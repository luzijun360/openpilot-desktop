#!/bin/bash
# 自测：模拟「openpilot 网页版.app」的生命周期（不开 GUI）
# 用法：bash test_web_lifecycle.sh
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
LOG="$DEMO/logs/web_app_lifecycle.log"
TS=/usr/local/bin/tailscale
cd "$DEMO" || exit 1

M="$(pgrep -f '[w]eb_app_launch.sh' | tr '\n' ' ')"
[ -n "$M" ] && { echo "已有实例在跑（$M），先清掉"; pkill -f '[w]eb_app_launch.sh'; sleep 4; }
touch "$LOG"
BEFORE=$(wc -l < "$LOG")
newlog() { tail -n +$((BEFORE + 1)) "$LOG"; }

echo "════════ 测试 1：打开 app（三样都已在跑 → 应全部「复用」）════════"
bash web_app_launch.sh &
LP=$!
sleep 6
newlog | sed 's/^/   /'
echo "   生命周期脚本 PID: $LP"
echo "   后端: $(pgrep -f '[c]onsole_server.py' | tr '\n' ' ')"
echo "   op 栈: $(pgrep -f '[r]un_offline_demo.sh' | wc -l | tr -d ' ') 个"
echo "   Tailscale 发布: $($TS serve status 2>/dev/null | grep -c -- '|-- /op ') 条（应为 1）"

echo
echo "════════ 测试 2：关闭 app（桌面版正在跑 → 只撤发布，后端+op 保留）════════"
kill -TERM $LP
sleep 8
newlog | tail -6 | sed 's/^/   /'
echo "   Tailscale 发布: $($TS serve status 2>/dev/null | grep -c -- '|-- /op ') 条（应为 0 = 已撤）"
echo "   后端: $(pgrep -f '[c]onsole_server.py' | tr '\n' ' ')（应还在）"
echo "   op 栈: $(pgrep -f '[r]un_offline_demo.sh' | wc -l | tr -d ' ') 个（应还在）"
echo "   脚本残留: $(pgrep -f '[w]eb_app_launch.sh' | wc -l | tr -d ' ')（应为 0）"

echo
echo "════════ 测试 3：桌面版不在时的分支（演练模式，不真停）════════"
BEFORE=$(wc -l < "$LOG")
WEB_APP_DESK_PAT="不存在的进程名XYZ" WEB_APP_DRY=1 bash web_app_launch.sh &
LP3=$!
sleep 6
kill -TERM $LP3
sleep 7
newlog | tail -7 | sed 's/^/   /'

echo
echo "════════ 测试 4：app 被强杀（看门狗应兜底清理）════════"
BEFORE=$(wc -l < "$LOG")
$TS serve --bg --https=10000 --set-path=/op http://127.0.0.1:8899 >/dev/null 2>&1   # 先挂上，好观察它被撤
bash -c "bash $DEMO/web_app_launch.sh" &
WRAP=$!
sleep 6
echo "   强杀前：发布 $($TS serve status 2>/dev/null | grep -c -- '|-- /op ') 条"
kill -9 $WRAP 2>/dev/null            # 模拟 .app 被强杀（生命周期脚本收不到 TERM）
sleep 8
newlog | tail -5 | sed 's/^/   /'
echo "   强杀后：发布 $($TS serve status 2>/dev/null | grep -c -- '|-- /op ') 条（应为 0 = 看门狗已兜底）"
echo "   脚本残留: $(pgrep -f '[w]eb_app_launch.sh' | wc -l | tr -d ' ')（应为 0）"

echo
echo "════════ 复原：重新挂上 Tailscale 发布 ════════"
$TS serve --bg --https=10000 --set-path=/op http://127.0.0.1:8899 >/dev/null 2>&1
$TS serve status 2>/dev/null | grep -- '|-- /op ' | sed 's/^/   /'
echo "   后端: $(pgrep -f '[c]onsole_server.py' | tr '\n' ' ')"
echo "   op 栈: $(pgrep -f '[r]un_offline_demo.sh' | wc -l | tr -d ' ') 个"
