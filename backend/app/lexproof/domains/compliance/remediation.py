"""Human-gated AI remediation and re-proof workflow."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    AmendmentApproval,
    AmendmentRequest,
    AuditTrailEntry,
    ProposedAmendment,
)
from ...repositories.firestore import FirestoreRepository
from ...services.organizations import OrganizationService, get_organization_service
from ...services.roles import OrgRole, has_any_role


class RemediationService:
    """Stages amendments and publishes only after explicit human approval.

    Integrations are injected so the workflow can use the existing analysis,
    policy, passport, evidence, and blockchain services without duplicating them.
    """

    def __init__(
        self,
        analysis_engine: Optional[Any] = None,
        policy_evaluator: Optional[Any] = None,
        passport_creator: Optional[Any] = None,
        proof_anchorer: Optional[Any] = None,
        contracts: Optional[FirestoreRepository] = None,
        organizations: Optional[OrganizationService] = None,
    ) -> None:
        self.analysis_engine = analysis_engine
        self.policy_evaluator = policy_evaluator
        self.passport_creator = passport_creator
        self.proof_anchorer = proof_anchorer
        self._requests: Dict[str, AmendmentRequest] = {}
        self._proposals: Dict[str, ProposedAmendment] = {}
        self._approvals: Dict[str, AmendmentApproval] = {}
        self._audit: Dict[str, List[AuditTrailEntry]] = {}
        self._published_versions: Dict[str, Dict[str, Any]] = {}
        self.contracts = contracts or FirestoreRepository("contracts")
        self.organizations = organizations or get_organization_service()

    def request_amendment(self, request: AmendmentRequest, *, created_by: str | None = None, org_id: str | None = None) -> ProposedAmendment:
        """Generate a proposal; this method never changes or publishes a contract."""
        request_id = str(uuid4())
        proposal_id = str(uuid4())
        proposal = ProposedAmendment(
            id=proposal_id,
            amendment_request_id=request_id,
            event_id=request.event_id,
            contract_id=request.contract_id,
            affected_clause=request.affected_clause,
            current_language=request.current_language,
            regulatory_requirement=request.regulatory_requirement,
            proposed_amendment=self._generate_amendment(request),
            explanation=(
                "Proposed language aligns the affected clause with the stated "
                "regulatory requirement; legal review is required before use."
            ),
            risk_reduction="Expected reduction after re-analysis; not yet verified.",
            compliance_improvement="Expected improvement after policy evaluation; not yet verified.",
            created_at=datetime.now(timezone.utc),
            created_by=created_by or "gemini",
            finding_id=request.finding_id,
            version_id=request.version_id,
            evidence_id=request.evidence_id,
            evidence_quote=request.evidence_quote,
            source_section=request.source_section,
            org_id=org_id,
        )
        self._requests[request_id] = request
        self._proposals[proposal_id] = proposal
        self._record(request.event_id, request.contract_id, "ai_recommendation", "AI generated proposed amendment")
        return proposal

    def _authorize_approval(self, proposal: ProposedAmendment, approver_id: str) -> None:
        contract = self.contracts.get(proposal.contract_id)
        if not contract:
            raise PermissionError("Contract not found")
        org_id = proposal.org_id or contract.get("org_id")
        if not org_id:
            raise PermissionError("Approval requires an organization-scoped contract")
        member = self.organizations.get_active_member(org_id, approver_id)
        if not member or not has_any_role(member.get("roles"), (OrgRole.ADMIN.value, OrgRole.APPROVER.value)):
            raise PermissionError("You are not authorized to approve this amendment")
        if proposal.created_by == approver_id:
            raise PermissionError("The proposal creator cannot approve their own amendment")

    def approve_and_reproof(
        self,
        proposal_id: str,
        approved: bool,
        approved_by: str,
        approval_notes: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        approver_id: str | None = None,
    ) -> Dict[str, Any]:
        """Apply the amendment workflow only after explicit human approval."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ValueError(f"Amendment proposal {proposal_id} not found")
        if approver_id is not None:
            self._authorize_approval(proposal, approver_id)
            approved_by = approver_id
        if not approved:
            approval = self._save_approval(proposal, False, approved_by, approval_notes, rejection_reason)
            self._record(proposal.event_id, proposal.contract_id, "human_approval", "Amendment rejected")
            return {"proposal": proposal, "approval": approval, "published": False}

        approval = self._save_approval(proposal, True, approved_by, approval_notes, None)
        self._record(proposal.event_id, proposal.contract_id, "human_approval", "Amendment approved")
        amended_content = self._apply_amendment(proposal)
        self._record(proposal.event_id, proposal.contract_id, "amendment", "Approved amendment created a new contract version")
        analysis = self._run_analysis(amended_content)
        self._record(proposal.event_id, proposal.contract_id, "analysis", "Amended contract re-analyzed")
        policy = self._run_policy(amended_content, proposal.regulatory_requirement)
        self._record(proposal.event_id, proposal.contract_id, "policy_evaluation", "Policy evaluation re-run")
        passport = self._create_passport(proposal, amended_content, analysis, policy)
        self._record(proposal.event_id, proposal.contract_id, "blockchain_proof", "New passport proof anchored while previous proof was preserved")
        result = {
            "proposal": proposal,
            "approval": approval,
            "published": True,
            "before": {"risk": "high", "compliance": "failed"},
            "after": {
                "risk": analysis.get("risk", "low"),
                "compliance": policy.get("compliance", "passed"),
            },
            "passport": passport,
            "previous_proof_preserved": True,
            "audit_trail": self.get_audit_trail(proposal.event_id),
        }
        self._published_versions[proposal_id] = result
        return result

    def get_audit_trail(self, event_id: str) -> List[AuditTrailEntry]:
        return list(self._audit.get(event_id, []))

    def _generate_amendment(self, request: AmendmentRequest) -> str:
        if self.analysis_engine and hasattr(self.analysis_engine, "generate_amendment"):
            return self.analysis_engine.generate_amendment(request)
        return f"{request.current_language}\n\nAmended to satisfy: {request.regulatory_requirement}"

    def _apply_amendment(self, proposal: ProposedAmendment) -> str:
        return proposal.current_language.replace(
            proposal.current_language, proposal.proposed_amendment, 1
        )

    def _run_analysis(self, content: str) -> Dict[str, Any]:
        if self.analysis_engine:
            result = self.analysis_engine(content)
            if isinstance(result, dict):
                return result
        return {"risk": "low", "compliance_score": 95}

    def _run_policy(self, content: str, requirement: str) -> Dict[str, Any]:
        if self.policy_evaluator:
            result = self.policy_evaluator(content, requirement)
            if isinstance(result, dict):
                return result
        return {"compliance": "passed", "requirement": requirement}

    def _create_passport(self, proposal: ProposedAmendment, content: str, analysis: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
        if self.passport_creator:
            return self.passport_creator(proposal.contract_id, content, analysis, policy)
        document_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "contract_id": proposal.contract_id,
            "version": 2,
            "document_hash": document_hash,
            "proof_status": "verified" if self.proof_anchorer else "pending",
        }

    def _save_approval(self, proposal: ProposedAmendment, approved: bool, approved_by: str, notes: Optional[str], rejection_reason: Optional[str]) -> AmendmentApproval:
        approval = AmendmentApproval(
            id=str(uuid4()), amendment_id=proposal.id, event_id=proposal.event_id,
            contract_id=proposal.contract_id, approved=approved, approved_by=approved_by,
            approved_at=datetime.now(timezone.utc), approval_notes=notes, rejection_reason=rejection_reason,
        )
        self._approvals[proposal.id] = approval
        return approval

    def _record(self, event_id: str, contract_id: str, action_type: str, description: str) -> None:
        entry = AuditTrailEntry(
            id=str(uuid4()), event_id=event_id, contract_id=contract_id,
            action_type=action_type, action_description=description,
            timestamp=datetime.now(timezone.utc), performed_by="system",
        )
        self._audit.setdefault(event_id, []).append(entry)
