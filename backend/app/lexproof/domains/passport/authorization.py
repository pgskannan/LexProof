"""Contract-based authorization shared by the Passport and Evidence domains.

Phase 3H.2 (P1-A): Contract Detail reaches Evidence/Anchor data through
Contract -> Passport -> Evidence -> Evidence Anchor. The Contract domain
(api/contracts.py::_is_visible_to_user, mirrored in
services/executive_summary.py::_is_visible_to_user) already resolves read
visibility as: an org-owned Contract is visible to any ACTIVE member of that
organization (membership alone -- no role check); a Contract with no org_id
(legacy/orphan data) keeps the original, strict owner-only visibility. The
Passport and Evidence domains instead filtered purely on
`created_by`/`owner_id` matching the caller, so an authorized non-owner
teammate (an org Admin, Reviewer, Approver, Auditor, or any other active
member) saw an empty Passport/Evidence list for a contract they were
otherwise fully entitled to view.

This module does not invent a new authorization policy. It resolves the
record's associated Contract and asks the existing organization service
exactly the same question api/contracts.py already asks for the Contract
itself, so Passport/Evidence visibility stays consistent with the
established Contract policy.
"""

from __future__ import annotations

from typing import Any

from ...repositories.firestore import FirestoreRepository
from ...services.organizations import get_organization_service


def is_visible_via_contract(
    *,
    owner_id: str | None,
    tenant_id: str,
    contract_id: str | None,
    contracts_repository: FirestoreRepository | None,
) -> bool:
    """True if `tenant_id` may see a Passport/Evidence record owned by
    `owner_id` and associated with `contract_id`.

    Resolution order (mirrors api/contracts.py::_is_visible_to_user):
      1. If `contract_id` resolves to a real Contract with an `org_id`,
         visibility is active organization membership in that org --
         regardless of who owns the Passport/Evidence record itself. This
         matches the Contract domain's own read-visibility rule exactly.
      2. Otherwise (no `contract_id`, no resolvable Contract, or a Contract
         with no `org_id` -- legacy/orphan data predating the contracts/
         collection) falls back to the original owner-only rule: visible if
         there is no owner_id at all, or the owner_id matches the caller.
    """
    org_id: str | None = None
    if contract_id and contracts_repository is not None:
        contract = contracts_repository.get(contract_id)
        if contract:
            org_id = contract.get("org_id")
    if org_id:
        return bool(get_organization_service().get_active_member(str(org_id), tenant_id))
    return not owner_id or owner_id == tenant_id
