# Cloud Run Backend Readiness

**Date:** 2026-08-23  
**Decision:** BLOCKED for deployment

## What Was Verified

- FastAPI imports successfully after repairing invalid relative imports and missing typing symbols.
- Local startup works with:

```powershell
C:\Projects\LexProof\backend\.venv\Scripts\python.exe -m uvicorn app.lexproof.main:app --app-dir C:\Projects\LexProof\backend --host 127.0.0.1 --port 8000
```

- `GET http://127.0.0.1:8000/health` returned:

```json
{"status":"ok","service":"lexproof"}
```

## Cloud Run Requirements

| Concern | Current status | Required action |
|---|---|---|
| PORT behavior | Partial | Uvicorn currently defaults to 8000; production command must use `$PORT` |
| Startup command | Partial | Use `uvicorn app.lexproof.main:app --host 0.0.0.0 --port $PORT` from backend root |
| Dockerfile | Blocked | No Dockerfile exists under `C:\Projects\LexProof\backend` |
| Dependencies | Partial | `uvicorn[standard]` was added; build image still needs to be created and tested |
| Secrets | Partial | Use Secret Manager/runtime env for Firebase private key, blockchain key, and RPC credentials |
| Persistent filesystem | Blocked | Passport, evidence, compliance, remediation, and transaction state are process-local |
| Database | Blocked | No SQL driver, database URL, migrations, or durable LexProof repository is configured |
| Background jobs | Blocked | Cloud Scheduler/Tasks are placeholders; no worker/retry model exists |
| CORS | Blocked | No explicit allowed frontend origin is configured |
| Authentication | Blocked | Firebase token verification helper exists but is not a FastAPI dependency |
| Health checks | Partial | `/health` checks process liveness only; dependency readiness endpoints report configuration, not connectivity |
| Multi-worker behavior | Blocked | In-memory stores diverge across instances and are lost on restart |
| Logging | Partial | Logging adapter exists but request correlation/error middleware is not wired |
| Blockchain | Blocked | Requires deployed registry address, Sepolia RPC, funded signer, and durable status handling |

## Environment Variables

Current `.env.example` defines:

- `FIREBASE_PROJECT_ID`
- `FIREBASE_CLIENT_EMAIL`
- `FIREBASE_PRIVATE_KEY`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`
- `GEMINI_MODEL`
- `GEMINI_TEMPERATURE`
- `GEMINI_MAX_OUTPUT_TOKENS`
- `BLOCKCHAIN_RPC_URL`
- `CONTRACT_ADDRESS`
- `BLOCKCHAIN_PRIVATE_KEY`
- `BLOCKCHAIN_PERSISTENCE`
- `FIREBASE_STORAGE_BUCKET`
- `INTEGRATION_TESTS`

Secrets must be supplied through Cloud Run secret references or runtime environment configuration. Do not place private keys in the image, repository, frontend environment, or logs.

## Persistent Storage Assumptions

The backend currently stores core state in module-level dictionaries and optionally stores blockchain transaction records in Firestore when `BLOCKCHAIN_PERSISTENCE=firestore`. Cloud Run instances are ephemeral and horizontally scaled, so this is not sufficient for production or a reliable multi-step demo. Contract files should use Cloud Storage; contract metadata, passport records, evidence, approvals, and audit records need a durable tenant-scoped repository. Existing ContractRiskEdge relational storage should remain the system of record for its mature analysis data.

## Required Pre-Deployment Work

1. Add and test a LexProof Dockerfile with a non-root runtime user and `$PORT` startup behavior.
2. Wire Firebase ID-token verification and tenant/RBAC dependencies to every protected mutation/read route.
3. Add explicit CORS configuration for the deployed Next.js origin.
4. Persist passport, evidence, compliance, remediation, and audit state durably.
5. Implement Cloud Storage document object paths and Firestore/relational metadata ownership rules.
6. Replace scheduler/task placeholders with authenticated Cloud Scheduler and Cloud Tasks handlers, retries, and idempotency keys.
7. Add readiness checks that avoid leaking credentials or raw provider errors.
8. Configure real Sepolia values only in Secret Manager and validate on a non-production test project.
9. Run the full test suite and a container smoke test before deployment.

## Final Status

**BLOCKED.** The application can run locally with the isolated Python environment and passes the liveness check, but it is not Cloud Run ready because the container artifact, durable persistence, auth enforcement, CORS, background processing, and production configuration are incomplete. No deployment was performed.
