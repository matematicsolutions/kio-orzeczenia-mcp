"""FastMCP server - 5 super-tools dla orzecznictwa KIO.

Uruchamianie:
    python -m kio_orzeczenia_mcp.server

Lub jako entry point po pip install:
    kio-orzeczenia-mcp
"""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timedelta
from typing import Union

from fastmcp import FastMCP

from . import BASE_URL, __version__
from . import audit
from . import cache as cache_mod
from .client import KioClient
from .models import (
    Orzeczenie,
    OrzeczenieSummary,
    PdfUrlResponse,
    SearchQuery,
    SearchResult,
)
from .parser import parse_orzeczenie, parse_search_results
from .signature import parse_signature


mcp = FastMCP(
    name="kio-orzeczenia-mcp",
    instructions=(
        "Orzecznictwo Krajowej Izby Odwolawczej (KIO) przy Urzedzie Zamowien Publicznych. "
        "Publiczna baza orzeczenia.uzp.gov.pl. Rate limit 1 req/s, cytowania obowiazkowe. "
        "Patrz CONSTITUTION.md."
    ),
)


# ---------- helpers ----------


def _cache_key_search(q: SearchQuery) -> str:
    parts = [
        f"q={q.phrase or ''}",
        f"sig={q.signature or ''}",
        f"df={q.date_from.isoformat() if q.date_from else ''}",
        f"dt={q.date_to.isoformat() if q.date_to else ''}",
        f"si={q.subject_index or ''}",
        f"inf={q.inflection}",
        f"cs={q.content_search}",
        f"p={q.page}",
        f"s={q.size}",
    ]
    return "search:" + "|".join(parts)


def _cache_key_orzeczenie(internal_id: int) -> str:
    return f"orz:{internal_id}"


# ---------- TOOL 1: kio_search ----------


@mcp.tool()
async def kio_search(
    phrase: str | None = None,
    signature: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    pzp_article: str | None = None,
    subject_index: str | None = None,
    inflection: bool = True,
    content_search: bool = True,
    page: int = 1,
    size: int = 20,
) -> dict:
    """Wyszukuje orzeczenia KIO w bazie orzeczenia.uzp.gov.pl.

    Wszystkie parametry opcjonalne. `pzp_article` to filtr post-process (brak server-side).

    Args:
        phrase: slowa kluczowe (np "razaco niska cena")
        signature: sygnatura "KIO {nr}/{rok}"
        date_from: YYYY-MM-DD
        date_to: YYYY-MM-DD
        pzp_article: artykul PZP do post-filter (np "226" lub "224 ust. 1 pkt 1")
        subject_index: indeks tematyczny
        inflection: odmiana slow (default True)
        content_search: szukaj w pelnej tresci (default True)
        page: strona wynikow (default 1)
        size: rozmiar strony (default 20, max 100)

    Returns:
        SearchResult jako dict: {total, page, size, items: [...], query, retrieved_at}
    """
    t0 = time.monotonic()

    df = date.fromisoformat(date_from) if date_from else None
    dt = date.fromisoformat(date_to) if date_to else None

    query = SearchQuery(
        phrase=phrase,
        signature=signature,
        date_from=df,
        date_to=dt,
        pzp_article=pzp_article,
        subject_index=subject_index,
        inflection=inflection,
        content_search=content_search,
        page=page,
        size=size,
    )

    cache_key = _cache_key_search(query)
    cached = cache_mod.get(cache_key)
    if cached is not None:
        latency = (time.monotonic() - t0) * 1000
        audit.log_event(
            tool="kio_search",
            params=query.model_dump(mode="json"),
            result_summary={"total": cached["total"], "items": len(cached["items"])},
            source_urls=[],
            latency_ms=latency,
            cache_hit=True,
        )
        return cached

    # Effective phrase - jezeli pzp_article podany a phrase nie, to filtruj przez art.
    effective_phrase = phrase
    if pzp_article and not phrase:
        effective_phrase = f"art. {pzp_article}"

    async with KioClient() as client:
        html, source_url = await client.search(
            phrase=effective_phrase,
            signature=signature,
            date_from=df.isoformat() if df else None,
            date_to=dt.isoformat() if dt else None,
            subject_index=subject_index,
            inflection=inflection,
            content_search=content_search,
            page=page,
        )

    total, items = parse_search_results(html, source_url)

    # Post-process filter po pzp_article
    if pzp_article:
        art_lower = pzp_article.lower().replace("art.", "").strip()
        items = [
            it for it in items
            if any(art_lower in a.lower() for a in it.pzp_articles)
        ]

    # Trim do size
    items = items[:size]

    result = SearchResult(
        total=total,
        page=page,
        size=size,
        items=items,
        query=query,
    )
    result_dict = result.model_dump(mode="json")

    cache_mod.set_search(cache_key, result_dict)

    latency = (time.monotonic() - t0) * 1000
    audit.log_event(
        tool="kio_search",
        params=query.model_dump(mode="json"),
        result_summary={"total": total, "items": len(items)},
        source_urls=[source_url],
        latency_ms=latency,
        cache_hit=False,
    )

    return result_dict


# ---------- TOOL 2: kio_get_orzeczenie ----------


@mcp.tool()
async def kio_get_orzeczenie(signature_or_id: Union[str, int]) -> dict:
    """Pobiera pelne orzeczenie KIO.

    Args:
        signature_or_id: "KIO 2924/21" (string) albo 15903 (internal int ID).
                         Sygnatura wymaga +1 req aby ustalic internal_id przez search.

    Returns:
        Orzeczenie jako dict z signature, internal_id, issue_date, chamber_composition,
        parties, sentence, reasoning, pzp_articles, content_text, source_url_html,
        source_url_pdf, human_readable_citation, retrieved_at.
    """
    t0 = time.monotonic()
    source_urls: list[str] = []

    # Resolve internal_id
    if isinstance(signature_or_id, int):
        internal_id = signature_or_id
        signature_input = None
    else:
        sig_str = str(signature_or_id).strip()
        # walidacja
        parse_signature(sig_str)
        signature_input = sig_str

        # cache lookup po sygnaturze
        sig_cache_key = f"sig2id:{sig_str.lower()}"
        cached_id = cache_mod.get(sig_cache_key)
        if cached_id is not None:
            internal_id = int(cached_id)
        else:
            # search by signature aby ustalic internal_id
            async with KioClient() as client:
                html, search_url = await client.search(signature=sig_str, page=1)
                source_urls.append(search_url)
            _, items = parse_search_results(html, search_url)
            match = next((it for it in items if it.signature.lower().replace(" ", "") == sig_str.lower().replace(" ", "")), None)
            if match is None and items:
                match = items[0]
            if match is None:
                latency = (time.monotonic() - t0) * 1000
                audit.log_event(
                    tool="kio_get_orzeczenie",
                    params={"signature_or_id": signature_or_id},
                    result_summary={"found": False},
                    source_urls=source_urls,
                    latency_ms=latency,
                    cache_hit=False,
                    error="not_found",
                )
                raise ValueError(f"Nie znaleziono orzeczenia o sygnaturze {sig_str!r}")
            internal_id = match.internal_id
            cache_mod.set_dictionary(sig_cache_key, internal_id)

    # Cache check
    cache_key = _cache_key_orzeczenie(internal_id)
    cached = cache_mod.get(cache_key)
    if cached is not None:
        latency = (time.monotonic() - t0) * 1000
        audit.log_event(
            tool="kio_get_orzeczenie",
            params={"signature_or_id": signature_or_id, "internal_id": internal_id},
            result_summary={"signature": cached.get("signature"), "from_cache": True},
            source_urls=source_urls,
            latency_ms=latency,
            cache_hit=True,
        )
        return cached

    async with KioClient() as client:
        html, html_url = await client.get_html_content(internal_id)
        source_urls.append(html_url)

    orz = parse_orzeczenie(html, html_url, internal_id)
    result_dict = orz.model_dump(mode="json")

    cache_mod.set_orzeczenie(cache_key, result_dict)
    # zapamietaj mapping sig -> id
    cache_mod.set_dictionary(f"sig2id:{orz.signature.lower()}", internal_id)

    latency = (time.monotonic() - t0) * 1000
    audit.log_event(
        tool="kio_get_orzeczenie",
        params={"signature_or_id": signature_or_id, "internal_id": internal_id},
        result_summary={
            "signature": orz.signature,
            "issue_date": orz.issue_date.isoformat(),
            "pzp_articles_count": len(orz.pzp_articles),
        },
        source_urls=source_urls,
        latency_ms=latency,
        cache_hit=False,
    )

    return result_dict


# ---------- TOOL 3: kio_recent ----------


@mcp.tool()
async def kio_recent(days: int = 30, limit: int = 20) -> list[dict]:
    """Najnowsze orzeczenia KIO z ostatnich N dni.

    Args:
        days: ile dni wstecz (default 30)
        limit: ile orzeczen zwrocic (default 20, max 100)

    Returns:
        Lista OrzeczenieSummary jako dict, sortowane malejaco po dacie.
    """
    today = date.today()
    df = today - timedelta(days=days)

    result = await kio_search(
        date_from=df.isoformat(),
        date_to=today.isoformat(),
        size=min(limit, 100),
    )

    # Sortuj malejaco po dacie
    items = result["items"]
    items.sort(key=lambda x: x.get("issue_date", ""), reverse=True)
    return items[:limit]


# ---------- TOOL 4: kio_by_pzp_article ----------


@mcp.tool()
async def kio_by_pzp_article(article: str, limit: int = 20) -> list[dict]:
    """Orzeczenia KIO cytujace konkretny artykul PZP.

    UWAGA: filtr post-process (brak server-side article filter w UZP).
    Realizowane przez phrase search "art. {article}" + post-filter na pzp_articles.

    Args:
        article: np "226" lub "224 ust. 1 pkt 1"
        limit: limit wynikow (default 20)

    Returns:
        Lista OrzeczenieSummary jako dict.
    """
    result = await kio_search(
        pzp_article=article,
        size=min(limit, 100),
    )
    return result["items"][:limit]


# ---------- TOOL 5: kio_get_pdf_url ----------


@mcp.tool()
async def kio_get_pdf_url(signature_or_id: Union[str, int]) -> dict:
    """Zwraca URL do PDF orzeczenia (NIE pobiera bytes).

    Args:
        signature_or_id: "KIO 2924/21" lub 15903

    Returns:
        {pdf_url, signature, internal_id, issue_date, human_readable_citation}
    """
    t0 = time.monotonic()
    source_urls: list[str] = []

    # Resolve internal_id (podobnie jak w get_orzeczenie, ale lzejszy flow)
    if isinstance(signature_or_id, int):
        internal_id = signature_or_id
        # signature unknown bez fetcha - sprobuj z cache, jezeli nie ma to fetchnij
        cache_key = _cache_key_orzeczenie(internal_id)
        cached = cache_mod.get(cache_key)
        if cached:
            signature = cached["signature"]
            issue_date_str = cached.get("issue_date")
            issue_date = date.fromisoformat(issue_date_str) if issue_date_str else None
        else:
            # fetch zeby ustalic sygnature
            async with KioClient() as client:
                html, html_url = await client.get_html_content(internal_id)
                source_urls.append(html_url)
            orz = parse_orzeczenie(html, html_url, internal_id)
            cache_mod.set_orzeczenie(cache_key, orz.model_dump(mode="json"))
            signature = orz.signature
            issue_date = orz.issue_date
    else:
        sig_str = str(signature_or_id).strip()
        parse_signature(sig_str)
        signature = sig_str

        sig_cache_key = f"sig2id:{sig_str.lower()}"
        cached_id = cache_mod.get(sig_cache_key)
        if cached_id is not None:
            internal_id = int(cached_id)
            issue_date = None
            # sprobuj wyciagnac date z cache orzeczenia
            orz_cached = cache_mod.get(_cache_key_orzeczenie(internal_id))
            if orz_cached:
                issue_date_str = orz_cached.get("issue_date")
                issue_date = date.fromisoformat(issue_date_str) if issue_date_str else None
        else:
            async with KioClient() as client:
                html, search_url = await client.search(signature=sig_str, page=1)
                source_urls.append(search_url)
            _, items = parse_search_results(html, search_url)
            if not items:
                raise ValueError(f"Nie znaleziono orzeczenia o sygnaturze {sig_str!r}")
            internal_id = items[0].internal_id
            issue_date = items[0].issue_date
            cache_mod.set_dictionary(sig_cache_key, internal_id)

    pdf_url = f"{BASE_URL}/Home/PdfContent/{internal_id}?Kind=KIO"
    response = PdfUrlResponse(
        pdf_url=pdf_url,
        signature=signature,
        internal_id=internal_id,
        issue_date=issue_date,
    )

    latency = (time.monotonic() - t0) * 1000
    audit.log_event(
        tool="kio_get_pdf_url",
        params={"signature_or_id": signature_or_id},
        result_summary={"signature": signature, "internal_id": internal_id},
        source_urls=source_urls + [pdf_url],
        latency_ms=latency,
        cache_hit=False,
    )

    return response.model_dump(mode="json")


# ---------- entry point ----------


def main() -> None:
    """Entry point dla stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
