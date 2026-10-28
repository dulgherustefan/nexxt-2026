# Making a multi-agent dispute/AML decision system accurate, testable and demonstrable (state as of 28 Oct 2026)

Prepared for NEXXT Summit 2026, Raiffeisen track "AI for Operational Efficiency". Jury weights: agent design and orchestration 25%, functional completeness and testability 20%, architecture and reproducibility 15%.

Conventions: "[unverified]" means no source fetched in this session confirmed the item. "[not re-fetched]" means a well-known paper cited from background knowledge with an arXiv ID I am confident of, but not opened in this session. "Inference" bullets are my reasoning, not source claims.

## 1. Does multi-agent debate improve accuracy and calibration? Critiques, best designs, and the two courtroom papers

### Takeaway
The 2025–2026 evidence says plain multi-agent debate (MAD) usually does not beat cheap baselines such as majority voting, self-consistency or CoT, and it can make answers worse through sycophantic capitulation. The measurable gains come from three additions: retrieving evidence during the debate, mixing different model families, and structured checks (judge panels, role-switching). Those gains cost about 11–14× more tokens. For a bank jury, present the debate as a way to cover the evidence from both sides and leave an audit trail, let deterministic rules make the decision, and show a measured comparison against a single-agent-plus-vote baseline.

### Cited Findings
**Critiques (2025–2026)**
- "Debate or Vote" (Choi, Zhu, Li; NeurIPS 2025 poster). Across 7 NLP benchmarks, majority voting over the agents' first answers accounts for most of the gain usually credited to MAD. The authors model debate as a stochastic process and prove that each agent's belief in the correct answer is a martingale, so debate alone does not raise expected correctness. Biasing belief updates toward correction can help. Code: github.com/deeplearning-wisc/debate-or-vote. — [arXiv 2508.17536](https://arxiv.org/abs/2508.17536v1); [NeurIPS 2025 poster](https://neurips.cc/virtual/2025/poster/116557)
- Zhang, Cui et al. first posted this as "If Multi-Agent Debate is the Answer, What is the Question?". v3 is retitled "Stop Overvaluing Multi-Agent Debate — We Must Rethink Evaluation and Embrace Model Heterogeneity".
  - MAD does not reliably beat CoT or Self-Consistency, even with extra inference compute.
  - Model heterogeneity (Heter-MAD, where an agent draws on outputs from different foundation models) consistently improves existing debate frameworks.
  - Models tested: gpt-4o-mini, claude-3.5-haiku, Llama3.1 8B and 70B.
  - — [arXiv 2502.08788 v3](https://arxiv.org/html/2502.08788v3); [v2 abstract](https://arxiv.org/abs/2502.08788v2)
- "Talk Isn't Always Cheap" (Wynn, Satija, Hadfield; 2025; listed on the ICML 2025 virtual site). Debate can lower accuracy over time, even when stronger models outnumber weaker ones. The main mechanism is capitulation: agents switch from correct to incorrect answers when peers push back. It can hurt particularly in heterogeneous groups. — [arXiv 2509.05396](https://arxiv.org/html/2509.05396v2); [ICML listing](https://icml.cc/virtual/2025/49332)
- "Peacemaker or Troublemaker" (Yao et al., 2025).
  - Inter-agent sycophancy causes disagreement collapse before agents reach the correct answer, giving lower accuracy than single-agent baselines.
  - Homogeneous Llama3.3-70B in a decentralized debate had a disagreement-collapse rate up to 86.36% (2 agents, CommonsenseQA) and no gain over a single agent.
  - Heterogeneous agent composition mitigates the collapse. The authors propose persona-based sycophancy control.
  - — [arXiv 2509.23055](https://arxiv.org/pdf/2509.23055)
- Sources disagree on heterogeneity. Zhang et al. and Yao et al. find that mixing models helps; Wynn et al. find it can hurt. — sources above.
- A 2026 paper, "The Cost of Consensus", reportedly splits debate failure into sycophantic conformity (agents adopt the majority answer up to 85.5% of the time), contextual fragility and a third pathway. I saw it only through an aggregator [unverified]. — [aggregator listing](https://awesomepapers.io/papers/bertalanivc2026the)
- Cognition's "Don't Build Multi-Agents" (June 2025) critiques multi-agent architectures: parallel sub-agents that don't share full context make conflicting implicit decisions [not re-fetched]. — [Cognition blog](https://cognition.ai/blog/dont-build-multi-agents)

**AgenticSimLaw (arXiv 2601.21936; Chun, Elkins, Lee; 29 Jan 2026; preprint, 18 pages)**
- Protocol: prosecutor, defense and judge roles in a 7-turn structured debate:
  1. Prosecutor opening.
  2. Defense opening.
  3. Judge's private belief update: YES/NO, 0–100% confidence, reasoning.
  4. Prosecutor rebuttal.
  5. Defense rebuttal.
  6. Judge's private mid-debate update.
  7. Closings, then the judge's final verdict.

  Each agent plans privately before speaking publicly. Full transcripts are kept for audit. Malformed outputs are logged, and a failed final verdict marks the run incomplete. — [arXiv HTML](https://arxiv.org/html/2601.21936v1)
- Setup:
  - Task: NLSY97 young-adult recidivism, 1,412 cases, 27 features, 3-year rearrest label (72% NO, 28% YES).
  - Models: 16 small open models (7–14B, 4-bit, via Ollama); larger ensembles of 37 and 81 model+prompt combinations up to 72B; commercial gpt-4o-mini, o3-mini, Claude 3.5 Haiku and Claude 3.5 Sonnet. About 90 combinations in total.
  - Temperature: 0.7 for debate, 0.0 for single-turn prompts.
  - — [arXiv HTML](https://arxiv.org/html/2601.21936v1)
- Results: no clear accuracy win.
  - Debate accuracy ranged 0.68–0.76 and F1 0.52–0.64 across the small models (e.g., Qwen 2.5 at 0.76/0.60).
  - The best single-agent zero-shot result was Dolphin 3 at 0.77/0.65.
  - The claimed benefit is stability: F1 standard deviation was 0.04 for debate versus 0.08 for single-agent zero-shot, and accuracy and F1 were more correlated.
  - Random Forest reached 0.7606 accuracy. The authors note that tabular ML such as XGBoost usually far outperforms LLM reasoning on tabular data.
  - — [arXiv HTML](https://arxiv.org/html/2601.21936v1)
- Calibration: self-reported prediction confidence did not correlate with accuracy, so the transcripts are plausible rather than faithful explanations. — [arXiv HTML](https://arxiv.org/html/2601.21936v1)
- Cost: about 9,100 tokens per debate versus 650–800 for single-turn CoT (11–14×), and 8–12× the wall-clock time. — [arXiv HTML](https://arxiv.org/html/2601.21936v1)
- Caveats:
  - One dataset, no repeated runs and no confidence intervals.
  - Claude 3.5 Haiku predicted NO in every CoT and n-shot run (0.71 accuracy, 0.00 F1).
  - With 72% NO labels, a majority-class baseline scores about 0.72. This is the extraction tool's inference from the stated label rate, not the authors' claim.
  - The authors attach explicit non-deployment constraints. Code is promised under MIT, but no specific repository is given.
  - — [arXiv HTML](https://arxiv.org/html/2601.21936v1); [abstract](https://arxiv.org/abs/2601.21936)

**PROClaim, "Courtroom-Style Multi-Agent Debate with Progressive RAG and Role-Switching" (arXiv 2603.28488; Chowdhury et al.; v1 30 Mar 2026, v3 1 Aug 2026; under review)**
- Roles (all heterogeneous):
  - Plaintiff Counsel: gpt-5-mini.
  - Defense Counsel: deepseek-v3.2.
  - Court: qwen3-235b-a22b.
  - Expert Witness, called when the judge asks: hermes-3-llama-405b.
  - Independent Critic: deepseek-r1.
  - Three-judge panel: deepseek-r1, hermes-3-405b and qwen3-235b, deciding by majority vote among Supported, Not Supported and Inconclusive. A "burden of refutation" rule counts Inconclusive as Supported.
  - — [arXiv HTML](https://arxiv.org/html/2603.28488)
- Rounds:
  - At most 10. Each round has five stages: evidence discovery, argument generation, expert testimony, self-reflection and critic evaluation.
  - Early stop on any of: a reflection plateau (|Δ| < 0.05 for two rounds), critic resolution, novelty exhaustion (average novelty < 0.10), or a judicial signal.
  - Evidence negotiation: the two sides exchange evidence pools before the debate.
  - Role-switching: the counsels swap sides and rerun the debate, and a separate LLM scores agent-level consistency.
  - — [arXiv HTML](https://arxiv.org/html/2603.28488)
- Progressive RAG (P-RAG):
  - Each query combines the last 4 debate messages with the agent's self-identified evidence gap, and the judge refines it.
  - Novelty = 1 − max cosine similarity to the existing pool. Only items with novelty ≥ 0.20 are admitted.
  - Admissibility w = relevance × credibility. w > 0.5 is admitted; 0.1–0.5 is marked disputed.
  - Retrieval: all-MiniLM-L6-v2 and FAISS over about 360k PubMed abstracts.
  - — [arXiv HTML](https://arxiv.org/html/2603.28488)
- Results:
  - Check-COVID: PROClaim 0.8167 accuracy / 0.8165 macro-F1; standard MAD 0.7167 / 0.7068; single-call DeepSeek-v3.2 + RAG 0.8000 / 0.7972. So PROClaim is +10 pp over MAD but only +1.7 pp over a single RAG call.
  - HealthVer subset: PROClaim 0.720; single-call RAG 0.630; standard MAD 0.560 (McNemar p = 0.0046 reported).
  - FEVEROUS (60 claims): 0.783.
  - — [arXiv HTML](https://arxiv.org/html/2603.28488); [abstract](https://arxiv.org/abs/2603.28488)
- Ablations (120 claims):
  - Without P-RAG: −7.5 pp. Inter-judge agreement also rises, which the authors call an epistemic bubble.
  - Without role-switching: −4.2 pp.
  - Without the three-judge panel: −3.3 pp.
  - Without self-reflection: −0.8 pp, but 29% more rounds and 17% more tokens.
  - — [arXiv HTML](https://arxiv.org/html/2603.28488)
- Calibration: their consensus-based confidence formula gives ECE 0.034, versus 0.18 for standard averaging. — [arXiv HTML](https://arxiv.org/html/2603.28488)
- Variance and bias:
  - Run accuracy varied from 0.790 to 0.950.
  - Mean inter-judge κ was 0.468, with 48.9% of verdicts unanimous.
  - The judges show structural negativity bias: debates over claims that end up refuted converge faster.
  - Concession rates were low (0.03 for Plaintiff and 0.01 for Defense per 1,000 words), i.e., little capitulation.
  - — [arXiv HTML](https://arxiv.org/html/2603.28488)
- Cost and claims: about 211K tokens per claim, roughly 11× standard MAD. The authors claim deliberative traceability, not faithful explanation. Code and data: github.com/mnc13/PROClaim. — [arXiv HTML](https://arxiv.org/html/2603.28488)

**Design references from before 2025 [not re-fetched]**
- Devil's-advocate ("tit-for-tat") debate to counter degeneration of thought — [Liang et al., arXiv 2305.19118](https://arxiv.org/abs/2305.19118)
- ReConcile: a round table of heterogeneous models with a confidence-weighted vote — [arXiv 2309.13007](https://arxiv.org/abs/2309.13007)
- A panel of diverse smaller LLM judges (PoLL) instead of one large judge, with less intra-model bias — [arXiv 2404.18796](https://arxiv.org/abs/2404.18796)
- Debate helps non-expert judges find the truth — [Khan et al., arXiv 2402.06782](https://arxiv.org/abs/2402.06782)
- The original multi-agent debate paper — [Du et al., arXiv 2305.14325](https://arxiv.org/abs/2305.14325)

### Inferences
- Justify the Prosecutor/Advocate debate by (1) adversarial coverage of inculpatory and exculpatory evidence and (2) the audit trail, not by an accuracy gain. ML-engineer jurors who know "Debate or Vote" will ask for a baseline. Report single-agent, single-agent with 3-sample vote, and debate side by side on the golden set.
- Recommended protocol:
  1. Independent first-round arguments, where neither side sees the other, to prevent anchoring and sycophancy.
  2. One rebuttal round restricted to the closed evidence bundle.
  3. An optional role-switch rerun as a stability check. If the outcome changes, send the case to a human.
  4. A deterministic rules engine makes the decision. An LLM judge, or a 2–3-model heterogeneous panel, only grades whether each argument's citations support it.
- Use different model families for the two sides or for the judge, e.g., Claude for one side and another Bedrock-hosted family for the other. The literature supports this for reducing correlated errors. Which models are available on the team's Bedrock region was not verified.
- PROClaim's burden-of-refutation rule (Inconclusive counts as Supported) maps onto "doubt favours the customer / routes to a human". This also matches the PSD2 idea that the payment provider must prove gross negligence, but I did not verify that legal point in this session.
- Do not show the LLM's verbal confidence as calibrated: AgenticSimLaw found it does not track accuracy. Derive confidence from vote fractions or rule scores, and report ECE or Brier score on the golden set if there is time.
- Latency and cost: courtroom debate costs about 11–14× a single call. For the live demo, cap at one opening plus one rebuttal and stop early once new evidence stops appearing (PROClaim-style novelty).

### Gaps
- I found no 2025–2026 study of debate applied to payment-dispute liability or AML triage.
- The only head-to-head calibration comparison (ECE) between debate and a simpler baseline is PROClaim's own formula versus averaging.
- I read only the abstracts of "Debate or Vote" and "Stop Overvaluing MAD", so their per-benchmark numbers were not extracted.
- Anthropic's June 2025 post on its multi-agent research system (token-multiplier figures) was not re-verified, so no numbers are given here.

## 2. Evidence-grounded decisions: citation enforcement, "no new facts", claim verification, counterfactuals, the AML triage paper and Co-Investigator AI

### Takeaway
The pattern with the best support is a closed evidence bundle, a structured output contract that cites evidence IDs, an automatic verifier with a repair loop, and counterfactual tests. In the AML triage paper, LLM-only triage is worse than classical ML. Evidence-grounded LLM triage with counterfactual checks beats a GNN on escalation F1 (0.62 vs 0.56), with citation validity of 0.98. That paper is weak evidence, though (no named LLM, synthetic data only, no variance reported), so reuse its metric definitions rather than its numbers. Co-Investigator AI shows a production-style layout (planner, specialist agents, privacy guard, agent-as-judge, human editing loop) with modest scores from expert raters.

### Cited Findings
**"Explainable AML Triage with LLMs: Evidence Retrieval and Counterfactual Checks" (arXiv 2604.19755; Torres, Cheng, Hu; v1 22 Mar 2026, v2 6 Jun 2026; 17 pages; a Jersey City, NJ school and Penn State)**
- Three components:
  1. A retrieval-augmented evidence bundle built from policy/typology guidance, customer context, alert triggers and transaction subgraphs.
  2. A structured output contract with explicit citations that separates supporting evidence from contradicting or missing evidence.
  3. Counterfactual checks.
  - — [arXiv abstract](https://arxiv.org/abs/2604.19755)
- Output schema, enforced for every LLM variant: decision, confidence, supporting evidence IDs, contradicting/missing evidence IDs, rationale with citations, and recommended next actions. An "unknowns" field is used in the adversarial tests.
  - An automatic verifier rejects outputs that contain non-existent citations, inconsistent amounts or dates, or unsupported claims, then triggers a repair step with targeted feedback.
  - — [arXiv PDF](https://arxiv.org/pdf/2604.19755) (text extracted locally from the PDF; no HTML version exists)
- Metric definitions (directly reusable):
  - Citation validity: share of cited evidence IDs that exist in the retrieved bundle.
  - Evidence support rate: share of rationale sentences whose cited evidence actually contains the entities and numbers they mention (amounts, timestamps, counterparties, risk tiers).
  - Decision-driver coverage: each top reason is backed by at least one policy/typology item and at least one case, customer or transaction item.
  - CF-Flip Rate: share of alerts for which the system finds a valid minimal flip condition within a bounded edit budget.
  - CF-Faithfulness (Removal): remove a critical cited item, rerun, and check that the model stops citing it and moves its decision or rationale in the expected direction.
  - CF-Stability: the decision stays the same under irrelevant perturbations, such as benign reordering of equivalent transactions or small noise.
  - Safety rates: numerical inconsistency, policy hallucination (cited policy that is not in the corpus) and unsupported assertions (new entities or facts not in any cited evidence).
  - Adversarial-evidence test: given conflicting or incomplete evidence, does the model flag uncertainty in "unknowns" instead of making facts up?
  - Workload proxy: share of alerts routed to monitor or escalate at a fixed recall target.
  - — [arXiv PDF](https://arxiv.org/pdf/2604.19755)
- Counterfactual generation: the model proposes candidate edits derived from its own stated decision drivers. An edit budget keeps them minimal, and plausibility rules filter out impossible ones (e.g., negative amounts, inconsistent timestamps). A triage validator then checks each one, and a counterfactual is accepted only if it produces the expected decision change. — [arXiv PDF](https://arxiv.org/pdf/2604.19755)
- Data: SynthAML10 and IBM's AMLSim simulator, with case notes generated from the simulator's typology annotations. The Elliptic Bitcoin graph is an optional external check. — [arXiv PDF](https://arxiv.org/pdf/2604.19755)
- Table 1 columns, in order: PR-AUC / escalate precision / escalate recall / escalate F1 / citation validity / evidence support / CF-flip / CF-faithfulness (removal) / numerical inconsistency / policy hallucination. — [arXiv PDF](https://arxiv.org/pdf/2604.19755)
  - Rule/threshold: 0.41 / 0.18 / 0.78 / 0.29 / – (no provenance metrics)
  - Tabular ML (GBDT): 0.63 / 0.42 / 0.66 / 0.51 / –
  - Graph ML (GNN): 0.69 / 0.46 / 0.71 / 0.56 / –
  - LLM-only: 0.52 / 0.31 / 0.60 / 0.41 / 0.62 / 0.54 / 0.28 / 0.39 / 0.11 / 0.14
  - RAG without CF checks: 0.71 / 0.49 / 0.73 / 0.59 / 0.96 / 0.83 / 0.41 / 0.57 / 0.06 / 0.05
  - RAG + counterfactual checks (theirs): 0.75 / 0.53 / 0.75 / 0.62 / 0.98 / 0.88 / 0.58 / 0.76 / 0.03 / 0.02
- The authors conclude that LLMs on their own are not competitive triage predictors. Their value is structured, evidence-bound decision support. The gain over the GNN comes mainly from higher precision at similar recall, which is what matters operationally. — [arXiv PDF](https://arxiv.org/pdf/2604.19755)
- Caveats I found in the extracted text:
  - No LLM model name appears anywhere.
  - The paper partly describes its evaluation as a reproducible blueprint.
  - No variance or confidence intervals are reported.
  - It uses synthetic data only; the authors name this as the main limitation.
  - No code link.
  - — [arXiv PDF](https://arxiv.org/pdf/2604.19755)

**"Co-Investigator AI: The Rise of Agentic AI for Smarter, Trustworthy AML Compliance Narratives" (arXiv 2509.08380; Naik, Dintakurthi, Hu, Wang, Qiu; Sep 2025)**
- Components:
  - Data ingestion and structuring layer.
  - AI-Privacy Guard: a RoBERTa+CRF model masks confidential entities before any external LLM call, and masks or unmasks again at each stage.
  - Crime-type detection: risk-indicator tools plus Random Forest and Gradient Boosting classifiers that output ranked typologies with confidence.
  - Planning agent: the orchestrator that spawns the other agents.
  - Seven typology agents: transaction fraud, payment velocity, country risk, text content, geographic anomalies, account health, dispute patterns.
  - External-intelligence agent: queries news, sanctions lists and media through MCP servers.
  - Narrative agent: drafts the SAR with explicit chain-of-thought.
  - Compliance validation agent (Agent-as-a-Judge): checks coherence and uses rule-based logic to cross-check narrative facts against the typology outputs.
  - Feedback agent.
  - Dynamic memory in three layers: regulatory, historical narratives, typology-specific.
  - — [arXiv HTML v2](https://arxiv.org/html/2509.08380v2)
- Human in the loop: investigators edit drafts in a secure interface, and their edits feed later cycles. The authors deliberately reject an approve-and-go workflow. — [arXiv HTML v2](https://arxiv.org/html/2509.08380v2)
- Evaluation:
  - Six expert investigators from an unnamed "leading global fintech company" rated drafts on a 1–5 scale:

    | Component | Score (1–5) | Effectiveness |
    |---|---|---|
    | Narrative completeness | 3.52 | 70% |
    | Efficiency gains | 3.06 | 61% |
    | Financial transaction analysis | 3.50 | 70% |
    | Volume/velocity anomalies | 4.00 | 80% |
    | Jurisdictional risk | 3.80 | 76% |
    | Text patterns | 4.00 | 80% |
    | Location anomalies | 5.00 | 100% |
    | Account integrity | 4.67 | 93% |
    | Dispute and chargeback | 4.50 | 90% |

  - Completeness reaches 87% for some typologies.
  - Pre-production scoring compares drafts with investigator-written "golden" SARs using Gemini 2.5 Pro: weighted accuracy on dates, amounts and subjects, plus semantic similarity across 7 compliance dimensions.
  - GPT-4 and Claude 3 with direct prompting serve as comparison points.
  - No hallucination rate, time per SAR or quantitative baseline is measured.
  - — [arXiv HTML v2](https://arxiv.org/html/2509.08380v2)
- Affiliation: the arXiv page does not name PayPal, so the PayPal link is [unverified]. — [arXiv abstract](https://arxiv.org/abs/2509.08380)

**Claim verification and "LLM as sensor"**
- Chain-of-Verification (Dhuliawala et al., Meta, 2023): draft an answer, plan verification questions, answer them independently of the draft (factored), then revise. This is background, older than the 2025–2026 window [not re-fetched]. — [arXiv 2309.11495](https://arxiv.org/abs/2309.11495)
- PolicyGuard pattern: the LLM only asserts whether specific facts (atoms) are present, and a symbolic evaluator (Z3) makes the compliance decision. I saw this only in a secondary summary. — [alphaXiv 2606.32004](https://www.alphaxiv.org/abs/2606.32004v1)

### Inferences
- Implement "no new facts" as the paper's evidence-support check, made deterministic.
  - Every amount, date, IBAN/account ID, URL or merchant name in an argument must match a field of a cited evidence item. If not, reject the argument and repair it with targeted feedback (at most 1–2 retries).
  - Only IDs from the bundle can be cited. Aim for citation validity of at least 0.98, and show the verifier rejecting a fabricated citation live.
- The supporting / contradicting / missing split in the paper's contract maps onto the roles:
  - The Prosecutor fills supporting evidence for gross negligence.
  - The Advocate fills contradicting evidence.
  - Both must list what is missing ("unknowns"). A non-empty "missing" field on a decisive fact routes the case to a human.
- Counterfactual checks to run live:
  - Remove the evidence item "customer typed the OTP into the phishing page after an in-app warning". The negligence finding should drop and a full refund should follow.
  - Reorder the transactions. Nothing should change.
  - In AML, remove the "account opened 3 days ago and receiving funds from 5 victims" link. The mule hypothesis should weaken, and the Advocate of innocence's "new legitimate shop" explanation should gain weight.
- CoVe-style factored verification is cheap: a small model checks each claim against only its cited evidence item.
- Ideas to borrow from Co-Investigator AI: a PII mask before LLM calls (supports the AML/dispute information barrier), MCP tools for external intelligence, an agent-as-judge combined with rule-based cross-validation, and a human editing interface where edits are logged.

### Gaps
- The AML triage paper does not report the LLM used, the prompts, the sample sizes or the variance, and links no code.
- Co-Investigator AI has no quantitative comparison with manual work or direct prompting, and its affiliation is unconfirmed.
- I did not verify whether Claude's native Citations feature works on Amazon Bedrock.

## 3. Deterministic decision layers: decision tables, rules engines, Z3/SMT, and how to combine them with LLM extraction

### Takeaway
Let the LLMs extract typed facts and argue, let a versioned decision table decide, and use an SMT solver (Z3) to check invariants. GoRules ZEN is the fastest to demo: a JSON decision model with a visual editor, a Rust core with Python and Node bindings, and a 2.0 line released in Aug 2026. 2025–2026 research (ARc, PolicyLLM, solver-aided tool-use compliance) supports the same split: the LLM acts as a sensor and the solver acts as the judge.

### Cited Findings
- GoRules ZEN is a business rules engine with a Rust core and several language bindings. Its JSON Decision Model (JDM) is a graph format whose node types include decision tables with hit policies.
  - Java/Kotlin: 2.0.0 (22 Aug 2026), 2.0.1 (23 Aug) and 2.0.2 (25 Aug).
  - Go: zen-go v2 is described as the first stable release of the new engine line.
  - .NET: latest is 0.7.2 (Mar 2026), so it may lag.
  - Python: zen-engine on PyPI.
  - — [JDM docs](https://docs.gorules.io/reference/json-decision-model-jdm); [node types](https://docs.gorules.io/developers/jdm/node-types.md); [Maven versions](https://mvnrepository.com/artifact/io.gorules/zen-engine/versions); [zen-go v2](https://pkg.go.dev/github.com/gorules/zen-go/v2); [PyPI zen-engine](https://www.pypi.org/project/zen-engine); [NuGet](https://www.nuget.org/packages/GoRules.ZenEngine); [what is GoRules](https://docs.gorules.io/learn/getting-started/what-is-gorules)
- ARc, "A Neurosymbolic Approach to Natural Language Formalization and Verification" (2025, hosted on Amazon Science): a Policy Model Creator turns policy documents into SMT-LIB models, and an Answer Verifier checks answers against them. The authors self-report soundness above 99% on held-out datasets. — [arXiv 2511.09008](https://arxiv.org/html/2511.09008v1); [Amazon Science PDF](https://cdn.amazon.science/e3/20/f19a59d44d6ebfbdc621439dc86b/scipub-approval152134-43501461-a-neurosymbolic-approach-to-natural-language-formalization-and-verification.pdf)
- PolicyLLM (ICML 2026): compiles natural-language policy into decision graphs validated with Z3 and enforces them over LLM outputs at inference time. — [ICML 2026](https://icml.cc/virtual/2026/78632)
- Solver-aided tool-use compliance (arXiv 2603.20449): tool-use policies are translated into SMT-LIB 2.0 constraints, LLM-assisted but human-guided, and Z3 checks each planned tool call before it runs. On TauBench this reduced policy violations while keeping task accuracy. — [arXiv 2603.20449](https://arxiv.org/abs/2603.20449)
- VERGE (arXiv 2601.20055): combines LLMs with SMT solvers to refine answers iteratively under verification guidance. — [alphaXiv](https://www.alphaxiv.org/abs/2601.20055)
- Co-Investigator AI's compliance agent cross-validates narrative facts with rule-based logic, a production precedent for rules checking LLM output. — [arXiv HTML v2](https://arxiv.org/html/2509.08380v2)
- These search results include no independent replications; all figures are the authors' own. — (search summary, sources above)

### Inferences
- Concrete pipeline:
  1. Claude extracts facts into a Pydantic or JSON schema in which every field carries an evidence ID. Example fields: `otp_entered_on_third_party_page`, `in_app_warning_shown_before`, `link_domain_lookalike`, `payment_authorised_by_biometric`, `first_such_incident`, `reported_within_hours`, `amount`.
  2. A GoRules decision table decides: liability (bank / customer / split), refund amount, and `requires_human_signature`. Each row gets an ID such as R-07.
  3. Z3 checks invariants, for example:
     - An outcome unfavourable to the customer implies `human_signature == true`.
     - The refund is at most the disputed amount.
     - Every fired rule references at least one admissible evidence ID.
     - Contradictory facts cannot both be true.
  4. The LLM writes the explanation, citing the rule row and the evidence IDs.
  - Show the decision table and the row that fired on screen, so jurors see that no LLM decides alone.
- json-rules-engine (Node) is the light alternative for a TypeScript backend. Drools with DMN is heavier and fits a Java/KIE shop, which is likely overkill for 24 hours. Versions for both are unverified.
- Amazon Bedrock Guardrails' "Automated Reasoning checks" appear to productize the ARc research. That would be a Bedrock-native talking point, but I did not verify the link or its availability in this session [unverified].
- Z3 also suits AML: it can encode the rule that the Advocate of innocence's explanation must be logically consistent with the transaction facts (e.g., "new legitimate shop" requires a registered merchant category and inbound card payments, not person-to-person transfers from victims).

### Gaps
- Current versions of json-rules-engine and Drools were not verified.
- I found no benchmark comparing rules engines inside LLM pipelines.
- I did not read the ZEN 2.0 changelog (breaking changes, Python binding version).

## 4. Evaluation and red-teaming tools for agents in 2026; golden test set and metric reporting

### Takeaway
Use a small golden set (20–60 cases) built from realistic failure cases, code-based graders wherever possible, and several trials per case (pass^k). Pair one harness for functional metrics (Inspect AI, or DeepEval via pytest) with promptfoo for red-teaming: prompt injection, PII leakage, and a custom policy for the AML/dispute information barrier. Report escalation precision and recall with confidence intervals, citation and evidence-support metrics, counterfactual metrics, leakage counts, and cost per case.

### Cited Findings
- Anthropic, "Demystifying evals for AI agents" (9 Jan 2026):
  - Grader types: code-based (fast, objective, brittle), model-based (flexible; must be calibrated against humans) and human.
  - Capability evals start at a low pass rate; regression evals stay near 100%.
  - Start with 20–50 simple tasks drawn from real failures.
  - Balance tests: check both when a behaviour should occur and when it should not.
  - pass@k means at least one of k trials succeeds; pass^k means all k succeed (75% per trial gives about 42% at k=3).
  - Grade outcomes rather than paths, and read transcripts to validate graders.
  - Isolate each trial in a clean environment.
  - For LLM judges: grade each dimension separately and allow an "Unknown" answer.
  - Tools named: Harbor, Braintrust, LangSmith, Langfuse, Arize.
  - The guide gives no specific advice for multi-agent systems.
  - — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- promptfoo:
  - Has an agent red-teaming guide.
  - Its `excessive-agency` plugin flags actions beyond the agent's intended scope.
  - Core plugins include prompt injection, and PII variants include `pii:direct`, `pii:session` and `pii:social`.
  - A custom `policy` plugin generates tests from your own rules.
  - The agent guide also covers repository prompt injection and secret-read risks for coding agents.
  - A secondary source reports that OpenAI agreed to acquire promptfoo in March 2026 and committed to keeping it open source.
  - — [promptfoo: red team agents](https://www.promptfoo.dev/docs/red-team/agents); [configuration](https://promptfoo.dev/docs/red-team/configuration); [plugin catalogue](https://promptfoo.dev/docs/category/plugins-1); [LLM red-teaming guide](https://promptfoo.dev/docs/guides/llm-redteaming); [third-party 2026 guide](https://qaskills.sh/blog/promptfoo-red-teaming-guide-2026); [acquisition report (secondary)](https://emelia.io/hub/promptfoo-test-securite-ia)
- Inspect AI (UK AISI):
  - Built-in `react()` agent, and a sandbox set per task (e.g., `sandbox="docker"`).
  - Deterministic scorers (match, pattern, choice) plus model-graded scorers.
  - The Inspect Evals collection of benchmark implementations.
  - The AISI sandboxing toolkit.
  - The US AI Safety Institute created AgentDojo-Inspect (usnistgov/agentdojo-inspect) to research agent hijacking, i.e., indirect prompt injection through data the agent reads.
  - — [Inspect tutorial](https://inspect.aisi.org.uk/tutorial.html); [Inspect llms.txt](https://inspect.aisi.org.uk/llms.txt); [AISI sandboxing blog](https://aisi.gov.uk/blog/the-inspect-sandboxing-toolkit-scalable-and-secure-ai-agent-evaluations); [NIST/Commerce dataset listing](https://data.commerce.gov/node/211960); [Hamel Husain notes](https://hamel.dev/notes/llm/evals/inspect.html)
- DeepEval:
  - Agentic metrics: Task Completion and Tool Correctness, plus Argument Correctness (are tool arguments correct?).
  - A safety group that includes `PIILeakageMetric`, alongside Bias and Toxicity.
  - Version 3.9.5 is listed on a PyPI mirror (date not shown).
  - MLflow and Databricks expose DeepEval scorers.
  - — [DeepEval metrics](https://deepeval.com/docs/metrics-introduction); [MLflow DeepEval scorers](https://www.mlflow.org/docs/latest/genai/eval-monitor/scorers/third-party/deepeval/); [Databricks](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/third-party-scorers/deep-eval); [PyPI mirror](https://simple-repository.app.cern.ch/project/deepeval); [Habr overview](https://habr.com/ru/articles/955314)
- Ragas: mainly RAG metrics (faithfulness, context precision and recall), plus a small set of agent metrics that the search results did not name. A practitioner's split is "Ragas for trends, DeepEval for gates"; DeepEval's own comparison is vendor-written. — [DeepEval vs Ragas (vendor)](https://deepeval.com/blog/deepeval-vs-ragas); [practitioner write-up](https://jacar.es/en/deepeval-evaluating-agents/)
- A ready-made, domain-specific metric set comes from the AML triage paper (Section 2): citation validity, evidence support, decision-driver coverage, CF flip, faithfulness and stability, numerical inconsistency, policy hallucination, unsupported assertions, escalate P/R/F1, PR-AUC, workload proxy. — [arXiv 2604.19755](https://arxiv.org/pdf/2604.19755)
- A reporting model for debate systems comes from PROClaim: ECE, inter-judge κ, run-to-run variance, tokens per case and component ablations. — [arXiv 2603.28488](https://arxiv.org/html/2603.28488)

### Inferences
- Golden set of about 40 cases, each with these labels: expected decision, expected escalation (human sign-off required yes/no), required evidence IDs, forbidden claims, and 2 counterfactual variants.
  - 20 disputes:
    - 6 clear gross negligence (e.g., the customer read the OTP to a "bank" caller despite an explicit in-app warning).
    - 6 clear non-negligence (e.g., spoofed caller ID plus a pixel-perfect lookalike domain, with no warning shown).
    - 8 borderline.
  - 20 AML leads:
    - Mule-ring members.
    - A recruited mule who is also a victim.
    - A legitimate new shop with a sales spike.
    - A small-business false positive.
    - A true layering pattern.
- Report card for the jury:
  - Confusion matrix on "escalate / needs human" with precision, recall, F1 and Wilson 95% confidence intervals, since N is small.
  - Citation validity, evidence-support rate and unsupported-assertion rate.
  - CF flip and stability.
  - pass^3 consistency.
  - Tokens and latency per case.
  - An ablation table: single agent vs single agent with vote vs debate vs debate plus verifier. This answers the "Debate or Vote" critique.
- Information-barrier (Chinese-wall) test between the AML zone and the dispute zone:
  - Plant canary strings (fake watchlist entries, SAR IDs) in AML-zone records.
  - Attack the dispute-zone agents with promptfoo's custom policy plugin, the PII plugins, and indirect prompt injection hidden in the free-text dispute description and the merchant name.
  - Pass criterion: 0 canary leaks. With 0 leaks in N attempts, the 95% upper bound on the leak rate is about 3/N (the "rule of three", standard statistics).
  - Include positive controls (allowed cross-zone signals) so the barrier is not tested one-sidedly, following Anthropic's balanced-tests advice.
- Make it runnable: `promptfoo redteam run`, `deepeval test run` (pytest) or `inspect eval` in one `make eval` target, with the results table shown in the demo. This addresses the testability (20%) and reproducibility (15%) criteria directly.

### Gaps
- Current exact versions of Inspect AI, promptfoo and Ragas were not verified. AgentDojo's task and test-case counts were not checked this session.
- promptfoo's full plugin list (e.g., cross-session leak, RBAC/BOLA, indirect prompt injection) was not confirmed from the official plugin page this session.
- I found no published benchmark of information-barrier leakage between cooperating agents.
- I could not confirm the promptfoo acquisition from a primary source.

## 5. Observability and durable execution: Langfuse, Phoenix, OTel GenAI, Temporal, LangGraph 1.x, Pydantic AI — which is fastest for a 24-hour build with Claude on Bedrock?

### Takeaway
For 24 hours: LangGraph 1.x, using interrupts plus a checkpointer for the human signature and streaming, with Claude on Bedrock; traces in Arize Phoenix (fastest locally) or Langfuse (shareable, self-hostable); and SSE or AG-UI events to the UI. Durable execution with Temporal (directly or through Pydantic AI) is a strong "production path" slide but adds infrastructure. The OTel GenAI semantic conventions are still at Development status, so pin versions.

### Cited Findings
- LangGraph interrupts:
  - Need a checkpointer and a thread ID.
  - Execution resumes with `Command(resume=value)`, and that value becomes the return value of `interrupt()` inside the node. The interrupt payload appears under `result["__interrupt__"]`.
  - State is persisted, so a graph can pause indefinitely.
  - On resume the node reruns from its start, so side effects belong after the interrupt or must be idempotent. Avoid loops over non-deterministic logic around interrupts.
  - A durable checkpointer (e.g., Postgres) is recommended in production.
  - — [LangGraph interrupts (Python)](https://docs.langchain.com/oss/python/langgraph/interrupts); [human-in-the-loop](https://docs.langchain.com/oss/python/langgraph/human-in-the-loop); [JS HITL](https://docs.langchain.com/oss/javascript/langgraph/human-in-the-loop)
- No fetched source confirmed LangGraph 1.0's release date or the current 1.x version. From prior knowledge, 1.0 shipped in Oct 2025 alongside LangChain 1.0 [unverified].
- Pydantic AI:
  - Officially supports four durable execution backends: Temporal, DBOS, Prefect and Restate.
  - Integration is through capabilities such as `TemporalDurability` and `DBOSDurability`. The older `DBOSAgent` wrapper is slated for removal in v3.
  - Pydantic Graph is a separate package for typed multi-step control flow.
  - Amazon Bedrock is one of its supported model providers.
  - A third party reports a v2 beta line (2.0.0b7, 10 Jun 2026) with beta modules exempt from stability guarantees.
  - Temporal has published a guide to building durable agents with Pydantic AI.
  - — [Pydantic AI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/); [backends](https://pydantic.dev/docs/ai/capabilities/durable_execution/backends/); [DBOS page](https://pydantic.dev/docs/ai/capabilities/durable_execution/dbos/index.md); [Temporal page](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/index.md); [Temporal blog](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal); [DBOS docs](https://docs.dbos.dev/integrations/pydantic-ai); [third-party summary](https://rywalker.com/research/pydantic-ai)
- OpenTelemetry GenAI semantic conventions:
  - The agent-span spec is at Status: Development. Explainers from May and Sep 2026 say all `gen_ai.*` spans, metrics and attributes remain at Development.
  - The `invoke_agent {gen_ai.agent.name}` span has kind CLIENT, or INTERNAL for in-process agents. `execute_tool` gets one span per tool call.
  - Recommended tree: a root `invoke_agent` span, a chat span per LLM call, and an `execute_tool` span per tool or MCP call.
  - Error status only covers technical failures. A wrong answer does not set it, so semantic failures need evals.
  - — [OTel GenAI agent spans spec](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans); [Dash0, updated Sep 2026](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained); [Greptime, May 2026](https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions); [Honeycomb guide](https://www.honeycomb.io/blog/instrumenting-ai-agents-agent-timeline-opentelemetry-guide); [ClickHouse on agent observability](https://clickhouse.com/resources/engineering/what-is-ai-agent-observability)
- Langfuse: ClickHouse announced it had acquired Langfuse on 16 Jan 2026, alongside a $400M Series D. Langfuse says there are no immediate changes to the product, roadmap or open-source commitment. A secondary source says the core stays MIT-licensed. — [Langfuse: joining ClickHouse](https://langfuse.com/blog/joining-clickhouse); [ClickHouse blog](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability); [SiliconANGLE](https://siliconangle.com/2026/01/16/database-maker-clickhouse-raises-400m-acquires-ai-observability-startup-langfuse/); [InfoWorld](https://www.infoworld.com/article/4118621/clickhouse-buys-langfuse-as-data-platforms-race-to-own-the-ai-feedback-loop.html)
- Arize Phoenix:
  - Arize's open tracing and evaluation tool. A secondary source says it is under the Elastic License 2.0, which is source-available rather than OSI open source.
  - Bedrock and Bedrock Agents are instrumented through `openinference-instrumentation-bedrock`.
  - It runs locally, in a notebook, in a container or in the cloud.
  - `arize-phoenix` 13.23.0 is listed on a PyPI mirror.
  - Arize has not been acquired; it raised a $70M Series C in Feb 2025.
  - — [PyPI arize-phoenix](https://pypi.org/p/arize-phoenix); [PyPI mirror](https://simple-repository.app.cern.ch/project/arize-phoenix); [LiteLLM Phoenix integration](https://docs.litellm.ai/docs/observability/phoenix_integration); [Hackernoon analysis](https://hackernoon.com/two-acquisitions-deep-two-still-standing-whats-really-happening-to-open-source-llm-observability)
- AWS Bedrock AgentCore Runtime documents AG-UI support. Strands agents wrapped with `ag-ui-strands` stream RUN_STARTED, TEXT_MESSAGE_CONTENT and RUN_FINISHED events. — [AWS AgentCore AG-UI docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.md)
- Anthropic's evals guide lists Langfuse (self-hosted, open source) and Arize Phoenix/AX among tracing and eval options. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Inferences
- Fastest stack for 24 hours, with Claude on Bedrock:
  - Python FastAPI.
  - LangGraph 1.x, with Claude through `langchain-aws` `ChatBedrockConverse`. Package versions are unverified.
  - `SqliteSaver`, or `PostgresSaver` if Postgres is already running.
  - A node "propose unfavourable decision" that calls `interrupt({...case summary, rule row, evidence...})`.
  - The UI shows "Awaiting human signature", and the reviewer's click sends `Command(resume={"approved": true, "signer": "..."})`.
  - Show durability live: restart the API server in the middle of a case and resume from the checkpoint. That is a concrete proof of reproducibility and robustness for the 15% criterion.
- Map the graph topology onto the story: extract → (Prosecutor ∥ Advocate) → verifier/repair → rules + Z3 → human interrupt → payout/notification. Show the same topology in React Flow in the UI.
- Tracing: Phoenix is quickest to start locally (pip install plus OpenInference LangChain/Bedrock instrumentors). Langfuse gives a hosted, shareable trace link plus datasets and annotation queues. Either way, show each case's trace ID or link in the UI.
- Temporal: keep it for the "production architecture" slide (one workflow per case, an activity per agent, the human signature as a Temporal signal, retries and timeouts). Build it in the 24 hours only if a team member already knows Temporal. The lowest-friction Temporal route is Pydantic AI with `TemporalDurability`.
- Strands with AgentCore is the most AWS-native alternative, with AG-UI out of the box, if the team wants a Bedrock-hosted runtime.
- Name the OTel GenAI attributes in the architecture slide, but pin SDK versions because the spec is still at Development.

### Gaps
- Exact current versions of LangGraph, langchain-aws, the Langfuse SDK, the Temporal SDK and Pydantic AI 1.x were not verified.
- I found no study comparing build speed across frameworks, so the "fastest" choice is an inference.
- I did not verify whether Langfuse or Phoenix render LangGraph's OTel `invoke_agent` spans natively.

## 6. Live demo UX: streaming traces, graph visualisation, mock banking PWA with push, examples of winning agentic demos

### Takeaway
Stream agent events to the UI over SSE using AG-UI event shapes (or CopilotKit). Draw the agent pipeline with React Flow and the fraud-ring graph with Cytoscape.js; Sigma.js is only needed for thousands of nodes. Do not rely on iOS web push in the live demo: it works only for PWAs added to the Home Screen (iOS 16.4+, permission needs a user gesture). Use Android or desktop Chrome, or an in-app push banner fed by SSE. The judging rubrics I found reward demos that run the full pipeline live and show traces and metrics.

### Cited Findings
- AG-UI (Agent-User Interaction protocol):
  - An open, event-based protocol. CopilotKit's docs say about 16 standard event types; one tutorial says about two dozen.
  - Events can travel over SSE, WebSockets or webhooks. CopilotKit's skill docs also mention a binary protobuf encoding.
  - CopilotKit uses AG-UI as the wire format between its runtime and the agent.
  - The `@ag-ui/langgraph` package implements AG-UI for LangGraph graphs. LangChain's Deep Agents docs have an AG-UI page.
  - Tutorials wire a LangGraph agent to a FastAPI endpoint that returns `text/event-stream`.
  - AWS AgentCore and Strands also emit AG-UI events.
  - — [CopilotKit architecture](https://docs.showcase.copilotkit.ai/concepts/architecture); [Codecademy explainer](https://codecademy.com/article/ag-ui-agent-user-interaction-protocol); [LangChain Deep Agents AG-UI](https://docs.langchain.com/oss/python/deepagents/ag-ui); [CopilotKit: frontend for any LangGraph agent](https://webflow.copilotkit.ai/blog/how-to-add-a-frontend-to-any-langgraph-agent-using-ag-ui-protocol); [CopilotKit LangGraph tutorial](https://dev.to/copilotkit/build-a-fullstack-stock-portfolio-agent-with-langgraph-and-ag-ui-5da0); [AWS AgentCore AG-UI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.md)
- Graph libraries:
  - Elastic moved the Kibana APM service map from Cytoscape.js to React Flow. At 500 services, React Flow drew the map in about 64 ms versus about 393 ms for Cytoscape. This is an application-specific benchmark.
  - React Flow suits node-based editing UIs; Cytoscape.js suits exploration and analysis.
  - Sigma.js uses WebGL and is framework-agnostic.
  - An old rule of thumb: SVG handles about 2k nodes, Canvas about 5k and WebGL about 10k.
  - A Cytoscape-maintained comparison (104 nodes, 2,000 edges) rates Cytoscape near-instant, and Sigma as near-instant to first frame but taking seconds for the layout to settle.
  - — [Elastic Observability Labs](https://www.elastic.co/observability-labs/blog/apm-service-map-react-flow-migration); [Cylynx comparison](https://dev.to/timlrx/a-comparison-of-javascript-graph-network-visualisation-libraries-34a8); [Cytoscape js-graph-lib-comparison](https://github.com/cytoscape/js-graph-lib-comparison/blob/master/README.md); [React Flow vs Cytoscape](https://radar.firstaimovers.com/react-flow-vs-cytoscape-graph-engine-choice)
- iOS web push:
  - Requirements: iOS/iPadOS 16.4+, a web app manifest, the site added to the Home Screen and opened in standalone mode, and a user gesture to trigger the permission prompt.
  - Declarative Web Push can subscribe and show notifications without an installed service worker, and exposes `window.pushManager`. It can be tested on iOS 18.4, iPadOS 18.4 and the macOS 15.5 beta.
  - Vendor guides predate Declarative Web Push and still list a service worker as a setup step.
  - — [WebKit: Meet Declarative Web Push](https://webkit.org/?p=16535); [OneSignal iOS web push](https://documentation.onesignal.com/docs/web-push-for-ios); [Pushpad iOS requirements](https://pushpad.xyz/blog/ios-special-requirements-for-web-push-notifications); [Notificare 2023](https://notificare.com/blog/2023/03/27/web-push-in-ios-safari/)
- Hackathon evidence:
  - The Fullstack Agents Hackathon (LlamaIndex, CopilotKit, Composio, B Capital) judging rubric gives as an example a demo with a dashboard of agent traces and metrics. It rewards live demos that run the full agent pipeline without manual hacks.
  - The Reply AI Agent Challenge asks teams to build a multi-agent system for a complex fraud-detection scenario; no winners list was found.
  - Duck Creek's "Felix" agent, which analyzes audio, images and text to detect fraud and assign claims, was named Best Agent in a global hackathon.
  - Team Agent Halo won $100k at the TDX Agentforce hackathon; details not read.
  - — [AI Tinkerers SF rubric](https://sf.aitinkerers.org/p/copilot-kit-b-capital-hackathon); [Reply AI Agent Challenge](https://challenges.reply.com/challenges/ai-agent/home); [BusinessWire (Duck Creek)](https://www.businesswire.com/news/home/20250915989915/en); [SalesforceBen (Agent Halo)](https://www.salesforceben.com/how-team-agent-halo-won-100k-at-the-tdx-agentforce-hackathon/)

### Inferences
- Demo choreography for the T+1 day:
  1. A QR code opens the mock bank PWA on the juror's phone. The juror gets a fake "delivery fee" SMS or e-mail link to a simulated phishing page, clearly watermarked "SIMULATION". It collects only test data, never real credentials.
  2. A payment is "authorised", and the juror taps Dispute.
  3. The big screen splits into three panels:
     - Left, the courtroom: Prosecutor and Advocate cards stream text, and each cited evidence chip lights up the matching evidence item.
     - Centre: the React Flow pipeline lights up node by node (extract → debate → verify → rules → human).
     - Right: the GoRules table row that fired, plus the Z3 check marks.
  4. The interrupt modal appears: "Human signature required" (only when the outcome is unfavourable). For the refund path, the rules approve it directly, or a reviewer signs.
  5. A refund notification arrives: Web Push on Android or desktop, or an SSE-driven in-app banner on iPhone.
  6. The AML view: a Cytoscape.js graph in which several victim nodes animate toward one mule account (fcose or cola layout). The "Advocate of innocence" side panel shows its hypothesis (recruited mule or new shop) with evidence, and the case is escalated to an analyst.
- Pre-record a backup video of the full flow, and keep a seeded "golden case" so the live run is deterministic: temperature 0, cached evidence, fixed IDs.
- End with an eval slide: golden-set metrics, red-team and leakage results, and the debate-vs-vote ablation, all reproducible with one command. This addresses the 20% and 15% criteria.
- Keep event names aligned with AG-UI (RUN_STARTED, TEXT_MESSAGE_CONTENT, TOOL_CALL_*, STATE_DELTA, RUN_FINISHED) even if you hand-roll the SSE. It costs nothing and gives you a "standards-based" story. The event names beyond those seen in the AWS docs are from memory and should be checked at docs.ag-ui.com.

### Gaps
- I found no verified write-up of a winning bank-track or agentic-fraud hackathon demo with trace-level detail.
- The canonical AG-UI event list (docs.ag-ui.com) was not fetched.
- Current versions of Cytoscape.js, Sigma.js, React Flow (@xyflow/react) and CopilotKit were not verified.
