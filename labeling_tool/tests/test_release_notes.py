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


def test_body_is_only_the_table_and_the_notes():
    """The page carries the download table and the change notes, nothing else:
    no file guide after the notes and no heading repeating the notes' own."""
    body = release_notes.build_body("0.2.0", "## 주요 변경 사항\n\n- 개선")
    assert body.rstrip().endswith(checker.NOTES_END)
    head = body.split(checker.NOTES_START)[0]
    assert [line for line in head.splitlines() if line.startswith("#")] == []


def test_cli_check_and_body(tmp_path):
    # Test: check command with Korean text returns 0
    korean_file = tmp_path / "korean.txt"
    korean_file.write_text("- 업데이트 방식 개선", encoding="utf-8")
    assert release_notes.main(["check", str(korean_file)]) == 0

    # Test: check command with Chinese text returns 1
    chinese_file = tmp_path / "chinese.txt"
    chinese_file.write_text("- 每次启动都检查更新", encoding="utf-8")
    assert release_notes.main(["check", str(chinese_file)]) == 1

    # Test: body command with Korean notes returns 0 and writes correct body
    notes_file = tmp_path / "notes.txt"
    notes_file.write_text("- 첫 번째 단일 설치 파일 배포", encoding="utf-8")
    out_file = tmp_path / "body.txt"
    assert release_notes.main(["body", "0.2.0", str(notes_file), str(out_file)]) == 0
    assert out_file.exists()
    body_text = out_file.read_text(encoding="utf-8")
    assert checker.extract_notes(body_text) == "- 첫 번째 단일 설치 파일 배포"

    # Test: body command with Chinese notes returns 1 and does not write output
    chinese_notes_file = tmp_path / "chinese_notes.txt"
    chinese_notes_file.write_text("- 每次启动都检查更新", encoding="utf-8")
    out_file_2 = tmp_path / "body2.txt"
    assert release_notes.main(["body", "0.2.0", str(chinese_notes_file), str(out_file_2)]) == 1
    assert not out_file_2.exists()

    # Test: main with no arguments returns 2
    assert release_notes.main([]) == 2
