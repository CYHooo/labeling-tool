# LM Labeling Tool

[한국어](README.md) | [English](README.en.md) | **中文**

在**本地电脑上人工修正** AI 服务器生成的拼接图像和裂缝 mask 的标注工具。
编辑裂缝 mask、标出修补区域（OBB）、确认比例尺（px/cm）后，把结果重新上传到服务器（EC2）。

工作流程：**登录 → 获取数据 → 标注 → 上传到 EC2**

---

## 下载

[**下载最新版本（Releases）**](https://github.com/CYHooo/labeling-tool/releases/latest) —— 在页面顶部的表格里，按自己的系统**只下载一个**文件即可。

| 系统 | 下载的文件 | 大小 |
|---|---|---|
| Windows 10 / 11（64 位） | `LM_LabelingTool-Setup-v<版本>.exe` | 约 1.6 GB |
| Ubuntu 22.04 / 24.04（64 位） | `lm-labeling-tool_<版本>_amd64.deb` | 约 1.8 GB |

## 安装

### Windows

1. 双击下载的 `LM_LabelingTool-Setup-v<版本>.exe`。
2. 如果出现“Windows 已保护你的电脑”，点击 **「更多信息」→「仍要运行」**。
3. 安装向导全部按默认继续即可，不需要管理员权限。
4. 在**开始菜单**中运行 **LM_LabelingTool**。

### Ubuntu

```bash
sudo dpkg -i lm-labeling-tool_<版本>_amd64.deb
```

在应用程序菜单中运行 **LM Labeling Tool**。

## 更新

程序会在**启动时以及运行中每 4 小时**检查一次新版本。想手动检查，可以点击登录界面的「检查更新」。

- 小更新（几 MB）会先在后台下载好再提示，点击「立即重启并更新」即可完成。Ubuntu 上需要输入一次密码。
- 标注过程中不会打断工作，会在关闭任务窗口时提示。
- 需要完整安装包的大更新会先告知大小，未经同意不会下载。
- 更新出错或中途断电时，会自动恢复到之前的版本。

## 使用方法

在登录界面上方的标签页中选择工作方式。

| 标签页 | 用途 |
|---|---|
| **在线标注** | 从服务器获取任务，标注后上传。 |
| **本地任务** | 继续已经下载的任务。 |
| **Few-shot 标注** | 基于 SAM2.1 的多类别标注。第一次打开时下载一次模型（约 308 MB）。 |

### 1. 登录与获取数据

1. 在「在线标注」标签页输入 `BASE URL` 和 `X-Viewer-Api-Key`，点击「下一步」。输入的内容会被保存，下次自动填入。
2. 在获取数据界面选择会话，需要时用 `fromNum` / `toNum` 指定照片范围（0 = 从头开始 / 到最后）。
3. 点击「获取（下载）」，照片下载完成后会打开标注界面。

已经下载的任务，在「本地任务」标签页选中后点击「打开」即可继续。

### 2. 标注

| 功能 | 说明 |
|---|---|
| **笔刷** | 大致画出裂缝，松开鼠标后会自动整理成 1px 中心线。要保留实际宽度，请打开「精细标注 (保留粗细)」。 |
| **修补区域** | 用可旋转的矩形（OBB）标出修补区域，重叠部分只计算一次。 |
| **比例尺 (px/cm)** | 直接使用服务器计算的值。需要修正时用「手动测量」：点击参考线的两个端点并输入实际长度。 |
| **SAM 分割 (剥落)** | 左键（加入）、右键（排除）自动框出剥落区域，点击「确认」写入。Esc 撤回上一个点。 |
| **显示高亮 / 显示15cm边界** | 预览裂缝周围的高亮和修补区域的 15cm 边界。 |

切换图像时会自动保存，也可以点击「保存 mask」手动保存。

### 3. 上传到 EC2

点击「上传到 EC2」，**只上传修改过的照片**，同时上传 mask、高亮和 15cm 边界。上传后会重新读取服务器确认是否生效，未生效的照片会连同编号一起提示。详细记录保存在任务文件夹的 `vapi.log` 中。

## 语言设置

界面语言（한국어 / 中文 / English）可以在登录界面底部或标注界面「设置」里的「语言:」中切换，选择会被保存。

## 数据位置与卸载

| | 数据位置 | 卸载方法 |
|---|---|---|
| Windows | `%LOCALAPPDATA%\Programs\LM_LabelingTool` | 控制面板 → 卸载程序 |
| Ubuntu | `~/.local/share/lm-labeling-tool/` | `sudo apt purge lm-labeling-tool` |

设置、已下载的任务和模型文件在**卸载后仍会保留**，重新安装后可以直接继续使用。

---

## 开发者说明

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
./run.sh                           # Windows: run.bat
```

- 测试：先 `pip install -r requirements-dev.txt`，再运行 `QT_QPA_PLATFORM=offscreen python -m pytest tests labeling_tool/tests annotation_tool/tests -q`
- Few-shot 工具：[`annotation_tool/USAGE.md`](annotation_tool/USAGE.md)
- 发布流程：[`docs/RELEASING.md`](docs/RELEASING.md)
- 界面术语：[`docs/i18n-glossary.md`](docs/i18n-glossary.md)
