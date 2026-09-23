# Windows 安装程序 + 软件内自动更新 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows 端改为发布 Inno Setup 安装程序，并让应用在启动时发现新版本后一键完成下载、校验、静默安装与重启。

**Architecture:** 新增 `labeling_tool/update/` 子包：`version.py` 读取构建信息，`checker.py` 查询 GitHub Releases 并比较版本，`state.py` 负责节流与"跳过此版本"，`installer.py` 构造并启动静默安装命令，`ui.py` 提供 Qt 检查线程与对话框。通用下载逻辑从 `annotation_tool/segmenter/weights.py` 提取到 `labeling_tool/core/net_download.py`，供权重下载与更新下载共用。`packaging/installer.iss` 由 CI 在 PyInstaller 产物之上生成安装程序，CI 会静默安装、运行自检、再卸载。

**Tech Stack:** Python 3.12、PyQt5、PyInstaller 6.22.3、Inno Setup 6（`iscc`，GitHub runner 预装，缺失时 `choco install innosetup -y`）、GitHub Releases API（未鉴权）。

**Spec:** `docs/superpowers/specs/2026-09-23-installer-and-auto-update-design.md`

## Global Constraints

- 源码运行（`run.sh` / `run.bat` / `python -m …`）行为不变：非打包运行时 `read_build_info()` 返回 `version="0.0.0-dev"`、`variant=None`，更新检查**直接返回无更新**，不发任何网络请求。
- 更新检查的任何失败（网络、解析、限流）都必须静默：只写日志，不弹窗。仅手动触发时才显示错误。
- 下载一律先写 `<dest>.part`，SHA256 校验通过后才改名；失败或取消时不留残File，且不破坏已有文件。
- 安装程序：`PrivilegesRequired=lowest`；lite 与 full 使用不同 `AppId`；卸载保留 `config.json`、`data\`、`checkpoint\`、`classes.json`。
- 资产命名固定：`LabelingTool-<variant>-Setup-v<version>.exe`；校验文件 `SHA256SUMS.txt`，每行 `<sha256>  <filename>`。
- GitHub 仓库常量：`CYHooo/labeling-tool`。
- 生产 `requirements.txt` 不新增依赖（更新器只用标准库 + PyQt5）。
- 代码注释英文；生产界面文字韩文；`annotation_tool/*.md` 与设计文档中文。
- 每个提交信息：主题行、空行、`Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。
- 测试命令：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`（当前基线 283 passed）。

**设计修订（计划阶段发现）**：生产主窗口没有菜单栏，因此规格 §2.3 的「업데이트 확인」菜单项改为**登录界面底部的一行**：左侧显示当前版本，右侧一个「업데이트 확인」按钮。Task 6 会同步修改设计文档。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `labeling_tool/core/net_download.py`（新） | `download_file(url, dest, sha256, progress, chunk_size, timeout)` + `DownloadCancelled` |
| `annotation_tool/segmenter/weights.py` | 改为调用 `net_download`，保留现有公开名字 |
| `labeling_tool/update/version.py`（新） | `BuildInfo`、`read_build_info()` |
| `labeling_tool/update/checker.py`（新） | GitHub Releases 查询、版本比较、资产与校验和解析 |
| `labeling_tool/update/state.py`（新） | `update-state.json`：24 小时节流、跳过版本 |
| `labeling_tool/update/installer.py`（新） | 静默安装命令构造与分离启动 |
| `labeling_tool/update/ui.py`（新） | Qt：检查线程、提示对话框、下载进度 |
| `labeling_tool/ui/login_dialog.py` | 底部版本行 + 「업데이트 확인」按钮 |
| `labeling_tool/app.py` | 启动时异步检查 |
| `packaging/installer.iss`（新） | Inno Setup 脚本 |
| `.github/workflows/build-windows.yml` | build-info.json、iscc、静默安装冒烟、SHA256SUMS、Release 资产 |

---

### Task 1: 通用下载模块 + 构建信息

**Files:**
- Create: `labeling_tool/core/net_download.py`、`labeling_tool/update/__init__.py`、`labeling_tool/update/version.py`
- Modify: `annotation_tool/segmenter/weights.py`
- Test: `labeling_tool/tests/test_net_download.py`（新）、`labeling_tool/tests/test_update_version.py`（新）、`annotation_tool/tests/test_weights.py`（保持通过）

**Interfaces:**
- Produces: `labeling_tool.core.net_download.download_file(url: str, dest: Path, sha256: str, progress=None, chunk_size: int = 1 << 20, timeout: float = 30) -> None`、`class DownloadCancelled(Exception)`；`labeling_tool.update.version.BuildInfo(version: str, variant: str | None, commit: str | None)`、`read_build_info(home: Path | None = None) -> BuildInfo`、`BUILD_INFO_NAME = "build-info.json"`、`DEV_VERSION = "0.0.0-dev"`

- [ ] **Step 1: 写失败测试**

`labeling_tool/tests/test_net_download.py`（结构与 `annotation_tool/tests/test_weights.py` 一致，用本地 HTTP 服务）：

```python
"""Shared checksum-verified downloader used by weights and updates."""
import hashlib
import http.server
import threading
from functools import partial

import pytest

from labeling_tool.core import net_download

PAYLOAD = b"payload" * 5000


@pytest.fixture
def server(tmp_path):
    (tmp_path / "srv").mkdir()
    (tmp_path / "srv" / "f.bin").write_bytes(PAYLOAD)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "srv"))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/f.bin"
    httpd.shutdown()


def test_download_ok(server, tmp_path):
    dest = tmp_path / "out" / "f.bin"
    seen = []
    net_download.download_file(server, dest, hashlib.sha256(PAYLOAD).hexdigest(),
                               progress=lambda d, t: seen.append((d, t)), chunk_size=4096)
    assert dest.read_bytes() == PAYLOAD
    assert not dest.with_name("f.bin.part").exists()
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))


def test_checksum_mismatch(server, tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(ValueError, match="checksum"):
        net_download.download_file(server, dest, "0" * 64)
    assert not dest.exists() and not dest.with_name("f.bin.part").exists()


def test_cancel(server, tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(net_download.DownloadCancelled):
        net_download.download_file(server, dest, hashlib.sha256(PAYLOAD).hexdigest(),
                                   progress=lambda d, t: False, chunk_size=4096)
    assert not dest.exists() and not dest.with_name("f.bin.part").exists()


def test_existing_file_survives_failure(server, tmp_path):
    dest = tmp_path / "f.bin"
    dest.write_bytes(b"old")
    with pytest.raises(ValueError):
        net_download.download_file(server, dest, "0" * 64)
    assert dest.read_bytes() == b"old"


def test_weights_module_reuses_it():
    from annotation_tool.segmenter import weights
    assert weights.download_weights is net_download.download_file
    assert weights.DownloadCancelled is net_download.DownloadCancelled
```

`labeling_tool/tests/test_update_version.py`：

```python
"""build-info.json written by CI next to the exe."""
import json

from labeling_tool.update.version import BUILD_INFO_NAME, DEV_VERSION, read_build_info


def test_reads_ci_build_info(tmp_path):
    (tmp_path / BUILD_INFO_NAME).write_text(
        json.dumps({"version": "1.2.3", "variant": "full", "commit": "abcdef1"}))
    info = read_build_info(tmp_path)
    assert (info.version, info.variant, info.commit) == ("1.2.3", "full", "abcdef1")


def test_missing_file_is_a_dev_build(tmp_path):
    info = read_build_info(tmp_path)
    assert info.version == DEV_VERSION and info.variant is None


def test_broken_file_is_a_dev_build(tmp_path):
    (tmp_path / BUILD_INFO_NAME).write_text("{not json")
    assert read_build_info(tmp_path).version == DEV_VERSION


def test_unknown_variant_is_rejected(tmp_path):
    (tmp_path / BUILD_INFO_NAME).write_text(json.dumps({"version": "1.0.0", "variant": "beta"}))
    assert read_build_info(tmp_path).variant is None


def test_defaults_to_app_home(monkeypatch, tmp_path):
    import labeling_tool.update.version as v
    (tmp_path / BUILD_INFO_NAME).write_text(json.dumps({"version": "9.9.9", "variant": "lite"}))
    monkeypatch.setattr(v, "app_home", lambda: tmp_path)
    assert read_build_info().version == "9.9.9"
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_net_download.py labeling_tool/tests/test_update_version.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError: No module named 'labeling_tool.core.net_download'`

- [ ] **Step 3: 实现**

`labeling_tool/core/net_download.py`：把 `annotation_tool/segmenter/weights.py` 中 `DownloadCancelled` 与 `download_weights` 的**实现原样搬过来**，函数改名为 `download_file`，docstring 改为通用说明（"Download ``url`` to ``dest`` when its SHA256 matches…"）。

`annotation_tool/segmenter/weights.py`：删除实现，改为

```python
from labeling_tool.core.net_download import DownloadCancelled, download_file

# SAM2.1 weights are fetched with the shared checksum-verified downloader.
download_weights = download_file
```

（保留 `SAM2_WEIGHTS_URL` / `SAM2_WEIGHTS_SHA256` / `SAM2_WEIGHTS_SIZE` 与模块 docstring；`DownloadCancelled` 继续以本模块名字导出。）

`labeling_tool/update/__init__.py`：空文件（仅包标记）。

`labeling_tool/update/version.py`：

```python
"""Build identity written next to the exe by CI (build-info.json).

Source runs have no such file: they report DEV_VERSION and no variant, which
is what makes the updater a no-op outside a real release build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from labeling_tool.core.app_paths import app_home

BUILD_INFO_NAME = "build-info.json"
DEV_VERSION = "0.0.0-dev"
VARIANTS = ("lite", "full")


@dataclass(frozen=True)
class BuildInfo:
    version: str
    variant: str | None
    commit: str | None

    @property
    def is_release_build(self) -> bool:
        return self.version != DEV_VERSION and self.variant in VARIANTS


def read_build_info(home: Path | None = None) -> BuildInfo:
    """Read build-info.json; anything missing or malformed reads as a dev build."""
    base = Path(home) if home is not None else app_home()
    try:
        data = json.loads((base / BUILD_INFO_NAME).read_text(encoding="utf-8"))
        version = str(data["version"])
        variant = data.get("variant")
    except (OSError, ValueError, KeyError, TypeError):
        return BuildInfo(DEV_VERSION, None, None)
    return BuildInfo(version,
                     variant if variant in VARIANTS else None,
                     str(data["commit"]) if data.get("commit") else None)
```

- [ ] **Step 4: 运行全部测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: 全部 PASS（283 + 新增）

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/net_download.py labeling_tool/update/ annotation_tool/segmenter/weights.py \
        labeling_tool/tests/test_net_download.py labeling_tool/tests/test_update_version.py
git commit   # subject: "feat(update): shared downloader + build identity"
```

---

### Task 2: 版本检查与节流状态

**Files:**
- Create: `labeling_tool/update/checker.py`、`labeling_tool/update/state.py`
- Test: `labeling_tool/tests/test_update_checker.py`、`labeling_tool/tests/test_update_state.py`

**Interfaces:**
- Consumes: `read_build_info`（Task 1）
- Produces:
  - `checker.GITHUB_REPO = "CYHooo/labeling-tool"`、`checker.asset_name_for(variant: str, version: str) -> str`、`checker.parse_version(text: str) -> tuple[int, ...] | None`、`checker.is_newer(latest: str, current: str) -> bool`、`checker.parse_sha256sums(text: str) -> dict[str, str]`、`@dataclass(frozen=True) checker.UpdateInfo(version, variant, asset_name, asset_url, size, sha256, notes)`、`checker.find_update(current_version: str, variant: str, repo: str = GITHUB_REPO, timeout: float = 10, opener=None) -> UpdateInfo | None`
  - `state.UpdateState(last_check: str | None, skipped_version: str | None)`、`state.load(home=None) -> UpdateState`、`state.save(st, home=None) -> None`、`state.should_check(st, now=None, interval_hours: int = 24) -> bool`、`state.mark_checked(home=None, now=None) -> None`、`state.skip_version(version, home=None) -> None`、`state.STATE_NAME = "update-state.json"`

- [ ] **Step 1: 写失败测试**

`labeling_tool/tests/test_update_checker.py`：

```python
"""GitHub Releases lookup: version compare, asset pick, checksum parse."""
import io
import json

import pytest

from labeling_tool.update import checker


def test_asset_name_and_version_parsing():
    assert checker.asset_name_for("lite", "1.2.3") == "LabelingTool-lite-Setup-v1.2.3.exe"
    assert checker.parse_version("v1.2.3") == (1, 2, 3)
    assert checker.parse_version("1.0.10") == (1, 0, 10)
    assert checker.parse_version("nightly") is None


@pytest.mark.parametrize("latest,current,expected", [
    ("1.0.1", "1.0.0", True),
    ("1.0.10", "1.0.9", True),
    ("v1.0.0", "1.0.0", False),
    ("0.9.9", "1.0.0", False),
    ("1.1", "1.0.5", True),
    ("garbage", "1.0.0", False),
    ("1.0.1", "0.0.0-dev", False),          # dev builds never auto-update
])
def test_is_newer(latest, current, expected):
    assert checker.is_newer(latest, current) is expected


def test_parse_sha256sums():
    text = ("a" * 64 + "  LabelingTool-lite-Setup-v1.0.1.exe\n"
            + "b" * 64 + "  LabelingTool-full-Setup-v1.0.1.exe\n\n")
    sums = checker.parse_sha256sums(text)
    assert sums["LabelingTool-lite-Setup-v1.0.1.exe"] == "a" * 64
    assert len(sums) == 2


def _release(tag="v1.0.1", names=("LabelingTool-lite-Setup-v1.0.1.exe",
                                  "LabelingTool-full-Setup-v1.0.1.exe",
                                  "SHA256SUMS.txt")):
    return {"tag_name": tag, "body": "fixes things",
            "assets": [{"name": n, "browser_download_url": f"https://x/{n}", "size": 1234}
                       for n in names]}


def _opener(release, sums_text):
    """Fake urlopen: returns the release JSON, then the SHA256SUMS body."""
    def open_url(url, timeout=None):
        payload = sums_text if url.endswith("SHA256SUMS.txt") else json.dumps(release)
        return io.BytesIO(payload.encode())
    return open_url


def test_find_update_returns_matching_asset():
    sums = "c" * 64 + "  LabelingTool-lite-Setup-v1.0.1.exe\n"
    info = checker.find_update("1.0.0", "lite", opener=_opener(_release(), sums))
    assert info.version == "1.0.1"
    assert info.asset_name == "LabelingTool-lite-Setup-v1.0.1.exe"
    assert info.asset_url == "https://x/LabelingTool-lite-Setup-v1.0.1.exe"
    assert info.sha256 == "c" * 64
    assert info.size == 1234
    assert "fixes things" in info.notes


def test_find_update_none_when_same_version():
    assert checker.find_update("1.0.1", "lite", opener=_opener(_release(), "")) is None


def test_find_update_none_when_variant_asset_missing():
    rel = _release(names=("LabelingTool-full-Setup-v1.0.1.exe", "SHA256SUMS.txt"))
    assert checker.find_update("1.0.0", "lite", opener=_opener(rel, "")) is None


def test_find_update_requires_checksum():
    # an asset without an entry in SHA256SUMS.txt must not be offered
    assert checker.find_update("1.0.0", "lite", opener=_opener(_release(), "")) is None


def test_find_update_propagates_network_errors():
    def boom(url, timeout=None):
        raise OSError("no network")
    with pytest.raises(OSError):
        checker.find_update("1.0.0", "lite", opener=boom)
```

`labeling_tool/tests/test_update_state.py`：

```python
"""Throttling and skipped versions for the update check."""
from datetime import datetime, timedelta, timezone

from labeling_tool.update import state


def test_missing_state_allows_check(tmp_path):
    st = state.load(tmp_path)
    assert st.last_check is None and st.skipped_version is None
    assert state.should_check(st) is True


def test_recent_check_is_throttled(tmp_path):
    now = datetime.now(timezone.utc)
    state.mark_checked(tmp_path, now=now)
    st = state.load(tmp_path)
    assert state.should_check(st, now=now + timedelta(hours=1)) is False
    assert state.should_check(st, now=now + timedelta(hours=25)) is True


def test_skip_version_round_trip(tmp_path):
    state.skip_version("1.0.1", tmp_path)
    assert state.load(tmp_path).skipped_version == "1.0.1"


def test_broken_state_file_is_ignored(tmp_path):
    (tmp_path / state.STATE_NAME).write_text("{broken")
    st = state.load(tmp_path)
    assert st.last_check is None
    assert state.should_check(st) is True


def test_mark_checked_keeps_skipped_version(tmp_path):
    state.skip_version("1.0.1", tmp_path)
    state.mark_checked(tmp_path)
    assert state.load(tmp_path).skipped_version == "1.0.1"
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_checker.py labeling_tool/tests/test_update_state.py -q -p no:cacheprovider`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`labeling_tool/update/checker.py`：

```python
"""Look up the newest release on GitHub and decide whether it is an update.

Pure logic plus one HTTP call; every failure is raised to the caller, which
decides whether to stay silent (startup check) or report (manual check).
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from labeling_tool.update.version import DEV_VERSION

GITHUB_REPO = "CYHooo/labeling-tool"
LATEST_URL = "https://api.github.com/repos/{repo}/releases/latest"
SUMS_ASSET = "SHA256SUMS.txt"
_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+(\S+)$")


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    variant: str
    asset_name: str
    asset_url: str
    size: int
    sha256: str
    notes: str


def asset_name_for(variant: str, version: str) -> str:
    return f"LabelingTool-{variant}-Setup-v{version}.exe"


def parse_version(text: str) -> tuple[int, ...] | None:
    """(1, 2, 3) for "v1.2.3"; None when it is not a plain numeric version."""
    parts = str(text).lstrip("vV").split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def is_newer(latest: str, current: str) -> bool:
    if current == DEV_VERSION:
        return False  # never offer updates to a source/dev build
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def parse_sha256sums(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = _SUM_LINE.match(line.strip())
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def _read(opener, url: str, timeout: float) -> str:
    with opener(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def find_update(current_version: str, variant: str, repo: str = GITHUB_REPO,
                timeout: float = 10, opener=None) -> UpdateInfo | None:
    """Newest release for ``variant`` if it is newer than ``current_version``.

    Returns None when up to date, when the release has no asset for this
    variant, or when the asset has no published checksum (never install an
    unverifiable download). Network and parse errors are raised.
    """
    opener = opener or urllib.request.urlopen
    release = json.loads(_read(opener, LATEST_URL.format(repo=repo), timeout))
    tag = str(release.get("tag_name", ""))
    version = tag.lstrip("vV")
    if not is_newer(version, current_version):
        return None
    assets = {a["name"]: a for a in release.get("assets", [])}
    wanted = asset_name_for(variant, version)
    if wanted not in assets or SUMS_ASSET not in assets:
        return None
    sums = parse_sha256sums(
        _read(opener, assets[SUMS_ASSET]["browser_download_url"], timeout))
    if wanted not in sums:
        return None
    asset = assets[wanted]
    return UpdateInfo(version=version, variant=variant, asset_name=wanted,
                      asset_url=asset["browser_download_url"],
                      size=int(asset.get("size", 0)), sha256=sums[wanted],
                      notes=str(release.get("body") or ""))
```

`labeling_tool/update/state.py`：

```python
"""Remember when we last checked for updates and which version was skipped."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from labeling_tool.core.app_paths import app_home

STATE_NAME = "update-state.json"


@dataclass(frozen=True)
class UpdateState:
    last_check: str | None = None
    skipped_version: str | None = None


def _path(home: Path | None) -> Path:
    return (Path(home) if home is not None else app_home()) / STATE_NAME


def load(home: Path | None = None) -> UpdateState:
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
        return UpdateState(data.get("last_check"), data.get("skipped_version"))
    except (OSError, ValueError, AttributeError):
        return UpdateState()


def save(st: UpdateState, home: Path | None = None) -> None:
    try:
        _path(home).write_text(json.dumps(
            {"last_check": st.last_check, "skipped_version": st.skipped_version},
            indent=2), encoding="utf-8")
    except OSError:
        pass  # a read-only install must not break the app over bookkeeping


def should_check(st: UpdateState, now: datetime | None = None,
                 interval_hours: int = 24) -> bool:
    if not st.last_check:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(st.last_check)
    except ValueError:
        return True
    return now - last >= timedelta(hours=interval_hours)


def mark_checked(home: Path | None = None, now: datetime | None = None) -> None:
    st = load(home)
    save(UpdateState((now or datetime.now(timezone.utc)).isoformat(),
                     st.skipped_version), home)


def skip_version(version: str, home: Path | None = None) -> None:
    st = load(home)
    save(UpdateState(st.last_check, version), home)
```

- [ ] **Step 4: 运行全部测试** → 全部 PASS

- [ ] **Step 5: 提交**（subject: `feat(update): release lookup + check throttling`）

---

### Task 3: 静默安装启动器

**Files:**
- Create: `labeling_tool/update/installer.py`
- Test: `labeling_tool/tests/test_update_installer.py`

**Interfaces:**
- Produces: `installer.SILENT_ARGS: tuple[str, ...]`、`installer.build_command(installer_path: Path, log_path: Path) -> list[str]`、`installer.launch_and_exit_args() -> dict`（Windows 上 `creationflags`）、`installer.launch_installer(installer_path: Path, log_path: Path, popen=subprocess.Popen) -> None`

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_update_installer.py`

```python
"""Silent installer launch: the app hands over and exits."""
import subprocess
import sys
from pathlib import Path

import pytest

from labeling_tool.update import installer


def test_command_is_silent_and_logged(tmp_path):
    exe, log = tmp_path / "Setup.exe", tmp_path / "update.log"
    cmd = installer.build_command(exe, log)
    assert cmd[0] == str(exe)
    assert "/VERYSILENT" in cmd and "/SUPPRESSMSGBOXES" in cmd and "/NORESTART" in cmd
    assert "/RESTARTAPP" in cmd            # Inno relaunches the app after install
    assert f"/LOG={log}" in cmd


def test_launch_is_detached_and_does_not_wait(tmp_path):
    calls = []

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))

    installer.launch_installer(tmp_path / "Setup.exe", tmp_path / "update.log",
                               popen=_FakePopen)
    cmd, kwargs = calls[0]
    assert cmd == installer.build_command(tmp_path / "Setup.exe", tmp_path / "update.log")
    assert kwargs.get("close_fds") is True
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.DETACHED_PROCESS
    else:
        assert "creationflags" not in kwargs   # POSIX has no such flag


def test_missing_installer_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        installer.launch_installer(tmp_path / "nope.exe", tmp_path / "l.log",
                                   popen=lambda *a, **k: None)
```

- [ ] **Step 2: 运行确认失败**（模块不存在）

- [ ] **Step 3: 实现** `labeling_tool/update/installer.py`

```python
"""Hand the downloaded Inno Setup installer control, then quit.

Windows cannot replace a running exe, so the app launches the installer
detached and exits immediately; /RESTARTAPP makes the installer start the new
version when it is done.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SILENT_ARGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RESTARTAPP")


def build_command(installer_path: Path, log_path: Path) -> list[str]:
    return [str(installer_path), *SILENT_ARGS, f"/LOG={log_path}"]


def launch_and_exit_args() -> dict:
    """Popen kwargs that detach the installer from this process."""
    if sys.platform == "win32":
        return {"close_fds": True,
                "creationflags": subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"close_fds": True}


def launch_installer(installer_path: Path, log_path: Path,
                     popen=subprocess.Popen) -> None:
    """Start the installer detached. The caller must exit right after."""
    installer_path = Path(installer_path)
    if not installer_path.is_file():
        raise FileNotFoundError(installer_path)
    popen(build_command(installer_path, log_path), **launch_and_exit_args())
```

- [ ] **Step 4: 全部测试 PASS**
- [ ] **Step 5: 提交**（subject: `feat(update): detached silent installer launch`）

---

### Task 4: Qt 界面接线（对话框 + 登录界面按钮 + 启动检查）

**Files:**
- Create: `labeling_tool/update/ui.py`
- Modify: `labeling_tool/ui/login_dialog.py`（底部版本行 + 버튼）、`labeling_tool/app.py`（启动检查）
- Test: `labeling_tool/tests/test_update_ui.py`、`labeling_tool/tests/test_login_modes.py`（追加）

**Interfaces:**
- Consumes: Task 1–3 全部接口
- Produces: `ui.UpdateCheckThread(current_version, variant, parent=None)`（信号 `found = pyqtSignal(object)`，找不到或失败时发 `None`）、`ui.check_for_updates(parent, *, force: bool = False, home=None) -> None`（非阻塞）、`ui.prompt_and_install(parent, info, home=None) -> bool`（True 表示已启动安装程序，调用方必须退出应用）；`login_dialog.LoginDialog.lbl_version`、`btn_check_update`

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_update_ui.py`

```python
"""Update prompt: three buttons, progress, and handing over to the installer."""
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.update import checker, state, ui

_app = QApplication.instance() or QApplication([])

INFO = checker.UpdateInfo(version="1.0.1", variant="lite",
                          asset_name="LabelingTool-lite-Setup-v1.0.1.exe",
                          asset_url="https://x/s.exe", size=170 * 1024 * 1024,
                          sha256="a" * 64, notes="fixes")


def test_prompt_later_does_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.LATER)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda *a, **k: pytest.fail("downloaded"))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False
    assert state.load(tmp_path).skipped_version is None


def test_prompt_skip_records_version(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.SKIP)
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False
    assert state.load(tmp_path).skipped_version == "1.0.1"


def test_prompt_update_downloads_verifies_and_launches(monkeypatch, tmp_path):
    seen = {}

    def fake_download(url, dest, sha256, progress=None, **kw):
        seen["download"] = (url, sha256)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"setup")
        if progress:
            progress(10, 100)

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda path, log, **kw: seen.setdefault("launched", path))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is True
    assert seen["download"] == (INFO.asset_url, INFO.sha256)
    assert seen["launched"].name == INFO.asset_name


def test_download_failure_is_reported_and_app_keeps_running(monkeypatch, tmp_path):
    shown = []

    def boom(*a, **k):
        raise ValueError("checksum mismatch")

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", boom)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda *a, **k: pytest.fail("launched after failure"))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False
    assert "checksum" in shown[0]


def test_cancelled_download_is_silent(monkeypatch, tmp_path):
    def cancelled(*a, **k):
        raise ui.net_download.DownloadCancelled()

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", cancelled)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail("error shown"))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False


def test_check_skips_dev_builds(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: pytest.fail("network hit from a dev build"))
    ui.check_for_updates(None, home=tmp_path)          # dev build: version 0.0.0-dev


def test_check_is_throttled(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    state.mark_checked(tmp_path)
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: pytest.fail("checked despite throttle"))
    ui.check_for_updates(None, home=tmp_path)


def test_forced_check_ignores_throttle_and_skip(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    calls = []
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: calls.append(a) or None)
    state.mark_checked(tmp_path)
    state.skip_version("1.0.1", tmp_path)
    thread = ui.check_for_updates(None, force=True, home=tmp_path)
    thread.wait(5000)
    assert calls
```

`labeling_tool/tests/test_login_modes.py` 追加：

```python
def test_login_shows_version_and_check_button(monkeypatch):
    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ld, "read_build_info", lambda: BuildInfo("1.2.3", "lite", None))
    dlg = ld.LoginDialog()
    assert "1.2.3" in dlg.lbl_version.text()
    clicked = []
    monkeypatch.setattr(ld, "check_for_updates", lambda parent, force=False: clicked.append(force))
    dlg.btn_check_update.click()
    assert clicked == [True]
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现** `labeling_tool/update/ui.py`

```python
"""Qt front end for the updater: background check, prompt, download, hand-off."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from labeling_tool.core import net_download
from labeling_tool.logging_setup import vlog
from labeling_tool.update import checker, installer, state
from labeling_tool.update.version import read_build_info

UPDATE, LATER, SKIP = "update", "later", "skip"


class UpdateCheckThread(QThread):
    """Look for an update off the UI thread; emits UpdateInfo or None."""
    found = pyqtSignal(object)

    def __init__(self, current_version: str, variant: str, parent=None):
        super().__init__(parent)
        self._version, self._variant = current_version, variant

    def run(self):
        try:
            self.found.emit(checker.find_update(self._version, self._variant))
        except Exception as exc:  # noqa: BLE001 - a failed check must stay silent
            vlog().info("update check failed: %s: %s", type(exc).__name__, exc)
            self.found.emit(None)


def _ask(parent, info) -> str:
    """The three-button prompt; returns UPDATE / LATER / SKIP."""
    size_mb = info.size // (1024 * 1024)
    notes = "\n".join(info.notes.splitlines()[:8])
    box = QMessageBox(parent)
    box.setWindowTitle("업데이트")
    box.setIcon(QMessageBox.Information)
    box.setText(f"새 버전이 있습니다: v{info.version}\n"
                f"다운로드 크기: 약 {size_mb} MB")
    box.setInformativeText(f"설치 후 자동으로 다시 시작됩니다.\n\n{notes}")
    btn_update = box.addButton("지금 업데이트", QMessageBox.AcceptRole)
    box.addButton("나중에", QMessageBox.RejectRole)
    btn_skip = box.addButton("이 버전 건너뛰기", QMessageBox.DestructiveRole)
    box.exec_()
    if box.clickedButton() is btn_update:
        return UPDATE
    return SKIP if box.clickedButton() is btn_skip else LATER


def prompt_and_install(parent, info, home: Path | None = None) -> bool:
    """Ask, then download + verify + hand over. True = installer started."""
    choice = _ask(parent, info)
    if choice == SKIP:
        state.skip_version(info.version, home)
        return False
    if choice != UPDATE:
        return False

    target_dir = Path(tempfile.gettempdir()) / "LabelingTool-update"
    dest = target_dir / info.asset_name
    bar = QProgressDialog("업데이트 다운로드 중…", "취소", 0, 100, parent)
    bar.setWindowTitle("업데이트")
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)

    def on_progress(done: int, total: int) -> bool:
        total = total or info.size
        bar.setValue(min(100, done * 100 // max(1, total)))
        bar.setLabelText(f"업데이트 다운로드 중… {done // (1024 * 1024)} / "
                         f"{total // (1024 * 1024)} MB")
        QApplication.processEvents()
        return not bar.wasCanceled()

    try:
        net_download.download_file(info.asset_url, dest, info.sha256, progress=on_progress)
        installer.launch_installer(dest, target_dir / "update.log")
        return True
    except net_download.DownloadCancelled:
        return False
    except Exception as exc:  # noqa: BLE001 - network / disk / checksum / launch
        vlog().exception("update failed")
        QMessageBox.critical(parent, "업데이트 실패",
                             f"{type(exc).__name__}: {exc}\n\n"
                             f"나중에 다시 시도하거나 직접 내려받으세요:\n"
                             f"https://github.com/{checker.GITHUB_REPO}/releases/latest")
        return False
    finally:
        bar.close()


def check_for_updates(parent, *, force: bool = False, home: Path | None = None):
    """Start a background check. Returns the thread, or None when skipped."""
    info = read_build_info()
    if not info.is_release_build:
        return None
    st = state.load(home)
    if not force and not state.should_check(st):
        return None

    thread = UpdateCheckThread(info.version, info.variant, parent)

    def _on_found(found):
        state.mark_checked(home)
        if found is None:
            if force:
                QMessageBox.information(parent, "업데이트",
                                        "최신 버전을 사용 중입니다.")
            return
        if not force and state.load(home).skipped_version == found.version:
            return
        if prompt_and_install(parent, found, home):
            QApplication.quit()   # the installer restarts the new version

    thread.found.connect(_on_found)
    thread.start()
    return thread
```

`labeling_tool/ui/login_dialog.py`：顶部加

```python
from labeling_tool.update.ui import check_for_updates
from labeling_tool.update.version import read_build_info
```

在 `__init__` 的 `root.addWidget(self.tabs)` 之后加一行版本行：

```python
        # bottom row: build identity + manual update check
        info = read_build_info()
        self.lbl_version = QLabel(f"버전 {info.version}"
                                  + (f" ({info.variant})" if info.variant else ""))
        self.lbl_version.setStyleSheet("color: #9ea3aa;")
        self.btn_check_update = QPushButton("업데이트 확인")
        self.btn_check_update.clicked.connect(
            lambda: check_for_updates(self, force=True))
        bottom = QHBoxLayout()
        bottom.addWidget(self.lbl_version, 1)
        bottom.addWidget(self.btn_check_update)
        root.addLayout(bottom)
```

`labeling_tool/app.py`：在 `app.setStyleSheet(STYLESHEET)` 之后、`while True:` 之前加

```python
    # startup update check (silent when offline / throttled / a dev build)
    from labeling_tool.update.ui import check_for_updates
    check_for_updates(None)
```

- [ ] **Step 4: 全部测试 PASS**，并确认应用仍能启动：
  `QT_QPA_PLATFORM=offscreen timeout 8 .venv/bin/python -m labeling_tool.app; [ $? = 124 ] && echo "started ok"`
- [ ] **Step 5: 提交**（subject: `feat(update): startup check, prompt and progress UI`）

---

### Task 5: Inno Setup 脚本 + CI

**Files:**
- Create: `packaging/installer.iss`
- Modify: `.github/workflows/build-windows.yml`

**Interfaces:**
- Consumes: `dist/LabelingTool/`（PyInstaller 产物）、`build-info.json`
- Produces: `LabelingTool-<variant>-Setup-v<version>.exe`、`SHA256SUMS.txt`

- [ ] **Step 1: 写 `packaging/installer.iss`**

```iss
; Inno Setup script for LabelingTool. Built by CI:
;   iscc /DMyVariant=lite /DMyVersion=1.0.1 /DMySource=dist\LabelingTool /DMyOutDir=out packaging\installer.iss
; Per-user install by default, so updates need no administrator rights.
#ifndef MyVariant
  #define MyVariant "lite"
#endif
#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif
#ifndef MySource
  #define MySource "dist\LabelingTool"
#endif
#ifndef MyOutDir
  #define MyOutDir "out"
#endif

[Setup]
; distinct AppId per variant: lite and full can coexist
#if MyVariant == "full"
AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}
AppName=LabelingTool (Few-shot)
DefaultDirName={autopf}\LabelingTool-full
DefaultGroupName=LabelingTool (Few-shot)
#else
AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F01}
AppName=LabelingTool
DefaultDirName={autopf}\LabelingTool
DefaultGroupName=LabelingTool
#endif
AppVersion={#MyVersion}
AppPublisher=CYHooo
VersionInfoVersion={#MyVersion}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
DisableProgramGroupPage=yes
OutputDir={#MyOutDir}
OutputBaseFilename=LabelingTool-{#MyVariant}-Setup-v{#MyVersion}
UninstallDisplayIcon={app}\LabelingTool.exe
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; Flags: unchecked

[Files]
; the whole PyInstaller onedir output; user data (config.json, data\,
; checkpoint\, classes.json) is created at runtime and never listed here,
; so uninstalling keeps it
Source: "{#MySource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LabelingTool"; Filename: "{app}\LabelingTool.exe"
Name: "{autodesktop}\LabelingTool"; Filename: "{app}\LabelingTool.exe"; Tasks: desktopicon

[Run]
; interactive install: optional launch. Silent update (/RESTARTAPP): always.
Filename: "{app}\LabelingTool.exe"; Description: "LabelingTool 실행"; \
  Flags: nowait postinstall skipifsilent
Filename: "{app}\LabelingTool.exe"; Flags: nowait runasoriginaluser; \
  Check: WantsRestart

[Code]
function WantsRestart(): Boolean;
begin
  // set by the in-app updater: relaunch after a silent install
  Result := WizardSilent and (Pos('/RESTARTAPP', GetCmdTail) > 0);
end;
```

- [ ] **Step 2: 修改 workflow**

在 build job 的 `Package` 步骤之前插入（`Launch smoke test` 之后）：

```yaml
      - name: Write build info
        run: |
          $ver = $env:LT_VERSION -replace '^v', ''
          $info = @{ version = $ver; variant = $env:LT_VARIANT; commit = $env:GITHUB_SHA.Substring(0,7) }
          $info | ConvertTo-Json -Compress | Set-Content -Path dist\LabelingTool\build-info.json -Encoding utf8
          Get-Content dist\LabelingTool\build-info.json

      - name: Build installer
        run: |
          $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
          if (-not (Test-Path $iscc)) { choco install innosetup -y --no-progress; }
          $ver = $env:LT_VERSION -replace '^v', ''
          New-Item -ItemType Directory -Force out | Out-Null
          & $iscc /DMyVariant=$env:LT_VARIANT /DMyVersion=$ver /DMySource=dist\LabelingTool /DMyOutDir=out packaging\installer.iss
          $setup = Get-ChildItem out\*.exe | Select-Object -First 1
          "LT_SETUP=$($setup.FullName)" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
          # GitHub release assets must stay below 2 GiB
          if ($setup.Length -ge 1.9GB) { throw "installer too large for a release asset: $($setup.Length) bytes" }

      - name: Installer smoke test (install, selftest, uninstall)
        run: |
          $target = "$env:RUNNER_TEMP\lt-install"
          $p = Start-Process -FilePath $env:LT_SETUP -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/DIR=$target","/LOG=$env:RUNNER_TEMP\install.log" -Wait -PassThru
          if ($p.ExitCode -ne 0) { Get-Content "$env:RUNNER_TEMP\install.log" -Tail 40; throw "install failed ($($p.ExitCode))" }
          if (-not (Test-Path "$target\build-info.json")) { throw "build-info.json missing from the install" }
          $s = Start-Process -FilePath "$target\LabelingTool.exe" -ArgumentList "--selftest=$env:LT_VARIANT" -Wait -PassThru
          if (Test-Path "$target\selftest.log") { Get-Content "$target\selftest.log" }
          if ($s.ExitCode -ne 0) { throw "installed selftest failed ($($s.ExitCode))" }
          $u = Get-ChildItem "$target\unins*.exe" | Select-Object -First 1
          Start-Process -FilePath $u.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES" -Wait
```

`Package` 步骤：保留 zip/7z（仅作 artifact 便于排查），并生成校验和：

```yaml
      - name: Package
        run: |
          Remove-Item -Recurse -Force build
          pip cache purge
          $name = "LabelingTool-$env:LT_VARIANT-$env:LT_VERSION"
          if ($env:LT_VARIANT -eq 'lite') { 7z a -tzip "out\$name.zip" .\dist\LabelingTool }
          else { 7z a -v1900m "out\$name.7z" .\dist\LabelingTool }
          $setup = Split-Path $env:LT_SETUP -Leaf
          $hash = (Get-FileHash $env:LT_SETUP -Algorithm SHA256).Hash.ToLower()
          "$hash  $setup" | Set-Content -Path "out\SHA256SUMS-$env:LT_VARIANT.txt" -Encoding ascii
          Get-ChildItem out | Format-Table Name, Length
```

`release` job：合并两个变体的校验和文件，只发布安装程序与 `SHA256SUMS.txt`：

```yaml
      - name: Assemble release assets
        run: |
          Get-Content out\SHA256SUMS-*.txt | Set-Content out\SHA256SUMS.txt -Encoding ascii
          Get-ChildItem out\*.zip, out\*.7z* -ErrorAction SilentlyContinue | Remove-Item
          Remove-Item out\SHA256SUMS-*.txt
          Get-ChildItem out | Format-Table Name, Length
```
（放在 `download-artifact` 之后、`action-gh-release` 之前；release 步骤的 `files: out/*` 保持不变。）

- [ ] **Step 3: 本地校验 YAML 与 iss 语法**

Run:
```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/build-windows.yml')); print('yaml ok')"
grep -c "OutputBaseFilename=LabelingTool-{#MyVariant}-Setup-v{#MyVersion}" packaging/installer.iss
```
Expected: `yaml ok`、`1`（Inno 脚本只能在 Windows 上编译，CI 是第一次真正验证）

- [ ] **Step 4: 提交**（subject: `build: Inno Setup installer + CI install smoke test`）

---

### Task 6: 文档与收尾

**Files:**
- Modify: `README.md`、`docs/README.md`、`docs/superpowers/specs/2026-09-23-installer-and-auto-update-design.md`

- [ ] **Step 1: README 的 exe 一节改写**（韩文）：下载 `LabelingTool-lite-Setup-v<버전>.exe` → 双击安装（SmartScreen「추가 정보 → 실행」）→ 开始菜单启动；更新为软件内自动提示，也可在登录界面点「업데이트 확인」；卸载保留数据；full 版说明其更新包约 1.5 GB。删除"解压到可写目录"等仅适用于压缩包的段落。
- [ ] **Step 2: `docs/README.md`** 索引追加 `2026-09-23-installer-and-auto-update`（状态：유효）。
- [ ] **Step 3: 设计文档** §2.3 的菜单项改为"登录界面底部的版本行 + 업데이트 확인 按钮"，与实现一致。
- [ ] **Step 4:** 全部测试 PASS；`git status` 干净；提交（subject: `docs: installer download / in-app update`）
- [ ] **Step 5:** 由控制者 push 分支并开 PR（CI 会构建安装程序并做安装冒烟测试）；合并后由用户打 tag `v1.1.0` 发布第一版安装程序，并在 Windows 上验证「v1.0.0 → v1.1.0」的真实更新路径。
