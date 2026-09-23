"""build-info.json written by CI next to the exe."""
import json

from labeling_tool.update.version import BUILD_INFO_NAME, DEV_VERSION, read_build_info


def test_reads_ci_build_info(tmp_path):
    (tmp_path / BUILD_INFO_NAME).write_text(
        json.dumps({"version": "1.2.3", "variant": "full", "commit": "abcdef1"}))
    info = read_build_info(tmp_path)
    assert (info.version, info.variant, info.commit) == ("1.2.3", "full", "abcdef1")


def test_missing_file_is_a_dev_build(tmp_path):
    info = read_build_info(tmp_path)
    assert info.version == DEV_VERSION and info.variant is None


def test_broken_file_is_a_dev_build(tmp_path):
    (tmp_path / BUILD_INFO_NAME).write_text("{not json")
    assert read_build_info(tmp_path).version == DEV_VERSION


def test_unknown_variant_is_rejected(tmp_path):
    (tmp_path / BUILD_INFO_NAME).write_text(json.dumps({"version": "1.0.0", "variant": "beta"}))
    assert read_build_info(tmp_path).variant is None


def test_defaults_to_app_home(monkeypatch, tmp_path):
    import labeling_tool.update.version as v
    (tmp_path / BUILD_INFO_NAME).write_text(json.dumps({"version": "9.9.9", "variant": "lite"}))
    monkeypatch.setattr(v, "app_home", lambda: tmp_path)
    assert read_build_info().version == "9.9.9"
