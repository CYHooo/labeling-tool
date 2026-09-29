# PyInstaller spec for LM_LabelingTool (onedir, windowed).
# One variant only: the production tool plus the few-shot annotation tool
# (torch/SAM). The lite variant was dropped in v1.3.0 -- see
# docs/superpowers/specs/2026-09-28-ui-refresh-and-rebrand-design.md 2.1.
# Build from the repo root:  pyinstaller --noconfirm packaging/labeling_tool.spec
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def _not_tests_or_scripts(name):
    return ".tests" not in name and ".scripts" not in name


ICON = os.path.join(ROOT, "labeling_tool", "resources", "icon.ico")
datas = [(os.path.join(ROOT, "labeling_tool", "models", "sam", "*.onnx"),
          os.path.join("labeling_tool", "models", "sam")),
         # needed at runtime as well as in the exe's resources: the title bar
         # and taskbar icon come from QApplication.setWindowIcon, not from
         # the PE resource below
         (ICON, os.path.join("labeling_tool", "resources"))]
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
excludes = ["sam3", "triton", "timm"]

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
    name="LM_LabelingTool",
    console=False,
    upx=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LM_LabelingTool")
