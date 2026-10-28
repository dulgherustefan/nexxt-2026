"""Modelele ML ale VersoML (docs/05 §8, docs/06 §4.2). ML-ul produce scoruri și semnale; deciziile rămân la
motorul de reguli și la om.

- M1 `m1_classifier.classify_complaint`: tipul și scenariul contestației (TF-IDF + regresie logistică calibrată).
- M2 `m2_client_fraud.client_fraud_signal`: semnal de fraudă a clientului (LightGBM pe fapte obiective).
- M5 `m5_mule.score_accounts / communities / detect_typologies`: conturi-cărăuș în graful AML.
- M6 `m6_entity_resolution.link_cases`: legarea cazurilor între ele.
- M7 `m7_counterfactual.counterfactual`: robustețea unei decizii la schimbarea câte unui fapt.
- `train.train_all()`: antrenează tot și scrie metricile în `models_dir/metrics.json`.
"""
