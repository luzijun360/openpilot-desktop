#!/bin/bash
# 离线视频 → comma 风格可视化线条：一键启动（假车 + webcamerad 视频 + 全栈 manager）
#
# 用法: ./run_offline_demo.sh [视频文件]
#       视频需先处理为 1928x1208@20fps（见 prepare_video.sh），默认用 test_1928x1208.mp4
set -e
cd /Users/lu/op项目of all/openpilot
source .venv/bin/activate

VIDEO="${1:-/Users/lu/op项目of all/openpilot/offline_demo/test_1928x1208.mp4}"
[ -f "$VIDEO" ] || { echo "视频不存在: $VIDEO"; exit 1; }

SCRATCH="${SCRATCH:-/Users/lu/.hermes/cache/scratch}"
export TERM="${TERM:-xterm-256color}"   # 从 GUI（.app）启动时没有 TERM，ncurses 会崩

export USE_WEBCAM=1
export ROAD_CAM="$VIDEO"
export SIMULATION=1
export NOBOARD=1
export SKIP_FW_QUERY=1
export PASSIVE=0
export BIG=1          # 用 comma 三经典大 UI（2160x1080 逻辑分辨率，自动缩放适配屏幕）
export FINGERPRINT=HONDA_CIVIC_2022
# [降占用补丁 2026-09-28] op 原生 UI 渲染帧率：默认 60 → 20（视频本身只有 20fps，肉眼无差别）
export FPS="${FPS:-20}"
# [推理帧率设置 2026-09-29] 推理帧率：控制台「推理帧率」写 infer_fps.txt；启动时读它（默认 10）
export VIDEO_OUT_FPS="${VIDEO_OUT_FPS:-$(cat /Users/lu/op项目of all/openpilot/offline_demo/infer_fps.txt 2>/dev/null || echo 10)}"
# [推理后端 2026-09-28] 模型推理后端：coreml = Apple 神经引擎（默认，modeld 占用约 15.7%）
#                      tinygrad = 原 Metal 路径（约 38%）。控制台「推理引擎」开关写的就是这个值。
export OP_MODEL_BACKEND="${OP_MODEL_BACKEND:-coreml}"
# modeld 启动时把实际使用的后端写进这个文件，控制台据此显示「现在跑在什么上」
export OP_MODEL_BACKEND_MARKER="${OP_MODEL_BACKEND_MARKER:-/Users/lu/op项目of all/openpilot/offline_demo/model_backend.running}"
export OP_CAM_DEBUG="${OP_CAM_DEBUG:-0}"   # [诊断 2026-09-28] 置 1 时相机每 2 秒打印耗时分布（默认关）
# [离线视频移植补丁] 把 op 原生 UI 画面按 JPEG 帧流出（控制台网页左上角内嵌显示），并隐藏原生窗口
export OP_STREAM_PATH="${OP_STREAM_PATH:-/Users/lu/op项目of all/openpilot/offline_demo/op_screen.jpg}"
export OP_STREAM_FPS="${OP_STREAM_FPS:-20}"
export OP_STREAM_W="${OP_STREAM_W:-1024}"
export OP_STREAM_H="${OP_STREAM_H:-512}"
export OP_STREAM_HIDDEN="${OP_STREAM_HIDDEN:-1}"
# [C2 补丁 2026-09-27] 网页点击转发文件：控制台网页把点击坐标写进去，UI 进程每帧读并合成触摸事件
export OP_CLICK_FILE="${OP_CLICK_FILE:-/Users/lu/op项目of all/openpilot/offline_demo/ui_click.json}"
# [已移除] 驾驶员监测功能已删除（2026-09-27）：不再打开 Mac 前置摄像头，摄像头灯不再常亮
# export DRIVER_CAM="${DRIVER_CAM:-0}"
# 前置摄像头不要 180° 翻转（WEBCAM_FLIP 默认对真实摄像头会翻，会把驾驶员画面倒过来）
export WEBCAM_FLIP="${WEBCAM_FLIP:-0}"
# 关掉真机摄像头/日志/麦克风/远程管理等无关进程（DM 两个进程不再拉黑：用 Mac 前置摄像头跑 op 原生驾驶员监测）
export BLOCK="camerad,loggerd,encoderd,micd,logmessaged,manage_athenad"

echo "== 预置参数（条款/培训/标定）=="
python3 -c "from openpilot.selfdrive.test.helpers import set_params_enabled; set_params_enabled()"
# [C2 补丁 2026-09-27] 预置「已确认实验模式」：让 onroad 右上角 experimental 按钮可点（网页点击即可切换实验模式）
python3 -c "from openpilot.common.params import Params; Params().put_bool('ExperimentalModeConfirmed', True)"
# [重新校准 2026-09-29] 用户点过控制台「重新校准」→ 删掉刚预置的假标定，让 op 从零开始真校准。
# （calibrationd 只在启动时读 CalibrationParams，所以必须在这里、栈起来之前处理）
# 恢复：控制台「恢复预置标定」按钮（会删掉这个 flag 并写回假标定）。
if [ -f "/Users/lu/op项目of all/openpilot/offline_demo/recalib.flag" ]; then
  python3 -c "from openpilot.common.params import Params; Params().remove('CalibrationParams')"
  echo "== 检测到 recalib.flag：本次不预置假标定 → op 将重新校准（需 >24km/h 直线素材）=="
fi

echo "== 启动假车桥接 =="
python3 offline_demo/fake_car_bridge.py > "$SCRATCH/op_fake_car.log" 2>&1 &
BRIDGE_PID=$!
trap 'kill $BRIDGE_PID 2>/dev/null || true' EXIT
echo "bridge pid=$BRIDGE_PID, 日志: $SCRATCH/op_fake_car.log"

echo "== 启动 manager（全栈，前台；Ctrl-C 退出）=="
cd openpilot/system/manager
./manager.py 2>&1 | tee "$SCRATCH/op_manager.log"
