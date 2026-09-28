# Terminology: docs/i18n-glossary.md
"""English UI strings."""

STRINGS = {
    # --- main window ---
    "window_title":       "Mask Editing Annotation Tool",
    "settings":           "Settings",
    "language":           "Language:",
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

    # --- login ---
    "login_title":                    "Log in",
    "login_tab_online":               "Online labeling",
    "login_tab_local":                "Local jobs",
    "login_tab_fewshot":              "Few-shot labeling",
    "login_field_base":               "BASE URL",
    "login_field_key":                "X-Viewer-Api-Key",
    "login_next":                     "Next",
    "login_col_job":                  "Job",
    "login_col_inspection":           "Inspection name",
    "login_col_photos":               "Photos / uploaded",
    "login_col_server":               "Server",
    "login_col_modified":             "Last modified",
    "login_jobs_empty":               "No jobs yet. Fetch data in “{tab}” first.",
    "login_open":                     "Open",
    "login_fewshot_hint_lite":
        "⚠ This build is the lite variant, so the few-shot tool is unavailable.\n"
        "Install the full build if you need the few-shot tool.",
    "login_fewshot_hint_no_torch":
        "⚠ torch is not installed, so this tool is unavailable.\n"
        "Install: pip install -r annotation_tool/requirements-gpu.txt",
    "login_fewshot_desc_lite":
        "SAM2.1-based multi-class semi-automatic labeling tool (for few-shot training data).\n"
        "Needs a GPU (torch) and SAM weights; the first launch takes time to load the model.",
    "login_fewshot_desc_full":
        "SAM3 / SAM2.1-based multi-class semi-automatic labeling tool (for few-shot training data).\n"
        "Needs a GPU (torch) and SAM weights; the first launch takes time to load the model.",
    "login_warn_input_required_title": "Input required",
    "login_warn_input_required_msg":   "Enter BASE/Key.",
    "login_upload_possible":           "Upload: possible (URL/Key entered)",
    "login_upload_impossible":
        "Upload: not possible — local save only (enter URL/Key to enable upload)",
    "login_warn_no_manifest_title":    "Not found",
    "login_warn_no_manifest_msg":      "Local manifest not found: {path}",
    "login_warn_server_mismatch_title": "Server mismatch",
    "login_warn_server_mismatch_msg":
        "This job was fetched from {base}.\n"
        "It cannot be uploaded to a different server.\n"
        "Change the URL back to the original server, or clear URL/Key to open it offline.",
    "login_warn_manifest_error_title": "Manifest error",
    "login_warn_manifest_error_msg":
        "Could not read the local manifest: {path}\n{exc}",
    "login_version":                  "Version {version}",
    "login_check_update":             "Check for updates",
}
