#!/usr/bin/env python3
"""Validate .stripdown/demand.yml: every external claim graded and sourced.

Demand research is where a language model is most likely to produce confident
fiction. "The market wants X" is exactly the shape of claim that comes out
fluent, unfalsifiable and useless -- and worse than silence, because it is
persuasive.

So the discipline is mechanical rather than aspirational. Every claim carries a
grade, and the grade determines what it is allowed to do:

  A  your own data: the repository, git history, your analytics, your revenue.
     Source must be a local artifact path or "own-data:<what>".
  B  a primary public source fetched this run: a competitor's pricing page,
     a changelog, official docs. Needs an https URL and a fetch date.
  C  public discussion: Hacker News, GitHub issues, app-store reviews.
     Needs an https URL and a fetch date. Lower weight than B on purpose.
  D  model inference with no source. MAY NOT justify anything. Must be
     phrased as a question, and `supports` must be empty.

A D-grade claim that asserts rather than asks, or that points at a feature as
justification, is an error, not a warning. That rule is the only thing standing
between this and a plausible-sounding hallucination with a feature id attached.

Exit codes: 0 valid, 1 valid with warnings, 2 invalid.
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import inv  # noqa: E402
import sdyaml  # noqa: E402

CLAIMS_PATH = os.path.join(inv.STATE_DIR, "demand.yml")
GRADES = ("A", "B", "C", "D")
KINDS = ("competitor", "signal", "gap", "scope", "other")
URL_RE = re.compile(r"^https://[^\s]+$", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Sources that masquerade as evidence. Scraping these is against their terms,
# and their reviews are vendor-solicited, so a claim sourced from one is
# downgraded with a reason rather than silently accepted.
DISCOURAGED_HOSTS = {
    "g2.com": "G2 prohibits scraping and its reviews are vendor-solicited, "
              "sometimes with incentives; treat as low-grade and say so",
    "capterra.com": "Capterra prohibits scraping; same solicitation bias",
    "trustradius.com": "TrustRadius prohibits scraping; same solicitation bias",
    "reddit.com": "Reddit's API is free only for non-commercial use and "
                  "commercial access is a negotiated contract; cite a specific "
                  "thread a human opened, not a scrape",
    "trends.google.com": "Google Trends has no usable public API: the official "
                         "one is an application-only alpha and pytrends is "
                         "archived. Do not build a claim on it",
}


def host_of(url):
    match = re.match(r"^https://([^/]+)", url or "", re.I)
    if not match:
        return ""
    return match.group(1).lower().lstrip("www.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    path = os.path.join(root, CLAIMS_PATH)
    if not os.path.exists(path):
        inv.die("no %s; /strip-down:demand writes it" % CLAIMS_PATH)
    try:
        data = sdyaml.load(path)
    except sdyaml.YamlError as exc:
        inv.die("%s: %s" % (CLAIMS_PATH, exc))

    errors, warnings = [], []
    claims = data.get("claims") if isinstance(data, dict) else None
    if claims is None:
        inv.die("%s has no 'claims' list" % CLAIMS_PATH)
    if not isinstance(claims, list):
        inv.die("'claims' must be a list")

    known_features = set()
    inventory = inv.load_inventory(root, required=False)
    if inventory:
        known_features = {f["id"] for f in inventory.get("features") or []}

    seen = set()
    by_grade = {g: 0 for g in GRADES}
    usable = []
    for idx, claim in enumerate(claims):
        where = "claims[%d]" % idx
        if not isinstance(claim, dict):
            errors.append("%s is not a mapping" % where)
            continue
        cid = claim.get("id")
        if not cid or not ID_RE.match(str(cid)):
            errors.append("%s: id must be lowercase a-z0-9, - or _" % where)
            cid = cid or where
        where = "claim %r" % cid
        if cid in seen:
            errors.append("%s: duplicate id" % where)
        seen.add(cid)

        text = str(claim.get("claim") or "").strip()
        if not text:
            errors.append("%s: empty claim text" % where)

        grade = str(claim.get("grade") or "").strip().upper()
        if grade not in GRADES:
            errors.append("%s: grade must be one of A/B/C/D, got %r"
                          % (where, claim.get("grade")))
            continue
        by_grade[grade] += 1

        kind = str(claim.get("kind") or "other").strip().lower()
        if kind not in KINDS:
            warnings.append("%s: unusual kind %r (expected %s)"
                            % (where, kind, "/".join(KINDS)))

        source = str(claim.get("source") or "").strip()
        fetched = str(claim.get("fetched") or "").strip()
        supports = claim.get("supports") or []
        if not isinstance(supports, list):
            errors.append("%s: supports must be a list" % where)
            supports = []

        if grade == "A":
            if not source:
                errors.append("%s: grade A needs a source naming your own "
                              "artifact (a path, or own-data:<what>)" % where)
            elif URL_RE.match(source):
                errors.append("%s: grade A means your own data; an external "
                              "URL cannot be grade A" % where)
        elif grade in ("B", "C"):
            if not URL_RE.match(source):
                errors.append("%s: grade %s needs an https URL as its source"
                              % (where, grade))
            if not DATE_RE.match(fetched):
                errors.append("%s: grade %s needs fetched: YYYY-MM-DD, so a "
                              "stale citation can be spotted" % (where, grade))
            host = host_of(source)
            for bad, why in DISCOURAGED_HOSTS.items():
                if host.endswith(bad):
                    warnings.append("%s: %s" % (where, why))
        else:  # D
            if supports:
                errors.append(
                    "%s: grade D is model inference with no source and may not "
                    "justify anything; `supports` must be empty (it names %s)"
                    % (where, ", ".join(str(s) for s in supports)))
            if text and not text.rstrip().endswith("?"):
                errors.append(
                    "%s: grade D must be phrased as a question, so it cannot "
                    "be mistaken for a finding" % where)
            if source:
                warnings.append("%s: grade D has a source; if the source "
                                "supports it, grade it B or C instead" % where)

        for ref in supports:
            if known_features and str(ref) not in known_features \
                    and str(ref) != "scope":
                warnings.append("%s: supports %r, which is not a feature id in "
                                "the inventory" % (where, ref))

        if grade in ("A", "B", "C"):
            usable.append({"id": cid, "grade": grade, "kind": kind,
                           "supports": [str(s) for s in supports]})

    report = {
        "claims_file": CLAIMS_PATH,
        "claims": len(claims),
        "by_grade": [{"grade": g, "claims": by_grade[g]} for g in GRADES],
        "usable_as_justification": usable,
        "unusable_grade_d": by_grade["D"],
        "errors": errors,
        "warnings": warnings,
        "verdict": "invalid" if errors else ("warnings" if warnings else "valid"),
        "reminder": "grade D claims are questions, not findings, and justify "
                    "nothing. A claim with no fetched source is grade D no "
                    "matter how plausible it sounds.",
    }
    if not usable and claims:
        report["warnings"].append(
            "no claim is usable as justification: every one is grade D or "
            "invalid, which means this research found nothing citable")
        report["verdict"] = "invalid" if errors else "warnings"
    inv.emit(report, args.json)
    raise SystemExit(2 if errors else (1 if report["warnings"] else 0))


if __name__ == "__main__":
    main()
