---
description: For a product with no users yet - measure how much of what you have built is off the critical path for the one job you claim to do, and research competitors and external signals under strict citation rules. Use for an MVP or idea-stage scope review, or when asked what to cut from a product with no usage data.
when_to_use: The user has an MVP or pre-launch product with no meaningful usage, asks what to strip from an idea-stage product, wants a scope review, or wants a competitor feature comparison.
argument-hint: "[--path id,id,id]"
allowed-tools:
  - Bash(python3 *)
  - Read
  - Write
---

# strip-down: demand

For `pre-users` mode. There is no usage data, so there is nothing to audit —
which means this command does two separable things, and only the first is a
measurement.

**Read this before starting:** this is the weakest part of strip-down, and the
part most likely to produce confident fiction if run carelessly. The honest
scope is narrow on purpose. [limits.md](limits.md) says what is and is not
reachable and why; read it before making any external claim.

## 1. Scope diff — local, measurable, trustworthy

A pre-PMF product does not have a bloat problem. It has a scope problem:
shipping six half-jobs instead of one whole one.

First, establish the one job. Read the README, any landing-page copy in the
repo, and the pitch if the user gives you one. State the job back to the user
in one sentence and get it confirmed — do not proceed on your own reading of
it.

Then ask which features deliver it, and write that to the inventory as
`critical_path:`. The script will not guess this, by design.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scope_diff.py" --path signup,editor,share
```

You get: the share of lines, commits and churn that went to features *off* the
declared path, and a timeline of when each feature first appeared — scope creep
as a chronology rather than an impression.

Two things to carry into the report:

- **Off the path is not an argument for removal.** Admin, billing, support and
  compliance are off the path by nature and load-bearing anyway. This measures
  where effort went, not what deserves to exist.
- **The timeline is the most useful artifact here.** "You shipped the core in
  March and have added five features since, none of them on the path" is a
  sentence a founder can act on.

Run this even with no critical path declared — the timeline still works.

## 2. External research — cited, graded, or not stated at all

Every external claim goes in `.stripdown/demand.yml` with a grade and a
source, and the grade decides what the claim is allowed to do:

| Grade | Means | Requires |
|---|---|---|
| **A** | your own data (repo, git, analytics, revenue) | a local path or `own-data:<what>` |
| **B** | a primary public source fetched this run | an `https` URL and a `fetched` date |
| **C** | public discussion (HN, GitHub issues, app reviews) | an `https` URL and a `fetched` date |
| **D** | model inference, no source | **justifies nothing**, must be phrased as a question, `supports` must be empty |

```yaml
version: 1
claims:
  - id: c1
    claim: 'Linear ships bulk CSV export on every paid tier; we do not'
    grade: B
    source: 'https://linear.app/docs/import-export'
    fetched: '2026-11-05'
    kind: competitor
    supports: [exports]
  - id: c2
    claim: 'Would teams pay for scheduled exports, or is one-off enough?'
    grade: D
    source: ''
    kind: signal
    supports: []
```

Then validate, and fix every error before reporting anything:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_claims.py"
```

A grade-D claim that asserts rather than asks, or points at a feature as
justification, is an **error**. That rule is the only thing between this
command and a plausible hallucination with a feature id attached. Do not work
around it by upgrading the grade — upgrade the evidence or drop the claim.

## Fetching pages

A plugin cannot pre-approve `WebFetch`, so the user is asked per domain the
first time. That is correct behaviour for a tool fetching arbitrary
third-party pages. Work with it: decide the full list of URLs first, tell the
user which domains you are about to fetch and why, then fetch them together
rather than drip-feeding approval prompts.

Competitor pricing and documentation pages are the backbone here — public,
fetchable, citable, and legal. Prefer them over anything else.

## The privacy boundary

**Never put the product's unreleased feature names, event names, code or
internal metrics into a search query or a fetched URL.** Research from the
product's *public* description only. Leaking an unreleased feature name into a
search is a real and serious failure, not a theoretical one.

## Reporting it

Lead with the scope diff, because it is the measured part. Then the competitor
matrix from grade-B claims. Then, clearly separated and clearly labelled, the
open questions — the grade-D claims, as questions.

Say explicitly that this command cannot tell the user what the market wants.
Nothing here is evidence about what anyone wants; the scope diff is evidence
about what they have built, and the competitor matrix is evidence about what
others shipped. The gap between those and demand is a gap only talking to users
closes.
