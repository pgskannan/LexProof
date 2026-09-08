"""Compliance monitoring API endpoints for continuous legal compliance tracking."""

from typing import Annotated, Any, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from ..domains.compliance.models import (
    ComplianceMonitorService,
    RegulatoryChangeStatus,
    MonitoringEvent,
    ImpactLevel,
    ContractImpact,
)
from ..services.auth import get_current_user, load_org_member
from ..services.audit import record_audit_event

router = APIRouter(tags=["compliance"])


# Request/Response Models
class SimulateRegulatoryChangeRequest(BaseModel):
    """Request model for simulating a regulatory change."""

    title: str = Field(..., description="Title of the regulatory change")
    description: str = Field(..., description="Detailed description of the change")
    jurisdiction: str = Field(..., description="Jurisdiction where the change applies")
    effective_date: datetime = Field(..., description="When the change becomes effective")
    affected_topics: List[str] = Field(
        ..., description="Topics affected by this change (e.g., GDPR, CCPA)"
    )


class AffectedContractResponse(BaseModel):
    """Response model for an affected contract."""

    contract_id: str = Field(..., description="Contract ID")
    contract_name: str = Field(..., description="Contract name")
    industry: Optional[str] = Field(None, description="Contract industry")
    jurisdiction: Optional[str] = Field(None, description="Contract jurisdiction")
    data_processing: Optional[bool] = Field(None, description="Data processing activities")
    cross_border: Optional[bool] = Field(None, description="Cross-border data transfers")
    compliant: Optional[bool] = Field(None, description="Compliance status")
    impact_level: str = Field(..., description="Impact level (low, medium, high, critical)")
    impact_reason: str = Field(..., description="Reason for impact")
    affected_clause: Optional[str] = Field(None, description="Specific clause affected")
    missing_requirement: Optional[str] = Field(None, description="Missing requirement")
    recommended_action: str = Field(..., description="Recommended action")


class MonitoringEventResponse(BaseModel):
    """Response model for monitoring event."""

    id: str
    regulatory_change_id: str
    regulatory_change_title: str
    jurisdiction: str
    effective_date: datetime
    affected_contracts: List[AffectedContractResponse]
    total_affected: int
    status: RegulatoryChangeStatus
    created_at: datetime
    created_by: str
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None


class ComplianceCommandCenterResponse(BaseModel):
    """Response model for compliance command center dashboard."""

    total_contracts: int = Field(..., description="Total number of contracts")
    total_affected: int = Field(..., description="Total number of affected contracts")
    high_impact: int = Field(..., description="Contracts with high impact")
    medium_impact: int = Field(..., description="Contracts with medium impact")
    low_impact: int = Field(..., description="Contracts with low impact")
    events: List[MonitoringEventResponse] = Field(..., description="Monitoring events")


# Compliance Monitor Service Singleton
_compliance_service: Optional[ComplianceMonitorService] = None


def _seed_demo_compliance_events(service: ComplianceMonitorService) -> None:
    """Seed the Compliance Command Center with realistic demo monitoring
    events.

    ComplianceMonitorService keeps events in memory only (no repository is
    wired up here) and starts empty, so on every fresh backend process the
    Command Center page showed "No data available" -- unlike every other
    section of the app, which has real seeded demo content. There is also no
    UI anywhere that calls POST /compliance/simulate-change, so nothing could
    ever populate this page short of a raw API call. Seeding two realistic
    regulatory-change scenarios here (using the service's own existing
    simulate/approve workflow, not synthetic response data) gives the page
    real content consistent with the rest of the demo dataset, the same way
    the app's other seeded contracts/passports/findings do.
    """
    gdpr_event = service.simulate_regulatory_change(
        title="EU GDPR Cross-Border Data Transfer Amendment",
        description=(
            "Tightens requirements for cross-border transfers of personal data "
            "outside the EU, requiring updated standard contractual clauses and "
            "documented transfer impact assessments."
        ),
        jurisdiction="EU",
        effective_date=datetime.now() + timedelta(days=45),
        affected_topics=["GDPR", "cross-border data transfer", "data protection"],
    )
    service.approve_event(gdpr_event.id, approved=True)

    service.simulate_regulatory_change(
        title="California Consumer Privacy Act (CCPA) — Expanded Consumer Rights",
        description=(
            "Expands consumer opt-out and data-deletion rights and adds new "
            "disclosure obligations for businesses processing California "
            "residents' personal data."
        ),
        jurisdiction="US",
        effective_date=datetime.now() + timedelta(days=90),
        affected_topics=["CCPA", "data protection", "consumer privacy"],
    )


def get_compliance_service() -> ComplianceMonitorService:
    """Get or create compliance monitor service instance.

    Returns:
        ComplianceMonitorService instance
    """
    global _compliance_service
    if _compliance_service is None:
        _compliance_service = ComplianceMonitorService()
        _seed_demo_compliance_events(_compliance_service)
    return _compliance_service


@router.post(
    "/compliance/simulate-change",
    response_model=MonitoringEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Simulate a regulatory change",
    description="Simulate a regulatory change and identify affected contracts. "
    "For MVP, this is a controlled workflow that doesn't depend on live regulatory feeds. "
    "Returns affected contracts with impact levels, reasons, and recommendations.",
)
async def simulate_regulatory_change(
    request: SimulateRegulatoryChangeRequest,
) -> MonitoringEventResponse:
    """
    Simulate a regulatory change and identify affected contracts.

    SECURITY: This endpoint requires human approval before changes are applied.
    No automatic contract modification is performed.

    Args:
        request: Regulatory change details

    Returns:
        Monitoring event with affected contracts and impact analysis

    Raises:
        HTTPException: If simulation fails
    """
    try:
        # Get or create compliance service
        service = get_compliance_service()

        # Simulate regulatory change
        monitoring_event = service.simulate_regulatory_change(
            title=request.title,
            description=request.description,
            jurisdiction=request.jurisdiction,
            effective_date=request.effective_date,
            affected_topics=request.affected_topics,
        )

        # Convert to response model
        return MonitoringEventResponse(
            id=monitoring_event.id,
            regulatory_change_id=monitoring_event.regulatory_change_id,
            regulatory_change_title=monitoring_event.regulatory_change_title,
            jurisdiction=monitoring_event.jurisdiction,
            effective_date=monitoring_event.effective_date,
            affected_contracts=[
                AffectedContractResponse(
                    contract_id=contract["contract_id"],
                    contract_name=contract["contract_name"],
                    industry=contract.get("industry"),
                    jurisdiction=contract.get("jurisdiction"),
                    data_processing=contract.get("data_processing"),
                    cross_border=contract.get("cross_border"),
                    compliant=contract.get("compliant"),
                    impact_level=contract["impact_level"],
                    impact_reason=contract["impact_reason"],
                    affected_clause=contract.get("affected_clause"),
                    missing_requirement=contract.get("missing_requirement"),
                    recommended_action=contract["recommended_action"],
                )
                for contract in monitoring_event.affected_contracts
            ],
            total_affected=monitoring_event.total_affected,
            status=monitoring_event.status,
            created_at=monitoring_event.created_at,
            created_by=monitoring_event.created_by,
            approved_at=monitoring_event.approved_at,
            approved_by=monitoring_event.approved_by,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error simulating regulatory change: {str(e)}",
        )


@router.get(
    "/compliance/command-center",
    response_model=ComplianceCommandCenterResponse,
    summary="Get compliance command center dashboard",
    description="Returns overview of compliance monitoring status including total contracts, "
    "affected contracts, and impact levels across all monitoring events.",
)
async def get_compliance_command_center() -> ComplianceCommandCenterResponse:
    """
    Get compliance command center dashboard with overview metrics.

    Returns:
        Compliance command center statistics

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        service = get_compliance_service()
        events = service.get_all_events()

        # Calculate totals
        distinct_contract_ids: set[str] = set()
        total_affected = 0
        high_impact = 0
        medium_impact = 0
        low_impact = 0

        for event in events:
            total_affected += event.total_affected

            for contract in event.affected_contracts:
                distinct_contract_ids.add(contract["contract_id"])
                impact_level = contract["impact_level"]
                if impact_level == "high":
                    high_impact += 1
                elif impact_level == "medium":
                    medium_impact += 1
                elif impact_level == "low":
                    low_impact += 1

        # This service tracks contracts only via the ones referenced in
        # monitoring events (it has no independent view of "every contract in
        # the org" -- see _identify_affected_contracts's synthetic sample
        # data), so "total contracts" is the distinct set seen across events
        # rather than a hardcoded 0.
        total_contracts = len(distinct_contract_ids)

        return ComplianceCommandCenterResponse(
            total_contracts=total_contracts,
            total_affected=total_affected,
            high_impact=high_impact,
            medium_impact=medium_impact,
            low_impact=low_impact,
            events=[
                MonitoringEventResponse(
                    id=event.id,
                    regulatory_change_id=event.regulatory_change_id,
                    regulatory_change_title=event.regulatory_change_title,
                    jurisdiction=event.jurisdiction,
                    effective_date=event.effective_date,
                    affected_contracts=[
                        AffectedContractResponse(
                            contract_id=contract["contract_id"],
                            contract_name=contract["contract_name"],
                            industry=contract.get("industry"),
                            jurisdiction=contract.get("jurisdiction"),
                            data_processing=contract.get("data_processing"),
                            cross_border=contract.get("cross_border"),
                            compliant=contract.get("compliant"),
                            impact_level=contract["impact_level"],
                            impact_reason=contract["impact_reason"],
                            affected_clause=contract.get("affected_clause"),
                            missing_requirement=contract.get("missing_requirement"),
                            recommended_action=contract["recommended_action"],
                        )
                        for contract in event.affected_contracts
                    ],
                    total_affected=event.total_affected,
                    status=event.status,
                    created_at=event.created_at,
                    created_by=event.created_by,
                    approved_at=event.approved_at,
                    approved_by=event.approved_by,
                )
                for event in events
            ],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving compliance command center: {str(e)}",
        )


@router.get(
    "/compliance/events/{event_id}",
    response_model=MonitoringEventResponse,
    summary="Get a specific monitoring event",
    description="Retrieve details of a specific monitoring event including all affected contracts.",
)
async def get_monitoring_event(event_id: str) -> MonitoringEventResponse:
    """
    Get a specific monitoring event by ID.

    Args:
        event_id: Monitoring event ID

    Returns:
        Monitoring event details

    Raises:
        HTTPException: If event not found
    """
    try:
        service = get_compliance_service()
        event = service.get_monitoring_event(event_id)

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring event {event_id} not found",
            )

        return MonitoringEventResponse(
            id=event.id,
            regulatory_change_id=event.regulatory_change_id,
            regulatory_change_title=event.regulatory_change_title,
            jurisdiction=event.jurisdiction,
            effective_date=event.effective_date,
            affected_contracts=[
                AffectedContractResponse(
                    contract_id=contract["contract_id"],
                    contract_name=contract["contract_name"],
                    industry=contract.get("industry"),
                    jurisdiction=contract.get("jurisdiction"),
                    data_processing=contract.get("data_processing"),
                    cross_border=contract.get("cross_border"),
                    compliant=contract.get("compliant"),
                    impact_level=contract["impact_level"],
                    impact_reason=contract["impact_reason"],
                    affected_clause=contract.get("affected_clause"),
                    missing_requirement=contract.get("missing_requirement"),
                    recommended_action=contract["recommended_action"],
                )
                for contract in event.affected_contracts
            ],
            total_affected=event.total_affected,
            status=event.status,
            created_at=event.created_at,
            created_by=event.created_by,
            approved_at=event.approved_at,
            approved_by=event.approved_by,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving monitoring event: {str(e)}",
        )


@router.post(
    "/compliance/events/{event_id}/approve",
    response_model=MonitoringEventResponse,
    summary="Approve or reject a monitoring event",
    description=(
        "Approve or reject a monitoring event. Approval is required before any "
        "automatic actions are taken. No automatic contract modification occurs."
    ),
)
async def approve_monitoring_event(
    event_id: str,
    approved: bool,
    user: dict[str, Any] = Depends(get_current_user),
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> MonitoringEventResponse:
    """
    Approve or reject a monitoring event.

    SECURITY: Human approval is required before any automatic actions.
    No automatic contract modification is performed.

    Args:
        event_id: Monitoring event ID
        approved: Whether to approve (True) or reject (False) the event

    Returns:
        Updated monitoring event

    Raises:
        HTTPException: If event not found or approval fails
    """
    try:
        service = get_compliance_service()
        event = service.approve_event(event_id, approved)
        org_id = None
        if x_org_id and x_org_id.strip():
            try:
                org_id = load_org_member(x_org_id.strip(), user)["org_id"]
            except HTTPException:
                org_id = None
        record_audit_event(
            actor_id=str(user["uid"]),
            actor_email=user.get("email"),
            action="compliance.event_approved" if approved else "compliance.event_rejected",
            resource_type="compliance_event",
            resource_id=event.id,
            resource_name=event.regulatory_change_title,
            summary=f"{'Approved' if approved else 'Rejected'} compliance event \"{event.regulatory_change_title}\"",
            org_id=org_id,
        )

        return MonitoringEventResponse(
            id=event.id,
            regulatory_change_id=event.regulatory_change_id,
            regulatory_change_title=event.regulatory_change_title,
            jurisdiction=event.jurisdiction,
            effective_date=event.effective_date,
            affected_contracts=[
                AffectedContractResponse(
                    contract_id=contract["contract_id"],
                    contract_name=contract["contract_name"],
                    industry=contract.get("industry"),
                    jurisdiction=contract.get("jurisdiction"),
                    data_processing=contract.get("data_processing"),
                    cross_border=contract.get("cross_border"),
                    compliant=contract.get("compliant"),
                    impact_level=contract["impact_level"],
                    impact_reason=contract["impact_reason"],
                    affected_clause=contract.get("affected_clause"),
                    missing_requirement=contract.get("missing_requirement"),
                    recommended_action=contract["recommended_action"],
                )
                for contract in event.affected_contracts
            ],
            total_affected=event.total_affected,
            status=event.status,
            created_at=event.created_at,
            created_by=event.created_by,
            approved_at=event.approved_at,
            approved_by=event.approved_by,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error approving monitoring event: {str(e)}",
        )


# Background task for scheduled monitoring
def schedule_periodic_monitoring():
    """Schedule periodic compliance monitoring (placeholder for Google Cloud Scheduler)."""
    # TODO: Integrate with Google Cloud Scheduler
    # TODO: Integrate with Cloud Tasks for async processing
    pass


# TODO: Add Google Cloud Scheduler integration
# TODO: Add Cloud Tasks integration for async processing
# TODO: Add scheduled monitoring job that runs at configured intervals
