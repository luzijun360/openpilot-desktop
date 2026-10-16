#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[压力测试 2026-09-27] 把 测试素材/ 下全部素材连续跑一遍，全程记录性能与日志。

每轮：POST /api/import → 等栈就绪（出现模型数据）→ 每 2 秒采样（模型/相机帧率、系统负载、
内存、进程数、关键进程 CPU、车速、告警）→ 等「播放完毕」出现（定格）→ 归档该轮 op 日志 → 下一轮。

输出目录：/Users/lu/op项目of all/op方向的辅助驾驶方案/压力测试_<时间戳>/
  summary.md        人读报告（环境 + 逐轮表格 + 汇总）
  results.json      全部原始数据（每轮含每次采样）
  samples.csv       逐次采样明细（方便画曲线）
  logs/NN_*.log     每轮的 op 栈日志（完整）
  logs/console.log  控制台后端日志（完整）
  env.txt           测试环境
"""
import csv, json, os, re, shutil, subprocess, time, urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8899"
DEMO = "/Users/lu/op项目of all/openpilot/offline_demo"
MATS = "/Users/lu/op项目of all/op方向的辅助驾驶方案/测试素材"
TS = datetime.now().strftime("%Y%m%d_%H%M")
OUT = f"/Users/lu/op项目of all/op方向的辅助驾驶方案/压力测试_{TS}"
MGR = f"{DEMO}/logs/op_manager.log"


def http(path, body=None, timeout=15):
    try:
        if body is None:
            r = urllib.request.urlopen(BASE + path, timeout=timeout)
        else:
            req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def snapshot():
    """读 SSE 流的第一帧快照（逐行读——read(n) 会阻塞到填满缓冲区，行读才即时）"""
    try:
        r = urllib.request.urlopen(BASE + "/api/stream", timeout=6)
        t0 = time.time()
        while time.time() - t0 < 6:
            line = r.readline()
            if not line:
                break
            if line.startswith(b"data:"):
                r.close()
                return json.loads(line[5:].decode()).get("data", {})
        r.close()
    except Exception:
        pass
    return {}


def sysinfo():
    try:
        load = os.getloadavg()
    except Exception:
        load = (0, 0, 0)
    used = total = None
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        vals = {}
        for line in out.splitlines():
            m = re.match(r"(.+?):\s+(\d+)\.", line)
            if m:
                vals[m.group(1).strip()] = int(m.group(2))
        free = (vals.get("Pages free", 0) + vals.get("Pages inactive", 0)) * 16384
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"],
                                   capture_output=True, text=True).stdout.strip())
        used = total - free
    except Exception:
        pass
    return {"load1": round(load[0], 2), "load5": round(load[1], 2),
            "mem_used_gb": round(used / 1e9, 2) if used else None,
            "mem_total_gb": round(total / 1e9, 1) if total else None}


def proc_cpu():
    """关键进程 CPU%（op 栈用 python 跑，按命令行匹配模块名）"""
    out = {}
    try:
        ps = subprocess.run(["ps", "-Ao", "%cpu,command"], capture_output=True, text=True).stdout
        for line in ps.splitlines()[1:]:
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            cpu, cmd = parts
            for key in ("modeld", "camerad", "ui", "selfdrived", "controlsd"):
                if re.search(rf"[-_/ ]{key}\b", cmd) and "stress_test" not in cmd:
                    try:
                        out[key] = out.get(key, 0.0) + float(cpu)
                    except Exception:
                        pass
    except Exception:
        pass
    return {k: round(v, 1) for k, v in out.items()}


def video_info(path):
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        return {"fps": round(fps, 1), "frames": int(n), "w": w, "h": h,
                "dur": round(n / fps, 1) if fps else None}
    except Exception as e:
        return {"error": str(e)}


def eof_count():
    try:
        with open(MGR, "rb") as f:
            return f.read().count("播放完毕".encode())
    except Exception:
        return -1


def collect_materials():
    mats = []
    for group in sorted(os.listdir(MATS)):
        gp = os.path.join(MATS, group)
        if not os.path.isdir(gp):
            continue
        for fn in sorted(os.listdir(gp)):
            if fn.lower().endswith((".mov", ".mp4")):
                mats.append((group, fn, os.path.join(gp, fn)))
    return mats


def main():
    os.makedirs(f"{OUT}/logs", exist_ok=True)
    mats = collect_materials()
    env = {"start": datetime.now().isoformat(), "materials": len(mats), "out": OUT}
    for cmd in (["sw_vers"], ["sysctl", "-n", "hw.model"], ["sysctl", "-n", "hw.memsize"],
                ["sysctl", "-n", "hw.ncpu"], ["uptime"]):
        try:
            env[" ".join(cmd)] = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
        except Exception:
            pass
    try:
        env["app_version"] = open("/Users/lu/op项目of all/op方向的辅助驾驶方案/VERSION").read().strip().splitlines()[0]
    except Exception:
        pass
    with open(f"{OUT}/env.txt", "w") as f:
        for k, v in env.items():
            f.write(f"{k}: {v}\n")
    print(f"压力测试开始：{len(mats)} 个素材 → {OUT}", flush=True)

    results = {"env": env, "rounds": []}
    for i, (group, fn, path) in enumerate(mats, 1):
        r = {"n": i, "group": group, "name": fn, "path": path, "video": video_info(path),
             "t_import": time.time(), "samples": [], "errors": []}
        r["import_resp"] = http("/api/import", {"path": path})
        # 等就绪：模型数据出现
        t0 = time.time()
        ready = False
        while time.time() - t0 < 150:
            time.sleep(3)
            d = snapshot()
            if (d.get("modelV2") or {}).get("frameId") and (d.get("rates") or {}).get("model", 0) > 3:
                ready = True
                break
        r["t_ready"] = time.time()
        r["startup_s"] = round(r["t_ready"] - r["t_import"], 1)
        if not ready:
            r["errors"].append("启动超时（150 秒内没有模型数据）")
        # 播放基准：此刻日志已属于新栈（每次启动会截断日志）——在导入前取会拿到旧栈的计数
        base_eof = eof_count()
        # 采样直到「播放完毕」
        t_play = time.time()
        r["t_play"] = t_play
        done = False
        while time.time() - t_play < 200:
            time.sleep(2)
            d = snapshot()
            mv = d.get("modelV2") or {}
            cs = d.get("carState") or {}
            rt = d.get("rates") or {}
            vel = mv.get("velocity") or []
            st = http("/api/status", timeout=6)
            st = st if isinstance(st, dict) else {}
            pr = st.get("procs")
            s = {"t": round(time.time() - t_play, 1),
                 "modelHz": rt.get("model"), "cameraHz": rt.get("camera"),
                 "vEgo_kmh": round((cs.get("vEgo") or 0) * 3.6, 1),
                 "modelVel_ms": round(vel[0], 2) if vel else None,
                 "procs": (pr.get("count") if isinstance(pr, dict) else None)}
            s.update(sysinfo())
            s.update(proc_cpu())
            r["samples"].append(s)
            if eof_count() > base_eof:
                done = True
                break
        r["t_end"] = time.time()
        r["playback_s"] = round(r["t_end"] - r["t_play"], 1)
        r["eof_detected"] = done
        if not done:
            r["errors"].append("播放超时（200 秒未检测到播放完毕）")
        # 归档该轮 op 日志 + 提取告警
        try:
            shutil.copy(MGR, f"{OUT}/logs/{i:02d}_{group}_{fn}.log")
        except Exception as e:
            r["errors"].append(f"日志归档失败: {e}")
        try:
            txt = open(MGR, encoding="utf-8", errors="ignore").read()
            hits = sorted(set(re.findall(r"[^\n]{0,60}(?:Traceback|Exception|CRITICAL|ERROR|WARNING|Lagging|crash)[^\n]{0,60}", txt)))
            r["alerts"] = [h.strip() for h in hits][:25]
        except Exception:
            r["alerts"] = []
        results["rounds"].append(r)
        json.dump(results, open(f"{OUT}/results.json", "w"), ensure_ascii=False, indent=1)
        print(f"[{i}/{len(mats)}] {group}/{fn} 启动{r['startup_s']}s 播放{r['playback_s']}s "
              f"{'✓' if done else '✗'} {r['errors'] if r['errors'] else ''}", flush=True)

    # 收尾：全量采样 CSV + 控制台日志 + 报告
    with open(f"{OUT}/samples.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "group", "name", "t_s", "modelHz", "cameraHz", "vEgo_kmh", "modelVel_ms",
                    "load1", "load5", "mem_used_gb", "procs", "modeld_cpu", "camerad_cpu", "ui_cpu",
                    "controlsd_cpu", "selfdrived_cpu"])
        for r in results["rounds"]:
            for s in r["samples"]:
                w.writerow([r["n"], r["group"], r["name"], s["t"], s.get("modelHz"), s.get("cameraHz"),
                            s.get("vEgo_kmh"), s.get("modelVel_ms"), s.get("load1"), s.get("load5"),
                            s.get("mem_used_gb"), s.get("procs"), s.get("modeld"), s.get("camerad"),
                            s.get("ui"), s.get("controlsd"), s.get("selfdrived")])
    try:
        shutil.copy(f"{DEMO}/logs/console.log", f"{OUT}/logs/console.log")
    except Exception:
        pass
    write_summary(results)
    print(f"压力测试结束 → {OUT}/summary.md", flush=True)


def write_summary(results):
    rs = results["rounds"]
    ok = [r for r in rs if r["eof_detected"] and not r["errors"]]
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None
    lines = ["# 压力测试报告 — 全素材连续运行", "",
             f"- 开始：{results['env']['start']}",
             f"- 结束：{datetime.now().isoformat(timespec='seconds')}",
             f"- 素材：{len(rs)} 个｜正常完成：{len(ok)} 个｜异常：{len(rs) - len(ok)} 个", "",
             "## 测试环境", ""]
    for k, v in results["env"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 逐轮结果", "",
              "| # | 分组 | 素材 | 视频时长 | 启动(s) | 播放(s) | 模型Hz(均) | 相机Hz(均) | 负载1(均) | 负载1(峰) | 内存GB(峰) | 结果 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rs:
        mhz = avg([s.get("modelHz") for s in r["samples"]])
        chz = avg([s.get("cameraHz") for s in r["samples"]])
        l1 = avg([s.get("load1") for s in r["samples"]])
        l1max = max([s.get("load1") or 0 for s in r["samples"]] or [0])
        mmax = max([s.get("mem_used_gb") or 0 for s in r["samples"]] or [0])
        status = "✅" if (r["eof_detected"] and not r["errors"]) else ("⚠️ " + "；".join(r["errors"]))
        lines.append(f"| {r['n']} | {r['group']} | {r['name']} | {r['video'].get('dur')}s | "
                     f"{r['startup_s']} | {r['playback_s']} | {mhz} | {chz} | {l1} | {l1max} | {mmax} | {status} |")
    all_s = [s for r in rs for s in r["samples"]]
    lines += ["", "## 汇总", "",
              f"- 总耗时：{round((rs[-1]['t_end'] - rs[0]['t_import']) / 60, 1)} 分钟（含每轮全栈重启）",
              f"- 启动耗时：平均 {avg([r['startup_s'] for r in rs])} 秒，最慢 {max([r['startup_s'] for r in rs] or [0])} 秒",
              f"- 模型帧率：平均 {avg([s.get('modelHz') for s in all_s])} Hz，最低 {min([s.get('modelHz') for s in all_s if s.get('modelHz')] or [0])} Hz",
              f"- 相机帧率：平均 {avg([s.get('cameraHz') for s in all_s])} Hz",
              f"- 系统负载（1 分钟均值）：平均 {avg([s.get('load1') for s in all_s])}，峰值 {max([s.get('load1') or 0 for s in all_s] or [0])}（8 核）",
              f"- 内存占用：峰值 {max([s.get('mem_used_gb') or 0 for s in all_s] or [0])} GB / {all_s[0].get('mem_total_gb')} GB",
              f"- 告警/异常：{'无' if not any(r.get('alerts') for r in rs) else sum(1 for r in rs if r.get('alerts'))} 轮出现关键字（见各轮日志）",
              "", "> 说明：每轮都完整重启 op 全栈（等价于手动导入一次素材），因此启动耗时含模型加载。",
              "> 采样间隔 2 秒；全部原始数据见 results.json，逐次明细见 samples.csv，逐轮完整日志见 logs/。"]
    open(f"{OUT}/summary.md", "w").write("\n".join(lines))


if __name__ == "__main__":
    main()
