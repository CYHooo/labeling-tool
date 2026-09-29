"""Render labeling_tool/resources/icon.ico from the LM letter mark.

Kept as a script rather than a one-off command so the icon can be rebuilt
identically later. Drawn directly with Pillow: no SVG rasteriser is
installed in this project's environment, and adding one (cairosvg,
librsvg) for a mark this simple is not worth the dependency.
labeling_tool/resources/icon.svg is the vector reference for a designer;
THIS file is what actually produces the shipped .ico. The .ico lives in the
package rather than in packaging/ because it is needed at RUNTIME too:
PyInstaller's EXE(icon=) only writes the exe's PE resource, while the title
bar and taskbar come from QApplication.setWindowIcon.

Small sizes get a heavier stroke, a larger glyph and a thicker underline:
at 16px the 64px proportions turn into mush in the taskbar.

Run from the repo root:  .venv/bin/python packaging/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BG = (27, 31, 37, 255)        # #1b1f25
ACCENT = (45, 108, 223, 255)  # #2d6cdf
TEXT = (232, 236, 242, 255)   # #e8ecf2
SIZES = (16, 24, 32, 48, 64, 128, 256)
# Below this, detail is noise: fatter stroke, bigger letters, no underline.
SMALL = 32


def render(px: int) -> Image.Image:
    # Draw at 8x and downsample: Pillow has no antialiased vector drawing,
    # so supersampling is what keeps the rounded corners clean.
    scale = 8
    n = px * scale
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    small = px <= SMALL

    inset = int(n * (0.015 if small else 0.031))
    radius = int(n * 0.203)
    stroke = max(1, int(n * (0.047 if small else 0.031)))
    d.rounded_rectangle([inset, inset, n - inset - 1, n - inset - 1],
                        radius=radius, fill=BG, outline=ACCENT, width=stroke)

    glyph = int(n * (0.38 if small else 0.36))
    font = ImageFont.truetype(FONT, glyph)
    # Letter-spacing, drawn per glyph: at 16px the two letters otherwise
    # touch and M's middle vertex fills in, turning LM into a grey blob.
    gap = int(n * (0.05 if small else 0.02))
    widths = [d.textlength(c, font=font) for c in "LM"]
    total = sum(widths) + gap
    # Centre on the ink box, not the font's line box: the latter includes
    # ascender space the letters do not use and pushes LM low.
    box = d.textbbox((0, 0), "LM", font=font)
    cy = n * (0.50 if small else 0.44)
    x = n / 2 - total / 2
    y = cy - (box[1] + box[3]) / 2
    for c, w in zip("LM", widths):
        d.text((x, y), c, font=font, fill=TEXT)
        x += w + gap

    if not small:
        bar_w, bar_h = int(n * 0.41), max(1, int(n * 0.047))
        bar_y = int(n * 0.69)
        d.rounded_rectangle([(n - bar_w) // 2, bar_y,
                             (n + bar_w) // 2, bar_y + bar_h],
                            radius=bar_h // 2, fill=ACCENT)

    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "labeling_tool" / "resources" / "icon.ico"
    imgs = [render(px) for px in SIZES]
    # The base image caps the sizes Pillow will write: anything larger than
    # it is silently skipped (IcoImagePlugin._save). Hand it the largest and
    # append the rest, so every size keeps the drawing made for it rather
    # than a downscale of the 256px one.
    largest = imgs[-1]
    largest.save(out, format="ICO",
                 sizes=[(i.width, i.height) for i in imgs],
                 append_images=imgs[:-1])
    print(f"wrote {out} with sizes {list(SIZES)}")


if __name__ == "__main__":
    main()
