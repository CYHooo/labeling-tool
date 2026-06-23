"""Background thread that builds upload items AND uploads them, off the UI thread.

Both halves are heavy and must not run on the UI thread:
  * building items reads each Labeling mask (full-res PNG decode) and runs the
    crack metric (skeleton + per-pixel width) — ~1.5s per panorama;
  * uploading does the presigned -> PUT -> register network I/O.
Doing the build on the UI thread froze the window ("not responding") even
though only the network part was threaded. Now the whole job runs here and
reports progress via signals delivered to the GUI thread.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
from PyQt5.QtCore import QThread, pyqtSignal

from labeling_tool.session import mask_store
from labeling_tool.core.mask_codec import decode_mask
from labeling_tool.core.bbox import load_bboxes, load_scale
from labeling_tool.session import naming
from labeling_tool.annotation_payload import build_annotation_item
from labeling_tool.api.uploader import upload_session
from labeling_tool.logging_setup import vlog


class UploadWorker(QThread):
    progress = pyqtSignal(int, int, str)   # (done, total, phase: 'prepare'|'upload')
    done = pyqtSignal(dict)                # upload result (+ 'timestamps')
    error = pyqtSignal(str)

    def __init__(self, client, *, session_id: int, specs: list,
                 labeling_dir: str, edit_batch_id: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._session_id = session_id
        self._specs = specs              # [{filename, timestamp, px_per_cm, scale_source}]
        self._labeling_dir = labeling_dir
        self._batch_id = edit_batch_id

    @property
    def batch_id(self) -> str:
        return self._batch_id

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

    def run(self):
        try:
            t0 = time.perf_counter()
            items, cache = self._build_items()
            if not items:
                self.done.emit({"uploaded": 0, "failed": [],
                                "timestamps": [], "batch_id": self._batch_id})
                return
            result = upload_session(
                self._client, session_id=self._session_id, items=items,
                bytes_for=lambda ts: cache[ts],
                edit_batch_id=self._batch_id,
                progress=lambda d, t: self.progress.emit(d, t, "upload"))
            # Only mark photos the server CONFIRMED persisting as synced; a
            # batch with an anomaly (updatedPhotoCount < sent) is excluded so we
            # never report a false success.
            result["timestamps"] = result.get("confirmed_timestamps",
                                               list(cache.keys()))
            result["batch_id"] = self._batch_id
            vlog().info("upload finished: uploaded=%d failed_batches=%d "
                        "anomalies=%d total=%.1fs",
                        result["uploaded"], len(result["failed"]),
                        len(result.get("anomalies", [])),
                        time.perf_counter() - t0)
            self.done.emit(result)
        except Exception as e:  # noqa: BLE001 - surface to UI, never crash thread
            vlog().exception("upload worker error: %s", e)
            self.error.emit(str(e))
