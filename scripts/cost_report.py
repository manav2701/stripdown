#!/usr/bin/env python3
"""Price each feature in the inventory from git history and the working tree.

Every published feature-audit framework asks you to plot value against
maintenance cost, and then sources the cost axis from a meeting where people
guess. This measures it instead:

  commits        how often the feature is touched
  churn          lines added + deleted in the window
  authors        how many people have touched it, and the top author's share
  fix_ratio      share of its commits whose subject looks like a bug fix
  loc            current size in the working tree
  test_loc       size of its tests
  last_touched   days since the last commit
  cost_index     share of the repo's weighted maintenance activity:
                 0.5*churn_share + 0.3*commit_share + 0.2*loc_share, as a
                 percentage. A transparent ordering heuristic, not a currency.

Things it deliberately does not do: convert any of this to money, or claim a
feature is expensive because it is large. A big, stable, never-touched feature
is cheap to keep -- "no_activity_in_window" marks exactly that case, and it
matters, because a quiet feature that costs nothing is rarely worth the risk of
removing.

Caveats that are inherent, not bugs: a repo-wide reformat or a dependency bump
inflates churn; vendored or generated code attributed to a feature inflates
everything; and squash-merge repositories compress many commits into one, so
commit counts are comparable within a repo but not across repos.

Read-only. Requires git.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import inv  # noqa: E402

FIX_RE = re.compile(
    r"\b(fix(e[sd])?|bug|hotfix|patch|regress(ion)?|revert|broken|crash|"
    r"workaround|incident)\b", re.I)
REVERT_RE = re.compile(r"^revert\b", re.I)

SEP_C = "\x01"
SEP_F = "\x02"


def resolve_rename(path):
    """numstat renders renames as 'a => b' or 'pre/{a => b}/post'."""
    if "=>" not in path:
        return path
    brace = re.search(r"\{(.*?) => (.*?)\}", path)
    if brace:
        return (path[: brace.start()] + brace.group(2) + path[brace.end():]
                ).replace("//", "/")
    return path.split("=>")[-1].strip()


def read_log(root, since, all_history):
    args = ["git", "log", "--no-merges", "--numstat",
            "--format=%s%%H%s%%at%s%%an%s%%s" % (SEP_C, SEP_F, SEP_F, SEP_F)]
    if not all_history:
        args.insert(2, "--since=%s" % since)
    out = inv.run(args, cwd=root, check=False)
    if out is None:
        inv.die("git log failed; is this a git repository with any commits?")
    commits = []
    current = None
    for line in out.splitlines():
        if line.startswith(SEP_C):
            parts = line[1:].split(SEP_F)
            if len(parts) < 4:
                continue
            current = {
                "sha": parts[0], "at": int(parts[1]), "author": parts[2],
                "subject": parts[3], "files": [],
            }
            commits.append(current)
        elif current is not None and "\t" in line:
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            add = 0 if cols[0] == "-" else int(cols[0] or 0)
            dele = 0 if cols[1] == "-" else int(cols[1] or 0)
            current["files"].append((resolve_rename(cols[2]), add, dele))
    return commits


def count_loc(root, paths):
    total = 0
    for path in paths:
        if not inv.is_texty(path):
            continue
        got = inv.read_text(os.path.join(root, path))
        if not got:
            continue
        total += got[0].count("\n") + 1
    return total


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--months", type=int, default=12,
                    help="history window in months (default 12)")
    ap.add_argument("--all-history", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--unassigned", type=int, default=12,
                    help="how many unassigned directories to list (default 12)")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    if not inv.is_git_repo(root):
        inv.die("%s is not a git repository; cost needs git history" % root)
    data = inv.load_inventory(root)
    features = data.get("features") or []
    if not features:
        inv.die("inventory has no features")

    files = inv.list_files(root)
    matcher = inv.Matcher(features)
    owner = {}
    for path in files:
        fid = matcher.match(path)
        if fid:
            owner[path] = fid

    since = "%d months ago" % args.months
    commits = read_log(root, since, args.all_history)

    stats = {}
    for feat in features:
        stats[feat["id"]] = {
            "commits": 0, "churn": 0, "fix_commits": 0, "reverts": 0,
            "authors": {}, "last_at": 0, "shas": set(),
        }
    repo = {"commits": 0, "churn": 0}

    for commit in commits:
        touched = {}
        for path, add, dele in commit["files"]:
            fid = owner.get(path) or matcher.match(path)
            repo["churn"] += add + dele
            if fid:
                touched[fid] = touched.get(fid, 0) + add + dele
        if commit["files"]:
            repo["commits"] += 1
        is_fix = bool(FIX_RE.search(commit["subject"]))
        is_revert = bool(REVERT_RE.match(commit["subject"]))
        for fid, churn in touched.items():
            st = stats[fid]
            st["commits"] += 1
            st["churn"] += churn
            st["shas"].add(commit["sha"])
            st["authors"][commit["author"]] = st["authors"].get(commit["author"], 0) + 1
            st["last_at"] = max(st["last_at"], commit["at"])
            if is_fix:
                st["fix_commits"] += 1
            if is_revert:
                st["reverts"] += 1

    repo_loc = count_loc(root, files)
    now = max([c["at"] for c in commits], default=0)

    rows = []
    for feat in features:
        fid = feat["id"]
        st = stats[fid]
        own = sorted(p for p, f in owner.items() if f == fid)
        tests = [p for p in own if inv.is_test_path(p)]
        prod = [p for p in own if p not in set(tests)]
        loc = count_loc(root, prod)
        test_loc = count_loc(root, tests)
        authors = st["authors"]
        top_author_share = None
        if authors:
            top = max(authors.values())
            top_author_share = inv.pct(top, sum(authors.values()))
        churn_share = (st["churn"] / repo["churn"]) if repo["churn"] else 0.0
        commit_share = (st["commits"] / repo["commits"]) if repo["commits"] else 0.0
        loc_share = (loc / repo_loc) if repo_loc else 0.0
        rows.append({
            "id": fid,
            "name": feat.get("name") or fid,
            "status": feat.get("status", "active"),
            "files": len(own),
            "loc": loc,
            "test_files": len(tests),
            "test_loc": test_loc,
            "commits": st["commits"],
            "churn": st["churn"],
            "authors": len(authors),
            "top_author_share": top_author_share,
            "bus_factor_1": bool(authors) and len(authors) == 1,
            "fix_commits": st["fix_commits"],
            "fix_ratio": inv.pct(st["fix_commits"], st["commits"]),
            "reverts": st["reverts"],
            "days_since_touched": (
                int((now - st["last_at"]) / 86400) if st["last_at"] else None),
            "no_activity_in_window": st["commits"] == 0,
            "share_of_repo_loc": round(100 * loc_share, 1),
            "share_of_repo_commits": round(100 * commit_share, 1),
            "share_of_repo_churn": round(100 * churn_share, 1),
            "cost_index": round(
                100 * (0.5 * churn_share + 0.3 * commit_share + 0.2 * loc_share), 2),
        })
    rows.sort(key=lambda r: -r["cost_index"])

    unassigned = [p for p in files if p not in owner]
    tally = {}
    for path in unassigned:
        parts = path.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else (
            parts[0] if len(parts) > 1 else "(repo root)")
        tally[key] = tally.get(key, 0) + 1

    report = {
        "root": root,
        "window": "all history" if args.all_history else since,
        "commits_in_window": repo["commits"],
        "repo_loc": repo_loc,
        "files_total": len(files),
        "files_attributed": len(owner),
        "coverage_pct": inv.pct(len(owner), len(files)),
        "features": rows,
        "unassigned_files": len(unassigned),
        "unassigned_top_dirs": [
            {"dir": d, "files": c}
            for d, c in sorted(tally.items(), key=lambda kv: -kv[1])[: args.unassigned]
        ],
        "path_overlaps": [
            {"file": f, "features": ids}
            for f, ids in sorted(matcher.overlaps.items())[:20]
        ],
        "caveats": [
            "churn is inflated by reformats, dependency bumps and generated code",
            "commit counts are comparable within this repo, not across repos",
            "a low cost_index with no usage is not urgent to remove; it is cheap "
            "to keep and removal carries its own risk",
        ],
    }
    if report["coverage_pct"] is not None and report["coverage_pct"] < 60:
        report["caveats"].insert(
            0, "only %s%% of files are attributed to a feature; the inventory is "
               "probably incomplete, so shares are understated"
               % report["coverage_pct"])
    inv.emit(report, args.json)


if __name__ == "__main__":
    main()
