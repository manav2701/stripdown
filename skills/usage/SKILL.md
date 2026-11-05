---
description: Join product usage data onto the feature inventory - breadth, depth, retention, trend and revenue concentration per feature, plus which features have no analytics coverage at all. Use when asked which features get used, which features are quiet or dead, which have low adoption, or for the usage side of a feature audit.
when_to_use: The user wants per-feature usage or adoption numbers, asks which features nobody uses, asks whether low adoption is a discovery or a value problem, or has a PostHog/Amplitude/Mixpanel export to analyse.
argument-hint: "[path/to/export.csv]"
allowed-tools:
  - Bash(python3 *)
  - Read
  - Glob
---

# strip-down: usage

Join usage data onto `.stripdown/inventory.yml` and report, per feature:
breadth, depth, retention, trend, and — where revenue is supplied — how
concentrated that feature's users are.

Needs `/strip-down:inventory` to have run.

## Pick an input, in this order

**1. A CSV the user exports themselves.** The default, and the recommended
path. No credentials, no network, nothing leaves their machine. Two shapes are
accepted and both are documented with copy-pasteable PostHog/Amplitude/Mixpanel
queries in [csv-schema.md](csv-schema.md):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage_report.py" --aggregate export.csv
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage_report.py" --events events.csv --eligible 5000
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage_report.py" --events events.csv --revenue accounts.csv --eligible 5000
```

**2. PostHog's own hosted MCP server**, if the user has it connected. This
plugin ships no credentials and no analytics server of its own; PostHog's is
maintained by PostHog and the user configures it themselves. See
[posthog.md](posthog.md) for which tools to call, the HogQL to run, and how to
turn the result into the CSV above. Query in aggregate and cache — those tool
calls share PostHog's REST rate limits and some of them bill as AI spend.

**3. Nothing.** If no usage data is reachable, say so and stop. Report the
inventory's blind spots and the cost figures instead. Do not estimate usage, and
do not reason about which features "are probably" unused — that invents the
exact data this command exists to supply.

## Before you run it: the privacy boundary

Ask for aggregates, not people. The `--aggregate` shape contains no user
identifiers at all and is always preferable. If the user supplies event-level
data, do not read raw rows into the conversation beyond what you need to check
the header, and never put feature names, event names or usage figures into a
web search or a fetched URL. See [../../PRIVACY.md](../../PRIVACY.md).

## Reading the output

`signature` describes the *shape of the data*. It is not a recommendation, and
no signature clears a feature for removal. Six of them matter:

| Signature | Means | What it does not mean |
|---|---|---|
| `blind-spot` | no events mapped in the inventory | not that it is unused — it is unmeasured |
| `no-data` | events mapped, none in the export | genuinely ambiguous: unused, never instrumented, or outside the window |
| `discoverability-suspect` | few found it, those who did kept using it | not that it needs promoting — confirm with a survey |
| `value-suspect` | widely seen, little repeat use | the strongest usage-side signal, still not a verdict |
| `insufficient-data` | denominator too small for a rate | not that usage is low |
| `in-use` / `quiet` | ordinary range / little of either | — |

Four things to carry into any summary you write:

1. **`blind-spot` and `no-data` are different** and the distinction is the
   point. One is a gap in instrumentation; the other is ambiguous. Never merge
   them into "unused".
2. **Depth is computed over adopters only.** Reported over all users it just
   restates breadth, which is the most common way this metric is got wrong.
3. **Breadth carries a Wilson 95% interval.** Quote it when the interval is
   wide. "40% (95% CI 25–57%)" is honest; "40%" alone is not, at n=40.
4. **Churned users are in nobody's export.** A feature whose absence or
   brokenness drove people away leaves no trace here. Say this once, plainly,
   whenever you present a quiet feature.

If `events_in_data_not_in_inventory` is non-empty, report it: the inventory's
`events` lists are incomplete, and fixing that changes the numbers.

## Separating a discovery problem from a value problem

This is the question worth the most money and it cannot be answered from event
data alone. Breadth and depth give you the behavioural signature; awareness —
whether users know the feature exists — requires asking them. Thresholds in
circulation (under 40% awareness means discovery, over 70% means value) are one
blog's unvalidated heuristic, not a standard.

So: report the signature, say which hypothesis it favours, and say plainly that
confirming it needs an awareness survey. Do not present a `discoverability-suspect`
feature as established fact.

## Report it

Group features by signature, blind spots first, then `no-data`, then the
suspects. For each, give breadth with its interval, depth, trend, and — if
`cost` has run — the cost index alongside. A feature that is expensive *and*
`value-suspect` is the one worth the user's attention; a feature that is quiet
and costs nothing is not urgent, and removal has its own risk.

Make no removal recommendations. Gated cut recommendations are v0.3 and the
gates do not exist yet; saying "you could drop this" without them is precisely
the failure this plugin is built to avoid.
