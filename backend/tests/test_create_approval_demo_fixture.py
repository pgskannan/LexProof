"""Offline unit tests for the Phase 3J-B golden-path fixture in
scripts/create_approval_demo_fixture.py.

Fully mocked -- FakeRepository (tests/fakes.py) stands in for Firestore, so
none of this contacts a real Firebase project. Mirrors the
FakeRepository-based pattern already used by tests/test_redline_proposals.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.redline_proposals import ProposalService
from app.lexproof.services.workflow_engine import WorkflowEngine
from tests.fakes import FakeRepository

import create_approval_demo_fixture as fixture  # noqa: E402


def reset_stores() -> None:
    FakeRepository.stores = {
        "contracts": {},
        "contract_versions": {},
        "risk_findings": {},
        "redline_proposals": {},
        "redline_reviews": {},
        "redline_publication_audits": {},
        "legal_passports": {},
        "evidence_records": {},
        "evidence_anchors": {},
        "organizations": {},
        f"organizations/{fixture.ORG_ID}/members": {},
        "users": {},
        "organization_invites": {},
        "workflow_definitions": {},
        "workflow_instances": {},
    }


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_workflow() -> WorkflowEngine:
    return WorkflowEngine(
        definitions=FakeRepository("workflow_definitions"),
        instances=FakeRepository("workflow_instances"),
        history_factory=lambda instance_id: FakeRepository(f"workflow_instances/{instance_id}/history"),
    )


def make_service(orgs: OrganizationService) -> ProposalService:
    return ProposalService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        reviews=FakeRepository("redline_reviews"),
        publication_audits=FakeRepository("redline_publication_audits"),
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        evidence_anchors=FakeRepository("evidence_anchors"),
        organizations=orgs,
        workflow=make_workflow(),
    )


class GoldenPathDraftFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_stores()

    def _run(self, orgs: OrganizationService, service: ProposalService) -> dict:
        return fixture.create_golden_path_draft_fixture(
            orgs,
            contracts=service.contracts,
            versions=service.versions,
            findings=service.findings,
            service=service,
        )

    def test_first_run_creates_draft_state_with_distinct_role_identities(self):
        orgs = make_orgs()
        service = make_service(orgs)

        summary = self._run(orgs, service)

        self.assertEqual(summary["proposal_status"], "DRAFT")
        self.assertEqual(summary["workflow_state"], "draft")
        self.assertEqual(summary["published_version_id"], None)
        self.assertIn("contract_owner", summary["available_roles"])
        self.assertEqual(
            {summary["contract_owner"], summary["reviewer"], summary["approver"]},
            {fixture.OWNER_ID, fixture.REVIEWER_ID, fixture.APPROVER_ID},
        )
        self.assertEqual(len({summary["contract_owner"], summary["reviewer"], summary["approver"]}), 3)

        contract = service.contracts.get(fixture.GOLDEN_PATH_CONTRACT_ID)
        self.assertEqual(contract["owner_id"], fixture.OWNER_ID)

        owner_member = orgs.get_active_member(fixture.ORG_ID, fixture.OWNER_ID)
        reviewer_member = orgs.get_active_member(fixture.ORG_ID, fixture.REVIEWER_ID)
        approver_member = orgs.get_active_member(fixture.ORG_ID, fixture.APPROVER_ID)
        self.assertIn("contract_owner", owner_member["roles"])
        self.assertIn("reviewer", reviewer_member["roles"])
        self.assertIn("approver", approver_member["roles"])

    def test_second_run_is_idempotent_no_duplicates(self):
        orgs = make_orgs()
        service = make_service(orgs)

        first = self._run(orgs, service)

        contracts_after_first = dict(FakeRepository.stores["contracts"])
        proposals_after_first = dict(FakeRepository.stores["redline_proposals"])
        instances_after_first = dict(FakeRepository.stores["workflow_instances"])
        members_after_first = dict(FakeRepository.stores[f"organizations/{fixture.ORG_ID}/members"])

        second = self._run(orgs, service)

        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(first["workflow_instance_id"], second["workflow_instance_id"])
        self.assertEqual(second["proposal_status"], "DRAFT")
        self.assertEqual(second["workflow_state"], "draft")

        # No new contracts, proposals, or workflow instances were created on
        # the second call -- same document counts and same document ids.
        self.assertEqual(len(FakeRepository.stores["contracts"]), len(contracts_after_first))
        self.assertEqual(len(FakeRepository.stores["redline_proposals"]), len(proposals_after_first))
        self.assertEqual(len(FakeRepository.stores["workflow_instances"]), len(instances_after_first))
        self.assertEqual(set(FakeRepository.stores["redline_proposals"]), set(proposals_after_first))
        self.assertEqual(set(FakeRepository.stores["workflow_instances"]), set(instances_after_first))

        # Membership roles/status were not duplicated or altered by the second
        # run (updated_at naturally refreshes on every ensure_member call --
        # that is expected upsert behavior, not a duplicate -- so only the
        # meaningful fields are compared here, not full-record equality).
        members_second = FakeRepository.stores[f"organizations/{fixture.ORG_ID}/members"]
        self.assertEqual(set(members_second), set(members_after_first))
        for user_id, member in members_after_first.items():
            self.assertEqual(members_second[user_id]["roles"], member["roles"])
            self.assertEqual(members_second[user_id]["status"], member["status"])

    def test_does_not_touch_pending_review_fixture_ids(self):
        orgs = make_orgs()
        service = make_service(orgs)

        self._run(orgs, service)

        self.assertIsNone(service.contracts.get(fixture.CONTRACT_ID))
        self.assertIsNone(service.findings.get(fixture.FINDING_ID))
        for proposal in FakeRepository.stores["redline_proposals"].values():
            self.assertNotEqual(proposal.get("contract_id"), fixture.CONTRACT_ID)

    def test_raises_when_proposal_has_moved_past_draft(self):
        orgs = make_orgs()
        service = make_service(orgs)
        self._run(orgs, service)

        # Simulate the golden-path proposal having been submitted for review
        # by a human/E2E test between two provisioning runs.
        proposals = FakeRepository.stores["redline_proposals"]
        (proposal_id, proposal), = (
            (pid, p) for pid, p in proposals.items() if p.get("contract_id") == fixture.GOLDEN_PATH_CONTRACT_ID
        )
        proposals[proposal_id]["status"] = "PROPOSED"
        instances = FakeRepository.stores["workflow_instances"]
        instances[proposal["workflow_instance_id"]]["current_state"] = "in_review"

        with self.assertRaises(RuntimeError):
            self._run(orgs, service)

    def test_reset_rebuilds_draft_after_approval(self):
        orgs = make_orgs()
        service = make_service(orgs)
        first = self._run(orgs, service)

        proposals = FakeRepository.stores["redline_proposals"]
        proposal_id = first["proposal_id"]
        instance_id = first["workflow_instance_id"]
        proposals[proposal_id]["status"] = "APPROVED"
        FakeRepository.stores["workflow_instances"][instance_id]["current_state"] = "approved"
        FakeRepository.stores["redline_reviews"]["review-1"] = {
            "review_id": "review-1",
            "proposal_id": proposal_id,
            "decision": "APPROVED",
        }
        FakeRepository.stores["redline_publication_audits"]["audit-1"] = {
            "proposal_id": proposal_id,
        }
        FakeRepository.stores["contract_versions"]["demo-golden-path-v2"] = {
            "id": "demo-golden-path-v2",
            "contract_id": fixture.GOLDEN_PATH_CONTRACT_ID,
            "version_number": 2,
        }
        FakeRepository.stores["contracts"][fixture.GOLDEN_PATH_CONTRACT_ID]["current_version_id"] = "demo-golden-path-v2"

        deleted = fixture.reset_golden_path_workflow_state(service)
        self.assertEqual(deleted["proposals"], [proposal_id])
        self.assertEqual(deleted["reviews"], ["review-1"])
        self.assertEqual(deleted["audits"], ["audit-1"])
        self.assertEqual(deleted["instances"], [instance_id])
        self.assertEqual(deleted["extra_versions"], ["demo-golden-path-v2"])
        self.assertIsNone(service.proposals.get(proposal_id))
        self.assertEqual(
            service.contracts.get(fixture.GOLDEN_PATH_CONTRACT_ID)["current_version_id"],
            fixture.GOLDEN_PATH_VERSION_ID,
        )

        second = self._run(orgs, service)
        self.assertEqual(second["proposal_status"], "DRAFT")
        self.assertEqual(second["workflow_state"], "draft")
        self.assertNotEqual(second["proposal_id"], proposal_id)
        self.assertEqual(list(FakeRepository.stores["redline_reviews"]), [])

    def test_reset_does_not_touch_pending_review_fixture_ids(self):
        orgs = make_orgs()
        service = make_service(orgs)
        self._run(orgs, service)

        FakeRepository.stores["contracts"][fixture.CONTRACT_ID] = {"id": fixture.CONTRACT_ID, "org_id": fixture.ORG_ID}
        FakeRepository.stores["redline_proposals"]["pending-proposal"] = {
            "proposal_id": "pending-proposal",
            "contract_id": fixture.CONTRACT_ID,
            "finding_id": fixture.FINDING_ID,
            "status": "PROPOSED",
        }
        FakeRepository.stores["redline_reviews"]["pending-review"] = {
            "review_id": "pending-review",
            "proposal_id": "pending-proposal",
        }

        fixture.reset_golden_path_workflow_state(service)

        self.assertIsNotNone(service.contracts.get(fixture.CONTRACT_ID))
        self.assertEqual(service.proposals.get("pending-proposal")["status"], "PROPOSED")
        self.assertEqual(service.reviews.get("pending-review")["proposal_id"], "pending-proposal")


    def test_pending_review_reset_rebuilds_after_approval(self):
        orgs = make_orgs()
        service = make_service(orgs)
        FakeRepository.stores["contracts"][fixture.CONTRACT_ID] = {
            "id": fixture.CONTRACT_ID,
            "org_id": fixture.ORG_ID,
            "current_version_id": "pending-v2",
        }
        FakeRepository.stores["contract_versions"][fixture.VERSION_ID] = {
            "id": fixture.VERSION_ID,
            "contract_id": fixture.CONTRACT_ID,
        }
        FakeRepository.stores["contract_versions"]["pending-v2"] = {
            "id": "pending-v2",
            "contract_id": fixture.CONTRACT_ID,
        }
        FakeRepository.stores["redline_proposals"]["pending-proposal"] = {
            "proposal_id": "pending-proposal",
            "id": "pending-proposal",
            "contract_id": fixture.CONTRACT_ID,
            "finding_id": fixture.FINDING_ID,
            "status": "APPROVED",
            "workflow_instance_id": "pending-instance",
        }
        FakeRepository.stores["workflow_instances"]["pending-instance"] = {
            "instance_id": "pending-instance",
            "current_state": "approved",
        }
        FakeRepository.stores["redline_reviews"]["pending-review"] = {
            "review_id": "pending-review",
            "proposal_id": "pending-proposal",
            "decision": "APPROVED",
        }
        FakeRepository.stores["redline_publication_audits"]["pending-audit"] = {
            "proposal_id": "pending-proposal",
        }
        FakeRepository.stores["redline_proposals"]["golden-proposal"] = {
            "proposal_id": "golden-proposal",
            "contract_id": fixture.GOLDEN_PATH_CONTRACT_ID,
            "finding_id": fixture.GOLDEN_PATH_FINDING_ID,
            "status": "DRAFT",
        }

        deleted = fixture.reset_pending_review_workflow_state(service)

        self.assertEqual(deleted["proposals"], ["pending-proposal"])
        self.assertEqual(deleted["reviews"], ["pending-review"])
        self.assertEqual(deleted["audits"], ["pending-audit"])
        self.assertEqual(deleted["instances"], ["pending-instance"])
        self.assertEqual(deleted["extra_versions"], ["pending-v2"])
        self.assertIsNone(service.proposals.get("pending-proposal"))
        self.assertEqual(
            service.contracts.get(fixture.CONTRACT_ID)["current_version_id"],
            fixture.VERSION_ID,
        )
        self.assertEqual(service.proposals.get("golden-proposal")["status"], "DRAFT")


class DuplicateApprovalDenialFixtureTests(unittest.TestCase):
    """Covers the new fixture added for the E2E workflow audit's Phase 4C
    (duplicate-approval E2E test), so this offline suite stays the fast
    regression signal for it -- same FakeRepository pattern as the
    golden-path tests above."""

    def setUp(self) -> None:
        reset_stores()

    def _run(self, orgs: OrganizationService, service: ProposalService) -> dict:
        return fixture.create_duplicate_approval_denial_fixture(
            orgs,
            contracts=service.contracts,
            versions=service.versions,
            findings=service.findings,
            service=service,
        )

    def test_first_run_reaches_real_approved_state_via_real_review_call(self):
        orgs = make_orgs()
        service = make_service(orgs)

        summary = self._run(orgs, service)

        self.assertEqual(summary["proposal_status"], "APPROVED")
        self.assertEqual(summary["review_count"], 1)
        self.assertEqual(summary["contract_owner"], fixture.OWNER_ID)
        self.assertEqual(summary["reviewer"], fixture.REVIEWER_ID)

        # A real APPROVED review record actually exists (not hand-crafted --
        # this fixture reaches APPROVED by calling ProposalService.review()).
        reviews = [
            review for review in service.reviews.stream()
            if review.get("proposal_id") == summary["proposal_id"]
        ]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["decision"], "APPROVED")
        self.assertEqual(reviews[0]["reviewer_id"], fixture.REVIEWER_ID)

    def test_second_run_is_idempotent_does_not_call_review_again(self):
        orgs = make_orgs()
        service = make_service(orgs)

        first = self._run(orgs, service)
        reviews_after_first = dict(FakeRepository.stores["redline_reviews"])

        second = self._run(orgs, service)

        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(second["proposal_status"], "APPROVED")
        self.assertEqual(second["review_count"], 1)
        # No second review record was written -- review() was not called
        # again (it would raise FinalDecisionError if it had been).
        self.assertEqual(dict(FakeRepository.stores["redline_reviews"]), reviews_after_first)

    def test_fixture_ids_are_distinct_from_golden_path_and_pending_review(self):
        self.assertNotEqual(fixture.DUPLICATE_APPROVAL_CONTRACT_ID, fixture.GOLDEN_PATH_CONTRACT_ID)
        self.assertNotEqual(fixture.DUPLICATE_APPROVAL_CONTRACT_ID, fixture.CONTRACT_ID)
        self.assertNotEqual(fixture.DUPLICATE_APPROVAL_FINDING_ID, fixture.GOLDEN_PATH_FINDING_ID)
        self.assertNotEqual(fixture.DUPLICATE_APPROVAL_FINDING_ID, fixture.FINDING_ID)

    def test_a_second_approval_attempt_is_rejected_exactly_like_the_real_app_would_reject_it(self):
        """Not part of the fixture itself -- proves, offline, the exact
        backend behavior the new duplicate-approval E2E test relies on: once
        this fixture has seeded APPROVED, calling review() again (what a
        second "Approve" click would trigger) is refused and the approved
        state / review count are unchanged."""
        from app.lexproof.services.redline_proposals import FinalDecisionError

        orgs = make_orgs()
        service = make_service(orgs)
        summary = self._run(orgs, service)

        with self.assertRaises(FinalDecisionError):
            service.review(summary["proposal_id"], "APPROVED", fixture.REVIEWER_ID)

        after = service.get(summary["proposal_id"], fixture.OWNER_ID)
        self.assertEqual(after["status"], "APPROVED")
        reviews = [
            review for review in service.reviews.stream()
            if review.get("proposal_id") == summary["proposal_id"]
        ]
        self.assertEqual(len(reviews), 1)


class DualRoleSodFixtureTests(unittest.TestCase):
    """Covers the new fixture added for the E2E security/workflow follow-up's
    Phase 3 (dual-role separation-of-duties E2E test). Proves offline, via
    the real ProposalService/WorkflowEngine code path (FakeRepository
    stands in for Firestore only), that a single real identity holding BOTH
    contract_owner and reviewer is still denied approval of its OWN
    submission specifically by requires_not_actor -- not by a role check,
    which this identity would otherwise pass."""

    def setUp(self) -> None:
        reset_stores()

    def _run(self, orgs: OrganizationService, service: ProposalService) -> dict:
        return fixture.create_dual_role_sod_fixture(
            orgs,
            contracts=service.contracts,
            versions=service.versions,
            findings=service.findings,
            service=service,
        )

    def test_first_run_creates_proposed_state_with_dual_role_identity(self):
        orgs = make_orgs()
        service = make_service(orgs)

        summary = self._run(orgs, service)

        self.assertEqual(summary["proposal_status"], "PROPOSED")
        self.assertEqual(summary["dual_role_user"], fixture.DUAL_ROLE_SOD_ID)
        self.assertIn("contract_owner", summary["dual_role_user_roles"])
        self.assertIn("reviewer", summary["dual_role_user_roles"])

        proposal = service.get(summary["proposal_id"], fixture.DUAL_ROLE_SOD_ID)
        self.assertEqual(proposal["created_by"], fixture.DUAL_ROLE_SOD_ID)
        instance = service.workflow.get_instance(proposal["workflow_instance_id"])
        self.assertEqual(instance["created_by"], fixture.DUAL_ROLE_SOD_ID)
        self.assertEqual(instance["current_state"], "in_review")

    def test_second_run_is_idempotent(self):
        orgs = make_orgs()
        service = make_service(orgs)

        first = self._run(orgs, service)
        second = self._run(orgs, service)

        self.assertEqual(first["proposal_id"], second["proposal_id"])
        proposals_for_contract = [
            p for p in service.proposals.stream()
            if p.get("contract_id") == fixture.DUAL_ROLE_SOD_CONTRACT_ID
        ]
        self.assertEqual(len(proposals_for_contract), 1)

    def test_fixture_ids_are_distinct_from_other_fixtures(self):
        self.assertNotEqual(fixture.DUAL_ROLE_SOD_CONTRACT_ID, fixture.GOLDEN_PATH_CONTRACT_ID)
        self.assertNotEqual(fixture.DUAL_ROLE_SOD_CONTRACT_ID, fixture.CONTRACT_ID)
        self.assertNotEqual(fixture.DUAL_ROLE_SOD_CONTRACT_ID, fixture.DUPLICATE_APPROVAL_CONTRACT_ID)
        self.assertNotEqual(fixture.DUAL_ROLE_SOD_ID, fixture.OWNER_ID)
        self.assertNotEqual(fixture.DUAL_ROLE_SOD_ID, fixture.REVIEWER_ID)

    def test_self_approval_is_rejected_by_separation_of_duties_not_by_a_role_check(self):
        """The core proof this fixture exists for: DUAL_ROLE_SOD_ID genuinely
        HOLDS the reviewer role (the role check -- allowed_roles=[reviewer,
        admin] -- passes), so the denial that follows can only be coming
        from requires_not_actor. Asserted two ways: the exception message
        names the "created_by" field_ref (not a "Role ... cannot perform"
        message), and state/review-count are unchanged afterward."""
        from app.lexproof.services.workflow_engine import WorkflowSeparationOfDutiesError

        orgs = make_orgs()
        service = make_service(orgs)
        summary = self._run(orgs, service)

        with self.assertRaises(PermissionError) as ctx:
            service.review(summary["proposal_id"], "APPROVED", fixture.DUAL_ROLE_SOD_ID)
        self.assertIn("created_by", str(ctx.exception))
        self.assertNotIn("Role", str(ctx.exception))

        # Confirm, directly against the workflow engine (bypassing the
        # ProposalService wrapper that turns it into PermissionError), that
        # the underlying exception really is the SoD-specific type -- not
        # WorkflowPermissionError, which is what a genuine role failure
        # would raise instead.
        proposal = service.get(summary["proposal_id"], fixture.DUAL_ROLE_SOD_ID)
        instance = service.workflow.get_instance(proposal["workflow_instance_id"])
        definition = service.workflow.get_definition(instance["definition_id"])
        with self.assertRaises(WorkflowSeparationOfDutiesError):
            service.workflow._validate_transition(
                instance, definition, "approve", fixture.DUAL_ROLE_SOD_ID, ["contract_owner", "reviewer"],
            )

        after = service.get(summary["proposal_id"], fixture.DUAL_ROLE_SOD_ID)
        self.assertEqual(after["status"], "PROPOSED")
        reviews = [r for r in service.reviews.stream() if r.get("proposal_id") == summary["proposal_id"]]
        self.assertEqual(len(reviews), 0)

    def test_a_different_reviewer_can_approve_the_same_proposal(self):
        """Contrast case: the SAME proposal, approved by a genuinely
        different reviewer (fixture.REVIEWER_ID, not the creator), succeeds
        -- proving the denial above is specifically about actor identity
        (SoD), not some other defect in the proposal or contract."""
        orgs = make_orgs()
        service = make_service(orgs)
        summary = self._run(orgs, service)

        review = service.review(summary["proposal_id"], "APPROVED", fixture.REVIEWER_ID)
        self.assertEqual(review["decision"], "APPROVED")
        after = service.get(summary["proposal_id"], fixture.DUAL_ROLE_SOD_ID)
        self.assertEqual(after["status"], "APPROVED")


class CrossTenantIsolationFixtureTests(unittest.TestCase):
    """Covers the new fixture added for the E2E security/workflow follow-up's
    Phase 2 (cross-tenant isolation E2E test). Proves offline, via the real
    OrganizationService API (FakeRepository stands in for Firestore only),
    that Tenant B is a genuinely separate org -- not a relabeled contract in
    the same org -- and that the real contract_owner_or_org_admin authorization
    helper (api/... / services/organizations.py) treats cross-tenant access
    exactly as it should."""

    def setUp(self) -> None:
        reset_stores()

    def _run(self, orgs: OrganizationService) -> dict:
        # Explicit FakeRepository-backed stores -- create_cross_tenant_isolation_fixture's
        # own defaults construct a REAL FirestoreRepository when a kwarg is
        # omitted (same reason every other fixture test in this file passes
        # them explicitly). Omitting these would make this offline test
        # suite try to reach real Firestore.
        return fixture.create_cross_tenant_isolation_fixture(
            orgs,
            contracts=FakeRepository("contracts"),
            versions=FakeRepository("contract_versions"),
            findings=FakeRepository("risk_findings"),
        )

    def test_creates_two_genuinely_separate_orgs_with_correct_membership(self):
        orgs = make_orgs()
        summary = self._run(orgs)

        self.assertEqual(summary["tenant_a_org_id"], fixture.ORG_ID)
        self.assertEqual(summary["tenant_b_org_id"], fixture.TENANT_B_ORG_ID)
        self.assertNotEqual(summary["tenant_a_org_id"], summary["tenant_b_org_id"])

        self.assertIsNotNone(orgs.get_active_member(fixture.ORG_ID, fixture.OWNER_ID))
        self.assertIsNotNone(orgs.get_active_member(fixture.ORG_ID, fixture.REVIEWER_ID))
        self.assertIsNotNone(orgs.get_active_member(fixture.TENANT_B_ORG_ID, fixture.TENANT_B_OWNER_ID))
        self.assertIsNotNone(orgs.get_active_member(fixture.TENANT_B_ORG_ID, fixture.TENANT_B_REVIEWER_ID))

        # The actual isolation: neither tenant's identities are members of
        # the other tenant's org at all.
        self.assertIsNone(orgs.get_active_member(fixture.TENANT_B_ORG_ID, fixture.OWNER_ID))
        self.assertIsNone(orgs.get_active_member(fixture.TENANT_B_ORG_ID, fixture.REVIEWER_ID))
        self.assertIsNone(orgs.get_active_member(fixture.ORG_ID, fixture.TENANT_B_OWNER_ID))
        self.assertIsNone(orgs.get_active_member(fixture.ORG_ID, fixture.TENANT_B_REVIEWER_ID))

    def test_second_run_is_idempotent(self):
        orgs = make_orgs()
        first = self._run(orgs)
        second = self._run(orgs)
        self.assertEqual(first, second)
        contracts_for_tenant_b = [
            c for c in FakeRepository.stores["contracts"].values()
            if c.get("org_id") == fixture.TENANT_B_ORG_ID
        ]
        self.assertEqual(len(contracts_for_tenant_b), 1)

    def test_fixture_ids_are_distinct_from_other_fixtures(self):
        self.assertNotEqual(fixture.CROSS_TENANT_A_CONTRACT_ID, fixture.GOLDEN_PATH_CONTRACT_ID)
        self.assertNotEqual(fixture.CROSS_TENANT_A_CONTRACT_ID, fixture.CONTRACT_ID)
        self.assertNotEqual(fixture.CROSS_TENANT_A_CONTRACT_ID, fixture.CROSS_TENANT_B_CONTRACT_ID)
        self.assertNotEqual(fixture.TENANT_B_ORG_ID, fixture.ORG_ID)

    def test_owner_a_is_not_authorized_on_tenant_b_contract(self):
        # contract_owner_or_org_admin() looks up membership via its own
        # module-level get_organization_service() call (a fresh
        # OrganizationService bound to the REAL FirestoreRepository), not
        # whatever OrganizationService instance a caller happens to hold --
        # so it must be patched to return this test's FakeRepository-backed
        # `orgs`, exactly like tests/test_contract_action_authorization.py
        # already does for the same function.
        from unittest.mock import patch

        from app.lexproof.services import organizations as organizations_module
        from app.lexproof.services.organizations import contract_owner_or_org_admin

        orgs = make_orgs()
        self._run(orgs)
        tenant_b_contract = FakeRepository.stores["contracts"][fixture.CROSS_TENANT_B_CONTRACT_ID]

        with patch.object(organizations_module, "get_organization_service", lambda: orgs):
            self.assertFalse(contract_owner_or_org_admin(tenant_b_contract, fixture.OWNER_ID))
            self.assertFalse(contract_owner_or_org_admin(tenant_b_contract, fixture.REVIEWER_ID))

    def test_tenant_b_identities_are_authorized_on_their_own_contract(self):
        from unittest.mock import patch

        from app.lexproof.services import organizations as organizations_module
        from app.lexproof.services.organizations import contract_owner_or_org_admin

        orgs = make_orgs()
        self._run(orgs)
        tenant_b_contract = FakeRepository.stores["contracts"][fixture.CROSS_TENANT_B_CONTRACT_ID]
        tenant_a_contract = FakeRepository.stores["contracts"][fixture.CROSS_TENANT_A_CONTRACT_ID]

        with patch.object(organizations_module, "get_organization_service", lambda: orgs):
            self.assertTrue(contract_owner_or_org_admin(tenant_b_contract, fixture.TENANT_B_OWNER_ID))
            # Owner A is still authorized on Tenant A's own dedicated contract
            # -- the denial above is genuinely tenant-scoped, not a global
            # lockout.
            self.assertTrue(contract_owner_or_org_admin(tenant_a_contract, fixture.OWNER_ID))
            # Tenant B's owner is NOT authorized on Tenant A's contract
            # either (denial holds in both directions).
            self.assertFalse(contract_owner_or_org_admin(tenant_a_contract, fixture.TENANT_B_OWNER_ID))


if __name__ == "__main__":
    unittest.main()
