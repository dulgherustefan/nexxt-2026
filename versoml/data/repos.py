"""Depozitele de date: singura cale prin care agenții citesc „sistemele băncii" (docs/06 §4.1).

- `ClientRepo` deschide DOAR `var/client_zone.db`; `AmlRepo` deschide DOAR `var/aml_zone.db`.
- Valorile întoarse sunt dict-uri simple, JSON-serializabile. Convenția pentru momente: șiruri ISO 8601 cu
  offset, în ora României (ex. `2026-10-28T14:02:11+02:00`). Parametrii de intrare acceptă `datetime` sau ISO.
- Coloanele `*_epoch` sunt interne și nu apar în rezultate; coloanele `*_json` apar decodate (fără sufix).
- Ceasul: implicit ora reală; dacă baza a fost generată de mult (peste 14 zile), ceasul rămâne la momentul lumii
  sintetice (`WORLD_NOW`), ca ferestrele „ultimele 90 de zile" să aibă sens. Testele dau `clock=` explicit.
- `post_transfer` și `post_refund` modifică soldul în aceeași tranzacție SQLite și sunt idempotente pe cheie.
  Niciun LLM nu primește acces direct la ele: rambursarea o emite motorul de reguli, după aprobare unde e cazul.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from versoml.contracts import Complaint, DisputeFacts
from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.calendar_ro import TZ, iso, parse_ts
from versoml.data.features import HUB_DEGREE, is_hub, node_features
from versoml.data.schema import AML_DDL, BOOL_COLUMNS, CLIENT_DDL, JSON_COLUMNS
from versoml.data.text import fmt_ron

FROZEN_AFTER_DAYS = 14


# ---------------------------------------------------------------- utilitare SQLite


def epoch(value: datetime | str | None) -> int | None:
    dt = parse_ts(value)
    return int(dt.timestamp()) if dt else None


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k in row.keys():
        v = row[k]
        if k.endswith("_epoch") or k == "natural_key":
            continue
        if k in JSON_COLUMNS:
            out[JSON_COLUMNS[k]] = json.loads(v) if v else ([] if k.endswith("refs_json") or k in ("attachments_json",) else None)
            continue
        if k in BOOL_COLUMNS and v is not None:
            v = bool(v)
        out[k] = v
    return out


def rows(cur: Iterable[sqlite3.Row]) -> list[dict]:
    return [row_to_dict(r) for r in cur]  # type: ignore[misc]


def insert(conn: sqlite3.Connection, table: str, records: list[dict], columns: list[str], *, mode: str = "INSERT") -> int:
    if not records:
        return 0
    sql = f"{mode} INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    conn.executemany(sql, [tuple(_sqlval(r.get(c)) for c in columns) for r in records])
    return len(records)


def _sqlval(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, datetime):
        return iso(v)
    return v


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


class _Repo:
    ddl = ""

    def __init__(self, db_path: str | Path | None, clock: Callable[[], datetime] | None):
        self.db_path = Path(db_path) if db_path else self._default_path()
        self._clock = clock
        self._world_now: datetime | None = None

    def _default_path(self) -> Path:  # pragma: no cover - suprascris
        raise NotImplementedError

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Tranzacție de scriere (BEGIN IMMEDIATE): fie se aplică tot, fie nimic."""
        conn = connect(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def now(self) -> datetime:
        if self._clock is not None:
            return parse_ts(self._clock())
        real = datetime.now(TZ)
        if self._world_now is None:
            try:
                with self._conn() as c:
                    r = c.execute("SELECT value FROM meta WHERE key='world_now'").fetchone()
                self._world_now = parse_ts(r[0]) if r else real
            except sqlite3.Error:
                self._world_now = real
        if real - self._world_now > timedelta(days=FROZEN_AFTER_DAYS):
            return self._world_now
        return real

    def ensure_schema(self) -> None:
        with self._conn() as c:
            c.executescript(self.ddl)


# ---------------------------------------------------------------- zona client


class ClientRepo(_Repo):
    """Zona client: doar `var/client_zone.db`."""

    ddl = CLIENT_DDL

    def __init__(self, db_path: str | Path | None = None, *, clock: Callable[[], datetime] | None = None):
        super().__init__(db_path, clock)

    def _default_path(self) -> Path:
        from versoml.config import get_settings
        return get_settings().client_db

    # -------- clienți, conturi
    def get_customer(self, customer_ref: str) -> dict | None:
        with self._conn() as c:
            cust = row_to_dict(c.execute("SELECT * FROM customers WHERE customer_ref=?", (customer_ref,)).fetchone())
            if cust is None:
                return None
            accounts = rows(c.execute("SELECT * FROM accounts WHERE customer_ref=? ORDER BY is_primary DESC, iban", (customer_ref,)))
            cards = rows(c.execute("SELECT * FROM cards WHERE customer_ref=? ORDER BY card_id", (customer_ref,)))
        primary = next((a for a in accounts if a.get("is_primary")), accounts[0] if accounts else None)
        cust.update(accounts=accounts, cards=cards, primary_iban=primary["iban"] if primary else None,
                    iban_masked=ids.mask_iban(primary["iban"]) if primary else None)
        return cust

    def get_account(self, customer_ref: str) -> dict | None:
        """Contul curent principal (extensie)."""
        with self._conn() as c:
            return row_to_dict(c.execute("SELECT * FROM accounts WHERE customer_ref=? ORDER BY is_primary DESC, iban LIMIT 1",
                                         (customer_ref,)).fetchone())

    def balance(self, customer_ref: str) -> float:
        acc = self.get_account(customer_ref)
        if acc is None:
            raise KeyError(f"unknown customer: {customer_ref}")
        return round(float(acc["balance"]), 2)

    # -------- tranzacții
    def get_transaction(self, tx_id: str) -> dict | None:
        with self._conn() as c:
            t = row_to_dict(c.execute("SELECT * FROM transactions WHERE tx_id=?", (tx_id,)).fetchone())
        return _flatten_extra(t)

    def list_transactions(self, customer_ref: str, days: int = 90, *, as_of: datetime | str | None = None,
                          limit: int | None = None) -> list[dict]:
        """Tranzacțiile clientului din ultimele `days` zile, cele mai noi primele."""
        end = parse_ts(as_of) if as_of else self.now()
        lo = int((end - timedelta(days=days)).timestamp())
        sql = "SELECT * FROM transactions WHERE customer_ref=? AND ts_epoch>=? AND ts_epoch<=? ORDER BY ts_epoch DESC, tx_id DESC"
        args: list[Any] = [customer_ref, lo, int(end.timestamp())]
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        with self._conn() as c:
            return [_flatten_extra(t) for t in rows(c.execute(sql, args))]

    def find_duplicates(self, tx_id: str, *, window_minutes: int = 10) -> list[dict]:
        """Tranzacții ale aceluiași client cu aceeași sumă, același comerciant/beneficiar, la cel mult N minute."""
        with self._conn() as c:
            t = c.execute("SELECT * FROM transactions WHERE tx_id=?", (tx_id,)).fetchone()
            if t is None:
                return []
            w = window_minutes * 60
            out = rows(c.execute(
                "SELECT * FROM transactions WHERE customer_ref=? AND tx_id<>? AND direction=? AND ABS(amount-?)<0.005 "
                "AND ts_epoch BETWEEN ? AND ? AND (COALESCE(merchant_id,'')=COALESCE(?,'') "
                "AND COALESCE(counterparty_iban,'')=COALESCE(?,'')) ORDER BY ts_epoch",
                (t["customer_ref"], tx_id, t["direction"], t["amount"], t["ts_epoch"] - w, t["ts_epoch"] + w,
                 t["merchant_id"], t["counterparty_iban"])))
        return [_flatten_extra(x) for x in out]

    def beneficiary_seen_before(self, customer_ref: str, iban: str, *, before: datetime | str | None = None) -> bool:
        """A mai plătit clientul acestui IBAN înainte? Fără `before`: înainte de ultima plată către el."""
        iban = ids.normalize_iban(iban)
        with self._conn() as c:
            ts = [r[0] for r in c.execute(
                "SELECT ts_epoch FROM transactions WHERE customer_ref=? AND counterparty_iban=? AND direction='debit' "
                "ORDER BY ts_epoch", (customer_ref, iban))]
            payee = c.execute("SELECT created_at FROM payees WHERE customer_ref=? AND iban=?", (customer_ref, iban)).fetchone()
        ref = epoch(before) if before else (ts[-1] if ts else None)
        if ref is None:
            return payee is not None
        if any(x < ref - 60 for x in ts):
            return True
        return payee is not None and (epoch(payee[0]) or ref) < ref - 60

    # -------- SCA, dispozitive, sesiuni, SIM
    def get_auth_events(self, tx_id: str) -> list[dict]:
        """Autentificările legate de tranzacție: cele cu tx_id-ul ei și cele din aceeași sesiune (ex. înrolarea)."""
        with self._conn() as c:
            t = c.execute("SELECT session_id FROM transactions WHERE tx_id=?", (tx_id,)).fetchone()
            sid = t["session_id"] if t else None
            return rows(c.execute("SELECT * FROM auth_events WHERE tx_id=? OR (session_id IS NOT NULL AND session_id=?) "
                                  "ORDER BY ts_epoch, auth_id", (tx_id, sid)))

    def get_device_history(self, customer_ref: str) -> list[dict]:
        with self._conn() as c:
            return rows(c.execute("SELECT * FROM devices WHERE customer_ref=? ORDER BY enrolled_epoch, device_id", (customer_ref,)))

    def get_session(self, session_id: str) -> dict | None:
        with self._conn() as c:
            return row_to_dict(c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone())

    def sim_swap_events(self, customer_ref: str, before: datetime | str, hours: int = 48) -> list[dict]:
        end = parse_ts(before)
        with self._conn() as c:
            return rows(c.execute("SELECT * FROM sim_events WHERE customer_ref=? AND ts_epoch BETWEEN ? AND ? ORDER BY ts_epoch",
                                  (customer_ref, int((end - timedelta(hours=hours)).timestamp()), int(end.timestamp()))))

    def get_prior_disputes(self, customer_ref: str, months: int = 12, *, as_of: datetime | str | None = None,
                           exclude_case_id: str | None = None) -> list[dict]:
        """The customer's disputes in the `months` before `as_of` (default: now), oldest first.

        Two sources, each row tagged with `source`:
        - "archive": the closed disputes written by the seed (`prior_disputes`);
        - "live": complaints filed in this session (`complaints`, historical=0), dated by `received_at`.
        The case under analysis never counts as its own prior dispute. Pass `exclude_case_id`; with `as_of`,
        only complaints received strictly before it count; with neither, the customer's latest live
        complaint is taken to be the case under analysis (the collector reads this right after the save).
        """
        end = parse_ts(as_of) if as_of else self.now()
        lo, hi = int((end - timedelta(days=round(months * 365 / 12))).timestamp()), int(end.timestamp())
        sql = "SELECT * FROM complaints WHERE customer_ref=? AND COALESCE(historical,0)=0 AND received_epoch>=?"
        args: list[Any] = [customer_ref, lo]
        if as_of:
            sql += " AND received_epoch<?"
            args.append(hi)
        with self._conn() as c:
            archived = rows(c.execute("SELECT * FROM prior_disputes WHERE customer_ref=? AND opened_epoch>=? AND opened_epoch<? "
                                      "ORDER BY opened_epoch", (customer_ref, lo, hi)))
            live = rows(c.execute(sql + " ORDER BY received_epoch, case_id", args))
            if not as_of and exclude_case_id is None and live:
                live = live[:-1]        # the latest complaint is the case being analysed
            skip = {d["case_id"] for d in archived} | {exclude_case_id}
            live = [x for x in live if x["case_id"] not in skip]
            refs = [x["transaction_refs"][0] for x in live if x.get("transaction_refs")]
            txs = {t["tx_id"]: t for t in rows(c.execute(
                f"SELECT tx_id, amount, counterparty_name, channel FROM transactions WHERE tx_id IN ({','.join('?' * len(refs))})",
                refs))} if refs else {}
        for d in archived:
            d["source"] = "archive"
        out = archived + [_live_dispute(x, txs) for x in live]
        return sorted(out, key=lambda d: (epoch(d["opened_at"]) or 0, d["case_id"] or ""))

    def get_merchant(self, merchant_id: str) -> dict | None:
        with self._conn() as c:
            return row_to_dict(c.execute("SELECT * FROM merchants WHERE merchant_id=?", (merchant_id,)).fetchone())

    # -------- identificarea clientului (reclamații libere, fără customer_ref)
    def world_now(self) -> datetime | None:
        """Momentul lumii sintetice (meta.world_now), referința pentru datele relative din setul de aur."""
        try:
            with self._conn() as c:
                r = c.execute("SELECT value FROM meta WHERE key='world_now'").fetchone()
        except sqlite3.Error:
            return None
        return parse_ts(r[0]) if r else None

    def customer_index(self) -> list[dict]:
        """Toți clienții, cu câmpurile de identificare (nume, telefon, e-mail, oraș). Doar în zona client."""
        with self._conn() as c:
            return rows(c.execute("SELECT customer_ref, first_name, last_name, full_name, phone, email, city "
                                  "FROM customers ORDER BY customer_ref"))

    def find_customer_by_iban(self, iban: str) -> str | None:
        """Clientul care deține IBAN-ul (unul dintre conturile lui), sau None."""
        try:
            norm = ids.normalize_iban(iban)
        except Exception:  # noqa: BLE001 - un IBAN malformat nu identifică pe nimeni
            return None
        with self._conn() as c:
            r = c.execute("SELECT customer_ref FROM accounts WHERE iban=?", (norm,)).fetchone()
        return r[0] if r else None

    def find_customers_by_phone(self, phone: str) -> list[str]:
        """Clienții cu numărul de telefon dat (comparat în forma E.164)."""
        norm = ids.normalize_phone(phone)
        if len(norm) < 8:
            return []
        with self._conn() as c:
            refs = [r[0] for r in c.execute("SELECT customer_ref, phone FROM customers WHERE phone IS NOT NULL")
                    if ids.normalize_phone(r[1] or "") == norm]
        return sorted(set(refs))

    def find_customers_by_email(self, email: str) -> list[str]:
        """Clienții cu adresa de e-mail dată (fără diferență de majuscule)."""
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT customer_ref FROM customers WHERE lower(email)=lower(?) "
                                            "ORDER BY customer_ref", ((email or "").strip(),))]

    def get_card(self, card_id: str) -> dict | None:
        """The card a payment was made with: scheme, product, masked number."""
        with self._conn() as c:
            return row_to_dict(c.execute("SELECT card_id, customer_ref, scheme, product, last4, status FROM cards "
                                         "WHERE card_id=?", (card_id,)).fetchone())

    def customer_cards_last4(self, customer_ref: str) -> dict[str, str]:
        """card_id -> ultimele 4 cifre, pentru cardurile clientului."""
        with self._conn() as c:
            return {r[0]: r[1] for r in c.execute("SELECT card_id, last4 FROM cards WHERE customer_ref=?", (customer_ref,))
                    if r[1]}

    def get_merchants(self, merchant_ids: Iterable[str]) -> dict[str, dict]:
        """Comercianții după ID (o singură interogare)."""
        wanted = sorted({m for m in merchant_ids if m})
        if not wanted:
            return {}
        with self._conn() as c:
            q = ",".join("?" for _ in wanted)
            return {r["merchant_id"]: r for r in rows(c.execute(f"SELECT * FROM merchants WHERE merchant_id IN ({q})",
                                                                 wanted))}

    def disputed_tx_ids(self, customer_ref: str, *, exclude_case_id: str | None = None) -> dict[str, str]:
        """Plățile clientului cu o contestație deschisă în sesiunea curentă: tx_id -> ID-ul cazului. Disputele
        închise din arhivă nu contează (clientul poate reveni asupra aceleiași plăți)."""
        out: dict[str, str] = {}
        with self._conn() as c:
            for r in c.execute("SELECT case_id, transaction_refs_json FROM complaints WHERE customer_ref=? "
                               "AND COALESCE(historical,0)=0", (customer_ref,)):
                if r[0] == exclude_case_id:
                    continue
                for ref in json.loads(r[1]) if r[1] else []:
                    out.setdefault(ref, r[0])
        return out

    def refunded_tx_ids(self, customer_ref: str) -> dict[str, str]:
        """Plățile clientului deja rambursate: tx_id -> ID-ul cazului care le-a rambursat."""
        out: dict[str, str] = {}
        with self._conn() as c:
            for r in c.execute("SELECT r.case_id, c.transaction_refs_json FROM refunds r "
                               "JOIN complaints c ON c.case_id = r.case_id WHERE r.customer_ref=?", (customer_ref,)):
                for ref in json.loads(r[1]) if r[1] else []:
                    out.setdefault(ref, r[0])
        return out

    def search_customers(self, q: str, limit: int = 20) -> list[dict]:
        """Căutarea din consolă: după referință, nume, telefon, e-mail sau IBAN. Întoarce doar câmpuri afișabile
        (referința, orașul, conturile mascate, ultima tranzacție), fără nume, CNP sau date de contact."""
        from versoml.data.text import fold as _fold

        q = (q or "").strip()
        limit = max(1, min(int(limit or 20), 20))
        with self._conn() as c:
            if not q:
                refs = [r[0] for r in c.execute("SELECT customer_ref FROM customers ORDER BY customer_ref LIMIT ?", (limit,))]
            else:
                needle = _fold(q)
                digits = "".join(ch for ch in q if ch.isdigit())
                compact = q.replace(" ", "").upper()
                refs = []
                for r in c.execute("SELECT customer_ref, full_name, phone, email FROM customers ORDER BY customer_ref"):
                    if (needle in _fold(r[0]) or needle in _fold(r[1] or "") or needle in (r[3] or "").lower()
                            or (len(digits) >= 6 and digits in "".join(ch for ch in (r[2] or "") if ch.isdigit()))):
                        refs.append(r[0])
                if compact.startswith("RO") and len(compact) >= 8:
                    refs += [r[0] for r in c.execute("SELECT customer_ref FROM accounts WHERE iban LIKE ?", (compact + "%",))]
                refs = list(dict.fromkeys(refs))[:limit]
            out = []
            for ref in refs:
                cust = c.execute("SELECT city FROM customers WHERE customer_ref=?", (ref,)).fetchone()
                accounts = [ids.mask_iban(a[0]) for a in c.execute(
                    "SELECT iban FROM accounts WHERE customer_ref=? ORDER BY is_primary DESC, iban", (ref,))]
                last = c.execute("SELECT ts FROM transactions WHERE customer_ref=? ORDER BY ts_epoch DESC LIMIT 1",
                                 (ref,)).fetchone()
                out.append({"customer_ref": ref, "city": cust[0] if cust else None, "accounts": accounts,
                            "last_tx_at": last[0] if last else None})
        return out

    def update_complaint_identity(self, case_id: str, customer_ref: str | None, transaction_refs: list[str]) -> None:
        """Extensie: după identificare, reclamația liberă primește clientul și plata găsite (pentru istoricul de
        dispute al clientului). Textul rămâne cel primit."""
        with self._tx() as c:
            c.execute("UPDATE complaints SET customer_ref=COALESCE(?, customer_ref), transaction_refs_json=? WHERE case_id=?",
                      (customer_ref, json.dumps(list(transaction_refs or []), ensure_ascii=False), case_id))

    # -------- reclamații
    def save_complaint(self, complaint: Complaint) -> None:
        """Salvează (sau actualizează) reclamația. Textul rămâne neîncrezut: se stochează, nu se interpretează."""
        d = complaint.model_dump(mode="json")
        rec = {"case_id": d["case_id"], "customer_ref": d["customer_ref"], "received_at": iso(complaint.received_at),
               "received_epoch": epoch(complaint.received_at), "channel_hint": d.get("channel_hint"), "source": d["source"],
               "text": d["text"], "attachments_json": d["attachments"], "transaction_refs_json": d["transaction_refs"],
               "status": "NOU", "historical": 0, "outcome": None, "scenario": None, "saved_at": iso(self.now()),
               "synthetic": d.get("synthetic", True)}
        with self._tx() as c:
            old = c.execute("SELECT status FROM complaints WHERE case_id=?", (rec["case_id"],)).fetchone()
            if old is not None and old["status"]:
                rec["status"] = old["status"]
            insert(c, "complaints", [rec], list(rec), mode="INSERT OR REPLACE")

    def list_complaints(self, *, include_historical: bool = False) -> list[dict]:
        sql = "SELECT * FROM complaints" + ("" if include_historical else " WHERE COALESCE(historical,0)=0")
        with self._conn() as c:
            return rows(c.execute(sql + " ORDER BY received_epoch DESC, case_id"))

    def get_complaint(self, case_id: str) -> dict | None:
        """Dict compatibil cu `Complaint.model_validate` (plus status, historical)."""
        with self._conn() as c:
            return row_to_dict(c.execute("SELECT * FROM complaints WHERE case_id=?", (case_id,)).fetchone())

    def set_complaint_status(self, case_id: str, status: str) -> None:
        """Extensie: statusul cazului (NOU, IN_ANALIZA, ...)."""
        with self._tx() as c:
            c.execute("UPDATE complaints SET status=? WHERE case_id=?", (status, case_id))

    # -------- Banca Demo: notificări, plăți, rambursări
    def list_notifications(self, customer_ref: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            return rows(c.execute("SELECT * FROM notifications WHERE customer_ref=? ORDER BY ts_epoch DESC, notification_id DESC LIMIT ?",
                                  (customer_ref, limit)))

    def _notify(self, c: sqlite3.Connection, customer_ref: str, ts: datetime, kind: str, text: str) -> None:
        nid = f"NTF-L-{uuid.uuid4().hex[:12].upper()}"
        insert(c, "notifications", [{"notification_id": nid, "customer_ref": customer_ref, "ts": iso(ts),
                                     "ts_epoch": epoch(ts), "kind": kind, "text": text, "read": 0, "synthetic": 1}],
               ["notification_id", "customer_ref", "ts", "ts_epoch", "kind", "text", "read", "synthetic"])

    def post_transfer(self, from_ref: str, to_iban: str, amount: float, meta: dict | None = None) -> dict:
        """Plată simulată din contul principal al clientului (Banca Demo). Idempotentă pe `meta["idempotency_key"]`
        sau `meta["tx_id"]`. `meta` poate aduce: ts, channel, beneficiary_name, description, device_id, ip,
        new_device (dict), session (dict), auth_events (listă), end_to_end_id, scenario, case_id."""
        meta = dict(meta or {})
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("the amount must be positive")
        to_iban = ids.normalize_iban(to_iban)
        if ids.validate_iban_ro(to_iban):
            raise ValueError(f"invalid IBAN: {to_iban}")
        ts = parse_ts(meta.get("ts")) or self.now()
        key = meta.get("idempotency_key") or meta.get("tx_id")
        with self._tx() as c:
            if key:
                old = c.execute("SELECT * FROM transactions WHERE idempotency_key=? OR tx_id=?", (key, meta.get("tx_id") or key)).fetchone()
                if old is not None:
                    t = row_to_dict(old)
                    return {"tx_id": t["tx_id"], "from_ref": from_ref, "from_iban": t["account_iban"], "to_iban": t["counterparty_iban"],
                            "amount": t["amount"], "currency": t["currency"], "ts": t["ts"], "status": t["status"],
                            "balance_after": t["balance_after"], "session_id": t["session_id"], "device_id": t["device_id"],
                            "created": False}
            acc = c.execute("SELECT * FROM accounts WHERE customer_ref=? ORDER BY is_primary DESC, iban LIMIT 1", (from_ref,)).fetchone()
            if acc is None:
                raise KeyError(f"unknown customer: {from_ref}")
            if acc["balance"] + 1e-9 < amount:
                return {"tx_id": None, "from_ref": from_ref, "from_iban": acc["iban"], "to_iban": to_iban, "amount": amount,
                        "currency": "RON", "ts": iso(ts), "status": "respins_fonduri_insuficiente",
                        "balance_after": acc["balance"], "created": False}
            tx_id = meta.get("tx_id") or f"TX-LIVE-{uuid.uuid4().hex[:10].upper()}"
            dev = meta.get("new_device")
            if dev:
                d = dict(dev, customer_ref=from_ref, enrolled_epoch=epoch(dev.get("enrolled_at") or ts))
                insert(c, "devices", [d], table_columns(c, "devices"), mode="INSERT OR IGNORE")
                self._notify(c, from_ref, parse_ts(dev.get("enrolled_at")) or ts, "securitate",
                             f"The Demo Bank app was activated on a new device ({dev.get('model') or 'unknown model'}).")
            device_id = meta.get("device_id") or (dev or {}).get("device_id")
            if device_id is None:
                r = c.execute("SELECT device_id FROM devices WHERE customer_ref=? AND status='activ' ORDER BY enrolled_epoch DESC LIMIT 1",
                              (from_ref,)).fetchone()
                device_id = r[0] if r else None
            ses = meta.get("session")
            session_id = None
            if ses:
                s = dict(ses, customer_ref=from_ref, started_epoch=epoch(ses.get("started_at") or ts))
                insert(c, "sessions", [s], table_columns(c, "sessions"), mode="INSERT OR REPLACE")
                session_id = s["session_id"]
            auths = meta.get("auth_events")
            if auths is None:   # implicit: aprobare în aplicație, cu suma și beneficiarul afișate
                auths = [{"auth_id": f"AUTH-L-{uuid.uuid4().hex[:10].upper()}", "customer_ref": from_ref, "tx_id": tx_id,
                          "session_id": session_id, "device_id": device_id, "ts": iso(ts - timedelta(seconds=15)),
                          "method": "app_push", "purpose": "payment", "result": "approved",
                          "screen_showed_amount_and_payee": True, "shown_amount": amount,
                          "shown_payee": meta.get("beneficiary_name"), "otp_text": None, "phone": None, "eci": None,
                          "cavv": None, "cavv_present": None, "three_ds_version": None, "flow_version": "2026-04",
                          "ip": meta.get("ip"), "synthetic": True}]
            for a in auths:
                a = dict(a, customer_ref=from_ref, ts_epoch=epoch(a.get("ts") or ts))
                if a.get("purpose") == "payment" and not a.get("tx_id"):
                    a["tx_id"] = tx_id
                insert(c, "auth_events", [a], table_columns(c, "auth_events"), mode="INSERT OR IGNORE")
            new_balance = round(acc["balance"] - amount, 2)
            name = meta.get("beneficiary_name") or "payee"
            known = {"ts", "channel", "beneficiary_name", "description", "device_id", "ip", "new_device", "session",
                     "auth_events", "end_to_end_id", "tx_id", "idempotency_key", "scenario"}
            extra = {k: v for k, v in meta.items() if k not in known}
            t = {"tx_id": tx_id, "customer_ref": from_ref, "account_iban": acc["iban"], "direction": "debit",
                 "kind": "transfer", "channel": meta.get("channel") or "transfer", "amount": amount, "currency": "RON",
                 "ts": iso(ts), "ts_epoch": epoch(ts), "booked_at": iso(ts),
                 "description": meta.get("description") or f"Transfer to {name}", "counterparty_name": name,
                 "counterparty_iban": to_iban, "merchant_id": None, "mcc": None, "card_id": None, "pos_entry_mode": None,
                 "eci": None, "cavv_present": None, "merchant_country": None, "device_id": device_id,
                 "session_id": session_id, "ip": meta.get("ip"), "status": "booked",
                 "end_to_end_id": meta.get("end_to_end_id") or f"E2E{uuid.uuid4().hex[:12].upper()}", "disputable": 1,
                 "case_tag": meta.get("scenario"), "balance_after": new_balance, "idempotency_key": key,
                 "extra_json": extra or None, "synthetic": 1}
            insert(c, "transactions", [t], list(t))
            c.execute("UPDATE accounts SET balance=? WHERE iban=?", (new_balance, acc["iban"]))
            self._notify(c, from_ref, ts, "tranzactie", f"You sent {fmt_ron(amount)} to {name}.")
        return {"tx_id": tx_id, "from_ref": from_ref, "from_iban": acc["iban"], "to_iban": to_iban, "amount": amount,
                "currency": "RON", "ts": iso(ts), "status": "booked", "balance_after": new_balance,
                "session_id": session_id, "device_id": device_id, "created": True}

    def post_refund(self, case_id: str, customer_ref: str, amount: float, idempotency_key: str) -> dict:
        """Rambursare (instrucțiune simulată, emisă de motorul de reguli). Aceeași cheie => același rezultat,
        fără a credita încă o dată. Reutilizarea cheii pentru alt caz sau altă sumă e o eroare."""
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("the amount must be positive")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        ts = self.now()
        with self._tx() as c:
            old = c.execute("SELECT * FROM refunds WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if old is not None:
                o = row_to_dict(old)
                if o["case_id"] != case_id or o["customer_ref"] != customer_ref or abs(o["amount"] - amount) > 0.005:
                    raise ValueError("idempotency_key was already used for another case or another amount")
                bal = c.execute("SELECT balance FROM accounts WHERE customer_ref=? ORDER BY is_primary DESC LIMIT 1",
                                (customer_ref,)).fetchone()[0]
                return {**o, "balance_after": round(bal, 2), "created": False, "idempotent_replay": True}
            acc = c.execute("SELECT * FROM accounts WHERE customer_ref=? ORDER BY is_primary DESC, iban LIMIT 1",
                            (customer_ref,)).fetchone()
            if acc is None:
                raise KeyError(f"unknown customer: {customer_ref}")
            h = hashlib.sha256(idempotency_key.encode()).hexdigest()[:10].upper()
            tx_id, refund_id = f"TX-RF-{h}", f"RF-{h}"
            new_balance = round(acc["balance"] + amount, 2)
            t = {"tx_id": tx_id, "customer_ref": customer_ref, "account_iban": acc["iban"], "direction": "credit",
                 "kind": "refund", "channel": "internal", "amount": amount, "currency": "RON", "ts": iso(ts),
                 "ts_epoch": epoch(ts), "booked_at": iso(ts), "description": f"Refund for dispute {case_id}",
                 "counterparty_name": art.BANK_NAME, "counterparty_iban": None, "status": "booked", "disputable": 0,
                 "case_tag": case_id, "balance_after": new_balance, "idempotency_key": f"refund:{idempotency_key}",
                 "synthetic": 1}
            insert(c, "transactions", [t], list(t))
            c.execute("UPDATE accounts SET balance=? WHERE iban=?", (new_balance, acc["iban"]))
            r = {"refund_id": refund_id, "case_id": case_id, "customer_ref": customer_ref, "amount": amount,
                 "currency": "RON", "idempotency_key": idempotency_key, "tx_id": tx_id, "ts": iso(ts),
                 "status": "executat", "synthetic": 1}
            insert(c, "refunds", [r], list(r))
            self._notify(c, customer_ref, ts, "rambursare", f"We refunded {fmt_ron(amount)} for dispute {case_id}.")
        return {**r, "synthetic": True, "balance_after": new_balance, "created": True, "idempotent_replay": False}

    # -------- scenarii live
    def apply_scenario(self, bundle: Any) -> dict:
        """Extensie: aplică idempotent plata unui scenariu live (demo_t1, demo_t1_victima2), cu dispozitivul,
        sesiunea și autentificările ei. Pentru scenariile deja scrise la seed nu face nimic."""
        args = (bundle.records if hasattr(bundle, "records") else bundle["records"]).get("post_transfer")
        if not args:
            tx = (bundle.records if hasattr(bundle, "records") else bundle["records"])["transaction"]
            return {"tx_id": tx["tx_id"], "created": False, "status": "seeded"}
        return self.post_transfer(args["from_ref"], args["to_iban"], args["amount"], args["meta"])


def _live_dispute(complaint: dict, txs: dict[str, dict]) -> dict:
    """A complaint filed live, in the shape of a `prior_disputes` row."""
    refs = complaint.get("transaction_refs") or []
    tx = (txs.get(refs[0]) if refs else None) or {}
    return {"dispute_id": f"LIVE-{complaint['case_id']}", "customer_ref": complaint["customer_ref"],
            "case_id": complaint["case_id"], "tx_ref": refs[0] if refs else None, "opened_at": complaint["received_at"],
            "closed_at": None, "channel": complaint.get("channel_hint") or tx.get("channel"), "dispute_type": None,
            "scenario": complaint.get("scenario"), "amount": tx.get("amount"), "counterparty": tx.get("counterparty_name"),
            "outcome": None, "reason": None, "status": complaint.get("status"), "source": "live",
            "synthetic": bool(complaint.get("synthetic", True))}


def _flatten_extra(t: dict | None) -> dict | None:
    if t is None:
        return None
    extra = t.pop("extra", None) or {}
    for k, v in extra.items():
        t.setdefault(k, v)
    return t


# ---------------------------------------------------------------- zona AML


class AmlRepo(_Repo):
    """Zona AML: doar `var/aml_zone.db`. Profiluri obiective de cont, fără date demografice."""

    ddl = AML_DDL

    def __init__(self, db_path: str | Path | None = None, *, clock: Callable[[], datetime] | None = None):
        super().__init__(db_path, clock)

    def _default_path(self) -> Path:
        from versoml.config import get_settings
        return get_settings().aml_db

    def _accounts(self, c: sqlite3.Connection, nodes: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(nodes), 500):
            chunk = nodes[i:i + 500]
            q = ",".join("?" for _ in chunk)
            for r in rows(c.execute(f"SELECT * FROM accounts WHERE iban IN ({q})", chunk)):
                out[r["iban"]] = r
        for n in nodes:
            out.setdefault(n, {"iban": n, "kind": "external", "holder_type": "necunoscut", "opened_at": None})
        return out

    def _flows_of(self, c: sqlite3.Connection, nodes: list[str], lo: int, hi: int) -> list[dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(nodes), 400):
            chunk = nodes[i:i + 400]
            q = ",".join("?" for _ in chunk)
            for r in rows(c.execute(f"SELECT * FROM flows WHERE from_iban IN ({q}) AND ts_epoch>? AND ts_epoch<=?", chunk + [lo, hi])):
                out[r["flow_id"]] = r
            for r in rows(c.execute(f"SELECT * FROM flows WHERE to_iban IN ({q}) AND ts_epoch>? AND ts_epoch<=?", chunk + [lo, hi])):
                out[r["flow_id"]] = r
        return sorted(out.values(), key=lambda f: (f["ts"], f["flow_id"]))

    def account_profile(self, iban: str) -> dict | None:
        """Profil obiectiv: tip, vechime, rulaj, contrapartide, alerte. Fără vârstă, gen sau naționalitate."""
        iban = ids.normalize_iban(iban) if iban != art.CASH_NODE else iban
        now = self.now()
        with self._conn() as c:
            acc = row_to_dict(c.execute("SELECT * FROM accounts WHERE iban=?", (iban,)).fetchone())
            if acc is None:
                return None
            hi = int(now.timestamp())
            lo30, lo90 = int((now - timedelta(days=30)).timestamp()), int((now - timedelta(days=90)).timestamp())
            q = c.execute(
                "SELECT "
                " SUM(CASE WHEN to_iban=? AND ts_epoch>? THEN amount END), SUM(CASE WHEN to_iban=? AND ts_epoch>? THEN 1 END),"
                " SUM(CASE WHEN from_iban=? AND ts_epoch>? THEN amount END), SUM(CASE WHEN from_iban=? AND ts_epoch>? THEN 1 END),"
                " SUM(amount) FROM flows WHERE (from_iban=? OR to_iban=?) AND ts_epoch>? AND ts_epoch<=?",
                (iban, lo30, iban, lo30, iban, lo30, iban, lo30, iban, iban, lo90, hi)).fetchone()
            cps = c.execute("SELECT COUNT(DISTINCT cp) FROM (SELECT to_iban AS cp FROM flows WHERE from_iban=? AND ts_epoch>? "
                            "UNION SELECT from_iban FROM flows WHERE to_iban=? AND ts_epoch>?)", (iban, lo30, iban, lo30)).fetchone()[0]
            n_alerts = c.execute("SELECT COUNT(*) FROM alerts WHERE iban=?", (iban,)).fetchone()[0]
            n_ref = c.execute("SELECT COUNT(*) FROM referrals WHERE beneficiary_iban=?", (iban,)).fetchone()[0]
        opened = parse_ts(acc.get("opened_at")) if acc.get("opened_at") else None
        acc.update({
            "age_days": (now - opened).days if opened else None,
            "turnover_30d_in": round(q[0] or 0.0, 2), "flows_30d_in": int(q[1] or 0),
            "turnover_30d_out": round(q[2] or 0.0, 2), "flows_30d_out": int(q[3] or 0),
            "avg_monthly_turnover_90d": round((q[4] or 0.0) / 3, 2), "counterparties_30d": int(cps or 0),
            "alerts": int(n_alerts), "referrals": int(n_ref), "as_of": iso(now)})
        return acc

    def flows(self, iban: str, days: int = 30, *, as_of: datetime | str | None = None) -> list[dict]:
        end = parse_ts(as_of) if as_of else self.now()
        node = ids.normalize_iban(iban) if iban != art.CASH_NODE else iban
        with self._conn() as c:
            return self._flows_of(c, [node], int((end - timedelta(days=days)).timestamp()), int(end.timestamp()))

    def neighborhood(self, ibans: list[str], hops: int = 2, days: int = 30, *, as_of: datetime | str | None = None,
                     hub_degree: int = HUB_DEGREE) -> dict:
        """Subgraful din jurul conturilor: {nodes, edges}. Hub-urile (exchange, numerar, noduri cu peste
        `hub_degree` contrapartide) intră în graf, dar nu se expandează. Fiecare nod are `features`
        (trăsăturile obiective din toată fereastra, aceleași ca la antrenarea M5)."""
        end = parse_ts(as_of) if as_of else self.now()
        lo, hi = int((end - timedelta(days=days)).timestamp()), int(end.timestamp())
        seeds = [ids.normalize_iban(i) if i != art.CASH_NODE else i for i in ibans]
        hop_of: dict[str, int] = {s: 0 for s in seeds}
        edges: dict[str, dict] = {}
        feats: dict[str, dict] = {}
        with self._conn() as c:
            accounts = self._accounts(c, seeds)

            def compute(nodes: list[str]) -> None:
                todo = [n for n in nodes if n not in feats]
                if not todo:
                    return
                accounts.update(self._accounts(c, [n for n in todo if n not in accounts]))
                fl = self._flows_of(c, todo, lo, hi)
                cps = sorted({f["from_iban"] for f in fl} | {f["to_iban"] for f in fl})
                accounts.update(self._accounts(c, [n for n in cps if n not in accounts]))
                feats.update(node_features(fl, accounts, as_of=end, days=days, nodes=todo))

            compute(seeds)
            frontier = list(seeds)
            for h in range(hops):
                expand = [n for n in frontier if h == 0 or not is_hub(accounts.get(n, {}).get("kind"), feats.get(n), hub_degree)]
                for f in self._flows_of(c, expand, lo, hi):
                    edges[f["flow_id"]] = f
                    for end_node in (f["from_iban"], f["to_iban"]):
                        hop_of.setdefault(end_node, h + 1)
                frontier = [n for n, k in hop_of.items() if k == h + 1]
                compute(frontier)
            compute(list(hop_of))
            nodes_list = sorted(hop_of, key=lambda n: (hop_of[n], n))
            accounts.update(self._accounts(c, [n for n in nodes_list if n not in accounts]))
            q = ",".join("?" for _ in nodes_list) or "''"
            companies = {r["iban"]: r for r in rows(c.execute(f"SELECT iban, name, role, cui FROM companies WHERE iban IN ({q})", nodes_list))}
            alerted = {r[0] for r in c.execute(f"SELECT DISTINCT iban FROM alerts WHERE iban IN ({q})", nodes_list)}
            refs = rows(c.execute(f"SELECT case_id, beneficiary_iban, flow_id FROM referrals WHERE beneficiary_iban IN ({q})", nodes_list))
        victim_cases: dict[str, list[str]] = {}
        for e in edges.values():
            if e.get("case_id"):
                victim_cases.setdefault(e["from_iban"], []).append(e["case_id"])
        nodes = []
        for n in nodes_list:
            a = accounts.get(n, {})
            kind = a.get("kind") or "external"
            comp = companies.get(n)
            role = ("exchange" if kind == "exchange" else "numerar" if kind == "cash" else
                    "victima" if n in victim_cases else
                    "comerciant" if comp and comp.get("role") in ("comerciant", "micro_merchant") else "cont")
            opened = parse_ts(a.get("opened_at")) if a.get("opened_at") else None
            label = a.get("holder_name") or (comp or {}).get("name") or (ids.mask_iban(n) if n.startswith("RO") else n)
            nodes.append({"id": n, "iban": n if n.startswith("RO") else None, "label": label, "kind": kind,
                          "role_hint": role, "bank_code": a.get("bank_code"), "holder_type": a.get("holder_type"),
                          "account_type": a.get("account_type"), "opened_at": a.get("opened_at"),
                          "age_days": (end - opened).days if opened else None, "hop": hop_of[n], "is_seed": n in seeds,
                          "hub": is_hub(kind, feats.get(n), hub_degree), "flagged": n in alerted,
                          "victim_case_ids": sorted(set(victim_cases.get(n, []))), "features": feats.get(n, {}),
                          "synthetic": True})
        edge_list = [{"id": e["flow_id"], "source": e["from_iban"], "target": e["to_iban"], "amount": e["amount"],
                      "currency": e.get("currency") or "RON", "ts": e["ts"], "channel": e.get("channel"),
                      "kind": e.get("channel"), "case_id": e.get("case_id"), "reported_fraud": bool(e.get("reported_fraud")),
                      "report_source": e.get("report_source"), "feed": e.get("feed")}
                     for e in sorted(edges.values(), key=lambda f: (f["ts"], f["flow_id"]))]
        return {"nodes": nodes, "edges": edge_list, "seeds": seeds, "hops": hops, "days": days, "as_of": iso(end),
                "hub_degree": hub_degree, "referrals": refs}

    def list_alerts(self) -> list[dict]:
        with self._conn() as c:
            return rows(c.execute("SELECT * FROM alerts ORDER BY ts DESC, alert_id"))

    def save_referral(self, facts: DisputeFacts) -> None:
        """Primește o sesizare (DisputeFacts, prin diodă) și o leagă de fluxul plății, dacă îl găsește."""
        d = facts.model_dump(mode="json")
        ben = d["beneficiary"]
        att = d.get("attack") or {}
        ben_iban = ids.normalize_iban(ben.get("iban")) if ben.get("iban") else None
        ex = parse_ts(facts.executed_at)
        rec = {"case_id": d["case_id"], "received_at": iso(self.now()), "victim_ref": d["victim_ref"],
               "channel": d["channel"], "dispute_type": d["dispute_type"], "scenario": d.get("scenario"),
               "amount": d["amount"]["value"], "currency": d["amount"].get("currency", "RON"), "executed_at": iso(ex),
               "beneficiary_iban": ben_iban, "beneficiary_name": ben.get("name"), "beneficiary_cui": ben.get("cui"),
               "beneficiary_bic": ben.get("bank_bic"), "domain": att.get("domain"), "url": att.get("url"),
               "phone": att.get("phone"), "domain_age_hours": att.get("domain_age_hours"),
               "lookalike_score": att.get("lookalike_score"), "fact_ids_json": d.get("fact_ids") or [],
               "payload_json": d, "lead_id": None, "flow_id": None, "synthetic": 1}
        with self._tx() as c:
            old = c.execute("SELECT lead_id FROM referrals WHERE case_id=?", (rec["case_id"],)).fetchone()
            if old is not None:
                rec["lead_id"] = old["lead_id"]
            flow_id = None
            if ben_iban:
                cand = c.execute("SELECT flow_id FROM flows WHERE to_iban=? AND ABS(amount-?)<0.005 AND ABS(ts_epoch-?)<=900 "
                                 "ORDER BY ABS(ts_epoch-?), flow_id LIMIT 1",
                                 (ben_iban, rec["amount"], epoch(ex), epoch(ex))).fetchone()
                if cand is not None:
                    flow_id = cand[0]
                    c.execute("UPDATE flows SET reported_fraud=1, report_source='dispute_intern', case_id=? WHERE flow_id=?",
                              (rec["case_id"], flow_id))
                else:
                    flow_id = f"FL-REF-{hashlib.sha256(rec['case_id'].encode()).hexdigest()[:10].upper()}"
                    _ensure_account(c, d["victim_ref"], kind="victim_ref")
                    _ensure_account(c, ben_iban)
                    insert(c, "flows", [{"flow_id": flow_id, "ts": iso(ex), "ts_epoch": epoch(ex), "from_iban": d["victim_ref"],
                                         "to_iban": ben_iban, "amount": rec["amount"], "currency": rec["currency"],
                                         "channel": d["channel"], "reference": "Disputed payment", "reported_fraud": 1,
                                         "report_source": "dispute_intern", "case_id": rec["case_id"], "feed": "referral",
                                         "natural_key": f"ref:{rec['case_id']}", "synthetic": 1}],
                           ["flow_id", "ts", "ts_epoch", "from_iban", "to_iban", "amount", "currency", "channel", "reference",
                            "reported_fraud", "report_source", "case_id", "feed", "natural_key", "synthetic"], mode="INSERT OR IGNORE")
            rec["flow_id"] = flow_id
            insert(c, "referrals", [rec], list(rec), mode="INSERT OR REPLACE")

    def list_referrals(self) -> list[dict]:
        with self._conn() as c:
            return rows(c.execute("SELECT * FROM referrals ORDER BY received_at, case_id"))

    def get_referral(self, case_id: str) -> dict | None:
        with self._conn() as c:
            return row_to_dict(c.execute("SELECT * FROM referrals WHERE case_id=?", (case_id,)).fetchone())

    def set_referral_lead(self, case_id: str, lead_id: str) -> None:
        """Extensie: leagă sesizarea de pista AML în care a intrat."""
        with self._tx() as c:
            c.execute("UPDATE referrals SET lead_id=? WHERE case_id=?", (lead_id, case_id))

    def ingest_demo_payment(self, from_ref: str, to_iban: str, amount: float, ts: datetime | str) -> None:
        """Evenimentul din fluxul core banking pentru o plată live din demo. `from_ref` = IBAN-ul plătitorului
        (recomandat; îl întoarce `ClientRepo.post_transfer` ca `from_iban`) sau referința clientului, care se
        rezolvă prin pseudonimul titularului (zona AML nu ține referințe de client în clar). Idempotent."""
        to_node = ids.normalize_iban(to_iban)
        when = parse_ts(ts)
        amount = round(float(amount), 2)
        with self._tx() as c:
            if from_ref.upper().startswith("RO") and not ids.validate_iban_ro(from_ref):
                frm = ids.normalize_iban(from_ref)
            else:
                r = c.execute("SELECT iban FROM accounts WHERE holder_ref=? AND kind='internal' ORDER BY account_type, iban LIMIT 1",
                              (ids.pseudonym("TIT", from_ref),)).fetchone()
                frm = r[0] if r else ids.pseudonym("TIT", from_ref)
            _ensure_account(c, frm)
            _ensure_account(c, to_node)
            key = hashlib.sha256(f"{frm}|{to_node}|{amount:.2f}|{epoch(when)}".encode()).hexdigest()
            insert(c, "flows", [{"flow_id": f"FL-LIVE-{key[:10].upper()}", "ts": iso(when), "ts_epoch": epoch(when),
                                 "from_iban": frm, "to_iban": to_node, "amount": amount, "currency": "RON",
                                 "channel": "transfer", "reference": "Transfer", "reported_fraud": 0, "report_source": None,
                                 "case_id": None, "feed": "demo_ingest", "natural_key": key, "synthetic": 1}],
                   ["flow_id", "ts", "ts_epoch", "from_iban", "to_iban", "amount", "currency", "channel", "reference",
                    "reported_fraud", "report_source", "case_id", "feed", "natural_key", "synthetic"], mode="INSERT OR IGNORE")


def _ensure_account(c: sqlite3.Connection, node: str, kind: str | None = None) -> None:
    if c.execute("SELECT 1 FROM accounts WHERE iban=?", (node,)).fetchone():
        return
    bank = ids.iban_bank_code(node) if node.startswith("RO") else None
    k = kind or ("internal" if bank == ids.OWN_BANK else "external")
    insert(c, "accounts", [{"iban": node, "kind": k, "bank_code": bank, "holder_type": "necunoscut",
                            "account_type": "necunoscut", "opened_at": None, "status": None, "holder_ref": None,
                            "holder_name": None, "cui": None, "synthetic": 1}],
           ["iban", "kind", "bank_code", "holder_type", "account_type", "opened_at", "status", "holder_ref",
            "holder_name", "cui", "synthetic"])
