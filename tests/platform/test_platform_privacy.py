"""PrivacyProxy: recall pe un set sintetic (formate dificile), precizie, pseudonime stabile, restaurare, sink-uri."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st
from versoml_platform_synth import make_cnp, make_iban

from versoml.contracts import Labels, Sink, Trust
from versoml.shared.privacy import (PrivacyProxy, RawPIIError, check_sink, cross_check, detect, explain_sink,
                                    normalize_ro)

SYNTH_CNP_75 = make_cnp("1", "850615", 75, 123)   # județ fictiv 71–79 (docs/06 §2)
SYNTH_CNP_70 = make_cnp("2", "920304", 70, 7)
BDEM_IBAN = make_iban("BDEM", "0000060012345678")
XBNK_IBAN = make_iban("XBNK", "1234567890123456")

# (text, tip așteptat, cheia normalizată așteptată)
POSITIVES = [
    ("CNP: 1900101401091", "CNP", "1900101401091"),
    ("cnp 6010315431239, născută în 2001", "CNP", "6010315431239"),
    ("CNP-ul meu este 2580722120774.", "CNP", "2580722120774"),
    ('{"cnp": "1830512123183"}', "CNP", "1830512123183"),
    (f"CNP sintetic {SYNTH_CNP_75}", "CNP", SYNTH_CNP_75),
    (f"cod {SYNTH_CNP_70}", "CNP", SYNTH_CNP_70),
    ("IBAN RO49AAAA1B31007593840000", "IBAN", "RO49AAAA1B31007593840000"),
    ("contul RO54 RZBR 0000 0600 1234 5678 al meu", "IBAN", "RO54RZBR0000060012345678"),
    ("ro54rzbr0000060012345678", "IBAN", "RO54RZBR0000060012345678"),
    ("IBAN:RO62BRDE0000007000123456.", "IBAN", "RO62BRDE0000007000123456"),
    ("RO54-RZBR-0000-0600-1234-5678", "IBAN", "RO54RZBR0000060012345678"),
    (f"spre {' '.join(BDEM_IBAN[i:i + 4] for i in range(0, 24, 4))} azi", "IBAN", BDEM_IBAN),
    (f"({XBNK_IBAN})", "IBAN", XBNK_IBAN),
    ("DE89 3704 0044 0532 0130 00", "IBAN", "DE89370400440532013000"),
    ("card 4111 1111 1111 1111", "CARD", "4111111111111111"),
    ("4111-1111-1111-1111", "CARD", "4111111111111111"),
    ("PAN4111111111111111exp", "CARD", "4111111111111111"),
    ("Mastercard 5555 5555 5555 4444", "CARD", "5555555555554444"),
    ("Amex 3782 822463 10005", "CARD", "378282246310005"),
    ("6011 1111 1111 1117", "CARD", "6011111111111117"),
    ("Visa 13 cifre 4222222222222", "CARD", "4222222222222"),
    ("MC seria 2: 2223 0031 2200 3222", "CARD", "2223003122003222"),
    ("card 4111 1111 1111 1111 exp 12/28", "CARD", "4111111111111111"),
    ("+40 722 123 456", "TELEFON", "+40722123456"),
    ("0040722123456", "TELEFON", "+40722123456"),
    ("sunați 0722-123-456", "TELEFON", "+40722123456"),
    ("0722.123.456", "TELEFON", "+40722123456"),
    ("(0722) 123 456", "TELEFON", "+40722123456"),
    ("+40 (0) 722 123 456", "TELEFON", "+40722123456"),
    ("07 22 12 34 56", "TELEFON", "+40722123456"),
    ("fix 021 123 4567", "TELEFON", "+40211234567"),
    ("+40-722-123-456", "TELEFON", "+40722123456"),
    ("tel:0722123456", "TELEFON", "+40722123456"),
    # foreign numbers, with a country code
    ("+44 20 7946 0958", "TELEFON", "+442079460958"),
    ("+44 (0)20 7946 0958", "TELEFON", "+442079460958"),
    ("sunați la 0049 30 123456789", "TELEFON", "+4930123456789"),
    ("call me on +1 (415) 555-0132, thanks", "TELEFON", "+14155550132"),
    ("+373 69 123 456 (Moldova)", "TELEFON", "+37369123456"),
    ("+33 6 12 34 56 78", "TELEFON", "+33612345678"),
    ("ana.testescu@example.ro", "EMAIL", "ana.testescu@example.ro"),
    ("ștefan.pop@example.ro", "EMAIL", "ștefan.pop@example.ro"),
    ("ANA_TESTESCU+banca@mail.example.com", "EMAIL", "ana_testescu+banca@mail.example.com"),
    ("x@sub.domain.test,", "EMAIL", "x@sub.domain.test"),
    ("CI seria XT nr. 123456", "CI", "XT123456"),
    ("Subsemnatul Popescu Ion, domiciliat", "NUME", "ion popescu"),
    ("Doamna Ionescu Maria a sunat", "NUME", "ionescu maria"),
    ("Nume: TESTESCU ANA-MARIA", "NUME", "ana maria testescu"),
    ("Cu stimă,\nIon Popescu", "NUME", "ion popescu"),
    # English complaints
    ("My name is Ana Testescu and I bank with you.", "NUME", "ana testescu"),
    ("I'm Ion Popescu, a customer since 2010.", "NUME", "ion popescu"),
    ("This is Maria Ionescu, I called yesterday.", "NUME", "ionescu maria"),
    ("Kind regards,\nMaria Ionescu", "NUME", "ionescu maria"),
    ("Thank you in advance.\nAna-Maria Testescu", "NUME", "ana maria testescu"),
    ("Thanks,\nRADU ENACHE", "NUME", "enache radu"),
    ("Account holder: Radu Enache", "NUME", "enache radu"),
    ("Mrs Ionescu called about the card.", "NUME", "ionescu"),
]

NEGATIVES = [
    "Suma de 3.200,00 lei a fost debitată pe 28.10.2026 la ora 14:30.",
    "Data: 02.10.2026 14:30, referința TX-2026-000123.",
    "Contul RO49 **** **** 0000 a fost creditat.",
    "Cardul terminat în 1111 (**** **** **** 1111).",
    "Codul OTP 123456 nu se comunică nimănui.",
    "Sunați la 0800 801 227 sau *2000.",
    "Hotărârea CJUE C-70/25 din 15.10.2026; art. 173 din Legea 209/2019.",
    "Referința plății 0000000000000000.",
    "Numărul de dosar 1234567890123.",
    "IBAN cu cifre de control greșite RO55RZBR0000060012345678.",
    "CNP cu cifră de control greșită 1630615123458.",
    "Firma SC EXEMPLU SRL, CUI RO12345674, domeniul livrare-bancademo.example.",
    # English text without a name
    "Thanks,\nPlease answer quickly.",
    "I'm writing about a transaction on my account.",
    "This is Demo Bank's helpline.",
    "I am Very upset about this.",
    "Best regards,\nDemo Bank",
    "Dear Sir or Madam, I paid RON 3,200.00 on 28 Oct 2026 at 14:30.",
    "Hi, I have an urgent problem. Help me get my money back please.",
    # a plus sign or a leading 00 that is not a phone number
    "Sold: +12.500.000,00 lei.",
    "Programare la ora 14:00 1234 5678.",
    "Primită la 2026-10-27T18:30:00+02:00.",
]


@pytest.fixture
def proxy() -> PrivacyProxy:
    return PrivacyProxy()


@pytest.mark.parametrize("text, kind, key", POSITIVES)
def test_recall_on_synthetic_formats(text, kind, key):
    found = [(f.type, f.key) for f in detect(text) if f.pii]
    assert (kind, key) in found, found


def test_recall_and_precision_summary():
    hits = sum(1 for text, kind, key in POSITIVES if (kind, key) in [(f.type, f.key) for f in detect(text) if f.pii])
    false_alarms = [text for text in NEGATIVES if any(f.pii for f in detect(text))]
    assert hits / len(POSITIVES) == 1.0
    assert false_alarms == []


@pytest.mark.parametrize("text", NEGATIVES)
def test_no_pii_in_negative_samples(text):
    assert [f.type for f in detect(text) if f.pii] == []


def test_public_identifiers_are_tagged_not_redacted(proxy):
    text = "Plata către SC EXEMPLU SRL (CUI RO12345674), după un SMS de la https://livrare-bancademo.example/plata."
    kinds = {f["type"]: f["pii"] for f in proxy.scan(text)}
    assert kinds == {"FIRMA": False, "CUI": False, "DOMENIU": False}
    out, vault = proxy.pseudonymize(text, "CT-1")
    assert out == text and vault == {}
    assert proxy.stats()["public_tags"] == {"FIRMA": 1, "CUI": 1, "DOMENIU": 1}


def test_cui_is_tagged_only_with_a_valid_check_digit(proxy):
    tags = [(f["type"], f["value"]) for f in proxy.scan("CUI 18547290; cod fiscal 12345678; CIF RO 18547290")]
    assert tags == [("CUI", "18547290"), ("CUI", "RO 18547290")]


def test_pseudonymize_restore_round_trip(proxy):
    text = ("Subsemnata Testescu Ana-Maria, CNP 6010315431239, IBAN RO49 AAAA 1B31 0075 9384 0000, card "
            "4111 1111 1111 1111, tel +40 722 123 456, e-mail ana.testescu@example.ro, CI seria XT nr. 123456.")
    out, vault = proxy.pseudonymize(text, "CT-1", known={"Ana-Maria Testescu": "CLIENT"})
    assert out == ("Subsemnata <CLIENT_1>, CNP <CNP_1>, IBAN <IBAN_1>, card <CARD_1>, tel <TELEFON_1>, "
                   "e-mail <EMAIL_1>, CI seria <CI_1>.")
    assert proxy.restore(out, vault) == text
    proxy.assert_llm_safe({"messages": [{"role": "user", "content": out}]})


def test_tokens_are_stable_per_case_and_numbered_in_reading_order(proxy):
    first, _ = proxy.pseudonymize("De pe RO49AAAA1B31007593840000 pe RO54RZBR0000060012345678.", "CT-1")
    assert first == "De pe <IBAN_1> pe <IBAN_2>."
    again, vault = proxy.pseudonymize("Iar RO54 RZBR 0000 0600 1234 5678 și ro49aaaa1b31007593840000.", "CT-1")
    assert again == "Iar <IBAN_2> și <IBAN_1>."
    other, _ = proxy.pseudonymize("RO54RZBR0000060012345678", "CT-2")
    assert other == "<IBAN_1>"
    assert set(vault) == {"<IBAN_1>", "<IBAN_2>"}


def test_known_names_match_case_diacritics_and_order(proxy):
    known = {"Ana-Maria Teștescu": "CLIENT", "Ion Popescu": "BENEFICIAR"}
    text = "TESTESCU ANA-MARIA, ana maria testescu și Ion Popescu; popescu ion"
    out, vault = proxy.pseudonymize(text, "CT-3", known=known)
    assert out == "<CLIENT_1>, <CLIENT_1> și <BENEFICIAR_1>; <BENEFICIAR_1>"
    later, _ = proxy.pseudonymize("A revenit Ana-Maria Testescu.", "CT-3")  # numele rămân reținute pe caz
    assert later == "A revenit <CLIENT_1>."
    explicit, _ = proxy.pseudonymize("Maria Ionescu", "CT-4", known={"Maria Ionescu": "<MARTOR_3>"})
    assert explicit == "<MARTOR_3>"


def test_public_role_known_entity_is_left_in_text(proxy):
    out, _ = proxy.pseudonymize("Beneficiar: Exemplu Logistic Demo SRL", "CT-5",
                                known={"Exemplu Logistic Demo SRL": "FIRMA"})
    assert out == "Beneficiar: Exemplu Logistic Demo SRL"


def test_restore_is_tolerant_to_llm_formatting(proxy):
    _, vault = proxy.pseudonymize("CNP 6010315431239", "CT-6")
    for variant in ("<CNP_1>", "< cnp_1 >", "&lt;CNP_1&gt;", "[CNP_1]", "CNP_1"):
        assert proxy.restore(f"Clientul cu {variant}.", vault) == "Clientul cu 6010315431239."


def test_pseudonymize_obj_for_tool_payloads(proxy):
    payload = {"tool": "bank-core.get_transaction", "args": {"iban": "RO49AAAA1B31007593840000"},
               "result": [{"phone": "0722 123 456", "amount": 3200}]}
    out, vault = proxy.pseudonymize_obj(payload, "CT-7")
    assert out == {"tool": "bank-core.get_transaction", "args": {"iban": "<IBAN_1>"},
                   "result": [{"phone": "<TELEFON_1>", "amount": 3200}]}
    assert proxy.restore_obj(out, vault) == payload


def test_assert_llm_safe_blocks_raw_pii_without_echoing_it(proxy):
    proxy.pseudonymize("x", "CT-8", known={"Ana-Maria Testescu": "CLIENT"})
    for payload in ({"system": "ok", "messages": [{"content": "IBAN RO49AAAA1B31007593840000"}]},
                    [{"cnp": 1900101401091}], "Clienta Ana-Maria Testescu a sunat", {"6010315431239": "cheie"}):
        with pytest.raises(RawPIIError) as err:
            proxy.assert_llm_safe(payload)
        assert err.value.findings
        for raw in ("RO49AAAA1B31007593840000", "1900101401091", "Ana-Maria Testescu", "6010315431239"):
            assert raw not in str(err.value) and raw not in json.dumps(err.value.findings, ensure_ascii=False)
    proxy.assert_llm_safe({"messages": [{"content": "<CLIENT_1> contestă plata spre <IBAN_1>."}]})
    stats = proxy.stats()
    assert stats["assert_checks"] == 5 and stats["assert_blocked"] == 4


# ------------------------------------------------------------ a doua verificare (crosscheck)

def test_crosscheck_shares_no_code_with_the_recognizers():
    from versoml.shared.privacy import crosscheck as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("recognizers" in name or name.endswith(".proxy") for name in imported if name)


@pytest.mark.parametrize("text, kind, key", [p for p in POSITIVES if p[1] in ("CNP", "IBAN", "CARD", "TELEFON", "EMAIL")
                                             and p[0] != "PAN4111111111111111exp"])
def test_crosscheck_finds_the_identifiers_on_its_own(text, kind, key):
    assert kind in [h["type"] for h in cross_check(text)]


@pytest.mark.parametrize("text", NEGATIVES)
def test_crosscheck_is_quiet_on_negative_samples(text):
    assert cross_check(text) == []


def test_crosscheck_reads_each_value_once():
    found = cross_check("De pe RO49 AAAA 1B31 0075 9384 0000 pe RO54RZBR0000060012345678, tel 0722 123 456.")
    assert [h["type"] for h in found] == ["IBAN", "IBAN", "TELEFON"]
    assert cross_check("Popescu,Ion a sunat; Ion Popescu a revenit.", ["Ion Popescu"]) == [
        {"type": "NUME", "masked": "Io•••••••cu"}]


def test_guard_blocks_what_only_the_second_check_sees(proxy):
    text = "CNP 1900101 401091, scris cu un spațiu"
    assert not [f for f in detect(text) if f.pii]  # the masking recognizers miss this format
    with pytest.raises(RawPIIError) as err:
        proxy.assert_llm_safe({"messages": [{"content": text}]})
    assert [(f["type"], f["check"]) for f in err.value.findings] == [("CNP", "crosscheck")]
    assert "1900101" not in str(err.value) and "401091" not in json.dumps(err.value.findings)


def test_guard_counts_a_value_both_checks_see_once(proxy):
    assert [(f["type"], f["check"]) for f in proxy.find_raw_pii("IBAN RO49AAAA1B31007593840000")] == [
        ("IBAN", "recognizers")]


def test_guard_leaves_known_public_names_in_the_text(proxy):
    proxy.pseudonymize("x", "CT-11", known={"Exemplu Logistic Demo SRL": "FIRMA", "Ana Testescu": "CLIENT"})
    proxy.assert_llm_safe("Beneficiar: Exemplu Logistic Demo SRL")
    with pytest.raises(RawPIIError):
        proxy.assert_llm_safe("Testescu, Ana a sunat")


ENTITIES = st.sampled_from([
    "6010315431239", "1900101401091", SYNTH_CNP_75, "RO49AAAA1B31007593840000", "RO54 RZBR 0000 0600 1234 5678",
    BDEM_IBAN, "4111 1111 1111 1111", "5555-5555-5555-4444", "+40 722 123 456", "0722.123.456",
    "ana.testescu@example.ro", "radu.fictivescu@mail.example.com",
])
TEMPLATES = st.sampled_from(["Datele: {a} și {b}.", "{a}, apoi {b}", "Am primit de la {a} un mesaj; contul {b}."])


@hsettings(max_examples=60, deadline=None)
@given(TEMPLATES, ENTITIES, ENTITIES)
def test_property_no_raw_pii_after_pseudonymize_and_exact_restore(template, a, b):
    proxy = PrivacyProxy()
    text = template.format(a=a, b=b)
    out, vault = proxy.pseudonymize(text, "CT-P")
    proxy.assert_llm_safe(out)
    assert a not in out and b not in out
    if detect(a)[0].key != detect(b)[0].key:  # aceeași entitate scrisă diferit primește același pseudonim
        assert proxy.restore(out, vault) == text


def test_input_is_normalized_to_comma_below(proxy):
    out, _ = proxy.pseudonymize("Plată către \u015etefan, tranzac\u0163ie", "CT-9")
    assert out == normalize_ro("Plată către Ștefan, tranzacție")


def test_vault_persists_in_zone_db(tmp_path):
    db = tmp_path / "client_zone.db"
    first = PrivacyProxy(db_path=db)
    out, _ = first.pseudonymize("IBAN RO49AAAA1B31007593840000, Ion Popescu", "CT-10", known={"Ion Popescu": "CLIENT"})
    second = PrivacyProxy(db_path=db)
    again, vault = second.pseudonymize("Ion Popescu, RO49AAAA1B31007593840000 și 0722 123 456", "CT-10")
    assert out == "IBAN <IBAN_1>, <CLIENT_1>"
    assert again == "<CLIENT_1>, <IBAN_1> și <TELEFON_1>"
    assert vault["<IBAN_1>"] == "RO49AAAA1B31007593840000"


# ------------------------------------------------------------ pașaportul datelor

@pytest.mark.parametrize("labels, sink, allowed", [
    (Labels(conf="client", sinks=[Sink.CLIENT, Sink.LLM]), Sink.CLIENT, True),
    (Labels(conf="client", sinks=[Sink.CLIENT, Sink.LLM]), Sink.LLM, True),
    (Labels(conf="client", sinks=[Sink.CLIENT]), Sink.LLM, False),
    (Labels(conf="client", sinks=[Sink.CLIENT, Sink.OSINT]), Sink.OSINT, False),
    (Labels(conf="client", sinks=[Sink.CLIENT, Sink.AML]), Sink.AML, True),
    (Labels(conf="aml-only", sinks=[Sink.AML, Sink.CLIENT, Sink.LETTER, Sink.LLM]), Sink.CLIENT, False),
    (Labels(conf="aml-only", sinks=[Sink.AML, Sink.CLIENT, Sink.LETTER, Sink.LLM]), Sink.LETTER, False),
    (Labels(conf="aml-only", sinks=[Sink.AML, Sink.LLM]), Sink.LLM, True),
    (Labels(conf="aml", sinks=[Sink.AML, Sink.OSINT]), Sink.OSINT, False),
    (Labels(conf="public", sinks=[Sink.OSINT, Sink.LLM, Sink.CLIENT]), Sink.OSINT, True),
    (Labels(conf="public", trust=Trust.UNTRUSTED, sinks=[Sink.LETTER, Sink.OSINT]), Sink.LETTER, False),
    (Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT, Sink.LLM]), Sink.LLM, True),
])
def test_check_sink_matrix(labels, sink, allowed):
    assert check_sink(labels, sink) is allowed
    ok, reason = explain_sink(labels.model_dump(), sink.value)
    assert ok is allowed and reason
