"""Pydantic v2 models for KIO MCP."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, computed_field, field_validator

from .signature import human_readable_citation as _hrc
from .signature import parse_signature


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Person(BaseModel):
    """Osoba w skladzie KIO lub strona postepowania."""

    role: str = Field(..., description="np 'przewodniczacy', 'protokolant', 'odwolujacy', 'zamawiajacy'")
    name: str


class SearchQuery(BaseModel):
    """Parametry wyszukiwania orzecznictwa KIO.

    Wszystkie pola opcjonalne - mozna szukac po samej frazie albo np tylko po dacie.
    """

    phrase: Optional[str] = Field(default=None, description="slowa kluczowe / fraza")
    signature: Optional[str] = Field(default=None, description="sygnatura KIO np 'KIO 2924/21'")
    date_from: Optional[date] = Field(default=None, description="data wydania od (YYYY-MM-DD)")
    date_to: Optional[date] = Field(default=None, description="data wydania do (YYYY-MM-DD)")
    pzp_article: Optional[str] = Field(
        default=None,
        description="artykul PZP np '226' lub '224 ust. 1 pkt 1' (post-process filter)",
    )
    subject_index: Optional[str] = Field(default=None, description="indeks tematyczny")
    inflection: bool = Field(default=True, description="odmiana slow (default True)")
    content_search: bool = Field(default=True, description="szukaj tez w pelnej tresci")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)

    @field_validator("signature")
    @classmethod
    def _validate_signature(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # walidacja przez parser - rzuci ValueError jezeli zly format
        parse_signature(v)
        return v.strip()


class OrzeczenieSummary(BaseModel):
    """Skrocony rekord orzeczenia (z listy wynikow)."""

    signature: str = Field(..., description="np 'KIO 2924/21'")
    internal_id: int = Field(..., description="wewnetrzny ID bazy UZP")
    issue_date: date
    snippet: Optional[str] = Field(default=None, description="fragment z kontekstem frazy")
    pzp_articles: list[str] = Field(default_factory=list)
    subject_index: list[str] = Field(default_factory=list)
    source_url: str
    retrieved_at: str = Field(default_factory=_utcnow_iso)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def human_readable_citation(self) -> str:
        return _hrc(self.signature, self.issue_date.isoformat())


class Orzeczenie(BaseModel):
    """Pelne orzeczenie KIO."""

    signature: str
    internal_id: int
    issue_date: date
    chamber_composition: list[Person] = Field(default_factory=list)
    parties: list[Person] = Field(default_factory=list)
    sentence: Optional[str] = Field(default=None, description="sentencja (uwzglednienie/oddalenie + nakazy)")
    reasoning: Optional[str] = Field(default=None, description="uzasadnienie")
    pzp_articles: list[str] = Field(default_factory=list)
    subject_index: list[str] = Field(default_factory=list)
    content_text: str = Field(default="", description="pelny plain text orzeczenia")
    source_url_html: str
    source_url_pdf: str
    retrieved_at: str = Field(default_factory=_utcnow_iso)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def human_readable_citation(self) -> str:
        return _hrc(self.signature, self.issue_date.isoformat())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_url(self) -> str:
        """Default source URL (HTML) dla zachowania Art. 4 Konstytucji."""
        return self.source_url_html


class SearchResult(BaseModel):
    """Wynik wyszukiwania."""

    total: int = Field(..., ge=0, description="szacowana liczba wszystkich trafien")
    page: int = Field(..., ge=1)
    size: int = Field(..., ge=1)
    items: list[OrzeczenieSummary] = Field(default_factory=list)
    query: SearchQuery
    retrieved_at: str = Field(default_factory=_utcnow_iso)


class PdfUrlResponse(BaseModel):
    """Response dla kio_get_pdf_url."""

    pdf_url: str
    signature: str
    internal_id: int
    issue_date: Optional[date] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def human_readable_citation(self) -> str:
        if self.issue_date is None:
            return f"Wyrok KIO, sygn. {self.signature}"
        return _hrc(self.signature, self.issue_date.isoformat())
