"""UI settings live next to the exe and never break the app."""
import json

from labeling_tool.core import app_paths, settings


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


def test_default_home_on_linux_frozen_writes_under_xdg(monkeypatch, tmp_path):
    """No ``home`` passed: the default must resolve through user_data_home(),
    which on a Linux frozen build is the XDG data dir, not app_home()'s
    /opt/lm-labeling-tool (root-owned, read-only)."""
    monkeypatch.setattr(app_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_paths.sys, "executable",
                         str(tmp_path / "opt" / "lm-labeling-tool" / "LM_LabelingTool"))
    monkeypatch.setattr(app_paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    settings.set_language_setting("zh")  # no home= -- exercise the real default

    settings_path = tmp_path / "xdg" / "lm-labeling-tool" / settings.SETTINGS_NAME
    assert settings_path.exists()
    assert json.loads(settings_path.read_text())["lang"] == "zh"


# ---------------------------------------------------------------- image-list column
def test_list_column_defaults(tmp_path):
    assert settings.get_list_column_width(tmp_path) == settings.DEFAULT_LIST_WIDTH == 280
    assert settings.get_list_column_collapsed(tmp_path) is False


def test_list_column_round_trip_keeps_the_language(tmp_path):
    settings.set_language_setting("zh", tmp_path)
    settings.set_list_column_state(333, True, tmp_path)
    assert settings.get_list_column_width(tmp_path) == 333
    assert settings.get_list_column_collapsed(tmp_path) is True
    assert settings.get_language(tmp_path) == "zh"
    settings.set_list_column_state(300, False, tmp_path)
    assert settings.get_list_column_width(tmp_path) == 300
    assert settings.get_list_column_collapsed(tmp_path) is False


def test_list_column_bad_values_fall_back(tmp_path):
    for width, collapsed in (("wide", "yes"), (True, 1), (-5, None), (0, []),
                             (float("nan"), {}), (None, "true")):
        settings.save_settings({"list_width": width, "list_collapsed": collapsed}, tmp_path)
        assert settings.get_list_column_width(tmp_path) == 280, width
        assert settings.get_list_column_collapsed(tmp_path) is False, collapsed


def test_list_column_whole_float_width_is_read(tmp_path):
    settings.save_settings({"list_width": 310.0}, tmp_path)
    assert settings.get_list_column_width(tmp_path) == 310


def test_list_column_broken_file_gives_defaults(tmp_path):
    (tmp_path / settings.SETTINGS_NAME).write_text("{broken")
    assert settings.get_list_column_width(tmp_path) == 280
    assert settings.get_list_column_collapsed(tmp_path) is False


def test_list_column_unwritable_home_does_not_raise(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir(mode=0o500)
    settings.set_list_column_state(300, True, ro)   # must not raise
