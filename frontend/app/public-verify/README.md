# Public Evidence Verification

## Endpoint

Public verification is exposed at:

```http
GET /api/verify/{evidence_id}
```

This is the live evidence-anchor verification endpoint. It does not use a legacy proof ID and it does not accept document content in the request body or query string.

## Verification flow

The route follows this real verification sequence:

1. Accept an `evidence_id` in the URL.
2. Fetch the evidence record from Firestore.
3. Recompute the evidence hash with `hash_evidence_item()` using the same canonical hashing logic used during anchoring.
4. Fetch the anchor metadata and on-chain hash from Ethereum via `EthereumAnchorService.verify_evidence()`.
5. Compare the recomputed hash with the hash stored on-chain.
6. Return one of four statuses:
   - `VERIFIED`
   - `TAMPERED`
   - `EVIDENCE_NOT_FOUND`
   - `ANCHOR_NOT_FOUND`

## Response contract

```json
{
  "evidence_id": "evd_123",
  "verified": true,
  "status": "VERIFIED",
  "evidence_hash_on_chain": "0xabc123...",
  "computed_hash": "def456...",
  "blockchain_network": "ethereum-sepolia",
  "contract_address": "0x1111111111111111111111111111111111111111",
  "transaction_hash": "0x987654...",
  "block_number": 12345678,
  "anchored_at": "2025-01-15T12:34:56+00:00",
  "timestamp": "2025-01-15T12:35:00.123456"
}
```

### Status meanings

- `VERIFIED`: Evidence exists, an anchor exists, and the recomputed hash matches the on-chain hash.
- `TAMPERED`: Evidence exists and is anchored, but the current evidence has changed since it was anchored.
- `EVIDENCE_NOT_FOUND`: No evidence record exists in Firestore for the supplied `evidence_id`.
- `ANCHOR_NOT_FOUND`: The evidence exists, but no Ethereum anchor was found for it.

## HTTP behavior

- An empty or blank `evidence_id` in the URL returns HTTP 404.
- `EVIDENCE_NOT_FOUND` and `ANCHOR_NOT_FOUND` return HTTP 200 with `verified: false`.
- The endpoint never returns raw evidence content, titles, or score values.

## Security expectations

- No authentication is required for public verification.
- Only hashes and blockchain metadata are returned.
- No `document_content`, `title`, `content`, or score fields are exposed.
- Any mutation after anchoring is detected by hash mismatch.

## Example

```bash
curl http://localhost:8000/api/verify/evd_123
```

## Old routes

The legacy route `/verify/{proof_id}` no longer exists. The public verifier now uses the evidence-based endpoint only.
