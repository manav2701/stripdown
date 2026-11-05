# Usage CSV formats

Two shapes. Prefer the first: it contains no user identifiers.

## 1. Aggregate (`--aggregate`)

One row per feature or per event. Headers are case-insensitive and `-`/`_`/
space are interchangeable.

```csv
event,eligible_users,adopters,repeat_adopters,retained_adopters,uses
checkout_started,4820,1960,1310,1180,18422
invoice_downloaded,4820,340,201,180,1290
report_viewed,4820,190,160,150,3100
```

| Column | Required | Meaning |
|---|---|---|
| `event` or `feature_id` | yes | joins to the inventory's `events`, or its `id` |
| `eligible_users` | for rates | users who *could* have used it. Not "all users" — exclude anyone the feature is not available to |
| `adopters` | yes | distinct users who used it at least once in the window |
| `repeat_adopters` | for depth | adopters who used it at least twice |
| `retained_adopters` | optional | adopters still using it in the following period |
| `uses` | optional | total occurrences |

Aliases accepted: `feature`, `event_name`; `eligible`, `exposed_users`,
`exposed`; `users`, `unique_users`; `repeat_users`, `repeat`; `retained`;
`events`, `event_count`, `count`.

Rows that contradict themselves (`adopters > eligible_users`, or
`repeat_adopters > adopters`) are rejected rather than silently clamped.

`eligible_users` is the number most often got wrong. If a feature is on an
enterprise tier, eligible users are enterprise users, not everyone — otherwise
breadth is understated and a healthy feature looks dead.

### PostHog (HogQL)

```sql
SELECT
  event,
  count(DISTINCT person_id) AS adopters,
  countIf(uses >= 2)        AS repeat_adopters,
  sum(uses)                 AS uses
FROM (
  SELECT event, person_id, count() AS uses
  FROM events
  WHERE timestamp >= now() - INTERVAL 90 DAY
  GROUP BY event, person_id
)
GROUP BY event
ORDER BY adopters DESC
```

Then add an `eligible_users` column yourself — PostHog will not know which
users each feature was available to.

### Amplitude / Mixpanel

Export an Event Segmentation / Insights report with **unique users** and
**total events** per event name over your window, as CSV. Amplitude and
Mixpanel both need explicit `track()` instrumentation, so the export covers
only instrumented features — which is exactly why the inventory's blind-spot
list is computed from the code instead.

## 2. Event-level (`--events`)

One row per occurrence. Breadth, depth, retention and trend are computed; the
window is split at its midpoint for retention and trend.

```csv
user_id,event,timestamp,account_id
u_8812,checkout_started,2026-09-02T10:14:00Z,acct_221
u_8812,checkout_started,2026-10-19T08:02:00Z,acct_221
u_4410,report_viewed,2026-09-03T11:40:00Z,acct_907
```

| Column | Required | Aliases |
|---|---|---|
| user id | yes | `user_id`, `distinct_id`, `user`, `person_id` |
| event | yes | `event`, `event_name`, `name` |
| timestamp | for retention/trend | `timestamp`, `time`, `ts`, `occurred_at`, `created_at` |
| account id | for revenue | `account_id`, `org_id`, `company_id`, `team_id` |

ISO 8601, `YYYY-MM-DD`, and unix seconds or milliseconds are all accepted.

**Pass `--eligible N`.** Without it, breadth is computed against the distinct
users present in the file — an *active-user* denominator, not an eligible-user
one, which overstates breadth. The report says so in its caveats, but supplying
the real number is better.

Use pseudonymous ids. Nothing here needs an email address or a name, and the
report never prints individual users.

## 3. Revenue (`--revenue`, optional)

```csv
account_id,arr
acct_221,48000
acct_907,1200
```

Joins to `account_id` in the event-level file. Produces `arr_touching` (ARR in
accounts that touch the feature) and `top_account_arr_share_pct` (how much of
that sits in one account).

This is **concentration, not attribution**. It does not say the feature earns
that revenue; it says that much revenue would be affected if it changed. That
is a risk measure, and feature-level revenue attribution is not something this
data can support. `mrr`, `revenue` and `value` are accepted as aliases.
