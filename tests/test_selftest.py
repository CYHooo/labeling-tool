"""Build smoke test entry point used by CI on the packaged exe."""
from labeling_tool import selftest


def test_full_reports_missing_module(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "user_data_home", lambda: tmp_path)
    monkeypatch.setattr(selftest, "COMMON_MODULES", ())
    monkeypatch.setattr(selftest, "_check_onnx", lambda: None)
    monkeypatch.setattr(selftest, "_check_login_dialog", lambda: None)
    monkeypatch.setattr(selftest, "FULL_MODULES", ("definitely_missing_mod_xyz",))
    monkeypatch.setattr(selftest, "_check_sam2_cfg", lambda: None)
    monkeypatch.setattr(selftest, "_check_backend", lambda: None)
    monkeypatch.setattr(selftest, "_check_fewshot_available", lambda: None)
    assert selftest.run_selftest("full") == 1
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "FAIL import definitely_missing_mod_xyz" in log
    assert "RESULT: FAIL" in log


def test_full_checks_fewshot_available(monkeypatch, tmp_path):
    monkeypatch.setattr(selftest, "user_data_home", lambda: tmp_path)
    monkeypatch.setattr(selftest, "COMMON_MODULES", ())
    monkeypatch.setattr(selftest, "FULL_MODULES", ())
    monkeypatch.setattr(selftest, "_check_onnx", lambda: None)
    monkeypatch.setattr(selftest, "_check_login_dialog", lambda: None)
    monkeypatch.setattr(selftest, "_check_sam2_cfg", lambda: None)
    monkeypatch.setattr(selftest, "_check_backend", lambda: None)
    monkeypatch.setattr("labeling_tool.ui.login_dialog.fewshot_available", lambda: False)
    assert selftest.run_selftest("full") == 1
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "FAIL few-shot stack available" in log


def test_full_checks_have_no_sam3():
    names = [name for name, _ in selftest._checks("full")]
    assert not any("sam3" in n for n in names)
    assert "SAM2 hydra config composes" in names
    assert "exe backend is sam2" in names


def test_unknown_variant(monkeypatch, tmp_path):
    """lite is gone as of v1.3.0, so it is now an unknown variant too."""
    monkeypatch.setattr(selftest, "user_data_home", lambda: tmp_path)
    # each run rewrites selftest.log, so check the log of the last one
    assert selftest.run_selftest("lite") == 2
    assert selftest.run_selftest("medium") == 2
    log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
    assert "unknown selftest variant: 'medium'" in log


def test_app_main_dispatches_selftest(monkeypatch):
    from labeling_tool import app
    monkeypatch.setattr(selftest, "run_selftest", lambda variant: {"full": 7}.get(variant, 3))
    assert app.main(["--selftest=full"]) == 7
    assert app.main(["--selftest"]) == 7          # bare flag -> full, the only variant
