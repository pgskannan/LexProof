"""Safety-guard tests for scripts/provision_demo_workflow_identities.py.

These are mocked, offline unit tests. None of them contact a real Firebase
project -- the script's real Firebase Admin entry point
(`_real_auth_functions`) is never called by any test below; every test
drives `provision_workflow_identity` (or `main()` with the real-auth
factory patched out) with fully mocked get_user/get_user_by_email/
create_user/update_user functions.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import provision_demo_workflow_identities as provisioning  # noqa: E402

ALLOWED_UIDS = provisioning.ALLOWED_UIDS
EMAIL_BY_UID = provisioning.EMAIL_BY_UID
SENTINEL_PASSWORD = "S3ntinel-Passw0rd-DoNotLog!"  # only ever used inside this test file


def make_auth_stub() -> Mock:
    """A Mock restricted to exactly the four functions this script may
    call -- calling anything else raises AttributeError immediately, so an
    accidental extra Firebase call fails the test rather than silently
    succeeding."""
    return Mock(spec=["get_user", "get_user_by_email", "create_user", "update_user"])


class AllowListTests(unittest.TestCase):
    def test_accepts_all_three_allowed_uids(self):
        for uid in ALLOWED_UIDS:
            provisioning.validate_allowed_uid(uid)  # must not raise

    def test_rejects_demo_admin_1(self):
        """demo-admin-1 belongs exclusively to the other script."""
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_allowed_uid("demo-admin-1")

    def test_rejects_arbitrary_uid(self):
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_allowed_uid("some-other-uid")

    def test_rejects_uid_that_merely_contains_an_allowed_uid_as_a_substring(self):
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_allowed_uid("demo-owner-1-extra")
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_allowed_uid("prefix-demo-owner-1")

    def test_exactly_three_allowed_uids(self):
        self.assertEqual(set(ALLOWED_UIDS), {"demo-owner-1", "demo-reviewer-1", "demo-approver-1"})


class DeterministicMappingTests(unittest.TestCase):
    def test_each_uid_maps_to_a_lexproof_local_email_matching_the_uid(self):
        for uid in ALLOWED_UIDS:
            self.assertEqual(EMAIL_BY_UID[uid], f"{uid}@lexproof.local")

    def test_no_personal_or_gmail_address_used(self):
        for email in EMAIL_BY_UID.values():
            self.assertNotIn("gmail.com", email)
            self.assertTrue(email.endswith("@lexproof.local"))


class ProvisionNewUserTests(unittest.TestCase):
    def test_creates_user_with_exact_custom_uid_when_absent(self):
        get_user = Mock(return_value=None)
        get_user_by_email = Mock(return_value=None)
        create_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-owner-1", email="demo-owner-1@lexproof.local", has_password_provider=True
            )
        )
        update_user = Mock()

        result = provisioning.provision_workflow_identity(
            "demo-owner-1",
            SENTINEL_PASSWORD,
            get_user_fn=get_user,
            get_user_by_email_fn=get_user_by_email,
            create_user_fn=create_user,
            update_user_fn=update_user,
        )

        self.assertEqual(result.action, "created")
        create_user.assert_called_once_with(
            uid="demo-owner-1", email="demo-owner-1@lexproof.local", password=SENTINEL_PASSWORD
        )
        update_user.assert_not_called()


class EmailConflictTests(unittest.TestCase):
    def test_stops_when_email_belongs_to_a_different_uid(self):
        get_user = Mock(return_value=None)
        get_user_by_email = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="some-other-accidental-uid", email="demo-owner-1@lexproof.local", has_password_provider=True
            )
        )
        create_user = Mock()
        update_user = Mock()

        with self.assertRaises(provisioning.EmailConflictError):
            provisioning.provision_workflow_identity(
                "demo-owner-1",
                SENTINEL_PASSWORD,
                get_user_fn=get_user,
                get_user_by_email_fn=get_user_by_email,
                create_user_fn=create_user,
                update_user_fn=update_user,
            )

        create_user.assert_not_called()
        update_user.assert_not_called()

    def test_get_user_by_email_matching_same_uid_is_not_a_conflict(self):
        # get_user_by_email finding the SAME uid (the normal case once a
        # user already exists) must not be treated as a conflict.
        get_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-reviewer-1", email="demo-reviewer-1@lexproof.local", has_password_provider=False
            )
        )
        get_user_by_email = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-reviewer-1", email="demo-reviewer-1@lexproof.local", has_password_provider=False
            )
        )
        create_user = Mock()
        update_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-reviewer-1", email="demo-reviewer-1@lexproof.local", has_password_provider=True
            )
        )

        result = provisioning.provision_workflow_identity(
            "demo-reviewer-1",
            SENTINEL_PASSWORD,
            get_user_fn=get_user,
            get_user_by_email_fn=get_user_by_email,
            create_user_fn=create_user,
            update_user_fn=update_user,
        )

        self.assertEqual(result.action, "credential_attached")
        create_user.assert_not_called()


class IdempotencyTests(unittest.TestCase):
    def test_already_provisioned_user_is_a_no_op(self):
        get_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-approver-1", email="demo-approver-1@lexproof.local", has_password_provider=True
            )
        )
        get_user_by_email = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-approver-1", email="demo-approver-1@lexproof.local", has_password_provider=True
            )
        )
        create_user = Mock()
        update_user = Mock()

        result = provisioning.provision_workflow_identity(
            "demo-approver-1",
            SENTINEL_PASSWORD,
            get_user_fn=get_user,
            get_user_by_email_fn=get_user_by_email,
            create_user_fn=create_user,
            update_user_fn=update_user,
        )

        self.assertEqual(result.action, "already_provisioned")
        create_user.assert_not_called()
        update_user.assert_not_called()  # existing password is never reset

    def test_existing_user_missing_credential_gets_credential_attached_not_recreated(self):
        get_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-owner-1", email="demo-owner-1@lexproof.local", has_password_provider=False
            )
        )
        get_user_by_email = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-owner-1", email="demo-owner-1@lexproof.local", has_password_provider=False
            )
        )
        create_user = Mock()
        update_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-owner-1", email="demo-owner-1@lexproof.local", has_password_provider=True
            )
        )

        result = provisioning.provision_workflow_identity(
            "demo-owner-1",
            SENTINEL_PASSWORD,
            get_user_fn=get_user,
            get_user_by_email_fn=get_user_by_email,
            create_user_fn=create_user,
            update_user_fn=update_user,
        )

        self.assertEqual(result.action, "credential_attached")
        create_user.assert_not_called()
        update_user.assert_called_once_with(
            "demo-owner-1", email="demo-owner-1@lexproof.local", password=SENTINEL_PASSWORD
        )

    def test_existing_user_with_mismatched_email_aborts_without_overwriting(self):
        get_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-owner-1", email="someone-else@lexproof.local", has_password_provider=False
            )
        )
        get_user_by_email = Mock(return_value=None)
        create_user = Mock()
        update_user = Mock()

        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.provision_workflow_identity(
                "demo-owner-1",
                SENTINEL_PASSWORD,
                get_user_fn=get_user,
                get_user_by_email_fn=get_user_by_email,
                create_user_fn=create_user,
                update_user_fn=update_user,
            )

        create_user.assert_not_called()
        update_user.assert_not_called()


class NoPasswordLeakageTests(unittest.TestCase):
    def _run_main_with_stubbed_auth(self, argv: list[str]) -> tuple[int, str, str]:
        stub_get_user = Mock(return_value=None)
        stub_get_user_by_email = Mock(return_value=None)
        stub_create_user = Mock(
            side_effect=lambda uid, email, password: provisioning.UnverifiedUser(
                uid=uid, email=email, has_password_provider=True
            )
        )
        stub_update_user = Mock()

        original_real_auth_functions = provisioning._real_auth_functions
        original_prompt = provisioning._prompt_for_password
        provisioning._real_auth_functions = lambda: (
            stub_get_user, stub_get_user_by_email, stub_create_user, stub_update_user,
        )
        provisioning._prompt_for_password = lambda uid: SENTINEL_PASSWORD
        try:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                exit_code = provisioning.main(argv)
            return exit_code, out.getvalue(), err.getvalue()
        finally:
            provisioning._real_auth_functions = original_real_auth_functions
            provisioning._prompt_for_password = original_prompt

    def test_password_never_appears_in_stdout_or_stderr_on_success(self):
        exit_code, out, err = self._run_main_with_stubbed_auth(["--uid", "demo-owner-1"])
        self.assertEqual(exit_code, 0)
        self.assertNotIn(SENTINEL_PASSWORD, out)
        self.assertNotIn(SENTINEL_PASSWORD, err)
        self.assertIn("created", out.lower())

    def test_password_never_appears_in_stdout_or_stderr_on_rejected_uid(self):
        exit_code, out, err = self._run_main_with_stubbed_auth(["--uid", "demo-admin-1"])
        self.assertEqual(exit_code, 2)
        self.assertNotIn(SENTINEL_PASSWORD, out)
        self.assertNotIn(SENTINEL_PASSWORD, err)

    def test_password_never_appears_in_exception_messages(self):
        get_user = Mock(
            return_value=provisioning.UnverifiedUser(
                uid="demo-owner-1", email="mismatch@lexproof.local", has_password_provider=False
            )
        )
        get_user_by_email = Mock(return_value=None)
        try:
            provisioning.provision_workflow_identity(
                "demo-owner-1",
                SENTINEL_PASSWORD,
                get_user_fn=get_user,
                get_user_by_email_fn=get_user_by_email,
                create_user_fn=Mock(),
                update_user_fn=Mock(),
            )
        except provisioning.ProvisioningError as exc:
            self.assertNotIn(SENTINEL_PASSWORD, str(exc))
        else:
            self.fail("expected ProvisioningError")


if __name__ == "__main__":
    unittest.main()
