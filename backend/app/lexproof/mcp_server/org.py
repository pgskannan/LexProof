"""Organization selection for MCP tool calls."""

from __future__ import annotations

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

import anyio

from ..services.organizations import get_organization_service


async def resolve_org_id(explicit: str | None, context: Context | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()

    headers = context.headers if context is not None else None
    header_org_id = headers.get("X-Org-Id") if headers else None
    if header_org_id and header_org_id.strip():
        return header_org_id.strip()

    token = get_access_token()
    claims = token.claims if token else None
    uid = (token.subject if token else None) or (claims or {}).get("uid")
    if uid:
        def list_memberships() -> list[dict[str, object]]:
            return get_organization_service().list_user_orgs(str(uid))

        memberships = await anyio.to_thread.run_sync(
            list_memberships,
        )
        active = [
            item for item in memberships
            if item.get("member_status") == "active" and item.get("status") == "active"
        ]
        if len(active) == 1:
            return str(active[0]["org_id"])

    raise ToolError("Pass org_id to select an organization you belong to.")