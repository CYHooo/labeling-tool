"""Every language covers every key, and UI modules hold no hardcoded CJK text."""
import ast
import re
import tokenize
from io import StringIO
from pathlib import Path

import pytest

from labeling_tool.core.i18n import LANGUAGES, TRANSLATIONS

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[ㄱ-힝一-鿿]")
PLACEHOLDER = re.compile(r"\{(\w+)[^}]*\}")

# UI modules that must already be free of hardcoded CJK string literals.
# Tasks 3-6 append to this list as each screen is migrated; the list is the
# regression guard that keeps them migrated.
UI_MODULES = [
    "labeling_tool/core/window/ui_builder.py",
    "labeling_tool/ui/login_dialog.py",
    "labeling_tool/ui/fetch_dialog.py",
    "labeling_tool/ui/sam2_weights_dialog.py",
    "labeling_tool/update/ui.py",
    "labeling_tool/app.py",
]


def _cjk_literals(path: Path) -> list[str]:
    """Scan a Python file for CJK string literals using tokenize.

    Returns offenders as ["<filename>:<line>: <first 40 chars>", ...].
    Catches all string tokens including multi-line strings.
    """
    offenders = []
    source = path.read_text(encoding="utf-8")
    tokens = tokenize.generate_tokens(StringIO(source).readline)

    try:
        for tok_type, tok_string, start, end, _ in tokens:
            if tok_type == tokenize.STRING:
                lineno = start[0]

                # Try to extract the actual string content
                try:
                    # Remove prefix (r, f, u, b, etc.)
                    clean_string = tok_string
                    while clean_string and clean_string[0] in "rfubRFUB":
                        clean_string = clean_string[1:]
                    # Use ast.literal_eval to safely extract the string value
                    value = ast.literal_eval(clean_string)
                except (ValueError, SyntaxError):
                    # If literal_eval fails, search the raw token text
                    value = tok_string

                # Check for CJK in the extracted/raw string
                if CJK.search(value):
                    offenders.append(f"{path.name}:{lineno}: {str(value)[:40]}")
    except tokenize.TokenError:
        # Incomplete input is OK; we still got what we could
        pass

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
