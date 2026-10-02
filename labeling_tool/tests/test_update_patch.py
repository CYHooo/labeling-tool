"""The app-layer zip: verify, swap with a journal, roll back, recover."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from labeling_tool.update import patch


def _install(root: Path, runtime="r11111111", version="0.2.0"):
    (root / "_internal" / "labeling_tool").mkdir(parents=True)
    (root / "_internal" / "torch").mkdir(parents=True)
    (root / "LM_LabelingTool.exe").write_bytes(b"old exe")
    (root / "_internal" / "labeling_tool" / "a.pyc").write_bytes(b"old a")
    (root / "_internal" / "labeling_tool" / "gone.pyc").write_bytes(b"old gone")
    (root / "_internal" / "torch" / "lib.dll").write_bytes(b"runtime")
    (root / "build-info.json").write_text(json.dumps(
        {"version": version, "variant": "full", "runtime": runtime, "commit": "x"}))
    return root


def _zip(path: Path, files: dict[str, bytes], runtime="r11111111", platform="win32",
         version="0.2.1", manifest_files=None):
    listing = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
    manifest = {"version": version, "runtime": runtime, "platform": platform,
                "files": manifest_files if manifest_files is not None else listing}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(patch.MANIFEST_NAME, json.dumps(manifest))
        for rel, data in files.items():
            z.writestr(rel, data)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


NEW = {
    "LM_LabelingTool.exe": b"new exe",
    "_internal/labeling_tool/a.pyc": b"new a",
    "_internal/labeling_tool/b.pyc": b"new b",
    "build-info.json": json.dumps({"version": "0.2.1", "variant": "full",
                                   "runtime": "r11111111", "commit": "y"}).encode(),
}


def test_apply_replaces_adds_and_removes_app_layer_files(tmp_path):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    m = patch.apply_patch(z, root, sha, platform="win32")
    assert m.version == "0.2.1"
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"new exe"
    assert (root / "_internal/labeling_tool/b.pyc").read_bytes() == b"new b"
    assert not (root / "_internal/labeling_tool/gone.pyc").exists()
    assert (root / "_internal/torch/lib.dll").read_bytes() == b"runtime"  # runtime untouched
    assert not (root / patch.JOURNAL).exists() and not (root / patch.STAGING).exists()


def test_a_wrong_checksum_changes_nothing(tmp_path):
    root = _install(tmp_path / "app")
    z, _ = _zip(tmp_path / "u.zip", NEW)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, "0" * 64, platform="win32")
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"


@pytest.mark.parametrize("runtime,platform", [("r22222222", "win32"), ("r11111111", "linux")])
def test_a_zip_for_another_runtime_or_platform_is_refused(tmp_path, runtime, platform):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW, runtime=runtime, platform=platform)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"


@pytest.mark.parametrize("bad", ["../evil.pyc", "/abs.pyc", "_internal/torch/lib.dll"])
def test_a_path_escaping_the_install_dir_is_refused(tmp_path, bad):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", {**NEW, bad: b"x"})
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert not (tmp_path / "evil.pyc").exists()
    assert (root / "_internal/torch/lib.dll").read_bytes() == b"runtime"


def test_a_file_that_does_not_match_the_manifest_is_refused(tmp_path):
    root = _install(tmp_path / "app")
    listing = {rel: hashlib.sha256(d).hexdigest() for rel, d in NEW.items()}
    listing["_internal/labeling_tool/a.pyc"] = "f" * 64
    z, sha = _zip(tmp_path / "u.zip", NEW, manifest_files=listing)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"


def test_a_failing_move_rolls_back_everything(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    real = patch._move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 4:   # fail part-way through the swap
            raise PermissionError("locked by another instance")
        real(src, dst)
    monkeypatch.setattr(patch, "_move", flaky)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"
    assert (root / "_internal/labeling_tool/gone.pyc").read_bytes() == b"old gone"
    assert not (root / "_internal/labeling_tool/b.pyc").exists()
    assert not (root / patch.JOURNAL).exists()


def test_recover_rolls_back_an_interrupted_apply(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    real = patch._move
    calls = {"n": 0}

    def crash(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise SystemExit("power cut")   # not caught by apply_patch's rollback
        real(src, dst)
    monkeypatch.setattr(patch, "_move", crash)
    with pytest.raises(SystemExit):
        patch.apply_patch(z, root, sha, platform="win32")
    monkeypatch.setattr(patch, "_move", real)
    assert (root / patch.JOURNAL).exists()
    assert patch.recover(root) is True
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"
    assert not (root / patch.JOURNAL).exists()
    assert patch.recover(root) is False


def test_cleanup_removes_the_backup_only_after_success(tmp_path):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    patch.apply_patch(z, root, sha, platform="win32")
    assert (root / patch.BACKUP).exists()
    patch.cleanup(root)
    assert not (root / patch.BACKUP).exists()
