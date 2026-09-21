"""First-use SAM2.1 weight download prompt shown before the few-shot tool opens."""
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from annotation_tool import configs
from annotation_tool.segmenter import weights
from labeling_tool.ui import sam2_weights_dialog as dlg

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def ckpt(monkeypatch, tmp_path):
    path = tmp_path / "checkpoint" / "sam2.1_hiera_base_plus.pt"
    monkeypatch.setattr(configs, "SAM2_CHECKPOINT", str(path))
    return path


def test_present_weights_need_no_prompt(ckpt, monkeypatch):
    ckpt.parent.mkdir(parents=True)
    ckpt.write_bytes(b"x")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("asked"))
    assert dlg.ensure_sam2_weights() is True


def test_user_declines(ckpt, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(weights, "download_weights", lambda *a, **k: pytest.fail("downloaded"))
    assert dlg.ensure_sam2_weights() is False


def test_user_accepts_and_download_succeeds(ckpt, monkeypatch):
    calls = []

    def fake_download(url, dest, sha256, progress=None, **kw):
        calls.append((url, Path(dest), sha256))
        progress(50, 100)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"w")

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(weights, "download_weights", fake_download)
    assert dlg.ensure_sam2_weights() is True
    assert calls == [(weights.SAM2_WEIGHTS_URL, ckpt, weights.SAM2_WEIGHTS_SHA256)]


def test_download_error_is_reported(ckpt, monkeypatch):
    shown = []

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(weights, "download_weights", boom)
    assert dlg.ensure_sam2_weights() is False
    assert "network down" in shown[0]


def test_cancel_is_silent(ckpt, monkeypatch):
    def cancelled(*a, **k):
        raise weights.DownloadCancelled()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail("error shown"))
    monkeypatch.setattr(weights, "download_weights", cancelled)
    assert dlg.ensure_sam2_weights() is False


def test_app_skips_fewshot_when_weights_unavailable(monkeypatch):
    from labeling_tool import app
    import annotation_tool.ui.main_window as fs_mw
    monkeypatch.setattr(configs, "BACKEND", "sam2")
    monkeypatch.setattr(dlg, "ensure_sam2_weights", lambda parent=None: False)
    monkeypatch.setattr(fs_mw, "MainWindow", lambda: pytest.fail("window built"))
    assert app.open_tool_window("fewshot") is None
