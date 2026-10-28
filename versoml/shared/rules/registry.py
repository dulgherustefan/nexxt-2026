"""Registrul regulilor: fiecare regulă e o funcție pură, înregistrată cu metadatele ei.

O regulă primește faptele (`RuleContextExt` sau `AmlRuleContext`) și mediul (`Env`: parametri, calendar)
și întoarce un `Finding` sau `None` (nu se aplică). Regulile nu se cheamă între ele și nu fac I/O.
Deciziile le compune motorul (`engine.py`), în ordinea fixă a arborilor din docs/context/11 §4.2 și 14 §4.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from versoml.contracts import Confidence, Deadline, Question, Zone

RULES_VERSION = "2026.10.28"

PACK_ORDER = ("PAY", "DSP", "CMP", "REC", "URM", "DP", "AML")
PACK_TITLES = {
    "PAY": "Plăți: Legea 209/2019 (PSD2) și CJUE C-70/25 (docs/context/11 §2.5)",
    "DSP": "Dispute card și scheme Visa/Mastercard (docs/context/14)",
    "CMP": "Reclamații: termene și conținutul răspunsului (docs/context/11 §2.6)",
    "REC": "Rechemarea transferurilor (docs/05 §3–4, ghiduri EPC); EXTENSIE, absentă din docs/context",
    "URM": "Reguli de produs VersoML (docs/05 §3–5); EXTENSIE, absentă din catalogul docs/context",
    "DP": "Protecția datelor și decizii automate (docs/context/11 §2.7)",
    "AML": "AML: Legea 129/2019 art. 6–8 (docs/context/11 §2.2); doar în zona AML",
}
EXTENSION_PACKS = frozenset({"REC", "URM"})

RuleKind = Literal["regula", "calculator", "garda"]

_CEDILLA = str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"})


def normalize_ro(text: str) -> str:
    """ş/ţ cu sedilă → ș/ț cu virgulă dedesubt."""
    return text.translate(_CEDILLA)


@dataclass(frozen=True)
class Finding:
    """Ce a constatat o regulă: codul rezultatului, explicația în română și câmpurile folosite."""

    rule_id: str
    outcome: str
    explanation: str
    fields: tuple[str, ...] = ()                       # câmpurile din context folosite (→ fact_ids)
    data: Mapping[str, Any] = field(default_factory=dict)   # valori calculate (termene, sume, coduri)
    deadlines: tuple[Deadline, ...] = ()


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    title: str
    basis: str
    confidence: Confidence
    pack: str
    source: str
    version: str = RULES_VERSION
    questions: tuple[Question, ...] = ()
    params: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    zone: Zone = Zone.CLIENT
    kind: RuleKind = "regula"
    tests: tuple[str, ...] = ()
    effective_from: date | None = None
    effective_to: date | None = None
    description: str = ""
    fn: Callable[..., Any] | None = None

    @property
    def extension(self) -> bool:
        """True pentru regulile care nu vin din catalogul docs/context (pachetele REC și URM)."""
        return self.pack in EXTENSION_PACKS

    def is_effective(self, on: date) -> bool:
        if self.effective_from and on < self.effective_from:
            return False
        return not (self.effective_to and on > self.effective_to)

    def to_catalog(self, param_values: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "basis": self.basis,
            "confidence": self.confidence.value,
            "pack": self.pack,
            "params": {name: param_values.get(name) for name in self.params},
            "version": self.version,
            "kind": self.kind,
            "zone": self.zone.value,
            "questions": [q.value for q in self.questions],
            "exceptions": list(self.exceptions),
            "aliases": list(self.aliases),
            "source": self.source,
            "extension": self.extension,
            "tests": list(self.tests),
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
        }


_REGISTRY: dict[str, RuleSpec] = {}
_ALIASES: dict[str, str] = {}
_ID = re.compile(r"^[A-Z]{2,4}-\d{2}$")


def register(spec: RuleSpec) -> RuleSpec:
    if not _ID.match(spec.rule_id):
        raise ValueError(f"ID de regulă invalid: {spec.rule_id}")
    if spec.pack not in PACK_ORDER:
        raise ValueError(f"Pachet necunoscut: {spec.pack}")
    if spec.rule_id in _REGISTRY or spec.rule_id in _ALIASES:
        raise ValueError(f"Regula {spec.rule_id} e deja înregistrată")
    for alias in spec.aliases:
        if alias in _REGISTRY or alias in _ALIASES:
            raise ValueError(f"Aliasul {alias} e deja folosit")
        _ALIASES[alias] = spec.rule_id
    _REGISTRY[spec.rule_id] = spec
    return spec


def rule(
    rule_id: str,
    *,
    title: str,
    basis: str,
    confidence: Confidence,
    pack: str,
    source: str,
    questions: tuple[Question, ...] = (),
    params: tuple[str, ...] = (),
    exceptions: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    zone: Zone = Zone.CLIENT,
    kind: RuleKind = "regula",
    tests: tuple[str, ...] = (),
    effective_from: date | None = None,
    effective_to: date | None = None,
    version: str = RULES_VERSION,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decoratorul care înregistrează o regulă (sau un calculator) cu metadatele ei."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        spec = RuleSpec(
            rule_id=rule_id, title=normalize_ro(title), basis=normalize_ro(basis), confidence=confidence,
            pack=pack, source=source, version=version, questions=tuple(questions), params=tuple(params),
            exceptions=tuple(exceptions), aliases=tuple(aliases), zone=zone, kind=kind, tests=tuple(tests),
            effective_from=effective_from, effective_to=effective_to,
            description=normalize_ro(inspect.getdoc(fn) or ""), fn=fn,
        )
        register(spec)
        fn.rule_spec = spec  # type: ignore[attr-defined]
        return fn

    return deco


def resolve_id(rule_id: str) -> str:
    """ID-ul canonic (ex. DSP-04 → PAY-15, pentru regulile DSP care aplică articolele din PAY/CMP)."""
    return _ALIASES.get(rule_id, rule_id)


def get_rule(rule_id: str) -> RuleSpec:
    canonical = resolve_id(rule_id)
    if canonical not in _REGISTRY:
        raise KeyError(f"Regulă necunoscută: {rule_id}")
    return _REGISTRY[canonical]


def known_ids() -> set[str]:
    return set(_REGISTRY) | set(_ALIASES)


def aliases() -> dict[str, str]:
    return dict(_ALIASES)


def _sort_key(spec: RuleSpec) -> tuple[int, int]:
    return PACK_ORDER.index(spec.pack), int(spec.rule_id.split("-")[1])


def all_rules(pack: str | None = None, zone: Zone | None = None, kind: RuleKind | None = None) -> list[RuleSpec]:
    rows = [s for s in _REGISTRY.values()
            if (pack is None or s.pack == pack) and (zone is None or s.zone == zone) and (kind is None or s.kind == kind)]
    return sorted(rows, key=_sort_key)


def engine_rules(zone: Zone) -> list[RuleSpec]:
    """Regulile rulate de motor, în ordinea registrului (nu în ordinea sortată pe ID)."""
    return [s for s in _REGISTRY.values() if s.zone == zone and s.kind == "regula" and s.fn is not None]
