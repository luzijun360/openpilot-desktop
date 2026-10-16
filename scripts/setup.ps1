# openpilot-mac Windows setup (PowerShell) — CPU/GPU/CUDA 通用
param([switch]$IncludeBigModel)
$ErrorActionPreference='Stop'
$BASE_SHA='49bbba371c29c5612e69b8ea9f906e151410e8bc'
$BASE_URL='https://github.com/commaai/openpilot.git'
$REPO_ROOT=(Resolve-Path "$PSScriptRoot/..").Path
$UPSTREAM_DIR=if ($env:OPENPILOT_DIR) { $env:OPENPILOT_DIR } else { "$REPO_ROOT/../openpilot-upstream" }
if (Test-Path "$REPO_ROOT/openpilot/launch_openpilot.sh") { $UPSTREAM_DIR="$REPO_ROOT/openpilot" }
function Need($cmd,$hint){ if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Write-Host "[setup] missing: $cmd — $hint"; exit 1 } }
Write-Host "[setup] checking toolchain..."
Need git 'https://git-scm.com/'
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) { Write-Host '[setup] missing: Python 3.12'; exit 1 }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host '[setup] warning: ffmpeg not found — winget install ffmpeg' }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Host '[setup] missing: uv — pip install uv'; exit 1 }
if (-not (Get-Command git-lfs -ErrorAction SilentlyContinue)) { try { git lfs version | Out-Null } catch { Write-Host '[setup] warning: git-lfs not found' } }
if (-not (Test-Path "$UPSTREAM_DIR/.git") -and -not (Test-Path "$UPSTREAM_DIR/launch_openpilot.sh")) {
  Write-Host "[setup] cloning $BASE_URL @ $BASE_SHA -> $UPSTREAM_DIR"
  git clone $BASE_URL $UPSTREAM_DIR
}
Push-Location $UPSTREAM_DIR
try {
  git fetch origin --depth 1 $BASE_SHA 2>$null; if ($LASTEXITCODE -ne 0) { git fetch origin }
  git checkout $BASE_SHA 2>$null; if ($LASTEXITCODE -ne 0) { git checkout -f $BASE_SHA }
  git submodule sync --recursive | Out-Null
  git submodule update --init --recursive --depth 1 2>$null; if ($LASTEXITCODE -ne 0) { git submodule update --init --recursive }
  if ($IncludeBigModel -or $env:INCLUDE_BIG_MODEL -eq '1') { Write-Host '[setup] pulling all LFS (~800MB)'; git lfs pull } else { Write-Host '[setup] pulling LFS small models (~65MB)'; git lfs pull --include 'openpilot/selfdrive/modeld/models/driving_tinygrad.pkl,openpilot/selfdrive/modeld/models/driving_warp_*.pkl,openpilot/selfdrive/modeld/models/dm_*.pkl,openpilot/selfdrive/modeld/models/dmonitoring_model*' 2>$null; if ($LASTEXITCODE -ne 0) { git lfs pull } }
  $patchDir="$REPO_ROOT/patches"
  foreach ($p in @(Get-ChildItem "$patchDir/openpilot.patch" -ErrorAction SilentlyContinue) + @(Get-ChildItem "$patchDir/openpilot__*.patch" -ErrorAction SilentlyContinue)) {
    if ($p) { Write-Host "[setup] applying $($p.Name)"; git apply --check $p.FullName 2>$null; if ($LASTEXITCODE -eq 0) { git apply $p.FullName } else { Write-Host "[setup] $($p.Name) already applied — skipping" } }
  }
  # overlay
  if (Test-Path "$REPO_ROOT/offline_demo") {
    Copy-Item "$REPO_ROOT/offline_demo/*.html","$REPO_ROOT/offline_demo/*.py","$REPO_ROOT/offline_demo/*.sh" -Destination "$UPSTREAM_DIR/offline_demo/" -Force -ErrorAction SilentlyContinue
    if (Test-Path "$REPO_ROOT/offline_demo/beamng_bridge") { Copy-Item "$REPO_ROOT/offline_demo/beamng_bridge/*" -Destination "$UPSTREAM_DIR/beamng_bridge/" -Force -Recurse -ErrorAction SilentlyContinue }
  }
  Write-Host '[setup] uv sync'
  uv sync --frozen --all-extras; if ($LASTEXITCODE -ne 0) { uv sync --all-extras }
  Write-Host '[setup] scons -u -j4'
  scons -u -j4; if ($LASTEXITCODE -ne 0) { scons -u -j2 }
  Write-Host '[setup] done. Next: .\scripts\run.ps1 demo.mp4 [-Backend cpu|gpu|cuda]'
} finally { Pop-Location }
