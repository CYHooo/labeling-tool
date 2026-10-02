"""The window icon.

PyInstaller's EXE(icon=) writes the .ico into the exe's PE resources, which
is what Windows shows for the FILE. The title bar and the taskbar button
come from Qt instead, and need QApplication.setWindowIcon -- without it the
running app shows Qt's default icon no matter what the exe looks like.
"""

import sys
from pathlib import Path

from PIL import Image
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from labeling_tool.core import app_paths

# packaging/make_icon.py's PNG_SIZES; kept in sync by hand (no runtime
# import of packaging/ from the shipped package).
PNG_SIZES = (16, 32, 48, 256)

_app = QApplication.instance() or QApplication([])


def test_icon_resource_ships_with_the_package():
    """Bundled next to the code, so the same path works from source and
    inside _internal/ after PyInstaller collects it."""
    icon = app_paths.resource_path("icon.ico")
    assert icon.is_file(), f"{icon} missing"
    assert icon.stat().st_size > 1024


def test_icon_loads_as_a_real_qicon():
    icon = QIcon(str(app_paths.resource_path("icon.ico")))
    assert not icon.isNull()
    # the sizes make_icon.py writes; a truncated .ico would lose the large ones
    have = {s.width() for s in icon.availableSizes()}
    assert {16, 32, 256} <= have, f"expected 16/32/256 among {sorted(have)}"


def test_main_sets_the_application_window_icon(monkeypatch):
    """Set on the QApplication, so every window -- login, fetch, labeling,
    few-shot -- inherits it without each one remembering to."""
    from labeling_tool import app as app_module

    captured = {}

    class _FakeApp:
        def __init__(self, argv):
            captured["argv"] = argv

        def setStyleSheet(self, *_a, **_k):
            pass

        def setWindowIcon(self, icon):
            captured["icon"] = icon

        def exec_(self):
            return 0

    class _FakeSignal:
        def connect(self, _slot):
            pass

    class _RejectingLogin:
        def __init__(self, *a, **k):
            self.fewshotRequested = _FakeSignal()

        def exec_(self):
            return 0

    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "LoginDialog", _RejectingLogin)
    monkeypatch.setattr(sys, "argv", ["LM_LabelingTool.exe"])

    app_module.main([])

    assert "icon" in captured, "main() never called setWindowIcon"
    assert not captured["icon"].isNull(), "the window icon loaded empty"
    # The icon must come from the multi-size PNGs, one addFile() per size:
    # an ICO here would be null on a Linux build whose Qt has no ICO plugin,
    # and a single generically-rescaled PNG would still pass a bare
    # isNull()/availableSizes() check while losing the hand-tuned small
    # renders -- so check every size app.py is expected to load is present.
    have = {s.width() for s in captured["icon"].availableSizes()}
    assert set(PNG_SIZES) <= have, f"expected {PNG_SIZES} among {sorted(have)}"


def test_png_icon_resources_ship_with_the_package():
    # Qt's ICO plugin is not guaranteed to be collected into the Linux
    # build, and the .desktop entry needs a bitmap regardless.
    for px in PNG_SIZES:
        png = app_paths.resource_path(f"icon-{px}.png")
        assert png.is_file(), f"{png} missing"
        assert png.stat().st_size > 100


def test_png_icons_load_as_real_qicons():
    for px in PNG_SIZES:
        icon = QIcon(str(app_paths.resource_path(f"icon-{px}.png")))
        assert not icon.isNull()
        have = {s.width() for s in icon.availableSizes()}
        assert px in have, f"expected a {px}px bitmap among {sorted(have)}"


def test_multi_size_icon_covers_every_declared_size():
    """The QIcon app.py builds (one addFile() per size) must expose every
    size, not just whichever one Qt picks as "the" available size for a
    single-file icon."""
    icon = QIcon()
    for px in PNG_SIZES:
        icon.addFile(str(app_paths.resource_path(f"icon-{px}.png")), QSize(px, px))
    have = {s.width() for s in icon.availableSizes()}
    assert set(PNG_SIZES) <= have, f"expected {PNG_SIZES} among {sorted(have)}"


def test_small_png_keeps_the_small_branch_tuning_not_a_256px_downscale():
    """packaging/make_icon.py's render() takes a SMALL branch (heavier
    stroke, bigger glyph, no underline) for px <= 32. If the shipped 16px
    PNG were ever produced by resizing the 256px render instead of calling
    render(16) directly, it would match a plain LANCZOS downscale of the
    256px image pixel-for-pixel. Assert it does NOT -- proving the SMALL
    branch actually ran -- and that it DOES match a direct render(16)."""
    import importlib.util

    make_icon_path = (
        Path(__file__).resolve().parents[2] / "packaging" / "make_icon.py"
    )
    spec = importlib.util.spec_from_file_location("make_icon", make_icon_path)
    make_icon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_icon)

    from PIL import ImageChops

    def max_channel_diff(first, second):
        diff = ImageChops.difference(first, second)
        return max(high for _, high in (band.getextrema() for band in diff.split()))

    shipped = Image.open(app_paths.resource_path("icon-16.png")).convert("RGBA")
    direct = make_icon.render(16).convert("RGBA")
    downscaled_from_256 = make_icon.render(256).resize((16, 16), Image.LANCZOS).convert("RGBA")

    assert shipped.size == direct.size
    # The DejaVu Sans Bold that render() reads differs between distro
    # releases (the Ubuntu 22.04 build container ships the 2016 revision, a
    # dev machine a newer one), which moves antialiased edge pixels by up to
    # ~33 levels. Compare with a tolerance well above that noise and well
    # below the ~175 levels separating a plain downscale.
    noise_tolerance = 64
    assert max_channel_diff(shipped, direct) <= noise_tolerance, (
        "shipped icon-16.png drifted from make_icon.render(16) beyond "
        "antialiasing noise"
    )
    assert max_channel_diff(shipped, downscaled_from_256) > noise_tolerance, (
        "shipped icon-16.png matches a plain downscale of the 256px render "
        "-- the SMALL-branch tuning was not applied"
    )
