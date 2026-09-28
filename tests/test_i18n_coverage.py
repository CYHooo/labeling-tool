"""Every language covers every key, and UI modules hold no hardcoded CJK text."""
import re
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
]


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
    offenders = []
    for lineno, line in enumerate(( ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        for literal in re.findall(r'"([^"]*)"|\'([^\']*)\'', code):
            text = literal[0] or literal[1]
            if CJK.search(text):
                offenders.append(f"{rel}:{lineno}: {text[:40]}")
    assert not offenders, "hardcoded UI text:\n" + "\n".join(offenders)
