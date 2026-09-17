"""Internal (org-scoped) and external (token-scoped) counterparty link endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..services.auth import get_current_org_member
from ..services.counterparty_links import (
    ATTESTATION_STATEMENT,
    CommentCapError,
    CounterpartyLinkError,
    CounterpartyLinkService,
    CountersignNotReadyError,
    LinkAlreadyCountersignedError,
    LinkExpiredError,
    LinkNotFoundError,
    LinkPermissionError,
    LinkRateLimitedError,
    LinkRevokedError,
    get_counterparty_link_service,
)
from ..services.esignature import ESignatureError

internal_router = APIRouter(prefix="/orgs/{org_id}/contracts/{contract_id}/counterparty-links", tags=["counterparty-links"])
external_router = APIRouter(prefix="/external", tags=["counterparty-links"])


class CreateCounterpartyLinkRequest(BaseModel):
    redline_proposal_id: str
    counterparty_name: str
    counterparty_email: str
    expires_in_days: int | None = Field(default=None, ge=1, le=90)
    permissions: list[str] | None = None


class ExternalCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ExternalCountersignRequest(BaseModel):
    typed_name: str
    attestation_accepted: bool
    attestation: str | None = None


class SimulateEsignatureRequest(BaseModel):
    decline: bool = False
    decline_reason: str | None = None


def _service() -> CounterpartyLinkService:
    return get_counterparty_link_service()


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, LinkNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, LinkExpiredError):
        return HTTPException(status_code=status.HTTP_410_GONE, detail=str(error))
    if isinstance(error, LinkRevokedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, LinkPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, LinkAlreadyCountersignedError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, LinkRateLimitedError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error))
    if isinstance(error, CommentCapError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error))
    if isinstance(error, CountersignNotReadyError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, CounterpartyLinkError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ESignatureError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@internal_router.post("", status_code=status.HTTP_201_CREATED)
def create_counterparty_link(
    org_id: str,
    contract_id: str,
    request: CreateCounterpartyLinkRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        return _service().create_link(
            org_id,
            contract_id,
            redline_proposal_id=request.redline_proposal_id,
            counterparty_name=request.counterparty_name,
            counterparty_email=request.counterparty_email,
            created_by=str(member["uid"]),
            expires_in_days=request.expires_in_days,
            permissions=request.permissions,
        )
    except (PermissionError, CounterpartyLinkError) as error:
        raise _http_error(error) from error


@internal_router.get("")
def list_counterparty_links(
    org_id: str,
    contract_id: str,
    redline_proposal_id: str | None = Query(None),
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        return _service().list_links(org_id, contract_id, str(member["uid"]), redline_proposal_id)
    except (PermissionError, CounterpartyLinkError) as error:
        raise _http_error(error) from error


@internal_router.post("/{token_id}/esignature", status_code=status.HTTP_201_CREATED)
async def send_counterparty_esignature(
    org_id: str,
    contract_id: str,
    token_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    """Route this link's redline to its counterparty for a real e-signature
    (DocuSign once configured, a zero-credential stub until then)."""
    try:
        return await _service().send_for_esignature(org_id, contract_id, token_id, str(member["uid"]))
    except (PermissionError, CounterpartyLinkError, ESignatureError) as error:
        raise _http_error(error) from error


@internal_router.get("/{token_id}/esignature")
async def get_counterparty_esignature_status(
    org_id: str,
    contract_id: str,
    token_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        return await _service().get_esignature_status(org_id, contract_id, token_id, str(member["uid"]))
    except (PermissionError, CounterpartyLinkError, ESignatureError) as error:
        raise _http_error(error) from error


@internal_router.post("/{token_id}/esignature/simulate")
async def simulate_counterparty_esignature(
    org_id: str,
    contract_id: str,
    token_id: str,
    request: SimulateEsignatureRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    """Stub-provider-only: stand in for the signer actually completing (or
    declining) the envelope, since there is no real DocuSign callback to
    wait for in this environment."""
    try:
        return await _service().simulate_esignature_completion(
            org_id,
            contract_id,
            token_id,
            str(member["uid"]),
            decline=request.decline,
            decline_reason=request.decline_reason,
        )
    except (PermissionError, CounterpartyLinkError, ESignatureError) as error:
        raise _http_error(error) from error


@external_router.get("/{token}")
def get_external_access(token: str):
    try:
        return _service().get_external_view(token)
    except CounterpartyLinkError as error:
        raise _http_error(error) from error


@external_router.post("/{token}/comment", status_code=status.HTTP_201_CREATED)
def add_external_comment(token: str, request: ExternalCommentRequest):
    try:
        return _service().add_comment(token, request.body)
    except CounterpartyLinkError as error:
        raise _http_error(error) from error


@external_router.post("/{token}/countersign")
async def countersign_external(token: str, request: ExternalCountersignRequest):
    if request.attestation is not None and request.attestation.strip() != ATTESTATION_STATEMENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attestation statement does not match the required wording",
        )
    try:
        return await _service().countersign(token, request.typed_name, request.attestation_accepted)
    except CounterpartyLinkError as error:
        raise _http_error(error) from error
