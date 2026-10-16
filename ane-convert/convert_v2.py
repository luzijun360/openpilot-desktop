"""supercombo ONNX → PyTorch → CoreML（v2 最终路线）。

模型特性（已实测确认）：权重全是 fp16，且图内带有显式 Cast 到 fp16 的节点
—— 它是按「fp16 权重 + 显式降精度点」设计的推理图。
coremltools 的常量/精度处理在这种图上会算出 fp32 权重，与 fp16 偏置冲突
（bias fp16 vs weight fp32），这是它的内部不一致，不是模型问题。

策略：把模型整体变成「纯 fp32 图」，再交给 coremltools 用它最成熟的标准路径
（compute_precision=FLOAT16）统一降到 fp16 —— 结果与 ANE 需要的精度一致。
  · 权重 fp16 → fp32（无损）
  · 图内 Cast(to=float16) → Identity（等价于把降精度点交给统一 pass 处理）
  · 清掉模型自带的陈旧类型声明（否则形状推断与 fp32 冲突）
"""
import os, time
import numpy as np
import onnx
from onnx import numpy_helper, helper, TensorProto
import torch
import coremltools as ct

SRC = "/Users/lu/op项目of all/openpilot/openpilot/selfdrive/modeld/models/driving_supercombo.onnx"
FIXED = "/Users/lu/op项目of all/ane-convert/supercombo_fp32graph.onnx"
OUT = "/Users/lu/op项目of all/ane-convert/driving_supercombo.mlpackage"

print("coremltools", ct.__version__, flush=True)
def pick_target():
    for name in ("macOS15", "macOS14", "macOS13"):
        t = getattr(ct.target, name, None)
        if t is not None:
            return name, t
    return "iOS18", getattr(ct.target, "iOS18", None)
tname, TARGET = pick_target()
print("目标平台:", tname, flush=True)

# ---------- 1) 预处理 ----------
m = onnx.load(SRC)

# 1a) 权重 fp16 → fp32
n_cast = 0
new_inits = []
for i in m.graph.initializer:
    arr = numpy_helper.to_array(i)
    if arr.dtype == np.float16:
        arr = arr.astype(np.float32); n_cast += 1
    new_inits.append(numpy_helper.from_array(arr, name=i.name))
del m.graph.initializer[:]
m.graph.initializer.extend(new_inits)

# 1b) 清掉陈旧类型声明
del m.graph.value_info[:]
n_io = 0
for coll in (m.graph.input, m.graph.output):
    for v in coll:
        if v.type.tensor_type.elem_type == TensorProto.FLOAT16:
            v.type.tensor_type.elem_type = TensorProto.FLOAT
            n_io += 1
# initializer 的 value_info 也要改
for v in m.graph.value_info:
    if v.type.tensor_type.elem_type == TensorProto.FLOAT16:
        v.type.tensor_type.elem_type = TensorProto.FLOAT

# 1c) 图内 Cast(to=float16) → Identity
n_id = 0
for n in m.graph.node:
    if n.op_type != "Cast":
        continue
    to = next((a.i for a in n.attribute if a.name == "to"), None)
    if to != TensorProto.FLOAT16:
        continue
    n.op_type = "Identity"
    del n.attribute[:]
    n_id += 1

# 1d) 形状推断（此时图已统一 fp32）
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
for n in m.graph.node:
    if n.op_type == "Reshape":
        az = next((a for a in n.attribute if a.name == "allowzero"), None)
        if az is None or az.i == 0:
            continue
        shp = n.input[1]
        if shp not in init:
            problems.append((n.name, "Reshape 形状非常量")); continue
        if 0 in init[shp].tolist():
            problems.append((n.name, "Reshape 形状含 0")); continue
        az.i = 0
        n_reshape += 1
    elif n.op_type in REDUCE_OPS and len(n.input) >= 2:
        axes_name = n.input[1]
        if axes_name not in init:
            problems.append((n.name, f"{n.op_type} axes 非常量")); continue
        axes = [int(a) for a in np.atleast_1d(init[axes_name])]
        r = rank.get(n.input[0])
        if not axes or r is None:
            problems.append((n.name, f"{n.op_type} axes 为空或秩未知")); continue
        axes = [a + r if a < 0 else a for a in axes]
        if any(a < 0 or a >= r for a in axes):
            problems.append((n.name, f"{n.op_type} axes 越界")); continue
        n.attribute.append(helper.make_attribute("axes", axes))
        del n.input[1]
        n_reduce += 1
if problems:
    for p in problems:
        print("  问题:", p, flush=True)
    raise SystemExit("中止")

used = {i for n in m.graph.node for i in n.input}
gi = {i.name for i in m.graph.input}
kept = [i for i in m.graph.initializer if i.name in used or i.name in gi]
dropped = len(m.graph.initializer) - len(kept)
del m.graph.initializer[:]
m.graph.initializer.extend(kept)

print(f"1) 预处理：权重 fp16→fp32 {n_cast} 个；Cast→Identity {n_id} 个；"
      f"I/O 声明改 fp32 {n_io} 个；Reshape 修正 {n_reshape}；Reduce axes 搬回属性 {n_reduce}；"
      f"清理权重 {dropped}", flush=True)
onnx.save(m, FIXED)

# ---------- 2) 版本回退补丁 + Gelu ----------
import onnx2torch.node_converters.registry as R
import onnx2torch.converter as C
def make_patched(orig):
    def patched(operation_type, version, domain=""):
        try:
            return orig(operation_type=operation_type, version=version, domain=domain)
        except NotImplementedError:
            c = [k for k in R._CONVERTER_REGISTRY
                 if k.operation_type == operation_type and k.domain == domain and k.version <= version]
            if not c:
                raise
            best = max(c, key=lambda k: k.version)
            print(f"   [回退] {operation_type} v{version} → v{best.version}", flush=True)
            return R._CONVERTER_REGISTRY[best]
    return patched
R.get_converter = make_patched(R.get_converter)
C.get_converter = R.get_converter

from onnx2torch.node_converters.registry import add_converter
from onnx2torch.utils.common import OnnxToTorchModule, OperationConverterResult, onnx_mapping_from_node

class OnnxGelu(torch.nn.Module, OnnxToTorchModule):
    def __init__(self, approximate="none"):
        super().__init__()
        self.approximate = approximate
    def forward(self, x):
        return torch.nn.functional.gelu(x, approximate=self.approximate)

@add_converter(operation_type="Gelu", version=20)
def _(node, graph):
    return OperationConverterResult(torch_module=OnnxGelu(node.attributes.get("approximate", "none")),
                                    onnx_mapping=onnx_mapping_from_node(node=node))

def shape_of(v):
    return [int(d.dim_value) for d in v.type.tensor_type.shape.dim]
specs = [(i.name, shape_of(i)) for i in m.graph.input]

# ---------- 3) ONNX → torch ----------
from onnx2torch import convert as onnx2torch_convert
t0 = time.time()
model = onnx2torch_convert(FIXED)
model.eval()
print(f"2) onnx2torch 转换完成（{time.time()-t0:.1f}s）", flush=True)

example = tuple(torch.randn(*s) for _, s in specs)
with torch.no_grad():
    y = model(*example)
if not isinstance(y, (tuple, list)):
    y = (y,)
print("   前向通过，输出形状:", [tuple(t.shape) for t in y], flush=True)

# ---------- 4) trace + CoreML ----------
with torch.no_grad():
    traced = torch.jit.trace(model, example)
print("3) trace 完成", flush=True)

t0 = time.time()
ml = ct.convert(
    traced,
    inputs=[ct.TensorType(name=n, shape=s) for n, s in specs],
    convert_to="mlprogram",
    compute_units=ct.ComputeUnit.ALL,
    compute_precision=ct.precision.FLOAT16,
    minimum_deployment_target=TARGET,
)
print(f"4) CoreML 转换完成（{time.time()-t0:.1f}s）", flush=True)

print("\n=== CoreML 输入/输出 ===")
_spec = ml.get_spec()
for _i in _spec.description.input:
    print(f"  输入 {_i.name:22s} {_i.type.WhichOneof('Type')}")
for _o in _spec.description.output:
    print(f"  输出 {_o.name:22s} {_o.type.WhichOneof('Type')}")

ml.save(OUT)
size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
print(f"\n已保存 {OUT}（{size/1e6:.1f} MB）", flush=True)


# ---------- 5) 数值保真：CoreML 输出 vs 源 torch 图输出 ----------
ml_cpu = ct.models.MLModel(OUT, compute_units=ct.ComputeUnit.CPU_ONLY)
ml_ne = ct.models.MLModel(OUT, compute_units=ct.ComputeUnit.CPU_AND_NE)
feed = {n: example[i].numpy() for i, (n, _) in enumerate(specs)}
out_ne = ml_ne.predict(feed)
if not isinstance(out_ne, dict):
    out_ne = {f"out{i}": v for i, v in enumerate(out_ne)}
refs = {tuple(t.shape): t.detach().numpy() for t in y}
print("\n=== 数值保真（CoreML(ANE) vs 源 torch 图）===")
worst = 0.0
for nm, o in out_ne.items():
    arr = np.asarray(o)
    r = refs.get(tuple(arr.shape))
    if r is None:
        print(f"  {nm:16s} 形状 {arr.shape} 无对应参考输出")
        continue
    d = np.abs(arr - r)
    denom = max(float(np.abs(r).max()), 1e-9)
    rel = d.max() / denom
    worst = max(worst, rel)
    print(f"  {nm:16s} 形状 {str(arr.shape):22s} 最大绝对误差 {d.max():.3e}  相对最大误差 {rel:.3e}  参考幅值 {denom:.3f}")
print(f"\n最差相对误差: {worst:.3e}  （fp16 预期量级 ~1e-3）")
