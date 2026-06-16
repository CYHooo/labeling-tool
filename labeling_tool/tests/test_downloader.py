import responses
from labeling_tool.api.downloader import download_photos


@responses.activate
def test_downloaded_mask_resolvable_by_core(tmp_path):
    from labeling_tool.core.mask_io import find_mask_path
    from labeling_tool.session.naming import stitched_filename
    responses.add(responses.GET, "https://s/stit1", body=b"JPG", status=200)
    responses.add(responses.GET, "https://s/mask1", body=b"PNG", status=200)
    photos = [{"timestamp": 1, "stitchedUrl": "https://s/stit1",
               "maskUrl": "https://s/mask1"}]
    origin_dir = tmp_path / "Origin"; origin_dir.mkdir()
    detected_dir = tmp_path / "Detected"; detected_dir.mkdir()
    download_photos(photos, origin_dir, detected_dir)
    found = find_mask_path(stitched_filename(1), str(detected_dir))
    assert found is not None


@responses.activate
def test_downloads_pairs_with_progress(tmp_path):
    responses.add(responses.GET, "https://s/stit1", body=b"JPGDATA", status=200)
    responses.add(responses.GET, "https://s/mask1", body=b"PNGDATA", status=200)
    photos = [{"timestamp": 1, "stitchedUrl": "https://s/stit1",
               "maskUrl": "https://s/mask1"}]
    origin_dir = tmp_path / "Origin"
    detected_dir = tmp_path / "Detected"
    origin_dir.mkdir(); detected_dir.mkdir()

    seen = []
    failures = download_photos(
        photos, origin_dir, detected_dir,
        progress=lambda done, total: seen.append((done, total)))

    assert failures == []
    assert (origin_dir / "stitched_1.jpg").read_bytes() == b"JPGDATA"
    assert (detected_dir / "stitched_1_mask.png").read_bytes() == b"PNGDATA"
    assert seen[-1] == (1, 1)


@responses.activate
def test_records_failure_without_aborting(tmp_path):
    responses.add(responses.GET, "https://s/stit1", body=b"JPG", status=200)
    responses.add(responses.GET, "https://s/mask1", status=500)
    photos = [{"timestamp": 1, "stitchedUrl": "https://s/stit1",
               "maskUrl": "https://s/mask1"}]
    origin_dir = tmp_path / "Origin"; origin_dir.mkdir()
    detected_dir = tmp_path / "Detected"; detected_dir.mkdir()
    failures = download_photos(photos, origin_dir, detected_dir)
    assert len(failures) == 1
    assert failures[0]["timestamp"] == 1


@responses.activate
def test_partial_pair_cleaned_on_mask_failure(tmp_path):
    responses.add(responses.GET, "https://s/stit1", body=b"JPG", status=200)
    responses.add(responses.GET, "https://s/mask1", status=500)
    photos = [{"timestamp": 1, "stitchedUrl": "https://s/stit1",
               "maskUrl": "https://s/mask1"}]
    origin_dir = tmp_path / "Origin"; origin_dir.mkdir()
    detected_dir = tmp_path / "Detected"; detected_dir.mkdir()
    failures = download_photos(photos, origin_dir, detected_dir)
    assert len(failures) == 1
    # No orphaned stitched file must remain (no partial pair).
    assert not (origin_dir / "stitched_1.jpg").exists()
    assert not (detected_dir / "stitched_1_mask.png").exists()
