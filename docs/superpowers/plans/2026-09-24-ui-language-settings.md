# 全界面语言设置 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 所有界面（生产工具 + few-shot 工具）统一走同一套翻译，可在运行时切换 한국어 / 中文 / English，选择会被记住。

**Architecture:** 现有单文件 `labeling_tool/core/i18n.py` 拆为 `labeling_tool/core/i18n/` 包：`__init__.py` 提供 `tr()` / `set_language()` / `LanguageManager`（QObject，`languageChanged` 信号），三份 `strings_*.py` 各含一个 `STRINGS` 字典。语言选择存在 `app_home()/ui-settings.json`（`labeling_tool/core/settings.py`），默认韩语。每个窗口实现 `retranslate()`，构造时调用一次并连接 `languageChanged`，实现无需重启的实时切换。

**Tech Stack:** Python 3.12、PyQt5。无新依赖。

**Spec:** `docs/superpowers/specs/2026-09-24-ui-language-settings-design.md`
**术语表（所有文案的唯一依据）:** `docs/i18n-glossary.md`

## Global Constraints

- **文案一律照 `docs/i18n-glossary.md`**：`균열`(crack)、`박리`(spalling)、`축척`(scale)、`작업`(job/session)、`보수 구역`(repair area)、`라벨링`(labeling)、`점검명`(inspection name)、`마스크`(mask)、`가중치`(weights)。
- 韩语用正式体（`-습니다` / `-하세요`），按钮用体言结尾不加句号；中文按钮用动词不加句号；英文 sentence case。
- **不翻译**：`sessionId`、`BASE URL`、`X-Viewer-Api-Key`、`SHA256`、文件名与路径、lite/full、few-shot 类别名（joint / concrete / scalebar / shoe / distractor）。
- **日志与异常文本保持英文**（`vlog()`、异常消息），只翻译界面可见文字。
- 三种语言的 key 集合必须完全一致，占位符集合也必须一致。
- 默认语言 `ko`；设置文件损坏或只读时静默回退，不得抛异常。
- 代码注释英文。提交信息：主题行、空行、`Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。
- 测试基线 348 passed：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
- 不碰 `labeling_tool/config.json`、`labeling_tool/data/`、`checkpoint/`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `labeling_tool/core/i18n/__init__.py`（新） | `tr` / `current_language` / `set_language` / `language_manager` / `LANGUAGES` / `LANG_DISPLAY_NAMES` / `FALLBACK_LANG`；兼容导出 `TRANSLATIONS` |
| `labeling_tool/core/i18n/strings_ko.py`（新） | 한국어（默认） |
| `labeling_tool/core/i18n/strings_zh.py`（新） | 中文 |
| `labeling_tool/core/i18n/strings_en.py`（新） | English（回退） |
| `labeling_tool/core/i18n.py` | 删除（内容迁入上面四个文件） |
| `labeling_tool/core/settings.py`（新） | `ui-settings.json` 读写 |
| `labeling_tool/ui/login_dialog.py` | 语言下拉框 + `retranslate()` |
| `labeling_tool/ui/fetch_dialog.py`、`ui/sam2_weights_dialog.py`、`update/ui.py`、`app.py` | 文案接入 `tr()` |
| `labeling_tool/core/window/main_window.py` | `tr_` 转发到新 API，语言下拉框与登录界面同步 |
| `annotation_tool/ui/main_window.py` | 文案接入 `tr()` |
| `tests/test_i18n_coverage.py`（新） | key 完整性 + CJK 字面量扫描守卫 |

---

### Task 1: i18n 包 + 设置持久化

**Files:**
- Create: `labeling_tool/core/i18n/__init__.py`、`strings_ko.py`、`strings_zh.py`、`strings_en.py`、`labeling_tool/core/settings.py`
- Delete: `labeling_tool/core/i18n.py`
- Test: `labeling_tool/tests/test_i18n_api.py`、`labeling_tool/tests/test_settings.py`（新）

**Interfaces:**
- Produces:
  - `labeling_tool.core.i18n.LANGUAGES = ("ko", "zh", "en")`、`LANG_DISPLAY_NAMES = {"ko": "한국어", "zh": "中文", "en": "English"}`、`FALLBACK_LANG = "en"`
  - `tr(key: str, **kwargs) -> str`、`current_language() -> str`、`set_language(code: str) -> None`、`language_manager() -> LanguageManager`（QObject，signal `languageChanged = pyqtSignal(str)`）
  - 兼容：`TRANSLATIONS: dict[str, dict[str, str]]`（`{"ko": STRINGS_KO, ...}`，供旧代码读取）
  - `labeling_tool.core.settings.SETTINGS_NAME = "ui-settings.json"`、`load_settings(home=None) -> dict`、`save_settings(data: dict, home=None) -> None`、`get_language(home=None) -> str`、`set_language_setting(code: str, home=None) -> None`

- [ ] **Step 1: 写失败测试** `labeling_tool/tests/test_settings.py`

```python
"""UI settings live next to the exe and never break the app."""
import json

from labeling_tool.core import settings


def test_defaults_to_korean(tmp_path):
    assert settings.get_language(tmp_path) == "ko"


def test_round_trip(tmp_path):
    settings.set_language_setting("zh", tmp_path)
    assert settings.get_language(tmp_path) == "zh"
    assert json.loads((tmp_path / settings.SETTINGS_NAME).read_text())["lang"] == "zh"


def test_unknown_language_falls_back(tmp_path):
    (tmp_path / settings.SETTINGS_NAME).write_text(json.dumps({"lang": "fr"}))
    assert settings.get_language(tmp_path) == "ko"


def test_broken_file_is_ignored(tmp_path):
    (tmp_path / settings.SETTINGS_NAME).write_text("{broken")
    assert settings.get_language(tmp_path) == "ko"


def test_unwritable_home_does_not_raise(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir(mode=0o500)
    settings.set_language_setting("en", ro)   # must not raise


def test_other_keys_survive(tmp_path):
    settings.save_settings({"lang": "en", "other": 1}, tmp_path)
    settings.set_language_setting("zh", tmp_path)
    assert settings.load_settings(tmp_path)["other"] == 1
```

`labeling_tool/tests/test_i18n_api.py`：

```python
"""Translation lookup, fallback and the language-change signal."""
import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool.core import i18n
from labeling_tool.core.i18n import strings_en, strings_ko, strings_zh

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")


def test_language_order_and_names():
    assert i18n.LANGUAGES == ("ko", "zh", "en")
    assert i18n.LANG_DISPLAY_NAMES["ko"] == "한국어"


def test_tr_uses_current_language():
    i18n.set_language("zh")
    assert i18n.tr("language") == strings_zh.STRINGS["language"]
    i18n.set_language("en")
    assert i18n.tr("language") == strings_en.STRINGS["language"]


def test_tr_formats_placeholders():
    # every language must accept the same kwargs
    for code in i18n.LANGUAGES:
        i18n.set_language(code)
        assert "42" in i18n.tr("fetch_progress", done=42, total=99)


def test_missing_key_falls_back_to_english(monkeypatch):
    monkeypatch.setitem(strings_ko.STRINGS, "only_en", None)
    strings_ko.STRINGS.pop("only_en")
    monkeypatch.setitem(strings_en.STRINGS, "only_en", "English only")
    i18n.set_language("ko")
    assert i18n.tr("only_en") == "English only"


def test_unknown_key_returns_the_key():
    assert i18n.tr("no_such_key_at_all") == "no_such_key_at_all"


def test_set_language_persists_and_emits():
    seen = []
    i18n.language_manager().languageChanged.connect(seen.append)
    i18n.set_language("en")
    assert seen == ["en"]
    assert i18n.current_language() == "en"


def test_set_language_ignores_unknown_code():
    i18n.set_language("ko")
    i18n.set_language("fr")
    assert i18n.current_language() == "ko"
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_settings.py labeling_tool/tests/test_i18n_api.py -q -p no:cacheprovider`
Expected: FAIL（`labeling_tool.core.settings` 不存在；`i18n` 还是旧单文件）

- [ ] **Step 3: 实现**

`labeling_tool/core/settings.py`：

```python
"""UI preferences stored next to the exe (ui-settings.json).

Kept apart from config.json: that file holds credentials and is rewritten
wholesale by save_config(base, key), which would drop anything else in it.
Every failure here is swallowed — a read-only install must not break the app
over a preference.
"""

from __future__ import annotations

import json
from pathlib import Path

from labeling_tool.core.app_paths import app_home

SETTINGS_NAME = "ui-settings.json"
DEFAULT_LANGUAGE = "ko"


def _path(home: Path | None) -> Path:
    return (Path(home) if home is not None else app_home()) / SETTINGS_NAME


def load_settings(home: Path | None = None) -> dict:
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict, home: Path | None = None) -> None:
    try:
        _path(home).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                               encoding="utf-8")
    except OSError:
        pass


def get_language(home: Path | None = None) -> str:
    from labeling_tool.core.i18n import LANGUAGES
    lang = load_settings(home).get("lang")
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def set_language_setting(code: str, home: Path | None = None) -> None:
    data = load_settings(home)
    data["lang"] = code
    save_settings(data, home)
```

`labeling_tool/core/i18n/__init__.py`：

```python
"""UI translations: lookup, current language, and a change signal.

Strings live in strings_<code>.py, one STRINGS dict each; docs/i18n-glossary.md
is the authority for terminology. tr() itself needs no Qt, so non-GUI modules
can use it; language_manager() is the QObject widgets connect to in order to
retranslate themselves when the language changes.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal

from labeling_tool.core.i18n import strings_en, strings_ko, strings_zh

LANGUAGES = ("ko", "zh", "en")
LANG_DISPLAY_NAMES = {"ko": "한국어", "zh": "中文", "en": "English"}
FALLBACK_LANG = "en"

TRANSLATIONS = {
    "ko": strings_ko.STRINGS,
    "zh": strings_zh.STRINGS,
    "en": strings_en.STRINGS,
}

_current: str | None = None
_manager: "LanguageManager | None" = None


class LanguageManager(QObject):
    """Emits languageChanged(code) so open windows can retranslate."""
    languageChanged = pyqtSignal(str)


def language_manager() -> LanguageManager:
    global _manager
    if _manager is None:
        _manager = LanguageManager()
    return _manager


def _settings_home():
    return None  # tests patch this to redirect ui-settings.json


def current_language() -> str:
    global _current
    if _current is None:
        from labeling_tool.core.settings import get_language
        _current = get_language(_settings_home())
    return _current


def set_language(code: str) -> None:
    """Switch language, persist it and notify open windows. Unknown code: ignored."""
    global _current
    if code not in LANGUAGES or code == current_language():
        return
    from labeling_tool.core.settings import set_language_setting
    _current = code
    set_language_setting(code, _settings_home())
    language_manager().languageChanged.emit(code)


def tr(key: str, **kwargs) -> str:
    """Current language, then English, then the key itself."""
    text = TRANSLATIONS.get(current_language(), {}).get(key)
    if text is None:
        text = TRANSLATIONS[FALLBACK_LANG].get(key, key)
    return text.format(**kwargs) if kwargs else text
```

`strings_ko.py` / `strings_zh.py` / `strings_en.py`：把旧 `i18n.py` 中 `TRANSLATIONS["ko"|"zh"|"en"]` 的内容分别搬过去，改为 `STRINGS = {...}`，并按术语表修正韩文（`"cat_crack": "균열"`、`"cat_spalling": "박리"`、`"group_scale": "축척 (px/cm)"` 等）。文件头写明 `# Terminology: docs/i18n-glossary.md`。每个文件按界面分区加注释（`# --- main window ---`、`# --- login ---` …），本任务只需迁移现有 key，新界面的 key 在 Task 2–5 逐步添加。

删除 `labeling_tool/core/i18n.py`。

- [ ] **Step 4: 运行全部测试** → 全部 PASS（主窗口仍用 `TRANSLATIONS`，不受影响）
- [ ] **Step 5: 提交**（subject: `feat(i18n): package with ko/zh/en strings and persisted setting`）

---

### Task 2: key 完整性与 CJK 字面量守卫

**Files:**
- Create: `tests/test_i18n_coverage.py`
- Modify: 若守卫发现 `strings_*.py` 的 key 不一致或占位符不一致，就地修正

**Interfaces:**
- Consumes: Task 1 的 `TRANSLATIONS`、`LANGUAGES`
- Produces: `tests/test_i18n_coverage.py::UI_MODULES`（后续任务逐个从"待接入"移到"已接入"的清单）

- [ ] **Step 1: 写测试**

```python
"""Every language covers every key, and UI modules hold no hardcoded CJK text."""
import re
from pathlib import Path

import pytest

from labeling_tool.core.i18n import LANGUAGES, TRANSLATIONS

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[ㄱ-힝一-鿿]")
PLACEHOLDER = re.compile(r"\{(\w+)[^}]*\}")

# UI modules that must already be free of hardcoded CJK string literals.
# Tasks 3-6 append to this list as each screen is migrated; the list is the
# regression guard that keeps them migrated.
UI_MODULES = [
    "labeling_tool/core/window/ui_builder.py",
]


def test_all_languages_share_the_same_keys():
    keys = {code: set(TRANSLATIONS[code]) for code in LANGUAGES}
    base = keys["en"]
    for code in LANGUAGES:
        assert keys[code] == base, (
            f"{code} differs: missing={sorted(base - keys[code])[:5]} "
            f"extra={sorted(keys[code] - base)[:5]}")


def test_no_empty_strings():
    for code in LANGUAGES:
        empty = [k for k, v in TRANSLATIONS[code].items() if not str(v).strip()]
        assert not empty, f"{code} has empty strings: {empty[:5]}"


def test_placeholders_match_across_languages():
    for key, text in TRANSLATIONS["en"].items():
        expected = set(PLACEHOLDER.findall(text))
        for code in LANGUAGES:
            got = set(PLACEHOLDER.findall(TRANSLATIONS[code][key]))
            assert got == expected, f"{key} in {code}: {got} != {expected}"


@pytest.mark.parametrize("rel", UI_MODULES)
def test_ui_module_has_no_hardcoded_cjk(rel):
    """UI text belongs in strings_*.py, never inline in a widget module."""
    offenders = []
    for lineno, line in enumerate(( ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        for literal in re.findall(r'"([^"]*)"|\'([^\']*)\'', code):
            text = literal[0] or literal[1]
            if CJK.search(text):
                offenders.append(f"{rel}:{lineno}: {text[:40]}")
    assert not offenders, "hardcoded UI text:\n" + "\n".join(offenders)
```

- [ ] **Step 2: 运行** → 若失败则修正 `strings_*.py`（补齐 key / 统一占位符），直到 PASS
- [ ] **Step 3: 提交**（subject: `test(i18n): key parity and hardcoded-CJK guard`）

---

### Task 3: 登录界面（含语言下拉框）

**Files:**
- Modify: `labeling_tool/ui/login_dialog.py`、`labeling_tool/core/i18n/strings_*.py`、`tests/test_i18n_coverage.py`（把 `labeling_tool/ui/login_dialog.py` 加入 `UI_MODULES`）
- Test: `labeling_tool/tests/test_login_modes.py`（追加）

**Interfaces:**
- Produces: `LoginDialog.cmb_language`、`LoginDialog.retranslate()`；新 key 前缀 `login_*`

- [ ] **Step 1: 写失败测试**（追加到 `labeling_tool/tests/test_login_modes.py`）

```python
def test_language_combo_switches_live(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    dlg = ld.LoginDialog()
    assert [dlg.cmb_language.itemData(i) for i in range(dlg.cmb_language.count())] \
        == list(i18n.LANGUAGES)
    ko_title = dlg.tabs.tabText(ld.TAB_ONLINE)
    dlg.cmb_language.setCurrentIndex(list(i18n.LANGUAGES).index("en"))
    assert i18n.current_language() == "en"
    assert dlg.tabs.tabText(ld.TAB_ONLINE) != ko_title
    assert dlg.btn_next.text() == i18n.tr("login_next")


def test_dialog_follows_language_changed_signal(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    dlg = ld.LoginDialog()
    i18n.set_language("zh")          # changed elsewhere (e.g. the main window)
    assert dlg.btn_next.text() == i18n.tr("login_next")


def test_job_table_headers_are_translated(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("en")
    dlg = ld.LoginDialog()
    assert dlg.tbl_jobs.horizontalHeaderItem(0).text() == i18n.tr("login_col_job")
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
  - `strings_*.py` 新增 `# --- login ---` 分区，覆盖登录界面全部文案：标签页名、两个输入框标签、`login_next`、作业表 5 个列名、空列表提示、上传可否提示、服务器不一致警告、manifest 读取失败警告、few-shot 说明与 lite 提示、版本行、`업데이트 확인`、语言标签。韩文照术语表（作业列名用 `작업`、点检名用 `점검명`）。
  - `LoginDialog.__init__`：底部行左侧插入 `self.cmb_language`（`addItem(LANG_DISPLAY_NAMES[c], c)`，当前语言选中），`currentIndexChanged` → `i18n.set_language(itemData)`。
  - 新增 `retranslate()`：设置窗口标题、标签页名、所有标签/按钮/表头/提示文字；`__init__` 末尾调用一次，并 `i18n.language_manager().languageChanged.connect(lambda *_: self.retranslate())`。
  - 把 `labeling_tool/ui/login_dialog.py` 加进 `tests/test_i18n_coverage.py` 的 `UI_MODULES`。
- [ ] **Step 4: 全部测试 PASS**
- [ ] **Step 5: 提交**（subject: `feat(i18n): translate the login screen and add the language selector`）

---

### Task 4: 获取数据 / 权重下载 / 更新提示 / 启动弹窗

**Files:**
- Modify: `labeling_tool/ui/fetch_dialog.py`、`labeling_tool/ui/sam2_weights_dialog.py`、`labeling_tool/update/ui.py`、`labeling_tool/app.py`、`strings_*.py`、`tests/test_i18n_coverage.py`（四个文件加入 `UI_MODULES`）
- Test: `labeling_tool/tests/test_update_ui.py`、`test_sam2_weights_dialog.py`（追加各一条断言：文案随语言变化）

**Interfaces:**
- Consumes: Task 1 的 `tr`
- Produces: key 前缀 `fetch_*`、`weights_*`、`update_*`、`app_*`

- [ ] **Step 1: 写失败测试**（每个文件一条即可，重点是"文案来自 tr()"）

```python
# labeling_tool/tests/test_update_ui.py 追加
def test_prompt_text_follows_language(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    captured = {}
    monkeypatch.setattr(ui.QMessageBox, "exec_", lambda self: captured.setdefault("text", self.text()))
    monkeypatch.setattr(ui.QMessageBox, "clickedButton", lambda self: None)
    i18n.set_language("en")
    ui._ask(None, INFO)
    assert captured["text"] == i18n.tr("update_available", version=INFO.version,
                                       size=INFO.size // (1024 * 1024))
```

```python
# labeling_tool/tests/test_sam2_weights_dialog.py 追加
def test_prompt_follows_language(monkeypatch, ckpt, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("zh")
    asked = {}
    monkeypatch.setattr(QMessageBox, "question",
                        lambda parent, title, text, *a, **k: asked.setdefault("t", text)
                        or QMessageBox.No)
    dlg.ensure_sam2_weights()
    assert asked["t"] == i18n.tr("weights_confirm",
                                 size=weights.SAM2_WEIGHTS_SIZE // (1024 * 1024),
                                 path=ckpt)
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** —— 逐文件把字面量替换为 `tr()`，并在 `strings_*.py` 对应分区补 key：
  - `fetch_dialog.py`：窗口标题、`sessionId` 标签（标识符不翻译，但标签文字翻译）、范围输入、按钮（`가져오기 (다운로드)` / `← 로그인`）、进度文案 `fetch_progress`、各类失败提示。
  - `sam2_weights_dialog.py`：确认框、进度、失败提示。
  - `update/ui.py`：更新提示（`update_available`、full 版 1.5 GB 警告、三个按钮）、进度、失败、"已是最新"、开发版提示、"检查中"。
  - `app.py`：few-shot 加载中提示与失败弹窗。
  - 打开 `FetchDialog` 前后语言变化时也要正确：这些是短生命周期对话框，构造时取值即可，不必连信号（在报告中说明）。
  - 四个文件加入 `UI_MODULES`。
- [ ] **Step 4: 全部测试 PASS**
- [ ] **Step 5: 提交**（subject: `feat(i18n): translate fetch, weights, update and startup dialogs`）

---

### Task 5: 生产主窗口（与登录界面同步）

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`、`labeling_tool/core/window/ui_builder.py`、`strings_*.py`（按术语表修正）、`tests/test_i18n_coverage.py`（加入 `main_window.py`）
- Test: `labeling_tool/tests/test_mainwindow_hooks.py` 或新建 `labeling_tool/tests/test_main_window_i18n.py`

**Interfaces:**
- Consumes: `tr`、`language_manager`
- Produces: `MainWindow.tr_` 保留（转发 `tr`），下拉框改为写 `i18n.set_language`

- [ ] **Step 1: 写失败测试**

```python
"""The main window and the login screen share one language setting."""
def test_main_window_combo_writes_the_shared_setting(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    win = _make_window()                      # existing helper / minimal构造
    idx = list(i18n.LANGUAGES).index("en")
    win._cmb_lang.setCurrentIndex(idx)
    assert i18n.current_language() == "en"
    assert win._btn_save.text() == i18n.tr("btn_save")


def test_main_window_follows_external_language_change(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    win = _make_window()
    i18n.set_language("zh")                   # e.g. changed on the login screen
    assert win._btn_save.text() == i18n.tr("btn_save")
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
  - `tr_` 改为 `return tr(key, **kwargs)`；删除实例变量 `self.lang` 的写入逻辑，`_change_language` 改为 `i18n.set_language(LANGUAGES[idx])`。
  - 构造时把下拉框项改为按 `LANGUAGES` 顺序（ko 在前），当前项取 `current_language()`。
  - 连接 `language_manager().languageChanged` → `self._retranslate_ui()`。
  - `strings_*.py` 中主窗口既有 key 的韩文按术语表修正（`균열` / `박리` / `축척` / `보수 구역`）。
- [ ] **Step 4: 全部测试 PASS**（主窗口既有测试不得修改语义）
- [ ] **Step 5: 提交**（subject: `feat(i18n): main window shares the app-wide language setting`）

---

### Task 6: few-shot 工具 + 文档

**Files:**
- Modify: `annotation_tool/ui/main_window.py`、`strings_*.py`、`tests/test_i18n_coverage.py`（加入 annotation_tool 界面文件）、`README.md`、`docs/README.md`
- Test: `annotation_tool/tests/test_smoke_ui.py`（追加一条：面板文字随语言变化）

- [ ] **Step 1: 写失败测试**

```python
# annotation_tool/tests/test_smoke_ui.py 追加
def test_panel_text_follows_language(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("en")
    w = _make_window(monkeypatch, tmp_path)
    assert w.btn_save.text() == i18n.tr("fs_save")
    i18n.set_language("ko")
    assert w.btn_save.text() == i18n.tr("fs_save")
    w.close()
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
  - `annotation_tool/ui/main_window.py` 的中文文案接入 `tr()`（key 前缀 `fs_`）：工具按钮（SAM 点/框、画笔、橡皮擦）、笔刷、确认/保存、类别管理按钮（添加 / 重命名 / 优先级）、导出优先级说明、各类状态栏与弹窗提示。
  - **类别名不翻译**（joint 等按 `classes.json` 原样显示）。
  - 连接 `languageChanged` → 重建类别面板与按钮文字。
  - README 增加"언어 설정"一节（韩文）：登录界面或主窗口右上角切换，选择会被记住；`docs/README.md` 索引追加本设计与术语表。
- [ ] **Step 4:** 全部测试 PASS；`QT_QPA_PLATFORM=offscreen timeout 8 .venv/bin/python -m labeling_tool.app; [ $? = 124 ] && echo started-ok`
- [ ] **Step 5: 提交**（subject: `feat(i18n): translate the few-shot tool; document language settings`）

---

### Task 7: 收尾

- [ ] **Step 1:** 全部测试 PASS，且 `tests/test_i18n_coverage.py::UI_MODULES` 已包含全部 9 个界面文件
- [ ] **Step 2:** 人工核对三语截图（登录三个标签页、获取数据、主窗口、few-shot 面板、更新提示），确认无串语言、无截断
- [ ] **Step 3:** 控制者 push 分支并开 PR；CI 通过后由用户合并
- [ ] **Step 4:** 用户在 Windows 上确认：首次启动为韩语；切到中文后重启仍是中文；exe 中 `ui-settings.json` 生成在 exe 同目录
