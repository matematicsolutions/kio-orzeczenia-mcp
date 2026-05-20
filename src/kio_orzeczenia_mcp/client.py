"""httpx async client z rate limit + retry/backoff dla orzeczenia.uzp.gov.pl."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from . import BASE_URL, USER_AGENT
from .rate_limit import RateLimiter, from_env


class KioClient:
    """Async HTTP client z global rate limit i retry na 429/503.

    Uzywaj jako async context manager:
        async with KioClient() as c:
            html = await c.get_html_content(15903)
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
        max_retries: int = 3,
    ) -> httpx.Response:
        """Wykonuje request z rate limit i backoff na 429/503."""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            await self._rate_limiter.acquire()
            try:
                resp = await self._client.request(method, url, params=params)
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

    async def get_html_content(self, internal_id: int) -> tuple[str, str]:
        """GET /Home/HtmlContent/{id}?Kind=KIO.

        Returns:
            (html_text, full_url)
        """
        url = f"/Home/HtmlContent/{internal_id}"
        params = {"Kind": "KIO"}
        resp = await self._request("GET", url, params=params)
        full_url = f"{BASE_URL}{url}?Kind=KIO"
        return resp.text, full_url

    async def search(
        self,
        phrase: Optional[str] = None,
        signature: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        subject_index: Optional[str] = None,
        inflection: bool = True,
        content_search: bool = True,
        page: int = 1,
    ) -> tuple[str, str]:
        """GET / (wyszukiwarka).

        Returns:
            (html_text, full_url)
        """
        params: dict[str, Any] = {"page": page}
        if phrase:
            params["phrase"] = phrase
        if signature:
            params["signature"] = signature
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if subject_index:
            params["subjectIndex"] = subject_index
        params["inflection"] = "true" if inflection else "false"
        params["contentSearch"] = "true" if content_search else "false"

        resp = await self._request("GET", "/", params=params)
        # Buduj URL do logow
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{BASE_URL}/?{qs}"
        return resp.text, full_url

    def pdf_url(self, internal_id: int) -> str:
        """Buduje URL do PDF (NIE pobiera bytes)."""
        return f"{BASE_URL}/Home/PdfContent/{internal_id}?Kind=KIO"
