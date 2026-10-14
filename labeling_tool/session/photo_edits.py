"""Local, not-yet-uploaded photo edits kept on the manifest entry: a changed
surface (floor / wall / ceiling) and a pending delete. The tool never works
out a surface itself; it shows the server's value or the user's choice."""

from __future__ import annotations

from labeling_tool.api.edit_fields import SURFACES, normalize_surface, photo_fields


def shown_surface(entry) -> str | None:
    if entry.surface_edit is not None:
        return normalize_surface(entry.surface_edit)
    return normalize_surface(entry.surface)


def set_surface(entry, value: str) -> bool:
    if value not in SURFACES:
        raise ValueError(f"unknown surface: {value!r}")
    new = None if value == normalize_surface(entry.surface) else value
    if new == entry.surface_edit:
        return False
    entry.surface_edit = new
    return True


def toggle_delete(entry) -> bool:
    entry.delete_pending = not entry.delete_pending
    return entry.delete_pending


def has_pending_edit(entry) -> bool:
    return entry.surface_edit is not None or bool(entry.delete_pending)


def surface_updates(entries) -> list[dict]:
    return [{"timestamp": int(e.timestamp), "surface": e.surface_edit}
            for e in sorted(entries, key=lambda e: e.timestamp)
            if e.surface_edit is not None and not e.delete_pending]


def deletes(entries) -> list[dict]:
    return [{"timestamp": int(e.timestamp)}
            for e in sorted(entries, key=lambda e: e.timestamp) if e.delete_pending]


def apply_photo_refresh(manifest, photos: list[dict]) -> bool:
    """Take the server's photo numbers and surface fields for the photos the
    manifest has (matched by timestamp). Photos the server did not list stay
    as they are (never removed here), and local edits are left alone.
    True if anything changed."""
    by_ts = {}
    for p in photos or []:
        if not isinstance(p, dict):
            continue
        ts = p.get("timestamp")
        if isinstance(ts, int) and not isinstance(ts, bool):
            by_ts[ts] = p
    changed = False
    for entry in manifest.photos.values():
        p = by_ts.get(int(entry.timestamp))
        if p is None:
            continue
        fields = photo_fields(p)
        num = p.get("reportPhotoNum")
        if isinstance(num, int) and not isinstance(num, bool):
            fields["report_photo_num"] = num
        for name, value in fields.items():
            if getattr(entry, name) != value:
                setattr(entry, name, value)
                changed = True
    return changed
