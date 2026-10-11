# LexProof MCP Server

LexProof exposes a self-hosted MCP server at `/mcp` using the MCP Python SDK 2.x and Streamable HTTP. The server requests and negotiates protocol version `2025-11-25`, uses stateless JSON responses for Cloud Run, and currently exposes read-only contract tools.

## Architecture

MCP is a thin adapter over the existing FastAPI REST API. A tool forwards the authenticated caller's Firebase ID token and selected `X-Org-Id` through an in-process `httpx.AsyncClient` using `ASGITransport`; it does not reimplement business rules, RBAC, tenant visibility, read-only judge checks, rate limits, or audit behavior. A REST failure becomes a short MCP tool error without returning REST response bodies or stack traces.

The SDK's custom `TokenVerifier` calls the existing Firebase token verifier in a worker thread. The parent FastAPI lifespan enters the MCP session manager because the mounted Starlette app's lifespan is not automatically run by FastAPI. Both `/mcp` and `/mcp/` are routed without a redirect. DNS-rebinding protection is enabled for the MCP mount.

The repository's current passport API does not expose the prompt's suggested `GET /api/passports/{id}/proof` route. Proof verification instead calls the existing authorized `POST /api/passports/{id}/verify` endpoint, which recomputes passport integrity and returns a separate `anchor_status`; only `anchor_status == "PASS"` is reported as verified. It does not use the older evidence-proof verification API, which verifies a different object.

## Tools

| Tool | Inputs | Result |
| --- | --- | --- |
| `list_contracts` | Optional `org_id`, `limit` | Organization-scoped contract list, passport/status fields, and voice-ready `speech` |
| `ask_contracts` | `question`, optional `org_id` | REST-backed answer, grounded flag, cited finding IDs, and voice-ready `speech` |
| `verify_contract_proof` | `contract_id` or `contract_name`, optional `org_id` | Recomputed passport integrity and on-chain root status, transaction metadata when available, and voice-ready `speech` |

Every tool is annotated read-only and has a structured output schema with a `speech` field. Spoken responses are plain text, capped at two sentences, and do not include identifiers. The server instructions explicitly prohibit legal advice.

## Authentication And Configuration

Requests require `Authorization: Bearer <Firebase ID token>`. The MCP verifier validates that token, then each in-process REST call forwards it so the existing API dependencies perform authentication and authorization again. Pass `org_id` explicitly when the user belongs to zero or multiple active organizations; otherwise the adapter uses the incoming `X-Org-Id` header, then a sole active membership.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `LEXPROOF_MCP_ENABLED` | `true` | Disable the MCP mount entirely when false |
| `LEXPROOF_MCP_PUBLIC_URL` | `http://localhost:8000` | Public base URL used for protected-resource metadata; `/mcp` is appended |
| `LEXPROOF_MCP_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*,[::1]:*` | Comma-separated Host header allowlist; add the exact Cloud Run service host |
| `LEXPROOF_CORS_ORIGINS` | Existing frontend-origin defaults | MCP transport-security Origin allowlist |

The main app's existing CORS policy already permits request headers via its wildcard header setting, including `Mcp-Session-Id`, `Mcp-Protocol-Version`, `Authorization`, and `X-Org-Id`. `Mcp-Session-Id` is exposed only on `/mcp` responses.

## Local Inspector Check

Run these commands from the repository root in PowerShell. The backend must have its normal local Firebase/GCP configuration available for REST-backed tools.

1. Start the backend:

   ```powershell
   Push-Location backend
   .\.venv\Scripts\python.exe -m uvicorn app.lexproof.main:app --host 0.0.0.0 --port 8000
   ```

2. In another PowerShell terminal, set the Firebase Web API key and mint a short-lived ID token for a development user. The password is requested without echo; the script does not access service-account files or print service-account credentials.

   ```powershell
   $env:FIREBASE_WEB_API_KEY = "<Firebase Web API key>"
   Push-Location backend
   $token = .\.venv\Scripts\python.exe scripts\print_dev_id_token.py
   Pop-Location
   ```

   Treat `$token` as a credential. Do not paste it into source files, tickets, or logs.

3. Launch the Inspector:

   ```powershell
   npx @modelcontextprotocol/inspector
   ```

   Select **Streamable HTTP**, enter `http://localhost:8000/mcp`, and add the request header `Authorization: Bearer <token>`. If the user has more than one active organization, also add `X-Org-Id: <org-id>`.

4. Confirm that initialize reports protocol version `2025-11-25` and server name `LexProof`; `tools/list` should show exactly `list_contracts`, `ask_contracts`, and `verify_contract_proof`. Call each tool with an organization visible to the signed-in user. The proof result is only verified when the REST endpoint reports a matching passport root.

For a noninteractive protocol check without Firebase or LLM calls, run this from the repository root:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests\test_mcp_server.py -q
Pop-Location
```

## Alexa+ Integration Plan

The intended live integration is for Alexa+ to connect to this self-hosted endpoint as an MCP server, using the user's Firebase-backed authorization and organization context. The hackathon demo path is the simulated Alexa+ voice console planned separately; it will call the same MCP tools and use their `speech` fields. Real-device/account availability is dependent on Amazon's Alexa+ MCP integration access.