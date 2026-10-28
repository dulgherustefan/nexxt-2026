"""Scannerul ieșirilor zonei client: JSON, JSONL, text, SQLite; raportul nu copiază conținutul găsit."""

from __future__ import annotations

import json
import sqlite3

from versoml.wall import journal, scan_paths


def test_scanner_finds_canaries_and_terms_without_copying_them(tmp_path, registry):
    token = registry.mint("LD-0100")
    logs = tmp_path / "logs"
    (logs / "trace").mkdir(parents=True)
    (logs / "events.jsonl").write_text(
        json.dumps({"type": "STEP_FINISHED", "message": "Colector gata"}) + "\n"
        + json.dumps({"type": "TEXT_MESSAGE_CONTENT", "message": f"dosar {token}"}) + "\n"
        + "linie stricată { nu e json " + token.lower() + "\n",
        encoding="utf-8")
    escaped = "".join(f"\\u{ord(c):04x}" for c in token)  # tokenul scris cu escape-uri JSON
    (logs / "trace" / "span.json").write_text('{"attrs": {"note": "' + escaped + '"}}', encoding="utf-8")
    (logs / "app.log").write_text("INFO pornit\nWARN scrisoarea menționa ONPCSB\n", encoding="utf-8")
    (logs / "ignored.bin").write_bytes(token.encode())
    with sqlite3.connect(tmp_path / "client_zone.db") as conn:
        conn.execute("CREATE TABLE letters (case_id TEXT, body TEXT)")
        conn.execute("INSERT INTO letters VALUES ('CT-2026-000123', ?)", (f"Rambursat. {token}",))

    report = scan_paths([logs, tmp_path / "client_zone.db"], registry=registry)
    assert report["files"] == 4 and report["canary_hits"] == 4 and report["term_hits"] == 1
    assert not report["clean"] and not report["strict_clean"]
    where = {(f["kind"], f["where"]) for f in report["findings"]}
    assert ("canary", "linia 2") in where and ("canary", "letters#1") in where and ("term", "linia 2") in where
    dumped = json.dumps(report, ensure_ascii=False)
    assert token not in dumped and token.lower() not in dumped and "dosar" not in dumped
    assert journal.recent(5, kind="scanner_canary")


def test_clean_outputs(tmp_path, registry):
    registry.mint("LD-0101")
    (tmp_path / "ok.jsonl").write_text(json.dumps({"message": "Rambursare emisă la T+1."}) + "\n", encoding="utf-8")
    (tmp_path / "policy.log").write_text("Refuzat: un principal din zona client nu acționează în zona AML\n",
                                         encoding="utf-8")
    report = scan_paths([tmp_path], registry=registry)
    assert report["clean"] and report["canary_hits"] == 0
    assert not report["strict_clean"] and report["term_hits"] == 1  # mesajele zidului pomenesc „AML"
    assert scan_paths([tmp_path], registry=registry, terms=False)["strict_clean"]


def test_missing_paths_are_ignored(tmp_path, registry):
    report = scan_paths([tmp_path / "nu-exista"], registry=registry)
    assert report["files"] == 0 and report["clean"]
