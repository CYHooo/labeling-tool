"""Carry out the downloaded update, per platform.

Windows cannot replace a running exe, so the app launches the Inno Setup
installer detached and exits immediately, handing over control; /RESTARTAPP
makes the installer start the new version when it is done.

Linux has no such restriction, so instead of handing over blindly, the app
installs the .deb packages synchronously with `pkexec dpkg -i` and waits for
dpkg to exit: a failed update can then be reported to the user -- including
*why* it failed -- rather than silently not happening.
"""

from __future__ import annotations

import enum
import os
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
    """Install synchronously and report what happened (see module docstring)."""
    paths = [Path(p) for p in paths]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    # Force the C locale for dpkg's own output. This is standard practice
    # when a caller parses command output, but here it matters concretely:
    # this product's users are mostly Korean (the UI defaults to Korean, the
    # packages are Korean-localized), so on their machines dpkg would emit
    # Korean text and the "dependency problems" substring match below would
    # never fire, silently downgrading a MISSING_DEPS case to a plain FAILED.
    env = {**os.environ, "LC_ALL": "C"}
    try:
        result = runner(build_deb_command(paths), capture_output=True,
                        text=True, check=False, env=env)
    except FileNotFoundError:
        # No pkexec on this system: an SSH session, WSL, or a desktop without
        # a polkit agent. Tell the user how to install by hand.
        return (InstallOutcome.FAILED,
                "pkexec not found: install polkit, or run "
                "`sudo dpkg -i` on the downloaded packages by hand")
    stderr = (getattr(result, "stderr", "") or "").strip()
    return classify_dpkg_result(result.returncode, stderr), stderr
