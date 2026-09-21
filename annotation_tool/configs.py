"""Central configuration: paths, classes, priority, colors, backend switch."""
from pathlib import Path

# --- dataset paths (override at runtime via MainWindow "open folder") ---
# Only used as the "Open Folder" dialog's starting point (no auto-load on launch).
DEFAULT_DATASET_DIR = Path("./dataset")
IMAGES_SUBDIR = "images"
MASKS_SUBDIR = "masks"
OVERLAYS_SUBDIR = "verify_overlays"

# --- class definition: pixel value -> name ---
# These are FACTORY DEFAULTS only. At runtime classes come from
# core.class_registry.ClassRegistry, persisted to CLASSES_FILE; classes added /
# renamed / recolored / re-prioritized in the UI are stored there. Delete that
# file to reset to these defaults.
CLASSES = {1: "joint", 2: "concrete", 3: "scalebar", 4: "shoe", 5: "distractor"}
CLASS_IDS = [1, 2, 3, 4, 5]

# export priority, low -> high (later writes overwrite earlier ones)
EXPORT_ORDER = [2, 1, 3, 5, 4]  # concrete < joint < scalebar < distractor < shoe (shoe on top)

# global, user-editable class definitions (shared by all datasets)
CLASSES_FILE = Path(__file__).parent / "classes.json"

# RGB colors per class value (for overlay + canvas highlight)
CLASS_COLORS = {
    1: (255, 0, 0),    # joint  -> red
    2: (0, 200, 0),    # concrete -> green
    3: (0, 80, 255),   # scalebar -> blue
    4: (230, 60, 220), # shoe -> magenta
    5: (0, 128, 220),  # distractor -> sky blue
}
OVERLAY_ALPHA = 0.45

# --- SAM backend ---
BACKEND = "sam3"  # "sam3" (main) | "sam2" (zero-download fallback)
SAM2_CHECKPOINT = "./checkpoint/sam2.1_hiera_base_plus.pt"
SAM2_MODEL_CFG = "configs/sam2.1/sam2.1_hiera_b+.yaml"
SAM3_HF_REPO = "facebook/sam3"
# Local SAM3 checkpoint copied out of the HF cache; when present it is loaded
# directly (no network / HF auth needed). Falls back to HF download if missing.
SAM3_CHECKPOINT = "./checkpoint/sam3.pt"
# SAM3's pip wheel omits the CLIP-style BPE vocab it expects; ship our own copy
SAM3_BPE_PATH = str(Path(__file__).parent / "assets" / "bpe_simple_vocab_16e6.txt.gz")

UNDO_DEPTH = 30
EXPORT_OVERLAY = True
