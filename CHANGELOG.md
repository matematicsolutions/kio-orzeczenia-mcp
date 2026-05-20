# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), SemVer.

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
