# LexProof — Architecture

*Last updated 2026-09-04.*

## 1. What LexProof does

LexProof takes an uploaded contract, runs AI analysis to find risky clauses, lets a reviewer author and publish AI-assisted redlines, and produces a "Legal Passport" — a cryptographically verifiable record of the contract's content, the policy it was checked against, the analysis that was run, and the evidence behind each finding. Each Legal Passport's evidence items are individually anchored on Ethereum (Sepolia testnet for the hackathon build) so anyone — not just LexProof's own backend — can independently verify that a piece of evidence hasn't been altered since it was reviewed.

## 2. System components

```
┌────────────┐      HTTPS/JSON       ┌─────────────┐      Firestore SDK      ┌────────────┐
│  Frontend    │ ──────────────────▶ │   Backend     │ ───────────────────▶  │  Firestore  │
│  (Next.js)   │ ◀────────────────── │   (FastAPI)   │ ◀───────────────────  │             │
└─────────────┘   Bearer <Firebase   └──────────────┘                        └────────────┘
       │             ID token>              │
       │                                    │ web3.py (JSON-RPC)
       │ Firebase Auth SDK                  ▼
       ▼                              ┌──────────────┐
┌─────────────┐                       │  Ethereum     │
│  Firebase    │                       │  Sepolia      │
│  Auth        │                       │  (LexProofRegistry.sol) │
└─────────────┘                       └──────────────┘
       │                                    ▲
       ▼                                    │ browser reads the
┌─────────────┐   ethers.js, direct RPC     │ contract directly too
│  Browser     │ ───────────────────────────┘
│  (/public-verify) 
└─────────────┘
```

- **Frontend** — Next.js 14 (App Router), React 18, TypeScript. Talks to the backend over `NEXT_PUBLIC_API_URL`, authenticating every call with a Firebase ID token (`frontend/lib/api.ts`'s `apiFetch`). Uses `ethers.js` directly in the browser for the public verification page's independent on-chain check.
- **Backend** — FastAPI (Python), organized as route modules under `backend/app/lexproof/api/` (contracts, findings, redline_proposals, evidence_anchor, blockchain, time_machine, compliance, remediation, auth) backed by domain services under `backend/app/lexproof/domains/` and `backend/app/lexproof/services/`. Every route (except the public `/api/verify/{id}`) requires a Firebase ID token, verified per-request (`services/auth.py` → `services/firebase_auth.py`).
- **Data store** — Google Cloud Firestore, accessed through a thin repository layer (`app/lexproof/repositories/firestore.py`). Collections: `contracts`, `contract_versions`, `legal_passports`, `risk_findings`, `evidence_records`, `evidence_anchors`, `redline_proposals`, `redline_reviews`, `redline_publication_audits`, `blockchain_proofs`.
- **File storage** — Google Cloud Storage, for the original uploaded contract documents (`repositories/cloud_storage.py`).
- **AI analysis** — Vertex AI (Gemini) via `services/vertex_ai.py`, invoked from the version-analysis pipeline to extract findings, risk/compliance scores, and evidence.
- **Blockchain layer** — `services/blockchain.py` (web3.py, JSON-RPC over an Alchemy Sepolia endpoint) and `services/ethereum_anchor_service.py` on top of it. All synchronous web3.py calls reachable from an `async def` FastAPI route are wrapped in `asyncio.to_thread(...)` so a slow or congested RPC call never blocks the event loop for unrelated requests.
- **Smart contract** — `contracts/LexProofRegistry.sol` (Solidity, deployed to Ethereum Sepolia). Two independent anchoring primitives:
  - `anchorEvidence(recordId, evidenceHash)` / `verifyEvidence(...)` / `getEvidenceAnchor(...)` — per-evidence-item anchoring. This is the path the whole app actually uses end-to-end today.
  - `registerProof(...)` / `verifyProof(...)` — a separate, passport-level (whole-Legal-Passport) proof primitive. Built into the contract but never wired to any UI action, and the backend's configured wallet is not an authorized registrar for it on the currently-deployed contract instance — see `LIMITATIONS.md`.
  - Both anchoring functions are gated by an `onlyRegistrar` modifier; `setRegistrar`/ownership are `onlyOwner`.

## 3. Data flow: upload → analysis → passport → anchor → verify

1. **Upload** (`POST /api/contracts`) — the file is stored in Cloud Storage, a `contracts` doc and a version-1 `contract_versions` doc are created with `analysis_status: "pending"`.
2. **Analysis** — the version-analysis pipeline (`services/version_analysis.py`) calls Vertex AI, extracts findings (`risk_findings` collection) and builds evidence items (`evidence_records` collection), computes risk/compliance scores, and creates a `legal_passports` document with document/policy/analysis/evidence hashes and a composite passport hash.
3. **Redline authoring** — a reviewer opens a finding and proposes replacement clause language (`redline_proposals`), which goes through a review step (`redline_reviews`: approve/reject) and, once approved, a publish step (`POST /api/redline-proposals/{id}/publish`) that creates a new contract version (V2, V3, …) carrying the edited clause, and records a `redline_publication_audits` entry.
4. **Evidence anchoring** — each evidence item's content hash is anchored on-chain via `anchorEvidence`. This can happen synchronously as part of publish, or be retried independently later (`POST /api/evidence/{id}/anchor`) if the on-chain transaction was slow/congested at publish time — publish itself always reports success once the Firestore writes are committed, with anchoring status shown and retriable separately (this decoupling was a deliberate fix; see `LIMITATIONS.md`/project history for why).
5. **Verification** — `GET /api/verify/{evidence_id}` (no auth required) recomputes the evidence's hash from current Firestore content and compares it to what's on-chain, returning one of `VERIFIED`, `TAMPERED`, `EVIDENCE_NOT_FOUND`, or `ANCHOR_NOT_FOUND`. The `/public-verify` frontend page additionally reads the same on-chain data **directly from the browser** via `ethers.js` against a public Sepolia RPC endpoint — bypassing the LexProof backend entirely — so a viewer doesn't have to trust the backend's word for what's actually on-chain.

## 4. Frontend structure

- `frontend/app/(authenticated)/…` — everything behind Firebase auth: contract list/lifecycle, findings & redlines, contract reviews (approve/publish), Legal Passport, Contract Time Machine, Reports, Compliance, the internal Evidence Verification page, Administration.
- `frontend/app/public-verify/` — the one public, unauthenticated page. Reads `?evidence_id=` from the URL, auto-verifies on load.
- `frontend/app/login/` — Firebase Auth sign-in.
- `frontend/lib/` — shared client code: `api.ts` (authenticated fetch wrapper), `auth.ts`/`firebase.ts` (Firebase client init), `evidenceHash.ts`, `verificationStatus.ts`.
- `frontend/components/` — `AnchorProofButton.tsx` (renders an evidence item's on-chain anchor status, including the Hybrid Anchoring "simulated batch" badge), `ui/` primitives (Badge, Button, Card, Skeleton).

## 5. Backend structure

- `app/lexproof/api/` — FastAPI routers, one per resource area.
- `app/lexproof/domains/passport/` — the core passport/evidence domain: `service.py` (passport creation), `evidence_service.py` (evidence CRUD + anchoring integration), `models/` (Pydantic models), `integrity.py` / `validation.py` (passport-integrity checks shown in the UI as the Document/Policy/Analysis/Evidence/Full-Passport panel).
- `app/lexproof/domains/compliance/` — the regulatory-change-monitoring feature (`compliance_models.py`, `remediation.py`) — a separate MVP workflow from the core passport flow, simulates a regulatory change and identifies affected contracts.
- `app/lexproof/services/` — cross-cutting services: `blockchain.py` (low-level web3.py wrapper, including the multi-layer fix for reliably resolving an anchor's transaction hash from event logs — see project history), `ethereum_anchor_service.py`, `contract_versions.py`, `version_analysis.py`, `version_comparison.py`, `vertex_ai.py`, `auth.py`/`firebase_auth.py`, `firebase.py`, `health.py`, `gcp_logging.py`.
- `app/lexproof/repositories/` — `firestore.py` (generic repository + two specialized, lock-enforcing subclasses — see `SECURITY.md`), `cloud_storage.py`, `secret_manager.py`.
- `app/lexproof/config/` — `settings.py` (Pydantic Settings, env-var driven), `firebase_credentials.py`.
- `backend/scripts/` — operational/demo scripts run directly by a developer (not exposed via any API): `seed_demo.py`, `reset_demo.py`, `create_tamper_demo_fixture.py`, `tamper_demo.py`, `restore_demo_evidence.py`, `create_merkle_batch_demo_anchor.py`, `check_status.py`, `cleanup_test_contracts.py`.

## 6. Deployment shape (as configured for the hackathon build)

- Backend: FastAPI/uvicorn, run locally (`uvicorn app.main:app`) during development; `backend/Dockerfile` exists for containerized deployment (e.g. Cloud Run — see `docs/CLOUD_RUN_BACKEND_READINESS.md`).
- Frontend: Next.js dev server locally (`next dev`); standard Next.js build/deploy path for production.
- Firestore + Cloud Storage: a single GCP project, credentials via a service-account JSON file locally (`GOOGLE_APPLICATION_CREDENTIALS`) or workload identity in a deployed environment.
- Ethereum: Sepolia testnet via an Alchemy RPC endpoint; the registry contract is deployed once (`contracts/deploy_sepolia.py`) and its address configured via `ETHEREUM_CONTRACT_ADDRESS`.
- CORS: `CORSMiddleware` on the FastAPI app, origins from `cors_origin_list()` in settings (env-configured, not hardcoded).

## 7. What this document deliberately doesn't cover

Security posture and known gaps are in `SECURITY.md` and `THREAT_MODEL.md`. Known bugs, deferred work, and explicit non-goals for the hackathon build are in `LIMITATIONS.md` and `ROADMAP.md`. This document is architecture-as-built, not a design proposal.
