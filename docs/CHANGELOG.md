# openpilot 控制台 — 更新日志

## v1.3 — 2026-09-29（双 app 拆分）

把 Mac 上的 openpilot 拆成两个 app：**原版一行未动**，新增「openpilot 网页版.app」。

### 新 app 能力
- **窗口显示**：本地地址 `http://127.0.0.1:8899/m` + Tailscale 地址 `https://lu.taild4eec4.ts.net:10000/op`（都能一键打开/复制）
- **运行状态**：网页服务（PID/端口/运行时长）、Tailscale 发布（已发布/未发布）、op 演示栈（进程数）、桌面版 app（在跑/没跑），每 2 秒自刷新
- **报错状态**：后端日志尾部的真实异常（自动滤掉断连噪音），无异常显示「✓ 没有发现异常」
- **打开 app = 起服务**：缺什么补什么（后端 / op 全栈 / Tailscale 发布），已在跑的一律复用
- **关闭 app = 停服务**：桌面版在用 → 只撤 Tailscale 发布（共享的后端和 op 全栈留着）；桌面版没在用 → 全停
- **强杀兜底**：app 被 `kill -9` 也由看门狗 3 秒内清理

### 新增文件
`web_app.swift` · `web_app_launch.sh` · `web_status.html` · `make_web_app_icon.py` · `build_web_app.sh` · `test_web_lifecycle.sh`
后端 `console_mobile.py` 新增 `GET /api/webstatus` + `GET /web`

### 修复
- **`restart_console.sh` 的 `setsid` 在 macOS 上不存在** → 脚本一直静默失败，后端实际是靠桌面版 app 的看门狗救回来的；改用 Python `start_new_session=True`

### 验收
4 个生命周期场景 + 报错抓取 + 状态页渲染，全部实测通过（详见 `PLAN.md` M9）

## v1.0 — 2026-09-27（封版）

首个完整可用版本。
**构成**：openpilot 0.11.2（Mac 移植）+ offline_demo 控制台 + 假车桥接
**链路**：视频文件 → webcamerad → 真模型推理（M1 Metal）→ comma 同款可视化 + 纵向控制闭环

### 核心能力
- 视频文件输入：任意分辨率、**免转码**（播放时实时对齐 1928×1208）、导入秒开
- 真模型输出：车道线 / 路沿 / 行驶路径 / 前车三角（模型前车概率 > 0.5 门槛）
- 纵向控制闭环：假车 + HONDA_CIVIC_2022 指纹 + AlphaLongitudinal（可接管）
- 控制台 app（1600×820 单窗口）：左上 op 原版画面（离屏渲染 MJPEG 20fps）、左下状态指标、右上导入/调试、右下（DM 已删除，留空）
- 统一生命周期：**打开 app = 启动全部；关 app = 停止全部**（含崩溃看门狗 + 后端自愈）
- 素材管理：内置 32 个素材自动索引、播放此素材、车速按文件名档位解析（如 80-0追尾 → 80 km/h）
- 其他：播完定格、⌘Q/⌘C/⌘V 菜单、启动浮层、真实帧率显示（模型/相机）、性能提示开关

### 本版修复（A / B / N 系列，全部实测）
| 编号 | 问题 | 修复 |
|---|---|---|
| A1 | 方向盘显示恒偏 14~18° | 桥接改用「期望曲率 → 几何车轮角」回喂，打破闭环自咬 |
| A2 | 视频循环播放 | 播完定格最后一帧 |
| A3 | ⌘Q 关不掉 | app 补标准主菜单（退出/编辑/窗口） |
| A4 | 每次弹 "not tested" 警告 | selfdrived 强制正常启动提示 |
| A5 | 前车三角要等 ~50 秒 | 渲染器改读「有效数据」（原来错过一帧要等 card 重发） |
| A6 | 前车距离不准 | 标注「模型估算」+ 未采纳状态如实显示 |
| B1 | 前车检测口径混乱 | 统一用 op 真实采纳标志（present），按 0.5 门槛标注 |
| B2 | 素材视角 | 确认为引擎盖视角 |
| B3 | 裁切视角偏差 | 记录为固有（模型内参硬要求） |
| B4 | op 画面 12fps | 提到 20fps |
| B5 | 启动 40 秒无提示 | 加「openpilot 正在启动…」浮层 |
| B6 | 网页无法复制粘贴 | 编辑菜单（⌘C/⌘V/⌘A） |
| N1 | 假车无横向动力学 | 补：转向 → 偏航率 → IMU 陀螺仪 + 航向/位置积分 + 加速度计 |
| N2 | 车速与视频不匹配 | 从素材文件名解析档位起步 |
| N3 | 假 CAN 报 0x17C 无效 | 查明报文一直在发（启动瞬间竞态，自愈） |
| N4 | 素材带游戏 HUD | 记录为素材固有，实测不影响模型 |
| N5 | card 每 ~50 秒重发 carParams | 查明机制；A5 修复后不再影响 |
| — | 帧率显示误导（5Hz） | 改为真实算法（相机 frameId 差分 + 丢帧率） |

### 已知限制（固有 / 不修）
- 模型帧率天花板：干净跑 ~19Hz、开控制台页 ~12Hz（官方目标 20Hz，8GB M1 极限）
- 前车距离为单目估算（24~119m 波动），绝对值不可当真
- 标定（calibrationd）纯视频下不收敛，绝对精度受影响（显示正常）
- 裁切视角偏差（1928×1208 scale-cover 固有）
- 启动 ~40 秒（模型加载，有浮层遮盖）
- 播完定格后内部姿态估计缓慢漂移（显示不受影响，重启清零）

### 未做（C 系列）
- C1 状态面板完整版（播放控制 + 系统负载 + 更彻底全停）
- C2 左上角 op 屏幕可点击操作
- C3 sunnypilot 换底座（搁置）

### 关键路径
- 代码：`openpilot (upstream checkout, created by scripts/setup.sh)`（`openpilot/` + `offline_demo/` + `beamng_bridge/`）
- app：`/Applications/openpilot 控制台.app`（bundle id `com.lu.openpilot-console`）
- 后端：`http://127.0.0.1:8899/`
- 素材：`docs//测试素材/`
- 备份：`docs//backups/v1.0_2026-09-27/`

### 备份内容与恢复
- `v1.0-openpilot.diff` — 对 openpilot 源码的全部改动（9 个文件），在干净 clone 上 `git apply` 恢复
- `offline_demo_v1.0.tar.gz` — 控制台全部脚本/页面/桥接/图标
- `beamng_bridge_v1.0.tar.gz` — BeamNG 桥接（后期分支，保留）
- `openpilot-console-v1.0-binary` — app 可执行文件（拷回 .app 后 `codesign --force --sign -`）
- `STATE.txt` — 封版时状态快照（日期/git 状态/进程）

---

## v1.1 — 2026-09-27（C1 + C2 + 模拟方向盘 + ⌘Q 提速）

在 v1.0 基础上完成 C 系列的 C1 / C2，新增模拟方向盘组件，修掉 ⌘Q 退出迟钝。

### C1 状态面板完整版
- **播放控制**（右上「播放控制」行）：`⏸ 暂停` / `⏩ 倍速`（1.0x → 2.0x → 0.5x 循环）/ `⏮ 重播` / `⏻ 退出全部`
  - 直接作用于播放管线，**不重启全栈**（秒级生效）
  - 实现：后端**原子写** flag 文件（`pause.flag` / `speed.flag` / `restart.flag`），`camera.py` 每 0.5 秒读取生效
  - 跳帧优化：倍速时被跳过的源帧改用 `grab()` 只推进不解码（省 CPU）
  - **实测**（同一 99 秒素材）：1x = 151 秒、2x = 79 秒（实际倍率 **1.91x**）、0.5x 的素材内容阶段出现时间正好是 1x 的 2 倍
  - 注：绝对播放速度受模型推理吞吐上限（~13–19Hz）约束，满载时 1x 会略慢于实时；倍率本身准确
- **系统负载 / 内存**：「运行状态」行新增（负载 1/5 分钟均值 + 已用/总内存，2 秒缓存）
- **⏻ 退出全部**：一键 = 停全栈 + 关闭控制台 app（按生命周期日志里的 app_pid 精确 SIGTERM，看门狗兜底）
- 后端新增端点：`POST /api/playback`、`POST /api/click`、`POST /api/quit`

### C2 op 屏幕可点击操作
- 控制台网页里**直接点 op 画面 = 点真实 op 屏幕**（右上角 experimental 按钮、设置页按钮等都能点）
- 实现链路：网页点击 → 归一化坐标 POST `/api/click` → 原子写 `ui_click.json`（带 seq）→ UI 进程 `MouseState` 每帧读取 → 合成「按下 + 抬起」触摸事件注入（与官方测试回放 `selfdrive/ui/tests/diff/replay.py` 同一注入点）
- 首次读取只记 seq 不触发（避免上次会话的旧点击在 UI 启动瞬间补一枪）
- 预置 `ExperimentalModeConfirmed=True`（否则 experimental 按钮拒绝切换）
- **实测**：点右上角按钮 → `experimentalMode` false→true；再点 → true→false ✓

### 模拟方向盘（2026-09-27 重做版 + 当晚修正）
- **造型改成真车样式**：轮缘（带明暗渐变）+ T 形三辐条 + 中心气囊盖 + **12 点红色标记**（随轮转动 → 方向一眼可见）
- **新增三重方向指示**：固定刻度盘（每 15° 一格、45° 加长）+ **彩色角度弧**（蓝 = 左、橙 = 右）+ 下方角度文字（如「左 5°」）
- **两个符号/幅度 bug 修正**（当晚实测定位，此前版本都不对）：
  1. `carState.steeringAngleDeg` **本身就是方向盘角**（op 的 `VehicleModel.get_steer_from_curvature` 反算时已含转向比）→ 旧代码再乘一次 15.38 是重复放大（4.7° 被画成 72°）→ 已去掉；
  2. 符号以**实车观察为准**：**正 = 左 / 负 = 右** → 画面旋转用 `rotate(-deg)`（左转 = 逆时针）、左转配蓝。
- **实测**：方向盘角 5.3° → 画面「左 5°」+ 逆时针 + 蓝弧，与 op 画面中道路左弯一致 ✓
- 刹车/油门柱：底部往上填充（顶边水平线）+ 中间百分比

### ⌘Q 退出提速
- 根因：`applicationWillTerminate` 在主线程同步等清理跑完（最多 12 秒）
- 修复：发信号即返回，清理在后台继续；app 若被强杀由看门狗兜底
- **实测**：⌘Q 退出 **0.54 秒**（旧版最多 12 秒）；退出后全栈自动清零 ✓

### 本轮顺手修的 bug
- 播放 flag 写入改原子（半截数字会被 camera.py 当成「新值」→ 重复触发重播）
- `/api/quit` 弃用 `pkill -f`（会误伤命令行里含同名字符串的进程），改按 app_pid 精确 kill
- 点击转发首次读取不再触发陈旧点击

### v1.1 涉及文件
- `offline_demo/`：`console_server.py`、`console.html`、`console_app.swift`、`run_offline_demo.sh`
- `openpilot/`：`system/camerad/webcam/camera.py`、`system/ui/lib/application.py`

---

## 2026-09-27 深夜 · slowroads.io 网页游戏接入（焦点，进行中）

### 实时帧源（游戏画面 → op）
- `offline_demo/live_screen.sh`：ffmpeg avfoundation 抓屏 → `live_frame.jpg`（`LIVE_CROP="x:y:w:h"` 可只抓游戏窗口区域）；`camera.py` 已有「实时 JPEG 帧源」模式（`ROAD_CAM=*.jpg` 按 mtime 取最新帧），无需改代码
- **坑**：屏幕采集按显示器刷新率（60fps）全量进滤镜链 → **561% CPU 且画面冻结**；**`fps` 过滤器必须放链首**（先降到 20fps 再裁剪/缩放/JPEG 编码）→ 45% CPU ✓

### 游戏窗口（`offline_demo/game_window.swift` → 编译 `GameWindow.app`）
- 无边框 WKWebView 窗口，三项能力：**自带截图输出**（`takeSnapshot` → JPEG 原子写，与窗口位置/遮挡无关，也不需要屏幕录制权限）、**按键注入**（读 `game_keys.json` 把按键事件投给自己；状态文件 1 秒不更新自动全松 = 安全兜底）、键鼠可正常操作
- **坑 1（用户反馈「键盘鼠标无法控制窗口」）**：无边框 NSWindow 默认 `canBecomeKey=false` → 用户键盘永远进不来。必须子类化 `NSWindow` 并放开 `canBecomeKey/canBecomeMain`
- **坑 2（用户要求「下次打开有设置记忆」）**：要跨启动保留游戏设置，必须打成正规 `.app`（bundle id `com.lu.game-window`）+ `cfg.websiteDataStore = WKWebsiteDataStore.default()` → 设置落盘于 `~/Library/WebKit/com.lu.game-window/.../LocalStorage/localstorage.sqlite3` ✓
- **实测**：用真实按键事件（System Events，等同手按）按 ↑ → 车速 **0 → 43.4 km/h** ✓（键盘通路验证通过）

### op 控制游戏（`offline_demo/game_driver.py`）
- 链路：op `carControl`（方向盘角 + 加速度）→ 按键状态 JSON → 游戏窗口投键 → 游戏里的车
- **坑（用户反馈「一直在疯狂左右画龙」）**：键盘只有 0/1，v1「|方向盘|>死区就一直按住」= 每次都是满舵 → 疯狂画龙 ✗
- v2 = **PWM 脉冲控制**：周期 120ms，占空比 ∝ |方向盘角|（最大 45%），op 指令一阶低通 τ=0.4s，死区 2.5°；油门/刹车同样 PWM
- 符号：`steer` 正 = 左（沿用实车约定）；`SIGN` 常量可一键反转（若画龙加剧说明符号反了）

---

## 2026-09-28 · 降占用优化（画面不变、功能不变；栈内 CPU 降到原来 ~45%）

### 结果
- 基线（三个主进程）：modeld 109% + ui 37% + camerad 33% = 179%
- 优化后（播放中）：modeld 37.5% + ui 30.5% + camerad 12.1% = **80.1%（≈ 原来的 45%）**
- 模型输出 4 个张量 sha256 **逐字节一致**；播放仍实时（57 源帧/秒，10.05 秒播完）；模型刷新 14.5 → 18.6 次/秒

### 改动 1：tinygrad `contiguous_view` 结果缓存（最大收益，单帧 90.5ms → 13.6ms）
- 文件：`tinygrad_repo/tinygrad/uop/ops.py`
- 根因：`UOp.contiguous_view()` 每调用一次就跑一遍 `graph_rewrite` 整图模式匹配；模型每帧经 `.buffer` 调用它约 380 次（每帧 60 万次 Python 调用）→ 占 modeld 每帧 CPU 的 ~80%
- 修法：它是纯函数（只依赖 UOp 结构；UOp 不可变且按结构 intern），结果缓存进 `_CONTIGUOUS_VIEW_CACHE`，原逻辑拆到 `_contiguous_view_compute()`
- 对比数据：单帧 90.5ms → 13.6ms（6.7×）；输出指纹完全一致

### 改动 2：相机改走 PyAV 直出 NV12
- 文件：`openpilot/system/camerad/webcam/camera.py`（`use_pyav` / `_open_pyav` / `_read_frames_pyav`；`OP_CAM_BACKEND=cv2` 一键回退旧路径）
- 旧路径 cv2 解码 → 放大 1928×1208 → 转 NV12 ≈ 22ms/帧；新路径一趟 swscale ≈ 3ms/帧（解码 0.26ms/帧）
- 实测 camerad 33% → 12–20%；画面差异 1.58/255

### 改动 3：op 原生 UI 渲染帧率 60 → 20
- 文件：`offline_demo/run_offline_demo.sh`（`export FPS="${FPS:-20}"`）；视频本身 20fps，肉眼无差别
- 实测 ui 37% → 30.5%

### 排障笔记（重要，别再踩）
- **控制台 app 的看门狗**：`console_app_launch.sh` 在 app 退出/被杀时会把整个 op 栈停掉（`__STOP__ stop-only`）。手动起栈做测量时若 app 不在运行，栈会被它随时停掉 → 先确认没有 `console_app_launch.sh` 在跑
- **日志缓冲会骗人**：`manager.py | tee op_manager.log` 的 tee 是块缓冲 → 日志行可能滞后几十秒；判断"重播是否生效"不要只按日志时间点
- **假车桥接的 vEgo 不跟视频位置走** → 不能用 vEgo 验证重播；看相机的「源帧」计数或日志的「从头重播」
- **`ps` 的 %CPU 是近一分钟衰减值** → 用 CPU 时间增量法（脚本 `op_cpu_delta.py`）
- 相机诊断：`OP_CAM_DEBUG=1` 时每 2 秒打印耗时分布 + flag 读取值（默认关）

### 改动 4：相机输出改「按时间抽帧」（分数抽帧，2026-09-28 追加）
- 文件：`openpilot/system/camerad/webcam/camera.py`（PyAV 路径 + cv2 回退路径同步改）
- 原逻辑：`step = round(源帧率/20)` 整数抽帧 → 30fps 视频只能凑到 15 次/秒、24fps 会飙到 24 次/秒（都偏离模型的 20Hz 设计值）
- 新逻辑：每消费 1 源帧累积 `out_ratio = 20/(源帧率×倍速)` 额度，攒满 1 才输出一帧（Bresenham 式）；非视频源保持每帧输出
- 实测（相机直出帧率）：57fps→20.1、30fps→**20.0**、24fps→**20.1**、10fps→10.0 次/秒；源消耗速度仍为各帧率实时
- 效果：任何源视频（≥20fps）都稳定输出 20 次/秒 → 模型推理恒定 20Hz；倍速/重播时额度重置

### 涉及文件
- `tinygrad_repo/tinygrad/uop/ops.py`、`openpilot/system/camerad/webcam/camera.py`、`offline_demo/run_offline_demo.sh`、`openpilot/system/ui/lib/application.py`

---

## 2026-09-28 · 大视频修复（导入 700MB 录屏全灰 → 正常播放 + 占用再降）

### 症状
- 导入大视频（如 2880x1800 系统录屏）后画面全灰。日志里相机线程崩溃：
  `ValueError: cannot reshape array of size 3503200 into shape (1933)`（`camera.py` `_src_to_nv12`）

### 根因
- 等比缩放到目标宽度时算出 **1933（奇数）**。NV12 色度横向 2 倍下采样、宽度必须为偶数 → swscale 产出的缓冲与 `to_ndarray()` 的期望尺寸对不上 → 抛异常 → 相机线程死掉 → 没有帧 → 界面全灰。
- 1280x848 素材缩出来是 1928（偶数）所以一直没暴露；2880x1800 缩出来是 1933 就踩中了。

### 修复（3 处，均在 `camera.py`）
1. `_src_to_nv12`：缩放宽度强制取偶数（`nw += nw % 2`）。
2. `_read_frames_pyav`：单帧转换失败只跳过该帧（保险丝），不再炸掉整个相机线程。
3. `_open_pyav`：**解码改走 VideoToolbox 硬件解码**（`OP_CAM_HWACCEL=0` 回退软解）——大分辨率源软解要吃 1~2 个核，硬解走专用媒体引擎。

### 实测
- 大录屏播放中 camerad **88.6% → 16.1%**；模型刷新 **20.0 次/秒**（正好 20Hz）；车道线/路径/车速全正常。
- 38 个视频（29 个素材 + 9 个录屏，含 2880x1800、1.1GB 的）全部正常出帧，0 失败。

---

## 2026-09-28 · 修「左上角帧号一直涨」（播完定格后改显示「已播完」）

### 症状
- 控制台左上角状态行 `帧 12345 ｜ 模型 20Hz ｜ 相机 20Hz` 里的「帧」在视频播完定格后仍一直增加。

### 根因
- 那个数字是相机累计帧号（frameId）。视频播完后相机按设计仍以输出帧率重发最后一帧（保证画面定格而不是黑屏），frameId 因此继续增长 → 光看它分不清「在播」还是「已播完」。

### 修复（3 个文件）
1. `camera.py`：播完定格时写 `offline_demo/ended.flag`，重播/新开播时清掉（PyAV 与 cv2 两条路径都加了）。
2. `console_server.py`：快照下发 `video_ended`（读该标记）。
3. `console.html`：已播完时把「帧 N」换成「已播完（定格最后一帧）」（右侧「帧」行同理）；Hz 照常显示（管线确实还在 20Hz 跑）。

### 实测
- 播完：左上角显示「已播完（定格最后一帧）｜ 模型 16.1Hz ｜ 相机 16.1Hz」✓
- 点重播：标记清除 → 显示回到「帧 3272 ｜ 模型 12.4Hz ｜ 相机 12.4Hz」→ 10 秒后再次播完 → 重新显示「已播完」✓

---

## 2026-09-28 · ANE 加速（CoreML mlpackage）接入完成

### 做了什么
把驾驶模型从 tinygrad/Metal 换到 **Apple 神经引擎（ANE）**：ONNX → PyTorch(onnx2torch) → CoreML mlpackage → 接进 modeld。
新增 `selfdrive/modeld/coreml_runner.py` + `OP_MODEL_BACKEND=coreml` 开关，**默认仍是 tinygrad**，去掉环境变量即回退。

### 转换（脚本 `~/op项目of all/ane-convert/convert_v2.py`）
- 产物 `driving_supercombo.mlpackage`（53.4MB，fp16，7 输入 4 输出，形状与 ONNX 一致）
- 数值保真（CoreML vs 源 torch 图）：相对误差 3.1e-4 ~ 6.1e-3，全在 fp16 量级 ✓

### 三个转换坑
1. **coremltools 6.0 起移除 ONNX 前端**（7.2 与 6.3 均无）→ 改走 ONNX→PyTorch→CoreML
2. **onnx2torch 缺 Gelu、Reduce opset18 语义变了** → 自写 Gelu 转换器 + 把常量 axes 搬回属性（只改内存副本，原 ONNX 文件一字未动）
3. **原图是「fp16 权重 + 图内显式 Cast 到 fp16」设计**，进 coremltools 的 fp16 pass 会算错 dtype（bias fp16 vs weight fp32）→ 最终解：整图转纯 fp32（fp16 Cast 换 Identity），再让 coremltools 标准降到 fp16

### 接入要点
- **warp（透视变换）保留 tinygrad**，只替换 `modeld.py` 里那一次模型调用
- mlpackage 输入输出声明**全是 fp16**（mlprogram 无 uint8 类型）→ 输入 uint8/float32 转 fp16、输出转回 float32/uint8
- **关键性能坑**：第一版用 tinygrad 张量当输入输出缓冲，每帧 14 次 `.numpy()/assign().realize()` 调度，把 ANE 省的时间全吃掉（modeld 32.3%）。换成纯 numpy 缓冲（`NumpyBuffer`）后 **15.7%**

### 实测
| 指标 | tinygrad/Metal | ANE（CoreML） |
|---|---|---|
| modeld CPU | 38.1% | **15.7%** |
| 单帧推理 | 13.6 ms | **4.36 ms** |
| 模型刷新 | 16.7 次/秒 | **18.6 次/秒** |

- 功能自检：车道线 33 点 / 路径 33 点 / vEgo 3.02 m/s / enabled / thermal ok ✓
- 栈内三进程（camerad+modeld+ui）：82.5% → **48.7%**（ui 32.4% 为主项；camerad 0.6% 因视频已定格）
- 回退：去掉 `OP_MODEL_BACKEND=coreml` 即回到 tinygrad

---

## 2026-09-28 · 控制台新增「推理引擎」开关（ANE 设为默认）

### 做了什么
控制台右侧「控制台」面板新增「推理引擎（模型跑在哪）」一行，两个按钮：
- **🧠 ANE 神经引擎**（默认，选中时绿色高亮）
- ⚙ Metal（tinygrad）

点一下即切换；**栈正在跑会自动重启演示**（约 40 秒）让新后端立即生效。「运行状态」区多了一行「推理引擎（当前）」，显示**实际**在跑哪个（不是选的那个）。

### 改动（5 个文件）
1. `offline_demo/run_offline_demo.sh` — `export OP_MODEL_BACKEND="${OP_MODEL_BACKEND:-coreml}"`：**默认 ANE**；另导出 `OP_MODEL_BACKEND_MARKER` 给 modeld 落标记
2. `offline_demo/op_app_launcher.sh` — 启动前读 `offline_demo/model_backend.txt`（控制台里选的）并 export，优先级高于脚本默认值
3. `openpilot/selfdrive/modeld/modeld.py` — 启动时把实际后端写进 `model_backend.running`
   （macOS 上 `ps eww` 读不到别的进程的环境变量，所以由 modeld 自己落标记）
4. `offline_demo/console_server.py` — 新增 `POST /api/model_backend`（写设置 + 栈在跑则用 `last_video.txt` 自动重启）；快照下发 `modelBackend: {setting, running}`
5. `offline_demo/console.html` — 新按钮行 + 运行状态行 + 渲染/点击逻辑

### 实测（端到端）
- 设置 tinygrad → 用启动器起栈 → 启动器日志「控制台设置：推理后端 = tinygrad」→ modeld 标记 = tinygrad ✓
- 调 API 切 coreml → 返回 `{"ok":true,"restarted":true}` → 自动重启 → 日志「控制台设置：推理后端 = coreml」→ 标记 = coreml ✓
- 快照 `{"setting":"coreml","running":"coreml"}`；页面显示「推理引擎（当前）🧠 ANE 神经引擎」、按钮高亮正确 ✓
- ANE 运行中功能自检：模型 17.6~19.8 次/秒、车道线 33 点、路径 33 点、thermal ok ✓；modeld 16.8% ✓

### 回退
控制台点「⚙ Metal」即回退；或删 `offline_demo/model_backend.txt` 并把 `run_offline_demo.sh` 里那行的默认值改成 `tinygrad`。

---

## 2026-09-28 · 控制台「驾驶指示器」（TSS 风格）+ AEB 红色闪烁 + TSS 音效

### 做了什么
- 控制台右上新增「驾驶指示器」面板（TSS2.0 风格）：
  - 梯形两条车道线：识别到 = 实心白；识别不到 = 空心虚线灰（阈值 0.5；取 `laneLineProbs[1]` / `[2]`，op 约定 = 左右相邻车道线）
  - 上方车屁股图标：有前车才显示（`radarState.leadOne.present` 或模型前车概率 > 0.5），带距离
  - 三条横杠：aggressive 1 格 / standard 2 格 / relaxed 3 格（读 `LongitudinalPersonality`）
  - 右侧文字行：前车 / 左车道线 / 右车道线 / 驾驶模式
- AEB 指示：触发时前车图标变红闪烁（`#ff453a` + `aebBlink` 0.55 秒动画），「前车」一行显示红色「⚠ AEB 紧急制动」
- AEB 音效：触发时用 `afplay` 播 `测试素材/tss sound/3月15日.m4a`（1.86 秒；2.5 秒内不重复，抖动不会连响）

### 关键发现：这版 op 里 AEB 事件没有发送方
`EventName.aeb` 只在 `selfdrived/events.py` 定义了警报样式，全仓没有任何地方发送它。真正活着的是这三个：

| 信号 | 含义 |
|---|---|
| `longitudinalPlan.fcw` | op 纵向规划器的前向碰撞预警（MPC 连续预测到碰撞才会置位），驱动 op 界面那条「BRAKE!」 |
| `modelV2.meta.hardBrakePredicted` | 模型自己预测到急刹（凯美瑞这段素材里就是它先触发） |
| `carState.stockAeb` | 原车 AEB（离线 demo 里恒为假，留作兼容） |

### 实测（「凯美瑞差点追尾」素材）
- 重播后 3.6 秒：模型预测急刹 → 指示器 AEB 亮起（源 `model`）→ 控制台**同一时刻**拉起 `afplay` 播 TSS 音效 ✓
- 页面侧实测：车图标填充 `rgb(255,69,58)`、`aebBlink` 动画对象在跑、透明度在 0.80↔1 之间变化（= 真的在闪）✓
- 期间 op 自己也在刹：车速 13.8 → 7.8 km/h、前车 22 → 5 m、op 警报「BRAKE!」✓

### 重要教训（别再踩）
- **视频播完定格后，模型对着同一帧反复算 → 车道线 / 路径 / 前车全部冻住**，而 Hz 还在跳，看起来像「数据是假的」。判定数据真假必须在**播放中**测（触发重播后立刻采样）。这也解释了「4 条线 33 点」曾被误判为假数据——实测播放中车道线概率 0.04~0.96、每帧都在变，是真的。
- 模型是**循环网络**：定格后内部状态会自我演化（急刹预测约 1 秒后衰减），所以不能靠「暂停画面」保持模型输出的某个状态。
- capnp 列表**不支持切片**（`leadsV3[:3]` 直接抛异常），要用索引；指示器那段包在 try 里，异常会被吞掉、整块显示成 0——看到指示器全 0 先怀疑这个。
- `restart.flag` 的内容是**序列号**：内容不变就不重播（控制台按钮写 `time.time()` ✓ 正常；手动写固定值会没反应）。

### 回退
- 指示器面板：删 `console.html` 里 `#indPanel` 那一块 + `console_server.py` 里 `out["indicator"]` 那段
- AEB 音效：删 `console_server.py` 里 `AEB_SOUND` 常量那几行；或设环境变量 `AEB_SOUND` 指向别的音频文件

---

## 2026-09-28 · AEB 时把 op 原版警报音静音（只留 TSS 音效）

### 问题
AEB 触发时除了控制台的 TSS 音效，还会听到 op 原版警报音——来源是 `selfdrive/selfdrived/events.py` 里
`EventName.fcw` 的 `AudibleAlert.warningSoft`；`soundd` 把它映射到 **`critical.wav` 且无限循环（音量 MAX）**
（`sound_list` 里 `warningSoft: ("critical.wav", None, MAX_VOLUME)`，play_count=None 就是循环）。
离线 demo 里 AEB 走的正是这条 FCW 警报（`aeb` / `stockAeb` 本来就是 `AudibleAlert.none`）。

### 改法
`events.py` 的 `EventName.fcw`：`AudibleAlert.warningSoft` → **`AudibleAlert.none`**（画面上的红色「BRAKE!」保留不动）。
回退：改回 `warningSoft`。

### 实测（凯美瑞差点追尾素材，改后重启全栈）
- AEB 那一刻 `selfdriveState.alertSound` = **`none`**（10 个 AEB 采样全部 none，没有出现其它取值）✓
- `selfdriveState.alertText1` = **`BRAKE!`**（视觉警报照旧）✓
- 控制台 TSS 音效照常播（同一时刻 `afplay` 在播）✓

---

## 2026-09-29 · 修「卡顿时跳出固定幻觉车道线 + 幻影前车」（静止帧去重）

### 问题
视频播完定格 / 游戏暂停时，画面静止但相机仍 20fps 重发同一张图 → 模型（循环网络）反复吃同一帧，
内部状态约 1 秒收敛到「吸引子」→ 吐出一套**固定不变的幻觉**：4 条车道线概率一起飙高、幻影前车
概率 0.97 / 距离 3.2m（画面里根本没有车）、每次都是同一套错误车道线/曲率/小三角车。
危害：幻影前车 3.2m 会误触发 FCW/AEB 红闪 + TSS 音效。

### 改法
`system/camerad/webcam/camera.py` 的 `read_frames`：每帧算内容哈希（`blake2b(buf[::64])`，开销可忽略），
内容与上一帧相同就**跳过发布**（视频路径 + 实时画面路径都生效）。定格效果保留（画面照旧停在最后一帧）。
- 开关：`OP_CAM_SKIP_STATIC=0` 回退到旧行为

### 实测（30-0斜.mov，改后重启全栈）
```
播放中：车道线概率 0.2~0.94 每帧变化 ✓ 真实数据
播完定格： [0.0, 0.03, 0.03, 0.0] 前车 0.32
18 秒后：  [0.0, 0.03, 0.03, 0.0] 前车 0.32   ← 零漂移 ✓
```
日志确认：`[camera] 画面内容未变化 → 暂停发布（模型不再空转漂移；恢复变化后自动继续）`
画面层无副作用：无红色警告、正常定格、manager 认为相机正常（`webcamerad` running ✓）。

### 回退
`OP_CAM_SKIP_STATIC=0`（或删 `camera.py` 里 `[静止帧去重 2026-09-29]` 那几段）

---

## 2026-09-29 · 控制台加「重新校准」按钮（op 真校准）

### 背景
演示启动时 `run_offline_demo.sh` 用 `set_params_enabled()` 预置了一个「假的有效标定」
（`CalibrationParams`，validBlocks=20、rpyCalib=[0,0,0]），所以 op 一启动就是「已校准」。
op 真实校准的速度门槛：`calibrationd.py:24 MIN_SPEED_FILTER = 15 mph = 24.1 km/h`
（还要直线、低偏航）——就是「以 24km 行驶」那个。

### 改法
- 控制台加两个按钮：**🎯 重新校准** / **↩ 恢复预置标定**（`console.html` + `console_server.py`）
- 后端 `/api/recalibrate`：写持久标志 `recalib.flag` + 删 `CalibrationParams` + 用当前画面源重启演示栈
- 后端 `/api/restore_calib`：写回假标定 + 删标志 + 重启
- `run_offline_demo.sh`：启动时若见 `recalib.flag` 就**不预置假标定**（否则重启会被覆盖——实测踩过）
- 控制台显示标定状态：`extrinsicsCalibration` 服务 → `calStatus`/`calPerc`（已校准 ✓ / 校准中 x% / 未校准）
- 为什么必须重启栈：`calibrationd` 只在启动时读 `CalibrationParams`（`calibrationd.py:72`），
  且它是 manager 管的 `only_onroad` 进程，单独 pkill 不会被拉起（实测没拉起 ✗）

### 实测（100-0追尾.mov，100km/h 素材）
```
点「重新校准」→ 日志出现「检测到 recalib.flag：本次不预置假标定」✓
重启后：status=uncalibrated perc=25% validBlocks=1     ← 真的在从零校准 ✓
重播 1 次：uncalibrated 65% 3 块
重播 2 次：calibrated  100% 5 块                        ← op 自己收敛了 ✓✓
重播 3~6 次：calibrated 100% 6→12 块
```

### 回退
删按钮 + 删两个 API 路由 + 删 `run_offline_demo.sh` 里 `[重新校准 2026-09-29]` 那段

---

## 2026-09-29 · 虚拟手柄（页面内伪装 Gamepad）+ 合成点击 —— op 真控 slowroads

### 背景
slowroads 支持手柄，但 macOS 用户态建虚拟 HID 需要 Apple 特批 entitlement
（`IOHIDUserDeviceCreate` 返回 nil ✗），而窗口原有的控制方式是**真实鼠标移动/点击**
（`CGEvent post(tap: .cghidEventTap)`）——会抢用户的鼠标（用户明确叫停过）。
→ 改为**在 WKWebView 页面内伪装 Gamepad API**：游戏分辨不出，且全程不碰鼠标。

### 改法（`offline_demo/game_window.swift` + `game_driver.py`）
- `padShim`（`.atDocumentStart` 注入）：伪造标准映射 Gamepad（4 轴 + 17 键）+ 派发 `gamepadconnected`
- `startPadLoop()` 30Hz 把 `game_keys.json` 的 steer/throttle/brake 推进页面；
  `pad:1` 时**早返回，不发任何鼠标/键盘事件**
- `game_driver.py`：`PAD_MODE`（`OP_GAME_PAD=0` 回退鼠标模式）+ 连续量 throttle/brake
- **合成点击**（解决"必须先点一下开始"）：`{"click":[x,y]}` 或 `{"clickText":"菜单文字"}` + `clickSeq` 序列号；
  纯页面内 `dispatchEvent`，不碰真实鼠标
- `pad_stats.json`：每 3 秒写「游戏读手柄」的计数 + 页面文字（诊断用）

### 关键坑（实测）
1. **页面 CSS 视口是 940×588（截图是 2 倍 Retina）** → 坐标点击要用**减半**的 CSS 坐标
2. **游戏有个 "Enable mouse control" 开关**（设置 → CONTROLS → MOUSE）：
   `if(!le.useMouse && this.hasGamepadInput) this.updateGamepad(...)`
   —— **开着它时游戏检测到手柄但完全忽略手柄的值**（实测：轴/键读取次数 0 ✗）。
   关掉后：`getGamepads` 从 38 → 965（每帧读），转向轴 1790 次、油门键 1731 次 ✓✓
3. 游戏默认手柄映射与我们的 shim 完全一致：油门=按钮7、刹车=按钮6、转向=轴0（左负右正）
4. 合成点击的元素查找要**大小写不敏感**（游戏标签是 CSS 大写，DOM 里是 "Controls"）

### 实测
```
① 合成点击 begin → 游戏开始（画面在动 ✓）
② 关掉 Enable mouse control → 游戏开始每帧读手柄 ✓
③ 推 throttle=0.6 持续 12 秒 → HUD：0.0 → 74.4 KM/H ✓✓（车真的动了）
④ 启动 game_driver.py（op 接管）→ 游戏每帧消费 op 的指令：
   getGamepads 11863 次 / 转向轴 23586 次 / 刹车 22781 次 / 油门 21766 次 ✓✓
   op 画面：游戏道路 + 绿色路径叠加 + 35 km/h ✓
```

### 边界（重要）
- **模型泛化天花板仍在**：op 能开游戏（管线全通），但模型没学过这种美术风格，
  车道置信度仅 ~0.5（真实素材 0.9+），会开到路边护栏 ✗ —— 这是模型能力上限，调参无解
- 关掉「Enable mouse control」后**鼠标不再能开车**（键盘仍可用）——这是手柄工作的前提条件
- 游戏开着设置菜单/暂停时输入会被忽略；控制时保持游戏在**前台**（被遮挡会被 WebKit 降速）

### 回退
- 手柄 → 鼠标：`game_keys.json` 去掉 `"pad":1`（或 `OP_GAME_PAD=0` 跑 game_driver.py）
- 游戏设置里把「Enable mouse control」勾回来（鼠标恢复可用）

### 附带发现（游戏持久化设置的真实值）
游戏设置存 `~/Library/WebKit/com.lu.game-window/…/LocalStorage/localstorage.sqlite3`（UTF-16 编码的 JSON）：
```
settings_Mouse:    {"useMouse":false, ...}          ← 鼠标控制已关（手柄生效的前提，已持久化）
settings_Gameplay: {"autodriveMode":2, ...}         ← 2 = Full auto（设置面板里本来就是全自动）
settings_Gamepad:  油门=按钮7、刹车=按钮6、转向=轴0（sign 左-1 右+1）← 与我们的假手柄映射完全一致
settings_Keys:     Autodrive=KeyF（开/关）、AutodriveMode=KeyG（循环模式）、WASD=油门/刹车/转向
```
**注意**：玩家一介入（推油门/刹车），游戏的自动驾驶会从 Full auto 降级为「只转向」——
所以控制测试后，游戏里按 **F** 恢复自动驾驶（或按 **G** 循环模式）。这是游戏自身行为，不是 bug。

---

## v1.2 — 2026-09-29（手机版网页控制台 + Tailscale 发布）

把桌面控制台搬上手机：**功能与桌面版完全一致**，挂 Tailscale 仅内网访问，带密码。

### 新增文件
| 文件 | 作用 |
|---|---|
| `offline_demo/console_mobile.py` | 手机版后端扩展（约 550 行，零依赖，纯标准库 + 已有 PIL） |
| `offline_demo/console_mobile.html` | 手机 / iPad 自适应前端（约 950 行，三档布局） |

`console_server.py` **只加了 3 处调用**（顶部 import + `do_GET`/`do_POST` 各一段钩子），桌面版逻辑零改动。

### 新增接口
```
GET  /m                        手机 / iPad 页面（远程根路径自动路由到此）
GET  /login                    登录页
POST /login                    校验密码 → 下发签名 Cookie
POST /api/logout               清除 Cookie
GET  /api/fs?path=             网页内文件浏览（限允许根目录，越界 403）
GET  /api/frame.jpg?w=&q=      op 画面单帧（缩放 / 降质，手机流用）
POST /api/upload?name=         裸 body 流式写盘（手机上传）
GET  /api/download?path=       文件下发到手机
```

### 关键设计决定（都有实测依据）
1. **前缀归一化，不赌行为** —— 实测 Tailscale `--set-path=/op` **会剥掉前缀**，
   但后端两种都吃（`/op/api/x` 与 `/api/x` 等价），前端一律用动态算出的 `BASE` 相对路径
2. **手机流用 JPEG 轮询，不用 MJPEG** —— 可精确控画质/帧率、弱网断了自动恢复；
   桌面版继续用 MJPEG，一行没改。实测标准档 **195KB/s**（原图直转是 1.1MB/s）
3. **上传走裸 body，不用 multipart** —— Python 3.13+ 已移除 `cgi`，标准库没有 multipart 解析器；
   改成 body 即文件字节、8KB 块边收边写盘，零依赖且能吃大文件
4. **鉴权用登录页 + 签名 Cookie，不用 HTTP Basic** —— 手机浏览器上 Basic 体验差、没法登出、
   每路流都带凭据。现在是 `HttpOnly; Secure; SameSite=Strict`，30 天有效
5. **本机直连免登录** —— 判据是 Host 是否本机 + 有无 `X-Forwarded-For`，
   所以 Mac 上打开 `127.0.0.1:8899` 仍是原桌面版、不用登录
6. **导入用「网页内浏览 Mac 目录」替代原生文件框** —— 手机上远程也能选文件，
   不受 Mac 锁屏影响，也不用跑到 Mac 前面
7. **坐标换算零误差** —— `<img>` 用 `width/height:auto + max-*` 让元素框 = 画面框（无 letterbox），
   `getBoundingClientRect()` 归一化即精确

### 三档自适应布局
- **手机**：顶部状态条 + 常驻 op 画面（可「收起画面」）+ 底部四标签（指示器/指标/控制/日志）
- **iPad（≥820px）**：双列，全部面板同时铺开，无标签栏
- **宽屏（≥1400px）**：三列

### 实测（31 项后端自测 + 浏览器实测）
- 本机直连行为不变：`/`、`/api/status`、`/api/materials`、`/api/opscreen.jpg` 全 200
- 远程未登录 → 401（API）/ 302 跳登录页（页面）；登录 → 303 + Cookie
- 文件浏览越界拦截：`/etc` 与 `docs//../../../etc` **都 403**
- 上传 300KB 落盘字节一致；下载内容一致；空 `Content-Length` → 400
- 画面缩放：原图 1024×512/55934B → w=960 **32790B(-41%)** → w=480 **10487B(-81%)**
- 手机流实测 **7.5fps / 均 26KB/帧 / 195KB/s**
- Tailscale 域名全链路：`/op` → 302 → 登录页 200 → 登录 → `/op/m` 200(52517B) → API 200 → 画面帧 200(26350B)
- **仪表盘 `/`→9119 回归验证正常**，未受影响

### 发现的坑（重要）
1. **非 ASCII 路径必须 percent-encode** —— curl 直接发原始中文 URL 会 400（HTTP 请求行规范）；
   浏览器本来就会编码，前端一律 `encodeURIComponent`
2. **`Secure` cookie 在 http 下不存储** —— 所以本机 http 测试用 curl 时看不到 cookie（走 Tailscale 是 https，正常）
3. **`--set-path` 挂载不影响同端口已有挂载** —— 加 `/op` 后 `/` 仍在，无需重建
4. **驾驶员摄像头（`/api/driverstream`）数据源本来就不存在** —— `driver_cam.jpg` 没有，
   返回的是占位图，且**桌面版前端从未引用过它**，本次也不做

### 使用
```
地址：https://lu.taild4eec4.ts.net:10000/op   （仅 Tailscale 内网，首次要输密码）
桌面版：http://127.0.0.1:8899/                （不变，不需要登录）
```

### 回退
```bash
# 撤掉 Tailscale 挂载
tailscale serve --https=10000 --set-path=/op off
# 让手机版接口失效（桌面版照常）
mv offline_demo/console_mobile.py offline_demo/console_mobile.py.off
# 重启后端即可
```


## 2026-09-29 控制台「slowroads 自动驾驶」一键开关（op 开游戏的总开关）
控制台新增一行「slowroads 自动驾驶」：一个按钮切换 op 开/关 slowroads，全程不碰真实鼠标。

### 实现
- `console_server.py`：`POST /api/game_control {"on": true|false}` + `_start/_stop_game_driver()` + 快照新增 `game` 字段（running/steer/throttle/brake/live）
  - 开 = Popen(game_driver.py, start_new_session)（日志 logs/game_driver.log、pid 写 game_driver.pid）
  - 关 = SIGTERM + 立刻写归零 game_keys.json（不等 1 秒超时兜底）
  - 守卫：画面源必须 live_frame.jpg + manager.py 在跑（否则返回错误文本，页面弹 toast）
- `console.html`：新按钮 `#btnGameDrive`（▶ 开始 / ⏹ 停止 切换，运行中变红）+ 状态行实时显示方向盘/油门/刹车（SSE 刷新）

### 踩坑（重要）
- 控制桥进程识别**不能用 `pgrep -f game_driver.py` 全表扫**：命令行里恰好含该字样的进程会被误伤（实测 stop 把自己的测试 shell 杀了 SIGTERM、start 误报「已经在跑」）→ 改为 **pid 文件 + `ps -o command= -p` 校验**；兜底 pgrep 也只认以 `game_driver.py` 结尾的命令行
- 控制台 app 没有刷新菜单 → 页面更新必须退出 app 重开（会顺带重启 op 栈）

### 验证（真实点击，双向）
- 点「开始」→ 控制桥 pid 55240 起 + 日志「接管=True 方向盘(滤波)=-12.6°」+ game_keys.json 0.0 秒新鲜（steer -0.14 / throttle 0.362）✓
- 点「停止」→ 进程停 + pid 文件清 + 手柄归零 ✓
- API 直调 + 页面按钮状态渲染（SSE 自动切换 ▶/⏹）均通过

### 回退
```bash
cp offline_demo/console_server.py.bak-20260929-game offline_demo/console_server.py
cp offline_demo/console.html.bak-20260929-game offline_demo/console.html
# 重启后端即可
```
