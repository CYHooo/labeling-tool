"""Batch upload orchestration: V2 -> V3 -> V4, paginated at 100 items.

A single editBatchId is reused across pages and retries so the whole
session is idempotent (V4: same id -> 200, no DB reprocessing).
"""

from __future__ import annotations

from typing import Callable

from labeling_tool.session import naming

BATCH_LIMIT = 100

MaskBytesFn = Callable[[int], bytes]
ProgressFn = Callable[[int, int], None]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def upload_session(client, *, session_id: int, items: list[dict],
                   mask_bytes_for: MaskBytesFn,
                   edit_batch_id: str,
                   progress: ProgressFn | None = None) -> dict:
    """items: V4 item dicts (see annotation_payload.build_annotation_item).

    progress(done, total) fires after each mask PUT so the caller can drive a
    determinate progress bar; total is the full item count.

    Returns {"uploaded": int, "failed": [{"timestamps": [...], "error": str}]}.
    """
    uploaded = 0
    failed: list[dict] = []
    total = len(items)
    base = 0   # items in batches already finished (success or failure)

    for batch in _chunks(items, BATCH_LIMIT):
        timestamps = [it["timestamp"] for it in batch]
        # Read each mask once and reuse for both sizeBytes (V2) and PUT (V3).
        batch_bytes = {ts: mask_bytes_for(ts) for ts in timestamps}
        try:
            # V2: presigned URLs for this batch's masks
            files = [{
                "filename": naming.mask_filename(ts),
                "timestamp": ts,
                "contentType": "image/png",
                "sizeBytes": len(batch_bytes[ts]),
            } for ts in timestamps]
            presigned = client.request_presigned(session_id, files)
            url_by_name = {u["filename"]: u for u in presigned["urls"]}

            # V3: PUT each mask to its presigned URL
            for i, ts in enumerate(timestamps, start=1):
                u = url_by_name[naming.mask_filename(ts)]
                client.put_mask(
                    u["presignedUrl"], batch_bytes[ts],
                    content_type="image/png",
                    cache_control=u.get("cacheControl",
                                        "max-age=0, must-revalidate"))
                if progress is not None:
                    progress(base + i, total)

            # V4: register the whole batch
            client.register_annotations(
                edit_batch_id=edit_batch_id, session_id=session_id,
                items=batch)
            uploaded += len(batch)
        except Exception as e:  # noqa: BLE001 - report per-batch, keep going
            failed.append({"timestamps": timestamps, "error": str(e)})
        finally:
            # Advance past the whole batch so the bar reaches total even if a
            # batch failed partway.
            base += len(batch)
            if progress is not None:
                progress(base, total)

    return {"uploaded": uploaded, "failed": failed}
