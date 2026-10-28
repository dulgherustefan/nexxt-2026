"""PrivacyProxy: pseudonimizare reversibilă, pe caz, înaintea oricărui apel spre LLM (docs/05 §6.4).

- Pseudonime stabile pe caz: <CLIENT_1>, <IBAN_1>, <CARD_1>, <TELEFON_1>, <EMAIL_1>, <CNP_1>, <CI_1>, <PERSOANA_1>.
- Seiful (pseudonim → valoare) stă doar în zona client; opțional persistat în baza zonei.
- `assert_llm_safe` ridică `RawPIIError` dacă în payload a rămas vreo dată personală brută.
- Identificatorii publici (CUI, firma beneficiară, domenii) rămân în text; sunt doar etichetați.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from versoml.shared.privacy.recognizers import Finding, detect, parse_role
from versoml.shared.privacy.text import fold, normalize_ro

_TOKEN_KIND = {"CNP": "CNP", "IBAN": "IBAN", "CARD": "CARD", "TELEFON": "TELEFON", "EMAIL": "EMAIL", "CI": "CI"}
_TOKEN_RE = re.compile(r"(?:<|&lt;|\[)\s*([A-Za-z]+(?:_[A-Za-z]+)*)_(\d+)\s*(?:>|&gt;|\])")
_INT_SCAN_MIN = 10**8  # numerele întregi lungi (CNP, card scris ca număr) se verifică și ele

_SCHEMA = """
CREATE TABLE IF NOT EXISTS privacy_vault (
    case_id TEXT NOT NULL,
    token TEXT NOT NULL,
    kind TEXT NOT NULL,
    value_key TEXT NOT NULL,
    original TEXT NOT NULL,
    PRIMARY KEY (case_id, token)
);
"""


class RawPIIError(ValueError):
    """Payload-ul spre LLM conține date personale brute. Mesajul nu include valorile."""

    def __init__(self, findings: list[dict[str, Any]]):
        self.findings = findings
        counts = Counter(f["type"] for f in findings)
        summary = ", ".join(f"{k} ×{v}" for k, v in sorted(counts.items()))
        super().__init__(f"Raw personal data in the request to the LLM: {summary}. Pseudonymize it before the call.")


@dataclass
class _CaseVault:
    forward: dict[tuple[str, str], str] = field(default_factory=dict)   # (grup, cheie) → pseudonim
    reverse: dict[str, str] = field(default_factory=dict)              # pseudonim → valoarea originală
    counters: Counter = field(default_factory=Counter)
    known: dict[str, str] = field(default_factory=dict)                # numele cunoscute ale cazului
    loaded: bool = False


def _walk(obj: Any, path: str = "$"):
    """Toate șirurile (chei și valori) dintr-un payload, cu calea lor."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, int):
        if abs(obj) >= _INT_SCAN_MIN:
            yield path, str(obj)
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            if isinstance(key, str):
                yield f"{path}.<key>", key
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for i, value in enumerate(obj):
            yield from _walk(value, f"{path}[{i}]")
    elif hasattr(obj, "model_dump"):
        yield from _walk(obj.model_dump(mode="json"), path)


class PrivacyProxy:
    """Detectare, pseudonimizare pe caz, restaurare și verificarea „zero PII spre model"."""

    def __init__(self, db_path: Path | str | None = None):
        self._lock = threading.RLock()
        self._vaults: dict[str, _CaseVault] = {}
        self._known_all: dict[str, str] = {}
        self._stats: Counter = Counter()
        self._redactions: Counter = Counter()
        self._tags: Counter = Counter()
        self._db_path = Path(db_path) if db_path else None
        if self._db_path:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(str(self._db_path), timeout=30)) as conn, conn:
                conn.executescript(_SCHEMA)

    # ------------------------------------------------------------ seiful

    def _vault(self, case_id: str) -> _CaseVault:
        vault = self._vaults.setdefault(case_id, _CaseVault())
        if self._db_path and not vault.loaded:
            with closing(sqlite3.connect(str(self._db_path), timeout=30)) as conn:
                rows = conn.execute(
                    "SELECT token, kind, value_key, original FROM privacy_vault WHERE case_id = ?", (case_id,)
                ).fetchall()
            for token, kind, key, original in rows:
                group = "NUME" if kind not in _TOKEN_KIND.values() else kind
                vault.forward[(group, key)] = token
                vault.reverse[token] = original
                number = int(token.strip("<>").rsplit("_", 1)[1])
                vault.counters[kind] = max(vault.counters[kind], number)
                if group == "NUME":
                    vault.known.setdefault(original, kind)
                    self._known_all.setdefault(original, kind)
        vault.loaded = True
        return vault

    def _token_for(self, case_id: str, vault: _CaseVault, finding: Finding, explicit: str | None) -> str:
        group = "NUME" if finding.type == "NUME" else finding.type
        existing = vault.forward.get((group, finding.key))
        if existing:
            return existing
        if explicit and explicit not in vault.reverse:
            token = explicit
            kind = explicit.strip("<>").rsplit("_", 1)[0]
            vault.counters[kind] = max(vault.counters[kind], int(explicit.strip("<>").rsplit("_", 1)[1]))
        else:
            kind = finding.role if finding.type == "NUME" and finding.role else _TOKEN_KIND.get(finding.type, "PERSOANA")
            kind = "PERSOANA" if finding.type == "NUME" and not finding.role else kind
            vault.counters[kind] += 1
            token = f"<{kind}_{vault.counters[kind]}>"
            while token in vault.reverse:
                vault.counters[kind] += 1
                token = f"<{kind}_{vault.counters[kind]}>"
        vault.forward[(group, finding.key)] = token
        vault.reverse[token] = finding.value
        if self._db_path:
            with closing(sqlite3.connect(str(self._db_path), timeout=30)) as conn, conn:
                conn.execute(
                    "INSERT OR IGNORE INTO privacy_vault (case_id, token, kind, value_key, original) VALUES (?, ?, ?, ?, ?)",
                    (case_id, token, kind, finding.key, finding.value),
                )
        return token

    def vault(self, case_id: str) -> dict[str, str]:
        """Copia seifului cazului: pseudonim → valoare. Nu se trimite niciodată spre LLM."""
        with self._lock:
            return dict(self._vault(case_id).reverse)

    def forget(self, case_id: str) -> None:
        """Șterge seiful din memorie (de ex. la închiderea cazului)."""
        with self._lock:
            self._vaults.pop(case_id, None)

    # ------------------------------------------------------------ API public

    def scan(self, text: str, known: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        """Potrivirile din text: {type, start, end, value, masked, pii, role, …}. Nu logați `value`."""
        text = normalize_ro(text or "")
        with self._lock:
            self._stats["scan"] += 1
            self._stats["calls"] += 1
        return [f.as_dict() for f in detect(text, known)]

    def pseudonymize(self, text: str, case_id: str, known: dict[str, str] | None = None) -> tuple[str, dict]:
        """Înlocuiește datele personale cu pseudonime stabile pe caz. Întoarce (text, seif)."""
        text = normalize_ro(text or "")
        with self._lock:
            vault = self._vault(case_id)
            explicit: dict[str, str] = {}
            for name, role_value in (known or {}).items():
                role, token = parse_role(role_value)
                vault.known[name] = role
                self._known_all[name] = role
                if token:
                    explicit[" ".join(sorted(t for t in re.split(r"[\s\-]+", fold(normalize_ro(name))) if t))] = token
            findings = detect(text, vault.known)
            replacements: list[tuple[Finding, str]] = []
            for f in findings:  # numerotarea urmează ordinea din text: primul IBAN e <IBAN_1>
                if not f.pii:
                    self._tags[f.type] += 1
                    continue
                token = self._token_for(case_id, vault, f, explicit.get(f.key) if f.type == "NUME" else None)
                replacements.append((f, token))
                self._redactions[f.type] += 1
            out = text
            for f, token in reversed(replacements):
                out = out[:f.start] + token + out[f.end:]
            self._stats["pseudonymize"] += 1
            self._stats["calls"] += 1
            return out, dict(vault.reverse)

    def restore(self, text: str, vault: dict) -> str:
        """Pune la loc valorile originale (tolerant la <X_1>, &lt;X_1&gt;, [X_1], spații, majuscule)."""
        if not text or not vault:
            return text
        table = {str(k).strip().strip("<>").strip().upper(): str(v) for k, v in vault.items()}

        def swap(m: re.Match) -> str:
            return table.get(f"{m.group(1).upper()}_{m.group(2)}", m.group(0))

        out = _TOKEN_RE.sub(swap, text)
        for key in sorted(table, key=len, reverse=True):
            out = re.sub(rf"(?<![\w<]){re.escape(key)}(?![\w>])", lambda _m, v=table[key]: v, out)
        with self._lock:
            self._stats["restore"] += 1
            self._stats["calls"] += 1
        return out

    def pseudonymize_obj(self, obj: Any, case_id: str, known: dict[str, str] | None = None) -> tuple[Any, dict]:
        """Ca `pseudonymize`, pe toate șirurile dintr-un dict/listă (argumente și rezultate de tool-uri)."""
        vault: dict = {}

        def walk(value: Any) -> Any:
            nonlocal vault
            if isinstance(value, str):
                new, vault = self.pseudonymize(value, case_id, known)
                return new
            if isinstance(value, Mapping):
                return {k: walk(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [walk(v) for v in value]
            return value

        result = walk(obj)
        return result, vault or self.vault(case_id)

    def restore_obj(self, obj: Any, vault: dict) -> Any:
        if isinstance(obj, str):
            return self.restore(obj, vault)
        if isinstance(obj, Mapping):
            return {k: self.restore_obj(v, vault) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.restore_obj(v, vault) for v in obj]
        return obj

    def find_raw_pii(self, payload: str | dict | list) -> list[dict[str, Any]]:
        """Datele personale brute rămase în payload: [{type, masked, path}] (fără valori)."""
        found = []
        with self._lock:
            known = dict(self._known_all)
        for path, text in _walk(payload):
            for f in detect(normalize_ro(text), known, public=False):
                if f.pii:
                    found.append({"type": f.type, "masked": f.masked, "path": path})
        return found

    def assert_llm_safe(self, payload: str | dict | list) -> None:
        """Ridică `RawPIIError` dacă payload-ul conține date personale brute (CNP, IBAN, card, …)."""
        found = self.find_raw_pii(payload)
        with self._lock:
            self._stats["assert_checks"] += 1
            self._stats["calls"] += 1
            if found:
                self._stats["assert_blocked"] += 1
        if found:
            raise RawPIIError(found)

    def stats(self) -> dict[str, Any]:
        """Contoarele pentru UI: apeluri, înlocuiri pe tip, etichete publice, verificări."""
        with self._lock:
            return {
                "calls": self._stats["calls"],
                "pseudonymize": self._stats["pseudonymize"],
                "scan": self._stats["scan"],
                "restore": self._stats["restore"],
                "assert_checks": self._stats["assert_checks"],
                "assert_blocked": self._stats["assert_blocked"],
                "redactions": dict(self._redactions),
                "redactions_total": sum(self._redactions.values()),
                "public_tags": dict(self._tags),
                "cases": len(self._vaults),
            }

    def reset_stats(self) -> None:
        with self._lock:
            self._stats.clear()
            self._redactions.clear()
            self._tags.clear()


_default: PrivacyProxy | None = None
_default_lock = threading.Lock()


def get_proxy() -> PrivacyProxy:
    """Instanța comună a procesului (seif în memorie)."""
    global _default
    with _default_lock:
        if _default is None:
            _default = PrivacyProxy()
        return _default


def assert_llm_safe(payload: str | dict | list) -> None:
    """Verificarea dinaintea fiecărui apel spre LLM, pe instanța comună."""
    get_proxy().assert_llm_safe(payload)


def scan(text: str) -> list[dict[str, Any]]:
    return get_proxy().scan(text)
