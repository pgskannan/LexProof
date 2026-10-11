"""In-process HTTP client for delegating MCP tools to FastAPI routes."""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError

_app: Any = None


def set_app(app: Any) -> None:
    global _app
    _app = app


async def call_api(
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
    org_id: str | None = None,
) -> Any:
    token = get_access_token()
    if token is None:
        raise ToolError("Authentication context is unavailable. Sign in again.")
    if _app is None:
        raise ToolError("LexProof API is not ready.")

    headers = {"Authorization": f"Bearer {token.token}"}
    if org_id:
        headers["X-Org-Id"] = org_id

    transport = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://lexproof.internal",
        timeout=180.0,
    ) as client:
        response = await client.request(method, path, headers=headers, json=json, params=params)

    if response.is_success:
        return response.json() if response.content else None

    messages = {
        401: "Authentication failed. Sign in again.",
        403: "You do not have access to this organization or resource.",
        404: "The requested contract or proof was not found.",
        429: "LexProof is receiving too many requests. Try again shortly.",
    }
    raise ToolError(messages.get(response.status_code, "LexProof could not complete the request."))