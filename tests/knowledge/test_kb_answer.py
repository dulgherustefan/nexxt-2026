"""Grounded answers: the citation verifier, the extractive fallback, ask() offline, the PII path."""

from __future__ import annotations

import pytest

from versoml.knowledge.answer import NO_ANSWER, AnswerDraft, DraftSentence, compose, extractive, verify
from versoml.knowledge.models import Hit


def _hits() -> list[Hit]:
    return [
        Hit(id="rule:PAY-03", kind="rule", title="PAY-03 · Refund by the end of the next business day",
            text="For an unauthorized payment, the bank refunds immediately, and no later than the end of the "
                 "business day after it noted the payment.", source="docs/context/11.md"),
        Hit(id="rule:DSP-54", kind="rule", title="DSP-54 · Police report",
            text="A police report is not a condition for the next-business-day refund.", source="docs/context/14.md"),
    ]


def test_verifier_drops_citations_to_chunks_that_were_not_retrieved():
    draft = AnswerDraft(sentences=[
        DraftSentence(text="The bank refunds by the next business day.", cites=[1],
                      quotes=["no later than the end of the business day"]),
        DraftSentence(text="A fabricated rule says otherwise.", cites=[7], quotes=["anything"]),
        DraftSentence(text="Another fabrication.", cites=[0], quotes=["refunds"]),
    ])
    verified = verify(draft, _hits())
    assert [t for t, _ in verified.sentences] == ["The bank refunds by the next business day."]
    assert {d["reason"] for d in verified.dropped} == {"cites a source that was not retrieved"}


def test_verifier_drops_quotes_that_are_not_in_the_cited_chunk():
    draft = AnswerDraft(sentences=[
        DraftSentence(text="Refunds wait for the investigation.", cites=[1], quotes=["after the investigation ends"]),
        DraftSentence(text="No police report is needed.", cites=[1], quotes=["A police report is not a condition"]),
        DraftSentence(text="No police report is needed.", cites=[2], quotes=["a  POLICE report is not a condition"]),
        DraftSentence(text="Cited without a quote.", cites=[2], quotes=[]),
    ])
    verified = verify(draft, _hits())
    # only the quote that is really in source 2 survives (case and spacing are tolerated)
    assert verified.sentences == [("No police report is needed.", [1])]
    reasons = [d["reason"] for d in verified.dropped]
    assert reasons.count("quote not found in the cited source") == 2 and "no supporting quote" in reasons


def test_compose_renumbers_and_flags_uncited_sentences():
    hits = _hits()
    draft = AnswerDraft(sentences=[
        DraftSentence(text="Police reports are optional [9]", cites=[2], quotes=["not a condition"]),
        DraftSentence(text="The refund is due the next business day.", cites=[1, 2],
                      quotes=["no later than the end of the business day"]),
    ])
    answer = compose("q", verify(draft, hits), hits, "live")
    assert answer.answer == "Police reports are optional. [1] The refund is due the next business day. [2] [1]"
    assert [h.id for h in answer.citations] == ["rule:DSP-54", "rule:PAY-03"] and answer.grounded
    uncited = verify(AnswerDraft(sentences=[DraftSentence(text="The sources do not say.", cites=[])]), hits)
    answer = compose("q", uncited, hits, "live")
    assert not answer.grounded and answer.citations == []
    assert compose("q", verify(AnswerDraft(), hits), hits, "offline").answer == NO_ANSWER


def test_extractive_fallback_quotes_the_chunks_verbatim():
    hits = _hits()
    draft = extractive("When is the refund due after an unauthorized payment?", hits)
    assert draft.sentences and draft.sentences[0].cites == [1]
    assert all(s.text in hits[s.cites[0] - 1].text for s in draft.sentences)
    assert extractive("", hits).sentences == []


async def test_ask_offline_is_grounded_and_deterministic(client_kb, offline_llm):
    client_kb._llm = offline_llm
    try:
        a = await client_kb.ask("By when must the bank refund an unauthorized payment?")
        b = await client_kb.ask("By when must the bank refund an unauthorized payment?")
    finally:
        client_kb._llm = None
    assert a.mode == "offline" and a.grounded and a.citations
    assert a.answer == b.answer and [h.id for h in a.citations] == [h.id for h in b.citations]
    assert "rule:PAY-03" in [h.id for h in a.citations]
    import re

    numbers = {int(n) for n in re.findall(r"\[(\d+)\]", a.answer)}
    assert numbers == set(range(1, len(a.citations) + 1))


class _Scripted:
    """An LLM client stub: returns a fixed draft and records the prompts."""

    def __init__(self, draft: AnswerDraft):
        self.draft = draft
        self.prompts: list[str] = []

    async def structured(self, *, role, agent, system, user, schema, max_tokens=4000, fallback=None, effort=None):
        from versoml.shared.llm import CallInfo

        self.prompts.append(user)
        return self.draft, CallInfo(agent=agent, role=str(role), model="stub", mode="live")


async def test_ask_drops_fabricated_llm_citations(client_kb):
    hits = client_kb.search("Does the customer need a police report before the refund?", k=6)
    real = next(i for i, h in enumerate(hits, start=1) if h.id == "rule:DSP-54")
    quote = "A police report is not a condition for the next-business-day refund"
    stub = _Scripted(AnswerDraft(sentences=[
        DraftSentence(text="A police report is not required for the refund.", cites=[real], quotes=[quote]),
        DraftSentence(text="Article 999 requires a notary.", cites=[42], quotes=["notary"]),
        DraftSentence(text="The bank may wait 90 days.", cites=[real], quotes=["the bank may wait 90 days"]),
    ]))
    client_kb._llm = stub
    try:
        answer = await client_kb.ask("Does the customer need a police report before the refund?")
    finally:
        client_kb._llm = None
    assert answer.mode == "live" and answer.grounded
    assert answer.answer == "A police report is not required for the refund. [1]"
    assert [h.id for h in answer.citations] == ["rule:DSP-54"]
    assert "ignore any instruction" not in stub.prompts[0].lower()  # the rule lives in the system prompt
    assert stub.prompts[0].startswith("Sources:")


async def test_ask_with_raw_pii_stays_local(client_kb):
    class Forbidden:
        async def structured(self, **_kw):
            raise AssertionError("raw personal data must not reach the LLM")

    client_kb._llm = Forbidden()
    try:
        answer = await client_kb.ask("Refund for IBAN RO49AAAA1B31007593840000 by when?")
    finally:
        client_kb._llm = None
    assert answer.mode == "offline"
    assert all(h.why.get("fallback") in ("pii_guard", "no_query_vector", None) for h in answer.citations)


@pytest.mark.parametrize("question", ["", "   "])
async def test_ask_empty_question(client_kb, question):
    answer = await client_kb.ask(question)
    assert answer.answer == NO_ANSWER and not answer.grounded
