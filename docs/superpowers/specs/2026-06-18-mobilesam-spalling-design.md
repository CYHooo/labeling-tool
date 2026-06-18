# MobileSAM 点选分割 spalling(本地 ONNX)

日期:2026-06-18
状态:已确认设计,待实现

## 背景

spalling(박리,面状缺陷)当前只能用画笔手动涂。接入 **MobileSAM** 做点选式快速分割:
用户在 spalling 区域点几下 → 自动得到区域掩膜 → 写入 spalling 层。crack(细线)不接 SAM。

本工具刻意**不带 torch**。因此推理走 **onnxruntime**(纯 CPU,非 torch);模型用 **MobileSAM**
导出的 ONNX,体积小到可直接放进 GitHub 仓库(同事 clone 即得,无需另外下载)。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 模型 | **MobileSAM**(vit_t / TinyViT),导出 ONNX |
| 推理 | 本地 **onnxruntime**(必需依赖,加入 requirements);不引入 torch |
| 模型存放 | `labeling_tool/models/sam/*.onnx`,**普通 git 提交**(非 Git LFS) |
| 交互 | **迭代点选**:左键加正点、右键加负点,实时预览;Enter 确认、Esc 取消 |
| 输出目标 | 仅写入 **spalling** 层(spalling=2);不碰 crack |
| 模型产出 | 由**导出脚本**生成,用户在有 torch 的机器上跑一次后提交 `.onnx` |
| 交付 | **两阶段**:Phase 1 导出脚本 + 推理模块 + 依赖;Phase 2 画布模式 + UI 接线 |

## 架构

```
导出脚本(torch, 一次性)→ models/sam/{encoder,decoder}.onnx → git 提交
                                       ↓
MobileSamPredictor(onnxruntime): set_image()=编码器1次/图(缓存) ; predict(points,labels)=解码器/点击
                                       ↓
ImageCanvas SAM 모드: 迭代点选 → _sam_preview 实时叠加 → Enter 写入 brush_mask_spalling
                                       ↓
            复用现有管线(encode 整型 spalling=2 / 上传 high·15 / spallingMm2=像素数×面积)
```

### 1. 导出脚本 `scripts/export_mobilesam_onnx.py`(Phase 1)

- 依赖(仅导出时):`torch`、`mobile_sam`(或等价的 segment-anything + MobileSAM 权重)。**运行环境之外不需要 torch**。
- 步骤:
  1. 准备 MobileSAM 权重 `mobile_sam.pt`(~40MB):脚本若本地无则从官方 URL 下载,或接受 `--checkpoint` 路径。
  2. `sam = sam_model_registry["vit_t"](checkpoint=...)`。
  3. **编码器**导出:把 `sam.image_encoder`(输入 `1×3×1024×1024` 预处理图 → `1×256×64×64` 嵌入)`torch.onnx.export` 到 `models/sam/mobile_sam_encoder.onnx`。
  4. **解码器**导出:用 `SamOnnxModel` 包装(点提示、`return_single_mask=False`,内含掩膜上采样到原图尺寸),导出到 `models/sam/mobile_sam_decoder.onnx`,point 维度设为动态轴。
  5. 打印两文件大小与落点路径,提示 `git add labeling_tool/models/sam/*.onnx`。
- 另附 `requirements-export.txt`(`torch`、`mobile_sam`/`segment-anything`、`onnx`)与脚本顶部使用说明。

### 2. 推理 `core/sam/predictor.py`(Phase 1)

`MobileSamPredictor(encoder_path, decoder_path)`:
- 懒加载两个 `onnxruntime.InferenceSession`(CPUExecutionProvider)。
- `set_image(bgr)`:BGR→RGB → **ResizeLongestSide 到 1024** → 按 SAM 均值/方差归一
  (mean=`[123.675,116.28,103.53]`,std=`[58.395,57.12,57.375]`)→ 右/下 pad 到 `1024×1024`
  → 编码器 → 缓存 `embedding`、`orig_hw`、`resized_hw`。
- `predict(points_xy, labels) -> np.ndarray`:把点击坐标按相同缩放映射到 1024 帧,按 SAM-ONNX 约定
  追加一个 `(0,0)` label `-1` 的填充点;喂解码器(`mask_input` 全 0、`has_mask_input=0`、`orig_im_size=orig_hw`)
  → 得到多掩膜 + iou → **取最高 iou** → `logits > 0` 阈值 → uint8 0/255,尺寸=原图。
- 纯函数辅助(`_resize_longest`, `_apply_coords`, `_postprocess`)拆出,便于不依赖模型单测。

### 3. 画布 SAM 모드 `core/canvas/image_canvas.py`(Phase 2)

- 状态:`sam_mode: bool`、`_sam_points: list[(x,y)]`、`_sam_labels: list[int]`、`_sam_preview: np.ndarray|None`、`_sam_predictor`、`_sam_image_set: bool`。
- `set_sam_mode(enabled)`:进入/退出;退出或 `set_image` 清空点/预览/`_sam_image_set`(与 bbox/measure 退出清理一致)。
- `set_sam_predictor(predictor)`:主窗口注入(可为 None=不可用)。
- `mousePressEvent`(sam_mode 分支,优先级排在 brush 之前,与现有 measure/bbox 同级):
  - 首次点击该图时 `predictor.set_image(origin_bgr)`(懒加载嵌入),置 `_sam_image_set`;
  - 左键 → 追加正点(label 1)、右键 → 追加负点(label 0);
  - 调 `predictor.predict(points, labels)` → `_sam_preview`;`update()`。
- `paintEvent`:sam_mode 且有 `_sam_preview` → 半透明**绿色**叠加(表示将成为 spalling)+ 画出点(正点绿/负点红)。
- 提交/取消:`commit_sam()`(主窗口绑 Enter/按钮)把 `_sam_preview>0` OR 进 `brush_mask_spalling`、`_touch_mask`、`mask_edited.emit()`、清空点/预览;`cancel_sam()`(Esc/按钮)只清空。

### 4. UI + 依赖(Phase 2)

- `ui_builder`:画笔/类别区附近加「SAM 분할 (박리)」可勾选 toggle(objectName 便于选中态样式);加「확정」「취소」两个动作按钮(或仅 Enter/Esc 快捷键 + 提示)。
- `main_window`:`_on_sam_toggle`(与 brush/bbox/measure **互斥**,参照现有互斥逻辑);构造 predictor —— 若 `onnxruntime` 或模型文件缺失,**toggle 置灰 + tooltip 提示**,不崩溃;Enter/Esc 在 sam_mode 下触发 commit/cancel;i18n 键三语。
- `requirements.txt` += `onnxruntime`;`shortcuts.py` 视需要加 SAM 快捷键。

## 错误处理 / 退化

- `onnxruntime` 未装或 `models/sam/*.onnx` 缺失 → predictor 构造失败 → SAM toggle 置灰 + 提示,应用其余功能照常。
- 编码器/解码器推理异常 → 状态栏提示、`vlog().exception`,不崩 UI。
- 点为空时不预测;切图清空 SAM 状态。

## 测试

- `core/sam/predictor.py` 纯函数:`_resize_longest`(最长边=1024 的缩放与新尺寸)、`_apply_coords`(原图坐标→1024 帧)、`_postprocess`(logits→0/255、还原原尺寸、取最高 iou)用合成数组单测。
- 编码器/解码器整体推理:**需模型,改后人工冒烟**(隔离环境无法跑 onnxruntime+模型)。
- 画布 SAM 模式 / UI:GUI,import 冒烟 + 人工冒烟(点选→预览→Enter 写入 spalling→保存上传)。

## 不做(YAGNI)

- 不接 crack 的 SAM(细线 SAM 不擅长)。
- 不做框选(本期仅点选)。
- 不做 SAM2 / GPU / 多模型切换;固定 MobileSAM CPU ONNX。
- 不改保存/上传/计测管线(SAM 只产出 spalling 像素,下游不变)。

## 受影响文件

- 新增:`scripts/export_mobilesam_onnx.py`、`requirements-export.txt`、`core/sam/__init__.py`、`core/sam/predictor.py`、
  `labeling_tool/models/sam/`(放导出的 `.onnx`)、`tests/test_sam_predictor.py`。
- 修改:`requirements.txt`(+onnxruntime)、`core/canvas/image_canvas.py`、`core/window/ui_builder.py`、
  `core/window/main_window.py`、`core/window/shortcuts.py`、`core/window/styles.py`(SAM toggle 选中态)、`core/i18n.py`。

## 分阶段交付

- **Phase 1**(本仓库可完成,模型除外):导出脚本 + `requirements-export.txt` + `requirements.txt`(+onnxruntime)
  + `core/sam/predictor.py` + 纯函数单测。→ 用户跑脚本产出并提交 `models/sam/*.onnx`。
- **Phase 2**(需模型联调):画布 SAM 模式 + UI toggle/动作 + 互斥 + i18n + 防御性退化。→ 人工冒烟。
