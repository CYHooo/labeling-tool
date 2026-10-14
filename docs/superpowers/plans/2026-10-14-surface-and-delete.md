# 拍摄面修改与照片删除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 标注窗口显示并可修改每张照片的拍摄面（바닥 / 벽 / 천장），可在图片列表里逐行标记删除；上传时把 `surfaceUpdates` / `deletes` 和原有 `items` 一起放进 V4，成功后本地移除已删照片并刷新编号。

**Architecture:** manifest 的 `PhotoEntry` 增加服务器字段（`surface`、`tilt_deg`、`tilt_source`）和本地待上传状态（`surface_edit`、`delete_pending`）；纯函数模块 `session/photo_edits.py` 负责读写这些状态并收集上传列表；字段名和每批上限集中在 `api/edit_fields.py`（服务器文档到达后只改这里）；`api/uploader.upload_session` 扩展为带 `surface_updates` / `deletes` 的批次；窗口层负责列表绘制（「면」列 + 每行删除按钮）、侧边栏拍摄面一行、上传确认框、上传后本地删除与后台刷新。

**Tech Stack:** Python 3.12, PyQt5, requests, pytest（offscreen Qt）。

**Spec:** `docs/superpowers/specs/2026-10-14-surface-and-delete-design.md`

## Global Constraints

- **开工前置条件：服务器新版 API 文档到达并核对 spec §7 的 5 项。** 文档与本计划不符时，以文档为准改 `api/edit_fields.py` 和受影响的测试，并在进度账本记 Ruling。
- 测试命令（每个任务结束必须全绿）：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`（当前 1012 passed）。
- 拍摄面取值：`floor` / `wall` / `ceiling`；其他值（含 `None`、未知字符串）一律按「모름」显示、不可回传。工具内**不判定**拍摄面。
- 只改了拍摄面 / 只标记删除的照片**不重新上传图片**；只有改了掩码的照片进 `items`。
- 删除不可恢复：上传前必须确认；取消确认 = 整个上传不进行。
- `deleted` 和 `skipped` 里的照片都视为已删除，本地移除，不报错。
- 侧边栏最小宽度 340 px；900 px 高窗口、ko / zh / en、任何工具都不出现滚动条。缩短文字，不加宽面板。
- 所有用户可见文字走 i18n，先改 `docs/i18n-glossary.md`；韩语正式；英文用词以术语表为准（카테고리 = Category 等）。
- 测试不在仓库里写文件（工作区放 `tmp_path`）。
- 代码注释英文；Commit：conventional commits，末尾 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`；分支 `feat/surface-and-delete`。

## Review Focus

1. **当前照片被删除**：上传后正在显示的照片被删 → 跳到相邻照片；全部删光 → 画面清空、上传按钮不可用（Task 7 测试）。
2. **上传中断后重试**：第一批成功、第二批失败 → 第一批的删除已在本地移除，第二批的删除仍是「삭제 예정」，再次上传只发剩下的（Task 5、7 测试）。
3. **范围视图 + 删除**：范围内照片被删、编号前移 → 范围视图仍是原来那些照片（按 timestamp），不会混入范围外照片（Task 7 测试）。
4. **标记删除又改了掩码 / 拍摄面**：只发 `deletes`，不发 `items` / `surfaceUpdates`（Task 2、5 测试）。
5. **服务器返回未知拍摄面值**（例如 `slope`）：显示「모름」，按钮都不亮，不会被当作修改回传（Task 2、4 测试）。

---

## File Structure

| 文件 | 职责 | 任务 |
|---|---|---|
| `labeling_tool/api/edit_fields.py`（新） | 字段名、合法拍摄面、每批上限、响应解析 | 1 |
| `labeling_tool/session/manifest.py` | `PhotoEntry` 新字段、`keep_from`、`remove` | 1 |
| `labeling_tool/ui/fetch_dialog.py` | 获取作业时写入服务器字段 | 1 |
| `labeling_tool/session/photo_edits.py`（新） | 显示值、修改 / 撤销、标记删除、收集上传列表 | 2 |
| `labeling_tool/session/workspace.py` | `remove_photo_files(filename)` | 3 |
| `labeling_tool/core/window/ui_builder.py` | 列表委托：「면」列、删除按钮、删除样式；表头 | 4 |
| `labeling_tool/core/window/surface_row.py`（新）+ `ui_builder.build_display_group` | 侧边栏拍摄面一行 | 4 |
| `labeling_tool/api/uploader.py`、`labeling_tool/ui/upload_worker.py` | 带 `surfaceUpdates` / `deletes` 的批次与结果 | 5 |
| `labeling_tool/ui/main_window.py` | 列表 / 侧边栏接线、上传条件与确认框、上传后删除与刷新 | 6、7 |
| `labeling_tool/ui/photo_refresh_worker.py`（新） | 后台取照片列表数据 | 7 |
| i18n 三个文件、`docs/i18n-glossary.md`、README | 文案 | 4、6、8 |

---

### Task 1: 字段常量、manifest 新字段、获取作业写入

**Files:**
- Create: `labeling_tool/api/edit_fields.py`
- Modify: `labeling_tool/session/manifest.py`
- Modify: `labeling_tool/ui/fetch_dialog.py`（创建 `PhotoEntry` 处，约 277 行）
- Test: `labeling_tool/tests/test_edit_fields.py`（新）、`labeling_tool/tests/test_manifest.py`（若不存在则新建；先 `ls labeling_tool/tests | grep -i manifest`）

**Interfaces:**
- Produces:
  - `edit_fields.SURFACES = ("floor", "wall", "ceiling")`
  - `edit_fields.SURFACE_UPDATES_KEY = "surfaceUpdates"`、`DELETES_KEY = "deletes"`、`DELETED_KEY = "deleted"`、`SKIPPED_KEY = "skipped"`
  - `edit_fields.EDIT_LIST_LIMIT = 100`（每个 V4 请求里 `surfaceUpdates` / `deletes` 各自的最大条数）
  - `edit_fields.normalize_surface(value) -> str | None`（合法值原样，其它 → `None`）
  - `edit_fields.photo_fields(p: dict) -> dict`：从照片列表项取 `{"surface", "tilt_deg", "tilt_source"}`
  - `edit_fields.timestamps_in(response: dict, key: str) -> list[int]`：从 V4 响应取 `deleted` / `skipped`，接受 `[ts, ...]` 或 `[{"timestamp": ts}, ...]`，缺失或格式不对 → `[]`
  - `PhotoEntry` 新字段（全部有默认值）：`surface: str | None = None`、`tilt_deg: float | None = None`、`tilt_source: str | None = None`、`surface_edit: str | None = None`、`delete_pending: bool = False`
  - `Manifest.remove(filename) -> None`

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_edit_fields.py`

```python
import pytest

from labeling_tool.api import edit_fields as F


@pytest.mark.parametrize("value, expected", [
    ("floor", "floor"), ("wall", "wall"), ("ceiling", "ceiling"),
    (None, None), ("slope", None), ("", None), (3, None),
])
def test_normalize_surface(value, expected):
    assert F.normalize_surface(value) == expected


def test_photo_fields_reads_the_three_server_values():
    assert F.photo_fields({"surface": "wall", "tiltDeg": 87.4, "tiltSource": "sensor"}) == {
        "surface": "wall", "tilt_deg": 87.4, "tilt_source": "sensor"}
    assert F.photo_fields({}) == {"surface": None, "tilt_deg": None, "tilt_source": None}
    assert F.photo_fields({"surface": "slope", "tiltDeg": "x"}) == {
        "surface": None, "tilt_deg": None, "tilt_source": None}


@pytest.mark.parametrize("body, expected", [
    ({"deleted": [1, 2]}, [1, 2]),
    ({"deleted": [{"timestamp": 1}, {"timestamp": 2}]}, [1, 2]),
    ({}, []), ({"deleted": None}, []), ({"deleted": "x"}, []), ("oops", []),
])
def test_timestamps_in(body, expected):
    assert F.timestamps_in(body, F.DELETED_KEY) == expected
```

追加到 manifest 测试：

```python
from labeling_tool.session.manifest import Manifest, PhotoEntry


def _entry(fn="a.jpg", ts=1, num=1, **kw):
    return PhotoEntry(filename=fn, timestamp=ts, photo_id=ts, report_photo_num=num,
                      px_per_cm=2.0, **kw)


def test_new_fields_have_defaults_and_round_trip(tmp_path):
    m = Manifest(session_id=1, base="")
    m.add(_entry(surface="wall", tilt_deg=87.0, tilt_source="sensor",
                 surface_edit="floor", delete_pending=True))
    m.save(tmp_path / "m.json")
    e = Manifest.load(tmp_path / "m.json").get("a.jpg")
    assert (e.surface, e.tilt_deg, e.tilt_source, e.surface_edit, e.delete_pending) == (
        "wall", 87.0, "sensor", "floor", True)


def test_an_old_manifest_loads(tmp_path):
    import json
    (tmp_path / "m.json").write_text(json.dumps({"sessionId": 1, "base": "", "photos": {
        "a.jpg": {"filename": "a.jpg", "timestamp": 1, "photo_id": 1,
                  "report_photo_num": 1, "px_per_cm": 2.0}}}), encoding="utf-8")
    e = Manifest.load(tmp_path / "m.json").get("a.jpg")
    assert e.surface is None and e.surface_edit is None and e.delete_pending is False


def test_refetch_keeps_local_edits_and_takes_new_server_values():
    old = Manifest(session_id=1, base="")
    old.add(_entry(surface="wall", surface_edit="floor", delete_pending=True))
    new = Manifest(session_id=1, base="")
    new.add(_entry(surface="ceiling", tilt_deg=170.0))
    new.keep_from(old)
    e = new.get("a.jpg")
    assert e.surface == "ceiling" and e.tilt_deg == 170.0
    assert e.surface_edit == "floor" and e.delete_pending is True


def test_remove():
    m = Manifest(session_id=1, base="")
    m.add(_entry())
    m.remove("a.jpg")
    m.remove("a.jpg")                     # absent: no error
    assert m.filenames_in_order() == []
```

- [ ] **Step 2: 跑测试确认失败**（`ModuleNotFoundError: edit_fields` / `unexpected keyword 'surface'`）

- [ ] **Step 3: 实现** `labeling_tool/api/edit_fields.py`

```python
"""Field names and limits of the photo-edit additions to the Viewer API
(surface per photo, surface updates and deletes in register-annotations).

Kept in one place: the server document was still on its way when this was
written, so a renamed field or a different limit is a one-line change here.
"""

from __future__ import annotations

SURFACES = ("floor", "wall", "ceiling")

SURFACE_UPDATES_KEY = "surfaceUpdates"
DELETES_KEY = "deletes"
DELETED_KEY = "deleted"
SKIPPED_KEY = "skipped"

# Most surfaceUpdates / deletes entries in one register-annotations call.
EDIT_LIST_LIMIT = 100


def normalize_surface(value) -> str | None:
    """A known surface, or None for unknown / missing values."""
    return value if isinstance(value, str) and value in SURFACES else None


def _float_or_none(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def photo_fields(p: dict) -> dict:
    """The surface fields of one photo-list entry, as PhotoEntry fields."""
    source = p.get("tiltSource")
    return {"surface": normalize_surface(p.get("surface")),
            "tilt_deg": _float_or_none(p.get("tiltDeg")),
            "tilt_source": source if isinstance(source, str) and source else None}


def timestamps_in(response, key: str) -> list[int]:
    """Timestamps listed under `key` in a register response: plain ints or
    {"timestamp": ...} objects; anything else gives []."""
    if not isinstance(response, dict):
        return []
    raw = response.get(key)
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        ts = item.get("timestamp") if isinstance(item, dict) else item
        if isinstance(ts, int) and not isinstance(ts, bool):
            out.append(ts)
    return out
```

`manifest.py`：`PhotoEntry` 末尾追加五个字段（类型和默认值如 Interfaces）；`Manifest` 加

```python
    def remove(self, filename: str) -> None:
        self.photos.pop(filename, None)
```

`keep_from` 里 `entry is not None` 分支追加两行：

```python
                entry.surface_edit = old.surface_edit
                entry.delete_pending = old.delete_pending
```

（`load` 用 `PhotoEntry(**d)`，新字段有默认值，旧文件可读；若 d 里出现未知键会报错——维持现状。）

`fetch_dialog.py` 的 `manifest.add(PhotoEntry(...))` 增加 `**photo_fields(p)`（`from labeling_tool.api.edit_fields import photo_fields`）。

- [ ] **Step 4: 跑测试确认通过**；完整三目录命令全绿。
- [ ] **Step 5: Commit** `feat(session): surface fields and pending deletes in the manifest`

---

### Task 2: 本地编辑状态 `session/photo_edits.py`

**Files:**
- Create: `labeling_tool/session/photo_edits.py`
- Test: `labeling_tool/tests/test_photo_edits.py`

**Interfaces:**
- Consumes: Task 1 `PhotoEntry` 字段、`SURFACES`、`normalize_surface`
- Produces:
  - `shown_surface(entry) -> str | None`（`surface_edit` 优先，再 `surface`；都经 `normalize_surface`）
  - `set_surface(entry, value: str) -> bool`：`value` 必须在 `SURFACES`（否则 `ValueError`）；等于服务器值 → `surface_edit = None`；否则 `surface_edit = value`；返回状态是否改变
  - `toggle_delete(entry) -> bool`：翻转 `delete_pending`，返回新值
  - `has_pending_edit(entry) -> bool`：`surface_edit is not None or delete_pending`
  - `surface_updates(entries) -> list[dict]`：`[{"timestamp", "surface"}]`，`surface_edit` 非空且未标记删除，按 timestamp 升序
  - `deletes(entries) -> list[dict]`：`[{"timestamp"}]`，按 timestamp 升序

- [ ] **Step 1: 写失败测试**

```python
import pytest

from labeling_tool.session import photo_edits as E
from labeling_tool.session.manifest import PhotoEntry


def _e(ts=1, surface=None, **kw):
    return PhotoEntry(filename=f"{ts}.jpg", timestamp=ts, photo_id=ts,
                      report_photo_num=ts, px_per_cm=2.0, surface=surface, **kw)


def test_shown_surface_prefers_the_local_edit():
    assert E.shown_surface(_e(surface="wall")) == "wall"
    assert E.shown_surface(_e(surface="wall", surface_edit="floor")) == "floor"
    assert E.shown_surface(_e(surface="slope")) is None


def test_set_surface_and_set_back_to_the_server_value():
    e = _e(surface="wall")
    assert E.set_surface(e, "floor") is True and e.surface_edit == "floor"
    assert E.set_surface(e, "floor") is False
    assert E.set_surface(e, "wall") is True and e.surface_edit is None


def test_set_surface_on_an_unknown_server_value_is_an_edit():
    e = _e(surface=None)
    assert E.set_surface(e, "ceiling") and e.surface_edit == "ceiling"


def test_set_surface_rejects_unknown_values():
    with pytest.raises(ValueError):
        E.set_surface(_e(), "slope")


def test_toggle_delete_and_pending():
    e = _e()
    assert not E.has_pending_edit(e)
    assert E.toggle_delete(e) is True and E.has_pending_edit(e)
    assert E.toggle_delete(e) is False and not E.has_pending_edit(e)


def test_upload_lists_skip_deleted_photos_and_sort():
    a = _e(3, surface="wall", surface_edit="floor")
    b = _e(1, surface="wall", surface_edit="ceiling", delete_pending=True)
    c = _e(2, delete_pending=True)
    assert E.surface_updates([a, b, c]) == [{"timestamp": 3, "surface": "floor"}]
    assert E.deletes([a, b, c]) == [{"timestamp": 1}, {"timestamp": 2}]
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**

```python
"""Local, not-yet-uploaded photo edits kept on the manifest entry: a changed
surface (floor / wall / ceiling) and a pending delete. The tool never works
out a surface itself; it shows the server's value or the user's choice."""

from __future__ import annotations

from labeling_tool.api.edit_fields import SURFACES, normalize_surface


def shown_surface(entry) -> str | None:
    if entry.surface_edit is not None:
        return normalize_surface(entry.surface_edit)
    return normalize_surface(entry.surface)


def set_surface(entry, value: str) -> bool:
    if value not in SURFACES:
        raise ValueError(f"unknown surface: {value!r}")
    new = None if value == normalize_surface(entry.surface) else value
    if new == entry.surface_edit:
        return False
    entry.surface_edit = new
    return True


def toggle_delete(entry) -> bool:
    entry.delete_pending = not entry.delete_pending
    return entry.delete_pending


def has_pending_edit(entry) -> bool:
    return entry.surface_edit is not None or bool(entry.delete_pending)


def surface_updates(entries) -> list[dict]:
    return [{"timestamp": int(e.timestamp), "surface": e.surface_edit}
            for e in sorted(entries, key=lambda e: e.timestamp)
            if e.surface_edit is not None and not e.delete_pending]


def deletes(entries) -> list[dict]:
    return [{"timestamp": int(e.timestamp)}
            for e in sorted(entries, key=lambda e: e.timestamp) if e.delete_pending]
```

- [ ] **Step 4: 测试通过；完整命令全绿。**
- [ ] **Step 5: Commit** `feat(session): pending surface changes and deletes per photo`

---

### Task 3: 删除本地照片文件 `Workspace.remove_photo_files`

**Files:**
- Modify: `labeling_tool/session/workspace.py`
- Test: `labeling_tool/tests/test_workspace_remove.py`（新）

**Interfaces:**
- Consumes: `labeling_tool/session/mask_store.py`（`mask_name(fn)`、`bbox_name(fn)`）、`naming.detected_mask_filename(ts)`；Result 文件名为 `<stem>.png` / `<stem>.txt`（见 `core/result/exporter.py`）
- Produces: `Workspace.remove_photo_files(filename: str, timestamp: int) -> list[Path]`（返回实际删掉的文件；不存在的跳过；单个文件删除失败记日志继续）

- [ ] **Step 1: 先确认文件名规则**：`grep -n "def " labeling_tool/session/mask_store.py labeling_tool/session/naming.py`，记下 Detected、Labeling（掩码 + bbox JSON）、HighLight、Repair15 的文件名函数。
- [ ] **Step 2: 写失败测试**：在 `tmp_path` 建 `Workspace(root=tmp_path, session_id=1)`，`ws.ensure()`，按上一步的命名在 Origin / Detected / Labeling（两个文件）/ HighLight / Repair15 / Result（png + txt）各放一个属于该照片的文件，再放一个**另一张照片**的文件；调用 `remove_photo_files` 后：该照片的 8 个文件都不存在、返回列表长度 8、另一张照片的文件还在；再调用一次返回 `[]`。
- [ ] **Step 3: 实现**（按 Step 1 的命名函数拼路径；`Path.unlink(missing_ok=True)` 前先 `exists()` 以便返回实际删除列表；`OSError` → `vlog().warning(...)` 继续）。
- [ ] **Step 4: 测试通过；完整命令全绿。**
- [ ] **Step 5: Commit** `feat(session): remove a deleted photo's files from the job folder`

---

### Task 4: 列表「면」列与逐行删除按钮；侧边栏拍摄面一行

**Files:**
- Modify: `labeling_tool/core/window/ui_builder.py`（`TwoPartItemDelegate`、`ListHeader`、`build_display_group`）
- Create: `labeling_tool/core/window/surface_row.py`
- Create: `labeling_tool/resources/icons/trash-2.svg`（Lucide，格式照 `x.svg`）
- Modify: i18n 三个文件、`docs/i18n-glossary.md`
- Test: `labeling_tool/tests/test_surface_ui.py`（新）

**Interfaces:**
- Produces（`ui_builder`）:
  - 新 item data role：`SURFACE_ROLE`（显示文字，如「벽」）、`SURFACE_EDITED_ROLE`（bool）、`DELETE_PENDING_ROLE`（bool）
  - `TwoPartItemDelegate`：`surface_width: int`（> 0 时在编号后画「면」列）、`delete_width: int`（> 0 时在行最右画删除图标）；信号载体 `delete_clicked = pyqtSignal(int)`（行号；委托继承 QObject 可直接声明）；`editorEvent` 中左键在删除图标区域按下时发 `delete_clicked(row)` 并返回 True（吞掉事件，不改变选中行）
  - 删除样式：`DELETE_PENDING_ROLE` 为真 → 文件名删除线、文字红色（`#e05a5a`，选中行仍白色），文件名后显示 `delete_pending_label`
  - `ListHeader.set_labels(number, surface, file)`：三列标题（surface 为空串时不画）；`column_offsets()` 返回三列 x
- Produces（`surface_row.py`）: `SurfaceRow(QWidget)`：
  - 子控件：`label`（「촬영면」）、`unknown`（「모름」，仅值为 None 时可见）、`buttons: dict[str, QPushButton]`（`floor` / `wall` / `ceiling`，可选中、互斥由代码控制）、`tilt`（灰字）
  - `set_value(surface: str | None, edited: bool, tilt_deg: float | None, tilt_source: str | None)`（不发信号）
  - 信号 `surfaceChosen = pyqtSignal(str)`（点击任一按钮）
  - `retranslate(tr)`
  - 窗口属性 `window._surface_row`，放在 `build_display_group` 的比例尺一行下面
- i18n 新键（ko / zh / en；先在术语表加「촬영면 / 拍摄面 / Surface」「바닥 / 地面 / Floor」「벽 / 墙面 / Wall」「천장 / 天花板 / Ceiling」「모름 / 未知 / Unknown」「삭제 예정 / 待删除 / To delete」）：
  `list_col_surface`（면 / 面 / Side）、`surface_label`（촬영면 / 拍摄面 / Surface）、`surface_floor`（바닥 / 地面 / Floor）、`surface_wall`（벽 / 墙面 / Wall）、`surface_ceiling`（천장 / 天花板 / Ceiling）、`surface_unknown`（모름 / 未知 / Unknown）、`surface_unknown_short`（? / ? / ?，列表列用）、`tilt_deg`（`{deg}°`，三语相同）、`tilt_none`（— 三语相同）、`tilt_manual_tip`（「수정된 값입니다」/「已人工修改」/「Corrected by hand」）、`delete_pending_label`（삭제 예정 / 待删除 / To delete）、`delete_toggle_tip`（「업로드할 때 서버에서 삭제합니다. 다시 누르면 취소」/「上传时在服务器删除，再点一次取消」/「Deleted on the server at upload; click again to undo」）
  （「면」列标题在英文用「Side」以免挤；若术语表另有决定，按术语表。）

- [ ] **Step 1: 写失败测试**（纯部件，不建主窗口）：
  - `SurfaceRow.set_value("wall", False, 87.4, "sensor")` → `buttons["wall"].isChecked()`，其余不选；`tilt.text() == "87°"`；`unknown` 不可见
  - `set_value(None, False, None, None)` → 三个都不选、`unknown` 可见、`tilt.text() == "—"`
  - `set_value("floor", True, 10.0, "manual")` → `floor` 选中、按钮有 `edited` 属性（QSS 琥珀色）、`tilt.toolTip()` 为 `tilt_manual_tip`
  - 点击 `buttons["ceiling"]` → `surfaceChosen` 收到 `"ceiling"`；`set_value` 不发信号
  - 委托：建一个 `QListWidget`（`resize(340, 200)`、`show()`），一项带 `SECONDARY_TEXT_ROLE` / `SURFACE_ROLE` / `DELETE_PENDING_ROLE`；`delegate.delete_width = 20`；用 `QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=<行右端-10, 行中点>)` → `delete_clicked` 收到行号且 `view.currentRow()` 不变；点行中部 → 不发信号
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（委托绘制顺序：mark → 编号 → 「면」列（`surface_width` 宽，改过用琥珀色 `#e0a040`）→ 文件名（剩余宽度减 `delete_width` 省略；删除样式）→ 删除图标（`icons.icon("trash-2")`，pending 时红色高亮）。`editorEvent` 用 `option.rect.right() - delete_width` 判断区域。`SurfaceRow` 按钮最小宽度适配 340 px 面板，`edited` 用动态属性 + `styles.py` 加 `QPushButton[edited="true"]:checked { background-color: #b07a20; }`。）
- [ ] **Step 4: 测试通过；完整命令全绿**（包括既有面板尺寸测试——此任务尚未接入主窗口，若 `build_display_group` 已加入 `SurfaceRow`，跑 `test_side_panel.py` 的 340 / 900 px 测试确认不滚动）。
- [ ] **Step 5: 截图**：offscreen 渲染委托（3 行：正常 / 改过拍摄面 / 待删除）和 `SurfaceRow` 三种状态，ko / en，存 scratchpad，人工检查不截断。
- [ ] **Step 6: Commit** `feat(ui): surface column, per-row delete button and the surface row`

---

### Task 5: 上传批次带 `surfaceUpdates` / `deletes`

**Files:**
- Modify: `labeling_tool/api/uploader.py`、`labeling_tool/api/client.py`（`register_annotations` 支持额外字段）、`labeling_tool/ui/upload_worker.py`
- Test: `labeling_tool/tests/test_uploader_edits.py`（新）；既有 `test_uploader*.py` 必须照旧通过

**Interfaces:**
- Consumes: Task 1 `SURFACE_UPDATES_KEY`、`DELETES_KEY`、`DELETED_KEY`、`SKIPPED_KEY`、`EDIT_LIST_LIMIT`、`timestamps_in`
- Produces:
  - `ViewerApiClient.register_annotations(*, edit_batch_id, session_id, items, surface_updates=None, deletes=None) -> dict`：非空时加对应键；都为空时请求体与现在完全相同
  - `upload_session(client, *, session_id, items, bytes_for, edit_batch_id, progress=None, surface_updates=(), deletes=()) -> dict`，结果新增：
    - `"deleted_timestamps": list[int]`（各批 `deleted` + `skipped` 的并集，去重保序）
    - `"surface_timestamps": list[int]`（成功批次里的 `surfaceUpdates` timestamp）
    - `failed` 条目增加 `"surface_timestamps"` / `"delete_timestamps"`（该批未确认的）
  - 批次规则：批次数 = `max(ceil(items/33), ceil(surface/100), ceil(deletes/100), 1 if 有任何内容 else 0)`；第 i 批带 items 的第 i 块、surface 的第 i 块、deletes 的第 i 块；没有 items 的批次不调 presigned / PUT，只调 register（`items: []`）；每批 `editBatchId` = `<id>-<i>`（不变）
  - `UploadWorker(..., surface_updates=(), deletes=())`：透传；`items` 为空也照样上传；done 字典带 `deleted_timestamps` / `surface_timestamps`

- [ ] **Step 1: 写失败测试**（假客户端记录每次 `register_annotations` 的参数并返回 `{"updatedPhotoCount": len(items), "deleted": [...]}`）：
  1. 只有 deletes（2 条）→ 不调 presigned / PUT；一次 register，`items == []`，`deletes` 两条；结果 `deleted_timestamps == [两条]`
  2. 只有 surface（1 条）→ 一次 register 带 `surface_updates`；结果 `surface_timestamps == [ts]`
  3. 混合：40 张 items（两批）、150 条 deletes → 两批：第一批 33 items + 100 deletes，第二批 7 items + 50 deletes
  4. 响应 `skipped` 里的 timestamp 也进 `deleted_timestamps`；格式 `[{"timestamp": ts}]` 也接受
  5. 第二批抛错 → 第一批的删除在 `deleted_timestamps`，第二批的在 `failed[...]["delete_timestamps"]`
  6. 没有 surface / deletes 时，`register_annotations` 收到的参数与改动前完全相同（不传额外键）
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（`_chunks` 复用；`client.register_annotations` 仅在列表非空时把键放进 payload；结果合并去重）
- [ ] **Step 4: 测试通过；完整命令全绿**（既有上传测试不改）。
- [ ] **Step 5: Commit** `feat(upload): surface updates and deletes ride along in register-annotations`

---

### Task 6: 窗口接线（列表、侧边栏、上传条件与确认框）

**Files:**
- Modify: `labeling_tool/ui/main_window.py`、`labeling_tool/core/window/main_window.py`（列表填充处 `_reload_data` 约 863–905 行、`_refresh_list_header`、`_show_image` 末尾刷新侧边栏）
- Modify: i18n 三个文件
- Test: `labeling_tool/tests/test_side_panel.py`（追加）

**Interfaces:**
- Consumes: Task 1～5
- Produces（`ViewerMainWindow`）:
  - 列表填充时每项写 `SURFACE_ROLE`（`surface_floor/wall/ceiling` 或 `surface_unknown_short`）、`SURFACE_EDITED_ROLE`、`DELETE_PENDING_ROLE`；委托 `surface_width`（按三语最宽文字算）、`delete_width = 22`
  - `_on_delete_clicked(row)`：`toggle_delete`，存 manifest，刷新该行与 ●
  - `_on_surface_chosen(value)`：对当前照片 `set_surface`，存 manifest，刷新列表行、侧边栏、●
  - `_refresh_surface_row()`：按当前照片 `set_value(shown_surface, surface_edit is not None, tilt_deg, tilt_source)`；无照片时禁用
  - `_list_item_mark`：在原条件上加 `has_pending_edit(entry)` → `"pending"`
  - `_on_upload`：
    - 收集 `edit_entries = [listed 照片的 entry]`；`surface = surface_updates(edit_entries)`、`dels = deletes(edit_entries)`
    - `items` 的 specs 排除 `delete_pending` 照片
    - 三者都空 → 照旧「没有修改」提示
    - `dels` 非空 → `_confirm_deletes(dels)`（`QMessageBox.warning` 风格的问题框，按钮 `delete_confirm_ok` / `delete_confirm_cancel`，文本 `delete_confirm_msg`：张数、编号列表（最多 20 个，其余 `delete_confirm_more`）、不可恢复与计测值 · 보수 구역 · 댓글说明）；取消 → 返回
    - 只有 surface / deletes 而 specs 为空时，也启动 `UploadWorker`（`specs=[]`）
- i18n 新键：`delete_confirm_title`（사진 삭제 확인 / 确认删除照片 / Delete photos?）、`delete_confirm_msg`（「사진 {count}장을 서버에서 삭제합니다.\n{numbers}\n되돌릴 수 없으며 계측값 · 보수 구역 · 댓글도 함께 지워집니다.」/「将在服务器上删除 {count} 张照片。\n{numbers}\n无法恢复，计测值、修补区域和评论也会一起删除。」/「{count} photos will be deleted on the server.\n{numbers}\nThis cannot be undone; their measurements, repair areas and comments are deleted too.」）、`delete_confirm_more`（외 {n}장 / 等 {n} 张 / and {n} more）、`delete_confirm_ok`（삭제하고 업로드 / 删除并上传 / Delete and upload）、`delete_confirm_cancel`（취소 / 取消 / Cancel）

- [ ] **Step 1: 写失败测试**（`_make_window` 已有；manifest 照片默认无 surface）：
  1. 列表第一行 `SURFACE_ROLE == tr("surface_unknown_short")`；给 manifest 设 `surface="wall"` 后重建列表 → 「벽」
  2. 点第 1 行删除区域（用委托信号或 `_on_delete_clicked(0)`）→ `delete_pending` 为真、已存 manifest、行 `DELETE_PENDING_ROLE` 为真、mark 为 pending、`current_idx` 不变；再点一次 → 取消
  3. `_on_surface_chosen("floor")` → 当前照片 `surface_edit == "floor"`，侧边栏 `floor` 选中，列表第 1 行显示「바닥」且 `SURFACE_EDITED_ROLE`；再选服务器原值 → 撤销
  4. 上传：只标记删除（无掩码修改），monkeypatch `QMessageBox` 确认返回取消 → 不创建 `UploadWorker`；返回确认 → 创建，`specs == []`，`deletes` 一条
  5. 标记删除且改了掩码 → specs 不含该照片
  6. 340 px / 900 px / ko-zh-en：选任一工具都不滚动（复用 `test_no_tool_makes_the_panel_scroll_in_a_900px_window` 的做法，加上 `_surface_row` 已显示）
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（`UploadWorker` 构造加 `surface_updates=` / `deletes=`；确认框 monkeypatch 点：`self._confirm_deletes` 方法，测试直接 monkeypatch 它）
- [ ] **Step 4: 测试通过；完整命令全绿。**
- [ ] **Step 5: Commit** `feat(ui): change a photo's surface and mark photos for deletion`

---

### Task 7: 上传之后：本地删除、拍摄面确认、后台刷新编号

**Files:**
- Modify: `labeling_tool/ui/main_window.py`（`_finish_upload`）
- Create: `labeling_tool/ui/photo_refresh_worker.py`
- Test: `labeling_tool/tests/test_side_panel.py`（追加）、`labeling_tool/tests/test_photo_refresh.py`（新）

**Interfaces:**
- Consumes: Task 1 `photo_fields`、`Manifest.remove`；Task 3 `remove_photo_files`；Task 5 结果字段；`fetch_dialog._fetch_all_photos` 的分页逻辑（`grep -n "_fetch_all_photos" -A25 labeling_tool/ui/fetch_dialog.py`，抽成 `api/client.py` 或 `api/photos.py` 的 `fetch_all_photos(client, session_id) -> list[dict]` 供两处共用）
- Produces:
  - `apply_photo_refresh(manifest, photos: list[dict]) -> bool`（纯函数，放 `session/photo_edits.py`）：对 manifest 中按 timestamp 匹配到的照片更新 `report_photo_num` 与三个服务器字段；返回是否有变化；不删除 manifest 中服务器列表里没有的照片
  - `PhotoRefreshRunnable(client, session_id, signals)` + `PhotoRefreshSignals.done = pyqtSignal(object)`（照片列表或 `None` 表示失败）
  - `_finish_upload` 新增步骤（在现有 synced 处理之后）：
    1. `deleted = result["deleted_timestamps"]`：对应照片 `remove_photo_files` + `manifest.remove`；从 `_edited` / `_bbox_edited` / 范围 focus 中移除
    2. `surface_timestamps` 对应照片：`surface = surface_edit`、`surface_edit = None`、`tilt_source = "manual"`
    3. 存 manifest；重建列表；当前照片被删 → 显示原位置的下一张（没有则上一张；全空则清空画布）
    4. 若有删除或拍摄面变化 → 启动 `PhotoRefreshRunnable`；回调里 `apply_photo_refresh` → 有变化则存 manifest、重建列表并保持当前照片（按文件名）；失败 → 状态栏 `photo_refresh_failed`
    5. 状态栏汇总 `upload_deleted_summary`（「삭제 {n}장」）附在原有完成信息后
- i18n 新键：`photo_refresh_failed`（사진 번호를 새로 받지 못했습니다. 작업을 다시 가져오면 맞춰집니다. / 未能刷新照片编号，重新获取作业即可更新。/ Could not refresh photo numbers; fetching the job again updates them.）、`upload_deleted_summary`（삭제 {n}장 / 已删除 {n} 张 / {n} deleted）

- [ ] **Step 1: 写失败测试**
  - `apply_photo_refresh`：编号前移被写入；服务器缺的照片保留；服务器值更新；`surface_edit` 不动
  - 窗口（假 `UploadWorker` 结果直接调 `_finish_upload`）：
    1. 3 张照片，删除第 2 张（当前显示第 2 张）→ 文件被删、manifest 只剩 2 张、列表 2 行、当前照片是原第 3 张
    2. 结果 `failed` 带 `delete_timestamps` → 那张仍 `delete_pending`、文件仍在
    3. `surface_timestamps` → `surface` 更新、`surface_edit` 清空、mark 不再因拍摄面为 pending
    4. 范围视图（`_range_window`）删除范围内一张 → 范围仍只含原范围剩下的照片
    5. 刷新回调：给出编号前移的照片列表 → 列表编号变化、当前照片不变；回调 `None` → 状态栏 `photo_refresh_failed`
    6. 删光所有照片 → 画布清空、无异常
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（刷新在 `QThreadPool` 后台；信号对象挂在窗口上，模式同 `ClassSyncRunnable`）
- [ ] **Step 4: 测试通过；完整命令全绿。**
- [ ] **Step 5: Commit** `feat(ui): drop deleted photos locally and refresh photo numbers after upload`

---

### Task 8: 收尾：文档、截图、按服务器文档核对

**Files:**
- Modify: README（ko / en / zh-CN，tracked 的三份）、`docs/i18n-glossary.md`（核对 Task 4/6/7 新词都在）、spec §7（写下核对结果）
- Test: 新增 `labeling_tool/tests/test_api_doc_examples.py`：用服务器文档里的请求 / 响应样例（照片列表项、V4 请求体、V4 响应）验证 `photo_fields`、`register_annotations` 组装的请求体、`timestamps_in` 解析

- [ ] **Step 1:** 对照服务器文档逐项核对 spec §7，差异改进 `api/edit_fields.py`，并写进 spec §7。
- [ ] **Step 2:** 写文档样例测试并通过。
- [ ] **Step 3:** README 的标注窗口功能表加两行（촬영면 / 사진 삭제），합니다체。
- [ ] **Step 4:** 截图（ko）：列表含正常 / 改过拍摄面 / 待删除三种行；侧边栏拍摄面一行；删除确认框。人工检查。
- [ ] **Step 5:** 完整命令全绿；启动冒烟 `QT_QPA_PLATFORM=offscreen timeout 8 .venv/bin/python -m labeling_tool.app; [ $? = 124 ]`。
- [ ] **Step 6: Commit** `docs: surface and delete in the README; checked against the server API`
