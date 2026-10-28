"""Dioda: HMAC, schemă strictă, HoldSignal fără text liber, URL-uri din Settings, outbox."""

from __future__ import annotations

import json
import re
import typing
from datetime import datetime

import httpx
import pytest
from pydantic import ValidationError

from versoml.config import Settings
from versoml.contracts import DisputeFacts, HoldSignal
from versoml.shared.ledger import canonical_bytes
from versoml.shared.policy import PolicyDenied
from versoml.wall import (
    HOLD_ID_FIELDS,
    SIGNATURE_HEADER,
    Diode,
    DiodeSchemaError,
    DiodeSignatureError,
    DiodeSizeError,
    HttpTransport,
    InProcessTransport,
    free_text_fields,
    journal,
)


def _signed(diode: Diode, kind: str, data: dict) -> tuple[bytes, str]:
    body = canonical_bytes(data)
    return body, diode.sign(kind, body)  # semnat corect: atacatorul are chiar secretul


def test_facts_round_trip_in_process(diodes, facts):
    client, aml, to_aml, _ = diodes
    result = client.send_facts(facts)
    assert result["ok"] and result["status"] == 202 and result["url"].endswith("/diode/inbox")
    assert to_aml.facts == [facts]


def test_hold_round_trip_in_process(diodes, hold):
    _, aml, _, to_client = diodes
    result = aml.send_hold(hold)
    assert result["ok"] and to_client.holds == [hold]


def test_dispute_facts_with_a_note_field_is_rejected(diodes, facts):
    client, aml, _, _ = diodes
    with pytest.raises(ValidationError):
        DisputeFacts(**facts.model_dump(), note="clientul pare suspect")
    data = {**facts.model_dump(mode="json"), "note": "beneficiarul e investigat"}
    with pytest.raises(DiodeSchemaError) as err:
        client.send_facts(data)  # type: ignore[arg-type]
    assert err.value.code == "extra_field"
    with pytest.raises(DiodeSchemaError) as err:
        aml.receive_facts(*_signed(aml, "facts", data))
    assert err.value.code == "extra_field" and err.value.status == 422 and "note" in str(err.value)
    nested = facts.model_dump(mode="json")
    nested["beneficiary"]["note"] = "text ascuns"
    with pytest.raises(DiodeSchemaError):
        aml.receive_facts(*_signed(aml, "facts", nested))


def test_hold_signal_with_a_reason_field_is_rejected(diodes, hold):
    client, _, _, _ = diodes
    data = {**hold.model_dump(mode="json"), "reason": "Clientul e investigat pentru spălare de bani."}
    with pytest.raises(DiodeSchemaError) as err:
        client.receive_hold(*_signed(client, "hold", data))
    assert err.value.code == "extra_field" and "reason" in str(err.value)
    # motivul (textul liber) nu ajunge nici în jurnalul zidului
    assert all("spălare" not in json.dumps(e, ensure_ascii=False) for e in journal.recent(50))


def test_bad_signatures_are_rejected(diodes, settings, hold, facts):
    client, aml, _, _ = diodes
    body, signature = _signed(aml, "hold", hold.model_dump(mode="json"))
    tampered = body.replace(b'"hold":true', b'"hold":false')
    for raw, sig in ((tampered, signature), (body, None), (body, ""), (body, signature[3:]),
                     (body, "v1=" + "0" * 64)):
        with pytest.raises(DiodeSignatureError) as err:
            client.receive_hold(raw, sig)
        assert err.value.status == 401
    other = Diode(b"un-alt-secret-de-cel-putin-32-octeti!!", settings=settings)
    with pytest.raises(DiodeSignatureError):
        client.receive_hold(body, other.sign("hold", body))
    facts_body, facts_sig = _signed(aml, "facts", facts.model_dump(mode="json"))
    with pytest.raises(DiodeSignatureError):  # semnătura de „facts” nu merge pe ruta „hold”
        client.receive_hold(facts_body, facts_sig)


def test_hold_signal_schema_has_no_free_text():
    assert free_text_fields(HoldSignal) == []
    for name, info in HoldSignal.model_fields.items():
        assert info.annotation in (str, bool, datetime), name
        if info.annotation is str:
            pattern = re.compile(HOLD_ID_FIELDS[name])
            assert not pattern.match("Clientul e investigat de AML"), name
            assert not pattern.match("CT-2026-000123 suspect"), name
            assert all(ch not in pattern.pattern for ch in (r"\s", " ", ".*", r"\w+ "))
    assert not {"reason", "note", "text", "message", "comment", "detail"} & set(HoldSignal.model_fields)
    assert HoldSignal.model_config["extra"] == "forbid" and DisputeFacts.model_config["extra"] == "forbid"
    assert free_text_fields(DisputeFacts)  # DisputeFacts are text, dar merge doar spre AML


@pytest.mark.parametrize("field, value", [
    ("case_id", "CT-2026-000123 contul e investigat"),
    ("case_id", "spalare-de-bani"),
    ("approved_by", "Analistul AML a confirmat RTS"),
    ("approved_by", "ANALIST 07"),
])
def test_hold_ids_must_match_their_patterns(diodes, hold, field, value):
    client, aml, _, _ = diodes
    data = {**hold.model_dump(mode="json"), field: value}
    with pytest.raises(DiodeSchemaError):
        client.receive_hold(*_signed(client, "hold", data))
    with pytest.raises(DiodeSchemaError):
        aml.send_hold(data)  # type: ignore[arg-type]


def test_hold_needs_timezone_and_known_case(settings, hold):
    strict = Diode(settings=settings, known_case=lambda case_id: case_id == "CT-2026-000999")
    with pytest.raises(DiodeSchemaError) as err:
        strict.receive_hold(*_signed(strict, "hold", hold.model_dump(mode="json")))
    assert err.value.code == "unknown_case"
    naive = {**hold.model_dump(mode="json"), "approved_at": "2026-10-28T13:10:00"}
    with pytest.raises(DiodeSchemaError):
        strict.receive_hold(*_signed(strict, "hold", naive))


def test_victim_ref_must_be_a_pseudonym(diodes, facts):
    client, _, _, _ = diodes
    with pytest.raises(DiodeSchemaError) as err:
        client.send_facts(facts.model_copy(update={"victim_ref": "CLIENT-0042 Testescu Ana"}))
    assert "pseudonim" in str(err.value)


def test_duplicate_keys_oversize_and_garbage_are_rejected(diodes, hold):
    client, _, _, _ = diodes
    body = canonical_bytes(hold.model_dump(mode="json"))
    dup = body[:-1] + b',"hold":false}'
    with pytest.raises(DiodeSchemaError) as err:
        client.receive_hold(dup, client.sign("hold", dup))
    assert err.value.code == "duplicate_keys"
    big = b'{"x":"' + b"a" * 70_000 + b'"}'
    with pytest.raises(DiodeSizeError):
        client.receive_hold(big, client.sign("hold", big))
    junk = b"nu e json"
    with pytest.raises(DiodeSchemaError):
        client.receive_hold(junk, client.sign("hold", junk))
    kinds = {e["detail"]["code"] for e in journal.recent(10)}
    assert {"duplicate_keys", "too_large", "bad_json"} <= kinds


def test_urls_come_from_settings(tmp_path):
    default = Diode(b"x" * 32, settings=Settings(versoml_var_dir=tmp_path, versoml_aml_url=None, versoml_client_url=None))
    assert default.aml_url == "http://127.0.0.1:8001" and default.client_url == "http://127.0.0.1:8000"
    docker = Diode(b"x" * 32, settings=Settings(versoml_var_dir=tmp_path, versoml_aml_url="http://aml:8001/",
                                                versoml_client_url="http://client:8000"))
    assert docker.aml_url == "http://aml:8001" and docker.client_url == "http://client:8000"


def test_secret_from_settings_or_generated_key(tmp_path, settings, hold):
    shared = Settings(versoml_var_dir=tmp_path / "v2", versoml_diode_secret="secret-comun-pentru-dioda-demo-0001")
    a, b = Diode(settings=shared), Diode(settings=shared)
    assert b.receive_hold(*a.encode_hold(hold)) == hold
    first, second = Diode(settings=settings), Diode(settings=settings)
    assert (settings.keys_dir / "diode.key").exists()
    assert second.receive_hold(*first.encode_hold(hold)) == hold
    with pytest.raises(DiodeSignatureError):
        a.receive_hold(*first.encode_hold(hold))


def test_http_transport_posts_signed_canonical_json(settings, facts):
    receiver = Diode(settings=settings)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["header"] = request.headers.get(SIGNATURE_HEADER)
        receiver.receive_facts(request.content, request.headers.get(SIGNATURE_HEADER))
        return httpx.Response(202, json={"ok": True})

    sender = Diode(settings=settings, transport=HttpTransport(transport=httpx.MockTransport(handler)))
    result = sender.send_facts(facts)
    assert result["ok"] and seen["path"] == "/diode/inbox" and seen["header"].startswith("v1=")
    assert result["url"] == f"{settings.aml_url}/diode/inbox"


def test_network_failure_never_blocks_and_outbox_retries(tmp_path, settings, facts):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("zona AML e oprită")

    receiver = Diode(settings=settings)
    sender = Diode(settings=settings, transport=HttpTransport(transport=httpx.MockTransport(down)),
                   outbox_db=tmp_path / "client_zone.db")
    result = sender.send_facts(facts)
    assert not result["ok"] and result["status"] == 0
    assert [p["case_id"] for p in sender.pending()] == [facts.case_id]
    sender.transport = InProcessTransport(receiver=receiver)
    assert [r["ok"] for r in sender.flush()] == [True]
    assert sender.pending() == []
    assert sender.transport.facts == [facts]


def test_send_with_principal_is_checked_by_policy(diodes, facts, hold):
    client, aml, _, _ = diodes
    assert client.send_facts(facts, principal="Judecator/Colector")["ok"]
    with pytest.raises(PolicyDenied):
        client.send_facts(facts, principal="Investigator/OSINT")
    assert aml.send_hold(hold, principal="AnalistAML")["ok"]
    with pytest.raises(PolicyDenied):
        aml.send_hold(hold, principal="Investigator/RTS")


def test_hold_fields_are_only_ids_bools_and_a_date():
    hints = typing.get_type_hints(HoldSignal)
    assert set(hints) == {"case_id", "hold", "approved_by", "approved_at", "authority_notified"}
