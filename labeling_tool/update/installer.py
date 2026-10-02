"""Carry out the downloaded update, per platform.

Windows cannot replace a running exe, so the app launches the Inno Setup
installer detached and exits immediately, handing over control; /RESTARTAPP
makes the installer start the new version when it is done.

Linux has no such restriction, so instead of handing over blindly, the app
installs the .deb package synchronously with `pkexec dpkg -i` and waits for
dpkg to exit: a failed update can then be reported to the user -- including
*why* it failed -- rather than silently not happening.

An app-layer update zip is applied by labeling_tool.update.patch: in-process
on Windows (the install dir is user-writable), and on Linux by running the
installed app itself as root (build_apply_command) since /opt is root-owned.
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

# pkexec's own exit codes. These are NOT interchangeable:
# 126 is the user dismissing the authentication dialog -- a deliberate,
# informed "no", so the app goes back quietly with no message.
# 127 is pkexec refusing to even ASK: the subject is not authorised by
# polkit policy, or the command could not be executed at all. The user
# never saw a prompt and never made a choice, so treating this as a quiet
# cancel means the "Update" button does nothing, every single time, on any
# machine whose polkit policy does not allow this user to gain root --
# exactly the silent failure this project keeps having to hunt down.
# 127 is classified as FAILED, which does report stderr to the user.
PKEXEC_CANCELLED = 126
PKEXEC_NOT_AUTHORISED = 127


class InstallOutcome(enum.Enum):
    OK = "ok"
    CANCELLED = "cancelled"          # user dismissed the password dialog
    MISSING_DEPS = "missing_deps"    # dpkg -i does not fetch from repositories
    FAILED = "failed"


def build_deb_command(paths) -> list[str]:
    """Install the downloaded package (a full update is a single deb).

    dpkg -i of the local file: the update was already downloaded and
    verified against SHA256SUMS, so nothing needs fetching from a
    repository except missing system libraries -- see MISSING_DEPS."""
    return ["pkexec", "dpkg", "-i", *[str(p) for p in paths]]


def classify_dpkg_result(returncode: int, stderr: str) -> InstallOutcome:
    """What actually happened, so the caller can tell a cancel from a fault."""
    if returncode == 0:
        return InstallOutcome.OK
    if returncode == PKEXEC_CANCELLED:
        return InstallOutcome.CANCELLED
    if returncode == PKEXEC_NOT_AUTHORISED:
        # Not a user choice -- see PKEXEC_NOT_AUTHORISED's comment above.
        # Report it like any other failure so the user is not left staring
        # at an "Update" button that silently does nothing.
        return InstallOutcome.FAILED
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


# -- Linux: applying an app-layer zip ------------------------------------------

def build_apply_command(exe: Path, zip_path: Path, sha256: str) -> list[str]:
    """Linux: /opt is root-owned, so the installed app applies its own update
    zip as root. The zip is re-verified there (see patch.apply_patch)."""
    return ["pkexec", str(exe), "--apply-update", str(zip_path), "--sha256", sha256]


def apply_zip_linux(exe: Path, zip_path: Path, sha256: str,
                    runner=subprocess.run) -> tuple[InstallOutcome, str]:
    """Apply the zip as root and wait. The app's own exit code is 0 or 1
    (with the reason on stderr); 126/127 are pkexec's, as for dpkg."""
    if not Path(zip_path).is_file():
        raise FileNotFoundError(zip_path)
    try:
        result = runner(build_apply_command(exe, zip_path, sha256), capture_output=True,
                        text=True, check=False, env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError:
        return InstallOutcome.FAILED, "pkexec not found: install polkit"
    stderr = (getattr(result, "stderr", "") or "").strip()
    if result.returncode == 0:
        return InstallOutcome.OK, stderr
    if result.returncode == PKEXEC_CANCELLED:
        return InstallOutcome.CANCELLED, stderr
    return InstallOutcome.FAILED, stderr
