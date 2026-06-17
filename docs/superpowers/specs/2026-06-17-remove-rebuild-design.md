# 移除 rebuild 子系统

日期:2026-06-17
状态:已确认设计,待实现

## 背景

EC2 下发的 AI 检测结果(`Detected/`)已是 AI 服务器端**做过 rebuilt 的最终结果**,labeling 工具不需要再做重建。当前工具里的"重建"子系统(把粗 AI 掩膜细化为 guided crack + 中心线、预构 `Rebuilt/` 缓存、加载时 rebuild-on-demand)是冗余的,应整体删除。

## 关键约束:两个"双用"工具必须保留(不能整包删 `core/rebuild/`)

盘点 `core/rebuild/` 的消费方发现两个与重建管线**无关**、但代码恰好放在该包里的工具,必须保留:

1. **`thin_stroke_into`**(`core/rebuild/thinning.py`)—— **画笔编辑**功能(画一笔→松开自动细化为 1px 中心线),`core/canvas/image_canvas.py` 依赖。
2. **`measure_length_px`**(`core/rebuild/length_centerline.py`)—— **crack 计测**用,`core/result/crack_metrics.py:55` 在上传算长度时依赖。

`thin_stroke_into` 的依赖闭包:`skeletonize_mask`、`prune_skeleton`、`_neighbor_count`(均在 thinning.py)。`measure_length_px` 自包含(仅 numpy/cv2)。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 范围 | 删除重建管线 + 预构 + `Rebuilt/` + rebuild-on-load + `build_rebuilt_label_mask` |
| 画笔细化 | **保留**(`thin_stroke_into` 迁出后继续工作) |
| `thin_stroke_into` 落点 | `core/canvas/stroke_thinning.py`(连同 `skeletonize_mask`/`prune_skeleton`/`_neighbor_count`) |
| `measure_length_px` 落点 | 内联进 `core/result/crack_metrics.py` |
| 加载显示 | `resolve_display_mask` 改为 **Labeling > Detected**(去掉 rebuilt 分支) |
| 顺序 | 本 spec 先做;highlight/15cm 特性在更干净的基础上单独做 |

## 架构

### 1. 迁出两个幸存工具(先迁后删)

- 新建 `core/canvas/stroke_thinning.py`,搬入 thinning.py 的 `skeletonize_mask`、`_neighbor_count`、`prune_skeleton`、`thin_stroke_into`(原样)。
  `image_canvas.py` 的导入从 `core.rebuild.thinning` 改为 `core.canvas.stroke_thinning`。
- 把 `measure_length_px`(length_centerline.py 第 52–64 行,原样)内联进 `core/result/crack_metrics.py`,
  删掉其 `from labeling_tool.core.rebuild import measure_length_px` 导入。

### 2. 删除重建管线与缓存

- 整删目录 `core/rebuild/`(`__init__.py`、`pipeline.py`、`width_fit.py`、`length_centerline.py`、`thinning.py`)。
- 删 `labeling_tool/rebuild_cache.py`。

### 3. `session/mask_store.py`

- 删 `from labeling_tool.core.rebuild import process_one`、`build_rebuilt_label_mask`、`_rebuilt_is_fresh`。
- `resolve_display_mask` 改签名去掉 `rebuilt_dir`,逻辑改为:
  - `Labeling/<name>` 存在 → `(path, "labeling")`;
  - 否则 `Detected/<name>` 存在 → `(path, "detected")`;
  - 否则 `(None, "none")`。
- 更新模块 docstring(去掉 Rebuilt/重建相关描述)。

### 4. `session/workspace.py`

- 删 `rebuilt_dir` 属性,并从 `ensure()` 的创建列表移除。

### 5. 对话框预构

- `ui/dialog_helpers.py`:删 `run_prebuild` 及对 `rebuild_cache` 的导入。
- `ui/login_dialog.py`(离线打开)、`ui/fetch_dialog.py`(在线拉取):删 `run_prebuild` 调用与导入;打开/拉取后直接进主界面(不再预构)。进度条仅用于下载阶段(fetch)。

### 6. `core/window/main_window.py`

- 删 `self.rebuilt_dir` 状态与 `_sync_output_dir` 里的 `rebuilt_dir` 赋值。
- 两处 rebuild-on-load(无 Labeling 时从 Detected 重建并写 `Rebuilt/`)简化为**直接用 Detected**:
  `resolve_display_mask` 返回 `detected` 时,加载该 Detected 掩膜显示(经 codec 解码),不再调用 `build_rebuilt_label_mask`、不再写 `Rebuilt/`、不再有 rebuilding 状态文案。
- `resolve_display_mask(...)` 调用同步去掉 `rebuilt_dir=` 实参。

### 7. `core/i18n.py`

- 删不再使用的键:`rebuild_done`、`rebuild_failed`、`status_rebuilding`(三种语言)。

## 数据流(删除后)

```
拉取/打开:V1 下载 stitched+Detected → manifest → 直接进主界面(无预构)
加载显示:  Labeling/<name> 有则用,否则 Detected/<name>(AI 最终结果)→ codec 解码 → 显示/编辑
保存:      编辑后 → encode 整型标签 → Labeling/(不变)
画笔:      画一笔 → thin_stroke_into(迁出后)→ 1px 中心线(不变)
计测:      crack_metrics 用内联的 measure_length_px(不变)
```

## 测试

- 删 `tests/test_rebuild_cache.py`。
- `tests/test_stroke_thinning.py`:导入改为 `from labeling_tool.core.canvas.stroke_thinning import thin_stroke_into`(用例不变)。
- `tests/test_mask_store.py`:删 `test_build_rebuilt_label_*` 两例;`resolve_display_mask` 用例改为新签名(去 `rebuilt_dir`)与 Labeling>Detected 语义(新增 detected 命中、无掩膜两种)。
- `tests/test_workspace.py`:去掉 `rebuilt_dir` 断言(布局与 ensure 列表)。
- crack_metrics 相关测试不变(measure_length_px 仍在,只是内联进 crack_metrics.py);经核查无测试直接 import 该符号,故无需改测试导入。
- 全量 pytest 保持绿。

## 不做(YAGNI)

- 不动画笔细化行为、crack 计测算法、Detected/Labeling/Result。
- 不动上传链路(highlight/15cm 特性在另一个 spec 做)。
- 不写历史 `Rebuilt/` 目录清理脚本(残留的本地 Rebuilt/ 无害,不再被读)。

## 受影响文件

- 新增:`core/canvas/stroke_thinning.py`。
- 删除:`core/rebuild/`(整个目录)、`rebuild_cache.py`、`tests/test_rebuild_cache.py`。
- 修改:`core/canvas/image_canvas.py`、`core/result/crack_metrics.py`、`session/mask_store.py`、
  `session/workspace.py`、`ui/dialog_helpers.py`、`ui/login_dialog.py`、`ui/fetch_dialog.py`、
  `core/window/main_window.py`、`core/i18n.py`。
- 测试更新:`tests/test_stroke_thinning.py`、`tests/test_mask_store.py`、`tests/test_workspace.py`。
