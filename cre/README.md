# LexProof Proof Monitor: Chainlink CRE workflow

An independent, decentralized auditor for LexProof's core claim that *an AI legal finding hasn't changed since it was anchored on Ethereum.*

On a schedule, the workflow:

1. **Off-chain (HTTP capability, DON consensus):** fetches each monitored evidence item's SHA-256 fingerprint from LexProof's **public** verification API (`GET /api/verify/{evidence_id}`, no login). LexProof recomputes it from the record as it's stored now. Every node fetches it independently and the DON must agree (`consensusIdenticalAggregation`).
2. **On-chain (EVM capability):** reads the anchored hash for the same item straight from `LexProofRegistry.evidenceAnchors(keccak256(evidenceId))` on Sepolia at the last finalized block. It doesn't trust LexProof's own chain read.
3. **On-chain:** reads each monitored Legal Passport's root from `LexProofPassportRegistry.passportRoots(keccak256(passportId))` and compares it with the root published in that passport's proof package.
4. Returns a verdict per item and an overall `alert` flag:

| Verdict | Meaning |
|---|---|
| `VERIFIED` | LexProof's current record hashes to exactly what was anchored |
| `TAMPERED` | the stored record changed after anchoring |
| `NOT_ANCHORED` | no anchor on chain for this evidence ID |
| `EVIDENCE_NOT_FOUND` | anchored on chain, but LexProof no longer serves the record |
| `ROOT_VERIFIED` / `ROOT_MISMATCH` / `ROOT_NOT_ANCHORED` | same, for a passport's root commitment |

It's read-only: no chain writes, no secrets, no LexProof credentials.

**Contracts (Ethereum Sepolia)**
- `LexProofRegistry` (evidence): `0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191`
- `LexProofPassportRegistry` (passport roots): `0x21Ddd03549c2d4fb75336b616f18c34D4a9BFDE6`

## Run the simulation (Windows, PowerShell)

Prerequisites, one time:

```powershell
# 1. Bun >= 1.2.21 (CRE's TypeScript toolchain)
powershell -c "irm bun.sh/install.ps1 | iex"
# 2. CRE CLI
irm https://app.chain.link/cre/install.ps1 | iex
# 3. Create a free CRE account at https://app.chain.link (email + 2FA), then:
cre login
cre whoami
```

Then, with the LexProof backend running on `localhost:8000`:

```powershell
cd C:\Projects\LexProof\cre
Copy-Item .env.example .env          # throwaway key; the monitor never signs anything
cd lexproof-proof-monitor
bun install
cd ..
cre workflow simulate lexproof-proof-monitor --target staging-settings
```

When it prints "Cron scheduler started. Press Enter to skip waiting…", press **Enter** to run immediately (the schedule is every 10 minutes).

Expected (staging): `[VERIFIED]` for both evidence items, `[ROOT_VERIFIED]` for the passport, and "All 3 anchored item(s) match Sepolia". The actual run is recorded in [`SIMULATION_RESULT_2026-09-28.md`](SIMULATION_RESULT_2026-09-28.md).

**Against the live public API** (Cloud Run, no local backend needed): `config.production.json` points at
`https://lexproof-api-1095554027100.us-central1.run.app` and also monitors the CONTRACT_01 demo passport.

```powershell
cre workflow simulate lexproof-proof-monitor --target production-settings
```

**Tamper drill** (same workflow; the config claims a root with one altered hex digit):

```powershell
cre workflow simulate lexproof-proof-monitor --target drill-settings
```

Expected: `[ROOT_MISMATCH]` for the drill entry and `ALERT: 1 item(s) no longer match their on-chain anchor`.


## Configure what's monitored

`lexproof-proof-monitor/config.*.json`:
- `evidenceIds`: evidence IDs to watch (any LexProof evidence ID; the same one the public verifier and QR codes use).
- `passports`: `{ label, passportId, expectedRoot }`. `expectedRoot` is `hashes.passport_hash` from the passport's proof-package download.
- `lexproofApiUrl`: `http://localhost:8000` for local simulation. Set the deployed API URL in `config.production.json` before deploying to the CRE network (deploying needs CRE deploy access).

## Files

- `lexproof-proof-monitor/main.ts`: the workflow (cron trigger → HTTP + consensus → EVM reads → verdicts)
- `contracts/abi.ts`: minimal read ABIs for both registries
- `project.yaml`: Sepolia RPC per target · `workflow.yaml`: targets (staging / production / drill)

Simulated successfully with CRE CLI v1.35.0 on 2026-09-28. Typechecked against `@chainlink/cre-sdk` 1.22. On-chain keys (`keccak256(UTF-8 id)`) and call data were cross-checked against LexProof's backend derivation and a live Sepolia `eth_call`.
