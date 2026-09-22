"""``LabelingTool.exe --selftest=lite|full``: import-level smoke test for builds.

CI runs it on the packaged exe right after PyInstaller to catch modules and
data files missing from the bundle (the usual failure with torch / SAM). It
never shows a window. The windowed exe has no console, so the report is also
written to ``<app_home>/selftest.log``.
"""

from __future__ import annotations

import importlib
import importlib.util
import os

from labeling_tool.core.app_paths import app_home

COMMON_MODULES = (
    "numpy", "cv2", "skimage", "onnxruntime", "requests",
    "labeling_tool.ui.login_dialog",
    "labeling_tool.ui.fetch_dialog",
    "labeling_tool.ui.main_window",
)
FULL_MODULES = (
    "torch",
    "sam2.build_sam",
    "sam2.sam2_image_predictor",
    "annotation_tool.ui.main_window",
    "annotation_tool.segmenter.weights",
    "labeling_tool.ui.sam2_weights_dialog",
)

_qt_app = None  # keep the QApplication alive for the whole run


def _check_onnx() -> None:
    from labeling_tool.core.sam.predictor import default_model_paths, models_available
    if not models_available():
        raise FileNotFoundError(", ".join(str(p) for p in default_model_paths()))


def _check_login_dialog() -> None:
    """Qt platform plugins + stylesheet + login dialog construct offscreen."""
    global _qt_app
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from labeling_tool.core.window.styles import STYLESHEET
    from labeling_tool.ui.login_dialog import LoginDialog
    _qt_app = QApplication.instance() or QApplication(["selftest"])
    _qt_app.setStyleSheet(STYLESHEET)
    LoginDialog().deleteLater()


def _check_no_torch() -> None:
    if importlib.util.find_spec("torch") is not None:
        raise RuntimeError("torch is present in a lite build")


def _check_sam2_cfg() -> None:
    """Compose the SAM2.1 config through hydra exactly as build_sam2 does."""
    import sam2  # noqa: F401 - registers sam2's hydra config module
    from hydra import compose
    from annotation_tool import configs
    compose(config_name=configs.SAM2_MODEL_CFG)


def _check_backend() -> None:
    from annotation_tool import configs
    from labeling_tool.core.app_paths import is_frozen
    if is_frozen() and configs.BACKEND != "sam2":
        raise RuntimeError(f"exe backend is {configs.BACKEND!r}, expected 'sam2'")


def _checks(variant: str):
    """(name, callable) pairs; each callable raises on failure."""
    for mod in COMMON_MODULES:
        yield f"import {mod}", lambda mod=mod: importlib.import_module(mod)
    yield "MobileSAM ONNX models", _check_onnx
    yield "Qt login dialog (offscreen)", _check_login_dialog
    if variant == "lite":
        yield "torch not bundled", _check_no_torch
        return
    for mod in FULL_MODULES:
        yield f"import {mod}", lambda mod=mod: importlib.import_module(mod)
    yield "SAM2 hydra config composes", _check_sam2_cfg
    yield "exe backend is sam2", _check_backend


def run_selftest(variant: str) -> int:
    """Run every check; 0 = all passed, 1 = failures, 2 = unknown variant."""
    if variant not in ("lite", "full"):
        print(f"unknown selftest variant: {variant!r} (use lite or full)")
        return 2
    lines, failed = [f"selftest variant={variant} home={app_home()}"], 0
    for name, check in _checks(variant):
        try:
            check()
            lines.append(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            lines.append(f"FAIL {name}: {type(exc).__name__}: {exc}")
    lines.append("RESULT: " + ("PASS" if not failed else f"FAIL ({failed})"))
    report = "\n".join(lines) + "\n"
    print(report, end="")
    (app_home() / "selftest.log").write_text(report, encoding="utf-8")
    return 0 if not failed else 1
