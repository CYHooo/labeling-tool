# 界面术语表 / UI Glossary（ko · zh · en）

所有界面文案以本表为准。改词时**先改这里**，再改 `labeling_tool/core/i18n/strings_*.py`。

- **韩语是生产用户的语言**，取词以建筑/结构检测领域的通用书面语为准，不用外来语音译（除非该音译已是行业惯用）。
- 现有界面里的韩文多为机器翻译，本表会覆盖它们；下表"现状"列标出会被替换的写法。
- few-shot 工具的类别名（joint / concrete / scalebar / shoe / distractor）**不翻译**，因为它们对应 `classes.json` 里的像素值定义，翻译后会和数据集对不上。

## 1. 缺陷与检测对象

| 概念 | 한국어 | 中文 | English | 现状 → 变更理由 |
|---|---|---|---|---|
| crack | **균열** | 裂缝 | Crack | 现为 `Crack(균열)`。`균열` 是韩国建筑领域标准用词，界面只留韩文，不再并列英文 |
| spalling | **박리** | 剥落 | Spalling | 现为 `Spalling(박리)`。`박리`（表层剥离）比 `박락`（块状脱落）更贴合本工具标注的表层缺陷 |
| mask | **마스크** | 掩膜 | Mask | 图像处理领域已惯用音译 `마스크`，保留 |
| 标注（动作/结果） | **라벨링** | 标注 | Labeling | 行业内 `라벨링` 已通用；`주석` 多指文字注释，不采用 |
| 类别 | **카테고리** | 类别 | Category | 保留现状 |

## 2. 作业与数据

| 概念 | 한국어 | 中文 | English | 说明 |
|---|---|---|---|---|
| session（服务器上的一次作业） | **작업** | 任务 | Job | 现状混用 `세션`/`작업`。对用户统一叫 `작업`；`sessionId` 这类**技术标识符保持英文原样** |
| session id | **작업 ID** | 任务 ID | Job ID | 列表里仍显示服务器返回的数字 |
| inspection name | **점검명** | 检测名称 | Inspection name | `점검` 是设施点检的标准用词，保留 |
| photo | **사진** | 照片 | Photo | |
| upload | **업로드** | 上传 | Upload | 音译已通用 |
| download / fetch | **가져오기** | 获取 | Fetch | 从服务器取数据用 `가져오기`；文件下载用 `다운로드` |
| local（本机已取得的作业） | **로컬 작업** | 本地任务 | Local jobs | 保留现有标签页名 |
| output folder | **저장 폴더** | 保存文件夹 | Output folder | |

## 3. 测量与几何

| 概念 | 한국어 | 中文 | English | 说明 |
|---|---|---|---|---|
| scale（px/cm 换算） | **축척** | 比例尺 | Scale | 现为 `스케일`。`축척` 是测量/制图的标准词，更准确 |
| manual measurement | **수동 측정** | 手动测量 | Manual measurement | 保留 |
| bounding box / 补修区域 | **보수 구역** | 修补区域 | Repair area | 现状为 OBB/bbox 等技术词，对用户改用 `보수 구역` |
| brush / eraser | **브러시** / **지우개** | 画笔 / 橡皮擦 | Brush / Eraser | |

## 4. 程序与更新

| 概念 | 한국어 | 中文 | English | 说明 |
|---|---|---|---|---|
| install | **설치** | 安装 | Install | |
| update | **업데이트** | 更新 | Update | |
| version | **버전** | 版本 | Version | |
| settings | **설정** | 设置 | Settings | |
| language | **언어** | 语言 | Language | |
| weights（模型权重） | **가중치** | 权重 | Weights | |
| lite / full（安装包变体） | **lite / full** | lite / full | lite / full | 不翻译，与下载文件名一致 |

## 5. 文体规则

- **韩语**：界面文字用 `해요체` 的正式形（`-습니다` / `-하세요`），与现有产品文案一致；按钮用体言结尾（`저장`、`열기`），不加句号。
- **中文**：简体，按钮用动词（`保存`、`打开`），句末不加句号。
- **English**：句首大写、其余小写（sentence case），按钮不加句号。
- **占位符**：三语必须使用同一组 `{name}`，顺序可不同。测试会校验。
- **技术标识符不翻译**：`sessionId`、`BASE URL`、`X-Viewer-Api-Key`、`SHA256`、文件名与路径、few-shot 类别名。
- **日志与异常文本保持英文**（`vapi.log`、堆栈信息），便于检索排查。
- **菜单快捷字母（mnemonic，如 `&File`）只保留英文写法**：中/韩文菜单标签没有字母可供下划线标记，因此三语共用英文 `&` 写法，不为中/韩文额外造一套。
