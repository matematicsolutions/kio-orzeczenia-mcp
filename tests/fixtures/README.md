# Fixture'y HTML z orzeczenia.uzp.gov.pl

Zamrozony HTML dla `tests/test_parser_regression.py` (testy offline).

| Plik | Zrodlo | Zapytanie |
|------|--------|-----------|
| `search_results_kio.html` | `POST /Home/GetResults` | `Phrase=rażąco niska cena&Fle=1&SCnt=1&Kind=KIO&Pg=1&CountStats=True` |
| `search_results_by_signature.html` | `POST /Home/GetResults` | `Sign=KIO 2924/21&Fle=1&SCnt=1&Kind=KIO&Pg=1&CountStats=True` |
| `details_15903.html` | `GET /Home/Details/15903` | metryka KIO 2924/21 |
| `content_html_15903.html` | `GET /Home/ContentHtml/15903?Kind=KIO&flection=0` | pelna tresc KIO 2924/21 |

Pobrano: **2026-07-31**. Tresc orzeczen KIO jest jawna (dokument urzedowy), fixture'y
sa niezmienione wzgledem zrodla - patrz zasada "bez modyfikacji tresci orzeczenia"
w `CONSTITUTION.md`.

## Odswiezenie

```bash
python scripts/refresh_fixtures.py
```

Po odswiezeniu uruchom `pytest tests/test_parser_regression.py -q`. Jesli testy padaja,
UZP zmienil strukture strony - poprawiaj `parser.py` / `client.py`, a nie asercje.
Zmiane opisz w `DISCOVERY.md`.
