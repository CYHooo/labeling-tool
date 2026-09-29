# 第二期：改名、图标、变体收敛与分层分发 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把软件改名为 `LM_LabelingTool`、加上自有图标、只发布 full 一个变体，并把安装包拆成应用层与运行时层，使代码改动的更新从 1536 MB 降到约 30 MB。

**Architecture:** 构建产物按白名单分成应用层（exe + 自有代码数据）与运行时层（其余一切）。CI 计算运行时层的哈希汇总作为 `runtime` 标识，写进 `build-info.json`，并用同一份 Inno 脚本以 `/DMyLayer=full|app` 生成两个安装器；`runtime` 出现在应用包的资产名里，客户端据此按名选包，无需额外元数据。运行时层变化时退回完整安装包。

**Tech Stack:** Python 3.12、PyQt5、PyInstaller 6.22.3（onedir）、Inno Setup 6、GitHub Actions（windows-latest）

**Spec:** `docs/superpowers/specs/2026-09-28-layered-distribution-design.md`（分层分发）与 `docs/superpowers/specs/2026-09-28-ui-refresh-and-rebrand-design.md` 第 5 节（改名、图标、变体收敛）

## Global Constraints

- 软件名一律 `LM_LabelingTool`，不使用括号承载变体说明。
- 只发布 `full` 一个变体，`lite` 废弃。
- 用户可见文案先改 `docs/i18n-glossary.md` 再改 `labeling_tool/core/i18n/strings_{ko,zh,en}.py`，三份文件的键必须完全一致。
- 代码注释用英文；日志与异常文本保持英文。
- 技术标识符永不翻译：`sessionId`、`BASE URL`、`X-Viewer-Api-Key`、`SHA256`、文件路径、few-shot 类名。
- 既有术语沿用：균열 / 박리 / 축척 / 보수 구역 / 마스크 / 라벨링 / 로딩。
- 测试命令固定为 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`，基线 404 通过，全程保持绿。
- offscreen Qt 下模态 `QMessageBox` 会挂起测试进程，新增失败路径一律走内嵌显示。
- Inno 的 `AppId` 保持 full 变体原值 `{{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}`，使现有安装被识别为升级。
- 标签必须是纯数字格式（`v1.3.0`），带后缀会破坏 Windows 版本资源。
- 提交信息用 conventional commits，结尾附 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 与 `Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq` 两行真实 trailer。

## Review Focus

- **应用包误删运行时层** — `installer.iss` 现有 `[InstallDelete] Type: filesandordirs; Name: "{app}\_internal"` 会在安装前删掉整个 `_internal`。应用包若照搬，装完只剩应用层文件，1.4 GB 运行时层丢失，程序无法启动。这是本期最危险的一条。测试归 Task 5。
- **旧 `build-info.json` 没有 `runtime` 字段** — 从 v1.2.0 升级上来的机器读到的 JSON 里没有该键，`read_build_info()` 必须当作不可增量处理并照常工作，不得抛异常或把整个构建信息判成 dev。测试归 Task 1。
- **release 里只有完整包、没有匹配的应用包** — 首次发布 v1.3.0 时，以及运行时层变化的每一次发布，都是这种情况。`find_update()` 必须干净地退回完整包，而不是返回 `None` 让用户永远收不到更新。测试归 Task 2。
- **`runtime` 为空时仍去拼应用包名** — 会生成 `...-App-v1.3.1-None.exe` 这种资产名，永远匹配不到，且掩盖了真正的原因。空 `runtime` 必须直接走完整包路径。测试归 Task 2。
- **应用包装到 `runtime` 不符的机器上** — 正常路径由资产名保证，但用户可能手动下错包。安装器必须拒绝并提示，而不是装上去让程序崩溃。测试归 Task 5。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `packaging/layers.py` | 分层白名单规则 + 计算 `runtime` 标识；CI 与测试共用 | 新建 |
| `labeling_tool/update/version.py` | `BuildInfo` 增加 `runtime` 字段 | 修改 |
| `labeling_tool/update/checker.py` | 按 `runtime` 选包，`UpdateInfo` 增加 `kind` | 修改 |
| `labeling_tool/update/ui.py` | 两种 `kind` 的提示文案 | 修改 |
| `labeling_tool/core/i18n/strings_{ko,zh,en}.py` | 更新提示新文案 | 修改 |
| `docs/i18n-glossary.md` | 登记「완전 재설치 / 完整重装」概念 | 修改 |
| `packaging/icon.svg` | 图标源文件（方案 A 字母标） | 新建 |
| `packaging/icon.ico` | 多尺寸图标，7 层 | 新建 |
| `packaging/labeling_tool.spec` | 改名、去掉 lite 分支、接入图标 | 修改 |
| `packaging/installer.iss` | 改名、单变体、双层、`runtime` 校验 | 修改 |
| `.github/workflows/build-windows.yml` | 单变体构建、分层、生成两个包、资产名断言、卸载验证 | 修改 |
| `labeling_tool/tests/test_layers.py` | 分层与 `runtime` 计算测试 | 新建 |
| `labeling_tool/tests/test_update_layered.py` | 选包逻辑测试 | 新建 |

**本地可测范围**：Task 1-3 是纯 Python，本地全量测试覆盖。Task 4-6 是打包与 CI 层，本地无法验证（需要 Windows + Inno Setup），只能靠 CI 的安装—自检—卸载流程。这个现实约束意味着 Task 4-6 的每次提交都要推分支等 CI，不能靠本地跑绿就认为完成。

---

### Task 1: 运行时标识与分层规则

**Files:**
- Create: `packaging/layers.py`
- Modify: `labeling_tool/update/version.py`
- Test: `labeling_tool/tests/test_layers.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces:
  - `packaging.layers.APP_LAYER_PREFIXES` — `tuple[str, ...]`，应用层路径前缀白名单
  - `packaging.layers.is_app_layer(relpath: str) -> bool` — 相对路径（正斜杠分隔）是否属于应用层
  - `packaging.layers.compute_runtime_id(dist_dir: Path) -> str` — 返回形如 `r3f8a1c92` 的标识
  - `labeling_tool.update.version.BuildInfo.runtime` — `str | None`

- [ ] **Step 1: 写失败的测试**

新建 `labeling_tool/tests/test_layers.py`：

```python
"""Layer split and runtime identity. The runtime id must change when any
runtime-layer file changes, and must not change when only app-layer files do
-- that is what lets an update ship 30 MB instead of 1.5 GB."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import layers  # noqa: E402


def _make_dist(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return tmp_path


def test_app_layer_covers_exe_and_own_packages():
    assert layers.is_app_layer("LM_LabelingTool.exe")
    assert layers.is_app_layer("_internal/labeling_tool/models/sam/mobile.onnx")
    assert layers.is_app_layer("_internal/annotation_tool/configs.py")


def test_runtime_layer_is_everything_else():
    assert not layers.is_app_layer("_internal/torch/lib/torch_cpu.dll")
    assert not layers.is_app_layer("_internal/nvidia/cudnn/bin/cudnn64_9.dll")
    assert not layers.is_app_layer("_internal/PyQt5/Qt5/bin/Qt5Core.dll")
    assert not layers.is_app_layer("_internal/base_library.zip")


def test_a_new_third_party_dependency_lands_in_the_runtime_layer():
    """The whitelist runs the right way round: anything we did not name is
    runtime, so a new dependency forces a full reinstall rather than
    silently riding along in a partial app package."""
    assert not layers.is_app_layer("_internal/scipy/linalg/_flapack.pyd")


def test_runtime_id_is_stable_for_identical_trees(tmp_path):
    files = {"_internal/torch/a.dll": b"aaa", "LM_LabelingTool.exe": b"app-v1"}
    one = _make_dist(tmp_path / "one", files)
    two = _make_dist(tmp_path / "two", files)
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_ignores_app_layer_changes(tmp_path):
    base = {"_internal/torch/a.dll": b"aaa"}
    one = _make_dist(tmp_path / "one", {**base, "LM_LabelingTool.exe": b"app-v1"})
    two = _make_dist(tmp_path / "two", {**base, "LM_LabelingTool.exe": b"app-v2"})
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_changes(tmp_path):
    app = {"LM_LabelingTool.exe": b"app-v1"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"aaa"})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/a.dll": b"bbb"})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_added(tmp_path):
    app = {"LM_LabelingTool.exe": b"app-v1", "_internal/torch/a.dll": b"aaa"}
    one = _make_dist(tmp_path / "one", app)
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/b.dll": b"ccc"})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_format(tmp_path):
    import re
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"aaa"})
    assert re.fullmatch(r"r[0-9a-f]{8}", layers.compute_runtime_id(d))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_layers.py -q -p no:cacheprovider`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'layers'`

- [ ] **Step 3: 写 packaging/layers.py**

```python
"""Split the PyInstaller onedir output into an app layer and a runtime layer.

The app layer is our own code and data; everything else -- Python, PyQt5,
torch, the CUDA runtime -- is the runtime layer, about 1.4 GB that almost
never changes. Publishing them separately lets a code-only release ship
tens of MB instead of 1.5 GB.

The whitelist runs this way round on purpose: anything not named here is
runtime, so a newly added third-party dependency changes the runtime id and
forces a full reinstall, instead of riding along inside a partial app
package that would install missing its own dependency.

Imported by CI (see .github/workflows/build-windows.yml) and by the tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Relative paths (forward slashes) that belong to the app layer.
APP_LAYER_PREFIXES = (
    "LM_LabelingTool.exe",
    "_internal/labeling_tool/",
    "_internal/annotation_tool/",
)


def is_app_layer(relpath: str) -> bool:
    """True when this file ships in the small app-only package."""
    rel = relpath.replace("\\", "/")
    return any(rel == p or rel.startswith(p) for p in APP_LAYER_PREFIXES)


def iter_runtime_files(dist_dir: Path):
    """Every runtime-layer file under dist_dir, sorted by relative path."""
    root = Path(dist_dir)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if not is_app_layer(rel):
            yield rel, path


def compute_runtime_id(dist_dir: Path) -> str:
    """A short, stable identity for the runtime layer's exact contents.

    Hashes each runtime file's relative path and SHA256, in path order, then
    hashes that. Any added, removed or changed runtime file moves the id, so
    nobody has to remember to bump a version number."""
    digest = hashlib.sha256()
    for rel, path in iter_runtime_files(dist_dir):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return "r" + digest.hexdigest()[:8]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_layers.py -q -p no:cacheprovider`
Expected: PASS，8 passed

- [ ] **Step 5: 写 BuildInfo.runtime 的失败测试**

在 `labeling_tool/tests/test_layers.py` 末尾追加：

```python
# ------------------------------------------------------- build-info.json
# A machine upgrading from v1.2.0 has a build-info.json with no `runtime`
# key. That must read as "cannot do a layered update", not as a crash and
# not as a dev build.

import json  # noqa: E402

from labeling_tool.update import version as ver  # noqa: E402


def test_runtime_is_read_from_build_info(tmp_path):
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.3.0", "runtime": "r3f8a1c92",
         "variant": "full", "commit": "abc1234"}), encoding="utf-8")
    info = ver.read_build_info(tmp_path)
    assert info.runtime == "r3f8a1c92"
    assert info.is_release_build


def test_missing_runtime_reads_as_none_but_stays_a_release_build(tmp_path):
    """v1.2.0's build-info.json has no `runtime`. The install is still a
    real release -- it just cannot take a layered update, which the checker
    handles by falling back to the full installer."""
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.2.0", "variant": "full", "commit": "abc1234"}),
        encoding="utf-8")
    info = ver.read_build_info(tmp_path)
    assert info.runtime is None
    assert info.is_release_build


def test_non_string_runtime_reads_as_none(tmp_path):
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.3.0", "runtime": 42, "variant": "full"}), encoding="utf-8")
    assert ver.read_build_info(tmp_path).runtime is None
```

- [ ] **Step 6: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_layers.py -q -p no:cacheprovider -k build_info or runtime_is_read or non_string`
Expected: FAIL，报 `TypeError: BuildInfo.__init__() got an unexpected keyword argument` 或 `AttributeError: 'BuildInfo' object has no attribute 'runtime'`

- [ ] **Step 7: 给 BuildInfo 加 runtime 字段**

`labeling_tool/update/version.py`，`BuildInfo` 定义改为：

```python
@dataclass(frozen=True)
class BuildInfo:
    version: str
    variant: str | None
    commit: str | None
    runtime: str | None = None
```

`read_build_info()` 的返回改为：

```python
    except (OSError, ValueError, KeyError, TypeError):
        return BuildInfo(DEV_VERSION, None, None)
    runtime = data.get("runtime")
    return BuildInfo(version,
                     variant if variant in VARIANTS else None,
                     str(data["commit"]) if data.get("commit") else None,
                     runtime if isinstance(runtime, str) and runtime else None)
```

`is_release_build` 不做改动：`runtime` 为空的 v1.2.0 安装仍是正式版本，只是不能走分层更新。

- [ ] **Step 8: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，415 passed（基线 404 + 本任务 11）

- [ ] **Step 9: 提交**

```bash
git add packaging/layers.py labeling_tool/update/version.py labeling_tool/tests/test_layers.py
git commit -m "$(cat <<'EOF'
feat(update): split the build into app and runtime layers

The runtime id hashes every runtime-layer file, so it moves by itself
whenever torch, the CUDA runtime or PyQt5 change, and nobody has to
remember to bump it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 2: 客户端选包逻辑

**Files:**
- Modify: `labeling_tool/update/checker.py`
- Test: `labeling_tool/tests/test_update_layered.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `BuildInfo.runtime`
- Produces:
  - `checker.app_asset_name(version: str, runtime: str) -> str` → `LM_LabelingTool-App-v{version}-{runtime}.exe`
  - `checker.full_asset_name(version: str) -> str` → `LM_LabelingTool-Setup-v{version}.exe`
  - `checker.UpdateInfo.kind` — `str`，`"app"` 或 `"full"`
  - `checker.find_update(current_version, variant, runtime=None, ...)` — 增加 `runtime` 关键字参数

- [ ] **Step 1: 写失败的测试**

新建 `labeling_tool/tests/test_update_layered.py`：

```python
"""Picking the right installer. The app package's asset name carries the
runtime id, so the client decides by name alone -- no extra metadata file."""

import json

from labeling_tool.update import checker


def _release(tag, assets):
    return json.dumps({"tag_name": tag, "body": "",
                       "assets": [{"name": n, "browser_download_url": f"https://x/{n}",
                                   "size": s} for n, s in assets]})


def _opener(release_json, sums_text):
    class _Resp:
        def __init__(self, text): self._t = text
        def read(self): return self._t.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _open(url, timeout=None):
        return _Resp(sums_text if url.endswith("SHA256SUMS.txt") else release_json)
    return _open


APP = "LM_LabelingTool-App-v1.3.1-r3f8a1c92.exe"
FULL = "LM_LabelingTool-Setup-v1.3.1.exe"
H = "a" * 64


def test_app_package_is_preferred_when_the_runtime_matches():
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {APP}\n{H}  {FULL}\n"
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, sums))
    assert info.kind == "app"
    assert info.asset_name == APP
    assert info.size == 31_000_000


def test_falls_back_to_full_when_the_runtime_changed():
    """torch got upgraded: the release carries an app package built against
    a different runtime, which must not be installed here."""
    other = "LM_LabelingTool-App-v1.3.1-rdeadbeef.exe"
    rel = _release("v1.3.1", [(other, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {other}\n{H}  {FULL}\n"
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, sums))
    assert info.kind == "full"
    assert info.asset_name == FULL


def test_falls_back_to_full_when_the_release_has_no_app_package():
    """The first layered release, and every release that changes the
    runtime, ships only the full installer."""
    rel = _release("v1.3.1", [(FULL, 1_610_000_000), ("SHA256SUMS.txt", 200)])
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"))
    assert info.kind == "full"


def test_no_runtime_on_this_install_goes_straight_to_full():
    """A machine upgrading from v1.2.0 has no runtime id. It must not build
    an asset name containing 'None' and then match nothing."""
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {APP}\n{H}  {FULL}\n"
    info = checker.find_update("1.2.0", "full", runtime=None,
                               opener=_opener(rel, sums))
    assert info.kind == "full"


def test_app_package_without_a_published_checksum_is_refused():
    """Never install an unverifiable download -- fall back to the full
    installer, which does have one."""
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"))
    assert info.kind == "full"


def test_returns_none_when_neither_package_is_usable():
    rel = _release("v1.3.1", [("SHA256SUMS.txt", 200)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, "")) is None


def test_up_to_date_returns_none():
    rel = _release("v1.3.0", [(FULL, 1_610_000_000), ("SHA256SUMS.txt", 200)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n")) is None


def test_asset_name_templates_match_what_ci_builds():
    """These two strings are a contract with packaging/installer.iss's
    OutputBaseFilename. CI asserts the same thing from the other side."""
    assert checker.app_asset_name("1.3.1", "r3f8a1c92") == APP
    assert checker.full_asset_name("1.3.1") == FULL
```

- [ ] **Step 2: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_layered.py -q -p no:cacheprovider`
Expected: FAIL，报 `AttributeError: module 'labeling_tool.update.checker' has no attribute 'app_asset_name'`

- [ ] **Step 3: 改写 checker.py**

把 `asset_name_for()` 替换为两个函数，`UpdateInfo` 增加 `kind`：

```python
APP_PREFIX = "LM_LabelingTool-App"
FULL_PREFIX = "LM_LabelingTool-Setup"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    variant: str
    asset_name: str
    asset_url: str
    size: int
    sha256: str
    notes: str
    kind: str          # "app" (runtime unchanged) or "full" (reinstall)


def app_asset_name(version: str, runtime: str) -> str:
    return f"{APP_PREFIX}-v{version}-{runtime}.exe"


def full_asset_name(version: str) -> str:
    return f"{FULL_PREFIX}-v{version}.exe"
```

`find_update()` 改为：

```python
def find_update(current_version: str, variant: str, repo: str = GITHUB_REPO,
                timeout: float = 10, opener=None,
                runtime: str | None = None) -> UpdateInfo | None:
    """Newest release for this install, or None when up to date.

    Prefers the small app-layer package built against THIS machine's runtime
    id; falls back to the full installer when the runtime changed, when the
    release has no app package, or when this install predates layering and
    has no runtime id at all. An asset without a published checksum is never
    offered -- an unverifiable download is not installed.
    """
    opener = opener or urllib.request.urlopen
    release = json.loads(_read(opener, LATEST_URL.format(repo=repo), timeout))
    tag = str(release.get("tag_name", ""))
    version = tag.lstrip("vV")
    if not is_newer(version, current_version):
        return None
    assets = {a["name"]: a for a in release.get("assets", [])}
    if SUMS_ASSET not in assets:
        return None
    sums = parse_sha256sums(
        _read(opener, assets[SUMS_ASSET]["browser_download_url"], timeout))

    candidates = []
    if runtime:
        candidates.append(("app", app_asset_name(version, runtime)))
    candidates.append(("full", full_asset_name(version)))
    for kind, name in candidates:
        if name in assets and name in sums:
            asset = assets[name]
            return UpdateInfo(version=version, variant=variant, asset_name=name,
                              asset_url=asset["browser_download_url"],
                              size=int(asset.get("size", 0)), sha256=sums[name],
                              notes=str(release.get("body") or ""), kind=kind)
    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_layered.py -q -p no:cacheprovider`
Expected: PASS，8 passed

- [ ] **Step 5: 更新调用方传入 runtime**

`labeling_tool/update/ui.py` 的 `UpdateCheckThread` 需要把 `runtime` 带进去。`__init__` 改为：

```python
    def __init__(self, current_version: str, variant: str,
                 runtime: str | None = None, parent=None):
        super().__init__(parent)
        self._version, self._variant = current_version, variant
        self._runtime = runtime

    def run(self):
        try:
            self.found.emit(checker.find_update(
                self._version, self._variant, timeout=self.CHECK_TIMEOUT,
                runtime=self._runtime))
        except Exception as exc:  # noqa: BLE001 - reporting is the caller's call
            vlog().info("update check failed: %s: %s", type(exc).__name__, exc)
            self.found.emit(exc)
```

`check_for_updates()` 里构建线程的那行改为：

```python
    thread = UpdateCheckThread(info.version, info.variant, info.runtime)
```

- [ ] **Step 6: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，423 passed（415 + 本任务 8）

- [ ] **Step 7: 提交**

```bash
git add labeling_tool/update/checker.py labeling_tool/update/ui.py \
        labeling_tool/tests/test_update_layered.py
git commit -m "$(cat <<'EOF'
feat(update): pick the app package when the runtime id matches

The app package's asset name carries the runtime id, so the client
decides by name alone. A changed runtime, a release without an app
package, and an install predating layering all fall back to the full
installer.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 3: 两种更新的提示文案

**Files:**
- Modify: `docs/i18n-glossary.md`
- Modify: `labeling_tool/core/i18n/strings_{ko,zh,en}.py`
- Modify: `labeling_tool/update/ui.py`
- Test: `labeling_tool/tests/test_update_layered.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `UpdateInfo.kind`
- Produces: 翻译键 `update_prompt_app`、`update_prompt_full`、`update_full_warning`

- [ ] **Step 1: 在 glossary 登记概念**

`docs/i18n-glossary.md` 第 4 节「程序与更新」表格追加一行：

| 概念 | 한국어 | 中文 | English | 说明 |
|---|---|---|---|---|
| full reinstall（完整重装） | **완전 재설치** | 完整重装 | Full reinstall | 运行时层（torch/CUDA）变化时才需要，约 1.5 GB |

- [ ] **Step 2: 写三份文案**

`strings_ko.py` 的 `# --- update dialog ---` 区块追加：

```python
    "update_prompt_app":               "새 버전이 있습니다: v{version}\n다운로드 크기: 약 {size} MB",
    "update_prompt_full":              "새 버전이 있습니다: v{version}\n이번에는 완전 재설치가 필요합니다.",
    "update_full_warning":
        "torch / CUDA 구성이 바뀌어 전체 설치 파일(약 {size} MB)을 내려받습니다.\n"
        "충분한 네트워크와 디스크 공간을 확인하세요.",
```

`strings_zh.py`：

```python
    "update_prompt_app":               "有新版本：v{version}\n下载大小：约 {size} MB",
    "update_prompt_full":              "有新版本：v{version}\n本次需要完整重装。",
    "update_full_warning":
        "torch / CUDA 组成已变更，需下载完整安装包（约 {size} MB）。\n"
        "请确认网络和磁盘空间充足。",
```

`strings_en.py`：

```python
    "update_prompt_app":               "A new version is available: v{version}\nDownload size: about {size} MB",
    "update_prompt_full":              "A new version is available: v{version}\nThis one needs a full reinstall.",
    "update_full_warning":
        "The torch / CUDA layer changed, so the full installer (about {size} MB)\n"
        "will be downloaded. Check your network and free disk space.",
```

- [ ] **Step 3: 写失败的测试**

在 `labeling_tool/tests/test_update_layered.py` 末尾追加：

```python
# ------------------------------------------------------------ the prompt
# An app update and a full reinstall cost the user very different things,
# so they must not read the same.

from labeling_tool.core import i18n  # noqa: E402
from labeling_tool.update import ui as update_ui  # noqa: E402


def _info(kind, size):
    return checker.UpdateInfo(version="1.3.1", variant="full",
                              asset_name="x.exe", asset_url="https://x/x.exe",
                              size=size, sha256=H, notes="", kind=kind)


def test_app_update_text_states_the_small_size():
    text = update_ui.prompt_text(_info("app", 31 * 1024 * 1024))
    assert "v1.3.1" in text
    assert "31" in text
    assert i18n.tr("update_full_warning", size=1536) not in text


def test_full_update_text_warns_about_the_reinstall():
    text = update_ui.prompt_text(_info("full", 1536 * 1024 * 1024))
    assert "v1.3.1" in text
    assert "1536" in text
    # the warning names the reason, so the user knows why this one is huge
    assert i18n.tr("update_full_warning", size=1536).splitlines()[0] in text
```

- [ ] **Step 4: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_update_layered.py -q -p no:cacheprovider -k prompt`
Expected: FAIL，报 `AttributeError: module 'labeling_tool.update.ui' has no attribute 'prompt_text'`

- [ ] **Step 5: 提取 prompt_text 并改写 _ask**

`labeling_tool/update/ui.py`，在 `_ask()` 之前加入：

```python
def prompt_text(info) -> str:
    """The body of the update prompt. Extracted from _ask so it can be
    tested without building a QMessageBox (a modal box under offscreen Qt
    hangs the suite)."""
    size_mb = info.size // (1024 * 1024)
    if info.kind == "app":
        return tr("update_prompt_app", version=info.version, size=size_mb)
    return (tr("update_prompt_full", version=info.version) + "\n\n"
            + tr("update_full_warning", size=size_mb))
```

`_ask()` 中原先构造 `text` 的那几行（从 `size_mb = ...` 到 `box.setText(text)` 之前的 full 变体警告）整段替换为：

```python
    notes = "\n".join(info.notes.splitlines()[:8])
    box = QMessageBox(parent)
    box.setWindowTitle(tr("update_title"))
    box.setIcon(QMessageBox.Information)
    box.setTextFormat(Qt.PlainText)
    box.setText(prompt_text(info))
```

`ui.py` 顶部需要 `from labeling_tool.core.i18n import tr`（若尚未导入）。原先硬编码的韩语按钮与标题文案改为既有的翻译键（`update_title`、`update_btn_now`、`update_btn_later`、`update_btn_skip`）——这些键在 i18n 包中已存在，第一期已统一。

- [ ] **Step 6: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，425 passed（423 + 本任务 2）

- [ ] **Step 7: 提交**

```bash
git add docs/i18n-glossary.md labeling_tool/core/i18n/ labeling_tool/update/ui.py \
        labeling_tool/tests/test_update_layered.py
git commit -m "$(cat <<'EOF'
feat(update): say which kind of update this is

A 30 MB app update and a 1.5 GB reinstall cost the user very different
things; the prompt now names the size and, for a reinstall, the reason.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 4: 改名与图标

**Files:**
- Create: `packaging/icon.svg`
- Create: `packaging/icon.ico`
- Modify: `packaging/labeling_tool.spec`
- Modify: `labeling_tool/ui/login_dialog.py:13`（陈旧 docstring，第一期复审的遗留 Minor）

**Interfaces:**
- Consumes: 无
- Produces: PyInstaller 产物目录名与 exe 名均为 `LM_LabelingTool`，与 Task 1 的 `APP_LAYER_PREFIXES` 一致

- [ ] **Step 1: 画图标源文件**

新建 `packaging/icon.svg`（方案 A 字母标，深底圆角方形 + 蓝描边 + 白色 LM + 蓝色下划线）：

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="2" y="2" width="60" height="60" rx="13" fill="#1b1f25" stroke="#2d6cdf" stroke-width="2"/>
  <text x="32" y="38" text-anchor="middle" font-family="Segoe UI, DejaVu Sans, sans-serif"
        font-size="23" font-weight="700" fill="#e8ecf2" letter-spacing="1">LM</text>
  <rect x="19" y="44" width="26" height="3" rx="1.5" fill="#2d6cdf"/>
</svg>
```

- [ ] **Step 2: 生成多尺寸 ico**

小尺寸需要更粗的字重和更细的下划线，否则 16px 下糊成一团。用 Pillow 从两版 SVG 渲染后合成：

```bash
.venv/bin/python - <<'PY'
import io, subprocess
from PIL import Image

def render(svg: str, px: int) -> Image.Image:
    png = subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px)],
                         input=svg.encode(), capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")

big = open("packaging/icon.svg").read()
# small sizes: heavier stroke, thicker underline, no letter-spacing
small = (big.replace('stroke-width="2"', 'stroke-width="3"')
            .replace('font-size="23"', 'font-size="26"')
            .replace(' letter-spacing="1"', '')
            .replace('y="44" width="26" height="3"', 'y="45" width="28" height="4"'))

imgs = [render(small if px <= 32 else big, px)
        for px in (16, 24, 32, 48, 64, 128, 256)]
imgs[0].save("packaging/icon.ico", format="ICO",
             sizes=[(i.width, i.height) for i in imgs], append_images=imgs[1:])
print("wrote packaging/icon.ico")
PY
```

`rsvg-convert` 来自 `librsvg2-bin`。若环境中没有，用 `inkscape -w <px> -h <px> icon.svg -o out.png` 替代；两者任选其一，产物相同。

- [ ] **Step 3: 验证 ico 的层数与尺寸**

```bash
.venv/bin/python -c "
from PIL import Image
im = Image.open('packaging/icon.ico')
print(sorted(im.info['sizes']))
"
```
Expected: `[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]`

- [ ] **Step 4: 改 spec 的名字、图标并去掉 lite 分支**

`packaging/labeling_tool.spec`：删除 `VARIANT` 读取与 `if VARIANT == "full" / else` 分支，只保留 full 的内容；`EXE(...)` 与 `COLLECT(...)` 的 `name=` 改为 `"LM_LabelingTool"`；`EXE(...)` 增加 `icon=os.path.join(SPECPATH, "icon.ico")`。文件头注释改为：

```python
# PyInstaller spec for LM_LabelingTool (onedir, windowed).
# One variant only: the production tool plus the few-shot annotation tool
# (torch/SAM). The lite variant was dropped in v1.3.0 -- see
# docs/superpowers/specs/2026-09-28-ui-refresh-and-rebrand-design.md 2.1.
# Build from the repo root:  pyinstaller --noconfirm packaging/labeling_tool.spec
```

具体改动：删掉 `VARIANT = os.environ.get(...)` 与其后的校验两行；把 `if VARIANT == "full":` 块内的语句提到顶层（去掉一级缩进）；删掉整个 `else:` 块。

- [ ] **Step 5: 顺手修掉第一期复审的陈旧 docstring**

`labeling_tool/ui/login_dialog.py:13`，把

```
  * MODE_FEWSHOT: no session; app.open_tool_window(mode)
```

改为

```
  * MODE_FEWSHOT: no session; app.open_fewshot_from_login(dialog)
```

- [ ] **Step 6: 收敛 VARIANTS 与自检的变体分支**

`labeling_tool/update/version.py` 的 `VARIANTS = ("lite", "full")` 改为 `VARIANTS = ("full",)`。
没有 lite 安装存在（软件尚未分发），所以没有机器会因此失去更新能力。

`labeling_tool/selftest.py` 删除 lite 专属检查：`_checks()` 中 `if variant == "lite":` 分支整段
删除（该分支断言 torch 不出现在构建里，lite 构建不再存在，这条检查永远不会执行），
`run_selftest()` 的 `if variant not in ("lite", "full"):` 改为 `if variant != "full":`，
其错误文案 `(use lite or full)` 改为 `(use full)`。模块首行 docstring
`` `LabelingTool.exe --selftest=lite|full` `` 改为 `` `LM_LabelingTool.exe --selftest=full` ``。

既有的 `labeling_tool/tests/` 中若有断言 lite 自检行为的用例，一并删除；用
`grep -rn "selftest" labeling_tool/tests/ tests/` 找出来逐个处理。

- [ ] **Step 7: 验证 spec 语法与变体收敛**

```bash
.venv/bin/python -c "
import ast, pathlib
src = pathlib.Path('packaging/labeling_tool.spec').read_text()
ast.parse(src)
assert 'LM_LabelingTool' in src
assert 'icon.ico' in src
assert 'LT_VARIANT' not in src
print('spec ok')
"
.venv/bin/python -c "
from labeling_tool.update.version import VARIANTS
assert VARIANTS == ('full',), VARIANTS
import labeling_tool.selftest as st
assert st.run_selftest('lite') == 2, 'lite must now be an unknown variant'
print('variant collapse ok')
"
```
Expected: `spec ok`

- [ ] **Step 8: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，425 passed（本任务不新增测试；spec 与 ico 由 CI 构建验证）

- [ ] **Step 9: 提交**

```bash
git add packaging/icon.svg packaging/icon.ico packaging/labeling_tool.spec \
        labeling_tool/ui/login_dialog.py labeling_tool/update/version.py \
        labeling_tool/selftest.py labeling_tool/tests/
git commit -m "$(cat <<'EOF'
feat(packaging): rename to LM_LabelingTool, add an icon, drop lite

The icon is one letter mark at every size: the four-corner variant read
as noise at 16px in the taskbar. Small layers get a heavier weight so
they stay legible.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 5: 双层安装器

**Files:**
- Modify: `packaging/installer.iss`

**Interfaces:**
- Consumes: Task 1 的分层规则（CI 按其生成 `app` 层的源目录）、Task 2 的资产名模板
- Produces: `/DMyLayer=full` 与 `/DMyLayer=app` 两种编译模式；`OutputBaseFilename` 与 `checker.py` 的模板一致

**这个任务本地无法验证**，Inno Setup 只在 Windows 上跑。每步的验证靠 Task 6 接上 CI 之后的构建结果。本任务的提交完成后不要宣称"已验证"，只能说"已实现，待 CI 验证"。

- [ ] **Step 1: 改 Setup 段为单变体双层**

`packaging/installer.iss` 的 `[Setup]` 段，把 `#if MyVariant == "full" / #else / #endif` 整段替换为：

```pascal
#ifndef MyLayer
  #define MyLayer "full"
#endif

AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}
#define MyAppName "LM_LabelingTool"
DefaultDirName={autopf}\LM_LabelingTool
DefaultGroupName=LM_LabelingTool
```

`AppId` 沿用 full 变体原值，使用户现有的 full 安装被识别为升级，配置与数据原地保留。

`OutputBaseFilename` 按层区分（必须与 `checker.py` 的两个模板逐字一致）：

```pascal
#if MyLayer == "app"
OutputBaseFilename=LM_LabelingTool-App-v{#MyVersion}-{#MyRuntime}
#else
OutputBaseFilename=LM_LabelingTool-Setup-v{#MyVersion}
#endif
```

`UninstallDisplayIcon` 改为 `{app}\LM_LabelingTool.exe`，并增加 `SetupIconFile={#MySourceRoot}\packaging\icon.ico`（`MySourceRoot` 由 CI 传入仓库根路径）。

- [ ] **Step 2: 按层区分 InstallDelete —— 本期最危险的一处**

现有的

```pascal
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
```

会在安装前删掉整个 `_internal`。应用包若照搬，会先删掉 1.4 GB 运行时层再只装回应用层，程序直接起不来。改为：

```pascal
[InstallDelete]
; The full installer replaces everything, so it clears _internal wholesale --
; ignoreversion never removes files a newer build dropped, and without this
; upgrades would accumulate stale content forever.
; The app package must NOT do that: _internal holds the 1.4 GB runtime layer
; it does not ship. It clears only the two directories it actually replaces.
#if MyLayer == "app"
Type: filesandordirs; Name: "{app}\_internal\labeling_tool"
Type: filesandordirs; Name: "{app}\_internal\annotation_tool"
#else
Type: filesandordirs; Name: "{app}\_internal"
#endif
```

- [ ] **Step 3: 应用包安装前校验 runtime**

`[Code]` 段增加，放在既有的 `WantsRestart` 之前：

```pascal
#if MyLayer == "app"
function InitializeSetup(): Boolean;
var
  Info: AnsiString;
begin
  Result := True;
  // Normal path: the client only ever downloads an app package whose asset
  // name carries this machine's runtime id, so this cannot fail. This
  // guards the user who downloaded the wrong file by hand.
  if LoadStringFromFile(ExpandConstant('{autopf}\LM_LabelingTool\build-info.json'), Info) then
  begin
    if Pos('"{#MyRuntime}"', String(Info)) = 0 then
    begin
      MsgBox('이 업데이트는 현재 설치된 버전과 맞지 않습니다.' + #13#10 +
             '전체 설치 파일을 내려받아 주세요.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
#endif
```

安装目录里没有 `build-info.json` 时（全新机器上手动跑了应用包）放行 —— 此时没有可比对的基准，交给完整包的正常安装流程处理更合适，强行拒绝反而会挡住合法的修复性重装。

- [ ] **Step 4: 改 Icons、Run 段的 exe 名**

`[Icons]` 与 `[Run]` 段中所有 `{app}\LabelingTool.exe` 改为 `{app}\LM_LabelingTool.exe`；`[Run]` 的 `Description` 文案改为 `"LM_LabelingTool 실행"`。

- [ ] **Step 5: 校验 iss 与 checker 的资产名模板一致**

```bash
.venv/bin/python - <<'PY'
import pathlib, re
from labeling_tool.update import checker
iss = pathlib.Path("packaging/installer.iss").read_text(encoding="utf-8")
app = re.search(r"OutputBaseFilename=(LM_LabelingTool-App-v\S+)", iss).group(1)
full = re.search(r"OutputBaseFilename=(LM_LabelingTool-Setup-v\S+)", iss).group(1)
# substitute Inno's preprocessor vars the way CI does
got_app = app.replace("{#MyVersion}", "1.3.1").replace("{#MyRuntime}", "r3f8a1c92") + ".exe"
got_full = full.replace("{#MyVersion}", "1.3.1") + ".exe"
assert got_app == checker.app_asset_name("1.3.1", "r3f8a1c92"), got_app
assert got_full == checker.full_asset_name("1.3.1"), got_full
print("asset name templates agree")
PY
```
Expected: `asset name templates agree`

- [ ] **Step 6: 提交**

```bash
git add packaging/installer.iss
git commit -m "$(cat <<'EOF'
feat(packaging): build a full and an app-layer installer from one script

The app package clears only the two directories it replaces. Clearing
_internal wholesale, as the full installer does, would delete the 1.4 GB
runtime layer it does not ship and leave the program unable to start.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 6: CI 集成与端到端验证

**Files:**
- Modify: `.github/workflows/build-windows.yml`

**Interfaces:**
- Consumes: Task 1 的 `packaging/layers.py`、Task 4 的 spec、Task 5 的双层 iss
- Produces: release 资产 `LM_LabelingTool-Setup-v{版本}.exe`、`LM_LabelingTool-App-v{版本}-{runtime}.exe`、`SHA256SUMS.txt`

- [ ] **Step 1: 收敛为单变体构建**

把 `strategy.matrix.variant: [lite, full]` 整段删除，job 不再有 matrix；所有 `$env:LT_VARIANT` 引用改为字面量 `full`；`dist\LabelingTool` 全部改为 `dist\LM_LabelingTool`；`LabelingTool.exe` 改为 `LM_LabelingTool.exe`。测试步骤中 `if ($env:LT_VARIANT -eq 'full') { $suites += "annotation_tool/tests" }` 的条件删除，直接包含该测试目录。

- [ ] **Step 2: 构建后计算 runtime 并写 build-info.json**

在构建步骤之后、打包安装器之前插入：

```yaml
      - name: Compute the runtime id and write build-info.json
        run: |
          $ver = $env:LT_VERSION -replace '^v', ''
          $rt = python -c "import sys; sys.path.insert(0, 'packaging'); import layers; print(layers.compute_runtime_id('dist/LM_LabelingTool'))"
          if (-not ($rt -match '^r[0-9a-f]{8}$')) { throw "bad runtime id: $rt" }
          "LT_RUNTIME=$rt" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
          $info = @{ version = $ver; variant = 'full'; runtime = $rt; commit = $env:GITHUB_SHA.Substring(0,7) }
          $info | ConvertTo-Json -Compress | Set-Content -Path dist\LM_LabelingTool\build-info.json -Encoding utf8
          Get-Content dist\LM_LabelingTool\build-info.json
```

注意顺序：`build-info.json` 本身属于应用层（它在产物根目录，不在 `APP_LAYER_PREFIXES` 里 —— 见 Step 3 的处理），必须在 `compute_runtime_id` **之后**写入，否则它会参与运行时哈希，导致每次版本号变化都改变 runtime id。

- [ ] **Step 3: 把 build-info.json 纳入应用层**

`packaging/layers.py` 的 `APP_LAYER_PREFIXES` 增加一项：

```python
APP_LAYER_PREFIXES = (
    "LM_LabelingTool.exe",
    "build-info.json",
    "_internal/labeling_tool/",
    "_internal/annotation_tool/",
)
```

并在 `labeling_tool/tests/test_layers.py` 追加：

```python
def test_build_info_is_app_layer_so_a_version_bump_keeps_the_runtime_id():
    """build-info.json carries the version, so if it counted as runtime the
    id would change on every release and layering would never engage."""
    assert layers.is_app_layer("build-info.json")
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_layers.py -q -p no:cacheprovider`
Expected: PASS，12 passed

- [ ] **Step 4: 生成两个安装器**

原先单次调用 ISCC 的步骤替换为：

```yaml
      - name: Stage the app layer
        run: |
          python - <<'PY'
          import shutil, sys
          from pathlib import Path
          sys.path.insert(0, "packaging")
          import layers
          src, dst = Path("dist/LM_LabelingTool"), Path("dist/app-layer")
          for p in src.rglob("*"):
              if not p.is_file():
                  continue
              rel = p.relative_to(src).as_posix()
              if layers.is_app_layer(rel):
                  out = dst / rel
                  out.parent.mkdir(parents=True, exist_ok=True)
                  shutil.copy2(p, out)
          total = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
          print(f"app layer: {total/1024/1024:.1f} MB")
          PY

      - name: Build both installers
        run: |
          $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
          $ver = $env:LT_VERSION -replace '^v', ''
          & $iscc /DMyLayer=full /DMyVersion=$ver "/DMyVersionInfo=$infoVer" `
            "/DMySource=$PWD\dist\LM_LabelingTool" "/DMySourceRoot=$PWD" `
            "/DMyRuntime=$env:LT_RUNTIME" "/DMyOutDir=$PWD\out" packaging\installer.iss
          if ($LASTEXITCODE -ne 0) { throw "full installer failed" }
          & $iscc /DMyLayer=app /DMyVersion=$ver "/DMyVersionInfo=$infoVer" `
            "/DMySource=$PWD\dist\app-layer" "/DMySourceRoot=$PWD" `
            "/DMyRuntime=$env:LT_RUNTIME" "/DMyOutDir=$PWD\out" packaging\installer.iss
          if ($LASTEXITCODE -ne 0) { throw "app installer failed" }
          Get-ChildItem out\*.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.Name, ($_.Length/1MB) }
```

`$infoVer` 沿用既有步骤计算出的数值版本。

- [ ] **Step 5: 断言资产名与客户端模板一致**

在打包之后加入：

```yaml
      - name: Assert the asset names match what the client looks for
        run: |
          $ver = $env:LT_VERSION -replace '^v', ''
          python - $ver $env:LT_RUNTIME <<'PY'
          import sys
          from labeling_tool.update import checker
          ver, rt = sys.argv[1], sys.argv[2]
          import pathlib
          names = {p.name for p in pathlib.Path("out").glob("*.exe")}
          for want in (checker.full_asset_name(ver), checker.app_asset_name(ver, rt)):
              assert want in names, f"{want!r} not in {sorted(names)}"
          print("asset names agree with checker.py")
          PY
```

这条守的是第一期复审点出过的契约漂移：`installer.iss` 的 `OutputBaseFilename` 和 `checker.py` 的模板是一份隐式合同，改了一边忘了另一边，客户端会静默地永远收不到更新。

- [ ] **Step 6: 扩展安装—自检—卸载为双层流程**

原先的安装自检步骤替换为：

```yaml
      - name: Install full, self-test, install app layer, self-test, uninstall
        run: |
          $target = "$env:LOCALAPPDATA\Programs\LM_LabelingTool"
          $full = Get-ChildItem out\LM_LabelingTool-Setup-*.exe | Select-Object -First 1
          Start-Process -FilePath $full.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
          if (-not (Test-Path "$target\LM_LabelingTool.exe")) { throw "full install produced no exe" }
          $s = Start-Process -FilePath "$target\LM_LabelingTool.exe" -ArgumentList "--selftest=full" -Wait -PassThru
          if ($s.ExitCode -ne 0) { throw "selftest after full install failed: $($s.ExitCode)" }

          $before = (Get-ChildItem "$target\_internal" -Recurse -File | Measure-Object -Property Length -Sum).Sum
          $app = Get-ChildItem out\LM_LabelingTool-App-*.exe | Select-Object -First 1
          Start-Process -FilePath $app.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
          $after = (Get-ChildItem "$target\_internal" -Recurse -File | Measure-Object -Property Length -Sum).Sum
          # the app package must not take the runtime layer with it
          if ($after -lt $before * 0.9) { throw "app install shrank _internal from $before to $after -- the runtime layer was deleted" }
          $s = Start-Process -FilePath "$target\LM_LabelingTool.exe" -ArgumentList "--selftest=full" -Wait -PassThru
          if ($s.ExitCode -ne 0) { throw "selftest after app-layer install failed: $($s.ExitCode)" }

          $unins = Get-ChildItem "$target\unins*.exe" | Select-Object -First 1
          Start-Process -FilePath $unins.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
          Start-Sleep -Seconds 5
          if (Test-Path "$target\_internal") {
            $left = (Get-ChildItem "$target\_internal" -Recurse -File | Measure-Object -Property Length -Sum).Sum
            throw "uninstall left $left bytes under _internal"
          }
```

这一步同时覆盖了 Review Focus 里最危险的两条：应用包是否误删运行时层（装完 `_internal` 体积不得缩水），以及卸载是否残留（`_internal` 必须消失）。

- [ ] **Step 7: 收敛 release 步骤**

`Assemble release assets` 步骤中 `cat out/SHA256SUMS-*.txt > out/SHA256SUMS.txt` 保留（现在只有一个变体的分片），确认 `rm -f out/*.zip out/*.7z*` 仍会清掉打包用的压缩包。校验和生成步骤要覆盖两个安装器：

```yaml
          Get-ChildItem out\*.exe | ForEach-Object {
            $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
            "$h  $($_.Name)" | Add-Content -Path "out\SHA256SUMS-full.txt" -Encoding ascii
          }
```

- [ ] **Step 8: 推分支触发 CI 并读结果**

```bash
git add .github/workflows/build-windows.yml packaging/layers.py labeling_tool/tests/test_layers.py
git commit -m "$(cat <<'EOF'
ci: build one variant in two layers and verify both installers

Installs the full package, self-tests, installs the app package on top,
asserts _internal did not shrink, self-tests again, uninstalls and
asserts nothing is left behind.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
git push -u origin feat/rebrand-and-layered-update
gh run watch $(gh run list --branch feat/rebrand-and-layered-update --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: run 成功。读构建日志中 `app layer: N MB` 的输出，确认应用层实际体积（设计预期 20-30 MB）。若超过 100 MB，说明 PYZ 里混入了预期外的内容，在 ledger 中记录并告知用户，再决定是否改用 `noarchive=True` 让 .pyc 散落以精确分层。

- [ ] **Step 9: 验证 runtime id 的可重现性**

CI 成功后，不改任何代码重新触发一次构建（`gh workflow run build-windows.yml --ref feat/rebrand-and-layered-update`），比对两次日志里的 runtime id。

Expected: 两次一致。若不一致，说明 PyInstaller 产物不可重现（时间戳或路径被写进了运行时层文件），分层更新会退化为每次都要完整重装。此时按 spec 第 9 节的对策，把 `compute_runtime_id` 改为对依赖清单取哈希：

```python
def compute_runtime_id(dist_dir: Path) -> str:
    """Hash the dependency manifests instead of the built files.

    Fallback for a non-reproducible PyInstaller build: less precise (a
    dependency that changes without its pin changing will not move the id)
    but stable across builds."""
    digest = hashlib.sha256()
    for name in ("requirements.txt", "packaging/build-constraints.txt"):
        digest.update(Path(name).read_bytes())
    digest.update(b"torch==2.5.1+cu124;torchvision==0.20.1")
    return "r" + digest.hexdigest()[:8]
```

并同步调整 Task 1 中依赖产物内容的那几个测试。

- [ ] **Step 10: 更新文档中的版本与体积数字**

把 Step 8 读到的应用层实际体积写回 `docs/superpowers/specs/2026-09-28-layered-distribution-design.md` 第 1 节的表格与第 2 节，替换"预期几 MB / 约 30 MB"的估算值。

```bash
git add docs/superpowers/specs/2026-09-28-layered-distribution-design.md
git commit -m "$(cat <<'EOF'
docs(design): record the measured app-layer size

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

## 完成标准

- 全量测试 425 通过（基线 404 + 本期 21）
- CI 的 build job 成功，产出三个 release 资产：完整包、应用包、`SHA256SUMS.txt`
- CI 的双层验证通过：装完整包 → 自检 → 装应用包（`_internal` 未缩水）→ 自检 → 卸载（`_internal` 清空）
- 资产名断言通过，`installer.iss` 与 `checker.py` 的模板一致
- runtime id 在两次构建间可重现（或已按回退方案改为依赖清单哈希，并在 ledger 记录）
- 应用层实际体积已实测并写回设计文档

## 发布与人工验证

本期完成后发布 v1.3.0。用户需要**手动下载完整包安装一次**（改名导致资产名变化，v1.2.0 的客户端匹配不到）。安装时 `AppId` 未变，Inno 会识别为升级，`config.json`、`data\`、`checkpoint\` 原地保留。

安装后请用户确认：

- 开始菜单、任务栏、标题栏显示 `LM_LabelingTool`，图标是蓝底 LM 字母标，16px 下清晰
- 登录界面底部的版本标识显示 `1.3.0`
- 旧的 `LabelingTool` 条目已消失，控制面板中没有重复程序
- `config.json` 与已下载的作业数据仍在

下一个版本（v1.4.0，标注窗口方向 B）发布后，该机器应当收到**约 30 MB**的应用层更新提示，而不是 1.5 GB —— 那次才是分层分发真正的验收。
