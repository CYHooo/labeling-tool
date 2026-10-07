"""A failed download must never cost the files already on disk: a refetch
writes each pair to .part files and swaps them in only when both arrive."""
from labeling_tool.api import downloader
from labeling_tool.session import naming


def _photo(ts):
    return {"timestamp": ts, "stitchedUrl": f"s{ts}", "maskUrl": f"m{ts}"}


def test_a_failed_refetch_keeps_the_previous_pair(tmp_path, monkeypatch):
    origin, detected = tmp_path / "Origin", tmp_path / "Detected"
    origin.mkdir(); detected.mkdir()
    old_s = origin / naming.stitched_filename(1)
    old_m = detected / naming.detected_mask_filename(1)
    old_s.write_bytes(b"old-stitched"); old_m.write_bytes(b"old-mask")

    def fake(url, dest, timeout=60, retries=3):
        if url.startswith("m"):
            raise IOError("mask unreachable")
        dest.write_bytes(b"new-stitched")
        return 12
    monkeypatch.setattr(downloader, "_download_to", fake)
    failures = downloader.download_photos([_photo(1)], origin, detected)
    assert len(failures) == 1
    assert old_s.read_bytes() == b"old-stitched" and old_m.read_bytes() == b"old-mask"
    assert not list(tmp_path.rglob("*.part"))


def test_a_successful_download_replaces_both_files(tmp_path, monkeypatch):
    origin, detected = tmp_path / "Origin", tmp_path / "Detected"
    origin.mkdir(); detected.mkdir()
    (origin / naming.stitched_filename(1)).write_bytes(b"old")

    def fake(url, dest, timeout=60, retries=3):
        dest.write_bytes(b"new-" + url.encode())
        return 5
    monkeypatch.setattr(downloader, "_download_to", fake)
    assert downloader.download_photos([_photo(1)], origin, detected) == []
    assert (origin / naming.stitched_filename(1)).read_bytes() == b"new-s1"
    assert (detected / naming.detected_mask_filename(1)).read_bytes() == b"new-m1"
    assert not list(tmp_path.rglob("*.part"))
