# LexProof Legal Passport Integrity Model

**Date:** 2026-09-18  
**Canonicalization:** v1 as specified in `docs/EVIDENCE_CANONICALIZATION_SPEC.md`.  
**Anchoring:** per-item hashes are on Sepolia today. Passport-root Ethereum anchoring is **not** implemented.

---

## Published passport = immutable snapshot

```text
CREATE
  → hashes
  → metadata.passport_hash
  → metadata.verification_snapshot
  → Firestore
```

Verification prefers `verification_snapshot` captured at publish. Evidence added after publication (Ethereum anchor bookkeeping, counterparty countersignatures) is **intentionally excluded** from the published package hash when `snapshot.evidence_items` is present.

Product semantics:

```text
published Legal Passport = immutable snapshot of the assessment at creation
```

Do not fold live post-publish evidence into `evidence_hash` automatically.

---

## Passport root (implemented additive chain commitment; Sepolia pending)

```text
document_hash
     +
policy_hash
     +
analysis_hash
     +
evidence_hash
     ↓
compute_passport_hash()
     ↓
metadata.passport_hash
```

`passport_hash_verified` only proves those **stored** four fingerprints still bind to `metadata.passport_hash`. It does **not** by itself prove snapshot bytes are unchanged. Component recomputation (`document_status` / `policy_status` / `analysis_status` / `evidence_status`) must also be `PASS` (or `UNVERIFIABLE` for unclaimed legacy fields).

The implemented on-chain commitment for the Legal Passport claim is:

```text
metadata.passport_hash
```

Existing per-item Sepolia anchors remain valid and separate.

---

## Field classification

| Field | Classification | In passport_hash? | Notes |
|---|---|---|---|
| Extracted original text + normalized text | **committed** via `document_hash` | yes (as document_hash) | Not raw file bytes |
| Policy id/version/content | **committed** via `policy_hash` | yes | |
| `analysis_result` dict | **committed** via `analysis_hash` | yes | Includes findings, `risk_score`, `compliance_score` inside the analysis |
| Publish-time evidence items (`EVIDENCE_HASH_FIELDS`) | **committed** via `evidence_hash` | yes | Snapshot list, including `[]` |
| `metadata.passport_hash` | **committed** root | n/a (is the root) | Hash of the four hashes + algorithm label |
| `metadata.verification_snapshot` | **inputs** to recompute, not hashed as a blob | no | Must match the four hashes when claimed |
| `metadata.original_document_hash` / `normalized_document_hash` | **derived** extras | no | Duplicate of parts of `hash_document` |
| Passport-row `risk_score` / `compliance_score` | **derived** from analysis | no directly | Committed if present in `analysis_result` and scores evidence `content` |
| `contract_id` / `contract_version` | **operational identity** | no | Links the passport; not in the four hashes |
| `created_by` / `owner_id` | **operational metadata** | no | Authorization, not assessment content |
| `created_at` | **operational metadata** | no | Used as publish cutoff for live evidence fallback |
| `status` | **intentionally mutable** | no | pending / created / revoked / expired |
| `audit_events` | **operational metadata** | no | Append-only trail, not in root |
| `ai_analysis_duration_ms` | **operational metadata** | no | |
| Raw uploaded file bytes | **not committed** | no | Two files with the same extracted text share `document_hash` |
| Live evidence after publish | **intentionally mutable** relative to passport root | no | Item-level Ethereum hash still covers each live record if anchored |

---

## Verification statuses

| Status | Meaning | Overall `verified` |
|---|---|---|
| `PASS` | Claimed or live-fallback input was hashed and matched the stored fingerprint | allowed |
| `FAIL` | Claimed input missing/unusable, or digest ≠ stored hash | **false** |
| `UNVERIFIABLE` | Snapshot does not claim this component (legacy / repaired evidence-only) | allowed if nothing is `FAIL` |

`*_verified` booleans are `true` only for `PASS`. They are **not** `true` for `UNVERIFIABLE`.

---

## Raw document bytes (product decision)

Current claim is over **extracted text**, not the upload blob:

```text
Two different files
        ↓
same extracted text
        ↓
same document_hash
```

That is acceptable for the current LexProof assessment claim (legal analysis of contract **text**). It is **not** a file-integrity / malware / PDF-swap guarantee. Treat file-byte hashing as a separate future commitment, not a silent change to v1 `document_hash`.

---

## Future `canonicalization_version`

Existing persisted hashes and Sepolia item anchors are v1. If numbers, Unicode, or field sets ever change, store:

```text
canonicalization_version
```

on new passports/anchors and keep v1 verifiers for old records. Do not rewrite historical hashes.
