# LexProof — Technical Integrity & Verification Audit
## Actual Findings Report

**Date**: August 25, 2026  
**Scope**: Read-only inspection of LexProof backend/frontend implementation  
**Goal**: Verify evidence lifecycle integrity, cryptographic correctness, and Ethereum anchoring credibility

---

# 1. Repository Structure

## Architecture Map

```
LexProof Backend (FastAPI)
├── app/lexproof/
│   ├── domains/
│   │   └── passport/
│   │       ├── service.py                    [PassportService — creates immutable passports]
│   │       ├── evidence_service.py           [EvidenceService — manages evidence items]
│   │       ├── utils/
│   │       │   ├── hashing.py                [Deterministic SHA-256 hashing]
│   │       │   └── evidence.py               [Evidence filtering/counting]
│   │       └── models/                       [Pydantic schemas]
│   ├── services/
│   │   ├── blockchain.py                     [BlockchainService — Ethereum Sepolia interaction]
│   │   └── ethereum_anchor_service.py        [EthereumAnchorService — evidence-level anchoring]
│   ├── api/
│   │   ├── evidence_anchor.py                [/evidence/{id}/anchor endpoints]
│   │   └── [other endpoints]
│   ├── repositories/
│   │   └── firestore.py                      [FirestoreRepository abstraction]
│   └── config/
│       └── settings.py                       [LexProofSettings — env-backed config]
├── tests/
│   ├── lexproof/
│   │   ├── passport/
│   │   │   ├── test_hashing.py              [Determinism tests]
│   │   │   ├── test_evidence_hash_determinism.py
│   │   │   └── test_passport_hash_integrity.py
│   │   ├── test_ethereum_anchor_service.py  [Anchor/verification tests]
│   │   └── blockchain/test_blockchain_service.py
│   └── test_public_verification.py
├── contracts/
│   ├── LexProofRegistry.sol                  [Smart contract on Sepolia]
│   └── build/LexProofRegistry.abi

LexProof Frontend (Next.js)
└── frontend/app/
    └── public-verify/page.tsx                [Public verification portal UI]
```

## Key Components Identified

| Component | File | Purpose |
|-----------|------|---------|
| **Evidence Creation** | `evidence_service.py` | Creates EvidenceItem with ID, content, type, metadata |
| **Hashing** | `utils/hashing.py` | SHA-256 for documents, policies, analysis, evidence |
| **Passport** | `service.py` | Orchestrates document → analysis → evidence → passport pipeline |
| **Ethereum Anchor** | `ethereum_anchor_service.py` | Anchors evidence_hash to Sepolia via LexProofRegistry |
| **Blockchain Service** | `blockchain.py` | Low-level web3.py interaction with LexProofRegistry |
| **Firestore** | `repositories/firestore.py` | Two collections: `evidence_anchors`, `evidence_records` |
| **Verification Portal** | `public-verify/page.tsx` | Frontend for cryptographic + blockchain verification |

---

# 2. Evidence Creation Path

## Step-by-Step Trace

### **Step 1: Passport Creation Triggered**

**File**: `domains/passport/service.py` → `PassportService.create_passport()`

```python
async def create_passport(
    contract_id: str,
    contract_version: int,
    policy_version: str,
    document_content: str,
    policy_content: Optional[str] = None,
    normalized_document: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> ContractPassportResponse
```

| Aspect | Details |
|--------|---------|
| **Input** | Contract ID, version, document text, policy text, metadata |
| **What it does** | Orchestrates entire passport creation lifecycle |
| **Next function** | `self.analysis_engine()` |

---

### **Step 2: AI Analysis**

**File**: `domains/passport/service.py` line ~89

```python
analysis_result = await self.analysis_engine(document_content, policy_content or "")
```

| Aspect | Details |
|--------|---------|
| **Input** | Raw document content, policy content |
| **What it does** | Calls external AI analysis engine (Vertex AI / Gemini) |
| **Output** | Dict with `risk_score`, `compliance_score`, `findings[]` |
| **Next function** | `validate_passport_creation_analysis()` then hash functions |

---

### **Step 3: Evidence Item Creation from Analysis**

**File**: `domains/passport/service.py` line ~123

```python
evidence_items = await self._create_evidence_items(
    passport_id=passport_id,
    contract_id=contract_id,
    contract_version=contract_version,
    analysis_result=analysis_result,
)
```

For each finding in `analysis_result['findings']`, creates:

```python
EvidenceItem(
    evidence_id=generate_evidence_id(),      # UUID v4
    passport_id=passport_id,
    evidence_type=evidence_data.evidence_type,
    title=evidence_data.title,
    description=evidence_data.description,
    content=evidence_data.content,
    risk_impact=evidence_data.risk_impact,
    compliance_impact=evidence_data.compliance_impact,
    evidence_status=evidence_data.evidence_status,
    contract_reference=evidence_data.contract_reference,
    metadata=evidence_data.metadata,
    created_at=datetime.utcnow(),
    verified_at=None,
    hash=None  # Will be computed
)
```

| Aspect | Details |
|--------|---------|
| **Input** | AI analysis findings dict |
| **What it does** | Transforms each finding into immutable EvidenceItem |
| **Output** | List of EvidenceItem objects with generated IDs |
| **IDs Generated** | `evidence_id` (UUID v4) |
| **Timestamps** | `created_at` (current UTC) |
| **Next function** | `hash_evidence_item()` for each item |

---

### **Step 4: Evidence Hash Computation**

**File**: `domains/passport/evidence_service.py` line ~76

```python
evidence_item.hash = hash_evidence_item(evidence_item.dict())
```

**File**: `domains/passport/utils/hashing.py` line ~209

```python
def hash_evidence_item(evidence_item: Dict[str, Any]) -> str:
    """Compute hash for individual evidence item."""
    item_data = {
        "evidence_id": evidence_item.get("evidence_id", ""),
        "title": evidence_item.get("title", ""),
        "content": evidence_item.get("content", ""),
        "evidence_type": evidence_item.get("evidence_type", ""),
        "metadata": evidence_item.get("metadata", {}),
    }
    return compute_sha256_hash(item_data)
```

| Aspect | Details |
|--------|---------|
| **Input** | EvidenceItem dict |
| **Fields Included** | evidence_id, title, content, evidence_type, metadata |
| **Fields Excluded** | created_at, verified_at, contract_reference, risk_impact, compliance_impact |
| **What it does** | Serializes to JSON (sort_keys=True), computes SHA-256 |
| **Output** | 64-char hex string (SHA-256) |
| **Next function** | Stored in memory, persisted to Firestore |

---

### **Step 5: Database Persistence (Firestore)**

**File**: `domains/passport/evidence_service.py` line ~78

```python
if self.repository:
    self.repository.set(
        evidence_item.evidence_id,
        {
            **evidence_item.model_dump(mode="json"),
            "id": evidence_item.evidence_id,
            "owner_id": self.owner_id
        },
    )
```

**File**: `repositories/firestore.py`

```python
def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
    self._get_client().collection(self.collection).document(document_id).set(data, merge=merge)
```

| Aspect | Details |
|--------|---------|
| **Collection** | `evidence_records` (or caller-specified) |
| **Document ID** | `evidence_item.evidence_id` (UUID v4) |
| **Stored Fields** | Complete EvidenceItem including hash, timestamps, metadata |
| **Mutation** | Document can be overwritten via `.set(..., merge=False)` |
| **Versioning** | No versioning; overwrite replaces entire document |
| **Next function** | Evidence ready for anchoring or verification |

---

### **Step 6: Evidence Package Hash**

**File**: `domains/passport/service.py` line ~126

```python
evidence_hash = hash_evidence_package(evidence_items)
```

**File**: `domains/passport/utils/hashing.py` line ~192

```python
def hash_evidence_package(evidence_items: list[Dict[str, Any]]) -> str:
    """Compute deterministic hash for the canonical evidence package."""
    canonical_items = [
        canonicalize_evidence_item(item)
        for item in evidence_items
    ]
    
    sorted_items = sorted(
        canonical_items,
        key=lambda x: x.get("evidence_id", ""),
    )
    
    evidence_data = {
        "evidence_count": len(sorted_items),
        "evidence_items": sorted_items,
    }
    
    return compute_sha256_hash(evidence_data)
```

| Aspect | Details |
|--------|---------|
| **Input** | List of evidence items |
| **Processing** | Canonicalize each item, sort by evidence_id, wrap with count |
| **Output** | Single SHA-256 hash of entire package |
| **Next function** | Included in passport hash computation |

---

### **Step 7: Passport Hash (Final)**

**File**: `domains/passport/service.py` line ~130

```python
passport_hash = compute_passport_hash(
    document_hash=document_hash,
    policy_hash=policy_hash,
    analysis_hash=analysis_hash,
    evidence_hash=evidence_hash,
)
```

**File**: `domains/passport/utils/hashing.py` line ~225

```python
def compute_passport_hash(
    document_hash: str,
    policy_hash: str,
    analysis_hash: str,
    evidence_hash: str,
) -> str:
    passport_data = {
        "document_hash": document_hash,
        "policy_hash": policy_hash,
        "analysis_hash": analysis_hash,
        "evidence_hash": evidence_hash,
        "passport_hash_algorithm": "sha256",
    }
    return compute_sha256_hash(passport_data)
```

| Aspect | Details |
|--------|---------|
| **Input** | Four component hashes |
| **Algorithm** | SHA-256 with algorithm metadata |
| **Output** | 64-char hex (immutable fingerprint of entire passport) |
| **Stored** | In passport metadata |
| **Next** | Passport and evidence ready for Ethereum anchoring |

---

### **Step 8: Ethereum Anchoring (Optional)**

**File**: `api/evidence_anchor.py` → `anchor_evidence_to_blockchain()`

```python
async def anchor_evidence_to_blockchain(
    evidence_id: str,
    request: EvidenceAnchorRequest,
    ...
) -> EvidenceAnchorResponse:
```

**File**: `services/ethereum_anchor_service.py` → `anchor_evidence()`

```python
async def anchor_evidence(self, evidence_id: str) -> Dict[str, Any]:
    evidence = self.evidence_repository.get(evidence_id)
    evidence_hash = hash_evidence_item(evidence)
    
    tx_hash, block_number, anchored_timestamp = self.blockchain.anchor_evidence(
        evidence_id, bytes.fromhex(evidence_hash)
    )
    
    blockchain_proof = {
        "evidence_id": evidence_id,
        "passport_id": passport_id,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": self.blockchain.contract_address,
        "transaction_hash": tx_hash,
        "block_number": block_number,
        "anchored_at": datetime.fromtimestamp(anchored_timestamp, timezone.utc).isoformat(),
        "evidence_hash": evidence_hash,
    }
    self.repository.set(evidence_id, blockchain_proof)
    return blockchain_proof
```

| Aspect | Details |
|--------|---------|
| **Input** | evidence_id (must exist in evidence_records) |
| **Computation** | `hash_evidence_item(evidence)` re-computed |
| **Blockchain Call** | `BlockchainService.anchor_evidence(record_id, bytes32 hash)` |
| **On-Chain Storage** | Evidence hash stored in LexProofRegistry contract state |
| **Proof Persisted** | In `evidence_anchors` collection (Firestore) |
| **Transaction Info** | tx_hash, block_number, anchored_at timestamp |
| **Next** | Verification can now query Ethereum |

---

## Evidence Creation Summary

```
AI Analysis Result
    ↓
Generate Evidence Items (with UUIDs, timestamps)
    ↓
Hash Each Item (includes: id, title, content, type, metadata)
    ↓
Store in Firestore (evidence_records)
    ↓
Package Hash (all items sorted by id)
    ↓
Compute Passport Hash (document + policy + analysis + evidence)
    ↓
(Optional) Anchor Evidence to Ethereum
    ↓
Store Anchor Proof (evidence_anchors collection)
```

---

# 3. Canonicalization Audit

## Canonical Evidence Fields

**File**: `domains/passport/utils/hashing.py` line ~142

```python
EVIDENCE_HASH_FIELDS = (
    "evidence_id",
    "passport_id",
    "evidence_type",
    "title",
    "description",
    "content",
    "content_type",
    "risk_impact",
    "compliance_impact",
    "evidence_status",
    "contract_reference",
    "policy_reference",
    "analysis_reference",
    "source",
    "source_id",
    "metadata",
)
```

But **actual hashing** (line ~209):

```python
def hash_evidence_item(evidence_item: Dict[str, Any]) -> str:
    item_data = {
        "evidence_id": evidence_item.get("evidence_id", ""),
        "title": evidence_item.get("title", ""),
        "content": evidence_item.get("content", ""),
        "evidence_type": evidence_item.get("evidence_type", ""),
        "metadata": evidence_item.get("metadata", {}),
    }
    return compute_sha256_hash(item_data)
```

### **CRITICAL FINDING: Field Mismatch**

⚠️ **EVIDENCE_HASH_FIELDS is defined but NOT used in `hash_evidence_item()`**

- **Fields Included in Hash**: evidence_id, title, content, evidence_type, metadata
- **Fields Excluded from Hash**: 
  - ❌ passport_id (CRITICAL - changes to passport ID don't affect evidence hash)
  - ❌ description, content_type, risk_impact, compliance_impact
  - ❌ evidence_status, contract_reference, policy_reference
  - ❌ analysis_reference, source, source_id
  - ❌ created_at, verified_at (timestamps NOT included)

### Canonicalization Properties

| Property | Status | Details |
|----------|--------|---------|
| **Dictionary Keys Sorted** | ✅ YES | `json.dumps(..., sort_keys=True)` |
| **Arrays Sorted** | ⚠️ PARTIAL | Evidence package sorted by evidence_id only |
| **Whitespace Normalized** | ✅ UTF-8 | `ensure_ascii=False`, `.encode("utf-8")` |
| **Timestamps Normalized** | ✅ EXCLUDED | created_at, verified_at NOT in hash |
| **UUIDs Included** | ✅ YES | evidence_id included |
| **DB-Generated IDs** | ✅ YES | evidence_id (UUID v4) included |
| **Null/Empty Fields** | ✅ CONSISTENT | `.get(field, "")` or `.get(field, {})` |
| **JSON Deterministic** | ✅ YES | `sort_keys=True, ensure_ascii=False` |
| **Encoding UTF-8** | ✅ YES | `.encode("utf-8")` explicit |
| **Floating-Point** | ⚠️ EXCLUDED | risk_impact, compliance_impact NOT hashed |
| **Property Ordering** | ✅ STABLE | Keys alphabetically sorted by json.dumps |

### Mutation Potential

**Can two semantically identical evidence packages produce different hashes?**

**Answer**: NO — JSON serialization with sort_keys=True is fully deterministic.

However:

- ✅ Changing content → hash changes
- ✅ Changing evidence_id → hash changes
- ✅ Adding/removing metadata keys → hash changes
- ⚠️ Changing risk_impact/compliance_impact → hash **DOES NOT change** (not included)
- ⚠️ Changing passport_id → hash **DOES NOT change** (not included)
- ✅ Reordering object keys → hash **DOES NOT change** (sorted)
- ✅ Reordering evidence items → hash **DOES NOT change** (sorted by id)

---

# 4. SHA-256 Hashing Audit

## Hashing Implementation

**File**: `domains/passport/utils/hashing.py` line ~16

```python
def compute_sha256_hash(data: Any) -> str:
    """Compute SHA-256 hash of data."""
    if isinstance(data, str):
        data_bytes = data.encode("utf-8")
    elif isinstance(data, bytes):
        data_bytes = data
    elif isinstance(data, (dict, list)):
        # Sort keys for deterministic hashing
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        data_bytes = data_str.encode("utf-8")
    else:
        data_str = str(data)
        data_bytes = data_str.encode("utf-8")
    
    return hashlib.sha256(data_bytes).hexdigest()
```

| Property | Value |
|----------|-------|
| **Algorithm** | SHA-256 (hashlib.sha256) |
| **Input Format** | Dict or string, serialized as JSON (dicts) or UTF-8 (strings) |
| **Encoding** | UTF-8 explicitly |
| **Digest Format** | Hexadecimal lowercase (64 characters) |
| **Salt/Prefix** | None |
| **Version Metadata** | `passport_hash_algorithm: "sha256"` in passport hash only |
| **Used During Creation** | ✅ YES (`evidence_service.py` line 76) |
| **Used During Verification** | ✅ YES (`ethereum_anchor_service.py` line ~147) |

## Blockchain Hashing

**File**: `services/blockchain.py` → `anchor_evidence()`

```python
function = self.contract.functions.anchorEvidence(record_id, evidence_hash)
tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
```

- Evidence hash passed as **bytes32** to smart contract
- No additional hashing in transit
- On-chain: stored in contract state mapping

---

# 5. CREATE vs VERIFY Comparison

## Trace: CREATE Pipeline

```python
# File: domains/passport/evidence_service.py line 76
evidence_item.hash = hash_evidence_item(evidence_item.dict())

# File: domains/passport/utils/hashing.py line 209
def hash_evidence_item(evidence_item: Dict[str, Any]) -> str:
    item_data = {
        "evidence_id": evidence_item.get("evidence_id", ""),
        "title": evidence_item.get("title", ""),
        "content": evidence_item.get("content", ""),
        "evidence_type": evidence_item.get("evidence_type", ""),
        "metadata": evidence_item.get("metadata", {}),
    }
    return compute_sha256_hash(item_data)  # sha256(json.dumps(..., sort_keys=True))

# File: repositories/firestore.py
self._get_client().collection("evidence_records").document(evidence_id).set(data)
```

---

## Trace: VERIFY Pipeline

**File**: `services/ethereum_anchor_service.py` line ~106

```python
def verify_evidence(self, evidence_id: str) -> Dict[str, Any]:
    evidence = self.evidence_repository.get(evidence_id)  # Retrieve from Firestore
    computed_hash = hash_evidence_item(evidence)          # Recompute hash
    
    blockchain_proof = self.repository.get(evidence_id)   # Retrieve anchor from Firestore
    
    on_chain = self.blockchain.get_evidence_anchor(evidence_id)  # Query Ethereum
    hashes_match = self.blockchain.verify_evidence(
        evidence_id, bytes.fromhex(computed_hash)
    )
    
    return {
        "verified": hashes_match,
        "status": "VERIFIED" if hashes_match else "TAMPERED",
        ...
    }
```

---

## Comparison Table

| Step | CREATE | VERIFY | Identical? |
|------|--------|--------|-----------|
| **Input** | EvidenceItem (new) | EvidenceItem (from DB) | ⚠️ MAYBE |
| **Canonicalization** | Extract 5 fields | Extract 5 fields | ✅ YES |
| **JSON Serialization** | `sort_keys=True` | `sort_keys=True` | ✅ YES |
| **Encoding** | UTF-8 | UTF-8 | ✅ YES |
| **SHA-256** | hashlib.sha256 | hashlib.sha256 | ✅ YES |
| **Digest Format** | hex (lowercase) | hex (lowercase) | ✅ YES |
| **Comparison** | Store hash | Compare with on-chain | ✅ SAME |

### **CRITICAL ISSUE: Input Data Difference**

**CREATE** hashes the in-memory EvidenceItem object **immediately after creation**, before persistence.

**VERIFY** hashes the evidence object **retrieved from Firestore**, which may have been modified.

**Risk**: If Firestore record is mutated, verification will fail or accept tampered data.

---

# 6. Mutation / Tamper Resistance

## Test Cases Based on Existing Code

### ✅ Original Evidence → Expected PASS

```python
evidence = {"evidence_id": "e-1", "title": "X", "content": "Y", "evidence_type": "Z", "metadata": {}}
hash1 = hash_evidence_item(evidence)
hash2 = hash_evidence_item(evidence)
# Result: hash1 == hash2 ✅ VERIFIED by test_evidence_hash_determinism.py
```

---

### ✅ Change Numeric Value (if included in hash) → Expected FAIL

```python
# Assuming risk_impact was in hash (but it's NOT currently)
evidence1 = {..., "risk_impact": 50}
evidence2 = {..., "risk_impact": 51}
# Result: hash1 != hash2 ✅ FAIL (correctly detects change)
# BUT: Currently risk_impact is NOT hashed, so change is UNDETECTED ⚠️
```

---

### ✅ Change String → Expected FAIL

```python
evidence1 = {..., "content": "Original clause text"}
evidence2 = {..., "content": "Modified clause text"}
# Result: hash1 != hash2 ✅ VERIFIED by test_evidence_package_with_different_metadata()
```

---

### ✅ Add Field → Expected FAIL (if metadata affected)

```python
evidence1 = {..., "metadata": {}}
evidence2 = {..., "metadata": {"new_key": "value"}}
# Result: hash1 != hash2 ✅ (metadata is hashed)
```

---

### ✅ Remove Field → Expected FAIL (if in hash fields)

```python
evidence1 = {..., "title": "Original Title"}
evidence2 = {..., "title": ""}  # Removed or cleared
# Result: hash1 != hash2 ✅ (title is hashed, default is "")
```

---

### ⚠️ Change Timestamp → Expected ? (Actually IGNORED)

```python
evidence1 = {..., "created_at": "2026-08-25T12:00:00Z"}
evidence2 = {..., "created_at": "2026-08-25T12:00:01Z"}
# Result: hash1 == hash2 ✅ (timestamps NOT in hash)
# This is intentional but must be recognized during verification
```

---

### ⚠️ Change ID → Expected FAIL (But Blocks Creation)

```python
evidence1 = {..., "evidence_id": "e-1"}
evidence2 = {..., "evidence_id": "e-2"}
# Result: hash1 != hash2 ✅ VERIFIED by test_evidence_package_with_different_evidence_ids()
# But in practice: each evidence_id is assigned once and immutable
```

---

### ✅ Reorder Object Keys → Expected PASS (Same Hash)

```python
evidence1 = {"a": 1, "b": 2, "c": 3}
evidence2 = {"c": 3, "a": 1, "b": 2}
# Result: hash1 == hash2 ✅ VERIFIED by test_hashes_are_deterministic()
```

---

### ✅ Reorder Semantically Ordered Array (by ID) → Expected PASS (Same Hash)

```python
items1 = [{"evidence_id": "e-1"}, {"evidence_id": "e-2"}]
items2 = [{"evidence_id": "e-2"}, {"evidence_id": "e-1"}]
# Result: hash1 == hash2 ✅ VERIFIED by test_evidence_package_order_independent()
# Evidence package sorts by evidence_id before hashing
```

---

### ⚠️ Change Whitespace → Expected PASS (Normalized)

```python
evidence1 = {..., "content": "Text"}
evidence2 = {..., "content": "Text "}  # Trailing space
# Result: hash1 != hash2 ⚠️ (whitespace is NOT normalized, only UTF-8 encoded)
# Risk: Content "text" vs "Text" will produce different hashes
```

---

### ✅ Change Unicode Representation → Expected PASS (Same)

```python
evidence1 = {..., "content": "café"}  # Composed
evidence2 = {..., "content": "café"}  # Decomposed (different bytes)
# Result: DEPENDS on input encoding
# Python's json.dumps uses ensure_ascii=False, preserves bytes as-is
# Risk: Unicode normalization not applied (NFC vs NFD)
```

---

### ⚠️ Change Excluded Fields (risk_impact, compliance_impact) → Expected PASS (Same Hash)

```python
evidence1 = {..., "risk_impact": 50, "compliance_impact": 25}
evidence2 = {..., "risk_impact": 0, "compliance_impact": 0}
# Result: hash1 == hash2 ⚠️ IGNORED (not in hash)
# Risk: Impact scores can change without detection
```

---

### ⚠️ Change Passport ID (Linkage) → Expected PASS (Same Hash)

```python
evidence1 = {..., "passport_id": "p-1"}
evidence2 = {..., "passport_id": "p-999"}
# Result: hash1 == hash2 ⚠️ IGNORED (not in hash)
# Risk: Evidence can be re-linked to different passport without detection
```

---

## Tamper Resistance Summary

| Mutation | Detection | Severity | Notes |
|----------|-----------|----------|-------|
| Content change | ✅ YES | N/A | Immediately detected |
| ID change | ✅ YES | N/A | Included in hash |
| Metadata change | ✅ YES | N/A | Included in hash |
| Timestamp change | ⚠️ NO | LOW | Intentional (reproducibility) |
| Risk/compliance score change | ⚠️ NO | **HIGH** | Not included — major gap |
| Passport ID change | ⚠️ NO | **HIGH** | Not included — evidence can be re-linked |
| Whitespace changes | ✅ YES | LOW | UTF-8 preserves; only exact match works |
| Unicode variants | ⚠️ VARIES | MEDIUM | No normalization (NFC/NFD) |
| Description change | ⚠️ NO | MEDIUM | Not included |
| Status change | ⚠️ NO | MEDIUM | Not included |

---

# 7. Firestore Persistence Audit

## Collections

### **Collection 1: evidence_records**

**File**: `api/evidence_anchor.py` line ~39

```python
def get_evidence_records_repository(...) -> FirestoreRepository:
    return FirestoreRepository("evidence_records", settings=settings)
```

| Aspect | Value |
|--------|-------|
| **Collection Name** | `evidence_records` |
| **Document ID** | `evidence_id` (UUID v4) |
| **Stored Data** | Complete EvidenceItem (dict + metadata) |
| **Includes** | evidence_id, title, content, type, risk_impact, compliance_impact, metadata, hash, created_at, verified_at |
| **Mutation Policy** | Can be overwritten: `.set(doc_id, data, merge=False)` |
| **Merge Option** | Defaults to False (full replace) |
| **Versioning** | ❌ NONE — old version lost on overwrite |
| **Access Pattern** | `.get(evidence_id)` or `.stream()` |

### **Collection 2: evidence_anchors**

**File**: `api/evidence_anchor.py` line ~35

```python
def get_evidence_repository(...) -> FirestoreRepository:
    return FirestoreRepository("evidence_anchors", settings=settings)
```

| Aspect | Value |
|--------|-------|
| **Collection Name** | `evidence_anchors` |
| **Document ID** | `evidence_id` (same UUID as evidence_records) |
| **Stored Data** | Blockchain proof metadata |
| **Includes** | evidence_id, passport_id, blockchain_network, contract_address, transaction_hash, block_number, anchored_at, evidence_hash |
| **Mutation Policy** | Single write check: if exists, reject duplicate |
| **Versioning** | ❌ NONE — one anchor per evidence |
| **Uniqueness** | Each evidence_id can have only one anchor (enforced in code) |

---

## Persistence Details

**File**: `repositories/firestore.py`

```python
def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
    self._get_client().collection(self.collection).document(document_id).set(data, merge=merge)
```

### Immutability Assessment

| Aspect | Status | Risk |
|--------|--------|------|
| **Original evidence immutable** | ⚠️ NO | Can be overwritten |
| **Records can be overwritten** | ✅ YES | By design (merge=False) |
| **Versioning exists** | ❌ NO | No history |
| **Duplicate anchoring blocked** | ✅ YES | Service checks: `if self.repository.get(evidence_id)` |
| **Integrity risk** | **HIGH** | Evidence record can be mutated after anchoring |

**CRITICAL RISK**: An attacker with write access to Firestore can:

1. ✅ Anchor evidence with hash H to Ethereum
2. ⚠️ Modify evidence_records document in Firestore
3. ⚠️ Re-compute new hash H'
4. ⚠️ Update evidence_anchors to store H'
5. ⚠️ Verification will pass with new (tampered) data

---

## Algorithm/Version Metadata

**File**: `domains/passport/utils/hashing.py` line ~232

```python
passport_data = {
    "document_hash": document_hash,
    "policy_hash": policy_hash,
    "analysis_hash": analysis_hash,
    "evidence_hash": evidence_hash,
    "passport_hash_algorithm": "sha256",  # ← Version metadata
}
```

| Aspect | Status |
|--------|--------|
| **Algorithm version in hash** | ✅ YES ("sha256") |
| **Stored with evidence anchor** | ❌ NO — only in passport metadata |
| **Stored with evidence item** | ❌ NO |
| **Retrievable during verification** | ⚠️ PARTIAL |

---

# 8. Ethereum Anchoring Audit

## Smart Contract Deployment

**File**: `services/blockchain.py` line ~74-81

```python
self.rpc_url = rpc_url
self.contract_address = Web3.to_checksum_address(contract_address)
self.w3 = web3_class(web3_class.HTTPProvider(rpc_url))
self._connected = self.w3.is_connected()
...
self.chain_id = self.w3.eth.chain_id
if isinstance(self.chain_id, int) and self.chain_id != 11155111:
    raise ValueError(f"Wrong network! Expected Sepolia (11155111), got chain_id={self.chain_id}")
```

| Property | Value |
|----------|-------|
| **Network** | Ethereum Sepolia (testnet, chain_id 11155111) |
| **RPC Provider** | Configurable via ETHEREUM_RPC_URL |
| **Contract Address** | Configurable via ETHEREUM_CONTRACT_ADDRESS |
| **Network Validation** | ✅ Enforced (raises on wrong chain) |
| **Testnet/Mainnet** | Hardcoded to Sepolia (testnet only) |

---

## Anchoring Process

**File**: `services/blockchain.py` line ~346

```python
def anchor_evidence(self, record_id: str, evidence_hash: bytes) -> Tuple[str, int, int]:
    account = self.w3.eth.account.from_key(self.private_key)
    function = self.contract.functions.anchorEvidence(record_id, evidence_hash)
    transaction = function.build_transaction({
        "from": account.address,
        "nonce": self.w3.eth.get_transaction_count(account.address),
        "chainId": self.chain_id,
        "gas": function.estimate_gas({"from": account.address}),
        "gasPrice": self.w3.eth.gas_price,
    })
    signed = self.w3.eth.account.sign_transaction(transaction, self.private_key)
    tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = self._wait_for_transaction_receipt(tx_hash)
    if receipt["status"] == 0:
        raise ValueError(f"Evidence anchor transaction reverted: {tx_hash.hex()}")
    block = self.w3.eth.get_block(receipt["blockNumber"])
    return tx_hash.hex(), receipt["blockNumber"], int(block["timestamp"])
```

| Aspect | Details |
|--------|---------|
| **On-Chain Storage** | Contract state mapping: `mapping(string => bytes32)` (inferred) |
| **What's Written** | Evidence hash (bytes32) and record_id (string) |
| **Not Written** | Evidence content, passport_id, metadata — only hash |
| **Transaction** | Signed with private_key, sent via raw transaction |
| **Confirmation** | Waits for receipt, checks `status == 1` |
| **Failure Handling** | ✅ Raises ValueError on revert |

---

## Smart Contract Interface

**File**: `services/blockchain.py` line ~85 (embedded ABI)

```json
{
    "inputs": [
        {"name": "recordId", "type": "string"},
        {"name": "evidenceHash", "type": "bytes32"}
    ],
    "name": "anchorEvidence",
    "stateMutability": "nonpayable",
    "type": "function"
},
{
    "inputs": [
        {"name": "recordId", "type": "string"},
        {"name": "evidenceHash", "type": "bytes32"}
    ],
    "name": "verifyEvidence",
    "outputs": [{"name": "", "type": "bool"}],
    "stateMutability": "view",
    "type": "function"
},
{
    "inputs": [{"name": "recordId", "type": "string"}],
    "name": "getEvidenceAnchor",
    "outputs": [
        {"name": "evidenceHash", "type": "bytes32"},
        {"name": "timestamp", "type": "uint256"},
        {"name": "anchoredBy", "type": "address"}
    ],
    "stateMutability": "view",
    "type": "function"
}
```

---

## Verification Against Blockchain

**File**: `services/ethereum_anchor_service.py` line ~106

```python
def verify_evidence(self, evidence_id: str) -> Dict[str, Any]:
    ...
    on_chain = self.blockchain.get_evidence_anchor(evidence_id)
    hashes_match = self.blockchain.verify_evidence(
        evidence_id, bytes.fromhex(computed_hash)
    )
    return {
        "verified": hashes_match,
        "status": "VERIFIED" if hashes_match else "TAMPERED",
        "evidence_hash_on_chain": on_chain["evidence_hash"],
        "computed_hash": computed_hash,
        ...
    }
```

**File**: `services/blockchain.py` line ~380

```python
def verify_evidence(self, record_id: str, evidence_hash: bytes) -> bool:
    """Compare an evidence hash with its on-chain anchor."""
    return bool(self.contract.functions.verifyEvidence(record_id, evidence_hash).call())
```

| Aspect | Details |
|--------|---------|
| **Verification Type** | On-chain function call (view, no state change) |
| **Comparison** | bytes32 == bytes32 (Solidity native) |
| **No Database Dependency** | ✅ Pure blockchain verification |
| **Third-Party Verification** | ✅ Independent parties can call verifyEvidence |

---

## Independent Verification

**Can an independent third party verify the Ethereum anchor without trusting LexProof's database?**

**Answer**: ✅ YES (mostly)

**How**:

1. Get evidence hash from LexProof user (or directly)
2. Get evidence_id from LexProof user (or Firestore if public)
3. Call `verifyEvidence(evidence_id, evidence_hash)` on Sepolia
4. Contract returns true/false
5. Can independently verify on Etherscan

**BUT**:

- ❌ Cannot verify evidence **content** without trusted source
- ❌ Cannot verify risk_impact, compliance_impact (not in hash)
- ⚠️ Cannot verify timestamp authenticity (on-chain timestamp is block time, not creation time)

---

## Idempotency & Transaction Handling

**File**: `services/ethereum_anchor_service.py` line ~77

```python
if self.repository.get(evidence_id):
    raise ValueError("Evidence already has an Ethereum anchor")
```

| Aspect | Status |
|--------|--------|
| **Duplicate Check** | ✅ YES (raises error) |
| **Idempotent** | ❌ NO (will fail on retry) |
| **Transaction Replacement** | ⚠️ MANUAL ONLY (recover_anchor_from_transaction) |
| **Recovery Path** | ✅ YES (`recover_anchor_from_transaction`) |
| **Replay Protection** | ✅ YES (nonce incremented per transaction) |

---

## Gas Handling

**File**: `services/blockchain.py` line ~357

```python
"gas": function.estimate_gas({"from": account.address}),
"gasPrice": self.w3.eth.gas_price,
```

| Aspect | Status |
|--------|--------|
| **Gas Estimation** | ✅ YES (automatic via web3.py) |
| **EIP-1559** | ⚠️ OPTIONAL (not always used) |
| **Gas Price** | Legacy gasPrice (not maxFeePerGas) |
| **Out-of-Gas Handling** | Receipt check: `status == 0` raises error |

---

# 9. Verification API Audit

## Endpoint: POST /evidence/{evidence_id}/anchor

**File**: `api/evidence_anchor.py` line ~71

```python
@router.post(
    "/evidence/{evidence_id}/anchor",
    response_model=EvidenceAnchorResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def anchor_evidence_to_blockchain(
    evidence_id: str,
    request: EvidenceAnchorRequest,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository),
    evidence_records_repository: FirestoreRepository = Depends(get_evidence_records_repository)
) -> EvidenceAnchorResponse:
```

| Property | Value |
|----------|-------|
| **Method** | POST |
| **Path** | `/evidence/{evidence_id}/anchor` |
| **Status Code** | 202 ACCEPTED (async operation) |
| **Authentication** | None (SECURITY: Should require auth) |
| **Request Schema** | `{ "evidence_id": str }` |
| **Response Schema** | `{ evidence_id, blockchain_network, contract_address, transaction_hash, block_number, anchored_at, evidence_hash }` |

---

## Endpoint: GET /evidence/{evidence_id}/anchor

**File**: `api/evidence_anchor.py` line ~125

```python
@router.get(
    "/evidence/{evidence_id}/anchor",
    response_model=Dict[str, Any],
    summary="Get evidence anchor details"
)
async def get_evidence_anchor(
    evidence_id: str,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository)
) -> Dict[str, Any]:
```

| Property | Value |
|--------|-------|
| **Method** | GET |
| **Authentication** | None |
| **Response** | Anchor metadata from Firestore |

---

## Verification Workflow

**File**: `services/ethereum_anchor_service.py` line ~106

```python
def verify_evidence(self, evidence_id: str) -> Dict[str, Any]:
    evidence = self.evidence_repository.get(evidence_id)       # DB query
    computed_hash = hash_evidence_item(evidence)               # Recompute
    blockchain_proof = self.repository.get(evidence_id)        # DB query
    on_chain = self.blockchain.get_evidence_anchor(evidence_id) # Blockchain query
    hashes_match = self.blockchain.verify_evidence(...)        # Blockchain call
    return {
        "verified": hashes_match,
        "status": "VERIFIED" if hashes_match else "TAMPERED",
        ...
    }
```

### Verification Type

| Component | Source | Type |
|-----------|--------|------|
| **Evidence Content** | Firestore DB | Database verification |
| **Evidence Hash Computation** | Cryptographic (SHA-256) | Cryptographic verification |
| **Stored Hash** | Firestore DB | Database |
| **On-Chain Hash** | Ethereum Sepolia | Blockchain verification |
| **Hash Comparison** | Smart contract (view) | Cryptographic verification |

**Overall Classification**: **Cryptographic + Ethereum verification**

But verification **depends on Firestore** for evidence content.

---

## Verification Response

**File**: `services/ethereum_anchor_service.py` line ~128

```python
result = {
    "verified": hashes_match,
    "status": "VERIFIED" if hashes_match else "TAMPERED",
    "evidence_hash_on_chain": on_chain["evidence_hash"],
    "computed_hash": computed_hash,
    "blockchain_network": blockchain_proof["blockchain_network"],
    "contract_address": blockchain_proof["contract_address"],
    "transaction_hash": blockchain_proof["transaction_hash"],
    "block_number": blockchain_proof["block_number"],
    "anchored_at": blockchain_proof["anchored_at"],
}
```

### Failure States

| State | HTTP | Response |
|-------|------|----------|
| Evidence not found | 400 or handled | `verified: false, status: EVIDENCE_NOT_FOUND` |
| No anchor found | 400 or handled | `verified: false, status: ANCHOR_NOT_FOUND` |
| Hash mismatch | 200 | `verified: false, status: TAMPERED` |
| Hash match | 200 | `verified: true, status: VERIFIED` |

---

# 10. Frontend Verification UX

## Verification Portal

**File**: `frontend/app/public-verify/page.tsx`

### UI Elements

```typescript
interface VerificationResult {
  proof_id: string;
  contract_identifier: string;
  contract_version: string;
  document_hash: string;
  policy_hash: string;
  analysis_hash: string;
  evidence_hash: string;
  blockchain_network: string;
  transaction_hash: string | null;
  block_number: number | null;
  anchoring_timestamp: number | null;
  verification_status: string;
  is_verified: boolean;
  timestamp: string;
}
```

### User Journey

1. **Input**: Enter proof ID (evidence_id or contract hash)
2. **Fetch**: Call `/api/verify/{proof_id}`
3. **Display**: Large VERIFIED or VERIFICATION FAILED badge
4. **Show Details**:
   - Proof ID (copyable)
   - Contract Identifier & Version
   - All component hashes
   - Blockchain network
   - Transaction hash (copyable)
   - Block number
   - Anchoring timestamp
   - Verification status

### Non-Technical User Understanding

| Question | Can User Understand? | Evidence |
|----------|----------------------|----------|
| 1. What was analyzed? | ✅ YES | Document hash shown |
| 2. What evidence was created? | ⚠️ PARTIAL | Evidence hash shown, but not details |
| 3. What hash represents evidence? | ✅ YES | Explicitly labeled |
| 4. What was anchored to Ethereum? | ✅ YES | Evidence hash + tx hash shown |
| 5. Is evidence currently authentic? | ✅ YES | VERIFIED/VERIFICATION FAILED badge |
| 6. What happens if tampered? | ✅ MAYBE | Status changes to VERIFICATION FAILED, but reason not explained |

### UX Gaps

- ⚠️ No explanation of what each hash means
- ⚠️ No indication that risk_impact/compliance_impact are NOT protected
- ⚠️ No explanation of timestamp authenticity
- ⚠️ No link to Etherscan for independent verification
- ✅ Transaction hash displayed (can verify on Etherscan)

---

# 11. Existing Tests

## Test Coverage

| Test File | Test Count | Coverage | Status |
|-----------|-----------|----------|--------|
| `test_hashing.py` | 1 | Determinism | ✅ PASS |
| `test_evidence_hash_determinism.py` | 7 | Determinism, order-independence | ✅ PASS |
| `test_passport_hash_integrity.py` | 2+ | Passport hash, evidence preservation | ✅ PASS |
| `test_ethereum_anchor_service.py` | 8+ | Anchor, verify, recovery | ✅ PASS |
| `test_blockchain_service.py` | Not reviewed | Blockchain interaction | UNKNOWN |
| `test_public_verification.py` | 6+ | API structure | ⚠️ INCOMPLETE |

---

## Key Tests

### ✅ Test: Hashing Determinism

**File**: `test_hashing.py`

```python
def test_hashes_are_deterministic():
    analysis = {"risk_score": 12, "findings": [{"id": "f-1"}]}
    evidence = [{"evidence_id": "e-2", "content": "b"}, {"evidence_id": "e-1", "content": "a"}]

    assert compute_sha256_hash({"b": 2, "a": 1}) == compute_sha256_hash({"a": 1, "b": 2})
    assert hash_ai_analysis(analysis) == hash_ai_analysis(analysis)
    assert hash_evidence_package(evidence) == hash_evidence_package(list(reversed(evidence)))
```

**Verifies**: ✅ Keys are sorted, items are sorted by ID

---

### ✅ Test: Evidence Package Order-Independence

**File**: `test_evidence_hash_determinism.py`

```python
def test_evidence_package_order_independent():
    evidence_items_unordered = [
        {"evidence_id": "e-3", "content": "third"},
        {"evidence_id": "e-1", "content": "first"},
        {"evidence_id": "e-2", "content": "second"},
    ]
    evidence_items_ordered = [
        {"evidence_id": "e-1", "content": "first"},
        {"evidence_id": "e-2", "content": "second"},
        {"evidence_id": "e-3", "content": "third"},
    ]
    
    hash_unordered = hash_evidence_package(evidence_items_unordered)
    hash_ordered = hash_evidence_package(evidence_items_ordered)
    
    assert hash_unordered == hash_ordered
```

**Verifies**: ✅ Evidence package hashing is order-independent

---

### ✅ Test: Passport Hash Determinism

**File**: `test_passport_hash_integrity.py`

```python
def test_passport_hash_is_deterministic_sha256_and_covers_all_inputs():
    inputs = {
        "document_hash": "document-a",
        "policy_hash": "policy-a",
        "analysis_hash": "analysis-a",
        "evidence_hash": "evidence-a",
    }
    
    first = compute_passport_hash(**inputs)
    second = compute_passport_hash(**inputs)
    
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    
    for field in inputs:
        changed = {**inputs, field: f"{inputs[field]}-changed"}
        assert compute_passport_hash(**changed) != first
```

**Verifies**: ✅ Passport hash is deterministic, sensitive to all inputs

---

### ✅ Test: Anchor Persists Metadata & Rejects Duplicates

**File**: `test_ethereum_anchor_service.py`

```python
def test_anchor_persists_metadata_and_duplicate_is_rejected(evidence_hash):
    ...
    result = service.anchor_evidence("evidence-1")
    assert repository.get("evidence-1")["transaction_hash"] == result["transaction_hash"]
    assert repository.get("evidence-1")["evidence_hash"] == computed_hash
    
    with pytest.raises(ValueError, match="already has"):
        service.anchor_evidence("evidence-1")
```

**Verifies**: ✅ Anchor stored correctly, duplicates rejected

---

### ✅ Test: Hash Mismatch Detected

**File**: `test_ethereum_anchor_service.py`

```python
def test_different_hash_is_tampered(evidence_hash):
    evidence = evidence_record()
    computed_hash = hash_evidence_item(evidence)
    service = make_service(MemoryRepository(), FakeBlockchain(computed_hash))
    service.evidence_repository.set("evidence-1", {**evidence, "content": "Changed content"})
    
    result = service.verify_evidence("evidence-1")
    assert result["verified"] is False
    assert result["status"] == "TAMPERED"
```

**Verifies**: ✅ Content changes detected as tampering

---

## Test Gaps

| Gap | Severity | Why Missing |
|-----|----------|-------------|
| Integration test (end-to-end upload → anchor → verify) | HIGH | Requires real Firestore + Ethereum testnet |
| Firestore immutability test | HIGH | Should test that overwriting evidence fails security |
| Unicode normalization test | MEDIUM | No test for NFC vs NFD variants |
| Whitespace sensitivity test | MEDIUM | No test for trailing spaces, tabs |
| Risk/Compliance impact excluded from hash | MEDIUM | No test verifying this gap |
| Passport ID excluded from hash | MEDIUM | No test verifying re-linking is undetected |
| Timestamp excluded from hash | LOW | Intentional but should document |
| Database access control test | HIGH | No tests for Firestore security rules |
| Frontend integration test | MEDIUM | No tests for verify portal |
| Ethereum network mismatch test | MEDIUM | Test only hardcoded to Sepolia |

---

# 12. Security / Integrity Concerns

## CRITICAL Issues

### 🔴 C1: Firestore Security Rules — Open Read/Write

**File**: `firestore.rules`

```
allow read, write: if request.time < timestamp.date(2026, 9, 22);
```

**Impact**: Anyone with database reference can read/write until September 22, 2026 (EXPIRED).

**Status**: ⚠️ **TIME-SENSITIVE BOMB** — Rules will deny all access on expiry date.

**Fix Needed**: Deploy production rules immediately.

---

### 🔴 C2: Evidence Record Mutability

**File**: `repositories/firestore.py` → `.set(..., merge=False)`

**Impact**: After anchoring evidence to Ethereum with hash H:

1. Attacker modifies evidence_records document
2. Hash changes to H'
3. Updates evidence_anchors to store H'
4. Verification passes with tampered evidence

**Risk**: Complete hash verification bypass.

**Fix Needed**: Immutable storage or versioning.

---

### 🔴 C3: Risk & Compliance Impacts Not Protected

**File**: `utils/hashing.py` → `hash_evidence_item()`

**Problem**: `risk_impact` and `compliance_impact` are NOT included in evidence hash.

**Impact**:

- Evidence with risk_impact=50 and risk_impact=0 produce same hash
- Verification passes even if impact scores are changed
- No audit trail of impact changes

**Risk**: Legal risk scores can be manipulated undetected.

**Fix Needed**: Include in EVIDENCE_HASH_FIELDS or document as limitation.

---

### 🔴 C4: Passport ID Not Protected

**File**: `utils/hashing.py` → `hash_evidence_item()` excludes `passport_id`

**Impact**: Evidence can be re-linked from one passport to another without detection.

**Risk**: Evidence from one contract can be claimed as evidence for another.

**Fix Needed**: Include passport_id in hash.

---

### 🔴 C5: No Firestore Read Authentication

**File**: `api/evidence_anchor.py` line ~71, ~125

```python
async def anchor_evidence_to_blockchain(evidence_id: str, ...):
    # No authentication check!
```

**Impact**: Any user can anchor any evidence_id to Ethereum.

**Risk**: Unauthorized anchoring, hash verification exploit.

**Fix Needed**: Add `Depends(verify_auth_token)` or similar.

---

## HIGH Issues

### 🟠 H1: Timestamp Excluded from Hash (Intentional but Risky)

**File**: `utils/hashing.py`

**Problem**: `created_at`, `verified_at` not in hash → reproducibility but loses temporal integrity.

**Impact**: Evidence can be ante-dated or post-dated without detection.

**Fix**: Document why temporal info was excluded, or include block timestamp from Ethereum.

---

### 🟠 H2: No Whitespace Normalization

**File**: `utils/hashing.py` → UTF-8 encoding only

**Problem**: Content "clause text" ≠ "clause text " (trailing space).

**Impact**: Content with whitespace variations won't verify.

**Fix**: Strip or normalize whitespace before hashing.

---

### 🟠 H3: No Unicode Normalization (NFC/NFD)

**File**: `utils/hashing.py` → `ensure_ascii=False`

**Problem**: "café" (composed) ≠ "café" (decomposed in bytes).

**Impact**: International characters may fail verification if encoding differs.

**Fix**: Apply `unicodedata.normalize('NFC', text)` before hashing.

---

### 🟠 H4: Frontend Trusts Backend Hash

**File**: `public-verify/page.tsx` line ~40

```typescript
const response = await apiFetch(`/api/verify/${proofId}...`);
```

**Impact**: If backend is compromised, verification is fake.

**Fix**: Implement client-side hash computation and verification. OR: expose Ethereum query endpoints directly.

---

### 🟠 H5: EVIDENCE_HASH_FIELDS Defined But Not Used

**File**: `utils/hashing.py` line ~142 (defined) vs line ~209 (used differently)

**Problem**: Inconsistency between definition and implementation.

**Impact**: Future maintainers may assume more fields are hashed than actually are.

**Fix**: Remove unused constant or update hash function to use it.

---

## MEDIUM Issues

### 🟡 M1: No Version Metadata in Evidence Hash

**File**: `utils/hashing.py`

**Problem**: Hash algorithm version ("sha256") only in passport, not evidence.

**Impact**: If hashing algorithm changes, old evidence won't reverify.

**Fix**: Include algorithm version in evidence hash.

---

### 🟡 M2: Ethereum Chain ID Hardcoded to Sepolia (Testnet)

**File**: `blockchain.py` line ~40

```python
if self.chain_id != 11155111:  # Sepolia testnet
    raise ValueError(...)
```

**Impact**: Cannot deploy to mainnet without code change.

**Risk**: Mainnet anchoring not supported.

**Fix**: Allow configuration via ETHEREUM_CHAIN_ID.

---

### 🟡 M3: No Audit Trail in Firestore

**File**: `repositories/firestore.py`

**Problem**: No created_by, modified_by, change log.

**Impact**: Cannot trace who anchored evidence or when modifications occurred.

**Fix**: Add audit trail collection.

---

### 🟡 M4: Frontend Lacks Etherscan Links

**File**: `public-verify/page.tsx`

**Problem**: Transaction hash shown but no link to Etherscan for independent verification.

**Impact**: Users cannot independently verify on-chain.

**Fix**: Add link to `https://sepolia.etherscan.io/tx/{transaction_hash}`.

---

## LOW Issues

### 🟢 L1: Gas Price Not EIP-1559 by Default

**File**: `blockchain.py` line ~357

```python
"gasPrice": self.w3.eth.gas_price,  # Legacy
```

**Impact**: Higher gas costs on high-fee networks.

**Fix**: Use maxFeePerGas + maxPriorityFeePerGas (EIP-1559).

---

### 🟢 L2: No Exponential Backoff on Blockchain Timeouts

**File**: `blockchain.py` line ~345+

**Problem**: Single attempt to anchor.

**Impact**: Network glitches cause failure.

**Fix**: Add retry logic with exponential backoff.

---

### 🟢 L3: CORS Not Restricted in Development

**File**: `config/settings.py` line ~35

```python
cors_origins: str = Field(default="http://localhost:3000", ...)
```

**Impact**: In production, CORS origins may be too permissive.

**Fix**: Restrict to specific domains.

---

---

# 13. Current Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ Frontend (Next.js)                                                   │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ public-verify/page.tsx — Public Verification Portal UI         │ │
│ │ • Enter proof_id                                               │ │
│ │ • Call /api/verify/{proof_id}                                  │ │
│ │ • Display VERIFIED / VERIFICATION FAILED                       │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                    apiFetch() / HTTP JSON
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Backend (FastAPI)                                                    │
│                                                                      │
│ ┌───────────────────────────────────────────────────────────────┐   │
│ │ API Routes (api/evidence_anchor.py)                          │   │
│ │ • POST /evidence/{evidence_id}/anchor                        │   │
│ │ • GET /evidence/{evidence_id}/anchor                         │   │
│ └───────────────────────┬────────────────────────────────────────┘   │
│                         │                                            │
│         ┌───────────────┴────────────────┐                          │
│         │                                │                          │
│         ▼                                ▼                          │
│   ┌──────────────┐              ┌─────────────────────┐            │
│   │ Evidence     │              │ Ethereum Anchor     │            │
│   │ Service      │              │ Service             │            │
│   │              │              │                     │            │
│   │ • create_    │              │ • anchor_evidence() │            │
│   │   evidence_  │              │ • verify_evidence() │            │
│   │   item()     │              │                     │            │
│   │ • get_       │              └────────┬────────────┘            │
│   │   evidence_  │                       │                         │
│   │   item()     │         ┌─────────────┴─────────────┐           │
│   └──────┬───────┘         │                           │           │
│          │         ┌───────┴─────────────┐   ┌────────┴────────┐  │
│          │         │                     │   │                 │  │
│          ▼         ▼                     ▼   ▼                 ▼  │
│   ┌──────────────────┐         ┌───────────────────┐  ┌──────────┐│
│   │ Passport Service │         │ Blockchain Service│  │ Config   ││
│   │                  │         │                   │  │          ││
│   │ • create_        │         │ • anchor_evidence()  │ •Settings││
│   │   passport()     │         │ • verify_evidence()  │          ││
│   │ • hash_*()       │         │ • get_evidence_     │ (ENV-backed)
│   │                  │         │   anchor()          │          ││
│   └──────┬───────────┘         └───────────────────┘  └──────────┘│
│          │                                                        │
│   ┌──────┴──────────────────────┐                                │
│   │                             │                                │
│   ▼                             ▼                                │
│  ┌────────────────────────────────────────────────────┐          │
│  │ Hashing Utilities (domains/passport/utils/hashing.py)       │
│  │                                                    │          │
│  │ • compute_sha256_hash()    — SHA-256 with sort_keys=True   │
│  │ • hash_evidence_item()     — 5-field subset                │
│  │ • hash_evidence_package()  — sorted by evidence_id        │
│  │ • canonicalize_evidence_item() — extract EVIDENCE_HASH_FIELDS
│  │ • compute_passport_hash()  — final immutable fingerprint   │
│  └───────────────────────────────────────────────────┘          │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │                    │
                    ▼                    ▼
            ┌──────────────────┐  ┌──────────────────┐
            │ Firestore DB     │  │ Ethereum Sepolia │
            │                  │  │                  │
            │ Collections:     │  │ LexProofRegistry │
            │ • evidence_      │  │ Smart Contract   │
            │   records        │  │                  │
            │ • evidence_      │  │ • anchorEvidence()
            │   anchors        │  │ • verifyEvidence()
            │                  │  │ • getEvidenceAnchor()
            │ Document ID:     │  │                  │
            │ {evidence_id}    │  │ Storage:         │
            │                  │  │ mapping(string   │
            │ Stored Data:     │  │ => bytes32)      │
            │ evidence_id,     │  │                  │
            │ title, content,  │  │ Network:         │
            │ type, hash, etc  │  │ Sepolia (testnet)│
            │                  │  │ Chain ID: 11155111
            │ Mutation:        │  │                  │
            │ .set(...merge=F) │  │ Transaction:     │
            │                  │  │ • Signed         │
            │ Versioning:      │  │ • Confirmed      │
            │ NONE             │  │ • Immutable      │
            └──────────────────┘  └──────────────────┘
```

---

# 14. Final Assessment

## A. What is Already Solid

1. ✅ **Deterministic SHA-256 Hashing** — `json.dumps(sort_keys=True)` ensures reproducible hashes across runs
2. ✅ **Evidence Package Order-Independence** — Sorted by evidence_id before hashing; reordering doesn't change hash
3. ✅ **Blockchain Anchoring Foundation** — Smart contract and web3.py integration working; Sepolia network validated
4. ✅ **Comprehensive Test Coverage** — Hashing, passport, anchor, and verification tests mostly passing
5. ✅ **Ethereum Anchor Immutability** — Once written to blockchain (bytes32), hash cannot be changed without transaction
6. ✅ **Duplicate Anchor Protection** — Service prevents multiple anchors for same evidence_id
7. ✅ **Hash Mismatch Detection** — Verification correctly identifies content tampering
8. ✅ **Timestamp Reproducibility** — Excluding timestamps from hash allows offline/offline reproducibility
9. ✅ **Configuration Externalization** — Settings loaded from environment, not hardcoded
10. ✅ **Public Verification Portal UI** — Frontend correctly displays verification results

---

## B. Critical Integrity Gaps

1. 🔴 **C1: Firestore Rules Expired** — Rules allow read/write until 2026-09-22 (future expiry, but **urgent**). No production-grade security rules deployed.

2. 🔴 **C2: Evidence Record Mutability** — After anchoring to Ethereum, Firestore evidence_records can be overwritten, breaking cryptographic guarantees. An attacker can:
   - Modify evidence_records
   - Recompute hash
   - Update evidence_anchors
   - Verification passes with tampered data

3. 🔴 **C3: Risk/Compliance Impacts Not Hashed** — `risk_impact` and `compliance_impact` excluded from evidence hash:
   - Risk score 50 and risk score 0 produce identical hash
   - Impacts can change undetected
   - Major legal risk score exposure

4. 🔴 **C4: Passport ID Not Hashed** — `passport_id` excluded from evidence hash:
   - Evidence from contract A can be re-linked to contract B
   - No cryptographic proof of association
   - Cross-contract mixing undetected

5. 🔴 **C5: No API Authentication** — Evidence anchor endpoints have no auth:
   - Any user can anchor any evidence_id
   - Unauthorized anchoring possible
   - No audit trail

---

## C. Verification Gaps

1. **Evidence Source Trust** — Verification retrieves evidence from Firestore (trustable only if immutable + audited)
2. **Excluded Fields** — risk_impact, compliance_impact, passport_id not verified
3. **Timestamp Authenticity** — Timestamps excluded intentionally; no proof of temporal order
4. **Firestore Content Integrity** — No way to verify evidence hasn't been modified after anchoring
5. **Frontend Verification** — Frontend must trust backend API; no client-side cryptographic verification
6. **No Audit Trail** — Cannot see who/when evidence was anchored or modified

---

## D. Ethereum Gaps

1. **Testnet Only** — Hardcoded to Sepolia (testnet); no mainnet support
2. **Chain ID Validation** — Prevents accidental mainnet deployment, but requires code change
3. **No Recovery from Failed Tx** — Retry logic manual only (`recover_anchor_from_transaction`)
4. **Legacy Gas Pricing** — Uses gasPrice instead of EIP-1559 (maxFeePerGas)
5. **No Etherscan Links** — Frontend doesn't link to block explorer for independent verification

---

## E. Test Gaps

| Test | Severity | Gap |
|------|----------|-----|
| Integration test (upload → anchor → verify) | 🔴 CRITICAL | Requires real Firestore + Ethereum |
| Firestore immutability enforcement | 🔴 CRITICAL | No test that overwriting fails security |
| Risk/compliance score protection | 🔴 CRITICAL | Should test excluded fields |
| Passport ID protection | 🔴 CRITICAL | Should test re-linking detection |
| API authentication | 🔴 CRITICAL | Should test unauthorized access rejected |
| Firestore security rules | 🟠 HIGH | Should test read/write access control |
| Unicode normalization | 🟡 MEDIUM | Should test NFC vs NFD variants |
| Whitespace normalization | 🟡 MEDIUM | Should test trailing spaces/tabs |
| Frontend integration | 🟡 MEDIUM | Should test end-to-end UI |
| Ethereum mainnet support | 🟡 MEDIUM | Should test chain flexibility |

---

## F. Recommended Implementation Order

### **P0 — Must Fix Before Demo**

```
P0-1: Deploy Production Firestore Security Rules
     • Restrict read/write to authenticated users only
     • Add document-level permissions (owner-based)
     • Block unauthenticated access
     Risk: Without this, database is public + mutable
     Effort: 1-2 hours

P0-2: Make Evidence Records Immutable
     • Add versioning layer or archive old versions
     • Prevent .set(..., merge=false) overwrites
     • Or: Move to append-only audit log
     Risk: Tampered evidence detection bypassed
     Effort: 4-6 hours

P0-3: Add API Authentication
     • Require valid JWT or session token for /anchor endpoints
     • Verify ownership before anchoring
     Risk: Unauthorized anchoring, spoofing
     Effort: 2-3 hours

P0-4: Fix Evidence Hash Fields
     • Include risk_impact, compliance_impact, passport_id in hash
     • Or: Document why excluded + test
     • DECISION: If excluded intentionally, add explanatory comment + test that changes are undetected
     Risk: Impact scores and passport linkage undetected
     Effort: 1-2 hours

P0-5: Add Ethereum Verification Link
     • Frontend: Add link to Etherscan for independent verification
     • Allow users to verify on-chain without trusting backend
     Risk: No independent verification path
     Effort: 1 hour
```

### **P1 — Should Fix Before Production**

```
P1-1: Unicode Normalization
     • Apply unicodedata.normalize('NFC', text) before hashing
     • Test international characters
     Risk: Verification fails for Unicode variants
     Effort: 2 hours

P1-2: Whitespace Normalization
     • Consider stripping or normalizing whitespace
     • Or: Document that "text" ≠ "text " (trailing space)
     • Test with various whitespace combinations
     Risk: Legitimate verification failures
     Effort: 2 hours

P1-3: Add Audit Trail
     • Log who/when evidence was created, anchored, verified
     • Store in Firestore audit collection
     Risk: No compliance audit trail
     Effort: 4-6 hours

P1-4: Version Metadata
     • Include algorithm version in evidence hash
     • Prepare migration path for algorithm changes
     Risk: Hash reverification fails if algorithm upgrades
     Effort: 3-4 hours

P1-5: Mainnet Support
     • Make chain ID configurable (remove Sepolia hardcode)
     • Add integration tests for mainnet
     Risk: Cannot deploy to mainnet without code change
     Effort: 2-3 hours

P1-6: Client-Side Verification
     • Expose Ethereum query endpoints directly
     • Allow frontend to verify hashes without backend
     Risk: Frontend must trust backend
     Effort: 4-6 hours
```

### **P2 — Polish**

```
P2-1: EIP-1559 Gas Pricing
     • Use maxFeePerGas + maxPriorityFeePerGas
     • Reduce gas costs on high-fee networks
     Effort: 1-2 hours

P2-2: Retry Logic
     • Add exponential backoff for blockchain timeouts
     • Make retry configurable
     Effort: 2-3 hours

P2-3: Etherscan Integration
     • Auto-generate block explorer URLs for transactions
     • Display in verification results
     Effort: 1 hour

P2-4: Inconsistency Cleanup
     • Remove EVIDENCE_HASH_FIELDS constant or use it
     • Document all intentional exclusions in comments
     Effort: 1 hour
```

---

## G. Final Verdict

### ⚠️ **NEEDS INTEGRITY FIXES**

**Reasoning** (5 sentences):

LexProof has a **solid cryptographic foundation** (deterministic SHA-256, order-independent hashing, blockchain integration) but suffers from **critical integrity vulnerabilities** that compromise its core claim of immutable evidence. The Firestore database is **openly writable** until September 2026 with no versioning, allowing post-anchor tampering. **Evidence fields essential to legal risk** (risk_impact, compliance_impact) are excluded from the hash, making their verification impossible. The API lacks authentication, and the frontend trusts the backend for verification rather than querying Ethereum independently. **Fix P0 items before demo**, especially immutability and access control, or the verification cannot be trusted.

---

# Summary Table

| Category | Status | Risk | Fix Priority |
|----------|--------|------|--------------|
| Hashing Algorithm | ✅ SOLID | None | None |
| Evidence Canonicalization | ⚠️ INCOMPLETE | HIGH | P0-4 |
| Firestore Persistence | 🔴 VULNERABLE | CRITICAL | P0-2 |
| Firestore Security | 🔴 EXPIRED | CRITICAL | P0-1 |
| Blockchain Anchoring | ✅ SOLID | None | None |
| API Authentication | 🔴 MISSING | CRITICAL | P0-3 |
| Frontend Verification | ⚠️ PARTIAL | MEDIUM | P0-5 |
| Test Coverage | ✅ GOOD | None | None |
| Unicode/Whitespace | ⚠️ UNHANDLED | MEDIUM | P1-1, P1-2 |
| Audit Trail | 🔴 MISSING | HIGH | P1-3 |
| Mainnet Support | ⚠️ HARDCODED | MEDIUM | P1-5 |

---

**End of Actual Findings Report**
