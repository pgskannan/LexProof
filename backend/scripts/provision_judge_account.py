r"""Create (or update) the read-only hackathon judge login.

  UID    demo-judge-1
  Email  judge@lexproof.demo
  Org    LexProof Demo (lexproof-demo), role: auditor

The account is read-only because the API refuses every data-changing request
from UIDs listed in LEXPROOF_READ_ONLY_UIDS (set to demo-judge-1 on Cloud Run
by backend/deploy/deploy-cloud-run.ps1). Judges can open every page, ask
Lexi, verify passports and export evidence packs, but cannot upload, edit,
approve or anchor anything.

The password is read from JUDGE_DEMO_PASSWORD, or prompted (hidden). It is
never printed. Re-running resets the password to the one you give.

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

JUDGE_UID = "demo-judge-1"
JUDGE_EMAIL = "judge@lexproof.demo"
JUDGE_NAME = "Hackathon Judge"
JUDGE_ROLES = ["auditor"]


def main() -> None:
    password = os.getenv("JUDGE_DEMO_PASSWORD") or getpass.getpass("Password for the judge account (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    initialize_firebase()
    from firebase_admin import auth

    try:
        auth.get_user(JUDGE_UID)
        auth.update_user(JUDGE_UID, email=JUDGE_EMAIL, password=password, display_name=JUDGE_NAME, disabled=False)
        print(f"Updated Firebase user {JUDGE_UID} ({JUDGE_EMAIL}).")
    except auth.UserNotFoundError:
        auth.create_user(uid=JUDGE_UID, email=JUDGE_EMAIL, password=password, display_name=JUDGE_NAME)
        print(f"Created Firebase user {JUDGE_UID} ({JUDGE_EMAIL}).")

    orgs = get_organization_service()
    member = orgs.ensure_member(DEFAULT_ORG_ID, JUDGE_UID, JUDGE_ROLES, email=JUDGE_EMAIL, invited_by="provision_judge_account")
    orgs.upsert_user(JUDGE_UID, email=JUDGE_EMAIL, display_name=JUDGE_NAME, add_org_id=DEFAULT_ORG_ID)
    if sorted(member.get("roles") or []) != JUDGE_ROLES:
        print(f"WARNING: {JUDGE_UID} already had roles {member.get('roles')}; set them to {JUDGE_ROLES} in Settings > Members.")
    print(f"Member of {DEFAULT_ORG_ID} with roles {member.get('roles')}. Status: {member.get('status')}.")
    print("Read-only mode needs LEXPROOF_READ_ONLY_UIDS=demo-judge-1 on Cloud Run (the deploy script sets it).")


if __name__ == "__main__":
    main()
