"""The single deb: control fields, maintainer scripts and the build."""
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


def test_one_package_named_like_the_client_expects():
    from labeling_tool.update import checker
    assert deb.deb_filename("0.2.0") == checker.full_asset_name("0.2.0", checker.LINUX)


def test_control_has_a_real_version_and_the_system_depends():
    f = _fields(deb.control("0.2.0", installed_kb=1))
    assert f["Package"] == "lm-labeling-tool"
    assert f["Version"] == "0.2.0"
    assert f["Architecture"] == "amd64"
    assert f["Installed-Size"] == "1"
    for lib in ("libgl1", "libxkbcommon-x11-0"):
        assert lib in f["Depends"]
    assert "lm-labeling-tool-runtime" not in f["Depends"]


def test_control_covers_both_glib_package_names():
    # Ubuntu 24.04 (noble) renamed libglib2.0-0 to libglib2.0-0t64 for its
    # 64-bit time_t transition; 22.04 (jammy) still has the old name. An
    # alternation satisfies dpkg on either release.
    f = _fields(deb.control("0.2.0", installed_kb=1))
    assert "libglib2.0-0t64 | libglib2.0-0" in f["Depends"]


def test_libraries_a_stock_desktop_lacks_are_bundled_not_declared():
    # `dpkg -i` does not fetch from repositories, so declaring a library a
    # stock desktop does not ship makes the install fail outright -- CI run
    # 36842846563: ubuntu-desktop-minimal on 22.04 has no libxcb-xinerama0.
    assert "libxcb-xinerama0" in deb.BUNDLED_LIBS
    f = _fields(deb.control("0.2.0", installed_kb=1))
    declared = {d.strip() for d in f["Depends"].split(",")}
    for lib in deb.BUNDLED_LIBS:
        assert lib not in declared, f"{lib} is bundled, it must not be a Depends"


def test_package_does_not_depend_on_an_nvidia_driver():
    # torch's cu124 wheel carries the CUDA runtime; requiring a driver
    # package would make the deb uninstallable on CPU-only machines.
    f = _fields(deb.control("0.2.0", installed_kb=1))
    assert "nvidia" not in f["Depends"].lower()
    assert "cuda" not in f["Depends"].lower()


def test_control_ends_with_a_newline():
    # dpkg-deb rejects a control file whose last field has no trailing LF.
    assert deb.control("1.0.0", 1).endswith("\n")


def test_a_release_build_compresses_with_xz_level_9(tmp_path, monkeypatch):
    # xz's default level (-6, 8 MB dictionary) left the v2.0.0 runtime deb at
    # 2,061,489,096 bytes -- over the release asset ceiling (CI run
    # 36965987450). -9 measured 8% smaller on the torch + CUDA payload.
    calls = []
    monkeypatch.setattr(deb.subprocess, "run", lambda args, **kw: calls.append(args))
    deb._dpkg_deb_build(tmp_path / "root", tmp_path / "out.deb", fast=False)
    assert "-Zxz" in calls[0] and "-z9" in calls[0]
    calls.clear()
    deb._dpkg_deb_build(tmp_path / "root", tmp_path / "out.deb", fast=True)
    assert "-Zgzip" in calls[0]


def test_desktop_entry_points_at_the_installed_executable():
    entry = deb.desktop_entry("1.4.1")
    assert "Exec=/opt/lm-labeling-tool/LM_LabelingTool" in entry
    assert "Icon=lm-labeling-tool" in entry
    assert entry.startswith("[Desktop Entry]")


def test_postrm_removes_files_dpkg_never_tracked():
    # zip updates write app-layer files outside dpkg's database
    assert "rm -rf /opt/lm-labeling-tool" in deb.POSTRM
    assert "remove|purge" in deb.POSTRM


def test_preinst_clears_the_app_layer_before_a_full_install():
    for d in ("_internal/labeling_tool", "_internal/annotation_tool",
              ".update-backup", ".update-staging"):
        assert f"/opt/lm-labeling-tool/{d}" in deb.PREINST


def test_build_produces_exactly_one_deb(tmp_path, dpkg_deb_available):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = deb.build(dist, tmp_path / "out", "0.2.0")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "lm-labeling-tool_0.2.0_amd64.deb"]
    control = _extract_control(out, tmp_path / "ctl")
    assert "Version: 0.2.0" in control


def test_every_maintainer_script_is_executable_in_the_built_deb(
        tmp_path, dpkg_deb_available):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = deb.build(dist, tmp_path / "out", "0.2.0")
    _extract_control(out, tmp_path / "ctl")
    for name in ("postinst", "preinst", "postrm"):
        script = tmp_path / "ctl" / name
        assert script.is_file(), name
        assert script.stat().st_mode & 0o111 == 0o111, name


def test_cli_builds_and_prints_the_path(tmp_path, dpkg_deb_available, capsys):
    if not dpkg_deb_available:
        pytest.skip("dpkg-deb not installed")
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    assert deb.main(["build", str(dist), str(out), "0.2.0"]) == 0
    assert capsys.readouterr().out.strip() == f"deb: {out / 'lm-labeling-tool_0.2.0_amd64.deb'}"


def test_cli_rejects_unknown_arguments():
    assert deb.main(["build", "--bogus-flag", "a", "b", "c"]) == 2
    assert deb.main(["build", "--app-only", "a", "b", "c"]) == 2
    assert deb.main(["nonsense"]) == 2
