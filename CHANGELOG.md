# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), SemVer.

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
