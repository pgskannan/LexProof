# Amazon Alexa+ MCP Staging

This prepares the dedicated `lexproof-api-amazon` Cloud Run service for the `feat/mcp-server-alexa` Vercel preview. Do not use the shared `lexproof-api`, PayPal, or Nebius services for this integration. The deployment script rejects an Amazon mode invocation unless `-Service lexproof-api-amazon` is explicit, rejects combining Amazon with the other modes, binds a separate HMAC secret, and enforces one minimum instance for in-memory short confirmation codes.

## Deploy

Run from the repository root. These are operator commands; the MCP implementation work does not run them.

```powershell
powershell -ExecutionPolicy Bypass -File backend\deploy\create-mcp-secrets.ps1
powershell -ExecutionPolicy Bypass -File backend\deploy\deploy-cloud-run.ps1 -Service lexproof-api-amazon -Amazon
```

The first deployment uses a temporary local MCP resource URL because Cloud Run has not assigned a URL yet. Once the service URL is available, the script creates a follow-up revision setting `LEXPROOF_MCP_PUBLIC_URL` to `<service-url>/mcp` and `LEXPROOF_MCP_ALLOWED_HOSTS` to the assigned `run.app` host. The LLM provider is not overridden; it remains the repository default. The generated 32-byte confirmation key is sent to Secret Manager over stdin, never printed, and is bound as `LEXPROOF_MCP_CONFIRM_SECRET`.

## Vercel Preview

In Vercel, set `NEXT_PUBLIC_API_URL` to the `lexproof-api-amazon` service URL for **Preview**, scoped to branch `feat/mcp-server-alexa`. Disable Vercel Deployment Protection for this preview so the Firebase-authenticated app can be opened directly. Do not set this environment variable for Production.

The deploy script allows the exact origin `https://lexproof-git-feat-mcp-server-alexa-pgskannans-projects.vercel.app` and `http://localhost:6274` for the MCP Inspector. The Inspector browser UI talks to its local proxy, which opens the MCP transport connection to LexProof; CORS is not normally involved in that proxy-to-server hop. The local origin is included in both CORS and MCP transport allowlists for direct browser-based Inspector connections and browser-based MCP clients.

## Smoke Checks

Use the URL printed by the deploy script:

```powershell
$serviceUrl = "<lexproof-api-amazon URL>"
Invoke-RestMethod "$serviceUrl/health"

$body = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke-check","version":"1.0"}}}'
try {
  Invoke-WebRequest -Uri "$serviceUrl/mcp" -Method Post -ContentType "application/json" -Headers @{ Accept = "application/json, text/event-stream" } -Body $body
} catch {
  $_.Exception.Response.StatusCode
  $_.Exception.Response.Headers["WWW-Authenticate"]
}
```

The unauthenticated initialize must return `401` with `WWW-Authenticate: Bearer`, not redirect. On the Vercel preview, sign in as `judge@lexproof.demo`, open **Connect an AI assistant**, and copy the current Firebase ID token. In Inspector choose Streamable HTTP, enter `<service-url>/mcp`, and add `Authorization: Bearer <token>`. Confirm initialize negotiates `2025-11-25`; call `list_contracts`, `upcoming_obligations`, `pending_approvals`, and `prepare_decision`. A judge's `confirm_decision` must return the read-only speech and make no state change.

Repeat on the preview with a non-judge account and a demo workflow item. Explicitly confirm the prepared action, then verify its workflow history or payment audit entry. The short six-character confirmation lookup is process-local; `--min-instances=1` keeps the voice demo on a warm instance, while the signed five-minute full confirmation token remains portable across Cloud Run instances.