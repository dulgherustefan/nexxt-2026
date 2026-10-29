"""Registrul de probe: JSON canonic, lanț, Merkle RFC 6962, sigiliu Ed25519, QR, tamper, dosar."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from versoml.contracts import Labels, Sink, Zone
from versoml.shared.ledger import (
    LabelError,
    Ledger,
    LedgerError,
    canonical_json,
    case_genesis,
    hash_obj,
    inclusion_path,
    leaf_hash,
    merkle_root,
    prefixed_hash,
    root_from_leaves,
    verify_dossier,
    verify_inclusion,
    verify_proof,
)
from versoml.shared.ledger.keys import verify_signature

CASE = "CT-2026-000123"


def _fill(ledger: Ledger, case_id: str = CASE, n: int = 5) -> list:
    facts = []
    for i in range(n):
        facts.append(ledger.append(
            case_id, "sca.auth_event", "sca-logs.get_auth_events", {"tx_id": f"TX-{i}"},
            {"device_new": True, "seconds_after_click": 118 + i, "amount": 3200.0, "score": 0.93},
            f"Plata #{i + 1} a fost inițiată la {118 + i} secunde după click.",
        ))
    return facts


def _tamper(ledger: Ledger, sql: str, params: tuple = ()) -> None:
    """Simulează un atacator cu acces la fișierul bazei: scoate triggerele și modifică direct."""
    with sqlite3.connect(ledger.db_path) as conn:
        for trigger in ("ledger_facts_no_update", "ledger_facts_no_delete", "ledger_seals_no_update",
                        "ledger_seals_no_delete"):
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        conn.execute(sql, params)


def _failed(result: dict) -> dict[str, dict]:
    return {c["name"]: c for c in result["checks"] if not c["ok"]}


# ------------------------------------------------------------ JSON canonic

def test_canonical_json_sorted_compact_utf8_and_dates():
    text = canonical_json({"b": 1, "a": {"ț": "ș", "z": [3, 2]},
                           "when": datetime(2026, 10, 28, 16, 2, tzinfo=timezone(timedelta(hours=2)))})
    assert text == '{"a":{"z":[3,2],"ț":"ș"},"b":1,"when":"2026-10-28T14:02:00+00:00"}'
    assert "ș".encode() in text.encode("utf-8")


@pytest.mark.parametrize("value, expected", [
    (3200.0, "3200"), (0.93, "0.93"), (1e-7, "1e-7"), (0.00001, "0.00001"), (1e21, "1e+21"),
    (123.456, "123.456"), (-0.0, "0"), (5e-324, "5e-324"), (-1.5, "-1.5"), (1e20, "100000000000000000000"),
])
def test_canonical_numbers_follow_rfc8785(value, expected):
    assert canonical_json(value) == expected


def test_canonical_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_args_hash_and_content_hash(ledger):
    fact = ledger.append(CASE, "k", "bank-core.get_transaction", {"b": 2, "a": 1}, {"x": 1}, "rezumat")
    assert fact.args_hash == "sha256:" + hash_obj({"a": 1, "b": 2}) == prefixed_hash({"b": 2, "a": 1})
    assert fact.sha256 == hash_obj({"x": 1}) and len(fact.sha256) == 64
    assert fact.retrieved_at.tzinfo is not None


# ------------------------------------------------------------ ID-uri, lanț, etichete

def test_fact_ids_per_case_and_zone(ledger, aml_ledger):
    facts = _fill(ledger, n=3)
    assert [f.fact_id for f in facts] == ["EV-001", "EV-002", "EV-003"]
    assert ledger.append("CT-2026-000124", "k", "t", {}, {}, "").fact_id == "EV-001"
    assert aml_ledger.append(CASE, "aml.flow", "aml.graph.neighborhood", {}, {"n": 1}, "").fact_id == "AX-001"
    assert facts[0].prev_hash == case_genesis(Zone.CLIENT, CASE)
    assert facts[1].prev_hash != facts[0].prev_hash
    assert ledger.count(CASE) == 3 and ledger.cases() == [CASE, "CT-2026-000124"]


def test_summary_is_normalized_to_comma_below(ledger):
    fact = ledger.append(CASE, "k", "t", {}, {}, "Tranzac\u0163ie \u015fi plă\u0163i")
    assert fact.summary == "Tranzacție și plăți"


def test_labels_enforce_the_wall(ledger, aml_ledger):
    with pytest.raises(LabelError):
        ledger.append(CASE, "k", "t", {}, {}, "", Labels(conf="aml-only", sinks=[Sink.AML]))
    with pytest.raises(LabelError):
        aml_ledger.append(CASE, "k", "t", {}, {}, "", Labels(conf="aml", sinks=[Sink.AML, Sink.CLIENT]))
    fact = aml_ledger.append(CASE, "k", "t", {}, {}, "")
    assert fact.labels.conf == "aml-only" and fact.labels.sinks == [Sink.AML]


def test_append_only_triggers_block_update_and_delete(ledger):
    _fill(ledger, n=2)
    with sqlite3.connect(ledger.db_path) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE ledger_facts SET summary = 'x'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM ledger_facts")


def test_other_modules_tables_are_left_alone(tmp_path):
    db = tmp_path / "client_zone.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE complaints (id TEXT)")
        conn.execute("INSERT INTO complaints VALUES ('CT-1')")
    ledger = Ledger(Zone.CLIENT, db, tmp_path / "keys")
    _fill(ledger, n=2)
    ledger.seal(CASE)
    Ledger(Zone.CLIENT, db, tmp_path / "keys")  # a doua inițializare nu strică nimic
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT id FROM complaints").fetchall() == [("CT-1",)]


def test_concurrent_appends_are_serialized(ledger):
    errors = []

    def worker(case_id: str) -> None:
        try:
            for i in range(15):
                ledger.append(case_id, "k", "t", {"i": i}, {"i": i}, "")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(CASE if i % 2 else "CT-2026-000999",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    ids = [f.fact_id for f in ledger.facts(CASE)]
    assert ids == [f"EV-{i:03d}" for i in range(1, 61)]
    ledger.seal(CASE)
    assert ledger.verify(CASE)["valid"]
    assert ledger.verify_global()["valid"]


# ------------------------------------------------------------ sigiliu, chei, QR

def test_seal_signs_root_and_makes_qr(ledger, tmp_path):
    _fill(ledger)
    seal = ledger.seal(CASE)
    assert {"root", "signature", "public_key", "count", "sealed_at", "qr_svg"} <= set(seal)
    assert seal["count"] == 5 and len(seal["root"]) == 64
    assert verify_signature(seal["public_key"], f"versoml:v1:{CASE}:5:{seal['root']}".encode(), seal["signature"])
    assert seal["qr_text"] == f"https://versoml.vercel.app/verify/{CASE}#{seal['root']}"
    assert seal["qr_svg"].startswith("<svg") and "versoml-qr" in seal["qr_svg"] and 'fill="#fff"' not in seal["qr_svg"]
    assert (tmp_path / "keys" / "zone_client.key").exists() and (tmp_path / "keys" / "zone_client.pub").exists()
    assert ledger.seal(CASE)["sealed_at"] == seal["sealed_at"]  # nimic nou → același sigiliu
    again = Ledger(Zone.CLIENT, ledger.db_path, tmp_path / "keys")
    assert again.public_key() == seal["public_key"]


def test_zone_keys_are_separate(ledger, aml_ledger):
    _fill(ledger, n=1)
    aml_ledger.append(CASE, "k", "t", {}, {}, "")
    assert ledger.seal(CASE)["public_key"] != aml_ledger.seal(CASE)["public_key"]


def test_verify_valid_with_english_check_names(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    result = ledger.verify(CASE)
    assert result["valid"] and result["sealed"]
    names = [c["name"] for c in result["checks"]]
    assert {"Content integrity", "Hash chain", "Merkle root", "Ed25519 signature",
            "Zone public key", "Seal coverage"} <= set(names)


def test_unsealed_and_post_seal_facts_are_reported(ledger):
    _fill(ledger, n=2)
    first = ledger.verify(CASE)
    assert not first["valid"] and not first["sealed"] and "Case seal" in _failed(first)
    ledger.seal(CASE)
    ledger.append(CASE, "human.approval", "console.approve", {}, {"approved": True}, "Aprobare umană.")
    after = ledger.verify(CASE)
    assert not after["valid"] and _failed(after)["Seal coverage"]["facts"] == ["EV-003"]
    ledger.seal(CASE)
    assert ledger.verify(CASE)["valid"]


# ------------------------------------------------------------ tamper

def test_one_byte_change_in_content_names_the_fact(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    _tamper(ledger, "UPDATE ledger_facts SET content_json = replace(content_json, '120', '121') WHERE fact_id = 'EV-003'")
    result = ledger.verify(CASE)
    assert not result["valid"]
    bad = _failed(result)["Content integrity"]
    assert bad["facts"] == ["EV-003"] and "EV-003" in bad["detail"]


def test_rehashed_content_is_caught_by_record_hash_chain_and_root(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    new_content = {"amount": 1, "device_new": False, "score": 0.93, "seconds_after_click": 999}
    _tamper(ledger, "UPDATE ledger_facts SET content_json = ?, sha256 = ? WHERE fact_id = 'EV-002'",
            (canonical_json(new_content), hash_obj(new_content)))
    failed = _failed(ledger.verify(CASE))
    assert "Content integrity" not in failed
    assert failed["Record integrity"]["facts"] == ["EV-002"]
    assert failed["Hash chain"]["facts"] == ["EV-003"]
    assert "EV-002" in failed["Hash chain"]["detail"]
    assert failed["Merkle root"]["facts"] == ["EV-002"]


def test_metadata_change_is_caught(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    _tamper(ledger, "UPDATE ledger_facts SET summary = 'Clientul a aprobat plata.' WHERE fact_id = 'EV-004'")
    assert _failed(ledger.verify(CASE))["Record integrity"]["facts"] == ["EV-004"]


def test_deleted_fact_breaks_numbering_chain_and_root(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    _tamper(ledger, "DELETE FROM ledger_facts WHERE fact_id = 'EV-002'")
    failed = _failed(ledger.verify(CASE))
    assert {"Entry numbering", "Hash chain", "Merkle root"} <= set(failed)


def test_forged_signature_and_foreign_key_are_caught(ledger, tmp_path):
    _fill(ledger)
    seal = ledger.seal(CASE)
    forged = seal["signature"][:-2] + ("AA" if not seal["signature"].endswith("AA") else "BB")
    _tamper(ledger, "UPDATE ledger_seals SET signature = ?", (forged,))
    assert "Ed25519 signature" in _failed(ledger.verify(CASE))
    # atacatorul resemnează aceeași rădăcină cu cheia lui: semnătura e validă, dar nu e cheia zonei
    from versoml.shared.ledger.keys import load_zone_key

    attacker = load_zone_key(Zone.CLIENT, tmp_path / "attacker_keys")
    payload = f"versoml:v1:{CASE}:{seal['count']}:{seal['root']}".encode()
    _tamper(ledger, "UPDATE ledger_seals SET signature = ?, public_key = ?", (attacker.sign(payload), attacker.public_b64))
    assert set(_failed(ledger.verify(CASE))) == {"Zone public key"}


def test_missing_zone_key_fails_the_key_check(ledger, tmp_path):
    _fill(ledger, n=2)
    ledger.seal(CASE)
    fresh = Ledger(Zone.CLIENT, ledger.db_path, tmp_path / "chei_goale")
    failed = _failed(fresh.verify(CASE))
    assert set(failed) == {"Zone public key"} and "missing" in failed["Zone public key"]["detail"]
    assert not (tmp_path / "chei_goale" / "zone_client.key").exists()  # verificarea nu generează chei


def test_last_fact_fully_recomputed_is_caught_by_sealed_root(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    from versoml.shared.ledger import entry_hash

    row = ledger.export_dossier(CASE)["facts"][-1]
    row["content"] = {"amount": 1}
    row["sha256"] = hash_obj(row["content"])
    _tamper(ledger, "UPDATE ledger_facts SET content_json = ?, sha256 = ?, entry_hash = ? WHERE fact_id = 'EV-005'",
            (canonical_json(row["content"]), row["sha256"], entry_hash(row)))
    failed = _failed(ledger.verify(CASE))
    assert set(failed) == {"Merkle root"} and failed["Merkle root"]["facts"] == ["EV-005"]


def test_seal_refuses_a_tampered_ledger(ledger):
    _fill(ledger)
    _tamper(ledger, "UPDATE ledger_facts SET content_json = '{}' WHERE fact_id = 'EV-001'")
    with pytest.raises(LedgerError):
        ledger.seal(CASE)


# ------------------------------------------------------------ Merkle

CT_LEAVES = [b"", b"\x00", b"\x10", b"\x20\x21", b"\x30\x31", b"\x40\x41\x42\x43",
             b"\x50\x51\x52\x53\x54\x55\x56\x57", bytes.fromhex("606162636465666768696a6b6c6d6e6f")]
CT_ROOTS = [
    "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
]


@pytest.mark.parametrize("n", range(1, 9))
def test_merkle_root_matches_rfc6962_vectors(n):
    assert merkle_root(CT_LEAVES[:n]).hex() == CT_ROOTS[n - 1]


@hsettings(max_examples=40, deadline=None)
@given(st.integers(min_value=1, max_value=40), st.data())
def test_every_inclusion_proof_verifies_and_tampering_fails(n, data):
    leaves = [leaf_hash(i.to_bytes(4, "big")) for i in range(n)]
    root = root_from_leaves(leaves)
    m = data.draw(st.integers(min_value=0, max_value=n - 1))
    path = inclusion_path(leaves, m)
    assert verify_inclusion(leaves[m], m, n, path, root)
    if path:
        k = data.draw(st.integers(min_value=0, max_value=len(path) - 1))
        broken = list(path)
        broken[k] = bytes(32)
        assert not verify_inclusion(leaves[m], m, n, broken, root)
    assert not verify_inclusion(leaf_hash(b"alt"), m, n, path, root)


def test_ledger_proofs(ledger):
    _fill(ledger, n=7)
    ledger.seal(CASE)
    for i in range(1, 8):
        proof = ledger.proof(CASE, f"EV-{i:03d}")
        assert proof["sealed"] and verify_proof(proof)
    bad = ledger.proof(CASE, "EV-004")
    bad["index"] = 2
    assert not verify_proof(bad)
    with pytest.raises(LedgerError):
        ledger.proof(CASE, "EV-099")


# ------------------------------------------------------------ dosarul exportat

def test_dossier_verifies_offline_and_after_json_round_trip(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    dossier = ledger.export_dossier(CASE)
    assert verify_dossier(dossier)["valid"]
    wire = json.loads(json.dumps(dossier, ensure_ascii=False))
    assert verify_dossier(wire, public_key=ledger.public_key())["valid"]

    def js_like(value):  # JSON.parse/JSON.stringify: 3200.0 devine 3200
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: js_like(v) for k, v in value.items()}
        if isinstance(value, list):
            return [js_like(v) for v in value]
        return value

    assert verify_dossier(js_like(wire))["valid"]


def test_dossier_tamper_and_wrong_key_are_caught(ledger):
    _fill(ledger)
    ledger.seal(CASE)
    dossier = ledger.export_dossier(CASE)
    assert not verify_dossier(dossier, public_key="A" * 43)["valid"]
    tampered = json.loads(json.dumps(dossier))
    tampered["facts"][1]["content"]["seconds_after_click"] = 5
    failed = _failed(verify_dossier(tampered))
    assert failed["Content integrity"]["facts"] == ["EV-002"]
    broken = json.loads(json.dumps(dossier))
    broken["merkle"]["proofs"]["EV-003"][0] = "00" * 32
    assert "Inclusion proofs" in _failed(verify_dossier(broken))
    assert not verify_dossier({"format": "x"})["valid"]


def test_snapshot_and_summary_shapes(ledger):
    _fill(ledger, n=2)
    assert ledger.summary(CASE) == {"count": 2, "root": None, "sealed": False}
    ledger.seal(CASE)
    snap = ledger.snapshot(CASE)
    assert set(snap) == {"facts", "seal", "verify"} and snap["verify"]["valid"]
    assert snap["facts"][0]["fact_id"] == "EV-001" and snap["seal"]["count"] == 2
    assert ledger.summary(CASE)["sealed"] is True


def test_reading_and_exporting_never_seal(ledger):
    _fill(ledger, n=2)
    with pytest.raises(LedgerError):
        ledger.export_dossier(CASE)                          # nothing sealed yet: no file to export
    assert ledger.latest_seal(CASE) is None
    ledger.seal(CASE)
    _fill(ledger, n=1)
    ledger.snapshot(CASE)
    dossier = ledger.export_dossier(CASE)
    assert ledger.latest_seal(CASE)["count"] == 2 and len(dossier["facts"]) == 3
    assert "Seal coverage" in _failed(verify_dossier(dossier, public_key=ledger.public_key()))


# ------------------------------------------------------------ verificarea publică din QR

def test_seal_check_answers_only_to_the_root_in_the_code(ledger):
    _fill(ledger)
    first = ledger.seal(CASE)
    _fill(ledger, n=1)
    second = ledger.seal(CASE)
    now = ledger.seal_check(CASE, second["root"].upper())
    assert now["current"] and now["intact"] and now["signature_valid"] and now["latest"] is None
    assert (now["count"], now["entries_now"], now["sealed_at"]) == (6, 6, second["sealed_at"])
    older = ledger.seal_check(CASE, first["root"])
    assert not older["current"] and older["intact"] and older["count"] == 5
    assert older["latest"] == {"sealed_at": second["sealed_at"], "count": 6}
    assert set(now) == {"case_id", "root", "current", "intact", "signature_valid", "sealed_at", "count", "entries_now",
                        "latest", "public_key", "checks", "verified_at"}
    assert all(set(c) == {"name", "ok", "detail"} for c in now["checks"])
    # a guessed case ID, a wrong root or a root from another case all get the same nothing
    assert ledger.seal_check("CT-2026-999999", second["root"]) is None
    assert ledger.seal_check(CASE, "0" * 64) is None
    assert ledger.seal_check(CASE, "") is None and ledger.seal_check(CASE, "not-a-root") is None


def test_seal_check_reports_a_tampered_file(ledger):
    _fill(ledger)
    seal = ledger.seal(CASE)
    _tamper(ledger, "UPDATE ledger_facts SET content_json = '{}' WHERE fact_id = 'EV-002'")
    result = ledger.seal_check(CASE, seal["root"])
    assert not result["intact"] and result["signature_valid"]
    assert {c["name"] for c in result["checks"] if not c["ok"]} == {"Content integrity"}
