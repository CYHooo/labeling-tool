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


def test_is_release_build_rejects_dev_build():
    """dev-<sha> builds should not be treated as release builds."""
    from labeling_tool.update.version import BuildInfo
    assert BuildInfo("dev-abc1234", "lite", None).is_release_build is False


def test_is_release_build_accepts_numeric_version():
    """Valid numeric versions with known variants are release builds."""
    from labeling_tool.update.version import BuildInfo
    assert BuildInfo("1.0.0", "lite", None).is_release_build is True
    assert BuildInfo("1.2.3", "full", None).is_release_build is True


def test_is_release_build_rejects_non_numeric_version():
    """Non-numeric version strings should not be release builds."""
    from labeling_tool.update.version import BuildInfo
    assert BuildInfo("v1.0.0-alpha", "lite", None).is_release_build is False
    assert BuildInfo("1.0.0-dev", "lite", None).is_release_build is False


def test_is_release_build_rejects_unknown_variant():
    """Unknown variants should not be release builds even with valid version."""
    from labeling_tool.update.version import BuildInfo
    assert BuildInfo("1.0.0", "beta", None).is_release_build is False
    assert BuildInfo("1.0.0", None, None).is_release_build is False
