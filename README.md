# Agentic Flow

Reusable skills for Codex and Claude Code, plus a Codex subagent setup.

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

## Codex subagent setup

The [codex](codex) directory contains five role configurations, a portable [config fragment](codex/config.toml), and the [delegation policy](codex/AGENTS.md). This setup uses `gpt-6-luna` for every subagent:

| Role | Work | Reasoning | Configured sandbox |
| --- | --- | --- | --- |
| [default](codex/agents/default.toml) | General-purpose fallback | `xhigh` | Inherits the parent |
| [explorer](codex/agents/explorer.toml) | Focused repository investigation | `xhigh` | `read-only` |
| [worker](codex/agents/worker.toml) | Bounded implementation and validation | `xhigh` | `workspace-write` |
| [reasoner](codex/agents/reasoner.toml) | Difficult behavior and architecture decisions | `max` | `read-only` |
| [reviewer](codex/agents/reviewer.toml) | Independent technical review | `max` | `read-only` |

The primary agent owns decisions, integration, final validation, and the final response. It delegates when useful, keeps agent work one level deep, and uses `reasoner` or `reviewer` only when the user explicitly requests that role. The config caps concurrently open subagent threads at five, excluding the primary.

### Install the subagents

From this repository's root, copy the role files into your Codex home. These commands skip existing role files:

```sh
agentic_codex_dir="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$agentic_codex_dir/agents"
for role in default explorer worker reasoner reviewer; do
  if [ -e "$agentic_codex_dir/agents/$role.toml" ]; then
    echo "Already configured: $role; review local changes before replacing it."
  else
    cp "codex/agents/$role.toml" "$agentic_codex_dir/agents/$role.toml"
  fi
done
```

Merge [codex/config.toml](codex/config.toml) into your existing `$CODEX_HOME/config.toml` (normally `~/.codex/config.toml`). Update existing `[features]`, `[agents]`, and role tables rather than appending duplicate tables. The `./agents/` paths resolve relative to that config file, so they work after copying the roles into the same Codex home. Keep your existing main-agent model, authentication, providers, plugins, and project settings.

Merge the marked section from [codex/AGENTS.md](codex/AGENTS.md) into your personal `$CODEX_HOME/AGENTS.md`, or into a project's `AGENTS.md` when the policy should apply only there. Preserve other instructions and replace an existing section with the same markers rather than duplicating it. Restart Codex after changing the setup.

Use a Codex release that supports these custom-agent settings. If your account does not offer `gpt-6-luna` or the configured effort, select supported values in the config fragment and affected role files. Role files set their own model and effort, so changing only the `[agents]` defaults does not change those roles. Parent runtime permission overrides can take precedence over the sandbox values in this table.

The [official OpenAI subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents) explains custom roles and runtime overrides. The [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) documents role config paths and thread limits. These TOML files are for Codex; the two skills above can also be used in Claude Code.

### Use the subagents

```text
Use an explorer to locate the export flow, then a worker to implement the agreed fix.
Use a reasoner to compare these architecture options.
Use a reviewer to check this branch for regressions and missing tests.
```

Use only the roles needed for the task. The delegation policy keeps simple work with the primary agent.

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
