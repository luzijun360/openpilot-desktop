#!/bin/bash
# 屏幕 → JPEG 实时帧源
# 把整个屏幕持续抓成 JPEG，供 openpilot 的「实时帧源」模式（ROAD_CAM=*.jpg）使用。
# camera.py 按文件更新时间取最新帧，所以这里就是不断覆盖同一个文件。
#
# 用法: live_screen.sh start|stop|status [输出jpg路径]
#       live_screen.sh testvideo <视频文件>   # 测试用：循环把视频写成 JPEG（验证链路，不抓屏）
#
# 依赖：ffmpeg（avfoundation "Capture screen 0" = 设备号 2）
# 注意：抓屏期间 macOS 菜单栏会出现录屏指示（紫点），停止后消失。

FF=/Users/lu/.hermes/tools/ffmpeg-9.0.1-darwin-arm64/ffmpeg
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
OUT="${2:-$DEMO/live_frame.jpg}"
PIDF="$DEMO/live_capture.pid"
LOG="$DEMO/logs/live_capture.log"
FPS="${LIVE_FPS:-20}"
W="${LIVE_W:-1928}"
H="${LIVE_H:-1208}"
SCREEN_DEV="${LIVE_SCREEN_DEV:-2}"   # ffmpeg avfoundation 设备号（Capture screen 0）

_launch() {   # $1=描述  $2...=ffmpeg 参数
  local desc="$1"; shift
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    echo "已在运行 pid=$(cat "$PIDF")（先 stop）"; exit 1
  fi
  rm -f "$OUT"
  nohup "$FF" -hide_banner -loglevel warning "$@" > "$LOG" 2>&1 &
  echo $! > "$PIDF"
  sleep 1.5
  if kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    echo "$desc 已启动 pid=$(cat "$PIDF")"
    echo "  帧输出: $OUT"
  else
    echo "$desc 启动失败，日志: $LOG"; tail -3 "$LOG"; exit 1
  fi
}

case "$1" in
  start)
    # LIVE_CROP="x:y:w:h" 可只抓屏幕的一块区域（比如游戏窗口），不设则抓全屏
    # 注意：fps 过滤器必须放最前 —— 屏幕采集以显示器刷新率（60fps）送来帧，
    # 先降到目标帧率再做裁剪/缩放/JPEG 编码，否则 CPU 会被烧穿（实测 561%）。
    if [ -n "$LIVE_CROP" ]; then
      _launch "抓屏(区域 $LIVE_CROP)" -f avfoundation -capture_cursor 0 -framerate "$FPS" -i "${SCREEN_DEV}:none" \
        -vf "fps=${FPS},crop=${LIVE_CROP},scale=${W}:-2" -q:v 5 -f image2 -update 1 -y "$OUT"
    else
      _launch "抓屏(全屏)" -f avfoundation -capture_cursor 0 -framerate "$FPS" -i "${SCREEN_DEV}:none" \
        -vf "fps=${FPS},scale=${W}:${H}" -q:v 5 -f image2 -update 1 -y "$OUT"
    fi
    ;;
  testvideo)
    SRC="$2"; [ -f "$SRC" ] || { echo "视频不存在: $SRC"; exit 1; }
    _launch "测试视频源($(basename "$SRC"))" -re -stream_loop -1 -i "$SRC" \
      -vf "scale=${W}:${H}" -q:v 5 -f image2 -update 1 -y "$OUT"
    ;;
  stop)
    if [ -f "$PIDF" ]; then
      P=$(cat "$PIDF"); kill "$P" 2>/dev/null; sleep 0.5; kill -9 "$P" 2>/dev/null; rm -f "$PIDF"
      echo "已停止 (pid=$P)"
    else
      echo "没有在运行"
    fi
    ;;
  status)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "运行中 pid=$(cat "$PIDF")"
      ls -l "$OUT" 2>/dev/null | awk '{printf "  帧文件: %s  %s bytes  %s %s %s\n", $9, $5, $6, $7, $8}'
    else
      echo "未运行"
    fi
    ;;
  *)
    echo "用法: $0 start|stop|status [输出jpg]  |  $0 testvideo <视频文件>"
    exit 1
    ;;
esac
