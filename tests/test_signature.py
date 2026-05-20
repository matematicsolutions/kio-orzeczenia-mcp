"""Offline unit testy parsera sygnatur KIO."""

from __future__ import annotations

from datetime import date

import pytest

from kio_orzeczenia_mcp.models import OrzeczenieSummary
from kio_orzeczenia_mcp.signature import (
    format_signature,
    format_signature_full,
    human_readable_citation,
    parse_signature,
)


class TestParseSignature:
    def test_parse_signature_basic(self):
        nr, rok = parse_signature("KIO 5072/25")
        assert nr == 5072 and rok == 2025

    def test_parse_signature_2924_21(self):
        nr, rok = parse_signature("KIO 2924/21")
        assert nr == 2924 and rok == 2021

    def test_signature_2_digit_year_24(self):
        # 24 -> 2024 (00-29 mapuje sie na 2000-2029)
        assert parse_signature("KIO 100/24")[1] == 2024

    def test_signature_2_digit_year_07(self):
        # 07 -> 2007 (poczatek dzialania KIO)
        assert parse_signature("KIO 1/07")[1] == 2007

    def test_signature_4_digit_year(self):
        nr, rok = parse_signature("KIO 1234/2024")
        assert nr == 1234 and rok == 2024

    def test_signature_lowercase(self):
        # case-insensitive
        nr, rok = parse_signature("kio 100/22")
        assert nr == 100 and rok == 2022

    def test_signature_extra_whitespace(self):
        nr, rok = parse_signature("  KIO   2924 / 21  ")
        assert nr == 2924 and rok == 2021

    def test_signature_legacy_year(self):
        # 99 -> 1999 (>= 30 -> 19xx)
        assert parse_signature("KIO 1/99")[1] == 1999

    def test_signature_invalid_format(self):
        with pytest.raises(ValueError):
            parse_signature("KIO/2024")

    def test_signature_empty(self):
        with pytest.raises(ValueError):
            parse_signature("")

    def test_signature_non_string(self):
        with pytest.raises(ValueError):
            parse_signature(12345)  # type: ignore[arg-type]

    def test_signature_wrong_prefix(self):
        with pytest.raises(ValueError):
            parse_signature("SAOS 100/24")


class TestFormatSignature:
    def test_format_signature_short(self):
        assert format_signature(2924, 2021) == "KIO 2924/21"

    def test_format_signature_pads_year(self):
        assert format_signature(1, 2007) == "KIO 1/07"

    def test_format_signature_full(self):
        assert format_signature_full(2924, 2021) == "KIO 2924/2021"


class TestHumanReadableCitation:
    def test_basic(self):
        assert (
            human_readable_citation("KIO 2924/21", "2021-10-28")
            == "Wyrok KIO z 2021-10-28, sygn. KIO 2924/21"
        )


class TestOrzeczenieSummaryCitation:
    def test_computed_citation(self):
        o = OrzeczenieSummary(
            signature="KIO 2924/21",
            internal_id=15903,
            issue_date=date(2021, 10, 28),
            source_url="https://orzeczenia.uzp.gov.pl/Home/HtmlContent/15903?Kind=KIO",
        )
        assert o.human_readable_citation == "Wyrok KIO z 2021-10-28, sygn. KIO 2924/21"

    def test_summary_minimal(self):
        o = OrzeczenieSummary(
            signature="KIO 5072/25",
            internal_id=32111,
            issue_date=date(2025, 9, 15),
            source_url="https://orzeczenia.uzp.gov.pl/Home/HtmlContent/32111?Kind=KIO",
        )
        assert o.signature == "KIO 5072/25"
        assert o.pzp_articles == []
        assert o.subject_index == []
        assert o.human_readable_citation == "Wyrok KIO z 2025-09-15, sygn. KIO 5072/25"


class TestRoundtrip:
    @pytest.mark.parametrize(
        "sig,expected_nr,expected_year",
        [
            ("KIO 2924/21", 2924, 2021),
            ("KIO 5072/25", 5072, 2025),
            ("KIO 100/24", 100, 2024),
            ("KIO 1/07", 1, 2007),
            ("KIO 12345/2023", 12345, 2023),
        ],
    )
    def test_parse_then_format_roundtrip(self, sig, expected_nr, expected_year):
        nr, year = parse_signature(sig)
        assert nr == expected_nr
        assert year == expected_year
        # Roundtrip dla 2-cyfrowego zapisu
        reformatted = format_signature(nr, year)
        nr2, year2 = parse_signature(reformatted)
        assert nr2 == nr and year2 == year
