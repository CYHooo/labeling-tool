import pytest
from labeling_tool.session import naming


def test_stitched_filename():
    assert naming.stitched_filename(1717572612000) == "stitched_1717572612000.jpg"


def test_mask_filename():
    assert naming.mask_filename(1717572612000) == "mask_1717572612000.png"


def test_timestamp_from_stitched():
    assert naming.timestamp_from_filename("stitched_1717572612000.jpg") == 1717572612000


def test_timestamp_from_mask():
    assert naming.timestamp_from_filename("mask_1717572612000.png") == 1717572612000


def test_mask_s3_key():
    assert naming.mask_s3_key(43, 1717572612000) == \
        "results/43/masks/mask_1717572612000.png"


def test_bad_filename_raises():
    with pytest.raises(ValueError):
        naming.timestamp_from_filename("DSC_1234.jpg")


def test_detected_mask_filename_pairs_with_core():
    from labeling_tool.core.mask_io import find_mask_path
    from labeling_tool.session.naming import (
        stitched_filename, detected_mask_filename,
    )
    import tempfile, os
    ts = 1717572612000
    with tempfile.TemporaryDirectory() as d:
        # write the downloaded mask under the detected name
        open(os.path.join(d, detected_mask_filename(ts)), "wb").close()
        found = find_mask_path(stitched_filename(ts), d)
    assert found is not None and found.endswith(detected_mask_filename(ts))
