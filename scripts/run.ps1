param([string]$Video, [ValidateSet('cpu','gpu','cuda','coreml','tinygrad')][string]$Backend='cpu', [switch]$Pick)
$REPO_ROOT=(Resolve-Path "$PSScriptRoot/..").Path
$UPSTREAM_DIR=if ($env:OPENPILOT_DIR) { $env:OPENPILOT_DIR } else { "$REPO_ROOT/../openpilot-upstream" }
if (Test-Path "$REPO_ROOT/openpilot/launch_openpilot.sh") { $UPSTREAM_DIR="$REPO_ROOT/openpilot" }
if ($Pick) { Start-Process "$REPO_ROOT/offline_demo/console.html"; Write-Host '[run] picker opened at http://127.0.0.1:8899/'; exit 0 }
if (-not $Video) { Write-Host "Usage: .\scripts\run.ps1 <video.mp4> [-Backend cpu|gpu|cuda] | -Pick"; exit 1 }
if (-not (Test-Path $Video)) { Write-Host "[run] not found: $Video"; exit 1 }
$env:OP_MODEL_BACKEND=$Backend
if ($Backend -eq 'cuda') { try { nvidia-smi | Out-Null } catch { Write-Host '[run] CUDA not detected — falling back to cpu'; $env:OP_MODEL_BACKEND='cpu' } }
# sync overlay
if (Test-Path "$REPO_ROOT/offline_demo") { Copy-Item "$REPO_ROOT/offline_demo/*.html","$REPO_ROOT/offline_demo/*.py" -Destination "$UPSTREAM_DIR/offline_demo/" -Force -ErrorAction SilentlyContinue }
$runSh="$UPSTREAM_DIR/offline_demo/run_offline_demo.sh"
if (Test-Path $runSh) {
  if (Get-Command bash -ErrorAction SilentlyContinue) { bash $runSh $Video; exit $LASTEXITCODE }
  if (Get-Command wsl -ErrorAction SilentlyContinue) { wsl bash $runSh $Video; exit $LASTEXITCODE }
}
Write-Host "[run] bash not found — install Git Bash and retry"
