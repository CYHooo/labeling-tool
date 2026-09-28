"""Layer split and runtime identity. The runtime id must change when any
runtime-layer file changes, and must not change when only app-layer files do
-- that is what lets an update ship 30 MB instead of 1.5 GB."""

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
    assert layers.is_app_layer("LM_LabelingTool.exe")
    assert layers.is_app_layer("_internal/labeling_tool/models/sam/mobile.onnx")
    assert layers.is_app_layer("_internal/annotation_tool/configs.py")


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


def test_runtime_id_is_stable_for_identical_trees(tmp_path):
    files = {"_internal/torch/a.dll": b"aaa", "LM_LabelingTool.exe": b"app-v1"}
    one = _make_dist(tmp_path / "one", files)
    two = _make_dist(tmp_path / "two", files)
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_ignores_app_layer_changes(tmp_path):
    base = {"_internal/torch/a.dll": b"aaa"}
    one = _make_dist(tmp_path / "one", {**base, "LM_LabelingTool.exe": b"app-v1"})
    two = _make_dist(tmp_path / "two", {**base, "LM_LabelingTool.exe": b"app-v2"})
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_changes(tmp_path):
    app = {"LM_LabelingTool.exe": b"app-v1"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"aaa"})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/a.dll": b"bbb"})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_added(tmp_path):
    app = {"LM_LabelingTool.exe": b"app-v1", "_internal/torch/a.dll": b"aaa"}
    one = _make_dist(tmp_path / "one", app)
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/b.dll": b"ccc"})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_renamed(tmp_path):
    """Content alone is not the identity: the path is hashed too, so a
    rename that keeps every byte still moves the id."""
    app = {"LM_LabelingTool.exe": b"app-v1"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"aaa"})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/b.dll": b"aaa"})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_format(tmp_path):
    import re
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"aaa"})
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
