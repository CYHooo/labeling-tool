# 用户追加类别（SAM · 画笔）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在标注窗口里手动追加损伤类别（编号由服务器 V5/V6 分配），SAM 和画笔都写入「当前类别」，新类别随掩码上传并带 `classAreas`；同时按 S 保存时自动确认未确认的编辑。

**Architecture:** 新模块 `labeling_tool/core/classes.py` 保存类别表（内置 1 균열 / 2 박리 + 服务器类别，按服务器缓存）；掩码在内存里从「两层」改为「类别编号 → 0/255 图层」字典，编解码、派生掩码、结果导出、上传统计都改为按字典处理，旧的两层函数保留为薄封装以免一次改动所有调用方；界面用一个 `ClassPicker`（下拉框 + 「+」）替换 균열 / 박리 两个按钮，브러시 和 SAM 页各放一个实例。

**Tech Stack:** Python 3.12, PyQt5, numpy, OpenCV, requests, pytest（offscreen Qt）。

**Spec:** `docs/superpowers/specs/2026-10-13-user-classes-design.md`；服务器提案 `docs/superpowers/specs/2026-10-13-api-v1.0.16-classes-proposal.ko.md`。

## Global Constraints

- 测试命令（每个任务结束都跑，必须全绿）：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`（开始时 933 passed）。
- 类别编号：1 = 균열（`line`），2 = 박리（`area`），用户类别 3～254（`area`），255 不用作类别。
- 一个像素一个类别：균열 最优先；面状类别之间后画的优先。
- 旧掩码（0/1/2 单通道、旧 3 通道 RGB、旧 0/255 二值）读取结果不变。
- 只用 균열 / 박리 时，上传的 V4 item 与现在完全相同（不出现 `classAreas` 键）。
- 侧边栏最小宽度 340 px；900 px 高窗口里任何工具、ko / zh / en 都不出现滚动条。缩短文字，不加宽面板。
- 所有用户可见文字走 i18n（`labeling_tool/core/i18n/strings_{ko,zh,en}.py`），先改 `docs/i18n-glossary.md`。韩语是正式界面语言。新类别名称原样显示，不翻译。
- 代码注释用英文，命名 snake_case（Python）；4 空格缩进。
- 测试不得在仓库里写文件：类别缓存目录在测试里一律重定向到 `tmp_path`（Task 1 加 autouse fixture）。
- **不要** `from packaging import X`（仓库里的 `packaging/` 目录会遮住 pip 的同名库）。
- Commit：conventional commits，正文说明原因，末尾加 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`。分支 `feat/user-classes`（已存在，设计文档已提交）。

## Review Focus

1. **复원 之后撤销**：用户在新类别上画了，再点「복원」（重新加载、新层消失），再 Ctrl+Z —— 新类别的像素必须回来（Task 6 测试 `test_undo_after_reset_brings_a_user_class_back`）。
2. **未知编号**：掩码里有本机类别表没有的编号（别人刚追加）——显示为灰色、保存后像素原样保留、上传时不写进 `classAreas`（Task 3、5、7 测试）。
3. **服务器没有 V5（404）/ 离线**：界面只有 균열 / 박리，「+」禁用并有提示，其余功能照常（Task 2、9 测试）。
4. **SAM 下选到 균열**：通过数字键 1 或进入 SAM 时当前是 균열 —— SAM 确认绝不能写进 균열 层（Task 6、8 测试）。
5. **面状互斥**：在 백태 上画 박리，保存再读回，该区域只剩 박리；균열 线不受影响（Task 6 测试）。

---

## File Structure

| 文件 | 职责 | 任务 |
|---|---|---|
| `labeling_tool/core/classes.py`（新） | `LabelClass`、`ClassRegistry`、缓存读写、颜色挑选 | 1 |
| `labeling_tool/api/client.py` | `list_classes()`、`add_class()` | 2 |
| `labeling_tool/api/class_sync.py`（新） | `sync_classes()`、`add_class_and_cache()`：网络 + 缓存 + 404/离线 | 2 |
| `labeling_tool/core/mask_codec.py` | `encode_layers()`、`decode_layers()`；旧函数变封装 | 3 |
| `labeling_tool/core/mask_io.py` | `load_origin_and_layers()` | 3 |
| `labeling_tool/core/derived_masks.py` | 按字典生成 하이라이트 / 15cm 경계 | 4 |
| `labeling_tool/ui/derived_mask_worker.py` | worker 接收字典 | 4 |
| `labeling_tool/core/result/*.py` | 结果图、结果文本按类别 | 5 |
| `labeling_tool/annotation_payload.py` | `classAreas` | 5 |
| `labeling_tool/ui/upload_worker.py` | 解码字典、上传前同步、未知编号 | 5 |
| `labeling_tool/core/canvas/image_canvas.py` | `layers` 字典、`current_class_id`、互斥、SAM 写当前类别、颜色 | 6 |
| `labeling_tool/core/canvas/overlay_painter.py` | `paint_layer_overlays()`、halo 多层 | 6 |
| `labeling_tool/core/window/main_window.py` | 读写管线改字典、类别表、选择类别、自动确认 | 7、8、10 |
| `labeling_tool/ui/main_window.py` | 打开时同步、上传前带类别表、追加类别 | 7、9 |
| `labeling_tool/core/window/class_picker.py`（新） | 下拉框 + 「+」组件 | 8 |
| `labeling_tool/core/window/ui_builder.py`、`shortcuts.py`、`styles.py` | 替换类别按钮、数字键 1～9 | 8 |
| `labeling_tool/ui/add_class_dialog.py`（新） | 追加对话框 | 9 |
| i18n 三个文件、`docs/i18n-glossary.md` | 文案 | 8、9、11 |

---

### Task 1: 类别表模块 `core/classes.py`

**Files:**
- Create: `labeling_tool/core/classes.py`
- Create: `labeling_tool/tests/test_classes.py`
- Modify: `labeling_tool/tests/conftest.py`（autouse 重定向缓存目录）
- Modify: `.gitignore`（源码运行时的缓存目录）

**Interfaces:**
- Produces:
  - 常量 `CRACK_ID = 1`、`SPALLING_ID = 2`、`MAX_CLASS_ID = 254`、`UNKNOWN_RGB = (150, 150, 150)`
  - `@dataclass(frozen=True) LabelClass(class_id: int, name: str, kind: str, color: str, builtin: bool = False)`，属性 `rgb -> tuple[int, int, int]`
  - `ClassRegistry(extra: Iterable[LabelClass] = ())`：`classes() -> list[LabelClass]`（按 id 升序）、`user_classes()`、`get(cid) -> LabelClass | None`、`__contains__(cid)`、`ids() -> list[int]`、`rgb(cid)`、`is_area(cid) -> bool`、`display_name(cid, tr) -> str`、`with_class(c) -> ClassRegistry`、`to_payload() -> dict`
  - `parse_class(d: dict) -> LabelClass`（不合法抛 `ValueError`）、`parse_classes(payload: dict) -> ClassRegistry`
  - `cache_dir() -> Path`、`cache_file(base_url, root=None) -> Path`、`load_cached(base_url, root=None) -> ClassRegistry`、`save_cached(base_url, registry, root=None) -> None`
  - `pick_color(registry) -> str`

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_classes.py`

```python
import json

import pytest

from labeling_tool.core import classes as C


def _user(cid, name="백태", color="#3C8CFF"):
    return C.LabelClass(cid, name, "area", color)


def test_builtins_are_always_there_in_id_order():
    reg = C.ClassRegistry([_user(4, "누수"), _user(3)])
    assert reg.ids() == [1, 2, 3, 4]
    assert reg.get(1).kind == "line" and reg.get(2).kind == "area"
    assert reg.get(1).builtin and not reg.get(3).builtin


def test_a_server_entry_cannot_replace_a_builtin():
    reg = C.ClassRegistry([C.LabelClass(1, "hack", "area", "#000000")])
    assert reg.get(1).name == "crack" and reg.get(1).kind == "line"


def test_ids_outside_3_to_254_are_ignored():
    reg = C.ClassRegistry([_user(0), _user(255), _user(300), _user(3)])
    assert reg.ids() == [1, 2, 3]


def test_display_names():
    tr = {"cat_crack": "균열", "cat_spalling": "박리"}
    reg = C.ClassRegistry([_user(3, "백태")])

    def fake_tr(key, **kw):
        return tr.get(key, f"{key}:{kw}")
    assert reg.display_name(1, fake_tr) == "균열"
    assert reg.display_name(2, fake_tr) == "박리"
    assert reg.display_name(3, fake_tr) == "백태"
    assert reg.display_name(7, fake_tr) == "class_unknown:{'id': 7}"


def test_colours_and_kinds_for_unknown_ids():
    reg = C.ClassRegistry()
    assert reg.rgb(1) == (255, 60, 60)
    assert reg.rgb(9) == C.UNKNOWN_RGB
    assert reg.is_area(2) and not reg.is_area(1)
    assert reg.is_area(9)                       # unknown pixels behave like an area


def test_parse_classes_skips_bad_entries():
    reg = C.parse_classes({"classes": [
        {"classId": 1, "name": "crack", "kind": "line", "color": "#FF3C3C", "builtin": True},
        {"classId": 3, "name": " 백태 ", "kind": "area", "color": "#3c8cff"},
        {"classId": "x", "name": "bad"},
        {"classId": 4, "name": "", "kind": "area", "color": "#123456"},
        {"classId": 5, "name": "누수", "kind": "area", "color": "red"},
    ]})
    assert reg.ids() == [1, 2, 3, 5]
    assert reg.get(3).name == "백태" and reg.get(3).color == "#3C8CFF"
    assert reg.get(5).color.startswith("#") and len(reg.get(5).color) == 7


def test_cache_round_trip_is_per_server(tmp_path):
    reg = C.ClassRegistry([_user(3)])
    C.save_cached("https://a.example.com", reg, root=tmp_path)
    assert C.load_cached("https://a.example.com/", root=tmp_path).ids() == [1, 2, 3]
    assert C.load_cached("https://b.example.com", root=tmp_path).ids() == [1, 2]


def test_a_broken_cache_gives_the_builtins(tmp_path):
    path = C.cache_file("https://a.example.com", root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert C.load_cached("https://a.example.com", root=tmp_path).ids() == [1, 2]
    assert path.read_text(encoding="utf-8") == "{not json"   # left alone


def test_pick_color_avoids_colours_in_use():
    reg = C.ClassRegistry([_user(3, color=C.PALETTE[0])])
    assert C.pick_color(reg) == C.PALETTE[1]
    many = C.ClassRegistry([_user(3 + i, f"c{i}", c) for i, c in enumerate(C.PALETTE)])
    extra = C.pick_color(many)
    assert extra not in C.PALETTE and extra.startswith("#") and len(extra) == 7


def test_with_class_returns_a_new_registry():
    reg = C.ClassRegistry()
    reg2 = reg.with_class(_user(3))
    assert reg.ids() == [1, 2] and reg2.ids() == [1, 2, 3]


def test_tests_never_write_the_cache_into_the_repo():
    from labeling_tool.core.app_paths import REPO_ROOT
    assert REPO_ROOT not in C.cache_dir().parents
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_classes.py -q -p no:cacheprovider`
Expected: FAIL（`ModuleNotFoundError: labeling_tool.core.classes`）

- [ ] **Step 3: 实现** `labeling_tool/core/classes.py`

```python
"""Damage classes of the label mask.

Pixel value = class id: 1 crack (a line), 2 spalling (an area), and classes
users add through the server (API v1.0.16 V5 / V6), ids 3..254, always areas.
The server owns the numbering so every PC means the same thing by a value;
this module keeps a per-server cache so the tool works offline.
"""

from __future__ import annotations

import colorsys
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from labeling_tool.core.app_paths import user_data_home

CRACK_ID = 1
SPALLING_ID = 2
MAX_CLASS_ID = 254          # 255 stays free: it marks legacy 0/255 binary masks
UNKNOWN_RGB = (150, 150, 150)
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Distinct from crack red, spalling green and the unknown grey.
PALETTE = ("#3C8CFF", "#FFAA00", "#B05CFF", "#00C8C8", "#FF5CC8",
           "#8C6E3C", "#C8C83C", "#5C5CFF", "#FF7F50", "#2E8B57")


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    s = color.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


@dataclass(frozen=True)
class LabelClass:
    class_id: int
    name: str
    kind: str                 # "line" | "area"
    color: str                # "#RRGGBB"
    builtin: bool = False

    @property
    def rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.color)


BUILTIN_CLASSES = (
    LabelClass(CRACK_ID, "crack", "line", "#FF3C3C", True),
    LabelClass(SPALLING_ID, "spalling", "area", "#3CE63C", True),
)
_BUILTIN_I18N = {CRACK_ID: "cat_crack", SPALLING_ID: "cat_spalling"}


class ClassRegistry:
    """The built-in classes plus the server's user classes, by id."""

    def __init__(self, extra: Iterable[LabelClass] = ()):
        by_id = {c.class_id: c for c in BUILTIN_CLASSES}
        for c in extra:
            if c.class_id in (CRACK_ID, SPALLING_ID):
                continue                       # built-ins are fixed
            if 3 <= c.class_id <= MAX_CLASS_ID:
                by_id[c.class_id] = c
        self._by_id = dict(sorted(by_id.items()))

    def classes(self) -> list[LabelClass]:
        return list(self._by_id.values())

    def user_classes(self) -> list[LabelClass]:
        return [c for c in self._by_id.values() if not c.builtin]

    def ids(self) -> list[int]:
        return list(self._by_id)

    def get(self, cid: int) -> LabelClass | None:
        return self._by_id.get(int(cid))

    def __contains__(self, cid) -> bool:
        return int(cid) in self._by_id

    def rgb(self, cid: int) -> tuple[int, int, int]:
        c = self.get(cid)
        return c.rgb if c is not None else UNKNOWN_RGB

    def is_area(self, cid: int) -> bool:
        """Unknown ids (added elsewhere, not synced yet) count as areas."""
        c = self.get(cid)
        return c is None or c.kind == "area"

    def display_name(self, cid: int, tr: Callable[..., str]) -> str:
        if int(cid) in _BUILTIN_I18N:
            return tr(_BUILTIN_I18N[int(cid)])
        c = self.get(cid)
        return c.name if c is not None else tr("class_unknown", id=int(cid))

    def with_class(self, c: LabelClass) -> "ClassRegistry":
        return ClassRegistry([*self.user_classes(), c])

    def to_payload(self) -> dict:
        """Same shape as the V5 response (built-ins included)."""
        return {"classes": [
            {"classId": c.class_id, "name": c.name, "kind": c.kind,
             "color": c.color, "builtin": c.builtin}
            for c in self.classes()]}


def parse_class(d: dict) -> LabelClass:
    """One V5 / V6 class entry; ValueError when it cannot be used."""
    cid = d.get("classId")
    if not isinstance(cid, int) or isinstance(cid, bool):
        raise ValueError(f"bad classId: {cid!r}")
    name = str(d.get("name") or "").strip()
    if not name:
        raise ValueError(f"class {cid} has no name")
    kind = d.get("kind") if d.get("kind") in ("line", "area") else "area"
    color = d.get("color") or ""
    if not _HEX.match(color):
        color = PALETTE[cid % len(PALETTE)]
    return LabelClass(cid, name, kind, color.upper(), bool(d.get("builtin")))


def parse_classes(payload: dict) -> ClassRegistry:
    """A V5 response (or our cache, same shape); bad entries are skipped."""
    out = []
    for d in (payload or {}).get("classes") or []:
        try:
            out.append(parse_class(d))
        except (ValueError, TypeError, AttributeError):
            from labeling_tool.logging_setup import vlog
            vlog().warning("skipping class entry %r", d)
    return ClassRegistry(out)


def cache_dir() -> Path:
    return user_data_home() / "label-classes"


def cache_file(base_url: str, root: Path | None = None) -> Path:
    parsed = urlparse(base_url.strip())
    host = parsed.netloc or parsed.path or "default"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", host.rstrip("/"))
    return Path(root or cache_dir()) / f"{safe}.json"


def load_cached(base_url: str, root: Path | None = None) -> ClassRegistry:
    try:
        text = cache_file(base_url, root).read_text(encoding="utf-8")
        return parse_classes(json.loads(text))
    except (OSError, ValueError):
        return ClassRegistry()


def save_cached(base_url: str, registry: ClassRegistry,
                root: Path | None = None) -> None:
    path = cache_file(base_url, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(registry.to_payload(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def pick_color(registry: ClassRegistry) -> str:
    """The first palette colour not in use; then evenly spread hues."""
    used = {c.color.upper() for c in registry.classes()}
    for color in PALETTE:
        if color.upper() not in used:
            return color
    n = len(used)
    while True:
        h = (n * 0.618033988749895) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.65, 0.95)
        color = "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))
        if color not in used and color not in PALETTE:
            return color
        n += 1
```

- [ ] **Step 4: 测试里重定向缓存目录**：在 `labeling_tool/tests/conftest.py` 末尾追加

```python
@pytest.fixture(autouse=True)
def _class_cache_in_tmp(tmp_path, monkeypatch):
    """The class cache lives under user_data_home(), which is the repo root
    in a source checkout: keep every test's cache in its own tmp dir."""
    from labeling_tool.core import classes
    monkeypatch.setattr(classes, "cache_dir", lambda: tmp_path / "label-classes")
```

并在 `.gitignore` 的「런타임 데이터」段落 `annotation_tool/classes.json` 一行下面追加：

```
# labeling window: per-server cache of the damage classes (source runs)
/label-classes/
```

- [ ] **Step 5: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_classes.py -q -p no:cacheprovider`
Expected: 11 passed。再跑完整三目录命令，全绿。

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/core/classes.py labeling_tool/tests/test_classes.py labeling_tool/tests/conftest.py .gitignore
git commit -m "feat(classes): damage-class registry with a per-server cache

Built-in crack (1) and spalling (2) plus the classes the server hands
out (3..254). Cached per server so the tool works offline.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 服务器接口 V5 / V6 与同步

**Files:**
- Modify: `labeling_tool/api/client.py`（在 `list_sessions` 之后追加两个方法）
- Create: `labeling_tool/api/class_sync.py`
- Create: `labeling_tool/tests/test_class_sync.py`

**Interfaces:**
- Consumes: Task 1 的 `ClassRegistry`、`parse_class`、`parse_classes`、`load_cached`、`save_cached`
- Produces:
  - `ViewerApiClient.list_classes() -> dict`、`ViewerApiClient.add_class(name: str, color: str) -> dict`
  - `class_sync.SYNC_OK = "ok"`、`SYNC_UNSUPPORTED = "unsupported"`、`SYNC_OFFLINE = "offline"`
  - `sync_classes(client, base_url, root=None) -> tuple[ClassRegistry, str]`
  - `add_class_and_cache(client, base_url, registry, name, color, root=None) -> tuple[ClassRegistry, LabelClass]`（错误原样抛出：`ViewerApiError` / `requests.RequestException` / `ValueError`）

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_class_sync.py`

```python
import pytest
import requests

from labeling_tool.api import class_sync as S
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.core import classes as C

BASE = "https://viewer.example.com"


class _Client:
    def __init__(self, listing=None, error=None, added=None):
        self.listing, self.error, self.added = listing, error, added
        self.calls = []

    def list_classes(self):
        self.calls.append("list")
        if self.error:
            raise self.error
        return self.listing

    def add_class(self, name, color):
        self.calls.append(("add", name, color))
        if self.error:
            raise self.error
        return self.added


_LISTING = {"classes": [
    {"classId": 1, "name": "crack", "kind": "line", "color": "#FF3C3C", "builtin": True},
    {"classId": 2, "name": "spalling", "kind": "area", "color": "#3CE63C", "builtin": True},
    {"classId": 3, "name": "백태", "kind": "area", "color": "#3C8CFF", "builtin": False},
]}


def test_sync_reads_the_server_and_caches_it(tmp_path):
    reg, status = S.sync_classes(_Client(_LISTING), BASE, root=tmp_path)
    assert status == S.SYNC_OK and reg.ids() == [1, 2, 3]
    assert C.load_cached(BASE, root=tmp_path).ids() == [1, 2, 3]


def test_a_server_without_v5_means_builtins_only(tmp_path):
    C.save_cached(BASE, C.ClassRegistry([C.LabelClass(3, "x", "area", "#123456")]), root=tmp_path)
    err = ViewerApiError("HTTP_ERROR", "Not Found", 404)
    reg, status = S.sync_classes(_Client(error=err), BASE, root=tmp_path)
    assert status == S.SYNC_UNSUPPORTED and reg.ids() == [1, 2]


@pytest.mark.parametrize("err", [requests.ConnectionError("down"),
                                 ViewerApiError("S3_ERROR", "boom", 500)])
def test_offline_or_failing_uses_the_cache(tmp_path, err):
    C.save_cached(BASE, C.ClassRegistry([C.LabelClass(3, "x", "area", "#123456")]), root=tmp_path)
    reg, status = S.sync_classes(_Client(error=err), BASE, root=tmp_path)
    assert status == S.SYNC_OFFLINE and reg.ids() == [1, 2, 3]


def test_no_client_uses_the_cache(tmp_path):
    reg, status = S.sync_classes(None, BASE, root=tmp_path)
    assert status == S.SYNC_OFFLINE and reg.ids() == [1, 2]


def test_adding_a_class_updates_and_caches_the_registry(tmp_path):
    added = {"classId": 4, "name": "누수", "kind": "area", "color": "#FFAA00", "builtin": False}
    client = _Client(added=added)
    reg, cls = S.add_class_and_cache(client, BASE, C.ClassRegistry(), "  누수 ", "#FFAA00",
                                     root=tmp_path)
    assert client.calls == [("add", "누수", "#FFAA00")]          # name trimmed
    assert cls.class_id == 4 and reg.ids() == [1, 2, 4]
    assert C.load_cached(BASE, root=tmp_path).ids() == [1, 2, 4]


def test_adding_an_empty_name_is_refused_before_the_network(tmp_path):
    client = _Client()
    with pytest.raises(ValueError):
        S.add_class_and_cache(client, BASE, C.ClassRegistry(), "   ", "#FFAA00", root=tmp_path)
    assert client.calls == []


def test_client_methods_hit_the_v5_v6_urls(monkeypatch):
    from labeling_tool.api.client import ViewerApiClient
    seen = []

    class _Resp:
        ok, status_code = True, 200
        def json(self):
            return {"classes": []}

    c = ViewerApiClient("https://viewer.example.com/", "k")
    monkeypatch.setattr(c._s, "get", lambda url, **kw: seen.append(("GET", url)) or _Resp())
    monkeypatch.setattr(c._s, "post", lambda url, json=None, **kw: seen.append(("POST", url, json)) or _Resp())
    c.list_classes()
    c.add_class("누수", "#FFAA00")
    assert seen == [("GET", "https://viewer.example.com/api/viewer/classes/"),
                    ("POST", "https://viewer.example.com/api/viewer/classes/",
                     {"name": "누수", "color": "#FFAA00"})]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_class_sync.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'class_sync'`）

- [ ] **Step 3: 实现**。在 `labeling_tool/api/client.py` 的 `list_sessions` 方法之后追加：

```python
    # ---- damage classes (API v1.0.16 V5 / V6) ------------------------
    # Short timeout: the labeling window syncs on open and must not hang
    # when the server is unreachable (the cached list is used instead).
    CLASSES_TIMEOUT = (5, 10)

    def list_classes(self) -> dict:
        url = f"{self.base_url}/api/viewer/classes/"
        resp = self._s.get(url, timeout=self.CLASSES_TIMEOUT)
        self._raise_for_error(resp)
        return resp.json()

    def add_class(self, name: str, color: str) -> dict:
        url = f"{self.base_url}/api/viewer/classes/"
        resp = self._s.post(url, json={"name": name, "color": color},
                            timeout=self.CLASSES_TIMEOUT)
        self._raise_for_error(resp)
        return resp.json()
```

创建 `labeling_tool/api/class_sync.py`：

```python
"""Keep the damage-class list in step with the server (V5 / V6).

The server numbers the classes; the per-server cache (core.classes) lets
the tool work offline. A server without V5 (404) only knows the built-in
crack / spalling, and then adding is not possible.
"""

from __future__ import annotations

import requests

from labeling_tool.api.errors import ViewerApiError
from labeling_tool.core.classes import (
    ClassRegistry, LabelClass, load_cached, parse_class, parse_classes, save_cached,
)
from labeling_tool.logging_setup import vlog

SYNC_OK = "ok"
SYNC_UNSUPPORTED = "unsupported"
SYNC_OFFLINE = "offline"


def sync_classes(client, base_url: str, root=None) -> tuple[ClassRegistry, str]:
    if client is None:
        return load_cached(base_url, root), SYNC_OFFLINE
    try:
        payload = client.list_classes()
    except ViewerApiError as e:
        if e.http_status == 404:
            vlog().info("server has no class API (V5): built-in classes only")
            return ClassRegistry(), SYNC_UNSUPPORTED
        vlog().warning("class sync failed: %s", e)
        return load_cached(base_url, root), SYNC_OFFLINE
    except requests.RequestException as e:
        vlog().warning("class sync failed: %s", e)
        return load_cached(base_url, root), SYNC_OFFLINE
    registry = parse_classes(payload)
    try:
        save_cached(base_url, registry, root)
    except OSError as e:
        vlog().warning("class cache not written: %s", e)
    return registry, SYNC_OK


def add_class_and_cache(client, base_url: str, registry: ClassRegistry,
                        name: str, color: str, root=None
                        ) -> tuple[ClassRegistry, LabelClass]:
    name = (name or "").strip()
    if not name:
        raise ValueError("class name is empty")
    cls = parse_class(client.add_class(name, color))
    updated = registry.with_class(cls)
    try:
        save_cached(base_url, updated, root)
    except OSError as e:
        vlog().warning("class cache not written: %s", e)
    return updated, cls
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_class_sync.py -q -p no:cacheprovider`
Expected: 8 passed。完整三目录命令全绿。

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/api/client.py labeling_tool/api/class_sync.py labeling_tool/tests/test_class_sync.py
git commit -m "feat(api): list and add damage classes (V5 / V6) with a cached fallback

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 掩码编解码改为「编号 → 图层」字典

**Files:**
- Modify: `labeling_tool/core/mask_codec.py`
- Modify: `labeling_tool/core/mask_io.py`
- Test: `labeling_tool/tests/test_mask_codec.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `CRACK_ID`、`SPALLING_ID`、`MAX_CLASS_ID`
- Produces:
  - `encode_layers(layers: dict[int, np.ndarray | None]) -> np.ndarray`（面状按 id 升序先写，균열 最后写）
  - `decode_layers(raw: np.ndarray, *, mask_path: str | None = None) -> dict[int, np.ndarray]`（0/255 图层；标签图中每个出现的值各一层，并且总是包含 1、2 两层）
  - `encode_label_mask(crack, spalling)`、`decode_mask(raw, mask_path=)` 行为不变（改为调用上面两个）
  - `mask_io.load_origin_and_layers(origin_path, mask_path) -> tuple[np.ndarray, dict[int, np.ndarray]]`

- [ ] **Step 1: 写失败测试**，追加到 `labeling_tool/tests/test_mask_codec.py`：

```python
# ---------------------------------------------------------------- N classes
from labeling_tool.core.mask_codec import decode_layers, encode_layers


def _layer(shape, *rects):
    m = np.zeros(shape, np.uint8)
    for y0, y1, x0, x1 in rects:
        m[y0:y1, x0:x1] = 255
    return m


def test_layers_round_trip_with_user_classes():
    shape = (10, 10)
    layers = {1: _layer(shape, (0, 1, 0, 10)), 2: _layer(shape, (2, 4, 0, 5)),
              3: _layer(shape, (5, 7, 0, 5)), 17: _layer(shape, (8, 10, 0, 5))}
    label = encode_layers(layers)
    assert set(np.unique(label)) == {0, 1, 2, 3, 17}
    back = decode_layers(label)
    assert sorted(back) == [1, 2, 3, 17]
    for cid in layers:
        assert (back[cid] == layers[cid]).all(), cid


def test_crack_wins_over_every_class():
    shape = (4, 4)
    label = encode_layers({3: _layer(shape, (0, 4, 0, 4)), 1: _layer(shape, (1, 2, 0, 4))})
    assert (label[1] == 1).all() and label[0, 0] == 3


def test_decode_always_has_crack_and_spalling_layers():
    back = decode_layers(np.zeros((3, 3), np.uint8))
    assert sorted(back) == [1, 2] and not back[1].any() and not back[2].any()


def test_legacy_binary_and_rgb_still_decode_to_two_layers():
    binm = np.zeros((4, 4), np.uint8); binm[1, 1] = 255
    back = decode_layers(binm, mask_path="x_spalling.png")
    assert sorted(back) == [1, 2] and back[2][1, 1] == 255 and not back[1].any()
    rgb = np.zeros((4, 4, 3), np.uint8); rgb[0, 0, 2] = 255
    back = decode_layers(rgb)
    assert back[1][0, 0] == 255 and not back[2].any()


def test_old_two_layer_functions_still_work():
    crack = _layer((4, 4), (0, 1, 0, 4)); spall = _layer((4, 4), (2, 3, 0, 4))
    c, s = decode_mask(encode_label_mask(crack, spall))
    assert (c == crack).all() and (s == spall).all()


def test_a_label_with_a_user_class_is_not_mistaken_for_binary():
    label = np.zeros((4, 4), np.uint8); label[0, 0] = 9
    back = decode_layers(label)
    assert back[9][0, 0] == 255 and not back[1].any()


def test_encode_with_no_layers_is_an_error():
    with pytest.raises(ValueError):
        encode_layers({1: None, 2: None})
```

（若该测试文件顶部还没有 `import pytest` / `from labeling_tool.core.mask_codec import decode_mask, encode_label_mask`，一并补上。）

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_mask_codec.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'decode_layers'`）

- [ ] **Step 3: 实现**。把 `labeling_tool/core/mask_codec.py` 换成：

```python
"""Mask disk codec: class layers <-> single-channel integer label PNG.

Pixel value = class id (core.classes): 0 background, 1 crack, 2 spalling,
3..254 user classes. The tool keeps one 0/255 binary layer per class in
memory; this module translates at the disk boundary. On decode it still
recognises legacy 3-channel RGB (R = crack, G = spalling) and legacy
single-channel 0/255 binary masks (class by filename).
"""

from __future__ import annotations

import os

import numpy as np

from labeling_tool.core.classes import CRACK_ID, MAX_CLASS_ID, SPALLING_ID


def encode_layers(layers: dict) -> np.ndarray:
    """Pack {class id: 0/255 layer} into a label image. Area classes are
    written in id order, crack last, so crack wins any overlap."""
    present = {cid: m for cid, m in layers.items() if m is not None}
    if not present:
        raise ValueError("encode_layers: no layers")
    ref = next(iter(present.values()))
    out = np.zeros(ref.shape[:2], dtype=np.uint8)
    for cid in sorted(c for c in present if c != CRACK_ID):
        out[present[cid] > 0] = cid
    if CRACK_ID in present:
        out[present[CRACK_ID] > 0] = CRACK_ID
    return out


def decode_layers(raw: np.ndarray, *, mask_path: str | None = None) -> dict:
    """Decode a mask image into {class id: 0/255 layer}. Crack and spalling
    layers are always present; other ids only when their pixels are."""
    if raw.ndim == 3:
        return {CRACK_ID: (raw[..., 2] > 0).astype(np.uint8) * 255,
                SPALLING_ID: (raw[..., 1] > 0).astype(np.uint8) * 255}
    zeros = np.zeros(raw.shape[:2], dtype=np.uint8)
    if int(raw.max()) <= MAX_CLASS_ID:
        layers = {CRACK_ID: zeros, SPALLING_ID: zeros.copy()}
        # bincount, not np.unique: O(N) on a large panorama instead of a sort
        counts = np.bincount(raw.ravel(), minlength=MAX_CLASS_ID + 1)
        for value in np.nonzero(counts)[0]:
            if int(value) != 0:
                layers[int(value)] = (raw == value).astype(np.uint8) * 255
        return layers
    binm = (raw > 0).astype(np.uint8) * 255
    if mask_path is not None and "_spalling" in os.path.basename(mask_path).lower():
        return {CRACK_ID: zeros, SPALLING_ID: binm}
    return {CRACK_ID: binm, SPALLING_ID: zeros}


def encode_label_mask(crack: np.ndarray | None,
                      spalling: np.ndarray | None) -> np.ndarray:
    """Two-layer form of encode_layers (crack precedence)."""
    if crack is None and spalling is None:
        raise ValueError("encode_label_mask: both layers are None")
    return encode_layers({CRACK_ID: crack, SPALLING_ID: spalling})


def decode_mask(raw: np.ndarray, *, mask_path: str | None = None
                ) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Two-layer form of decode_layers: (crack, spalling). A legacy binary
    mask gives None for the class it does not hold, as before."""
    if raw.ndim != 3 and int(raw.max()) > MAX_CLASS_ID:
        layers = decode_layers(raw, mask_path=mask_path)
        is_spalling = (mask_path is not None
                       and "_spalling" in os.path.basename(mask_path).lower())
        return (None, layers[SPALLING_ID]) if is_spalling else (layers[CRACK_ID], None)
    layers = decode_layers(raw, mask_path=mask_path)
    return layers[CRACK_ID], layers[SPALLING_ID]
```

在 `labeling_tool/core/mask_io.py` 末尾追加（并把 import 改为 `from labeling_tool.core.mask_codec import decode_layers, decode_mask`）：

```python
def load_origin_and_layers(origin_path: str, mask_path: str | None):
    """Load the origin image and decode its mask into {class id: 0/255
    layer} (empty dict when there is no readable mask)."""
    origin = cv2.imread(origin_path)
    if origin is None:
        raise FileNotFoundError(f"Cannot read origin image: {origin_path}")
    layers = {}
    if mask_path is not None:
        raw = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if raw is not None:
            layers = decode_layers(raw, mask_path=mask_path)
    return origin, layers
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_mask_codec.py -q -p no:cacheprovider`
Expected: 全部通过（含原有用例）。完整三目录命令全绿。

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/core/mask_codec.py labeling_tool/core/mask_io.py labeling_tool/tests/test_mask_codec.py
git commit -m "feat(mask): encode and decode any number of class layers

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 派生掩码（하이라이트 · 15cm 경계）按字典

**Files:**
- Modify: `labeling_tool/core/derived_masks.py`
- Modify: `labeling_tool/ui/derived_mask_worker.py`
- Test: `labeling_tool/tests/test_derived_masks.py`（追加）

**Interfaces:**
- Consumes: Task 3 的约定（图层字典，0/255）
- Produces:
  - `build_highlight_layers(layers: dict) -> np.ndarray`、`build_repair15_layers(layers: dict, px_per_cm: float) -> np.ndarray`
  - `generate_derived_layers(layers: dict, px_per_cm, highlight_path, repair15_path) -> tuple[np.ndarray, np.ndarray | None]`
  - 旧的 `build_highlight(crack, spalling)`、`build_repair15(crack, spalling, px)`、`generate_derived_masks(crack, spalling, ...)` 保留为封装
  - `DerivedMaskRunnable(*, layers, px_per_cm, highlight_path, repair15_path, token, signals)`（构造参数从 `crack=, spalling=` 改为 `layers=`）

- [ ] **Step 1: 写失败测试**，追加到 `labeling_tool/tests/test_derived_masks.py`：

```python
# ---------------------------------------------------------------- N classes
from labeling_tool.core.derived_masks import (
    build_highlight_layers, build_repair15_layers, generate_derived_layers,
)


def _blk(shape, y0, y1, x0, x1):
    m = np.zeros(shape, np.uint8)
    m[y0:y1, x0:x1] = 255
    return m


def test_highlight_keeps_user_class_values_and_crack_precedence():
    shape = (80, 80)
    layers = {1: _blk(shape, 40, 41, 0, 80), 2: np.zeros(shape, np.uint8),
              5: _blk(shape, 10, 20, 10, 20)}
    hi = build_highlight_layers(layers)
    assert hi[15, 15] == 5
    assert hi[40, 40] == 1
    assert hi[15, 25] == 5                      # grown by the 10 px dilation
    assert set(np.unique(hi)) <= {0, 1, 5}


def test_repair15_covers_user_classes_too():
    shape = (60, 60)
    layers = {1: np.zeros(shape, np.uint8), 2: np.zeros(shape, np.uint8),
              4: _blk(shape, 30, 31, 30, 31)}
    r15 = build_repair15_layers(layers, px_per_cm=1.0)   # 15 px padding
    assert r15[30, 30] == 255 and r15[30, 44] == 255 and r15[30, 47] == 0


def test_generate_derived_layers_writes_both_files(tmp_path):
    import cv2
    shape = (30, 30)
    layers = {1: np.zeros(shape, np.uint8), 2: np.zeros(shape, np.uint8),
              3: _blk(shape, 5, 10, 5, 10)}
    hi, r15 = generate_derived_layers(layers, 1.0, tmp_path / "h.png", tmp_path / "r.png")
    assert (cv2.imread(str(tmp_path / "h.png"), cv2.IMREAD_UNCHANGED) == hi).all()
    assert r15 is not None and (tmp_path / "r.png").exists()


def test_no_layers_is_an_error():
    with pytest.raises(ValueError):
        build_highlight_layers({1: None, 2: None})
```

（文件顶部如缺 `import pytest`，补上。）

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 实现**。在 `labeling_tool/core/derived_masks.py` 中：import 改为 `from labeling_tool.core.classes import CRACK_ID, SPALLING_ID`（删掉 `CLASS_LABELS` 的 import），用下面的代码替换 `build_highlight`、`build_repair15`、`generate_derived_masks` 三个函数：

```python
def _present(layers: dict) -> dict:
    out = {cid: _binary(m) for cid, m in layers.items() if m is not None}
    if not out:
        raise ValueError("derived masks need at least one class layer")
    return out


def build_highlight_layers(layers: dict) -> np.ndarray:
    """Dilate every class by 10 px and re-encode with the mask's own values
    (area classes in id order, crack last -> crack precedence)."""
    present = _present(layers)
    shape = next(iter(present.values())).shape
    out = np.zeros(shape, dtype=np.uint8)
    kernel = _ellipse_kernel(_HIGHLIGHT_DILATE_PX)
    for cid in sorted(c for c in present if c != CRACK_ID) + (
            [CRACK_ID] if CRACK_ID in present else []):
        if present[cid].any():
            out[cv2.dilate(present[cid], kernel) > 0] = cid
    return out


def build_repair15_layers(layers: dict, px_per_cm: float) -> np.ndarray:
    """Union of every class expanded by round(15*px_per_cm) px, FILLED 0/255.

    Uses a distance transform (O(N), Euclidean) instead of a giant dilation
    kernel, so it stays fast even at large px/cm."""
    present = _present(layers)
    shape = next(iter(present.values())).shape
    union = np.zeros(shape, dtype=np.uint8)
    for m in present.values():
        union |= m
    if int(union.max()) == 0:
        return np.zeros(shape, dtype=np.uint8)
    pad_px = int(round(_REPAIR15_CM * float(px_per_cm)))
    src = np.where(union > 0, np.uint8(0), np.uint8(255))
    dist = cv2.distanceTransform(src, cv2.DIST_L2, 5)
    return np.where(dist <= pad_px, np.uint8(255), np.uint8(0)).astype(np.uint8)


def generate_derived_layers(layers: dict, px_per_cm: float,
                            highlight_path, repair15_path
                            ) -> tuple[np.ndarray, np.ndarray | None]:
    """Build the highlight (+ scale-dependent repair15) and write them to disk.

    repair15 is built+written only when px_per_cm is truthy. A None path skips
    the write but the array is still returned. Callers ensure parent dirs."""
    highlight = build_highlight_layers(layers)
    if highlight_path is not None:
        cv2.imwrite(str(highlight_path), highlight)
    repair15 = None
    if px_per_cm:
        repair15 = build_repair15_layers(layers, px_per_cm)
        if repair15_path is not None:
            cv2.imwrite(str(repair15_path), repair15)
    return highlight, repair15


# Two-layer forms kept for existing callers and tests.
def build_highlight(crack, spalling) -> np.ndarray:
    if crack is None and spalling is None:
        raise ValueError("build_highlight requires at least one of crack/spalling")
    return build_highlight_layers({CRACK_ID: crack, SPALLING_ID: spalling})


def build_repair15(crack, spalling, px_per_cm: float) -> np.ndarray:
    if crack is None and spalling is None:
        raise ValueError("build_repair15 requires at least one of crack/spalling")
    return build_repair15_layers({CRACK_ID: crack, SPALLING_ID: spalling}, px_per_cm)


def generate_derived_masks(crack, spalling, px_per_cm: float,
                           highlight_path, repair15_path):
    return generate_derived_layers({CRACK_ID: crack, SPALLING_ID: spalling},
                                   px_per_cm, highlight_path, repair15_path)
```

把模块 docstring 第一段的「crack/spalling layers」改为「class layers」。

`labeling_tool/ui/derived_mask_worker.py`：import 改为 `generate_derived_layers`；构造函数改为

```python
    def __init__(self, *, layers, px_per_cm,
                 highlight_path, repair15_path, token, signals):
        super().__init__()
        self._layers = layers
        self._px_per_cm = px_per_cm
        self._highlight_path = highlight_path
        self._repair15_path = repair15_path
        self._token = token
        self._signals = signals

    def run(self):
        try:
            hi, r15 = generate_derived_layers(
                self._layers, self._px_per_cm,
                self._highlight_path, self._repair15_path)
            self._signals.done.emit(self._token, hi, r15)
        except Exception as e:  # noqa: BLE001 - never crash the pool thread
            vlog().exception("derived mask worker failed: %s", e)
```

然后改唯一的调用方 `labeling_tool/core/window/main_window.py` 的 `_dispatch_derived`，让它暂时把两层包成字典（Task 7 会整体改为字典）：签名保持 `(self, filename, crack, spall, scale)`，`DerivedMaskRunnable(...)` 那一行改为

```python
        QThreadPool.globalInstance().start(DerivedMaskRunnable(
            layers={1: crack, 2: spall}, px_per_cm=scale,
            highlight_path=hi_path, repair15_path=r15_path,
            token=filename, signals=self._derived_signals))
```

用 `grep -rn "DerivedMaskRunnable(" labeling_tool` 确认没有别的调用方（测试里若有，同样改为 `layers=`）。

- [ ] **Step 4: 跑测试确认通过**

Run: 完整三目录命令。Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/core/derived_masks.py labeling_tool/ui/derived_mask_worker.py labeling_tool/core/window/main_window.py labeling_tool/tests/test_derived_masks.py
git commit -m "feat(mask): highlight and 15 cm boundary from any number of classes

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 结果导出、上传统计 `classAreas`、上传前同步

**Files:**
- Modify: `labeling_tool/core/result/result_image.py`、`text_report.py`、`exporter.py`
- Modify: `labeling_tool/annotation_payload.py`
- Modify: `labeling_tool/ui/upload_worker.py`
- Test: `labeling_tool/tests/test_annotation_payload.py`（追加）、`labeling_tool/tests/test_result_export_classes.py`（新）、`labeling_tool/tests/test_upload_worker_classes.py`（新）

**Interfaces:**
- Consumes: Task 1 `ClassRegistry`；Task 2 `sync_classes`；Task 3 `decode_layers`
- Produces:
  - `build_annotation_item(..., crack_mask, spalling_mask, boxes, extra_layers: dict[int, np.ndarray] | None = None) -> dict`：有 3 号以上且有像素的层时加 `classAreas`（按 id 升序，`areaMm2` 保留浮点，`pixelCount` int），否则不加该键
  - `write_result_image(out_path, origin_bgr, crack_mask, spalling_mask, boxes, extra_layers=None, colors=None)`：`extra_layers` 先画，crack / spalling 后画（与现在相同的颜色）
  - `write_text_report(..., boxes, extra_areas_mm2: dict[str, float | None] | None = None)`：每项追加一行 `class_area_mm2[<name>]: <value>`
  - `export_result(..., scale_px_per_cm, extra_layers=None, registry=None)`
  - `UploadWorker(..., class_registry: ClassRegistry | None = None)`；`done` 字典新增 `"unknown_classes": list[int]`

- [ ] **Step 1: 现有构造**：`UploadWorker(client, *, session_id: int, specs: list, labeling_dir: str, edit_batch_id: str, parent=None)`。新参数 `class_registry=None` 加在 `edit_batch_id` 之后、`parent` 之前（关键字参数），不改已有参数。

- [ ] **Step 2: 写失败测试**

追加到 `labeling_tool/tests/test_annotation_payload.py`：

```python
def _blank(shape=(20, 20)):
    return np.zeros(shape, np.uint8)


def test_no_user_classes_means_no_class_areas_key():
    item = build_annotation_item(
        timestamp=1, mask_s3_key="m", highlight_s3_key="h", repair15_s3_key="r",
        px_per_cm=10.0, scale_source="metrics", crack_mask=_blank(),
        spalling_mask=_blank(), boxes=[], extra_layers={})
    assert "classAreas" not in item


def test_class_areas_for_user_classes_in_id_order():
    a = _blank(); a[0:10, 0:10] = 255          # 100 px
    b = _blank(); b[0:2, 0:5] = 255            # 10 px
    empty = _blank()
    item = build_annotation_item(
        timestamp=1, mask_s3_key="m", highlight_s3_key="h", repair15_s3_key="r",
        px_per_cm=10.0, scale_source="metrics", crack_mask=_blank(),
        spalling_mask=_blank(), boxes=[], extra_layers={7: b, 3: a, 4: empty})
    # 10 px/cm -> 1 px = 1 mm^2
    assert item["classAreas"] == [
        {"classId": 3, "areaMm2": 100.0, "pixelCount": 100},
        {"classId": 7, "areaMm2": 10.0, "pixelCount": 10},
    ]
    assert item["crackMetrics"]["defectType"] == 0      # unchanged rule
```

（文件顶部如缺 `import numpy as np` / `from labeling_tool.annotation_payload import build_annotation_item`，补上。）

新建 `labeling_tool/tests/test_result_export_classes.py`：

```python
import cv2
import numpy as np

from labeling_tool.core.classes import ClassRegistry, LabelClass
from labeling_tool.core.result.exporter import export_result


def test_result_image_and_text_show_user_classes(tmp_path):
    origin = np.zeros((20, 20, 3), np.uint8)
    layer = np.zeros((20, 20), np.uint8); layer[0:10, 0:10] = 255
    reg = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF")])
    export_result(tmp_path, "p.jpg", origin, None, None, [], 10.0,
                  extra_layers={3: layer}, registry=reg)
    img = cv2.imread(str(tmp_path / "p.png"))
    assert tuple(int(v) for v in img[5, 5]) == (255, 140, 60)     # BGR of #3C8CFF
    text = (tmp_path / "p.txt").read_text(encoding="utf-8")
    assert "class_area_mm2[백태]: 100.00" in text


def test_unknown_ids_are_named_by_number(tmp_path):
    origin = np.zeros((10, 10, 3), np.uint8)
    layer = np.zeros((10, 10), np.uint8); layer[0, 0] = 255
    export_result(tmp_path, "p.jpg", origin, None, None, [], 10.0,
                  extra_layers={9: layer}, registry=ClassRegistry())
    assert "class_area_mm2[#9]: 1.00" in (tmp_path / "p.txt").read_text(encoding="utf-8")
```

新建 `labeling_tool/tests/test_upload_worker_classes.py`：

```python
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.classes import ClassRegistry, LabelClass
from labeling_tool.session import mask_store
from labeling_tool.ui import upload_worker as UW

_app = QApplication.instance() or QApplication([])


def _prepare(tmp_path, label):
    ldir = tmp_path / "Labeling"; ldir.mkdir()
    (tmp_path / "HighLight").mkdir(); (tmp_path / "Repair15").mkdir()
    name = mask_store.mask_name("stitched_1.jpg")
    for d in ("Labeling", "HighLight", "Repair15"):
        cv2.imwrite(str(tmp_path / d / name), label)
    return ldir


class _Client:
    def __init__(self, listing=None):
        self.listing = listing

    def list_classes(self):
        if self.listing is None:
            raise UW.requests.ConnectionError("down")
        return self.listing


def test_known_classes_get_areas_and_unknown_ones_are_reported(tmp_path):
    label = np.zeros((20, 20), np.uint8)
    label[0:2, 0:2] = 3          # known after sync
    label[5:6, 5:6] = 9          # nobody on the server knows 9
    ldir = _prepare(tmp_path, label)
    listing = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF")]).to_payload()
    worker = UW.UploadWorker(
        _Client(listing), session_id=45,
        specs=[{"filename": "stitched_1.jpg", "timestamp": 1, "px_per_cm": 10.0}],
        labeling_dir=str(ldir), edit_batch_id="b", class_registry=ClassRegistry())
    items, _cache = worker._build_items()
    assert items[0]["classAreas"] == [{"classId": 3, "areaMm2": 4.0, "pixelCount": 4}]
    assert worker.unknown_classes == [9]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_annotation_payload.py labeling_tool/tests/test_result_export_classes.py labeling_tool/tests/test_upload_worker_classes.py -q -p no:cacheprovider`
Expected: FAIL（`unexpected keyword argument 'extra_layers'` / `'class_registry'`）

- [ ] **Step 4: 实现**

`labeling_tool/annotation_payload.py`：`build_annotation_item` 加关键字参数 `extra_layers: dict | None = None`，在 `return` 之前：

```python
    item = {
        "timestamp": int(timestamp),
        "maskS3Key": mask_s3_key,
        "highlightS3Key": highlight_s3_key,
        "repair15S3Key": repair15_s3_key,
        "pxPerCm": float(px_per_cm),
        "scaleSource": scale_source or "metrics",
        "repairAreas": repair_areas,
        "crackMetrics": crack_metrics,
    }
    class_areas = []
    for cid in sorted(extra_layers or {}):
        layer = extra_layers[cid]
        count = int(np.count_nonzero(layer)) if layer is not None else 0
        if cid >= 3 and count:
            class_areas.append({"classId": int(cid),
                                "areaMm2": float(count * mm_per_px ** 2),
                                "pixelCount": count})
    if class_areas:                      # v1.0.16; absent = same as before
        item["classAreas"] = class_areas
    return item
```

（删除原来直接 `return {...}` 的字典；把模块 docstring 的「api-reference_v1.0.7」补一句「classAreas: v1.0.16 proposal」。）

`labeling_tool/core/result/result_image.py`：签名加 `extra_layers: dict | None = None, colors: dict | None = None`，在画 crack 之前：

```python
    for cid in sorted(extra_layers or {}):
        layer = extra_layers[cid]
        if layer is None:
            continue
        r, g, b = (colors or {}).get(cid, (150, 150, 150))
        out[layer > 0] = (b, g, r)
```

并把 docstring 的图层列表加一行「1b. user-class pixels -> their class colour, opaque」。

`labeling_tool/core/result/text_report.py`：签名加 `extra_areas_mm2: dict | None = None`，在 `lines` 列表后、写文件前：

```python
    for name, area in (extra_areas_mm2 or {}).items():
        lines.append(f"class_area_mm2[{name}]: {_fmt(area)}")
```

`labeling_tool/core/result/exporter.py`：签名加 `extra_layers: dict | None = None, registry=None`；在计算 `spalling_area_mm2` 之后：

```python
    from labeling_tool.core.classes import ClassRegistry
    registry = registry or ClassRegistry()
    extra = {cid: m for cid, m in (extra_layers or {}).items()
             if cid >= 3 and m is not None and m.any()}
    extra_areas = {
        (registry.get(cid).name if registry.get(cid) else f"#{cid}"):
            compute_spalling_area_mm2(m, scale_px_per_cm)
        for cid, m in sorted(extra.items())}
```

把 `extra_areas` 传给 `write_text_report(..., boxes, extra_areas)`，把 `extra_layers=extra, colors={cid: registry.rgb(cid) for cid in extra}` 传给 `write_result_image`。

`labeling_tool/ui/upload_worker.py`：
- import：`from labeling_tool.core.mask_codec import decode_layers`、`import requests`、`from labeling_tool.api.class_sync import sync_classes`、`from labeling_tool.core.classes import ClassRegistry, CRACK_ID, SPALLING_ID`
- `__init__` 末尾加参数 `class_registry=None`，保存 `self._class_registry = class_registry or ClassRegistry()`，并设 `self.unknown_classes: list[int] = []`
- `_build_items` 开头（循环前）：

```python
        # Classes added on other PCs since this window opened: ask once more,
        # so only ids the server knows go into classAreas (unknown -> 400).
        registry = self._class_registry
        if self._client is not None and hasattr(self._client, "list_classes"):
            synced, status = sync_classes(self._client, getattr(self._client, "base_url", ""))
            if status == "ok":
                registry = synced
        unknown: set[int] = set()
```

- 循环里把 `crack, spall = decode_mask(...)` 换成：

```python
            layers = decode_layers(raw, mask_path=str(mask_path)) if raw is not None else {}
            crack, spall = layers.get(CRACK_ID), layers.get(SPALLING_ID)
            extra = {}
            for cid, layer in layers.items():
                if cid in (CRACK_ID, SPALLING_ID):
                    continue
                if cid in registry:
                    extra[cid] = layer
                else:
                    unknown.add(cid)
```

  并在 `build_annotation_item(...)` 调用里加 `extra_layers=extra`
- 循环结束后：`self.unknown_classes = sorted(unknown)`；若非空，`vlog().warning("upload: class ids unknown to the server kept in the mask only: %s", self.unknown_classes)`
- `run()` 里所有 `self.done.emit({...})` 的字典都加 `"unknown_classes": self.unknown_classes`（`grep -n "done.emit" labeling_tool/ui/upload_worker.py` 找全）

注意：`sync_classes` 的 `base_url` 用于缓存文件名；client 没有 `base_url` 属性时（测试假对象）传空串即可，`cache_file` 会落到 `default.json`（测试里在 tmp 目录）。

- [ ] **Step 5: 跑测试确认通过**

Run: 完整三目录命令。Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/annotation_payload.py labeling_tool/core/result labeling_tool/ui/upload_worker.py labeling_tool/tests/test_annotation_payload.py labeling_tool/tests/test_result_export_classes.py labeling_tool/tests/test_upload_worker_classes.py
git commit -m "feat(upload): per-class areas (classAreas) and user classes in results

Only ids the server knows go into classAreas; others stay in the mask
and are reported. Nothing changes when only crack/spalling are used.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 画布图层字典、当前类别、面状互斥、SAM 写当前类别

**Files:**
- Modify: `labeling_tool/core/canvas/image_canvas.py`
- Modify: `labeling_tool/core/canvas/overlay_painter.py`
- Test: `labeling_tool/tests/test_canvas_classes.py`（新）

**Interfaces:**
- Consumes: Task 1 `ClassRegistry`、`CRACK_ID`、`SPALLING_ID`；Task 3 字典约定
- Produces（`ImageCanvas`）:
  - `layers: dict[int, np.ndarray]`（加载后总有 1、2）
  - `brush_mask_crack` / `brush_mask_spalling`：读写属性，映射到 `layers[1]` / `layers[2]`（无图像时为 `None`）
  - `current_class_id: int`（默认 `CRACK_ID`）；兼容属性 `current_category`（读：1→"crack"，其他→"spalling"；写："crack"→1，"spalling"→2），Task 8 删除
  - `set_class_registry(registry: ClassRegistry) -> None`、`class_registry` 属性
  - `set_image_layers(origin_bgr, layers: dict) -> None`；`set_image(origin, crack, spalling)` 改为调用它
  - `snapshot()` / `record_external_change(before)` 支持层数变化
- Produces（`overlay_painter`）:`paint_layer_overlays(painter, viewport, widget_w, widget_h, layers: list[tuple[np.ndarray, tuple[int, int, int]]])`；`paint_mask_overlay` 改为调用它；`compute_highlight_halo(highlight, *layers)`

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_canvas_classes.py`

```python
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas
from labeling_tool.core.classes import ClassRegistry, LabelClass

_app = QApplication.instance() or QApplication([])
REG = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF"),
                     LabelClass(4, "누수", "area", "#FFAA00")])


class _Event:
    def __init__(self, x, y, button=Qt.LeftButton):
        self._x, self._y, self._b = x, y, button
    def x(self): return self._x
    def y(self): return self._y
    def button(self): return self._b
    def modifiers(self): return Qt.NoModifier


class _Predictor:
    def set_image(self, bgr):
        self._hw = bgr.shape[:2]

    def predict(self, points, labels):
        m = np.zeros(self._hw, np.uint8)
        m[:, :] = 255
        return m


def _canvas(layers=None):
    c = ImageCanvas()
    c.resize(100, 100)
    c.set_class_registry(REG)
    c.set_image_layers(np.zeros((100, 100, 3), np.uint8), layers or {})
    return c


def _stroke(c, x0, y0, x1, y1, button=Qt.LeftButton):
    wx0, wy0 = c.viewport.image_to_widget(x0, y0)
    wx1, wy1 = c.viewport.image_to_widget(x1, y1)
    c.mousePressEvent(_Event(wx0, wy0, button))
    c.mouseMoveEvent(_Event(wx1, wy1, button))
    c.mouseReleaseEvent(_Event(wx1, wy1, button))


def test_layers_always_hold_crack_and_spalling():
    c = _canvas()
    assert sorted(c.layers) == [1, 2]
    assert c.brush_mask_crack is c.layers[1] and c.brush_mask_spalling is c.layers[2]


def test_loaded_user_class_layers_are_kept():
    lay = np.zeros((100, 100), np.uint8); lay[0:5, 0:5] = 255
    c = _canvas({3: lay, 9: lay.copy()})
    assert sorted(c.layers) == [1, 2, 3, 9]


def test_the_brush_paints_the_current_user_class():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    assert c.layers[3].any() and not c.layers[2].any() and not c.layers[1].any()


def test_painting_an_area_class_clears_other_area_classes_there():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    c.current_class_id = 2
    _stroke(c, 20, 50, 80, 50)
    assert c.layers[2].any() and not c.layers[3][50, 50]


def test_area_painting_leaves_crack_alone():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 1
    _stroke(c, 10, 50, 90, 50)
    crack = c.layers[1].copy()
    c.current_class_id = 3
    _stroke(c, 10, 50, 90, 50)
    assert (c.layers[1] == crack).all()


def test_sam_commits_into_the_current_area_class_and_clears_others():
    c = _canvas()
    c.layers[2][:, :] = 255
    c.set_sam_predictor(_Predictor())
    c.set_sam_mode(True)
    c.current_class_id = 4
    c._sam_add_point(50, 50, 1)
    assert c.commit_sam()
    assert c.layers[4][50, 50] == 255 and c.layers[2][50, 50] == 0


def test_sam_never_writes_crack():
    c = _canvas()
    c.set_sam_predictor(_Predictor())
    c.set_sam_mode(True)
    c.current_class_id = 1
    c._sam_add_point(50, 50, 1)
    assert c.commit_sam()
    assert not c.layers[1].any() and c.layers[2][50, 50] == 255


def test_undo_restores_a_user_class_stroke():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    assert c.undo() and not c.layers[3].any()
    assert c.redo() and c.layers[3].any()


def test_undo_after_reset_brings_a_user_class_back():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    drawn = c.layers[3].copy()
    before = c.snapshot()
    c.set_image_layers(np.zeros((100, 100, 3), np.uint8), {})    # 복원: no class 3
    c.record_external_change(before)
    assert not c.layers[3].any()
    assert c.undo()
    assert (c.layers[3] == drawn).all()


def test_current_category_compat_property():
    c = _canvas()
    c.current_category = "spalling"
    assert c.current_class_id == 2 and c.current_category == "spalling"
    c.current_category = "crack"
    assert c.current_class_id == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_canvas_classes.py -q -p no:cacheprovider`
Expected: FAIL（`AttributeError: 'ImageCanvas' object has no attribute 'set_class_registry'`）

- [ ] **Step 3: 实现 overlay_painter**。在 `labeling_tool/core/canvas/overlay_painter.py`：把 `paint_mask_overlay` 的函数体（从计算 `x0..` 到循环结束）搬到新函数 `paint_layer_overlays(painter, viewport, widget_w, widget_h, layers)`，循环改为 `for mask, rgb in layers:`；`paint_mask_overlay` 改为

```python
def paint_mask_overlay(painter, viewport, widget_w, widget_h,
                       crack_mask, spalling_mask) -> None:
    """Two-layer form of paint_layer_overlays (crack red, spalling green)."""
    paint_layer_overlays(painter, viewport, widget_w, widget_h,
                         [(spalling_mask, _SPALLING_RGB), (crack_mask, _CRACK_RGB)])
```

`compute_highlight_halo` 签名改为 `compute_highlight_halo(highlight, *layers)`，函数体循环 `for m in layers: if m is not None and m.shape == halo.shape: halo &= (m == 0)`。

- [ ] **Step 4: 实现 image_canvas**（逐处改，改完跑 Step 1 测试）

1. import：`from labeling_tool.core.classes import ClassRegistry, CRACK_ID, SPALLING_ID`；`from labeling_tool.core.canvas.overlay_painter import paint_layer_overlays`（`paint_mask_overlay` 的 import 不再需要可删）；删掉 `DEFAULT_CATEGORY` 的 import。
2. `__init__`：把 `self.brush_mask_crack = None` / `self.brush_mask_spalling = None` 两行换成 `self.layers: dict[int, np.ndarray] = {}`；把 `self.current_category: str = DEFAULT_CATEGORY` 换成 `self.current_class_id: int = CRACK_ID` 和 `self.class_registry = ClassRegistry()`。
3. 在 `_touch_mask` 之前加：

```python
    # ----- class layers --------------------------------------------------
    @property
    def brush_mask_crack(self):
        return self.layers.get(CRACK_ID)

    @brush_mask_crack.setter
    def brush_mask_crack(self, m):
        self._set_layer(CRACK_ID, m)

    @property
    def brush_mask_spalling(self):
        return self.layers.get(SPALLING_ID)

    @brush_mask_spalling.setter
    def brush_mask_spalling(self, m):
        self._set_layer(SPALLING_ID, m)

    def _set_layer(self, cid: int, m) -> None:
        if m is None:
            self.layers.pop(cid, None)
        else:
            self.layers[cid] = m

    @property
    def current_category(self) -> str:
        """Compatibility with the two-class callers (removed in Task 8)."""
        return "crack" if self.current_class_id == CRACK_ID else "spalling"

    @current_category.setter
    def current_category(self, name: str) -> None:
        self.current_class_id = CRACK_ID if name == "crack" else SPALLING_ID

    def set_class_registry(self, registry: ClassRegistry) -> None:
        self.class_registry = registry
        self._touch_mask()
        self.update()

    def _ensure_layer(self, cid: int) -> np.ndarray | None:
        """The layer for `cid`, created empty on first use."""
        if cid not in self.layers:
            ref = self.layers.get(CRACK_ID)
            if ref is None:
                return None
            self.layers[cid] = np.zeros_like(ref)
        return self.layers[cid]

    def _clear_other_areas(self, cid: int, where) -> None:
        """One pixel, one class: an area edit wins over other areas there.
        `where` is a boolean mask or a callable drawing 0 into a layer."""
        if not self.class_registry.is_area(cid):
            return
        for other, layer in self.layers.items():
            if other == cid or other == CRACK_ID or layer is None:
                continue
            if callable(where):
                where(layer)
            else:
                layer[where] = 0
```

4. `set_image`：改名为 `set_image_layers(self, origin_bgr, layers: dict)`，把原来那两行 `self.brush_mask_crack = _mask_to_origin(...)` / `self.brush_mask_spalling = ...` 和它们之前的尺寸警告循环换成：

```python
        conformed = {}
        for cid, m in (layers or {}).items():
            if m is not None and m.shape[:2] != (h, w):
                from labeling_tool.logging_setup import vlog
                vlog().warning("loaded class %s layer %s != origin (%d,%d); conformed "
                               "(upstream AI-mask vs stitched-size mismatch)",
                               cid, tuple(m.shape[:2]), h, w)
            conformed[int(cid)] = _mask_to_origin(m, h, w)
        for cid in (CRACK_ID, SPALLING_ID):
            conformed.setdefault(cid, np.zeros((h, w), dtype=np.uint8))
        self.layers = conformed
```

   并加两层兼容入口：

```python
    def set_image(self, origin_bgr, crack_mask, spalling_mask):
        self.set_image_layers(origin_bgr, {CRACK_ID: crack_mask, SPALLING_ID: spalling_mask})
```

5. `clear()`：`self.layers = {}`（替换两行赋 None）。
6. `_masks()` 改为 `return self.layers`；`_snapshot()` 不变（遍历 `_masks()`）。`record_external_change` 改为：

```python
    def record_external_change(self, before: dict) -> None:
        """Record a change made outside the canvas (reset to the loaded mask)
        from `before` (see snapshot()) to the current masks. Layers that the
        reload dropped come back empty so the step can restore them."""
        for cid in before:
            self._ensure_layer(cid)
        if self._history.record(before, self._masks()):
            self.history_changed.emit()
```

7. 画笔：`_active_brush_mask` 改为 `return self._ensure_layer(self.current_class_id)`。`_brush_paint_at` 在 `cv2.line(m, ...)` 之后加：

```python
        if not self._brush_erase:
            self._clear_other_areas(
                self.current_class_id,
                lambda layer: cv2.line(layer, (x1, y1), (x2, y2), 0,
                                       thickness=thickness, lineType=cv2.LINE_8))
```

   原来的 `self.current_category == "crack"` 判断（`_brush_paint_at` 与 `mousePressEvent` 的 brush 分支各一处）改为 `self.current_class_id == CRACK_ID`。在 `mousePressEvent` 的 brush 分支 `self._begin_mask_edit()` **之前**加 `self._ensure_layer(self.current_class_id)`，保证撤销快照里有这个层。
8. 光标颜色 `_paint_brush_cursor`：`elif` 两支换成 `else: color = QColor(*self.class_registry.rgb(self.current_class_id))`（擦除仍为 `QColor(255, 80, 80)`）。
9. `commit_sam`：

```python
    def commit_sam(self) -> bool:
        """OR the preview into the current area class (spalling when the
        current class is the crack line); returns True if anything written."""
        cid = (self.current_class_id
               if self.class_registry.is_area(self.current_class_id) else SPALLING_ID)
        if self._sam_preview is None or self._ensure_layer(cid) is None:
            return False
        self._begin_mask_edit()
        region = self._sam_preview > 0
        self.layers[cid][region] = 255
        self._clear_other_areas(cid, region)
        self._end_mask_edit()
        self._clear_sam_state()
        self._touch_mask()
        self.mask_edited.emit()
        self.update()
        return True
```

10. 叠加绘制（`paint_mask_overlay(op, ...)` 那处）改为：

```python
            reg = self.class_registry
            ordered = sorted(c for c in self.layers if c != CRACK_ID) + [CRACK_ID]
            paint_layer_overlays(op, self.viewport, w, h,
                                 [(self.layers.get(c), reg.rgb(c)) for c in ordered])
```

11. `set_highlight`：`compute_highlight_halo(arr, *self.layers.values())`。

- [ ] **Step 5: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_canvas_classes.py -q -p no:cacheprovider`，再跑完整三目录命令。
Expected: 全绿（原有画布、SAM、撤销测试不改动即通过）。

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/core/canvas labeling_tool/tests/test_canvas_classes.py
git commit -m "feat(canvas): one layer per class; brush and SAM write the current class

Area classes are exclusive (the later edit wins), crack stays on top,
SAM never writes the crack line.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 窗口读写管线改字典 + 类别表同步

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`
- Modify: `labeling_tool/ui/main_window.py`
- Test: `labeling_tool/tests/test_side_panel.py`（追加）

**Interfaces:**
- Consumes: Task 1～6
- Produces（`MainWindow`）:
  - `class_registry: ClassRegistry`、`_class_sync_status: str`（`"ok" | "unsupported" | "offline"`）
  - `_apply_class_registry(registry, status) -> None`（存、传给画布、调用 `_refresh_class_pickers()`；基类里 `_refresh_class_pickers` 先是空方法，Task 8 实现）
  - `_class_base_url() -> str`（基类返回 `""`；Viewer 返回 `client.base_url` 或 `manifest.base`）
- Produces（`ViewerMainWindow`）:`_start_class_sync()`；上传时 `UploadWorker(..., class_registry=self.class_registry)`，结束时若 `unknown_classes` 非空显示状态栏 `class_unknown_on_upload`

- [ ] **Step 1: 写失败测试**，追加到 `labeling_tool/tests/test_side_panel.py`：

```python
# ---------------------------------------------------------------- user classes
def _with_user_class_mask(tmp_path, monkeypatch, value=3):
    """A window whose first photo already has class `value` pixels saved."""
    import cv2
    win = _make_window(tmp_path, monkeypatch)
    label = np.zeros((8, 8), np.uint8)
    label[1:3, 1:3] = value
    win.output_dir.mkdir(parents=True, exist_ok=True)
    from labeling_tool.session import mask_store
    cv2.imwrite(str(win.output_dir / mask_store.mask_name(_FILES[0])), label)
    win._show_image(0, force_reload=True)
    return win


def test_a_saved_user_class_survives_load_and_save(tmp_path, monkeypatch):
    import cv2
    from labeling_tool.session import mask_store
    win = _with_user_class_mask(tmp_path, monkeypatch, value=3)
    try:
        assert sorted(win.canvas.layers) == [1, 2, 3]
        win._edited[_FILES[0]] = True
        assert win._save_all_artifacts(silent=True, async_derived=False)
        back = cv2.imread(str(win.output_dir / mask_store.mask_name(_FILES[0])),
                          cv2.IMREAD_UNCHANGED)
        assert back[1, 1] == 3 and back[5, 5] == 0
        hi = cv2.imread(str(win.highlight_dir / mask_store.mask_name(_FILES[0])),
                        cv2.IMREAD_UNCHANGED)
        assert hi[1, 1] == 3
    finally:
        win.close()


def test_an_unknown_class_is_kept_through_a_save(tmp_path, monkeypatch):
    import cv2
    from labeling_tool.session import mask_store
    win = _with_user_class_mask(tmp_path, monkeypatch, value=9)
    try:
        assert 9 not in win.class_registry
        win._edited[_FILES[0]] = True
        assert win._save_all_artifacts(silent=True, async_derived=False)
        back = cv2.imread(str(win.output_dir / mask_store.mask_name(_FILES[0])),
                          cv2.IMREAD_UNCHANGED)
        assert back[1, 1] == 9
    finally:
        win.close()


def test_the_window_starts_from_the_cached_class_list(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    C.save_cached("", C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]))
    win = _make_window(tmp_path, monkeypatch)            # client=None -> offline
    try:
        assert win.class_registry.ids() == [1, 2, 3]
        assert win._class_sync_status == "offline"
        assert win.canvas.class_registry is win.class_registry
    finally:
        win.close()
```

注意：`_make_window` 里 `Manifest(session_id=45, base="", ...)`，所以缓存键是空串 `""`，`cache_file` 会落到 `default.json`；autouse fixture 已把目录放进 `tmp_path`。

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_side_panel.py -q -p no:cacheprovider -k "user_class or unknown_class or cached_class"`
Expected: FAIL（层里没有 3 / 没有 `class_registry`）

- [ ] **Step 3: 实现 core MainWindow**（`labeling_tool/core/window/main_window.py`）

1. import：`from labeling_tool.core.mask_io import load_origin_and_layers`、`from labeling_tool.core.mask_codec import encode_layers`、`from labeling_tool.core.classes import ClassRegistry, CRACK_ID, SPALLING_ID`。
2. `__init__` 里（`_build_ui()` 之前）：`self.class_registry = ClassRegistry()`、`self._class_sync_status = "offline"`；`_build_ui()` 之后：`self.canvas.set_class_registry(self.class_registry)`。
3. 新方法：

```python
    # ------------------------------------------------------------------
    # Damage classes
    # ------------------------------------------------------------------
    def _class_base_url(self) -> str:
        return ""

    def _apply_class_registry(self, registry: ClassRegistry, status: str) -> None:
        self.class_registry = registry
        self._class_sync_status = status
        self.canvas.set_class_registry(registry)
        self._refresh_class_pickers()

    def _refresh_class_pickers(self) -> None:
        """Rebuild the class pickers from class_registry (Task 8)."""
```

4. `_show_image`：`origin, crack_mask, spalling_mask = load_origin_and_masks(...)` 换成 `origin, layers = load_origin_and_layers(origin_path, mask_path)`；`self.canvas.set_image(origin, crack_mask, spalling_mask)` 换成 `self.canvas.set_image_layers(origin, layers)`。末尾「No Repair15 on disk yet」那段换成：

```python
        elif self.current_scale and self.current_scale > 0:
            if self.canvas.layers:
                self._dispatch_derived(
                    filename, {c: m.copy() for c, m in self.canvas.layers.items()},
                    float(self.current_scale))
```

5. `_dispatch_derived(self, filename, layers: dict, scale)`：签名改为字典，`DerivedMaskRunnable(layers=layers, ...)`。
6. `_save_all_artifacts`：`mc = ...` / `ms = ...` 两行与 `if mc is not None or ms is not None:` 块换成：

```python
        layers = self.canvas.layers
        if layers:
            label = encode_layers(layers)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mask_out = self._save_mask_path(filename)
            _cv2.imwrite(str(mask_out), label)

            # ----- 1b. Derived masks: highlight + (scale-dependent) repair15 --
            snap = {c: m.copy() for c, m in layers.items()}
            scale = self.current_scale or 0.0
            if async_derived:
                if mask_dirty and self.canvas.bbox_interaction.boxes:
                    self._offer_refit_for = filename
                self._dispatch_derived(filename, snap, scale)
            else:
                from labeling_tool.core.derived_masks import generate_derived_layers
                hi_path = (str(self.highlight_dir / mask_store.mask_name(filename))
                           if self.highlight_dir is not None else None)
                r15_path = (str(self.repair15_dir / mask_store.mask_name(filename))
                            if self.repair15_dir is not None else None)
                if self.highlight_dir is not None:
                    self.highlight_dir.mkdir(parents=True, exist_ok=True)
                if self.repair15_dir is not None:
                    self.repair15_dir.mkdir(parents=True, exist_ok=True)
                hi, r15 = generate_derived_layers(snap, scale, hi_path, r15_path)
                self.canvas.set_highlight(hi)
                self.canvas.set_repair15(r15)
```

   `export_result(...)` 调用改为 `export_result(self.result_dir, filename, origin, layers.get(CRACK_ID), layers.get(SPALLING_ID), list(self.canvas.bbox_interaction.boxes), self.current_scale, extra_layers={c: m for c, m in layers.items() if c not in (CRACK_ID, SPALLING_ID)}, registry=self.class_registry)`。
7. `grep -n "brush_mask_crack\|brush_mask_spalling\|load_origin_and_masks\|encode_label_mask" labeling_tool/core/window/main_window.py`，确认已无残留（`_on_brush_reset` 用的是 `snapshot()` / `record_external_change`，不需要改）。

- [ ] **Step 4: 实现 Viewer**（`labeling_tool/ui/main_window.py`）

1. `__init__` 末尾（`_init_sam()` 之后）调用 `self._start_class_sync()`。
2. 新方法：

```python
    def _class_base_url(self) -> str:
        if self._client is not None:
            return self._client.base_url
        return getattr(self._manifest, "base", "") or ""

    def _start_class_sync(self) -> None:
        """Cached classes at once; the server's list when it answers."""
        from labeling_tool.core.classes import load_cached
        from labeling_tool.api.class_sync import SYNC_OFFLINE
        base = self._class_base_url()
        self._apply_class_registry(load_cached(base), SYNC_OFFLINE)
        if self._client is None:
            return
        from PyQt5.QtCore import QThreadPool
        from labeling_tool.ui.class_sync_worker import ClassSyncRunnable, ClassSyncSignals
        self._class_sync_signals = ClassSyncSignals()
        self._class_sync_signals.done.connect(self._apply_class_registry)
        QThreadPool.globalInstance().start(
            ClassSyncRunnable(self._client, base, self._class_sync_signals))
```

3. 新文件 `labeling_tool/ui/class_sync_worker.py`：

```python
"""Ask the server for the class list off the UI thread (it may be slow or
unreachable); the window applies the result when it arrives."""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from labeling_tool.api.class_sync import sync_classes
from labeling_tool.logging_setup import vlog


class ClassSyncSignals(QObject):
    done = pyqtSignal(object, str)          # ClassRegistry, status


class ClassSyncRunnable(QRunnable):
    def __init__(self, client, base_url: str, signals: ClassSyncSignals):
        super().__init__()
        self._client, self._base, self._signals = client, base_url, signals

    def run(self):
        try:
            registry, status = sync_classes(self._client, self._base)
            self._signals.done.emit(registry, status)
        except Exception as e:  # noqa: BLE001 - never crash the pool thread
            vlog().exception("class sync worker failed: %s", e)
```

4. 上传：找到创建 `UploadWorker(` 的地方（`grep -n "UploadWorker(" labeling_tool/ui/main_window.py`），加 `class_registry=self.class_registry`；找到上传完成的处理（`_finish_upload`），在其显示结果之后加：

```python
        unknown = result.get("unknown_classes") or []
        if unknown:
            self.status.showMessage(self.tr_(
                "class_unknown_on_upload", ids=", ".join(f"#{i}" for i in unknown)))
```

   （变量名按 `_finish_upload` 实际参数名。）
5. i18n：三种语言各加一键（Task 8 统一补其余键）：
   - ko `"class_unknown_on_upload": "서버에 없는 카테고리({ids})는 마스크에만 남기고 면적은 보내지 않았습니다.",`
   - zh `"class_unknown_on_upload": "服务器上没有的类别（{ids}）只保留在掩码里，未上传面积。",`
   - en `"class_unknown_on_upload": "Classes unknown to the server ({ids}) stay in the mask; their areas were not sent.",`
   - 同时各加 `"class_unknown"`：ko/zh/en 都是 `"#{id}"`。

- [ ] **Step 5: 跑测试确认通过**

Run: 完整三目录命令。Expected: 全绿（`tests/test_i18n_coverage.py` 要求三种语言键一致）。

- [ ] **Step 6: Commit**

```bash
git add labeling_tool/core/window/main_window.py labeling_tool/ui/main_window.py labeling_tool/ui/class_sync_worker.py labeling_tool/core/i18n labeling_tool/tests/test_side_panel.py
git commit -m "feat(window): load, save and upload every class layer; sync the class list

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 类别选择器（替换 균열 / 박리 按钮）、数字键 1～9

**Files:**
- Create: `labeling_tool/core/window/class_picker.py`
- Modify: `labeling_tool/core/window/ui_builder.py`（`_build_brush_options`、`_build_sam_options`）
- Modify: `labeling_tool/core/window/main_window.py`（`_refresh_class_pickers`、`_set_current_class`、`_select_class_by_index`、SAM 切换、retranslate；删除 `_on_category_changed` / `_select_category_btn` 与 `CATEGORIES` 用法）
- Modify: `labeling_tool/core/window/shortcuts.py`、`styles.py`
- Modify: `labeling_tool/core/canvas/image_canvas.py`（删除 Task 6 的兼容属性 `current_category`）、`labeling_tool/core/constants.py`（删除 `CATEGORIES`、`DEFAULT_CATEGORY`，若再无引用）
- Modify: i18n 三个文件、`docs/i18n-glossary.md`
- Test: `labeling_tool/tests/test_side_panel.py`（替换两个旧测试、追加新测试）、`labeling_tool/tests/test_canvas_classes.py`（删除 `test_current_category_compat_property`）

**Interfaces:**
- Consumes: Task 6 `current_class_id`；Task 7 `_apply_class_registry`、`class_registry`
- Produces:
  - `ClassPicker(QWidget)`：信号 `classChosen(int)`、`addRequested()`；方法 `set_classes(entries: list[tuple[int, str, tuple[int, int, int]]], current: int, disabled: set[int] = frozenset())`、`set_current(cid: int)`、`current_class() -> int`、`set_add_enabled(enabled: bool, tip: str)`、`retranslate(label: str)`；子控件 `combo: QComboBox`、`add_button: QToolButton`、`label: QLabel`
  - 窗口属性 `_class_picker_brush`、`_class_picker_sam`；方法 `_set_current_class(cid)`、`_select_class_by_index(i)`、`_on_add_class()`（基类空实现，Task 9 在 Viewer 里实现）、`_can_add_class() -> tuple[bool, str]`（基类返回 `(False, tr("class_add_unavailable"))`）

- [ ] **Step 1: 改测试**。在 `labeling_tool/tests/test_side_panel.py`：

把 `test_crack_and_spalling_are_only_shown_with_the_brush` 整个替换为：

```python
def test_the_class_picker_shows_with_the_brush_and_sam_only(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for idx in (VIEW, BRUSH, SAM, BBOX):
            win._tool_picker.setCurrentIndex(idx)
            QApplication.processEvents()
            assert win._class_picker_brush.isVisible() == (idx == BRUSH)
            assert win._class_picker_sam.isVisible() == (idx == SAM)
    finally:
        win.close()
```

把 `test_category_shortcuts_work_while_the_brush_page_is_hidden` 整个替换为：

```python
def test_number_keys_pick_classes_while_the_brush_page_is_hidden(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._apply_class_registry(
            C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]), "ok")
        assert not win._class_picker_brush.isVisible()           # 보기 selected
        win.activateWindow()
        QTest.keyClick(win, Qt.Key_2)
        assert win.canvas.current_class_id == 2
        QTest.keyClick(win, Qt.Key_3)
        assert win.canvas.current_class_id == 3
        assert win._class_picker_brush.current_class() == 3
        QTest.keyClick(win, Qt.Key_9)                             # no 9th class: no change
        assert win.canvas.current_class_id == 3
    finally:
        win.close()
```

追加：

```python
def test_both_pickers_follow_the_current_class(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._apply_class_registry(
            C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]), "ok")
        combo = win._class_picker_brush.combo
        combo.setCurrentIndex(combo.findData(3))
        assert win.canvas.current_class_id == 3
        assert win._class_picker_sam.current_class() == 3
        assert [combo.itemData(i) for i in range(combo.count())] == [1, 2, 3]
        assert "백태" in combo.itemText(2) and "3" in combo.itemText(2)
    finally:
        win.close()


def test_sam_cannot_use_the_crack_line(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._set_current_class(1)
        win._tool_picker.setCurrentIndex(SAM)
        QApplication.processEvents()
        assert win.canvas.current_class_id == 2                   # moved to 박리
        model = win._class_picker_sam.combo.model()
        assert not model.item(win._class_picker_sam.combo.findData(1)).isEnabled()
        win._set_current_class(1)                                 # e.g. key 1 in SAM
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


def test_the_add_button_needs_the_server(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)                     # client=None
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        btn = win._class_picker_brush.add_button
        assert not btn.isEnabled() and btn.toolTip()
    finally:
        win.close()


def test_many_classes_keep_the_panel_unscrolled(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.resize(1400, 900)
        win._apply_class_registry(C.ClassRegistry(
            [C.LabelClass(3 + i, f"아주 긴 카테고리 이름 {i}", "area", "#3C8CFF")
             for i in range(20)]), "ok")
        scroll = win.findChild(QScrollArea)
        content = scroll.widget()
        narrowest = scroll.parentWidget().minimumWidth()
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            for idx in (BRUSH, SAM):
                win._tool_picker.setCurrentIndex(idx)
                for _ in range(10):
                    QApplication.processEvents()
                assert not scroll.verticalScrollBar().isVisible(), (code, idx)
                assert content.minimumSizeHint().width() <= narrowest, (code, idx)
    finally:
        i18n.set_language("ko")
        win.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_side_panel.py -q -p no:cacheprovider -k "picker or number_keys or crack_line or add_button or many_classes"`
Expected: FAIL（`AttributeError: ... '_class_picker_brush'`）

- [ ] **Step 3: 实现 ClassPicker** `labeling_tool/core/window/class_picker.py`

```python
"""Class picker for the brush and SAM pages: a drop-down of the damage
classes (colour swatch, number key, name) and a "+" to add one."""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget,
)

from labeling_tool.ui import icons


def _swatch(rgb: tuple[int, int, int]) -> QIcon:
    pm = QPixmap(12, 12)
    pm.fill(QColor(*rgb))
    return QIcon(pm)


class ClassPicker(QWidget):
    classChosen = pyqtSignal(int)
    addRequested = pyqtSignal()

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label_text)
        self.combo = QComboBox()
        self.combo.setIconSize(QSize(12, 12))
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Long user names must not widen the 340 px panel.
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(8)
        self.add_button = QToolButton()
        self.add_button.setIcon(icons.icon("plus"))
        lay.addWidget(self.label)
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.add_button)
        self.combo.currentIndexChanged.connect(self._on_index)
        self.add_button.clicked.connect(self.addRequested)

    def set_classes(self, entries, current: int, disabled=frozenset()) -> None:
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            for i, (cid, name, rgb) in enumerate(entries):
                text = f"{i + 1}  {name}" if i < 9 else f"    {name}"
                self.combo.addItem(_swatch(rgb), text, cid)
                if cid in disabled:
                    self.combo.model().item(i).setEnabled(False)
            self.combo.setCurrentIndex(max(0, self.combo.findData(current)))
        finally:
            self.combo.blockSignals(False)

    def set_current(self, cid: int) -> None:
        idx = self.combo.findData(cid)
        if idx >= 0 and idx != self.combo.currentIndex():
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(idx)
            self.combo.blockSignals(False)

    def current_class(self) -> int:
        return int(self.combo.currentData())

    def set_add_enabled(self, enabled: bool, tip: str) -> None:
        self.add_button.setEnabled(enabled)
        self.add_button.setToolTip(tip)

    def retranslate(self, label: str) -> None:
        self.label.setText(label)

    def _on_index(self, idx: int) -> None:
        if idx >= 0:
            self.classChosen.emit(int(self.combo.itemData(idx)))
```

图标库（`labeling_tool/resources/icons/`，Lucide）里没有 `plus`，新建 `labeling_tool/resources/icons/plus.svg`，格式照抄同目录的 `x.svg`，只把路径换成 Lucide plus 的两条：`<path d="M5 12h14" />` 和 `<path d="M12 5v14" />`。（打包时整个 icons 目录都会带上，不需要改 spec 文件；可用 `grep -rn "resources/icons\|icons/" packaging/*.spec` 确认。）

- [ ] **Step 4: 接入 ui_builder**。在 `_build_brush_options` 里删掉整段 `cat_row`（`_btn_cat_crack`、`_btn_cat_spalling`、`_cat_group`），换成：

```python
    window._class_picker_brush = ClassPicker(window.tr_("lbl_class"))
    window._class_picker_brush.classChosen.connect(window._set_current_class)
    window._class_picker_brush.addRequested.connect(window._on_add_class)
    lay.addWidget(window._class_picker_brush)
```

在 `_build_sam_options` 开头加同样一段（变量名 `_class_picker_sam`）。文件顶部 `from labeling_tool.core.window.class_picker import ClassPicker`。

- [ ] **Step 5: 窗口逻辑**（`labeling_tool/core/window/main_window.py`）

删除 `_on_category_changed`、`_select_category_btn`，以及 `_retranslate_ui` 里两行 `_btn_cat_*.setText`；import 里去掉 `CATEGORIES, DEFAULT_CATEGORY`。实现：

```python
    def _refresh_class_pickers(self) -> None:
        if not hasattr(self, "_class_picker_brush"):
            return                      # called while the panel is being built
        reg = self.class_registry
        cur = self.canvas.current_class_id
        if cur not in reg:
            cur = self.canvas.current_class_id = CRACK_ID
        entries = [(c.class_id, reg.display_name(c.class_id, self.tr_), c.rgb)
                   for c in reg.classes()]
        # unknown ids found in this photo cannot be chosen; they are listed
        # nowhere and only shown grey on the canvas
        ok, tip = self._can_add_class()
        for picker, disabled in ((self._class_picker_brush, frozenset()),
                                 (self._class_picker_sam, frozenset({CRACK_ID}))):
            shown = cur if cur not in disabled else SPALLING_ID
            picker.set_classes(entries, shown, disabled)
            picker.set_add_enabled(ok, tip)
            picker.retranslate(self.tr_("lbl_class"))

    def _set_current_class(self, cid: int) -> None:
        reg = self.class_registry
        if cid not in reg:
            return
        if self.canvas.sam_mode and not reg.is_area(cid):
            cid = SPALLING_ID                      # SAM selects areas only
        self.canvas.current_class_id = cid
        for picker in (self._class_picker_brush, self._class_picker_sam):
            picker.set_current(cid)
        self.canvas.update()
        self.status.showMessage(self.tr_(
            "status_category_changed", cat=reg.display_name(cid, self.tr_)))

    def _select_class_by_index(self, i: int) -> None:
        classes = self.class_registry.classes()
        if 0 <= i < len(classes):
            self._set_current_class(classes[i].class_id)

    def _can_add_class(self) -> tuple[bool, str]:
        return False, self.tr_("class_add_unavailable")

    def _on_add_class(self) -> None:
        """Adding needs the server (Viewer window)."""
```

在 `_on_sam_toggle` 的 `if checked:` 块里（关掉其他模式之后）加：

```python
            if not self.class_registry.is_area(self.canvas.current_class_id):
                self._set_current_class(SPALLING_ID)
```

`_retranslate_ui` 里加一行 `self._refresh_class_pickers()`。在 `_build_ui()` 完成之后、`__init__` 里调用一次 `self._refresh_class_pickers()`（Task 7 已有 `set_class_registry` 那行之后）。

- [ ] **Step 6: 快捷键与样式**。`labeling_tool/core/window/shortcuts.py`：删除 `"1"` / `"2"` 两个 `QShortcut`，加

```python
    for n in range(1, 10):
        QShortcut(QKeySequence(str(n)), window,
                  lambda n=n: window._select_class_by_index(n - 1))
```

docstring 里的「A/D/S/B/[ /]/1/2」改为「A/D/S/B/[ /]/1-9」。`styles.py`：删除 `QPushButton#catCrack:checked` 与 `QPushButton#catSpalling:checked` 两段。

- [ ] **Step 7: 删除兼容属性**。`image_canvas.py` 删掉 Task 6 加的 `current_category` 属性；`test_canvas_classes.py` 删掉 `test_current_category_compat_property`；`grep -rn "current_category\|CATEGORIES\|DEFAULT_CATEGORY\|_btn_cat_\|_cat_group" labeling_tool tests annotation_tool` 应无结果（`constants.py` 里两行一并删除）。

- [ ] **Step 8: 文案**。先在 `docs/i18n-glossary.md` 第 3 节加一行：

```
| damage class | **카테고리** (균열 · 박리 · 사용자 추가) | 类别 | Class | 下拉框 + 「+」；数字键 1～9；新类别名称原样显示不翻译；SAM 只能选面状类别 |
```

三种语言新增 / 修改的键：

| key | ko | zh | en |
|---|---|---|---|
| `lbl_class` | `카테고리` | `类别` | `Class` |
| `class_add_unavailable` | `카테고리 추가는 서버 연결이 필요합니다.` | `追加类别需要连接服务器。` | `Adding a class needs the server.` |
| `class_add_tip` | `카테고리 추가` | `追加类别` | `Add a class` |
| `class_add_unsupported` | `서버가 카테고리 추가를 지원하지 않습니다 (서버 업데이트 필요).` | `服务器不支持追加类别（需要升级服务器）。` | `The server cannot add classes yet (server update needed).` |
| `tool_sam_hint` | `좌클릭으로 포함, 우클릭으로 제외합니다. Enter 로 확정하면 선택한 카테고리로 기록됩니다. Ctrl+Z 는 마지막 포인트 취소, Esc 는 전체 취소입니다.` | `左键=加入、右键=排除；Enter 确认并写入所选类别；Ctrl+Z 撤回上一点，Esc 全部取消` | `Left-click includes, right-click excludes. Enter confirms it as the chosen class; Ctrl+Z undoes the last point, Esc clears all.` |
| `sam_hint` | `좌클릭=포함, 우클릭=제외; Enter=확정(선택한 카테고리로 기록); Ctrl+Z=마지막 포인트 취소; Esc=전체 취소` | `左键=加入、右键=排除;Enter 确认(写入所选类别);Ctrl+Z 撤回上一点;Esc 全部取消。` | `Left-click = include, right-click = exclude; Enter confirms (writes the chosen class); Ctrl+Z undoes the last point; Esc clears all.` |
| `sam_committed` | `SAM 영역을 선택한 카테고리로 기록했습니다.` | `已将 SAM 区域写入所选类别。` | `SAM region recorded as the chosen class.` |
| `sam_auto_committed` | `확정하지 않은 SAM 영역을 선택한 카테고리로 기록했습니다.` | `已将未确认的 SAM 区域写入所选类别。` | `Unconfirmed SAM selection recorded as the chosen class.` |
| `hint_text` 第一、二行 | `브러시  왼쪽=그리기 · 오른쪽=지우기 · 1~9=카테고리` / `        B=토글 · [ / ]=크기` | `画笔   左键拖拽=绘制 · 右键拖拽=擦除 · 1~9=类别` / `       B=切换 · [ / ]=笔大小` | `Brush   L-drag paint · R-drag erase · 1-9 class` / `        B toggle · [ / ] size` |
| `btn_sam`（隐藏按钮） | `SAM 분할` | `SAM 分割` | `SAM select` |

`tool_sam_hint` 每种语言写完后跑 `test_tool_pages_are_never_squeezed_in_a_900px_window` 和 `test_no_tool_makes_the_panel_scroll_in_a_900px_window`；若 SAM 页超高，缩短文字（例如韩语去掉「입니다」），不要加宽面板。

- [ ] **Step 9: 跑测试确认通过**

Run: 完整三目录命令。Expected: 全绿（包括所有面板尺寸测试与 i18n 覆盖测试）。

- [ ] **Step 10: 截图检查**：用 offscreen 把 브러시 / SAM 页在 ko、zh、en 下截图（参照 `test_side_panel._make_window`，先 `_apply_class_registry` 放 3 个用户类别，处理事件 10 轮后 `win._grp_tools.grab().save(...)`，存到 scratchpad），确认下拉框、色块、「+」没有被截断。

- [ ] **Step 11: Commit**

```bash
git add -A labeling_tool docs/i18n-glossary.md
git commit -m "feat(ui): class picker on the brush and SAM pages; keys 1-9

Replaces the fixed crack/spalling buttons. SAM lists the crack line
but cannot use it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 追加类别对话框（V6）

**Files:**
- Create: `labeling_tool/ui/add_class_dialog.py`
- Modify: `labeling_tool/ui/main_window.py`（`_can_add_class`、`_on_add_class`）
- Modify: i18n 三个文件
- Test: `labeling_tool/tests/test_add_class.py`（新）

**Interfaces:**
- Consumes: Task 2 `add_class_and_cache`、`SYNC_OK`、`SYNC_UNSUPPORTED`；Task 1 `pick_color`；Task 8 `_set_current_class`、`_can_add_class`、`_apply_class_registry`
- Produces:
  - `AddClassDialog(QDialog)`：`__init__(color: str, tr, parent=None)`；`name() -> str`、`color() -> str`；子控件 `name_edit: QLineEdit`、`color_button: QPushButton`、`buttons: QDialogButtonBox`（OK 在名称为空时禁用）
  - `ViewerMainWindow._can_add_class()`：client 为 None → `(False, class_add_unavailable)`；状态 `unsupported` → `(False, class_add_unsupported)`；状态 `ok` → `(True, class_add_tip)`；`offline` → `(False, class_add_unavailable)`
  - `ViewerMainWindow._ask_new_class() -> tuple[str, str] | None`（弹对话框；测试里 monkeypatch）

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_add_class.py`

```python
import pytest
import requests
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from labeling_tool.api.errors import ViewerApiError
from labeling_tool.core import classes as C
from labeling_tool.core import i18n
from labeling_tool.tests.test_side_panel import BRUSH, _make_window

_app = QApplication.instance() or QApplication([])


class _Client:
    base_url = "https://viewer.example.com"

    def __init__(self, added=None, error=None):
        self.added, self.error, self.calls = added, error, []

    def add_class(self, name, color):
        self.calls.append((name, color))
        if self.error:
            raise self.error
        return self.added

    def list_classes(self):
        return C.ClassRegistry().to_payload()


def _online(win, client):
    win._client = client
    win._apply_class_registry(C.ClassRegistry(), "ok")


def test_dialog_needs_a_name():
    from labeling_tool.ui.add_class_dialog import AddClassDialog
    d = AddClassDialog("#3C8CFF", i18n.tr)
    ok = d.buttons.button(QDialogButtonBox.Ok)
    assert not ok.isEnabled()
    d.name_edit.setText("  백태 ")
    assert ok.isEnabled() and d.name() == "백태" and d.color() == "#3C8CFF"
    d.name_edit.setText("   ")
    assert not ok.isEnabled()


def test_adding_a_class_selects_it(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client(added={"classId": 3, "name": "백태", "kind": "area",
                                "color": "#3C8CFF", "builtin": False})
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("백태", "#3C8CFF"))
        win._on_add_class()
        assert client.calls == [("백태", "#3C8CFF")]
        assert win.class_registry.ids() == [1, 2, 3]
        assert win.canvas.current_class_id == 3
        assert win._class_picker_brush.current_class() == 3
    finally:
        win.close()


def test_adding_an_existing_name_selects_the_existing_class(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client(added={"classId": 2, "name": "spalling", "kind": "area",
                                "color": "#3CE63C", "builtin": True})
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("Spalling", "#3C8CFF"))
        win._on_add_class()
        assert win.class_registry.ids() == [1, 2]
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


@pytest.mark.parametrize("error", [
    requests.ConnectionError("down"),
    ViewerApiError("CLASS_LIMIT_EXCEEDED", "full", 409),
])
def test_a_failed_add_shows_why_and_changes_nothing(tmp_path, monkeypatch, error):
    win = _make_window(tmp_path, monkeypatch)
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    try:
        _online(win, _Client(error=error))
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("백태", "#3C8CFF"))
        win._on_add_class()
        assert win.class_registry.ids() == [1, 2] and shown
    finally:
        win.close()


def test_cancel_does_nothing(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client()
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: None)
        win._on_add_class()
        assert client.calls == []
    finally:
        win.close()


def test_add_button_state_follows_the_server(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        btn = win._class_picker_brush.add_button
        win._client = _Client()
        win._apply_class_registry(C.ClassRegistry(), "unsupported")
        assert not btn.isEnabled() and btn.toolTip() == i18n.tr("class_add_unsupported")
        win._apply_class_registry(C.ClassRegistry(), "ok")
        assert btn.isEnabled()
    finally:
        win.close()
```

注意 `_make_window` 里 `QMessageBox.warning` 已被 monkeypatch 成 no-op；上面的失败用例在调用 `_make_window` **之后**再 monkeypatch 一次以收集提示文字。

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_add_class.py -q -p no:cacheprovider`
Expected: FAIL（`ModuleNotFoundError: labeling_tool.ui.add_class_dialog`）

- [ ] **Step 3: 实现对话框** `labeling_tool/ui/add_class_dialog.py`

```python
"""Ask for a new damage class: a name and a colour (pre-picked)."""

from __future__ import annotations

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QPushButton,
)

MAX_NAME_LEN = 50


class AddClassDialog(QDialog):
    def __init__(self, color: str, tr, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("class_add_title"))
        self._color = color
        form = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_NAME_LEN)
        self.name_edit.setPlaceholderText(tr("class_add_name_hint"))
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        self._show_color()
        form.addRow(tr("class_add_name"), self.name_edit)
        form.addRow(tr("class_add_color"), self.color_button)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.name_edit.textChanged.connect(self._update_ok)
        self._update_ok()

    def name(self) -> str:
        return self.name_edit.text().strip()

    def color(self) -> str:
        return self._color

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self.name()))

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self)
        if chosen.isValid():
            self._color = chosen.name().upper()
            self._show_color()

    def _show_color(self) -> None:
        self.color_button.setText(self._color)
        self.color_button.setStyleSheet(
            f"background-color: {self._color}; color: #101010;")
```

- [ ] **Step 4: Viewer 窗口**（`labeling_tool/ui/main_window.py`）

```python
    def _can_add_class(self) -> tuple[bool, str]:
        from labeling_tool.api.class_sync import SYNC_OK, SYNC_UNSUPPORTED
        if self._client is None:
            return False, self.tr_("class_add_unavailable")
        if self._class_sync_status == SYNC_UNSUPPORTED:
            return False, self.tr_("class_add_unsupported")
        if self._class_sync_status != SYNC_OK:
            return False, self.tr_("class_add_unavailable")
        return True, self.tr_("class_add_tip")

    def _ask_new_class(self) -> tuple[str, str] | None:
        from labeling_tool.core.classes import pick_color
        from labeling_tool.ui.add_class_dialog import AddClassDialog
        dlg = AddClassDialog(pick_color(self.class_registry), self.tr_, self)
        if dlg.exec_() != dlg.Accepted:
            return None
        return dlg.name(), dlg.color()

    def _on_add_class(self) -> None:
        import requests
        from labeling_tool.api.class_sync import add_class_and_cache
        from labeling_tool.api.errors import ViewerApiError
        ok, _tip = self._can_add_class()
        if not ok:
            return
        answer = self._ask_new_class()
        if answer is None:
            return
        name, color = answer
        try:
            registry, cls = add_class_and_cache(
                self._client, self._class_base_url(), self.class_registry, name, color)
        except (ViewerApiError, requests.RequestException, ValueError) as e:
            key = ("class_add_full" if getattr(e, "code", "") == "CLASS_LIMIT_EXCEEDED"
                   else "class_add_failed")
            QMessageBox.warning(self, self.tr_("class_add_title"),
                                self.tr_(key, error=str(e)))
            return
        self._apply_class_registry(registry, self._class_sync_status)
        self._set_current_class(cls.class_id)
```

- [ ] **Step 5: 文案**（三种语言都加）

| key | ko | zh | en |
|---|---|---|---|
| `class_add_title` | `카테고리 추가` | `追加类别` | `Add a class` |
| `class_add_name` | `이름` | `名称` | `Name` |
| `class_add_name_hint` | `예: 백태, 누수` | `例如：白华、渗水` | `e.g. efflorescence, leak` |
| `class_add_color` | `색` | `颜色` | `Colour` |
| `class_add_failed` | `카테고리를 추가하지 못했습니다.\n{error}` | `未能追加类别。\n{error}` | `Could not add the class.\n{error}` |
| `class_add_full` | `카테고리를 더 추가할 수 없습니다 (최대 252개).` | `无法再追加类别（最多 252 个）。` | `No more classes can be added (252 at most).` |

（`class_add_full` 没有 `{error}` 占位符，`tr_` 多给的关键字参数会被忽略——先确认 `labeling_tool/core/i18n/__init__.py` 的 `tr` 用 `str.format(**kw)`，多余参数无害；若不是，调用处对 `class_add_full` 不传 `error`。）

- [ ] **Step 6: 跑测试确认通过**

Run: 完整三目录命令。Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add labeling_tool/ui/add_class_dialog.py labeling_tool/ui/main_window.py labeling_tool/core/i18n labeling_tool/tests/test_add_class.py
git commit -m "feat(ui): add a damage class from the labeling window (V6)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 按 S / Ctrl+S 保存时自动确认

**Files:**
- Modify: `labeling_tool/core/window/main_window.py:_on_brush_save`
- Test: `labeling_tool/tests/test_side_panel.py`（追加）

**Interfaces:**
- Consumes: 0.2.17 已有的 `_confirm_pending_edits() -> str | None`
- Produces: `_on_brush_save()` 先确认再保存，有自动确认时状态栏显示该提示（覆盖「저장 완료」）

- [ ] **Step 1: 写失败测试**，追加到 `labeling_tool/tests/test_side_panel.py`：

```python
def test_s_saves_an_unconfirmed_sam_selection(tmp_path, monkeypatch):
    import cv2
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from labeling_tool.session import mask_store
    win = _make_window(tmp_path, monkeypatch)
    try:
        _sam_with_points(win, (2, 2, 1))
        win.activateWindow()
        QTest.keyClick(win.canvas, Qt.Key_S)
        QApplication.processEvents()
        assert not win.canvas.has_sam_preview()
        saved = cv2.imread(str(win.output_dir / mask_store.mask_name(_FILES[0])),
                           cv2.IMREAD_UNCHANGED)
        assert saved is not None and (saved == 2).any()
        assert win.status.currentMessage() == i18n.tr("sam_auto_committed")
    finally:
        win.close()


def test_ctrl_s_confirms_repair_area_points(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BBOX)
        QApplication.processEvents()
        c = win.canvas
        c.bbox_interaction.on_left_press(1, 1)
        c.bbox_interaction.on_left_press(6, 6)
        _ctrl(win, Qt.Key_S)
        assert len(c.bbox_interaction.boxes) == 1 and not c.bbox_interaction.in_progress_clicks
    finally:
        win.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_side_panel.py -q -p no:cacheprovider -k "s_saves or ctrl_s_confirms"`
Expected: FAIL（预览还在 / 框数为 0）

- [ ] **Step 3: 实现**

```python
    def _on_brush_save(self):
        """S / Ctrl+S / the save button: what is still unconfirmed (a SAM
        selection, repair-area points) is confirmed first, then saved."""
        notice = (self._confirm_pending_edits()
                  if 0 <= self.current_idx < len(self.image_files) else None)
        self._save_all_artifacts(silent=False)
        if notice:
            self.status.showMessage(notice)
```

- [ ] **Step 4: 跑测试确认通过**；完整三目录命令全绿。

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/core/window/main_window.py labeling_tool/tests/test_side_panel.py
git commit -m "feat(ui): S confirms an unconfirmed SAM selection or repair area, then saves

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: 收尾：文档、全量检查、截图

**Files:**
- Modify: `docs/superpowers/specs/2026-10-13-user-classes-design.md`（同步时机按实现改：标注窗口打开时 + 上传前；不在作业列表页同步）
- Modify: `CLAUDE.md`（若项目根有，补一句类别模块位置）——先 `ls CLAUDE.md`，没有则跳过

- [ ] **Step 1: 规格同步**：把设计文档 4.1 的「同步时机：作业列表页打开时、标注窗口打开时」改为「标注窗口打开时（后台线程，先用缓存）、上传前（upload worker 内再同步一次）」。
- [ ] **Step 2: 残留检查**：

```bash
grep -rn "cat_crack\|cat_spalling" labeling_tool --include=*.py | grep -v i18n/strings
grep -rn "박리로 기록\|写入剥落\|as spalling" labeling_tool/core/i18n
```

第一条只应出现在 `core/classes.py` 的 `_BUILTIN_I18N`；第二条应无结果（全部改成「선택한 카테고리」）。
- [ ] **Step 3: 全量测试**：完整三目录命令，记录通过数。
- [ ] **Step 4: 应用冒烟**：`QT_QPA_PLATFORM=offscreen timeout 8 .venv/bin/python -m labeling_tool.app; [ $? = 124 ] && echo OK`
- [ ] **Step 5: 截图**：ko 下 브러시 页、SAM 页（带 3 个用户类别、下拉展开前）、追加对话框，各存 scratchpad，人工看一遍。
- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-10-13-user-classes-design.md
git commit -m "docs: class sync happens on window open and before upload

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
