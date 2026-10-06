r"""Create (or update) the hackathon judge logins.

  demo-judge-1  judge@lexproof.demo            auditor   (view everything)
  demo-judge-2  judge-approver@lexproof.demo   approver  (PayPal demo contract only)

Both stay read-only except the PayPal judge sandbox. demo-judge-1 may run the
payment agent on LEXPROOF_JUDGE_SANDBOX_CONTRACT_ID. demo-judge-2 may approve
and execute payment actions on that same contract. A refund still needs the
second account. Put the shared password only in Devpost's private testing
instructions. This script never prints it.

Usage (from backend/):
    .\.venv\Scripts\python.exe scripts\provision_judge_account.py
"""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.services.firebase import initialize_firebase
from app.lexproof.services.organizations import DEFAULT_ORG_ID, get_organization_service

ACCOUNTS = (
    ("demo-judge-1", "judge@lexproof.demo", "Hackathon Judge", ["auditor"]),
    ("demo-judge-2", "judge-approver@lexproof.demo", "Hackathon Judge Approver", ["approver"]),
)


def _upsert(auth, orgs, uid: str, email: str, name: str, roles: list[str], password: str) -> None:
    try:
        auth.get_user(uid)
        auth.update_user(uid, email=email, password=password, display_name=name, disabled=False)
        print(f"Updated Firebase user {uid} ({email}).")
    except auth.UserNotFoundError:
        auth.create_user(uid=uid, email=email, password=password, display_name=name)
        print(f"Created Firebase user {uid} ({email}).")
    member = orgs.ensure_member(DEFAULT_ORG_ID, uid, roles, email=email, invited_by="provision_judge_account")
    orgs.upsert_user(uid, email=email, display_name=name, add_org_id=DEFAULT_ORG_ID)
    if sorted(member.get("roles") or []) != roles:
        print(f"WARNING: {uid} already had roles {member.get('roles')}; set them to {roles} in Settings > Members.")
    print(f"Member of {DEFAULT_ORG_ID} with roles {member.get('roles')}. Status: {member.get('status')}.")


def main() -> None:
    password = os.getenv("JUDGE_DEMO_PASSWORD") or getpass.getpass("Password for the judge accounts (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    initialize_firebase()
    from firebase_admin import auth

    orgs = get_organization_service()
    for uid, email, name, roles in ACCOUNTS:
        _upsert(auth, orgs, uid, email, name, roles, password)
    print("Both accounts share that password. Do not commit it. Put it only in Devpost's private testing instructions.")
    print("PayPal staging sets LEXPROOF_READ_ONLY_UIDS=demo-judge-1,demo-judge-2 and LEXPROOF_JUDGE_SANDBOX_CONTRACT_ID.")
    print("demo-judge-1 can run the agent on that contract. demo-judge-2 approves money leaving the merchant there only.")


if __name__ == "__main__":
    main()
