#!/usr/bin/env python3
"""openpilot 控制台后端：静态页面 + SSE 实时数据 + 控制 API（纯标准库，零依赖）

- GET  /                    控制台页面
- GET  /video               处理后的视频（支持 Range，供 <video> 播放）
- GET  /api/stream          SSE：10Hz 推送 modelV2 / carState / radarState 等快照
- GET  /api/materials       列出测试素材（4 组 × 8 速度档）
- GET  /api/status          进程/服务状态
- GET  /api/log?name=stack  读日志尾部
- POST /api/pick            弹原生文件选择框，返回路径
- POST /api/import {path}   免转码直接播放 + 重启全栈（等价于 .app 的流程）
- POST /api/stop            停止全栈
- POST /api/long {enabled}  开/关纵向控制（接管）
- POST /api/game_control {on} 开/关「op 开 slowroads」控制桥（虚拟手柄，不碰鼠标）
- POST /api/export/frame {png}  保存画面截图到桌面
- POST /api/export/data     保存当前模型数据 JSON 到桌面
"""
import base64
import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# [手机版 2026-09-29] 手机/iPad 版扩展：新增接口 + 远程登录守卫 + 路径前缀归一化。
# 加载失败不影响桌面版（只是手机版接口不可用），故用 try 包裹。
try:
  import console_mobile as _mobile
except Exception as _e:  # noqa: BLE001
  _mobile = None
  print(f"[mobile] 扩展加载失败，手机版不可用: {_e}", flush=True)

OP = "/Users/lu/op项目of all/openpilot"
DEMO = f"{OP}/offline_demo"
LOGS = f"{DEMO}/logs"
VIDEO = f"{DEMO}/test_1928x1208.mp4"
MATERIAL = "/Users/lu/op项目of all/op方向的辅助驾驶方案/测试素材"
LAUNCHER = f"{DEMO}/op_app_launcher.sh"
DESKTOP = os.path.expanduser("~/Desktop")
PORT = int(os.environ.get("OP_CONSOLE_PORT", "8899"))
OP_SCREEN = os.environ.get("OP_STREAM_PATH", f"{DEMO}/op_screen.jpg")   # op 原生 UI 帧流文件
DRIVER_SCREEN = f"{DEMO}/driver_cam.jpg"                               # 驾驶员摄像头帧（camerad cabin 流）
# [C1 补丁 2026-09-27] 播放控制 flag（camera.py 每 0.5 秒读一次）
PAUSE_FLAG = f"{DEMO}/pause.flag"
SPEED_FLAG = f"{DEMO}/speed.flag"
RESTART_FLAG = f"{DEMO}/restart.flag"
# [C2 补丁 2026-09-27] 网页点击转发文件（UI 进程每帧读一次）
CLICK_FILE = f"{DEMO}/ui_click.json"
# [推理后端设置 2026-09-28] 模型推理后端：coreml = Apple 神经引擎（默认）/ tinygrad = 原 Metal 路径
MODEL_BACKEND_FILE = f"{DEMO}/model_backend.txt"          # 控制台里选的（下次启动生效）
MODEL_BACKEND_RUNNING = f"{DEMO}/model_backend.running"   # modeld 启动时写下的（当前实际在跑哪个）
MODEL_BACKEND_DEFAULT = "coreml"
INFER_FPS_FILE = f"{DEMO}/infer_fps.txt"                   # [推理帧率设置 2026-09-29] 控制台里选的推理帧率（相机每帧读，立即生效）
INFER_FPS_DEFAULT = 10.0
# [AEB 音效 2026-09-28] AEB（碰撞预警 / 模型预测急刹）触发时播放 TSS 音效。
# 素材：测试素材/tss sound/3月15日.m4a（1.86 秒 AAC）；用 macOS 自带 afplay 播，不阻塞控制台。
AEB_SOUND = os.environ.get("AEB_SOUND", "/Users/lu/op项目of all/op方向的辅助驾驶方案/测试素材/tss sound/3月15日.m4a")
AEB_SOUND_GAP = 2.5      # 秒；AEB 抖动时不连响；持续 AEB 会变成「每隔 2.5 秒鸣响一次」
_AEB_PLAY = {"last": 0.0, "n": 0}

# [slowroads 自动驾驶开关 2026-09-29] op 开 slowroads 的控制桥（game_driver.py）：
# op 的 carControl → game_keys.json（虚拟手柄值）→ 游戏窗口推页面假手柄 → 游戏。全程不碰真实鼠标。
GAME_DRIVER = f"{DEMO}/game_driver.py"
GAME_DRIVER_LOG = f"{LOGS}/game_driver.log"
GAME_PY = f"{OP}/.venv/bin/python"
GAME_PID_FILE = f"{DEMO}/game_driver.pid"
_GAME_CACHE = {"t": 0.0, "running": False}

# [slowroads App 自动接入 + 恢复到主页 2026-09-30]
SLOWROADS_APP = f"{DEMO}/slowroads_app.json"          # slowroads App 心跳（打开时每 2 秒刷新）
SLOWROADS_CONNECT = f"{DEMO}/slowroads_connect.sh"    # 自动接入脚本
SLOWROADS_PREV = f"{DEMO}/slowroads_prev_video.txt"   # 接入前的画面源（断开时恢复）
HOME_FLAG = f"{DEMO}/home.flag"                       # 主页模式（桥接熄火 → op 显示主页）
HOME_FRAME = f"{DEMO}/home_frame.jpg"                 # 主页模式的静态帧源
LIVE_FRAME = f"{DEMO}/live_frame.jpg"                 # slowroads 实时帧源


def _play_aeb_sound() -> None:
  now = time.time()
  if now - _AEB_PLAY["last"] < AEB_SOUND_GAP:
    return
  _AEB_PLAY["last"] = now
  _AEB_PLAY["n"] += 1
  try:
    subprocess.Popen(["afplay", AEB_SOUND], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  except Exception as e:
    print(f"[aeb] 音效播放失败: {e}", flush=True)
# 驾驶员监测状态（由 _cabin_loop 更新，/api/stream 快照里以 driver 字段下发）
_DM = {"cam": False, "fps": 0.0, "face": None, "leftEye": None, "rightEye": None, "sleep": None,
       "phone": None, "distracted": None, "awareness": None, "alertLevel": None,
       "faceDetected": None, "distTypes": [], "ts": 0.0, "dmTs": 0.0, "error": ""}


def _placeholder_jpeg() -> bytes:
  """op 未运行时的占位图（避免网页出现破图）"""
  try:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1024, 512), (10, 13, 18))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1023, 511], outline=(38, 48, 62), width=2)
    font = None
    for fp in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Helvetica.ttc"):
      try:
        font = ImageFont.truetype(fp, 34)
        break
      except Exception:
        continue
    msg = "openpilot 未运行 —— 点右侧「导入视频」启动"
    try:
      d.text((60, 236), msg, fill=(122, 140, 162), font=font)
    except Exception:
      d.text((60, 236), "openpilot not running - click Import Video", fill=(122, 140, 162))
    import io
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72)
    return buf.getvalue()
  except Exception:
    return b""

def _current_source():
  """[重新校准 2026-09-29] 当前演示用的画面源：优先从跑着的 run_offline_demo.sh 命令行里取
  （实时画面模式 / 任意视频都能拿到），拿不到就退回 last_video.txt，再不行用默认视频。"""
  try:
    out = subprocess.run(["ps", "-Ao", "args"], capture_output=True, text=True).stdout
    for line in out.splitlines():
      if "run_offline_demo.sh" in line and "grep" not in line and "ps -Ao" not in line:
        parts = line.split()
        for i, t in enumerate(parts):
          if t.endswith("run_offline_demo.sh") and i + 1 < len(parts):
            cand = parts[i + 1]
            if os.path.exists(cand):
              return cand
  except Exception:
    pass
  try:
    with open(f"{DEMO}/last_video.txt") as f:
      p = f.read().strip()
      if p and os.path.exists(p):
        return p
  except Exception:
    pass
  return VIDEO


def _restart_stack(src):
  """[重新校准 2026-09-29] 用指定画面源重启整个演示栈（走启动器：先停旧实例再起新的）。
  [导入报错修复 2026-09-30] 加 cwd=DEMO：控制台后端若在目录被移动/重建过之后仍在运行，
  其工作目录会指向已删除的旧目录，子进程 bash 启动时会打印
  "chdir: error retrieving current directory: getcwd: ..."（导入其实成功，纯噪音报错）。"""
  subprocess.Popen(["/bin/bash", LAUNCHER, src, "auto"],
                   stdout=open(f"{LOGS}/launcher_app.log", "a"), stderr=subprocess.STDOUT,
                   cwd=DEMO, start_new_session=True)


def _game_driver_pids():
  """[slowroads 自动驾驶开关 2026-09-29] 正在跑的控制桥进程。
  用 pid 文件 + ps 校验——不用 pgrep 全表扫：命令行里恰好含「game_driver.py」字样的
  进程（比如测试脚本自己）会被误伤，实测 stop 曾把测试 shell 一起杀掉。"""
  pids = []
  try:
    with open(GAME_PID_FILE) as f:
      pid = int(f.read().strip())
    out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    if pid > 0 and "game_driver.py" in out:
      pids.append(pid)
  except Exception:
    pass
  if not pids:
    # 兜底：外部手动启动的（没有 pid 文件）——只认「命令行以 game_driver.py 结尾」的进程
    try:
      out = subprocess.run(["pgrep", "-f", "game_driver.py$"], capture_output=True, text=True).stdout
      pids = [int(x) for x in out.split() if x.isdigit()]
    except Exception:
      pids = []
  return pids


def _game_running():
  """带 2 秒缓存的控制桥状态（快照 10Hz 调用，别每次都 pgrep）。"""
  now = time.time()
  if now - _GAME_CACHE["t"] > 2.0:
    _GAME_CACHE["t"] = now
    _GAME_CACHE["running"] = len(_game_driver_pids()) > 0
  return _GAME_CACHE["running"]


def _start_game_driver():
  """启动控制桥。返回 (ok, msg)。"""
  if _game_driver_pids():
    return True, "已经在跑"
  try:
    lf = open(GAME_DRIVER_LOG, "ab")
    p = subprocess.Popen([GAME_PY, GAME_DRIVER], cwd=OP, stdout=lf, stderr=subprocess.STDOUT,
                         start_new_session=True)
    try:
      with open(GAME_PID_FILE, "w") as f:
        f.write(str(p.pid))
    except Exception:
      pass
    return True, "已启动"
  except Exception as e:
    return False, str(e)


def _stop_game_driver():
  """停控制桥 + 立刻把虚拟手柄归零（不靠 1 秒超时兜底）。"""
  for pid in _game_driver_pids():
    try:
      os.kill(pid, signal.SIGTERM)
    except Exception:
      pass
  try:
    os.remove(GAME_PID_FILE)
  except Exception:
    pass
  try:
    tmp = f"{DEMO}/game_keys.json.tmp"
    with open(tmp, "w") as f:
      json.dump({"pad": 1, "steer": 0.0, "throttle": 0.0, "brake": 0.0, "t": time.time()}, f)
    os.replace(tmp, f"{DEMO}/game_keys.json")
  except Exception:
    pass
  return True, "已停止"


SERVICES = ['modelV2', 'carState', 'selfdriveState', 'deviceState', 'managerState',
            'narrowRoadCameraState', 'radarState', 'carControl', 'longitudinalPlan',
            'carParams', 'onroadEvents', 'pandaStates',
            'extrinsicsCalibration']   # [重新校准 2026-09-29] 标定状态（calStatus/calPerc）

_LATEST = {"t": 0.0, "data": {"alive": False}}
_LOCK = threading.Lock()
_SM = None

# [帧率修复 2026-09-27] 真实帧率（frameId 差分 + 指数平滑）：原先前端按 SSE 推送率算 → 显示 ~5Hz 误导
_RATE = {"m": (None, None, 0.0, 0.0), "c": (None, None, 0.0, 0.0)}   # tag: (上次 frameId, 上次时间, 平滑 Hz, 上次帧号变化时间)


def _rate(tag, fid):
  now = time.time()
  last_fid, last_t, hz, last_change = _RATE[tag]
  if last_fid is not None and (now - last_t) >= 0.05 and fid >= last_fid:
    inst = (fid - last_fid) / (now - last_t)
    hz = inst if hz == 0.0 else (hz * 0.7 + inst * 0.3)
  if last_fid is None or fid != last_fid:
    last_change = now          # [画面冻结提示 2026-09-29] 记录帧号最后一次变化的时间
  _RATE[tag] = (fid, now, hz, last_change)
  return round(hz, 1)


def _video_info():
  try:
    import subprocess as sp
    out = sp.run(["ffmpeg", "-i", VIDEO], capture_output=True, text=True, timeout=10).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if m:
      dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
      return {"duration": dur, "fps": 20, "frames": int(round(dur * 20))}
  except Exception:
    pass
  return {"duration": 0, "fps": 20, "frames": 0}


def _arr(x, n=None):
  try:
    v = list(x)
    return v[:n] if n else v
  except Exception:
    return []


# [指示器 2026-09-28] 驾驶模式（LongitudinalPersonality 0/1/2 → aggressive/standard/relaxed，格数 1/2/3）
_PERS = {"t": 0.0, "idx": 0, "name": "aggressive", "bars": 1}
_PERS_MAP = {0: "aggressive", 1: "standard", 2: "relaxed"}


def _personality():
  """读 LongitudinalPersonality；2 秒缓存，避免每帧都去读参数文件。"""
  now = time.time()
  if now - _PERS["t"] < 2.0:
    return _PERS
  idx = 0
  try:
    from openpilot.common.params import Params
    idx = int(Params().get("LongitudinalPersonality", return_default=True) or 0)
  except Exception:
    pass
  idx = max(0, min(2, idx))
  _PERS.update(t=now, idx=idx, name=_PERS_MAP[idx], bars=idx + 1)
  return _PERS


def _snapshot():
  """从 msgq 抓一帧数据（用 openpilot 的库）"""
  global _SM
  import openpilot.cereal.messaging as messaging
  if _SM is None:
    _SM = messaging.SubMaster(SERVICES, ignore_alive=['managerState', 'onroadEvents', 'pandaStates'])
  _SM.update(0)
  seen = {k: bool(_SM.seen[k]) for k in SERVICES}
  alive = {k: bool(_SM.alive[k]) for k in SERVICES}
  out = {"seen": seen, "alive": alive}

  if seen.get('modelV2'):
    mv = _SM['modelV2']
    leads = []
    for i in range(min(3, len(mv.leadsV3))):     # capnp 列表不支持切片，用索引
      ld = mv.leadsV3[i]
      leads.append({"prob": float(ld.prob), "x": _arr(ld.x, 1), "y": _arr(ld.y, 1),
                    "v": _arr(ld.v, 1), "a": _arr(ld.a, 1)})
    out["modelV2"] = {
      "frameId": int(mv.frameId),
      "position": {"x": _arr(mv.position.x), "y": _arr(mv.position.y), "z": _arr(mv.position.z)},
      "laneLines": [{"x": _arr(ll.x), "y": _arr(ll.y), "z": _arr(ll.z),
                     "prob": float(mv.laneLineProbs[i]) if i < len(mv.laneLineProbs) else 1.0,
                     "std": float(mv.laneLineStds[i]) if i < len(mv.laneLineStds) else 0.0}
                    for i, ll in enumerate(mv.laneLines)],
      "roadEdges": [{"x": _arr(re_.x), "y": _arr(re_.y), "z": _arr(re_.z),
                     "prob": 1.0, "std": 0.0} for re_ in mv.roadEdges],
      "velocity": _arr(mv.velocity.x, 1),
      # [死行修复 2026-09-27] 车道线置信度（4 条线，实时变化）+ 每条线 std：供状态面板显示实时值
      "laneLineProbs": [float(p) for p in mv.laneLineProbs],
      "laneLineStds": [float(s) for s in mv.laneLineStds],
      "leadsV3": leads,
    }
  # [指示器 2026-09-28] TSS 风格简易指示器用的三个信号：前车 / 左右车道线置信度 / 驾驶模式
  ind = {"lead": False, "leadProb": 0.0, "leadDist": None, "laneL": 0.0, "laneR": 0.0,
         "mode": None, "bars": 0, "modeIdx": None, "aeb": False, "aebSrc": []}
  try:
    if seen.get('modelV2'):
      mv = _SM['modelV2']
      nl = min(3, len(mv.leadsV3))                       # capnp 列表不支持切片，用索引
      lp = [float(mv.leadsV3[i].prob) for i in range(nl)]
      ind["leadProb"] = round(max(lp), 3) if lp else 0.0
      probs = [float(p) for p in mv.laneLineProbs]
      # openpilot 约定：laneLines[1] = 左相邻车道线、laneLines[2] = 右相邻车道线
      ind["laneL"] = round(probs[1], 3) if len(probs) > 1 else 0.0
      ind["laneR"] = round(probs[2], 3) if len(probs) > 2 else 0.0
      if lp:
        try:
          ind["leadDist"] = round(float(mv.leadsV3[lp.index(max(lp))].x[0]), 1)
        except Exception:
          pass
    if seen.get('radarState'):
      l1 = _SM['radarState'].leadOne
      ind["radarLead"] = bool(l1.present)
      if bool(l1.present):
        ind["leadDist"] = round(float(l1.dRel), 1)
    # 前车判定：雷达认到 或 模型概率 > 0.5（op 采纳模型前车的标准）
    ind["lead"] = bool(ind.get("radarLead")) or ind["leadProb"] > 0.5
    # [AEB 指示 2026-09-28] 碰撞预警/紧急制动触发 → 指示器前车变红闪烁。
    # 这版 op 里 EventName.aeb 没有任何发送方（只在 events.py 里定义了警报样式），
    # 真正活着的信号有三个：
    #   ① longitudinalPlan.fcw —— op 纵向规划器的前向碰撞预警，就是驱动 op 界面「BRAKE!」的那条
    #   ② modelV2.meta.hardBrakePredicted —— 模型自己预测到要急刹
    #   ③ carState.stockAeb —— 原车 AEB（离线 demo 里恒为假，留作兼容）
    aeb_src = []
    if seen.get('longitudinalPlan') and bool(_SM['longitudinalPlan'].fcw):
      aeb_src.append("planner")
    if seen.get('modelV2') and bool(_SM['modelV2'].meta.hardBrakePredicted):
      aeb_src.append("model")
    if seen.get('carState') and bool(_SM['carState'].stockAeb):
      aeb_src.append("stock")
    ind["aeb"], ind["aebSrc"] = bool(aeb_src), aeb_src
    pers = _personality()
    ind["mode"], ind["bars"], ind["modeIdx"] = pers["name"], pers["bars"], pers["idx"]
  except Exception:
    pass
  out["indicator"] = ind
  if ind["aeb"]:
    _play_aeb_sound()        # [AEB 音效 2026-09-28] AEB 触发 → 响 TSS 提示音（2.5 秒内不重复）
  if seen.get('carState'):
    cs = _SM['carState']
    out["carState"] = {
      "vEgo": float(cs.vEgo), "vEgoRaw": float(cs.vEgoRaw), "aEgo": float(cs.aEgo),
      "steeringAngleDeg": float(cs.steeringAngleDeg), "steeringTorque": float(cs.steeringTorque),
      "gasPressed": bool(cs.gasPressed), "brakePressed": bool(cs.brakePressed),
      "standstill": bool(cs.standstill), "gearShifter": str(cs.gearShifter),
      "cruise": {"enabled": bool(cs.cruiseState.enabled), "available": bool(cs.cruiseState.available),
                 "speed": float(cs.cruiseState.speed)},
    }
  if seen.get('selfdriveState'):
    ss = _SM['selfdriveState']
    out["selfdriveState"] = {
      "enabled": bool(ss.enabled), "active": bool(ss.active), "engageable": bool(ss.engageable),
      "state": str(ss.state), "alertText1": str(ss.alertText1), "alertText2": str(ss.alertText2),
      "alertStatus": str(ss.alertStatus), "experimentalMode": bool(ss.experimentalMode),
    }
  if seen.get('radarState'):
    rs = _SM['radarState']
    def lead(l):
      # [B1 修复 2026-09-27] 改用 op 自己的采纳标志 present（radard 是否真的采用了这条前车），
      # 不再用 dRel/modelProb 猜；模型概率、是否雷达匹配一并给出，前端按 op 真实门槛 0.5 标注。
      return {"present": bool(l.present), "dRel": float(l.dRel), "yRel": float(l.yRel),
              "vRel": float(l.vRel), "vLead": float(l.vLead), "modelProb": float(l.modelProb),
              "radar": bool(l.radar), "aLeadK": float(l.aLeadK)}
    out["radarState"] = {"leadOne": lead(rs.leadOne), "leadTwo": lead(rs.leadTwo)}
  if seen.get('carControl'):
    cc = _SM['carControl']
    out["carControl"] = {"accel": float(cc.actuators.accel), "steeringAngleDeg": float(cc.actuators.steeringAngleDeg),
                         "curvature": float(cc.actuators.curvature),
                         "gas": float(cc.actuators.gas), "brake": float(cc.actuators.brake),
                         "enabled": bool(cc.enabled), "latActive": bool(cc.latActive), "longActive": bool(cc.longActive)}
  if seen.get('longitudinalPlan'):
    lp = _SM['longitudinalPlan']
    out["longitudinalPlan"] = {"accels": _arr(lp.accels, 5), "speeds": _arr(lp.speeds, 5),
                               "allowThrottle": bool(lp.allowThrottle), "hasLead": bool(lp.hasLead)}
  if seen.get('carParams'):
    cp = _SM['carParams']
    cpd: dict[str, object] = {"fingerprint": str(cp.carFingerprint), "radarUnavailable": bool(cp.radarUnavailable),
                              "openpilotLongitudinalControl": bool(cp.openpilotLongitudinalControl),
                              "alphaLongitudinalAvailable": bool(cp.alphaLongitudinalAvailable),
                              "pcmCruise": bool(cp.pcmCruise), "passive": bool(cp.passive),
                              "steerRatio": float(cp.steerRatio)}   # [方向盘组件] 转角→方向盘图标旋转用
    out["carParams"] = cpd
  if seen.get('narrowRoadCameraState'):
    nrs = _SM['narrowRoadCameraState']
    out["camera"] = {"frameId": int(nrs.frameId), "timestampSof": int(nrs.timestampSof)}
  # [帧率修复 2026-09-27] 真实帧率：相机用 frameId 差分（frameId 就是相机计数器）；
  # 模型 = 相机率 × (1-丢帧率)。注意 modelV2.frameId 是「相机帧号」不是模型计数，不能直接差分。
  rates = {}
  if seen.get('narrowRoadCameraState'):
    rates["camera"] = _rate("c", int(_SM['narrowRoadCameraState'].frameId))
    # [画面冻结提示 2026-09-29] 相机帧号 >2.5 秒没变 = 画面源冻结（游戏窗口被切到后台/暂停，或视频定格）。
    # 前端显示提示；帧号从未动过（栈没起）不提示。
    try:
      _lc = _RATE["c"][3]
      out["camStalled"] = bool(_lc > 0 and (time.time() - _lc) > 2.5)
    except Exception:
      out["camStalled"] = False
  if seen.get('modelV2') and rates.get("camera"):
    drop = float(_SM['modelV2'].frameDropPerc)
    rates["model"] = round(rates["camera"] * max(0.0, 1.0 - drop / 100.0), 1)
  out["rates"] = rates
  # [播完标记 2026-09-28] 相机定格后会写 ended.flag（定格后 frameId 仍按输出帧率增长，
  # 前端需要这个标记才能把「帧 N」换成「已播完」，否则看起来像视频还在播）
  try:
    out["video_ended"] = os.path.exists(os.path.join(DEMO, "ended.flag"))
  except Exception:
    out["video_ended"] = False
  if seen.get('deviceState'):
    ds = _SM['deviceState']
    out["deviceState"] = {"started": bool(ds.started), "thermalStatus": str(ds.thermalStatus)}
  if seen.get('pandaStates') and len(_SM['pandaStates']) > 0:
    ps = _SM['pandaStates'][0]
    out["panda"] = {"ignition": bool(ps.ignitionLine), "controlsAllowed": bool(ps.controlsAllowed),
                    "safetyModel": str(ps.safetyModel)}
  # [重新校准 2026-09-29] 标定状态：uncalibrated / calibrating / calibrated + 百分比
  if seen.get('extrinsicsCalibration'):
    ec = _SM['extrinsicsCalibration']
    try:
      out["calib"] = {"status": str(ec.calStatus), "perc": float(ec.calPerc), "validBlocks": int(ec.validBlocks)}
    except Exception:
      pass
  # [slowroads 自动驾驶开关 2026-09-29] 控制桥状态 + 当前推给游戏的手柄值
  try:
    gv = {}
    try:
      with open(f"{DEMO}/game_keys.json") as f:
        gv = json.load(f)
    except Exception:
      pass
    live = False
    try:
      with open(f"{DEMO}/last_video.txt") as f:
        live = f.read().strip().endswith("live_frame.jpg")
    except Exception:
      pass
    out["game"] = {"running": _game_running(),
                   "steer": round(float(gv.get("steer", 0.0)), 3),
                   "throttle": round(float(gv.get("throttle", 0.0)), 3),
                   "brake": round(float(gv.get("brake", 0.0)), 3),
                   "live": live}
  except Exception:
    pass
  # [slowroads App 自动接入 + 恢复到主页 2026-09-30] App 开关状态 + 是否已接入实时源 + 主页模式
  try:
    _sr_open = _slowroads_open()
    _live_src = False
    try:
      with open(f"{DEMO}/last_video.txt") as f:
        _live_src = f.read().strip().endswith("live_frame.jpg")
    except Exception:
      pass
    out["slowroads"] = {"open": _sr_open, "connected": bool(_sr_open and _live_src), "source_live": _live_src}
    out["home"] = _home_mode()
  except Exception:
    pass
  out["driver"] = dict(_DM)
  return out


def _cabin_loop():
  """[驾驶员监测] 从 op 的 cabin 流（camerad 发出的 Mac 前置摄像头画面）取帧 → JPEG 供网页显示，
  同时收集 op 原生 DM 模型（dmonitoringmodeld/dmonitoringd）的输出状态到 _DM。
  注意：不要自己用 cv2 抓摄像头——会和 camerad 抢设备把 webcamerad 挤死；只当 VIPC 的第二个客户端。"""
  import numpy as np
  import cv2
  import openpilot.cereal.messaging as messaging
  from msgq.visionipc import VisionIpcClient
  from openpilot.cereal.visionipc import VisionStreamType
  from openpilot.system.camerad.cameras.nv12_info import get_nv12_info

  client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_CABIN, True)
  sm = messaging.SubMaster(["driverStateV2", "driverMonitoringState"])
  tmp = DRIVER_SCREEN + ".tmp"
  shape = None
  fps_t, fps_n = time.time(), 0
  jpg_t = 0.0
  while True:
    try:
      if not client.is_connected():
        if not client.connect(False):
          _DM["cam"] = False
          _DM["error"] = "等待 camerad 的 cabin 流"
          time.sleep(0.5)
          continue
        shape = get_nv12_info(client.width, client.height)
      buf = client.recv(200)
      if buf is None:
        time.sleep(0.02)
        continue
      w, h = client.width, client.height
      # [降载] 画面编码限到 ~12fps：30fps 的 JPEG 编码在 8GB M1 上吃掉 20% CPU，
      # 会把 op 控制循环拖到报警（System Lagging）。DM 数据仍然每帧都读。
      now_jpg = time.time()
      if now_jpg - jpg_t >= 0.08:
        jpg_t = now_jpg
        stride, y_height, uv_height, _size = shape
        raw = np.frombuffer(buf.data, dtype=np.uint8)
        y = raw[:stride * y_height].reshape(y_height, stride)[:h, :w]
        uv = raw[stride * y_height:stride * y_height + stride * uv_height].reshape(uv_height, stride)[:h // 2, :w]
        bgr = cv2.cvtColor(np.vstack([y, uv]), cv2.COLOR_YUV2BGR_NV12)
        bgr = cv2.flip(bgr, 1)                       # 镜像，像照镜子
        ok, jpg = cv2.imencode(".jpg", cv2.resize(bgr, (960, 543)), [cv2.IMWRITE_JPEG_QUALITY, 78])
        if ok:
          with open(tmp, "wb") as f:
            f.write(jpg.tobytes())
          os.replace(tmp, DRIVER_SCREEN)
      fps_n += 1
      now = time.time()
      if now - fps_t >= 1.0:
        _DM["fps"] = round(fps_n / (now - fps_t), 1)
        fps_t, fps_n = now, 0
      _DM["cam"] = True
      _DM["ts"] = now
      _DM["error"] = ""
      sm.update(0)
      if sm.updated["driverStateV2"]:
        d = sm["driverStateV2"].leftDriverData
        _DM.update(face=round(float(d.faceProb), 2), leftEye=round(float(d.leftEyeProb), 2),
                   rightEye=round(float(d.rightEyeProb), 2), sleep=round(float(d.sleepProb), 2),
                   phone=round(float(d.phoneProb), 2), dmTs=time.time())
      if sm.updated["driverMonitoringState"]:
        dm = sm["driverMonitoringState"]
        v = dm.visionPolicyState
        try:
          alert_level = int(dm.alertLevel)
        except Exception:
          alert_level = 0
        _DM.update(distracted=bool(v.isDistracted),
                   awareness=float(v.awarenessPercent),
                   alertLevel=alert_level,
                   faceDetected=bool(v.faceDetected),
                   distTypes=[n for n, on in (('姿态', v.distractedTypes.pose), ('眼睛', v.distractedTypes.eye),
                                              ('手机', v.distractedTypes.phone), ('睡意', v.distractedTypes.sleep)) if on])
    except Exception as e:
      _DM["error"] = str(e)[:80]
      time.sleep(0.5)


def _collector():
  while True:
    try:
      data = _snapshot()
      try:
        with open(f"{DEMO}/long_control.flag") as f:
          data["demoLong"] = f.read().strip() != "0"
      except Exception:
        data["demoLong"] = True
      # [性能提示开关] 默认关闭（离线 demo 中 System Lagging 是误报）
      try:
        with open(f"{DEMO}/perf_alert.flag") as f:
          data["perfAlert"] = f.read().strip() != "0"
      except Exception:
        data["perfAlert"] = False
      # [C1 补丁 2026-09-27] 播放控制状态（暂停/倍速）+ 系统负载
      pb = {"pause": False, "speed": 1.0}
      try:
        with open(PAUSE_FLAG) as f:
          pb["pause"] = f.read().strip() == "1"
      except Exception:
        pass
      try:
        with open(SPEED_FLAG) as f:
          pb["speed"] = float(f.read().strip() or "1")
      except Exception:
        pass
      data["playback"] = pb
      # [推理后端设置 2026-09-28] setting = 控制台里选的（下次启动生效）；running = 当前实际在跑的
      mb = {"setting": MODEL_BACKEND_DEFAULT, "running": None}
      try:
        with open(MODEL_BACKEND_FILE) as f:
          v = f.read().strip()
          if v:
            mb["setting"] = v
      except Exception:
        pass
      try:
        with open(MODEL_BACKEND_RUNNING) as f:
          mb["running"] = f.read().strip() or None
      except Exception:
        pass
      data["modelBackend"] = mb
      # [推理帧率设置 2026-09-29] 推理帧率：setting = 控制台选的；model/camera = 实际率
      fpsv = {"setting": INFER_FPS_DEFAULT, "model": None, "camera": None}
      try:
        with open(INFER_FPS_FILE) as f:
          v = float(f.read().strip())
          if 1.0 <= v <= 60.0:
            fpsv["setting"] = v
      except Exception:
        pass
      _r = data.get("rates") or {}
      fpsv["model"] = _r.get("model")
      fpsv["camera"] = _r.get("camera")
      data["inferFps"] = fpsv
      data["sys"] = _sysinfo()
      with _LOCK:
        _LATEST["t"] = time.time()
        _LATEST["data"] = data
    except Exception as e:
      with _LOCK:
        _LATEST["data"] = {"error": str(e)}
    time.sleep(0.1)


_SYS_CACHE = {"t": 0.0, "d": {}}


def _sysinfo():
  """[C1 补丁 2026-09-27] 系统负载（负载均值 + 内存占用），最多 2 秒算一次。"""
  now = time.time()
  if now - _SYS_CACHE["t"] < 2.0 and _SYS_CACHE["d"]:
    return _SYS_CACHE["d"]
  d = {"load1": 0.0, "load5": 0.0, "ncpu": os.cpu_count() or 0, "mem_used_gb": 0.0, "mem_total_gb": 0.0}
  try:
    la = os.getloadavg()
    d["load1"], d["load5"] = round(la[0], 2), round(la[1], 2)
  except Exception:
    pass
  try:
    out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3).stdout.strip()
    total = int(out)
    vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3).stdout
    pages = {}
    for line in vm.splitlines():
      m = re.match(r"([^:]+):\s+(\d+)", line)
      if m:
        pages[m.group(1).strip()] = int(m.group(2))
    page_size = 16384  # Apple Silicon
    used = (pages.get("Pages active", 0) + pages.get("Pages wired down", 0) +
            pages.get("Pages occupied by compressor", 0)) * page_size
    d["mem_total_gb"] = round(total / 1e9, 1)
    d["mem_used_gb"] = round(used / 1e9, 1)
  except Exception:
    pass
  _SYS_CACHE["t"], _SYS_CACHE["d"] = now, d
  return d


def _slowroads_open():
  """[slowroads App 2026-09-30] App 开没开：心跳文件新鲜（<6 秒）+ pid 还活着。"""
  try:
    with open(SLOWROADS_APP) as f:
      d = json.load(f)
    if time.time() - float(d.get("t", 0)) > 6.0:
      return False
    pid = int(d.get("pid", 0))
    if pid <= 0:
      return False
    os.kill(pid, 0)
    return True
  except Exception:
    return False


def _home_mode():
  """[恢复到主页 2026-09-30] 主页模式标志（桥接熄火中）。"""
  try:
    with open(HOME_FLAG) as f:
      return f.read().strip() == "1"
  except Exception:
    return False


def _procs():
  try:
    out = subprocess.run(["pgrep", "-fl", "manager.py|openpilot\\.|fake_car_bridge"],
                         capture_output=True, text=True, timeout=5).stdout
    lines = [l.strip() for l in out.strip().splitlines() if l.strip()]
    names = {}
    for l in lines:
      m = re.match(r"\d+\s+(\S+)", l)
      if m:
        n = m.group(1).split('.')[-1]
        names[n] = names.get(n, 0) + 1
    return {"count": len(lines), "names": names, "running": len(lines) > 0}
  except Exception:
    return {"count": 0, "names": {}, "running": False}


class Handler(BaseHTTPRequestHandler):
  def log_message(self, *a):
    pass

  def _send(self, code, body, ctype="application/json; charset=utf-8"):
    if isinstance(body, (dict, list)):
      body = json.dumps(body, ensure_ascii=False).encode()
    elif isinstance(body, str):
      body = body.encode()
    self.send_response(code)
    self.send_header("Content-Type", ctype)
    self.send_header("Content-Length", str(len(body)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(body)

  def _body(self):
    n = int(self.headers.get("Content-Length") or 0)
    if n == 0:
      return {}
    try:
      return json.loads(self.rfile.read(n) or b"{}")
    except Exception:
      return {}

  # ---------- GET ----------
  def do_GET(self):
    u = urllib.parse.urlparse(self.path)
    p, q = u.path, urllib.parse.parse_qs(u.query)

    # [手机版 2026-09-29] 前缀归一化 + 远程登录守卫 + 手机版接口（本机直连行为不变）
    if _mobile is not None:
      p = _mobile.resolve(self, p)
      if not _mobile.guard(self, p):
        return
      if _mobile.handle_get(self, p, q):
        return

    if p in ("/", "/index.html"):
      return self._file(f"{DEMO}/console.html", "text/html; charset=utf-8")
    if p == "/video":
      return self._video()
    if p == "/api/stream":
      return self._sse()
    if p == "/api/materials":
      return self._send(200, self._materials())
    if p == "/api/status":
      with _LOCK:
        d = dict(_LATEST["data"])
      return self._send(200, {"procs": _procs(), "video": _video_info(), "data_alive": d.get("seen") is not None,
                              "last_snapshot": _LATEST["t"]})
    if p == "/api/log":
      name = (q.get("name") or ["stack"])[0]
      fn = {"stack": "stack.log", "manager": "op_manager.log", "launcher": "launcher.log",
            "bridge": "op_fake_car.log"}.get(name, "stack.log")
      path = f"{LOGS}/{fn}"
      try:
        with open(path, "rb") as f:
          f.seek(0, 2)
          size = f.tell()
          f.seek(max(0, size - 20000))
          txt = f.read().decode("utf-8", "replace")
        return self._send(200, {"name": name, "text": txt})
      except Exception as e:
        return self._send(200, {"name": name, "text": f"(无法读取 {path}: {e})"})
    if p == "/api/opscreen.jpg":
      return self._opscreen_jpeg()
    if p == "/api/opstream":
      return self._opstream()
    if p == "/api/gamestream":
      # [slowroads App 自动接入 2026-09-30] 游戏实时画面流（live_frame.jpg → MJPEG；只读不转发点击）
      return self._mjpeg(LIVE_FRAME)
    if p == "/api/driverstream":
      return self._driverstream()
    if p.startswith("/static/"):
      fn = p[len("/static/"):]
      if ".." in fn:
        return self._send(403, {"error": "no"})
      return self._file(f"{DEMO}/{fn}")
    return self._send(404, {"error": "not found"})

  def _file(self, path, ctype=None):
    try:
      with open(path, "rb") as f:
        b = f.read()
    except Exception as e:
      return self._send(404, {"error": f"{path}: {e}"})
    if ctype is None:
      ctype = "text/plain; charset=utf-8"
      if path.endswith(".html"):
        ctype = "text/html; charset=utf-8"
      elif path.endswith(".js"):
        ctype = "application/javascript"
      elif path.endswith(".css"):
        ctype = "text/css"
    return self._send(200, b, ctype)

  def _video(self):
    if not os.path.exists(VIDEO):
      return self._send(404, {"error": "no video"})
    size = os.path.getsize(VIDEO)
    rng = self.headers.get("Range")
    start, end = 0, size - 1
    code = 200
    if rng:
      m = re.match(r"bytes=(\d*)-(\d*)", rng)
      if m:
        if m.group(1):
          start = int(m.group(1))
        if m.group(2):
          end = int(m.group(2))
        code = 206
    length = end - start + 1
    self.send_response(code)
    self.send_header("Content-Type", "video/mp4")
    self.send_header("Accept-Ranges", "bytes")
    self.send_header("Content-Length", str(length))
    if code == 206:
      self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    self.end_headers()
    with open(VIDEO, "rb") as f:
      f.seek(start)
      remaining = length
      while remaining > 0:
        chunk = f.read(min(262144, remaining))
        if not chunk:
          break
        try:
          self.wfile.write(chunk)
        except Exception:
          return
        remaining -= len(chunk)

  # ---------- op 原生 UI 画面 ----------
  def _op_jpeg(self) -> bytes:
    """最新一帧 op UI 画面；过旧或缺失时返回占位图"""
    try:
      st = os.stat(OP_SCREEN)
      if time.time() - st.st_mtime < 6.0:
        with open(OP_SCREEN, "rb") as f:
          return f.read()
    except Exception:
      pass
    return _placeholder_jpeg()

  def _opscreen_jpeg(self):
    data = self._op_jpeg()
    self.send_response(200)
    self.send_header("Content-Type", "image/jpeg")
    self.send_header("Content-Length", str(len(data)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(data)

  def _mjpeg(self, path):
    """MJPEG 流：文件一变就推一帧（浏览器 <img> 直接显示）"""
    self.send_response(200)
    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    last = None
    try:
      while True:
        try:
          st = os.stat(path)
          sig = (st.st_mtime_ns, st.st_size)
        except Exception:
          sig = None
        if sig != last:
          last = sig
          try:
            with open(path, "rb") as f:
              data = f.read()
          except Exception:
            data = _placeholder_jpeg()
          self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n")
          self.wfile.flush()
        time.sleep(0.05)
    except Exception:
      return

  def _opstream(self):
    return self._mjpeg(OP_SCREEN)

  def _driverstream(self):
    return self._mjpeg(DRIVER_SCREEN)

  def _sse(self):
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
    self.send_header("Cache-Control", "no-store")
    self.send_header("Connection", "keep-alive")
    self.end_headers()
    try:
      while True:
        with _LOCK:
          payload = {"t": time.time(), "procs": _procs(), "data": _LATEST["data"]}
        self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()
        time.sleep(0.15)
    except Exception:
      return

  def _materials(self):
    groups = []
    try:
      for g in sorted(os.listdir(MATERIAL)):
        gp = os.path.join(MATERIAL, g)
        if os.path.isdir(gp):
          files = sorted([f for f in os.listdir(gp) if f.lower().endswith((".mov", ".mp4", ".mkv", ".avi", ".webm"))],
                         key=lambda s: int(re.match(r"(\d+)", s).group(1)) if re.match(r"(\d+)", s) else 999)
          groups.append({"group": g, "files": [{"name": f, "path": os.path.join(gp, f)} for f in files]})
    except Exception as e:
      return {"groups": [], "error": str(e)}
    return {"groups": groups, "current": VIDEO, "video": _video_info()}

  # ---------- POST ----------
  def do_POST(self):
    p = urllib.parse.urlparse(self.path).path
    # [手机版 2026-09-29] 必须在 _body() 之前：上传接口要独占请求体（裸字节流式写盘）
    if _mobile is not None:
      _mq = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
      p = _mobile.resolve(self, p)
      if not _mobile.guard(self, p):
        return
      if _mobile.handle_post(self, p, _mq):
        return
    body = self._body()

    if p == "/api/pick":
      try:
        out = subprocess.run(["osascript", "-e",
                              f'POSIX path of (choose file with prompt "选择行车视频" default location POSIX file "{MATERIAL}")'],
                             capture_output=True, text=True, timeout=180)
        path = out.stdout.strip()
        return self._send(200, {"path": path, "ok": bool(path)})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/import":
      path = body.get("path") or ""
      if not os.path.exists(path):
        return self._send(200, {"ok": False, "error": f"文件不存在: {path}"})
      # [统一入口 2026-09-27] 只走启动器脚本：「openpilot 视频测试.app」已删除（只保留控制台一个 app）。
      # 控制台后端跑在 .app 的 GUI 会话里，脚本 spawn 的全栈能正常创建窗口。
      # 免转码：任意分辨率视频直接播（camera.py 播放时实时对齐），导入秒开。
      subprocess.Popen(["/bin/bash", LAUNCHER, path, "auto"],
                       stdout=open(f"{LOGS}/launcher_app.log", "a"), stderr=subprocess.STDOUT,
                       cwd=DEMO, start_new_session=True)
      return self._send(200, {"ok": True, "msg": f"已开始启动: {os.path.basename(path)}"})

    if p == "/api/stop":
      subprocess.Popen(["/bin/bash", LAUNCHER, "__STOP__", "stop-only"],
                       stdout=open(f"{LOGS}/launcher_app.log", "a"), stderr=subprocess.STDOUT,
                       cwd=DEMO, start_new_session=True)
      return self._send(200, {"ok": True, "msg": "正在停止全栈…"})

    if p == "/api/long":
      try:
        enabled = bool(body.get("enabled", True))
        with open(f"{DEMO}/long_control.flag", "w") as f:
          f.write("1" if enabled else "0")
        return self._send(200, {"ok": True, "enabled": enabled})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/perf_alert":
      # [性能提示开关] op 的「TAKE CONTROL / System Lagging」报警：离线 demo 里没有真车，
      # 它是误报。写 flag 文件，selfdrived 每次循环读取（内容非 "0" = 显示提示并响铃）；默认关闭。
      try:
        enabled = bool(body.get("enabled", False))
        with open(f"{DEMO}/perf_alert.flag", "w") as f:
          f.write("1" if enabled else "0")
        return self._send(200, {"ok": True, "enabled": enabled})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/recalibrate":
      # [重新校准 2026-09-29] 清掉 run_offline_demo.sh 预置的「假有效标定」+ 重启整个演示栈。
      # 为什么必须重启：calibrationd 只在启动时读 CalibrationParams（calibrationd.py:72），
      # 而且它是 op manager 管的 only_onroad 进程，单独 pkill 不一定被拉起来（实测没拉起）。
      # 重启后 op 从零开始真校准：只在车速 >24km/h(15mph)、直线、低偏航时才采校准块
      # （calibrationd.py:24 MIN_SPEED_FILTER = 15mph = 24.1km/h），所以放 30km/h 以上素材才会收敛。
      # 校准期间画面会先歪，收敛后回正。恢复：用「恢复预置标定」按钮。
      try:
        from openpilot.common.params import Params
        # 写持久标志：run_offline_demo.sh 启动时会看到它，从而不预置假标定（否则重启就被覆盖）
        with open(f"{DEMO}/recalib.flag", "w") as f:
          f.write(str(time.time()))
        Params().remove("CalibrationParams")
        src = _current_source()
        _restart_stack(src)
        return self._send(200, {"ok": True, "msg": f"已清除标定，正在重启演示（{os.path.basename(src)}）→ op 将重新校准"})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/restore_calib":
      # [重新校准 2026-09-29] 恢复预置的有效标定（等价于 run_offline_demo.sh 启动时的 set_params_enabled）
      # + 重启演示栈，让 op 立刻回到「已校准」状态。
      try:
        import openpilot.cereal.messaging as messaging
        from openpilot.common.params import Params
        msg = messaging.new_message('extrinsicsCalibration')
        msg.extrinsicsCalibration.validBlocks = 20
        msg.extrinsicsCalibration.rpyCalib = [0.0, 0.0, 0.0]
        Params().put("CalibrationParams", msg.to_bytes(), block=True)
        try:
          os.remove(f"{DEMO}/recalib.flag")   # 清掉持久标志 → 以后启动都恢复预置标定
        except FileNotFoundError:
          pass
        src = _current_source()
        _restart_stack(src)
        return self._send(200, {"ok": True, "msg": f"已恢复预置标定，正在重启演示（{os.path.basename(src)}）"})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/game_control":
      # [slowroads 自动驾驶开关 2026-09-29] 开/关「op 开 slowroads」控制桥。
      # 开 = 启动 game_driver.py（op 的 carControl → 虚拟手柄 → 游戏）；关 = 杀掉 + 手柄归零。
      try:
        on = bool(body.get("on", True))
        if on:
          src = _current_source()
          if os.path.basename(src or "") != "live_frame.jpg":
            return self._send(200, {"ok": False, "error": f"画面源不是 slowroads 实时画面（当前：{os.path.basename(src or '未知')}），先切到 slowroads 再开"})
          # [恢复到主页 2026-09-30] 开自动驾驶 = 离开主页模式（op 要点火才能开车）
          try:
            os.remove(HOME_FLAG)
          except FileNotFoundError:
            pass
          if subprocess.run(["pgrep", "-f", "[m]anager.py"], capture_output=True, text=True).stdout.strip() == "":
            return self._send(200, {"ok": False, "error": "op 演示栈没在运行"})
          ok, msg = _start_game_driver()
        else:
          ok, msg = _stop_game_driver()
        _GAME_CACHE["t"] = 0.0     # 立刻刷新状态（不等 2 秒缓存）
        return self._send(200, {"ok": ok, "running": _game_running(), "msg": msg})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/home":
      # [恢复到主页 2026-09-30] 切出 + 停止当前推理 + 回 op 主页：
      # 暂停当前源（camera 保持当前帧、模型停推理）+ 写 home.flag（桥接熄火 → op offroad → 渲染主页）。
      # 栈没在跑 → 直接起「主页模式」栈（控制台空闲态）。
      try:
        _stop_game_driver()
        def _w(path, text):
          tmp = path + ".tmp"
          with open(tmp, "w") as f:
            f.write(text)
          os.replace(tmp, path)
        _w(PAUSE_FLAG, "1")
        _w(HOME_FLAG, "1")
        if not _procs().get("running"):
          subprocess.Popen(["/bin/bash", LAUNCHER, "__HOME__", "auto"],
                           stdout=open(f"{LOGS}/launcher_app.log", "a"), stderr=subprocess.STDOUT,
                           cwd=DEMO, start_new_session=True)
          msg = "栈没在跑 → 正在启动主页模式（约 40 秒）"
        else:
          msg = "已回主页（推理已停）"
        return self._send(200, {"ok": True, "msg": msg})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/slowroads_reconnect":
      # [slowroads App 自动接入 2026-09-30] 重新接入（幂等；slowroads_connect.sh 自带并发锁）
      try:
        if not os.path.exists(SLOWROADS_CONNECT):
          return self._send(200, {"ok": False, "error": "接入脚本缺失"})
        subprocess.Popen(["/bin/bash", SLOWROADS_CONNECT],
                         stdout=open(f"{LOGS}/slowroads_connect.log", "a"), stderr=subprocess.STDOUT,
                         cwd=DEMO, start_new_session=True)
        return self._send(200, {"ok": True, "msg": "正在接入 slowroads（约 1 分钟）"})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/model_backend":
      # [推理后端设置 2026-09-28] 写设置文件；栈正在跑就用最后播放的视频自动重启（约 40 秒）让它立即生效。
      # 不自动重启的话用户会以为没生效（旧栈还跑着旧后端）。
      try:
        backend = str(body.get("backend") or "").strip()
        if backend not in ("coreml", "tinygrad"):
          return self._send(200, {"ok": False, "error": f"未知后端: {backend}"})
        with open(MODEL_BACKEND_FILE, "w") as f:
          f.write(backend)
        restarted = False
        if _procs().get("running"):
          try:
            with open(f"{DEMO}/last_video.txt") as f:
              vid = f.read().strip()
          except Exception:
            vid = ""
          if vid and os.path.exists(vid):
            subprocess.Popen(["/bin/bash", LAUNCHER, vid, "auto"],
                             stdout=open(f"{LOGS}/launcher_app.log", "a"), stderr=subprocess.STDOUT,
                             cwd=DEMO, start_new_session=True)
            restarted = True
        return self._send(200, {"ok": True, "backend": backend, "restarted": restarted})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/infer_fps":
      # [推理帧率设置 2026-09-29] 写 infer_fps.txt；相机每帧重读 → 立即生效，不用重启。
      try:
        fps = float(body.get("fps") or 0)
        if not (1.0 <= fps <= 60.0):
          return self._send(200, {"ok": False, "error": f"帧率超出范围: {body.get('fps')!r}"})
        with open(INFER_FPS_FILE, "w") as f:
          f.write(str(int(fps)) if float(fps).is_integer() else str(fps))
        return self._send(200, {"ok": True, "fps": fps})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/playback":
      # [C1 补丁 2026-09-27] 播放控制：暂停/倍速/重播。写 flag 文件，camera.py 每 0.5 秒读取生效。
      # 原子写：camera.py 读到写一半的内容（半截数字）会被当成「新值」→ 重复触发，必须先写临时文件再替换。
      def _w(path, text):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
          f.write(text)
        os.replace(tmp, path)
      try:
        if "pause" in body:
          _w(PAUSE_FLAG, "1" if body.get("pause") else "0")
          # [恢复到主页 2026-09-30] 点「继续播放」= 离开主页模式（op 恢复行车）
          if not body.get("pause"):
            try:
              os.remove(HOME_FLAG)
            except FileNotFoundError:
              pass
        if "speed" in body:
          sp = min(4.0, max(0.25, float(body.get("speed") or 1)))
          _w(SPEED_FLAG, f"{sp:g}")
        if body.get("restart"):
          _w(RESTART_FLAG, str(time.time()))
        state = {"pause": False, "speed": 1.0}
        try:
          with open(PAUSE_FLAG) as f:
            state["pause"] = f.read().strip() == "1"
        except Exception:
          pass
        try:
          with open(SPEED_FLAG) as f:
            state["speed"] = float(f.read().strip() or "1")
        except Exception:
          pass
        return self._send(200, {"ok": True, **state})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/click":
      # [C2 补丁 2026-09-27] 网页点击 → 转发给 op UI 进程（归一化坐标 0~1，写文件+换 seq）
      try:
        x = min(1.0, max(0.0, float(body.get("x", 0.5))))
        y = min(1.0, max(0.0, float(body.get("y", 0.5))))
        tmp = CLICK_FILE + ".tmp"
        with open(tmp, "w") as f:
          json.dump({"seq": int(time.time() * 1000), "x": x, "y": y}, f)
        os.replace(tmp, CLICK_FILE)
        return self._send(200, {"ok": True, "x": x, "y": y})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/quit":
      # [C1 补丁 2026-09-27] 退出全部：停全栈 + 关掉控制台 app（app 看门狗兜底清理后端）
      # 关 app 用「生命周期日志里最后一条 app_pid」精确 SIGTERM —— 不要用 pkill -f：
      # 它会连带匹配「命令行里含同名字符串」的进程（后端自己的 shell、用户的终端都中过招）。
      try:
        subprocess.Popen(["/bin/bash", LAUNCHER, "__STOP__", "stop-only"],
                         stdout=open(f"{LOGS}/launcher_app.log", "a"), stderr=subprocess.STDOUT,
                         cwd=DEMO, start_new_session=True)
        app_pid = None
        try:
          with open(f"{LOGS}/app_lifecycle.log") as f:
            for line in f:
              m = re.search(r"app_pid=(\d+)", line)
              if m:
                app_pid = int(m.group(1))
        except Exception:
          pass
        if app_pid:
          try:
            os.kill(app_pid, signal.SIGTERM)
          except Exception:
            pass
        return self._send(200, {"ok": True, "msg": "正在退出…", "app_pid": app_pid})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/export/frame":
      try:
        data = body.get("png", "")
        data = re.sub(r"^data:image/png;base64,", "", data)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fn = f"{DESKTOP}/op控制台_{ts}.png"
        with open(fn, "wb") as f:
          f.write(base64.b64decode(data))
        return self._send(200, {"ok": True, "path": fn})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/export/opscreen":
      try:
        data = self._op_jpeg()
        ts = time.strftime("%Y%m%d_%H%M%S")
        dst = os.path.expanduser(f"~/Desktop/openpilot_主机画面_{ts}.jpg")
        with open(dst, "wb") as f:
          f.write(data)
        return self._send(200, {"ok": True, "path": dst})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    if p == "/api/export/data":
      try:
        with _LOCK:
          d = _LATEST["data"]
        ts = time.strftime("%Y%m%d_%H%M%S")
        fn = f"{DESKTOP}/op模型数据_{ts}.json"
        with open(fn, "w") as f:
          json.dump(d, f, ensure_ascii=False, indent=1)
        return self._send(200, {"ok": True, "path": fn})
      except Exception as e:
        return self._send(200, {"ok": False, "error": str(e)})

    return self._send(404, {"error": "not found"})


def main():
  os.makedirs(LOGS, exist_ok=True)
  threading.Thread(target=_collector, daemon=True).start()
  # 驾驶员监测功能已移除（2026-09-27）：不再起 cabin 采集线程（省 ~10% CPU）
  # threading.Thread(target=_cabin_loop, daemon=True).start()
  srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
  print(f"[console] http://127.0.0.1:{PORT}/  (pid={os.getpid()})", flush=True)
  with open(f"{LOGS}/console.pid", "w") as f:
    f.write(str(os.getpid()))
  srv.serve_forever()


if __name__ == "__main__":
  main()
