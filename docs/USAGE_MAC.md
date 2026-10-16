# Mac 使用教程

## 环境

- macOS 13+，Python 3.12，Xcode Command Line Tools
- `brew install python@3.12 uv ffmpeg git-lfs && git lfs install`

## 一键安装

```bash
git clone https://github.com/<you>/openpilot-mac.git && cd openpilot-mac
./scripts/setup.sh   # 克隆上游 49bbba3 → git lfs pull（huggingface，约 65MB）→ 打补丁 → uv sync → scons -j4
```

`setup.sh` 会自检缺什么并提示如何补装；失败可直接重跑。首次 `git lfs pull` 约 65MB；大模型 773MB 默认跳过（`INCLUDE_BIG_MODEL=1 ./scripts/setup.sh` 才拉）。

懒人：访达双击 `scripts/setup.command`。

## 跑视频

```bash
./scripts/run.sh /path/to/video.mp4
./scripts/run.sh --pick   # 弹文件选择框（桌面）
# 控制台：http://127.0.0.1:8899/  手机同网段：/m
```

后端切换：

```bash
OP_MODEL_BACKEND=coreml ./scripts/run.sh demo.mp4    # ANE（默认，需 mlpackage）
OP_MODEL_BACKEND=tinygrad ./scripts/run.sh demo.mp4  # Metal 回退
```

也可控制台右上角「推理引擎」一键切，约 40 秒重启生效。无 mlpackage 时自动回退 tinygrad。

## 常见问题

- 模型帧率天花板约 19Hz（干净）/12Hz（开控制台页），启动约 40 秒有浮层遮盖，属 8GB M1 极限。
- 前车距离为单目估算，绝对值仅供参考。
- 排障见 `docs/CHANGELOG.md` 末尾排障笔记。
