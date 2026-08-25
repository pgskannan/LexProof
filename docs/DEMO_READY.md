# Demo Readiness

## Sprint 2B Status

### WORKING

- Firebase Google Sign-In client and authenticated route guard are implemented.
- Authenticated API requests obtain and send Firebase ID tokens.
- Contract upload validates PDF, DOCX, and TXT files, hashes original bytes, and
	writes UID-scoped Cloud Storage and Firestore records.
- The upload flow calls Vertex AI through `VertexGeminiProvider` and persists
	findings and a reused `PassportService` passport.
- Public verification remains unauthenticated and does not expose private data.
- Frontend typecheck/build and backend compilation pass.

### PARTIAL

- Blockchain anchoring still requires a reachable Sepolia RPC, signing key,
	deployed LexProofRegistry address, and compiled ABI. No transaction is mocked.
- Cloud persistence and Vertex analysis require real Firebase and Google Cloud
	credentials at runtime.

### BLOCKED

- A complete login-to-Sepolia end-to-end run has not been executed in this local
	environment because Firebase credentials, Vertex credentials, and blockchain
	signing configuration are unavailable.
- Docker image validation requires a running Docker Desktop engine.

The fictional sample contract is available at
[demo-high-risk-contract.pdf](../contracts/demo-high-risk-contract.pdf).

The supported demo sequence is login, upload, analysis, findings, legal
passport, evidence, blockchain anchoring, and public verification.

Private routes use Firebase bearer-token authentication and `/verify` is public.
Contract binaries must be stored in Cloud Storage; Firestore stores metadata,
hashes, findings, passports, evidence, and ownership identifiers.

Before presenting a demo, verify the configured Firebase credentials, Storage
bucket, Vertex AI project/model, Sepolia RPC, deployed LexProofRegistry address,
ABI, and signing key. Missing integration configuration must be treated as a
blocked demo step, never replaced with fake analysis or blockchain results.