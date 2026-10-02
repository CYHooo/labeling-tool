"""Filters applied to PyInstaller's binary list in labeling_tool.spec.

Kept out of the spec so they can be unit-tested
(labeling_tool/tests/test_bundle_filters.py). Import this module by putting
packaging/ on sys.path, never as ``from packaging import ...`` -- that name
is pip's own library.
"""
from __future__ import annotations


def _parts(dest: str) -> list[str]:
    return dest.replace("\\", "/").split("/")


def drop_toplevel_nvidia_duplicates(binaries):
    """Drop top-level copies of libraries PyInstaller also keeps under
    ``nvidia/<package>/lib/``.

    On Linux, torch's CUDA libraries carry a DT_RPATH of
    ``$ORIGIN/../../nvidia/<package>/lib``, which the dynamic linker searches
    BEFORE ``LD_LIBRARY_PATH`` (where the PyInstaller bootloader puts the
    top level). The nested copy is therefore the one that loads, and the
    top-level twin is dead weight -- 240 MB for libnccl.so.2 alone in the
    v2.0.0 runtime deb. Windows keeps its CUDA DLLs under ``nvidia/*/bin``,
    so nothing there matches and the Windows runtime layer is unchanged.
    """
    nested = {
        parts[-1]
        for dest, _src, _kind in binaries
        if len(parts := _parts(dest)) == 4 and parts[0] == "nvidia" and parts[2] == "lib"
    }
    return [entry for entry in binaries
            if not (len(_parts(entry[0])) == 1 and entry[0] in nested)]
