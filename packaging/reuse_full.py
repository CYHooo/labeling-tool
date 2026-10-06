"""Reuse the previous release's full installer when the runtime is unchanged.

Compressing the ~4 GB full installer is over half of a release build (about
11 of 18 minutes), and on a code-only release its runtime layer -- nearly
all of those bytes -- is identical to the previous one. So a code-only
release ships the previous full installer again, under this release's
asset name. A new user installs the previous version and the update zip
brings it up to date on first launch (every launch checks).

It is attached under THIS version's name because every client ever shipped
looks for exactly full_asset_name(<latest version>) in the latest release;
a release without it would leave anyone needing a full install -- e.g. an
install on an older runtime -- with no update offered at all.

"Runtime unchanged" is decided by the previous release itself: its update
zip is named for the runtime id it was built against, and if that id is
ours, its full installer holds our runtime layer byte for byte.

Called by CI (.github/workflows/release.yml); PowerShell has no
heredoc, so the logic lives here where it is unit-tested.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labeling_tool.update import checker  # noqa: E402


def plan_reuse(release: dict, runtime: str,
               platform: str = checker.WINDOWS) -> tuple[str, str] | None:
    """(previous tag, its full package's asset name) when that package
    carries our runtime layer; None when a fresh full build is needed.
    The Windows installer and the Linux deb (packaging/reuse_deb.py) both
    use it.

    `release` is `gh release view --json tagName,assets` for the latest
    published release."""
    tag = str(release.get("tagName") or "")
    version = tag.lstrip("vV")
    if not version or checker.parse_version(version) is None:
        return None
    names = {a.get("name") for a in release.get("assets") or []}
    if checker.update_asset_name(version, runtime, platform) not in names:
        return None   # runtime changed, or that release predates update zips
    full = checker.full_asset_name(version, platform)
    if full not in names or checker.SUMS_ASSET not in names:
        return None
    return tag, full


def verify(sums_path: Path, file_path: Path) -> bool:
    """True when file_path's SHA-256 matches its line in the SHA256SUMS file
    it was published with. A reused installer is re-published under a new
    checksum line, so it must be proven intact first."""
    sums = checker.parse_sha256sums(Path(sums_path).read_text(encoding="utf-8"))
    expected = sums.get(Path(file_path).name)
    if not expected:
        return False
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) in (3, 4) and args[0] == "plan":
        release = json.loads(Path(args[1]).read_text(encoding="utf-8-sig"))
        found = plan_reuse(release, args[2], args[3] if len(args) == 4 else checker.WINDOWS)
        if found:
            print(f"{found[0]}\t{found[1]}")
        return 0
    if len(args) == 3 and args[0] == "verify":
        ok = verify(Path(args[1]), Path(args[2]))
        print("checksum ok" if ok else "checksum MISMATCH", file=sys.stderr)
        return 0 if ok else 1
    print("usage: reuse_full.py plan <release.json> <runtime-id> [win32|linux]\n"
          "       reuse_full.py verify <SHA256SUMS.txt> <file>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
