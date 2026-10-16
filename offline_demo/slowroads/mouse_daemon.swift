// mouse_daemon.swift — 读 game_keys.json，把 op 的控制指令推成真实鼠标事件
//
// 背景：游戏窗口程序（GameWindow.app）内部合成鼠标事件会被 macOS 隐私权限（TCC）静默丢弃
//       （无边框 .app 没有输入监控权限）。而独立小进程从终端启动会继承终端/父进程的权限，
//       实测可正常推动游戏（鼠标转向已验证）。所以鼠标注入放在这个独立进程里。
//
// 职责：
//   steer ∈ [-1,+1]（+1 = 满左）→ 鼠标 x 位置（窗口内 5%..95%，线性映射）
//   up   = 1 → 按住鼠标左键（slowroads 鼠标模式：左键 = 前进）
//   down = 1 → 按住鼠标右键（右键 = 后退/刹车）
//   状态文件超过 1 秒没更新 → 全部松开 + 鼠标回正（安全兜底）
//
// 编译: swiftc -O mouse_daemon.swift -o mouse_daemon
// 用法: ./mouse_daemon [keyFile] [winX winY winW winH]   （窗口参数为屏幕点坐标）
import Cocoa

let args = CommandLine.arguments
let keyFile = args.count > 1 ? args[1] : "/Users/lu/op项目of all/openpilot/offline_demo/game_keys.json"
let wx = Double(args.count > 2 ? args[2] : "500") ?? 500
let wy = Double(args.count > 3 ? args[3] : "38") ?? 38
let ww = Double(args.count > 4 ? args[4] : "940") ?? 940
let wh = Double(args.count > 5 ? args[5] : "588") ?? 588

var lastSteer = 99.0
var upPressed = false
var downPressed = false

func postMouse(_ type: CGEventType, _ b: CGMouseButton) {
  let pt = CGEvent(source: nil)?.location ?? CGPoint(x: 0, y: 0)
  CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: pt, mouseButton: b)?
    .post(tap: .cghidEventTap)
}

func moveMouse(steer: Double) {
  let tx = wx + ww * (0.5 - 0.45 * steer)     // steer +1（左）→ 窗口内 5%
  let ty = wy + wh / 2
  CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
          mouseCursorPosition: CGPoint(x: tx, y: ty), mouseButton: .left)?
    .post(tap: .cghidEventTap)
}

// 返回 (steer, up, down)；文件不存在/过期返回 nil（走安全兜底）
func readState() -> (Double, Bool, Bool)? {
  guard let attrs = try? FileManager.default.attributesOfItem(atPath: keyFile),
        let mtime = attrs[.modificationDate] as? Date,
        Date().timeIntervalSince(mtime) < 1.0 else { return nil }
  guard let data = try? Data(contentsOf: URL(fileURLWithPath: keyFile)),
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
  let steer = max(-1.0, min(1.0, (obj["steer"] as? NSNumber)?.doubleValue ?? 0.0))
  let up = ((obj["up"] as? NSNumber)?.intValue ?? 0) != 0
  let down = ((obj["down"] as? NSNumber)?.intValue ?? 0) != 0
  return (steer, up, down)
}

print("[mouse_daemon] 监视 \(keyFile) → 窗口点(\(wx),\(wy)) \(ww)x\(wh)")

while true {
  if let (steer, up, down) = readState() {
    if abs(steer - lastSteer) > 0.004 {
      lastSteer = steer
      moveMouse(steer: steer)
    }
    if up != upPressed {
      upPressed = up
      postMouse(up ? .leftMouseDown : .leftMouseUp, .left)
    }
    if down != downPressed {
      downPressed = down
      postMouse(down ? .rightMouseDown : .rightMouseUp, .right)
    }
  } else {
    // 安全兜底：指令方挂了 → 松键 + 回正
    if upPressed { upPressed = false; postMouse(.leftMouseUp, .left) }
    if downPressed { downPressed = false; postMouse(.rightMouseUp, .right) }
    if lastSteer != 0.0 { lastSteer = 0.0; moveMouse(steer: 0.0) }
  }
  usleep(33000)   // ~30Hz
}
