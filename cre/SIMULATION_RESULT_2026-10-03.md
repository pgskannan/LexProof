# CRE simulation result — production-settings (live Cloud Run API), 2026-10-03

Command (CRE CLI 1.35.0, Windows):

```powershell
cre workflow simulate lexproof-proof-monitor --target production-settings
```

Run at 2026-10-03T13:02:49Z against `https://lexproof-api-1095554027100.us-central1.run.app`, chain `ethereum-testnet-sepolia`.

```
[USER LOG] Fetched 3 evidence fingerprint(s) from LexProof with DON consensus
[USER LOG] [VERIFIED] evidence 7fd45be6-c028-4faf-a548-4158068f4e95
[USER LOG] [VERIFIED] evidence b37c48ed-ba07-4f28-a440-590b6f3da26e
[USER LOG] [VERIFIED] evidence 1bb07971-d6be-40a5-9381-7ac4410a7ddd
[USER LOG] [ROOT_VERIFIED] passport root 1fd094f7-9775-4774-a042-9445360d7988 (CONTRACT_01 NDA (demo hero passport))
[USER LOG] [ROOT_VERIFIED] passport root 8975e635-0db6-4334-83e5-939ae62a0caf (E2E-anchored passport)
[USER LOG] All 5 anchored item(s) match Sepolia; 0 not anchored/not found
```

| Item | Kind | Off-chain hash = on-chain hash | Verdict |
|---|---|---|---|
| 7fd45be6-c028-4faf-a548-4158068f4e95 | evidence | e1a2d0d9…b936ec | VERIFIED |
| b37c48ed-ba07-4f28-a440-590b6f3da26e | evidence | 8d6fcc6f…3a0c3 | VERIFIED |
| 1bb07971-d6be-40a5-9381-7ac4410a7ddd | evidence | a9e0a700…7cd7b4 | VERIFIED |
| 1fd094f7-9775-4774-a042-9445360d7988 | passport root (CONTRACT_01 NDA) | 4aaaca23…eb2b52 | ROOT_VERIFIED |
| 8975e635-0db6-4334-83e5-939ae62a0caf | passport root (E2E) | 5ad7a54f…3400d9 | ROOT_VERIFIED |

Result: `"alert": false, "checked": 5, "verified": 5, "problems": 0`.
