"""Attach Ask Lexi demo approvals and payments to real analyzed contracts.

From ``backend/`` (dry-run is the default):
  python scripts/seed_alexa_demo.py --owner-email owner@example.com
  python scripts/seed_alexa_demo.py --owner-email owner@example.com --judge-uid JUDGE_UID --apply
  python scripts/seed_alexa_demo.py --remove-synthetic --dry-run
  python scripts/seed_alexa_demo.py --remove-synthetic --apply

This script never creates fake contract intelligence or submits blockchain transactions.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from app.lexproof.services.auth import read_only_uids
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.paypal.obligations import assess_extracted_obligation

ORG_ID = "lexproof-alexa-demo"
ORG_NAME = "LexProof Alexa Demo"
SEED_NAMESPACE = "https://lexproofsolutions.com/demo/alexa/"
SYNTHETIC_CONTRACTS = tuple(f"alexa-{key}" for key in ("acme-msa", "globex-saas", "initech-sow", "umbrella-nda", "stark-po-terms"))
SYNTHETIC_VERSIONS = tuple(f"{contract_id}-v1" for contract_id in SYNTHETIC_CONTRACTS)
SYNTHETIC_PASSPORTS = tuple(str(uuid5(NAMESPACE_URL, f"{SEED_NAMESPACE}passport/{key}")) for key in ("acme-msa", "globex-saas", "initech-sow", "umbrella-nda", "stark-po-terms"))
SYNTHETIC_FINDINGS = tuple(f"{contract_id}-finding-1" for contract_id in SYNTHETIC_CONTRACTS)
SYNTHETIC_WORKFLOW_KEYS = ("legal-review", "finance-review")
SYNTHETIC_WORKFLOW_DEFINITIONS = tuple(f"alexa-{key}-definition" for key in SYNTHETIC_WORKFLOW_KEYS)
SYNTHETIC_WORKFLOW_INSTANCES = tuple(str(uuid5(NAMESPACE_URL, f"{SEED_NAMESPACE}workflow-instance/{key}")) for key in SYNTHETIC_WORKFLOW_KEYS)
SYNTHETIC_PAYMENT_IDS = tuple(f"alexa-payment-{key}" for key in ("initech-milestone", "acme-monthly", "globex-renewal"))
_AMOUNT = re.compile(r"(?:USD|US\$|\$)\s*\d[\d,]*(?:\.\d{1,2})?", re.IGNORECASE)


def _amount_value(raw: str) -> str:
    normalized = raw.upper().replace("USD", "").replace("US$", "").replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Could not parse an amount from contract text") from exc
    return format(value, "f")


def _quote_for_match(text: str, start: int, end: int) -> str:
    left = max(text.rfind("\n", 0, start), text.rfind(".", 0, start), text.rfind(";", 0, start)) + 1
    boundaries = [index for marker in ("\n", ".", ";") if (index := text.find(marker, end)) >= 0]
    right = min(boundaries) + 1 if boundaries else len(text)
    return text[left:right].strip()


def extract_verified_payment_candidates(contracts: list[dict[str, Any]], versions_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick numeric amounts from analyzed version text and retain only exact assessed quotes."""
    candidates: list[dict[str, Any]] = []
    for contract in contracts:
        version = versions_by_id.get(str(contract.get("current_version_id") or ""), {})
        text = version.get("document_text")
        if not isinstance(text, str) or not text.strip():
            continue
        for match in _AMOUNT.finditer(text):
            quote = _quote_for_match(text, match.start(), match.end())
            amount = _amount_value(match.group(0))
            assessed = assess_extracted_obligation(text, {
                "label": quote[:80],
                "amount": amount,
                "currency": "USD",
                "clause_quote": quote,
            })
            if assessed.get("needs_review_reason"):
                continue
            candidates.append({"contract": contract, "version": version, "quote": quote, "amount": amount})
    return candidates


def _analyzed_contracts(contracts_repo: Any, versions_repo: Any, org_id: str = ORG_ID) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    contracts = [
        row for row in contracts_repo.query(equal={"org_id": org_id})
        if row.get("current_version_id")
    ]
    version_ids = [str(row["current_version_id"]) for row in contracts]
    versions = versions_repo.get_many(version_ids) if version_ids else {}
    analyzed = [
        row for row in contracts
        if versions.get(str(row.get("current_version_id")), {}).get("analysis_status") == "complete"
    ]
    return analyzed, versions


def build_attach_plan(
    analyzed_contracts: list[dict[str, Any]],
    versions_by_id: dict[str, dict[str, Any]],
    owner_uid: str,
    judge_uid: str,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    if len(analyzed_contracts) < 2:
        raise ValueError("Upload and analyze contracts in LexProof Alexa Demo first")

    ordered = sorted(analyzed_contracts, key=lambda item: str(item.get("name") or "").casefold())
    msa = next((item for item in ordered if re.search(r"\b(master services|\bmsa\b)", str(item.get("name") or ""), re.IGNORECASE)), None)
    if msa is None:
        raise ValueError("Upload and analyze a Master Services Agreement in LexProof Alexa Demo first")
    finance = next((item for item in ordered if item.get("id") != msa.get("id")), None)
    if finance is None:
        raise ValueError("Upload and analyze another contract in LexProof Alexa Demo first")

    candidate_contracts = [msa, *[item for item in ordered if item.get("id") != msa.get("id")]]
    candidates = extract_verified_payment_candidates(candidate_contracts, versions_by_id)
    if not candidates:
        raise ValueError("No numeric payment amounts with verbatim quotes were found in analyzed contract text")
    if len(candidates) < 3:
        raise ValueError("At least three verbatim payment amounts are required in analyzed contracts")

    stamp = datetime.combine(today, time.min, tzinfo=timezone.utc).isoformat()
    obligations: list[dict[str, Any]] = []
    due_dates = ((today - timedelta(days=2)).isoformat(), (today + timedelta(days=10)).isoformat(), (today + timedelta(days=25)).isoformat())
    statuses = ("PENDING_APPROVAL", "EXTRACTED", "PENDING_APPROVAL")
    labels = ("Overdue milestone", "Monthly fee", "Renewal fee")
    for index, (candidate, due_date, status, label) in enumerate(zip(candidates[:3], due_dates, statuses, labels)):
        contract = candidate["contract"]
        version = candidate["version"]
        assessed = assess_extracted_obligation(version["document_text"], {
            "label": label,
            "amount": candidate["amount"],
            "currency": "USD",
            "due_date": due_date,
            "trigger_text": label,
            "payer_name": str(contract.get("name") or "Contract").split()[0],
            "payer_email": "finance@example.test",
            "clause_ref": "Seeded from contract text",
            "clause_quote": candidate["quote"],
        })
        if assessed.get("needs_review_reason"):
            raise ValueError(f"Extracted payment quote did not validate: {assessed['needs_review_reason']}")
        obligations.append({
            "id": f"alexa-payment-{('initech-milestone', 'acme-monthly', 'globex-renewal')[index]}",
            "org_id": ORG_ID,
            "contract_id": contract.get("id"),
            "contract_version_id": version.get("id"),
            "contract_hash": str(version.get("content_hash") or ""),
            "status": status,
            "extracted_by": "seed:alexa-demo-attach-v1",
            "edited_by": judge_uid,
            "approved_by": None,
            "created_at": stamp,
            "updated_at": stamp,
                        **assessed,
        })

    workflows = [
        _workflow_records("legal-review", "Legal review", msa, judge_uid, stamp),
        _workflow_records("finance-review", "Finance review", finance, judge_uid, stamp),
    ]
    return {
        "org_id": ORG_ID,
        "owner_uid": owner_uid,
        "judge_uid": judge_uid,
        "analyzed_contracts": candidate_contracts,
        "workflows": workflows,
        "obligations": obligations,
    }


def _workflow_records(key: str, workflow_name: str, contract: dict[str, Any], judge_uid: str, stamp: str) -> dict[str, dict[str, Any]]:
    definition_id = f"alexa-{key}-definition"
    instance_id = str(uuid5(NAMESPACE_URL, f"{SEED_NAMESPACE}workflow-instance/{key}"))
    states = [
        {"id": "pending", "name": workflow_name, "is_initial": True},
        {"id": "approved", "name": "Approved", "is_terminal": True},
        {"id": "rejected", "name": "Rejected", "is_terminal": True},
    ]
    transitions = [
        {"id": "approve", "from_state": "pending", "to_state": "approved", "action_name": f"Approve {workflow_name.casefold()}", "allowed_roles": ["admin", "approver"], "requires_not_actor": ["created_by"]},
        {"id": "reject", "from_state": "pending", "to_state": "rejected", "action_name": f"Reject {workflow_name.casefold()}", "allowed_roles": ["admin", "approver"], "requires_not_actor": ["created_by"]},
    ]
    return {
        "definition": {
            "id": definition_id, "definition_id": definition_id, "org_id": ORG_ID,
            "name": workflow_name, "version": 1, "is_active": True,
            "states": states, "transitions": transitions, "created_by": judge_uid,
            "created_at": stamp, "updated_at": stamp,
        },
        "instance": {
            "id": instance_id, "instance_id": instance_id, "org_id": ORG_ID,
            "definition_id": definition_id, "definition_version": 1,
            "entity_type": "contract", "entity_id": contract.get("id"),
            "current_state": "pending", "status": "in_progress",
            "available_roles": ["admin", "approver"], "created_by": judge_uid,
            "created_at": stamp, "updated_at": stamp,
            "metadata": {"workflow_name": workflow_name},
        },
    }


def synthetic_record_ids() -> dict[str, tuple[str, ...]]:
    return {
        "contracts": SYNTHETIC_CONTRACTS,
        "contract_versions": SYNTHETIC_VERSIONS,
        "legal_passports": SYNTHETIC_PASSPORTS,
        "risk_findings": SYNTHETIC_FINDINGS,
        "workflow_definitions": SYNTHETIC_WORKFLOW_DEFINITIONS,
        "workflow_instances": SYNTHETIC_WORKFLOW_INSTANCES,
        "payment_obligations": SYNTHETIC_PAYMENT_IDS,
    }


def plan_synthetic_removal(repositories: dict[str, Any]) -> dict[str, list[str]]:
    plan: dict[str, list[str]] = {}
    for collection, candidates in synthetic_record_ids().items():
        repository = repositories[collection]
        plan[collection] = [
            record_id for record_id in candidates
            if (record := repository.get(record_id)) and record.get("org_id") == ORG_ID
        ]
    return plan


def apply_synthetic_removal(repositories: dict[str, Any], removal_plan: dict[str, list[str]]) -> dict[str, list[str]]:
    removed: dict[str, list[str]] = {}
    for instance_id in removal_plan.get("workflow_instances", []):
        instance = repositories["workflow_instances"].get(instance_id)
        if not instance or instance.get("org_id") != ORG_ID:
            continue
        history = repositories["workflow_history_factory"](instance_id)
        for event in list(history.stream()):
            event_id = str(event.get("id") or event.get("event_id") or "")
            if event_id:
                history.delete(event_id)
    for collection, record_ids in removal_plan.items():
        repository = repositories[collection]
        removed[collection] = []
        for record_id in record_ids:
            record = repository.get(record_id)
            if not record or record.get("org_id") != ORG_ID:
                continue
            repository.delete(record_id)
            removed[collection].append(record_id)
    return removed


def _resolve_accounts(owner_email: str, requested_judge_uid: str | None) -> tuple[str, str, str]:
    from app.lexproof.services.firebase import initialize_firebase
    from firebase_admin import auth

    initialize_firebase()
    try:
        owner_record = auth.get_user_by_email(owner_email.strip())
    except auth.UserNotFoundError as exc:
        raise ValueError("Owner email was not found in Firebase Auth") from exc
    allowed_judges = sorted(read_only_uids())
    judge_uid = requested_judge_uid or (allowed_judges[0] if len(allowed_judges) == 1 else None)
    if not judge_uid or judge_uid not in allowed_judges:
        raise ValueError("Pass --judge-uid matching a UID in LEXPROOF_READ_ONLY_UIDS")
    try:
        judge_record = auth.get_user(judge_uid)
    except auth.UserNotFoundError as exc:
        raise ValueError("Configured read-only judge UID was not found in Firebase Auth") from exc
    if owner_record.uid == judge_uid:
        raise ValueError("The owner and read-only judge must be different Firebase accounts")
    return owner_record.uid, judge_uid, str(judge_record.email or "")


def _repositories() -> dict[str, Any]:
    from app.lexproof.repositories.firestore import FirestoreRepository

    return {
        "contracts": FirestoreRepository("contracts"),
        "contract_versions": FirestoreRepository("contract_versions"),
        "legal_passports": FirestoreRepository("legal_passports"),
        "risk_findings": FirestoreRepository("risk_findings"),
        "workflow_definitions": FirestoreRepository("workflow_definitions"),
        "workflow_instances": FirestoreRepository("workflow_instances"),
        "payment_obligations": FirestoreRepository("payment_obligations"),
        "workflow_history_factory": lambda instance_id: FirestoreRepository(f"workflow_instances/{instance_id}/history"),
    }


def _apply_attach_plan(plan: dict[str, Any], repositories: dict[str, Any]) -> None:
    orgs = OrganizationService()
    org = orgs.orgs.get(ORG_ID)
    if not org:
        raise ValueError("Organization LexProof Alexa Demo was not found; create it and analyze at least two contracts first")
    orgs.orgs.set(ORG_ID, {"name": ORG_NAME, "status": "active"}, merge=True)
    stamp = datetime.now(timezone.utc).isoformat()
    for user_id, email, roles in (
        (plan["owner_uid"], plan["owner_email"], ["admin", "contract_owner"]),
        (plan["judge_uid"], plan["judge_email"], ["reviewer", "approver"]),
    ):
        existing = orgs.members(ORG_ID).get(user_id) or {}
        orgs.members(ORG_ID).set(user_id, {
            **existing,
            "user_id": user_id,
            "org_id": ORG_ID,
            "email": email.strip().lower() or existing.get("email"),
            "roles": roles,
            "status": "active",
            "invited_by": plan["owner_uid"],
            "created_at": existing.get("created_at") or stamp,
            "joined_at": existing.get("joined_at") or stamp,
            "updated_at": stamp,
        })
        orgs.upsert_user(user_id, email=email, add_org_id=ORG_ID)

    # Deterministic own IDs make attach rerunnable: replace only this seed's rows.
    for workflow in plan["workflows"]:
        definition = workflow["definition"]
        instance = workflow["instance"]
        repositories["workflow_definitions"].set(definition["id"], definition)
        repositories["workflow_instances"].set(instance["id"], instance)
    for obligation in plan["obligations"]:
        repositories["payment_obligations"].set(obligation["id"], obligation)


def _print_attach_summary(plan: dict[str, Any], *, apply: bool) -> None:
    print("APPLIED" if apply else "DRY RUN (no writes)")
    print(f"Organization ID: {ORG_ID}")
    print("Mode: attach to existing analyzed contracts; no contracts/passports/findings created")
    print(f"Contracts eligible: {len(plan['analyzed_contracts'])}")
    print("Pending workflows: Legal review, Finance review")
    print("Payment obligations: 3 (1 overdue, 2 due within 30 days)")


def _print_removal_plan(removal: dict[str, list[str]], *, apply: bool) -> None:
    print("REMOVED" if apply else "DRY RUN (no writes)")
    print(f"Organization ID: {ORG_ID}")
    for collection, record_ids in removal.items():
        print(f"{collection}: {len(record_ids)}" + (f" ({', '.join(record_ids)})" if record_ids else ""))
    print("passport_anchors: untouched")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-email", help="Existing Firebase Auth email for the Alexa demo owner/admin")
    parser.add_argument("--judge-uid", help="Read-only judge UID; defaults when exactly one UID is configured")
    parser.add_argument("--remove-synthetic", action="store_true", help="Remove only legacy synthetic seed IDs in the Alexa demo org")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Show planned changes only (the default)")
    mode.add_argument("--apply", action="store_true", help="Write changes")
    args = parser.parse_args(argv)
    try:
        repositories = _repositories()
        if args.remove_synthetic:
            removal = plan_synthetic_removal(repositories)
            if args.apply:
                apply_synthetic_removal(repositories, removal)
            _print_removal_plan(removal, apply=args.apply)
            return 0

        if not args.owner_email:
            parser.error("--owner-email is required in attach mode")
        owner_uid, judge_uid, judge_email = _resolve_accounts(args.owner_email, args.judge_uid)
        analyzed, versions = _analyzed_contracts(repositories["contracts"], repositories["contract_versions"])
        plan = build_attach_plan(
            analyzed,
            versions,
            owner_uid,
            judge_uid,
            owner_email=args.owner_email,
            judge_email=judge_email,
        )
        if args.apply:
            _apply_attach_plan(plan, repositories)
        _print_attach_summary(plan, apply=args.apply)
    except Exception as exc:
        print(f"Seed failed: {type(exc).__name__}; details omitted to protect credentials and account data.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())