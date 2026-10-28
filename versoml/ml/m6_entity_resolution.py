"""M6: legarea cazurilor între ele (docs/05 §8, docs/06 §4.2).

Două cazuri se leagă dacă au în comun: IBAN-ul beneficiarului, CUI-ul, denumirea firmei (normalizată, potrivire
aproximativă cu rapidfuzz), domeniul escrocului (la nivel de domeniu înregistrat), telefonul (E.164) sau
amprenta dispozitivului. Numele de persoane NU leagă singure cazuri (prea multe omonime).
Rezultatul: clustere cu motivul fiecărei legături, ca analistul AML să vadă de ce s-a aprins graful.

Intrare: dict-urile din `AmlRepo.list_referrals()`, `DisputeFacts` ca dict, sau dict-uri plate
(iban, cui, company, domain, url, phone, device).
"""

from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz

from versoml.data import ids
from versoml.data.text import fold

LEGAL_FORMS = r"\b(s\.?\s?r\.?\s?l\.?|s\.?\s?a\.?|p\.?\s?f\.?\s?a\.?|i\.?\s?i\.?|i\.?\s?f\.?|ltd|gmbh|s\.?\s?n\.?\s?c\.?|s\.?\s?c\.?\s?s\.?)\b"
REASON_RO = {"iban": "același IBAN beneficiar", "cui": "același CUI", "denumire_firma": "aceeași firmă (denumire normalizată)",
             "domeniu": "același domeniu înregistrat", "telefon": "același număr de telefon", "dispozitiv": "același dispozitiv"}


def normalize_company(name: str | None) -> str | None:
    if not name:
        return None
    s = fold(name)
    s = re.sub(LEGAL_FORMS, " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def looks_like_company(name: str | None, cui: str | None = None) -> bool:
    if cui:
        return True
    return bool(name) and re.search(LEGAL_FORMS, fold(name)) is not None


def _extract(r: dict) -> dict:
    payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
    ben = r.get("beneficiary") or payload.get("beneficiary") or {}
    att = r.get("attack") or payload.get("attack") or {}
    iban = r.get("beneficiary_iban") or ben.get("iban") or r.get("iban")
    name = r.get("beneficiary_name") or ben.get("name") or r.get("company")
    cui = r.get("beneficiary_cui") or ben.get("cui") or r.get("cui")
    domains = {x for x in [r.get("domain"), att.get("domain"), r.get("url"), att.get("url")] if x}
    phone = r.get("phone") or att.get("phone")
    device = r.get("device") or r.get("device_fingerprint") or r.get("device_id") or att.get("device")
    amount = r.get("amount")
    if isinstance(amount, dict):
        amount = amount.get("value")
    if amount is None and isinstance(payload.get("amount"), dict):
        amount = payload["amount"].get("value")
    return {"case_id": r.get("case_id"),
            "iban": ids.normalize_iban(iban) if iban else None,
            "cui": ids.normalize_cui(cui) if cui else None,
            "company": normalize_company(name) if looks_like_company(name, cui) else None,
            "company_raw": name if looks_like_company(name, cui) else None,
            "domains": sorted({ids.registered_domain(d) for d in domains if ids.registered_domain(d)}),
            "phone": ids.normalize_phone(phone) if phone else None,
            "device": str(device) if device else None,
            "amount": float(amount) if amount is not None else 0.0}


class _UF:
    def __init__(self, items: list[str]):
        self.p = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def link_cases(referrals: list[dict], *, name_threshold: int = 90, include_singletons: bool = False) -> list[dict]:
    """Clustere de cazuri legate: [{cluster_id, case_ids, size, links:[{a, b, reason, value, score, explanation}],
    shared:{ibans, cuis, companies, domains, phones, devices}, amount_total}]."""
    items = [_extract(r) for r in referrals if r.get("case_id")]
    by_id = {it["case_id"]: it for it in items}
    uf = _UF(list(by_id))
    links: list[dict] = []

    def link(a: str, b: str, reason: str, value: str, score: float = 1.0) -> None:
        if a == b:
            return
        a, b = sorted((a, b))
        links.append({"a": a, "b": b, "reason": reason, "value": value, "score": round(score, 3),
                      "explanation": f"{REASON_RO[reason]}: {value}"})
        uf.union(a, b)

    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for it in items:
        for reason, vals in (("iban", [it["iban"]]), ("cui", [it["cui"]]), ("domeniu", it["domains"]),
                             ("telefon", [it["phone"]]), ("dispozitiv", [it["device"]])):
            for v in vals:
                if v:
                    index[(reason, v)].append(it["case_id"])
    for (reason, value), cases in sorted(index.items()):
        cases = sorted(set(cases))
        for other in cases[1:]:
            link(cases[0], other, reason, ids.format_iban(value) if reason == "iban" else value)
    comps = sorted((it["case_id"], it["company"], it["company_raw"]) for it in items if it["company"])
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            score = fuzz.token_sort_ratio(comps[i][1], comps[j][1])
            if score >= name_threshold:
                link(comps[i][0], comps[j][0], "denumire_firma", comps[i][2], score / 100.0)
    groups: dict[str, list[str]] = defaultdict(list)
    for cid in sorted(by_id):
        groups[uf.find(cid)].append(cid)
    clusters = []
    for root, cases in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[1][0])):
        if len(cases) < 2 and not include_singletons:
            continue
        cl_links = [l for l in links if l["a"] in cases]
        members = [by_id[c] for c in cases]
        shared = {
            "ibans": sorted({v for (r, v), cs in index.items() if r == "iban" and len(set(cs) & set(cases)) > 1}),
            "cuis": sorted({v for (r, v), cs in index.items() if r == "cui" and len(set(cs) & set(cases)) > 1}),
            "domains": sorted({v for (r, v), cs in index.items() if r == "domeniu" and len(set(cs) & set(cases)) > 1}),
            "phones": sorted({v for (r, v), cs in index.items() if r == "telefon" and len(set(cs) & set(cases)) > 1}),
            "devices": sorted({v for (r, v), cs in index.items() if r == "dispozitiv" and len(set(cs) & set(cases)) > 1}),
            "companies": sorted({l["value"] for l in cl_links if l["reason"] == "denumire_firma"}),
        }
        clusters.append({"cluster_id": f"CL-{len(clusters) + 1:03d}", "case_ids": cases, "size": len(cases),
                         "links": cl_links, "shared": shared,
                         "amount_total": round(sum(m["amount"] for m in members), 2)})
    return clusters
