#!/bin/bash
# BeamNG 控制测试工具（openpilot ↔ BeamNG 控制链路）
# 注意：控制文件必须写在游戏数据目录里，BeamNG 的 Lua 才读得到（相对路径解析到 userpath）。
#
# 用法:
#   ./set_control.sh 0.3 0 0      # 30% 油门
#   ./set_control.sh 0 0.5 0      # 50% 刹车
#   ./set_control.sh 0 0 0.2      # 方向盘右转 20%
#   ./set_control.sh off          # 全部松开（禁用）
#   ./set_control.sh status       # 只看当前状态

GAME_DATA="/Users/lu/Library/Application Support/CrossOver/Bottles/111/drive_c/users/crossover/AppData/Local/BeamNG.drive/0.22"
CTRL="$GAME_DATA/op_control.json"
STAT="$GAME_DATA/op_status.json"

case "$1" in
  off)
    printf '{"enabled": false, "throttle": 0.0, "brake": 0.0, "steering": 0.0}\n' > "$CTRL"
    echo "已禁用（所有控制归零）"
    ;;
  status)
    ;;
  "")
    echo "用法: $0 <油门 0-1> [刹车 0-1] [方向 -1~1]   |   $0 off   |   $0 status"
    ;;
  *)
    THR="$1"; BRK="${2:-0}"; STR="${3:-0}"
    printf '{"enabled": true, "throttle": %s, "brake": %s, "steering": %s}\n' "$THR" "$BRK" "$STR" > "$CTRL"
    echo "已设置: 油门=$THR 刹车=$BRK 方向=$STR"
    ;;
esac

echo "--- 控制文件 ---"
cat "$CTRL" 2>/dev/null || echo "(不存在)"
echo "--- 游戏回写状态 ---"
cat "$STAT" 2>/dev/null || echo "(游戏还没回写，检查 mod 是否加载)"
