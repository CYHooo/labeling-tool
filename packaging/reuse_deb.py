"""Re-ship the previous release's deb under a new version, without
recompressing it.

The deb's xz -9 payload is ~1.7 GB of torch + CUDA and takes ~16 of the
Linux job's ~28 minutes to compress. On a code-only release that payload is
the same as the previous release's (same runtime id, see reuse_full.py), so
only the small control member is rewritten -- its Version field -- and the
data member is copied byte for byte. New installs get the previous app code
and the update zip brings it up to date on first launch, exactly as the
reused Windows installer does.

Everything a deb carries besides /opt must still be current, or a reused
deb would install stale files the update zip never touches. reusable()
therefore demands that the control this code would write today -- Depends,
maintainer scripts and the fingerprint of the .desktop entry and icons
(deb.extras_fingerprint) -- matches the old one in all but Version.

A deb is an ar archive: debian-binary, control.tar.<xz|gz>, data.tar.<...>.

Called by CI (.github/workflows/release.yml).
"""

from __future__ import annotations

import gzip
import io
import lzma
import re
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deb  # noqa: E402

FINGERPRINT_FIELD = deb.FINGERPRINT_FIELD
_AR_MAGIC = b"!<arch>\n"
_HEADER = 60


def _iter_ar(f):
    """(name, raw header, data offset, size) for each member of an open ar file."""
    if f.read(len(_AR_MAGIC)) != _AR_MAGIC:
        raise ValueError("not an ar archive (not a deb)")
    while True:
        header = f.read(_HEADER)
        if not header:
            return
        if len(header) != _HEADER or header[58:60] != b"`\n":
            raise ValueError("corrupt ar member header")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        offset = f.tell()
        yield name, header, offset, size
        f.seek(offset + size + (size % 2))


def _read_ar(blob: bytes) -> list[tuple[str, bytes]]:
    """Every member of an ar archive held in memory (tests, small debs)."""
    f = io.BytesIO(blob)
    return [(name, blob[off:off + size]) for name, _, off, size in list(_iter_ar(f))]


def _decompress(name: str, blob: bytes) -> bytes:
    if name.endswith(".xz"):
        return lzma.decompress(blob)
    if name.endswith(".gz"):
        return gzip.decompress(blob)
    if name.endswith(".tar"):
        return blob
    raise ValueError(f"unsupported control compression: {name}")


def _compress(name: str, raw: bytes) -> bytes:
    if name.endswith(".xz"):
        return lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64)
    if name.endswith(".gz"):
        return gzip.compress(raw, mtime=0)
    return raw


def _control_member(deb_path: Path) -> tuple[str, bytes]:
    with open(deb_path, "rb") as f:
        for name, _, off, size in _iter_ar(f):
            if name.startswith("control.tar"):
                f.seek(off)
                return name, f.read(size)
    raise ValueError(f"{deb_path} has no control member")


def _control_files(deb_path: Path) -> dict[str, str]:
    """The control file and maintainer scripts, by base name."""
    name, blob = _control_member(deb_path)
    out = {}
    with tarfile.open(fileobj=io.BytesIO(_decompress(name, blob))) as tar:
        for info in tar.getmembers():
            if info.isfile():
                out[Path(info.name).name] = tar.extractfile(info).read().decode("utf-8")
    return out


def _fields(control: str) -> dict[str, str]:
    out = {}
    for line in control.splitlines():
        if line and not line[0].isspace() and ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _restamped_control(control: str, version: str, drop_fields=()) -> str:
    text = re.sub(r"(?m)^Version:.*$", f"Version: {version}", control, count=1)
    for field in drop_fields:
        text = re.sub(rf"(?m)^{re.escape(field)}:.*\n", "", text)
    return text


def reusable(deb_path: Path, version: str) -> bool:
    """True when restamping deb_path to `version` gives exactly the control
    and maintainer scripts deb.build would write today."""
    files = _control_files(Path(deb_path))
    control = files.get("control", "")
    fields = _fields(control)
    if FINGERPRINT_FIELD not in fields or not fields.get("Installed-Size", "").isdigit():
        return False
    expected = deb.control(version, int(fields["Installed-Size"]))
    if _restamped_control(control, version) != expected:
        return False
    scripts = {"postinst": deb.POSTINST, "preinst": deb.PREINST, "postrm": deb.POSTRM}
    return all(files.get(name) == body for name, body in scripts.items())


def _rewrite_control_tar(name: str, blob: bytes, version: str, drop_fields) -> bytes:
    src = tarfile.open(fileobj=io.BytesIO(_decompress(name, blob)))
    buf = io.BytesIO()
    with src, tarfile.open(fileobj=buf, mode="w", format=src.format) as dst:
        for info in src.getmembers():
            if info.isfile():
                data = src.extractfile(info).read()
                if Path(info.name).name == "control":
                    data = _restamped_control(data.decode("utf-8"), version, drop_fields).encode("utf-8")
                info = _copy_info(info, len(data))
                dst.addfile(info, io.BytesIO(data))
            else:
                dst.addfile(info)
    return _compress(name, buf.getvalue())


def _copy_info(info: tarfile.TarInfo, size: int) -> tarfile.TarInfo:
    new = tarfile.TarInfo(info.name)
    for attr in ("mode", "uid", "gid", "uname", "gname", "mtime", "type", "linkname"):
        setattr(new, attr, getattr(info, attr))
    new.size = size
    return new


def restamp(src: Path, dst: Path, version: str, drop_fields=()) -> Path:
    """Write dst: src with Version set to `version` in its control member;
    every other member is copied byte for byte (streamed, not loaded)."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    with open(src, "rb") as f, open(tmp, "wb") as out:
        out.write(_AR_MAGIC)
        for name, header, off, size in list(_iter_ar(f)):
            f.seek(off)
            if name.startswith("control.tar"):
                body = _rewrite_control_tar(name, f.read(size), version, drop_fields)
                out.write(header[:48] + f"{len(body):<10}".encode("ascii") + header[58:])
                out.write(body)
                size = len(body)
            else:
                out.write(header)
                remaining = size
                while remaining:
                    chunk = f.read(min(remaining, 1 << 20))
                    if not chunk:
                        raise ValueError(f"{src} is truncated in member {name}")
                    out.write(chunk)
                    remaining -= len(chunk)
            if size % 2:
                out.write(b"\n")
    tmp.replace(dst)
    return dst


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 4 and args[0] == "restamp":
        src, dst, version = Path(args[1]), Path(args[2]), args[3]
        if not reusable(src, version):
            print(f"{src.name}: control, maintainer scripts or desktop/icon extras "
                  "differ from this build -- full build needed", file=sys.stderr)
            return 3
        restamp(src, dst, version)
        print(dst)
        return 0
    print("usage: reuse_deb.py restamp <previous.deb> <out.deb> <version>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
