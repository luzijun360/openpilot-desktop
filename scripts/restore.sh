#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" == "--check" ]]; then
  echo "[restore] checking patches apply cleanly..."
  TMP=$(mktemp -d)
  git clone --depth 1 https://github.com/commaai/openpilot.git "$TMP/openpilot" 2>&1 | tail -n 3
  (cd "$TMP/openpilot" && git fetch --depth 1 origin 49bbba371c29c5612e69b8ea9f906e151410e8bc 2>/dev/null && git checkout 49bbba371c29c5612e69b8ea9f906e151410e8bc 2>/dev/null || true)
  ok=1
  for p in "$REPO_ROOT"/patches/openpilot*.patch; do
    if ! (cd "$TMP/openpilot" && git apply --check "$p" 2>&1); then echo "[restore] FAIL: $(basename "$p")"; ok=0; else echo "[restore] ok: $(basename "$p")"; fi
  done
  rm -rf "$TMP"
  [[ $ok == 1 ]] && echo "[restore] all patches apply cleanly" || { echo "[restore] some patches need update"; exit 1; }
  exit 0
fi
echo "Usage: $0 --check"
