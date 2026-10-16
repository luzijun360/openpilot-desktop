# slowroads — 可选分支（默认关闭）

> 作用：把 slowroads / BeamNG 游戏画面作为 openpilot 的实时视频源，在控制台左上角实时叠加可视化。
> 注意：需自备 slowroads 网页或 BeamNG.drive 游戏本体（`v0.38.4.0/BD` 不随仓库分发）。

## 启用

```bash
./offline_demo/slowroads/slowroads_app_launcher.sh   # 需已打开 slowroads 页面/游戏窗口
./offline_demo/slowroads/slowroads_connect.sh         # 手动连接
./offline_demo/slowroads/slowroads_disconnect.sh      # 断开回主页
```

构建 app（如需）：

```bash
./offline_demo/slowroads/build_slowroads_app.sh
./offline_demo/slowroads/build_web_app.sh
```

详细生命周期与双 app 规则见 `docs/slowroads-任务清单.md` 与 `docs/PLAN.md` M8/M9。
