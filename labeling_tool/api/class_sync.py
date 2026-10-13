"""Keep the damage-class list in step with the server (V5 / V6).

The server numbers the classes; the per-server cache (core.classes) lets
the tool work offline. A server without V5 (404) only knows the built-in
crack / spalling, and then adding is not possible.
"""

from __future__ import annotations

import requests

from labeling_tool.api.errors import ViewerApiError
from labeling_tool.core.classes import (
    ClassRegistry, LabelClass, load_cached, parse_class, parse_classes, save_cached,
)
from labeling_tool.logging_setup import vlog

SYNC_OK = "ok"
SYNC_UNSUPPORTED = "unsupported"
SYNC_OFFLINE = "offline"


def sync_classes(client, base_url: str, root=None) -> tuple[ClassRegistry, str]:
    if client is None:
        return load_cached(base_url, root), SYNC_OFFLINE
    try:
        payload = client.list_classes()
    except ViewerApiError as e:
        if e.http_status == 404:
            vlog().info("server has no class API (V5): built-in classes only")
            return ClassRegistry(), SYNC_UNSUPPORTED
        vlog().warning("class sync failed: %s", e)
        return load_cached(base_url, root), SYNC_OFFLINE
    except requests.RequestException as e:
        vlog().warning("class sync failed: %s", e)
        return load_cached(base_url, root), SYNC_OFFLINE
    registry = parse_classes(payload)
    try:
        save_cached(base_url, registry, root)
    except OSError as e:
        vlog().warning("class cache not written: %s", e)
    return registry, SYNC_OK


def add_class_and_cache(client, base_url: str, registry: ClassRegistry,
                        name: str, color: str, root=None
                        ) -> tuple[ClassRegistry, LabelClass]:
    name = (name or "").strip()
    if not name:
        raise ValueError("class name is empty")
    cls = parse_class(client.add_class(name, color))
    updated = registry.with_class(cls)
    try:
        save_cached(base_url, updated, root)
    except OSError as e:
        vlog().warning("class cache not written: %s", e)
    return updated, cls
