"""Headless upload of a saved local session to EC2 (mirrors ViewerMainWindow._on_upload).

Usage: python -m labeling_tool.scripts.upload_session_cli <sessionId>
Reads BASE/apiKey from labeling_tool/config.json.
"""

import json
import sys
import uuid
from pathlib import Path

import cv2

from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
from labeling_tool.session import naming, mask_store
from labeling_tool.core.mask_codec import decode_mask
from labeling_tool.core.bbox import load_bboxes, load_scale
from labeling_tool.annotation_payload import build_annotation_item
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.uploader import upload_session
from labeling_tool.logging_setup import attach_session_log, vlog

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def main(session_id: int) -> int:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    base, key = cfg["base"], cfg["apiKey"]
    print(f"BASE={base}  sessionId={session_id}")

    ws = Workspace.default(session_id)
    log_path = attach_session_log(ws.session_dir)
    vlog().info("=== CLI upload session %s ===", session_id)
    print(f"log -> {log_path}")
    mf = Manifest.load(ws.manifest_path)

    items, mask_cache = [], {}
    for fn in mf.filenames_in_order():
        entry = mf.get(fn)
        stem = Path(fn).stem
        name = mask_store.mask_name(fn)
        mask_path = ws.labeling_dir / name
        high_path = ws.highlight_dir / name
        rep_path = ws.repair15_dir / name
        if not (mask_path.exists() and high_path.exists() and rep_path.exists()):
            vlog().warning("skip %s: missing mask/high/repair15", fn)
            print(f"  skip {fn}: missing mask/high/repair15")
            continue
        raw = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        crack, spall = (None, None)
        if raw is not None:
            crack, spall = decode_mask(raw, mask_path=str(mask_path))
        boxes = load_bboxes(ws.labeling_dir / f"{stem}.bbox.json")
        measured = load_scale(ws.labeling_dir / f"{stem}.bbox.json")
        px_per_cm = measured if measured else (entry.px_per_cm or 0.0)
        if px_per_cm <= 0:
            print(f"  skip {fn}: no scale")
            continue
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
        items.append(item)
        cm = item["crackMetrics"]
        print(f"  #{entry.report_photo_num:<2} ts={entry.timestamp} "
              f"pxPerCm={px_per_cm:.2f} bbox={cm['bboxCount']} "
              f"defect={cm['defectType']} lenMm={cm['lengthMm']:.1f}")

    if not items:
        print("nothing to upload")
        return 1

    print(f"\nuploading {len(items)} items …")
    batch_id = str(uuid.uuid4())
    client = ViewerApiClient(base_url=base, api_key=key)
    result = upload_session(
        client, session_id=session_id, items=items,
        bytes_for=lambda ts: mask_cache[ts], edit_batch_id=batch_id,
        progress=lambda d, t: print(f"  progress {d}/{t}"))

    if not result["failed"]:
        mf.mark_synced(
            [fn for fn in mf.filenames_in_order()
             if mf.get(fn).timestamp in mask_cache], batch_id=batch_id)
        mf.save(ws.manifest_path)
    print(f"\nuploaded={result['uploaded']}  failed_batches={len(result['failed'])}")
    for f in result["failed"]:
        print("  FAILED:", f["error"][:300])
    return 0 if not result["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 18))
