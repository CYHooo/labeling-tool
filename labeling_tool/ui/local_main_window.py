"""Standalone offline labeling window: pick an image folder + a mask folder
IN the GUI (no startup dialog), edit crack/spalling masks (brush/bbox/SAM/scale),
save to an output folder. No login/API/upload, no highlight/15cm derived masks.

Folder selection reuses the core window's own "select folder" buttons:
origin_dir = image folder, detected_dir = mask folder. Output is a Labeling/
folder beside the image folder (non-destructive). Masks pair by stem (<name>.png).
"""

from __future__ import annotations

from pathlib import Path

from labeling_tool.core.window.main_window import MainWindow
from labeling_tool.core.constants import OUTPUT_DIR_NAME
from labeling_tool.session.local_pairing import pair_by_stem, mask_for_stem
from labeling_tool.logging_setup import vlog


class LocalMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        # Clean start: no auto-loaded ./Origin — the user picks folders in-GUI.
        self.origin_dir = None
        self.detected_dir = None
        self._sync_output_dir()              # output/derived -> None
        self.export_result_on_save = False   # skip Result/<stem>.png export
        self.canvas.show_repair15 = False    # no 15cm overlay
        # Relabel the folder buttons for image/mask; hide highlight/15cm toggles.
        if getattr(self, "_btn_select_origin", None) is not None:
            self._btn_select_origin.setText("이미지 폴더")
        if getattr(self, "_btn_select_detected", None) is not None:
            self._btn_select_detected.setText("마스크 폴더")
        for name in ("_btn_show_highlight", "_btn_show_repair15"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setChecked(False)
                btn.hide()
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

    # ----- output beside the image folder; no derived dirs -----
    def _sync_output_dir(self) -> None:
        self.output_dir = (self.origin_dir.parent / OUTPUT_DIR_NAME
                           if self.origin_dir is not None else None)
        self.result_dir = None
        self.highlight_dir = None
        self.repair15_dir = None

    def _load_data(self) -> None:
        # Only load once BOTH folders are chosen. Otherwise skip — the base
        # _load_data pops a MODAL "no images" warning on an empty list, which
        # would block at startup / on picking just one folder.
        if self.origin_dir is not None and self.detected_dir is not None:
            super()._load_data()

    # ----- folder/stem/.png convention (overrides core defaults) -----
    def _build_image_list(self) -> list[str]:
        if self.origin_dir is None or self.detected_dir is None:
            return []                         # need both folders picked
        pairs = pair_by_stem(self.origin_dir, self.detected_dir)
        missing = [img for img, m in pairs if m is None]
        if missing:
            vlog().warning("skip %d image(s) with no mask: %s",
                           len(missing), missing[:5])
        return [img for img, m in pairs if m is not None]

    def _display_mask_path(self, filename: str) -> tuple[str | None, str]:
        stem = Path(filename).stem
        if self.output_dir is not None:
            edited = self.output_dir / f"{stem}.png"      # already-edited wins
            if edited.exists():
                return str(edited), "labeling"
        m = mask_for_stem(self.detected_dir, stem) if self.detected_dir else None
        return (str(m) if m else None), ("detected" if m else "none")

    def _save_mask_path(self, filename: str) -> Path:
        return self.output_dir / f"{Path(filename).stem}.png"

    # ----- highlight/15cm fully disabled in the standalone -----
    def _dispatch_derived(self, filename, crack, spall, scale) -> None:
        return          # never generate highlight/repair15

    def _maybe_auto_bbox(self, token: str) -> None:
        return          # no 15cm-contour auto-bbox

    def _has_labeling_file(self, filename: str) -> bool:
        return (self.output_dir is not None
                and self._save_mask_path(filename).exists())
