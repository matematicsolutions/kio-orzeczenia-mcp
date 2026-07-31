"""Odswieza fixture'y HTML z orzeczenia.uzp.gov.pl dla testow regresyjnych parsera.

    python scripts/refresh_fixtures.py

Respektuje rate limit (1 req/s), pobiera 4 dokumenty. Po odswiezeniu uruchom:

    pytest tests/test_parser_regression.py -q

Jesli testy padaja - UZP zmienil strukture. Poprawiaj parser, nie asercje.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kio_orzeczenia_mcp import (  # noqa: E402
    BASE_URL,
    CONTENT_PATH,
    DETAILS_PATH,
    SEARCH_PATH,
    USER_AGENT,
)

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
KIO_2924_21_ID = 15903
HEADERS = {"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"}
BASE_FORM = {"Fle": "1", "SCnt": "1", "Kind": "KIO", "Pg": "1", "CountStats": "True"}


def _write(name: str, text: str) -> None:
    (FIXTURES / name).write_text(text, encoding="utf-8")
    print(f"  {name:38s} {len(text):>7d} znakow")


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    print(f"Odswiezam fixture'y z {BASE_URL} (rate limit 1 req/s)")

    with httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=True) as c:
        r = c.post(SEARCH_PATH, data={**BASE_FORM, "Phrase": "rażąco niska cena"}, headers=HEADERS)
        r.raise_for_status()
        _write("search_results_kio.html", r.text)
        time.sleep(1)

        r = c.post(SEARCH_PATH, data={**BASE_FORM, "Sign": "KIO 2924/21"}, headers=HEADERS)
        r.raise_for_status()
        _write("search_results_by_signature.html", r.text)
        time.sleep(1)

        r = c.get(f"{DETAILS_PATH}/{KIO_2924_21_ID}", headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        _write(f"details_{KIO_2924_21_ID}.html", r.text)
        time.sleep(1)

        r = c.get(
            f"{CONTENT_PATH}/{KIO_2924_21_ID}",
            params={"Kind": "KIO", "flection": "0"},
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        _write(f"content_html_{KIO_2924_21_ID}.html", r.text)

    print("Gotowe. Uruchom: pytest tests/test_parser_regression.py -q")


if __name__ == "__main__":
    main()
