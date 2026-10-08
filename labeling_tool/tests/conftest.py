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


@pytest.fixture(autouse=True)
def app_log_starts(monkeypatch):
    """app.main() would write <repo>/logs/app.log and install process-wide
    exception hooks (sys.excepthook / threading.excepthook / Qt's message
    handler) that outlive the test. Record the call instead; a test that
    needs to know whether logging started reads this list."""
    import labeling_tool.app as app_module
    calls = []
    monkeypatch.setattr(app_module, "_start_app_logging", lambda: calls.append(True))
    return calls
