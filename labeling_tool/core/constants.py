"""Project-wide constants for the labeling tool."""

CATEGORIES: tuple[str, ...] = ("crack", "spalling")
DEFAULT_CATEGORY: str = "crack"

BRUSH_DEFAULT_SIZE: int = 10
BRUSH_MAX_SIZE: int = 300
OUTPUT_DIR_NAME: str = "Labeling"   # Auto-created next to Origin/

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# Mask name suffixes to strip when deriving the stem
MASK_NAME_SUFFIXES: tuple[str, ...] = (
    "_mask", "_crack", "_spalling", "_detected", "_overlap", "_result",
)
