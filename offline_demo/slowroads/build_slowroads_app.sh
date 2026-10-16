#!/bin/bash
# 构建「openpilot slowroads.app」—— 双击打开 slowroads 游戏 + 自动接入控制台（可重复执行）
# 图标：先生成 offline_demo/slowroads_app.icns（见 make_slowroads_icon.py），有则打进包
set -e
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
APP="/Applications/openpilot slowroads.app"

cd "$DEMO"

echo "① 组装 app 包…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$DEMO/slowroads_app_launcher.sh" "$APP/Contents/MacOS/slowroads-launcher"
chmod +x "$APP/Contents/MacOS/slowroads-launcher"
[ -f "$DEMO/slowroads_app.icns" ] && cp "$DEMO/slowroads_app.icns" "$APP/Contents/Resources/app.icns" || true

echo "② 写 Info.plist…"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key><string>openpilot slowroads</string>
  <key>CFBundleExecutable</key><string>slowroads-launcher</string>
  <key>CFBundleIconFile</key><string>app.icns</string>
  <key>CFBundleIdentifier</key><string>com.lu.openpilot-slowroads</string>
  <key>CFBundleName</key><string>openpilot slowroads</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

echo "③ adhoc 签名…"
codesign --force --deep --sign - "$APP" 2>&1 | tail -1

echo "④ 校验…"
plutil -p "$APP/Contents/Info.plist" | grep -E "CFBundleIdentifier|CFBundleExecutable|LSUIElement"
ls -la "$APP/Contents/MacOS/"
echo "✅ 构建完成：$APP"
