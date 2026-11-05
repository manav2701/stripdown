#!/usr/bin/env python3
"""Scan a repository for structural evidence of user-facing features.

This emits *signals*, not features. A signal is one piece of evidence -- a
route, a feature-flag check, an analytics call, a queue worker -- with the file
and line it came from. Grouping signals into features is a judgment call about
product granularity that this script deliberately does not make; that is the
model's job in /strip-down:inventory, with a human reviewing the result.

The method is regex over text, which has known and permanent limits:
  * dynamically registered routes, flags read from a database, and
    metaprogrammed handlers are invisible to it
  * a commented-out or dead call site looks exactly like a live one
  * string concatenation hides names ("track('user_' + verb)")
So treat the output as a candidate list to review, never as a complete
inventory. The one number here that is close to trustworthy is the set of
analytics event names, because those are nearly always literals.

Read-only: nothing is written and no network is used.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import inv  # noqa: E402

JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".svelte", ".vue", ".astro")
PY = (".py",)
RB = (".rb", ".erb", ".rake")
PHP = (".php",)
GO = (".go",)
JAVA = (".java", ".kt", ".kts", ".scala")
CS = (".cs",)
EX = (".ex", ".exs")
RS = (".rs",)
SWIFT = (".swift", ".m", ".mm")
DART = (".dart",)
WEB = JS + PY + RB + PHP + GO + JAVA + CS + EX + RS + SWIFT + DART
SQL = (".sql",)
GQL = (".graphql", ".gql")

# (type, label, extensions or None for any text file, cheap needle, regex)
# The regex may define a group named "n" to capture the signal's name.
P = [
    # ---------- analytics events (highest-confidence signal here) ----------
    ("event", "posthog", JS, ".capture(",
     r"""posthog(?:\.[\w$]+)*\.capture\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "posthog", PY, ".capture(",
     r"""capture\(\s*[^,()]{1,80},\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "segment", WEB, ".track(",
     r"""(?:analytics|segment|client)\.track\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "mixpanel", WEB, "mixpanel",
     r"""mixpanel(?:\.[\w$]+)*\.track\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "amplitude", WEB, "amplitude",
     r"""amplitude(?:\.[\w$]+)*\.(?:track|logEvent)\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "generic", WEB, "logevent(",
     r"""logEvent\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "generic", WEB, ("trackevent(", "track_event("),
     r"""track_?[Ee]vent\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "gtag", JS, "gtag(",
     r"""gtag\(\s*['"]event['"]\s*,\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "rudderstack", JS, "rudderanalytics",
     r"""rudderanalytics\.track\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("event", "generic", RB, "track(",
     r"""(?:analytics|tracker)\.track\(\s*[^,()]{0,60}event:\s*['"](?P<n>[^'"]{1,120})['"]"""),

    # ---------- feature flags ----------
    ("flag", "launchdarkly", WEB, "variation",
     r"""(?:bool|string|int|json|number)?[Vv]ariation\w*\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "posthog", WEB, ("isfeatureenabled", "is_feature_enabled"),
     r"""is_?[Ff]eature_?[Ee]nabled\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "posthog", WEB, ("getfeatureflag", "get_feature_flag"),
     r"""get_?[Ff]eature_?[Ff]lag\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "unleash", WEB, ("isenabled(", "is_enabled("),
     r"""is[Ee]nabled\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "flagsmith", WEB, ("hasfeature", "has_feature"),
     r"""has_?[Ff]eature\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "growthbook", WEB, ".ison(",
     r"""\.isOn\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "growthbook", WEB, ("getfeaturevalue", "get_feature_value"),
     r"""get_?[Ff]eature_?[Vv]alue\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "statsig", WEB, ("checkgate", "check_gate"),
     r"""check_?[Gg]ate\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "split", WEB, ("gettreatment", "get_treatment"),
     r"""get_?[Tt]reatment\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("flag", "generic", WEB, "featureflag",
     r"""featureFlags?\.(?P<n>[A-Za-z_][\w]{2,60})\b"""),
    ("flag", "generic", WEB, "flags.",
     r"""\bflags\.(?P<n>[A-Za-z_][\w]{2,60})\b"""),
    ("flag", "env", None, "feature_",
     r"""\b(?P<n>(?:FEATURE|ENABLE|DISABLE)_[A-Z0-9_]{2,60})\b"""),

    # ---------- entitlements / plan gating ----------
    ("entitlement", "permission", WEB, ("haspermission", "has_permission"),
     r"""has_?[Pp]ermission\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("entitlement", "ability", RB, "can?(",
     r"""\bcan\?\(\s*:(?P<n>\w{2,60})"""),
    ("entitlement", "role", WEB, ("requirerole", "require_role"),
     r"""require_?[Rr]ole\(\s*['"](?P<n>[^'"]{1,120})['"]"""),
    ("entitlement", "plan", WEB, ("plan", "tier"),
     r"""\b(?:plan|tier)\s*(?:===?|!==?|in)\s*['"](?P<n>[^'"]{1,60})['"]"""),
    ("entitlement", "entitlement", WEB, "entitlement",
     r"""entitlements?(?:\.|\[['"])(?P<n>[\w-]{2,60})"""),
    ("entitlement", "paywall", WEB, ("ispro", "ispremium", "isenterprise", "ispaid", "istrial"),
     r"""\b(?P<n>is(?:Pro|Premium|Enterprise|Paid|Trial)\w*)\b"""),
    ("entitlement", "spring", JAVA, "preauthorize",
     r"""@PreAuthorize\(\s*['"](?P<n>[^'"]{1,120})['"]"""),

    # ---------- explicit route tables ----------
    ("route", "express", JS, None,
     r"""(?:app|router|server|api)\.(?:get|post|put|patch|delete|all)\(\s*['"`](?P<n>/[^'"`]{0,160})['"`]"""),
    ("route", "fastify", JS, ".route(",
     r"""\.route\(\s*\{\s*(?:method:[^,]+,\s*)?url:\s*['"`](?P<n>/[^'"`]{0,160})['"`]"""),
    ("route", "nestjs", JS, "@controller",
     r"""@Controller\(\s*['"](?P<n>[^'"]{0,120})['"]"""),
    ("route", "fastapi", PY, None,
     r"""@(?:app|router|api)\.(?:get|post|put|patch|delete)\(\s*['"](?P<n>/[^'"]{0,160})['"]"""),
    ("route", "flask", PY, ".route(",
     r"""@\w+\.route\(\s*['"](?P<n>/[^'"]{0,160})['"]"""),
    ("route", "django", PY, "path(",
     r"""(?:^|\s)(?:path|re_path|url)\(\s*r?['"](?P<n>[^'"]{0,160})['"]"""),
    ("route", "rails", RB, "resources",
     r"""(?:^|\s)resources?\s+:(?P<n>\w{2,60})"""),
    ("route", "rails", RB, "get ",
     r"""(?:^|\s)(?:get|post|put|patch|delete)\s+['"](?P<n>[^'"]{1,160})['"]"""),
    ("route", "laravel", PHP, "route::",
     r"""Route::(?:get|post|put|patch|delete|any|resource)\(\s*['"](?P<n>[^'"]{0,160})['"]"""),
    ("route", "spring", JAVA, "mapping(",
     r"""@(?:Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:value\s*=\s*)?['"](?P<n>[^'"]{0,160})['"]"""),
    ("route", "aspnet", CS, "[http",
     r"""\[Http(?:Get|Post|Put|Patch|Delete)\(\s*['"](?P<n>[^'"]{0,160})['"]"""),
    ("route", "go", GO, "handlefunc",
     r"""(?:HandleFunc|Handle)\(\s*['"`](?P<n>/[^'"`]{0,160})['"`]"""),
    ("route", "go-chi", GO, ".get(",
     r"""\.(?:Get|Post|Put|Patch|Delete)\(\s*['"`](?P<n>/[^'"`]{0,160})['"`]"""),
    ("route", "phoenix", EX, "get \"",
     r"""(?:^|\s)(?:get|post|put|patch|delete|resources)\s+"(?P<n>[^"]{1,160})\""""),
    ("route", "rust-axum", RS, ".route(",
     r"""\.route\(\s*"(?P<n>/[^"]{0,160})\""""),

    # ---------- background work ----------
    ("job", "celery", PY, "task",
     r"""@(?:shared_task|celery\.task|app\.task)[\s(]*.{0,80}?\n?\s*def\s+(?P<n>\w+)"""),
    ("job", "sidekiq", RB, "sidekiq",
     r"""class\s+(?P<n>\w+)\s*<?.{0,40}(?:Worker|Job)"""),
    ("job", "bullmq", JS, ("new queue(", "new worker("),
     r"""new\s+(?:Queue|Worker)\(\s*['"](?P<n>[^'"]{1,80})['"]"""),
    ("job", "cron", None, "cron",
     r"""(?:cron|schedule)\s*[:=]\s*['"](?P<n>[-\d*/,\s]{5,40})['"]"""),
    ("job", "spring", JAVA, "@scheduled",
     r"""@Scheduled"""),
    ("job", "django-command", PY, "class command",
     r"""class\s+Command\b"""),
    ("webhook", "handler", WEB, "webhook",
     r"""['"`](?P<n>/[\w/.:{}$-]*webhooks?[\w/.:{}$-]*)['"`]"""),

    # ---------- CLI surfaces ----------
    ("cli", "argparse", PY, "add_parser",
     r"""add_parser\(\s*['"](?P<n>[^'"]{1,60})['"]"""),
    ("cli", "click", PY, "@click",
     r"""@click\.(?:command|group)\("""),
    ("cli", "commander", JS, ".command(",
     r"""\.command\(\s*['"](?P<n>[^'"]{1,80})['"]"""),
    ("cli", "cobra", GO, "cobra.command",
     r"""Use:\s*['"](?P<n>[^'"]{1,60})['"]"""),

    # ---------- data model ----------
    ("table", "sql", SQL, "create table",
     r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(?P<n>[\w.]{2,80})"""),
    ("table", "django", PY, "models.model",
     r"""class\s+(?P<n>\w+)\s*\(\s*(?:models\.)?Model"""),
    ("table", "sqlalchemy", PY, "__tablename__",
     r"""__tablename__\s*=\s*['"](?P<n>[\w]{2,80})['"]"""),
    ("table", "prisma", (".prisma",), "model ",
     r"""^\s*model\s+(?P<n>\w+)\s*\{"""),
    ("table", "typeorm", JS, "@entity",
     r"""@Entity\("""),
    ("table", "activerecord", RB, "create_table",
     r"""create_table\s+:?['"]?(?P<n>\w{2,80})"""),
    ("table", "knex", JS, "createtable",
     r"""createTable\(\s*['"](?P<n>[\w]{2,80})['"]"""),

    # ---------- graphql ----------
    ("graphql", "sdl", GQL, "type ",
     r"""^\s*(?:type|input|enum)\s+(?P<n>\w+)"""),
    ("graphql", "resolver", JS, "@resolver",
     r"""@(?:Resolver|Query|Mutation)\("""),
]

FILE_ROUTES = [
    # (label, regex over the repo-relative path, how to name it)
    ("next-app-router", re.compile(
        r"^(?:src/)?app/(?P<n>.*?)/?(?:page|route)\.(?:js|jsx|ts|tsx)$")),
    ("next-pages-router", re.compile(
        r"^(?:src/)?pages/(?!_app|_document|_error)(?P<n>.+)\.(?:js|jsx|ts|tsx)$")),
    ("sveltekit", re.compile(
        r"^src/routes/(?P<n>.*?)/?\+(?:page|server|layout)[\w.]*\.(?:svelte|ts|js)$")),
    ("remix", re.compile(r"^app/routes/(?P<n>.+)\.(?:tsx|jsx|ts|js)$")),
    ("nuxt", re.compile(r"^(?:src/)?pages/(?P<n>.+)\.vue$")),
    ("astro", re.compile(r"^src/pages/(?P<n>.+)\.(?:astro|md|mdx)$")),
    ("rails-controller", re.compile(
        r"^app/controllers/(?P<n>.+)_controller\.rb$")),
    ("rails-view", re.compile(r"^app/views/(?P<n>[^/]+)/")),
    ("django-app", re.compile(r"^(?P<n>[\w]+)/(?:views|urls)\.py$")),
    ("laravel-controller", re.compile(
        r"^app/Http/Controllers/(?P<n>.+)Controller\.php$")),
]

COMPILED = []
for stype, label, exts, needle, pattern in P:
    _rx = re.compile(pattern, re.MULTILINE)
    COMPILED.append((stype, label, exts, needle, _rx, "n" in _rx.groupindex))

MAX_LINE = 400
SAMPLES = 6


def scan_file(root, path, out, counts):
    ext = os.path.splitext(path)[1].lower()
    got = inv.read_text(os.path.join(root, path))
    if not got:
        return False
    text, truncated = got
    low = text.lower()
    for stype, label, exts, needle, rx, has_name in COMPILED:
        if exts is not None and ext not in exts:
            continue
        if needle:
            if isinstance(needle, tuple):
                if not any(nd in low for nd in needle):
                    continue
            elif needle not in low:
                continue
        for match in rx.finditer(text):
            name = (match.group("n") or "").strip() if has_name else ""
            line = text.count("\n", 0, match.start()) + 1
            evidence = match.group(0).replace("\n", " ").strip()[:160]
            out.append({
                "type": stype, "label": label, "name": name[:160],
                "file": path, "line": line, "evidence": evidence,
            })
            counts[stype] = counts.get(stype, 0) + 1
    return truncated


def scan_paths(files, out, counts):
    for path in files:
        for label, rx in FILE_ROUTES:
            match = rx.match(path)
            if not match:
                continue
            name = (match.groupdict().get("n") or "").strip("/")
            if not name:
                name = "/"
            out.append({
                "type": "route", "label": label, "name": name,
                "file": path, "line": 1, "evidence": "file-based route",
            })
            counts["route"] = counts.get("route", 0) + 1
            break


def top_dirs(signals, limit=15):
    tally = {}
    for sig in signals:
        parts = sig["file"].split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
        tally[key] = tally.get(key, 0) + 1
    ranked = sorted(tally.items(), key=lambda kv: -kv[1])[:limit]
    return [{"dir": d, "signals": c} for d, c in ranked]


def dedupe_names(signals, stype):
    names = {}
    for sig in signals:
        if sig["type"] != stype or not sig["name"]:
            continue
        rec = names.setdefault(sig["name"], {"name": sig["name"], "count": 0,
                                             "files": []})
        rec["count"] += 1
        if sig["file"] not in rec["files"] and len(rec["files"]) < 5:
            rec["files"].append(sig["file"])
    return sorted(names.values(), key=lambda r: (-r["count"], r["name"]))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None,
                    help="directory to scan (default: the git repository root)")
    ap.add_argument("--type", action="append", dest="types",
                    help="only this signal type; repeatable")
    ap.add_argument("--names", metavar="TYPE",
                    help="list deduplicated names for one type (use 'event' to "
                         "get the analytics event inventory)")
    ap.add_argument("--all", action="store_true",
                    help="emit every signal rather than a summary")
    ap.add_argument("--limit", type=int, default=400,
                    help="cap on signals emitted with --all/--type (default 400)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    files = [f for f in inv.list_files(root) if inv.is_texty(f)]

    signals = []
    counts = {}
    truncated = []
    for path in files:
        if scan_file(root, path, signals, counts):
            truncated.append(path)
    scan_paths(files, signals, counts)

    seen = set()
    deduped = []
    for sig in signals:
        key = (sig["type"], sig["name"], sig["file"], sig["line"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sig)
    signals = deduped
    counts = {}
    for sig in signals:
        counts[sig["type"]] = counts.get(sig["type"], 0) + 1

    if args.types:
        wanted = set(args.types)
        signals = [s for s in signals if s["type"] in wanted]

    header = {
        "root": root,
        "files_scanned": len(files),
        "signals_found": sum(counts.values()),
        "method": "regex over text; a candidate list to review, not an inventory",
    }
    if truncated:
        header["files_truncated"] = len(truncated)

    if args.names:
        header["names_for"] = args.names
        header["names"] = dedupe_names(signals, args.names)
        inv.emit(header, args.json)
        return

    if args.all or args.types:
        shown = signals[: args.limit]
        header["signals_emitted"] = len(shown)
        if len(signals) > len(shown):
            header["omitted"] = len(signals) - len(shown)
        header["signals"] = shown
        inv.emit(header, args.json)
        return

    header["by_type"] = [
        {"type": t, "count": c}
        for t, c in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    labels = {}
    for sig in signals:
        key = "%s/%s" % (sig["type"], sig["label"])
        labels[key] = labels.get(key, 0) + 1
    header["by_detector"] = [
        {"detector": k, "count": v}
        for k, v in sorted(labels.items(), key=lambda kv: -kv[1])[:25]
    ]
    header["top_directories"] = top_dirs(signals)
    header["event_names"] = dedupe_names(signals, "event")[:60]
    header["samples"] = {}
    for stype in sorted(counts):
        header["samples"][stype] = [
            {"name": s["name"], "file": s["file"], "line": s["line"]}
            for s in signals if s["type"] == stype
        ][:SAMPLES]
    inv.emit(header, args.json)


if __name__ == "__main__":
    main()
