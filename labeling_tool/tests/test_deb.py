"""The deb control files: where the layer split becomes dpkg's problem."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import deb  # noqa: E402
import layers  # noqa: E402


def _fields(control: str) -> dict:
    out = {}
    for line in control.splitlines():
        if line and not line.startswith(" ") and ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _make_dist(tmp_path: Path) -> Path:
    """A minimal PyInstaller onedir layout: one app-layer file (the entry
    point) and one runtime-layer file (anything else), which is all
    layers.compute_runtime_id and layers.stage_app_layer need."""
    dist = tmp_path / "dist"
    (dist / layers.app_entry_name(layers.LINUX)).parent.mkdir(parents=True, exist_ok=True)
    (dist / layers.app_entry_name(layers.LINUX)).write_bytes(b"#!/bin/sh\n")
    runtime_file = dist / "_internal" / "torch" / "libtorch.so"
    runtime_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_file.write_bytes(b"not a real shared object")
    return dist


def _extract_control(deb_path: Path, into: Path) -> str:
    subprocess.run(["dpkg-deb", "-e", str(deb_path), str(into)], check=True)
    return (into / "control").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dpkg_deb_available() -> bool:
    return shutil.which("dpkg-deb") is not None


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


# ------------------------------------------------------ build() / app_only
# CI's runtime-reuse path (packaging/reuse_runtime.py) downloads and
# re-verifies the previous release's runtime deb instead of rebuilding it,
# so build() must be able to produce just the app deb. These are the public,
# unit-tested entry point the CI workflow calls -- see
# .github/workflows/release.yml's "Build debs" step, which must never reach
# into this module's private staging helpers directly.

def test_build_produces_both_debs_by_default(tmp_path, dpkg_deb_available):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    paths = deb.build(dist, out, "1.4.1")
    assert set(paths) == {"runtime", "app"}
    assert paths["runtime"].is_file()
    assert paths["app"].is_file()
    produced = {p.name for p in out.glob("*.deb")}
    assert produced == {paths["runtime"].name, paths["app"].name}


def test_build_app_only_produces_only_the_app_deb(tmp_path, dpkg_deb_available):
    # The whole point of app_only: no runtime deb is built (or published) at
    # all when the previous release's is being reused instead.
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    paths = deb.build(dist, out, "1.4.1", app_only=True)
    assert set(paths) == {"app"}
    assert paths["app"].is_file()
    produced = list(out.glob("*.deb"))
    assert produced == [paths["app"]]
    assert not any(p.name.startswith("lm-labeling-tool-runtime_") for p in produced)


def test_app_only_control_matches_a_full_build(tmp_path, dpkg_deb_available):
    # app_only must not be a different code path that happens to produce a
    # similar-looking package: its app deb's control has to be byte-for-byte
    # what a full build would have produced for the same dist_dir/version.
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    full = deb.build(dist, tmp_path / "out-full", "1.4.1")
    app_only = deb.build(dist, tmp_path / "out-app-only", "1.4.1", app_only=True)
    full_control = _extract_control(full["app"], tmp_path / "extract-full")
    app_only_control = _extract_control(app_only["app"], tmp_path / "extract-app-only")
    assert full_control == app_only_control
    # And the filename -- which carries the runtime id -- agrees too.
    assert full["app"].name == app_only["app"].name


def test_cli_accepts_the_app_only_flag(tmp_path, dpkg_deb_available, capsys):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    assert deb.main(["build", "--app-only", str(dist), str(out), "1.4.1"]) == 0
    produced = list(out.glob("*.deb"))
    assert len(produced) == 1
    assert produced[0].name.startswith("lm-labeling-tool_")
    printed = capsys.readouterr().out
    assert "app:" in printed
    assert "runtime:" not in printed


def test_cli_rejects_unknown_arguments():
    assert deb.main(["build", "--bogus-flag", "a", "b", "c"]) == 2
    assert deb.main(["nonsense"]) == 2


# -------------------------------------------- runtime_id override (CI guard)
# CI's dependency-guard smoke test needs an app deb that FALSELY claims a
# runtime id the installed runtime does not have, to prove dpkg -i refuses
# it -- see the "Dependency guard" step in .github/workflows/release.yml.

def test_runtime_id_override_builds_an_app_deb_for_a_different_runtime(
        tmp_path, dpkg_deb_available):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    paths = deb.build(dist, out, "1.4.1", app_only=True, runtime_id="rdeadbeef")
    assert set(paths) == {"app"}
    assert paths["app"].name == "lm-labeling-tool_1.4.1-rdeadbeef_amd64.deb"
    control = _extract_control(paths["app"], tmp_path / "extract")
    assert "lm-labeling-tool-runtime (= 0~rdeadbeef)" in control


def test_runtime_id_override_requires_app_only():
    # A runtime deb built under a declared id that does not match its own
    # staged payload would be a real, publishable bug, not a test fixture.
    with pytest.raises(ValueError):
        deb.build("dist", "out", "1.4.1", app_only=False, runtime_id="rdeadbeef")


def test_cli_accepts_the_runtime_id_flag(tmp_path, dpkg_deb_available):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    assert deb.main(["build", "--app-only", "--runtime-id", "rdeadbeef",
                      str(dist), str(out), "1.4.1"]) == 0
    produced = list(out.glob("*.deb"))
    assert produced == [out / "lm-labeling-tool_1.4.1-rdeadbeef_amd64.deb"]


def test_cli_surfaces_the_app_only_requirement_as_a_clean_error():
    assert deb.main(["build", "--runtime-id", "rdeadbeef", "dist", "out", "1.4.1"]) == 2
