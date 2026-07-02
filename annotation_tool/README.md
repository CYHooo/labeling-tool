# ConcJoint 半自动标注工具

用 SAM（SAM3 主 / SAM2.1 回退）做**点/框交互式分割**，为 ConcJoint few-shot 训练制作三分类像素级标注，导出与 `ConcJointDataset` 完全兼容的 `_mask.png`（0/1/2/3）。

类别：`1=joint(줄눈)` `2=concrete` `3=scalebar` `4=shoe`，背景 `0`。
颜色：红=joint、绿=concrete、蓝=scalebar、品红=shoe。
优先级（重叠时取高者）：shoe > scalebar > joint > concrete > 背景。

---

## 1. 目录结构

```
annotation_tool/
├── main.py                   # 入口（python -m annotation_tool.main）
├── configs.py                # 路径 / 类别 / 优先级 / 颜色 / 后端开关
├── core/
│   ├── mask_state.py         # MaskState：三类二值图层 + 优先级合成 + 撤销/重做
│   └── dataset_io.py         # EXIF 读图 + 0/1/2/3 掩膜读写 + overlay 导出
├── segmenter/
│   ├── base.py               # Segmenter 抽象接口 + build_segmenter 工厂
│   ├── sam2_backend.py       # SAM2.1 ImagePredictor（零下载回退）
│   └── sam3_backend.py       # SAM3 PVS 点/框（主后端）
├── ui/
│   ├── geometry.py           # 场景<->图像坐标映射（纯函数）
│   ├── worker.py             # InferenceWorker(QThread) 后台推理
│   ├── canvas.py             # ImageCanvas：缩放/平移 + 提示采集 + 叠加渲染
│   └── main_window.py        # MainWindow 整合
└── tests/                    # 纯逻辑 + UI smoke 测试（系统 python 即可跑）
```

---

## 2. 两套运行环境

| 环境 | 用途 | 依赖 |
|------|------|------|
| 系统 `python3`(3.12) | 跑 core/UI 逻辑测试、开发 | 已有 PyQt5 / Pillow / numpy / pytest |
| 项目根目录 `.venv/` | 真机推理 + 运行 GUI | torch + PyQt5 + sam2(editable) / sam3 |

> core 逻辑（`mask_state` / `dataset_io` / `geometry`）和 UI smoke 测试不需要 GPU；只有真正调用 SAM 推理才需要 `.venv`。

### 2.1 跑测试（系统 python，无需 GPU）

```bash
cd /home/cyh/Project/Few-shot/FS-SAM2_260523_v01
QT_QPA_PLATFORM=offscreen python3 -m pytest annotation_tool/tests/ -v
```

### 2.2 搭建推理环境 `.venv`

```bash
cd /home/cyh/Project/Few-shot/FS-SAM2_260523_v01
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install PyQt5 pillow numpy pytest

# SAM2.1 回退后端（项目内 editable，零额外权重下载，复用 checkpoint/sam2.1_hiera_base_plus.pt）
pip install -e segment-anything2/sam2

# SAM3 主后端（需 HuggingFace 授权）
pip install sam3 huggingface_hub psutil   # sam3 import 时需要 psutil（其包未声明该依赖）
huggingface-cli login        # 粘贴有 facebook/sam3 访问权限的 token
# 注：sam3 的 pip wheel 缺 CLIP BPE 词表，本仓库已捆绑 annotation_tool/assets/bpe_simple_vocab_16e6.txt.gz，无需额外下载
# 注：若把 sam3.pt 放到 checkpoint/sam3.pt（可从 HF 缓存复制），后端会直接本地加载（离线、免授权）；否则自动从 HF 下载
```

依赖清单见 `annotation_tool/requirements-gpu.txt`。

---

## 3. 运行 GUI

```bash
. .venv/bin/activate
cd /home/cyh/Project/Few-shot/FS-SAM2_260523_v01

# 用 SAM2.1 后端（零下载，先验证全链路）
python3 -m annotation_tool.main --dataset /home/cyh/Project/Few-shot/ConcJointDataset --backend sam2

# 用 SAM3 后端（默认，需先 HF 登录）
python3 -m annotation_tool.main --dataset /home/cyh/Project/Few-shot/ConcJointDataset --backend sam3
```

不带 `--backend` 时使用 `configs.BACKEND` 的默认值。`--dataset` 也可省略——启动后用菜单 **File → Open Folder…（`Ctrl+O`）** 选择**存放图片的文件夹**（直接读取该文件夹内的图片；mask 会写到其下固定的 `masks/` 子目录）。GUI 需要图形显示（本机桌面 / X11 转发 / VNC）。

---

## 4. 标注操作

工作流：**选类别 → 点/框提示 → SAM 出候选 → 确认并入该类别层 → 保存**。

| 操作 | 快捷键 / 鼠标 |
|------|---------------|
| 切换类别 joint/concrete/scalebar | `1` / `2` / `3`（或右侧单选） |
| 切工具：SAM点框 / 画笔 / 橡皮擦 | `V` / `B` / `E` |
| 画笔涂抹 / 橡皮擦擦除（当前类别） | 选画笔或橡皮擦后左键拖拽 |
| 笔刷调小 / 调大 | `[` / `]`（或右侧滑块） |
| 加正点（前景） | 左键单击 |
| 加负点（背景） | 右键单击 |
| 框选 | 左键拖拽（>5px） |
| 平移 | 按住 `Ctrl` + 左键拖拽（或 `Space` + 拖拽） |
| 缩放 | 滚轮 |
| 确认候选并入当前类别 | `Enter` |
| 放弃候选 / 清空当前提示 | `Esc` |
| 撤销 / 重做 | `Ctrl+Z` / `Ctrl+Y` |
| 上一张 / 下一张 | `A` / `D` |
| 保存 | `Ctrl+S` |

左侧列表显示所有图片，已标注的前缀 `✓`。右侧面板显示各类像素占比。

---

## 5. 输出与训练衔接

保存时按优先级 **scalebar(3) > joint(1) > concrete(2) > bg(0)** 压平为单通道：

- `masks/<name>_mask.png`：单通道 `L` 模式 PNG，值 0/1/2/3，方向/尺寸与 EXIF 校正后的原图一致。
- `verify_overlays/<name>_overlay.jpg`：彩色叠加校验图（可在 `configs.EXPORT_OVERLAY` 关闭）。

导出的 `masks/` 可被 `data/concjoint.py` 直接读取用于 few-shot 训练，无需额外转换。

---

## 6. 后端切换与回退

- `configs.BACKEND = "sam2" | "sam3"`，或运行时 `--backend` 覆盖。
- SAM3 接入受阻（未授权 / 显存不足）时切 `sam2` 即可用项目已有权重继续标注。
- 新增后端：实现 `segmenter/base.py` 的 `Segmenter` 接口（`load` / `set_image` / `predict` / `reset`），在 `build_segmenter` 注册即可，UI 无需改动。
