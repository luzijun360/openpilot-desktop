# openpilot-mac — openpilot on Mac (M1 8GB) · Video → comma-style visualization

> Feed any road video in, get comma's lane / road-edge / predicted path / lead-vehicle overlay out. Offline, no car needed.

**Base**: `commaai/openpilot@49bbba3` (main, 2026-09-26) · **Release**: 2026-09-30 dual-app edition

## Quick start

```bash
git clone https://github.com/<you>/openpilot-mac.git && cd openpilot-mac
./scripts/setup.sh        # clone upstream 49bbba3 → git lfs pull (huggingface) → apply patches → uv sync → scons -j4
./scripts/run.sh demo.mp4 # drop a video, open the console to see the lines
```

Console: `http://127.0.0.1:8899/` (desktop) and `/m` (mobile). See `README.md` (Chinese) for full guide and `docs/` for the porting log.
