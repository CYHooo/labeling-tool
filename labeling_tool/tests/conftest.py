"""Make any Qt-touching test run headless."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""


@pytest.fixture(autouse=True)
def _reset_i18n_current_language():
    """Reset the cached current-language singleton around every test.

    labeling_tool.core.i18n keeps `_current` as a module global (set once
    lazily from the persisted setting, then cached). Tests that call
    i18n.set_language(...) without restoring it would otherwise leak that
    language into whichever test runs next -- including tests elsewhere in
    this file that assert on hardcoded default-language (ko) literals.
    Clearing it before *and* after each test makes every test start from
    the real persisted default, same as a freshly started process.
    """
    from labeling_tool.core import i18n
    i18n._current = None
    yield
    i18n._current = None
