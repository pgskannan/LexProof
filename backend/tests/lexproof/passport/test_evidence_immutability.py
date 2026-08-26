"""P0.2 tests for anchored evidence immutability."""

import pytest

from app.lexproof.domains.passport.evidence_service import EvidenceService
from app.lexproof.domains.passport.models import EvidenceItemCreate, EvidenceItemUpdate
from app.lexproof.repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository


class MemoryRepository:
    def __init__(self):
        self.data = {}

    def get(self, document_id):
        return self.data.get(document_id)

    def set(self, document_id, data, merge=False):
        self.data[document_id] = {**self.data.get(document_id, {}), **data} if merge else data

    def delete(self, document_id):
        self.data.pop(document_id, None)


class Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self.data = data

    def to_dict(self):
        return self.data


class Document:
    def __init__(self, collection, document_id):
        self.collection = collection
        self.document_id = document_id

    def get(self):
        return Snapshot(self.collection.data.get(self.document_id))

    def set(self, data, merge=False):
        if merge:
            self.collection.data[self.document_id] = {
                **self.collection.data.get(self.document_id, {}),
                **data,
            }
        else:
            self.collection.data[self.document_id] = data

    def delete(self):
        self.collection.data.pop(self.document_id, None)


class Collection:
    def __init__(self):
        self.data = {}

    def document(self, document_id):
        return Document(self, document_id)


class Client:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, Collection())


def evidence_create():
    return EvidenceItemCreate(
        passport_id="passport-1",
        evidence_type="clause",
        title="Clause",
        content="Original",
        content_type="text/plain",
        source="manual_review",
    )


@pytest.mark.asyncio
async def test_unanchored_evidence_update_and_delete_are_allowed():
    evidence_repository = MemoryRepository()
    anchor_repository = MemoryRepository()
    service = EvidenceService(evidence_repository, anchor_repository=anchor_repository)
    evidence = await service.create_evidence_item("passport-1", evidence_create(), user=None)

    updated = await service.update_evidence_item(
        evidence.evidence_id,
        EvidenceItemUpdate(evidence_status="suspicious"),
    )

    assert updated is not None
    assert await service.delete_evidence_item(evidence.evidence_id) is True


@pytest.mark.asyncio
async def test_new_service_instance_can_mutate_unanchored_persisted_evidence():
    evidence_repository = MemoryRepository()
    anchor_repository = MemoryRepository()
    creator = EvidenceService(evidence_repository, anchor_repository=anchor_repository)
    evidence = await creator.create_evidence_item("passport-1", evidence_create(), user=None)
    updater = EvidenceService(evidence_repository, anchor_repository=anchor_repository)

    updated = await updater.update_evidence_item(
        evidence.evidence_id,
        EvidenceItemUpdate(evidence_status="suspicious"),
    )

    assert updated is not None
    assert evidence_repository.get(evidence.evidence_id)["evidence_status"] == "suspicious"


@pytest.mark.asyncio
async def test_anchored_evidence_update_delete_and_verification_are_rejected():
    evidence_repository = MemoryRepository()
    anchor_repository = MemoryRepository()
    service = EvidenceService(evidence_repository, anchor_repository=anchor_repository)
    evidence = await service.create_evidence_item("passport-1", evidence_create(), user=None)
    anchor_repository.set(evidence.evidence_id, {"evidence_hash": evidence.hash})
    original = service.evidence_items[evidence.evidence_id].model_copy(deep=True)

    with pytest.raises(ValueError, match="Anchored evidence cannot be modified"):
        await service.update_evidence_item(
            evidence.evidence_id,
            EvidenceItemUpdate(evidence_status="suspicious"),
        )
    with pytest.raises(ValueError, match="Anchored evidence cannot be modified"):
        await service.verify_evidence_item(evidence.evidence_id)
    with pytest.raises(ValueError, match="Anchored evidence cannot be modified"):
        await service.delete_evidence_item(evidence.evidence_id)

    assert service.evidence_items[evidence.evidence_id] == original


@pytest.mark.asyncio
async def test_new_evidence_id_can_represent_an_amendment_without_changing_v1():
    evidence_repository = MemoryRepository()
    anchor_repository = MemoryRepository()
    service = EvidenceService(evidence_repository, anchor_repository=anchor_repository)
    version_one = await service.create_evidence_item("passport-1", evidence_create(), user=None)
    anchor_repository.set(version_one.evidence_id, {"evidence_hash": version_one.hash})

    amended = evidence_create().model_copy(update={"content": "Amended"})
    version_two = await service.create_evidence_item("passport-1", amended, user=None)

    assert version_two.evidence_id != version_one.evidence_id
    assert version_two.hash != version_one.hash
    assert service.evidence_items[version_one.evidence_id].content == "Original"


def test_evidence_repository_rejects_overwrite_merge_and_delete_after_anchor():
    client = Client()
    anchors = EvidenceAnchorRepository("evidence_anchors", client=client)
    records = EvidenceRecordRepository(anchors, client=client)
    records.set("evidence-1", {"evidence_id": "evidence-1", "content": "Original"})
    anchors.set("evidence-1", {"evidence_hash": "a" * 64})

    with pytest.raises(ValueError, match="cannot be modified"):
        records.set("evidence-1", {"content": "Changed"})
    with pytest.raises(ValueError, match="cannot be modified"):
        records.set("evidence-1", {"content": "Changed"}, merge=True)
    with pytest.raises(ValueError, match="cannot be deleted"):
        records.delete("evidence-1")

    assert records.get("evidence-1")["content"] == "Original"

    client.collection("evidence_records").data.pop("evidence-1")
    with pytest.raises(ValueError, match="cannot be modified"):
        records.set("evidence-1", {"content": "Recreated"})


def test_anchor_repository_is_create_only():
    client = Client()
    anchors = EvidenceAnchorRepository("evidence_anchors", client=client)
    proof = {"evidence_hash": "a" * 64, "transaction_hash": "0xabc"}
    anchors.set("evidence-1", proof)

    with pytest.raises(ValueError, match="already exists"):
        anchors.set("evidence-1", {**proof, "block_number": 2})
    with pytest.raises(ValueError, match="cannot be deleted"):
        anchors.delete("evidence-1")

    assert anchors.get("evidence-1") == proof