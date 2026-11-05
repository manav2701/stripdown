#!/usr/bin/env python3
"""Scope analysis for a product with no usage data yet.

A pre-PMF product does not have a bloat problem, it has a scope problem:
shipping six half-jobs instead of one whole one. There is no usage data to
audit, so this measures something that is actually knowable from the repository
-- how much of what you have built is not on the path that delivers the one job
you claim to do.

You declare that path; the script will not guess it. Put it in the inventory:

    critical_path:
      - signup
      - editor
      - share

Then this reports what share of the codebase, the commits and the churn went to
everything else, and when each feature first appeared, so scope creep is
visible as a chronology rather than an impression.

What it cannot do: tell you whether the one job is the right job, or what the
market wants. That is not a measurement, and a confident answer to it would be
fiction. See skills/demand/SKILL.md for what is honestly available there.

Read-only. Needs git for the timeline and the activity shares.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import inv  # noqa: E402


def first_seen(root, files_by_feature):
    """Earliest commit date per feature, from one reverse log pass."""
    out = inv.run(["git", "log", "--reverse", "--no-merges", "--name-only",
                   "--format=\x01%at"], cwd=root, check=False)
    if out is None:
        return {}, {}
    first_for_file = {}
    stamp = None
    for line in out.splitlines():
        if line.startswith("\x01"):
            try:
                stamp = int(line[1:])
            except ValueError:
                stamp = None
        elif line.strip() and stamp is not None:
            first_for_file.setdefault(line.strip(), stamp)
    per_feature = {}
    for fid, paths in files_by_feature.items():
        stamps = [first_for_file[p] for p in paths if p in first_for_file]
        if stamps:
            per_feature[fid] = min(stamps)
    return per_feature, first_for_file


def iso(stamp):
    import datetime
    return datetime.datetime.fromtimestamp(
        stamp, datetime.timezone.utc).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--path", help="comma-separated feature ids on the "
                                   "critical path, overriding the inventory")
    ap.add_argument("--months", type=int, default=0,
                    help="cost window; 0 means all history (the default here, "
                         "because scope creep is a whole-life question)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    data = inv.load_inventory(root)
    features = data.get("features") or []
    if not features:
        inv.die("inventory has no features")

    declared = []
    if args.path:
        declared = [p.strip() for p in args.path.split(",") if p.strip()]
    elif data.get("critical_path"):
        declared = [str(p) for p in data["critical_path"]]
    else:
        cfg = inv.load_config(root)
        declared = [str(p) for p in (cfg.get("critical_path") or [])]

    known = {f["id"] for f in features}
    unknown = [d for d in declared if d not in known]
    if unknown:
        inv.die("critical_path names features that are not in the inventory: %s"
                % ", ".join(unknown))

    files = inv.list_files(root)
    matcher = inv.Matcher(features)
    attributed = matcher.assign(files)

    cost = None
    if inv.is_git_repo(root):
        extra = ["--root", root, "--json"]
        extra += ["--all-history"] if not args.months else ["--months",
                                                            str(args.months)]
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "cost_report.py")] + extra,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        if proc.returncode == 0 and proc.stdout.strip():
            cost = json.loads(proc.stdout)
    cost_rows = {r["id"]: r for r in (cost or {}).get("features", [])}

    seen, _ = first_seen(root, attributed) if inv.is_git_repo(root) else ({}, {})

    on, off = [], []
    for feat in features:
        fid = feat["id"]
        crow = cost_rows.get(fid, {})
        entry = {
            "id": fid,
            "name": feat.get("name") or fid,
            "on_critical_path": fid in declared,
            "files": len(attributed.get(fid, [])),
            "loc": crow.get("loc"),
            "commits": crow.get("commits"),
            "churn": crow.get("churn"),
            "share_of_repo_loc": crow.get("share_of_repo_loc"),
            "share_of_repo_churn": crow.get("share_of_repo_churn"),
            "cost_index": crow.get("cost_index"),
            "first_seen": iso(seen[fid]) if fid in seen else None,
            "events_mapped": len(feat.get("events") or []),
        }
        (on if entry["on_critical_path"] else off).append(entry)

    def total(rows, key):
        return sum(r.get(key) or 0 for r in rows)

    all_rows = on + off
    totals = {key: total(all_rows, key) for key in ("loc", "commits", "churn",
                                                     "cost_index")}
    shares = {}
    for key in ("loc", "commits", "churn", "cost_index"):
        if totals[key]:
            shares["off_path_%s_pct" % key] = round(
                100.0 * total(off, key) / totals[key], 1)
        else:
            shares["off_path_%s_pct" % key] = None

    timeline = sorted(
        [r for r in all_rows if r["first_seen"]],
        key=lambda r: r["first_seen"])

    report = {
        "root": root,
        "mode": data.get("mode"),
        "critical_path_declared": bool(declared),
        "critical_path": declared,
        "features_total": len(all_rows),
        "features_on_path": len(on),
        "features_off_path": len(off),
        "off_path_shares": shares,
        "on_path": sorted(on, key=lambda r: -(r["cost_index"] or 0)),
        "off_path": sorted(off, key=lambda r: -(r["cost_index"] or 0)),
        "timeline": [
            {"first_seen": r["first_seen"], "id": r["id"],
             "on_critical_path": r["on_critical_path"]}
            for r in timeline
        ],
        "caveats": [],
    }

    if not declared:
        report["caveats"].append(
            "no critical path declared, so nothing can be measured against "
            "it; add critical_path to the inventory or pass --path. This "
            "script deliberately will not infer which features deliver your "
            "one job")
        report["caveats"].append(
            "the timeline below is still useful on its own: it shows the order "
            "in which features appeared, which is scope creep as a chronology")
    else:
        off_churn = shares.get("off_path_churn_pct")
        if off_churn is not None:
            report["headline"] = (
                "%.1f%% of this repository's churn went to features not on the "
                "declared critical path (%d of %d features)"
                % (off_churn, len(off), len(all_rows)))
    if not inv.is_git_repo(root):
        report["caveats"].append(
            "not a git repository: no activity shares and no timeline, only "
            "file counts")
    report["caveats"].append(
        "being off the critical path is not an argument for removal. Admin, "
        "billing, support and compliance features are off the path by nature "
        "and load-bearing anyway. This measures where effort went, not what "
        "deserves to exist")
    report["caveats"].append(
        "in pre-users mode there is no usage data, so nothing here is evidence "
        "about what anyone wants; it is evidence about what you have built")
    inv.emit(report, args.json)


if __name__ == "__main__":
    main()
