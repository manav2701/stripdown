#!/usr/bin/env python3
"""Draft a sunset plan for one feature. Writes a document; deletes nothing.

Sunsetting is a release-engineering task, not an announcement, so the plan is
shaped like one: a single named owner across product, engineering and legal; a
flag to turn it off before anything is deleted; a migration path; the metrics
that would abort it; and an audit trail.

If the feature has not cleared its gates, the plan opens with the blockers
instead of a schedule. A plan that reads as approved when it is not is worse
than no plan.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import gates as G  # noqa: E402
import inv  # noqa: E402

PASSTHROUGH = ("aggregate", "events", "revenue", "eligible", "window_days",
               "months", "cost_json", "usage_json", "seasonal_days")


def fetch_verdict(root, args):
    extra = ["--root", root, "--json"]
    for name in PASSTHROUGH:
        value = getattr(args, name, None)
        if value:
            extra += ["--%s" % name.replace("_", "-"), str(value)]
    if args.all_history:
        extra.append("--all-history")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "verdict_report.py")] + extra,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        inv.die("could not compute a verdict: %s" % (proc.stderr or "").strip())
    return json.loads(proc.stdout)


def fmt_date(base, days):
    return (base + datetime.timedelta(days=days)).strftime("%Y-%m-%d")


def render(feature, row, today, flag_prefix, weeks):
    fid = feature["id"]
    name = feature.get("name") or fid
    out = []
    w = out.append
    blockers = (row.get("gates_failed") or []) + (row.get("gates_unknown") or [])

    w("# Sunset plan: %s" % name)
    w("")
    w("- **Feature id:** `%s`" % fid)
    w("- **Drafted:** %s" % today.strftime("%Y-%m-%d"))
    w("- **Verdict bucket:** `%s`" % row.get("bucket"))
    w("- **Confidence:** %s" % row.get("confidence"))
    w("- **Status of this document:** DRAFT. Nothing here has been approved, "
      "and no code has been changed.")
    w("")

    if blockers:
        w("## Stop: this feature has not cleared its gates")
        w("")
        w("It is in the `%s` bucket, not `cut`. Do not schedule a removal. "
          "Resolve these first:" % row.get("bucket"))
        w("")
        for name_ in blockers:
            gate = (row.get("gates") or {}).get(name_, {})
            w("- **%s** — %s (`%s`)"
              % (name_, gate.get("because", "no reason recorded"),
                 gate.get("state")))
        w("")
        if row.get("cheapest_next_step"):
            w("Cheapest way forward: %s." % row["cheapest_next_step"])
            w("")
        w("The rest of this document is a template to fill in **after** the "
          "blockers are cleared, not a plan to execute now.")
        w("")
    else:
        w("## Gates")
        w("")
        w("All seven gates passed on the evidence available. That means "
          "\"no reason to stop was found\", not \"safe to delete\".")
        w("")

    w("## Evidence")
    w("")
    w("| | |")
    w("|---|---|")
    for label, key in (("Usage signature", "usage_signature"),
                       ("Adopters", "adopters"),
                       ("Breadth", "breadth_pct"),
                       ("Depth (adopters only)", "depth_pct"),
                       ("ARR share of users", "arr_share_pct"),
                       ("Cost index", "cost_index"),
                       ("Bug-fix ratio", "fix_ratio"),
                       ("Lines of code", "loc"),
                       ("Files", "files")):
        value = row.get(key)
        w("| %s | %s |" % (label, "unknown" if value is None else value))
    w("")
    if row.get("missing_evidence"):
        w("**Evidence missing:** %s." % "; ".join(row["missing_evidence"]))
        w("")
    w("Churned users appear in no usage export, so none of the above can show "
      "a user who already left because of this feature.")
    w("")

    w("## Owner")
    w("")
    w("One named person accountable end to end, plus a named reviewer in each "
      "of the three areas. Fill these in before anything ships.")
    w("")
    w("- Accountable owner: _TBD_")
    w("- Product reviewer: _TBD_")
    w("- Engineering reviewer: _TBD_")
    w("- Legal / contracts reviewer: _TBD_ (required even when the contractual "
      "gate passed: the repository is not where contracts live)")
    w("")

    w("## Dependencies to unpick first")
    w("")
    dep = (row.get("gates") or {}).get("dependency", {})
    examples = dep.get("inbound_examples") or []
    if examples:
        for hit in examples:
            w("- `%s` imports `%s`" % (hit.get("from"), hit.get("imports")))
        if dep.get("inbound_total", 0) > len(examples):
            w("- …and %d more"
              % (dep["inbound_total"] - len(examples)))
    else:
        w("No static import crosses into this feature. That is weaker than "
          "\"nothing depends on it\": check dynamic requires, DI registration, "
          "autoloading, shared database tables, queue consumers and HTTP "
          "callers by hand.")
    w("")

    w("## Schedule")
    w("")
    w("Flag off first, delete last. Nothing is deleted until the feature has "
      "been provably off for a full observation period.")
    w("")
    w("| Day | Date | Step |")
    w("|---|---|---|")
    steps = [
        (0, "Plan reviewed and approved by all four names above"),
        (3, "Feature flag `%s%s` added, defaulting to ON; deprecation notice "
            "shown in-product to current users" % (flag_prefix, fid.replace("-", "_"))),
        (7, "Export or migration path available to affected users; support and "
            "docs updated; changelog entry published"),
        (14, "Flag flipped OFF for new accounts only"),
        (7 * weeks // 2, "Flag flipped OFF for all accounts; feature "
                         "unreachable but code intact"),
        (7 * weeks, "Observation period ends; if no abort trigger fired, "
                    "remove the code and the flag in one reviewable pull "
                    "request"),
        (7 * weeks + 30, "Delete the flag definition and any orphaned data, "
                         "per your retention policy"),
    ]
    for days, text in steps:
        w("| +%d | %s | %s |" % (days, fmt_date(today, days), text))
    w("")

    w("## Metrics to watch through the wind-down")
    w("")
    w("- Support ticket volume mentioning this feature (the earliest signal)")
    w("- Usage of the feature itself after each flag flip — a spike means "
      "someone depended on it more than the data showed")
    w("- Churn and downgrade rate in accounts that used it, versus accounts "
      "that did not")
    w("- Error rate in the code paths that remain")
    w("")

    w("## Abort triggers")
    w("")
    w("Any one of these stops the schedule and reverts the flag. Decide them "
      "now, not in the middle of an incident.")
    w("")
    w("- An account above your ARR threshold asks for it back")
    w("- Support tickets about it exceed _TBD_ in any week")
    w("- Churn in the affected cohort exceeds the unaffected cohort by _TBD_")
    w("- Any contractual or regulatory obligation surfaces that the gates "
      "missed")
    w("")
    w("Reverting is a flag flip until the deletion step; after deletion it is "
      "a revert of one pull request. That is the reason for this ordering.")
    w("")

    w("## Audit trail")
    w("")
    w("- Keep every flag change logged with who made it and when")
    w("- Link the approving decision to this document")
    w("- Record the deletion commit here once it merges: _TBD_")
    w("")
    w("---")
    w("")
    w("Generated as a draft by strip-down. It deletes nothing and approves "
      "nothing. Edit it, get it reviewed, and commit it alongside the "
      "inventory.")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("feature", help="feature id from the inventory")
    ap.add_argument("--root", default=None)
    ap.add_argument("--aggregate")
    ap.add_argument("--events")
    ap.add_argument("--revenue")
    ap.add_argument("--eligible", type=int)
    ap.add_argument("--window-days", type=int, dest="window_days")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--all-history", action="store_true")
    ap.add_argument("--cost-json", dest="cost_json")
    ap.add_argument("--usage-json", dest="usage_json")
    ap.add_argument("--seasonal-days", type=int, dest="seasonal_days")
    ap.add_argument("--weeks", type=int, default=6,
                    help="observation period before deletion (default 6)")
    ap.add_argument("--flag-prefix", default="sunset_")
    ap.add_argument("--stdout", action="store_true",
                    help="print instead of writing a file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    data = inv.load_inventory(root)
    feature = None
    for feat in data.get("features") or []:
        if feat.get("id") == args.feature:
            feature = feat
            break
    if feature is None:
        ids = [f.get("id") for f in data.get("features") or []]
        inv.die("no feature %r in the inventory. Known ids: %s"
                % (args.feature, ", ".join(str(i) for i in ids[:30])))

    verdict = fetch_verdict(root, args)
    row = None
    for candidate in verdict.get("rows", []):
        if candidate.get("id") == args.feature:
            row = candidate
            break
    if row is None:
        inv.die("the verdict report returned no row for %r" % args.feature)

    today = datetime.date.today()
    body = render(feature, row, today, args.flag_prefix, max(1, args.weeks))

    if args.stdout:
        sys.stdout.write(body)
        return
    out_dir = os.path.join(root, inv.STATE_DIR, "sunset")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "%s.md" % args.feature)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    blockers = (row.get("gates_failed") or []) + (row.get("gates_unknown") or [])
    inv.emit({
        "wrote": os.path.relpath(out_path, root),
        "feature": args.feature,
        "bucket": row.get("bucket"),
        "blocked_by": blockers,
        "status": "draft: nothing approved, nothing deleted",
    }, args.json)


if __name__ == "__main__":
    main()
