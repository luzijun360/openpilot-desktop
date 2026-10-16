#!/bin/bash
# ============================================================
# slowroads 断开 —— 「openpilot slowroads」App 关闭时自动切出：
#   ① 停「op 开 slowroads」控制桥（op 松手）
#   ② 暂停 + 主页模式（op 进 offroad → UI 渲染主页；实时帧停更后模型自然停推理）
#   ③ 恢复 last_video（避免下次启动误用已停更的实时帧）
# 触发：App 关闭（游戏窗口退出）时由其启动器调用；重复调用无害（幂等）
# 测试钩子（沙箱自测用，生产不设）：SLOWROADS_TEST_STACK_PAT / SLOWROADS_TEST_DRIVER_PAT
# ============================================================
set -u
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
LOG="$DEMO/logs/slowroads_connect.log"
STACK_PAT="${SLOWROADS_TEST_STACK_PAT:-[o]ffline_demo/run_offline_demo.sh}"
DRIVER_PAT="${SLOWROADS_TEST_DRIVER_PAT:-[g]ame_driver.py}"
mkdir -p "$DEMO/logs"
exec >>"$LOG" 2>&1
echo "===== [$(date '+%F %T')] slowroads_disconnect 开始 ====="

# ① 停控制桥（op 松手；没在跑就跳过）
if pkill -f "$DRIVER_PAT" 2>/dev/null; then
  echo "已停 slowroads 控制桥"
else
  echo "控制桥本来就没在跑"
fi

# ② 回主页：暂停 + 主页模式（栈没在跑就跳过 —— 等控制台打开时自己起主页栈）
if pgrep -f "$STACK_PAT" >/dev/null 2>&1; then
  echo 1 > "$DEMO/pause.flag"
  echo 1 > "$DEMO/home.flag"
  echo "已写 暂停 + 主页模式 → op 回主页"
else
  echo "栈没在跑（断开只做清理）"
fi

# ③ 恢复上次画面源记录
PREV=$(cat "$DEMO/slowroads_prev_video.txt" 2>/dev/null || true)
if [ -n "$PREV" ] && [ -f "$PREV" ]; then
  printf '%s' "$PREV" > "$DEMO/last_video.txt"
  echo "last_video 已恢复: ${PREV##*/}"
else
  echo "没有可恢复的上次画面源"
fi
echo "===== [$(date '+%F %T')] slowroads_disconnect 完成 ====="
