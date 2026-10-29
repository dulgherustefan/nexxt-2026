# VersoML under the AI Act, GDPR and DORA

Classification note, 29 October 2026. Our reading of the texts and the sources below, not legal advice. *Unverified* marks what we could not check against a primary source.

## AI Act: outside Annex III

- Annex III point 5(b) covers AI that rates the creditworthiness of natural persons, "with the exception of AI systems used for the purpose of detecting financial fraud" [1]. Payment disputes and complaints appear nowhere in Annex III.
- VersoML handles disputes and detects fraud (M2, a first-party fraud signal; M5, money mules). We read it as not high-risk, so no Art. 6(3) assessment or registration is needed [1][2].
- This changes if a component starts using creditworthiness ("can the customer afford the loss", a credit limit). That is 5(b), and because it profiles natural persons, Art. 6(3) cannot take it out again.
- The AML zone scores accounts on objective, checkable facts and a person decides, which keeps it inside the exception to the Art. 5(1)(d) ban (see `docs/05_versoml_solutie_si_plan.md`).
- Art. 12 (logging) and Art. 14 (human oversight) do not bind us, but we build to them, since the EBA finds no equivalent for oversight and explanation in banking law [3]: the sealed evidence file is the log, the sign-off is the oversight.

| Obligation | Applies from |
|---|---|
| AI literacy for staff, Art. 4 | 2 February 2025 |
| General-purpose model duties, Arts. 53-55 (on Anthropic, not the bank) | 2 August 2025 |
| Transparency, Art. 50 | 2 August 2026 |
| Art. 50(2) marking, for systems on the market before 2 August 2026 | 2 December 2026 |
| High-risk obligations for Annex III systems, postponed | 2 December 2027 |

The postponement is the Digital Omnibus on AI, reported as Regulation (EU) 2026/1744, in force from 27 July 2026 [4][5][6]. We did not read the Official Journal text, so the number and dates rest on secondary sources (*unverified*). Also *unverified*: whether the Omnibus changed Art. 6(3) registration, and how the draft Commission guidelines on classification (19 May 2026) treat fraud detection.

## Art. 50: transparency

- Art. 50(1), telling people they deal with an AI system, applies when customers interact with it directly. VersoML customers get a letter; only bank staff use the console.
- Art. 50(2), machine-readable marking of generated text, falls on providers of systems that generate text, which a bank building the letter writer on Claude may be. Whether a letter a person reviews counts as "assistive function for standard editing" is open.
- Cheap either way: an "AI-assisted, human-approved" flag in the letter metadata and the evidence file, and a sentence in the letter saying a person reviewed it. Not built yet (item 13 in `reports/Cercetare îmbunătățiri agent VersoML.md`).

## GDPR Art. 22: a person signs every adverse outcome

- Refusing a PSD2 refund has legal effects. Decided solely by automated means, it falls under Art. 22, and a person who only rubber-stamps a score does not change that [7][8][9].
- The rules engine decides with a rule ID and a legal basis; automatic refunds under the cap favour the customer. The DP-02 guard sends every adverse outcome to a person: a late claim, the customer-fraud exception, recovery from the customer, and "next-day refund does not apply" for APP and credit fraud. DP-03 requires a rule, a basis and an explanation for every decision, as Dun & Bradstreet (C-203/22) asks [10]. The M2 score only sends a case to a person; it is never the reason for a refusal (`versoml/shared/rules/packs/dp.py`).
- Every letter names the ways to contest: ANPC, ANAF, BNR, CSALB and the courts (Art. 22(3)).
- This depends on items 1 to 4 of `reports/Cercetare îmbunătățiri agent VersoML.md`, open when this note was written: the graph pauses for every `requires_human`, NU_SE_APLICA_T1 included; the approver comes from the signed-in session and the approval is tied to the case, amount and verdict; the bank's facts beat the classifier's label; every approval, refusal and override carries a reason. Until then, Art. 22 is not fully covered.
- *Unverified*: ANSPDCP guidance on Art. 22 in banking. The Commission's November 2025 proposal to reword Art. 22 is only a proposal.

## DORA: Bedrock is an ICT third-party service

- DORA has applied since 17 January 2025 [11]. Amazon Web Services EMEA Sarl is on the European supervisors' first list of critical ICT third-party providers (November 2025) [12]; Anthropic is a subcontractor.
- The bank needs AWS and Anthropic in its register of information (Art. 28(3)), due diligence and a concentration check (Art. 29), and the Art. 30 contract terms with an exit plan, if dispute handling is a critical or important function. With a next-business-day refund deadline it most likely is (our inference).
- The demo calls Bedrock in us-east-1, because the hackathon account blocks the endpoint in EU regions (`versoml/config.py`). Production needs an EU region, pinned model versions and an exit plan. The rules, deadlines and evidence never depend on the model, and replay or offline mode keeps cases moving without it (item 29).
- *Unverified*: whether the EBA outsourcing guidelines still apply next to DORA; the DORA incident-reporting deadlines; which Romanian authority supervises the AI Act for banks (BNR and ANCOM are candidates).

## Sources

1. AI Act, Annex III: https://artificialintelligenceact.eu/annex/3/
2. Regulation (EU) 2024/1689 (AI Act): https://eur-lex.europa.eu/eli/reg/2024/1689/oj
3. EBA, "AI Act: implications for the EU banking and payments sector", 21 November 2025: https://www.eba.europa.eu/sites/default/files/2025-11/d8b999ce-a1d9-4964-9606-971bbc2aaf89/AI%20Act%20implications%20for%20the%20EU%20banking%20sector.pdf
4. Gibson Dunn, the AI Act Omnibus agreement: https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
5. CSA Labs, the Omnibus and the December 2027 deadline: https://labs.cloudsecurityalliance.org/research/csa-research-note-eu-ai-act-high-risk-deadline-omnibus-20260/
6. Usercentrics, on Regulation (EU) 2026/1744 (it says publication "should still be confirmed"): https://usercentrics.com/knowledge-hub/eu-ai-act-high-risk-delay-article-50-transparency-consent/
7. GDPR: https://eur-lex.europa.eu/eli/reg/2016/679/oj
8. CJEU C-634/21 SCHUFA, Bird & Bird summary: https://twobirds.com/en/insights/2023/global/key-takeaways-from-the-schufa-case-of-the-cjeu
9. WP29/EDPB guidelines on automated decisions (WP251rev.01): https://ec.europa.eu/newsroom/article29/items/612053
10. CJEU C-203/22 Dun & Bradstreet Austria, press release 22/25: https://curia.europa.eu/jcms/upload/docs/application/pdf/2025-02/cp250022en.pdf
11. Regulation (EU) 2022/2554 (DORA): https://eur-lex.europa.eu/eli/reg/2022/2554/oj
12. PwC Legal, the first list of critical ICT third-party providers: https://legal.pwc.de/en/news/articles/esas-publish-first-list-of-critical-ict-third-party-providers-under-dora
