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
| upload status (list) | **✓ 업로드됨** · **● 수정됨 (업로드 필요)** | ✓ 已上传 · ● 已修改（需上传） | ✓ uploaded · ● edited (needs upload) | 图片列表编号前的标记；表头悬停提示 |
| photo range (fetch) | **사진**: **전체** / **범위 지정**, **사진 번호** `a ~ b`（`b` 可为 **끝** / 最后 / End） | 照片：全部 / 指定范围，照片编号 | Photos: All / Range, Photo number | 「새 작업 가져오기」界面；接口参数 `fromNum`/`toNum` 不出现在界面上 |
| range view (labeling) | **사진 {a} ~ {b} ({n}장)** · **전체 보기** / **범위만 보기** · `{shown} / {total}장` | 照片 {a} ~ {b}（{n} 张）· 显示全部 / 只看范围 · `{shown} / {total} 张` | Photos {a} ~ {b} ({n}) · Show all / Range only · `Photos: {shown} / {total}` | 范围下载后标注窗口只列出该范围；上传也只传列出的照片 |
| previous / next photo | **이전 사진** / **다음 사진** | 上一张 / 下一张 | Previous / Next | 标注窗口导航按钮；中/英为了面板宽度用短形式 |
| edit tools | **편집 도구**: **보기** · **브러시** · **SAM** · **보수 구역** | 编辑工具：查看 · 画笔 · SAM · 修补区域 | Edit tools: View · Brush · SAM · Repair area | 2×2 工具按钮，选中的工具即编辑模式；`보기` = 不编辑。另一组 **표시 · 축척** / 显示 · 比例尺 / Display · Scale |
| job info | **작업 정보** | 任务信息 | Job info | 标注窗口右侧顶部一行：`작업 {id} · {점검명} · {n}장`；图片列表表头 `번호` / `파일 이름`，列表项 `<작업 ID>-<사진 번호>` + 文件名 |
| upload | **업로드** | 上传 | Upload | 音译已通用 |
| download / fetch | **가져오기** | 获取 | Fetch | 从服务器取数据用 `가져오기`；文件下载用 `다운로드` |
| local（本机已取得的作业） | **로컬 작업** | 本地任务 | Local jobs | 登录界面「라벨링」标签页里的任务列表标题（原独立标签页已合并） |
| sign in / log out | **로그인** / **로그아웃** | 登录 / 退出登录 | Log in / Log out | 第一页的账号登录；`로그인: {user}` 显示当前用户 |
| password | **비밀번호** | 密码 | Password | 账号字段名保持 `ID` |
| output folder | **저장 폴더** | 保存文件夹 | Output folder | |
| log / app log | **로그** / **프로그램 로그** | 日志 / 程序日志 | Log / App log | 帮助窗口按钮 `로그 폴더 열기` / 打开日志文件夹 / Open log folder；文件名 `app.log`、`vapi.log` 不翻译 |

## 3. 测量与几何

| 概念 | 한국어 | 中文 | English | 说明 |
|---|---|---|---|---|
| scale（px/cm 换算） | **축척** | 比例尺 | Scale | 现为 `스케일`。`축척` 是测量/制图的标准词，更准确 |
| manual measurement | **수동 측정** | 手动测量 | Manual measurement | 保留；英文按钮因面板宽度用短形式 `Measure`。手动测得的축척数值以琥珀色显示，提示文字 `수동 측정값 (서버 값 대신 사용)` / 手动测量值（替代服务器的值） / Measured by hand (used instead of the server's value) |
| bounding box / 补修区域 | **보수 구역** | 修补区域 | Repair area | 现状为 OBB/bbox 等技术词，对用户改用 `보수 구역` |
| brush / eraser | **브러시** / **지우개** | 画笔 / 橡皮擦 | Brush / Eraser | |
| undo / redo | **실행 취소** / **다시 실행** | 撤销 / 重做 | Undo / Redo | 掩码编辑（画笔、SAM 确认、복원）；Ctrl+Z / Ctrl+Y |

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
| loading（模型加载） | **로딩** | 加载 | Loading | 指把权重载入内存的过程；进行中用 `로딩 중…`，句尾省略号统一用 `…` |
| full reinstall（完整重装） | **전체 설치** | 完整重装 | Full reinstall | 仅当运行时层（torch/CUDA）变化时需要，约 1.5 GB；应用层更新只有几十 MB |

## 5. 文体规则

- **韩语**：界面文字用 `해요체` 的正式形（`-습니다` / `-하세요`），与现有产品文案一致；按钮用体言结尾（`저장`、`열기`），不加句号。
- **中文**：简体，按钮用动词（`保存`、`打开`），句末不加句号。
- **English**：句首大写、其余小写（sentence case），按钮不加句号。
- **占位符**：三语必须使用同一组 `{name}`，顺序可不同。测试会校验。
- **技术标识符不翻译**：`sessionId`、`BASE URL`、`X-Viewer-Api-Key`、`SHA256`、文件名与路径、few-shot 类别名。
- **日志与异常文本保持英文**（`vapi.log`、堆栈信息），便于检索排查。
- **菜单快捷字母（mnemonic，如英文 `&File`）只在英文里保留 `&`**：Alt 加字母的菜单快捷键（如 Alt+F）依赖该字母出现在标签文字里，中/韩文标签（`파일`/`文件`）没有这样的字母，所以中/韩文不使用 `&`，也没有等效的 Alt 快捷键。
