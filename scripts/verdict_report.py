#!/usr/bin/env python3
"""Join inventory, cost and usage; apply the seven kill gates; sort into buckets.

This is the first command in strip-down that makes a recommendation, so it is
built to make as few as possible. Five buckets, because they imply five
different actions:

  cut          every gate passed. A removal candidate, with a sunset plan next.
  reposition   few people found it, those who did kept using it. Fix placement,
               do not remove. Needs an awareness survey to confirm.
  keep         earning its cost, or load-bearing.
  blind-spot   exists in code, nothing measures it. Not a candidate: an
               instrumentation gap. Cannot be judged at all.
  blocked      would be a cut, but a gate failed or is unanswered. The gate is
               named. This is the output working correctly, not a defect.

Every row carries the evidence used, the evidence MISSING, a confidence level,
and the cheapest next step that would raise it. A fresh inventory blocks
everything, because three gates rest on facts only a human has.

Nothing here deletes anything, and "cut" means "a human should now decide",
not "safe to delete".
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import deps  # noqa: E402
import gates as G  # noqa: E402
import inv  # noqa: E402

BUCKETS = ("cut", "reposition", "blocked", "blind-spot", "keep")


def run_sub(script, extra):
    args = [sys.executable, os.path.join(HERE, script), "--json"] + extra
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None, (proc.stderr or "").strip()
    try:
        return json.loads(proc.stdout), None
    except ValueError as exc:
        return None, "could not parse %s output: %s" % (script, exc)


def urgency(cost_index):
    if cost_index is None:
        return "unknown"
    if cost_index >= 5.0:
        return "high"
    if cost_index >= 1.0:
        return "medium"
    return "low"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--all-history", action="store_true")
    ap.add_argument("--aggregate", help="usage CSV, aggregate shape")
    ap.add_argument("--events", help="usage CSV, event-level shape")
    ap.add_argument("--revenue", help="account_id,arr CSV")
    ap.add_argument("--eligible", type=int)
    ap.add_argument("--window-days", type=int)
    ap.add_argument("--cost-json", help="reuse a saved cost_report --json file")
    ap.add_argument("--usage-json", help="reuse a saved usage_report --json file")
    ap.add_argument("--seasonal-days", type=int, default=365)
    ap.add_argument("--arr-share-limit", type=float, default=5.0)
    ap.add_argument("--top-account-limit", type=float, default=50.0)
    ap.add_argument("--dormant-breadth", type=float, default=1.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    data = inv.load_inventory(root)
    features = data.get("features") or []
    if not features:
        inv.die("inventory has no features")

    notes = []

    # ---- cost -------------------------------------------------------------
    cost = None
    if args.cost_json:
        with open(args.cost_json) as fh:
            cost = json.load(fh)
    elif inv.is_git_repo(root):
        extra = ["--root", root]
        extra += ["--all-history"] if args.all_history else ["--months",
                                                             str(args.months)]
        cost, err = run_sub("cost_report.py", extra)
        if cost is None:
            notes.append("cost unavailable: %s" % err)
    else:
        notes.append("not a git repository, so no cost data; cut urgency "
                     "cannot be ranked")
    cost_rows = {r["id"]: r for r in (cost or {}).get("features", [])}

    # ---- usage ------------------------------------------------------------
    usage = None
    if args.usage_json:
        with open(args.usage_json) as fh:
            usage = json.load(fh)
    elif args.aggregate or args.events:
        extra = ["--root", root]
        if args.aggregate:
            extra += ["--aggregate", args.aggregate]
        else:
            extra += ["--events", args.events]
        if args.revenue:
            extra += ["--revenue", args.revenue]
        if args.eligible:
            extra += ["--eligible", str(args.eligible)]
        if args.window_days:
            extra += ["--window-days", str(args.window_days)]
        usage, err = run_sub("usage_report.py", extra)
        if usage is None:
            inv.die("usage data was supplied but could not be read: %s" % err)
    else:
        notes.append("no usage data supplied, so every feature is "
                     "unassessable; pass --aggregate or --events")
    usage_rows = {r["id"]: r for r in (usage or {}).get("rows", [])}

    # ---- dependency index -------------------------------------------------
    files = inv.list_files(root)
    matcher = inv.Matcher(features)
    attributed = matcher.assign(files)
    dep_index = deps.DepIndex(root, files, inv.read_text)

    ctx = G.Context(
        window_days=(usage or {}).get("window_days") or args.window_days,
        seasonal_days=args.seasonal_days,
        arr_share_limit=args.arr_share_limit,
        top_account_limit=args.top_account_limit,
        dormant_breadth=args.dormant_breadth,
        dep_index=dep_index, root=root, files=files, read_text=inv.read_text,
        has_revenue=bool((usage or {}).get("total_arr")),
    )

    rows = []
    for feat in features:
        fid = feat["id"]
        ucost = cost_rows.get(fid)
        urow = usage_rows.get(fid)
        own = attributed.get(fid, [])

        results = G.evaluate(feat, urow, ctx, feature_files=own)
        summary = G.summarise(results)
        sig = (urow or {}).get("signature")
        cost_index = (ucost or {}).get("cost_index")

        # ---- bucket ------------------------------------------------------
        if urow is None or sig == "blind-spot":
            bucket = "blind-spot"
            why = ("nothing measures this feature, so no judgment is possible"
                   if urow is None or sig == "blind-spot" else "")
        elif sig == "discoverability-suspect":
            bucket = "reposition"
            why = ("few people found it and those who did kept using it; the "
                   "hypothesis is placement, not value, and an awareness "
                   "survey is what would confirm it")
        elif not summary["all_clear"]:
            bucket = "blocked"
            blockers = summary["failed"] + summary["unknown"]
            why = "blocked by %s" % ", ".join(blockers)
        elif sig in ("dormant", "value-suspect", "quiet", "no-data"):
            bucket = "cut"
            why = ("every gate passed and the usage signature is %s; a human "
                   "should now decide, and /strip-down:sunset drafts the plan"
                   % sig)
        else:
            bucket = "keep"
            why = "in ordinary use and nothing suggests otherwise"

        # ---- evidence accounting ------------------------------------------
        missing = []
        if ucost is None:
            missing.append("maintenance cost (needs git history)")
        if urow is None:
            missing.append("usage data")
        if not ctx.window_days:
            missing.append("observation window length")
        elif ctx.window_days < args.seasonal_days:
            missing.append("a full %d-day window (have %d)"
                           % (args.seasonal_days, ctx.window_days))
        if not ctx.has_revenue:
            missing.append("revenue per account")
        for name in ("contractual", "regulatory", "migration"):
            if results[name]["state"] == G.UNKNOWN:
                missing.append("a human answer for the %s gate" % name)
        if (urow or {}).get("depth_pct") is None and urow is not None:
            missing.append("repeat-use data (depth)")

        have = 5 - min(5, len(set(missing)))
        confidence = "high" if not missing else ("medium" if have >= 3 else "low")

        step = None
        if bucket == "reposition":
            step = "run /strip-down:survey to test awareness before acting"
        elif urow is None:
            step = "export usage for the events in the inventory"
        elif sig == "blind-spot":
            step = ("instrument this feature, or decide about it deliberately "
                    "without data and record that choice")
        elif results["dormancy"]["state"] == G.UNKNOWN or (
                ctx.window_days and ctx.window_days < args.seasonal_days):
            step = "re-export usage over a full %d-day window" % args.seasonal_days
        elif results["contractual"]["state"] == G.UNKNOWN:
            step = "answer gates.contractual and gates.public_api in the inventory"
        elif results["regulatory"]["state"] == G.UNKNOWN:
            step = "record in notes why this is not a regulated feature"
        elif results["revenue"]["state"] == G.UNKNOWN:
            step = "supply --revenue so revenue at risk can be checked"
        elif results["migration"]["state"] == G.UNKNOWN:
            step = "run /strip-down:sunset to draft a migration path"

        row = {
            "id": fid,
            "name": feat.get("name") or fid,
            "bucket": bucket,
            "because": why,
            "confidence": confidence,
            "missing_evidence": sorted(set(missing)),
            "cheapest_next_step": step,
            "usage_signature": sig,
            "breadth_pct": (urow or {}).get("breadth_pct"),
            "breadth_ci95": (urow or {}).get("breadth_ci95"),
            "depth_pct": (urow or {}).get("depth_pct"),
            "adopters": (urow or {}).get("adopters"),
            "arr_share_pct": (urow or {}).get("arr_share_pct"),
            "cost_index": cost_index,
            "fix_ratio": (ucost or {}).get("fix_ratio"),
            "loc": (ucost or {}).get("loc"),
            "no_activity_in_window": (ucost or {}).get("no_activity_in_window"),
            "files": len(own),
            "gates": {name: results[name] for name in G.GATE_ORDER},
            "gates_passed": summary["passed"],
            "gates_failed": summary["failed"],
            "gates_unknown": summary["unknown"],
        }
        if bucket == "cut":
            row["urgency"] = urgency(cost_index)
            if row["urgency"] == "low":
                row["urgency_note"] = (
                    "cheap to keep: removing it costs engineering time and "
                    "carries its own risk, so this is not urgent")
            row["red_team_brief"] = {
                "adopters_at_removal": (urow or {}).get("adopters"),
                "arr_touching": (urow or {}).get("arr_touching"),
                "top_account_arr_share_pct":
                    (urow or {}).get("top_account_arr_share_pct"),
                "question": "who specifically is hurt if this is removed, and "
                            "what evidence would show they exist?",
            }
        rows.append(row)

    order = {b: i for i, b in enumerate(BUCKETS)}
    rows.sort(key=lambda r: (order.get(r["bucket"], 9),
                             -(r["cost_index"] or 0)))

    tally = {}
    for row in rows:
        tally[row["bucket"]] = tally.get(row["bucket"], 0) + 1

    report = {
        "root": root,
        "features": len(rows),
        "buckets": [{"bucket": b, "features": tally.get(b, 0)} for b in BUCKETS],
        "gate_thresholds": ctx.as_dict(),
        "dependency_index": {
            "code_files": dep_index.code_files,
            "unreadable": dep_index.unparsed,
            "limits": "static imports only: dynamic requires, DI containers, "
                      "autoloading, shared database tables and HTTP callers are "
                      "invisible to it",
        },
        "rows": rows,
        "notes": notes,
        "caveats": [
            "a cut bucket means every available gate passed, not that removal "
            "is safe; a human decides and /strip-down:sunset drafts the plan",
            "three gates (contractual, regulatory, migration) rest on facts "
            "only a human has, so a fresh inventory blocks everything",
            "churned users appear in no export, so a feature whose absence "
            "drove people away leaves no trace in any of this",
            "there is no published evidence that removing features improves "
            "retention; the case for removal is the cost you stop paying",
        ],
    }
    if tally.get("cut"):
        report["caveats"].insert(0, (
            "%d features reached the cut bucket; have the red-team agent argue "
            "against each one before acting" % tally["cut"]))
    inv.emit(report, args.json)


if __name__ == "__main__":
    main()
