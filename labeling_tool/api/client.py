"""HTTP client for the 로컬 포토뷰어 API (V1~V4).

Auth: X-Viewer-Api-Key header. All non-2xx responses are parsed for the
common error body {error, code, details} and re-raised as ViewerApiError.
"""

from __future__ import annotations

import time

import requests

from labeling_tool.api.errors import ViewerApiError
from labeling_tool.logging_setup import vlog

DEFAULT_TIMEOUT = 30


class ViewerApiClient:
    def __init__(self, base_url: str, api_key: str,
                 timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({"X-Viewer-Api-Key": api_key})

    # ---- internal -------------------------------------------------
    def _raise_for_error(self, resp: requests.Response) -> None:
        if resp.ok:
            return
        try:
            body = resp.json()
        except ValueError:
            body = {}
        vlog().error("API error %s %s: %s", resp.status_code,
                     body.get("code", "HTTP_ERROR"), body.get("error", resp.reason))
        raise ViewerApiError(
            code=body.get("code", "HTTP_ERROR"),
            message=body.get("error", resp.reason or "request failed"),
            http_status=resp.status_code,
            details=body.get("details"),
        )

    # ---- V1 -------------------------------------------------------
    def list_photos(self, session_id: int, *, from_num: int | None = None,
                    to_num: int | None = None, offset: int = 0,
                    limit: int = 100) -> dict:
        params: dict = {}
        if from_num is not None and to_num is not None:
            params["fromNum"] = from_num
            params["toNum"] = to_num
        else:
            params["offset"] = offset
            params["limit"] = limit
        url = f"{self.base_url}/api/viewer/sessions/{session_id}/photos/"
        t = time.perf_counter()
        resp = self._s.get(url, params=params, timeout=self.timeout)
        self._raise_for_error(resp)
        data = resp.json()
        vlog().info("V1 list_photos session=%s %s -> total=%s photos=%d (%.0f ms)",
                    session_id, params, data.get("total"),
                    len(data.get("photos", [])), (time.perf_counter() - t) * 1000)
        return data

    # ---- V2 -------------------------------------------------------
    def request_presigned(self, session_id: int, files: list[dict]) -> dict:
        url = f"{self.base_url}/api/viewer/presigned-urls/"
        t = time.perf_counter()
        resp = self._s.post(
            url, json={"sessionId": session_id, "files": files},
            timeout=self.timeout)
        self._raise_for_error(resp)
        vlog().info("V2 presigned files=%d (%.0f ms)",
                    len(files), (time.perf_counter() - t) * 1000)
        return resp.json()

    # ---- V3 -------------------------------------------------------
    def put_mask(self, presigned_url: str, png_bytes: bytes, *,
                 content_type: str = "image/png",
                 cache_control: str = "max-age=0, must-revalidate") -> None:
        # Direct S3 PUT: no X-Viewer-Api-Key, header values must match what
        # V2 echoed back or S3 signature validation fails.
        t = time.perf_counter()
        resp = requests.put(
            presigned_url, data=png_bytes,
            headers={"Content-Type": content_type,
                     "Cache-Control": cache_control},
            timeout=self.timeout)
        vlog().info("V3 PUT mask bytes=%d -> %s (%.0f ms)",
                    len(png_bytes), resp.status_code,
                    (time.perf_counter() - t) * 1000)
        if not resp.ok:
            raise ViewerApiError(
                code="S3_PUT_FAILED",
                message=f"S3 PUT failed: {resp.text[:200]}",
                http_status=resp.status_code)

    # ---- V4 -------------------------------------------------------
    def register_annotations(self, *, edit_batch_id: str, session_id: int,
                             items: list[dict]) -> dict:
        url = f"{self.base_url}/api/viewer/register-annotations/"
        t = time.perf_counter()
        resp = self._s.post(url, json={
            "editBatchId": edit_batch_id,
            "sessionId": session_id,
            "items": items,
        }, timeout=self.timeout)
        self._raise_for_error(resp)
        data = resp.json()
        vlog().info("V4 register items=%d -> %s (%.0f ms)",
                    len(items), data.get("status"),
                    (time.perf_counter() - t) * 1000)
        return data

    # ---- session list (endpoint PENDING: assumed contract) --------
    def list_sessions(self) -> list[dict]:
        """List available session ids for the session dropdown.

        Endpoint is not live yet; assumed contract is
        ``GET {base}/api/viewer/sessions/`` returning
        ``{"sessions": [{"sessionId": int, ...}, ...]}``. A bare-int array
        ``{"sessions": [18, 19]}`` is also accepted. Each returned dict is
        normalized to carry an int ``sessionId``; other fields pass through.
        When the real endpoint lands, only this method should need changes.
        """
        url = f"{self.base_url}/api/viewer/sessions/"
        t = time.perf_counter()
        resp = self._s.get(url, timeout=self.timeout)
        self._raise_for_error(resp)
        data = resp.json()
        raw = data.get("sessions", []) if isinstance(data, dict) else data
        out: list[dict] = []
        for item in raw or []:
            if isinstance(item, dict):
                if "sessionId" in item:
                    out.append({**item, "sessionId": int(item["sessionId"])})
            else:
                out.append({"sessionId": int(item)})
        vlog().info("list_sessions -> %d (%.0f ms)",
                    len(out), (time.perf_counter() - t) * 1000)
        return out
