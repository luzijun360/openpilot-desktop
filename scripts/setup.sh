#!/usr/bin/env bash
set -euo pipefail
# openpilot-mac one-click setup
# Flow: clone upstream @49bbba3 → git lfs pull (huggingface) → apply patches → uv sync → scons -j4
BASE_SHA="49bbba371c29c5612e69b8ea9f906e151410e8bc"
BASE_URL="https://github.com/commaai/openpilot.git"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM_DIR="${OPENPILOT_DIR:-$REPO_ROOT/../openpilot-upstream}"
# allow running from repo root: checkout upstream as sibling dir
if [[ -d "$REPO_ROOT/openpilot" && -f "$REPO_ROOT/openpilot/launch_openpilot.sh" ]]; then
  echo "[setup] openpilot checkout already exists at $REPO_ROOT/openpilot — reusing"
  UPSTREAM_DIR="$REPO_ROOT/openpilot"
fi
need() { command -v "$1" >/dev/null 2>&1 || { echo "[setup] missing: $1 — please install it first"; exit 1; }; }
echo "[setup] checking toolchain..."
need git; need python3; need ffmpeg
if ! command -v uv >/dev/null 2>&1; then echo "[setup] uv not found — install: brew install uv  or  curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; fi
if ! git lfs version >/dev/null 2>&1 && ! "$REPO_ROOT"/.venv/bin/git-lfs version >/dev/null 2>&1; then
  echo "[setup] git-lfs not found — install: brew install git-lfs && git lfs install"; fi
mkdir -p "$(dirname "$UPSTREAM_DIR")"
if [[ ! -d "$UPSTREAM_DIR/.git" && ! -f "$UPSTREAM_DIR/launch_openpilot.sh" ]]; then
  echo "[setup] cloning $BASE_URL @ $BASE_SHA → $UPSTREAM_DIR"
  git clone "$BASE_URL" "$UPSTREAM_DIR"
fi
cd "$UPSTREAM_DIR"
git fetch origin --depth 1 "$BASE_SHA" 2>/dev/null || git fetch origin
# checkout base (detached)
git checkout "$BASE_SHA" 2>/dev/null || git checkout -f "$BASE_SHA"
git submodule sync --recursive || true
git submodule update --init --recursive --depth 1 || git submodule update --init --recursive
# LFS: pull small models (big_* skipped unless requested)
if [[ "${INCLUDE_BIG_MODEL:-}" == "1" ]]; then
  echo "[setup] pulling all LFS (including big_*) — this is ~800MB"
  git lfs pull || .venv/bin/git-lfs pull || true
else
  echo "[setup] pulling LFS (small models only, ~65MB) — set INCLUDE_BIG_MODEL=1 to fetch big_* as well"
  git lfs pull --include "openpilot/selfdrive/modeld/models/driving_tinygrad.pkl,openpilot/selfdrive/modeld/models/driving_warp_*.pkl,openpilot/selfdrive/modeld/models/dm_*.pkl,openpilot/selfdrive/modeld/models/dmonitoring_model*" 2>/dev/null || git lfs pull || true
fi
# Apply overlay patches (idempotent: skip if already applied)
PATCH_DIR="$REPO_ROOT/patches"
for p in "$PATCH_DIR"/openpilot.patch "$PATCH_DIR"/openpilot__*.patch; do
  [[ -f "$p" ]] || continue
  echo "[setup] applying $(basename "$p")"
  # try apply; if already applied, check will fail — skip
  if git apply --check "$p" 2>/dev/null; then
    git apply "$p"
  else
    echo "[setup] $(basename "$p") already applied or conflicts — skipping (run scripts/restore.sh --check)"
  fi
done
# Overlay offline_demo / ane-convert into upstream checkout (symlink or copy)
# We keep offline_demo as the source of truth in this overlay repo; copy into upstream for scons/run
copy_overlay() {
  local src="$REPO_ROOT/offline_demo"
  local dst="$UPSTREAM_DIR/offline_demo"
  mkdir -p "$dst"
  # rsync-like copy without deleting user state (logs/frames auto-ignored)
  (cd "$src" && tar cf - --exclude='logs' --exclude='frames' --exclude='*.flag' --exclude='*.jpg' --exclude='*.pid' --exclude='*.log' --exclude='*.mp4' .) | (cd "$dst" && tar xf -)
  echo "[setup] offline_demo overlay copied → $dst"
  local s2="$REPO_ROOT/offline_demo/slowroads"
  if [[ -d "$s2" ]]; then
    mkdir -p "$dst/slowroads"
    (cd "$s2" && tar cf - .) | (cd "$dst/slowroads" && tar xf -)
  fi
  local bsrc="$REPO_ROOT/offline_demo/beamng_bridge"
  local bdst="$UPSTREAM_DIR/beamng_bridge"
  if [[ -d "$bsrc" ]]; then mkdir -p "$bdst"; (cd "$bsrc" && tar cf - .) | (cd "$bdst" && tar xf -); fi
}
copy_overlay
# Python env + build
echo "[setup] uv sync --frozen --all-extras (this may take a few minutes)"
uv sync --frozen --all-extras || uv sync --all-extras
echo "[setup] building (scons -u -j4)"
scons -u -j4 || scons -u -j2
# Optional ANE mlpackage from Release
echo "[setup] done. Next: ./scripts/run.sh demo.mp4"
echo "[setup] Tip: ANE mlpackage (51MB) → ./scripts/build_ane.sh  or download from GitHub Release"
