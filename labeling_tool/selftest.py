"""``LM_LabelingTool.exe --selftest=full``: import-level smoke test for builds.

CI runs it on the packaged exe right after PyInstaller to catch modules and
data files missing from the bundle (the usual failure with torch / SAM). It
never shows a window. The windowed exe has no console, so the report is also
written to ``<user_data_home>/selftest.log``.
"""

from __future__ import annotations

import faulthandler
import importlib
import importlib.util
import os

from labeling_tool.core.app_paths import user_data_home

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

# A healthy full run takes well under a minute. Past this, faulthandler
# writes every thread's traceback to selftest-hang.txt and exits, so a hang
# names its own cause instead of silently running into the CI job's limit
# (CI run 36856399327 hung 23 minutes without a single line of output).
HANG_SECONDS = 240


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


def _check_fewshot_available() -> None:
    from labeling_tool.ui.login_dialog import fewshot_available
    if not fewshot_available():
        raise RuntimeError("fewshot_available() is False in a full build")


def _checks(variant: str):
    """(name, callable) pairs; each callable raises on failure."""
    for mod in COMMON_MODULES:
        yield f"import {mod}", lambda mod=mod: importlib.import_module(mod)
    yield "MobileSAM ONNX models", _check_onnx
    yield "Qt login dialog (offscreen)", _check_login_dialog
    for mod in FULL_MODULES:
        yield f"import {mod}", lambda mod=mod: importlib.import_module(mod)
    yield "SAM2 hydra config composes", _check_sam2_cfg
    yield "exe backend is sam2", _check_backend
    yield "few-shot stack available", _check_fewshot_available


def run_selftest(variant: str) -> int:
    """Run every check; 0 = all passed, 1 = failures, 2 = unknown variant."""
    # On Linux, the default home is an XDG directory that may not exist yet
    # on a fresh install -- app_home() (beside the exe) never needed this
    # because the exe's own directory always exists.
    home = user_data_home()
    home.mkdir(parents=True, exist_ok=True)
    if variant != "full":
        message = f"unknown selftest variant: {variant!r} (use full)\n"
        print(message, end="")
        (home / "selftest.log").write_text(message, encoding="utf-8")
        return 2
    log = home / "selftest.log"
    lines, failed = [f"selftest variant={variant} home={home}"], 0
    hang_path = home / "selftest-hang.txt"
    with open(hang_path, "w", encoding="utf-8") as hang_file:
        faulthandler.dump_traceback_later(HANG_SECONDS, exit=True, file=hang_file)
        try:
            for name, check in _checks(variant):
                # Name the check BEFORE running it: a check that hangs never
                # returns, so only this line says which one it was.
                log.write_text("\n".join(lines + [f"RUN  {name}"]) + "\n", encoding="utf-8")
                try:
                    check()
                    lines.append(f"OK   {name}")
                except Exception as exc:  # noqa: BLE001 - report every failure, keep going
                    failed += 1
                    lines.append(f"FAIL {name}: {type(exc).__name__}: {exc}")
        finally:
            faulthandler.cancel_dump_traceback_later()
    # Reaching here means no hang: drop the empty file. On Windows this
    # directory is the bundle itself, and a leftover file joins the runtime
    # layer and moves the runtime id. A hang exits inside the block above,
    # so its traceback is never removed.
    hang_path.unlink()
    lines.append("RESULT: " + ("PASS" if not failed else f"FAIL ({failed})"))
    report = "\n".join(lines) + "\n"
    print(report, end="")
    log.write_text(report, encoding="utf-8")
    return 0 if not failed else 1
