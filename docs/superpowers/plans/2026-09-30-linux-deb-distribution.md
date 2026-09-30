# Linux deb 分发 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付与 Windows 功能对等的 Linux deb 分发：双包分层、应用内增量更新、同一 tag 同步发布。

**Architecture:** 复用现有的 PyInstaller onedir + `packaging/layers.py` 分层模型，把 Inno Setup 的角色换成两个 deb —— 运行时包以 runtime id 作包版本，应用包用 `Depends` 精确钉住它，由 dpkg 取代 `installer.iss` 中手写的运行时校验。客户端侧把 `UpdateInfo` 从单资产改为资产列表，并按平台选择资产名与安装命令。

**Tech Stack:** Python 3.12.10、PyInstaller onedir、`dpkg-deb`、pkexec/polkit、PyQt5、pytest、GitHub Actions

**Spec:** `docs/superpowers/specs/2026-09-30-linux-deb-distribution-design.md`

## Global Constraints

- 构建机：`ubuntu-22.04`（glibc 2.35），产物须同时支持 Ubuntu 22.04 与 24.04。**不得**改用 `ubuntu-latest`。
- Python：`3.12.10`，与 Windows 侧逐位一致（解释器属运行时层）。
- torch：`2.5.1+cu124`，与 Windows 一致；deb **不得**声明对 NVIDIA 驱动包的依赖。
- 安装前缀：`/opt/lm-labeling-tool/`。
- 包名：应用包 `lm-labeling-tool`，运行时包 `lm-labeling-tool-runtime`；架构 `amd64`。
- 运行时包的 `Version` 字段恒为 `0~<runtime-id>`（如 `0~r3f8a1c92`）；应用包的 `Version` 为纯版本号（如 `1.4.1`）。
- deb 文件名：应用包 `lm-labeling-tool_<version>-<runtime-id>_amd64.deb`；运行时包 `lm-labeling-tool-runtime_<version>_amd64.deb`。文件名与 `Version` 字段**刻意不一致**，理由见 spec 7.2。
- 可写状态：`~/.local/share/lm-labeling-tool/`；下载缓存：`~/.cache/lm-labeling-tool/`。
- **Windows 的一切既有行为必须逐字节不变**，尤其 `app_paths.writable_path()` 的返回值与资产命名。
- 代码注释一律英文；Python 4 空格缩进、`snake_case`。
- 每个 release 必须挂齐四个资产：Windows full/app、Linux runtime/app。

## Review Focus

这五类输入 spec 有所暗示、但若不显式覆盖最可能伤到使用者，按可能性排序。每一条都已落到下面对应任务的测试步骤中。

1. **`HOME` 未设置或 `~/.local/share` 不可写**（sudo 运行、服务账户、只读家目录）：`user_data_home()` 不应在 import 期或启动期抛异常致程序无法启动 → Task 2。
2. **`XDG_DATA_HOME` 为空串或相对路径**：空串必须视为未设置而回落到 `~/.local/share`，相对路径不得把数据写到当前工作目录 → Task 2。
3. **系统无 `pkexec`**（纯 SSH 会话、WSL、精简桌面）：更新须给出可读提示，而非 `FileNotFoundError` 崩溃 → Task 6。
4. **release 中 Linux app deb 存在但 runtime deb 缺失**（spec 7.2.1 所述的静默故障）：`find_update` 必须整体放弃该全量更新，而不是提供一个装不上的半套 → Task 5。
5. **`~/.cache` 不可写或空间不足**：1.5 GB 下载失败须报可读错误并保留应用可用，而非留下半个文件让 dpkg 去装 → Task 7。

---

### Task 1: layers.py 平台化

现有分层白名单硬编码了 Windows 的入口名与系统 DLL 规则。Linux 构建要复用同一套规则，因此把平台作为显式参数引入，默认由 `sys.platform` 推断，使 CI 中既有的 `layers.py runtime-id <dist>` 调用无需改动。

**Files:**
- Modify: `packaging/layers.py`
- Test: `labeling_tool/tests/test_layers.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `WINDOWS = "win32"`, `LINUX = "linux"`
  - `current_platform() -> str`
  - `app_entry_name(platform: str | None = None) -> str`
  - `app_layer_prefixes(platform: str | None = None) -> tuple[str, ...]`
  - `is_app_layer(relpath: str, platform: str | None = None) -> bool`
  - `is_build_machine_file(relpath: str, platform: str | None = None) -> bool`
  - `iter_runtime_files(dist_dir, platform=None)`、`runtime_manifest(dist_dir, platform=None)`、`compute_runtime_id(dist_dir, platform=None)`、`stage_app_layer(dist_dir, out_dir, platform=None)`

- [ ] **Step 1: 写失败测试**

追加到 `labeling_tool/tests/test_layers.py`：

```python
def test_app_entry_name_is_platform_specific():
    assert layers.app_entry_name(layers.WINDOWS) == "LM_LabelingTool.exe"
    assert layers.app_entry_name(layers.LINUX) == "LM_LabelingTool"


def test_linux_entry_is_app_layer_and_windows_entry_is_not():
    # The Linux build has no .exe; classifying the other platform's entry
    # as app layer would silently ship it in the wrong package.
    assert layers.is_app_layer("LM_LabelingTool", layers.LINUX) is True
    assert layers.is_app_layer("LM_LabelingTool.exe", layers.LINUX) is False
    assert layers.is_app_layer("LM_LabelingTool.exe", layers.WINDOWS) is True
    assert layers.is_app_layer("LM_LabelingTool", layers.WINDOWS) is False


def test_shared_app_layer_prefixes_hold_on_both_platforms():
    for platform in (layers.WINDOWS, layers.LINUX):
        assert layers.is_app_layer("build-info.json", platform) is True
        assert layers.is_app_layer("_internal/labeling_tool/app.py", platform) is True
        assert layers.is_app_layer("_internal/annotation_tool/x.py", platform) is True
        assert layers.is_app_layer("_internal/torch/lib/c10.so", platform) is False
        assert layers.is_app_layer("_internal/models/sam/mobile_sam.onnx", platform) is False


def test_build_machine_files_are_a_windows_only_concept():
    # The exclusion exists because PyInstaller copies UCRT/VC++ DLLs from the
    # build machine's Windows. Nothing analogous is taken from the Linux host.
    assert layers.is_build_machine_file("_internal/vcruntime140.dll", layers.WINDOWS) is True
    assert layers.is_build_machine_file("_internal/vcruntime140.dll", layers.LINUX) is False
    assert layers.is_build_machine_file("_internal/libstdc++.so.6", layers.LINUX) is False


def test_runtime_id_differs_between_platforms_for_the_same_tree(tmp_path):
    # Same relative paths, different entry-name rule: the Windows run counts
    # LM_LabelingTool as a runtime file, the Linux run does not.
    (tmp_path / "_internal").mkdir()
    (tmp_path / "LM_LabelingTool").write_bytes(b"x" * 10)
    (tmp_path / "_internal" / "libtorch.so").write_bytes(b"y" * 20)
    win = layers.compute_runtime_id(tmp_path, layers.WINDOWS)
    linux = layers.compute_runtime_id(tmp_path, layers.LINUX)
    assert win != linux
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_layers.py -q`
Expected: FAIL — `AttributeError: module 'packaging.layers' has no attribute 'app_entry_name'`

- [ ] **Step 3: 实现**

在 `packaging/layers.py` 中，把模块级的 `APP_LAYER_PREFIXES` 常量替换为平台相关的函数，并给每个公开函数加 `platform` 参数：

```python
import sys

WINDOWS = "win32"
LINUX = "linux"


def current_platform() -> str:
    """The platform whose layout the caller means, defaulting to this host.

    CI builds each platform on its own runner, so the default is right there;
    the tests pass it explicitly to check both rules from one machine."""
    return WINDOWS if sys.platform.startswith("win") else LINUX


def app_entry_name(platform: str | None = None) -> str:
    """The executable PyInstaller emits at the root of the onedir output."""
    return "LM_LabelingTool.exe" if (platform or current_platform()) == WINDOWS \
        else "LM_LabelingTool"


def app_layer_prefixes(platform: str | None = None) -> tuple[str, ...]:
    """Relative paths (forward slashes) that belong to the app layer. An entry
    ending in "/" matches a whole directory; any other entry matches that one
    file exactly.

    The whitelist runs this way round on purpose: anything not named here is
    runtime, so a newly added third-party dependency changes the runtime id
    and forces a full reinstall, instead of riding along inside a partial app
    package that would install missing its own dependency."""
    return (
        app_entry_name(platform),
        # Written by CI after the runtime id is computed, and it carries the
        # version string -- if it counted as a runtime file the id would move
        # on every release and layering would never engage.
        "build-info.json",
        "_internal/labeling_tool/",
        "_internal/annotation_tool/",
    )
```

`is_app_layer` 与 `is_build_machine_file` 改为：

```python
def is_build_machine_file(relpath: str, platform: str | None = None) -> bool:
    """True for a system runtime DLL that PyInstaller took from the build
    machine rather than from a dependency.

    Windows-only by construction: the exclusion exists because GitHub refreshes
    its Windows runner image weekly and the UCRT/VC++ forwarders move the
    runtime id for nothing. PyInstaller takes no equivalent files from the
    Linux host -- anything it collects there comes out of a wheel."""
    if (platform or current_platform()) != WINDOWS:
        return False
    rel = relpath.replace("\\", "/")
    if not rel.startswith("_internal/"):
        return False
    name = rel[len("_internal/"):]
    if "/" in name or not name.lower().endswith(".dll"):
        return False
    return name.lower().startswith(_SYSTEM_RUNTIME_PREFIXES)


def is_app_layer(relpath: str, platform: str | None = None) -> bool:
    """True when this file ships in the small app-only package."""
    rel = relpath.replace("\\", "/")
    if any(rel.startswith(x) for x in APP_LAYER_EXCLUSIONS):
        return False
    for prefix in app_layer_prefixes(platform):
        if prefix.endswith("/"):
            if rel.startswith(prefix):
                return True
        elif rel == prefix:
            return True
    return False
```

`iter_runtime_files`、`runtime_manifest`、`compute_runtime_id`、`stage_app_layer` 各加一个 `platform: str | None = None` 参数并原样向下传递。`main()` 的 CLI 不加平台参数 —— CI 在各自的 runner 上构建各自的平台，默认推断即正确。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_layers.py -q`
Expected: PASS，且**既有测试全部仍通过**（`test_nothing_runtime_layer_lives_under_the_cleared_directory` 等不变式在两个平台上都必须成立）

- [ ] **Step 5: 全量回归**

Run: `python -m pytest labeling_tool/tests -q`
Expected: PASS。`packaging/layers.py` 被 `test_installer_script.py`、`test_reuse_full.py` 间接使用，签名改动不得波及它们。

- [ ] **Step 6: Commit**

```bash
git add packaging/layers.py labeling_tool/tests/test_layers.py
git commit -m "refactor(layers): make the layer split platform-aware

The whitelist hardcoded LM_LabelingTool.exe and the Windows system-DLL
exclusion. Both become functions of an explicit platform argument that
defaults to this host, so CI's existing runtime-id call is unchanged while
the tests can check either rule from one machine."
```

---

### Task 2: 可写状态位置

Windows 把用户状态写在可执行文件旁边；`/opt` 是 root 所有的只读目录，Linux 必须落到 XDG 目录。本任务同时覆盖 Review Focus 第 1、2 条。

**Files:**
- Modify: `labeling_tool/core/app_paths.py`
- Test: `labeling_tool/tests/test_app_paths.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces:
  - `user_data_home() -> Path`
  - `user_cache_home() -> Path`
  - `writable_path(source_path: Path, frozen_name: str) -> Path`（行为变更：frozen 时基准由 `app_home()` 改为 `user_data_home()`）

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_app_paths.py`：

```python
"""Where the app writes: beside the exe on Windows, XDG on Linux."""
from pathlib import Path

import pytest

from labeling_tool.core import app_paths


@pytest.fixture
def frozen(monkeypatch):
    """Pretend to be a PyInstaller build rooted at a given directory."""
    def _apply(platform, exe_dir):
        monkeypatch.setattr(app_paths.sys, "frozen", True, raising=False)
        monkeypatch.setattr(app_paths.sys, "executable", str(Path(exe_dir) / "LM_LabelingTool"))
        monkeypatch.setattr(app_paths.sys, "platform", platform)
    return _apply


def test_source_run_is_the_repo_root_on_every_platform(monkeypatch):
    monkeypatch.delattr(app_paths.sys, "frozen", raising=False)
    assert app_paths.user_data_home() == app_paths.REPO_ROOT


def test_windows_frozen_still_writes_beside_the_executable(frozen, tmp_path):
    # The Windows install is per-user and portable; moving its data would
    # strand every copy already installed. This must never change.
    frozen("win32", tmp_path)
    assert app_paths.user_data_home() == tmp_path
    assert app_paths.writable_path(Path("/ignored"), "config.json") == tmp_path / "config.json"


def test_linux_frozen_uses_xdg_data_home(frozen, tmp_path, monkeypatch):
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert app_paths.user_data_home() == tmp_path / "xdg" / "lm-labeling-tool"


def test_linux_frozen_falls_back_to_dot_local_share(frozen, tmp_path, monkeypatch):
    frozen("linux", tmp_path / "opt")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert app_paths.user_data_home() == tmp_path / "home" / ".local/share/lm-labeling-tool"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_xdg_data_home_is_treated_as_unset(frozen, tmp_path, monkeypatch, value):
    # An empty XDG_DATA_HOME is common in stripped login environments. Joining
    # onto it would resolve relative to the current working directory.
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_DATA_HOME", value)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert app_paths.user_data_home() == tmp_path / "home" / ".local/share/lm-labeling-tool"


def test_relative_xdg_data_home_is_rejected(frozen, tmp_path, monkeypatch):
    # The XDG spec requires an absolute path; a relative one would scatter user
    # data into whatever directory the app happened to be launched from.
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_DATA_HOME", "relative/data")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert app_paths.user_data_home() == tmp_path / "home" / ".local/share/lm-labeling-tool"


def test_missing_home_does_not_raise(frozen, tmp_path, monkeypatch):
    # Service accounts and some sudo invocations have no HOME. Raising here
    # would happen during startup and the app would never open a window.
    frozen("linux", tmp_path / "opt")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    result = app_paths.user_data_home()
    assert result.is_absolute()
    assert result.name == "lm-labeling-tool"


def test_cache_home_is_separate_from_data_home(frozen, tmp_path, monkeypatch):
    # Downloads are throwaway; keeping them out of the data directory stops a
    # 1.5 GB deb riding along in the user's backups.
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert app_paths.user_cache_home() == tmp_path / "cache" / "lm-labeling-tool"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_app_paths.py -q`
Expected: FAIL — `AttributeError: module has no attribute 'user_data_home'`

- [ ] **Step 3: 实现**

在 `labeling_tool/core/app_paths.py` 顶部加 `import os`，并新增：

```python
APP_DIR_NAME = "lm-labeling-tool"


def _xdg_dir(env_var: str, default_suffix: str) -> Path:
    """An XDG base directory, falling back when the variable is unusable.

    The spec requires an absolute path; a blank or relative value -- both seen
    in stripped login environments -- would otherwise resolve against the
    current working directory and scatter user data. Path.home() raises when
    HOME is unset, and this runs during startup, so that falls back too rather
    than leaving the app unable to open a window."""
    raw = (os.environ.get(env_var) or "").strip()
    if raw and Path(raw).is_absolute():
        return Path(raw)
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        home = Path(os.environ.get("TMPDIR") or "/tmp")
    return home / default_suffix


def user_data_home() -> Path:
    """Where the app may write. Beside the executable on Windows (the install
    is per-user and portable); XDG on Linux, where the install lives under
    /opt and is root-owned."""
    if not is_frozen():
        return REPO_ROOT
    if sys.platform == "win32":
        return app_home()
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_DIR_NAME


def user_cache_home() -> Path:
    """Where downloads land: discardable, and kept out of user_data_home() so
    a 1.5 GB update package is not swept into the user's backups."""
    if not is_frozen():
        return REPO_ROOT / ".cache"
    if sys.platform == "win32":
        return app_home()
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_DIR_NAME
```

并把 `writable_path` 改为：

```python
def writable_path(source_path: Path, frozen_name: str) -> Path:
    """``source_path`` from source; ``user_data_home() / frozen_name`` frozen."""
    return user_data_home() / frozen_name if is_frozen() else Path(source_path)
```

同时更新模块 docstring，说明 Linux 下写入位置为 XDG 目录。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_app_paths.py -q`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `python -m pytest labeling_tool/tests -q`
Expected: PASS。重点确认 `test_bundled_resources.py`、`test_workspace.py`、`test_settings.py` 不受影响 —— 它们走源码路径，`is_frozen()` 为假，行为不变。

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/core/app_paths.py labeling_tool/tests/test_app_paths.py
git commit -m "feat(paths): write user state to XDG directories on Linux

/opt is root-owned, so the Windows rule -- write beside the executable --
cannot hold there. Windows keeps that rule byte for byte; a test pins it.

Blank and relative XDG variables fall back rather than resolving against
the working directory, and a missing HOME does not raise: this runs during
startup, where an exception means no window ever opens."
```

---

### Task 3: 图标统一为 PNG

`app.py` 当前把 `.ico` 交给 `QIcon`。Qt 在 Linux 上的 ICO 支持取决于插件是否被收入，不可靠；`.desktop` 也需要一张标准位图。从既有的 `icon.svg` 生成 PNG，两个平台共用。

**Files:**
- Create: `labeling_tool/resources/icon.png`（由脚本生成并提交）
- Modify: `packaging/make_icon.py`、`labeling_tool/app.py:107`、`packaging/labeling_tool.spec`
- Test: `labeling_tool/tests/test_window_icon.py`

**Interfaces:**
- Consumes: 无
- Produces: `labeling_tool/resources/icon.png`（256×256），`resource_path("icon.png")` 可解析

- [ ] **Step 1: 写失败测试**

追加到 `labeling_tool/tests/test_window_icon.py`：

```python
def test_png_icon_resource_ships_with_the_package():
    # Qt's ICO plugin is not guaranteed to be collected into the Linux
    # build, and the .desktop entry needs a bitmap regardless.
    png = app_paths.resource_path("icon.png")
    assert png.is_file(), f"{png} missing"
    assert png.stat().st_size > 1024


def test_png_icon_loads_as_a_real_qicon():
    icon = QIcon(str(app_paths.resource_path("icon.png")))
    assert not icon.isNull()
    have = {s.width() for s in icon.availableSizes()}
    assert 256 in have, f"expected a 256px bitmap among {sorted(have)}"
```

并把既有的 `test_main_sets_the_application_window_icon` 末尾加一条断言，确认图标确实来自 PNG（`_FakeApp` 夹具原样沿用，只在 `main([])` 之后追加）：

```python
    # The icon must come from the PNG: an ICO here would be null on a Linux
    # build whose Qt has no ICO plugin, and the assertion above would still
    # pass on a developer's Windows machine.
    assert captured["icon"].availableSizes(), "the window icon carries no bitmap"
    expected = QIcon(str(app_paths.resource_path("icon.png")))
    assert (captured["icon"].availableSizes()[0].width()
            == expected.availableSizes()[0].width())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_window_icon.py -q`
Expected: FAIL — `missing .../labeling_tool/resources/icon.png`

- [ ] **Step 3: 生成 PNG 并切换引用**

在 `packaging/make_icon.py` 中增加 PNG 输出（与既有 `.ico` 生成共用同一份 SVG 渲染），然后运行它生成 `labeling_tool/resources/icon.png`（256×256，带透明通道）。

`labeling_tool/app.py:107` 改为：

```python
    # PNG rather than ICO: Qt's ICO plugin is not guaranteed to be collected
    # into the Linux build, and the .desktop entry needs a bitmap anyway.
    app.setWindowIcon(QIcon(str(resource_path("icon.png"))))
```

`packaging/labeling_tool.spec` 的 `datas` 中，把随包资源由 `ICON`（.ico）改为同时收入 PNG：

```python
ICON = os.path.join(ROOT, "labeling_tool", "resources", "icon.ico")
ICON_PNG = os.path.join(ROOT, "labeling_tool", "resources", "icon.png")
datas = [(os.path.join(ROOT, "labeling_tool", "models", "sam", "*.onnx"),
          os.path.join("models", "sam")),
         # needed at runtime as well as in the exe's resources: the title bar
         # and taskbar icon come from QApplication.setWindowIcon, not from
         # the PE resource below. PNG is used on both platforms; the .ico
         # remains only for the Windows executable's own resource.
         (ICON_PNG, os.path.join("labeling_tool", "resources"))]
```

`EXE(...)` 的 `icon=ICON` 保持不变 —— Windows 可执行文件的 PE 资源仍需 `.ico`。注意 `.ico` 仍需保留在仓库中供 `installer.iss` 的 `SetupIconFile` 使用。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_window_icon.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/resources/icon.png packaging/make_icon.py \
        labeling_tool/app.py packaging/labeling_tool.spec \
        labeling_tool/tests/test_window_icon.py
git commit -m "feat(icon): load the window icon from PNG on both platforms

Qt's ICO plugin is not guaranteed to be collected into the Linux build, and
the .desktop entry needs a bitmap. The .ico stays for the Windows PE
resource and Inno's SetupIconFile."
```

---

### Task 4: Linux 依赖锁与漂移防护

两个平台各有一份 lock，一旦分开就会各自漂移，而漂移的后果是两边功能悄悄不一致。本任务生成 Linux lock，并用测试强制两份清单保持同步。

**Files:**
- Create: `packaging/build-lock-linux.txt`
- Create: `packaging/lock_parity.py`
- Test: `labeling_tool/tests/test_lock_parity.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `lock_parity.parse_lock(text: str) -> dict[str, str]`（包名小写 → 版本）
  - `lock_parity.PLATFORM_ONLY: dict[str, str]`（包名小写 → 只存在于一侧的理由）
  - `lock_parity.compare(win_text: str, linux_text: str) -> list[str]`（返回违规描述，空列表即通过）

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_lock_parity.py`：

```python
"""The two build locks must not drift: drift means the platforms differ."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from packaging import lock_parity  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WIN_LOCK = REPO / "packaging" / "build-lock.txt"
LINUX_LOCK = REPO / "packaging" / "build-lock-linux.txt"


def test_parse_lock_ignores_comments_and_blanks():
    text = "# a comment\n\nNumPy==1.26.4\ntorch==2.5.1+cu124\n"
    assert lock_parity.parse_lock(text) == {"numpy": "1.26.4", "torch": "2.5.1+cu124"}


def test_both_locks_exist():
    assert WIN_LOCK.is_file() and LINUX_LOCK.is_file()


def test_shared_packages_pin_identical_versions():
    # A version that differs between platforms is a functional difference
    # nobody declared. Either sync it, or declare it in PLATFORM_ONLY.
    problems = lock_parity.compare(WIN_LOCK.read_text(encoding="utf-8"),
                                   LINUX_LOCK.read_text(encoding="utf-8"))
    assert problems == [], "\n".join(problems)


def test_every_platform_only_entry_states_a_reason():
    for name, reason in lock_parity.PLATFORM_ONLY.items():
        assert name == name.lower(), f"{name} must be lowercased"
        assert len(reason.strip()) > 20, f"{name}: reason too thin to audit"


def test_a_version_mismatch_is_reported():
    problems = lock_parity.compare("numpy==1.26.4\n", "numpy==1.27.0\n")
    assert any("numpy" in p for p in problems)


def test_an_undeclared_one_sided_package_is_reported():
    problems = lock_parity.compare("onlywin==1.0\n", "")
    assert any("onlywin" in p for p in problems)


def test_a_declared_one_sided_package_is_accepted():
    name = next(iter(lock_parity.PLATFORM_ONLY))
    assert lock_parity.compare(f"{name}==1.0\n", "") == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_lock_parity.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'packaging.lock_parity'`

- [ ] **Step 3: 实现 `packaging/lock_parity.py`**

```python
"""Keep the Windows and Linux build locks from drifting apart.

Two locks are unavoidable: PyInstaller's Windows-only build dependencies
cannot be installed on Linux, and vice versa. But once the files are
separate, upgrading a package on one side and forgetting the other makes
the two platforms differ in ways nobody decided on -- and the symptom
surfaces months later as a bug that reproduces on one platform only.

So every package present in both locks must pin the same version, and every
package present in only one must be listed in PLATFORM_ONLY with a reason.
Enforced by labeling_tool/tests/test_lock_parity.py.
"""

from __future__ import annotations

import re

_REQ = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*==\s*(\S+)\s*$")

# Packages that legitimately exist on one platform only. The key is the
# lowercased package name; the value says why, in enough detail to audit.
PLATFORM_ONLY: dict[str, str] = {
    "pefile": "PyInstaller reads PE headers only when building for Windows.",
    "pywin32-ctypes": "PyInstaller uses it for Windows version resources and "
                      "code signing; there is no Linux equivalent.",
}


def parse_lock(text: str) -> dict[str, str]:
    """{lowercased package name: pinned version} for every `name==version`."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _REQ.match(line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def compare(win_text: str, linux_text: str) -> list[str]:
    """Every parity violation between the two locks; empty means they agree."""
    win, linux = parse_lock(win_text), parse_lock(linux_text)
    problems: list[str] = []
    for name in sorted(set(win) & set(linux)):
        if win[name] != linux[name]:
            problems.append(
                f"{name}: windows pins {win[name]}, linux pins {linux[name]} "
                f"-- sync them, or the platforms differ")
    for name in sorted(set(win) ^ set(linux)):
        if name in PLATFORM_ONLY:
            continue
        side = "windows" if name in win else "linux"
        problems.append(
            f"{name}: only in the {side} lock and not declared in "
            f"lock_parity.PLATFORM_ONLY -- add it there with a reason, or "
            f"pin it on both sides")
    return problems
```

- [ ] **Step 4: 生成 `packaging/build-lock-linux.txt`**

在 Ubuntu 22.04（或其容器）上，用与 Windows 侧完全相同的流程生成，**必须使用全新 venv**，不得用系统 Python：

```bash
python3.12 -m venv /tmp/lt-linux-lock && . /tmp/lt-linux-lock/bin/activate
pip install --upgrade pip
pip install -c packaging/build-constraints.txt \
    --extra-index-url https://download.pytorch.org/whl/cu124 \
    -r requirements.txt -r requirements-dev.txt pyinstaller
pip install --no-build-isolation \
    "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"
pip freeze | grep -v "^sam2" > packaging/build-lock-linux.txt
```

在文件头部加与 `build-lock.txt` 对应的英文注释块，说明：这是 Linux 构建环境的完整锁；升级其中任何一项都是一次运行时变更；须从全新 venv 重新生成；sam2 由固定 commit 从 git 安装故不在列。

随后运行 `test_shared_packages_pin_identical_versions`，对每一处报出的差异做出决定：**能对齐的一律对齐**（通常是重新 pin 到 Windows 侧的版本）；确实只能存在于一侧的，加入 `PLATFORM_ONLY` 并写明理由。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_lock_parity.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packaging/build-lock-linux.txt packaging/lock_parity.py \
        labeling_tool/tests/test_lock_parity.py
git commit -m "build: lock the Linux build environment and guard against drift

Two locks are unavoidable -- PyInstaller's Windows-only build deps cannot
be installed on Linux. But separate files drift, and drift means the two
platforms quietly differ. Shared packages must pin identical versions;
one-sided ones must be declared with a reason."
```

---

### Task 5: checker 资产列表化与平台化命名

Windows 的完整安装包是一个文件，Linux 的是两个，因此 `UpdateInfo` 由单资产改为资产列表。本任务同时覆盖 Review Focus 第 4 条。

**Files:**
- Modify: `labeling_tool/update/checker.py`
- Test: `labeling_tool/tests/test_update_checker.py`、`labeling_tool/tests/test_update_layered.py`

**Interfaces:**
- Consumes: `packaging.layers` 的平台常量概念（此处不 import，独立定义 `WINDOWS`/`LINUX` 判断，避免客户端依赖打包脚本）
- Produces:
  - `@dataclass(frozen=True) class Asset: name: str; url: str; size: int; sha256: str`
  - `UpdateInfo` 字段改为 `version, variant, assets: tuple[Asset, ...], notes, kind`
  - `UpdateInfo.total_size -> int`、`UpdateInfo.asset_name -> str`（列表首项名，仅供显示）
  - `app_asset_name(version, runtime, platform=None) -> str`
  - `full_asset_names(version, platform=None) -> tuple[str, ...]`
  - `current_platform() -> str`

- [ ] **Step 1: 写失败测试**

追加到 `labeling_tool/tests/test_update_checker.py`：

```python
def test_windows_asset_names_are_unchanged():
    # Every client ever shipped looks for exactly these names.
    assert (checker.full_asset_names("1.2.3", checker.WINDOWS)
            == ("LM_LabelingTool-Setup-v1.2.3.exe",))
    assert (checker.app_asset_name("1.2.3", "r3f8a1c92", checker.WINDOWS)
            == "LM_LabelingTool-App-v1.2.3-r3f8a1c92.exe")


def test_linux_asset_names():
    # The runtime deb's FILENAME carries no runtime id: a client taking a full
    # update knows the target version but not the new runtime id, so it could
    # not spell the name otherwise. The id lives in its Version field instead.
    assert (checker.full_asset_names("1.2.3", checker.LINUX)
            == ("lm-labeling-tool-runtime_1.2.3_amd64.deb",
                "lm-labeling-tool_1.2.3-RUNTIME_amd64.deb"))
    assert (checker.app_asset_name("1.2.3", "r3f8a1c92", checker.LINUX)
            == "lm-labeling-tool_1.2.3-r3f8a1c92_amd64.deb")


def test_windows_update_carries_exactly_one_asset():
    # The list is length 1 on Windows, always. This pins the refactor.
    info = checker.find_update("1.0.0", "full", opener=_opener(_release()),
                               platform=checker.WINDOWS)
    assert len(info.assets) == 1
    assert info.assets[0].name == "LM_LabelingTool-Setup-v1.0.1.exe"
    assert info.total_size == info.assets[0].size


def test_linux_full_update_carries_both_debs():
    names = ("lm-labeling-tool-runtime_1.0.1_amd64.deb",
             "lm-labeling-tool_1.0.1-rdeadbeef_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full",
                               opener=_opener(_release(names=names)),
                               platform=checker.LINUX)
    assert info.kind == "full"
    assert [a.name for a in info.assets] == list(names[:2])
    assert info.total_size == sum(a.size for a in info.assets)


def test_linux_app_update_carries_one_deb():
    names = ("lm-labeling-tool-runtime_1.0.1_amd64.deb",
             "lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full", runtime="r3f8a1c92",
                               opener=_opener(_release(names=names)),
                               platform=checker.LINUX)
    assert info.kind == "app"
    assert [a.name for a in info.assets] == ["lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb"]


def test_linux_full_update_is_refused_when_the_runtime_deb_is_missing():
    # spec 7.2.1: a release that lost its runtime deb must not produce a
    # half-installable update. Offering the app deb alone would hand the user
    # a download that dpkg then refuses.
    names = ("lm-labeling-tool_1.0.1-rdeadbeef_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full",
                               opener=_opener(_release(names=names)),
                               platform=checker.LINUX)
    assert info is None


def test_an_asset_without_a_published_checksum_is_never_offered():
    # Already true before this change; it must stay true per asset, not just
    # for the first one.
    names = ("lm-labeling-tool-runtime_1.0.1_amd64.deb",
             "lm-labeling-tool_1.0.1-rdeadbeef_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full",
                               opener=_opener(_release(names=names),
                                              omit_sum=names[0]),
                               platform=checker.LINUX)
    assert info is None
```

（实现者注：本文件已有 `_release()` 与构造 opener 的辅助函数，按其既有风格扩展，使其能为任意资产名生成条目、并支持从 `SHA256SUMS.txt` 中略去指定名字。`full_asset_names` 的 Linux 分支中 app deb 名需要 runtime id，而全量更新时客户端并不知道它 —— 见 Step 3 的处理方式。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_update_checker.py -q`
Expected: FAIL — `AttributeError: module 'labeling_tool.update.checker' has no attribute 'Asset'`

- [ ] **Step 3: 实现**

在 `labeling_tool/update/checker.py` 中：

```python
import sys

WINDOWS = "win32"
LINUX = "linux"
APP_PREFIX = "LM_LabelingTool-App"
FULL_PREFIX = "LM_LabelingTool-Setup"
DEB_APP = "lm-labeling-tool"
DEB_RUNTIME = "lm-labeling-tool-runtime"
DEB_ARCH = "amd64"


def current_platform() -> str:
    return WINDOWS if sys.platform.startswith("win") else LINUX


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    variant: str
    assets: tuple[Asset, ...]
    notes: str
    kind: str          # "app" (runtime unchanged) or "full" (reinstall)

    @property
    def total_size(self) -> int:
        return sum(a.size for a in self.assets)

    @property
    def asset_name(self) -> str:
        """The first asset's name, for display only. Callers that install must
        iterate `assets`: a Linux full update is two packages."""
        return self.assets[0].name if self.assets else ""


def app_asset_name(version: str, runtime: str, platform: str | None = None) -> str:
    """The small package: only our own code, built against `runtime`.

    The runtime id is in the FILENAME on both platforms, so a client can tell
    from the name alone whether a package matches its own runtime, without
    downloading it. On Linux the deb's Version field stays a clean version
    number -- the runtime binding is expressed by Depends instead."""
    if (platform or current_platform()) == WINDOWS:
        return f"{APP_PREFIX}-v{version}-{runtime}.exe"
    return f"{DEB_APP}_{version}-{runtime}_{DEB_ARCH}.deb"


def full_asset_names(version: str, platform: str | None = None) -> tuple[str, ...]:
    """Everything a machine needs when its runtime does not match.

    Windows: one installer carrying both layers. Linux: the runtime deb plus
    the app deb. The app deb's name needs a runtime id the client does not
    know at this point, so it is spelled with the RUNTIME placeholder and
    resolved against the release's actual asset list by _resolve_full()."""
    if (platform or current_platform()) == WINDOWS:
        return (f"{FULL_PREFIX}-v{version}.exe",)
    return (f"{DEB_RUNTIME}_{version}_{DEB_ARCH}.deb",
            f"{DEB_APP}_{version}-RUNTIME_{DEB_ARCH}.deb")
```

全量更新时客户端不知道新的 runtime id，因而拼不出 app deb 的文件名。解析办法是在 release 的资产列表里按前后缀匹配出唯一一个：

```python
_APP_DEB = re.compile(r"^lm-labeling-tool_(?P<ver>[^_]+)-(?P<runtime>r[0-9a-f]+)_amd64\.deb$")


def _resolve_full(names: tuple[str, ...], version: str,
                  available: dict) -> list[str] | None:
    """Replace the RUNTIME placeholder with the id this release actually
    carries. None when the release is missing any part of a full install."""
    out = []
    for name in names:
        if "-RUNTIME_" not in name:
            if name not in available:
                return None
            out.append(name)
            continue
        matches = [n for n in available
                   if (m := _APP_DEB.match(n)) and m.group("ver") == version]
        if len(matches) != 1:
            # Zero: the release lost its app deb. More than one: ambiguous,
            # and guessing would hand the user a package dpkg refuses.
            return None
        out.append(matches[0])
    return out
```

`find_update` 改为构造资产列表，并要求**每一个**资产都有已发布的校验和：

```python
    candidates: list[tuple[str, tuple[str, ...]]] = []
    if runtime:
        candidates.append(("app", (app_asset_name(version, runtime, platform),)))
    candidates.append(("full", full_asset_names(version, platform)))
    for kind, wanted in candidates:
        names = _resolve_full(wanted, version, assets) if kind == "full" \
            else ([wanted[0]] if wanted[0] in assets else None)
        if not names:
            continue
        # Every part must be verifiable: an unverifiable download is not
        # installed, and half a full install is worse than none.
        if any(n not in sums for n in names):
            continue
        return UpdateInfo(
            version=version, variant=variant,
            assets=tuple(Asset(name=n,
                               url=assets[n]["browser_download_url"],
                               size=int(assets[n].get("size", 0)),
                               sha256=sums[n]) for n in names),
            notes=str(release.get("body") or ""), kind=kind)
    return None
```

`find_update` 的签名增加 `platform: str | None = None` 并向下传递。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_update_checker.py labeling_tool/tests/test_update_layered.py -q`
Expected: PASS

- [ ] **Step 5: 修正其余调用方并全量回归**

两处调用方会因字段变更而失效，本步只做**最小改动让既有 Windows 行为与测试恢复通过**，完整的多资产下载在 Task 7 实现：

1. `labeling_tool/update/ui.py` 中 `info.size`、`info.asset_name`、`info.sha256`、`info.asset_url` 的引用，改用 `info.assets[0].*` 与 `info.total_size`。
2. `labeling_tool/tests/test_update_ui.py` 顶部的模块级常量 `INFO`，由关键字构造改为携带一个 `Asset`：

```python
INFO = checker.UpdateInfo(
    version="1.0.1", variant="lite",
    assets=(checker.Asset(name="LabelingTool-lite-Setup-v1.0.1.exe",
                          url="https://x/s.exe",
                          size=170 * 1024 * 1024,
                          sha256="a" * 64),),
    notes="fixes", kind="app")
```

同一文件中其它直接构造 `UpdateInfo` 或读取 `info.size` / `info.asset_url` 的地方一并改用新字段。

Run: `python -m pytest labeling_tool/tests -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/update/checker.py labeling_tool/update/ui.py \
        labeling_tool/tests/test_update_checker.py labeling_tool/tests/test_update_layered.py
git commit -m "feat(update): carry a list of assets, not a single one

A Linux full install is two debs; Windows is one installer. UpdateInfo now
holds a tuple, length 1 on Windows and pinned there by a test.

A full update cannot spell the app deb's name -- it knows the version but
not the new runtime id -- so that name is resolved against the release's
own asset list, and a release missing either deb yields no update at all
rather than a half-installable one."
```

---

### Task 6: installer 的 Linux 分支

Windows 必须 detach 后立刻退出；Linux 可以同步等待并取得退出码，因而能分辨失败原因。本任务覆盖 Review Focus 第 3 条。

**Files:**
- Modify: `labeling_tool/update/installer.py`
- Modify: `labeling_tool/core/i18n/strings_en.py`、`strings_ko.py`、`strings_zh.py`
- Test: `labeling_tool/tests/test_update_installer.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `build_command(installer_path, log_path) -> list[str]`（Windows，不变）
  - `build_deb_command(paths: list[Path]) -> list[str]`
  - `InstallOutcome`：枚举值 `OK`、`CANCELLED`、`MISSING_DEPS`、`FAILED`
  - `classify_dpkg_result(returncode: int, stderr: str) -> InstallOutcome`
  - `install_debs(paths, runner=subprocess.run) -> tuple[InstallOutcome, str]`
  - `PKEXEC_CANCELLED = 126`

- [ ] **Step 1: 写失败测试**

追加到 `labeling_tool/tests/test_update_installer.py`：

```python
def test_deb_command_installs_every_package_in_one_call(tmp_path):
    # dpkg unpacks all of them before configuring any, so the app deb's
    # dependency on the runtime deb is satisfied within a single call.
    runtime = tmp_path / "lm-labeling-tool-runtime_1.0.1_amd64.deb"
    app = tmp_path / "lm-labeling-tool_1.0.1-r1_amd64.deb"
    cmd = installer.build_deb_command([runtime, app])
    assert cmd[:3] == ["pkexec", "dpkg", "-i"]
    assert cmd[3:] == [str(runtime), str(app)]


@pytest.mark.parametrize("code,stderr,expected", [
    (0, "", installer.InstallOutcome.OK),
    (126, "", installer.InstallOutcome.CANCELLED),
    (127, "", installer.InstallOutcome.CANCELLED),
    (1, "dpkg: dependency problems prevent configuration of lm-labeling-tool",
     installer.InstallOutcome.MISSING_DEPS),
    (1, "dpkg: error processing archive (--install)", installer.InstallOutcome.FAILED),
])
def test_dpkg_results_are_classified(code, stderr, expected):
    assert installer.classify_dpkg_result(code, stderr) is expected


def test_missing_pkexec_is_reported_not_raised(tmp_path):
    # SSH sessions, WSL and stripped desktops have no polkit agent. An
    # uncaught FileNotFoundError here would crash the app mid-update.
    deb = tmp_path / "x.deb"
    deb.touch()

    def _runner(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    outcome, detail = installer.install_debs([deb], runner=_runner)
    assert outcome is installer.InstallOutcome.FAILED
    assert "pkexec" in detail


def test_install_debs_returns_stderr_on_failure(tmp_path):
    deb = tmp_path / "x.deb"
    deb.touch()

    class _Result:
        returncode = 1
        stderr = "dpkg: dependency problems prevent configuration of foo"

    outcome, detail = installer.install_debs([deb], runner=lambda *a, **k: _Result())
    assert outcome is installer.InstallOutcome.MISSING_DEPS
    assert "dependency problems" in detail


def test_install_debs_refuses_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        installer.install_debs([tmp_path / "nope.deb"], runner=lambda *a, **k: None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_update_installer.py -q`
Expected: FAIL — `AttributeError: module has no attribute 'build_deb_command'`

- [ ] **Step 3: 实现**

在 `labeling_tool/update/installer.py` 中追加（保留既有 Windows 函数不动）：

```python
import enum

# pkexec's own exit codes for "the user dismissed the dialog" (126) and
# "the authorisation could not even be requested" (127) -- no polkit agent
# in this session. Both mean: go back to the app quietly.
PKEXEC_CANCELLED = 126
PKEXEC_NOT_AUTHORISED = 127


class InstallOutcome(enum.Enum):
    OK = "ok"
    CANCELLED = "cancelled"          # user dismissed the password dialog
    MISSING_DEPS = "missing_deps"    # dpkg -i does not fetch from repositories
    FAILED = "failed"


def build_deb_command(paths) -> list[str]:
    """Install every package in ONE dpkg call.

    dpkg unpacks all the archives before configuring any of them, so the app
    package's Depends on the runtime package is satisfied within the call and
    the order on the command line does not matter.

    dpkg -i rather than `apt install ./x.deb`: the runtime package's version
    is a hash, not a sequence, so apt reads a runtime switch as a downgrade
    and refuses it. dpkg merely warns."""
    return ["pkexec", "dpkg", "-i", *[str(p) for p in paths]]


def classify_dpkg_result(returncode: int, stderr: str) -> InstallOutcome:
    """What actually happened, so the caller can tell a cancel from a fault."""
    if returncode == 0:
        return InstallOutcome.OK
    if returncode in (PKEXEC_CANCELLED, PKEXEC_NOT_AUTHORISED):
        return InstallOutcome.CANCELLED
    if "dependency problems" in (stderr or ""):
        # dpkg -i does not resolve dependencies. Nothing is broken: the user
        # needs one apt call to pull the missing system libraries.
        return InstallOutcome.MISSING_DEPS
    return InstallOutcome.FAILED


def install_debs(paths, runner=subprocess.run) -> tuple[InstallOutcome, str]:
    """Install synchronously and report what happened.

    Unlike Windows -- which cannot replace a running exe, so the app hands the
    installer over and exits blind -- Linux can wait for dpkg and read its
    exit code, so a failed update is reported instead of silently not
    happening."""
    paths = [Path(p) for p in paths]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    try:
        result = runner(build_deb_command(paths), capture_output=True,
                        text=True, check=False)
    except FileNotFoundError:
        # No pkexec on this system: an SSH session, WSL, or a desktop without
        # a polkit agent. Tell the user how to install by hand.
        return (InstallOutcome.FAILED,
                "pkexec not found: install polkit, or run "
                "`sudo dpkg -i` on the downloaded packages by hand")
    stderr = (getattr(result, "stderr", "") or "").strip()
    return classify_dpkg_result(result.returncode, stderr), stderr
```

在三份 i18n 文件中各加四个键（照搬既有的排版与占位符风格）：

| 键 | 用途 |
|---|---|
| `update_linux_deps_title` | 缺系统库时的对话框标题 |
| `update_linux_deps_msg` | 正文，须含 `sudo apt-get install -f` 原样命令与 dpkg 输出占位符 `{detail}` |
| `update_linux_restart_title` | 安装成功、提示重启的标题 |
| `update_linux_restart_msg` | 正文 |

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_update_installer.py labeling_tool/tests/test_i18n_api.py -q`
Expected: PASS（`test_i18n_api.py` 会校验三种语言的键集合一致）

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/update/installer.py labeling_tool/core/i18n/strings_*.py \
        labeling_tool/tests/test_update_installer.py
git commit -m "feat(update): install debs synchronously and classify the result

Linux is not Windows: nothing stops us replacing files of a running process,
so the app can wait for dpkg and read its exit code instead of handing over
and exiting blind.

Three outcomes need different handling. 126/127 is the user dismissing the
polkit dialog -- go back quietly. 'dependency problems' is dpkg -i not
fetching system libraries -- tell them the one apt command that fixes it.
A missing pkexec is reported, not raised: SSH sessions and WSL have none."
```

---

### Task 7: ui.py 多资产下载与 Linux 安装流程

把下载循环改为遍历资产列表，并按平台分派安装动作。本任务覆盖 Review Focus 第 5 条。

**Files:**
- Modify: `labeling_tool/update/ui.py:139-181`
- Test: `labeling_tool/tests/test_update_ui.py`

**Interfaces:**
- Consumes: Task 5 的 `UpdateInfo.assets` / `total_size`；Task 6 的 `install_debs` / `InstallOutcome`；Task 2 的 `user_cache_home`
- Produces: `prompt_and_install(parent, info, home=None) -> bool`（语义不变：True = 安装已启动或已完成）

- [ ] **Step 1: 写失败测试**

追加到 `labeling_tool/tests/test_update_ui.py`（沿用本文件既有的 `_app` / `_drain_qt_events` 夹具）：

```python
def _asset(name, size=100 * 1024 * 1024, sha="a" * 64):
    return checker.Asset(name=name, url=f"https://x/{name}", size=size, sha256=sha)


def _linux_full_info():
    return checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(_asset("lm-labeling-tool-runtime_1.0.1_amd64.deb", 700 * 1024 * 1024,
                       "b" * 64),
                _asset("lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb", 20 * 1024 * 1024,
                       "c" * 64)),
        notes="fixes", kind="full")


def _linux_app_info():
    return checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(_asset("lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb", 20 * 1024 * 1024),),
        notes="fixes", kind="app")


@pytest.fixture
def linux(monkeypatch):
    """Take the Linux branch, and never actually call pkexec."""
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)


def test_every_asset_is_downloaded_and_verified(linux, monkeypatch, tmp_path):
    # A Linux full update is two debs; downloading only the first would hand
    # dpkg half an install.
    got = []

    def _download(url, dest, sha, progress=None):
        got.append((dest.name, sha))
        dest.write_bytes(b"deb")

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.OK, ""))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    info = _linux_full_info()
    assert ui.prompt_and_install(None, info, home=tmp_path) is True
    assert [name for name, _ in got] == [a.name for a in info.assets]
    assert [sha for _, sha in got] == [a.sha256 for a in info.assets]


def test_both_debs_are_passed_to_dpkg_in_one_call(linux, monkeypatch, tmp_path):
    # dpkg must see both packages at once, or the app deb's Depends on the
    # runtime deb cannot be satisfied.
    calls = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"deb"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (calls.append(list(paths))
                                             or (ui.installer.InstallOutcome.OK, "")))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    ui.prompt_and_install(None, _linux_full_info(), home=tmp_path)
    assert len(calls) == 1 and len(calls[0]) == 2


def test_progress_spans_the_total_of_all_assets(linux, monkeypatch, tmp_path):
    # Two debs must not each drive the bar from 0 to 100.
    totals = []

    def _download(url, dest, sha, progress=None):
        dest.write_bytes(b"deb")
        if progress is not None:
            progress(1024, 0)

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.OK, ""))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ui.QProgressDialog, "setLabelText",
                        lambda self, text: totals.append(text))

    info = _linux_full_info()
    ui.prompt_and_install(None, info, home=tmp_path)
    whole_mb = str(info.total_size // (1024 * 1024))
    assert all(whole_mb in t for t in totals), \
        f"the bar must be scaled to {whole_mb} MB, saw {totals}"


def test_cancelled_install_is_silent(linux, monkeypatch, tmp_path):
    # Dismissing the polkit dialog is not an error.
    boxes = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"deb"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.CANCELLED, ""))
    monkeypatch.setattr(ui.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: boxes.append(a)))
    monkeypatch.setattr(ui.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: boxes.append(a)))

    assert ui.prompt_and_install(None, _linux_app_info(), home=tmp_path) is False
    assert boxes == []


def test_missing_deps_names_the_apt_command(linux, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"deb"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.MISSING_DEPS,
                                             "dpkg: dependency problems ... libxcb-xinerama0"))
    monkeypatch.setattr(ui.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: shown.append(a)))

    assert ui.prompt_and_install(None, _linux_app_info(), home=tmp_path) is False
    assert shown, "the user must be told which apt command fixes this"
    assert any("apt-get install -f" in str(arg) for arg in shown[0])


def test_a_failed_download_installs_nothing(linux, monkeypatch, tmp_path):
    # ~/.cache full or unwritable: report it, install nothing, keep the app
    # usable. Installing a partially downloaded deb would be worse.
    installs = []
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: installs.append(paths))
    monkeypatch.setattr(ui.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    def _boom(url, dest, sha, progress=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ui.net_download, "download_file", _boom)
    assert ui.prompt_and_install(None, _linux_full_info(), home=tmp_path) is False
    assert installs == []


def test_a_failure_on_the_second_deb_installs_nothing(linux, monkeypatch, tmp_path):
    # The first deb downloaded fine. Installing it alone would leave a
    # runtime layer with no application on top of it.
    installs = []
    seen = []

    def _download(url, dest, sha, progress=None):
        seen.append(dest.name)
        if len(seen) == 2:
            raise OSError(28, "No space left on device")
        dest.write_bytes(b"deb")

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: installs.append(paths))
    monkeypatch.setattr(ui.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    assert ui.prompt_and_install(None, _linux_full_info(), home=tmp_path) is False
    assert installs == []


def test_windows_still_hands_over_to_the_installer(monkeypatch, tmp_path):
    # The Windows path must be untouched by the list refactor.
    launched = []
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"exe"))
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda dest, log: launched.append(dest))

    assert ui.prompt_and_install(None, INFO, home=tmp_path) is True
    assert len(launched) == 1
    assert launched[0].name == INFO.assets[0].name
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_update_ui.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

把 `prompt_and_install` 的下载段改为遍历资产、按总字节数推进进度，并按平台分派安装：

```python
    # A fresh directory per download avoids the TOCTOU on a fixed,
    # user-writable path and stops packages (up to ~1.5 GB each)
    # accumulating forever under a single well-known name.
    cache_root = app_paths.user_cache_home()
    cache_root.mkdir(parents=True, exist_ok=True)
    target_dir = Path(tempfile.mkdtemp(prefix="update-", dir=cache_root))
    bar = QProgressDialog(tr("update_progress_label"), tr("update_cancel"), 0, 100, parent)
    bar.setWindowTitle(tr("update_title"))
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)

    done_before = 0
    paths = []
    try:
        for asset in info.assets:
            dest = target_dir / asset.name

            def on_progress(done, total, _base=done_before):
                # One bar across every asset: two 700 MB debs must not each
                # drive it from 0 to 100.
                overall = _base + done
                bar.setValue(min(100, overall * 100 // max(1, info.total_size)))
                bar.setLabelText(tr("update_progress_template",
                                    done=overall // (1024 * 1024),
                                    total=info.total_size // (1024 * 1024)))
                QApplication.processEvents()
                return not bar.wasCanceled()

            net_download.download_file(asset.url, dest, asset.sha256,
                                       progress=on_progress)
            paths.append(dest)
            done_before += asset.size
        return _hand_over(parent, info, paths, target_dir)
```

新增分派函数：

```python
def _hand_over(parent, info, paths, target_dir) -> bool:
    """Install what was downloaded. True = the update is under way."""
    if checker.current_platform() == checker.WINDOWS:
        # Windows cannot replace a running exe: hand over and exit.
        installer.launch_installer(paths[0], target_dir / "update.log")
        return True
    outcome, detail = installer.install_debs(paths)
    if outcome is installer.InstallOutcome.OK:
        QMessageBox.information(parent, tr("update_linux_restart_title"),
                                tr("update_linux_restart_msg"))
        return True
    if outcome is installer.InstallOutcome.CANCELLED:
        # The user dismissed the polkit dialog. Not an error.
        return False
    if outcome is installer.InstallOutcome.MISSING_DEPS:
        QMessageBox.warning(parent, tr("update_linux_deps_title"),
                            tr("update_linux_deps_msg", detail=detail))
        return False
    QMessageBox.critical(parent, tr("update_failed_title"),
                         tr("update_failed_msg", type="dpkg", exc=detail,
                            url=f"https://github.com/{checker.GITHUB_REPO}/releases/latest"))
    return False
```

`ui.py` 顶部需新增 `from labeling_tool.core import app_paths`（下载目录改用 `user_cache_home()`）。

`QApplication.quit()` 的调用点（`ui.py:239` 附近）需区分平台：Windows 仍在移交后立即退出；Linux 在 `_hand_over` 返回 True 后由使用者手动重启，因此**不**自动退出（提示文案已说明重启生效）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_update_ui.py -q`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `python -m pytest labeling_tool/tests -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/update/ui.py labeling_tool/tests/test_update_ui.py
git commit -m "feat(update): download every asset and install per platform

One progress bar across the whole set, not one per deb. A failed download
installs nothing: a partially fetched package is worse than no update.

Windows keeps handing over and exiting. Linux waits for dpkg, stays silent
when the user dismisses the polkit dialog, and names the apt command when
dpkg -i stops on missing system libraries."
```

---

### Task 8: packaging/deb.py — 组装两个 deb

`installer.iss` 在 Linux 侧的对应物。逻辑放在 Python 里以便单测，与 `layers.py`、`reuse_full.py` 同一模式。

**Files:**
- Create: `packaging/deb.py`
- Create: `packaging/linux/lm-labeling-tool.desktop.in`
- Test: `labeling_tool/tests/test_deb.py`

**Interfaces:**
- Consumes: `packaging.layers` 的 `compute_runtime_id`、`stage_app_layer`、`LINUX`
- Produces:
  - `RUNTIME_DEPENDS: tuple[str, ...]`
  - `runtime_control(runtime_id: str, installed_kb: int) -> str`
  - `app_control(version: str, runtime_id: str, installed_kb: int) -> str`
  - `app_deb_filename(version, runtime_id) -> str`、`runtime_deb_filename(version) -> str`
  - `desktop_entry(version: str) -> str`
  - `build(dist_dir: Path, out_dir: Path, version: str) -> dict[str, Path]`（键为 `"runtime"`、`"app"`）
  - CLI：`python packaging/deb.py build <dist> <out> <version>`

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_deb.py`：

```python
"""The deb control files: where the layer split becomes dpkg's problem."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from packaging import deb  # noqa: E402


def _fields(control: str) -> dict:
    out = {}
    for line in control.splitlines():
        if line and not line.startswith(" ") and ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_runtime_package_is_versioned_by_the_runtime_id():
    f = _fields(deb.runtime_control("r3f8a1c92", installed_kb=1_400_000))
    assert f["Package"] == "lm-labeling-tool-runtime"
    # 0~ sorts before every real version, so this can never be mistaken for
    # an application version number.
    assert f["Version"] == "0~r3f8a1c92"
    assert f["Architecture"] == "amd64"
    assert f["Installed-Size"] == "1400000"


def test_app_package_pins_the_exact_runtime():
    # This one line replaces the hand-written guard installer.iss needs.
    f = _fields(deb.app_control("1.4.1", "r3f8a1c92", installed_kb=20_000))
    assert f["Package"] == "lm-labeling-tool"
    assert f["Version"] == "1.4.1"
    assert f["Depends"] == "lm-labeling-tool-runtime (= 0~r3f8a1c92)"


def test_runtime_package_declares_the_qt_system_libraries():
    # Without these, the install succeeds and the app dies at startup with
    # "could not load the Qt platform plugin xcb".
    f = _fields(deb.runtime_control("r1", installed_kb=1))
    for lib in ("libgl1", "libglib2.0-0", "libxkbcommon-x11-0"):
        assert lib in f["Depends"], f"{lib} missing from runtime Depends"


def test_runtime_package_does_not_depend_on_an_nvidia_driver():
    # torch's cu124 wheel carries the CUDA runtime; requiring a driver
    # package would make the deb uninstallable on CPU-only machines.
    f = _fields(deb.runtime_control("r1", installed_kb=1))
    assert "nvidia" not in f["Depends"].lower()
    assert "cuda" not in f["Depends"].lower()


def test_filenames_split_the_runtime_id_from_the_version():
    # The app deb's NAME carries the id so a client can match it without
    # downloading. The runtime deb's does not: a client taking a full update
    # knows the version but not the new id.
    assert deb.app_deb_filename("1.4.1", "r3f8a1c92") == \
        "lm-labeling-tool_1.4.1-r3f8a1c92_amd64.deb"
    assert deb.runtime_deb_filename("1.4.1") == \
        "lm-labeling-tool-runtime_1.4.1_amd64.deb"


def test_filenames_match_what_the_client_looks_for():
    # Two modules spell these names; if they disagree, updates silently stop.
    from labeling_tool.update import checker
    assert deb.app_deb_filename("1.4.1", "r3f8a1c92") == \
        checker.app_asset_name("1.4.1", "r3f8a1c92", checker.LINUX)
    assert deb.runtime_deb_filename("1.4.1") == \
        checker.full_asset_names("1.4.1", checker.LINUX)[0]


def test_desktop_entry_points_at_the_installed_executable():
    entry = deb.desktop_entry("1.4.1")
    assert "Exec=/opt/lm-labeling-tool/LM_LabelingTool" in entry
    assert "Icon=lm-labeling-tool" in entry
    assert entry.startswith("[Desktop Entry]")


def test_control_ends_with_a_newline():
    # dpkg-deb rejects a control file whose last field has no trailing LF.
    assert deb.runtime_control("r1", 1).endswith("\n")
    assert deb.app_control("1.0.0", "r1", 1).endswith("\n")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_deb.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'packaging.deb'`

- [ ] **Step 3: 实现 `packaging/deb.py`**

模块 docstring 须说明：为何不用 `dpkg-buildpackage`（打的是二进制包而非源码包）、为何 runtime 包版本是 runtime id（见 spec 4.1）、为何文件名与 `Version` 刻意不一致（见 spec 7.2）。

```python
INSTALL_PREFIX = "/opt/lm-labeling-tool"
MAINTAINER = "CYHooo <cyh960502@gmail.com>"

# Qt's xcb platform plugin links against the host's X libraries; PyInstaller
# does not collect them. Without these the package installs cleanly and the
# app dies at startup with "could not load the Qt platform plugin xcb".
#
# Installation goes through `dpkg -i`, which does NOT fetch from
# repositories, so this list must stay within what a desktop install of the
# supported Ubuntu releases already has. CI proves it: the smoke test must
# install without `apt-get install -f`. If something is genuinely needed and
# not present by default, collect it into the runtime layer instead of
# declaring it here.
RUNTIME_DEPENDS = (
    "libc6 (>= 2.35)",
    "libgl1",
    "libglib2.0-0",
    "libxkbcommon-x11-0",
    "libxcb-xinerama0",
    "libxcb-icccm4",
    "libxcb-image0",
    "libxcb-keysyms1",
    "libxcb-randr0",
    "libxcb-render-util0",
    "libxcb-shape0",
    "libdbus-1-3",
)
```

`runtime_control` 与 `app_control` 生成标准 Debian control（字段顺序 `Package`、`Version`、`Architecture`、`Maintainer`、`Installed-Size`、`Depends`、`Section`、`Priority`、`Description`），末尾保留换行。`app_control` 的 `Depends` 恒为 `lm-labeling-tool-runtime (= 0~{runtime_id})`。

`build()` 的步骤：用 `layers.compute_runtime_id(dist_dir, layers.LINUX)` 求 id；用 `layers.stage_app_layer` 与其反向选择分别铺出两棵目录树到 `<staging>/opt/lm-labeling-tool/`；app 包额外写入 `.desktop`、`/usr/share/icons/hicolor/256x256/apps/lm-labeling-tool.png`、`/usr/bin/lm-labeling-tool` 软链与 `DEBIAN/postinst`；最后对每棵树调 `dpkg-deb --build --root-owner-group`。`postinst` 内容：

```sh
#!/bin/sh
set -e
# Make the new entry and icon visible without a re-login. Both tools are
# absent on minimal systems, and their absence must not fail the install.
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
```

压缩由环境变量控制，与 Windows 的 `/DMyFast=1` 对应：`build()` 读 `LT_FAST`，为真时传 `-Zgzip -z1`，否则 `-Zxz`（并由调用方设置 `XZ_OPT=-T4`）。

`.desktop` 模板置于 `packaging/linux/lm-labeling-tool.desktop.in`，`desktop_entry()` 读入并替换版本占位符。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_deb.py -q`
Expected: PASS

- [ ] **Step 5: 本机真实构建一次**

在已装 `dpkg-deb` 的机器上，对一棵最小的假 dist 目录跑一次 `build()`，确认 `dpkg-deb` 不报错，并用 `dpkg-deb -I` 检查两个包的控制信息：

```bash
python packaging/deb.py build /tmp/fake-dist /tmp/out 1.4.1
dpkg-deb -I /tmp/out/lm-labeling-tool_1.4.1-*.deb
dpkg-deb -c /tmp/out/lm-labeling-tool_1.4.1-*.deb | head
```
Expected: `Depends: lm-labeling-tool-runtime (= 0~r...)`，且文件路径以 `./opt/lm-labeling-tool/` 开头。

- [ ] **Step 6: Commit**

```bash
git add packaging/deb.py packaging/linux/ labeling_tool/tests/test_deb.py
git commit -m "build(deb): assemble the runtime and app packages

installer.iss's counterpart on Linux, in Python so the control fields are
unit-tested. The app package's Depends on an exact runtime version replaces
the guard installer.iss has to hand-write and has twice got wrong.

The runtime package's system-library list is bounded by what dpkg -i can
assume: it fetches nothing, so anything not present on a default desktop
install belongs in the runtime layer instead."
```

---

### Task 9: 运行时未变时复用上一个 release 的 runtime deb

spec 7.2.1：每个 release 都必须挂一份 runtime deb，即便当次无人下载它。运行时未变时不重新压缩 1.4 GB，而是取上一个 release 的产物、核对校验和、以本次版本名重新发布。

**Files:**
- Create: `packaging/reuse_runtime.py`
- Test: `labeling_tool/tests/test_reuse_runtime.py`

**Interfaces:**
- Consumes: `labeling_tool.update.checker` 的 Linux 资产名函数
- Produces:
  - `plan(release_json: dict, runtime_id: str) -> tuple[str, str] | None`（`(上一个 tag, 上一个 runtime deb 文件名)`，None 表示必须重新构建）
  - `verify(sums_text: str, path: Path) -> bool`
  - CLI：`plan <release.json> <runtime-id>`、`verify <SHA256SUMS.txt> <file>`

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_reuse_runtime.py`，比照既有的 `test_reuse_full.py` 组织：

```python
def test_reuses_when_the_previous_release_carries_our_runtime_id():
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-r3f8a1c92_amd64.deb"},
        {"name": "lm-labeling-tool-runtime_1.4.0_amd64.deb"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") == \
        ("v1.4.0", "lm-labeling-tool-runtime_1.4.0_amd64.deb")


def test_rebuilds_when_the_runtime_id_moved():
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-rOLDOLD1_amd64.deb"},
        {"name": "lm-labeling-tool-runtime_1.4.0_amd64.deb"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") is None


def test_rebuilds_when_the_previous_release_has_no_runtime_deb():
    # Nothing to copy. Also the exact hole spec 7.2.1 exists to close.
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-r3f8a1c92_amd64.deb"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") is None


def test_rebuilds_when_the_previous_release_is_windows_only():
    # The first release after this feature ships has no Linux assets at all.
    release = {"tagName": "v1.4.1", "assets": [
        {"name": "LM_LabelingTool-Setup-v1.4.1.exe"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") is None


def test_verify_accepts_a_matching_checksum(tmp_path):
    f = tmp_path / "lm-labeling-tool-runtime_1.4.0_amd64.deb"
    f.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    sums = f"{digest}  {f.name}\n"
    assert reuse_runtime.verify(sums, f) is True


def test_verify_rejects_a_mismatch(tmp_path):
    f = tmp_path / "lm-labeling-tool-runtime_1.4.0_amd64.deb"
    f.write_bytes(b"payload")
    assert reuse_runtime.verify("0" * 64 + f"  {f.name}\n", f) is False


def test_verify_rejects_a_file_with_no_published_checksum(tmp_path):
    # Republishing something we cannot verify would launder a corrupted or
    # tampered asset into a new release under our name.
    f = tmp_path / "lm-labeling-tool-runtime_1.4.0_amd64.deb"
    f.write_bytes(b"payload")
    assert reuse_runtime.verify("", f) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_reuse_runtime.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现**

模块 docstring 须写明：为何即便无人下载也必须挂（新装机器与运行时不匹配的旧安装只会查最新 release 里那一个名字，缺了它故障是静默的）；「运行时未变」的判据取自上一个 release 自身的 app deb 文件名中的 runtime id。

判定逻辑：在上一个 release 的资产名中用正则找出 `lm-labeling-tool_<ver>-<runtime>_amd64.deb`，若其 `<runtime>` 等于本次 runtime id，且同一 release 中存在 `lm-labeling-tool-runtime_<ver>_amd64.deb`，则返回 `(tagName, 该 runtime deb 名)`；否则返回 None。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_reuse_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packaging/reuse_runtime.py labeling_tool/tests/test_reuse_runtime.py
git commit -m "build(deb): reuse the previous runtime deb when the runtime holds

Every release must carry a runtime deb even when nobody downloads it that
day: whoever needs a full install looks for exactly one name in the latest
release, and its absence fails silently.

Compressing 1.4 GB of xz to republish identical bytes is waste, so the
previous release's file is downloaded, checked against its published
checksum, and reattached under this version's name."
```

---

### Task 10: CI 工作流、烟测与发布文档

把工作流由「build + release」两 job 扩为「build-windows + build-linux + release」三 job，加入 Linux 构建与安装烟测，并让发布在四个资产齐备前失败。发布文档一并更新。

**Files:**
- Modify: `.github/workflows/build-windows.yml` → 重命名为 `.github/workflows/release.yml`
- Modify: `docs/RELEASING.md`、`README.md`
- Test: `labeling_tool/tests/test_installer_script.py`（扩展为同时校验工作流的静态约束）

**Interfaces:**
- Consumes: 前九个任务的全部产物
- Produces: 同一 tag 下含四个资产的 GitHub Release

- [ ] **Step 1: 写失败测试**

追加到 `labeling_tool/tests/test_installer_script.py`（该文件已在做工作流的静态校验，沿用其读取方式）：

```python
WORKFLOW = REPO / ".github" / "workflows" / "release.yml"


def test_the_linux_job_pins_2204_not_latest():
    # glibc only works forwards: a 24.04 build cannot run on 22.04. A casual
    # bump to ubuntu-latest would silently drop half the supported users.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ubuntu-22.04" in text
    assert "runs-on: ubuntu-latest" not in [l.strip() for l in text.splitlines()
                                            if "build-linux" in text]


def test_release_needs_both_builds():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "needs: [build-windows, build-linux]" in text


def test_release_asserts_all_four_assets_are_present():
    # A build that fails on one platform must not produce a release carrying
    # only the other: clients look for one name and find nothing, silently.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "LM_LabelingTool-Setup-v" in text
    assert "lm-labeling-tool-runtime_" in text


def test_the_linux_smoke_test_forbids_apt_fix_broken():
    # `dpkg -i` must succeed on its own; needing `apt-get install -f` means
    # the runtime package declares a library users will not have either.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "dpkg -i" in text
    assert "install -f" not in text, \
        "the smoke test must not paper over a missing dependency"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest labeling_tool/tests/test_installer_script.py -q`
Expected: FAIL — `release.yml` 尚不存在

- [ ] **Step 3: 重构工作流**

`git mv .github/workflows/build-windows.yml .github/workflows/release.yml`，并：

1. 顶部注释块更新：说明现在发布两个平台、Linux 侧为何钉 `ubuntu-22.04`、验证仍主要在本地完成。
2. 现有 `build` job 更名为 `build-windows`，内容不变。
3. 新增 `build-linux` job（`runs-on: ubuntu-22.04`，`timeout-minutes: 90`），步骤顺序对齐 Windows job：

   - `actions/setup-python@v5`，`python-version: "3.12.10"`，`cache: pip`，`cache-dependency-path` 指向 `packaging/build-lock-linux.txt` 等。
   - 安装系统构建依赖：`sudo apt-get update && sudo apt-get install -y dpkg-dev xvfb`（`dpkg-deb` 随 `dpkg-dev`）。
   - 建全新 venv，按 `build-lock-linux.txt` 安装，再以固定 commit 安装 sam2（与 Windows 同一 commit，`SAM2_BUILD_CUDA=0`，`--no-build-isolation`）。
   - `pyinstaller --noconfirm packaging/labeling_tool.spec`。
   - selftest：`xvfb-run -a dist/LM_LabelingTool/LM_LabelingTool --selftest`（与 Windows 同一自检入口）。
   - 计算 runtime id 并写 `build-info.json`：`python packaging/layers.py runtime-id dist/LM_LabelingTool`。
   - 应用层大小护栏：沿用 Windows 侧 20 MB 的阈值。
   - 复用判定：`gh release view` 取上一个 release，调 `python packaging/reuse_runtime.py plan`；命中则下载并 `verify`，否则本次重新构建 runtime deb。
   - 构建 deb：`XZ_OPT=-T4 python packaging/deb.py build dist/LM_LabelingTool out "$LT_VERSION"`；非 tag 运行设 `LT_FAST=1`。
   - **安装烟测**：`sudo dpkg -i out/lm-labeling-tool-runtime_*.deb out/lm-labeling-tool_*.deb`，**不得**跟 `apt-get install -f`；随后 `xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest`。
   - **依赖护栏测试**：单独 `sudo dpkg -i` 一个人为构造的、runtime id 不匹配的 app deb，断言 dpkg 以非零码拒绝。
   - **24.04 交叉验证**：在 `ubuntu:24.04` 容器中重复「dpkg -i 两个包 + selftest」，同样不得使用 `install -f`。
   - checksum 与 artifact 上传，命名与 Windows job 一致，供 release job 合并。

4. `release` job 改为 `needs: [build-windows, build-linux]`，并在发布前增加一步断言四个资产齐备（按 `LT_VERSION` 拼出四个预期文件名逐一检查存在），缺任何一个即 `exit 1`。
5. **合并两份 `SHA256SUMS.txt`**：两个 build job 各自产出，release job 需将其合并为单一文件后发布 —— 客户端只读一个 `SHA256SUMS.txt`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest labeling_tool/tests/test_installer_script.py -q`
Expected: PASS

- [ ] **Step 5: 更新发布文档**

`docs/RELEASING.md`：在既有的 Windows 流程旁补 Linux 一节 —— 产物有哪两个 deb、手动安装命令（`sudo dpkg -i` 两个包）、缺系统库时的 `sudo apt-get install -f`、如何核对 CI 日志中的 Linux runtime id、以及「运行时变更时两个平台都会是全量」这一事实。

`README.md`：安装说明补 Linux 段落，给出下载与 `dpkg -i` 的完整命令，并说明数据目录在 `~/.local/share/lm-labeling-tool/`。

- [ ] **Step 6: 触发一次 workflow_dispatch 验证**

Run: `gh workflow run release.yml --ref feat/linux-deb-distribution`
Expected: 两个 build job 均绿；Linux job 的日志中能看到 runtime id、应用层大小、`dpkg -i` 一次成功、两处 selftest 通过、不匹配 app deb 被拒。失败则据日志修正后重跑。

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/release.yml docs/RELEASING.md README.md \
        labeling_tool/tests/test_installer_script.py
git commit -m "ci: build and publish both platforms from one tag

Three jobs now: build-windows, build-linux, and a release that needs both.
A build failing on one platform must not publish a release carrying only
the other -- clients look for one asset name and find nothing, silently.

The Linux smoke test installs with dpkg -i and is forbidden from calling
apt-get install -f: needing it would mean the runtime package declares a
library real users will not have either. The same install is repeated in a
24.04 container, because 'built on 22.04, runs on both' is otherwise only
an assumption."
```

---

## 完成条件

全部任务完成后，以下均须为真：

- `python -m pytest labeling_tool/tests -q` 全绿。
- 一次 `workflow_dispatch` 中两个 build job 均绿。
- 一个 tag 产出的 Release 含四个资产：两个 `.exe` 与两个 `.deb`，外加合并后的单一 `SHA256SUMS.txt`。
- 在 22.04 与 24.04 上均可用 `sudo dpkg -i` 两个包装成，无需 `apt-get install -f`，启动后 selftest 通过。
- 装好的 Linux 版能检查到更新：运行时未变时只下载一个 app deb；运行时变更时下载两个 deb。
- Windows 侧行为无任何可观察变化。
