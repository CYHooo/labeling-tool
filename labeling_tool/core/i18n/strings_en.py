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
    "warn_select_first":  "Please select Origin and Detected folders first",
    "warn_title":         "Warning",
    "warn_no_images":     "No image files in {dir}/.",
    "err_no_origin_title":"Error",
    "err_no_origin_msg":  "Origin folder not found.",
    "status_template":    "{i}/{n}: {f}  |  edited: {edited}",
    "status_edited_yes":  "yes",
    "status_edited_no":   "no",
    "status_category_changed": "Category -> {cat}",
    "status_error":       "[Error] {error}",
    "group_bbox":            "Repair area labeling",
    "btn_bbox_on":           "Enter Repair Area Mode",
    "btn_bbox_off":          "Exit Repair Area Mode",
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
    "fetch_progress": "Downloaded {done}/{total}",

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

    "login_loading_detail":            "Loading the SAM2.1 weights into memory. This may take a moment.",
    "login_loading_failed":            "Could not open the few-shot tool: {type}: {exc}",
    # --- fetch dialog ---
    "fetch_title":                     "Fetch data",
    "fetch_from_label":                "fromNum (0 = from the start)",
    "fetch_to_label":                  "toNum (0 = to the end)",
    "fetch_back":                      "← Log in",
    "fetch_btn":                       "Fetch (download)",
    "fetch_session_item":              "Job {sid}",
    "fetch_session_item_named":        "Job {sid} · {name}",
    "fetch_photo_count":               "({count} photos)",
    "fetch_sessions_failed_title":     "Job list failed",
    "fetch_sessions_failed_msg":       "Could not load the job list. Enter it manually.\n{error}",
    "fetch_input_required_title":      "Input required",
    "fetch_input_required_msg":        "Select or enter a sessionId.",
    "fetch_failed_title":              "Fetch failed",
    "fetch_empty_title":               "Empty",
    "fetch_empty_msg":                 "No photos selected (check the range).",
    "fetch_partial_failed_title":      "Partial failure",
    "fetch_partial_failed_msg":        "{count} downloads failed. The rest are usable.",

    # --- SAM2.1 weights dialog ---
    "weights_title":                   "Download SAM2.1 model",
    "weights_confirm":
        "Few-shot labeling needs the SAM2.1 model (about {size} MB).\n"
        "It downloads only once; after that it's ready to use.\n\n"
        "Save location: {path}\n\nDownload it now?",
    "weights_progress_label":          "Downloading SAM2.1 model…",
    "weights_progress_template":       "Downloading SAM2.1 model… {done} / {total} MB",
    "weights_cancel":                  "Cancel",
    "weights_failed_title":            "Download failed",
    "weights_failed_msg":
        "Could not download the SAM2.1 model.\n{type}: {exc}\n\n"
        "Check your internet connection, or download the file manually "
        "and place it at {path}:\n{url}",

    # --- update dialog ---
    "update_title":                    "Update",
    "update_available":                "A new version is available: v{version}\nDownload size: about {size} MB",
    "update_full_warning":
        "\n\n⚠ The full variant update downloads about 1.5 GB. "
        "Make sure you have enough network and disk space.",
    "update_informative":              "The app restarts automatically after installing.\n\n{notes}",
    "update_btn_update":               "Update now",
    "update_btn_later":                "Later",
    "update_btn_skip":                 "Skip this version",
    "update_progress_label":           "Downloading update…",
    "update_progress_template":        "Downloading update… {done} / {total} MB",
    "update_cancel":                   "Cancel",
    "update_failed_title":             "Update failed",
    "update_failed_msg":
        "{type}: {exc}\n\nTry again later, or download it manually:\n{url}",
    "update_dev_build_msg":            "Update checks are unavailable on a development build.",
    "update_checking_msg":             "Checking for updates.",
    "update_uptodate_msg":             "You're using the latest version.",
    "update_check_failed_title":       "Update check failed",
    "update_check_failed_msg":
        "An error occurred while checking for updates: {type}: {exc}\n\n{url}",

    # --- app / startup ---
    "app_fewshot_loading":             "Loading the few-shot model… please wait.",
    "app_fewshot_error_title":         "Could not open the few-shot tool",
    "app_fewshot_error_msg":
        "{type}: {exc}\n\nCheck the SAM weights (./checkpoint) and the torch "
        "installation (see annotation_tool/USAGE.md).",

    # --- few-shot tool (annotation_tool/ui/main_window.py) ---
    # Class names themselves (joint, concrete, scalebar, shoe, distractor,
    # and any user-added class) are never translated: they are the identities
    # stored in classes.json and map to pixel values in the training data.
    "fs_status_choose_folder":
        "Use File > Open Folder (Ctrl+O) to choose an image folder",
    "fs_classes_corrupt":
        "Class file corrupted, using default classes; edits will not be saved: {exc}",
    "fs_save_classes_failed_title":     "Save classes failed",
    "fs_add_class_title":               "Add class",
    "fs_add_class_label":               "Class name:",
    "fs_choose_color_title":            "Choose class color",
    "fs_add_class_failed_title":        "Add class failed",
    "fs_status_class_added":            "Added class {cid}: {name}",
    "fs_rename_class_title":            "Rename class",
    "fs_rename_class_label":            "New name for class {cid}:",
    "fs_rename_failed_title":           "Rename failed",
    "fs_class_color_title":             "Color for class {cid}: {name}",
    "fs_btn_add":                       "Add",
    "fs_tip_add":                       "Add a new class",
    "fs_btn_rename":                    "Rename",
    "fs_tip_rename":                    "Rename the active class",
    "fs_btn_priority_up":               "Priority ↑",
    "fs_tip_priority_up":
        "Raise the active class's export priority (overrides other classes)",
    "fs_btn_priority_down":             "↓",
    "fs_tip_priority_down":             "Lower the active class's export priority",
    "fs_section_tool":                  "Tool",
    "fs_tool_sam":                      "SAM point/box [V]",
    "fs_tool_brush":                    "Brush [B]",
    "fs_tool_eraser":                   "Eraser [E]",
    "fs_label_brush":                   "Brush",
    "fs_confirm":                       "Confirm (Enter)",
    "fs_save":                          "Save (Ctrl+S)",
    "fs_tip_swatch":                    "Click to change color",
    "fs_export_order":                  "Export priority (low to high): {order}",
    "fs_menu_file":                     "&File",
    "fs_action_open_folder":            "Open folder…",
    "fs_dialog_select_folder":
        "Select an image folder (images are read directly from it)",
    "fs_invalid_folder_title":          "Invalid folder",
    "fs_folder_not_found":              "Folder not found:\n{dir}",
    "fs_window_title":                  "ConcJoint Annotator — {name} ({count} images)",
    "fs_status_dataset_loaded":
        "{count} images, {n_masks} already labeled; mask folder: {mask_dir}",
    "fs_no_images_title":               "No images",
    "fs_no_images_msg":                 "No image files found directly in {dir}",
    "fs_mask_read_error":               "Could not read mask {name}: {exc}",
    "fs_mask_size_mismatch":
        "Mask {name} size {mw}x{mh} does not match image {w}x{h}; not loaded. "
        "Saving is disabled for this image to protect the original file",
    "fs_mask_unknown_pixels":
        "Warning: mask contains undefined pixel values {values}; they will be "
        "cleared on save. Add matching classes first",
    "fs_save_blocked_title":            "Save blocked",
    "fs_status_saved":                  "Saved {name}",
    "fs_inference_error_title":         "Inference error",
    "fs_dock_images":                   "Images",
    "fs_dock_classes":                  "Classes",

    # --- viewer main window (labeling_tool/ui/main_window.py) ---
    "vmw_btn_upload":                  "Upload to EC2",
    "vmw_offline_title":               "Offline",
    "vmw_offline_msg":                 "Cannot upload: no API client.",
    "vmw_status_no_edits":
        "No edited masks to upload (nothing saved)",
    "vmw_none_title":                  "None",
    "vmw_msg_no_edits":                "No edited masks to upload.",
    "vmw_no_scale_title":              "No scale",
    "vmw_status_no_scale":
        "No edits have pxPerCm -- run ArUco auto-detect or measure manually",
    "vmw_msg_no_scale":                "No edits have pxPerCm (ArUco required).",
    "vmw_phase_prepare":               "Preparing",
    "vmw_phase_upload":                "Uploading",
    "vmw_progress_format":             "{phase} %v/%m",
    "vmw_status_upload_starting":      "Preparing EC2 upload... (0/{total})",
    "vmw_status_progress":             "EC2 {phase}... ({done}/{total})",
    "vmw_upload_failed":               "Upload failed",
    "vmw_status_no_items":             "Nothing to upload",
    "vmw_status_done":
        "Upload complete: {count} photo(s) (server-verified)",
    "vmw_done_title":                  "Done",
    "vmw_done_msg":
        "{count} photo(s) uploaded and server-verified.{report_line}",
    "vmw_report_line":                 "\nVerification report (CSV): {report}",
    "vmw_err_unrecorded":              "(cause not recorded)",
    "vmw_part_failed_batches":
        "{count} batch(es) failed to upload -- cause: {err}",
    "vmw_part_verify_failures":
        "Server verification found {count} photo(s) not reflected "
        "(number/timestamp: {nums}{more})",
    "vmw_part_anomalies":
        "Server saved only part of the batch "
        "({missing} photo(s) not reflected vs. requested)",
    "vmw_status_partial":
        "Server-verified {count} photo(s); some not reflected -- try again",
    "vmw_partial_title":               "Partial failure / not reflected",
    "vmw_partial_msg_header":          "Server-verified photos: {count}\n\n",
    "vmw_partial_msg_footer":
        "\nDetailed log: {log_path}\n\nPlease upload again.",
}
