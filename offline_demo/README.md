# offline_demo — 视频 → 线条 主链路

> 核心：把任意视频喂给 openpilot 的 `webcamerad → modeld → ui` 管线，得到 comma 同款可视化。

## 启动

- Mac: `../scripts/run.sh demo.mp4` 或 `../scripts/setup.sh` 后 `./run_offline_demo.sh demo.mp4`
- Win: `..\\scripts\\run.bat demo.mp4 [cpu|gpu|cuda]` 或 `..\\scripts\\run.ps1 demo.mp4 -Backend cuda`

控制台：`http://127.0.0.1:8899/`（桌面），`/m`（手机/同网段）。

## 后端环境变量

`OP_MODEL_BACKEND`：

- Mac: `coreml`（ANE，默认）/ `tinygrad`（Metal）
- Win: `cpu`（LLVM，默认）/ `gpu` / `cuda`

无对应加速时自动回退，控制台右上角也可一键切换。

## 文件索引

`console.html` 控制台页面 · `console_server.py` 后端 · `fake_car_bridge.py` 假车桥接 · `run_offline_demo.sh` 一键起栈 · `prepare_video.sh` 转码 · `beamng_bridge/` 窗口桥接 · `slowroads/` 可选分支（见 `slowroads/README.md`）。
