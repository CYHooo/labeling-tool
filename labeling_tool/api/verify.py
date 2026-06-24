"""Read-back verification after upload.

Re-fetches the session's photos via V1 (`GET .../sessions/{id}/photos/`) and
confirms each uploaded photo's annotation ACTUALLY persisted server-side —
independent of what register-annotations reported. A photo counts as confirmed
only when the server now shows:
  * highlightS3Key  (highlight registered, non-null)
  * repair15S3Key   (15cm boundary registered, non-null)
  * crackMetrics.metricsSource == "user_edit"  (our edit took effect, not the
    stale AI value)
  * pxPerCm matching what we sent (within PX_TOL)

This catches silent drops that updatedPhotoCount alone can miss (e.g. a server
that returns 200 with a full count but didn't persist). Uses only existing
endpoints — no server changes required.
"""

from __future__ import annotations

import csv
from pathlib import Path

PX_TOL = 0.5   # px/cm tolerance for the read-back comparison


def _fetch_all_by_ts(client, session_id: int, page_limit: int = 100) -> dict:
    """Paginate the whole session photo list into {timestamp: photo}."""
    by_ts: dict[int, dict] = {}
    offset = 0
    while True:
        page = client.list_photos(session_id, offset=offset, limit=page_limit)
        photos = page.get("photos", [])
        for p in photos:
            by_ts[int(p["timestamp"])] = p
        total = page.get("total", len(by_ts))
        offset += page_limit
        if offset >= total or not photos:
            break
    return by_ts


def verify_registered(client, session_id: int, items: list[dict],
                      page_limit: int = 100) -> list[dict]:
    """Return a per-item verdict list after reading back the live server state.

    Each verdict: {timestamp, reportPhotoNum, ok, reasons, highlightS3Key,
    repair15S3Key, metricsSource, pxPerCm}.
    """
    by_ts = _fetch_all_by_ts(client, session_id, page_limit)
    verdicts: list[dict] = []
    for it in items:
        ts = int(it["timestamp"])
        p = by_ts.get(ts)
        reasons: list[str] = []
        if p is None:
            verdicts.append({
                "timestamp": ts, "reportPhotoNum": None, "ok": False,
                "reasons": ["not found on server"],
                "highlightS3Key": None, "repair15S3Key": None,
                "metricsSource": None, "pxPerCm": None})
            continue
        high = p.get("highlightS3Key")
        rep = p.get("repair15S3Key")
        cm = p.get("crackMetrics") or {}
        ms = cm.get("metricsSource")
        got_px = p.get("pxPerCm")
        if not high:
            reasons.append("highlight not registered")
        if not rep:
            reasons.append("repair15 not registered")
        if ms != "user_edit":
            reasons.append(f"metricsSource={ms!r} (expected user_edit)")
        exp_px = it.get("pxPerCm")
        if exp_px and got_px and abs(float(got_px) - float(exp_px)) > PX_TOL:
            reasons.append(f"pxPerCm {got_px} != sent {exp_px}")
        verdicts.append({
            "timestamp": ts, "reportPhotoNum": p.get("reportPhotoNum"),
            "ok": not reasons, "reasons": reasons,
            "highlightS3Key": high, "repair15S3Key": rep,
            "metricsSource": ms, "pxPerCm": got_px})
    return verdicts


def write_verify_csv(verdicts: list[dict], path) -> Path:
    """Write a per-photo verification table (CSV) the user can open to confirm
    every uploaded photo's data is present on the server / web side."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "reportPhotoNum", "result", "highlightS3Key",
                    "repair15S3Key", "metricsSource", "pxPerCm", "reasons"])
        for v in verdicts:
            w.writerow([
                v["timestamp"], v.get("reportPhotoNum"),
                "OK" if v["ok"] else "FAIL",
                v.get("highlightS3Key") or "MISSING",
                v.get("repair15S3Key") or "MISSING",
                v.get("metricsSource"),
                v.get("pxPerCm"),
                "; ".join(v["reasons"])])
    return path
