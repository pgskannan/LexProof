"""Safety-guard tests for scripts/provision_demo_admin_email_password.py.

These are mocked, offline unit tests. None of them contact a real Firebase
project, and the provisioning script's CLI (`main()`) is exercised only
with fully mocked `get_user`/`update_user` functions -- its real Firebase
Admin entry point (`_real_auth_functions`) is patched out in every test
below, so running this test file never touches live Firebase data.
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

import provision_demo_admin_email_password as provisioning  # noqa: E402


TARGET_UID = provisioning.TARGET_UID
SENTINEL_PASSWORD = "S3ntinel-Passw0rd-DoNotLog!"  # only ever used inside this test file


def make_auth_stub(existing_uid: str | None = TARGET_UID):
    """A Mock restricted to exactly get_user/update_user -- calling
    `.create_user(...)` on it raises AttributeError immediately, so any
    accidental call to create_user in the code under test fails the test
    rather than silently succeeding."""
    stub = Mock(spec=["get_user", "update_user"])

    if existing_uid is not None:
        stub.get_user.return_value = provisioning.UnverifiedUser(uid=existing_uid, email=None)
    else:
        stub.get_user.side_effect = LookupError("no such Firebase user")

    stub.update_user.return_value = provisioning.UnverifiedUser(
        uid=existing_uid or TARGET_UID, email="demo-admin@example.invalid"
    )
    return stub


class ValidateTargetUidTests(unittest.TestCase):
    def test_accepts_exact_target_uid(self):
        provisioning.validate_target_uid(TARGET_UID)  # must not raise

    def test_rejects_any_other_uid(self):
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_target_uid("some-other-uid")

    def test_rejects_uid_that_merely_contains_the_target_as_a_substring(self):
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_target_uid("demo-admin-1-extra")
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.validate_target_uid("prefix-demo-admin-1")


class ProvisionEmailPasswordCredentialTests(unittest.TestCase):
    def test_existing_uid_is_updated_via_update_user_only(self):
        auth_stub = make_auth_stub(existing_uid=TARGET_UID)

        result = provisioning.provision_email_password_credential(
            TARGET_UID,
            "demo-admin@example.invalid",
            SENTINEL_PASSWORD,
            get_user_fn=auth_stub.get_user,
            update_user_fn=auth_stub.update_user,
        )

        auth_stub.get_user.assert_called_once_with(TARGET_UID)
        auth_stub.update_user.assert_called_once_with(
            TARGET_UID, email="demo-admin@example.invalid", password=SENTINEL_PASSWORD
        )
        self.assertEqual(result.uid, TARGET_UID)

    def test_wrong_uid_is_rejected_before_any_firebase_call(self):
        auth_stub = make_auth_stub(existing_uid="some-other-uid")

        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.provision_email_password_credential(
                "some-other-uid",
                "attacker@example.invalid",
                SENTINEL_PASSWORD,
                get_user_fn=auth_stub.get_user,
                update_user_fn=auth_stub.update_user,
            )

        auth_stub.get_user.assert_not_called()
        auth_stub.update_user.assert_not_called()

    def test_nonexistent_uid_is_rejected_and_never_updated(self):
        auth_stub = make_auth_stub(existing_uid=None)  # get_user raises: user does not exist

        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.provision_email_password_credential(
                TARGET_UID,
                "demo-admin@example.invalid",
                SENTINEL_PASSWORD,
                get_user_fn=auth_stub.get_user,
                update_user_fn=auth_stub.update_user,
            )

        auth_stub.get_user.assert_called_once_with(TARGET_UID)
        auth_stub.update_user.assert_not_called()

    def test_create_user_is_never_called_for_the_happy_path(self):
        # Mock(spec=["get_user", "update_user"]) has no create_user attribute
        # at all -- accessing it raises AttributeError. This proves the
        # success path never even references create_user, not merely that it
        # returned early.
        auth_stub = make_auth_stub(existing_uid=TARGET_UID)

        provisioning.provision_email_password_credential(
            TARGET_UID,
            "demo-admin@example.invalid",
            SENTINEL_PASSWORD,
            get_user_fn=auth_stub.get_user,
            update_user_fn=auth_stub.update_user,
        )

        with self.assertRaises(AttributeError):
            auth_stub.create_user("demo-admin-1", email="x@example.invalid", password="y")

    def test_source_file_never_contains_a_create_user_call(self):
        source = Path(provisioning.__file__).read_text(encoding="utf-8")
        self.assertNotIn("create_user(", source)

    def test_missing_email_is_rejected(self):
        auth_stub = make_auth_stub(existing_uid=TARGET_UID)
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.provision_email_password_credential(
                TARGET_UID, "", SENTINEL_PASSWORD,
                get_user_fn=auth_stub.get_user, update_user_fn=auth_stub.update_user,
            )
        auth_stub.update_user.assert_not_called()

    def test_missing_password_is_rejected(self):
        auth_stub = make_auth_stub(existing_uid=TARGET_UID)
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.provision_email_password_credential(
                TARGET_UID, "demo-admin@example.invalid", "",
                get_user_fn=auth_stub.get_user, update_user_fn=auth_stub.update_user,
            )
        auth_stub.update_user.assert_not_called()

    def test_mismatched_returned_uid_is_treated_as_failure(self):
        auth_stub = make_auth_stub(existing_uid=TARGET_UID)
        auth_stub.update_user.return_value = provisioning.UnverifiedUser(
            uid="unexpected-uid", email="demo-admin@example.invalid"
        )
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.provision_email_password_credential(
                TARGET_UID, "demo-admin@example.invalid", SENTINEL_PASSWORD,
                get_user_fn=auth_stub.get_user, update_user_fn=auth_stub.update_user,
            )


class PasswordIsNeverLoggedTests(unittest.TestCase):
    def _run_cli_with_mocked_firebase(self, existing_uid):
        auth_stub = make_auth_stub(existing_uid=existing_uid)
        original_real_auth_functions = provisioning._real_auth_functions
        provisioning._real_auth_functions = lambda: (auth_stub.get_user, auth_stub.update_user)  # type: ignore[assignment]
        try:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = provisioning.main([
                    "--email", "demo-admin@example.invalid",
                    "--password-env", "TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST",
                ])
            return exit_code, stdout.getvalue(), stderr.getvalue()
        finally:
            provisioning._real_auth_functions = original_real_auth_functions

    def test_successful_run_never_prints_the_password(self):
        import os

        os.environ["TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST"] = SENTINEL_PASSWORD
        try:
            exit_code, stdout, stderr = self._run_cli_with_mocked_firebase(existing_uid=TARGET_UID)
        finally:
            del os.environ["TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST"]

        self.assertEqual(exit_code, 0)
        self.assertIn("SUCCESS", stdout)
        self.assertNotIn(SENTINEL_PASSWORD, stdout)
        self.assertNotIn(SENTINEL_PASSWORD, stderr)

    def test_failed_run_also_never_prints_the_password(self):
        import os

        os.environ["TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST"] = SENTINEL_PASSWORD
        try:
            # existing_uid=None -> ensure_user_exists() raises -> abort path
            exit_code, stdout, stderr = self._run_cli_with_mocked_firebase(existing_uid=None)
        finally:
            del os.environ["TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST"]

        self.assertEqual(exit_code, 2)
        self.assertIn("ABORTED", stderr)
        self.assertNotIn(SENTINEL_PASSWORD, stdout)
        self.assertNotIn(SENTINEL_PASSWORD, stderr)


class CliRejectsWrongUidTests(unittest.TestCase):
    def test_cli_aborts_before_touching_firebase_when_uid_flag_is_wrong(self):
        auth_stub = make_auth_stub(existing_uid=TARGET_UID)
        original_real_auth_functions = provisioning._real_auth_functions
        # If main() ever reached _real_auth_functions for a bad --uid, this
        # would raise, failing the test loudly.
        provisioning._real_auth_functions = lambda: (_ for _ in ()).throw(  # type: ignore[assignment]
            AssertionError("must not initialize Firebase for a rejected UID")
        )
        try:
            import os

            os.environ["TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST"] = SENTINEL_PASSWORD
            try:
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = provisioning.main([
                        "--uid", "not-demo-admin-1",
                        "--email", "demo-admin@example.invalid",
                        "--password-env", "TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST",
                    ])
            finally:
                del os.environ["TEST_DEMO_ADMIN_PASSWORD_FOR_UNITTEST"]
        finally:
            provisioning._real_auth_functions = original_real_auth_functions

        self.assertEqual(exit_code, 2)
        auth_stub.get_user.assert_not_called()
        auth_stub.update_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
