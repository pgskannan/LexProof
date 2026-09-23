# LexProof Evidence Canonicalization Spec (v1)

**Status:** Documents **current** production behavior.  
**Version:** `canonicalization_version` is not stored on existing records. This document is **v1**. A future incompatible change MUST introduce an explicit version field rather than silently changing SHA-256 input bytes.  
**Do not** treat this as a proposal to normalize numbers or Unicode.

Server source of truth: `backend/app/lexproof/domains/passport/utils/hashing.py` (`compute_sha256_hash`, `canonicalize_evidence_item`).

---

## Algorithm

```text
SHA-256
digest: lowercase hexadecimal, 64 characters
library: Python hashlib.sha256
salt / prefix / version byte: none
```

## Encoding

```text
UTF-8
```

Strings and JSON text are encoded with `.encode("utf-8")` before hashing. Raw `bytes` are hashed as-is.

## JSON canonicalization

For `dict` and `list` values:

```text
json.dumps(data, sort_keys=True, ensure_ascii=False)
```

Default separators are `(", ", ": ")` (space after `:` and `,`). Object keys are sorted at every nested object. This is v1. There is no RFC 8785 / JCS implementation.

## Arrays

Order-sensitive. Lists are **not** sorted. Changing `["a", "b"]` to `["b", "a"]` changes the hash.

Evidence **package** order is independent of input list order because items are sorted by `evidence_id` before hashing. That is package assembly, not array canonicalization inside an item.

## Strings

Whitespace is preserved. `"Test"`, `" Test"`, `"Test "`, and `"Test\n"` are different evidence.

## Unicode

No NFC/NFD normalization. NFC `café` (`caf\u00e9`) and NFD `cafe\u0301` hash differently.

`ensure_ascii=False` keeps non-ASCII code points in the JSON text (not `\uXXXX` escaped unless the character is a JSON control character).

## Numbers

Python `json.dumps` type distinction is part of v1:

```text
95    → 95
95.0  → 95.0
"95"  → "95"

95 != 95.0
```

at the byte/canonicalization level. This is defined behavior, not a bug in SHA-256.

Booleans are not numbers: `True`/`False` are JSON `true`/`false`. `bool` is a `int` subclass in Python, but `json.dumps(True)` emits `true`, not `1`.

## Missing vs null

`canonicalize_evidence_item` uses `dict.get(field)`, so a missing `EVIDENCE_HASH_FIELDS` key and an explicit `None` both become JSON `null`. Extra keys outside that tuple are omitted.

## Booleans

JSON `true` / `false` (lowercase).

## Nested objects

Hashed as nested JSON with `sort_keys=True` at each object. Nested list order is significant. Nested number types follow the same `95` vs `95.0` rule.

## Evidence field boundary (v1)

Included: `evidence_id`, `passport_id`, `evidence_type`, `title`, `description`, `content`, `content_type`, `risk_impact`, `compliance_impact`, `evidence_status`, `contract_reference`, `policy_reference`, `analysis_reference`, `source`, `source_id`, `metadata`.

Excluded: `created_at`, `verified_at`, `hash`, `owner_id`, `contract_id`, `contract_version`, and any other operational field.

## Document / policy / analysis / passport envelopes (v1)

- Document: `{"hash_algorithm": "sha256", "normalized": "...", "original": "..."}`
- Policy: `policy_id`, `version`, `content`, `metadata`
- Analysis: `analysis_type`, `model`, `timestamp`, `result`
- Package: `{"evidence_count": N, "evidence_items": [canonical items sorted by evidence_id]}`
- Passport root: the four stored component hashes plus `"passport_hash_algorithm": "sha256"`

## JavaScript companion (not the chain source of truth)

`frontend/lib/evidenceHash.ts` uses the same field list and JSON spacing, but JavaScript `Number` cannot distinguish `95` from `95.0`. It emits `95` for both. Ethereum VERIFY and passport VERIFY on the server use Python. A float-valued `risk_impact` in an API JSON body can make the browser local hash disagree with the Python/on-chain digest.

**Future (not implemented):** if client and server must match on floats, add `canonicalization_version: 2` with an explicit numeric encoding. Do not change v1 bytes; existing Sepolia item anchors use Python `json.dumps`.
