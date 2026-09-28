"""app.py's few-shot flow: the model loads with the login dialog still
open, and failures come back as text rather than a modal box."""

import pytest
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


def test_load_fewshot_window_returns_window_on_success(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(app_module, "_build_fewshot_main_window", lambda: sentinel)
    win, err = app_module.load_fewshot_window()
    assert win is sentinel
    assert err is None


# --------------------------------------------------- the orchestration seam
# open_fewshot_from_login() is what the login dialog's signal actually runs:
# weights check -> loading state -> load -> accept or report. Its ordering is
# where a modal can end up stacked on top of the loading notice.

class _FakeDialog:
    """Records the order of calls main()'s flow makes on the login dialog."""
    def __init__(self):
        self.calls = []
        self.mode = None
        self.accepted = False

    def enter_loading_state(self, message, detail=""):
        self.calls.append(("enter", message, detail))

    def exit_loading_state(self, error=None):
        self.calls.append(("exit", error))

    def accept(self):
        self.accepted = True
        self.calls.append(("accept",))


def test_weights_prompt_runs_before_the_loading_state(monkeypatch):
    """The weights download asks with a modal. It must ask BEFORE the loading
    area claims the model is being loaded, or the modal stacks on top of a
    notice that is describing the wrong thing for the whole download."""
    order = []

    def _weights():
        order.append("weights")
        return True

    monkeypatch.setattr(app_module, "_ensure_weights", _weights)
    monkeypatch.setattr(app_module, "_build_fewshot_main_window", lambda: object())
    dlg = _FakeDialog()

    def _enter(message, detail=""):
        order.append("enter")

    dlg.enter_loading_state = _enter
    app_module.open_fewshot_from_login(dlg)
    assert order == ["weights", "enter"]


def test_declined_weights_never_enters_the_loading_state(monkeypatch):
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: False)
    monkeypatch.setattr(
        app_module, "_build_fewshot_main_window",
        lambda: pytest.fail("window built after the download was declined"))
    dlg = _FakeDialog()
    assert app_module.open_fewshot_from_login(dlg) is None
    assert dlg.calls == []          # nothing was ever shown
    assert not dlg.accepted


def test_failure_reports_inline_and_leaves_dialog_open(monkeypatch):
    def _boom():
        raise RuntimeError("no CUDA")

    monkeypatch.setattr(app_module, "_ensure_weights", lambda: True)
    monkeypatch.setattr(app_module, "_build_fewshot_main_window", _boom)
    dlg = _FakeDialog()
    assert app_module.open_fewshot_from_login(dlg) is None
    assert not dlg.accepted
    kinds = [c[0] for c in dlg.calls]
    assert kinds == ["enter", "exit"]
    assert "no CUDA" in dlg.calls[-1][1]


def test_success_accepts_the_dialog_and_returns_the_window(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: True)
    monkeypatch.setattr(app_module, "_build_fewshot_main_window", lambda: sentinel)
    dlg = _FakeDialog()
    assert app_module.open_fewshot_from_login(dlg) is sentinel
    assert dlg.accepted
    assert dlg.mode == "fewshot"
