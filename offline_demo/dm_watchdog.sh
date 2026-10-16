#!/bin/bash
# DM 守护进程：op 的 manager 只在全栈启动时拉起 dmonitoringmodeld，
# 运行中死掉不会重启（会导致面板显示冻住的旧数据）——这里每 5 秒检查一次。
cd /Users/lu/op项目of all/openpilot || exit 1
while true; do
  if ! pgrep -f "selfdrive.modeld.dmonitoringmodeld" > /dev/null 2>&1; then
    source .venv/bin/activate 2>/dev/null
    echo "[watchdog $(date '+%m-%d %H:%M:%S')] DM 不在，拉起新实例" >> /tmp/dm_watchdog.log
    nohup python3 -u -m openpilot.selfdrive.modeld.dmonitoringmodeld >> /tmp/dm_live.log 2>&1 &
  fi
  sleep 5
done
