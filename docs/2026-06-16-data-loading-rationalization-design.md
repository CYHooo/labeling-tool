# labeling_tool 数据结构与加载方式合理化 设计

- 日期:2026-06-16
- 状态:已批准,待实现计划
- 分支:accelerate(改动随后同步到独立仓库 `labeling-tool`)

## 背景

`labeling_tool` 的数据加载经多次修复后积累了复杂度与隐患:

- **`Rebuilt/` 缓存层**先后引发 4 类 bug:盖住 `Labeling/` 编辑、丢 `G`(spalling)通道、缓存过期(session_18)、把噪声膨胀成假裂缝。
- **`find_mask_path` 按 stem 模糊匹配**(试 `_mask/_crack/...` 多后缀 + 多扩展名 + 扫目录),脆弱,且是早期"命名配对" critical bug 的根源。V-API 工具里文件名其实确定。
- **三处 rebuild 输出代码重复**(预构 / 按需 / 重建按钮),G 保留逻辑要在三处各写一遍。
- **`_show_image` 又长又杂**,加载/重建/ArUco/bbox 混在一起,难测试。

## 已确认的决定

1. **保留 `Rebuilt/` 强度精化层**(不删、不改成按需)。
2. **缓存失效按 mtime 自动判定**:`Detected/` 比 `Rebuilt/` 新 → 自动重算;否则复用。`Labeling/` 永远优先于显示。

## 数据结构(不变)

```
labeling_tool/data/session_{id}/
├── Origin/      stitched_{ts}.jpg
├── Detected/    stitched_{ts}_mask.png     R=crack(mfuser), G=spalling(人工新增)
├── Rebuilt/     stitched_{ts}_mask.png     R=强度精化crack, G=保留的spalling
├── Labeling/    stitched_{ts}_mask.png + stitched_{ts}.bbox.json
├── manifest.json
└── vapi.log
```
掩膜编码不变:3 通道 BGR PNG,R=crack,G=spalling,B 不用。S3 上传名仍为 `mask_{ts}.png`(仅在上传边界转换,不变)。

## 组件设计

### 新模块 `labeling_tool/session/mask_store.py`(纯函数,无 Qt 依赖,可单测)

**确定性命名**(替代 `find_mask_path`;现有磁盘数据已全部符合,无需迁移):

```python
def mask_name(origin_filename: str) -> str:   # f"{Path(origin_filename).stem}_mask.png"
def bbox_name(origin_filename: str) -> str:   # f"{Path(origin_filename).stem}.bbox.json"
```

**显示掩膜解析**(优先级 + mtime 失效;只做 path/exists/mtime 判断,纯逻辑):

```python
def resolve_display_mask(*, labeling_dir, rebuilt_dir, detected_dir,
                         origin_filename) -> tuple[Path | None, str]:
    """
    返回 (mask_path | None, source):
      1. Labeling/{mask_name} 存在            -> (path, "labeling")
      2. Rebuilt/{mask_name} 存在 且 新鲜      -> (path, "rebuilt")
         新鲜 := Detected/{mask_name} 不存在 或 Rebuilt.mtime >= Detected.mtime
      3. 否则                                 -> (None, "needs_rebuild")
    任一 dir 为 None 视为该层不可用。
    """
```

**唯一的 rebuild 输出构造**(被预构 / 按需 / 重建按钮三处共用):

```python
def build_rebuilt_rgb(origin_bgr, coarse_raw) -> np.ndarray:
    """3 通道 BGR:R=强度精化 crack,G=原样保留的 spalling。
    coarse_gray = coarse_raw[...,2] if 3ch else coarse_raw
    guided,_,_ = process_one(origin_bgr, coarse_gray, compute_length=False)
    rgb[...,2] = guided
    若 coarse_raw 为 3 通道:G 通道(必要时按最近邻缩放到 guided 尺寸)写入 rgb[...,1]
    """
```

### 加载流程改造(`_show_image` 瘦身)

```python
path, source = resolve_display_mask(labeling_dir=self.output_dir,
        rebuilt_dir=self.rebuilt_dir, detected_dir=self.detected_dir,
        origin_filename=filename)
if source == "needs_rebuild":
    coarse_raw = cv2.imread(Detected/{mask_name}, IMREAD_UNCHANGED)
    if coarse_raw is not None:
        rgb = build_rebuilt_rgb(origin_bgr, coarse_raw)
        write Rebuilt/{mask_name}; path = 该路径; source = "rebuilt(from detected)"
    else:
        path = None  # 无掩膜,空白
origin, crack, spall = load_origin_and_masks(origin_path, path)  # 不变
bbox = load_bboxes(self.output_dir / bbox_name(filename))
```
三级优先与现在一致;去掉模糊匹配;加入 mtime 失效;rebuild 失败回退到直接加载 Detected(保持现有健壮性)。

### 三处 rebuild 合一

- `rebuild_cache._prebuild_one`、`_show_image` 按需重建、`_on_rebuild_force` **全部改用 `build_rebuilt_rgb`**。
- 预构跳过规则:`resolve` 判定 Rebuilt 新鲜则跳过,过期则重算(落实 mtime 自动失效)。
- `_on_rebuild_force`(用户显式点重建):coarse 源仍是 `Labeling/ 若存在否则 Detected/`,结果同时覆盖 `Labeling/` 与 `Rebuilt/`(保持现有"在编辑上再精化"语义)。

### 保存与上传走确定性命名

- `_save_all_artifacts`:Labeling 掩膜固定写 `mask_name(filename)`;移除 `_mask_filename` 字典(原本用于"记住加载掩膜名以便保存",现在确定性命名后不再需要)。bbox 写 `bbox_name(filename)`。
- `ui/upload_worker._build_items` 与 `_edited_filenames`:用 `mask_name(filename)` 直接定位 Labeling 掩膜,不再 `find_mask_path`。

### 兼容性

- 现有磁盘数据已全部是 `{stem}_mask.png` / `{stem}.bbox.json`,确定性解析与之吻合,**无需迁移**。
- `find_mask_path` 保留在 `core/mask_io.py`(不删除,避免触动其它),但 V-API 加载/保存/上传路径不再调用它。

## 错误处理

- `resolve_display_mask` 仅做存在性/mtime 判断,不抛异常;dir 为 None 或文件缺失时按缺失处理。
- 按需 rebuild 失败:回退为直接加载 `Detected/{mask_name}`(沿用现状),并在状态栏报错。
- mtime 读取对缺失文件返回"需重建",不崩。

## 测试

- `mask_store` 纯函数单测:
  - `mask_name`/`bbox_name` 命名正确。
  - `resolve_display_mask`:Labeling 优先;无 Labeling 时 Rebuilt 新鲜→rebuilt;Rebuilt 过期(Detected 更新 mtime)→needs_rebuild;全缺→needs_rebuild。
  - `build_rebuilt_rgb`:R 精化非空、G 保留(给含 G 的 coarse,输出 G 非零);coarse 与 origin 尺寸不一致时正确缩放。
- 现有 60 项测试保持通过。
- offscreen 端到端:构造含 Detected+Rebuilt(过期)+Labeling 的工作区,验证加载选择正确(Labeling 优先、过期 Rebuilt 触发重建并带回 G)、保存写 `{stem}_mask.png`、上传读取正常。

## 影响文件

- 新增:`labeling_tool/session/mask_store.py`、`labeling_tool/tests/test_mask_store.py`
- 修改:`labeling_tool/core/window/main_window.py`(`_show_image`/`_on_rebuild_force`/`_save_all_artifacts`)、`labeling_tool/rebuild_cache.py`、`labeling_tool/ui/main_window.py`、`labeling_tool/ui/upload_worker.py`
- 行为不变项:保留精化、R=crack/G=spalling 语义、三级显示优先级、S3 上传命名、crack 细化/spalling 面状、上传 metrics。

## 非目标(YAGNI)

- 不删除 `Rebuilt/` 层、不改 manifest 结构、不动 V API 协议与上传逻辑。
- 不删除 `find_mask_path`(仅停用于本工具路径)。
- 不引入 manifest 哈希/版本字段(mtime 已够)。
