"""Parser i formatter sygnatur KIO.

Format kanoniczny: "KIO {nr}/{rok}", np "KIO 2924/21", "KIO 5072/25".
Lata 2-cyfrowe: 00-29 -> 2000-2029, 30-99 -> 1930-1999 (wstecznie zgodne).
W praktyce KIO dziala od 2007 roku, wiec wszystkie rzeczywiste lata 2-cyfrowe to >= 07 -> 2007+.
"""

from __future__ import annotations

import re

_SIGNATURE_RE = re.compile(r"^\s*KIO\s+(\d{1,5})\s*/\s*(\d{2}|\d{4})\s*$", re.IGNORECASE)


def parse_signature(signature: str) -> tuple[int, int]:
    """Parse "KIO {nr}/{rok}" do (nr, full_year).

    Examples:
        >>> parse_signature("KIO 2924/21")
        (2924, 2021)
        >>> parse_signature("KIO 5072/25")
        (5072, 2025)
        >>> parse_signature("KIO 100/24")
        (100, 2024)
        >>> parse_signature("KIO 1234/2024")
        (1234, 2024)

    Raises:
        ValueError: jezeli signature nie pasuje do wzorca.
    """
    if not isinstance(signature, str):
        raise ValueError(f"signature must be str, got {type(signature).__name__}")

    m = _SIGNATURE_RE.match(signature)
    if not m:
        raise ValueError(
            f"Invalid KIO signature format: {signature!r}. "
            f"Expected 'KIO {{nr}}/{{rok}}', np 'KIO 2924/21'."
        )

    nr = int(m.group(1))
    year_raw = m.group(2)

    if len(year_raw) == 4:
        year = int(year_raw)
    else:
        # 2-cyfrowy rok. KIO dziala od 2007, ale zachowujemy backward-compat:
        # 00-29 -> 2000-2029, 30-99 -> 1930-1999.
        yy = int(year_raw)
        year = 2000 + yy if yy < 30 else 1900 + yy

    return nr, year


def format_signature(nr: int, year: int) -> str:
    """Format do kanonicznego "KIO {nr}/{rok}".

    Domyslnie rok 4-cyfrowy. Jezeli chcesz 2-cyfrowy (np do query UZP) - uzyj format_signature_short.

    Examples:
        >>> format_signature(2924, 2021)
        'KIO 2924/21'
    """
    yy = year % 100
    return f"KIO {nr}/{yy:02d}"


def format_signature_full(nr: int, year: int) -> str:
    """Format z pelnym 4-cyfrowym rokiem.

    Examples:
        >>> format_signature_full(2924, 2021)
        'KIO 2924/2021'
    """
    return f"KIO {nr}/{year}"


def human_readable_citation(signature: str, issue_date: str) -> str:
    """Format cytatu dla czlowieka.

    Args:
        signature: kanoniczna sygnatura "KIO 2924/21"
        issue_date: ISO YYYY-MM-DD

    Returns:
        "Wyrok KIO z {YYYY-MM-DD}, sygn. {signature}"

    Examples:
        >>> human_readable_citation("KIO 2924/21", "2021-10-28")
        'Wyrok KIO z 2021-10-28, sygn. KIO 2924/21'
    """
    return f"Wyrok KIO z {issue_date}, sygn. {signature}"
