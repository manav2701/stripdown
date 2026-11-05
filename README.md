# strip-down

**A Claude Code plugin that shows you which features are earning their keep.**

Every product-analytics tool can tell you which of your *instrumented events*
are quiet. None of them can tell you what's in your product that you never
instrumented, or what each feature costs you to keep.

strip-down runs inside your repository. It builds a feature inventory from the
code itself, prices each feature from your git history, joins both against
usage data you export, and then refuses to call anything a removal candidate
until it has passed seven gates. It never deletes anything.

**Status: v0.4.** Seven commands, 108 tests, no dependencies.

---

## Table of contents

- [The original idea](#the-original-idea)
- [What it became, and why](#what-it-became-and-why)
- [Install](#install)
- [The commands](#the-commands)
- [How it actually works](#how-it-actually-works)
- [The five buckets](#the-five-buckets)
- [The seven kill gates](#the-seven-kill-gates)
- [Evidence grading](#evidence-grading)
- [What it doesn't do](#what-it-doesnt-do)
- [Privacy](#privacy)
- [Roadmap](#roadmap)
- [Development](#development)

---

## The original idea

This is the brief the project started from, as proposed:

> I want to make a Claude plugin called strip-down. It will be open sourced.
> Anyone with a startup idea, or who has built a startup, or a growing company,
> can use this plugin to check and see what features are bloating their app
> that they should remove — and strip it down.
>
> For an idea or MVP with no users, it just blatantly tries to find and
> understand their business idea, search and look up what's actually in demand
> and not implemented much currently, and ask to remove the ones not in much
> demand.
>
> For startups with customers it will do a mix of that, and also — you have to
> find a way to do this — check which features of their platform get more
> engagement, which ones don't at all, to strip down, and which ones could have
> potential if maneuvered a little better.

Three distinct asks in there: **find the bloat**, **research demand for the
pre-users case**, and **split the quiet features into "dead" versus "could work
if repositioned"**. The third one turned out to be the sharpest instinct in the
brief, and the second turned out to be the weakest idea. Here's what each
became.

## What it became, and why

| In the brief | What was built | Why it changed |
|---|---|---|
| "check and see what features are bloating their app" | A feature inventory built **from the code**, joined to usage and to git-measured maintenance cost | Analytics tools only see instrumented events. Claude Code is in the repo, so it can see everything that exists — and the gap between the two sets is the real finding |
| "features they should remove" | Five buckets behind seven kill gates. A `cut` bucket means *a human should now decide* | A tool that says "delete this" will eventually be wrong about something load-bearing. The gates are the cheapest available check against each way that happens |
| "which ones don't get engagement at all" | Usage **signatures**, with `blind-spot` and `no-data` kept strictly separate | "No events" usually means "never instrumented", not "never used". Collapsing those is how you delete something a paying customer depends on |
| "which could have potential if maneuvered a little better" | The `reposition` bucket, plus `/strip-down:survey` | Your best instinct. Low breadth + high depth among the few who found it = a placement problem, not a value problem. But confirming it needs *awareness* data, which no event stream contains — so the plugin generates the survey and says it can't answer it |
| "search and look up what's actually in demand" | A **scope diff** (what you built that isn't on your critical path) + a cited competitor matrix + a graded claims ledger that rejects uncited demand claims | This is where an LLM produces the most confident fiction, and the good sources are closed: Google Trends has no usable API, Reddit is contract-only, G2 and Capterra prohibit scraping. So the command measures what *is* knowable and refuses to assert the rest |
| "strip it down" for a pre-users MVP | Reframed as scope, not bloat | A product with no users doesn't have a bloat problem. It has a scope problem: six half-jobs instead of one whole one |
| (implied) "removing features will help" | No retention claim anywhere | I went looking for a published case of feature removal improving retention and **did not find one**. The honest case for removal is the cost you stop paying |

The full research, the sources, and the things that don't work are in
[docs/PLAN.md](docs/PLAN.md).

## Install

```bash
/plugin install strip-down --marketplace manav2701/stripdown
```

On older Claude Code versions, in two steps:

```bash
/plugin marketplace add manav2701/stripdown
```

```bash
/plugin install strip-down@stripdown
```

No dependencies, no API keys, no configuration. Python standard library only.

## The commands

| Command | Does | Needs |
|---|---|---|
| `/strip-down:init` | Detect stack, routing, analytics and flag vendors; pick a mode | — |
| `/strip-down:inventory` | Build the feature inventory from code; find blind spots | — |
| `/strip-down:cost` | Price each feature from git history | git |
| `/strip-down:usage` | Join exported usage: breadth, depth, retention, trend, revenue | a CSV |
| `/strip-down:verdict` | Five buckets, seven gates, missing evidence named | usage |
| `/strip-down:sunset <id>` | Draft a removal plan — a document, not a deletion | usage |
| `/strip-down:survey <id>` | Generate the awareness survey that tells discovery from value | — |
| `/strip-down:demand` | Scope diff + cited competitor matrix, for pre-users mode | — |

Plus three agents: `red-team` (argues against every cut),
`feature-cartographer` (maps large repos), `demand-researcher` (external
evidence under citation rules).

## How it actually works

**1. The inventory is the foundation.** `inventory` scans for routes across 18
frameworks, feature flags across 7 vendors, entitlement gates, background jobs,
webhooks, CLI commands, tables, GraphQL types — and every analytics event name
in the code. It emits *signals, not features*: grouping them is a
product-granularity judgment, so the model proposes and you correct. Output is
`.stripdown/inventory.yml`, meant to be committed and reviewed like source.

**2. The blind-spot list falls out of it.** Features that exist in the code with
no events mapped. Your dashboard cannot show you these, because the gap *is* the
absence of instrumentation.

**3. Cost is measured, not guessed.** Every feature-audit framework in
circulation asks you to plot value against maintenance cost, then sources that
axis from a meeting. `cost` uses one `git log` pass:

```
id             commits  churn  fix_ratio  authors  bus_1  loc  cost_index
billing              5   1240      60.0%        2  false  830       41.9
reports              2     90       0.0%        2  false  210        6.1
weekly-digest        0      0          -        1   true   95        1.2
```

`fix_ratio` is the sharpest single signal: a feature you keep fixing and nobody
uses costs you twice. `no_activity_in_window` is the counterweight — a feature
nobody touches is *cheap to keep*, and removing it has its own risk.

**4. Usage gives signatures, not verdicts.** Breadth with a Wilson 95% interval
(because "2 of 3 users" is not 67% adoption), depth computed over *adopters
only*, retention, trend, and revenue concentration if you supply ARR.

**5. Verdict applies the gates and sorts.** Then `red-team` argues against every
cut candidate, and `sunset` drafts the plan.

## The five buckets

| Bucket | Means | Action |
|---|---|---|
| `cut` | every gate passed | a human decides; `sunset` drafts the plan |
| `reposition` | few found it, those who did kept using it | fix placement, don't remove |
| `keep` | in ordinary use | nothing |
| `blind-spot` | nothing measures it | instrument it, or decide deliberately without data |
| `blocked` | would be a cut, but a gate failed or is unanswered | the gate is named |

**`blocked` is the output working, not failing.** Three gates rest on facts only
a human has, so a fresh inventory blocks everything. That's intended.

## The seven kill gates

Nothing reaches `cut` without passing all seven. An *unanswered* gate blocks,
because the default has to be that we don't know.

1. **instrumentation** — is it actually measured? A blind spot can't be cut.
2. **dormancy** — unused across a *full seasonal cycle*. A window under a year
   fails: annual features (tax, renewals, reporting) look dead for eleven
   months. A feature with live users also fails — removing it is a product
   decision with a migration plan, not a usage threshold.
3. **dependency** — does anything statically import it? A pass means "no static
   import crosses this boundary", which is weaker than "nothing depends on it",
   and the tool says so.
4. **regulatory** — audit logs, data export, account deletion, consent,
   accessibility, SSO, encryption, invoices, tax records. Never removed on usage
   evidence alone. A name that *looks* regulated requires an explicit
   `regulated: no` **plus a written reason**.
5. **contractual** — named in a contract, SLA or public API? Absence of evidence
   in the repo is not evidence of absence; contracts aren't in the repo.
6. **revenue** — how much ARR sits in accounts that touch it, and is it
   concentrated in one. A rarely used feature can be load-bearing for your
   largest customer.
7. **migration** — is there a path for current users, or nobody to migrate?

## Evidence grading

Every external claim in `demand` mode goes in `.stripdown/demand.yml` with a
grade, and the grade decides what the claim may do:

| Grade | Means | Requires |
|---|---|---|
| **A** | your own data | a local path or `own-data:<what>` |
| **B** | a primary public page fetched this run | an `https` URL and a `fetched` date |
| **C** | public discussion (HN, GitHub issues, app reviews) | an `https` URL and a `fetched` date |
| **D** | model inference, no source | **justifies nothing**; must be phrased as a question |

A grade-D claim that asserts rather than asks, or points at a feature as
justification, is a validation **error**. That rule is the only thing between
this command and a plausible hallucination with a feature id attached.

## What it doesn't do

- **It deletes nothing**, and opens no pull request that does. `sunset` produces
  a document.
- **`cut` never means "safe to delete."** It means every available gate passed
  and a human should now decide.
- **It makes no retention claims.** No published evidence supports them.
- **It can't tell a discovery problem from a value problem on its own.** That
  needs a survey, which it writes and you run.
- **It can't see churned users.** A feature whose absence drove people away
  leaves no trace in any export, or in a survey of current users.
- **It can't tell you what the market wants.** The scope diff is evidence about
  what you built; the competitor matrix is evidence about what others shipped.
  The gap between those and demand is closed only by talking to people.
- **The scan is regex over text.** It misses dynamically registered routes and
  flags read from a database, and can't distinguish a live call site from a dead
  one. [reference.md](skills/inventory/reference.md) lists the failure modes.

## Privacy

Every command makes **no network calls** except `demand`, which fetches only
public competitor pages with your per-domain approval. The plugin declares no
credentials, ships no MCP server, and has nothing to leak. Aggregate CSVs
contain no user identifiers and are the documented default. Feature names, event
names and usage figures never go into a search query. Full detail in
[PRIVACY.md](PRIVACY.md).

## Roadmap

| | |
|---|---|
| **v0.1** ✅ | `init`, `inventory`, `cost` — fully offline |
| **v0.2** ✅ | `usage` — CSV first, PostHog via your own MCP server |
| **v0.3** ✅ | `verdict`, the seven gates, `sunset`, `red-team` agent |
| **v0.4** ✅ | `demand` — scope diff, competitor matrix, graded claims; `survey` |
| v0.5 | `amnesty` (blameless "what would you cut" with the team), more stack heuristics, and only if genuinely needed, first-party Amplitude/Mixpanel MCP adapters |

Out of scope, possibly forever: automated code deletion, feature-level revenue
attribution, retention-lift predictions, and scraping any source whose terms
prohibit it.

## Development

```bash
python3 tests/test_stripdown.py
```

108 tests, standard library only, no setup. They build throwaway git
repositories with controlled history so the cost and gate behaviour is verified
rather than assumed. The tests that matter most are the ones asserting the tool
produces **no** recommendation: a regulated-sounding feature, a short
observation window, a missing revenue column, a feature with live users.

```bash
claude plugin validate --strict .
```

Every script works standalone, without Claude:

```bash
python3 scripts/scan_signals.py --names event
python3 scripts/cost_report.py --months 12 --json
python3 scripts/usage_report.py --aggregate export.csv
python3 scripts/verdict_report.py --aggregate export.csv --window-days 400 --revenue arr.csv
python3 scripts/sunset_plan.py weekly-digest --stdout
python3 scripts/scope_diff.py --path signup,editor,share
python3 scripts/validate_claims.py
```

## Contributing

Disagreements with the honesty section are the most welcome kind. In particular:
if you have a counter-example to "no published evidence that removing features
improves retention," please open an issue — that's the claim in here I'd most
like to be wrong about.

MIT licensed.
