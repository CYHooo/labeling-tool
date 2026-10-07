# Terminology: docs/i18n-glossary.md
"""Chinese (Simplified) UI strings."""

STRINGS = {
    # --- main window ---
    "window_title":       "掩码编辑标注工具",
    "language":           "语言:",
    "lbl_category":       "当前类别:",
    "cat_crack":          "裂缝",
    "cat_spalling":       "剥落",
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
        "  R 通道=裂缝, G 通道=剥落",
    "brush_saved":        "Mask 已保存 → {p}",
    "brush_no_image":     "未加载图片",
    "brush_reset":        "Mask 已恢复为加载状态",
    "group_job_info":     "任务信息",
    "lbl_job_id":         "任务 ID",
    "lbl_inspection_name":"检测名称",
    "lbl_photo_count":    "照片",
    "photo_count":        "{n} 张",
    "group_list":         "图片列表",
    "group_nav":          "导航",
    "group_hint":         "帮助 / 用法",
    "btn_prev":           "上一张  [A]",
    "btn_next":           "下一张  [D]",
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
    "warn_select_first":  "请先选择 Origin 和 Detected 文件夹",
    "warn_title":         "警告",
    "warn_no_images":     "{dir}/ 目录中没有图片。",
    "err_no_origin_title":"错误",
    "err_no_origin_msg":  "未找到 Origin 文件夹。",
    "status_template":    "{i}/{n}: {f}  |  已编辑: {edited}",
    "status_edited_yes":  "是",
    "status_edited_no":   "否",
    "status_category_changed": "类别 -> {cat}",
    "status_error":       "[错误] {error}",
    "group_bbox":            "修补区域标注",
    "btn_bbox_on":           "进入修补区域模式",
    "btn_bbox_off":          "退出修补区域模式",
    "group_scale":           "比例尺 (px/cm)",
    "lbl_scale_template":    "比例尺：{scale} mm/px（{source}）",
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
    "bbox_need_more_clicks": "至少需要 2 个点",
    "bbox_no_scale":         "未检测到比例尺，无法计算 15cm 余量",
    "btn_show_highlight":    "显示高亮",
    "btn_show_repair15":     "显示15cm边界",
    "btn_sam":         "SAM 分割 (剥落)",
    "btn_sam_commit":  "确认 (写入剥落)",
    "btn_sam_cancel":  "取消",
    "btn_sam_undo":    "撤回点 (Esc)",
    "sam_undone":      "已撤回上一个 SAM 点。",
    "sam_hint":        "左键=加入、右键=排除;Esc 撤回上一点;确认将区域写入剥落层。",
    "sam_committed":   "SAM 区域已写入剥落层。",
    "sam_unavailable": "SAM 不可用(缺 onnxruntime 或 models/sam/*.onnx)。",

    # --- fetch/progress (shared, used across future screens too) ---
    "fetch_progress": "已下载 {done}/{total}",

    # --- login ---
    "login_title":                    "登录",
    "login_tab_fewshot":              "Few-shot 标注",
    "login_field_base":               "BASE URL",
    "login_field_key":                "X-Viewer-Api-Key",
    "login_col_job":                  "任务",
    "login_col_inspection":           "检测名称",
    "login_col_photos":               "照片 / 已上传",
    "login_col_modified":             "最近修改",
    "login_jobs_empty": "还没有本地任务。请点击「{button}」获取数据。",
    "login_tab_labeling": "标注",
    "login_new_job": "获取新任务",
    "login_jobs_title": "本地任务（本机已获取的任务）",
    "fetch_existing_title": "已获取的任务",
    "fetch_existing_msg": "任务 {sid} 已在本机。\n要继续打开，还是从服务器重新获取？\n（重新获取也会保留标注结果和上传记录。）",
    "fetch_existing_refetch": "重新获取",
    "fetch_other_server_title": "其他服务器的任务",
    "fetch_other_server_msg": "本机的任务 {sid} 是从 {base} 获取的另一个任务。\n只是编号相同，与当前服务器的任务不同，不能在这里打开或重新获取。\n请在任务界面的本地任务列表中打开它。",
    "work_title": "任务",
    "signin_field_id": "ID",
    "signin_field_password": "密码",
    "signin_server_section": "服务器",
    "signin_button": "登录",
    "signin_error": "ID 或密码不正确。",
    "login_logout": "退出登录",
    "login_signed_in_as": "已登录: {user}",
    "signin_server_required": "要获取新任务，请填写服务器（BASE URL / Key）后重新登录。",
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
    "login_upload_possible": "上传: 可以 → {host}",
    "login_upload_impossible": "上传: 不可 — 仅本地保存 (退出登录后填写服务器即可上传)",
    "login_warn_no_manifest_title":    "未找到",
    "login_warn_no_manifest_msg":      "未找到本地清单: {path}",
    "login_warn_manifest_error_title": "清单错误",
    "login_warn_manifest_error_msg":
        "无法读取本地清单: {path}\n{exc}",
    "login_version":                  "版本 {version}",
    "login_check_update":             "检查更新",

    "login_loading_detail":            "正在将 SAM2.1 权重载入内存，最长约需 1 分钟，\n"
        "其间窗口可能无响应。",
    "login_loading_failed":            "无法打开 Few-shot 工具：{type}：{exc}",
    # --- fetch dialog ---
    "fetch_title":                     "获取数据",
    "fetch_from_label":                "fromNum (0=从头开始)",
    "fetch_to_label":                  "toNum (0=到末尾)",
    "fetch_back":                      "登录",
    "fetch_btn":                       "获取（下载）",
    "fetch_session_item":              "任务 {sid}",
    "fetch_session_item_named":        "任务 {sid} · {name}",
    "fetch_photo_count":               "({count} 张)",
    "fetch_sessions_failed_title":     "任务列表失败",
    "fetch_sessions_failed_msg":       "无法获取作业列表，请手动输入。\n{error}",
    "fetch_input_required_title":      "需要输入",
    "fetch_input_required_msg":        "请选择或输入 sessionId。",
    "fetch_failed_title":              "获取失败",
    "fetch_empty_title":               "为空",
    "fetch_empty_msg":                 "未选中任何照片（请检查范围）。",
    "fetch_partial_failed_title":      "部分失败",
    "fetch_partial_failed_msg":        "{count} 个下载失败，其余可正常使用。",

    # --- SAM2.1 weights dialog ---
    "weights_title":                   "下载 SAM2.1 模型",
    "weights_confirm":
        "Few-shot 标注需要 SAM2.1 模型（约 {size} MB）。\n"
        "只需下载一次，之后即可直接使用。\n\n"
        "保存位置：{path}\n\n是否现在下载？",
    "weights_progress_label":          "正在下载 SAM2.1 模型…",
    "weights_progress_template":       "正在下载 SAM2.1 模型… {done} / {total} MB",
    "weights_cancel":                  "取消",
    "weights_failed_title":            "下载失败",
    "weights_failed_msg":
        "未能下载 SAM2.1 模型。\n{type}: {exc}\n\n"
        "请检查网络连接，或手动下载文件并放到 {path}：\n{url}",

    # --- update dialog ---
    "update_title":                    "更新",
    "update_available":                "有新版本可用：v{version}",
    "update_download_size":            "\n下载大小：约 {size} MB",
    "update_full_warning":
        "\n\n⚠ torch / CUDA 组成已变更，需下载完整安装包。"
        "请确认网络和磁盘空间充足。",
    "update_informative":              "安装后将自动重启。\n\n{notes}",
    "update_btn_update":               "立即更新",
    "update_btn_later":                "稍后",
    "update_btn_skip":                 "跳过此版本",
    "update_ready_status":             "新版本 v{version} 已就绪 — 关闭任务窗口后更新",
    "update_btn_restart":              "立即重启并更新",
    "update_ready_informative":        "更新已就绪，重启后立即生效。\n\n{notes}",
    "update_applying":                 "正在应用更新…",
    "update_apply_failed_msg":         "未能应用更新。请关闭所有程序窗口后重试。\n\n{exc}",
    "update_progress_label":           "正在下载更新…",
    "update_progress_template":        "正在下载更新… {done} / {total} MB",
    "update_cancel":                   "取消",
    "update_failed_title":             "更新失败",
    "update_failed_msg":
        "{type}: {exc}\n\n请稍后重试，或手动下载：\n{url}",
    "update_dev_build_msg":            "开发版本无法检查更新。",
    "update_checking_msg":             "正在检查更新。",
    "update_uptodate_msg":             "当前已是最新版本。",
    "update_check_failed_title":       "检查更新失败",
    "update_check_failed_msg":
        "检查更新时发生错误：{type}: {exc}\n\n{url}",
    "update_linux_deps_title":         "缺少系统库",
    "update_linux_deps_msg":
        "软件包文件已写入，但由于缺少部分系统库，尚未完成配置。\n\n"
        "请打开终端并执行：\nsudo apt-get install -f\n\n{detail}",
    "update_linux_restart_title":      "更新安装完成",
    "update_linux_restart_msg":        "更新已成功安装，请重启应用。",

    # --- app / startup ---
    "app_fewshot_loading":             "正在加载 Few-shot 模型…请稍候。",
    "app_fewshot_error_title":         "无法打开 Few-shot 工具",
    "app_fewshot_error_msg":
        "{type}: {exc}\n\n请检查 SAM 权重（./checkpoint）和 torch 安装"
        "（参见 annotation_tool/USAGE.md）。",

    # --- few-shot tool (annotation_tool/ui/main_window.py) ---
    # Class names themselves (joint, concrete, scalebar, shoe, distractor,
    # and any user-added class) are never translated: they are the identities
    # stored in classes.json and map to pixel values in the training data.
    "fs_status_choose_folder":
        "请用 File ▸ Open Folder (Ctrl+O) 选择存放图片的文件夹",
    "fs_classes_corrupt":
        "类别文件损坏，已使用默认类别，修改不会被保存：{exc}",
    "fs_save_classes_failed_title":     "保存类别失败",
    "fs_add_class_title":               "添加类别",
    "fs_add_class_label":               "类别名称：",
    "fs_choose_color_title":            "选择类别颜色",
    "fs_add_class_failed_title":        "添加类别失败",
    "fs_status_class_added":            "已添加类别 {cid}：{name}",
    "fs_rename_class_title":            "重命名类别",
    "fs_rename_class_label":            "类别 {cid} 的新名称：",
    "fs_rename_failed_title":           "重命名失败",
    "fs_class_color_title":             "类别 {cid}：{name} 的颜色",
    "fs_btn_add":                       "添加",
    "fs_tip_add":                       "添加新类别",
    "fs_btn_rename":                    "重命名",
    "fs_tip_rename":                    "重命名当前类别",
    "fs_btn_priority_up":               "提升优先级 ↑",
    "fs_tip_priority_up":               "提高当前类别的导出优先级（覆盖其他类）",
    "fs_btn_priority_down":             "↓",
    "fs_tip_priority_down":             "降低当前类别的导出优先级",
    "fs_section_tool":                  "工具",
    "fs_tool_sam":                      "SAM 点/框 [V]",
    "fs_tool_brush":                    "画笔 [B]",
    "fs_tool_eraser":                   "橡皮擦 [E]",
    "fs_label_brush":                   "笔刷",
    "fs_confirm":                       "确认 (Enter)",
    "fs_save":                          "保存 (Ctrl+S)",
    "fs_tip_swatch":                    "点击修改颜色",
    "fs_export_order":                  "导出优先级（低→高）：{order}",
    "fs_menu_file":                     "文件",
    "fs_action_open_folder":            "打开文件夹…",
    "fs_dialog_select_folder":          "选择图片文件夹（直接读取该文件夹中的图片）",
    "fs_invalid_folder_title":          "文件夹无效",
    "fs_folder_not_found":              "未找到文件夹：\n{dir}",
    "fs_window_title":                  "ConcJoint Annotator — {name}（{count} 张图片）",
    "fs_status_dataset_loaded":
        "{count} 张图片，{n_masks} 张已有标注；mask 目录：{mask_dir}",
    "fs_no_images_title":               "没有图片",
    "fs_no_images_msg":                 "在 {dir} 中未直接找到图片文件",
    "fs_mask_read_error":               "无法读取 mask {name}：{exc}",
    "fs_mask_size_mismatch":
        "mask {name} 尺寸 {mw}x{mh} 与图片 {w}x{h} 不一致，未加载；"
        "为保护原文件，本图禁止保存",
    "fs_mask_unknown_pixels":
        "警告：mask 中含未定义的像素值 {values}，保存时会被清除；请先添加对应类别",
    "fs_save_blocked_title":            "禁止保存",
    "fs_status_saved":                  "已保存 {name}",
    "fs_inference_error_title":         "推理错误",
    "fs_dock_images":                   "图片",
    "fs_dock_classes":                  "类别",

    # --- viewer main window (labeling_tool/ui/main_window.py) ---
    "vmw_btn_upload":                  "上传到 EC2",
    "vmw_offline_title":               "离线",
    "vmw_offline_msg":                 "无法上传：没有 API 客户端。",
    "vmw_status_no_edits":             "没有可上传的编辑内容（未保存任何 mask）",
    "vmw_none_title":                  "无",
    "vmw_msg_no_edits":                "没有可上传的编辑内容。",
    "vmw_no_scale_title":              "无比例尺",
    "vmw_status_no_scale":
        "没有带 pxPerCm 的编辑内容 — 需要 ArUco 自动检测或手动测量",
    "vmw_msg_no_scale":                "没有带 pxPerCm 的编辑内容（需要 ArUco）。",
    "vmw_phase_prepare":               "准备",
    "vmw_phase_upload":                "上传",
    "vmw_progress_format":             "{phase} %v/%m",
    "vmw_status_upload_starting":      "正在准备 EC2 上传…（0/{total}）",
    "vmw_status_progress":             "EC2 {phase}中…（{done}/{total}）",
    "vmw_upload_failed":               "上传失败",
    "vmw_status_no_items":             "没有可上传的项目",
    "vmw_status_done":                 "上传完成：{count} 张（服务器确认 OK）",
    "vmw_done_title":                  "完成",
    "vmw_done_msg":                    "已上传 {count} 张并完成服务器确认。{report_line}",
    "vmw_report_line":                 "\n验证报告（CSV）：{report}",
    "vmw_err_unrecorded":              "（原因未记录）",
    "vmw_part_failed_batches":         "{count} 个批次上传失败 — 原因：{err}",
    "vmw_part_verify_failures":
        "服务器确认结果：{count} 张未反映（编号/时间戳：{nums}{more}）",
    "vmw_part_anomalies":
        "服务器只保存了部分数据（比请求少 {missing} 张未反映）",
    "vmw_status_partial":
        "服务器确认 {count} 张正常，部分未反映 — 请重试",
    "vmw_partial_title":               "部分失败 / 未反映",
    "vmw_partial_msg_header":          "服务器已确认的照片：{count} 张\n\n",
    "vmw_partial_msg_footer":          "\n详细日志：{log_path}\n\n请重新上传。",
}
