---
description: Build a feature inventory from this codebase - every route, feature flag, entitlement gate, endpoint, job and analytics event - and write it to .stripdown/inventory.yml. Use when asked what features a product has, to list or map the surface area of a codebase, to find untracked or uninstrumented features, or before a feature audit.
when_to_use: The user wants to know what features exist in a repo, wants a feature map or surface-area list, asks which features have no analytics coverage, or is starting a strip-down audit.
argument-hint: "[--refresh]"
allowed-tools:
  - Bash(python3 *)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# strip-down: inventory

Produce `.stripdown/inventory.yml`: the list of features that actually exist
in this repository, and for each one the code that implements it and the
analytics events that measure it.

This file is the foundation — `cost` and `usage` are joins against it. Getting
it roughly right matters more than getting it quickly.

## Why this is worth doing at all

Analytics tools only know about features someone remembered to instrument.
This file is built from the code, so the gap between its `paths` and its
`events` is the list of features nobody can currently see in a dashboard. That
list is the main thing v0.1 produces, and no analytics vendor can produce it.

## 1. Gather signals

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_signals.py"
```

That prints a summary: counts per signal type, top directories, the full set of
analytics event names, and a few samples per type. Then pull detail only for
what you need:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_signals.py" --type route --limit 500
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_signals.py" --names event
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_signals.py" --names flag
```

Signals are evidence, not features. The scan is regex over text, so it misses
dynamically registered routes and flags read from a database, and it cannot
tell a live call site from a dead one. Read
[reference.md](reference.md) for what each signal type means per stack, how to
set feature granularity, and the failure modes worth checking by hand.

## 2. Read the product's own description of itself

Before grouping anything, read the README, any landing-page copy in the repo,
and the top-level navigation definition if there is one. Users name features
differently from the way the code is laid out, and the inventory should use
*their* names. A nav or sidebar definition is usually the single best source of
feature boundaries, because it is the product's own answer to the question.

## 3. Group signals into features

This is the judgment call, and it is yours to propose and the user's to
correct. The rules that matter:

- **A feature is something a user would name.** "Billing", not
  `app/billing/page.tsx`. If a user would not recognise it as a thing they can
  use, it is not a feature — it is implementation.
- **Granularity: aim for 15–60 features in a typical product.** Fewer than 10
  and the inventory is too coarse to act on; more than 100 and nobody will
  review it, which makes it worthless. Collapse sub-pages into their parent
  unless the sub-page is independently valuable.
- **Infrastructure is not a feature.** Auth plumbing, build config, CI, design
  systems and shared utilities belong in no feature. Leave them unassigned;
  `cost` reports unassigned files separately and that is the correct outcome.
- **Admin and internal tooling are features.** They are often the most
  expensive and least examined code in a product.
- **Map events honestly.** Put an event under a feature only if firing it means
  that feature was used. A generic `page_view` belongs nowhere. An event name
  must appear under at most one feature, or usage gets double counted.
- **Leave `events: []` when there is nothing to map.** That is a blind spot and
  the tooling treats it as one. Do not invent plausible event names to make the
  file look complete — that silently converts a measurement gap into fake data.

## 4. Write the file

The schema, with every field explained, is in [schema.md](schema.md). Write
`.stripdown/inventory.yml` with `Write`.

Set `gates` honestly. Every gate starts `unknown` and only a human can answer
it — whether a feature is named in a contract, whether it is load-bearing for a
regulation or an accessibility obligation, whether it is part of a public API
commitment. Do not fill these in from the code. Guessing here is how a tool
like this gets someone's product broken.

On `--refresh`, read the existing file first and preserve every human edit:
names, owners, tags, notes, gates and status. Only add newly-found features and
flag ones whose paths no longer match anything. Say explicitly what changed.

## 5. Validate, then report

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_inventory.py"
```

Exit 0 is clean, 1 has warnings, 2 is invalid — fix errors before reporting.

Then tell the user, briefly:

- how many features, and the coverage percentage
- **the blind spots**: features with no events mapped. Lead with this; it is
  the most actionable output and the one they cannot get elsewhere.
- any event names found in the code but mapped to no feature
- which features you were unsure about, and why — name them rather than hiding
  the uncertainty in a confident-looking file

Close by telling them the file is a draft meant to be edited and committed,
and that `cost` and `usage` are only as good as it is.
