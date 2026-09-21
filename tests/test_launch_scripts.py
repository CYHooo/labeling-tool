# tests/test_launch_scripts.py
"""Contract for the double-click launcher in the repo root.

One launcher pair starts labeling_tool.app, whose login screen selects the
tool (online / local folder / few-shot): a Windows .bat (CRLF) and a Linux
.sh (LF, executable). Both cd to the repo root, prefer .venv's python and run
`python -m <module>` with the arguments passed through."""
import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

LAUNCHERS = {
    "run": "labeling_tool.app",
}


def test_only_one_launcher_pair():
    found = sorted(p.name for p in ROOT.glob("run*") if p.suffix in (".sh", ".bat"))
    assert found == ["run.bat", "run.sh"]


@pytest.mark.parametrize("name,module", LAUNCHERS.items())
def test_launcher_module_exists(name, module):
    assert importlib.util.find_spec(module) is not None, module


@pytest.mark.parametrize("name,module", LAUNCHERS.items())
def test_sh_launcher(name, module):
    path = ROOT / f"{name}.sh"
    data = path.read_bytes()
    assert b"\r\n" not in data, "sh launcher must use LF line endings"
    assert data.startswith(b"#!/usr/bin/env bash\n")
    if os.name == "nt":
        # NTFS has no exec bit, so st_mode is meaningless on Windows CI.
        # Check the executable bit recorded in the git index instead.
        result = subprocess.run(
            ["git", "ls-files", "-s", f"{name}.sh"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        assert result.stdout.startswith("100755"), "sh launcher must be executable in git index"
    else:
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
    # The login dialog blocks, so give it a moment, then stop it: still running
    # (timeout) means the package resolved and the GUI started.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([str(ROOT / "run.sh")], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=8)
