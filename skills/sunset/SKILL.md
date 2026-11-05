---
description: Draft a sunset plan for one feature - owner, dependencies, flag strategy, migration path, comms, metrics to watch, abort triggers and a dated schedule. Use when a feature has been chosen for removal and the user asks how to retire, deprecate, sunset or phase it out safely.
when_to_use: The user has decided to remove a feature and wants a plan, asks how to deprecate or retire something safely, or has a cut candidate from /strip-down:verdict.
argument-hint: "<feature-id>"
allowed-tools:
  - Bash(python3 *)
  - Read
---

# strip-down: sunset

Draft a removal plan for one feature. **It writes a document. It changes no
code and deletes nothing.**

## Run it

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sunset_plan.py" <feature-id> --aggregate usage.csv --window-days 400 --revenue accounts.csv
```

Writes `.stripdown/sunset/<feature-id>.md`. Add `--stdout` to review without
writing, `--weeks N` to change the observation period before deletion
(default 6).

The script re-runs the verdict for that feature, so pass the same usage flags
you gave `/strip-down:verdict`.

## If the feature has not cleared its gates

The plan opens with the blockers instead of a schedule, and says so in its own
header. Do not reframe that as a plan to execute — relay the blockers and the
cheapest next step. A document that reads as approved when it is not is worse
than no document.

Drafting a plan for a blocked feature is still useful: it shows what clearing
the gates would require. Say which one you are doing.

## The shape of the plan, and why

- **Flag off first, delete last.** Nothing is removed until the feature has
  been provably off for a full observation period. Until the deletion step,
  reverting is a flag flip; after it, it is reverting one pull request. That
  ordering is the whole point.
- **One accountable owner plus three named reviewers** — product, engineering,
  and legal. The legal reviewer is required even when the contractual gate
  passed, because the repository is not where contracts live.
- **Abort triggers decided in advance**, not during an incident.
- **Support ticket volume is the earliest signal** that someone depended on it
  more than the data showed. Watch it through the whole wind-down.
- **An audit trail**: flag changes logged with who and when, the approving
  decision linked, the deletion commit recorded.

## After generating it

Tell the user the path, that it is a draft with `_TBD_` fields they must fill
in, and that it should be reviewed and committed alongside the inventory.

Then stop. Do not offer to execute the plan, open a pull request, remove the
code, or add the feature flag. None of those are this plugin's to do, and the
value of the ordering above is lost if the first step is taken by something
that cannot be held accountable for the last one.
