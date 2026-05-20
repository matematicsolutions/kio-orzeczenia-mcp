"""Audit log JSONL dla rozliczalnosci operatora konektora.

Lokalizacja: ~/.matematic/audit/kio-orzeczenia-mcp.jsonl (overridable via KIO_MCP_AUDIT_DIR).

Co logujemy: ts, tool, params_hash, result_summary, source_urls, latency_ms, cache_hit.
Czego NIE logujemy: pelny tekst orzeczen (content_text, reasoning).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _audit_dir() -> Path:
    override = os.environ.get("KIO_MCP_AUDIT_DIR")
    if override:
        return Path(override)
    return Path.home() / ".matematic" / "audit"


def _audit_file() -> Path:
    return _audit_dir() / "kio-orzeczenia-mcp.jsonl"


def params_hash(params: Any) -> str:
    """SHA-256 z params (deterministyczny dump JSON)."""
    try:
        s = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(params)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def log_event(
    tool: str,
    params: Any,
    result_summary: dict[str, Any],
    source_urls: list[str],
    latency_ms: float,
    cache_hit: bool = False,
    error: str | None = None,
) -> None:
    """Zapisz wpis do audit log JSONL. Best-effort - bledy nie blokuja flow."""
    try:
        d = _audit_dir()
        d.mkdir(parents=True, exist_ok=True)

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "params_hash": params_hash(params),
            "result_summary": result_summary,
            "source_urls": source_urls,
            "latency_ms": round(latency_ms, 2),
            "cache_hit": cache_hit,
        }
        if error is not None:
            entry["error"] = error

        with _audit_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Audit log to best-effort - nie blokujemy uzytkownika jezeli sie nie da pisac.
        # W produkcji warto by tu wpiac structlog/sentry.
        pass
