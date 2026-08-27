# Ethereum Evidence Anchoring

LexProof anchors the existing deterministic `evidence_hash` to Ethereum Sepolia. The chain stores only the evidence record ID, hash, timestamp, and registrar address. Evidence content and PII remain in LexProof/Firestore.

## Configuration

Copy `backend/.env.example` to an environment-managed `.env` and set:

- `ETHEREUM_RPC_URL`: Sepolia RPC endpoint.
- `ETHEREUM_PRIVATE_KEY`: server-side registrar key. Never commit or log it.
- `ETHEREUM_CHAIN_ID`: `11155111` for Sepolia.
- `ETHEREUM_CONTRACT_ADDRESS`: deployed `LexProofRegistry` address.

The registrar account must be authorized by the contract owner with `setRegistrar(address, true)` and funded with Sepolia ETH.

## Deploy the contract

From `contracts/`, use the repository's Solidity toolchain. The script uses
`solc@0.8.20` through npm and pins OpenZeppelin to `4.9.6` for the existing
import paths:

```powershell
./compile.sh
```

After compilation succeeds, deploy explicitly from `contracts/` with the
backend virtual environment:

```powershell
..\backend\.venv\Scripts\python.exe .\deploy_sepolia.py
```

The script deploys `LexProofRegistry` with the registrar account as
`initialOwner`, waits for confirmation, and prints the public contract address
and transaction hash. Put the resulting address only in the environment-managed
`backend/.env` as `ETHEREUM_CONTRACT_ADDRESS`; do not commit that file. Record
the network (`ethereum-sepolia`), chain ID (`11155111`), and address in the
deployment record for the environment. Do not deploy this contract to mainnet
as part of normal development.

## API

Authenticated API routes are mounted under `/api`:

- `POST /api/evidence/{evidence_id}/anchor`
- `GET /api/evidence/{evidence_id}/anchor`
- `POST /api/evidence/{evidence_id}/verify`
- `GET /api/evidence/{evidence_id}/status`

Anchoring persists metadata in the existing Firestore repository pattern under the `evidence_anchors` collection. Existing evidence records without an anchor continue to work.

Verification must use the hash recalculated by LexProof's existing canonical hashing pipeline. A matching on-chain hash returns `VERIFIED`; a mismatch returns `TAMPERED`; an absent anchor returns `ANCHOR_NOT_FOUND`.

## Tests

Run normal unit tests without a live blockchain:

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q
```

Blockchain calls should be mocked in unit tests. Live Sepolia tests are optional and must be separately marked as integration tests.
