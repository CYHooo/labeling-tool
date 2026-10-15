"""Batch upload orchestration: presigned -> S3 PUT -> register, paginated at 100 items.

register-annotations dedupes by editBatchId (same id -> 200, NO DB reprocessing),
so EACH batch must get its own id, or every batch after the first is silently
dropped (its highlight/15/metrics never reach the DB while the S3 files still
upload). Each item batch uses ``<edit_batch_id>-<batch_index>`` and each
delete batch ``<edit_batch_id>-d<batch_index>``: distinct per batch so all
batches register, yet stable per batch so a retry stays idempotent.

Per v1.0.8 each photo uploads three files: mask -> high -> 15 (3 PUTs),
then the batch is registered with maskS3Key/highlightS3Key/repair15S3Key.
"""

from __future__ import annotations

from typing import Callable

from labeling_tool.api.edit_fields import (
    DELETED_KEY, EDIT_LIST_LIMIT, SKIP_DELETES, SKIP_ITEMS, SKIP_SURFACE,
    SURFACE_UPDATED_KEY, skipped_by_kind, timestamps_in)

from labeling_tool.api.errors import ViewerApiError
from labeling_tool.session import naming
from labeling_tool.logging_setup import vlog

PHOTO_NOT_FOUND = "PHOTO_NOT_FOUND"

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


def _files_for(timestamps, batch_bytes) -> list[dict]:
    """The presigned request: 3 files per photo (mask / high / 15)."""
    files = []
    for ts in timestamps:
        blobs = batch_bytes[ts]
        for fname, kind in ((naming.mask_filename(ts), "mask"),
                            (naming.high_filename(ts), "high"),
                            (naming.repair15_filename(ts), "repair15")):
            files.append({"filename": fname, "timestamp": ts,
                          "contentType": "image/png",
                          "sizeBytes": len(blobs[kind])})
    return files


def _missing_photo(exc, timestamps) -> int | None:
    """The timestamp a presign PHOTO_NOT_FOUND names, if it is one of
    `timestamps`; None for any other error."""
    if not isinstance(exc, ViewerApiError) or exc.code != PHOTO_NOT_FOUND:
        return None
    ts = exc.details.get("timestamp") if isinstance(exc.details, dict) else None
    if isinstance(ts, int) and not isinstance(ts, bool) and ts in timestamps:
        return ts
    return None


def _presign(client, session_id, timestamps, batch_bytes):
    """Presigned URLs for `timestamps`, dropping photos the server no longer
    has. The live server rejects the WHOLE request with 404 PHOTO_NOT_FOUND
    naming the first missing photo, so each such photo is dropped and the
    rest asked again (at most once per photo). Returns (url_by_name,
    remaining timestamps, dropped timestamps); any other error is raised."""
    remaining = list(timestamps)
    dropped: list[int] = []
    while remaining:
        try:
            presigned = client.request_presigned(
                session_id, _files_for(remaining, batch_bytes))
        except ViewerApiError as exc:
            ts = _missing_photo(exc, remaining)
            if ts is None:
                raise
            vlog().warning("UPLOAD: photo %s is not on the server (presign "
                           "PHOTO_NOT_FOUND); left out of this batch", ts)
            remaining.remove(ts)
            dropped.append(ts)
            continue
        return ({u["filename"]: u for u in presigned["urls"]},
                remaining, dropped)
    return {}, remaining, dropped


def _confirmed_deletes(reg, sent_deletes, batch_edit_id) -> list[int]:
    """The deletes a register response confirms, among those it was sent.
    A delete skipped for a missing photo is gone all the same; unkinded
    skips (pre-release shape) only ever meant deletes. Timestamps the
    call never sent are logged and ignored."""
    skipped = skipped_by_kind(reg)
    if skipped.get(None):
        vlog().warning(
            "UPLOAD: server skipped entries without a kind "
            "(editBatchId=%s timestamps=%s); read as deletes",
            batch_edit_id, skipped[None])
    reported = (timestamps_in(reg, DELETED_KEY)
                + skipped.get(SKIP_DELETES, []) + skipped.get(None, []))
    sent = set(sent_deletes)
    extras = [t for t in reported if t not in sent]
    if extras:
        vlog().warning(
            "UPLOAD: server reported deletes this batch never sent "
            "(editBatchId=%s timestamps=%s); ignored",
            batch_edit_id, extras)
    return [t for t in reported if t in sent]


def upload_session(client, *, session_id: int, items: list[dict],
                   bytes_for: BytesFn,
                   edit_batch_id: str,
                   progress: ProgressFn | None = None,
                   surface_updates=(), deletes=()) -> dict:
    """items: register-annotation item dicts (see annotation_payload.build_annotation_item).

    bytes_for(ts) -> {"mask": bytes, "high": bytes, "repair15": bytes}.

    progress(done, total) fires once per photo (after its 3 PUTs) so the caller
    can drive a determinate bar; total is the full item count.

    Deletes go FIRST, in their own register calls of up to 100 (items=[],
    no surfaceUpdates, no presigned / PUT), ids "<edit_batch_id>-d<i>"; they
    do not move the progress bar, and a failed one does not stop the rest.
    Then the item batches: batch i carries chunk i of items (33) and of
    surface_updates (100), id "<edit_batch_id>-<i>"; a batch with no items
    skips presigned / PUT and only registers its surfaces.
    Caller contract: a delete is done ONLY if its timestamp is in
    deleted_timestamps (and only timestamps that call actually sent count);
    everything sent but not confirmed stays pending, and a timestamp is never
    in both deleted_timestamps and a failed entry.
    Retry stays idempotent: every batch keeps its id across retries.

    Returns {"uploaded": int, "failed": [...], "anomalies": [...],
             "confirmed_timestamps": [...], "deleted_timestamps": [...],
             "surface_timestamps": [...], "skipped_timestamps": [...]}.
    deleted_timestamps merges the server's `deleted` and the `skipped` deletes
    (both mean the photo is gone). surface_timestamps follows the server's
    `surfaceUpdated` (v1.0.16). skipped_timestamps lists mask / surface edits
    for photos the server no longer has (deleted by someone else): those
    register `skipped`, and items presign rejects with PHOTO_NOT_FOUND (they
    are dropped and the rest of the batch goes on; with no item left, the
    batch registers only its surface updates). A failed entry also lists the
    batch's "surface_timestamps" / "delete_timestamps" (a delete batch's
    entry has no "timestamps").

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
    skipped_ts: list[int] = []   # items / surfaces for photos the server lacks
    surface_updates = list(surface_updates)
    deletes = list(deletes)
    total = len(items)
    base = 0   # items in batches already finished (success or failure)

    # Phase 1: deletes first, in their own register calls (no items, no
    # surfaces, no presign / PUT). A failed delete batch leaves its deletes
    # pending and does not stop the item batches.
    for idx in range(_ceil_div(len(deletes), EDIT_LIST_LIMIT)):
        batch_deletes = _nth(deletes, EDIT_LIST_LIMIT, idx)
        sent_deletes = [d["timestamp"] for d in batch_deletes]
        batch_edit_id = f"{edit_batch_id}-d{idx}"
        try:
            reg = client.register_annotations(
                edit_batch_id=batch_edit_id, session_id=session_id,
                items=[], deletes=batch_deletes)
            _merge(deleted_ts, _confirmed_deletes(reg, sent_deletes, batch_edit_id))
        except Exception as e:  # noqa: BLE001 - report per-batch, keep going
            details = getattr(e, "details", None)
            vlog().exception(
                "UPLOAD DELETE BATCH FAILED timestamps=%s: %s%s",
                sent_deletes, e, f" details={details}" if details else "")
            failed.append({"timestamps": [], "error": str(e),
                           "surface_timestamps": [],
                           "delete_timestamps": sent_deletes})

    # Phase 2: item batches (33 photos), surface chunk i riding in batch i.
    batch_count = max(_ceil_div(len(items), BATCH_LIMIT),
                      _ceil_div(len(surface_updates), EDIT_LIST_LIMIT))

    for idx in range(batch_count):
        batch = _nth(items, BATCH_LIMIT, idx)
        batch_surface = _nth(surface_updates, EDIT_LIST_LIMIT, idx)
        sent_surface = [u["timestamp"] for u in batch_surface]
        # Distinct id per batch (stable for retries) — register dedupes by id,
        # so reusing one id would drop every batch after the first.
        batch_edit_id = f"{edit_batch_id}-{idx}"
        timestamps = [it["timestamp"] for it in batch]
        # Read each photo's 3 blobs once; reuse for sizeBytes + PUT.
        batch_bytes = {ts: bytes_for(ts) for ts in timestamps}
        try:
            # an edits-only batch has nothing to upload; a photo the server
            # no longer has is dropped here (like a register `skipped` item)
            url_by_name, timestamps, gone_at_presign = _presign(
                client, session_id, timestamps, batch_bytes)
            # recorded now: a later failure must not list them as failed
            _merge(skipped_ts, gone_at_presign)
            kept = set(timestamps)
            batch_items = [it for it in batch if it["timestamp"] in kept]

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
            if batch_items or extra:
                reg = client.register_annotations(
                    edit_batch_id=batch_edit_id, session_id=session_id,
                    items=batch_items, **extra)
            else:   # every photo was gone and nothing else to send
                reg = None
            # v1.0.16: a photo the server no longer has is skipped, not an
            # error; such items are neither saved nor an anomaly.
            skipped = skipped_by_kind(reg)
            gone_items = set(skipped.get(SKIP_ITEMS, ())) & set(timestamps)
            saved = [ts for ts in timestamps if ts not in gone_items]
            updated = reg.get("updatedPhotoCount") if isinstance(reg, dict) else None
            # updatedPhotoCount counts saved items + changed surfaces (each
            # photo once), so it can exceed the items but never fall short.
            expected = set(saved)
            if isinstance(reg, dict) and isinstance(reg.get(SURFACE_UPDATED_KEY), list):
                expected |= set(timestamps_in(reg, SURFACE_UPDATED_KEY)) & set(sent_surface)
            if updated is not None and updated < len(expected):
                # Server accepted the request but persisted fewer than we sent.
                vlog().warning(
                    "UPLOAD ANOMALY: server persisted %d of %d sent "
                    "(editBatchId=%s timestamps=%s)",
                    updated, len(expected), batch_edit_id, sorted(expected))
                anomalies.append({"timestamps": saved,
                                  "sent": len(expected), "updated": int(updated)})
                uploaded += int(updated)
            else:
                uploaded += len(saved)
                confirmed.extend(saved)   # fully persisted -> safe to mark synced
            # an item batch sends no deletes: any it reports are logged
            _confirmed_deletes(reg, [], batch_edit_id)
            gone_surface = set(skipped.get(SKIP_SURFACE, ()))
            if isinstance(reg, dict) and isinstance(reg.get(SURFACE_UPDATED_KEY), list):
                changed = set(timestamps_in(reg, SURFACE_UPDATED_KEY))
                surface_ts.extend(t for t in sent_surface if t in changed)
            else:   # a server before v1.0.16: the batch succeeding confirms it
                surface_ts.extend(t for t in sent_surface if t not in gone_surface)
            _merge(skipped_ts, sorted(gone_items | (gone_surface & set(sent_surface))))
        except Exception as e:  # noqa: BLE001 - report per-batch, keep going
            details = getattr(e, "details", None)
            vlog().exception(
                "UPLOAD BATCH FAILED timestamps=%s: %s%s",
                timestamps, e, f" details={details}" if details else "")
            failed.append({
                "timestamps": timestamps, "error": str(e),
                "surface_timestamps": sent_surface,
                "delete_timestamps": []})
        finally:
            base += len(batch)
            if progress is not None:
                progress(base, total)

    return {"uploaded": uploaded, "failed": failed,
            "anomalies": anomalies, "confirmed_timestamps": confirmed,
            "deleted_timestamps": deleted_ts, "surface_timestamps": surface_ts,
            "skipped_timestamps": skipped_ts}
