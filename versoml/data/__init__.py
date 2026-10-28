"""Datele sintetice ale VersoML: simulatorul Banca Demo, scenariile, setul de aur și depozitele pe zone.

Module:
- `ids`         identificatori RO sintetici (CNP, CUI, IBAN, ONRC), telefoane, IP-uri TEST-NET, domenii.
- `text`        normalizarea diacriticelor (ş/ţ cu sedilă -> ș/ț cu virgulă) și formatarea sumelor.
- `calendar_ro` zile lucrătoare RO și termenul T+1 (oglinda calculatorului din motorul de reguli).
- `world`       `generate_world()`: clienți, conturi, carduri, dispozitive, sesiuni, SCA, tranzacții.
- `aml_world`   lumea AML: conturi interne, cărăuși, tipologii AMLworld/SAML-D/PaySim, alerte, etichete.
- `features`    trăsături obiective pentru M2 și M5 (funcții pure, folosite și de depozite, și de ML).
- `complaints`  generatorul de reclamații în engleză (și corpusul M1, `generate_corpus`, EN sau RO, pe grupuri de șabloane).
- `complaints_ro` aceleași scenarii în română, cu stil dezordonat (fără diacritice, greșeli, informal).
- `typologies`  tipologiile din `typologies_ro.yaml`: reclamații pe tipologie, mapate pe constructorii existenți.
- `corpus_llm`  corpusul augmentat cu Claude pe Bedrock (`corpus/llm_complaints.jsonl`, generat o dată, în git).
- `scenarios`   `SCENARIOS` și `build_scenario()` (cu semnale de jurnal pe tipologie, `CaseParams.typology`).
- `golden`      setul de aur (`golden/golden_40.jsonl`, `golden/generated_300.jsonl`, `golden/typology_cases.jsonl`).
- `freeform`    `golden/freeform_60.jsonl`: reclamații libere fără `transaction_refs`, pentru matcher.
- `seed`        `seed_all()`: scrie cele două baze separate, pe zone.
- `repos`       `ClientRepo` și `AmlRepo`: singura cale prin care agenții citesc „sistemele băncii".

Convenție pentru date și ore: toate momentele sunt `datetime` cu fus orar `Europe/Bucharest`;
în baze și în dict-urile întoarse de depozite sunt șiruri ISO 8601 cu offset (ex. `2026-10-28T14:02:11+02:00`).
Toate înregistrările sunt sintetice și poartă `synthetic: True`.
"""
