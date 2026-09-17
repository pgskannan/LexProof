"""Firestore-backed reviewable redline proposals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import logging

from ..repositories.firestore import FirestoreRepository
from .contract_versions import create_contract_version
from .organizations import OrganizationService, get_organization_service
from .roles import OrgRole
from .version_analysis import VersionAnalysisService
from .workflow_catalog import (
    CONTRACT_REDLINE_APPROVAL,
    CONTRACT_REDLINE_STATES,
    CONTRACT_REDLINE_TRANSITIONS,
    PROPOSAL_STATUS_BY_STATE,
    redline_definition_id,
)
from .workflow_engine import (
    WorkflowEngine,
    WorkflowError,
    WorkflowPermissionError,
    WorkflowSeparationOfDutiesError,
    get_workflow_engine,
    is_overdue as is_workflow_overdue,
)
from .published_version_status import project_published_version_status, project_published_version_status_batch

logger = logging.getLogger(__name__)


class RedlineProposalError(ValueError):
    """Base error for proposal validation failures."""


class ProposalNotFoundError(RedlineProposalError):
    """Raised when a proposal does not exist."""


class FinalDecisionError(RedlineProposalError):
    """Raised when a finalized proposal is reviewed again."""


class PublicationError(RedlineProposalError):
    """Raised when an approved proposal cannot be published safely."""


class ProposalService:
    def __init__(
        self,
        *,
        contracts: FirestoreRepository | None = None,
        versions: FirestoreRepository | None = None,
        findings: FirestoreRepository | None = None,
        proposals: FirestoreRepository | None = None,
        reviews: FirestoreRepository | None = None,
        publication_audits: FirestoreRepository | None = None,
        passports: FirestoreRepository | None = None,
        evidence_records: FirestoreRepository | None = None,
        evidence_anchors: FirestoreRepository | None = None,
        analysis_service: VersionAnalysisService | None = None,
        organizations: OrganizationService | None = None,
        workflow: WorkflowEngine | None = None,
    ) -> None:
        self.contracts = contracts or FirestoreRepository("contracts")
        self.versions = versions or FirestoreRepository("contract_versions")
        self.findings = findings or FirestoreRepository("risk_findings")
        self.proposals = proposals or FirestoreRepository("redline_proposals")
        self.reviews = reviews or FirestoreRepository("redline_reviews")
        self.publication_audits = publication_audits or FirestoreRepository("redline_publication_audits")
        self.passports = passports or FirestoreRepository("legal_passports")
        self.evidence_records = evidence_records or FirestoreRepository("evidence_records")
        self.evidence_anchors = evidence_anchors or FirestoreRepository("evidence_anchors")
        self.analysis_service = analysis_service
        self.organizations = organizations or get_organization_service()
        self.workflow = workflow or get_workflow_engine()

    def create(
        self,
        contract_id: str,
        source_version_id: str,
        finding_id: str,
        proposed_text: str,
        created_by: str,
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise RedlineProposalError(f"Contract not found: {contract_id}")
        org_id = self._org_id(contract)
        roles = self._require_member(org_id, created_by)
        if contract.get("owner_id") != created_by and OrgRole.ADMIN.value not in roles:
            raise PermissionError("You are not authorized to create a proposal")

        source_version = self.versions.get(source_version_id)
        if not source_version or source_version.get("contract_id") != contract_id:
            raise RedlineProposalError(f"Source version not found: {source_version_id}")

        finding = self.findings.get(finding_id)
        if not finding:
            raise RedlineProposalError(f"Finding not found: {finding_id}")
        if finding.get("contract_id") != contract_id:
            raise RedlineProposalError("Finding does not belong to the contract")
        if finding.get("version_id") and finding.get("version_id") != source_version_id:
            raise RedlineProposalError("Finding does not belong to the source version")
        finding_evidence_id = finding.get("evidence_id")
        if evidence_id and evidence_id != finding_evidence_id:
            raise RedlineProposalError("Evidence does not belong to the finding")

        original_text = finding.get("evidence_quote")
        if not original_text:
            evidence = finding.get("evidence")
            original_text = evidence if isinstance(evidence, str) else json.dumps(evidence) if evidence is not None else ""
        now = datetime.now(timezone.utc).isoformat()
        status = "PROPOSED" if proposed_text.strip() else "DRAFT"
        proposal = {
            "proposal_id": str(uuid4()),
            "org_id": org_id,
            "contract_id": contract_id,
            "source_version_id": source_version_id,
            "finding_id": finding_id,
            "evidence_id": finding_evidence_id,
            "title": finding.get("title"),
            "severity": finding.get("severity"),
            "original_text": original_text,
            "evidence": finding.get("evidence"),
            "proposed_text": proposed_text,
            "recommendation": finding.get("recommendation"),
            "reason": finding.get("description"),
            "status": status,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        self.proposals.set(proposal["proposal_id"], proposal)
        instance = self._ensure_instance(proposal, created_by, roles)
        proposal["workflow_instance_id"] = instance["instance_id"]
        if status == "PROPOSED" and instance.get("current_state") == "draft":
            instance = self.workflow.execute_transition(
                instance["instance_id"], "submit_for_review", created_by, roles
            )
        proposal["status"] = PROPOSAL_STATUS_BY_STATE.get(instance["current_state"], status)
        self.proposals.set(
            proposal["proposal_id"],
            {"workflow_instance_id": instance["instance_id"], "status": proposal["status"]},
            merge=True,
        )
        return self._with_review(proposal)

    def list(self, contract_id: str, user_id: str, version_id: str | None = None, finding_id: str | None = None) -> list[dict[str, Any]]:
        self._require_contract_member(contract_id, user_id)
        proposals = [
            proposal for proposal in self.proposals.stream()
            if proposal.get("contract_id") == contract_id
            and (version_id is None or proposal.get("source_version_id") == version_id)
            and (finding_id is None or proposal.get("finding_id") == finding_id)
        ]
        reviews_by_proposal = {
            item.get("proposal_id"): item
            for item in self.reviews.stream()
            if item.get("proposal_id")
        }
        published_version_ids = {
            item.get("published_version_id")
            for item in proposals
            if item.get("published_version_id")
        }
        passport_snapshot = list(self.passports.stream()) if published_version_ids else []
        evidence_snapshot = list(self.evidence_records.stream()) if published_version_ids else []
        anchor_snapshot = list(self.evidence_anchors.stream()) if published_version_ids else []
        finding_snapshot = list(self.findings.stream()) if published_version_ids else []
        status_by_version = project_published_version_status_batch(
            [item for item in self.versions.stream() if item.get("contract_id") == contract_id],
            proposals,
            passport_snapshot,
            evidence_snapshot,
            anchor_snapshot,
            finding_snapshot,
        )
        return [
            self._with_review(
                proposal,
                review=reviews_by_proposal.get(proposal.get("proposal_id")),
                status=status_by_version.get(proposal.get("published_version_id")),
            )
            for proposal in proposals
        ]

    def get(self, proposal_id: str, user_id: str) -> dict[str, Any]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
        self._require_contract_member(proposal.get("contract_id", ""), user_id)
        return self._with_review(proposal)

    def review(self, proposal_id: str, decision: str, reviewer_id: str, comment: str | None = None) -> dict[str, Any]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
        org_id = proposal.get("org_id") or self._org_id_for_contract(proposal.get("contract_id", ""))
        roles = self._require_member(org_id, reviewer_id)
        normalized_decision = decision.upper()
        if normalized_decision not in {"APPROVED", "REJECTED"}:
            raise RedlineProposalError("Decision must be APPROVED or REJECTED")
        if proposal.get("status") in {"APPROVED", "REJECTED", "PUBLISHED"} or any(
            review.get("proposal_id") == proposal_id for review in self.reviews.stream()
        ):
            raise FinalDecisionError(f"Proposal already has a final decision: {proposal_id}")
        instance = self._ensure_instance(proposal, proposal.get("created_by") or reviewer_id, roles)
        if instance.get("current_state") == "draft":
            owner_id = proposal.get("created_by") or reviewer_id
            owner_roles = self._require_member(org_id, owner_id)
            instance = self.workflow.execute_transition(
                instance["instance_id"], "submit_for_review", owner_id, owner_roles
            )
        transition_id = "approve" if normalized_decision == "APPROVED" else "reject"
        try:
            instance = self.workflow.execute_transition(
                instance["instance_id"], transition_id, reviewer_id, roles, comment
            )
        except (WorkflowPermissionError, WorkflowSeparationOfDutiesError) as error:
            raise PermissionError(str(error)) from error
        except WorkflowError as error:
            raise RedlineProposalError(str(error)) from error
        now = datetime.now(timezone.utc).isoformat()
        review = {
            "review_id": str(uuid4()),
            "proposal_id": proposal_id,
            "contract_id": proposal["contract_id"],
            "source_version_id": proposal["source_version_id"],
            "finding_id": proposal["finding_id"],
            "decision": normalized_decision,
            "reviewer_id": reviewer_id,
            "comment": comment,
            "created_at": now,
            "updated_at": now,
        }
        self.reviews.set(review["review_id"], review)
        self.proposals.set(
            proposal_id,
            {
                "status": PROPOSAL_STATUS_BY_STATE.get(instance["current_state"], normalized_decision),
                "workflow_instance_id": instance["instance_id"],
                "updated_at": now,
            },
            merge=True,
        )
        return review

    def update(self, proposal_id: str, proposed_text: str, user_id: str) -> dict[str, Any]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
        if proposal.get("status") in {"APPROVED", "REJECTED", "PUBLISHED"}:
            raise FinalDecisionError(f"Finalized proposal cannot be edited: {proposal_id}")
        contract = self.contracts.get(proposal.get("contract_id", ""))
        if not contract:
            raise RedlineProposalError(f"Contract not found: {proposal.get('contract_id')}")
        org_id = proposal.get("org_id") or self._org_id(contract)
        roles = self._require_member(org_id, user_id)
        if contract.get("owner_id") != user_id and OrgRole.ADMIN.value not in roles:
            raise PermissionError("You are not authorized to access proposals")
        updated = {
            "proposed_text": proposed_text,
            "status": "PROPOSED" if proposed_text.strip() else "DRAFT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.proposals.set(proposal_id, updated, merge=True)
        merged = {**proposal, **updated}
        if updated["status"] == "PROPOSED":
            instance = self._ensure_instance(merged, user_id, roles)
            if instance.get("current_state") == "draft":
                instance = self.workflow.execute_transition(
                    instance["instance_id"], "submit_for_review", user_id, roles
                )
                merged["status"] = PROPOSAL_STATUS_BY_STATE.get(instance["current_state"], merged["status"])
                merged["workflow_instance_id"] = instance["instance_id"]
                self.proposals.set(
                    proposal_id,
                    {"status": merged["status"], "workflow_instance_id": instance["instance_id"]},
                    merge=True,
                )
        return self._with_review(merged)

    def publish(self, proposal_id: str, publisher_id: str) -> dict[str, Any]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
        org_id = proposal.get("org_id") or self._org_id_for_contract(proposal.get("contract_id", ""))
        roles = self._require_member(org_id, publisher_id)
        if proposal.get("published_version_id"):
            return self._publication_response(proposal)
        if proposal.get("status") != "APPROVED":
            raise PublicationError("Only an APPROVED proposal can be published")

        instance = self._ensure_instance(proposal, proposal.get("created_by") or publisher_id, roles)
        try:
            self.workflow.assert_transition_allowed(instance["instance_id"], "publish", publisher_id, roles)
        except (WorkflowPermissionError, WorkflowSeparationOfDutiesError) as error:
            raise PermissionError(str(error)) from error
        except WorkflowError as error:
            raise PublicationError(str(error)) from error

        approved_review = next(
            (review for review in self.reviews.stream()
             if review.get("proposal_id") == proposal_id and review.get("decision") == "APPROVED"),
            None,
        )
        if not approved_review:
            raise PublicationError("An APPROVED persisted review is required")

        source_version_id = proposal.get("source_version_id")
        source = self.versions.get(source_version_id) if source_version_id else None
        if not source or source.get("contract_id") != proposal.get("contract_id"):
            raise PublicationError("Source contract version is missing or unrelated")
        original_text = proposal.get("original_text")
        proposed_text = proposal.get("proposed_text")
        document_text = source.get("document_text")
        if not isinstance(original_text, str) or not original_text.strip():
            raise PublicationError("Proposal does not contain exact original text")
        if not isinstance(proposed_text, str) or not proposed_text.strip():
            raise PublicationError("Proposal does not contain proposed text")
        if not isinstance(document_text, str):
            raise PublicationError("Source version does not contain editable document text")
        if document_text.count(original_text) != 1:
            raise PublicationError("Original text must match exactly once in the source version")

        transformed_text = document_text.replace(original_text, proposed_text, 1)
        new_version = create_contract_version(
            proposal["contract_id"],
            source_version_id,
            {"document_text": transformed_text},
            publisher_id,
            contracts=self.contracts,
            versions=self.versions,
        )
        published_at = datetime.now(timezone.utc).isoformat()
        self.proposals.set(proposal_id, {
            "status": "PUBLISHED",
            "published_version_id": new_version["id"],
            "published_by": publisher_id,
            "published_at": published_at,
            "updated_at": published_at,
            "workflow_instance_id": instance["instance_id"],
        }, merge=True)
        self.publication_audits.set(str(uuid4()), {
            "proposal_id": proposal_id,
            "contract_id": proposal["contract_id"],
            "source_version_id": source_version_id,
            "published_version_id": new_version["id"],
            "approved_review_id": approved_review["review_id"],
            "published_by": publisher_id,
            "published_at": published_at,
        })
        try:
            self.workflow.execute_transition(instance["instance_id"], "publish", publisher_id, roles)
        except Exception as exc:
            logger.warning(
                "workflow publish transition failed for proposal_id=%s instance_id=%s (publish itself already committed): %s",
                proposal_id, instance["instance_id"], exc,
            )
        # Everything above this line is the durable "publish" commit: a new
        # contract version now exists, the proposal is marked PUBLISHED, and
        # the publication audit record is written. From here on is slow,
        # best-effort post-publish work (Gemini analysis + Ethereum evidence
        # anchoring) that must NEVER make an already-successful publish look
        # like a failure to the user who clicked the button.
        #
        # This used to run inline via asyncio.run(self.analysis_service.
        # analyze_version(...)) before returning, which blocked this method
        # (and the HTTP request calling it) on the slow analysis+anchoring
        # call. If that request timed out or the connection dropped while
        # this was still running, the frontend's catch block surfaced
        # "Unable to publish proposal" even though the publish had already
        # fully committed (hardening item #1: publish success/error
        # semantic separation). Instead, mark the proposal's analysis as
        # PENDING and let the caller schedule run_post_publish_analysis()
        # below as a FastAPI background task -- the same commit-fast/
        # verify-later pattern already used for blockchain proof anchoring
        # in api/blockchain.py's anchor_proof_to_blockchain().
        analysis_status = "pending" if self.analysis_service else "not_attempted"
        self.proposals.set(proposal_id, {"analysis_status": analysis_status}, merge=True)
        return {
            "proposal_id": proposal_id,
            "contract_id": proposal.get("contract_id"),
            "status": "PUBLISHED",
            "source_version_id": source_version_id,
            "published_version_id": new_version["id"],
            "published_by": publisher_id,
            "published_at": published_at,
            "analysis_status": analysis_status,
        }

    async def run_post_publish_analysis(
        self,
        proposal_id: str,
        contract_id: str,
        version_id: str,
        publisher_id: str,
    ) -> None:
        """Best-effort post-publish analysis + evidence anchoring.

        Intended to be scheduled as a FastAPI BackgroundTasks callback *after*
        the publish() HTTP response has already been sent, so it can take as
        long as it needs without the publishing user's request ever waiting
        on it or timing out because of it. Never raises: a failure here only
        updates analysis_status to "failed" so the UI can show an honest,
        non-alarming "processing"/"failed" state and offer a retry -- the
        contract reviews page already has a "Retry evidence anchoring" action
        that re-calls the analyze endpoint directly for this exact version.
        A failure here must never undo or contradict the publish, which has
        already durably succeeded by the time this runs.
        """
        if not self.analysis_service:
            return
        try:
            await self.analysis_service.analyze_version(
                contract_id,
                version_id,
                publisher_id,
                anchor_evidence=True,
            )
            analysis_status = "complete"
        except Exception as exc:
            # analyze_version() has its own idempotency guard and raises an
            # HTTPException(409) if analysis for this exact version is
            # already in progress or already complete. That's not a real
            # failure (e.g. a retried publish() call scheduling this a
            # second time for the same version) -- leave analysis_status as
            # whatever the in-flight/completed run already set it to, rather
            # than incorrectly downgrading it to "failed".
            if getattr(exc, "status_code", None) == 409:
                logger.info(
                    "Post-publish analysis for proposal_id=%s, published_version_id=%s "
                    "already in progress or complete (409) -- leaving analysis_status as-is: %s",
                    proposal_id, version_id, exc,
                )
                return
            logger.warning(
                "Post-publish analysis/anchoring failed for proposal_id=%s, "
                "published_version_id=%s (publish itself already committed): %s",
                proposal_id, version_id, exc,
            )
            analysis_status = "failed"
        self.proposals.set(proposal_id, {"analysis_status": analysis_status}, merge=True)

    def _org_id(self, contract: dict[str, Any]) -> str:
        org_id = contract.get("org_id")
        if not org_id:
            raise PermissionError("Contract is not assigned to an organization")
        return str(org_id)

    def _org_id_for_contract(self, contract_id: str) -> str:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise RedlineProposalError(f"Contract not found: {contract_id}")
        return self._org_id(contract)

    def _require_member(self, org_id: str, user_id: str) -> list[str]:
        member = self.organizations.get_active_member(org_id, user_id)
        if not member:
            logger.warning("permission denied org_id=%s actor=%s action=org_membership", org_id, user_id)
            raise PermissionError("You are not authorized to access proposals")
        return list(member.get("roles") or [])

    def _require_contract_member(self, contract_id: str, user_id: str) -> list[str]:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise RedlineProposalError(f"Contract not found: {contract_id}")
        return self._require_member(self._org_id(contract), user_id)

    def _ensure_instance(self, proposal: dict[str, Any], created_by: str, roles: list[str]) -> dict[str, Any]:
        instance_id = proposal.get("workflow_instance_id")
        if instance_id:
            return self.workflow.get_instance(instance_id)
        org_id = proposal.get("org_id") or self._org_id_for_contract(proposal["contract_id"])
        existing = self.workflow.find_instance(org_id, "redline_proposal", proposal["proposal_id"])
        if existing:
            return existing
        try:
            definition = self.workflow.get_active_definition(org_id, CONTRACT_REDLINE_APPROVAL)
            # Self-heal: a definition provisioned before SLA/escalation
            # metadata existed on the catalog still has a stable
            # definition_id, so refresh its states/transitions in place
            # rather than leaving old orgs permanently without SLAs.
            if (
                definition.get("states") != CONTRACT_REDLINE_STATES
                or definition.get("transitions") != CONTRACT_REDLINE_TRANSITIONS
            ):
                definition = self.workflow.update_definition_content(
                    definition["definition_id"], CONTRACT_REDLINE_STATES, CONTRACT_REDLINE_TRANSITIONS
                )
        except WorkflowError:
            definition = self.workflow.create_definition(
                org_id,
                CONTRACT_REDLINE_APPROVAL,
                CONTRACT_REDLINE_STATES,
                CONTRACT_REDLINE_TRANSITIONS,
                created_by,
                definition_id=redline_definition_id(org_id),
            )
        return self.workflow.start_instance(
            org_id,
            definition["definition_id"],
            "redline_proposal",
            proposal["proposal_id"],
            proposal.get("created_by") or created_by,
            metadata={"contract_id": proposal.get("contract_id")},
        )

    def _with_review(
        self,
        proposal: dict[str, Any],
        *,
        review: dict[str, Any] | None = None,
        status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if review is None:
            review = next((item for item in self.reviews.stream() if item.get("proposal_id") == proposal.get("proposal_id")), None)
        sla_due_at = None
        overdue = False
        instance_id = proposal.get("workflow_instance_id")
        if instance_id:
            try:
                instance = self.workflow.get_instance(instance_id)
                sla_due_at = instance.get("sla_due_at")
                overdue = is_workflow_overdue(instance)
            except WorkflowError:
                pass
        if status is None:
            version = self.versions.get(proposal.get("published_version_id")) if proposal.get("published_version_id") else None
            status = project_published_version_status(
                version,
                proposal,
                passports=self.passports,
                evidence_records=self.evidence_records,
                evidence_anchors=self.evidence_anchors,
                findings=self.findings,
            )
        return {
            **proposal,
            "review": review,
            "sla_due_at": sla_due_at,
            "is_overdue": overdue,
            **status,
        }

    def _publication_response(self, proposal: dict[str, Any]) -> dict[str, Any]:
        return {
            "proposal_id": proposal["proposal_id"],
            "contract_id": proposal.get("contract_id"),
            "status": proposal.get("status", "PUBLISHED"),
            "source_version_id": proposal["source_version_id"],
            "published_version_id": proposal["published_version_id"],
            "published_by": proposal.get("published_by"),
            "published_at": proposal.get("published_at"),
            "analysis_status": proposal.get("analysis_status"),
        }
