import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import post_issues


class MemoryForge:
    def __init__(self):
        self.calls = []
        self.items = {}
        self.next_number = 100

    def label(self, host):
        self.calls.append(("label", host))
        return "test forge"

    def issue(self, host, slug, number):
        self.calls.append(("issue", host, slug, number))
        return '"Existing issue" (open)'

    def api(self, host, method, endpoint, payload=None):
        self.calls.append((method, host, endpoint, payload))
        if method == "POST":
            self.next_number += 1
            number = self.next_number
            if endpoint.endswith("/comments"):
                issue_path = endpoint.removesuffix("/comments")
                url = f"https://{host}{issue_path.removeprefix('/repos')}#issuecomment-{number}"
                endpoint = f"{issue_path.rsplit('/', 1)[0]}/comments/{number}"
            else:
                endpoint = f"{endpoint}/{number}"
                url = f"https://{host}{endpoint.removeprefix('/repos')}"
            data = {"id": number, "number": number,
                    "html_url": url, "body": payload["body"],
                    "title": payload.get("title", ""), "state": "open"}
            self.items[(host, endpoint)] = data
        elif method == "PATCH":
            self.items[(host, endpoint)].update(payload)
        return True, self.items[(host, endpoint)].copy()


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="create-issue-test-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.state_path = self.folder / ".posted.json"
        self.forge = MemoryForge()
        self.output = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        self.addCleanup(self.output.close)
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def draft(self, repo="github.com/acme/repo-a", action="create", number=None,
              body="Original body", filename="01-task.md", key=None):
        fields = [f"repo: {repo}"]
        if action != "comment":
            fields.append("title: Tracking task")
        if action != "create":
            fields.append(f"{action}: {number}")
        if key:
            fields.append(f"key: {key}")
        file = self.folder / filename
        file.write_text("---\n" + "\n".join(fields) + f"\n---\n{body}\n")
        return post_issues.Draft(file)

    def posted(self):
        draft = self.draft()
        post_issues.post([draft], self.forge, {}, self.state_path)
        self.forge.calls.clear()
        return draft, post_issues.load_state(self.state_path)

    def test_changed_repo_stops_before_wrong_issue_is_patched(self):
        _, state = self.posted()
        draft = self.draft(repo="github.com/acme/repo-b", body="Different task")
        endpoint = "/repos/acme/repo-b/issues/101"
        self.forge.items[("github.com", endpoint)] = {"body": "Original body\n"}
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            post_issues.post([draft], self.forge, state, self.state_path)
        self.assertEqual(self.forge.items[("github.com", endpoint)]["body"], "Original body\n")
        self.assertEqual(self.forge.calls, [])

    def test_target_changes_fail_preflight_without_forge_access(self):
        cases = [
            {"repo": "other.example/acme/repo-a"},
            {"repo": "github.com/another/repo-a"},
            {"repo": "github.com/acme/repo-b"},
            {"action": "comment", "number": 101},
            {"action": "update", "number": 101},
        ]
        _, state = self.posted()
        for changed in cases:
            with self.subTest(changed=changed):
                draft = self.draft(**changed)
                self.forge.calls.clear()
                errors, _ = post_issues.check([draft], self.forge, state)
                self.assertTrue(errors)
                self.assertEqual(self.forge.calls, [])

    def test_existing_issue_number_change_fails_preflight(self):
        draft, state = self.posted()
        entry = state[draft.file]
        entry["action"] = "update"
        entry["identity"] = {"host": "github.com", "repo": "acme/repo-a",
                             "action": "update", "number": 101}
        changed = self.draft(action="update", number=102)
        errors, _ = post_issues.check([changed], self.forge, state)
        self.assertTrue(errors)
        self.assertEqual(self.forge.calls, [])

    def test_legacy_progress_is_preserved_and_rejected(self):
        draft, state = self.posted()
        state[draft.file].pop("identity", None)
        self.state_path.write_text(json.dumps(state))
        before = self.state_path.read_bytes()
        errors, _ = post_issues.check([draft], self.forge, state)
        self.assertTrue(errors)
        self.assertEqual(self.forge.calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_unchanged_retry_does_not_create_duplicate(self):
        draft, state = self.posted()
        post_issues.post([draft], self.forge, state, self.state_path)
        self.assertEqual(len(self.forge.items), 1)
        self.assertFalse(any(call[0] in {"POST", "PATCH"} for call in self.forge.calls))

    def test_existing_actions_resume_without_duplicate_writes(self):
        for action in ("comment", "update"):
            with self.subTest(action=action):
                draft = self.draft(action=action, number=7)
                forge = MemoryForge()
                endpoint = "/repos/acme/repo-a/issues/7"
                forge.items[("github.com", endpoint)] = {
                    "id": 7, "number": 7, "html_url": "https://github.com/acme/repo-a/issues/7",
                    "title": "Before", "body": "Before\n", "state": "open"}
                post_issues.post([draft], forge, {}, self.state_path)
                state = post_issues.load_state(self.state_path)
                count = len(forge.items)
                forge.calls.clear()
                post_issues.post([draft], forge, state, self.state_path)
                self.assertEqual(len(forge.items), count)
                self.assertFalse(any(call[0] in {"POST", "PATCH"} for call in forge.calls))

    def test_body_correction_keeps_same_issue_on_retry(self):
        _, state = self.posted()
        draft = self.draft(body="Corrected body")
        post_issues.post([draft], self.forge, state, self.state_path)
        self.assertEqual(len(self.forge.items), 1)
        self.assertEqual(self.forge.items[("github.com", "/repos/acme/repo-a/issues/101")]["body"],
                         "Corrected body\n")

    def test_mutual_links_still_resolve(self):
        drafts = [self.draft(body="Related: {{b}}", key="a"),
                  self.draft(repo="github.com/acme/repo-b", body="Related: {{a}}",
                             filename="02-task.md", key="b")]
        post_issues.post(drafts, self.forge, {}, self.state_path)
        self.assertEqual(self.forge.items[("github.com", "/repos/acme/repo-a/issues/101")]["body"],
                         "Related: acme/repo-b#102\n")
        self.assertEqual(self.forge.items[("github.com", "/repos/acme/repo-b/issues/102")]["body"],
                         "Related: acme/repo-a#101\n")

    def test_mismatch_blocks_whole_batch_before_new_issue(self):
        _, state = self.posted()
        drafts = [self.draft(filename="00-new.md"), self.draft(repo="github.com/acme/repo-b")]
        self.forge.items[("github.com", "/repos/acme/repo-b/issues/101")] = {"body": "Original body\n"}
        before = self.state_path.read_bytes()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            post_issues.post(drafts, self.forge, state, self.state_path)
        self.assertEqual(self.forge.calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_dry_run_rejects_mismatch(self):
        self.posted()
        self.draft(repo="github.com/acme/repo-b")
        with patch("sys.argv", ["post_issues.py", str(self.folder), "--dry"]), \
                patch.object(post_issues, "Forges", return_value=self.forge):
            with self.assertRaises(SystemExit):
                post_issues.main()
        self.assertEqual(self.forge.calls, [])


if __name__ == "__main__":
    unittest.main()
