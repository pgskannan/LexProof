"""Reusable workflow definition documents. Data, not contract-specific engine logic."""

from __future__ import annotations

from typing import Any

CONTRACT_REDLINE_APPROVAL = "contract_redline_approval"

# SLA hours are measured from the moment an instance enters the state; an
# instance still sitting in a state past its SLA is "overdue" and, once, is
# escalated (an in-app notification to escalate_to_roles). draft/published/
# rejected have no SLA -- draft is un-owned busywork, published/rejected are
# terminal -- only the two states that represent someone's pending action
# on someone else's behalf carry one.
CONTRACT_REDLINE_STATES: list[dict[str, Any]] = [
    {"id": "draft", "name": "Draft", "is_initial": True, "is_terminal": False},
    {
        "id": "in_review",
        "name": "In review",
        "is_initial": False,
        "is_terminal": False,
        "sla_hours": 48,
        "escalate_to_roles": ["admin"],
    },
    {
        "id": "approved",
        "name": "Approved",
        "is_initial": False,
        "is_terminal": False,
        "sla_hours": 24,
        "escalate_to_roles": ["admin"],
    },
    {"id": "published", "name": "Published", "is_initial": False, "is_terminal": True},
    {"id": "rejected", "name": "Rejected", "is_initial": False, "is_terminal": True},
]

CONTRACT_REDLINE_TRANSITIONS: list[dict[str, Any]] = [
    {
        "id": "submit_for_review",
        "from_state": "draft",
        "to_state": "in_review",
        "action_name": "Submit for review",
        "allowed_roles": ["contract_owner", "admin"],
        "requires_not_actor": [],
    },
    {
        "id": "approve",
        "from_state": "in_review",
        "to_state": "approved",
        "action_name": "Approve",
        "allowed_roles": ["reviewer", "admin"],
        "requires_not_actor": ["created_by"],
    },
    {
        "id": "reject",
        "from_state": "in_review",
        "to_state": "rejected",
        "action_name": "Reject",
        "allowed_roles": ["reviewer", "admin"],
        "requires_not_actor": [],
    },
    {
        "id": "publish",
        "from_state": "approved",
        "to_state": "published",
        "action_name": "Publish",
        "allowed_roles": ["approver", "admin"],
        "requires_not_actor": ["created_by"],
    },
]


def redline_definition_id(org_id: str) -> str:
    return f"{org_id}_{CONTRACT_REDLINE_APPROVAL}"


PROPOSAL_STATUS_BY_STATE = {
    "draft": "DRAFT",
    "in_review": "PROPOSED",
    "approved": "APPROVED",
    "rejected": "REJECTED",
    "published": "PUBLISHED",
}

STATE_BY_PROPOSAL_STATUS = {
    "DRAFT": "draft",
    "PROPOSED": "in_review",
    "APPROVED": "approved",
    "REJECTED": "rejected",
    "PUBLISHED": "published",
}
