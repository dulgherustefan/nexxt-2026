# Surse OSINT: ce dau, cum se accesează, condiții, verificare

Verificările live s-au făcut de pe mașina de dezvoltare pe **28.10.2026**, cu câte o cerere pe sursă (User-Agent `VersoMLBot/0.1 (hackathon NEXXT 2026)`). „Da" înseamnă că endpoint-ul a răspuns cum e descris; „nu" înseamnă că nu l-am putut verifica (lipsă cheie, eroare, nefolosit). Condițiile de utilizare marcate [U] nu au fost citite în documentația furnizorului în această sesiune.

Modurile (`VERSOML_OSINT_MODE`): `fixture` citește doar `fixtures/<tool>/<cheie>.json`; `live` cheamă sursa (cu cache proaspăt în `var/osint_cache.db`); `auto` încearcă cache → sursă → cache expirat → fixture. Țintele sintetice (.example, .test, TEST-NET, +40 700 000 xxx, registrul sintetic) nu pleacă niciodată spre o sursă reală.

## Domenii și infrastructură

| Sursă | Ce dă | Endpoint | Cheie | Limite și condiții | Verificat live |
|---|---|---|---|---|---|
| rdap.org (bootstrap IANA) | data înregistrării, registrar, contact de abuz, status, NS | `GET https://rdap.org/domain/<d>` (302 spre registrul RDAP) | nu | gratuit, best effort | da, 28.10.2026: example.com 200; **.ro → 404 „No RDAP service"** |
| IANA RDAP bootstrap | TLD → server RDAP | `https://data.iana.org/rdap/dns.json` | nu | — | da, 28.10.2026 (nefolosit direct; rdap.org îl aplică) |
| WHOIS ROTLD (port 43) | .ro: „Registered On", registrar, NS, status; fără titular | `whois.rotld.ro:43` | nu | termenii ROTLD: doar scop tehnic, administrativ sau juridic; interzisă extragerea în masă | da, 28.10.2026 (format „Registered On: Before 2001") |
| crt.sh | certificatele din CT: emitent, `not_before`, `entry_timestamp` | `GET https://crt.sh/?q=<d>&output=json` | nu | lent și instabil: ~21 s pentru example.com, prima încercare a expirat la 20 s | da, 28.10.2026 (lent) |
| Cert Spotter (SSLMate) | emiterile din CT (rezerva lui crt.sh) | `GET https://api.certspotter.com/v1/issuances?domain=&include_subdomains=true&expand=dns_names&expand=issuer` | nu (opțională pentru cote mai mari) | cotă gratuită limitată [U] | da, 28.10.2026 (1,3 s) |
| Cloudflare DNS-over-HTTPS | A/AAAA/MX/NS/TXT în JSON | `GET https://cloudflare-dns.com/dns-query?name=&type=` cu `Accept: application/dns-json` | nu | — | da, 28.10.2026 |
| Google DNS-over-HTTPS | același format (rezervă) | `GET https://dns.google/resolve?name=&type=` | nu | — | da, 28.10.2026 |
| dnspython | rezolvitorul sistemului (ultima rezervă) | bibliotecă | nu | — | nu (rezervă neexersată live) |
| Wayback Machine CDX | prima captură a domeniului | `GET https://web.archive.org/cdx/search/cdx?url=&matchType=domain&output=json&fl=timestamp,original,statuscode&limit=1` | nu | limitat la rată | da, 28.10.2026 |
| Wayback availability | captura cea mai apropiată de 1996 (rezervă) | `GET https://archive.org/wayback/available?url=&timestamp=19960101` | nu | a răspuns 429 | nu (429 pe 28.10.2026) |
| ip-api.com | țara, ASN, ISP, indicatorii hosting/proxy | `GET http://ip-api.com/json/<ip>?fields=...` | nu | varianta gratuită: doar HTTP, uz necomercial, ~45 cereri/min [U] | da, 28.10.2026 |
| ipinfo.io | țara, organizația (ASN) (rezervă) | `GET https://ipinfo.io/<ip>/json` | nu (token pentru mai mult) | fără token, cotă mică | da, 28.10.2026 |
| ipwho.is | geolocalizare | `GET https://ipwho.is/<ip>` | nu | — | da, 28.10.2026 (nefolosit în cod) |

## Liste de amenințări

| Sursă | Ce dă | Endpoint | Cheie | Limite și condiții | Verificat live |
|---|---|---|---|---|---|
| OpenPhish, feed comunitar | URL-uri de phishing (actualizat la ~6 ore, după notele de research) | `https://openphish.com/feed.txt`; oglindă `https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt` | nu | feed-urile premium sunt comerciale; uzul comercial al celui comunitar [U]. Îl ținem în cache 6 ore | da, 28.10.2026 (ambele URL-uri, 14,6 KB) |
| URLhaus (abuse.ch) | URL-uri de malware după gazdă sau URL | `POST https://urlhaus-api.abuse.ch/v1/host/` sau `/v1/url/`, header `Auth-Key` | da, `URLHAUS_AUTH_KEY` (cont gratuit) | [U] | da: fără cheie răspunde 401 |
| urlscan.io (search) | scanările publice: URL, IP, ASN, verdict, captură | `GET https://urlscan.io/api/v1/search/?q=domain:<d>`, header `API-Key` | da, `URLSCAN_API_KEY` | cote pe plan; folosiți doar căutarea, nu trimiteți scanări cu date de client | da: **căutarea fără cheie a răspuns 200**; tool-ul cere totuși cheia, cum s-a cerut |
| VirusTotal v3 | detecțiile motoarelor pentru domeniu, reputația | `GET https://www.virustotal.com/api/v3/domains/<d>`, header `x-apikey` | da, `VIRUSTOTAL_API_KEY` | API-ul public: ~4 cereri/min, 500/zi, uz necomercial (note de research, [U]) | da: fără cheie răspunde 401 |
| Google Safe Browsing v4 (Lookup) | potriviri pe listele Google | `POST https://safebrowsing.googleapis.com/v4/threatMatches:find`, header `X-Goog-Api-Key` (cheia nu stă în URL) | da, `GOOGLE_SAFE_BROWSING_KEY` | uz necomercial; pentru bancă: Google Web Risk (plătit) | da: fără cheie răspunde 403 |
| Google Web Risk | aceeași funcție, comercial | `uris.search` | da | plătit | nu (neimplementat) |
| PhishStats | bază de date de phishing | `https://api.phishstats.info/api/phishing` | nu | — | nu (502 pe 28.10.2026; neimplementat) |

## Registre românești și europene

| Sursă | Ce dă | Endpoint | Cheie | Limite și condiții | Verificat live |
|---|---|---|---|---|---|
| ANAF, serviciul web TVA v9 | firma după CUI: denumire, adresă, stare (inclusiv radiere), inactiv, TVA, TVA la încasare, split TVA, e-Factura, data înregistrării, CAEN | `POST https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva`, corp `[{"cui": <int>, "data": "AAAA-LL-ZZ"}]` | nu | ≤100 CUI-uri pe cerere, 1 cerere/s (impus în `base.HOST_MIN_INTERVAL_S`); **răspunde HTTP 404 cu JSON când niciun CUI nu e găsit**; fără învelișul `{"cod":200}` din documentație | da, 28.10.2026 (found și notFound) |
| VIES (Comisia Europeană) | validitatea codului de TVA, nume, adresă | `GET https://ec.europa.eu/taxation_customs/vies/rest-api/ms/RO/vat/<cui>` | nu | — | da, 28.10.2026 (nefolosit; candidat de rezervă pentru ANAF) |
| BNR, cursul de referință | cursurile zilnice (XML) | `GET https://curs.bnr.ro/nbrfxrates.xml`; **`www.bnr.ro/nbrfxrates.xml` redirecționează acum spre prima pagină** | nu | publicat zilnic | da, 28.10.2026 (EUR = 5,3495 lei) |
| Frankfurter (BCE) | EUR/RON, cursul BCE (rezervă; nu e cursul BNR) | `GET https://api.frankfurter.dev/v1/latest?base=EUR&symbols=RON` | nu | — | da, 28.10.2026 (5,3488 pentru 27.10) |
| ONRC open data (data.gov.ro) | extrase cu firmele înregistrate | portal | nu | [U] | nu (neverificat, neimplementat) |

## Sancțiuni

| Sursă | Ce dă | Endpoint | Cheie | Limite și condiții | Verificat live |
|---|---|---|---|---|---|
| OpenSanctions `eu_fsf` (CSV simplu) | ținte din lista UE de sancțiuni financiare | `https://data.opensanctions.org/datasets/latest/eu_fsf/targets.simple.csv` (307 spre `artifacts/...`) | nu | **CC BY-NC 4.0: uz necomercial; producția cere licență**. Se descarcă la cerere în `var/opensanctions/`, cel mult o dată pe zi | da, 28.10.2026 (HEAD 200 după redirecționare) |
| OpenSanctions API (match) | potrivire găzduită | `POST https://api.opensanctions.org/match/default` | da | — | da: fără cheie răspunde 401 (neimplementat) |
| yente (local) | API de potrivire pe date OpenSanctions | Docker + Elasticsearch | nu | aceeași licență a datelor | nu (calea de producție, neinstalată) |
| Lista sintetică | entități inventate pentru teste | `fixtures/sanctions_screen/watchlist.json` | — | — | — |

## Căutare web și presă

Lanțul e fix: Serper → Brave → Tavily → Exa → DuckDuckGo. Un furnizor fără cheie se sare; unul care dă eroare sau zero rezultate trece la următorul. Interogările cu CNP, număr de card sau IBAN sunt refuzate înainte de orice apel.

| Sursă | Endpoint | Cheie | Limite și condiții | Verificat live |
|---|---|---|---|---|
| Serper (Google) | `POST https://google.serper.dev/search` și `/news`, header `X-API-KEY`, corp `{q, num, gl:"ro", hl:"ro"}`, rezultate în `organic` / `news` | `SERPER_API_KEY` | credite (1 pe cerere); plan gratuit | da, 28.10.2026 (cheia din `.env`, verificată de orchestrator și în testul de fum) |
| Brave Search | `GET https://api.search.brave.com/res/v1/web/search` (știri: `/news/search`), header `X-Subscription-Token`, `country=RO`, `search_lang=ro` | `BRAVE_API_KEY` | [U] | nu (fără cheie) |
| Tavily | `POST https://api.tavily.com/search`, `Authorization: Bearer`, `topic` general/news | `TAVILY_API_KEY` | [U] | nu (fără cheie) |
| Exa | `POST https://api.exa.ai/search`, header `x-api-key`, `userLocation: "RO"`, `category: "news"` | `EXA_API_KEY` | [U] | nu (fără cheie) |
| DuckDuckGo (`ddgs` 9) | biblioteca `ddgs` (`text`, `news`, `region="ro-ro"`) | nu | neoficial (scraping), limitat la rată, instabil: interogările lungi cu OR expiră des, așa că îi trimitem o formă scurtă (`search.ddg_query`) | da, 28.10.2026 (text: 3 rezultate în 3 s; news: 3 în 5,4 s; unele interogări au expirat la 10 s) |
| Jina Reader | `GET https://r.jina.ai/<url>` (`Authorization: Bearer` opțional) | opțional `JINA_API_KEY` | fără cheie: cotă mică; pagina se randează la Jina, nu la noi | da, 28.10.2026 (6,4 s) |

## Telefoane

Nicio sursă fără cheie nu dă operatorul unui număr românesc (portabilitatea numerelor face prefixul neconcludent). `phone_intel` normalizează la E.164, deduce tipul din prima cifră a numărului național [U] (7 mobil, 2/3 fix, 800 gratuit, 801 cost partajat, 90x tarif special) și caută raportări publice prin lanțul de căutare. API-urile de validare din lista public-apis (Numverify, Veriphone, Abstract) cer toate cheie și nu sunt implementate.

## Selecția din lista public-apis

Lista `public-apis/public-apis` a fost citită pe 28.10.2026 (secțiunile Anti-Malware, Security, Open Data, Government, Finance, Currency Exchange, Geocoding, Phone, Email). Ce am implementat sau păstrat drept candidat:

- **Implementate:** URLhaus, URLScan.io, VirusTotal, Google Safe Browsing (Anti-Malware); OpenSanctions, Archive.org (Open Data); ip-api, IP Address Details/ipinfo (Geocoding); Frankfurter (Currency Exchange).
- **Candidați fără cheie:** PhishStats (căzut azi), IPWhois.net Blacklist, VATComply (validare TVA prin VIES), Open Government Romania (data.gov.ro), SSL Labs (lent).
- **Candidați cu cheie:** AlienVault OTX, AbuseIPDB, GreyNoise, Shodan, Censys, OpenCorporates.
- **Neimplementate intenționat:** validatoarele de telefon și e-mail cu cheie; nu aduc ceva ce nu facem local.

## Metode (fără dependențe noi)

- **Permutări de domenii:** fuzzerii din dnstwist (elceef/dnstwist, Apache-2.0), reimplementați în `lookalike.py`, nu copiați: addition, bitsquatting, homoglyph, hyphenation, insertion, omission, repetition, replacement, transposition, vowel-swap, subdomain, TLD swap, dictionary, plural.
- **Schelet de confusables:** un subset compact din Unicode TR39 (chirilic și grec → latin), plus cifre și secvențe (0/o, 1/l/i, rn/m, vv/w, cl/d), după decodarea punycode (IDNA 2008, pachetul `idna`).
- **Distanțe:** Damerau-Levenshtein și Jaro-Winkler din `rapidfuzz`; ponderile modelului logistic sunt în `lookalike.WEIGHTS`.
- **Text din pagini:** `trafilatura` (cu rezervă pe BeautifulSoup); M4 compară 3-grame de cuvinte, simhash, câmpurile formularelor, 4-grame de taguri și paleta CSS, fără randare.
- **Fixture-uri:** toate sintetice (`synthetic: true`), pe nume rezervate (.example, .test, TEST-NET, ASN-uri de documentare 64496–64511, telefoane +40 700 000 xxx). Excepție: `bnr_fx_rates/` conține instantaneul public al cursurilor BNR din 28.10.2026.
