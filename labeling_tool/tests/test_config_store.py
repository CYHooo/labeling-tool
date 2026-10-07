"""config.json holds the server settings and the last signed-in ID; saving
one must never drop the other. The password is never stored."""
import json

from labeling_tool.ui import dialog_helpers as dh


def test_saving_the_server_keeps_the_remembered_id(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "CONFIG_PATH", tmp_path / "config.json")
    dh.save_user_id("admin")
    dh.save_config("https://a", "k")
    assert dh.load_config() == {"userId": "admin", "base": "https://a", "apiKey": "k"}


def test_saving_the_id_keeps_the_server(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "CONFIG_PATH", tmp_path / "sub" / "config.json")
    dh.save_config("https://a", "k")
    dh.save_user_id("admin")
    data = json.loads((tmp_path / "sub" / "config.json").read_text(encoding="utf-8"))
    assert data == {"base": "https://a", "apiKey": "k", "userId": "admin"}
    assert "password" not in json.dumps(data).lower()
