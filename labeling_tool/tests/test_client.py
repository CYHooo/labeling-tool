import pytest
import responses
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError

BASE = "https://api.example.com"
KEY = "test-key"


def _client():
    return ViewerApiClient(base_url=BASE, api_key=KEY)


@responses.activate
def test_list_photos_sends_key_and_parses():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/43/photos/",
        json={"sessionId": 43, "offset": 0, "limit": 100, "total": 1,
              "photos": [{"photoId": 101, "timestamp": 1717572612000,
                          "reportPhotoNum": 1, "stitchedUrl": "https://s/stit",
                          "maskUrl": "https://s/mask", "pxPerCm": 45.2,
                          "repairAreas": [], "crackMetrics": {}}]},
        status=200,
    )
    out = _client().list_photos(43, from_num=1, to_num=10)
    assert out["total"] == 1
    assert out["photos"][0]["timestamp"] == 1717572612000
    req = responses.calls[0].request
    assert req.headers["X-Viewer-Api-Key"] == KEY
    assert "fromNum=1" in req.url and "toNum=10" in req.url


@responses.activate
def test_job_not_ready_raises_typed_error():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/43/photos/",
        json={"error": "AI job not finished", "code": "JOB_NOT_READY",
              "details": {}},
        status=409,
    )
    with pytest.raises(ViewerApiError) as ei:
        _client().list_photos(43)
    assert ei.value.code == "JOB_NOT_READY"
    assert ei.value.http_status == 409


@responses.activate
def test_request_presigned_v2():
    responses.add(
        responses.POST, f"{BASE}/api/viewer/presigned-urls/",
        json={"urls": [{"filename": "mask_1.png",
                        "s3Key": "results/43/masks/mask_1.png",
                        "presignedUrl": "https://s3/put",
                        "cacheControl": "max-age=0, must-revalidate"}]},
        status=200,
    )
    out = _client().request_presigned(43, [
        {"filename": "mask_1.png", "timestamp": 1,
         "contentType": "image/png", "sizeBytes": 1024}])
    assert out["urls"][0]["presignedUrl"] == "https://s3/put"


@responses.activate
def test_put_mask_v3_sends_headers():
    responses.add(responses.PUT, "https://s3/put", status=200)
    _client().put_mask("https://s3/put", b"PNGDATA",
                       content_type="image/png",
                       cache_control="max-age=0, must-revalidate")
    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "image/png"
    assert req.headers["Cache-Control"] == "max-age=0, must-revalidate"
    assert req.body == b"PNGDATA"


@responses.activate
def test_register_annotations_v4():
    responses.add(
        responses.POST, f"{BASE}/api/viewer/register-annotations/",
        json={"sessionId": 43, "status": "saved", "updatedPhotoCount": 1},
        status=201,
    )
    out = _client().register_annotations(
        edit_batch_id="b1", session_id=43,
        items=[{"timestamp": 1, "maskS3Key": "k", "pxPerCm": 10.0,
                "scaleSource": "aruco", "repairAreas": [], "crackMetrics": {}}])
    assert out["status"] == "saved"
    body = responses.calls[0].request.body
    assert b"editBatchId" in body


@responses.activate
def test_register_retries_once_on_read_timeout():
    """A slow/lost first register response retries (idempotent) instead of failing."""
    import requests as _rq
    url = f"{BASE}/api/viewer/register-annotations/"
    responses.add(responses.POST, url, body=_rq.exceptions.ReadTimeout("slow"))
    responses.add(responses.POST, url,
                  json={"sessionId": 43, "status": "saved", "updatedPhotoCount": 1},
                  status=201)
    out = _client().register_annotations(
        edit_batch_id="b1", session_id=43,
        items=[{"timestamp": 1, "maskS3Key": "k", "highlightS3Key": "h",
                "repair15S3Key": "r", "pxPerCm": 10.0, "scaleSource": "aruco",
                "repairAreas": [], "crackMetrics": {}}])
    assert out["status"] == "saved"
    assert len(responses.calls) == 2          # first timed out, retried once


@responses.activate
def test_register_read_timeout_propagates_if_retry_also_times_out():
    import requests as _rq
    url = f"{BASE}/api/viewer/register-annotations/"
    responses.add(responses.POST, url, body=_rq.exceptions.ReadTimeout("slow"))
    responses.add(responses.POST, url, body=_rq.exceptions.ReadTimeout("slow again"))
    import pytest
    with pytest.raises(_rq.exceptions.ReadTimeout):
        _client().register_annotations(edit_batch_id="b1", session_id=43, items=[])
    assert len(responses.calls) == 2
