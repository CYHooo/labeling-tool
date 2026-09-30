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

APP_PREFIX = "LM_LabelingTool-App"
FULL_PREFIX = "LM_LabelingTool-Setup"
DEB_APP = "lm-labeling-tool"
DEB_RUNTIME = "lm-labeling-tool-runtime"
DEB_ARCH = "amd64"

_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+(\S+)$")
_APP_DEB = re.compile(r"^lm-labeling-tool_(?P<ver>[^_]+)-(?P<runtime>r[0-9a-f]+)_amd64\.deb$")


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
        """The first asset's name, for display only. Callers that install must
        iterate `assets`: a Linux full update is two packages."""
        return self.assets[0].name if self.assets else ""


def app_asset_name(version: str, runtime: str, platform: str | None = None) -> str:
    """The small package: only our own code, built against `runtime`.

    The runtime id is in the FILENAME on both platforms, so a client can tell
    from the name alone whether a package matches its own runtime, without
    downloading it. On Linux the deb's Version field stays a clean version
    number -- the runtime binding is expressed by Depends instead."""
    if (platform or current_platform()) == WINDOWS:
        return f"{APP_PREFIX}-v{version}-{runtime}.exe"
    return f"{DEB_APP}_{version}-{runtime}_{DEB_ARCH}.deb"


def full_asset_names(version: str, platform: str | None = None) -> tuple[str, ...]:
    """Everything a machine needs when its runtime does not match.

    Windows: one installer carrying both layers. Linux: the runtime deb plus
    the app deb. The app deb's name needs a runtime id the client does not
    know at this point, so it is spelled with the RUNTIME placeholder and
    resolved against the release's actual asset list by _resolve_full()."""
    if (platform or current_platform()) == WINDOWS:
        return (f"{FULL_PREFIX}-v{version}.exe",)
    return (f"{DEB_RUNTIME}_{version}_{DEB_ARCH}.deb",
            f"{DEB_APP}_{version}-RUNTIME_{DEB_ARCH}.deb")


def _resolve_full(names: tuple[str, ...], version: str,
                  available: dict) -> list[str] | None:
    """Replace the RUNTIME placeholder with the id this release actually
    carries. None when the release is missing any part of a full install."""
    out = []
    for name in names:
        if "-RUNTIME_" not in name:
            if name not in available:
                return None
            out.append(name)
            continue
        matches = [n for n in available
                   if (m := _APP_DEB.match(n)) and m.group("ver") == version]
        if len(matches) != 1:
            # Zero: the release lost its app deb. More than one: ambiguous,
            # and guessing would hand the user a package dpkg refuses.
            return None
        out.append(matches[0])
    return out


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

    Prefers the small app-layer package built against THIS machine's runtime
    id; falls back to the full installer when the runtime changed, when the
    release carries no app package, or when this install predates layering
    and has no runtime id at all. Every asset offered must have a published
    checksum -- an unverifiable download is not installed -- and a full
    update must resolve every one of its parts, or none is offered: half an
    install is worse than none.

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

    candidates: list[tuple[str, tuple[str, ...]]] = []
    if runtime:
        candidates.append(("app", (app_asset_name(version, runtime, platform),)))
    candidates.append(("full", full_asset_names(version, platform)))
    for kind, wanted in candidates:
        names = _resolve_full(wanted, version, assets) if kind == "full" \
            else ([wanted[0]] if wanted[0] in assets else None)
        if not names:
            continue
        # Every part must be verifiable: an unverifiable download is not
        # installed, and half a full install is worse than none.
        if any(n not in sums for n in names):
            continue
        return UpdateInfo(
            version=version, variant=variant,
            assets=tuple(Asset(name=n,
                               url=assets[n]["browser_download_url"],
                               size=int(assets[n].get("size", 0)),
                               sha256=sums[n]) for n in names),
            notes=str(release.get("body") or ""), kind=kind)
    return None
