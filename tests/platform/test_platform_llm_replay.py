"""LLM recordings: live runs write to var/replay (outside git); replay reads the committed file and var."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import versoml.config as config
from versoml.config import Settings
from versoml.shared.llm.client import LLMClient, ReplayStore, Role


class Out(BaseModel):
    verdict: str


def _row(key: str, verdict: str) -> dict:
    return {"key": key, "agent": "t", "role": "haiku", "model": "anthropic.claude-haiku-4-5", "schema": "Out",
            "output": {"verdict": verdict}}


@pytest.fixture
def committed(tmp_path, monkeypatch):
    """A stand-in for versoml/data/replay/replay.jsonl, so the test never touches the real file."""
    package = tmp_path / "package"
    monkeypatch.setattr(config, "PACKAGE_DIR", package)
    path = package / "data" / "replay" / "replay.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_row(LLMClient._key("haiku", "s", "old input", "Out"), "NU_SE_APLICA_T1")) + "\n",
                    encoding="utf-8")
    return path


def test_replay_key_ignores_english_dates():
    a = LLMClient._key("haiku", "s", "Case CT-2026-481516, refund by 29 Oct 2026, 23:59 (notified 28 Oct, 14:05)", "X")
    b = LLMClient._key("haiku", "s", "Case CT-2026-234200, refund by 3 Nov 2026, 23:59 (notified 2 Nov, 09:00)", "X")
    c = LLMClient._key("haiku", "s", "Case CT-2026-234200, refund by 3 Nov 2026, 23:59 (notified 2 Nov, 09:00) now", "X")
    assert a == b and a != c


def test_replay_key_carries_the_case_scope():
    # two complaints that normalize to the same text never share a recording; a rerun of the same one still does
    a = LLMClient._key("haiku", "s", "Case CT-2026-481516, paid on 29 Oct 2026", "X", scope="c0ffee00c0ffee00")
    b = LLMClient._key("haiku", "s", "Case CT-2026-234200, paid on 3 Nov 2026", "X", scope="deadbeefdeadbeef")
    again = LLMClient._key("haiku", "s", "Case CT-2026-999999, paid on 4 Nov 2026", "X", scope="c0ffee00c0ffee00")
    assert a != b and a == again
    assert LLMClient._key("haiku", "s", "x", "X", scope="") == LLMClient._key("haiku", "s", "x", "X")


def test_a_recording_for_another_case_is_not_replayed(tmp_path, committed):
    replay = LLMClient(Settings(versoml_var_dir=tmp_path / "var", versoml_llm_mode="replay"))
    got, info = asyncio.run(replay.structured(role=Role.HAIKU, agent="t", system="s", user="old input", schema=Out,
                                              scope="c0ffee00c0ffee00", fallback=lambda: Out(verdict="FALLBACK")))
    assert (got.verdict, info.mode) == ("FALLBACK", "offline")


def test_store_reads_every_file_and_writes_only_its_own(tmp_path):
    committed = tmp_path / "committed.jsonl"
    committed.write_text(json.dumps(_row("k1", "A")) + "\n", encoding="utf-8")
    before = committed.read_bytes()
    own = tmp_path / "var" / "replay" / "replay.jsonl"
    store = ReplayStore(own, read_also=[committed])
    assert store.get("k1")["output"] == {"verdict": "A"}
    store.put("k1", {"output": {"verdict": "B"}})          # already recorded: nothing new is written
    store.put("k2", {"output": {"verdict": "C"}})
    assert committed.read_bytes() == before
    assert [json.loads(line)["key"] for line in own.read_text(encoding="utf-8").splitlines()] == ["k2"]
    again = ReplayStore(own, read_also=[committed])
    assert len(again) == 2 and again.get("k1")["output"] == {"verdict": "A"} and again.get("k2")["output"] == {"verdict": "C"}


def test_live_answers_are_recorded_under_var_and_replayed_with_the_committed_ones(tmp_path, committed, monkeypatch):
    before = committed.read_bytes()
    live = LLMClient(Settings(versoml_var_dir=tmp_path / "var", versoml_llm_mode="live"))
    assert live.replay.path == tmp_path / "var" / "replay" / "replay.jsonl"
    usage = SimpleNamespace(input_tokens=12, output_tokens=4, cache_read_input_tokens=0)

    async def parse(**kwargs):
        return SimpleNamespace(parsed_output=Out(verdict="RAMBURSEAZA"), usage=usage, stop_reason="end_turn")

    monkeypatch.setattr(live, "_get_client", lambda: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    out, info = asyncio.run(live.structured(role=Role.HAIKU, agent="t", system="s", user="new input", schema=Out))
    assert out.verdict == "RAMBURSEAZA" and info.mode == "live"
    assert committed.read_bytes() == before                 # the git-tracked file is never written
    recorded = [json.loads(line) for line in live.replay.path.read_text(encoding="utf-8").splitlines()]
    assert [r["key"] for r in recorded] == [LLMClient._key("haiku", "s", "new input", "Out")]

    replay = LLMClient(Settings(versoml_var_dir=tmp_path / "var", versoml_llm_mode="replay"))
    for user, verdict in (("new input", "RAMBURSEAZA"), ("old input", "NU_SE_APLICA_T1")):
        got, got_info = asyncio.run(replay.structured(role=Role.HAIKU, agent="t", system="s", user=user, schema=Out))
        assert (got.verdict, got_info.mode) == (verdict, "replay")
    assert replay.describe()["replay_entries"] == 2
