"""app.py's few-shot flow: the model loads with the login dialog still
open, and failures come back as text rather than a modal box."""

from PyQt5.QtWidgets import QApplication

from labeling_tool import app as app_module

_app = QApplication.instance() or QApplication([])


def test_load_fewshot_window_returns_error_text_on_failure(monkeypatch):
    def _boom():
        raise RuntimeError("no CUDA")

    monkeypatch.setattr(app_module, "_build_fewshot_main_window", _boom)
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: True)
    win, err = app_module.load_fewshot_window()
    assert win is None
    assert "RuntimeError" in err
    assert "no CUDA" in err


def test_load_fewshot_window_returns_none_none_when_weights_cancelled(monkeypatch):
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: False)
    win, err = app_module.load_fewshot_window()
    assert win is None
    assert err is None


def test_load_fewshot_window_returns_window_on_success(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: True)
    monkeypatch.setattr(app_module, "_build_fewshot_main_window", lambda: sentinel)
    win, err = app_module.load_fewshot_window()
    assert win is sentinel
    assert err is None
