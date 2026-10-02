"""Build the app-layer update zip a release publishes for each platform.

Input is `layers.py stage`'s output (only app-layer files); output is
update-v<ver>-<runtime>-<windows|linux>.zip with manifest.json, the format
labeling_tool/update/patch.py applies. Imported by bare name -- never as
`from packaging import ...`, which is pip's own library.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layers  # noqa: E402
from labeling_tool.update import checker, patch  # noqa: E402


def build_update_zip(app_layer_dir: Path, out_dir: Path, version: str,
                     runtime: str, platform: str) -> Path:
    src = Path(app_layer_dir)
    files: dict[str, str] = {}
    for path in sorted(src.rglob("*")):
        if path.is_file():
            rel = path.relative_to(src).as_posix()
            if not layers.is_app_layer(rel, platform):
                raise ValueError(f"not an app-layer file: {rel}")
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / checker.update_asset_name(version, runtime, platform)
    manifest = {"version": version, "runtime": runtime, "platform": platform, "files": files}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(patch.MANIFEST_NAME, json.dumps(manifest, indent=1))
        for rel in files:
            z.write(src / rel, rel)
    return zip_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 5 and args[4] in (layers.WINDOWS, layers.LINUX):
        print(build_update_zip(Path(args[0]), Path(args[1]), args[2], args[3], args[4]))
        return 0
    print("usage: update_zip.py <app-layer-dir> <out-dir> <version> <runtime> <win32|linux>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
