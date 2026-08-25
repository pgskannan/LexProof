# Public Verification Portal

## Quick Start

1. **Start the backend server**:
   ```bash
   cd backend
   python -m app.lexproof.main
   ```

2. **Start the frontend server**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Open verification portal**:
   ```
   http://localhost:3000/public-verify
   ```

## Verification Modes

### Mode A: Verify Registered Contract

- **Purpose**: View verification details for an already-anchored proof
- **Steps**:
  1. Select "Verify Registered Contract" mode
  2. Enter Proof ID (e.g., `0x1a2b3c4d5e6f...`)
  3. Click "Verify Contract"
  4. View verification result

### Mode B: Upload Document & Verify

- **Purpose**: Upload a document and verify its hash against registered hash
- **Steps**:
  1. Select "Upload Document & Verify" mode
  2. Paste contract document content
  3. Click "Upload & Verify"
  4. System calculates SHA-256 hash and compares
  5. View VERIFIED or VERIFICATION FAILED result

## Example Proof ID

You can use any valid Proof ID from your blockchain transactions. For testing, you can:

1. Create a legal passport in the authenticated portal
2. Anchor it to blockchain
3. Use the returned Proof ID in the verification portal

## Verification Algorithm

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

## Displayed Information

1. Proof ID
2. Contract Identifier
3. Contract Version
4. Document Hash
5. Policy Hash
6. Analysis Hash
7. Evidence Hash
8. Blockchain Network (Ethereum Sepolia)
9. Transaction Hash
10. Block Number
11. Anchoring Timestamp
12. Verification Status (VERIFIED / FAILED)
13. Timestamp

## Security

- ✅ No authentication required
- ✅ No private contract contents exposed
- ✅ Only hashes and metadata shown
- ✅ Strict hash comparison (1-byte difference → fail)
- ✅ HTTPS encryption required

## Testing

Run the automated tests:

```bash
cd backend
pytest tests/test_public_verification.py -v
```

## API Endpoint

```
GET /verify/{proofId}?document_content={optional_document_content}
```

**Parameters**:
- `proofId` (required): Proof ID in hex format
- `document_content` (optional): Document content for hash comparison

**Response**:
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

## Troubleshooting

### Verification Fails

1. Check that the Proof ID is correct
2. Verify the document content matches exactly (case-sensitive)
3. Check that blockchain service is running
4. Verify Proof ID is not malformed

### 404 Not Found

1. Check that Proof ID is valid (64 hex characters)
2. Verify Proof ID was properly anchored to blockchain
3. Check that blockchain service is connected

### Verification Status Red

1. Document content differs from registered hash
2. Even one byte difference causes failure
3. Ensure exact match for verification success

## Visual Indicators

- **GREEN VERIFIED**: Large, bold text indicating successful verification
- **RED VERIFICATION FAILED**: Large, bold text indicating failed verification

## Copy Hashes

Click the "Copy" button next to any hash to copy it to clipboard.

## Support

For issues or questions, refer to:
- [Public Verification Portal Documentation](../docs/PUBLIC_VERIFICATION_PORTAL.md)
- [Blockchain Architecture](../docs/BLOCKCHAIN_ARCHITECTURE.md)
- [LexProof Architecture](../docs/LEXPROOF_ARCHITECTURE.md)
