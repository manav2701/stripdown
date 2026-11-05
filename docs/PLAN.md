# strip-down

**A Claude Code plugin that helps you find the features you should stop paying for.**

Status: **v0.1 through v0.4 are built and tested** (`init`, `inventory`, `cost`, `usage`, `verdict`, `sunset`, `survey`, `demand`) — see the [README](../README.md) to install and run them. Only v0.5 remains plan.

This document is the design, the research behind it, and an honest account of which parts of the idea work, which parts don't, and what we're doing about the parts that don't. Where the implementation has since settled a question the plan left open, the roadmap section says so.

---

## Table of contents

- [The one-paragraph version](#the-one-paragraph-version)
- [Why this needs to exist as a *Claude Code* plugin](#why-this-needs-to-exist-as-a-claude-code-plugin)
- [Research: what's actually known about feature bloat](#research-what-actually-known-about-feature-bloat)
- [Research: what the existing tools do and don't do](#research-what-the-existing-tools-do-and-dont-do)
- [The honest part: what doesn't work](#the-honest-part-what-doesnt-work)
- [Design](#design)
  - [The feature inventory is the whole product](#the-feature-inventory-is-the-whole-product)
  - [Four evidence axes](#four-evidence-axes)
  - [The verdict matrix](#the-verdict-matrix)
  - [Kill gates](#kill-gates)
  - [Two modes, and why Mode B ships first](#two-modes-and-why-mode-b-ships-first)
- [Plugin architecture](#plugin-architecture)
  - [Commands](#commands)
  - [What the plugin format actually allows](#what-the-plugin-format-actually-allows)
  - [Repository layout](#repository-layout)
  - [Skills, agents, and why no hooks](#skills-agents-and-why-no-hooks)
  - [Secrets and the MCP constraint](#secrets-and-the-mcp-constraint)
- [Data sources: what we can actually reach](#data-sources-what-we-can-actually-reach)
- [Privacy and safety](#privacy-and-safety)
- [Roadmap](#roadmap)
- [How we'll know it works](#how-well-know-it-works)
- [Prior art and credits](#prior-art-and-credits)
- [Sources](#sources)

---

## The one-paragraph version

Every product-analytics tool can tell you which of your *instrumented events* are quiet. None of them can tell you what's in your product that you never instrumented, what each feature costs you to keep, or whether a quiet feature is quiet because it's worthless or because nobody can find it. `strip-down` runs inside your repository, builds a feature inventory from the code itself, prices each feature from your git history, joins that against your analytics and your revenue, and produces a ranked, gated, cited list of removal candidates — plus the sunset plan for each one. It never deletes anything.

---

## Why this needs to exist as a *Claude Code* plugin

This is the part worth being precise about, because "AI product analytics" is a crowded, mostly worthless category. The reason to build this as a Claude Code plugin rather than a SaaS dashboard is specific:

**Claude Code is already sitting inside the codebase with shell access and git history.** That gives it three inputs no analytics vendor has:

1. **The true feature inventory.** Pendo, Amplitude, Mixpanel and PostHog only know about features someone remembered to instrument. The code knows about all of them — every route, nav entry, feature flag, entitlement check, settings toggle, API endpoint, background job and admin screen. The difference between those two sets is the single most useful artifact this tool produces, and it is currently nobody's product.
2. **Cost of carry, measured rather than guessed.** Every published feature-audit framework asks you to plot value against *effort* or *maintenance cost*, and every one of them sources that axis from a workshop where engineers guess. `git log` is a measurement: commits per feature path, distinct authors, churn, the share of commits that are bug fixes, the share of the test suite, dependency count, how much of your CI time it burns. That's a real cost axis, available offline, for free, in every repo.
3. **The dependency graph.** "What breaks if we remove this" is a static-analysis question, and a pre-flight check that every removal playbook lists and no analytics tool can answer.

So the thesis is: **the code is the missing half of the feature audit.** Analytics tells you what gets used. The repo tells you what exists and what it costs. The decision needs both, and only a tool inside the repo can join them.

---

## Research: what's actually known about feature bloat

I went looking for evidence, not opinions. Here's what holds up and what doesn't.

### What holds up

**Over-featured products get chosen and then regretted.** The one piece of peer-reviewed work here is Thompson, Hamilton & Rust, *"Feature Fatigue: When Product Capabilities Become Too Much of a Good Thing,"* Journal of Marketing Research 42(4), 2005. The mechanism they found: people weight capability heavily *before* use and usability heavily *after* use, so they systematically pick products more complex than the ones that would actually satisfy them. Their model shows that optimising feature count for initial choice overshoots and reduces customer lifetime value.

**Caveat, and it's a big one:** this is a 2005 study on consumer electronics purchase decisions, with a tech-skewed sample. It is *not* a study of SaaS retention, and it does not say that removing features from an existing product improves anything. Anyone citing it as "research proves feature bloat kills retention" is overreaching. We won't.

**Usage is heavily concentrated.** Pendo's 2019 Feature Adoption Report, across 615 subscriptions, found roughly 12% of features drive 80% of daily usage volume, and that about 80% of features are rarely or never used.

**Caveat:** vendor research; "feature" meant whatever each customer tagged, so the unit is inconsistent across products; and daily-volume measures structurally favour high-frequency features over genuinely occasional-but-important ones. The widely repeated "$29.5B wasted" figure is a derived estimate of spend on features that *may* go unused — not measured waste. We'll cite the concentration finding as directional, not as a law.

### The frameworks, and what they agree on

Across practitioner sources the playbook is remarkably consistent, and it's worth implementing rather than reinventing:

- **Usage data first, opinions second.** Start from telemetry, not from a meeting.
- **Plot value against maintenance cost.** The core 2x2. Features that have stopped returning get sunset or refactored.
- **Core / supporting / distraction buckets.** Cut distractions first.
- **The Subtraction Audit** (identify → evaluate → plan → execute) adds two good ideas: a blameless "feature amnesty" where anyone can name a thing they'd cut, and treating *features users routinely work around* as removal candidates.
- **Pre-flight checks before any cut:** is it genuinely dormant; who uses it and what do they pay; what depends on it; does a contract require it.
- **Sunsetting is a release-engineering task,** not an announcement: one named owner across product/eng/legal, audit trails on flag changes, support-ticket volume watched through the wind-down.
- **Treat every feature as a recurring cost** and re-review quarterly.

### Low adoption has two different causes, and they have opposite fixes

This is the part most "find your unused features" tooling gets wrong, and it's where the "features that could work if maneuvered better" half of the idea lives.

A quiet feature is either a **discoverability failure** (users would value it but don't know it exists or can't find it) or a **value failure** (they know about it and don't want it). Pendo's own framing asks exactly this question — are underused features not delivering value, or simply hard to find — and recommends in-app guides first, then a UI change, then removal. Their Keap case study is the clean example: team hypothesised discoverability, targeted non-adopters with a guide, usage jumped.

The behavioural signature differs:

| Signal | Reading |
|---|---|
| Low exposure, high repeat use among the few who find it | **Discoverability failure** → reposition, don't cut |
| High exposure, trial then abandonment | **Value failure** → cut candidate |
| Low exposure, low repeat | Ambiguous → needs an awareness survey |
| Low breadth, high depth, concentrated in paying accounts | **Working power-user feature** → leave alone |

Breadth (share of eligible users who tried it) and depth (repeat use, computed *only over adopters*, or it's diluted into meaninglessness) have to be read together. There's a widely-circulated heuristic that under 40% awareness implies discoverability and over 70% implies value — it's one blog's own cutoff with no validation behind it, so we'll surface it as a prompt, labelled, not as a threshold the tool acts on.

**The honest consequence:** the discoverability-vs-value split needs *awareness* data, and awareness cannot be derived from event streams. It requires asking people. So `strip-down` will generate the survey and tell you it can't answer it for you. The Value-Adoption Matrix approach makes the same point: analytics gives you the adoption axis, a survey gives you the perceived-value axis, and only the second one disambiguates.

---

## Research: what the existing tools do and don't do

| Tool | What it does | What it can't do |
|---|---|---|
| Pendo / Amplitude / Mixpanel / PostHog | Usage, funnels, retention, stickiness on **instrumented** events | See uninstrumented features; price maintenance; read contracts; see the dependency graph |
| Reflag / Flagsmith / Harness / Statsig stale-flag detection | Flag-level staleness (fully rolled out, code removed, checks not firing, untouched for N days) | Reason about *features*, only flags; most products' features aren't behind flags |
| Uber's Piranha | Automated code transform to strip stale flags | Decide *which* flags are stale — you must supply that list from elsewhere |
| Static dead-code analysis | Unused imports, variables, unreachable code | Contextual dead code behind flags or rare conditions; unused HTTP endpoints appear to have no established tooling at all |
| Avo / Segment Protocols | Compare live event schemas against a declared tracking plan | Compare either against the **code**; I found no tool that diffs a tracking plan against a code-level inventory of what exists |
| Existing Claude Code audit plugins (`code-audit`, `cc-plugins/audit`, `plugin-ops`, daymade's `product-analysis`) | Code quality, architecture, tech debt, complexity creep | None of them touch product usage data |

**The gap is real and it's specific:** nobody joins *what exists in the code* to *what gets used* to *what it costs to keep*. That join is the product.

---

## The honest part: what doesn't work

I'd rather lead with this than bury it.

### 1. There is no evidence that removing features improves retention

I went looking for a case study — anyone, Intercom, Basecamp, anyone — that removed features and measured a retention gain. **I did not find one.** What exists instead:

- Basecamp's most-cited simplification win was a *wording* change (dropping "projects"), not a feature cut.
- Intercom's published simplification work is principles, information-architecture restructuring and splitting into four products — all reported qualitatively, no retention numbers.
- Intercom's Help Center case study points the *other* way: deals were lost to missing features, and retention was higher for customers who created more content.

So the honest framing for this tool is **not** "removing features will grow your retention." It's: *every feature you keep has a measurable recurring cost in engineering time, test surface, support load, onboarding complexity and decision load, and most products cannot tell you which features are earning that cost.* `strip-down` makes the cost legible. The retention claim is unsupported and we won't make it.

### 2. "Look up what's in demand" is the weakest part of the original idea

The pre-users / MVP mode asked for: research the idea, find what's in demand and under-built, recommend cutting the rest. Three problems:

- **This is where an LLM is most likely to produce confident fiction.** "Markets want X" is exactly the shape of claim that generates fluent, unfalsifiable, useless output. Demand assertions without a fetched, citable source are worse than no output, because they're persuasive.
- **The good data sources are mostly closed.** See the data-source table below. Google Trends has no usable public API (official one is an application-only alpha since July 2025; `pytrends` is archived and 429s). Reddit's API is free only for non-commercial use with tightening pre-approval, and commercial use is a negotiated contract. G2 and Capterra reviews are the richest source of "what users wish this did" and both prohibit scraping; G2's own guidelines note reviews are subjective, incomplete, and solicited by vendors — sometimes with incentives tied to word count, which skews which products accumulate them.
- **A pre-PMF product with no users has nothing to strip.** The real failure mode of an MVP isn't bloat, it's *scope* — shipping six half-jobs instead of one whole one. That's a different analysis and it's answerable from the repo and the README alone.

**What we'll do instead:** Mode A doesn't claim to find demand. It does three things it can do honestly:
- **Scope diff** — extract the one job the product claims to do from its README/landing copy, enumerate everything in the code, and show what isn't on the single critical path. This is entirely local, verifiable, and genuinely useful.
- **Competitor feature matrix** from fetched public pricing and docs pages — verifiable, citable, legal.
- **Evidence-graded signals** from sources that are actually open (HN Algolia, GitHub issue search, app-store review RSS, public changelogs), where every claim carries its source URL and a grade, and uncited demand claims are refused outright.

### 3. "No analytics events" does not mean "not used"

It very often means "never instrumented." Treating instrumentation gaps as dead features is how you delete something a quiet, paying segment depends on. This is why blind spots get their own output bucket and are explicitly **not** cut candidates.

### 4. Low usage does not mean low value

Admin, compliance, data-export, audit-log, accessibility, security and billing features are frequently used by a handful of people, rarely, and are load-bearing — sometimes contractually or legally. A feature at 5–15% breadth with high depth among adopters can be entirely healthy. Published adoption "benchmarks" (core 30–60%, niche 5–20%) are uncited vendor numbers; there is no universal benchmark because adoption is feature-specific.

### 5. Churned users are invisible

Your analytics only contains people who stayed. The feature whose absence or brokenness drove people away leaves no trace. No amount of event analysis fixes this survivorship problem, and the tool will say so rather than pretend completeness.

### 6. The LLM cannot run the survey

Awareness, perceived value and willingness-to-pay require asking humans. `strip-down` generates instruments; it does not fabricate results.

### 7. Feature-level attribution of revenue is mostly fiction

"This feature drives $X" requires causal inference the data almost never supports. We'll report the defensible version — *revenue concentration*: what share of ARR sits in accounts that touch this feature, and how concentrated. That's a risk measure, not an attribution, and it's labelled as such.

---

## Design

### The feature inventory is the whole product

Everything else is a join against this table, so it gets built first and it gets a human in the loop.

`/strip-down:inventory` walks the repo and proposes features from structural evidence, which varies by stack but is enumerable:

- Router definitions and page files (Next.js/Remix/Rails/Django/Laravel route tables, file-based routing trees)
- Navigation and menu definitions, settings panels, tab registries
- Feature-flag and entitlement checks (`flags.`, `isEnabled`, plan/tier gates, LaunchDarkly/PostHog/Unleash/Flagsmith/GrowthBook SDK calls)
- HTTP/GraphQL/RPC endpoint registrations and resolver maps
- Background jobs, cron entries, queue workers, webhook handlers
- Database tables and migrations with no reader outside one module
- CLI subcommands, public exports, plugin hooks
- Analytics `track()` / `capture()` / `logEvent()` call sites — the *declared* surface, kept as a separate column

Output is `.stripdown/inventory.yml`: a human-editable, version-controlled file where each feature has an id, a human name, the paths that implement it, the events that measure it (if any), owner, and tags. **The tool proposes; the human corrects.** Automatic feature detection will be wrong — about granularity especially, since "feature" is a product concept and the code only has structural proxies. An inventory that's reviewed once and then maintained in git is worth more than a perfect-looking one that nobody trusts. It also fixes the "feature meant different things to different customers" problem that undermines cross-product adoption statistics: within *your* repo, the unit is explicit and stable.

A side effect worth naming: this file is the tracking-plan-to-code diff that doesn't currently exist as a product.

### Four evidence axes

Each feature in the inventory gets scored on four axes, each with a provenance label and a confidence level. Nothing is a single number, because a single number hides which axis is missing.

**1. Cost of carry** — local, offline, free, available on day one:
- Lines and files, and share of total codebase
- Commits touching it over the last N months; distinct authors; churn rate
- Share of its commits that are bug fixes (conventional-commit prefixes, revert density, hotfix patterns)
- Exclusive dependencies it drags in
- Test files and (where measurable) CI minutes attributable to it
- Open issues/PRs referencing its paths
- Bus factor: features with one author who has left are a specific kind of liability

**2. Usage** — needs analytics, honest about gaps:
- Exposure / breadth: eligible users who ever triggered it
- Depth: repeat use among adopters only
- Retained adoption: adopters still using it in the next period
- Trend over the last two quarters
- Time-to-first-use from signup
- **Blind spot flag** when the feature has no mapped events at all

**3. Revenue concentration** — the kill gate, not a score:
- Share of ARR in accounts that touch it
- Concentration: does one large account account for most of its use
- Plan-tier distribution: is it a stated selling point of a paid tier

**4. Demand / strategic fit** — the weakest axis, graded accordingly:
- On or off the single critical path for the product's stated job
- Competitor presence (fetched, cited)
- External signal (cited, graded)
- Workaround evidence: support tickets or issues where users describe routing around it — a documented removal signal

### The verdict matrix

`/strip-down:verdict` doesn't produce one list. It produces five buckets, because they imply five different actions:

| Bucket | Signature | Action |
|---|---|---|
| **Cut** | High cost, low breadth, low depth, no revenue concentration, passes all gates | Sunset plan |
| **Reposition** | Low exposure, *high* depth among adopters, or high cost but valuable | Fix discoverability/placement — this is the "could work if maneuvered better" bucket |
| **Keep** | Earning its cost, or load-bearing | Nothing |
| **Blind spot** | Exists in code, no events mapped | Instrument it or decide deliberately without data — **never** auto-cut |
| **Blocked** | Failed a kill gate | Explicit reason, revisit date |

Each recommendation carries: the evidence used, the evidence *missing*, a confidence level, and the cheapest next step that would raise that confidence. A recommendation with low confidence says so in the output rather than in a footnote.

### Kill gates

No feature reaches **Cut** without passing every gate. These come straight from the pre-flight checklists in the research, plus a few the research doesn't mention and should:

1. **Dormancy** — genuinely unused over a full seasonal cycle, not just a quiet month. Annual-cycle features (tax, renewals, reporting) look dead for eleven months.
2. **Dependency** — nothing in the codebase depends on it.
3. **Contractual** — not named in a contract, SLA, SOC2/ISO control, enterprise agreement or public API commitment. The tool can grep for the obvious; a human confirms.
4. **Revenue** — no material ARR concentration in its users.
5. **Regulatory / accessibility class** — data export, audit logging, accessibility affordances, consent management, security controls and account deletion are **never** cut on usage data alone. Hard rule, not a heuristic.
6. **Instrumentation** — it is actually measured. If it's a blind spot, it cannot be a cut.
7. **Migration** — there's a path for current users, or an explicit decision that there doesn't need to be.

A cut candidate that fails a gate goes to **Blocked** with the reason named. That's a feature of the output, not a failure of it.

### Two modes, and why Mode B ships first

**Mode B — you have users.** The defensible mode. Code inventory + git cost + analytics + revenue + gates. Everything above applies.

**Mode A — idea or MVP, no users.** The honest-but-narrower mode. No usage data exists, so this is a *scope* analysis, not a usage analysis:
- What single job does the product claim to do (from README, landing copy, pitch)?
- What's the shortest path through the product that delivers that job?
- What exists that isn't on that path?
- What does the cost axis say about what you've already spent on the off-path parts?
- Competitor matrix, cited.
- External demand signals, cited and graded, with uncited claims refused.

The original idea put Mode A first. Research says ship Mode B first: it has real data, a real gap in the market, and no hallucination surface. Mode A is the one most likely to generate plausible nonsense, so it ships last, with the strictest citation discipline, and with a clear statement in its own output that it is advisory and its demand claims are weak evidence.

---

## Plugin architecture

Deliberately small. Every command either produces a reviewable file or reads one. Nothing runs without being asked.

### Commands

These are implemented as **skills**, not legacy `commands/*.md` files — Anthropic's docs now direct new plugins to write slash-invokable workflows as skills. The plugin is named `strip-down`, so every skill is namespaced `/strip-down:<name>`.

| Command | Does |
|---|---|
| `/strip-down:init` | Detect stack, mode and available integrations; write `.stripdown/config.yml` |
| `/strip-down:inventory` | Build/refresh `.stripdown/inventory.yml` from the code; diff against the previous version |
| `/strip-down:cost` | Git-history and static cost-of-carry per feature |
| `/strip-down:usage` | Pull per-feature usage from the configured analytics source; report blind spots loudly |
| `/strip-down:demand` | Evidence-graded external research; refuses uncited claims |
| `/strip-down:verdict` | The five buckets, gated, with confidence and missing-evidence notes |
| `/strip-down:sunset <feature>` | Generate a sunset plan: owner, comms draft, flag strategy, migration, metrics to watch, rollback trigger, deletion date. **Generates a plan. Does not delete code.** |
| `/strip-down:survey` | Generate the awareness/perceived-value survey the event data can't replace |
| `/strip-down:amnesty` | Run the blameless "what would you cut" prompt with the team, and fold answers into the inventory as hypotheses |

### What the plugin format actually allows

I researched the plugin system before designing around it, and four constraints landed hard enough to change the plan. Worth stating plainly, because they're the kind of thing you'd otherwise discover after building the wrong thing.

**1. A plugin cannot pre-approve web access.** `WebFetch` and `WebSearch` are Claude Code built-ins, not something a plugin can provide, and they need user approval by default — `WebFetch` is exempt only for a built-in list of documentation domains. Approval is granted per repository and per domain. Of a plugin's own `settings.json`, only `agent` and `subagentStatusLine` take effect; every other key is dropped, so a plugin cannot ship permission rules. The only lever is a skill's `allowed-tools`, which pre-approves tools *for the turn that invoked that skill*.

*Consequence for us:* Mode A (demand research) will prompt the user for each new domain the first time. That's correct behaviour for a tool fetching arbitrary third-party pages, and we'll document it as expected rather than fight it. The `demand` skill will declare a narrow `allowed-tools` and batch its fetches so the user approves a small, predictable set rather than a drip of prompts. Modes that matter most (inventory, cost) need no network at all.

**2. Sensitive config values cannot reach a skill.** `userConfig` lets a plugin declare config the install dialog prompts for, and `sensitive: true` values go to the platform's secure store. But sensitive values are **not** substituted into skill or agent Markdown — they stay placeholders. They resolve only in MCP server config (`env`, `url`, `headers`), LSP config, and exec-form hook args (as `CLAUDE_PLUGIN_OPTION_<KEY>`). Plugin path variables and those option env vars are also *not* present in the environment of plain Bash-tool commands.

*Consequence for us:* a "skill that calls the Amplitude API with your key" is not buildable. An analytics adapter that needs a secret has to be an MCP server. This is the single biggest design change the research forced, and it's detailed below.

**3. Local stdio MCP servers and `bin/` don't run everywhere.** They work in the CLI but not on claude.ai or in Cowork; cross-surface reach needs a remote MCP server declared by https URL.

*Consequence for us:* the offline core (inventory, cost) works everywhere because it only needs Bash and Read. Analytics adapters are CLI-first, and we'll say so rather than implying universal support.

**4. Plugin hooks, monitors and MCP servers run outside the sandbox with the user's full privileges**, and Anthropic's own security page tells users to review plugin code before installing. For a plugin that reads a company's product analytics, that warning is pointed at us. It's the main reason this is open source, the reason we ship no hooks, and the reason the offline tier needs no credentials at all.

### Repository layout

Single-plugin repo, published as its own marketplace so `claude plugin marketplace add manav2701/stripdown` is all a user needs:

```
stripdown/
├── .claude-plugin/
│   ├── plugin.json          # name: "strip-down"  (only `name` is actually required)
│   └── marketplace.json     # one entry, "source": "./"
├── skills/
│   ├── init/SKILL.md            # v0.1, shipped
│   ├── inventory/SKILL.md       # v0.1, shipped (+ reference.md, schema.md)
│   ├── cost/SKILL.md            # v0.1, shipped
│   ├── usage/SKILL.md           # v0.2, shipped (+ csv-schema.md, posthog.md)
│   ├── verdict/SKILL.md         # v0.3
│   ├── sunset/SKILL.md          # v0.3
│   ├── demand/SKILL.md          # v0.4
│   ├── survey/SKILL.md          # v0.5
│   └── amnesty/SKILL.md         # v0.5
├── lib/                         # sdyaml.py, inv.py  (stdlib only)
├── scripts/                     # detect_stack, scan_signals, cost_report,
│                                # usage_report, validate_inventory
├── tests/                       # stdlib unittest + a fixture app
├── agents/                      # v0.3+
│   ├── feature-cartographer.md
│   ├── cost-accountant.md
│   ├── demand-researcher.md
│   └── red-team.md
├── evals/                       # v0.3: eval cases with mocked analytics
├── PRIVACY.md  README.md  LICENSE
```

As built, v0.1 and v0.2 need no `.mcp.json` at all: the analytics tier reads a
CSV the user exports, or uses the user's own PostHog MCP server. That was the
plan's third tier and it turned out to be sufficient, so no first-party
credential handling exists yet.

Notes we'll have to respect: only `plugin.json` goes inside `.claude-plugin/` (components placed there don't load); a `CLAUDE.md` at plugin root is *not* loaded, so plugin-wide instructions belong in a skill; and once published the plugin name can never change. The marketplace entry name must equal the `plugin.json` name or install fails. `version` must be bumped every release or updates report "already at the latest version". Auto-update is off by default for third-party marketplaces, so release notes matter.

State and caches go in `${CLAUDE_PLUGIN_DATA}` (persistent across updates), never in `${CLAUDE_PLUGIN_ROOT}`, which changes per version. Analytics query results get cached there — PostHog's MCP tool calls share their REST rate limits and some tools bill as PostHog AI spend, so re-querying on every run would be both slow and rude.

### Skills, agents, and why no hooks

**Skills** carry the reusable knowledge and are the user-facing surface: per-stack inventory heuristics, the scoring rubric, the sunset playbook, the survey instruments, and the citation-grading rules. Detail goes in linked `reference.md` files rather than one long `SKILL.md` — skills should stay under ~500 lines, with Claude loading the references only because the skill tells it to. Scripts under `scripts/` are executed, not read into context, which is the right home for git-archaeology work. Skill `description` text is what determines whether the skill fires on natural phrasing, and the docs name a weak description as the most common eval failure, so descriptions get written and tested deliberately rather than as an afterthought.

**Agents** exist where isolated context or restricted tools genuinely help:
- `feature-cartographer` — inventory extraction, per-stack heuristics; large, noisy reads kept out of the main thread
- `cost-accountant` — git archaeology, same reason
- `demand-researcher` — external evidence gathering under citation rules, with a deliberately narrow tool set
- `red-team` — adversarially argues *against* every cut recommendation and tries to name the user who'd be hurt. This is the honesty mechanism, and it exists because a tool whose whole job is finding things to delete will, left alone, find things to delete. Isolating it means it argues from the evidence rather than from the enthusiasm of the thread that produced the recommendation.

Worth knowing: plugin agents silently ignore `hooks`, `mcpServers`, `permissionMode` and `initialPrompt` in their frontmatter, so none of our safety properties can live there.

**Hooks: none.** The workflow is human-invoked and review-gated end to end, plugin hooks register the moment the plugin loads rather than when a skill runs, and they execute outside the sandbox with full user privileges. Shipping hooks here would add risk and surprise to buy nothing. If someone later wants a `PostToolUse` nudge when a feature directory grows, that belongs in their own config, not in this plugin.

### Secrets and the MCP constraint

Because sensitive `userConfig` can't reach skill text, the analytics tier has three tiers of its own, ordered by how little trust they ask for:

1. **CSV / SQL import (no credentials).** You export per-feature metrics yourself; the skill reads a local file. Zero secrets, works on every surface, privacy-safest, and it is the *documented default*. Ugly, honest, and sufficient.
2. **PostHog's own hosted MCP server** (`https://mcp.posthog.com/mcp`, installable with `npx @posthog/wizard mcp add`). The user configures it themselves, with their own credentials, outside our plugin. It already exposes trends, funnels, retention, paths, stickiness, lifecycle and `execute-sql`/HogQL — exactly the query surface we need, maintained by the vendor. We ship a skill that knows how to *use* those tools, and hold no key. This is the recommended path and it is deliberately not ours.
3. **Our own stdio MCP adapters for Amplitude and Mixpanel**, only if tiers 1 and 2 prove insufficient. These would declare `userConfig` with `sensitive: true` and reference `${user_config.KEY}` in the server's `env` — the only sanctioned route for a secret. CLI-only, aggregate queries only, read-only scopes documented, and the server code deliberately small enough to audit in one sitting, because we're asking people to hand a plugin their analytics credentials.

Tool names from a plugin MCP server are `mcp__plugin_strip-down_<server>__<tool>` (with non-alphanumerics replaced by `_`), which matters for anyone writing their own permission rules around us.

## Data sources: what we can actually reach

Being concrete about this up front prevents designing around a source that turns out to be closed.

| Source | Status | Verdict |
|---|---|---|
| **Your git history** | Local, free, complete | **Primary.** Most underused signal in this space |
| **Your codebase** | Local, free, complete | **Primary** |
| **PostHog** | Free hosted MCP server; full query surface; shares REST rate limits; some tools bill as AI spend | **Primary analytics adapter** |
| **Amplitude / Mixpanel** | Documented APIs, user-supplied key; both require explicit `track()` instrumentation, so cleaner data but more gaps | Adapter, BYO key |
| **Warehouse / raw SQL / CSV** | Fully under user control | Universal fallback, and the privacy-safest path |
| **HN Algolia** (`hn.algolia.com/api/v1/`) | Free, no auth; ~10k req/hr per IP per third-party reports; an undocumented result-count cap exists | Usable for demand signal |
| **GitHub issue/PR search** | Available in-session | Usable, especially for workaround evidence |
| **App Store / Play review feeds** | Public RSS/JSON | Usable where the product is a mobile app |
| **Competitor pricing & docs pages** | Public, fetchable, citable | Usable — the backbone of the competitor matrix |
| **Google Trends** | Official API application-only alpha since Jul 2025, no production guarantees; `pytrends` archived and 429s | **Not usable.** Don't design around it |
| **Reddit** | Free only for non-commercial use (~100 QPM); pre-approval tightening under the Nov 2025 Responsible Builder Policy; commercial access is a negotiated contract; sources conflict on whether the public API closes in late 2026 or 2027 | **Not usable** for a tool others run commercially. Document manual-export path instead |
| **G2 / Capterra / TrustRadius** | Richest "I wish it did X" corpus; scraping prohibited; reviews solicited and incentivised, so skewed | **Not scraped.** Support manual paste/export, and treat as low-grade evidence when used |

Every external claim in `strip-down`'s output carries a source URL and an evidence grade:

- **A** — your own data (code, git, analytics, revenue)
- **B** — primary public source fetched this run (competitor pricing page, changelog, docs)
- **C** — public discussion (HN, GitHub issues, app reviews), cited
- **D** — model inference with no source. **Never used to justify a cut.** Rendered as a question, not a finding.

---

## Privacy and safety

A tool that reads product analytics is reading data about real people, and a tool that recommends deletions can do real damage. Non-negotiables:

- **Aggregate only.** Query for counts, rates and cohort sizes. Never pull user-level event rows, emails, names or IDs into the session.
- **Read-only credentials.** Documented as read-only scopes; the plugin never needs write access to your analytics.
- **Nothing proprietary leaves the session.** Feature names, event names, code and usage numbers are never put into a web search or fetched URL. The demand researcher works from the product's *public* description only. This is a hard boundary in the skill instructions, because leaking an unreleased feature name into a search query is a realistic and serious failure.
- **No credentials in the repo.** Keys come from the environment or the user's own MCP config; `.stripdown/` holds no secrets and the plugin will say so in its generated `.gitignore` guidance.
- **Never deletes code.** No command removes a feature, and `sunset` produces a document. Deletion stays a human action behind human review. The plugin will not open a PR that strips a feature.
- **Recommendations are gated and reversible.** Every sunset plan includes a rollback trigger and the metrics that should abort it.

---

## Roadmap

Sequenced so that each version is useful on its own, and the trustworthy parts ship before the speculative ones.

**v0.1 — Inventory and cost (fully offline)**
`init`, `inventory`, `cost`. No integrations, no network, no analytics. Output: a reviewed feature inventory with a measured cost-of-carry per feature, and the blind-spot list (features in code with no tracking calls). Useful to a team on its own, and it's the artifact no other tool produces.

**v0.2 — Usage join**
`usage`, reading CSV/SQL export first (no credentials, every surface), then PostHog via the user's own hosted MCP server. Breadth, depth, retained adoption, trend. Blind spots reported loudly. Deliberately no credential handling of our own in this version.

**v0.3 — Verdict, gates and sunset**
`verdict` with the five buckets, all seven kill gates, the `red-team` agent, and `sunset` plan generation. This is the first version that makes recommendations, and it doesn't ship before the gates do.

**v0.4 — Mode A (scope analysis)**
`demand` with strict citation grading, the competitor matrix, and the scope diff for pre-PMF products.

**v0.5 — Breadth**
More stack heuristics, `survey`, `amnesty`, and — only if tiers 1 and 2 prove insufficient — first-party Amplitude/Mixpanel MCP adapters. Those are last on purpose: they're the only component that would hold a user's credentials, and they don't get built until the rest has earned the trust to ask.

**Explicitly out of scope, possibly forever:** automated code deletion, feature-level revenue attribution, retention-lift predictions, and anything that scrapes a source whose terms prohibit it.

---

## How we'll know it works

Worth deciding before building, so we can't move the goalposts:

1. **Inventory precision/recall.** Run `inventory` on open-source products with known feature sets; a maintainer reviews. Target: the inventory needs editing, not rewriting.
2. **Blind-spot discovery.** On a repo with real analytics, does it surface features the team didn't know were untracked? If yes, v0.1 already pays for itself.
3. **Does the red-team agent actually bite?** If it never blocks a recommendation, it's theatre. Track the block rate.
4. **Would a maintainer act on it?** The only outcome that matters. Measured by asking, on real repos, with real maintainers — not by a metric the tool computes about itself.
5. **False-cut rate.** Recommendations that a maintainer says would have broken something for someone. This is the number to minimise, and it should be published.

Mechanically, that's testable with the plugin tooling rather than by vibes. `claude plugin validate --strict` runs in CI. `claude plugin eval` runs real cases against fixture repositories, and critically it **mocks MCP tool calls** from files under `evals/mocks/<server>/<tool>.md` — so we can test the analytics adapters, including adversarial cases, without a live account or a real company's data. Eval also runs each case *without* the plugin loaded and reports the delta, which is the honest way to find out whether the plugin adds anything over asking Claude the same question unaided. If the delta is small on a case, that case's skill isn't earning its place.

The eval cases that matter most are the ones that should produce **no** recommendation: a feature with low usage but concentrated revenue, an annual-cycle feature in its quiet month, a compliance feature, a blind spot. A tool like this is worth more for what it refuses to suggest than for what it suggests. Note that eval is not a security review, and its own docs say so — a passing suite doesn't make the plugin safe to hand credentials to. Code review does.

---

## Prior art and credits

This plan borrows liberally and tries to say from whom. The Subtraction Audit's four stages and feature-amnesty idea; the value-vs-cost matrix common to most practitioner writing; Pendo's discoverability-vs-value question and their adoption-report concentration finding; the Value-Adoption Matrix's insight that the value axis has to come from a survey; breadth/depth/retained-adoption definitions from the feature-adoption literature; pre-flight removal checklists from the featurebloat FAQ; the release-engineering framing of sunsets from the feature-flag playbooks; Uber's Piranha for showing that the hard part is deciding *which* flags are stale, not removing them; and Thompson, Hamilton & Rust for the only peer-reviewed grounding in the area, with its scope limits acknowledged.

Contributions, and especially disagreements with the honesty section, are welcome. If you have a counter-example to "no published evidence that removing features improves retention," please open an issue — that's the claim in here I'd most like to be wrong about.

Licence: to be decided before first release (MIT unless there's a reason not to).

---

## Sources

**Research and frameworks**
- Thompson, Hamilton & Rust, "Feature Fatigue: When Product Capabilities Become Too Much of a Good Thing," *JMR* 42(4), 2005 — [record](https://www.econbiz.de/Record/feature-fatigue-when-product-capabilities-become-too-much-of-a-good-thing/10006642901), [summary](https://acawiki.org/Feature_Fatigue:_When_Product_Capabilities_Become_Too_Much_of_a_Good_Thing), [popular coverage](https://www.cbsnews.com/news/feature-fatigue-hits-gadget-users)
- [The Subtraction Audit: A Framework for Removing Features](https://theproductmanagersjournal.com/2025/05/22/the-subtraction-audit-a-framework-for-removing-features/)
- [Stop maintaining dead code: A practical guide to sunsetting features](https://www.devprojournal.com/software-development-trends/business-best-practices/stop-maintaining-dead-code-a-practical-guide-to-sunsetting-features/)
- [Feature Bloat FAQ: Definitions, Causes, Fixes](https://featurebloat.com/faq)
- [Feature Bloat: The Silent Product Killer](https://sonin.agency/insights/feature-bloat-the-silent-product-killer/)
- [What is Feature Bloat? Causes, Risks, and How to Prevent It](https://hellopm.co/what-is-feature-bloat/)
- [Sunsetting features gracefully: a feature-flag playbook](https://toggle.top/sunsetting-features-gracefully-a-release-playbook-inspired-b)
- [SaaS Feature Factory: Why More Features Kill Retention](https://saasfractionalcpo.com/blog/escaping-the-feature-factory/)

**Adoption measurement**
- [Pendo: The 2019 Feature Adoption Report](https://www.pendo.io/resources/the-2019-feature-adoption-report/) · [What is Feature Adoption?](https://www.pendo.io/glossary/feature-adoption/) · [The path to increasing product adoption](https://www.pendo.io/resources/the-path-to-product-adoption/) · [Keap case study](https://www.pendo.io/customers/keap-used-in-app-announcements-to-increase-feature-adoption-10x/)
- [Critique of the 80% statistic's methodology](https://swkhan.medium.com/youre-focusing-on-the-wrong-product-development-bottleneck-8ee207b28a7d)
- [How to measure feature adoption (breadth vs depth)](https://ooligo.com/en/learn/feature-adoption-rate/) · [How to Measure Feature Adoption Rate](https://userorbit.com/blog/how-to-measure-feature-adoption-rate) · [Feature Adoption Rate Playbook](https://umbrex.com/resources/company-analysis/product-management/feature-adoption-rate/) · [Feature Adoption Rate: Definition, Formula & SQL](https://www.metabase.com/metrics/feature-adoption-rate) · [Advanced feature adoption](https://www.chameleon.io/blog/advanced-feature-adoption)
- [Discoverability vs value failure](https://www.saasfactor.co/blogs/how-to-measure-feature-adoption-in-saas-key-metrics-for-success)
- [Value-Adoption Matrix](https://www.opinionx.co/blog/value-adoption-matrix)

**Tooling landscape**
- [PostHog MCP](https://posthog.com/mcp) · [Product analytics over MCP](https://posthog.com/docs/product-analytics/surfaces/mcp) · [Build insights with MCP](https://posthog.com/docs/product-analytics/build-insights-mcp) · [MCP FAQ and advanced setup](https://posthog.com/docs/model-context-protocol/faq)
- [Reflag stale flag detection](https://reflag.com/changelog/stale-flag-detection) · [Flagsmith stale flags](https://docs.flagsmith.com/managing-flags/stale-flags) · [Automated feature flag cleanup](https://reflag.com/blog/automated-feature-flag-cleanup) · [Feature flag cleanup tools](https://flagshark.com/blog/best-feature-flag-cleanup-tools-2026/)
- [What Is Dead Code? limits of static analysis](https://axify.io/blog/dead-code)
- [Avo tracking plan audit rules](https://www.avo.app/docs/audit/rules) · [Avo + Segment integration](https://www.avo.app/integrations/segment) · [Avo destination in Segment](https://segment.com/docs/connections/destinations/catalog/actions-avo/) · [Event taxonomy that won't rot](https://www.digitalapplied.com/blog/product-analytics-event-taxonomy-tracking-plan-2026)
- Existing Claude Code audit plugins: [code-audit](https://github.com/SeanWeldon/code-audit) · [product-analysis skill](https://claudemarketplaces.com/skills/daymade/claude-code-skills/product-analysis) · [plugin-ops](https://claudepluginhub.com/plugins/ivintik-plugin-ops)

**Data source availability**
- [Google opens alpha testing for new Trends API](https://ppc.land/google-opens-alpha-testing-for-new-trends-api-targeting-developers-and-journalists/) · [pytrends is archived](https://dev.to/rimulabs/pytrends-is-archived-how-to-migrate-your-google-trends-code-no-more-429s-4e63) · [pytrends is dead](https://apiserpent.com/blog/pytrends-dead-google-trends-data-2026)
- [Reddit API pricing and limits](https://www.xpoz.ai/blog/guides/reddit-api-pricing-tiers-and-alternatives/) · [Reddit API in 2026](https://www.socialcrawl.dev/blog/reddit-data-api-2026) · [Reddit API controversy](https://en.wikipedia.org/wiki/Reddit_API_controversy)
- [HN Algolia API guide](https://dev.to/agenthustler/scraping-hacker-news-in-2026-complete-guide-algolia-api-date-filters-3iep) · [Firebase vs Algolia HN APIs](https://dev.to/odeeb/hacker-news-firebase-api-vs-algolia-which-one-to-use-3g2n) · [undocumented result cap](https://github.com/algolia/hn-search/issues/230)
- [G2 Community Guidelines](https://legal.g2.com/community-guidelines) · [Mining G2 and Capterra reviews](https://userconcern.com/blog/g2-capterra-reviews-pain-points) · [Review-site mining](https://linkeddit.com/blog/review-site-mining-g2-capterra-trustradius)

**Claude Code plugin platform**
- [Create a plugin](https://code.claude.com/docs/en/plugins/create.md) · [Manifest reference](https://code.claude.com/docs/en/plugins/manifest-reference.md) · [Components](https://code.claude.com/docs/en/plugins/components.md) · [Marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference.md) · [Create a marketplace](https://code.claude.com/docs/en/plugins/create-marketplace.md) · [Install](https://code.claude.com/docs/en/plugins/install.md) · [Publish](https://code.claude.com/docs/en/plugins/publish.md) · [Plugin security](https://code.claude.com/docs/en/plugins/security.md)
- [Skills](https://code.claude.com/docs/en/skills.md) · [Subagents](https://code.claude.com/docs/en/sub-agents.md) · [Hooks](https://code.claude.com/docs/en/hooks.md) · [MCP](https://code.claude.com/docs/en/mcp.md) · [Permissions](https://code.claude.com/docs/en/permissions.md) · [Plugin evals](https://code.claude.com/docs/en/plugin-evals.md)

**Counter-evidence searched for and not found**
- Searched for a published case of feature removal improving retention; found [Basecamp's Jason Fried on product strategy](https://www.intercom.com/blog/podcasts/podcast-jason-fried-product-strategy/), [Intercom's product principles](https://www.intercom.com/blog/podcasts/intercoms-product-principles-back-to-the-basics), [Intercom's IA restructuring](https://www.intercom.com/blog/designing-for-clarity-restructuring-intercoms-information-architecture) and [Intercom Help Center case study](https://neilod.com/intercom-help-center-case-study) — none report a measured retention gain from removal.
