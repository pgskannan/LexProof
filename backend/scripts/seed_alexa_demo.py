"""Seed the dedicated Ask Lexi / Alexa demo organization.

From ``backend/``:
  python scripts/seed_alexa_demo.py --owner-email owner@example.com --dry-run
  python scripts/seed_alexa_demo.py --owner-email owner@example.com --judge-uid JUDGE_UID --apply

Dry-run is the default. This script never submits blockchain transactions.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from app.lexproof.domains.passport.integrity import verify_passport_integrity
from app.lexproof.domains.passport.utils.hashing import (
    compute_passport_hash,
    hash_ai_analysis,
    hash_document,
    hash_evidence_package,
    hash_policy_version,
)
from app.lexproof.services.auth import read_only_uids
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.paypal.obligations import assess_extracted_obligation

ORG_ID = "lexproof-alexa-demo"
ORG_NAME = "LexProof Alexa Demo"
SEED_NAMESPACE = "https://lexproofsolutions.com/demo/alexa/"

CONTRACT_SPECS = (
    {
        "key": "acme-msa",
        "name": "Acme Master Services Agreement",
        "kind": "Master Services Agreement",
        "risk_score": 24.0,
        "finding_title": "Monthly fee has an extended payment window",
        "finding_text": "Acme's monthly fee is payable within 30 days after invoice.",
        "body": """MASTER SERVICES AGREEMENT\n\nAcme Corporation and LexProof Solutions agree that services will be provided for the initial term. The monthly service fee is USD 12,500, payable within thirty (30) days after invoice. Either party may terminate on thirty days' written notice. The provider will protect confidential information and maintain commercially reasonable security controls.""",
    },
    {
        "key": "globex-saas",
        "name": "Globex SaaS Subscription",
        "kind": "SaaS Subscription Agreement",
        "risk_score": 38.0,
        "finding_title": "Subscription renews automatically",
        "finding_text": "The subscription renews for successive annual terms unless notice is given.",
        "body": """SAAS SUBSCRIPTION AGREEMENT\n\nGlobex Corporation grants a subscription to its hosted service. The annual renewal fee is USD 18,000 and is due on the renewal date. The subscription automatically renews for one-year terms unless either party gives sixty days' notice. Customer data remains customer property.""",
    },
    {
        "key": "initech-sow",
        "name": "Initech Statement of Work",
        "kind": "Statement of Work",
        "risk_score": 42.0,
        "finding_title": "Milestone acceptance is not time-bounded",
        "finding_text": "The statement of work does not define a response period for milestone acceptance.",
        "body": """STATEMENT OF WORK\n\nInitech Services will deliver implementation services in three milestones. The first milestone payment of USD 7,500 is due on 2026-10-01. The second milestone payment of USD 9,000 is due after user acceptance testing. The final milestone payment of USD 5,000 is due at production launch. Customer will review each deliverable and provide written acceptance.""",
    },
    {
        "key": "umbrella-nda",
        "name": "Umbrella NDA",
        "kind": "Non-Disclosure Agreement",
        "risk_score": 18.0,
        "finding_title": "Confidentiality term should be confirmed",
        "finding_text": "The confidentiality obligations have a defined survival period.",
        "body": """NON-DISCLOSURE AGREEMENT\n\nUmbrella Group and LexProof Solutions will protect confidential information using reasonable care. Confidentiality obligations continue for five years after disclosure, except for trade secrets, which remain protected while they qualify as trade secrets. No intellectual property license is granted.""",
    },
    {
        "key": "stark-po-terms",
        "name": "Stark Purchase Order Terms",
        "kind": "Purchase Order Terms",
        "risk_score": 31.0,
        "finding_title": "Purchase order terms do not specify a liability cap",
        "finding_text": "The purchase order terms do not include a clear aggregate liability cap.",
        "body": """PURCHASE ORDER TERMS\n\nStark Industries will purchase the listed goods at the prices stated on each purchase order. Invoices are payable within forty-five days after receipt. Delivery dates are estimates unless expressly marked firm. These terms do not set an aggregate cap on either party's liability.""",
    },
)


def _stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{SEED_NAMESPACE}{kind}/{key}"))


def _passport_record(contract: dict[str, Any], version: dict[str, Any], spec: dict[str, Any], owner_uid: str, stamp: str) -> dict[str, Any]:
    passport_id = _stable_id("passport", spec["key"])
    text = version["document_text"]
    normalized = " ".join(text.split())
    policy_content = "LexProof demo policy: identify contract risks and obligations."
    analysis = {
        "risk_score": spec["risk_score"],
        "compliance_score": 92.0,
        "findings": [{"title": spec["finding_title"], "description": spec["finding_text"]}],
    }
    document_hash = hash_document(text, normalized)
    policy_hash = hash_policy_version("default-policy", policy_content, "1.0")
    analysis_hash = hash_ai_analysis(analysis, "risk_and_compliance", "seeded-demo")
    evidence_hash = hash_evidence_package([])
    passport_hash = compute_passport_hash(document_hash, policy_hash, analysis_hash, evidence_hash)
    return {
        "id": passport_id,
        "passport_id": passport_id,
        "org_id": ORG_ID,
        "owner_id": owner_uid,
        "contract_id": contract["id"],
        "contract_version": 1,
        "version_id": version["id"],
        "document_hash": document_hash,
        "policy_hash": policy_hash,
        "analysis_hash": analysis_hash,
        "evidence_hash": evidence_hash,
        "risk_score": spec["risk_score"],
        "compliance_score": 92.0,
        "risk_level": "medium" if spec["risk_score"] >= 30 else "low",
        "evidence_count": 0,
        "policy_version": "1.0",
        "created_at": stamp,
        "created_by": owner_uid,
        "status": "created",
        "ai_provider": "vertex_ai",
        "ai_model": "seeded-demo",
        "audit_events": [],
        "metadata": {
            "passport_hash": passport_hash,
            "contract_name": spec["name"],
            "original_document_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "normalized_document_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "verification_snapshot": {
                "document_content": text,
                "normalized_document": normalized,
                "policy_content": policy_content,
                "policy_id": "default-policy",
                "policy_version": "1.0",
                "analysis_result": analysis,
                "analysis_type": "risk_and_compliance",
                "ai_provider": "vertex_ai",
                "ai_model": "seeded-demo",
                "evidence_items": [],
            },
        },
    }


def build_seed_plan(
    owner_uid: str,
    judge_uid: str,
    *,
    owner_email: str = "",
    judge_email: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    stamp = datetime.combine(today, time.min, tzinfo=timezone.utc).isoformat()
    contracts: list[dict[str, Any]] = []
    versions: list[dict[str, Any]] = []
    passports: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for spec in CONTRACT_SPECS:
        contract_id = f"alexa-{spec['key']}"
        version_id = f"{contract_id}-v1"
        passport_id = _stable_id("passport", spec["key"])
        document_text = spec["body"]
        content_hash = hashlib.sha256(document_text.encode("utf-8")).hexdigest()
        contract = {
            "id": contract_id,
            "contract_id": contract_id,
            "org_id": ORG_ID,
            "owner_id": owner_uid,
            "name": spec["name"],
            "status": "uploaded",
            "current_version_id": version_id,
            "created_at": stamp,
            "updated_at": stamp,
        }
        version = {
            "id": version_id,
            "org_id": ORG_ID,
            "contract_id": contract_id,
            "owner_id": owner_uid,
            "version_number": 1,
            "filename": f"{spec['key']}.txt",
            "content_type": "text/plain",
            "document_text": document_text,
            "content_hash": content_hash,
            "analysis_status": "complete",
            "passport_id": passport_id,
            "created_at": stamp,
            "created_by": owner_uid,
        }
        passport = _passport_record(contract, version, spec, owner_uid, stamp)
        findings.append({
            "id": f"{contract_id}-finding-1",
            "finding_id": f"{contract_id}-finding-1",
            "org_id": ORG_ID,
            "contract_id": contract_id,
            "version_id": version_id,
            "title": spec["finding_title"],
            "description": spec["finding_text"],
            "severity": "medium" if spec["risk_score"] >= 30 else "low",
            "created_at": stamp,
        })
        contracts.append(contract)
        versions.append(version)
        passports.append(passport)

    workflows = [
        _workflow_records("legal-review", "Legal review", contracts[0], judge_uid, stamp),
        _workflow_records("finance-review", "Finance review", contracts[2], judge_uid, stamp),
    ]
    obligations = [
        _payment_record("initech-milestone", contracts[2], versions[2], owner_uid, judge_uid, "Initech milestone", "7500.00", (today - timedelta(days=2)).isoformat(), "PENDING_APPROVAL", "USD 7,500 is due on 2026-10-01."),
        _payment_record("acme-monthly", contracts[0], versions[0], owner_uid, judge_uid, "Acme monthly fee", "12500.00", (today + timedelta(days=10)).isoformat(), "EXTRACTED", "The monthly service fee is USD 12,500, payable within thirty (30) days after invoice."),
        _payment_record("globex-renewal", contracts[1], versions[1], owner_uid, judge_uid, "Globex renewal", "18000.00", (today + timedelta(days=25)).isoformat(), "PENDING_APPROVAL", "The annual renewal fee is USD 18,000 and is due on the renewal date."),
    ]
    acme_passport = passports[0]
    eligibility = verify_passport_integrity(acme_passport, [])
    if not eligibility.get("verified"):
        raise ValueError("Seeded Acme passport snapshot is not integrity-verifiable")
    return {
        "org": {"org_id": ORG_ID, "name": ORG_NAME, "status": "active", "created_by": owner_uid, "created_at": stamp},
        "owner_uid": owner_uid,
        "owner_email": owner_email,
        "judge_uid": judge_uid,
        "judge_email": judge_email,
        "contracts": contracts,
        "versions": versions,
        "passports": passports,
        "findings": findings,
        "workflows": workflows,
        "obligations": obligations,
        "passport_anchor_eligible": True,
    }


def _workflow_records(key: str, workflow_name: str, contract: dict[str, Any], judge_uid: str, stamp: str) -> dict[str, dict[str, Any]]:
    definition_id = f"alexa-{key}-definition"
    instance_id = _stable_id("workflow-instance", key)
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
            "id": definition_id,
            "definition_id": definition_id,
            "org_id": ORG_ID,
            "name": workflow_name,
            "version": 1,
            "is_active": True,
            "states": states,
            "transitions": transitions,
            "created_by": judge_uid,
            "created_at": stamp,
            "updated_at": stamp,
        },
        "instance": {
            "id": instance_id,
            "instance_id": instance_id,
            "org_id": ORG_ID,
            "definition_id": definition_id,
            "definition_version": 1,
            "entity_type": "contract",
            "entity_id": contract["id"],
            "current_state": "pending",
            "status": "in_progress",
            "available_roles": ["admin", "approver"],
            "created_by": judge_uid,
            "created_at": stamp,
            "updated_at": stamp,
            "metadata": {},
        },
    }


def _payment_record(key: str, contract: dict[str, Any], version: dict[str, Any], owner_uid: str, editor_uid: str, label: str, amount: str, due_date: str, status: str, quote: str) -> dict[str, Any]:
    assessed = assess_extracted_obligation(
        version["document_text"],
        {
            "label": label,
            "amount": amount,
            "currency": "USD",
            "due_date": due_date,
            "trigger_text": label,
            "payer_name": contract["name"].split()[0],
            "payer_email": "finance@example.test",
            "clause_ref": "Payment terms",
            "clause_quote": quote,
        },
    )
    return {
        "id": f"alexa-payment-{key}",
        "org_id": ORG_ID,
        "contract_id": contract["id"],
        "contract_version_id": version["id"],
        "contract_hash": version["content_hash"],
        "status": status,
        "extracted_by": "seed:alexa-demo-v1",
        "edited_by": editor_uid,
        "approved_by": None,
        "created_at": "2026-10-12T00:00:00+00:00",
        "updated_at": "2026-10-12T00:00:00+00:00",
        **assessed,
    }


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


def _apply_plan(plan: dict[str, Any]) -> None:
    from app.lexproof.repositories.firestore import FirestoreRepository
    from app.lexproof.services.organizations import OrganizationService

    orgs = OrganizationService()
    existing_org = orgs.orgs.get(ORG_ID)
    if existing_org:
        orgs.orgs.set(ORG_ID, {"name": ORG_NAME, "status": "active"}, merge=True)
    else:
        orgs.create_org(
            ORG_NAME,
            plan["owner_uid"],
            org_id=ORG_ID,
            creator_email=plan["owner_email"],
            roles=["admin", "contract_owner"],
        )
    stamp = plan["org"]["created_at"]
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

    repositories = {
        "contracts": FirestoreRepository("contracts"),
        "contract_versions": FirestoreRepository("contract_versions"),
        "legal_passports": FirestoreRepository("legal_passports"),
        "risk_findings": FirestoreRepository("risk_findings"),
        "workflow_definitions": FirestoreRepository("workflow_definitions"),
        "workflow_instances": FirestoreRepository("workflow_instances"),
        "payment_obligations": FirestoreRepository("payment_obligations"),
    }
    for collection, key in (("contracts", "contracts"), ("contract_versions", "versions"), ("legal_passports", "passports"), ("risk_findings", "findings"), ("payment_obligations", "obligations")):
        for record in plan[key]:
            doc_id = str(record.get("id") or record.get("contract_id"))
            repositories[collection].set(doc_id, record)
    for workflow in plan["workflows"]:
        definition = workflow["definition"]
        instance = workflow["instance"]
        repositories["workflow_definitions"].set(definition["id"], definition)
        repositories["workflow_instances"].set(instance["id"], instance)


def _print_summary(plan: dict[str, Any], *, apply: bool) -> None:
    mode = "APPLIED" if apply else "DRY RUN (no writes)"
    print(f"{mode}: {ORG_NAME}")
    print(f"Organization ID: {ORG_ID}")
    print(f"Contracts: {len(plan['contracts'])} analyzed")
    print("Workflows: 2 pending")
    print(f"Payment obligations: {len(plan['obligations'])} (1 overdue, 2 due within 30 days)")
    print(f"Acme passport eligible for UI anchoring: {'yes' if plan['passport_anchor_eligible'] else 'no'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-email", required=True, help="Existing Firebase Auth email for the org owner/admin")
    parser.add_argument("--judge-uid", help="Read-only judge UID; defaults when exactly one UID is configured")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Show planned changes only (the default)")
    mode.add_argument("--apply", action="store_true", help="Write or refresh the dedicated Alexa demo data")
    args = parser.parse_args(argv)
    try:
        owner_uid, judge_uid, judge_email = _resolve_accounts(args.owner_email, args.judge_uid)
        plan = build_seed_plan(
            owner_uid,
            judge_uid,
            owner_email=args.owner_email,
            judge_email=judge_email,
        )
        if args.apply:
            _apply_plan(plan)
        _print_summary(plan, apply=args.apply)
    except Exception as exc:
        print(f"Seed failed: {type(exc).__name__}; details omitted to protect credentials and account data.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
