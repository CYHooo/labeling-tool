# 默认显示 15cm 外轮廓 + 从轮廓自动生成 bbox

日期:2026-06-29
状态:已确认设计,待实现

## 背景

服务端现已为每张图提供 PPM(px/cm),拍摄端取消 ArUco。用户希望手动标注时:
1. **默认显示 15cm 外轮廓**;
2. **基于该外轮廓自动生成对应的 bbox**(用 PPM 直接计算);
3. bbox 标注模式下仍可**修改这些自动生成的 bbox**。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 15cm 轮廓默认显示 | **ON**(`show_repair15` 默认 True) |
| 自动 bbox 来源 | 对每个 15cm 外轮廓 `cv2.minAreaRect` 拟合 OBB,**不额外加 padding**(15cm 已在掩膜内) |
| 生成时机 | **首次加载就生成**;并**随 mask 修改而更新**(与现有 15cm 轮廓更新时机一致:加载读盘 / 保存后异步重算) |
| 首次加载磁盘无 Repair15 | 用当前 mask + 服务端 PPM **后台现算**一份用于显示+拟合 |
| 重新生成与手动编辑的关系 | 已有 bbox 时,**弹窗确认后全部重拟合**(取消则保留) |
| 自动 bbox 性质 | 与手动 OBB 完全同质:存 bbox.json、bbox 模式可编辑、计入 `bboxAreaMm2` 并集面积 |

## 架构 / 组件

### 1. 纯函数 `bboxes_from_contours`(`core/bbox/oriented_box.py`)
```
bboxes_from_contours(contours, min_area_px=1.0) -> list[OrientedBox]
```
- 对每个外轮廓(findContours 的点集,image 坐标)`cv2.minAreaRect` → `(cx,cy),(w,h),angle` → `OrientedBox`。
- 跳过退化轮廓(点 < 3、w/h ≤ 0、面积 < `min_area_px`)。
- **不加 padding**(15cm 已包含在 repair15 掩膜里)。
- 从 `labeling_tool.core.bbox` 导出。纯函数,易单测。

### 2. 默认显示 15cm(`image_canvas.py` + UI)
- `image_canvas.__init__`: `self.show_repair15 = True`(原 False)。
- 启动时把 `_btn_show_repair15` 的勾选态同步为 True(主窗口 UI 构建完成后 `setChecked(True)`),保证按钮选中态与画布一致。

### 3. 自动 bbox 同步逻辑(`core/window/main_window.py`)
新增 `_maybe_auto_bbox(token: str)`:在 **repair15 轮廓刚被设置之后**调用。
- 仅当 `token == 当前文件名` 且画布有 `repair15_contours` 时处理。
- 计算 `new = bboxes_from_contours(self.canvas.repair15_contours)`。
- **画布当前无 bbox** → 直接采用 `new`(静默),标记该图 bbox 已编辑(以便下次保存持久化),刷新。
- **已有 bbox 且本次属于"mask 编辑后的重算"**(由 `self._offer_refit_for == token` 标记)→ **弹窗确认**`bbox_refit_confirm`:确认则替换为 `new` + `bbox_edited`;取消则保留。处理后清除该标记。
- 其它情况(已有 bbox 且非编辑重算,例如普通加载)→ 不动(尊重已存的 bbox,不弹窗)。

调用点:
- **`_show_image`(加载)**:读 `Repair15/<name>.png` → `set_repair15` → `_maybe_auto_bbox(filename)`(此时 `_offer_refit_for` 未设 → 仅 fit-if-empty,不弹窗)。
  - 若磁盘**无** Repair15 但有 mask 且 `current_scale>0` → 走与保存相同的**异步派生生成**(highlight+repair15);完成回调里 `set_repair15` 后再 `_maybe_auto_bbox`(同样 fit-if-empty)。
- **`_on_derived_ready(token, hi, r15)`(异步完成)**:`set_repair15` 之后调用 `_maybe_auto_bbox(token)`。
- **`_save_all_artifacts`**:当**本图 mask 被编辑**且**已存在 bbox**时,派发派生生成前设 `self._offer_refit_for = filename`,使其完成回调走"弹窗重拟合"。

> 复用现有异步派生设施(`DerivedMaskRunnable` / `_derived_signals` / `_on_derived_ready`),distance transform 在后台线程,**不卡界面**。把 `_show_image` 里"无 Repair15 则派发生成"与保存里的派发抽到一个小helper `_dispatch_derived(filename, crack, spall, scale)` 复用。

### 4. bbox 编辑
自动 bbox 即普通 OBB,bbox 模式下增删改与手动一致;手动画 bbox(from_clicks,带 padding)保留不变。下游 `bboxAreaMm2`(并集)自动涵盖。

## 数据流
```
加载图片 → mask 显示
  → repair15:读盘 or (无则) 后台用 mask+PPM 现算 → set_repair15(轮廓)
  → _maybe_auto_bbox: 无 bbox 则按轮廓静默拟合
改 mask → 保存 → (mask 编辑且已有 bbox 时置 _offer_refit_for)
  → 后台重算 repair15 → _on_derived_ready → set_repair15
  → _maybe_auto_bbox: 弹窗确认 → 全部重拟合 / 保留
bbox 模式:自由编辑这些 OBB(与手动同质)→ 保存进 bbox.json
```

## 错误处理 / 边界
- 无轮廓(空 repair15)→ `_maybe_auto_bbox` 直接返回,不动 bbox。
- PPM ≤ 0(无比例尺)→ 不生成 repair15、不自动 bbox(与现有 repair15 行为一致)。
- 异步回调用 token 防过期(切图后旧结果不污染当前图,沿用现有逻辑)。
- 弹窗仅在"mask 编辑后的重算且已有 bbox"时出现,普通加载/切图不弹窗。

## i18n
新增键(三语):`bbox_refit_confirm_title`、`bbox_refit_confirm`(正文,如"15cm 영역이 바뀌었습니다. bbox를 다시 생성할까요? (수동 편집 사라짐)")。

## 测试
- `bboxes_from_contours`:合成轮廓(单个矩形→1 个 OBB、尺寸≈轮廓;多个→多个;退化→跳过)纯函数单测。
- 默认 `show_repair15 == True`(画布单测)。
- `_maybe_auto_bbox` 的 fit-if-empty / 重拟合分支:离屏冒烟(有真实数据本地验证;不入 CI 套件因依赖会话数据)。

## 不做(YAGNI)
- 不做"区分 auto vs 手动 bbox 的逐框合并"(用户选了"弹窗确认后全部重拟合")。
- 不改手动 from_clicks 画法(仍带 15cm padding)。
- 不改 repair15 掩膜本身的生成算法(仍 distance transform 填充)。

## 受影响文件
- 修改:`core/bbox/oriented_box.py`(+`bboxes_from_contours`)、`core/bbox/__init__.py`(导出)、
  `core/canvas/image_canvas.py`(`show_repair15` 默认 True)、`core/window/main_window.py`
  (`_maybe_auto_bbox`/`_dispatch_derived`/`_show_image`/`_on_derived_ready`/`_save_all_artifacts`/`_offer_refit_for` + 启动同步 toggle)、`core/i18n.py`(2 键×3 语)。
- 新增测试:`tests/test_bboxes_from_contours.py`。
