# Discovery - orzeczenia.uzp.gov.pl

Discovery date: 2026-05-20
Author: MateMatic (Wieslaw Mazur)
Status: POC v0.1.0

## Verdict

**SCRAPE-BASED** - no public API, no Swagger/OpenAPI, no RSS feed.

The site, run by the **Urzad Zamowien Publicznych (UZP) (Public Procurement Office)**, makes available the case law of the Krajowa Izba Odwolawcza (KIO) (National Appeals Chamber) - an administrative (quasi-judicial) body operating at the Public Procurement Office (KIO members are independent when adjudicating - art. 471 PZP), which hears appeals in public procurement proceedings. KIO is not a court within the meaning of chapter VIII of the Constitution of the Republic of Poland. A complaint against a KIO ruling lies to the Regional Court in Warsaw (the so-called Public Procurement Court) under art. 579 et seq. of the Act of 11 September 2019 - Public Procurement Law.

## Frontend stack

- ASP.NET MVC (routes `/Home/HtmlContent`, `/Home/PdfContent`)
- PDF rendering via Qt 4.8.7 from the source .docx document
- No SPA, no JavaScript rendering - plain server-side HTML -> we can use selectolax (a fast HTML parser, lxml-based)

## URL patterns

### Single ruling HTML

```
GET https://orzeczenia.uzp.gov.pl/Home/HtmlContent/{id}?Kind=KIO
```

### Single ruling PDF

```
GET https://orzeczenia.uzp.gov.pl/Home/PdfContent/{id}?Kind=KIO
```

### Search / list

```
GET https://orzeczenia.uzp.gov.pl/?phrase={fraza}&dateFrom=...&dateTo=...&signature=...
```

**Critical limitation**: `{id}` is the internal database ID (e.g. `15903`, `32111`), NOT linked to the signature `KIO 2924/21`. Mapping `signature -> internal_id` requires scraping the search listing.

## Search fields

| Field | Query param | Type |
|------|-------------|-----|
| Keyword / keywords | `phrase` | str |
| Signature | `signature` | str (format `KIO {nr}/{rok}`) |
| Date from | `dateFrom` | YYYY-MM-DD |
| Date to | `dateTo` | YYYY-MM-DD |
| Subject index | `subjectIndex` | str |
| PZP provisions | (filter by phrase) | no server-side filter |
| Word inflection | `inflection` | bool toggle |
| Full-text search | `contentSearch` | bool toggle |

**No server-side filter by PZP article** - filtered via phrase + post-process in `parser.py`.

## Single ruling schema

From HTML `/Home/HtmlContent/{id}`:

```python
{
  "signature": "KIO 2924/21",
  "internal_id": 15903,
  "issue_date": "2021-10-28",
  "chamber_composition": [
    {"role": "przewodniczacy", "name": "..."},
    {"role": "protokolant", "name": "..."}
  ],
  "parties": [
    {"role": "odwolujacy", "name": "..."},
    {"role": "zamawiajacy", "name": "..."}
  ],
  "sentence": "...",
  "reasoning": "...",
  "pzp_articles": ["art. 226 ust. 1 pkt 5"],
  "subject_index": ["razaco niska cena"],
  "content_text": "...",
  "source_url_html": "https://orzeczenia.uzp.gov.pl/Home/HtmlContent/15903?Kind=KIO",
  "source_url_pdf": "https://orzeczenia.uzp.gov.pl/Home/PdfContent/15903?Kind=KIO",
  "retrieved_at": "2026-05-20T12:00:00Z"
}
```

## Result list schema

```python
{
  "total": 154,
  "page": 1,
  "items": [
    {
      "signature": "KIO 2924/21",
      "internal_id": 15903,
      "issue_date": "2021-10-28",
      "snippet": "... razaco niska cena ...",
      "pzp_articles": [...],
      "source_url": "...",
      "human_readable_citation": "Wyrok KIO z 2021-10-28, sygn. KIO 2924/21"
    }
  ]
}
```

## Limitations POC

1. **Mapping signature -> internal_id requires a search** (extra request, +1 req/s of latency)
2. **No server-side filter by PZP article** - filter by phrase + post-process
3. **PDF not fetched** - only a link (product decision: we do not host PDFs, we link to them)
4. **No deep sentence/reasoning parser** - in the POC we return `content_text` (plain). A full parser with section splitting -> v1.0
5. **Rate limit 1 req/s** -> larger "by article" sessions will be slow (require pagination)

## Complementarity with other MateMatic MCPs

- `saos-orzecznictwo` - SAOS (common courts, Supreme Court, Supreme Administrative Court, Constitutional Tribunal) - **different scope** (not KIO)
- `eu-sparql-search` - EU law - **different scope**
- `legal-data-hunter-pl` - bulk harvest catalog (if it covers KIO -> we add `kio-orzeczenia-mcp` as a "live query" layer on top)

KIO is a **specific area of public procurement law** - a separate connector is justified.

## Open questions

- **UZP rate limit** - is 1 req/s appropriate? No official limit in the documentation; the 2.0 req/s cap in the Constitution is an arbitrary POC decision. Validation: an email to UZP asking about limits.
- **Mapping signature -> internal_id** - currently 1 extra search request; does UZP provide an index by signature (permanent link)?
- **Server-side filter by PZP article** - does the UZP search support a filter by a specific article, or does it require a phrase + post-process?
- **Bulk export** - does UZP provide a bulk download of rulings (e.g. CSV/JSON for a date range)?
- **HTML stability** - the parser selectors are best-effort; a snapshot test fixture is needed after the first smoke test.

## TODO before v1.0

- Snapshot testing with real HTML fixtures (anonymized if needed)
- Full sentence + reasoning parser (splitting into sections)
- PZP dictionary (mapping article -> description)
- PDF bytes streaming if a client requests it
- Server-side article filter if UZP adds it to the search
- Tagged release on github.com/matematicsolutions/kio-orzeczenia-mcp
