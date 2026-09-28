# Terminology: docs/i18n-glossary.md
"""Korean UI strings.

The Korean text used to be machine-translated; docs/i18n-glossary.md is now
the authority and wins over whatever was here before (e.g. crack -> 균열,
spalling -> 박리, scale -> 축척).
"""

STRINGS = {
    # --- main window ---
    "window_title":       "마스크 편집 라벨링 도구",
    "settings":           "설정",
    "language":           "언어:",
    "btn_select_origin":  "Origin 폴더 선택",
    "btn_select_detected":"Detected 폴더 선택",
    "lbl_origin":         "Origin: {p}",
    "lbl_detected":       "Detected: {p}",
    "lbl_output":         "출력(자동): {p}",
    "no_path":            "(선택 안됨)",
    "lbl_category":       "현재 카테고리:",
    "cat_crack":          "균열",
    "cat_spalling":       "박리",
    "group_brush":        "브러시 라벨",
    "btn_brush_on":       "브러시 모드 진입",
    "btn_brush_off":      "브러시 모드 종료",
    "btn_brush_reset":    "로드된 마스크로 복원",
    "btn_brush_save":     "마스크 저장",
    "lbl_brush_size":     "브러시 크기 (px):",
    "btn_fine_annotation": "정밀 주석 (굵기 유지)",
    "brush_hint":
        "왼쪽 드래그   그리기 (현재 카테고리 채널)\n"
        "오른쪽 드래그 지우기 (현재 카테고리만)\n"
        "Ctrl+드래그   화면 이동\n"
        "휠            확대/축소\n"
        "이미지 전환 시 Labeling/<mask 이름>에 자동 저장\n"
        "  R=crack, G=spalling",
    "brush_saved":        "마스크 저장 완료 → {p}",
    "brush_no_image":     "이미지가 로드되지 않음",
    "brush_reset":        "마스크가 로드된 상태로 복원됨",
    "group_list":         "이미지 목록",
    "group_nav":          "탐색",
    "group_hint":         "도움말 / 사용법",
    "btn_prev":           "← 이전  [A]",
    "btn_next":           "다음  [D] →",
    "btn_save":           "현재 저장  [S]",
    "hint_text":
        "브러시  왼쪽=그리기 · 오른쪽=지우기 · 1/2=균열/박리\n"
        "        B=토글 · [ / ]=크기 · R=균열 G=박리\n"
        "박스    클릭=점추가 · Enter=확정 · Esc=취소 · Del=삭제\n"
        "측정    알려진 길이 기준의 양 끝을 클릭 (기본 마커변 7cm)\n"
        "화면    Ctrl+드래그=이동 · 휠=확대/축소\n"
        "탐색    A / D=이전/다음 · S=저장 · 전환 시 자동저장",
    "ready":              "준비 완료",
    "loaded_n_images":    "이미지 {n}장 로드됨",
    "dlg_origin":         "Origin 이미지 폴더 선택",
    "dlg_detected":       "Detected 마스크 폴더 선택",
    "dlg_output":         "출력 마스크 폴더 선택",
    "warn_select_first":  "먼저 Origin과 Detected 폴더를 선택하세요",
    "warn_title":         "경고",
    "warn_no_images":     "{dir}/ 디렉토리에 이미지 파일이 없습니다.",
    "err_no_origin_title":"오류",
    "err_no_origin_msg":  "Origin 폴더를 찾을 수 없습니다.",
    "status_template":    "{i}/{n}: {f}  |  편집됨: {edited}",
    "group_bbox":            "보수 구역 라벨링",
    "btn_bbox_on":           "보수 구역 모드 진입",
    "btn_bbox_off":          "보수 구역 모드 종료",
    "group_scale":           "축척 (px/cm)",
    "lbl_scale_template":    "Scale: {scale} mm/px ({source})",
    "scale_source_aruco":    "ArUco(자동)",
    "scale_source_fallback": "이전값",
    "scale_source_manual":   "수동",
    "scale_source_none":     "없음",
    "scale_source_server":   "서버(PPM)",
    "btn_measure":           "수동 측정 (대체)",
    "btn_measure_cancel":    "측정 취소",
    "measure_dialog_title":  "수동 축척",
    "measure_dialog_label":  "측정한 선분의 실제 길이 (cm):",
    "measure_hint":          "알려진 길이 기준(기본 ArUco 마커 변 7cm)의 양 끝을 클릭하세요",
    "measure_done":          "수동 축척 설정됨: {scale} mm/px",
    "bbox_hint":
        "클릭    점 추가\n"
        "Enter   확정 (≥2점)\n"
        "Esc     진행 중 취소 / 선택 해제\n"
        "Del     선택 삭제",
    "bbox_need_more_clicks": "최소 2개 점 필요",
    "bbox_no_scale":         "축척 없음, 15cm 여백 계산 불가",
    "btn_show_highlight":    "하이라이트 표시",
    "btn_show_repair15":     "15cm 경계 표시",
    "btn_sam":         "SAM 분할 (박리)",
    "btn_sam_commit":  "확정 (박리 기록)",
    "btn_sam_cancel":  "취소",
    "btn_sam_undo":    "포인트 취소 (Esc)",
    "sam_undone":      "마지막 SAM 포인트를 취소했습니다.",
    "sam_hint":        "좌클릭=포함, 우클릭=제외; Esc 로 마지막 포인트 취소; 확정 시 영역을 박리로 기록합니다.",
    "sam_committed":   "SAM 영역을 박리에 기록했습니다.",
    "sam_unavailable": "SAM 사용 불가 (onnxruntime 또는 models/sam/*.onnx 없음).",

    # --- fetch/progress (shared, used across future screens too) ---
    "fetch_progress": "다운로드 {done}/{total}",

    # --- login ---
    "login_title":                    "로그인",
    "login_tab_online":               "온라인 라벨링",
    "login_tab_local":                "로컬 작업",
    "login_tab_fewshot":              "Few-shot 라벨링",
    "login_field_base":               "BASE URL",
    "login_field_key":                "X-Viewer-Api-Key",
    "login_next":                     "다음",
    "login_col_job":                  "작업",
    "login_col_inspection":           "점검명",
    "login_col_photos":               "사진 / 업로드",
    "login_col_server":               "서버",
    "login_col_modified":             "최근 수정",
    "login_jobs_empty":               "받은 작업이 없습니다. 「{tab}」에서 먼저 데이터를 가져오세요.",
    "login_open":                     "열기",
    "login_fewshot_hint_lite":
        "⚠ 이 빌드는 lite 버전이라 few-shot 도구를 사용할 수 없습니다.\n"
        "few-shot 도구가 필요하면 full 빌드를 설치하세요.",
    "login_fewshot_hint_no_torch":
        "⚠ torch 가 설치되어 있지 않아 사용할 수 없습니다.\n"
        "설치: pip install -r annotation_tool/requirements-gpu.txt",
    "login_fewshot_desc_lite":
        "SAM2.1 기반 다중 클래스 반자동 라벨링 도구 (few-shot 학습 데이터용).\n"
        "GPU(torch)와 SAM 가중치가 필요하며, 처음 열 때 모델 로딩에 시간이 걸립니다.",
    "login_fewshot_desc_full":
        "SAM3 / SAM2.1 기반 다중 클래스 반자동 라벨링 도구 (few-shot 학습 데이터용).\n"
        "GPU(torch)와 SAM 가중치가 필요하며, 처음 열 때 모델 로딩에 시간이 걸립니다.",
    "login_warn_input_required_title": "입력 필요",
    "login_warn_input_required_msg":   "BASE/Key를 입력하세요.",
    "login_upload_possible":           "업로드: 가능 (URL/Key 입력됨)",
    "login_upload_impossible":
        "업로드: 불가 — 로컬 저장만 (URL/Key 를 입력하면 업로드 가능)",
    "login_warn_no_manifest_title":    "없음",
    "login_warn_no_manifest_msg":      "로컬 매니페스트 없음: {path}",
    "login_warn_server_mismatch_title": "서버 불일치",
    "login_warn_server_mismatch_msg":
        "이 작업은 {base} 에서 받아왔습니다.\n"
        "다른 서버로 업로드할 수 없습니다.\n"
        "URL을 원래 서버로 되돌리거나, URL/Key를 비우고 오프라인으로 여세요.",
    "login_warn_manifest_error_title": "매니페스트 오류",
    "login_warn_manifest_error_msg":
        "로컬 매니페스트를 읽을 수 없습니다: {path}\n{exc}",
    "login_version":                  "버전 {version}",
    "login_check_update":             "업데이트 확인",

    # --- fetch dialog ---
    "fetch_title":                     "데이터 가져오기",
    "fetch_from_label":                "fromNum (0=처음부터)",
    "fetch_to_label":                  "toNum (0=끝까지)",
    "fetch_back":                      "← 로그인",
    "fetch_btn":                       "가져오기 (다운로드)",
    "fetch_session_item":              "작업 {sid}",
    "fetch_session_item_named":        "작업 {sid} · {name}",
    "fetch_photo_count":               "({count}장)",
    "fetch_sessions_failed_title":     "작업 목록 실패",
    "fetch_sessions_failed_msg":       "작업 목록을 불러오지 못했습니다. 수동 입력하세요.\n{error}",
    "fetch_input_required_title":      "입력 필요",
    "fetch_input_required_msg":        "sessionId를 선택/입력하세요.",
    "fetch_failed_title":              "가져오기 실패",
    "fetch_empty_title":               "비어있음",
    "fetch_empty_msg":                 "선택된 사진이 없습니다 (범위를 확인하세요).",
    "fetch_partial_failed_title":      "일부 실패",
    "fetch_partial_failed_msg":        "{count}건 다운로드 실패. 나머지는 사용 가능합니다.",

    # --- SAM2.1 weights dialog ---
    "weights_title":                   "SAM2.1 모델 다운로드",
    "weights_confirm":
        "Few-shot 라벨링에는 SAM2.1 모델(약 {size} MB)이 필요합니다.\n"
        "처음 한 번만 내려받으며, 다음부터는 바로 사용됩니다.\n\n"
        "저장 위치: {path}\n\n지금 다운로드할까요?",
    "weights_progress_label":          "SAM2.1 모델 다운로드 중…",
    "weights_progress_template":       "SAM2.1 모델 다운로드 중… {done} / {total} MB",
    "weights_cancel":                  "취소",
    "weights_failed_title":            "다운로드 실패",
    "weights_failed_msg":
        "SAM2.1 모델을 내려받지 못했습니다.\n{type}: {exc}\n\n"
        "인터넷 연결을 확인하거나, 파일을 직접 받아 {path} 에 두세요:\n{url}",

    # --- update dialog ---
    "update_title":                    "업데이트",
    "update_available":                "새 버전이 있습니다: v{version}\n다운로드 크기: 약 {size} MB",
    "update_full_warning":
        "\n\n⚠ full 버전 업데이트는 약 1.5 GB 를 다운로드합니다. "
        "충분한 네트워크/디스크 공간을 확인하세요.",
    "update_informative":              "설치 후 자동으로 다시 시작됩니다.\n\n{notes}",
    "update_btn_update":               "지금 업데이트",
    "update_btn_later":                "나중에",
    "update_btn_skip":                 "이 버전 건너뛰기",
    "update_progress_label":           "업데이트 다운로드 중…",
    "update_progress_template":        "업데이트 다운로드 중… {done} / {total} MB",
    "update_cancel":                   "취소",
    "update_failed_title":             "업데이트 실패",
    "update_failed_msg":
        "{type}: {exc}\n\n나중에 다시 시도하거나 직접 내려받으세요:\n{url}",
    "update_dev_build_msg":            "개발 빌드에서는 업데이트를 확인할 수 없습니다.",
    "update_checking_msg":             "업데이트 확인 중입니다.",
    "update_uptodate_msg":             "최신 버전을 사용 중입니다.",
    "update_check_failed_title":       "업데이트 확인 실패",
    "update_check_failed_msg":
        "업데이트 확인 중 오류가 발생했습니다: {type}: {exc}\n\n{url}",

    # --- app / startup ---
    "app_fewshot_loading":             "Few-shot 모델 로딩 중… 잠시 기다려 주세요.",
    "app_fewshot_error_title":         "Few-shot 도구를 열 수 없습니다",
    "app_fewshot_error_msg":
        "{type}: {exc}\n\nSAM 가중치(./checkpoint)와 torch 설치를 확인하세요 "
        "(annotation_tool/USAGE.md 참고).",

    # --- few-shot tool (annotation_tool/ui/main_window.py) ---
    # 클래스 이름(joint, concrete, scalebar, shoe, distractor 및 사용자가
    # 추가한 클래스)은 번역하지 않습니다: classes.json에 저장된 식별자이며
    # 학습 데이터의 픽셀 값에 대응합니다.
    "fs_status_choose_folder":
        "File ▸ Open Folder (Ctrl+O)로 이미지 폴더를 선택하세요",
    "fs_classes_corrupt":
        "클래스 파일이 손상되어 기본 클래스를 사용합니다. 수정 내용은 저장되지 "
        "않습니다: {exc}",
    "fs_save_classes_failed_title":     "클래스 저장 실패",
    "fs_add_class_title":               "클래스 추가",
    "fs_add_class_label":               "클래스 이름:",
    "fs_choose_color_title":            "클래스 색상 선택",
    "fs_add_class_failed_title":        "클래스 추가 실패",
    "fs_status_class_added":            "클래스 {cid}: {name}를 추가했습니다",
    "fs_rename_class_title":            "클래스 이름 변경",
    "fs_rename_class_label":            "클래스 {cid}의 새 이름:",
    "fs_rename_failed_title":           "이름 변경 실패",
    "fs_class_color_title":             "클래스 {cid}: {name}의 색상",
    "fs_btn_add":                       "추가",
    "fs_tip_add":                       "새 클래스 추가",
    "fs_btn_rename":                    "이름 변경",
    "fs_tip_rename":                    "현재 클래스 이름 변경",
    "fs_btn_priority_up":               "우선순위 ↑",
    "fs_tip_priority_up":
        "현재 클래스의 내보내기 우선순위를 높입니다 (다른 클래스를 덮어씀)",
    "fs_btn_priority_down":             "↓",
    "fs_tip_priority_down":             "현재 클래스의 내보내기 우선순위를 낮춥니다",
    "fs_section_tool":                  "도구",
    "fs_tool_sam":                      "SAM 점/박스 [V]",
    "fs_tool_brush":                    "브러시 [B]",
    "fs_tool_eraser":                   "지우개 [E]",
    "fs_label_brush":                   "브러시",
    "fs_confirm":                       "확인 (Enter)",
    "fs_save":                          "저장 (Ctrl+S)",
    "fs_tip_swatch":                    "클릭하여 색상 변경",
    "fs_export_order":                  "내보내기 우선순위 (낮음→높음): {order}",
    "fs_menu_file":                     "파일",
    "fs_action_open_folder":            "폴더 열기…",
    "fs_dialog_select_folder":
        "이미지 폴더 선택 (해당 폴더의 이미지를 직접 읽습니다)",
    "fs_invalid_folder_title":          "유효하지 않은 폴더",
    "fs_folder_not_found":              "폴더를 찾을 수 없습니다:\n{dir}",
    "fs_window_title":                  "ConcJoint Annotator — {name} ({count}장)",
    "fs_status_dataset_loaded":
        "이미지 {count}장, 라벨링 완료 {n_masks}장; 마스크 폴더: {mask_dir}",
    "fs_no_images_title":               "이미지 없음",
    "fs_no_images_msg":                 "{dir}에서 이미지 파일을 찾을 수 없습니다",
    "fs_mask_read_error":               "마스크 {name}를 읽을 수 없습니다: {exc}",
    "fs_mask_size_mismatch":
        "마스크 {name} 크기 {mw}x{mh}가 이미지 {w}x{h}와 일치하지 않아 불러오지 "
        "않았습니다. 원본 보호를 위해 이 이미지는 저장이 금지됩니다",
    "fs_mask_unknown_pixels":
        "경고: 마스크에 정의되지 않은 픽셀 값 {values}이 있어 저장 시 삭제됩니다. "
        "먼저 해당 클래스를 추가하세요",
    "fs_save_blocked_title":            "저장 금지",
    "fs_status_saved":                  "{name} 저장 완료",
    "fs_inference_error_title":         "추론 오류",
    "fs_dock_images":                   "이미지",
    "fs_dock_classes":                  "클래스",
}
