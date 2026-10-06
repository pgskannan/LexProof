"""PayPal startup probe.

Configured PayPal must be sandbox. When the process is not a pytest run, the
probe fetches one access token and logs whether the invoicing scope is present.
The token value is never logged.
"""

from __future__ import annotations

import os
import sys

from ...config import LexProofSettings, get_settings
from .auth import PayPalTokenProvider, log_invoicing_scope


def _network_probe_enabled(probe: bool | None) -> bool:
    if probe is not None:
        return probe
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if "pytest" in sys.modules:
        return False
    return True


_invoicing_scope: bool | None = None


def remember_invoicing_scope(present: bool) -> None:
    """Remember the last startup probe. /health reads this and does not call PayPal."""
    global _invoicing_scope
    _invoicing_scope = present


def paypal_health(settings: LexProofSettings) -> dict[str, object]:
    """Sandbox env and whether the last probe saw the invoicing scope. No secrets."""
    configured = settings.has_paypal_configuration()
    return {
        "env": (settings.paypal_env or "sandbox").strip().lower(),
        "invoicing_scope": _invoicing_scope if configured else False,
    }


async def run_paypal_startup(
    settings: LexProofSettings | None = None,
    *,
    probe: bool | None = None,
) -> None:
    """Reject live PayPal, then log the invoicing scope when a probe is allowed."""
    settings = settings or get_settings()
    if not settings.has_paypal_configuration():
        return
    if settings.paypal_env.strip().lower() != "sandbox":
        raise RuntimeError("PayPal integration is sandbox-only; paypal_env must be 'sandbox'")
    if not _network_probe_enabled(probe):
        return
    provider = PayPalTokenProvider(
        settings.paypal_client_id,
        settings.paypal_client_secret.get_secret_value(),
    )
    try:
        await provider.get_access_token()
        remember_invoicing_scope(log_invoicing_scope(provider.scopes))
    finally:
        await provider.aclose()
