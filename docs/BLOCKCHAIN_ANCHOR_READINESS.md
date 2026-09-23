# LexProof Blockchain Anchor Readiness

**Date:** 2026-09-18  
**Companion:** `docs/EVIDENCE_INTEGRITY_AUDIT.md`, `docs/PASSPORT_INTEGRITY_MODEL.md`, `docs/EVIDENCE_CANONICALIZATION_SPEC.md`

Do **not** implement passport-root Ethereum anchoring from this document. Do **not** call `registerProof`. Do **not** change `LexProofRegistry`.

---

## Architecture

```text
CURRENT

Evidence Item
     ↓
hash_evidence_item   (canonicalization v1, Python)
     ↓
Ethereum / Sepolia


PASSPORT-ROOT (implemented locally; Sepolia pending)

Legal Passport
     ↓
document_hash + policy_hash + analysis_hash + evidence_hash
     ↓
metadata.passport_hash
     ↓
Ethereum / Sepolia   (additive; existing item anchors stay valid)
```

Merkle-batch anchoring remains demo-only (`is_mock: true`).

---

## A. What exact hash should be anchored?

| Digest | Function | Commits to | Anchored today? |
|---|---|---|---|
| Item hash | `hash_evidence_item` | One evidence record (`EVIDENCE_HASH_FIELDS`) | **Yes** |
| `passport.evidence_hash` | `hash_evidence_package` | Publish-time package | No |
| `passport.document_hash` | `hash_document` | Extracted + normalized text | No |
| `passport.analysis_hash` | `hash_ai_analysis` | Analysis result dict | No |
| `metadata.passport_hash` | `compute_passport_hash` | The four stored component hashes | No |

Current product claims: item hash plus the additive Legal Passport root
commitment `metadata.passport_hash`. The passport-root implementation and local
EVM verification are complete; Sepolia deployment and live transactions remain
pending.

---

## B. Is the hash deterministic?

```text
PASS
```

v1 `json.dumps(sort_keys=True, ensure_ascii=False)` UTF-8 SHA-256. `int` `95` vs `float` `95.0` is a defined difference, not non-determinism.

---

## C. Is verification deterministic?

```text
PASS
```

CREATE and VERIFY use the same Python functions. Claimed snapshot inputs fail closed. Unclaimed legacy/repaired fields are `UNVERIFIABLE`, not `PASS`. Empty `evidence_items` lists are hashed. Live post-publish evidence is ignored when a snapshot list is present.

---

## D. Does the hash cover all material evidence?

```text
FAIL for a whole-passport claim
PASS for the published snapshot components that are actually hashed
```

Item hash ≠ Legal Passport. Raw upload bytes are outside `document_hash`. See `docs/PASSPORT_INTEGRITY_MODEL.md`.

---

## E. Can the same evidence produce the same hash independently?

```text
PASS
```

Independent reconstruction is specified in `docs/EVIDENCE_CANONICALIZATION_SPEC.md`. Golden tests do not call `hash_evidence_item` to generate expected digests.

---

## F. Can tampering be reliably detected?

```text
PASS
```

for hashed snapshot fields and for anchored live items vs chain.

```text
FAIL
```

for excluded operational fields, same-text different files, and a consistent Firestore rewrite of hashes when no chain root exists.

---

## G. Suitable as a blockchain commitment?

**Per-item:**

```text
YES
```

Python v1 digest, already on Sepolia. Do not change the format.

**Passport-root:**

```text
IMPLEMENTED LOCALLY
```

(The **additive** anchor of `metadata.passport_hash` is implemented and locally
verified after fail-closed claimed-input verification. It does not change the
item hash. Client JS number serialization remains a display-layer caveat; chain
VERIFY is Python. Sepolia deployment and live production validation are still
pending.)

---

## Verdict

```text
ITEM-LEVEL: READY

PASSPORT-ROOT IMPLEMENTATION: COMPLETE
LOCAL EVM VERIFICATION: COMPLETE
DEPLOYMENT SCRIPT/SAFETY VERIFICATION: COMPLETE
SEPOLIA DEPLOYMENT: NOT YET EXECUTED
LIVE TRANSACTIONS: NONE
LIVE CHROMIUM E2E: NOT YET COMPLETED
```

The implementation is ready to proceed to a human-controlled Sepolia
deployment. Do not call `registerProof`, change `LexProofRegistry`, or change
canonicalization v1. Future production validation remains pending deployment
and live E2E execution.

Still required before production passport-root validation:

1. Sepolia deployment of the dedicated `LexProofPassportRegistry` address.
2. Live Chromium E2E, including the positive anchor and persistence flow.
3. Explicit `canonicalization_version` on any future incompatible encoding.

**Do not implement those Ethereum changes here.**
