"""Standalone offline labeling window: pick an image folder + a mask folder,
edit crack/spalling masks (brush/bbox/SAM/scale), save to an output folder.
No login/API/upload, no highlight/15cm derived masks."""

from __future__ import annotations

from pathlib import Path

from labeling_tool.core.window.main_window import MainWindow
from labeling_tool.session.local_pairing import pair_by_stem, mask_for_stem
from labeling_tool.logging_setup import vlog


class LocalMainWindow(MainWindow):
    def __init__(self, image_dir, mask_dir, output_dir):
        super().__init__()
        self.image_dir = Path(image_dir)
        self.mask_dir = Path(mask_dir)
        self.origin_dir = self.image_dir
        self.detected_dir = self.mask_dir
        self.output_dir = Path(output_dir)
        self.highlight_dir = None            # skip derived masks
        self.repair15_dir = None
        self.export_result_on_save = False   # skip Result/<stem>.png export
        self._init_sam()
        self._reload_data()

    def _init_sam(self) -> None:
        from labeling_tool.core.sam.predictor import MobileSamPredictor
        predictor = MobileSamPredictor.try_load()
        if predictor is not None:
            self.canvas.set_sam_predictor(predictor)
            return
        btn = getattr(self, "_btn_sam_toggle", None)
        if btn is not None:
            btn.setEnabled(False)
            btn.setToolTip(self.tr_("sam_unavailable"))

    # ----- folder/stem/.png convention (overrides core defaults) -----
    def _build_image_list(self) -> list[str]:
        pairs = pair_by_stem(self.image_dir, self.mask_dir)
        missing = [img for img, m in pairs if m is None]
        if missing:
            vlog().warning("skip %d image(s) with no mask: %s",
                           len(missing), missing[:5])
        return [img for img, m in pairs if m is not None]

    def _display_mask_path(self, filename: str) -> tuple[str | None, str]:
        stem = Path(filename).stem
        edited = self.output_dir / f"{stem}.png"          # already-edited wins
        if edited.exists():
            return str(edited), "labeling"
        m = mask_for_stem(self.mask_dir, stem)             # input mask
        return (str(m) if m else None), ("detected" if m else "none")

    def _save_mask_path(self, filename: str) -> Path:
        return self.output_dir / f"{Path(filename).stem}.png"
