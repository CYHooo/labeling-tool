"""Shared checksum-verified downloader used by weights and updates."""
import hashlib
import http.server
import threading
from functools import partial

import pytest

from labeling_tool.core import net_download

PAYLOAD = b"payload" * 5000


@pytest.fixture
def server(tmp_path):
    (tmp_path / "srv").mkdir()
    (tmp_path / "srv" / "f.bin").write_bytes(PAYLOAD)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "srv"))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/f.bin"
    httpd.shutdown()


def test_download_ok(server, tmp_path):
    dest = tmp_path / "out" / "f.bin"
    seen = []
    net_download.download_file(server, dest, hashlib.sha256(PAYLOAD).hexdigest(),
                               progress=lambda d, t: seen.append((d, t)), chunk_size=4096)
    assert dest.read_bytes() == PAYLOAD
    assert not dest.with_name("f.bin.part").exists()
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))


def test_checksum_mismatch(server, tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(ValueError, match="checksum"):
        net_download.download_file(server, dest, "0" * 64)
    assert not dest.exists() and not dest.with_name("f.bin.part").exists()


def test_cancel(server, tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(net_download.DownloadCancelled):
        net_download.download_file(server, dest, hashlib.sha256(PAYLOAD).hexdigest(),
                                   progress=lambda d, t: False, chunk_size=4096)
    assert not dest.exists() and not dest.with_name("f.bin.part").exists()


def test_existing_file_survives_failure(server, tmp_path):
    dest = tmp_path / "f.bin"
    dest.write_bytes(b"old")
    with pytest.raises(ValueError):
        net_download.download_file(server, dest, "0" * 64)
    assert dest.read_bytes() == b"old"


def test_weights_module_reuses_it():
    from annotation_tool.segmenter import weights
    assert weights.download_weights is net_download.download_file
    assert weights.DownloadCancelled is net_download.DownloadCancelled
