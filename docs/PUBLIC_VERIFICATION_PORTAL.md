# Public Verification Portal - Sprint 4

## Overview

The Public Verification Portal provides a judge-friendly, no-authentication-required verification experience for legal document proofs on the blockchain.

## Route

```
GET /verify/{proofId}
```

## Features

### Two Verification Modes

#### Mode A: Verify Registered Contract
- Verifier does NOT need to upload a document
- Simply enters the Proof ID to view verification details
- Shows the registered contract hash and blockchain metadata

#### Mode B: Upload Document and Verify
- Verifier uploads the contract document content
- System calculates SHA-256 hash of uploaded document
- Compares hash with registered contract hash
- Returns VERIFIED or VERIFICATION FAILED

### Strict Verification

The verification algorithm is **strict**:

```
uploaded_document
    ↓
SHA-256 hash calculation
    ↓
Compare with registered document hash
    ↓
Query blockchain for proof details
    ↓
Verify matching hashes
    ↓
VERIFIED / VERIFICATION FAILED
```

**Critical**: If the document differs by even one byte, verification **fails**.

### 11 Display Fields

1. **Proof ID** - Unique identifier for the proof on blockchain
2. **Contract Identifier** - Name or ID of the contract
3. **Contract Version** - Version of the contract
4. **Document Hash** - SHA-256 hash of the contract document
5. **Policy Hash** - SHA-256 hash of the policy
6. **Analysis Hash** - SHA-256 hash of the AI analysis
7. **Evidence Hash** - SHA-256 hash of evidence
8. **Blockchain Network** - Ethereum Sepolia (testnet)
9. **Transaction Hash** - Hash of the blockchain transaction
10. **Block Number** - Block number where proof was anchored
11. **Anchoring Timestamp** - When the proof was anchored to blockchain
12. **Current Verification Result** - VERIFIED or VERIFICATION FAILED
13. **Timestamp** - When verification was performed

### Clear Visual Indicators

- **GREEN VERIFIED**: Large, bold text indicating successful verification
- **RED VERIFICATION FAILED**: Large, bold text indicating failed verification

## Security

### No Private Content Exposure

The verification portal **never exposes private contract contents**:

- ❌ No contract text or content
- ❌ No PII (Personally Identifiable Information)
- ❌ No AI analysis findings
- ❌ No risk scores or compliance scores
- ✅ Only hashes and metadata are shown

### No Authentication Required

- Verifiers do NOT need a LexProof account
- No login or registration required
- Public access for judges, auditors, and verifiers

### Hash-Only Verification

- Contract contents are never stored or transmitted
- Only cryptographic hashes are compared
- Secure even if blockchain is compromised

## API Specification

### Request

```
GET /verify/{proofId}?document_content={optional_document_content}
```

### Parameters

- `proofId` (path, required): Proof ID in hex format (e.g., `0x1234...`)
- `document_content` (query, optional): Document content for hash comparison (Mode B)

### Response

```json
{
  "proof_id": "0x1234...",
  "contract_identifier": "CONTRACT-001",
  "contract_version": "1.0",
  "document_hash": "a1b2c3...",
  "policy_hash": "d4e5f6...",
  "analysis_hash": "g7h8i9...",
  "evidence_hash": "j0k1l2...",
  "blockchain_network": "ethereum-sepolia",
  "transaction_hash": "0xabcd...",
  "block_number": 12345678,
  "anchoring_timestamp": 1695556800,
  "verification_status": "VERIFIED",
  "is_verified": true,
  "timestamp": "2024-09-23T10:30:00"
}
```

### Status Codes

- `200 OK`: Verification successful
- `404 Not Found`: Proof ID does not exist or is invalid
- `500 Internal Server Error`: Blockchain service unavailable or other error

## Frontend UI

### Judge-Friendly Design

- Large, clear text for verification status
- Simple, intuitive two-mode interface
- Easy-to-read hash displays
- Copy-to-clipboard functionality for hashes
- Responsive design for all devices

### Verification Modes Switch

- **Verify Registered Contract**: Enter Proof ID only
- **Upload Document & Verify**: Paste document content for comparison

### Result Display

1. **Status Banner** (top)
   - Large GREEN VERIFIED text
   - Large RED VERIFICATION FAILED text

2. **Basic Information** (grid)
   - Proof ID
   - Contract Identifier
   - Contract Version
   - Blockchain Network

3. **Transaction Details** (grid)
   - Transaction Hash
   - Block Number
   - Anchoring Timestamp

4. **Document Hashes** (list)
   - Document Hash (with copy button)
   - Policy Hash (with copy button)
   - Analysis Hash (with copy button)
   - Evidence Hash (with copy button)

5. **Verification Timestamp** (bottom)
   - When verification was performed

## Testing

### Test Cases

1. **Valid Document Verification**
   - Upload document that matches registered hash
   - Expected: VERIFIED

2. **Modified Document Verification**
   - Upload document that differs by one byte
   - Expected: VERIFICATION FAILED

3. **Wrong Passport**
   - Use proof ID from different contract
   - Expected: VERIFICATION FAILED

4. **Nonexistent Proof**
   - Use invalid or non-existent Proof ID
   - Expected: 404 Not Found

5. **Blockchain Unavailable**
   - Test when blockchain service is down
   - Expected: Error handling with clear message

6. **Malformed Document**
   - Upload malformed or empty document content
   - Expected: Error handling

### Test Structure

```python
# Test valid document
response = client.get(
    "/verify/{proof_id}",
    params={"document_content": valid_document}
)
assert response.status_code == 200
assert response.json()["is_verified"] == True

# Test modified document
response = client.get(
    "/verify/{proof_id}",
    params={"document_content": modified_document}
)
assert response.status_code == 200
assert response.json()["is_verified"] == False
```

## Deployment

### Backend Requirements

- FastAPI server running
- Ethereum Sepolia RPC endpoint configured
- Smart contract deployed and ABI loaded
- Transaction store initialized (Firestore or memory)

### Frontend Requirements

- Next.js 14 application
- Public route at `/public-verify`
- API proxy configured for `/api/verify` endpoint

### Environment Variables

```bash
# Backend
BLOCKCHAIN_RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
BLOCKCHAIN_PRIVATE_KEY=your_private_key
BLOCKCHAIN_CONTRACT_ADDRESS=0x...
BLOCKCHAIN_PERSISTENCE=memory  # or "firestore"
```

## Usage Examples

### Example 1: Verify Registered Contract (Mode A)

1. Open verification portal: `http://localhost:3000/public-verify`
2. Select "Verify Registered Contract" mode
3. Enter Proof ID: `0x1a2b3c...`
4. Click "Verify Contract"
5. View verification result with all 11 fields

### Example 2: Upload and Verify Document (Mode B)

1. Open verification portal: `http://localhost:3000/public-verify`
2. Select "Upload Document & Verify" mode
3. Paste contract document content
4. Click "Upload & Verify"
5. System calculates SHA-256 hash and compares with registered hash
6. View VERIFIED or VERIFICATION FAILED result

## Performance Considerations

- Hash calculation is fast (SHA-256 is optimized)
- Blockchain queries are asynchronous
- Caching for frequently accessed proofs
- Rate limiting for public API to prevent abuse

## Future Enhancements

- [ ] Bulk verification for multiple documents
- [ ] PDF document upload support
- [ ] Download verification report
- [ ] Integration with legal document management systems
- [ ] Multi-chain support (mainnet, testnets)
- [ ] Verification history and audit trail

## Security Best Practices

1. **Never expose contract contents**: Only hashes and metadata
2. **Use HTTPS**: Encrypt all communication
3. **Rate limiting**: Prevent API abuse
4. **Input validation**: Sanitize all inputs
5. **Error messages**: Don't reveal system internals
6. **Audit logging**: Log all verification requests
7. **Secure storage**: Protect private keys and credentials

## Legal Considerations

- Verification is for informational purposes only
- Verifiers should maintain their own records
- Chain of custody is maintained on blockchain
- Timestamps are cryptographically verified
- Tamper-evident proof of document integrity
