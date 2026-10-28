# VersoML evaluation report

Generated: 2026-10-28T19:25:26.848552+00:00 · LLM mode: live

| Metric | Value | Target |
|---|---|---|
| Rules: T+1 verdict on the golden set (40) | 100.0% | 100% |
| Rules: verdict on 300 generated cases | 100.0% | 100% |
| Correct T+1 deadlines | 100.0% | 100% |
| Recall of escalations to a person | 100.0% | ≥ 0.95 |
| Non-interference: leaks across the wall | 0 | 0 |
| Non-interference: decisions changed by the AML zone | 0 | 0 |
| Raw personal data sent to the LLM | 0 | 0 |
| Injections detected | 100.0% | 100% |
| Letter check: tipping-off recall | 100.0% | 100% |
| Letter check: clean letters blocked by mistake | 0 | 0 |
| Injections: false alarms on clean complaints | 0.0% | ≈ 0 |
| M1 scenario classification: macro-F1 | 99.0% | ≥ 0.90 |
| M1 scenario calibration: ECE | 3.6% | ≤ 0.05 |
| M5 money mules: AUC (graph GBDT) | 99.2% | ≥ 0.85 |
| M5 money mules: AUC, rules only (baseline) | 75.0% | comparison |
| M5: false alarms on hard negatives | 0.8% | ≈ 0 |

## Details

```json
{
 "rules_golden": {
  "cases": 40,
  "verdict_accuracy": 1.0,
  "requires_human_accuracy": 1.0,
  "escalation_recall": 1.0,
  "deadline_accuracy": 1.0,
  "recovery_accuracy": 1.0,
  "ms_per_case": 1.114,
  "failures": []
 },
 "rules_generated": {
  "cases": 300,
  "verdict_accuracy": 1.0,
  "requires_human_accuracy": 1.0,
  "escalation_recall": 1.0,
  "deadline_accuracy": 1.0,
  "recovery_accuracy": 1.0,
  "ms_per_case": 0.163,
  "failures": []
 },
 "privacy": {
  "complaints_checked": 140,
  "raw_pii_to_llm": 0,
  "pseudonyms_created": 125
 },
 "injection": {
  "injection_cases": 28,
  "detected": 28,
  "detection_rate": 1.0,
  "false_positive_rate": 0.0,
  "decision_changed_by_injection": 0,
  "note": "The complaint text does not go into RuleContext, so the text cannot change the decision."
 },
 "letter_filter": {
  "adversarial": 20,
  "blocked": 20,
  "tipping_off_recall": 1.0,
  "clean": 14,
  "false_blocks": 0,
  "false_block_examples": []
 },
 "ml": {
  "seed": 7,
  "generated_at": "2026-10-28T21:20:54+02:00",
  "seconds_total": 9.25,
  "seconds": {
   "world": 1.19,
   "m1": 6.07,
   "m2": 0.22,
   "m5": 1.64,
   "m6_m7": 0.13
  },
  "m1_classifier": {
   "channel": {
    "accuracy": 0.9948,
    "macro_f1": 0.9961,
    "ece": 0.004,
    "classes": [
     "card",
     "transfer",
     "transfer_instant"
    ]
   },
   "dispute_type": {
    "accuracy": 1.0,
    "macro_f1": 1.0,
    "ece": 0.0004,
    "classes": [
     "app",
     "disputa_comerciant",
     "eroare_procesare",
     "neautorizata"
    ]
   },
   "scenario": {
    "accuracy": 0.9896,
    "macro_f1": 0.9895,
    "ece": 0.0364,
    "classes": [
     "card_ecom_fara_3ds",
     "card_visa_secure",
     "cont_sigur",
     "frauda_client",
     "inel_carausi",
     "injectie_document",
     "marfa_nelivrata",
     "phishing_link",
     "plata_dubla",
     "reclamatie_tardiva",
     "sim_swap",
     "vishing_securitate"
    ]
   },
   "n_train": 3120,
   "n_test": 960,
   "model_version": "m1-tfidf-lr-iso-de1029a4",
   "ambiguous_rate_sample": 0.0396,
   "accuracy_text_only": {
    "channel": 0.9896,
    "dispute_type": 1.0,
    "scenario": 0.9333
   },
   "held_out": "corpus generat cu alt seed (seed+1000): aceleași șabloane, alte persoane, stiluri și fapte; acuratețea pe reclamații reale va fi mai mică"
  },
  "m2_client_fraud": {
   "held_out": {
    "auc": 0.9908,
    "pr_auc": 0.9596,
    "f1": 0.8878,
    "precision": 0.9029,
    "recall": 0.8732,
    "threshold": 0.5,
    "n": 1250,
    "positives": 213
   },
   "brier": 0.028,
   "n_train": 3750,
   "n_test": 1250,
   "fraud_rate": 0.17,
   "note": "semnal pentru om; distribuții sintetice suprapuse, nu date reale",
   "model_version": "m2-lgbm-234c294a"
  },
  "m5_mule": {
   "rules_only": {
    "auc": 0.7505,
    "pr_auc": 0.4394,
    "f1": 0.3978,
    "precision": 0.72,
    "recall": 0.2748,
    "threshold": 0.5,
    "n": 839,
    "positives": 131
   },
   "gbdt_no_graph": {
    "auc": 0.9537,
    "pr_auc": 0.8295,
    "f1": 0.7653,
    "precision": 0.726,
    "recall": 0.8092,
    "threshold": 0.1632,
    "n": 839,
    "positives": 131
   },
   "gbdt_graph": {
    "auc": 0.9916,
    "pr_auc": 0.9689,
    "f1": 0.9286,
    "precision": 0.9669,
    "recall": 0.8931,
    "threshold": 0.1969,
    "n": 839,
    "positives": 131
   },
   "gbdt_graph_at_0.5": {
    "auc": 0.9916,
    "pr_auc": 0.9689,
    "f1": 0.887,
    "precision": 0.9815,
    "recall": 0.8092,
    "threshold": 0.5,
    "n": 839,
    "positives": 131
   },
   "cv": "StratifiedGroupKFold(5), grupuri = tiparul de spălare (cărăușii aceluiași tipar stau în același fold)",
   "window_days": 30,
   "n_accounts": 839,
   "mule_rate": 0.1561,
   "false_positive_rate_hard_negatives": 0.0077,
   "model_version": "m5-lgbm-graph-678b4a63"
  },
  "m6_entity_resolution": {
   "clusters": [
    {
     "case_ids": [
      "CT-2026-900001",
      "CT-2026-900005",
      "CT-2026-900011",
      "CT-2026-900015",
      "CT-2026-900016"
     ],
     "reasons": [
      "domeniu",
      "iban",
      "telefon"
     ]
    },
    {
     "case_ids": [
      "CT-2026-900010",
      "CT-2026-910019",
      "CT-2026-910020"
     ],
     "reasons": [
      "domeniu",
      "iban"
     ]
    }
   ],
   "demo_t1_linked_to_victima2": true,
   "inel_3_victims_linked": true
  },
  "m7_counterfactual": {
   "case": "demo_t1",
   "decide": "oracle.expected_outcome (tabelul comun cu motorul de reguli)",
   "change_rate": 0.3529,
   "fragile_fields": [
    "amount",
    "client_fraud_score",
    "dispute_type",
    "hold_signal",
    "notified_at",
    "prior_disputes_12m"
   ],
   "n_variants": 17
  },
  "synthetic": true,
  "note": "Toate metricile sunt pe date sintetice; pe date reale vor fi mai mici."
 },
 "noninterference": {
  "at": "2026-10-28T19:25:26.835963+00:00",
  "scenarios": [
   "demo_t1",
   "card_visa_secure",
   "vishing_securitate",
   "sim_swap",
   "frauda_client",
   "injectie_document"
  ],
  "runs": 12,
  "mismatches": 0,
  "mismatch_details": [],
  "letters_failing_filter": 0,
  "canaries_planted": 5,
  "canary_hits_in_client_zone": 0,
  "bytes_scanned": 1451561,
  "leaks": 0,
  "statuses": {
   "demo_t1": [
    "RAMBURSAT",
    "RAMBURSAT"
   ],
   "card_visa_secure": [
    "RAMBURSAT",
    "RAMBURSAT"
   ],
   "vishing_securitate": [
    "TRASEU_APP",
    "TRASEU_APP"
   ],
   "sim_swap": [
    "RAMBURSAT",
    "RAMBURSAT"
   ],
   "frauda_client": [
    "RAMBURSAT",
    "RAMBURSAT"
   ],
   "injectie_document": [
    "RAMBURSAT",
    "RAMBURSAT"
   ]
  }
 }
}
```
