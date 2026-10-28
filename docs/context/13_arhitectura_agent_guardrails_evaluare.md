# 13 · Arhitectura agentului: design, guardrails, evaluare și justificare

> **Pentru:** echipa NEXXT Summit 2026, challenge Raiffeisen, track „AI for Operational Efficiency” (redactat pe 28 octombrie 2026).
> **Subiect:** un agent care primește un document sau date, aplică reguli predefinite și produce un rezultat sau semnalează o excepție, pe date sintetice. Agnostic de proces; exemple din popriri, KYC refresh, dispute card și triaj AML.

**Surse.** Trei note din `research_notes/Oportunități AI operațiuni Raiffeisen România/`: `ai_operatiuni_bancare_benchmark_reglementare.md` (sursa principală); `raiffeisen_profil_ai_hackathon.md` (doar stack, AI existent, declarațiile CEO-ului, formatul NEXXT/VibeHack, câștigătorii din 2025); `date_sintetice_formate_tooling.md` (doar framework-urile de agenți și uneltele de evaluare).

| Marcaj | Sens |
|---|---|
| **[vendor]** | afirmație de marketing a unui furnizor |
| **[bank self-reported]** | anunțul unei bănci despre propriile rezultate |
| **[secondary]** | găsit doar în agregator sau presă; sursa primară nu a fost deschisă |
| **[independent]** | regulator, studiu academic sau instanță |
| *neverificat*, *proiecție*, *ilustrativ*, *search snippet* | niveluri de încredere preluate din note |
| *(inferență)* | sinteza autorului notelor, nu un fapt din sursă |
| *(propunere)* | recomandare de inginerie a acestui document (nume de tool-uri, câmpuri JSON, praguri simbolice, livrabile); nu e fapt sursat |

Cifrele pe care notele nu le marchează rămân nemarcate și aici.

---

## 1. Rezumat

- **Principiu.** LLM-ul extrage și redactează, motorul de reguli decide, pragurile de încredere rutează, omul aprobă tot ce are consecințe, iar fiecare pas se loghează. Notele găsesc tiparul în practica bancară și în cercetarea de securitate *(inferență)*.
- **Orchestrare.** Planner cu allowlist de tool-uri read-only și „draft”; niciun tool nu mută bani, iar acțiunile de tip plată trec prin controalele existente, ca în pilotul BT × Visa din iulie 2026.
- **„Situații neprevăzute” (25%).** Surprize scriptate: injecție într-un PDF, CNP greșit, alocație protejată, ordin duplicat, scan ilizibil, tip necunoscut, fiecare cu rută și reason code vizibile în trace.
- **Testabilitate (20%).** Set golden sintetic de 50–200 de cazuri, metrici pe etape, rulări repetate și un evidence pack (raport, audit log, script de demo).
- **Reglementare.** Procesele de operațiuni din note nu sunt în Anexa III a AI Act *(lectura notelor, nu aviz juridic)*; evaluarea bonității persoanelor fizice e high-risk de la **2 decembrie 2027** (Reg. (UE) 2026/1744). Din cauza GDPR art. 22 și a hotărârii SCHUFA, creditul rămâne „pre-check pentru underwriter”, nu decizie.
- **Business.** Baseline-uri sursate (≈95% alerte AML fals pozitive; $25–50 per dispută lucrată manual [vendor]; ≈$2.200 per review KYC corporate) plus un uplift măsurat. Gartner (peste 40% din proiectele agentice anulate până la finalul lui 2027) justifică scope-ul îngust.
- **Raiffeisen.** Agentul e pasul de la ARI (asistent de cunoștințe) la un agent de proces cu aprobator uman, în linia CEO-ului: AI pregătește decizia, iar supravegherea crește cu impactul.
- **Limite.** Uplift-urile sunt aproape toate [vendor] sau [bank self-reported], nu există volume românești publice, iar CCD2 art. 18 și „PoC-ul de automatizare a reclamațiilor la nivel de grup” lipsesc din cele trei note (§12).

| Criteriu (pondere) | Ce arătăm | Unde |
|---|---|---|
| Design și orchestrare (25%) | allowlist, buclă multi-pas, escaladare, surprize | §2, §3 |
| Completitudine și testabilitate (20%) | scenariu verificabil, set golden, evidence pack | §7 |
| Originalitate (15%) | agent de excepții cu reguli executabile și audit | §9 |
| Cercetare și domeniu (15%) | baseline-uri sursate, moduri de eșec reale | §4, §8 |
| Arhitectură și reproductibilitate (15%) | contract de date, module, setup într-o comandă | §2, §7, §11 |
| Business (10%) | formulă ROI cu intrări de la mentori | §8 |

*Ponderile sunt cele transmise de echipă; rulebook-ul public listează șapte criterii, fără ponderi.*

---

## 2. Arhitectura de referință: „LLM-ul extrage și redactează, motorul de reguli decide”

Nicio autoritate nu a publicat o arhitectură prescriptivă pentru agenți în bănci. Ce urmează e recomandarea din note, sprijinită pe tiparul „ML propune, regulile decid” din reconcilieri (Digiqt), pe tiparele anti-injecție ale lui Beurer-Kellner et al. (2025) și pe practica human-in-the-loop de la ING, Lloyds, BNP Paribas și Alpha Bank.

### 2.1 Componente

| # | Componentă | Responsabilitate | Implementare |
|---|---|---|---|
| 1 | Ingestie | atribuie `case_id`, calculează hash-ul, păstrează originalul; marchează conținutul ca *untrusted* | cod |
| 2 | Clasificare | tip de caz dintr-o listă închisă; tip necunoscut sau încredere mică → escaladare | LLM în carantină; eticheta selectează un plan fix (Action-Selector) |
| 3 | Extragere structurată | JSON strict, cu încredere și span sursă (pagină, offset) per câmp; textul documentului e tratat doar ca date | LLM în carantină, fără tool-uri (Dual LLM, Context-Minimization) |
| 4 | Validatori deterministici | checksum-uri, consistență între documente, logica datelor, totaluri | cod |
| 5 | Motor de reguli | procedurile băncii, de felul celor pe care ARI le indexează deja, ca reguli testabile și versionate | cod |
| 6 | Calcule | sume, toleranțe, termene; LLM-ul nu face aritmetică | cod |
| 7 | Orchestrator / planner | fixează planul din `case_type`, cheamă doar tool-uri din allowlist, nu citește text brut | mașină de stări cu decizii LLM la ramificații |
| 8 | Rutare pe încredere | STP, four-eyes, cerere de completare sau escaladare | cod, praguri în config |
| 9 | Coadă de revizuire umană | inbox cu dovezi, `rule_hits` și motivare pre-redactată | UI |
| 10 | Generare răspuns | draft din *decision record* și șablon, niciodată din documentul brut | LLM cu șablon |
| 11 | Audit log | fiecare prompt, apel de tool, rezultat de regulă, versiune de model, prag și decizie umană | append-only |

Exemple de reguli din note: la popriri, potrivirea pe CNP, excluderile pe tip de cont, limitele de venit protejat, reconcilierea sumelor între bănci și ordinea de prioritate; la reconcilieri, ferestre de toleranță și potriviri many-to-one. Componentele urmează recomandarea din note *(inferență)*; granițele și numele lor sunt *(propunere)*.

### 2.2 Fluxul

```mermaid
flowchart TD
    subgraph UNTRUSTED["Zonă de conținut neîncrezut: LLM în carantină, fără tool-uri"]
        A["1 · Ingestie<br/>case_id, hash, original păstrat"]
        B["2 · Clasificare<br/>etichetă dintr-o listă închisă"]
        C["3 · Extragere structurată<br/>JSON + încredere + span sursă"]
    end
    subgraph PRIV["Zonă privilegiată: vede doar câmpuri tipizate"]
        O["7 · Orchestrator / planner<br/>plan fixat din case_type, allowlist"]
        D["4 · Validatori deterministici"]
        E["5 · Motor de reguli versionat"]
        F["6 · Calcule deterministe"]
        G{"8 · Rutare pe încredere<br/>și rezultatele regulilor"}
    end
    S["STP: rezultat propus<br/>plus eșantion verificat post-hoc"]
    Q["9 · Coadă de revizuire umană<br/>four-eyes"]
    R["Draft de cerere de completare"]
    H["Decizie umană"]
    T["10 · Generare răspuns<br/>din decision record și șablon"]
    X["Trimitere sau execuție<br/>prin controalele existente"]
    L[("11 · Audit log append-only")]

    A --> B
    B -->|tip cunoscut| C
    B -->|tip necunoscut| Q
    C --> D --> E --> F --> G
    G -->|încredere mare, toate regulile trec| S
    G -->|încredere medie sau conflict de reguli| Q
    G -->|câmp obligatoriu lipsă| R
    G -->|input neașteptat sau injecție suspectată| Q
    R --> Q
    Q --> H
    S --> T
    H --> T
    T --> X
    O -. pornește .-> B
    O -.-> C
    O -.-> D
    O -.-> E
    O -.-> F
    O -.-> T
    B & C & D & E & F & G & H & T --> L
```

STP înseamnă „dosar complet, fără revizuire individuală” doar pentru acțiunile cu impact redus. La blocări de sume, credit sau dispoziții AML, STP se oprește la propunere și decide omul (§5.1).

### 2.3 Contractul de date

Un singur plic JSON per caz, completat pe rând de componente. Exemplu: o poprire oprită pentru revizuire.

```json
{
  "contract_version": "1.0",
  "case_id": "CASE-0001",
  "case_type": "poprire",
  "idempotency_key": "sha256(document)|poprire|rules-2026.10.1",
  "documents": [
    {"doc_id": "DOC-1", "sha256": "…", "mime_type": "application/pdf",
     "pages": 2, "trust": "untrusted", "quality": {"readable": true}}
  ],
  "classification": {
    "label": "poprire", "confidence": 0.93,
    "alternatives": [{"label": "ridicare_poprire", "confidence": 0.05}],
    "model": "classifier@pinned", "prompt_version": "classify-v3"
  },
  "extraction": {
    "schema_id": "poprire-v2",
    "fields": {
      "debtor_id": {
        "value": "tok_cnp_7f3a", "confidence": 0.98,
        "evidence": {"doc_id": "DOC-1", "page": 1, "char_start": 412, "char_end": 425},
        "validators": [{"name": "cnp_checksum", "result": "pass"}]
      },
      "amount_due": {
        "value": "12500.00", "currency": "RON", "confidence": 0.71,
        "evidence": {"doc_id": "DOC-1", "page": 1, "char_start": 890, "char_end": 899},
        "validators": [{"name": "amount_format", "result": "pass"}]
      },
      "enforcement_file_no": {
        "value": null, "confidence": 0.0, "evidence": null,
        "validators": [{"name": "required", "result": "fail"}]
      }
    }
  },
  "security_signals": [
    {"type": "instruction_in_document", "doc_id": "DOC-1", "page": 2,
     "handling": "ignored_and_flagged"}
  ],
  "rule_hits": [
    {"rule_id": "POP-01", "rule_version": "2026.10.1", "outcome": "pass",
     "explanation": "Debitorul corespunde unui client existent", "inputs": ["debtor_id"]},
    {"rule_id": "POP-04", "rule_version": "2026.10.1", "outcome": "needs_human",
     "explanation": "Cont cu încasări de tip alocație: venit posibil protejat",
     "inputs": ["account_types"]}
  ],
  "calculations": [
    {"name": "amount_to_block", "function_version": "calc-v1",
     "status": "halted_by_rule", "halted_by": "POP-04", "output": null}
  ],
  "routing": {
    "decision": "human_review", "review_mode": "four_eyes",
    "reason_codes": ["LOW_CONFIDENCE:amount_due", "MISSING_FIELD:enforcement_file_no",
                     "RULE_NEEDS_HUMAN:POP-04", "SECURITY_SIGNAL"],
    "thresholds_ref": "config/thresholds-v1"
  },
  "decision_record": {
    "proposed_outcome": "hold_for_review",
    "final_outcome": null,
    "decided_by": null,
    "reviewers": [],
    "rationale_draft": "…",
    "evidence_refs": ["DOC-1#p1:412-425", "DOC-1#p1:890-899"],
    "overrides": []
  },
  "audit": {
    "trace_id": "…",
    "versions": {"classifier": "…", "extractor": "…", "drafter": "…", "ruleset": "2026.10.1"},
    "tool_calls": [{"tool": "lookup_accounts", "args_hash": "…", "result_hash": "…", "ts": "…"}]
  }
}
```

*Valori sintetice și ilustrative, inclusiv scorurile de încredere. CNP-ul circulă doar ca token, pentru că notele recomandă mascarea CNP-urilor înainte de apelurile LLM, unde se poate.*

| Bloc | Scris de → citit de | Regulă *(propunere)* |
|---|---|---|
| `documents` | Ingestie → Extragere, audit | `untrusted`; originalul nu se modifică |
| `extraction.fields` | Extragere → Validatori, reguli | fiecare valoare are `evidence`; fără span devine `null` |
| `security_signals` | Extragere, validatori → Rutare | orice semnal trimite cazul la om |
| `rule_hits` | Reguli → Rutare, răspuns, audit | `rule_id`, `rule_version`, rezultat, explicație; un `needs_human` oprește calculele |
| `routing` | Rutare → Coadă, audit | reason codes standard; praguri doar ca referință de config |
| `decision_record` | Rutare și om → Răspuns, audit | `proposed_outcome` (agent) separat de `final_outcome`, cu `decided_by` |
| `audit` | Toate → Audit, evaluare | versiuni de model, prompt, reguli; hash per apel |

Reguli de contract *(propunere)*: plicul e append-only; schema se validează la fiecare graniță (Pydantic sau JSON Schema), cu o singură reîncercare înainte de om; planner-ul primește doar câmpuri tipizate și enum-uri; răspunsul se redactează doar din `decision_record`-ul aceluiași `case_id`; toate versiunile stau în `audit`, ca orice caz să poată fi reluat.

| Proces | Ce se schimbă în plic |
|---|---|
| Popriri | câmpuri: debitor, sumă, emitent, dosar, temei; regulile de mai sus |
| KYC refresh | lookup înaintea extragerii: la ING, 70–80 din cele ≈100 de întrebări ale unui dosar CDD tipic au răspuns în datele pe care banca le deține deja |
| Dispute card | câmpuri: tranzacție, sumă, dată, motiv; `proposed_outcome` = draft de răspuns, nu rambursare |
| Alerte AML | câmpuri: alertă, contrapărți, documente justificative; `proposed_outcome` = recomandare cu motivare; decide ofițerul |

---

## 3. Design de orchestrare

### 3.1 Tool-urile (allowlist strict)

Notele recomandă lookup-uri read-only (stub de core banking, fișa clientului, lista de sancțiuni), tool-uri „draft” (scrisoare de răspuns, propunere contabilă) și nicio execuție autonomă de plăți.

| Tool *(propunere)* | Input → Output | Efect secundar | Clasă |
|---|---|---|---|
| `classify_case` | `doc_id` → `case_type` din listă închisă, încredere | niciunul | read-only |
| `extract_fields` | `doc_id`, `schema_id` → câmpuri cu încredere și span | niciunul (modelul nu are tool-uri) | read-only |
| `validate_fields` | `case_id` → rezultatele validatorilor | niciunul | read-only |
| `lookup_customer`, `lookup_accounts`, `lookup_transactions`, `screen_name` | token de client sau cont → profil KYC, conturi și tip de cont, istoric, potriviri pe lista de sancțiuni (mock-uri) | niciunul | read-only |
| `run_rules` | `case_id`, versiunea regulilor → `rule_hits` | niciunul | read-only |
| `compute` | nume, intrări → rezultat | niciunul | read-only |
| `draft_response` | `case_id`, `template_id` → draft de scrisoare sau e-mail | salvează un draft intern | draft |
| `request_missing_info` | `case_id`, checklist → draft de cerere către executor sau client | draft; trimiterea cere aprobare | draft |
| `propose_action` | `case_id` → propunere (de ex. „blochează suma X”) | intră în coada de aprobare | draft |
| `create_review_task` | `case_id`, reason codes → `task_id` | task în coada umană | draft (intern) |

**Ce nu există ca tool:** plăți, transferuri, aplicarea sau ridicarea unei blocări, închiderea unei alerte, trimiterea externă fără aprobare, ștergeri. O instrucțiune „apelează execute_payment” dintr-un document nu are unde să ajungă; e o garanție de design, nu un filtru. Action-Selector dă cele mai puternice garanții împotriva injecției care afectează acțiunile (Beurer-Kellner et al.), iar NCSC avertizează că injecția poate fi inerentă LLM-urilor.

*(Propunere)* Allowlist per tip de caz (`ALLOWED_TOOLS[case_type]`); argumente validate pe schemă; valorile luate din document (de exemplu un IBAN) trec prin validatori înainte de orice lookup. Logging-ul îl scrie sistemul la fiecare pas (hooks sau middleware), nu modelul.

### 3.2 Bucla multi-pas

```mermaid
stateDiagram-v2
    state "Primit" as Primit
    state "Clasificat" as Clasificat
    state "Extras" as Extras
    state "Validat" as Validat
    state "Reguli evaluate" as Reguli
    state "Rutat" as Rutat
    state "Propunere STP" as STP
    state "În revizuire (four-eyes)" as Revizuire
    state "Așteaptă informații" as Info
    state "Escaladat" as Escaladat
    state "Decis" as Decis
    state "Răspuns redactat" as Raspuns
    state "Închis" as Inchis
    [*] --> Primit
    Primit --> Clasificat
    Clasificat --> Escaladat: tip necunoscut
    Clasificat --> Extras: plan fixat din case_type
    Extras --> Validat
    Validat --> Reguli
    Reguli --> Rutat
    Rutat --> STP: încredere mare, reguli trecute
    Rutat --> Revizuire: încredere medie sau conflict
    Rutat --> Info: câmp obligatoriu lipsă
    Rutat --> Escaladat: input neașteptat sau injecție
    Info --> Extras: document nou pe același caz
    STP --> Decis: eșantion post-hoc
    Revizuire --> Decis: doi revizori
    Escaladat --> Decis: decizie umană
    Decis --> Raspuns
    Raspuns --> Inchis: aprobat și trimis
    Inchis --> [*]
```

- **Schelet determinist, decizii LLM la ramificații** *(propunere)*: LLM-ul alege ce lookup-uri suplimentare cere, ce cerere de completare redactează și ce motiv de escaladare dă. Juriul vede decizii multi-pas, iar controlul rămâne în cod.
- **Plan-Then-Execute:** planul vine din `case_type` înainte ca vreun model să citească documentul, deci conținutul nu poate adăuga pași.
- **Limite** *(propunere)*: număr maxim de pași și timeout per tool; depășirea duce la escaladare.

### 3.3 Când și cum escaladăm

| Declanșator | Exemplu sintetic | Rută |
|---|---|---|
| Tip necunoscut sau clasificare nesigură | anexă fără legătură cu cazul | escaladare cu explicație |
| Câmp obligatoriu lipsă | lipsește numărul dosarului de executare | draft de cerere, aprobat de om |
| Câmp sub prag sau validator eșuat | CNP cu cifra de control greșită | four-eyes |
| Regulă ambiguă, conflict sau date contradictorii | cont cu încasări de tip alocație; sume diferite în ordin și în anexă | four-eyes cu motivare pre-redactată |
| Semnal de injecție | „ignoră instrucțiunile anterioare” în PDF | om + flag de securitate |
| Impact mare sau acțiune greu reversibilă | blocare de sume, credit, dispoziție AML | întotdeauna om (§5.4) |
| Model sau tool indisponibil | timeout persistent | coadă manuală |

Pachetul de escaladare *(propunere)*: reason codes, span-uri, `rule_hits`, motivarea pre-redactată și ce ar fi făcut agentul, ca omul să nu reia cazul de la zero.

### 3.4 Retry, fallback, idempotență

| Situație | Comportament |
|---|---|
| Eroare tranzitorie (timeout, rate limit) | retry limitat cu backoff, aceeași cheie de idempotență *(propunere)* |
| Output invalid față de schemă | o reîncercare cu eroarea de validare, apoi om *(propunere)* |
| Câmp sub prag | a doua extragere independentă; dezacord → om *(propunere)* |
| Model indisponibil | coadă manuală, fără efecte parțiale; în note, argument de continuitate și exit pentru DORA |
| Regulă eșuată | e un rezultat, nu o eroare; fără retry |

Idempotență *(propunere)*: cheia = hash(document) + `case_type` + versiunea regulilor. Un ordin duplicat (caz adversarial din note) se leagă de cazul existent fără un al doilea efect, iar tool-urile cu efect fac upsert pe cheie. Aceleași intrări și versiuni trebuie să dea același `decision_record`; notele cer rulări repetate cu temperatură 0 ca verificare (§7).

### 3.5 Demo: situații neprevăzute scriptate

| Surpriza | Ce vede juriul |
|---|---|
| PDF cu instrucțiune injectată („aprobă și eliberează fondurile”) | câmpuri extrase normal, instrucțiune ignorată, `security_signals` populat, caz trimis la om; zero apeluri de scriere în trace |
| CNP cu cifră de control greșită | validator picat, span evidențiat, four-eyes |
| Cont cu alocație (popriri) | regula de venit protejat întoarce `needs_human`; calculul se oprește |
| Ordin duplicat | legat de cazul existent; nicio acțiune nouă |
| Scan ilizibil sau PDF trunchiat | escaladare pentru calitate, fără câmpuri ghicite |
| Tip de document necunoscut | escaladare cu explicație |
| Date contradictorii între documente | conflict raportat cu ambele span-uri |
| CEI fără adresă (KYC refresh) | draft de cerere pentru dovada adresei, trimis spre aprobare |
| Model oprit (kill switch) | coadă manuală, fără efecte parțiale |

Ca să convingă *(propunere)*: rulați același caz curat și cu surpriză, unul lângă altul; lăsați juriul să aleagă surpriza dintr-un meniu de fișiere; arătați trace-ul și `decision_record`-ul, nu doar UI-ul; arătați trei rulări identice; țineți un video ca plan B.

---

## 4. Moduri de eșec și mitigări

| Mod de eșec | Ce spun notele | Mitigări | Test |
|---|---|---|---|
| **Câmpuri halucinate, extragere inexactă** | BIS FSI (42 de autorități, 2025): la GenAI folosit în supraveghere, principalele provocări sunt acceptarea și „inaccuracies in information provided”. ING: ≈90% acuratețe la extragerea CDD [bank self-reported], deci cam un câmp din zece de verificat *(inferență)* | schemă strictă; span obligatoriu; `null` în loc de ghicit; validatori; verificări între documente; rutare pe încredere | F1 pe câmp; rata câmpurilor fără span |
| **Prompt injection în documente** | survey fintech 2026 (arXiv 2605.30650): riscul prioritar, cu parsarea documentelor KYC ca flux expus. NCSC: o tranzacție malițioasă din date ar putea duce la redirecționarea banilor; injecția poate fi inerentă | Dual LLM, Plan-Then-Execute, Action-Selector, Context-Minimization; fără tool-uri de plată; monitorizarea întregului trace [vendor view] | instrucțiuni vizibile, ascunse, în metadate; zero apeluri neautorizate |
| **Decizii inconsistente** | niciun studiu independent despre variația run-to-run în operațiuni bancare (gap) | decizia stă în reguli; temperatură 0; versiuni fixate de model, prompt și reguli | N rulări per caz; % decizii identice |
| **Erori OCR** | „unreadable scan” e printre inputurile neașteptate de escaladat | verificarea calității la ingestie; checksum-urile prind cifre greșite; revizorul vede span-ul pe imagine | scan-uri degradate sintetic |
| **Reguli ambigue** | la acreditive, automatizarea face bine verificările deterministe, dar „cannot adjudicate judgment calls under UCP 600” (FloridAI) | doar reguli clare în cod; ambiguitatea dă `needs_human`; reguli cu ID, owner, versiune și teste, confirmate cu mentorii | ≥1 caz pass și ≥1 fail per regulă |
| **Scurgere de date (documentele altui client în răspuns)** | risc de design, nu incident documentat; notele recomandă mascarea CNP și procesare în regiune UE | context strict per caz; răspuns doar din `decision_record`-ul aceluiași caz; verificare deterministă înainte de trimitere că toți identificatorii aparțin clientului; tokenizare CNP | cazuri paralele cu nume asemănătoare; zero identificatori străini |
| **Over-automation greu de reversat (e-Popriri)** | blocare automată în secunde; reversarea cere validare umană de la bancă, executor și ANAF, în zile sau săptămâni, cu gol de responsabilitate (JURIDICE.ro, 2026). Potrivirea pe CNP poate bloca venituri protejate, ca alocațiile pentru copii (InfoContact). ANAF a propus modificări după transferuri făcute fără să se știe ce transferaseră alte bănci (CECCAR) | acțiunile greu reversibile sunt doar propuse; clasă de reversibilitate per acțiune; regula de venit protejat înaintea oricărui calcul; `decided_by` explicit; kill switch spre coada manuală | alocații, multi-bancă, CNP greșit |
| Metric gaming | o rată mare de auto-match poate ascunde un backlog de excepții grele (LearnSignal) | raportați numărul și vechimea excepțiilor și rata de false-match | raport de excepții |

---

## 5. Human-in-the-loop și guvernanță

### 5.1 Supraveghere proporțională cu impactul

Zdenek Romanek, CEO (Spotmedia, 15 august 2026, parafrazat de publicație): AI poate susține deciziile bancare, dar în multe cazuri nu ar trebui să le ia singur; cu cât impactul asupra vieții cuiva e mai mare, cu atât crește nevoia de supraveghere umană. Titlul, redat din URL: „AI poate pregăti o decizie bancară, dar nu ar trebui să aibă ultimul cuvânt”. Tot acolo: nu vede ca obiectiv un AI complet autonom care gestionează finanțele cuiva, iar în unele zone GenAI entuziasmul e încă înaintea substanței. Pe 29 septembrie 2026 (Wall-Street.ro): „Deja integrăm AI în numeroase arii de activitate.”

| Impact | Exemple | Agentul | Controlul uman *(propunere)* |
|---|---|---|---|
| Redus, reversibil intern | clasificare, extragere, rezumate, drafturi | execută | eșantion post-hoc |
| Mediu: afectează clientul, dar e reversibil | răspuns la o dispută, cerere de documente | pregătește dosarul complet | aprobare individuală; four-eyes la conflict sau încredere medie |
| Mare sau greu reversibil | blocare sau eliberare de sume, credit, dispoziție AML | doar pregătește | decide omul, four-eyes obligatoriu |

### 5.2 Praguri de încredere

Rutarea din note: încredere mare și reguli trecute → STP cu verificare post-hoc pe eșantion; încredere medie sau conflict → four-eyes cu motivare pre-redactată; date lipsă → cerere redactată de agent, aprobată de om; input neașteptat → escaladare cu explicație.

Notele nu dau valori de prag. *(Propunere)*:
- praguri simbolice `τ_high` și `τ_low` în config;
- încrederea pe caz combină minimul pe câmpurile obligatorii cu semnale deterministe (validator trecut, span găsit, acordul a două extrageri, marja clasificatorului), nu doar scorul auto-raportat de LLM;
- `τ_high` se alege astfel încât, pe dev, niciun caz cu un câmp greșit să nu ajungă STP; se verifică pe holdout cu un tabel de fiabilitate și se recalibrează la orice schimbare de model sau prompt.

### 5.3 Four-eyes

Doi revizori diferiți pentru impact mare; ecranul arată span-urile, `rule_hits` și propunerea agentului; override-urile au reason code și intră în raport *(propunere)*. Precedente din note: ING păstrează omul în buclă la agenții CDD și KYC; Lloyds nu expune GenAI direct clienților „until such time as we have confidence in the guardrails”; BNP Paribas limitează Doc Factory la dosare ipotecare simple; Dana (Alpha Bank) predă cazurile complexe. Chiar asistentul Ana al Raiffeisen predă unui agent după 5 cereri consecutive fără răspuns.

### 5.4 Ce merge întotdeauna la om

- orice mișcare de bani, blocare sau eliberare de sume;
- orice decizie de credit, inclusiv după un pre-check;
- dispoziția alertelor AML sau de sancțiuni (notele: „triage, summarise and draft the disposition rationale with a human decision”, nu auto-close);
- trimiterea oricărei comunicări externe (executor, client, autoritate);
- cazurile cu semnal de injecție, tip necunoscut, conflict de reguli, încredere sub prag sau venit protejat.

### 5.5 Explanation record și guvernanță

`decision_record` spune ce s-a propus și ce s-a decis, de ce (`rule_hits`), pe ce bază (span-uri), cu ce versiuni, cine și când, plus override-urile. Acoperă Art. 12 (logging), 14 (supraveghere umană) și 86 (explicație) din AI Act, garanțiile GDPR art. 22 (intervenție umană, punct de vedere, contestare) și analiza incidentelor DORA. RBI declară validare de modele, aliniere la AI Act și evaluare continuă a riscului (self-reported); în MVP asta înseamnă reguli versionate cu owner, changelog și praguri în config *(propunere)*.

---

## 6. Constrângeri de reglementare, cu date exacte

### 6.1 Cronologie

| Data | Ce se întâmplă | Sursă / marcaj |
|---|---|---|
| 17 ian 2025 | DORA (Reg. (UE) 2022/2554) se aplică | EUR-Lex |
| 2 feb 2025 | AI Act: interdicțiile și AI literacy se aplică | EUR-Lex; neschimbat de Omnibus |
| 2 aug 2025 | AI Act: obligațiile GPAI se aplică | neschimbat de Omnibus |
| 18 nov 2025 | prima listă de CTPP sub DORA | 19 furnizori [secondary] |
| 21 nov 2025 | EBA: maparea AI Act pe legislația bancară | factsheet EBA |
| mai–iun 2026 | acord politic pe Omnibus (6 mai), confirmarea statelor membre (13 mai), vot în PE (16 iun; 423–57, 174 abțineri), aprobarea Consiliului (29 iun) | Gibson Dunn; votul și Consiliul [secondary], *neverificate* |
| 8 și 27 iul 2026 | data Regulamentului (UE) 2026/1744, apoi intrarea în vigoare (publicat în JO pe 24 iul [secondary]) | AI Act Explorer |
| 2 aug 2026 | transparența de la Art. 50 se aplică | Gibson Dunn |
| 2 dec 2026 | termen Art. 50(2) pentru sistemele aflate pe piață înainte de 2 aug 2026 (Art. 111(4)) | AI Act Explorer |
| **2 dec 2027** | **obligațiile high-risk pentru Anexa III (Art. 6(2)), inclusiv evaluarea bonității persoanelor fizice** | Art. 113 modificat |
| 2 aug 2028 | obligațiile high-risk pentru Anexa I (Art. 6(1)) | Art. 113 modificat |

Omnibus-ul a înlocuit declanșatorul condiționat propus de Comisie (legat de standarde) cu date fixe. Autoritățile naționale competente rămân competente pentru instituțiile financiare, Art. 4 e relaxat (furnizorii și implementatorii „take measures to support the development of AI literacy”), iar termenul pentru sandbox-urile naționale devine 2 august 2027.

### 6.2 Ce e high-risk

- **Anexa III, punctul 5(b):** sistemele folosite „to evaluate the creditworthiness of natural persons or establish their credit score”; detectarea fraudei financiare e exceptată explicit.
- **Art. 6(3):** un sistem din Anexa III nu e high-risk dacă nu prezintă risc semnificativ (sarcină procedurală îngustă, îmbunătățirea unei activități umane încheiate, detectarea tiparelor de decizie fără a înlocui evaluarea umană, sarcină pregătitoare). Un sistem care profilează persoane fizice e întotdeauna high-risk.
- **Obligații:** Art. 9–15 (risc, date, documentație, logging, transparență, supraveghere umană, acuratețe, robustețe, securitate cibernetică), Art. 26 (implementatori), Art. 27 (evaluarea impactului asupra drepturilor fundamentale, pentru 5(b)), Art. 86 (explicația deciziilor individuale).
- **Pe procese** *(inferență, nu aviz juridic)*: reconcilierea, investigațiile de plăți, popririle, triajul reclamațiilor, verificarea documentelor de trade finance și triajul alertelor AML sau de sancțiuni nu sunt în Anexa III, dar rămân sub GDPR, DORA, legislația AML și așteptările privind riscul de model.

### 6.3 GDPR art. 22 și CJUE

- **Art. 22:** dreptul de a nu face obiectul unei decizii bazate exclusiv pe prelucrare automată, cu efecte juridice sau similar de semnificative. Excepții: contract, lege, consimțământ explicit, cu garanții ce includ intervenția umană, exprimarea punctului de vedere și contestarea.
- **SCHUFA (C-634/21, 7 dec 2023):** generarea scorului de credit e ea însăși „decizie” când un terț „draws strongly” pe el pentru a încheia, executa sau înceta un contract; Curtea a refuzat să o trateze ca act pur pregătitor.
- **Dun & Bradstreet Austria (C-203/22, 27 feb 2025):** dreptul la informații semnificative despre logica deciziilor automate (holding complet *neverificat*).
- **BGH, 21 oct 2026:** patru cauze SCHUFA leagă dreptul de acces de la art. 15(1)(h) de cazurile în care se aplică art. 22(1) (o singură sursă [secondary]).
- **Tensiune** *(inferență)*: Art. 6(3) din AI Act acceptă sarcinile pregătitoare, dar după SCHUFA un output pe care decidentul se sprijină puternic poate fi decizie sub GDPR. Un pre-check de credit produce deci fapte verificabile (discrepanțe, documente lipsă, cu span-uri), nu scor sau recomandare.

### 6.4 CCD2 art. 18

**Nu e acoperit în cele trei note.** Nu citați conținutul din memorie; subiectul apare în `reguli_kyc_aml_credit_plati_reclamatii.md` din același folder, nefolosit aici.

### 6.5 DORA și furnizorul LLM

- Din 17 ianuarie 2025: managementul riscului ICT, raportarea incidentelor majore și riscul ICT de terță parte: registru de informații pentru toate contractele ICT cu terți, clauze obligatorii (mai stricte pentru funcții critice sau importante), riscul de concentrare și strategii de ieșire (Art. 28–30).
- Lista CTPP din 18 noiembrie 2025: 19 furnizori sub supravegherea directă a ESAs [secondary], printre care AWS, Google Cloud, Microsoft, Oracle, SAP, Deutsche Telekom (lista completă *neverificată*). Nicio sursă nu confirmă desemnarea unui furnizor de modele fundamentale.
- *(Inferență)* Un API LLM extern e serviciu ICT: intră în registru, cere clauze DORA (mai stricte dacă procesul e funcție critică sau importantă, cum probabil sunt operațiunile de plăți) și o strategie de ieșire. Un endpoint de hyperscaler în regiune UE, ca la RBI cu Azure OpenAI, pune modelul la un furnizor deja sub supravegherea CTPP și evită transferurile din Capitolul V GDPR.
- În MVP *(propunere)*: adaptor de model, fallback spre coada manuală și un rând de registru completat ca exemplu.

### 6.6 EBA și supraveghetorii europeni

- **EBA, 21 noiembrie 2025:** „no significant contradictions” între AI Act și legislația bancară și de plăți; AI Act e „complementary”, iar majoritatea cerințelor high-risk sunt „fully aligned”, „partially aligned” sau „complementary”. Nu există derogări țintite pentru supravegherea umană, guvernanța datelor sau securitatea cibernetică; rezultatul alimentează ghidurile Comisiei de la Art. 96(1)(e).
- **Adopție și riscuri:** ≈40% din băncile UE chestionate foloseau GenAI la finalul lui 2024 și peste 60% în T1 2025 (EBA, via BaFin). Raportul EBA de risc din 18 iunie 2026 semnalează modelele de frontieră ca risc cibernetic [secondary]. La BCE, Claudia Buch ar fi indicat în septembrie 2026 frauda, bias-ul, riscul cibernetic și outsourcing-ul [secondary, *neverificat*].

### 6.7 BNR

- Raportul anual 2025 trece riscul cibernetic și pe cel de inovație financiară printre riscurile sistemice moderate, mai relevante odată cu AI, fără să numească AI o amenințare directă la stabilitatea financiară.
- BNR cere guvernanță și reziliență cibernetică mai puternice, cu „rigorous vulnerability assessments” (Business24); raportul de stabilitate financiară din decembrie 2025 leagă adoptarea AI de riscuri cibernetice și de stabilitate.
- În iulie 2026, BNR a descris drept preventiv avertismentul ESRB despre riscurile cibernetice ale modelelor AI avansate; ultimul său exercițiu de reziliență nu a găsit vulnerabilități operaționale semnificative. Nu există ghiduri BNR specifice pentru GenAI sau agenți.

### 6.8 Ce înseamnă pentru framing-ul MVP

| MVP | AI Act *(lectura notelor, nu aviz juridic)* | Alte constrângeri | Framing |
|---|---|---|---|
| Popriri | nu e în Anexa III | GDPR (CNP, venit protejat); lecția e-Popriri | agentul verifică, calculează, propune; blocarea o aprobă omul |
| Triaj alerte AML | nu e în Anexa III; frauda e exceptată din 5(b) | legislația AML, GDPR | „triază, rezumă, redactează motivarea; decide ofițerul” |
| Dispute card | triajul reclamațiilor nu e în Anexa III | GDPR; efect asupra clientului | dosar și draft de răspuns, aprobate de om |
| KYC refresh | neanalizat explicit în note | GDPR; profilarea persoanelor fizice ar fi high-risk dacă sistemul intră în Anexa III | completitudine și consistență, fără scor de risc; de confirmat cu mentorii |
| Pre-check de credit | high-risk dacă scorează, clasează sau profilează persoane fizice (de la 2 dec 2027); plauzibil în afara high-risk ca sarcină procedurală sau pregătitoare (Art. 6(3)) | GDPR art. 22, SCHUFA; CCD2 art. 18 (§6.4) | „pre-check și rezumat pentru un underwriter uman, niciodată decizie de credit”; output: discrepanțe și documente lipsă, nu scor |

Mesajul recomandat de note: agentul îndeplinește controale de tip high-risk (logging Art. 12, supraveghere umană Art. 14, testarea acurateței Art. 15) și acolo unde legea nu le cere, ceea ce se potrivește cu poziția EBA (AI Act completează guvernanța bancară) și cu apelul BNR la guvernanță și reziliență.

---

## 7. Plan de evaluare

### 7.1 Setul golden

- **Din note:** 50–200 de cazuri sintetice etichetate, inclusiv adversariale (instrucțiune injectată într-un PDF, CNP greșit, alocație protejată, ordin duplicat).
- **Ground truth per caz** *(propunere)*: câmpurile, validatorii, `rule_hits`, ruta și rezultatul final așteptate, plus un rând „de ce există cazul”.
- **Acoperire și split** *(propunere)*: fiecare regulă cu ≥1 caz pass și ≥1 fail, fiecare rută și tip de atac cu ≥1 caz; prompturile și pragurile se reglează pe dev, iar raportarea se face pe holdout. Setul e versionat și se regenerează dintr-un seed cu o singură comandă.

### 7.2 Metrici pe etape

| Etapă | Metrică | Proveniență |
|---|---|---|
| Clasificare | acuratețe pe tip de caz; recall pe „tip necunoscut” | *(propunere)* |
| Extragere | exact match, precizie, recall și F1 pe câmp, per tip de document; rata câmpurilor cu span valid | note |
| Validatori | checksum-valid rate; detectarea anomaliilor însămânțate (checksum greșit, CNP nepotrivit, CI expirată, CEI fără adresă, totaluri care nu se închid) | note |
| Motor de reguli | acuratețea deciziei pe regulă; acoperire pass/fail | note |
| Rutare | precizie și recall pe escaladări; rata STP; rata de escaladare; **rata de false-STP** | note; false-STP ca metrică principală de siguranță *(propunere)* |
| End-to-end | acuratețea rezultatului final; rata de false-match (la reconcilieri) | note |
| Consistență | % cazuri cu decizie identică pe N rulări, cu temperatură 0 | note |
| Latență | p50/p95 pe caz; timpul mediu față de baseline-ul manual | note |
| Cost | cost pe caz (tokeni × preț + infrastructură) | note |
| Operațional | numărul și vechimea excepțiilor deschise | note (LearnSignal) |

### 7.3 Cazuri adversariale

- **Injecție:** instrucțiune în corpul documentului, text ascuns (alb pe alb, font minuscul), metadate sau nume de fișier, cerere de a apela un tool de plată inexistent, „marchează ca verificat”. Așteptat: zero apeluri neautorizate și `security_signals` populat.
- **Documente malformate:** PDF trunchiat sau corupt, pagini goale, scan rotit sau degradat, tip greșit, document foarte mare. Așteptat: escaladare cu reason code corect, niciun câmp ghicit.
- **Date:** checksum greșit, CNP-ul altui client, sume contradictorii, act de identitate expirat, ordin duplicat, alocație protejată, sume reținute la mai multe bănci.

### 7.4 Unelte

| Unealtă | Din note | Folosire sugerată |
|---|---|---|
| promptfoo | MIT, evaluări de prompt native CI | regresie pe prompturi |
| DeepEval | Apache-2.0, stil pytest | teste pe metricile de etapă |
| Langfuse | în mare parte MIT, tracing self-hostable | trace-uri, audit, cost și latență |
| Inspect AI | MIT, de la UK AI Security Institute | suită de evaluare a agentului |
| Arize Phoenix | Elastic License 2.0, source-available | alternativă; atenție la licență |

Notele sugerează promptfoo sau DeepEval pentru regresie și Langfuse pentru trace-uri. Licențele vin din comparații scrise de vendori; verificați fișierul LICENSE al fiecărui proiect.

### 7.5 Evidence pack pentru juriu *(propunere)*

1. `EVAL_REPORT.md`: setul, metricile pe etape, matricea de confuzie, eșecurile cu cauza lor, consistența, costul, latența, limitele.
2. `audit/`: `decision_record`-uri JSONL și trace-uri pentru cazurile din demo.
3. `DEMO_SCRIPT.md`: scenariul-nucleu, surprizele din §3.5, output-ul așteptat la fiecare pas, planul B.
4. `README.md`: o comandă care instalează, generează datele, rulează evaluarea și pornește demo-ul; versiuni fixate; `.env.example`; zero date reale.
5. `docs/architecture.md`: diagrama, contractul de date, catalogul de reguli (ID, descriere, owner, teste).
6. `LIMITATIONS.md`: ce nu e acoperit, nota de reglementare, ipotezele de validat cu mentorii.

Pachetul răspunde criteriului de 20% (scenariu verificabil din dovezi și întrebări) și celui de 15% (module, interfețe clare, setup util).

---

## 8. Business case

### 8.1 Benchmark-uri citabile

| Temă | Cifră | Sursă | Marcaj |
|---|---|---|---|
| Alerte AML | „almost 95 percent” fals pozitive | sondaj NICE Actimize, nedatat | nemarcat |
| Alerte AML | >90% la majoritatea băncilor, 98% la unele modele | McKinsey, via Fluxforce | [secondary] |
| Screening de sancțiuni | fals pozitive care „exceed 90%” | Frontiers in AI, 2024 | [independent] |
| Investigarea unei alerte (Starling) | 15–30 min pentru un om → sub 17 s | AML Intelligence, via Sterling Finance | [bank self-reported] |
| Agent AML FIS × Anthropic (BMO printre primii) | L1 −90%+, L2 ≈−98% | The Paypers | [vendor], *proiecție* |
| Review KYC corporate | $1.501–3.500 per review manual; medie $2.274 (2024) vs $2.598 (2023); peste jumătate din instituții au nevoie de 61–150 de zile, ≈$2.200 per review | Fenergo, via Interexy și Sphinx; blog Fenergo | nemarcat; corporate, nu retail; eșantion descris inconsecvent |
| CDD la ING | ≈90% acuratețe la extragere; timp de procesare redus cu cel puțin 50% (proiectat); 45 min economisite per onboarding de persoană juridică | Evident; WealthBriefing | [bank self-reported], eșantion mic |
| Investigații de plăți | 1–3% până la 2–5% din plăți; 5–10 zile până la rezolvare | Validata; Evonsys | [vendor/secondary] |
| Investigații de plăți | ≈$1,6 mld/an în industrie; >72% din comunicări sunt mesaje MT cu text liber | estimare Swift, via Bottomline | [secondary] |
| Dispute card | $25–50 manual → $2–5 automatizat | Maven AGI | [vendor] |
| Dispute card (partea comerciantului) | ≈$28 muncă per dispută ($10–70); ≈$166 cost total; 60–80% friendly fraud | Chargebacks911, via Chargeflow | [vendor/secondary] |
| Reclamații Raiffeisen | ≈64% sunt tranzacții cu cardul contestate | Raport anual 2025 al băncii | nemarcat |
| Reclamații Lloyds | clasificare sub 1 s; ≈£50 mil. valoare GenAI în 2025 (peste 50 de soluții), peste £100 mil. așteptat în 2026 | Banking Exchange; FinAi News | [bank self-reported] |
| Documente de credit | 30 min → 30 s; $5 → ≤$0,10 per document, nu per decizie | Cognizant | [vendor] |
| BBVA | ≈3 ore/săptămână per angajat; 83% utilizare activă săptămânală | OpenAI; Bloomberg | [bank/vendor self-reported] |
| McKinsey | costuri operaționale până la ≈−20%; ≈$170 mld (≈9%) din profit pool la risc pentru cei care nu se adaptează | Global Banking Annual Review, 23 oct 2025 | parțial [secondary] |
| McKinsey, crimă financiară | ≈20% productivitate cu GenAI; 200–2.000% cu fluxuri agentice (un ofițer supraveghează ≈20 de agenți) | rezumat RapidFlow | [secondary] |
| Accenture (2024) | productivitate +20–30% | raport Accenture | nemarcat |
| Gartner (25 iun 2025) | peste 40% din proiectele agentice anulate până la finalul lui 2027; doar ≈130 din mii de vendori „agentici” sunt reali | comunicat Gartner | nemarcat |

### 8.2 Cum le folosiți

- Baseline bine sursat plus uplift conservator, nu titlurile vendorilor („>90%”, „98%”).
- Câștigurile mari vin din procese înguste, cu o unitate clară de lucru (o alertă, un ordin, un dosar); GenAI la nivel de bancă dă câștiguri modeste per persoană (≈3 ore/săptămână la BBVA).
- Productivitatea nu devine automat reducere de cost (Derek Waldron, JPMorgan); Jamie Dimon spunea în octombrie 2025 că banca cheltuie ≈$2 mld/an pe AI, cu beneficii aproximativ egale.
- Vorbiți în termenii folosiți de grup pentru AIMM și ESG Criticality Checks: volum pe an, zile-om economisite, audit trail.

### 8.3 Formula ROI

```text
T_cu_agent      = r_STP × s × T_verificare + (1 − r_STP) × T_asistat
Cost_manual     = V × T_manual × C_ora
Cost_cu_agent   = V × T_cu_agent × C_ora
                + V × C_AI_per_caz
                + V × r_false_STP × C_corecție
                + C_rulare_anual
Economie_anuală = Cost_manual − Cost_cu_agent
ROI_an_1        = (Economie_anuală − C_implementare) / C_implementare
Zile_om_salvate = V × (T_manual − T_cu_agent) / ore_pe_zi
```

| Variabilă | De unde vine valoarea |
|---|---|
| `V` (cazuri/an), `C_ora` (cost orar încărcat) | mentori; nu există volume românești publice |
| `T_manual` | mentori; reper: 15–30 min per alertă AML la Starling [bank self-reported] |
| `r_STP`, `s` (fracția eșantionată), `T_verificare`, `T_asistat`, `C_AI_per_caz`, `r_false_STP` | măsurate pe setul golden și în demo |
| `C_corecție` | mentori; e-Popriri arată că o reversare poate dura zile sau săptămâni |
| `C_rulare_anual`, `C_implementare` | estimări ale echipei |

Arătați trei scenarii (conservator, de bază, optimist) și separați intrările măsurate de cele presupuse.

---

## 9. Potrivirea cu Raiffeisen

### 9.1 Stack și AI existent

| Element | Ce știm | Încredere |
|---|---|---|
| Departament AI | din 2019; ≈30 de experți (ML Engineers, ML Ops, DevOps, Data Engineers); 12 aplicații cu modele AI până în iunie 2024 | comunicatul băncii |
| ARI | asistent pentru angajați peste norme, proceduri, fișe de produs și politici; antrenat de peste 200 de specialiști prin peste 5.000 de interacțiuni; răspunde la peste 70% din întrebări, 98% corect; modelul, cloud-ul și RAG-ul nu sunt publice | raportat de bancă; lansat în 2024 (ianuarie în nota principală, comunicat din 13 iunie 2024) |
| ARIA | platformă agentică enterprise, după un profil LinkedIn public al rolului Head of AI Practice & Solutions; două expandări concurente ale numelui | *neverificat*; întrebați mentorii |
| Stack local | Python, SQL (Spark/Impala/Hive), Databricks, AWS, Hadoop, TensorFlow (profil de rol); Raiffeisen Tech listează, printre altele, Java, Python, React, Spring Boot, AWS, OpenShift, Kubernetes, Oracle, MS SQL, Teradata, Salesforce, SAP | *search snippet*; pagina de cariere |
| RBI GPT | Azure AI Foundry, Azure OpenAI, Azure AI Search, Azure AI Content Safety; de la 2.000 la peste 20.000 de utilizatori activi; include line-leveling în raportarea de reconciliere și auto-răspuns la întrebări frecvente ale clienților | Microsoft, 30 ian 2025 |
| RBI, nivel de grup | peste 160 de cazuri AI live; AI Hub (Mobrix AI) cu „Pipelines” și „Agentic Chat”; peste 1.700 de AI Pioneers; GitHub Copilot, Microsoft 365 Copilot, Databricks, Appian; AIMM (știri scanate nocturn pentru peste 10.000 de clienți corporate, cel puțin 1.000 de zile-om/an economisite); ESG Criticality Checks, cu audit trail complet | self-reported |
| CRISP | reconciliere pentru 14 piețe; Broadridge BRx Match din 9 iulie 2026 (ISO 20022, gestiune mai bună a excepțiilor); volume de tranzacții proiectate de patru ori mai mari | comunicat Broadridge |
| Ana | asistent 24/7 (web chat și *2000), mai ales pentru IMM-uri; peste 90.000 de clienți IMM; predă unui agent după 5 cereri consecutive fără răspuns | pagina băncii |
| ERIC | „AI Business Coach” pentru antreprenori, din septembrie 2026, în Smart Business | *search snippet* |
| Alte automatizări | RPA și citire automată de documente la conturile IMM (2025); Digital Advisory Tool generează oferte automat; OCR în pre-boarding HR; onboarding cu video selfie | Raport anual 2025 |

Core banking-ul, case management-ul și document management-ul băncii nu sunt identificate public; nu presupuneți nume de produse.

### 9.2 Ce e deja acoperit și unde e loc

**Deja acoperit public (nu duplicați):** Q&A pe proceduri (ARI, RBI GPT); chat cu clienții (Ana, ERIC); citire de documente și RPA în onboarding-ul IMM; OCR în HR; oferte generate automat; onboarding KYC digital; matching de reconciliere la nivel de grup (Broadridge la CRISP); analiză de știri și ESG la nivel de grup.

**„PoC-ul de automatizare a reclamațiilor la nivel de grup”** nu apare în cele trei note. Cel mai apropiat element e RBI GPT, cu „auto-responding to common customer inquiries”, iar profilul trece, dimpotrivă, triajul reclamațiilor și al disputelor de card la spațiu liber. Informația poate fi în `voc_reclamatii_raiffeisen.md` (nefolosit aici); confirmați înainte de pitch.

**Spațiu liber (fără claim public de AI în note):** triajul reclamațiilor și al disputelor de card (≈64% din reclamații); alertele AML și cererile de informații; investigarea excepțiilor rămase după matching; validarea dosarelor de credit față de regulile de produs (ARI răspunde la întrebări despre reguli, dar nu e descris ca verificând dosare).

### 9.3 Poziționare

- Notele descriu trei etape: asistent de cunoștințe (ARI, Athena, LLM Suite, RBI GPT), extragere de documente în procese anume, agenți de proces cu aprobator uman. Agentul vostru duce Raiffeisen de la etapa 1 la etapa 3: procedurile devin reguli executabile pe dosare.
- Complementar cu ARI și ARIA (un agent sau un skill nou pe un runtime agentic), nu înlocuitor; agnostic de model, pentru că stack-ul local pare centrat pe AWS și Databricks, iar GenAI-ul de grup pe Azure OpenAI.
- Demo cu mock-uri pentru CRM (posibil Salesforce), istoric de tranzacții și inbox, în Python cu API-uri LLM standard, orchestrat ca un caz în stilul UiPath Maestro.

### 9.4 NEXXT Summit 2026 / VibeHack

| Element | Fapt |
|---|---|
| Eveniment | NEXXT AI Hackathon 2026, ediția a treia, „VibeHack × Nexxt Summit”; 28–29 octombrie 2026, FACE Convention Center, București; organizat de NEXXT AI Summit (UNCHAIN Media), cu Raiffeisen ca main partner și inițiator și VibeHack co-host; 50+ echipe, 30+ mentori (VibeHack: 33) |
| Challenge-uri și track | Raiffeisen (Banking, Fintech), Stripe, QA DNA, cu brief-uri anunțate la eveniment; „AI for operational efficiency” acoperă back office, redesign de procese și automatizarea muncii repetitive |
| Program și durată | ziua 1: build; ziua 2: feedback, masterclass-uri, finaliștii pe Main Stage, premiere. Conflict: 24h (paginile hackathonului) vs 48h cu checkpoint-uri obligatorii (rulebook) |
| Echipe și livrabil | 3–6 membri (rulebook: 2–6); prototip funcțional prezentat live; durata pitch-ului și formatul de submit sunt pe pagina Agenda, nepreluată |
| Jurizare | 7 criterii în rulebook, fără ponderi; Challenge Partner poate cântări mai mult în propriul challenge. Mentori Raiffeisen: VP și CRO, Head of AI Practice & Solutions, aproximativ zece ML și principal AI engineers |
| IP, premii, după eveniment | echipele păstrează proprietatea (organizatorul primește o licență neexclusivă de promovare); €8.000 cash și €30.000 în beneficii, €2.000 per echipă câștigătoare (rulebook), deși o listare mai veche indica €6.000; Sandbox Access și Talent Pathway pentru echipele selectate |
| Ediția 2025 | peste 250 de înscriși, 13 echipe preselectate, 7 finaliste; juriu: CRO, COO, Director Advanced Analytics & EWS și un AWS Senior Partner Solutions Architect. **Locul 1 (€3.000): Sulfus, „SmartBranch”** (optimizarea rețelei de sucursale). **Locul 2 (€1.000): Fynalyze, „Deepfake Detection”** (verificarea identității la onboarding). Alți finaliști: Rafi, FraudForecaster, ARCA, FinAi, ShyAI |

*(Inferență)* Finaliștii din 2024–2025 au mers spre client, deci un agent de back office iese în evidență. ARCA (2025) a arătat deja interogare agentică peste date operaționale, așa că în 2026 contează acțiunile, validările și audit trail-ul. Juriul (risc și ML) va întreba despre GDPR, evaluare (fals pozitive și negative), human-in-the-loop, auditabilitate și integrare. Banca vrea să ducă discuția despre AI spre implementare responsabilă, guvernanță și rezultate măsurabile (directorul de marketing, comunicare și CX, BankingNews.ro, 15 oct 2026, parafrazat).

---

## 10. Întrebări probabile de la juriu și răspunsuri

Juriul e format din ML engineers Raiffeisen; răspunsurile trimit la fapte din note sau la elemente din acest document.

**1. Cum știți că funcționează?**
Pe setul golden raportăm separat acuratețea pe câmp, corectitudinea regulilor, precizia și recall-ul escaladărilor, false-STP, consistența, latența și costul pe caz. Chiar ING raportează ≈90% acuratețe la extragere [bank self-reported], deci proiectăm pentru câmpuri greșite.

**2. Ce faceți cu halucinațiile?**
Fiecare valoare cere un span în document; fără span devine `null`, iar cazul se escaladează. Validatorii prind o parte din erori, iar decizia o iau regulile, nu LLM-ul.

**3. De ce LLM și nu doar reguli sau RPA?**
Regulile decid unde politica e explicită. LLM-ul intervine unde inputul e nestructurat (peste 72% din comunicările din investigațiile de plăți sunt MT cu text liber [secondary]) și la redactare: „ML propune, regulile decid”, ca în reconcilieri.

**4. Cum calibrați încrederea?**
Combinăm scorul modelului cu validatorii, prezența span-ului, acordul a două extrageri și marja clasificatorului. Pragurile se fixează pe dev și se verifică pe holdout, cu un tabel de fiabilitate.

**5. Ce date ajung la LLM?**
În MVP, doar sintetice. În producție: CNP-uri tokenizate unde se poate, model în regiune UE (ca RBI cu Azure OpenAI), context strict pe caz și nicio decizie cu efect semnificativ luată exclusiv automat (GDPR art. 22).

**6. Ce model folosiți și cât costă un caz?**
Un adaptor de model, pentru că stack-ul local pare AWS și Databricks, iar cel de grup Azure OpenAI. Costul și latența per caz sunt măsurate pe setul golden; în producție, furnizorul intră în registrul DORA, cu strategie de ieșire.

**7. Ce se întâmplă dacă modelul cade?**
Retry limitat cu aceeași cheie de idempotență, apoi coada manuală, fără efecte parțiale (argumentul de continuitate din DORA). Validatorii și regulile rulează și fără LLM.

**8. Cum vă apărați de prompt injection?**
Prin constrângere: modelul care citește documentul n-are tool-uri (Dual LLM), planul se fixează înainte de citire (Plan-Then-Execute), planner-ul alege din allowlist (Action-Selector), iar tool-uri care mută bani nu există. În demo: un PDF cu injecție și un trace fără scrieri.

**9. Pot reconstitui o decizie de acum șase luni?**
Da: `decision_record` păstrează append-only span-urile, `rule_id` și `rule_version`, versiunile de model și prompt, pragurile și deciziile umane. Rerularea cu aceleași versiuni dă aceeași decizie, iar testul de consistență verifică asta.

**10. Ce lăsați mereu omului?**
Banii și blocările, creditul, dispoziția alertelor AML, comunicările externe și cazurile cu injecție, conflict sau încredere scăzută. Cum a spus public CEO-ul: AI pregătește decizia, dar nu are ultimul cuvânt unde e afectată viața oamenilor.

**11. Sistemul e high-risk sub AI Act?**
După lectura din note (nu aviz juridic), procesele de operațiuni nu sunt în Anexa III; evaluarea bonității persoanelor fizice este, de la 2 decembrie 2027. Aplicăm oricum controale de tip Art. 12, 14 și 15, complementare reglementării bancare după EBA.

**12. Cum scalează la volume de producție?**
Workeri stateless, cozi, idempotență și, unde are sens, batch nocturn ca AIMM. Costul crește liniar, deci ROI-ul folosește costul per caz măsurat. Volumele românești le cerem mentorilor; la reconcilieri, CRISP proiectează volume de patru ori mai mari.

**13. Cum evitați erori greu de reversat, ca la e-Popriri?**
Acțiunile greu reversibile sunt doar propuse. Regula de venit protejat rulează înaintea calculului, iar `decided_by` explicit închide golul de responsabilitate dintre bancă, ANAF și executor.

**14. Ce aduceți în plus față de ARI sau Broadridge?**
ARI răspunde la întrebări despre proceduri; agentul le aplică pe dosare, cu audit trail. Broadridge face matching la CRISP, iar notele n-au găsit nimic public despre analiza cu LLM a excepțiilor rămase.

**15. De ce n-ați fi printre cele peste 40% de proiecte anulate?**
Gartner dă trei cauze: costuri în creștere, valoare neclară, controale de risc insuficiente. Răspundem cu cost per caz măsurat, un KPI de proces cu baseline și controale incluse din prima zi.

---

## 11. Alegerea framework-ului (build de 1–2 zile)

| Framework | PyPI (28 oct 2026) | Licență | Bun pentru | Atenție |
|---|---|---|---|---|
| LangGraph | 1.2.18 | MIT | fluxuri cu stare explicită și human-in-the-loop | curbă de învățare abruptă (listicle) |
| PydanticAI | 2.63.0 | MIT | extragere tipizată, schema-first | |
| OpenAI Agents SDK | 0.24.0 | MIT | agnostic de furnizor („100+ other LLMs”, LiteLLM și any-llm opționale) | |
| CrewAI, AutoGen, Mastra | neverificate | | CrewAI: prototip rapid | CrewAI: mai slab la stare (listicle) |

Notele spun că alegerea e o judecată, nu rezultatul unui benchmark: extragere tipizată ca miez → PydanticAI; mașină de stări explicită, cu întreruperi pentru aprobare → LangGraph; furnizor interschimbabil → OpenAI Agents SDK.

*(Propunere)* Țineți validatorii, regulile și calculele în Python simplu, independent de framework, cu scheme Pydantic la granițe. Framework-ul doar orchestrează, deci schimbarea lui nu schimbă nicio decizie, iar testele de reguli rulează fără LLM.

---

## 12. Goluri și surse

### 12.1 Goluri

- **Uplift și volume:** nu există dovezi independente, înainte și după, pentru niciun proces; aproape totul e [vendor] sau [bank self-reported]. Lipsesc volumele românești (popriri, reclamații, dispute, investigații de plăți) și costul unui chargeback pentru banca emitentă, în UE sau România.
- **Consistență și injecție:** niciun studiu independent despre variația run-to-run în bănci; afirmația AgentDojo (injecție reușită în 20–50% din cazuri) vine dintr-un blog de vendor, neverificată, deci nu o citați.
- **Arhitectură:** nicio arhitectură prescriptivă publicată de autorități; nicio dată publică de acuratețe sau STP pentru document-AI la bănci românești, inclusiv popririle de la BCR.
- **Reglementare:** lista CTPP completă și eventuala desemnare a unui furnizor de modele fundamentale sunt neverificate; nu există ghid BNR pe GenAI sau agenți; autoritatea națională de supraveghere sub AI Act, AMLR/AMLA și ghidurile EBA privind originarea creditelor nu au fost cercetate; holding-ul C-203/22 și voturile din PE sunt neverificate; **CCD2 art. 18 lipsește** din cele trei note.
- **Raiffeisen și hackathon:** „PoC-ul de automatizare a reclamațiilor la nivel de grup” lipsește din note; data lansării ARI diferă între surse; modelul din spatele ARI și ARIA și numele ARIA sunt neconfirmate. Pagina Agenda și juriul 2026 nu au fost preluate; sursele se contrazic la durată (24h vs 48h) și la premii (€8.000 vs €6.000); ponderile din §1 vin de la echipă, nu din rulebook.
- **Tooling:** versiunile CrewAI, Microsoft Agent Framework, Google ADK și Mastra nu au fost verificate; licențele uneltelor de evaluare vin din bloguri de vendori.
- **Excluse deliberat de note:** cifra McKinsey de 70–75% (supravegherea umană din costul variabil) și cifra EY (−50%, ≈2 ore per investigație AML), ambele fără sursă primară.

### 12.2 Surse (URL-uri din note)

**Benchmark-uri de proces**
- AML: https://www.niceactimize.com/Documents/aml_ai_in_aml_insights_report.pdf ; https://www.fluxforce.ai/answers/what-percentage-of-aml-alerts-are-false-positives ; https://sterlingfinance.uk/news/starling-bank-launches-native-ai-agent-to-automate-aml-investigations ; https://thepaypers.com/fraud-and-fincrime/news/fis-opens-aml-investigations-agent-built-with-anthropic-to-us-banks ; https://www.rapidflowapps.com/news/mckinsey-agentic-ai-could-lift-bank-compliance-productivity-up-to-20x-far-beyond-earlier-ai-tools/ ; https://www.mckinsey.com/capabilities/risk-and-resilience/our-insights/agentic-ai-in-financial-crime-prevention-lessons-from-winners
- KYC și ING: https://interexy.com/kyc-cost-per-customer ; https://sphinxhq.com/blog-posts/cost-of-manual-kyb-workflows ; https://www.fenergo.com/blogs/perpetual-kyc-pkyc ; https://evidentinsights.com/insights/articles/ing-genai-in-wholesale-banking ; https://mckinsey.com/industries/financial-services/our-insights/deploying-ai-at-speed-and-scale-talking-with-ings-marnix-van-stiphout ; https://www.wealthbriefing.com/html/article.php/ing-uses-ai-to-give-relationship-managers-more-time-for-clients-
- Sancțiuni: https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2024.1374323/pdf
- Plăți: https://www.bottomline.com/resources/blog/iso-20022-enabled-customer-case-management-final-hurdle-overcome-achieving-payments-modernisation ; https://www.validata-software.com/solutions/payments-investigation-and-case-manager/ ; https://www.evonsys.com/tracei-blogs/iso-20022-and-the-future-of-exception-handling-why-this-migration-is-a-defining-moment-for-banks
- Reconciliere: https://learnsignal.com/blog/ai-for-account-reconciliations ; https://digiqt.com/ai-agent/financial-services/reconciliation/nostro-reconciliation-ai-agent-for-reconciliation-in-financial-services/
- Dispute: https://www.mavenagi.com/resources/banking-transaction-disputes ; https://www.chargeflow.io/blog/cost-of-manual-vs-automated-chargeback-processing
- Credit: https://www.cognizant.com/us/en/case-studies/global-bank-processes-documents-98-percentage-faster-with-generative-ai ; https://group.bnpparibas/en/news/ai-at-bnp-paribas-3-using-artificial-intelligence-to-speed-up-granting-of-mortgage-loans
- Lloyds: https://www.bankingexchange.com/news-feed/item/10536-lloyds-says-genai-delivered-50m-of-value-in-2025 ; https://finainews.com/banking/lloyds-ai-generated-value-to-reach-134m-in-2026/ ; https://www.pymnts.com/news/artificial-intelligence/2025/lloyds-bank-and-coinbase-inside-their-generative-ai-playbooks/
- Popriri: https://www.vocea-olteniei.ro/2020/12/28/automatizarea-procesarii-documentelor-de-popriri-la-bcr/ ; https://www.ceccarbusinessmagazine.ro/anaf-propune-modificari-la-mecanismul-privind-automatizarea-infiintarii-si-ridicarii-popririlor-bancare/s/k8jVKT9MVfb048GOitqF ; https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf ; https://www.juridice.ro/862896/interoperabilitatea-bazelor-de-date-in-procedura-popririi-electronice-de-la-automatizarea-interogarilor-la-riscul-erorilor-de-sistem.html ; https://www.infocontact.ro/cont-blocat-abuziv-anaf-executor/
- Trade finance: https://floridai.agency/blog/letter-of-credit-discrepancy-rate-ai

**Studii de caz și analiști**
- BBVA: https://openai.com/index/bbva-collaboration-expansion/ ; https://www.bloomberg.com/news/articles/2025-12-12/bbva-rolls-out-chatgpt-to-almost-all-employees-in-openai-deal
- JPMorgan: https://www.fortune.com/2025/10/08/jamie-dimon-head-in-the-sand-ai-will-take-jobs-tip-iceberg ; https://www.mckinsey.com/industries/financial-services/our-insights/jpmorgan-chases-derek-waldron-on-building-an-ai-first-bank-culture
- BT × Visa: https://www.bancatransilvania.ro/news/comunicate-de-presa/comert-agentic-in-timp-real-banca-transilvania-a-finalizat-cu-succes-prima-plata-initiata-prin-intermediul-unui-agent-ai-cu-visa
- Alpha Bank (Dana): https://www.druidai.com/news/druid-ai-and-alpha-bank-launches-dana-virtual-assistant
- UiPath Maestro: https://siliconangle.com/2025/09/30/uipath-expands-agentic-platform-orchestration-development-governance-tools/
- McKinsey: https://www.mckinsey.com/de/news/presse/2025-10-23-global-banking-annual-review-2025 ; https://www.mckinsey.com/industries/financial-services/our-insights/banking-matters/agentic-ai-will-shake-up-banking-shrinking-global-profit-pools
- Accenture: https://www.accenture.com/gb-en/insights/banking/generative-ai-banking
- Gartner: https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
- BIS FSI: https://www.bis.org/fsi/fsibriefs26.pdf

**Reglementare**
- AI Act și Omnibus: https://eur-lex.europa.eu/eli/reg/2024/1689/oj ; https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/ ; https://artificialintelligenceact.eu/ai-act-explorer/digital-omnibus/ ; https://labs.cloudsecurityalliance.org/research/csa-research-note-eu-ai-act-omnibus-vii-deadline-delay-20260/
- EBA, BaFin, BCE: https://www.eba.europa.eu/sites/default/files/2025-11/d8b999ce-a1d9-4964-9606-971bbc2aaf89/AI%20Act%20implications%20for%20the%20EU%20banking%20sector.pdf ; https://www.bafin.de/EN/die-bafin/publikationen-daten/risiken-im-fokus/Fokusrisiken_2026/RIF_Trend1/RIF_Trend_1_digitalisierung_en.html ; https://cryptobriefing.com/eba-frontier-ai-risks-banks/ ; https://buttondown.com/Horizonscan/archive/ai-pulse-daily-brief-2026-09-23/
- GDPR și CJUE: https://eur-lex.europa.eu/eli/reg/2016/679/oj ; https://www.aoshearman.com/en/insights/ao-shearman-on-data/cjeu-rules-that-a-credit-score-constitutes-automated-decision-making-under-the-gdpr ; https://verfassungsblog.de/to-score-is-to-decide/ ; https://iapp.org/news/a/key-takeaways-from-the-cjeus-recent-automated-decision-making-rulings ; https://ppc.land/schufa-loses-blanket-trade-secret-defence-at-germanys-top-civil-court/
- DORA: https://eur-lex.europa.eu/eli/reg/2022/2554/oj ; https://www.morganlewis.com/de/blogs/sourcingatmorganlewis/2025/11/dora-eu-regulators-announce-list-of-critical-ict-third-party-providers ; https://finreg.aoshearman.com/esas-publish-official-list-of-designated-critical-ctpps-under-dora
- BNR: https://www.bnr.ro/uploads/2025-6raportanual_documentpdf_545_1782459656.pdf ; https://business24.ro/guvernanta/consolidare-guvernanta-rezilente-cibernetice-sector-1659001 ; https://www.bnr.ro/uploads/2025-12-09raportasuprastabilit%C4%83%C8%9Biifinanciare-decembrie2025_documentpdf_545_1765290572.pdf ; https://www.zf.ro/banci-si-asigurari/bnr-clarifica-avertismentul-european-privind-inteligenta-artificiala-analiza-riscurilor-cibernetice-confundata-indemn-retragerea-depozitelor-renuntarea-serviciile-financiare-digitale-23202162

**Moduri de eșec și tipare de securitate**
- https://arxiv.org/pdf/2605.30650 ; https://www.ncsc.gov.uk/pdfs/blog-post/exercise-caution-building-off-llms.pdf ; https://nhimg.org/articles/ai-agents-in-banking-need-runtime-controls-beyond-appsec/
- https://arxiv.org/abs/2506.08837v3 ; https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/ ; https://lord.technology/2025/06/14/securing-llm-agents-against-prompt-injection-through-design-patterns.html

**Raiffeisen și NEXXT**
- ARI și raportul anual: https://www.raiffeisen.ro/ro/despre-noi/comunicate-de-presa/2024/raiffeisen-bank-romania-dezvolta-ari-un-instrument-inovator-de-artificial-intelligence.html ; https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/rapoarte/anuale/2025-Raport-anual-Raiffeisen-Bank.pdf.coredownload.inline.pdf
- Ana, ERIC, Raiffeisen Tech: https://www.raiffeisen.ro/ro/imm/produse-si-servicii/servicii-electronice/ana-asistentul-virtual-raiffeisen-bank.html ; https://www.wall-street.ro/articol/banking/raiffeisen-lanseaza-un-agent-ai-pentru-antreprenori.html ; https://www.raiffeisen-tech.com/ro/en/open-positions.html
- RBI și CRISP: https://www.microsoft.com/en/customers/story/21406-raiffeisen-bank-international-azure ; https://www.rbinternational.com/en/raiffeisen/career/topics/ai-at-rbi.html ; https://www.broadridge.com/press-release/2026/broadridge-delivers-next-generation-reconciliation-platform-to-raiffeisen-bank-international
- CEO: https://spotmedia.ro/stiri/economie/zdenek-romanek-ceo-raiffeisen-bank-ai-poate-pregati-o-decizie-bancara-dar-nu-ar-trebui-sa-aiba-ultimul-cuvant ; https://www.wall-street.ro/articol/banking/ai-in-bancile-romanesti-ce-fac-bt-bcr-cec-ing-si-raiffeisen.html
- NEXXT: https://nexxtsummit.com/hackathon/ ; https://nexxtsummit.com/rulebook ; https://vibehack.eu/cities/bucharest ; https://bankingnews.ro/raiffeisen-bank-sustine-nexxt-ai-summit.html ; https://financialmarket.ro/events/nexxt-ai-hackathon-2026-aduce-la-bucuresti-peste-50-de-echipe-care-dezvolta-solutii-bazate-pe-inteligenta-artificiala/
- Câștigători 2025: https://start-up.ro/castigatorii-nexxt-ai-hackathon-2025-hackathonul-despre-viitorul-inteligentei-artificiale-in-banking ; https://startupcafe.ro/solutii-castigatoare-hackathon-solutii-inteligenta-artificiala-89179
- Profilul LinkedIn citat pentru ARIA: URL-ul e în `raiffeisen_profil_ai_hackathon.md` (omis aici intenționat).

**Framework-uri și evaluare**
- https://pypi.org/pypi/langgraph/json ; https://pypi.org/pypi/pydantic-ai/json ; https://pypi.org/pypi/openai-agents/json
- Comparații (orientative): https://www.morphllm.com/ai-agent-framework ; https://www.noqta.tn/en/blog/ai-agent-frameworks-langgraph-crewai-openai-sdk-comparison-2026
- Evaluare: https://futureagi.com/blog/best-open-source-eval-frameworks-2026 ; https://techsy.io/en/blog/llm-evaluation-framework-open-source
