# First Vertical Slice

The implemented path is:

1. `/login` signs in with Firebase Google Sign-In.
2. The authenticated route group redirects unauthenticated users to login.
3. The Contracts page sends the selected PDF, DOCX, or TXT file to
   `POST /api/contracts` with a Firebase bearer token.
4. The backend validates the file, computes SHA-256 over the original bytes,
   uploads it to `contracts/{uid}/{contract_id}/{version_id}/original/{filename}`,
   and persists contract/version metadata in Firestore.
5. `POST /api/contracts/{contract_id}/analyze` extracts text and calls the
   existing `VertexGeminiProvider` for structured JSON analysis.
6. Findings are stored in `risk_findings`; the existing `PassportService`
   creates evidence and a legal passport, and passport metadata is stored in
   `legal_passports`.
7. The existing passport UI displays the passport and provides the existing
   blockchain anchor action. Anchoring is real and fails clearly when Sepolia
   configuration is absent.
8. `/public-verify` remains public and returns only proof hashes and public
   blockchain metadata.

The cloud-backed steps require the environment variables in
[CONFIGURATION.md](CONFIGURATION.md). No fake AI output or blockchain success
is returned when those services are unavailable.