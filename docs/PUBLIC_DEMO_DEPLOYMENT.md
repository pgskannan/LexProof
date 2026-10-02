# Public demo deployment (hackathon)

Goal: give judges links they can open themselves, with no login and no localhost.

## Phase 1: frontend only on Vercel (about 30 minutes, no backend needed)

The **Tamper Test** (`/public-verify/tamper`) runs entirely in the browser. It recomputes the
passport root with Web Crypto and reads the LexProofPassportRegistry contract on Ethereum Sepolia
through a public RPC. So a frontend-only deployment already gives judges a live, working proof.

1. The demo passport file is `frontend/public/demo/proof-package.json` (CONTRACT_01, passport
   `1fd094f7-9775-4774-a042-9445360d7988`, anchored 2026-09-29 at Sepolia block 11810118). It is a
   **stripped** copy: contract, hashes and evidence anchors only. The full downloaded bundle also
   contains the contract text (`verification_snapshot`), so never put the full bundle in `public/`.
   To replace it, export a new bundle and strip it the same way.
2. On vercel.com: **Add New → Project →** import `pgskannan/LexProof`, set **Root Directory** to
   `frontend`, and keep the Next.js framework preset.
3. Environment variables (Production):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_ETHEREUM_SEPOLIA_RPC_URL` | `https://ethereum-sepolia-rpc.publicnode.com` (or your own RPC) |
   | `NEXT_PUBLIC_LEXPROOF_CONTRACT_ADDRESS` | evidence registry `0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191` |
   | `NEXT_PUBLIC_LEXPROOF_PASSPORT_REGISTRY_ADDRESS` | passport registry `0x21Ddd03549c2d4fb75336b616f18c34D4a9BFDE6` |
   | `NEXT_PUBLIC_FIREBASE_*` | same values as `frontend/.env.local` (client config, not secrets) |
   | `NEXT_PUBLIC_API_URL` | leave empty until Phase 2 |

4. Deploy, then open `https://<project>.vercel.app/public-verify/tamper` → **Load the demo passport**.
   The page should show "Anchor found on Ethereum Sepolia" and **VERIFIED**.
5. Locally, set `NEXT_PUBLIC_PUBLIC_VERIFY_ORIGIN=https://<project>.vercel.app` in
   `frontend/.env.local` so the QR codes in the app open the public site when scanned by a phone.

Evidence lookups on `/public-verify?evidence_id=…` need the API, so they only work after Phase 2.

## Phase 2: backend on Cloud Run (public verify API + full app)

One script does it: `backend/deploy/deploy-cloud-run.ps1`. Prerequisites: the gcloud CLI,
`gcloud auth login` with an owner of the `lexproof-afc7c` project, and a filled-in `backend/.env`.

```powershell
cd C:\Projects\LexProof
powershell -ExecutionPolicy Bypass -File backend\deploy\deploy-cloud-run.ps1
```

What it does (safe to re-run):
1. Enables Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Vertex AI, Firestore and Identity Toolkit.
2. Creates the `lexproof-api` runtime service account with only Firestore, Vertex AI, Firebase Auth admin,
   Storage object admin, secret accessor and log writer roles. No service-account key is used: on Cloud Run
   the API authenticates with Application Default Credentials (detected via `K_SERVICE`).
3. Copies `ETHEREUM_PRIVATE_KEY` and `ETHEREUM_RPC_URL` from `backend/.env` into Secret Manager
   without printing them. Nothing secret is in the image: `.gcloudignore` excludes `.env` and the
   service-account file from the upload, and the Dockerfile copies only `app/` and `scripts/`.
4. Builds `backend/` with Cloud Build and deploys `lexproof-api` (1 GiB, max 1 instance so in-memory
   state stays consistent, `--allow-unauthenticated` because the API enforces its own Firebase auth and
   the public verify routes are public by design). CORS allows the Vercel site and localhost.
5. Prints the URL and checks `/health`.

Then:
- Vercel → Settings → Environment Variables: `NEXT_PUBLIC_API_URL=<service URL>` → Redeploy.
- Firebase console → Authentication → Settings → Authorized domains: add `lexproof-pied.vercel.app`.
- Logs: `gcloud run services logs read lexproof-api --region us-central1 --limit 50`.
- Add `--MinInstances 1` to the script to avoid cold starts during judging (small always-on cost).

The image installs `requirements.txt` only; tests use `requirements-dev.txt`.

## Notes
- Everything runs on the **Sepolia testnet**. Say so in the submission. Mainnet path: a
  gas-sponsoring relayer, so customers never handle crypto.
- Never commit `backend/.env`, `firebase-service-account.json` or any private key.
