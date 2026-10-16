"""ANE 实测：加载 mlpackage，分别用 CPU / CPU+NE / ALL 跑，测单次推理耗时。"""
import time, numpy as np, coremltools as ct

P = "/Users/lu/op项目of all/ane-convert/driving_supercombo.mlpackage"
SHAPES = {
    "new_img": (2, 6, 128, 256),
    "desire": (8,),
    "traffic_convention": (1, 2),
    "action_t": (1, 2),
    "state_img_q": (2, 5, 6, 128, 256),
    "state_desire_q": (100, 1, 8),
    "state_feat_q": (96, 1, 512),
}

print("=== mlpackage 输入/输出 ===")
ml0 = ct.models.MLModel(P, compute_units=ct.ComputeUnit.CPU_ONLY)
spec = ml0.get_spec()
for i in spec.description.input:
    print(f"  输入 {i.name:22s} {i.type.WhichOneof('Type')}")
for o in spec.description.output:
    print(f"  输出 {o.name:22s} {o.type.WhichOneof('Type')}")

inp = {k: np.random.randn(*s).astype(np.float32) for k, s in SHAPES.items()}

print("\n=== 推理耗时（含首次编译预热）===")
results = {}
for name, units in (("仅 CPU", ct.ComputeUnit.CPU_ONLY),
                    ("CPU+神经引擎", ct.ComputeUnit.CPU_AND_NE),
                    ("全部(含GPU)", ct.ComputeUnit.ALL)):
    try:
        m = ct.models.MLModel(P, compute_units=units)
        t0 = time.time()
        out = m.predict(inp)
        warm = time.time() - t0
        t0 = time.time()
        N = 20
        for _ in range(N):
            out = m.predict(inp)
        dt = (time.time() - t0) / N
        results[name] = dt * 1000
        print(f"  {name:14s} 首次(含编译) {warm:6.2f}s   稳态 {dt*1000:7.2f} ms/次")
    except Exception as e:
        print(f"  {name:14s} 失败: {type(e).__name__} {str(e)[:120]}")

print("\n=== 输出形状 ===")
for k, v in out.items():
    print(f"  {k:22s} {getattr(v, 'shape', v)}")
if "仅 CPU" in results and "CPU+神经引擎" in results:
    r = results["仅 CPU"] / results["CPU+神经引擎"]
    print(f"\n神经引擎相对纯 CPU 的加速: {r:.2f}×")
