"""Limits for public access: the demo is open on a tunnel, and every case run or knowledge answer costs Bedrock calls.

Two kinds of limit, both sliding windows kept in memory (one process per zone, so no shared store is needed):

- per caller: the first address in X-Forwarded-For (Vercel and ngrok both set it). A request without it comes from
  this machine (the console on localhost, or the MCP tools calling the API) and only counts towards the global limit;
- global: everything that reaches Bedrock, from any entry point, so the account's quota holds whoever is calling.
"""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from versoml.config import get_settings


@dataclass(frozen=True)
class Policy:
    name: str
    per_caller: int
    caller_window_s: int
    global_limit: int
    global_window_s: int
    what: str


class _Window:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def take(self, key: str, limit: int, window_s: int, now: float) -> float | None:
        """Records a hit and returns None, or returns how many seconds until the next hit is allowed."""
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_s:
                hits.popleft()
            if len(hits) >= limit:
                return max(1.0, hits[0] + window_s - now)
            hits.append(now)
            return None

    def give_back(self, key: str) -> None:
        with self._lock:
            if self._hits.get(key):
                self._hits[key].pop()

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_window = _Window()


def policies() -> dict[str, Policy]:
    s = get_settings()
    return {
        "case_run": Policy("case_run", s.versoml_case_runs_per_caller, 600, s.versoml_case_runs_per_hour, 3600,
                           "cases started"),
        "kb_ask": Policy("kb_ask", s.versoml_kb_asks_per_caller, 600, s.versoml_kb_asks_per_hour, 3600, "questions"),
        "web_lookup": Policy("web_lookup", 10, 600, 120, 3600, "domain lookups"),
        "mcp_call": Policy("mcp_call", s.versoml_mcp_calls_per_caller, 60, 100_000, 3600, "MCP requests"),
    }


@dataclass(frozen=True)
class Refusal:
    policy: str
    retry_after: int
    message: str

    def text(self) -> str:
        minutes = math.ceil(self.retry_after / 60)
        wait = f"{self.retry_after} seconds" if self.retry_after < 90 else f"{minutes} minutes"
        return f"{self.message}. Try again in {wait}."


def check(policy_name: str, caller: str | None, now: float | None = None) -> Refusal | None:
    """One hit for `caller` under `policy_name`. A refusal on either limit leaves the other one untouched."""
    p = policies()[policy_name]
    now = time.monotonic() if now is None else now
    if caller:
        wait = _window.take(f"{p.name}:{caller}", p.per_caller, p.caller_window_s, now)
        if wait is not None:
            return Refusal(p.name, math.ceil(wait),
                           f"Too many {p.what} from here. Each person gets a few, so the demo stays up for everyone")
    wait = _window.take(f"{p.name}:*", p.global_limit, p.global_window_s, now)
    if wait is not None:
        if caller:
            _window.give_back(f"{p.name}:{caller}")
        return Refusal(p.name, math.ceil(wait), f"The demo has reached its shared limit on {p.what}")
    return None


def caller_of(headers) -> str | None:
    """The caller's address from X-Forwarded-For, or None for a request made on this machine."""
    forwarded = headers.get("x-forwarded-for") or ""
    first = forwarded.split(",")[0].strip()
    return first or None


def reset() -> None:
    """For tests."""
    _window.clear()
