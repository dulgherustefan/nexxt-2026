# Motorul de reguli VersoML (`versoml/shared/rules`)

LLM-ul extrage și redactează; **regulile decid**. Motorul e determinist și pur: aceleași fapte și aceiași
parametri dau același rezultat, fără rețea și fără I/O în afară de citirea parametrilor. Fiecare decizie are
ID-urile regulilor, rânduri de motivare care citează doar fact_id-uri din `ctx.fact_ids`, termenul ei și
`requires_human`. Fiecare `RuleHit` are versiunea, temeiul și marcajul de încredere al regulii.

```python
from versoml.shared.rules import evaluate, evaluate_aml, catalog, explain, get_params, set_params
out = evaluate(ctx)                 # RulesOutcome: 4 decizii, în ordine: rambursare_t1, recuperare_client,
                                    # recuperare_escroc, raspuns_reclamatie (+ hits, deadlines, params_used)
out = evaluate(ctx, {"auto_refund_cap_ron": 2000})   # peste valorile implicite, fără să citească fișierul
```

`ctx` e un `RuleContext` din contract sau un `RuleContextExt` (aceleași câmpuri plus faptele opționale pentru
DSP, CMP și REC: IBAN-ul beneficiarului, data procesării, ancora constatării, dovezile de la comerciant etc.).
Valorile implicite ale câmpurilor extinse sunt neutre. Indicatorul `{"_classification_ambiguous": True}` se
poate trimite și prin `params`.

## Ordinea deciziei de rambursare (docs/context/11 §4.2, 14 §4)

1. Tipul cererii: APP → `NU_SE_APLICA_T1` (PAY-12, om); dispută cu comerciantul sau eroare → `NU_SE_APLICA_T1`
   și traseul de schemă; credit pe numele victimei → reclamație de credit (DSP-16, CMP-04).
2. 13 luni de la debitare (PAY-01) → altfel `RESPINGE_TARDIV`, semnat de om (DP-02).
3. Singura excepție: HOLD confirmat **și** autoritatea notificată → `EXCEPTIE_FRAUDA_CLIENT` (PAY-03).
4. Altfel rambursare la T+1 (PAY-03, C-70/25): `RAMBURSEAZA` sub plafon (DSP-59) și fără semnale (URM-03,
   DSP-50, DSP-57, DSP-30, HOLD fără notificare); altfel `RAMBURSEAZA_CU_APROBARE`, **tot cu termenul T+1**.
   Neglijența gravă, SCA reușită, OTP divulgat sau „aprobat în aplicație” nu schimbă nimic aici (PAY-15, PAY-02).
5. Recuperarea de la client (PAY-04/05/06) și de la escroc (REC, DSP-52) sunt piste separate: nu ating rambursarea.

## Pachete și ID-uri

| Pachet | Sursa | Reguli |
|---|---|---|
| PAY | docs/context/11 §2.5 (Legea 209/2019, C-70/25) | PAY-01…09, PAY-12, PAY-15; PAY-10 calculator |
| DSP | docs/context/14 (Visa Core Rules, Mastercard [S]) | DSP-03, 16, 20–34, 37, 40, 42, 43, 50–55, 57–59 |
| CMP | docs/context/11 §2.6 | CMP-01…04 (+ verificarea scrisorii: puncte, căi de sesizare) |
| DP | docs/context/11 §2.7 | DP-02 (GDPR art. 22, gardă), DP-03 (explicație, gardă) |
| AML | docs/context/11 §2.2 (Legea 129/2019 art. 6–8) | AML-01…09, doar în `evaluate_aml` |
| **REC** | **extensie**: docs/05 §3–4, ghidurile EPC | REC-01 camt.056 FRAD [S], REC-02 15 zile bancare SCT Inst [S], REC-03 beneficiar BDEM [U], REC-04 RON [U], REC-05 fereastra [U] |
| **URM** | **extensie**: docs/05 §3–5 | URM-01 AI Act art. 5(1)(d) [S], URM-02 tipping-off art. 38(2)/47(1) [S], URM-03 semnale de risc [U], URM-04 propunere RTS [U] |

REC și URM nu există în catalogul docs/context; `catalog()` le marchează cu `extension: true`.
DSP-01, 02, 04–15 aplică articolele din PAY/CMP în fluxul de dispute și sunt **aliasuri**
(`explain("DSP-04")` → PAY-15), după coloana „În 11” din docs/context/14 §3.

## Marcaje de încredere

`P` text oficial citit; `S` sursă secundară; `U` neverificat; `V` verificat în research (nefolosit aici).
Inferențele și propunerile din note (*(inferență)*, *(propunere)*, [Inf]) sunt marcate `U`. Orice valoare [U]
e **parametru**, nu constantă; regulile [U] fără valoare (ex. DSP-50, DSP-54) doar trimit cazul la om.

## Parametri (`params_default.yaml`, suprascrieri în `var/rules_params.json`)

`get_params()`, `set_params(updates)` (validare de tip, interval, opțiuni; `ParamsError`, subclasă de
`ValueError`), `reset_params()`, `param_specs()` (metadate pentru UI). Principalii, toți [U]:
`auto_refund_cap_ron` 5000, `client_fraud_signal_threshold` 0,7, `prior_disputes_signal_threshold` 3,
`eur_ron_rate` 5,0, `refund_end_of_day` 23:59:59, `bank_closure_days` [], `refund_anchor_mode`,
`undue_delay_days` (gol), `competent_authority` (gol), `fraud_report_deadline_mode` (gol),
`recall_window_months` 13, `ron_recall_answer_banking_days` (gol), `banking_calendar` ro, `same_bank_codes` [BDEM].
`require_human_for_unfavourable` e **blocat** (DP-02): încercarea de a-l opri dă `DP_HUMAN_REVIEW_REQUIRED`.

## Calendar (`calendar_ro.py`)

Ora României (zoneinfo), sărbătorile legale din `holidays.Romania` (inclusiv Paștele și Rusaliile ortodoxe),
zilele închise ale băncii ca parametru. `end_of_next_business_day`, `add_business_days`, `add_banking_days`
(implicit zile lucrătoare RO, [U]; opțiune TARGET), `roll_same_hour` (L129 art. 8(10)), `add_months`,
`months_between`. Datele fără fus orar sunt ora României.

## Cum adaugi o regulă

1. Alege ID-ul din docs/context (sau, dacă lipsește, un ID nou în REC/URM, cu marcaj `S` sau `U`).
2. Scrie funcția pură în pachetul ei, cu decoratorul `@rule(...)`: titlu și temei în română (ș/ț cu virgulă),
   `confidence`, `questions`, `params`, `exceptions`, `tests`; docstring scurt în română.
   Funcția primește `(x: RuleContextExt, env: Env)` și întoarce `Finding(rule_id, outcome, explanation, fields,
   data, deadlines)` sau `None`. `fields` = câmpurile folosite (devin citări prin `ctx.fact_ids`).
3. Orice valoare [U] intră în `params_default.yaml` (cu `rules: [ID]`, tip, interval).
4. Dacă regula schimbă o decizie, leag-o în `engine.py` (deciziile au ordinea fixă de mai sus).
5. Adaugă teste în `tests/rules/` cu ID-ul cazului în nume (TC-xx, DT-xx, EX-xx) și rulează:
   `.venv/Scripts/python.exe -m pytest tests/rules -q`.
