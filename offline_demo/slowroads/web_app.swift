// openpilot 网页版 —— WKWebView 外壳
// 作用：① 启动生命周期脚本（保证后端 / op 全栈 / Tailscale 发布都在，缺什么补什么）
//       ② 用原生窗口显示「网页服务状态页」（本地地址 / Tailscale 地址 / 运行状态 / 报错状态）
//       ③ 关 app → 脚本收到 TERM → 按规则停服务（桌面版在用就只撤发布）
// 与「openpilot 控制台.app」完全独立：那个 app 的源码与脚本一行未改。
import Cocoa
import WebKit

let STATUS_URL = "http://127.0.0.1:8899/web"
let ALIVE_URL = "http://127.0.0.1:8899/api/status"
let LAUNCH_SCRIPT = "/Users/lu/op项目of all/openpilot/offline_demo/web_app_launch.sh"

func serverAlive() -> Bool {
  guard let url = URL(string: ALIVE_URL) else { return false }
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

// 后端没起来时的兜底页（状态页本身由后端提供，起不来就显示这个）
let FALLBACK_HTML = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>openpilot 网页版</title>
<style>
 body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
   background:#0b0e13;color:#e6edf3;font:14px/1.6 -apple-system,"PingFang SC",sans-serif}
 .box{text-align:center;max-width:460px;padding:32px}
 .ic{font-size:46px;margin-bottom:14px}
 h1{font-size:18px;margin:0 0 10px}
 p{color:#8b98a8;font-size:13px;margin:0 0 20px}
 button{font:inherit;font-size:14px;padding:10px 26px;border-radius:10px;cursor:pointer;
   background:#173a25;border:1px solid #256b41;color:#b6f7cd}
 button:hover{background:#1d4a30}
</style></head><body><div class="box">
 <div class="ic">⚠️</div>
 <h1>网页服务未启动</h1>
 <p>控制台后端没起来，状态页暂时读不到。<br>点下面的按钮重试；一直失败就看后端日志。</p>
 <button onclick="webkit.messageHandlers.retry.postMessage('')">重试连接</button>
</div></body></html>
"""

final class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandler {
  var window: NSWindow!
  var webView: WKWebView!
  var proc: Process?

  func applicationDidFinishLaunching(_ notification: Notification) {
    _ = NSApp.setActivationPolicy(.regular)

    // 标准主菜单：⌘Q 退出、⌘W 关窗、编辑菜单（⌘C/⌘V/⌘A）
    let mainMenu = NSMenu()

    let appItem = NSMenuItem(); mainMenu.addItem(appItem)
    let appMenu = NSMenu(); appItem.submenu = appMenu
    appMenu.addItem(withTitle: "关于 openpilot 网页版", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
    appMenu.addItem(.separator())
    appMenu.addItem(withTitle: "隐藏 openpilot 网页版", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
    appMenu.addItem(.separator())
    appMenu.addItem(withTitle: "退出 openpilot 网页版", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

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
    cfg.userContentController.add(self, name: "retry")
    webView = WKWebView(frame: .zero, configuration: cfg)
    webView.uiDelegate = self
    webView.navigationDelegate = self

    window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1020, height: 700),
                      styleMask: [.titled, .closable, .miniaturizable, .resizable],
                      backing: .buffered, defer: false)
    window.title = "openpilot 网页版"
    window.minSize = NSSize(width: 620, height: 480)
    window.isReleasedWhenClosed = false
    window.contentView = webView
    window.center()
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)

    DispatchQueue.global().async {
      NSLog("web: starting lifecycle script …")
      let p = Process()
      p.executableURL = URL(fileURLWithPath: "/bin/bash")
      p.arguments = [LAUNCH_SCRIPT]
      try? p.run()
      self.proc = p
      for _ in 0..<80 {                       // 最多等 40 秒
        if serverAlive() { break }
        Thread.sleep(forTimeInterval: 0.5)
      }
      DispatchQueue.main.async { self.loadStatus() }
    }
  }

  func loadStatus() {
    webView.load(URLRequest(url: URL(string: STATUS_URL)!))
  }

  // 状态页加载失败（后端没起来 / 中途挂了）→ 显示兜底页
  func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
    NSLog("web: status page failed: \(error.localizedDescription)")
    webView.loadHTMLString(FALLBACK_HTML, baseURL: nil)
  }
  func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
    webView.loadHTMLString(FALLBACK_HTML, baseURL: nil)
  }

  // 页面里的「打开」链接 → 交给默认浏览器，窗口本身只留状态页
  func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
               decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
    if navigationAction.navigationType == .linkActivated, let u = navigationAction.request.url {
      NSWorkspace.shared.open(u)
      decisionHandler(.cancel)
      return
    }
    decisionHandler(.allow)
  }

  // 兜底页的「重试连接」
  func userContentController(_ userContentController: WKUserContentController,
                             didReceive message: WKScriptMessage) {
    if message.name == "retry" {
      DispatchQueue.global().async {
        for _ in 0..<40 {
          if serverAlive() { break }
          Thread.sleep(forTimeInterval: 0.5)
        }
        DispatchQueue.main.async { self.loadStatus() }
      }
    }
  }

  // 关 app = 关网页版服务：终止生命周期脚本（它收到 TERM 后按规则清理）。
  // 发完信号立即返回，清理在后台继续；app 若被强杀，看门狗 3 秒内兜底。
  func applicationWillTerminate(_ notification: Notification) {
    if let p = proc, p.isRunning {
      p.terminate()
    }
  }

  // 让页面里的 alert/confirm 正常工作
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

  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
