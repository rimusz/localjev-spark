"""Stdlib helpers — safe to import without FastAPI / Laya."""

from __future__ import annotations

import asyncio
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

HOP_BY_HOP = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}
# Starlette/uvicorn set these; forwarding them duplicates the hop.
DROP_RESPONSE_EXTRA = {"date", "server"}


def resolve_backend(raw: str, platform: str) -> str:
    """Pick the Laya runtime. ``auto`` is laya-mlx on macOS, official torch laya on Linux."""
    value = (raw or "auto").strip().lower()
    if value in {"", "auto"}:
        return "laya-mlx" if platform == "darwin" else "laya"
    if value == "laya-mlx":
        return "laya-mlx"
    if value in {"laya", "localjev", "torch"}:
        return "laya"
    raise ValueError(f"unknown LOCALJEV_BACKEND={raw!r} (supported: auto, laya-mlx, laya)")


def parse_upstream(url: str) -> str:
    """Normalize a Spark OpenAI base to `scheme://host:port/path` (default path `/v1`)."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("empty upstream URL")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "localhost"
    if parsed.port:
        port = parsed.port
    else:
        port = 443 if scheme == "https" else 80
    path = (parsed.path or "").rstrip("/")
    if not path:
        path = "/v1"
    return f"{scheme}://{host}:{port}{path}"


def filter_hop_headers(
    headers: Mapping[str, str] | Iterable[tuple[str, str]],
    extra: set[str] | None = None,
) -> dict[str, str]:
    skip = HOP_BY_HOP if extra is None else HOP_BY_HOP | extra
    items = headers.items() if isinstance(headers, Mapping) else headers
    return {k: v for k, v in items if k.lower() not in skip}


def last_user_text(body: dict[str, Any]) -> str:
    messages = body.get("messages") or []
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return " ".join(parts).strip()
    return ""


def truncate(text: str, limit: int = 480) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class LoopBoundLock:
    """``asyncio.Lock`` created on the running loop and replaced if the loop changes.

    A module-level ``asyncio.Lock()`` binds on first contended acquire. A later
    loop (tests, another ``asyncio.run``, ASGI TestClient) then raises
    ``RuntimeError: is bound to a different event loop``.
    """

    __slots__ = ("_lock", "_loop")

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def get(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock = asyncio.Lock()
            self._loop = loop
        return self._lock
