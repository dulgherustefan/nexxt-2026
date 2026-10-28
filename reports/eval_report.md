# VersoML evaluation report

Generated: 2026-10-28T23:28:25.286598+00:00 · LLM mode: offline

| Metric | Value | Target |
|---|---|---|
| Rules: refund verdict on the golden set (40) | 100.0% | 100% |
| Rules: verdict on 300 generated cases | 100.0% | 100% |
| Rules: verdict on the typology cases | 100.0% | 100% |
| Correct refund deadlines | 100.0% | 100% |
| Recall of escalations to a person | 100.0% | ≥ 0.95 |
| Non-interference: leaks across the wall | 0 | 0 |
| Non-interference: decisions changed by the AML zone | 0 | 0 |
| Raw personal data sent to the LLM | 0 | 0 |
| Injections detected | 100.0% | 100% |
| Letter check: tipping-off recall | 100.0% | 100% |
| Letter check: clean letters blocked by mistake | 0 | 0 |
| Injections: false alarms on clean complaints | 0.0% | ≈ 0 |
| M1 scenario on held-out templates: macro-F1 | 97.0% | ≥ 0.90 |
| M1 scenario calibration on held-out templates: ECE | 1.2% | ≤ 0.05 |
| M1 scenario, trained on templates, tested on free text | 81.9% | comparison |
| M1 scenario, trained on English, tested on Romanian | 65.5% | comparison |
| M2 client-fraud signal: AUC, temporal split | 88.5% | ≥ 0.80 |
| M5 money mules: AUC, temporal split (ensemble) | 98.7% | ≥ 0.85 |
| M5 money mules: AUC, rules only (baseline) | 75.3% | comparison |
| M5: false alarms on hard negatives | 0.4% | ≈ 0 |
| Knowledge base Recall@5 (bm25) | 78.2% |  |
| Knowledge base Recall@5 (dense) | 89.3% |  |
| Knowledge base Recall@5 (hybrid) | 88.4% | >= 0.80 |
| Knowledge base answers fully cited | 100.0% | 1.0 |
| Free-form intake: right payment on clear cases | 100.0% | >= 0.95 |
| Free-form intake: ambiguous or unknown sent to a person | 100.0% | 1.0 |
| Free-form intake: wrong automatic matches | 0 | 0 |

## Models: old vs new

| Model | Old (split) | New, honest split | New, old-style split |
|---|---|---|---|
| M1 scenario accuracy | 0.993 (a second corpus from the same templates (seed + 1000)) | 0.973 (held-out templates) | 0.993 (random split) |
| M2 AUC | 0.991 (random 75/25 split of the simulator) | 0.885 (temporal, 5% label noise; 0.983 on clean labels) | 0.862 |
| M5 AUC | 0.991 (group CV on one 30-day window (patterns only in the last month)) | 0.987 (temporal, 7-day gap) | 0.995 (group CV, GBDT) |

### M1 scenario accuracy: members vs ensemble

`emb` and `ensemble_full` are measured on the rows that have a cached embedding; `ensemble_served` is what `classify_complaint` returns (the embedding meta-learner only where a vector exists and where it beat the fallback out of fold).

| Split | char | word | cnb | emb | ensemble_fallback | ensemble_full | ensemble_served | n |
|---|---|---|---|---|---|---|---|---|
| held_out_templates | 0.972 | 0.951 | 0.903 | 0.848 | 0.973 | 0.962 | 0.973 | 1580 |
| typo_noise | 0.965 | 0.948 | 0.903 | n/a | 0.975 | n/a | 0.975 | 1580 |
| held_out_llm_batch | 0.920 | 0.918 | 0.911 | 0.833 | 0.928 | 0.933 | 0.933 | 461 |
| cross_lingual_en_to_ro | 0.580 | 0.432 | 0.466 | 0.617 | 0.655 | 0.486 | 0.655 | 2369 |
| templates_to_llm_paraphrases | 0.742 | 0.752 | 0.792 | 0.710 | 0.819 | 0.715 | 0.819 | 1260 |
| hard_negatives | 0.319 | 0.325 | 0.275 | 0.275 | 0.381 | 0.425 | 0.381 | 160 |
| random_split_leaky | 0.986 | 0.975 | 0.939 | n/a | 0.993 | n/a | 0.993 | 805 |

Ambiguity flag on hard negatives: vague or multi-issue complaints flagged 0.475, clear ones flagged 0.050.

### M2 client-fraud signal: members vs ensemble (temporal split)

| Member | AUC | PR-AUC | Brier | AUC on clean labels |
|---|---|---|---|---|
| lgbm | 0.882 | 0.799 | 0.075 | 0.979 |
| lr | 0.879 | 0.791 | 0.082 | 0.976 |
| ensemble | 0.885 | 0.804 | 0.074 | 0.983 |
| iforest (stacked feature only) | 0.771 | | | |

### M5 money mules: baselines, members and ensemble (temporal split)

Train: 30-day windows ending 2026-09-21, 2026-08-22, 2026-07-23; test: 2026-09-28 to 2026-10-28 (7-day gap, 151 active mules among 3403 accounts).

| Model | AUC | PR-AUC | F1 |
|---|---|---|---|
| rules_only | 0.753 | 0.263 | 0.341 |
| gbdt_no_graph | 0.962 | 0.740 | 0.680 |
| gbdt_graph | 0.988 | 0.894 | 0.828 |
| ppr_alone | 0.867 | 0.417 | n/a |
| iforest_alone | 0.742 | 0.153 | n/a |
| ensemble | 0.987 | 0.895 | 0.839 |

Typology hold-out (trained without that typology, tested on its mules in the last window):

| Typology | Mules | Ensemble AUC | Ensemble recall | Rules-only AUC |
|---|---|---|---|---|
| behavioural_change | 3 | 0.999 | 1.000 | 0.879 |
| bipartite | 38 | 0.947 | 0.368 | 0.713 |
| cycle | 3 | 1.000 | 1.000 | 0.711 |
| demo_ring | 1 | 1.000 | 1.000 | 1.000 |
| fan_in | 13 | 1.000 | 1.000 | 0.974 |
| fan_out | 21 | 0.992 | 0.619 | 0.598 |
| gather_scatter | 11 | 1.000 | 1.000 | 0.665 |
| layered_fan_out | 6 | 0.999 | 0.833 | 0.701 |
| random | 15 | 0.999 | 0.933 | 0.841 |
| rapid_pass_through | 8 | 0.987 | 0.500 | 0.909 |
| scatter_gather | 24 | 0.992 | 0.833 | 0.782 |
| smurfing | 4 | 1.000 | 1.000 | 1.000 |
| stack | 4 | 0.997 | 0.750 | 0.354 |

Inference latency (median of repeated calls, warm): M1 4.1 ms, M2 8.5 ms, M5 (demo neighbourhood) 10.7 ms.

Notes: every number is on synthetic data. Methods follow docs/08_cercetare_rag_ml_agenti.md: stacking on out-of-fold predictions (Wolpert 1992; scikit-learn stacking docs), IsolationForest as a stacked feature (Liu, Ting, Zhou 2008), sigmoid / temperature calibration with few positives (Niculescu-Mizil and Caruana 2005), group splits on unseen templates and temporal splits with a gap (ULB fraud-detection handbook, ch. 5), LLM paraphrases added on top of templates, never instead of them (Li et al. 2023; Gerstgrasser et al. 2024), AML typologies after AMLworld (Altman et al. 2023, data at github.com/IBM/AML-Data), PPR as guilt by association (Koutra et al. 2011).

## Knowledge base retrieval

72 labelled queries ({'en': 37, 'ro': 35}), model cohere.embed-v4:0.

| Method | R@1 | R@5 | MRR@10 | nDCG@10 |
|---|---|---|---|---|
| bm25 | 0.472 | 0.782 | 0.666 | 0.691 |
| dense | 0.597 | 0.893 | 0.808 | 0.818 |
| hybrid | 0.583 | 0.884 | 0.800 | 0.816 |
| hybrid_offline | 0.474 | 0.759 | 0.654 | 0.666 |


## Free-form intake (freeform_60)

Clear cases: 36/36 right payment. Ambiguous or unknown: 24/24 sent to a person. Wrong automatic matches: 0.


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
  "ms_per_case": 5.816,
  "failures": []
 },
 "rules_generated": {
  "cases": 300,
  "verdict_accuracy": 1.0,
  "requires_human_accuracy": 1.0,
  "escalation_recall": 1.0,
  "deadline_accuracy": 1.0,
  "recovery_accuracy": 1.0,
  "ms_per_case": 0.662,
  "failures": []
 },
 "rules_typologies": {
  "cases": 25,
  "verdict_accuracy": 1.0,
  "requires_human_accuracy": 1.0,
  "escalation_recall": 1.0,
  "deadline_accuracy": 1.0,
  "recovery_accuracy": 1.0,
  "ms_per_case": 0.506,
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
  "generated_at": "2026-10-29T01:11:25+02:00",
  "seconds_total": 106.36,
  "seconds": {
   "world": 11.31,
   "m2": 55.38,
   "m1": 96.48,
   "m5": 94.75,
   "m6_m7": 0.3
  },
  "m1_classifier": {
   "model_version": "m1-stack-4bad97e8",
   "members": [
    "char",
    "word",
    "cnb",
    "emb"
   ],
   "meta": "multinomial LR on out-of-fold log-probabilities (folds = template phrase groups), temperature-scaled",
   "n_rows": 6160,
   "n_rows_with_embedding": 2288,
   "embedding_member": "available",
   "corpus": {
    "template": 3240,
    "typology": 1500,
    "llm": 1420
   },
   "languages": {
    "en": 3081,
    "ro": 3079
   },
   "temperature": {
    "channel": {
     "fallback": 0.794,
     "full": 0.794
    },
    "dispute_type": {
     "fallback": 0.708,
     "full": 0.708
    },
    "scenario": {
     "fallback": 0.562,
     "full": 0.501
    }
   },
   "embedding_meta_served": {
    "channel": true,
    "dispute_type": true,
    "scenario": true
   },
   "embedding_meta_oof": {
    "channel": {
     "full": 0.9677,
     "fallback_same_rows": 0.9628
    },
    "dispute_type": {
     "full": 0.976,
     "fallback_same_rows": 0.9642
    },
    "scenario": {
     "full": 0.9567,
     "fallback_same_rows": 0.9493
    }
   },
   "eval_only_rows": 80,
   "honest": {
    "held_out_templates": {
     "train": "template groups 0+1 (EN+RO, typologies) + LLM batches 0+1, out-of-fold on group 0 vs 1",
     "test": "template group 2: phrase variants never seen in training",
     "channel": {
      "char": {
       "accuracy": 0.938,
       "macro_f1": 0.9287,
       "ece": 0.0964,
       "n": 1580
      },
      "word": {
       "accuracy": 0.9652,
       "macro_f1": 0.966,
       "ece": 0.0722,
       "n": 1580
      },
      "cnb": {
       "accuracy": 0.9563,
       "macro_f1": 0.9593,
       "ece": 0.011,
       "n": 1580
      },
      "ensemble_fallback": {
       "accuracy": 0.9759,
       "macro_f1": 0.9788,
       "ece": 0.0143,
       "n": 1580
      },
      "emb": {
       "accuracy": 0.931,
       "macro_f1": 0.9194,
       "ece": 0.0515,
       "n": 290
      },
      "fallback_same_rows": {
       "accuracy": 0.9552,
       "macro_f1": 0.9571,
       "ece": 0.0366,
       "n": 290
      },
      "ensemble_full": {
       "accuracy": 0.9552,
       "macro_f1": 0.9664,
       "ece": 0.039,
       "n": 290
      },
      "ensemble_served": {
       "accuracy": 0.9759,
       "macro_f1": 0.9797,
       "ece": 0.0159,
       "n": 1580
      },
      "best_text_member": "word"
     },
     "dispute_type": {
      "char": {
       "accuracy": 0.9905,
       "macro_f1": 0.9887,
       "ece": 0.0738,
       "n": 1580
      },
      "word": {
       "accuracy": 0.9886,
       "macro_f1": 0.9912,
       "ece": 0.0886,
       "n": 1580
      },
      "cnb": {
       "accuracy": 0.9968,
       "macro_f1": 0.9963,
       "ece": 0.0556,
       "n": 1580
      },
      "ensemble_fallback": {
       "accuracy": 0.9949,
       "macro_f1": 0.9935,
       "ece": 0.0039,
       "n": 1580
      },
      "emb": {
       "accuracy": 0.9828,
       "macro_f1": 0.9709,
       "ece": 0.1157,
       "n": 290
      },
      "fallback_same_rows": {
       "accuracy": 0.9966,
       "macro_f1": 0.9944,
       "ece": 0.0077,
       "n": 290
      },
      "ensemble_full": {
       "accuracy": 0.9966,
       "macro_f1": 0.9949,
       "ece": 0.003,
       "n": 290
      },
      "ensemble_served": {
       "accuracy": 0.9949,
       "macro_f1": 0.9935,
       "ece": 0.0035,
       "n": 1580
      },
      "best_text_member": "cnb"
     },
     "scenario": {
      "char": {
       "accuracy": 0.9715,
       "macro_f1": 0.9698,
       "ece": 0.2011,
       "n": 1580
      },
      "word": {
       "accuracy": 0.9513,
       "macro_f1": 0.9476,
       "ece": 0.2549,
       "n": 1580
      },
      "cnb": {
       "accuracy": 0.9032,
       "macro_f1": 0.8825,
       "ece": 0.1827,
       "n": 1580
      },
      "ensemble_fallback": {
       "accuracy": 0.9734,
       "macro_f1": 0.9704,
       "ece": 0.0111,
       "n": 1580
      },
      "emb": {
       "accuracy": 0.8483,
       "macro_f1": 0.8346,
       "ece": 0.2957,
       "n": 290
      },
      "fallback_same_rows": {
       "accuracy": 0.9655,
       "macro_f1": 0.9652,
       "ece": 0.0142,
       "n": 290
      },
      "ensemble_full": {
       "accuracy": 0.9621,
       "macro_f1": 0.9616,
       "ece": 0.0186,
       "n": 290
      },
      "ensemble_served": {
       "accuracy": 0.9728,
       "macro_f1": 0.9696,
       "ece": 0.0119,
       "n": 1580
      },
      "best_text_member": "char"
     }
    },
    "typo_noise": {
     "test": "held-out group 2, diacritics stripped and 12% of words with a typo",
     "scenario": {
      "char": {
       "accuracy": 0.9652,
       "macro_f1": 0.9626,
       "ece": 0.2164,
       "n": 1580
      },
      "word": {
       "accuracy": 0.9475,
       "macro_f1": 0.9437,
       "ece": 0.2703,
       "n": 1580
      },
      "cnb": {
       "accuracy": 0.9032,
       "macro_f1": 0.8816,
       "ece": 0.2057,
       "n": 1580
      },
      "ensemble_fallback": {
       "accuracy": 0.9753,
       "macro_f1": 0.9719,
       "ece": 0.0077,
       "n": 1580
      },
      "ensemble_served": {
       "accuracy": 0.9753,
       "macro_f1": 0.9719,
       "ece": 0.0077,
       "n": 1580
      },
      "best_text_member": "char"
     }
    },
    "held_out_llm_batch": {
     "test": "LLM paraphrases of batch 2 (other writers)",
     "channel": {
      "char": {
       "accuracy": 0.7874,
       "macro_f1": 0.6992,
       "ece": 0.0931,
       "n": 461
      },
      "word": {
       "accuracy": 0.8829,
       "macro_f1": 0.8624,
       "ece": 0.1075,
       "n": 461
      },
      "cnb": {
       "accuracy": 0.9349,
       "macro_f1": 0.9374,
       "ece": 0.0742,
       "n": 461
      },
      "ensemble_fallback": {
       "accuracy": 0.9349,
       "macro_f1": 0.9394,
       "ece": 0.0254,
       "n": 461
      },
      "emb": {
       "accuracy": 0.8221,
       "macro_f1": 0.7796,
       "ece": 0.0651,
       "n": 461
      },
      "fallback_same_rows": {
       "accuracy": 0.9349,
       "macro_f1": 0.9394,
       "ece": 0.0254,
       "n": 461
      },
      "ensemble_full": {
       "accuracy": 0.9436,
       "macro_f1": 0.9476,
       "ece": 0.0409,
       "n": 461
      },
      "ensemble_served": {
       "accuracy": 0.9436,
       "macro_f1": 0.9476,
       "ece": 0.0409,
       "n": 461
      },
      "best_text_member": "cnb"
     },
     "dispute_type": {
      "char": {
       "accuracy": 0.9696,
       "macro_f1": 0.9482,
       "ece": 0.1203,
       "n": 461
      },
      "word": {
       "accuracy": 0.9718,
       "macro_f1": 0.9457,
       "ece": 0.1415,
       "n": 461
      },
      "cnb": {
       "accuracy": 0.974,
       "macro_f1": 0.9515,
       "ece": 0.1594,
       "n": 461
      },
      "ensemble_fallback": {
       "accuracy": 0.9761,
       "macro_f1": 0.9463,
       "ece": 0.0132,
       "n": 461
      },
      "emb": {
       "accuracy": 0.9761,
       "macro_f1": 0.972,
       "ece": 0.1039,
       "n": 461
      },
      "fallback_same_rows": {
       "accuracy": 0.9761,
       "macro_f1": 0.9463,
       "ece": 0.0132,
       "n": 461
      },
      "ensemble_full": {
       "accuracy": 0.987,
       "macro_f1": 0.9803,
       "ece": 0.0092,
       "n": 461
      },
      "ensemble_served": {
       "accuracy": 0.987,
       "macro_f1": 0.9803,
       "ece": 0.0092,
       "n": 461
      },
      "best_text_member": "cnb"
     },
     "scenario": {
      "char": {
       "accuracy": 0.9197,
       "macro_f1": 0.9086,
       "ece": 0.3457,
       "n": 461
      },
      "word": {
       "accuracy": 0.9176,
       "macro_f1": 0.9038,
       "ece": 0.4124,
       "n": 461
      },
      "cnb": {
       "accuracy": 0.9111,
       "macro_f1": 0.8949,
       "ece": 0.497,
       "n": 461
      },
      "ensemble_fallback": {
       "accuracy": 0.9284,
       "macro_f1": 0.9123,
       "ece": 0.0289,
       "n": 461
      },
      "emb": {
       "accuracy": 0.833,
       "macro_f1": 0.8378,
       "ece": 0.2384,
       "n": 461
      },
      "fallback_same_rows": {
       "accuracy": 0.9284,
       "macro_f1": 0.9123,
       "ece": 0.0289,
       "n": 461
      },
      "ensemble_full": {
       "accuracy": 0.9328,
       "macro_f1": 0.9184,
       "ece": 0.0519,
       "n": 461
      },
      "ensemble_served": {
       "accuracy": 0.9328,
       "macro_f1": 0.9184,
       "ece": 0.0519,
       "n": 461
      },
      "best_text_member": "char"
     }
    },
    "cross_lingual_en_to_ro": {
     "train": "English templates only",
     "test": "Romanian templates and LLM paraphrases",
     "scenario": {
      "char": {
       "accuracy": 0.5804,
       "macro_f1": 0.5738,
       "ece": 0.2819,
       "n": 2369
      },
      "word": {
       "accuracy": 0.4318,
       "macro_f1": 0.4309,
       "ece": 0.1293,
       "n": 2369
      },
      "cnb": {
       "accuracy": 0.4664,
       "macro_f1": 0.4453,
       "ece": 0.1404,
       "n": 2369
      },
      "ensemble_fallback": {
       "accuracy": 0.6551,
       "macro_f1": 0.6391,
       "ece": 0.0762,
       "n": 2369
      },
      "emb": {
       "accuracy": 0.6173,
       "macro_f1": 0.6375,
       "ece": 0.3132,
       "n": 1181
      },
      "fallback_same_rows": {
       "accuracy": 0.5385,
       "macro_f1": 0.5187,
       "ece": 0.129,
       "n": 1181
      },
      "ensemble_full": {
       "accuracy": 0.486,
       "macro_f1": 0.4751,
       "ece": 0.1873,
       "n": 1181
      },
      "ensemble_served": {
       "accuracy": 0.6551,
       "macro_f1": 0.6391,
       "ece": 0.0762,
       "n": 2369
      },
      "best_text_member": "char"
     }
    },
    "templates_to_llm_paraphrases": {
     "train": "templates only (EN+RO, typologies)",
     "test": "LLM paraphrases and typology complaints, EN+RO",
     "scenario": {
      "char": {
       "accuracy": 0.7421,
       "macro_f1": 0.707,
       "ece": 0.2845,
       "n": 1260
      },
      "word": {
       "accuracy": 0.7516,
       "macro_f1": 0.7004,
       "ece": 0.3487,
       "n": 1260
      },
      "cnb": {
       "accuracy": 0.7921,
       "macro_f1": 0.7753,
       "ece": 0.3331,
       "n": 1260
      },
      "ensemble_fallback": {
       "accuracy": 0.819,
       "macro_f1": 0.7818,
       "ece": 0.0829,
       "n": 1260
      },
      "emb": {
       "accuracy": 0.7103,
       "macro_f1": 0.7171,
       "ece": 0.2912,
       "n": 1260
      },
      "fallback_same_rows": {
       "accuracy": 0.819,
       "macro_f1": 0.7818,
       "ece": 0.0829,
       "n": 1260
      },
      "ensemble_full": {
       "accuracy": 0.7151,
       "macro_f1": 0.6802,
       "ece": 0.1639,
       "n": 1260
      },
      "ensemble_served": {
       "accuracy": 0.819,
       "macro_f1": 0.7818,
       "ece": 0.0829,
       "n": 1260
      },
      "best_text_member": "cnb"
     }
    },
    "hard_negatives": {
     "model": "templates-only model (scenario, on changed-mind, subscription, processing-error and friendly-fraud texts); held-out model (ambiguity flag, text only)",
     "scenario": {
      "char": {
       "accuracy": 0.3187,
       "macro_f1": 0.4275,
       "ece": 0.0675,
       "n": 160
      },
      "word": {
       "accuracy": 0.325,
       "macro_f1": 0.4445,
       "ece": 0.0978,
       "n": 160
      },
      "cnb": {
       "accuracy": 0.275,
       "macro_f1": 0.3761,
       "ece": 0.071,
       "n": 160
      },
      "ensemble_fallback": {
       "accuracy": 0.3812,
       "macro_f1": 0.448,
       "ece": 0.329,
       "n": 160
      },
      "emb": {
       "accuracy": 0.275,
       "macro_f1": 0.3766,
       "ece": 0.095,
       "n": 160
      },
      "fallback_same_rows": {
       "accuracy": 0.3812,
       "macro_f1": 0.448,
       "ece": 0.329,
       "n": 160
      },
      "ensemble_full": {
       "accuracy": 0.425,
       "macro_f1": 0.4936,
       "ece": 0.3012,
       "n": 160
      },
      "ensemble_served": {
       "accuracy": 0.3812,
       "macro_f1": 0.448,
       "ece": 0.329,
       "n": 160
      },
      "best_text_member": "word"
     },
     "ambiguity": {
      "vague_or_multi_issue_flagged": 0.475,
      "clear_hard_negatives_flagged": 0.05
     }
    },
    "random_split_leaky": {
     "note": "random 75/25 split of template rows: test texts share templates with training texts (what the old 0.99 measured)",
     "scenario": {
      "char": {
       "accuracy": 0.9863,
       "macro_f1": 0.9863,
       "ece": 0.0906,
       "n": 805
      },
      "word": {
       "accuracy": 0.9752,
       "macro_f1": 0.9744,
       "ece": 0.0828,
       "n": 805
      },
      "cnb": {
       "accuracy": 0.9391,
       "macro_f1": 0.9292,
       "ece": 0.0462,
       "n": 805
      },
      "ensemble_fallback": {
       "accuracy": 0.9925,
       "macro_f1": 0.9925,
       "ece": 0.006,
       "n": 805
      },
      "ensemble_served": {
       "accuracy": 0.9925,
       "macro_f1": 0.9925,
       "ece": 0.006,
       "n": 805
      },
      "best_text_member": "char"
     }
    }
   },
   "channel": {
    "accuracy": 0.9759,
    "macro_f1": 0.9797,
    "ece": 0.0159,
    "n": 1580,
    "classes": [
     "card",
     "transfer",
     "transfer_instant"
    ]
   },
   "dispute_type": {
    "accuracy": 0.9949,
    "macro_f1": 0.9935,
    "ece": 0.0035,
    "n": 1580,
    "classes": [
     "app",
     "disputa_comerciant",
     "eroare_procesare",
     "neautorizata"
    ]
   },
   "scenario": {
    "accuracy": 0.9728,
    "macro_f1": 0.9696,
    "ece": 0.0119,
    "n": 1580,
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
   "accuracy_text_only": {
    "scenario": 0.9753
   },
   "seconds": 96.5
  },
  "m2_client_fraud": {
   "held_out": {
    "auc": 0.8847,
    "pr_auc": 0.804,
    "f1": 0.7715,
    "precision": 0.8464,
    "recall": 0.7088,
    "threshold": 0.5,
    "n": 2134,
    "positives": 443,
    "auc_clean_labels": 0.9826,
    "brier": 0.0745
   },
   "temporal_split": {
    "lgbm": {
     "auc": 0.8816,
     "pr_auc": 0.7987,
     "f1": 0.7653,
     "precision": 0.8347,
     "recall": 0.7065,
     "threshold": 0.5,
     "n": 2134,
     "positives": 443,
     "auc_clean_labels": 0.979,
     "brier": 0.0752
    },
    "lr": {
     "auc": 0.8793,
     "pr_auc": 0.7911,
     "f1": 0.7408,
     "precision": 0.842,
     "recall": 0.6614,
     "threshold": 0.5,
     "n": 2134,
     "positives": 443,
     "auc_clean_labels": 0.9758,
     "brier": 0.0817
    },
    "ensemble": {
     "auc": 0.8847,
     "pr_auc": 0.804,
     "f1": 0.7715,
     "precision": 0.8464,
     "recall": 0.7088,
     "threshold": 0.5,
     "n": 2134,
     "positives": 443,
     "auc_clean_labels": 0.9826,
     "brier": 0.0745
    },
    "iforest_alone": {
     "auc": 0.7713,
     "note": "unsupervised anomaly score; used only as a stacked feature"
    }
   },
   "split": "temporal: train on simulated days 0-270, test on days 270-365 (drift: more 'stolen phone' friendly fraud and more remote-access victims later)",
   "label_noise": 0.05,
   "random_split_old_style": {
    "lgbm": 0.8592,
    "lr": 0.8594,
    "ensemble": 0.8622
   },
   "brier": 0.0745,
   "n_train": 5866,
   "n_test": 2134,
   "fraud_rate": 0.205,
   "model_version": "m2-stack-ff65aeb8",
   "meta": "logistic regression on out-of-fold [logit LightGBM, logit LR, IsolationForest anomaly]",
   "note": "a signal for a person; overlapping synthetic distributions with label noise, not real data"
  },
  "m5_mule": {
   "temporal_split": {
    "rules_only": {
     "auc": 0.7527,
     "pr_auc": 0.2628,
     "f1": 0.341,
     "precision": 0.5606,
     "recall": 0.245,
     "threshold": 0.5,
     "n": 3403,
     "positives": 151
    },
    "gbdt_no_graph": {
     "auc": 0.9622,
     "pr_auc": 0.7403,
     "f1": 0.6798,
     "precision": 0.8431,
     "recall": 0.5695,
     "threshold": 0.5,
     "n": 3403,
     "positives": 151
    },
    "gbdt_graph": {
     "auc": 0.9878,
     "pr_auc": 0.8943,
     "f1": 0.8283,
     "precision": 0.8425,
     "recall": 0.8146,
     "threshold": 0.0826,
     "n": 3403,
     "positives": 151
    },
    "ensemble": {
     "auc": 0.9873,
     "pr_auc": 0.8946,
     "f1": 0.8394,
     "precision": 0.935,
     "recall": 0.7616,
     "threshold": 0.4816,
     "n": 3403,
     "positives": 151,
     "threshold_from": "best F1 on the training snapshots (out-of-fold)"
    },
    "ppr_alone": {
     "auc": 0.8668,
     "pr_auc": 0.417
    },
    "iforest_alone": {
     "auc": 0.7423,
     "pr_auc": 0.1528
    },
    "train_snapshots_as_of": [
     "2026-09-21T10:00:00+03:00",
     "2026-08-22T10:00:00+03:00",
     "2026-07-23T10:00:00+03:00"
    ],
    "test_window": [
     "2026-09-28T10:00:00+03:00",
     "2026-10-28T10:00:00+02:00"
    ],
    "label_delay_days": 7,
    "max_train_flow_ts": "2026-09-21T09:59:20+03:00",
    "n_train": 9692,
    "n_test": 3403,
    "test_mules": 151,
    "false_positive_rate_hard_negatives": 0.0039
   },
   "typology_holdout": {
    "behavioural_change": {
     "positives": 3,
     "ensemble_auc": 0.9992,
     "ensemble_recall_at_thr": 1.0,
     "rules_only_auc": 0.879,
     "rules_only_recall_at_0.5": 0.3333
    },
    "bipartite": {
     "positives": 38,
     "ensemble_auc": 0.9469,
     "ensemble_recall_at_thr": 0.3684,
     "rules_only_auc": 0.7129,
     "rules_only_recall_at_0.5": 0.1053
    },
    "cycle": {
     "positives": 3,
     "ensemble_auc": 1.0,
     "ensemble_recall_at_thr": 1.0,
     "rules_only_auc": 0.711,
     "rules_only_recall_at_0.5": 0.0
    },
    "demo_ring": {
     "positives": 1,
     "ensemble_auc": 1.0,
     "ensemble_recall_at_thr": 1.0,
     "rules_only_auc": 0.9997,
     "rules_only_recall_at_0.5": 1.0
    },
    "fan_in": {
     "positives": 13,
     "ensemble_auc": 0.9999,
     "ensemble_recall_at_thr": 1.0,
     "rules_only_auc": 0.9744,
     "rules_only_recall_at_0.5": 0.9231
    },
    "fan_out": {
     "positives": 21,
     "ensemble_auc": 0.9923,
     "ensemble_recall_at_thr": 0.619,
     "rules_only_auc": 0.5975,
     "rules_only_recall_at_0.5": 0.0952
    },
    "gather_scatter": {
     "positives": 11,
     "ensemble_auc": 0.9996,
     "ensemble_recall_at_thr": 1.0,
     "rules_only_auc": 0.6655,
     "rules_only_recall_at_0.5": 0.1818
    },
    "layered_fan_out": {
     "positives": 6,
     "ensemble_auc": 0.9988,
     "ensemble_recall_at_thr": 0.8333,
     "rules_only_auc": 0.7014,
     "rules_only_recall_at_0.5": 0.0
    },
    "random": {
     "positives": 15,
     "ensemble_auc": 0.999,
     "ensemble_recall_at_thr": 0.9333,
     "rules_only_auc": 0.8409,
     "rules_only_recall_at_0.5": 0.2
    },
    "rapid_pass_through": {
     "positives": 8,
     "ensemble_auc": 0.9872,
     "ensemble_recall_at_thr": 0.5,
     "rules_only_auc": 0.9087,
     "rules_only_recall_at_0.5": 0.5
    },
    "scatter_gather": {
     "positives": 24,
     "ensemble_auc": 0.9916,
     "ensemble_recall_at_thr": 0.8333,
     "rules_only_auc": 0.7817,
     "rules_only_recall_at_0.5": 0.1667
    },
    "smurfing": {
     "positives": 4,
     "ensemble_auc": 1.0,
     "ensemble_recall_at_thr": 1.0,
     "rules_only_auc": 0.9998,
     "rules_only_recall_at_0.5": 1.0
    },
    "stack": {
     "positives": 4,
     "ensemble_auc": 0.9973,
     "ensemble_recall_at_thr": 0.75,
     "rules_only_auc": 0.3541,
     "rules_only_recall_at_0.5": 0.0
    }
   },
   "rules_only": {
    "auc": 0.7383,
    "pr_auc": 0.2466,
    "f1": 0.3201,
    "precision": 0.6278,
    "recall": 0.2148,
    "threshold": 0.5,
    "n": 13095,
    "positives": 526
   },
   "gbdt_no_graph": {
    "auc": 0.9762,
    "pr_auc": 0.8075,
    "f1": 0.7363,
    "precision": 0.8486,
    "recall": 0.6502,
    "threshold": 0.3446,
    "n": 13095,
    "positives": 526
   },
   "gbdt_graph": {
    "auc": 0.995,
    "pr_auc": 0.9557,
    "f1": 0.9141,
    "precision": 0.9507,
    "recall": 0.8802,
    "threshold": 0.2335,
    "n": 13095,
    "positives": 526
   },
   "gbdt_graph_at_0.5": {
    "auc": 0.995,
    "pr_auc": 0.9557,
    "f1": 0.87,
    "precision": 0.9696,
    "recall": 0.789,
    "threshold": 0.5,
    "n": 13095,
    "positives": 526
   },
   "ensemble": {
    "auc": 0.9873,
    "pr_auc": 0.8946,
    "f1": 0.8394,
    "precision": 0.935,
    "recall": 0.7616,
    "threshold": 0.4816,
    "n": 3403,
    "positives": 151,
    "threshold_from": "best F1 on the training snapshots (out-of-fold)"
   },
   "cv": "StratifiedGroupKFold(5), grupuri = tiparul de spălare (cărăușii aceluiași tipar stau în același fold); 4 instantanee de 30 de zile",
   "window_days": 30,
   "n_accounts": 13095,
   "mule_rate": 0.0402,
   "false_positive_rate_hard_negatives": 0.0039,
   "model_version": "m5-stack-graph-e828b06a",
   "meta_inputs": [
    "logit(GBDT on own + graph features)",
    "log1p(100 x personalized PageRank from reported accounts)",
    "IsolationForest anomaly on own features",
    "rules-only score"
   ],
   "meta_coef": [
    1.0417,
    0.2225,
    0.461,
    0.079
   ],
   "note": "PPR seeds = accounts with incoming payments reported as fraud in the window (an observable fact); ground-truth labels never reach the features"
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
   "decide": "oracle.expected_outcome (the table shared with the rules engine)",
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
  "note": "Every metric is on synthetic data; on real data they will be lower.",
  "_latency_ms": {
   "M1": 4.1,
   "M2": 8.5,
   "M5 (demo neighbourhood)": 10.7
  }
 },
 "data": {
  "freeform_60": {
   "lines": 60,
   "by_category": {
    "clear": 36,
    "ambiguous": 12,
    "no_match": 4,
    "unknown_customer": 8
   },
   "by_language": {
    "ro": 30,
    "en": 30
   }
  },
  "llm_corpus": {
   "rows": 1500,
   "by_kind": {
    "paraphrase": 855,
    "hard_negative": 240,
    "typology": 405
   },
   "by_language": {
    "en": 751,
    "ro": 749
   },
   "scrubbed_rows": 41
  }
 },
 "noninterference": {
  "at": "2026-10-28T23:28:21.126252+00:00",
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
  "bytes_scanned": 3311799,
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
 },
 "retrieval": {
  "queries": 72,
  "by_lang": {
   "en": 37,
   "ro": 35
  },
  "embedding_model": "cohere.embed-v4:0",
  "dense_query_vectors_missing": 0,
  "methods": {
   "bm25": {
    "recall@1": 0.4722,
    "hit@1": 0.5556,
    "recall@3": 0.6898,
    "hit@3": 0.7639,
    "recall@5": 0.7824,
    "hit@5": 0.8194,
    "mrr@10": 0.666,
    "ndcg@10": 0.691
   },
   "dense": {
    "recall@1": 0.5972,
    "hit@1": 0.7083,
    "recall@3": 0.7917,
    "hit@3": 0.875,
    "recall@5": 0.8935,
    "hit@5": 0.9306,
    "mrr@10": 0.8078,
    "ndcg@10": 0.8176
   },
   "hybrid": {
    "recall@1": 0.5833,
    "hit@1": 0.6944,
    "recall@3": 0.8403,
    "hit@3": 0.9028,
    "recall@5": 0.8843,
    "hit@5": 0.9306,
    "mrr@10": 0.8004,
    "ndcg@10": 0.8164
   },
   "hybrid_offline": {
    "recall@1": 0.4745,
    "hit@1": 0.5694,
    "recall@3": 0.6366,
    "hit@3": 0.7222,
    "recall@5": 0.7593,
    "hit@5": 0.7917,
    "mrr@10": 0.6537,
    "ndcg@10": 0.6661
   }
  },
  "methods_by_lang": {
   "en": {
    "bm25": {
     "recall@1": 0.4865,
     "hit@1": 0.5676,
     "recall@3": 0.6757,
     "hit@3": 0.7297,
     "recall@5": 0.7297,
     "hit@5": 0.7568,
     "mrr@10": 0.6541,
     "ndcg@10": 0.6671
    },
    "dense": {
     "recall@1": 0.6216,
     "hit@1": 0.7297,
     "recall@3": 0.8243,
     "hit@3": 0.8919,
     "recall@5": 0.8919,
     "hit@5": 0.9189,
     "mrr@10": 0.8192,
     "ndcg@10": 0.8193
    },
    "hybrid": {
     "recall@1": 0.5946,
     "hit@1": 0.7027,
     "recall@3": 0.8649,
     "hit@3": 0.8919,
     "recall@5": 0.8784,
     "hit@5": 0.9189,
     "mrr@10": 0.7915,
     "ndcg@10": 0.8056
    },
    "hybrid_offline": {
     "recall@1": 0.4324,
     "hit@1": 0.5405,
     "recall@3": 0.5541,
     "hit@3": 0.6216,
     "recall@5": 0.6486,
     "hit@5": 0.6757,
     "mrr@10": 0.5955,
     "ndcg@10": 0.5933
    }
   },
   "ro": {
    "bm25": {
     "recall@1": 0.4571,
     "hit@1": 0.5429,
     "recall@3": 0.7048,
     "hit@3": 0.8,
     "recall@5": 0.8381,
     "hit@5": 0.8857,
     "mrr@10": 0.6786,
     "ndcg@10": 0.7163
    },
    "dense": {
     "recall@1": 0.5714,
     "hit@1": 0.6857,
     "recall@3": 0.7571,
     "hit@3": 0.8571,
     "recall@5": 0.8952,
     "hit@5": 0.9429,
     "mrr@10": 0.7957,
     "ndcg@10": 0.8158
    },
    "hybrid": {
     "recall@1": 0.5714,
     "hit@1": 0.6857,
     "recall@3": 0.8143,
     "hit@3": 0.9143,
     "recall@5": 0.8905,
     "hit@5": 0.9429,
     "mrr@10": 0.8098,
     "ndcg@10": 0.8279
    },
    "hybrid_offline": {
     "recall@1": 0.519,
     "hit@1": 0.6,
     "recall@3": 0.7238,
     "hit@3": 0.8286,
     "recall@5": 0.8762,
     "hit@5": 0.9143,
     "mrr@10": 0.7152,
     "ndcg@10": 0.743
    }
   }
  },
  "kb": {
   "zone": "client",
   "chunks": 800,
   "by_kind": {
    "case_study": 19,
    "guidance": 136,
    "law": 163,
    "precedent": 366,
    "rule": 66,
    "typology": 50
   },
   "embedding_model": "cohere.embed-v4:0",
   "embedding_dim": 1536,
   "dense_available": true,
   "dense_coverage": 1.0,
   "live_embeddings": false,
   "built_at": "2026-10-28T23:23:40+00:00",
   "stale": false,
   "precedents": {
    "static": 365,
    "runtime": 1
   },
   "load_ms": 737,
   "signals": [
    "bm25",
    "dense",
    "rrf"
   ]
  },
  "seconds": 1.37,
  "query_ms_p50": 13.2,
  "target_hybrid_ge_single_recall@5": false,
  "grounding": {
   "questions": 15,
   "citation_precision": 0.5349,
   "grounded_rate": 1.0,
   "answered_rate": 1.0,
   "markers_valid_rate": 1.0,
   "details": [
    {
     "id": "q01",
     "grounded": true,
     "citations": [
      "rule:PAY-03",
      "ctx:11_reguli_kyc_aml_credit_plati_reclamatii#4-2-cerere-de-rambursare-pentru-o-tranzactie-neautorizata",
      "rule:PAY-01"
     ],
     "relevant": 1,
     "mode": "offline"
    },
    {
     "id": "q02",
     "grounded": true,
     "citations": [
      "rule:PAY-15",
      "ctx:11_reguli_kyc_aml_credit_plati_reclamatii#2-5-plati-fraude-psd2-pay-xx-6",
      "rule:PAY-06"
     ],
     "relevant": 2,
     "mode": "offline"
    },
    {
     "id": "q03",
     "grounded": true,
     "citations": [
      "rule:PAY-05",
      "ctx:14_dispute_card_fraude#3-cadrul-legal-5",
      "rule:PAY-04"
     ],
     "relevant": 2,
     "mode": "offline"
    },
    {
     "id": "q04",
     "grounded": true,
     "citations": [
      "rule:DSP-25",
      "rule:PAY-01",
      "rule:PAY-03"
     ],
     "relevant": 1,
     "mode": "offline"
    },
    {
     "id": "q05",
     "grounded": true,
     "citations": [
      "rule:PAY-02",
      "ctx:14_dispute_card_fraude#3-cadrul-legal-3",
      "rule:DSP-50"
     ],
     "relevant": 2,
     "mode": "offline"
    },
    {
     "id": "q08",
     "grounded": true,
     "citations": [
      "rule:CMP-01",
      "ctx:11_reguli_kyc_aml_credit_plati_reclamatii#2-6-reclamatii-cmp-xx"
     ],
     "relevant": 2,
     "mode": "offline"
    },
    {
     "id": "q10",
     "grounded": true,
     "citations": [
      "rule:DSP-54",
      "rule:PAY-03",

```
