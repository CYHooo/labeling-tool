"""Layer split and runtime identity. The runtime id must change when any
runtime-layer file changes, and must not change when only app-layer files do
-- that is what lets an update ship 30 MB instead of 1.5 GB."""

import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import layers  # noqa: E402


def _make_dist(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return tmp_path


def test_app_layer_covers_exe_and_own_packages():
    # Explicit WINDOWS: this test locks the Windows entry-name rule and must
    # hold the same on any host, not just when run on a Windows machine.
    assert layers.is_app_layer("LM_LabelingTool.exe", layers.WINDOWS)
    assert layers.is_app_layer("_internal/labeling_tool/core/settings.pyc")
    assert layers.is_app_layer("_internal/annotation_tool/configs.py")
    # models/ is deliberately NOT here any more -- see
    # test_onnx_models_are_runtime_layer


def test_build_info_is_app_layer_so_a_version_bump_keeps_the_runtime_id():
    """build-info.json carries the version, so if it counted as runtime the
    id would change on every release and layering would never engage."""
    assert layers.is_app_layer("build-info.json")


def test_runtime_layer_is_everything_else():
    assert not layers.is_app_layer("_internal/torch/lib/torch_cpu.dll")
    assert not layers.is_app_layer("_internal/nvidia/cudnn/bin/cudnn64_9.dll")
    assert not layers.is_app_layer("_internal/PyQt5/Qt5/bin/Qt5Core.dll")
    assert not layers.is_app_layer("_internal/base_library.zip")


def test_a_new_third_party_dependency_lands_in_the_runtime_layer():
    """The whitelist runs the right way round: anything we did not name is
    runtime, so a new dependency forces a full reinstall rather than
    silently riding along in a partial app package."""
    assert not layers.is_app_layer("_internal/scipy/linalg/_flapack.pyd")


def test_a_path_that_merely_starts_like_an_app_path_is_not_app_layer():
    """Prefix matching must respect directory boundaries: a sibling named
    labeling_tool_vendor is not ours."""
    assert not layers.is_app_layer("_internal/labeling_tool_vendor/x.dll")


def test_windows_backslashes_are_understood():
    assert layers.is_app_layer("_internal\\labeling_tool\\core\\i18n\\__init__.pyc")


def test_onnx_models_are_runtime_layer():
    """42.4 MB of fixed pretrained weights -- over half of every app update
    before this. A frozen build ships them at _internal/models/, beside the
    package rather than inside it, so they fall outside the app-layer
    prefixes naturally AND survive the installer clearing labeling_tool/."""
    assert not layers.is_app_layer("_internal/models/sam/mobile_sam_encoder.onnx")
    assert not layers.is_app_layer("_internal/models/sam/mobile_sam_decoder.onnx")


def test_our_code_under_the_same_package_is_still_app_layer():
    """The exclusion is narrow: only models/, not the package around it."""
    assert layers.is_app_layer("_internal/labeling_tool/app.pyc")
    assert layers.is_app_layer("_internal/labeling_tool/core/i18n/__init__.pyc")
    assert layers.is_app_layer("_internal/labeling_tool/ui/login_dialog.pyc")


def test_our_own_modules_are_never_mistaken_for_bundled_data():
    """A module named models_helper is code, not a model directory."""
    assert layers.is_app_layer("_internal/labeling_tool/models_helper.pyc")


def test_changing_a_model_moves_the_runtime_id(tmp_path):
    """Replacing MobileSAM is a full reinstall, consistent with the rule
    that swapping a big file means everyone re-downloads."""
    base = {"LM_LabelingTool.exe": b"app", "_internal/torch/a.dll": b"x" * 10}
    one = _make_dist(tmp_path / "one", {**base, "_internal/models/sam/m.onnx": b"m" * 100})
    two = _make_dist(tmp_path / "two", {**base, "_internal/models/sam/m.onnx": b"m" * 200})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_is_stable_for_the_same_tree(tmp_path):
    """Two PyInstaller runs of the same commit write different BYTES --
    timestamps go into the files -- so contents cannot be hashed (proved on
    CI runs 36421966949 / 36424404832). Paths and sizes are stable, and they
    are what this measures."""
    files = {"_internal/torch/a.dll": b"x" * 100, "LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", files)
    two = _make_dist(tmp_path / "two", files)
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_ignores_app_layer_changes(tmp_path):
    """The whole point: changing our own code must not force a reinstall."""
    base = {"_internal/torch/a.dll": b"x" * 100}
    one = _make_dist(tmp_path / "one", {**base, "_internal/labeling_tool/app.pyc": b"v1"})
    two = _make_dist(tmp_path / "two", {**base, "_internal/labeling_tool/app.pyc": b"v2-longer"})
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_changes_size(tmp_path):
    app = {"LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"x" * 100})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/a.dll": b"x" * 101})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_added(tmp_path):
    app = {"LM_LabelingTool.exe": b"app", "_internal/torch/a.dll": b"x" * 100}
    one = _make_dist(tmp_path / "one", app)
    two = _make_dist(tmp_path / "two", {**app, "_internal/nvidia/b.dll": b"y" * 50})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_removed(tmp_path):
    app = {"LM_LabelingTool.exe": b"app", "_internal/torch/a.dll": b"x" * 100}
    one = _make_dist(tmp_path / "one", {**app, "_internal/nvidia/nccl/n.dll": b"z" * 70})
    two = _make_dist(tmp_path / "two", app)
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_renamed(tmp_path):
    """Path is hashed too: a rename that keeps every byte still moves it."""
    app = {"LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"x" * 100})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/b.dll": b"x" * 100})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_does_not_see_content_changes_at_equal_size(tmp_path):
    """A DELIBERATE trade-off, not a defect: hashing contents was tried and
    abandoned because PyInstaller's output is not reproducible. A dependency
    that changes content without changing any file's size or path -- a
    republished wheel under the same version -- will not move the id.
    Do not "fix" this by hashing contents; that breaks the mechanism."""
    app = {"LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"aaaa"})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/a.dll": b"bbbb"})
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_rejects_a_missing_dist(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        layers.compute_runtime_id(tmp_path / "nope")


def test_runtime_id_rejects_an_empty_runtime_layer(tmp_path):
    """No runtime files means the caller pointed at the wrong directory;
    hashing nothing would produce a confident-looking wrong id."""
    import pytest
    d = _make_dist(tmp_path / "d", {"LM_LabelingTool.exe": b"app"})
    with pytest.raises(ValueError):
        layers.compute_runtime_id(d, layers.WINDOWS)


def test_runtime_id_format(tmp_path):
    import re
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"x" * 10})
    assert re.fullmatch(r"r[0-9a-f]{8}", layers.compute_runtime_id(d))


# ------------------------------------------------------- build-info.json
# A machine upgrading from v1.2.0 has a build-info.json with no `runtime`
# key. That must read as "cannot do a layered update", not as a crash and
# not as a dev build.

import json  # noqa: E402

from labeling_tool.update import version as ver  # noqa: E402


def test_runtime_is_read_from_build_info(tmp_path):
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.3.0", "runtime": "r3f8a1c92",
         "variant": "full", "commit": "abc1234"}), encoding="utf-8")
    info = ver.read_build_info(tmp_path)
    assert info.runtime == "r3f8a1c92"
    assert info.is_release_build


def test_missing_runtime_reads_as_none_but_stays_a_release_build(tmp_path):
    """v1.2.0's build-info.json has no `runtime`. The install is still a
    real release -- it just cannot take a layered update, which the checker
    handles by falling back to the full installer."""
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.2.0", "variant": "full", "commit": "abc1234"}),
        encoding="utf-8")
    info = ver.read_build_info(tmp_path)
    assert info.runtime is None
    assert info.is_release_build


def test_non_string_runtime_reads_as_none(tmp_path):
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.3.0", "runtime": 42, "variant": "full"}), encoding="utf-8")
    assert ver.read_build_info(tmp_path).runtime is None


def test_empty_runtime_reads_as_none(tmp_path):
    (tmp_path / "build-info.json").write_text(json.dumps(
        {"version": "1.3.0", "runtime": "", "variant": "full"}), encoding="utf-8")
    assert ver.read_build_info(tmp_path).runtime is None


# ------------------------------------------------------------------- CLI
# CI calls these; PowerShell has no heredoc, so the logic lives in the
# module rather than inline in the workflow YAML.

def test_stage_app_layer_copies_only_the_app_layer(tmp_path):
    dist = _make_dist(tmp_path / "dist", {
        "LM_LabelingTool.exe": b"x" * 10,
        "build-info.json": b"{}",
        "_internal/labeling_tool/core.pyc": b"y" * 20,
        "_internal/torch/big.dll": b"z" * 100,
    })
    out = tmp_path / "app"
    app_bytes, all_bytes = layers.stage_app_layer(dist, out, layers.WINDOWS)
    copied = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert copied == ["LM_LabelingTool.exe", "_internal/labeling_tool/core.pyc",
                      "build-info.json"]
    assert app_bytes == 32
    assert all_bytes == 132


def test_cli_runtime_id(tmp_path, capsys):
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"x" * 10})
    assert layers.main(["runtime-id", str(d)]) == 0
    assert capsys.readouterr().out.strip() == layers.compute_runtime_id(d)


def test_cli_runtime_id_reports_a_bad_path(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        layers.main(["runtime-id", str(tmp_path / "missing")])


def test_cli_stage(tmp_path, capsys, monkeypatch):
    # The CLI has no platform flag by design (CI always builds the runner's
    # own platform); pin it to WINDOWS here so this fixture, which hardcodes
    # the .exe entry name, is not at the mercy of the host running the tests.
    monkeypatch.setattr(layers, "current_platform", lambda: layers.WINDOWS)
    d = _make_dist(tmp_path / "d", {"LM_LabelingTool.exe": b"x",
                                    "_internal/torch/a.dll": b"aaa"})
    assert layers.main(["stage", str(d), str(tmp_path / "out")]) == 0
    assert "app layer:" in capsys.readouterr().out
    assert (tmp_path / "out" / "LM_LabelingTool.exe").exists()
    assert not (tmp_path / "out" / "_internal" / "torch").exists()


def test_cli_rejects_bad_usage(capsys):
    assert layers.main(["nonsense"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_build_machine_system_dlls_are_recognised():
    for rel in ("_internal/api-ms-win-core-file-l1-1-0.dll",
                "_internal/ucrtbase.dll",
                "_internal/VCRUNTIME140_1.dll",
                "_internal\\msvcp140.dll",
                "_internal/concrt140.dll"):
        assert layers.is_build_machine_file(rel, layers.WINDOWS), rel


def test_a_wheels_own_copy_of_a_system_dll_is_not_a_build_machine_file():
    # PyQt5 ships its own MSVCP140.dll inside its wheel: a PyQt5 upgrade
    # that changes it must still move the id.
    assert not layers.is_build_machine_file("_internal/PyQt5/Qt5/bin/MSVCP140.dll")
    assert not layers.is_build_machine_file("_internal/python312.dll")
    assert not layers.is_build_machine_file("_internal/ucrtbase_notes.txt")
    assert not layers.is_build_machine_file("api-ms-win-core-file-l1-1-0.dll")


def test_runtime_id_ignores_the_build_machines_system_dlls(tmp_path):
    # Runner images 20260922.246.2 and 20260925.250.1 built the same commit
    # with different UCRT/VC++ DLLs and so different ids.
    a = _make_dist(tmp_path / "a", {"_internal/torch/a.dll": b"x" * 10,
                                    "_internal/ucrtbase.dll": b"u" * 100,
                                    "_internal/api-ms-win-crt-math-l1-1-0.dll": b"m"})
    b = _make_dist(tmp_path / "b", {"_internal/torch/a.dll": b"x" * 10,
                                    "_internal/ucrtbase.dll": b"u" * 120})
    assert layers.compute_runtime_id(a, layers.WINDOWS) == layers.compute_runtime_id(b, layers.WINDOWS)


def test_build_machine_dlls_still_ship_in_the_runtime_layer(tmp_path):
    # Left out of the id, not out of the install: the full package needs them.
    assert not layers.is_app_layer("_internal/ucrtbase.dll")
    d = _make_dist(tmp_path / "d", {"_internal/ucrtbase.dll": b"u",
                                    "_internal/torch/a.dll": b"x"})
    assert [rel for rel, _ in layers.iter_runtime_files(d)] == [
        "_internal/torch/a.dll", "_internal/ucrtbase.dll"]


def test_manifest_lists_runtime_files_with_sizes_sorted(tmp_path):
    d = _make_dist(tmp_path / "d", {
        "LM_LabelingTool.exe": b"x",
        "_internal/torch/b.dll": b"bb",
        "_internal/abc.pyc": b"aaa",
        "_internal/labeling_tool/core.pyc": b"y",
    })
    assert layers.runtime_manifest(d, layers.WINDOWS) == [("_internal/abc.pyc", 3),
                                          ("_internal/torch/b.dll", 2)]


def test_manifest_is_what_the_runtime_id_hashes(tmp_path):
    # Diffing two manifests is only a valid diagnosis of a moved id if the
    # manifest carries everything the id depends on.
    a = _make_dist(tmp_path / "a", {"_internal/torch/a.dll": b"x" * 10})
    b = _make_dist(tmp_path / "b", {"_internal/torch/a.dll": b"y" * 10})
    assert layers.runtime_manifest(a) == layers.runtime_manifest(b)
    assert layers.compute_runtime_id(a) == layers.compute_runtime_id(b)


def test_cli_manifest(tmp_path, capsys, monkeypatch):
    # See test_cli_stage: pin the host platform so this .exe fixture behaves
    # the same regardless of which OS runs the test suite.
    monkeypatch.setattr(layers, "current_platform", lambda: layers.WINDOWS)
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"x" * 10,
                                    "LM_LabelingTool.exe": b"x"})
    assert layers.main(["manifest", str(d)]) == 0
    assert capsys.readouterr().out == "10\t_internal/torch/a.dll\n"


def test_cli_manifest_reports_a_bad_path(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        layers.main(["manifest", str(tmp_path / "missing")])


def test_app_entry_name_is_platform_specific():
    assert layers.app_entry_name(layers.WINDOWS) == "LM_LabelingTool.exe"
    assert layers.app_entry_name(layers.LINUX) == "LM_LabelingTool"


def test_linux_entry_is_app_layer_and_windows_entry_is_not():
    # The Linux build has no .exe; classifying the other platform's entry
    # as app layer would silently ship it in the wrong package.
    assert layers.is_app_layer("LM_LabelingTool", layers.LINUX) is True
    assert layers.is_app_layer("LM_LabelingTool.exe", layers.LINUX) is False
    assert layers.is_app_layer("LM_LabelingTool.exe", layers.WINDOWS) is True
    assert layers.is_app_layer("LM_LabelingTool", layers.WINDOWS) is False


def test_shared_app_layer_prefixes_hold_on_both_platforms():
    for platform in (layers.WINDOWS, layers.LINUX):
        assert layers.is_app_layer("build-info.json", platform) is True
        assert layers.is_app_layer("_internal/labeling_tool/app.py", platform) is True
        assert layers.is_app_layer("_internal/annotation_tool/x.py", platform) is True
        assert layers.is_app_layer("_internal/torch/lib/c10.so", platform) is False
        assert layers.is_app_layer("_internal/models/sam/mobile_sam.onnx", platform) is False


def test_build_machine_files_are_a_windows_only_concept():
    # The exclusion exists because PyInstaller copies UCRT/VC++ DLLs from the
    # build machine's Windows. Nothing analogous is taken from the Linux host.
    assert layers.is_build_machine_file("_internal/vcruntime140.dll", layers.WINDOWS) is True
    assert layers.is_build_machine_file("_internal/vcruntime140.dll", layers.LINUX) is False
    assert layers.is_build_machine_file("_internal/libstdc++.so.6", layers.LINUX) is False


def test_runtime_id_differs_between_platforms_for_the_same_tree(tmp_path):
    # Same relative paths, different entry-name rule: the Windows run counts
    # LM_LabelingTool as a runtime file, the Linux run does not.
    (tmp_path / "_internal").mkdir()
    (tmp_path / "LM_LabelingTool").write_bytes(b"x" * 10)
    (tmp_path / "_internal" / "libtorch.so").write_bytes(b"y" * 20)
    win = layers.compute_runtime_id(tmp_path, layers.WINDOWS)
    linux = layers.compute_runtime_id(tmp_path, layers.LINUX)
    assert win != linux
