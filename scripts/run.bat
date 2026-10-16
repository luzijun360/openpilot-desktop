@echo off
setlocal
REM usage: scripts\run.bat <video.mp4> [cpu|gpu|cuda]  or  scripts\run.bat --pick
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
if defined OPENPILOT_DIR (set "UPSTREAM_DIR=%OPENPILOT_DIR%") else (set "UPSTREAM_DIR=%REPO_ROOT%\..\openpilot-upstream")
if exist "%REPO_ROOT%\openpilot\launch_openpilot.sh" set "UPSTREAM_DIR=%REPO_ROOT%\openpilot"
if "%~1"=="--pick" (
  echo [run] opening file picker — choose a video in the console at http://127.0.0.1:8899/
  start "" "%REPO_ROOT%\offline_demo\console.html" 2>nul
  exit /b 0
)
set "VIDEO=%~1"
set "BACKEND=%~2"
if "%VIDEO%"=="" (echo Usage: %~nx0 ^<video.mp4^> [cpu^|gpu^|cuda] ^| %~nx0 --pick & exit /b 1)
if not exist "%VIDEO%" (echo [run] not found: %VIDEO% & exit /b 1)
if "%BACKEND%"=="" set "BACKEND=cpu"
REM map backend to tinygrad device / env
set "OP_MODEL_BACKEND=%BACKEND%"
if /I "%BACKEND%"=="cpu" set "OP_MODEL_BACKEND=cpu"
if /I "%BACKEND%"=="gpu" set "OP_MODEL_BACKEND=gpu"
if /I "%BACKEND%"=="cuda" (
  nvidia-smi >nul 2>&1 || (echo [run] CUDA not detected ^(nvidia-smi failed^) — falling back to cpu & set "OP_MODEL_BACKEND=cpu")
)
REM sync overlay
if exist "%REPO_ROOT%\offline_demo" xcopy /E /I /Y "%REPO_ROOT%\offline_demo\*.html" "%UPSTREAM_DIR%\offline_demo\" >nul 2>&1
if exist "%REPO_ROOT%\offline_demo" xcopy /E /I /Y "%REPO_ROOT%\offline_demo\*.py" "%UPSTREAM_DIR%\offline_demo\" >nul 2>&1
if exist "%REPO_ROOT%\offline_demo" xcopy /E /I /Y "%REPO_ROOT%\offline_demo\*.sh" "%UPSTREAM_DIR%\offline_demo\" >nul 2>&1
set "RUN_SH=%UPSTREAM_DIR%\offline_demo\run_offline_demo.sh"
if not exist "%RUN_SH%" (echo [run] not found: %RUN_SH% — run setup first & exit /b 1)
REM run via bash (Git Bash) or wsl if available; fallback to python direct
where bash >nul 2>&1 && (bash "%RUN_SH%" "%VIDEO%" & exit /b) || (
  echo [run] bash not found — trying python offline_demo directly
  python "%UPSTREAM_DIR%\offline_demo\console_server.py" 2>&1
)
