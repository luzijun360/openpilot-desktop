#!/bin/bash
# ============================================================
# 双 app 生命周期逻辑自测（沙箱版，2026-09-30）
# 全部用桩：不碰真实后端 / 真实 op 栈 / 真实 Tailscale / 真实 app。
# 覆盖：
#   A 关桌面版、网页版还在      → 应保留（不拆共享资源）   ← 本次修复核心
#   B 保留后网页版也被强杀      → 20 秒兜底复查应自动收摊   ← 新增机制
#   C 桌面版单独关              → 应立即全停（旧行为不变）
#   D 关网页版、桌面版还在      → 只撤发布、共享资源保留（旧行为不变）
#   E 网页版单独关              → 撤发布 + 全停（旧行为不变）
#   F 两个几乎同时关（0.5 秒差）→ 后关的收摊
# 用法：bash test_dual_lifecycle.sh   （约 100 秒）
# ============================================================
set -u
T=/tmp/dual_test
SRC=/Users/lu/op项目of all/openpilot/offline_demo
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✅ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ❌ $1"; }
chk() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

rm -rf "$T"; mkdir -p "$T/logs"
cd "$SRC" || exit 1

echo "== 预检：真实后端（仅做只读探测，不会被停）=="
curl -s -m 2 --noproxy '*' -o /dev/null -w "   后端 HTTP %{http_code}\n" http://127.0.0.1:8899/api/status || true

# ---------- 1. 桩 ----------
cat > "$T/op_app_launcher.sh" <<'EOF'
#!/bin/bash
echo "[stub_launcher $(date '+%T')] $*" >> /tmp/dual_test/launcher_calls.log
exit 0
EOF
cat > "$T/ts_stub" <<'EOF'
#!/bin/bash
echo "[ts_stub $(date '+%T')] $*" >> /tmp/dual_test/ts_calls.log
if [ "$1" = "serve" ] && [ "$2" = "status" ]; then
  echo "  |-- /op proxy http://127.0.0.1:8899"
fi
exit 0
EOF
chmod +x "$T/op_app_launcher.sh" "$T/ts_stub"

# ---------- 2. 从真实脚本生成测试副本（桩掉一切副作用）----------
sed -e 's|^DEMO=/Users/lu/op项目of all/openpilot/offline_demo|DEMO=/tmp/dual_test|' \
    -e 's|^LOGS="$DEMO/logs"|LOGS=/tmp/dual_test/logs|' \
    -e 's|^LOG="$LOGS/app_lifecycle.log"|LOG="/tmp/dual_test/desk_lifecycle.log"|' \
    -e 's|nohup /Users/lu/op项目of all/openpilot/.venv/bin/python3 offline_demo/console_server.py|true offline_demo/console_server_TEST.py|g' \
    -e 's|offline_demo/\[c\]onsole_server\.py|offline_demo/[c]onsole_server_TEST_none.py|g' \
    -e 's|offline_demo/console_server\.py|offline_demo/console_server_TEST_none.py|g' \
    -e 's|\[c\]onsole_app_launch\.sh|[c]onsole_app_launch_TEST.sh|g' \
    -e 's|\[w\]eb_app_launch\.sh|[w]eb_app_launch_TEST.sh|g' \
    -e 's|openpilot-console|bash|' \
    console_app_launch.sh > "$T/console_app_launch_TEST.sh"

sed -e 's|^DEMO=/Users/lu/op项目of all/openpilot/offline_demo|DEMO=/tmp/dual_test|' \
    -e 's|^LOGS="$DEMO/logs"|LOGS=/tmp/dual_test/logs|' \
    -e 's|^LOG="$LOGS/web_app_lifecycle.log"|LOG="/tmp/dual_test/web_lifecycle.log"|' \
    -e 's|^TS=/usr/local/bin/tailscale|TS=/tmp/dual_test/ts_stub|' \
    -e 's|nohup /Users/lu/op项目of all/openpilot/.venv/bin/python3 offline_demo/console_server.py|true offline_demo/console_server_TEST.py|g' \
    -e 's|offline_demo/\[c\]onsole_server\.py|offline_demo/[c]onsole_server_TEST_none.py|g' \
    -e 's|offline_demo/console_server\.py|offline_demo/console_server_TEST_none.py|g' \
    -e 's|\[c\]onsole_app_launch\.sh|[c]onsole_app_launch_TEST.sh|g' \
    -e 's|\[w\]eb_app_launch\.sh|[w]eb_app_launch_TEST.sh|g' \
    web_app_launch.sh > "$T/web_app_launch_TEST.sh"

# 构建校验（防脚本结构变化导致 sed 悄悄失效；负向检查防真实 pkill 模式漏杀真实后端）
for f in "$T/console_app_launch_TEST.sh" "$T/web_app_launch_TEST.sh"; do
  grep -q "DEMO=/tmp/dual_test" "$f" || { echo "sed 构建失败: $f 缺 DEMO"; exit 1; }
  grep -q "onsole_server_TEST_none" "$f" || { echo "sed 构建失败: $f 缺 pkill 桩"; exit 1; }
  grep -q "\[c\]onsole_app_launch_TEST.sh" "$f" || { echo "sed 构建失败: $f 缺 [c] 模式"; exit 1; }
  grep -q "\[w\]eb_app_launch_TEST.sh" "$f" || { echo "sed 构建失败: $f 缺 [w] 模式"; exit 1; }
  grep -q 'offline_demo/console_server\.py' "$f" && { echo "sed 构建失败: $f 仍有真实 pkill 模式（危险）"; exit 1; }
  grep -q 'offline_demo/\[c\]onsole_server\.py' "$f" && { echo "sed 构建失败: $f 仍有真实 bracketed pkill 模式（危险）"; exit 1; }
done
grep -q "openpilot-console" "$T/console_app_launch_TEST.sh" && { echo "sed 构建失败: APP_COMM 未替换"; exit 1; }
echo "   桩与测试副本构建完成 ✓"
echo

reset_logs()   { : > "$T/desk_lifecycle.log"; : > "$T/web_lifecycle.log"; : > "$T/launcher_calls.log"; : > "$T/ts_calls.log"; }
stop_all_fakes() { pkill -9 -f "[c]onsole_app_launch_TEST.sh" 2>/dev/null; pkill -9 -f "[w]eb_app_launch_TEST.sh" 2>/dev/null; sleep 1; }
# 假 app（bash -c 包裹防 exec 优化）。注意：输出必须重定向到 /dev/null——
# 否则后台进程会占住 $( ) 的管道，命令替换永远不返回（实测卡死过一次）。
start_fake()   { bash -c "bash $1 & wait" >/dev/null 2>&1 & echo $!; }
trap 'pkill -9 -f "[c]onsole_app_launch_TEST.sh" 2>/dev/null; pkill -9 -f "[w]eb_app_launch_TEST.sh" 2>/dev/null' EXIT

# ============================================================
echo "════════ 场景 A：关桌面版、网页版还在 → 应保留（视频不中断）════════"
reset_logs
FW=$(start_fake "$T/web_app_launch_TEST.sh")
FD=$(start_fake "$T/console_app_launch_TEST.sh")
sleep 3
echo "   杀掉桌面版假 app（网页版保持开着）…"
kill $FD 2>/dev/null
sleep 12
echo "   ——桌面版日志——"; tail -6 "$T/desk_lifecycle.log" | sed 's/^/     /'
chk "桌面版判定「保留」"     "grep -q '网页版 app 在运行 → 后端与 op 全栈保留' '$T/desk_lifecycle.log'"
chk "没有停栈调用"           "! grep -q '__STOP__' '$T/launcher_calls.log'"
chk "cleanup 完成（保留）"   "grep -q 'cleanup 完成（保留）' '$T/desk_lifecycle.log'"

echo
echo "════════ 场景 B：保留后网页版也被强杀 → 20 秒兜底复查自动收摊 ════════"
pkill -9 -f "[w]eb_app_launch_TEST.sh" 2>/dev/null
sleep 24
echo "   ——桌面版日志尾部——"; tail -4 "$T/desk_lifecycle.log" | sed 's/^/     /'
echo "   ——桩启动器调用——"; tail -3 "$T/launcher_calls.log" | sed 's/^/     /'
chk "兜底复查触发"           "grep -q '兜底复查：两个 app 都已不在 → 停共享资源' '$T/desk_lifecycle.log'"
chk "兜底复查有停栈调用"     "grep -q '__STOP__' '$T/launcher_calls.log'"
stop_all_fakes

echo
echo "════════ 场景 C：桌面版单独关 → 应立即全停（旧行为不变）════════"
reset_logs
FD=$(start_fake "$T/console_app_launch_TEST.sh")
sleep 3
kill $FD 2>/dev/null
sleep 9
chk "判定全停"               "grep -q '网页版未运行 → 停 op 全栈 + 停后端' '$T/desk_lifecycle.log'"
chk "有停栈调用"             "grep -q '__STOP__' '$T/launcher_calls.log'"
stop_all_fakes

echo
echo "════════ 场景 D：关网页版、桌面版还在 → 只撤发布、共享资源保留 ════════"
reset_logs
FD=$(start_fake "$T/console_app_launch_TEST.sh")
FW=$(start_fake "$T/web_app_launch_TEST.sh")
sleep 3
kill $FW 2>/dev/null
sleep 12
echo "   ——网页版日志——"; tail -7 "$T/web_lifecycle.log" | sed 's/^/     /'
chk "撤了 Tailscale 发布"    "grep -q '已撤 Tailscale 发布' '$T/web_lifecycle.log'"
chk "桌面版在 → 保留"        "grep -q '桌面版 app 在运行 → 后端与 op 全栈保留' '$T/web_lifecycle.log'"
chk "没有停栈调用"           "! grep -q '__STOP__' '$T/launcher_calls.log'"
stop_all_fakes

echo
echo "════════ 场景 E：网页版单独关 → 撤发布 + 全停（旧行为不变）════════"
reset_logs
FW=$(start_fake "$T/web_app_launch_TEST.sh")
sleep 3
kill $FW 2>/dev/null
sleep 9
chk "撤发布"                 "grep -q '已撤 Tailscale 发布' '$T/web_lifecycle.log'"
chk "全停"                   "grep -q '桌面版未运行 → 停 op 全栈 + 停后端' '$T/web_lifecycle.log'"
chk "有停栈调用"             "grep -q '__STOP__' '$T/launcher_calls.log'"
stop_all_fakes

echo
echo "════════ 场景 F：两个几乎同时关（0.5 秒差）→ 后关的收摊 ════════"
reset_logs
FD=$(start_fake "$T/console_app_launch_TEST.sh")
FW=$(start_fake "$T/web_app_launch_TEST.sh")
sleep 3
kill $FD 2>/dev/null; sleep 0.5; kill $FW 2>/dev/null
sleep 30
echo "   ——桌面版日志——"; tail -5 "$T/desk_lifecycle.log" | sed 's/^/     /'
echo "   ——网页版日志——"; tail -5 "$T/web_lifecycle.log" | sed 's/^/     /'
chk "有一方收摊（直接或兜底）" "grep -qE '由本脚本收摊|cleanup 完成（全停）|兜底复查：两个 app 都已不在' '$T/desk_lifecycle.log' '$T/web_lifecycle.log'"
chk "收摊方有停栈调用"       "grep -q '__STOP__' '$T/launcher_calls.log'"
chk "两边脚本都已收尾"       "grep -q 'cleanup 完成' '$T/desk_lifecycle.log' && grep -q 'cleanup 完成' '$T/web_lifecycle.log'"
stop_all_fakes

echo
echo "════════════════ 结果：$PASS 过 / $FAIL 败 ════════════════"
if [ "$FAIL" -eq 0 ]; then echo "全部通过 ✅"; else echo "有失败 ❌（日志在 $T/）"; fi
