#!/usr/bin/env python3
"""生成「openpilot slowroads」App 图标（iconset → icns）。
设计：深色圆角方块 + 蜿蜒的道路（白边线 + 黄色中央虚线），与 slowroads 的公路主题呼应。
用法：/Users/lu/op项目of all/openpilot/.venv/bin/python3 make_slowroads_icon.py
"""
import math
import os
import shutil
import subprocess

from PIL import Image, ImageDraw

DEMO = "/Users/lu/op项目of all/openpilot/offline_demo"
ICONSET = f"{DEMO}/slowroads_app.iconset"
OUT = f"{DEMO}/slowroads_app.icns"
S = 1024


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 深色圆角背景（macOS 风格留边）
    pad = int(S * 0.06)
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=int(S * 0.22), fill=(13, 17, 23, 255))
    # 道路中心线：底部中间蜿蜒到顶部（S 形）
    pts = []
    for i in range(0, 101):
        t = i / 100.0
        y = (1 - t) * (S - pad * 2 - 60) + pad + 30
        x = S / 2 + math.sin(t * math.pi * 1.6) * S * 0.15
        pts.append((x, y))
    width = S * 0.14
    # 路面（深灰）
    band = [(x - width / 2, y) for (x, y) in pts] + [(x + width / 2, y) for (x, y) in reversed(pts)]
    d.polygon(band, fill=(38, 48, 62, 255))
    # 两侧白边线
    for off in (-width / 2, width / 2):
        d.line([(x + off, y) for (x, y) in pts], fill=(240, 246, 252, 255), width=10, joint="curve")
    # 中央黄色虚线
    for i in range(2, 98, 10):
        seg = pts[i:i + 5]
        if len(seg) >= 2:
            d.line(seg, fill=(255, 212, 89, 255), width=9, joint="curve")
    return img


def main() -> None:
    img = draw_icon()
    shutil.rmtree(ICONSET, ignore_errors=True)
    os.makedirs(ICONSET, exist_ok=True)
    specs = [("16x16", 16), ("16x16@2x", 32), ("32x32", 32), ("32x32@2x", 64),
             ("128x128", 128), ("128x128@2x", 256), ("256x256", 256), ("256x256@2x", 512),
             ("512x512", 512), ("512x512@2x", 1024)]
    for name, size in specs:
        img.resize((size, size), Image.LANCZOS).save(f"{ICONSET}/icon_{name}.png")
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", OUT], check=True)
    shutil.rmtree(ICONSET, ignore_errors=True)
    print(f"✅ 图标已生成：{OUT}")


if __name__ == "__main__":
    main()
