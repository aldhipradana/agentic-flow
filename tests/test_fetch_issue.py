import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/check-issue/fetch_issue.py"
spec = importlib.util.spec_from_file_location("fetch_issue", SCRIPT)
fetch_issue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_issue)


class FetchIssueTests(unittest.TestCase):
    def test_web_remote_preserves_service_port(self):
        with patch.object(fetch_issue, "run", return_value=(0, "https://git.example.test:3000/team/app.git\n", "")):
            self.assertEqual(fetch_issue.origin(), ("git.example.test:3000", "team/app"))

    def test_common_remotes(self):
        for remote in [
            "git@github.com:team/app.git",
            "https://github.com/team/app.git",
            "ssh://git@github.com:22/team/app.git",
        ]:
            with self.subTest(remote=remote), patch.object(fetch_issue, "run", return_value=(0, remote, "")):
                self.assertEqual(fetch_issue.origin(), ("github.com", "team/app"))

    def test_issue_and_pull_request_urls_preserve_anchor(self):
        for kind in ["issues", "pulls", "pull"]:
            with self.subTest(kind=kind):
                self.assertEqual(
                    fetch_issue.parse_ref(f"https://git.example.test/team/app/{kind}/42#issuecomment-7"),
                    ("git.example.test", "team", "app", 42, "issuecomment-7"),
                )

    def test_short_reference_uses_origin(self):
        with patch.object(fetch_issue, "origin", return_value=("git.example.test:3000", "team/app")):
            self.assertEqual(fetch_issue.parse_ref("#42"), ("git.example.test:3000", "team", "app", 42, ""))
            self.assertEqual(fetch_issue.parse_ref("other/service#3"), ("git.example.test:3000", "other", "service", 3, ""))

    def test_github_comment_pages_are_combined(self):
        with patch.object(fetch_issue, "run", return_value=(0, '[[{"id": 1}], [{"id": 2}]]', "")) as run:
            self.assertEqual(fetch_issue.gh_get("github.com", "repos/team/app/issues/42/comments"), [{"id": 1}, {"id": 2}])
            self.assertIn("--paginate", run.call_args.args[0])

    def test_api_errors_stop_instead_of_becoming_issue_data(self):
        with patch.object(fetch_issue, "run", return_value=(0, '{"message": "Not Found"}', "")), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                fetch_issue.tea_get("work", "/repos/team/app/issues/42")

    def test_download_does_not_send_gitea_auth_to_another_host(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch_issue, "run") as run:
            self.assertFalse(fetch_issue.download("tea", "work", "git.example.test", "https://other.example.test/image.png", Path(directory) / "image.png"))
            run.assert_not_called()

    def test_digest_records_raw_evidence_and_unread_images(self):
        issue = {
            "title": "Settings fail to save", "state": "open", "user": {"login": "colleague"},
            "created_at": "2026-01-01T00:00:00Z", "html_url": "https://github.com/team/app/issues/42",
            "body": "![Screenshot](https://example.test/image.png)",
        }
        comments = [{"id": 7, "user": {"login": "colleague"}, "created_at": "2026-01-02T00:00:00Z", "body": "See #99"}]
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch.object(fetch_issue, "fetch", return_value=("gh", None, issue, comments)), patch.object(
                fetch_issue.sys, "argv", [str(SCRIPT), issue["html_url"] + "#issuecomment-7", directory]
            ), contextlib.redirect_stdout(output):
                fetch_issue.main()
            self.assertEqual(json.loads((Path(directory) / "issue.json").read_text()), issue)
            self.assertEqual(json.loads((Path(directory) / "comments.json").read_text()), comments)
            self.assertIn("NOT FETCHED: https://example.test/image.png", output.getvalue())
            self.assertIn("linked comment", output.getvalue())
            self.assertIn("#99", output.getvalue())


if __name__ == "__main__":
    unittest.main()
