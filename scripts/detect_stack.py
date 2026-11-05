#!/usr/bin/env python3
"""Detect the stack, routing style and analytics/flag vendors in a repo.

Read-only. Prints YAML (or JSON with --json) describing what strip-down found,
so /strip-down:init can write a config file without guessing.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import inv  # noqa: E402

# marker file -> (framework, routing style)
MARKERS = [
    ("next.config.js", "next", None), ("next.config.mjs", "next", None),
    ("next.config.ts", "next", None),
    ("nuxt.config.ts", "nuxt", "file-routes"), ("nuxt.config.js", "nuxt", "file-routes"),
    ("svelte.config.js", "sveltekit", "file-routes"),
    ("remix.config.js", "remix", "file-routes"),
    ("astro.config.mjs", "astro", "file-routes"),
    ("angular.json", "angular", None),
    ("vite.config.ts", "vite", None), ("vite.config.js", "vite", None),
    ("config/routes.rb", "rails", "route-table"),
    ("manage.py", "django", "route-table"),
    ("artisan", "laravel", "route-table"),
    ("go.mod", "go", None),
    ("Cargo.toml", "rust", None),
    ("pom.xml", "java-maven", None), ("build.gradle", "java-gradle", None),
    ("build.gradle.kts", "java-gradle", None),
    ("mix.exs", "phoenix", "route-table"),
    ("composer.json", "php", None),
    ("Gemfile", "ruby", None),
    ("pubspec.yaml", "flutter", None),
    ("requirements.txt", "python", None),
    ("pyproject.toml", "python", None),
    ("package.json", "node", None),
]

# dependency name fragment -> (category, vendor)
DEPS = [
    ("launchdarkly", "flags", "launchdarkly"),
    ("unleash", "flags", "unleash"),
    ("flagsmith", "flags", "flagsmith"),
    ("growthbook", "flags", "growthbook"),
    ("statsig", "flags", "statsig"),
    ("splitio", "flags", "split"),
    ("configcat", "flags", "configcat"),
    ("flipt", "flags", "flipt"),
    ("posthog", "analytics", "posthog"),
    ("mixpanel", "analytics", "mixpanel"),
    ("amplitude", "analytics", "amplitude"),
    ("@segment/", "analytics", "segment"),
    ("analytics-node", "analytics", "segment"),
    ("rudder", "analytics", "rudderstack"),
    ("heap-", "analytics", "heap"),
    ("pendo", "analytics", "pendo"),
    ("plausible", "analytics", "plausible"),
    ("@sentry/", "observability", "sentry"),
    ("stripe", "billing", "stripe"),
    ("@paddle", "billing", "paddle"),
    ("chargebee", "billing", "chargebee"),
    ("recurly", "billing", "recurly"),
]

DEP_FILES = (
    "package.json", "requirements.txt", "pyproject.toml", "Gemfile",
    "go.mod", "Cargo.toml", "composer.json", "pom.xml", "build.gradle",
    "build.gradle.kts", "mix.exs", "Pipfile", "poetry.lock", "pnpm-lock.yaml",
    "yarn.lock", "package-lock.json",
)

ROUTE_DIR_HINTS = (
    ("app/", "next-app-router"), ("src/app/", "next-app-router"),
    ("pages/", "next-pages-router"), ("src/pages/", "next-pages-router"),
    ("src/routes/", "sveltekit"), ("app/routes/", "remix"),
    ("app/controllers/", "rails"), ("routes/", "laravel"),
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = inv.resolve_root(args.root or ".", args.root is not None)
    files = inv.list_files(root)
    fileset = set(files)

    frameworks = []
    routing = []
    for marker, framework, style in MARKERS:
        if marker in fileset or any(f.endswith("/" + marker) for f in files):
            if framework not in frameworks:
                frameworks.append(framework)
            if style and style not in routing:
                routing.append(style)

    vendors = {}
    for name in DEP_FILES:
        matches = [f for f in files if f == name or f.endswith("/" + name)]
        for path in matches[:4]:
            got = inv.read_text(os.path.join(root, path), limit=600000)
            if not got:
                continue
            low = got[0].lower()
            for fragment, category, vendor in DEPS:
                if fragment in low:
                    vendors.setdefault(category, [])
                    if vendor not in vendors[category]:
                        vendors[category].append(vendor)

    for prefix, style in ROUTE_DIR_HINTS:
        if any(f.startswith(prefix) for f in files) and style not in routing:
            routing.append(style)

    langs = {}
    for path in files:
        ext = os.path.splitext(path)[1].lower()
        if ext:
            langs[ext] = langs.get(ext, 0) + 1
    top_langs = sorted(langs.items(), key=lambda kv: -kv[1])[:8]

    git = inv.is_git_repo(root)
    report = {
        "root": root,
        "git": git,
        "files_tracked": len(files),
        "frameworks": frameworks or ["unknown"],
        "routing": routing or ["unknown"],
        "top_extensions": [{"ext": e, "files": c} for e, c in top_langs],
        "vendors": vendors or {},
        "has_inventory": os.path.exists(os.path.join(root, inv.INVENTORY_PATH)),
        "has_config": os.path.exists(os.path.join(root, inv.CONFIG_PATH)),
        "suggested_mode": "has-users" if vendors.get("analytics") else "pre-users",
        "notes": [],
    }
    if not git:
        report["notes"].append(
            "not a git repository: /strip-down:cost cannot run without git history")
    if not vendors.get("analytics"):
        report["notes"].append(
            "no analytics SDK found in dependency files; usage data will have to "
            "come from a CSV export or be treated as unavailable")
    inv.emit(report, args.json)


if __name__ == "__main__":
    main()
