#!/usr/bin/env python3
"""生成「openpilot 控制台」图标：四宫格布局（左上大画面 + 右侧控制 + 底部两块），comma 风格。"""
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角底板（深色）
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=228, fill=(16, 21, 28, 255))
# 外框微光
d.rounded_rectangle([10, 10, S - 11, S - 11], radius=220, outline=(46, 58, 74, 255), width=6)

PAD = 74
GAP = 26
W = S - PAD * 2
# 四宫格：左 66% / 右 34%；上 76% / 下 24%
lw = int((W - GAP) * 0.66)
rw = W - GAP - lw
th = int((W - GAP) * 0.76)          # 注意用 W 保持接近正方形比例
bh = W - GAP - th
if bh < 150:                         # 保证底部够高
    bh = 150
    th = W - GAP - bh
x0, y0 = PAD, PAD
x1 = x0 + lw + GAP
y1 = y0 + th + GAP

def panel(x, y, w, h, fill=(22, 28, 37, 255)):
    d.rounded_rectangle([x, y, x + w, y + h], radius=26, fill=fill, outline=(40, 51, 66, 255), width=3)

# 左上：op 主机画面
panel(x0, y0, lw, th, (12, 16, 22, 255))
# 画面里的车道线（透视收敛）
cx = x0 + lw // 2
d.polygon([(cx - 40, y0 + 46), (cx - 250, y0 + th - 30), (cx - 300, y0 + th - 30), (cx - 120, y0 + 46)],
          fill=(210, 224, 238, 210))
d.polygon([(cx + 40, y0 + 46), (cx + 250, y0 + th - 30), (cx + 300, y0 + th - 30), (cx + 120, y0 + 46)],
          fill=(210, 224, 238, 210))
# 绿色行驶路径（中间）
d.polygon([(cx - 26, y0 + 60), (cx + 26, y0 + 60), (cx + 150, y0 + th - 40), (cx - 150, y0 + th - 40)],
          fill=(0, 210, 120, 190))
# 前车三角
d.polygon([(cx, y0 + th - 210), (cx - 34, y0 + th - 150), (cx + 34, y0 + th - 150)], fill=(228, 40, 40, 255))

# 右上：控制面板（按钮条）
panel(x1, y0, rw, th, (20, 26, 35, 255))
by = y0 + 40
for i in range(5):
    col = (0, 168, 96, 255) if i == 0 else (44, 56, 72, 255)
    d.rounded_rectangle([x1 + 34, by, x1 + rw - 34, by + 74], radius=18, fill=col)
    by += 100

# 左下：状态/指标
panel(x0, y1, lw, bh, (20, 26, 35, 255))
for i, wfrac in enumerate((0.5, 0.72, 0.36)):
    d.rounded_rectangle([x0 + 36, y1 + 34 + i * 44, x0 + 36 + int((lw - 72) * wfrac), y1 + 62 + i * 44],
                        radius=14, fill=(58, 74, 94, 255))

# 右下：日志
panel(x1, y1, rw, bh, (20, 26, 35, 255))
for i in range(3):
    d.rounded_rectangle([x1 + 34, y1 + 34 + i * 44, x1 + rw - 34 - i * 40, y1 + 62 + i * 44],
                        radius=14, fill=(44, 56, 72, 255))

img.save("/tmp/console_icon_1024.png")
print("已生成 /tmp/console_icon_1024.png")
