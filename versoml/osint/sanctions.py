"""Verificarea pe liste de sancțiuni: lista sintetică (fixture) și, opțional, lista UE de sancțiuni financiare
(OpenSanctions `eu_fsf`, CSV simplu descărcat la cerere în var/; licență CC BY-NC 4.0, producția cere licență).

Se verifică doar beneficiari și firme, niciodată victime. Potrivirea e fuzzy (rapidfuzz) și e un semnal
pentru om: un scor mare înseamnă „de verificat", nu „sancționat".
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from versoml.osint.base import (
    FIXTURES_DIR,
    ToolResult,
    configured_mode,
    describe_error,
    failure,
    http_request,
    is_synthetic_target,
    settings,
    tool,
)
from versoml.osint.params import param
from versoml.osint.util import fold, normalize_ro

EU_FSF_URL = "https://data.opensanctions.org/datasets/latest/eu_fsf/targets.simple.csv"
EU_FSF_MAX_AGE_S = 24 * 3600
EU_FSF_MAX_BYTES = 80 * 1024 * 1024
LEGAL_FORMS = frozenset({
    "srl", "sa", "sc", "srld", "snc", "scs", "pfa", "ii", "if", "ltd", "llc", "gmbh", "ag", "inc", "plc", "spa",
    "sarl", "bv", "nv", "oy", "ab", "sro", "kft", "ooo", "zao", "oao", "jsc", "pjsc", "co", "company", "limited",
    "corp", "corporation",
})


LIST_LABELS = {"sintetic": "lista sintetică", "eu_fsf": "lista UE de sancțiuni financiare (OpenSanctions)"}


def normalize_name(name: str) -> str:
    """Nume comparabil: fără diacritice, litere mici, fără punctuație și forme juridice (SRL, SA, LTD...)."""
    text = fold(name).replace(".", "")
    tokens = re.findall(r"[a-z0-9]+", text)
    kept = [t for t in tokens if t not in LEGAL_FORMS]
    return " ".join(kept or tokens)


def match_score(query: str, candidate: str) -> float:
    """0,6 × token_set + 0,4 × token_sort: prinde subseturi, dar nu și potriviri pe un singur cuvânt scurt."""
    return 0.6 * fuzz.token_set_ratio(query, candidate) + 0.4 * fuzz.token_sort_ratio(query, candidate)


# ---------------------------------------------------------------- listele


@lru_cache(maxsize=1)
def synthetic_watchlist() -> list[dict[str, Any]]:
    path = FIXTURES_DIR / "sanctions_screen" / "watchlist.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["entities"]
    except (OSError, ValueError, KeyError):
        return []


def eu_fsf_path() -> Path:
    folder = settings().var_dir / "opensanctions"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "eu_fsf_targets.simple.csv"


def _split_aliases(value: str) -> list[str]:
    return [a.strip() for a in re.split(r"[;|]", value or "") if a.strip()]


@lru_cache(maxsize=4)
def _load_csv(path_str: str, mtime: float) -> list[dict[str, Any]]:
    entities = []
    with open(path_str, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            names = [row.get("name") or "", *_split_aliases(row.get("aliases", ""))]
            entities.append({
                "id": row.get("id"),
                "name": normalize_ro(row.get("name") or ""),
                "aliases": [n for n in names[1:] if n],
                "schema": row.get("schema"),
                "countries": row.get("countries"),
                "program": row.get("program_ids") or row.get("sanctions"),
                "list": "eu_fsf",
            })
    return entities


def eu_fsf_entities() -> list[dict[str, Any]] | None:
    path = eu_fsf_path()
    if not path.is_file():
        return None
    return _load_csv(str(path), path.stat().st_mtime)


async def download_eu_fsf(force: bool = False) -> dict[str, Any]:
    """Descarcă lista UE FSF (OpenSanctions) în var/opensanctions/ dacă lipsește sau e mai veche de 24 h."""
    path = eu_fsf_path()
    if path.is_file() and not force and time.time() - path.stat().st_mtime < EU_FSF_MAX_AGE_S:
        return {"status": "local", "path": str(path)}
    resp = await http_request("GET", EU_FSF_URL, follow_redirects=True, total_timeout=45.0, retries=1,
                              timeout=45.0)
    if resp.status_code != 200 or len(resp.content) > EU_FSF_MAX_BYTES:
        raise RuntimeError(f"descărcarea listei UE a eșuat (HTTP {resp.status_code})")
    text = resp.text
    if not text.startswith("id,") and "schema" not in text[:200]:
        raise RuntimeError("fișierul descărcat nu are antetul așteptat")
    path.write_text(text, encoding="utf-8")
    return {"status": "descarcat", "path": str(path), "bytes": len(resp.content), "url": str(resp.url)}


# ---------------------------------------------------------------- potrivirea


def _candidates(query: str, entities: list[dict[str, Any]], list_id: str, limit: int = 5) -> list[dict[str, Any]]:
    choices: list[str] = []
    owners: list[tuple[dict[str, Any], str]] = []
    for entity in entities:
        for name in [entity["name"], *entity.get("aliases", [])]:
            normalized = normalize_name(name)
            if normalized:
                choices.append(normalized)
                owners.append((entity, name))
    if not choices:
        return []
    rough = process.extract(query, choices, scorer=fuzz.token_set_ratio, limit=max(limit * 6, 30), score_cutoff=70)
    scored: dict[str, dict[str, Any]] = {}
    for _, _, index in rough:
        entity, original = owners[index]
        score = round(match_score(query, choices[index]), 1)
        current = scored.get(entity["id"])
        if current is None or score > current["score"]:
            scored[entity["id"]] = {"list": list_id, "entity_id": entity["id"], "name": entity["name"],
                                    "matched_name": original, "score": score, "schema": entity.get("schema"),
                                    "program": entity.get("program"), "countries": entity.get("countries")}
    return sorted(scored.values(), key=lambda m: -m["score"])[:limit]


@tool("sanctions_screen", zones=("aml",), group="sanctions")
async def sanctions_screen(name: str) -> ToolResult:
    """Verifică fuzzy numele unui beneficiar sau al unei firme pe lista sintetică și pe lista UE FSF (OpenSanctions, dacă e disponibilă). Nu se folosește pentru victime."""
    started = time.perf_counter()
    clean = normalize_ro(name).strip()
    args = {"name": clean}
    query = normalize_name(clean)
    if len(query) < 3:
        return failure("sanctions_screen", args, "Nume prea scurt pentru verificarea pe liste.", error="nume prea scurt")
    lists: list[dict[str, Any]] = []
    matches = _candidates(query, synthetic_watchlist(), "sintetic")
    lists.append({"id": "sintetic", "entries": len(synthetic_watchlist())})
    mode = "fixture"
    if is_synthetic_target(clean):
        lists.append({"id": "eu_fsf", "status": "omisă pentru o țintă sintetică"})
    else:
        status: dict[str, Any] = {"id": "eu_fsf"}
        if configured_mode() != "fixture":
            try:
                status.update(await download_eu_fsf())
            except Exception as exc:  # noqa: BLE001 - lista UE e opțională
                status.update({"status": "indisponibilă", "error": describe_error(exc)})
        entities = eu_fsf_entities()
        if entities is not None:
            matches += _candidates(query, entities, "eu_fsf")
            status["entries"] = len(entities)
            mode = "live" if status.get("status") == "descarcat" else "cache"
        else:
            status.setdefault("status", "nedescărcată")
        lists.append(status)
    matches = sorted(matches, key=lambda m: -m["score"])[:8]
    best = matches[0]["score"] if matches else 0.0
    red, yellow = float(param("sanctions_red")), float(param("sanctions_yellow"))
    consulted = ", ".join(LIST_LABELS.get(l["id"], l["id"]) for l in lists if l.get("entries"))
    data = {"name": clean, "normalized": query, "best_score": best, "matches": matches, "lists": lists,
            "thresholds": {"rosu": red, "galben": yellow}}
    if best >= red:
        top = matches[0]
        summary = (f"Posibilă potrivire pentru „{clean}” pe {LIST_LABELS.get(top['list'], top['list'])}: „{top['matched_name']}” "
                   f"(scor {best:.0f}/100); de verificat de un om.")
        signal = "rosu"
    elif best >= yellow:
        label = LIST_LABELS.get(matches[0]["list"], matches[0]["list"])
        summary = f"Potrivire slabă pentru „{clean}” (scor {best:.0f}/100) pe {label}; de verificat."
        signal = "galben"
    else:
        summary = f"Nicio potrivire pentru „{clean}” în listele consultate ({consulted or 'niciuna'})."
        signal = "verde"
    return ToolResult(tool="sanctions_screen", args=args, ok=True, data=data, summary=summary, signal=signal,
                      mode=mode, source_url=EU_FSF_URL if mode in ("live", "cache") else None,
                      latency_ms=int((time.perf_counter() - started) * 1000))


def parse_csv_text(text: str) -> list[dict[str, Any]]:
    """Pentru teste: parsează un CSV `targets.simple` din memorie."""
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{"id": r.get("id"), "name": r.get("name"), "aliases": _split_aliases(r.get("aliases", "")),
             "schema": r.get("schema"), "list": "eu_fsf"} for r in rows]
