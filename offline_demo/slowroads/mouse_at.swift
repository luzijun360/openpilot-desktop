// mouse_at.swift — 把鼠标移动到指定屏幕坐标（真实 mouseMoved 事件，游戏能收到）
// 用途：slowroads 支持鼠标转向（"Turn: Move mouse left/right"），openpilot 的控制指令
//       可以用它投射成鼠标位置，实现模拟量（非 0/1）的方向控制，避免画龙。
// 用法: ./mouse_at <x> <y>   （屏幕点坐标，原点左上角，与 click_at 一致）
import Cocoa

let a = CommandLine.arguments
guard a.count >= 3, let x = Double(a[1]), let y = Double(a[2]) else {
  print("用法: mouse_at <x> <y>")
  exit(1)
}
let pt = CGPoint(x: x, y: y)
if let ev = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                    mouseCursorPosition: pt, mouseButton: .left) {
  ev.post(tap: .cghidEventTap)
  print("moved to \(x),\(y)")
} else {
  print("事件创建失败")
  exit(1)
}
