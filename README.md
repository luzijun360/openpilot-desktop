# openpilot-mac — openpilot on Mac (M1 8GB) · 视频 → comma 同款可视化

> **一句话**：在 MacBook Air M1（8GB）上，把任意道路视频丢进去，得到 comma 设备上那套车道线 / 路沿 / 行驶路径 / 前车标记的实时叠加画面。离线可跑，无需真车。

[![Based on](https://img.shields.io/badge/based%20on-commaai%2Fopenpilot%4049bbba3-blue)](https://github.com/commaai/openpilot)
[![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-lightgrey)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Base**: `commaai/openpilot@49bbba3` (main, 2026-09-26) + 6 submodules · **封版**: 2026-09-30 双 app 逻辑版（M0→M9 全完成）

---

## 效果

- 输入：任意道路视频（行车记录仪 / 网络视频 / 录屏，任意分辨率，免转码）
- 输出：comma 同款可视化线条（车道线、路沿、预测路径、前车三角）+ HUD 状态 + 可选纵向控制闭环
- 控制台：桌面 app `openpilot 控制台.app`（1600×820）+ 移动端网页 `http://127.0.0.1:8899/m`，实时看模型输出与系统状态
- 加速：tinygrad/Metal 默认 13.6ms/帧，ANE（CoreML mlpackage）4.36ms/帧，`OP_MODEL_BACKEND=coreml` 一键切换

## 快速开始（3 步）

```bash
git clone https://github.com/<you>/openpilot-mac.git && cd openpilot-mac
./scripts/setup.sh          # 克隆上游 49bbba3 → git lfs pull（huggingface）→ 打补丁 → uv sync → scons -j4
./scripts/run.sh demo.mp4   # 丢一个视频进去，打开控制台看线条
```

`setup.sh` 会自检 `brew / python3.12 / uv / ffmpeg / git-lfs / Xcode CLT`，缺什么会提示如何装；失败可重试。

控制台地址：

- 桌面：`http://127.0.0.1:8899/`
- 手机/局域网：`http://127.0.0.1:8899/m`（需与 Mac 同一网络；Tailscale 远程见 `docs/slowroads-任务清单.md`）

## 权重说明（别人能跑的关键）

本仓库不直接提交大权重，保持 `git clone <5MB` 秒级。首次 `./scripts/setup.sh` 会自动从上游拉取：

| 权重 | 大小 | 来源 | 备注 |
|---|---|---|---|
| `driving_tinygrad.pkl` + `warp_*.pkl` + `dm_*`（小模型） | 约 61MB + 几MB | `huggingface.co/commaai/openpilot-lfs` via `git lfs pull` | **必需**，M1 8GB 默认只用这个 |
| `big_driving_tinygrad.pkl` 等大模型 | 773MB | 同上 | 可选，默认跳过（需 `INCLUDE_BIG_MODEL=1`） |
| `driving_supercombo.mlpackage`（ANE 自编译产物） | 51MB | GitHub Release 附件，或本地 `ane-convert/convert_v2.py` 现场生成 | 可选，默认回退 tinygrad/Metal 即可跑 |

`run.sh` 默认 `OP_MODEL_BACKEND=coreml`，若本机无 mlpackage 会自动回退 Metal，不会起不来。

## 目录结构

```
openpilot-mac/
├── README.md / README_EN.md / LICENSE(MIT) / VERSION
├── docs/                     # 移植全记录（IDEA / PLAN / CHANGELOG / 跳变根因报告等）
├── patches/                  # 相对上游 49bbba3 的全量补丁（7 个，含 tinygrad/panda 等）
├── offline_demo/             # 离线管线核心：视频→线条
│   ├── console.html / console_mobile.html
│   ├── console_server.py / console_mobile.py / fake_car_bridge.py
│   ├── run_offline_demo.sh / op_app_launcher.sh / jump_probe.py
│   ├── beamng_bridge/        # 接 BeamNG 窗口的 3 个小脚本
│   └── slowroads/            # 可选分支：slowroads / BeamNG 游戏接入（默认关闭）
├── ane-convert/              # ANE 转换链（ONNX→CoreML），含 convert_v2.py / measure_ane.py
├── scripts/                  # setup.sh / run.sh / build_ane.sh / restore.sh
└── assets/                   # 图标与 iconset
```

测试视频（972MB/91个）与 ANE 中间产物 `*.onnx/*.mlpackage` 不进主分支，见 `docs/测试素材说明.md` 与 Release。

## 使用教程

### 1) 跑自己的视频

```bash
./scripts/run.sh /path/to/your_video.mp4
# 或
./scripts/run.sh --pick   # 弹文件选择框（桌面）
```

控制台会自动索引 `docs` 中说明的素材目录，支持暂停/倍速/重播/截图/导出模型 JSON。

### 2) 切换推理后端

```bash
OP_MODEL_BACKEND=coreml ./scripts/run.sh demo.mp4   # ANE（默认，需 mlpackage）
OP_MODEL_BACKEND=tinygrad ./scripts/run.sh demo.mp4  # Metal 回退
```

也可在控制台右上角「推理引擎」一键切换，栈会自动重启约 40 秒生效。

### 3) slowroads / BeamNG（可选）

```bash
./offline_demo/slowroads/slowroads_app_launcher.sh   # 需自备 slowroads 网页/游戏
./offline_demo/slowroads/build_slowroads_app.sh      # 构建 slowroads.app（如需）
```

该分支默认关闭，不影响主流程 `视频→线条`。详见 `offline_demo/slowroads/README.md` 与 `docs/slowroads-任务清单.md`。

### 4) 性能与排障

- 模型帧率天花板约 19Hz（干净）/ 12Hz（开控制台页），8GB M1 极限；启动约 40 秒有浮层遮盖。
- 前车距离为单目估算，绝对值仅供参考。
- 常见坑见 `docs/CHANGELOG.md` 排障笔记（看门狗、日志缓冲、vEgo、%CPU 测量等）。

## 开发与复现

```bash
./scripts/restore.sh --check   # 校验 patches 是否干净合入
./scripts/build_ane.sh         # 本地重编 mlpackage（需 coremltools，见 ane-convert/README.md）
```

上游更新：修改 `scripts/setup.sh` 中的 `BASE_SHA=49bbba3` 并重新生成 `patches/*.patch`。

## 致谢

基于 [commaai/openpilot](https://github.com/commaai/openpilot)（MIT），ML 模型与字体等资源遵循上游许可；本仓库仅包含移植层与控制台，未分发游戏本体或私有测试视频。
