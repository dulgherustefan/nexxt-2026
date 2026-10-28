# Brief hackathon — NEXXT Summit 2026 · VibeHack · Raiffeisen Bank

Transcris din slide-urile prezentate pe scenă. Ce e marcat „Implicație" e interpretarea noastră, nu textul oficial.

## Provocarea: „AI for Operational Efficiency"

**The challenge.** Build an AI agent that handles repetitive internal banking work involving documents, data, and predefined rules.

**Possible directions**
- Reconcile records and identify discrepancies
- Validate applications against requirements
- Triage and summarise requests
- Detect anomalies

**What to demonstrate.** A working process that takes an input, applies the relevant rules, and produces an outcome or flags an exception.

**Data for your demo.** Use synthetic documents and datasets. Internal banking data is not required.

> **Implicație:** juriul vrea un *proces* (input → reguli → decizie/excepție), nu un chatbot. Munca e **internă** (back-office), deci utilizatorul principal e un angajat al băncii, nu clientul. Plângerile clienților servesc ca dovadă că procesul intern doare.

## Ce evaluează juriul

| Pondere | Criteriu | Descriere oficială | Implicație pentru MVP |
|---:|---|---|---|
| 25% | Agent design and orchestration | Effective tool use, multi-step decisions, and handling of unexpected situations. | Agent cu tool-uri reale (extragere, validatori, lookup-uri, calcule), pași de decizie expliciți, ramuri pentru excepții și escaladare la om. Cel mai mare criteriu. |
| 20% | Functional completeness and testability | A working core scenario that the jury can verify using the submitted evidence and follow-up questions. | Un scenariu end-to-end care merge sigur. Set de cazuri de test cu rezultat așteptat, rulabile cu o comandă. Log/audit trail ca dovadă. |
| 15% | Originality and ingenuity | An inventive approach to the chosen task. | Problemă specifică României sau abordare neobișnuită. 29 de echipe pe același track. |
| 15% | Problem research and domain understanding | Understanding of the relevant processes, data, rules, constraints, and exceptions. | Reguli citate cu act normativ + articol, excepții documentate, cifre de volum și cost. |
| 15% | Architecture and reproducibility | A modular implementation, clear interfaces, and useful setup instructions. | Module separate (ingestie, extragere, reguli, decizie, UI), contracte de date clare, `README` cu setup într-o comandă, date sintetice incluse în repo. |
| 10% | Business mentoring | Problem and user understanding · Value of the solution · Potential for adoption. | Persona internă clară, timp/bani economisiți, cum se integrează în fluxul existent al băncii. |

## Mentori (Raiffeisen Bank)

Toți cei 9 sunt **ML Engineers**: Tiberiu Vasilescu, Teodor Chiroiu, Răzvan-Andrei Mihăescu, Alexandru Crăciun, Cosmin-Gabriel Andrieș, Andrei-Cristian Năstase, Georgiana Ragabeja, Ana-Maria Petre, Alexandru Samson.

> **Implicație:** întrebările vor fi tehnice. Pregătiți răspunsuri la: cum evaluați acuratețea extragerii; ce faceți la încredere scăzută; cum preveniți halucinațiile; de ce LLM și nu reguli simple (și invers); unde e omul în buclă; cum se auditează o decizie; ce se întâmplă cu un document neașteptat.

## Echipele de pe track (29)

ret2futureAI · Phoenix · cat_lovers_ · ChatGPT generate a team name! · Alumor · cnicb · Bug Happens · UVT_VIRUS · liliecii de la electronica · SynCoders · One one zero · smar · Inox · Clingorienii · CTMS Goats · Profit of the Prompt · Hegemind · Cei 4 mustafiri · San Francisco · MergeConflict · ShrimpAI · Andreii · LENS² · Liliecii · KratosMessi · Tripolar · CCC – Claude Code Crusaders · Sha256orma · AppBuilder.AI

> **Implicație:** ideile evidente („validare cerere de credit", „chatbot de reclamații", „detecție fraudă pe card") vor apărea de mai multe ori. Diferențierea vine din specificul românesc, din calitatea gestionării excepțiilor și din testabilitate.
