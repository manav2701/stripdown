#!/usr/bin/env python3
"""Join product usage data onto the feature inventory.

Takes usage you have exported yourself -- no credentials, no network -- and
reports, per feature: breadth, depth, retention, trend, and where revenue
information is supplied, how concentrated that feature's users are.

Two input shapes, both CSV:

  --aggregate FILE   one row per feature or per event, pre-aggregated:
                     feature_id|event, eligible_users, adopters,
                     repeat_adopters, [retained_adopters], [uses]
  --events FILE      one row per event occurrence:
                     user_id, event, timestamp, [account_id]
                     breadth/depth/retention/trend are computed from it

  --revenue FILE     account_id, arr  (optional, joins via events' account_id)

What it reports, and the vocabulary it uses on purpose:

  breadth   adopters / eligible users, with a Wilson 95% interval, because
            "2 of 3 users" is not 67% adoption
  depth     repeat adopters / adopters -- computed over ADOPTERS ONLY. Taken
            over all users it is just breadth again, which is the single most
            common way this metric is reported wrongly.
  signature a description of the shape of the data, NOT a recommendation.
            "discoverability-suspect" means few people found it but those who
            did kept using it. Deciding what to do about that needs awareness
            data, which no event stream contains -- you have to ask people.

Two distinctions this script refuses to collapse:

  blind-spot   the feature has no events mapped in the inventory. Nothing can
               be said about its usage. It is not a removal candidate; it is an
               instrumentation gap.
  no-data      events ARE mapped but none appear in the export. This is
               genuinely ambiguous: either nobody used it, or it was never
               wired up, or your export window missed it. The script will not
               guess which, and says so.

It also refuses to print a percentage when the denominator is too small to
support one, reporting "insufficient-data" instead.

Read-only. No network. Expects aggregates, not personal data -- see PRIVACY.md.
"""

import argparse
import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import inv  # noqa: E402

TS_FORMATS = (
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y",
)


def norm_header(name):
    return (name or "").strip().lower().replace(" ", "_").replace("-", "_")


def read_csv(path):
    if not os.path.exists(path):
        inv.die("no such file: %s" % path)
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if not reader.fieldnames:
            inv.die("%s has no header row" % path)
        rows = []
        for raw in reader:
            rows.append({norm_header(k): (v or "").strip()
                         for k, v in raw.items() if k is not None})
        return rows, [norm_header(f) for f in reader.fieldnames]


def pick(row, *names):
    for name in names:
        if name in row and row[name] != "":
            return row[name]
    return None


def to_int(value, where, field):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        inv.die("%s: %s is not a number: %r" % (where, field, value))


def to_float(value, where, field):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        inv.die("%s: %s is not a number: %r" % (where, field, value))


def parse_ts(value, where):
    text = (value or "").strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        if number > 10_000_000_000:
            number //= 1000
        return number
    cleaned = text.replace("Z", "").split("+")[0].split(".")[0]
    for fmt in TS_FORMATS:
        try:
            return int(datetime.strptime(cleaned, fmt).timestamp())
        except ValueError:
            continue
    inv.die("%s: cannot parse timestamp %r" % (where, value))


def wilson(successes, total, z=1.96):
    """95% Wilson score interval for a proportion, as percentages."""
    if not total:
        return None
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / total
                            + z * z / (4 * total * total))) / denom
    return [round(100 * max(0.0, centre - margin), 1),
            round(100 * min(1.0, centre + margin), 1)]


class Thresholds(object):
    def __init__(self, args):
        self.min_eligible = args.min_eligible
        self.min_adopters = args.min_adopters
        self.low_breadth = args.low_breadth
        self.high_depth = args.high_depth
        self.wide_breadth = args.wide_breadth
        self.low_depth = args.low_depth

    def as_dict(self):
        return {
            "min_eligible": self.min_eligible,
            "min_adopters": self.min_adopters,
            "low_breadth_pct": self.low_breadth,
            "high_depth_pct": self.high_depth,
            "wide_breadth_pct": self.wide_breadth,
            "low_depth_pct": self.low_depth,
            "provenance": "defaults chosen to be conservative, not validated; "
                          "published adoption benchmarks are uncited vendor "
                          "figures and adoption is feature-specific",
        }


def signature(row, th):
    if row["blind_spot"]:
        return "blind-spot", (
            "no events mapped in the inventory; usage cannot be assessed and "
            "this is not a removal candidate")
    if row["events_seen"] == 0:
        return "no-data", (
            "events are mapped but none appear in the export: either unused, "
            "never instrumented, or outside the export window -- this script "
            "cannot tell which")
    eligible = row.get("eligible_users") or 0
    adopters = row.get("adopters") or 0
    if eligible < th.min_eligible:
        return "insufficient-data", (
            "only %s eligible users, too few to support a rate" % eligible)
    # Zero adopters against a large denominator is a STRONG result, not a
    # missing one. The adopter floor exists to stop depth being computed over a
    # handful of people, so it must not swallow a genuine dormant case.
    if adopters == 0:
        return "dormant", (
            "nobody among %s eligible users touched it in the window"
            % eligible)
    if adopters < th.min_adopters:
        return "insufficient-data", (
            "only %s adopters, too few to compute depth over" % adopters)
    breadth = row.get("breadth_pct")
    depth = row.get("depth_pct")
    if breadth is None:
        return "insufficient-data", "no eligible-user denominator supplied"
    if depth is None:
        return "in-use", "no repeat-use data supplied, so depth is unknown"
    if breadth < th.low_breadth and depth >= th.high_depth:
        return "discoverability-suspect", (
            "few people found it, but those who did kept using it; confirm with "
            "an awareness survey before changing anything")
    if breadth >= th.wide_breadth and depth < th.low_depth:
        return "value-suspect", (
            "widely seen and not adopted repeatedly, which points at value "
            "rather than discovery")
    if breadth < th.low_breadth and depth < th.low_depth:
        return "quiet", (
            "little breadth and little depth; ambiguous without awareness data")
    return "in-use", "breadth and depth both within an ordinary range"


def build_from_aggregate(rows, fields):
    """Return {key: metrics} keyed by feature_id or event name."""
    if not ({"feature_id", "feature", "event", "event_name"} & set(fields)):
        inv.die("--aggregate needs a feature_id, feature, event or event_name "
                "column; found: %s" % ", ".join(fields))
    out = {}
    for idx, row in enumerate(rows, 2):
        where = "row %d" % idx
        key = pick(row, "feature_id", "feature", "event", "event_name")
        if not key:
            continue
        keyed_by_event = pick(row, "feature_id", "feature") is None
        eligible = to_int(pick(row, "eligible_users", "eligible", "exposed_users",
                               "exposed"), where, "eligible_users")
        adopters = to_int(pick(row, "adopters", "users", "unique_users"),
                          where, "adopters")
        repeat = to_int(pick(row, "repeat_adopters", "repeat_users", "repeat"),
                        where, "repeat_adopters")
        retained = to_int(pick(row, "retained_adopters", "retained"),
                          where, "retained_adopters")
        uses = to_int(pick(row, "uses", "events", "event_count", "count"),
                      where, "uses")
        if adopters is not None and eligible is not None and adopters > eligible:
            inv.die("%s: adopters (%d) exceeds eligible_users (%d)"
                    % (where, adopters, eligible))
        if repeat is not None and adopters is not None and repeat > adopters:
            inv.die("%s: repeat_adopters (%d) exceeds adopters (%d)"
                    % (where, repeat, adopters))
        bucket = out.setdefault(key, {
            "keyed_by_event": keyed_by_event, "eligible_users": None,
            "adopters": 0, "repeat_adopters": None, "retained_adopters": None,
            "uses": 0, "rows": 0,
        })
        bucket["rows"] += 1
        if eligible is not None:
            bucket["eligible_users"] = max(bucket["eligible_users"] or 0, eligible)
        if adopters is not None:
            bucket["adopters"] = max(bucket["adopters"], adopters)
        for name, value in (("repeat_adopters", repeat),
                            ("retained_adopters", retained)):
            if value is not None:
                bucket[name] = max(bucket[name] or 0, value)
        if uses is not None:
            bucket["uses"] += uses
    return out


def build_from_events(rows, fields, revenue, default_eligible):
    """Returns (per-event metrics, distinct users, observed window in days)."""
    present = set(fields)
    alt_user = {"user_id", "distinct_id", "user", "person_id"} & present
    alt_event = {"event", "event_name", "name"} & present
    if not alt_user or not alt_event:
        inv.die("--events needs a user id column (user_id/distinct_id) and an "
                "event column; found: %s" % ", ".join(fields))
    has_ts = bool({"timestamp", "time", "ts", "occurred_at", "created_at"} & present)

    per_event = {}
    all_users = set()
    stamps = []
    for idx, row in enumerate(rows, 2):
        user = pick(row, "user_id", "distinct_id", "user", "person_id")
        event = pick(row, "event", "event_name", "name")
        if not user or not event:
            continue
        stamp = None
        if has_ts:
            stamp = parse_ts(pick(row, "timestamp", "time", "ts", "occurred_at",
                                  "created_at"), "row %d" % idx)
            if stamp:
                stamps.append(stamp)
        account = pick(row, "account_id", "org_id", "company_id", "team_id")
        bucket = per_event.setdefault(event, {
            "uses_by_user": {}, "stamps_by_user": {}, "accounts": set(),
        })
        bucket["uses_by_user"][user] = bucket["uses_by_user"].get(user, 0) + 1
        if stamp:
            bucket["stamps_by_user"].setdefault(user, []).append(stamp)
        if account:
            bucket["accounts"].add(account)
        all_users.add(user)

    midpoint = None
    window_days = None
    if stamps:
        midpoint = (min(stamps) + max(stamps)) // 2
        window_days = int((max(stamps) - min(stamps)) / 86400) or 1

    out = {}
    for event, bucket in per_event.items():
        uses_by_user = bucket["uses_by_user"]
        adopters = len(uses_by_user)
        repeat = sum(1 for n in uses_by_user.values() if n >= 2)
        retained = None
        retained_of = None
        trend = None
        first = set()
        if midpoint is not None:
            second = set()
            first_uses = second_uses = 0
            for user, user_stamps in bucket["stamps_by_user"].items():
                early = [s for s in user_stamps if s <= midpoint]
                late = [s for s in user_stamps if s > midpoint]
                if early:
                    first.add(user)
                    first_uses += len(early)
                if late:
                    second.add(user)
                    second_uses += len(late)
            if first:
                retained = len(first & second)
                retained_of = len(first)
            if first_uses:
                trend = round(100.0 * (second_uses - first_uses) / first_uses, 1)
        arr_touching = None
        top_account_share = None
        if revenue and bucket["accounts"]:
            touched = {a: revenue[a] for a in bucket["accounts"] if a in revenue}
            if touched:
                arr_touching = round(sum(touched.values()), 2)
                biggest = max(touched.values())
                arr_touching_total = sum(touched.values())
                if arr_touching_total:
                    top_account_share = round(100 * biggest / arr_touching_total, 1)
        out[event] = {
            "keyed_by_event": True,
            "eligible_users": default_eligible or len(all_users),
            "eligible_basis": ("supplied" if default_eligible
                               else "distinct users present in the export, which "
                                    "is NOT the same as eligible users"),
            "adopters": adopters,
            "repeat_adopters": repeat,
            "retained_adopters": retained,
            "retained_of": retained_of,
            "uses": sum(uses_by_user.values()),
            "trend_pct": trend,
            "accounts": len(bucket["accounts"]),
            "arr_touching": arr_touching,
            "top_account_arr_share_pct": top_account_share,
        }
    return out, len(all_users), window_days


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--aggregate", help="pre-aggregated CSV")
    ap.add_argument("--events", help="event-level CSV")
    ap.add_argument("--revenue", help="account_id,arr CSV")
    ap.add_argument("--eligible", type=int, default=None,
                    help="eligible-user denominator for --events mode")
    ap.add_argument("--window-days", type=int, default=None,
                    help="length of the observation window in days. Measured "
                         "from timestamps in --events mode; declare it in "
                         "--aggregate mode or the dormancy gate cannot clear")
    ap.add_argument("--min-eligible", type=int, default=30)
    ap.add_argument("--min-adopters", type=int, default=5)
    ap.add_argument("--low-breadth", type=float, default=10.0)
    ap.add_argument("--high-depth", type=float, default=50.0)
    ap.add_argument("--wide-breadth", type=float, default=40.0)
    ap.add_argument("--low-depth", type=float, default=20.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.aggregate and not args.events:
        inv.die("supply --aggregate FILE or --events FILE "
                "(see skills/usage/csv-schema.md)")
    if args.aggregate and args.events:
        inv.die("use one of --aggregate or --events, not both")

    root = inv.resolve_root(args.root or ".", args.root is not None)
    data = inv.load_inventory(root)
    features = data.get("features") or []
    th = Thresholds(args)

    revenue = {}
    if args.revenue:
        rev_rows, rev_fields = read_csv(args.revenue)
        if not ({"account_id", "org_id", "company_id", "team_id"} & set(rev_fields)):
            inv.die("--revenue needs an account_id column")
        for idx, row in enumerate(rev_rows, 2):
            account = pick(row, "account_id", "org_id", "company_id", "team_id")
            arr = to_float(pick(row, "arr", "mrr", "revenue", "value"),
                           "row %d" % idx, "arr")
            if account and arr is not None:
                revenue[account] = revenue.get(account, 0.0) + arr

    total_users_in_export = None
    measured_window = None
    if args.aggregate:
        rows, fields = read_csv(args.aggregate)
        metrics = build_from_aggregate(rows, fields)
        source = os.path.basename(args.aggregate)
        mode = "aggregate"
    else:
        rows, fields = read_csv(args.events)
        metrics, total_users_in_export, measured_window = build_from_events(
            rows, fields, revenue, args.eligible)
        source = os.path.basename(args.events)
        mode = "events"

    keyed_by_event = any(m.get("keyed_by_event") for m in metrics.values())
    seen_keys = set(metrics)
    used_keys = set()

    out_rows = []
    for feat in features:
        fid = feat["id"]
        events = [str(e) for e in (feat.get("events") or [])]
        row = {
            "id": fid,
            "name": feat.get("name") or fid,
            "status": feat.get("status", "active"),
            "events_mapped": len(events),
            "events_seen": 0,
            "blind_spot": not events,
            "eligible_users": None,
            "adopters": 0,
            "repeat_adopters": None,
            "retained_adopters": None,
            "uses": 0,
        }
        buckets = []
        if keyed_by_event:
            for event in events:
                if event in metrics:
                    buckets.append(metrics[event])
                    used_keys.add(event)
        if fid in metrics:
            buckets.append(metrics[fid])
            used_keys.add(fid)
            row["blind_spot"] = False

        if buckets:
            row["events_seen"] = len(buckets)
            # A user of any of a feature's events is an adopter of the feature,
            # but event-level aggregates cannot be unioned without the user ids.
            # Taking the maximum is the conservative choice and is labelled.
            row["adopters"] = max(b.get("adopters") or 0 for b in buckets)
            eligibles = [b.get("eligible_users") for b in buckets
                         if b.get("eligible_users")]
            row["eligible_users"] = max(eligibles) if eligibles else None
            repeats = [b.get("repeat_adopters") for b in buckets
                       if b.get("repeat_adopters") is not None]
            row["repeat_adopters"] = max(repeats) if repeats else None
            retains = [b.get("retained_adopters") for b in buckets
                       if b.get("retained_adopters") is not None]
            row["retained_adopters"] = max(retains) if retains else None
            row["uses"] = sum(b.get("uses") or 0 for b in buckets)
            trends = [b.get("trend_pct") for b in buckets
                      if b.get("trend_pct") is not None]
            if trends:
                row["trend_pct"] = round(sum(trends) / len(trends), 1)
            arrs = [b.get("arr_touching") for b in buckets
                    if b.get("arr_touching") is not None]
            if arrs:
                row["arr_touching"] = max(arrs)
            if row.get("arr_touching") is not None and revenue:
                total_arr = sum(revenue.values())
                if total_arr:
                    row["arr_share_pct"] = round(
                        100 * row["arr_touching"] / total_arr, 1)
            tops = [b.get("top_account_arr_share_pct") for b in buckets
                    if b.get("top_account_arr_share_pct") is not None]
            if tops:
                row["top_account_arr_share_pct"] = max(tops)
            if len(buckets) > 1:
                row["multi_event_note"] = (
                    "feature has %d measured events; adopters is the maximum "
                    "across them, not a union, so it is a lower bound"
                    % len(buckets))

        if row["eligible_users"]:
            row["breadth_pct"] = inv.pct(row["adopters"], row["eligible_users"])
            row["breadth_ci95"] = wilson(row["adopters"], row["eligible_users"])
        else:
            row["breadth_pct"] = None
        if row["adopters"] and row["repeat_adopters"] is not None:
            row["depth_pct"] = inv.pct(row["repeat_adopters"], row["adopters"])
        else:
            row["depth_pct"] = None
        if row["retained_adopters"] is not None and row["adopters"]:
            row["retention_pct"] = inv.pct(row["retained_adopters"], row["adopters"])

        sig, why = signature(row, th)
        row["signature"] = sig
        row["signature_because"] = why
        out_rows.append(row)

    order = {"blind-spot": 0, "no-data": 1, "dormant": 2, "quiet": 3,
             "value-suspect": 4, "discoverability-suspect": 5,
             "insufficient-data": 6, "in-use": 7}
    out_rows.sort(key=lambda r: (order.get(r["signature"], 9),
                                 r.get("breadth_pct") if r.get("breadth_pct")
                                 is not None else 999))

    unmapped = sorted(seen_keys - used_keys)
    tally = {}
    for row in out_rows:
        tally[row["signature"]] = tally.get(row["signature"], 0) + 1

    window_days = args.window_days or measured_window
    report = {
        "root": root,
        "source": source,
        "input_mode": mode,
        "window_days": window_days,
        "window_days_basis": (
            "declared with --window-days" if args.window_days
            else ("measured from timestamps in the export" if measured_window
                  else "unknown: not declared and not derivable from this input")),
        "total_arr": round(sum(revenue.values()), 2) if revenue else None,
        "accounts_with_arr": len(revenue) or None,
        "features": len(out_rows),
        "signature_counts": [{"signature": k, "features": v}
                             for k, v in sorted(tally.items())],
        "thresholds": th.as_dict(),
        "rows": out_rows,
        "events_in_data_not_in_inventory": unmapped[:60],
        "events_in_data_not_in_inventory_total": len(unmapped),
        "caveats": [
            "a signature describes the shape of the data; it is not a "
            "recommendation, and nothing here clears a feature for removal",
            "blind-spot means no events are mapped: an instrumentation gap, "
            "not evidence of disuse",
            "no-data means mapped events are absent from the export, which is "
            "ambiguous between unused and never-instrumented",
            "churned users are absent from every export, so a feature whose "
            "absence drove people away leaves no trace here",
            "separating a discovery problem from a value problem needs "
            "awareness data, which event streams do not contain",
        ],
    }
    if total_users_in_export is not None and not args.eligible:
        report["caveats"].insert(0, (
            "no --eligible supplied, so breadth is computed against the %d "
            "distinct users present in the export; that is an active-user "
            "denominator, not an eligible-user one, and it overstates breadth"
            % total_users_in_export))
    if not window_days:
        report["caveats"].append(
            "the observation window is unknown, so a quiet feature cannot be "
            "distinguished from a seasonal one; pass --window-days")
    elif window_days < 365:
        report["caveats"].append(
            "the window is %d days, under a full year, so annual-cycle "
            "features (tax, renewals, reporting) can look dormant"
            % window_days)
    if unmapped:
        report["caveats"].append(
            "%d event names in the data are not mapped to any feature; the "
            "inventory's events lists are incomplete" % len(unmapped))
    inv.emit(report, args.json)


if __name__ == "__main__":
    main()
