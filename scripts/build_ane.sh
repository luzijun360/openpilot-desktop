#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Try Release download first
RELEASE_URL="${ANE_MLPACKAGE_URL:-}"
if [[ -n "$RELEASE_URL" ]]; then
  echo "[build_ane] downloading mlpackage from $RELEASE_URL"
  curl -L "$RELEASE_URL" -o "/tmp/driving_supercombo.mlpackage.tar.gz"
  tar xzf /tmp/driving_supercombo.mlpackage.tar.gz -C "$REPO_ROOT/ane-convert/" 2>/dev/null || unzip -o /tmp/driving_supercombo.mlpackage.tar.gz -d "$REPO_ROOT/ane-convert/" 2>/dev/null || true
fi
if [[ -d "$REPO_ROOT/ane-convert/driving_supercombo.mlpackage" ]]; then
  echo "[build_ane] mlpackage already present — skipping build"
  # also copy into upstream if exists
  for d in "$REPO_ROOT/openpilot" "$REPO_ROOT/../openpilot-upstream"; do
    if [[ -d "$d/openpilot/selfdrive/modeld/models" ]]; then mkdir -p "$d/openpilot/selfdrive/modeld/models"; cp -R "$REPO_ROOT/ane-convert/driving_supercombo.mlpackage" "$d/openpilot/selfdrive/modeld/models/" 2>/dev/null || true; fi
  done
  exit 0
fi
echo "[build_ane] building mlpackage locally via ane-convert/convert_v2.py"
VENV="$REPO_ROOT/ane-convert/.venv63"
if [[ ! -d "$VENV" ]]; then python3.10 -m venv "$VENV" 2>/dev/null || python3 -m venv "$VENV"; fi
"$VENV/bin/pip" install -q coremltools==7.2 onnx onnx2torch torch 2>&1 | tail -n 5
"$VENV/bin/python" "$REPO_ROOT/ane-convert/convert_v2.py"
if [[ -d "$REPO_ROOT/ane-convert/driving_supercombo.mlpackage" ]]; then
  for d in "$REPO_ROOT/openpilot" "$REPO_ROOT/../openpilot-upstream"; do
    if [[ -d "$d/openpilot/selfdrive/modeld/models" ]]; then cp -R "$REPO_ROOT/ane-convert/driving_supercombo.mlpackage" "$d/openpilot/selfdrive/modeld/models/" 2>/dev/null || true; fi
  done
  echo "[build_ane] done"
else echo "[build_ane] failed — check ane-convert logs"; exit 1; fi
