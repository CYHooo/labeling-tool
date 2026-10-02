"""PyInstaller binary filters applied in packaging/labeling_tool.spec."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import bundle_filters  # noqa: E402


def test_a_top_level_copy_of_an_nvidia_library_is_dropped():
    # The v2.0.0 Linux runtime shipped libnccl.so.2 twice (2 x 240 MB):
    # libtorch_cuda.so's DT_RPATH ($ORIGIN/../../nvidia/nccl/lib) resolves
    # the nested copy before LD_LIBRARY_PATH ever reaches the top-level one.
    toc = [
        ("libnccl.so.2", "/venv/nvidia/nccl/lib/libnccl.so.2", "BINARY"),
        ("nvidia/nccl/lib/libnccl.so.2", "/venv/nvidia/nccl/lib/libnccl.so.2", "BINARY"),
        ("libcupti.so.12", "/venv/nvidia/cuda_cupti/lib/libcupti.so.12", "BINARY"),
        ("nvidia/cuda_cupti/lib/libcupti.so.12", "/venv/nvidia/cuda_cupti/lib/libcupti.so.12", "BINARY"),
    ]
    kept = [dest for dest, _, _ in bundle_filters.drop_toplevel_nvidia_duplicates(toc)]
    assert kept == ["nvidia/nccl/lib/libnccl.so.2", "nvidia/cuda_cupti/lib/libcupti.so.12"]


def test_anything_without_a_nested_nvidia_twin_is_kept():
    # Only exact top-level twins of nvidia/<pkg>/lib/ files go: a top-level
    # library with no nested copy is the only copy there is.
    toc = [
        ("libQt5Core.so.5", "/venv/PyQt5/Qt5/lib/libQt5Core.so.5", "BINARY"),
        ("PyQt5/Qt5/lib/libQt5Core.so.5", "/venv/PyQt5/Qt5/lib/libQt5Core.so.5", "BINARY"),
        ("libxcb-xinerama.so.0", "/usr/lib/x86_64-linux-gnu/libxcb-xinerama.so.0", "BINARY"),
        ("torch/lib/libtorch_cuda.so", "/venv/torch/lib/libtorch_cuda.so", "BINARY"),
    ]
    assert bundle_filters.drop_toplevel_nvidia_duplicates(toc) == toc


def test_windows_style_separators_are_understood():
    toc = [
        ("cudnn64_9.dll", "C:/venv/nvidia/cudnn/bin/cudnn64_9.dll", "BINARY"),
        ("nvidia\\cudnn\\bin\\cudnn64_9.dll", "C:/venv/nvidia/cudnn/bin/cudnn64_9.dll", "BINARY"),
    ]
    # Windows keeps CUDA DLLs under nvidia/<pkg>/bin, not lib: untouched, so
    # the Windows runtime layer (and its runtime id) cannot change.
    assert bundle_filters.drop_toplevel_nvidia_duplicates(toc) == toc


def test_the_spec_applies_the_filter():
    spec = (Path(__file__).resolve().parents[2] / "packaging" / "labeling_tool.spec").read_text(encoding="utf-8")
    assert "a.binaries = bundle_filters.drop_toplevel_nvidia_duplicates(a.binaries)" in spec
    # an actual import statement, not the comment warning against one
    import re
    assert re.search(r"^\s*from packaging import", spec, re.M) is None
