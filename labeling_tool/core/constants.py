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

# Integer class labels for single-channel mask storage (0 = background).
# Single source of truth — append future classes here (e.g. {"...": 3}).
BACKGROUND_LABEL: int = 0
CLASS_LABELS: dict[str, int] = {"crack": 1, "spalling": 2}
LABEL_TO_CLASS: dict[int, str] = {v: k for k, v in CLASS_LABELS.items()}
