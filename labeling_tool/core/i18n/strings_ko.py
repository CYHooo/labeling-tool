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
    "language":           "언어",
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
    "group_bbox":            "BBox 라벨링",
    "btn_bbox_on":           "BBox 모드 진입",
    "btn_bbox_off":          "BBox 모드 종료",
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
    "fetch_progress": "가져오기 {done}/{total}",
}
