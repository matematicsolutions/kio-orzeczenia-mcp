"""Smoke testy online - hit live UZP. Rate-limited 1 req/s.

Wieslaw uruchamia recznie:
    pytest tests/test_smoke.py -v -m smoke

Te testy moga byc flaky jezeli:
- UZP zmieni HTML / strukture wyszukiwarki -> parser wymaga update
- UZP jest down / pod load
- Network problem

W razie failure - PIERWSZE: sprawdz HTML w przegladarce, drugie: dostosuj selektory w parser.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_smoke_search_recent():
    """kio_recent(days=90) zwraca co najmniej 1 wynik."""
    from kio_orzeczenia_mcp.server import kio_recent

    items = await kio_recent(days=90, limit=10)
    assert isinstance(items, list)
    assert len(items) > 0, "Brak orzeczen z ostatnich 90 dni - sprawdz parser albo UZP"

    first = items[0]
    assert "signature" in first
    assert first["signature"].startswith("KIO ")
    assert "internal_id" in first
    assert "issue_date" in first
    assert "source_url" in first
    assert first["source_url"].startswith("https://orzeczenia.uzp.gov.pl")
    assert "human_readable_citation" in first
    assert first["human_readable_citation"].startswith("Wyrok KIO z ")


@pytest.mark.asyncio
async def test_smoke_get_orzeczenie():
    """kio_get_orzeczenie('KIO 2924/21') zwraca pelne orzeczenie z PZP articles."""
    from kio_orzeczenia_mcp.server import kio_get_orzeczenie

    orz = await kio_get_orzeczenie("KIO 2924/21")
    assert orz["signature"].lower().replace(" ", "") == "kio2924/21"
    assert orz["internal_id"] > 0
    assert "issue_date" in orz
    assert "content_text" in orz
    assert len(orz["content_text"]) > 100, "Tresc orzeczenia podejrzanie krotka"
    assert orz["source_url_html"].startswith("https://orzeczenia.uzp.gov.pl/Home/HtmlContent/")
    assert orz["source_url_pdf"].startswith("https://orzeczenia.uzp.gov.pl/Home/PdfContent/")
    # PZP articles - powinno byc co najmniej kilka (orzeczenie z 2021)
    assert isinstance(orz["pzp_articles"], list)


@pytest.mark.asyncio
async def test_smoke_pzp_article():
    """kio_by_pzp_article('226') zwraca co najmniej 1 wynik."""
    from kio_orzeczenia_mcp.server import kio_by_pzp_article

    items = await kio_by_pzp_article("226", limit=10)
    assert isinstance(items, list)
    assert len(items) >= 1, "Brak orzeczen cytujacych art. 226 PZP - parser albo phrase search broken"


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
