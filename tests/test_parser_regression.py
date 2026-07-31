"""Test regresyjny parsera na zamrozonym HTML z orzeczenia.uzp.gov.pl.

Powod istnienia: w v0.2.2 kazde `kio_search` zwracalo `total=0` i pusta liste, bo UZP
przeniosl wyszukiwarke na AJAX (`POST /Home/GetResults`), a linki wynikow z
`/Home/HtmlContent/{id}` na `/Home/Details/{id}`. Parser nie mial ANI JEDNEGO testu na
prawdziwym HTML, wiec cala suita byla zielona przy calkowicie martwym scraperze.

Fixture'y w `tests/fixtures/` pobrano 2026-07-31. Testy sa offline - lapia regresje
parsera. Zmiane po stronie UZP lapie `tests/test_smoke.py` (online, uruchamiany recznie).

Odswiezenie fixture'ow: patrz `tests/fixtures/README.md`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from kio_orzeczenia_mcp.client import KioClient
from kio_orzeczenia_mcp.parser import (
    _parse_pl_date,
    extract_internal_id_from_url,
    parse_details,
    parse_orzeczenie,
    parse_search_results,
)


FIXTURES = Path(__file__).parent / "fixtures"
SEARCH_URL = "https://orzeczenia.uzp.gov.pl/Home/Search?Phrase=razaco+niska+cena"
KIO_2924_21_ID = 15903


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Lista wynikow (POST /Home/GetResults)
# ---------------------------------------------------------------------------


def test_search_results_are_not_empty():
    """REGRESJA v0.2.2: total=0 i pusta lista dla kazdego zapytania."""
    total, items = parse_search_results(_fixture("search_results_kio.html"), SEARCH_URL)

    assert total > 1000, f"total={total} - parser nie odczytal licznika UZP"
    assert len(items) == 10, f"UZP zwraca 10 wynikow na strone, sparsowano {len(items)}"


def test_search_results_items_are_well_formed():
    _, items = parse_search_results(_fixture("search_results_kio.html"), SEARCH_URL)

    for it in items:
        assert it.signature.startswith("KIO "), it.signature
        assert it.internal_id > 0
        assert it.source_url.startswith("https://orzeczenia.uzp.gov.pl/Home/Details/")
        assert str(it.internal_id) in it.source_url
        assert it.doc_type in {"wyrok", "postanowienie", "uchwala", "uchwała"}, it.doc_type
        assert it.issue_date is None or isinstance(it.issue_date, date)

    assert len({it.internal_id for it in items}) == len(items), "duplikaty internal_id"
    assert any(it.snippet for it in items), "zaden wynik nie ma fragmentu z kontekstem frazy"


def test_search_results_do_not_invent_missing_dates():
    """UZP nie ma daty dla czesci rekordow - `issue_date` ma byc None, nie 1970-01-01."""
    _, items = parse_search_results(_fixture("search_results_kio.html"), SEARCH_URL)

    assert all(
        it.issue_date != date(1970, 1, 1) for it in items
    ), "parser podstawia zastepcza date zamiast None"

    for it in items:
        if it.issue_date is None:
            assert "z 1970" not in it.human_readable_citation
            assert it.human_readable_citation.endswith(f"sygn. {it.signature}")


def test_search_by_signature_returns_single_hit():
    total, items = parse_search_results(
        _fixture("search_results_by_signature.html"), SEARCH_URL
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].signature == "KIO 2924/21"
    assert items[0].internal_id == KIO_2924_21_ID
    assert items[0].issue_date == date(2021, 10, 28)


# ---------------------------------------------------------------------------
# Metryka (/Home/Details/{id})
# ---------------------------------------------------------------------------


def test_parse_details_extracts_metrics():
    details = parse_details(_fixture(f"details_{KIO_2924_21_ID}.html"), KIO_2924_21_ID)

    assert details["signature"] == "KIO 2924/21"
    assert details["issue_date"] == date(2021, 10, 28)
    assert details["doc_type"] == "wyrok"
    assert details["outcome"] == "uwzględnione"
    assert details["chairman"] == "Trojanowska Agnieszka"
    assert details["purchaser"] == "22. Baza Lotnictwa Taktycznego"
    assert details["city"] == "Malbork"
    assert details["procedure"] == "przetarg nieograniczony"


def test_parse_details_separates_articles_from_subject_index():
    details = parse_details(_fixture(f"details_{KIO_2924_21_ID}.html"), KIO_2924_21_ID)

    assert details["pzp_articles"] == ["art. 223 ust. 1", "art. 223 ust. 2 pkt 3"]
    assert "inna omyłka" in details["subject_index"]
    # zagadnienia z indeksu NIE moga wyladowac w przepisach i odwrotnie
    assert not any(a.startswith("art.") for a in details["subject_index"])
    assert all(a.startswith("art.") for a in details["pzp_articles"])


# ---------------------------------------------------------------------------
# Pelne orzeczenie (/Home/ContentHtml/{id} + metryka)
# ---------------------------------------------------------------------------


def test_parse_orzeczenie_uses_details_as_source_of_truth():
    details = parse_details(_fixture(f"details_{KIO_2924_21_ID}.html"), KIO_2924_21_ID)
    orz = parse_orzeczenie(
        _fixture(f"content_html_{KIO_2924_21_ID}.html"),
        f"https://orzeczenia.uzp.gov.pl/Home/Details/{KIO_2924_21_ID}",
        KIO_2924_21_ID,
        details=details,
    )

    assert orz.signature == "KIO 2924/21"
    assert orz.issue_date == date(2021, 10, 28)
    assert orz.doc_type == "wyrok"
    assert orz.outcome == "uwzględnione"
    assert orz.pzp_articles == ["art. 223 ust. 1", "art. 223 ust. 2 pkt 3"]
    assert orz.subject_index, "indeks tematyczny z metryki zgubiony"
    assert (
        orz.human_readable_citation == "Wyrok KIO z 2021-10-28, sygn. KIO 2924/21"
    )


def test_parse_orzeczenie_has_full_text_and_source_urls():
    orz = parse_orzeczenie(
        _fixture(f"content_html_{KIO_2924_21_ID}.html"),
        f"https://orzeczenia.uzp.gov.pl/Home/Details/{KIO_2924_21_ID}",
        KIO_2924_21_ID,
    )

    assert len(orz.content_text) > 10_000, "tresc orzeczenia podejrzanie krotka"
    assert "Krajowa Izba Odwoławcza" in orz.content_text
    assert orz.source_url_html.endswith(f"/Home/Details/{KIO_2924_21_ID}")
    assert orz.source_url_content.startswith(
        f"https://orzeczenia.uzp.gov.pl/Home/ContentHtml/{KIO_2924_21_ID}"
    )
    assert orz.source_url_pdf == (
        f"https://orzeczenia.uzp.gov.pl/Home/PdfContent/{KIO_2924_21_ID}?Kind=KIO"
    )
    assert orz.sentence, "sentencja nie wyodrebniona"
    assert orz.reasoning, "uzasadnienie nie wyodrebnione"


def test_parse_orzeczenie_without_details_falls_back_to_content():
    """Bez metryki parser nadal musi wyciagnac sygnature i date z tresci."""
    orz = parse_orzeczenie(
        _fixture(f"content_html_{KIO_2924_21_ID}.html"),
        f"https://orzeczenia.uzp.gov.pl/Home/Details/{KIO_2924_21_ID}",
        KIO_2924_21_ID,
    )

    assert orz.signature == "KIO 2924/21"
    assert orz.issue_date == date(2021, 10, 28)
    assert orz.doc_type == "wyrok"


# ---------------------------------------------------------------------------
# Jednostkowe: daty, URL-e, payload formularza
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("28-10-2021", date(2021, 10, 28)),   # format listy i metryki UZP
        ("28.10.2021", date(2021, 10, 28)),
        ("2021-10-28", date(2021, 10, 28)),
        ("28 października 2021", date(2021, 10, 28)),
        ("28 pazdziernika 2021", date(2021, 10, 28)),
        ("-", None),
        ("", None),
        ("brak daty", None),
        ("32-13-2021", None),
    ],
)
def test_parse_pl_date(text, expected):
    assert _parse_pl_date(text) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://orzeczenia.uzp.gov.pl/Home/Details/15903", 15903),
        ("/Home/ContentHtml/15903?Kind=KIO&flection=0", 15903),
        ("/Home/PdfContent/15903?Kind=KIO", 15903),
        ("/Home/HtmlContent/15903?Kind=KIO", 15903),  # legacy, do v0.2.2
        ("https://orzeczenia.uzp.gov.pl/Home/Search?Phrase=cena", None),
    ],
)
def test_extract_internal_id_from_url(url, expected):
    assert extract_internal_id_from_url(url) == expected


def test_search_form_data_uses_current_uzp_field_names():
    """REGRESJA v0.2.2: klient wysylal `phrase`/`dateFrom`/`contentSearch`, ktore UZP ignoruje."""
    data = KioClient._search_form_data(
        phrase="rażąco niska cena",
        signature="KIO 2924/21",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 7, 31),
        subject_index="rażąco niska cena",
        pzp_article="art. 226 ust. 1 pkt 5",
        inflection=True,
        content_search=True,
        page=2,
        sort="date_desc",
    )

    assert data == {
        "Kind": "KIO",
        "Pg": "2",
        "CountStats": "True",
        "Phrase": "rażąco niska cena",
        "Sign": "KIO 2924/21",
        "ThIdx": "rażąco niska cena",
        "Art": "art. 226 ust. 1 pkt 5",
        "Dt": "01-06-2026 - 31-07-2026",
        "Fle": "1",
        "SCnt": "1",
        "Srt": "date_desc",
    }


def test_search_form_data_omits_unchecked_boxes():
    data = KioClient._search_form_data(phrase="cena", inflection=False, content_search=False)
    assert "Fle" not in data and "SCnt" not in data


def test_search_form_data_completes_open_date_range():
    """UZP wymaga pelnego zakresu 'od - do' - podanie samego `date_from` nie moze go urwac."""
    data = KioClient._search_form_data(date_from=date(2026, 1, 1))
    lo, hi = data["Dt"].split(" - ")
    assert lo == "01-01-2026"
    assert hi == date.today().strftime("%d-%m-%Y")


def test_search_form_data_rejects_unknown_sort():
    with pytest.raises(ValueError, match="Invalid sort"):
        KioClient._search_form_data(phrase="cena", sort="relevance")
