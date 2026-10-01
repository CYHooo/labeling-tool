"""Where the app writes: beside the exe on Windows, XDG on Linux."""
from pathlib import Path

import pytest

from labeling_tool.core import app_paths


@pytest.fixture
def frozen(monkeypatch):
    """Pretend to be a PyInstaller build rooted at a given directory."""
    def _apply(platform, exe_dir):
        monkeypatch.setattr(app_paths.sys, "frozen", True, raising=False)
        monkeypatch.setattr(app_paths.sys, "executable", str(Path(exe_dir) / "LM_LabelingTool"))
        monkeypatch.setattr(app_paths.sys, "platform", platform)
    return _apply


def test_source_run_is_the_repo_root_on_every_platform(monkeypatch):
    monkeypatch.delattr(app_paths.sys, "frozen", raising=False)
    assert app_paths.user_data_home() == app_paths.REPO_ROOT


def test_windows_frozen_still_writes_beside_the_executable(frozen, tmp_path):
    # The Windows install is per-user and portable; moving its data would
    # strand every copy already installed. This must never change.
    frozen("win32", tmp_path)
    assert app_paths.user_data_home() == tmp_path
    assert app_paths.writable_path(Path("/ignored"), "config.json") == tmp_path / "config.json"


def test_linux_frozen_uses_xdg_data_home(frozen, tmp_path, monkeypatch):
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert app_paths.user_data_home() == tmp_path / "xdg" / "lm-labeling-tool"


def test_linux_frozen_falls_back_to_dot_local_share(frozen, tmp_path, monkeypatch):
    frozen("linux", tmp_path / "opt")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert app_paths.user_data_home() == tmp_path / "home" / ".local/share/lm-labeling-tool"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_xdg_data_home_is_treated_as_unset(frozen, tmp_path, monkeypatch, value):
    # An empty XDG_DATA_HOME is common in stripped login environments. Joining
    # onto it would resolve relative to the current working directory.
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_DATA_HOME", value)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert app_paths.user_data_home() == tmp_path / "home" / ".local/share/lm-labeling-tool"


def test_relative_xdg_data_home_is_rejected(frozen, tmp_path, monkeypatch):
    # The XDG spec requires an absolute path; a relative one would scatter user
    # data into whatever directory the app happened to be launched from.
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_DATA_HOME", "relative/data")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert app_paths.user_data_home() == tmp_path / "home" / ".local/share/lm-labeling-tool"


def test_missing_home_does_not_raise(frozen, tmp_path, monkeypatch):
    # Service accounts and some sudo invocations have no HOME, and on some of
    # those Path.home() itself raises (it does not always fall back to the
    # passwd database). Raising here would happen during startup and the app
    # would never open a window.
    frozen("linux", tmp_path / "opt")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))

    def _raise_no_home():
        raise RuntimeError("could not determine home directory")

    monkeypatch.setattr(app_paths.Path, "home", staticmethod(_raise_no_home))
    result = app_paths.user_data_home()
    assert result.is_absolute()
    assert result.name == "lm-labeling-tool"
    assert result == tmp_path / "tmp" / ".local/share/lm-labeling-tool"


def test_cache_home_is_separate_from_data_home(frozen, tmp_path, monkeypatch):
    # Downloads are throwaway; keeping them out of the data directory stops a
    # 1.5 GB deb riding along in the user's backups.
    frozen("linux", tmp_path / "opt")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert app_paths.user_cache_home() == tmp_path / "cache" / "lm-labeling-tool"


def test_windows_cache_home_is_not_the_install_directory(frozen, tmp_path, monkeypatch):
    # Regression: user_cache_home() once returned app_home() on Windows too,
    # which put a 1.5 GB in-progress update download inside the install
    # directory. installer.iss's [InstallDelete] never clears it (it only
    # knows about _internal/ and the two app-package subdirectories), so
    # every full update would permanently grow the install by 1.5 GB and an
    # uninstall would not remove it either. The download must land in the
    # system temp directory instead, which the OS already reclaims on its
    # own.
    frozen("win32", tmp_path)
    cache_home = app_paths.user_cache_home()
    assert cache_home != app_paths.app_home()
    assert cache_home == Path(app_paths.tempfile.gettempdir())
