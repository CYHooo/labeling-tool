"""Button icons: Lucide SVGs in labeling_tool/resources/icons, recolored to
the dark theme at load, shipped in the app layer (no runtime change)."""
import re
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from labeling_tool.ui import icons

_app = QApplication.instance() or QApplication([])
REPO = Path(__file__).resolve().parents[2]
ICON_DIR = REPO / "labeling_tool" / "resources" / "icons"


def _used_names():
    names = set()
    for path in (REPO / "labeling_tool").rglob("*.py"):
        if "tests" in path.parts:
            continue
        names |= set(re.findall(r"""icons\.(?:icon|pixmap)\(\s*["']([\w-]+)["']""", path.read_text(encoding="utf-8")))
    return names


def test_every_icon_the_code_asks_for_exists():
    used = _used_names()
    assert used, "no icon is used anywhere"
    missing = sorted(n for n in used if not (ICON_DIR / f"{n}.svg").is_file())
    assert not missing, missing


def _solid_colors(ic):
    img = ic.pixmap(24, 24).toImage()
    return [img.pixelColor(x, y) for x in range(24) for y in range(24) if img.pixelColor(x, y).alpha() > 200]


def _near(color, hex_):
    from PyQt5.QtGui import QColor
    ref = QColor(hex_)
    return all(abs(a - b) <= 2 for a, b in ((color.red(), ref.red()), (color.green(), ref.green()), (color.blue(), ref.blue())))


def test_an_icon_renders_in_the_theme_color():
    ic = icons.icon("download")
    assert not ic.isNull()
    colors = _solid_colors(ic)
    assert colors and all(_near(c, icons.THEME_COLOR) for c in colors)


def test_a_primary_icon_is_white():
    colors = _solid_colors(icons.icon("download", primary=True))
    assert colors and all(_near(c, "#ffffff") for c in colors)


def test_the_build_ships_the_icons_and_their_license():
    spec = (REPO / "packaging" / "labeling_tool.spec").read_text(encoding="utf-8")
    assert '"icons"' in spec and "*.svg" in spec
    assert (ICON_DIR / "LICENSE-lucide.txt").is_file()


def test_each_size_is_drawn_at_that_size_not_rescaled():
    """Lucide SVGs say width/height 24; drawing them at 24 and shrinking to
    16 with nearest-neighbour gave jagged edges. Each size renders natively."""
    for px in (16, 18, 24, 32):
        assert f'width="{px}"' in icons._svg("download", icons.THEME_COLOR, px).decode()
        assert icons._render("download", icons.THEME_COLOR, px).width() == px


def test_a_missing_icon_file_is_a_blank_icon_not_a_crash():
    ic = icons.icon("no-such-icon")      # a broken bundle must not crash a dialog
    pm = ic.pixmap(16, 16)
    assert pm.isNull() or pm.toImage().pixelColor(8, 8).alpha() == 0


def test_the_selftest_checks_that_svg_icons_render():
    from labeling_tool import selftest
    names = [name for name, _ in selftest._checks("full")]
    assert "SVG icons render" in names
    dict(selftest._checks("full"))["SVG icons render"]()        # passes here
