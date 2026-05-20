"""Global async rate limiter dla orzeczenia.uzp.gov.pl.

Defaultowy limit: 1 request/sekunde. Hard cap: 2 req/s (Art. 2 Konstytucji).
Global lock - jeden licznik na caly serwer, nie per-tool.
"""

from __future__ import annotations

import asyncio
import os
import time


HARD_CAP_RPS = 2.0


class RateLimiter:
    """Token-bucket-like rate limiter (simple sliding minimum interval).

    Nie burst-friendly - kazde wywolanie czeka az `min_interval` minelo od ostatniego.
    To celowe: UZP to mniejsza infra, wolimy stale tempo niz burst.
    """

    def __init__(self, rps: float = 1.0):
        if rps <= 0:
            raise ValueError(f"rps must be > 0, got {rps}")
        if rps > HARD_CAP_RPS:
            raise ValueError(
                f"rps {rps} exceeds hard cap {HARD_CAP_RPS} (Art. 2 Konstytucji). "
                f"UZP to mniejsza infra, nie wolno bombic."
            )
        self.min_interval = 1.0 / rps
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Blokuje az minie `min_interval` od poprzedniego acquire."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            wait = self.min_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()


def from_env() -> RateLimiter:
    """Tworzy RateLimiter z env var KIO_MCP_RATE_LIMIT (default 1.0)."""
    rps_str = os.environ.get("KIO_MCP_RATE_LIMIT", "1.0")
    try:
        rps = float(rps_str)
    except ValueError as e:
        raise ValueError(f"KIO_MCP_RATE_LIMIT must be a float, got {rps_str!r}") from e
    return RateLimiter(rps=rps)
