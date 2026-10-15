from labeling_tool.session.manifest import Manifest, PhotoEntry


def test_add_and_lookup_by_filename(tmp_path):
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(
        filename="stitched_1717572612000.jpg",
        timestamp=1717572612000, photo_id=101, report_photo_num=1,
        px_per_cm=45.2, scale_source="aruco",
    ))
    e = mf.get("stitched_1717572612000.jpg")
    assert e.timestamp == 1717572612000
    assert e.px_per_cm == 45.2
    assert e.synced is False


def test_roundtrip_save_load(tmp_path):
    path = tmp_path / "manifest.json"
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(
        filename="stitched_1.jpg", timestamp=1, photo_id=1,
        report_photo_num=1, px_per_cm=10.0, scale_source="aruco",
    ))
    mf.save(path)
    loaded = Manifest.load(path)
    assert loaded.session_id == 43
    assert loaded.get("stitched_1.jpg").timestamp == 1


def test_mark_synced(tmp_path):
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(filename="stitched_1.jpg", timestamp=1, photo_id=1,
                      report_photo_num=1, px_per_cm=10.0, scale_source="aruco"))
    mf.mark_synced(["stitched_1.jpg"], batch_id="batch-abc")
    e = mf.get("stitched_1.jpg")
    assert e.synced is True
    assert e.uploaded_batch_id == "batch-abc"


def test_filenames_in_report_order():
    mf = Manifest(session_id=43, base="https://x")
    mf.add(PhotoEntry(filename="stitched_20.jpg", timestamp=20, photo_id=2,
                      report_photo_num=2, px_per_cm=10.0, scale_source="aruco"))
    mf.add(PhotoEntry(filename="stitched_10.jpg", timestamp=10, photo_id=1,
                      report_photo_num=1, px_per_cm=10.0, scale_source="aruco"))
    assert mf.filenames_in_order() == ["stitched_10.jpg", "stitched_20.jpg"]


def test_inspection_name_roundtrip(tmp_path):
    path = tmp_path / "manifest.json"
    Manifest(session_id=7, base="https://x", inspection_name="B1 주차장").save(path)
    assert Manifest.load(path).inspection_name == "B1 주차장"


def test_load_old_manifest_without_inspection_name(tmp_path):
    import json
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"sessionId": 7, "base": "https://x",
                                "fetchedAt": None, "photos": {}}))
    assert Manifest.load(path).inspection_name is None


def _entry(fn="a.jpg", ts=1, num=1, **kw):
    return PhotoEntry(filename=fn, timestamp=ts, photo_id=ts, report_photo_num=num,
                      px_per_cm=2.0, **kw)


def test_new_fields_have_defaults_and_round_trip(tmp_path):
    m = Manifest(session_id=1, base="")
    m.add(_entry(surface="wall", tilt_deg=87.0, tilt_source="sensor",
                 surface_edit="floor", delete_pending=True))
    m.save(tmp_path / "m.json")
    e = Manifest.load(tmp_path / "m.json").get("a.jpg")
    assert (e.surface, e.tilt_deg, e.tilt_source, e.surface_edit, e.delete_pending) == (
        "wall", 87.0, "sensor", "floor", True)


def test_an_old_manifest_loads(tmp_path):
    import json
    (tmp_path / "m.json").write_text(json.dumps({"sessionId": 1, "base": "", "photos": {
        "a.jpg": {"filename": "a.jpg", "timestamp": 1, "photo_id": 1,
                  "report_photo_num": 1, "px_per_cm": 2.0}}}), encoding="utf-8")
    e = Manifest.load(tmp_path / "m.json").get("a.jpg")
    assert e.surface is None and e.surface_edit is None and e.delete_pending is False


def test_refetch_keeps_local_edits_and_takes_new_server_values():
    old = Manifest(session_id=1, base="")
    old.add(_entry(surface="wall", surface_edit="floor", delete_pending=True))
    new = Manifest(session_id=1, base="")
    new.add(_entry(surface="ceiling", tilt_deg=170.0))
    new.keep_from(old)
    e = new.get("a.jpg")
    assert e.surface == "ceiling" and e.tilt_deg == 170.0
    assert e.surface_edit == "floor" and e.delete_pending is True


def test_remove():
    m = Manifest(session_id=1, base="")
    m.add(_entry())
    m.remove("a.jpg")
    m.remove("a.jpg")                     # absent: no error
    assert m.filenames_in_order() == []


# ---------------------------------------------------------------- server_missing
def _photo(n, **kw):
    return PhotoEntry(filename=f"stitched_{n}.jpg", timestamp=n, photo_id=n,
                      report_photo_num=n, px_per_cm=10.0, **kw)


def test_server_missing_defaults_false_and_old_manifests_load(tmp_path):
    import json
    path = tmp_path / "manifest.json"
    mf = Manifest(session_id=1, base="")
    mf.add(_photo(1))
    mf.save(path)
    data = json.loads(path.read_text())
    del data["photos"]["stitched_1.jpg"]["server_missing"]   # an older manifest
    path.write_text(json.dumps(data))
    assert Manifest.load(path).get("stitched_1.jpg").server_missing is False


def test_server_missing_round_trips(tmp_path):
    path = tmp_path / "manifest.json"
    mf = Manifest(session_id=1, base="")
    mf.add(_photo(1))
    assert mf.mark_server_missing([1, 99]) == ["stitched_1.jpg"]
    assert mf.mark_server_missing([1]) == []          # already marked
    mf.save(path)
    assert Manifest.load(path).get("stitched_1.jpg").server_missing is True


def test_keep_from_a_photo_listed_again_is_not_missing():
    old = Manifest(session_id=1, base="")
    old.add(_photo(1, server_missing=True))
    old.add(_photo(2, server_missing=True))
    new = Manifest(session_id=1, base="")
    new.add(_photo(1))
    new.keep_from(old)
    assert new.get("stitched_1.jpg").server_missing is False
    assert new.get("stitched_2.jpg").server_missing is True
