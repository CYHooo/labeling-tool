# 全界面语言设置（한국어 / 中文 / English）

日期：2026-09-24
状态：设计待确认
分支：`feat/i18n-all-ui`（基于 `main`，需在 PR #5 合并后 rebase）

## 背景 / 目标

现在界面语言是混的：主窗口有完整的三语切换（`labeling_tool/core/i18n.py`，213 个 key），但**其他界面全是硬编码**——登录界面 33 处韩文、获取数据 15 处、SAM2.1 权重下载 10 处、更新提示 21 处、few-shot 工具 26 处中文。而且主窗口选的语言**不会保存**，每次启动回到英文。

目标：**所有界面统一走同一套翻译，可在运行时切换，选择会记住。**

用户决定（2026-09-24）：全部界面（含 few-shot 工具）；支持 한국어 / 中文 / English；**首次启动默认韩语**；切换入口在登录界面和主窗口，两处同步。

非目标：Qt 自带的 `.ts/.qm` 翻译体系（现有字典足够且改动小）、RTL 语言、翻译外包流程、日志与异常文本的翻译（保持英文，便于排查）。

## 1. 模块结构

把现在的单文件 `labeling_tool/core/i18n.py`（270 行，加完新 key 会到 ~700 行）拆成包：

```
labeling_tool/core/i18n/
├── __init__.py      运行时 API（tr / 当前语言 / 切换 / 信号）
├── strings_ko.py    한국어（新增：默认语言）
├── strings_zh.py    中文
└── strings_en.py    English（回退语言）
```

每个 `strings_*.py` 只含一个 `STRINGS: dict[str, str]`，按界面分区注释（`# --- login ---`、`# --- fetch ---`、`# --- update ---`、`# --- few-shot ---` …）。

### API

```python
LANGUAGES = ("ko", "zh", "en")           # 顺序即下拉框顺序
LANG_DISPLAY_NAMES = {"ko": "한국어", "zh": "中文", "en": "English"}
FALLBACK_LANG = "en"

def tr(key: str, **kwargs) -> str          # 当前语言 -> 回退英文 -> key 本身
def current_language() -> str
def set_language(code: str) -> None        # 持久化 + 发出 languageChanged
def language_manager() -> LanguageManager  # QObject，signal languageChanged(str)
```

- `tr()` 不依赖 Qt，纯逻辑模块可直接用。
- `LanguageManager` 是懒加载的 QObject 单例，界面连接它的 `languageChanged` 信号实现实时刷新。
- 缺失 key：回退英文；英文也缺则返回 key 本身（不崩溃），并且**测试会保证不存在缺 key**。

## 2. 持久化

新增 `labeling_tool/core/settings.py`：读写 `app_home()/ui-settings.json`（`{"lang": "ko"}`）。

- 不动 `config.json`（那是凭证文件，`save_config(base, key)` 会整体覆写，混入界面设置容易误删）。
- 读取失败 / 文件损坏 / 只读目录 → 返回默认值、静默忽略写入失败（与 `update/state.py` 同样的原则）。
- 首次启动没有文件 → **韩语**。

## 3. 界面接入

| 界面 | 改动 |
|---|---|
| 登录界面 | 底部那一行（版本 + 업데이트 확인）左侧加语言下拉框；切换立即刷新本窗口全部文字 |
| 获取数据界面 | 文字接入 `tr()`；打开时按当前语言渲染 |
| SAM2.1 权重下载 / 更新提示 / 启动错误弹窗 | 同上 |
| 生产主窗口 | 保留现有下拉框，但改为读写同一套 API（不再用实例变量 `self.lang`）；与登录界面互相同步 |
| few-shot 工具 | 现有中文文案（类别面板、工具按钮、提示）接入 `tr()` |

每个窗口实现 `retranslate()`，在构造时调用一次、并连接 `languageChanged`。已经打开的窗口会**实时切换**，不需要重启。

## 4. 测试

- **Key 完整性**：三份 `strings_*.py` 的 key 集合完全一致；没有空字符串；带 `{}` 占位符的 key 在三语中占位符集合相同（防止 `format` 崩溃）。
- **回退**：缺失 key 时回退英文；英文也缺时返回 key。
- **持久化**：`set_language` 写入并能读回；损坏文件读为默认；只读目录不抛异常。
- **默认值**：无设置文件时为 `ko`。
- **实时刷新**：构造登录界面 → `set_language("en")` → 断言按钮/标签文字变化；主窗口同理。
- **回归守卫（重要）**：扫描所有界面模块源码，断言**没有硬编码的中日韩字符**（允许清单：`strings_*.py`、`LANG_DISPLAY_NAMES`、文档字符串与注释）。这条测试保证以后新增界面文字时不会再退回硬编码。

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| 翻译质量：现有韩文是产品用语，中文/英文需新写 | 以现有韩文为准翻译；界面截图人工核对（生产用户用韩语，优先保证韩文不变） |
| 遗漏某处文案 | 第 4 节的 CJK 扫描测试会在 CI 中失败 |
| 改动面大（约 15 个文件） | 分 5 个任务逐个界面推进，每步全套测试通过 |
| few-shot 工具引入 `labeling_tool.core.i18n` 依赖 | 已有同样的依赖（`app_paths`），且 `core/__init__` 已是惰性导入，不会拉入 Qt 主窗口 |
| exe 中语言文件缺失 | 纯 Python 模块，PyInstaller 的 `collect_submodules("labeling_tool")` 已覆盖；lite 版自检会构造登录界面，可及早发现 |
| 主窗口现有 213 个 key 的行为变化 | 保留全部 key 与 `tr_` 方法（改为转发到新 API），主窗口测试不动 |

## 6. 交付物

- `labeling_tool/core/i18n/`（4 个文件）、`labeling_tool/core/settings.py`
- 登录 / 获取 / 权重 / 更新 / 启动弹窗 / 主窗口 / few-shot 界面的文案接入
- 测试：key 完整性、回退、持久化、实时刷新、CJK 扫描守卫
- README（韩文）补充"언어 설정"一节；`docs/README.md` 索引
