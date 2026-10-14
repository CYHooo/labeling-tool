"""The job's photo list (V1 metadata), every page of it."""

from __future__ import annotations

_PAGE = 100


def fetch_all_photos(client, session_id: int) -> list[dict]:
    """Fetch the full photo list of a job (metadata only, paginated).

    Shared by the fetch dialog and the refresh after an upload; a range is
    applied by the caller (filter_photos_by_range)."""
    out: list[dict] = []
    offset = 0
    while True:
        page = client.list_photos(session_id, offset=offset, limit=_PAGE)
        out.extend(page["photos"])
        total = page.get("total", len(out))
        offset += _PAGE
        if offset >= total or not page["photos"]:
            break
    return out
