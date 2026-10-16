// click_at.swift — 在指定屏幕坐标合成一次真实鼠标点击（用于点 WebGL 游戏里的按钮）
// 编译: swiftc -O click_at.swift -o click_at
// 用法: ./click_at <x> <y>        （x,y 是屏幕「点」坐标，原点左上角）
import Cocoa

let args = CommandLine.arguments
guard args.count >= 3, let x = Double(args[1]), let y = Double(args[2]) else {
  print("用法: click_at <x> <y>"); exit(1)
}
let p = CGPoint(x: x, y: y)
let src = CGEventSource(stateID: .hidSystemState)

CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
usleep(150_000)
CGEvent(mouseEventSource: src, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
usleep(70_000)
CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
print("clicked at \(Int(x)),\(Int(y))")
