"""The corpus: rule catalog, docs/context, case studies, typologies and precedents, built into chunks.

Committed snapshot under versoml/data/kb/: chunks.jsonl (static corpus), precedents.jsonl (client zone only)
and manifest.json (fingerprints of the sources, counts, model, build time). At load time the fingerprint is
checked; a stale snapshot is rebuilt in memory from the sources (vectors are content-addressed, so unchanged
chunks keep theirs).
"""

from __future__ import annotations

import hashlib
import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from versoml.config import PACKAGE_DIR, ROOT
from versoml.knowledge.chunker import CHUNKER_VERSION, Chunk, chunk_case_studies, chunk_markdown
from versoml.knowledge.text import fold, marks_in, normalize_ro, rule_ids_in, weakest_mark

log = logging.getLogger("versoml.knowledge.corpus")

KB_DIR = PACKAGE_DIR / "data" / "kb"
CHUNKS_FILE = "chunks.jsonl"
PRECEDENTS_FILE = "precedents.jsonl"
MANIFEST_FILE = "manifest.json"

CONTEXT_DIR = ROOT / "docs" / "context"
CASE_STUDIES = ROOT / "docs" / "03_cazuri_reale_raiffeisen.md"
TYPOLOGIES = PACKAGE_DIR / "data" / "typologies_ro.yaml"
GOLDEN_DIR = PACKAGE_DIR / "data" / "golden"


# ---------------------------------------------------------------- rules catalog


def _context_file(ref: str) -> str:
    """'docs/context/11 §2.5' → 'docs/context/11_reguli_....md §2.5' when the file exists."""
    head, _, section = ref.partition(" ")
    if head.startswith("docs/context/") and head.count("/") == 2:
        number = head.rsplit("/", 1)[1]
        matches = sorted(CONTEXT_DIR.glob(f"{number}_*.md"))
        if matches:
            return f"{matches[0].relative_to(ROOT).as_posix()} {section}".strip()
    return ref


_ROW_ID = re.compile(r"^\|\s*\*{0,2}([A-Z]{2,4}-\d{2})\*{0,2}\s*\|\s*(.+?)\s*\|")


def catalog_rows() -> dict[str, tuple[str, str]]:
    """Rule text from the docs/context catalog tables: rule ID → (the "Regulă" cell, file). First row wins."""
    rows: dict[str, tuple[str, str]] = {}
    for path in context_files():
        for line in normalize_ro(path.read_text(encoding="utf-8")).splitlines():
            m = _ROW_ID.match(line.strip())
            if m and m.group(1) not in rows and len(m.group(2)) >= 30:
                rows[m.group(1)] = (" ".join(m.group(2).split()), path.relative_to(ROOT).as_posix())
    return rows


def rule_chunks() -> list[Chunk]:
    """One chunk per rule in the registry, with ID, title, text, confidence mark, legal basis and source.

    The rule's row in the docs/context catalog (Romanian) is quoted too, so a rule is found in both languages.
    """
    from versoml.shared.rules import param_specs
    from versoml.shared.rules.registry import PACK_TITLES, all_rules

    specs = param_specs()
    rows = catalog_rows()
    out: list[Chunk] = []
    for spec in all_rules():
        lines = [f"{spec.rule_id} · {spec.title}"]
        if spec.description:
            lines.append(spec.description.replace("\n", " "))
        for rid in (spec.rule_id, *spec.aliases):
            if rid in rows:
                text, path = rows[rid]
                cut = text if len(text) <= 700 else text[:700].rsplit(" ", 1)[0] + " …"
                lines.append(f"In {path.rsplit('/', 1)[-1]} ({rid}): {cut}")
                break
        lines.append(f"Legal basis: {spec.basis}")
        lines.append(f"Confidence: [{spec.confidence.value}]")
        if spec.params:
            parts = []
            for name in spec.params:  # names and marks only: values are run-time settings, not knowledge
                mark = getattr(specs.get(name), "confidence", None)
                mark = getattr(mark, "value", mark)
                parts.append(name + (f" [{mark}]" if mark else ""))
            lines.append("Parameters (configurable): " + ", ".join(parts))
        if spec.exceptions:
            lines.append("Exceptions: " + ", ".join(spec.exceptions))
        if spec.aliases:
            lines.append("Also cited as: " + ", ".join(spec.aliases))
        if spec.extension:
            lines.append("Extension rule: not in the docs/context catalog.")
        lines.append(f"Pack: {PACK_TITLES.get(spec.pack, spec.pack)}. Zone: {spec.zone.value}. Kind: {spec.kind}.")
        text = normalize_ro("\n".join(lines))
        out.append(Chunk(
            id=f"rule:{spec.rule_id}", kind="rule", title=f"{spec.rule_id} · {spec.title}", text=text,
            source=_context_file(spec.source), confidence=spec.confidence.value,
            rule_ids=[spec.rule_id, *spec.aliases],
            meta={"pack": spec.pack, "zone": spec.zone.value, "rule_kind": spec.kind, "basis": spec.basis,
                  "registry": f"versoml/shared/rules/packs/{spec.pack.lower()}.py", "aliases": list(spec.aliases),
                  "tests": list(spec.tests), "extension": spec.extension},
        ))
    return out


# ---------------------------------------------------------------- typologies


_MARK_NORMAL = {"P": "P", "S": "S", "U": "U"}


def _mark(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().strip("[]").upper()
    if value.startswith("P-PROIECT"):
        return "U"
    letters = [ch for ch in value if ch in "PSU"]
    if not letters:
        return None
    return min(letters, key=lambda x: {"U": 0, "S": 1, "P": 2}[x])


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)]


def typology_chunks(path: Path = TYPOLOGIES) -> list[Chunk]:
    """One chunk per typology in versoml/data/typologies_ro.yaml. Missing or invalid file: no chunks."""
    if not path.exists():
        return []
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a broken file must not break the knowledge base
        log.warning("typologies file is not valid YAML (%s); skipped", type(exc).__name__)
        return []
    items = data.get("typologies") if isinstance(data, dict) else data
    if not isinstance(items, list):
        log.warning("typologies file has no `typologies:` list; skipped")
        return []
    source = path.relative_to(ROOT).as_posix()
    out: list[Chunk] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or not (item.get("name") or item.get("name_ro")):
            continue
        tid = str(item["id"]).strip()
        if tid in seen:
            continue
        seen.add(tid)
        name, name_ro = str(item.get("name") or "").strip(), str(item.get("name_ro") or "").strip()
        lines = [f"{name}" + (f" ({name_ro})" if name_ro and name_ro != name else "")]
        facts = []
        for label, key in (("Family", "family"), ("PSD2 class", "psd2_class"), ("Scenario", "maps_to_scenario")):
            if item.get(key):
                facts.append(f"{label}: {item[key]}")
        if item.get("channels"):
            facts.append("Channels: " + ", ".join(_as_list(item.get("channels"))))
        if facts:
            lines.append(". ".join(facts) + ".")
        if item.get("story"):
            lines.append(str(item["story"]).strip())
        steps = _as_list(item.get("steps"))
        if steps:
            lines.append("Steps: " + " ".join(f"{i}) {s.strip()}" for i, s in enumerate(steps, 1)))
        signals = _as_list(item.get("bank_signals"))
        if signals:
            lines.append("Bank signals: " + "; ".join(s.strip() for s in signals))
        sources = [s for s in (item.get("sources") or []) if isinstance(s, dict)]
        if sources:
            lines.append("Sources: " + "; ".join(
                " · ".join(str(s.get(k)) for k in ("title", "publisher", "date") if s.get(k))
                + (f" [{_mark(s.get('confidence'))}]" if _mark(s.get("confidence")) else "") for s in sources))
        text = normalize_ro("\n".join(lines))
        mark = _mark(item.get("confidence")) or weakest_mark(marks_in(text))
        title = normalize_ro(name or name_ro)
        meta = {"family": item.get("family"), "psd2_class": item.get("psd2_class"),
                "channels": _as_list(item.get("channels")), "scenario": item.get("maps_to_scenario"),
                "name_ro": name_ro, "typology_id": tid,
                "sources": [{k: s.get(k) for k in ("title", "publisher", "url", "date", "confidence")} for s in sources]}
        out.append(Chunk(id=f"typ:{tid}", kind="typology", title=title, text=text, source=source,
                         confidence=mark, rule_ids=rule_ids_in(text), meta={**meta, "part": "overview"}))
        # what customers write, in a chunk of its own: it matches complaint text without diluting the overview
        cues_en, cues_ro = _as_list(item.get("complaint_cues_en")), _as_list(item.get("complaint_cues_ro"))
        if cues_en or cues_ro:
            cue_lines = [lines[0]]
            if cues_en:
                cue_lines.append("Complaint cues: " + " ".join(c.strip() for c in cues_en))
            if cues_ro:
                cue_lines.append("Indicii în reclamație: " + " ".join(c.strip() for c in cues_ro))
            cue_text = normalize_ro("\n".join(cue_lines))
            out.append(Chunk(id=f"typ:{tid}#cues", kind="typology", title=f"{title} · complaint cues",
                             text=cue_text, source=source, confidence=mark, rule_ids=rule_ids_in(cue_text),
                             meta={**meta, "part": "cues"}))
    return out


# ---------------------------------------------------------------- precedents (client zone only)


VERDICT_TEXT = {
    "RAMBURSEAZA": "refund by the end of the next business day, issued by the rules engine",
    "RAMBURSEAZA_CU_APROBARE": "refund by the end of the next business day, after a human approval",
    "EXCEPTIE_FRAUDA_CLIENT": "refund withheld: reasonable suspicion of customer fraud, authority notified",
    "RESPINGE_TARDIV": "rejected: the customer notified more than 13 months after the debit",
    "NU_SE_APLICA_T1": "the T+1 refund does not apply (authorized payment or merchant dispute); other track",
    "CHARGEBACK": "chargeback",
}
RECOVERY_TEXT = {
    "RECHEMARE": "recall of the transfer",
    "CHARGEBACK": "chargeback",
    "RECUPERARE_PROPUSA": "recovery proposed",
    "NU_RECOMANDAM_RECUPERARE": "recovery not recommended",
    None: "none",
}


def _facts_line(ctx: dict) -> str:
    facts: list[str] = []
    if ctx.get("sca_performed") is True:
        facts.append(f"SCA performed ({ctx.get('sca_method') or 'method not recorded'})")
    elif ctx.get("sca_performed") is False:
        facts.append("no SCA")
    if ctx.get("eci"):
        facts.append(f"ECI {ctx['eci']}" + ("; CAVV present" if ctx.get("cavv_present") else ""))
    if ctx.get("screen_showed_amount_and_payee") is True:
        facts.append("the screen showed the amount and the payee")
    elif ctx.get("screen_showed_amount_and_payee") is False:
        facts.append("the screen did not show the amount and the payee")
    if ctx.get("device_known") is False:
        facts.append("unknown device")
    elif ctx.get("device_known") is True:
        facts.append("known device")
    if ctx.get("seconds_after_click") is not None:
        facts.append(f"payment {ctx['seconds_after_click']} s after the link click")
    if ctx.get("sim_swap_hours_before") is not None:
        facts.append(f"SIM swap {ctx['sim_swap_hours_before']} h before")
    if ctx.get("beneficiary_new") is True:
        facts.append("new beneficiary")
    if ctx.get("duplicate_of"):
        facts.append("duplicate of an earlier payment")
    if ctx.get("merchant_mcc"):
        facts.append(f"merchant MCC {ctx['merchant_mcc']}")
    if ctx.get("prior_disputes_12m"):
        facts.append(f"{ctx['prior_disputes_12m']} prior disputes in 12 months")
    if ctx.get("client_admits_sharing_credentials"):
        facts.append("the customer admits sharing credentials")
    if ctx.get("client_admits_approving_in_app"):
        facts.append("the customer admits approving in the app")
    if ctx.get("hold_signal"):
        facts.append("HOLD signal received" + (", authority notified" if ctx.get("hold_authority_notified") else ""))
    try:
        executed = datetime.fromisoformat(ctx["executed_at"])
        notified = datetime.fromisoformat(ctx["notified_at"])
        hours = (notified - executed).total_seconds() / 3600
        facts.append(f"notified {hours / 24:.0f} days after the debit" if hours >= 72
                     else f"notified {hours:.0f} h after the debit")
    except (KeyError, TypeError, ValueError):
        pass
    return "; ".join(facts)


def _engine_rule_ids(ctx: dict) -> list[str]:
    """The rules the engine fires on the golden facts (retrieval metadata only; decisions stay in the engine)."""
    try:
        from versoml.contracts import RuleContext
        from versoml.shared.rules import evaluate

        outcome = evaluate(RuleContext.model_validate(ctx))
    except Exception:  # noqa: BLE001 - a precedent without rule IDs is still a precedent
        return []
    ids: dict[str, None] = {}
    for decision in outcome.decisions:
        for rid in decision.rule_ids:
            ids.setdefault(rid, None)
    return list(ids)


def precedent_text(case_id: str, scenario: str, text: str, outcome: dict, *, channel: str | None = None,
                   amount: dict | None = None, facts: str = "", note: str = "", label: str = "Customer says") -> str:
    head = f"Past case {case_id} (synthetic)." + (f" Scenario: {scenario}" if scenario else "")
    if note:
        head += f" ({note})"
    head += "."
    if channel or amount:
        bits = []
        if channel:
            bits.append(f"Channel: {channel}")
        if amount and amount.get("value") is not None:
            bits.append(f"Amount: {amount['value']:g} {amount.get('currency', 'RON')}")
        head += " " + ". ".join(bits) + "."
    lines = [head]
    if text:
        lines.append(f"{label}: {text}")
    if facts:
        lines.append(f"Bank facts: {facts}.")
    verdict = outcome.get("verdict") or outcome.get("rambursare_t1")
    parts = []
    if verdict:
        parts.append(f"{verdict} ({VERDICT_TEXT.get(verdict, verdict)})")
    if "requires_human" in outcome:
        parts.append("human approval required" if outcome["requires_human"] else "no human approval needed")
    if "recovery" in outcome:
        parts.append(f"recovery: {RECOVERY_TEXT.get(outcome['recovery'], outcome['recovery'])}")
    if outcome.get("chargeback_reason"):
        parts.append(f"chargeback reason {outcome['chargeback_reason']}")
    if outcome.get("rule_ids"):
        parts.append("rules " + ", ".join(outcome["rule_ids"]))
    if parts:
        lines.append("Outcome: " + "; ".join(parts) + ".")
    return normalize_ro("\n".join(lines))


def safe_case_text(text: str, case_id: str) -> str:
    """Pseudonymized complaint text (a throwaway vault: the pseudonyms cannot be reversed from the KB)."""
    from versoml.shared.privacy import PrivacyProxy

    proxy = PrivacyProxy()
    safe, vault = proxy.pseudonymize(normalize_ro(text or ""), case_id=f"kb-{case_id}")
    # names inside a sentence ("sent 300 RON to Ana Pop") have no cue for the recognizers: catch them here
    used = [int(m) for m in re.findall(r"<PERSOANA_(\d+)>", safe)]
    counter = iter(range(max(used, default=0) + 1, 10_000))
    names: dict[str, str] = {}

    def swap(m: re.Match) -> str:
        if {fold(m.group(1)), fold(m.group(2))} & _NOT_NAME_WORDS:
            return m.group(0)
        key = m.group(0)
        if key not in names:
            names[key] = f"<PERSOANA_{next(counter)}>"
        return names[key]

    safe = _INLINE_NAME.sub(swap, safe)
    return " ".join(safe.split())


_NAME_WORD = r"[A-ZĂÂÎȘȚ][a-zăâîșț]+(?:-[A-ZĂÂÎȘȚ][a-zăâîșț]+)?"
_INLINE_NAME = re.compile(rf"(?<=[a-zăâîșț0-9,:] )({_NAME_WORD}) ({_NAME_WORD})(?![a-zăâîșț])")
# words of the synthetic merchants, banks and brands that appear in complaints (not personal names)
_NOT_NAME_WORDS = frozenset("""
demo deom deemo dmeo bank banca banci example exmaple travel electro fashion north south east west pharmacy fuel
mega courier bookshop shop store market apps app global visa secure mastercard apple google pay revolut olx posta
romana fan cargo sameday express online services service center centre group media games game sport sports home
house city digital tech mobile telecom energy food foods auto motors airlines air hotel hotels booking gadgetworld
""".split())


def golden_precedents(directory: Path = GOLDEN_DIR) -> list[Chunk]:
    """Past cases from the golden set: pseudonymized summary + expected outcome (+ the rules the engine fires)."""
    out: list[Chunk] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            complaint = row.get("complaint") or {}
            ctx = row.get("rule_context") or {}
            case_id = complaint.get("case_id") or ctx.get("case_id") or row.get("id")
            if not case_id or case_id in seen:
                continue
            seen.add(case_id)
            expected = dict(row.get("expected") or {})
            injection = bool(expected.get("injection_suspected")) or row.get("scenario") == "injectie_document"
            if injection:
                # hidden instructions stay out of the knowledge base (they would reach prompts as context)
                said = ("The complaint and its attachments carried hidden instructions for the automated system; "
                        "they were treated as data and ignored.")
            else:
                said = safe_case_text(complaint.get("text", ""), case_id)
            rule_ids = _engine_rule_ids(ctx) if ctx else []
            outcome = {
                "verdict": expected.get("rambursare_t1"),
                "requires_human": expected.get("requires_human"),
                "recovery": expected.get("recovery"),
                "chargeback_reason": expected.get("chargeback_reason"),
                "t1_deadline": expected.get("t1_deadline"),
                "injection_suspected": expected.get("injection_suspected", False),
                "rule_ids": rule_ids,
            }
            scenario = row.get("scenario") or ctx.get("scenario") or ""
            text = precedent_text(case_id, scenario, said, outcome, channel=ctx.get("channel"),
                                  amount=ctx.get("amount"), facts=_facts_line(ctx) if ctx else "",
                                  note=str(row.get("notes") or "")[:120])
            out.append(Chunk(
                id=f"prec:{case_id}", kind="precedent", title=f"Past case {case_id} · {scenario}", text=text,
                source=path.relative_to(ROOT).as_posix(), confidence=None, rule_ids=rule_ids,
                meta={"outcome": outcome, "scenario": scenario, "case_id": case_id, "golden_id": row.get("id"),
                      "channel": ctx.get("channel"), "origin": "golden", "synthetic": True},
            ))
    return out


# ---------------------------------------------------------------- the whole corpus


def context_files() -> list[Path]:
    return sorted(CONTEXT_DIR.glob("*.md"))


def build_static_corpus() -> list[Chunk]:
    """Rules + docs/context + case studies + typologies (both zones)."""
    chunks: list[Chunk] = []
    chunks += rule_chunks()
    for path in context_files():
        chunks += chunk_markdown(path, root=ROOT)
    if CASE_STUDIES.exists():
        chunks += chunk_case_studies(CASE_STUDIES, root=ROOT)
    chunks += typology_chunks()
    ids = [c.id for c in chunks]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"Duplicate chunk IDs: {dupes[:5]}")
    return chunks


def _hash_file(h: "hashlib._Hash", path: Path) -> None:
    h.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
    h.update(b"\x00")
    h.update(path.read_bytes() if path.exists() else b"<missing>")
    h.update(b"\x00")


def static_fingerprint(rules: list[Chunk] | None = None) -> str:
    """Changes when a source of the static corpus (rule registry, docs, typologies) or the chunker changes."""
    h = hashlib.sha256(f"chunker={CHUNKER_VERSION}\x00".encode())
    for chunk in rules if rules is not None else rule_chunks():
        h.update(json.dumps(chunk.to_json(), sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for path in context_files():
        _hash_file(h, path)
    _hash_file(h, CASE_STUDIES)
    _hash_file(h, TYPOLOGIES)
    return h.hexdigest()


def precedents_fingerprint() -> str:
    h = hashlib.sha256(f"chunker={CHUNKER_VERSION}\x00".encode())
    for path in sorted(GOLDEN_DIR.glob("*.jsonl")):
        _hash_file(h, path)
    return h.hexdigest()


def write_jsonl(path: Path, chunks: list[Chunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_json(), ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[Chunk]:
    if not path.exists():
        return []
    out: list[Chunk] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(Chunk.from_json(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return out


def read_manifest(kb_dir: Path = KB_DIR) -> dict:
    path = kb_dir / MANIFEST_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_snapshot(static: list[Chunk], precedents: list[Chunk], *, model: str, kb_dir: Path = KB_DIR,
                   extra: dict | None = None) -> dict:
    """Write chunks.jsonl, precedents.jsonl and manifest.json. Returns the manifest."""
    write_jsonl(kb_dir / CHUNKS_FILE, static)
    write_jsonl(kb_dir / PRECEDENTS_FILE, precedents)
    by_kind: dict[str, int] = {}
    for chunk in [*static, *precedents]:
        by_kind[chunk.kind] = by_kind.get(chunk.kind, 0) + 1
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunker_version": CHUNKER_VERSION,
        "embedding_model": model,
        "static_fingerprint": static_fingerprint(),
        "precedents_fingerprint": precedents_fingerprint(),
        "counts": {"static": len(static), "precedents": len(precedents), "by_kind": dict(sorted(by_kind.items()))},
        **(extra or {}),
    }
    (kb_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
