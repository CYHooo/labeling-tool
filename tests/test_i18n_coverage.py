"""Every language covers every key, and UI modules hold no hardcoded CJK text."""
import ast
import re
from pathlib import Path

import pytest

from labeling_tool.core.i18n import LANGUAGES, TRANSLATIONS

ROOT = Path(__file__).resolve().parent.parent
# Hangul Jamo (ㄱ-ㅣ), Hangul syllables (가-힣, the full range) and CJK ideographs.
CJK = re.compile(r"[ㄱ-ㅣ가-힣一-鿿]")
PLACEHOLDER = re.compile(r"\{(\w+)[^}]*\}")

# UI modules that must already be free of hardcoded CJK string literals.
# Tasks 3-6 append to this list as each screen is migrated; the list is the
# regression guard that keeps them migrated.
UI_MODULES = [
    "labeling_tool/core/window/ui_builder.py",
    "labeling_tool/core/window/main_window.py",
    "labeling_tool/ui/login_dialog.py",
    "labeling_tool/ui/main_window.py",
    "labeling_tool/ui/fetch_dialog.py",
    "labeling_tool/ui/sam2_weights_dialog.py",
    "labeling_tool/update/ui.py",
    "labeling_tool/app.py",
    "annotation_tool/ui/main_window.py",
    "annotation_tool/ui/canvas.py",
]


def _cjk_literals(path: Path) -> list[str]:
    """Scan a Python file's AST for CJK string literals.

    Every plain string, byte-string-decoded-as-str, and f-string literal
    part is an `ast.Constant` node with a `str` value (f-string literal
    segments are `Constant` nodes inside `JoinedStr`, on every Python
    version -- unlike `tokenize`, which splits f-strings into
    FSTRING_START/MIDDLE/END tokens on 3.12+ and so misses their text).

    Returns offenders as ["<filename>:<line>: <first 40 chars>", ...].
    """
    offenders = []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if CJK.search(node.value):
                offenders.append(
                    f"{path.name}:{node.lineno}: {node.value[:40]}")

    return offenders


def test_all_languages_share_the_same_keys():
    keys = {code: set(TRANSLATIONS[code]) for code in LANGUAGES}
    base = keys["en"]
    for code in LANGUAGES:
        assert keys[code] == base, (
            f"{code} differs: missing={sorted(base - keys[code])[:5]} "
            f"extra={sorted(keys[code] - base)[:5]}")


def test_no_empty_strings():
    for code in LANGUAGES:
        empty = [k for k, v in TRANSLATIONS[code].items() if not str(v).strip()]
        assert not empty, f"{code} has empty strings: {empty[:5]}"


def test_placeholders_match_across_languages():
    for key, text in TRANSLATIONS["en"].items():
        expected = set(PLACEHOLDER.findall(text))
        for code in LANGUAGES:
            got = set(PLACEHOLDER.findall(TRANSLATIONS[code][key]))
            assert got == expected, f"{key} in {code}: {got} != {expected}"


@pytest.mark.parametrize("rel", UI_MODULES)
def test_ui_module_has_no_hardcoded_cjk(rel):
    """UI text belongs in strings_*.py, never inline in a widget module."""
    offenders = _cjk_literals(ROOT / rel)
    assert not offenders, "hardcoded UI text:\n" + "\n".join(offenders)


def test_ui_module_guard_catches_multiline_cjk(tmp_path):
    """Guard must detect CJK inside multi-line strings (regression test)."""
    # Create a test module with a multi-line Korean string on separate lines
    test_module = tmp_path / "test_widget.py"
    test_module.write_text(
        '''"""A test widget."""
msg = """
오류가 발생했습니다
"""
''',
        encoding="utf-8"
    )

    offenders = _cjk_literals(test_module)
    assert offenders, "Guard should catch CJK in multi-line strings"
    assert "오류" in str(offenders)


def test_ui_module_guard_catches_cjk_in_fstring(tmp_path):
    """Guard must detect CJK inside an f-string literal part (regression
    test: on Python 3.12+, f-strings tokenize as FSTRING_START/MIDDLE/END,
    not tokenize.STRING, so a tokenize-based scan misses this entirely)."""
    test_module = tmp_path / "test_fstring_widget.py"
    test_module.write_text(
        'n = 3\n'
        'msg = f"업로드 완료: {n}건"\n',
        encoding="utf-8",
    )

    offenders = _cjk_literals(test_module)
    assert offenders, "Guard should catch CJK inside an f-string"
    assert "업로드" in str(offenders)
