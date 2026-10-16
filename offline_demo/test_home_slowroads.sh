#!/bin/bash
# ============================================================
# 自测：「slowroads App 自动接入 + 恢复到主页」新功能
#   （全桩沙箱 /tmp/slowroads_test，不碰真实系统；真实栈不用开）
#   ① 桥接主页开关（home.flag → _home_enabled）
#   ② slowroads_connect.sh：记源 + 等帧 + 调启动器 + 幂等
#   ③ slowroads_disconnect.sh：停桥 + 写主页/暂停 + 恢复上次源
#   ④ slowroads_app_launcher.sh：心跳 + 接入/断开回调（用假游戏进程）
#   ⑤ 后端新接口冒烟（import console_server 后直调新函数）
# 注意：假进程必须用 `bash -c 'exec -a 名字 sleep N'` ——
#   复制 /bin/sleep 改名会被 macOS 直接 SIGKILL（实测 Killed: 9）。
# 用法：bash test_home_slowroads.sh
# ============================================================
set -u
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

DEMO_REAL=/Users/lu/op项目of all/openpilot/offline_demo
PY=/Users/lu/op项目of all/openpilot/.venv/bin/python3
SB=/tmp/slowroads_test
rm -rf "$SB"; mkdir -p "$SB/logs"

echo "═══ ① 桥接主页开关（home.flag）═══"
cd /Users/lu/op项目of all/openpilot || exit 1
"$PY" - <<'PY' && ok "桥接 _home_enabled：无文件/1/0 三种情况全对" || bad "桥接主页开关测试失败"
import os, sys, tempfile
sys.path.insert(0, "/Users/lu/op项目of all/openpilot")
import offline_demo.fake_car_bridge as b
b.HOME_FLAG = tempfile.mktemp(suffix=".home.flag")
assert b._home_enabled() is False, "无文件时应为 False"
with open(b.HOME_FLAG, "w") as f: f.write("1")
assert b._home_enabled() is True, "flag=1 时应为 True"
with open(b.HOME_FLAG, "w") as f: f.write("0")
assert b._home_enabled() is False, "flag=0 时应为 False"
os.remove(b.HOME_FLAG)
PY

echo "═══ ② slowroads_connect.sh（接入）═══"
sed -e "s|^DEMO=.*|DEMO=$SB|" "$DEMO_REAL/slowroads_connect.sh" > "$SB/slowroads_connect.sh"
chmod +x "$SB/slowroads_connect.sh"
cat > "$SB/op_app_launcher.sh" <<EOF
#!/bin/bash
echo "LAUNCHER_CALLED args=[\$*]" >> "$SB/launcher_calls.txt"
EOF
chmod +x "$SB/op_app_launcher.sh"

# 场景 1：首次接入（上次源=视频；栈没跑）
touch "$SB/prev_video.mov"
echo "$SB/prev_video.mov" > "$SB/last_video.txt"
touch "$SB/live_frame.jpg"
export SLOWROADS_TEST_STACK_PAT="[n]o_such_stack_xyz"
export SLOWROADS_TEST_WAIT_N=2
bash "$SB/slowroads_connect.sh"
grep -q "LAUNCHER_CALLED args=\[.*live_frame.jpg auto\]" "$SB/launcher_calls.txt" 2>/dev/null \
  && ok "接入：调启动器（实时帧 + auto）" || bad "接入：启动器没被正确调用"
[ "$(cat "$SB/slowroads_prev_video.txt" 2>/dev/null)" = "$SB/prev_video.mov" ] \
  && ok "接入：记下接入前的源" || bad "接入：prev 没记对"

# 场景 2：幂等（已在实时源 + 栈在跑 → 不再调启动器）
echo "$SB/live_frame.jpg" > "$SB/last_video.txt"
bash -c 'exec -a fake_stack_proc sleep 20' &
FAKE_STACK=$!
sleep 0.5
export SLOWROADS_TEST_STACK_PAT="[f]ake_stack_proc"
rm -f "$SB/launcher_calls.txt"
bash "$SB/slowroads_connect.sh"
[ ! -f "$SB/launcher_calls.txt" ] && ok "接入：已在实时源 → 不重复启动（幂等）" || bad "接入：幂等失败（又调了启动器）"

echo "═══ ③ slowroads_disconnect.sh（切出）═══"
sed -e "s|^DEMO=.*|DEMO=$SB|" "$DEMO_REAL/slowroads_disconnect.sh" > "$SB/slowroads_disconnect.sh"
chmod +x "$SB/slowroads_disconnect.sh"
echo "$SB/live_frame.jpg" > "$SB/last_video.txt"
echo "$SB/prev_video.mov" > "$SB/slowroads_prev_video.txt"
bash -c 'exec -a fake_game_driver sleep 20' &
FAKE_DRV=$!
sleep 0.5
export SLOWROADS_TEST_DRIVER_PAT="[f]ake_game_driver"
bash "$SB/slowroads_disconnect.sh"
[ "$(cat "$SB/pause.flag" 2>/dev/null)" = "1" ] && ok "断开：写了暂停" || bad "断开：暂停没写"
[ "$(cat "$SB/home.flag" 2>/dev/null)" = "1" ] && ok "断开：写了主页模式" || bad "断开：主页模式没写"
[ "$(cat "$SB/last_video.txt")" = "$SB/prev_video.mov" ] && ok "断开：恢复了上次画面源" || bad "断开：last_video 没恢复"
sleep 0.3
kill -0 "$FAKE_DRV" 2>/dev/null && bad "断开：桥进程没被杀" || ok "断开：桥进程已停"
kill "$FAKE_STACK" 2>/dev/null || true

echo "═══ ④ slowroads_app_launcher.sh（App 开/关全流程）═══"
sed -e "s|^DEMO=.*|DEMO=$SB|" \
    -e "s|\[G\]ameWindow|[f]ake_game_proc|g" \
    -e "s|slowroads_connect.sh|connect_stub.sh|g" \
    -e "s|slowroads_disconnect.sh|disconnect_stub.sh|g" \
    "$DEMO_REAL/slowroads_app_launcher.sh" > "$SB/slowroads_app_launcher.sh"
chmod +x "$SB/slowroads_app_launcher.sh"
cat > "$SB/connect_stub.sh" <<EOF
#!/bin/bash
echo called >> "$SB/connect_called.txt"
EOF
cat > "$SB/disconnect_stub.sh" <<EOF
#!/bin/bash
echo called >> "$SB/disconnect_called.txt"
EOF
chmod +x "$SB/connect_stub.sh" "$SB/disconnect_stub.sh"
bash -c 'exec -a fake_game_proc sleep 6' &
FAKE_GAME=$!
sleep 0.5
export SLOWROADS_TEST_GAME_PAT="[f]ake_game_proc"
export SLOWROADS_TEST_OPEN=true
bash "$SB/slowroads_app_launcher.sh" &
WRAP=$!
sleep 2.5
if [ -f "$SB/slowroads_app.json" ] && grep -q '"open":true' "$SB/slowroads_app.json"; then
  ok "App：心跳已写（slowroads_app.json）"
else
  bad "App：心跳没写"
fi
[ -f "$SB/connect_called.txt" ] && ok "App：打开时触发自动接入" || bad "App：没触发接入"
sleep 6
[ -f "$SB/disconnect_called.txt" ] && ok "App：关闭后触发自动切出" || bad "App：没触发切出"
[ ! -f "$SB/slowroads_app.json" ] && ok "App：心跳已清" || bad "App：心跳残留"
wait "$WRAP" 2>/dev/null || true
kill "$FAKE_GAME" 2>/dev/null || true

echo "═══ ⑤ 后端新接口冒烟 ═══"
"$PY" - <<'PY' && ok "后端：新常量/函数/路由齐备" || bad "后端：冒烟失败"
import os, sys
os.chdir("/Users/lu/op项目of all/openpilot")
import importlib.util
spec = importlib.util.spec_from_file_location("cs", "/Users/lu/op项目of all/openpilot/offline_demo/console_server.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)   # 只加载模块级代码（不起服务）
assert cs.LIVE_FRAME.endswith("live_frame.jpg")
assert cs.HOME_FLAG.endswith("home.flag")
assert cs._slowroads_open() is False, "没有心跳时应为 False"
assert cs._home_mode() is False, "没有 flag 时应为 False"
src = open("/Users/lu/op项目of all/openpilot/offline_demo/console_server.py").read()
for key in ('"/api/home"', '"/api/slowroads_reconnect"', '"/api/gamestream"'):
    assert key in src, f"缺路由 {key}"
srcm = open("/Users/lu/op项目of all/openpilot/offline_demo/console_mobile.py").read()
assert '"/api/gameframe.jpg"' in srcm
assert "src=LIVE_FRAME" in srcm
PY

echo
echo "════════════════════════════════════"
echo "  结果：$PASS 过 / $FAIL 败"
echo "════════════════════════════════════"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
