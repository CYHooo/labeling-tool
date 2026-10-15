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
    calls = _LogStarts()
    calls.real = app_module._start_app_logging
    monkeypatch.setattr(app_module, "_start_app_logging", lambda: calls.append(True))
    return calls


class _LogStarts(list):
    """Recorded _start_app_logging calls; .real is the unstubbed function."""
    real = None


@pytest.fixture(autouse=True)
def _class_cache_in_tmp(tmp_path, monkeypatch):
    """The class cache lives under user_data_home(), which is the repo root
    in a source checkout: keep every test's cache in its own tmp dir."""
    from labeling_tool.core import classes
    monkeypatch.setattr(classes, "cache_dir", lambda: tmp_path / "label-classes")


@pytest.fixture(autouse=True)
def _ui_settings_in_tmp(tmp_path, monkeypatch):
    """ui-settings.json (language, image-list column width / collapsed)
    lives under user_data_home(), the repo root in a source checkout: a
    window built by a test must never read or write the developer's file.
    Tests that need a particular home patch _settings_home again."""
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "ui-settings-home")


@pytest.fixture(autouse=True)
def close_prompts(monkeypatch):
    """Closing a labeling window with photos not uploaded asks the user, and
    a modal dialog would hang an offscreen run. Every test answers "close"
    (and the upload-running notice records instead of showing); a test that
    checks the prompt patches the methods again. The list records each ask
    as ("ask", count) or ("busy", None); .real is the unstubbed prompt."""
    from labeling_tool.ui.main_window import ViewerMainWindow
    asked = _LogStarts()
    asked.real = ViewerMainWindow._ask_close_unuploaded

    def ask(_self, count):
        asked.append(("ask", count))
        return "close"

    monkeypatch.setattr(ViewerMainWindow, "_ask_close_unuploaded", ask)
    monkeypatch.setattr(ViewerMainWindow, "_tell_upload_running",
                        lambda _self: asked.append(("busy", None)))
    yield asked
    # A test that left a (fake) upload "running" had its close refused; a
    # window still visible afterwards would make later tests think a
    # labeling session is open (update/ui._session_in_progress).
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    for w in (app.topLevelWidgets() if app is not None else ()):
        if isinstance(w, ViewerMainWindow) and w.isVisible():
            w._upload_worker = None
            w._close_after_upload = False
            w.close()
