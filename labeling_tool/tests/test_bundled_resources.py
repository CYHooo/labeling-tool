"""Where read-only bundled resources live in a frozen build.

The app-layer installer clears _internal/labeling_tool wholesale -- that is
how stale .pyc files from deleted modules get cleaned up. Anything shipping
in the RUNTIME layer must therefore live BESIDE that package, not inside it,
or the app package deletes a file it does not carry and cannot restore.
CI run 36670089766 caught exactly that: the ONNX models vanished after an
app-layer install.
"""

from pathlib import Path

from labeling_tool.core import app_paths


def test_bundled_path_from_source_stays_in_the_package(monkeypatch):
    monkeypatch.setattr(app_paths, "is_frozen", lambda: False)
    p = app_paths.bundled_path("models", "sam")
    assert p == app_paths.REPO_ROOT / "labeling_tool" / "models" / "sam"
    assert p.is_dir(), "the checked-in models directory should exist"


def test_bundled_path_when_frozen_sits_outside_labeling_tool(monkeypatch):
    """_MEIPASS is _internal/ in a PyInstaller onedir build, so this lands
    at _internal/models/sam -- a sibling of _internal/labeling_tool, safe
    from the app package's InstallDelete."""
    import sys
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\app\_internal", raising=False)
    p = app_paths.bundled_path("models", "sam")
    assert p == Path(r"C:\app\_internal") / "models" / "sam"
    assert "labeling_tool" not in str(p)


def test_onnx_paths_use_the_bundled_location(monkeypatch):
    import sys
    from labeling_tool.core.sam import predictor
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\app\_internal", raising=False)
    enc, dec = predictor.default_model_paths()
    assert enc.parent == Path(r"C:\app\_internal") / "models" / "sam"
    assert enc.name == "mobile_sam_encoder.onnx"
    assert dec.name == "mobile_sam_decoder.onnx"


def test_onnx_from_source_still_resolves(monkeypatch):
    """Source runs keep the repo layout: labeling_tool/models/sam/."""
    from labeling_tool.core.sam import predictor
    monkeypatch.setattr(app_paths, "is_frozen", lambda: False)
    enc, dec = predictor.default_model_paths()
    assert enc.is_file() and dec.is_file()


def test_frozen_models_are_runtime_layer():
    """The whole point of the move: at its frozen path, the model is not
    app layer, so the app package neither ships nor deletes it."""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
    import layers
    assert not layers.is_app_layer("_internal/models/sam/mobile_sam_encoder.onnx")
    assert layers.is_app_layer("_internal/labeling_tool/core/sam/predictor.pyc")


def test_nothing_runtime_layer_lives_under_the_cleared_directory():
    """The invariant this whole file exists for.

    A zip update moves every installed file under _internal/labeling_tool/
    that the zip does not carry into the backup, so EVERY path under it must
    be app layer -- otherwise the first update deletes something it cannot
    restore. Broken once already: the
    ONNX models were runtime layer while still sitting in that directory
    (CI run 36670089766).
    """
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
    import layers

    cleared = "_internal/labeling_tool/"
    # Anything the layer rules would put in the runtime layer must not be
    # reachable under the cleared prefix.
    for excluded in layers.APP_LAYER_EXCLUSIONS:
        assert not excluded.startswith(cleared), (
            f"{excluded} is excluded from the app layer but sits under "
            f"{cleared}, which the app installer wipes")
