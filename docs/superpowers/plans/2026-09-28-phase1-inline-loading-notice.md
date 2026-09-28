# 第一期：加载提示内嵌 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 few-shot 模型加载时弹出的白底浅灰字浮窗，改为在登录窗口内部显示加载状态，加载失败时就地显示错误而不弹框。

**Architecture:** `LoginDialog` 增加一块默认隐藏的加载区（消息 + 不定量进度条 + 说明文字）和 `enter_loading_state()` / `exit_loading_state()` 两个方法。few-shot 按钮不再直接 `accept()`，而是发出 `fewshotRequested` 信号；`app.py` 连接该信号并编排时序：进入加载态 → 加载模型 → 成功则 `accept()`，失败则退出加载态并就地显示错误。用信号而非直接调用，是因为 `login_dialog` 直接 import `app` 会造成循环依赖。

**Tech Stack:** Python 3.12、PyQt5、pytest（offscreen Qt）

**Spec:** `docs/superpowers/specs/2026-09-28-ui-refresh-and-rebrand-design.md`

## Global Constraints

- 用户可见文案一律走 i18n，先改 `docs/i18n-glossary.md` 再改 `labeling_tool/core/i18n/strings_{ko,zh,en}.py`。三份文件的键必须完全一致。
- 代码注释用英文；日志与异常文本保持英文。
- 既有术语沿用，不得另起译法：균열 / 박리 / 축척 / 보수 구역 / 마스크 / 라벨링。
- 技术标识符永不翻译：`sessionId`、`BASE URL`、`X-Viewer-Api-Key`、`SHA256`、文件路径、`lite`/`full`、few-shot 类名。
- 测试命令固定为 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`，基线 388 通过，全程保持绿。
- offscreen Qt 下模态 `QMessageBox` 会挂起整个测试进程，失败路径一律走内嵌显示，不得新增弹框。
- 提交信息用 conventional commits，结尾附 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 与 `Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq` 两行真实 trailer。

## Review Focus

- **加载过程中用户点窗口关闭按钮** — 模型加载阻塞主线程，此时点 X 不会有反应；加载态下应显式禁用关闭（`setWindowCloseButtonHint` 或忽略 `closeEvent`），否则用户会以为程序卡死。测试归 Task 3。
- **加载失败后再次点击 few-shot 按钮** — 退出加载态后按钮必须重新可用，能再试一次，且第二次失败的错误文本会替换第一次的而不是叠加。测试归 Task 3。
- **`ensure_sam2_weights()` 被用户取消** — 权重下载对话框取消后返回 `None`，此时不是错误，登录窗应干净地退出加载态且不显示任何错误文本。测试归 Task 3。
- **加载态下点"업데이트 확인"** — 更新检查按钮在加载态必须禁用，否则 `force=True` 的检查会在加载区上叠一个模态框。测试归 Task 2。
- **加载态下切换语言** — 语言下拉在加载态必须禁用；若允许切换，`retranslate()` 会重写加载区文本，把正在显示的进度说明覆盖掉。测试归 Task 2。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `docs/i18n-glossary.md` | 三语术语权威 | 修改：新增加载态三条术语 |
| `labeling_tool/core/i18n/strings_{ko,zh,en}.py` | 三语文案 | 修改：新增 3 个键 |
| `labeling_tool/ui/login_dialog.py` | 登录窗，新增加载区与加载态 API | 修改 |
| `labeling_tool/app.py` | 编排 few-shot 加载时序，删除浮窗 | 修改 |
| `labeling_tool/tests/test_login_loading_state.py` | 加载态行为测试 | 新建 |
| `labeling_tool/tests/test_login_modes.py` | few-shot 按钮行为变更 | 修改 |

---

### Task 1: i18n 文案

**Files:**
- Modify: `docs/i18n-glossary.md`
- Modify: `labeling_tool/core/i18n/strings_ko.py`
- Modify: `labeling_tool/core/i18n/strings_zh.py`
- Modify: `labeling_tool/core/i18n/strings_en.py`
- Test: `tests/test_i18n_coverage.py`（已有，无需新增用例）

**Interfaces:**
- Consumes: 无
- Produces: 三个翻译键 `login_loading_detail`、`login_loading_failed`、`login_loading_cancelled`，供 Task 2、Task 3 使用。既有键 `app_fewshot_loading` 继续作为加载区主消息复用。

- [ ] **Step 1: 在 glossary 中登记新术语**

在 `docs/i18n-glossary.md` 的表格中追加三行（保持既有列格式）：

| 键 | 한국어 | 中文 | English |
|---|---|---|---|
| `login_loading_detail` | SAM2.1 가중치를 메모리에 올리는 중입니다. 잠시 기다려 주세요. | 正在将 SAM2.1 权重载入内存，请稍候。 | Loading the SAM2.1 weights into memory. This may take a moment. |
| `login_loading_failed` | Few-shot 도구를 열 수 없습니다: {type}: {exc} | 无法打开 Few-shot 工具：{type}：{exc} | Could not open the few-shot tool: {type}: {exc} |
| `login_loading_cancelled` | 모델 로딩이 취소되었습니다. | 已取消模型加载。 | Model loading was cancelled. |

- [ ] **Step 2: 写入三份 strings 文件**

在每份文件的 `# --- login screen ---` 区块末尾追加对应条目。`strings_ko.py`：

```python
    "login_loading_detail":            "SAM2.1 가중치를 메모리에 올리는 중입니다. 잠시 기다려 주세요.",
    "login_loading_failed":            "Few-shot 도구를 열 수 없습니다: {type}: {exc}",
    "login_loading_cancelled":         "모델 로딩이 취소되었습니다.",
```

`strings_zh.py`：

```python
    "login_loading_detail":            "正在将 SAM2.1 权重载入内存，请稍候。",
    "login_loading_failed":            "无法打开 Few-shot 工具：{type}：{exc}",
    "login_loading_cancelled":         "已取消模型加载。",
```

`strings_en.py`：

```python
    "login_loading_detail":            "Loading the SAM2.1 weights into memory. This may take a moment.",
    "login_loading_failed":            "Could not open the few-shot tool: {type}: {exc}",
    "login_loading_cancelled":         "Model loading was cancelled.",
```

- [ ] **Step 3: 运行 i18n 守卫测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_i18n_coverage.py -q -p no:cacheprovider`
Expected: PASS（键平价与占位符一致性通过；`{type}` / `{exc}` 三语一致）

- [ ] **Step 4: 提交**

```bash
git add docs/i18n-glossary.md labeling_tool/core/i18n/strings_ko.py \
        labeling_tool/core/i18n/strings_zh.py labeling_tool/core/i18n/strings_en.py
git commit -m "$(cat <<'EOF'
i18n: add the login dialog's inline loading strings

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 2: LoginDialog 的加载态

**Files:**
- Modify: `labeling_tool/ui/login_dialog.py`
- Test: `labeling_tool/tests/test_login_loading_state.py`（新建）

**Interfaces:**
- Consumes: Task 1 的翻译键
- Produces:
  - `LoginDialog.fewshotRequested` — `pyqtSignal()`，few-shot 按钮点击时发出
  - `LoginDialog.enter_loading_state(message: str, detail: str = "") -> None`
  - `LoginDialog.exit_loading_state(error: str | None = None) -> None`
  - `LoginDialog._loading_box` — `QFrame`，`objectName` 为 `loadingBox`，默认 `isVisible()` 为 False
  - `LoginDialog._lbl_loading` / `_lbl_loading_detail` — `QLabel`
  - `LoginDialog._loading_bar` — `QProgressBar`，`range(0, 0)` 即不定量模式

- [ ] **Step 1: 写失败的测试**

新建 `labeling_tool/tests/test_login_loading_state.py`：

```python
"""The login dialog's inline loading state, used while the few-shot model
loads. Replaces the old free-floating QLabel splash in app.py."""

import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool.ui import login_dialog as ld

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_real_config(monkeypatch, tmp_path):
    monkeypatch.setattr(ld, "load_config", lambda: {"apiKey": "saved-key"})
    monkeypatch.setattr(ld, "save_config", lambda base, key: None)
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path)


@pytest.fixture
def dlg(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: True)
    d = ld.LoginDialog()
    yield d
    d.close()


def test_loading_box_hidden_initially(dlg):
    assert not dlg._loading_box.isVisibleTo(dlg)


def test_enter_loading_state_shows_box_and_texts(dlg):
    dlg.enter_loading_state("로딩 중…", "가중치를 올리는 중")
    assert dlg._loading_box.isVisibleTo(dlg)
    assert dlg._lbl_loading.text() == "로딩 중…"
    assert dlg._lbl_loading_detail.text() == "가중치를 올리는 중"


def test_progress_bar_is_indeterminate(dlg):
    dlg.enter_loading_state("로딩 중…")
    assert dlg._loading_bar.minimum() == 0
    assert dlg._loading_bar.maximum() == 0


def test_enter_loading_state_disables_interaction(dlg):
    dlg.enter_loading_state("로딩 중…")
    assert not dlg.tabs.isEnabled()
    assert not dlg.cmb_language.isEnabled()
    assert not dlg.btn_check_update.isEnabled()


def test_exit_loading_state_restores_interaction(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state()
    assert dlg.tabs.isEnabled()
    assert dlg.cmb_language.isEnabled()
    assert dlg.btn_check_update.isEnabled()
    assert not dlg._loading_box.isVisibleTo(dlg)


def test_exit_loading_state_with_error_keeps_box_and_hides_bar(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state("열 수 없습니다: RuntimeError: boom")
    assert dlg._loading_box.isVisibleTo(dlg)
    assert "RuntimeError: boom" in dlg._lbl_loading.text()
    assert not dlg._loading_bar.isVisibleTo(dlg)
    assert dlg.tabs.isEnabled()


def test_fewshot_button_emits_signal_instead_of_accepting(dlg):
    seen = []
    dlg.fewshotRequested.connect(lambda: seen.append(True))
    dlg.btn_fewshot.click()
    assert seen == [True]
    assert dlg.result() == 0  # not accepted yet
```

- [ ] **Step 2: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_login_loading_state.py -q -p no:cacheprovider`
Expected: FAIL，报 `AttributeError: 'LoginDialog' object has no attribute '_loading_box'`

- [ ] **Step 3: 加入加载区控件**

在 `login_dialog.py` 顶部导入中补上 `QFrame`、`pyqtSignal`：

```python
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QComboBox, QFrame,
    QApplication,
)
```

在 `class LoginDialog(QDialog):` 的类体开头声明信号：

```python
class LoginDialog(QDialog):
    # Emitted when the user picks the few-shot tool. app.py connects this and
    # drives the loading state; the dialog cannot import app.py itself
    # (circular import), so the ordering lives on the app side.
    fewshotRequested = pyqtSignal()
```

在 `__init__` 中 `root.addWidget(self.tabs)` 之后、bottom row 之前插入加载区：

```python
        # Inline loading area, shown while the few-shot model loads. Hidden
        # until enter_loading_state() is called. This replaces the old
        # free-floating QLabel splash, which rendered as grey-on-white
        # because a parentless QLabel picks up the theme's color rule but
        # not its background.
        self._loading_box = QFrame()
        self._loading_box.setObjectName("loadingBox")
        loading_lay = QVBoxLayout(self._loading_box)
        loading_lay.setContentsMargins(16, 14, 16, 14)
        loading_lay.setSpacing(10)
        self._lbl_loading = QLabel("")
        self._lbl_loading.setWordWrap(True)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)   # indeterminate
        self._loading_bar.setTextVisible(False)
        self._lbl_loading_detail = QLabel("")
        self._lbl_loading_detail.setWordWrap(True)
        self._lbl_loading_detail.setObjectName("loadingDetail")
        loading_lay.addWidget(self._lbl_loading)
        loading_lay.addWidget(self._loading_bar)
        loading_lay.addWidget(self._lbl_loading_detail)
        self._loading_box.setVisible(False)
        root.addWidget(self._loading_box)
```

- [ ] **Step 4: 实现两个状态方法**

在 `_accept_mode` 之前加入：

```python
    def enter_loading_state(self, message: str, detail: str = "") -> None:
        """Show the inline loading area and lock the dialog down.

        The model load blocks the UI thread, so everything that would open a
        second modal (update check) or rewrite the loading text (language
        switch) is disabled for the duration."""
        self._lbl_loading.setText(message)
        self._lbl_loading.setStyleSheet("")
        self._lbl_loading_detail.setText(detail)
        self._lbl_loading_detail.setVisible(bool(detail))
        self._loading_bar.setVisible(True)
        self._loading_box.setVisible(True)
        self.tabs.setEnabled(False)
        self.cmb_language.setEnabled(False)
        self.btn_check_update.setEnabled(False)
        self._loading = True
        QApplication.processEvents()

    def exit_loading_state(self, error: str | None = None) -> None:
        """Unlock the dialog. With `error`, keep the area visible and show
        the message there instead of in a QMessageBox -- a modal box under
        offscreen Qt hangs the test suite, and an inline error lets the user
        pick another tab without restarting."""
        self.tabs.setEnabled(True)
        self.cmb_language.setEnabled(True)
        self.btn_check_update.setEnabled(True)
        self._loading = False
        self._loading_bar.setVisible(False)
        if error:
            self._lbl_loading.setText(error)
            self._lbl_loading.setStyleSheet("color: #e06c6c;")
            self._lbl_loading_detail.setVisible(False)
            self._loading_box.setVisible(True)
        else:
            self._loading_box.setVisible(False)
```

在 `__init__` 中 `self._build_info = read_build_info()` 附近初始化 `self._loading = False`。


- [ ] **Step 5: few-shot 按钮改为发信号**

把 `_build_fewshot_page` 中的连接改掉：

```python
        self.btn_fewshot.clicked.connect(self.fewshotRequested.emit)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_login_loading_state.py -q -p no:cacheprovider`
Expected: PASS，7 passed

- [ ] **Step 7: 提交**

```bash
git add labeling_tool/ui/login_dialog.py labeling_tool/tests/test_login_loading_state.py
git commit -m "$(cat <<'EOF'
feat(ui): add an inline loading state to the login dialog

The few-shot button now emits fewshotRequested instead of accepting
right away, so app.py can drive the load with the dialog still open.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 3: app.py 时序改造与浮窗删除

**Files:**
- Modify: `labeling_tool/app.py:34-62`（`_open_fewshot_window`）与 `main()` 的 few-shot 分支
- Modify: `labeling_tool/tests/test_login_modes.py:208-213`
- Test: `labeling_tool/tests/test_login_loading_state.py`（追加用例）

**Interfaces:**
- Consumes: Task 2 的 `fewshotRequested` / `enter_loading_state` / `exit_loading_state`；Task 1 的翻译键
- Produces: `labeling_tool.app.load_fewshot_window() -> tuple[object | None, str | None]` — 返回 `(窗口, 错误文本)`。两者都为 `None` 表示用户取消了权重下载，不是错误。

- [ ] **Step 1: 写失败的测试**

在 `labeling_tool/tests/test_login_loading_state.py` 末尾追加：

```python
def test_close_is_ignored_while_loading(dlg):
    dlg.show()
    dlg.enter_loading_state("로딩 중…")
    dlg.close()
    assert dlg.isVisible()          # the close was ignored
    dlg.exit_loading_state()
    dlg.close()
    assert not dlg.isVisible()      # and honoured once loading ended


def test_retry_after_failure_replaces_error_text(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state("첫 번째 실패")
    assert "첫 번째 실패" in dlg._lbl_loading.text()
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state("두 번째 실패")
    assert dlg._lbl_loading.text() == "두 번째 실패"
    assert "첫 번째 실패" not in dlg._lbl_loading.text()


def test_cancelled_weights_download_leaves_no_error(dlg):
    dlg.enter_loading_state("로딩 중…")
    dlg.exit_loading_state(None)
    assert not dlg._loading_box.isVisibleTo(dlg)
    assert dlg.tabs.isEnabled()
```

新建 `labeling_tool/tests/test_app_fewshot_flow.py`：

```python
"""app.py's few-shot flow: the model loads with the login dialog still
open, and failures come back as text rather than a modal box."""

import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool import app as app_module

_app = QApplication.instance() or QApplication([])


def test_load_fewshot_window_returns_error_text_on_failure(monkeypatch):
    def _boom():
        raise RuntimeError("no CUDA")

    monkeypatch.setattr(app_module, "_build_fewshot_main_window", _boom)
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: True)
    win, err = app_module.load_fewshot_window()
    assert win is None
    assert "RuntimeError" in err
    assert "no CUDA" in err


def test_load_fewshot_window_returns_none_none_when_weights_cancelled(monkeypatch):
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: False)
    win, err = app_module.load_fewshot_window()
    assert win is None
    assert err is None


def test_load_fewshot_window_returns_window_on_success(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(app_module, "_ensure_weights", lambda: True)
    monkeypatch.setattr(app_module, "_build_fewshot_main_window", lambda: sentinel)
    win, err = app_module.load_fewshot_window()
    assert win is sentinel
    assert err is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_app_fewshot_flow.py -q -p no:cacheprovider`
Expected: FAIL，报 `AttributeError: module 'labeling_tool.app' has no attribute 'load_fewshot_window'`

- [ ] **Step 3: 重写 app.py 的加载函数**

把 `labeling_tool/app.py` 中整个 `_open_fewshot_window()` 替换为三个函数。删除 `notice = QLabel(...)` 那段浮窗代码，以及不再需要的 `QLabel` 导入（若该文件其他地方未使用）：

```python
def _ensure_weights() -> bool:
    """True when the SAM2.1 weights are present (or not needed).

    Split out so tests can stub it without reaching into the weights
    dialog."""
    from annotation_tool import configs as fewshot_configs
    if fewshot_configs.BACKEND != "sam2":
        return True
    from labeling_tool.ui.sam2_weights_dialog import ensure_sam2_weights
    return ensure_sam2_weights()


def _build_fewshot_main_window():
    """Import the few-shot tool and build its window.

    Imported lazily: pulls in torch, which production PCs may not have."""
    from annotation_tool.ui import main_window as fewshot_main_window
    return fewshot_main_window.MainWindow()


def load_fewshot_window() -> tuple[object | None, str | None]:
    """Load the few-shot tool.

    Returns (window, None) on success, (None, message) on failure, and
    (None, None) when the user declined the weights download -- a decline
    is not an error, so the caller just returns to a normal login screen."""
    if not _ensure_weights():
        return None, None
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        return _build_fewshot_main_window(), None
    except Exception as exc:  # noqa: BLE001 - any load failure is reported
        vlog().exception("few-shot tool failed to open")
        return None, tr("login_loading_failed",
                        type=type(exc).__name__, exc=exc)
    finally:
        QApplication.restoreOverrideCursor()
```

删除现在无人调用的 `open_tool_window()`，以及 `app_fewshot_error_title` / `app_fewshot_error_msg` 两个键的使用点（键本身保留在 strings 文件中，供后续版本复用）。

- [ ] **Step 4: 改写 main() 的 few-shot 分支**

把 `main()` 中的登录循环改为连接信号。原先的

```python
        if login.mode == MODE_FEWSHOT:
            tool_win = open_tool_window(login.mode)
            if tool_win is None:
                continue
```

改为在 `login = LoginDialog()` 之后、`login.exec_()` 之前接上信号：

```python
    while True:
        login = LoginDialog()
        holder = {}

        def _on_fewshot(dlg=login, holder=holder):
            dlg.enter_loading_state(tr("app_fewshot_loading"),
                                    tr("login_loading_detail"))
            win, err = load_fewshot_window()
            if win is None:
                # err is None when the user declined the weights download:
                # drop back to a clean login screen with nothing to report.
                dlg.exit_loading_state(err)
                return
            holder["win"] = win
            dlg.mode = MODE_FEWSHOT
            dlg.accept()

        login.fewshotRequested.connect(_on_fewshot)

        if not login.exec_():
            wait_for_checks()
            return 0  # user cancelled

        if login.mode == MODE_FEWSHOT:
            tool_win = holder["win"]
            tool_win.show()
            code = app.exec_()
            wait_for_checks()
            return code
```

- [ ] **Step 5: 加载态下禁止关闭窗口**

在 `login_dialog.py` 的 `LoginDialog` 中加入：

```python
    def closeEvent(self, event) -> None:
        """The model load blocks the UI thread, so a close during loading
        cannot be honoured anyway -- ignore it rather than let the window
        look frozen."""
        if getattr(self, "_loading", False):
            event.ignore()
            return
        super().closeEvent(event)
```

- [ ] **Step 6: 更新既有的 few-shot 按钮测试**

`labeling_tool/tests/test_login_modes.py` 中 `test_fewshot_tab_enabled_when_torch_installed` 的断言已不成立（按钮不再直接设置 `mode`）。改为：

```python
def test_fewshot_tab_enabled_when_torch_installed(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: True)
    dlg = ld.LoginDialog()
    assert dlg.btn_fewshot.isEnabled()
    seen = []
    dlg.fewshotRequested.connect(lambda: seen.append(True))
    dlg.btn_fewshot.click()
    # app.py drives the load and only then accepts; the click itself just
    # asks for it.
    assert seen == [True]
```

- [ ] **Step 7: 运行相关测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_app_fewshot_flow.py labeling_tool/tests/test_login_loading_state.py labeling_tool/tests/test_login_modes.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add labeling_tool/app.py labeling_tool/ui/login_dialog.py \
        labeling_tool/tests/test_app_fewshot_flow.py \
        labeling_tool/tests/test_login_loading_state.py \
        labeling_tool/tests/test_login_modes.py
git commit -m "$(cat <<'EOF'
fix(ui): load the few-shot model inside the login dialog

Drops the parentless QLabel splash, which rendered grey-on-white because
it picked up the dark theme's color rule but not its background. Failures
now show inline, so the user can pick another tab without restarting.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 4: 加载区配色与收尾

**Files:**
- Modify: `labeling_tool/core/window/styles.py`
- Test: 全量测试套件

**Interfaces:**
- Consumes: Task 2 的 `objectName`：`loadingBox`、`loadingDetail`
- Produces: 无（本期最后一个任务）

- [ ] **Step 1: 给加载区加样式**

在 `labeling_tool/core/window/styles.py` 的 `STYLESHEET` 中，`QLabel#hintText` 规则之后追加：

```css
        QFrame#loadingBox {
            background-color: #181b20;
            border: 1px solid #2c313a;
            border-radius: 6px;
        }
        QLabel#loadingDetail {
            color: #9ea3aa;
            font-size: 11px;
        }
        QProgressBar {
            background-color: #2d333d;
            border: none;
            border-radius: 2px;
            max-height: 4px;
        }
        QProgressBar::chunk {
            background-color: #2d6cdf;
            border-radius: 2px;
        }
```

- [ ] **Step 2: 确认没有遗留的浮窗代码**

Run: `grep -n "SplashScreen\|WindowStaysOnTopHint" labeling_tool/`
Expected: 无输出（浮窗已彻底移除）

- [ ] **Step 3: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，401 passed（基线 388 + 本期新增 13）

- [ ] **Step 4: 冒烟验证应用仍能启动**

Run: `QT_QPA_PLATFORM=offscreen timeout 8 .venv/bin/python -m labeling_tool.app; [ $? = 124 ] && echo started-ok`
Expected: 输出 `started-ok`（阻塞在登录框即为成功）

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/window/styles.py
git commit -m "$(cat <<'EOF'
style(ui): theme the login dialog's inline loading area

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

## 完成标准

- 全量测试 401 通过
- `grep -n "SplashScreen" labeling_tool/` 无输出
- 应用能启动并停在登录框
- 点击 Few-shot 标签页的按钮后，登录窗内出现加载区而非独立小窗；加载失败时错误就地显示，窗口仍可切换标签页

本期完成后发布 v1.2.1，自动更新链路不受影响，可用于验证 v1.2.0 → v1.2.1 的更新流程。
