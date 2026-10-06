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
    monkeypatch.setattr(deb, "MAINTAINER_SCRIPTS", {**deb.MAINTAINER_SCRIPTS, "postrm": deb.POSTRM + "# changed\n"})
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
    monkeypatch.setattr(deb, "MAINTAINER_SCRIPTS", {**deb.MAINTAINER_SCRIPTS, "postrm": deb.POSTRM + "# changed\n"})
    assert reuse_deb.main(["restamp", str(old_deb), str(tmp_path / "no.deb"), "0.2.2"]) == 3
    assert not (tmp_path / "no.deb").exists()


def test_an_unreadable_previous_deb_falls_back_to_a_full_build(tmp_path):
    """Anything reuse_deb cannot parse -- a non-deb, a truncated download, a
    control member in a compression it does not know -- means "build in full"
    (exit 3), never a failed release job."""
    bad = tmp_path / "bad.deb"
    bad.write_bytes(b"not an ar archive")
    assert reuse_deb.main(["restamp", str(bad), str(tmp_path / "o.deb"), "0.2.2"]) == 3


def test_a_truncated_previous_deb_falls_back_and_leaves_no_partial_file(old_deb, tmp_path):
    cut = tmp_path / "cut.deb"
    cut.write_bytes(old_deb.read_bytes()[:-200])
    out = tmp_path / "o.deb"
    assert reuse_deb.main(["restamp", str(cut), str(out), "0.2.2"]) == 3
    assert not out.exists() and not list(tmp_path.glob("*.part"))


def test_an_unknown_control_compression_falls_back(tmp_path):
    blob = reuse_deb._AR_MAGIC
    for name, body in ((b"debian-binary", b"2.0\n"), (b"control.tar.zst", b"\x28\xb5\x2f\xfd"), (b"data.tar.xz", b"x")):
        header = name.ljust(16) + b"0".ljust(12) + b"0".ljust(6) + b"0".ljust(6) + b"100644".ljust(8) + str(len(body)).encode().ljust(10) + b"`\n"
        blob += header + body + (b"\n" if len(body) % 2 else b"")
    deb_path = tmp_path / "zst.deb"
    deb_path.write_bytes(blob)
    assert reuse_deb.main(["restamp", str(deb_path), str(tmp_path / "o.deb"), "0.2.2"]) == 3


def test_not_reusable_when_deb_build_would_add_a_control_file(old_deb, monkeypatch):
    monkeypatch.setattr(deb, "MAINTAINER_SCRIPTS", {**deb.MAINTAINER_SCRIPTS, "prerm": "#!/bin/sh\nexit 0\n"})
    assert reuse_deb.reusable(old_deb, "0.2.2") is False


def test_not_reusable_when_the_staging_layout_revision_changed(old_deb, monkeypatch):
    monkeypatch.setattr(deb, "LAYOUT_REVISION", deb.LAYOUT_REVISION + 1)
    assert reuse_deb.reusable(old_deb, "0.2.2") is False


def test_the_rewritten_control_tar_stays_gnu_format(old_deb, tmp_path):
    new = tmp_path / "new.deb"
    reuse_deb.restamp(old_deb, new, "0.2.2")
    import io, lzma
    name, blob = next((n, b) for n, b in _members(new).items() if n.startswith("control.tar"))
    raw = lzma.decompress(blob) if name.endswith(".xz") else blob
    assert raw[257:265] == b"ustar  \0"   # GNU magic, as dpkg-deb writes it


def test_the_version_is_written_literally_not_as_a_regex_template():
    assert reuse_deb._restamped_control("Package: x\nVersion: 1\n", "0.2.2+g\\1") == \
        "Package: x\nVersion: 0.2.2+g\\1\n"
