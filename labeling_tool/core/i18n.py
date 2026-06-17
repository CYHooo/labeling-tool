"""Translations and language constants."""

TRANSLATIONS = {
    "en": {
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
    },
    "zh": {
        "window_title":       "掩码编辑标注工具",
        "settings":           "设置",
        "language":           "语言",
        "btn_select_origin":  "选择 Origin 文件夹",
        "btn_select_detected":"选择 Detected 文件夹",
        "lbl_origin":         "Origin: {p}",
        "lbl_detected":       "Detected: {p}",
        "lbl_output":         "输出(自动): {p}",
        "no_path":            "(未选择)",
        "lbl_category":       "当前类别:",
        "cat_crack":          "Crack(裂缝)",
        "cat_spalling":       "Spalling(剥落)",
        "group_brush":        "画笔标注",
        "btn_brush_on":       "进入画笔模式",
        "btn_brush_off":      "退出画笔模式",
        "btn_brush_reset":    "恢复为加载的 mask",
        "btn_brush_save":     "保存 mask",
        "lbl_brush_size":     "画笔大小 (px):",
        "brush_hint":
            "左键拖拽    绘制(写入当前类别通道)\n"
            "右键拖拽    擦除(仅当前类别)\n"
            "Ctrl+拖拽   平移视图\n"
            "滚轮        缩放\n"
            "切换图片时自动保存到 Labeling/<mask 名>\n"
            "  R 通道=crack, G 通道=spalling",
        "brush_saved":        "Mask 已保存 → {p}",
        "brush_no_image":     "未加载图片",
        "brush_reset":        "Mask 已恢复为加载状态",
        "group_list":         "图片列表",
        "group_nav":          "导航",
        "group_hint":         "帮助 / 用法",
        "btn_prev":           "← 上一张  [A]",
        "btn_next":           "下一张  [D] →",
        "btn_save":           "保存当前  [S]",
        "hint_text":
            "画笔   左键拖拽=绘制 · 右键拖拽=擦除 · 1/2=裂缝/剥落\n"
            "       B=切换 · [ / ]=笔大小 · R通道=裂缝 G通道=剥落\n"
            "画框   点击=加点 · Enter=提交 · Esc=取消 · Del=删除\n"
            "测量   点已知长度参照物的两端(默认 marker 边 7cm)\n"
            "视图   Ctrl+拖拽=平移 · 滚轮=缩放\n"
            "导航   A / D=上/下一张 · S=保存 · 切换时自动保存",
        "ready":              "就绪",
        "loaded_n_images":    "共加载 {n} 张图片",
        "dlg_origin":         "选择 Origin 图片文件夹",
        "dlg_detected":       "选择 Detected Mask 文件夹",
        "dlg_output":         "选择输出 Mask 文件夹",
        "warn_select_first":  "请先选择 Origin 和 Detected 文件夹",
        "warn_title":         "警告",
        "warn_no_images":     "{dir}/ 目录中没有图片。",
        "err_no_origin_title":"错误",
        "err_no_origin_msg":  "未找到 Origin 文件夹。",
        "status_template":    "{i}/{n}: {f}  |  已编辑: {edited}",
        "group_bbox":            "BBox 标注",
        "btn_bbox_on":           "进入 BBox 模式",
        "btn_bbox_off":          "退出 BBox 模式",
        "group_scale":           "比例尺 (px/cm)",
        "lbl_scale_template":    "Scale: {scale} mm/px ({source})",
        "scale_source_aruco":    "ArUco(自动)",
        "scale_source_fallback": "沿用上次",
        "scale_source_manual":   "手动",
        "scale_source_none":     "无",
        "btn_measure":           "手动测量(兜底)",
        "btn_measure_cancel":    "取消测量",
        "measure_dialog_title":  "手动比例尺",
        "measure_dialog_label":  "测量线段的实际长度 (cm):",
        "measure_hint":          "在图上点已知长度参照物的两端(默认 ArUco marker 边长 7cm)",
        "measure_done":          "已设置手动比例: {scale} mm/px",
        "bbox_hint":
            "点击    添加点\n"
            "Enter   提交(≥2 点)\n"
            "Esc     取消当前点集/取消选中\n"
            "Del     删除选中",
        "bbox_need_more_clicks": "至少需要 2 个点",
        "bbox_no_scale":         "未检测到 scale,无法计算 15cm 余量",
    },
    "ko": {
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
        "cat_crack":          "Crack(균열)",
        "cat_spalling":       "Spalling(박리)",
        "group_brush":        "브러시 라벨",
        "btn_brush_on":       "브러시 모드 진입",
        "btn_brush_off":      "브러시 모드 종료",
        "btn_brush_reset":    "로드된 마스크로 복원",
        "btn_brush_save":     "마스크 저장",
        "lbl_brush_size":     "브러시 크기 (px):",
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
        "group_scale":           "스케일 (px/cm)",
        "lbl_scale_template":    "Scale: {scale} mm/px ({source})",
        "scale_source_aruco":    "ArUco(자동)",
        "scale_source_fallback": "이전값",
        "scale_source_manual":   "수동",
        "scale_source_none":     "없음",
        "btn_measure":           "수동 측정 (대체)",
        "btn_measure_cancel":    "측정 취소",
        "measure_dialog_title":  "수동 스케일",
        "measure_dialog_label":  "측정한 선분의 실제 길이 (cm):",
        "measure_hint":          "알려진 길이 기준(기본 ArUco 마커 변 7cm)의 양 끝을 클릭하세요",
        "measure_done":          "수동 스케일 설정됨: {scale} mm/px",
        "bbox_hint":
            "클릭    점 추가\n"
            "Enter   확정 (≥2점)\n"
            "Esc     진행 중 취소 / 선택 해제\n"
            "Del     선택 삭제",
        "bbox_need_more_clicks": "최소 2개 점 필요",
        "bbox_no_scale":         "scale 없음, 15cm 여백 계산 불가",
    },
}
LANG_DISPLAY_NAMES = {"en": "English", "zh": "中文", "ko": "한국어"}
DEFAULT_LANG = "en"
