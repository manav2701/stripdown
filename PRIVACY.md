# Privacy and safety

strip-down reads a codebase and, optionally, product usage data. Both are
sensitive. These are the rules the plugin holds itself to, and they are
testable claims rather than reassurances.

## What runs where

`inventory`, `cost` and `validate` are **local and offline**. They read files
and git history, write `.stripdown/`, and make no network calls. There is
nothing to configure and no credential to supply.

`usage` reads a CSV you produced. It makes no network calls either. If you have
PostHog's own MCP server connected, Claude can query it — but that is your
server, configured by you, with your credentials, outside this plugin.

## This plugin holds no credentials

It declares no `userConfig`, ships no MCP server, and has no API key of its
own. There is nothing here to leak. That is a deliberate v0.1/v0.2 choice: a
Claude Code plugin's hooks and MCP servers run outside the sandbox with your
full privileges, so a plugin that reads company analytics should ask for as
little trust as it can get away with.

If first-party Amplitude or Mixpanel adapters are ever added, they will be MCP
servers using `userConfig` with `sensitive: true` — the only sanctioned route
for a secret, since sensitive values are deliberately never substituted into
skill text. They are last on the roadmap for exactly this reason.

## Aggregates, not people

The `--aggregate` CSV format contains no user identifiers at all, and it is the
documented default. The event-level format needs a user id; use a pseudonymous
one. Nothing in this plugin needs an email address, a name, or any other
personal field, and no report prints an individual user.

## Nothing proprietary goes to the web

Feature names, event names, code and usage figures must never be put into a web
search or a fetched URL. Leaking an unreleased feature name into a search query
is a realistic and serious failure, so the skills state this as a boundary
rather than a preference. v0.1 and v0.2 make no web calls at all.

## It never deletes anything

No command in this plugin removes a feature, deletes code, or opens a pull
request that does. `inventory` writes `.stripdown/inventory.yml`; `init` writes
`.stripdown/config.yml`; everything else only reads and prints.

v0.2 makes no removal recommendations either, because the kill gates that
should precede one do not exist yet. It reports measurements and the shape of
the data.

## Keep `.stripdown/` free of secrets

The inventory and config are meant to be committed and reviewed like source.
Nothing in this plugin writes a credential there, and you should not either.

## Reviewing this plugin

It is open source and stdlib-only on purpose: every script is readable in one
sitting, there are no dependencies to audit, and `tests/test_stripdown.py` runs
with no setup. Read it before you install it — that advice is Anthropic's for
every plugin, and it applies here too.
