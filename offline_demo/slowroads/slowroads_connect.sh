#!/bin/bash
# ============================================================
# slowroads 自动接入 —— 把 op 的画面源切到 slowroads 实时帧（全自动、幂等）
# 触发：
#   ① 「openpilot slowroads」App 打开时（App 启动器调用）
#   ② 控制台「重新接入」按钮
#   ③ 控制台 App 打开时发现 slowroads 在跑
# 流程：记下当前画面源 → 等游戏窗口出帧 → 走统一启动器（停旧栈 → 实时源起栈，约 40 秒）
# 测试钩子（沙箱自测用，生产不设）：
#   SLOWROADS_TEST_STACK_PAT / SLOWROADS_TEST_WAIT_N
# ============================================================
set -u
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
LOG="$DEMO/logs/slowroads_connect.log"
FRAME="$DEMO/live_frame.jpg"
LAUNCHER="$DEMO/op_app_launcher.sh"
LOCK="$DEMO/slowroads_connect.lock"
STACK_PAT="${SLOWROADS_TEST_STACK_PAT:-[o]ffline_demo/run_offline_demo.sh}"
WAIT_N="${SLOWROADS_TEST_WAIT_N:-40}"
mkdir -p "$DEMO/logs"
exec >>"$LOG" 2>&1
echo "===== [$(date '+%F %T')] slowroads_connect 开始 (pid=$$) ====="

# 并发锁：已有接入在进行中 → 直接退出（幂等）
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "已有接入在进行中（pid $(cat "$LOCK")）→ 退出"
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# 已经在实时源上跑着 → 无需重接
SRC=$(cat "$DEMO/last_video.txt" 2>/dev/null || true)
if [ "${SRC##*/}" = "live_frame.jpg" ] && pgrep -f "$STACK_PAT" >/dev/null 2>&1; then
  echo "已在 slowroads 实时源上运行 → 无需重接"
  exit 0
fi

# 记下接入前的画面源（断开时恢复）
printf '%s' "$SRC" > "$DEMO/slowroads_prev_video.txt"
echo "接入前画面源: ${SRC:-（无）}"

# 等游戏窗口写出新鲜帧（最多约 20 秒；没等到也继续 —— 起栈后帧到了自然会用上）
i=0
while [ "$i" -lt "$WAIT_N" ]; do
  if [ -f "$FRAME" ]; then
    MT=$(stat -f %m "$FRAME" 2>/dev/null || echo 0)
    if [ $(( $(date +%s) - MT )) -lt 5 ]; then
      echo "游戏窗口帧已就绪: $FRAME"
      break
    fi
  fi
  i=$((i + 1))
  sleep 0.5
done

echo "→ 走统一启动器（auto：停旧栈 + 实时源起栈）"
/bin/bash "$LAUNCHER" "$FRAME" auto
echo "===== [$(date '+%F %T')] slowroads_connect 完成 ====="
