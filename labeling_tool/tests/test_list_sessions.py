import responses
from labeling_tool.api.client import ViewerApiClient

BASE = "https://api.example.com"
KEY = "test-key"


def _client():
    return ViewerApiClient(base_url=BASE, api_key=KEY)


@responses.activate
def test_list_sessions_object_array():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [
            {"sessionId": 18, "createdAt": "2026-06-01", "photoCount": 42},
            {"sessionId": 19},
        ]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [18, 19]
    assert out[0]["photoCount"] == 42
    # 凭证头随请求发出
    assert responses.calls[0].request.headers["X-Viewer-Api-Key"] == KEY


@responses.activate
def test_list_sessions_bare_array():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [18, 19, 20]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [18, 19, 20]


@responses.activate
def test_list_sessions_skips_items_without_id():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [{"createdAt": "x"}, {"sessionId": 7}]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [7]


@responses.activate
def test_list_sessions_real_shape_passthrough():
    responses.add(
        responses.GET, f"{BASE}/api/viewer/sessions/",
        json={"sessions": [
            {"sessionId": 28, "inspectionName": "6월 3주차 테스트", "photoCount": 4},
            {"sessionId": 18, "inspectionName": "0612 내부 시연", "photoCount": 16},
        ]},
        status=200,
    )
    out = _client().list_sessions()
    assert [s["sessionId"] for s in out] == [28, 18]
    assert out[0]["inspectionName"] == "6월 3주차 테스트"
    assert out[0]["photoCount"] == 4
