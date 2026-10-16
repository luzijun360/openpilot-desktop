# ane-convert — ONNX → CoreML (ANE) 转换链

> 把 `driving_supercombo.onnx` 转为 `driving_supercombo.mlpackage`，在 M1 上走 ANE 推理（实测 13.6ms → 4.36ms/帧，modeld 38% → 15.7%）。

## 预编译产物（推荐）

直接从 GitHub Release 下载 `driving_supercombo.mlpackage`（51MB）放到 `openpilot/openpilot/selfdrive/modeld/models/`，或由 `scripts/build_ane.sh` 自动下载。

## 本地重编

```bash
./scripts/build_ane.sh           # 创建独立 venv（py3.10 + coremltools 7.2）并执行 convert_v2.py
# 或手动：
python3 -m venv ane-convert/.venv63
.venv63/bin/pip install coremltools==7.2 onnx onnx2torch torch
.venv63/bin/python ane-convert/convert_v2.py  # 产物 ane-convert/driving_supercombo.mlpackage
```

主脚本 `convert_v2.py` 为部署版（fp16），`convert_final.py` 为 fp32 备用；`measure_ane.py` 用于测 ANE 命中率与误差。
