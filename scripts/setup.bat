@echo off
setlocal EnableDelayedExpansion
REM openpilot-mac Windows setup (cmd) — CPU/GPU/CUDA 通用
REM Flow: clone upstream @49bbba3 -> git lfs pull (huggingface ~65MB) -> apply patches -> uv sync -> scons
set "BASE_SHA=49bbba371c29c5612e69b8ea9f906e151410e8bc"
set "BASE_URL=https://github.com/commaai/openpilot.git"
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
if defined OPENPILOT_DIR (set "UPSTREAM_DIR=%OPENPILOT_DIR%") else (set "UPSTREAM_DIR=%REPO_ROOT%\..\openpilot-upstream")
if exist "%REPO_ROOT%\openpilot\launch_openpilot.sh" set "UPSTREAM_DIR=%REPO_ROOT%\openpilot"
echo [setup] checking toolchain...
where git >nul 2>&1 || (echo [setup] missing: git — https://git-scm.com/ && exit /b 1)
where python >nul 2>&1 || where python3 >nul 2>&1 || (echo [setup] missing: Python 3.12 — https://www.python.org/downloads/ && exit /b 1)
where ffmpeg >nul 2>&1 || echo [setup] warning: ffmpeg not found — winget install ffmpeg
where uv >nul 2>&1 || (echo [setup] missing: uv — pip install uv && exit /b 1)
git lfs version >nul 2>&1 || echo [setup] warning: git-lfs not found — https://git-lfs.github.com/
if not exist "%UPSTREAM_DIR%\.git" if not exist "%UPSTREAM_DIR%\launch_openpilot.sh" (
  echo [setup] cloning %BASE_URL% @ %BASE_SHA% -^> %UPSTREAM_DIR%
  git clone "%BASE_URL%" "%UPSTREAM_DIR%"
  if errorlevel 1 exit /b 1
)
cd /d "%UPSTREAM_DIR%"
git fetch origin --depth 1 %BASE_SHA% 2>nul || git fetch origin
 git checkout %BASE_SHA% 2>nul || git checkout -f %BASE_SHA%
 git submodule sync --recursive >nul 2>&1
 git submodule update --init --recursive --depth 1 2>nul || git submodule update --init --recursive
if "%INCLUDE_BIG_MODEL%"=="1" (
  echo [setup] pulling all LFS including big_* (~800MB)
  git lfs pull
) else (
  echo [setup] pulling LFS small models only (~65MB) — set INCLUDE_BIG_MODEL=1 to fetch big_*
  git lfs pull --include "openpilot/selfdrive/modeld/models/driving_tinygrad.pkl,openpilot/selfdrive/modeld/models/driving_warp_*.pkl,openpilot/selfdrive/modeld/models/dm_*.pkl,openpilot/selfdrive/modeld/models/dmonitoring_model*" 2>nul || git lfs pull
)
set "PATCH_DIR=%REPO_ROOT%\patches"
for %%P in ("%PATCH_DIR%\openpilot.patch" "%PATCH_DIR%\openpilot__*.patch") do (
  if exist %%P (
    echo [setup] applying %%~nxP
    git apply --check "%%P" >nul 2>&1 && git apply "%%P" || echo [setup] %%~nxP already applied or conflicts — skipping ^(run scripts\restore.bat^)
  )
)
REM overlay offline_demo into upstream (copy, keep user state out)
if exist "%REPO_ROOT%\offline_demo" (
  xcopy /E /I /Y "%REPO_ROOT%\offline_demo\*.html" "%UPSTREAM_DIR%\offline_demo\" >nul 2>&1
  xcopy /E /I /Y "%REPO_ROOT%\offline_demo\*.py" "%UPSTREAM_DIR%\offline_demo\" >nul 2>&1
  xcopy /E /I /Y "%REPO_ROOT%\offline_demo\*.sh" "%UPSTREAM_DIR%\offline_demo\" >nul 2>&1
  xcopy /E /I /Y "%REPO_ROOT%\offline_demo\beamng_bridge\*" "%UPSTREAM_DIR%\beamng_bridge\" >nul 2>&1
)
echo [setup] uv sync --frozen --all-extras
uv sync --frozen --all-extras || uv sync --all-extras
if errorlevel 1 exit /b 1
echo [setup] building scons -u -j4
scons -u -j4 || scons -u -j2
if errorlevel 1 exit /b 1
echo [setup] done. Next: scripts\run.bat demo.mp4 [cpu^|gpu^|cuda]
