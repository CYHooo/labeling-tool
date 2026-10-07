"""Sign-in: one Authenticator interface; the development one accepts only
admin / admin until a server account system replaces it."""
import pytest

from labeling_tool import auth


def test_dev_account_signs_in():
    user = auth.DevAuthenticator().login("admin", "admin")
    assert user == auth.User("admin")


@pytest.mark.parametrize("uid,pw", [("admin", "wrong"), ("someone", "admin"), ("", ""), ("admin", "")])
def test_anything_else_is_refused(uid, pw):
    with pytest.raises(auth.AuthError):
        auth.DevAuthenticator().login(uid, pw)


def test_surrounding_spaces_in_the_id_are_ignored_but_not_in_the_password():
    assert auth.DevAuthenticator().login("  admin ", "admin").user_id == "admin"
    with pytest.raises(auth.AuthError):
        auth.DevAuthenticator().login("admin", " admin")


def test_the_app_uses_the_dev_authenticator_for_now():
    assert isinstance(auth.default_authenticator(), auth.DevAuthenticator)
