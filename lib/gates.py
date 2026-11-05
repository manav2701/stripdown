"""The seven kill gates.

No feature may be labelled a removal candidate without passing every one of
these. They exist because the failure mode of a tool like this is not being
wrong about a number -- it is being confidently right about a number and wrong
about the world. Each gate is the cheapest available check against one way that
happens.

A gate is "pass", "fail" or "unknown". Only "pass" clears it: an unanswered
gate blocks, because the default has to be that we do not know. Three gates
(contractual, regulatory, migration) rest partly on facts only a human has, so
a fresh inventory blocks everything, and that is the intended behaviour rather
than a usability problem to design away.
"""

import os
import re

GATE_ORDER = ("instrumentation", "dormancy", "dependency", "regulatory",
              "contractual", "revenue", "migration")

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"

# Feature classes that are never removed on usage evidence alone, because the
# obligation to provide them does not come from how often they are used.
REGULATED_TERMS = (
    "audit", "audit log", "audit trail", "export", "data export",
    "gdpr", "ccpa", "dsar", "dsr", "consent", "cookie", "privacy",
    "account deletion", "delete account", "deletion", "erasure",
    "right to be forgotten",
    "data retention", "retention policy", "legal hold", "ediscovery",
    "accessibility", "a11y", "wcag", "screen reader", "aria",
    "two factor", "two-factor", "2fa", "mfa", "sso", "saml", "scim", "oauth",
    "encryption", "kms", "backup", "disaster recovery", "soc2", "soc 2",
    "hipaa", "pci", "iso27001", "kyc", "aml", "sanction",
    "tax", "vat", "gst", "invoice", "receipt", "billing statement",
    "terms", "dpa", "subprocessor", "security", "rbac", "permission",
)

CONTRACT_DOC_HINTS = (
    "openapi", "swagger", "terms", "tos", "sla", "dpa", "msa", "contract",
    "soc2", "soc-2", "security.txt", ".well-known", "public-api", "api-spec",
    "changelog", "deprecation",
)


def _haystack(feature):
    parts = [str(feature.get("id") or ""), str(feature.get("name") or "")]
    parts += [str(t) for t in (feature.get("tags") or [])]
    parts += [str(p) for p in (feature.get("paths") or [])]
    text = " ".join(parts).lower()
    return re.sub(r"[_\-/*.]+", " ", text)


def regulated_terms_matching(feature):
    hay = " %s " % _haystack(feature)
    out = []
    for term in REGULATED_TERMS:
        # Allow the plural, so "invoices" matches "invoice". Over-matching is
        # the intended bias: a false positive costs one line in `notes`, a
        # false negative could remove a legal obligation.
        pattern = r"(?<![a-z])%s(?:s|es)?(?![a-z])" % re.escape(term)
        if re.search(pattern, hay):
            out.append(term)
    return out


def contract_evidence(root, files, feature, read_text, limit=5):
    """Files that look contractual and mention this feature by name.

    Evidence for a human, never a decision. Absence proves nothing: the
    contract is usually not in the repository.
    """
    needles = {str(feature.get("id") or "").lower()}
    name = str(feature.get("name") or "").lower()
    if name:
        needles.add(name)
    needles = {n for n in needles if len(n) >= 4}
    if not needles:
        return []
    hits = []
    for path in files:
        low = path.lower()
        if not any(hint in low for hint in CONTRACT_DOC_HINTS):
            continue
        got = read_text(os.path.join(root, path))
        if not got:
            continue
        body = got[0].lower()
        for needle in needles:
            if needle in body:
                hits.append({"file": path, "mentions": needle})
                break
        if len(hits) >= limit:
            break
    return hits


class Context(object):
    """Everything the gates need that is not on the feature itself."""

    def __init__(self, window_days=None, seasonal_days=365,
                 arr_share_limit=5.0, top_account_limit=50.0,
                 dormant_breadth=1.0, dep_index=None, root=None, files=None,
                 read_text=None, has_revenue=False):
        self.window_days = window_days
        self.seasonal_days = seasonal_days
        self.arr_share_limit = arr_share_limit
        self.top_account_limit = top_account_limit
        self.dormant_breadth = dormant_breadth
        self.dep_index = dep_index
        self.root = root
        self.files = files or []
        self.read_text = read_text
        self.has_revenue = has_revenue

    def as_dict(self):
        return {
            "window_days": self.window_days,
            "seasonal_cycle_days": self.seasonal_days,
            "arr_share_limit_pct": self.arr_share_limit,
            "top_account_share_limit_pct": self.top_account_limit,
            "dormant_breadth_pct": self.dormant_breadth,
            "revenue_data_supplied": self.has_revenue,
        }


def _gate(state, because, **extra):
    out = {"state": state, "because": because}
    out.update(extra)
    return out


def gate_instrumentation(feature, usage, ctx):
    if usage is None:
        return _gate(UNKNOWN, "no usage data has been supplied, so nothing is "
                              "known about this feature's use")
    sig = usage.get("signature")
    if sig == "blind-spot":
        return _gate(FAIL, "no events are mapped to this feature: an "
                           "instrumentation gap, not evidence of disuse")
    if sig == "no-data":
        return _gate(FAIL, "mapped events are absent from the export, which is "
                           "ambiguous between unused and never instrumented")
    if sig == "insufficient-data":
        return _gate(FAIL, usage.get("signature_because")
                     or "the data is too thin to support a rate")
    return _gate(PASS, "the feature is measured and the data supports a rate")


def gate_dormancy(feature, usage, ctx):
    if usage is None:
        return _gate(UNKNOWN, "no usage data supplied")
    if not ctx.window_days:
        return _gate(UNKNOWN, "the observation window is unknown, so a quiet "
                              "feature cannot be told from a seasonal one; "
                              "pass --window-days to usage")
    if ctx.window_days < ctx.seasonal_days:
        return _gate(FAIL, "the window is %d days, short of a full %d-day "
                           "cycle, so an annual feature (tax, renewals, "
                           "reporting) could look dead"
                           % (ctx.window_days, ctx.seasonal_days))
    adopters = usage.get("adopters") or 0
    breadth = usage.get("breadth_pct")
    if adopters == 0:
        return _gate(PASS, "nobody used it across a full %d-day cycle"
                           % ctx.window_days)
    if breadth is not None and breadth < ctx.dormant_breadth:
        return _gate(PASS, "%d users over a full cycle, %.1f%% breadth, below "
                           "the %.1f%% dormancy floor"
                           % (adopters, breadth, ctx.dormant_breadth))
    return _gate(FAIL, "%d people still use it; removing a feature with live "
                       "users is a product decision with a migration plan, not "
                       "a usage threshold" % adopters)


def gate_dependency(feature, usage, ctx, feature_files=None):
    if ctx.dep_index is None:
        return _gate(UNKNOWN, "no dependency index was built")
    files = feature_files or []
    if not files:
        return _gate(UNKNOWN, "no files are attributed to this feature")
    hits, total = ctx.dep_index.inbound(files)
    if total:
        return _gate(FAIL, "%d static imports reach into this feature from "
                           "outside it" % total, inbound_examples=hits,
                     inbound_total=total)
    return _gate(PASS, "no static import crosses into this feature, which is "
                       "weaker than 'nothing depends on it': dynamic requires, "
                       "DI containers, autoloading, shared tables and HTTP "
                       "callers are not visible to this check")


def gate_regulatory(feature, usage, ctx):
    from inv import gate_value  # local import: lib is on sys.path by then
    declared = gate_value(feature.get("gates"), "regulated")
    matched = regulated_terms_matching(feature)
    if declared == "yes":
        return _gate(FAIL, "marked as regulated in the inventory",
                     matched_terms=matched)
    if matched and declared == "no":
        if str(feature.get("notes") or "").strip():
            return _gate(PASS, "named like a regulated feature (%s) but "
                               "explicitly marked not regulated, with a "
                               "recorded reason" % ", ".join(matched[:4]),
                         matched_terms=matched)
        return _gate(UNKNOWN, "named like a regulated feature (%s) and marked "
                              "not regulated with no reason recorded; put the "
                              "justification in notes"
                              % ", ".join(matched[:4]), matched_terms=matched)
    if matched:
        return _gate(FAIL, "the name or paths suggest a legal, security or "
                           "accessibility obligation (%s); such features are "
                           "never removed on usage evidence alone"
                           % ", ".join(matched[:4]), matched_terms=matched)
    if declared == "no":
        return _gate(PASS, "marked not regulated and nothing in the name "
                           "suggests otherwise")
    return _gate(UNKNOWN, "gates.regulated is unanswered; only a human can "
                          "answer it")


def gate_contractual(feature, usage, ctx):
    from inv import gate_value
    declared = gate_value(feature.get("gates"), "contractual")
    public = gate_value(feature.get("gates"), "public_api")
    evidence = []
    if ctx.root and ctx.read_text:
        evidence = contract_evidence(ctx.root, ctx.files, feature, ctx.read_text)
    if declared == "yes":
        return _gate(FAIL, "named in a contract, SLA or agreement",
                     evidence=evidence)
    if public == "yes":
        return _gate(FAIL, "part of a public API or integration surface that "
                           "others build on", evidence=evidence)
    if declared == "unknown" or public == "unknown":
        return _gate(UNKNOWN, "gates.contractual or gates.public_api is "
                              "unanswered; the contract is usually not in the "
                              "repository, so only a human can answer this",
                     evidence=evidence)
    if evidence:
        return _gate(UNKNOWN, "marked as not contractual, but %d "
                              "contract-shaped file(s) in the repo mention it; "
                              "confirm before proceeding" % len(evidence),
                     evidence=evidence)
    return _gate(PASS, "marked not contractual and not a public API surface; "
                       "note that an absence of evidence in the repo is not "
                       "evidence of absence")


def gate_revenue(feature, usage, ctx):
    if usage is None:
        return _gate(UNKNOWN, "no usage data supplied")
    if not ctx.has_revenue:
        return _gate(UNKNOWN, "no revenue data supplied, so revenue at risk is "
                              "unknown; pass --revenue to usage")
    share = usage.get("arr_share_pct")
    top = usage.get("top_account_arr_share_pct")
    arr = usage.get("arr_touching")
    if not arr:
        return _gate(PASS, "no revenue is attached to the accounts that use it")
    if share is not None and share > ctx.arr_share_limit:
        return _gate(FAIL, "accounts touching this feature hold %.1f%% of ARR, "
                           "above the %.1f%% limit"
                           % (share, ctx.arr_share_limit))
    if top is not None and top > ctx.top_account_limit:
        return _gate(FAIL, "%.1f%% of the revenue touching this feature sits in "
                           "a single account; a rarely used feature can still "
                           "be load-bearing for your largest customer" % top)
    return _gate(PASS, "revenue exposure is %.1f%% of ARR, below the %.1f%% "
                       "limit" % (share or 0.0, ctx.arr_share_limit))


def gate_migration(feature, usage, ctx):
    plan = str(feature.get("migration") or "").strip()
    if plan:
        return _gate(PASS, "a migration path is recorded in the inventory")
    adopters = (usage or {}).get("adopters")
    if usage is not None and adopters == 0:
        return _gate(PASS, "nobody is using it, so there is nobody to migrate")
    return _gate(UNKNOWN, "no migration path recorded and the feature has "
                          "users; add a `migration:` note to the feature or "
                          "run /strip-down:sunset to draft one")


def evaluate(feature, usage, ctx, feature_files=None):
    results = {
        "instrumentation": gate_instrumentation(feature, usage, ctx),
        "dormancy": gate_dormancy(feature, usage, ctx),
        "dependency": gate_dependency(feature, usage, ctx, feature_files),
        "regulatory": gate_regulatory(feature, usage, ctx),
        "contractual": gate_contractual(feature, usage, ctx),
        "revenue": gate_revenue(feature, usage, ctx),
        "migration": gate_migration(feature, usage, ctx),
    }
    return {name: results[name] for name in GATE_ORDER}


def summarise(results):
    failed = [n for n in GATE_ORDER if results[n]["state"] == FAIL]
    unknown = [n for n in GATE_ORDER if results[n]["state"] == UNKNOWN]
    return {
        "passed": [n for n in GATE_ORDER if results[n]["state"] == PASS],
        "failed": failed,
        "unknown": unknown,
        "all_clear": not failed and not unknown,
    }
