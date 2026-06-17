# 균열 하이라이트 + 15cm 경계 派生掩膜 + 上传升级 v1.0.8

日期:2026-06-17
状态:已确认设计,待实现

## 背景

按 api-reference **v1.0.8**,本地 Photo Viewer 编辑确认时需随 mask 一并上传两张派生掩膜:
- **highlight**(`high_{ts}.png`):균열 하이라이트,让裂缝位置在 web 端更显眼。
- **repair15**(`15_{ts}.png`):15cm 경계 검증,**0=배경, 255=경계**;web 端修改 bbox 时核对 15cm 覆盖。

v1.0.8 已把上传契约改为:V2 presigned 每张图可发 mask+high+repair15 三件;V3 按 mask→high→15 各 PUT 一次;
V4 的 `highlightS3Key`、`repair15S3Key` 均为**必填**。当前工具(`upload_worker`/`upload_session_cli`)只产出并上传 mask,需升级。

派生掩膜在 web 端实时计算太慢,故移到本地生成、并**在本地画布上可视化**,再上传到 web 数据库供调用。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 生成架构 | 集中式 `core/derived_masks.py`(纯函数),保存时写两个本地文件夹 |
| highlight 内容 | **所有类别**(crack+spalling)各外扩 **10px**,按 0/1/2 重编码,**crack 优先** |
| repair15 文件内容 | 前景并集外扩 **15cm**(round(15×px/cm) px)后**整体填充 255**(0=背景) |
| 上传范围 | 整条链路升级到 v1.0.8(V2 三件 / V3 三 PUT / V4 两新必填键) |
| 缺文件 | 上传时 mask/high/15 任一缺失则**跳过该图** |
| 画布显示 | 两个 toggle(默认关);**highlight 黄色光晕**、**repair15 只画外轮廓线** |
| 显示来源 | 读已保存 HighLight/Repair15 文件;**保存时用刚生成的数组即时刷新** |

## 架构

### 1. 派生掩膜生成 `core/derived_masks.py`(纯函数 + 单测)

- `build_highlight(crack, spalling) -> np.ndarray`:对每个类别区域 `cv2.dilate` 10px(椭圆核 21×21),
  再以 `CLASS_LABELS` 重编码为单通道 0/1/2;**先写 spalling(2)后写 crack(1)** → crack 优先。两层皆 None 抛 `ValueError`。
- `build_repair15(crack, spalling, px_per_cm) -> np.ndarray`:前景并集(crack>0 ∪ spalling>0)→
  `cv2.dilate` `round(15 * px_per_cm)` px → 输出单通道 `uint8`,前景处 **255、背景 0(填充,非轮廓)**。

> 复用 `core/constants.CLASS_LABELS`;不依赖已删的 rebuild。

### 2. 工作区与命名

- `workspace.py`:新增 `highlight_dir`(`HighLight/`)、`repair15_dir`(`Repair15/`),并入 `ensure()`。
- `naming.py`:新增
  - `high_filename(ts) -> "high_{ts}.png"`、`repair15_filename(ts) -> "15_{ts}.png"`;
  - `high_s3_key(sid, ts) -> "results/{sid}/masks/high_{ts}.png"`、`repair15_s3_key(sid, ts) -> "results/{sid}/masks/15_{ts}.png"`。
- 本地文件名沿用 `mask_store.mask_name`(`{stem}_mask.png`),分别落在两个新文件夹(与 Labeling 一致)。

### 3. 保存时生成 + 即时刷新画布(`main_window`)

`_save_all_artifacts` 写完 mask 后追加:
- `label_hi = build_highlight(mc, ms)` → 写 `HighLight/{stem}_mask.png` → `self.canvas.set_highlight(label_hi)`。
- 若 `self.current_scale`(px/cm)有效:`r15 = build_repair15(mc, ms, current_scale)` → 写 `Repair15/{stem}_mask.png`
  → `self.canvas.set_repair15(r15)`;无 scale 则跳过(该图 px≤0 本就不上传),并 `set_repair15(None)`。

主窗口新增 `highlight_dir`/`repair15_dir` 状态(`_sync_output_dir` 由 `origin_dir.parent` 派生,
`ui/main_window` 从 `workspace` 取),与既有 `output_dir`/`result_dir` 并列。

### 4. 画布显示(`ImageCanvas` + `overlay_painter`/新绘制)

- 新状态:`highlight_mask`(0/1/2 或 None)、`repair15_contours`(图像坐标多边形列表或 None)、
  `show_highlight`/`show_repair15`(默认 False)。
- `set_highlight(arr)`:存数组,作废叠加缓存。
- `set_repair15(arr)`:对 `arr`(0/255 填充)做 `cv2.findContours(RETR_EXTERNAL)` 得外轮廓,存为图像坐标点集
  (一次性,非每帧);`None` 清空。
- `paintEvent`:
  - `show_highlight` 且有 `highlight_mask` → 把其前景(>0)以**黄色 (255,255,0)**、不透明度 ~0.35 半透明叠加
    (复用现有 overlay 的"裁剪→缩放到 widget→合成"机制,**按视口缓存**,与主 mask 叠加同款,平移/缩放不每帧重算)。
  - `show_repair15` 且有 `repair15_contours` → 用 `viewport.image_to_widget` 把外轮廓点映射后 `drawPolyline`
    (青色 (0,200,255),2px),**只画线不填充**(每帧画线,开销小)。
- `_show_image` 加载时:若 `HighLight/<name>`/`Repair15/<name>` 存在则 `imread` 后 `set_*`,否则 `set_*(None)`。

### 5. 主窗口 toggle 按钮(`ui_builder` + handlers + i18n)

- 侧栏新增两个可勾选 `QPushButton`:「하이라이트 표시」「15cm 경계 표시」。
- handler 翻转 `canvas.show_highlight`/`show_repair15` 并 `canvas.update()`。
- 新增 i18n 键(三语):`btn_show_highlight`、`btn_show_repair15`。

### 6. 上传升级到 v1.0.8

- `annotation_payload.build_annotation_item`:返回 item 增加 `highlightS3Key`、`repair15S3Key`
  (新增两个入参 `highlight_s3_key`、`repair15_s3_key`)。
- `api/uploader.upload_session`:bytes 源从单一 `mask_bytes_for(ts)` 改为 `bytes_for(ts) -> dict`(键 `mask`/`high`/`repair15`);
  每张图 presign **三件**(`mask_/high_/15_` 文件名)、按 **mask→high→15** PUT,再 register。
- `upload_worker._build_items` + `scripts/upload_session_cli`:对每张图读 `Labeling/`+`HighLight/`+`Repair15/` 三份字节;
  **任一缺失 → 跳过该图**(并记日志),与现有"缺 mask 跳过"一致;item 用 `naming.high_s3_key`/`repair15_s3_key`。
- `api/client` 的 V2/V3/V4 方法签名不变(V2 files 无需 `fileType`,服务端按 `mask_/high_/15_` 前缀区分;
  V4 多两个键由 item 透传)。

## 数据流

```
保存:  mask=encode(mc,ms) → Labeling/ ; high=build_highlight → HighLight/ ;
        repair15=build_repair15(...,scale) → Repair15/(有scale时) → 同时 set_* 刷新画布
加载:  读 Labeling|Detected 显示 mask ; 读 HighLight/Repair15 → set_*(供 toggle 显示)
上传:  每图 read 三份字节 → V2 presign×3 → V3 PUT mask→high→15 → V4(maskS3Key+highlightS3Key+repair15S3Key)
```

## 错误处理

- `build_repair15` 需 px/cm;无 scale 时不生成、不显示、该图不上传(px≤0 已跳过)。
- 上传:三件任一缺失跳过该图并 `vlog().warning`。
- `findContours` 在空 repair15(无前景)→ 空轮廓,显示为空,无异常。

## 测试

- 新增 `tests/test_derived_masks.py`:
  - `build_highlight`:外扩约 10px(前景像素数增加)、值域 ⊆{0,1,2}、crack 与 spalling 重叠处为 1(crack 优先);
  - `build_repair15`:输出 0/255、前景随 px/cm 增大而扩大、空输入→全 0;
  - 两者对 None 层的处理。
- 更新 `tests/test_upload_worker.py`、`tests/test_uploader.py`:三件 presign/PUT 顺序、item 含两新键、缺文件跳过;
  `tests/test_annotation_payload.py`:item 含 `highlightS3Key`/`repair15S3Key`。
- 画布渲染层(GUI)沿用现状不单测;生成函数全单测。

## 不做(YAGNI)

- 不实时重算 high/15(只在保存时生成)。
- 画布 repair15 不做填充显示(只外轮廓);highlight 不做逐类配色(统一黄色光晕)。
- 不动 `Result/`、Detected、画笔/计测、scale 检测逻辑。

## 受影响文件

- 新增:`core/derived_masks.py`、`tests/test_derived_masks.py`。
- 修改:`session/workspace.py`、`session/naming.py`、`core/window/main_window.py`、`core/window/ui_builder.py`、
  `core/i18n.py`、`core/canvas/image_canvas.py`、`core/canvas/overlay_painter.py`、`ui/main_window.py`、
  `annotation_payload.py`、`api/uploader.py`、`ui/upload_worker.py`、`scripts/upload_session_cli.py`。
- 测试更新:`test_upload_worker.py`、`test_uploader.py`、`test_annotation_payload.py`。
