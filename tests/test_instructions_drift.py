"""Drift test - INSTRUCTIONS spojne z zarejestrowanymi tools i KIOError.

Cherry-pick wzorca z dograh-hq/dograh v1.31.0 (BSD-2) via
sejm-eli-mcp v0.2.0 (pierwszy Python adaptacja).

Fail jesli:
  1. Tool name w INSTRUCTIONS (backtick) nie jest zarejestrowany w mcp
  2. ErrorCode w KIOError.VALID_CODES nie jest udokumentowany w INSTRUCTIONS
  3. `KIOError(<code>, ...)` w SRC uzywa kodu ktorego nie ma w VALID_CODES
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kio_orzeczenia_mcp.server import INSTRUCTIONS, KIOError, mcp


SRC = (
    Path(__file__).parent.parent / "src" / "kio_orzeczenia_mcp" / "server.py"
).read_text(encoding="utf-8")


def _registered_tool_names() -> set[str]:
    """Imiona wszystkich tooli zarejestrowanych w FastMCP."""
    if hasattr(mcp, "_tool_manager"):
        tools_dict = getattr(mcp._tool_manager, "_tools", {})
        if tools_dict:
            return set(tools_dict.keys())
    return set(re.findall(r"@mcp\.tool\([^)]*\)\s+async def (\w+)", SRC))


def _referenced_tool_names_in_instructions() -> set[str]:
    """Nazwy tooli w INSTRUCTIONS (backtick code spans `kio_xxx`)."""
    skip = {"isError", "true", "false"}
    out: set[str] = set()
    for m in re.finditer(r"`([a-z][a-z0-9_]{3,})`", INSTRUCTIONS):
        token = m.group(1)
        if token in skip:
            continue
        if "_" in token:
            out.add(token)
    return out


def test_instructions_only_reference_registered_tools():
    """Kazdy tool name w INSTRUCTIONS musi byc registered."""
    registered = _registered_tool_names()
    referenced = _referenced_tool_names_in_instructions()
    response_fields_skip = {
        "human_readable_citation",
        "source_url_html",
        "source_url_pdf",
        "pzp_articles",
        "pzp_article",
        "internal_id",
        "issue_date",
        "subject_index",
        "date_from",
        "date_to",
        "content_search",
        "structuredContent",
        "signature_or_id",
    }
    referenced_tools = {
        r for r in referenced
        if r.startswith("kio_") and r not in response_fields_skip
    }
    orphan = referenced_tools - registered
    assert not orphan, (
        f"INSTRUCTIONS referencuja tools ktorych nie ma w mcp: {orphan}. "
        f"Registered: {sorted(registered)}. "
        f"Jesli to nie tool a response field, dodaj do response_fields_skip."
    )


def test_error_codes_documented_in_instructions():
    """Kazdy ErrorCode w VALID_CODES musi byc w INSTRUCTIONS sekcji `Iteracja po bledach`."""
    undocumented = set()
    for code in KIOError.VALID_CODES:
        if not re.search(r"\b" + re.escape(code) + r"\b", INSTRUCTIONS):
            undocumented.add(code)
    assert not undocumented, (
        f"ErrorCode w VALID_CODES nie udokumentowany w INSTRUCTIONS: "
        f"{undocumented}. Dodaj wpis."
    )


def test_raised_error_codes_in_valid_codes():
    """Kazdy `KIOError(<code>, ...)` w kodzie musi byc w VALID_CODES."""
    raised = set(re.findall(r'KIOError\(\s*"(\w+)"\s*,', SRC))
    invalid = raised - KIOError.VALID_CODES
    assert not invalid, (
        f"KIOError uzywa kodow ktorych nie ma w VALID_CODES: {invalid}. "
        f"VALID_CODES: {sorted(KIOError.VALID_CODES)}"
    )


def test_kio_error_format():
    """KIOError formatuje jako '[code] message' dla LLM."""
    err = KIOError("invalid_signature", "Bad format: 'foo'")
    assert str(err).startswith("[invalid_signature] ")
    assert "Bad format" in str(err)


def test_kio_error_rejects_unknown_code():
    """KIOError z nieznanym code rzuca w konstruktorze - chroni przed drift."""
    with pytest.raises(ValueError, match="Unknown KIOError code"):
        KIOError("nonexistent_code", "x")


def test_all_valid_codes_constructible():
    """Wszystkie VALID_CODES powinny dac sie skonstruowac (sanity check)."""
    for code in KIOError.VALID_CODES:
        err = KIOError(code, "test message")
        assert err.code == code
        assert f"[{code}]" in str(err)
