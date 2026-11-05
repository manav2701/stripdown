# `.stripdown/inventory.yml` schema

Hand-edited and committed to git. Validate with
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_inventory.py"`.

```yaml
version: 1                  # schema version, currently always 1
mode: has-users             # has-users | pre-users
features:
  - id: billing             # required. lowercase a-z 0-9 - _ , unique, stable
    name: Billing           # required in practice. the name a USER would use
    status: active          # active | deprecated | sunset-planned
    paths:                  # required. globs, repo-relative. ** is supported
      - app/billing/**
      - lib/stripe.ts
    events:                 # analytics events meaning "this feature was used"
      - checkout_started    # [] is valid and means "blind spot"
      - invoice_downloaded
    owner: payments         # free text: team or person. optional
    tags:                   # free text. optional
      - revenue
    gates:                  # human-asserted facts. NEVER inferred from code
      contractual: unknown  # yes | no | unknown
      regulated: unknown    # yes | no | unknown
      public_api: unknown   # yes | no | unknown
    notes: ''               # free text
```

## Field notes

**`id`** — stable across refreshes. Renaming one orphans its history in any
report you have already produced, so pick it once.

**`paths`** — a pattern with no wildcard also matches everything beneath it, so
`app/billing` behaves like `app/billing/**`. When a file matches more than one
feature, the pattern with the longest literal prefix wins and the overlap is
reported rather than silently resolved. Keep patterns disjoint where you can.

A feature whose paths match no files is an **error**, not a warning: either the
paths are wrong or the code is already gone, and both need a human.

**`events`** — the join key for `usage`. Two rules:
- an event belongs to at most one feature, or usage is double counted
- only map an event if firing it means the feature was *used*

An empty list is the honest answer when nothing measures the feature, and the
tooling reports that as `blind-spot` — an instrumentation gap, explicitly not
evidence of disuse and never a removal candidate.

**`gates`** — the three questions the code cannot answer:
- `contractual` — named in a customer contract, SLA or enterprise agreement?
- `regulated` — load-bearing for a regulation, audit, security or accessibility
  obligation? Data export, audit logs, consent management and account deletion
  are usually `yes`.
- `public_api` — part of a published API or integration surface others build on?

These exist so that a later version cannot propose removing something that is
legally or contractually required. `unknown` is a truthful default; a wrong
`no` is how this tool would do real damage.
