"""Magistrala de evenimente (format AG-UI), câte una pe zonă.

Fiecare canal (un caz sau o pistă AML) are istoricul lui, abonați SSE și un fișier JSONL, ca un
client care se conectează târziu să vadă tot ce s-a întâmplat și ca demo-ul să poată fi rejucat.
Zonele nu împart magistrala: fiecare proces are instanța lui.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from versoml.contracts import AgentEvent, EventType, Zone
from versoml.secrets import redact

TICKER = "*"


def now() -> datetime:
    return datetime.now(timezone.utc)


class EventBus:
    def __init__(self, zone: Zone, log_dir: Path | None = None):
        self.zone = zone
        self.log_dir = log_dir
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
        self._history: dict[str, list[AgentEvent]] = defaultdict(list)
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq: dict[str, int] = defaultdict(int)
        self._ticker: deque[AgentEvent] = deque(maxlen=200)

    async def publish(self, channel: str, event: AgentEvent) -> AgentEvent:
        self._seq[channel] += 1
        event.seq = self._seq[channel]
        if event.message:
            event.message = redact(event.message)
        self._history[channel].append(event)
        self._ticker.append(event)
        if self.log_dir:
            path = self.log_dir / f"{channel}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
        for queue in list(self._subscribers[channel]) + list(self._subscribers[TICKER]):
            queue.put_nowait(event)
        return event

    def history(self, channel: str) -> list[AgentEvent]:
        if channel not in self._history and self.log_dir:
            path = self.log_dir / f"{channel}.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        self._history[channel].append(AgentEvent.model_validate_json(line))
                if self._history[channel]:
                    self._seq[channel] = self._history[channel][-1].seq
        return list(self._history.get(channel, []))

    def ticker(self, limit: int = 40) -> list[AgentEvent]:
        return list(self._ticker)[-limit:]

    def reset(self, channel: str) -> None:
        self._history.pop(channel, None)
        self._seq.pop(channel, None)
        if self.log_dir:
            (self.log_dir / f"{channel}.jsonl").unlink(missing_ok=True)

    async def subscribe(self, channel: str, replay: bool = True) -> AsyncIterator[AgentEvent]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[channel].add(queue)
        try:
            last = 0
            if replay and channel != TICKER:
                for event in self.history(channel):
                    last = event.seq
                    yield event
            while True:
                event = await queue.get()
                if channel != TICKER and event.seq <= last:
                    continue
                yield event
        finally:
            self._subscribers[channel].discard(queue)


class Emitter:
    """Scurtături pentru un agent care rulează pe un canal."""

    def __init__(self, bus: EventBus, channel: str, run_id: str, case_id: str):
        self.bus = bus
        self.channel = channel
        self.run_id = run_id
        self.case_id = case_id

    async def emit(self, type_: EventType, *, step: str | None = None, agent: str | None = None,
                   name: str | None = None, message: str | None = None, data: dict[str, Any] | None = None) -> None:
        event = AgentEvent(type=type_, zone=self.bus.zone, run_id=self.run_id, case_id=self.case_id, ts=now(),
                           step=step, agent=agent, name=name, message=message,
                           data=json.loads(json.dumps(data or {}, default=str)))
        await self.bus.publish(self.channel, event)

    async def run_started(self, message: str) -> None:
        await self.emit(EventType.RUN_STARTED, message=message)

    async def run_finished(self, message: str, data: dict | None = None) -> None:
        await self.emit(EventType.RUN_FINISHED, message=message, data=data)

    async def run_error(self, message: str) -> None:
        await self.emit(EventType.RUN_ERROR, message=message)

    async def step(self, step: str, agent: str, message: str, data: dict | None = None) -> None:
        await self.emit(EventType.STEP_STARTED, step=step, agent=agent, message=message, data=data)

    async def done(self, step: str, agent: str, message: str, data: dict | None = None) -> None:
        await self.emit(EventType.STEP_FINISHED, step=step, agent=agent, message=message, data=data)

    async def tool(self, step: str, agent: str, tool: str, args: dict, result: dict | None = None,
                   message: str | None = None) -> None:
        if result is None:
            await self.emit(EventType.TOOL_CALL_START, step=step, agent=agent, name=tool,
                            message=message or f"{agent} apelează {tool}", data={"tool": tool, "args": args})
        else:
            await self.emit(EventType.TOOL_CALL_END, step=step, agent=agent, name=tool,
                            message=message or f"{tool} a răspuns", data={"tool": tool, "args": args, "result": result})

    async def custom(self, name: str, message: str, data: dict | None = None, *, step: str | None = None,
                     agent: str | None = None) -> None:
        await self.emit(EventType.CUSTOM, name=name, step=step, agent=agent, message=message, data=data)

    async def text_start(self, step: str, agent: str, message_id: str) -> None:
        await self.emit(EventType.TEXT_MESSAGE_START, step=step, agent=agent, data={"message_id": message_id})

    async def text_delta(self, step: str, agent: str, message_id: str, delta: str) -> None:
        await self.emit(EventType.TEXT_MESSAGE_CONTENT, step=step, agent=agent, data={"message_id": message_id, "delta": delta})

    async def text_end(self, step: str, agent: str, message_id: str) -> None:
        await self.emit(EventType.TEXT_MESSAGE_END, step=step, agent=agent, data={"message_id": message_id})

    async def state(self, delta: dict) -> None:
        await self.emit(EventType.STATE_DELTA, data=delta)
