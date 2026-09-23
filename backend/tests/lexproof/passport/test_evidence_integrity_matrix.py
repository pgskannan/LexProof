"""Deterministic evidence-integrity matrix.

Expected SHA-256 digests are independent hashlib+json constants. They are not
produced by calling hash_evidence_item / compute_sha256_hash at runtime.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone

import pytest

from app.lexproof.domains.passport.integrity import verify_passport_integrity
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.domains.passport.utils.hashing import (
    EVIDENCE_HASH_FIELDS,
    canonicalize_evidence_item,
    hash_evidence_item,
    hash_evidence_package,
    verify_hash_consistency,
)
from app.lexproof.repositories.firestore import FirestoreRepository


def _independent_sha256(obj: object) -> str:
    canonical_bytes = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


GOLDEN_EVIDENCE = {
    "evidence_id": "golden-1",
    "passport_id": "passport-golden",
    "evidence_type": "clause",
    "title": "Test evidence",
    "description": "Test evidence",
    "content": "canonical evidence body",
    "content_type": "text/plain",
    "risk_impact": 95,
    "compliance_impact": 10,
    "evidence_status": "valid",
    "contract_reference": "",
    "policy_reference": "",
    "analysis_reference": "",
    "source": "test",
    "source_id": "src-1",
    "metadata": {"amount": 95, "status": "active"},
}

# SHA-256 of json.dumps(canonicalize(GOLDEN_EVIDENCE), sort_keys=True, ensure_ascii=False)
GOLDEN_ITEM_HASH = "cca985e44ad52a9909656d6b221ed0690c5ba5a9f443038ea0144fd15bf2cec6"
GOLDEN_ITEM_96_HASH = "2180a1b8a4eaed6628f43ee0800b166476858de85f239122c388d7c632142166"
GOLDEN_PACKAGE_HASH = "c82efaf97cf21df4f874d1ce9b72431bfbffb4820848c3d26c0ecd5bc5d5bf0e"
GOLDEN_PACKAGE_96_HASH = "14068f193f0fade259d947995a6e92d7758788bd3cec655b2cc485699cda4028"
GOLDEN_EMPTY_PACKAGE_HASH = "5f5bb14ee04ebf972636aa0cde27fec09ba2514c4f78a25346a90330cba65113"
GOLDEN_FLOAT_95_HASH = "16111e1094765bd57b4bc9cde76b1ec377626450bdb9528514e3cf554a9c38be"
GOLDEN_NESTED_95_HASH = "bc1832c83468ad31ea23dbba74a6ce4a39d4cecc5e1dac5177d7757c7e94b987"
GOLDEN_NESTED_96_HASH = "0a37be66ead33ee89e53e230b671229606f4f676135b00e0708f9a73c65364a5"
GOLDEN_LIST_AB_HASH = "c5cb4cab1c97b0236f8766278bb08b334c54b3c348a67acaaf10b814a13f1912"
GOLDEN_LIST_AC_HASH = "4991f1feaa4cd9a250023a7c6eacd055023072d3f95cc40161b6fe97ab6d1c64"
GOLDEN_LIST_BA_HASH = "e1076af63cbc0a017df7cbada5002fe55c98a113d1ac30698860df21adbc96ff"
GOLDEN_TRAILING_SPACE_HASH = "017c968631ec83c4c9cbdb98b1a7a23d13dc9346d822251b1f0c743be3bd89d6"
GOLDEN_TRAILING_NEWLINE_HASH = "1e4db95d989dce60095ba1fa3af084b2c0055a244dff48135ec90cd1f984fe14"
GOLDEN_NFC_TITLE_HASH = "98b95ed664a561fa8a4def7bfffced18259671ce6ac7e984851f4e139146a443"
GOLDEN_NFD_TITLE_HASH = "cf08dfba0b2d856ea2aff3a80247745b86e5059c2ffcb2c61ed8cb8d9628b793"
GOLDEN_FRONTEND_FIXTURE_HASH = "e8c40d43edd6d5dca9fa220c8333001a0e0318456d6f6a2852e2658a2810e9fc"
MINI_OBJECT_95_HASH = "e1af26d0290f15b872b34839dc7b93195832cea629dc6c93189fe48cd30f5243"
MINI_OBJECT_96_HASH = "7164f589887d77871563b851533c922fa077c8574644f87b46c6a00f51a45511"
MINI_OBJECT_95_FLOAT_HASH = "045a85e7fd8c214e2164c965fc32c79b91fded9de9dd6c62f73d184000612fdf"
MINI_OBJECT_95_STRING_HASH = "223815ec374fbea4c6ccfcb8785811c82cae91bf7aeb265f8ea9f1a03d21f0c7"


def _golden(**overrides):
    item = dict(GOLDEN_EVIDENCE)
    item.update(overrides)
    return item


def _analysis_engine(risk_impact: int = 95):
    async def engine(_document: str, _policy: str) -> dict:
        return {
            "risk_score": 35,
            "risk_level": "medium",
            "compliance_score": 85,
            "findings": [{
                "title": "Finding 1",
                "severity": "high",
                "description": "Finding description",
                "evidence": "Evidence text",
                "recommendation": "Recommendation text",
                "risk_impact": risk_impact,
                "compliance_impact": 15,
                "source_section": "Section 1",
                "evidence_quote": "Quote text",
            }],
            "key_clauses": ["Section 1"],
            "compliance_items": ["Policy"],
        }

    return engine


class _FakeSnapshot:
    def __init__(self, data, document_id=None):
        self._data = data
        self.id = document_id
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeDocument:
    def __init__(self, store, document_id):
        self._store = store
        self._document_id = document_id

    def set(self, data, merge=False):
        if merge and self._document_id in self._store:
            self._store[self._document_id].update(data)
        else:
            self._store[self._document_id] = dict(data)

    def get(self):
        return _FakeSnapshot(self._store.get(self._document_id), document_id=self._document_id)

    def delete(self):
        self._store.pop(self._document_id, None)


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, document_id):
        return _FakeDocument(self._store, document_id)

    def stream(self):
        return [
            _FakeSnapshot(data, document_id=document_id)
            for document_id, data in self._store.items()
        ]


class _FakeFirestoreClient:
    def __init__(self):
        self._collections = {}

    def collection(self, collection):
        return _FakeCollection(self._collections.setdefault(collection, {}))


def test_independent_constants_match_documented_algorithm():
    canonical = canonicalize_evidence_item(GOLDEN_EVIDENCE)
    assert _independent_sha256(canonical) == GOLDEN_ITEM_HASH
    assert _independent_sha256({"amount": 95, "description": "Test evidence", "status": "active"}) == MINI_OBJECT_95_HASH
    assert _independent_sha256({
        "evidence_count": 1,
        "evidence_items": [canonicalize_evidence_item(GOLDEN_EVIDENCE)],
    }) == GOLDEN_PACKAGE_HASH
    assert _independent_sha256({"evidence_count": 0, "evidence_items": []}) == GOLDEN_EMPTY_PACKAGE_HASH


def test_golden_item_hash_matches_independent_digest():
    canonical = canonicalize_evidence_item(GOLDEN_EVIDENCE)
    expected_bytes = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    assert hashlib.sha256(expected_bytes).hexdigest() == GOLDEN_ITEM_HASH
    assert hash_evidence_item(GOLDEN_EVIDENCE) == GOLDEN_ITEM_HASH
    assert hash_evidence_package([GOLDEN_EVIDENCE]) == GOLDEN_PACKAGE_HASH


def test_golden_frontend_fixture_matches_independent_digest():
    fixture = {
        "evidence_id": "e-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "metadata": {"key": "value"},
    }
    assert hash_evidence_item(fixture) == GOLDEN_FRONTEND_FIXTURE_HASH
    assert _independent_sha256(canonicalize_evidence_item(fixture)) == GOLDEN_FRONTEND_FIXTURE_HASH


def test_identical_original_data_passes():
    stored = hash_evidence_item(GOLDEN_EVIDENCE)
    computed = hash_evidence_item(dict(GOLDEN_EVIDENCE))
    assert verify_hash_consistency(computed, stored) is True
    assert stored == GOLDEN_ITEM_HASH


def test_amount_95_to_96_fails_and_restore_passes():
    original = _golden()
    stored = hash_evidence_item(original)
    assert stored == GOLDEN_ITEM_HASH

    original["risk_impact"] = 96
    original["metadata"] = {"amount": 96, "status": "active"}
    tampered = hash_evidence_item(original)
    assert tampered == GOLDEN_ITEM_96_HASH
    assert verify_hash_consistency(tampered, stored) is False

    original["risk_impact"] = 95
    original["metadata"] = {"amount": 95, "status": "active"}
    restored = hash_evidence_item(original)
    assert restored == GOLDEN_ITEM_HASH
    assert verify_hash_consistency(restored, stored) is True


def test_dictionary_key_order_does_not_change_hash():
    reordered = {
        "metadata": {"status": "active", "amount": 95},
        "title": "Test evidence",
        "source_id": "src-1",
        "source": "test",
        "analysis_reference": "",
        "policy_reference": "",
        "contract_reference": "",
        "evidence_status": "valid",
        "compliance_impact": 10,
        "risk_impact": 95,
        "content_type": "text/plain",
        "content": "canonical evidence body",
        "description": "Test evidence",
        "evidence_type": "clause",
        "passport_id": "passport-golden",
        "evidence_id": "golden-1",
    }
    assert hash_evidence_item(reordered) == GOLDEN_ITEM_HASH


def test_json_object_key_order_mini_vector():
    first = {"amount": 95, "description": "Test evidence", "status": "active"}
    second = {"status": "active", "amount": 95, "description": "Test evidence"}
    assert _independent_sha256(first) == MINI_OBJECT_95_HASH
    assert _independent_sha256(second) == MINI_OBJECT_95_HASH
    assert _independent_sha256({"amount": 96, "description": "Test evidence", "status": "active"}) == MINI_OBJECT_96_HASH


def test_material_text_and_whitespace_are_significant():
    stored = GOLDEN_ITEM_HASH
    assert hash_evidence_item(_golden(content="canonical evidence body!")) != stored
    assert hash_evidence_item(_golden(content="canonical evidence body ")) == GOLDEN_TRAILING_SPACE_HASH
    assert hash_evidence_item(_golden(content="canonical evidence body\n")) == GOLDEN_TRAILING_NEWLINE_HASH
    assert hash_evidence_item(_golden(content=" canonical evidence body")) != stored
    assert verify_hash_consistency(hash_evidence_item(_golden(content="canonical evidence body ")), stored) is False


def test_nested_value_change_fails():
    nested_95 = _golden(metadata={"amount": 95, "nested": {"score": 95}, "status": "active"})
    nested_96 = _golden(metadata={"amount": 95, "nested": {"score": 96}, "status": "active"})
    assert hash_evidence_item(nested_95) == GOLDEN_NESTED_95_HASH
    assert hash_evidence_item(nested_96) == GOLDEN_NESTED_96_HASH
    assert hash_evidence_item(nested_95) != hash_evidence_item(nested_96)


def test_list_item_and_list_order_are_significant():
    tags_ab = _golden(metadata={"tags": ["a", "b"]})
    tags_ac = _golden(metadata={"tags": ["a", "c"]})
    tags_ba = _golden(metadata={"tags": ["b", "a"]})
    assert hash_evidence_item(tags_ab) == GOLDEN_LIST_AB_HASH
    assert hash_evidence_item(tags_ac) == GOLDEN_LIST_AC_HASH
    assert hash_evidence_item(tags_ba) == GOLDEN_LIST_BA_HASH
    assert hash_evidence_item(tags_ab) != hash_evidence_item(tags_ac)
    assert hash_evidence_item(tags_ab) != hash_evidence_item(tags_ba)


def test_added_field_outside_hash_boundary_passes():
    extra = _golden(owner_id="attacker", contract_id="other-contract", created_at="2099-01-01T00:00:00+00:00")
    extra["hash"] = "deadbeef"
    extra["verified_at"] = "2099-01-01T00:00:00+00:00"
    assert hash_evidence_item(extra) == GOLDEN_ITEM_HASH


def test_removed_or_missing_hash_field_matches_explicit_none():
    missing = {field: GOLDEN_EVIDENCE[field] for field in EVIDENCE_HASH_FIELDS if field != "analysis_reference"}
    explicit_none = _golden(analysis_reference=None)
    assert hash_evidence_item(missing) == hash_evidence_item(explicit_none)


def test_added_material_field_changes_hash():
    with_quote = _golden(description="Test evidence with extra material")
    assert hash_evidence_item(with_quote) != GOLDEN_ITEM_HASH


def test_unicode_nfc_and_nfd_are_distinct():
    nfc = "caf\u00e9"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert hash_evidence_item(_golden(title=nfc)) == GOLDEN_NFC_TITLE_HASH
    assert hash_evidence_item(_golden(title=nfd)) == GOLDEN_NFD_TITLE_HASH
    assert GOLDEN_NFC_TITLE_HASH != GOLDEN_NFD_TITLE_HASH


def test_numeric_95_vs_95_dot_0_vs_string_are_distinct():
    """Current Python json.dumps semantics: int, float, and string are different bytes."""
    as_int = _golden(risk_impact=95)
    as_float = _golden(risk_impact=95.0)
    as_string = _golden(risk_impact="95")
    assert hash_evidence_item(as_int) == GOLDEN_ITEM_HASH
    assert hash_evidence_item(as_float) == GOLDEN_FLOAT_95_HASH
    assert hash_evidence_item(as_int) != hash_evidence_item(as_float)
    assert hash_evidence_item(as_int) != hash_evidence_item(as_string)
    assert _independent_sha256({"amount": 95.0, "description": "Test evidence", "status": "active"}) == MINI_OBJECT_95_FLOAT_HASH
    assert _independent_sha256({"amount": "95", "description": "Test evidence", "status": "active"}) == MINI_OBJECT_95_STRING_HASH
    assert MINI_OBJECT_95_HASH != MINI_OBJECT_95_FLOAT_HASH
    assert MINI_OBJECT_95_HASH != MINI_OBJECT_95_STRING_HASH
    assert json.dumps(95.0) == "95.0"
    assert json.dumps(95) == "95"


def test_pydantic_float_dump_keeps_python_95_dot_0_bytes():
    """GET/API JSON of EvidenceItem numeric fields uses JSON floats.

    Passport CREATE often stores AI JSON ints. EvidenceItem.model_dump_json()
    emits 95.0 / 10.0. Python hashing of that dump therefore differs from the
    int golden item. The browser then parses 95.0 as IEEE 95 and serializes
    "95". Do not change v1 hashes to hide this; see EVIDENCE_CANONICALIZATION_SPEC.
    """
    from datetime import datetime, timezone

    from app.lexproof.domains.passport.models.evidence_item import EvidenceItem

    item = EvidenceItem(
        evidence_id="golden-1",
        passport_id="passport-golden",
        evidence_type="clause",
        title="Test evidence",
        description="Test evidence",
        content="canonical evidence body",
        content_type="text/plain",
        risk_impact=95.0,
        compliance_impact=10,
        evidence_status="valid",
        contract_reference="",
        policy_reference="",
        analysis_reference="",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="test",
        source_id="src-1",
        metadata={"amount": 95, "status": "active"},
    )
    dumped = json.loads(item.model_dump_json())
    assert dumped["risk_impact"] == 95.0
    assert json.dumps(dumped["risk_impact"]) == "95.0"
    assert json.dumps(dumped["compliance_impact"]) == "10.0"
    assert hash_evidence_item(dumped) != GOLDEN_ITEM_HASH
    assert hash_evidence_item(_golden(risk_impact=95.0)) == GOLDEN_FLOAT_95_HASH


def test_timestamps_are_excluded_including_timezone_equivalents():
    naive = _golden(created_at="2026-01-01T00:00:00")
    utc = _golden(created_at="2026-01-01T00:00:00+00:00")
    offset = _golden(created_at="2026-01-01T01:00:00+01:00")
    assert hash_evidence_item(naive) == GOLDEN_ITEM_HASH
    assert hash_evidence_item(utc) == GOLDEN_ITEM_HASH
    assert hash_evidence_item(offset) == GOLDEN_ITEM_HASH


def test_one_character_content_change_fails():
    stored = GOLDEN_ITEM_HASH
    changed = hash_evidence_item(_golden(content="canonical evidence Body"))
    assert verify_hash_consistency(changed, stored) is False


def test_create_persist_retrieve_verify_round_trip():
    repository = FirestoreRepository("evidence_records", client=_FakeFirestoreClient())
    created_hash = hash_evidence_item(GOLDEN_EVIDENCE)
    assert created_hash == GOLDEN_ITEM_HASH

    repository.set(
        GOLDEN_EVIDENCE["evidence_id"],
        {
            **GOLDEN_EVIDENCE,
            "id": GOLDEN_EVIDENCE["evidence_id"],
            "owner_id": "user-1",
            "contract_id": "contract-1",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            "hash": created_hash,
        },
    )
    retrieved = repository.get(GOLDEN_EVIDENCE["evidence_id"])
    assert retrieved is not None
    computed = hash_evidence_item(retrieved)
    assert verify_hash_consistency(computed, created_hash) is True
    assert hash_evidence_package([retrieved]) == GOLDEN_PACKAGE_HASH


def test_persist_tamper_verify_fails_then_restore_passes():
    repository = FirestoreRepository("evidence_records", client=_FakeFirestoreClient())
    repository.set("golden-1", {**GOLDEN_EVIDENCE, "id": "golden-1", "hash": GOLDEN_ITEM_HASH})
    stored_hash = GOLDEN_ITEM_HASH

    retrieved = repository.get("golden-1")
    retrieved["risk_impact"] = 96
    retrieved["metadata"] = {"amount": 96, "status": "active"}
    repository.set("golden-1", retrieved)

    tampered = repository.get("golden-1")
    assert hash_evidence_item(tampered) == GOLDEN_ITEM_96_HASH
    assert verify_hash_consistency(hash_evidence_item(tampered), stored_hash) is False

    tampered["risk_impact"] = 95
    tampered["metadata"] = {"amount": 95, "status": "active"}
    repository.set("golden-1", tampered)
    restored = repository.get("golden-1")
    assert verify_hash_consistency(hash_evidence_item(restored), stored_hash) is True


@pytest.mark.asyncio
async def test_passport_create_persist_retrieve_verify_passes():
    service = PassportService(_analysis_engine(95), user_id="user", tenant_id="tenant")
    passport = await service.create_passport(
        contract_id="contract-integrity-roundtrip",
        contract_version=1,
        policy_version="policy-1",
        document_content="Sample contract text",
        normalized_document="sample contract text",
        policy_content="Sample policy",
    )
    evidence_items = await service.get_evidence(passport.passport_id)

    client = _FakeFirestoreClient()
    passports = FirestoreRepository("legal_passports", client=client)
    evidence = FirestoreRepository("evidence_records", client=client)
    passports.set(passport.passport_id, {**passport.model_dump(mode="json"), "id": passport.passport_id})
    for item in evidence_items:
        evidence.set(item["evidence_id"], {**item, "id": item["evidence_id"]})

    stored_passport = passports.get(passport.passport_id)
    stored_evidence = list(evidence.stream())
    result = verify_passport_integrity(stored_passport, evidence_items=stored_evidence)
    assert result["verified"] is True
    assert result["evidence_verified"] is True
    assert result["document_verified"] is True
    assert result["passport_hash_verified"] is True


@pytest.mark.asyncio
async def test_passport_snapshot_95_to_96_fails_and_restore_passes():
    service = PassportService(_analysis_engine(95), user_id="user", tenant_id="tenant")
    passport = await service.create_passport(
        contract_id="contract-integrity-tamper",
        contract_version=1,
        policy_version="policy-1",
        document_content="Sample contract text",
        normalized_document="sample contract text",
        policy_content="Sample policy",
    )
    evidence_items = await service.get_evidence(passport.passport_id)
    data = passport.model_dump(mode="json")
    snapshot_item = data["metadata"]["verification_snapshot"]["evidence_items"][0]
    original_impact = snapshot_item["risk_impact"]
    assert original_impact == 95

    snapshot_item["risk_impact"] = 96
    failed = verify_passport_integrity(data, evidence_items=evidence_items)
    assert failed["evidence_verified"] is False
    assert failed["verified"] is False

    snapshot_item["risk_impact"] = 95
    restored = verify_passport_integrity(data, evidence_items=evidence_items)
    assert restored["evidence_verified"] is True
    assert restored["verified"] is True


@pytest.mark.asyncio
async def test_emptied_snapshot_evidence_items_fails():
    service = PassportService(_analysis_engine(95), user_id="user", tenant_id="tenant")
    passport = await service.create_passport(
        contract_id="contract-empty-snapshot",
        contract_version=1,
        policy_version="policy-1",
        document_content="Sample contract text",
        normalized_document="sample contract text",
        policy_content="Sample policy",
    )
    evidence_items = await service.get_evidence(passport.passport_id)
    data = passport.model_dump(mode="json")
    data["metadata"]["verification_snapshot"]["evidence_items"] = []

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["evidence_verified"] is False
    assert result["verified"] is False
    assert hash_evidence_package([]) == GOLDEN_EMPTY_PACKAGE_HASH


@pytest.mark.asyncio
async def test_material_live_mutation_is_ignored_when_snapshot_exists():
    service = PassportService(_analysis_engine(95), user_id="user", tenant_id="tenant")
    passport = await service.create_passport(
        contract_id="contract-live-ignored",
        contract_version=1,
        policy_version="policy-1",
        document_content="Sample contract text",
        normalized_document="sample contract text",
        policy_content="Sample policy",
    )
    live = [json.loads(json.dumps(item)) for item in await service.get_evidence(passport.passport_id)]
    live[0]["content"] = "tampered live content"
    live[0]["risk_impact"] = 96
    result = verify_passport_integrity(passport.model_dump(mode="json"), evidence_items=live)
    assert result["evidence_verified"] is True
    assert result["verified"] is True
