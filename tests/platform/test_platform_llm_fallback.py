"""When Bedrock is throttled or down, a live call moves on to the Claude API (only when an API key is set)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pydantic import BaseModel, SecretStr

from versoml.config import Settings
from versoml.shared.llm.client import LLMClient, Role, first_party_id


class Out(BaseModel):
    verdict: str


class RateLimitError(Exception):
    """Named like the SDK's 429 error: the router looks at the class name only."""


class APIConnectionError(Exception):
    pass


USAGE = SimpleNamespace(input_tokens=10, output_tokens=3, cache_read_input_tokens=0)


def _client(tmp_path, api_key: str | None) -> LLMClient:
    llm = LLMClient(Settings(versoml_var_dir=tmp_path / "var", versoml_llm_mode="auto",
                             anthropic_api_key=SecretStr(api_key) if api_key else None))
    llm.has_key = True
    return llm


def _wire(llm: LLMClient, bedrock_error: type[Exception] | None, seen: list[tuple[str, str]]):
    def parse_for(provider):
        async def parse(**kwargs):
            seen.append((provider, kwargs["model"]))
            if provider == "bedrock" and bedrock_error:
                raise bedrock_error("bedrock says no")
            return SimpleNamespace(parsed_output=Out(verdict=f"from {provider}"), usage=USAGE, stop_reason="end_turn")
        return parse

    llm._client_for = lambda provider: SimpleNamespace(messages=SimpleNamespace(parse=parse_for(provider)))


def test_model_ids_map_to_the_claude_api():
    assert first_party_id("anthropic.claude-opus-5-5") == "claude-opus-5-5"
    assert first_party_id("anthropic.claude-haiku-4-5") == "claude-haiku-4-5"


def test_throttled_bedrock_falls_back_to_the_claude_api(tmp_path):
    llm, seen = _client(tmp_path, "sk-ant-test"), []
    _wire(llm, RateLimitError, seen)
    out, info = asyncio.run(llm.structured(role=Role.OPUS, agent="t", system="s", user="u", schema=Out))
    assert out.verdict == "from anthropic" and info.provider == "anthropic" and info.model == "claude-opus-5-5"
    # every Bedrock model was tried first, then the same primary model on the Claude API
    assert [p for p, _ in seen].count("bedrock") == len(llm._candidates(Role.OPUS))
    assert seen[-1] == ("anthropic", "claude-opus-5-5")
    assert llm._live_failed_at is None          # throttling isn't an outage: Bedrock stays first next time


def test_bedrock_outage_skips_its_other_models_and_cools_down(tmp_path):
    llm, seen = _client(tmp_path, "sk-ant-test"), []
    _wire(llm, APIConnectionError, seen)
    out, info = asyncio.run(llm.structured(role=Role.SONNET, agent="t", system="s", user="u", schema=Out))
    assert info.provider == "anthropic" and [p for p, _ in seen] == ["bedrock", "anthropic"]
    assert llm._live_failed_at is not None and llm.mode == "live"     # still live, through the API
    seen.clear()
    asyncio.run(llm.structured(role=Role.SONNET, agent="t", system="s", user="u2", schema=Out))
    assert [p for p, _ in seen] == ["anthropic"]                        # Bedrock rests for 60 s


def test_without_an_api_key_nothing_changes(tmp_path):
    llm, seen = _client(tmp_path, None), []
    _wire(llm, None, seen)
    out, info = asyncio.run(llm.structured(role=Role.HAIKU, agent="t", system="s", user="u", schema=Out))
    assert info.provider == "bedrock" and all(p == "bedrock" for p, _ in seen)
    assert llm.describe()["fallback"] is None


def test_the_api_key_never_reaches_the_logs(tmp_path):
    from versoml.secrets import redact

    _client(tmp_path, "sk-ant-api03-SECRETVALUE")
    assert "SECRETVALUE" not in redact("failed with key sk-ant-api03-SECRETVALUE")
