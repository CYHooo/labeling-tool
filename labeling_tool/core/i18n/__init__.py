"""UI translations: lookup, current language, and a change signal.

Strings live in strings_<code>.py, one STRINGS dict each; docs/i18n-glossary.md
is the authority for terminology. tr() itself needs no Qt, so non-GUI modules
can use it; language_manager() is the QObject widgets connect to in order to
retranslate themselves when the language changes.
"""

from __future__ import annotations

from labeling_tool.core.i18n import strings_en, strings_ko, strings_zh

LANGUAGES = ("ko", "zh", "en")
LANG_DISPLAY_NAMES = {"ko": "한국어", "zh": "中文", "en": "English"}
FALLBACK_LANG = "en"

TRANSLATIONS = {
    "ko": strings_ko.STRINGS,
    "zh": strings_zh.STRINGS,
    "en": strings_en.STRINGS,
}

_current: str | None = None
_manager: "LanguageManager | None" = None


def language_manager() -> "LanguageManager":
    # PyQt5 is imported lazily, here, so plain tr() lookups (used by non-GUI
    # code and by tests that only exercise translation lookup) stay Qt-free,
    # as this module's own docstring and spec section 1 both claim.
    global _manager
    if _manager is None:
        from PyQt5.QtCore import QObject, pyqtSignal

        class LanguageManager(QObject):
            """Emits languageChanged(code) so open windows can retranslate."""
            languageChanged = pyqtSignal(str)

        _manager = LanguageManager()
    return _manager


def _settings_home():
    return None  # tests patch this to redirect ui-settings.json


def current_language() -> str:
    global _current
    if _current is None:
        from labeling_tool.core.settings import get_language
        _current = get_language(_settings_home())
    return _current


def set_language(code: str) -> None:
    """Switch language, persist it and notify open windows. Unknown code: ignored."""
    global _current
    if code not in LANGUAGES or code == current_language():
        return
    from labeling_tool.core.settings import set_language_setting
    _current = code
    set_language_setting(code, _settings_home())
    language_manager().languageChanged.emit(code)


def tr(key: str, **kwargs) -> str:
    """Current language, then English, then the key itself."""
    text = TRANSLATIONS.get(current_language(), {}).get(key)
    if text is None:
        text = TRANSLATIONS[FALLBACK_LANG].get(key, key)
    return text.format(**kwargs) if kwargs else text
