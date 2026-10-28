"""Scannerul ieșirilor zonei client: loguri, trasări, evenimente, baza zonei (zidul, stratul 5).

Caută tokenuri-canary (conținut AML scurs) și termeni interziși. Raportul nu copiază
niciodată textul găsit, doar fișierul, locul, tipul și eticheta termenului.
Termenii în loguri de sistem sunt informativi (mesajele zidului pomenesc „zona AML"),
deci `clean` înseamnă „zero canary"; `strict_clean` cere și zero termeni.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

from versoml.shared.ledger.canonical import iso_utc, now_utc
from versoml.wall import journal
from versoml.wall.canary import CanaryRegistry
from versoml.wall.terms import find_terms, labels

TEXT_SUFFIXES = {".txt", ".log", ".md", ".csv", ".html", ".xml", ".out"}
JSON_SUFFIXES = {".json"}
JSONL_SUFFIXES = {".jsonl", ".ndjson"}
DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
SCANNABLE = TEXT_SUFFIXES | JSON_SUFFIXES | JSONL_SUFFIXES | DB_SUFFIXES


def _strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _strings(value)


def _units(path: Path) -> Iterator[tuple[str, str]]:
    """(locul, text) pentru fiecare unitate scanabilă a fișierului."""
    suffix = path.suffix.lower()
    if suffix in DB_SUFFIXES:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                for i, row in enumerate(conn.execute(f"SELECT * FROM {quoted}")):
                    text = "\n".join(v.decode("utf-8", "ignore") if isinstance(v, bytes) else v
                                     for v in row if isinstance(v, (str, bytes)))
                    if text:
                        yield f"{table}#{i + 1}", text
        return
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in JSON_SUFFIXES:
        try:
            yield "json", "\n".join(_strings(json.loads(raw)))
            return
        except ValueError:
            pass
    for number, line in enumerate(raw.splitlines(), start=1):
        if suffix in JSONL_SUFFIXES:
            try:
                line = "\n".join(_strings(json.loads(line)))
            except ValueError:
                pass
        if line.strip():
            yield f"linia {number}", line


def _files(paths: Iterable[Path | str]) -> Iterator[Path]:
    for item in paths:
        path = Path(item)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SCANNABLE:
                    yield child
        elif path.is_file():
            yield path


def scan_paths(paths: Iterable[Path | str], *, registry: CanaryRegistry | None = None,
               terms: bool = True, max_bytes: int = 50 * 1024 * 1024) -> dict[str, Any]:
    """Scanează fișiere și directoare. Întoarce {files, canary_hits, term_hits, findings, clean, …}."""
    registry = registry if registry is not None else CanaryRegistry()
    findings: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    files = 0
    canary_hits = term_hits = 0
    for path in _files(paths):
        try:
            if path.stat().st_size > max_bytes:
                errors.append({"path": str(path), "error": "fișier prea mare, sărit"})
                continue
            files += 1
            for where, text in _units(path):
                count = registry.scan(text)
                if count:
                    canary_hits += count
                    findings.append({"path": str(path), "where": where, "kind": "canary", "count": count, "terms": []})
                if terms:
                    hits = find_terms(text)
                    if hits:
                        term_hits += len(hits)
                        findings.append({"path": str(path), "where": where, "kind": "term", "count": len(hits),
                                         "terms": labels(hits)})
        except (OSError, sqlite3.Error, UnicodeError) as exc:
            errors.append({"path": str(path), "error": type(exc).__name__})
    report = {
        "files": files,
        "canary_hits": canary_hits,
        "term_hits": term_hits,
        "findings": findings,
        "errors": errors,
        "clean": canary_hits == 0,
        "strict_clean": canary_hits == 0 and term_hits == 0,
        "scanned_at": iso_utc(now_utc()),
    }
    if canary_hits:
        journal.record(5, "scanner_canary", reasons=[f"{canary_hits} token(uri) canary în ieșirile zonei client."],
                       detail={"files": sorted({f['path'] for f in findings if f['kind'] == 'canary'})})
    return report
