"""Per-user hourly cap for the payment agent.

Judging can otherwise burn Vertex and PayPal sandbox quotas. The cap is
in-memory on this Cloud Run instance. A second instance has its own counter.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from collections.abc import Callable

from .obligations import PaymentError

DEFAULT_LIMIT = 10
WINDOW_SECONDS = 3600


class AgentRateLimiter:
    def __init__(self, *, limit: int | None = None, clock: Callable[[], float] | None = None) -> None:
        configured = os.getenv("LEXPROOF_AGENT_TURNS_PER_HOUR", str(DEFAULT_LIMIT))
        self.limit = limit if limit is not None else int(configured)
        self.clock = clock or time.time
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, uid: str) -> None:
        now = self.clock()
        window = [stamp for stamp in self._hits[uid] if now - stamp < WINDOW_SECONDS]
        if len(window) >= self.limit:
            self._hits[uid] = window
            raise PaymentError(
                429,
                f"The payment agent is limited to {self.limit} turns per hour for this account. Try again later.",
            )
        window.append(now)
        self._hits[uid] = window


_limiter = AgentRateLimiter()


def check_agent_rate(uid: str) -> None:
    _limiter.check(uid)
