# Public Verification Portal - Quick Reference

## URL
```
http://localhost:3000/public-verify
```

## API Endpoint
```
GET /verify/{proofId}?document_content={optional}
```

## Verification Modes

### Mode A: Verify Registered Contract
- **What**: View verification details
- **Input**: Proof ID only
- **Steps**:
  1. Select "Verify Registered Contract"
  2. Enter Proof ID
  3. Click "Verify Contract"

### Mode B: Upload Document & Verify
- **What**: Upload and verify document hash
- **Input**: Document content
- **Steps**:
  1. Select "Upload Document & Verify"
  2. Paste document content
  3. Click "Upload & Verify"

## Status Indicators

### GREEN VERIFIED
```
    VERIFIED
VERIFICATION FAILED
```
- All hashes match
- Document is authentic

### RED VERIFICATION FAILED
```
    VERIFICATION FAILED
VERIFIED
```
- Hashes don't match
- Document modified

## 11 Display Fields

1. **Proof ID** - Unique blockchain identifier
2. **Contract Identifier** - Contract name/ID
3. **Contract Version** - Version number
4. **Document Hash** - SHA-256 of contract
5. **Policy Hash** - SHA-256 of policy
6. **Analysis Hash** - SHA-256 of analysis
7. **Evidence Hash** - SHA-256 of evidence
8. **Blockchain Network** - Ethereum Sepolia
9. **Transaction Hash** - Blockchain transaction
10. **Block Number** - Block where proof anchored
11. **Anchoring Timestamp** - When proof anchored

## Quick Test

### Test Mode A (Verify)
```
1. Open portal
2. Select "Verify Registered Contract"
3. Enter: 0x1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
4. Click "Verify Contract"
5. Check result
```

### Test Mode B (Upload)
```
1. Open portal
2. Select "Upload Document & Verify"
3. Paste: "Test contract content"
4. Click "Upload & Verify"
5. Check result
```

## Security

- ✅ No login required
- ✅ No private content exposed
- ✅ Only hashes shown
- ✅ HTTPS required
- ✅ Strict hash comparison

## Troubleshooting

### 404 Not Found
- Proof ID invalid or doesn't exist
- Check Proof ID format (64 hex chars)
- Verify Proof ID was anchored

### Verification Failed
- Document differs by 1 byte
- Hashes don't match exactly
- Copy and paste exact content

### Blockchain Error
- Service unavailable
- Check blockchain RPC connection
- Verify smart contract deployed

## Copy Hashes

Click "Copy" button next to any hash to copy to clipboard.

## API Response

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

## File Locations

- **Frontend**: `frontend/app/public-verify/page.tsx`
- **Backend**: `backend/app/lexproof/api/blockchain.py`
- **Tests**: `backend/tests/test_public_verification.py`
- **Docs**: `docs/PUBLIC_VERIFICATION_PORTAL.md`

## Running Tests

```bash
cd backend
pytest tests/test_public_verification.py -v
```

## Support

- Documentation: `docs/PUBLIC_VERIFICATION_PORTAL.md`
- Architecture: `docs/BLOCKCHAIN_ARCHITECTURE.md`
- Sprint Summary: `docs/SPRINT4_SUMMARY.md`
