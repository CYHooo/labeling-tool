# Windows exe 打包（lite / full 双版本）

日期：2026-09-21
状态：已确认设计，实现中
分支：`feat/windows-exe`（已包含启动脚本、登录界面选择工具、로컬 작업 标签页）；完成后以**一个 PR 合入 `main`**，不另建长期分支

## 0. 修订（2026-09-21）

full 版只用 SAM2.1 base_plus（SAM3 需 HuggingFace 授权且依赖 triton），权重不打包，首次使用时下载并校验 SHA256；源码运行仍默认 SAM3；第 3–6 节（PyInstaller 配置、GitHub Actions、目标电脑使用、风险应对）以本修订为准（不再有 sam3 / triton-windows / timm）。

## 背景 / 目标

目前 Windows 上需要先装 Python、建 `.venv`、装依赖，再双击 `run.bat`。目标是**下载 zip → 解压 → 双击 `LabelingTool.exe`** 即可使用，目标电脑无需安装 Python。

- 同一套 PyInstaller 配置产出两个版本：
  | 版本 | 内容 | 预计体积（zip / 解压） | 目标机器 |
  |---|---|---|---|
  | `LabelingTool-lite` | 在线标注 + 本地作业（已下载 job，`labeling_tool`，MobileSAM ONNX / CPU） | ~150–200 MB / ~400 MB | 生产用户普通 PC |
  | `LabelingTool-full` | lite + few-shot（`annotation_tool`，torch CUDA + SAM3 + SAM2） | ~2.5–3 GB / ~5 GB | 有 NVIDIA GPU 的标注 PC |
- 在 **GitHub Actions**（`windows-latest`）上打包，不依赖本地 Windows 环境。
- 形式：**onedir 文件夹 + zip**（非单文件 exe：单文件每次启动需解压数百 MB、且更易被杀毒误报）。
- **源码运行方式（`run.sh` / `run.bat` / `python -m …`）的行为完全不变。**

非目标：代码签名（首次运行会出现 SmartScreen 提示，README 说明“更多信息 → 仍要运行”）、自动更新、安装程序（MSI/NSIS）、macOS/Linux 可执行文件。

## 1. 可写数据位置：`app_home()`

问题：以下路径都相对于**源码文件位置**计算，打包后位于只读/内部目录（onedir 的 `_internal/`），数据会写进程序内部目录，升级（替换文件夹）时丢失：

| 用途 | 现在 | 位置 |
|---|---|---|
| 登录信息 | `labeling_tool/config.json` | `ui/dialog_helpers.py`、`scripts/upload_session_cli.py` |
| 下载的会话数据 | `labeling_tool/data/` | `session/workspace.py` |
| few-shot 权重 | `./checkpoint/…`（相对**当前工作目录**） | `annotation_tool/configs.py` |
| few-shot 默认数据集 | `./dataset` | `annotation_tool/configs.py` |
| few-shot 类别定义 | `annotation_tool/classes.json` | `annotation_tool/configs.py` |

方案：新增 `labeling_tool/core/app_paths.py`（无第三方依赖）：

```python
def is_frozen() -> bool:            # sys.frozen (PyInstaller)
def app_home() -> Path:
    """Writable per-installation folder.
    frozen : folder containing LabelingTool.exe
    source : repo root (parent of labeling_tool/)"""
```

改动后的解析规则：

| 用途 | 源码运行（**不变**） | exe 运行 |
|---|---|---|
| `config.json` | `labeling_tool/config.json` | `<exe目录>/config.json` |
| 会话数据 | `labeling_tool/data/` | `<exe目录>/data/` |
| few-shot 权重 | `./checkpoint/…` | `<exe目录>/checkpoint/…` |
| few-shot 类别定义 | `annotation_tool/classes.json` | `<exe目录>/classes.json` |
| few-shot 默认数据集 | `./dataset` | `<exe目录>/dataset` |

- 源码运行时 `config.json` / `data/` 仍在 `labeling_tool/` 下（与 `.gitignore`、现有用户数据一致），因此这两个用 `app_home()` 仅在 frozen 时切换；few-shot 的权重与数据集路径在源码运行时仍相对当前工作目录（保持现有 `cd` 到其他目录运行的用法）。
- **只读资源**（MobileSAM ONNX、BPE 词表、SAM2 yaml 配置）继续用 `__file__` 相对路径——PyInstaller 会把它们放进 `_internal/`，`__file__` 解析仍然正确。

## 2. 自检入口 `--selftest`

`labeling_tool/app.py` 新增 `--selftest`：不创建窗口，导入所有入口模块（`labeling_tool.ui.*`（登录界面、获取数据、主窗口）、ONNX 模型文件存在性；full 版额外导入 `torch`、`sam3.model_builder`、`sam2.build_sam`、`annotation_tool.ui.main_window`），打印结果后以 0/1 退出。

用途：CI 在打包后直接运行 exe 做冒烟测试，捕获 PyInstaller 漏打的模块/数据文件（这是打包 torch/SAM 最常见的失败点）。

`--selftest` 需在 `QT_QPA_PLATFORM=offscreen` 下可运行；因 exe 为无控制台（windowed）程序，结果同时写入 `<exe目录>/selftest.log`，CI 读取该文件。

## 3. PyInstaller 配置 `packaging/labeling_tool.spec`

- 入口：`labeling_tool/app.py`；onedir；`console=False`；exe 名 `LabelingTool.exe`；输出目录名 `LabelingTool/`。
- 通过环境变量 `LT_VARIANT=lite|full` 切换：
  - **lite**：`excludes=["torch", "torchvision", "sam2", "sam3", "annotation_tool", "triton"]`（防止开发环境中存在 torch 时被意外打入）。Few-shot 标签页因 `find_spec("torch")` 为 None 自动变灰（已有逻辑）。
  - **full**：`hiddenimports += collect_submodules("annotation_tool")`，`collect_all("sam3")`、`collect_all("sam2")`（含 hydra yaml 配置），`collect_data_files("annotation_tool")`（BPE 词表）。torch 使用 PyInstaller 自带 hook。
- 共同数据：`labeling_tool/models/sam/*.onnx`。
- 不打包：`config.json`、`data/`、`checkpoint/`、任何权重（`.gitignore` 已保证仓库里没有）。

## 4. GitHub Actions `.github/workflows/build-windows.yml`

- 触发：`workflow_dispatch`（手动）+ push tag `v*`。
- `strategy.matrix.variant: [lite, full]`，`windows-latest`，Python 3.12。
- 依赖安装：
  - lite：`pip install -r requirements.txt pyinstaller`
  - full：上述 + `torch/torchvision`（CUDA 12.4 wheel，`--index-url https://download.pytorch.org/whl/cu124`）+ `sam3 huggingface_hub psutil` + `sam2`（从官方 git 固定 commit 安装，`SAM2_BUILD_CUDA=0` 跳过 CUDA 扩展编译）。
- 步骤：安装 → 跑 `pytest`（lite：`labeling_tool/tests` + `tests/`；full：再加 `annotation_tool/tests`）→ `pyinstaller packaging/labeling_tool.spec` → `LabelingTool.exe --selftest` → 压缩。
- 产出：
  - 始终上传 Actions artifact：`LabelingTool-<variant>-<version>`（公开仓库免费，保留 90 天）。
  - tag 触发时发布到 GitHub Release：lite 为单个 zip；full 超过 Release 单文件 2 GiB 上限，用 7-Zip 分卷（`-v1900m`）上传 `LabelingTool-full.7z.001/.002/…`，README 说明用 7-Zip 解压第一个分卷。
- 版本号：tag 名（`v1.2.0`）或 `dev-<short sha>`；写入 exe 旁 `VERSION.txt`。

## 5. 目标电脑上的使用

```
LabelingTool/
├── LabelingTool.exe        ← 双击
├── _internal/              ← 程序本体（勿改动）
├── VERSION.txt
├── config.json             ← 首次登录后生成
├── data/                   ← 下载的会话数据
└── checkpoint/             ← 仅 full 版：首次打开 few-shot 时自动下载 SAM2.1 权重（~308 MB，SHA256 校验）；离线 PC 可手动下载放入
```

- 升级：解压新版本到新文件夹，把旧文件夹的 `config.json`、`data/`、`checkpoint/` 拷过去（README 写明）。
- full 版运行要求：NVIDIA GPU + 支持 CUDA 12.4 的驱动；无 GPU 时 torch 回退到 CPU（SAM2.1 会较慢，但可用）。
- 首次打开 few-shot 工具时自动下载 SAM2.1 base_plus 权重（~308 MB，SHA256 校验）到 `checkpoint/`；下载时弹出进度对话框（确认 → 进度条 → 关闭或取消；失败则弹窗说明并回到登录界面）。

## 6. 风险与应对

| 风险 | 应对 |
|---|---|
| PyInstaller 漏打 torch/SAM2 的动态导入或数据文件 | `--selftest` 在 CI 中导入全部关键模块；预计首轮需按 CI 日志补 hiddenimports / datas 若干次 |
| `sam3` 依赖在 Windows 上不可用的包（如 triton） | **已解决**（修订 §0：exe 仅使用 SAM2.1 base_plus，不含 SAM3） |
| full zip > 2 GiB 无法作为单个 Release 资产 | 7-Zip 分卷；artifact 另有完整包 |
| Actions runner 磁盘（~14 GB 可用）不足 | full 构建后清理 pip 缓存与 `build/`；必要时改用 D: 盘工作目录 |
| 杀毒软件 / SmartScreen 误报 | onedir（非单文件）降低误报；README 说明；代码签名作为后续可选项 |
| 生产行为回归 | 源码路径解析保持不变并有测试；lite 版 CI 跑全部生产测试 |

## 7. 测试

- 单元测试：`app_home()` 在源码 / 模拟 frozen（monkeypatch `sys.frozen`、`sys.executable`）下的路径；`config.json`、会话数据根目录、few-shot 权重/类别文件的解析结果；源码模式下与现状一致。
- `--selftest`：源码模式下 lite/full 均可运行并返回 0。
- CI：两个变体的打包 + exe 自检。
- 人工：在 Windows 上解压 lite 版，完整走一遍“登录 → 获取 → 标注 → 上传”；full 版在 GPU 机器上打开 few-shot 工具并完成一次 SAM 分割。

## 8. 交付物

- `labeling_tool/core/app_paths.py` + 路径改动（`dialog_helpers.py`、`upload_session_cli.py`、`workspace.py`、`annotation_tool/configs.py`）
- `labeling_tool/app.py` 的 `--selftest`
- `packaging/labeling_tool.spec`
- `.github/workflows/build-windows.yml`
- README：exe 下载 / 解压 / 升级 / full 版权重放置 / SmartScreen 说明
