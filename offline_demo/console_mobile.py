#!/usr/bin/env python3
"""手机 / iPad 版控制台后端扩展（2026-09-29）

设计原则
--------
1. **零依赖**：只用标准库 + 已有的 PIL（op venv 自带）。
2. **桌面版零改动**：本机直连（Host 为 127.0.0.1/localhost，且无 X-Forwarded-For）不要求登录，
   所有原有接口行为不变。新增逻辑只在 console_server.py 里插了 3 处调用。
3. **前缀归一化**：Tailscale `--set-path=/op` 是否剥掉前缀存在版本差异，
   这里两种都吃（`/op/api/fs` 与 `/api/fs` 等价），前端一律用相对 URL。
4. **远程根路径 → 手机版**：走 Tailscale 打开 `/op` 或 `/op/` 得到手机版页面；
   本机打开 `http://127.0.0.1:8899/` 仍是桌面版。

新增接口（全部带 [手机版 2026-09-29] 注释，便于回退）
  GET  /m                        手机 / iPad 自适应页面
  GET  /login                    登录页
  POST /login                    校验密码 → 下发签名 Cookie
  POST /api/logout               清除 Cookie
  GET  /api/fs?path=             网页内文件浏览（限允许根目录，越界 403）
  GET  /api/frame.jpg?w=&q=      op 画面单帧（缩放 / 降质，手机流用）
  POST /api/upload?name=         裸 body 流式写盘（手机上传视频）
  GET  /api/download?path=       文件下发到手机
"""

import hashlib
import hmac
import io
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
DEMO = "/Users/lu/op项目of all/openpilot/offline_demo"
OP_SCREEN = os.environ.get("OP_STREAM_PATH", f"{DEMO}/op_screen.jpg")
LIVE_FRAME = f"{DEMO}/live_frame.jpg"   # [slowroads App 自动接入 2026-09-30] 游戏实时帧源
PROJECT = "/Users/lu/op项目of all/op方向的辅助驾驶方案"
MATERIAL = f"{PROJECT}/测试素材"
UPLOAD_DIR = f"{MATERIAL}/手机上传"

PASS_FILE = "/Users/lu/.hermes/op_console_password"
KEY_FILE = "/Users/lu/.hermes/op_console_cookie.key"

PREFIX = "/op"                     # Tailscale 挂载前缀（浏览器可见的路径）
COOKIE_NAME = "op_auth"
COOKIE_MAX_AGE = 30 * 24 * 3600    # 30 天
MOBILE_HTML = f"{DEMO}/console_mobile.html"

# 允许浏览 / 下载的根目录（realpath 必须落在其中之一，否则 403）
ALLOWED_ROOTS = [
    PROJECT,
    "/Users/lu/Desktop",
    "/Users/lu/Downloads",
    "/Users/lu/Movies",
]
# 页面上的快捷入口
SHORTCUTS = [
    ("测试素材", MATERIAL),
    ("桌面", "/Users/lu/Desktop"),
    ("下载", "/Users/lu/Downloads"),
    ("影片", "/Users/lu/Movies"),
]
VIDEO_EXT = (".mov", ".mp4", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".flv", ".wmv")
FRAME_STALE_S = 6.0                # 源帧超过这个秒数视为陈旧 → 返回占位图
_FRAME_CACHE = {"key": None, "data": None}
_FRAME_LOCK = threading.Lock()

# --------------------------------------------------------------------------
# [网页版 app 2026-09-29] 网页服务状态（供「openpilot 网页版.app」的状态页显示）
# --------------------------------------------------------------------------
START_TS = time.time()
TAILSCALE_BIN = "/usr/local/bin/tailscale"
TS_PORT = "10000"                  # 仅 tailnet 的端口（443/8443 是公网 Funnel，禁用）
TS_PATH = "/op"
WEB_STATUS_HTML = f"{DEMO}/web_status.html"
CONSOLE_LOG = f"{DEMO}/logs/console.log"

_TS_CACHE = {"t": 0.0, "d": None}
_TS_LOCK = threading.Lock()
_PG_CACHE = {}
_PG_LOCK = threading.Lock()

# 这些是长连接客户端断开时的正常噪音，不算「报错」
_BENIGN = ("ConnectionResetError", "BrokenPipeError", "ConnectionAbortedError",
           "ClientDisconnected", "[Errno 54]", "[Errno 32]")
# 这些是噪音的伴随行，本身不代表错误
_SKIP_LINES = ("Traceback (most recent call last)", "Exception occurred during processing of request from")
_ERR_RE = re.compile(r"([\w.]*(?:Error|Exception)\b|失败|错误|报错)")


# --------------------------------------------------------------------------
# 密码与 Cookie
# --------------------------------------------------------------------------
def _read_password() -> str:
    try:
        with open(PASS_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _secret() -> bytes:
    """Cookie 签名密钥：持久化到 600 权限文件，重启后已登录的设备不掉线。"""
    try:
        with open(KEY_FILE, "rb") as f:
            k = f.read()
            if len(k) >= 32:
                return k
    except Exception:
        pass
    k = secrets.token_bytes(32)
    try:
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
    except Exception:
        pass
    return k


def _make_cookie() -> str:
    ts = str(int(time.time()))
    sig = hmac.new(_secret(), ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def _check_cookie(val: str) -> bool:
    try:
        ts, sig = (val or "").split(".", 1)
        want = hmac.new(_secret(), ts.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, want):
            return False
        return (time.time() - int(ts)) < COOKIE_MAX_AGE
    except Exception:
        return False


def _cookie_value(handler) -> str:
    raw = handler.headers.get("Cookie") or ""
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE_NAME:
            return v
    return ""


def _set_cookie_header(handler, value: str, max_age: int) -> None:
    handler.send_header(
        "Set-Cookie",
        f"{COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Strict",
    )


# --------------------------------------------------------------------------
# 本机 / 远程 判定 与 路径归一化
# --------------------------------------------------------------------------
def _is_remote(handler) -> bool:
    """走 Tailscale 进来的请求视为远程。

    判据（任一命中即远程）：有 X-Forwarded-For（tailscale serve 会加），
    或 Host 不是本机形式。两者都用上，避免单一头部缺失导致误判。
    """
    if handler.headers.get("X-Forwarded-For"):
        return True
    host = (handler.headers.get("Host") or "").split(":")[0].strip().lower()
    return host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]")


def _is_local(handler) -> bool:
    return not _is_remote(handler)


def resolve(handler, p: str) -> str:
    """[手机版 2026-09-29] 前缀归一化 + 远程根路径路由到手机版。

    - `/op/xxx` 与 `/xxx` 等价（兼容 --set-path 剥/不剥前缀两种行为）
    - `/op`、`/op/`、远程的 `/` → `/m`（手机版）
    - 去掉尾部斜杠，保证页面里相对 URL 的解析基准稳定
    """
    if p == PREFIX or p.startswith(PREFIX + "/"):
        p = p[len(PREFIX):] or "/"
    if p in ("", "/", "/index.html") and _is_remote(handler):
        return "/m"
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/") or "/"
    return p or "/"


def guard(handler, p: str) -> bool:
    """[手机版 2026-09-29] 远程请求的登录守卫。本机直连直接放行。

    返回 True = 放行；False = 已自行回复（401 或 302 到登录页）。
    """
    if _is_local(handler):
        return True
    if p in ("/login", "/api/login", "/favicon.ico"):
        return True
    if _check_cookie(_cookie_value(handler)):
        return True

    if p.startswith("/api/") or p.endswith((".jpg", ".jpeg", ".png")):
        handler._send(401, {"ok": False, "error": "未登录或登录已过期", "need_login": True})
    else:
        loc = f"{PREFIX}/login?next={urllib.parse.quote(p)}"
        handler.send_response(302)
        handler.send_header("Location", loc)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
    return False


# --------------------------------------------------------------------------
# 文件浏览
# --------------------------------------------------------------------------
def _under_allowed(path: str):
    """realpath 必须落在允许根目录内，返回 realpath 或 None。"""
    try:
        real = os.path.realpath(path)
    except Exception:
        return None
    for root in ALLOWED_ROOTS:
        r = os.path.realpath(root)
        if real == r or real.startswith(r + os.sep):
            return real
    return None


def _fs_listing(path: str) -> dict:
    if not path:
        path = MATERIAL
    real = _under_allowed(path)
    if real is None:
        return {"ok": False, "error": "路径不在允许范围内", "code": 403}
    if not os.path.isdir(real):
        return {"ok": False, "error": f"不是目录: {real}"}

    dirs, files = [], []
    try:
        for name in sorted(os.listdir(real), key=lambda s: s.lower()):
            if name.startswith("."):
                continue
            full = os.path.join(real, name)
            try:
                st = os.stat(full)
            except Exception:
                continue
            if os.path.isdir(full):
                if _under_allowed(full):
                    dirs.append({"name": name, "path": full})
            elif os.path.isfile(full):
                files.append({
                    "name": name,
                    "path": full,
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                    "video": name.lower().endswith(VIDEO_EXT),
                })
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 视频优先，其次按名称
    files.sort(key=lambda f: (not f["video"], f["name"].lower()))

    parent = os.path.dirname(real.rstrip(os.sep))
    if parent == real or _under_allowed(parent) is None:
        parent = None

    return {
        "ok": True,
        "cwd": real,
        "parent": parent,
        "roots": [{"name": n, "path": p} for n, p in SHORTCUTS],
        "dirs": dirs,
        "files": files,
        "video_ext": list(VIDEO_EXT),
    }


# --------------------------------------------------------------------------
# 单帧缩放（手机流）
# --------------------------------------------------------------------------
def _placeholder_scaled(w: int, q: int) -> bytes:
    try:
        from console_server import _placeholder_jpeg  # 延迟导入，避免循环依赖
        return _placeholder_jpeg()
    except Exception:
        return b""


def scaled_frame(w: int = 960, q: int = 60, src: str = None) -> bytes:
    """画面单帧：按宽度缩放 + JPEG 降质。源帧未变时直接复用缓存。

    w<=0 表示不缩放（原画）。src 缺省 = op 画面；传 LIVE_FRAME = slowroads 实时画面。
    """
    path = src or OP_SCREEN
    w = int(w if w is not None else 960)
    if w > 0:
        w = max(160, min(w, 2560))
    q = max(20, min(int(q or 60), 95))
    try:
        st = os.stat(path)
        fresh = (time.time() - st.st_mtime) < FRAME_STALE_S
        key = (path, st.st_mtime_ns, st.st_size, w, q)
    except Exception:
        return _placeholder_scaled(w, q)

    if not fresh:
        return _placeholder_scaled(w, q)

    with _FRAME_LOCK:
        if _FRAME_CACHE["key"] == key and _FRAME_CACHE["data"]:
            return _FRAME_CACHE["data"]

    try:
        from PIL import Image
        with Image.open(path) as img:
            img = img.convert("RGB")
            if w and img.width > w:
                h = max(1, int(img.height * w / img.width))
                img = img.resize((w, h), Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=q)
            data = buf.getvalue()
    except Exception:
        return _placeholder_scaled(w, q)

    with _FRAME_LOCK:
        _FRAME_CACHE["key"] = key
        _FRAME_CACHE["data"] = data
    return data


# --------------------------------------------------------------------------
# 上传（裸 body 流式写盘）
# --------------------------------------------------------------------------
def _safe_name(name: str) -> str:
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[^\w\u4e00-\u9fff.\- ]+", "_", name)
    name = name.lstrip(".")
    if not name:
        name = f"upload_{int(time.time())}.mp4"
    if not name.lower().endswith(VIDEO_EXT):
        name += ".mp4"
    return name[:180]


def _do_upload(handler, q) -> None:
    """POST /api/upload?name=x.mp4 —— body 即文件原始字节，8KB 块边收边写盘。"""
    name = _safe_name((q.get("name") or [""])[0])
    try:
        total = int(handler.headers.get("Content-Length") or 0)
    except Exception:
        total = 0
    if total <= 0:
        return handler._send(400, {"ok": False, "error": "缺少 Content-Length"})

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dst = os.path.join(UPLOAD_DIR, name)
    tmp = dst + ".part"
    got = 0
    try:
        with open(tmp, "wb") as f:
            while got < total:
                chunk = handler.rfile.read(min(65536, total - got))
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
        if got < total:
            raise IOError(f"上传不完整：收到 {got}/{total} 字节")
        os.replace(tmp, dst)
    except Exception as e:
        try:
            os.path.exists(tmp) and os.remove(tmp)
        except Exception:
            pass
        return handler._send(200, {"ok": False, "error": str(e), "received": got})

    return handler._send(200, {
        "ok": True, "path": dst, "name": name,
        "size": os.path.getsize(dst), "received": got,
    })


# --------------------------------------------------------------------------
# 登录页
# --------------------------------------------------------------------------
def _login_page(next_path: str, err: str = "") -> bytes:
    err_html = f'<div class="err">{err}</div>' if err else ""
    nxt = urllib.parse.quote(next_path or "/m")
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0a0d12">
<title>openpilot 控制台 · 登录</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100dvh;display:flex;align-items:center;justify-content:center;
background:#0a0d12;color:#e6edf3;font:16px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;padding:24px}}
.card{{width:100%;max-width:400px;background:#11161d;border:1px solid #26303e;border-radius:18px;padding:28px 22px}}
h1{{margin:0 0 4px;font-size:20px}}
.sub{{color:#7d8b9c;font-size:13px;margin-bottom:22px}}
label{{display:block;font-size:13px;color:#9fb0c3;margin-bottom:8px}}
input{{width:100%;padding:15px 14px;font-size:17px;border-radius:12px;border:1px solid #2c3746;
background:#0d1219;color:#e6edf3;outline:none;-webkit-appearance:none}}
input:focus{{border-color:#3b82f6}}
button{{width:100%;margin-top:16px;padding:16px;font-size:17px;font-weight:600;border:0;border-radius:12px;
background:#2563eb;color:#fff;-webkit-appearance:none}}
button:active{{background:#1d4ed8}}
.err{{margin-top:14px;padding:11px 13px;border-radius:10px;background:#3a1418;border:1px solid #7f1d1d;
color:#fca5a5;font-size:13px}}
.foot{{margin-top:18px;color:#5d6b7c;font-size:12px;text-align:center}}
</style></head><body>
<form class="card" method="post" action="{PREFIX}/login">
  <h1>openpilot 控制台</h1>
  <div class="sub">请输入访问密码</div>
  <input type="hidden" name="next" value="{nxt}">
  <label for="pw">密码</label>
  <input id="pw" name="password" type="password" autocomplete="current-password"
         inputmode="text" autofocus placeholder="••••••••">
  <button type="submit">进入控制台</button>
  {err_html}
  <div class="foot">仅 Tailscale 内网可访问</div>
</form>
</body></html>""".encode()


# --------------------------------------------------------------------------
# [网页版 app 2026-09-29] 网页服务状态聚合
# --------------------------------------------------------------------------
def _pgrep(pattern: str) -> int:
    """按命令行模式数进程数（缓存 2 秒，避免状态页刷新把机器拖忙）"""
    now = time.time()
    with _PG_LOCK:
        c = _PG_CACHE.get(pattern)
        if c and now - c[0] < 2.0:
            return c[1]
    n = 0
    try:
        out = subprocess.run(["/usr/bin/pgrep", "-f", pattern],
                             capture_output=True, text=True, timeout=5)
        n = len([x for x in (out.stdout or "").split() if x.strip()])
    except Exception:
        pass
    with _PG_LOCK:
        _PG_CACHE[pattern] = (now, n)
    return n


def _tailscale_state(force: bool = False) -> dict:
    """解析 `tailscale serve status`，判断 /op 发布是否挂上。缓存 5 秒。"""
    now = time.time()
    with _TS_LOCK:
        if not force and _TS_CACHE["d"] and now - _TS_CACHE["t"] < 5.0:
            d = dict(_TS_CACHE["d"])
            d["age"] = round(now - _TS_CACHE["t"], 1)
            return d
    d = {"mounted": False, "url": "", "expected_url": "", "target": "",
         "raw": "", "error": None, "age": 0.0}
    try:
        out = subprocess.run([TAILSCALE_BIN, "serve", "status"],
                             capture_output=True, text=True, timeout=8)
        raw = (out.stdout or "") + (out.stderr or "")
        d["raw"] = raw.strip()[:4000]
        m = re.search(r"https://([^\s:]+):" + TS_PORT + r"\b", raw)
        host = m.group(1) if m else ""
        mm = re.search(r"\|\-\-\s*" + re.escape(TS_PATH) + r"\s+proxy\s+(\S+)", raw)
        if host:
            d["expected_url"] = f"https://{host}:{TS_PORT}{TS_PATH}"
        if mm:
            d["mounted"] = True
            d["target"] = mm.group(1)
            d["url"] = d["expected_url"]
        if out.returncode != 0:
            d["error"] = f"tailscale serve status 退出码 {out.returncode}"
    except Exception as e:
        d["error"] = f"无法执行 tailscale：{e}"
    with _TS_LOCK:
        _TS_CACHE["t"] = now
        _TS_CACHE["d"] = dict(d)
    return d


def _recent_errors(limit: int = 10) -> list:
    """从后端日志尾部挑出真正的报错行（滤掉长连接断开的正常噪音及其伴随行）"""
    try:
        with open(CONSOLE_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 120000))
            txt = f.read().decode("utf-8", "replace")
    except Exception:
        return []
    out = []
    for line in txt.splitlines():
        s = line.strip()
        if not s or len(s) > 300:
            continue
        if any(x in s for x in _SKIP_LINES):
            continue
        if any(b in s for b in _BENIGN):
            continue
        if _ERR_RE.search(s):
            if not out or out[-1] != s[:240]:
                out.append(s[:240])
    return out[-limit:]


def webstatus() -> dict:
    port = "8899"
    op = None
    try:
        import console_server as _cs          # 延迟导入，避免循环依赖
        port = str(_cs.PORT)
        pr = _cs._procs()
        op = {"running": bool(pr.get("running")), "count": pr.get("count", 0)}
    except Exception:
        pass
    if op is None:
        n = _pgrep("run_offline_demo.sh")
        op = {"running": n > 0, "count": 0, "launchers": n}

    ts = _tailscale_state()
    desk = _pgrep("console_app_launch.sh") > 0
    warn = []
    if desk:
        warn.append("桌面版 app 正在运行 —— 关闭本 app 只会撤掉 Tailscale 发布，"
                    "共享的后端和 op 栈会留着（桌面版继续用）")
    else:
        warn.append("桌面版 app 没在运行 —— 关闭本 app 会把 Tailscale 发布、后端、op 栈一起停掉")
    if not ts["mounted"]:
        warn.append("Tailscale 发布未挂载 —— 手机现在连不上")
    if not op["running"]:
        warn.append("op 演示栈未运行 —— 手机上只会看到「未运行」")

    return {
        "ok": True,
        "t": time.time(),
        "backend": {
            "pid": os.getpid(), "port": port,
            "uptime_s": round(time.time() - START_TS, 1),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(START_TS)),
            "running": True,
        },
        "local_url": f"http://127.0.0.1:{port}/m",
        "desktop_url": f"http://127.0.0.1:{port}/",
        "tailscale": ts,
        "op": op,
        "desktop_app": {"running": desk},
        "errors": _recent_errors(),
        "warnings": warn,
    }


def _serve_web_status(handler) -> bool:
    try:
        with open(WEB_STATUS_HTML, "rb") as f:
            body = f.read()
    except Exception as e:
        return handler._send(500, f"状态页缺失: {e}", "text/plain; charset=utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
    return True


# --------------------------------------------------------------------------
# 分发
# --------------------------------------------------------------------------
def handle_get(handler, p: str, q: dict) -> bool:
    if p == "/m":
        return _serve_mobile(handler)
    if p == "/web":
        return _serve_web_status(handler)
    if p == "/api/webstatus":
        return handler._send(200, webstatus())
    if p == "/login":
        nxt = (q.get("next") or ["/m"])[0]
        return handler._send(200, _login_page(nxt), "text/html; charset=utf-8")
    if p == "/api/fs":
        path = (q.get("path") or [""])[0]
        res = _fs_listing(path)
        code = 403 if res.get("code") == 403 else 200
        return handler._send(code, res)
    if p == "/api/gameframe.jpg":
        # [slowroads App 自动接入 2026-09-30] 游戏实时画面单帧（同 frame.jpg，源换成 live_frame.jpg）
        w = (q.get("w") or ["960"])[0]
        qq = (q.get("q") or ["60"])[0]
        try:
            data = scaled_frame(int(w), int(qq), src=LIVE_FRAME)
        except Exception:
            data = b""
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(data)
        return True
    if p == "/api/frame.jpg":
        w = (q.get("w") or ["960"])[0]
        qq = (q.get("q") or ["60"])[0]
        try:
            data = scaled_frame(int(w), int(qq))
        except Exception:
            data = b""
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(data)
        return True
    if p == "/api/download":
        return _serve_download(handler, (q.get("path") or [""])[0])
    return False


def handle_post(handler, p: str, q: dict) -> bool:
    """在 console_server.do_POST 读取 body 之前调用（上传要独占 body）。"""
    if p == "/login":
        return _do_login(handler)
    if p == "/api/logout":
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        _set_cookie_header(handler, "", 0)
        handler.send_header("Content-Length", "2")
        handler.end_headers()
        handler.wfile.write(b"{}")
        return True
    if p == "/api/upload":
        _do_upload(handler, q)
        return True
    return False


def _serve_mobile(handler) -> bool:
    try:
        with open(MOBILE_HTML, "rb") as f:
            body = f.read()
    except Exception as e:
        return handler._send(500, f"手机版页面缺失: {e}", "text/plain; charset=utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _serve_download(handler, path: str) -> bool:
    real = _under_allowed(path)
    if real is None:
        return handler._send(403, {"ok": False, "error": "路径不在允许范围内"})
    if not os.path.isfile(real):
        return handler._send(404, {"ok": False, "error": f"文件不存在: {real}"})
    try:
        size = os.path.getsize(real)
        name = os.path.basename(real)
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(size))
        handler.send_header(
            "Content-Disposition",
            "attachment; filename*=UTF-8''" + urllib.parse.quote(name),
        )
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        with open(real, "rb") as f:
            while True:
                chunk = f.read(262144)
                if not chunk:
                    break
                handler.wfile.write(chunk)
    except Exception:
        pass
    return True


def _do_login(handler) -> bool:
    try:
        n = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(n) if n else b""
        form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
    except Exception:
        form = {}
    pw = (form.get("password") or [""])[0]
    nxt = (form.get("next") or ["/m"])[0] or "/m"
    if nxt.startswith("/") is False or nxt.startswith("//"):
        nxt = "/m"

    want = _read_password()
    if not want:
        return handler._send(500, _login_page(nxt, "服务端未配置密码文件"), "text/html; charset=utf-8")
    if not hmac.compare_digest(pw, want):
        time.sleep(0.6)  # 轻微延迟，抬高暴力破解成本
        return handler._send(401, _login_page(nxt, "密码不正确"), "text/html; charset=utf-8")

    # Location 里可能带中文路径（文件浏览的 next），必须 percent-encode
    safe = urllib.parse.quote(nxt, safe="/?=&%")
    loc = f"{PREFIX}{safe}"
    body = f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={loc}">'.encode()
    handler.send_response(303)
    handler.send_header("Location", loc)
    _set_cookie_header(handler, _make_cookie(), COOKIE_MAX_AGE)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True
