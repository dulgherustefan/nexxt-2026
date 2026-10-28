"""Parametrii motorului: valorile implicite din `params_default.yaml`, suprascrierile în var/rules_params.json.

Parametrii [U] sunt valori neverificate, deci configurabile (regulile proiectului). Fiecare valoare se validează
(tip, interval, opțiuni). Parametrii `locked` (ex. semnătura umană pe deciziile defavorabile, DP-02) nu se
pot schimba: o încercare ridică `ParamsError` cu codul regulii.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from versoml.contracts import Confidence
from . import calendar_ro

DEFAULTS_FILE = Path(__file__).with_name("params_default.yaml")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$")
_TYPES = {"number", "integer", "boolean", "string", "enum", "time", "date_list", "string_list"}

# Indicatorii pe caz pe care orchestratorul îi poate trimite prin `params` (nu sunt parametri).
CASE_FLAGS = {"_classification_ambiguous": "classification_ambiguous"}


class ParamsError(ValueError):
    """Parametri invalizi. `errors` = [{param, code, message}]."""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__("; ".join(f"{e['param']}: {e['message']}" for e in errors))


@dataclass(frozen=True)
class ParamSpec:
    name: str
    value: Any
    type: str
    confidence: Confidence
    rules: tuple[str, ...]
    description: str
    min: float | None = None
    max: float | None = None
    choices: tuple[Any, ...] | None = None
    nullable: bool = False
    locked: bool = False
    locked_code: str | None = None

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "type": self.type, "confidence": self.confidence.value,
                "rules": list(self.rules), "description": self.description, "min": self.min, "max": self.max,
                "choices": list(self.choices) if self.choices else None, "nullable": self.nullable,
                "locked": self.locked}


def _fail(name: str, code: str, message: str) -> dict[str, str]:
    return {"param": name, "code": code, "message": message}


def _coerce(spec: ParamSpec, value: Any) -> tuple[Any, dict[str, str] | None]:
    """Validează și normalizează o valoare. Întoarce (valoare, eroare)."""
    if value is None:
        return (None, None) if spec.nullable else (None, _fail(spec.name, "PARAM_NULL", "valoarea nu poate lipsi"))
    t = spec.type
    if t in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, _fail(spec.name, "PARAM_TYPE", "trebuie să fie un număr")
        if t == "integer":
            if float(value) != int(value):
                return None, _fail(spec.name, "PARAM_TYPE", "trebuie să fie un număr întreg")
            value = int(value)
        else:
            value = float(value)
        if spec.min is not None and value < spec.min:
            return None, _fail(spec.name, "PARAM_RANGE", f"minimul este {spec.min}")
        if spec.max is not None and value > spec.max:
            return None, _fail(spec.name, "PARAM_RANGE", f"maximul este {spec.max}")
        return value, None
    if t == "boolean":
        if not isinstance(value, bool):
            return None, _fail(spec.name, "PARAM_TYPE", "trebuie să fie true sau false")
        return value, None
    if t in ("string", "enum"):
        if not isinstance(value, str):
            return None, _fail(spec.name, "PARAM_TYPE", "trebuie să fie text")
        if t == "enum" and spec.choices and value not in spec.choices:
            return None, _fail(spec.name, "PARAM_CHOICE", f"valori permise: {', '.join(map(str, spec.choices))}")
        return value, None
    if t == "time":
        if not isinstance(value, str) or not _TIME.match(value):
            return None, _fail(spec.name, "PARAM_TYPE", "format HH:MM:SS")
        return value, None
    if t == "date_list":
        if not isinstance(value, (list, tuple)):
            return None, _fail(spec.name, "PARAM_TYPE", "trebuie să fie o listă de date ISO")
        out = []
        for item in value:
            try:
                out.append((item if isinstance(item, date) else date.fromisoformat(str(item))).isoformat())
            except ValueError:
                return None, _fail(spec.name, "PARAM_TYPE", f"dată invalidă: {item}")
        return sorted(set(out)), None
    if t == "string_list":
        if not isinstance(value, (list, tuple)) or not all(isinstance(i, str) and i.strip() for i in value):
            return None, _fail(spec.name, "PARAM_TYPE", "trebuie să fie o listă de texte")
        return [i.strip() for i in value], None
    return None, _fail(spec.name, "PARAM_TYPE", f"tip necunoscut {t}")


@lru_cache(maxsize=1)
def param_specs() -> dict[str, ParamSpec]:
    raw = yaml.safe_load(DEFAULTS_FILE.read_text(encoding="utf-8")) or {}
    specs: dict[str, ParamSpec] = {}
    for name, row in raw.items():
        if row.get("type") not in _TYPES:
            raise ValueError(f"{name}: tip necunoscut {row.get('type')}")
        spec = ParamSpec(
            name=name, value=row.get("value"), type=row["type"], confidence=Confidence(row.get("confidence", "U")),
            rules=tuple(row.get("rules") or ()), description=" ".join(str(row.get("description", "")).split()),
            min=row.get("min"), max=row.get("max"), choices=tuple(row["choices"]) if row.get("choices") else None,
            nullable=bool(row.get("nullable", False)), locked=bool(row.get("locked", False)),
            locked_code=row.get("locked_code"),
        )
        value, err = _coerce(spec, spec.value)
        if err:
            raise ValueError(f"Valoare implicită invalidă: {err}")
        specs[name] = ParamSpec(**{**spec.__dict__, "value": value})
    return specs


def defaults() -> dict[str, Any]:
    return {name: _copy(spec.value) for name, spec in param_specs().items()}


def _copy(value: Any) -> Any:
    return list(value) if isinstance(value, list) else value


def validate(updates: Mapping[str, Any]) -> dict[str, Any]:
    """Validează un dicționar parțial de parametri; ridică `ParamsError` la prima listă de erori."""
    specs = param_specs()
    clean: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for name, value in updates.items():
        spec = specs.get(name)
        if spec is None:
            errors.append(_fail(name, "PARAM_UNKNOWN", "parametru necunoscut"))
            continue
        coerced, err = _coerce(spec, value)
        if err:
            errors.append(err)
            continue
        if spec.locked and coerced != spec.value:
            errors.append(_fail(name, spec.locked_code or "PARAM_LOCKED",
                                "parametrul e blocat: o decizie defavorabilă nu poate fi luată exclusiv automat "
                                "(GDPR art. 22)" if spec.locked_code == "DP_HUMAN_REVIEW_REQUIRED"
                                else "parametrul e blocat"))
            continue
        clean[name] = coerced
    if errors:
        raise ParamsError(errors)
    return clean


def params_path() -> Path:
    from versoml.config import get_settings

    return get_settings().var_dir / "rules_params.json"


def _read_overrides() -> dict[str, Any]:
    path = params_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    good: dict[str, Any] = {}
    specs = param_specs()
    for name, value in raw.items():
        spec = specs.get(name)
        if spec is None or spec.locked:
            continue
        coerced, err = _coerce(spec, value)
        if err is None:
            good[name] = coerced
    return good


def _write_overrides(overrides: Mapping[str, Any]) -> None:
    path = params_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dict(sorted(overrides.items())), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _sync_calendar(params: Mapping[str, Any]) -> None:
    calendar_ro.set_bank_closure_days(params.get("bank_closure_days") or [])


def get_params() -> dict[str, Any]:
    """Parametrii efectivi: valorile implicite peste care se pun suprascrierile salvate."""
    params = {**defaults(), **_read_overrides()}
    _sync_calendar(params)
    return params


def set_params(updates: Mapping[str, Any]) -> dict[str, Any]:
    """Validează și salvează suprascrierile în var/rules_params.json; întoarce parametrii efectivi."""
    if not isinstance(updates, Mapping):
        raise ParamsError([_fail("*", "PARAM_TYPE", "corpul trebuie să fie un obiect {nume: valoare}")])
    clean = validate(updates)
    overrides = {**_read_overrides(), **clean}
    base = defaults()
    overrides = {k: v for k, v in overrides.items() if v != base.get(k)}
    _write_overrides(overrides)
    return get_params()


def reset_params() -> dict[str, Any]:
    """Șterge suprascrierile; întoarce valorile implicite."""
    path = params_path()
    if path.exists():
        path.unlink()
    return get_params()


def resolve(params: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parametrii pentru o evaluare și indicatorii pe caz.

    - `None` → parametrii efectivi (`get_params()`).
    - un dicționar → valorile implicite peste care se pun cele date (validate); fără citirea fișierului,
      ca evaluarea să depindă doar de intrări. Cheile din `CASE_FLAGS` (ex. `_classification_ambiguous`)
      sunt indicatori pe caz, nu parametri; alte chei care încep cu `_` se ignoră.
    """
    flags: dict[str, Any] = {}
    if params is None:
        return get_params(), flags
    plain: dict[str, Any] = {}
    for key, value in params.items():
        if key in CASE_FLAGS:
            flags[CASE_FLAGS[key]] = bool(value)
        elif not key.startswith("_"):
            plain[key] = value
    return {**defaults(), **validate(plain)}, flags
