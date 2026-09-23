"""One-time, narrowly-scoped utility: create/verify real Firebase
Authentication Email/Password credentials for LexProof's three deterministic
golden-path workflow identities -- and ONLY those three.

Why this exists
----------------
Phase 3J-B's deterministic fixture (backend/scripts/create_approval_demo_fixture.py)
created three application-level (Firestore) identities for the golden-path
workflow's three distinct roles:

    demo-owner-1     -> contract_owner
    demo-reviewer-1  -> reviewer
    demo-approver-1  -> approver

A live, read-only Firebase Authentication audit (Phase 3K-A) confirmed none
of the three exist as Firebase Authentication users, so none of them can log
in through the real LexProof UI -- which blocks proving real, role-separated
browser E2E coverage (Phase 3K-A/3K-B) without falling back to the admin
account, which the workflow's separation-of-duties design exists specifically
to NOT allow.

This script exists to close exactly that gap, and nothing else.

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
  - It never accepts or creates a Firebase user for the demo-admin-1 UID --
    that identity's provisioning is provision_demo_admin_email_password.py's
    job, exclusively, unchanged. This script does not import, call, or
    duplicate any of that script's logic.
  - It never changes the email on an existing Firebase user (a genuine
    email mismatch aborts loudly instead).
  - It never resets a password that is already attached.
  - It never prints, logs, or writes to a file any password value.
  - It is never imported or invoked by the application, by pytest, by
    Playwright, by application startup, or by the Phase 3J-B fixture
    script. It is a human-run, manually-invoked CLI only (see "How to run
    it" below) -- this file is intentionally NOT executed as part of
    writing it.

Deterministic email convention
-------------------------------
Reuses the SAME "<uid>@lexproof.local" convention Phase 3J-B's fixture
already set as each member's Firestore `email` field (see
create_approval_demo_fixture.py's `_ensure_org`), so the Firebase
Authentication email matches the existing Firestore membership record --
not a new convention, and never a real personal address.

email_verified
---------------
Deliberately left at the Firebase Admin SDK's default (unset/false) on
creation, and never touched on update. Nothing in this backend gates any
behavior on email_verified (grep confirms zero references), and
provision_demo_admin_email_password.py -- the one other script that
provisions a real E2E login identity -- never sets it either. Setting it
here would be a new, unreviewed convention this script has no reason to
introduce.

How it authenticates to Firebase
---------------------------------
Reuses the project's existing Firebase Admin initialization
(`app.lexproof.services.firebase.initialize_firebase`), exactly like
provision_demo_admin_email_password.py.

How to run it (a human runs this deliberately; it is never imported or
invoked by the application, by tests, or by CI):

    cd backend
    python scripts/provision_demo_workflow_identities.py --uid demo-owner-1 demo-reviewer-1 demo-approver-1

Each identity's password is read from its own environment variable
(DEMO_OWNER_PROVISION_PASSWORD / DEMO_REVIEWER_PROVISION_PASSWORD /
DEMO_APPROVER_PROVISION_PASSWORD), or, if unset, prompted interactively via
getpass (input hidden) -- the same pattern as provision_demo_admin_email_password.py.
Passwords are never accepted as CLI arguments and never printed.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Callable, NamedTuple

# The ONLY UIDs this script is allowed to touch -- the three Phase 3J-B
# golden-path workflow role identities. Not extensible via CLI; any other
# value is rejected before any Firebase call is made. demo-admin-1 is
# deliberately excluded: that identity belongs exclusively to
# provision_demo_admin_email_password.py.
EMAIL_BY_UID: dict[str, str] = {
    "demo-owner-1": "demo-owner-1@lexproof.local",
    "demo-reviewer-1": "demo-reviewer-1@lexproof.local",
    "demo-approver-1": "demo-approver-1@lexproof.local",
}
ALLOWED_UIDS = tuple(EMAIL_BY_UID)

# uid -> the environment variable this script reads that uid's password
# from, if set (otherwise prompted interactively via getpass).
PASSWORD_ENV_BY_UID: dict[str, str] = {
    "demo-owner-1": "DEMO_OWNER_PROVISION_PASSWORD",
    "demo-reviewer-1": "DEMO_REVIEWER_PROVISION_PASSWORD",
    "demo-approver-1": "DEMO_APPROVER_PROVISION_PASSWORD",
}


class UnverifiedUser(NamedTuple):
    """The minimal shape this module needs from a Firebase UserRecord.

    A small local type (rather than importing firebase_admin's UserRecord
    at module scope) keeps this module importable -- and its safety logic
    unit-testable -- without the firebase_admin package installed."""

    uid: str
    email: str | None
    has_password_provider: bool


class ProvisioningError(RuntimeError):
    """Raised whenever a safety guard rejects the requested operation."""


class EmailConflictError(ProvisioningError):
    """Raised when the deterministic email for a UID already belongs to a
    DIFFERENT Firebase user. The other user is never modified."""


def validate_allowed_uid(uid: str) -> None:
    """Abort unless `uid` is one of the three UIDs this script may touch."""
    if uid not in ALLOWED_UIDS:
        raise ProvisioningError(
            f"Refusing to operate on UID {uid!r}; this script only ever targets "
            f"{sorted(ALLOWED_UIDS)!r}. demo-admin-1 is provisioned exclusively by "
            "provision_demo_admin_email_password.py, not this script."
        )


class ProvisioningResult(NamedTuple):
    uid: str
    action: str  # "created" | "credential_attached" | "already_provisioned"


def provision_workflow_identity(
    uid: str,
    password: str,
    *,
    get_user_fn: Callable[[str], UnverifiedUser | None],
    get_user_by_email_fn: Callable[[str], UnverifiedUser | None],
    create_user_fn: Callable[..., UnverifiedUser],
    update_user_fn: Callable[..., UnverifiedUser],
) -> ProvisioningResult:
    """Idempotently ensure `uid` (one of ALLOWED_UIDS) is a real Firebase
    Email/Password user at its deterministic email. Never touches any other
    UID. See module docstring for the exact safety guarantees.

    `get_user_fn` returns None (not an exception) when the UID does not
    exist -- callers below pass a thin adapter over
    firebase_admin.auth.get_user that catches UserNotFoundError, so this
    function's own logic stays exception-free and easy to unit test.
    """
    validate_allowed_uid(uid)
    if not password:
        raise ProvisioningError(f"A password value is required for {uid!r} and was not supplied.")
    expected_email = EMAIL_BY_UID[uid]

    # Email-conflict guard: if the deterministic email already belongs to a
    # DIFFERENT uid, stop before touching anything -- including before the
    # get_user(uid) lookup below, so a conflict is always caught regardless
    # of whether `uid` itself happens to already exist.
    by_email = get_user_by_email_fn(expected_email)
    if by_email is not None and by_email.uid != uid:
        raise EmailConflictError(
            f"{expected_email!r} is already registered to Firebase UID {by_email.uid!r}, "
            f"not {uid!r}. Refusing to create or modify anything -- that other Firebase "
            "user was not read further and was not touched."
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
        # Already fully provisioned. Do not reset an existing password.
        return ProvisioningResult(uid=uid, action="already_provisioned")

    updated = update_user_fn(uid, email=expected_email, password=password)
    if updated.uid != uid:
        raise ProvisioningError(
            f"Firebase returned UID {updated.uid!r} after update, expected {uid!r}. "
            "Treating this as a failure; no further action taken."
        )
    return ProvisioningResult(uid=uid, action="credential_attached")


def _prompt_for_password(uid: str) -> str:
    """Read the password via getpass (not echoed, not a CLI argument, so it
    never lands in shell history or a process listing)."""
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
    """Initialize Firebase Admin using the project's EXISTING mechanism and
    return (get_user, get_user_by_email, create_user, update_user) bound to
    the real SDK, each adapted to this module's UnverifiedUser shape.

    Imported lazily (only when actually running, never at module import
    time) so this file stays importable -- and its safety logic
    unit-testable -- in an environment without firebase_admin installed."""
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
            "credentials for LexProof's three golden-path workflow identities "
            f"({', '.join(ALLOWED_UIDS)}) ONLY. Never touches demo-admin-1 or any "
            "other UID."
        )
    )
    parser.add_argument(
        "--uid",
        nargs="+",
        default=list(ALLOWED_UIDS),
        help=(
            f"One or more of {list(ALLOWED_UIDS)} (default: all three). Any other "
            "value aborts immediately before any Firebase call."
        ),
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
            result = provision_workflow_identity(
                uid,
                password,
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
            # Drop the only reference to this identity's password in this
            # process. Never printed, logged, or included in any message.
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
