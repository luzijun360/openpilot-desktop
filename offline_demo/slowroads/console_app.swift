// openpilot 控制台 —— WKWebView 外壳
// 作用：① 保证控制台后端在跑（若没跑则以子进程启动，继承 GUI 会话）
//       ② 用原生窗口显示控制台页面
// 为什么需要它：从非 GUI 会话（后台服务）直接 spawn openpilot 全栈时，
// raylib/GLFW 无法创建窗口（Failed to initialize platform）；经 .app 启动才有窗口权限。
import Cocoa
import WebKit

let CONSOLE_URL = "http://127.0.0.1:8899/"
let LAUNCH_SCRIPT = "/Users/lu/op项目of all/openpilot/offline_demo/console_app_launch.sh"
let STOP_SCRIPT = "/Users/lu/op项目of all/openpilot/offline_demo/op_app_launcher.sh"

func serverAlive() -> Bool {
  guard let url = URL(string: CONSOLE_URL + "api/status") else { return false }
  var req = URLRequest(url: url)
  req.timeoutInterval = 1.0
  let sem = DispatchSemaphore(value: 0)
  var ok = false
  let task = URLSession.shared.dataTask(with: req) { _, resp, _ in
    if let http = resp as? HTTPURLResponse, http.statusCode == 200 { ok = true }
    sem.signal()
  }
  task.resume()
  _ = sem.wait(timeout: .now() + 1.5)
  return ok
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate {
  var window: NSWindow!
  var webView: WKWebView!
  var proc: Process?

  func applicationDidFinishLaunching(_ notification: Notification) {
    _ = NSApp.setActivationPolicy(.regular)

    // [A3/B6 修复 2026-09-27] 补标准主菜单：⌘Q 退出、⌘W 关窗、编辑菜单（⌘C/⌘V/⌘A 复制粘贴）
    // 之前没有主菜单 → 键盘 ⌘Q 无效（用户反馈「软件无法 command+q 关闭」）。
    let mainMenu = NSMenu()

    let appItem = NSMenuItem(); mainMenu.addItem(appItem)
    let appMenu = NSMenu(); appItem.submenu = appMenu
    appMenu.addItem(withTitle: "关于 openpilot 控制台", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
    appMenu.addItem(.separator())
    appMenu.addItem(withTitle: "隐藏 openpilot 控制台", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
    appMenu.addItem(.separator())
    appMenu.addItem(withTitle: "退出 openpilot 控制台", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

    let editItem = NSMenuItem(); mainMenu.addItem(editItem)
    let editMenu = NSMenu(title: "编辑"); editItem.submenu = editMenu
    editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
    editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
    editMenu.addItem(.separator())
    editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
    editMenu.addItem(withTitle: "拷贝", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
    editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
    editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

    let winItem = NSMenuItem(); mainMenu.addItem(winItem)
    let winMenu = NSMenu(title: "窗口"); winItem.submenu = winMenu
    winMenu.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
    winMenu.addItem(withTitle: "关闭窗口", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")

    NSApp.mainMenu = mainMenu

    let cfg = WKWebViewConfiguration()
    cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
    webView = WKWebView(frame: .zero, configuration: cfg)
    webView.uiDelegate = self

    window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1600, height: 820),
                      styleMask: [.titled, .closable, .miniaturizable, .resizable],
                      backing: .buffered, defer: false)
    window.title = "openpilot 控制台"
    window.minSize = NSSize(width: 1200, height: 620)
    window.isReleasedWhenClosed = false
    window.contentView = webView
    window.center()
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)

    DispatchQueue.global().async {
      // 生命周期脚本：保证后端在跑 + 自动启动 op 全栈；app 退出时由它负责关停（关 app = 关 op）
      NSLog("console: starting lifecycle script …")
      let p = Process()
      p.executableURL = URL(fileURLWithPath: "/bin/bash")
      p.arguments = [LAUNCH_SCRIPT]
      try? p.run()
      self.proc = p
      for _ in 0..<80 {                       // 最多等 40 秒
        if serverAlive() { break }
        Thread.sleep(forTimeInterval: 0.5)
      }
      DispatchQueue.main.async {
        self.webView.load(URLRequest(url: URL(string: CONSOLE_URL)!))
      }
    }
  }

  // 关 app = 关 op：终止生命周期脚本（它收到 TERM 后停全栈 + 停后端）。
  // [迟钝修复 2026-09-27] 旧版在主线程同步等清理跑完（最多 12 秒）→ ⌘Q 反应迟钝。
  // 现在发完信号立即返回，清理在后台继续；app 若被强杀，看门狗 3 秒内兜底清理。
  func applicationWillTerminate(_ notification: Notification) {
    if let p = proc, p.isRunning {
      p.terminate()
    } else {
      let stop = Process()
      stop.executableURL = URL(fileURLWithPath: "/bin/bash")
      stop.arguments = [STOP_SCRIPT, "__STOP__", "stop-only"]
      try? stop.run()
    }
  }

  // 让页面里的 alert/confirm 正常工作（否则 WKWebView 会静默卡住）
  func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
               initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
    let a = NSAlert(); a.messageText = message; a.addButton(withTitle: "好"); a.runModal()
    completionHandler()
  }
  func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
               initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
    let a = NSAlert(); a.messageText = message
    a.addButton(withTitle: "确定"); a.addButton(withTitle: "取消")
    completionHandler(a.runModal() == .alertFirstButtonReturn)
  }
  func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
               defaultText: String?, initiatedByFrame frame: WKFrameInfo,
               completionHandler: @escaping (String?) -> Void) {
    completionHandler(nil)
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
