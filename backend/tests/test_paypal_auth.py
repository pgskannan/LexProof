"""PayPal sandbox token provider tests. Tokens and secrets stay out of logs."""

import asyncio
import logging

import httpx
import pytest

from app.lexproof.services.paypal.auth import (
    TOKEN_URL,
    PayPalAuthError,
    PayPalTokenProvider,
    log_invoicing_scope,
)


SECRET = "client-secret-value"
TOKEN = "sandbox-token-1"


def _token_payload(token: str = TOKEN, *, expires_in: int = 32400, scope: str = "https://uri.paypal.com/services/invoicing openid"):
    return {
        "access_token": token,
        "expires_in": expires_in,
        "scope": scope,
        "token_type": "Bearer",
    }


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_token_is_cached_until_within_ten_minutes_of_expiry(caplog):
    caplog.set_level(logging.DEBUG)
    calls = {"token": 0}
    now = {"t": 1_000.0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api-m.sandbox.paypal.com"
        assert str(request.url).startswith(TOKEN_URL)
        calls["token"] += 1
        return httpx.Response(200, json=_token_payload(f"tok-{calls['token']}"))

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler), clock=lambda: now["t"])
    first = await provider.get_access_token()
    second = await provider.get_access_token()
    assert first == second == "tok-1"
    assert calls["token"] == 1
    assert provider.scopes == ("https://uri.paypal.com/services/invoicing", "openid")

    now["t"] = 1_000.0 + 32400 - 601
    assert await provider.get_access_token() == "tok-1"
    assert calls["token"] == 1

    now["t"] = 1_000.0 + 32400 - 600
    assert await provider.get_access_token() == "tok-2"
    assert calls["token"] == 2
    assert SECRET not in caplog.text
    assert "tok-1" not in caplog.text
    assert "tok-2" not in caplog.text
    await provider.aclose()


@pytest.mark.asyncio
async def test_force_refresh_terminates_then_requests_a_new_token():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.read().decode()))
        if request.url.path.endswith("/token/terminate"):
            body = seen[-1][1]
            assert "token_type_hint=ACCESS_TOKEN" in body
            assert "token=tok-1" in body
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={})
        return httpx.Response(200, json=_token_payload(f"tok-{len(seen)}"))

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    assert await provider.get_access_token() == "tok-1"
    assert await provider.force_refresh() == "tok-3"
    assert [path for path, _ in seen] == [
        "/v1/oauth2/token",
        "/v1/oauth2/token/terminate",
        "/v1/oauth2/token",
    ]
    await provider.aclose()


@pytest.mark.asyncio
async def test_force_refresh_without_a_cached_token_skips_terminate():
    calls = {"token": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.path.endswith("/terminate")
        calls["token"] += 1
        return httpx.Response(200, json=_token_payload("fresh"))

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    assert await provider.force_refresh() == "fresh"
    assert calls["token"] == 1


@pytest.mark.asyncio
async def test_not_authorized_refreshes_once_and_retries_once():
    state = {"tokens": 0, "invoices": 0, "terminates": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/terminate"):
            state["terminates"] += 1
            return httpx.Response(204)
        if request.url.path.endswith("/v1/oauth2/token"):
            state["tokens"] += 1
            return httpx.Response(200, json=_token_payload(f"tok-{state['tokens']}"))
        state["invoices"] += 1
        if state["invoices"] == 1:
            assert request.headers["authorization"] == "Bearer tok-1"
            return httpx.Response(403, json={"name": "NOT_AUTHORIZED", "message": "scope missing"})
        assert request.headers["authorization"] == "Bearer tok-2"
        return httpx.Response(200, json={"items": [], "total_items": None})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    response = await provider.request("GET", "https://api-m.sandbox.paypal.com/v2/invoicing/invoices")
    assert response.status_code == 200
    assert state == {"tokens": 2, "invoices": 2, "terminates": 1}
    await provider.aclose()


@pytest.mark.asyncio
async def test_second_not_authorized_is_not_retried_again():
    state = {"tokens": 0, "invoices": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/terminate"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/v1/oauth2/token"):
            state["tokens"] += 1
            return httpx.Response(200, json=_token_payload(f"tok-{state['tokens']}", scope="openid"))
        state["invoices"] += 1
        return httpx.Response(403, json={"details": [{"issue": "NOT_AUTHORIZED"}]})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    response = await provider.request("GET", "https://api-m.sandbox.paypal.com/v2/invoicing/invoices")
    assert response.status_code == 403
    assert state["invoices"] == 2
    assert state["tokens"] == 2
    assert provider.scopes == ("openid",)
    await provider.aclose()


@pytest.mark.asyncio
async def test_not_authorized_text_and_error_field():
    mode = {"kind": "text"}

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2/token" in request.url.path:
            return httpx.Response(200, json=_token_payload("tok"))
        if mode["kind"] == "text":
            return httpx.Response(403, text="NOT_AUTHORIZED")
        if mode["kind"] == "error":
            return httpx.Response(403, json={"error": "NOT_AUTHORIZED"})
        if mode["kind"] == "name":
            return httpx.Response(403, json={"details": [{"name": "NOT_AUTHORIZED"}]})
        if mode["kind"] == "list":
            return httpx.Response(403, json=["NOT_AUTHORIZED"])
        return httpx.Response(403, json={"name": "PERMISSION_DENIED"})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    for kind in ("text", "error", "name", "list", "other"):
        mode["kind"] = kind
        response = await provider.request("GET", "https://api-m.sandbox.paypal.com/v1/catalogs/products")
        assert response.status_code == 403
    other = await provider.request("GET", "https://api-m.sandbox.paypal.com/v1/catalogs/products", headers={"X-Test": "1"})
    assert other.status_code == 403


@pytest.mark.asyncio
async def test_non_403_does_not_refresh_and_live_hosts_are_rejected():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "oauth2/token" in request.url.path:
            return httpx.Response(200, json=_token_payload("tok"))
        return httpx.Response(401, json={"name": "NOT_AUTHORIZED"})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    response = await provider.request("GET", "https://api-m.sandbox.paypal.com/v2/invoicing/invoices")
    assert response.status_code == 401
    assert calls["n"] == 2
    with pytest.raises(PayPalAuthError):
        await provider.request("GET", "https://api-m.paypal.com/v2/invoicing/invoices")
    with pytest.raises(PayPalAuthError):
        await provider.request("GET", "http://api-m.sandbox.paypal.com/v2/invoicing/invoices")
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_token_errors_omit_secrets():
    def forbidden(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(forbidden))
    with pytest.raises(PayPalAuthError, match="status 401") as exc:
        await provider.get_access_token()
    assert SECRET not in str(exc.value)

    def not_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="nope")

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(not_json))
    with pytest.raises(PayPalAuthError, match="not JSON"):
        await provider.get_access_token()

    def not_object(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["nope"])

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(not_object))
    with pytest.raises(PayPalAuthError, match="not an object"):
        await provider.get_access_token()

    def missing_token(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expires_in": 10, "scope": ""})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(missing_token))
    with pytest.raises(PayPalAuthError, match="access token"):
        await provider.get_access_token()

    def bad_expiry(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "tok", "expires_in": "soon"})

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(bad_expiry))
    with pytest.raises(PayPalAuthError, match="expires_in"):
        await provider.get_access_token()


@pytest.mark.asyncio
async def test_terminate_failure_keeps_the_cached_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/terminate"):
            return httpx.Response(500, text="no")
        return httpx.Response(200, json=_token_payload("kept"))

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    assert await provider.get_access_token() == "kept"
    with pytest.raises(PayPalAuthError, match="terminate failed"):
        await provider.force_refresh()
    assert await provider.get_access_token() == "kept"


def test_invoicing_scope_log_does_not_include_a_token(caplog):
    caplog.set_level(logging.INFO)
    assert log_invoicing_scope(["openid", "https://uri.paypal.com/services/invoicing"]) is True
    assert log_invoicing_scope(["openid"]) is False
    assert "sandbox-token" not in caplog.text
    assert "PayPal invoicing scope present: True" in caplog.text
    assert "PayPal invoicing scope present: False" in caplog.text


def test_credentials_are_required():
    with pytest.raises(ValueError):
        PayPalTokenProvider("", SECRET)


@pytest.mark.asyncio
async def test_concurrent_reads_share_one_token_request():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_token_payload("shared"))

    provider = PayPalTokenProvider("client-id", SECRET, client=_client(handler))
    first, second = await asyncio.gather(provider.get_access_token(), provider.get_access_token())
    assert first == second == "shared"
    assert calls["n"] == 1
