# Konstytucja kio-orzeczenia-mcp

Wersja: 0.1.0 (2026-05-20)
Status: Draft POC

Ten dokument definiuje 4 nieprzekraczalne zasady governance dla konektora MCP do orzecznictwa Krajowej Izby Odwolawczej (KIO) przy Urzedzie Zamowien Publicznych (UZP).

---

## Art. 1. Tylko publiczne dane

`kio-orzeczenia-mcp` konsumuje wylacznie publicznie dostepna baze orzeczen KIO udostepniana pod adresem `https://orzeczenia.uzp.gov.pl`. Sa to oficjalne, publikowane przez UZP orzeczenia Krajowej Izby Odwolawczej - orzecznictwo publicznie udostepnione na podstawie ustawy z 6 wrzesnia 2001 r. o dostepie do informacji publicznej (Dz.U. 2001 nr 112 poz. 1198 z pozn. zm.) oraz ustawy z 11 wrzesnia 2019 r. - Prawo zamowien publicznych.

Orzeczenia KIO nie sa zrodlem prawa w rozumieniu art. 87 Konstytucji RP - sa orzeczeniami stosowania prawa, ktore powszechnie sluza praktyce kancelaryjnej jako material referencyjny.

Konektor:
- NIE omija zadnych zabezpieczen (brak CAPTCHA-solving, brak fake-CSRF)
- NIE deanonimizuje stron postepowania ponad to, co publikuje UZP
- NIE przechowuje pelnych tresci orzeczen w audit log (tylko sygnatury i metadane)
- NIE modyfikuje danych zrodlowych

Jezeli UZP zmieni regulamin lub Terms of Service i zabroni programatycznego dostepu - konektor zostaje wstrzymany. Decyzja Wieslawa Mazura jako Administratora.

## Art. 2. Rate limit 1 req/s obowiazkowy

Defaultowy rate limit to **1 request na sekunde** dla calego serwera (globalny lock, nie per-tool). Wartosc dobrana konserwatywnie - bez znajomosci faktycznej pojemnosci infrastruktury UZP wybieramy nizszy prog niz dla wiekszych instytucjonalnych portali (np. api.sejm.gov.pl, ktore nie publikuja oficjalnego rate limitu, ale obsluguja zauwazalnie wieksze obciazenie).

- Konfigurowalny przez env `KIO_MCP_RATE_LIMIT` (float, requests per second), ale nie wyzej niz **2.0** (decyzja arbitralna POC, do walidacji - patrz `DISCOVERY.md` sekcja "Otwarte pytania")
- Jezeli `KIO_MCP_RATE_LIMIT > 2.0` -> hard error przy starcie
- User-Agent obowiazkowy: `matematic-kio-mcp/{version} (+https://matematic.co; kontakt@matematic.co)`
- Retry-After respektowane bezwzglednie
- Backoff exponential przy 429/503

Cel: nie obciazyc nadmiernie infrastruktury UZP i identyfikowac sie jasno (kontakt@matematic.co).

## Art. 3. Audit log obowiazkowy

Kazde wywolanie kazdego z 5 narzedzi zapisuje wpis w `~/.matematic/audit/kio-orzeczenia-mcp.jsonl`:

- `ts` (ISO 8601 UTC)
- `tool` (nazwa narzedzia, np `kio_search`)
- `params_hash` (SHA-256 z parametrow - bez surowych danych)
- `result_summary` (np `{"items": 12, "total": 154}`)
- `source_urls` (lista pelnych URL trafionych endpointow)
- `latency_ms`
- `cache_hit` (bool)

**Czego NIE logujemy:**
- Pelnej tresci orzeczen (`reasoning`, `content_text`) - tylko sygnatury
- Danych osobowych stron postepowania (mimo ze sa publiczne, audit log to nasz wewnetrzny artefakt)

Audit log sluzy rozliczalnosci operatora - kazde wywolanie konektora pozostawia slad pozwalajacy zweryfikowac, co i kiedy zostalo pobrane. Decyzja o powolaniu na konkretny przepis (np. art. 12 rozporzadzenia (UE) 2024/1689 - AI Act, w zakresie record-keeping dla systemow AI wysokiego ryzyka) nalezy do podmiotu wdrazajacego konektor i wymaga osobnej oceny prawnej dla tego podmiotu. Sam konektor nie jest systemem AI wysokiego ryzyka w rozumieniu AI Act.

## Art. 4. Cytowania obowiazkowe

Kazdy `Orzeczenie` i `OrzeczenieSummary` zwracany przez konektor MUSI zawierac:

- `signature` w formacie kanonicznym `"KIO {nr}/{rok}"` (np `"KIO 2924/21"`)
- `human_readable_citation` w formacie `"Wyrok KIO z {YYYY-MM-DD}, sygn. KIO {nr}/{rok}"`
- `source_url` - pelny URL do `orzeczenia.uzp.gov.pl` (mozliwy do otwarcia przez czlowieka)
- `retrieved_at` (ISO 8601 UTC)

Cel: kazde orzeczenie zwracane przez konektor zawiera komplet metadanych pozwalajacych na bezposrednia weryfikacje w bazie UZP - sygnatura, link do oryginalu, data pobrania.

---

## Zmiany konstytucji

Zmiany w tym dokumencie wymagaja:
1. Wpisu w `DISCOVERY.md` z uzasadnieniem
2. Bump SEMVER konstytucji (MAJOR przy zmianie Art. 1-4, MINOR przy doprecyzowaniu, PATCH przy literowce)
3. Akceptacji Administratora (Wieslaw Mazur)

---

Konstytucja oparta na patternie spec-driven (cherry-pick github/spec-kit, MIT).
