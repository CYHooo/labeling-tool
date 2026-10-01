"""The deb control files: where the layer split becomes dpkg's problem."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import deb  # noqa: E402


def _fields(control: str) -> dict:
    out = {}
    for line in control.splitlines():
        if line and not line.startswith(" ") and ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_runtime_package_is_versioned_by_the_runtime_id():
    f = _fields(deb.runtime_control("r3f8a1c92", installed_kb=1_400_000))
    assert f["Package"] == "lm-labeling-tool-runtime"
    # 0~ sorts before every real version, so this can never be mistaken for
    # an application version number.
    assert f["Version"] == "0~r3f8a1c92"
    assert f["Architecture"] == "amd64"
    assert f["Installed-Size"] == "1400000"


def test_app_package_pins_the_exact_runtime():
    # This one line replaces the hand-written guard installer.iss needs.
    f = _fields(deb.app_control("1.4.1", "r3f8a1c92", installed_kb=20_000))
    assert f["Package"] == "lm-labeling-tool"
    assert f["Version"] == "1.4.1"
    assert f["Depends"] == "lm-labeling-tool-runtime (= 0~r3f8a1c92)"


def test_runtime_package_declares_the_qt_system_libraries():
    # Without these, the install succeeds and the app dies at startup with
    # "could not load the Qt platform plugin xcb".
    f = _fields(deb.runtime_control("r1", installed_kb=1))
    for lib in ("libgl1", "libglib2.0-0", "libxkbcommon-x11-0"):
        assert lib in f["Depends"], f"{lib} missing from runtime Depends"


def test_runtime_package_does_not_depend_on_an_nvidia_driver():
    # torch's cu124 wheel carries the CUDA runtime; requiring a driver
    # package would make the deb uninstallable on CPU-only machines.
    f = _fields(deb.runtime_control("r1", installed_kb=1))
    assert "nvidia" not in f["Depends"].lower()
    assert "cuda" not in f["Depends"].lower()


def test_filenames_split_the_runtime_id_from_the_version():
    # The app deb's NAME carries the id so a client can match it without
    # downloading. The runtime deb's does not: a client taking a full update
    # knows the version but not the new id.
    assert deb.app_deb_filename("1.4.1", "r3f8a1c92") == \
        "lm-labeling-tool_1.4.1-r3f8a1c92_amd64.deb"
    assert deb.runtime_deb_filename("1.4.1") == \
        "lm-labeling-tool-runtime_1.4.1_amd64.deb"


def test_runtime_package_covers_both_glib_package_names():
    # Ubuntu 24.04 (noble) renamed libglib2.0-0 to libglib2.0-0t64 for its
    # 64-bit time_t transition; 22.04 (jammy) still has the old name. An
    # alternation satisfies dpkg on either release -- a single name would
    # make the deb uninstallable on one of our two supported targets.
    f = _fields(deb.runtime_control("r1", installed_kb=1))
    assert "libglib2.0-0t64 | libglib2.0-0" in f["Depends"]


def test_filenames_match_what_the_client_looks_for():
    # Two modules spell these names; if they disagree, updates silently stop.
    from labeling_tool.update import checker
    assert deb.app_deb_filename("1.4.1", "r3f8a1c92") == \
        checker.app_asset_name("1.4.1", "r3f8a1c92", checker.LINUX)
    assert deb.runtime_deb_filename("1.4.1") == \
        checker.full_asset_names("1.4.1", checker.LINUX)[0]


def test_desktop_entry_points_at_the_installed_executable():
    entry = deb.desktop_entry("1.4.1")
    assert "Exec=/opt/lm-labeling-tool/LM_LabelingTool" in entry
    assert "Icon=lm-labeling-tool" in entry
    assert entry.startswith("[Desktop Entry]")


def test_control_ends_with_a_newline():
    # dpkg-deb rejects a control file whose last field has no trailing LF.
    assert deb.runtime_control("r1", 1).endswith("\n")
    assert deb.app_control("1.0.0", "r1", 1).endswith("\n")
