# 本地标注工具 `labeling_tool`(V API 闭环版)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个自包含、可移植的 `labeling_tool/` 文件夹,在现有标注核心外包一层「会话连接 + V1 下载 + V2/V3/V4 上传」,实现本地 PC 上 `获取 → 标注 → 回传 EC2` 的完整闭环。

**Architecture:** 顶层包 `labeling_tool`,内含从现有 `algorithms/05_detect/src/tools/labeling` 整体复制并改写导入前缀的 `core/`(标注核心),外加 `api/`(V API 客户端/下载/上传)、`session/`(工作区与会话清单)、`ui/`(连接向导 + 扩展主窗口)。逻辑层与 API 层用纯函数 + `responses` mock 做 TDD,GUI 层手动验收。

**Tech Stack:** Python 3.10+, PyQt5, qfluentwidgets, opencv-python, numpy, scikit-image, requests, pycocotools。测试:pytest + responses。

参考设计:`docs/superpowers/specs/2026-06-12-local-labeling-tool-vapi-design.md`
参考 API:`api-reference_v1.0.7.md`(V1~V4 = 「로컬 포토뷰어 API」节;V2 响应结构同 I4)

---

## File Structure

```
labeling_tool/
├── __init__.py
├── app.py                      # 入口:连接向导 → 主界面
├── config.json                 # 运行期生成,仅存 BASE/apiKey(.gitignore)
├── requirements.txt
├── README.md
├── core/                       # 从现有 labeling 包复制 + 导入前缀改写
│   └── …(bbox/ canvas/ rebuild/ result/ window/ constants.py i18n.py mask_io.py qt_utils.py)
├── api/
│   ├── __init__.py
│   ├── client.py               # ViewerApiClient: V1/V2/V3/V4 + 错误码
│   ├── errors.py               # ViewerApiError(code, message, details, http_status)
│   ├── downloader.py           # download_photos(): 下载 stitched/mask 到本地
│   └── uploader.py             # upload_session(): V2→V3→V4 批量编排
├── session/
│   ├── __init__.py
│   ├── naming.py               # filename ↔ timestamp 互转 + s3 key
│   ├── workspace.py            # 目录布局
│   └── manifest.py             # manifest.json 读写 + synced 状态
├── ui/
│   ├── __init__.py
│   ├── connect_dialog.py       # 启动连接向导
│   └── main_window.py          # 扩展 core 的 MainWindow:工作区目录 + 上传按钮
├── annotation_payload.py       # 由掩膜/OBB/scale 构造 V4 item(纯逻辑)
└── tests/
    ├── __init__.py
    ├── test_naming.py
    ├── test_workspace.py
    ├── test_manifest.py
    ├── test_annotation_payload.py
    ├── test_crack_metrics_minwidth.py
    ├── test_client.py
    ├── test_downloader.py
    └── test_uploader.py
```

**测试运行约定:** 所有命令从仓库根目录 `/home/claire/Lastmile/XI_ParkingLots` 执行,使用 `python -m pytest`(确保 `import labeling_tool` 可解析)。

---

## Task 1: 脚手架 + 复制标注核心(改写导入前缀)

**Files:**
- Create: `labeling_tool/__init__.py`, `labeling_tool/tests/__init__.py`
- Create: `labeling_tool/core/`(由现有包复制而来)
- Test: `labeling_tool/tests/test_core_import.py`

- [ ] **Step 1: 创建包目录与复制核心**

Run(从仓库根目录):
```bash
mkdir -p labeling_tool/tests
touch labeling_tool/__init__.py labeling_tool/tests/__init__.py
cp -r algorithms/05_detect/src/tools/labeling labeling_tool/core
find labeling_tool/core -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 2: 改写 core 内所有导入前缀 `labeling.` → `labeling_tool.core.`**

Run:
```bash
find labeling_tool/core -name '*.py' -print0 | xargs -0 sed -i \
  -e 's/\bfrom labeling\./from labeling_tool.core./g' \
  -e 's/\bfrom labeling import/from labeling_tool.core import/g' \
  -e 's/\bimport labeling\b/import labeling_tool.core/g'
```

- [ ] **Step 3: 写核心导入冒烟测试(只导入无 Qt 依赖的纯逻辑模块)**

Create `labeling_tool/tests/test_core_import.py`:
```python
"""Smoke test: the copied core package imports under its new package path.

We import only the Qt-free logic modules so the test runs headless.
"""


def test_oriented_box_imports():
    from labeling_tool.core.bbox.oriented_box import OrientedBox
    box = OrientedBox(cx=10, cy=20, w=4, h=6, angle_deg=0)
    assert box.area_px2() == 24.0


def test_crack_metrics_imports():
    from labeling_tool.core.result.crack_metrics import (
        CrackMetrics, compute_crack_metrics, compute_spalling_area_mm2,
    )
    assert CrackMetrics.zero().length_mm == 0.0
```

- [ ] **Step 4: 运行冒烟测试,确认通过**

Run: `python -m pytest labeling_tool/tests/test_core_import.py -v`
Expected: 2 passed。若失败提示 `No module named 'labeling.…'`,说明 Step 2 有遗漏的导入未改写,补一条 `grep -rn 'labeling\.' labeling_tool/core --include='*.py'` 排查并修正。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/
git commit -m "feat(labeling_tool): scaffold package + vendor labeling core with rewritten imports"
```

---

## Task 2: 给 crack metrics 补 `min_width_mm`(TDD)

**Files:**
- Modify: `labeling_tool/core/result/crack_metrics.py`
- Test: `labeling_tool/tests/test_crack_metrics_minwidth.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_crack_metrics_minwidth.py`:
```python
import numpy as np
from labeling_tool.core.result.crack_metrics import (
    CrackMetrics, compute_crack_metrics,
)


def test_zero_has_min_width():
    z = CrackMetrics.zero()
    assert z.min_width_mm == 0.0


def test_min_le_mean_le_max_on_synthetic_crack():
    # A 3px-thick horizontal bar of varying width is hard to synthesize
    # cleanly; a constant-width bar makes min==mean==max, which still
    # validates the field exists and obeys ordering.
    mask = np.zeros((60, 200), dtype=np.uint8)
    mask[28:33, 20:180] = 255          # ~5px thick horizontal crack
    m = compute_crack_metrics(mask, scale_px_per_cm=10.0)
    assert m.min_width_mm is not None
    assert m.min_width_mm <= m.mean_width_mm <= m.max_width_mm
    assert m.length_mm > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_crack_metrics_minwidth.py -v`
Expected: FAIL — `AttributeError: 'CrackMetrics' object has no attribute 'min_width_mm'`

- [ ] **Step 3: 实现 —— 在 dataclass 与计算中加入 min_width_mm**

Modify `labeling_tool/core/result/crack_metrics.py`:

dataclass 改为(增加 `min_width_mm` 字段,放在 `max_width_mm` 之后):
```python
@dataclass
class CrackMetrics:
    max_width_mm: float | None
    min_width_mm: float | None
    mean_width_mm: float | None
    length_mm: float | None

    @classmethod
    def zero(cls) -> "CrackMetrics":
        return cls(0.0, 0.0, 0.0, 0.0)

    @classmethod
    def na(cls) -> "CrackMetrics":
        return cls(None, None, None, None)
```

`compute_crack_metrics` 末尾的 return 改为:
```python
    return CrackMetrics(
        max_width_mm  = float(max(widths_px)) * mm_per_px,
        min_width_mm  = float(min(widths_px)) * mm_per_px,
        mean_width_mm = float(np.mean(widths_px)) * mm_per_px,
        length_mm     = float(length_px) * mm_per_px,
    )
```

- [ ] **Step 4: 运行确认通过 + 不破坏既有用法**

Run: `python -m pytest labeling_tool/tests/test_crack_metrics_minwidth.py labeling_tool/tests/test_core_import.py -v`
Expected: all passed。
注:`CrackMetrics` 在 `core/result/text_report.py`、`core/result/exporter.py` 中按字段名(关键字)使用,新增字段不影响;若有按位置构造处,Step 4 会暴露——届时改为关键字构造。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/result/crack_metrics.py labeling_tool/tests/test_crack_metrics_minwidth.py
git commit -m "feat(labeling_tool): add min_width_mm to crack metrics"
```

---

## Task 3: V4 注释 item 构造器(TDD)

**Files:**
- Create: `labeling_tool/annotation_payload.py`
- Test: `labeling_tool/tests/test_annotation_payload.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_annotation_payload.py`:
```python
import numpy as np
from labeling_tool.core.bbox.oriented_box import OrientedBox
from labeling_tool.annotation_payload import build_annotation_item


def _crack_mask():
    m = np.zeros((60, 200), dtype=np.uint8)
    m[28:33, 20:180] = 255
    return m


def test_repair_areas_use_camelcase_angle():
    boxes = [OrientedBox(cx=320, cy=180, w=120, h=40, angle_deg=15)]
    item = build_annotation_item(
        timestamp=1717572612000,
        mask_s3_key="results/43/masks/mask_1717572612000.png",
        px_per_cm=45.2, scale_source="aruco",
        crack_mask=_crack_mask(), spalling_mask=None, boxes=boxes,
    )
    assert item["timestamp"] == 1717572612000
    assert item["maskS3Key"] == "results/43/masks/mask_1717572612000.png"
    assert item["pxPerCm"] == 45.2
    assert item["scaleSource"] == "aruco"
    ra = item["repairAreas"][0]
    assert set(ra.keys()) == {"cx", "cy", "w", "h", "angleDeg"}
    assert ra["angleDeg"] == 15


def test_crack_metrics_fields_and_defect_type():
    item = build_annotation_item(
        timestamp=1, mask_s3_key="k", px_per_cm=10.0, scale_source="aruco",
        crack_mask=_crack_mask(), spalling_mask=None, boxes=[],
    )
    cm = item["crackMetrics"]
    for key in ("lengthMm", "avgWidthMm", "minWidthMm", "maxWidthMm",
                "bboxAreaMm2", "bboxCount", "spallingMm2", "defectType",
                "pxPerMm"):
        assert key in cm
    assert cm["defectType"] == 0          # crack only
    assert cm["pxPerMm"] == 1.0           # 10 px/cm = 1 px/mm
    assert cm["bboxCount"] == 0
    assert cm["minWidthMm"] <= cm["avgWidthMm"] <= cm["maxWidthMm"]


def test_defect_type_spalling_and_mixed():
    spall = np.zeros((60, 200), dtype=np.uint8)
    spall[10:20, 10:20] = 255
    only_spall = build_annotation_item(
        timestamp=1, mask_s3_key="k", px_per_cm=10.0, scale_source="aruco",
        crack_mask=np.zeros((60, 200), np.uint8), spalling_mask=spall, boxes=[],
    )
    assert only_spall["crackMetrics"]["defectType"] == 1   # spalling only
    assert only_spall["crackMetrics"]["spallingMm2"] > 0

    mixed = build_annotation_item(
        timestamp=1, mask_s3_key="k", px_per_cm=10.0, scale_source="aruco",
        crack_mask=_crack_mask(), spalling_mask=spall, boxes=[],
    )
    assert mixed["crackMetrics"]["defectType"] == 2        # both


def test_bbox_area_sums_in_mm2():
    # 10 px/cm -> 1 px/mm -> area_px2 == area_mm2
    boxes = [OrientedBox(cx=0, cy=0, w=10, h=20, angle_deg=0)]  # 200 px^2
    item = build_annotation_item(
        timestamp=1, mask_s3_key="k", px_per_cm=10.0, scale_source="aruco",
        crack_mask=np.zeros((30, 30), np.uint8), spalling_mask=None, boxes=boxes,
    )
    assert item["crackMetrics"]["bboxCount"] == 1
    assert abs(item["crackMetrics"]["bboxAreaMm2"] - 200.0) < 1e-6
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_annotation_payload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.annotation_payload'`

- [ ] **Step 3: 实现**

Create `labeling_tool/annotation_payload.py`:
```python
"""Build a V4 register-annotations `item` dict from local edit state.

Maps the labeling tool's internal artifacts (crack/spalling masks,
OrientedBox repair areas, ArUco scale) onto the V4 schema documented in
api-reference_v1.0.7 (로컬 포토뷰어 API · V4).
"""

from __future__ import annotations

import numpy as np

from labeling_tool.core.bbox.oriented_box import OrientedBox
from labeling_tool.core.result.crack_metrics import (
    compute_crack_metrics, compute_spalling_area_mm2,
)


def _defect_type(has_crack: bool, has_spalling: bool) -> int:
    """0 crack, 1 spalling(박리), 2 mixed(혼합). Default 0 when neither."""
    if has_crack and has_spalling:
        return 2
    if has_spalling:
        return 1
    return 0


def build_annotation_item(
    *,
    timestamp: int,
    mask_s3_key: str,
    px_per_cm: float,
    scale_source: str,
    crack_mask: np.ndarray | None,
    spalling_mask: np.ndarray | None,
    boxes: list[OrientedBox],
) -> dict:
    mm_per_px = 10.0 / px_per_cm
    px_per_mm = px_per_cm / 10.0

    has_crack = crack_mask is not None and bool((crack_mask > 0).any())
    has_spalling = spalling_mask is not None and bool((spalling_mask > 0).any())

    if has_crack:
        cm = compute_crack_metrics(crack_mask, px_per_cm)
    else:
        from labeling_tool.core.result.crack_metrics import CrackMetrics
        cm = CrackMetrics.zero()

    spalling_mm2 = compute_spalling_area_mm2(spalling_mask, px_per_cm) or 0.0

    bbox_area_mm2 = sum(b.area_px2() for b in boxes) * (mm_per_px ** 2)
    bbox_count = len(boxes)

    repair_areas = [
        {"cx": b.cx, "cy": b.cy, "w": b.w, "h": b.h, "angleDeg": b.angle_deg}
        for b in boxes
    ]

    crack_metrics = {
        "lengthMm": float(cm.length_mm or 0.0),
        "avgWidthMm": float(cm.mean_width_mm or 0.0),
        "minWidthMm": float(cm.min_width_mm or 0.0),
        "maxWidthMm": float(cm.max_width_mm or 0.0),
        "bboxAreaMm2": float(bbox_area_mm2),
        "bboxCount": int(bbox_count),
        "spallingMm2": float(spalling_mm2),
        "defectType": _defect_type(has_crack, has_spalling),
        "pxPerMm": float(px_per_mm),
    }

    return {
        "timestamp": int(timestamp),
        "maskS3Key": mask_s3_key,
        "pxPerCm": float(px_per_cm),
        "scaleSource": scale_source or "aruco",
        "repairAreas": repair_areas,
        "crackMetrics": crack_metrics,
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_annotation_payload.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/annotation_payload.py labeling_tool/tests/test_annotation_payload.py
git commit -m "feat(labeling_tool): V4 annotation item builder"
```

---

## Task 4: 文件名 ↔ timestamp 命名工具(TDD)

**Files:**
- Create: `labeling_tool/session/__init__.py`, `labeling_tool/session/naming.py`
- Test: `labeling_tool/tests/test_naming.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_naming.py`:
```python
import pytest
from labeling_tool.session import naming


def test_stitched_filename():
    assert naming.stitched_filename(1717572612000) == "stitched_1717572612000.jpg"


def test_mask_filename():
    assert naming.mask_filename(1717572612000) == "mask_1717572612000.png"


def test_timestamp_from_stitched():
    assert naming.timestamp_from_filename("stitched_1717572612000.jpg") == 1717572612000


def test_timestamp_from_mask():
    assert naming.timestamp_from_filename("mask_1717572612000.png") == 1717572612000


def test_mask_s3_key():
    assert naming.mask_s3_key(43, 1717572612000) == \
        "results/43/masks/mask_1717572612000.png"


def test_bad_filename_raises():
    with pytest.raises(ValueError):
        naming.timestamp_from_filename("DSC_1234.jpg")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.session'`

- [ ] **Step 3: 实现**

Create `labeling_tool/session/__init__.py`:
```python
```
(空文件)

Create `labeling_tool/session/naming.py`:
```python
"""Filename <-> timestamp <-> S3 key conversions for the V API.

Convention (api-reference_v1.0.7): stitched_{timestampMs}.jpg paired with
mask_{timestampMs}.png. S3 mask key: results/{sessionId}/masks/mask_{ts}.png.
"""

from __future__ import annotations

import re

_TS_RE = re.compile(r"^(?:stitched|mask)_(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)


def stitched_filename(timestamp: int) -> str:
    return f"stitched_{int(timestamp)}.jpg"


def mask_filename(timestamp: int) -> str:
    return f"mask_{int(timestamp)}.png"


def timestamp_from_filename(filename: str) -> int:
    m = _TS_RE.match(filename)
    if not m:
        raise ValueError(f"not a stitched/mask filename: {filename!r}")
    return int(m.group(1))


def mask_s3_key(session_id: int, timestamp: int) -> str:
    return f"results/{int(session_id)}/masks/mask_{int(timestamp)}.png"
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_naming.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/session/__init__.py labeling_tool/session/naming.py labeling_tool/tests/test_naming.py
git commit -m "feat(labeling_tool): filename/timestamp/s3key naming helpers"
```

---

## Task 5: 工作区目录布局(TDD)

**Files:**
- Create: `labeling_tool/session/workspace.py`
- Test: `labeling_tool/tests/test_workspace.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_workspace.py`:
```python
from pathlib import Path
from labeling_tool.session.workspace import Workspace


def test_layout_paths(tmp_path):
    ws = Workspace(root=tmp_path, session_id=43)
    assert ws.session_dir == tmp_path / "session_43"
    assert ws.origin_dir == tmp_path / "session_43" / "Origin"
    assert ws.detected_dir == tmp_path / "session_43" / "Detected"
    assert ws.labeling_dir == tmp_path / "session_43" / "Labeling"
    assert ws.result_dir == tmp_path / "session_43" / "Result"
    assert ws.manifest_path == tmp_path / "session_43" / "manifest.json"


def test_ensure_creates_dirs(tmp_path):
    ws = Workspace(root=tmp_path, session_id=43)
    ws.ensure()
    for d in (ws.origin_dir, ws.detected_dir, ws.labeling_dir, ws.result_dir):
        assert d.is_dir()


def test_default_root_under_home():
    ws = Workspace.default(session_id=7)
    assert ws.session_dir == Path.home() / "labeling_tool_data" / "session_7"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.session.workspace'`

- [ ] **Step 3: 实现**

Create `labeling_tool/session/workspace.py`:
```python
"""Per-session local workspace directory layout.

~/labeling_tool_data/session_{id}/{Origin,Detected,Labeling,Result}/ + manifest.json
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Workspace:
    root: Path
    session_id: int

    @classmethod
    def default(cls, session_id: int) -> "Workspace":
        return cls(root=Path.home() / "labeling_tool_data", session_id=session_id)

    @property
    def session_dir(self) -> Path:
        return self.root / f"session_{self.session_id}"

    @property
    def origin_dir(self) -> Path:
        return self.session_dir / "Origin"

    @property
    def detected_dir(self) -> Path:
        return self.session_dir / "Detected"

    @property
    def labeling_dir(self) -> Path:
        return self.session_dir / "Labeling"

    @property
    def result_dir(self) -> Path:
        return self.session_dir / "Result"

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "manifest.json"

    def ensure(self) -> None:
        for d in (self.origin_dir, self.detected_dir,
                  self.labeling_dir, self.result_dir):
            d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_workspace.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/session/workspace.py labeling_tool/tests/test_workspace.py
git commit -m "feat(labeling_tool): per-session workspace layout"
```

---

## Task 6: 会话清单 manifest(TDD)

**Files:**
- Create: `labeling_tool/session/manifest.py`
- Test: `labeling_tool/tests/test_manifest.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_manifest.py`:
```python
from labeling_tool.session.manifest import Manifest, PhotoEntry


def test_add_and_lookup_by_filename(tmp_path):
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(
        filename="stitched_1717572612000.jpg",
        timestamp=1717572612000, photo_id=101, report_photo_num=1,
        px_per_cm=45.2, scale_source="aruco",
    ))
    e = mf.get("stitched_1717572612000.jpg")
    assert e.timestamp == 1717572612000
    assert e.px_per_cm == 45.2
    assert e.synced is False


def test_roundtrip_save_load(tmp_path):
    path = tmp_path / "manifest.json"
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(
        filename="stitched_1.jpg", timestamp=1, photo_id=1,
        report_photo_num=1, px_per_cm=10.0, scale_source="aruco",
    ))
    mf.save(path)
    loaded = Manifest.load(path)
    assert loaded.session_id == 43
    assert loaded.get("stitched_1.jpg").timestamp == 1


def test_mark_synced(tmp_path):
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(filename="stitched_1.jpg", timestamp=1, photo_id=1,
                      report_photo_num=1, px_per_cm=10.0, scale_source="aruco"))
    mf.mark_synced(["stitched_1.jpg"], batch_id="batch-abc")
    e = mf.get("stitched_1.jpg")
    assert e.synced is True
    assert e.uploaded_batch_id == "batch-abc"


def test_filenames_in_report_order():
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(filename="stitched_20.jpg", timestamp=20, photo_id=2,
                      report_photo_num=2, px_per_cm=10.0, scale_source="aruco"))
    mf.add(PhotoEntry(filename="stitched_10.jpg", timestamp=10, photo_id=1,
                      report_photo_num=1, px_per_cm=10.0, scale_source="aruco"))
    assert mf.filenames_in_order() == ["stitched_10.jpg", "stitched_20.jpg"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.session.manifest'`

- [ ] **Step 3: 实现**

Create `labeling_tool/session/manifest.py`:
```python
"""Local session manifest: bridges GUI filenames and V API timestamps.

Persists per-photo metadata fetched from V1 plus upload (sync) state, so
labeling can resume offline and uploads stay idempotent across runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class PhotoEntry:
    filename: str
    timestamp: int
    photo_id: int
    report_photo_num: int
    px_per_cm: float
    scale_source: str = "aruco"
    synced: bool = False
    uploaded_batch_id: str | None = None


@dataclass
class Manifest:
    session_id: int
    base: str
    fetched_at: str | None = None
    photos: dict[str, PhotoEntry] = field(default_factory=dict)

    def add(self, entry: PhotoEntry) -> None:
        self.photos[entry.filename] = entry

    def get(self, filename: str) -> PhotoEntry:
        return self.photos[filename]

    def filenames_in_order(self) -> list[str]:
        return [e.filename for e in sorted(
            self.photos.values(), key=lambda e: e.report_photo_num)]

    def mark_synced(self, filenames: list[str], batch_id: str) -> None:
        for fn in filenames:
            e = self.photos.get(fn)
            if e is not None:
                e.synced = True
                e.uploaded_batch_id = batch_id

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": self.session_id,
            "base": self.base,
            "fetchedAt": self.fetched_at,
            "photos": {fn: asdict(e) for fn, e in self.photos.items()},
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        mf = cls(
            session_id=data["sessionId"],
            base=data.get("base", ""),
            fetched_at=data.get("fetchedAt"),
        )
        for fn, d in data.get("photos", {}).items():
            mf.photos[fn] = PhotoEntry(**d)
        return mf
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_manifest.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/session/manifest.py labeling_tool/tests/test_manifest.py
git commit -m "feat(labeling_tool): session manifest with sync state"
```

---

## Task 7: V API 错误类型 + 客户端 V1(TDD)

**Files:**
- Create: `labeling_tool/api/__init__.py`, `labeling_tool/api/errors.py`, `labeling_tool/api/client.py`
- Test: `labeling_tool/tests/test_client.py`(本任务先覆盖 V1 + 错误)

- [ ] **Step 1: 安装测试依赖 `responses`**

Run: `python -m pip install responses`
Expected: 成功安装(若已装则 "Requirement already satisfied")。

- [ ] **Step 2: 写失败测试**

Create `labeling_tool/tests/test_client.py`:
```python
import pytest
import responses
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError

BASE = "https://api.example.com"
KEY = "test-key"


def _client():
    return ViewerApiClient(base_url=BASE, api_key=KEY)


@responses.activate
def test_list_photos_sends_key_and_parses():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/43/photos/",
        json={"sessionId": 43, "offset": 0, "limit": 100, "total": 1,
              "photos": [{"photoId": 101, "timestamp": 1717572612000,
                          "reportPhotoNum": 1, "stitchedUrl": "https://s/stit",
                          "maskUrl": "https://s/mask", "pxPerCm": 45.2,
                          "repairAreas": [], "crackMetrics": {}}]},
        status=200,
    )
    out = _client().list_photos(43, from_num=1, to_num=10)
    assert out["total"] == 1
    assert out["photos"][0]["timestamp"] == 1717572612000
    req = responses.calls[0].request
    assert req.headers["X-Viewer-Api-Key"] == KEY
    assert "fromNum=1" in req.url and "toNum=10" in req.url


@responses.activate
def test_job_not_ready_raises_typed_error():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/43/photos/",
        json={"error": "AI job not finished", "code": "JOB_NOT_READY",
              "details": {}},
        status=409,
    )
    with pytest.raises(ViewerApiError) as ei:
        _client().list_photos(43)
    assert ei.value.code == "JOB_NOT_READY"
    assert ei.value.http_status == 409
```

- [ ] **Step 3: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.api.client'`

- [ ] **Step 4: 实现 errors + client(V1)**

Create `labeling_tool/api/__init__.py`:
```python
```
(空文件)

Create `labeling_tool/api/errors.py`:
```python
"""Typed error for V API responses (공통 오류 응답: {error, code, details})."""

from __future__ import annotations


class ViewerApiError(Exception):
    def __init__(self, code: str, message: str,
                 http_status: int, details: dict | None = None):
        super().__init__(f"[{http_status} {code}] {message}")
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}
```

Create `labeling_tool/api/client.py`:
```python
"""HTTP client for the 로컬 포토뷰어 API (V1~V4).

Auth: X-Viewer-Api-Key header. All non-2xx responses are parsed for the
common error body {error, code, details} and re-raised as ViewerApiError.
"""

from __future__ import annotations

import requests

from labeling_tool.api.errors import ViewerApiError

DEFAULT_TIMEOUT = 30


class ViewerApiClient:
    def __init__(self, base_url: str, api_key: str,
                 timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({"X-Viewer-Api-Key": api_key})

    # ---- internal -------------------------------------------------
    def _raise_for_error(self, resp: requests.Response) -> None:
        if resp.ok:
            return
        try:
            body = resp.json()
        except ValueError:
            body = {}
        raise ViewerApiError(
            code=body.get("code", "HTTP_ERROR"),
            message=body.get("error", resp.reason or "request failed"),
            http_status=resp.status_code,
            details=body.get("details"),
        )

    # ---- V1 -------------------------------------------------------
    def list_photos(self, session_id: int, *, from_num: int | None = None,
                    to_num: int | None = None, offset: int = 0,
                    limit: int = 100) -> dict:
        params: dict = {}
        if from_num is not None and to_num is not None:
            params["fromNum"] = from_num
            params["toNum"] = to_num
        else:
            params["offset"] = offset
            params["limit"] = limit
        url = f"{self.base_url}/api/viewer/sessions/{session_id}/photos/"
        resp = self._s.get(url, params=params, timeout=self.timeout)
        self._raise_for_error(resp)
        return resp.json()
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_client.py -v`
Expected: 2 passed

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/api/__init__.py labeling_tool/api/errors.py labeling_tool/api/client.py labeling_tool/tests/test_client.py
git commit -m "feat(labeling_tool): V API client errors + V1 list_photos"
```

---

## Task 8: 客户端 V2/V3/V4(TDD)

**Files:**
- Modify: `labeling_tool/api/client.py`
- Modify: `labeling_tool/tests/test_client.py`

- [ ] **Step 1: 追加失败测试**

Append to `labeling_tool/tests/test_client.py`:
```python
@responses.activate
def test_request_presigned_v2():
    responses.add(
        responses.POST, f"{BASE}/api/viewer/presigned-urls/",
        json={"urls": [{"filename": "mask_1.png",
                        "s3Key": "results/43/masks/mask_1.png",
                        "presignedUrl": "https://s3/put",
                        "cacheControl": "max-age=0, must-revalidate"}]},
        status=200,
    )
    out = _client().request_presigned(43, [
        {"filename": "mask_1.png", "timestamp": 1,
         "contentType": "image/png", "sizeBytes": 1024}])
    assert out["urls"][0]["presignedUrl"] == "https://s3/put"


@responses.activate
def test_put_mask_v3_sends_headers():
    responses.add(responses.PUT, "https://s3/put", status=200)
    _client().put_mask("https://s3/put", b"PNGDATA",
                       content_type="image/png",
                       cache_control="max-age=0, must-revalidate")
    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "image/png"
    assert req.headers["Cache-Control"] == "max-age=0, must-revalidate"
    assert req.body == b"PNGDATA"


@responses.activate
def test_register_annotations_v4():
    responses.add(
        responses.POST, f"{BASE}/api/viewer/register-annotations/",
        json={"sessionId": 43, "status": "saved", "updatedPhotoCount": 1},
        status=201,
    )
    out = _client().register_annotations(
        edit_batch_id="b1", session_id=43,
        items=[{"timestamp": 1, "maskS3Key": "k", "pxPerCm": 10.0,
                "scaleSource": "aruco", "repairAreas": [], "crackMetrics": {}}])
    assert out["status"] == "saved"
    body = responses.calls[0].request.body
    assert b"editBatchId" in body
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_client.py -v`
Expected: 新增 3 个 FAIL —— `AttributeError: 'ViewerApiClient' object has no attribute 'request_presigned'`

- [ ] **Step 3: 实现 —— 在 client.py 末尾追加 V2/V3/V4 方法**

Append to `ViewerApiClient` in `labeling_tool/api/client.py`:
```python
    # ---- V2 -------------------------------------------------------
    def request_presigned(self, session_id: int, files: list[dict]) -> dict:
        url = f"{self.base_url}/api/viewer/presigned-urls/"
        resp = self._s.post(
            url, json={"sessionId": session_id, "files": files},
            timeout=self.timeout)
        self._raise_for_error(resp)
        return resp.json()

    # ---- V3 -------------------------------------------------------
    def put_mask(self, presigned_url: str, png_bytes: bytes, *,
                 content_type: str = "image/png",
                 cache_control: str = "max-age=0, must-revalidate") -> None:
        # Direct S3 PUT: no X-Viewer-Api-Key, header values must match what
        # V2 echoed back or S3 signature validation fails.
        resp = requests.put(
            presigned_url, data=png_bytes,
            headers={"Content-Type": content_type,
                     "Cache-Control": cache_control},
            timeout=self.timeout)
        if not resp.ok:
            raise ViewerApiError(
                code="S3_PUT_FAILED",
                message=f"S3 PUT failed: {resp.text[:200]}",
                http_status=resp.status_code)

    # ---- V4 -------------------------------------------------------
    def register_annotations(self, *, edit_batch_id: str, session_id: int,
                             items: list[dict]) -> dict:
        url = f"{self.base_url}/api/viewer/register-annotations/"
        resp = self._s.post(url, json={
            "editBatchId": edit_batch_id,
            "sessionId": session_id,
            "items": items,
        }, timeout=self.timeout)
        self._raise_for_error(resp)
        return resp.json()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_client.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/api/client.py labeling_tool/tests/test_client.py
git commit -m "feat(labeling_tool): V API client V2/V3/V4 methods"
```

---

## Task 9: 下载器(TDD)

**Files:**
- Create: `labeling_tool/api/downloader.py`
- Test: `labeling_tool/tests/test_downloader.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_downloader.py`:
```python
import responses
from labeling_tool.api.downloader import download_photos


@responses.activate
def test_downloads_pairs_with_progress(tmp_path):
    responses.add(responses.GET, "https://s/stit1", body=b"JPGDATA", status=200)
    responses.add(responses.GET, "https://s/mask1", body=b"PNGDATA", status=200)
    photos = [{"timestamp": 1, "stitchedUrl": "https://s/stit1",
               "maskUrl": "https://s/mask1"}]
    origin_dir = tmp_path / "Origin"
    detected_dir = tmp_path / "Detected"
    origin_dir.mkdir(); detected_dir.mkdir()

    seen = []
    failures = download_photos(
        photos, origin_dir, detected_dir,
        progress=lambda done, total: seen.append((done, total)))

    assert failures == []
    assert (origin_dir / "stitched_1.jpg").read_bytes() == b"JPGDATA"
    assert (detected_dir / "mask_1.png").read_bytes() == b"PNGDATA"
    assert seen[-1] == (1, 1)


@responses.activate
def test_records_failure_without_aborting(tmp_path):
    responses.add(responses.GET, "https://s/stit1", body=b"JPG", status=200)
    responses.add(responses.GET, "https://s/mask1", status=500)
    photos = [{"timestamp": 1, "stitchedUrl": "https://s/stit1",
               "maskUrl": "https://s/mask1"}]
    origin_dir = tmp_path / "Origin"; origin_dir.mkdir()
    detected_dir = tmp_path / "Detected"; detected_dir.mkdir()
    failures = download_photos(photos, origin_dir, detected_dir)
    assert len(failures) == 1
    assert failures[0]["timestamp"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_downloader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.api.downloader'`

- [ ] **Step 3: 实现**

Create `labeling_tool/api/downloader.py`:
```python
"""Download V1 photo pairs (stitched + mask) into the local workspace.

Sequential with per-photo error capture: one bad URL never aborts the
batch. Returns the list of failed entries for the UI to surface/retry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import requests

from labeling_tool.session import naming

ProgressFn = Callable[[int, int], None]


def _download_to(url: str, dest: Path, timeout: int = 60) -> None:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def download_photos(photos: list[dict], origin_dir: Path, detected_dir: Path,
                    progress: ProgressFn | None = None,
                    timeout: int = 60) -> list[dict]:
    total = len(photos)
    failures: list[dict] = []
    for i, p in enumerate(photos, start=1):
        ts = int(p["timestamp"])
        try:
            _download_to(p["stitchedUrl"],
                         origin_dir / naming.stitched_filename(ts), timeout)
            _download_to(p["maskUrl"],
                         detected_dir / naming.mask_filename(ts), timeout)
        except Exception as e:  # noqa: BLE001 - capture & continue by design
            failures.append({"timestamp": ts, "error": str(e)})
        if progress is not None:
            progress(i, total)
    return failures
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_downloader.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/api/downloader.py labeling_tool/tests/test_downloader.py
git commit -m "feat(labeling_tool): photo pair downloader with failure capture"
```

---

## Task 10: 上传编排器(TDD)

**Files:**
- Create: `labeling_tool/api/uploader.py`
- Test: `labeling_tool/tests/test_uploader.py`

依赖说明:`upload_session` 接收一个**已构造好的 V4 items 列表**(每个含 `timestamp`、`maskS3Key`、`crackMetrics` 等,由 Task 3 的 `build_annotation_item` 产出)以及一个 `mask_bytes_for(timestamp) -> bytes` 回调取本地掩膜字节。它负责 100 分页 + V2→V3→V4 编排,不关心掩膜如何计算。

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_uploader.py`:
```python
from labeling_tool.api.uploader import upload_session


class FakeClient:
    def __init__(self):
        self.presigned_calls = []
        self.puts = []
        self.register_calls = []

    def request_presigned(self, session_id, files):
        self.presigned_calls.append((session_id, files))
        return {"urls": [
            {"filename": f["filename"],
             "s3Key": f"results/{session_id}/masks/{f['filename']}",
             "presignedUrl": f"https://s3/{f['filename']}",
             "cacheControl": "max-age=0, must-revalidate"} for f in files]}

    def put_mask(self, url, data, *, content_type, cache_control):
        self.puts.append(url)

    def register_annotations(self, *, edit_batch_id, session_id, items):
        self.register_calls.append((edit_batch_id, session_id, len(items)))
        return {"sessionId": session_id, "status": "saved",
                "updatedPhotoCount": len(items)}


def _item(ts):
    return {"timestamp": ts,
            "maskS3Key": f"results/43/masks/mask_{ts}.png",
            "pxPerCm": 10.0, "scaleSource": "aruco",
            "repairAreas": [], "crackMetrics": {}}


def test_uploads_single_batch_in_order():
    client = FakeClient()
    items = [_item(1), _item(2)]
    result = upload_session(
        client, session_id=43, items=items,
        mask_bytes_for=lambda ts: f"png{ts}".encode(),
        edit_batch_id="batch-xyz")
    assert result["uploaded"] == 2
    assert result["failed"] == []
    assert client.register_calls == [("batch-xyz", 43, 2)]
    assert len(client.puts) == 2


def test_paginates_over_100():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 items -> 2 batches
    result = upload_session(
        client, session_id=43, items=items,
        mask_bytes_for=lambda ts: b"x", edit_batch_id="b")
    assert result["uploaded"] == 150
    # 100 + 50
    assert [c[2] for c in client.register_calls] == [100, 50]
    # same editBatchId reused across pages
    assert {c[0] for c in client.register_calls} == {"b"}


def test_v4_failure_recorded_per_batch():
    class FailingRegister(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailingRegister()
    result = upload_session(
        client, session_id=43, items=[_item(1)],
        mask_bytes_for=lambda ts: b"x", edit_batch_id="b")
    assert result["uploaded"] == 0
    assert len(result["failed"]) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest labeling_tool/tests/test_uploader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.api.uploader'`

- [ ] **Step 3: 实现**

Create `labeling_tool/api/uploader.py`:
```python
"""Batch upload orchestration: V2 -> V3 -> V4, paginated at 100 items.

A single editBatchId is reused across pages and retries so the whole
session is idempotent (V4: same id -> 200, no DB reprocessing).
"""

from __future__ import annotations

from typing import Callable

from labeling_tool.session import naming

BATCH_LIMIT = 100

MaskBytesFn = Callable[[int], bytes]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def upload_session(client, *, session_id: int, items: list[dict],
                   mask_bytes_for: MaskBytesFn,
                   edit_batch_id: str) -> dict:
    """items: V4 item dicts (see annotation_payload.build_annotation_item).

    Returns {"uploaded": int, "failed": [{"timestamps": [...], "error": str}]}.
    """
    uploaded = 0
    failed: list[dict] = []

    for batch in _chunks(items, BATCH_LIMIT):
        timestamps = [it["timestamp"] for it in batch]
        try:
            # V2: presigned URLs for this batch's masks
            files = [{
                "filename": naming.mask_filename(ts),
                "timestamp": ts,
                "contentType": "image/png",
                "sizeBytes": len(mask_bytes_for(ts)),
            } for ts in timestamps]
            presigned = client.request_presigned(session_id, files)
            url_by_name = {u["filename"]: u for u in presigned["urls"]}

            # V3: PUT each mask to its presigned URL
            for ts in timestamps:
                u = url_by_name[naming.mask_filename(ts)]
                client.put_mask(
                    u["presignedUrl"], mask_bytes_for(ts),
                    content_type="image/png",
                    cache_control=u.get("cacheControl",
                                        "max-age=0, must-revalidate"))

            # V4: register the whole batch
            client.register_annotations(
                edit_batch_id=edit_batch_id, session_id=session_id,
                items=batch)
            uploaded += len(batch)
        except Exception as e:  # noqa: BLE001 - report per-batch, keep going
            failed.append({"timestamps": timestamps, "error": str(e)})

    return {"uploaded": uploaded, "failed": failed}
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest labeling_tool/tests/test_uploader.py -v`
Expected: 3 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest labeling_tool/tests -v`
Expected: 所有逻辑/API 测试 passed(约 25 个)。

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/api/uploader.py labeling_tool/tests/test_uploader.py
git commit -m "feat(labeling_tool): batch upload orchestration V2->V3->V4"
```

---

## Task 11: 连接向导对话框(GUI,手动验收)

**Files:**
- Create: `labeling_tool/ui/__init__.py`, `labeling_tool/ui/connect_dialog.py`

GUI 无自动化测试(本地交付物)。本任务产出可独立冒烟运行的对话框。

- [ ] **Step 1: 实现对话框**

Create `labeling_tool/ui/__init__.py`:
```python
```
(空文件)

Create `labeling_tool/ui/connect_dialog.py`:
```python
"""Startup connection wizard: collect creds, call V1, download, build manifest.

Returns a populated Workspace + Manifest on success. The caller (app.py)
then opens the main labeling window against that workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QSpinBox,
)

from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.api.downloader import download_photos
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session import naming

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(base: str, api_key: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"base": base, "apiKey": api_key}, indent=2),
        encoding="utf-8")


class ConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("연결 / 데이터 가져오기 (V1)")
        self.resize(520, 320)
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None

        cfg = _load_config()
        form = QFormLayout()
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.sp_session = QSpinBox(); self.sp_session.setRange(1, 10_000_000)
        self.sp_from = QSpinBox(); self.sp_from.setRange(0, 10_000_000)
        self.sp_to = QSpinBox(); self.sp_to.setRange(0, 10_000_000)
        form.addRow("BASE URL", self.ed_base)
        form.addRow("X-Viewer-Api-Key", self.ed_key)
        form.addRow("sessionId", self.sp_session)
        form.addRow("fromNum (0=미사용)", self.sp_from)
        form.addRow("toNum (0=미사용)", self.sp_to)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_fetch = QPushButton("가져오기 (V1 + 다운로드)")
        self.btn_open_local = QPushButton("이미 받은 세션 열기")
        self.btn_fetch.clicked.connect(self._on_fetch)
        self.btn_open_local.clicked.connect(self._on_open_local)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_open_local)
        btns.addStretch(1)
        btns.addWidget(self.btn_fetch)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.progress)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)

    def _zone(self) -> tuple[int | None, int | None]:
        f, t = self.sp_from.value(), self.sp_to.value()
        if f > 0 and t > 0:
            return f, t
        return None, None

    def _on_open_local(self):
        sid = self.sp_session.value()
        ws = Workspace.default(session_id=sid)
        if not ws.manifest_path.exists():
            QMessageBox.warning(self, "없음",
                                f"로컬 매니페스트 없음: {ws.manifest_path}")
            return
        self.workspace = ws
        self.manifest = Manifest.load(ws.manifest_path)
        self.accept()

    def _on_fetch(self):
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        sid = self.sp_session.value()
        if not base or not key:
            QMessageBox.warning(self, "입력 필요", "BASE/Key를 입력하세요.")
            return
        from_num, to_num = self._zone()
        client = ViewerApiClient(base_url=base, api_key=key)

        ws = Workspace.default(session_id=sid)
        ws.ensure()
        manifest = Manifest(session_id=sid, base=base)

        # ---- V1 with pagination ----
        try:
            photos = self._fetch_all_photos(client, sid, from_num, to_num)
        except ViewerApiError as e:
            QMessageBox.critical(self, "V1 실패", str(e))
            return
        if not photos:
            QMessageBox.warning(self, "비어있음", "조회된 사진이 없습니다.")
            return

        for p in photos:
            ts = int(p["timestamp"])
            manifest.add(PhotoEntry(
                filename=naming.stitched_filename(ts),
                timestamp=ts,
                photo_id=int(p.get("photoId", 0)),
                report_photo_num=int(p.get("reportPhotoNum", 0)),
                px_per_cm=float(p.get("pxPerCm") or 0.0),
                scale_source="aruco",
            ))

        # ---- download ----
        self.progress.setVisible(True)
        self.progress.setRange(0, len(photos))
        from PyQt5.QtWidgets import QApplication

        def _prog(done, total):
            self.progress.setValue(done)
            self.lbl_status.setText(f"다운로드 {done}/{total}")
            QApplication.processEvents()

        failures = download_photos(
            photos, ws.origin_dir, ws.detected_dir, progress=_prog)

        manifest.save(ws.manifest_path)
        _save_config(base, key)

        if failures:
            QMessageBox.warning(
                self, "일부 실패",
                f"{len(failures)}건 다운로드 실패. 나머지는 사용 가능합니다.")
        self.workspace = ws
        self.manifest = manifest
        self.accept()

    @staticmethod
    def _fetch_all_photos(client: ViewerApiClient, session_id: int,
                          from_num, to_num) -> list[dict]:
        if from_num is not None and to_num is not None:
            return client.list_photos(
                session_id, from_num=from_num, to_num=to_num)["photos"]
        out: list[dict] = []
        offset, limit = 0, 100
        while True:
            page = client.list_photos(session_id, offset=offset, limit=limit)
            out.extend(page["photos"])
            total = page.get("total", len(out))
            offset += limit
            if offset >= total or not page["photos"]:
                break
        return out
```

- [ ] **Step 2: 冒烟运行(确认导入与构造无误)**

Run: `python -c "from labeling_tool.ui.connect_dialog import ConnectDialog; print('ok')"`
Expected: 打印 `ok`(若环境无 PyQt5 显示后端,导入仍应成功;实际弹窗在 Task 13 端到端验收)。

- [ ] **Step 3: 提交**

```bash
git add labeling_tool/ui/__init__.py labeling_tool/ui/connect_dialog.py
git commit -m "feat(labeling_tool): startup connection wizard (V1 fetch + download)"
```

---

## Task 12: 扩展主窗口 —— 工作区目录注入 + 上传按钮

**Files:**
- Create: `labeling_tool/ui/main_window.py`

复用 `core` 的 `MainWindow`,子类化注入工作区目录,并在侧栏底部加「上传到 EC2」按钮。上传时从 manifest 取 `pxPerCm`/`timestamp`,读 `Labeling/` 掩膜字节,用 Task 3/10 构造并提交。

- [ ] **Step 1: 实现子类窗口**

Create `labeling_tool/ui/main_window.py`:
```python
"""MainWindow subclass wired to a V API Workspace + Manifest.

Reuses all core labeling behavior; adds session directory injection and a
single "Upload to EC2" action that runs V2->V3->V4 for edited photos.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QPushButton, QMessageBox, QProgressDialog, QApplication,
)

from labeling_tool.core.window.main_window import MainWindow as CoreMainWindow
from labeling_tool.core.bbox import load_bboxes
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
from labeling_tool.session import naming
from labeling_tool.annotation_payload import build_annotation_item
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.uploader import upload_session


class ViewerMainWindow(CoreMainWindow):
    def __init__(self, workspace: Workspace, manifest: Manifest,
                 client: ViewerApiClient | None):
        self._ws = workspace
        self._manifest = manifest
        self._client = client
        super().__init__()

        # Point the core tool at the workspace folders.
        self.origin_dir = workspace.origin_dir.resolve()
        self.detected_dir = workspace.detected_dir.resolve()
        self._sync_output_dir()                 # derives Labeling/ etc.
        # Override derived dirs to the workspace's explicit layout.
        self.output_dir = workspace.labeling_dir.resolve()
        self.rebuilt_dir = (workspace.session_dir / "Rebuilt").resolve()
        self.result_dir = workspace.result_dir.resolve()
        self._refresh_path_labels()
        self._reload_data()

        self._add_upload_button()

    # ------------------------------------------------------------------
    def _add_upload_button(self):
        self.btn_upload = QPushButton("EC2에 업로드 (V2→V3→V4)")
        self.btn_upload.setObjectName("primaryAction")
        self.btn_upload.clicked.connect(self._on_upload)
        # _panel_layout is the side panel's QVBoxLayout (exposed by the
        # ui_builder patch in Step 2). Insert above the trailing addStretch()
        # so the button sits at the bottom of the content, not floating.
        layout = getattr(self, "_panel_layout", None)
        if layout is not None:
            layout.insertWidget(layout.count() - 1, self.btn_upload)

    def _edited_filenames(self) -> list[str]:
        """Photos with a mask in Labeling/ (i.e. saved edits this session)."""
        out = []
        for fn in self._manifest.filenames_in_order():
            stem = Path(fn).stem
            mask_png = self.output_dir / f"{stem}.png"
            mask_alt = self.output_dir / naming.mask_filename(
                self._manifest.get(fn).timestamp)
            if mask_png.exists() or mask_alt.exists():
                out.append(fn)
        return out

    def _read_artifacts(self, filename: str):
        """Return (crack_mask, spalling_mask, boxes, mask_bytes) for a photo."""
        entry = self._manifest.get(filename)
        stem = Path(filename).stem
        mask_path = self.output_dir / f"{stem}.png"
        if not mask_path.exists():
            mask_path = self.output_dir / naming.mask_filename(entry.timestamp)
        bgr = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        crack = bgr[..., 2] if bgr is not None and bgr.ndim == 3 else None
        spall = bgr[..., 1] if bgr is not None and bgr.ndim == 3 else None
        boxes = load_bboxes(self.output_dir / f"{stem}.bbox.json")
        mask_bytes = mask_path.read_bytes()
        return crack, spall, boxes, mask_bytes

    def _on_upload(self):
        if self._client is None:
            QMessageBox.warning(self, "오프라인",
                                "API 클라이언트가 없어 업로드할 수 없습니다.")
            return
        self._save_all_artifacts(silent=True, only_if_edited=True)
        filenames = self._edited_filenames()
        if not filenames:
            QMessageBox.information(self, "없음", "업로드할 편집본이 없습니다.")
            return

        items: list[dict] = []
        mask_cache: dict[int, bytes] = {}
        for fn in filenames:
            entry = self._manifest.get(fn)
            crack, spall, boxes, mask_bytes = self._read_artifacts(fn)
            mask_cache[entry.timestamp] = mask_bytes
            px_per_cm = entry.px_per_cm or 0.0
            if px_per_cm <= 0:
                # Skip photos with no scale: V4 requires pxPerCm.
                continue
            items.append(build_annotation_item(
                timestamp=entry.timestamp,
                mask_s3_key=naming.mask_s3_key(
                    self._ws.session_id, entry.timestamp),
                px_per_cm=px_per_cm,
                scale_source=entry.scale_source,
                crack_mask=crack, spalling_mask=spall, boxes=boxes,
            ))

        if not items:
            QMessageBox.warning(self, "스케일 없음",
                                "pxPerCm가 있는 편집본이 없습니다 (ArUco 필요).")
            return

        dlg = QProgressDialog("업로드 중…", None, 0, 0, self)
        dlg.show(); QApplication.processEvents()
        batch_id = str(uuid.uuid4())
        try:
            result = upload_session(
                self._client, session_id=self._ws.session_id, items=items,
                mask_bytes_for=lambda ts: mask_cache[ts],
                edit_batch_id=batch_id)
        finally:
            dlg.close()

        self._manifest.mark_synced(
            [fn for fn in filenames
             if self._manifest.get(fn).timestamp in mask_cache],
            batch_id=batch_id)
        self._manifest.save(self._ws.manifest_path)

        if result["failed"]:
            QMessageBox.warning(
                self, "일부 실패",
                f"업로드 {result['uploaded']}건 성공, "
                f"{len(result['failed'])}개 배치 실패. 다시 시도하세요.")
        else:
            QMessageBox.information(
                self, "완료", f"{result['uploaded']}건 업로드 완료.")
```

- [ ] **Step 2: 暴露侧栏布局注入点(`_panel_layout`)—— 必改**

现有 `core/window/ui_builder.py::build_side_panel` 用的是局部变量 `panel_layout`,**并未**暴露给 window,且末尾有 `panel_layout.addStretch()`。需把该布局挂到 window 上,供上传按钮插入。

在 `labeling_tool/core/window/ui_builder.py` 中,找到这一行:
```python
    panel_layout.addStretch()
```
在它**之前**插入一行:
```python
    window._panel_layout = panel_layout
```
即改为:
```python
    panel_layout.addWidget(build_hint_group(window))
    window._panel_layout = panel_layout
    panel_layout.addStretch()
```

Run 验证: `grep -n "window._panel_layout" labeling_tool/core/window/ui_builder.py`
Expected: 命中一行。

- [ ] **Step 3: 冒烟导入**

Run: `python -c "from labeling_tool.ui.main_window import ViewerMainWindow; print('ok')"`
Expected: 打印 `ok`

- [ ] **Step 4: 提交**

```bash
git add labeling_tool/ui/main_window.py
# 若 Step 2 改动了 ui_builder:
git add labeling_tool/core/window/ui_builder.py
git commit -m "feat(labeling_tool): viewer main window with EC2 upload action"
```

---

## Task 13: 入口 app.py + 打包文件 + .gitignore + 文档

**Files:**
- Create: `labeling_tool/app.py`, `labeling_tool/requirements.txt`, `labeling_tool/README.md`
- Modify: `.gitignore`(忽略 `labeling_tool/config.json`)

- [ ] **Step 1: 入口**

Create `labeling_tool/app.py`:
```python
"""Local labeling tool entry point.

Flow: connection wizard (V1 fetch + download) -> main labeling window
wired to the per-session workspace -> manual batch upload (V2->V3->V4).
Run on a LOCAL PC (not the AI server).
"""

from __future__ import annotations

import os
import sys

# Prevent cv2's bundled Qt plugins from clashing with PyQt5 (same guard the
# original labeling GUI uses).
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.connect_dialog import ConnectDialog
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.api.client import ViewerApiClient


def main() -> int:
    app = QApplication(sys.argv)

    dialog = ConnectDialog()
    if not dialog.exec_():
        return 0  # user cancelled
    if dialog.workspace is None or dialog.manifest is None:
        return 0

    client = None
    base = dialog.ed_base.text().strip()
    key = dialog.ed_key.text().strip()
    if base and key:
        client = ViewerApiClient(base_url=base, api_key=key)

    win = ViewerMainWindow(dialog.workspace, dialog.manifest, client)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: requirements.txt**

Create `labeling_tool/requirements.txt`:
```
PyQt5
PyQt-Fluent-Widgets
opencv-python
numpy
scikit-image
requests
pycocotools
segment-anything
```

- [ ] **Step 3: README.md**

Create `labeling_tool/README.md`:
```markdown
# 本地标注工具 (labeling_tool)

AI 服务器产出拼接图/掩膜后,在**本地 PC** 上人工编辑均裂掩膜、生成保修区 OBB、
计算计测值,并通过 V API(V1~V4)回传 EC2。

## 安装

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r labeling_tool/requirements.txt
```

## 运行

从仓库根目录:

```bash
python -m labeling_tool.app
```

1. 弹出「连接向导」:填写 BASE URL、X-Viewer-Api-Key、sessionId,
   (可选)区域分担 fromNum/toNum。
2. 点「가져오기」→ 调 V1 列出照片 → 下载 stitched/mask 到
   `~/labeling_tool_data/session_{id}/{Origin,Detected}/`。
3. 标注:笔刷编辑掩膜、画保修区 OBB、ArUco 自动标尺。
4. 点「EC2에 업로드」→ 批量 V2→V3→V4 回传(每批 100,UUID 幂等)。

断网时可用「이미 받은 세션 열기」直接打开本地已下载会话继续标注。

## 配置

首次「가져오기」成功后,BASE/Key 会保存到 `labeling_tool/config.json`
(**已被 .gitignore 忽略,请勿提交**)。sessionId 每次手动输入。

## 测试

```bash
python -m pytest labeling_tool/tests -v
```
```

- [ ] **Step 4: .gitignore**

在仓库根 `.gitignore` 追加一行:
```
labeling_tool/config.json
```
Run: `grep -q '^labeling_tool/config.json$' .gitignore || printf 'labeling_tool/config.json\n' >> .gitignore`

- [ ] **Step 5: 全量回归 + 入口冒烟**

Run:
```bash
python -m pytest labeling_tool/tests -v
python -c "import labeling_tool.app as a; print('entry ok')"
```
Expected: 全部测试 passed;打印 `entry ok`。

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/app.py labeling_tool/requirements.txt labeling_tool/README.md .gitignore
git commit -m "feat(labeling_tool): app entry point, packaging files, docs"
```

---

## 端到端手动验收(实现后由用户执行)

1. `python -m labeling_tool.app`,在连接向导填真实 BASE/Key/sessionId,点「가져오기」。
2. 确认 `~/labeling_tool_data/session_{id}/Origin|Detected` 下出现 `stitched_*.jpg` / `mask_*.png`,主界面文件列表已填好。
3. 编辑一张掩膜 + 画一个 OBB,确认 ArUco 标尺生效(右侧 scale 非 `--`),保存。
4. 点「EC2에 업로드」,确认返回成功;在 EC2/Web 端核对该 timestamp 的掩膜/OBB/metrics 已更新。
5. 重复点上传(同一会话未改动)→ 应幂等无副作用。

---

## Self-Review(计划自检结果)

**Spec 覆盖核对:**
- V1 获取 + 下载 → Task 7(client V1)+ Task 9(downloader)+ Task 11(向导编排分页)✓
- V2/V3/V4 上传 → Task 8(client)+ Task 10(uploader 分页+幂等)+ Task 12(窗口触发)✓
- 自包含 core 复制 → Task 1 ✓
- minWidthMm 缺口 → Task 2 ✓
- V4 全字段(含可选 bboxAreaMm2/bboxCount/pxPerMm/defectType)→ Task 3 ✓
- 工作区 `~/labeling_tool_data/session_{id}/` → Task 5 ✓
- manifest filename↔timestamp + synced → Task 4 + Task 6 ✓
- 连接向导(启动弹窗 + 打开本地会话)→ Task 11 ✓
- 批量手动上传按钮 → Task 12 ✓
- config.json 仅存 BASE/Key + .gitignore → Task 11 + Task 13 ✓
- 错误码处理 → Task 7(`_raise_for_error` + ViewerApiError)✓

**占位扫描:** 无 TBD/TODO;每个代码步骤含完整代码。

**类型/命名一致性:** `ViewerApiClient` 方法名(`list_photos`/`request_presigned`/`put_mask`/`register_annotations`)在 Task 7/8/10/12 间一致;`build_annotation_item` 关键字参数在 Task 3/12 一致;`Workspace`/`Manifest`/`PhotoEntry` 字段在 Task 4/5/6/11/12 一致;`naming.*` 函数签名在 Task 4/9/10/12 一致。

**已知风险(实现时验证):**
- Task 12 Step 2:`_panel_layout` 属性可能在现有 `ui_builder` 中不存在,已给出补丁指引。
- core 的 Detected 掩膜通道约定(crack=R 通道、spalling=G 通道)沿用现有 `mask_io`/`_save_all_artifacts` 逻辑;上传读回时按同约定拆通道(Task 12 `_read_artifacts`)。
