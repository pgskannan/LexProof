# LexProof

## Problem

AI-generated legal analysis can be modified or disputed after the fact. Today, there is no simple independent way to prove that an AI finding has not been altered since it was created.

## Solution

LexProof turns AI findings into tamper-evident legal evidence and anchors a canonical SHA-256 hash to Ethereum Sepolia. Anyone can recompute the evidence hash and compare it with the on-chain anchor without trusting LexProof's backend as the final authority.

## Architecture

```mermaid
flowchart LR
User[User uploads Contract] --> Next[LexProof Frontend<br/>Next.js]
Next --> API[FastAPI Backend]
API --> Gemini[Gemini AI Analysis]
API --> Firestore[(Firestore<br/>Legal Evidence + Legal Passport)]
API --> Hash[canonicalize_evidence_item<br/>SHA-256]
Hash -->|anchor| Ethereum[(Ethereum Sepolia<br/>LexProofRegistry Solidity contract)]

Verifier[Verifier<br/>logged-in or public] --> Browser[Browser verifier<br/>verifyOnChainIndependently<br/>readEvidenceAnchorFromEthereum]
Browser -->|direct public RPC<br/>NOT through FastAPI| Ethereum
Browser --> Result[VERIFIED or TAMPERED<br/>Etherscan transaction link]
```

## Killer Demonstration

The clearest proof is a tamper / verify / restore cycle:

```text
VERIFIED -> Firestore tampered -> TAMPERED -> Restore -> VERIFIED
```

1. Verify an anchored evidence item. The stored evidence matches its Ethereum anchor.
2. Change the stored evidence directly in Firestore to simulate tampering.
3. Verify again. The recomputed hash no longer matches, and the result is `TAMPERED`.
4. Restore the original evidence and verify once more. The result returns to `VERIFIED`.

The hash covers the canonical evidence fields defined by the application: `evidence_id`, `passport_id`, `evidence_type`, `title`, `description`, `content`, `content_type`, `risk_impact`, `compliance_impact`, `evidence_status`, `contract_reference`, `policy_reference`, `analysis_reference`, `source`, `source_id`, and `metadata`. Operational timestamps and the stored hash itself are excluded so the value can be recomputed.

## Technical Stack

- Next.js and TypeScript
- FastAPI
- Firestore
- Ethereum Sepolia
- Solidity
- ethers.js
- Gemini

## Try It

Start at the dashboard, open a contract with a Legal Passport, expand an evidence item, and select **Verify Publicly**. The public verifier accepts an evidence ID directly and shows the backend result plus an independent browser-to-Ethereum comparison.

The current verification baseline is 206/206 backend tests and 14/14 frontend tests.

## Links

- GitHub: https://github.com/pgskannan/LexProof
- Live demo: deployment in progress
- Evidence registry (LexProofRegistry, Sepolia): https://sepolia.etherscan.io/address/0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191
- Passport root registry (LexProofPassportRegistry, Sepolia): https://sepolia.etherscan.io/address/0x21Ddd03549c2d4fb75336b616f18c34D4a9BFDE6
- Example passport-root anchor transaction: https://sepolia.etherscan.io/tx/0x1356cf613b05e5a681490f4d89e62d261618c40d657adfde616fbfcf21e32e92
- Chainlink CRE Proof Monitor: [cre/README.md](cre/README.md) (simulation results in [cre/SIMULATION_RESULT_2026-09-28.md](cre/SIMULATION_RESULT_2026-09-28.md))
- Hackathon: BLI Legal Tech Hackathon 2 (https://dorahacks.io/hackathon/legal-hack-2026/detail)

## License

Copyright 2026 Kannan Ganesan. Licensed under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE).
