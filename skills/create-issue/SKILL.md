---
name: create-issue
description: >-
  Use when the user wants issues filed on Gitea or GitHub ("create an issue for this",
  "raise these in each repo", "let me see the draft first"): from items they list,
  findings or a design in the conversation, an analysis doc or a check-issue report;
  including one ask split across repos, a batch of findings, and rewriting or
  commenting on an issue that already exists.
---

# Create issue

Turn a request into issues a **cold reader** can act on: a teammate who sees only the issue, never this conversation, your local docs or your scratch notes. Route each item to its repo, find what already exists, ground it in the code, show drafts, and post through `tea` (Gitea) or `gh` (GitHub) once the user says go.

Requires Python 3.9+ and the sibling [check-issue](../check-issue/SKILL.md) skill. The bundled [post_issues.py](post_issues.py) imports its forge helper; install both complete directories under the same skills directory.

## Arguments

The arguments (`$ARGUMENTS`, or the user's message) are the source plus optional modifiers.

| In the request | Effect |
|---|---|
| bullet items or quoted text | one item each |
| nothing | the subject of the current conversation |
| a doc path, or an issue/PR link | the source; read all of it |
| "simple", "just to track" | tracking size |
| a repo constraint ("backend only", "admin") | route within it |
| "create now", "post directly" | new issues are posted right after the checks |
| "update #N", "comment on #N" | that existing issue is the target |

**The gate.** New issues are posted after the user approves the drafts, or straight after the checks on "create now". Every change to an existing issue (a comment, a new body or title) waits for an explicit yes, "create now" included. Assignees and labels are set only when the user asks, after posting: `tea issues edit N --add-assignees … --add-labels …` or `gh issue edit N --add-assignee … --add-label …`.

## 1. Read

- **Instructions:** the working directory's and each candidate repo's CLAUDE.md / AGENTS.md. They name which repo owns what, the forge CLI, the IDs to cite (requirements, test cases) and the domain terms, and they override this skill where they differ.
- **Source:** every listed item and named doc in full. For a linked issue, resolve [check-issue's helper](../check-issue/fetch_issue.py) from its installed directory and run `python3 <check-issue-directory>/fetch_issue.py <ref> <scratch>/issue-<n>`. View successfully fetched attachments; inspect `NOT FETCHED` images with an available authorized tool or report them as unread.

Done when you can restate each item's ask in one sentence. An item you can't restate goes back to the user as a question.

## 2. Route

- One issue per distinct ask per repo. The repo is where the change lands, per the instructions and the code.
- When a back end and a front end both change, file one issue in each and link them. Check how earlier issues in these repos split similar work, and follow that.
- From an analysis or test results, file only the items that need action.

Done when every item has a repo, or a stated reason it gets no issue.

## 3. Find what exists

Search each target repo, open and closed, by each item's key terms (`tea login list` names the login for the host):

```bash
tea issues list --login <login> --repo OWNER/REPO --state all --keyword <term>
gh issue list -R OWNER/REPO --state all --search <term>
```

Read every close match. When one already covers the item, the user chooses, with your recommendation: comment on it, update it, or file a new issue that references it.

Done when each item is marked new, comment on #N, or update #N.

## 4. Ground

- **Baseline:** the git repo under the working directory whose `origin` is OWNER/REPO. Resolve its actual default branch from `origin/HEAD` or read-only forge metadata. Run `git fetch` and read that remote-tracking branch; its short sha goes in "Checked against". Leave the checkout as it is (no checkout, pull or stash). With no local clone, say so and work from what the forge shows.
- **Bug:** the cause, with `path:line`. **Feature:** the existing code it extends, and what's missing.
- **Remote truth:** a spec, branch or PR that isn't pushed is described, not cited as existing. A rule no doc or code states goes under Open question, with who decides.

Done when every claim in the draft has a source on the remote or is marked as a question.

## 5. Draft

Write each draft to `<scratch>/issues-<slug>/NN-<key>.md` in posting order, an issue before the drafts that link to it (format in [Draft files](#draft-files)). Then show the user:

- a routing table: item · repo · action (new / comment #N / update #N) · title;
- each draft in full; past five drafts, the table, the folder path and the drafts that need a decision;
- the existing issues you found, and the open decisions.

Then wait at the gate. While the user questions the content, revise the drafts: the issue is the deliverable, and a spec or code waits for its own request.

### Size

| Size | Use for | Shape |
|---|---|---|
| Tracking | "simple", "just to track" | what and why in 1–2 sentences, 3–5 bullets of what's needed, a design link when pushed. Keeps what the implementer needs to start: the contract, the scope. |
| Standard | most bugs and small features (default) | header line, Problem, Fix, Checked against |
| Full | a feature after design discussion, a bug with several causes | Standard plus Proposed change in detail, Open question, Acceptance, out of scope |

### Title

- **Bug:** the symptom as a sentence: "Report download ignores the edited date range".
- **Feature:** "Area: what to add or change": "Item Master: add a "Download template" button for the CSV upload".
- **Severity** from testing: a prefix such as `[UAT Blocker]` or `[UAT Minor]`.
- Match the wording of the repo's recent issues.

### Body

```markdown
**Severity: <level>**: <what fails, or who will notice>.        (bugs from testing)
**Requirement:** <source: requirement or test IDs, client request> · Related: <refs>

Paths are relative to `<prefix>/`.                             (when most paths share a long prefix)

## Problem
- <current behavior, with `path:line`>
- <how to reproduce, who is affected>

## Fix                                                         (or: ## Proposed change)
- <what to change and where; the existing code to extend>

## Open question                                               (when a decision is pending)
**<question>** <the options>. <who decides>.

## Acceptance                                                  (full size)
- <observable checks, and the tests that prove it>

_Checked against `<sha>`._
```

- **Cold reader:** state what a local doc says; link only what the reader can open.
- **References:** `#N` in the same repo, `OWNER/REPO#N` in another repo, the full URL on another host, `{{key}}` for a draft not posted yet.
- Write in the language of the repo's existing issues, English by default.
- The issue reads as the user's own: no AI or agent attribution, no "drafted by".
- Leave out secrets, tokens and personal contact details.
- **Updating an issue:** read its current body just before writing. Keep what still holds, and end with `_Updated <date>: <what changed>._`

### Draft files

```markdown
---
key: be
repo: git.example.com/Owner/backend
title: Item master: endpoint to download the CSV template
---
Body. Links to another draft: {{admin}}.
```

- `key` (optional) lets other drafts write `{{be}}`.
- `repo` is `HOST/OWNER/REPO` or the repo URL.
- `title` is required to create; on an update it replaces the title.
- `comment: N` or `update: N` acts on existing issue N instead of creating one.

## 6. Post

Resolve [post_issues.py](post_issues.py) beside this installed `SKILL.md` and use its absolute path. Run the posting command only after the gate above is satisfied:

```bash
python3 <create-issue-directory>/post_issues.py <drafts-dir> --dry
python3 <create-issue-directory>/post_issues.py <drafts-dir>
```

- `--dry` picks `tea` or `gh` by host, prints the plan, and resolves every reference to the title it points at. Confirm each one is the issue you meant.
- Errors and warnings (unknown `{{key}}`, missing target, local paths, attribution lines, a hand-made `#PLACEHOLDER`) stop the post. Fix the draft. Pass `--force` only once the user has seen a warning and accepts it.
- Posting follows file order and fills in links to later drafts by an edit at the end. Progress is kept in `<drafts-dir>/.posted.json`, so after a failure, fix the draft and rerun. Every body is read back.
- Retries bind each posted filename to its host, repo, action and existing issue number. A changed target or an older progress entry without that identity stops before any forge call. Keep the progress file and reconcile its saved URLs with the drafts before retrying; deleting it can create duplicates.
- An `ERROR:` about a missing CLI or login: give the user the fix it names and stop. All access goes through the CLI's stored login (no tokens, no `curl`).

## 7. Report

```markdown
Posted to <host>:
- [OWNER/REPO#N](<url>): <title> (new | comment | updated)

Unset: assignees, labels.
Ahead of the remote: <anything an issue cites that isn't pushed yet>
Open decisions: <question · who decides>
```

Drop the last three lines when they're empty or set on request.

## Common mistakes

| Mistake | Instead |
|---|---|
| Pointing to a doc only you can open | State what it says in the issue |
| Filing a duplicate | Search open and closed first; offer comment, update or new |
| Posting before the drafts are seen | Wait at the gate unless "create now" |
| Writing a spec or code during drafting | Revise the draft |
| "Simple" that drops what the implementer needs | Keep the contract and scope, cut the rest |
| A bare `#N` for another repo's issue | `OWNER/REPO#N` |
| Citing work that isn't pushed as done | Check the remote; report what's ahead |
| Assigning or labelling unasked | Leave both unset and say so |
