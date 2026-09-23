"""Look up the newest release on GitHub and decide whether it is an update.

Pure logic plus one HTTP call; every failure is raised to the caller, which
decides whether to stay silent (startup check) or report (manual check).
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from labeling_tool.update.version import DEV_VERSION

GITHUB_REPO = "CYHooo/labeling-tool"
LATEST_URL = "https://api.github.com/repos/{repo}/releases/latest"
SUMS_ASSET = "SHA256SUMS.txt"
_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+(\S+)$")


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    variant: str
    asset_name: str
    asset_url: str
    size: int
    sha256: str
    notes: str


def asset_name_for(variant: str, version: str) -> str:
    return f"LabelingTool-{variant}-Setup-v{version}.exe"


def parse_version(text: str) -> tuple[int, ...] | None:
    """(1, 2, 3) for "v1.2.3"; None when it is not a plain numeric version."""
    parts = str(text).lstrip("vV").split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def is_newer(latest: str, current: str) -> bool:
    if current == DEV_VERSION:
        return False  # never offer updates to a source/dev build
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def parse_sha256sums(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = _SUM_LINE.match(line.strip())
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def _read(opener, url: str, timeout: float) -> str:
    with opener(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def find_update(current_version: str, variant: str, repo: str = GITHUB_REPO,
                timeout: float = 10, opener=None) -> UpdateInfo | None:
    """Newest release for ``variant`` if it is newer than ``current_version``.

    Returns None when up to date, when the release has no asset for this
    variant, or when the asset has no published checksum (never install an
    unverifiable download). Network and parse errors are raised.
    """
    opener = opener or urllib.request.urlopen
    release = json.loads(_read(opener, LATEST_URL.format(repo=repo), timeout))
    tag = str(release.get("tag_name", ""))
    version = tag.lstrip("vV")
    if not is_newer(version, current_version):
        return None
    assets = {a["name"]: a for a in release.get("assets", [])}
    wanted = asset_name_for(variant, version)
    if wanted not in assets or SUMS_ASSET not in assets:
        return None
    sums = parse_sha256sums(
        _read(opener, assets[SUMS_ASSET]["browser_download_url"], timeout))
    if wanted not in sums:
        return None
    asset = assets[wanted]
    return UpdateInfo(version=version, variant=variant, asset_name=wanted,
                      asset_url=asset["browser_download_url"],
                      size=int(asset.get("size", 0)), sha256=sums[wanted],
                      notes=str(release.get("body") or ""))
