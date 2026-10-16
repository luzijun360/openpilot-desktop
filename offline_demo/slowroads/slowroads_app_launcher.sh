#!/bin/bash
# ============================================================
# 「openpilot slowroads」启动器 —— 双击 App 时执行：
#   ① 打开游戏窗口（slowroads.io，位置/大小照旧，窗口自带实时帧输出）
#   ② 写心跳（slowroads_app.json，控制台靠它知道开没开；游戏窗口退出即失效）
#   ③ 自动接入：op 画面源切到 slowroads 实时帧（slowroads_connect.sh，约 40 秒）
#   ④ 窗口关闭 → 自动切出（slowroads_disconnect.sh）+ 清心跳
# 测试钩子（沙箱自测用，生产不设）：SLOWROADS_TEST_GAME_PAT / SLOWROADS_TEST_OPEN
# ============================================================
set -u
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
GAME="$DEMO/GameWindow.app"
URL="https://slowroads.io/"
GEOM=(1000 76 1880 1176)
HB="$DEMO/slowroads_app.json"
PIDFILE="$DEMO/slowroads_app.pid"
LOG="$DEMO/logs/slowroads_app.log"
GAME_PAT="${SLOWROADS_TEST_GAME_PAT:-[G]ameWindow}"
OPEN_CMD="${SLOWROADS_TEST_OPEN:-open}"
mkdir -p "$DEMO/logs"
exec >>"$LOG" 2>&1
echo "===== [$(date '+%F %T')] openpilot slowroads 启动 (pid=$$) ====="
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

# 防重入：已有会话在跑 → 只把游戏窗口带到前台，自己退出
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  echo "已有 slowroads 会话（pid $(cat "$PIDFILE")）→ 激活窗口后退出"
  osascript -e 'tell application "GameWindow" to activate' >/dev/null 2>&1 || true
  exit 0
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

# ① 游戏窗口（已在跑就不重开）
if pgrep -f "$GAME_PAT" >/dev/null 2>&1; then
  echo "游戏窗口已在跑"
else
  echo "打开游戏窗口…"
  "$OPEN_CMD" -n "$GAME" --args "$URL" "${GEOM[@]}"
fi

# 等窗口进程出现（最多 15 秒）
GPID=""
for _ in $(seq 1 30); do
  GPID=$(pgrep -f "$GAME_PAT" | head -1 || true)
  [ -n "$GPID" ] && break
  sleep 0.5
done
if [ -z "$GPID" ]; then
  echo "游戏窗口没起来，退出"
  osascript -e 'display notification "游戏窗口启动失败，详见 logs/slowroads_app.log" with title "openpilot slowroads"' >/dev/null 2>&1 || true
  exit 1
fi
echo "游戏窗口 pid=$GPID"

# ② 心跳循环（原子写）+ ③ 自动接入（后台跑，别挡住心跳）
(
  while kill -0 "$GPID" 2>/dev/null; do
    printf '{"pid":%s,"t":%s,"open":true}\n' "$GPID" "$(date +%s)" > "$HB.tmp" && mv "$HB.tmp" "$HB"
    sleep 2
  done
) &
HB_PID=$!
echo "心跳已启动 (writer pid=$HB_PID, 监控 game pid=$GPID)"
/bin/bash "$DEMO/slowroads_connect.sh" &
CONNECT_PID=$!

# ④ 等游戏窗口退出 → 自动切出
while kill -0 "$GPID" 2>/dev/null; do sleep 2; done
echo "游戏窗口已退出 → 自动切出"
kill "$HB_PID" 2>/dev/null || true
wait "$CONNECT_PID" 2>/dev/null || true
rm -f "$HB"
/bin/bash "$DEMO/slowroads_disconnect.sh"
echo "===== [$(date '+%F %T')] openpilot slowroads 会话结束 ====="
