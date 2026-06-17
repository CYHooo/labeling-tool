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
