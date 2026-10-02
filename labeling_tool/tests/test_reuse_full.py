"""Deciding whether a release can ship the previous full installer again."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import reuse_full  # noqa: E402


def _release(tag, *names):
    return {"tagName": tag, "assets": [{"name": n} for n in names]}


PREV = _release("v1.4.0",
                "LM_LabelingTool-Setup-v1.4.0.exe",
                "update-v1.4.0-r88c8d3f0-windows.zip",
                "SHA256SUMS.txt")


def test_same_runtime_reuses_the_previous_full_installer():
    assert reuse_full.plan_reuse(PREV, "r88c8d3f0") == (
        "v1.4.0", "LM_LabelingTool-Setup-v1.4.0.exe")


def test_a_changed_runtime_needs_a_fresh_full_build():
    assert reuse_full.plan_reuse(PREV, "r12345678") is None


def test_a_release_without_a_full_installer_cannot_be_reused():
    rel = _release("v1.4.0", "update-v1.4.0-r88c8d3f0-windows.zip", "SHA256SUMS.txt")
    assert reuse_full.plan_reuse(rel, "r88c8d3f0") is None


def test_a_release_without_checksums_cannot_be_reused():
    rel = _release("v1.4.0", "update-v1.4.0-r88c8d3f0-windows.zip",
                   "LM_LabelingTool-Setup-v1.4.0.exe")
    assert reuse_full.plan_reuse(rel, "r88c8d3f0") is None


def test_no_previous_release_means_a_full_build():
    assert reuse_full.plan_reuse({}, "r88c8d3f0") is None
    assert reuse_full.plan_reuse({"tagName": "nightly", "assets": []}, "r88c8d3f0") is None


def test_names_follow_the_client_contract():
    """The client looks assets up by these exact names; building them any
    other way would let the reuse path drift from what clients request."""
    from labeling_tool.update import checker
    tag, full = reuse_full.plan_reuse(PREV, "r88c8d3f0")
    assert full == checker.full_asset_name("1.4.0", checker.WINDOWS)


def _published(tmp_path, name, content):
    f = tmp_path / name
    f.write_bytes(content)
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n", encoding="ascii")
    return f


def test_verify_accepts_the_published_bytes(tmp_path):
    f = _published(tmp_path, "LM_LabelingTool-Setup-v1.4.0.exe", b"installer")
    assert reuse_full.verify(tmp_path / "SHA256SUMS.txt", f)


def test_verify_rejects_altered_bytes(tmp_path):
    f = _published(tmp_path, "LM_LabelingTool-Setup-v1.4.0.exe", b"installer")
    f.write_bytes(b"tampered!")
    assert not reuse_full.verify(tmp_path / "SHA256SUMS.txt", f)


def test_verify_rejects_a_file_the_sums_do_not_list(tmp_path):
    _published(tmp_path, "LM_LabelingTool-Setup-v1.4.0.exe", b"installer")
    other = tmp_path / "other.exe"
    other.write_bytes(b"installer")
    assert not reuse_full.verify(tmp_path / "SHA256SUMS.txt", other)


def test_cli_plan_prints_tag_and_name(tmp_path, capsys):
    # gh on Windows may write a BOM when redirected through PowerShell.
    p = tmp_path / "rel.json"
    p.write_text("﻿" + json.dumps(PREV), encoding="utf-8")
    assert reuse_full.main(["plan", str(p), "r88c8d3f0"]) == 0
    assert capsys.readouterr().out == "v1.4.0\tLM_LabelingTool-Setup-v1.4.0.exe\n"


def test_cli_plan_prints_nothing_when_a_full_build_is_needed(tmp_path, capsys):
    p = tmp_path / "rel.json"
    p.write_text(json.dumps(PREV), encoding="utf-8")
    assert reuse_full.main(["plan", str(p), "r00000000"]) == 0
    assert capsys.readouterr().out == ""


def test_cli_verify_exit_codes(tmp_path):
    f = _published(tmp_path, "a.exe", b"x")
    assert reuse_full.main(["verify", str(tmp_path / "SHA256SUMS.txt"), str(f)]) == 0
    f.write_bytes(b"y")
    assert reuse_full.main(["verify", str(tmp_path / "SHA256SUMS.txt"), str(f)]) == 1


def test_cli_rejects_bad_usage(capsys):
    assert reuse_full.main(["nonsense"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_reuse_when_the_previous_release_has_our_runtime_zip():
    rel = {"tagName": "v0.2.0", "assets": [{"name": n} for n in (
        "LM_LabelingTool-Setup-v0.2.0.exe", "update-v0.2.0-r11111111-windows.zip", "SHA256SUMS.txt")]}
    assert reuse_full.plan_reuse(rel, "r11111111") == ("v0.2.0", "LM_LabelingTool-Setup-v0.2.0.exe")
    assert reuse_full.plan_reuse(rel, "r22222222") is None
