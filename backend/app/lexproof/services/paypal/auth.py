"""Sandbox PayPal OAuth2 client-credentials tokens.

PayPal returns the same cached access token for up to nine hours. A feature
enabled after that token was issued, including the invoicing scope, stays
missing until the token is terminated and a new one is requested.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("lexproof.paypal.auth")

SANDBOX_API_HOST = "api-m.sandbox.paypal.com"
TOKEN_URL = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
TERMINATE_URL = "https://api-m.sandbox.paypal.com/v1/oauth2/token/terminate"
REFRESH_SKEW_SECONDS = 10 * 60


class PayPalAuthError(RuntimeError):
    """PayPal rejected a sandbox auth call. Messages never include secrets or tokens."""


@dataclass(frozen=True)
class PayPalAccessToken:
    access_token: str
    expires_at: float
    scopes: tuple[str, ...]
    token_type: str = "Bearer"


def scopes_include_invoicing(scopes: tuple[str, ...] | list[str]) -> bool:
    return any("invoicing" in scope for scope in scopes)


def log_invoicing_scope(scopes: tuple[str, ...] | list[str]) -> bool:
    """Log whether the invoicing scope is present. The token itself is not logged."""
    present = scopes_include_invoicing(scopes)
    logger.info("PayPal invoicing scope present: %s", present)
    return present


class PayPalTokenProvider:
    """Client-credentials tokens for the PayPal sandbox, with a single 403 retry."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("PayPal client credentials are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = client
        self._owns_client = client is None
        self._lock = asyncio.Lock()
        self._cached: PayPalAccessToken | None = None
        self._scopes: tuple[str, ...] = ()
        self._clock = clock

    @property
    def scopes(self) -> tuple[str, ...]:
        return self._scopes

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
            self._owns_client = True
        return self._client

    def _needs_refresh(self, token: PayPalAccessToken) -> bool:
        return self._clock() >= token.expires_at - REFRESH_SKEW_SECONDS

    async def get_access_token(self) -> str:
        async with self._lock:
            if self._cached is not None and not self._needs_refresh(self._cached):
                return self._cached.access_token
            minted = await self._request_token()
            self._store(minted)
            return minted.access_token

    async def force_refresh(self) -> str:
        """Terminate the cached access token, then request a new one.

        Call this when a PayPal response is 403 ``NOT_AUTHORIZED`` after a
        scope was enabled: the previous token is cached by PayPal and will
        not pick up the new scope on its own.
        """
        async with self._lock:
            current = self._cached.access_token if self._cached is not None else None
            if current:
                await self._terminate(current)
            self._cached = None
            self._scopes = ()
            minted = await self._request_token()
            self._store(minted)
            return minted.access_token

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send one sandbox API call.

        A 403 ``NOT_AUTHORIZED`` terminates the current token and retries the
        call once. A second 403 is returned to the caller.
        """
        _assert_sandbox_api_url(url)
        token = await self.get_access_token()
        response = await self._send(method, url, token, **kwargs)
        if _is_not_authorized(response):
            token = await self.force_refresh()
            response = await self._send(method, url, token, **kwargs)
        return response

    def _store(self, minted: PayPalAccessToken) -> None:
        self._cached = minted
        self._scopes = minted.scopes
        logger.info(
            "PayPal access token acquired; expires_in_seconds=%s invoicing_scope=%s",
            max(0, int(minted.expires_at - self._clock())),
            scopes_include_invoicing(minted.scopes),
        )

    async def _request_token(self) -> PayPalAccessToken:
        response = await self._http().post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
        if response.status_code != 200:
            raise PayPalAuthError(f"PayPal token request failed with status {response.status_code}")
        try:
            payload = response.json()
        except Exception as exc:
            raise PayPalAuthError("PayPal token response was not JSON") from exc
        if not isinstance(payload, dict):
            raise PayPalAuthError("PayPal token response was not an object")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise PayPalAuthError("PayPal token response did not include an access token")
        try:
            expires_in_seconds = int(payload.get("expires_in", 0))
        except (TypeError, ValueError) as exc:
            raise PayPalAuthError("PayPal token response did not include expires_in") from exc
        scope_text = payload.get("scope") or ""
        scopes = tuple(part for part in str(scope_text).split() if part)
        return PayPalAccessToken(
            access_token=access_token,
            expires_at=self._clock() + expires_in_seconds,
            scopes=scopes,
            token_type=str(payload.get("token_type") or "Bearer"),
        )

    async def _terminate(self, access_token: str) -> None:
        response = await self._http().post(
            TERMINATE_URL,
            data={"token": access_token, "token_type_hint": "ACCESS_TOKEN"},
            auth=(self._client_id, self._client_secret),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
        if response.status_code not in (200, 204):
            raise PayPalAuthError(f"PayPal token terminate failed with status {response.status_code}")

    async def _send(self, method: str, url: str, token: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Accept", "application/json")
        return await self._http().request(method, url, headers=headers, **kwargs)


def _assert_sandbox_api_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != SANDBOX_API_HOST:
        raise PayPalAuthError("PayPal API calls are restricted to https://api-m.sandbox.paypal.com")


def _is_not_authorized(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        body = response.json()
    except Exception:
        return "NOT_AUTHORIZED" in (response.text or "")
    if not isinstance(body, dict):
        return False
    if body.get("name") == "NOT_AUTHORIZED" or body.get("error") == "NOT_AUTHORIZED":
        return True
    details = body.get("details")
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict) and item.get("issue") == "NOT_AUTHORIZED":
                return True
            if isinstance(item, dict) and item.get("name") == "NOT_AUTHORIZED":
                return True
    return False
