#!/usr/bin/env python3
# [三连跑 2026-09-30] 分析各轮记录：指纹帧数 / 幻影车签名 / 锁定统计
import json, sys

FP_LANE = [0.85, 0.96, 0.90, 0.22]   # 固定幻觉指纹（车道线概率）

def fp_lane(lp, atol=0.04):
    return len(lp) == 4 and all(abs(a - b) <= atol for a, b in zip(lp, FP_LANE))

for path in sys.argv[1:]:
    n = 0; fp = 0; leadzone = 0; cam = 0; phantom = 0
    maxlock = 0; cur = 0; prev = None
    leadmax = 0.0; leadmaxx = None
    leadval = {}  # 60-80m 区间的 leadProb 值分布
    try:
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if "laneProbs" in r:
                n += 1
                lp = r["laneProbs"]
                if fp_lane(lp):
                    fp += 1
                if lp == prev:
                    cur += 1
                    maxlock = max(maxlock, cur)
                else:
                    cur = 0
                prev = lp
                lprob = r.get("leadProb", 0.0) or 0.0
                lx = r.get("leadX")
                if lprob >= 0.4 and lx and 60 <= lx <= 80:
                    leadzone += 1
                    key = round(lprob, 2)
                    leadval[key] = leadval.get(key, 0) + 1
                # 幻影车签名：prob 0.50-0.58 且 x 68-71（固定值 0.536 @ 69.3 附近）
                if 0.50 <= lprob <= 0.58 and lx and 68 <= lx <= 71:
                    phantom += 1
                if lprob > leadmax:
                    leadmax = lprob; leadmaxx = lx
            elif "camSeq" in r:
                cam += 1
    except FileNotFoundError:
        print(f"{path}: 文件不存在")
        continue
    top = sorted(leadval.items(), key=lambda kv: -kv[1])[:3]
    print(f"── {path.split('/')[-1]}")
    print(f"   模型帧 {n} | 相机帧 {cam}")
    print(f"   指纹车道线帧 {fp} | 幻影车签名帧 {phantom} | 60-80m 高概率前车帧 {leadzone}")
    print(f"   最长连续相同输出 {maxlock} 帧")
    print(f"   最高前车概率 {leadmax:.3f} @ {leadmaxx}")
    if top:
        print(f"   前车值分布(top3): {top}")
