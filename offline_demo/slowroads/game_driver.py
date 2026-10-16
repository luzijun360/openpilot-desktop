#!/usr/bin/env python3
"""openpilot → 游戏 控制桥 v2（PWM 脉冲版，修「疯狂画龙」）

v1 的教训：键盘只有 0/1，直接「|方向盘|>死区就一直按住」= 每次都是满舵，
车子疯狂左右画龙。v2 改成：
  1) PWM：每个周期 T 内只按 占空比×T 的时间，占空比 ∝ |op 方向盘角|；
  2) 一阶低通滤波（τ=0.4s）op 的指令，抑制模型在游戏画面上的抖动；
  3) 油门/刹车同样 PWM，占空比 ∝ 加速度；
  4) 死区 2.5°；状态文件 1 秒不更新，游戏端自动全部松键（安全兜底）。

符号：steer 正 = 左（本机实测，见 CHANGELOG），SIGN 常量便于一键反转。
"""
import json
import os
import sys
import time
from collections import deque

sys.path.insert(0, "/Users/lu/op项目of all/openpilot")
import openpilot.cereal.messaging as messaging  # noqa: E402

OUT = "/Users/lu/op项目of all/openpilot/offline_demo/game_keys.json"
SIGN = 1.0           # 方向盘角符号：1 = 正角 = 左（实测约定）；若发现越修越偏说明反了，改 -1
STEER_FULL = 90.0    # 方向盘角达到该值 → 鼠标打满（放柔：op 在游戏画面上指令抖动大，增益要小）
TAU = 0.6            # 一阶低通时间常数（秒）：0.35→0.6 加强滤波压抖动（模型对游戏画面置信度低 ~0.5、指令抖 ±60°）
# [转向平滑 v4 2026-09-29] 用户实测「大把方向」：模型输出 = 长时间 ~0 + 偶发 ±5~15° 尖刺；
# 而 5° 死区把连续小量归零 → 交付变成「0 或突然跳 5~15°」→ 游戏里就是一把一把的方向。
# 处理：①中值滤波(5)去单帧尖刺 ②死区 5°→2°（防抖但不制造跳变）③输出变化率限制
# ④输出限幅（模型尖峰不给满舵）⑤纵向（油门/刹车）也加变化率限制，治「一窜一刹」
STEER_DEADBAND = 2.0  # 方向盘死区（度）：配合中值滤波，2° 足够防抖，不会制造跳变
MEDIAN_N = 5          # 中值滤波窗口（50Hz → 100ms）：去单帧尖刺
SLEW_DEG_S = 30.0     # 转向输出变化率上限（°/s）：大摆变柔（25° 满摆约 0.8 秒完成）
STEER_CLAMP = 25.0    # 转向输出限幅（°）：超过的尖峰直接截掉，不给满舵
TAU_ACCEL = 0.9       # 加速度低通时间常数（秒）：纵向单独、比转向缓
ACCEL_CLAMP = 1.0     # 加速度限幅（m/s²）：超出的不给
THR_SLEW = 0.6        # 油门输出变化率上限（每秒）
BRK_SLEW = 0.9        # 刹车输出变化率上限（每秒）
ACCEL_DB = 0.25      # 加速度死区
ACCEL_FULL = 1.2     # 满占空比加速度
ACCEL_MAX_DUTY = 0.5
ACCEL_BIAS = 1.2     # 油门偏置：op 巡航时 accel≈0，但游戏里要持续给油才能维持速度（给大点才跑得起来）
PWM_PERIOD = 0.12    # 油门/刹车 PWM 周期（秒）
RATE_HZ = 50
WRITE_HZ = 30        # 状态文件写入上限（游戏窗口按 30Hz 读）

# —— 虚拟手柄模式（[虚拟手柄 2026-09-28]）——
# 游戏窗口内伪造了 Gamepad API：转向/油门/刹车都是连续量，不再用鼠标位置 + 键位 PWM。
# 一条命令回退到鼠标/键盘方式：OP_GAME_PAD=0 python3 game_driver.py
PAD_MODE = os.environ.get("OP_GAME_PAD", "1") != "0"
PAD_THR_BIAS = 0.35  # 手柄模式下的"巡航油门"基线（op 巡航时 accel≈0，游戏里要持续给油）
PAD_THR_GAIN = 0.6   # 每 1 m/s² 加速度叠加的油门量
PAD_BRK_FULL = 1.5   # 减速度达到该值 → 刹车踩满


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def write(state):
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, OUT)          # 原子替换，读方永远拿到完整 JSON


def main():
    write({"left": 0, "right": 0, "up": 0, "down": 0, "steer": 0.0, "throttle": 0.0, "brake": 0.0,
           "pad": 1 if PAD_MODE else 0})   # 初始全松（pad 标记决定游戏窗口走手柄还是鼠标）
    sm = messaging.SubMaster(["carControl", "carState", "selfdriveState"])
    steer_f = 0.0        # 低通后的方向盘角
    accel_f = 0.0
    steer_lim = 0.0      # [v4] 变化率限制后的交付角
    thr_lim = 0.0        # [v4] 变化率限制后的油门
    brk_lim = 0.0        # [v4] 变化率限制后的刹车
    steer_buf = deque(maxlen=MEDIAN_N)   # [v4] 中值滤波窗口
    cyc = time.monotonic()      # 当前 PWM 周期起点
    last_t = cyc
    thr_dirn, thr_duty = None, 0.0    # 油门：'up'/'down'/None
    last = None
    last_write = 0.0
    last_log = time.monotonic()
    print(f"[game_driver] v3 鼠标转向 + 键盘油门：满舵 {STEER_FULL}° 低通 τ={TAU}s "
          f"PWM 周期 {PWM_PERIOD*1000:.0f}ms → {OUT}", flush=True)

    while True:
        sm.update(int(1000 / RATE_HZ))
        now = time.monotonic()
        dt = clamp(now - last_t, 0.0, 0.2)
        last_t = now
        active = bool(sm["selfdriveState"].active)
        act = sm["carControl"].actuators
        steer_raw = SIGN * float(act.steeringAngleDeg)
        accel_raw = float(act.accel)

        # 一阶低通（转向 τ=0.6；纵向 [v4] 单独 τ=0.9 + 限幅）
        a = clamp(dt / TAU, 0.0, 1.0)
        a2 = clamp(dt / TAU_ACCEL, 0.0, 1.0)
        steer_buf.append(steer_raw)
        steer_med = sorted(steer_buf)[len(steer_buf) // 2]   # [v4] 中值滤波：单帧尖刺不进低通
        steer_f += (steer_med - steer_f) * a
        accel_f += (clamp(accel_raw, -ACCEL_CLAMP, ACCEL_CLAMP) - accel_f) * a2

        # 每个 PWM 周期重算油门/刹车占空比
        if now - cyc >= PWM_PERIOD:
            cyc = now
            if active and accel_f < -ACCEL_DB:                      # 刹车（不带偏置，op 真减速才刹）
                thr_dirn = "down"
                thr_duty = clamp(-accel_f / ACCEL_FULL, 0.0, 1.0) * ACCEL_MAX_DUTY
            elif active and (accel_f + ACCEL_BIAS) > ACCEL_DB:      # 油门（带偏置，维持巡航速度）
                thr_dirn = "up"
                thr_duty = clamp((accel_f + ACCEL_BIAS) / ACCEL_FULL, 0.0, 1.0) * ACCEL_MAX_DUTY
            else:
                thr_dirn, thr_duty = None, 0.0

        # 当前处于周期的哪个相位
        phase = now - cyc
        thr_on = thr_dirn is not None and phase < thr_duty * PWM_PERIOD

        # 转向 = 连续量；油门/刹车：手柄模式 = 连续量，键盘回退模式 = PWM 开关量
        # [v4] 转向交付链：死区(2°) → 限幅(±25°) → 变化率限制(30°/s)
        tgt = 0.0 if abs(steer_f) < STEER_DEADBAND else clamp(steer_f, -STEER_CLAMP, STEER_CLAMP)
        if not active:
            tgt = 0.0
        sstep = SLEW_DEG_S * dt
        steer_lim += clamp(tgt - steer_lim, -sstep, sstep)
        steer_out = clamp(steer_lim / STEER_FULL, -1.0, 1.0)
        if PAD_MODE:
            # [v4] 油门/刹车同样加变化率限制，治「一窜一刹」
            thr_tgt = clamp(PAD_THR_BIAS + PAD_THR_GAIN * accel_f, 0.0, 1.0) if active else 0.0
            brk_tgt = clamp(-accel_f / PAD_BRK_FULL, 0.0, 1.0) if active else 0.0
            thr_lim += clamp(thr_tgt - thr_lim, -THR_SLEW * dt, THR_SLEW * dt)
            brk_lim += clamp(brk_tgt - brk_lim, -BRK_SLEW * dt, BRK_SLEW * dt)
            thr_analog, brk_analog = thr_lim, brk_lim
        else:
            thr_analog = brk_analog = 0.0
        state = {
            "steer": round(steer_out, 3),
            "throttle": round(thr_analog, 3),      # [虚拟手柄 2026-09-28]
            "brake": round(brk_analog, 3),         # [虚拟手柄 2026-09-28]
            "pad": 1 if PAD_MODE else 0,           # 告诉游戏窗口：走手柄，别碰鼠标/键盘
            "up": 1 if (thr_on and thr_dirn == "up") else 0,
            "down": 1 if (thr_on and thr_dirn == "down") else 0,
        }
        if state != last and now - last_write >= 1.0 / WRITE_HZ:
            write(state)
            last = state
            last_write = now

        if now - last_log > 5.0:
            last_log = now
            keys = [k for k, v in state.items() if v]
            print(f"[game_driver] 接管={active} 方向盘(滤波)={steer_f:+.1f}°→交付{steer_lim:+.1f}° "
                  f"鼠标={steer_out:+.2f} 加速度={accel_f:+.2f} "
                  f"→ {keys or '（无）'}", flush=True)


if __name__ == "__main__":
    main()
