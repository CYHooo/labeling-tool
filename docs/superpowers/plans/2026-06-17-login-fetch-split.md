# 登录页 + 数据拉取页拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把单一 `ConnectDialog` 拆成"前置登录页(URL/KEY)+ 数据拉取页(sessionId 下拉)"两段式启动流程。

**Architecture:** 新增 `LoginDialog`(登录 + 离线扫描下拉)与 `FetchDialog`(在线拉取 + sessionId 下拉),共用辅助移入 `ui/dialog_helpers.py`,删除旧 `connect_dialog.py`;`app.py` 编排两者;`client.py` 新增隔离的 `list_sessions()`;`workspace.py` 新增本地会话扫描函数。

**Tech Stack:** Python 3.10+、PyQt5、requests;测试用 pytest + responses。

## Global Constraints

- Python 3.10+,允许 `X | None` 类型注解。
- 不新增运行时依赖(仅用 PyQt5/requests/已有库)。
- 所有 V-API 调用走 `ViewerApiClient._s`(带 `X-Viewer-Api-Key` 头)+ `_raise_for_error` + `vlog()` 计时日志。
- 登录页**不联网验证**,仅把 URL/KEY 存入 `config.json`。
- GUI 对话框本身不写单测(沿用现状);可测逻辑抽成纯函数单独测。
- 假定的获取 ID 接口契约:`GET {base}/api/viewer/sessions/`,响应 `{"sessions":[{"sessionId":18,"createdAt":...,"photoCount":42}, ...]}`,需兼容裸数组 `{"sessions":[18,19]}`。

---

### Task 1: `ViewerApiClient.list_sessions()`(获取会话列表,容错解析)

**Files:**
- Modify: `labeling_tool/api/client.py`(在 `register_annotations` 之后追加方法)
- Test: `labeling_tool/tests/test_list_sessions.py`(新建)

**Interfaces:**
- Consumes: 现有 `ViewerApiClient.__init__(base_url, api_key)`、`self._s`、`self._raise_for_error`、`self.timeout`。
- Produces: `list_sessions(self) -> list[dict]` —— 返回归一化后的列表,每项至少含 `"sessionId": int`,其余字段(如 `createdAt`、`photoCount`)原样透传(存在才有)。

- [ ] **Step 1: Write the failing tests**

新建 `labeling_tool/tests/test_list_sessions.py`:

```python
import responses
from labeling_tool.api.client import ViewerApiClient

BASE = "https://api.example.com"
KEY = "test-key"


def _client():
    return ViewerApiClient(base_url=BASE, api_key=KEY)


@responses.activate
def test_list_sessions_object_array():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [
            {"sessionId": 18, "createdAt": "2026-06-01", "photoCount": 42},
            {"sessionId": 19},
        ]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [18, 19]
    assert out[0]["photoCount"] == 42
    # 凭证头随请求发出
    assert responses.calls[0].request.headers["X-Viewer-Api-Key"] == KEY


@responses.activate
def test_list_sessions_bare_array():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [18, 19, 20]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [18, 19, 20]


@responses.activate
def test_list_sessions_skips_items_without_id():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [{"createdAt": "x"}, {"sessionId": 7}]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [7]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_list_sessions.py -v`
Expected: FAIL —— `AttributeError: 'ViewerApiClient' object has no attribute 'list_sessions'`

- [ ] **Step 3: Implement `list_sessions()`**

在 `labeling_tool/api/client.py` 末尾(`register_annotations` 方法之后,类内)追加:

```python
    # ---- session list (endpoint PENDING: assumed contract) --------
    def list_sessions(self) -> list[dict]:
        """List available session ids for the session dropdown.

        Endpoint is not live yet; assumed contract is
        ``GET {base}/api/viewer/sessions/`` returning
        ``{"sessions": [{"sessionId": int, ...}, ...]}``. A bare-int array
        ``{"sessions": [18, 19]}`` is also accepted. Each returned dict is
        normalized to carry an int ``sessionId``; other fields pass through.
        When the real endpoint lands, only this method should need changes.
        """
        url = f"{self.base_url}/api/viewer/sessions/"
        t = time.perf_counter()
        resp = self._s.get(url, timeout=self.timeout)
        self._raise_for_error(resp)
        data = resp.json()
        raw = data.get("sessions", []) if isinstance(data, dict) else data
        out: list[dict] = []
        for item in raw or []:
            if isinstance(item, dict):
                if "sessionId" in item:
                    out.append({**item, "sessionId": int(item["sessionId"])})
            else:
                out.append({"sessionId": int(item)})
        vlog().info("list_sessions -> %d (%.0f ms)",
                    len(out), (time.perf_counter() - t) * 1000)
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_list_sessions.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/api/client.py labeling_tool/tests/test_list_sessions.py
git commit -m "feat(api): add list_sessions() with tolerant parsing (endpoint pending)"
```

---

### Task 2: 本地会话扫描 `list_local_session_ids()`

**Files:**
- Modify: `labeling_tool/session/workspace.py`(模块级追加函数)
- Test: `labeling_tool/tests/test_workspace.py`(追加用例)

**Interfaces:**
- Consumes: 现有 `DEFAULT_DATA_ROOT`、`pathlib.Path`。
- Produces: `list_local_session_ids(root: Path = DEFAULT_DATA_ROOT) -> list[int]` —— 扫描 `root/session_<N>` 中含 `manifest.json` 的目录,返回升序排列的整型 id 列表;`root` 不存在返回 `[]`。

- [ ] **Step 1: Write the failing test**

在 `labeling_tool/tests/test_workspace.py` 末尾追加(顶部确保 `from labeling_tool.session.workspace import list_local_session_ids` 可用;如该文件还没 import,加上):

```python
from labeling_tool.session.workspace import list_local_session_ids


def test_list_local_session_ids(tmp_path):
    (tmp_path / "session_1").mkdir()
    (tmp_path / "session_1" / "manifest.json").write_text("{}")
    (tmp_path / "session_10").mkdir()
    (tmp_path / "session_10" / "manifest.json").write_text("{}")
    # 缺 manifest -> 跳过
    (tmp_path / "session_2").mkdir()
    # 非数字后缀 -> 跳过
    (tmp_path / "session_x").mkdir()
    (tmp_path / "session_x" / "manifest.json").write_text("{}")
    # 同名文件(非目录) -> 跳过
    (tmp_path / "session_3").write_text("not a dir")

    assert list_local_session_ids(tmp_path) == [1, 10]


def test_list_local_session_ids_missing_root(tmp_path):
    assert list_local_session_ids(tmp_path / "nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_workspace.py -k list_local -v`
Expected: FAIL —— `ImportError: cannot import name 'list_local_session_ids'`

- [ ] **Step 3: Implement the function**

在 `labeling_tool/session/workspace.py` 末尾(`Workspace` 类之后,模块级)追加:

```python
def list_local_session_ids(root: Path = DEFAULT_DATA_ROOT) -> list[int]:
    """Session ids already downloaded under ``root`` (have a manifest.json).

    Used by the offline open dropdown. Returns ascending int ids; a missing
    root yields an empty list.
    """
    if not root.exists():
        return []
    ids: list[int] = []
    for d in root.glob("session_*"):
        if not d.is_dir() or not (d / "manifest.json").exists():
            continue
        suffix = d.name[len("session_"):]
        if suffix.isdigit():
            ids.append(int(suffix))
    return sorted(ids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_workspace.py -k list_local -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/session/workspace.py labeling_tool/tests/test_workspace.py
git commit -m "feat(session): scan locally-downloaded session ids for offline dropdown"
```

---

### Task 3: 共用辅助 `ui/dialog_helpers.py`

**Files:**
- Create: `labeling_tool/ui/dialog_helpers.py`

**Interfaces:**
- Consumes: 现有 `rebuild_cache.prebuild_rebuilt`、`session.workspace.Workspace`。
- Produces:
  - `CONFIG_PATH: Path`
  - `load_config() -> dict`
  - `save_config(base: str, api_key: str) -> None`
  - `run_prebuild(ws, timestamps: list[int], progress, status_label) -> None` —— 带可见进度条地预构 Rebuilt/;`timestamps` 为空直接返回。`progress`/`status_label` 是 Qt 控件(`QProgressBar`/`QLabel`)。

这是从旧 `connect_dialog.py` 平移过来的共用逻辑,两个对话框都要用,抽出避免重复。无独立单测(GUI/IO 粘合层,沿用现状)。

- [ ] **Step 1: Create the file**

新建 `labeling_tool/ui/dialog_helpers.py`:

```python
"""Shared helpers for the login + fetch dialogs: config persistence and the
Rebuilt/ prebuild progress loop (lifted from the old ConnectDialog)."""

from __future__ import annotations

import json
from pathlib import Path

from labeling_tool.rebuild_cache import prebuild_rebuilt

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(base: str, api_key: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"base": base, "apiKey": api_key}, indent=2),
        encoding="utf-8")


def run_prebuild(ws, timestamps, progress, status_label) -> None:
    """Pre-compute the Rebuilt/ cache for every photo with a visible progress
    bar, so the labeling window opens instantly instead of freezing while it
    rebuilds the first image on the UI thread."""
    if not timestamps:
        return
    from PyQt5.QtWidgets import QApplication
    progress.setVisible(True)
    progress.setRange(0, len(timestamps))
    progress.setValue(0)

    def _prog(done, total):
        progress.setValue(done)
        status_label.setText(f"재구성(rebuild) {done}/{total}")
        QApplication.processEvents()

    prebuild_rebuilt(ws.origin_dir, ws.detected_dir, ws.rebuilt_dir,
                     timestamps, progress=_prog)
```

- [ ] **Step 2: Sanity import**

Run: `.venv/bin/python -c "from labeling_tool.ui.dialog_helpers import load_config, save_config, run_prebuild; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 3: Commit**

```bash
git add labeling_tool/ui/dialog_helpers.py
git commit -m "refactor(ui): extract config + prebuild helpers shared by dialogs"
```

---

### Task 4: `LoginDialog`(前置登录页)

**Files:**
- Create: `labeling_tool/ui/login_dialog.py`

**Interfaces:**
- Consumes: `dialog_helpers.load_config/save_config/run_prebuild`、`session.workspace.{Workspace, list_local_session_ids}`、`session.manifest.Manifest`、`logging_setup.{attach_session_log, vlog}`。
- Produces: `LoginDialog(QDialog)`,`exec_()` 返回 `Accepted`(>0)时,调用方据以下属性分流:
  - 离线分支:`self.workspace: Workspace`、`self.manifest: Manifest` 已就绪(`self.base`/`self.key` 为空串)。
  - 在线分支:`self.base: str`、`self.key: str` 已就绪,`self.workspace is None`。

GUI 不写单测(沿用现状)。

- [ ] **Step 1: Create the file**

新建 `labeling_tool/ui/login_dialog.py`:

```python
"""Startup login screen: collect BASE URL + API key (no network verify),
or open an already-downloaded session offline.

Outputs for app.py:
  * offline: self.workspace / self.manifest set -> go straight to main window
  * online:  self.base / self.key set, self.workspace is None -> open FetchDialog
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QComboBox,
)

from labeling_tool.ui.dialog_helpers import load_config, save_config, run_prebuild
from labeling_tool.session.workspace import Workspace, list_local_session_ids
from labeling_tool.session.manifest import Manifest
from labeling_tool.logging_setup import attach_session_log, vlog


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그인")
        self.resize(480, 240)

        # online outputs
        self.base: str = ""
        self.key: str = ""
        # offline outputs
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None

        cfg = load_config()
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        form = QFormLayout()
        form.addRow("BASE URL", self.ed_base)
        form.addRow("X-Viewer-Api-Key", self.ed_key)

        # offline section
        self.cb_local = QComboBox()
        local_ids = list_local_session_ids()
        for sid in local_ids:
            self.cb_local.addItem(f"session_{sid}", sid)
        self.btn_open_local = QPushButton("이미 받은 세션 열기")
        self.btn_open_local.clicked.connect(self._on_open_local)
        if not local_ids:
            self.cb_local.addItem("(받은 세션 없음)")
            self.cb_local.setEnabled(False)
            self.btn_open_local.setEnabled(False)
        offline = QHBoxLayout()
        offline.addWidget(self.cb_local, 1)
        offline.addWidget(self.btn_open_local)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_next = QPushButton("다음")
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._on_next)
        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.btn_next)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("오프라인으로 열기:"))
        root.addLayout(offline)
        root.addWidget(self.progress)
        root.addWidget(self.lbl_status)
        root.addLayout(nav)

    def _on_next(self):
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        if not base or not key:
            QMessageBox.warning(self, "입력 필요", "BASE/Key를 입력하세요.")
            return
        save_config(base, key)
        self.base, self.key = base, key
        self.accept()

    def _on_open_local(self):
        sid = self.cb_local.currentData()
        if sid is None:
            return
        ws = Workspace.default(session_id=int(sid))
        if not ws.manifest_path.exists():
            QMessageBox.warning(self, "없음",
                                f"로컬 매니페스트 없음: {ws.manifest_path}")
            return
        self.workspace = ws
        self.manifest = Manifest.load(ws.manifest_path)
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local) ===", sid)
        run_prebuild(ws, [
            self.manifest.get(fn).timestamp
            for fn in self.manifest.filenames_in_order()],
            self.progress, self.lbl_status)
        self.accept()
```

- [ ] **Step 2: Sanity import**

Run: `.venv/bin/python -c "from labeling_tool.ui.login_dialog import LoginDialog; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 3: Commit**

```bash
git add labeling_tool/ui/login_dialog.py
git commit -m "feat(ui): add LoginDialog (creds + offline session dropdown)"
```

---

### Task 5: `FetchDialog`(数据拉取页,sessionId 下拉)

**Files:**
- Create: `labeling_tool/ui/fetch_dialog.py`

**Interfaces:**
- Consumes: `ViewerApiClient`、`ViewerApiError`、`downloader.download_photos`、`dialog_helpers.{save_config, run_prebuild}`、`session.workspace.Workspace`、`session.manifest.{Manifest, PhotoEntry}`、`session.naming`、`logging_setup.{attach_session_log, vlog}`、`client.list_sessions()`。
- Produces: `FetchDialog(QDialog)`,构造签名 `FetchDialog(base: str, key: str, parent=None)`;成功 `exec_()` 后 `self.workspace: Workspace`、`self.manifest: Manifest` 就绪。

`sessionId` 用 `QComboBox`,打开时 `client.list_sessions()` 填充;失败/空则转为可编辑下拉手输。`fromNum/toNum` 沿用 `QSpinBox`。在线拉取主体逻辑平移自旧 `ConnectDialog._on_fetch` / `_fetch_all_photos`。

- [ ] **Step 1: Create the file**

新建 `labeling_tool/ui/fetch_dialog.py`:

```python
"""Data fetch screen (shown after login): pick a session from the dropdown
(populated via list_sessions), set the optional num zone, then V1 + download
+ prebuild. Mirrors the old ConnectDialog online path."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QSpinBox, QComboBox, QApplication,
)

from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.api.downloader import download_photos
from labeling_tool.ui.dialog_helpers import save_config, run_prebuild
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session import naming
from labeling_tool.logging_setup import attach_session_log, vlog


class FetchDialog(QDialog):
    def __init__(self, base: str, key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("데이터 가져오기 (V1)")
        self.resize(520, 300)
        self.base = base
        self.key = key
        self.client = ViewerApiClient(base_url=base, api_key=key)
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None
        self._sessions_loaded = False

        self.cb_session = QComboBox()
        self.sp_from = QSpinBox(); self.sp_from.setRange(0, 10_000_000)
        self.sp_to = QSpinBox(); self.sp_to.setRange(0, 10_000_000)
        form = QFormLayout()
        form.addRow("sessionId", self.cb_session)
        form.addRow("fromNum (0=미사용)", self.sp_from)
        form.addRow("toNum (0=미사용)", self.sp_to)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_fetch = QPushButton("가져오기 (V1 + 다운로드)")
        self.btn_fetch.setDefault(True)
        self.btn_fetch.clicked.connect(self._on_fetch)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btn_fetch)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.progress)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)

    # ---- session dropdown ----
    def showEvent(self, event):
        super().showEvent(event)
        if not self._sessions_loaded:
            self._sessions_loaded = True
            self._load_sessions()

    def _load_sessions(self):
        try:
            sessions = self.client.list_sessions()
        except Exception as e:  # endpoint pending / network error -> manual
            QMessageBox.warning(
                self, "세션 목록 실패",
                f"세션 목록을 불러오지 못했습니다. 수동 입력하세요.\n{e}")
            self.cb_session.setEditable(True)
            return
        if not sessions:
            self.cb_session.setEditable(True)
            return
        for s in sessions:
            sid = s["sessionId"]
            extra = []
            if s.get("createdAt"):
                extra.append(str(s["createdAt"]))
            if s.get("photoCount") is not None:
                extra.append(f"{s['photoCount']}장")
            label = f"session {sid}"
            if extra:
                label += "  (" + ", ".join(extra) + ")"
            self.cb_session.addItem(label, sid)

    def _selected_sid(self) -> int | None:
        data = self.cb_session.currentData()
        if data is not None:
            return int(data)
        txt = self.cb_session.currentText().strip()
        return int(txt) if txt.isdigit() else None

    def _zone(self):
        f, t = self.sp_from.value(), self.sp_to.value()
        if f > 0 and t > 0:
            return f, t
        return None, None

    # ---- fetch ----
    def _on_fetch(self):
        sid = self._selected_sid()
        if sid is None:
            QMessageBox.warning(self, "입력 필요", "sessionId를 선택/입력하세요.")
            return
        from_num, to_num = self._zone()

        ws = Workspace.default(session_id=sid)
        ws.ensure()
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s fetch start (base=%s) ===", sid, self.base)
        manifest = Manifest(session_id=sid, base=self.base)

        try:
            photos = self._fetch_all_photos(self.client, sid, from_num, to_num)
        except ViewerApiError as e:
            QMessageBox.critical(self, "V1 실패", str(e))
            return
        if not photos:
            QMessageBox.warning(self, "비어있음", "조회된 사진이 없습니다.")
            return

        for p in photos:
            ts = int(p["timestamp"])
            manifest.add(PhotoEntry(
                filename=naming.stitched_filename(ts),
                timestamp=ts,
                photo_id=int(p.get("photoId", 0)),
                report_photo_num=int(p.get("reportPhotoNum", 0)),
                px_per_cm=float(p.get("pxPerCm") or 0.0),
                scale_source="aruco",
            ))

        self.progress.setVisible(True)
        self.progress.setRange(0, len(photos))

        def _prog(done, total):
            self.progress.setValue(done)
            self.lbl_status.setText(f"다운로드 {done}/{total}")
            QApplication.processEvents()

        failures = download_photos(
            photos, ws.origin_dir, ws.detected_dir, progress=_prog)

        run_prebuild(ws, [int(p["timestamp"]) for p in photos],
                     self.progress, self.lbl_status)

        manifest.save(ws.manifest_path)
        save_config(self.base, self.key)

        if failures:
            QMessageBox.warning(
                self, "일부 실패",
                f"{len(failures)}건 다운로드 실패. 나머지는 사용 가능합니다.")
        self.workspace = ws
        self.manifest = manifest
        self.accept()

    @staticmethod
    def _fetch_all_photos(client: ViewerApiClient, session_id: int,
                          from_num, to_num) -> list[dict]:
        if from_num is not None and to_num is not None:
            return client.list_photos(
                session_id, from_num=from_num, to_num=to_num)["photos"]
        out: list[dict] = []
        offset, limit = 0, 100
        while True:
            page = client.list_photos(session_id, offset=offset, limit=limit)
            out.extend(page["photos"])
            total = page.get("total", len(out))
            offset += limit
            if offset >= total or not page["photos"]:
                break
        return out
```

- [ ] **Step 2: Sanity import**

Run: `.venv/bin/python -c "from labeling_tool.ui.fetch_dialog import FetchDialog; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 3: Commit**

```bash
git add labeling_tool/ui/fetch_dialog.py
git commit -m "feat(ui): add FetchDialog with session dropdown (list_sessions + manual fallback)"
```

---

### Task 6: 编排 `app.py` + 删除旧 `connect_dialog.py`

**Files:**
- Modify: `labeling_tool/app.py`
- Delete: `labeling_tool/ui/connect_dialog.py`

**Interfaces:**
- Consumes: `LoginDialog`(`workspace/manifest/base/key`)、`FetchDialog(base, key)`(`workspace/manifest`)、现有 `ViewerMainWindow`、`ViewerApiClient`。

- [ ] **Step 1: Rewrite app.py main()**

把 `labeling_tool/app.py` 中的 import 与 `main()` 改为:

```python
from labeling_tool.ui.login_dialog import LoginDialog
from labeling_tool.ui.fetch_dialog import FetchDialog
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.api.client import ViewerApiClient


def main() -> int:
    app = QApplication(sys.argv)

    login = LoginDialog()
    if not login.exec_():
        return 0  # user cancelled

    base, key = login.base, login.key
    if login.workspace is not None:
        # offline: a downloaded session was opened directly
        workspace, manifest = login.workspace, login.manifest
    else:
        # online: creds entered -> fetch screen
        fetch = FetchDialog(base=base, key=key)
        if not fetch.exec_():
            return 0
        if fetch.workspace is None or fetch.manifest is None:
            return 0
        workspace, manifest = fetch.workspace, fetch.manifest

    client = None
    if base and key:
        client = ViewerApiClient(base_url=base, api_key=key)

    win = ViewerMainWindow(workspace, manifest, client)
    win.show()
    return app.exec_()
```

(保留文件顶部 `os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""` 与 `from PyQt5.QtWidgets import QApplication`、`import os, sys`、模块 docstring。删除对 `connect_dialog` 的旧 import。)

- [ ] **Step 2: Delete the old dialog**

Run: `git rm labeling_tool/ui/connect_dialog.py`
Expected: 文件被移除暂存。

- [ ] **Step 3: Verify nothing else imports it**

Run: `grep -rn "connect_dialog\|ConnectDialog" labeling_tool`
Expected: 无输出(若有命中,改为新对话框后再继续)。

- [ ] **Step 4: Sanity import + full test suite**

Run: `.venv/bin/python -c "import labeling_tool.app; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(含新增的 list_sessions / local-session 用例)。

- [ ] **Step 5: Commit**

```bash
git add labeling_tool/app.py labeling_tool/ui/connect_dialog.py
git commit -m "feat(app): orchestrate LoginDialog -> FetchDialog, drop ConnectDialog"
```

---

### Task 7: 手动冒烟(GUI)

**Files:** 无(仅运行验证)

- [ ] **Step 1: 启动 GUI**

Run: `DISPLAY=:1 .venv/bin/python -m labeling_tool.app`
Expected:
- 先弹**登录页**(BASE/KEY 预填,底部有「오프라인으로 열기」下拉 + 버튼,右下「다음」)。
- 选 `session_18`(本地已有)点「이미 받은 세션 열기」→ 直接进主标注窗口(跳过拉取页)。
- 或填 BASE/KEY 点「다음」→ 弹**拉取页**(sessionId 下拉;若接口未上线会提示并转为可手输)。

- [ ] **Step 2: 记录结果**

人工确认两条路径(离线/在线)都能进入主窗口或给出明确提示;无未捕获异常打印到控制台(libjpeg 的 `Invalid SOS parameters` 警告可忽略)。

---

## Self-Review

**Spec coverage:**
- 登录页(URL/KEY,不验证,仅存 config)→ Task 4 ✅
- 离线扫描下拉 → Task 2(扫描)+ Task 4(下拉)✅
- 拉取页 sessionId 下拉 + list_sessions + 手输降级 → Task 1 + Task 5 ✅
- fromNum/toNum 手输沿用 → Task 5 ✅
- 两独立窗口 + app.py 编排 → Task 6 ✅
- 删除 connect_dialog、共用辅助抽出 → Task 3 + Task 6 ✅
- 单测(list_sessions 容错 + 本地扫描)→ Task 1 + Task 2 ✅

**Placeholder scan:** 无 TBD/TODO;每个改代码的 step 均含完整代码。

**Type consistency:** `list_sessions() -> list[dict]`(项含 `sessionId:int`)在 Task 1 定义、Task 5 `_load_sessions` 消费一致;`run_prebuild(ws, timestamps, progress, status_label)` 在 Task 3 定义、Task 4/5 调用签名一致;`list_local_session_ids(root)` 在 Task 2 定义、Task 4 无参调用(用默认 root)一致;`LoginDialog.{base,key,workspace,manifest}` 与 `FetchDialog(base,key)`/`.{workspace,manifest}` 在 Task 6 消费一致。

**说明(相对 spec 的小细化):** 本地扫描的单测放在 `tests/test_workspace.py`(函数所在模块),`list_sessions` 单测放在新 `tests/test_list_sessions.py`,而非 spec 所写的全部集中在一个文件——按"测试与被测模块就近"更合理。
