"""Batch upload orchestration: presigned -> S3 PUT -> register, paginated at 100 items.

register-annotations dedupes by editBatchId (same id -> 200, NO DB reprocessing),
so EACH batch must get its own id, or every batch after the first is silently
dropped (its highlight/15/metrics never reach the DB while the S3 files still
upload). Each batch uses ``<edit_batch_id>-<batch_index>``: distinct per batch
so all batches register, yet stable per batch so a retry stays idempotent.

Per v1.0.8 each photo uploads three files: mask -> high -> 15 (3 PUTs),
then the batch is registered with maskS3Key/highlightS3Key/repair15S3Key.
"""

from __future__ import annotations

from typing import Callable

from labeling_tool.api.edit_fields import (
    DELETED_KEY, EDIT_LIST_LIMIT, SKIPPED_KEY, timestamps_in)

from labeling_tool.session import naming
from labeling_tool.logging_setup import vlog

FILES_PER_PHOTO = 3          # mask + high + repair15 (V2/V3)
V2_FILE_LIMIT = 100          # api-reference v1.0.8: V2 files array max 100
BATCH_LIMIT = V2_FILE_LIMIT // FILES_PER_PHOTO   # 33 photos -> 99 files (<=100)

# Returns the three byte blobs for one photo: {"mask":..,"high":..,"repair15":..}.
BytesFn = Callable[[int], dict]
ProgressFn = Callable[[int, int], None]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _nth(seq, n, i):
    """The i-th chunk of `seq` (size n), or [] past the end."""
    return list(seq[i * n:(i + 1) * n])


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def _merge(into: list[int], more) -> None:
    """Append `more` to `into`, skipping timestamps already there."""
    for ts in more:
        if ts not in into:
            into.append(ts)


def upload_session(client, *, session_id: int, items: list[dict],
                   bytes_for: BytesFn,
                   edit_batch_id: str,
                   progress: ProgressFn | None = None,
                   surface_updates=(), deletes=()) -> dict:
    """items: register-annotation item dicts (see annotation_payload.build_annotation_item).

    bytes_for(ts) -> {"mask": bytes, "high": bytes, "repair15": bytes}.

    progress(done, total) fires once per photo (after its 3 PUTs) so the caller
    can drive a determinate bar; total is the full item count.

    surface_updates / deletes ride along in the same register calls: batch i
    carries chunk i of items (33), of surface_updates (100) and of deletes
    (100). A batch with no items skips presigned / PUT and only registers.
    Caller contract: a delete is done ONLY if its timestamp is in
    deleted_timestamps (and only timestamps this batch actually sent count);
    everything sent but not confirmed stays pending, and a timestamp is never
    in both deleted_timestamps and a failed entry.
    Retry stays idempotent: batch i always gets the id "<edit_batch_id>-<i>".

    Returns {"uploaded": int, "failed": [...], "anomalies": [...],
             "confirmed_timestamps": [...], "deleted_timestamps": [...],
             "surface_timestamps": [...]}. deleted_timestamps merges the
    server's `deleted` and `skipped` (both mean the photo is gone). A failed
    entry also lists the batch's "surface_timestamps" / "delete_timestamps".

    A batch where the server's updatedPhotoCount is LESS than the photos sent
    (e.g. a silent server-side dedupe/partial write) is recorded in "anomalies"
    and logged at WARNING; its photos are NOT counted as confirmed, so the GUI
    won't mark them synced or report a false success.
    """
    uploaded = 0
    failed: list[dict] = []
    anomalies: list[dict] = []
    confirmed: list[int] = []
    deleted_ts: list[int] = []
    surface_ts: list[int] = []
    surface_updates = list(surface_updates)
    deletes = list(deletes)
    total = len(items)
    base = 0   # items in batches already finished (success or failure)

    has_edits = bool(items or surface_updates or deletes)
    batch_count = max(_ceil_div(len(items), BATCH_LIMIT),
                      _ceil_div(len(surface_updates), EDIT_LIST_LIMIT),
                      _ceil_div(len(deletes), EDIT_LIST_LIMIT),
                      1 if has_edits else 0)

    for idx in range(batch_count):
        batch = _nth(items, BATCH_LIMIT, idx)
        batch_surface = _nth(surface_updates, EDIT_LIST_LIMIT, idx)
        batch_deletes = _nth(deletes, EDIT_LIST_LIMIT, idx)
        sent_surface = [u["timestamp"] for u in batch_surface]
        sent_deletes = [d["timestamp"] for d in batch_deletes]
        # Distinct id per batch (stable for retries) — register dedupes by id,
        # so reusing one id would drop every batch after the first.
        batch_edit_id = f"{edit_batch_id}-{idx}"
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
            url_by_name = {}
            if files:   # an edits-only batch has nothing to upload
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

            extra = {}   # only non-empty, so plain batches keep the old call
            if batch_surface:
                extra["surface_updates"] = batch_surface
            if batch_deletes:
                extra["deletes"] = batch_deletes
            reg = client.register_annotations(
                edit_batch_id=batch_edit_id, session_id=session_id,
                items=batch, **extra)
            updated = reg.get("updatedPhotoCount") if isinstance(reg, dict) else None
            if updated is not None and updated < len(batch):
                # Server accepted the request but persisted fewer than we sent.
                vlog().warning(
                    "UPLOAD ANOMALY: server persisted %d of %d sent "
                    "(editBatchId=%s timestamps=%s)",
                    updated, len(batch), batch_edit_id, timestamps)
                anomalies.append({"timestamps": timestamps,
                                  "sent": len(batch), "updated": int(updated)})
                uploaded += int(updated)
            else:
                uploaded += len(batch)
                confirmed.extend(timestamps)   # fully persisted -> safe to mark synced
            # Last step of the batch: nothing below can raise, so a timestamp
            # is never in both deleted_ts and this batch's failed entry.
            sent = set(sent_deletes)
            reported = (timestamps_in(reg, DELETED_KEY)
                        + timestamps_in(reg, SKIPPED_KEY))
            extras = [t for t in reported if t not in sent]
            if extras:
                vlog().warning(
                    "UPLOAD: server reported deletes this batch never sent "
                    "(editBatchId=%s timestamps=%s); ignored",
                    batch_edit_id, extras)
            _merge(deleted_ts, [t for t in reported if t in sent])
            surface_ts.extend(sent_surface)
        except Exception as e:  # noqa: BLE001 - report per-batch, keep going
            details = getattr(e, "details", None)
            vlog().exception(
                "UPLOAD BATCH FAILED timestamps=%s: %s%s",
                timestamps, e, f" details={details}" if details else "")
            failed.append({
                "timestamps": timestamps, "error": str(e),
                "surface_timestamps": sent_surface,
                "delete_timestamps": sent_deletes})
        finally:
            base += len(batch)
            if progress is not None:
                progress(base, total)

    return {"uploaded": uploaded, "failed": failed,
            "anomalies": anomalies, "confirmed_timestamps": confirmed,
            "deleted_timestamps": deleted_ts, "surface_timestamps": surface_ts}
