"""Public limits: per caller and shared, on the API and on MCP over HTTP."""

from __future__ import annotations

import asyncio
import json

import pytest

from versoml.mcp_server.server import PublicLimits
from versoml.shared import ratelimit


@pytest.fixture(autouse=True)
def fresh_windows():
    ratelimit.reset()
    yield
    ratelimit.reset()


def test_per_caller_limit_then_window_slides():
    p = ratelimit.policies()["case_run"]
    for i in range(p.per_caller):
        assert ratelimit.check("case_run", "203.0.113.7", now=100.0 + i) is None
    refused = ratelimit.check("case_run", "203.0.113.7", now=110.0)
    assert refused and refused.retry_after > 0 and "from here" in refused.text()
    # someone else is not affected, and the first caller is let in again once the window has passed
    assert ratelimit.check("case_run", "198.51.100.2", now=110.0) is None
    assert ratelimit.check("case_run", "203.0.113.7", now=100.0 + p.caller_window_s + 1) is None


def test_local_calls_only_count_towards_the_shared_limit():
    p = ratelimit.policies()["kb_ask"]
    for i in range(p.global_limit):
        assert ratelimit.check("kb_ask", None, now=float(i)) is None
    refused = ratelimit.check("kb_ask", None, now=float(p.global_limit))
    assert refused and "shared limit" in refused.text()
    # a refusal by the shared limit gives the caller's hit back
    assert ratelimit.check("kb_ask", "203.0.113.9", now=float(p.global_limit)) is not None
    assert len(ratelimit._window._hits["kb_ask:203.0.113.9"]) == 0


def test_caller_is_the_first_forwarded_address():
    assert ratelimit.caller_of({"x-forwarded-for": "203.0.113.5, 76.76.21.21"}) == "203.0.113.5"
    assert ratelimit.caller_of({}) is None


def _call_mcp(app, body: dict, caller: str | None):
    sent: list[dict] = []
    headers = [(b"content-type", b"application/json")]
    if caller:
        headers.append((b"x-forwarded-for", caller.encode()))
    scope = {"type": "http", "method": "POST", "path": "/", "headers": headers}
    payload = json.dumps(body).encode()

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


class _Inner:
    router = None

    def __init__(self):
        self.bodies: list[bytes] = []

    async def __call__(self, scope, receive, send):
        self.bodies.append((await receive())["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def test_mcp_costly_tool_is_limited_per_caller_and_body_reaches_the_server():
    inner = _Inner()
    app = PublicLimits(inner)
    call = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "versoml_open_case", "arguments": {}}}
    limit = ratelimit.policies()["case_run"].per_caller
    for _ in range(limit):
        assert _call_mcp(app, call, "203.0.113.20")[0]["status"] == 200
    refused = _call_mcp(app, call, "203.0.113.20")
    assert refused[0]["status"] == 429 and (b"retry-after", refused[0]["headers"][-1][1]) in refused[0]["headers"]
    error = json.loads(refused[1]["body"])
    assert error["id"] == 7 and "Too many cases started" in error["error"]["message"]
    assert len(inner.bodies) == limit and json.loads(inner.bodies[0])["params"]["name"] == "versoml_open_case"
    # cheap tools from the same caller still go through
    cheap = {**call, "params": {"name": "versoml_case_status", "arguments": {"case_id": "CT-1"}}}
    assert _call_mcp(app, cheap, "203.0.113.20")[0]["status"] == 200


def test_mcp_refuses_oversized_requests():
    app = PublicLimits(_Inner())
    big = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "versoml_check_letter", "arguments": {"text": "x" * 70_000}}}
    assert _call_mcp(app, big, "203.0.113.30")[0]["status"] == 413
