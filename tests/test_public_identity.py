"""実際のアカウントを利用せず、公開用認証の取り違えを検証する。"""

import json
import subprocess
import unittest
from unittest.mock import patch

from tools.public_github import APPROVED_ID, APPROVED_LOGIN, verify_identity, login_public_account, verify_outgoing_commits
from tools.public_github import main


def result(stdout="", code=0):
    return subprocess.CompletedProcess([], code, stdout, "")


class PublicIdentityTests(unittest.TestCase):
    def test_missing_public_token_does_not_fall_back_to_active_account(self):
        with patch("tools.public_github.subprocess.run", return_value=result(code=1)) as run:
            with self.assertRaises(RuntimeError):
                verify_identity({})
        self.assertEqual(run.call_count, 1)
        self.assertIn(APPROVED_LOGIN, run.call_args.args[0])

    def test_wrong_account_is_rejected_before_any_write(self):
        env = {}
        with patch("tools.public_github.subprocess.run", side_effect=[result("test-token"), result('{"login":"unapproved","id":1}')]) as run:
            with self.assertRaises(RuntimeError):
                verify_identity(env)
        self.assertEqual(run.call_count, 2)

    def test_login_name_alone_cannot_override_the_approved_user_id(self):
        with patch("tools.public_github.subprocess.run", side_effect=[result("test-token"), result(json.dumps({"login": APPROVED_LOGIN, "id": 1}))]):
            with self.assertRaises(RuntimeError):
                verify_identity({})

    def test_approved_token_is_pinned_to_the_child_environment(self):
        env = {}
        with patch("tools.public_github.subprocess.run", side_effect=[result("test-token"), result(json.dumps({"login": APPROVED_LOGIN, "id": APPROVED_ID}))]):
            verify_identity(env)
        self.assertEqual(env["GH_TOKEN"], "test-token")

    def test_local_account_selection_is_restored_when_login_fails(self):
        with patch("tools.public_github.subprocess.run", side_effect=[result("previous-test-account"), result(code=1), result()]) as run:
            self.assertEqual(login_public_account({}), 1)
        self.assertEqual(run.call_args.args[0], ["gh", "auth", "switch", "--hostname", "github.com", "--user", "previous-test-account"])

    def test_commit_with_an_unapproved_committer_is_blocked(self):
        email = "223291788+tomonariworks@users.noreply.github.com"
        line = "TomonariWorks\0" + email + "\0unapproved\0test@example.invalid"
        with patch("tools.public_github.subprocess.run", return_value=result(line)):
            with self.assertRaises(RuntimeError):
                verify_outgoing_commits("release/test")

    def test_approved_commit_is_allowed(self):
        email = "223291788+tomonariworks@users.noreply.github.com"
        line = "\0".join(("TomonariWorks", email, "TomonariWorks", email))
        with patch("tools.public_github.subprocess.run", return_value=result(line)):
            verify_outgoing_commits("release/test")

    def test_secret_output_command_is_blocked(self):
        with patch("tools.public_github.sys.argv", ["public_github.py", "gh", "auth", "token"]), \
                patch("tools.public_github.public_environment", return_value={}), \
                patch("tools.public_github.verify_identity"), \
                patch("tools.public_github.subprocess.run") as run:
            with self.assertRaises(RuntimeError):
                main()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
