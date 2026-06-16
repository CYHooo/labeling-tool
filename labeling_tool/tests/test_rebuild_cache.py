import cv2
import numpy as np

from labeling_tool.rebuild_cache import prebuild_rebuilt
from labeling_tool.core.mask_io import find_mask_path
from labeling_tool.session import naming


def _make_pair(origin_dir, detected_dir, ts):
    """Write a tiny synthetic origin + Detected crack mask for timestamp ts."""
    img = np.full((80, 80, 3), 30, dtype=np.uint8)
    img[38:43, 10:70] = 220                      # bright horizontal band
    cv2.imwrite(str(origin_dir / naming.stitched_filename(ts)), img)

    mask = np.zeros((80, 80, 3), dtype=np.uint8)
    mask[38:43, 10:70, 2] = 255                  # R channel = crack
    cv2.imwrite(str(detected_dir / naming.detected_mask_filename(ts)), mask)


def _dirs(tmp_path):
    o = tmp_path / "Origin"; o.mkdir()
    d = tmp_path / "Detected"; d.mkdir()
    r = tmp_path / "Rebuilt"
    return o, d, r


def test_prebuild_writes_cache_resolvable_by_core(tmp_path):
    o, d, r = _dirs(tmp_path)
    _make_pair(o, d, 1)
    seen = []
    failures = prebuild_rebuilt(o, d, r, [1],
                               progress=lambda done, total: seen.append((done, total)))
    assert failures == []
    out = r / naming.detected_mask_filename(1)
    assert out.exists()
    cached = cv2.imread(str(out), cv2.IMREAD_UNCHANGED)
    assert cached.ndim == 3                       # 3-channel (R=crack) like on-demand rebuild
    # The core resolver must find it for the origin filename.
    assert find_mask_path(naming.stitched_filename(1), str(r)) == str(out)
    assert seen[-1] == (1, 1)


def test_prebuild_is_idempotent(tmp_path):
    o, d, r = _dirs(tmp_path)
    _make_pair(o, d, 1)
    prebuild_rebuilt(o, d, r, [1])
    out = r / naming.detected_mask_filename(1)
    marker = out.read_bytes()
    # Second run must not recompute/overwrite an existing cache entry.
    failures = prebuild_rebuilt(o, d, r, [1])
    assert failures == []
    assert out.read_bytes() == marker


def test_prebuild_records_failure_on_missing_input(tmp_path):
    o, d, r = _dirs(tmp_path)
    # no files written for ts=99
    failures = prebuild_rebuilt(o, d, r, [99])
    assert len(failures) == 1
    assert failures[0]["timestamp"] == 99
    assert not (r / naming.detected_mask_filename(99)).exists()


def test_prebuild_parallel_multiple(tmp_path):
    o, d, r = _dirs(tmp_path)
    ts_list = [1, 2, 3, 4]
    for ts in ts_list:
        _make_pair(o, d, ts)
    seen = []
    failures = prebuild_rebuilt(
        o, d, r, ts_list,
        progress=lambda done, total: seen.append((done, total)),
        workers=2)                      # force the process-pool path
    assert failures == []
    for ts in ts_list:
        assert (r / naming.detected_mask_filename(ts)).exists()
    assert seen[-1] == (4, 4)
