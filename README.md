# VersoML

VersoML ajută o bancă să trateze plățile cu cardul pe care clienții spun că nu le-au făcut, de la contestație până la recuperarea banilor.

## Problema

Un client spune că nu el a făcut o plată cu cardul. După hotărârea CJUE C-70/25, banca trebuie să-i dea banii înapoi în 24 de ore lucrătoare, chiar dacă crede că a greșit, și abia apoi să verifice cazul.

Pe lângă rambursare, banca trebuie să strângă probele, să încerce să recupereze banii și să anunțe echipa AML, fără ca clientul să afle de anchetă. La Raiffeisen, cam 64% din reclamațiile din 2025 au fost de acest tip, prea multe pentru a fi tratate manual la timp.

## Ce face

1. **Rambursarea în 24 de ore lucrătoare.** Un motor de reguli decide dacă rambursarea e obligatorie. Cazurile defavorabile clientului sau peste plafon sunt aprobate de un om.
2. **Dosarul de probe.** Fiecare afirmație trimite la o probă cu sursă, oră și hash. Dosarul este sigilat (Merkle + Ed25519), astfel încât orice modificare ulterioară poate fi detectată.
3. **Recuperarea.** Rechemarea camt.056, chargeback-ul și raportul DNSC sunt pregătite ca ciorne și trimise doar după aprobarea unui om.
4. **Pista AML.** Contul care a primit banii este trimis către zona AML, separată de zona client, astfel încât nicio informație despre anchetă să nu ajungă la client.

Proiectul folosește doar date sintetice, generate pentru o bancă fictivă (Banca Demo). Poate fi folosit ca aplicație web sau ca server MCP.

## Pornire

Necesită Python 3.12 (prin [uv](https://docs.astral.sh/uv/)) și Node.js 20+.

```bash
uv sync
```

```bash
uv run versoml up
```

La prima rulare se generează datele, se antrenează modelele și se construiește interfața. Apoi pornesc zona client pe http://127.0.0.1:8000 și zona AML pe http://127.0.0.1:8001.

`versoml demo` rulează scenariul demo fără interfață, iar `versoml eval` rulează evaluarea.

Cheia AWS Bedrock se pune în `API_KEY.txt`, exclus din git. Fără cheie, aplicația rulează cu reguli și șabloane fixe.

## Arhitectură

Modelele de limbaj extrag informații din reclamație, construiesc argumente și redactează scrisori. Deciziile sunt luate de reguli deterministe, iar niciun model nu are acces la operațiuni care mută bani.

Reclamația este procesată de un model izolat, fără acces la instrumente, pentru a evita instrucțiunile ascunse introduse de escroci. Datele personale sunt pseudonimizate înainte de orice apel către model.

Zona client și zona AML rulează ca procese separate, cu baze de date separate. Spre AML se trimit doar faptele contestației, într-un format strict. Înapoi se primește doar un răspuns da/nu, dacă plata trebuie blocată. Scrisorile către client trec printr-un filtru care blochează orice informație despre anchetă.

Modelele ML clasifică contestațiile și identifică conturile-cărăuș. Ele oferă semnale, nu decizii.

## Documentație

- [Soluția și arhitectura](docs/05_versoml_solutie_si_plan.md)
- [Implementarea](docs/06_implementare.md)
