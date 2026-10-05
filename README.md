# Agentic Flow

Two reusable skills for Codex and Claude Code:

| Skill | Purpose |
| --- | --- |
| [check-issue](skills/check-issue/SKILL.md) | Analyze GitHub or Gitea issues using their text, comments, available images, and repository code. Analysis is the default; implementation requires a request to fix the issue. |
| [daily-standup](skills/daily-standup/SKILL.md) | Produce a copyable Yesterday/Today standup from verified personal work across local Git repositories, GitHub, and Gitea. |

## Install

### Codex

Ask Codex:

```text
Use $skill-installer to install skills/check-issue and skills/daily-standup
from aldhipradana/agentic-flow on the master branch.
```

Restart Codex after installation. The skill installer checks for existing destinations instead of overwriting your customizations.

### Claude Code or manual installation

Clone the repository, then copy the complete skill directories into your personal skills directory:

```sh
git clone https://github.com/aldhipradana/agentic-flow.git
cd agentic-flow
mkdir -p "$HOME/.claude/skills"
for skill in check-issue daily-standup; do
  if [ -e "$HOME/.claude/skills/$skill" ]; then
    echo "Already installed: $skill; review local changes before replacing it."
  else
    cp -R "skills/$skill" "$HOME/.claude/skills/$skill"
  fi
done
```

For manual Codex installation, use `${CODEX_HOME:-$HOME/.codex}/skills` as the destination. Project installations can use `.claude/skills` or the project's supported Codex skills directory. Keep `check-issue/fetch_issue.py` beside its `SKILL.md`.

Claude Code's [skill documentation](https://code.claude.com/docs/en/skills) explains personal and project installation locations.

## Requirements

- A local repository checkout and an assistant with shell access. Image inspection needs an available image tool or user-provided attachments.
- Git and Python 3 for `check-issue`. The helper uses only Python's standard library.
- An installed and authenticated `gh` CLI for GitHub, or `tea` with a matching saved login for Gitea. The installed `tea` must support `login list` and `api`; check its `--help`. Local Git evidence remains usable for standups when a forge CLI is unavailable.

The helper downloads same-host Gitea attachments through `tea`. GitHub and external-host images are explicitly marked `NOT FETCHED`; the assistant must inspect them using another authorized tool or disclose that they remain unread. Custom GitHub Enterprise hosts need an available authenticated read-only alternative.

No credentials or personal account defaults are bundled. `daily-standup` discovers the current user's identity and timezone; you can specify both in your request.

## Use

In Codex:

```text
$check-issue https://github.com/owner/repo/issues/123
$daily-standup — use Asia/Makassar; today I plan to finish the export flow
```

In Claude Code, invoke `/check-issue` or `/daily-standup` with the same arguments. Ordinary requests such as “check this issue” or “generate my daily standup” can also select the skills.

Issue analysis and standup generation leave repository files and forge records untouched. To implement an issue fix, request it explicitly; publishing, commenting, and other external actions need their own authorization.

## Development

Run the helper's regression tests from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Tests cover remote/reference parsing, GitHub comment pagination, API errors, attachment host boundaries, and the saved evidence/digest.
