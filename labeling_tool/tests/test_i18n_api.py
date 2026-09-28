"""Translation lookup, fallback and the language-change signal."""
import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool.core import i18n
from labeling_tool.core.i18n import strings_en, strings_ko, strings_zh

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")


def test_language_order_and_names():
    assert i18n.LANGUAGES == ("ko", "zh", "en")
    assert i18n.LANG_DISPLAY_NAMES["ko"] == "한국어"


def test_tr_uses_current_language():
    i18n.set_language("zh")
    assert i18n.tr("language") == strings_zh.STRINGS["language"]
    i18n.set_language("en")
    assert i18n.tr("language") == strings_en.STRINGS["language"]


def test_tr_formats_placeholders():
    # every language must accept the same kwargs
    for code in i18n.LANGUAGES:
        i18n.set_language(code)
        assert "42" in i18n.tr("fetch_progress", done=42, total=99)


def test_missing_key_falls_back_to_english(monkeypatch):
    monkeypatch.setitem(strings_ko.STRINGS, "only_en", None)
    strings_ko.STRINGS.pop("only_en")
    monkeypatch.setitem(strings_en.STRINGS, "only_en", "English only")
    i18n.set_language("ko")
    assert i18n.tr("only_en") == "English only"


def test_unknown_key_returns_the_key():
    assert i18n.tr("no_such_key_at_all") == "no_such_key_at_all"


def test_set_language_persists_and_emits():
    seen = []
    i18n.language_manager().languageChanged.connect(seen.append)
    i18n.set_language("en")
    assert seen == ["en"]
    assert i18n.current_language() == "en"


def test_set_language_ignores_unknown_code():
    i18n.set_language("ko")
    i18n.set_language("fr")
    assert i18n.current_language() == "ko"
