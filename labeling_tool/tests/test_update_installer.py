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


def test_deb_command_installs_the_single_package(tmp_path):
    # A full update on Linux is one deb carrying the whole install.
    deb = tmp_path / "lm-labeling-tool_1.0.1_amd64.deb"
    cmd = installer.build_deb_command([deb])
    assert cmd == ["pkexec", "dpkg", "-i", str(deb)]


@pytest.mark.parametrize("code,stderr,expected", [
    (0, "", installer.InstallOutcome.OK),
    (126, "", installer.InstallOutcome.CANCELLED),
    # 127 means pkexec refused to even ask -- not authorised by polkit
    # policy, or the command could not be executed -- not a user choice.
    # Silently treating it as CANCELLED left the "Update" button doing
    # nothing on any machine whose polkit policy denies this user root.
    (127, "", installer.InstallOutcome.FAILED),
    (1, "dpkg: dependency problems prevent configuration of lm-labeling-tool",
     installer.InstallOutcome.MISSING_DEPS),
    (1, "dpkg: error processing archive (--install)", installer.InstallOutcome.FAILED),
])
def test_dpkg_results_are_classified(code, stderr, expected):
    assert installer.classify_dpkg_result(code, stderr) is expected


def test_missing_pkexec_is_reported_not_raised(tmp_path):
    # SSH sessions, WSL and stripped desktops have no polkit agent. An
    # uncaught FileNotFoundError here would crash the app mid-update.
    deb = tmp_path / "x.deb"
    deb.touch()

    def _runner(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    outcome, detail = installer.install_debs([deb], runner=_runner)
    assert outcome is installer.InstallOutcome.FAILED
    assert "pkexec" in detail


def test_install_debs_returns_stderr_on_failure(tmp_path):
    deb = tmp_path / "x.deb"
    deb.touch()

    class _Result:
        returncode = 1
        stderr = "dpkg: dependency problems prevent configuration of foo"

    outcome, detail = installer.install_debs([deb], runner=lambda *a, **k: _Result())
    assert outcome is installer.InstallOutcome.MISSING_DEPS
    assert "dependency problems" in detail


def test_install_debs_refuses_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        installer.install_debs([tmp_path / "nope.deb"], runner=lambda *a, **k: None)


def test_install_debs_forces_c_locale(tmp_path):
    # dpkg's output is localized. This product's users are mostly Korean, so
    # without a forced locale the "dependency problems" match would never
    # fire on their machines, silently misclassifying MISSING_DEPS as FAILED.
    deb = tmp_path / "x.deb"
    deb.touch()
    seen_kwargs = {}

    class _Result:
        returncode = 0
        stderr = ""

    def _runner(cmd, **kwargs):
        seen_kwargs.update(kwargs)
        return _Result()

    installer.install_debs([deb], runner=_runner)
    assert seen_kwargs["env"]["LC_ALL"] == "C"


def test_apply_command_runs_the_installed_app_as_root(tmp_path):
    cmd = installer.build_apply_command(tmp_path / "LM_LabelingTool", tmp_path / "u.zip", "a" * 64)
    assert cmd == ["pkexec", str(tmp_path / "LM_LabelingTool"), "--apply-update",
                   str(tmp_path / "u.zip"), "--sha256", "a" * 64]


def test_apply_zip_linux_classifies_cancel_and_failure(tmp_path):
    from types import SimpleNamespace
    z = tmp_path / "u.zip"
    z.write_bytes(b"x")
    ok = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64,
                                   runner=lambda *a, **k: SimpleNamespace(returncode=0, stderr=""))
    assert ok[0] is installer.InstallOutcome.OK
    cancel = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64,
                                       runner=lambda *a, **k: SimpleNamespace(returncode=126, stderr=""))
    assert cancel[0] is installer.InstallOutcome.CANCELLED
    bad = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64,
                                    runner=lambda *a, **k: SimpleNamespace(returncode=1, stderr="runtime mismatch"))
    assert bad == (installer.InstallOutcome.FAILED, "runtime mismatch")


def test_apply_zip_linux_reports_missing_pkexec(tmp_path):
    z = tmp_path / "u.zip"
    z.write_bytes(b"x")

    def _runner(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    outcome, detail = installer.apply_zip_linux(tmp_path / "exe", z, "a" * 64, runner=_runner)
    assert outcome is installer.InstallOutcome.FAILED
    assert "pkexec" in detail
