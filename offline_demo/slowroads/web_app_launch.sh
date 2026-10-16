#!/bin/bash
# ============================================================
# openpilot 网页版 —— 生命周期脚本（由「openpilot 网页版.app」启动）
#
# 语义（2026-09-29 与用户约定；2026-09-30 双 app 逻辑统一）：
#   打开 app：缺什么补什么
#     · 后端没跑   → 起后端
#     · op 全栈没跑 → 起 op 全栈：
#         [slowroads App + 主页默认 2026-09-30] slowroads App 开着 → 自动接入 slowroads；
#         否则 → 主页模式（op 熄火停主页）—— 不再自动重播上次视频（用户约定的空闲态）。
#     · Tailscale /op 发布没挂 → 挂上
#   关闭 app：
#     · 桌面版 app 在用 → 共享的后端和 op 全栈留着，只撤 Tailscale 发布
#     · 桌面版没在用   → 全停（撤发布 + 停后端 + 停全栈）
#   [双app逻辑 2026-09-30] 关的时候看到对方「还在」会等 5 秒再确认一次
#   （防两个几乎同时关误判）；决定「保留」的话 20 秒后兜底复查：
#   那时两个 app 都不在 → 自动收摊。
#   备份：web_app_launch.sh.bak-20260930-dualapp
#
# 与「openpilot 控制台.app」（原版）互不干扰。
# ============================================================
set -u
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
LOGS="$DEMO/logs"
LAUNCHER="$DEMO/op_app_launcher.sh"
LASTVIDEO="$DEMO/last_video.txt"
DEFAULT_VIDEO="$DEMO/test_1928x1208.mp4"
URL="http://127.0.0.1:8899/api/status"
TS=/usr/local/bin/tailscale
TS_PORT=10000
TS_PATH=/op
# 桌面版 app 的生命周期脚本（用它判断桌面版在不在用）；方括号防自匹配；测试钩子可覆盖
DESK_PAT="${WEB_APP_DESK_PAT:-[c]onsole_app_launch.sh}"
DRY="${WEB_APP_DRY:-0}"                                  # 演练模式：只记日志不动手（自测用）
mkdir -p "$LOGS"

LOG="$LOGS/web_app_lifecycle.log"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

APP_PID=$PPID
APP_COMM=$(ps -o comm= -p "$APP_PID" 2>/dev/null || true)
MAIN_PID=$$

WD_PID=""
CLEANED=""

alive()      { curl -s -m 2 --noproxy '*' -o /dev/null "$URL" 2>/dev/null; }
ts_mounted() { "$TS" serve status 2>/dev/null | grep -q -- "|-- ${TS_PATH} "; }
desk_up()    { pgrep -f "$DESK_PAT" >/dev/null 2>&1; }

start_backend() {
  cd /Users/lu/op项目of all/openpilot || return 1
  nohup /Users/lu/op项目of all/openpilot/.venv/bin/python3 offline_demo/console_server.py >> "$LOGS/console.log" 2>&1 &
  for _ in $(seq 1 40); do
    alive && return 0
    sleep 0.5
  done
  return 1
}

# 停共享资源（op 全栈 + 后端）
stop_shared() {
  /bin/bash "$LAUNCHER" __STOP__ stop-only >> "$LOGS/launcher.log" 2>&1 || true
  pkill -f "offline_demo/[c]onsole_server.py" 2>/dev/null || true
}

# [双app逻辑 2026-09-30] 决定「保留」后 20 秒兜底复查：
# 防两个 app 几乎同时关、两边都判断「对方还在」而谁都没收摊的极端情况。
# 注意：必须用独立 bash -c 运行 —— 不能用子 shell 跑函数体：子 shell 会继承本脚本
# 的 argv，被对方的「还在吗」检测误认成脚本还活着（幽灵匹配，实测踩过）。
schedule_gc() {
  nohup bash -c '
    sleep 20
    if ! pgrep -f "[c]onsole_app_launch.sh" >/dev/null 2>&1 \
       && ! pgrep -f "[w]eb_app_launch.sh" >/dev/null 2>&1; then
      echo "[$(date "+%F %T")] 兜底复查：两个 app 都已不在 → 停共享资源" >> "$1"
      /bin/bash "$2" __STOP__ stop-only >> "$3" 2>&1 || true
      pkill -f "offline_demo/[c]onsole_server.py" 2>/dev/null || true
    fi' _ "$LOG" "$LAUNCHER" "$LOGS/launcher.log" >/dev/null 2>&1 &
}

cleanup() {
  [ -n "$CLEANED" ] && return
  CLEANED=1
  log "cleanup 开始"
  [ -n "$WD_PID" ] && kill "$WD_PID" 2>/dev/null || true

  # ① 撤 Tailscale 发布 —— 这是「网页版」对外的总开关，总是撤
  if ts_mounted; then
    if [ "$DRY" = "1" ]; then
      log "[DRY] 本应撤 Tailscale 发布 :${TS_PORT}${TS_PATH}"
    else
      "$TS" serve --https="${TS_PORT}" --set-path="${TS_PATH}" off >> "$LOG" 2>&1 || true
      log "已撤 Tailscale 发布 :${TS_PORT}${TS_PATH}"
    fi
  else
    log "Tailscale 发布本来就没挂"
  fi

  # ② 共享资源（后端 + op 全栈）：桌面版在用就留着，否则全停
  # [双app逻辑 2026-09-30] 看到桌面版「还在」先等 5 秒再确认一次（防两个几乎同时关误判）
  if desk_up; then
    sleep 5
    if desk_up; then
      log "桌面版 app 在运行 → 后端与 op 全栈保留（桌面版继续用）"
      if [ "$DRY" = "1" ]; then
        log "[DRY] 本应安排 20 秒兜底复查（演练，不执行）"
      else
        schedule_gc
      fi
      log "cleanup 完成（保留）"
      return
    fi
    log "等待后桌面版也已退出 → 由本脚本收摊"
  fi

  if [ "$DRY" = "1" ]; then
    log "[DRY] 桌面版未运行 → 本应停 op 全栈 + 停后端（演练，不执行）"
  else
    log "桌面版未运行 → 停 op 全栈 + 停后端"
    stop_shared
  fi
  log "cleanup 完成"
}
trap cleanup EXIT
# 双重信号加固：cleanup 进行中再收到 TERM 时不打断（等它跑完自然退出）
trap 'if [ -z "$CLEANED" ]; then cleanup; exit 0; fi' TERM INT HUP

log "启动：app_pid=${APP_PID} (${APP_COMM})"

# ---------- ① 后端（幂等）----------
if alive; then
  log "后端已在运行（复用，不动它）"
else
  log "启动后端"
  if start_backend; then log "后端已就绪"; else log "后端启动失败"; fi
fi

# ---------- ② op 全栈（幂等）----------
# [slowroads App + 主页默认 2026-09-30] slowroads App 开着 → 自动接入 slowroads；
# 否则 → 主页模式（op 熄火停主页）；不再自动重播上次视频。
if pgrep -f "offline_demo/run_offline_demo.sh" >/dev/null 2>&1; then
  log "op 全栈已在运行（复用，不动它）"
else
  SR_PID=$(/usr/bin/python3 -c "import json;print(json.load(open('$DEMO/slowroads_app.json')).get('pid',0))" 2>/dev/null || echo 0)
  if [ -n "$SR_PID" ] && [ "$SR_PID" != "0" ] && kill -0 "$SR_PID" 2>/dev/null; then
    log "slowroads App 在跑 → 自动接入 slowroads"
    /bin/bash "$DEMO/slowroads_connect.sh" >> "$LOGS/slowroads_connect.log" 2>&1 &
  else
    log "启动 op 全栈（主页模式）"
    /bin/bash "$LAUNCHER" "__HOME__" auto >> "$LOGS/launcher.log" 2>&1 &
  fi
fi

# ---------- ③ Tailscale 发布（幂等）----------
if ts_mounted; then
  log "Tailscale 发布已存在（复用）"
else
  log "挂 Tailscale 发布 :${TS_PORT}${TS_PATH} → http://127.0.0.1:8899"
  if "$TS" serve --bg --https="${TS_PORT}" --set-path="${TS_PATH}" http://127.0.0.1:8899 >> "$LOG" 2>&1; then
    log "Tailscale 发布已挂上"
  else
    log "Tailscale 发布挂载失败（详见本日志上文）"
  fi
fi

# ---------- ④ 看门狗 ----------
# app 退出（含被强杀）→ 通知主进程走 cleanup；
# 后端无响应且桌面版没在跑 → 重启后端（保住状态页 / 手机端）。
# 注意：不自动重启 op 全栈 —— 那会让控制台的「停止」按钮失效。
(
  while :; do
    sleep 3
    if ! kill -0 "$APP_PID" 2>/dev/null; then
      log "看门狗：app(${APP_PID}) 已退出 → 触发清理"
      kill -TERM "$MAIN_PID" 2>/dev/null
      exit 0
    fi
    if ! alive; then
      if desk_up; then
        log "看门狗：后端无响应，但桌面版在跑（由它自愈）→ 不介入"
      else
        log "看门狗：后端无响应 → 重启后端"
        cd /Users/lu/op项目of all/openpilot || true
        nohup /Users/lu/op项目of all/openpilot/.venv/bin/python3 offline_demo/console_server.py >> "$LOGS/console.log" 2>&1 &
        sleep 4
      fi
    fi
  done
) &
WD_PID=$!
log "看门狗已启动 pid=${WD_PID}（监控 app pid=${APP_PID}）"

wait "$WD_PID"
