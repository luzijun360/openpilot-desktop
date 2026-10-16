"""打桩：捕获失败卷积节点的输入类型，定位 fp32 来源。"""
import numpy as np, torch, onnx
from onnx import numpy_helper, helper

# —— 复用预处理（从 convert_final 拷贝）——
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
def shape_of(v):
    return [int(d.dim_value) for d in v.type.tensor_type.shape.dim]
specs = [(i.name, shape_of(i)) for i in m.graph.input]
example = tuple(torch.randn(*s).half() for _, s in specs)
with torch.no_grad():
    traced = torch.jit.trace(model, example)

# —— 打桩：捕获失败卷积的输入类型 ——
import coremltools.converters.mil.frontend.torch.ops as T
_orig = T._convolution
fail_count = {"n": 0}

def patched(context, node):
    try:
        return _orig(context, node)
    except Exception as e:
        fail_count["n"] += 1
        if fail_count["n"] <= 3:
            print(f"\n### 失败节点 #{fail_count['n']}: name={node.name} kind={node.kind()}")
            for i, inp in enumerate(node.inputs()):
                t = inp.type()
                print(f"    输入{i}: {inp.debugName():40s} type={t}")
                if hasattr(inp, "target"):
                    try:
                        v = getattr(traced, inp.target)
                        print(f"          值: dtype={v.dtype} shape={tuple(v.shape)}")
                    except Exception:
                        pass
        raise

T._convolution = patched

import coremltools as ct
try:
    ct.convert(
        traced,
        inputs=[ct.TensorType(name=n, shape=s, dtype=np.float16) for n, s in specs],
        convert_to="mlprogram",
        compute_units=ct.ComputeUnit.ALL,
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=getattr(ct.target, "macOS15", None),
    )
except Exception as e:
    print("\n最终错误:", type(e).__name__, str(e)[:200])
