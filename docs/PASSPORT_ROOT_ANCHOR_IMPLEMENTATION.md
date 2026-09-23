# Passport Root Anchor — Implementation Report

Status: **implementation complete, local-chain verified, Sepolia deployment prepared but NOT executed**

This document records what was actually built for the additive Ethereum/Sepolia
anchoring of the LexProof Legal Passport root commitment, against the approved
design in `docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md`. Read that document first
for the *why*; this document is the *what was done* and *how it was verified*.

## 1. Summary

A new, additive `LexProofPassportRegistry` contract anchors the existing v1
SHA-256 `metadata.passport_hash` root for a Legal Passport, keyed by
`keccak256(UTF-8(passport_id))`. It is a completely separate contract, address,
ABI, and Firestore collection from the existing per-evidence-item
`LexProofRegistry` / `evidence_anchors` path. Nothing about evidence-item
anchoring (`EthereumAnchorService`, `AnchorProofButton.tsx`,
`registerProof`/`anchorEvidence`) was touched, renamed, or reused.

The server never trusts a client-supplied hash. A passport becomes eligible
for anchoring only when `verify_passport_integrity()` reports PASS for every
one of `document_status` / `policy_status` / `analysis_status` /
`evidence_status` / `passport_hash_status`; the server then anchors its own
recomputed `recomputed_passport_hash`, never anything read from the request
body or from the passport document's own stored fields. UNVERIFIABLE
(legacy/evidence-only snapshots) and FAIL both block anchoring outright —
there is no "anchor anyway" path, and a blockchain match can never promote a
FAIL/UNVERIFIABLE local integrity result to PASS.

The old, unsafe `POST /passports/{id}/anchor` route (client-supplied hashes,
no ownership check, called `registerProof`) is now permanently disabled
(`410 Gone`) rather than retrofitted — `registerProof` is not a safe reuse
target for this design (see architecture doc §2.3).

## 2. Contract

**File:** `contracts/LexProofPassportRegistry.sol` (136 lines, Solidity
`^0.8.20`, OpenZeppelin `Ownable` + `ReentrancyGuard` v5.0.2).

```solidity
struct PassportRootAnchor {
    bytes32 passportRoot;
    uint256 timestamp;
    address anchoredBy;
}
mapping(bytes32 => PassportRootAnchor) public passportRoots;
mapping(address => bool) public authorizedRegistrars;

function anchorPassportRoot(bytes32 passportKey, bytes32 passportRoot) external onlyRegistrar nonReentrant;
function verifyPassportRoot(bytes32 passportKey, bytes32 passportRoot) external view returns (bool);
function getPassportRoot(bytes32 passportKey) external view returns (bytes32, uint256, address);
function setRegistrar(address registrar, bool authorized) external onlyOwner;
event PassportRootAnchored(bytes32 indexed passportKey, bytes32 indexed passportRoot, uint256 timestamp, address indexed anchoredBy);
```

Design properties, all proven against real compiled bytecode on a local EVM
(§5):

- **First-write-wins immutability.** `anchorPassportRoot` reverts
  (`"Passport root already anchored"`) on any second write for the same
  `passportKey` — whether the second write repeats the identical root or
  supplies a different one. There is no update/delete function of any kind.
- **Registrar-gated, owner-managed.** Only `authorizedRegistrars[msg.sender]`
  can anchor; only the contract owner can grant/revoke registrar status.
- **Zero-value rejection.** Both `passportKey == 0` and `passportRoot == 0`
  revert before any state is written.
- **No `updateProofStatus`, no `registerProof`.** Confirmed by ABI inspection
  in the test suite — this contract has no mutator beyond the single
  first-write anchor call.
- **Fully isolated from `LexProofRegistry`.** Deployed at its own address
  with its own storage; anchoring an evidence item cannot create or affect a
  passport root and vice versa (proven by deploying both side-by-side on the
  same local chain and cross-checking).

`contracts/compile.sh` now compiles `LexProofRegistry.sol` and
`LexProofPassportRegistry.sol` together (`solc@0.8.20`); byte-for-byte
comparison confirms `LexProofRegistry`'s own compiled artifacts (ABI/BIN)
are unchanged by this addition.

## 3. Identity and root relationship

| Concept | Algorithm | Purpose |
|---|---|---|
| `passportKey` (on-chain mapping key) | `keccak256(UTF-8(passport_id))` | Ethereum-native identity key. Computed by `compute_passport_key()`. Never a content commitment. |
| `passportRoot` (on-chain value) | existing v1 `metadata.passport_hash` (SHA-256), decoded to `bytes32` | The actual content commitment. Computed by the existing, untouched `compute_passport_hash()`/`verify_passport_integrity()` pipeline; `passport_root_bytes32()` only decodes the existing hex string, it never recomputes or alters it. |

The two hash families (Keccak-256 for the identity key, SHA-256 for the
content root) are deliberately kept algorithmically distinct, matching the
approved design. `passport_id` itself (a UUID) is never sent as on-chain
calldata — only the 32-byte key and 32-byte root.

**Golden vectors** (independently cross-checked in
`test_passport_root_anchor_service.py` against a direct `Web3.keccak()` call,
not merely re-derived through the function under test):

| `passport_id` | `compute_passport_key(passport_id)` |
|---|---|
| `11111111-1111-4111-8111-111111111111` | `31e5891f6803041a37cfae842c5bf47aa89df5130d6a8ba235cdd9041744763f` |
| `a1b2c3d4-e5f6-4789-9abc-def012345678` | `e74ec87633f8add186ec9c983897f821c715d43c910151b367e8329964fe43e4`[:64] (64-char value) |

## 4. Backend

### 4.1 New files

- `backend/app/lexproof/services/passport_blockchain.py` — `PassportBlockchainService`, a self-contained web3.py client for `LexProofPassportRegistry` only. Never imports or mutates `services/blockchain.py`'s `BlockchainService`. Rejects a non-Sepolia `chain_id` at construction and on every real-chain call.
- `backend/app/lexproof/services/passport_root_anchor_service.py` — `PassportRootAnchorService`: eligibility gating, idempotent/race-safe anchoring, verification, and public existence-check logic. `passport_root_eligibility()` is a pure function anyone can unit-test without a chain or Firestore.

### 4.2 Edited files

- `backend/app/lexproof/domains/passport/utils/hashing.py` — added `compute_passport_key()` and `passport_root_bytes32()`. All existing hash functions (`compute_passport_hash`, `hash_evidence_item`, etc.) are byte-for-byte unchanged.
- `backend/app/lexproof/config/settings.py` — added `passport_registry_address` (env `ETHEREUM_PASSPORT_REGISTRY_ADDRESS`) and `has_passport_blockchain_configuration()`. Fully independent of the existing evidence-registry settings.
- `backend/app/lexproof/repositories/firestore.py` — added `PassportAnchorRepository`, a create-once repository over a **new** `passport_anchors` collection (never `evidence_anchors`).
- `backend/app/lexproof/domains/passport/api/router.py` — extended `POST /passports/{id}/verify` with the additive `anchor_status` (and related) fields; added `POST /passports/{id}/anchor-root`.
- `backend/app/lexproof/api/blockchain.py` — permanently disabled the legacy `POST /passports/{id}/anchor` (`410 Gone`, handler body removed entirely — it no longer touches `create_blockchain_service()`/`registerProof`/`transaction_store`); added the public, existence-only `GET /verify/passport/{id}`.
- `backend/requirements.txt` — added `eth-tester[py-evm]` as a **test-only** dependency (used only by `test_passport_registry_contract.py`; never imported by production code).

### 4.3 API surface

| Endpoint | Auth | Behavior |
|---|---|---|
| `POST /api/passports/{id}/verify` | required, org-aware visibility | Unchanged local integrity fields, **plus** `anchor_status` (`PASS`/`FAIL`/`UNVERIFIABLE`/`NOT_ANCHORED`/`NETWORK_ERROR`/`CHAIN_MISMATCH`/`INVALID_PROOF`), `anchor_ineligible_reasons`, `blockchain_network`, `contract_address`, `chain_id`, `transaction_hash`, `block_number`, `on_chain_root`. |
| `POST /api/passports/{id}/anchor-root` | required, org-aware visibility | Body-less — the client supplies only the `passport_id` in the URL. Recomputes integrity server-side, anchors only if eligible. `409` (eligibility or conflict), `503` (chain not configured/unreachable), `400` (other `ValueError`), `500` (unexpected). |
| `GET /api/verify/passport/{id}?passport_hash=...` | **none** (public, wildcard-CORS sub-app) | Existence-only: does a root matching the given `passport_hash` exist for this `passport_id`. Never loads or exposes the confidential `verification_snapshot`. |
| `POST /api/passports/{id}/anchor` | required | **Disabled.** Always `410 Gone` with a message pointing at `anchor-root`. Body, if any, is never parsed. |

### 4.4 Idempotency / recovery playbook

`PassportRootAnchorService.anchor_passport_root()` follows the same shape as
the existing, already-proven `EthereumAnchorService.anchor_evidence()`:

1. Firestore already has a matching anchor → return it, no transaction.
2. Firestore has a **different** root → `PassportRootConflictError` (never overwritten).
3. Chain already has a matching root (Firestore write was lost, or a race) → recover from chain, persist, no transaction.
4. Chain has a **different** root → `PassportRootConflictError`.
5. Nothing exists anywhere → submit a new transaction; persist only after `receipt.status == 1`.
6. Submission itself fails (e.g. a concurrent caller won the race) → re-check chain once before propagating the failure; recover instead of failing if now found.
7. Receipt succeeds but event-log enrichment (tx hash/block lookup) fails → the anchor is still persisted (with `transaction_hash`/`block_number` left `None`) rather than losing a confirmed on-chain anchor over a display-only lookup failure.

## 5. Testing

All counts below are from real, executed runs in this implementation pass —
not estimates.

| Suite | File | Tests | Result |
|---|---|---|---|
| Contract (local EVM, real compiled bytecode via `eth-tester`/`py-evm`) | `backend/tests/lexproof/blockchain/test_passport_registry_contract.py` | 17 | **17 passed** |
| Service unit tests (fake repository + fake blockchain, no network) | `backend/tests/lexproof/passport/test_passport_root_anchor_service.py` | 37 | **37 passed** |
| Router/API integration tests (FastAPI `TestClient`, scripted service) | `backend/tests/lexproof/passport/test_passport_root_anchor_api.py` | 17 | **17 passed** |
| **New tests total** | | **71** | **71 passed, 0 failed** |
| Full backend regression (pre-existing baseline + all new tests) | `backend/` (`pytest -n 2`) | 1001 (930 baseline + 71 new) | **1001 passed, 0 failed** |
| Frontend type-check | `frontend/` (`tsc --noEmit`) | whole project, incl. new files | **0 errors** |
| Frontend E2E discovery | `frontend/` (`playwright test --list`) | 12 tests / 7 files (incl. 1 new) | all discovered, syntactically valid |
| Frontend E2E live run | `workflow/passport-root-anchor.spec.ts` | 1 | **blocked** — see §7 |
| Frontend unit tests (Vitest) | `frontend/` | spot-checked 24+ files | 0 failures observed; full single-run blocked by a pre-existing host timing constraint unrelated to this change (documented previously) |

The contract tests deploy the **actual** compiled bytecode
(`contracts/build/LexProofPassportRegistry_sol_LexProofPassportRegistry.{abi,bin}`)
to a real, in-process local Ethereum chain (`eth_tester` + `PyEVMBackend`) —
real EVM execution, real reverts, real event logs, not a Python mock of the
contract's behavior. This satisfies the "local blockchain verification
before Sepolia" requirement.

## 6. Frontend

- `frontend/app/(authenticated)/legal-passport/components/PassportRootAnchorPanel.tsx` — new component, added to the Legal Passport page immediately after the existing "Passport Integrity" block (`legal-passport/page.tsx`). Renders the extended `/verify` response's `anchor_status` and calls `/api/passports/{id}/anchor-root` on the real "Anchor to Ethereum Sepolia" button — no hash, score, or other value is ever sent from the client.
- States covered, matching the task's required UI states: **Anchored** (PASS — network/contract/tx/block, Etherscan links), **Not anchored** (NOT_ANCHORED — eligible, shows the anchor button), **Not eligible** (FAIL/UNVERIFIABLE — reasons list, no anchor button), **Network unavailable** (NETWORK_ERROR/CHAIN_MISMATCH — no anchor button), plus a distinct **Mismatch** state (INVALID_PROOF — on-chain root exists but does not match the current recomputed fingerprint).
- Follows the existing `AnchorProofButton.tsx` visual pattern (badge + detail card + button), but is a fully separate component — no shared state, no shared API calls.
- `legal-passport/page.tsx`'s `PassportIntegrityResult` interface was extended with the new optional fields; nothing existing was removed or renamed.

## 7. E2E status (honest account)

`frontend/e2e/workflow/passport-root-anchor.spec.ts` was written following
the repo's existing E2E conventions exactly (real Firebase login, real
upload + real Gemini analysis to reach a genuinely eligible, freshly-created
passport, real backend calls, no mocks). It was verified statically:

- `tsc --noEmit`: 0 errors.
- `npx playwright test --list`: discovered correctly (12 tests / 7 files total, including this new one).

**It has not been run to completion.** `npx playwright install chromium`
fails in this diagnostic Linux VM with the same, previously-documented
environment blocker (`docs`/prior phase report):
`Download failed: server returned code 403 body 'Connection blocked by
network allowlist'` against Playwright's CDN. No system Chromium is
available either. This is an environment/network-policy limitation of this
specific execution host, not an application defect — the same blocker that
stopped the Phase 3J-A foundation from self-verifying and that was
previously resolved only by a human running `npm run test:e2e` directly on
the real machine with a working Chromium.

The test itself is also written to be honest about what it can prove **on
this specific environment right now**: because Phase F (Sepolia deployment,
§8) has not been executed, `ETHEREUM_PASSPORT_REGISTRY_ADDRESS` is not
configured, so a freshly-created, genuinely-eligible passport's real
`anchor_status` today is `NETWORK_ERROR` ("Network unavailable" in the UI),
not `PASS`. The test asserts on whichever of the two real, honest states the
environment actually reports, and only exercises the click-to-anchor /
persistence-across-reload-and-logout / idempotency assertions when the
registry is actually configured. It does not claim a live on-chain anchor
succeeded when it has not.

**To actually run it:** from `frontend/`, with the backend and frontend
both running locally and `.env.e2e.local` populated (see `e2e/README.md`),
on a machine with a working Chromium:

```
npx playwright install chromium   # once, if not already installed
npm run test:e2e -- workflow/passport-root-anchor.spec.ts
```

## 8. Sepolia deployment — prepared, NOT executed

Per the task's explicit instruction, real Sepolia deployment requires a
funded registrar private key and Sepolia RPC credentials this environment
does not have, and was never attempted. What is ready for a human/CI with
those credentials:

1. `contracts/LexProofPassportRegistry.sol` is compiled and its bytecode/ABI
   are checked into `contracts/build/`.
2. `PassportBlockchainService`/`create_passport_blockchain_service()`
   already read `ETHEREUM_PASSPORT_REGISTRY_ADDRESS` and the existing
   `blockchain_private_key`/`ethereum_rpc_url` settings — no code change is
   needed once a real address exists.
3. Deployment itself (not performed here) would be: deploy
   `LexProofPassportRegistry` with the constructor's `initialOwner` set to
   the funded registrar address (which is automatically also the first
   authorized registrar per the constructor), record the deployed address,
   set `ETHEREUM_PASSPORT_REGISTRY_ADDRESS` in the environment, and re-run
   `frontend/e2e/workflow/passport-root-anchor.spec.ts` to get the real
   positive/persistence branch exercised for the first time.

**Current blockchain deployment status: LOCAL only.** No transaction has
ever been submitted to Sepolia or any other live network by this
implementation.

## 9. Security confirmations

- No PII, contract text, evidence content, scores, or tenant/org identifiers
  are ever placed on-chain — only a 32-byte root, a 32-byte identity key, a
  timestamp, and the registrar address.
- The server independently recomputes and verifies passport integrity on
  every anchor/verify call; no client-supplied hash is ever trusted or
  accepted (the new `anchor-root` endpoint takes no request body at all).
- UNVERIFIABLE is never silently promoted to PASS by the presence of a
  blockchain root, in either direction — local integrity is computed first
  and is never overridden by chain state.
- A passport root anchor, once written (Firestore or on-chain), is never
  overwritten, updated, or deleted — enforced at three independent layers:
  the contract's own `require(... == bytes32(0))` check, the create-once
  `PassportAnchorRepository`, and the service's own existing-anchor
  conflict check before ever building a transaction.
- The legacy unsafe route is not merely deprecated but structurally
  disabled: its handler body was removed and replaced with an unconditional
  `410`, so it cannot be reached even by a stale client that still calls it.
- No existing evidence-item anchor, contract, ABI, deployed address, or test
  was modified. `LexProofRegistry`'s compiled artifacts are byte-for-byte
  identical (verified in `compile.sh`'s own comparison).

## 10. Remaining risks / follow-ups

- **Not yet deployed to Sepolia** — by design, per §8. Until it is, every
  passport's real `anchor_status` will be `NETWORK_ERROR`, which is the
  correct, honest behavior rather than a defect.
- **E2E live execution is environment-blocked** in this diagnostic host
  (§7); needs to be run once on a machine with real Chromium, ideally
  again after Sepolia deployment to exercise the true positive/persistence
  branch.
- **OpenZeppelin version note** (pre-existing, not introduced by this
  work): an older doc elsewhere in this repo references OpenZeppelin
  `4.9.6`; the contracts directory's actual installed dependency is `5.0.2`.
  Both `LexProofRegistry` and the new `LexProofPassportRegistry` compile and
  behave correctly against the installed `5.0.2`; this is a stale-comment
  discrepancy to clean up separately, not a functional issue.
- **Frontend Vitest full-suite run** could not be completed in a single
  tool call in this diagnostic host (a pre-existing ~2-minute host-timing
  constraint documented in earlier phases, unrelated to this change); a
  spot-check of 24+ files showed zero failures and none of this
  implementation's files are exercised by any existing Vitest spec.
