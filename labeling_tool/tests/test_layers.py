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


def _make_repo(tmp_path, manifests):
    """A fake repo root holding just the files the runtime id hashes."""
    for rel, content in manifests.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return tmp_path


SPEC = b'coll = COLLECT(exe, a.binaries, name="LM_LabelingTool")\n'
FREEZE = "PyQt5==5.15.11\nnumpy==1.26.4\ntorch==2.5.1+cu124\n"


def _make_repo(tmp_path, spec=SPEC):
    """A fake repo root holding the files the runtime id reads."""
    p = tmp_path / "packaging" / "labeling_tool.spec"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(spec)
    return tmp_path


def test_runtime_id_is_stable_for_the_same_environment(tmp_path):
    """The built files are NOT hashed: two PyInstaller runs of the same
    commit produce different bytes (verified on CI runs 36421966949 and
    36424404832), which would move the id on every release and make the
    app package match nothing."""
    one, two = _make_repo(tmp_path / "one"), _make_repo(tmp_path / "two")
    assert layers.compute_runtime_id(one, FREEZE) == layers.compute_runtime_id(two, FREEZE)


def test_runtime_id_changes_when_a_resolved_version_changes(tmp_path):
    """requirements.txt says PyQt5>=5.15, so pip can resolve a different
    version with no file changing. PyQt5's .py code rides in the exe (app
    layer) while its .pyd files are runtime layer -- shipping an app
    package across that split is a half-upgraded PyQt5 that cannot import."""
    repo = _make_repo(tmp_path / "repo")
    a = layers.compute_runtime_id(repo, FREEZE)
    b = layers.compute_runtime_id(repo, FREEZE.replace("5.15.11", "5.15.13"))
    assert a != b


def test_runtime_id_changes_when_the_pyinstaller_spec_changes(tmp_path):
    """The spec decides what enters the runtime layer (collect_all, excludes).
    Adding a dependency there without moving the id would ship an exe whose
    PYZ imports a package the installed runtime layer does not have."""
    one = _make_repo(tmp_path / "one")
    two = _make_repo(tmp_path / "two",
                     spec=SPEC + b'for pkg in ("scipy",): collect_all(pkg)\n')
    assert layers.compute_runtime_id(one, FREEZE) != layers.compute_runtime_id(two, FREEZE)


def test_runtime_id_ignores_freeze_ordering_and_blank_lines(tmp_path):
    """pip freeze ordering is not guaranteed stable across runs."""
    repo = _make_repo(tmp_path / "repo")
    shuffled = "\n\ntorch==2.5.1+cu124\nPyQt5==5.15.11\n\nnumpy==1.26.4\n"
    assert layers.compute_runtime_id(repo, FREEZE) == layers.compute_runtime_id(repo, shuffled)


def test_runtime_id_ignores_the_build_output(tmp_path):
    """Whatever PyInstaller emitted does not enter the identity."""
    repo = _make_repo(tmp_path / "repo")
    before = layers.compute_runtime_id(repo, FREEZE)
    _make_dist(repo / "dist" / "LM_LabelingTool", {"_internal/torch/a.dll": b"whatever"})
    assert layers.compute_runtime_id(repo, FREEZE) == before


def test_runtime_id_rejects_an_empty_freeze(tmp_path):
    """An empty freeze means the caller did not actually capture the
    environment; hashing it would produce a confident-looking wrong id."""
    import pytest
    repo = _make_repo(tmp_path / "repo")
    with pytest.raises(ValueError):
        layers.compute_runtime_id(repo, "   \n\n")


def test_runtime_id_rejects_a_missing_spec(tmp_path):
    import pytest
    (tmp_path / "bare").mkdir()
    with pytest.raises(FileNotFoundError):
        layers.compute_runtime_id(tmp_path / "bare", FREEZE)


def test_runtime_id_format(tmp_path):
    import re
    repo = _make_repo(tmp_path / "repo")
    assert re.fullmatch(r"r[0-9a-f]{8}", layers.compute_runtime_id(repo, FREEZE))


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
    app_bytes, all_bytes = layers.stage_app_layer(dist, out)
    copied = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert copied == ["LM_LabelingTool.exe", "_internal/labeling_tool/core.pyc",
                      "build-info.json"]
    assert app_bytes == 32
    assert all_bytes == 132


def test_cli_runtime_id(tmp_path, capsys):
    repo = _make_repo(tmp_path / "repo")
    freeze = tmp_path / "freeze.txt"
    freeze.write_text(FREEZE, encoding="utf-8")
    assert layers.main(["runtime-id", str(repo), str(freeze)]) == 0
    assert capsys.readouterr().out.strip() == layers.compute_runtime_id(repo, FREEZE)


def test_cli_runtime_id_on_this_repo(tmp_path, capsys):
    """The real spec file exists where the CLI expects it -- a rename fails
    here rather than on the runner."""
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    freeze = tmp_path / "freeze.txt"
    freeze.write_text(FREEZE, encoding="utf-8")
    assert layers.main(["runtime-id", str(root), str(freeze)]) == 0
    assert re.fullmatch(r"r[0-9a-f]{8}", capsys.readouterr().out.strip())


def test_cli_stage(tmp_path, capsys):
    d = _make_dist(tmp_path / "d", {"LM_LabelingTool.exe": b"x",
                                    "_internal/torch/a.dll": b"aaa"})
    assert layers.main(["stage", str(d), str(tmp_path / "out")]) == 0
    assert "app layer:" in capsys.readouterr().out
    assert (tmp_path / "out" / "LM_LabelingTool.exe").exists()
    assert not (tmp_path / "out" / "_internal" / "torch").exists()


def test_cli_rejects_bad_usage(capsys):
    assert layers.main(["nonsense"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_runtime_id_ignores_line_endings(tmp_path):
    """git may check the spec out with CRLF on Windows and LF elsewhere.
    Hashing raw bytes made the same commit produce different ids on
    different platforms, which is the silent-drift failure this whole
    mechanism exists to avoid."""
    lf = _make_repo(tmp_path / "lf", spec=b"a = 1\nb = 2\n")
    crlf = _make_repo(tmp_path / "crlf", spec=b"a = 1\r\nb = 2\r\n")
    assert layers.compute_runtime_id(lf, FREEZE) == layers.compute_runtime_id(crlf, FREEZE)


def test_runtime_id_ignores_freeze_line_endings(tmp_path):
    repo = _make_repo(tmp_path / "repo")
    assert (layers.compute_runtime_id(repo, "PyQt5==5.15.11\r\nnumpy==1.26.4\r\n")
            == layers.compute_runtime_id(repo, "PyQt5==5.15.11\nnumpy==1.26.4\n"))
