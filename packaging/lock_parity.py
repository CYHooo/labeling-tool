"""Keep the Windows and Linux build locks from drifting apart.

Two locks are unavoidable: PyInstaller's Windows-only build dependencies
cannot be installed on Linux, and vice versa. But once the files are
separate, upgrading a package on one side and forgetting the other makes
the two platforms differ in ways nobody decided on -- and the symptom
surfaces months later as a bug that reproduces on one platform only.

So every package present in both locks must pin the same version, every
package present in only one must be listed in PLATFORM_ONLY with a reason,
and the rare package that is legitimately pinned to different versions on
each platform (an upstream release split, not drift) must be listed in
VERSION_MAY_DIFFER with a reason. Enforced by
labeling_tool/tests/test_lock_parity.py.
"""

from __future__ import annotations

import re

_REQ = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*==\s*(\S+)\s*$")

# Packages that legitimately exist on one platform only. The key is the
# lowercased package name; the value says why, in enough detail to audit.
PLATFORM_ONLY: dict[str, str] = {
    "pefile": "PyInstaller reads PE headers only when building for Windows.",
    "pywin32-ctypes": "PyInstaller uses it for Windows version resources and "
                      "code signing; there is no Linux equivalent.",
    "colorama": "Only needed to translate ANSI escape codes for Windows "
                "terminals; Linux terminals already support ANSI natively.",
    "pyreadline3": "A readline reimplementation for Windows, which has no "
                   "native readline; Linux's CPython is built against the "
                   "system readline/libedit directly.",
    "triton": "Pulled in by torch's Linux cu124 wheel as the GPU kernel "
              "compiler; the Windows cu124 wheel bundles the equivalent "
              "functionality internally instead of depending on triton.",
    "nvidia-cublas-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                          "runtime as separate pip packages; the Windows "
                          "cu124 wheel bundles the same libraries inside "
                          "itself instead, so there is no package to pin.",
    "nvidia-cuda-cupti-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                              "runtime as separate pip packages; the Windows "
                              "cu124 wheel bundles the same libraries inside "
                              "itself instead, so there is no package to pin.",
    "nvidia-cuda-nvrtc-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                              "runtime as separate pip packages; the Windows "
                              "cu124 wheel bundles the same libraries inside "
                              "itself instead, so there is no package to pin.",
    "nvidia-cuda-runtime-cu12": "torch's Linux cu124 wheel depends on the "
                                "CUDA runtime as separate pip packages; the "
                                "Windows cu124 wheel bundles the same "
                                "libraries inside itself instead, so there "
                                "is no package to pin.",
    "nvidia-cudnn-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                         "runtime as separate pip packages; the Windows "
                         "cu124 wheel bundles the same libraries inside "
                         "itself instead, so there is no package to pin.",
    "nvidia-cufft-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                         "runtime as separate pip packages; the Windows "
                         "cu124 wheel bundles the same libraries inside "
                         "itself instead, so there is no package to pin.",
    "nvidia-curand-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                          "runtime as separate pip packages; the Windows "
                          "cu124 wheel bundles the same libraries inside "
                          "itself instead, so there is no package to pin.",
    "nvidia-cusolver-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                            "runtime as separate pip packages; the Windows "
                            "cu124 wheel bundles the same libraries inside "
                            "itself instead, so there is no package to pin.",
    "nvidia-cusparse-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                            "runtime as separate pip packages; the Windows "
                            "cu124 wheel bundles the same libraries inside "
                            "itself instead, so there is no package to pin.",
    "nvidia-nccl-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                        "runtime as separate pip packages; the Windows "
                        "cu124 wheel bundles the same libraries inside "
                        "itself instead, so there is no package to pin.",
    "nvidia-nvjitlink-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                             "runtime as separate pip packages; the Windows "
                             "cu124 wheel bundles the same libraries inside "
                             "itself instead, so there is no package to pin.",
    "nvidia-nvtx-cu12": "torch's Linux cu124 wheel depends on the CUDA "
                        "runtime as separate pip packages; the Windows "
                        "cu124 wheel bundles the same libraries inside "
                        "itself instead, so there is no package to pin.",
}

# Packages that are present on BOTH platforms but can never be pinned to the
# same version, because the upstream project ships separate version lines
# per platform rather than one version for both. The key is the lowercased
# package name; the value says why, in enough detail to audit.
VERSION_MAY_DIFFER: dict[str, str] = {
    "pyqt5-qt5": "PyPI's Windows wheels for this package stop at 5.15.2 "
                "while the Linux wheels continue to 5.15.19 and beyond; "
                "upstream publishes the two platforms on different version "
                "lines, so there is no shared version to pin to.",
}


def parse_lock(text: str) -> dict[str, str]:
    """{lowercased package name: pinned version} for every `name==version`."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _REQ.match(line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def compare(win_text: str, linux_text: str) -> list[str]:
    """Every parity violation between the two locks; empty means they agree."""
    win, linux = parse_lock(win_text), parse_lock(linux_text)
    problems: list[str] = []
    for name in sorted(set(win) & set(linux)):
        if win[name] != linux[name]:
            if name in VERSION_MAY_DIFFER:
                continue
            problems.append(
                f"{name}: windows pins {win[name]}, linux pins {linux[name]} "
                f"-- sync them, or the platforms differ")
    for name in sorted(set(win) ^ set(linux)):
        if name in PLATFORM_ONLY:
            continue
        side = "windows" if name in win else "linux"
        problems.append(
            f"{name}: only in the {side} lock and not declared in "
            f"lock_parity.PLATFORM_ONLY -- add it there with a reason, or "
            f"pin it on both sides")
    return problems
