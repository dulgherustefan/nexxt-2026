# Cercetare pentru upgrade-ul VersoML: RAG hibrid, date sintetice, ensemble-uri, orchestrare

Document de rațiune de design, 29.10.2026. Sursele din secțiunea 7 au fost deschise și citite; cifrele sunt cele din sursă. [neverificat] marchează ce nu am putut confirma la sursa primară; „inferență" marchează o concluzie a noastră, fără sursă directă.

## 1. RAG hibrid și citări

**Fuziune.** RRF adună 1/(k + rang) peste liste. Autorii au fixat k = 60 într-un pilot, valoare aproape optimă, dar necritică; RRF a depășit Condorcet, CombMNZ și cel mai bun sistem individual cu 4-5% în medie [1]. Lecție: fuzionăm BM25 și vectorii pe rang, fără normalizarea scorurilor.

**BM25 și vectori pe text normativ.** BEIR: BM25 e un baseline robust în afara domeniului [2]. Pe BSARD (22.600+ articole de lege) BM25 are R@100 51,33%; bi-encoderele antrenate pentru retrieval ating 71,63-74,78%, iar embeddings preantrenate folosite direct doar 4,21% [3]. Lecție: păstrăm ambele benzi și măsurăm pe corpusul nostru. Pentru BM25 în română indexăm și forma fără diacritice, fiindcă reclamanții scriu adesea fără ele (inferență).

**Chunking.** LegalBench-RAG (6.858 perechi întrebare-răspuns): a câștigat Recursive Character Text Splitter fără reranker, iar rerankerul Cohere testat (rerank-english-v3.0) a fost mai slab decât lipsa lui [4]. Un prefix de context per chunk reduce eșecurile din top-20 cu 35% (embeddings), 49% (plus BM25) și 67% (plus reranking), de la 5,7% la 1,9% [5]. Lecție: chunk = regulă sau articol cu ID stabil, cu prefix (ID, act, secțiune) luat din structură, nu din LLM (inferență). Limite de text: Cohere v3 512 tokeni, v4 circa 128k, Titan v2 8.192 [6].

**Reranker.** Cohere Rerank 3.5 e listat pentru us-east-1, Amazon Rerank 1.0 nu [7]. Lecție: comutator în config, decis prin ablație.

**Embeddings și româna.** MMTEB (500+ sarcini, 250+ limbi) numește cel mai bun model public multilingual-e5-large-instruct [8]; pe MTEB engleză are 64,4, față de 64,0 pentru Cohere multilingual-v3 [9], deci nu dovedește nimic pentru română. Singurul studiu românesc găsit compară mE5, Jina-v3 și Qwen3, fără Cohere sau Titan [10]. Titan v2 listează româna, dar e optimizat pentru engleză, iar interogările între limbi sunt suboptime [6]. Cohere și Titan pe română: [neverificat]. Lecție: alegem pe 40-60 de interogări proprii RO/EN (recall@5), cu input_type search_document la indexare și search_query la interogare [6].

**Citări.** ALCE măsoară citation recall și precision cu un model NLI; pe ELI5 chiar cele mai bune modele nu au susținere completă în 50% din cazuri [11]. RAGAS evaluează fără adnotări umane [12]; ARES antrenează judecători pe date sintetice și cere câteva sute de adnotări umane [13]. Instrumentele comerciale de cercetare juridică cu RAG au halucinat 17-33% din timp [14]. Grounding din Bedrock Guardrails (Classic) listează engleza, franceza și spaniola; româna: [neverificat] [16]. Lecție: un strat determinist (fiecare ID citat există în setul recuperat) și un judecător NLI sau LLM pe eșantion.

## 2. Date sintetice cu LLM

Pe 10 sarcini de clasificare, modelele antrenate pe date reale le depășesc pe cele pe date sintetice: +16,9% Macro-F1 față de generarea zero-shot și +6,7% față de few-shot; exemplele reale în prompt adaugă +10,6% față de zero-shot, iar pe cele 6 sarcini cele mai subiective scăderea medie e 27,4% [17]. Lecție: sămânța e reală (șabloane și texte scrise de noi), LLM-ul doar parafrazează; categoriile de graniță, ca „autorizat sub manipulare" față de „neautorizat", se etichetează manual (inferență).

SuperGen filtrează după probabilitatea de generare și regularizează cu label smoothing [18]. Prompturile cu atribute (lungime, stil) ating performanța celor simple la 5% din cost și reduc bias-ul [19]. Înlocuirea datelor reale cu cele generate duce la colaps, acumularea nu [20]. Lecție: grilă de atribute (canal, registru, diacritice, greșeli, RO/EN/mixt, scenariu), sintetic cu pondere mai mică (inferență), fără reantrenare pe ieșirile propriului clasificator.

CheckList: teste de funcționalitate minimă, invarianță și direcție; utilizatorii au scris de două ori mai multe teste [21]. Lecție: hard negatives sunt perechi minimale care schimbă clasa („nu am autorizat" / „am autorizat, dar am fost păcălit").

GroupKFold nu lasă același grup în antrenare și în test [22]. Lecție: grup = șablon plus familia de parafraze; raportăm separat testul pe șabloane nevăzute și setul de aur scris de mână.

## 3. Ensemble-uri pentru fraudă și AML

**Stacking și tabular.** Meta-modelul se antrenează pe predicții out-of-fold, iar modelele de bază se refac pe tot setul [22][23]. Lecție: foldurile se grupează pe șablon, altfel parafrazele aceluiași șablon scurg. Pe circa 10.000 de exemple, arborii rămân state-of-the-art față de rețelele neuronale [26]; LightGBM e de până la peste 20 de ori mai rapid decât GBDT clasic, cu acuratețe aproape neschimbată [25]. În Isolation Forest, anomaliile ajung la căi mai scurte în arbori aleatori [24][22]; îl folosim ca trăsătură, nu ca decident.

**Grafuri.** Elliptic: Random Forest a bătut GCN, cu split temporal 70:30 (primii 34 din 49 de pași); doar ~2% din noduri sunt etichetate ilicit [27]. AMLworld: seturi sintetice HI/LI, Small/Medium/Large, cu etichete complete (în datele reale multe spălări nu sunt detectate) și tipare fan-in, fan-out, scatter-gather, ciclu [28]. Multi-GNN: până la +30% F1 pe clasa minoritară față de un GNN standard, la nivelul baseline-urilor pe arbori sau peste [29]. Lecție: M5 = LightGBM pe trăsături de graf (fan-in/out, tranzit sub 24h, vârsta contului, PPR), GNN opțional. Random walk with restart (familia personalized PageRank), semi-supervised learning și belief propagation duc la o problemă similară de inversare de matrice [30]; seed-urile PPR vin doar din perioada de antrenare.

**Split-uri și calibrare.** Manualul ULB cere validare prequential și un interval între antrenare și validare, fiindcă etichetele sosesc târziu [31]. Lecție: M2 cu split temporal și gap, M5 pe componente conexe plus timp, niciodată aleator. Sigmoid merge la eșantioane mici, isotonic doar peste circa 1.000 de exemple, cu calibrator pe date independente [22]; isotonic se supraajustează la date puține [32]. Raportăm Brier și curba de fiabilitate.

## 4. Orchestrare și siguranță

Send(nod, stare), returnat dintr-o muchie condiționată, lansează câte un nod pe element; ramurile rulează în același superpas, iar starea comună are nevoie de reducer, de exemplu Annotated[list, add]. interrupt() cere checkpointer durabil și același thread_id; la reluare nodul rulează de la început, deci efectele dinainte trebuie să fie idempotente [33]. Lecție: thread_id = case_id, interrupt la începutul nodului de aprobare, rambursare simulată cu cheie de idempotență.

CaMeL separă un LLM privilegiat (vede doar cererea utilizatorului) de unul în carantină (fără tool-uri, ieșire în schemă Pydantic); rezolvă 77% din sarcinile AgentDojo cu securitate demonstrabilă, față de 84% fără apărare [34]. Dual LLM: ieșirea nefiltrată din carantină nu ajunge la LLM-ul privilegiat, iar autorul admite că nu e 100% sigur [35]. LLM map-reduce: un agent izolat per document, ieșire constrânsă (boolean, număr), reduce fără LLM sau cu verificări stricte [36]. Lecție: LLM-ul nostru izolat e Q-LLM (enumerări și numere, fără tool-uri), Send e etapa map, reduce e cod; pasajele din precedente sunt tot date neîncrezute; indecșii RAG se separă pe zone, ca să respecte zidul (inferență).

Verificare numerică a scrisorilor: orice sumă, dată, termen sau ID din text trebuie să existe în fișa de fapte a motorului de reguli, altfel scrisoarea merge la om (decizie proprie, fără sursă externă). Un preprint AML din 2026 raportează, pe date sintetice, validitate a citărilor de 0,98 și mai puține erori numerice cu probe obligatorii [15]; verificarea Bedrock nu e garantată pentru română [16].

## 5. Implementări reale documentate

**UK.** Din 7.10.2024, pentru Faster Payments și CHAPS: plafon 85.000 GBP, rambursare în 5 zile lucrătoare (rezultat în maximum 35), excepție pentru complicitate sau neglijență gravă, costul împărțit 50:50 între bănci [37]. Pe 7.10.2024-30.06.2025, PSR raportează 84% din cereri rezolvate în 5 zile lucrătoare, 97% în 35, 112 mil. GBP rambursați și 126.000 de cereri, cu circa 15% mai puține [37]. Pay.UK RCMS e un sistem comun de cereri, cu comunicare bidirecțională între banca trimițătoare și cea primitoare [38]. Lecție: dosarul are ceasuri pe etape și canal bidirecțional cu banca beneficiarului (camt.056).

**Mastercard și Visa.** Consumer Fraud Risk dă băncii expeditorului un scor în timp real; alertele pentru banca primitoare au arătat, în teste offline inițiale, +60% la identificarea timpurie a conturilor de cărăuși, fără metodologie publicată [39]. Rezultate bancare publicate și verificabile: negăsite [neverificat]. Visa RDR cere comerciantului, înaintea disputei formale, să accepte răspunderea; dacă acceptă, tranzacția nu se numără ca dispută [40]; cifre independente: [neverificat]. Lecție: raportăm rezultatele ca offline, pe date sintetice, și ținem în audit o stare „rezolvat înainte de dispută".

**UE și EBA/BCE.** Acordul provizoriu PSR/PSD3 (27.11.2025): rambursare integrală când escrocul s-a dat drept angajat al furnizorului, dacă clientul raportează la poliție și informează furnizorul; verificarea numelui beneficiarului; răspunderea platformelor [41]. La 29.10.2026 nu e publicat în JO: Consiliul urmează să adopte poziția în primă lectură [42], iar plenara indicativă e 14.12.2026 [43]. Lecție: „raport la poliție" e parametru [U]. EBA-BCE (15.12.2025): fraudă de 4,2 mld. EUR în 2024 față de 3,5 mld. EUR în 2023; utilizatorii au suportat circa 85% din pierderile la transferuri [44]. Cifre pentru România: [neverificat] (nu apar în comunicat; raportul complet nu l-am deschis).

## 6. Ce adoptăm în VersoML

| Decizie | Dovadă | Sursă |
|---|---|---|
| BM25 + vectori, fuziune RRF (k = 60 în config) | RRF bate Condorcet cu 4-5%; BM25 robust în afara domeniului | [1](http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf), [2](https://arxiv.org/abs/2104.08663) |
| Chunk = regulă sau articol cu ID, prefix din structură; rerank Cohere 3.5 ca flag, după ablație | Prefixul scade eșecurile top-20 cu 35-49%; reranker general mai slab pe text juridic; Rerank 3.5 e listat pentru us-east-1 | [5](https://www.anthropic.com/news/contextual-retrieval), [4](https://arxiv.org/abs/2408.10343), [7](https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-supported.html) |
| Embedder ales pe 40-60 de interogări proprii RO/EN | Nicio comparație publică Cohere/Titan pe română | [6](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html), [10](https://doi.org/10.3390/app152212219) |
| Citări: ID-uri verificate determinist, NLI pe eșantion | Susținere incompletă în 50% din cazuri; RAG juridic comercial 17-33% halucinații | [11](https://arxiv.org/abs/2305.14627), [14](https://arxiv.org/abs/2405.20362) |
| Date sintetice: sămânță reală, grilă de atribute, acumulare, hard negatives | Real peste sintetic cu 6,7-16,9% Macro-F1; atribute la 5% din cost | [17](https://arxiv.org/abs/2310.07849), [19](https://arxiv.org/abs/2306.15895), [20](https://arxiv.org/abs/2404.01413) |
| Teste CheckList; evaluare pe șabloane nevăzute (GroupKFold) | De 2 ori mai multe teste și de ~3 ori mai multe defecte găsite | [21](https://arxiv.org/abs/2005.04118), [22](https://scikit-learn.org/stable/modules/cross_validation.html) |
| Stacking cu predicții out-of-fold grupate pe șablon; LightGBM pentru M2 și M5; Isolation Forest ca trăsătură | Meta-modelul se antrenează pe predicții out-of-fold; arborii rămân state-of-the-art la ~10.000 de exemple | [22](https://scikit-learn.org/stable/modules/ensemble.html), [26](https://arxiv.org/abs/2207.08815) |
| M5: trăsături de graf plus PPR (seed-uri doar din antrenare) | RF a bătut GCN pe Elliptic; PPR și RWR sunt guilt-by-association | [27](https://arxiv.org/abs/1908.02591), [30](https://mlanthology.org/ecmlpkdd/2011/koutra2011ecmlpkdd-unifying) |
| Split temporal cu gap (M2), pe componente (M5); calibrare sigmoid sub ~1.000 de pozitive | Etichete tardive; isotonic se supraajustează pe date puține | [31](https://fraud-detection-handbook.github.io/fraud-detection-handbook/Chapter_5_ModelValidationAndSelection/ValidationStrategies.html), [32](https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf) |
| Send pentru colectori; interrupt cu efecte idempotente | Același superpas; nodul reia de la început | [33](https://docs.langchain.com/oss/python/langgraph/interrupts) |
| LLM izolat ca Q-LLM cu ieșire tipizată; indecși RAG pe zone | 77% din sarcini cu securitate demonstrabilă | [34](https://arxiv.org/abs/2503.18813), [36](https://arxiv.org/abs/2506.08837) |
| Verificator numeric al scrisorilor pe fișa de fapte | Ancorarea reduce erorile numerice; Bedrock nu garantează româna | [15](https://arxiv.org/abs/2604.19755), [16](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html) |

## 7. Surse

1. Cormack, Clarke, Büttcher (2009). Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods. SIGIR'09. http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
2. Thakur et al. (2021). BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models. NeurIPS 2021 Datasets and Benchmarks. https://arxiv.org/abs/2104.08663
3. Louis, Spanakis (2022). A Statutory Article Retrieval Dataset in French. ACL 2022. https://arxiv.org/abs/2108.11792
4. Pipitone, Houir Alami (2024). LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain. https://arxiv.org/abs/2408.10343
5. Anthropic (19.09.2024). Contextual retrieval in AI systems. https://www.anthropic.com/news/contextual-retrieval
6. AWS, Amazon Bedrock User Guide. Cohere Embed v3; Cohere Embed v4; Amazon Titan Text Embeddings models. https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html ; https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v4.html ; https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html
7. AWS, Amazon Bedrock User Guide. Supported Regions and models for reranking in Amazon Bedrock. https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-supported.html
8. Enevoldsen et al. (2025). MMTEB: Massive Multilingual Text Embedding Benchmark. ICLR 2025. https://arxiv.org/abs/2502.13595
9. Wang et al. (2024). Multilingual E5 Text Embeddings: A Technical Report. https://arxiv.org/abs/2402.05672
10. Guțu, Popescu (2025). From Dataset to Model: A Romanian-English Corpus and Fine-Tuned Cross-Lingual Embeddings for Text and Tabular Retrieval. Applied Sciences 15(22), 12219. https://doi.org/10.3390/app152212219
11. Gao, Yen, Yu, Chen (2023). Enabling Large Language Models to Generate Text with Citations. EMNLP 2023. https://arxiv.org/abs/2305.14627
12. Es, James, Espinosa-Anke, Schockaert (2023). Ragas: Automated Evaluation of Retrieval Augmented Generation. https://arxiv.org/abs/2309.15217
13. Saad-Falcon, Khattab, Potts, Zaharia (2023). ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems. NAACL 2024. https://arxiv.org/abs/2311.09476
14. Magesh et al. (2024). Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools. https://arxiv.org/abs/2405.20362
15. Torres, Cheng, Hu (2026). Explainable AML Triage with LLMs: Evidence Retrieval and Counterfactual Checks. https://arxiv.org/abs/2604.19755
16. AWS, Amazon Bedrock User Guide. Use contextual grounding check to filter hallucinations in responses. https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html
17. Li, Zhu, Lu, Yin (2023). Synthetic Data Generation with Large Language Models for Text Classification: Potential and Limitations. EMNLP 2023. https://arxiv.org/abs/2310.07849
18. Meng, Huang, Zhang, Han (2022). Generating Training Data with Language Models: Towards Zero-Shot Language Understanding. NeurIPS 2022. https://arxiv.org/abs/2202.04538
19. Yu et al. (2023). Large Language Model as Attributed Training Data Generator: A Tale of Diversity and Bias. NeurIPS 2023. https://arxiv.org/abs/2306.15895
20. Gerstgrasser et al. (2024). Is Model Collapse Inevitable? Breaking the Curse of Recursion by Accumulating Real and Synthetic Data. https://arxiv.org/abs/2404.01413
21. Ribeiro, Wu, Guestrin, Singh (2020). Beyond Accuracy: Behavioral Testing of NLP models with CheckList. ACL 2020. https://arxiv.org/abs/2005.04118
22. scikit-learn 1.9.1 documentation. Cross-validation: evaluating estimator performance; Ensembles: Gradient boosting, random forests, bagging, voting, stacking; Novelty and Outlier Detection; Probability calibration. https://scikit-learn.org/stable/modules/cross_validation.html ; https://scikit-learn.org/stable/modules/ensemble.html ; https://scikit-learn.org/stable/modules/outlier_detection.html ; https://scikit-learn.org/stable/modules/calibration.html
23. Wolpert (1992). Stacked generalization. Neural Networks 5(2), 241-259. https://doi.org/10.1016/S0893-6080(05)80023-1 (doar metadate, verificate în Crossref)
24. Liu, Ting, Zhou (2008). Isolation Forest. ICDM 2008, 413-422. https://doi.org/10.1109/ICDM.2008.17 (doar metadate, verificate în Crossref)
25. Ke et al. (2017). LightGBM: A Highly Efficient Gradient Boosting Decision Tree. NeurIPS 2017. https://papers.nips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html
26. Grinsztajn, Oyallon, Varoquaux (2022). Why do tree-based models still outperform deep learning on tabular data? https://arxiv.org/abs/2207.08815
27. Weber et al. (2019). Anti-Money Laundering in Bitcoin: Experimenting with Graph Convolutional Networks for Financial Forensics. https://arxiv.org/abs/1908.02591
28. Altman et al. (2023). Realistic Synthetic Financial Transactions for Anti-Money Laundering Models. https://arxiv.org/abs/2306.16424
29. Egressy et al. (2024). Provably Powerful Graph Neural Networks for Directed Multigraphs. AAAI 2024. https://arxiv.org/abs/2306.11586
30. Koutra et al. (2011). Unifying Guilt-by-Association Approaches: Theorems and Fast Algorithms. ECML PKDD 2011, 245-260. https://mlanthology.org/ecmlpkdd/2011/koutra2011ecmlpkdd-unifying
31. ULB Machine Learning Group. Validation strategies (cap. 5), în Reproducible Machine Learning for Credit Card Fraud Detection - Practical Handbook. https://fraud-detection-handbook.github.io/fraud-detection-handbook/Chapter_5_ModelValidationAndSelection/ValidationStrategies.html
32. Niculescu-Mizil, Caruana (2005). Predicting Good Probabilities With Supervised Learning. ICML 2005. https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf
33. LangChain, documentația LangGraph. Graph API overview; Interrupts. https://docs.langchain.com/oss/python/langgraph/graph-api ; https://docs.langchain.com/oss/python/langgraph/interrupts
34. Debenedetti et al. (2025). Defeating Prompt Injections by Design. https://arxiv.org/abs/2503.18813
35. Willison (25.04.2023). The Dual LLM pattern for building AI assistants that can resist prompt injection. https://simonwillison.net/2023/Apr/25/dual-llm-pattern/
36. Beurer-Kellner et al. (2025). Design Patterns for Securing LLM Agents against Prompt Injections. https://arxiv.org/abs/2506.08837
37. Payment Systems Regulator. APP fraud reimbursement protections; APP scams; One year on: Impact of APP reimbursement on victims (08.10.2025). https://www.psr.org.uk/information-for-consumers/app-fraud-reimbursement-protections/ ; https://www.psr.org.uk/our-work/app-scams/ ; https://www.psr.org.uk/news-and-updates/latest-news/news/one-year-on-impact-of-app-reimbursement-on-victims/
38. Pay.UK. Reimbursement Claims Management System (RCMS). https://www.wearepay.uk/rcms/
39. Mastercard (24.09.2024). Mastercard expands first-of-its-kind AI technology to help banks protect more consumers from scams in real time. https://newsroom.mastercard.com/news/press/2024/september/mastercard-expands-first-of-its-kind-ai-technology-to-help-banks-protect-more-consumers-from-scams-in-real-time
40. Visa (29.10.2020). Article ID AI10571, Rapid Dispute Resolution: Proper Identification of RDR Transactions and Service Activation. https://usa.visa.com/dam/VCOM/global/support-legal/documents/proper-identification-of-rdr-transactions-and-service-activation.pdf
41. Parlamentul European (27.11.2025). Payment services deal: More protection from online fraud and hidden fees. https://www.europarl.europa.eu/news/en/press-room/20251121IPR31540/payment-services-deal-more-protection-from-online-fraud-and-hidden-fees
42. Consiliul UE (23.10.2026). Nota I/A 14798/26, adoptarea poziției Consiliului în primă lectură (2023/0210(COD)). https://data.consilium.europa.eu/doc/document/ST-14798-2026-INIT/en/pdf
43. Parlamentul European. Procedure File 2023/0210(COD), Legislative Observatory. https://oeil.europarl.europa.eu/oeil/en/procedure-file?reference=2023/0210(COD)
44. EBA, ECB (15.12.2025). Joint EBA-ECB report on payment fraud: strong authentication remains effective but fraudsters are adapting. https://www.eba.europa.eu/publications-and-media/press-releases/joint-eba-ecb-report-payment-fraud-strong-authentication-remains-effective-fraudsters-are-adapting

**Repo-uri verificate** (API-ul GitHub, 29.10.2026; „fost" marchează redirecționări):
- https://github.com/IBM/AML-Data (datele AMLworld; IBM/AMLworld dă 404; pagina Kaggle: [neverificat], cere reCAPTCHA)
- https://github.com/IBM/Multi-GNN
- https://github.com/langchain-ai/langgraph
- https://github.com/vibrantlabsai/ragas (fost explodinggradients/ragas)
- https://github.com/princeton-nlp/ALCE
- https://github.com/stanford-futuredata/ARES
- https://github.com/data-privacy-stack/presidio (fost microsoft/presidio)
- https://github.com/google-research/camel-prompt-injection
- https://github.com/dorianbrown/rank_bm25
- https://github.com/lightgbm-org/LightGBM (fost microsoft/LightGBM)
- https://github.com/Fraud-Detection-Handbook/fraud-detection-handbook
