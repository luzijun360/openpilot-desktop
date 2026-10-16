#!/usr/bin/env python3
"""离线视频回放桥接（带纵向控制）：让 openpilot 全栈在没有真车的情况下进入 onroad、跑真模型、并真正接管。

- 假车：模拟 Honda Civic 2022（CAN 报文 + pandaStates），机制与 tools/sim 完全一致
- 自动接管：engageable 时交替按 MAIN / DECEL_SET 巡航键（与官方 sim 相同序列）
- 纵向闭环：车速跟随 openpilot 的 carControl.actuators.accel（v += a·dt），所以 ACC 真的在控速
- 横向闭环（N1 修复 2026-09-27）：方向盘角度 = 用 op 的期望曲率经 VehicleModel 反算的「几何车轮角」
  （不再把指令原样回喂——那会让 paramsd 学到假偏置、显示恒偏 +14~18°）；偏航率喂给 IMU 陀螺仪，
  航向/位置积分给 GPS → 定位、标定、参数学习都能看到真实的横向运动
- 初始车速（N2 修复 2026-09-27）：从素材文件名解析（30-0斜.mov → 30 km/h）；否则 FAKE_CAR_SPEED_KMH；默认 60
- 控制台开关：文件 long_control.flag（默认 True）→ 控制台里可随时开/关接管
- [恢复到主页 2026-09-30] 主页模式：文件 home.flag="1" 时熄火（ignition=False）→ op 进 offroad →
  UI 自动渲染 openpilot 主页（「恢复到主页」按钮 / slowroads 断开 / 主页启动器用它；恢复=清 flag 重新点火）

用法（见 run_offline_demo.sh）:
    USE_WEBCAM=1 ROAD_CAM=<视频路径> python3 offline_demo/fake_car_bridge.py
"""
import json
import math
import os
import re
import time
import traceback

from opendbc.car.honda.values import CruiseButtons
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.realtime import Ratekeeper
from openpilot.common.params import Params
from openpilot.tools.sim.lib.common import SimulatorState, vec3

# 让 SimulatedSensors 不要再自己开一个 VisionIpcServer("camerad")——会与 webcamerad 冲突
import openpilot.tools.sim.lib.simulated_sensors as sim_sensors


class _NoCams:
  """占位类：替换 sim 的 Camerad，摄像头画面交给 webcamerad"""
  def __init__(self, *args, **kwargs):
    pass

  def rgb_to_yuv(self, *args, **kwargs):
    return None

  def cam_send_yuv_road(self, *args, **kwargs):
    pass

  def cam_send_yuv_wide_road(self, *args, **kwargs):
    pass


sim_sensors.Camerad = _NoCams

from openpilot.tools.sim.lib.simulated_car import SimulatedCar  # noqa: E402
from openpilot.tools.sim.lib.simulated_sensors import SimulatedSensors  # noqa: E402

MAX_SPEED = 16.7    # 上限 60 km/h（原 45 m/s=162km/h 太快：游戏窄弯道在 90+ 直接冲出路面）
MIN_SPEED = 8.0 / 3.6   # 最低速 8 km/h：op 对游戏画面会误判出 -3.5 急刹把假车刹到 0 → 自动退出接管；
                        # 托底后永远不会因「停车」掉出接管（游戏演示不需要真停）
DT = 0.01           # 100Hz
FLAG = "/Users/lu/op项目of all/openpilot/offline_demo/long_control.flag"   # 控制台开关（文件方式，Params 只接受预定义键）
GAME_SPEED = "/Users/lu/op项目of all/openpilot/offline_demo/game_speed.json"   # 游戏窗口 OCR 出的实际车速（km/h）
# [恢复到主页 2026-09-30] 主页模式开关："1" = 熄火（op → offroad → UI 渲染主页）。
# 由控制台「恢复到主页」按钮 / slowroads 断开脚本 / 主页启动器写；播视频、接入 slowroads 时自动清。
HOME_FLAG = "/Users/lu/op项目of all/openpilot/offline_demo/home.flag"


def _game_speed():
  """[慢速修复] 读游戏窗口 OCR 出的实际车速（m/s）。2 秒内有效，否则返回 None。
  这是「控制对不上」的根治：op 按假车速度算方向盘角，假车速度必须等于游戏里的真实车速。"""
  try:
    with open(GAME_SPEED) as f:
      d = json.load(f)
    if time.time() - float(d.get("t", 0)) < 2.0:
      return float(d["kmh"]) / 3.6
  except Exception:
    pass
  return None


def _long_enabled() -> bool:
  try:
    with open(FLAG) as f:
      return f.read().strip() != "0"
  except Exception:
    return True   # 文件不存在时默认开启接管


def _home_enabled() -> bool:
  """[恢复到主页 2026-09-30] 主页模式：home.flag="1" 时熄火（op 进 offroad → UI 渲染主页）。"""
  try:
    with open(HOME_FLAG) as f:
      return f.read().strip() == "1"
  except Exception:
    return False


def _initial_speed():
  """[N2 修复 2026-09-27] 初始车速与素材档位对齐：文件名里的 "NN-0"（如 30-0斜.mov → 30 km/h）。"""
  src = os.getenv("ROAD_CAM") or os.getenv("WIDE_CAM") or ""
  m = re.search(r"(\d+)-0", os.path.basename(src))
  if m and 5 <= float(m.group(1)) <= 200:
    return float(m.group(1)) / 3.6, f"素材档位 {m.group(1)} km/h"
  env = os.getenv("FAKE_CAR_SPEED_KMH")
  if env:
    try:
      return float(env) / 3.6, f"环境变量 {env} km/h"
    except ValueError:
      pass
  return 60.0 / 3.6, "默认 60 km/h"


def main():
  # 注：条款/培训/有效标定参数由 run_offline_demo.sh 在启动前写好（此处不再重复调用，
  # 省掉一次重量级 import 的启动开销 → CAN 报文更早发出 → card 初始化/识别更早完成）。
  params = Params()
  params.put_bool("AlphaLongitudinalEnabled", True, block=True)   # Honda 雷达less → op 纵向控制
  # [N1 修复 2026-09-27] 清掉上次运行学到的车辆参数（含被「指令回喂」污染的假方向盘偏置 ~17°），
  # 让 paramsd 在修正后的数据上重新收敛到真实值。
  try:
    params.remove("LiveParametersV2")
  except Exception:
    pass
  try:
    with open(FLAG) as f:
      pass
  except Exception:
    with open(FLAG, "w") as f:
      f.write("1")                                                # 首次运行默认开启接管

  speed_ms, speed_src = _initial_speed()

  # 构造行驶中的假车辆状态
  state = SimulatorState()
  state.valid = True
  state.ignition = True
  state.velocity = vec3(speed_ms, 0.0, 0.0)
  state.gps.from_xy((0.0, 0.0))
  state.imu.accelerometer = vec3(-9.81, 0.0, 0.0)   # 静止时的重力读数（上 = +9.81；原始轴 x 取负）
  state.imu.gyroscope = vec3(0.0, 0.0, 0.0)
  state.imu.bearing = 0.0
  state.steering_angle = 0.0
  state.user_gas = 0.0
  state.user_brake = 0.0
  state.user_torque = 0.0
  state.cruise_button = 0
  state.left_blinker = False
  state.right_blinker = False
  state.is_engaged = False

  car = SimulatedCar()
  sensors = SimulatedSensors(dual_camera=False)

  startup_button_prev = True
  long_prev = _long_enabled()
  home_prev = _home_enabled()          # [恢复到主页 2026-09-30]
  vm = None            # VehicleModel：拿到 carParams 后构造（N1）
  heading = 0.0        # 航向（rad；逆时针/左转为正）
  x_pos = 0.0
  y_pos = 0.0
  omega = 0.0          # 偏航率（rad/s）
  last_log = time.monotonic()
  last_param_check = time.monotonic()
  last_home_check = time.monotonic()   # [恢复到主页 2026-09-30]

  print(f"[fake_car_bridge] 启动：ignition={not home_prev}, 初始 {speed_ms*3.6:.0f} km/h（{speed_src}）, "
        f"纵向接管={'开' if long_prev else '关'}, 主页模式={'开' if home_prev else '关'}", flush=True)

  rk = Ratekeeper(100, None)
  while True:
    state.cruise_button = 0

    # ---- 读 openpilot 状态与指令 ----
    car.sm.update(0)
    ss = car.sm['selfdriveState']
    state.is_engaged = bool(ss.active)

    if state.is_engaged:
      # 纵向：车速优先跟随「游戏里的真实车速」（OCR 值，平滑过渡）；没有则退回积分 op 加速度
      accel = float(car.sm['carControl'].actuators.accel)
      gv = _game_speed()
      if gv is not None:
        # 平滑：向游戏实际车速靠拢（0.3 权重，避免 OCR 抖动直接进模型）
        v = state.velocity.x + (gv - state.velocity.x) * 0.3
      else:
        v = state.velocity.x + accel * DT
      v = max(MIN_SPEED, min(MAX_SPEED, v))     # 托底：永不掉到 0（防止误判停车 → 退出接管）
      state.velocity = vec3(v, 0.0, 0.0)

      # ---- N1 修复 2026-09-27：横向动力学（期望曲率 → 车轮角 → 偏航率 → 航向/位置/IMU）----
      if vm is None and car.sm.valid['carParams']:
        vm = VehicleModel(car.sm['carParams'])
      curv = float(car.sm['carControl'].actuators.curvature)        # op 期望曲率（左正）
      steer = 0.0
      if vm is not None and v > 0.5:
        steer = math.degrees(vm.get_steer_from_curvature(-curv, v, 0.0))
      state.steering_angle = steer                                   # 几何车轮角（模拟 EPS 执行）
      omega = curv * v                                               # 偏航率（左转为正）
      heading += omega * DT
      x_pos += v * math.cos(heading) * DT
      y_pos += v * math.sin(heading) * DT
      state.gps.from_xy((x_pos, y_pos))
      # 原始 IMU 轴映射：陀螺仪 x = -偏航率；加速度计 = (-9.81 重力, -横向, -纵向)
      state.imu.gyroscope = vec3(-omega, 0.0, 0.0)
      state.imu.accelerometer = vec3(-9.81, -v * omega, -accel)
      state.imu.bearing = math.degrees(heading)
    elif long_prev and ss.engageable and not home_prev:
      # 自动接管：与官方 sim 相同的按键序列（主页模式下不按 —— op 已熄火）
      state.cruise_button = CruiseButtons.DECEL_SET if startup_button_prev else CruiseButtons.MAIN
      startup_button_prev = not startup_button_prev

    # ---- 控制台开关：关掉纵向控制时按 CANCEL 解除接管 ----
    if time.monotonic() - last_param_check > 1.0:
      last_param_check = time.monotonic()
      long_now = _long_enabled()
      if long_now != long_prev:
        print(f"[fake_car_bridge] 控制台切换纵向接管: {'开' if long_now else '关'}", flush=True)
        if not long_now and state.is_engaged:
          state.cruise_button = CruiseButtons.CANCEL
        long_prev = long_now

    # ---- [恢复到主页 2026-09-30] 主页模式：熄火 → op 进 offroad → UI 渲染主页 ----
    # 恢复（清 flag）→ 重新点火 → op 自动重新接管（走上面的自动接管序列）。
    if time.monotonic() - last_home_check > 1.0:
      last_home_check = time.monotonic()
      home_now = _home_enabled()
      if home_now != home_prev:
        print(f"[fake_car_bridge] 主页模式：{'开（熄火 → op 回主页）' if home_now else '关（点火 → op 恢复行车）'}", flush=True)
        if home_now and state.is_engaged:
          state.cruise_button = CruiseButtons.CANCEL   # 保险：立即解除接管
        home_prev = home_now
    state.ignition = not home_prev
    if home_prev:
      state.velocity = vec3(0.0, 0.0, 0.0)             # 主页模式 = 驻车

    car.update(state)            # 假 CAN + pandaStates（100Hz，pandaState 每 50 帧）
    sensors.update(state, None)   # IMU/GPS（100Hz）+ 假驾驶员监控 + 外设

    if time.monotonic() - last_log > 15.0:
      last_log = time.monotonic()
      print(f"[fake_car_bridge] {'已接管' if state.is_engaged else ('待接管' if long_prev else '未接管')} "
            f"| 车速 {state.velocity.x*3.6:.1f} km/h | 方向盘 {state.steering_angle:+.1f}° | "
            f"偏航率 {math.degrees(omega):+.2f}°/s", flush=True)
    rk.keep_time()


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("[fake_car_bridge] 退出")
  except Exception:
    traceback.print_exc()
    raise
