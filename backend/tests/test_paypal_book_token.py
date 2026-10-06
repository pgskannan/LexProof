"""Regression: PaymentBook must pass the token string through unchanged.

PayPalTokenProvider.get_access_token() returns a str. A staging run on
2026-10-06 failed with "'str' object has no attribute 'access_token'" because
PaymentBook._access_token treated it as an object; no test drove that path.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.lexproof.services.paypal.book import PaymentBook


class _FakeProvider:
    async def get_access_token(self) -> str:
        return "sandbox-token"


def test_access_token_returns_provider_string():
    settings = SimpleNamespace(has_paypal_configuration=lambda: True)
    book = PaymentBook(
        obligations=MagicMock(),
        actions=MagicMock(),
        invoices=[],
        receipts=[],
        settings=settings,
        token_provider=_FakeProvider(),
    )
    assert asyncio.run(book._access_token()) == "sandbox-token"


def test_adk_uses_vertex_ai_by_default(monkeypatch):
    from app.lexproof.services.paypal.agent import use_vertex_ai

    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    use_vertex_ai()
    import os

    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "TRUE"
