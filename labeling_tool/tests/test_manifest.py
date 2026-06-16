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
