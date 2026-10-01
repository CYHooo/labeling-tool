"""Hand the downloaded Inno Setup installer control, then quit.

Windows cannot replace a running exe, so the app launches the installer
detached and exits immediately; /RESTARTAPP makes the installer start the new
version when it is done.
"""

from __future__ import annotations

import enum
import subprocess
import sys
from pathlib import Path

SILENT_ARGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RESTARTAPP")


def build_command(installer_path: Path, log_path: Path) -> list[str]:
    return [str(installer_path), *SILENT_ARGS, f"/LOG={log_path}"]


def launch_and_exit_args() -> dict:
    """Popen kwargs that detach the installer from this process."""
    if sys.platform == "win32":
        return {"close_fds": True,
                "creationflags": subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"close_fds": True}


def launch_installer(installer_path: Path, log_path: Path,
                     popen=subprocess.Popen) -> None:
    """Start the installer detached. The caller must exit right after."""
    installer_path = Path(installer_path)
    if not installer_path.is_file():
        raise FileNotFoundError(installer_path)
    popen(build_command(installer_path, log_path), **launch_and_exit_args())


# -- Linux: dpkg installation -----------------------------------------------
#
# Unlike Windows -- which cannot replace a running exe, so the app hands the
# installer over and exits blind -- Linux can wait for dpkg to finish and
# read its exit code, so a failed update is reported instead of silently not
# happening.

# pkexec's own exit codes for "the user dismissed the dialog" (126) and
# "the authorisation could not even be requested" (127) -- no polkit agent
# in this session. Both mean: go back to the app quietly.
PKEXEC_CANCELLED = 126
PKEXEC_NOT_AUTHORISED = 127


class InstallOutcome(enum.Enum):
    OK = "ok"
    CANCELLED = "cancelled"          # user dismissed the password dialog
    MISSING_DEPS = "missing_deps"    # dpkg -i does not fetch from repositories
    FAILED = "failed"


def build_deb_command(paths) -> list[str]:
    """Install every package in ONE dpkg call.

    dpkg unpacks all the archives before configuring any of them, so the app
    package's Depends on the runtime package is satisfied within the call and
    the order on the command line does not matter.

    dpkg -i rather than `apt install ./x.deb`: the runtime package's version
    is a hash, not a sequence, so apt reads a runtime switch as a downgrade
    and refuses it. dpkg merely warns."""
    return ["pkexec", "dpkg", "-i", *[str(p) for p in paths]]


def classify_dpkg_result(returncode: int, stderr: str) -> InstallOutcome:
    """What actually happened, so the caller can tell a cancel from a fault."""
    if returncode == 0:
        return InstallOutcome.OK
    if returncode in (PKEXEC_CANCELLED, PKEXEC_NOT_AUTHORISED):
        return InstallOutcome.CANCELLED
    if "dependency problems" in (stderr or ""):
        # dpkg -i does not resolve dependencies. Nothing is broken: the user
        # needs one apt call to pull the missing system libraries.
        return InstallOutcome.MISSING_DEPS
    return InstallOutcome.FAILED


def install_debs(paths, runner=subprocess.run) -> tuple[InstallOutcome, str]:
    """Install synchronously and report what happened.

    Unlike Windows -- which cannot replace a running exe, so the app hands the
    installer over and exits blind -- Linux can wait for dpkg and read its
    exit code, so a failed update is reported instead of silently not
    happening."""
    paths = [Path(p) for p in paths]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    try:
        result = runner(build_deb_command(paths), capture_output=True,
                        text=True, check=False)
    except FileNotFoundError:
        # No pkexec on this system: an SSH session, WSL, or a desktop without
        # a polkit agent. Tell the user how to install by hand.
        return (InstallOutcome.FAILED,
                "pkexec not found: install polkit, or run "
                "`sudo dpkg -i` on the downloaded packages by hand")
    stderr = (getattr(result, "stderr", "") or "").strip()
    return classify_dpkg_result(result.returncode, stderr), stderr
