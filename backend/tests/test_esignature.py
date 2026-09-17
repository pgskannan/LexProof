"""Unit tests for the e-signature provider abstraction: the stub's envelope
lifecycle, and get_esignature_provider()'s stub/DocuSign selection based on
whether real credentials are configured."""

import asyncio

import pytest

from app.lexproof.config.settings import LexProofSettings
from app.lexproof.services.esignature import (
    DocuSignProvider,
    ESignatureError,
    StubESignatureProvider,
    get_esignature_provider,
)
from tests.fakes import FakeRepository


def run(coro):
    return asyncio.run(coro)


def envelopes() -> FakeRepository:
    return FakeRepository("esignature_envelopes")


def reset():
    FakeRepository.stores = {"esignature_envelopes": {}}


def test_stub_create_envelope_starts_sent():
    reset()
    provider = StubESignatureProvider(envelopes=envelopes())
    envelope = run(
        provider.create_envelope(
            document_title="Redline for Acme MSA",
            document_text="...",
            signer_name="Jordan Chen",
            signer_email="jordan@example.com",
            metadata={"contract_id": "contract-1"},
        )
    )
    assert envelope["status"] == "sent"
    assert envelope["provider"] == "stub"
    assert envelope["envelope_id"].startswith("stub-")
    assert envelope["completed_at"] is None

    fetched = run(provider.get_envelope_status(envelope["envelope_id"]))
    assert fetched["status"] == "sent"


def test_stub_get_envelope_status_missing_envelope_raises():
    reset()
    provider = StubESignatureProvider(envelopes=envelopes())
    with pytest.raises(ESignatureError):
        run(provider.get_envelope_status("does-not-exist"))


def test_stub_simulate_completion_sets_certificate_and_is_terminal():
    reset()
    provider = StubESignatureProvider(envelopes=envelopes())
    envelope = run(
        provider.create_envelope(
            document_title="t", document_text="d", signer_name="Jordan", signer_email="j@example.com", metadata={}
        )
    )
    completed = run(provider.simulate_completion(envelope["envelope_id"]))
    assert completed["status"] == "completed"
    assert completed["certificate_url"]
    assert completed["completed_at"]

    with pytest.raises(ESignatureError):
        run(provider.simulate_completion(envelope["envelope_id"]))


def test_stub_simulate_completion_can_decline():
    reset()
    provider = StubESignatureProvider(envelopes=envelopes())
    envelope = run(
        provider.create_envelope(
            document_title="t", document_text="d", signer_name="Jordan", signer_email="j@example.com", metadata={}
        )
    )
    declined = run(provider.simulate_completion(envelope["envelope_id"], decline=True, decline_reason="No longer agreed"))
    assert declined["status"] == "declined"
    assert declined["decline_reason"] == "No longer agreed"
    assert declined["certificate_url"] is None


def test_get_esignature_provider_defaults_to_stub_without_credentials():
    settings = LexProofSettings()
    provider = get_esignature_provider(settings)
    assert provider.name == "stub"
    assert isinstance(provider, StubESignatureProvider)


def test_get_esignature_provider_selects_docusign_once_fully_configured():
    settings = LexProofSettings(
        docusign_integration_key="key",
        docusign_user_id="user",
        docusign_account_id="acct",
        docusign_private_key="-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
    )
    assert settings.has_esignature_configuration() is True
    provider = get_esignature_provider(settings)
    assert provider.name == "docusign"
    assert isinstance(provider, DocuSignProvider)


def test_get_esignature_provider_stays_stub_when_partially_configured():
    settings = LexProofSettings(docusign_integration_key="key", docusign_user_id="user")
    assert settings.has_esignature_configuration() is False
    provider = get_esignature_provider(settings)
    assert provider.name == "stub"
