"""Reuse the previous release's runtime deb when the runtime is unchanged.

Every release must carry a runtime deb, even on a day nobody downloads it.
Whoever needs a full install -- a fresh machine, or an old install whose
runtime no longer matches -- only ever looks in the LATEST release for one
exact name: lm-labeling-tool-runtime_<latest version>_amd64.deb. If that
name is missing, they get nothing installable, and the failure is silent:
no error, the updater just offers nothing.

So that file must exist in every release, even when its bytes are
identical to the previous one. Re-running xz over 1.4 GB to reproduce the
same bytes is waste, so instead: download the previous release's runtime
deb, check it against its own published checksum, and re-publish it under
this release's filename.

"Runtime unchanged" is decided by the previous release itself: it carries
an app deb built against a runtime id, named lm-labeling-tool_<ver>-<runtime
id>_amd64.deb. If that id matches ours, the previous release's runtime deb
holds our runtime layer byte for byte -- PROVIDED that release also has a
runtime deb to copy (it might not, e.g. the first release after this
feature shipped only had Windows assets, or had no runtime deb at all
because this feature had not shipped yet).

The runtime deb's name carries only a version, never a runtime id -- this
is intentional: a client doing a full update knows the target version
before this release is built, but has no way to know the new runtime id.

This is the Linux counterpart to packaging/reuse_full.py (Windows); see
that module's docstring for the full rationale. Called by CI
(.github/workflows/build-deb.yml); logic lives here so it is unit-tested.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labeling_tool.update import checker  # noqa: E402


def plan(release_json: dict, runtime_id: str) -> tuple[str, str] | None:
    """(previous tag, its runtime deb's asset name) when that deb carries
    our runtime layer byte for byte; None when a fresh runtime build is
    needed.

    `release_json` is `gh release view --json tagName,assets` for the
    latest published release."""
    tag = str(release_json.get("tagName") or "")
    version = tag.lstrip("vV")
    if not version or checker.parse_version(version) is None:
        return None
    names = {a.get("name") for a in release_json.get("assets") or []}
    if checker.app_asset_name(version, runtime_id, checker.LINUX) not in names:
        return None   # no app deb for this version, or the runtime moved
    runtime_deb = checker.full_asset_names(version, checker.LINUX)[0]
    if runtime_deb not in names or checker.SUMS_ASSET not in names:
        return None   # no runtime deb to copy, or nothing to verify it against
    return tag, runtime_deb


def verify(sums_text: str, path: Path) -> bool:
    """True when path's SHA-256 matches its line in a published SHA256SUMS
    file. A reused deb is re-published under a new checksum line, so it
    must be proven intact first; a file with no published checksum is
    never accepted -- republishing it under our name would launder a
    possibly corrupted or tampered asset into a new release."""
    sums = checker.parse_sha256sums(sums_text)
    expected = sums.get(Path(path).name)
    if not expected:
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 3 and args[0] == "plan":
        release = json.loads(Path(args[1]).read_text(encoding="utf-8-sig"))
        found = plan(release, args[2])
        if found:
            print(f"{found[0]}\t{found[1]}")
        return 0
    if len(args) == 3 and args[0] == "verify":
        # Matches reuse_full.py's verify(): the sums file is our own
        # published artifact, never user-authored, so no BOM tolerance.
        sums_text = Path(args[1]).read_text(encoding="utf-8")
        ok = verify(sums_text, Path(args[2]))
        print("checksum ok" if ok else "checksum MISMATCH", file=sys.stderr)
        return 0 if ok else 1
    print("usage: reuse_runtime.py plan <release.json> <runtime-id>\n"
          "       reuse_runtime.py verify <SHA256SUMS.txt> <file>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
