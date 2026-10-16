#!/usr/bin/env python3
"""生成「openpilot 网页版」app 图标 → web_app_icon.png (1024x1024)

设计：和原版控制台图标同一套暗色语言（深色圆角底 + 车道线），
但换成蓝青色调 + 地球/广播意象，一眼能分清是「网页版」。
"""
from PIL import Image, ImageDraw, ImageFilter

W = 1024
img = Image.new("RGBA", (W, W), (0, 0, 0, 0))

# ---- 圆角背景（垂直渐变，偏蓝）----
bg = Image.new("RGB", (W, W), (0, 0, 0))
bd = ImageDraw.Draw(bg)
top, bot = (16, 26, 44), (4, 7, 13)
for y in range(W):
    t = y / W
    bd.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
mask = Image.new("L", (W, W), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=225, fill=255)
img.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(img, "RGBA")

# ---- 地平线辉光（青）----
glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([W * 0.10, W * 0.50, W * 0.90, W * 0.90], fill=(40, 190, 230, 60))
glow = glow.filter(ImageFilter.GaussianBlur(85))
img.alpha_composite(glow)

# ---- 车道线（透视收束到地平线）----
HOR = int(W * 0.545)
d.line([(int(W * 0.50), HOR), (int(W * 0.20), W)], fill=(150, 165, 185, 105), width=11)
d.line([(int(W * 0.50), HOR), (int(W * 0.80), W)], fill=(150, 165, 185, 105), width=11)
for i, y in enumerate((0.63, 0.72, 0.83, 0.96)):
    sp = 0.06 + i * 0.075
    d.line([(int(W * (0.5 - sp)), int(W * y)), (int(W * (0.5 - sp * 0.55)), int(W * (y + 0.035)))],
           fill=(150, 165, 185, 90), width=7)
    d.line([(int(W * (0.5 + sp)), int(W * y)), (int(W * (0.5 + sp * 0.55)), int(W * (y + 0.035)))],
           fill=(150, 165, 185, 90), width=7)

# ---- 地球（青蓝渐变球体 + 经纬线）----
cx, cy, R = int(W * 0.50), int(W * 0.425), int(W * 0.235)

# 球体底色
sphere = Image.new("RGBA", (W, W), (0, 0, 0, 0))
sd = ImageDraw.Draw(sphere)
sd.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(20, 92, 132, 235))
sphere = sphere.filter(ImageFilter.GaussianBlur(2))
img.alpha_composite(sphere)

# 高光（左上）
hl = Image.new("RGBA", (W, W), (0, 0, 0, 0))
ImageDraw.Draw(hl).ellipse([cx - R * 0.72, cy - R * 0.82, cx + R * 0.30, cy + R * 0.02],
                           fill=(120, 225, 255, 70))
img.alpha_composite(hl.filter(ImageFilter.GaussianBlur(38)))

# 经纬线（裁剪在圆内）
grid = Image.new("RGBA", (W, W), (0, 0, 0, 0))
gd2 = ImageDraw.Draw(grid)
C = (128, 236, 255, 190)
lw = 7
for k in (0.34, 0.68):                                   # 经线
    rx = int(R * k)
    gd2.ellipse([cx - rx, cy - R, cx + rx, cy + R], outline=C, width=lw)
gd2.line([(cx, cy - R), (cx, cy + R)], fill=C, width=lw)
for k in (0.36, 0.72):                                   # 纬线
    ry = int(R * k * 0.62)
    half = int((R * R - ry * ry) ** 0.5)
    gd2.line([(cx - half, cy - ry), (cx + half, cy - ry)], fill=C, width=lw)
    gd2.line([(cx - half, cy + ry), (cx + half, cy + ry)], fill=C, width=lw)
cmask = Image.new("L", (W, W), 0)
ImageDraw.Draw(cmask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
grid.putalpha(Image.composite(grid.getchannel("A"), Image.new("L", (W, W), 0), cmask))
img.alpha_composite(grid)

# 球体外圈
d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(150, 240, 255, 235), width=9)

# ---- 右上广播弧（网页版 = 发出去）----
for i, rr in enumerate((0.115, 0.175, 0.235)):
    r = int(W * rr)
    bx, by = int(W * 0.775), int(W * 0.225)
    d.arc([bx - r, by - r, bx + r, by + r], start=205, end=335,
          fill=(70, 225, 175, 235 - i * 45), width=11)
d.ellipse([int(W * 0.775) - 13, int(W * 0.225) - 13, int(W * 0.775) + 13, int(W * 0.225) + 13],
          fill=(70, 235, 180, 255))

# ---- 底部小点阵（数据流）----
for i in range(7):
    x = int(W * (0.315 + i * 0.062))
    r = 9 if i % 2 == 0 else 6
    d.ellipse([x - r, int(W * 0.875) - r, x + r, int(W * 0.875) + r],
              fill=(90, 220, 255, 210 if i % 2 == 0 else 130))

img.save("web_app_icon.png")
print("已生成 web_app_icon.png (1024x1024)")
