"""Build smoke test entry point used by CI on the packaged exe."""
import importlib.util

from labeling_tool import selftest


def test_lite_passes_and_writes_log(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "app_home", lambda: tmp_path)
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "torch" else real_find_spec(name, *a))
    assert selftest.run_selftest("lite") == 0
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "OK   import labeling_tool.ui.login_dialog" in log
    assert "OK   MobileSAM ONNX models" in log
    assert "RESULT: PASS" in log


def test_lite_fails_when_torch_is_bundled(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "app_home", lambda: tmp_path)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: object())
    monkeypatch.setattr(selftest, "COMMON_MODULES", ())
    monkeypatch.setattr(selftest, "_check_onnx", lambda: None)
    monkeypatch.setattr(selftest, "_check_login_dialog", lambda: None)
    assert selftest.run_selftest("lite") == 1
    assert "FAIL torch not bundled" in (tmp_path / "selftest.log").read_text(encoding="utf-8")


def test_full_reports_missing_module(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "app_home", lambda: tmp_path)
    monkeypatch.setattr(selftest, "COMMON_MODULES", ())
    monkeypatch.setattr(selftest, "_check_onnx", lambda: None)
    monkeypatch.setattr(selftest, "_check_login_dialog", lambda: None)
    monkeypatch.setattr(selftest, "FULL_MODULES", ("definitely_missing_mod_xyz",))
    monkeypatch.setattr(selftest, "_check_bpe", lambda: None)
    monkeypatch.setattr(selftest, "_check_sam2_cfg", lambda: None)
    assert selftest.run_selftest("full") == 1
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "FAIL import definitely_missing_mod_xyz" in log
    assert "RESULT: FAIL" in log


def test_unknown_variant():
    assert selftest.run_selftest("medium") == 2


def test_app_main_dispatches_selftest(monkeypatch):
    from labeling_tool import app
    monkeypatch.setattr(selftest, "run_selftest", lambda variant: {"full": 7}.get(variant, 3))
    assert app.main(["--selftest=full"]) == 7
    assert app.main(["--selftest"]) == 3          # bare flag -> lite
