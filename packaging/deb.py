"""Assemble the two Linux deb packages from a PyInstaller onedir build.

This is `installer.iss`'s counterpart on Linux. It builds plain binary debs
by hand (`dpkg-deb --build`) rather than going through `dpkg-buildpackage`:
`dpkg-buildpackage` is for SOURCE packages that Debian rebuilds from a
`debian/rules` recipe, and we have no source package to offer -- we are
shipping a PyInstaller binary tree, the exact analogue of the Windows exe.
`dpkg-deb` builds a binary .deb directly from a staged root plus a
`DEBIAN/control` file, which is all a binary distribution needs.

The runtime package's Version field is the runtime id itself (e.g.
"0~r3f8a1c92"), not a release number -- see
docs/superpowers/specs/2026-09-30-linux-deb-distribution.md 4.1. The id is
computed from the runtime layer's file listing (packaging.layers), so two
builds with an unchanged runtime always produce a package APT considers
identical, and a changed runtime always produces a package APT considers
newer (the "0~" prefix sorts before every real version string, so a runtime
package can never be mistaken for, or outrank, an application release).
The app package's Depends then pins the exact runtime id it was built
against, which is what makes `dpkg -i` refuse to install an app package on
top of a mismatched runtime -- the one line that replaces the hand-written
Pascal guard installer.iss needs on Windows (a guard that has twice broken
in ways that were invisible until it mattered: a brace-parsing bug once
silently disabled it, and a MsgBox once hung CI for 96 minutes).

The deb FILENAME and the deb Version are deliberately different -- see
docs/superpowers/specs/2026-09-30-linux-deb-distribution.md 7.2:

- The app deb's filename carries the runtime id
  (lm-labeling-tool_<version>-<runtime id>_amd64.deb) so a client can tell
  from the name alone, without downloading it, whether a release's app
  package matches its own runtime. Its package Version is the plain
  version number; the runtime binding is expressed through Depends, not
  through the version string.
- The runtime deb's filename carries only the version
  (lm-labeling-tool-runtime_<version>_amd64.deb): a client taking a full
  update knows the version it is fetching but not yet the runtime id that
  build will produce, so the id cannot be part of the name it asks for.

Imported by CI, and unit-tested directly (labeling_tool/tests/test_deb.py)
so the control fields never have to be verified by hand.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layers  # noqa: E402

INSTALL_PREFIX = "/opt/lm-labeling-tool"
MAINTAINER = "CYHooo <cyh960502@gmail.com>"

APP_PACKAGE = "lm-labeling-tool"
RUNTIME_PACKAGE = "lm-labeling-tool-runtime"
ARCH = "amd64"

_DESKTOP_TEMPLATE = Path(__file__).resolve().parent / "linux" / \
    "lm-labeling-tool.desktop.in"

# Icon sizes PyInstaller collects into _internal/labeling_tool/resources/
# (see packaging/labeling_tool.spec's ICON_PNGS) -- the same four the
# hicolor icon theme expects a dedicated rendering for, rather than one
# large PNG the desktop environment rescales on the fly.
ICON_SIZES = (16, 32, 48, 256)

# Qt's xcb platform plugin links against the host's X libraries; PyInstaller
# does not collect them. Without these the package installs cleanly and the
# app dies at startup with "could not load the Qt platform plugin xcb".
#
# Installation goes through `dpkg -i`, which does NOT fetch from
# repositories, so this list must stay within what a desktop install of the
# supported Ubuntu releases already has. CI proves it: the smoke test must
# install without `apt-get install -f`. If something is genuinely needed and
# not present by default, collect it into the runtime layer instead of
# declaring it here.
RUNTIME_DEPENDS = (
    "libc6 (>= 2.35)",
    "libgl1",
    # Ubuntu 24.04 (noble) renamed this package to libglib2.0-0t64 as part
    # of its 64-bit time_t transition; 22.04 (jammy) still ships the old
    # name. The alternation covers both -- do not collapse it to one name,
    # that silently drops one of the two supported releases.
    "libglib2.0-0t64 | libglib2.0-0",
    "libxkbcommon-x11-0",
    "libxcb-xinerama0",
    "libxcb-icccm4",
    "libxcb-image0",
    "libxcb-keysyms1",
    "libxcb-randr0",
    "libxcb-render-util0",
    "libxcb-shape0",
    "libdbus-1-3",
)

# Both tools must not fail the install when they are absent -- minimal
# systems (containers, CI runners) commonly lack both.
POSTINST = """#!/bin/sh
set -e
# Make the new entry and icon visible without a re-login. Both tools are
# absent on minimal systems, and their absence must not fail the install.
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
"""


def _control(fields: list[tuple[str, str]]) -> str:
    """Render a Debian control stanza in a fixed field order, LF-terminated.

    dpkg-deb rejects a control file whose last field has no trailing
    newline, so every field (including the last) ends with "\\n"."""
    return "".join(f"{key}: {value}\n" for key, value in fields)


def runtime_control(runtime_id: str, installed_kb: int) -> str:
    """DEBIAN/control for the runtime package.

    Version is the runtime id itself, prefixed with "0~" so it always
    sorts below any real application version -- see the module docstring."""
    return _control([
        ("Package", RUNTIME_PACKAGE),
        ("Version", f"0~{runtime_id}"),
        ("Architecture", ARCH),
        ("Maintainer", MAINTAINER),
        ("Installed-Size", str(int(installed_kb))),
        ("Depends", ", ".join(RUNTIME_DEPENDS)),
        ("Section", "misc"),
        ("Priority", "optional"),
        ("Description", "LM Labeling Tool runtime (Python, PyQt5, torch)"),
    ])


def app_control(version: str, runtime_id: str, installed_kb: int) -> str:
    """DEBIAN/control for the app package.

    Depends pins the exact runtime id this build was staged against -- the
    line that replaces installer.iss's hand-written guard."""
    return _control([
        ("Package", APP_PACKAGE),
        ("Version", version),
        ("Architecture", ARCH),
        ("Maintainer", MAINTAINER),
        ("Installed-Size", str(int(installed_kb))),
        ("Depends", f"{RUNTIME_PACKAGE} (= 0~{runtime_id})"),
        ("Section", "graphics"),
        ("Priority", "optional"),
        ("Description", "LM Labeling Tool"),
    ])


def app_deb_filename(version: str, runtime_id: str) -> str:
    """Must agree with labeling_tool.update.checker.app_asset_name."""
    return f"{APP_PACKAGE}_{version}-{runtime_id}_{ARCH}.deb"


def runtime_deb_filename(version: str) -> str:
    """Must agree with labeling_tool.update.checker.full_asset_names."""
    return f"{RUNTIME_PACKAGE}_{version}_{ARCH}.deb"


def desktop_entry(version: str) -> str:
    """The .desktop file content, version placeholder resolved."""
    text = _DESKTOP_TEMPLATE.read_text(encoding="utf-8")
    return text.replace("@VERSION@", version)


def _write_control_dir(root: Path, control: str, postinst: str | None = None) -> None:
    debian = root / "DEBIAN"
    debian.mkdir(parents=True, exist_ok=True)
    (debian / "control").write_text(control, encoding="utf-8")
    if postinst is not None:
        path = debian / "postinst"
        path.write_text(postinst, encoding="utf-8")
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _stage_runtime_layer(dist_dir: Path, root: Path, platform: str | None = None) -> int:
    """Copy every runtime-layer file under <root>/opt/lm-labeling-tool/.
    Returns the total staged size in bytes."""
    target_root = root / INSTALL_PREFIX.lstrip("/")
    total = 0
    for rel, path in layers.iter_runtime_files(dist_dir, platform):
        dest = target_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        total += path.stat().st_size
    return total


def _stage_app_extras(dist_dir: Path, root: Path, version: str) -> None:
    """.desktop entry, icons and the /usr/bin symlink -- everything that
    references the installed executable, which is why they belong to the
    app layer rather than the runtime layer."""
    applications = root / "usr" / "share" / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    (applications / f"{APP_PACKAGE}.desktop").write_text(
        desktop_entry(version), encoding="utf-8")

    icon_src_dir = dist_dir / "_internal" / "labeling_tool" / "resources"
    for px in ICON_SIZES:
        src = icon_src_dir / f"icon-{px}.png"
        if not src.is_file():
            continue
        icon_dir = root / "usr" / "share" / "icons" / "hicolor" / \
            f"{px}x{px}" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, icon_dir / f"{APP_PACKAGE}.png")

    bin_dir = root / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / APP_PACKAGE
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(f"{INSTALL_PREFIX}/{layers.app_entry_name(layers.LINUX)}")


def _dpkg_deb_build(root: Path, out_path: Path, fast: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["dpkg-deb", "--build", "--root-owner-group"]
    # Compression controlled the same way the Windows build picks its
    # compressor via /DMyFast=1: fast gzip for local iteration, xz for a
    # real release (XZ_OPT=-T4 is set by the caller to parallelize it).
    args += (["-Zgzip", "-z1"] if fast else ["-Zxz"])
    args += [str(root), str(out_path)]
    subprocess.run(args, check=True)


def build(dist_dir: Path, out_dir: Path, version: str) -> dict[str, Path]:
    """Build both debs from a PyInstaller onedir output.

    Returns {"runtime": <path>, "app": <path>}.
    """
    dist_dir = Path(dist_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fast = bool(os.environ.get("LT_FAST"))

    runtime_id = layers.compute_runtime_id(dist_dir, layers.LINUX)

    with tempfile.TemporaryDirectory(prefix="deb-stage-") as tmp:
        tmp_path = Path(tmp)

        runtime_root = tmp_path / "runtime"
        runtime_bytes = _stage_runtime_layer(dist_dir, runtime_root, layers.LINUX)
        runtime_kb = max(1, runtime_bytes // 1024)
        _write_control_dir(runtime_root, runtime_control(runtime_id, runtime_kb))
        runtime_out = out_dir / runtime_deb_filename(version)
        _dpkg_deb_build(runtime_root, runtime_out, fast)

        app_root = tmp_path / "app"
        app_bytes, _ = layers.stage_app_layer(
            dist_dir, app_root / INSTALL_PREFIX.lstrip("/"), layers.LINUX)
        _stage_app_extras(dist_dir, app_root, version)
        app_kb = max(1, app_bytes // 1024)
        _write_control_dir(
            app_root, app_control(version, runtime_id, app_kb), POSTINST)
        app_out = out_dir / app_deb_filename(version, runtime_id)
        _dpkg_deb_build(app_root, app_out, fast)

    return {"runtime": runtime_out, "app": app_out}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 4 and args[0] == "build":
        _, dist_dir, out_dir, version = args
        paths = build(Path(dist_dir), Path(out_dir), version)
        for kind, path in paths.items():
            print(f"{kind}: {path}")
        return 0
    print("usage: deb.py build <dist> <out> <version>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
