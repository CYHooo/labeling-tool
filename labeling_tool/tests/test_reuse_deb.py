"""reuse_deb.py: ship the previous release's deb under a new version without
recompressing its 1.7 GB payload -- only the small control member changes."""
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import deb  # noqa: E402
import layers  # noqa: E402
import reuse_deb  # noqa: E402
import reuse_full  # noqa: E402

from labeling_tool.update import checker  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="dpkg-deb not installed")


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    entry = dist / layers.app_entry_name(layers.LINUX)
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_bytes(b"#!/bin/sh\n")
    entry.chmod(0o755)
    lib = dist / "_internal" / "torch" / "libtorch.so"
    lib.parent.mkdir(parents=True, exist_ok=True)
    lib.write_bytes(b"not a real shared object" * 1000)
    return dist


@pytest.fixture
def old_deb(tmp_path, monkeypatch):
    monkeypatch.delenv("LT_FAST", raising=False)   # xz, like a release
    return deb.build(_make_dist(tmp_path), tmp_path / "old", "0.2.1")


def _field(deb_path: Path, name: str) -> str:
    return subprocess.run(["dpkg-deb", "-f", str(deb_path), name], check=True,
                          capture_output=True, text=True).stdout.strip()


def _members(deb_path: Path) -> dict[str, bytes]:
    return dict(reuse_deb._read_ar(deb_path.read_bytes()))


def test_restamp_changes_only_the_version(old_deb, tmp_path):
    new = tmp_path / "new" / deb.deb_filename("0.2.2")
    reuse_deb.restamp(old_deb, new, "0.2.2")
    assert _field(new, "Version") == "0.2.2"
    for name in ("Package", "Architecture", "Depends", "Installed-Size", reuse_deb.FINGERPRINT_FIELD):
        assert _field(new, name) == _field(old_deb, name)
    old, fresh = _members(old_deb), _members(new)
    assert list(fresh) == list(old)          # same members, same order
    data = next(n for n in old if n.startswith("data.tar"))
    assert fresh[data] == old[data]          # the payload is not recompressed


def test_a_restamped_deb_is_a_valid_package(old_deb, tmp_path):
    new = tmp_path / "new.deb"
    reuse_deb.restamp(old_deb, new, "0.2.2")
    subprocess.run(["dpkg-deb", "--info", str(new)], check=True, capture_output=True)
    root = tmp_path / "x"
    subprocess.run(["dpkg-deb", "-x", str(new), str(root)], check=True)
    assert (root / "opt" / "lm-labeling-tool" / layers.app_entry_name(layers.LINUX)).is_file()
    ctl = tmp_path / "ctl"
    subprocess.run(["dpkg-deb", "-e", str(new), str(ctl)], check=True)
    for script, body in (("postinst", deb.POSTINST), ("preinst", deb.PREINST), ("postrm", deb.POSTRM)):
        assert (ctl / script).read_text(encoding="utf-8") == body
        assert (ctl / script).stat().st_mode & stat.S_IXUSR


def test_control_members_keep_root_ownership(old_deb, tmp_path):
    new = tmp_path / "new.deb"
    reuse_deb.restamp(old_deb, new, "0.2.2")
    blob = next(b for n, b in _members(new).items() if n.startswith("control.tar"))
    import io
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        for info in tar.getmembers():
            assert (info.uid, info.gid) == (0, 0), info.name


def test_reusable_when_nothing_but_the_version_would_change(old_deb):
    assert reuse_deb.reusable(old_deb, "0.2.2") is True


def test_not_reusable_when_the_depends_changed(old_deb, monkeypatch):
    monkeypatch.setattr(deb, "RUNTIME_DEPENDS", deb.RUNTIME_DEPENDS + ("libnew0",))
    assert reuse_deb.reusable(old_deb, "0.2.2") is False


def test_not_reusable_when_a_maintainer_script_changed(old_deb, monkeypatch):
    monkeypatch.setattr(deb, "POSTRM", deb.POSTRM + "# changed\n")
    assert reuse_deb.reusable(old_deb, "0.2.2") is False


def test_not_reusable_when_the_desktop_entry_changed(old_deb, tmp_path, monkeypatch):
    template = tmp_path / "other.desktop"
    template.write_text(deb._DESKTOP_TEMPLATE.read_text(encoding="utf-8") + "Keywords=x;\n", encoding="utf-8")
    monkeypatch.setattr(deb, "_DESKTOP_TEMPLATE", template)
    assert reuse_deb.reusable(old_deb, "0.2.2") is False


def test_not_reusable_when_the_old_deb_has_no_fingerprint(old_deb, tmp_path):
    # v0.2.1 and earlier were built before the fingerprint field existed:
    # nothing proves their extras match, so the first release after this
    # change builds in full.
    stripped = tmp_path / "nofp.deb"
    reuse_deb.restamp(old_deb, stripped, "0.2.1", drop_fields=(reuse_deb.FINGERPRINT_FIELD,))
    assert _field(stripped, reuse_deb.FINGERPRINT_FIELD) == ""
    assert reuse_deb.reusable(stripped, "0.2.2") is False


def test_plan_finds_the_previous_deb_for_the_same_runtime():
    release = {"tagName": "v0.2.1", "assets": [
        {"name": checker.full_asset_name("0.2.1", checker.LINUX)},
        {"name": checker.update_asset_name("0.2.1", "ra493a449", checker.LINUX)},
        {"name": checker.SUMS_ASSET},
    ]}
    assert reuse_full.plan_reuse(release, "ra493a449", checker.LINUX) == (
        "v0.2.1", checker.full_asset_name("0.2.1", checker.LINUX))
    assert reuse_full.plan_reuse(release, "rffffffff", checker.LINUX) is None


def test_cli_restamps_or_says_why_not(old_deb, tmp_path, monkeypatch):
    out = tmp_path / "cli.deb"
    assert reuse_deb.main(["restamp", str(old_deb), str(out), "0.2.2"]) == 0
    assert _field(out, "Version") == "0.2.2"
    monkeypatch.setattr(deb, "POSTRM", deb.POSTRM + "# changed\n")
    assert reuse_deb.main(["restamp", str(old_deb), str(tmp_path / "no.deb"), "0.2.2"]) == 3
    assert not (tmp_path / "no.deb").exists()
