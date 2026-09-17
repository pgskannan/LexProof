"""One-time, narrowly-scoped utility: attach an Email/Password credential to
the EXISTING Firebase Authentication user `demo-admin-1`.

Why this exists
----------------
LexProof's Demo Admin already exists as a Firebase Authentication user with
UID `demo-admin-1` (visible in the Firebase Console, but with a blank
Identifier column -- i.e. no email/password credential is attached yet) and
as a corresponding LexProof application user / organization member in
Firestore. This script attaches an Email/Password sign-in credential to
that EXISTING Firebase user so it can authenticate through LexProof's
Email/Password login for human ground-truth review testing.

What this script will NEVER do
-------------------------------
  - It never calls firebase_admin.auth.create_user. There is no code path
    in this file that creates a Firebase user, under any condition.
  - It never targets any UID other than the single hardcoded constant
    TARGET_UID below. A --uid flag exists only as an explicit safety
    check: if it is not exactly TARGET_UID, the script aborts before
    touching Firebase at all.
  - It never deletes, disables, or reads/writes Firestore application
    data (LexProof users, organizations, memberships, or roles). Those
    are untouched by this script.
  - It never prints the password, an ID/access token, or service-account
    contents.

How it authenticates to Firebase
---------------------------------
This script reuses the project's existing Firebase Admin initialization
(`app.lexproof.services.firebase.initialize_firebase`), the exact same
mechanism the backend server itself uses: GOOGLE_APPLICATION_CREDENTIALS,
then a local `firebase-service-account.json`, then Application Default
Credentials. It does not accept or read a credential path/value of its
own.

How to run it (a human runs this deliberately; it is never imported or
invoked by the application, by tests, or by CI):

    cd backend
    python scripts/provision_demo_admin_email_password.py --email <ADMIN_EMAIL>

You will be prompted for the password via a hidden (getpass) prompt so it
is never typed into a place your shell records it. See the module-level
--password-env option below for the non-interactive alternative.

This script is intentionally NOT executed as part of writing it. Running
it is a deliberate, separate human action.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Callable, NamedTuple

# The one and only UID this script is allowed to touch. Not a CLI default
# meant to be overridden in normal use -- see validate_target_uid().
TARGET_UID = "demo-admin-1"


class UnverifiedUser(NamedTuple):
    """The minimal shape this module needs from a Firebase UserRecord.

    Using a small local type (rather than importing firebase_admin's
    UserRecord at module scope) keeps this module importable -- and its
    safety logic unit-testable -- without the firebase_admin package
    installed.
    """

    uid: str
    email: str | None


class ProvisioningError(RuntimeError):
    """Raised whenever a safety guard rejects the requested operation."""


def validate_target_uid(uid: str) -> None:
    """Abort unless `uid` is exactly the one UID this script may touch."""
    if uid != TARGET_UID:
        raise ProvisioningError(
            f"Refusing to operate on UID {uid!r}; this script only ever "
            f"targets the existing UID {TARGET_UID!r}."
        )


def ensure_user_exists(
    uid: str,
    get_user_fn: Callable[[str], UnverifiedUser],
) -> UnverifiedUser:
    """Fetch the existing Firebase user. Never creates one.

    `get_user_fn` is expected to behave like `firebase_admin.auth.get_user`:
    it raises when the UID does not exist (in production, a
    `firebase_admin.auth.UserNotFoundError`). Any such failure is
    re-raised here as ProvisioningError with a safe, explicit message --
    the script aborts, it does not fall back to creating the user.
    """
    try:
        return get_user_fn(uid)
    except Exception as exc:  # noqa: BLE001 - intentionally broad: any lookup
        # failure means "do not proceed", regardless of the exact SDK
        # exception type raised.
        raise ProvisioningError(
            f"Firebase user {uid!r} does not exist (or could not be fetched). "
            "This script only updates an existing user and will not create "
            "one. Aborting."
        ) from exc


def provision_email_password_credential(
    uid: str,
    email: str,
    password: str,
    *,
    get_user_fn: Callable[[str], UnverifiedUser],
    update_user_fn: Callable[..., UnverifiedUser],
) -> UnverifiedUser:
    """Attach an Email/Password credential to the existing `uid`.

    Safety guarantees enforced in this function, in order:
      1. `uid` must be exactly TARGET_UID (validate_target_uid).
      2. `email` and `password` must both be explicitly supplied.
      3. The user must already exist (ensure_user_exists) -- create_user
         is never called anywhere in this module.
      4. `update_user_fn` (i.e. firebase_admin.auth.update_user in
         production) is called to set ONLY email/password on the existing
         record -- no other fields (roles, tenant, disabled, etc.) are
         touched.
      5. The UID on the record returned by the update call is verified to
         still be exactly TARGET_UID before declaring success.
    """
    validate_target_uid(uid)
    if not email or not email.strip():
        raise ProvisioningError("An email value is required and was not supplied.")
    if not password:
        raise ProvisioningError("A password value is required and was not supplied.")

    ensure_user_exists(uid, get_user_fn)

    updated = update_user_fn(uid, email=email, password=password)

    if updated.uid != TARGET_UID:
        # Defense in depth. The Admin SDK should never return a different
        # UID from the one it was called with, but if it ever did, that is
        # exactly the class of mistake this script exists to prevent.
        raise ProvisioningError(
            f"Firebase returned UID {updated.uid!r} after update, expected "
            f"{TARGET_UID!r}. Treating this as a failure; no further action taken."
        )
    return updated


def _prompt_for_password() -> str:
    """Read the password via getpass (not echoed, not a CLI argument, so it
    never lands in shell history or a process listing)."""
    password = getpass.getpass("Password for demo-admin-1 (input hidden): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise ProvisioningError("Passwords did not match.")
    return password


def _real_auth_functions() -> tuple[Callable[[str], UnverifiedUser], Callable[..., UnverifiedUser]]:
    """Initialize Firebase Admin using the project's EXISTING mechanism and
    return (get_user, update_user) bound to the real SDK.

    Imported lazily (only when actually running, never at module import
    time) so this file stays importable -- and its safety logic
    unit-testable -- in an environment without firebase_admin installed.
    Note this function never references `create_user`.
    """
    backend_root = Path(__file__).resolve().parent.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.lexproof.services.firebase import initialize_firebase
    from firebase_admin import auth

    initialize_firebase()
    return auth.get_user, auth.update_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-time utility: attach an Email/Password credential to the "
            "EXISTING Firebase user demo-admin-1. Does not create, delete, "
            "disable, or otherwise modify any user, role, or tenant."
        )
    )
    parser.add_argument(
        "--uid",
        default=TARGET_UID,
        help=(
            f"Must be exactly {TARGET_UID!r}. This flag exists as an explicit, "
            "visible safety check -- not as a way to target a different user. "
            "Any other value aborts immediately."
        ),
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email address to set on the existing demo-admin-1 Firebase user.",
    )
    parser.add_argument(
        "--password-env",
        default="DEMO_ADMIN_PROVISION_PASSWORD",
        help=(
            "Name of an environment variable to read the password from, if it is "
            "set. If unset, you are prompted interactively via getpass (input "
            "hidden, recommended -- this keeps the password out of shell "
            "history). The password is never accepted as a plain CLI argument."
        ),
    )
    args = parser.parse_args(argv)

    try:
        validate_target_uid(args.uid)
    except ProvisioningError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 2

    password = os.environ.get(args.password_env) or _prompt_for_password()

    try:
        get_user_fn, update_user_fn = _real_auth_functions()

        updated = provision_email_password_credential(
            args.uid,
            args.email,
            password,
            get_user_fn=get_user_fn,
            update_user_fn=update_user_fn,
        )
    except ProvisioningError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 2
    finally:
        # Drop the only reference to the password in this process. It is
        # never printed, logged, or included in any exception message above.
        password = None  # noqa: F841

    print(f"SUCCESS: Email/Password credential set for existing Firebase UID {updated.uid}.")
    print("No user was created. No other user, role, or tenant was modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
