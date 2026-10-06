"""The payment agent is capped per user so judging cannot exhaust quotas."""

from app.lexproof.services.paypal.obligations import PaymentError
from app.lexproof.services.paypal.rate_limit import AgentRateLimiter


def test_agent_turns_are_capped_per_user_per_hour():
    now = {"value": 1_000.0}
    limiter = AgentRateLimiter(limit=2, clock=lambda: now["value"])
    limiter.check("judge")
    limiter.check("judge")
    try:
        limiter.check("judge")
    except PaymentError as exc:
        assert exc.status_code == 429
        assert "2 turns per hour" in exc.detail
    else:
        raise AssertionError("expected a rate limit")
    limiter.check("other-user")
    now["value"] += 3600
    limiter.check("judge")
