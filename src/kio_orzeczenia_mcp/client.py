"""httpx async client z rate limit + retry/backoff dla orzeczenia.uzp.gov.pl.

Wyszukiwarka UZP jest AJAX-owa: strona `/` i `/Home/Search` to tylko shell z formularzem,
a wyniki dociagane sa POST-em na `/Home/GetResults` (form-urlencoded). Nazwy pol formularza
sa krotkie i case-sensitive - patrz `_search_form_data`.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Optional

import httpx

from . import (
    BASE_URL,
    CONTENT_PATH,
    DETAILS_PATH,
    PDF_PATH,
    SEARCH_PATH,
    USER_AGENT,
)
from .rate_limit import RateLimiter, from_env


# Najstarsze orzeczenia w bazie UZP - uzywane gdy podano tylko `date_to`
# (UZP wymaga PELNEGO zakresu "od - do" w polu Dt).
_MIN_DATE = date(2004, 1, 1)

# Dopuszczalne wartosci pola Srt (sortowanie) w formularzu UZP.
VALID_SORTS = frozenset({"rank", "date_asc", "date_desc"})


def _fmt_dt(d: date) -> str:
    """UZP oczekuje dat w formacie DD-MM-YYYY (nie ISO)."""
    return d.strftime("%d-%m-%Y")


class KioClient:
    """Async HTTP client z global rate limit i retry na 429/503.

    Uzywaj jako async context manager:
        async with KioClient() as c:
            html, url = await c.get_content_html(15903)
    """

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        timeout: float = 30.0,
    ):
        self._rate_limiter = rate_limiter or from_env()
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "KioClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        """Wykonuje request z rate limit i backoff na 429/503."""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            await self._rate_limiter.acquire()
            try:
                resp = await self._client.request(method, url, params=params, data=data)
            except httpx.RequestError as e:
                last_exc = e
                await asyncio.sleep(2 ** attempt)
                continue

            if resp.status_code in (429, 503):
                # respektuj Retry-After
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = 2 ** attempt
                else:
                    wait = 2 ** attempt
                await asyncio.sleep(min(wait, 60.0))
                continue

            resp.raise_for_status()
            return resp

        if last_exc is not None:
            raise last_exc
        raise httpx.HTTPError(f"Failed after {max_retries} retries: {method} {url}")

    # ---------- pojedynczy dokument ----------

    async def get_content_html(self, internal_id: int) -> tuple[str, str]:
        """GET /Home/ContentHtml/{id}?Kind=KIO - pelna tresc orzeczenia.

        UWAGA: do v0.2.2 klient uderzal w `/Home/HtmlContent/{id}` (odwrocona nazwa),
        ktore zwraca 404. Poprawna sciezka to `/Home/ContentHtml/{id}`.

        Returns:
            (html_text, full_url)
        """
        url = f"{CONTENT_PATH}/{internal_id}"
        params = {"Kind": "KIO", "flection": "0"}
        resp = await self._request("GET", url, params=params)
        return resp.text, f"{BASE_URL}{url}?Kind=KIO&flection=0"

    async def get_details(self, internal_id: int) -> tuple[str, str]:
        """GET /Home/Details/{id} - metryka orzeczenia (data, sklad, strony, przepisy PZP).

        To jest kanoniczny URL "do klikniecia przez czlowieka" - cytujemy go w
        `source_url_html`.

        Returns:
            (html_text, full_url)
        """
        url = f"{DETAILS_PATH}/{internal_id}"
        resp = await self._request("GET", url)
        return resp.text, f"{BASE_URL}{url}"

    # ---------- wyszukiwarka ----------

    @staticmethod
    def _search_form_data(
        phrase: Optional[str] = None,
        signature: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        subject_index: Optional[str] = None,
        pzp_article: Optional[str] = None,
        inflection: bool = True,
        content_search: bool = True,
        page: int = 1,
        sort: Optional[str] = None,
        kind: str = "KIO",
    ) -> dict[str, str]:
        """Buduje payload formularza UZP.

        Mapowanie nazw pol (stan 2026-07-31):
            Phrase  - fraza                     Sign  - sygnatura
            Fle     - odmiana slow (checkbox)   SCnt  - szukaj w tresci (checkbox)
            Dt      - zakres dat "DD-MM-YYYY - DD-MM-YYYY"
            ThIdx   - indeks tematyczny         Art   - przepis PZP (filtr SERVER-SIDE)
            Kind    - KIO/SO/SA/SN              Pg    - numer strony (10 wynikow/strona)
            Srt     - rank | date_asc | date_desc
            CountStats - True zeby serwer policzyl total

        Checkboxy Fle/SCnt: przegladarka NIE wysyla ich gdy odznaczone, wiec przy
        False pomijamy klucz (Fle=0 daje ten sam wynik, ale trzymamy sie zachowania
        przegladarki).
        """
        data: dict[str, str] = {
            "Kind": kind,
            "Pg": str(page),
            "CountStats": "True",
        }
        if phrase:
            data["Phrase"] = phrase
        if signature:
            data["Sign"] = signature
        if subject_index:
            data["ThIdx"] = subject_index
        if pzp_article:
            data["Art"] = pzp_article
        if date_from or date_to:
            lo = date_from or _MIN_DATE
            hi = date_to or date.today()
            data["Dt"] = f"{_fmt_dt(lo)} - {_fmt_dt(hi)}"
        if inflection:
            data["Fle"] = "1"
        if content_search:
            data["SCnt"] = "1"
        if sort:
            if sort not in VALID_SORTS:
                raise ValueError(f"Invalid sort {sort!r}. Valid: {sorted(VALID_SORTS)}")
            data["Srt"] = sort
        return data

    async def search(
        self,
        phrase: Optional[str] = None,
        signature: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        subject_index: Optional[str] = None,
        pzp_article: Optional[str] = None,
        inflection: bool = True,
        content_search: bool = True,
        page: int = 1,
        sort: Optional[str] = None,
    ) -> tuple[str, str]:
        """POST /Home/GetResults - fragment HTML z lista wynikow (10 na strone).

        Returns:
            (html_fragment, human_url) - `human_url` to GET-owy odpowiednik zapytania,
            ktory czlowiek moze otworzyc w przegladarce (/Home/Search?...).
        """
        data = self._search_form_data(
            phrase=phrase,
            signature=signature,
            date_from=date_from,
            date_to=date_to,
            subject_index=subject_index,
            pzp_article=pzp_article,
            inflection=inflection,
            content_search=content_search,
            page=page,
            sort=sort,
        )
        resp = await self._request("POST", SEARCH_PATH, data=data)
        return resp.text, self.human_search_url(data)

    @staticmethod
    def human_search_url(form_data: dict[str, str]) -> str:
        """URL wyszukiwarki do otwarcia przez czlowieka (audit log / cytowanie)."""
        qs = httpx.QueryParams(form_data)
        return f"{BASE_URL}/Home/Search?{qs}"

    # ---------- URL-e bez pobierania ----------

    def pdf_url(self, internal_id: int) -> str:
        """Buduje URL do PDF (NIE pobiera bytes)."""
        return f"{BASE_URL}{PDF_PATH}/{internal_id}?Kind=KIO"

    def details_url(self, internal_id: int) -> str:
        """Buduje URL metryki orzeczenia (strona dla czlowieka)."""
        return f"{BASE_URL}{DETAILS_PATH}/{internal_id}"
