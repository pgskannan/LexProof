# CRE simulation result: staging (2026-09-28)

Run on the developer's Windows machine with CRE CLI v1.35.0, `@chainlink/cre-sdk` 1.22.0 and Bun 1.4.2, against the live LexProof backend and Ethereum Sepolia.

```
PS C:\Projects\LexProof\cre> cre workflow simulate lexproof-proof-monitor --target staging-settings
✓ Workflow compiled
✓ Simulation limits enabled
  HTTP: req=120kb resp=250kb timeout=10s | ConfHTTP: req=125kb resp=500kb timeout=1m30s | Consensus obs=25kb | ChainWrite evm_report=50kb evm_gas=10000000 solana_report=265b solana_cu=300000 | WASM binary=100mb compressed=20mb
  Binary hash: dd3748509df317e1821d1736046ee9e02956c02f45c87f19e15ecbca5712e4f8
  Config hash: d3b77f0e240bf256a212ce3edb45b94c4591e98e5a99e9f1138479dd53ef93a2
2026-09-28T12:25:41Z [SIMULATION] Simulator Initialized
2026-09-28T12:25:41Z [SIMULATION] Running trigger trigger=cron-trigger@1.0.0
2026-09-28T12:27:23Z [USER LOG] Fetched 2 evidence fingerprint(s) from LexProof with DON consensus
2026-09-28T12:27:23Z [USER LOG] [VERIFIED] evidence 7fd45be6-c028-4faf-a548-4158068f4e95
2026-09-28T12:27:23Z [USER LOG] [VERIFIED] evidence b37c48ed-ba07-4f28-a440-590b6f3da26e
2026-09-28T12:27:23Z [USER LOG] [ROOT_VERIFIED] passport root 8975e635-0db6-4334-83e5-939ae62a0caf (E2E-anchored passport)
2026-09-28T12:27:23Z [USER LOG] All 3 anchored item(s) match Sepolia; 0 not anchored/not found

✓ Workflow Simulation Result:
{
  "alert": false,
  "checked": 3,
  "items": [
    { "anchoredAt": 1787947692, "id": "7fd45be6-c028-4faf-a548-4158068f4e95", "kind": "evidence",
      "label": "evidence (LexProof API: VERIFIED)",
      "offchainHash": "e1a2d0d96562dca5458573c8346b2da4441df3c35aa94b068410b65899b936ec",
      "onchainHash":  "e1a2d0d96562dca5458573c8346b2da4441df3c35aa94b068410b65899b936ec", "verdict": "VERIFIED" },
    { "anchoredAt": 1790194860, "id": "b37c48ed-ba07-4f28-a440-590b6f3da26e", "kind": "evidence",
      "label": "evidence (LexProof API: VERIFIED)",
      "offchainHash": "8d6fcc6fd8fbc95d144bb41467577ea53eb0d143dd49830611bafbfce383a0c3",
      "onchainHash":  "8d6fcc6fd8fbc95d144bb41467577ea53eb0d143dd49830611bafbfce383a0c3", "verdict": "VERIFIED" },
    { "anchoredAt": 1790360004, "id": "8975e635-0db6-4334-83e5-939ae62a0caf", "kind": "passport-root",
      "label": "E2E-anchored passport",
      "offchainHash": "5ad7a54ff0c88de57e846b3c6132914c0cdb827ae939d77c00891334ca3400d9",
      "onchainHash":  "5ad7a54ff0c88de57e846b3c6132914c0cdb827ae939d77c00891334ca3400d9", "verdict": "ROOT_VERIFIED" }
  ],
  "network": "ethereum-testnet-sepolia",
  "problems": 0,
  "verified": 3
}
2026-09-28T12:27:23Z [SIMULATION] Execution finished signal received
```

Each `onchainHash` was read by the CRE EVM capability directly from the Sepolia registries at the last finalized block. Each evidence `offchainHash` came from LexProof's public verification API under DON identical-consensus. Cross-check: evidence `7fd45be6…` is the same item the public verifier and the offline proof package report as VERIFIED.
