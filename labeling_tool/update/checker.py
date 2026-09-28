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
APP_PREFIX = "LM_LabelingTool-App"
FULL_PREFIX = "LM_LabelingTool-Setup"
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
    kind: str          # "app" (runtime unchanged) or "full" (reinstall)


def app_asset_name(version: str, runtime: str) -> str:
    """The small package: only our own code, built against `runtime`."""
    return f"{APP_PREFIX}-v{version}-{runtime}.exe"


def full_asset_name(version: str) -> str:
    """The whole thing, runtime layer included."""
    return f"{FULL_PREFIX}-v{version}.exe"


def parse_version(text: str) -> tuple[int, ...] | None:
    """(1, 2, 3) for "v1.2.3"; None when it is not a plain numeric version."""
    parts = str(text).lstrip("vV").split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _normalize_version(v: tuple[int, ...]) -> tuple[int, ...]:
    """Strip trailing zeros: (1, 2, 0) becomes (1, 2)."""
    while v and v[-1] == 0:
        v = v[:-1]
    return v or (0,)


def is_newer(latest: str, current: str) -> bool:
    if current == DEV_VERSION:
        return False  # never offer updates to a source/dev build
    a, b = parse_version(latest), parse_version(current)
    if not (a and b):
        return False
    return _normalize_version(a) > _normalize_version(b)


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
                timeout: float = 10, opener=None,
                runtime: str | None = None) -> UpdateInfo | None:
    """Newest release for this install, or None when up to date.

    Prefers the small app-layer package built against THIS machine's runtime
    id; falls back to the full installer when the runtime changed, when the
    release carries no app package, or when this install predates layering
    and has no runtime id at all. An asset without a published checksum is
    never offered -- an unverifiable download is not installed.

    Network and parse errors are raised to the caller.
    """
    opener = opener or urllib.request.urlopen
    release = json.loads(_read(opener, LATEST_URL.format(repo=repo), timeout))
    tag = str(release.get("tag_name", ""))
    version = tag.lstrip("vV")
    if not is_newer(version, current_version):
        return None
    assets = {a["name"]: a for a in release.get("assets", [])}
    if SUMS_ASSET not in assets:
        return None
    sums = parse_sha256sums(
        _read(opener, assets[SUMS_ASSET]["browser_download_url"], timeout))

    candidates = []
    if runtime:
        candidates.append(("app", app_asset_name(version, runtime)))
    candidates.append(("full", full_asset_name(version)))
    for kind, name in candidates:
        if name in assets and name in sums:
            asset = assets[name]
            return UpdateInfo(version=version, variant=variant, asset_name=name,
                              asset_url=asset["browser_download_url"],
                              size=int(asset.get("size", 0)), sha256=sums[name],
                              notes=str(release.get("body") or ""), kind=kind)
    return None
