"""Tests for server-side passport integrity verification."""

import json

import pytest

from app.lexproof.domains.passport.integrity import verify_passport_integrity
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.domains.passport.utils.hashing import compute_passport_hash


def _analysis_engine():
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
                "risk_impact": 25,
                "compliance_impact": 15,
                "source_section": "Section 1",
                "evidence_quote": "Quote text",
            }],
            "key_clauses": ["Section 1"],
            "compliance_items": ["Policy"],
        }

    return engine


async def _create_passport(contract_id: str) -> tuple[PassportService, object]:
    service = PassportService(_analysis_engine(), user_id="user", tenant_id="tenant")
    passport = await service.create_passport(
        contract_id=contract_id,
        contract_version=1,
        policy_version="policy-1",
        document_content="Sample contract text",
        normalized_document="sample contract text",
        policy_content="Sample policy",
    )
    evidence_items = await service.get_evidence(passport.passport_id)
    return service, passport, evidence_items


@pytest.mark.asyncio
async def test_verify_passport_integrity_valid_passport():
    """A valid persisted passport should verify true."""
    _, passport, evidence_items = await _create_passport("contract-123")

    result = verify_passport_integrity(
        passport.model_dump(mode="json"),
        evidence_items=evidence_items,
    )
    assert result["verified"] is True
    assert result["document_verified"] is True
    assert result["policy_verified"] is True
    assert result["analysis_verified"] is True
    assert result["evidence_verified"] is True
    assert result["passport_hash_verified"] is True
    assert result["stored_passport_hash"] == result["recomputed_passport_hash"]


@pytest.mark.asyncio
async def test_verify_passport_integrity_modified_evidence_fails():
    """Mutating the evidence hash should invalidate the passport."""
    _, passport, evidence_items = await _create_passport("contract-124")
    data = passport.model_dump(mode="json")
    data["evidence_hash"] = "a" * 64

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is False
    assert result["evidence_verified"] is False
    assert result["passport_hash_verified"] is False


@pytest.mark.asyncio
async def test_verify_passport_integrity_modified_analysis_fails():
    """Mutating the analysis hash should invalidate the passport."""
    _, passport, evidence_items = await _create_passport("contract-125")
    data = passport.model_dump(mode="json")
    data["analysis_hash"] = "b" * 64

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is False
    assert result["analysis_verified"] is False
    assert result["passport_hash_verified"] is False


@pytest.mark.asyncio
async def test_verify_passport_integrity_modified_document_fingerprint_fails():
    """Mutating document_hash should invalidate the passport."""
    _, passport, evidence_items = await _create_passport("contract-126")
    data = passport.model_dump(mode="json")
    data["document_hash"] = "c" * 64

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is False
    assert result["document_verified"] is False
    assert result["passport_hash_verified"] is False


@pytest.mark.asyncio
async def test_verify_passport_integrity_modified_policy_fingerprint_fails():
    """Mutating policy_hash should invalidate the passport."""
    _, passport, evidence_items = await _create_passport("contract-127")
    data = passport.model_dump(mode="json")
    data["policy_hash"] = "d" * 64

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is False
    assert result["policy_verified"] is False
    assert result["passport_hash_verified"] is False


@pytest.mark.asyncio
async def test_verify_passport_integrity_modified_passport_hash_fails():
    """Mutating metadata.passport_hash should invalidate the passport."""
    _, passport, evidence_items = await _create_passport("contract-128")
    data = passport.model_dump(mode="json")
    data["metadata"]["passport_hash"] = "e" * 64

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is False
    assert result["passport_hash_verified"] is False


@pytest.mark.asyncio
async def test_verify_passport_integrity_analysis_snapshot_tampering_detected():
    """Mutating the stored analysis snapshot should fail even if the stored hash fields remain unchanged."""
    _, passport, evidence_items = await _create_passport("contract-analysis-tamper")
    data = passport.model_dump(mode="json")
    original_risk_score = data["metadata"]["verification_snapshot"]["analysis_result"]["risk_score"]

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is True
    assert result["analysis_verified"] is True

    data["metadata"]["verification_snapshot"]["analysis_result"]["risk_score"] = original_risk_score + 1
    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["analysis_verified"] is False
    assert result["verified"] is False
    assert result["passport_hash_verified"] is True

    data["metadata"]["verification_snapshot"]["analysis_result"]["risk_score"] = original_risk_score
    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["analysis_verified"] is True
    assert result["verified"] is True


@pytest.mark.asyncio
async def test_verify_passport_integrity_evidence_snapshot_tampering_detected():
    """Mutating the publish-time snapshot should fail; live evidence mutations must not."""
    _, passport, evidence_items = await _create_passport("contract-evidence-tamper")
    data = passport.model_dump(mode="json")
    snapshot_items = data["metadata"]["verification_snapshot"]["evidence_items"]
    original_quote = snapshot_items[0]["metadata"]["evidence_quote"]

    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["verified"] is True
    assert result["evidence_verified"] is True

    snapshot_items[0]["metadata"]["evidence_quote"] = "Tampered evidence quote"
    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["evidence_verified"] is False
    assert result["verified"] is False
    assert result["passport_hash_verified"] is True

    snapshot_items[0]["metadata"]["evidence_quote"] = original_quote
    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["evidence_verified"] is True
    assert result["verified"] is True

    live = [json.loads(json.dumps(item)) for item in evidence_items]
    live[0]["metadata"]["evidence_quote"] = "Live mutation should not matter"
    result = verify_passport_integrity(data, evidence_items=live)
    assert result["evidence_verified"] is True
    assert result["verified"] is True


@pytest.mark.asyncio
async def test_legacy_passport_ignores_post_publish_evidence_appends():
    """Passports published before snapshot.evidence_items must not FAIL when later evidence is appended."""
    from datetime import datetime, timedelta, timezone

    from app.lexproof.domains.passport.utils.hashing import hash_evidence_package

    published = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def item(evidence_id: str, created_at: str, evidence_type: str = "clause") -> dict:
        return {
            "evidence_id": evidence_id,
            "passport_id": "legacy-passport",
            "evidence_type": evidence_type,
            "title": evidence_id,
            "description": "",
            "content": "clause text",
            "content_type": "text/plain",
            "risk_impact": 10,
            "compliance_impact": 10,
            "evidence_status": "valid",
            "contract_reference": "",
            "policy_reference": "",
            "analysis_reference": "",
            "source": "test",
            "source_id": evidence_id,
            "metadata": {},
            "created_at": created_at,
        }

    original = [item("e1", published.isoformat())]
    later = item("e2", (published + timedelta(days=1)).isoformat())
    countersign = item("e3", published.isoformat(), "counterparty_countersignature")
    evidence_hash = hash_evidence_package(original)
    data = {
        "document_hash": "d" * 64,
        "policy_hash": "e" * 64,
        "analysis_hash": "f" * 64,
        "evidence_hash": evidence_hash,
        "created_at": published.isoformat(),
        "metadata": {
            "passport_hash": compute_passport_hash("d" * 64, "e" * 64, "f" * 64, evidence_hash),
            "verification_snapshot": {},
        },
    }

    result = verify_passport_integrity(data, evidence_items=original + [later, countersign])
    assert result["evidence_verified"] is True
    assert result["verified"] is True

    tampered = [{**original[0], "title": "tampered"}]
    failed = verify_passport_integrity(data, evidence_items=tampered + [later])
    assert failed["evidence_verified"] is False
    assert failed["verified"] is False


def test_verify_passport_integrity_deterministic_recomputation():
    """The canonical passport hash must be deterministic."""
    data = {
        "document_hash": "d" * 64,
        "policy_hash": "e" * 64,
        "analysis_hash": "f" * 64,
        "evidence_hash": "g" * 64,
        "metadata": {"passport_hash": compute_passport_hash("d" * 64, "e" * 64, "f" * 64, "g" * 64)},
    }
    first = verify_passport_integrity(data)
    second = verify_passport_integrity(data)

    assert first == second
    assert first["verified"] is True
    assert first["passport_hash_verified"] is True
    assert first["stored_passport_hash"] == first["recomputed_passport_hash"]


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
        return _FakeSnapshot(
            self._store.get(self._document_id),
            document_id=self._document_id,
        )

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


@pytest.mark.asyncio
async def test_passport_evidence_hash_survives_firestore_round_trip():
    """Creation evidence hash must equal recomputation from persisted evidence."""
    from app.lexproof.domains.passport.utils.hashing import hash_evidence_package
    from app.lexproof.repositories.firestore import FirestoreRepository

    _, passport, evidence_items = await _create_passport(
        "contract-firestore-roundtrip"
    )

    fake_client = _FakeFirestoreClient()

    repository = FirestoreRepository(
        "evidence_records",
        client=fake_client,
    )

    for item in evidence_items:
        item_data = (
            item
            if isinstance(item, dict)
            else item.model_dump(mode="json")
        )

        repository.set(
            item_data["evidence_id"],
            {
                **item_data,
                "id": item_data["evidence_id"],
                "owner_id": "user",
            },
        )

    persisted_items = list(repository.stream())

    assert persisted_items

    recomputed_evidence_hash = hash_evidence_package(
        persisted_items
    )

    assert recomputed_evidence_hash == passport.evidence_hash
