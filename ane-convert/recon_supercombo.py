"""侦察 supercombo ONNX：输入/输出形状 + 算子清单（判断 ANE 可行性）。"""
import onnx
from collections import Counter

P = "/Users/lu/op项目of all/openpilot/openpilot/selfdrive/modeld/models/driving_supercombo.onnx"
m = onnx.load(P)
g = m.graph

print(f"IR 版本: {m.ir_version}   opset: {[(o.domain or 'ai.onnx', o.version) for o in m.opset_import]}")
print(f"节点数: {len(g.node)}   初始化器: {len(g.initializer)}   生产者: {m.producer_name} {m.producer_version}")

def shape_of(v):
    t = v.type.tensor_type
    return [d.dim_value if d.HasField('dim_value') else (d.dim_param or '?') for d in t.shape.dim]

print("\n=== 输入 ===")
for i in g.input:
    print(f"  {i.name:24s} {shape_of(i)}")

print("\n=== 输出 ===")
for o in g.output:
    print(f"  {o.name:24s} {shape_of(o)}")

print("\n=== 算子统计（按数量）===")
c = Counter(n.op_type for n in g.node)
for k, v in c.most_common():
    print(f"  {k:24s} {v}")

# ANE 友好度粗判：这些算子 CoreML/ANE 支持良好；列出"可能掉出 ANE"的
RISKY = {"LSTM", "GRU", "RNN", "Loop", "Scan", "NonMaxSuppression", "TopK", "Einsum",
         "GatherND", "ScatterND", "NonZero", "Where", "Range", "DynamicQuantizeLinear",
         "Mod", "Trilu", "GridSample", "Resize"}
risky = {k: v for k, v in c.items() if k in RISKY}
print("\n=== 可能影响 ANE 命中的算子 ===")
print("  无" if not risky else "\n".join(f"  {k}: {v}" for k, v in risky.items()))

# 动态形状检查（ANE 要求静态）
dyn = [i.name for i in list(g.input) + list(g.output) if any(not d.HasField('dim_value') for d in i.type.tensor_type.shape.dim)]
print("\n=== 动态维度 ===")
print("  无（全静态，ANE 友好）" if not dyn else f"  有: {dyn}")
