# openpilot-mac — 视频 → comma 同款可视化（M1/M2/M3 与 Windows 通用）

> **一句话**：丢进去一个行车视频，得到 comma 设备上那套车道线 / 路沿 / 行驶路径 / 前车标记的实时叠加画面。离线可跑，无需真车，Mac 与 Windows 均可。

[![Based on](https://img.shields.io/badge/based%20on-commaai%2Fopenpilot%4049bbba3-blue)](https://github.com/commaai/openpilot)
[![Mac](https://img.shields.io/badge/Mac-M1%2FM2%2FM3%20%E2%80%A2%20ANE%2FMetal-black)](https://www.apple.com/mac/)
[![Windows](https://img.shields.io/badge/Windows-CPU%2FGPU%2FCUDA-0078D6)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Base**: `commaai/openpilot@49bbba3` (main, 2026-09-26) · **封版**: 2026-09-30 双 app · **首次 clone <5MB**

---

## 怎么打开 / 怎么用（一眼看懂）

| 你在什么系统 | 第 1 步：装好 | 第 2 步：一键起 | 第 3 步：看画面 |
|---|---|---|---|
| **Mac**（M1/M2/M3，8GB 也可） | `brew install python@3.12 uv ffmpeg git-lfs` + Xcode CLT | `git clone ... && cd openpilot-mac && ./scripts/setup.sh` | `./scripts/run.sh demo.mp4` → 打开 `http://127.0.0.1:8899/` |
| **Windows**（CPU / NVIDIA GPU / CUDA） | 装 `Python 3.12 + Git + ffmpeg`（见下方 Win 教程） | `git clone ... && cd openpilot-mac && scripts\\setup.bat` 或 `powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1` | `scripts\\run.bat demo.mp4` → 打开 `http://127.0.0.1:8899/` |

就 3 步。`setup` 会自动从 `huggingface.co/commaai/openpilot-lfs` 拉回小模型（约 65MB，`big_* 773MB` 默认跳过），`run` 默认 ANE（Mac）或你选的 `cpu/gpu/cuda`（Win），没对应加速就自动回退，不会起不来。

> 懒人入口：Mac 双击 `scripts/setup.command`；Win 双击 `scripts/setup.bat`。

---

## 快速开始

### Mac

```bash
git clone https://github.com/<you>/openpilot-mac.git && cd openpilot-mac
./scripts/setup.sh          # 克隆上游 49bbba3 → git lfs pull（huggingface）→ 打补丁 → uv sync → scons -j4
./scripts/run.sh demo.mp4   # 丢一个视频进去，打开控制台看线条（或 ./scripts/run.sh --pick 弹框选文件）
```

控制台：桌面 `http://127.0.0.1:8899/`，手机/同网段 `http://127.0.0.1:8899/m`。

### Windows

```bat
REM cmd
 git clone https://github.com/<you>/openpilot-mac.git && cd openpilot-mac
 scripts\setup.bat
 scripts\run.bat demo.mp4
```

```powershell
# PowerShell
 git clone https://github.com/<you>/openpilot-mac.git; cd openpilot-mac
 .\scripts\setup.ps1
 .\scripts\run.ps1 demo.mp4 -Backend cuda   # 可选：cpu / gpu / cuda，默认 cpu
```

> Win 常见坑已在脚本里处理：中文路径、长路径、PowerShell 执行策略、缺 `ffmpeg`/`git-lfs` 的提示。详见 `docs/WINDOWS.md`。

---

## 推理后端（Mac / Win 对照）

| 后端 | 适用 | 怎么选 | 速度（参考） |
|---|---|---|---|
| `coreml`（ANE） | Mac 独有，M1/M2/M3 | `OP_MODEL_BACKEND=coreml ./scripts/run.sh demo.mp4`（默认） | 4.36ms/帧，modeld ~15.7% |
| `tinygrad:METAL` | Mac 回退 | `OP_MODEL_BACKEND=tinygrad ./scripts/run.sh demo.mp4` | 13.6ms/帧，modeld ~38% |
| `cpu`（LLVM） | Win 通用，无需显卡 | `scripts\\run.bat demo.mp4` 或 `-Backend cpu` | 可用，CPU 占用较高 |
| `gpu` / `cuda` | Win + NVIDIA 显卡 + CUDA | `scripts\\run.bat demo.mp4 cuda` 或 `-Backend cuda` | 显著更快（取决于显卡） |

也可在控制台右上角「推理引擎」一键切换，栈会自动重启约 40 秒生效。Win 上切 `cuda` 前会检测 `nvidia-smi` / `CUDA_PATH`，不通过则回退 `cpu`。

---

## 效果

- 输入：任意道路视频（行车记录仪 / 网络视频 / 录屏，任意分辨率，免转码，实时对齐 1928×1208）
- 输出：comma 同款可视化（车道线 / 路沿 / 预测路径 / 前车三角）+ HUD + 可选纵向控制闭环
- 加速：Mac 上 `tinygrad/Metal` 与 `ANE(CoreML)` 一键互切；Win 上 `cpu/gpu/cuda` 一键互切

---

## 权重说明（别人能跑的关键）

本仓库不直接提交大权重，保持 `git clone <5MB` 秒级。首次 `setup` 会自动从上游拉取：

| 权重 | 大小 | 来源 | 备注 |
|---|---|---|---|
| `driving_tinygrad.pkl` + `warp_*.pkl` + `dm_*`（小模型） | 约 61MB + 几MB | `huggingface.co/commaai/openpilot-lfs` via `git lfs pull` | **必需** |
| `big_driving_tinygrad.pkl` 等大模型 | 773MB | 同上 | 可选，默认跳过（`INCLUDE_BIG_MODEL=1`） |
| `driving_supercombo.mlpackage`（Mac ANE 产物） | 51MB | GitHub Release 附件，或 `scripts/build_ane.sh` 本地生成 | 可选，无则回退 tinygrad |

---

## 教程

- **Mac 详细**：`docs/USAGE_MAC.md`
- **Windows 详细**：`docs/WINDOWS.md`
- **素材说明**（972MB/91个视频不进库）：`docs/测试素材说明.md`
- **slowroads 可选分支**：`offline_demo/slowroads/README.md` + `docs/slowroads-任务清单.md`
- **移植全记录**：`docs/IDEA.md` `docs/PLAN.md` `docs/CHANGELOG.md` `docs/跳变-根因与修复计划.md`

---

## 目录

```
openpilot-mac/
├── README.md / README_EN.md / LICENSE / VERSION
├── docs/                     # 教程与移植记录
│   ├── USAGE_MAC.md / WINDOWS.md / 测试素材说明.md
│   └── IDEA.md / PLAN.md / CHANGELOG.md ...
├── patches/                  # 相对上游 49bbba3 的全量补丁（7 个）
├── offline_demo/             # 离线管线核心：视频→线条
│   ├── console.html / console_mobile.html
│   ├── console_server.py / fake_car_bridge.py
│   ├── run_offline_demo.sh / op_app_launcher.sh
│   ├── beamng_bridge/        # 接 BeamNG 窗口的 3 个小脚本
│   └── slowroads/            # 可选分支，默认关闭
├── ane-convert/              # ANE 转换链（Mac）+ 说明
├── scripts/                  # 一键脚本（Mac+Win）
│   ├── setup.sh / setup.bat / setup.ps1 / setup.command
│   ├── run.sh / run.bat / run.ps1
│   └── build_ane.sh / restore.sh
└── assets/
```

---

## 致谢

基于 [commaai/openpilot](https://github.com/commaai/openpilot)（MIT），模型与字体等资源遵循上游许可；本仓库仅包含移植层与控制台，未分发游戏本体或私有测试视频。
