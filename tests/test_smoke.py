"""Smoke testy online - hit live UZP. Rate-limited 1 req/s.

Wieslaw uruchamia recznie:
    pytest tests/test_smoke.py -v -m smoke

Te testy moga byc flaky jezeli:
- UZP zmieni HTML / strukture wyszukiwarki -> parser wymaga update
- UZP jest down / pod load
- Network problem

W razie failure - PIERWSZE: odswiez fixture'y (`tests/fixtures/README.md`) i uruchom
`tests/test_parser_regression.py`; jesli offline testy tez padaja, UZP zmienil strukture
i trzeba poprawic selektory w `parser.py` / nazwy pol w `client.py`.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_smoke_search_phrase():
    """kio_search po frazie zwraca niezerowy total - REGRESJA v0.2.2 (total=0 zawsze)."""
    from kio_orzeczenia_mcp.server import kio_search

    result = await kio_search(phrase="rażąco niska cena", size=5)
    assert result["total"] > 0, "total=0 - wyszukiwarka UZP znowu zmieniona, patrz DISCOVERY.md"
    assert len(result["items"]) == 5

    first = result["items"][0]
    assert first["signature"].startswith("KIO ")
    assert first["source_url"].startswith("https://orzeczenia.uzp.gov.pl/Home/Details/")


@pytest.mark.asyncio
async def test_smoke_search_pagination():
    """size > 10 wymaga sklejenia stron UZP (10 wynikow/strona), bez duplikatow.

    UZP przy sortowaniu po trafnosci zwraca strony zachodzace na siebie, wiec
    egzekwujemy unikalnosc, a nie dokladnie `size` pozycji.
    """
    from kio_orzeczenia_mcp.server import kio_search

    result = await kio_search(phrase="wykluczenie wykonawcy", size=15)
    ids = [it["internal_id"] for it in result["items"]]

    assert len(ids) > 10, "sklejanie stron nie zadzialalo - dostalismy jedna strone UZP"
    assert len(ids) <= 15
    assert len(set(ids)) == len(ids), "duplikaty w wynikach - deduplikacja nie dziala"


@pytest.mark.asyncio
async def test_smoke_search_pagination_stable_sort():
    """Przy sortowaniu po dacie ranking nie przetasowuje - komplet `size` wynikow."""
    from kio_orzeczenia_mcp.server import kio_search

    result = await kio_search(phrase="cena", sort="date_desc", size=15)
    ids = [it["internal_id"] for it in result["items"]]
    assert len(ids) == 15
    assert len(set(ids)) == 15


@pytest.mark.asyncio
async def test_smoke_search_recent():
    """kio_recent(days=365) zwraca co najmniej 1 wynik.

    UWAGA: UZP publikuje z opoznieniem - dla days=30 pusta lista bywa poprawna,
    dlatego smoke test bierze szerszy zakres.
    """
    from kio_orzeczenia_mcp.server import kio_recent

    items = await kio_recent(days=365, limit=10)
    assert isinstance(items, list)
    assert len(items) > 0, "Brak orzeczen z ostatniego roku - sprawdz parser albo UZP"

    first = items[0]
    assert first["signature"].startswith("KIO ")
    assert first["internal_id"] > 0
    assert first["issue_date"], "kio_recent filtruje po dacie, wiec data musi byc znana"
    assert first["source_url"].startswith("https://orzeczenia.uzp.gov.pl/Home/Details/")
    assert f"sygn. {first['signature']}" in first["human_readable_citation"]
    assert first["issue_date"] in first["human_readable_citation"]

    dates = [it["issue_date"] for it in items if it["issue_date"]]
    assert dates == sorted(dates, reverse=True), "kio_recent ma sortowac malejaco po dacie"


@pytest.mark.asyncio
async def test_smoke_get_orzeczenie():
    """kio_get_orzeczenie('KIO 2924/21') zwraca pelne orzeczenie z metryka."""
    from kio_orzeczenia_mcp.server import kio_get_orzeczenie

    orz = await kio_get_orzeczenie("KIO 2924/21")
    assert orz["signature"].lower().replace(" ", "") == "kio2924/21"
    assert orz["internal_id"] == 15903
    assert orz["issue_date"] == "2021-10-28"
    assert orz["doc_type"] == "wyrok"
    assert len(orz["content_text"]) > 100, "Tresc orzeczenia podejrzanie krotka"
    assert orz["source_url_html"].startswith("https://orzeczenia.uzp.gov.pl/Home/Details/")
    assert orz["source_url_content"].startswith("https://orzeczenia.uzp.gov.pl/Home/ContentHtml/")
    assert orz["source_url_pdf"].startswith("https://orzeczenia.uzp.gov.pl/Home/PdfContent/")
    assert isinstance(orz["pzp_articles"], list) and orz["pzp_articles"]


@pytest.mark.asyncio
async def test_smoke_pzp_article():
    """kio_by_pzp_article zwraca co najmniej 1 wynik (filtr server-side UZP)."""
    from kio_orzeczenia_mcp.server import kio_by_pzp_article

    items = await kio_by_pzp_article("art. 226 ust. 1 pkt 5", limit=10)
    assert isinstance(items, list)
    assert len(items) >= 1, "Brak orzeczen dla art. 226 ust. 1 pkt 5 - filtr Art albo parser broken"


@pytest.mark.asyncio
async def test_smoke_pdf_url():
    """kio_get_pdf_url zwraca poprawny PDF URL."""
    from kio_orzeczenia_mcp.server import kio_get_pdf_url

    response = await kio_get_pdf_url("KIO 2924/21")
    assert response["pdf_url"].startswith("https://orzeczenia.uzp.gov.pl/Home/PdfContent/")
    assert response["pdf_url"].endswith("?Kind=KIO")
    assert response["signature"].lower().replace(" ", "") == "kio2924/21"
    assert response["internal_id"] > 0
    assert "human_readable_citation" in response


@pytest.mark.asyncio
async def test_smoke_pdf_url_is_reachable():
    """Link PDF, ktory podajemy uzytkownikowi, musi faktycznie dzialac (HEAD 200)."""
    import httpx

    from kio_orzeczenia_mcp import USER_AGENT

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        resp = await c.head(
            "https://orzeczenia.uzp.gov.pl/Home/PdfContent/15903?Kind=KIO",
            headers={"User-Agent": USER_AGENT},
        )
    assert resp.status_code == 200, f"PDF UZP zwraca {resp.status_code} - sciezka zmieniona?"
