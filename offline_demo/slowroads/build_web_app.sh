#!/bin/bash
# 构建「openpilot 网页版.app」—— 可重复执行（改了 web_app.swift 后重跑即可）
set -e
DEMO=/Users/lu/op项目of all/openpilot/offline_demo
APP="/Applications/openpilot 网页版.app"
BIN=openpilot-web

cd "$DEMO"

echo "① 编译 Swift 外壳…"
swiftc -O web_app.swift -o /tmp/$BIN -framework Cocoa -framework WebKit

echo "② 组装 app 包…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp /tmp/$BIN "$APP/Contents/MacOS/$BIN"
chmod +x "$APP/Contents/MacOS/$BIN"
[ -f web_app.icns ] && cp web_app.icns "$APP/Contents/Resources/app.icns"

echo "③ 写 Info.plist…"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key><string>openpilot 网页版</string>
  <key>CFBundleExecutable</key><string>openpilot-web</string>
  <key>CFBundleIconFile</key><string>app.icns</string>
  <key>CFBundleIdentifier</key><string>com.lu.openpilot-web</string>
  <key>CFBundleName</key><string>openpilot 网页版</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

echo "④ adhoc 签名…"
codesign --force --deep --sign - "$APP" 2>&1 | tail -2

echo "⑤ 校验…"
codesign -dv "$APP" 2>&1 | grep -E "Identifier|Signature"
plutil -p "$APP/Contents/Info.plist" | head -4
ls -la "$APP/Contents/MacOS/"
echo "✅ 构建完成：$APP"
