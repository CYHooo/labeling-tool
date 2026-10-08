# LM Labeling Tool

[한국어](README.md) | [English](README.en.md) | **中文**

在**本地电脑上人工修正** AI 服务器生成的拼接图像和裂缝 mask 的标注工具。
编辑裂缝 mask、标出修补区域（OBB）、确认比例尺（px/cm）后，把结果重新上传到服务器（EC2）。

工作流程：**登录 → 获取新任务 → 标注 → 上传到 EC2**

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

登录后的任务界面有两个标签页。

| 标签页 | 用途 |
|---|---|
| **标注** | 从服务器获取新任务，或继续本机已有的任务，标注后上传。 |
| **Few-shot 标注** | 基于 SAM2.1 的多类别标注。第一次打开时下载一次模型（约 308 MB）。 |

### 1. 登录与打开任务

在第一个界面输入 **ID / 密码** 和**服务器**（`BASE URL`、`X-Viewer-Api-Key`），点击「登录」。ID 和服务器会被保存，下次自动填入；密码不会保存。目前使用开发账号 `admin` / `admin`（多用户账号将在接入服务器后支持）。

登录后进入任务界面，**本地任务**列表显示本机已获取的任务，最近修改的排在前面。点击「退出登录」回到第一个界面。

- **新任务**：「获取新任务」→ 选择「任务 ID」，照片默认「全部」，也可以选「指定范围」填写照片编号范围（例如 10 ~ 50）→「获取」，照片下载完成后打开标注界面。
- **已有的任务**：在列表中选中后点「打开」（或双击）。上传会发往该任务原来的服务器；Key 为空时只保存在本机。
- 列表默认按最近修改时间排列。点击列标题（任务 · 检测名称 · 照片 · 最近修改）即可按该列排序，再点一次反向排序。
- 获取本机已有的任务时，会询问「打开」或「重新获取」。重新获取也会保留标注结果和上传记录。从其他服务器获取的同编号任务不能在这里打开。

### 2. 标注

右侧面板顶部显示任务 ID · 检测名称 · 照片数，点「?」打开快捷键说明。图片列表显示「编号」（`任务 ID-照片编号`，例如 49-3）和「文件名」，下方是「上一张」/「下一张」/「保存」（A / D / S）。在「编辑工具」中点击「查看 · 画笔 · SAM · 修补区域」之一，选中的工具就是当前编辑模式（「查看」不编辑），其用法和选项显示在正下方。裂缝 / 剥落在画笔选项中选择。「显示 · 比例尺」中可切换高亮 / 15cm 边界并查看比例尺。「上传到 EC2」固定在面板最底部。

| 功能 | 说明 |
|---|---|
| **画笔** | 大致画出裂缝，松开鼠标后会自动整理成 1px 中心线。要保留实际宽度，请打开「精细标注 (保留粗细)」。 |
| **修补区域** | 用可旋转的矩形（OBB）标出修补区域，重叠部分只计算一次。 |
| **比例尺 (px/cm)** | 直接使用服务器计算的值。需要修正时用「手动测量」：点击参考线的两个端点并输入实际长度。 |
| **SAM 分割 (剥落)** | 左键（加入）、右键（排除）自动框出剥落区域，点击「确认」写入。Esc 撤回上一个点。 |
| **高亮 / 15cm 边界** | 预览裂缝周围的高亮和修补区域的 15cm 边界。 |

切换图像时会自动保存，也可以点击「保存」（S）手动保存。

### 3. 上传到 EC2

点击「上传到 EC2」，**只上传修改过的照片**，同时上传 mask、高亮和 15cm 边界。上传后会重新读取服务器确认是否生效，未生效的照片会连同编号一起提示。详细记录保存在任务文件夹的 `vapi.log` 中。

### 数据与日志位置

| 项目 | Linux | Windows |
|---|---|---|
| 任务（照片 · 标注结果） | `~/.local/share/lm-labeling-tool/data/session_<任务 ID>/` | `<安装目录>\data\session_<任务 ID>\` |
| 任务日志 | 任务文件夹中的 `vapi.log` | 任务文件夹中的 `vapi.log` |
| 程序日志 | `~/.local/share/lm-labeling-tool/logs/app.log` | `<安装目录>\logs\app.log` |

Windows 的 `<安装目录>` 默认是 `%LOCALAPPDATA%\Programs\LM_LabelingTool`。程序日志（`app.log`）记录启动信息、登录、更新、意外错误以及所有任务日志，每 1 MB 轮换一次，保留最近 5 个。遇到问题时，在标注界面点「?」→「打开日志文件夹」，把 `app.log` 发给开发人员。密码和 API Key 不会被记录。

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
