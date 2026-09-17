"""E-signature provider abstraction.

A redline that has already been internally approved can be routed to the
counterparty for a real, legally-recognized e-signature, as a higher-trust
alternative to the lightweight in-app typed-name countersignature flow that
``CounterpartyLinkService.countersign()`` already provides.

Per this engagement's "stub-now, wire in real credentials later" scope
decision:

- ``StubESignatureProvider`` is the default and needs zero credentials. It
  fully implements the envelope lifecycle (sent -> completed/declined) so
  every API path and UI affordance is real and clickable today; only the
  "a human opens the email and clicks through DocuSign" step is simulated,
  via an explicit ``simulate_completion`` call instead of a real webhook.
- ``DocuSignProvider`` is a complete, real integration against DocuSign's
  eSignature REST API (JWT Grant auth + envelope creation), so switching
  from stub to production is a matter of setting four environment
  variables (DOCUSIGN_INTEGRATION_KEY, DOCUSIGN_USER_ID,
  DOCUSIGN_ACCOUNT_ID, DOCUSIGN_PRIVATE_KEY) -- no code changes anywhere
  else, since ``get_esignature_provider()`` picks it automatically once
  configured.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

import httpx

from ..config import LexProofSettings, get_settings
from ..repositories.firestore import FirestoreRepository

logger = logging.getLogger(__name__)

ENVELOPES_COLLECTION = "esignature_envelopes"
TERMINAL_STATUSES = frozenset({"completed", "declined", "voided"})


class ESignatureError(ValueError):
    """Base error for e-signature provider/envelope failures."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ESignatureProvider(Protocol):
    name: str

    async def create_envelope(
        self,
        *,
        document_title: str,
        document_text: str,
        signer_name: str,
        signer_email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def get_envelope_status(self, envelope_id: str) -> dict[str, Any]: ...


class StubESignatureProvider:
    """Zero-credential provider: a fully working envelope lifecycle, with
    completion/decline triggered explicitly (``simulate_completion``)
    instead of a real signer's click and a real webhook callback."""

    name = "stub"

    def __init__(self, *, envelopes: FirestoreRepository | None = None) -> None:
        self.envelopes = envelopes or FirestoreRepository(ENVELOPES_COLLECTION)

    async def create_envelope(
        self,
        *,
        document_title: str,
        document_text: str,
        signer_name: str,
        signer_email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        envelope_id = f"stub-{uuid4()}"
        now = _now_iso()
        record = {
            "envelope_id": envelope_id,
            "provider": self.name,
            "status": "sent",
            "document_title": document_title,
            "signer_name": signer_name,
            "signer_email": signer_email,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "decline_reason": None,
            "sign_url": f"/esignature/stub/{envelope_id}",
            "certificate_url": None,
            "metadata": metadata,
        }
        self.envelopes.set(envelope_id, record)
        logger.info("stub e-signature envelope created envelope_id=%s signer=%s", envelope_id, signer_email)
        return record

    async def get_envelope_status(self, envelope_id: str) -> dict[str, Any]:
        record = self.envelopes.get(envelope_id)
        if not record:
            raise ESignatureError(f"Envelope not found: {envelope_id}")
        return record

    async def simulate_completion(
        self, envelope_id: str, *, decline: bool = False, decline_reason: str | None = None
    ) -> dict[str, Any]:
        """Stub-only: stands in for the signer actually opening the email
        and clicking through DocuSign, since there is no real provider here
        to do that. Moves a ``sent`` envelope to its terminal state."""
        record = self.envelopes.get(envelope_id)
        if not record:
            raise ESignatureError(f"Envelope not found: {envelope_id}")
        if record.get("status") in TERMINAL_STATUSES:
            raise ESignatureError(f"Envelope is already {record['status']}")
        now = _now_iso()
        updates: dict[str, Any] = {"updated_at": now, "completed_at": now}
        if decline:
            updates["status"] = "declined"
            updates["decline_reason"] = decline_reason or "Declined by signer"
        else:
            updates["status"] = "completed"
            updates["certificate_url"] = f"/esignature/stub/{envelope_id}/certificate"
        self.envelopes.set(envelope_id, updates, merge=True)
        return {**record, **updates}


class DocuSignProvider:
    """Real DocuSign eSignature REST API integration (JWT Grant auth).
    Inert until DOCUSIGN_INTEGRATION_KEY/USER_ID/ACCOUNT_ID/PRIVATE_KEY are
    all configured -- ``get_esignature_provider()`` only ever constructs
    this once that is true, so it is never exercised without real
    credentials."""

    name = "docusign"

    def __init__(
        self,
        *,
        integration_key: str,
        user_id: str,
        account_id: str,
        private_key_pem: str,
        base_url: str,
        auth_server: str,
        envelopes: FirestoreRepository | None = None,
    ) -> None:
        self.integration_key = integration_key
        self.user_id = user_id
        self.account_id = account_id
        self.private_key_pem = private_key_pem
        self.base_url = base_url.rstrip("/")
        self.auth_server = auth_server
        self.envelopes = envelopes or FirestoreRepository(ENVELOPES_COLLECTION)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        import jwt  # local import: only ever exercised on this real-provider path

        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self.integration_key,
                "sub": self.user_id,
                "aud": self.auth_server,
                "iat": now,
                "exp": now + 3600,
                "scope": "signature impersonation",
            },
            self.private_key_pem,
            algorithm="RS256",
        )
        async with httpx.AsyncClient(base_url=f"https://{self.auth_server}", timeout=30.0) as client:
            response = await client.post(
                "/oauth/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            )
        if response.status_code != 200:
            raise ESignatureError(f"DocuSign authentication failed: {response.text}")
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    async def create_envelope(
        self,
        *,
        document_title: str,
        document_text: str,
        signer_name: str,
        signer_email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        token = await self._access_token()
        document_b64 = base64.b64encode(document_text.encode("utf-8")).decode("ascii")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            response = await client.post(
                f"/v2.1/accounts/{self.account_id}/envelopes",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "emailSubject": f"Please sign: {document_title}",
                    "documents": [
                        {
                            "documentBase64": document_b64,
                            "name": document_title,
                            "fileExtension": "txt",
                            "documentId": "1",
                        }
                    ],
                    "recipients": {
                        "signers": [
                            {
                                "email": signer_email,
                                "name": signer_name,
                                "recipientId": "1",
                                "routingOrder": "1",
                                "tabs": {
                                    "signHereTabs": [
                                        {"anchorString": "/sig/", "anchorUnits": "pixels", "anchorXOffset": "0", "anchorYOffset": "0"}
                                    ]
                                },
                            }
                        ]
                    },
                    "status": "sent",
                },
            )
        if response.status_code not in (200, 201):
            raise ESignatureError(f"DocuSign envelope creation failed: {response.text}")
        payload = response.json()
        envelope_id = payload.get("envelopeId")
        now = _now_iso()
        record = {
            "envelope_id": envelope_id,
            "provider": self.name,
            "status": (payload.get("status") or "sent").lower(),
            "document_title": document_title,
            "signer_name": signer_name,
            "signer_email": signer_email,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "decline_reason": None,
            "sign_url": None,
            "certificate_url": None,
            "metadata": metadata,
        }
        self.envelopes.set(envelope_id, record)
        logger.info("docusign envelope created envelope_id=%s signer=%s", envelope_id, signer_email)
        return record

    async def get_envelope_status(self, envelope_id: str) -> dict[str, Any]:
        token = await self._access_token()
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            response = await client.get(
                f"/v2.1/accounts/{self.account_id}/envelopes/{envelope_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            raise ESignatureError(f"DocuSign envelope status lookup failed: {response.text}")
        payload = response.json()
        status_value = (payload.get("status") or "sent").lower()
        updates: dict[str, Any] = {"status": status_value, "updated_at": _now_iso()}
        if status_value == "completed":
            updates["completed_at"] = payload.get("completedDateTime") or _now_iso()
        self.envelopes.set(envelope_id, updates, merge=True)
        record = self.envelopes.get(envelope_id) or {}
        return {**record, **updates, "envelope_id": envelope_id}


def get_esignature_provider(settings: LexProofSettings | None = None) -> ESignatureProvider:
    settings = settings or get_settings()
    if settings.has_esignature_configuration():
        return DocuSignProvider(
            integration_key=settings.docusign_integration_key,
            user_id=settings.docusign_user_id,
            account_id=settings.docusign_account_id,
            private_key_pem=settings.docusign_private_key.get_secret_value(),
            base_url=settings.docusign_base_url,
            auth_server=settings.docusign_auth_server,
        )
    return StubESignatureProvider()
