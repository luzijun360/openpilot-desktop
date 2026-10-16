#!/usr/bin/env python3
"""生成 .app 图标（comma 风格：暗色 UI + 车道线 + 绿色行驶路径）→ app_icon.png (1024x1024)"""
from PIL import Image, ImageDraw, ImageFilter

W = 1024
img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# ---- 圆角背景（垂直渐变）----
bg = Image.new("RGB", (W, W), (0, 0, 0))
bd = ImageDraw.Draw(bg)
top = (18, 26, 40)
bot = (5, 7, 11)
for y in range(W):
    t = y / W
    c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    bd.line([(0, y), (W, y)], fill=c)
mask = Image.new("L", (W, W), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=225, fill=255)
img.paste(bg, (0, 0), mask)

d = ImageDraw.Draw(img, "RGBA")

# ---- 地平线辉光 ----
glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([160, 300, 864, 520], fill=(90, 150, 255, 40))
glow = glow.filter(ImageFilter.GaussianBlur(60))
img.alpha_composite(Image.composite(glow, Image.new("RGBA", (W, W), (0, 0, 0, 0)), mask))

HX, HY = 512, 402          # 灭点
d.polygon([(HX - 26, HY), (HX + 26, HY), (HX + 780, W), (HX - 780, W)], fill=(35, 39, 48, 255))   # 路面
d.polygon([(HX - 8, HY), (HX + 8, HY), (HX + 300, W), (HX - 300, W)], fill=(42, 47, 58, 255))     # 本车道（略亮）

def lane(x_top, x_bot, w_top, w_bot, color):
    d.polygon([(x_top - w_top, HY + 6), (x_top + w_top, HY + 6),
               (x_bot + w_bot, W), (x_bot - w_bot, W)], fill=color)

# 白色车道线（左右）
lane(HX - 62, HX - 430, 3, 15, (232, 238, 248, 235))
lane(HX + 62, HX + 430, 3, 15, (232, 238, 248, 235))
lane(HX - 150, HX - 900, 2, 12, (170, 180, 196, 120))
lane(HX + 150, HX + 900, 2, 12, (170, 180, 196, 120))

# ---- 绿色行驶路径（带辉光）----
pg = Image.new("RGBA", (W, W), (0, 0, 0, 0))
pgd = ImageDraw.Draw(pg)
pgd.polygon([(HX - 16, HY + 20), (HX + 16, HY + 20), (HX + 74, W), (HX - 74, W)], fill=(62, 224, 110, 150))
pg = pg.filter(ImageFilter.GaussianBlur(18))
img.alpha_composite(pg)
d.polygon([(HX - 6, HY + 22), (HX + 6, HY + 22), (HX + 30, W), (HX - 30, W)], fill=(70, 236, 124, 255))

# ---- 自车位置（绿点）----
d.ellipse([HX - 34, 872, HX + 34, 940], fill=(12, 16, 22, 255))
d.ellipse([HX - 26, 880, HX + 26, 932], fill=(70, 236, 124, 255))

img.save("/Users/lu/op项目of all/openpilot/offline_demo/app_icon.png")
print("图标已生成: app_icon.png")
