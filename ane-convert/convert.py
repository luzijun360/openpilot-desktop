"""supercombo ONNX → CoreML mlpackage（目标：ANE）。
阶段 7.3：转换 + 首次前向 + 耗时测量。"""
import os, time
import numpy as np
import coremltools as ct

SRC = "/Users/lu/op项目of all/openpilot/openpilot/selfdrive/modeld/models/driving_supercombo.onnx"
OUT = "/Users/lu/op项目of all/ane-convert/driving_supercombo.mlpackage"

t0 = time.time()
print("开始转换（coremltools %s）…" % ct.__version__, flush=True)
ml = ct.convert(
    SRC,
    source="onnx",
    convert_to="mlprogram",
    compute_units=ct.ComputeUnit.ALL,          # 允许使用 ANE
    minimum_deployment_target=ct.target.macOS13,
)
print("转换耗时 %.1f 秒" % (time.time() - t0), flush=True)

print("\n=== CoreML 模型输入 ===")
for name, desc in ml.input_description.items():
    print(f"  {name:22s} {desc.type}  {desc.shape if hasattr(desc,'shape') else ''}")
print("=== CoreML 模型输出 ===")
for name, desc in ml.output_description.items():
    print(f"  {name:22s} {desc.type}  {desc.shape if hasattr(desc,'shape') else ''}")

ml.save(OUT)
size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
print(f"\n已保存 {OUT}（{size/1e6:.1f} MB）", flush=True)
