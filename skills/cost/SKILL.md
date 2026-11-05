---
description: Measure what each feature costs to keep, from git history - commits, churn, bug-fix ratio, authors, bus factor, lines of code and tests. Use when asked which features are expensive to maintain, where engineering time is going, or for the cost side of a feature audit.
when_to_use: The user wants maintenance cost per feature, asks which parts of the codebase soak up effort, asks about technical debt by feature, or has just run /strip-down:inventory.
allowed-tools:
  - Bash(python3 *)
  - Read
---

# strip-down: cost

Price every feature in the inventory from git history. Read-only; needs git.

## Run it

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cost_report.py" --months 12
```

Use `--all-history` for a young repo, or `--months N` to match the window the
user cares about. Add `--json` if you need to post-process.

If it reports no inventory, run `/strip-down:inventory` first. If it reports
the directory is not a git repository, stop and say so: there is no fallback,
and guessing a cost axis is exactly what this command exists to avoid.

## What the numbers mean

- `cost_index` — share of the repo's weighted maintenance activity
  (`0.5*churn + 0.3*commits + 0.2*loc`, as percentages). An ordering
  heuristic. It is not money and must never be presented as money.
- `fix_ratio` — share of the feature's commits whose subject looks like a bug
  fix. A high ratio on a low-usage feature is the strongest single signal in
  v0.1: you are paying repeatedly for something nobody is using.
- `bus_factor_1` — one author has touched it. A liability, especially if that
  person has left; check with the user rather than assuming.
- `no_activity_in_window` — **read this carefully.** A feature nobody has
  touched is *cheap to keep*. Low usage plus low cost is not urgent, and
  removal carries its own risk. Say that out loud rather than listing it as a
  candidate because its usage is low.
- `coverage_pct` — share of repo files attributed to some feature. Below ~60%
  the inventory is incomplete and every share is understated. Lead with that
  caveat rather than burying it.

## Report it honestly

Give the user a table ordered by `cost_index`, then three short observations.
Rules for the prose:

- Pair cost with usage only if `/strip-down:usage` has actually run. Cost
  alone cannot say a feature is not worth keeping.
- Never recommend deleting anything. Cut recommendations and their gates are
  v0.3; this command reports a measurement.
- Repeat the script's own caveats where they bear on what you are claiming: a
  repo-wide reformat or a dependency bump inflates churn, generated or vendored
  code attributed to a feature inflates everything, and an imported or squashed
  first commit makes every feature present at import look multi-author.
- If `path_overlaps` is non-empty, mention it: those files are counted once,
  under the most specific pattern, which may not be what the user meant.
