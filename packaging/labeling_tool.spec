# PyInstaller spec for LabelingTool (onedir, windowed).
#   LT_VARIANT=lite  production tool only (no torch)          -> ~400 MB
#   LT_VARIANT=full  + few-shot annotation_tool (torch/SAM)   -> ~5 GB
# Build from the repo root:  pyinstaller --noconfirm packaging/labeling_tool.spec
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

VARIANT = os.environ.get("LT_VARIANT", "lite")
if VARIANT not in ("lite", "full"):
    raise SystemExit(f"LT_VARIANT must be lite or full, got {VARIANT!r}")

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def _not_tests_or_scripts(name):
    return ".tests" not in name and ".scripts" not in name


datas = [(os.path.join(ROOT, "labeling_tool", "models", "sam", "*.onnx"),
          os.path.join("labeling_tool", "models", "sam"))]
binaries = []
# labeling_tool imports several modules lazily inside functions
hiddenimports = collect_submodules("labeling_tool", filter=_not_tests_or_scripts)
excludes = []

if VARIANT == "full":
    hiddenimports += collect_submodules("annotation_tool", filter=_not_tests_or_scripts)
    # never ship a developer's classes.json; weights are downloaded on first use
    datas += collect_data_files("annotation_tool", excludes=["**/classes.json"])
    # sam2 builds models from hydra yaml configs resolved at runtime
    for pkg in ("sam2", "hydra", "omegaconf"):
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    excludes = ["sam3", "triton", "timm"]
else:
    excludes = ["torch", "torchvision", "torchaudio", "triton",
                "sam2", "sam3", "timm", "annotation_tool"]

a = Analysis(
    [os.path.join(ROOT, "labeling_tool", "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LabelingTool",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LabelingTool")
