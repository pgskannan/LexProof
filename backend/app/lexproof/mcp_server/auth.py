"""Firebase ID-token verification for MCP's bearer-auth middleware."""

from __future__ import annotations

from typing import Any

import anyio
from mcp.server.auth.provider import AccessToken, TokenVerifier

from ..services import firebase_auth


class FirebaseTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims: dict[str, Any] = await anyio.to_thread.run_sync(
                firebase_auth.verify_firebase_token,
                token,
            )
        except firebase_auth.FirebaseAuthenticationError:
            return None

        uid = claims.get("uid")
        if not uid:
            return None
        return AccessToken(
            token=token,
            client_id="lexproof-mcp",
            scopes=["lexproof:read"],
            expires_at=claims.get("exp"),
            subject=str(uid),
            claims=claims,
        )