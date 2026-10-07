"""The login dialog's first page: ID / PW plus the server (BASE URL / Key);
only a signed-in user reaches the jobs page, and the sign-in lasts until
log-out even when app.py reopens the dialog."""
import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool import auth
from labeling_tool.ui import login_dialog as ld

_app = QApplication.instance() or QApplication([])

SAVED_IDS = []


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    SAVED_IDS.clear()
    monkeypatch.setattr(ld, "load_config", lambda: {"userId": "admin", "base": "https://a", "apiKey": "k"})
    monkeypatch.setattr(ld, "save_config", lambda base, key: None)
    monkeypatch.setattr(ld, "save_user_id", SAVED_IDS.append)
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path)
    created = []
    orig = ld.LoginDialog.__init__

    def _track(self, *a, **k):
        orig(self, *a, **k)
        created.append(self)

    monkeypatch.setattr(ld.LoginDialog, "__init__", _track)
    yield
    for d in created:
        d.close()


def test_starts_on_sign_in_with_the_remembered_id_and_no_password():
    dlg = ld.LoginDialog()
    assert dlg.pages.currentIndex() == ld.PAGE_SIGN_IN
    assert dlg.ed_user.text() == "admin" and dlg.ed_password.text() == ""
    page = dlg.pages.widget(ld.PAGE_SIGN_IN)
    for w in (dlg.ed_user, dlg.ed_password, dlg.ed_base, dlg.ed_key, dlg.btn_sign_in):
        assert page.isAncestorOf(w)
    assert dlg.user is None


def test_the_dev_account_reaches_the_jobs_page_and_is_remembered():
    dlg = ld.LoginDialog()
    dlg.ed_password.setText("admin")
    dlg.btn_sign_in.click()
    assert dlg.user == auth.User("admin")
    assert dlg.pages.currentIndex() == ld.PAGE_WORK
    assert SAVED_IDS == ["admin"]
    assert "admin" in dlg.lbl_user.text()


def test_a_wrong_password_stays_on_sign_in_with_an_inline_error():
    dlg = ld.LoginDialog()
    dlg.ed_password.setText("nope")
    dlg.btn_sign_in.click()
    assert dlg.user is None
    assert dlg.pages.currentIndex() == ld.PAGE_SIGN_IN
    assert dlg.lbl_sign_in_error.text()
    assert SAVED_IDS == []


def test_enter_in_the_password_field_signs_in():
    dlg = ld.LoginDialog()
    dlg.ed_password.setText("admin")
    dlg.ed_password.returnPressed.emit()
    assert dlg.pages.currentIndex() == ld.PAGE_WORK


def test_an_empty_server_does_not_block_sign_in():
    """Local jobs open offline; the server is only needed to fetch or upload."""
    dlg = ld.LoginDialog()
    dlg.ed_base.setText("")
    dlg.ed_key.setText("")
    dlg.ed_password.setText("admin")
    dlg.btn_sign_in.click()
    assert dlg.pages.currentIndex() == ld.PAGE_WORK


def test_a_signed_in_user_reopens_on_the_jobs_page():
    """app.py reopens the dialog after a cancelled fetch or a failed few-shot
    load; that must not ask for the password again."""
    dlg = ld.LoginDialog(user=auth.User("admin"))
    assert dlg.pages.currentIndex() == ld.PAGE_WORK
    assert dlg.user == auth.User("admin")


def test_log_out_returns_to_sign_in_and_forgets_the_password():
    dlg = ld.LoginDialog()
    dlg.ed_password.setText("admin")
    dlg.btn_sign_in.click()
    dlg.btn_log_out.click()
    assert dlg.user is None
    assert dlg.pages.currentIndex() == ld.PAGE_SIGN_IN
    assert dlg.ed_password.text() == ""


def test_the_authenticator_is_replaceable():
    class Server:
        def login(self, uid, pw):
            if (uid, pw) == ("kim", "pw1"):
                return auth.User("kim")
            raise auth.AuthError("no")

    dlg = ld.LoginDialog(authenticator=Server())
    dlg.ed_user.setText("kim")
    dlg.ed_password.setText("pw1")
    dlg.btn_sign_in.click()
    assert dlg.user == auth.User("kim")


def test_the_sign_in_page_follows_the_language(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    dlg = ld.LoginDialog()
    i18n.set_language("en")
    en = dlg.btn_sign_in.text()
    i18n.set_language("ko")
    assert dlg.btn_sign_in.text() != en
    assert dlg.btn_sign_in.text() == i18n.tr("signin_button")


def test_the_password_has_focus_when_the_id_is_remembered():
    dlg = ld.LoginDialog()
    dlg.show()
    QApplication.processEvents()
    assert dlg.focusWidget() is dlg.ed_password
