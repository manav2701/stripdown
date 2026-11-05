#!/usr/bin/env python3
"""Check .stripdown/inventory.yml: schema, path coverage, overlaps, blind spots.

Exit codes: 0 valid, 1 valid with warnings, 2 invalid.
Run this after hand-editing the inventory, and in CI if you want the inventory
to stay honest as the codebase moves.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import inv  # noqa: E402
import sdyaml  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None)
    ap.add_argument("--strict", action="store_true",
                    help="also warn about unanswered gates")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    path = os.path.join(root, inv.INVENTORY_PATH)
    if not os.path.exists(path):
        inv.die("no %s" % inv.INVENTORY_PATH)
    try:
        data = sdyaml.load(path)
    except sdyaml.YamlError as exc:
        inv.die("%s: %s" % (inv.INVENTORY_PATH, exc))

    errors, warnings = inv.validate(data, strict=args.strict)
    features = data.get("features") or [] if isinstance(data, dict) else []

    report = {"inventory": inv.INVENTORY_PATH, "features": len(features)}

    if not errors and features:
        files = inv.list_files(root)
        matcher = inv.Matcher(features)
        assigned = matcher.assign(files)
        report["files_total"] = len(files)
        report["files_attributed"] = sum(len(v) for v in assigned.values())
        report["coverage_pct"] = inv.pct(report["files_attributed"], len(files))
        dead = [f["id"] for f in features if not assigned.get(f["id"])]
        if dead:
            report["features_matching_no_files"] = dead
            for fid in dead:
                errors.append(
                    "feature %r matches no files; its paths are wrong or the "
                    "code is already gone" % fid)
        if matcher.overlaps:
            report["overlapping_files"] = len(matcher.overlaps)
            report["overlap_examples"] = [
                {"file": f, "features": ids}
                for f, ids in sorted(matcher.overlaps.items())[:10]
            ]
            warnings.append(
                "%d files match more than one feature; the most specific "
                "pattern wins, which may not be what you meant"
                % len(matcher.overlaps))
        blind = [f["id"] for f in features if not (f.get("events") or [])]
        if blind:
            report["blind_spots"] = blind
            warnings.append(
                "%d of %d features have no events mapped; their usage cannot "
                "be assessed" % (len(blind), len(features)))
        dupe_events = {}
        for feat in features:
            for event in feat.get("events") or []:
                dupe_events.setdefault(str(event), []).append(feat["id"])
        shared = {e: ids for e, ids in dupe_events.items() if len(ids) > 1}
        if shared:
            report["events_shared_between_features"] = shared
            warnings.append(
                "%d event names are mapped to more than one feature, so usage "
                "will be double counted" % len(shared))

    report["errors"] = errors
    report["warnings"] = warnings
    report["verdict"] = "invalid" if errors else ("warnings" if warnings else "valid")
    inv.emit(report, args.json)
    raise SystemExit(2 if errors else (1 if warnings else 0))


if __name__ == "__main__":
    main()
