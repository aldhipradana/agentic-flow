---
name: check-issue
description: Use when the user pastes a Gitea or GitHub issue link, or an owner/repo#N reference, and wants it checked, analyzed, triaged or worked on, including title-only issues, issues whose details are only in screenshots, and several links at once.
---

# Check issue

Turn a pasted issue link into an analysis grounded in the issue's full content (screenshots included) and the current code, reported in a fixed shape. **Default is analysis only**; words after the link can widen it.

## Arguments

The arguments (`$ARGUMENTS`, or the user's message where nothing is substituted) are one or more issue references followed by optional free text.

- `https://<host>/<owner>/<repo>/issues/<n>`: a `#issuecomment-<id>` anchor marks the comment the user is pointing at.
- `owner/repo#n`, or `#n` resolved from the current repo's `origin`. If the working directory isn't a single repo, ask which repo; don't probe every repo for that number.

| Free text after the links | Scope |
|---|---|
| none, "check", "analyze", "look into" | Analysis only: code, tests and docs stay untouched. Memory notes your instructions ask for are fine; CLAUDE.md updates go under **Next** as proposals. |
| a question ("how come this is a bug?") | Analysis; the verdict answers that question first |
| a constraint ("backend only") | Honor it in the analysis and proposed fix |
| "fix", "work on it", "implement" | Analysis, then implement under the repo's own rules |
| "commit", "push", "open a PR" | Exactly those git/forge actions, nothing more |

Commenting on, labelling, assigning, closing or editing the issue happens only when the free text asks for it.

## 1. Read everything on the issue

Resolve the bundled [fetch_issue.py](fetch_issue.py) beside this `SKILL.md`, then run it once per reference. Use its absolute path so it works with personal, project, or plugin installations. Run from the repo directory when the reference is short:

```bash
python3 <skill-directory>/fetch_issue.py <ref> <scratch>/issue-<n>
```

`<scratch>` is the session scratchpad, or a temp directory outside the repo when there is none. The script uses `gh` for `github.com` and `*.ghe.com`, and otherwise requires a matching `tea` login for a Gitea host. It saves raw issue/comment JSON, downloads same-host Gitea attachments through `tea`, and prints a digest with referenced issue numbers. GitHub and external-host images are listed as `NOT FETCHED`; it does not download them. For other GitHub Enterprise hosts, use an already available authenticated `gh` or read-only connector for that host and report the helper's coverage limit.

- **View every successfully fetched attachment.** On terse issues the screenshot is the whole report.
- For `NOT FETCHED:` images, use an available authorized image tool or ask the user to attach them. Keep any images you could not inspect in the report as unread; mark a verdict provisional when they could change it.
- `ERROR:` about a missing CLI or login: stop and give the user the fix it names.
- Nothing reads tokens or CLI config files, or sends credentials with `curl`. What the script can't fetch is reported as unread.
- Referenced issues and PRs ("Done in #81", "see #88"): fetch them too when they could change the verdict.
- Search the repo's open issues for the subject's key term to catch duplicates and overlapping asks. Inspect the installed CLI's `--help` for supported syntax; select the matching host/login and repository explicitly.
- Title-only issue: work from title, comments, images and code, and state your reading of it as an assumption.

## 2. Ground it in the code

- **Checkout:** the git repo under the working directory (search a few levels down) whose `origin` is OWNER/REPO. Don't clone; if none is found, say so and ask for the path.
- **Instructions:** read applicable `AGENTS.md` and `CLAUDE.md` files before analyzing. Follow `CLAUDE.md` when its scope has no `AGENTS.md`; when both exist, keep applicable guidance from both, with `AGENTS.md` taking precedence over conflicts.
- **Baseline:** note the branch, uncommitted changes and ahead/behind against existing local refs. Resolve the actual default branch from `origin/HEAD` or read-only forge metadata instead of assuming `main`. Analyze its available remote-tracking ref; if that ref is absent, analyze the available checkout and state the limitation. Compare its SHA with read-only forge metadata when available. State exactly which revision you read and whether freshness is verified. Analysis does not fetch, checkout, pull or stash.
- **Reach:** check the sibling checkouts the issue touches (a front-end bug filed on the backend repo, an API both UIs call).
- **Bug:** root cause with `file:line` evidence before any fix; if reading the code path doesn't reveal it, use an available debugging skill or continue targeted investigation and report uncertainty. **Feature:** find existing code with the same intent and propose extending it. **Closed or possibly fixed:** verify against the actual default branch and linked PRs; qualify the conclusion when that revision is unavailable or stale.

## 3. Report

One block per issue, in this shape:

```markdown
## OWNER/REPO#N: <title>
<state> · @<author>, <date> · <link> · checked against <repo> <branch>@<short sha>[, <repo> <branch>@<short sha> for each other repo read]

**Verdict:** <1–3 sentences: what is going on, whether it still holds on current code, and the answer to the user's question if they asked one>

**What the issue asks:** <plain restatement, including what the screenshots show; assumptions marked>

**Cause / current behavior:** <evidence, with file:line links>

**Proposed fix:** <recommendation, repos and files touched, tests that would prove it>

**Open decisions:** <question · who decides (you / client / teammate) · your recommendation>

**Next:** <what happens on the user's go, e.g. "Say `fix` and I'll implement it in <repo>, uncommitted.">
```

- Omit **Open decisions** when there are none. When one belongs to someone else, offer a short chat message (not an email) addressed to that decision owner, by name if the issue gives one.
- Define a domain term in plain words the first time the argument depends on it.
- Several issues: one block each, then one line on how they relate (shared root cause, one change, or independent).

## Common mistakes

| Mistake | Instead |
|---|---|
| Analyzing from the title when the body is a screenshot | Download and view every attachment first |
| Working around a fetch error with tokens or `curl` | Relay the script's fix command and stop |
| Running `tea issues <n>` in every repo to find the right one | The URL names the repo; for a bare `#n`, ask |
| Starting to implement after "check" or "analyze" | Stop at the report |
| Reporting something already fixed on the default branch | Check the actual default-branch revision and linked PRs |
