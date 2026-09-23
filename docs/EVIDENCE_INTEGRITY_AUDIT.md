# LexProof Evidence Integrity Audit

**Date:** 2026-09-18  
**Scope:** Read of the current hashing, canonicalization, passport, evidence, Firestore, and Ethereum code. Production hash format was not redesigned. One verification fail-open defect was fixed after it was proven (see §7 and §12).  
**Regression:** backend `916 passed / 1 skipped` (was 893 + new integrity matrix). Playwright suite still has 11 tests; this session could not launch Chromium in the agent sandbox (`chrome-headless-shell` missing). Re-run `npx playwright test --reporter=line` locally to confirm the 11/0 baseline.  
**Question:** If someone changes the evidence after LexProof created the Legal Passport, can LexProof reliably detect that change?

**Short answer:** Yes for fields inside the published hash boundary when CREATE and VERIFY see the same Python object graph. No for fields excluded from the hash, for live post-publish evidence while a snapshot exists, for raw upload bytes that are not in `document_content`, and (before the §12 fix) for a published snapshot whose `evidence_items` list was replaced with `[]`.

---

## 1. Hash algorithm

Verified in `backend/app/lexproof/domains/passport/utils/hashing.py` (`compute_sha256_hash`):

```text
SHA-256
digest format: lowercase hexadecimal, 64 characters
encoding of text/JSON: UTF-8
salt / prefix / version byte: none
library: Python hashlib.sha256
```

The same function is used for document, policy, analysis, per-item evidence, evidence-package, and passport-root hashes. Comparison is exact string equality (`verify_hash_consistency` / `==`). Ethereum stores the same digest as 32 bytes (`bytes.fromhex(computed_hash)`).

There is no Merkle tree on the live CREATE/VERIFY path. `backend/scripts/create_merkle_batch_demo_anchor.py` is an explicit demo/mock.

---

## 2. Canonicalization

### 2.1 Bytes that are hashed

For `dict` / `list` values:

```text
json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
```

Default JSON separators are `(", ", ": ")` (space after `:` and `,`). Unicode is not NFC/NFD-normalized. Arrays are not sorted. Whitespace inside string values is preserved. Python `int` `95` and `float` `95.0` serialize differently (`95` vs `95.0`). `null` is JSON `null`. Booleans are `true` / `false`.

For `str` values (original document text when hashed alone): UTF-8 bytes of the string, no JSON wrapping.

For `bytes`: hashed as-is.

Any other top-level type falls through to `str(data)` then UTF-8. Nested non-JSON types inside a dict raise `ValueError` from `json.dumps`.

### 2.2 Evidence-item field boundary

`canonicalize_evidence_item` copies only `EVIDENCE_HASH_FIELDS` via `.get()` (missing → `None`):

| Included | Excluded |
|---|---|
| `evidence_id` | `created_at` |
| `passport_id` | `verified_at` |
| `evidence_type` | `hash` |
| `title` | `owner_id` |
| `description` | `contract_id` |
| `content` | `contract_version` |
| `content_type` | any other operational field |
| `risk_impact` | |
| `compliance_impact` | |
| `evidence_status` | |
| `contract_reference` | |
| `policy_reference` | |
| `analysis_reference` | |
| `source` | |
| `source_id` | |
| `metadata` | |

### 2.3 Representative canonical bytes

Independent `json.dumps(..., sort_keys=True, ensure_ascii=False)` of the golden evidence item used in tests:

```text
{"analysis_reference": "", "compliance_impact": 10, "content": "canonical evidence body", "content_type": "text/plain", "contract_reference": "", "description": "Test evidence", "evidence_id": "golden-1", "evidence_status": "valid", "evidence_type": "clause", "metadata": {"amount": 95, "status": "active"}, "passport_id": "passport-golden", "policy_reference": "", "risk_impact": 95, "source": "test", "source_id": "src-1", "title": "Test evidence"}
```

SHA-256 of those UTF-8 bytes:

```text
cca985e44ad52a9909656d6b221ed0690c5ba5a9f443038ea0144fd15bf2cec6
```

Frontend `serializeCanonicalEvidence` uses the same field list and the same JSON spacing. JavaScript `Number` cannot distinguish `95` from `95.0`; Python `json.dumps` can. Server CREATE/VERIFY is Python. Client-side `hashEvidenceItem` in `frontend/lib/evidenceHash.ts` is a parallel implementation used by `AnchorProofButton` against the chain hash.

### 2.4 Document / policy / analysis / passport envelopes

`hash_document` hashes:

```json
{"hash_algorithm": "sha256", "normalized": "<normalized or empty>", "original": "<extracted text>"}
```

`hash_policy_version` hashes `policy_id`, `version`, `content`, `metadata`.

`hash_ai_analysis` hashes `analysis_type`, `model`, `timestamp`, `result` (the analysis dict). Passport CREATE passes `analysis_type="risk_and_compliance"` and empty model/timestamp.

`hash_evidence_package` hashes:

```json
{"evidence_count": N, "evidence_items": [<canonical items sorted by evidence_id>]}
```

`compute_passport_hash` hashes the four stored component hashes plus `"passport_hash_algorithm": "sha256"`.

---

## 3. CREATE path

Production contract analysis (the path that creates a Legal Passport and evidence records):

```text
backend/app/lexproof/services/version_analysis.py
    VersionAnalysisService.analyze_version
        → PassportService.create_passport
            → analysis_engine (Vertex Gemini)
            → hashing.hash_document(document_content, normalized_document)
            → hashing.hash_policy_version(...)
            → hashing.hash_ai_analysis(analysis_result, analysis_type="risk_and_compliance")
            → PassportService._create_evidence_items
                → json.dumps(finding, sort_keys=True) stored in content
                → finding.risk_impact / compliance_impact copied as-is (JSON int or float)
                → PassportService._compute_evidence_item_hash
                    → hashing.hash_evidence_item
                        → canonicalize_evidence_item
                        → compute_sha256_hash
            → hashing.hash_evidence_package(evidence_items)
            → hashing.compute_passport_hash(document_hash, policy_hash, analysis_hash, evidence_hash)
            → Firestore legal_passports.set (model_dump JSON + owner_id)
            → metadata.verification_snapshot written with document, policy, analysis, evidence_items
        → evidence_records.set(evidence_id, evidence_item)  # raw dict from _create_evidence_items
        → optional EthereumAnchorService.anchor_evidence
            → hash_evidence_item(firestore evidence dict)
            → BlockchainService.anchor_evidence(id, bytes.fromhex(hash))
```

Alternate CREATE (manual evidence API):

```text
domains/passport/api/router.py  create_evidence_item
    → EvidenceService.create_evidence_item
        → EvidenceItem (Pydantic; risk_impact is float)
        → hash_evidence_item(evidence_item.dict())
        → Firestore evidence_records.set(model_dump(mode="json"))
```

Passport HTTP CREATE:

```text
domains/passport/api/router.py  create_passport
    → PassportService.create_passport
```

### CREATE hash flow

```text
input (document text, policy text, analysis dict, finding dicts)
 ↓
evidence items built as Python dicts (content = JSON string of the finding)
 ↓
canonicalize_evidence_item (field subset; missing → None)
 ↓
json.dumps(sort_keys=True, ensure_ascii=False)
 ↓
UTF-8 bytes
 ↓
SHA-256 hex
 ↓
stored on the item as hash
 ↓
package hash stored as passport.evidence_hash
 ↓
passport_hash stored as metadata.passport_hash
 ↓
optional per-item hash anchored on Ethereum
```

---

## 4. VERIFY path

### 4.1 Legal Passport integrity (server, never trusts client hashes)

```text
POST /api/passports/{passport_id}/verify
    domains/passport/api/router.py  verify_passport_integrity_endpoint
        → load passport (in-memory or Firestore legal_passports)
        → load evidence (in-memory or evidence_records.stream)
        → integrity.verify_passport_integrity(passport_doc, evidence_items)
            → _recompute_document_hash
                snapshot.document_content + normalized_document
                → hash_document
            → _recompute_policy_hash
                snapshot.policy_content (key must be present)
                → hash_policy_version
            → _recompute_analysis_hash
                snapshot.analysis_result
                → hash_ai_analysis
            → _recompute_evidence_hash
                prefer snapshot.evidence_items (including [])
                else evidence_as_of_publish(live items)
                → hash_evidence_package
            → compute_passport_hash(stored document/policy/analysis/evidence hashes)
            → exact == vs metadata.passport_hash
```

### VERIFY hash flow

```text
stored passport + verification_snapshot (preferred) or live publish-time evidence
 ↓
same canonicalize + json.dumps + SHA-256 as CREATE
 ↓
computed_hash
 ↓
== stored document_hash / policy_hash / analysis_hash / evidence_hash
 ↓
passport_hash recomputed from the *stored* component hashes (not the recomputed ones)
 ↓
PASS only if every available component check and the passport_hash check pass
```

`passport_hash_verified` binds the four stored fingerprints to each other. Tampering a snapshot while leaving stored hashes unchanged fails the component check and still reports `passport_hash_verified: true`. Overall `verified` is false.

### 4.2 Per-item Ethereum VERIFY

```text
EthereumAnchorService.verify_evidence
    → evidence_repository.get(evidence_id)     # Firestore dict
    → hash_evidence_item(evidence)             # same canonicalize as CREATE
    → BlockchainService.verify_evidence(id, bytes.fromhex(computed_hash))
        → VERIFIED | TAMPERED | ANCHOR_NOT_FOUND
```

Public `GET /api/verify/{evidence_id}` uses the same service. `frontend/app/public-verify/page.tsx` also reads Sepolia directly.

---

## 5. Comparison

| Check | Stored | Computed | Operator |
|---|---|---|---|
| Evidence item | `evidence.hash` / on-chain 32 bytes | `hash_evidence_item(record)` | `==` / bytes equality |
| Evidence package | `passport.evidence_hash` | `hash_evidence_package(snapshot or live-as-of-publish)` | `==` |
| Document | `passport.document_hash` | `hash_document(snapshot original, snapshot normalized)` | `==` |
| Policy | `passport.policy_hash` | `hash_policy_version(...)` | `==` |
| Analysis | `passport.analysis_hash` | `hash_ai_analysis(snapshot.analysis_result, ...)` | `==` |
| Passport root | `metadata.passport_hash` | `compute_passport_hash(stored four hashes)` | `==` |

If a component cannot be recomputed (legacy passport with no snapshot input), that component currently fail-opens (`else True`) except for evidence when `snapshot.evidence_items` is present, including as an empty list.

CREATE and VERIFY hash the same canonical representation **when they hash the same Python types and the same snapshot/live source**. They diverge if `95` (int, typical AI JSON / passport `_create_evidence_items`) is later rehashed as `95.0` (Pydantic `float` on `EvidenceItem`).

---

## 6. Integrity boundary (hash scope)

A Legal Passport conceptually contains more than one commitment:

```text
Legal Passport
├── document_hash          ← extracted original text + normalized text (+ algorithm label)
├── policy_hash            ← policy id/version/content
├── analysis_hash          ← full analysis_result dict
├── evidence_hash          ← canonical package of evidence items at publish
├── metadata.passport_hash ← hash of the four hashes above
├── metadata.original_document_hash / normalized_document_hash  (separate, not in passport_hash)
├── metadata.verification_snapshot  (inputs used to recompute the four hashes)
├── risk_score / compliance_score on the passport row (NOT in passport_hash except via analysis/evidence content)
└── audit_events, created_at, created_by, status  (NOT in passport_hash)

Per evidence item (what Ethereum currently anchors)
├── EVIDENCE_HASH_FIELDS including content JSON and metadata
└── NOT owner_id, contract_id, timestamps, stored hash field
```

**Protected by `hash_evidence_item` / package hash:** finding title/description, `content` (JSON of the finding, including quote/recommendation when present there), `risk_impact`, `compliance_impact`, `metadata` (severity, quote, citations, nested objects/arrays), ids, type, status, references.

**Not protected by those hashes:**

- Raw uploaded file bytes (only extracted `document_content` / `normalized_document`).
- Passport-row `risk_score` / `compliance_score` except as copied into analysis snapshot and the scores evidence item `content`.
- `owner_id`, `contract_id`, `created_at`, `verified_at`.
- Live evidence appended after publish, while `verification_snapshot.evidence_items` exists (intentional: anchoring / countersignatures).
- Firestore rewrite of snapshot **and** stored hashes **and** `passport_hash` together, unless an external anchor exists.

**Can a user modify material evidence without changing `evidence_hash`?**

| Change | Detected by passport `evidence_hash`? |
|---|---|
| Snapshot finding text / `risk_impact` 95 → 96 | Yes |
| Restore 96 → 95 | Hash matches again |
| Live evidence after publish (snapshot present) | No (by design) |
| Same live item if Ethereum-anchored | Yes, via item hash vs chain |
| `owner_id` / `created_at` | No |
| Upload bytes with identical extracted text | No |
| Emptying `snapshot.evidence_items` to `[]` | Yes, after the §12 fix (was No) |

---

## 7. Weaknesses (code/test supported)

1. **Fail-open when a component cannot be recomputed.** `verify_passport_integrity` uses `else True` if document/policy/analysis/evidence recompute returns `None`. Legacy tests (`test_verify_passport_integrity_deterministic_recomputation`, repaired snapshots that only contain `evidence_items`) depend on this. A Firestore editor who deletes `document_content` from a snapshot can skip the document check while keeping stored hashes.

2. **Empty snapshot list used to fail-open.** `_recompute_evidence_hash` treated a falsy `[]` as “cannot recompute” and then verified true. An attacker could replace published `evidence_items` with `[]` and still pass. **Fixed** in `integrity.py`: a present `evidence_items` key, including `[]`, is hashed. Regression: `test_emptied_snapshot_evidence_items_fails`.

3. **`95` vs `95.0`.** Python `json.dumps` emits different bytes. Passport CREATE keeps AI JSON types (often `int`). `EvidenceService` / `EvidenceItem.risk_impact: float` emits `95.0`. Same legal amount can produce two hashes. Not changed: altering number canonicalization would invalidate existing stored/on-chain digests.

4. **Python vs TypeScript serializers.** `frontend/lib/evidenceHash.ts` serializes JS numbers with `toString()`-style rules, so `95` and `95.0` match in the browser and can disagree with a Python float digest. Server VERIFY and Ethereum VERIFY use Python only.

5. **`passport_hash` is a hash of stored hashes, not of snapshot bytes.** Consistent rewrite of the four hashes plus `passport_hash` verifies locally. External detection requires the Ethereum item anchor (or a future passport-root anchor).

6. **Package hash does not cover the source file.** `hash_document` covers extracted/normalized text stored in the snapshot, not GCS/upload bytes.

7. **Scores evidence `content` uses `json.dumps(..., indent=2)`.** The stored string is hashed; VERIFY of that stored string is stable. Regenerating the scores blob with different indent would change the item hash.

8. **No Unicode normalization.** NFC `café` and NFD `cafe\u0301` are different evidence.

9. **Metadata array order is significant.** Lists are not sorted.

10. **Merkle batch anchoring is demo-only** (`is_mock: true`). Not a production VERIFY path.

---

## 8. Passport fields actually stored

From `ContractPassport` and `create_passport` metadata (not invented):

- `passport_id`, `contract_id`, `contract_version`
- `document_hash`, `policy_hash`, `analysis_hash`, `evidence_hash`
- `risk_score`, `compliance_score`, `policy_version`, `evidence_count`
- `created_at`, `created_by`, `status`, `ai_analysis_duration_ms`, `audit_events`
- `metadata.passport_hash`
- `metadata.original_document_hash`, `metadata.normalized_document_hash`
- `metadata.verification_snapshot` (`document_content`, `normalized_document`, `policy_content`, `policy_id`, `policy_version`, `analysis_result`, `analysis_type`, `evidence_items`)

Anchor records (`evidence_anchors`) store `evidence_hash`, `transaction_hash`, `block_number`, `blockchain_network`, `contract_address`, `anchored_at`, optional demo Merkle fields.

---

## 9. Tests added

`backend/tests/lexproof/passport/test_evidence_integrity_matrix.py`

Golden expected digests are independent `hashlib.sha256(json.dumps(...).encode("utf-8"))` constants, not copied from `hash_evidence_item` at runtime.

---

## 12. Production change made after the audit

**File:** `backend/app/lexproof/domains/passport/integrity.py`  
**Change:** If `verification_snapshot.evidence_items` is present, including `[]`, always run `hash_evidence_package`. Do not return `None` (fail-open) for an empty list.  
**Not changed:** SHA-256, canonical JSON, `EVIDENCE_HASH_FIELDS`, stored hash hex format, Ethereum contract.  
**Compatibility:** Passports without `evidence_items` on the snapshot still fall back to live `evidence_as_of_publish`. Empty-snapshot `{}` and missing snapshot behavior for document/policy/analysis is unchanged.
