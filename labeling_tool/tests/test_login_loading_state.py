"""The login dialog's inline loading state, used while the few-shot model
loads. Replaces the old free-floating QLabel splash in app.py."""

import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool.ui import login_dialog as ld

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_real_config(monkeypatch, tmp_path):
    monkeypatch.setattr(ld, "load_config", lambda: {"apiKey": "saved-key"})
    monkeypatch.setattr(ld, "save_config", lambda base, key: None)
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path)


@pytest.fixture
def dlg(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: True)
    d = ld.LoginDialog()
    yield d
    d.close()


def test_loading_box_hidden_initially(dlg):
    assert not dlg._loading_box.isVisibleTo(dlg)


def test_enter_loading_state_shows_box_and_texts(dlg):
    dlg.enter_loading_state("로딩 중…", "가중치를 올리는 중")
    assert dlg._loading_box.isVisibleTo(dlg)
    assert dlg._lbl_loading.text() == "로딩 중…"
    assert dlg._lbl_loading_detail.text() == "가중치를 올리는 중"


def test_no_progress_bar_is_shown(dlg):
    """The load blocks the UI thread, so an animated bar would freeze
    mid-sweep and read as a hung program. Show no bar rather than promise
    motion the event loop cannot deliver."""
    from PyQt5.QtWidgets import QProgressBar
    dlg.enter_loading_state("로딩 중…")
    assert dlg._loading_box.findChild(QProgressBar) is None


def test_enter_loading_state_disables_interaction(dlg):
    dlg.enter_loading_state("로딩 중…")
    assert not dlg.tabs.isEnabled()
    assert not dlg.cmb_language.isEnabled()
    assert not dlg.btn_check_update.isEnabled()


def test_exit_loading_state_restores_interaction(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state()
    assert dlg.tabs.isEnabled()
    assert dlg.cmb_language.isEnabled()
    assert dlg.btn_check_update.isEnabled()
    assert not dlg._loading_box.isVisibleTo(dlg)


def test_exit_loading_state_with_error_keeps_box_and_hides_bar(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state("열 수 없습니다: RuntimeError: boom")
    assert dlg._loading_box.isVisibleTo(dlg)
    assert "RuntimeError: boom" in dlg._lbl_loading.text()
    assert not dlg._lbl_loading_detail.isVisibleTo(dlg)
    assert dlg.tabs.isEnabled()


def test_fewshot_button_emits_signal_instead_of_accepting(dlg):
    seen = []
    dlg.fewshotRequested.connect(lambda: seen.append(True))
    dlg.btn_fewshot.click()
    assert seen == [True]
    assert dlg.result() == 0  # not accepted yet


def test_close_is_ignored_while_loading(dlg):
    dlg.show()
    dlg.enter_loading_state("로딩 중…")
    dlg.close()
    assert dlg.isVisible()          # the close was ignored
    dlg.exit_loading_state()
    dlg.close()
    assert not dlg.isVisible()      # and honoured once loading ended


def test_retry_after_failure_replaces_error_text(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state("첫 번째 실패")
    assert "첫 번째 실패" in dlg._lbl_loading.text()
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state("두 번째 실패")
    assert dlg._lbl_loading.text() == "두 번째 실패"
    assert "첫 번째 실패" not in dlg._lbl_loading.text()


def test_cancelled_weights_download_leaves_no_error(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state(None)
    assert not dlg._loading_box.isVisibleTo(dlg)
    assert dlg.tabs.isEnabled()


def test_log_out_is_locked_while_the_model_loads():
    """Log-out moved to the bottom row, outside the disabled tabs; a click
    queued during the load would flip the page under the accept."""
    from labeling_tool import auth
    dlg = ld.LoginDialog(user=auth.User("admin"))
    try:
        dlg.enter_loading_state("loading")
        assert not dlg.btn_log_out.isEnabled()
        dlg.exit_loading_state()
        assert dlg.btn_log_out.isEnabled()
    finally:
        dlg._loading = False
        dlg.close()
