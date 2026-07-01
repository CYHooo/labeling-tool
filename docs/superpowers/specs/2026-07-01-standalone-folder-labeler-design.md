# 独立离线文件夹标注版(standalone-local-labeler)

日期:2026-07-01
状态:已确认设计,待实现(新分支)

## 背景 / 目标

隔离一份**本地精简版**标注工具,用于在其他相似数据上做二次整理:
- **去掉**:登录/验证、fetch、下载、API client、上传、manifest、highlight、15cm(repair15)、Result 导出。
- **数据载入**:选择 **image 文件夹** + **mask 文件夹**(替代登录→fetch→下载)。
- **保留一致**:crack(1)/spalling(2) 整数标签、画笔、bbox、SAM(含裁块/多块累加)、比例尺/测量 —— 与当前代码功能一致,不做额外功能开发。
- 放在**新分支** `standalone-local-labeler`,推送到远程;`main`(在线版)不改。

## 已确认决策

| 决策点 | 选择 |
|--------|------|
| 类别 | 与当前一致:整数标签 PNG(0 背景 / 1 crack / 2 spalling),复用现有 `encode_label_mask`/`decode_mask` |
| 文件配对 | **同 stem 不同后缀**:image `foo.jpg` ↔ mask `foo.png`(mask 取该 stem 下的图片文件) |
| 保存位置 | **单独输出目录(非破坏)**:默认 `<image父目录>/Labeling/`;保存为 `output/foo.png`(与输入同名镜像) |
| 保留工具 | 画笔 crack/spalling、bbox、SAM、比例尺/测量 全保留 |
| 15cm/highlight | 优雅无效化(不设 highlight_dir/repair15_dir → 不生成/不显示/自动 bbox 不触发) |
| core 改动 | 仅**行为不变**地抽取 2–3 个可重写钩子;在线版默认行为完全不变 |

## 架构 / 组件

### 1. core `MainWindow` 可重写钩子(behavior-preserving)
在 `core/window/main_window.py` 抽出以下方法,**默认实现 = 现有行为**,供子类重写:
- `_build_image_list() -> list[str]`:默认 = 现有 `_reload_data` 里扫描 `origin_dir` 的逻辑。
- `_display_mask_path(filename) -> tuple[str|None, str]`:默认 = `mask_store.resolve_display_mask(labeling_dir=output_dir, detected_dir=detected_dir, origin_filename=filename)`。(`_show_image` 改调此钩子。)
- `_save_mask_path(filename) -> Path`:默认 = `output_dir / mask_store.mask_name(filename)`(`<stem>_mask.png`)。(`_save_all_artifacts` 保存掩膜处改调此钩子。)

> 仅抽取+改调用点,**在线版 `ViewerMainWindow` 行为不变**(默认钩子返回原路径/原列表)。bbox 命名(`<stem>.bbox.json`)与 Result/派生的目录门控保持不变。

### 2. `ui/local_main_window.py` — `LocalMainWindow(MainWindow)`
- 构造:`image_dir`, `mask_dir`, `output_dir`。设 `origin_dir=image_dir`;`detected_dir=mask_dir`;`output_dir=output_dir`;`highlight_dir=repair15_dir=None`;`export_result_on_save=False`。
- 注入 SAM:复用现有 `_init_sam` 逻辑(`MobileSamPredictor.try_load()` → `canvas.set_sam_predictor`;不可用则置灰,与在线版一致)。
- 重写钩子:
  - `_build_image_list()`:扫描 `image_dir` 里的图片(`.jpg/.jpeg/.png/.bmp`,大小写不敏感),按名排序;仅保留在 `mask_dir` 有同 stem 图片文件的项(无配对掩膜的跳过,记 vlog)。
  - `_display_mask_path(filename)`:优先 `output_dir/<stem>.png`(已编辑过的),否则 `mask_dir/<stem>.png`;都无则 `(None,"none")`。
  - `_save_mask_path(filename)`:`output_dir/<stem>.png`。
- **无** manifest / API / 上传按钮 / `_resolve_scale` 覆盖(用 core 默认 ArUco;新数据无标记时 scale=none,无害)。

### 3. `ui/folder_dialog.py` — 启动选文件夹
- 两个必选:image 文件夹、mask 文件夹;一个可选输出(默认 `<image父目录>/Labeling/`)。
- 校验目录存在;实时显示"可配对张数 = image 中有同 stem 掩膜的数量"。
- 确认后暴露 `image_dir/mask_dir/output_dir`。

### 4. `app_local.py` — 入口
选文件夹对话框 → `LocalMainWindow(image_dir, mask_dir, output_dir)` → 显示。应用同一暗色主题。保留原 `app.py` 不动。

## 配对/命名辅助(纯函数,可单测)
`pair_by_stem(image_dir, mask_dir) -> list[(image_filename, mask_path|None)]`:
- 扫描 image_dir 图片;对每个 `stem`,在 mask_dir 找 `stem.*`(优先 `.png`)图片文件;返回配对(无掩膜=None)。
- 供 `_build_image_list` 与对话框计数复用。放 `session/local_pairing.py`。

## 数据流
```
选 image+mask 文件夹 → pair_by_stem → image_files(有配对的)
逐张:origin=image_dir/foo.jpg;mask=output_dir/foo.png 或 mask_dir/foo.png → decode_mask(0/1/2)
编辑(画笔/SAM/bbox/比例尺)→ encode_label_mask → 存 output_dir/foo.png(非破坏)
```

## 错误处理 / 边界
- image 有、mask 无 → 该项跳过(vlog),不进列表(或进列表但空掩膜?—— 取"跳过无掩膜项",避免误标)。
- 掩膜尺寸与图片不一致 → 复用已有 `_mask_to_origin`(canvas set_image 已对齐)。
- 输出目录不存在 → 保存时 `mkdir(parents=True)`(现有 `_save_all_artifacts` 已 mkdir output_dir)。
- SAM 模型缺失 → SAM 按钮置灰(与在线版一致)。

## 测试
- `pair_by_stem` 单测:同 stem 配对、多后缀优先 png、无掩膜项标 None、大小写/排序。
- 保存往返:`encode_label_mask`→写 `output/foo.png`→`decode_mask` 还原 crack/spalling 一致。
- core 钩子默认值不变:`_save_mask_path`/`_display_mask_path` 默认仍返回 `<stem>_mask.png`/resolve_display_mask 结果(保护在线版)。
- 离屏冒烟:临时 image/mask 文件夹(1–2 张合成图+掩膜)→ `LocalMainWindow` → `_build_image_list` 非空 → `_show_image(0)` 载入 → 编辑并 `_save_all_artifacts` → `output/foo.png` 存在且能 decode。

## 不做(YAGNI)
- 不加多类别配置(就是 crack/spalling,与当前一致)。
- 不动在线版(login/fetch/api/upload/manifest 保留在 main 与本分支,standalone 不用)。
- 不做输出命名自定义(固定 `output/<stem>.png`)。
- 不重写比例尺来源(用 core 默认;无 manifest 即无 server PPM)。

## 受影响文件(新分支)
- 修改:`core/window/main_window.py`(抽 3 个可重写钩子 + 改调用点,行为不变)。
- 新增:`ui/folder_dialog.py`、`ui/local_main_window.py`、`app_local.py`、`session/local_pairing.py`(`pair_by_stem`)。
- 新增测试:`tests/test_local_pairing.py`、`tests/test_local_main_window.py`(离屏)。
- 分支:`standalone-local-labeler`,推送到 origin。
