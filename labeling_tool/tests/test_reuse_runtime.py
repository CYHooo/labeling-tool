"""Deciding whether a release can ship the previous runtime deb again."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import reuse_runtime  # noqa: E402


def test_reuses_when_the_previous_release_carries_our_runtime_id():
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-r3f8a1c92_amd64.deb"},
        {"name": "lm-labeling-tool-runtime_1.4.0_amd64.deb"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") == \
        ("v1.4.0", "lm-labeling-tool-runtime_1.4.0_amd64.deb")


def test_rebuilds_when_the_runtime_id_moved():
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-rOLDOLD1_amd64.deb"},
        {"name": "lm-labeling-tool-runtime_1.4.0_amd64.deb"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") is None


def test_rebuilds_when_the_previous_release_has_no_runtime_deb():
    # Nothing to copy. Also the exact hole spec 7.2.1 exists to close.
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-r3f8a1c92_amd64.deb"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") is None


def test_rebuilds_when_the_previous_release_is_windows_only():
    # The first release after this feature ships has no Linux assets at all.
    release = {"tagName": "v1.4.1", "assets": [
        {"name": "LM_LabelingTool-Setup-v1.4.1.exe"}]}
    assert reuse_runtime.plan(release, "r3f8a1c92") is None


def test_verify_accepts_a_matching_checksum(tmp_path):
    f = tmp_path / "lm-labeling-tool-runtime_1.4.0_amd64.deb"
    f.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    sums = f"{digest}  {f.name}\n"
    assert reuse_runtime.verify(sums, f) is True


def test_verify_rejects_a_mismatch(tmp_path):
    f = tmp_path / "lm-labeling-tool-runtime_1.4.0_amd64.deb"
    f.write_bytes(b"payload")
    assert reuse_runtime.verify("0" * 64 + f"  {f.name}\n", f) is False


def test_verify_rejects_a_file_with_no_published_checksum(tmp_path):
    # Republishing something we cannot verify would launder a corrupted or
    # tampered asset into a new release under our name.
    f = tmp_path / "lm-labeling-tool-runtime_1.4.0_amd64.deb"
    f.write_bytes(b"payload")
    assert reuse_runtime.verify("", f) is False


def test_cli_plan_prints_tag_and_name(tmp_path, capsys):
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-r3f8a1c92_amd64.deb"},
        {"name": "lm-labeling-tool-runtime_1.4.0_amd64.deb"}]}
    p = tmp_path / "rel.json"
    p.write_text(json.dumps(release), encoding="utf-8")
    assert reuse_runtime.main(["plan", str(p), "r3f8a1c92"]) == 0
    assert capsys.readouterr().out == \
        "v1.4.0\tlm-labeling-tool-runtime_1.4.0_amd64.deb\n"


def test_cli_plan_prints_nothing_when_a_rebuild_is_needed(tmp_path, capsys):
    release = {"tagName": "v1.4.0", "assets": [
        {"name": "lm-labeling-tool_1.4.0-r3f8a1c92_amd64.deb"},
        {"name": "lm-labeling-tool-runtime_1.4.0_amd64.deb"}]}
    p = tmp_path / "rel.json"
    p.write_text(json.dumps(release), encoding="utf-8")
    assert reuse_runtime.main(["plan", str(p), "rOTHEROTHER"]) == 0
    assert capsys.readouterr().out == ""


def test_cli_verify_exit_codes(tmp_path):
    f = tmp_path / "a.deb"
    f.write_bytes(b"x")
    sums_path = tmp_path / "SHA256SUMS.txt"
    sums_path.write_text(f"{hashlib.sha256(b'x').hexdigest()}  a.deb\n",
                          encoding="ascii")
    assert reuse_runtime.main(["verify", str(sums_path), str(f)]) == 0
    f.write_bytes(b"y")
    assert reuse_runtime.main(["verify", str(sums_path), str(f)]) == 1


def test_cli_rejects_bad_usage(capsys):
    assert reuse_runtime.main(["nonsense"]) == 2
    assert "usage:" in capsys.readouterr().err
