# kio-orzeczenia-mcp

<!-- mcp-name: io.github.matematicsolutions/kio-orzeczenia-mcp -->

MCP server (Model Context Protocol) dla orzecznictwa **Krajowej Izby Odwolawczej (KIO)** przy Urzedzie Zamowien Publicznych - publiczna baza `orzeczenia.uzp.gov.pl`.

Pozwala agentom Claude / Cursor / VS Code MCP konsumowac wyroki KIO z weryfikowalnymi cytatami (sygnatura + URL + data).

**Status: POC v0.1.0** | Licencja: **Apache-2.0** | Maintainer: [MateMatic](https://matematicsolutions.com)

> **Ostrzezenie wstepne.** Konektor v0.1.0 to wersja proof-of-concept. Pobiera dane z publicznej bazy orzeczen UZP przez HTML (bez oficjalnego REST API). Pelny disclaimer prawny - sekcja "Disclaimer prawny" ponizej. Przed wdrozeniem produkcyjnym wymagany jest wlasny smoke test i powiadomienie UZP.

---

## Co to jest KIO

Krajowa Izba Odwolawcza to organ administracyjny (kwazi-sadowy) dzialajacy przy Urzedzie Zamowien Publicznych (czlonkowie KIO sa niezawisli przy orzekaniu - art. 471 PZP), rozpatrujacy odwolania od decyzji zamawiajacych w postepowaniach o udzielenie zamowienia publicznego (ustawa z 11 wrzesnia 2019 r. - Prawo zamowien publicznych). Orzeczenia KIO sa publicznie udostepniane przez UZP na podstawie ustawy o dostepie do informacji publicznej.

Orzeczenia KIO nie sa zrodlem prawa w rozumieniu art. 87 Konstytucji RP - sa materialem referencyjnym powszechnie wykorzystywanym w praktyce kancelarii zajmujacych sie zamowieniami publicznymi.

## Quickstart

```powershell
# Sklonuj i przejdz do katalogu
git clone https://github.com/matematicsolutions/kio-orzeczenia-mcp.git
cd kio-orzeczenia-mcp

# Virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install
pip install -e ".[dev]"

# Test offline (parser sygnatury)
pytest tests/test_signature.py -v

# Test smoke (online - hit UZP, rate-limited 1 req/s)
pytest tests/test_smoke.py -v -m smoke

# Uruchom serwer (stdio)
python -m kio_orzeczenia_mcp.server
```

## Podpiecie do Claude Code

Dodaj do `~/.claude.json` (lub `.mcp.json` w projekcie):

```json
{
  "mcpServers": {
    "kio-orzeczenia": {
      "command": "python",
      "args": ["-m", "kio_orzeczenia_mcp.server"],
      "env": {
        "KIO_MCP_RATE_LIMIT": "1.0",
        "KIO_MCP_CACHE_DIR": "~/.matematic/cache/kio"
      }
    }
  }
}
```

Restartuj Claude Code. Po starcie powinno byc widoczne 5 narzedzi.

## 5 narzedzi MCP

### 1. `kio_search(query: SearchQuery) -> SearchResult`

Wyszukiwarka po orzecznictwie KIO. Wszystkie pola opcjonalne.

```jsonc
// Argumenty:
{
  "phrase": "razaco niska cena",
  "signature": null,
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "pzp_article": "226",
  "subject_index": null,
  "inflection": true,
  "page": 1,
  "size": 20
}
```

Zwraca `{total, page, items: [OrzeczenieSummary]}`.

### 2. `kio_get_orzeczenie(signature_or_id: str | int) -> Orzeczenie`

Pobiera pelny tekst pojedynczego orzeczenia.

```jsonc
// Argumenty:
"KIO 2924/21"   // string -> najpierw search by signature aby ustalic internal_id (+1 req)
15903           // int -> bezposrednio GET /Home/HtmlContent/15903
```

Zwraca pelny `Orzeczenie` z `content_text`, `sentence`, `reasoning` (jezeli parser zdola wyodrebnic), `pzp_articles`, `chamber_composition`, `parties`.

### 3. `kio_recent(days: int = 30, limit: int = 20) -> list[OrzeczenieSummary]`

Najnowsze orzeczenia z ostatnich N dni, sortowane malejaco po dacie.

```jsonc
// Argumenty:
{ "days": 30, "limit": 20 }
```

### 4. `kio_by_pzp_article(article: str, limit: int = 20) -> list[OrzeczenieSummary]`

Orzeczenia cytujace konkretny artykul PZP. Filtr po fraze + post-process (brak server-side article filter).

```jsonc
// Argumenty:
{ "article": "226", "limit": 20 }
{ "article": "224 ust. 1 pkt 1", "limit": 50 }
```

### 5. `kio_get_pdf_url(signature_or_id: str | int) -> dict`

Zwraca URL do PDF (renderowany przez UZP z .docx via Qt 4.8.7). **Nie pobiera bytes** - linkujemy.

```jsonc
// Zwraca:
{
  "pdf_url": "https://orzeczenia.uzp.gov.pl/Home/PdfContent/15903?Kind=KIO",
  "signature": "KIO 2924/21",
  "internal_id": 15903,
  "human_readable_citation": "Wyrok KIO z 2021-10-28, sygn. KIO 2924/21"
}
```

---

## 3 przyklady uzycia (jezykiem naturalnym)

### Przyklad 1: "Wyroki KIO o razaco niskiej cenie z ostatniego roku"

Agent wywola `kio_search`:

```json
{
  "phrase": "razaco niska cena",
  "date_from": "2025-05-20",
  "date_to": "2026-05-20",
  "inflection": true,
  "size": 50
}
```

Wynik: lista OrzeczenieSummary z `human_readable_citation` gotowymi do wstawienia w pismo procesowe.

### Przyklad 2: "Wyroki KIO cytujace art. 226 ust. 1 pkt 5 PZP"

Agent wywola `kio_by_pzp_article`:

```json
{ "article": "226 ust. 1 pkt 5", "limit": 30 }
```

### Przyklad 3: "Wyrok KIO 2924/21 - jakie byly strony i czy uwzgledniono odwolanie"

Agent wywola `kio_get_orzeczenie`:

```json
"KIO 2924/21"
```

Wynik: pelny `Orzeczenie` z `parties`, `sentence`, `reasoning`.

---

## Limitations (POC)

1. **Mapowanie sygnatura -> internal_id wymaga search** - jezeli wolasz po sygnaturze, robimy +1 req
2. **Brak server-side filtru po artykule PZP** - filtr realizowany przez phrase search + post-process (moze gubic niektore trafienia)
3. **PDF nie pobierany** - tylko link do strony UZP (decyzja produktowa)
4. **Parser sentencji/uzasadnienia jest plytki** - na POC zwracamy `content_text` jako plain. Rozbicie na sekcje -> v1.0
5. **Rate limit 1 req/s** - duze listy moga byc wolne. Cache 7 dni dla orzeczen (immutable) lagodzi to.

## Cache

- Orzeczenia (immutable): **7 dni**
- Listy wynikow wyszukiwania: **6 godzin**
- Slownik PZP (gdy zaimplementowany): **30 dni**

Lokalizacja cache: `~/.matematic/cache/kio/` (konfigurowalne przez `KIO_MCP_CACHE_DIR`).

## Audit log

Lokalizacja: `~/.matematic/audit/kio-orzeczenia-mcp.jsonl`

Format JSONL (jeden wpis per wywolanie narzedzia). Patrz `CONSTITUTION.md` Art. 3.

**Co NIE jest logowane**: pelna tresc orzeczenia (`content_text`, `reasoning`). Logujemy tylko sygnatury i metadane.

## Disclaimer prawny

Dane pochodza z publicznej bazy orzecznictwa UZP (`orzeczenia.uzp.gov.pl`), udostepnianej na podstawie ustawy z 6 wrzesnia 2001 r. o dostepie do informacji publicznej oraz ustawy z 11 wrzesnia 2019 r. - Prawo zamowien publicznych.

Konektor:

- nie modyfikuje danych zrodlowych,
- nie deanonimizuje stron postepowania ponad to, co publikuje UZP,
- nie omija zadnych zabezpieczen technicznych,
- identyfikuje sie naglowkiem User-Agent `matematic-kio-mcp/{version} (+https://matematic.co)`.

**Pre-release blocker.** Przed publikacja repozytorium na GitHub planowane jest powiadomienie UZP (`kontakt@uzp.gov.pl`) o uruchomieniu konektora - User-Agent, limit zapytan, charakter dostepu. Status: TODO.

W razie zastrzezen UZP lub innych podmiotow - kontakt: `kontakt@matematic.co`.

## Licencja

Apache-2.0. Patrz `LICENSE`.

## Konstytucja projektu

Patrz [`CONSTITUTION.md`](CONSTITUTION.md) - 4 zasady governance (publiczne dane, rate limit, audit log, cytowania).

## Inne otwarte konektory prawa polskiego

Konektory open-source autorstwa MateMatic uzupelniajace zakres tego repozytorium:

- [`saos-orzecznictwo`](https://github.com/matematicsolutions/saos-orzecznictwo) - SAOS (Sad Najwyzszy, NSA, sady powszechne)
- [`eu-sparql-search`](https://github.com/matematicsolutions/eu-sparql-search) - prawo UE przez Cellar SPARQL
- [`sejm-eli-mcp`](https://github.com/matematicsolutions/sejm-eli-mcp) - Dziennik Ustaw, Monitor Polski, dzienniki resortowe (ELI API Sejmu)
- [`uodo-orzeczenia-mcp`](https://github.com/matematicsolutions/uodo-orzeczenia-mcp) - orzecznictwo Prezesa UODO (RODO)

Katalog zewnetrzny zrodel prawa: [`worldwidelaw/legal-sources`](https://github.com/worldwidelaw/legal-sources) (bulk harvest scripts, MIT).
