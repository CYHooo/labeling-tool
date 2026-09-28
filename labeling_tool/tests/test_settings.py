"""UI settings live next to the exe and never break the app."""
import json

from labeling_tool.core import settings


def test_defaults_to_korean(tmp_path):
    assert settings.get_language(tmp_path) == "ko"


def test_round_trip(tmp_path):
    settings.set_language_setting("zh", tmp_path)
    assert settings.get_language(tmp_path) == "zh"
    assert json.loads((tmp_path / settings.SETTINGS_NAME).read_text())["lang"] == "zh"


def test_unknown_language_falls_back(tmp_path):
    (tmp_path / settings.SETTINGS_NAME).write_text(json.dumps({"lang": "fr"}))
    assert settings.get_language(tmp_path) == "ko"


def test_broken_file_is_ignored(tmp_path):
    (tmp_path / settings.SETTINGS_NAME).write_text("{broken")
    assert settings.get_language(tmp_path) == "ko"


def test_unwritable_home_does_not_raise(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir(mode=0o500)
    settings.set_language_setting("en", ro)   # must not raise


def test_other_keys_survive(tmp_path):
    settings.save_settings({"lang": "en", "other": 1}, tmp_path)
    settings.set_language_setting("zh", tmp_path)
    assert settings.load_settings(tmp_path)["other"] == 1
