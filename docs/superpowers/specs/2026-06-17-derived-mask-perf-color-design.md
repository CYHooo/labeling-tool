# 派生掩膜:光晕配色修复 + 加速 + 后台线程

日期:2026-06-17
状态:已确认设计,待实现

## 背景(GUI 冒烟暴露的三个问题)

highlight/repair15 上线后人工冒烟发现:

1. **光晕不是黄色**:`paint_single_color_overlay` 沿用了 `paint_mask_overlay` 的通道反转
   (`rgba[0]=rgb[2]`),而本机 `QImage.Format_RGBA8888` 是标准 RGBA(byte0=R,离屏已验)。
   反转把意图黄 (255,255,0) 渲染成青 (0,255,255)——正好与 repair15 同色,故"不是黄色"。
2. **保存卡死**:`build_repair15` 用 `cv2.dilate` 做 15cm 外扩,核约 `round(15*px_per_cm)` 半径
   (典型 ~428px → 857×857 椭圆核),在大图上同步跑几十秒,冻结 UI 线程。
3. **切图"没自动保存"**:`_show_image` 切图前会 `_save_all_artifacts(only_if_edited=True)`(已接好),
   但该同步保存触发上面的巨核 dilation → 卡住,表现为切图卡顿/像没保存。#2 与 #3 同源。

> 已确认:Viewer 工具 `export_result_on_save=False`(`ui/main_window.py:35`),保存时不跑 Result 导出;
> 故唯一重型同步步骤是派生掩膜生成。`cv2.distanceTransform` 在 cv2 4.13 可用。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 颜色修复 | 只动 `paint_single_color_overlay` 去掉通道反转(不动既有 crack/spalling 配色) |
| 卡顿修复 | **两者都做**:距离变换让计算变快 + 派生掩膜生成下后台线程 |
| 线程范围 | 仅派生掩膜(highlight+repair15)异步;`closeEvent` 路径同步以保证退出前落盘 |

## 架构

### 1. 颜色修复(`core/canvas/overlay_painter.py`)

`paint_single_color_overlay` 的通道赋值由反转改为直序:
```python
rgba[..., 0] = rgb[0]
rgba[..., 1] = rgb[1]
rgba[..., 2] = rgb[2]
```
于是 highlight 传入的 `(255,255,0)` 渲染为黄。`paint_mask_overlay`(crack/spalling)**不动**。

### 2. 加速 `build_repair15`(`core/derived_masks.py`)

巨核 dilate 替换为距离变换(O(N)、毫秒级、≈圆形 dilation):
```python
fg = (crack>0) | (spalling>0)                          # 前景并集
src = np.where(fg, np.uint8(0), np.uint8(255))         # 0 在前景
dist = cv2.distanceTransform(src, cv2.DIST_L2, 5)      # 每像素到最近前景的欧氏距离
px = int(round(15.0 * float(px_per_cm)))
return np.where(dist <= px, np.uint8(255), np.uint8(0))   # 含前景(dist=0)+ px 内
```
输出仍单通道 0/255 填充。两层皆 None → `ValueError`(同现状)。`build_highlight` 不变(10px dilate 已快)。

### 3. 派生掩膜生成下后台线程

- 抽出纯函数 `generate_derived_masks(crack, spalling, px_per_cm, highlight_path, repair15_path)
  -> tuple[np.ndarray, np.ndarray | None]`(放 `core/derived_masks.py`):
  - `build_highlight` → imwrite `highlight_path` → 返回 highlight 数组;
  - `px_per_cm` 为真:`build_repair15` → imwrite `repair15_path` → 返回 r15 数组;否则 r15 为 None
    (不写 repair15 文件)。
  - 目录由调用方保证存在(调用前 mkdir);函数只写文件 + 返回数组。
- 新增 `ui/derived_mask_worker.py`:
  - `class _Signals(QObject): done = pyqtSignal(str, object, object)`(token, hi, r15)。
  - `class DerivedMaskRunnable(QRunnable)`:构造接收 `crack`(已 copy)、`spalling`(已 copy)、
    `px_per_cm`、`highlight_path`、`repair15_path`、`token`、`signals`;`run()` 调
    `generate_derived_masks(...)` 后 `signals.done.emit(token, hi, r15)`;异常时 `vlog().exception` 不崩线程。
- `core/window/main_window.py`:
  - `_save_all_artifacts(...)` 新增 `async_derived: bool = True`。同步写 Labeling mask + bbox 不变;
    原内联的派生掩膜块(1b)改为:**快照** `mc.copy()`/`ms.copy()`/`current_scale`/两路径/`token=filename`,
    先确保 `highlight_dir`/`repair15_dir` 存在,然后:
    - `async_derived` 为真:构造 `DerivedMaskRunnable` → `QThreadPool.globalInstance().start(runnable)`;
    - 为假(closeEvent):同步调 `generate_derived_masks(...)` 并 `canvas.set_highlight/set_repair15`。
  - 槽 `_on_derived_ready(token, hi, r15)`(连到 worker 的 `_Signals`):仅当 `token == 当前文件名`
    才 `canvas.set_highlight(hi)` / `canvas.set_repair15(r15)`;否则跳过(文件已写好,避免把旧图叠到新图)。
  - `closeEvent` 调 `_save_all_artifacts(only_if_edited=True, async_derived=False)`。
  - 持有一个 `_Signals` 实例(连一次槽),供所有 runnable 复用。

### 数据流 / 竞态

```
保存(手动/切图自动):
  encode mask -> Labeling/ (同步) ; bbox -> json (同步)
  快照(mc.copy, ms.copy, scale, paths, filename) -> QThreadPool.start(runnable)   [不阻塞 UI]
  runnable: generate_derived_masks -> 写 HighLight/Repair15 -> signals.done(token, hi, r15)
  _on_derived_ready: token==当前文件名? set_highlight/set_repair15 : 跳过
关闭:
  _save_all_artifacts(async_derived=False) -> 同步 generate + set_*(快,距离变换)
```

- 快照 mask 副本隔离 worker 与用户后续编辑/切图。
- 文件按文件名各写各,后编辑→后写,last-write-wins,正确。
- 画布刷新按 token 守卫,切走不误刷。
- 并发由 `QThreadPool` 托管;派发频率是用户级(保存/切图),且单次计算现为毫秒级,重叠罕见且无害。

## 错误处理

- worker `run()` 内异常 `vlog().exception` 记录,不崩线程、不影响已写的 Labeling mask。
- `build_repair15` 需 px/cm;无 scale → 不生成 repair15、画布 `set_repair15(None)`、该图不上传(px≤0 跳过)。
- 距离变换对空前景(全 0)→ 全 0 输出,无异常。

## 测试

- `core/derived_masks.py`:
  - `build_repair15`(距离变换):输出 0/255;单点前景外扩 px 后,距前景 ≤px 的像素置位、明显 >px 的不置位;
    前景区域随 px/cm 增大而扩大;两层皆 None → ValueError。
  - `generate_derived_masks`:写出 highlight 文件 + (有 scale 时)repair15 文件,返回数组;
    无 scale → 不写 repair15、返回 r15=None。
- `core/canvas/overlay_painter.py`:`paint_single_color_overlay` 离屏渲染断言——
  传 (255,255,0) 的像素 readback 为 (R=255,G=255,B=0)(锁颜色回归)。
- 线程/worker GUI 接线沿用现状不单测;import 冒烟 + 人工冒烟覆盖。

## 不做(YAGNI)

- 不改 crack/spalling 既有配色与 `paint_mask_overlay`。
- 不改 repair15 的语义(仍是 15cm 填充区域,文件 0/255);只换更快的等价算法。
- 不引入跨进程(QThreadPool 线程足够;计算现为毫秒级)。
- 不改上传链路、命名、工作区。

## 受影响文件

- 修改:`core/canvas/overlay_painter.py`(颜色)、`core/derived_masks.py`(repair15 距离变换 + generate_derived_masks)、
  `core/window/main_window.py`(异步派发 + 槽 + closeEvent 同步)。
- 新增:`ui/derived_mask_worker.py`(QRunnable + Signals)。
- 测试更新/新增:`tests/test_derived_masks.py`(repair15 距离变换 + generate_derived_masks)、
  新增 `tests/test_overlay_color.py`(离屏颜色断言)。
