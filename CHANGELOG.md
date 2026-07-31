# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), SemVer.

## [0.3.0] - 2026-07-31

**Naprawa krytyczna.** W v0.2.2 kazde `kio_search` zwracalo `total=0` i pusta liste, a
`kio_get_orzeczenie` dostawalo HTTP 404 - serwer byl calkowicie nieuzywalny. Przyczyna:
UZP przebudowal wyszukiwarke orzeczenia.uzp.gov.pl na AJAX i przeniosl endpointy.
Szczegoly rozpoznania w `DISCOVERY.md`, sekcja "Zmiana po stronie UZP (2026-07)".

### Fixed

- **Wyszukiwarka**: `GET /?phrase=...` zwraca juz tylko shell strony z JS-em
  ("Wyszukiwanie dokumentow. Prosze czekac...") - zero linkow do orzeczen. Klient uderza
  teraz w `POST /Home/GetResults` (form-urlencoded), tak jak robi to przegladarka.
- **Nazwy pol formularza**: `phrase`/`signature`/`dateFrom`/`dateTo`/`subjectIndex`/
  `inflection`/`contentSearch`/`page` -> `Phrase`/`Sign`/`Dt`/`ThIdx`/`Fle`/`SCnt`/`Pg`
  (+ `Kind`, `Srt`, `CountStats`). Stare nazwy byly po cichu ignorowane przez UZP.
- **Zakres dat**: jedno pole `Dt` w formacie `DD-MM-YYYY - DD-MM-YYYY` zamiast dwoch pol ISO.
- **Tresc orzeczenia**: `/Home/HtmlContent/{id}` (404) -> `/Home/ContentHtml/{id}`.
  Nazwa zostala odwrocona po stronie UZP.
- **Linki wynikow**: lista wskazuje teraz na `/Home/Details/{id}`, nie `/Home/HtmlContent/{id}`.
- **Parser dat**: doszedl format `DD-MM-YYYY` uzywany przez liste i metryke UZP (wczesniej
  rozpoznawane byly tylko `YYYY-MM-DD`, `DD.MM.YYYY` i daty slowne).
- **`kio_by_pzp_article`**: post-filter po `pzp_articles` odsiewal 100% wynikow, bo lista
  UZP nie zawiera przepisow. Zastapiony filtrem server-side `Art` z fallbackiem frazowym.
- **`subject_index`**: parametr byl przyjmowany i po cichu ignorowany; teraz mapuje sie na
  filtr `ThIdx`.
- **Wersja pakietu**: `__init__.__version__` zostal na `0.1.0` mimo wydan 0.2.x, przez co
  User-Agent wysylany do UZP klamal. Dodany test spojnosci wersji.

### Added

- `tests/test_parser_regression.py` (27 testow offline) na zamrozonym HTML z UZP -
  fixture'y w `tests/fixtures/` + `scripts/refresh_fixtures.py` do ich odswiezania.
  Brak takiego testu byl powodem, dla ktorego cala suita byla zielona przy martwym scraperze.
- `parse_details()` - parser metryki `/Home/Details/{id}`. `kio_get_orzeczenie` bierze
  metadane (data, rodzaj dokumentu, przepisy PZP, indeks tematyczny, zamawiajacy,
  przewodniczacy) ze strukturalnej metryki zamiast zgadywac je regexem z tresci.
- Filtry server-side UZP: `pzp_article` (`Art`) i `subject_index` (`ThIdx`) - odpowiedz na
  otwarte pytanie z `DISCOVERY.md`.
- `sort` w `kio_search`: `rank` | `date_asc` | `date_desc`. `kio_recent` sortuje po stronie UZP.
- Paginacja klienta - `size > 10` sklejane z kolejnych stron UZP (UZP daje sztywno 10/strone;
  wczesniej `size=20` cicho zwracalo maks 10 wynikow).
- Nowe pola odpowiedzi: `doc_type`, `outcome`, `source_url_content`.
- Mapowanie bledow HTTP z UZP na `KIOError` (`not_found` przy 404, `upstream_error` reszta)
  oraz walidacja `days`/`limit`/zakresu dat.

### Changed

- **BREAKING**: `issue_date` jest teraz `Optional` (`null`) zamiast podstawianego
  `1970-01-01`. UZP nie ma daty wydania dla czesci starszych rekordow - falszywa data w
  cytacie prawniczym jest gorsza niz jej brak.
- **BREAKING**: `source_url_html` wskazuje na metryke `/Home/Details/{id}` (strona dla
  czlowieka). Pelna tresc HTML jest pod nowym `source_url_content`.
- `human_readable_citation` uwzglednia rodzaj dokumentu ("Postanowienie KIO z ...") i pomija
  date, gdy UZP jej nie podaje.
- `KioClient.get_html_content()` -> `get_content_html()`; doszly `get_details()`,
  `details_url()`, `human_search_url()`.

### Validation

- 57/57 testow offline PASS (27 regresja parsera + 8 drift/wersja + reszta unit).
- 7 smoke testow live UZP PASS (wyszukiwanie frazowe, paginacja, `kio_recent`,
  pelne orzeczenie KIO 2924/21, filtr po artykule PZP, URL PDF + HEAD 200).

## [0.2.0] - 2026-05-25

Retrofit do kanonu MCP MateMatic (pattern z dograh-hq/dograh v1.31.0, BSD-2). **Backward-compatible** - istniejaci klienci dzialaja bez zmian. Drugi Python MCP MateMatic z pelnym kanonem (po sejm-eli-mcp v0.2.0).

### Added

- **`INSTRUCTIONS` (pelne procedural orchestration)** w `FastMCP(instructions=...)` - kolejnosc wywolan (5 tooli), twarde ograniczenia (sygnatura format / rate limit 1 req/s / audit log / pre-production wymaga powiadomienia UZP), iteracja po bledach (5 ErrorCode), styl odpowiedzi z disclaimer KIO (orzeczenia KIO nie sa zrodlem prawa art. 87 Konstytucji RP). Poprzednia wersja byla 3-zdaniowy summary.
- **`ToolAnnotations`** na 5 toolach: `readOnlyHint=true`, `idempotentHint=true`, `destructiveHint=false`, `openWorldHint=true` (UZP scraping live). Klient MCP moze auto-approve wywolania bez monitu.
- **Strukturalna klasa `KIOError`** z `VALID_CODES`: `invalid_signature`, `missing_arg`, `invalid_arg`, `not_found`, `upstream_error`. Format `[code] message`. Konstruktor odrzuca nieznane kody.
- Konwersja `ValueError` z `parse_signature` na `KIOError("invalid_signature", ...)` w 2 handlerach (`kio_get_orzeczenie`, `kio_get_pdf_url`).
- 2 wystapienia `raise ValueError("Nie znaleziono...")` zamienione na `KIOError("not_found", ...)`.
- `tests/test_instructions_drift.py` (6 testow): tool names w INSTRUCTIONS, ErrorCode w VALID_CODES, `KIOError(<code>)` w SRC, format `[code] message`, konstruktor walidacji, sanity check VALID_CODES constructible.

### Validation

- 29/29 testow non-smoke PASS (6 drift + 23 unit parsera/signature/etc).
- 4 smoke live UZP API fail - znane ograniczenie POC v0.1.0 (selektory HTML best-effort), NIE regresja retrofitu.

## [0.1.0] - 2026-05-20

### Added
- Pierwsza wersja POC serwera MCP dla publicznej bazy orzeczen Krajowej Izby Odwolawczej (`orzeczenia.uzp.gov.pl`).
- 5 narzedzi: `kio_search`, `kio_get_orzeczenie`, `kio_recent`, `kio_by_pzp_article`, `kio_get_pdf_url`.
- Parser sygnatury (`KIO 5072/25` <-> `(5072, 2025)`) i human-readable citation.
- Parser HTML (selectolax) dla pojedynczego orzeczenia i listy wynikow.
- Audit log JSONL do `~/.matematic/audit/kio-orzeczenia-mcp.jsonl` (bez pelnej tresci orzeczen).
- Rate limit token bucket (default 1 req/s, hard cap 2.0).
- Cache TTL: 7 dni orzeczenie, 6h lista, 30 dni slowniki PZP.
- Konstytucja governance (`CONSTITUTION.md`) z 4 zasadami.
- Smoke testy live API i testy offline parsera sygnatury.
- Licencja Apache-2.0.

### Known limitations
- Selektory parsera HTML to best-effort - bez prawdziwego HTML do testowania, pierwsze smoke moga ujawnic rozbieznosci wymagajace kalibracji.
- Mapowanie `sygnatura -> internal_id` wymaga dodatkowego requestu search (UZP nie ma indeksu po sygnaturze).
- Brak server-side filtru po artykule PZP - filtr po frazie + post-process.

[0.1.0]: https://github.com/matematicsolutions/kio-orzeczenia-mcp/releases/tag/v0.1.0
