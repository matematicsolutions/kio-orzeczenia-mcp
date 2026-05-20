# Discovery - orzeczenia.uzp.gov.pl

Data discovery: 2026-05-20
Autor: MateMatic (Wieslaw Mazur)
Status: POC v0.1.0

## Werdykt

**SCRAPE-BASED** - brak publicznego API, brak Swagger/OpenAPI, brak feed RSS.

Strona prowadzona przez **Urzad Zamowien Publicznych (UZP)** udostepnia orzecznictwo Krajowej Izby Odwolawczej (KIO) - organu administracyjnego (kwazi-sadowego) dzialajacego przy Urzedzie Zamowien Publicznych (czlonkowie KIO sa niezawisli przy orzekaniu - art. 471 PZP), rozpatrujacego odwolania w postepowaniach o udzielenie zamowienia publicznego. KIO nie jest sadem w rozumieniu rozdzialu VIII Konstytucji RP. Skarga na orzeczenie KIO przysluguje do Sadu Okregowego w Warszawie (tzw. Sad Zamowien Publicznych) na podstawie art. 579 i nast. ustawy z 11 wrzesnia 2019 r. - Prawo zamowien publicznych.

## Stack frontu

- ASP.NET MVC (routy `/Home/HtmlContent`, `/Home/PdfContent`)
- Renderowanie PDF przez Qt 4.8.7 z dokumentu .docx zrodlowego
- Bez SPA, bez JavaScript rendering - czyste HTML server-side -> mozemy uzyc selectolax (szybki HTML parser, lxml-based)

## URL patterns

### Pojedyncze orzeczenie HTML

```
GET https://orzeczenia.uzp.gov.pl/Home/HtmlContent/{id}?Kind=KIO
```

### Pojedyncze orzeczenie PDF

```
GET https://orzeczenia.uzp.gov.pl/Home/PdfContent/{id}?Kind=KIO
```

### Wyszukiwarka / lista

```
GET https://orzeczenia.uzp.gov.pl/?phrase={fraza}&dateFrom=...&dateTo=...&signature=...
```

**Krytyczne ograniczenie**: `{id}` to wewnetrzny ID bazy (np `15903`, `32111`), NIE powiazany z sygnatura `KIO 2924/21`. Mapowanie `sygnatura -> internal_id` wymaga scrape listingu wyszukiwarki.

## Pola wyszukiwarki

| Pole | Param query | Typ |
|------|-------------|-----|
| Haslo / slowa kluczowe | `phrase` | str |
| Sygnatura | `signature` | str (format `KIO {nr}/{rok}`) |
| Data od | `dateFrom` | YYYY-MM-DD |
| Data do | `dateTo` | YYYY-MM-DD |
| Indeks tematyczny | `subjectIndex` | str |
| Przepisy PZP | (filtr po fraze) | brak server-side filtra |
| Odmiana slow | `inflection` | bool toggle |
| Wyszukiwanie w tresci | `contentSearch` | bool toggle |

**Brak server-side filtra po artykule PZP** - filtruje przez phrase + post-process w `parser.py`.

## Schema pojedynczego orzeczenia

Z HTML `/Home/HtmlContent/{id}`:

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

## Schema listy wynikow

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

1. **Mapowanie sygnatura -> internal_id wymaga search** (extra request +1 req/s opoznienia)
2. **Brak server-side filtru po artykule PZP** - filtr po fraze + post-process
3. **PDF nie pobierany** - tylko link (decyzja produktowa: nie hostujemy PDF, linkujemy)
4. **Brak deep parsera sentencji/uzasadnienia** - na POC zwracamy `content_text` (plain). Pelny parser z rozbiciem na czesci -> v1.0
5. **Rate limit 1 req/s** -> wieksze sesje "po artykule" beda wolne (wymagaja paginacji)

## Komplementarnosc z innymi MCP MateMatic

- `saos-orzecznictwo` - SAOS (Sady powszechne, SN, NSA, TK) - **inny zakres** (nie KIO)
- `eu-sparql-search` - prawo UE - **inny zakres**
- `legal-data-hunter-pl` - bulk harvest catalog (jezeli pokrywa KIO -> dodajemy `kio-orzeczenia-mcp` jako "live query" warstwe na wierzch)

KIO to **specyficzny obszar prawa zamowien publicznych** - oddzielny konektor uzasadniony.

## Otwarte pytania

- **Rate limit UZP** - czy 1 req/s jest odpowiedni? Brak oficjalnego limitu w dokumentacji; cap 2.0 req/s w Konstytucji to decyzja arbitralna POC. Walidacja: mail do UZP z pytaniem o limity.
- **Mapowanie sygnatura -> internal_id** - obecnie 1 dodatkowy request search; czy UZP udostepnia indeks po sygnaturze (link permanentny)?
- **Server-side filtr po artykule PZP** - czy wyszukiwarka UZP wspiera filtr po konkretnym artykule, czy wymaga frazy + post-process?
- **Eksport masowy** - czy UZP udostepnia bulk download orzeczen (np. CSV/JSON dla dat zakresu)?
- **Stabilnosc HTML** - selektory parsera sa best-effort; potrzebny snapshot test fixture po pierwszym smoke teste.

## TODO przed v1.0

- Snapshot testing z prawdziwymi fixtures HTML (anonimizowane jezeli trzeba)
- Pelny parser sentencji + uzasadnienia (rozbicie na sekcje)
- Slownik PZP (mapowanie artykul -> opis)
- PDF bytes streaming jezeli klient zazyczy
- Server-side article filter jezeli UZP doda do wyszukiwarki
- Tagged release na github.com/matematicsolutions/kio-orzeczenia-mcp
