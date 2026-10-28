# VersoML · raport de evaluare

Generat: 2026-10-28T16:50:13.727248+00:00 · mod LLM: live

| Metrică | Valoare | Țintă |
|---|---|---|
| Reguli: verdict T+1 pe setul de aur (40) | 100.0% | 100% |
| Reguli: verdict pe 300 de cazuri generate | 100.0% | 100% |
| Termene T+1 corecte | 100.0% | 100% |
| Recall escaladări spre om | 100.0% | ≥ 0,95 |
| Neinterferență: scurgeri peste zid | 0 | 0 |
| Neinterferență: decizii schimbate de zona AML | 0 | 0 |
| Date personale brute trimise LLM-ului | 0 | 0 |
| Injecții detectate | 100.0% | 100% |
| Filtrul zidului: recall tipping-off | 100.0% | 100% |
| Filtrul zidului: scrisori curate blocate greșit | 0 | 0 |
| Injecții: alarme false pe reclamații curate | 0.0% | ≈ 0 |
| M1 clasificare scenariu: macro-F1 | 99.3% | ≥ 0,90 |
| M1 calibrare scenariu: ECE | 4.0% | ≤ 0,05 |
| M5 cărăuși: AUC (GBDT pe graf) | 99.1% | ≥ 0,85 |
| M5 cărăuși: AUC doar reguli (bază) | 75.0% | comparație |
| M5: alarme false pe contraexemple dificile | 0.8% | ≈ 0 |

## Detalii

```json
{
 "rules_golden": {
  "cases": 40,
  "verdict_accuracy": 1.0,
  "requires_human_accuracy": 1.0,
  "escalation_recall": 1.0,
  "deadline_accuracy": 1.0,
  "recovery_accuracy": 1.0,
  "ms_per_case": 5.208,
  "failures": []
 },
 "rules_generated": {
  "cases": 300,
  "verdict_accuracy": 1.0,
  "requires_human_accuracy": 1.0,
  "escalation_recall": 1.0,
  "deadline_accuracy": 1.0,
  "recovery_accuracy": 1.0,
  "ms_per_case": 0.485,
  "failures": []
 },
 "privacy": {
  "complaints_checked": 140,
  "raw_pii_to_llm": 0,
  "pseudonyms_created": 43
 },
 "injection": {
  "injection_cases": 28,
  "detected": 28,
  "detection_rate": 1.0,
  "false_positive_rate": 0.0,
  "decision_changed_by_injection": 0,
  "note": "Textul reclamației nu intră în RuleContext: decizia nu poate fi schimbată de text."
 },
 "letter_filter": {
  "adversarial": 8,
  "blocked": 8,
  "tipping_off_recall": 1.0,
  "clean": 6,
  "false_blocks": 0,
  "false_block_examples": []
 },
 "ml": {
  "seed": 7,
  "generated_at": "2026-10-28T18:46:22+02:00",
  "seconds_total": 18.5,
  "seconds": {
   "world": 2.5,
   "m1": 12.1,
   "m2": 0.45,
   "m5": 3.15,
   "m6_m7": 0.3
  },
  "m1_classifier": {
   "channel": {
    "accuracy": 0.9958,
    "macro_f1": 0.9969,
    "ece": 0.0049,
    "classes": [
     "card",
     "transfer",
     "transfer_instant"
    ]
   },
   "dispute_type": {
    "accuracy": 1.0,
    "macro_f1": 1.0,
    "ece": 0.0003,
    "classes": [
     "app",
     "disputa_comerciant",
     "eroare_procesare",
     "neautorizata"
    ]
   },
   "scenario": {
    "accuracy": 0.9927,
    "macro_f1": 0.9927,
    "ece": 0.0397,
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
   "model_version": "m1-tfidf-lr-iso-404583ac",
   "ambiguous_rate_sample": 0.0437,
   "accuracy_text_only": {
    "channel": 0.9948,
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
    "auc": 0.9914,
    "pr_auc": 0.9686,
    "f1": 0.9286,
    "precision": 0.9669,
    "recall": 0.8931,
    "threshold": 0.1969,
    "n": 839,
    "positives": 131
   },
   "gbdt_graph_at_0.5": {
    "auc": 0.9914,
    "pr_auc": 0.9686,
    "f1": 0.8861,
    "precision": 0.9906,
    "recall": 0.8015,
    "threshold": 0.5,
    "n": 839,
    "positives": 131
   },
   "cv": "StratifiedGroupKFold(5), grupuri = tiparul de spălare (cărăușii aceluiași tipar stau în același fold)",
   "window_days": 30,
   "n_accounts": 839,
   "mule_rate": 0.1561,
   "false_positive_rate_hard_negatives": 0.0077,
   "model_version": "m5-lgbm-graph-684b1746"
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
  "at": "2026-10-28T16:50:13.675899+00:00",
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
  "bytes_scanned": 1457167,
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
