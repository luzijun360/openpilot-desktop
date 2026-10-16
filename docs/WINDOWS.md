# Windows 使用教程（CPU / GPU / CUDA）

> 本项目主链路 `视频 → 线条` 在 Windows 上用 tinygrad 的 `CPU:LLVM` / `GPU` / `CUDA` 后端跑，不依赖 Mac 的 ANE。管线与控制台与 Mac 一致。

## 环境

1. **Python 3.12**（https://www.python.org/downloads/，勾选 Add to PATH）
2. **Git for Windows**（https://git-scm.com/，含 Git LFS）+ `git lfs install`
3. **ffmpeg**（https://ffmpeg.org/ 或 `winget install ffmpeg` / `choco install ffmpeg`）
4. **uv**（`pip install uv` 或 `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`）
5. **CUDA（可选）**：NVIDIA 显卡 + 驱动 + CUDA Toolkit（https://developer.nvidia.com/cuda-toolkit）才可走 `cuda` 加速；否则用 `cpu` 即可。

> 注意：项目路径避免中文与空格；如遇长路径报错，执行 `git config --system core.longpaths true`。

## 一键安装

```bat
REM cmd（管理员可选）
git clone https://github.com/<you>/openpilot-mac.git && cd openpilot-mac
scripts\setup.bat
```

```powershell
# PowerShell（首次可能需放行：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned）
git clone https://github.com/<you>/openpilot-mac.git; cd openpilot-mac
.\scripts\setup.ps1
```

脚本流程：克隆上游 `commaai/openpilot@49bbba3` → `git lfs pull`（约 65MB，小模型；`big_* 773MB` 默认跳过）→ 打补丁 → `uv sync` → `scons`。缺什么会有中文提示如何补装。

可选：`set INCLUDE_BIG_MODEL=1 && scripts\\setup.bat` 才会拉大模型。

## 跑视频

```bat
scripts\run.bat demo.mp4
scripts\run.bat demo.mp4 cuda    REM 末参可选：cpu / gpu / cuda，默认 cpu
scripts\run.bat --pick            REM 弹文件选择对话框选视频
```

```powershell
.\scripts\run.ps1 demo.mp4
.\scripts\run.ps1 demo.mp4 -Backend cuda   # cpu / gpu / cuda
.\scripts\run.ps1 -Pick
```

控制台：`http://127.0.0.1:8899/`（桌面），手机同网段 `http://<你的WinIP>:8899/m`。

## 后端说明

| 后端 | 要求 | 说明 |
|---|---|---|
| `cpu` | 无 | 最通用，`CPU:LLVM`，无需显卡 |
| `gpu` | 显卡驱动 | tinygrad 通用 GPU 后端 |
| `cuda` | NVIDIA 显卡 + CUDA Toolkit + `nvidia-smi` 可用 | 最快；检测不通过自动回退 `cpu` |

切换：命令行末参或环境变量 `OP_MODEL_BACKEND=cuda scripts\\run.bat demo.mp4`，也可在控制台右上角「推理引擎」切换。

## 排障

- **中文路径报错**：把仓库移到 `C:\\openpilot-mac` 这类英文路径。
- **PowerShell 禁止脚本**：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 后重试。
- **ffmpeg 找不到**：把 `ffmpeg.exe` 所在目录加入 PATH，重启终端。
- **`git lfs pull` 慢**：属 Hugging Face 拉取 65MB 模型，稍等；可重试。
- **`scons` 失败**：先 `uv sync --all-extras`，再 `scons -u -j4`；仍失败贴 `scons` 尾部日志提 issue。
