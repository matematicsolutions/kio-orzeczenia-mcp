# Discovery - orzeczenia.uzp.gov.pl

Discovery date: 2026-05-20
Re-discovery: 2026-07-31 (see "UZP-side change (2026-07)" - all endpoints moved)
Author: MateMatic (Wieslaw Mazur)
Status: v0.3.0

## Verdict

**SCRAPE-BASED** - no public API, no Swagger/OpenAPI, no RSS feed.

The site, run by the **Urzad Zamowien Publicznych (UZP) (Public Procurement Office)**, makes available the case law of the Krajowa Izba Odwolawcza (KIO) (National Appeals Chamber) - an administrative (quasi-judicial) body operating at the Public Procurement Office (KIO members are independent when adjudicating - art. 471 PZP), which hears appeals in public procurement proceedings. KIO is not a court within the meaning of chapter VIII of the Constitution of the Republic of Poland. A complaint against a KIO ruling lies to the Regional Court in Warsaw (the so-called Public Procurement Court) under art. 579 et seq. of the Act of 11 September 2019 - Public Procurement Law.

## UZP-side change (2026-07) - why v0.2.2 returned nothing

Diagnosed 2026-07-31 after v0.2.2 started returning `total=0` and an empty list for every
`kio_search`, and HTTP 404 for every `kio_get_orzeczenie`. Nothing was wrong with the
network or the rate limiter - **UZP rebuilt the search engine and moved every endpoint**.

| What | Until v0.2.2 (dead) | Since 2026-07 (working) |
|------|--------------------|--------------------------|
| Search | `GET /?phrase=...` | `POST /Home/GetResults` (form-urlencoded, AJAX) |
| Result link | `/Home/HtmlContent/{id}` | `/Home/Details/{id}` |
| Full text | `/Home/HtmlContent/{id}` | `/Home/ContentHtml/{id}` (name reversed) |
| PDF | `/Home/PdfContent/{id}` | `/Home/PdfContent/{id}` (unchanged) |

`GET /` and `GET /Home/Search` still return HTTP 200, but the body is only the page shell
with the form and the text "Wyszukiwanie dokumentow. Prosze czekac..." - results are
injected by `js/Search.min.js` via a POST to `/Home/GetResults`. **A 200 with parseable
HTML is not proof that the scraper works** - that is exactly why v0.2.2 failed silently
instead of raising. Guard: `tests/test_parser_regression.py` asserts a non-zero `total`
on frozen HTML.

Internal IDs did NOT change (`KIO 2924/21` is still `15903`), so caches survive.

## Frontend stack

- ASP.NET MVC + jQuery. Search results are loaded by AJAX; the rest is server-side HTML
- PDF rendering via Qt 4.8.7 from the source .docx document
- No SPA framework - `selectolax` is still enough, provided we call the AJAX endpoint ourselves

## URL patterns

### Search / list (AJAX)

```
POST https://orzeczenia.uzp.gov.pl/Home/GetResults
Content-Type: application/x-www-form-urlencoded
Phrase=ra%C5%BC%C4%85co+niska+cena&Fle=1&SCnt=1&Kind=KIO&Pg=1&CountStats=True
```

Returns an HTML fragment: `#resultCounts` (`ALL,KIO,SO,SA,SN`), the header "Liczba
znalezionych dokumentow: N" and up to **10** `div.search-list-item` blocks. Page size is
fixed - the form has no page-size field, so pagination is client-side via `Pg`.

The human-readable equivalent (for citations / audit log) is
`GET /Home/Search?<same params>`.

### Ruling metrics (canonical human URL)

```
GET https://orzeczenia.uzp.gov.pl/Home/Details/{id}
```

Structured metadata: issue date, document type, outcome, chair, purchaser, city,
procedure, key PZP provisions, thematic index. This is the source of truth for metadata -
regexing them out of the ruling text is guesswork.

### Single ruling full text

```
GET https://orzeczenia.uzp.gov.pl/Home/ContentHtml/{id}?Kind=KIO&flection=0
```

### Single ruling PDF

```
GET https://orzeczenia.uzp.gov.pl/Home/PdfContent/{id}?Kind=KIO
GET https://orzeczenia.uzp.gov.pl/Home/PdfMetrics/{id}?Kind=KIO   (metrics only)
```

**Critical limitation**: `{id}` is the internal database ID (e.g. `15903`, `32111`), NOT linked to the signature `KIO 2924/21`. Mapping `signature -> internal_id` requires scraping the search listing.

## Search fields (form `POST /Home/GetResults`)

| Field | Form field | Type / format |
|------|-------------|-----|
| Keyword / keywords | `Phrase` | str |
| Signature | `Sign` | str (format `KIO {nr}/{rok}`) |
| Issue date range | `Dt` | `DD-MM-YYYY - DD-MM-YYYY` (one field, both ends required) |
| Subject index | `ThIdx` | str, server-side filter (multi-value) |
| PZP provisions | `Art` | str, server-side filter (multi-value) |
| Word inflection | `Fle` | checkbox, `1` or omitted |
| Full-text search | `SCnt` | checkbox, `1` or omitted |
| Body | `Kind` | `KIO` / `SO` / `SA` / `SN` / empty = all |
| Page | `Pg` | int, 10 results per page |
| Sorting | `Srt` | `rank` / `date_asc` / `date_desc` |
| Count results | `CountStats` | `True` to have the server compute the total |

**A server-side filter by PZP article now exists** (`Art`) - this closes an open question
from the 2026-05 discovery. It matches the provisions dictionary and is format-sensitive:
`art. 226 ust. 1 pkt 5` -> 1708 hits, `art. 226` -> 11, plain `226` -> 0. Dictionary
autocomplete: `GET /DictionaryPzpArticle/SearchArticle?query=...` (and `SearchIndex` for
the thematic index) - note the param is `query`, not `term`.

Other autocompletes seen in the form, not wired up yet: `/Dictionary/SearchCity`,
`/Dictionary/SearchPurchaser`, `/Dictionary/SearchChairman`.

**Missing issue dates**: for a sizeable share of older records the list and the metrics
show `Data wydania: -`. `issue_date` is then `null` - we do not substitute a placeholder,
because a false date in a legal citation is worse than no date.

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

## Limitations

1. **Mapping signature -> internal_id requires a search** (extra request, +1 req/s of latency)
2. **The `Art` filter is dictionary-based** - format-sensitive (see above); on a miss we fall back to a phrase search, which is broader and needs verification
3. **PDF not fetched** - only a link (product decision: we do not host PDFs, we link to them)
4. **No deep sentence/reasoning parser** - we return `content_text` (plain) plus regex-extracted sentence/reasoning. A full parser with section splitting -> v1.0
5. **Rate limit 1 req/s** -> larger "by article" sessions will be slow (require pagination)
6. **10 results per UZP page** - `size > 10` costs +1 request per extra page

## Complementarity with other MateMatic MCPs

- `saos-orzecznictwo` - SAOS (common courts, Supreme Court, Supreme Administrative Court, Constitutional Tribunal) - **different scope** (not KIO)
- `eu-sparql-search` - EU law - **different scope**
- `legal-data-hunter-pl` - bulk harvest catalog (if it covers KIO -> we add `kio-orzeczenia-mcp` as a "live query" layer on top)

KIO is a **specific area of public procurement law** - a separate connector is justified.

## Open questions

- **UZP rate limit** - is 1 req/s appropriate? No official limit in the documentation; the 2.0 req/s cap in the Constitution is an arbitrary POC decision. Validation: an email to UZP asking about limits.
- **Mapping signature -> internal_id** - currently 1 extra search request; does UZP provide an index by signature (permanent link)?
- ~~**Server-side filter by PZP article**~~ - **ANSWERED 2026-07-31**: yes, the `Art` field (dictionary-based, format-sensitive).
- **Bulk export** - does UZP provide a bulk download of rulings (e.g. CSV/JSON for a date range)?
- ~~**HTML stability**~~ - **ANSWERED 2026-07-31**: not stable, every endpoint moved within ~2 months. Fixtures + a regression test are now in `tests/`; treat the connector as needing a periodic smoke run, not fire-and-forget.
- **Missing issue dates** - is the gap in `Data wydania` for older records permanent, or is UZP backfilling? Affects the usefulness of `kio_recent` for historical queries.
- **`/AiSearch/*` endpoints** - the search page calls `GetQueryRelatedMetrics` and `RateMetric` (semantic search relevance). Worth checking whether they expose anything useful for grounding.

## TODO before v1.0

- Full sentence + reasoning parser (splitting into sections)
- PZP dictionary (mapping article -> description), on top of `/DictionaryPzpArticle/*`
- PDF bytes streaming if a client requests it
- Filters not wired up yet: purchaser, city, chair, outcome, procedure, contract type
- Periodic smoke run (cron) so the next UZP-side change is caught by us, not by a user
- Tagged release on github.com/matematicsolutions/kio-orzeczenia-mcp
