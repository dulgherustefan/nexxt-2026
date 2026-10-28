"""Schemele celor două baze, una pe zonă (docs/06 §5: fiecare zonă are baza ei).

- zona client (`var/client_zone.db`): clienți, conturi, carduri, dispozitive, sesiuni, SCA, tranzacții,
  beneficiari salvați, SIM, dispute anterioare, reclamații, notificări, rambursări;
- zona AML (`var/aml_zone.db`): conturi (profil obiectiv, fără date demografice), fluxuri, alerte,
  sesizări (DisputeFacts primite prin diodă), registrul sintetic de firme, indicatori, etichete de adevăr.

Alte module își adaugă propriile tabele cu CREATE TABLE IF NOT EXISTS; aici nu presupunem că suntem singurii.
Momentele sunt ISO 8601 cu offset; coloanele `*_epoch` (secunde UTC) servesc doar la filtrare și sortare.
"""

from __future__ import annotations

CLIENT_TABLES = ["meta", "customers", "accounts", "cards", "devices", "sessions", "auth_events", "merchants",
                 "transactions", "payees", "sim_events", "prior_disputes", "complaints", "notifications", "refunds"]
AML_TABLES = ["meta", "accounts", "flows", "alerts", "referrals", "companies", "indicators", "synthetic_labels",
              "patterns"]

CLIENT_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS customers (
  customer_ref TEXT PRIMARY KEY, alias TEXT, first_name TEXT, last_name TEXT, full_name TEXT, cnp TEXT,
  birth_date TEXT, sex TEXT, phone TEXT, email TEXT, city TEXT, address TEXT, segment TEXT, customer_since TEXT,
  kyc_level TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS accounts (
  iban TEXT PRIMARY KEY, customer_ref TEXT NOT NULL, type TEXT, currency TEXT, opened_at TEXT,
  opening_balance REAL, balance REAL NOT NULL, status TEXT, is_primary INTEGER, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_accounts_customer ON accounts(customer_ref);
CREATE TABLE IF NOT EXISTS cards (
  card_id TEXT PRIMARY KEY, customer_ref TEXT, account_iban TEXT, pan_masked TEXT, last4 TEXT, scheme TEXT,
  product TEXT, status TEXT, issued_at TEXT, expires TEXT, token TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS devices (
  device_id TEXT PRIMARY KEY, customer_ref TEXT, fingerprint TEXT, model TEXT, os TEXT, app_version TEXT,
  enrolled_at TEXT, enrolled_epoch INTEGER, enrolled_via TEXT, enrollment_session_id TEXT, last_seen_at TEXT,
  status TEXT, first_ip TEXT, trusted INTEGER, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_devices_customer ON devices(customer_ref);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, customer_ref TEXT, device_id TEXT, ip TEXT, channel TEXT, started_at TEXT,
  started_epoch INTEGER, ended_at TEXT, user_agent TEXT, clicked_url TEXT, clicked_at TEXT, referrer TEXT, geo TEXT,
  synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_sessions_customer ON sessions(customer_ref);
CREATE TABLE IF NOT EXISTS auth_events (
  auth_id TEXT PRIMARY KEY, customer_ref TEXT, tx_id TEXT, session_id TEXT, device_id TEXT, ts TEXT, ts_epoch INTEGER,
  method TEXT, purpose TEXT, result TEXT, screen_showed_amount_and_payee INTEGER, shown_amount REAL, shown_payee TEXT,
  otp_text TEXT, phone TEXT, eci TEXT, cavv TEXT, cavv_present INTEGER, three_ds_version TEXT, flow_version TEXT,
  ip TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_auth_tx ON auth_events(tx_id);
CREATE INDEX IF NOT EXISTS ix_auth_session ON auth_events(session_id);
CREATE TABLE IF NOT EXISTS merchants (
  merchant_id TEXT PRIMARY KEY, name TEXT, mcc TEXT, purchase_type TEXT, channel TEXT, country TEXT, eea INTEGER,
  domain TEXT, cui TEXT, settlement_iban TEXT, city TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS transactions (
  tx_id TEXT PRIMARY KEY, customer_ref TEXT NOT NULL, account_iban TEXT, direction TEXT, kind TEXT, channel TEXT,
  amount REAL NOT NULL, currency TEXT, ts TEXT NOT NULL, ts_epoch INTEGER NOT NULL, booked_at TEXT, description TEXT,
  counterparty_name TEXT, counterparty_iban TEXT, merchant_id TEXT, mcc TEXT, card_id TEXT, pos_entry_mode TEXT,
  eci TEXT, cavv_present INTEGER, merchant_country TEXT, device_id TEXT, session_id TEXT, ip TEXT, status TEXT,
  end_to_end_id TEXT, disputable INTEGER, case_tag TEXT, balance_after REAL, idempotency_key TEXT UNIQUE,
  extra_json TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_tx_customer_ts ON transactions(customer_ref, ts_epoch);
CREATE INDEX IF NOT EXISTS ix_tx_counterparty ON transactions(customer_ref, counterparty_iban);
CREATE TABLE IF NOT EXISTS payees (
  customer_ref TEXT, iban TEXT, name TEXT, created_at TEXT, last_used_at TEXT, uses INTEGER,
  synthetic INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (customer_ref, iban));
CREATE TABLE IF NOT EXISTS sim_events (
  event_id TEXT PRIMARY KEY, customer_ref TEXT, phone TEXT, ts TEXT, ts_epoch INTEGER, kind TEXT, operator TEXT,
  channel TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_sim_customer ON sim_events(customer_ref, ts_epoch);
CREATE TABLE IF NOT EXISTS prior_disputes (
  dispute_id TEXT PRIMARY KEY, customer_ref TEXT, case_id TEXT, tx_ref TEXT, opened_at TEXT, opened_epoch INTEGER,
  closed_at TEXT, channel TEXT, dispute_type TEXT, scenario TEXT, amount REAL, counterparty TEXT, outcome TEXT,
  reason TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_prior_customer ON prior_disputes(customer_ref, opened_epoch);
CREATE TABLE IF NOT EXISTS complaints (
  case_id TEXT PRIMARY KEY, customer_ref TEXT, received_at TEXT, received_epoch INTEGER, channel_hint TEXT,
  source TEXT, text TEXT, attachments_json TEXT, transaction_refs_json TEXT, status TEXT, historical INTEGER DEFAULT 0,
  outcome TEXT, scenario TEXT, saved_at TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS notifications (
  notification_id TEXT PRIMARY KEY, customer_ref TEXT, ts TEXT, ts_epoch INTEGER, kind TEXT, text TEXT, read INTEGER,
  synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_notif_customer ON notifications(customer_ref, ts_epoch);
CREATE TABLE IF NOT EXISTS refunds (
  refund_id TEXT PRIMARY KEY, case_id TEXT, customer_ref TEXT, amount REAL, currency TEXT,
  idempotency_key TEXT UNIQUE NOT NULL, tx_id TEXT, ts TEXT, status TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
"""

AML_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS accounts (
  iban TEXT PRIMARY KEY, kind TEXT, bank_code TEXT, holder_type TEXT, account_type TEXT, opened_at TEXT, status TEXT,
  holder_ref TEXT, holder_name TEXT, cui TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_aml_accounts_holder ON accounts(holder_ref);
CREATE TABLE IF NOT EXISTS flows (
  flow_id TEXT PRIMARY KEY, ts TEXT NOT NULL, ts_epoch INTEGER NOT NULL, from_iban TEXT NOT NULL, to_iban TEXT NOT NULL,
  amount REAL NOT NULL, currency TEXT, channel TEXT, reference TEXT, reported_fraud INTEGER DEFAULT 0,
  report_source TEXT, case_id TEXT, feed TEXT, natural_key TEXT UNIQUE, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_flows_from ON flows(from_iban, ts_epoch);
CREATE INDEX IF NOT EXISTS ix_flows_to ON flows(to_iban, ts_epoch);
CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY, iban TEXT, rule_id TEXT, title TEXT, basis TEXT, ts TEXT, detail TEXT, status TEXT,
  synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_alerts_iban ON alerts(iban);
CREATE TABLE IF NOT EXISTS referrals (
  case_id TEXT PRIMARY KEY, received_at TEXT, victim_ref TEXT, channel TEXT, dispute_type TEXT, scenario TEXT,
  amount REAL, currency TEXT, executed_at TEXT, beneficiary_iban TEXT, beneficiary_name TEXT, beneficiary_cui TEXT,
  beneficiary_bic TEXT, domain TEXT, url TEXT, phone TEXT, domain_age_hours REAL, lookalike_score REAL,
  fact_ids_json TEXT, payload_json TEXT, lead_id TEXT, flow_id TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_referrals_iban ON referrals(beneficiary_iban);
CREATE TABLE IF NOT EXISTS companies (
  cui TEXT PRIMARY KEY, name TEXT, onrc TEXT, registered_at TEXT, status TEXT, caen TEXT, city TEXT, iban TEXT,
  role TEXT, cui_checksum_valid INTEGER, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS indicators (
  indicator TEXT PRIMARY KEY, kind TEXT, label TEXT, scenario TEXT, first_seen TEXT, target TEXT, ip TEXT,
  synthetic INTEGER NOT NULL DEFAULT 1);
-- etichete de adevăr și tiparele plantate: DOAR pentru antrenare și evaluare, nu pentru agenți
CREATE TABLE IF NOT EXISTS synthetic_labels (
  iban TEXT PRIMARY KEY, label TEXT, segment TEXT, role TEXT, hard_negative INTEGER, is_internal INTEGER,
  patterns_json TEXT, typologies_json TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS patterns (
  pattern_id TEXT PRIMARY KEY, typology TEXT, family TEXT, mules_json TEXT, victims_json TEXT, flow_ids_json TEXT,
  start TEXT, end TEXT, amount_in REAL, typologies_json TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
"""

# coloane booleene (INTEGER în SQLite, bool în dict-urile întoarse)
BOOL_COLUMNS = {"synthetic", "is_primary", "trusted", "screen_showed_amount_and_payee", "cavv_present", "eea",
                "disputable", "historical", "read", "reported_fraud", "cui_checksum_valid", "hard_negative",
                "is_internal"}
JSON_COLUMNS = {"attachments_json": "attachments", "transaction_refs_json": "transaction_refs",
                "extra_json": "extra", "fact_ids_json": "fact_ids", "payload_json": "payload",
                "patterns_json": "patterns", "typologies_json": "typologies", "mules_json": "mules",
                "victims_json": "victims", "flow_ids_json": "flow_ids"}
