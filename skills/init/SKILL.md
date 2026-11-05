---
description: Set up strip-down in this repository - detect the stack, routing style, analytics and feature-flag vendors, pick a mode, and write .stripdown/config.yml. Run this once before the other strip-down commands.
when_to_use: The user asks to set up, initialise or configure strip-down, or runs another strip-down command in a repo that has no .stripdown/config.yml yet.
argument-hint: "[pre-users|has-users]"
allowed-tools:
  - Bash(python3 *)
  - Read
  - Write
  - Glob
---

# strip-down: init

Set up strip-down in the current repository. This is read-only apart from
writing `.stripdown/config.yml`.

## 1. Detect what this repo is

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_stack.py"
```

It reports frameworks, routing style, top file extensions, which analytics /
feature-flag / billing vendors appear in dependency files, and a suggested
mode. It touches no network.

## 2. Settle the mode

`$1` may already say which mode to use. Otherwise take the script's
`suggested_mode` and confirm it with the user in one line, because the two
modes answer different questions:

- **`has-users`** — the product has real users and usage data exists somewhere.
  The work is a usage audit.
- **`pre-users`** — an idea or an MVP with no meaningful usage. There is
  nothing to measure, so the work is a *scope* analysis, which lands in a later
  version of this plugin. In this mode `inventory` and `cost` still work and
  are still useful: they tell the user how much they have already built and
  what it is costing them.

Do not infer the mode from repository size or commit count. Ask.

## 3. Write the config

Write `.stripdown/config.yml`, creating the directory if needed. Keep exactly
this shape and fill it from what you found:

```yaml
version: 1
mode: has-users
stack:
  frameworks:
    - next
  routing:
    - next-app-router
vendors:
  analytics:
    - posthog
  flags:
    - launchdarkly
history_months: 12
usage:
  source: csv
  path: ''
```

`history_months` is the window `cost` uses. `usage.source` is one of `csv`
(the default, and the only one needing no credentials), `posthog-mcp`, or
`none`.

## 4. Tell the user what to do next, and what is honestly available

Say, briefly:

1. `/strip-down:inventory` next — nothing else works without it.
2. Whether `cost` will work: it needs git history. If `detect_stack.py`
   reported `git: false`, say so plainly.
3. Whether usage data is reachable. If no analytics vendor was detected, say
   that `usage` will need a CSV export and point at
   `${CLAUDE_PLUGIN_ROOT}/skills/usage/csv-schema.md`.

Also add `.stripdown/` to the repo's `.gitignore` **only if the user asks**.
The default is the opposite: the inventory is meant to be committed and
reviewed in pull requests like any other source file. Never write credentials
into `.stripdown/`; nothing in this plugin needs them there.
