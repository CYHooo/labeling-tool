# 单安装包发布与 zip 增量更新 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每个平台只发布一个安装包（Windows Setup exe、Linux 单个 deb），代码更新改用程序自行应用的 zip 增量包，配合韩语 Release 页面、定时检查与后台预下载，并把版本号重排为 0.x 后发布 v0.2.0。

**Architecture:** 客户端新增 `labeling_tool/update/patch.py`（zip 清单、校验、带日志的替换与回滚），`checker.py` 改为单资产选择（zip 优先、完整包兜底），`ui.py` 增加后台下载、缓存复用、按平台应用（Windows 进程内替换；Linux 用 `pkexec <exe> --apply-update`）和每 4 小时的定时检查。打包侧新增 `packaging/update_zip.py` 与 `packaging/release_notes.py`，`deb.py` 改为单包，`installer.iss` 删除 app 层模式，CI 改为产出 4 个文件并自动生成韩语 Release 说明。

**Tech Stack:** Python 3.12、PyQt5、PyInstaller 6.22.3、Inno Setup 6、dpkg-deb、GitHub Actions、pytest（`QT_QPA_PLATFORM=offscreen`）。

**Spec:** `docs/superpowers/specs/2026-10-02-single-package-release-design.md`

## Global Constraints

- 仅 x86-64：Windows、Ubuntu 22.04 / 24.04（构建固定在 `ubuntu-22.04`）。
- 发布文件名（客户端与打包共用的契约）：
  - Windows 完整：`LM_LabelingTool-Setup-v<ver>.exe`
  - Linux 完整：`lm-labeling-tool_<ver>_amd64.deb`
  - 增量：`update-v<ver>-<runtime>-windows.zip` / `update-v<ver>-<runtime>-linux.zip`
  - 校验：`SHA256SUMS.txt`
- runtime id 格式 `^r[0-9a-f]{8}$`，计算方式不变（`packaging/layers.py`）。
- 应用层前缀不变：`LM_LabelingTool(.exe)`、`build-info.json`、`_internal/labeling_tool/`、`_internal/annotation_tool/`。
- Release 说明与 tag 注释**只用韩语**（不得含汉字 U+4E00–U+9FFF，必须含韩文）。程序界面仍是三语，新增字符串三语齐全并遵守 `docs/i18n-glossary.md`（update = 업데이트 / 更新 / Update）。
- 定时检查间隔 4 小时；完整更新不自动下载。
- 测试命令：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`（三个目录都要跑）。
- 绝不写 `from packaging import ...`（与 pip 的 packaging 库重名）；打包脚本用 `sys.path.insert` 后按裸名导入。
- 提交信息使用 conventional commits，结尾附 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`。

## Review Focus

1. **替换进行到一半时程序被杀或断电**：下次启动必须自动回滚到完整的旧版本，而不是半新半旧（Task 2 `test_recover_rolls_back_an_interrupted_apply`）。
2. **zip 内含越界路径（`../`、绝对路径）或清单外的文件**：必须拒绝且不写任何文件（Task 2 `test_a_path_escaping_the_install_dir_is_refused`）。
3. **缓存里留着下载了一半或被篡改的 zip**：校验不符时重新下载，绝不应用（Task 6 `test_a_corrupt_cached_zip_is_downloaded_again`）。
4. **Windows 上第二个实例开着时应用更新**：某个文件被锁定 → 回滚并提示关闭所有窗口，旧版本仍能启动（Task 2 `test_a_failing_move_rolls_back_everything`）。
5. **tag 注释写成中文或英文**：CI 在构建开始时就失败，而不是发布出一份非韩语说明（Task 5 `test_check_korean_rejects_han_and_requires_hangul`）。

---

### Task 1: checker 改为单资产选择，新增说明段提取

**Files:**
- Modify: `labeling_tool/update/checker.py`
- Test: `labeling_tool/tests/test_update_checker.py`（改写涉及双包与 `_resolve_full` 的用例）

**Interfaces:**
- Produces:
  - `full_asset_name(version: str, platform: str | None = None) -> str`
  - `update_asset_name(version: str, runtime: str, platform: str | None = None) -> str`
  - `extract_notes(body: str) -> str`
  - `NOTES_START = "<!-- notes:start -->"`、`NOTES_END = "<!-- notes:end -->"`
  - `find_update(...)` 返回的 `UpdateInfo.assets` 恒为 1 个；`kind` 为 `"app"`（zip）或 `"full"`；`notes` 已是提取后的正文。
- 删除：`APP_PREFIX`、`DEB_RUNTIME`、`_APP_DEB`、`app_asset_name`、`full_asset_names`、`_resolve_full`。

- [ ] **Step 1: 写失败测试**（追加到 `labeling_tool/tests/test_update_checker.py`，并删除引用 `app_asset_name` / `full_asset_names` / `_resolve_full` / `DEB_RUNTIME` 的旧用例）

```python
from labeling_tool.update import checker


def test_one_full_asset_per_platform():
    assert checker.full_asset_name("0.2.0", checker.WINDOWS) == "LM_LabelingTool-Setup-v0.2.0.exe"
    assert checker.full_asset_name("0.2.0", checker.LINUX) == "lm-labeling-tool_0.2.0_amd64.deb"


def test_update_zip_name_carries_runtime_and_platform():
    assert checker.update_asset_name("0.2.1", "r88c8d3f0", checker.WINDOWS) == "update-v0.2.1-r88c8d3f0-windows.zip"
    assert checker.update_asset_name("0.2.1", "ra493a449", checker.LINUX) == "update-v0.2.1-ra493a449-linux.zip"


def _release(names, body=""):
    import json
    assets = [{"name": n, "browser_download_url": f"https://x/{n}", "size": 10} for n in names]
    return json.dumps({"tag_name": "v0.2.1", "body": body, "assets": assets})


def _opener(release_json, sums):
    import io

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(url, timeout):
        if url.endswith("SHA256SUMS.txt"):
            return _Resp(sums.encode())
        return _Resp(release_json.encode())
    return opener


SUMS = "\n".join(f"{c * 64}  {n}" for c, n in [
    ("a", "LM_LabelingTool-Setup-v0.2.1.exe"),
    ("b", "update-v0.2.1-r88c8d3f0-windows.zip"),
    ("c", "lm-labeling-tool_0.2.1_amd64.deb"),
    ("d", "update-v0.2.1-ra493a449-linux.zip"),
])
ALL = ["LM_LabelingTool-Setup-v0.2.1.exe", "update-v0.2.1-r88c8d3f0-windows.zip",
       "lm-labeling-tool_0.2.1_amd64.deb", "update-v0.2.1-ra493a449-linux.zip", "SHA256SUMS.txt"]


def test_same_runtime_gets_the_zip():
    info = checker.find_update("0.2.0", "full", opener=_opener(_release(ALL), SUMS),
                               runtime="r88c8d3f0", platform=checker.WINDOWS)
    assert info.kind == "app"
    assert [a.name for a in info.assets] == ["update-v0.2.1-r88c8d3f0-windows.zip"]
    assert info.assets[0].sha256 == "b" * 64


def test_changed_runtime_gets_the_full_package():
    info = checker.find_update("0.2.0", "full", opener=_opener(_release(ALL), SUMS),
                               runtime="rdeadbeef", platform=checker.LINUX)
    assert info.kind == "full"
    assert [a.name for a in info.assets] == ["lm-labeling-tool_0.2.1_amd64.deb"]


def test_an_asset_without_a_checksum_is_never_offered():
    sums = "\n".join(l for l in SUMS.splitlines() if "windows.zip" not in l)
    info = checker.find_update("0.2.0", "full", opener=_opener(_release(ALL), sums),
                               runtime="r88c8d3f0", platform=checker.WINDOWS)
    assert info.kind == "full"


def test_extract_notes_returns_only_the_marked_section():
    body = "| table |\n<!-- notes:start -->\n- 버그 수정\n- 속도 개선\n<!-- notes:end -->\n### 어떤 파일"
    assert checker.extract_notes(body) == "- 버그 수정\n- 속도 개선"


def test_extract_notes_without_markers_falls_back_to_eight_lines():
    body = "\n".join(f"line {i}" for i in range(20))
    assert checker.extract_notes(body) == "\n".join(f"line {i}" for i in range(8))
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_checker.py -q -p no:cacheprovider`
Expected: FAIL，`AttributeError: module ... has no attribute 'full_asset_name'`

- [ ] **Step 3: 实现**（替换 `checker.py` 中常量、资产命名函数、`_resolve_full` 与 `find_update` 的资产选择部分）

```python
FULL_PREFIX = "LM_LabelingTool-Setup"
DEB_PACKAGE = "lm-labeling-tool"
DEB_ARCH = "amd64"
NOTES_START = "<!-- notes:start -->"
NOTES_END = "<!-- notes:end -->"


def full_asset_name(version: str, platform: str | None = None) -> str:
    """The one package a user downloads by hand, and the full update a
    machine takes when its runtime id no longer matches."""
    if (platform or current_platform()) == WINDOWS:
        return f"{FULL_PREFIX}-v{version}.exe"
    return f"{DEB_PACKAGE}_{version}_{DEB_ARCH}.deb"


def update_asset_name(version: str, runtime: str, platform: str | None = None) -> str:
    """The app-layer zip built against `runtime`. The id is in the name so a
    client can tell, without downloading, whether the zip fits its install."""
    tag = "windows" if (platform or current_platform()) == WINDOWS else "linux"
    return f"update-v{version}-{runtime}-{tag}.zip"


def extract_notes(body: str) -> str:
    """The change notes between the markers release_notes.py writes; the
    first eight lines of a body that has none (hand-edited releases)."""
    text = str(body or "")
    start, end = text.find(NOTES_START), text.find(NOTES_END)
    if start != -1 and end > start:
        return text[start + len(NOTES_START):end].strip()
    return "\n".join(text.splitlines()[:8])
```

`find_update` 中从 `candidates` 起替换为：

```python
    candidates: list[tuple[str, str]] = []
    if runtime:
        candidates.append(("app", update_asset_name(version, runtime, platform)))
    candidates.append(("full", full_asset_name(version, platform)))
    for kind, name in candidates:
        if name not in assets or name not in sums:
            continue  # an unverifiable download is never installed
        a = assets[name]
        return UpdateInfo(
            version=version, variant=variant,
            assets=(Asset(name=name, url=a["browser_download_url"],
                          size=int(a.get("size", 0)), sha256=sums[name]),),
            notes=extract_notes(release.get("body") or ""), kind=kind)
    return None
```

同时更新 `find_update` 的 docstring（去掉“half an install”双包描述），删除 `UpdateInfo.asset_name` 的“Linux 两个包”注释。

- [ ] **Step 4: 运行，确认通过**；再全量跑测试，修正其他引用旧名的地方（`packaging/reuse_full.py` 在 Task 4 处理；此处若有其他导入失败一并改为新函数）。

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_checker.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/update/checker.py labeling_tool/tests/test_update_checker.py
git commit -m "feat(update): pick one asset per update, zip before full package"
```

---

### Task 2: patch 模块（清单、校验、替换、回滚、恢复）

**Files:**
- Create: `labeling_tool/update/patch.py`
- Test: `labeling_tool/tests/test_update_patch.py`

**Interfaces:**
- Consumes: `labeling_tool.update.version.read_build_info(home) -> BuildInfo`（`.runtime`）、`checker.WINDOWS/LINUX/current_platform()`。
- Produces:
  - `MANIFEST_NAME = "manifest.json"`；`STAGING, BACKUP, JOURNAL = ".update-staging", ".update-backup", ".update-journal"`
  - `APP_LAYER_PREFIXES(platform) -> tuple[str, ...]`（与 `packaging/layers.app_layer_prefixes` 一致，Task 3 有一致性测试）
  - `class PatchError(Exception)`
  - `@dataclass(frozen=True) class PatchManifest: version: str; runtime: str; platform: str; files: dict[str, str]`
  - `read_manifest(zip_path: Path) -> PatchManifest`
  - `apply_patch(zip_path: Path, install_dir: Path, expected_sha256: str, platform: str | None = None) -> PatchManifest`
  - `recover(install_dir: Path) -> bool`（有未完成日志时回滚，返回 True）
  - `cleanup(install_dir: Path) -> None`（无日志时删除备份与 staging）

- [ ] **Step 1: 写失败测试**

```python
"""The app-layer zip: verify, swap with a journal, roll back, recover."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from labeling_tool.update import patch


def _install(root: Path, runtime="r11111111", version="0.2.0"):
    (root / "_internal" / "labeling_tool").mkdir(parents=True)
    (root / "_internal" / "torch").mkdir(parents=True)
    (root / "LM_LabelingTool.exe").write_bytes(b"old exe")
    (root / "_internal" / "labeling_tool" / "a.pyc").write_bytes(b"old a")
    (root / "_internal" / "labeling_tool" / "gone.pyc").write_bytes(b"old gone")
    (root / "_internal" / "torch" / "lib.dll").write_bytes(b"runtime")
    (root / "build-info.json").write_text(json.dumps(
        {"version": version, "variant": "full", "runtime": runtime, "commit": "x"}))
    return root


def _zip(path: Path, files: dict[str, bytes], runtime="r11111111", platform="win32",
         version="0.2.1", manifest_files=None):
    listing = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
    manifest = {"version": version, "runtime": runtime, "platform": platform,
                "files": manifest_files if manifest_files is not None else listing}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(patch.MANIFEST_NAME, json.dumps(manifest))
        for rel, data in files.items():
            z.writestr(rel, data)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


NEW = {
    "LM_LabelingTool.exe": b"new exe",
    "_internal/labeling_tool/a.pyc": b"new a",
    "_internal/labeling_tool/b.pyc": b"new b",
    "build-info.json": json.dumps({"version": "0.2.1", "variant": "full",
                                   "runtime": "r11111111", "commit": "y"}).encode(),
}


def test_apply_replaces_adds_and_removes_app_layer_files(tmp_path):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    m = patch.apply_patch(z, root, sha, platform="win32")
    assert m.version == "0.2.1"
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"new exe"
    assert (root / "_internal/labeling_tool/b.pyc").read_bytes() == b"new b"
    assert not (root / "_internal/labeling_tool/gone.pyc").exists()
    assert (root / "_internal/torch/lib.dll").read_bytes() == b"runtime"  # runtime untouched
    assert not (root / patch.JOURNAL).exists() and not (root / patch.STAGING).exists()


def test_a_wrong_checksum_changes_nothing(tmp_path):
    root = _install(tmp_path / "app")
    z, _ = _zip(tmp_path / "u.zip", NEW)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, "0" * 64, platform="win32")
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"


@pytest.mark.parametrize("runtime,platform", [("r22222222", "win32"), ("r11111111", "linux")])
def test_a_zip_for_another_runtime_or_platform_is_refused(tmp_path, runtime, platform):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW, runtime=runtime, platform=platform)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"


@pytest.mark.parametrize("bad", ["../evil.pyc", "/abs.pyc", "_internal/torch/lib.dll"])
def test_a_path_escaping_the_install_dir_is_refused(tmp_path, bad):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", {**NEW, bad: b"x"})
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert not (tmp_path / "evil.pyc").exists()
    assert (root / "_internal/torch/lib.dll").read_bytes() == b"runtime"


def test_a_file_that_does_not_match_the_manifest_is_refused(tmp_path):
    root = _install(tmp_path / "app")
    listing = {rel: hashlib.sha256(d).hexdigest() for rel, d in NEW.items()}
    listing["_internal/labeling_tool/a.pyc"] = "f" * 64
    z, sha = _zip(tmp_path / "u.zip", NEW, manifest_files=listing)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"


def test_a_failing_move_rolls_back_everything(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    real = patch._move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 4:   # fail part-way through the swap
            raise PermissionError("locked by another instance")
        real(src, dst)
    monkeypatch.setattr(patch, "_move", flaky)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"
    assert (root / "_internal/labeling_tool/gone.pyc").read_bytes() == b"old gone"
    assert not (root / "_internal/labeling_tool/b.pyc").exists()
    assert not (root / patch.JOURNAL).exists()


def test_recover_rolls_back_an_interrupted_apply(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    real = patch._move
    calls = {"n": 0}

    def crash(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise SystemExit("power cut")   # not caught by apply_patch's rollback
        real(src, dst)
    monkeypatch.setattr(patch, "_move", crash)
    with pytest.raises(SystemExit):
        patch.apply_patch(z, root, sha, platform="win32")
    monkeypatch.setattr(patch, "_move", real)
    assert (root / patch.JOURNAL).exists()
    assert patch.recover(root) is True
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"
    assert not (root / patch.JOURNAL).exists()
    assert patch.recover(root) is False


def test_cleanup_removes_the_backup_only_after_success(tmp_path):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    patch.apply_patch(z, root, sha, platform="win32")
    assert (root / patch.BACKUP).exists()
    patch.cleanup(root)
    assert not (root / patch.BACKUP).exists()
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_patch.py -q -p no:cacheprovider`
Expected: FAIL，`ImportError: cannot import name 'patch'`

- [ ] **Step 3: 实现 `labeling_tool/update/patch.py`**

```python
"""Apply an app-layer update zip to an installed copy, with a journal.

The zip carries the app layer -- our own code, a few MB -- plus
manifest.json (version, runtime id, platform, every file's SHA-256). The
swap moves each replaced file into .update-backup/ before moving the new
one in, journalling every move first, so a failure rolls back exactly and a
crash mid-swap is undone by recover() on the next start.

Windows: a running .exe cannot be overwritten but can be renamed, so moving
it into the backup works while the app runs. Linux: /opt is root-owned, so
the app runs this module as root via `pkexec <exe> --apply-update`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from labeling_tool.update import checker
from labeling_tool.update.version import read_build_info

MANIFEST_NAME = "manifest.json"
STAGING, BACKUP, JOURNAL = ".update-staging", ".update-backup", ".update-journal"


def APP_LAYER_PREFIXES(platform: str | None = None) -> tuple[str, ...]:
    """Must equal packaging/layers.app_layer_prefixes (test_update_zip.py)."""
    exe = "LM_LabelingTool.exe" if (platform or checker.current_platform()) == checker.WINDOWS \
        else "LM_LabelingTool"
    return (exe, "build-info.json", "_internal/labeling_tool/", "_internal/annotation_tool/")


class PatchError(Exception):
    """The zip cannot be applied; nothing on disk was changed (or it was rolled back)."""


@dataclass(frozen=True)
class PatchManifest:
    version: str
    runtime: str
    platform: str
    files: dict[str, str]


def _is_app_layer(rel: str, platform: str) -> bool:
    for prefix in APP_LAYER_PREFIXES(platform):
        if (prefix.endswith("/") and rel.startswith(prefix)) or rel == prefix:
            return True
    return False


def _safe_rel(rel: str, platform: str) -> str:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or rel != p.as_posix():
        raise PatchError(f"unsafe path in update: {rel!r}")
    if not _is_app_layer(rel, platform):
        raise PatchError(f"not an app-layer file: {rel!r}")
    return rel


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)


def read_manifest(zip_path: Path) -> PatchManifest:
    try:
        with zipfile.ZipFile(zip_path) as z:
            data = json.loads(z.read(MANIFEST_NAME).decode("utf-8"))
        return PatchManifest(str(data["version"]), str(data["runtime"]),
                             str(data["platform"]), dict(data["files"]))
    except (KeyError, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise PatchError(f"not an update zip: {exc}") from exc


def _installed_app_files(root: Path, platform: str) -> list[str]:
    out = []
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if not rel.startswith((STAGING, BACKUP)) and _is_app_layer(rel, platform):
                out.append(rel)
    return out


def _rollback(root: Path, journal: list[list[str]]) -> None:
    for op, a, b in reversed(journal):
        src, dst = Path(b), Path(a)   # undo: move it back where it came from
        if src.exists():
            _move(src, dst)
    shutil.rmtree(root / STAGING, ignore_errors=True)
    (root / JOURNAL).unlink(missing_ok=True)


def apply_patch(zip_path: Path, install_dir: Path, expected_sha256: str,
                platform: str | None = None) -> PatchManifest:
    platform = platform or checker.current_platform()
    root = Path(install_dir)
    zip_path = Path(zip_path)
    if _sha256(zip_path) != expected_sha256.lower():
        raise PatchError("update zip does not match its published checksum")
    m = read_manifest(zip_path)
    installed = read_build_info(root)
    if m.platform != platform:
        raise PatchError(f"update is for {m.platform}, this install is {platform}")
    if not installed.runtime or m.runtime != installed.runtime:
        raise PatchError(f"update needs runtime {m.runtime}, installed is {installed.runtime}")
    for rel in m.files:
        _safe_rel(rel, platform)

    staging = root / STAGING
    shutil.rmtree(staging, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist()) - {MANIFEST_NAME}
        if names != set(m.files):
            raise PatchError("zip contents do not match its manifest")
        for rel in m.files:
            _safe_rel(rel, platform)
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(rel))
            if _sha256(target) != m.files[rel]:
                shutil.rmtree(staging, ignore_errors=True)
                raise PatchError(f"{rel} does not match the manifest")

    backup = root / BACKUP
    shutil.rmtree(backup, ignore_errors=True)
    journal: list[list[str]] = []
    journal_path = root / JOURNAL

    def record(op: str, src: Path, dst: Path) -> None:
        journal.append([op, str(src), str(dst)])
        journal_path.write_text(json.dumps(journal), encoding="utf-8")

    try:
        stale = set(_installed_app_files(root, platform)) - set(m.files)
        for rel in sorted(set(m.files) | stale):
            current = root / rel
            if current.exists():
                record("backup", current, backup / rel)
                _move(current, backup / rel)
            if rel in m.files:
                record("install", staging / rel, current)
                _move(staging / rel, current)
    except Exception as exc:  # noqa: BLE001 - any failure must roll back
        _rollback(root, journal)
        raise PatchError(f"could not apply the update: {exc}") from exc
    journal_path.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    return m


def recover(install_dir: Path) -> bool:
    """Undo a swap that never finished. Call first thing at startup."""
    root = Path(install_dir)
    journal_path = root / JOURNAL
    if not journal_path.exists():
        return False
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        journal = []
    _rollback(root, journal)
    return True


def cleanup(install_dir: Path) -> None:
    """Drop the previous version's files once the new one is running."""
    root = Path(install_dir)
    if (root / JOURNAL).exists():
        return
    shutil.rmtree(root / BACKUP, ignore_errors=True)
    shutil.rmtree(root / STAGING, ignore_errors=True)
```

注意 `_rollback` 的语义：日志记录的是 `[op, src, dst]`（文件从 src 移到 dst），回滚时把存在于 dst 的文件移回 src——backup 项把旧文件放回原处，install 项把新文件移回 staging（随后整个 staging 被删除）。必须按**逆序**执行。

- [ ] **Step 4: 运行，确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_patch.py -q -p no:cacheprovider`
Expected: PASS（9 个测试）

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/update/patch.py labeling_tool/tests/test_update_patch.py
git commit -m "feat(update): apply app-layer zips with a journal and rollback"
```

---

### Task 3: 打包侧的 update zip，以及应用层前缀一致性

**Files:**
- Create: `packaging/update_zip.py`
- Test: `labeling_tool/tests/test_update_zip.py`

**Interfaces:**
- Consumes: `packaging/layers.py` 的 `app_layer_prefixes`、`stage_app_layer`；Task 1 的 `checker.update_asset_name`；Task 2 的 `patch.MANIFEST_NAME`、`patch.APP_LAYER_PREFIXES`、`patch.read_manifest`。
- Produces: `build_update_zip(app_layer_dir: Path, out_dir: Path, version: str, runtime: str, platform: str) -> Path`；CLI `python packaging/update_zip.py <app-layer-dir> <out-dir> <version> <runtime> <win32|linux>`（打印 zip 路径）。

- [ ] **Step 1: 写失败测试**

```python
"""packaging/update_zip.py: the app-layer zip the release publishes."""
import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import layers  # noqa: E402
import update_zip  # noqa: E402

from labeling_tool.update import patch  # noqa: E402


@pytest.mark.parametrize("platform", [layers.WINDOWS, layers.LINUX])
def test_client_and_packaging_agree_on_the_app_layer(platform):
    assert patch.APP_LAYER_PREFIXES(platform) == layers.app_layer_prefixes(platform)


def test_zip_carries_every_file_and_a_matching_manifest(tmp_path):
    src = tmp_path / "app-layer"
    (src / "_internal/labeling_tool").mkdir(parents=True)
    (src / "_internal/labeling_tool/a.pyc").write_bytes(b"a")
    (src / "LM_LabelingTool.exe").write_bytes(b"exe")
    (src / "build-info.json").write_text("{}")
    z = update_zip.build_update_zip(src, tmp_path / "out", "0.2.1", "r11111111", layers.WINDOWS)
    assert z.name == "update-v0.2.1-r11111111-windows.zip"
    m = patch.read_manifest(z)
    assert (m.version, m.runtime, m.platform) == ("0.2.1", "r11111111", "win32")
    assert m.files["_internal/labeling_tool/a.pyc"] == hashlib.sha256(b"a").hexdigest()
    with zipfile.ZipFile(z) as f:
        assert set(f.namelist()) == set(m.files) | {patch.MANIFEST_NAME}


def test_a_non_app_layer_file_in_the_source_is_rejected(tmp_path):
    src = tmp_path / "app-layer"
    (src / "_internal/torch").mkdir(parents=True)
    (src / "_internal/torch/x.dll").write_bytes(b"x")
    with pytest.raises(ValueError):
        update_zip.build_update_zip(src, tmp_path / "out", "0.2.1", "r11111111", layers.WINDOWS)
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_zip.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError: No module named 'update_zip'`

- [ ] **Step 3: 实现 `packaging/update_zip.py`**

```python
"""Build the app-layer update zip a release publishes for each platform.

Input is `layers.py stage`'s output (only app-layer files); output is
update-v<ver>-<runtime>-<windows|linux>.zip with manifest.json, the format
labeling_tool/update/patch.py applies. Imported by bare name -- never as
`from packaging import ...`, which is pip's own library.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layers  # noqa: E402
from labeling_tool.update import checker, patch  # noqa: E402


def build_update_zip(app_layer_dir: Path, out_dir: Path, version: str,
                     runtime: str, platform: str) -> Path:
    src = Path(app_layer_dir)
    files: dict[str, str] = {}
    for path in sorted(src.rglob("*")):
        if path.is_file():
            rel = path.relative_to(src).as_posix()
            if not layers.is_app_layer(rel, platform):
                raise ValueError(f"not an app-layer file: {rel}")
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / checker.update_asset_name(version, runtime, platform)
    manifest = {"version": version, "runtime": runtime, "platform": platform, "files": files}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(patch.MANIFEST_NAME, json.dumps(manifest, indent=1))
        for rel in files:
            z.write(src / rel, rel)
    return zip_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 5 and args[4] in (layers.WINDOWS, layers.LINUX):
        print(build_update_zip(Path(args[0]), Path(args[1]), args[2], args[3], args[4]))
        return 0
    print("usage: update_zip.py <app-layer-dir> <out-dir> <version> <runtime> <win32|linux>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行，确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_zip.py -q -p no:cacheprovider`
Expected: PASS（4 个测试）

- [ ] **Step 5: 提交**

```bash
git add packaging/update_zip.py labeling_tool/tests/test_update_zip.py
git commit -m "build: produce the app-layer update zip with its manifest"
```

---

### Task 4: Linux 单 deb、Windows 删除 app 层模式、复用逻辑改看 zip、删除无效代码

**Files:**
- Modify: `packaging/deb.py`（单包；新增 `PREINST`、`POSTRM`；删除 `--app-only`/`--runtime-id`、runtime 包相关）
- Modify: `packaging/installer.iss`（删除 `MyLayer`/`MyRuntime` 与 `[Code]` 中的守卫；新增 `[UninstallDelete]`）
- Modify: `packaging/reuse_full.py`（`plan_reuse` 以 `update_asset_name(..., WINDOWS)` 判断运行时未变）
- Delete: `packaging/reuse_runtime.py`、`labeling_tool/tests/test_reuse_runtime.py`、`packaging/bundle_filters.py`、`labeling_tool/tests/test_bundle_filters.py`；`packaging/labeling_tool.spec` 中 `bundle_filters` 的导入与调用
- Test: `labeling_tool/tests/test_deb.py`、`labeling_tool/tests/test_installer_script.py`（iss 部分）、`labeling_tool/tests/test_reuse_full.py`

**Interfaces:**
- Consumes: Task 1 的 `checker.full_asset_name`、`checker.update_asset_name`。
- Produces: `deb.build(dist_dir: Path, out_dir: Path, version: str) -> Path`（返回单个 deb 路径）；`deb.deb_filename(version) -> str`；CLI `deb.py build <dist> <out> <version>`。

- [ ] **Step 1: 写失败测试**（`test_deb.py` 删除 runtime/app 双包、`app_only`、`runtime_id` 相关用例，新增：）

```python
def test_one_package_named_like_the_client_expects():
    from labeling_tool.update import checker
    assert deb.deb_filename("0.2.0") == checker.full_asset_name("0.2.0", checker.LINUX)


def test_control_has_a_real_version_and_the_system_depends():
    f = _fields(deb.control("0.2.0", installed_kb=1))
    assert f["Package"] == "lm-labeling-tool"
    assert f["Version"] == "0.2.0"
    for lib in ("libgl1", "libxkbcommon-x11-0"):
        assert lib in f["Depends"]
    assert "lm-labeling-tool-runtime" not in f["Depends"]


def test_postrm_removes_files_dpkg_never_tracked():
    # zip updates write app-layer files outside dpkg's database
    assert "rm -rf /opt/lm-labeling-tool" in deb.POSTRM
    assert "remove|purge" in deb.POSTRM


def test_preinst_clears_the_app_layer_before_a_full_install():
    for d in ("_internal/labeling_tool", "_internal/annotation_tool", ".update-backup", ".update-staging"):
        assert f"/opt/lm-labeling-tool/{d}" in deb.PREINST


def test_build_produces_exactly_one_deb(tmp_path, dpkg_deb_available):
    dist = _make_dist(tmp_path)
    out = deb.build(dist, tmp_path / "out", "0.2.0")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["lm-labeling-tool_0.2.0_amd64.deb"]
    control = _extract_control(out, tmp_path / "ctl")
    assert "Version: 0.2.0" in control
```

`test_installer_script.py` 新增：

```python
def test_the_installer_has_no_app_layer_mode(iss):
    assert "MyLayer" not in iss and "MyRuntime" not in iss
    assert "OutputBaseFilename=LM_LabelingTool-Setup-v{#MyVersion}" in iss


def test_uninstall_removes_update_leftovers(iss):
    for name in (".update-backup", ".update-staging", ".update-journal"):
        assert f'{{app}}\\{name}' in iss
```

`test_reuse_full.py` 中把“上一版带 App exe”的夹具改为带 `update-v<ver>-<runtime>-windows.zip`：

```python
def test_reuse_when_the_previous_release_has_our_runtime_zip():
    rel = {"tagName": "v0.2.0", "assets": [{"name": n} for n in (
        "LM_LabelingTool-Setup-v0.2.0.exe", "update-v0.2.0-r11111111-windows.zip", "SHA256SUMS.txt")]}
    assert reuse_full.plan_reuse(rel, "r11111111") == ("v0.2.0", "LM_LabelingTool-Setup-v0.2.0.exe")
    assert reuse_full.plan_reuse(rel, "r22222222") is None
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_deb.py labeling_tool/tests/test_installer_script.py labeling_tool/tests/test_reuse_full.py -q -p no:cacheprovider`
Expected: FAIL（`deb_filename`、`control`、`POSTRM` 不存在；iss 仍含 `MyLayer`）

- [ ] **Step 3: 实现**

`packaging/deb.py`：模块 docstring 改为单包说明；删除 `RUNTIME_PACKAGE`、`runtime_control`、`app_control`、`app_deb_filename`、`runtime_deb_filename`、`_stage_runtime_layer`；新增：

```python
PACKAGE = "lm-labeling-tool"

PREINST = """#!/bin/sh
set -e
# A full install replaces the whole tree. zip updates may have added
# app-layer files dpkg never recorded; clear them so none survive.
rm -rf /opt/lm-labeling-tool/_internal/labeling_tool \\
       /opt/lm-labeling-tool/_internal/annotation_tool \\
       /opt/lm-labeling-tool/.update-backup \\
       /opt/lm-labeling-tool/.update-staging \\
       /opt/lm-labeling-tool/.update-journal
"""

POSTRM = """#!/bin/sh
set -e
case "$1" in
    remove|purge)
        # zip updates write files outside dpkg's database; remove them too.
        rm -rf /opt/lm-labeling-tool
        ;;
esac
"""


def control(version: str, installed_kb: int) -> str:
    return _control([
        ("Package", PACKAGE),
        ("Version", version),
        ("Architecture", ARCH),
        ("Maintainer", MAINTAINER),
        ("Installed-Size", str(int(installed_kb))),
        ("Depends", ", ".join(RUNTIME_DEPENDS)),
        ("Section", "graphics"),
        ("Priority", "optional"),
        ("Description", "LM Labeling Tool"),
    ])


def deb_filename(version: str) -> str:
    """Must agree with labeling_tool.update.checker.full_asset_name."""
    return f"{PACKAGE}_{version}_{ARCH}.deb"
```

`_write_control_dir(root, control, postinst=None)` 扩展为接收 `scripts: dict[str, str]`（`{"postinst": POSTINST, "preinst": PREINST, "postrm": POSTRM}`），对每个脚本写入并 `chmod +x`。`build` 改为：

```python
def build(dist_dir: Path, out_dir: Path, version: str) -> Path:
    """Build the single deb: the whole PyInstaller onedir under /opt plus
    the desktop entry, icons and /usr/bin link."""
    dist_dir, out_dir = Path(dist_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fast = bool(os.environ.get("LT_FAST"))
    with tempfile.TemporaryDirectory(prefix="deb-stage-") as tmp:
        root = Path(tmp) / "pkg"
        target = root / INSTALL_PREFIX.lstrip("/")
        shutil.copytree(dist_dir, target, symlinks=True)
        _stage_app_extras(dist_dir, root, version)
        size_kb = max(1, sum(p.stat().st_size for p in target.rglob("*")
                             if p.is_file() and not p.is_symlink()) // 1024)
        _write_control_dir(root, control(version, size_kb),
                           {"postinst": POSTINST, "preinst": PREINST, "postrm": POSTRM})
        out = out_dir / deb_filename(version)
        _dpkg_deb_build(root, out, fast)
    return out
```

`main` 只接受 `build <dist> <out> <version>`，打印 `deb: <path>`。

`packaging/installer.iss`：删除 `#ifndef MyLayer`、`#ifndef MyRuntime` 两段；`OutputBaseFilename` 只保留 `LM_LabelingTool-Setup-v{#MyVersion}`；`[InstallDelete]` 只保留 `Type: filesandordirs; Name: "{app}\_internal"` 并补充：

```
Type: filesandordirs; Name: "{app}\.update-backup"
Type: filesandordirs; Name: "{app}\.update-staging"
Type: files;          Name: "{app}\.update-journal"
```

新增：

```
[UninstallDelete]
; zip updates (labeling_tool/update/patch.py) leave these beside the install
Type: filesandordirs; Name: "{app}\.update-backup"
Type: filesandordirs; Name: "{app}\.update-staging"
Type: files;          Name: "{app}\.update-journal"
```

删除 `[Code]` 中 `#if MyLayer == "app"` … `#endif` 整段（`InstalledDir`、`Refuse`、`InitializeSetup` 的 runtime 守卫），保留 `WantsRestart`。

`packaging/reuse_full.py` 的 `plan_reuse`：

```python
    names = {a.get("name") for a in release.get("assets") or []}
    if checker.update_asset_name(version, runtime, checker.WINDOWS) not in names:
        return None   # runtime changed, or that release predates update zips
    full = checker.full_asset_name(version, checker.WINDOWS)
```

删除 `packaging/reuse_runtime.py`、`packaging/bundle_filters.py` 及其测试；`packaging/labeling_tool.spec` 中删除 `sys.path.insert(0, SPECPATH)`、`import bundle_filters`、`a.binaries = bundle_filters...` 三处及其注释（`import sys` 若无其他用途一并删除），并把 nccl/cupti 注释恢复为“这些 excludes 只在 Windows 生效；Linux 上 libtorch_cuda.so 链接 libnccl.so.2，PyInstaller 以符号链接收集，无重复数据”。

- [ ] **Step 4: 运行，确认通过**；全量测试（`test_local_build_sh.py` 等若引用 `--app-only` 在 Task 7 处理，此处先确认无导入错误）

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: 只剩 Task 7 将处理的 workflow / local-build 断言失败；记录失败名单。

- [ ] **Step 5: 提交**

```bash
git add -A packaging labeling_tool/tests
git commit -m "build: one installer per platform; drop the app-layer packages"
```

---

### Task 5: 韩语 Release 说明生成与检查

**Files:**
- Create: `packaging/release_notes.py`
- Test: `labeling_tool/tests/test_release_notes.py`

**Interfaces:**
- Consumes: `checker.full_asset_name`、`checker.NOTES_START/END`、`checker.GITHUB_REPO`。
- Produces: `check_korean(text: str) -> None`（不合格抛 `ValueError`）；`build_body(version: str, notes: str, repo: str = checker.GITHUB_REPO) -> str`；CLI `release_notes.py check <notes-file>`、`release_notes.py body <version> <notes-file> <out-file>`。

- [ ] **Step 1: 写失败测试**

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import release_notes  # noqa: E402

from labeling_tool.update import checker  # noqa: E402


def test_check_korean_rejects_han_and_requires_hangul():
    release_notes.check_korean("- 업데이트 방식 개선")
    with pytest.raises(ValueError):
        release_notes.check_korean("- 每次启动都检查更新")
    with pytest.raises(ValueError):
        release_notes.check_korean("- faster startup")
    with pytest.raises(ValueError):
        release_notes.check_korean("   ")


def test_body_links_the_two_packages_and_marks_the_notes():
    body = release_notes.build_body("0.2.0", "- 첫 번째 단일 설치 파일 배포")
    base = f"https://github.com/{checker.GITHUB_REPO}/releases/download/v0.2.0/"
    assert f"[EXE]({base}{checker.full_asset_name('0.2.0', checker.WINDOWS)})" in body
    assert f"({base}{checker.full_asset_name('0.2.0', checker.LINUX)})" in body
    assert "x86-64 (64-bit)" in body
    assert checker.extract_notes(body) == "- 첫 번째 단일 설치 파일 배포"
    release_notes.check_korean(body.split(checker.NOTES_END)[1])  # the guide is Korean too
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_release_notes.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 `packaging/release_notes.py`**

```python
"""The Korean release page: download table, change notes, file guide.

Change notes come from the annotated tag's message, which must be Korean.
The updater shows only the part between the notes markers
(checker.extract_notes), so the table and guide never reach its dialog.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labeling_tool.update import checker  # noqa: E402

_HAN = re.compile(r"[一-鿿]")
_HANGUL = re.compile(r"[가-힣]")


def check_korean(text: str) -> None:
    if _HAN.search(text or ""):
        raise ValueError("release notes must be Korean: Chinese characters found")
    if not _HANGUL.search(text or ""):
        raise ValueError("release notes must be Korean: no Hangul found")


def build_body(version: str, notes: str, repo: str = checker.GITHUB_REPO) -> str:
    base = f"https://github.com/{repo}/releases/download/v{version}/"
    exe = checker.full_asset_name(version, checker.WINDOWS)
    deb = checker.full_asset_name(version, checker.LINUX)
    return "\n".join([
        "| Architecture | Windows | Ubuntu 22.04 / 24.04 |",
        "|---|---|---|",
        f"| x86-64 (64-bit) | [EXE]({base}{exe}) | [Download]({base}{deb}) |",
        "",
        "## 변경 사항",
        checker.NOTES_START,
        notes.strip(),
        checker.NOTES_END,
        "",
        "### 어떤 파일을 받아야 하나요?",
        "- Windows: 위 표의 **EXE** 하나만 받으면 됩니다.",
        "- Ubuntu 22.04 / 24.04: 위 표의 **Download (.deb)** 하나만 받으면 됩니다.",
        "- 아래 Assets 의 update-*.zip, SHA256SUMS.txt, Source code 는 자동 업데이트용이므로 받지 않아도 됩니다.",
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) == 2 and args[0] == "check":
            check_korean(Path(args[1]).read_text(encoding="utf-8"))
            print("release notes are Korean")
            return 0
        if len(args) == 4 and args[0] == "body":
            notes = Path(args[2]).read_text(encoding="utf-8")
            check_korean(notes)
            Path(args[3]).write_text(build_body(args[1], notes), encoding="utf-8")
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("usage: release_notes.py check <notes> | body <version> <notes> <out>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行，确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_release_notes.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add packaging/release_notes.py labeling_tool/tests/test_release_notes.py
git commit -m "build: generate the Korean release page from the tag message"
```

---

### Task 6: 客户端流程（应用 zip、后台下载与缓存、启动恢复、定时检查、三语字符串）

**Files:**
- Modify: `labeling_tool/update/ui.py`、`labeling_tool/update/installer.py`、`labeling_tool/app.py`
- Modify: `labeling_tool/core/i18n/strings_ko.py`、`strings_zh.py`、`strings_en.py`
- Test: `labeling_tool/tests/test_update_ui.py`、`labeling_tool/tests/test_update_installer.py`、`tests/test_app_main.py`（或现有 `labeling_tool/tests/test_app_main.py`）

**Interfaces:**
- Consumes: Task 1 `checker.find_update`、`UpdateInfo(kind, assets[0])`；Task 2 `patch.apply_patch/recover/cleanup/PatchError`；`net_download.download_file(url, dest, sha256, progress=None)`；`app_paths.app_home()`、`app_paths.user_cache_home()`。
- Produces:
  - `installer.build_apply_command(exe: Path, zip_path: Path, sha256: str) -> list[str]` → `["pkexec", str(exe), "--apply-update", str(zip_path), "--sha256", sha256]`
  - `installer.apply_zip_linux(exe, zip_path, sha256, runner=subprocess.run) -> tuple[InstallOutcome, str]`
  - `ui.cached_update_path(info) -> Path`（`user_cache_home()/updates/<asset name>`）
  - `ui.ensure_downloaded(info, progress=None) -> Path`（缓存命中且校验相符则直接返回；否则重新下载）
  - `ui.apply_and_restart(parent, info, zip_path) -> bool`
  - `ui.start_periodic_checks(interval_ms: int = 4 * 3600 * 1000) -> None`
  - `app.main` 识别 `--apply-update <zip> --sha256 <hex>`，返回 0 / 1
  - 新字符串键：`update_ready_status`、`update_btn_restart`、`update_apply_failed_msg`、`update_ready_informative`

- [ ] **Step 1: 写失败测试**

`labeling_tool/tests/test_update_installer.py` 追加：

```python
def test_apply_command_runs_the_installed_app_as_root(tmp_path):
    from labeling_tool.update import installer
    cmd = installer.build_apply_command(tmp_path / "LM_LabelingTool", tmp_path / "u.zip", "a" * 64)
    assert cmd == ["pkexec", str(tmp_path / "LM_LabelingTool"), "--apply-update",
                   str(tmp_path / "u.zip"), "--sha256", "a" * 64]


def test_apply_zip_linux_classifies_cancel_and_failure(tmp_path):
    from types import SimpleNamespace
    from labeling_tool.update import installer
    z = tmp_path / "u.zip"; z.write_bytes(b"x")
    ok = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64,
                                   runner=lambda *a, **k: SimpleNamespace(returncode=0, stderr=""))
    assert ok[0] is installer.InstallOutcome.OK
    cancel = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64,
                                       runner=lambda *a, **k: SimpleNamespace(returncode=126, stderr=""))
    assert cancel[0] is installer.InstallOutcome.CANCELLED
    bad = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64,
                                    runner=lambda *a, **k: SimpleNamespace(returncode=1, stderr="runtime mismatch"))
    assert bad == (installer.InstallOutcome.FAILED, "runtime mismatch")
```

`labeling_tool/tests/test_update_ui.py` 追加（沿用该文件已有的 Qt 夹具与 `QMessageBox` mock 方式，不得弹出真实模态框）：

```python
from labeling_tool.update import checker, ui


def _zip_info(sha="a" * 64):
    return checker.UpdateInfo(
        version="0.2.1", variant="full", kind="app", notes="- 개선",
        assets=(checker.Asset("update-v0.2.1-r11111111-windows.zip", "https://x/u.zip", 10, sha),))


def test_a_cached_zip_with_the_right_checksum_is_not_downloaded_again(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)
    data = b"zip bytes"
    info = _zip_info(hashlib.sha256(data).hexdigest())
    path = ui.cached_update_path(info)
    path.parent.mkdir(parents=True); path.write_bytes(data)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded again")))
    assert ui.ensure_downloaded(info) == path


def test_a_corrupt_cached_zip_is_downloaded_again(tmp_path, monkeypatch):
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)
    info = _zip_info()
    path = ui.cached_update_path(info)
    path.parent.mkdir(parents=True); path.write_bytes(b"half a download")
    calls = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: calls.append(dest) or dest.write_bytes(b"ok"))
    ui.ensure_downloaded(info)
    assert calls == [path]


def test_other_cached_updates_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)
    info = _zip_info()
    stale = tmp_path / "updates" / "update-v0.1.9-r11111111-windows.zip"
    stale.parent.mkdir(parents=True); stale.write_bytes(b"old")
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"ok"))
    ui.ensure_downloaded(info)
    assert not stale.exists()


def test_periodic_checks_start_one_timer(qapp, monkeypatch):
    monkeypatch.setattr(ui, "_PERIODIC", [])
    ui.start_periodic_checks(1000)
    ui.start_periodic_checks(1000)
    assert len(ui._PERIODIC) == 1 and ui._PERIODIC[0].interval() == 1000
```

`test_app_main.py` 追加：

```python
def test_main_applies_an_update_and_reports_failure(monkeypatch, tmp_path, capsys):
    from labeling_tool import app
    from labeling_tool.update import patch
    seen = {}
    monkeypatch.setattr(patch, "apply_patch",
                        lambda z, root, sha: seen.update(z=z, sha=sha))
    assert app.main(["--apply-update", str(tmp_path / "u.zip"), "--sha256", "a" * 64]) == 0
    assert seen["sha"] == "a" * 64

    def boom(*a, **k):
        raise patch.PatchError("runtime mismatch")
    monkeypatch.setattr(patch, "apply_patch", boom)
    assert app.main(["--apply-update", str(tmp_path / "u.zip"), "--sha256", "a" * 64]) == 1
    assert "runtime mismatch" in capsys.readouterr().err


def test_main_recovers_an_interrupted_update_before_anything_else(monkeypatch):
    from labeling_tool import app, selftest
    from labeling_tool.update import patch
    order = []
    monkeypatch.setattr(patch, "recover", lambda root: order.append("recover") or False)
    monkeypatch.setattr(patch, "cleanup", lambda root: order.append("cleanup"))
    monkeypatch.setattr(selftest, "run_selftest", lambda v: order.append("selftest") or 0)
    app.main(["--selftest=full"])
    assert order[:2] == ["recover", "cleanup"]
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_ui.py labeling_tool/tests/test_update_installer.py labeling_tool/tests/test_app_main.py tests -q -p no:cacheprovider`
Expected: FAIL（新函数不存在）

- [ ] **Step 3: 实现**

`labeling_tool/update/installer.py` 追加：

```python
def build_apply_command(exe: Path, zip_path: Path, sha256: str) -> list[str]:
    """Linux: /opt is root-owned, so the installed app applies its own update
    zip as root. The zip is re-verified there (see patch.apply_patch)."""
    return ["pkexec", str(exe), "--apply-update", str(zip_path), "--sha256", sha256]


def apply_zip_linux(exe: Path, zip_path: Path, sha256: str,
                    runner=subprocess.run) -> tuple[InstallOutcome, str]:
    if not Path(zip_path).is_file():
        raise FileNotFoundError(zip_path)
    try:
        result = runner(build_apply_command(exe, zip_path, sha256), capture_output=True,
                        text=True, check=False, env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError:
        return InstallOutcome.FAILED, "pkexec not found: install polkit"
    stderr = (getattr(result, "stderr", "") or "").strip()
    if result.returncode == 0:
        return InstallOutcome.OK, stderr
    if result.returncode == PKEXEC_CANCELLED:
        return InstallOutcome.CANCELLED, stderr
    return InstallOutcome.FAILED, stderr
```

`labeling_tool/app.py`：确认文件顶部已有 `import sys` 与 `from pathlib import Path`（没有则补上）；在 `main()` 开头（`--selftest` 判断之前）加入：

```python
    from labeling_tool.core.app_paths import app_home, is_frozen
    from labeling_tool.update import patch
    if is_frozen():
        # A swap interrupted by a crash or power cut is undone before any of
        # our own (possibly half-replaced) modules beyond these are imported.
        patch.recover(app_home())
        patch.cleanup(app_home())
    if "--apply-update" in argv:
        i = argv.index("--apply-update")
        zip_path = argv[i + 1]
        sha = argv[argv.index("--sha256") + 1]
        try:
            patch.apply_patch(Path(zip_path), app_home(), sha)
        except patch.PatchError as exc:
            print(f"update failed: {exc}", file=sys.stderr)
            return 1
        return 0
```

（测试中 `is_frozen()` 为 False；`test_main_recovers...` 需同时 `monkeypatch.setattr("labeling_tool.core.app_paths.is_frozen", lambda: True)`——在测试里补上这一行。）

`labeling_tool/update/ui.py`：

```python
_PERIODIC: list = []   # the one QTimer, kept alive for the app's lifetime


def cached_update_path(info) -> Path:
    return app_paths.user_cache_home() / "updates" / info.assets[0].name


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_downloaded(info, progress=None) -> Path:
    """The verified update file, from the cache when it is already there.
    A partial or tampered cache entry is downloaded again; other cached
    updates are removed."""
    path = cached_update_path(info)
    path.parent.mkdir(parents=True, exist_ok=True)
    for other in path.parent.iterdir():
        if other != path:
            other.unlink(missing_ok=True)
    asset = info.assets[0]
    if path.is_file() and _sha256(path) == asset.sha256:
        return path
    path.unlink(missing_ok=True)
    net_download.download_file(asset.url, path, asset.sha256, progress=progress)
    return path


def apply_and_restart(parent, info, zip_path: Path) -> bool:
    """Apply a downloaded zip and relaunch. False = still on the old version."""
    import subprocess
    from labeling_tool.update import patch
    exe = app_paths.app_home() / ("LM_LabelingTool.exe"
                                  if checker.current_platform() == checker.WINDOWS
                                  else "LM_LabelingTool")
    if checker.current_platform() == checker.WINDOWS:
        try:
            patch.apply_patch(zip_path, app_paths.app_home(), info.assets[0].sha256)
        except patch.PatchError as exc:
            QMessageBox.warning(parent, tr("update_failed_title"),
                                tr("update_apply_failed_msg", exc=exc))
            return False
    else:
        outcome, detail = installer.apply_zip_linux(exe, zip_path, info.assets[0].sha256)
        if outcome is installer.InstallOutcome.CANCELLED:
            return False
        if outcome is not installer.InstallOutcome.OK:
            QMessageBox.warning(parent, tr("update_failed_title"),
                                tr("update_apply_failed_msg", exc=detail))
            return False
    subprocess.Popen([str(exe)], **installer.launch_and_exit_args())
    QApplication.quit()
    return True


def start_periodic_checks(interval_ms: int = 4 * 3600 * 1000) -> None:
    from PyQt5.QtCore import QTimer
    if _PERIODIC:
        return
    timer = QTimer()
    timer.setInterval(interval_ms)
    timer.timeout.connect(lambda: check_for_updates(None))
    timer.start()
    _PERIODIC.append(timer)
```

修改流程：
- `prompt_and_install`：`kind == "app"` 时调用 `ensure_downloaded(info, progress)`（已缓存则不显示进度）后 `apply_and_restart`；`kind == "full"` 沿用现有下载 + `_hand_over`（`_hand_over` 中 `install_debs(paths)` 只有一个 deb）。
- `_ask`：`kind == "app"` 时更新按钮文字用 `tr("update_btn_restart")`，正文用 `tr("update_ready_informative", notes=info.notes)`；`notes` 不再截取前 8 行（`checker.extract_notes` 已处理）。
- `check_for_updates._on_found`：对 `kind == "app"` 先在后台下载——新增 `UpdateDownloadThread(QThread)`（`done = pyqtSignal(object)`，`run()` 中调用 `ensure_downloaded(self.info)`，异常时 emit 异常并 `vlog().info`），完成后：会话进行中则 `_PENDING[:] = [(found, home)]`，并在可见的 `QMainWindow` 的 `statusBar()` 上 `showMessage(tr("update_ready_status", version=found.version))`；否则立即 `prompt_and_install`。下载失败静默（只写日志）。线程生命周期沿用 `_RUNNING_CHECKS` 的持有方式。
- `labeling_tool/app.py`：在 `check_for_updates(None)` 之后调用 `start_periodic_checks()`。

三语字符串（`strings_ko.py` / `strings_zh.py` / `strings_en.py`，按术语表）：

| key | ko | zh | en |
|---|---|---|---|
| `update_ready_status` | `새 버전 v{version} 준비됨 — 작업 창을 닫으면 업데이트합니다` | `新版本 v{version} 已就绪 — 关闭作业窗口后更新` | `Version {version} is ready — it installs when you close this window` |
| `update_btn_restart` | `지금 재시작하여 업데이트` | `立即重启并更新` | `Restart and update` |
| `update_ready_informative` | `업데이트가 준비되었습니다. 재시작하면 바로 적용됩니다.\n\n{notes}` | `更新已就绪，重启后立即生效。\n\n{notes}` | `The update is ready and applies on restart.\n\n{notes}` |
| `update_apply_failed_msg` | `업데이트를 적용하지 못했습니다. 프로그램을 모두 닫고 다시 시도하세요.\n\n{exc}` | `未能应用更新。请关闭所有程序窗口后重试。\n\n{exc}` | `The update could not be applied. Close every window of the program and try again.\n\n{exc}` |

- [ ] **Step 4: 运行，确认通过**，并全量测试

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: 除 Task 7 的 workflow / local-build 断言外全部通过

- [ ] **Step 5: 启动冒烟**

Run: `QT_QPA_PLATFORM=offscreen timeout 8 .venv/bin/python -m labeling_tool.app; [ $? = 124 ] && echo started-ok`
Expected: `started-ok`

- [ ] **Step 6: 提交**

```bash
git add labeling_tool
git commit -m "feat(update): download zips in the background, apply them, check every 4h"
```

---

### Task 7: CI 与本地验证脚本改为新产物

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `packaging/ci/local-build.sh`、`packaging/ci/local-build.ps1`
- Test: `labeling_tool/tests/test_installer_script.py`（workflow 部分）、`labeling_tool/tests/test_local_build_sh.py`

**Interfaces:**
- Consumes: Task 3 `update_zip.py` CLI；Task 4 `deb.py build <dist> <out> <ver>`、`reuse_full.py`；Task 5 `release_notes.py check|body`；Task 2/6 `LM_LabelingTool --apply-update <zip> --sha256 <hex>`。

- [ ] **Step 1: 写失败测试**（`test_installer_script.py` 删除 `test_release_asserts_all_four_assets_are_present` 中对 runtime deb、`App-` 的旧断言、`test_the_runner_installs_the_debs_before_running_the_installed_app` 中 `lm-labeling-tool-runtime_` 的匹配、依赖守卫相关断言，新增：）

```python
def test_each_platform_publishes_one_package_and_one_zip(workflow):
    assert "LM_LabelingTool-App-" not in workflow
    assert "lm-labeling-tool-runtime" not in workflow
    assert "reuse_runtime.py" not in workflow
    assert workflow.count("packaging/update_zip.py") == 2


def test_the_release_page_is_generated_and_korean(workflow):
    assert "packaging/release_notes.py body" in workflow
    assert "body_path:" in workflow
    # checked before the 30-minute builds, not after them
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(workflow)["jobs"]["build-linux"]["steps"]
    version = next(s for s in steps if s.get("name") == "Version")["run"]
    assert "release_notes.py check" in version


def test_ci_proves_a_zip_update_on_the_installed_app(workflow):
    assert "--apply-update" in workflow
```

`test_local_build_sh.py` 新增：

```python
def test_smoke_proves_a_zip_update():
    text = SH.read_text(encoding="utf-8")
    assert "--apply-update" in text
    assert "--app-only" not in text and "rdeadbeef" not in text
```

- [ ] **Step 2: 运行，确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_installer_script.py labeling_tool/tests/test_local_build_sh.py -q -p no:cacheprovider`
Expected: FAIL

- [ ] **Step 3: 修改 `release.yml`**

1. 两个 job 的 checkout 改为 `with: { fetch-depth: 1, fetch-tags: true }`；build-linux 的 `Version` 步骤在 tag 分支追加：
   ```bash
   git fetch --force origin "refs/tags/$GITHUB_REF_NAME:refs/tags/$GITHUB_REF_NAME"
   git tag -l --format='%(contents)' "$GITHUB_REF_NAME" > "$RUNNER_TEMP/notes.txt"
   python packaging/release_notes.py check "$RUNNER_TEMP/notes.txt"
   ```
2. Windows：`Build installers` 删除 app 层 ISCC 调用与 `/DMyRuntime`；`Stage the app layer` 之后新增：
   ```powershell
   python packaging/update_zip.py dist/app-layer out $ver $env:LT_RUNTIME win32
   if ($LASTEXITCODE -ne 0) { throw "update zip failed" }
   ```
   `Assert the asset names` 改为检查 `checker.full_asset_name(ver, WINDOWS)` 与 `checker.update_asset_name(ver, rt, WINDOWS)` 都在 `out\`；`Checksums` 改为对 `out\*.exe, out\*.zip` 计算。
3. Linux：删除 `Reuse the previous runtime deb…` 步骤与 `Dependency guard…` 步骤；`Build debs` 改为
   ```bash
   python packaging/deb.py build dist/LM_LabelingTool out "$ver"
   python packaging/update_zip.py dist/app-layer out "$ver" "$LT_RUNTIME" linux
   ```
   大小上限检查改查 `checker.full_asset_name(ver, LINUX)`；名称检查改为 deb + zip；冒烟 1/2、24.04 的 `dpkg -i` 只装 `/out/lm-labeling-tool_*.deb`；冒烟 2/2 之后新增步骤：
   ```yaml
   - name: Update round trip -- the installed app applies its own zip
     run: |
       set -euo pipefail
       zip=$(ls out/update-v*-linux.zip)
       sha=$(sha256sum "$zip" | cut -d' ' -f1)
       # Damage one installed app-layer file, then let the zip repair it.
       # (build-info.json must stay intact: apply_patch reads its runtime id.)
       victim=$(cd /opt/lm-labeling-tool && find _internal/labeling_tool -name '*.pyc' | head -1)
       sudo rm "/opt/lm-labeling-tool/$victim"
       timeout 300 sudo /opt/lm-labeling-tool/LM_LabelingTool --apply-update "$zip" --sha256 "$sha"
       test -f "/opt/lm-labeling-tool/$victim"
       test ! -e /opt/lm-labeling-tool/.update-journal
       rm -f "$HOME/.local/share/lm-labeling-tool/selftest.log"
       timeout 300 xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest=full
       echo "zip update applied and the app still passes its selftest"
   ```
   `Checksums` 改为对 `*.deb *.zip` 计算。
4. release job：资产断言改为 4 个文件（`full_asset_name` ×2、`update_asset_name` ×2 用 glob `update-v{ver}-r*-windows.zip` / `-linux.zip`）加校验；`Publish` 前新增：
   ```bash
   git fetch --force origin "refs/tags/$GITHUB_REF_NAME:refs/tags/$GITHUB_REF_NAME"
   git tag -l --format='%(contents)' "$GITHUB_REF_NAME" > notes.txt
   python packaging/release_notes.py body "${GITHUB_REF_NAME#v}" notes.txt body.md
   ```
   `softprops/action-gh-release@v2` 增加 `body_path: body.md`。

- [ ] **Step 4: 修改本地脚本**

`packaging/ci/local-build.sh`：`step_deb` 改为 `deb.py build "$DIST" out "$version"` 加 `update_zip.py dist/app-layer out "$version" "$RUNTIME_ID" linux`（`step_layers` 中已 stage `dist/app-layer`；如无则补上 `layers.py stage`）；`step_smoke` 删除 3/4 依赖守卫，改为与 CI 相同的 “update round trip”（外层容器内执行，命令同上，去掉 `sudo`）；所有 `dpkg -i` 只装单个 deb。

`packaging/ci/local-build.ps1`：`installer` 步骤只编译 Setup，并运行 `update_zip.py dist/app-layer out $Version $script:runtimeId win32`；`smoke` 步骤安装完整包并 selftest 后，删除 `$target\_internal\labeling_tool` 下一个 `.pyc`，运行 `Invoke-Bounded -Path "$target\LM_LabelingTool.exe" -CallArgs @("--apply-update", $zip.FullName, "--sha256", $sha)`，断言该文件恢复、`.update-journal` 不存在、再次 selftest 通过；删除 app 包与错配包的安装检查；卸载后断言 `.update-backup` 不残留。

- [ ] **Step 5: 运行测试，确认通过；YAML 可解析；全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider && .venv/bin/python -c "import yaml;yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: 全部通过

- [ ] **Step 6: 本地完整验证 Linux**（约 30～40 分钟，后台运行）

Run（仓库根目录）：
`docker run --rm -v "$PWD:/repo" -v /var/run/docker.sock:/var/run/docker.sock -e HOST_REPO_ROOT="$PWD" --tmpfs /repo/.venv -w /repo ubuntu:22.04 bash packaging/ci/local-build.sh`
Expected: 所有步骤 PASS（依赖 Task 8 先修好容器内的两个测试；若 Task 8 未完成，用 `--steps build,selftest,layers,deb,smoke`）

- [ ] **Step 7: 提交**

```bash
git add .github/workflows/release.yml packaging/ci labeling_tool/tests
git commit -m "ci: publish one package and one update zip per platform, prove the zip"
```

---

### Task 8: 修复构建容器中失败的两个测试

**Files:**
- Modify: `labeling_tool/tests/test_window_icon.py`
- Modify: `tests/test_app_paths.py`
- （根据诊断结果）Modify: 失败根因所在文件

- [ ] **Step 1: 让子进程失败可诊断**——在 `tests/test_app_paths.py::test_frozen_module_constants_live_next_to_exe_on_windows` 中把 `subprocess.run(..., check=True)` 改为：

```python
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: 在构建容器中只跑测试步骤，读出真实报错**

Run: `docker run --rm -v "$PWD:/repo" -v /var/run/docker.sock:/var/run/docker.sock -e HOST_REPO_ROOT="$PWD" --tmpfs /repo/.venv -w /repo ubuntu:22.04 bash packaging/ci/local-build.sh --steps tests 2>&1 | grep -A30 "test_frozen_module_constants"`
Expected: 断言消息中出现子进程 stderr 的 Traceback，指出具体失败的导入或属性。按报错修复根因（例如模块在 `sys.platform='win32'` 下访问 Windows 专属 API 时改为惰性访问）；修复后为该根因补一个不依赖容器的单元测试。

- [ ] **Step 3: 图标测试改为容差比较**——`test_small_png_keeps_the_small_branch_tuning_not_a_256px_downscale` 中逐字节比较改为像素比较（Pillow 12.2 与 12.3 的抗锯齿差 1 级灰度）：

```python
    from PIL import Image, ImageChops
    shipped = Image.open(shipped_path).convert("RGBA")
    rendered = make_icon.render(16).convert("RGBA")
    assert shipped.size == rendered.size
    diff = ImageChops.difference(shipped, rendered)
    assert max(b for _, b in (band.getextrema() for band in diff.split())) <= 2, \
        "shipped icon-16.png drifted from make_icon.render(16) beyond antialiasing noise"
```

（保留测试原意：小尺寸图标来自小尺寸专用渲染而非 256px 缩放——缩放版与专用渲染的差异远大于 2。）

- [ ] **Step 4: 本机全量测试 + 容器测试步骤**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`，再执行 Step 2 的命令（去掉 grep）
Expected: 两处都全部通过

- [ ] **Step 5: 提交**

```bash
git add tests labeling_tool/tests <根因文件>
git commit -m "test: make two checks pass under the locked build environment"
```

---

### Task 9: 文档与项目记忆

**Files:**
- Modify: `README.md`（Windows/Linux 安装与更新章节）、`docs/RELEASING.md`、`docs/superpowers/specs/2026-09-30-linux-deb-distribution-design.md`（文首加“已被 2026-10-02 单安装包设计取代的部分”说明）
- Memory: `project-linux-deb-distribution.md`、`project-release-process.md`、`project-layered-updates.md`、`project-state-2026-10-01.md`（新建 `project-state-2026-10-02.md` 并更新 `MEMORY.md` 索引）

- [ ] **Step 1:** README：安装文件表改为单个 exe / 单个 deb；Linux 安装命令改为 `sudo dpkg -i lm-labeling-tool_<버전>_amd64.deb`，卸载为 `sudo apt purge lm-labeling-tool`；更新说明改为“코드만 바뀐 업데이트는 약 1~2 MB 의 업데이트 파일을 백그라운드에서 받아 재시작 시 적용（Linux 는 비밀번호 입력 1회）”。
- [ ] **Step 2:** RELEASING.md：发布步骤改为“写韩语 annotated tag → 先 `gh workflow run release.yml -f release_compression=true` 演练 → 打 tag”；产物表改为 4 个文件；删除 app 包、runtime deb 复用、依赖守卫的章节；新增“tag 注释必须是韩语，CI 会检查”。
- [ ] **Step 3:** 记忆：更正 NCCL 结论（符号链接，无重复）；记录新产物与 zip 更新机制、版本号重排、Release 说明韩语规则。
- [ ] **Step 4:** 全量测试后提交

```bash
git add README.md docs
git commit -m "docs: describe single-package releases and zip updates"
```

---

### Task 10: 版本号重排与 v0.2.0 发布

前提：Task 1～9 全部完成并已推送到 `main`。以下为对外操作，逐步执行并在每步确认输出。

- [ ] **Step 1: 发布级演练**

Run: `gh workflow run release.yml --ref main -f release_compression=true`，等待完成
Expected: build-windows、build-linux 成功（含 “Update round trip”）；`out/` 中每个平台一个安装包和一个 zip；Linux deb 小于 2,040,109,465 字节

- [ ] **Step 2: tag 改名（保留原提交，注释改为韩语）**

```bash
for pair in v1.1.0:v0.0.1 v1.2.0:v0.0.2 v1.3.0:v0.0.3 v1.4.0:v0.0.4 v1.4.1:v0.0.5 v2.0.0:v0.1.0; do
  old=${pair%%:*}; new=${pair##*:}
  commit=$(git rev-list -n1 "$old")
  git tag -a "$new" "$commit" -m "$new (이전 $old)"
done
git push origin v0.0.1 v0.0.2 v0.0.3 v0.0.4 v0.0.5 v0.1.0
```

- [ ] **Step 3: 删除全部旧 Release 与旧 tag**

```bash
for t in v1.1.0 v1.2.0 v1.3.0 v1.4.0 v1.4.1 v2.0.0; do
  gh release delete "$t" --yes 2>/dev/null || true
  git push origin ":refs/tags/$t"; git tag -d "$t"
done
gh release list
```
Expected: `gh release list` 为空

- [ ] **Step 4: 打 v0.2.0（韩语注释）并推送**

```bash
git tag -a v0.2.0 -m "- 설치 파일을 플랫폼별 하나로 정리했습니다 (Windows EXE, Ubuntu .deb).
- 코드만 바뀐 업데이트는 약 1~2 MB 업데이트 파일을 백그라운드에서 받아 재시작 시 적용합니다.
- 실행 중에도 4시간마다 새 버전을 확인합니다."
git push origin v0.2.0
```

- [ ] **Step 5: 核对 Release 页面**

Run: `gh release view v0.2.0 --json body,assets --jq '.body, (.assets[].name)'`
Expected: 正文以下载表格开头、含 `<!-- notes:start -->` 段；资产恰为 `LM_LabelingTool-Setup-v0.2.0.exe`、`lm-labeling-tool_0.2.0_amd64.deb`、两个 `update-v0.2.0-r*-*.zip`、`SHA256SUMS.txt`

---

### Task 11: 真机端到端验证与使用说明 PPT 更新

- [ ] **Step 1:** WinBoat 虚拟机：卸载 v1.4.1（0.x 不会被视为更新），从 v0.2.0 Release 页面表格的 EXE 安装，确认启动与版本显示 0.2.0。
- [ ] **Step 2:** 任意一处代码改动（例如韩语字符串微调）走 Task 10 Step 1 演练后打 `v0.2.1`（韩语注释），在虚拟机中等待启动检查：确认后台下载完成、弹窗为「지금 재시작하여 업데이트」、点击后约数秒内重启并显示 0.2.1、安装目录无 `.update-journal`、下次启动后 `.update-backup` 被清除。
- [ ] **Step 3:** PPT：重拍“1단계～3단계”（新 Release 页面表格、单个 EXE 链接）与“自动更新”页（新弹窗文字），删除“✕ App 파일은 받지 마세요”的提示，更新附录 Linux 页为单个 deb；重新渲染核对后覆盖 `~/Documents/LM_LabelingTool_사용설명서_v2.0.0.pptx` 并改名为 `…_v0.2.pptx`。
