"""Wspolna konfiguracja testow.

Najwazniejsze: testy NIE moga korzystac z produkcyjnego cache uzytkownika
(`~/.matematic/cache/kio/`, TTL 6h dla list wynikow). Bez izolacji smoke test potrafi
przejsc albo paso na wynikach sprzed poprawki - dokladnie taki falszywy sygnal pojawil
sie przy naprawie deduplikacji stron w v0.3.0.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Kazdy test dostaje wlasny, pusty katalog cache."""
    monkeypatch.setenv("KIO_MCP_CACHE_DIR", str(tmp_path / "cache"))

    from kio_orzeczenia_mcp import cache as cache_mod

    monkeypatch.setattr(cache_mod, "_cache", None, raising=False)
    yield
    cache = getattr(cache_mod, "_cache", None)
    if cache is not None:
        cache.close()
    monkeypatch.setattr(cache_mod, "_cache", None, raising=False)


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Testy nie dopisuja do produkcyjnego audit logu."""
    monkeypatch.setenv("KIO_MCP_AUDIT_DIR", str(tmp_path / "audit"))
