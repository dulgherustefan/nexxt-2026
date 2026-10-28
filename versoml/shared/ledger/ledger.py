"""Registrul de probe al unei zone (docs/05 §6.5).

- Doar-adăugare: triggere SQLite blochează UPDATE și DELETE.
- Lanț SHA-256 pe caz (`prev_hash`) și un lanț global al zonei.
- Pe caz: rădăcină Merkle RFC 6962, semnată Ed25519 cu cheia zonei, plus QR.
- `verify` recalculează tot și numește faptul modificat.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import segno

from versoml.contracts import Fact, Labels, Sink, Trust, Zone
from versoml.shared.ledger.canonical import (
    canonical_json,
    hash_obj,
    iso_utc,
    normalize_json,
    now_utc,
    prefixed_hash,
    sha256_hex,
)
from versoml.shared.ledger.keys import ZoneKey, load_zone_key, verify_signature
from versoml.shared.ledger.merkle import inclusion_path, leaf_hash, root_from_leaves, verify_inclusion
from versoml.shared.privacy.text import normalize_ro

DOSSIER_FORMAT = "versoml-dossier/v1"
SEAL_PREFIX = "versoml:v1"
ID_PREFIX = {Zone.CLIENT: "EV", Zone.AML: "AX"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_facts (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_index INTEGER NOT NULL,
    fact_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_tool TEXT NOT NULL,
    args_json TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    global_prev TEXT NOT NULL,
    global_hash TEXT NOT NULL,
    labels_json TEXT NOT NULL,
    summary TEXT NOT NULL,
    content_json TEXT NOT NULL,
    UNIQUE (zone, case_id, case_index),
    UNIQUE (zone, case_id, fact_id)
);
CREATE INDEX IF NOT EXISTS ix_ledger_facts_case ON ledger_facts (zone, case_id, case_index);
CREATE TABLE IF NOT EXISTS ledger_seals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT NOT NULL,
    case_id TEXT NOT NULL,
    count INTEGER NOT NULL,
    root TEXT NOT NULL,
    signature TEXT NOT NULL,
    public_key TEXT NOT NULL,
    sealed_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    leaves_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ledger_seals_case ON ledger_seals (zone, case_id, id);
CREATE TRIGGER IF NOT EXISTS ledger_facts_no_update BEFORE UPDATE ON ledger_facts
BEGIN SELECT RAISE(ABORT, 'registrul de probe e doar-adaugare'); END;
CREATE TRIGGER IF NOT EXISTS ledger_facts_no_delete BEFORE DELETE ON ledger_facts
BEGIN SELECT RAISE(ABORT, 'registrul de probe e doar-adaugare'); END;
CREATE TRIGGER IF NOT EXISTS ledger_seals_no_update BEFORE UPDATE ON ledger_seals
BEGIN SELECT RAISE(ABORT, 'sigiliile sunt doar-adaugare'); END;
CREATE TRIGGER IF NOT EXISTS ledger_seals_no_delete BEFORE DELETE ON ledger_seals
BEGIN SELECT RAISE(ABORT, 'sigiliile sunt doar-adaugare'); END;
"""

_FACT_COLUMNS = (
    "zone, case_id, case_index, fact_id, kind, source_tool, args_json, args_hash, retrieved_at, sha256, "
    "prev_hash, entry_hash, global_prev, global_hash, labels_json, summary, content_json"
)

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class LedgerError(Exception):
    """Eroare de registru (argumente greșite sau registru compromis)."""


class LabelError(LedgerError):
    """O etichetă încalcă zidul (stratul 4: etichete pe date)."""


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def case_genesis(zone: Zone | str, case_id: str) -> str:
    """Primul `prev_hash` al unui caz: leagă lanțul de zonă și de caz."""
    return sha256_hex(f"{SEAL_PREFIX}:{Zone(zone).value}:{case_id}:genesis")


def global_genesis(zone: Zone | str) -> str:
    return sha256_hex(f"{SEAL_PREFIX}:{Zone(zone).value}:global:genesis")


def seal_payload(case_id: str, count: int, root: str) -> str:
    """Mesajul semnat Ed25519."""
    return f"{SEAL_PREFIX}:{case_id}:{count}:{root}"


def qr_text(case_id: str, root: str, signature: str) -> str:
    """The text in the evidence file's QR code."""
    return f"{SEAL_PREFIX}:{case_id}:{root}:{signature}"


def qr_svg(text: str, title: str | None = None) -> str:
    """QR negru pe fundal transparent (merge pe galben), SVG inline."""
    return segno.make(text, error="m").svg_inline(
        scale=4, border=4, dark="#000000", light=None, title=title, svgclass="versoml-qr"
    )


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return iso_utc(value)
    return iso_utc(datetime.fromisoformat(str(value)))


def entry_record(fact: dict[str, Any]) -> dict[str, Any]:
    """Câmpurile unui fapt acoperite de hash-ul înregistrării (conținutul intră prin `sha256`)."""
    labels = fact.get("labels") or {}
    if isinstance(labels, Labels):
        labels = labels.model_dump(mode="json")
    return {
        "v": 1,
        "zone": Zone(fact["zone"]).value,
        "case_id": fact["case_id"],
        "fact_id": fact["fact_id"],
        "kind": fact["kind"],
        "source_tool": fact["source_tool"],
        "args_hash": fact["args_hash"],
        "retrieved_at": _iso(fact["retrieved_at"]),
        "sha256": fact["sha256"],
        "prev_hash": fact["prev_hash"],
        "labels": normalize_json(labels),
        "summary": fact.get("summary", ""),
    }


def entry_hash(fact: dict[str, Any]) -> str:
    return hash_obj(entry_record(fact))


def root_hex(entries: Sequence[str]) -> str:
    """Rădăcina Merkle (hex) peste hash-urile înregistrărilor."""
    return root_from_leaves([leaf_hash(bytes.fromhex(e)) for e in entries]).hex()


def _check(name: str, ok: bool, detail: str, facts: Sequence[str] = ()) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail, "facts": list(facts)}


def _list_ids(ids: Sequence[str], limit: int = 6) -> str:
    shown = ", ".join(ids[:limit])
    return shown + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


def _entries(n: int) -> str:
    return "1 entry" if n == 1 else f"{n} entries"


SEAL_CHECK = "Case seal"


def verify_facts(
    zone: Zone | str,
    case_id: str,
    facts: Sequence[dict[str, Any]],
    seal: dict[str, Any] | None,
    *,
    stored_entries: Sequence[str | None] | None = None,
    stored_args: Sequence[tuple[Any, str]] | None = None,
    sealed_leaves: Sequence[str] | None = None,
    expected_public_key: str | None = None,
    key_source: str = "the zone key",
) -> dict[str, Any]:
    """Verificarea completă a unui caz, comună pentru registru și pentru dosarul exportat."""
    zone = Zone(zone)
    prefix = ID_PREFIX[zone]
    checks: list[dict[str, Any]] = []
    ids = [str(f.get("fact_id", f"#{i + 1}")) for i, f in enumerate(facts)]
    n = len(facts)

    # 1. conținutul fiecărui fapt
    bad = []
    for fid, fact in zip(ids, facts):
        try:
            if hash_obj(fact["content"]) != fact["sha256"]:
                bad.append(fid)
        except (KeyError, TypeError, ValueError):
            bad.append(fid)
    checks.append(_check(
        "Content integrity", not bad,
        f"The content no longer matches its hash for: {_list_ids(bad)}." if bad
        else ("The entry's content is intact." if n == 1 else f"All {n} entries have intact content."), bad))

    # 2. argumentele (doar în registru; dosarul are doar hash-ul lor)
    if stored_args is not None:
        bad = [fid for fid, (args, h) in zip(ids, stored_args) if prefixed_hash(args) != h]
        checks.append(_check(
            "Argument integrity", not bad,
            f"The arguments no longer match their hash for: {_list_ids(bad)}." if bad
            else "The argument hashes match.", bad))

    # 3. hash-ul fiecărei înregistrări
    entries: list[str | None] = []
    for fact in facts:
        try:
            entries.append(entry_hash(fact))
        except (KeyError, TypeError, ValueError):
            entries.append(None)
    if stored_entries is not None:
        bad = [fid for fid, mine, stored in zip(ids, entries, stored_entries) if stored is not None and mine != stored]
        bad += [fid for fid, mine in zip(ids, entries) if mine is None and fid not in bad]
        checks.append(_check(
            "Record integrity", not bad,
            f"The entry metadata was changed for: {_list_ids(bad)}." if bad
            else "The metadata (source, time, labels, summary) is intact.", bad))

    # 4. numerotarea: EV-001, EV-002, … fără goluri, aceeași zonă și același caz
    bad = []
    for i, (fid, fact) in enumerate(zip(ids, facts)):
        expected = f"{prefix}-{i + 1:03d}"
        if fid != expected or fact.get("case_id") != case_id or str(fact.get("zone")) != zone.value:
            bad.append(fid)
    checks.append(_check(
        "Entry numbering", not bad,
        f"Missing, moved or foreign entries at: {_list_ids(bad)}." if bad
        else f"The entries are consecutive ({prefix}-001 to {prefix}-{n:03d})." if n else "The case ledger is empty.", bad))

    # 5. lanțul de hash-uri
    bad = []
    for i, (fid, fact) in enumerate(zip(ids, facts)):
        expected = case_genesis(zone, case_id) if i == 0 else entries[i - 1]
        if expected is None or fact.get("prev_hash") != expected:
            bad.append(fid)
    if bad:
        first = ids.index(bad[0])
        hint = f" (check {ids[first - 1]} and {bad[0]})" if first > 0 else ""
        detail = f"The chain is broken at: {_list_ids(bad)}{hint}."
    else:
        detail = "Each entry points correctly to the one before it."
    checks.append(_check("Hash chain", not bad, detail, bad))

    # 6–9. sigiliul
    root_value = None
    if seal is None:
        checks.append(_check(SEAL_CHECK, False, "The case is not sealed yet; the chain is verified, the root is not."))
    else:
        count = int(seal.get("count", -1))
        root_value = str(seal.get("root", ""))
        covered = entries[:count] if 0 <= count <= n else []
        if count < 0 or count > n:
            checks.append(_check(
                "Merkle root", False,
                f"The seal covers {_entries(count)}, but the ledger has only {n}: entries are missing.",
                ids[count:] if count > 0 else ()))
        elif any(e is None for e in covered):
            bad = [fid for fid, e in zip(ids, covered) if e is None]
            checks.append(_check("Merkle root", False, f"Unreadable entries: {_list_ids(bad)}.", bad))
        else:
            computed = root_hex([e for e in covered if e is not None])
            if computed == root_value:
                checks.append(_check("Merkle root", True, f"The root over {_entries(count)} matches the seal."))
            else:
                bad = []
                if sealed_leaves is not None and len(sealed_leaves) == count:
                    bad = [fid for fid, mine, old in zip(ids, covered, sealed_leaves) if mine != old]
                    if root_hex(list(sealed_leaves)) != root_value:
                        bad = bad or ids[:count]
                detail = (f"The recomputed root differs from the sealed one; changed entries: {_list_ids(bad)}." if bad
                          else "The recomputed root differs from the sealed one.")
                checks.append(_check("Merkle root", False, detail, bad))
        payload = seal_payload(case_id, count, root_value)
        sig_ok = verify_signature(str(seal.get("public_key", "")), payload.encode("utf-8"), str(seal.get("signature", "")))
        checks.append(_check(
            "Ed25519 signature", sig_ok,
            "The signature on the root is valid." if sig_ok else "The signature does not match the root and the public key."))
        if expected_public_key is None:
            checks.append(_check(
                "Zone public key", True,
                "The public key was taken from the evidence file; compare it with the key the bank publishes."))
        else:
            key_ok = seal.get("public_key") == expected_public_key
            checks.append(_check(
                "Zone public key", key_ok,
                f"The seal was made with {key_source}." if key_ok else f"The seal was not made with {key_source}."))
        extra = n - count if 0 <= count <= n else 0
        checks.append(_check(
            "Seal coverage", extra == 0,
            "The seal covers every entry." if extra == 0
            else f"{_entries(extra)} added after the seal; seal the case again.", ids[count:] if extra else ()))

    return {
        "valid": all(c["ok"] for c in checks),
        "checks": checks,
        "case_id": case_id,
        "zone": zone.value,
        "count": n,
        "sealed": seal is not None,
        "root": root_value,
        "verified_at": iso_utc(now_utc()),
    }


class Ledger:
    """Registrul de probe al unei zone, într-un tabel propriu din baza zonei."""

    def __init__(self, zone: Zone | str, db_path: Path | str, keys_dir: Path | str):
        self.zone = Zone(zone)
        self.db_path = Path(db_path)
        self.keys_dir = Path(keys_dir)
        self.prefix = ID_PREFIX[self.zone]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for(self.db_path)
        self._key: ZoneKey | None = None
        with self._lock, self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------ infrastructură

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _zone_key(self) -> ZoneKey:
        if self._key is None:
            self._key = load_zone_key(self.zone, self.keys_dir)
        return self._key

    def public_key(self) -> str | None:
        """Cheia publică a zonei (base64url), fără să genereze una nouă."""
        if self._key is not None:
            return self._key.public_b64
        if not (self.keys_dir / f"zone_{self.zone.value}.key").exists():
            return None
        return self._zone_key().public_b64

    def default_labels(self) -> Labels:
        if self.zone is Zone.AML:
            return Labels(conf="aml-only", trust=Trust.TRUSTED, sinks=[Sink.AML])
        return Labels()

    def _check_labels(self, labels: Labels | dict | None) -> Labels:
        if labels is None:
            return self.default_labels()
        labels = labels if isinstance(labels, Labels) else Labels.model_validate(labels)
        if self.zone is Zone.CLIENT and labels.conf in ("aml", "aml-only"):
            raise LabelError(
                f"The wall (labels): an entry with confidentiality \"{labels.conf}\" cannot enter the client zone ledger.")
        if self.zone is Zone.AML and (Sink.CLIENT in labels.sinks or Sink.LETTER in labels.sinks):
            raise LabelError("The wall (labels): an entry from the AML zone cannot go to the client zone or into a letter.")
        return labels

    def _rows(self, conn: sqlite3.Connection, case_id: str) -> list[sqlite3.Row]:
        return conn.execute(
            f"SELECT {_FACT_COLUMNS} FROM ledger_facts WHERE zone = ? AND case_id = ? ORDER BY case_index",
            (self.zone.value, case_id),
        ).fetchall()

    def _seal_row(self, conn: sqlite3.Connection, case_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM ledger_seals WHERE zone = ? AND case_id = ? ORDER BY id DESC LIMIT 1",
            (self.zone.value, case_id),
        ).fetchone()

    @staticmethod
    def _fact_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "fact_id": row["fact_id"],
            "case_id": row["case_id"],
            "zone": row["zone"],
            "kind": row["kind"],
            "source_tool": row["source_tool"],
            "args_hash": row["args_hash"],
            "retrieved_at": row["retrieved_at"],
            "sha256": row["sha256"],
            "prev_hash": row["prev_hash"],
            "labels": json.loads(row["labels_json"]),
            "summary": row["summary"],
            "content": json.loads(row["content_json"]),
            "entry_hash": row["entry_hash"],
        }

    @classmethod
    def _to_fact(cls, row: sqlite3.Row) -> Fact:
        data = cls._fact_dict(row)
        data.pop("entry_hash")
        return Fact.model_validate(data)

    def _seal_view(self, row: sqlite3.Row, *, with_svg: bool = True) -> dict[str, Any]:
        text = qr_text(row["case_id"], row["root"], row["signature"])
        view = {
            "case_id": row["case_id"],
            "zone": row["zone"],
            "root": row["root"],
            "signature": row["signature"],
            "public_key": row["public_key"],
            "count": row["count"],
            "sealed_at": row["sealed_at"],
            "algorithm": "Ed25519 over the RFC 6962 Merkle root (SHA-256, RFC 8785 canonical JSON)",
            "payload": row["payload"],
            "qr_text": text,
        }
        if with_svg:
            view["qr_svg"] = qr_svg(text, title=f"Seal of case {row['case_id']}")
        return view

    # ------------------------------------------------------------ API public

    def append(
        self,
        case_id: str,
        kind: str,
        source_tool: str,
        args: dict,
        content: dict,
        summary: str,
        labels: Labels | None = None,
        *,
        retrieved_at: datetime | None = None,
    ) -> Fact:
        """Adaugă o probă. Întoarce faptul cu ID-ul lui (EV-001… sau AX-001…)."""
        case_id = str(case_id).strip()
        if not case_id or len(case_id) > 128:
            raise LedgerError("case_id is missing or too long")
        if not kind or not source_tool:
            raise LedgerError("kind and source_tool are required")
        checked = self._check_labels(labels)
        args_norm = normalize_json(args if args is not None else {})
        content_norm = normalize_json(content if content is not None else {})
        if not isinstance(content_norm, dict):
            raise LedgerError("an entry's content must be a JSON object")
        labels_dict = normalize_json(checked.model_dump(mode="json"))
        fact = {
            "zone": self.zone.value,
            "case_id": case_id,
            "kind": str(kind),
            "source_tool": str(source_tool),
            "args_hash": prefixed_hash(args_norm),
            "retrieved_at": iso_utc(retrieved_at or now_utc()),
            "sha256": hash_obj(content_norm),
            "labels": labels_dict,
            "summary": normalize_ro(summary or ""),
            "content": content_norm,
        }
        with self._lock, self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                last = conn.execute(
                    "SELECT case_index, entry_hash FROM ledger_facts WHERE zone = ? AND case_id = ? "
                    "ORDER BY case_index DESC LIMIT 1",
                    (self.zone.value, case_id),
                ).fetchone()
                last_global = conn.execute(
                    "SELECT global_hash FROM ledger_facts WHERE zone = ? ORDER BY seq DESC LIMIT 1",
                    (self.zone.value,),
                ).fetchone()
                index = last["case_index"] + 1 if last else 1
                fact["fact_id"] = f"{self.prefix}-{index:03d}"
                fact["prev_hash"] = last["entry_hash"] if last else case_genesis(self.zone, case_id)
                ehash = entry_hash(fact)
                gprev = last_global["global_hash"] if last_global else global_genesis(self.zone)
                conn.execute(
                    f"INSERT INTO ledger_facts ({_FACT_COLUMNS}) VALUES ({', '.join('?' * 17)})",
                    (
                        self.zone.value, case_id, index, fact["fact_id"], fact["kind"], fact["source_tool"],
                        canonical_json(args_norm), fact["args_hash"], fact["retrieved_at"], fact["sha256"],
                        fact["prev_hash"], ehash, gprev, sha256_hex(f"{gprev}:{ehash}"),
                        canonical_json(labels_dict), fact["summary"], canonical_json(content_norm),
                    ),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return Fact.model_validate(fact)

    def facts(self, case_id: str) -> list[Fact]:
        with self._conn() as conn:
            return [self._to_fact(row) for row in self._rows(conn, case_id)]

    def get(self, case_id: str, fact_id: str) -> Fact | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {_FACT_COLUMNS} FROM ledger_facts WHERE zone = ? AND case_id = ? AND fact_id = ?",
                (self.zone.value, case_id, fact_id),
            ).fetchone()
        return self._to_fact(row) if row else None

    def count(self, case_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM ledger_facts WHERE zone = ? AND case_id = ?", (self.zone.value, case_id)
            ).fetchone()
        return int(row["n"])

    def cases(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT case_id, MIN(seq) AS first FROM ledger_facts WHERE zone = ? GROUP BY case_id ORDER BY first",
                (self.zone.value,),
            ).fetchall()
        return [r["case_id"] for r in rows]

    def latest_seal(self, case_id: str, *, with_svg: bool = True) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = self._seal_row(conn, case_id)
        return self._seal_view(row, with_svg=with_svg) if row else None

    def seal(self, case_id: str) -> dict[str, Any]:
        """Sigilează cazul: rădăcina Merkle semnată Ed25519 și QR-ul.

        Întoarce {root, signature, public_key, count, sealed_at, qr_svg, …}. Dacă nu s-a
        adăugat nimic de la ultimul sigiliu, întoarce sigiliul existent. Refuză să sigileze
        un registru care nu trece verificarea.
        """
        key = self._zone_key()
        with self._lock, self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._rows(conn, case_id)
                facts = [self._fact_dict(r) for r in rows]
                pre = verify_facts(self.zone, case_id, facts, None, stored_entries=[f["entry_hash"] for f in facts])
                broken = [c for c in pre["checks"] if not c["ok"] and c["name"] != SEAL_CHECK]
                if broken:
                    raise LedgerError("The ledger fails verification, so it is not sealed: " + broken[0]["detail"])
                entries = [f["entry_hash"] for f in facts]
                root = root_hex(entries)
                last = self._seal_row(conn, case_id)
                if last and last["count"] == len(entries) and last["root"] == root and last["public_key"] == key.public_b64:
                    conn.execute("COMMIT")
                    return self._seal_view(last)
                payload = seal_payload(case_id, len(entries), root)
                conn.execute(
                    "INSERT INTO ledger_seals (zone, case_id, count, root, signature, public_key, sealed_at, payload, "
                    "leaves_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.zone.value, case_id, len(entries), root, key.sign(payload.encode("utf-8")),
                        key.public_b64, iso_utc(now_utc()), payload, json.dumps(entries),
                    ),
                )
                row = self._seal_row(conn, case_id)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return self._seal_view(row)

    def verify(self, case_id: str) -> dict[str, Any]:
        """Recalculează conținutul, lanțul, rădăcina și semnătura. {valid, checks:[{name, ok, detail}]}."""
        with self._conn() as conn:
            rows = self._rows(conn, case_id)
            seal_row = self._seal_row(conn, case_id)
        facts = [self._fact_dict(r) for r in rows]
        stored_args = []
        for row in rows:
            try:
                stored_args.append((json.loads(row["args_json"]), row["args_hash"]))
            except ValueError:
                stored_args.append((None, row["args_hash"]))
        seal = self._seal_view(seal_row, with_svg=False) if seal_row else None
        leaves = json.loads(seal_row["leaves_json"]) if seal_row else None
        zone_key = self.public_key()
        return verify_facts(
            self.zone, case_id, facts, seal,
            stored_entries=[f["entry_hash"] for f in facts],
            stored_args=stored_args,
            sealed_leaves=leaves,
            expected_public_key=zone_key or "",  # fără cheia zonei, verificarea cheii trebuie să pice
            key_source=f"the {self.zone.value} zone key" + ("" if zone_key else " (missing from keys_dir)"),
        )

    def verify_global(self) -> dict[str, Any]:
        """Verifică lanțul global al zonei (toate cazurile, în ordinea adăugării)."""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {_FACT_COLUMNS} FROM ledger_facts WHERE zone = ? ORDER BY seq", (self.zone.value,)
            ).fetchall()
        prev = global_genesis(self.zone)
        bad = []
        for row in rows:
            mine = entry_hash(self._fact_dict(row))
            if row["global_prev"] != prev or row["global_hash"] != sha256_hex(f"{prev}:{mine}"):
                bad.append(f"{row['case_id']}/{row['fact_id']}")
            prev = row["global_hash"]
        check = _check(
            "Zone-wide chain", not bad,
            f"The zone-wide chain is broken at: {_list_ids(bad)}." if bad
            else ("The only record is linked." if len(rows) == 1 else f"All {len(rows)} records are linked."),
            bad)
        return {"valid": not bad, "checks": [check], "zone": self.zone.value, "count": len(rows)}

    def proof(self, case_id: str, fact_id: str) -> dict[str, Any]:
        """Dovada de includere a unui fapt în arborele sigilat (sau în cel curent, dacă nu e sigilat)."""
        with self._conn() as conn:
            rows = self._rows(conn, case_id)
            seal_row = self._seal_row(conn, case_id)
        entries = [r["entry_hash"] for r in rows]
        ids = [r["fact_id"] for r in rows]
        if fact_id not in ids:
            raise LedgerError(f"Entry {fact_id} does not exist in case {case_id}")
        index = ids.index(fact_id)
        size = seal_row["count"] if seal_row and index < seal_row["count"] else len(entries)
        leaves = [leaf_hash(bytes.fromhex(e)) for e in entries[:size]]
        root = root_from_leaves(leaves).hex()
        sealed = bool(seal_row and seal_row["count"] == size and seal_row["root"] == root)
        return {
            "case_id": case_id,
            "fact_id": fact_id,
            "index": index,
            "tree_size": size,
            "entry_hash": entries[index],
            "leaf": leaves[index].hex(),
            "path": [p.hex() for p in inclusion_path(leaves, index)],
            "root": root,
            "sealed": sealed,
            "signature": seal_row["signature"] if sealed else None,
        }

    def export_dossier(self, case_id: str) -> dict[str, Any]:
        """Dosarul complet, verificabil fără acces la bancă (cu `verify_dossier`). Sigilează dacă e nevoie."""
        current = self.latest_seal(case_id, with_svg=False)
        if current is None or current["count"] != self.count(case_id):
            self.seal(case_id)
        with self._conn() as conn:
            rows = self._rows(conn, case_id)
            seal_row = self._seal_row(conn, case_id)
        if seal_row is None:
            raise LedgerError(f"Case {case_id} has no seal")
        facts = [self._fact_dict(r) for r in rows]
        entries = [f["entry_hash"] for f in facts]
        leaves = [leaf_hash(bytes.fromhex(e)) for e in entries]
        return {
            "format": DOSSIER_FORMAT,
            "zone": self.zone.value,
            "case_id": case_id,
            "exported_at": iso_utc(now_utc()),
            "facts": facts,
            "chain": {"genesis": case_genesis(self.zone, case_id), "hash": "SHA-256 over RFC 8785 canonical JSON"},
            "merkle": {
                "algorithm": "RFC 6962 (leaf = H(0x00‖entry_hash), node = H(0x01‖left‖right))",
                "tree_size": len(entries),
                "leaves": entries,
                "root": root_hex(entries),
                "proofs": {f["fact_id"]: [p.hex() for p in inclusion_path(leaves, i)] for i, f in enumerate(facts)},
            },
            "seal": self._seal_view(seal_row),
            "public_key": self.public_key(),
            "how_to_verify": (
                "For each entry: sha256 = SHA-256(canonical JSON of the content); entry_hash = SHA-256(canonical JSON "
                "of the metadata); prev_hash = the entry_hash of the entry before it. The Merkle root over the "
                "entry_hash values must equal seal.root, and seal.signature must be a valid Ed25519 signature of "
                "\"versoml:v1:{case_id}:{count}:{root}\" with the zone's public key."
            ),
        }

    def snapshot(self, case_id: str) -> dict[str, Any]:
        """Forma pentru `GET /api/ledger/{case_id}`: {facts, seal|null, verify}."""
        return {
            "facts": [f.model_dump(mode="json") for f in self.facts(case_id)],
            "seal": self.latest_seal(case_id),
            "verify": self.verify(case_id),
        }

    def summary(self, case_id: str) -> dict[str, Any]:
        """Forma pentru `CaseDetail.ledger`: {count, root, sealed}."""
        seal = self.latest_seal(case_id, with_svg=False)
        count = self.count(case_id)
        return {"count": count, "root": seal["root"] if seal else None, "sealed": bool(seal and seal["count"] == count)}


def verify_dossier(dossier: dict[str, Any], public_key: str | None = None) -> dict[str, Any]:
    """Verifică un dosar exportat, fără bază de date. `public_key` = cheia publicată a zonei, dacă o aveți."""
    try:
        zone = Zone(dossier.get("zone"))
        case_id = str(dossier["case_id"])
        facts = list(dossier.get("facts") or [])
        seal = dossier.get("seal")
        merkle = dossier.get("merkle") or {}
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"valid": False, "checks": [_check("Evidence file format", False,
                                                  "The evidence file lacks the required fields (zone, case_id, facts).")]}
    format_ok = dossier.get("format") == DOSSIER_FORMAT
    result = verify_facts(
        zone, case_id, facts, seal,
        stored_entries=[f.get("entry_hash") if isinstance(f, dict) else None for f in facts],
        sealed_leaves=merkle.get("leaves"),
        expected_public_key=public_key,
        key_source="the public key given for this check",
    )
    checks = [_check("Evidence file format", format_ok, "Format versoml-dossier/v1." if format_ok else "Unknown format.")]
    checks += result["checks"]
    proofs = merkle.get("proofs") or {}
    if proofs and seal:
        size = int(seal.get("count", 0))
        root = bytes.fromhex(str(seal.get("root", "")).strip() or "00")
        bad = []
        for i, fact in enumerate(facts[:size]):
            fid = fact.get("fact_id", f"#{i + 1}")
            try:
                leaf = leaf_hash(bytes.fromhex(entry_hash(fact)))
                path = [bytes.fromhex(p) for p in proofs.get(fid, [])]
                if not verify_inclusion(leaf, i, size, path, root):
                    bad.append(fid)
            except (KeyError, TypeError, ValueError):
                bad.append(fid)
        checks.append(_check(
            "Inclusion proofs", not bad,
            f"Invalid inclusion proofs for: {_list_ids(bad)}." if bad else "Every entry has a valid inclusion proof.", bad))
    result["checks"] = checks
    result["valid"] = all(c["ok"] for c in checks)
    return result


def verify_proof(proof: dict[str, Any]) -> bool:
    """Verifică o dovadă întoarsă de `Ledger.proof`."""
    try:
        leaf = leaf_hash(bytes.fromhex(proof["entry_hash"]))
        if proof.get("leaf") and proof["leaf"] != leaf.hex():
            return False
        return verify_inclusion(
            leaf, int(proof["index"]), int(proof["tree_size"]),
            [bytes.fromhex(p) for p in proof["path"]], bytes.fromhex(proof["root"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
