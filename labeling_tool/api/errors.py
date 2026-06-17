"""Typed error for Viewer API responses (공통 오류 응답: {error, code, details})."""

from __future__ import annotations


class ViewerApiError(Exception):
    def __init__(self, code: str, message: str,
                 http_status: int, details: dict | None = None):
        super().__init__(f"[{http_status} {code}] {message}")
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}
