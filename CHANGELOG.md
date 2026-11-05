# Changelog

## 0.4.0

`demand` mode and the awareness survey.

- `scope_diff.py` — for a product with no users, measures what share of the
  lines, commits and churn went to features *off* the declared critical path,
  plus a timeline of when each feature first appeared. It will not guess the
  critical path; you declare it.
- `validate_claims.py` — makes evidence grading mechanical. A grade-D claim
  (model inference, no source) that asserts rather than asks, or names a
  feature as justification, is a validation error. Sources whose terms prohibit
  scraping are warned about by name.
- `/strip-down:demand` and `/strip-down:survey` skills; `demand-researcher`
  agent.
- `skills/demand/limits.md` documents which external sources are actually
  reachable and which are closed, so the command is not designed around a
  source that turns out to be unusable.

## 0.3.0

Recommendations, gated.

- `verdict_report.py` — five buckets (`cut`, `reposition`, `keep`,
  `blind-spot`, `blocked`), each row carrying its evidence, its *missing*
  evidence, a confidence level and the cheapest next step.
- `lib/gates.py` — the seven kill gates. An unanswered gate blocks, so a fresh
  inventory blocks everything. Features whose names suggest a legal, security
  or accessibility obligation require an explicit override with a written
  reason.
- `lib/deps.py` — an approximate inbound-dependency index, which reports its
  own limits: static imports only.
- `sunset_plan.py` — drafts a removal plan. Flag off first, delete last; one
  accountable owner plus three named reviewers; abort triggers decided in
  advance. It writes a document and changes no code.
- `red-team` and `feature-cartographer` agents.
- **Fix:** a feature with zero adopters against a large eligible population was
  reported as `insufficient-data`. Zero out of thousands is a *strong* result;
  the adopter floor meant for depth was swallowing it. It is now `dormant`.
- `usage` now reports `window_days` (measured from timestamps, or declared with
  `--window-days`) and per-feature `arr_share_pct`, both of which the dormancy
  and revenue gates need.

## 0.2.0

- `usage_report.py` — joins exported usage onto the inventory. Breadth with a
  Wilson 95% interval, depth over adopters only, retention, trend, revenue
  concentration. Reports signatures, never recommendations, and keeps
  `blind-spot` separate from `no-data`.
- Two CSV shapes, documented with copy-pasteable PostHog/Amplitude/Mixpanel
  queries. No credentials: you export, strip-down reads.
- `skills/usage/posthog.md` for querying the user's own PostHog MCP server.

## 0.1.0

- `detect_stack.py`, `scan_signals.py`, `cost_report.py`,
  `validate_inventory.py`.
- Feature inventory built from code: routes across 18 frameworks, flags across
  7 vendors, entitlement gates, jobs, webhooks, CLI commands, tables, GraphQL,
  and every analytics event name in the repository.
- Maintenance cost measured from git history rather than estimated.
- `lib/sdyaml.py`, a documented YAML subset reader/writer, so the inventory can
  be hand-edited YAML with no third-party dependency.
