# IDEA · 把 openpilot 移植到我的 Mac

> 最后更新：2026-09-26 ｜ 状态：开工准备完成，M1 进行中 ｜ 工作清单见 `PLAN.md`

**一句话**：在 MacBook Air M1（8GB）上实现「输入视频画面 → 输出 comma 设备屏幕同款的可视化线条（车道线 / 路沿 / 行驶路径 / 前车等）」。

## 想要的效果

- 输入：任意道路视频（行车记录仪 / 网络视频 / 之后可扩展实时摄像头）
- 输出：comma 设备上那套叠加在画面上的线条与元素（车道线、路径、前车标记；HUD 可选）
- 加分项：SR 风格（3D 环绕 / 鸟瞰）渲染 —— 生态里没有现成方案，由本项目自研

## 为什么可行（调研结论，2026-09）

- openpilot 0.11.2 官方支持 macOS 开发运行（“大部分组件可原生运行”，核心工具与 replay 无障碍）
- 仓库自带 webcam 输入通道（代码显式区分 Darwin），OpenCV 可直接打开视频文件
- UI 已重写为 Python + raylib（跨平台）；画线条的 `onroad/model_renderer.py` 就是纯 Python
- 推理引擎 tinygrad 支持 Metal；无外置加速器时自动走小模型路径（880M 大模型不适用本机）
- 官方 `replay --demo` 无需硬件/账号即可先验证全链路

## 范围

**做**：

- 视频文件进 → 带线条视频出（离线优先，对 8GB 内存友好）
- 保留 comma 原版 UI 风格；可选移植社区版皮肤
- （可选）SR 风格自研渲染器

**不做**：

- 不接真车、不做 AEB/ADAS 车控（需要 panda + 线控；本项目纯可视化）
- 不碰 880M 大模型 / chestnut 外置 GPU（本机跑不动）

## 技术路线（已定）

**官方 master 打底 + 小模型 + 离线优先 + 挑社区 UI 皮肤 + 自研 SR 渲染**

## 关键决策记录

- 社区版取舍：sunnypilot（备选底座 + 86 模型库）；FrogPilot / StarPilot / chameleonpilot（UI 素材来源）；OPKR / dragonpilot / OPGM / carrotpilot / HGK-JPR 等车型专用版不采用
- AEB 真相：openpilot 生态无自研 AEB，均为“保留原车 AEB”；与本项目无关
- SR：生态无现成方案 → 作为自研加分项
- git-lfs：无需系统级安装，官方方案用 venv 内置（comma-deps-git-lfs）
- 机器约束：8GB 内存 → 离线优先；磁盘 ~32GB 可用 → 及时清理；macOS 27 较新 → 构建问题优先怀疑系统差异

## 交付物

1. Mac 上可复现的运行环境（openpilot 全栈）
2. 「视频 → 带线条视频」工具 + 使用文档
3. （可选）SR 风格演示视频

## 相关文件

- 工作计划 / 任务清单：`PLAN.md`
- 代码：`./openpilot`（克隆自 github.com/commaai/openpilot）
- 调研与日志：`~/.hermes/cache/scratch/`（临时目录；重要结论已沉淀进本文档）
