// game_window.swift — 「网页游戏专用浏览器窗口」+ 自带截图输出 + 按键注入
// 用途：
//   1) 把网页游戏（如 slowroads.io）装进一个无边框窗口；
//   2) 以固定帧率把窗口内容截图写成 JPEG（供 openpilot 的「实时帧源」当摄像头输入）。
//      用 WKWebView 原生截图（takeSnapshot），与窗口位置/遮挡无关，也不需要屏幕录制权限。
//   3) 读 game_keys.json（由 op 控制指令投射而来），把按键事件投给自己 → 让 openpilot 控制游戏。
//      带死区保护：状态文件超过 1 秒没更新就全部松键（防止指令方挂掉后车一直加速）。
//
// 编译: swiftc -O game_window.swift -o game_window -framework WebKit
// 用法: ./game_window <url> [x y w h] [输出jpg] [帧率] [按键状态文件]
import Cocoa
import WebKit
import Vision

let args = CommandLine.arguments
let url = args.count > 1 ? args[1] : "https://slowroads.io/"
let px = Double(args.count > 2 ? args[2] : "1000") ?? 1000
let py = Double(args.count > 3 ? args[3] : "76") ?? 76
let pw = Double(args.count > 4 ? args[4] : "1880") ?? 1880
let ph = Double(args.count > 5 ? args[5] : "1176") ?? 1176
let outPath = args.count > 6 ? args[6] : "/Users/lu/op项目of all/openpilot/offline_demo/live_frame.jpg"
let fps = Double(args.count > 7 ? args[7] : "20") ?? 20
let keyFile = args.count > 8 ? args[8] : "/Users/lu/op项目of all/openpilot/offline_demo/game_keys.json"
let speedFile = args.count > 9 ? args[9] : "/Users/lu/op项目of all/openpilot/offline_demo/game_speed.json"
// 虚拟手柄被游戏读取的统计（写文件，方便外部验证游戏到底有没有在用手柄）  [虚拟手柄 2026-09-28]
let padStatsFile = args.count > 10 ? args[10] : "/Users/lu/op项目of all/openpilot/offline_demo/pad_stats.json"

// 每个动作对应的虚拟键码（只发方向键：↑↓ 管油门/刹车；左右转向改由鼠标控制，
// 因为 slowroads 的鼠标转向是模拟量，比键盘的 0/1 平滑得多，不会画龙）
let keyMap: [String: [CGKeyCode]] = [
  "down":  [125],       // ↓ / S
  "up":    [126],       // ↑ / W
]

// —— op 虚拟手柄：在页面内伪装成一个「标准映射」的 Gamepad ——  [虚拟手柄 2026-09-28]
// 背景：macOS 不允许普通程序创建虚拟 HID 设备（实测 IOHIDUserDeviceCreate 被拒，
// 需要 Apple 特批的 com.apple.developer.hid.virtual.device）。但游戏跑在我们自己的
// WKWebView 里 → 直接伪造 Gamepad API，游戏分辨不出来，且转向/油门/刹车都是连续量。
// Swift 侧以 30Hz 调 window.__opPad.set(steer, thr, brk) 推值。
// 附带「读取计数器」：游戏每读一次轴/键都记账 → 用来证明游戏真的在用手柄、用的是哪个轴。
let padShim = """
(function(){
  if (window.__opPad) return;
  var NB = 17;
  var st = { steer: 0, thr: 0, brk: 0 };
  var reads = { axes: [0,0,0,0], buttons: new Array(NB).fill(0), getGamepads: 0, events: 0, firstReadAt: 0, lastClick: "", dom: "" };
  function touch(){ if (!reads.firstReadAt) reads.firstReadAt = Date.now(); }
  var btnArr = [];
  for (var i = 0; i < NB; i++) (function(i){
    btnArr.push({
      get pressed(){ reads.buttons[i]++; touch(); return i===6 ? st.brk > 0.05 : (i===7 ? st.thr > 0.05 : false); },
      get touched(){ return false; },
      get value(){ reads.buttons[i]++; touch(); return i===6 ? st.brk : (i===7 ? st.thr : 0); }
    });
  })(i);
  var axesArr = [0,0,0,0];
  [0,1,2,3].forEach(function(i){
    Object.defineProperty(axesArr, i, {
      get: function(){ reads.axes[i]++; touch(); return i===0 ? -st.steer : (i===1 ? st.thr : 0); },
      enumerable: true
    });
  });
  var pad = {
    id: "op Virtual Wheel (STANDARD GAMEPAD)", index: 0, connected: true, mapping: "standard",
    get timestamp(){ return performance.now(); },
    get axes(){ return axesArr; },
    get buttons(){ return btnArr; },
    vibrationActuator: { playEffect: function(){ return Promise.resolve("complete"); }, reset: function(){ return Promise.resolve("complete"); } },
    hapticActuators: []
  };
  navigator.getGamepads = function(){
    reads.getGamepads++;
    if (reads.getGamepads <= 6){
      try {
        reads.stacks = reads.stacks || [];
        reads.stacks.push(String(new Error().stack || "").split("\\n").slice(1, 4).join(" | ").slice(0, 320));
      } catch(_){}
    }
    return [pad, null, null, null];
  };
  navigator.webkitGetGamepads = navigator.getGamepads;
  function announce(){
    reads.events++;
    try { var e = new Event("gamepadconnected"); e.gamepad = pad; window.dispatchEvent(e); } catch(_){}
  }
  window.addEventListener("load", announce);
  setTimeout(announce, 300); setTimeout(announce, 1500); setTimeout(announce, 4000);
  window.__opPad = {
    set: function(steer, thr, brk){
      st.steer = Math.max(-1, Math.min(1, steer || 0));
      st.thr   = Math.max(0, Math.min(1, thr || 0));
      st.brk   = Math.max(0, Math.min(1, brk || 0));
    },
    stats: function(){
      // 每次取统计时刷新页面文字（方便外部诊断当前在哪个菜单）  [合成点击 2026-09-29]
      try { reads.dom = (document.body && document.body.innerText || "").replace(/\\s+/g, " ").slice(0, 400); } catch(_){}
      return JSON.stringify(reads);
    },
    // [合成点击 2026-09-29] 在页面内某坐标合成一次鼠标点击（不碰真实鼠标/光标）：
    // 用于「开始游戏 / 恢复游戏」这类必须点一下的场景。
    click: function(x, y){
      try {
        var el = document.elementFromPoint(x, y) || document.body;
        var o = { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: 1, view: window };
        ["pointerdown","mousedown","pointerup","mouseup","click"].forEach(function(t){
          var E = (t.indexOf("pointer") === 0 && window.PointerEvent) ? window.PointerEvent : window.MouseEvent;
          el.dispatchEvent(new E(t, o));
        });
        reads.lastClick = "clicked " + (el.tagName || "?") + "#" + (el.id || "") + "." + (el.className || "").toString().slice(0,40) + "@" + Math.round(x) + "," + Math.round(y);
        reads.dom = (document.body && document.body.innerText || "").replace(/\\s+/g, " ").slice(0, 260);
        return reads.lastClick;
      } catch(e){ reads.lastClick = "err " + e; return reads.lastClick; }
    },
    // [按文字点击 2026-09-29] 找到文字匹配的元素并合成点击（比坐标可靠；用于操作游戏菜单）
    // 大小写不敏感（游戏标签是 CSS 大写）；取面积最小的匹配元素（最具体）
    clickText: function(t){
      try {
        var want = String(t).trim().toUpperCase(), best = null, bestA = 1e12;
        var all = document.querySelectorAll("*");
        for (var i = 0; i < all.length; i++){
          var el = all[i];
          var txt = (el.innerText || "").trim().toUpperCase();
          if (txt !== want) continue;
          var r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) continue;
          var a = r.width * r.height;
          if (a < bestA){ bestA = a; best = el; }
        }
        if (!best) { reads.lastClick = "未找到文字: " + t; return reads.lastClick; }
        var rb = best.getBoundingClientRect();
        var x = rb.x + rb.width / 2, y = rb.y + rb.height / 2;
        var o = { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: 1, view: window };
        ["pointerdown","mousedown","pointerup","mouseup","click"].forEach(function(ev){
          var E = (ev.indexOf("pointer") === 0 && window.PointerEvent) ? window.PointerEvent : window.MouseEvent;
          best.dispatchEvent(new E(ev, o));
        });
        reads.lastClick = "clickText '" + t + "' → " + best.tagName + "." + (best.className || "").toString().slice(0,30) + "@" + Math.round(x) + "," + Math.round(y);
        return reads.lastClick;
      } catch(e){ reads.lastClick = "err " + e; return reads.lastClick; }
    },
    pad: pad
  };
  console.log("[op] 虚拟手柄已注入");
})();
"""

final class GameWindow: NSWindow {
  // 无边框窗口默认 canBecomeKey=false → 用户键盘永远进不来。必须放开。
  override var canBecomeKey: Bool { true }
  override var canBecomeMain: Bool { true }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
  var window: GameWindow!
  var web: WKWebView!
  var timer: Timer?
  var busy = false
  var pressed: [String: Bool] = [:]
  var btnPressed: [String: Bool] = [:]
  var lastSteer: Double = 99.0
  var snapCount = 0

  func applicationDidFinishLaunching(_ note: Notification) {
    // 参数是「屏幕像素」，NSWindow 用「点」→ 按 backingScaleFactor 换算；
    // macOS 屏幕坐标原点在左下角，参数用「左上角原点」更好记，这里换算一下
    let screen = NSScreen.main
    let scale = screen?.backingScaleFactor ?? 2.0
    let screenHPoints = (screen?.frame.height ?? 900)
    let w = pw / scale, h = ph / scale
    let rect = NSRect(x: px / scale, y: screenHPoints - (py / scale) - h, width: w, height: h)

    window = GameWindow(contentRect: rect, styleMask: [.borderless], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false

    let cfg = WKWebViewConfiguration()
    cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
    // 持久化存储：游戏的设置/种子/车辆选择都存在 localStorage 里，必须用默认（磁盘）存储，
    // 否则每次打开都是全新环境（用户要求「下次打开还有设置记忆」）。
    cfg.websiteDataStore = WKWebsiteDataStore.default()
    // 虚拟手柄：在页面脚本之前注入（游戏启动时就能"看到"手柄）  [虚拟手柄 2026-09-28]
    cfg.userContentController.addUserScript(WKUserScript(source: padShim, injectionTime: .atDocumentStart, forMainFrameOnly: true))
    web = WKWebView(frame: NSRect(x: 0, y: 0, width: w, height: h), configuration: cfg)
    // 伪装成正常 Safari，避免 Cloudflare 拦截
    web.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    web.load(URLRequest(url: URL(string: url)!))

    window.contentView = web
    window.makeKeyAndOrderFront(nil)
    window.makeFirstResponder(web)
    NSApp.activate(ignoringOtherApps: true)

    startSnapshots()
    startKeyLoop()
    startPadLoop()      // 虚拟手柄推值循环  [虚拟手柄 2026-09-28]
    startPadStats()     // 手柄被读取情况统计（验证游戏真的在用）  [虚拟手柄 2026-09-28]
    print("[game_window] \(url) @ \(Int(px)),\(Int(py)) \(Int(pw))x\(Int(ph)) → \(outPath) @\(Int(fps))fps, keys=\(keyFile)")
  }

  // 定时把网页画面截成 JPEG，原子写入（先写 .tmp 再 rename，读方永远拿到完整文件）
  func startSnapshots() {
    let interval = 1.0 / max(1.0, fps)
    timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
      guard let self = self, !self.busy else { return }
      self.busy = true
      let conf = WKSnapshotConfiguration()
      // snapshotWidth 单位是「点」；乘回 scale 得到目标像素宽（默认 940 点 = 1880 像素）
      conf.snapshotWidth = NSNumber(value: Int(pw / (NSScreen.main?.backingScaleFactor ?? 2.0)))
      self.web.takeSnapshot(with: conf) { image, _ in
        defer { self.busy = false }
        guard let image = image,
              let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.72]) else { return }
        // 每 5 帧做一次车速 OCR（~4fps 足够，写 game_speed.json 给 op 桥接用）
        self.snapCount += 1
        if self.snapCount % 5 == 0, let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) {
          self.readSpeed(cg)
        }
        let tmp = outPath + ".tmp"
        do {
          try data.write(to: URL(fileURLWithPath: tmp))
          // POSIX rename 是原子替换
          if rename(tmp, outPath) != 0 {
            try? FileManager.default.removeItem(atPath: tmp)
          }
        } catch { /* 磁盘/权限问题：忽略这一帧 */ }
      }
    }
  }

  // 从画面右下角 OCR 读车速（形如 "10.9 KILOMETERS PER HOUR"），写 game_speed.json 供 op 桥接使用。
  // 这是「op 控制对不上」的根治：op 按假车速度算方向盘角，假车速度必须等于游戏里的真实车速。
  func readSpeed(_ cg: CGImage) {
    let w = CGFloat(cg.width), h = CGFloat(cg.height)
    // 车速区域：画面右下角（归一化坐标，CGImage 原点在左上）
    let rect = CGRect(x: w * 0.63, y: h * 0.79, width: w * 0.30, height: h * 0.10)
    guard let crop = cg.cropping(to: rect) else { return }
    let req = VNRecognizeTextRequest { [weak self] request, _ in
      guard let obs = request.results as? [VNRecognizedTextObservation] else { return }
      for o in obs {
        guard let t = o.topCandidates(1).first?.string else { continue }
        if let m = t.range(of: #"\d+\.\d+"#, options: .regularExpression),
           let kmh = Double(String(t[m])), kmh >= 0, kmh < 300 {
          self?.writeSpeed(kmh)
          break
        }
      }
    }
    req.recognitionLevel = .fast
    try? VNImageRequestHandler(cgImage: crop, options: [:]).perform([req])
  }

  func writeSpeed(_ kmh: Double) {
    let obj: [String: Any] = ["t": Date().timeIntervalSince1970, "kmh": kmh]
    guard let data = try? JSONSerialization.data(withJSONObject: obj) else { return }
    let tmp = speedFile + ".tmp"
    try? data.write(to: URL(fileURLWithPath: tmp))
    rename(tmp, speedFile)      // 原子替换
  }

  // —— 虚拟手柄：30Hz 把 op 的控制量推进页面 ——  [虚拟手柄 2026-09-28]
  // 只有 game_keys.json 里带 "pad":1 才走手柄；否则维持原来的鼠标/键盘方式（零回归）。
  var padOn = false
  var padMsgCount = 0
  var lastClickSeq = 0     // [合成点击 2026-09-29] 一次性合成点击的序列号
  func startPadLoop() {
    Timer.scheduledTimer(withTimeInterval: 0.033, repeats: true) { [weak self] _ in
      guard let self = self else { return }
      guard let attrs = try? FileManager.default.attributesOfItem(atPath: keyFile),
            let mtime = attrs[.modificationDate] as? Date,
            let data = try? Data(contentsOf: URL(fileURLWithPath: keyFile)),
            let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return }
      let isPad = ((obj["pad"] as? NSNumber)?.intValue ?? 0) != 0
      if isPad != self.padOn {
        self.padOn = isPad
        print("[game_window] 虚拟手柄模式 \(isPad ? "开（不再碰鼠标/键盘）" : "关")")
      }
      guard isPad else { return }
      var steer = (obj["steer"] as? NSNumber)?.doubleValue ?? 0
      var thr = (obj["throttle"] as? NSNumber)?.doubleValue ?? ((obj["up"] as? NSNumber)?.doubleValue ?? 0)
      var brk = (obj["brake"] as? NSNumber)?.doubleValue ?? ((obj["down"] as? NSNumber)?.doubleValue ?? 0)
      // 死区：指令文件 1 秒没更新（控制方挂了）→ 全部归零，防止车一直冲
      if Date().timeIntervalSince(mtime) >= 1.0 { steer = 0; thr = 0; brk = 0 }
      self.web.evaluateJavaScript("window.__opPad && window.__opPad.set(\(steer), \(thr), \(brk))", completionHandler: nil)
      self.padMsgCount += 1
      // [合成点击 2026-09-29] 一次性合成点击：JSON 里 {"click":[x,y],"clickSeq":N}，N 变了就点一次
      // （用于开始游戏 / 恢复游戏；纯页面内事件，不碰真实鼠标）
      // 也支持 {"clickText":"菜单文字","clickSeq":N}：按文字找元素再点（操作游戏菜单更可靠）
      let cseq = (obj["clickSeq"] as? NSNumber)?.intValue ?? 0
      if cseq != self.lastClickSeq {
        if let t = obj["clickText"] as? String, !t.isEmpty {
          self.lastClickSeq = cseq
          self.web.evaluateJavaScript("window.__opPad && window.__opPad.clickText(\(jsString(t)))") { res, _ in
            if let s = res as? String { print("[game_window] 按文字点击: \(s)") }
          }
        } else if let c = obj["click"] as? [Double], c.count == 2 {
          self.lastClickSeq = cseq
          self.web.evaluateJavaScript("window.__opPad && window.__opPad.click(\(c[0]), \(c[1]))") { res, _ in
            if let s = res as? String { print("[game_window] 合成点击: \(s)") }
          }
        }
      }
    }
  }

  // 把 Swift 字符串安全地转成 JS 字符串字面量（转义引号和反斜杠）
  func jsString(_ s: String) -> String {
    let esc = s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
    return "\"\(esc)\""
  }

  // 每 3 秒把「游戏读取手柄」的计数写进 pad_stats.json（同时打日志）
  // → 外部可以直接读文件验证游戏真的在用手柄、用的是哪个轴/键
  func startPadStats() {
    Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
      guard let self = self else { return }
      self.web.evaluateJavaScript("window.__opPad ? window.__opPad.stats() : ''") { res, _ in
        guard let s = res as? String, !s.isEmpty else { return }
        let line = "{\"t\": \(Date().timeIntervalSince1970), \"padOn\": \(self.padOn), \"pushed\": \(self.padMsgCount), \"reads\": \(s)}"
        try? line.write(toFile: padStatsFile, atomically: true, encoding: .utf8)
        print("[game_window] 手柄读取统计: \(s) (已推 \(self.padMsgCount) 帧)")
      }
    }
  }

  // 读按键状态文件 → 把按键事件投给自己（op 控制游戏）
  // 转向用鼠标（模拟量，slowroads 支持 "Turn: Move mouse left/right"）：
  // JSON 里的 "steer" ∈ [-1, +1]（+1 = 满左，与 op 的「正 = 左」一致）映射到窗口内 x 的 5%..95%
  func startKeyLoop() {
    Timer.scheduledTimer(withTimeInterval: 0.033, repeats: true) { [weak self] _ in
      guard let self = self else { return }
      var want: [String: Bool] = [:]
      var fresh = false
      var steer: Double = 0.0
      if let attrs = try? FileManager.default.attributesOfItem(atPath: keyFile),
         let mtime = attrs[.modificationDate] as? Date {
        fresh = Date().timeIntervalSince(mtime) < 1.0        // 死区：1 秒没更新就当指令方挂了
        if fresh, let data = try? Data(contentsOf: URL(fileURLWithPath: keyFile)),
           let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
          for (k, _) in keyMap { want[k] = ((obj[k] as? NSNumber)?.intValue ?? 0) != 0 }
          steer = (obj["steer"] as? NSNumber)?.doubleValue ?? 0.0
          steer = max(-1.0, min(1.0, steer))
        }
      }
      if !fresh { for (k, _) in keyMap { want[k] = false }; steer = 0.0 }   // 兜底：指令方挂了 → 松键回正

      // 手柄模式：不发鼠标/键盘事件（用户的鼠标不被占用）  [虚拟手柄 2026-09-28]
      if self.padOn { return }

      // —— 鼠标转向 ——
      if abs(steer - self.lastSteer) > 0.005 {
        self.lastSteer = steer
        let f = self.window.frame
        let screenH = NSScreen.main?.frame.height ?? 900
        let topY = screenH - (f.origin.y + f.height / 2)          // AppKit 左下原点 → CGEvent 左上原点
        let tx = f.origin.x + f.width * (0.5 - 0.45 * steer)      // steer +1（左）→ 窗口内 5%
        if let ev = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                            mouseCursorPosition: CGPoint(x: tx, y: topY), mouseButton: .left) {
          ev.post(tap: .cghidEventTap)
        }
      }

      for (name, codes) in keyMap {
        let w = want[name] ?? false
        let now = self.pressed[name] ?? false
        if w != now {
          self.pressed[name] = w
          let src = CGEventSource(stateID: .hidSystemState)
          for code in codes {
            CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: w)?.postToPid(getpid())
          }
        }
      }

      // 油门/刹车：鼠标模式下车键无效 → 用鼠标左右键（slowroads 鼠标控制：左键 = 前进，右键 = 后退）
      let btnMap: [(String, CGMouseButton, CGEventType, CGEventType)] = [
        ("up", .left, .leftMouseDown, .leftMouseUp),
        ("down", .right, .rightMouseDown, .rightMouseUp),
      ]
      for (name, btn, downType, upType) in btnMap {
        let w = want[name] ?? false
        let now = self.btnPressed[name] ?? false
        if w != now {
          self.btnPressed[name] = w
          let pt = CGEvent(source: nil)?.location ?? CGPoint(x: 0, y: 0)
          if let ev = CGEvent(mouseEventSource: nil, mouseType: w ? downType : upType,
                              mouseCursorPosition: pt, mouseButton: btn) {
            ev.post(tap: .cghidEventTap)
          }
        }
      }
    }
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
