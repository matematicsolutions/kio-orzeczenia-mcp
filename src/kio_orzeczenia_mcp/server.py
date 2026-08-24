"""FastMCP server - 5 super-tools dla orzecznictwa KIO.

Uruchamianie:
    python -m kio_orzeczenia_mcp.server

Lub jako entry point po pip install:
    kio-orzeczenia-mcp
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional, Union

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import BASE_URL, PDF_PATH, UZP_PAGE_SIZE
from . import audit
from . import cache as cache_mod
from .client import KioClient
from .models import (
    OrzeczenieSummary,
    PdfUrlResponse,
    SearchQuery,
    SearchResult,
)
from .parser import parse_details, parse_orzeczenie, parse_search_results
from .signature import parse_signature
from .coverage import Coverage, build_coverage


# ---------------------------------------------------------------------------
# Instructions (procedural orchestration) - wstrzykiwane do system promptu
# klienta MCP. LLM widzi to PRZED pierwszym tool call.
# Drift test (tests/test_instructions_drift.py) failuje jesli tool w
# INSTRUCTIONS nie zarejestrowany lub ErrorCode nie udokumentowany.
# Pattern z dograh-hq/dograh v1.31.0 (BSD-2) via sejm-eli-mcp v0.2.0.
# ---------------------------------------------------------------------------

INSTRUCTIONS = """\
Ten serwer MCP udostepnia orzecznictwo Krajowej Izby Odwolawczej (KIO) przy Urzedzie Zamowien Publicznych. Publiczna baza orzeczenia.uzp.gov.pl (HTML scraping, brak oficjalnego REST API). Rate limit 1 req/s (token bucket, hard cap 2.0). Cache TTL: 7 dni orzeczenie, 6h lista, 30 dni slowniki PZP.

## Kolejnosc wywolan

### Sygnatura znana
1. `kio_get_orzeczenie` - pelne orzeczenie po sygnaturze (`KIO 2924/21`) lub internal_id. Sygnatura wymaga +1 req zeby ustalic internal_id przez search (1 req extra).

### Szukanie
2. `kio_search` - przeszukiwanie po `phrase` (slowa kluczowe), `signature`, `date_from/to` (YYYY-MM-DD), `subject_index` (indeks tematyczny, filtr server-side), `pzp_article` (filtr server-side), `inflection` (odmiana), `content_search` (pelna tresc), `sort` (`rank`/`date_asc`/`date_desc`). Maks `size=100`, paginacja przez `page`.
3. `kio_by_pzp_article` - skrot szukania po artykule PZP (np. `"art. 226 ust. 1 pkt 5"`). Filtr server-side UZP wymaga formatu `art. {nr} ust. {n} pkt {n}`; przy zerowym wyniku tool automatycznie schodzi do wyszukiwania frazowego.
4. `kio_recent` - najnowsze orzeczenia z ostatnich `days` dni (default 30, max 100 wynikow). Sortowane malejaco po dacie po stronie UZP.

### PDF
5. `kio_get_pdf_url` - URL do PDF orzeczenia. NIE pobiera bytes (zbyt ciezkie dla MCP). Zwraca pdf_url + signature + internal_id + issue_date.

## Twarde ograniczenia

- **Do not answer past the edge of this corpus** - when a search comes back empty, or the question touches material this connector does not carry, call `kio_coverage` and relay what it says is missing. Absence here is not absence in the law.
- **Sygnatura w formacie `KIO {nr}/{rok}`** - np. `KIO 2924/21` lub `KIO 5072/25`. Spacje wewnatrz tolerowane. Inne formaty (np. `KIO/UZP/...`) odrzucane jako `invalid_signature`.
- **Rate limit 1 req/s** - hard cap 2.0. NIE wysylaj burstow zapytan. UZP nie ma oficjalnego API, scrapujemy ostroznie z respektem dla zasobow sadu.
- **Bez modyfikacji tresci orzeczenia** - tekst urzedowy integralny. Zwracamy verbatim z UZP.
- **Pre-production wymaga**: wlasny smoke test + powiadomienie UZP zgodnie z CONSTITUTION.md.
- **`issue_date` moze byc `null`** - UZP nie ma daty wydania dla czesci starszych rekordow. Wtedy cytuj bez daty (`Wyrok KIO, sygn. KIO 22/17`). NIE zgaduj daty z sygnatury.
- **Cytowania obowiazkowe** w response: `human_readable_citation`, `source_url_html`, `source_url_pdf`. Cytuj te trzy w odpowiedzi koncowej.
- **Audit log JSONL** - kazdy tool call zapisuje audit do `~/.matematic/audit/kio-orzeczenia-mcp.jsonl` (bez pelnej tresci orzeczen).

## Iteracja po bledach

Tool zwraca structured error z prefixem `[code]`:
- `invalid_signature` - format sygnatury nieprawidlowy. Wymagany `KIO {nr}/{rok}` (np. `KIO 2924/21`).
- `missing_arg` - brakujacy wymagany parametr.
- `invalid_arg` - parametr poza zakresem (np. `size > 100`, `days < 1`, `date_from` po `date_to`).
- `not_found` - orzeczenie/sygnatura nie znaleziona w UZP. Sprobuj `kio_search` z innym query lub szerszej daty.
- `upstream_error` - blad UZP API (HTTP, timeout, parsing HTML failed). Retry raz przed surface do uzytkownika.

## Styl odpowiedzi

- Cytuj orzeczenia w pelnym formacie: `KIO 2924/21 (data 2021-10-15)`. Zawsze sygnatura + data, chyba ze `issue_date` jest `null` - wtedy sama sygnatura.
- Rodzaj dokumentu z pola `doc_type` - nie nazywaj postanowienia wyrokiem.
- Przy analizie linii orzeczniczej (`kio_by_pzp_article`) sortuj chronologicznie, komentuj zmiany linii.
- NIE wymyslaj sygnatur ani dat - wszystko z `structuredContent` / response fields.
- Przy `kio_get_pdf_url` poinformuj ze masz link, nie zawartosc - LLM nie pobiera bytes.
- Disclaimer KIO: orzeczenia KIO **nie sa zrodlem prawa** (art. 87 Konstytucji RP) - material referencyjny dla kancelarii zamowieniowych.
"""

# Strukturalne kody bledow - drift test asercja kazdy w klasie + w INSTRUCTIONS.
class KIOError(Exception):
    """Strukturalny blad dla kio MCP tools - widoczny dla LLM z prefixem [code]."""

    VALID_CODES = frozenset({
        "invalid_signature",
        "missing_arg",
        "invalid_arg",
        "not_found",
        "upstream_error",
    })

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown KIOError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,  # UZP scraping live
)


mcp = FastMCP(name="kio-orzeczenia-mcp", instructions=INSTRUCTIONS)


# ---------- helpers ----------


def _cache_key_search(q: SearchQuery) -> str:
    parts = [
        f"q={q.phrase or ''}",
        f"sig={q.signature or ''}",
        f"df={q.date_from.isoformat() if q.date_from else ''}",
        f"dt={q.date_to.isoformat() if q.date_to else ''}",
        f"si={q.subject_index or ''}",
        f"art={q.pzp_article or ''}",
        f"inf={q.inflection}",
        f"cs={q.content_search}",
        f"srt={q.sort or ''}",
        f"p={q.page}",
        f"s={q.size}",
    ]
    return "search:" + "|".join(parts)


def _cache_key_orzeczenie(internal_id: int) -> str:
    return f"orz:{internal_id}"


def _normalize_article(article: str) -> str:
    """Normalizuje artykul PZP do formatu filtra UZP: `art. 226 ust. 1 pkt 5`.

    Filtr `Art` w UZP dziala na slowniku przepisow i wymaga prefiksu `art.`
    (samo `"226"` zwraca 0 wynikow).
    """
    a = article.strip()
    if not a:
        return a
    if not a.lower().startswith("art"):
        a = f"art. {a}"
    return a


async def _fetch_pages(
    client: KioClient,
    query: SearchQuery,
    offset: int,
    needed: int,
) -> tuple[int, list[OrzeczenieSummary], str]:
    """Pobiera tyle stron UZP (po 10 wynikow), ile trzeba na `needed` pozycji od `offset`.

    UZP nie pozwala ustawic rozmiaru strony, wiec paginacje robimy po stronie klienta.
    Kazda strona to +1 request przy rate limicie 1 req/s - stad twardy limit stron.

    UWAGA: przy sortowaniu po trafnosci (domyslnym) kolejne strony UZP **zachodza na
    siebie** - ranking semantyczny przetasowuje wyniki miedzy requestami, wiec to samo
    orzeczenie potrafi wyjsc na stronie 1 i 2. Deduplikujemy po `internal_id` (podwojny
    cytat tego samego orzeczenia to defekt) i dobieramy do `EXTRA_PAGES` stron, zeby
    nadrobic ubytek. Przy mocnym zachodzeniu lista bywa krotsza niz `size` - to poprawny
    wynik, nie blad.
    """
    EXTRA_PAGES = 2
    first_uzp_page = offset // UZP_PAGE_SIZE + 1
    last_uzp_page = (offset + needed - 1) // UZP_PAGE_SIZE + 1
    max_pages = -(-100 // UZP_PAGE_SIZE) + EXTRA_PAGES  # size <= 100 + zapas na duplikaty
    hard_last_page = min(last_uzp_page + EXTRA_PAGES, first_uzp_page + max_pages - 1)

    skip = offset - (first_uzp_page - 1) * UZP_PAGE_SIZE
    collected: list[OrzeczenieSummary] = []
    seen_ids: set[int] = set()
    total = 0
    first_url = ""
    uzp_page = first_uzp_page

    while uzp_page <= hard_last_page:
        html, url = await client.search(
            phrase=query.phrase,
            signature=query.signature,
            date_from=query.date_from,
            date_to=query.date_to,
            subject_index=query.subject_index,
            pzp_article=_normalize_article(query.pzp_article) if query.pzp_article else None,
            inflection=query.inflection,
            content_search=query.content_search,
            page=uzp_page,
            sort=query.sort,
        )
        if not first_url:
            first_url = url
        page_total, page_items = parse_search_results(html, url)
        if page_total:
            total = page_total

        for item in page_items:
            if item.internal_id in seen_ids:
                continue
            seen_ids.add(item.internal_id)
            collected.append(item)

        uzp_page += 1
        if len(page_items) < UZP_PAGE_SIZE:
            break  # ostatnia strona wynikow
        if len(collected) >= skip + needed and uzp_page > last_uzp_page:
            break  # mamy komplet

    return total, collected[skip: skip + needed], first_url


# ---------- TOOL 1: kio_search ----------


@mcp.tool(annotations=READ_ONLY)
async def kio_search(
    phrase: str | None = None,
    signature: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    pzp_article: str | None = None,
    subject_index: str | None = None,
    inflection: bool = True,
    content_search: bool = True,
    sort: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """Wyszukuje orzeczenia KIO w bazie orzeczenia.uzp.gov.pl.

    Wszystkie parametry opcjonalne. `pzp_article` i `subject_index` to filtry
    server-side UZP (od 2026-07 wyszukiwarka je udostepnia).

    Args:
        phrase: slowa kluczowe (np "razaco niska cena")
        signature: sygnatura "KIO {nr}/{rok}"
        date_from: YYYY-MM-DD
        date_to: YYYY-MM-DD
        pzp_article: artykul PZP, format slownika UZP (np "art. 226 ust. 1 pkt 5")
        subject_index: indeks tematyczny (np "razaco niska cena")
        inflection: odmiana slow (default True)
        content_search: szukaj w pelnej tresci (default True)
        sort: "rank" (trafnosc) | "date_asc" | "date_desc"
        page: strona wynikow (default 1)
        size: rozmiar strony (default 20, max 100)

    Returns:
        SearchResult jako dict: {total, page, size, items: [...], query, retrieved_at}
    """
    t0 = time.monotonic()

    try:
        df = date.fromisoformat(date_from) if date_from else None
        dt = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise KIOError("invalid_arg", f"Data musi byc w formacie YYYY-MM-DD: {exc}") from exc
    if df and dt and df > dt:
        raise KIOError("invalid_arg", f"date_from ({df}) jest po date_to ({dt}).")

    try:
        query = SearchQuery(
            phrase=phrase,
            signature=signature,
            date_from=df,
            date_to=dt,
            pzp_article=pzp_article,
            subject_index=subject_index,
            inflection=inflection,
            content_search=content_search,
            sort=sort,
            page=page,
            size=size,
        )
    except ValueError as exc:
        raise KIOError("invalid_arg", str(exc)) from exc

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

    offset = (query.page - 1) * query.size
    try:
        async with KioClient() as client:
            total, items, source_url = await _fetch_pages(
                client, query, offset=offset, needed=query.size
            )
    except httpx.HTTPError as exc:
        raise KIOError("upstream_error", f"Blad UZP przy wyszukiwaniu: {exc}") from exc

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


@mcp.tool(annotations=READ_ONLY)
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
    else:
        sig_str = str(signature_or_id).strip()
        # walidacja
        try:
            parse_signature(sig_str)
        except ValueError as exc:
            raise KIOError("invalid_signature", str(exc)) from exc
        # cache lookup po sygnaturze
        sig_cache_key = f"sig2id:{sig_str.lower()}"
        cached_id = cache_mod.get(sig_cache_key)
        if cached_id is not None:
            internal_id = int(cached_id)
        else:
            # search by signature aby ustalic internal_id
            try:
                async with KioClient() as client:
                    html, search_url = await client.search(signature=sig_str, page=1)
            except httpx.HTTPError as exc:
                raise KIOError("upstream_error", f"Blad UZP przy wyszukiwaniu sygnatury: {exc}") from exc
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
                raise KIOError("not_found", f"Nie znaleziono orzeczenia o sygnaturze {sig_str!r} w UZP. Sprobuj kio_search z innym query.")
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

    # Metryka (/Home/Details) + tresc (/Home/ContentHtml) = 2 requesty.
    # Metadane bierzemy z metryki, nie z regexow na tresci.
    try:
        async with KioClient() as client:
            details_html, details_url = await client.get_details(internal_id)
            content_html, content_url = await client.get_content_html(internal_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise KIOError(
                "not_found",
                f"UZP nie zna dokumentu o internal_id={internal_id} (HTTP 404).",
            ) from exc
        raise KIOError("upstream_error", f"Blad UZP przy pobieraniu orzeczenia: {exc}") from exc
    except httpx.HTTPError as exc:
        raise KIOError("upstream_error", f"Blad UZP przy pobieraniu orzeczenia: {exc}") from exc

    source_urls.extend([details_url, content_url])

    details = parse_details(details_html, internal_id)
    orz = parse_orzeczenie(content_html, details_url, internal_id, details=details)
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
            "issue_date": orz.issue_date.isoformat() if orz.issue_date else None,
            "pzp_articles_count": len(orz.pzp_articles),
        },
        source_urls=source_urls,
        latency_ms=latency,
        cache_hit=False,
    )

    return result_dict


# ---------- TOOL 3: kio_recent ----------


@mcp.tool(annotations=READ_ONLY)
async def kio_recent(days: int = 30, limit: int = 20) -> list[dict]:
    """Najnowsze orzeczenia KIO z ostatnich N dni.

    UWAGA: UZP publikuje orzeczenia z opoznieniem - dla `days=30` lista bywa krotka
    lub pusta, i to jest poprawny wynik, a nie blad parsera. Przy pustym wyniku
    zaproponuj uzytkownikowi szerszy zakres (`days=90`).

    Args:
        days: ile dni wstecz (default 30, max 3650)
        limit: ile orzeczen zwrocic (default 20, max 100)

    Returns:
        Lista OrzeczenieSummary jako dict, sortowane malejaco po dacie (sort UZP).
    """
    if days < 1 or days > 3650:
        raise KIOError("invalid_arg", f"days musi byc w zakresie 1-3650, dostano {days}.")
    if limit < 1 or limit > 100:
        raise KIOError("invalid_arg", f"limit musi byc w zakresie 1-100, dostano {limit}.")

    today = date.today()
    df = today - timedelta(days=days)

    result = await kio_search(
        date_from=df.isoformat(),
        date_to=today.isoformat(),
        sort="date_desc",
        size=limit,
    )
    return result["items"][:limit]


# ---------- TOOL 4: kio_by_pzp_article ----------


@mcp.tool(annotations=READ_ONLY)
async def kio_by_pzp_article(article: str, limit: int = 20) -> list[dict]:
    """Orzeczenia KIO cytujace konkretny artykul PZP.

    Uzywa filtra server-side UZP (`Art`), ktory dziala na slowniku przepisow i jest
    wrazliwy na format: `"art. 226 ust. 1 pkt 5"` daje trafienia, samo `"226"` nie.
    Gdy filtr zwroci 0 wynikow, tool schodzi do wyszukiwania frazowego po tresci -
    wtedy trafienia sa szersze i wymagaja weryfikacji przez `kio_get_orzeczenie`.

    Args:
        article: np "art. 226 ust. 1 pkt 5" albo "224 ust. 1"
        limit: limit wynikow (default 20, max 100)

    Returns:
        Lista OrzeczenieSummary jako dict.
    """
    if not article or not article.strip():
        raise KIOError("missing_arg", "Parametr `article` jest wymagany (np 'art. 226 ust. 1 pkt 5').")
    if limit < 1 or limit > 100:
        raise KIOError("invalid_arg", f"limit musi byc w zakresie 1-100, dostano {limit}.")

    result = await kio_search(pzp_article=article, size=limit)
    if result["items"]:
        return result["items"][:limit]

    # Fallback: wyszukiwanie frazowe po tresci orzeczen.
    fallback = await kio_search(phrase=_normalize_article(article), size=limit)
    return fallback["items"][:limit]


# ---------- TOOL 5: kio_get_pdf_url ----------


@mcp.tool(annotations=READ_ONLY)
async def kio_get_pdf_url(signature_or_id: Union[str, int]) -> dict:
    """Zwraca URL do PDF orzeczenia (NIE pobiera bytes).

    Args:
        signature_or_id: "KIO 2924/21" lub 15903

    Returns:
        {pdf_url, signature, internal_id, issue_date, human_readable_citation}
    """
    t0 = time.monotonic()
    source_urls: list[str] = []
    issue_date: Optional[date] = None
    doc_type: Optional[str] = None

    # Resolve internal_id (podobnie jak w get_orzeczenie, ale lzejszy flow)
    if isinstance(signature_or_id, int):
        internal_id = signature_or_id
        # signature unknown bez fetcha - sprobuj z cache, jezeli nie ma to fetchnij metryke
        cache_key = _cache_key_orzeczenie(internal_id)
        cached = cache_mod.get(cache_key)
        if cached:
            signature = cached["signature"]
            issue_date_str = cached.get("issue_date")
            issue_date = date.fromisoformat(issue_date_str) if issue_date_str else None
            doc_type = cached.get("doc_type")
        else:
            # metryka wystarczy - NIE pobieramy pelnej tresci tylko po sygnature
            try:
                async with KioClient() as client:
                    details_html, details_url = await client.get_details(internal_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise KIOError(
                        "not_found",
                        f"UZP nie zna dokumentu o internal_id={internal_id} (HTTP 404).",
                    ) from exc
                raise KIOError("upstream_error", f"Blad UZP przy pobieraniu metryki: {exc}") from exc
            except httpx.HTTPError as exc:
                raise KIOError("upstream_error", f"Blad UZP przy pobieraniu metryki: {exc}") from exc
            source_urls.append(details_url)
            details = parse_details(details_html, internal_id)
            signature = details.get("signature") or f"KIO ?/? (id={internal_id})"
            issue_date = details.get("issue_date")
            doc_type = details.get("doc_type")
    else:
        sig_str = str(signature_or_id).strip()
        try:
            parse_signature(sig_str)
        except ValueError as exc:
            raise KIOError("invalid_signature", str(exc)) from exc
        signature = sig_str

        sig_cache_key = f"sig2id:{sig_str.lower()}"
        cached_id = cache_mod.get(sig_cache_key)
        if cached_id is not None:
            internal_id = int(cached_id)
            # sprobuj wyciagnac date z cache orzeczenia
            orz_cached = cache_mod.get(_cache_key_orzeczenie(internal_id))
            if orz_cached:
                issue_date_str = orz_cached.get("issue_date")
                issue_date = date.fromisoformat(issue_date_str) if issue_date_str else None
                doc_type = orz_cached.get("doc_type")
        else:
            try:
                async with KioClient() as client:
                    html, search_url = await client.search(signature=sig_str, page=1)
            except httpx.HTTPError as exc:
                raise KIOError("upstream_error", f"Blad UZP przy wyszukiwaniu sygnatury: {exc}") from exc
            source_urls.append(search_url)
            _, items = parse_search_results(html, search_url)
            if not items:
                raise KIOError("not_found", f"Nie znaleziono orzeczenia o sygnaturze {sig_str!r} w UZP. Sprobuj kio_search z innym query.")
            internal_id = items[0].internal_id
            issue_date = items[0].issue_date
            doc_type = items[0].doc_type
            cache_mod.set_dictionary(sig_cache_key, internal_id)

    pdf_url = f"{BASE_URL}{PDF_PATH}/{internal_id}?Kind=KIO"
    response = PdfUrlResponse(
        pdf_url=pdf_url,
        signature=signature,
        internal_id=internal_id,
        issue_date=issue_date,
        doc_type=doc_type,
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


@mcp.tool(annotations=READ_ONLY)
async def kio_coverage() -> Coverage:
    """Declare what this connector covers, how it is sourced, and what it does NOT cover.

    Call this before telling a user that the law "does not contain" something, and whenever
    a search comes back empty: the absence may be a gap in this connector rather than in the
    law. Every gap carries a fallback saying where to look instead.

    Returns:
        ``Coverage`` with families, an as-of note, and a non-empty list of known gaps.
    """
    return build_coverage()


# ---------- entry point ----------


def main() -> None:
    """Entry point dla stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
