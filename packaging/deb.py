"""Assemble the Linux deb from a PyInstaller onedir build.

This is `installer.iss`'s counterpart on Linux. It builds a plain binary deb
by hand (`dpkg-deb --build`) rather than going through `dpkg-buildpackage`:
`dpkg-buildpackage` is for SOURCE packages that Debian rebuilds from a
`debian/rules` recipe, and we have no source package to offer -- we are
shipping a PyInstaller binary tree, the exact analogue of the Windows exe.
`dpkg-deb` builds a binary .deb directly from a staged root plus a
`DEBIAN/control` file, which is all a binary distribution needs.

There is exactly one package per release. Incremental updates do not go
through dpkg at all: they are zips applied in place by
labeling_tool/update/patch.py. Those zips write files dpkg never recorded,
so the maintainer scripts below clean them up (preinst before a full
install, postrm on removal).

The deb filename must agree with labeling_tool.update.checker.full_asset_name;
labeling_tool/tests/test_deb.py asserts it.
"""

from __future__ import annotations

import hashlib
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

PACKAGE = "lm-labeling-tool"
ARCH = "amd64"

_DESKTOP_TEMPLATE = Path(__file__).resolve().parent / "linux" / \
    "lm-labeling-tool.desktop.in"

# Icon sizes PyInstaller collects into _internal/labeling_tool/resources/
# (see packaging/labeling_tool.spec's ICON_PNGS) -- the same four the
# hicolor icon theme expects a dedicated rendering for, rather than one
# large PNG the desktop environment rescales on the fly.
ICON_SIZES = (16, 32, 48, 256)

# Qt's xcb platform plugin links against these X libraries. PyInstaller
# collects most of them into the bundle (_internal/) when they are present at
# build time, but declaring them as well keeps the dynamic linker from
# ever falling back to a missing system copy: without them the package can
# install cleanly and the app dies at startup with "could not load the Qt
# platform plugin xcb".
#
# Installation goes through `dpkg -i`, which does NOT fetch from
# repositories, so this list must stay within what a desktop install of the
# supported Ubuntu releases already has. CI proves it: the smoke test must
# install without `apt-get install -f`. If something is genuinely needed and
# not present by default, bundle it in the deb (BUNDLED_LIBS below) instead
# of declaring it here.
RUNTIME_DEPENDS = (
    "libc6 (>= 2.35)",
    "libgl1",
    # Ubuntu 24.04 (noble) renamed this package to libglib2.0-0t64 as part
    # of its 64-bit time_t transition; 22.04 (jammy) still ships the old
    # name. The alternation covers both -- do not collapse it to one name,
    # that silently drops one of the two supported releases.
    "libglib2.0-0t64 | libglib2.0-0",
    "libxkbcommon-x11-0",
    "libxcb-icccm4",
    "libxcb-image0",
    "libxcb-keysyms1",
    "libxcb-randr0",
    "libxcb-render-util0",
    "libxcb-shape0",
    "libdbus-1-3",
)

# Needed by Qt's xcb platform plugin but NOT on a stock desktop, so they
# cannot be Depends (see above): ubuntu-desktop-minimal on 22.04 lacks
# libxcb-xinerama0, and dpkg -i refused the install (CI run 36842846563).
# The build installs them alongside RUNTIME_DEPENDS so PyInstaller collects
# them into the bundle the deb ships -- its exclude list only skips glibc, libGL,
# libdrm, libxcb itself and libxcb-dri*, none of which are listed here.
BUNDLED_LIBS = (
    "libxcb-xinerama0",
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

PREINST = """#!/bin/sh
set -e
# A full install replaces the whole tree. zip updates may have added
# app-layer files dpkg never recorded; clear them so none survive.
rm -rf /opt/lm-labeling-tool/_internal/labeling_tool \\
       /opt/lm-labeling-tool/_internal/annotation_tool \\
       /opt/lm-labeling-tool/.update-backup \\
       /opt/lm-labeling-tool/.update-staging \\
       /opt/lm-labeling-tool/.update-journal
"""

POSTRM = """#!/bin/sh
set -e
case "$1" in
    remove|purge)
        # zip updates write files outside dpkg's database; remove them too.
        rm -rf /opt/lm-labeling-tool
        ;;
esac
"""


# Every file besides "control" in DEBIAN/: build() writes exactly these, and
# reuse_deb.reusable() demands a previous deb carries exactly these.
MAINTAINER_SCRIPTS = {"postinst": POSTINST, "preinst": PREINST, "postrm": POSTRM}


def _control(fields: list[tuple[str, str]]) -> str:
    """Render a Debian control stanza in a fixed field order, LF-terminated.

    dpkg-deb rejects a control file whose last field has no trailing
    newline, so every field (including the last) ends with "\\n"."""
    return "".join(f"{key}: {value}\n" for key, value in fields)


# Files the deb installs outside /opt that the app-layer zip never updates
# (packaging/reuse_deb.py may only re-ship a previous deb when these match).
FINGERPRINT_FIELD = "X-LT-Extras-SHA256"
# Bump whenever build() / _stage_app_extras change WHAT they put outside
# /opt (a new file, a new path, a renamed entry): the fingerprint hashes the
# inputs it knows about, not this code, so this is how a change in the code
# itself stops a previous deb from being re-shipped.
LAYOUT_REVISION = 1
_ICON_SOURCE_DIR = Path(__file__).resolve().parents[1] / "labeling_tool" / "resources"


def extras_fingerprint() -> str:
    """SHA-256 over what _stage_app_extras puts outside /opt: the .desktop
    template and the icons. A previous deb whose fingerprint differs carries
    stale extras, so it cannot be re-shipped under a new version."""
    digest = hashlib.sha256(f"layout {LAYOUT_REVISION}\n".encode("utf-8"))
    for path in [_DESKTOP_TEMPLATE] + [_ICON_SOURCE_DIR / f"icon-{px}.png" for px in ICON_SIZES]:
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
    digest.update(f"{INSTALL_PREFIX}/{layers.app_entry_name(layers.LINUX)}".encode("utf-8"))
    return digest.hexdigest()


def control(version: str, installed_kb: int) -> str:
    """DEBIAN/control for the single package."""
    return _control([
        ("Package", PACKAGE),
        ("Version", version),
        ("Architecture", ARCH),
        ("Maintainer", MAINTAINER),
        ("Installed-Size", str(int(installed_kb))),
        ("Depends", ", ".join(RUNTIME_DEPENDS)),
        ("Section", "graphics"),
        ("Priority", "optional"),
        (FINGERPRINT_FIELD, extras_fingerprint()),
        ("Description", "LM Labeling Tool"),
    ])


def deb_filename(version: str) -> str:
    """Must agree with labeling_tool.update.checker.full_asset_name."""
    return f"{PACKAGE}_{version}_{ARCH}.deb"


def desktop_entry() -> str:
    """The .desktop file content. It carries no version: a reused deb
    (reuse_deb.py) keeps the previous release's copy, and the app's own
    version lives in build-info.json, which the update zip replaces."""
    return _DESKTOP_TEMPLATE.read_text(encoding="utf-8")


def _write_control_dir(root: Path, control: str, scripts: dict[str, str]) -> None:
    """Write DEBIAN/control plus each maintainer script, made executable."""
    debian = root / "DEBIAN"
    debian.mkdir(parents=True, exist_ok=True)
    (debian / "control").write_text(control, encoding="utf-8")
    for name, body in scripts.items():
        path = debian / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _stage_app_extras(dist_dir: Path, root: Path) -> None:
    """.desktop entry, icons and the /usr/bin symlink -- everything that
    references the installed executable."""
    applications = root / "usr" / "share" / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    (applications / f"{PACKAGE}.desktop").write_text(
        desktop_entry(), encoding="utf-8")

    icon_src_dir = dist_dir / "_internal" / "labeling_tool" / "resources"
    for px in ICON_SIZES:
        src = icon_src_dir / f"icon-{px}.png"
        if not src.is_file():
            continue
        icon_dir = root / "usr" / "share" / "icons" / "hicolor" / \
            f"{px}x{px}" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, icon_dir / f"{PACKAGE}.png")

    bin_dir = root / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / PACKAGE
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(f"{INSTALL_PREFIX}/{layers.app_entry_name(layers.LINUX)}")


def _dpkg_deb_build(root: Path, out_path: Path, fast: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["dpkg-deb", "--build", "--root-owner-group"]
    # Compression controlled the same way the Windows build picks its
    # compressor via /DMyFast=1: fast gzip for local iteration, xz for a
    # real release. dpkg-deb's xz is already multi-threaded across every
    # core on its own: measured on jammy's dpkg 1.21.1, it ignores XZ_OPT
    # (byte-identical output, same time) and has no --threads-max yet.
    # Level 9, not xz's default 6: -6 left the then-separate runtime deb at
    # 2,061,489,096 bytes, over the release asset ceiling (CI run
    # 36965987450); -9's 64 MB dictionary measured 8% smaller on the
    # torch + CUDA payload for ~37% more compression time.
    args += (["-Zgzip", "-z1"] if fast else ["-Zxz", "-z9"])
    args += [str(root), str(out_path)]
    subprocess.run(args, check=True)


def build(dist_dir: Path, out_dir: Path, version: str) -> Path:
    """Build the single deb: the whole PyInstaller onedir under /opt plus
    the desktop entry, icons and /usr/bin link."""
    dist_dir, out_dir = Path(dist_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fast = bool(os.environ.get("LT_FAST"))
    with tempfile.TemporaryDirectory(prefix="deb-stage-") as tmp:
        root = Path(tmp) / "pkg"
        target = root / INSTALL_PREFIX.lstrip("/")
        shutil.copytree(dist_dir, target, symlinks=True)
        _stage_app_extras(dist_dir, root)
        size_kb = max(1, sum(p.stat().st_size for p in target.rglob("*")
                             if p.is_file() and not p.is_symlink()) // 1024)
        _write_control_dir(root, control(version, size_kb), MAINTAINER_SCRIPTS)
        out = out_dir / deb_filename(version)
        _dpkg_deb_build(root, out, fast)
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 4 and args[0] == "build":
        print(f"deb: {build(Path(args[1]), Path(args[2]), args[3])}")
        return 0
    print("usage: deb.py build <dist> <out> <version>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
