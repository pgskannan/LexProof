# Google Cloud and Firebase Setup

## Scope

Sprint 1 adds server-side adapters under `backend/app/lexproof`. Existing ContractRiskEdge services remain the source of truth for contract ingestion, review, policy, risk, and LLM workflows.

## Environment

Copy `backend/.env.example` to the server environment only. Do not add Firebase private keys, blockchain private keys, or service-account JSON to the frontend, source control, browser bundles, or client-visible API responses.

Required foundation variables:

- `FIREBASE_PROJECT_ID`
- `FIREBASE_CLIENT_EMAIL`
- `FIREBASE_PRIVATE_KEY` (use escaped `\\n` line breaks)
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`
- `GEMINI_MODEL`
- `BLOCKCHAIN_RPC_URL`
- `BLOCKCHAIN_PRIVATE_KEY`

`GOOGLE_CLOUD_PROJECT` is preferred when both project IDs are supplied.

## Services

- `config/settings.py`: typed environment abstraction with `SecretStr` for private values.
- `services/firebase.py`: lazy, process-wide Firebase Admin initialization.
- `services/firebase_auth.py`: server-side Firebase ID-token verification.
- `repositories/firestore.py`: Firestore CRUD abstraction.
- `repositories/cloud_storage.py`: Cloud Storage upload/download/delete abstraction.
- `repositories/secret_manager.py`: Secret Manager access abstraction.
- `services/gcp_logging.py`: Google Cloud logging with standard logging fallback.
- `services/vertex_ai.py`: Vertex AI/Gemini adapter implementing ContractRiskEdge's `complete(request)` and `LLMResponse` contract when the existing app is on `PYTHONPATH`.

## Health endpoints

Include `app.lexproof.services.health.router` in the existing FastAPI app. The endpoints return status metadata only:

- `GET /health`
- `GET /health/firebase`
- `GET /health/gcp`
- `GET /health/ai`

A `not_configured` response is expected in local development without cloud credentials.

## IAM baseline

Use a dedicated runtime service account with only the permissions required by the deployment:

- Firebase Admin identity-token verification
- Firestore read/write for approved collections
- Storage object read/write for the contract bucket
- Secret Manager accessor for named secrets
- Vertex AI user for model invocation
- Logs writer for application logs

Store production secrets in Secret Manager and inject them at deployment time. Do not persist private keys in Firestore.

## Tests

Run offline unit tests with:

```text
cd backend
pytest -m "not integration"
```

Cloud-dependent tests should be marked `@pytest.mark.integration` and run only when `INTEGRATION_TESTS=true` with Application Default Credentials configured.
