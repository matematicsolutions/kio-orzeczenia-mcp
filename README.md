# kio-orzeczenia-mcp

<!-- mcp-name: io.github.matematicsolutions/kio-orzeczenia-mcp -->

MCP server (Model Context Protocol) for the case law of the **Krajowa Izba Odwolawcza (KIO) (National Appeals Chamber)** at the Urzad Zamowien Publicznych (Public Procurement Office) - the public database `orzeczenia.uzp.gov.pl`.

It lets Claude / Cursor / VS Code MCP agents consume KIO rulings with verifiable citations (signature + URL + date).

**Status: POC v0.1.0** | License: **Apache-2.0** | Maintainer: [MateMatic](https://matematicsolutions.com)

> **Preliminary warning.** The v0.1.0 connector is a proof-of-concept release. It fetches data from the public UZP case law database via HTML (no official REST API). Full legal disclaimer - see the "Legal disclaimer" section below. A dedicated smoke test and notification to UZP are required before production deployment.

---

## What KIO is

The Krajowa Izba Odwolawcza (National Appeals Chamber) is an administrative (quasi-judicial) body operating at the Urzad Zamowien Publicznych (Public Procurement Office) - KIO members are independent when adjudicating (art. 471 PZP) - which hears appeals against contracting authorities' decisions in public procurement proceedings (the Act of 11 September 2019 - Public Procurement Law). KIO rulings are made publicly available by UZP under the Act on access to public information.

KIO rulings are not a source of law within the meaning of art. 87 of the Constitution of the Republic of Poland - they are reference material widely used in the practice of law firms dealing with public procurement.

## Quickstart

```powershell
# Clone and enter the directory
git clone https://github.com/matematicsolutions/kio-orzeczenia-mcp.git
cd kio-orzeczenia-mcp

# Virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install
pip install -e ".[dev]"

# Offline test (signature parser)
pytest tests/test_signature.py -v

# Smoke test (online - hits UZP, rate-limited 1 req/s)
pytest tests/test_smoke.py -v -m smoke

# Run the server (stdio)
python -m kio_orzeczenia_mcp.server
```

## Wiring into Claude Code

Add to `~/.claude.json` (or `.mcp.json` in the project):

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

Restart Claude Code. After startup, 5 tools should be visible.

## 5 MCP tools

### 1. `kio_search(query: SearchQuery) -> SearchResult`

Search over KIO case law. All fields optional.

```jsonc
// Arguments:
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

Returns `{total, page, items: [OrzeczenieSummary]}`.

### 2. `kio_get_orzeczenie(signature_or_id: str | int) -> Orzeczenie`

Fetches the full text of a single ruling.

```jsonc
// Arguments:
"KIO 2924/21"   // string -> first search by signature to resolve internal_id (+1 req)
15903           // int -> directly GET /Home/HtmlContent/15903
```

Returns the full `Orzeczenie` with `content_text`, `sentence`, `reasoning` (if the parser can extract them), `pzp_articles`, `chamber_composition`, `parties`.

### 3. `kio_recent(days: int = 30, limit: int = 20) -> list[OrzeczenieSummary]`

The most recent rulings from the last N days, sorted by date descending.

```jsonc
// Arguments:
{ "days": 30, "limit": 20 }
```

### 4. `kio_by_pzp_article(article: str, limit: int = 20) -> list[OrzeczenieSummary]`

Rulings citing a specific PZP article. Filtered by phrase + post-process (no server-side article filter).

```jsonc
// Arguments:
{ "article": "226", "limit": 20 }
{ "article": "224 ust. 1 pkt 1", "limit": 50 }
```

### 5. `kio_get_pdf_url(signature_or_id: str | int) -> dict`

Returns the URL to the PDF (rendered by UZP from .docx via Qt 4.8.7). **Does not fetch bytes** - we link to it.

```jsonc
// Returns:
{
  "pdf_url": "https://orzeczenia.uzp.gov.pl/Home/PdfContent/15903?Kind=KIO",
  "signature": "KIO 2924/21",
  "internal_id": 15903,
  "human_readable_citation": "Wyrok KIO z 2021-10-28, sygn. KIO 2924/21"
}
```

---

## 3 usage examples (natural language)

### Example 1: "KIO rulings on abnormally low price from the past year"

The agent calls `kio_search`:

```json
{
  "phrase": "razaco niska cena",
  "date_from": "2025-05-20",
  "date_to": "2026-05-20",
  "inflection": true,
  "size": 50
}
```

Result: a list of OrzeczenieSummary with `human_readable_citation` ready to insert into a court filing.

### Example 2: "KIO rulings citing art. 226 sec. 1 point 5 PZP"

The agent calls `kio_by_pzp_article`:

```json
{ "article": "226 ust. 1 pkt 5", "limit": 30 }
```

### Example 3: "Ruling KIO 2924/21 - who were the parties and was the appeal upheld"

The agent calls `kio_get_orzeczenie`:

```json
"KIO 2924/21"
```

Result: the full `Orzeczenie` with `parties`, `sentence`, `reasoning`.

---

## Limitations (POC)

1. **Mapping signature -> internal_id requires a search** - if you query by signature, we make +1 req
2. **No server-side filter by PZP article** - filtering done via phrase search + post-process (may miss some hits)
3. **PDF not fetched** - only a link to the UZP page (product decision)
4. **The sentence/reasoning parser is shallow** - in the POC we return `content_text` as plain text. Splitting into sections -> v1.0
5. **Rate limit 1 req/s** - large lists may be slow. A 7-day cache for rulings (immutable) mitigates this.

## Cache

- Rulings (immutable): **7 days**
- Search result lists: **6 hours**
- PZP dictionary (once implemented): **30 days**

Cache location: `~/.matematic/cache/kio/` (configurable via `KIO_MCP_CACHE_DIR`).

## Audit log

Location: `~/.matematic/audit/kio-orzeczenia-mcp.jsonl`

JSONL format (one entry per tool call). See `CONSTITUTION.md` Art. 3.

**What is NOT logged**: the full text of a ruling (`content_text`, `reasoning`). We log only signatures and metadata.

## Legal disclaimer

The data comes from the public UZP case law database (`orzeczenia.uzp.gov.pl`), made available under the Act of 6 September 2001 on access to public information and the Act of 11 September 2019 - Public Procurement Law.

The connector:

- does not modify the source data,
- does not de-anonymize the parties to a proceeding beyond what UZP publishes,
- does not circumvent any technical protections,
- identifies itself with the User-Agent header `matematic-kio-mcp/{version} (+https://matematic.co)`.

**Pre-release blocker.** Before publishing the repository on GitHub, a notification to UZP (`kontakt@uzp.gov.pl`) about launching the connector is planned - User-Agent, query limit, nature of access. Status: TODO.

In case of objections from UZP or other parties - contact: `kontakt@matematic.co`.

## License

Apache-2.0. See `LICENSE`.

## Project constitution

See [`CONSTITUTION.md`](CONSTITUTION.md) - 4 governance principles (public data, rate limit, audit log, citations).

## Other open connectors for Polish law

Open-source connectors by MateMatic that complement the scope of this repository:

- [`mcp-saos`](https://github.com/matematicsolutions/mcp-saos) - SAOS (Supreme Court, Supreme Administrative Court, common courts)
- [`mcp-eu-sparql`](https://github.com/matematicsolutions/mcp-eu-sparql) - EU law via Cellar SPARQL
- [`mcp-isap`](https://github.com/matematicsolutions/mcp-isap) - Journal of Laws, Monitor Polski, ministerial gazettes (Sejm ELI API)

External catalog of legal sources: [`worldwidelaw/legal-sources`](https://github.com/worldwidelaw/legal-sources) (bulk harvest scripts, MIT).
