"""Per-user hourly cap for the payment agent.

Judging can otherwise burn Vertex and PayPal sandbox quotas. The cap is
in-memory on this Cloud Run instance. A second instance has its own counter.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import HTTPException

from .obligations import PaymentError

DEFAULT_LIMIT = 10
WINDOW_SECONDS = 3600
JUDGE_DEMO_LIMIT_DETAIL = "Judge demo limit reached — try again later."


class AgentRateLimiter:
    def __init__(
        self,
        *,
        limit: int | None = None,
        window_seconds: int = WINDOW_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        configured = os.getenv("LEXPROOF_AGENT_TURNS_PER_HOUR", str(DEFAULT_LIMIT)) if limit is None else None
        self.limit = limit if limit is not None else int(configured)
        self.window_seconds = window_seconds
        self.clock = clock or time.time
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, uid: str) -> None:
        now = self.clock()
        window = [stamp for stamp in self._hits[uid] if now - stamp < self.window_seconds]
        if len(window) >= self.limit:
            self._hits[uid] = window
            raise PaymentError(
                429,
                f"The payment agent is limited to {self.limit} turns per hour for this account. Try again later.",
            )
        window.append(now)
        self._hits[uid] = window


_limiter = AgentRateLimiter()
_judge_analysis_limiter = AgentRateLimiter(limit=10, window_seconds=24 * 60 * 60)
_judge_interaction_limiter = AgentRateLimiter(limit=30, window_seconds=WINDOW_SECONDS)


def check_agent_rate(uid: str) -> None:
    _limiter.check(uid)


def _check_judge_limit(limiter: AgentRateLimiter, uid: str) -> None:
    try:
        limiter.check(uid)
    except PaymentError as exc:
        raise HTTPException(status_code=429, detail=JUDGE_DEMO_LIMIT_DETAIL) from exc


def check_judge_analysis_rate(uid: str) -> None:
    _check_judge_limit(_judge_analysis_limiter, uid)


def check_judge_interaction_rate(uid: str) -> None:
    _check_judge_limit(_judge_interaction_limiter, uid)
