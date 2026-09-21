# Windows exe 打包（lite / full）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 由 GitHub Actions 为 Windows 生成 `LabelingTool-lite` / `LabelingTool-full` 两个免安装 onedir 包，解压后双击 `LabelingTool.exe` 即可运行。

**Architecture:** 新增 `labeling_tool/core/app_paths.py`，在打包运行（`sys.frozen`）时把可写文件（config.json、data/、checkpoint/、classes.json）放到 exe 旁边，源码运行时路径完全不变。`labeling_tool/selftest.py` 提供 `--selftest=lite|full` 导入级冒烟测试，供 CI 在打包后直接运行 exe。一个 PyInstaller spec 通过 `LT_VARIANT` 切换是否包含 few-shot（torch + SAM3 + SAM2），一个 workflow 以 matrix 并行打包两个版本。

**Tech Stack:** Python 3.12、PyQt5、PyInstaller 6.22.3、GitHub Actions `windows-latest`、torch 2.5.1+cu124、triton-windows 3.1.0.post17、sam3 0.1.4、sam2（git `2b90b9f5ceec907a1c18123530e92e794ad901a4`）、7-Zip（runner 预装）。

**Spec:** `docs/superpowers/specs/2026-09-21-windows-exe-packaging-design.md`

## Global Constraints

- 源码运行（`run.sh` / `run.bat` / `python -m …`）的所有路径与行为保持不变。
- exe 形式：onedir + 压缩包；`console=False`；exe 名 `LabelingTool.exe`；输出目录 `LabelingTool/`。
- lite 版不得包含 torch / torchvision / sam2 / sam3 / annotation_tool / triton。
- 不打包 `config.json`、`data/`、`checkpoint/`、`classes.json` 或任何权重。
- Release 单个文件 < 2 GiB：full 版用 7-Zip 分卷 `-v1900m`。
- 生产 `requirements.txt` 不加入 torch。
- 代码注释用英文；面向用户的界面/README 文字：根 README 为韩文，`annotation_tool/*.md` 为中文。
- 全部工作在 `feat/windows-exe` 分支，最终以一个 PR 合入 `main`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `labeling_tool/core/app_paths.py`（新） | `is_frozen()`、`app_home()`、`writable_path()`：唯一决定"可写文件放哪里"的地方 |
| `labeling_tool/ui/dialog_helpers.py` | `CONFIG_PATH` 改用 `writable_path` |
| `labeling_tool/scripts/upload_session_cli.py` | 复用 `dialog_helpers.CONFIG_PATH`，删除重复定义 |
| `labeling_tool/session/workspace.py` | `DEFAULT_DATA_ROOT` 改用 `writable_path` |
| `annotation_tool/configs.py` | 数据集 / 权重 / classes.json 改用 `writable_path` |
| `labeling_tool/selftest.py`（新） | `run_selftest(variant) -> int` |
| `labeling_tool/app.py` | `main(argv)` 识别 `--selftest[=variant]` |
| `packaging/labeling_tool.spec`（新） | PyInstaller 配置，`LT_VARIANT=lite|full` |
| `.github/workflows/build-windows.yml`（新） | 打包 + 测试 + 自检 + 发布 |
| `tests/test_app_paths.py`、`tests/test_selftest.py`（新） | 上述逻辑的测试 |
| `README.md`、`annotation_tool/USAGE.md` | exe 使用说明 |

---

### Task 1: 可写路径 `app_paths` 及接入

**Files:**
- Create: `labeling_tool/core/app_paths.py`
- Modify: `labeling_tool/ui/dialog_helpers.py:9`、`labeling_tool/scripts/upload_session_cli.py:24`、`labeling_tool/session/workspace.py:13-14`、`annotation_tool/configs.py`（`DEFAULT_DATASET_DIR`、`CLASSES_FILE`、`SAM2_CHECKPOINT`、`SAM3_CHECKPOINT`）
- Test: `tests/test_app_paths.py`

**Interfaces:**
- Produces: `labeling_tool.core.app_paths.is_frozen() -> bool`、`app_home() -> Path`、`writable_path(source_path: Path, frozen_name: str) -> Path`、`REPO_ROOT: Path`

- [ ] **Step 1: 写失败测试** `tests/test_app_paths.py`

```python
"""Writable locations: unchanged from source, next to the exe when frozen."""
import subprocess
import sys
from pathlib import Path

from labeling_tool.core import app_paths

ROOT = Path(__file__).resolve().parent.parent


def test_source_mode_paths_are_unchanged():
    from labeling_tool.ui.dialog_helpers import CONFIG_PATH
    from labeling_tool.session.workspace import DEFAULT_DATA_ROOT
    from annotation_tool import configs
    assert not app_paths.is_frozen()
    assert app_paths.app_home() == ROOT
    assert CONFIG_PATH == ROOT / "labeling_tool" / "config.json"
    assert DEFAULT_DATA_ROOT == ROOT / "labeling_tool" / "data"
    # few-shot weights stay relative to the working directory from source
    assert Path(configs.SAM3_CHECKPOINT) == Path("checkpoint/sam3.pt")
    assert Path(configs.SAM2_CHECKPOINT) == Path("checkpoint/sam2.1_hiera_base_plus.pt")
    assert configs.DEFAULT_DATASET_DIR == Path("dataset")


def test_frozen_helpers(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "LabelingTool.exe"))
    assert app_paths.is_frozen()
    assert app_paths.app_home() == tmp_path
    assert app_paths.writable_path(Path("ignored"), "config.json") == tmp_path / "config.json"


def test_frozen_module_constants_live_next_to_exe(tmp_path):
    # module-level constants are computed at import: check them in a fresh
    # interpreter that pretends to be the PyInstaller exe
    exe = tmp_path / "LabelingTool.exe"
    code = (
        "import sys; sys.frozen = True; sys.executable = %r\n"
        "from labeling_tool.ui import dialog_helpers as d\n"
        "from labeling_tool.session import workspace as w\n"
        "from annotation_tool import configs as c\n"
        "print(d.CONFIG_PATH, w.DEFAULT_DATA_ROOT, c.SAM3_CHECKPOINT,\n"
        "      c.SAM2_CHECKPOINT, c.CLASSES_FILE, c.DEFAULT_DATASET_DIR, sep='\\n')\n"
    ) % str(exe)
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split("\n")
    assert [Path(p) for p in out[:6]] == [
        tmp_path / "config.json",
        tmp_path / "data",
        tmp_path / "checkpoint" / "sam3.pt",
        tmp_path / "checkpoint" / "sam2.1_hiera_base_plus.pt",
        tmp_path / "classes.json",
        tmp_path / "dataset",
    ]


def test_upload_cli_reuses_config_path():
    from labeling_tool.scripts import upload_session_cli
    from labeling_tool.ui import dialog_helpers
    assert upload_session_cli.CONFIG_PATH is dialog_helpers.CONFIG_PATH
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_paths.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError: No module named 'labeling_tool.core.app_paths'`

- [ ] **Step 3: 实现** `labeling_tool/core/app_paths.py`

```python
"""Where the app may write files, for source runs and PyInstaller builds.

Source run: every caller keeps its historical location (passed in as
``source_path``), so existing checkouts and their data are untouched.
Frozen (LabelingTool.exe): writable state lives next to the exe, so the whole
folder is portable and survives replacing ``_internal/`` on upgrade.
Read-only bundled resources (ONNX models, BPE vocab) keep using ``__file__``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def is_frozen() -> bool:
    """True inside a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def app_home() -> Path:
    """Folder containing LabelingTool.exe when frozen, else the repo root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return REPO_ROOT


def writable_path(source_path: Path, frozen_name: str) -> Path:
    """``source_path`` from source; ``app_home() / frozen_name`` in the exe."""
    return app_home() / frozen_name if is_frozen() else Path(source_path)
```

`labeling_tool/ui/dialog_helpers.py`：

```python
from labeling_tool.core.app_paths import writable_path

CONFIG_PATH = writable_path(
    Path(__file__).resolve().parent.parent / "config.json", "config.json")
```

`labeling_tool/scripts/upload_session_cli.py`：删除第 24 行的 `CONFIG_PATH = ...`，改为

```python
from labeling_tool.ui.dialog_helpers import CONFIG_PATH
```

`labeling_tool/session/workspace.py`：

```python
from labeling_tool.core.app_paths import writable_path

# Package root (the labeling_tool/ directory); from source, workspace data lives
# under it so a checkout carries its sessions (no ~/ scattering). In the exe it
# lives next to LabelingTool.exe instead.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = writable_path(_PACKAGE_ROOT / "data", "data")
```

`annotation_tool/configs.py`（顶部加 `from labeling_tool.core.app_paths import writable_path`）：

```python
DEFAULT_DATASET_DIR = writable_path(Path("./dataset"), "dataset")
...
CLASSES_FILE = writable_path(Path(__file__).parent / "classes.json", "classes.json")
...
SAM2_CHECKPOINT = str(writable_path(Path("./checkpoint/sam2.1_hiera_base_plus.pt"),
                                    "checkpoint/sam2.1_hiera_base_plus.pt"))
SAM3_CHECKPOINT = str(writable_path(Path("./checkpoint/sam3.pt"), "checkpoint/sam3.pt"))
```

- [ ] **Step 4: 运行确认通过，并跑全部测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: 全部 PASS（新增 4 个）

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/app_paths.py labeling_tool/ui/dialog_helpers.py \
        labeling_tool/scripts/upload_session_cli.py labeling_tool/session/workspace.py \
        annotation_tool/configs.py tests/test_app_paths.py
git commit -m "feat: keep writable files next to the exe when frozen (app_paths)"
```

---

### Task 2: `--selftest=lite|full`

**Files:**
- Create: `labeling_tool/selftest.py`
- Modify: `labeling_tool/app.py`（`main` 签名与开头）
- Test: `tests/test_selftest.py`

**Interfaces:**
- Consumes: `app_paths.app_home()`（Task 1）
- Produces: `labeling_tool.selftest.run_selftest(variant: str) -> int`（0=通过，1=有失败，2=variant 非法）；`labeling_tool.app.main(argv: list[str] | None = None) -> int`；CLI `LabelingTool.exe --selftest=lite|full`，报告写入 `<app_home>/selftest.log`

- [ ] **Step 1: 写失败测试** `tests/test_selftest.py`

```python
"""Build smoke test entry point used by CI on the packaged exe."""
import importlib.util

from labeling_tool import selftest


def test_lite_passes_and_writes_log(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "app_home", lambda: tmp_path)
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "torch" else real_find_spec(name, *a))
    assert selftest.run_selftest("lite") == 0
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "OK   import labeling_tool.ui.login_dialog" in log
    assert "OK   MobileSAM ONNX models" in log
    assert "RESULT: PASS" in log


def test_lite_fails_when_torch_is_bundled(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "app_home", lambda: tmp_path)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: object())
    monkeypatch.setattr(selftest, "COMMON_MODULES", ())
    monkeypatch.setattr(selftest, "_check_onnx", lambda: None)
    monkeypatch.setattr(selftest, "_check_login_dialog", lambda: None)
    assert selftest.run_selftest("lite") == 1
    assert "FAIL torch not bundled" in (tmp_path / "selftest.log").read_text(encoding="utf-8")


def test_full_reports_missing_module(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "app_home", lambda: tmp_path)
    monkeypatch.setattr(selftest, "COMMON_MODULES", ())
    monkeypatch.setattr(selftest, "_check_onnx", lambda: None)
    monkeypatch.setattr(selftest, "_check_login_dialog", lambda: None)
    monkeypatch.setattr(selftest, "FULL_MODULES", ("definitely_missing_mod_xyz",))
    monkeypatch.setattr(selftest, "_check_bpe", lambda: None)
    monkeypatch.setattr(selftest, "_check_sam2_cfg", lambda: None)
    assert selftest.run_selftest("full") == 1
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "FAIL import definitely_missing_mod_xyz" in log
    assert "RESULT: FAIL" in log


def test_unknown_variant():
    assert selftest.run_selftest("medium") == 2


def test_app_main_dispatches_selftest(monkeypatch):
    from labeling_tool import app
    monkeypatch.setattr(selftest, "run_selftest", lambda variant: {"full": 7}.get(variant, 3))
    assert app.main(["--selftest=full"]) == 7
    assert app.main(["--selftest"]) == 3          # bare flag -> lite
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selftest.py -q -p no:cacheprovider`
Expected: FAIL，`ImportError: cannot import name 'selftest'`

- [ ] **Step 3: 实现** `labeling_tool/selftest.py`

```python
"""``LabelingTool.exe --selftest=lite|full``: import-level smoke test for builds.

CI runs it on the packaged exe right after PyInstaller to catch modules and
data files missing from the bundle (the usual failure with torch / SAM). It
never shows a window. The windowed exe has no console, so the report is also
written to ``<app_home>/selftest.log``.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path

from labeling_tool.core.app_paths import app_home

COMMON_MODULES = (
    "numpy", "cv2", "skimage", "onnxruntime", "requests",
    "labeling_tool.ui.login_dialog",
    "labeling_tool.ui.fetch_dialog",
    "labeling_tool.ui.main_window",
)
FULL_MODULES = (
    "torch",
    "sam3.model_builder",
    "sam3.model.sam3_image_processor",
    "sam2.build_sam",
    "sam2.sam2_image_predictor",
    "annotation_tool.ui.main_window",
)

_qt_app = None  # keep the QApplication alive for the whole run


def _check_onnx() -> None:
    from labeling_tool.core.sam.predictor import default_model_paths, models_available
    if not models_available():
        raise FileNotFoundError(", ".join(str(p) for p in default_model_paths()))


def _check_login_dialog() -> None:
    """Qt platform plugins + stylesheet + login dialog construct offscreen."""
    global _qt_app
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from labeling_tool.core.window.styles import STYLESHEET
    from labeling_tool.ui.login_dialog import LoginDialog
    _qt_app = QApplication.instance() or QApplication(["selftest"])
    _qt_app.setStyleSheet(STYLESHEET)
    LoginDialog().deleteLater()


def _check_no_torch() -> None:
    if importlib.util.find_spec("torch") is not None:
        raise RuntimeError("torch is present in a lite build")


def _check_bpe() -> None:
    from annotation_tool import configs
    if not Path(configs.SAM3_BPE_PATH).is_file():
        raise FileNotFoundError(configs.SAM3_BPE_PATH)


def _check_sam2_cfg() -> None:
    from importlib.resources import files
    from annotation_tool import configs
    cfg = files("sam2").joinpath(configs.SAM2_MODEL_CFG)
    if not cfg.is_file():
        raise FileNotFoundError(f"sam2/{configs.SAM2_MODEL_CFG}")


def _checks(variant: str):
    """(name, callable) pairs; each callable raises on failure."""
    for mod in COMMON_MODULES:
        yield f"import {mod}", lambda mod=mod: importlib.import_module(mod)
    yield "MobileSAM ONNX models", _check_onnx
    yield "Qt login dialog (offscreen)", _check_login_dialog
    if variant == "lite":
        yield "torch not bundled", _check_no_torch
        return
    for mod in FULL_MODULES:
        yield f"import {mod}", lambda mod=mod: importlib.import_module(mod)
    yield "SAM3 BPE vocab", _check_bpe
    yield "SAM2 model config", _check_sam2_cfg


def run_selftest(variant: str) -> int:
    """Run every check; 0 = all passed, 1 = failures, 2 = unknown variant."""
    if variant not in ("lite", "full"):
        print(f"unknown selftest variant: {variant!r} (use lite or full)")
        return 2
    lines, failed = [f"selftest variant={variant} home={app_home()}"], 0
    for name, check in _checks(variant):
        try:
            check()
            lines.append(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            lines.append(f"FAIL {name}: {type(exc).__name__}: {exc}")
    lines.append("RESULT: " + ("PASS" if not failed else f"FAIL ({failed})"))
    report = "\n".join(lines) + "\n"
    print(report, end="")
    (app_home() / "selftest.log").write_text(report, encoding="utf-8")
    return 0 if not failed else 1
```

`labeling_tool/app.py`：把 `def main() -> int:` 与其第一行替换为

```python
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for arg in argv:
        if arg.startswith("--selftest"):
            # build smoke test (CI): no window, exit code = result
            from labeling_tool import selftest
            return selftest.run_selftest(arg.partition("=")[2] or "lite")

    app = QApplication(sys.argv)
```

- [ ] **Step 4: 运行确认通过，并跑全部测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/selftest.py labeling_tool/app.py tests/test_selftest.py
git commit -m "feat: --selftest=lite|full build smoke test"
```

---

### Task 3: PyInstaller spec + 本地（Linux）lite 打包验证

**Files:**
- Create: `packaging/labeling_tool.spec`
- Modify: `.gitignore`（加入 `build/`、`dist/`）
- Test: 本地 PyInstaller 打包 + 运行打包产物 `--selftest=lite`（Linux 产物只用于验证 spec 逻辑，Windows 产物由 Task 4 的 CI 生成）

**Interfaces:**
- Consumes: `--selftest`（Task 2）
- Produces: `LT_VARIANT=lite|full pyinstaller packaging/labeling_tool.spec` → `dist/LabelingTool/LabelingTool(.exe)`

- [ ] **Step 1: 写 spec** `packaging/labeling_tool.spec`

```python
# PyInstaller spec for LabelingTool (onedir, windowed).
#   LT_VARIANT=lite  production tool only (no torch)          -> ~400 MB
#   LT_VARIANT=full  + few-shot annotation_tool (torch/SAM)   -> ~5 GB
# Build from the repo root:  pyinstaller --noconfirm packaging/labeling_tool.spec
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

VARIANT = os.environ.get("LT_VARIANT", "lite")
if VARIANT not in ("lite", "full"):
    raise SystemExit(f"LT_VARIANT must be lite or full, got {VARIANT!r}")

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def _not_tests_or_scripts(name):
    return ".tests" not in name and ".scripts" not in name


datas = [(os.path.join(ROOT, "labeling_tool", "models", "sam", "*.onnx"),
          os.path.join("labeling_tool", "models", "sam"))]
binaries = []
# labeling_tool imports several modules lazily inside functions
hiddenimports = collect_submodules("labeling_tool", filter=_not_tests_or_scripts)
excludes = []

if VARIANT == "full":
    hiddenimports += collect_submodules("annotation_tool", filter=_not_tests_or_scripts)
    # BPE vocab etc.; never ship a developer's classes.json
    datas += collect_data_files("annotation_tool", excludes=["**/classes.json"])
    for pkg in ("sam3", "sam2", "timm"):
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
else:
    excludes = ["torch", "torchvision", "torchaudio", "triton",
                "sam2", "sam3", "timm", "annotation_tool"]

a = Analysis(
    [os.path.join(ROOT, "labeling_tool", "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LabelingTool",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LabelingTool")
```

`.gitignore` 追加：

```
# PyInstaller output
build/
dist/
```

- [ ] **Step 2: 本地打包 lite**

Run:
```bash
.venv/bin/pip install -q "pyinstaller==6.22.3"
SP=$(mktemp -d)   # build output stays outside the repo
LT_VARIANT=lite .venv/bin/pyinstaller --noconfirm --log-level WARN \
    --distpath $SP/dist --workpath $SP/build packaging/labeling_tool.spec
```
Expected: 生成 `$SP/dist/LabelingTool/LabelingTool`，无 ERROR。

- [ ] **Step 3: 运行打包产物自检**

Run: `QT_QPA_PLATFORM=offscreen $SP/dist/LabelingTool/LabelingTool --selftest=lite; echo rc=$?`
Expected: 所有行 `OK`，`RESULT: PASS`，`rc=0`；且 `$SP/dist/LabelingTool/_internal` 中没有 `torch` 目录（`ls $SP/dist/LabelingTool/_internal | grep -c '^torch$'` 输出 0）。
若有 `FAIL import …`：把缺失模块加入 spec 的 `hiddenimports`，重复 Step 2–3。

- [ ] **Step 4: 提交**

```bash
git add packaging/labeling_tool.spec .gitignore
git commit -m "build: PyInstaller spec for lite / full LabelingTool"
```

---

### Task 4: GitHub Actions 打包 workflow

**Files:**
- Create: `.github/workflows/build-windows.yml`

**Interfaces:**
- Consumes: spec（Task 3）、`--selftest`（Task 2）
- Produces: artifact `LabelingTool-<variant>-<version>`；tag 时 Release 资产 `LabelingTool-lite-<ver>.zip`、`LabelingTool-full-<ver>.7z.001…`

- [ ] **Step 1: 写 workflow**

```yaml
# Build the Windows LabelingTool exe (lite + full) with PyInstaller.
# Triggers: manual run, version tags (v*) -> GitHub Release, and PRs that
# touch the build so packaging breakage shows up before merging.
name: build-windows

on:
  workflow_dispatch:
  push:
    tags: ["v*"]
  pull_request:
    paths:
      - "packaging/**"
      - ".github/workflows/build-windows.yml"
      - "requirements*.txt"
      - "labeling_tool/app.py"
      - "labeling_tool/selftest.py"
      - "labeling_tool/core/app_paths.py"

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest
    timeout-minutes: 120
    strategy:
      fail-fast: false
      matrix:
        variant: [lite, full]
    env:
      LT_VARIANT: ${{ matrix.variant }}
      QT_QPA_PLATFORM: offscreen
      PIP_DISABLE_PIP_VERSION_CHECK: "1"
    defaults:
      run:
        shell: pwsh
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Version
        run: |
          $ver = if ($env:GITHUB_REF_TYPE -eq 'tag') { $env:GITHUB_REF_NAME } else { "dev-" + $env:GITHUB_SHA.Substring(0, 7) }
          "LT_VERSION=$ver" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8

      - name: Install production dependencies
        run: pip install -r requirements-dev.txt "pyinstaller==6.22.3"

      - name: Install few-shot dependencies (full)
        if: matrix.variant == 'full'
        env:
          SAM2_BUILD_CUDA: "0"
        run: |
          pip install "torch==2.5.1" "torchvision==0.20.1" --index-url https://download.pytorch.org/whl/cu124
          pip install "triton-windows==3.1.0.post17" "sam3==0.1.4" huggingface_hub psutil
          pip install "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"
          python -c "import sam3.model_builder, sam2.build_sam; print('few-shot imports OK')"

      - name: Tests
        run: |
          $suites = @("tests", "labeling_tool/tests")
          if ($env:LT_VARIANT -eq 'full') { $suites += "annotation_tool/tests" }
          python -m pytest @suites -q -p no:cacheprovider

      - name: Build exe
        run: pyinstaller --noconfirm --log-level WARN packaging/labeling_tool.spec

      - name: Selftest packaged exe
        run: |
          $p = Start-Process -FilePath dist\LabelingTool\LabelingTool.exe -ArgumentList "--selftest=$env:LT_VARIANT" -Wait -PassThru
          Get-Content dist\LabelingTool\selftest.log
          Remove-Item dist\LabelingTool\selftest.log
          if ($p.ExitCode -ne 0) { throw "selftest failed with exit code $($p.ExitCode)" }

      - name: Launch smoke test (login screen stays up)
        run: |
          $p = Start-Process -FilePath dist\LabelingTool\LabelingTool.exe -PassThru
          Start-Sleep -Seconds 20
          if ($p.HasExited) { throw "LabelingTool.exe exited early with code $($p.ExitCode)" }
          Stop-Process -Id $p.Id -Force
          # the app may create these next to the exe; never ship them
          Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist\LabelingTool\data, dist\LabelingTool\config.json

      - name: Package
        run: |
          Set-Content -Path dist\LabelingTool\VERSION.txt -Value "$env:LT_VERSION ($env:LT_VARIANT)"
          Remove-Item -Recurse -Force build
          pip cache purge
          New-Item -ItemType Directory -Force out | Out-Null
          $name = "LabelingTool-$env:LT_VARIANT-$env:LT_VERSION"
          if ($env:LT_VARIANT -eq 'lite') {
            7z a -tzip "out\$name.zip" .\dist\LabelingTool
          } else {
            # GitHub Release assets must be < 2 GiB each
            7z a -v1900m "out\$name.7z" .\dist\LabelingTool
          }
          Get-ChildItem out | Format-Table Name, Length

      - uses: actions/upload-artifact@v4
        with:
          name: LabelingTool-${{ matrix.variant }}-${{ env.LT_VERSION }}
          path: out/*
          compression-level: 0

      - name: Publish release assets (tags only)
        if: github.ref_type == 'tag'
        uses: softprops/action-gh-release@v2
        with:
          files: out/*
```

- [ ] **Step 2: 本地校验 YAML 语法**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build-windows.yml')); print('yaml ok')"`
Expected: `yaml ok`

- [ ] **Step 3: 提交、push，开 draft PR 触发 CI**

`workflow_dispatch` 只能运行默认分支上已存在的 workflow，所以首次运行借助 PR 触发（同一个 PR 最终合入 `main`）：

```bash
git add .github/workflows/build-windows.yml
git commit -m "ci: build Windows exe (lite / full) with GitHub Actions"
git push
gh pr create --draft --base main --head feat/windows-exe \
  --title "feat: single launcher, tool tabs on login, 로컬 작업 job list, Windows exe build" \
  --body "Draft: CI builds the lite / full Windows exe. Full description is written in Task 6 before marking ready."
gh run watch
```
Expected: lite / full 两个 job 均通过；artifact 可在 run 页面下载。

- [ ] **Step 4: 按 CI 日志修复**

对 `Selftest packaged exe` 中的每个 `FAIL import X`：在 spec 中加入 `hiddenimports += ["X"]`（或对该包 `collect_all`）；对缺失数据文件：加入 `datas`。每轮提交并 push，直到两个 job 均为绿色。若 `import sam3.model_builder` 在 Windows 上即使安装 `triton-windows` 仍无法导入，按设计文档第 6 节：full 版把 `configs.BACKEND` 默认改为 `sam2`，并从 `FULL_MODULES` 中移除 sam3 项，在 PR 中说明。

---

### Task 5: 文档

**Files:**
- Modify: `README.md`（新增「Windows 실행 파일 (exe)」一节）、`annotation_tool/USAGE.md`（full 版说明）、`docs/superpowers/specs/2026-09-21-windows-exe-packaging-design.md`（第 1 节 checkpoint 源码行为修正）

- [ ] **Step 1: README 新增一节**（放在「## 실행」之前）

```markdown
## Windows 실행 파일 (exe) — Python 설치 불필요

GitHub 의 **Releases**(태그 버전) 또는 **Actions → build-windows** 실행 결과(artifact)에서 받습니다.

| 파일 | 내용 | 대상 PC |
|---|---|---|
| `LabelingTool-lite-<버전>.zip` | 온라인 라벨링 + 로컬 작업 | 일반 PC (GPU 불필요) |
| `LabelingTool-full-<버전>.7z.001, .002 …` | lite + Few-shot 라벨링 (torch, SAM3/SAM2) | NVIDIA GPU PC |

1. 압축을 풀고 `LabelingTool\LabelingTool.exe` 를 더블클릭합니다.
   full 판은 **7-Zip 으로 `.7z.001` 을 열어** 풉니다 (분할 압축).
2. 처음 실행 시 "Windows 의 PC 보호" 창이 뜨면 **「추가 정보」→「실행」** 을 누릅니다 (코드 서명 없음).
3. 로그인 정보(`config.json`)와 받은 작업(`data\`)은 **exe 와 같은 폴더**에 저장됩니다.
4. full 판: SAM 가중치를 `LabelingTool\checkpoint\` 에 넣으세요 (`sam3.pt`, `sam2.1_hiera_base_plus.pt`).

**업그레이드**: 새 버전을 다른 폴더에 풀고, 이전 폴더의 `config.json`, `data\`, `checkpoint\` 를 복사합니다.
```

- [ ] **Step 2: `annotation_tool/USAGE.md` 在「## 5. 运行」末尾追加**

```markdown
**Windows exe（full 版）**：无需安装 Python。用 7-Zip 解压 `LabelingTool-full-<版本>.7z.001`，
把权重放到 `LabelingTool\checkpoint\`（`sam3.pt`、`sam2.1_hiera_base_plus.pt`），双击
`LabelingTool.exe` → 登录界面「Few-shot 라벨링」标签页。`classes.json` 保存在 exe 同目录。
```

- [ ] **Step 3: 修正设计文档第 1 节**：表格"few-shot 权重"行的源码列改为 `./checkpoint/…`（相对当前工作目录，**不变**）；删除"few-shot 的 `./checkpoint` 改为锚定仓库根目录"一句，改为"few-shot 的权重与数据集路径在源码运行时仍相对当前工作目录（保持现有 `cd` 到其他目录运行的用法）"。

- [ ] **Step 4: 提交并 push**

```bash
git add README.md annotation_tool/USAGE.md docs/superpowers/specs/2026-09-21-windows-exe-packaging-design.md
git commit -m "docs: Windows exe download / upgrade / weights"
git push
```

---

### Task 6: 收尾

- [ ] **Step 1:** 全部测试：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider` → 全部 PASS
- [ ] **Step 2:** 确认 CI 两个 job 绿色、artifact 可下载；`git ls-files | grep -iE "(^|/)data/|config\.json$|classes\.json$|\.(pt|pth)$"` 无输出
- [ ] **Step 3:** 更新 PR 描述（包含本分支全部内容：启动脚本、登录界面选择工具、로컬 작업、exe 打包），将 draft 改为 ready：`gh pr ready`
- [ ] **Step 4:** 请用户在 Windows 上下载 lite artifact 实测（登录 → 获取 → 标注 → 上传；로컬 작업 打开已下载 job），full 版在 GPU 机器上打开 few-shot 并完成一次分割；用户在网页上合并 PR
