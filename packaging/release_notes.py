"""The Korean release page: the download table, then the change notes.

Change notes come from the annotated tag's message, which must be Korean.
The updater shows only the part between the notes markers
(checker.extract_notes), so the table never reaches its dialog.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labeling_tool.update import checker  # noqa: E402

_HAN = re.compile(r"[一-鿿]")
_HANGUL = re.compile(r"[가-힣]")


def check_korean(text: str) -> None:
    if _HAN.search(text or ""):
        raise ValueError("release notes must be Korean: Chinese characters found")
    if not _HANGUL.search(text or ""):
        raise ValueError("release notes must be Korean: no Hangul found")


def build_body(version: str, notes: str, repo: str = checker.GITHUB_REPO) -> str:
    base = f"https://github.com/{repo}/releases/download/v{version}/"
    exe = checker.full_asset_name(version, checker.WINDOWS)
    deb = checker.full_asset_name(version, checker.LINUX)
    return "\n".join([
        "| Architecture | Windows | Ubuntu 22.04 / 24.04 |",
        "|---|---|---|",
        f"| x86-64 (64-bit) | [EXE]({base}{exe}) | [Download (.deb)]({base}{deb}) |",
        "",
        checker.NOTES_START,
        notes.strip(),
        checker.NOTES_END,
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) == 2 and args[0] == "check":
            check_korean(Path(args[1]).read_text(encoding="utf-8"))
            print("release notes are Korean")
            return 0
        if len(args) == 4 and args[0] == "body":
            notes = Path(args[2]).read_text(encoding="utf-8")
            check_korean(notes)
            Path(args[3]).write_text(build_body(args[1], notes), encoding="utf-8")
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("usage: release_notes.py check <notes> | body <version> <notes> <out>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
