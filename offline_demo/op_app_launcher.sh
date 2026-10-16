#!/bin/bash
# ============================================================
# openpilot 控制台 —— 核心启动器（供 .app / 控制台网页调用）
#   1) 选择或拖入任意行车视频（免转码：分辨率在播放时实时对齐，导入秒开）
#   2) 启动 openpilot 全栈：假车桥接 + 视频摄像头 + comma 风格大 UI
#   再次运行：可「换新视频 / 停止运行 / 保留运行」
#
# 用法: op_app_launcher.sh [视频路径|__HOME__] [auto]     （auto = 跳过确认对话框，用于自动化测试）
#   [slowroads 自动接入 + 恢复到主页 2026-09-30]
#   · __HOME__     = 主页模式：不播视频，op 熄火停主页（控制台空闲态 / 「恢复到主页」用）
#   · *.jpg/*.jpeg = 实时帧源（slowroads 实时画面），跳过视频解码校验
#   · 正常播视频时自动清 home.flag + 复位 pause.flag（不受上次暂停/主页状态影响）
# ============================================================
set -u

OP=/Users/lu/op项目of all/openpilot
DEMO="$OP/offline_demo"
LOGDIR="$DEMO/logs"
PIDFILE="$LOGDIR/stack.pid"
LASTVIDEO="$DEMO/last_video.txt"
MATERIAL="/Users/lu/op项目of all/op方向的辅助驾驶方案/测试素材"
# [slowroads 自动接入 + 恢复到主页 2026-09-30]
HOME_FLAG="$DEMO/home.flag"
HOME_FRAME="$DEMO/home_frame.jpg"
PAUSE_FLAG="$DEMO/pause.flag"

mkdir -p "$LOGDIR"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$OP/.venv/bin"
export TERM="${TERM:-xterm-256color}"
exec >>"$LOGDIR/launcher.log" 2>&1
echo "===== [$(date '+%F %T')] launcher args=[$*] ====="

VIDEO="${1:-}"
MODE="${2:-}"

# [恢复到主页 2026-09-30] __HOME__ = 主页模式（控制台空闲态用；不写 last_video，保持上次视频记录）
HOME_MODE=""
if [ "$VIDEO" = "__HOME__" ]; then
  VIDEO="$HOME_FRAME"
  HOME_MODE=1
  MODE="auto"
fi

say() { osascript -e "display notification \"$1\" with title \"openpilot 控制台\"" >/dev/null 2>&1 || true; }
alert() { osascript -e "display dialog \"$1\" buttons {\"好\"} default button 1 with title \"openpilot 控制台\" with icon note" >/dev/null 2>&1 || true; }
pick() { # $1=正文 $2=默认按钮 $3.. =其它按钮（最后一个=取消）
  local body="$1"; shift
  local btns=""
  for b in "$@"; do btns="$btns\"$b\", "; done
  btns="${btns%, }"
  osascript -e "button returned of (display dialog \"$body\" buttons {$btns} default button \"$2\" with title \"openpilot 控制台\")" 2>/dev/null
}

# ---------- 运行状态 ----------
stack_pid() {
  if [ -f "$PIDFILE" ]; then
    local p; p=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo "$p"; return; fi
  fi
  pgrep -f "offline_demo/run_offline_demo.sh" 2>/dev/null | head -1
}

stop_stack() {
  local p; p=$(stack_pid)
  [ -n "$p" ] && kill "$p" 2>/dev/null
  sleep 1
  # 注意：manager 的进程名是 `python3 ./manager.py`（相对路径），
  # 用 "system/manager/manager.py" 匹配不到——必须用宽松模式，否则旧实例残留会和新的抢 msgq
  for pat in "offline_demo/run_offline_demo.sh" "offline_demo/fake_car_bridge.py" "manager.py" \
             "openpilot.selfdrive" "openpilot.system" "openpilot.tools" "selfdrive/ui/ui.py"; do
    pkill -f "$pat" 2>/dev/null || true
  done
  # 等待优雅退出，最多 8 秒
  for i in $(seq 1 16); do
    if ! pgrep -f "manager.py|openpilot\.(selfdrive|system)" >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
  # 还在的强杀
  for pat in "manager.py" "openpilot.selfdrive" "openpilot.system" "openpilot.tools" "fake_car_bridge"; do
    pkill -9 -f "$pat" 2>/dev/null || true
  done
  sleep 1
  rm -f "$PIDFILE"
  if pgrep -f "manager.py|openpilot\.(selfdrive|system)" >/dev/null 2>&1; then
    echo "警告：仍有残留进程"; pgrep -fl "manager.py|openpilot\." | head -5
  else
    echo "已停止栈（系统干净）"
  fi
}

RUNNING=$(stack_pid)

# 仅停止模式（控制台调用）
if [ "$VIDEO" = "__STOP__" ] || [ "$MODE" = "stop-only" ]; then
  stop_stack
  say "已停止 ✓"
  exit 0
fi

if [ -n "$RUNNING" ]; then
  if [ "$MODE" = "auto" ]; then
    echo "auto：先停止已有实例 ($RUNNING)"
    stop_stack
  else
    ans=$(pick "openpilot 正在运行中（视频正在播放）。\n\n要做什么？" "换新视频" "停止运行" "保留运行")
    case "$ans" in
      "停止运行") stop_stack; say "已停止 ✓"; exit 0 ;;
      "保留运行"|"") exit 0 ;;
      "换新视频") stop_stack ;;
    esac
  fi
fi

# ---------- 选视频 ----------
if [ -z "$VIDEO" ]; then
  DEF=""
  [ -d "$MATERIAL" ] && DEF="default location POSIX file \"$MATERIAL\""
  VIDEO=$(osascript -e "POSIX path of (choose file with prompt \"选择一段行车视频（前挡风/行车记录仪视角最佳）\" of type {\"public.movie\"} $DEF)" 2>/dev/null || true)
fi
[ -n "$VIDEO" ] || { echo "用户取消选择"; exit 0; }
[ -f "$VIDEO" ] || { alert "文件不存在：\n$VIDEO"; exit 1; }
NAME=$(basename "$VIDEO")

# ---------- 确认 ----------
if [ "$MODE" != "auto" ]; then
  ans=$(pick "将播放：\n\n$NAME\n\n流程：直接启动 openpilot 全栈（免转码，导入秒开）。\n屏幕上会出现一个 openpilot 界面窗口（大窗口，含车道线/路径叠加）。\n\n继续吗？" "开始" "取消")
  [ "$ans" = "开始" ] || { echo "用户取消"; exit 0; }
fi

# ---------- 快速校验 ----------
# [slowroads 自动接入 2026-09-30] 实时帧源（*.jpg）不是视频，跳过解码校验（只查存在性，上面已查）
# 主页模式（__HOME__）：home_frame.jpg 不存在时现场生成一张深灰占位帧（尺寸与 live_frame 一致）
if [ -n "$HOME_MODE" ] && [ ! -f "$HOME_FRAME" ]; then
  echo "生成主页占位帧: $HOME_FRAME"
  "$OP/.venv/bin/python3" -c "import cv2, numpy as np; cv2.imwrite('$HOME_FRAME', np.full((1208, 1928, 3), 24, np.uint8))" || true
fi
case "$VIDEO" in
  *.jpg|*.jpeg)
    echo "实时帧源（跳过视频校验）：$VIDEO" ;;
  *)
    if ! "$OP/.venv/bin/python3" - "$VIDEO" <<'PY'
import sys
import cv2
cap = cv2.VideoCapture(sys.argv[1])
ok = bool(cap.isOpened()) and bool(cap.read()[0])
cap.release()
sys.exit(0 if ok else 1)
PY
    then
      alert "这个视频打不开（解码失败）：\n$NAME"
      exit 1
    fi
    echo "视频校验通过（免转码直接播放）：$VIDEO" ;;
esac

# ---------- 启动全栈 ----------
# [推理后端设置 2026-09-28] 控制台里选的推理后端优先；没有则用 run_offline_demo.sh 的默认值（coreml/ANE）
if [ -z "${OP_MODEL_BACKEND:-}" ] && [ -f "$DEMO/model_backend.txt" ]; then
  export OP_MODEL_BACKEND="$(tr -d '[:space:]' < "$DEMO/model_backend.txt" 2>/dev/null)"
  echo "控制台设置：推理后端 = ${OP_MODEL_BACKEND:-未设置}"
fi
# 启动前最后确认系统干净（防止旧实例残留抢 msgq）
if pgrep -f "manager.py|openpilot\.(selfdrive|system)" >/dev/null 2>&1; then
  echo "启动前发现残留进程，清理中…"
  stop_stack
fi
# [slowroads 自动接入 + 恢复到主页 2026-09-30] 启动模式与 flag：
#   主页模式 → 写 home.flag=1（桥接熄火 → op 显示主页）；不写 last_video（保持上次视频记录）
#   正常播放 → 清 home.flag + 复位 pause（新片从头正常播）+ 记 last_video
if [ -n "$HOME_MODE" ]; then
  echo 1 > "$HOME_FLAG"
  say "正在启动 openpilot（主页模式）…"
else
  rm -f "$HOME_FLAG"
  echo 0 > "$PAUSE_FLAG"
  echo "$VIDEO" > "$LASTVIDEO"
  say "视频就绪，正在启动 openpilot…"
fi
cd "$OP" || exit 1
SCRATCH="$LOGDIR" nohup "$DEMO/run_offline_demo.sh" "$VIDEO" >"$LOGDIR/stack.log" 2>&1 &
SPID=$!
echo "$SPID" > "$PIDFILE"
disown $SPID 2>/dev/null || true
sleep 6

if kill -0 "$SPID" 2>/dev/null; then
  say "已启动 ✓ openpilot 界面窗口马上出现（再次双击本应用可停止/换片）"
  echo "启动成功 stack pid=$SPID"
else
  alert "启动失败，详情见：\n$LOGDIR/stack.log"
  exit 1
fi
exit 0
