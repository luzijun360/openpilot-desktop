"""supercombo ONNX → PyTorch → CoreML mlpackage（最终版）。

路径：coremltools 6.0+ 无 ONNX 前端 → onnx2torch → jit.trace → ct.convert(mlprogram)

过程中解决的问题（均已核实语义等价，原模型文件不改动）：
1. Reshape opset19/20 的 allowzero=1：形状是常量且不含 0 → 置 0（allowzero 只在形状含 0 时才影响语义）
2. ReduceX 系列 opset18 起把 axes 从属性改成输入，而 onnx2torch 只有 v13 实现（属性形式）
   → 把常量 axes 搬回属性，并按输入秩归一化负轴
3. onnx2torch 完全没有 Gelu 实现 → 自实现（模型 20 个全是 approximate='tanh'，
   与 torch F.gelu(approximate='tanh') 公式一致）
4. 缺失算子的版本回退（opset20 → 已实现最高版本），逐条打印
5. 模型原生就是纯 fp16（315 个 float16 权重）→ 输入也走 fp16，全程一致
"""
import os, time
import numpy as np
import onnx
from onnx import numpy_helper, helper
import torch
import coremltools as ct

SRC = "/Users/lu/op项目of all/openpilot/openpilot/selfdrive/modeld/models/driving_supercombo.onnx"
FIXED = "/Users/lu/op项目of all/ane-convert/supercombo_fixed.onnx"
OUT = "/Users/lu/op项目of all/ane-convert/driving_supercombo.mlpackage"

print("coremltools", ct.__version__, flush=True)

# ---------- 0) 目标平台 ----------
def pick_target():
    for name in ("macOS15", "macOS14", "macOS13"):
        t = getattr(ct.target, name, None)
        if t is not None:
            return name, t
    return "iOS18", getattr(ct.target, "iOS18", None)

tname, TARGET = pick_target()
print("目标平台:", tname, flush=True)

# ---------- 1) 预处理 ONNX 副本 ----------
m = onnx.load(SRC)
m = onnx.shape_inference.infer_shapes(m)
init = {i.name: np.array(numpy_helper.to_array(i)) for i in m.graph.initializer}

rank = {}
for coll in (m.graph.input, m.graph.output, m.graph.value_info):
    for v in coll:
        d = v.type.tensor_type.shape.dim
        if len(d) and all(x.HasField("dim_value") for x in d):
            rank[v.name] = len(d)

REDUCE_OPS = {"ReduceL1", "ReduceL2", "ReduceLogSum", "ReduceLogSumExp", "ReduceMax",
              "ReduceMean", "ReduceMin", "ReduceProd", "ReduceSum", "ReduceSumSquare"}

problems, n_reshape, n_reduce = [], 0, 0

# 1a) Reshape: allowzero=1 且形状为常量、不含 0 → 置 0
for n in m.graph.node:
    if n.op_type != "Reshape":
        continue
    az = next((a for a in n.attribute if a.name == "allowzero"), None)
    if az is None or az.i == 0:
        continue
    shp = n.input[1]
    if shp not in init:
        problems.append((n.name, "Reshape 形状非常量")); continue
    if 0 in init[shp].tolist():
        problems.append((n.name, f"Reshape 形状含 0: {init[shp].tolist()}")); continue
    az.i = 0
    n_reshape += 1

# 1b) ReduceX: 常量 axes 输入 → axes 属性（负轴归一化）
for n in m.graph.node:
    if n.op_type not in REDUCE_OPS or len(n.input) < 2:
        continue
    axes_name = n.input[1]
    if axes_name not in init:
        problems.append((n.name, f"{n.op_type} 的 axes 非常量")); continue
    axes = [int(a) for a in np.atleast_1d(init[axes_name])]
    if not axes:
        problems.append((n.name, f"{n.op_type} axes 为空")); continue
    r = rank.get(n.input[0])
    if r is None:
        problems.append((n.name, f"{n.op_type} 无法确定输入秩")); continue
    axes = [a + r if a < 0 else a for a in axes]
    if any(a < 0 or a >= r for a in axes):
        problems.append((n.name, f"{n.op_type} axes 越界: {axes} (秩 {r})")); continue
    if any(a.name == "axes" for a in n.attribute):
        problems.append((n.name, f"{n.op_type} 同时存在 axes 属性与输入")); continue
    n.attribute.append(helper.make_attribute("axes", axes))
    del n.input[1]
    n_reduce += 1

if problems:
    for p in problems:
        print("  问题:", p, flush=True)
    raise SystemExit("中止：存在无法安全预处理的项目")

# 1c) 清理不再被引用的权重
used = {i for n in m.graph.node for i in n.input}
graph_inputs = {i.name for i in m.graph.input}
kept = [i for i in m.graph.initializer if i.name in used or i.name in graph_inputs]
dropped = len(m.graph.initializer) - len(kept)
del m.graph.initializer[:]
m.graph.initializer.extend(kept)

print(f"1) 预处理完成：Reshape allowzero 修正 {n_reshape} 个；Reduce axes 搬回属性 {n_reduce} 个；"
      f"清理无用权重 {dropped} 个", flush=True)
onnx.save(m, FIXED)

# ---------- 2) 版本回退补丁 ----------
import onnx2torch.node_converters.registry as R
import onnx2torch.converter as C

def make_patched(orig):
    def patched(operation_type, version, domain=""):
        try:
            return orig(operation_type=operation_type, version=version, domain=domain)
        except NotImplementedError:
            cands = [k for k in R._CONVERTER_REGISTRY
                     if k.operation_type == operation_type and k.domain == domain and k.version <= version]
            if not cands:
                raise
            best = max(cands, key=lambda k: k.version)
            print(f"   [回退] {operation_type} v{version} → v{best.version}", flush=True)
            return R._CONVERTER_REGISTRY[best]
    return patched

R.get_converter = make_patched(R.get_converter)
C.get_converter = R.get_converter

# ---------- 3) 补 Gelu 转换器 ----------
from onnx2torch.node_converters.registry import add_converter
from onnx2torch.utils.common import OnnxToTorchModule, OperationConverterResult, onnx_mapping_from_node

class OnnxGelu(torch.nn.Module, OnnxToTorchModule):
    def __init__(self, approximate: str = "none"):
        super().__init__()
        self.approximate = approximate

    def forward(self, x):
        return torch.nn.functional.gelu(x, approximate=self.approximate)

@add_converter(operation_type="Gelu", version=20)
def _(node, graph):  # pylint: disable=unused-argument
    return OperationConverterResult(
        torch_module=OnnxGelu(approximate=node.attributes.get("approximate", "none")),
        onnx_mapping=onnx_mapping_from_node(node=node),
    )

def shape_of(v):
    return [int(d.dim_value) for d in v.type.tensor_type.shape.dim]

specs = [(i.name, shape_of(i)) for i in m.graph.input]

# ---------- 4) ONNX → torch ----------
from onnx2torch import convert as onnx2torch_convert
t0 = time.time()
model = onnx2torch_convert(FIXED)
model.eval()

print(f"2) onnx2torch 转换完成（{time.time()-t0:.1f}s）", flush=True)

example = tuple(torch.randn(*s).half() for _, s in specs)   # 模型原生 fp16
with torch.no_grad():
    y = model(*example)
if not isinstance(y, (tuple, list)):
    y = (y,)
print("   前向通过，输出形状:", [tuple(t.shape) for t in y], flush=True)

# ---------- 5) trace + CoreML ----------
with torch.no_grad():
    traced = torch.jit.trace(model, example)
print("3) trace 完成", flush=True)

t0 = time.time()
ml = ct.convert(
    traced,
    inputs=[ct.TensorType(name=n, shape=s, dtype=np.float16) for n, s in specs],
    convert_to="mlprogram",
    compute_units=ct.ComputeUnit.ALL,
    compute_precision=ct.precision.FLOAT32,
    minimum_deployment_target=TARGET,
)
print(f"4) CoreML 转换完成（{time.time()-t0:.1f}s）", flush=True)

print("\n=== CoreML 输入 ===")
for n, d in ml.input_description.items():
    print(f"  {n:22s} {d.type} {getattr(d, 'shape', '')}")
print("=== CoreML 输出 ===")
for n, d in ml.output_description.items():
    print(f"  {n:22s} {d.type} {getattr(d, 'shape', '')}")

ml.save(OUT)
size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
print(f"\n已保存 {OUT}（{size/1e6:.1f} MB）", flush=True)
