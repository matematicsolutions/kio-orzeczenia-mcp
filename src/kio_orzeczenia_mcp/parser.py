"""Parser HTML strony orzeczenia.uzp.gov.pl (selectolax).

UWAGA POC: selektory sa **best-effort** na podstawie discovery. Mozliwe ze beda wymagaly
korekt po pierwszym smoke teste z prawdziwym HTML. Patrz TODO w DISCOVERY.md.

Strategia: ZAWSZE staramy sie wyciagnac signature + internal_id + issue_date + content_text.
Pozostale pola (chamber_composition, parties, pzp_articles, sentence, reasoning) - best effort,
defaultujemy do pustych list/None jezeli parser nie znajdzie.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from selectolax.parser import HTMLParser

from . import BASE_URL
from .models import Orzeczenie, OrzeczenieSummary, Person
from .signature import parse_signature


# Regex helpers
_RE_SIG = re.compile(r"KIO\s+\d{1,5}\s*/\s*(?:\d{2}|\d{4})", re.IGNORECASE)
_RE_DATE_PL = re.compile(r"(\d{1,2})[.\s]+(\d{1,2}|stycz|luteg|marc|kwiet|maj|czerw|lip|sierp|wrze|pazd|listop|grud)[a-z]*[.\s]+(\d{4})", re.IGNORECASE)
_RE_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_INTERNAL_ID = re.compile(r"/Home/(?:HtmlContent|PdfContent)/(\d+)", re.IGNORECASE)
_RE_PZP_ART = re.compile(
    r"art\.\s*(\d+[a-z]?)(?:\s*ust\.\s*(\d+))?(?:\s*pkt\s*(\d+))?",
    re.IGNORECASE,
)


PL_MONTHS = {
    "styczn": 1, "stycze": 1,
    "luteg": 2, "lutym": 2,
    "marc": 3,
    "kwiet": 4,
    "maj": 5,
    "czerw": 6,
    "lip": 7,
    "sierp": 8,
    "wrze": 9,
    "pazd": 10, "październ": 10,
    "listop": 11,
    "grud": 12,
}


def _parse_pl_date(text: str) -> Optional[date]:
    """Parsuje polskie daty: "28 pazdziernika 2021", "2021-10-28", "28.10.2021"."""
    if not text:
        return None
    text = text.strip()

    m = _RE_DATE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 28.10.2021
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # 28 pazdziernika 2021
    m = re.search(r"(\d{1,2})\s+([a-zżźćńółęąś]+)\s+(\d{4})", text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month_word = m.group(2).lower()
        year = int(m.group(3))
        for prefix, num in PL_MONTHS.items():
            if month_word.startswith(prefix):
                try:
                    return date(year, num, day)
                except ValueError:
                    return None
    return None


def _extract_signature(html_text: str) -> Optional[str]:
    """Znajduje pierwsza sygnature KIO w tekscie."""
    m = _RE_SIG.search(html_text)
    if m:
        sig = m.group(0).strip()
        # normalizuj do "KIO {nr}/{rok}" przez parse + format short
        try:
            nr, year = parse_signature(sig)
            yy = year % 100
            return f"KIO {nr}/{yy:02d}"
        except ValueError:
            return sig
    return None


def _extract_pzp_articles(text: str) -> list[str]:
    """Wyciaga unikalne artykuly PZP wymieniane w tekscie."""
    found = set()
    for m in _RE_PZP_ART.finditer(text):
        art = m.group(1)
        ust = m.group(2)
        pkt = m.group(3)
        s = f"art. {art}"
        if ust:
            s += f" ust. {ust}"
        if pkt:
            s += f" pkt {pkt}"
        found.add(s)
    return sorted(found)


def parse_orzeczenie(html: str, source_url_html: str, internal_id: int) -> Orzeczenie:
    """Parser pelnego orzeczenia z /Home/HtmlContent/{id}."""
    tree = HTMLParser(html)

    # Plain text z body
    body_node = tree.body or tree.root
    content_text = body_node.text(separator="\n") if body_node else ""
    content_text = re.sub(r"\n{3,}", "\n\n", content_text).strip()

    # Signature - z naglowka albo z calego tekstu
    signature = _extract_signature(content_text) or f"KIO ?/? (id={internal_id})"

    # Issue date - szukaj w pierwszych 3000 znakach (czesto w naglowku "dnia 28 pazdziernika 2021 r.")
    head = content_text[:3000]
    issue_date = _parse_pl_date(head) or date(1970, 1, 1)

    # PZP articles z calej tresci
    pzp_articles = _extract_pzp_articles(content_text)

    # Chamber composition - heurystyka: szukaj "Przewodniczacy:", "Protokolant:"
    chamber: list[Person] = []
    for role_pattern, role_name in [
        (r"Przewodnicz[aą]cy[:\s]+([A-ZŻŹĆŃÓŁĘĄŚ][^\n,;]{2,80})", "przewodniczacy"),
        (r"Protokolant[:\s]+([A-ZŻŹĆŃÓŁĘĄŚ][^\n,;]{2,80})", "protokolant"),
        (r"Czlonkowie[:\s]+([A-ZŻŹĆŃÓŁĘĄŚ][^\n;]{2,200})", "czlonek"),
    ]:
        m = re.search(role_pattern, head)
        if m:
            chamber.append(Person(role=role_name, name=m.group(1).strip()))

    # Parties - heurystyka: szukaj "Odwolujacy:", "Zamawiajacy:"
    parties: list[Person] = []
    for role_pattern, role_name in [
        (r"Odwoluj[aą]cy[:\s]+([^\n]{2,200})", "odwolujacy"),
        (r"Zamawiaj[aą]cy[:\s]+([^\n]{2,200})", "zamawiajacy"),
        (r"Przyst[eę]puj[aą]cy[:\s]+([^\n]{2,200})", "przystepujacy"),
    ]:
        m = re.search(role_pattern, content_text[:8000])
        if m:
            parties.append(Person(role=role_name, name=m.group(1).strip()))

    # Sentence / reasoning - heurystyka (POC: tylko spróbuj wyodrebnic, jezeli nie da rady - None)
    sentence: Optional[str] = None
    reasoning: Optional[str] = None
    m = re.search(r"(orzeka|postanawia)[:\s]+(.*?)(?=uzasadnienie|sygn\. akt|$)", content_text, re.IGNORECASE | re.DOTALL)
    if m:
        sentence = m.group(2).strip()[:5000]  # cap dla bezpieczenstwa
    m = re.search(r"uzasadnienie[:\s]+(.*)", content_text, re.IGNORECASE | re.DOTALL)
    if m:
        reasoning = m.group(1).strip()

    pdf_url = f"{BASE_URL}/Home/PdfContent/{internal_id}?Kind=KIO"

    return Orzeczenie(
        signature=signature,
        internal_id=internal_id,
        issue_date=issue_date,
        chamber_composition=chamber,
        parties=parties,
        sentence=sentence,
        reasoning=reasoning,
        pzp_articles=pzp_articles,
        subject_index=[],
        content_text=content_text,
        source_url_html=source_url_html,
        source_url_pdf=pdf_url,
    )


def parse_search_results(html: str, source_url: str) -> tuple[int, list[OrzeczenieSummary]]:
    """Parser listy wynikow z /.

    Returns:
        (total_estimate, list_of_summaries)

    POC: scrapuje linki do /Home/HtmlContent/{id}?Kind=KIO + okoliczny kontekst.
    """
    tree = HTMLParser(html)
    body_text = (tree.body or tree.root).text(separator="\n") if tree.body or tree.root else ""

    summaries: list[OrzeczenieSummary] = []
    seen_ids: set[int] = set()

    # Znajdz wszystkie linki z internal_id
    for link in tree.css("a"):
        href = link.attributes.get("href", "")
        if not href:
            continue
        m = _RE_INTERNAL_ID.search(href)
        if not m:
            continue
        internal_id = int(m.group(1))
        if internal_id in seen_ids:
            continue
        seen_ids.add(internal_id)

        # Sygnatura - z tekstu linku albo otoczenia
        link_text = link.text(strip=True)
        signature = _extract_signature(link_text)
        if not signature:
            # sprobuj z parenta
            parent_text = link.parent.text(strip=True) if link.parent else ""
            signature = _extract_signature(parent_text)
        if not signature:
            continue

        # Issue date - sprobuj wyciagnac z otoczenia
        ctx = link.parent.text(separator=" ", strip=True) if link.parent else link_text
        issue_date = _parse_pl_date(ctx) or date(1970, 1, 1)

        # Snippet - tekst rodzica
        snippet = ctx[:300] if ctx else None

        # PZP articles z kontekstu
        pzp = _extract_pzp_articles(ctx)

        # Source URL absolute
        if href.startswith("http"):
            source_full = href
        else:
            source_full = f"{BASE_URL}{href}" if href.startswith("/") else f"{BASE_URL}/{href}"

        summaries.append(
            OrzeczenieSummary(
                signature=signature,
                internal_id=internal_id,
                issue_date=issue_date,
                snippet=snippet,
                pzp_articles=pzp,
                subject_index=[],
                source_url=source_full,
            )
        )

    # Total - sprobuj wyciagnac z paginacji ("Znaleziono 154 wyniki" lub podobne)
    total = len(summaries)
    m = re.search(r"znalezion[aoy]?\s+(\d+)", body_text, re.IGNORECASE)
    if m:
        try:
            total = int(m.group(1))
        except ValueError:
            pass

    return total, summaries


def extract_internal_id_from_url(url: str) -> Optional[int]:
    m = _RE_INTERNAL_ID.search(url)
    if m:
        return int(m.group(1))
    return None
