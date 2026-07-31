"""Parser HTML orzeczenia.uzp.gov.pl (selectolax).

Trzy rodzaje dokumentow do sparsowania:

1. **Lista wynikow** - fragment HTML z POST `/Home/GetResults`. Kazdy wynik to
   `div.search-list-item` z etykietami (`<label>Sygnatura:</label>` itd.) i linkiem
   `a.link-details` -> `/Home/Details/{id}`.
2. **Metryka** - `/Home/Details/{id}`. Strukturalne metadane: data wydania, rodzaj
   dokumentu, przewodniczacy, zamawiajacy, sposob rozstrzygniecia, przepisy PZP,
   indeks tematyczny. Zrodlo prawdy dla metadanych - NIE zgadujemy ich regexem.
3. **Tresc** - `/Home/ContentHtml/{id}`. Plain text orzeczenia (konwersja z .docx).

Heurystyki regexowe zostaly w parserze tresci (sentencja / uzasadnienie / sklad),
bo ta czesc nie jest ustrukturyzowana po stronie UZP.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional

from selectolax.parser import HTMLParser, Node

from . import BASE_URL, CONTENT_PATH, DETAILS_PATH, PDF_PATH
from .models import Orzeczenie, OrzeczenieSummary, Person
from .signature import parse_signature


# Regex helpers
_RE_SIG = re.compile(r"KIO\s+\d{1,5}\s*/\s*(?:\d{2}|\d{4})", re.IGNORECASE)
_RE_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RE_DATE_DMY = re.compile(r"\b(\d{1,2})[.\-](\d{1,2})[.\-](\d{4})\b")
_RE_DETAILS_ID = re.compile(r"/Home/Details/(\d+)", re.IGNORECASE)
# Stare sciezki (do v0.2.2) - tolerowane przy odczycie URL-i z cache/audytu.
_RE_LEGACY_ID = re.compile(r"/Home/(?:HtmlContent|ContentHtml|PdfContent)/(\d+)", re.IGNORECASE)
_RE_PZP_ART = re.compile(
    r"art\.\s*(\d+[a-z]?)(?:\s*ust\.\s*(\d+))?(?:\s*pkt\s*(\d+))?",
    re.IGNORECASE,
)
_RE_TOTAL = re.compile(r"Liczba znalezionych dokument\w*\s*:\s*([\d\s ]+)", re.IGNORECASE)


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

# Rodzaje dokumentow KIO wg pola "Rodzaj dokumentu" w metryce UZP.
KNOWN_DOC_TYPES = frozenset({"wyrok", "postanowienie", "uchwala", "uchwała"})


def _strip_diacritics(text: str) -> str:
    """ASCII-fikacja polskiego tekstu do porownan.

    UWAGA: `ł`/`Ł` nie maja rozkladu kanonicznego w NFKD (to osobne litery, nie
    litera + znak diakrytyczny), wiec trzeba je podmienic recznie - inaczej
    "artykulu" nigdy nie zmatchuje "artykułu".
    """
    text = text.replace("ł", "l").replace("Ł", "L")
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _norm_label(text: str) -> str:
    """Normalizuje etykiete do klucza: bez diakrytykow, lowercase, bez ':' i spacji brzegowych."""
    return _strip_diacritics(text).strip().rstrip(":").strip().lower()


def _parse_pl_date(text: str) -> Optional[date]:
    """Parsuje daty UZP: "2021-10-28", "28-10-2021", "28.10.2021", "28 pazdziernika 2021"."""
    if not text:
        return None
    text = text.strip()
    if text in {"-", "--", ""}:
        return None

    m = _RE_DATE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 28-10-2021 (format listy i metryki UZP) oraz 28.10.2021
    m = _RE_DATE_DMY.search(text)
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


def _normalize_signature(raw: str) -> Optional[str]:
    """Normalizuje sygnature do kanonicznego "KIO {nr}/{rr}"."""
    m = _RE_SIG.search(raw or "")
    if not m:
        return None
    sig = m.group(0).strip()
    try:
        nr, year = parse_signature(sig)
    except ValueError:
        return sig
    return f"KIO {nr}/{year % 100:02d}"


def _extract_signature(html_text: str) -> Optional[str]:
    """Znajduje pierwsza sygnature KIO w tekscie."""
    return _normalize_signature(html_text)


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


def _labelled_fields(node: Node) -> dict[str, str]:
    """Mapuje `<label>Nazwa</label> wartosc` -> {"nazwa": "wartosc"} w obrebie node'a.

    UZP renderuje metadane jako etykieta + tekst rodzica. Bierzemy tekst rodzica
    etykiety i odejmujemy od niego tekst samej etykiety.
    """
    out: dict[str, str] = {}
    for label in node.css("label"):
        parent = label.parent
        if parent is None:
            continue
        label_text = label.text(separator=" ", strip=True)
        key = _norm_label(label_text)
        if not key:
            continue
        parent_text = parent.text(separator=" ", strip=True)
        value = parent_text
        idx = parent_text.find(label_text)
        if idx != -1:
            value = parent_text[idx + len(label_text):]
        value = value.strip().lstrip(":").strip()
        # pierwsza etykieta wygrywa (metryka powtarza niektore pola w filtrach)
        if key not in out or not out[key]:
            out[key] = value
    return out


def _total_from_html(html: str, fallback: int) -> int:
    """Total z naglowka listy; fallback na `#resultCounts` (ALL,KIO,SO,SA,SN)."""
    m = _RE_TOTAL.search(html)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        if digits:
            return int(digits)
    m = re.search(r'id="resultCounts"[^>]*value="([\d,]+)"', html)
    if not m:
        m = re.search(r'value="([\d,]+)"[^>]*id="resultCounts"', html)
    if m:
        parts = m.group(1).split(",")
        if len(parts) == 5 and parts[1].isdigit():
            return int(parts[1])  # indeks 1 = KIO
    return fallback


def parse_search_results(html: str, source_url: str) -> tuple[int, list[OrzeczenieSummary]]:
    """Parser fragmentu listy wynikow z POST /Home/GetResults.

    Returns:
        (total, list_of_summaries) - `total` to liczba wszystkich trafien wg UZP,
        lista zawiera maks 10 pozycji (sztywna strona UZP).
    """
    tree = HTMLParser(html)

    summaries: list[OrzeczenieSummary] = []
    seen_ids: set[int] = set()

    for item in tree.css("div.search-list-item"):
        link = item.css_first("a.link-details")
        href = link.attributes.get("href", "") if link is not None else ""
        m = _RE_DETAILS_ID.search(href or "")
        if not m:
            # awaryjnie: jakikolwiek link z internal_id w obrebie itemu
            for any_link in item.css("a"):
                m = _RE_DETAILS_ID.search(any_link.attributes.get("href", "") or "")
                if m:
                    href = any_link.attributes.get("href", "")
                    break
        if not m:
            continue
        internal_id = int(m.group(1))
        if internal_id in seen_ids:
            continue

        fields = _labelled_fields(item)
        signature = _normalize_signature(fields.get("sygnatura", ""))
        if not signature:
            signature = _normalize_signature(item.text(separator=" ", strip=True))
        if not signature:
            continue

        seen_ids.add(internal_id)

        snippet_node = item.css_first("p.fragment")
        snippet = snippet_node.text(separator=" ", strip=True) if snippet_node else None
        if snippet:
            snippet = re.sub(r"\s+", " ", snippet).strip()[:300]

        doc_type = (fields.get("rodzaj dokumentu") or "").strip().lower() or None

        summaries.append(
            OrzeczenieSummary(
                signature=signature,
                internal_id=internal_id,
                issue_date=_parse_pl_date(fields.get("data wydania", "")),
                doc_type=doc_type,
                snippet=snippet,
                pzp_articles=[],      # lista wynikow ich nie zawiera - patrz kio_get_orzeczenie
                subject_index=[],
                source_url=f"{BASE_URL}{DETAILS_PATH}/{internal_id}",
            )
        )

    return _total_from_html(html, len(summaries)), summaries


def parse_details(html: str, internal_id: int) -> dict:
    """Parser metryki z /Home/Details/{id}.

    Returns:
        dict z kluczami: signature, issue_date, doc_type, outcome, chairman,
        purchaser, city, procedure, contract_type, pzp_articles, subject_index.
        Pola nieobecne w metryce -> None / pusta lista.
    """
    tree = HTMLParser(html)
    root = tree.body or tree.root
    metrics = tree.css_first("div.details-metrics") or root

    fields = _labelled_fields(metrics) if metrics is not None else {}

    # Sygnatura + sposob rozstrzygniecia: "<li>KIO 2924/21 / uwzglednione</li>"
    signature: Optional[str] = None
    outcome: Optional[str] = None
    sig_block = fields.get("sygnatura akt / sposob rozstrzygniecia", "")
    if sig_block:
        signature = _normalize_signature(sig_block)
        if "/" in sig_block:
            tail = sig_block.rsplit("/", 1)[-1].strip()
            if tail and not tail[0].isdigit():
                outcome = tail
    if not signature:
        heading = tree.css_first("h2.section-title")
        if heading is not None:
            signature = _normalize_signature(heading.text(separator=" ", strip=True))

    doc_type = (fields.get("rodzaj dokumentu") or "").strip().lower() or None

    # Przepisy PZP i indeks tematyczny - odrozniane po atrybucie `title` linku.
    pzp_articles: list[str] = []
    subject_index: list[str] = []
    for link in (root.css("a") if root is not None else []):
        title = _strip_diacritics(link.attributes.get("title", "") or "").lower()
        text = link.text(separator=" ", strip=True)
        if not text:
            continue
        text = re.sub(r"\s+", " ", text)
        if "dla artykulu" in title and text not in pzp_articles:
            pzp_articles.append(text)
        elif "dla indeksu tematycznego" in title and text not in subject_index:
            subject_index.append(text)

    def _clean(key: str) -> Optional[str]:
        v = (fields.get(key) or "").strip()
        return v or None

    return {
        "signature": signature,
        "issue_date": _parse_pl_date(fields.get("data wydania rozstrzygniecia", "")),
        "doc_type": doc_type,
        "outcome": outcome,
        "chairman": _clean("przewodniczacy"),
        "purchaser": _clean("zamawiajacy"),
        "city": _clean("miejscowosc"),
        "procedure": _clean("tryb postepowania"),
        "contract_type": _clean("rodzaj zamowienia"),
        "pzp_articles": pzp_articles,
        "subject_index": subject_index,
    }


def parse_orzeczenie(
    html: str,
    source_url_html: str,
    internal_id: int,
    details: Optional[dict] = None,
) -> Orzeczenie:
    """Parser pelnego orzeczenia.

    Args:
        html: tresc z /Home/ContentHtml/{id}
        source_url_html: kanoniczny URL metryki (/Home/Details/{id}) do cytowania
        internal_id: wewnetrzny ID UZP
        details: wynik `parse_details` - jezeli podany, metadane (data, rodzaj,
            przepisy PZP, indeks) pochodza z metryki, a nie z regexow na tresci.
    """
    tree = HTMLParser(html)

    body_node = tree.body or tree.root
    content_text = body_node.text(separator="\n") if body_node else ""
    content_text = re.sub(r"[ \t]+", " ", content_text)
    content_text = re.sub(r"\n{3,}", "\n\n", content_text).strip()

    details = details or {}
    head = content_text[:3000]

    signature = (
        details.get("signature")
        or _extract_signature(content_text)
        or f"KIO ?/? (id={internal_id})"
    )
    issue_date = details.get("issue_date") or _parse_pl_date(head)

    doc_type = details.get("doc_type")
    if not doc_type:
        m = re.search(r"\b(wyrok|postanowienie|uchwa[łl]a)\b", head, re.IGNORECASE)
        if m:
            doc_type = m.group(1).lower()

    pzp_articles = details.get("pzp_articles") or _extract_pzp_articles(content_text)
    subject_index = details.get("subject_index") or []

    # Sklad orzekajacy - heurystyka na tresci (UZP nie wystawia protokolanta w metryce).
    chamber: list[Person] = []
    if details.get("chairman"):
        chamber.append(Person(role="przewodniczacy", name=str(details["chairman"])))
    for role_pattern, role_name in [
        (r"Przewodnicz[aą]cy[:\s]+([A-ZŻŹĆŃÓŁĘĄŚ][^\n,;]{2,80})", "przewodniczacy"),
        (r"Protokolant[:\s]+([A-ZŻŹĆŃÓŁĘĄŚ][^\n,;]{2,80})", "protokolant"),
        (r"Cz[lł]onkowie[:\s]+([A-ZŻŹĆŃÓŁĘĄŚ][^\n;]{2,200})", "czlonek"),
    ]:
        if any(p.role == role_name for p in chamber):
            continue
        m = re.search(role_pattern, head)
        if m:
            chamber.append(Person(role=role_name, name=m.group(1).strip()))

    # Strony - metryka daje zamawiajacego, reszta heurystyka na tresci.
    parties: list[Person] = []
    if details.get("purchaser"):
        parties.append(Person(role="zamawiajacy", name=str(details["purchaser"])))
    for role_pattern, role_name in [
        (r"Odwo[lł]uj[aą]cy[:\s]+([^\n]{2,200})", "odwolujacy"),
        (r"Zamawiaj[aą]cy[:\s]+([^\n]{2,200})", "zamawiajacy"),
        (r"Przyst[eę]puj[aą]cy[:\s]+([^\n]{2,200})", "przystepujacy"),
    ]:
        if any(p.role == role_name for p in parties):
            continue
        m = re.search(role_pattern, content_text[:8000])
        if m:
            parties.append(Person(role=role_name, name=m.group(1).strip()))

    sentence: Optional[str] = None
    reasoning: Optional[str] = None
    m = re.search(
        r"(orzeka|postanawia)[:\s]+(.*?)(?=uzasadnienie|sygn\. akt|$)",
        content_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        sentence = m.group(2).strip()[:5000]  # cap dla bezpieczenstwa
    m = re.search(r"uzasadnienie[:\s]+(.*)", content_text, re.IGNORECASE | re.DOTALL)
    if m:
        reasoning = m.group(1).strip()

    return Orzeczenie(
        signature=signature,
        internal_id=internal_id,
        issue_date=issue_date,
        doc_type=doc_type,
        outcome=details.get("outcome"),
        chamber_composition=chamber,
        parties=parties,
        sentence=sentence,
        reasoning=reasoning,
        pzp_articles=pzp_articles,
        subject_index=subject_index,
        content_text=content_text,
        source_url_html=source_url_html,
        source_url_content=f"{BASE_URL}{CONTENT_PATH}/{internal_id}?Kind=KIO&flection=0",
        source_url_pdf=f"{BASE_URL}{PDF_PATH}/{internal_id}?Kind=KIO",
    )


def extract_internal_id_from_url(url: str) -> Optional[int]:
    """Wyciaga internal_id z URL-a UZP (Details, ContentHtml, PdfContent, legacy HtmlContent)."""
    m = _RE_DETAILS_ID.search(url) or _RE_LEGACY_ID.search(url)
    if m:
        return int(m.group(1))
    return None
