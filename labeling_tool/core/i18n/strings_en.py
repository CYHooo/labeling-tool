# Terminology: docs/i18n-glossary.md
"""English UI strings."""

STRINGS = {
    # --- main window ---
    "window_title":       "Mask Editing Annotation Tool",
    "settings":           "Settings",
    "language":           "Language",
    "btn_select_origin":  "Select Origin Folder",
    "btn_select_detected":"Select Detected Folder",
    "lbl_origin":         "Origin: {p}",
    "lbl_detected":       "Detected: {p}",
    "lbl_output":         "Output (auto): {p}",
    "no_path":            "(not selected)",
    "lbl_category":       "Category:",
    "cat_crack":          "Crack",
    "cat_spalling":       "Spalling",
    "group_brush":        "Brush Annotation",
    "btn_brush_on":       "Enter Brush Mode",
    "btn_brush_off":      "Exit Brush Mode",
    "btn_brush_reset":    "Reset to Loaded Mask",
    "btn_brush_save":     "Save Mask",
    "lbl_brush_size":     "Brush size (px):",
    "btn_fine_annotation": "Fine annotation (keep width)",
    "brush_hint":
        "Left drag    Paint (writes current category channel)\n"
        "Right drag   Erase (current category only)\n"
        "Ctrl+drag    Pan view\n"
        "Wheel        Zoom\n"
        "Auto-saves to Labeling/<mask name> on image switch\n"
        "  R = crack, G = spalling",
    "brush_saved":        "Mask saved -> {p}",
    "brush_no_image":     "No image loaded",
    "brush_reset":        "Mask reset to loaded mask",
    "group_list":         "Image List",
    "group_nav":          "Navigation",
    "group_hint":         "Help / Usage",
    "btn_prev":           "<- Previous  [A]",
    "btn_next":           "Next  [D] ->",
    "btn_save":           "Save Current  [S]",
    "hint_text":
        "Brush   L-drag paint · R-drag erase · 1/2 crack/spalling\n"
        "        B toggle · [ / ] size · R=crack G=spalling\n"
        "BBox    click add point · Enter commit · Esc cancel · Del delete\n"
        "Measure click the two ends of a known-length reference\n"
        "View    Ctrl+drag pan · wheel zoom\n"
        "Nav     A / D prev/next · S save · auto-save on switch",
    "ready":              "Ready",
    "loaded_n_images":    "Loaded {n} images",
    "dlg_origin":         "Select Origin Image Folder",
    "dlg_detected":       "Select Detected Mask Folder",
    "dlg_output":         "Select Output Mask Folder",
    "warn_select_first":  "Please select Origin and Detected folders first",
    "warn_title":         "Warning",
    "warn_no_images":     "No image files in {dir}/.",
    "err_no_origin_title":"Error",
    "err_no_origin_msg":  "Origin folder not found.",
    "status_template":    "{i}/{n}: {f}  |  edited: {edited}",
    "group_bbox":            "BBox Annotation",
    "btn_bbox_on":           "Enter BBox Mode",
    "btn_bbox_off":          "Exit BBox Mode",
    "group_scale":           "Scale (px/cm)",
    "lbl_scale_template":    "Scale: {scale} mm/px ({source})",
    "scale_source_aruco":    "ArUco (auto)",
    "scale_source_fallback": "fallback",
    "scale_source_manual":   "manual",
    "scale_source_none":     "none",
    "scale_source_server":   "server (PPM)",
    "btn_measure":           "Manual Measure (fallback)",
    "btn_measure_cancel":    "Cancel Measurement",
    "measure_dialog_title":  "Manual Scale",
    "measure_dialog_label":  "Real length of the measured segment (cm):",
    "measure_hint":          "Click the two ends of a known-length reference (default 7 cm marker side)",
    "measure_done":          "Manual scale set: {scale} mm/px",
    "bbox_hint":
        "Click   Add point\n"
        "Enter   Commit (>=2 clicks)\n"
        "Esc     Cancel in-progress / deselect\n"
        "Del     Delete selected box",
    "bbox_need_more_clicks": "Need at least 2 clicks",
    "bbox_no_scale":         "No scale; cannot compute 15cm padding",
    "btn_show_highlight":    "Show Highlight",
    "btn_show_repair15":     "Show 15cm Boundary",
    "btn_sam":         "SAM segment (spalling)",
    "btn_sam_commit":  "Confirm (write spalling)",
    "btn_sam_cancel":  "Cancel",
    "btn_sam_undo":    "Undo point (Esc)",
    "sam_undone":      "Last SAM point undone.",
    "sam_hint":        "Left-click = include, right-click = exclude; Esc undoes the last point; Confirm writes the region to spalling.",
    "sam_committed":   "SAM region written to spalling.",
    "sam_unavailable": "SAM unavailable (onnxruntime or models/sam/*.onnx missing).",

    # --- fetch/progress (shared, used across future screens too) ---
    "fetch_progress": "Fetched {done}/{total}",
}
