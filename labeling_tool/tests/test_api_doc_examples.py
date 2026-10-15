"""The v1.0.16 API reference examples (surface and delete), checked against
the client code that builds and reads them.

The JSON below is copied from the request / response examples of the
v1.0.16 reference (kept outside this public repository). Download URLs are
left out of the photo-list entry: only the keys the client reads matter here.
"""

import pytest

from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.edit_fields import (
    DELETED_KEY, SKIPPED_KEY, photo_fields, timestamps_in)
from labeling_tool.session.photo_edits import apply_photo_refresh

# V1 response, photos[0] (v1.0.16 fields at the end).
DOC_PHOTO_ENTRY = {
    "photoId": 101,
    "timestamp": 1717572612000,
    "reportPhotoNum": 1,
    "highlightS3Key": "results/43/masks/high_1717572612000.png",
    "repair15S3Key": "results/43/masks/15_1717572612000.png",
    "pxPerCm": 45.2,
    "scaleSource": "aruco",
    "repairAreas": [{"cx": 320, "cy": 180, "w": 120, "h": 40, "angleDeg": 15}],
    "crackMetrics": {"lengthMm": 1234.5, "avgWidthMm": 0.8, "maxWidthMm": 1.2,
                     "metricsSource": "user_edit"},
    "surface": "wall",
    "tiltDeg": 87.4,
    "tiltSource": "sensor",
}

# V4 request: surface changes and deletes only, no images.
DOC_V4_REQUEST = {
    "editBatchId": "viewer-edit-batch-002-0",
    "sessionId": 43,
    "items": [],
    "surfaceUpdates": [
        {"timestamp": 1717572612000, "surface": "wall"},
        {"timestamp": 1717572614000, "surface": "ceiling"},
    ],
    "deletes": [
        {"timestamp": 1717572613000},
        {"timestamp": 1717572615000},
    ],
}

# V4 response to the request above.
DOC_V4_RESPONSE = {
    "sessionId": 43,
    "status": "saved",
    "updatedPhotoCount": 0,
    "photos": [],
    "deleted": [1717572613000],
    "skipped": [1717572615000],
}


def test_doc_photo_entry_gives_the_surface_fields():
    assert photo_fields(DOC_PHOTO_ENTRY) == {
        "surface": "wall", "tilt_deg": 87.4, "tilt_source": "sensor"}


def test_doc_photo_entry_without_the_new_fields_reads_as_unknown():
    # A v1.0.15 server sends none of the three keys.
    old = {k: v for k, v in DOC_PHOTO_ENTRY.items()
           if k not in ("surface", "tiltDeg", "tiltSource")}
    assert photo_fields(old) == {
        "surface": None, "tilt_deg": None, "tilt_source": None}


def test_doc_photo_entry_refreshes_number_and_surface():
    class Entry:
        timestamp = 1717572612000
        report_photo_num = 3
        surface = None
        tilt_deg = None
        tilt_source = None
        surface_edit = "floor"

    class Manifest:
        photos = {"stitched_1717572612000.jpg": Entry()}

    manifest = Manifest()
    assert apply_photo_refresh(manifest, [DOC_PHOTO_ENTRY]) is True
    entry = manifest.photos["stitched_1717572612000.jpg"]
    assert (entry.report_photo_num, entry.surface, entry.tilt_deg,
            entry.tilt_source) == (1, "wall", 87.4, "sensor")
    assert entry.surface_edit == "floor"     # local edit left alone


class _Resp:
    ok = True
    status_code = 201

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def sent(monkeypatch):
    """The client with session.post replaced; returns (client, captured calls)."""
    client = ViewerApiClient(base_url="https://api.example.com", api_key="k")
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        return _Resp(DOC_V4_RESPONSE)

    monkeypatch.setattr(client._s, "post", fake_post)
    return client, calls


def test_register_builds_the_doc_request_body(sent):
    client, calls = sent
    data = client.register_annotations(
        edit_batch_id=DOC_V4_REQUEST["editBatchId"],
        session_id=DOC_V4_REQUEST["sessionId"],
        items=[],
        surface_updates=DOC_V4_REQUEST["surfaceUpdates"],
        deletes=DOC_V4_REQUEST["deletes"])
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/viewer/register-annotations/")
    assert calls[0]["json"] == DOC_V4_REQUEST
    assert data == DOC_V4_RESPONSE


def test_register_without_edits_sends_no_edit_keys(sent):
    # A plain mask upload stays exactly the v1.0.15 body.
    client, calls = sent
    client.register_annotations(edit_batch_id="b-0", session_id=43, items=[])
    assert calls[0]["json"] == {"editBatchId": "b-0", "sessionId": 43,
                                "items": []}


def test_doc_response_lists_deleted_and_skipped():
    assert timestamps_in(DOC_V4_RESPONSE, DELETED_KEY) == [1717572613000]
    assert timestamps_in(DOC_V4_RESPONSE, SKIPPED_KEY) == [1717572615000]


def test_doc_response_object_form_is_accepted_too():
    # The reference notes that [{"timestamp": ...}] is also accepted.
    resp = dict(DOC_V4_RESPONSE,
                deleted=[{"timestamp": 1717572613000}],
                skipped=[{"timestamp": 1717572615000}])
    assert timestamps_in(resp, DELETED_KEY) == [1717572613000]
    assert timestamps_in(resp, SKIPPED_KEY) == [1717572615000]
