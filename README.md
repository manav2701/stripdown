# strip-down

**A Claude Code plugin that shows you which features are earning their keep.**

Every product-analytics tool can tell you which of your *instrumented events*
are quiet. None of them can tell you what's in your product that you never
instrumented, or what each feature costs you to keep.

strip-down runs inside your repository. It builds a feature inventory from the
code itself, prices each feature from your git history, and joins both against
usage data you export. It never deletes anything.

**Status: v0.2.** Inventory, cost and usage work and are tested. Removal
recommendations do not exist yet, on purpose — see
[what it doesn't do](#what-it-doesnt-do) and [docs/PLAN.md](docs/PLAN.md) for
the full design and the research behind it.

---

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

No dependencies, no API keys, no configuration. Everything in v0.1 and v0.2 is
Python standard library and runs offline.

## Quickstart

```
/strip-down:init
```

```
/strip-down:inventory
```

```
/strip-down:cost
```

```
/strip-down:usage path/to/export.csv
```

`init` detects your stack and writes `.stripdown/config.yml`. `inventory`
writes `.stripdown/inventory.yml` — commit it; it's meant to be reviewed in
pull requests like source. `cost` and `usage` are joins against it.

## What you get

**1. A feature inventory built from code, not from memory.** Routes (Next.js,
Remix, SvelteKit, Nuxt, Astro, Rails, Django, Laravel, Express, Fastify, Nest,
FastAPI, Flask, Spring, ASP.NET, Go, Phoenix, Axum), feature flags
(LaunchDarkly, PostHog, Unleash, Flagsmith, GrowthBook, Statsig, Split),
entitlement gates, background jobs, webhooks, CLI commands, tables, GraphQL
types — and every analytics event name in the codebase.

**2. The blind-spot list.** Features that exist in the code with no analytics
events mapped to them. Your dashboard cannot show you these, because the gap
*is* the absence of instrumentation. This is the output nothing else produces.

**3. Measured cost of carry.** Every feature-audit framework in circulation
asks you to plot value against maintenance cost, then sources that cost axis
from a meeting where engineers guess. This measures it:

```
id             commits  churn  fix_ratio  authors  bus_1  loc  cost_index
billing              5   1240      60.0%        2  false  830       41.9
reports              2     90       0.0%        2  false  210        6.1
weekly-digest        0      0          -        1   true   95        1.2
```

`fix_ratio` is the sharpest signal in v0.1: a feature you keep fixing and
nobody uses is costing you twice. `no_activity_in_window` is the counterweight
— a feature nobody touches is *cheap to keep*, and removing it has its own
risk.

**4. Usage signatures, not verdicts.** Breadth (with a Wilson 95% interval,
because "2 of 3 users" is not 67% adoption), depth computed over adopters only,
retention, trend, and revenue concentration if you supply ARR per account.

Each feature gets a *signature* describing the shape of its data:

| Signature | Means |
|---|---|
| `blind-spot` | no events mapped — unmeasured, **not** unused |
| `no-data` | events mapped but absent from the export — genuinely ambiguous |
| `discoverability-suspect` | few found it; those who did kept using it |
| `value-suspect` | widely seen, little repeat use |
| `insufficient-data` | denominator too small to support a rate |
| `in-use` / `quiet` | ordinary range / little of either |

`blind-spot` and `no-data` are kept separate deliberately. One is an
instrumentation gap; the other could be disuse *or* an instrumentation gap *or*
your export window. Collapsing them into "unused" is how you delete something a
paying customer depends on.

## Usage data

No credentials. You export, strip-down reads. Two CSV shapes, both documented
with copy-pasteable PostHog/Amplitude/Mixpanel queries in
[skills/usage/csv-schema.md](skills/usage/csv-schema.md):

```csv
event,eligible_users,adopters,repeat_adopters
checkout_started,4820,1960,1310
```

or event-level rows (`user_id,event,timestamp,account_id`), from which breadth,
depth, retention and trend are computed.

If you have [PostHog's own hosted MCP server](skills/usage/posthog.md)
connected, Claude can query it directly — your server, your credentials,
outside this plugin. strip-down ships no analytics server and holds no keys.

## What it doesn't do

Stated plainly, because a tool whose job is finding things to delete should be
held to its limits:

- **It makes no removal recommendations.** The seven kill gates that should
  precede one — dormancy across a full seasonal cycle, dependencies, contracts,
  revenue concentration, regulatory/accessibility class, instrumentation,
  migration path — are v0.3. Until they exist, a cut recommendation would be
  irresponsible.
- **It deletes nothing**, and opens no pull request that does.
- **It makes no retention claims.** I looked for a published case of feature
  removal improving retention and did not find one. The honest pitch is that
  most products can't tell you which features are earning their cost — not that
  deleting things grows your numbers. ([the search](docs/PLAN.md#1-there-is-no-evidence-that-removing-features-improves-retention))
- **It can't tell a discovery problem from a value problem on its own.** That
  needs awareness data, and no event stream contains it. You have to ask people.
- **It can't see churned users.** A feature whose absence drove people away
  leaves no trace in any export.
- **The scan is regex over text.** It misses dynamically registered routes and
  flags read from a database, and can't distinguish a live call site from a dead
  one. The inventory is a draft for a human to correct, and
  [reference.md](skills/inventory/reference.md) lists the failure modes to check.

## Privacy

`inventory`, `cost` and `usage` make **no network calls**. The plugin declares
no credentials, ships no MCP server, and has nothing to leak. Aggregate CSVs
contain no user identifiers and are the documented default. Feature names, event
names and usage figures never go into a web search. Full detail, including why
first-party analytics adapters are last on the roadmap rather than first, in
[PRIVACY.md](PRIVACY.md).

## Roadmap

| | |
|---|---|
| **v0.1** ✅ | `init`, `inventory`, `cost` — fully offline |
| **v0.2** ✅ | `usage` — CSV first, PostHog via your own MCP server |
| v0.3 | `verdict` (five buckets), the seven kill gates, a `red-team` agent that argues against every recommendation, `sunset` plan generation |
| v0.4 | `demand` — scope diff for pre-PMF products, cited competitor matrix, strict evidence grading |
| v0.5 | `survey`, `amnesty`, more stack heuristics, and only if genuinely needed, first-party Amplitude/Mixpanel MCP adapters |

Out of scope, possibly forever: automated code deletion, feature-level revenue
attribution, retention-lift predictions, and scraping any source whose terms
prohibit it.

## Development

```bash
python3 tests/test_stripdown.py
```

52 tests, standard library only, no setup. They build a throwaway git
repository with controlled history so the cost metrics are verified rather than
assumed.

```bash
claude plugin validate --strict .
```

The scripts are usable on their own, without Claude:

```bash
python3 scripts/scan_signals.py --names event
python3 scripts/cost_report.py --months 12 --json
python3 scripts/usage_report.py --aggregate export.csv
python3 scripts/validate_inventory.py --strict
```

## Contributing

Disagreements with the honesty section are the most welcome kind. In
particular: if you have a counter-example to "no published evidence that
removing features improves retention," please open an issue — that's the claim
in here I'd most like to be wrong about.

The design, the research, the sources and the things that don't work are all in
[docs/PLAN.md](docs/PLAN.md).

MIT licensed.
