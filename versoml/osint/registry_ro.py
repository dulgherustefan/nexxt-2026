"""Registre românești: ANAF (firma după CUI), validarea IBAN (mod 97 + codul băncii), cursul BNR.

CUI și IBAN se validează local întâi (docs/context/12 §2.2–2.3). Un CUI cu cifră de control greșită
e semnal roșu și nu ajunge la ANAF. Serviciul ANAF cere cel mult 1 cerere/secundă (limita e în base).
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

from versoml.osint.base import (
    FIXTURE_NOW,
    Ctx,
    Interp,
    SourceError,
    ToolResult,
    configured_mode,
    expect_status,
    fmt_age,
    hours_since,
    http_request,
    is_synthetic_target,
    load_fixture,
    now_ro,
    parse_dt,
    run_source,
    synthetic_registry,
    tool,
)
from versoml.osint.params import param
from versoml.osint.util import fold, normalize_ro

# ---------------------------------------------------------------- CUI

CUI_WEIGHTS = "753217532"
ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"


def cui_check_digit(body: str) -> int:
    """Cifra de control pentru corpul CUI (fără ultima cifră, maximum 9 cifre)."""
    return sum(int(a) * int(b) for a, b in zip(body.zfill(9), CUI_WEIGHTS)) * 10 % 11 % 10


def normalize_cui(value: str) -> tuple[str, bool]:
    """('18547290', True) pentru 'RO 185 472 90'; al doilea element arată prefixul RO (TVA)."""
    text = normalize_ro(value).upper().replace(" ", "").replace("-", "").replace(".", "")
    return (text[2:], True) if text.startswith("RO") else (text, False)


def validate_cui(value: str) -> list[str]:
    """Erorile de format ale unui CUI/CIF (listă goală = valid)."""
    cui, _ = normalize_cui(value)
    if not cui.isdigit():
        return ["format: doar cifre (după eliminarea prefixului RO)"]
    if not 2 <= len(cui) <= 10:
        return ["lungime în afara intervalului 2-10"]
    if cui[0] == "0":
        return ["începe cu 0"]
    if cui_check_digit(cui[:-1]) != int(cui[-1]):
        return ["cifra de control greșită"]
    return []


def _addr(block: dict[str, Any], prefix: str) -> dict[str, Any]:
    keys = {"judet": "denumire_Judet", "localitate": "denumire_Localitate", "strada": "denumire_Strada",
            "numar": "numar_Strada", "cod_postal": "cod_Postal", "detalii": "detalii_Adresa"}
    return {k: normalize_ro(str(block.get(prefix + v) or "")).strip() or None for k, v in keys.items()}


def parse_anaf_record(record: dict[str, Any], now) -> dict[str, Any]:
    general = record.get("date_generale") or {}
    tva = record.get("inregistrare_scop_Tva") or {}
    rtvai = record.get("inregistrare_RTVAI") or {}
    inactive = record.get("stare_inactiv") or {}
    split = record.get("inregistrare_SplitTVA") or {}
    state = normalize_ro(general.get("stare_inregistrare") or "")
    registered = parse_dt(general.get("data_inregistrare"))
    hours = hours_since(registered, now)
    return {
        "cui": str(general.get("cui") or ""),
        "denumire": normalize_ro(general.get("denumire") or "") or None,
        "adresa": normalize_ro(general.get("adresa") or "") or None,
        "nr_reg_com": general.get("nrRegCom") or None,
        "cod_caen": general.get("cod_CAEN") or None,
        "forma_juridica": normalize_ro(general.get("forma_juridica") or "") or None,
        "data_inregistrare": general.get("data_inregistrare") or None,
        "age_days": round(hours / 24, 1) if hours is not None else None,
        "stare_inregistrare": state or None,
        "radiat": "radiere" in fold(state) or bool(inactive.get("dataRadiere")),
        "inactiv": bool(inactive.get("statusInactivi")),
        "data_inactivare": inactive.get("dataInactivare") or None,
        "data_reactivare": inactive.get("dataReactivare") or None,
        "platitor_tva": bool(tva.get("scpTVA")),
        "tva_la_incasare": bool(rtvai.get("statusTvaIncasare")),
        "split_tva": bool(split.get("statusSplitTVA")),
        "e_factura": bool(general.get("statusRO_e_Factura")),
        "organ_fiscal": normalize_ro(general.get("organFiscalCompetent") or "") or None,
        "sediu_social": _addr(record.get("adresa_sediu_social") or {}, "s"),
        "domiciliu_fiscal": _addr(record.get("adresa_domiciliu_fiscal") or {}, "d"),
    }


def _build_anaf(raw: Any, ctx: Ctx) -> Interp:
    cui = ctx.args["cui"]
    found = raw.get("found") or []
    if not found:
        data = {"cui": cui, "valid": True, "found": False, "anaf_called": True}
        return Interp(data, f"CUI {cui} e valid ca format, dar ANAF nu găsește nicio firmă cu el.", "galben")
    data = {"valid": True, "found": True, "anaf_called": True, **parse_anaf_record(found[0], ctx.now)}
    name = data["denumire"] or f"CUI {cui}"
    age = fmt_age((data["age_days"] or 0) * 24) if data["age_days"] is not None else "vârstă necunoscută"
    if data["radiat"]:
        return Interp(data, f"{name} (CUI {cui}) este radiată: {data['stare_inregistrare']}.", "rosu")
    if data["inactiv"]:
        return Interp(data, f"{name} (CUI {cui}) e contribuabil inactiv din {data['data_inactivare']}.", "rosu")
    tva = "plătitoare de TVA" if data["platitor_tva"] else "neplătitoare de TVA"
    if data["age_days"] is not None and data["age_days"] < float(param("company_new_days")):
        return Interp(data, f"{name} (CUI {cui}) e înregistrată de doar {age}, {tva}.", "galben")
    signal = "verde" if data["platitor_tva"] else "neutru"
    return Interp(data, f"{name} (CUI {cui}) e activă, înregistrată acum {age}, {tva}.", signal)


def _synthetic_cui(cui: str) -> bool:
    return cui in set(synthetic_registry().get("cuis", [])) or load_fixture("anaf_company", [cui]) is not None


@tool("anaf_company", zones=("aml",), group="osint-ro")
async def anaf_company(cui: str) -> ToolResult:
    """Firma după CUI din serviciul web ANAF v9 (denumire, adresă, stare, inactiv/radiat, TVA, data înregistrării); CUI-ul se validează local întâi."""
    started = time.perf_counter()
    digits, vat_prefix = normalize_cui(cui)
    args = {"cui": digits or normalize_ro(cui).strip()}
    errors = validate_cui(cui)
    if errors:
        data = {"cui": args["cui"], "valid": False, "errors": errors, "vat_prefix": vat_prefix, "anaf_called": False}
        return ToolResult(tool="anaf_company", args=args, ok=True, data=data, signal="rosu", mode="offline",
                          summary=f"CUI {args['cui']} invalid ({errors[0]}); ANAF nu a fost interogat. "
                                  "O firmă beneficiară cu CUI invalid e un semnal de fraudă.",
                          latency_ms=int((time.perf_counter() - started) * 1000))
    synthetic = _synthetic_cui(digits) or is_synthetic_target(digits)
    query_day = (FIXTURE_NOW if synthetic or configured_mode() == "fixture" else now_ro()).date().isoformat()

    async def fetch() -> tuple[Any, str | None]:
        resp = await http_request("POST", ANAF_URL, json=[{"cui": int(digits), "data": query_day}])
        if resp.status_code not in (200, 404):
            raise SourceError(f"ANAF HTTP {resp.status_code}")
        body = resp.json()
        if not isinstance(body, dict) or ("found" not in body and "notFound" not in body):
            raise SourceError("ANAF: răspuns fără found/notFound")
        return body, ANAF_URL

    return await run_source("anaf_company", args, key=digits, fetch=fetch, build=_build_anaf, ttl_s=86400,
                            label="ANAF", synthetic=synthetic)


# ---------------------------------------------------------------- IBAN

IBAN_LENGTHS = {
    "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22, "DK": 18, "EE": 20, "ES": 24,
    "FI": 18, "FR": 27, "GB": 22, "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21,
    "LT": 20, "LU": 20, "LV": 21, "MD": 24, "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25, "RO": 24,
    "SE": 24, "SI": 19, "SK": 24, "TR": 26, "UA": 29,
}
# Codurile de bancă RO. Încrederea: S = confirmat de o sursă secundară (docs/context/12 §2.3);
# U = cunoscut de echipă, neverificat în lista oficială BNR (Anexa 1 nu a fost citită); SINTETIC = fictiv.
RO_BANKS: dict[str, tuple[str, str]] = {
    "RZBR": ("Raiffeisen Bank", "S"),
    "BTRL": ("Banca Transilvania", "S"),
    "BRDE": ("BRD", "S"),
    "RNCB": ("BCR", "S"),
    "INGB": ("ING", "S"),
    "NBOR": ("Banca Națională a României", "U"),
    "TREZ": ("Trezoreria Statului", "U"),
    "CECE": ("CEC Bank", "U"),
    "BACX": ("UniCredit Bank", "U"),
    "UGBI": ("Garanti BBVA", "U"),
    "WBAN": ("Intesa Sanpaolo Bank", "U"),
    "MIND": ("ProCredit Bank", "U"),
    "CARP": ("Patria Bank", "U"),
    "PIRB": ("First Bank", "U"),
    "OTPV": ("OTP Bank", "U"),
    "EXIM": ("EximBank", "U"),
    "CITI": ("Citibank Europe", "U"),
    "FNNB": ("Credit Europe Bank", "U"),
    "EGNA": ("Vista Bank", "U"),
    "BREL": ("Libra Internet Bank sau Revolut (disputat în note)", "U"),
    "BDEM": ("Banca Demo (sintetic)", "SINTETIC"),
    "XBNK": ("Banca X (sintetic)", "SINTETIC"),
    "YBNK": ("Banca Y (sintetic)", "SINTETIC"),
    "ZBNK": ("Banca Z (sintetic)", "SINTETIC"),
}
# Prezente doar în lista Faker ro_RO (docs/context/12): codul e plauzibil, denumirea neverificată
FAKER_ONLY_CODES = frozenset(
    "ABNA BUCU ARBL BPOS BROM BITR BRMA DAFB MIRB CRCO BSEA HVBL CRDZ BNRB PORL MIRO RZBL ROIN TRFD BACX VBBU DARO"
    .split()
)


def _iban_numeric(text: str) -> int:
    return int("".join(str(int(c, 36)) for c in text))


def iban_check_digits(country: str, bban: str) -> str:
    return f"{98 - _iban_numeric((bban + country + '00').upper()) % 97:02d}"


def _iban_interp(iban: str) -> tuple[dict[str, Any], str, str]:
    raw = normalize_ro(iban)
    compact = re.sub(r"[\s-]", "", raw).upper()
    data: dict[str, Any] = {"iban": compact, "valid": False, "errors": [], "warnings": []}
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", compact):
        data["errors"].append("format: 2 litere (țara) + 2 cifre de control + cont alfanumeric")
        return data, f"IBAN invalid ca format: {compact or iban}.", "galben"
    country = compact[:2]
    data.update({"country": country, "check_digits": compact[2:4], "bban": compact[4:],
                 "formatted": " ".join(compact[i:i + 4] for i in range(0, len(compact), 4))})
    expected = IBAN_LENGTHS.get(country)
    if expected is None:
        data["warnings"].append(f"lungimea pentru țara {country} nu e în tabelul local")
    elif len(compact) != expected:
        data["errors"].append(f"lungime {len(compact)}, așteptat {expected} pentru {country}")
    if country == "RO" and not re.fullmatch(r"RO\d{2}[A-Z]{4}[A-Z0-9]{16}", compact):
        data["errors"].append("format RO: RO + 2 cifre + 4 litere (cod bancă) + 16 alfanumerice")
    if _iban_numeric(compact[4:] + compact[:4]) % 97 != 1:
        data["errors"].append("cifre de control (mod 97) greșite")
    if data["errors"]:
        return data, f"IBAN invalid: {data['errors'][0]}.", "galben"
    data["valid"] = True
    if country != "RO":
        return data, f"IBAN valid ({country}); banca nu se determină local pentru alte țări.", "neutru"
    code = compact[4:8]
    name, confidence = RO_BANKS.get(code, (None, None))
    data.update({"bank_code": code, "bank_name": name, "bank_confidence": confidence,
                 "synthetic": confidence == "SINTETIC"})
    if confidence == "SINTETIC":
        return data, f"IBAN valid: {name}, cod {code} fictiv (nu există la BNR).", "neutru"
    if name:
        note = "" if confidence == "S" else " (denumire neverificată în lista BNR)"
        return data, f"IBAN valid, {name}{note}.", "neutru"
    if code in FAKER_ONLY_CODES:
        data["warnings"].append(f"cod bancă {code}: doar în lista Faker, denumire neverificată")
        return data, f"IBAN valid; codul de bancă {code} nu are o denumire verificată.", "neutru"
    data["warnings"].append(f"cod bancă {code} necunoscut")
    return data, f"IBAN valid ca sumă de control, dar codul de bancă {code} e necunoscut.", "galben"


@tool("validate_iban", group="osint-ro")
def validate_iban(iban: str) -> ToolResult:
    """Validează local un IBAN (mod 97, lungimea pe țară) și, pentru RO, identifică banca după cod (inclusiv codurile fictive BDEM/XBNK/YBNK/ZBNK)."""
    started = time.perf_counter()
    data, summary, signal = _iban_interp(iban)
    return ToolResult(tool="validate_iban", args={"iban": data["iban"]}, ok=True, data=data, summary=summary,
                      signal=signal, mode="offline", latency_ms=int((time.perf_counter() - started) * 1000))


# ---------------------------------------------------------------- curs BNR

BNR_URL = "https://curs.bnr.ro/nbrfxrates.xml"   # www.bnr.ro/nbrfxrates.xml redirecționează acum spre prima pagină
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"


def parse_bnr_xml(text: str) -> dict[str, Any]:
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    cube = root.find(".//{*}Cube")
    if cube is None:
        raise SourceError("XML BNR fără Cube")
    rates = {}
    for rate in cube.findall("{*}Rate"):
        multiplier = int(rate.get("multiplier") or 1)
        rates[rate.get("currency")] = round(float(rate.text) / multiplier, 6)
    return {"date": cube.get("date"), "rates": rates}


async def _fx_fetch() -> tuple[Any, str | None]:
    try:
        resp = await http_request("GET", BNR_URL, retries=1)
        expect_status(resp)
        if "<DataSet" not in resp.text:
            raise SourceError("BNR: răspunsul nu e XML-ul de cursuri")
        return {"provider": "bnr", "xml": resp.text}, BNR_URL
    except Exception:  # noqa: BLE001 - rezerva: cursul de referință BCE (nu e cursul BNR)
        resp = await http_request("GET", FRANKFURTER_URL, params={"base": "EUR", "symbols": "RON"}, retries=1)
        expect_status(resp)
        return {"provider": "ecb", "json": resp.json()}, FRANKFURTER_URL


def _build_fx(raw: Any, ctx: Ctx) -> Interp:
    amount = ctx.args.get("amount_eur")
    if raw.get("provider") == "ecb":
        body = raw.get("json") or {}
        eur_ron = float((body.get("rates") or {})["RON"])
        data: dict[str, Any] = {"provider": "ecb", "date": body.get("date"), "eur_ron": eur_ron,
                                "rates": {"EUR": eur_ron}, "note": "curs de referință BCE, nu cursul BNR"}
    else:
        parsed = parse_bnr_xml(raw["xml"])
        eur_ron = parsed["rates"]["EUR"]
        data = {"provider": "bnr", "date": parsed["date"], "eur_ron": eur_ron, "rates": parsed["rates"]}
    rate = f"{eur_ron:.4f}".replace(".", ",")
    summary = f"Cursul {'BNR' if data['provider'] == 'bnr' else 'BCE (rezervă, nu BNR)'} din {data['date']}: 1 EUR = {rate} lei."
    if amount is not None:
        data["amount_eur"] = amount
        data["amount_ron"] = round(float(amount) * eur_ron, 2)
        ron = f"{data['amount_ron']:.2f}".replace(".", ",")
        summary += f" {float(amount):g} EUR = {ron} lei."
    return Interp(data, summary, "neutru")


@tool("bnr_fx_rates", group="osint-ro")
async def bnr_fx_rates(amount_eur: float | None = None) -> ToolResult:
    """Cursul de referință BNR (XML zilnic), cu EUR/RON și opțional conversia unei sume în lei (de exemplu un plafon exprimat în euro)."""
    args: dict[str, Any] = {} if amount_eur is None else {"amount_eur": amount_eur}
    return await run_source("bnr_fx_rates", args, key="latest", fetch=_fx_fetch, build=_build_fx, ttl_s=6 * 3600,
                            label="Cursul BNR", fixture_keys=["latest"])
