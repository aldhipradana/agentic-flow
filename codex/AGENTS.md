<!-- codex-subagent-policy:start -->

## Subagent delegation policy

The root agent owns orchestration, reasoning, decisions, integration, conflict
resolution, final validation, review, and the final response. Spawn `reasoner`
or `reviewer` only when the user explicitly requests that role, even if a skill
or workflow recommends it.

Delegate when it materially improves speed, parallelism, focus, or confidence.
Keep trivial tasks, obvious edits, and simple questions local. Use only as many
agents as help; no task must pass through every role.

### Agent roles

- `explorer`: preferred for fast, read-only investigation. Locate relevant
  files, symbols, tests, configuration, and dependencies; trace behavior and
  analyze logs or similar implementations. Prefer targeted searches and report
  evidence, references, conclusions, and uncertainty. Do not implement changes.
- `worker`: preferred for bounded implementation. Reuse supplied findings,
  implement agreed changes, update tests, and run focused validation. Decide
  obvious local details; escalate architecture, ambiguous behavior, or unexpected
  cross-module impact to the root.
- `reasoner`: independently analyze difficult root-cause, architecture,
  state/concurrency, or tradeoff questions. Challenge the root's hypothesis,
  consider alternatives, identify assumptions, distinguish facts from inference
  and uncertainty, and recommend an approach with rationale. Prefer supplied
  explorer evidence over repeated investigation.
- `reviewer`: independently review important decisions or meaningful changes
  for correctness, regressions, edge cases, races, security, compatibility,
  missing tests, and unnecessary complexity. Focus on material risks rather
  than style or disagreement for its own sake; say clearly when the solution is
  sound. Remain read-only unless explicitly instructed otherwise.
- `default`: use only when no specialized role fits better.

### Workflow and parallelism

For non-trivial repository work:

1. Explore enough to understand the relevant area. The root assesses the request,
   verifies important assumptions, resolves ambiguity, and chooses the approach
   before implementation. Revisit it only for new evidence, changed requirements,
   or a material blocker.
2. Implement with workers where delegation helps. Parallelize independent
   investigation or implementation when it reduces latency. Avoid duplicate
   investigation, overlapping worker edits, and spawning merely to add agents.
3. Wait for relevant delegated results before dependent decisions. Validate
   consequential findings without mechanically repeating the investigation.
4. Integrate, run applicable validation, then review the consolidated result in
   the root for edge cases, regressions, security, and compatibility. Review
   proposals only once meaningful; avoid repeatedly reviewing partial changes.
   If review prompts changes, validate and review the updated result.

Give each agent a focused objective, existing evidence, scope, constraints, and
expected output. Pass explorer findings and settled decisions to workers.
Require concise, actionable results with relevant references, evidence,
conclusions or recommendations, changes, validation, and blockers or uncertainty
as applicable; avoid raw logs and rediscovery of completed work.

Keep delegation one level deep: subagents complete their task and report to the
root. Further delegation requires an explicit request or clear necessity.

### Validation and completion

Run tests appropriate to the change; broaden or repeat testing only when
failures, risk, follow-up changes, or unresolved uncertainty justify it. Before
completing meaningful work, ensure intended behavior is understood, important
assumptions are verified, implementation matches the decision, validation has
run, and material review findings are addressed. Stop investigating, delegating,
or reviewing when further work is unlikely to materially improve the result.

<!-- codex-subagent-policy:end -->
