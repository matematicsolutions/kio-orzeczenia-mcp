"""Diskcache wrapper - cache 7 dni orzeczenia, 6h listy, 30 dni slowniki."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from diskcache import Cache


# TTL w sekundach
TTL_ORZECZENIE = 7 * 24 * 3600       # 7 dni (immutable)
TTL_SEARCH = 6 * 3600                # 6 godzin
TTL_DICTIONARY = 30 * 24 * 3600      # 30 dni


def _cache_dir() -> Path:
    override = os.environ.get("KIO_MCP_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".matematic" / "cache" / "kio"


_cache: Optional[Cache] = None


def get_cache() -> Cache:
    """Lazy singleton dla Cache."""
    global _cache
    if _cache is None:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        _cache = Cache(str(d))
    return _cache


def get(key: str) -> Any:
    """Zwraca wartosc albo None."""
    return get_cache().get(key)


def set_orzeczenie(key: str, value: Any) -> None:
    get_cache().set(key, value, expire=TTL_ORZECZENIE)


def set_search(key: str, value: Any) -> None:
    get_cache().set(key, value, expire=TTL_SEARCH)


def set_dictionary(key: str, value: Any) -> None:
    get_cache().set(key, value, expire=TTL_DICTIONARY)
