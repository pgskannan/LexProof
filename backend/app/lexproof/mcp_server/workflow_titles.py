"""Human-readable workflow titles resolved from authorized REST resources."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

from .client import call_api
from .spoken_names import spoken_contract_name

_GENERIC_WORKFLOW_TITLE = "Contract approval"


def workflow_label(instance: dict[str, Any], definition: dict[str, Any]) -> str:
    metadata = instance.get("metadata") or {}
    entity_type = str(instance.get("entity_type") or "").casefold()
    current_state = str(instance.get("current_state") or "")
    state_name = next(
        (str(state.get("name") or "") for state in definition.get("states") or [] if state.get("id") == current_state),
        "",
    )
    for candidate in (
        definition.get("name"),
        metadata.get("workflow_name"),
        state_name,
        metadata.get("title"),
    ):
        label = str(candidate or "").strip()
        if label and label.casefold() not in {entity_type, "redline proposal", "workflow", "contract"}:
            return label
    return "Contract review"


def workflow_title_parts(
    instance: dict[str, Any],
    definition: dict[str, Any],
    contract_name: str | None,
) -> tuple[str, str | None]:
    metadata = instance.get("metadata") or {}
    selected_contract_name = str(metadata.get("contract_name") or contract_name or "").strip() or None
    if not selected_contract_name:
        return _GENERIC_WORKFLOW_TITLE, None
    return workflow_label(instance, definition), selected_contract_name


def format_workflow_title(instance: dict[str, Any], definition: dict[str, Any], contract_name: str | None) -> str:
    label, resolved_contract = workflow_title_parts(instance, definition, contract_name)
    return f"{label}: {resolved_contract}" if resolved_contract else _GENERIC_WORKFLOW_TITLE


def workflow_subject(instance: dict[str, Any], definition: dict[str, Any], contract_name: str | None) -> str:
    label, resolved_contract = workflow_title_parts(instance, definition, contract_name)
    if not resolved_contract:
        return "the contract approval"
    return f"the {label.casefold()} for the {spoken_contract_name(resolved_contract)}"


def workflow_structured_subject(instance: dict[str, Any], definition: dict[str, Any], contract_name: str | None) -> str:
    label, resolved_contract = workflow_title_parts(instance, definition, contract_name)
    if not resolved_contract:
        return "the contract approval"
    return f"the {label.casefold()} for the {resolved_contract}"


async def resolve_workflow_contract_names(
    instances: list[dict[str, Any]],
    org_id: str,
    semaphore: asyncio.Semaphore | None = None,
) -> dict[str, str]:
    """Resolve entity references, fetching each proposal/contract at most once."""
    limiter = semaphore or asyncio.Semaphore(8)
    names: dict[str, str] = {}
    proposal_by_instance: dict[str, str] = {}
    contract_by_instance: dict[str, str] = {}

    for instance in instances:
        instance_id = str(instance.get("instance_id") or instance.get("id") or "")
        metadata = instance.get("metadata") or {}
        if metadata.get("contract_name"):
            names[instance_id] = str(metadata["contract_name"])
            continue
        metadata_contract_id = str(metadata.get("contract_id") or "")
        entity_type = str(instance.get("entity_type") or "").casefold()
        entity_id = str(instance.get("entity_id") or "")
        if metadata_contract_id:
            contract_by_instance[instance_id] = metadata_contract_id
        elif entity_type in {"contract", "contracts"} and entity_id:
            contract_by_instance[instance_id] = entity_id
        elif entity_type in {"redline_proposal", "redline-proposal", "proposal"} and entity_id:
            proposal_by_instance[instance_id] = entity_id

    async def load_proposal(proposal_id: str) -> tuple[str, str | None]:
        try:
            async with limiter:
                proposal = await call_api(
                    "GET",
                    f"/api/redline-proposals/{quote(proposal_id, safe='')}",
                    org_id=org_id,
                )
            contract_id = str(proposal.get("contract_id") or "")
            return proposal_id, contract_id or None
        except Exception:
            return proposal_id, None

    unique_proposal_ids = list(dict.fromkeys(proposal_by_instance.values()))
    proposal_results = await asyncio.gather(*(
        load_proposal(proposal_id)
        for proposal_id in unique_proposal_ids
    ))
    proposal_contract_ids = {proposal_id: contract_id for proposal_id, contract_id in proposal_results if contract_id}
    for instance_id, proposal_id in proposal_by_instance.items():
        if proposal_id in proposal_contract_ids:
            contract_by_instance[instance_id] = proposal_contract_ids[proposal_id]

    unique_contract_ids = list(dict.fromkeys(contract_by_instance.values()))

    async def load_contract(contract_id: str) -> tuple[str, str | None]:
        try:
            async with limiter:
                contract = await call_api(
                    "GET",
                    f"/api/contracts/{quote(contract_id, safe='')}",
                    org_id=org_id,
                )
            name = str(contract.get("name") or contract.get("contract_name") or "").strip()
            return contract_id, name or None
        except Exception:
            return contract_id, None

    contract_results = await asyncio.gather(*(load_contract(contract_id) for contract_id in unique_contract_ids))
    contract_names = {contract_id: name for contract_id, name in contract_results if name}
    for instance_id, contract_id in contract_by_instance.items():
        if contract_id in contract_names:
            names[instance_id] = contract_names[contract_id]
    return names


async def resolve_workflow_contract_name(instance: dict[str, Any], org_id: str) -> str | None:
    instance_id = str(instance.get("instance_id") or instance.get("id") or "")
    names = await resolve_workflow_contract_names([instance], org_id)
    return names.get(instance_id)
