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


@pytest.mark.parametrize("bad", ["../evil.pyc", "/abs.pyc", "_internal/torch/lib.dll",
                                 "_internal/labeling_tool/..\\..\\..\\evil.exe",
                                 "_internal/labeling_tool/C:evil.pyc"])
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


def _interrupt_apply(root, z, sha, monkeypatch, at):
    real = patch._move
    calls = {"n": 0}

    def crash(src, dst):
        calls["n"] += 1
        if calls["n"] == at:
            raise SystemExit("power cut")
        real(src, dst)
    monkeypatch.setattr(patch, "_move", crash)
    with pytest.raises(SystemExit):
        patch.apply_patch(z, root, sha, platform="win32")
    monkeypatch.setattr(patch, "_move", real)
    return real


def _assert_old_files(root):
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"
    assert (root / "_internal/labeling_tool/a.pyc").read_bytes() == b"old a"
    assert (root / "_internal/labeling_tool/gone.pyc").read_bytes() == b"old gone"


def test_the_executable_bit_survives_the_swap_on_linux(tmp_path):
    root = _install(tmp_path / "app")
    (root / "LM_LabelingTool.exe").unlink()
    (root / "LM_LabelingTool").write_bytes(b"old")
    listing = {"LM_LabelingTool": hashlib.sha256(b"new").hexdigest()}
    z = tmp_path / "u.zip"
    manifest = {"version": "0.2.1", "runtime": "r11111111", "platform": "linux",
                "files": listing}
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(patch.MANIFEST_NAME, json.dumps(manifest))
        info = zipfile.ZipInfo("LM_LabelingTool")
        info.external_attr = 0o100755 << 16
        zf.writestr(info, b"new")
    sha = hashlib.sha256(z.read_bytes()).hexdigest()
    patch.apply_patch(z, root, sha, platform="linux")
    assert (root / "LM_LabelingTool").read_bytes() == b"new"
    assert (root / "LM_LabelingTool").stat().st_mode & 0o100


def test_an_interrupted_recover_can_be_rerun(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    real = _interrupt_apply(root, z, sha, monkeypatch, at=5)
    calls = {"n": 0}

    def crash(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise SystemExit("power cut during recover")
        real(src, dst)
    monkeypatch.setattr(patch, "_move", crash)
    with pytest.raises(SystemExit):
        patch.recover(root)
    monkeypatch.setattr(patch, "_move", real)
    assert patch.recover(root) is True
    _assert_old_files(root)
    assert not (root / patch.JOURNAL).exists()


def test_apply_first_recovers_a_leftover_journal(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    _interrupt_apply(root, z, sha, monkeypatch, at=3)
    assert (root / patch.JOURNAL).exists()
    seen = {}
    real_stage = patch._stage

    def spy(*args, **kwargs):
        seen["old_back"] = (root / "_internal/labeling_tool/a.pyc").exists() \
            or (root / "LM_LabelingTool.exe").read_bytes() == b"old exe"
        return real_stage(*args, **kwargs)
    monkeypatch.setattr(patch, "_stage", spy)
    patch.apply_patch(z, root, sha, platform="win32")
    assert seen["old_back"]
    assert (root / "LM_LabelingTool.exe").read_bytes() == b"new exe"
    assert not (root / "_internal/labeling_tool/gone.pyc").exists()
    assert not (root / patch.JOURNAL).exists()


def test_the_zip_is_read_from_a_private_copy_that_is_not_left_behind(tmp_path):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    patch.apply_patch(z, root, sha, platform="win32")
    assert not (root / patch.STAGING).exists()
    root2 = _install(tmp_path / "app2")
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root2, "0" * 64, platform="win32")
    assert not (root2 / patch.STAGING).exists()
    assert z.exists()


# ------------------------------------------------ F1: a crash-safe journal

def test_every_journal_write_is_a_synced_temp_file_replaced_into_place(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    events = []
    real_replace, real_fsync = patch.os.replace, patch.os.fsync

    def spy_replace(src, dst):
        events.append(("replace", Path(src), Path(dst)))
        real_replace(src, dst)

    def spy_fsync(fd):
        events.append(("fsync",))
        real_fsync(fd)
    monkeypatch.setattr(patch.os, "replace", spy_replace)
    monkeypatch.setattr(patch.os, "fsync", spy_fsync)
    patch.apply_patch(z, root, sha, platform="win32")
    journal_writes = [i for i, e in enumerate(events)
                      if e[0] == "replace" and e[2] == root / patch.JOURNAL]
    assert len(journal_writes) >= 2 * len(NEW) - 1
    for i in journal_writes:
        _, src, _ = events[i]
        assert src.parent == root and src != root / patch.JOURNAL
        assert events[i - 1] == ("fsync",)   # the temp file is on disk before the swap
    assert not [p for p in root.iterdir() if p.name.startswith(patch.JOURNAL)]


def test_a_crash_while_writing_the_journal_keeps_the_previous_journal(tmp_path, monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    real_replace = patch.os.replace
    writes = {"n": 0}

    def crash(src, dst):
        if Path(dst) == root / patch.JOURNAL:
            writes["n"] += 1
            if writes["n"] == 4:
                raise SystemExit("power cut while writing the journal")
        real_replace(src, dst)
    monkeypatch.setattr(patch.os, "replace", crash)
    with pytest.raises(SystemExit):
        patch.apply_patch(z, root, sha, platform="win32")
    monkeypatch.setattr(patch.os, "replace", real_replace)
    assert len(json.loads((root / patch.JOURNAL).read_text())) == 3
    assert patch.recover(root) is True
    _assert_old_files(root)


@pytest.mark.parametrize("garbage", [b"", b'[["backup", "C:\\\\x', b"\x00\xff junk",
                                     b'{"not": "a list"}', b'[["backup"]]'])
def test_an_unreadable_journal_restores_every_old_file_from_the_backup(tmp_path, monkeypatch,
                                                                       garbage):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    # Stop as the new exe is moved in: every other file was swapped, gone.pyc
    # and the old exe were moved out, so every old file lives only in the backup.
    _interrupt_apply(root, z, sha, monkeypatch, at=8)
    assert not (root / "_internal/labeling_tool/gone.pyc").exists()
    (root / patch.JOURNAL).write_bytes(garbage)
    assert patch.recover(root) is True
    _assert_old_files(root)
    assert json.loads((root / "build-info.json").read_text())["version"] == "0.2.0"
    assert not (root / patch.JOURNAL).exists()
    assert not (root / patch.STAGING).exists()


def test_a_failed_recovery_from_an_unreadable_journal_keeps_journal_and_backup(tmp_path,
                                                                               monkeypatch):
    root = _install(tmp_path / "app")
    z, sha = _zip(tmp_path / "u.zip", NEW)
    _interrupt_apply(root, z, sha, monkeypatch, at=8)
    (root / patch.JOURNAL).write_text("garbage")
    backed_up = sorted(p.relative_to(root / patch.BACKUP)
                       for p in (root / patch.BACKUP).rglob("*") if p.is_file())
    assert backed_up

    def denied(src, dst):
        raise PermissionError("unprivileged start cannot touch /opt")
    monkeypatch.setattr(patch, "_move", denied)
    with pytest.raises(OSError):
        patch.recover(root)
    assert (root / patch.JOURNAL).exists()
    patch.cleanup(root)
    assert sorted(p.relative_to(root / patch.BACKUP)
                  for p in (root / patch.BACKUP).rglob("*") if p.is_file()) == backed_up


def test_a_backup_that_cannot_be_cleared_stops_the_apply_before_the_swap(tmp_path, monkeypatch):
    """A garbage journal is recovered by restoring the whole backup, so the
    backup must never mix in an older version's leftovers."""
    root = _install(tmp_path / "app")
    (root / patch.BACKUP / "_internal/labeling_tool").mkdir(parents=True)
    (root / patch.BACKUP / "_internal/labeling_tool/a.pyc").write_bytes(b"older a")
    monkeypatch.setattr(patch.shutil, "rmtree",
                        lambda path, ignore_errors=False: None)
    z, sha = _zip(tmp_path / "u.zip", NEW)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(z, root, sha, platform="win32")
    _assert_old_files(root)
    assert not (root / patch.JOURNAL).exists()


# ------------------------------------------------ F5: the executable goes last

@pytest.mark.parametrize("platform,exe", [("win32", "LM_LabelingTool.exe"),
                                          ("linux", "LM_LabelingTool")])
def test_the_executable_is_swapped_after_every_other_file(tmp_path, monkeypatch, platform, exe):
    root = _install(tmp_path / "app")
    if exe != "LM_LabelingTool.exe":
        (root / "LM_LabelingTool.exe").rename(root / exe)
    files = {exe if rel == "LM_LabelingTool.exe" else rel: data for rel, data in NEW.items()}
    z, sha = _zip(tmp_path / "u.zip", files, platform=platform)
    moved = []
    real = patch._move

    def spy(src, dst):
        moved.append(Path(dst).name)
        real(src, dst)
    monkeypatch.setattr(patch, "_move", spy)
    patch.apply_patch(z, root, sha, platform=platform)
    assert moved[-2:] == [exe, exe]          # into the backup, then the new one in
    assert exe not in moved[:-2]
    assert (root / exe).read_bytes() == b"new exe"


# ------------------------------------- F6: Windows retries a briefly locked file

def _flaky_replace(monkeypatch, failures):
    real = patch.os.replace
    calls = {"n": 0}

    def fake(src, dst):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise PermissionError("locked by antivirus")
        real(src, dst)
    monkeypatch.setattr(patch.os, "replace", fake)
    return calls


def test_windows_retries_a_move_that_antivirus_briefly_locks(tmp_path, monkeypatch):
    monkeypatch.setattr(patch.checker, "current_platform", lambda: patch.checker.WINDOWS)
    sleeps = []
    monkeypatch.setattr(patch.time, "sleep", sleeps.append)
    calls = _flaky_replace(monkeypatch, failures=2)
    (tmp_path / "a").write_bytes(b"x")
    patch._move(tmp_path / "a", tmp_path / "sub" / "b")
    assert (tmp_path / "sub" / "b").read_bytes() == b"x"
    assert calls["n"] == 3
    assert sleeps == [0.2, 0.4]


def test_windows_gives_up_after_five_tries(tmp_path, monkeypatch):
    monkeypatch.setattr(patch.checker, "current_platform", lambda: patch.checker.WINDOWS)
    sleeps = []
    monkeypatch.setattr(patch.time, "sleep", sleeps.append)
    calls = _flaky_replace(monkeypatch, failures=99)
    (tmp_path / "a").write_bytes(b"x")
    with pytest.raises(PermissionError):
        patch._move(tmp_path / "a", tmp_path / "b")
    assert calls["n"] == 5
    assert sleeps == [0.2, 0.4, 0.8, 1.0]


def test_linux_does_not_retry_a_refused_move(tmp_path, monkeypatch):
    monkeypatch.setattr(patch.checker, "current_platform", lambda: patch.checker.LINUX)
    monkeypatch.setattr(patch.time, "sleep", lambda s: pytest.fail("slept on Linux"))
    calls = _flaky_replace(monkeypatch, failures=1)
    (tmp_path / "a").write_bytes(b"x")
    with pytest.raises(PermissionError):
        patch._move(tmp_path / "a", tmp_path / "b")
    assert calls["n"] == 1
