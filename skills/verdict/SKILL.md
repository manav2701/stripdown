---
description: Decide what to do about each feature - sort them into cut, reposition, keep, blind-spot and blocked, with the seven kill gates applied and the missing evidence named. Use when asked which features to remove or strip down, what to cut, which features are not worth keeping, or for the recommendation stage of a feature audit.
when_to_use: The user asks what to cut or remove, wants removal candidates, asks which features are not earning their keep, or has run /strip-down:inventory, :cost and :usage and wants the conclusion.
argument-hint: "[usage.csv]"
allowed-tools:
  - Bash(python3 *)
  - Read
---

# strip-down: verdict

Join inventory, cost and usage; apply the seven kill gates; sort every feature
into one of five buckets. This is the first strip-down command that
recommends anything, so it is built to recommend as little as it honestly can.

Needs `/strip-down:inventory`. Usage data is required for any judgment at all —
without it every feature lands in `blind-spot`, which is the correct answer.

## Run it

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verdict_report.py" --aggregate usage.csv --window-days 400 --revenue accounts.csv
```

It runs `cost_report.py` and `usage_report.py` itself, so pass whichever usage
flags apply (`--aggregate` / `--events` / `--revenue` / `--eligible` /
`--window-days`). Reuse saved runs with `--cost-json` and `--usage-json`.

## The five buckets

| Bucket | Means | What to do |
|---|---|---|
| `cut` | every gate passed | a human decides; draft with `/strip-down:sunset` |
| `reposition` | few found it, those who did kept using it | fix placement, do not remove |
| `keep` | in ordinary use | nothing |
| `blind-spot` | nothing measures it | instrument it, or decide deliberately without data |
| `blocked` | would be a cut, but a gate failed or is unanswered | the gate is named |

**`blocked` is the output working, not failing.** Three gates rest on facts
only a human has, so a fresh inventory blocks everything. Say that plainly
instead of apologising for it or working around it.

## The seven gates

1. **instrumentation** — is it actually measured? A blind spot cannot be cut.
2. **dormancy** — unused across a *full seasonal cycle*. A window under a year
   fails this gate, because annual features (tax, renewals, reporting) look
   dead for eleven months. A feature with live users also fails: removing it is
   a product decision with a migration plan, not a usage threshold.
3. **dependency** — does anything statically import it? A pass means "no static
   import crosses this boundary", which is weaker than "nothing depends on it";
   dynamic requires, DI containers, autoloading, shared tables and HTTP callers
   are invisible. Quote that limit rather than implying a clean bill of health.
4. **regulatory** — audit logs, data export, account deletion, consent,
   accessibility, SSO, encryption, invoices and tax records are never removed on
   usage evidence alone. A name that looks regulated requires an explicit
   `regulated: no` *plus* a written reason in `notes`.
5. **contractual** — named in a contract, SLA or public API? Absence of
   evidence in the repo is not evidence of absence: contracts usually are not
   in the repository.
6. **revenue** — how much ARR sits in accounts that touch it, and is it
   concentrated in one of them. A rarely used feature can be load-bearing for
   your largest customer.
7. **migration** — is there a path for current users, or is there nobody to
   migrate?

## Reporting it

Lead with the bucket counts, then go bucket by bucket. For each row give the
reason, the confidence, the **missing evidence**, and the cheapest next step.

Rules for the prose, all of which exist because they are the ways this output
gets misread:

- **`cut` means "a human should now decide", not "safe to delete".** Never
  write "you can remove these".
- **Spawn the `red-team` agent on every `cut` row before presenting it**, with
  `@agent-strip-down:red-team`. Its job is to find the user who would be hurt.
  If it finds one, say so in the same breath as the recommendation; a cut that
  survives an argument is worth more than one that was never challenged.
- **Respect `urgency`.** A `cut` row with low urgency is cheap to keep; removing
  it costs engineering time and carries its own risk. Do not present a free
  feature as a win.
- **Never merge `blind-spot` into "unused".** One is unmeasured, the other
  ambiguous.
- **Say once, plainly, that churned users are in no export**, so a feature
  whose absence drove people away leaves no trace in any of this.
- **Make no retention claim.** There is no published evidence that removing
  features improves retention. The case for removal is the cost you stop
  paying.
