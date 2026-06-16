from labeling_tool.session.workspace import Workspace


def test_layout_paths(tmp_path):
    ws = Workspace(root=tmp_path, session_id=43)
    assert ws.session_dir == tmp_path / "session_43"
    assert ws.origin_dir == tmp_path / "session_43" / "Origin"
    assert ws.detected_dir == tmp_path / "session_43" / "Detected"
    assert ws.labeling_dir == tmp_path / "session_43" / "Labeling"
    assert ws.result_dir == tmp_path / "session_43" / "Result"
    assert ws.rebuilt_dir == tmp_path / "session_43" / "Rebuilt"
    assert ws.manifest_path == tmp_path / "session_43" / "manifest.json"


def test_ensure_creates_dirs(tmp_path):
    ws = Workspace(root=tmp_path, session_id=43)
    ws.ensure()
    for d in (ws.origin_dir, ws.detected_dir, ws.labeling_dir,
              ws.result_dir, ws.rebuilt_dir):
        assert d.is_dir()


def test_default_root_under_package_data():
    ws = Workspace.default(session_id=7)
    # Lives under the package's own data/ dir, not the user's home.
    assert ws.root.name == "data"
    assert ws.root.parent.name == "labeling_tool"
    assert ws.session_dir == ws.root / "session_7"
