#!/usr/bin/env python3
"""
BeamNG 窗口自动跟踪抓屏

每 3 秒查询一次 BeamNG 窗口的位置和尺寸（通过 macOS Quartz API），
只要窗口被移动/缩放，就自动重启 ffmpeg 抓屏，让裁剪框始终对准游戏画面。

用法：用带 Quartz 的 python 运行（Hermes 自带的 venv 里已装好）
  /Users/lu/.hermes/hermes-agent/venv/bin/python3 watch_window.py
"""
import subprocess
import time

import Quartz

FF = "/Users/lu/.hermes/tools/ffmpeg-9.0.1-darwin-arm64/ffmpeg"
OUT = "/tmp/beamng_frames/frame.jpg"
SCALE = 2          # Retina 2x：Quartz 返回逻辑坐标，实际像素要乘 2
TITLE_BAR = 56     # 标题栏像素高度，裁掉
FPS = 12


def find_window():
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    for w in wins:
        owner = str(w.get("kCGWindowOwnerName", ""))
        title = str(w.get("kCGWindowName", ""))
        if "BeamNG" in owner or "BeamNG" in title:
            b = w.get("kCGWindowBounds", {})
            return (int(b.get("X", 0)), int(b.get("Y", 0)),
                    int(b.get("Width", 0)), int(b.get("Height", 0)))
    return None


def start_ffmpeg(bounds):
    x, y, w, h = [v * SCALE for v in bounds]
    y += TITLE_BAR
    h -= TITLE_BAR
    # 全部取偶数（编码器要求）
    x, y, w, h = x - x % 2, y - y % 2, w - w % 2, h - h % 2
    vf = f"crop={w}:{h}:{x}:{y},scale=1344:760"
    print(f"[watch] 窗口像素区域 {w}x{h}@{x},{y} → 启动抓屏", flush=True)
    return subprocess.Popen(
        [FF, "-sws_flags", "fast_bilinear", "-f", "avfoundation", "-framerate", str(FPS), "-i", "1:none",
         "-vf", vf, "-r", str(FPS), "-q:v", "14", "-update", "1", "-y", OUT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    proc = None
    cur = None
    while True:
        try:
            # ffmpeg 意外死亡（例如屏幕采集权被别的进程抢走）→ 重启
            if proc is not None and proc.poll() is not None:
                print(f"[watch] 抓屏进程退出（code={proc.returncode}），准备重启", flush=True)
                proc = None
                cur = None
            b = find_window()
            if b and b != cur:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                proc = start_ffmpeg(b)
                cur = b
            elif not b:
                print("[watch] 没找到 BeamNG 窗口（游戏最小化了？）", flush=True)
                cur = None
        except Exception as e:  # noqa: BLE001 — 守护脚本不能因为单次查询失败就退出
            print(f"[watch] 出错: {e}", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    main()
