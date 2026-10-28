# VersoML: implementarea (hartă, interfețe, contract API)

Documentul tehnic pentru cine scrie cod. Soluția și motivele sunt în `docs/05_versoml_solutie_si_plan.md`; contractele de date sunt în `versoml/contracts.py` și sunt sursa de adevăr.

## 1. Fapte de la pasul 0 (28.10.2026)

- Cheia Bedrock e o cheie pe termen lung. Se încarcă la rulare din `API_KEY.txt` prin `versoml.secrets.load_bedrock_key()`. Nimeni nu citește sau afișează fișierul.
- În UE, o politică SCP a organizației AWS blochează explicit `bedrock-mantle:CreateInference`. **Regiunea de lucru e `us-east-1`.**
- Modele care răspund prin Mantle în `us-east-1`: `anthropic.claude-opus-5-5`, `anthropic.claude-opus-4-8`, `anthropic.claude-sonnet-5`, `anthropic.claude-haiku-4-5` (Opus 5 și Opus 4.7 răspund, dar în ~90 s). `anthropic.claude-sonnet-5-5` și `anthropic.claude-haiku-5-5` nu sunt activate pe cont.
- Rolurile modelelor: **Opus 5.5** pentru Procuror, Avocatul nevinovăției și RTS; **Sonnet 5** pentru colectori, Avocat, OSINT și scrisori; **Haiku 4.5** pentru LLM-ul izolat (extragere din text neîncrezut) și clasificarea ajutătoare.
- Haiku 4.5 nu are thinking adaptiv și nici `effort`. Nu trimitem `temperature`, `top_p` sau `top_k` la niciun model.

## 2. Reguli pentru tot codul

- Python 3.12 din `.venv` (`uv sync`). Rulare: `.venv/Scripts/python.exe -m ...` pe Windows.
- Doar date sintetice, marcate `synthetic: true`. Nume din Faker `ro_RO`, CNP-uri generate cu cifră de control validă, dar cu județ fictiv 70–79 sau prefix de test. IBAN-uri RO cu cod de bancă fictiv `BDEM` (Banca Demo), `XBNK`, `YBNK`, `ZBNK` (nu există la BNR) și cifre de control valide. Domeniile escrocilor sunt pe `.example` sau `.test` (RFC 2606), ca să nu acuzăm domenii reale. Firmele beneficiare au CUI-uri cu cifră de control **invalidă** sau dintr-un registru sintetic, ca să nu cadă pe o firmă reală.
- Textul în română folosește ș/ț cu virgulă dedesubt. Intrarea se normalizează (ş→ș, ţ→ț).
- Niciun LLM nu are un tool care mută bani. Rambursarea o emite doar motorul de reguli, ca instrucțiune simulată, după aprobare umană acolo unde regulile o cer.
- Fiecare modul are teste în `tests/<modul>/` care trec fără rețea (fixtures). Testele live sunt marcate `@pytest.mark.live` și rulează doar cu `VERSOML_LIVE_TESTS=1`.
- Nu adăuga dependențe în `pyproject.toml` fără nevoie. Dacă instalezi ceva cu `uv add`, spune în raport.
- Logurile trec prin `versoml.secrets.install_log_redaction()`. Nu loga headere, chei sau text de reclamație nepseudonimizat.

## 3. Harta modulelor

| Director | Ce conține | Cine îl scrie |
|---|---|---|
| `versoml/contracts.py` | Contractele Pydantic | platformă |
| `versoml/config.py`, `versoml/secrets.py` | Setări, cheia la rulare, redactare | platformă |
| `versoml/shared/llm/` | Clientul Bedrock Mantle, rutare pe roluri, fallback, structured outputs, modurile live/replay/offline | orchestrare |
| `versoml/shared/events.py` | Magistrala de evenimente AG-UI pe zone, persistată pentru replay | orchestrare |
| `versoml/shared/rules/` | Motorul de reguli cu ID-uri, calendarul RO, ceasurile, parametrii [U] | reguli |
| `versoml/shared/ledger/` | Registrul de probe: lanț SHA-256, Merkle, Ed25519, QR, verificare | platformă |
| `versoml/shared/privacy/` | PrivacyProxy: recunoscători RO, seif de pseudonime, verificarea destinațiilor | platformă |
| `versoml/shared/policy/` | Politici Cedar, punctul de control pe fiecare tool, jurnalul de decizii | platformă |
| `versoml/wall/` | Dioda (outbox semnat HMAC), HoldSignal, filtrul de scrisori, canary, scannerul | platformă |
| `versoml/data/` | Simulatorul de bancă, scenariile, setul de aur, seed-ul bazelor pe zone, depozitele de date | date+ML |
| `versoml/ml/` | M1, M2, M5, M6, M7 + antrenare și metrici | date+ML |
| `versoml/osint/` | Căutare web, crawler, RDAP, CT, DNS, Wayback, ANAF, OpenPhish, sancțiuni, M3 (sosie), M4 (asemănarea paginii) | OSINT |
| `versoml/zone_client/` | Graful Judecătorului, agenții, aplicația FastAPI a zonei client | orchestrare |
| `versoml/zone_aml/` | Graful Investigatorului, agenții, aplicația FastAPI a zonei AML | orchestrare |
| `versoml/mcp_server/` | Serverul MCP (stdio + HTTP), tool-uri pe zone, filtrate de Cedar | orchestrare |
| `versoml/eval/` | Setul de aur, neinterferența, red-team, raportul | orchestrare |
| `versoml/cli.py` | `versoml up | seed | train | eval | mcp | check-bedrock | demo` | orchestrare |
| `frontend/` | Vite + React: consola de contestații, consola AML, Banca Demo, pagina falsă de demo | UI |

## 4. Interfețe între module (semnături stabile)

### 4.1 Date (`versoml/data/`)

```python
# versoml/data/world.py
def generate_world(seed: int = 7, n_customers: int = 2000) -> World: ...
# World: dataclass cu liste de dict-uri: customers, accounts, devices, sessions, auth_events,
#        card_transactions, transfers, merchants, companies, domains, complaints, labels

# versoml/data/seed.py
def seed_all(settings=None, seed: int = 7) -> dict:
    """Generează lumea și scrie DOUĂ baze separate: var/client_zone.db și var/aml_zone.db.
    Zona client primește: clienții, conturile lor, tranzacțiile, SCA, dispozitive, sesiuni, reclamații.
    Zona AML primește: fluxurile conturilor interne (inclusiv cărăușii), profilul obiectiv al conturilor,
    alertele. Întoarce numărătorile pe tabele."""

# versoml/data/scenarios.py
SCENARIOS: dict[str, ScenarioSpec]   # cheile = valorile din contracts.Scenario + "demo_t1"
def build_scenario(scenario_id: str, seed: int = 7) -> ScenarioBundle:
    """Un caz complet și determinist: Complaint + înregistrările lui (tranzacție, SCA, dispozitiv,
    sesiune, beneficiar, domeniu) + rezultatul așteptat (verdict, reguli, termene)."""

# versoml/data/repos.py: singura cale prin care agenții citesc „sistemele băncii"
class ClientRepo:   # doar var/client_zone.db
    def get_customer(self, customer_ref: str) -> dict | None
    def get_transaction(self, tx_id: str) -> dict | None
    def list_transactions(self, customer_ref: str, days: int = 90) -> list[dict]
    def get_auth_events(self, tx_id: str) -> list[dict]            # SCA: metodă, ce a afișat ecranul
    def get_device_history(self, customer_ref: str) -> list[dict]
    def get_session(self, session_id: str) -> dict | None           # IP, dispozitiv, momentul click-ului
    def get_prior_disputes(self, customer_ref: str, months: int = 12) -> list[dict]
    def beneficiary_seen_before(self, customer_ref: str, iban: str) -> bool
    def find_duplicates(self, tx_id: str) -> list[dict]
    def sim_swap_events(self, customer_ref: str, before: datetime, hours: int = 48) -> list[dict]
    def save_complaint(self, complaint: Complaint) -> None
    def list_complaints(self) -> list[dict]
    def get_complaint(self, case_id: str) -> dict | None
    # Banca Demo: sold, tranzacții, notificări
    def balance(self, customer_ref: str) -> float
    def post_transfer(self, from_ref: str, to_iban: str, amount: float, meta: dict) -> dict
    def post_refund(self, case_id: str, customer_ref: str, amount: float, idempotency_key: str) -> dict

class AmlRepo:      # doar var/aml_zone.db
    def account_profile(self, iban: str) -> dict | None   # vârsta contului, tip, rulaj; fără date demografice
    def flows(self, iban: str, days: int = 30) -> list[dict]
    def neighborhood(self, ibans: list[str], hops: int = 2, days: int = 30) -> dict  # {nodes, edges}
    def list_alerts(self) -> list[dict]
    def save_referral(self, facts: DisputeFacts) -> None
    def list_referrals(self) -> list[dict]
    def ingest_demo_payment(self, from_ref: str, to_iban: str, amount: float, ts: datetime) -> None
```

### 4.2 ML (`versoml/ml/`)

```python
# versoml/ml/train.py
def train_all(seed: int = 7) -> dict          # antrenează și salvează în var/models; întoarce metricile
# versoml/ml/m1_classifier.py
def classify_complaint(text: str, meta: dict | None = None) -> Classification
# versoml/ml/m2_client_fraud.py
def client_fraud_signal(features: dict) -> dict   # {score, top_features:[(nume, contribuție)], model_version}
# versoml/ml/m5_mule.py
def score_accounts(graph: dict) -> list[AccountScore]    # graph = AmlRepo.neighborhood(...)
def communities(graph: dict) -> dict[str, int]
def detect_typologies(graph: dict) -> list[dict]         # fan-in, fan-out, tranzit rapid, ciclu, scatter-gather
# versoml/ml/m6_entity_resolution.py
def link_cases(referrals: list[dict]) -> list[dict]      # clustere de cazuri legate, cu motivul legăturii
# versoml/ml/m7_counterfactual.py
def counterfactual(decide, ctx: dict, fields: list[str]) -> dict  # rata de schimbare + faptele fragile
```

### 4.3 OSINT (`versoml/osint/`)

```python
class ToolResult(BaseModel):
    tool: str; args: dict; ok: bool; data: dict; summary: str
    signal: Literal["rosu","galben","verde","neutru"]
    source_url: str | None; retrieved_at: datetime
    mode: Literal["live","fixture","cache","offline"]; latency_ms: int; error: str | None

async def web_search(query: str, n: int = 8) -> ToolResult           # Serper → Brave → Tavily → Exa → DuckDuckGo
async def fetch_page(url: str) -> ToolResult                           # fetch sigur, fără JS, lanț de redirect, formulare
async def rdap_domain(domain: str) -> ToolResult
async def dns_records(domain: str) -> ToolResult
async def ct_certificates(domain: str) -> ToolResult                   # crt.sh
async def wayback_first_seen(domain: str) -> ToolResult
async def ip_geo(ip: str) -> ToolResult
async def openphish_check(url_or_domain: str) -> ToolResult
async def anaf_company(cui: str) -> ToolResult
async def sanctions_screen(name: str) -> ToolResult
async def phone_intel(phone: str) -> ToolResult
def lookalike_score(domain: str, protected: list[str] | None = None) -> ToolResult   # M3
def page_similarity(html: str, reference: str = "bancademo_login") -> ToolResult     # M4
def validate_iban(iban: str) -> ToolResult
async def investigate(artifacts: dict) -> list[ToolResult]   # toate tool-urile potrivite, în paralel
```

Modurile: `fixture` citește `versoml/osint/fixtures/<tool>/<cheie>.json`; `live` apelează sursa reală; `auto` încearcă live și cade pe fixture sau cache. Rezultatele live se pun în cache în `var/osint_cache.db`.

### 4.4 Reguli (`versoml/shared/rules/`)

```python
def evaluate(ctx: RuleContext, params: dict | None = None) -> RulesOutcome
def catalog() -> list[dict]                      # {rule_id, title, basis, confidence, pack, params}
def get_params() -> dict; def set_params(updates: dict) -> dict   # parametrii [U], în var/rules_params.json
# calendar_ro.py
def end_of_next_business_day(dt: datetime) -> datetime   # 23:59:59 ora României
def add_business_days(dt: datetime, n: int) -> datetime
def is_business_day(d: date) -> bool
```

### 4.5 Platformă

```python
# versoml/shared/ledger
class Ledger:
    def __init__(self, zone: Zone, db_path: Path, keys_dir: Path)
    def append(self, case_id, kind, source_tool, args: dict, content: dict, summary: str, labels: Labels | None = None) -> Fact
    def facts(self, case_id) -> list[Fact]
    def seal(self, case_id) -> dict      # {root, signature, public_key, count, sealed_at, qr_svg}
    def verify(self, case_id) -> dict    # {valid, checks:[{name, ok, detail}]}
    def export_dossier(self, case_id) -> dict
def verify_dossier(dossier: dict) -> dict

# versoml/shared/privacy
class PrivacyProxy:
    def pseudonymize(self, text: str, case_id: str, known: dict[str, str] | None = None) -> tuple[str, dict]
    def restore(self, text: str, vault: dict) -> str
    def scan(self, text: str) -> list[dict]          # CNP, IBAN, card, telefon, e-mail, nume cunoscute
def check_sink(labels: Labels, sink: Sink) -> bool

# versoml/shared/policy
def authorize(principal: str, action: str, resource_zone: Zone, context: dict | None = None) -> PolicyDecision
def guarded(principal: str, action: str, zone: Zone)   # decorator; ridică PolicyDenied și jurnalizează
def recent_decisions(limit: int = 50) -> list[PolicyDecision]

# versoml/wall
def check_letter(text: str) -> FilterResult               # termeni interziși + canary + PII
class Diode: send_facts(DisputeFacts) / receive_facts(payload, signature) / send_hold(HoldSignal) / receive_hold(...)
class CanaryRegistry: mint(lead_id) -> str ; scan(text) -> int    # registrul ține doar hash-uri
```

## 5. Procese și porturi

- `versoml up` pornește două procese: **zona client** pe `127.0.0.1:8000` (servește și UI-ul) și **zona AML** pe `127.0.0.1:8001` (servește aceeași aplicație UI, dar în modul AML).
- Zonele comunică doar prin diodă: client → AML `POST /diode/inbox` (DisputeFacts, semnat HMAC); AML → client `POST /diode/hold` (HoldSignal). Nimic altceva.
- Fiecare zonă are baza ei: `var/client_zone.db`, `var/aml_zone.db`. Zona client nu are calea spre baza AML în configurare.

## 6. Contractul API (pentru UI)

Toate răspunsurile sunt JSON. Datele sunt în ISO 8601 cu fus orar. Evenimentele vin prin SSE (`text/event-stream`), un `AgentEvent` JSON pe mesaj (`data: {...}`); la conectare se trimit întâi evenimentele deja produse.

### 6.1 Zona client (`:8000`)

| Metodă și cale | Răspuns |
|---|---|
| `GET /api/meta` | `{zone:"client", version, llm:{mode, region, models:{opus,sonnet,haiku}, live_ok}, osint_mode, urls:{client, aml}}` |
| `GET /api/stats` | `{cases_total, open, refunded, awaiting_human, amount_refunded, amount_recoverable, avg_decision_seconds, deadlines_at_risk, by_status:{}, by_scenario:{}}` |
| `GET /api/scenarios` | `[{id, title, description, channel, expected_verdict}]` |
| `POST /api/cases` | corp `{scenario_id}` sau `{complaint:{customer_ref, text, transaction_refs, attachments}}` → `{case_id}` |
| `GET /api/cases` | `[{case_id, customer_alias, received_at, channel, scenario, amount:{value,currency}, status, verdict, deadline, sla_seconds_left, requires_human}]` |
| `GET /api/cases/{id}` | `CaseDetail` (mai jos) |
| `POST /api/cases/{id}/run` | `{run_id}`; pornește graful Judecătorului |
| `GET /api/cases/{id}/events` | SSE de `AgentEvent` |
| `POST /api/cases/{id}/approve` | corp `{action:"approve"|"reject", note?, approver?}` → `{ok, status}` |
| `POST /api/cases/{id}/counterfactual` | corp `{field, value}` → `{before:[{question,decision}], after:[...], changed:[...], explanation}` |
| `POST /api/cases/{id}/letter/check` | corp `{body}` → `FilterResult` |
| `GET /api/ledger/{case_id}` | `{facts:[Fact], seal:{root, signature, public_key, count, sealed_at, qr_svg}|null, verify:{valid, checks}}` |
| `POST /api/verify` | corp = dosarul exportat → `{valid, checks:[{name, ok, detail}]}` |
| `GET /api/rules` | `[{rule_id, title, basis, confidence, pack, params}]` |
| `GET/PUT /api/rules/params` | `{nume: valoare}` |
| `GET /api/wall` | `{layers:[{id, name, status:"ok"|"alert", detail}], denials:[PolicyDecision], blocks:[{at, case_id, reasons, terms}], noninterference:{runs, leaks, at}}` |
| `POST /api/wall/attack` | corp `{kind:"read_aml_tool"|"letter_tipping_off"|"prompt_injection"|"diode_text_field", payload?}` → `{blocked, layer, detail, evidence}` |
| `GET /api/eval` | ultimul raport de evaluare (JSON) |
| `GET /api/mcp` | `{tools:[{name, zone, description, effect}], snippets:{claude_desktop, cursor}, http_url}` |
| `GET /api/bank/{customer_ref}` | Banca Demo: `{customer_alias, balance, iban_masked, transactions:[{id, ts, description, amount, direction, status, disputable}], notifications:[{ts, text, kind}]}` |
| `POST /api/bank/{customer_ref}/dispute` | corp `{transaction_id, text}` → `{case_id}` (creează și pornește cazul) |
| `POST /api/demo/scam` | corp `{customer_ref, card_last4?}` → `{transaction_id, amount}`: simulează plata spre contul escrocului după pagina falsă |

**`CaseDetail`**
```json
{
  "summary": {"case_id": "CT-2026-000123", "status": "ASTEAPTA_APROBARE", "verdict": "RAMBURSEAZA_CU_APROBARE", "deadline": "2026-10-29T23:59:59+02:00", "sla_seconds_left": 81234, "amount": {"value": 3200, "currency": "RON"}, "channel": "transfer", "scenario": "phishing_link", "customer_alias": "Client 0042"},
  "complaint": {"text": "…", "attachments": [{"kind": "sms", "content": "…"}], "received_at": "…"},
  "extracted": {"…": "ExtractedClaim"},
  "classification": {"…": "Classification"},
  "facts": [{"…": "Fact"}],
  "rules": {"…": "RulesOutcome"},
  "decisions": [{"…": "Decision"}],
  "debate": {"prosecutor": [{"text": "…", "cites": ["EV-004"]}], "defender": [], "rubric": [{"indicator": "…", "value": true, "weight": 2, "cites": []}], "recommendation": "NU_RECOMANDAM_RECUPERARE", "ran": true},
  "recovery": {"chargeback": {"eligible": false, "reason_code": "10.4", "explanation": "…"}, "recall": {"kind": "camt.056", "xml": "<…>", "deadline": "…"}, "dnsc_report": {"text": "…"}},
  "letter": {"…": "LetterDraft"},
  "pipeline": {"nodes": [{"id": "receptor", "label": "Receptor", "agent": "Judecătorul/Receptor", "model": "haiku", "status": "done", "summary": "…"}], "edges": [{"source": "receptor", "target": "clasificator"}]},
  "interrupt": {"pending": true, "kind": "aprobare_rambursare", "prompt": "…", "options": ["approve", "reject"]},
  "hold": {"received": false},
  "ledger": {"count": 14, "root": "…", "sealed": true}
}
```

Statusuri: `NOU`, `IN_ANALIZA`, `ASTEAPTA_APROBARE`, `RAMBURSAT`, `EXCEPTIE`, `RESPINS`, `TRASEU_APP`, `INCHIS`.

### 6.2 Zona AML (`:8001`)

| Metodă și cale | Răspuns |
|---|---|
| `GET /api/meta` | `{zone:"aml", …}` |
| `GET /api/aml/stats` | `{referrals, leads, rts_drafts, accounts_flagged, amount_at_risk, communities}` |
| `GET /api/aml/referrals` | `[{case_id, received_at, amount, beneficiary_iban_masked, scenario, lead_id}]` |
| `GET /api/aml/leads` | `[{lead_id, case_ids, top_score, typologies, recommendation, status, updated_at}]` |
| `GET /api/aml/leads/{lead_id}` | `{lead: AmlLead, graph:{nodes:[{id, label, kind:"victima"|"carausi"|"exchange"|"comerciant"|"cont"|"numerar", score, community, amount_in, amount_out, flagged}], edges:[{id, source, target, amount, ts, case_id, kind}]}, osint:[OsintFinding], innocent:[RationaleLine], rts:{fields:{}, narrative:[RationaleLine], status}, clocks:[Deadline], timeline:[AgentEvent]}` |
| `POST /api/aml/leads/{lead_id}/run` | `{run_id}`; pornește graful Investigatorului |
| `GET /api/aml/leads/{lead_id}/events` | SSE de `AgentEvent` |
| `POST /api/aml/leads/{lead_id}/decide` | corp `{action:"file_rts"|"close"|"request_info"|"hold_client", note?, analyst?}` → `{ok}` |
| `POST /api/aml/osint` | corp `{target, kind?:"auto"|"domain"|"url"|"phone"|"cui"|"iban"|"company"}` → `{findings:[OsintFinding], raw:{}}` |
| `GET /api/aml/campaigns` | `[{campaign_id, cases, shared:{domains, ibans, phones}, amount_total}]` |
| `GET /api/aml/graph` | rețeaua conturilor semnalate: `{nodes, edges}` |
| `GET /api/aml/wall` | jurnalul de politici al zonei AML |

## 7. Design UI

Galben, alb și negru, editorial, după cele trei imagini de referință (CabinCar, Post Malone, NEOFASHION). Detaliile sunt în `frontend/DESIGN.md`.
