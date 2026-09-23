"""One-time, narrowly-scoped utility: create/verify real Firebase
Authentication Email/Password credentials for the THREE new identities the
"LexProof -- Close Remaining E2E Security & Workflow Gaps" follow-up task
needs, and ONLY those three.

Why this exists
----------------
Phase 2 (cross-tenant isolation) and Phase 3 (dual-role separation-of-duty)
of that follow-up need real, loggable-in Firebase users for:

    demo-tenant-b-owner-1     -> contract_owner in a genuinely SEPARATE
                                  second org ("lexproof-demo-tenant-b")
    demo-tenant-b-reviewer-1  -> reviewer in that same second org
    demo-dual-role-1          -> contract_owner AND reviewer, together, in
                                  the EXISTING "lexproof-demo" org

None of the three exist as Firebase Authentication users yet -- only as
Firestore application-level identities once
scripts/create_approval_demo_fixture.py's create_cross_tenant_isolation_fixture()
/ create_dual_role_sod_fixture() have been run. Without a real Firebase
Auth credential, none of them can log in through the real LexProof UI,
which blocks the real-Firebase-auth E2E tests those two phases require.

This script exists to close exactly that gap, and nothing else. It is a
direct sibling of provision_demo_workflow_identities.py (same pattern,
same safety guarantees), scoped to these three different UIDs -- that
script's own ALLOWED_UIDS is intentionally not extended, so as to not
touch its own tightly-scoped, already-reviewed safety contract.

What this script is allowed to do
----------------------------------
For each of exactly ALLOWED_UIDS below:
  - If no Firebase user exists with that UID: create ONE, with that EXACT
    custom UID (firebase_admin.auth.create_user(uid=..., email=..., password=...)),
    the deterministic email from EMAIL_BY_UID, and Email/Password sign-in.
  - If a Firebase user with that UID already exists: verify (never silently
    overwrite) its email and whether it already has a password sign-in
    provider attached. Only calls update_user to ATTACH a missing
    email/password credential -- never to change an email that doesn't
    already match the deterministic value below, and never to reset a
    password that is already attached (rerunning this script is a no-op
    once a UID is fully provisioned).
  - If the deterministic email is already registered to a DIFFERENT UID:
    abort with a clear error before touching anything. That other Firebase
    user is never read further or modified.

What this script will NEVER do
-------------------------------
  - It never targets any UID outside ALLOWED_UIDS below. A CLI --uid value
    outside that set aborts before any Firebase call.
  - It never touches demo-owner-1, demo-reviewer-1, demo-approver-1, or
    demo-admin-1 -- those identities' provisioning belongs exclusively to
    provision_demo_workflow_identities.py / provision_demo_admin_email_password.py.
  - It never changes the email on an existing Firebase user (a genuine
    email mismatch aborts loudly instead).
  - It never resets a password that is already attached.
  - It never prints, logs, or writes to a file any password value.
  - It is never imported or invoked by the application, by pytest, by
    Playwright, by application startup, or by create_approval_demo_fixture.py.
    It is a human-run, manually-invoked CLI only.

Deterministic email convention
-------------------------------
Reuses the SAME "<uid>@lexproof.local" convention every other fixture
identity in this repo already uses (see create_approval_demo_fixture.py's
_ensure_org and the new create_cross_tenant_isolation_fixture /
create_dual_role_sod_fixture, whose Firestore member records already carry
these exact emails).

How to run it (a human runs this deliberately; it is never imported or
invoked by the application, by tests, or by CI):

    cd backend
    python scripts/provision_e2e_security_identities.py
        # all three, prompting for each password via hidden input

Each identity's password can instead be read from its own environment
variable (see PASSWORD_ENV_BY_UID below), or, if unset, prompted
interactively via getpass (input hidden) -- the same pattern as
provision_demo_workflow_identities.py. Passwords are never accepted as CLI
arguments and never printed.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Callable, NamedTuple

# The ONLY UIDs this script is allowed to touch. Not extensible via CLI;
# any other value is rejected before any Firebase call is made.
EMAIL_BY_UID: dict[str, str] = {
    "demo-tenant-b-owner-1": "demo-tenant-b-owner-1@lexproof.local",
    "demo-tenant-b-reviewer-1": "demo-tenant-b-reviewer-1@lexproof.local",
    "demo-dual-role-1": "demo-dual-role-1@lexproof.local",
}
ALLOWED_UIDS = tuple(EMAIL_BY_UID)

PASSWORD_ENV_BY_UID: dict[str, str] = {
    "demo-tenant-b-owner-1": "DEMO_TENANT_B_OWNER_PROVISION_PASSWORD",
    "demo-tenant-b-reviewer-1": "DEMO_TENANT_B_REVIEWER_PROVISION_PASSWORD",
    "demo-dual-role-1": "DEMO_DUAL_ROLE_PROVISION_PASSWORD",
}


class UnverifiedUser(NamedTuple):
    uid: str
    email: str | None
    has_password_provider: bool


class ProvisioningError(RuntimeError):
    """Raised whenever a safety guard rejects the requested operation."""


class EmailConflictError(ProvisioningError):
    """Raised when the deterministic email for a UID already belongs to a
    DIFFERENT Firebase user. The other user is never modified."""


def validate_allowed_uid(uid: str) -> None:
    if uid not in ALLOWED_UIDS:
        raise ProvisioningError(
            f"Refusing to operate on UID {uid!r}; this script only ever targets "
            f"{sorted(ALLOWED_UIDS)!r}."
        )


class ProvisioningResult(NamedTuple):
    uid: str
    action: str  # "created" | "credential_attached" | "already_provisioned"


def provision_identity(
    uid: str,
    password: str,
    *,
    get_user_fn: Callable[[str], UnverifiedUser | None],
    get_user_by_email_fn: Callable[[str], UnverifiedUser | None],
    create_user_fn: Callable[..., UnverifiedUser],
    update_user_fn: Callable[..., UnverifiedUser],
) -> ProvisioningResult:
    validate_allowed_uid(uid)
    if not password:
        raise ProvisioningError(f"A password value is required for {uid!r} and was not supplied.")
    expected_email = EMAIL_BY_UID[uid]

    by_email = get_user_by_email_fn(expected_email)
    if by_email is not None and by_email.uid != uid:
        raise EmailConflictError(
            f"{expected_email!r} is already registered to Firebase UID {by_email.uid!r}, "
            f"not {uid!r}. Refusing to create or modify anything."
        )

    existing = get_user_fn(uid)
    if existing is None:
        created = create_user_fn(uid=uid, email=expected_email, password=password)
        if created.uid != uid:
            raise ProvisioningError(
                f"Firebase returned UID {created.uid!r} after create, expected {uid!r}. "
                "Treating this as a failure; no further action taken."
            )
        return ProvisioningResult(uid=uid, action="created")

    if existing.email and existing.email != expected_email:
        raise ProvisioningError(
            f"Firebase UID {uid!r} already exists with email {existing.email!r}, which "
            f"does not match the deterministic value {expected_email!r}. Refusing to "
            "silently overwrite an existing user's email -- resolve this manually."
        )

    if existing.has_password_provider:
        return ProvisioningResult(uid=uid, action="already_provisioned")

    updated = update_user_fn(uid, email=expected_email, password=password)
    if updated.uid != uid:
        raise ProvisioningError(
            f"Firebase returned UID {updated.uid!r} after update, expected {uid!r}. "
            "Treating this as a failure; no further action taken."
        )
    return ProvisioningResult(uid=uid, action="credential_attached")


def _prompt_for_password(uid: str) -> str:
    password = getpass.getpass(f"Password for {uid} (input hidden): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise ProvisioningError(f"Passwords did not match for {uid}.")
    return password


def _real_auth_functions() -> tuple[
    Callable[[str], UnverifiedUser | None],
    Callable[[str], UnverifiedUser | None],
    Callable[..., UnverifiedUser],
    Callable[..., UnverifiedUser],
]:
    backend_root = Path(__file__).resolve().parent.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.lexproof.services.firebase import initialize_firebase
    from firebase_admin import auth

    initialize_firebase()

    def _to_unverified(record: object) -> UnverifiedUser:
        provider_data = getattr(record, "provider_data", None) or []
        has_password = any(getattr(p, "provider_id", None) == "password" for p in provider_data)
        return UnverifiedUser(uid=record.uid, email=record.email, has_password_provider=has_password)

    def get_user(uid: str) -> UnverifiedUser | None:
        try:
            return _to_unverified(auth.get_user(uid))
        except auth.UserNotFoundError:
            return None

    def get_user_by_email(email: str) -> UnverifiedUser | None:
        try:
            return _to_unverified(auth.get_user_by_email(email))
        except auth.UserNotFoundError:
            return None

    return get_user, get_user_by_email, auth.create_user, auth.update_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-time utility: create/verify real Firebase Email/Password "
            f"credentials for {', '.join(ALLOWED_UIDS)} ONLY."
        )
    )
    parser.add_argument(
        "--uid",
        nargs="+",
        default=list(ALLOWED_UIDS),
        help=f"One or more of {list(ALLOWED_UIDS)} (default: all three).",
    )
    args = parser.parse_args(argv)

    for uid in args.uid:
        try:
            validate_allowed_uid(uid)
        except ProvisioningError as exc:
            print(f"ABORTED: {exc}", file=sys.stderr)
            return 2

    try:
        get_user_fn, get_user_by_email_fn, create_user_fn, update_user_fn = _real_auth_functions()
    except Exception as exc:  # noqa: BLE001
        print(f"ABORTED: could not initialize Firebase Admin: {exc}", file=sys.stderr)
        return 2

    exit_code = 0
    for uid in args.uid:
        password = os.environ.get(PASSWORD_ENV_BY_UID[uid]) or _prompt_for_password(uid)
        try:
            result = provision_identity(
                uid, password,
                get_user_fn=get_user_fn,
                get_user_by_email_fn=get_user_by_email_fn,
                create_user_fn=create_user_fn,
                update_user_fn=update_user_fn,
            )
        except ProvisioningError as exc:
            print(f"ABORTED for {uid}: {exc}", file=sys.stderr)
            exit_code = 2
            continue
        finally:
            password = None  # noqa: F841

        if result.action == "created":
            print(f"SUCCESS: created Firebase user {result.uid} ({EMAIL_BY_UID[result.uid]}).")
        elif result.action == "credential_attached":
            print(f"SUCCESS: attached Email/Password credential to existing Firebase user {result.uid}.")
        else:
            print(f"NO CHANGE: {result.uid} already has an Email/Password credential attached.")

    print("No UID outside the allow-list was touched. No password was printed.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
