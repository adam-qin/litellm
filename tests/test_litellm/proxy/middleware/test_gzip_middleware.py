"""ASGI regression tests for dashboard-only off-thread gzip compression."""

import asyncio
import gzip
import importlib.util
import threading
from pathlib import Path

import pytest
from starlette.responses import Response, StreamingResponse
from starlette.types import Message, Scope

# Load the standalone ASGI middleware without importing the entire proxy stack.
# This keeps the unit tests runnable in a minimal Starlette environment.
module_path = Path(__file__).resolve().parents[4] / "litellm/proxy/middleware/gzip_middleware.py"
spec = importlib.util.spec_from_file_location("xhub_gzip_middleware", module_path)
assert spec is not None and spec.loader is not None
gzip_middleware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gzip_middleware)
GZipBufferedResponseMiddleware = gzip_middleware.GZipBufferedResponseMiddleware


async def _messages(path: str, body: bytes, *, stream: bool = False, method: str = "GET"):
    async def app(scope, receive, send):
        if stream:
            async def chunks():
                yield body[:500]
                yield body[500:]
            response = StreamingResponse(chunks())
        else:
            response = Response(body)
        await response(scope, receive, send)

    scope: Scope = {
        "type": "http", "method": method, "path": path, "root_path": "",
        "query_string": b"", "headers": [(b"accept-encoding", b"gzip")],
    }
    sent: list[Message] = []
    first_request = True
    disconnected = asyncio.Event()

    async def receive():
        nonlocal first_request
        if first_request:
            first_request = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message):
        sent.append(message)

    await GZipBufferedResponseMiddleware(app)(scope, receive, send)
    return sent


def _headers(messages):
    return dict(messages[0]["headers"])


def _body(messages):
    return b"".join(m.get("body", b"") for m in messages[1:])


@pytest.mark.asyncio
async def test_dashboard_compresses_off_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    real_compress = gzip.compress
    observed = []

    def compress(data, level):
        observed.append(threading.get_ident())
        return real_compress(data, level)

    monkeypatch.setattr(gzip_middleware.gzip, "compress", compress)
    body = b"a" * 4096
    messages = await _messages("/user/daily/activity/aggregated", body)
    assert _headers(messages)[b"content-encoding"] == b"gzip"
    assert _headers(messages)[b"vary"] == b"Accept-Encoding"
    assert gzip.decompress(_body(messages)) == body
    assert observed and observed[0] != loop_thread


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method", [
    ("/v1/chat/completions", "POST"),
    ("/v1/embeddings", "POST"),
    ("/user/daily/activity/aggregated", "POST"),
    ("/openapi.json", "GET"),
])
async def test_inference_and_non_dashboard_requests_bypass_gzip(path, method):
    body = b"x" * 4096
    messages = await _messages(path, body, method=method)
    assert b"content-encoding" not in _headers(messages)
    assert _body(messages) == body


@pytest.mark.asyncio
async def test_dashboard_stream_is_not_buffered_or_compressed():
    body = b"z" * 1200
    messages = await _messages("/user/daily/activity/aggregated", body, stream=True)
    assert b"content-encoding" not in _headers(messages)
    assert _body(messages) == body
    assert len([m for m in messages if m.get("body")]) == 2
