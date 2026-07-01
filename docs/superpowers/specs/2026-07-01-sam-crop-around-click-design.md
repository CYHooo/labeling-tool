# 大图 SAM 点击处原分辨率裁块分割

日期:2026-07-01
状态:已确认设计,待实现

## 背景 / 根因

用户报告:在大拼接图上用 SAM 点选标 spalling,常把**整张图**标成 spalling,负点也救不回。

**根因(已验证,predictor.py:31-36)**:`preprocess_image(bgr, target=1024)` 把**整张图最长边缩到 1024**。一张 15663×4933 的全景 → 压成约 1024×322 再送进 MobileSAM(~15× 下采样),细节尽失 → 点击落在糊成一片的低分图上 → SAM 返回"整片";负点无法恢复本就不存在的分辨率。

**这不是模型容量问题,而是"整图被压缩"**。换更大 SAM/加 DINO 若同样把整图缩到输入尺寸,照样糊。真正的杠杆:**在点击处取原分辨率的局部窗口跑 SAM**。

## 目标

点击处按**原分辨率**裁一块跑 SAM,把 mask 贴回全图;保留人工点击/负点/undo;保持 MobileSAM ONNX 轻量、CPU、可进 git。只针对 spalling(现状即如此:commit 只写 spalling 层)。

## 已确认决策

| 决策点 | 选择 |
|--------|------|
| 裁块尺寸 | `SAM_CROP_PX = 1024`(见方;1:1 最清晰)。可调常量 |
| 裁块中心 | **第一次点击**处,居中;靠边贴边;图比窗口小则取全图 |
| 后续点/负点 | 全图坐标 → 减裁块偏移 → clamp 进窗口 → predict |
| mask 回贴 | crop 掩膜放进 `zeros(H,W)` 的 `_sam_preview[y0:y1, x0:x1]` |
| 裁块生命周期 | 首点固定;取消/切图/清空重置;下次首点重新裁 |
| predictor | **不改**(收到裁块,`_orig_hw`=裁块尺寸,输出裁块掩膜) |
| spalling > 1024 | mask 被裁块边界截断 → 相邻再点+commit(OR 累加)或调大常量 |

## 架构 / 组件

### 1. 纯函数 `crop_window`(`core/sam/predictor.py`,与其它纯 helper 同处)
```
crop_window(h, w, cx, cy, side) -> (x0, y0, x1, y1)
```
- `cw = min(side, w)`, `ch = min(side, h)`。
- `x0 = clip(cx - cw//2, 0, w - cw)`, `y0 = clip(cy - ch//2, 0, h - ch)`;返回 `(x0, y0, x0+cw, y0+ch)`。
- 图比窗口小 → 返回 `(0,0,w,h)`(整图)。纯函数,易单测。

### 2. 常量
`SAM_CROP_PX = 1024`(`core/sam/predictor.py` 或 constants;供 canvas 引用)。

### 3. Canvas 改动(`core/canvas/image_canvas.py`)
- 新状态:`self._sam_crop: tuple[int,int,int,int] | None = None`(裁块 `(x0,y0,x1,y1)`,全图坐标)。
- `_clear_sam_state`:同时 `self._sam_crop = None`。
- `_sam_add_point(ix, iy, label)`:
  - 首点(`not self._sam_image_set`)时:`self._sam_crop = crop_window(H, W, ix, iy, SAM_CROP_PX)`;取 `x0,y0,x1,y1`;`predictor.set_image(self._origin_bgr[y0:y1, x0:x1])`;`self._sam_image_set=True`。
  - 追加点(全图坐标)后调 `_sam_recompute()`。
- `_sam_recompute()`:
  - 无点 → `_sam_preview=None; update()`。
  - 否则:`x0,y0,x1,y1 = self._sam_crop`;`cw,ch = x1-x0, y1-y0`;每个点 `(px,py)` → `(clip(px-x0,0,cw-1), clip(py-y0,0,ch-1))` → `predictor.predict(crop_pts, labels)` 得 `mask_crop`(裁块尺寸 `ch×cw`)→ `preview=np.zeros((H,W),uint8); preview[y0:y1, x0:x1]=mask_crop`;`self._sam_preview=preview; update()`。
  - 异常时 `_sam_preview=None` 并 vlog(沿用现状)。

### 4. 不变项
`commit_sam`(OR 进 spalling)、`undo_sam_point`(重跑 recompute)、`_paint_sam_points`(点用全图坐标)、`select_mask` 爆图剔除(现在作用在裁块内)、`cancel_sam` —— 均不改。predictor 不改。

## 数据流
```
首点(cx,cy) → crop_window → set_image(原分辨率裁块)  [1:1 清晰]
后续点(全图坐标) → 减(x0,y0)、clamp进窗口 → predict → 裁块掩膜
→ 贴进全图 preview[y0:y1,x0:x1] → commit OR 进 spalling 层
```

## 错误处理 / 边界
- 图 ≤ 窗口 → 裁块=整图(退化为当前行为,小图也更清晰)。
- 点落窗口外 → clamp 到窗口边(罕见:裁块由首点居中)。
- 裁块首点固定;取消/切图/清空重置。
- `_origin_bgr` 或 predictor 为 None → 与现状一致,直接 return。

## 测试
- `crop_window` 单测:居中、贴边(四角/四边 clamp)、图小于窗口取整图、奇偶尺寸。
- **端到端亮块冒烟(关键回归)**:合成一张**大**图(如 4000×3000,均值暗)在某处放亮块;fake/真 predictor;点亮块 → `_sam_preview>0` 的 bbox **贴合亮块、不覆盖整图**;`_sam_crop` 偏移正确;commit 后 spalling 掩膜=亮块。用离屏(本地)验证真实模型;`crop_window` 与坐标映射用可提交单测(fake predictor,返回裁块内固定块 → 校验回贴偏移)。

## 不做(YAGNI)
- 不做 DINO / 文本提示 / 全自动(本次只解决大图点击质量)。
- 不换 SAM 模型(仍 MobileSAM ONNX;GPU 强 SAM 留作后续可选)。
- 不做拖框自定义裁块大小(v1 固定 1024;常量可调)。
- 不改 commit 只写 spalling 的现状。

## 受影响文件
- 修改:`core/sam/predictor.py`(+`crop_window`、`SAM_CROP_PX`)、`core/canvas/image_canvas.py`(裁块状态 + `_sam_add_point`/`_sam_recompute`/`_clear_sam_state`)。
- 新增测试:`tests/test_sam_crop.py`(crop_window + 坐标映射/回贴)。
- 可能:README 一行说明(大图 SAM 在点击处按原分辨率分割)。
