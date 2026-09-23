"""Checksum-verified file downloader."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


class DownloadCancelled(Exception):
    """The progress callback asked to stop."""


def download_file(url: str, dest: Path, sha256: str, progress=None,
                  chunk_size: int = 1 << 20, timeout: float = 30) -> None:
    """Download ``url`` to ``dest`` when its SHA256 matches ``sha256``.

    ``progress(done, total)`` is called after every chunk (total is 0 when the
    server sends no Content-Length); returning False cancels. On any failure
    the partial file is removed and an existing ``dest`` is left untouched.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            while chunk := resp.read(chunk_size):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None and progress(done, total) is False:
                    raise DownloadCancelled()
        if digest.hexdigest() != sha256:
            raise ValueError(f"checksum mismatch for {url}: got {digest.hexdigest()}")
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
