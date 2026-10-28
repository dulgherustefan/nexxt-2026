"""Dioda de date dintre zone (zidul, stratul 2; docs/05 §6.3 și docs/06 §5).

- Client → AML: doar `DisputeFacts`, pe `POST {aml_url}/diode/inbox`.
- AML → client: doar `HoldSignal` (ID-uri, booleeni, o dată), pe `POST {client_url}/diode/hold`.
- Corpul e JSON canonic, semnat HMAC-SHA256 în antetul `X-VersoML-Signature`.
- Primirea e strictă: semnătură corectă, chei duplicate interzise, câmpuri în plus respinse
  (modelele `Strict`), ID-uri pe tipare fixe, deci niciun câmp nu poate căra text liber.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import typing
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from versoml.config import Settings, get_settings
from versoml.contracts import DisputeFacts, HoldSignal, Zone
from versoml.secrets import register_secret
from versoml.shared.ledger.canonical import canonical_bytes, iso_utc, now_utc, sha256_hex
from versoml.wall import journal

log = logging.getLogger("versoml.wall.diode")

SIGNATURE_HEADER = "X-VersoML-Signature"
INBOX_PATH = "/diode/inbox"
HOLD_PATH = "/diode/hold"
MAX_BODY_BYTES = 64 * 1024
_SIG_PREFIX = "v1="

CASE_ID_PATTERN = r"^[A-Z]{2,4}-\d{4}-\d{3,8}$"          # ex. CT-2026-000123
APPROVER_PATTERN = r"^[A-Z]{2,16}-\d{1,6}$"              # ex. ANALIST-07
VICTIM_REF_PATTERN = r"^VCT-[A-Za-z0-9]{4,16}$"          # pseudonimul victimei, nu ID-ul de client
FACT_ID_PATTERN = r"^(?:EV|AX)-\d{3,6}$"
# Câmpurile text ale HoldSignal: toate sunt ID-uri cu tipar (testul „fără text liber" le verifică)
HOLD_ID_FIELDS = {"case_id": CASE_ID_PATTERN, "approved_by": APPROVER_PATTERN}
_FACTS_MAX_LEN = {"beneficiary.iban": 34, "beneficiary.name": 140, "beneficiary.cui": 16, "beneficiary.bank_bic": 11,
                  "attack.domain": 253, "attack.url": 2048, "attack.phone": 32}

Kind = Literal["facts", "hold"]


class DiodeError(Exception):
    """Pachet respins de diodă. `code` e stabil (pentru UI), `status` e codul HTTP potrivit."""

    status = 400
    code = "diode_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class DiodeSignatureError(DiodeError):
    status = 401
    code = "bad_signature"


class DiodeSchemaError(DiodeError):
    status = 422
    code = "bad_schema"


class DiodeSizeError(DiodeError):
    status = 413
    code = "too_large"


def free_text_fields(model: type[BaseModel], id_fields: dict[str, str] = HOLD_ID_FIELDS) -> list[str]:
    """Câmpurile de tip text care NU sunt ID-uri cu tipar. Pentru HoldSignal trebuie să fie zero."""
    found = []
    for name, info in model.model_fields.items():
        annotation = info.annotation
        args = typing.get_args(annotation)
        is_text = annotation is str or str in args or annotation is typing.Any
        is_model = isinstance(annotation, type) and issubclass(annotation, BaseModel)
        if is_model or any(isinstance(a, type) and issubclass(a, BaseModel) for a in args):
            found.append(name)  # un sub-obiect poate ascunde text liber
        elif is_text and name not in id_fields:
            found.append(name)
        elif typing.get_origin(annotation) in (list, dict, tuple, set):
            found.append(name)
    return found


# ------------------------------------------------------------ transporturi

class Transport(Protocol):
    def post(self, url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]: ...


class HttpTransport:
    """POST prin httpx. `transport` permite un `httpx.MockTransport` în teste."""

    def __init__(self, timeout: float = 5.0, transport: httpx.BaseTransport | None = None):
        self.timeout = timeout
        self.transport = transport

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            response = client.post(url, content=body, headers=headers)
        return response.status_code, response.text[:300]


class InProcessTransport:
    """Livrează direct în dioda-pereche, fără rețea (teste, demo offline)."""

    def __init__(self, receiver: Diode | None = None,
                 on_facts: Callable[[DisputeFacts], None] | None = None,
                 on_hold: Callable[[HoldSignal], None] | None = None):
        self.receiver = receiver
        self.on_facts = on_facts
        self.on_hold = on_hold
        self.facts: list[DisputeFacts] = []
        self.holds: list[HoldSignal] = []
        self.rejected: list[dict[str, Any]] = []

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        if self.receiver is None:
            return 503, "nicio diodă receptoare"
        signature = headers.get(SIGNATURE_HEADER)
        try:
            if url.endswith(INBOX_PATH):
                facts = self.receiver.receive_facts(body, signature)
                self.facts.append(facts)
                if self.on_facts:
                    self.on_facts(facts)
            elif url.endswith(HOLD_PATH):
                hold = self.receiver.receive_hold(body, signature)
                self.holds.append(hold)
                if self.on_hold:
                    self.on_hold(hold)
            else:
                return 404, "rută necunoscută"
        except DiodeError as exc:
            self.rejected.append({"url": url, "code": exc.code, "status": exc.status})
            return exc.status, str(exc)
        return 202, "acceptat"


# ------------------------------------------------------------ dioda

def _load_secret(settings: Settings, keys_dir: Path | None) -> bytes:
    configured = settings.versoml_diode_secret.get_secret_value() if settings.versoml_diode_secret else ""
    if configured:
        return configured.encode("utf-8")
    path = (Path(keys_dir) if keys_dir else settings.keys_dir) / "diode.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        value = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(value)
    value = path.read_bytes().strip()
    if len(value) < 16:
        raise DiodeError("secretul diodei e prea scurt")
    return value


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise DiodeSchemaError("Pachet respins: chei JSON duplicate.", code="duplicate_keys")
    return dict(pairs)


def _schema_error(model: str, exc: ValidationError) -> DiodeSchemaError:
    problems = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err.get("loc", ())) or "(rădăcină)"
        what = "câmp nepermis" if err.get("type") == "extra_forbidden" else "valoare invalidă"
        problems.append(f"{where}: {what}")
    code = "extra_field" if any(e.get("type") == "extra_forbidden" for e in exc.errors()) else "bad_schema"
    return DiodeSchemaError(f"Pachet {model} respins de schema strictă: " + "; ".join(problems[:6]) + ".", code=code)


class Diode:
    """Capătul de diodă al unei zone. Aceeași clasă trimite și primește; secretul e comun."""

    def __init__(
        self,
        secret: bytes | str | None = None,
        *,
        settings: Settings | None = None,
        keys_dir: Path | str | None = None,
        aml_url: str | None = None,
        client_url: str | None = None,
        transport: Transport | None = None,
        known_case: Callable[[str], bool] | None = None,
        case_id_pattern: str = CASE_ID_PATTERN,
        approver_pattern: str = APPROVER_PATTERN,
        outbox_db: Path | str | None = None,
    ):
        self.settings = settings or get_settings()
        if secret is None:
            secret = _load_secret(self.settings, Path(keys_dir) if keys_dir else None)
        self._secret = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
        register_secret(self._secret.decode("utf-8", errors="ignore"))
        self.aml_url = (aml_url or self.settings.aml_url).rstrip("/")
        self.client_url = (client_url or self.settings.client_url).rstrip("/")
        self.transport: Transport = transport or HttpTransport()
        self.known_case = known_case
        self._case_re = re.compile(case_id_pattern)
        self._approver_re = re.compile(approver_pattern)
        self._outbox = Path(outbox_db) if outbox_db else None
        if self._outbox:
            self._outbox.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(str(self._outbox), timeout=30)) as conn, conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS diode_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
                    "case_id TEXT NOT NULL, url TEXT NOT NULL, body BLOB NOT NULL, signature TEXT NOT NULL, "
                    "sha256 TEXT NOT NULL, created_at TEXT NOT NULL, status INTEGER, delivered_at TEXT, "
                    "attempts INTEGER NOT NULL DEFAULT 0)"
                )

    # ------------------------------------------------------------ semnătura

    def sign(self, kind: Kind, body: bytes) -> str:
        mac = hmac.new(self._secret, b"versoml-diode:v1:" + kind.encode("ascii") + b"\n" + body, hashlib.sha256)
        return _SIG_PREFIX + mac.hexdigest()

    def verify(self, kind: Kind, body: bytes, signature: str | None) -> bool:
        if not signature or not signature.startswith(_SIG_PREFIX):
            return False
        return hmac.compare_digest(self.sign(kind, body), signature.strip())

    # ------------------------------------------------------------ verificări de formă

    def _check_facts(self, facts: DisputeFacts) -> None:
        problems = []
        if not self._case_re.match(facts.case_id):
            problems.append("case_id nu are forma unui ID de caz")
        if not re.match(VICTIM_REF_PATTERN, facts.victim_ref):
            problems.append("victim_ref trebuie să fie un pseudonim VCT-…, nu identitatea clientului")
        bad_ids = [f for f in facts.fact_ids if not re.match(FACT_ID_PATTERN, f)]
        if bad_ids or len(facts.fact_ids) > 500:
            problems.append("fact_ids conține valori care nu sunt ID-uri de probă")
        data = facts.model_dump(mode="json")
        for path, limit in _FACTS_MAX_LEN.items():
            group, field = path.split(".")
            value = (data.get(group) or {}).get(field)
            if isinstance(value, str) and len(value) > limit:
                problems.append(f"{path} depășește {limit} caractere")
        if problems:
            raise DiodeSchemaError("DisputeFacts respins: " + "; ".join(problems) + ".", code="bad_ids")

    def _check_hold(self, signal: HoldSignal) -> None:
        problems = []
        if not self._case_re.match(signal.case_id):
            problems.append("case_id nu are forma unui ID de caz")
        if not self._approver_re.match(signal.approved_by):
            problems.append("approved_by nu are forma unui ID de analist (ex. ANALIST-07)")
        if signal.approved_at.tzinfo is None:
            problems.append("approved_at trebuie să aibă fus orar")
        if problems:
            raise DiodeSchemaError("HoldSignal respins: " + "; ".join(problems) + ".", code="bad_ids")
        if self.known_case is not None and not self.known_case(signal.case_id):
            raise DiodeSchemaError("HoldSignal respins: cazul nu există în zona client.", code="unknown_case")

    def _parse(self, kind: Kind, model: type[BaseModel], raw_body: bytes, signature: str | None) -> Any:
        label = "DisputeFacts" if kind == "facts" else "HoldSignal"
        try:
            if not isinstance(raw_body, (bytes, bytearray)):
                raw_body = str(raw_body).encode("utf-8")
            if len(raw_body) > MAX_BODY_BYTES:
                raise DiodeSizeError(f"{label} respins: pachet prea mare ({len(raw_body)} octeți).")
            if not self.verify(kind, bytes(raw_body), signature):
                raise DiodeSignatureError(f"{label} respins: semnătura HMAC lipsește sau nu e validă.")
            try:
                json.loads(raw_body, object_pairs_hook=_no_duplicate_keys)
            except ValueError:
                raise DiodeSchemaError(f"{label} respins: corpul nu e JSON valid.", code="bad_json") from None
            try:
                return model.model_validate_json(raw_body, strict=True)
            except ValidationError as exc:
                raise _schema_error(label, exc) from None
        except DiodeError as exc:
            journal.record(2, "diode_reject", reasons=[str(exc)], detail={"kind": kind, "code": exc.code})
            raise

    # ------------------------------------------------------------ client → AML

    def encode_facts(self, facts: DisputeFacts | dict[str, Any]) -> tuple[bytes, str]:
        """(corp canonic, semnătură) pentru un DisputeFacts verificat."""
        try:
            facts = DisputeFacts.model_validate(facts.model_dump(mode="json") if isinstance(facts, BaseModel) else facts)
        except ValidationError as exc:
            raise _schema_error("DisputeFacts", exc) from None
        self._check_facts(facts)
        body = canonical_bytes(facts.model_dump(mode="json"))
        return body, self.sign("facts", body)

    def send_facts(self, facts: DisputeFacts, *, principal: str | None = None) -> dict[str, Any]:
        """Trimite faptele spre zona AML. Nu ridică la erori de rețea: rambursarea nu așteaptă AML-ul."""
        if principal:
            from versoml.shared.policy import enforce

            enforce(principal, "diode.send_facts", Zone.CLIENT)
        body, signature = self.encode_facts(facts)
        return self._deliver("facts", f"{self.aml_url}{INBOX_PATH}", body, signature, json.loads(body)["case_id"])

    def receive_facts(self, raw_body: bytes, signature: str | None) -> DisputeFacts:
        """Partea AML: verifică semnătura și schema strictă. Ridică `DiodeError`."""
        facts = self._parse("facts", DisputeFacts, raw_body, signature)
        try:
            self._check_facts(facts)
        except DiodeError as exc:
            journal.record(2, "diode_reject", case_id=None, reasons=[str(exc)], detail={"kind": "facts", "code": exc.code})
            raise
        return facts

    # ------------------------------------------------------------ AML → client

    def encode_hold(self, signal: HoldSignal | dict[str, Any]) -> tuple[bytes, str]:
        try:
            signal = HoldSignal.model_validate(signal.model_dump(mode="json") if isinstance(signal, BaseModel) else signal)
        except ValidationError as exc:
            raise _schema_error("HoldSignal", exc) from None
        self._check_hold(signal)
        body = canonical_bytes(signal.model_dump(mode="json"))
        return body, self.sign("hold", body)

    def send_hold(self, signal: HoldSignal, *, principal: str | None = None) -> dict[str, Any]:
        """Trimite semnalul HOLD spre zona client (după acțiunea analistului)."""
        if principal:
            from versoml.shared.policy import enforce

            enforce(principal, "diode.send_hold", Zone.AML)
        body, signature = self.encode_hold(signal)
        return self._deliver("hold", f"{self.client_url}{HOLD_PATH}", body, signature, signal.case_id)

    def receive_hold(self, raw_body: bytes, signature: str | None) -> HoldSignal:
        """Partea client: semnătură, schemă strictă, ID-uri pe tipar. Ridică `DiodeError`."""
        signal = self._parse("hold", HoldSignal, raw_body, signature)
        try:
            self._check_hold(signal)
        except DiodeError as exc:
            journal.record(2, "diode_reject", reasons=[str(exc)], detail={"kind": "hold", "code": exc.code})
            raise
        return signal

    # ------------------------------------------------------------ livrarea

    def _deliver(self, kind: Kind, url: str, body: bytes, signature: str, case_id: str) -> dict[str, Any]:
        digest = sha256_hex(body)
        row_id = None
        if self._outbox:
            with closing(sqlite3.connect(str(self._outbox), timeout=30)) as conn, conn:
                row_id = conn.execute(
                    "INSERT INTO diode_outbox (kind, case_id, url, body, signature, sha256, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (kind, case_id, url, body, signature, digest, iso_utc(now_utc())),
                ).lastrowid
        headers = {"Content-Type": "application/json", SIGNATURE_HEADER: signature}
        try:
            status, detail = self.transport.post(url, body, headers)
        except Exception as exc:  # noqa: BLE001 - rețeaua căzută nu oprește zona client
            status, detail = 0, f"livrare eșuată ({type(exc).__name__})"
            log.warning("Dioda: livrarea %s spre %s a eșuat: %s", kind, url, type(exc).__name__)
        ok = 200 <= status < 300
        if row_id is not None:
            with closing(sqlite3.connect(str(self._outbox), timeout=30)) as conn, conn:
                conn.execute(
                    "UPDATE diode_outbox SET status = ?, attempts = attempts + 1, delivered_at = ? WHERE id = ?",
                    (status, iso_utc(now_utc()) if ok else None, row_id),
                )
        return {"ok": ok, "status": status, "detail": detail, "sha256": digest, "url": url, "kind": kind,
                "case_id": case_id, "sent_at": iso_utc(now_utc())}

    def pending(self) -> list[dict[str, Any]]:
        """Pachetele din outbox nelivrate încă."""
        if not self._outbox:
            return []
        with closing(sqlite3.connect(str(self._outbox), timeout=30)) as conn:
            rows = conn.execute(
                "SELECT id, kind, case_id, url, sha256, attempts FROM diode_outbox WHERE delivered_at IS NULL ORDER BY id"
            ).fetchall()
        return [dict(zip(("id", "kind", "case_id", "url", "sha256", "attempts"), r)) for r in rows]

    def flush(self) -> list[dict[str, Any]]:
        """Reîncearcă pachetele nelivrate din outbox (aceleași octeți, aceeași semnătură)."""
        if not self._outbox:
            return []
        with closing(sqlite3.connect(str(self._outbox), timeout=30)) as conn:
            rows = conn.execute(
                "SELECT id, kind, url, body, signature FROM diode_outbox WHERE delivered_at IS NULL ORDER BY id"
            ).fetchall()
        results = []
        for row_id, kind, url, body, signature in rows:
            try:
                status, detail = self.transport.post(url, bytes(body), {"Content-Type": "application/json",
                                                                         SIGNATURE_HEADER: signature})
            except Exception as exc:  # noqa: BLE001
                status, detail = 0, f"livrare eșuată ({type(exc).__name__})"
            ok = 200 <= status < 300
            with closing(sqlite3.connect(str(self._outbox), timeout=30)) as conn, conn:
                conn.execute(
                    "UPDATE diode_outbox SET status = ?, attempts = attempts + 1, delivered_at = ? WHERE id = ?",
                    (status, iso_utc(now_utc()) if ok else None, row_id),
                )
            results.append({"id": row_id, "kind": kind, "ok": ok, "status": status, "detail": detail})
        return results
