#!/bin/bash
# 把任意视频处理成 openpilot 模型需要的 1928x1208 @ 20fps
# （PC 端 DEVICE_CAMERAS[("pc","unknown")] 的内参就是按 1928x1208 算的，分辨率必须对齐）
#
# 用法: ./prepare_video.sh <输入视频> [输出视频]
set -e
IN="${1:?用法: $0 <输入视频> [输出视频]}"
OUT="${2:-/Users/lu/op项目of all/openpilot/offline_demo/test_1928x1208.mp4}"

ffmpeg -y -i "$IN" \
  -vf "scale=1928:1208:force_original_aspect_ratio=increase,crop=1928:1208" \
  -r 20 -pix_fmt yuv420p -c:v libx264 -preset fast -crf 20 -an -movflags +faststart \
  "$OUT"

echo "输出: $OUT"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -show_entries format=duration -of default=nw=1 "$OUT"
