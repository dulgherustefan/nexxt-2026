"""Clientul LLM: Claude pe Bedrock (Mantle), rutare pe roluri, ieșiri structurate, live/replay/offline.

- live: apel real; răspunsul se înregistrează pentru replay.
- replay: răspunsul înregistrat pentru aceeași intrare (demo fără rețea, rezultate stabile).
- offline: funcția deterministă dată de apelant (de obicei reguli + șabloane).
Înaintea fiecărui apel live, textul trece prin garda de date personale: nimic brut nu pleacă spre model.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from pydantic import BaseModel

from versoml.config import Settings, get_settings
from versoml.secrets import install_log_redaction, load_bedrock_key, redact

log = logging.getLogger("versoml.llm")
T = TypeVar("T", bound=BaseModel)

# USD per milion de tokeni (intrare, ieșire): estimare pentru panoul de cost
PRICES = {
    "opus-5-5": (4.0, 20.0),
    "opus-4-8": (5.0, 25.0),
    "sonnet-5": (2.0, 10.0),
    "haiku-4-5": (1.0, 5.0),
}


import re

_VOLATILE = [
    (re.compile(r"\bCT-\d{4}-\d{3,8}\b"), "CT-X"),
    (re.compile(r"\b(?:A?RUN)-[a-f0-9]{8}\b"), "RUN-X"),
    (re.compile(r"\bPL-[A-F0-9]{6}\b"), "PL-X"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"), "<TS>"),
    (re.compile(r"\b\d{2}\.\d{2}\.\d{4}(?: \d{2}:\d{2})?\b"), "<DATA>"),
    # English dates in prompts: "29 Oct 2026, 23:59", "29 Oct, 23:59", "29 October 2026"
    (re.compile(r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?: \d{4})?(?:,? \d{2}:\d{2})?\b"),
     "<DATA>"),
    (re.compile(r"\b[a-f0-9]{16,64}\b"), "<HASH>"),
]


class Role(str, Enum):
    OPUS = "opus"      # Procuror, Avocatul nevinovăției, RTS
    SONNET = "sonnet"  # colectori, Avocat, OSINT, scrisori
    HAIKU = "haiku"    # LLM-ul izolat: extragere din text neîncrezut


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class CallInfo:
    agent: str
    role: str
    model: str
    mode: str
    ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    key: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Usage:
    calls: int = 0
    by_mode: dict[str, int] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def _price_key(model: str) -> str:
    return model.replace("anthropic.claude-", "")


def _cost(model: str, usage: Any) -> float:
    pin, pout = PRICES.get(_price_key(model), (3.0, 15.0))
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return round(inp / 1e6 * pin + out / 1e6 * pout, 6)


class ReplayStore:
    """Recorded answers, key = hash(role, system, input, schema), in JSONL files.

    `path` is the only file written (by live runs: var/replay/replay.jsonl, outside git). `read_also` are
    read-only files, such as the recordings committed in versoml/data/replay. When a key appears more than
    once, the first recording wins (the read-only files are read first).
    """

    def __init__(self, path: Path | str, read_also: Iterable[Path | str] = ()):
        self.path = Path(path)
        self.read_paths = [Path(p) for p in read_also if Path(p) != self.path]
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        for source in (*self.read_paths, self.path):
            self._load(source)

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                    self._data.setdefault(row["key"], row)
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

    def get(self, key: str) -> dict | None:
        return self._data.get(key)

    def put(self, key: str, row: dict) -> None:
        with self._lock:
            if key in self._data:
                return
            row = {"key": key, **row}
            self._data[key] = row
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self._data)


def _guard(payload: str) -> None:
    """Garda de date personale (PrivacyProxy). Dacă modulul lipsește, nu blocăm, dar logăm."""
    try:
        from versoml.shared.privacy import assert_llm_safe
    except ImportError:  # modulul de confidențialitate nu e încă disponibil
        return
    assert_llm_safe(payload)


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        install_log_redaction()
        self.has_key = load_bedrock_key()
        # new recordings go under var/ (never into git); replay also reads the committed recordings
        self.replay = ReplayStore(self.settings.replay_record_path,
                                  read_also=[self.settings.replay_dir / "replay.jsonl"])
        self.usage = _Usage()
        self._client = None
        self._live_failed_at: float | None = None
        self.calls: list[CallInfo] = []

    # ------------------------------------------------------------ configurare

    @property
    def mode(self) -> str:
        configured = self.settings.versoml_llm_mode
        if configured != "auto":
            return configured
        if not self.has_key:
            return "replay"
        # după o eroare de rețea/acces, revenim la live abia după 60 s
        if self._live_failed_at and time.time() - self._live_failed_at < 60:
            return "replay"
        return "live"

    def model_for(self, role: Role | str) -> str:
        role = Role(role)
        return {
            Role.OPUS: self.settings.model_opus,
            Role.SONNET: self.settings.model_sonnet,
            Role.HAIKU: self.settings.model_haiku,
        }[role]

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "region": self.settings.aws_region,
            "models": {r.value: self.model_for(r) for r in Role},
            "live_ok": self.has_key and self._live_failed_at is None,
            "replay_entries": len(self.replay),
            "usage": asdict(self.usage),
        }

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropicBedrockMantle

            self._client = AsyncAnthropicBedrockMantle(
                aws_region=self.settings.aws_region, max_retries=2, timeout=120
            )
        return self._client

    @staticmethod
    def _normalize(text: str) -> str:
        """Scoate ce se schimbă de la o rulare la alta (ID de caz, ore, hash-uri), ca replay-ul să se potrivească."""
        for pattern, repl in _VOLATILE:
            text = pattern.sub(repl, text)
        return text

    @classmethod
    def _key(cls, role: str, system: str, user: str, schema: str) -> str:
        blob = json.dumps([role, system, cls._normalize(user), schema], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _supports_effort(self, model: str) -> bool:
        return "haiku-4-5" not in model

    def _record(self, info: CallInfo) -> CallInfo:
        self.usage.calls += 1
        self.usage.by_mode[info.mode] = self.usage.by_mode.get(info.mode, 0) + 1
        self.usage.input_tokens += info.input_tokens
        self.usage.output_tokens += info.output_tokens
        self.usage.cost_usd = round(self.usage.cost_usd + info.cost_usd, 6)
        self.calls.append(info)
        self.calls = self.calls[-500:]
        return info

    def _candidates(self, role: Role) -> list[str]:
        primary = self.model_for(role)
        rest = [m for m in self.settings.fallback_models if m != primary]
        return [primary, *rest]

    # ------------------------------------------------------------ ieșiri structurate

    async def structured(
        self,
        *,
        role: Role | str,
        agent: str,
        system: str,
        user: str,
        schema: type[T],
        effort: str | None = None,
        max_tokens: int = 4000,
        fallback: Callable[[], T] | None = None,
    ) -> tuple[T, CallInfo]:
        role = Role(role)
        key = self._key(role.value, system, user, schema.__name__)
        mode = self.mode

        if mode == "live":
            _guard(user)
            last_error = None
            for model in self._candidates(role):
                started = time.perf_counter()
                try:
                    kwargs: dict[str, Any] = {}
                    if effort and self._supports_effort(model):
                        kwargs["output_config"] = {"effort": effort}
                    response = await self._get_client().messages.parse(
                        model=model,
                        max_tokens=max_tokens,
                        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                        messages=[{"role": "user", "content": user}],
                        output_format=schema,
                        **kwargs,
                    )
                    parsed = response.parsed_output
                    if parsed is None:
                        raise LLMUnavailable(f"the response has no valid JSON (stop_reason={response.stop_reason})")
                    usage = response.usage
                    info = CallInfo(
                        agent=agent, role=role.value, model=model, mode="live",
                        ms=round((time.perf_counter() - started) * 1000),
                        input_tokens=usage.input_tokens or 0, output_tokens=usage.output_tokens or 0,
                        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                        cost_usd=_cost(model, usage), key=key,
                    )
                    self.replay.put(key, {"agent": agent, "role": role.value, "model": model,
                                          "schema": schema.__name__, "output": parsed.model_dump(mode="json")})
                    return parsed, self._record(info)
                except Exception as exc:  # noqa: BLE001 - încercăm modelul următor, apoi replay/offline
                    if type(exc).__name__ == "RawPIIError":
                        raise
                    last_error = redact(f"{type(exc).__name__}: {exc}")[:300]
                    log.warning("LLM call %s on %s failed: %s", agent, model, last_error)
                    if type(exc).__name__ in ("APIConnectionError", "AuthenticationError", "PermissionDeniedError"):
                        self._live_failed_at = time.time()
                        break
            mode = "replay"
        else:
            last_error = None

        if mode == "replay":
            row = self.replay.get(key)
            if row:
                info = CallInfo(agent=agent, role=role.value, model=row.get("model", ""), mode="replay", key=key)
                return schema.model_validate(row["output"]), self._record(info)

        if fallback is None:
            raise LLMUnavailable(last_error or "no LLM available and no deterministic fallback")
        info = CallInfo(agent=agent, role=role.value, model="determinist", mode="offline", error=last_error, key=key)
        return fallback(), self._record(info)

    # ------------------------------------------------------------ text liber, cu streaming

    async def text(
        self,
        *,
        role: Role | str,
        agent: str,
        system: str,
        user: str,
        effort: str | None = None,
        max_tokens: int = 3000,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        fallback: Callable[[], str] | None = None,
    ) -> tuple[str, CallInfo]:
        role = Role(role)
        key = self._key(role.value, system, user, "text")
        mode = self.mode
        last_error = None

        if mode == "live":
            _guard(user)
            for model in self._candidates(role):
                started = time.perf_counter()
                try:
                    kwargs: dict[str, Any] = {}
                    if effort and self._supports_effort(model):
                        kwargs["output_config"] = {"effort": effort}
                    chunks: list[str] = []
                    async with self._get_client().messages.stream(
                        model=model,
                        max_tokens=max_tokens,
                        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                        messages=[{"role": "user", "content": user}],
                        **kwargs,
                    ) as stream:
                        async for delta in stream.text_stream:
                            chunks.append(delta)
                            if on_delta:
                                await on_delta(delta)
                        final = await stream.get_final_message()
                    text = "".join(chunks).strip()
                    info = CallInfo(
                        agent=agent, role=role.value, model=model, mode="live",
                        ms=round((time.perf_counter() - started) * 1000),
                        input_tokens=final.usage.input_tokens or 0, output_tokens=final.usage.output_tokens or 0,
                        cost_usd=_cost(model, final.usage), key=key,
                    )
                    self.replay.put(key, {"agent": agent, "role": role.value, "model": model,
                                          "schema": "text", "output": text})
                    return text, self._record(info)
                except Exception as exc:  # noqa: BLE001
                    if type(exc).__name__ == "RawPIIError":
                        raise
                    last_error = redact(f"{type(exc).__name__}: {exc}")[:300]
                    log.warning("LLM text call %s on %s failed: %s", agent, model, last_error)
                    if type(exc).__name__ in ("APIConnectionError", "AuthenticationError", "PermissionDeniedError"):
                        self._live_failed_at = time.time()
                        break
            mode = "replay"

        if mode == "replay":
            row = self.replay.get(key)
            if row:
                text = row["output"]
                if on_delta:
                    for i in range(0, len(text), 48):
                        await on_delta(text[i:i + 48])
                        await asyncio.sleep(0.01)
                return text, self._record(CallInfo(agent=agent, role=role.value, model=row.get("model", ""),
                                                   mode="replay", key=key))

        if fallback is None:
            raise LLMUnavailable(last_error or "no LLM available and no deterministic fallback")
        text = fallback()
        if on_delta:
            for i in range(0, len(text), 64):
                await on_delta(text[i:i + 64])
                await asyncio.sleep(0.005)
        return text, self._record(CallInfo(agent=agent, role=role.value, model="determinist", mode="offline",
                                           error=last_error, key=key))

    # ------------------------------------------------------------ bucla de tool-uri

    async def tool_loop(
        self,
        *,
        role: Role | str,
        agent: str,
        system: str,
        user: str,
        tools: list[dict],
        execute: Callable[[str, dict], Awaitable[dict]],
        max_turns: int = 5,
        effort: str | None = "medium",
        fallback_plan: Callable[[], list[tuple[str, dict]]] | None = None,
        on_tool: Callable[[str, dict, dict], Awaitable[None]] | None = None,
    ) -> tuple[str, list[dict], CallInfo]:
        """Modelul alege tool-urile (în paralel); `execute` aplică politica Cedar și rulează tool-ul.

        Fără LLM, `fallback_plan` dă lista deterministă de apeluri. Rezultatele tool-urilor sunt date
        neîncrezute: intră înapoi în model doar ca `tool_result`, niciodată ca instrucțiuni.
        """
        role = Role(role)
        transcript: list[dict] = []
        mode = self.mode
        if mode == "live":
            _guard(user)
            model = self.model_for(role)
            started = time.perf_counter()
            messages: list[dict] = [{"role": "user", "content": user}]
            total_in = total_out = 0
            nudged = False
            try:
                for _ in range(max_turns + 1):
                    kwargs: dict[str, Any] = {}
                    if effort and self._supports_effort(model):
                        kwargs["output_config"] = {"effort": effort}
                    response = await self._get_client().messages.create(
                        model=model, max_tokens=4000,
                        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                        tools=tools, messages=messages, **kwargs,
                    )
                    total_in += response.usage.input_tokens or 0
                    total_out += response.usage.output_tokens or 0
                    messages.append({"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in response.content]})
                    calls = [b for b in response.content if b.type == "tool_use"]
                    if not calls and not transcript and not nudged:
                        # modelul a anunțat un plan fără să cheme nimic: îi cerem o dată să execute
                        nudged = True
                        messages.append({"role": "user", "content": "Run the checks now by calling the tools."})
                        continue
                    if response.stop_reason != "tool_use" or not calls:
                        text = "".join(getattr(b, "text", "") for b in response.content).strip()
                        if not transcript:
                            break  # niciun tool chemat: cădem pe planul determinist, ca dosarul să aibă probe
                        cost = round(total_in / 1e6 * PRICES.get(_price_key(model), (3, 15))[0]
                                     + total_out / 1e6 * PRICES.get(_price_key(model), (3, 15))[1], 6)
                        info = CallInfo(agent=agent, role=role.value, model=model, mode="live",
                                        ms=round((time.perf_counter() - started) * 1000),
                                        input_tokens=total_in, output_tokens=total_out, cost_usd=cost)
                        return text, transcript, self._record(info)
                    results = await asyncio.gather(*(execute(c.name, dict(c.input)) for c in calls))
                    blocks = []
                    for call, result in zip(calls, results):
                        transcript.append({"tool": call.name, "input": dict(call.input), "result": result})
                        if on_tool:
                            await on_tool(call.name, dict(call.input), result)
                        blocks.append({"type": "tool_result", "tool_use_id": call.id,
                                       "content": json.dumps(result, ensure_ascii=False, default=str)[:6000]})
                    messages.append({"role": "user", "content": blocks})
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ == "RawPIIError":
                    raise
                log.warning("tool_loop %s failed: %s", agent, redact(str(exc))[:200])
                if type(exc).__name__ in ("APIConnectionError", "AuthenticationError", "PermissionDeniedError"):
                    self._live_failed_at = time.time()

        if fallback_plan is None:
            raise LLMUnavailable("no LLM available and no deterministic plan")
        for name, args in fallback_plan():
            result = await execute(name, args)
            transcript.append({"tool": name, "input": args, "result": result})
            if on_tool:
                await on_tool(name, args, result)
        info = CallInfo(agent=agent, role=role.value, model="determinist", mode="offline")
        return "", transcript, self._record(info)


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
