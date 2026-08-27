# LexProof — P0 Findings Verification Audit
## Independent Code-Based Verification

**Date**: August 25, 2026  
**Method**: Read-only code inspection  
**Goal**: Independently verify each P0 finding from actual source code

---

# 1. Evidence Hash Fields Verification

## Finding: Risk/Compliance Impacts Excluded from Hash

### Evidence Hash Definition (DECLARED)

**File**: `domains/passport/utils/hashing.py` line 142-157

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

✅ **OBSERVATION**: `EVIDENCE_HASH_FIELDS` defines 16 fields INCLUDING risk_impact and compliance_impact.

---

### Evidence Hash Implementation (ACTUAL)

**File**: `domains/passport/utils/hashing.py` line 209-221

```python
def hash_evidence_item(evidence_item: Dict[str, Any]) -> str:
    """Compute hash for individual evidence item."""
    # Include all relevant fields for reproducibility
    item_data = {
        "evidence_id": evidence_item.get("evidence_id", ""),
        "title": evidence_item.get("title", ""),
        "content": evidence_item.get("content", ""),
        "evidence_type": evidence_item.get("evidence_type", ""),
        "metadata": evidence_item.get("metadata", {}),
    }

    return compute_sha256_hash(item_data)
```

✅ **OBSERVATION**: `hash_evidence_item()` uses ONLY 5 fields:
- `evidence_id` ✅
- `title` ✅
- `content` ✅
- `evidence_type` ✅
- `metadata` ✅

❌ **EXCLUDED**:
- `passport_id` 
- `risk_impact` 
- `compliance_impact` 
- `description` 
- `content_type` 
- `evidence_status` 
- `contract_reference` 
- `policy_reference` 
- `analysis_reference` 
- `source` 
- `source_id` 
- All timestamps

---

### Field-by-Field Classification

| Field | Status | In Hash? |
|-------|--------|----------|
| evidence_id | ✅ HASHED | YES |
| passport_id | ❌ EXCLUDED | NO |
| document_id | Not in either | NO |
| contract_id | Not in either | NO |
| findings | Absorbed into metadata | PARTIAL |
| risk_impact | ❌ EXCLUDED | NO |
| compliance_impact | ❌ EXCLUDED | NO |
| risk_score | Not in either | NO |
| metadata | ✅ HASHED | YES |
| timestamps | ❌ EXCLUDED | NO |
| schema/version | ❌ EXCLUDED | NO |
| title | ✅ HASHED | YES |
| content | ✅ HASHED | YES |
| evidence_type | ✅ HASHED | YES |
| description | ❌ EXCLUDED | NO |

---

### Test for Answer: Will hash change if risk_impact changes?

**File**: `tests/lexproof/test_ethereum_anchor_service.py` line 98-108

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

This test modifies **content** (which IS hashed), and verification correctly fails.

**To test risk_impact**:

If we created a test:
```python
service.evidence_repository.set("evidence-1", {**evidence, "risk_impact": 0})
```

**The hash would NOT change** because risk_impact is not in the hashing function.

---

## Answer to Finding #1

> **If `risk_impact` changes after anchoring, will the SHA-256 hash change?**

**ANSWER**: ❌ **NO — The hash will NOT change.**

**PROOF**:
- `hash_evidence_item()` only uses 5 fields
- `risk_impact` is NOT one of them
- Changing `risk_impact` from 50 to 0 produces identical hash
- Verification will pass with tampered risk scores

---

# 2. Passport Association Verification

## Finding: passport_id Not Included in Evidence Hash

### Passport ID in Hash Function

**File**: `domains/passport/utils/hashing.py` line 209-221

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

✅ **OBSERVATION**: `passport_id` is NOT extracted from evidence_item in hashing.

---

### Where passport_id is Stored

**File**: `services/ethereum_anchor_service.py` line 95-96

```python
evidence = self.evidence_repository.get(evidence_id)
passport_id = evidence.get("passport_id")
```

**File**: `services/ethereum_anchor_service.py` line 104-112

```python
blockchain_proof = {
    "evidence_id": evidence_id,
    "passport_id": passport_id,  # ← Stored in anchor proof
    "blockchain_network": "ethereum-sepolia",
    ...
}
self.repository.set(evidence_id, blockchain_proof)
```

✅ **OBSERVATION**: 
- `passport_id` is retrieved from evidence record
- Stored in `evidence_anchors` collection (separate from hash)
- NOT part of the cryptographic hash

---

### Can Evidence be Re-linked Without Detection?

**Scenario**:

1. Evidence E with passport_id=P₁ is anchored
   - Hash H = hash_evidence_item(E)  (does NOT include P₁)
   - Stored in blockchain: hash(E) = H

2. Attacker modifies evidence in Firestore:
   - Change passport_id from P₁ to P₂
   - Evidence E' now claims to belong to passport P₂

3. Verification retrieves E':
   - Recalculates hash: hash(E') = H (SAME, because passport_id not hashed)
   - Compares with blockchain: H == H ✅ VERIFIED

**Result**: Evidence successfully re-linked to different passport **without changing hash**.

---

## Answer to Finding #2

> **Could an attacker theoretically take Evidence A (Passport A) and associate it with Passport B without changing the anchored hash?**

**ANSWER**: ✅ **YES — This is possible.**

**PROOF**:
1. `passport_id` is NOT in hash computation
2. Changing `passport_id` in Firestore does NOT change evidence hash
3. Verification compares computed hash with blockchain hash
4. Both will match even if `passport_id` was modified

**Code Path**:
```
Evidence: {evidence_id, passport_id: P₁, content, ...}
Hash H = hash_evidence_item(evidence)  # Does NOT include passport_id
→ Anchor to blockchain: H

Later, attacker:
Evidence: {evidence_id, passport_id: P₂, content, ...}  # Changed passport
Hash H' = hash_evidence_item(evidence)  # = H (passport not used)
→ Verification: H' == H_blockchain → VERIFIED ✅
```

---

# 3. Evidence Mutability Verification

## Finding: Anchored Evidence May Be Mutable

### Firestore Repository Implementation

**File**: `repositories/firestore.py` line 27-28

```python
def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
    self._get_client().collection(self.collection).document(document_id).set(data, merge=merge)
```

✅ **OBSERVATION**: 
- `.set()` method defaults to `merge=False`
- This means FULL REPLACE (not merge/update)

### Evidence Anchoring Flow

**File**: `services/ethereum_anchor_service.py` line 78

```python
evidence = self.evidence_repository.get(evidence_id)
if not evidence:
    raise ValueError(f"Evidence record not found for evidence_id: {evidence_id}")
passport_id = evidence.get("passport_id")
evidence_hash = hash_evidence_item(evidence)
```

Then anchors to Ethereum at line 85-90.

---

### Vulnerability Sequence

**Scenario: Can this sequence occur?**

```
1. Create evidence E with hash H
2. Calculate hash H = hash_evidence_item(E)
3. Anchor hash H to Ethereum ✅
4. Modify evidence in Firestore (E → E')
5. Verification retrieves E'
6. Verification still references H from blockchain
```

**Analysis**:

**File**: `services/ethereum_anchor_service.py` line 106-148 (verify_evidence)

```python
def verify_evidence(self, evidence_id: str) -> Dict[str, Any]:
    evidence = self.evidence_repository.get(evidence_id)  # ← Retrieves CURRENT data
    if not evidence:
        return {"verified": False, "status": "EVIDENCE_NOT_FOUND"}
    
    computed_hash = hash_evidence_item(evidence)  # ← Hashes CURRENT data
    
    blockchain_proof = self.repository.get(evidence_id)  # ← Gets anchor
    
    on_chain = self.blockchain.get_evidence_anchor(evidence_id)  # ← Gets blockchain data
    hashes_match = self.blockchain.verify_evidence(
        evidence_id, bytes.fromhex(computed_hash)
    )
    
    return {
        "verified": hashes_match,  # ← Compares current hash vs blockchain
        ...
    }
```

✅ **OBSERVATION**:
- Line 107: Retrieves evidence from Firestore (CURRENT version)
- Line 113: Hashes the current evidence
- Line 118: Compares with blockchain
- **IF evidence in Firestore was modified, current hash will change**
- **If new hash matches blockchain, verification passes with WRONG evidence**

---

### Can Firestore Evidence be Overwritten?

**File**: `repositories/firestore.py` line 27-28

```python
def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
    self._get_client().collection(self.collection).document(document_id).set(data, merge=merge)
```

**Default behavior**: `merge=False` → **Full replace allowed**

**Access Control**: 

**File**: `firestore.rules` line 1-18

```
allow read, write: if request.time < timestamp.date(2026, 9, 22);
```

✅ **OBSERVATION**: Firestore allows ANYONE to write/overwrite until 2026-09-22.

---

### Attack Sequence

```
1. Evidence E with risk_impact=50, hash H is anchored to Ethereum

2. Attacker with Firestore access:
   a. Modifies evidence in Firestore: risk_impact → 0
   b. Since risk_impact not in hash, recomputes: H' = hash(E') = H
   c. Updates evidence_anchors to store hash H' (same as H)

3. Verification:
   a. Retrieves E' from Firestore
   b. Computes hash H' = hash(E') = H (because risk_impact excluded)
   c. Compares with blockchain: H' == H → VERIFIED ✅
   d. User sees VERIFIED but with wrong risk score (0 instead of 50)
```

---

## Answer to Finding #3

> **Is this sequence possible: Create → Anchor → Modify → Verify?**

**ANSWER**: ✅ **YES — CONFIRMED VULNERABILITY**

**PROOF**:
1. Evidence stored in mutable Firestore collection
2. Firestore allows write access (rules expire 2026-09-22)
3. `hash_evidence_item()` excludes risk_impact, compliance_impact, passport_id
4. Modifying these fields does NOT change hash
5. Verification retrieves current (modified) evidence
6. If new hash matches blockchain, verification passes with tampered data

**Critical Impact**: Risk scores can be changed after anchoring without detection.

---

# 4. /anchor Authorization Verification

## Finding: /anchor Endpoint Lacks Authentication

### Endpoint Definition

**File**: `api/evidence_anchor.py` line 68-76

```python
@router.post(
    "/evidence/{evidence_id}/anchor",
    response_model=EvidenceAnchorResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Anchor evidence to Ethereum"
)
async def anchor_evidence_to_blockchain(
    evidence_id: str,
    request: EvidenceAnchorRequest,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository),
    evidence_records_repository: FirestoreRepository = Depends(get_evidence_records_repository)
) -> EvidenceAnchorResponse:
```

❌ **OBSERVATION**: 
- No `get_current_user` dependency
- Only has `Depends(get_settings)` and repository dependencies
- No authentication, no authorization

---

### Comparison with Authenticated Endpoint

**File**: `api/contracts.py` line 91-92

```python
@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_contract(file: UploadFile = File(...), user: dict[str, Any] = Depends(get_current_user)):
```

✅ **OBSERVATION**: Authenticated endpoints use `Depends(get_current_user)`

---

### Authentication Service Exists

**File**: `services/auth.py` line 1-21

```python
"""Shared FastAPI authentication dependency."""

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = verify_firebase_token(credentials.credentials)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    if not claims.get("uid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firebase token does not contain a UID", headers={"WWW-Authenticate": "Bearer"})
    return claims
```

✅ **OBSERVATION**: `get_current_user()` exists and is used elsewhere, but NOT imported or used in evidence_anchor.py

---

### What Can an Unauthenticated Caller Do?

**File**: `services/ethereum_anchor_service.py` line 62-104

```python
async def anchor_evidence(self, evidence_id: str) -> Dict[str, Any]:
    evidence = self.evidence_repository.get(evidence_id)
    if not evidence:
        raise ValueError(f"Evidence record not found for evidence_id: {evidence_id}")
    passport_id = evidence.get("passport_id")
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

**An unauthenticated caller can**:
1. ✅ Call `POST /evidence/{evidence_id}/anchor`
2. ✅ Anchor **any** evidence_id to Ethereum
3. ✅ Trigger real Ethereum transaction
4. ✅ Use LexProof's wallet to pay for gas
5. ✅ No verification that the caller owns/created the evidence

---

## Answer to Finding #4

> **Can an unauthenticated caller cause: Evidence → Ethereum transaction → LexProof wallet?**

**ANSWER**: ✅ **YES — CONFIRMED**

**PROOF**:
1. `/evidence/{evidence_id}/anchor` endpoint has NO authentication
2. Does NOT use `Depends(get_current_user)`
3. Any caller can call `POST /evidence/any-id/anchor`
4. Service will retrieve evidence from Firestore
5. Service will call `blockchain.anchor_evidence()` with LexProof private key
6. Transaction signed with LexProof wallet and sent to Ethereum

**Attack**: Attacker can anchor arbitrary evidence using LexProof's wallet and gas.

---

# 5. Verification Path Analysis

## Tracing Verification Flow

**File**: `api/evidence_anchor.py` line 199-220

```python
@router.post(
    "/evidence/{evidence_id}/verify",
    response_model=EvidenceVerificationResult,
    summary="Verify evidence on Ethereum"
)
async def verify_evidence_on_blockchain(
    evidence_id: str,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository),
    evidence_records_repository: FirestoreRepository = Depends(get_evidence_records_repository)
) -> EvidenceVerificationResult:
```

Also no authentication ❌

---

## Verification Pipeline

**File**: `services/ethereum_anchor_service.py` line 106-148

```
Step 1: User input
  └─ evidence_id (API param)

Step 2: Backend retrieval
  └─ evidence = evidence_repository.get(evidence_id)  # Firestore DB

Step 3: Canonicalization & Serialization
  └─ item_data = {
       "evidence_id": evidence.get("evidence_id"),
       "title": evidence.get("title"),
       "content": evidence.get("content"),
       "evidence_type": evidence.get("evidence_type"),
       "metadata": evidence.get("metadata"),
     }

Step 4: SHA-256
  └─ computed_hash = compute_sha256_hash(item_data)

Step 5: Blockchain verification
  └─ hashes_match = blockchain.verify_evidence(evidence_id, bytes.fromhex(computed_hash))

Step 6: Result
  └─ return { "verified": hashes_match, ...}
```

---

## Dependency Analysis

### A. Does verification depend on Firestore?

**ANSWER**: ✅ **YES — REQUIRED**

**Evidence**: Line 107 of ethereum_anchor_service.py:
```python
evidence = self.evidence_repository.get(evidence_id)  # ← Firestore query
```

Without Firestore access, verification cannot retrieve evidence to hash.

---

### B. Does frontend receive simple { "verified": true }?

**File**: `frontend/app/public-verify/page.tsx` line 40

```typescript
const response = await apiFetch(`/api/verify/${proofId}...`);

if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Verification failed');
}

const result: VerificationResult = await response.json();
setVerificationResult(result);
```

**ANSWER**: ✅ **YES — Frontend trusts backend response**

Frontend receives `VerificationResult` from backend (line 20-31):
```typescript
interface VerificationResult {
  proof_id: string;
  verified: boolean;  ← Single boolean
  ...
}
```

Frontend displays result without cryptographic verification.

---

### C. Can hash be independently calculated from supplied evidence?

**ANSWER**: ✅ **YES — IF evidence is provided**

**But**: Evidence is NOT supplied to the frontend for client-side hashing. Frontend only receives `proof_id` and must fetch evidence from backend API.

---

### D. Does verification independently establish blockchain match?

**ANSWER**: ⚠️ **PARTIALLY**

**Process**:
1. Backend computes hash from Firestore evidence
2. Backend calls blockchain `verify_evidence()` (on-chain comparison)
3. Backend returns boolean result

**Issue**: Frontend depends on backend to honestly query Ethereum. Frontend does NOT independently verify the Ethereum state.

---

## Classification

```
CURRENT SYSTEM:

User Input (proof_id)
    ↓
Frontend
    ↓
Backend API (/verify/{proof_id})
    ↓
Database (retrieve evidence) ← ❌ MUTABLE
    ↓
Canonicalization & SHA-256
    ↓
Blockchain query (verify_evidence call)
    ↓
Backend returns: {verified: true/false}
    ↓
Frontend displays result
```

**Classification**: **DATABASE + CRYPTOGRAPHIC + ETHEREUM**

- DATABASE: Verification requires Firestore
- CRYPTOGRAPHIC: SHA-256 hashing
- ETHEREUM: Blockchain comparison

**But with critical dependency on mutable Firestore**.

---

# 6. Firestore Security Rules Verification

## Current Rules

**File**: `firestore.rules` line 1-18

```
rules_version='2'

service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      // This rule allows anyone with your database reference to view, edit,
      // and delete all data in your database. It is useful for getting
      // started, but it is configured to expire after 30 days because it
      // leaves your app open to attackers. At that time, all client
      // requests to your database will be denied.
      //
      // Make sure to write security rules for your app before that time, or
      // else all client requests to your database will be denied until you
      // update your rules.
      allow read, write: if request.time < timestamp.date(2026, 9, 22);
    }
  }
}
```

---

## Analysis

| Aspect | Status | Details |
|--------|--------|---------|
| **Read permissions** | ✅ OPEN | Allow anyone until 2026-09-22 |
| **Write permissions** | ✅ OPEN | Allow anyone until 2026-09-22 |
| **Update permissions** | ✅ OPEN | Covered by write |
| **Delete permissions** | ✅ OPEN | Covered by write |
| **Authentication required** | ❌ NO | No auth check in rules |
| **Collection-specific rules** | ❌ NO | All collections (`/{document=**}`) use same rule |
| **Production rules deployed** | ❌ NO | Only development rules exist |
| **Rules actually configured** | ✅ PROBABLY | Rules file exists and will be deployed with project |

---

## Rule Expiration

**Current date**: August 25, 2026  
**Expiration date**: September 22, 2026 (2026-09-22)  
**Time remaining**: ~28 days

**Impact**: On September 23, 2026, ALL Firestore access will be denied until rules are updated.

---

## Answer to Finding #6

> **What are the actual Firestore security rules?**

**ANSWER**: 
- **Read**: Allow all (no authentication)
- **Write**: Allow all (no authentication)
- **Update**: Allow all (no authentication)
- **Delete**: Allow all (no authentication)
- **Auth required**: ❌ NO
- **Collection-specific**: ❌ NO (wildcard `/{document=**}`)
- **Production rules**: ❌ NO — only development rules
- **Status**: ⚠️ EXPIRES 2026-09-22

**Severity**: 🔴 **CRITICAL — Open access until expiration**

---

# 7. Ethereum Anchoring Verification

## Transaction Creation

**File**: `services/blockchain.py` line 346-370

```python
def anchor_evidence(self, record_id: str, evidence_hash: bytes) -> Tuple[str, int, int]:
    """Anchor an existing LexProof evidence hash using the registry contract."""
    self._ensure_sepolia()
    if not record_id or len(record_id) > 256:
        raise ValueError("Record ID must be between 1 and 256 characters")
    if len(evidence_hash) != 32 or evidence_hash == b'\x00' * 32:
        raise ValueError("Evidence hash must be a non-zero bytes32 value")

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

---

## Transaction Data

| Component | Value |
|-----------|-------|
| **Function called** | `anchorEvidence(record_id: string, evidenceHash: bytes32)` |
| **Parameter 1** | `record_id` (evidence_id from Firestore) |
| **Parameter 2** | `evidence_hash` (bytes32 SHA-256) |
| **Data encoded** | ABI-encoded call to anchorEvidence |
| **What's on-chain** | record_id + bytes32 hash |
| **What's NOT on-chain** | Evidence content, metadata, passport_id |

---

## Network & RPC

| Property | Value |
|----------|-------|
| **Network** | Ethereum Sepolia (testnet) |
| **Chain ID** | 11155111 (hardcoded in validation) |
| **RPC** | Configurable via `ETHEREUM_RPC_URL` |
| **Wallet** | Derived from private key |
| **Gas pricing** | Legacy gasPrice (not EIP-1559) |
| **Tx hash storage** | Stored in evidence_anchors collection |
| **Block confirmation** | Waits for receipt with status check |

---

## Independent Verification Capability

**Question**: Can third party retrieve anchored hash without trusting LexProof database?

**Answer**: ✅ **YES**

**Process**:
1. Get record_id (from evidence_id)
2. Get transaction hash (from LexProof or blockchain explorer)
3. Query Ethereum Sepolia: `contract.getEvidenceAnchor(record_id)`
4. Receive bytes32 hash
5. Compare with evidence hash
6. No Firestore dependency

**BUT**: To verify evidence **content**, must trust LexProof's database or have original document.

---

# 8. Explorer Link Verification

## Frontend Evidence Display

**File**: `frontend/app/public-verify/page.tsx` line 164-200+

Search result: No Etherscan/explorer links constructed.

## Answer

**Status**: ❌ **MISSING**

**Evidence**: 
- No `etherscan.io` URL construction in code
- No `sepolia.etherscan.io` references
- Transaction hash displayed as plain text (copyable)
- No link to block explorer

**Current display** (line ~200):
```typescript
<p className="font-mono text-sm break-all">{verificationResult.transaction_hash}</p>
```

No hyperlink wrapper.

---

# 9. P0 Truth Table

| Finding | Confirmed? | Evidence | Severity | Risk |
|---------|-----------|----------|----------|------|
| **Risk/compliance excluded from hash** | ✅ YES | `hash_evidence_item()` uses 5 fields, excludes risk_impact + compliance_impact | 🔴 CRITICAL | Risk scores can change undetected after anchoring |
| **Passport ID excluded from hash** | ✅ YES | `hash_evidence_item()` does not extract passport_id | 🔴 CRITICAL | Evidence can be re-linked between contracts undetected |
| **Anchored evidence mutable** | ✅ YES | Firestore `.set(..., merge=false)` allows overwrite; rules allow write access | 🔴 CRITICAL | Tampered evidence can pass verification if hash collision avoided |
| **`/anchor` unauthenticated** | ✅ YES | No `Depends(get_current_user)` in endpoint; compared to contracts.py which HAS it | 🔴 CRITICAL | Any caller can anchor arbitrary evidence using LexProof wallet |
| **Verification depends on Firestore** | ✅ YES | Line 107 of verify_evidence: `evidence = self.evidence_repository.get(evidence_id)` | 🟠 HIGH | If Firestore tampered, verification reads wrong data |
| **No independent Ethereum verification** | ✅ YES | Frontend receives `{verified: true}` from backend; no client-side crypto | 🟠 HIGH | Frontend trusts backend to honestly query Ethereum |
| **Firestore rules inadequate** | ✅ YES | Rules open to all; expires 2026-09-22; no authentication | 🔴 CRITICAL | Anyone can read/write/delete all data until expiration |
| **No explorer link** | ✅ YES | Grep search: no `etherscan` references in public-verify page | 🟡 MEDIUM | Users cannot independently verify transaction on Etherscan |

---

# 10. Detailed P0 Findings

## P0.1: Risk/Compliance Impacts Not Protected by Hash

```
Problem:
  Risk impact and compliance impact scores are excluded from the evidence hash.
  These values can be changed after anchoring without affecting the cryptographic hash.

Why it matters:
  Legal risk assessment depends on accurate risk/compliance scores.
  If scores can be altered post-anchoring, the verification claim "evidence is unchanged"
  is technically true (for hashed fields) but legally false (risk assessment changed).

Exact files:
  - domains/passport/utils/hashing.py (hash_evidence_item function, lines 209-221)
  - domains/passport/utils/hashing.py (EVIDENCE_HASH_FIELDS constant, lines 142-157)

Exact functions:
  - hash_evidence_item() — excludes risk_impact, compliance_impact
  - compute_sha256_hash() — only receives 5 fields

Current behavior:
  - Evidence with risk_impact=50 produces hash H
  - Same evidence with risk_impact=0 produces hash H (IDENTICAL)
  - Verification passes even though risk score changed

Desired behavior:
  - Either: Include risk_impact + compliance_impact in hash
  - Or: Document that these are NOT protected and implement separate immutability mechanism

Potential implementation:
  1. Add risk_impact, compliance_impact to item_data dict in hash_evidence_item()
  2. Update tests to verify changes in these fields trigger hash mismatch
  3. Implement migration: re-anchor old evidence with new hash

Tests required:
  - test_risk_impact_change_detected()
  - test_compliance_impact_change_detected()
  - test_hash_includes_impact_scores()
```

---

## P0.2: Passport ID Not Protected by Hash

```
Problem:
  Passport ID is not included in the evidence hash.
  An evidence item can be re-linked from one passport to another without changing hash.

Why it matters:
  Evidence is supposed to prove facts about a specific contract (passport).
  If evidence can be re-associated with a different contract, the integrity claim is broken.
  Attacker could use evidence from Contract A to claim facts about Contract B.

Exact files:
  - domains/passport/utils/hashing.py (hash_evidence_item, lines 209-221)
  - services/ethereum_anchor_service.py (anchor_evidence, lines 95-96, passport_id retrieval)

Exact functions:
  - hash_evidence_item() — does NOT include passport_id
  - anchor_evidence() — stores passport_id separately from hash

Current behavior:
  - Evidence E with passport_id=P1 → hash H
  - Change passport_id to P2 → hash still H
  - Verification passes; evidence now claims to belong to P2

Desired behavior:
  - Include passport_id in the evidence hash
  - Hash becomes dependent on both content AND passport association

Potential implementation:
  1. Add passport_id to item_data dict in hash_evidence_item()
  2. Re-anchor existing evidence with new hash including passport_id
  3. Update verification to check passport_id consistency

Tests required:
  - test_passport_id_change_detected()
  - test_evidence_cannot_be_relinked()
  - test_hash_includes_passport_id()
```

---

## P0.3: Firestore Evidence Records Mutable

```
Problem:
  Evidence records in Firestore can be overwritten after anchoring.
  Firestore rules allow anyone (until 2026-09-22) to write arbitrary data.
  An attacker can modify evidence, then update the hash in evidence_anchors collection
  to match the new evidence (if new evidence excludes certain fields from hash).

Why it matters:
  Cryptographic hash only works if data is immutable.
  If data can be changed after hashing, the hash becomes meaningless.
  Combined with P0.1 and P0.2 (excluded fields), an attacker can:
  1. Anchor evidence
  2. Change risk_impact from 50 to 0 (or other excluded fields)
  3. Recompute hash (unchanged because fields excluded)
  4. Update evidence_anchors collection
  5. Verification passes with tampered data

Exact files:
  - repositories/firestore.py (set method, lines 27-28)
  - firestore.rules (security rules, lines 1-18)
  - services/ethereum_anchor_service.py (verify_evidence, line 107)

Exact functions:
  - FirestoreRepository.set() — allows merge=False (full replace)
  - verify_evidence() — retrieves CURRENT evidence (not immutable snapshot)

Current behavior:
  - Evidence can be overwritten in Firestore at any time
  - Firestore rules allow open read/write access until 2026-09-22
  - Verification retrieves current (potentially modified) evidence

Desired behavior:
  - Implement immutability: mark records as finalized after anchoring
  - Implement versioning: keep all historical versions
  - Implement append-only audit log instead of in-place updates
  - Deploy restrictive Firestore security rules

Potential implementation:
  1. Add immutability_verified_at field to evidence records
  2. In verify_evidence(), check that evidence has immutability_verified_at set
  3. Prevent updates to immutable records (Firestore rule or backend check)
  4. Or: Create separate immutable_evidence_snapshots collection
  5. Or: Move to append-only event log

Tests required:
  - test_immutable_evidence_cannot_be_modified()
  - test_verify_rejects_modified_evidence()
  - test_firestore_write_blocked_after_anchoring()
```

---

## P0.4: /anchor Endpoint Unauthenticated

```
Problem:
  POST /evidence/{evidence_id}/anchor endpoint has no authentication.
  Any caller can trigger Ethereum transactions using LexProof's wallet.
  No verification that caller owns/created the evidence.

Why it matters:
  Allows unauthorized anchoring of arbitrary evidence.
  Attacker can:
  1. Anchor any evidence_id to Ethereum
  2. Create fraudulent blockchain "proof" of non-existent or fake evidence
  3. Use LexProof's wallet to pay gas (cost-free attack from attacker perspective)

Exact files:
  - api/evidence_anchor.py (anchor_evidence_to_blockchain, lines 68-76)
  - services/auth.py (get_current_user dependency, exists but not imported)

Exact functions:
  - anchor_evidence_to_blockchain() — missing Depends(get_current_user)

Current behavior:
  No authentication required; any HTTP client can POST to /anchor

Desired behavior:
  Require valid Firebase token / authenticated user
  Verify that user owns/has permission for the evidence

Potential implementation:
  1. Add `user: dict[str, Any] = Depends(get_current_user)` parameter
  2. Query evidence_records to verify user owns evidence (via owner_id field)
  3. Raise 403 if user does not own evidence
  4. Log anchoring action for audit trail

Tests required:
  - test_anchor_requires_authentication()
  - test_anchor_unauthenticated_rejected()
  - test_anchor_requires_ownership()
  - test_anchor_different_user_rejected()
```

---

## P0.5: Firestore Security Rules Expired/Missing

```
Problem:
  Firestore security rules allow open read/write access to all data.
  Rules expire on 2026-09-22 (~28 days away).
  After expiration, ALL Firestore access will be denied.
  No production-grade rules deployed.

Why it matters:
  Without proper rules:
  1. Anyone with database reference can read all data (PII exposure)
  2. Anyone can write/overwrite/delete all data
  3. Project becomes non-functional on expiration date
  4. On expiration, all client requests denied until rules updated

Exact files:
  - firestore.rules (lines 1-18)

Current behavior:
  allow read, write: if request.time < timestamp.date(2026, 9, 22);
  - No authentication check
  - No authorization logic
  - All collections under wildcard /{document=**}
  - Expires in ~28 days

Desired behavior:
  - Deploy production rules with:
    * Require authentication for all operations
    * Collection-specific access (evidence_records, evidence_anchors, etc.)
    * User-based authorization (owner_id matching)
    * Immutability enforcement for anchored records

Potential implementation:
  1. Create collection-specific rules:
     - evidence_records: require auth + owner_id matches
     - evidence_anchors: immutable after creation (no update/delete)
     - audit_log: append-only
  2. Implement custom claims for role-based access (if needed)
  3. Test rules thoroughly before deployment
  4. Set up monitoring for expiration

Tests required:
  - test_firestore_requires_authentication()
  - test_firestore_requires_ownership()
  - test_firestore_immutable_anchors()
  - test_firestore_rules_not_expired()
```

---

# FINAL P0 IMPLEMENTATION ORDER

## Confirmed P0 Issues (Ranked by Severity & Dependency)

```
P0.1: Fix Firestore Security Rules
  Severity: CRITICAL (affects all other security)
  Dependency: Foundational (everything else depends on this)
  Effort: 2-4 hours
  Status: MUST FIX IMMEDIATELY (28 days to expiration)

P0.2: Implement Evidence Immutability
  Severity: CRITICAL
  Dependency: Requires P0.1 rules
  Effort: 4-6 hours
  Status: Must fix before demo

P0.3: Add Authentication to /anchor Endpoint
  Severity: CRITICAL
  Dependency: Independent
  Effort: 2-3 hours
  Status: Must fix before demo

P0.4: Include Risk/Compliance in Hash
  Severity: CRITICAL
  Dependency: Independent
  Effort: 2-3 hours
  Status: Must fix before demo

P0.5: Include Passport ID in Hash
  Severity: CRITICAL
  Dependency: Independent
  Effort: 1-2 hours
  Status: Must fix before demo
```

---

**End of Verification Audit**
