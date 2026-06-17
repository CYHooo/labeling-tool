# labeling_tool 数据加载合理化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个可测的 `mask_store` 解析层取代脆弱的 `find_mask_path` 模糊匹配 + 三处重复的 rebuild 代码,加入 mtime 缓存失效,并让 `_show_image` 瘦身——行为(保留 Rebuilt 精化、R=crack/G=spalling、三级优先级)不变。

**Architecture:** 新增纯函数模块 `labeling_tool/session/mask_store.py`,集中:确定性命名(`{stem}_mask.png` / `{stem}.bbox.json`)、显示掩膜解析(`Labeling > 新鲜Rebuilt > needs_rebuild`,按 mtime 失效)、唯一的 rebuild 输出构造(R 精化 + G 保留)。`_show_image`、`rebuild_cache`、`_on_rebuild_force`、保存与上传路径全部改走它。

**Tech Stack:** Python 3.10+,numpy,opencv-python,scikit-image,PyQt5。测试:pytest(+offscreen GUI 冒烟)。

参考 spec:`docs/superpowers/specs/2026-06-16-labeling-data-loading-rationalization-design.md`

**环境约定(所有任务)**
- 仓库根:`/home/claire/Lastmile/XI_ParkingLots`,分支 `accelerate`,提交于此(不新建分支、不 push,除最后一步同步到独立仓库)。
- 解释器:`/home/claire/Lastmile/XI_ParkingLots/algorithms/05_detect/.venv/bin/python`,从仓库根运行(使 `import labeling_tool` 可解析)。命令里的 `python` 一律用此绝对路径。依赖已装,勿 pip。

---

## File Structure

- 新增 `labeling_tool/session/mask_store.py` —— 命名 + 解析 + rebuild 输出(纯函数,无 Qt)。
- 新增 `labeling_tool/tests/test_mask_store.py`。
- 改 `labeling_tool/rebuild_cache.py` —— 用 `build_rebuilt_rgb` + mtime 跳过。
- 改 `labeling_tool/core/window/main_window.py` —— `_show_image` / `_save_all_artifacts` / `_on_rebuild_force` 走 mask_store,移除 `_mask_filename`。
- 改 `labeling_tool/ui/main_window.py`、`labeling_tool/ui/upload_worker.py` —— 用 `mask_store.mask_name` 定位,停用 `find_mask_path`。
- 改 `labeling_tool/tests/test_rebuild_cache.py` —— 适配新跳过规则 + mtime 测试。

---

## Task 1: `mask_store` 模块(命名 + 解析 + rebuild 输出,TDD)

**Files:**
- Create: `labeling_tool/session/mask_store.py`
- Test: `labeling_tool/tests/test_mask_store.py`

- [ ] **Step 1: 写失败测试**

Create `labeling_tool/tests/test_mask_store.py`:
```python
import time
import numpy as np
import cv2

from labeling_tool.session import mask_store


def test_naming():
    assert mask_store.mask_name("stitched_123.jpg") == "stitched_123_mask.png"
    assert mask_store.bbox_name("stitched_123.jpg") == "stitched_123.bbox.json"


def _touch(p, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))


def test_resolve_labeling_wins(tmp_path):
    lab, reb, det = tmp_path / "L", tmp_path / "R", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(lab / name); _touch(reb / name); _touch(det / name)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=lab, rebuilt_dir=reb, detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "labeling" and path == lab / name


def test_resolve_fresh_rebuilt(tmp_path):
    reb, det = tmp_path / "R", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(det / name, mtime=1000)
    _touch(reb / name, mtime=2000)            # Rebuilt newer -> fresh
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", rebuilt_dir=reb, detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "rebuilt" and path == reb / name


def test_resolve_stale_rebuilt_needs_rebuild(tmp_path):
    reb, det = tmp_path / "R", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(reb / name, mtime=1000)
    _touch(det / name, mtime=2000)            # Detected newer -> Rebuilt stale
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", rebuilt_dir=reb, detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "needs_rebuild" and path is None


def test_resolve_nothing(tmp_path):
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", rebuilt_dir=tmp_path / "R",
        detected_dir=tmp_path / "D", origin_filename="stitched_1.jpg")
    assert src == "needs_rebuild" and path is None


def test_build_rebuilt_rgb_refines_crack_and_keeps_g():
    origin = np.full((80, 200, 3), 30, np.uint8)
    origin[38:43, 10:190] = 20                 # darker crack band
    coarse = np.zeros((80, 200, 3), np.uint8)
    coarse[38:43, 10:190, 2] = 255             # R = crack
    coarse[10:25, 10:60, 1] = 255              # G = non-crack class
    rgb = mask_store.build_rebuilt_rgb(origin, coarse)
    assert rgb.ndim == 3 and rgb.shape[2] == 3
    assert int((rgb[..., 2] > 0).sum()) > 0    # crack present (R)
    assert int((rgb[..., 1] > 0).sum()) > 0    # non-crack class preserved (G)


def test_build_rebuilt_rgb_resizes_g_to_guided(tmp_path):
    origin = np.full((60, 120, 3), 30, np.uint8)
    coarse = np.zeros((30, 60, 3), np.uint8)   # half-size coarse mask
    coarse[10:20, 5:55, 1] = 255               # G only
    rgb = mask_store.build_rebuilt_rgb(origin, coarse)
    assert rgb.shape[:2] == origin.shape[:2]   # output matches origin/guided size
    assert int((rgb[..., 1] > 0).sum()) > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests/test_mask_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.session.mask_store'`

- [ ] **Step 3: 实现**

Create `labeling_tool/session/mask_store.py`:
```python
"""Deterministic per-session mask layout + display resolution + rebuild output.

Single source of truth for the V-API tool's data loading:
  * where each layer's mask/bbox lives (keyed off the origin filename — no fuzzy
    matching): Detected/Rebuilt/Labeling all use ``{origin_stem}_mask.png``;
  * which layer to display: Labeling > fresh Rebuilt > needs_rebuild, where
    "fresh" means the Rebuilt cache is not older than its Detected source;
  * how a Rebuilt mask is built: crack (R) intensity-refined, non-crack (G) kept.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from labeling_tool.core.rebuild import process_one


def mask_name(origin_filename: str) -> str:
    """Mask filename for an origin image (Detected/Rebuilt/Labeling share it)."""
    return f"{Path(origin_filename).stem}_mask.png"


def bbox_name(origin_filename: str) -> str:
    return f"{Path(origin_filename).stem}.bbox.json"


def _rebuilt_is_fresh(rebuilt: Path, detected: Path) -> bool:
    """Rebuilt is fresh if its Detected source is gone or not newer than it."""
    if not detected.exists():
        return True
    return rebuilt.stat().st_mtime >= detected.stat().st_mtime


def resolve_display_mask(*, labeling_dir, rebuilt_dir, detected_dir,
                         origin_filename) -> tuple[Path | None, str]:
    """Pick the mask to display for an origin image.

    Returns (path, source):
      Labeling/<name> exists                  -> (path, "labeling")
      Rebuilt/<name> exists and is fresh       -> (path, "rebuilt")
      otherwise                                -> (None, "needs_rebuild")
    A None dir means that layer is unavailable.
    """
    name = mask_name(origin_filename)
    if labeling_dir is not None:
        lab = Path(labeling_dir) / name
        if lab.exists():
            return lab, "labeling"
    if rebuilt_dir is not None:
        reb = Path(rebuilt_dir) / name
        if reb.exists():
            det = Path(detected_dir) / name if detected_dir is not None else None
            if det is None or _rebuilt_is_fresh(reb, det):
                return reb, "rebuilt"
    return None, "needs_rebuild"


def build_rebuilt_rgb(origin_bgr: np.ndarray,
                      coarse_raw: np.ndarray) -> np.ndarray:
    """Build a Rebuilt mask: R = intensity-refined crack, G = preserved non-crack.

    `coarse_raw` is the Detected/Labeling mask as read (3-ch BGR or single-ch).
    Only the crack channel is refined via process_one; the non-crack (G) channel
    is carried through unchanged (resized to the guided size if needed).
    """
    coarse_gray = coarse_raw[..., 2] if coarse_raw.ndim == 3 else coarse_raw
    guided, _, _ = process_one(origin_bgr, coarse_gray, compute_length=False)
    rgb = np.zeros((*guided.shape, 3), dtype=np.uint8)
    rgb[..., 2] = guided
    if coarse_raw.ndim == 3:
        g = coarse_raw[..., 1]
        if g.shape != guided.shape:
            g = cv2.resize(g, (guided.shape[1], guided.shape[0]),
                           interpolation=cv2.INTER_NEAREST)
        rgb[..., 1] = np.where(g > 0, 255, 0).astype(np.uint8)
    return rgb
```

- [ ] **Step 4: 运行确认通过**

Run: `algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests/test_mask_store.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/session/mask_store.py labeling_tool/tests/test_mask_store.py
git commit -m "feat(labeling_tool): mask_store — deterministic layout + display resolution + rebuild output"
```

---

## Task 2: `rebuild_cache` 改用 `build_rebuilt_rgb` + mtime 跳过(TDD)

**Files:**
- Modify: `labeling_tool/rebuild_cache.py`
- Modify: `labeling_tool/tests/test_rebuild_cache.py`

- [ ] **Step 1: 追加 mtime 失效测试**

Append to `labeling_tool/tests/test_rebuild_cache.py`:
```python
def test_prebuild_regenerates_when_detected_newer(tmp_path):
    import os, time
    o, d, r = _dirs(tmp_path)
    _make_pair(o, d, 1)
    prebuild_rebuilt(o, d, r, [1], workers=1)
    out = r / naming.detected_mask_filename(1)
    assert out.exists()
    first = out.stat().st_mtime_ns
    # Make Detected newer than the cached Rebuilt -> must regenerate.
    time.sleep(0.01)
    os.utime(d / naming.detected_mask_filename(1), None)   # bump Detected mtime
    # ensure Rebuilt looks older than Detected
    older = d.joinpath(naming.detected_mask_filename(1)).stat().st_mtime - 100
    os.utime(out, (older, older))
    prebuild_rebuilt(o, d, r, [1], workers=1)
    assert out.stat().st_mtime_ns != first       # regenerated


def test_prebuild_skips_when_fresh(tmp_path):
    import os
    o, d, r = _dirs(tmp_path)
    _make_pair(o, d, 1)
    prebuild_rebuilt(o, d, r, [1], workers=1)
    out = r / naming.detected_mask_filename(1)
    # Rebuilt newer than Detected -> fresh -> skipped (mtime unchanged).
    newer = d.joinpath(naming.detected_mask_filename(1)).stat().st_mtime + 100
    os.utime(out, (newer, newer))
    before = out.stat().st_mtime_ns
    prebuild_rebuilt(o, d, r, [1], workers=1)
    assert out.stat().st_mtime_ns == before      # not regenerated
```

- [ ] **Step 2: 运行确认失败**

Run: `algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests/test_rebuild_cache.py -v`
Expected: `test_prebuild_regenerates_when_detected_newer` FAILs (current code skips when out exists regardless of mtime).

- [ ] **Step 3: 实现 —— `_prebuild_one` 用 `build_rebuilt_rgb`,跳过规则改 mtime**

In `labeling_tool/rebuild_cache.py`:

Add import near the top (with the other `labeling_tool` imports):
```python
from labeling_tool.session import mask_store
```

Replace the body of `_prebuild_one` (the read + build + write) with:
```python
def _prebuild_one(origin_path: str, detected_path: str, out_path: str) -> str | None:
    """Build one Rebuilt mask. Returns an error string, or None on success.

    Top-level + path-only args so it is picklable for the process pool.
    """
    try:
        origin_bgr = cv2.imread(origin_path)
        raw = cv2.imread(detected_path, cv2.IMREAD_UNCHANGED)
        if origin_bgr is None or raw is None:
            return "missing origin or detected mask"
        rgb = mask_store.build_rebuilt_rgb(origin_bgr, raw)
        cv2.imwrite(out_path, rgb)
        return None
    except Exception as e:  # noqa: BLE001 - reported back to the caller
        return str(e)
```

In `prebuild_rebuilt`, change the "skip if cached" check from existence to freshness. Replace:
```python
        out_path = rebuilt_dir / naming.detected_mask_filename(ts)
        if out_path.exists():
            continue
```
with:
```python
        out_path = rebuilt_dir / naming.detected_mask_filename(ts)
        det_path = detected_dir / naming.detected_mask_filename(ts)
        if out_path.exists() and (not det_path.exists()
                                  or out_path.stat().st_mtime >= det_path.stat().st_mtime):
            continue   # fresh cache, skip
```

(`numpy`/`process_one` imports in rebuild_cache that are now only used via mask_store can stay; leaving them is harmless. Do NOT remove `cv2`.)

- [ ] **Step 4: 运行确认通过**

Run: `algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests/test_rebuild_cache.py -v`
Expected: all passed (existing + 2 new).

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/rebuild_cache.py labeling_tool/tests/test_rebuild_cache.py
git commit -m "perf(labeling_tool): prebuild via mask_store.build_rebuilt_rgb + mtime-based cache invalidation"
```

---

## Task 3: 主窗口走 `mask_store`,移除 `_mask_filename` 与模糊匹配

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`

GUI 改动,无单测;以 offscreen 构造 + 行为脚本验证。

- [ ] **Step 1: 加导入**

In `labeling_tool/core/window/main_window.py`, after the existing `from labeling_tool.core.bbox import (...)` import block, add:
```python
from labeling_tool.session import mask_store
```

- [ ] **Step 2: 移除 `_mask_filename` 字典(init + clear)**

In `__init__`, delete the line:
```python
        self._mask_filename: dict[str, str | None] = {}
```
In `_reload_data`, delete the line:
```python
        self._mask_filename.clear()
```

- [ ] **Step 3: `_show_image` 加载块改写**

Replace everything from `mask_path = None` / `mask_source = "none"` down through the end of the rebuild block (the original Step 0 / Step 1 / Step 2 logic, i.e. the block that ends just before `print(f"[load] {filename} -> {mask_source}: {mask_path}", ...)`) with:
```python
        mask_path = None
        source = "none"

        resolved, source = mask_store.resolve_display_mask(
            labeling_dir=self.output_dir, rebuilt_dir=self.rebuilt_dir,
            detected_dir=self.detected_dir, origin_filename=filename)
        mask_path = str(resolved) if resolved is not None else None

        if source == "needs_rebuild":
            import cv2 as _cv2
            name = mask_store.mask_name(filename)
            det_path = (self.detected_dir / name
                        if self.detected_dir is not None else None)
            coarse_raw = (_cv2.imread(str(det_path), _cv2.IMREAD_UNCHANGED)
                          if det_path is not None and det_path.exists() else None)
            if coarse_raw is None:
                print(f"[load] {filename}: no mask in any folder", file=_sys.stderr)
                self.status.showMessage(f"No mask found for {filename}")
            else:
                self.status.showMessage(self.tr_("status_rebuilding"))
                QApplication.processEvents()
                try:
                    origin_bgr_rb = _cv2.imread(origin_path)
                    if origin_bgr_rb is None:
                        raise RuntimeError(f"cannot read origin {origin_path}")
                    rgb = mask_store.build_rebuilt_rgb(origin_bgr_rb, coarse_raw)
                    if self.rebuilt_dir is not None:
                        self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                        rebuilt_path = self.rebuilt_dir / name
                        _cv2.imwrite(str(rebuilt_path), rgb)
                        mask_path = str(rebuilt_path)
                        source = "rebuilt(from detected)"
                        self.status.showMessage(self.tr_("rebuild_done", name=name))
                except Exception as e:
                    import traceback as _tb
                    print(f"[rebuild] {filename}: FAILED {e}", file=_sys.stderr)
                    _tb.print_exc()
                    self.status.showMessage(self.tr_("rebuild_failed", err=str(e)))
                    mask_path = str(det_path)            # fallback: load Detected as-is
                    source = "detected(rebuild_failed)"

        print(f"[load] {filename} -> {source}: {mask_path}", file=_sys.stderr)
```
(`mask_source` is renamed to `source` here; the original kept a separate `mask_source` — make sure the `print` line uses `source`. The `import sys as _sys` line that precedes this block stays.)

- [ ] **Step 4: 删除 `_show_image` 里设置 `_mask_filename` 的行**

Delete:
```python
        self._mask_filename[filename] = (
            Path(mask_path).name if mask_path else None
        )
```

- [ ] **Step 5: `_show_image` 的 bbox 加载改用 `bbox_name`**

Replace:
```python
            bbox_path = self.output_dir / f"{Path(filename).stem}.bbox.json"
            self.canvas.bbox_interaction.boxes = load_bboxes(bbox_path)
```
with:
```python
            bbox_path = self.output_dir / mask_store.bbox_name(filename)
            self.canvas.bbox_interaction.boxes = load_bboxes(bbox_path)
```

- [ ] **Step 6: `_save_all_artifacts` 用确定性命名**

Replace:
```python
            out_name = self._mask_filename.get(filename)
            if not out_name:
                out_name = f"{Path(filename).stem}.png"
            mask_out = self.output_dir / out_name
```
with:
```python
            mask_out = self.output_dir / mask_store.mask_name(filename)
```
And replace the bbox path line:
```python
        bbox_path = self.output_dir / f"{Path(filename).stem}.bbox.json"
```
with:
```python
        bbox_path = self.output_dir / mask_store.bbox_name(filename)
```

- [ ] **Step 7: `_on_rebuild_force` 改用确定性命名 + `build_rebuilt_rgb`**

Replace the coarse-source + inline-rebuild section (from `# Pick coarse source: prefer Labeling/ over Detected/` down to the `except Exception as e:` ... `return` that ends the rebuild try) with:
```python
        # Coarse source: prefer current edits in Labeling/, else Detected/.
        name = mask_store.mask_name(filename)
        coarse_path = None
        if self.output_dir is not None and (self.output_dir / name).exists():
            coarse_path = self.output_dir / name
        elif self.detected_dir is not None and (self.detected_dir / name).exists():
            coarse_path = self.detected_dir / name
        if coarse_path is None:
            self.status.showMessage(self.tr_("rebuild_failed", err="no coarse mask"))
            return

        origin_path = str(self.origin_dir / filename)
        self.status.showMessage(self.tr_("status_rebuilding"))
        QApplication.processEvents()
        try:
            import cv2 as _cv2
            coarse_raw = _cv2.imread(str(coarse_path), _cv2.IMREAD_UNCHANGED)
            if coarse_raw is None:
                raise RuntimeError(f"failed to read coarse mask: {coarse_path}")
            origin_bgr = _cv2.imread(origin_path)
            if origin_bgr is None:
                raise RuntimeError(f"failed to read origin: {origin_path}")
            rgb = mask_store.build_rebuilt_rgb(origin_bgr, coarse_raw)
            if self.rebuilt_dir is not None:
                self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.rebuilt_dir / name), rgb)
            if self.output_dir is not None:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.output_dir / name), rgb)
        except Exception as e:
            self.status.showMessage(self.tr_("rebuild_failed", err=str(e)))
            return
```
Then the lines after the try (the `self._edited.pop(...)`, `self._bbox_edited.pop(...)`, status, and `self._show_image(self.current_idx, force_reload=True)`) — if any referenced the old local `mask_name` variable for a `rebuild_done` message, update it to use `name`. (The `rebuild_done` status uses `name=` — set it to `name`.)

- [ ] **Step 8: 确认没有残留 `_mask_filename` 或 `find_mask_path` 调用**

Run: `grep -n "_mask_filename\|find_mask_path" labeling_tool/core/window/main_window.py`
Expected: no output. If any remain, fix them (they should all be replaced by `mask_store.mask_name(...)`). Also remove the now-unused `find_mask_path` import if it is no longer referenced in this file (`from labeling_tool.core.mask_io import ...` — keep `load_origin_and_masks`, drop `find_mask_path` if unused). Verify the import line still imports what's used.

- [ ] **Step 9: offscreen 构造 + 全量测试**

Run:
```bash
algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests -q
QT_QPA_PLATFORM=offscreen algorithms/05_detect/.venv/bin/python -c "import os; os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']=''; from PyQt5.QtWidgets import QApplication; app=QApplication([]); from labeling_tool.core.window.main_window import MainWindow; w=MainWindow(); print('build ok')"
```
Expected: tests pass; prints `build ok`.

- [ ] **Step 10: 提交**

```bash
git add labeling_tool/core/window/main_window.py
git commit -m "refactor(labeling_tool): main window loads/saves/rebuilds via mask_store; drop _mask_filename + fuzzy match"
```

---

## Task 4: UI 层(`ui/main_window`、`upload_worker`)走确定性命名

**Files:**
- Modify: `labeling_tool/ui/main_window.py`
- Modify: `labeling_tool/ui/upload_worker.py`

- [ ] **Step 1: `ui/main_window._edited_filenames` 改用 `mask_name`**

In `labeling_tool/ui/main_window.py`, add import (with the other `labeling_tool` imports):
```python
from labeling_tool.session import mask_store
```
Replace `_edited_filenames`:
```python
    def _edited_filenames(self) -> list[str]:
        """Photos with a saved edited mask in Labeling/ this session."""
        out = []
        for fn in self._manifest.filenames_in_order():
            if (self.output_dir / mask_store.mask_name(fn)).exists():
                out.append(fn)
        return out
```
If `find_mask_path` is now unused in this file, remove its import (`from labeling_tool.core.mask_io import find_mask_path`).

- [ ] **Step 2: `upload_worker._build_items` 改用 `mask_name`**

In `labeling_tool/ui/upload_worker.py`, replace the import:
```python
from labeling_tool.core.mask_io import find_mask_path
```
with:
```python
from labeling_tool.session import mask_store
```
In `_build_items`, replace:
```python
            mask_path = find_mask_path(fn, str(ldir))
            if mask_path is None:
                vlog().warning("prepare skip ts=%s: no mask in Labeling/", ts)
                continue
            bgr = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
```
with:
```python
            mask_path = ldir / mask_store.mask_name(fn)
            if not mask_path.exists():
                vlog().warning("prepare skip ts=%s: no mask in Labeling/", ts)
                continue
            bgr = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
```
And the `boxes = load_bboxes(ldir / f"{stem}.bbox.json")` line — replace with:
```python
            boxes = load_bboxes(ldir / mask_store.bbox_name(fn))
            measured = load_scale(ldir / mask_store.bbox_name(fn))
```
(replacing both the `load_bboxes(... f"{stem}.bbox.json")` and the adjacent `load_scale(... f"{stem}.bbox.json")` lines; `stem` may then be unused — leave or remove the `stem = Path(fn).stem` line if nothing else uses it).

- [ ] **Step 2b: `mask_bytes_for` reads via the same path**

Confirm `mask_cache[ts] = Path(mask_path).read_bytes()` still works (`mask_path` is now a `Path` — fine). If the code used `Path(mask_path)`, simplify to `mask_path.read_bytes()`.

- [ ] **Step 3: 全量 + worker 测试**

Run: `algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: all pass (test_upload_worker builds Labeling masks as `stitched_{ts}_mask.png` = `mask_store.mask_name(stitched_{ts}.jpg)`, so deterministic lookup matches).

- [ ] **Step 4: 提交**

```bash
git add labeling_tool/ui/main_window.py labeling_tool/ui/upload_worker.py
git commit -m "refactor(labeling_tool): UI/upload locate masks via mask_store.mask_name (drop find_mask_path)"
```

---

## Task 5: 端到端验证 + 同步到独立仓库并推送

**Files:** none changed (verification + propagation)

- [ ] **Step 1: 全量回归**

Run: `algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: all passed (~67).

- [ ] **Step 2: offscreen 端到端(过期 Rebuilt → 重建带回 G;Labeling 优先;保存命名;上传)**

Run this script with `QT_QPA_PLATFORM=offscreen`:
```python
import os, tempfile, time
from pathlib import Path
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""
import cv2, numpy as np
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session import naming, mask_store
ws = Workspace(root=Path(tempfile.mkdtemp()), session_id=1); ws.ensure()
ts = 1700000000000
cv2.imwrite(str(ws.origin_dir / naming.stitched_filename(ts)), np.full((80,200,3),60,np.uint8))
det = np.zeros((80,200,3),np.uint8); det[38:43,10:190,2]=255; det[10:25,10:60,1]=255  # R+G
cv2.imwrite(str(ws.detected_dir / naming.detected_mask_filename(ts)), det)
# stale Rebuilt (older than Detected, and missing G) -> must regenerate & bring back G
reb = np.zeros((80,200,3),np.uint8); reb[38:43,10:190,2]=255
p = ws.rebuilt_dir / naming.detected_mask_filename(ts); cv2.imwrite(str(p), reb)
old = (ws.detected_dir / naming.detected_mask_filename(ts)).stat().st_mtime - 100
os.utime(p, (old, old))
mf = Manifest(session_id=1, base="x"); mf.add(PhotoEntry(filename=naming.stitched_filename(ts), timestamp=ts, photo_id=1, report_photo_num=1, px_per_cm=10.0, scale_source="aruco"))
from labeling_tool.ui.main_window import ViewerMainWindow
w = ViewerMainWindow(ws, mf, None)
cm = w.canvas.brush_mask_crack; sm = w.canvas.brush_mask_spalling
assert cm is not None and (cm>0).sum()>0, "crack missing"
assert sm is not None and (sm>0).sum()>0, "spalling(G) not restored after stale-rebuild"
# Labeling-first: save, then a fresh load must read Labeling deterministically
w._edited[w.image_files[0]] = True
w._save_all_artifacts(silent=True)
assert (ws.labeling_dir / mask_store.mask_name(naming.stitched_filename(ts))).exists(), "Labeling mask name wrong"
print("E2E OK: stale rebuild restored G; labeling saved with deterministic name")
```
Expected: prints `E2E OK ...` with no assertion error.

- [ ] **Step 3: 同步改动到独立仓库**

```bash
SRC=/home/claire/Lastmile/XI_ParkingLots/labeling_tool
DST=/home/claire/Lastmile/labeling-tool/labeling_tool
mkdir -p "$DST/session"
for f in session/mask_store.py rebuild_cache.py core/window/main_window.py ui/main_window.py ui/upload_worker.py tests/test_mask_store.py tests/test_rebuild_cache.py; do cp "$SRC/$f" "$DST/$f"; done
cd /home/claire/Lastmile/labeling-tool
QT_QPA_PLATFORM=offscreen /home/claire/Lastmile/XI_ParkingLots/algorithms/05_detect/.venv/bin/python -m pytest labeling_tool/tests -q
```
Expected: all pass in the standalone repo.

- [ ] **Step 4: 提交并推送独立仓库**

```bash
cd /home/claire/Lastmile/labeling-tool
git add labeling_tool/session/mask_store.py labeling_tool/rebuild_cache.py labeling_tool/core/window/main_window.py labeling_tool/ui/main_window.py labeling_tool/ui/upload_worker.py labeling_tool/tests/test_mask_store.py labeling_tool/tests/test_rebuild_cache.py
git -c user.name="claire" -c user.email="cyh960502@gmail.com" commit -m "refactor: rationalize data loading via mask_store (deterministic naming + mtime cache)"
git push origin main
```

- [ ] **Step 5: 主仓库最终提交(若有未提交的同步脚本产物,无需提交)**

确认主仓库 `git status` 干净(Task 1–4 已各自提交)。

---

## Self-Review

**Spec 覆盖核对:**
- 确定性命名 `mask_name`/`bbox_name` → Task 1 ✓
- `resolve_display_mask`(Labeling>新鲜Rebuilt>needs_rebuild + mtime)→ Task 1 + 用于 Task 3 ✓
- `build_rebuilt_rgb`(R 精化 + G 保留,三处共用)→ Task 1;接入 Task 2(prebuild)、Task 3(_show_image + _on_rebuild_force)✓
- mtime 缓存失效 → Task 2(prebuild 跳过规则)+ Task 1/3(resolve)✓
- `_show_image` 瘦身 + 去 `find_mask_path` + 去 `_mask_filename` → Task 3 ✓
- 保存/上传确定性命名 → Task 3(save)+ Task 4(ui/worker)✓
- 无需迁移(现有数据已 `{stem}_mask.png`)→ 测试与 e2e 用同命名验证 ✓
- 行为不变(优先级、R/G、精化、S3 名)→ Task 3/4 保持;e2e 校验 ✓

**占位扫描:** 无 TBD/TODO;每个代码步骤含完整代码或精确替换。

**类型/命名一致性:** `mask_store.mask_name/bbox_name/resolve_display_mask/build_rebuilt_rgb` 在 Task 1 定义,Task 2/3/4 调用签名一致;`resolve_display_mask` 返回 `(Path|None, str)`,Task 3 据此分支 `needs_rebuild`;`build_rebuilt_rgb(origin_bgr, coarse_raw)` 两参在三处调用一致。

**已知风险(实现时验证):**
- Task 3 的大段替换需对准原 `_show_image` 边界(Step 0/1/2 块);Step 8 的 grep 兜底确保无残留 `_mask_filename`/`find_mask_path`。
- `_on_rebuild_force` 原代码里局部变量名曾叫 `mask_name`,Task 3 Step 7 统一改为 `name`,避免与 `mask_store.mask_name` 函数混淆。
