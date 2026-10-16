# openpilot-mac — Video → comma-style visualization (Mac + Windows)

> Drop in any road video, get comma's lane / road-edge / predicted path / lead-vehicle overlay. Offline, no car needed.

**Base**: `commaai/openpilot@49bbba3` (2026-09-26) · **Clone <5MB** — weights fetched on first `setup` from Hugging Face LFS.

## Get started at a glance

| OS | Step 1 | Step 2 | Step 3 |
|---|---|---|---|
| **Mac** (M1/M2/M3) | `brew install python@3.12 uv ffmpeg git-lfs` | `./scripts/setup.sh` | `./scripts/run.sh demo.mp4` → `http://127.0.0.1:8899/` |
| **Windows** (CPU/GPU/CUDA) | Install Python 3.12 + Git + ffmpeg | `scripts\\setup.bat` or `setup.ps1` | `scripts\\run.bat demo.mp4 [cpu|gpu|cuda]` → `http://127.0.0.1:8899/` |

Backends: Mac `coreml(ANE, 4.36ms)` / `tinygrad:METAL(13.6ms)`; Windows `cpu` / `gpu` / `cuda` (auto-fallback to cpu if CUDA not found). Toggle in console header.

See `README.md` (Chinese) and `docs/WINDOWS.md` / `docs/USAGE_MAC.md` for the full guide.
