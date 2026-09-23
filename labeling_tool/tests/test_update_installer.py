"""Silent installer launch: the app hands over and exits."""
import subprocess
import sys
from pathlib import Path

import pytest

from labeling_tool.update import installer


def test_command_is_silent_and_logged(tmp_path):
    exe, log = tmp_path / "Setup.exe", tmp_path / "update.log"
    cmd = installer.build_command(exe, log)
    assert cmd[0] == str(exe)
    assert "/VERYSILENT" in cmd and "/SUPPRESSMSGBOXES" in cmd and "/NORESTART" in cmd
    assert "/RESTARTAPP" in cmd            # Inno relaunches the app after install
    assert f"/LOG={log}" in cmd


def test_launch_is_detached_and_does_not_wait(tmp_path):
    calls = []

    exe = tmp_path / "Setup.exe"
    exe.touch()  # Create the installer file

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))

    installer.launch_installer(exe, tmp_path / "update.log",
                               popen=_FakePopen)
    cmd, kwargs = calls[0]
    assert cmd == installer.build_command(exe, tmp_path / "update.log")
    assert kwargs.get("close_fds") is True
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.DETACHED_PROCESS
    else:
        assert "creationflags" not in kwargs   # POSIX has no such flag


def test_missing_installer_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        installer.launch_installer(tmp_path / "nope.exe", tmp_path / "l.log",
                                   popen=lambda *a, **k: None)
