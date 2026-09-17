"""Integration tests for e-signature routing through CounterpartyLinkService:
sending an envelope, the stub-completion path recording evidence and
countersigning the link the same way the in-app typed-name flow does, and
the guardrails (already-countersigned, non-member, non-stub-simulate)."""

import asyncio

import pytest

from app.lexproof.services.counterparty_links import LinkAlreadyCountersignedError
from app.lexproof.services.esignature import DocuSignProvider, ESignatureError
from tests.fakes import FakeRepository
from tests.test_counterparty_links import ORG_ID, make_service, seed_data

ESIGN_STORE = "esignature_envelopes"


def run(coro):
    return asyncio.run(coro)


def _approved_link(service):
    return service.create_link(
        ORG_ID,
        "contract-1",
        redline_proposal_id="proposal-1",
        counterparty_name="Jordan Chen",
        counterparty_email="jordan@counterparty.example",
        created_by="owner-1",
    )


def _seed():
    seed_data()
    FakeRepository.stores[ESIGN_STORE] = {}


def test_send_for_esignature_creates_stub_envelope_and_is_idempotent():
    _seed()
    service = make_service()
    link = _approved_link(service)

    first = run(service.send_for_esignature(ORG_ID, "contract-1", link["token_id"], "owner-1"))
    assert first["status"] == "sent"
    assert first["provider"] == "stub"

    listed = service.list_links(ORG_ID, "contract-1", "owner-1")
    assert listed[0]["esignature_envelope_id"] == first["envelope_id"]
    assert listed[0]["esignature_status"] == "sent"

    second = run(service.send_for_esignature(ORG_ID, "contract-1", link["token_id"], "owner-1"))
    assert second["envelope_id"] == first["envelope_id"]


def test_simulate_completion_records_evidence_and_countersigns_link():
    _seed()
    service = make_service()
    link = _approved_link(service)
    run(service.send_for_esignature(ORG_ID, "contract-1", link["token_id"], "owner-1"))

    result = run(service.simulate_esignature_completion(ORG_ID, "contract-1", link["token_id"], "owner-1"))

    assert result["status"] == "completed"
    listed = service.list_links(ORG_ID, "contract-1", "owner-1")
    assert listed[0]["countersigned"] is True
    evidence_id = listed[0]["countersign_evidence_id"]
    assert evidence_id
    evidence = FakeRepository("evidence_records").get(evidence_id)
    assert evidence["source"] == "esignature_stub"
    assert evidence["evidence_type"] == "counterparty_countersignature"


def test_simulate_decline_does_not_countersign():
    _seed()
    service = make_service()
    link = _approved_link(service)
    run(service.send_for_esignature(ORG_ID, "contract-1", link["token_id"], "owner-1"))

    result = run(
        service.simulate_esignature_completion(
            ORG_ID, "contract-1", link["token_id"], "owner-1", decline=True, decline_reason="Changed their mind"
        )
    )

    assert result["status"] == "declined"
    listed = service.list_links(ORG_ID, "contract-1", "owner-1")
    assert listed[0]["countersigned"] is False
    assert listed[0]["countersign_evidence_id"] is None


def test_cannot_send_for_esignature_after_already_countersigned():
    _seed()
    service = make_service()
    link = _approved_link(service)
    run(service.countersign(link["token"], "Jordan Chen", True))

    with pytest.raises(LinkAlreadyCountersignedError):
        run(service.send_for_esignature(ORG_ID, "contract-1", link["token_id"], "owner-1"))


def test_non_member_cannot_send_for_esignature():
    _seed()
    service = make_service()
    link = _approved_link(service)

    with pytest.raises(PermissionError):
        run(service.send_for_esignature(ORG_ID, "contract-1", link["token_id"], "stranger-1"))


def test_simulate_completion_requires_stub_provider():
    _seed()
    service = make_service()
    service.esignature_provider = DocuSignProvider(
        integration_key="k",
        user_id="u",
        account_id="a",
        private_key_pem="pem",
        base_url="https://example.invalid",
        auth_server="account-d.docusign.com",
        envelopes=FakeRepository(ESIGN_STORE),
    )
    link = _approved_link(service)

    with pytest.raises(ESignatureError):
        run(service.simulate_esignature_completion(ORG_ID, "contract-1", link["token_id"], "owner-1"))
