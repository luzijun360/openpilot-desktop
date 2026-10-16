#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM_DIR="${OPENPILOT_DIR:-$REPO_ROOT/../openpilot-upstream}"
if [[ -d "$REPO_ROOT/openpilot" && -f "$REPO_ROOT/openpilot/launch_openpilot.sh" ]]; then UPSTREAM_DIR="$REPO_ROOT/openpilot"; fi
if [[ "${1:-}" == "--pick" ]]; then
  # delegate to console_server's pick via open app
  open "$REPO_ROOT/offline_demo/console.html" 2>/dev/null || xdg-open "$REPO_ROOT/offline_demo/console.html" 2>/dev/null || true
  echo "[run] opened file picker — choose a video in the console"
  exit 0
fi
VIDEO="${1:-}"
if [[ -z "$VIDEO" ]]; then echo "Usage: $0 <video.mp4> | $0 --pick"; exit 1; fi
if [[ ! -f "$VIDEO" ]]; then echo "[run] not found: $VIDEO"; exit 1; fi
# sync overlay again
if [[ -d "$REPO_ROOT/offline_demo" && -d "$UPSTREAM_DIR/offline_demo" ]]; then
  (cd "$REPO_ROOT/offline_demo" && tar cf - --exclude='logs' --exclude='frames' --exclude='*.flag' --exclude='*.jpg' --exclude='*.pid' --exclude='*.log' --exclude='*.mp4' .) | (cd "$UPSTREAM_DIR/offline_demo" && tar xf -)
fi
export OP_MODEL_BACKEND="${OP_MODEL_BACKEND:-coreml}"
# fallback if mlpackage missing
if [[ "$OP_MODEL_BACKEND" == "coreml" && ! -d "$UPSTREAM_DIR/openpilot/selfdrive/modeld/models/driving_supercombo.mlpackage" && ! -d "$REPO_ROOT/../openpilot-upstream/openpilot/selfdrive/modeld/models/driving_supercombo.mlpackage" ]]; then
  echo "[run] ANE mlpackage not found — falling back to tinygrad/Metal"
  export OP_MODEL_BACKEND=tinygrad
fi
exec "$UPSTREAM_DIR/offline_demo/run_offline_demo.sh" "$VIDEO"
