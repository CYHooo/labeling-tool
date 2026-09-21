# tests/test_launch_scripts.py
"""Contract for the double-click launchers in the repo root.

Each entry point has a Windows (.bat, CRLF) and a Linux (.sh, LF, executable)
launcher that cds to the repo root, prefers .venv's python and runs
`python -m <module>` with the arguments passed through."""
import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

LAUNCHERS = {
    "run_labeling": "labeling_tool.app",
    "run_local": "labeling_tool.app_local",
    "run_fewshot": "annotation_tool.main",
}


@pytest.mark.parametrize("name,module", LAUNCHERS.items())
def test_launcher_module_exists(name, module):
    assert importlib.util.find_spec(module) is not None, module


@pytest.mark.parametrize("name,module", LAUNCHERS.items())
def test_sh_launcher(name, module):
    path = ROOT / f"{name}.sh"
    data = path.read_bytes()
    assert b"\r\n" not in data, "sh launcher must use LF line endings"
    assert data.startswith(b"#!/usr/bin/env bash\n")
    assert path.stat().st_mode & stat.S_IXUSR, "sh launcher must be executable"
    text = data.decode()
    assert f"-m {module} " in text and '"$@"' in text
    assert ".venv/bin/python" in text


@pytest.mark.parametrize("name,module", LAUNCHERS.items())
def test_bat_launcher(name, module):
    data = (ROOT / f"{name}.bat").read_bytes()
    lines = data.split(b"\n")[:-1]
    assert all(line.endswith(b"\r") for line in lines), "bat launcher must use CRLF"
    text = data.decode()
    assert 'cd /d "%~dp0"' in text
    assert f"-m {module} %*" in text
    assert r".venv\Scripts\python.exe" in text
    assert "pause" in text  # keep the window open on failure


def test_gitattributes_pins_line_endings():
    text = (ROOT / ".gitattributes").read_text()
    assert "*.bat text eol=crlf" in text
    assert "*.sh text eol=lf" in text


@pytest.mark.skipif(os.name == "nt", reason="bash launcher")
def test_sh_launcher_runs_from_another_directory(tmp_path):
    # --help makes argparse exit 0 before any Qt window is created
    out = subprocess.run([str(ROOT / "run_fewshot.sh"), "--help"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "--backend" in out.stdout
