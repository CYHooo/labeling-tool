# 掩膜存储格式:RGB 通道 → 整型类别标签

日期:2026-06-17
状态:已确认设计,待实现

## 背景

当前 crack / spalling 掩膜以**三通道 BGR PNG**存储:R 通道=crack、G 通道=spalling(非裂缝)。
读写散落在多处(`mask_io` 解码、`main_window._save_all_artifacts` 编码、`mask_store.build_rebuilt_rgb`
重构、`upload_worker` 上传解码)。

需求:改为**单通道整型类别标签**——背景=0、crack=1、spalling=2,将来追加的类别顺延(3、4…)。

**关键约束**:`upload_worker.py` 上传时直接 `mask_path.read_bytes()` 上传 Labeling/ 里保存的
原始 PNG 字节,所以**本地保存格式 = 上传到 EC2 的格式**。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 范围 | **整条链路**(本地保存 + 上传 EC2)都改成整型标签 |
| 内部表示 | **不重构**:画笔/叠加/计测内部仍用双二值层,只在磁盘读写边界换格式(方向 A) |
| 重叠优先级 | 同一像素既 crack 又 spalling 时 **crack 胜**(写 1) |
| 读取兼容 | **自动判别**:三通道按旧 RGB 解,单通道按整型标签解,旧版单通道二值(0/255)按文件名兜底 |
| Rebuilt 缓存 | 一并改成整型(与 Labeling 一致);旧 RGB 缓存靠自动判别仍可读 |
| PNG 取值 | **字面值 0/1/2**(非调色板) |

## 架构(方向 A:集中式 codec,内部不重构)

整型标签本质是一种**磁盘编码**。只在读写边界引入一个集中的编解码模块,所有读写点路由到它;
画笔交互、叠加颜色、crack 计测等内部管线保持双二值层、行为不变。

### 组件

**1. 类别 ↔ 标签注册表(`core/constants.py`)**

唯一真源,将来加类别只改这里:
```python
BACKGROUND_LABEL = 0
CLASS_LABELS: dict[str, int] = {"crack": 1, "spalling": 2}   # 追加: {"xxx": 3}
LABEL_TO_CLASS: dict[int, str] = {v: k for k, v in CLASS_LABELS.items()}
```
现有 `CATEGORIES = ("crack", "spalling")` 顺序与之一致(保留)。

**2. 编解码模块(`core/mask_codec.py`,新增,纯函数 + 单测)**

- `encode_label_mask(crack: np.ndarray | None, spalling: np.ndarray | None) -> np.ndarray`
  返回单通道 `uint8`。背景=0;先写 spalling(2)再写 crack(1),故**重叠处 crack 覆盖 spalling**。
  尺寸取任一非空层;两者皆空时由调用方决定是否写(沿用现有"皆空不写"逻辑)。
- `decode_mask(raw: np.ndarray, *, mask_path: str | None = None) -> tuple[crack, spalling]`
  返回两个 0/255 `uint8` 层(或 None)。**自动判别**:
  - `raw.ndim == 3` → 旧 RGB:crack = R(`[...,2]`)>0、spalling = G(`[...,1]`)>0。
  - `raw.ndim == 2` 且 `raw.max() <= len(CLASS_LABELS)` → 整型标签:crack = (raw==1)、spalling = (raw==2)。
  - `raw.ndim == 2` 且含 255(旧版二值)→ 按 `mask_path` 文件名判类(保留现有 `_spalling` 兜底)。

> 判别阈值说明:整型标签最大值 ≤ 类别数(当前 2);旧版二值用 255。两者范围不重叠,可靠区分。
> 全背景(max=0)的空标签图与空二值图解码结果都是空,语义一致,无歧义。

**3. 接入点(全部改走 codec,仅换格式,行为不变)**

| 位置 | 现状 | 改为 |
|------|------|------|
| `main_window._save_all_artifacts`(~319–333) | 手拼 BGR 后 `imwrite` | `encode_label_mask(mc, ms)` → `imwrite` 单通道 |
| `mask_io.load_origin_and_masks`(34–62) | 内联 RGB/二值解码 | `decode_mask(raw, mask_path=...)` |
| `mask_store.build_rebuilt_rgb` | 返回 RGB(R=精修 crack、G=保留非裂缝) | 重命名 `build_rebuilt_label_mask`,返回单通道标签(crack=1、保留类=2,crack 优先) |
| `rebuild_cache._prebuild_one`(50–51) | `build_rebuilt_rgb` + `imwrite` | 新函数 + `imwrite` 单通道 |
| `main_window` 重构落盘(~474–480、~618–622) | `build_rebuilt_rgb` + `imwrite` | 新函数 + `imwrite` 单通道 |
| `upload_worker._build_items`(59–61) | `bgr[...,2]`/`bgr[...,1]` 取 crack/spall | `decode_mask(raw, mask_path=...)` 取两层 |

> 上传字节仍是 `mask_path.read_bytes()`——因保存已是整型,上传天然即整型,**无需额外转换**。

**4. 不动的部分**
- AI 下发的 `Detected/`(RGB)只读不写,经 `decode_mask` 自动判别。
- `Result/<stem>.png` 是给人看的彩色预览(`result_image.py`),与标签格式无关,保持现状。
- 画笔交互、叠加颜色映射、crack 计测内部逻辑不变。

## 数据流

```
保存:  canvas(crack 0/255, spalling 0/255) ─encode_label_mask→ 单通道 0/1/2 PNG → Labeling/
读取:  Detected/Rebuilt/Labeling PNG ─decode_mask(自动判别)→ (crack, spalling) → 显示/编辑
重构:  origin + coarse(RGB 或整型) ─build_rebuilt_label_mask→ 单通道 0/1/2 → Rebuilt/
上传:  Labeling/ 单通道 PNG ── read_bytes() ──→ EC2(整型);并 decode_mask 出 crack/spall 算 metrics
```

## 错误处理 / 兼容

- 旧 RGB(AI Detected、历史 Labeling/Rebuilt)读取时自动识别,下次保存即写成整型——**无需迁移脚本**。
- 旧版单通道二值(0/255)经文件名兜底,行为与现状一致。
- codec 对 None 层、空层、尺寸不一致(沿用 `build_rebuilt` 现有 resize 逻辑)做防御。

## 测试

- 新增 `tests/test_mask_codec.py`:
  - encode→decode 往返(crack/spalling 分别、同时);
  - **crack 优先**:crack 与 spalling 重叠像素 encode 后为 1,decode 出 crack 含该像素、spalling 不含;
  - decode 自动判别三种输入:三通道 RGB、单通道整型、单通道旧二值(0/255 + 文件名)。
- 更新依赖旧 RGB 断言的现有测试:`test_mask_store.py`(`build_rebuilt_rgb` 两例 → 新函数,断言标签值 1/2 存在)、
  `test_rebuild_cache.py`、`test_upload_worker.py`(构造的 mask 与解码断言)。其余按需。
- GUI 接入点沿用现状不单测。

## 不做(YAGNI)

- 不重构内部为单一标签数组(画笔/叠加/计测保持双层)。
- 不做调色板 PNG。
- 不做历史掩膜批量迁移脚本(读时自动兼容 + 写时升级即可)。
- 不改 AI 端 Detected 产出格式、不改 `Result/` 预览。

## 受影响文件

- 新增:`core/mask_codec.py`、`tests/test_mask_codec.py`。
- 修改:`core/constants.py`、`core/mask_io.py`、`core/window/main_window.py`、
  `session/mask_store.py`、`rebuild_cache.py`、`ui/upload_worker.py`。
- 测试更新:`test_mask_store.py`、`test_rebuild_cache.py`、`test_upload_worker.py`(及连带断言)。
