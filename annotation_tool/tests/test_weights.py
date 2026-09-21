"""SAM2.1 weight download: checksum-verified, atomic, cancellable."""
import hashlib
import http.server
import threading
from functools import partial

import pytest

from annotation_tool.segmenter import weights

PAYLOAD = b"fake-sam2-weights" * 1000


@pytest.fixture
def server(tmp_path):
    (tmp_path / "srv").mkdir()
    (tmp_path / "srv" / "w.pt").write_bytes(PAYLOAD)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "srv"))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/w.pt"
    httpd.shutdown()


def test_official_constants():
    assert weights.SAM2_WEIGHTS_URL == (
        "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt")
    assert weights.SAM2_WEIGHTS_SHA256 == (
        "a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5")
    assert weights.SAM2_WEIGHTS_SIZE == 323_606_802


def test_download_ok_reports_progress(server, tmp_path):
    dest = tmp_path / "checkpoint" / "sam2.pt"
    seen = []
    weights.download_weights(server, dest, hashlib.sha256(PAYLOAD).hexdigest(),
                             progress=lambda done, total: seen.append((done, total)),
                             chunk_size=4096)
    assert dest.read_bytes() == PAYLOAD
    assert not dest.with_name("sam2.pt.part").exists()
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))


def test_checksum_mismatch_leaves_nothing(server, tmp_path):
    dest = tmp_path / "sam2.pt"
    with pytest.raises(ValueError, match="checksum"):
        weights.download_weights(server, dest, "0" * 64)
    assert not dest.exists() and not dest.with_name("sam2.pt.part").exists()


def test_cancel_leaves_nothing(server, tmp_path):
    dest = tmp_path / "sam2.pt"
    with pytest.raises(weights.DownloadCancelled):
        weights.download_weights(server, dest, hashlib.sha256(PAYLOAD).hexdigest(),
                                 progress=lambda done, total: False, chunk_size=4096)
    assert not dest.exists() and not dest.with_name("sam2.pt.part").exists()


def test_existing_weights_untouched_on_failure(server, tmp_path):
    dest = tmp_path / "sam2.pt"
    dest.write_bytes(b"old")
    with pytest.raises(ValueError):
        weights.download_weights(server, dest, "0" * 64)
    assert dest.read_bytes() == b"old"
