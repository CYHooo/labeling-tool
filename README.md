# Labeling Tool — Few-Shot 分支（ConcJoint 多分类半自动标注）

> 本分支（`few-shot`）是一个独立的 **PyQt5 桌面半自动标注工具**，用 SAM（**SAM3** 主 / **SAM2.1** 回退）做**点/框交互式分割 + 画笔精修**，为 few-shot 语义分割训练制作多分类像素级标注（导出单通道 `_mask.png`，值 `0/1/2/3/4`）。
>
> 与本仓库 `main`/`offline` 分支（裂缝标注工具）相互独立，仅共用同一个远程仓库。

---

## 1. 功能

- **SAM 点/框交互分割**：左键正点、右键负点、左键拖拽框选，SAM 实时出候选，`Enter` 确认。
- **手动画笔 / 橡皮擦**：SAM 分不好的细节（细缝、毛糙边界）用画笔在原生分辨率手动补，橡皮擦去除多余。可调笔刷大小。
- **多分类图层 + 优先级合成**：多个类别独立成层，重叠像素按优先级唯一归属；导出单通道 `L` 模式 PNG。
- **文件夹批量标注**：`File ▸ Open Folder` 选数据集，列表导航，已标注标 `✓`，自动/手动保存 + 彩色 overlay 校验图。
- **深色界面**、缩放/平移（`Ctrl`+拖拽）、撤销/重做。

默认类别（可在 `annotation_tool/configs.py` 修改）：

| 值 | 类别 | 颜色 | 优先级 |
|:--:|------|------|:--:|
| 0 | 背景 | — | 最低 |
| 1 | joint（줄눈/接缝）| 红 | |
| 2 | concrete（混凝土）| 绿 | 最低（前景类中）|
| 3 | scalebar（比例尺）| 蓝 | |
| 4 | shoe（鞋子）| 品红 | 最高 |

优先级（重叠取高者）：**shoe > scalebar > joint > concrete > 背景**。

---

## 2. 目录结构

```
annotation_tool/
├── main.py            # 入口：python -m annotation_tool.main
├── configs.py         # 类别 / 优先级 / 颜色 / 后端开关 / 权重路径
├── core/
│   ├── mask_state.py  # 多类二值图层 + 优先级合成 + 撤销/重做（纯逻辑）
│   └── dataset_io.py  # EXIF 读图 + 0/1/2/3/4 掩膜读写 + overlay 导出
├── segmenter/
│   ├── base.py        # Segmenter 抽象接口 + build_segmenter 工厂
│   ├── sam3_backend.py# SAM3 交互式点/框（主后端）
│   └── sam2_backend.py# SAM2.1 ImagePredictor（回退后端）
├── ui/                # 画布 / 主窗口 / 后台推理线程 / 深色样式 / 坐标映射
├── assets/            # 捆绑的 CLIP BPE 词表（SAM3 需要）
└── tests/             # 纯逻辑 + UI smoke 测试（系统 python 即可跑）
```

---

## 3. 环境安装

需要 **Python 3.10+** 和一块 CUDA GPU（SAM3 约需 3.4GB 显存）。建议用项目根目录下的 `.venv/`：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# PyTorch (CUDA 12.1 为例)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 通用依赖
pip install PyQt5 pillow numpy pytest

# --- SAM2.1 回退后端 ---
# 需要 Meta 的 SAM2 包（提供 sam2 模块与 configs/sam2.1/*.yaml）
pip install "git+https://github.com/facebookresearch/sam2.git"

# --- SAM3 主后端 ---
pip install sam3 huggingface_hub psutil   # sam3 import 时需要 psutil（其未声明）
huggingface-cli login                     # 粘贴有 facebook/sam3 访问权限的 token
```

> `annotation_tool/requirements-gpu.txt` 也列了这些依赖。

---

## 4. 权重下载

模型权重不随仓库分发，请自行下载到 `checkpoint/`（该目录已被 `.gitignore` 忽略）。

### SAM2.1-B+（回退后端，零授权）

```bash
mkdir -p checkpoint
wget -P checkpoint https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt
```
- 配置见 `configs.SAM2_CHECKPOINT = "./checkpoint/sam2.1_hiera_base_plus.pt"`，模型 cfg `configs/sam2.1/sam2.1_hiera_b+.yaml` 由 `sam2` 包自带。

### SAM3（主后端，需 HuggingFace 授权）

1. 在 HuggingFace 申请并获得 [`facebook/sam3`](https://huggingface.co/facebook/sam3) 的访问权限。
2. `huggingface-cli login` 登录（token 需有该 repo 权限）。
3. 首次启动会自动从 HF 下载 `sam3.pt`（约 3.4GB）到 HF 缓存。
4. **（可选，推荐）离线加载**：把权重复制到 `checkpoint/sam3.pt`，之后免联网/免授权直接本地加载：
   ```bash
   cp ~/.cache/huggingface/hub/models--facebook--sam3/snapshots/*/sam3.pt checkpoint/sam3.pt
   ```
   `sam3_backend` 检测到 `checkpoint/sam3.pt` 就直接用它。

> 注：`sam3` 的 pip wheel 缺 CLIP BPE 词表，本仓库已捆绑 `annotation_tool/assets/bpe_simple_vocab_16e6.txt.gz`，无需额外下载。

### 训练好的 few-shot 权重

本分支**不含**训练好的 few-shot（FS-SAM2 LoRA）权重；如需在自有场景使用，请自行用标注好的数据训练。

---

## 5. 运行

```bash
source .venv/bin/activate
# 默认 SAM3；不带 --dataset 时启动后用 File ▸ Open Folder (Ctrl+O) 选文件夹
python -m annotation_tool.main

# 用回退后端 / 指定数据集
python -m annotation_tool.main --backend sam2 --dataset /path/to/YourDataset
```

数据集文件夹需含 `images/` 子目录（`*.jpg`）。保存产物：
- `masks/<name>_mask.png`：单通道 `L` 模式，值 `0/1/2/3/4`（可直接用于 few-shot 训练）。
- `verify_overlays/<name>_overlay.jpg`：彩色叠加校验图。

> GUI 需要图形显示（本机桌面 / X11 转发 / VNC）。若 `PYTHONPATH` 指向了 ROS 等环境导致冲突，先 `unset PYTHONPATH`。

---

## 6. 快捷键

| 操作 | 快捷键 |
|------|--------|
| 切类别 | `1`..`N`（或右侧单选） |
| 切工具：SAM点框 / 画笔 / 橡皮擦 | `V` / `B` / `E` |
| 加正点 / 负点 / 框选 | 左键 / 右键 / 左键拖拽（SAM 工具下）|
| 画笔涂抹 / 橡皮擦擦除 | 选画笔或橡皮擦后左键拖拽 |
| 笔刷调小 / 调大 | `[` / `]`（或右侧滑块）|
| 平移 / 缩放 | `Ctrl`+左键拖拽 / 滚轮 |
| 确认候选 / 取消 | `Enter` / `Esc` |
| 撤销 / 重做 | `Ctrl+Z` / `Ctrl+Y` |
| 上一张 / 下一张 / 保存 | `A` / `D` / `Ctrl+S` |

---

## 7. 测试

纯逻辑与 UI smoke 测试用系统 python 即可（无需 GPU）：

```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest annotation_tool/tests/ -q
```

---

## 8. 扩展类别

改 `annotation_tool/configs.py` 的 `CLASSES` / `CLASS_IDS` / `EXPORT_ORDER` / `CLASS_COLORS` 即可增删类别，UI（类别按钮、快捷键、画笔颜色、图层渲染）会自动适配。
