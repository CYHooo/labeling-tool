"""Look up the newest release on GitHub and decide whether it is an update.

Pure logic plus one HTTP call; every failure is raised to the caller, which
decides whether to stay silent (startup check) or report (manual check).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass

from labeling_tool.update.version import DEV_VERSION

GITHUB_REPO = "CYHooo/labeling-tool"
LATEST_URL = "https://api.github.com/repos/{repo}/releases/latest"
SUMS_ASSET = "SHA256SUMS.txt"

# Platform constants defined independently of packaging.layers: the client
# must not import packaging code, only agree with it on these two strings.
WINDOWS = "win32"
LINUX = "linux"

FULL_PREFIX = "LM_LabelingTool-Setup"
DEB_PACKAGE = "lm-labeling-tool"
DEB_ARCH = "amd64"
NOTES_START = "<!-- notes:start -->"
NOTES_END = "<!-- notes:end -->"

_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+(\S+)$")


def current_platform() -> str:
    return WINDOWS if sys.platform.startswith("win") else LINUX


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    variant: str
    assets: tuple[Asset, ...]
    notes: str
    kind: str          # "app" (runtime unchanged) or "full" (reinstall)

    @property
    def total_size(self) -> int:
        return sum(a.size for a in self.assets)

    @property
    def asset_name(self) -> str:
        """The first asset's name, for display only."""
        return self.assets[0].name if self.assets else ""


def full_asset_name(version: str, platform: str | None = None) -> str:
    """The one package a user downloads by hand, and the full update a
    machine takes when its runtime id no longer matches."""
    if (platform or current_platform()) == WINDOWS:
        return f"{FULL_PREFIX}-v{version}.exe"
    return f"{DEB_PACKAGE}_{version}_{DEB_ARCH}.deb"


def update_asset_name(version: str, runtime: str, platform: str | None = None) -> str:
    """The app-layer zip built against `runtime`. The id is in the name so a
    client can tell, without downloading, whether the zip fits its install."""
    tag = "windows" if (platform or current_platform()) == WINDOWS else "linux"
    return f"update-v{version}-{runtime}-{tag}.zip"


def extract_notes(body: str) -> str:
    """The change notes between the markers release_notes.py writes; the
    first eight lines of a body that has none (hand-edited releases)."""
    text = str(body or "")
    start, end = text.find(NOTES_START), text.find(NOTES_END)
    if start != -1 and end > start:
        return text[start + len(NOTES_START):end].strip()
    return "\n".join(text.splitlines()[:8])


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
                runtime: str | None = None,
                platform: str | None = None) -> UpdateInfo | None:
    """Newest release for this install, or None when up to date.

    Offers exactly one asset: the update zip built against THIS machine's
    runtime id when the release has it, otherwise the single full package
    (runtime changed, no zip published, or this install has no runtime id).
    The asset must have a published checksum -- an unverifiable download is
    not installed.

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

    candidates: list[tuple[str, str]] = []
    if runtime:
        candidates.append(("app", update_asset_name(version, runtime, platform)))
    candidates.append(("full", full_asset_name(version, platform)))
    for kind, name in candidates:
        if name not in assets or name not in sums:
            continue  # an unverifiable download is never installed
        a = assets[name]
        return UpdateInfo(
            version=version, variant=variant,
            assets=(Asset(name=name, url=a["browser_download_url"],
                          size=int(a.get("size", 0)), sha256=sums[name]),),
            notes=extract_notes(release.get("body") or ""), kind=kind)
    return None
