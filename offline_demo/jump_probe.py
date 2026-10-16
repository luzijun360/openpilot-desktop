#!/usr/bin/env python3
# [跳变追查 2026-09-29 v2] 黄金标准记录器：
# ① 作为 VIPC 客户端直连相机「窄路流」——抓模型真正收到的每一帧（相机去重/节流之后的实际序列）；
# ② SubMaster 订阅 modelV2——记录模型每帧输出（4 条车道线概率 + 前车 + 帧号 + 时间）。
# 跳变一出现：帧序列 + 模型输出逐帧对照，定位「哪种输入序列让模型跳到固定状态（4条线+假前车）」。
import os
import sys
import time
import json
import threading

import numpy as np
import cv2

sys.path.insert(0, "/Users/lu/op项目of all/openpilot")
import openpilot.cereal.messaging as messaging
from msgq.visionipc import VisionIpcClient
from openpilot.cereal.visionipc import VisionStreamType
from openpilot.system.camerad.cameras.nv12_info import get_nv12_info

DEMO = "/Users/lu/op项目of all/openpilot/offline_demo"
# [三连跑 2026-09-30] 输出路径可用环境变量覆盖（默认值不变，不影响老用法）
OUT = os.environ.get("JP_OUT") or f"{DEMO}/logs/jump_probe.jsonl"
FRAMES = os.environ.get("JP_FRAMES") or f"{DEMO}/logs/probe_frames"
os.makedirs(FRAMES, exist_ok=True)
_lock = threading.Lock()
_stop = threading.Event()


def log(rec):
    with _lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")


def vipc_thread():
    client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_NARROW_ROAD, True)
    shape = None
    seq = 0
    while not _stop.is_set():
        try:
            if not client.is_connected():
                if not client.connect(False):
                    time.sleep(0.5)
                    continue
                shape = get_nv12_info(client.width, client.height)
                log({"t": round(time.time(), 3), "vipc": "connected",
                     "w": client.width, "h": client.height})
            buf = client.recv(200)
            if buf is None:
                continue
            now = time.time()
            w, h = client.width, client.height
            stride, y_height, uv_height, _ = shape
            raw = np.frombuffer(buf.data, dtype=np.uint8)
            y = raw[:stride * y_height].reshape(y_height, stride)[:h, :w]
            uv = raw[stride * y_height:stride * y_height + stride * uv_height].reshape(uv_height, stride)[:h // 2, :w]
            bgr = cv2.cvtColor(np.vstack([y, uv]), cv2.COLOR_YUV2BGR_NV12)
            ok, jpg = cv2.imencode(".jpg", cv2.resize(bgr, (940, 590)), [cv2.IMWRITE_JPEG_QUALITY, 78])
            seq += 1
            if ok:
                fn = f"{FRAMES}/c_{seq:06d}_{int(now * 1000)}.jpg"
                with open(fn + ".tmp", "wb") as f:
                    f.write(jpg.tobytes())
                os.replace(fn + ".tmp", fn)
                fs = sorted(os.listdir(FRAMES))
                for f_ in fs[:-600]:
                    try:
                        os.remove(os.path.join(FRAMES, f_))
                    except Exception:
                        pass
            log({"t": round(now, 3), "camSeq": seq, "camFrame": getattr(buf, "frame_id", None)})
        except Exception as e:
            log({"t": round(time.time(), 3), "vipcErr": str(e)[:120]})
            time.sleep(0.5)


threading.Thread(target=vipc_thread, daemon=True).start()

sm = messaging.SubMaster(["modelV2", "carState"])
print(f"[probe2] 开始 → {OUT}", flush=True)
t0 = time.time()
last_beat = t0
while time.time() - t0 < 7200:
    sm.update(50)
    if sm.updated["modelV2"]:
        mv = sm["modelV2"]
        rec = {"t": round(time.time(), 3), "mvFrame": int(mv.frameId), "mvT": int(sm.logMonoTime["modelV2"])}
        try:
            rec["laneProbs"] = [round(float(mv.laneLineProbs[i]), 4) for i in range(len(mv.laneLineProbs))]
        except Exception:
            pass
        try:
            l = mv.leadsV3[0]
            rec["leadProb"] = round(float(l.prob), 4)
            rec["leadX"] = round(float(l.x[0]), 2) if len(l.x) else None
        except Exception:
            pass
        try:
            rec["vEgo"] = round(float(sm["carState"].vEgo), 2)
        except Exception:
            pass
        log(rec)
    if time.time() - last_beat > 60:
        log({"t": round(time.time(), 3), "beat": True})
        last_beat = time.time()
_stop.set()
print("[probe2] 结束", flush=True)
