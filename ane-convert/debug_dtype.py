"""调试：扫描 onnx2torch 转换后模型的 dtype 一致性，定位 fp32 权重的卷积。"""
import numpy as np, onnx, torch
from onnx import numpy_helper, helper

# —— 复用 convert_final 的预处理（简化版）——
SRC = "/Users/lu/op项目of all/openpilot/openpilot/selfdrive/modeld/models/driving_supercombo.onnx"
FIXED = "/Users/lu/op项目of all/ane-convert/supercombo_fixed.onnx"
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
for n in m.graph.node:
    if n.op_type == "Reshape":
        az = next((a for a in n.attribute if a.name == "allowzero"), None)
        if az is not None and az.i == 1 and n.input[1] in init and 0 not in init[n.input[1]].tolist():
            az.i = 0
    elif n.op_type in REDUCE_OPS and len(n.input) >= 2 and n.input[1] in init:
        axes = [int(a) for a in np.atleast_1d(init[n.input[1]])]
        r = rank.get(n.input[0])
        if axes and r:
            axes = [a + r if a < 0 else a for a in axes]
            n.attribute.append(helper.make_attribute("axes", axes))
            del n.input[1]
used = {i for n in m.graph.node for i in n.input}
gi = {i.name for i in m.graph.input}
kept = [i for i in m.graph.initializer if i.name in used or i.name in gi]
del m.graph.initializer[:]
m.graph.initializer.extend(kept)
onnx.save(m, FIXED)

# —— 版本回退补丁 + Gelu ——
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
            return R._CONVERTER_REGISTRY[max(c, key=lambda k: k.version)]
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

from onnx2torch import convert as onnx2torch_convert
model = onnx2torch_convert(FIXED)
model.eval()

print("=== 所有含 weight/bias 的模块 dtype ===")
bad = []
for name, mod in model.named_modules():
    w = getattr(mod, "weight", None)
    b = getattr(mod, "bias", None)
    if w is None and b is None:
        continue
    wd = str(w.dtype) if w is not None else "-"
    bd = str(b.dtype) if b is not None else "-"
    if w is not None and b is not None and wd != bd:
        bad.append((name, type(mod).__name__, wd, bd))
        print(f"  【不一致】{name:34s} {type(mod).__name__:20s} w={wd} b={bd}")

print(f"\n共 {sum(1 for _ in model.modules())} 个模块；weight/bias dtype 不一致的: {len(bad)} 个")

print("\n=== 各类 dtype 统计 ===")
from collections import Counter
c = Counter()
for name, mod in model.named_modules():
    w = getattr(mod, "weight", None)
    if w is not None:
        c[str(w.dtype)] += 1
print(dict(c))
