import csv

from labeling_tool.api.verify import verify_registered, write_verify_csv


class FakeClient:
    """list_photos returns a fixed server state (paginated)."""
    def __init__(self, photos):
        self._photos = photos

    def list_photos(self, session_id, *, from_num=None, to_num=None,
                    offset=0, limit=100):
        page = self._photos[offset:offset + limit]
        return {"total": len(self._photos), "photos": page}


def _server_photo(ts, *, num, high=True, rep=True, src="user_edit", px=10.0):
    return {"timestamp": ts, "reportPhotoNum": num,
            "highlightS3Key": f"results/43/masks/high_{ts}.png" if high else None,
            "repair15S3Key": f"results/43/masks/15_{ts}.png" if rep else None,
            "crackMetrics": {"metricsSource": src},
            "pxPerCm": px}


def _item(ts, px=10.0):
    return {"timestamp": ts, "pxPerCm": px}


def test_all_confirmed():
    server = [_server_photo(1, num=1), _server_photo(2, num=2)]
    v = verify_registered(FakeClient(server), 43, [_item(1), _item(2)])
    assert all(x["ok"] for x in v)
    assert [x["reportPhotoNum"] for x in v] == [1, 2]


def test_missing_highlight_and_repair_flagged():
    server = [_server_photo(1, num=1, high=False, rep=False)]
    v = verify_registered(FakeClient(server), 43, [_item(1)])
    assert v[0]["ok"] is False
    assert any("highlight" in r for r in v[0]["reasons"])
    assert any("repair15" in r for r in v[0]["reasons"])


def test_stale_metrics_source_flagged():
    server = [_server_photo(1, num=1, src="ai")]   # not user_edit -> our edit didn't persist
    v = verify_registered(FakeClient(server), 43, [_item(1)])
    assert v[0]["ok"] is False
    assert any("metricsSource" in r for r in v[0]["reasons"])


def test_photo_absent_from_server_flagged():
    v = verify_registered(FakeClient([]), 43, [_item(99)])
    assert v[0]["ok"] is False
    assert v[0]["reasons"] == ["not found on server"]


def test_pxpercm_mismatch_flagged():
    server = [_server_photo(1, num=1, px=5.0)]
    v = verify_registered(FakeClient(server), 43, [_item(1, px=10.0)])
    assert v[0]["ok"] is False
    assert any("pxPerCm" in r for r in v[0]["reasons"])


def test_paginates_full_session():
    server = [_server_photo(i, num=i) for i in range(1, 251)]   # 3 pages of 100
    v = verify_registered(FakeClient(server), 43, [_item(1), _item(150), _item(250)])
    assert all(x["ok"] for x in v)


def test_write_verify_csv(tmp_path):
    server = [_server_photo(1, num=1), _server_photo(2, num=2, high=False)]
    v = verify_registered(FakeClient(server), 43, [_item(1), _item(2)])
    p = write_verify_csv(v, tmp_path / "report.csv")
    rows = list(csv.reader(p.open(encoding="utf-8")))
    assert rows[0] == ["timestamp", "reportPhotoNum", "result", "highlightS3Key",
                       "repair15S3Key", "metricsSource", "pxPerCm", "reasons"]
    assert rows[1][2] == "OK"
    assert rows[2][2] == "FAIL" and rows[2][3] == "MISSING"
