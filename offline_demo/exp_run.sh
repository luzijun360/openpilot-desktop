#!/bin/bash
# [三连跑 2026-09-30] ANE 跳变定位实验 · 单次运行驱动器
# 用法: exp_run.sh <名称> <引擎> <计算单元>
#   exp_run.sh run1-metal tinygrad CPU_AND_NE   （tinygrad 忽略计算单元）
#   exp_run.sh run2-cpu   coreml  CPU_ONLY
#   exp_run.sh run3-ane   coreml  CPU_AND_NE
# 每轮：清场 → 先开记录器 → 起栈（同素材、去重/门关闭）→ 等视频播完 → 收记录器 → 停栈
set -u
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
VIDEO="/Users/lu/op项目of all/op方向的辅助驾驶方案/测试素材/ccb2fd17cf556fc2ccf4631c6963ea6f.mp4"
NAME="$1"; ENGINE="$2"; UNITS="${3:-CPU_AND_NE}"
EXP="$DEMO/logs/exp_20260930"
mkdir -p "$EXP"

echo "════ [$NAME] 引擎=$ENGINE 计算单元=$UNITS ════"
date '+开始: %H:%M:%S'

# 0) 清场（残留记录器 + 旧 ended.flag）
pkill -f "[j]ump_probe" 2>/dev/null || true
pkill -f "[c]url -sN --noproxy" 2>/dev/null || true
rm -f "$DEMO/ended.flag"

# 1) 先开记录器（早于栈启动，保证从第 0 帧开始录）
JP_OUT="$EXP/$NAME-probe.jsonl" JP_FRAMES="$EXP/$NAME-frames" \
  nohup /Users/lu/op项目of all/openpilot/.venv/bin/python3 "$DEMO/jump_probe.py" > "$EXP/$NAME-probe.log" 2>&1 &
PROBE_PID=$!
nohup curl -sN --noproxy '*' "http://127.0.0.1:8899/api/stream" > "$EXP/$NAME-sse.log" 2>&1 &
CURL_PID=$!
echo "记录器已启动 probe=$PROBE_PID curl=$CURL_PID"

# 2) 引擎设置（文件 + 环境双保险；环境优先）
echo "$ENGINE" > "$DEMO/model_backend.txt"

# 3) 起栈
cd "$DEMO"
OP_MODEL_BACKEND="$ENGINE" OP_COREML_UNITS="$UNITS" OP_CAM_SKIP_STATIC=0 OP_CAM_MIN_MOTION=0 \
  /bin/bash "$DEMO/op_app_launcher.sh" "$VIDEO" auto >> "$EXP/$NAME-launcher.log" 2>&1
echo "启动器已返回"

# 4) 等探针连上相机流（最多 120s）
OK=""
for i in $(seq 1 60); do
  if grep -q '"vipc": "connected"' "$EXP/$NAME-probe.jsonl" 2>/dev/null; then OK=1; echo "相机流已连上（等待 ${i}×2s）"; break; fi
  sleep 2
done
[ -z "$OK" ] && echo "⚠ 探针 120s 未连上相机流"

# 5) 等视频播完（ended.flag，最多 180s）
DONE=""
for i in $(seq 1 90); do
  if [ -f "$DEMO/ended.flag" ]; then DONE=1; echo "视频播完（第 ${i}×2s 检出）"; break; fi
  sleep 2
done
[ -z "$DONE" ] && echo "⚠ 180s 未见 ended.flag"
sleep 5

# 6) 收记录器
kill $PROBE_PID $CURL_PID 2>/dev/null || true
sleep 1
pkill -f "[j]ump_probe" 2>/dev/null || true
pkill -f "[c]url -sN --noproxy" 2>/dev/null || true

# 7) 停栈（只停栈，后端不动）
/bin/bash "$DEMO/op_app_launcher.sh" __STOP__ stop-only >> "$EXP/$NAME-launcher.log" 2>&1 || true
sleep 3

echo "════ [$NAME] 结束 ════"
echo "probe 记录: $(wc -l < "$EXP/$NAME-probe.jsonl" 2>/dev/null || echo 0) 行 | 帧图: $(ls "$EXP/$NAME-frames" 2>/dev/null | wc -l | tr -d ' ') 张"
date '+结束: %H:%M:%S'
