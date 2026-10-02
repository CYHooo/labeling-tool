# PyInstaller spec for LM_LabelingTool (onedir, windowed).
# One variant only: the production tool plus the few-shot annotation tool
# (torch/SAM). The lite variant was dropped in v1.3.0 -- see
# docs/superpowers/specs/2026-09-28-ui-refresh-and-rebrand-design.md 2.1.
# Build from the repo root:  pyinstaller --noconfirm packaging/labeling_tool.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# packaging/ itself, for bundle_filters -- imported by bare name, never as
# "from packaging import ...", which is pip's own library.
sys.path.insert(0, SPECPATH)
import bundle_filters  # noqa: E402

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def _not_tests_or_scripts(name):
    return ".tests" not in name and ".scripts" not in name


ICON = os.path.join(ROOT, "labeling_tool", "resources", "icon.ico")
# One PNG per size app.py's QIcon.addFile() loop loads (16/32/48/256) -- see
# packaging/make_icon.py's PNG_SIZES. A single 256px file would make Qt
# rescale it generically for the taskbar/title bar, losing the hand-tuned
# small-size renders make_icon.py produces.
ICON_PNGS = [os.path.join(ROOT, "labeling_tool", "resources", f"icon-{px}.png")
             for px in (16, 32, 48, 256)]
# The ONNX models go BESIDE labeling_tool/, not inside it: they ship in the
# runtime layer, and the app-layer installer clears _internal\labeling_tool
# wholesale to drop stale bytecode. Inside, they would be deleted by a
# package that does not carry them (CI run 36670089766).
datas = [(os.path.join(ROOT, "labeling_tool", "models", "sam", "*.onnx"),
          os.path.join("models", "sam"))]
# needed at runtime as well as in the exe's resources: the title bar
# and taskbar icon come from QApplication.setWindowIcon, not from
# the PE resource below. PNGs are used on both platforms; the .ico
# remains only for the Windows executable's own resource.
datas += [(png, os.path.join("labeling_tool", "resources")) for png in ICON_PNGS]
binaries = []
# labeling_tool imports several modules lazily inside functions
hiddenimports = collect_submodules("labeling_tool", filter=_not_tests_or_scripts)
excludes = []

hiddenimports += collect_submodules("annotation_tool", filter=_not_tests_or_scripts)
# never ship a developer's classes.json; weights are downloaded on first use
datas += collect_data_files("annotation_tool", excludes=["**/classes.json"])
# sam2 builds models from hydra yaml configs resolved at runtime
for pkg in ("sam2", "hydra", "omegaconf"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
# nccl is multi-GPU collective communication and cupti is the CUDA
# profiler: neither is reachable from single-card inference, and together
# they are 283 MB unpacked. These excludes only drop them on WINDOWS: on
# Linux libtorch_cuda.so links libnccl.so.2 (DT_NEEDED), so PyInstaller's
# binary analysis brings both back -- twice, see the filter below. Everything else under nvidia/ stays -- cudnn and
# cublas are required, and the rest cannot be verified without a GPU, which
# CI does not have.
excludes = ["sam3", "triton", "timm", "nvidia.nccl", "nvidia.cuda_cupti"]

a = Analysis(
    [os.path.join(ROOT, "labeling_tool", "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    # noarchive=True writes pure-Python modules as .pyc files under
    # _internal/<package>/ instead of packing them into the exe's PYZ. That
    # is what puts torch/PyQt5/numpy bytecode in the RUNTIME layer: with the
    # PYZ, all of it rode inside the exe and every code change shipped ~38 MB
    # of unchanged third-party bytecode.
    noarchive=True,
)
# Linux: torch's CUDA libraries also land at the top level next to their
# nvidia/<pkg>/lib/ originals; DT_RPATH loads the nested ones first, so the
# top-level twins are dead weight (2 x 240 MB of NCCL in v2.0.0). A no-op on
# Windows, whose CUDA DLLs live under nvidia/<pkg>/bin.
a.binaries = bundle_filters.drop_toplevel_nvidia_duplicates(a.binaries)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LM_LabelingTool",
    console=False,
    upx=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LM_LabelingTool")
