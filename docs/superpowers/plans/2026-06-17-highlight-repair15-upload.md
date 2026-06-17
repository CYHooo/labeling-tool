# 균열 하이라이트 + 15cm 경계 + v1.0.8 上传 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On edit-confirm, generate two derived masks locally (균열 하이라이트 `high_{ts}.png`, 15cm 경계 검증 `15_{ts}.png`), visualize both on the canvas behind toggles, and upload mask+high+repair15 per photo via the v1.0.8 contract (V2 3 files / V3 3 PUTs / V4 two new required keys).
**Architecture:** A centralized pure-function module `core/derived_masks.py` produces both masks from the in-memory crack/spalling layers. `_save_all_artifacts` writes them to two new workspace folders (`HighLight/`, `Repair15/`) and refreshes the canvas with the just-built arrays. The canvas reads saved files on image load. The upload chain (`annotation_payload` -> `api/uploader` -> `upload_worker`/`upload_session_cli`) is upgraded end-to-end to read three byte blobs per photo and register two new S3 keys.
**Tech Stack:** Python 3.10+, NumPy, OpenCV (cv2), PyQt5. No new runtime dependencies. Tests run with `.venv/bin/python -m pytest`.

## Global Constraints
- CLASS_LABELS source of truth: `labeling_tool/core/constants.CLASS_LABELS = {"crack": 1, "spalling": 2}`; `BACKGROUND_LABEL = 0`. Never hardcode 1/2 — import from constants.
- highlight = each class region dilated 10px (cv2.MORPH_ELLIPSE kernel, 21x21 i.e. radius 10), re-encoded single-channel 0/1/2 via CLASS_LABELS, spalling(2) written first then crack(1) -> crack precedence on overlap.
- repair15 = foreground union (crack>0 | spalling>0) dilated by `round(15 * px_per_cm)` px, output single-channel uint8 FILLED 0/255 (NOT a contour); requires px_per_cm.
- upload v1.0.8 = V2 presign 3 files per photo (mask_/high_/15_), V3 PUT in order mask -> high -> 15, V4 item requires `maskS3Key`, `highlightS3Key`, `repair15S3Key` (+ existing pxPerCm/scaleSource/repairAreas/crackMetrics). V2 files[] fields = filename/timestamp/contentType/sizeBytes (NO fileType); server distinguishes by mask_/high_/15_ prefix.
- skip photo if any of mask/high/15 missing (vlog().warning), consistent with the existing missing-mask skip.
- canvas display: highlight = translucent YELLOW (255,255,0, alpha ~90) halo of highlight_mask>0 reusing the resize-to-widget composite; repair15 = OUTER-CONTOUR LINE ONLY drawn cyan (0,200,255) 2px (the saved file stays FILLED 0/255).
- display source: canvas reads saved HighLight/Repair15 files on load, and is refreshed in-place with the freshly-built arrays on save.
- no new runtime deps; Python 3.10+.
---

## Task 1 — core/derived_masks.py + tests/test_derived_masks.py

**Files**
- Create: `labeling_tool/core/derived_masks.py`
- Create: `labeling_tool/tests/test_derived_masks.py`

**Interfaces**
- Consumes: `labeling_tool.core.constants.CLASS_LABELS` (dict), `cv2`, `numpy`.
- Produces:
  - `build_highlight(crack: np.ndarray | None, spalling: np.ndarray | None) -> np.ndarray` — single-channel uint8, values in {0,1,2}.
  - `build_repair15(crack: np.ndarray | None, spalling: np.ndarray | None, px_per_cm: float) -> np.ndarray` — single-channel uint8, values in {0,255}.

### TDD steps

- [ ] **1.1 Write the failing tests** in `labeling_tool/tests/test_derived_masks.py`:

```python
import numpy as np
import pytest

from labeling_tool.core.derived_masks import build_highlight, build_repair15
from labeling_tool.core.constants import CLASS_LABELS


def _crack():
    m = np.zeros((80, 80), np.uint8)
    m[38:42, 20:60] = 255          # a thin horizontal crack line
    return m


def _spalling():
    m = np.zeros((80, 80), np.uint8)
    m[10:20, 10:20] = 255          # a small spalling blob
    return m


# ---- build_highlight ----------------------------------------------------
def test_highlight_grows_foreground_by_about_10px():
    crack = _crack()
    hi = build_highlight(crack, None)
    # dilation by radius 10 makes the foreground strictly larger.
    assert int((hi > 0).sum()) > int((crack > 0).sum())


def test_highlight_values_are_subset_of_0_1_2():
    hi = build_highlight(_crack(), _spalling())
    assert set(np.unique(hi)).issubset({0, CLASS_LABELS["crack"], CLASS_LABELS["spalling"]})


def test_highlight_crack_precedence_on_overlap():
    # crack and spalling occupy the SAME pixels -> crack (1) must win.
    crack = np.zeros((40, 40), np.uint8); crack[18:22, 18:22] = 255
    spall = np.zeros((40, 40), np.uint8); spall[18:22, 18:22] = 255
    hi = build_highlight(crack, spall)
    assert hi[20, 20] == CLASS_LABELS["crack"]


def test_highlight_both_none_raises():
    with pytest.raises(ValueError):
        build_highlight(None, None)


# ---- build_repair15 -----------------------------------------------------
def test_repair15_output_is_0_or_255():
    r = build_repair15(_crack(), None, px_per_cm=1.0)
    assert set(np.unique(r)).issubset({0, 255})


def test_repair15_grows_with_larger_px_per_cm():
    small = build_repair15(_crack(), None, px_per_cm=0.5)   # ~8px dilate
    large = build_repair15(_crack(), None, px_per_cm=2.0)   # ~30px dilate
    assert int((large == 255).sum()) > int((small == 255).sum())


def test_repair15_region_larger_than_input_mask():
    crack = _crack()
    r = build_repair15(crack, None, px_per_cm=1.0)          # ~15px dilate
    assert int((r == 255).sum()) > int((crack > 0).sum())


def test_repair15_both_none_raises():
    with pytest.raises(ValueError):
        build_repair15(None, None, px_per_cm=1.0)
```

- [ ] **1.2 Run the tests, confirm they fail** (module missing):
  `.venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -q`
  Expected: collection/import error or 8 failures (`ModuleNotFoundError: labeling_tool.core.derived_masks`).

- [ ] **1.3 Implement** `labeling_tool/core/derived_masks.py`:

```python
"""Derived masks for the local Photo Viewer: 균열 하이라이트 + 15cm 경계.

Pure functions (no Qt, no I/O). Generated at save time from the in-memory
crack/spalling layers, written to HighLight/ and Repair15/, and uploaded
to S3 as high_{ts}.png / 15_{ts}.png.
"""

from __future__ import annotations

import cv2
import numpy as np

from labeling_tool.core.constants import CLASS_LABELS

# Highlight: every class region grows by this many px so the defect reads
# clearly on the web viewer. Ellipse kernel of radius 10 (21x21).
_HIGHLIGHT_DILATE_PX = 10
# Repair15: the foreground union is padded by 15 cm worth of pixels.
_REPAIR15_CM = 15.0


def _ellipse_kernel(radius_px: int) -> np.ndarray:
    r = max(1, int(radius_px))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _binary(layer: np.ndarray | None) -> np.ndarray | None:
    if layer is None:
        return None
    return (layer > 0).astype(np.uint8)


def build_highlight(crack: np.ndarray | None,
                    spalling: np.ndarray | None) -> np.ndarray:
    """Dilate each class by 10px and re-encode to a single-channel 0/1/2 mask.

    spalling (2) is written first, then crack (1) overwrites it -> crack
    precedence on overlap. Raises ValueError when both layers are None.
    """
    cb = _binary(crack)
    sb = _binary(spalling)
    if cb is None and sb is None:
        raise ValueError("build_highlight requires at least one of crack/spalling")

    shape = cb.shape if cb is not None else sb.shape
    out = np.zeros(shape, dtype=np.uint8)
    kernel = _ellipse_kernel(_HIGHLIGHT_DILATE_PX)

    if sb is not None:
        grown = cv2.dilate(sb, kernel)
        out[grown > 0] = CLASS_LABELS["spalling"]
    if cb is not None:
        grown = cv2.dilate(cb, kernel)
        out[grown > 0] = CLASS_LABELS["crack"]   # crack precedence
    return out


def build_repair15(crack: np.ndarray | None,
                   spalling: np.ndarray | None,
                   px_per_cm: float) -> np.ndarray:
    """Foreground union dilated by round(15*px_per_cm) px, FILLED 0/255.

    Raises ValueError when both layers are None.
    """
    cb = _binary(crack)
    sb = _binary(spalling)
    if cb is None and sb is None:
        raise ValueError("build_repair15 requires at least one of crack/spalling")

    shape = cb.shape if cb is not None else sb.shape
    union = np.zeros(shape, dtype=np.uint8)
    if cb is not None:
        union |= cb
    if sb is not None:
        union |= sb

    pad_px = int(round(_REPAIR15_CM * float(px_per_cm)))
    grown = cv2.dilate(union, _ellipse_kernel(pad_px)) if pad_px > 0 else union
    return np.where(grown > 0, np.uint8(255), np.uint8(0)).astype(np.uint8)
```

- [ ] **1.4 Run the tests, confirm green**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -q`
  Expected: `8 passed`.

- [ ] **1.5 Commit**:
  `git add labeling_tool/core/derived_masks.py labeling_tool/tests/test_derived_masks.py`
  `git commit -m "feat(masks): add build_highlight/build_repair15 derived-mask generators"`

---

## Task 2 — naming.py additions + tests/test_naming.py

**Files**
- Modify: `labeling_tool/session/naming.py`
- Modify: `labeling_tool/tests/test_naming.py`

**Interfaces**
- Produces:
  - `high_filename(timestamp: int) -> str` = `"high_{ts}.png"`
  - `repair15_filename(timestamp: int) -> str` = `"15_{ts}.png"`
  - `high_s3_key(session_id: int, timestamp: int) -> str` = `"results/{sid}/masks/high_{ts}.png"`
  - `repair15_s3_key(session_id: int, timestamp: int) -> str` = `"results/{sid}/masks/15_{ts}.png"`

### TDD steps

- [ ] **2.1 Add failing tests** to `labeling_tool/tests/test_naming.py`:

```python
def test_high_filename():
    assert naming.high_filename(1717572612000) == "high_1717572612000.png"


def test_repair15_filename():
    assert naming.repair15_filename(1717572612000) == "15_1717572612000.png"


def test_high_s3_key():
    assert naming.high_s3_key(43, 1717572612000) == \
        "results/43/masks/high_1717572612000.png"


def test_repair15_s3_key():
    assert naming.repair15_s3_key(43, 1717572612000) == \
        "results/43/masks/15_1717572612000.png"
```

- [ ] **2.2 Run, confirm failure**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_naming.py -q`
  Expected: 4 new failures (`AttributeError: module 'labeling_tool.session.naming' has no attribute 'high_filename'`).

- [ ] **2.3 Implement** — append to `labeling_tool/session/naming.py` (after `mask_s3_key`, ~line 37). Also bump the module docstring header reference to v1.0.8:

```python
def high_filename(timestamp: int) -> str:
    return f"high_{int(timestamp)}.png"


def repair15_filename(timestamp: int) -> str:
    return f"15_{int(timestamp)}.png"


def high_s3_key(session_id: int, timestamp: int) -> str:
    return f"results/{int(session_id)}/masks/high_{int(timestamp)}.png"


def repair15_s3_key(session_id: int, timestamp: int) -> str:
    return f"results/{int(session_id)}/masks/15_{int(timestamp)}.png"
```

- [ ] **2.4 Run, confirm green**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_naming.py -q`
  Expected: all naming tests pass (existing 7 + new 4 = 11 passed).

- [ ] **2.5 Commit**:
  `git add labeling_tool/session/naming.py labeling_tool/tests/test_naming.py`
  `git commit -m "feat(naming): add high_/15_ filename + s3 key helpers for v1.0.8"`

---

## Task 3 — workspace.py + tests/test_workspace.py

**Files**
- Modify: `labeling_tool/session/workspace.py`
- Modify: `labeling_tool/tests/test_workspace.py`

**Interfaces**
- Produces on `Workspace`:
  - `highlight_dir` property -> `session_dir / "HighLight"`
  - `repair15_dir` property -> `session_dir / "Repair15"`
  - `ensure()` now also creates both.

### TDD steps

- [ ] **3.1 Update tests** `labeling_tool/tests/test_workspace.py`:
  - In `test_layout_paths` add:
    ```python
    assert ws.highlight_dir == tmp_path / "session_43" / "HighLight"
    assert ws.repair15_dir == tmp_path / "session_43" / "Repair15"
    ```
  - In `test_ensure_creates_dirs` extend the loop:
    ```python
    for d in (ws.origin_dir, ws.detected_dir, ws.labeling_dir,
              ws.result_dir, ws.highlight_dir, ws.repair15_dir):
        assert d.is_dir()
    ```

- [ ] **3.2 Run, confirm failure**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_workspace.py -q`
  Expected: `test_layout_paths` + `test_ensure_creates_dirs` fail (`AttributeError: 'Workspace' object has no attribute 'highlight_dir'`).

- [ ] **3.3 Implement** in `labeling_tool/session/workspace.py`:
  - Update module docstring dir list (line 3) to:
    `labeling_tool/data/session_{id}/{Origin,Detected,Labeling,Result,HighLight,Repair15}/ + manifest.json`
  - Add two properties after `result_dir` (~line 44):
    ```python
    @property
    def highlight_dir(self) -> Path:
        return self.session_dir / "HighLight"

    @property
    def repair15_dir(self) -> Path:
        return self.session_dir / "Repair15"
    ```
  - Extend `ensure()` loop (~line 51) to include both new dirs:
    ```python
    def ensure(self) -> None:
        for d in (self.origin_dir, self.detected_dir,
                  self.labeling_dir, self.result_dir,
                  self.highlight_dir, self.repair15_dir):
            d.mkdir(parents=True, exist_ok=True)
    ```

- [ ] **3.4 Run, confirm green**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_workspace.py -q`
  Expected: all workspace tests pass.

- [ ] **3.5 Commit**:
  `git add labeling_tool/session/workspace.py labeling_tool/tests/test_workspace.py`
  `git commit -m "feat(workspace): add HighLight/ and Repair15/ session dirs"`

---

## Task 4 — annotation_payload.py + tests/test_annotation_payload.py

**Files**
- Modify: `labeling_tool/annotation_payload.py`
- Modify: `labeling_tool/tests/test_annotation_payload.py`

**Interfaces**
- Consumes (new required kwargs): `highlight_s3_key: str`, `repair15_s3_key: str`.
- Produces: returned dict gains `"highlightS3Key"` and `"repair15S3Key"`.

### TDD steps

- [ ] **4.1 Update existing tests** in `labeling_tool/tests/test_annotation_payload.py` — every `build_annotation_item(...)` call must pass the two new kwargs, and add assertions. The four call sites are at lines ~16, ~31, ~48/55, ~65. Add to each call:
  ```python
  highlight_s3_key="results/43/masks/high_1.png",
  repair15_s3_key="results/43/masks/15_1.png",
  ```
  (Use the real ts in `test_repair_areas_use_camelcase_angle`, e.g. `high_1717572612000.png` / `15_1717572612000.png`.)
  In `test_repair_areas_use_camelcase_angle` add:
  ```python
  assert item["highlightS3Key"] == "results/43/masks/high_1717572612000.png"
  assert item["repair15S3Key"] == "results/43/masks/15_1717572612000.png"
  ```

- [ ] **4.2 Run, confirm failure**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_annotation_payload.py -q`
  Expected: `TypeError: build_annotation_item() missing 2 required keyword-only arguments: 'highlight_s3_key' and 'repair15_s3_key'` (once tests pass the kwargs) OR KeyError on the new assertions if implemented partially. First failure surfaces because the function does not accept the kwargs yet.

- [ ] **4.3 Implement** in `labeling_tool/annotation_payload.py`:
  - Add to the signature (after `mask_s3_key: str,`, ~line 30):
    ```python
    highlight_s3_key: str,
    repair15_s3_key: str,
    ```
  - Add to the returned dict (after `"maskS3Key": mask_s3_key,`, ~line 73):
    ```python
    "highlightS3Key": highlight_s3_key,
    "repair15S3Key": repair15_s3_key,
    ```

- [ ] **4.4 Run, confirm green**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_annotation_payload.py -q`
  Expected: all annotation-payload tests pass.

- [ ] **4.5 Commit**:
  `git add labeling_tool/annotation_payload.py labeling_tool/tests/test_annotation_payload.py`
  `git commit -m "feat(payload): require highlightS3Key/repair15S3Key in annotation item"`

---

## Task 5 — api/uploader.py + tests/test_uploader.py

**Files**
- Modify: `labeling_tool/api/uploader.py`
- Modify: `labeling_tool/tests/test_uploader.py`

**Interfaces**
- Consumes (changed): `bytes_for: Callable[[int], dict]` returning `{"mask": bytes, "high": bytes, "repair15": bytes}` (replaces `mask_bytes_for: Callable[[int], bytes]`).
- Produces: per photo presigns 3 files (`naming.mask_filename` / `naming.high_filename` / `naming.repair15_filename`), PUTs in order mask -> high -> 15, then registers. Progress fires once per photo (after its 3 PUTs), keeping monotonic/total semantics. Return shape unchanged: `{"uploaded": int, "failed": [...]}`.

### TDD steps

- [ ] **5.1 Rewrite the tests** `labeling_tool/tests/test_uploader.py`. Update `_item` to include the two new keys, rename the callback in every call to `bytes_for` returning the dict, and assert `len(client.puts) == 3 * len(items)`:

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
            "highlightS3Key": f"results/43/masks/high_{ts}.png",
            "repair15S3Key": f"results/43/masks/15_{ts}.png",
            "pxPerCm": 10.0, "scaleSource": "aruco",
            "repairAreas": [], "crackMetrics": {}}


def _bytes(ts):
    return {"mask": f"m{ts}".encode(),
            "high": f"h{ts}".encode(),
            "repair15": f"r{ts}".encode()}


def test_uploads_single_batch_in_order():
    client = FakeClient()
    items = [_item(1), _item(2)]
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="batch-xyz")
    assert result["uploaded"] == 2
    assert result["failed"] == []
    assert client.register_calls == [("batch-xyz", 43, 2)]
    assert len(client.puts) == 6                       # 3 PUTs * 2 photos
    # mask -> high -> 15 order for the first photo
    assert client.puts[0] == "https://s3/mask_1.png"
    assert client.puts[1] == "https://s3/high_1.png"
    assert client.puts[2] == "https://s3/15_1.png"


def test_paginates_over_100():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 items -> 2 batches
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="b")
    assert result["uploaded"] == 150
    assert [c[2] for c in client.register_calls] == [100, 50]
    assert {c[0] for c in client.register_calls} == {"b"}
    assert len(client.puts) == 450                     # 3 * 150


def test_v4_failure_recorded_per_batch():
    class FailingRegister(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailingRegister()
    result = upload_session(
        client, session_id=43, items=[_item(1)],
        bytes_for=_bytes, edit_batch_id="b")
    assert result["uploaded"] == 0
    assert len(result["failed"]) == 1


def test_progress_reports_each_item():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 -> 2 batches
    seen = []
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="b",
        progress=lambda done, total: seen.append((done, total)))
    assert result["uploaded"] == 150
    assert seen[-1] == (150, 150)
    assert all(d <= t for d, t in seen)
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_progress_completes_even_when_batch_fails():
    class FailReg(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailReg()
    seen = []
    result = upload_session(
        client, session_id=43, items=[_item(1), _item(2)],
        bytes_for=_bytes, edit_batch_id="b",
        progress=lambda done, total: seen.append((done, total)))
    assert result["uploaded"] == 0
    assert seen[-1] == (2, 2)
```

- [ ] **5.2 Run, confirm failure**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_uploader.py -q`
  Expected: failures — `TypeError: upload_session() got an unexpected keyword argument 'bytes_for'`.

- [ ] **5.3 Implement** — replace the whole body of `labeling_tool/api/uploader.py` with:

```python
"""Batch upload orchestration: presigned -> S3 PUT -> register, paginated at 100 items.

A single editBatchId is reused across pages and retries so the whole
session is idempotent (register: same id -> 200, no DB reprocessing).

Per v1.0.8 each photo uploads three files: mask -> high -> 15 (3 PUTs),
then the batch is registered with maskS3Key/highlightS3Key/repair15S3Key.
"""

from __future__ import annotations

from typing import Callable

from labeling_tool.session import naming

BATCH_LIMIT = 100

# Returns the three byte blobs for one photo: {"mask":..,"high":..,"repair15":..}.
BytesFn = Callable[[int], dict]
ProgressFn = Callable[[int, int], None]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def upload_session(client, *, session_id: int, items: list[dict],
                   bytes_for: BytesFn,
                   edit_batch_id: str,
                   progress: ProgressFn | None = None) -> dict:
    """items: register-annotation item dicts (see annotation_payload.build_annotation_item).

    bytes_for(ts) -> {"mask": bytes, "high": bytes, "repair15": bytes}.

    progress(done, total) fires once per photo (after its 3 PUTs) so the caller
    can drive a determinate bar; total is the full item count.

    Returns {"uploaded": int, "failed": [{"timestamps": [...], "error": str}]}.
    """
    uploaded = 0
    failed: list[dict] = []
    total = len(items)
    base = 0   # items in batches already finished (success or failure)

    for batch in _chunks(items, BATCH_LIMIT):
        timestamps = [it["timestamp"] for it in batch]
        # Read each photo's 3 blobs once; reuse for sizeBytes + PUT.
        batch_bytes = {ts: bytes_for(ts) for ts in timestamps}
        try:
            # presigned URLs: 3 files per photo (mask/high/15)
            files = []
            for ts in timestamps:
                blobs = batch_bytes[ts]
                files.append({"filename": naming.mask_filename(ts),
                              "timestamp": ts, "contentType": "image/png",
                              "sizeBytes": len(blobs["mask"])})
                files.append({"filename": naming.high_filename(ts),
                              "timestamp": ts, "contentType": "image/png",
                              "sizeBytes": len(blobs["high"])})
                files.append({"filename": naming.repair15_filename(ts),
                              "timestamp": ts, "contentType": "image/png",
                              "sizeBytes": len(blobs["repair15"])})
            presigned = client.request_presigned(session_id, files)
            url_by_name = {u["filename"]: u for u in presigned["urls"]}

            # PUT mask -> high -> 15 for each photo, then advance progress once.
            for i, ts in enumerate(timestamps, start=1):
                blobs = batch_bytes[ts]
                for kind, fname in (("mask", naming.mask_filename(ts)),
                                    ("high", naming.high_filename(ts)),
                                    ("repair15", naming.repair15_filename(ts))):
                    u = url_by_name[fname]
                    client.put_mask(
                        u["presignedUrl"], blobs[kind],
                        content_type="image/png",
                        cache_control=u.get("cacheControl",
                                            "max-age=0, must-revalidate"))
                if progress is not None:
                    progress(base + i, total)

            client.register_annotations(
                edit_batch_id=edit_batch_id, session_id=session_id,
                items=batch)
            uploaded += len(batch)
        except Exception as e:  # noqa: BLE001 - report per-batch, keep going
            failed.append({"timestamps": timestamps, "error": str(e)})
        finally:
            base += len(batch)
            if progress is not None:
                progress(base, total)

    return {"uploaded": uploaded, "failed": failed}
```

- [ ] **5.4 Run, confirm green**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_uploader.py -q`
  Expected: all 5 uploader tests pass.

- [ ] **5.5 Commit**:
  `git add labeling_tool/api/uploader.py labeling_tool/tests/test_uploader.py`
  `git commit -m "feat(uploader): upload mask+high+repair15 per photo (v1.0.8 3-file)"`

---

## Task 6 — ui/upload_worker.py + scripts/upload_session_cli.py + tests/test_upload_worker.py

**Files**
- Modify: `labeling_tool/ui/upload_worker.py`
- Modify: `labeling_tool/scripts/upload_session_cli.py`
- Modify: `labeling_tool/tests/test_upload_worker.py`

**Interfaces**
- Both build loops now read 3 local files per photo: `Labeling/<stem>_mask.png`, `HighLight/<stem>_mask.png`, `Repair15/<stem>_mask.png`.
  - Worker derives the two extra dirs from `Path(self._labeling_dir).parent / "HighLight"` and `/ "Repair15"`.
  - CLI uses `ws.highlight_dir` / `ws.repair15_dir` with `mask_store.mask_name(fn)`.
- If mask OR high OR repair15 is missing -> skip the photo (`vlog().warning`).
- Cache becomes `{ts: {"mask":.., "high":.., "repair15":..}}`; pass `bytes_for=lambda ts: cache[ts]`.
- `build_annotation_item(...)` now also receives `highlight_s3_key=naming.high_s3_key(sid, ts)` and `repair15_s3_key=naming.repair15_s3_key(sid, ts)`.

### TDD steps

- [ ] **6.1 Update `tests/test_upload_worker.py`** so `_setup_labeling` writes the HighLight/ and Repair15/ companion files (named via `mask_store.mask_name(stitched_filename(ts))`) next to the Labeling mask, all under sibling dirs of `tmp_path`. Because the worker derives HighLight/Repair15 from `labeling_dir.parent`, point `labeling_dir` at `tmp_path / "Labeling"` and create the three sibling folders:

```python
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.upload_worker import UploadWorker
from labeling_tool.tests.test_uploader import FakeClient
from labeling_tool.session import naming, mask_store
from labeling_tool.core.bbox import save_bboxes

_app = QApplication.instance() or QApplication([])


def _setup_labeling(tmp_path, ts_list):
    labeling = tmp_path / "Labeling"
    high = tmp_path / "HighLight"
    rep = tmp_path / "Repair15"
    for d in (labeling, high, rep):
        d.mkdir(parents=True, exist_ok=True)
    for ts in ts_list:
        stitched = naming.stitched_filename(ts)
        name = mask_store.mask_name(stitched)            # {stem}_mask.png
        # Labeling mask carries the real crack channel for metrics.
        m = np.zeros((40, 40, 3), np.uint8)
        m[18:23, 5:35, 2] = 255                          # R = crack
        cv2.imwrite(str(labeling / name), m)
        # HighLight + Repair15 just need to exist with valid PNG bytes.
        cv2.imwrite(str(high / name), np.zeros((40, 40), np.uint8))
        cv2.imwrite(str(rep / name), np.zeros((40, 40), np.uint8))
        stem = Path(stitched).stem
        save_bboxes(labeling / f"{stem}.bbox.json", stitched, [], 10.0, "aruco")
    return [{"filename": naming.stitched_filename(ts), "timestamp": ts,
             "px_per_cm": 10.0, "scale_source": "aruco"} for ts in ts_list]


def test_worker_builds_items_and_uploads(tmp_path):
    specs = _setup_labeling(tmp_path, [1, 2])
    client = FakeClient()
    worker = UploadWorker(client, session_id=43, specs=specs,
                          labeling_dir=str(tmp_path / "Labeling"),
                          edit_batch_id="b")
    prepare, upload, results = [], [], []
    worker.progress.connect(
        lambda d, t, ph: (prepare if ph == "prepare" else upload).append((d, t)))
    worker.done.connect(lambda r: results.append(r))
    worker.run()
    assert results and results[0]["uploaded"] == 2
    assert results[0]["batch_id"] == "b"
    assert set(results[0]["timestamps"]) == {1, 2}
    assert prepare[-1] == (2, 2)
    assert upload[-1] == (2, 2)
    assert len(client.puts) == 6                          # 3 PUTs * 2 photos


def test_worker_skips_missing_masks(tmp_path):
    (tmp_path / "Labeling").mkdir()
    specs = [{"filename": naming.stitched_filename(99), "timestamp": 99,
              "px_per_cm": 10.0, "scale_source": "aruco"}]   # no files on disk
    worker = UploadWorker(FakeClient(), session_id=43, specs=specs,
                          labeling_dir=str(tmp_path / "Labeling"),
                          edit_batch_id="b")
    results = []
    worker.done.connect(lambda r: results.append(r))
    worker.run()
    assert results and results[0]["uploaded"] == 0
    assert results[0]["timestamps"] == []
```

- [ ] **6.2 Run, confirm failure**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_upload_worker.py -q`
  Expected: failures (puts count 6 vs old 2; and/or `TypeError: build_annotation_item() missing ... highlight_s3_key`; and/or `upload_session() got an unexpected keyword argument 'bytes_for'`).

- [ ] **6.3 Implement worker** — edit `labeling_tool/ui/upload_worker.py`:
  - Replace `_build_items` body so the cache holds dicts and three files are read; skip when any is missing:

```python
    def _build_items(self):
        items, cache = [], {}
        total = len(self._specs)
        ldir = Path(self._labeling_dir)
        hdir = ldir.parent / "HighLight"
        rdir = ldir.parent / "Repair15"
        vlog().info("prepare start: %d items", total)
        for i, spec in enumerate(self._specs, start=1):
            fn = spec["filename"]
            ts = spec["timestamp"]
            name = mask_store.mask_name(fn)
            mask_path = ldir / name
            high_path = hdir / name
            rep_path = rdir / name
            if not (mask_path.exists() and high_path.exists() and rep_path.exists()):
                vlog().warning("prepare skip ts=%s: missing mask/high/repair15", ts)
                continue
            t = time.perf_counter()
            raw = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
            crack, spall = (None, None)
            if raw is not None:
                crack, spall = decode_mask(raw, mask_path=str(mask_path))
            boxes = load_bboxes(ldir / mask_store.bbox_name(fn))
            measured = load_scale(ldir / mask_store.bbox_name(fn))
            px = measured if measured else (spec.get("px_per_cm") or 0.0)
            if px <= 0:
                continue
            cache[ts] = {"mask": mask_path.read_bytes(),
                         "high": high_path.read_bytes(),
                         "repair15": rep_path.read_bytes()}
            item = build_annotation_item(
                timestamp=ts,
                mask_s3_key=naming.mask_s3_key(self._session_id, ts),
                highlight_s3_key=naming.high_s3_key(self._session_id, ts),
                repair15_s3_key=naming.repair15_s3_key(self._session_id, ts),
                px_per_cm=px, scale_source=spec.get("scale_source", "aruco"),
                crack_mask=crack, spalling_mask=spall, boxes=boxes)
            items.append(item)
            cm = item["crackMetrics"]
            vlog().info("prepare ts=%s metrics lenMm=%.0f defect=%s "
                        "(%.0f ms) [%d/%d]", ts, cm["lengthMm"], cm["defectType"],
                        (time.perf_counter() - t) * 1000, i, total)
            self.progress.emit(i, total, "prepare")
        vlog().info("prepare done: %d items", len(items))
        return items, cache
```
  - In `run()` rename the local var `mask_cache` -> `cache` and change the upload call:
    ```python
    items, cache = self._build_items()
    ...
    result = upload_session(
        self._client, session_id=self._session_id, items=items,
        bytes_for=lambda ts: cache[ts],
        edit_batch_id=self._batch_id,
        progress=lambda d, t: self.progress.emit(d, t, "upload"))
    result["timestamps"] = list(cache.keys())
    ```

- [ ] **6.4 Implement CLI** — edit `labeling_tool/scripts/upload_session_cli.py` build loop (lines ~39-83):
  - After `stem = Path(fn).stem` resolve all three paths via `mask_store.mask_name`:
    ```python
    from labeling_tool.session import mask_store   # add to imports
    ...
    name = mask_store.mask_name(fn)
    mask_path = ws.labeling_dir / name
    high_path = ws.highlight_dir / name
    rep_path = ws.repair15_dir / name
    if not (mask_path.exists() and high_path.exists() and rep_path.exists()):
        vlog().warning("skip %s: missing mask/high/repair15", fn)
        print(f"  skip {fn}: missing mask/high/repair15")
        continue
    raw = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    ```
    (This replaces the `find_mask_path` block; `find_mask_path`/`decode_mask` import line for find_mask_path may be dropped if unused.)
  - Cache becomes a dict and item gains the two keys:
    ```python
    mask_cache[entry.timestamp] = {
        "mask": mask_path.read_bytes(),
        "high": high_path.read_bytes(),
        "repair15": rep_path.read_bytes()}
    item = build_annotation_item(
        timestamp=entry.timestamp,
        mask_s3_key=naming.mask_s3_key(session_id, entry.timestamp),
        highlight_s3_key=naming.high_s3_key(session_id, entry.timestamp),
        repair15_s3_key=naming.repair15_s3_key(session_id, entry.timestamp),
        px_per_cm=px_per_cm, scale_source=entry.scale_source,
        crack_mask=crack, spalling_mask=spall, boxes=boxes)
    ```
  - Change the `upload_session(...)` call: `mask_bytes_for=lambda ts: mask_cache[ts]` -> `bytes_for=lambda ts: mask_cache[ts]`.

- [ ] **6.5 Run tests + import-smoke the CLI**:
  `.venv/bin/python -m pytest labeling_tool/tests/test_upload_worker.py -q`
  Expected: 2 passed (uploaded==2, puts==6; missing-mask skip still 0).
  `.venv/bin/python -c "import labeling_tool.scripts.upload_session_cli; import labeling_tool.ui.upload_worker; print('ok')"`
  Expected: `ok`.

- [ ] **6.6 Commit**:
  `git add labeling_tool/ui/upload_worker.py labeling_tool/scripts/upload_session_cli.py labeling_tool/tests/test_upload_worker.py`
  `git commit -m "feat(upload): read+upload high/repair15 alongside mask in worker+cli"`

---

## Task 7 — core/canvas/image_canvas.py + core/canvas/overlay_painter.py (GUI: import-smoke + full-suite)

**Files**
- Modify: `labeling_tool/core/canvas/overlay_painter.py`
- Modify: `labeling_tool/core/canvas/image_canvas.py`

**Interfaces**
- Consumes: `cv2.findContours`, `viewport.image_to_widget`, the existing crop/resize/composite pattern in `paint_mask_overlay`.
- Produces on `ImageCanvas`:
  - State: `highlight_mask: np.ndarray | None`, `repair15_contours: list | None`, `show_highlight: bool = False`, `show_repair15: bool = False`.
  - `set_highlight(arr: np.ndarray | None)` — store + invalidate overlay cache (`_touch_mask()`), then `update()`.
  - `set_repair15(arr: np.ndarray | None)` — run `cv2.findContours(RETR_EXTERNAL)` on the 0/255 mask, store image-coord polygons (or None), then `update()`.
  - paintEvent additions: yellow highlight halo + cyan repair15 outline.
  - `set_image(...)` clears all four (highlight None, contours None, toggles untouched but masks cleared).
- New helper in `overlay_painter.py`: `paint_single_color_overlay(painter, viewport, w, h, mask, rgb, alpha=90)`.

> No unit test (project convention: GUI/canvas verified by import-smoke + full suite).

### Steps

- [ ] **7.1 Add `paint_single_color_overlay`** to `labeling_tool/core/canvas/overlay_painter.py` (mirrors `paint_mask_overlay`'s crop/resize/composite, single color, configurable alpha):

```python
def paint_single_color_overlay(
    painter: QPainter,
    viewport: Viewport,
    widget_w: int,
    widget_h: int,
    mask: np.ndarray | None,
    rgb: tuple[int, int, int],
    alpha: int = 90,
) -> None:
    """Render mask>0 as a single translucent color (e.g. the highlight halo)."""
    if mask is None or viewport.scale <= 0:
        return
    ih, iw = viewport.img_h, viewport.img_w
    scale = viewport.scale
    ox, oy = viewport.offset.x(), viewport.offset.y()

    x0 = max(0, int((0 - ox) / scale))
    y0 = max(0, int((0 - oy) / scale))
    x1 = min(iw, int(np.ceil((widget_w - ox) / scale)) + 1)
    y1 = min(ih, int(np.ceil((widget_h - oy) / scale)) + 1)
    if x1 <= x0 or y1 <= y0:
        return

    cw, ch = (x1 - x0), (y1 - y0)
    wsw = max(1, int(cw * scale))
    wsh = max(1, int(ch * scale))
    px = int(ox + x0 * scale)
    py = int(oy + y0 * scale)

    crop = mask[y0:y1, x0:x1]
    if crop.max() == 0:
        return
    shrinking = (wsw < cw) or (wsh < ch)
    interp = cv2.INTER_AREA if shrinking else cv2.INTER_NEAREST
    resized = cv2.resize(crop, (wsw, wsh), interpolation=interp)
    binimg = np.where(resized > 0, np.uint8(255), np.uint8(0))
    rgba = np.zeros((wsh, wsw, 4), dtype=np.uint8)
    rgba[..., 0] = rgb[2]
    rgba[..., 1] = rgb[1]
    rgba[..., 2] = rgb[0]
    rgba[..., 3] = np.where(binimg > 0, np.uint8(alpha), np.uint8(0))
    qimg = QImage(rgba.data, wsw, wsh, wsw * 4, QImage.Format_RGBA8888)
    painter.drawImage(QPointF(px, py), qimg)
```

- [ ] **7.2 Add canvas state** in `ImageCanvas.__init__` (near the other overlay state, ~line 58):
```python
        # ----- derived-mask overlays (display-only; default hidden) -----
        self.highlight_mask: np.ndarray | None = None
        self.repair15_contours: list | None = None
        self.show_highlight: bool = False
        self.show_repair15: bool = False
```

- [ ] **7.3 Add setters** (public API region, e.g. after `set_aruco_corners`):
```python
    def set_highlight(self, arr: np.ndarray | None) -> None:
        """Store the 0/1/2 highlight mask; invalidate the overlay cache."""
        self.highlight_mask = arr
        self._touch_mask()
        self.update()

    def set_repair15(self, arr: np.ndarray | None) -> None:
        """Compute external contours (image coords) of the 0/255 mask, once."""
        if arr is None:
            self.repair15_contours = None
        else:
            binu = (arr > 0).astype(np.uint8)
            cnts, _ = cv2.findContours(
                binu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            self.repair15_contours = cnts   # list of Nx1x2 int arrays (image px)
        self.update()
```

- [ ] **7.4 Clear in `set_image`** — add to the reset block (~line 96-102, before `self._touch_mask()`):
```python
        self.highlight_mask = None
        self.repair15_contours = None
```
  (Toggles `show_highlight`/`show_repair15` persist across images, matching the spec's "toggle (default off)" — the caller will set masks via `_show_image`.)

- [ ] **7.5 Add paintEvent drawing** — in `paintEvent`, after `self._draw_cached_overlay(painter)` (~line 201) and before the bbox overlay block, add:
```python
        if (self._pixmap is not None and self.show_highlight
                and self.highlight_mask is not None):
            from labeling_tool.core.canvas.overlay_painter import (
                paint_single_color_overlay,
            )
            paint_single_color_overlay(
                painter, self.viewport, self.width(), self.height(),
                self.highlight_mask, (255, 255, 0), alpha=90)

        if (self._pixmap is not None and self.show_repair15
                and self.repair15_contours is not None):
            self._paint_repair15(painter)
```
  And add the helper method:
```python
    def _paint_repair15(self, painter: QPainter):
        """Draw the 15cm boundary as cyan outline polylines (line only)."""
        pen = QPen(QColor(0, 200, 255, 230), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.NoBrush))
        for cnt in self.repair15_contours:
            pts = cnt.reshape(-1, 2)
            if len(pts) < 2:
                continue
            wpts = [QPointF(*self.viewport.image_to_widget(float(x), float(y)))
                    for x, y in pts]
            for i in range(len(wpts)):
                painter.drawLine(wpts[i], wpts[(i + 1) % len(wpts)])
```
  (`QPointF`, `QPen`, `QColor`, `QBrush`, `Qt` are already imported at the top of image_canvas.py.)

- [ ] **7.6 Import-smoke + full suite**:
  `.venv/bin/python -c "from labeling_tool.core.canvas.image_canvas import ImageCanvas; from labeling_tool.core.canvas.overlay_painter import paint_single_color_overlay; print('ok')"`
  Expected: `ok`.
  `.venv/bin/python -m pytest labeling_tool/tests -q`
  Expected: full suite green (no regressions).

- [ ] **7.7 Commit**:
  `git add labeling_tool/core/canvas/image_canvas.py labeling_tool/core/canvas/overlay_painter.py`
  `git commit -m "feat(canvas): highlight halo + repair15 outline overlays w/ setters"`

---

## Task 8 — main_window.py + ui_builder.py + ui/main_window.py + i18n.py (GUI: import-smoke + full-suite)

**Files**
- Modify: `labeling_tool/core/window/main_window.py`
- Modify: `labeling_tool/core/window/ui_builder.py`
- Modify: `labeling_tool/ui/main_window.py`
- Modify: `labeling_tool/core/i18n.py`

**Interfaces**
- `MainWindow` gains `highlight_dir`/`repair15_dir` state (declared in `__init__`, derived in `_sync_output_dir`).
- `_save_all_artifacts` writes HighLight/Repair15 files (after the mask write) and refreshes the canvas with the freshly-built arrays.
- `_show_image` reads HighLight/Repair15 files (if present) and pushes them to the canvas.
- `ui_builder` adds two checkable `QPushButton`s `_btn_show_highlight` / `_btn_show_repair15` wired to handlers `_on_toggle_highlight` / `_on_toggle_repair15`.
- `i18n` gains `btn_show_highlight` / `btn_show_repair15` in en/zh/ko.
- `ViewerMainWindow` sets `highlight_dir`/`repair15_dir` from the workspace.

> No unit test (GUI convention).

### Steps

- [ ] **8.1 Declare state + derive dirs** in `labeling_tool/core/window/main_window.py`:
  - In `__init__` (~line 49) after `self.result_dir = None`:
    ```python
    self.highlight_dir: Path | None = None
    self.repair15_dir: Path | None = None
    ```
  - In `_sync_output_dir` (~line 155-162):
    ```python
    def _sync_output_dir(self):
        """Derive output_dir, result_dir, highlight_dir, repair15_dir from origin_dir.parent."""
        if self.origin_dir is not None:
            parent = self.origin_dir.parent
            self.output_dir   = parent / OUTPUT_DIR_NAME
            self.result_dir   = parent / "Result"
            self.highlight_dir = parent / "HighLight"
            self.repair15_dir  = parent / "Repair15"
        else:
            self.output_dir = self.result_dir = None
            self.highlight_dir = self.repair15_dir = None
    ```

- [ ] **8.2 Generate + refresh on save** — in `_save_all_artifacts`, after the mask-write block (~line 325, after `_cv2.imwrite(str(mask_out), label)`), add (keep inside the `if mc is not None or ms is not None:` guard so we only derive when there is a mask):
```python
            # ----- 1b. Derived masks: highlight + (scale-dependent) repair15 -----
            from labeling_tool.core.derived_masks import (
                build_highlight, build_repair15,
            )
            try:
                label_hi = build_highlight(mc, ms)
                if self.highlight_dir is not None:
                    self.highlight_dir.mkdir(parents=True, exist_ok=True)
                    _cv2.imwrite(
                        str(self.highlight_dir / mask_store.mask_name(filename)),
                        label_hi)
                self.canvas.set_highlight(label_hi)
            except ValueError:
                self.canvas.set_highlight(None)

            if self.current_scale:
                r15 = build_repair15(mc, ms, self.current_scale)
                if self.repair15_dir is not None:
                    self.repair15_dir.mkdir(parents=True, exist_ok=True)
                    _cv2.imwrite(
                        str(self.repair15_dir / mask_store.mask_name(filename)),
                        r15)
                self.canvas.set_repair15(r15)
            else:
                self.canvas.set_repair15(None)
```

- [ ] **8.3 Load on image switch** — in `_show_image`, after `self.canvas.set_image(origin, crack_mask, spalling_mask)` (~line 540), add:
```python
        # ----- derived-mask overlays (read saved files; else clear) -----
        import cv2 as _cv2_load
        hi_name = mask_store.mask_name(filename)
        if self.highlight_dir is not None and (self.highlight_dir / hi_name).exists():
            arr = _cv2_load.imread(str(self.highlight_dir / hi_name),
                                   _cv2_load.IMREAD_UNCHANGED)
            self.canvas.set_highlight(arr)
        else:
            self.canvas.set_highlight(None)
        if self.repair15_dir is not None and (self.repair15_dir / hi_name).exists():
            arr = _cv2_load.imread(str(self.repair15_dir / hi_name),
                                   _cv2_load.IMREAD_UNCHANGED)
            self.canvas.set_repair15(arr)
        else:
            self.canvas.set_repair15(None)
```

- [ ] **8.4 Add toggle handlers** in `labeling_tool/core/window/main_window.py` (near the brush callbacks):
```python
    def _on_toggle_highlight(self, checked: bool):
        self.canvas.show_highlight = bool(checked)
        self.canvas.update()

    def _on_toggle_repair15(self, checked: bool):
        self.canvas.show_repair15 = bool(checked)
        self.canvas.update()
```

- [ ] **8.5 Add the two buttons** in `labeling_tool/core/window/ui_builder.py` — extend `build_bbox_group` (or a new small group). Simplest: append to the bbox group's layout after the bbox toggle (~line 171), before `return`:
```python
    window._btn_show_highlight = QPushButton(window.tr_("btn_show_highlight"))
    window._btn_show_highlight.setCheckable(True)
    window._btn_show_highlight.setMinimumHeight(32)
    window._btn_show_highlight.toggled.connect(window._on_toggle_highlight)
    gb.addWidget(window._btn_show_highlight)

    window._btn_show_repair15 = QPushButton(window.tr_("btn_show_repair15"))
    window._btn_show_repair15.setCheckable(True)
    window._btn_show_repair15.setMinimumHeight(32)
    window._btn_show_repair15.toggled.connect(window._on_toggle_repair15)
    gb.addWidget(window._btn_show_repair15)
```

- [ ] **8.6 Retranslate** — in `MainWindow._retranslate_ui`, after the bbox toggle text (~line 137) add:
```python
        self._btn_show_highlight.setText(self.tr_("btn_show_highlight"))
        self._btn_show_repair15.setText(self.tr_("btn_show_repair15"))
```

- [ ] **8.7 i18n keys** — add to each of en/zh/ko in `labeling_tool/core/i18n.py` (next to the bbox keys):
```python
        # en
        "btn_show_highlight":    "Show Highlight",
        "btn_show_repair15":     "Show 15cm Boundary",
        # zh
        "btn_show_highlight":    "显示高亮",
        "btn_show_repair15":     "显示15cm边界",
        # ko
        "btn_show_highlight":    "하이라이트 표시",
        "btn_show_repair15":     "15cm 경계 표시",
```

- [ ] **8.8 ViewerMainWindow dirs** — in `labeling_tool/ui/main_window.py.__init__`, after `self.result_dir = workspace.result_dir.resolve()` (~line 43) add:
```python
        self.highlight_dir = workspace.highlight_dir.resolve()
        self.repair15_dir = workspace.repair15_dir.resolve()
```

- [ ] **8.9 Import-smoke + full suite**:
  `.venv/bin/python -c "import labeling_tool.core.window.main_window, labeling_tool.core.window.ui_builder, labeling_tool.ui.main_window, labeling_tool.core.i18n; print('ok')"`
  Expected: `ok`.
  `.venv/bin/python -m pytest labeling_tool/tests -q`
  Expected: full suite green.

- [ ] **8.10 Commit**:
  `git add labeling_tool/core/window/main_window.py labeling_tool/core/window/ui_builder.py labeling_tool/ui/main_window.py labeling_tool/core/i18n.py`
  `git commit -m "feat(ui): generate+display highlight/repair15 overlays w/ toggles+i18n"`

---

## Task 9 — GUI smoke (manual, optional)

- [ ] **9.1** Launch the app against an offline session:
  `DISPLAY=:1 .venv/bin/python -m labeling_tool.app`
- [ ] **9.2** Offline-open `session_18`, draw a crack, set a scale (ArUco auto or manual measure), and Save.
- [ ] **9.3** Toggle "Show Highlight" -> a translucent yellow halo appears around the crack; toggle "Show 15cm Boundary" -> a cyan outline appears at the 15cm pad.
- [ ] **9.4** Confirm `data/session_18/HighLight/<stem>_mask.png` and `data/session_18/Repair15/<stem>_mask.png` were written.
  `ls -1 labeling_tool/data/session_18/HighLight labeling_tool/data/session_18/Repair15`

---

## Self-Review

**Spec coverage**
- [x] Decision: centralized `core/derived_masks.py` pure functions -> Task 1.
- [x] highlight = all classes dilate 10px, re-encode 0/1/2, crack precedence -> Task 1 (`build_highlight`, spalling written then crack).
- [x] repair15 = foreground union dilate round(15*px/cm), FILLED 0/255 -> Task 1 (`build_repair15`).
- [x] workspace HighLight/Repair15 dirs + ensure -> Task 3; naming high_/15_ filenames + s3 keys -> Task 2.
- [x] V2 3-file / V3 mask->high->15 / V4 two new required keys -> Tasks 4 (payload) + 5 (uploader).
- [x] missing mask/high/15 -> skip photo (vlog warning) -> Task 6 (worker + CLI).
- [x] canvas highlight yellow halo translucent; repair15 outer-contour line only (file stays filled) -> Task 7.
- [x] display reads saved files on load; refreshed in-place on save -> Task 8 (`_show_image` reads, `_save_all_artifacts` set_*).
- [x] two toggles default off + i18n (en/zh/ko) -> Task 8.
- [x] no new runtime deps (cv2/numpy/PyQt5 already used); Python 3.10+ (uses `X | None` syntax already pervasive).

**Placeholder scan** — no `TODO`/`pass`/`...`/`NotImplemented` placeholders in the provided code blocks; every function body is complete.

**Type consistency across tasks**
- `bytes_for` dict shape `{"mask":bytes,"high":bytes,"repair15":bytes}` is produced identically in the worker cache (6.3), the CLI cache (6.4), and the uploader's per-photo presign/PUT (5.3); the test `_bytes` helper (5.1) matches. The PUT loop indexes `blobs["mask"/"high"/"repair15"]`.
- `build_annotation_item` new kwargs `highlight_s3_key` / `repair15_s3_key` (Task 4) are passed by both callers (Task 6) and asserted in test_annotation_payload (4.1); the output keys `highlightS3Key`/`repair15S3Key` are asserted in test_uploader `_item` (5.1) which mirrors what the worker builds.
- naming function names are exactly `high_filename`, `repair15_filename`, `high_s3_key`, `repair15_s3_key` (Task 2) and are referenced verbatim in uploader (5.3) and worker/CLI (6.3/6.4).
- canvas setter names are exactly `set_highlight` / `set_repair15` (Task 7) and are called verbatim from `_save_all_artifacts` and `_show_image` (Task 8).
- progress semantics unchanged: `progress(base + i, total)` once per photo + the `finally` `progress(base, total)`; monotonic/total tests (5.1) still hold because per-photo `i` is monotonic and `base` advances by full batch.

**Open risks / watch-items**
- The worker now expects `labeling_dir` to be a real `Labeling/` folder whose parent holds `HighLight/`/`Repair15/`. `ViewerMainWindow` passes `str(self.output_dir)` which is `workspace.labeling_dir` (sibling of HighLight/Repair15) — consistent. The worker test (6.1) therefore points `labeling_dir` at `tmp_path/"Labeling"`.
- `_save_all_artifacts` build_* is guarded by `if mc is not None or ms is not None` and a `try/except ValueError`, so a manual-scale-only save (no painted mask) will not crash; repair15 is skipped when `current_scale` is falsy, matching "px<=0 photo isn't uploaded anyway".
