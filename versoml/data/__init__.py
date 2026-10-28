"""Datele sintetice ale VersoML: simulatorul Banca Demo, scenariile, setul de aur și depozitele pe zone.

Module:
- `ids`         identificatori RO sintetici (CNP, CUI, IBAN, ONRC), telefoane, IP-uri TEST-NET, domenii.
- `text`        normalizarea diacriticelor (ş/ţ cu sedilă -> ș/ț cu virgulă) și formatarea sumelor.
- `calendar_ro` zile lucrătoare RO și termenul T+1 (oglinda calculatorului din motorul de reguli).
- `world`       `generate_world()`: clienți, conturi, carduri, dispozitive, sesiuni, SCA, tranzacții.
- `aml_world`   lumea AML: conturi interne, cărăuși, tipologii AMLworld/SAML-D/PaySim, alerte, etichete.
- `features`    trăsături obiective pentru M2 și M5 (funcții pure, folosite și de depozite, și de ML).
- `complaints`  generatorul de texte de reclamație în română.
- `scenarios`   `SCENARIOS` și `build_scenario()`.
- `golden`      setul de aur (`golden/golden_40.jsonl`, `golden/generated_300.jsonl`).
- `seed`        `seed_all()`: scrie cele două baze separate, pe zone.
- `repos`       `ClientRepo` și `AmlRepo`: singura cale prin care agenții citesc „sistemele băncii".

Convenție pentru date și ore: toate momentele sunt `datetime` cu fus orar `Europe/Bucharest`;
în baze și în dict-urile întoarse de depozite sunt șiruri ISO 8601 cu offset (ex. `2026-10-28T14:02:11+02:00`).
Toate înregistrările sunt sintetice și poartă `synthetic: True`.
"""
