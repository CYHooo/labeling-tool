import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import release_notes  # noqa: E402

from labeling_tool.update import checker  # noqa: E402


def test_check_korean_rejects_han_and_requires_hangul():
    release_notes.check_korean("- 업데이트 방식 개선")
    with pytest.raises(ValueError):
        release_notes.check_korean("- 每次启动都检查更新")
    with pytest.raises(ValueError):
        release_notes.check_korean("- faster startup")
    with pytest.raises(ValueError):
        release_notes.check_korean("   ")


def test_body_links_the_two_packages_and_marks_the_notes():
    body = release_notes.build_body("0.2.0", "- 첫 번째 단일 설치 파일 배포")
    base = f"https://github.com/{checker.GITHUB_REPO}/releases/download/v0.2.0/"
    assert f"[EXE]({base}{checker.full_asset_name('0.2.0', checker.WINDOWS)})" in body
    assert f"({base}{checker.full_asset_name('0.2.0', checker.LINUX)})" in body
    assert "x86-64 (64-bit)" in body
    assert checker.extract_notes(body) == "- 첫 번째 단일 설치 파일 배포"
    release_notes.check_korean(body.split(checker.NOTES_END)[1])  # the guide is Korean too
