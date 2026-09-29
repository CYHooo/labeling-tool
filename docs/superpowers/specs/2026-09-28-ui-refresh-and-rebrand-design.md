# UI 改版与品牌统一 — 设计文档

- 日期：2026-09-28
- 状态：已确认，待实现
- 起点：v1.2.0（`main` @ 538ad3b）
- 视觉方案画布：https://claude.ai/artifact/1awkfixY4oCxeh4MnPfUzR

## 1. 背景与目标

v1.2.0 完成了全 UI 三语化并验证了应用内自动更新。在真机使用中暴露出四个问题：

1. few-shot 工具打开时弹出的"正在加载模型"提示是白底浅灰字，看不清内容，且是一个游离于主界面之外的独立小窗。
2. 标注窗口侧栏的八个分组竖排在一个滚动区里，一屏放不下，且八个分组视觉权重完全相同，看不出当前在用哪个工具。
3. 软件名 `LabelingTool (Few-shot)` 过长，且用括号承载变体说明。
4. 软件没有自定义图标，用的是 PyInstaller 与 Inno Setup 的默认图标。

本次改版解决这四个问题，并借机把公司标识（LM = Lastmile）落到产品上。

## 2. 已确认的决策

| 项 | 决策 | 备选与放弃理由 |
|---|---|---|
| 软件名 | `LM_LabelingTool`，不使用括号承载说明 | — |
| 改名范围 | 全部改名，包含 exe 与 release 资产名，**不做向后兼容** | 曾考虑只改用户可见名称以保住更新链路；用户选择彻底改名，接受手动升级一次的代价 |
| 变体 | 只发布 `full` 一个变体，废弃 `lite` | 曾考虑用 `_FS` 后缀区分两个变体；用户选择收敛为单变体 |
| 加载提示 | 内嵌到登录窗口 | 曾考虑先开主窗口再异步加载（需拆解 `annotation_tool` 内部，风险大）、或保留独立窗口只改配色（未满足"不要额外小窗"的诉求） |
| 标注窗口 | 方向 B：工具驱动重组 | 方向 A（克制打磨）改动更小，但侧栏仍是纵向堆叠；用户选择 B |
| 图标 | 方案 A 字母标，全尺寸统一使用 | 曾提议 B 做大尺寸、A 做小尺寸；用户要求统一为一个，避免混乱。选 A 是因为 B 的四角选框在 16px 下会糊成噪点 |

### 2.1 关于废弃 lite 的权衡（留给未来的记录）

`lite` 变体的存在意义是让没有 GPU、没有 torch 的生产机器只下载约 128 MB 的安装包。废弃之后，所有机器都要下载约 1.5 GB 的 full 安装包，其中包含生产流程用不到的 torch 与 CUDA 依赖。

用户在知晓该代价的前提下选择收敛为单变体，换取的是：打包脚本不再需要双分支、CI 构建时间减半、开始菜单不再有同名条目的歧义。若未来生产机器的下载成本成为问题，可以恢复双变体，届时需要重新解决变体的命名区分问题。

## 3. 分期计划

> **2026-09-28 修订**：原为三期。用户确认软件尚未分发（只有他本人的机器装了 v1.2.0，且本次会手动重装），改名导致的更新链路中断因此不再是顾虑；同时新增了分层分发设计（`2026-09-28-layered-distribution-design.md`），它与改名、变体收敛动的是同一批文件。据此压缩为两期，原第一期已经完成，原计划的 v1.2.1 取消。

| 期 | 内容 | 版本 | 状态 | 用户动作 |
|---|---|---|---|---|
| 一 | 加载提示内嵌 + 配色修复 | 并入 v1.3.0 | **已完成**（PR #8 已合并） | — |
| 二 | 改名 + 图标 + 变体收敛 + 分层分发 | v1.3.0 | 待实现 | 手动安装完整包，最后一次 |
| 三 | 标注窗口方向 B | v1.4.0 | 待实现 | 自动更新，只下应用层（几 MB） |

分期的理由：

- 第三期改动最大、回归风险最高，单独成版便于定位问题。
- 第二期一次性完成改名、变体收敛与分层分发，因为三者改的是同一批文件（`labeling_tool.spec`、`installer.iss`、CI workflow），分次改要把同一个文件翻多遍。
- 用户在第二期手动安装一次之后，从第三期起所有更新都是增量的。

## 4. 第一期：加载提示内嵌（已完成，PR #8）

### 4.1 问题根因

`labeling_tool/app.py:44`：

```python
notice = QLabel(tr("app_fewshot_loading"))
notice.setWindowFlags(Qt.SplashScreen | Qt.WindowStaysOnTopHint)
```

一个裸 `QLabel` 被直接当作顶层窗口。应用级暗色样式表中的 `QLabel { color: #e0e0e0 }` 使文字变成浅灰，但这个无父窗口的 label 没有应用到背景色规则，保持系统默认白底，形成浅灰字配白底的低对比组合。

### 4.2 方案

删除该浮窗。`LoginDialog` 增加两个方法：

- `enter_loading_state(message: str)` — 禁用 tab 栏与"다음"按钮，在按钮上方插入加载区：转圈图标、不定量进度条（`QProgressBar` 设 `range(0, 0)`）、说明文字。
- `exit_loading_state(error: str | None = None)` — 恢复可交互状态；`error` 非空时在原加载区位置显示错误文本。

`app.py` 的调用时序相应调整。现状是 `login.exec_()` 返回后才调用 `open_tool_window()`；改为 few-shot 分支在 dialog 仍然存活时加载模型，加载成功后再 `accept()`。

加载失败时登录窗留在原地显示错误，用户可以直接切换到别的 tab，不必重启应用。这比现状（弹出 `QMessageBox` 后回到登录界面）少一次交互。

### 4.3 影响面

- `labeling_tool/app.py` — `_open_fewshot_window()` 与 `main()` 的 few-shot 分支
- `labeling_tool/ui/login_dialog.py` — 新增加载态
- `labeling_tool/core/i18n/strings_{ko,zh,en}.py` — `app_fewshot_loading` 复用，新增加载区副标题与失败提示键

## 5. 第二期：命名、图标与变体收敛（v1.3.0）

### 5.1 改名波及点

全部改为 `LM_LabelingTool`：

| 文件 | 位置 |
|---|---|
| `packaging/labeling_tool.spec` | `EXE(name=)`、`COLLECT(name=)` |
| `packaging/installer.iss` | `MyAppName`、`DefaultDirName`、`DefaultGroupName`、`UninstallDisplayIcon`、`OutputBaseFilename`、`[Run]` 与 `[Icons]` 段的 exe 路径 |
| `.github/workflows/build-windows.yml` | 所有 `dist\LabelingTool` 路径、自检与打包步骤 |
| `labeling_tool/update/checker.py` | `asset_name_for()` 返回的资产名模板 |

### 5.2 自动更新断链的处理

`checker.py` 的 `asset_name_for()` 与 `installer.iss` 的 `OutputBaseFilename` 是一份隐式契约。改名后，已安装 v1.2.0 的客户端会去查找 `LabelingTool-full-Setup-v1.3.0.exe`，而 release 中只有 `LM_LabelingTool-full-Setup-v1.3.0.exe`，`find_update()` 因 `wanted not in assets` 返回 `None`，客户端静默地不提示更新。

用户已确认接受此后果：**现有安装需手动下载 v1.3.0 安装包安装一次**。软件尚未对外分发，受影响的只有用户本人的机器，他也已计划本次重装。

安装时 `AppId` 保持 full 变体原有的值，Inno Setup 会将其识别为升级，原地覆盖旧版本、保留 `config.json`、`data\` 与 `checkpoint\`，控制面板中不会出现两个程序条目。

**前提是现有安装为 full 变体**。由于 lite 与 full 使用不同的 `AppId`（分别以 `...0F01` 与 `...0F02` 结尾），若现有安装是 lite 变体，v1.3.0 不会将其识别为升级，两者会并存于控制面板。

已于 2026-09-28 与用户确认：**现有安装为 full 变体**，因此 v1.3.0 沿用 full 的 `AppId`（`...0F02`）即可原地升级，无需卸载。

从 v1.3.0 起，新旧资产名一致，自动更新恢复正常，且由于同期引入了分层分发
（`2026-09-28-layered-distribution-design.md`），此后只要运行时层不变，更新只下载应用层。

### 5.3 变体收敛

- `installer.iss` 删除 `#if MyVariant == "full"` 双分支，只保留单一命名与 `AppId`。保留 full 变体原有的 `AppId`（`...0F02`），使现有 full 安装能被识别为升级。
- `.github/workflows/build-windows.yml` 的 build matrix 由 `[lite, full]` 收敛为 `full`；`SHA256SUMS-*.txt` 的合并步骤相应简化。
- `labeling_tool/update/version.py` 的 `VARIANTS` 保留 `("full",)`。`is_release_build` 的判定逻辑不变（仍要求 variant 在 `VARIANTS` 内且版本号为纯数字）。
- `labeling_tool/selftest.py` 的变体参数保留，CI 只以 `--selftest=full` 调用。

### 5.4 图标

新建 `packaging/icon.ico`，采用方案 A（字母标）：圆角方形深底 `#1b1f25`、蓝色描边 `#2d6cdf`、居中白色 `LM` 字样、下方一道蓝色短线。

制作方式：先绘制 SVG 源文件 `packaging/icon.svg`（纳入版本管理），再合成多尺寸 ico，包含 16/24/32/48/64/128/256 七层。小尺寸层适当加粗字重、按比例缩放蓝线宽度，避免大尺寸显单薄、小尺寸糊成一团。

接入两处：`labeling_tool.spec` 的 `EXE(icon=)`，`installer.iss` 的 `SetupIconFile`。

## 6. 第三期：标注窗口方向 B（v1.4.0）

### 6.1 生产标注窗口重排

由"画布 + 右侧八组竖排滚动栏"改为五区布局：

- **顶部工具条** — 类别分段控件（균열 / 박리）、四个工具切换（브러시 / SAM 분할 / 보수 구역 / 축척）、右端"현재 저장"主操作按钮
- **左侧 dock** — 图片列表，带缩略图
- **中央** — 画布
- **右栏** — 仅显示当前选中工具的参数
- **底部状态栏** — 축척值、完成进度、当前文件名

核心收益：常驻可见的分组由八个降为一个，右栏不再需要滚动；当前工具在工具条中高亮，解决"看不出在用哪个工具"的问题。

### 6.2 `ui_builder.py` 的改造

保留八个 `build_*_group` 的函数边界，改变其返回形态与归属：

| 原分组 | 去向 |
|---|---|
| `build_category_group` | 顶部工具条的分段控件 |
| `build_brush_group` / `build_bbox_group` / `build_scale_group` / SAM 相关 | 右栏的可切换工具面板，同一时刻只有一个可见 |
| `build_settings_group` | 顶部工具条右侧的设置入口 |
| `build_list_group` | 左侧 dock |
| `build_nav_group` | 顶部工具条的保存按钮 + 底部状态栏的进度 |
| `build_hint_group` | 右栏底部的快捷键说明区 |

控件对象本身、信号连接与快捷键绑定保持不变，只改变父子关系与布局归属。这是为了让现有的窗口测试尽可能少改。

### 6.3 两个应用的样式统一

`labeling_tool/core/window/styles.py` 与 `annotation_tool/ui/styles.py` 的色板本就一致（`#1f2329` 底、`#2d6cdf` 主色、`#e0e0e0` 文字）。将共用部分提取为一份共享样式，两侧各自只保留自己独有的控件规则（前者的 `QGroupBox`/`sidePanel`，后者的 `QDockWidget`/`QListWidget`/`QRadioButton`）。

提取后的共享样式放在 `labeling_tool/core/window/styles.py` 中作为基础常量，由 `annotation_tool` 导入后追加自己的规则。这一依赖方向与既有约定一致（`annotation_tool` 依赖 `labeling_tool.core`，反向不成立）。

few-shot 窗口本身已是左右 dock 结构，方向 B 之后两个应用的骨架对齐，主要工作是套用统一后的样式。

### 6.4 登录与作业获取对话框

按新样式走一遍，重点是间距节奏与按钮层级（主操作实心蓝、次级描边）。不改变控件构成与交互流程。

## 7. i18n

方向 B 引入新的用户可见文案：工具条的工具名、底部状态栏的字段标签、右栏快捷键说明区。第一期也会新增加载区的副标题与失败提示。

按项目既定规矩：**先在 `docs/i18n-glossary.md` 中确定术语，再写入三份 `strings_{ko,zh,en}.py`**。已有术语（균열 / 박리 / 축척 / 보수 구역 / 마스크）沿用，不得在本次改版中另起译法。

`tests/test_i18n_coverage.py` 的键平价检查与 AST 级 CJK 扫描会自动捕获遗漏的硬编码文案。新增 UI 模块时需同步加入 `UI_MODULES` 列表。

## 8. 测试策略

基线：388 个测试全部通过，全程保持绿。

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider
```

- **第一期** — 新增登录窗加载态测试：进入加载态后 tab 与"다음"按钮被禁用、加载区可见；加载失败后恢复可交互并显示错误。注意 offscreen Qt 下模态 `QMessageBox` 会挂起测试，失败路径必须走内嵌错误显示而非弹框，这也正是本期方案的行为。
- **第二期** — 主要是打包层改动，由 CI 的"安装 → `--selftest=full` → 卸载"覆盖。另需断言 release 资产名与 `asset_name_for()` 的输出一致，防止契约再次漂移。建议新增一个纯逻辑测试，直接比对两者的字符串模板。
- **第三期** — 现有窗口测试需随控件归属调整而修改，工作量在本次改版中最大，实现计划中单独列为一项。

## 9. 风险

| 风险 | 应对 |
|---|---|
| 第二期断更新后，用户忘记手动安装，长期停留在 v1.2.0 | 在 v1.3.0 的 release notes 中显著说明；分期发布使该版本内容单一，便于说明 |
| 资产名契约再次漂移 | 第二期新增字符串模板比对测试 |
| 第三期改动面大，回归风险高 | 保留控件与信号不变，只改父子关系；单独成版发布，便于定位问题 |
| 单变体后生产机器下载体积增大 | 已记录于 2.1，作为已知权衡接受 |

## 10. 下一步

本设计文档确认后，进入实现计划（`docs/superpowers/plans/`），按三期拆分任务。
