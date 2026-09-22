"""SAM2.1 base_plus weights: official URL + checksum, and a safe downloader.

The Windows exe does not bundle weights (keeps the download smaller and lets
upgrades reuse <exe>/checkpoint/); they are fetched on first few-shot use.
Download goes to ``<dest>.part`` and is renamed only after the SHA256 matches,
so an interrupted or corrupted download never looks like usable weights.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

SAM2_WEIGHTS_URL = (
    "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt")
SAM2_WEIGHTS_SHA256 = "a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5"
SAM2_WEIGHTS_SIZE = 323_606_802


class DownloadCancelled(Exception):
    """The progress callback asked to stop."""


def download_weights(url: str, dest: Path, sha256: str, progress=None,
                     chunk_size: int = 1 << 20, timeout: float = 30) -> None:
    """Download ``url`` to ``dest`` if its SHA256 equals ``sha256``.

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
