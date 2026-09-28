# Terminology: docs/i18n-glossary.md
"""Chinese (Simplified) UI strings."""

STRINGS = {
    # --- main window ---
    "window_title":       "掩码编辑标注工具",
    "settings":           "设置",
    "language":           "语言:",
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
    "btn_fine_annotation": "精细标注 (保留粗细)",
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
    "scale_source_server":   "服务器(PPM)",
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
    "btn_show_highlight":    "显示高亮",
    "btn_show_repair15":     "显示15cm边界",
    "btn_sam":         "SAM 分割 (剥离)",
    "btn_sam_commit":  "确认 (写入剥离)",
    "btn_sam_cancel":  "取消",
    "btn_sam_undo":    "撤回点 (Esc)",
    "sam_undone":      "已撤回上一个 SAM 点。",
    "sam_hint":        "左键=加入、右键=排除;Esc 撤回上一点;确认将区域写入剥离层。",
    "sam_committed":   "SAM 区域已写入剥离层。",
    "sam_unavailable": "SAM 不可用(缺 onnxruntime 或 models/sam/*.onnx)。",

    # --- fetch/progress (shared, used across future screens too) ---
    "fetch_progress": "已获取 {done}/{total}",

    # --- login ---
    "login_title":                    "登录",
    "login_tab_online":               "在线标注",
    "login_tab_local":                "本地任务",
    "login_tab_fewshot":              "Few-shot 标注",
    "login_field_base":               "BASE URL",
    "login_field_key":                "X-Viewer-Api-Key",
    "login_next":                     "下一步",
    "login_col_job":                  "任务",
    "login_col_inspection":           "检测名称",
    "login_col_photos":               "照片 / 已上传",
    "login_col_server":               "服务器",
    "login_col_modified":             "最近修改",
    "login_jobs_empty":               "还没有本地任务。请先在「{tab}」获取数据。",
    "login_open":                     "打开",
    "login_fewshot_hint_lite":
        "⚠ 此构建为 lite 版本，无法使用 few-shot 工具。\n"
        "需要 few-shot 工具时请安装 full 构建。",
    "login_fewshot_hint_no_torch":
        "⚠ 未安装 torch，无法使用。\n"
        "安装: pip install -r annotation_tool/requirements-gpu.txt",
    "login_fewshot_desc_lite":
        "基于 SAM2.1 的多类别半自动标注工具 (用于 few-shot 训练数据)。\n"
        "需要 GPU(torch) 和 SAM 权重，首次打开时模型加载需要一些时间。",
    "login_fewshot_desc_full":
        "基于 SAM3 / SAM2.1 的多类别半自动标注工具 (用于 few-shot 训练数据)。\n"
        "需要 GPU(torch) 和 SAM 权重，首次打开时模型加载需要一些时间。",
    "login_warn_input_required_title": "需要输入",
    "login_warn_input_required_msg":   "请输入 BASE/Key。",
    "login_upload_possible":           "上传: 可以 (已输入 URL/Key)",
    "login_upload_impossible":
        "上传: 不可 — 仅本地保存 (输入 URL/Key 后可上传)",
    "login_warn_no_manifest_title":    "未找到",
    "login_warn_no_manifest_msg":      "未找到本地清单: {path}",
    "login_warn_server_mismatch_title": "服务器不一致",
    "login_warn_server_mismatch_msg":
        "此任务是从 {base} 获取的。\n"
        "无法上传到其他服务器。\n"
        "请将 URL 改回原服务器，或清空 URL/Key 以离线打开。",
    "login_warn_manifest_error_title": "清单错误",
    "login_warn_manifest_error_msg":
        "无法读取本地清单: {path}\n{exc}",
    "login_version":                  "版本 {version}",
    "login_check_update":             "检查更新",
}
