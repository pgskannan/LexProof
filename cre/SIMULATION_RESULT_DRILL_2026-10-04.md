# CRE tamper drill result — drill-settings, 2026-10-04

Command (CRE CLI 1.35.0, Windows):

```powershell
cre workflow simulate lexproof-proof-monitor --target drill-settings
```

Run at 2026-10-04T17:30:52Z, chain `ethereum-testnet-sepolia`. The drill config adds one entry that claims the E2E passport root with its last hex digit altered (`…3400d8` instead of `…3400d9`).

```
[USER LOG] Fetched 2 evidence fingerprint(s) from LexProof with DON consensus
[USER LOG] [VERIFIED] evidence 7fd45be6-c028-4faf-a548-4158068f4e95
[USER LOG] [VERIFIED] evidence b37c48ed-ba07-4f28-a440-590b6f3da26e
[USER LOG] [ROOT_VERIFIED] passport root 8975e635-0db6-4334-83e5-939ae62a0caf (E2E-anchored passport)
[USER LOG] [ROOT_MISMATCH] passport root 8975e635-0db6-4334-83e5-939ae62a0caf (TAMPER DRILL: proof package with one altered hex digit)
[USER LOG] ALERT: 1 item(s) no longer match their on-chain anchor
```

| Item | Kind | Off-chain hash | On-chain hash | Verdict |
|---|---|---|---|---|
| 7fd45be6-c028-4faf-a548-4158068f4e95 | evidence | e1a2d0d9…b936ec | e1a2d0d9…b936ec | VERIFIED |
| b37c48ed-ba07-4f28-a440-590b6f3da26e | evidence | 8d6fcc6f…3a0c3 | 8d6fcc6f…3a0c3 | VERIFIED |
| 8975e635-0db6-4334-83e5-939ae62a0caf | passport root (E2E) | 5ad7a54f…3400d9 | 5ad7a54f…3400d9 | ROOT_VERIFIED |
| 8975e635-0db6-4334-83e5-939ae62a0caf | passport root (TAMPER DRILL) | 5ad7a54f…3400**d8** | 5ad7a54f…3400d9 | ROOT_MISMATCH |

Result: `"alert": true, "checked": 4, "verified": 3, "problems": 1` — one altered hex digit is caught and raises the alert.
