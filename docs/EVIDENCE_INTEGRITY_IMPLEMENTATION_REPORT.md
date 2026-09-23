# LexProof Evidence Integrity Implementation Report

**Date:** 2026-09-18  
**Question:** Can LexProof now determine, without silently accepting missing claimed evidence, whether the published Legal Passport’s committed components are still exactly what they were when the passport was created?

**Answer:** Yes for components the snapshot **claims**. Unclaimed legacy/repaired fields are `UNVERIFIABLE`, not `PASS`. Per-item Sepolia hashes were not changed. Passport-root Ethereum anchoring was not implemented.

---

## 1. Original weaknesses

From `docs/EVIDENCE_INTEGRITY_AUDIT.md`, re-checked against current code:

1. Document/policy/analysis VERIFY used `else True` when recompute returned `None` (fail-open).
2. Empty `verification_snapshot.evidence_items` `[]` used to fail-open (already fixed; preserved).
3. Snapshot key `evidence_items: null` still fell through to live evidence (fail-open).
4. `95` vs `95.0` are different Python canonical bytes (defined v1 behavior).
5. JavaScript `Number` cannot distinguish `95` / `95.0`; browser local hash can disagree with Python float digests.
6. `passport_hash` binds stored hashes, not snapshot bytes by itself.
7. `document_hash` covers extracted text, not raw upload bytes.
8. Live post-publish evidence is outside the published package hash when a snapshot list exists (intentional).
9. Merkle batch path is demo-only.

---

## 2. Fixes made

```text
File: backend/app/lexproof/domains/passport/integrity.py
Defect: claimed snapshot inputs that could not be recomputed were treated as verified (else True)
Fix: PASS / FAIL / UNVERIFIABLE. Claimed missing/unusable → FAIL. Unclaimed → UNVERIFIABLE. Overall verified is false iff any status is FAIL.
Backward compatibility: repaired evidence-only snapshots and passports with no snapshot still verify overall if stored hashes bind and any live/snapshot evidence that can be hashed matches. Boolean *_verified is true only for PASS.
Regression test: tests/lexproof/passport/test_snapshot_claim_verification.py
```

```text
File: backend/app/lexproof/domains/passport/integrity.py
Defect: evidence_items: null used live fallback
Fix: key present and not a list → FAIL (empty list still hashed)
Backward compatibility: missing key still uses evidence_as_of_publish
Regression test: test_claimed_evidence_items_null_fails_instead_of_live_fallback
```

```text
File: frontend/app/(authenticated)/legal-passport/page.tsx
Defect: false shown as “fingerprint mismatch”
Fix: render UNVERIFIABLE as “not claimed in snapshot”
Backward compatibility: optional status fields; booleans unchanged for PASS/FAIL
Regression test: TypeScript compile of the page types
```

Empty-list hashing from the prior audit was **not** undone.

Not changed: `hashing.py`, item hash format, smart contract, Firestore hash rewrite, number/Unicode canonicalization.

---

## 3. Verification semantics

| Status | Meaning | `*_verified` boolean | Overall `verified` |
|---|---|---|---|
| `PASS` | Input hashed and matched stored fingerprint | `true` | allowed |
| `FAIL` | Claimed missing/unusable, or digest mismatch | `false` | **false** |
| `UNVERIFIABLE` | Snapshot does not claim this component | `false` | allowed if nothing is `FAIL` |

UNVERIFIABLE is not collapsed into PASS.

`passport_hash_verified` / `passport_hash_status` bind the four **stored** hashes to `metadata.passport_hash`. Snapshot tampering can FAIL a component while the stored root still PASSes.

---

## 4. Canonicalization

See `docs/EVIDENCE_CANONICALIZATION_SPEC.md` (v1, current behavior):

```text
SHA-256
UTF-8
json.dumps(..., sort_keys=True, ensure_ascii=False)
arrays order-sensitive
strings whitespace-preserving
no Unicode NFC/NFD
95 != 95.0
missing field == null for EVIDENCE_HASH_FIELDS
booleans true/false
```

---

## 5. Hash scope

```text
document   → extracted original + normalized text (+ algorithm label)
policy     → policy id/version/content
analysis   → analysis_result dict
evidence   → canonical publish-time items (EVIDENCE_HASH_FIELDS)
passport root → hash of the four stored component hashes
```

Not in the root: owner, timestamps, status, audit events, contract identity, raw file bytes, live post-publish evidence. Details: `docs/PASSPORT_INTEGRITY_MODEL.md`.

---

## 6. Tamper matrix

| Case | Result |
|---|---|
| 95 → 96 | FAIL (detected) |
| 96 → 95 | PASS (restored) |
| material text | FAIL |
| nested value | FAIL |
| list value / list order | FAIL |
| dictionary key order | PASS |
| claimed snapshot input missing/unusable | FAIL |
| empty evidence snapshot `[]` | FAIL vs stored nonempty package |
| `evidence_items: null` (key present) | FAIL |
| evidence-only repaired snapshot | overall PASS; document/policy/analysis UNVERIFIABLE |
| no verification snapshot | overall PASS if stored root binds; components UNVERIFIABLE (live evidence still checked if present) |
| stored document/policy/analysis/evidence hash change | FAIL component + FAIL passport root |
| stored `metadata.passport_hash` change | FAIL root only; components can still PASS |
| snapshot text change, stored hashes unchanged | FAIL component; passport root PASS; overall FAIL |

---

## 7. Blockchain readiness

```text
ITEM-LEVEL: READY

PASSPORT-ROOT: REQUIRES CHANGE
```

Item anchors stay on `hash_evidence_item` v1. Future passport-root anchoring should add a commitment of `metadata.passport_hash` without replacing item anchors. Not implemented in this task.

---

## 8. Remaining risks

| Risk | Level | Evidence |
|---|---|---|
| Consistent Firestore rewrite of snapshot + four hashes + `passport_hash` with no chain root | **HIGH** | Local VERIFY would PASS; no passport-root anchor yet |
| Raw file swap with identical extracted text | **MEDIUM** | `hash_document` ignores upload bytes; recorded as product decision |
| Browser local hash vs Python float `95.0` | **MEDIUM** | `serializeCanonicalValue` emits `95`; chain VERIFY is Python |
| Passport-row scores / owner / status editable without root change | **LOW** | Classified operational/derived; analysis snapshot still committed |
| Merkle-batch UI records | **LOW** | Explicit `is_mock` demo |

No CRITICAL issue remains in claimed-snapshot fail-open after this change.

---

## Regression

```text
Backend: 929 passed / 1 skipped  (integrity audit was 916; + snapshot-claim tests)
Frontend: tsc --noEmit passed; vitest lib/evidenceHash.test.ts 13 passed
Playwright: executed; Chromium did not launch in this environment
  (chrome-headless-shell missing). 11 specs still present; not claimed as passed.
```
