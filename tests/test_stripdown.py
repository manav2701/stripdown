#!/usr/bin/env python3
"""Tests for strip-down. Standard library only: python3 tests/test_stripdown.py"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
FIXTURE = os.path.join(HERE, "fixtures", "sampleapp")
sys.path.insert(0, os.path.join(ROOT, "lib"))

import deps  # noqa: E402
import gates as G  # noqa: E402
import inv  # noqa: E402
import sdyaml  # noqa: E402


def run_script(name, *args):
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, name), "--json"] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return proc.returncode, proc.stdout, proc.stderr


def run_json(name, *args):
    code, out, err = run_script(name, *args)
    if not out.strip():
        raise AssertionError("%s produced no output (exit %d): %s"
                             % (name, code, err))
    return json.loads(out), code, err


def git(repo, *args, **kwargs):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": kwargs.get("author", "Ada"),
        "GIT_AUTHOR_EMAIL": "%s@example.com" % kwargs.get("author", "Ada").lower(),
        "GIT_COMMITTER_NAME": kwargs.get("author", "Ada"),
        "GIT_COMMITTER_EMAIL": "%s@example.com" % kwargs.get("author", "Ada").lower(),
        "GIT_AUTHOR_DATE": kwargs.get("date", "2026-10-01T12:00:00"),
        "GIT_COMMITTER_DATE": kwargs.get("date", "2026-10-01T12:00:00"),
    })
    proc = subprocess.run(["git"] + list(args), cwd=repo, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    if proc.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stdout))
    return proc.stdout


class SdYamlTests(unittest.TestCase):
    def test_round_trip(self):
        data = {
            "version": 1, "mode": "has-users",
            "features": [
                {"id": "a", "name": "A: thing", "paths": ["x/**"],
                 "events": ["e1", "e2"], "tags": [], "notes": "",
                 "gates": {"contractual": "unknown", "regulated": "no"}},
                {"id": "b", "name": "B", "paths": [], "events": [],
                 "gates": {}},
            ],
        }
        self.assertEqual(sdyaml.loads(sdyaml.dumps(data)), data)

    def test_quoting_preserves_ambiguous_scalars(self):
        for value in ["yes", "no", "null", "true", "1.0", "007", "- x", "a: b",
                      "# not a comment", ""]:
            got = sdyaml.loads(sdyaml.dumps({"k": value}))
            self.assertEqual(got["k"], value, "failed on %r" % value)

    def test_comments_and_blank_lines(self):
        text = "# header\nversion: 1\n\nmode: pre-users  # trailing\n"
        self.assertEqual(sdyaml.loads(text), {"version": 1, "mode": "pre-users"})

    def test_hash_inside_quotes_is_kept(self):
        self.assertEqual(sdyaml.loads("k: 'a # b'")["k"], "a # b")

    def test_flow_sequence(self):
        self.assertEqual(sdyaml.loads("tags: [a, b, 'c d']")["tags"],
                         ["a", "b", "c d"])

    def test_rejects_unsupported_syntax_with_line_number(self):
        with self.assertRaises(sdyaml.YamlError) as caught:
            sdyaml.loads("a: 1\nb: &anchor\n")
        self.assertEqual(caught.exception.line, 2)

    def test_rejects_tab_indentation(self):
        with self.assertRaises(sdyaml.YamlError):
            sdyaml.loads("a:\n\tb: 1\n")

    def test_empty_file(self):
        self.assertEqual(sdyaml.loads(""), {})


class MatcherTests(unittest.TestCase):
    def test_bare_directory_matches_subtree(self):
        m = inv.Matcher([{"id": "f", "paths": ["app/billing"]}])
        self.assertEqual(m.match("app/billing/page.tsx"), "f")
        self.assertIsNone(m.match("app/billingx/page.tsx"))

    def test_most_specific_pattern_wins(self):
        m = inv.Matcher([{"id": "broad", "paths": ["app/**"]},
                         {"id": "narrow", "paths": ["app/billing/**"]}])
        self.assertEqual(m.match("app/billing/p.tsx"), "narrow")
        self.assertEqual(m.match("app/other/p.tsx"), "broad")

    def test_overlap_is_recorded_not_hidden(self):
        m = inv.Matcher([{"id": "a", "paths": ["app/**"]},
                         {"id": "b", "paths": ["app/billing/**"]}])
        m.match("app/billing/p.tsx")
        self.assertEqual(m.overlaps["app/billing/p.tsx"], ["a", "b"])

    def test_double_star_does_not_cross_into_unrelated_prefix(self):
        m = inv.Matcher([{"id": "f", "paths": ["src/**/*.ts"]}])
        self.assertEqual(m.match("src/a/b/c.ts"), "f")
        self.assertEqual(m.match("src/c.ts"), "f")
        self.assertIsNone(m.match("lib/c.ts"))

    def test_single_star_stops_at_slash(self):
        m = inv.Matcher([{"id": "f", "paths": ["app/*/page.tsx"]}])
        self.assertEqual(m.match("app/x/page.tsx"), "f")
        self.assertIsNone(m.match("app/x/y/page.tsx"))


class ValidateTests(unittest.TestCase):
    def base(self, **over):
        feat = inv.blank_feature("billing", "Billing")
        feat["paths"] = ["app/billing/**"]
        feat["events"] = ["checkout_started"]
        feat.update(over)
        return {"version": 1, "mode": "has-users", "features": [feat]}

    def test_valid(self):
        errors, _ = inv.validate(self.base())
        self.assertEqual(errors, [])

    def test_missing_paths_is_an_error(self):
        errors, _ = inv.validate(self.base(paths=[]))
        self.assertTrue(any("no paths" in e for e in errors))

    def test_no_events_is_a_warning_not_an_error(self):
        errors, warnings = inv.validate(self.base(events=[]))
        self.assertEqual(errors, [])
        self.assertTrue(any("blind spot" in w for w in warnings))

    def test_duplicate_ids_rejected(self):
        data = self.base()
        data["features"].append(dict(data["features"][0]))
        errors, _ = inv.validate(data)
        self.assertTrue(any("duplicate id" in e for e in errors))

    def test_bad_id_rejected(self):
        errors, _ = inv.validate(self.base(id="Billing Feature"))
        self.assertTrue(any("lowercase" in e for e in errors))

    def test_bad_gate_value_rejected(self):
        errors, _ = inv.validate(self.base(gates={"contractual": "maybe"}))
        self.assertTrue(any("gates.contractual" in e for e in errors))

    def test_bad_mode_rejected(self):
        data = self.base()
        data["mode"] = "lots-of-users"
        errors, _ = inv.validate(data)
        self.assertTrue(any("mode must be" in e for e in errors))


class ScanTests(unittest.TestCase):
    def test_finds_known_surfaces_in_the_fixture(self):
        report, _, _ = run_json("scan_signals.py", "--root", FIXTURE)
        names = {e["name"] for e in report["event_names"]}
        self.assertEqual(names, {"checkout_started", "invoice_downloaded",
                                 "report_viewed", "dashboard_viewed"})
        counts = {x["type"]: x["count"] for x in report["by_type"]}
        self.assertGreaterEqual(counts.get("route", 0), 7)
        self.assertGreaterEqual(counts.get("flag", 0), 2)
        self.assertGreaterEqual(counts.get("table", 0), 3)
        self.assertGreaterEqual(counts.get("job", 0), 1)

    def test_root_is_respected_and_does_not_widen_to_the_repo(self):
        report, _, _ = run_json("scan_signals.py", "--root", FIXTURE, "--all",
                                "--limit", "500")
        for sig in report["signals"]:
            self.assertFalse(sig["file"].startswith("scripts/"),
                             "scan leaked outside --root: %s" % sig["file"])

    def test_file_based_routes_are_named_by_path(self):
        report, _, _ = run_json("scan_signals.py", "--root", FIXTURE,
                                "--type", "route", "--limit", "500")
        names = {s["name"] for s in report["signals"]}
        self.assertIn("billing", names)
        self.assertIn("settings/notifications", names)

    def test_names_mode_lists_flags(self):
        report, _, _ = run_json("scan_signals.py", "--root", FIXTURE,
                                "--names", "flag")
        names = {n["name"] for n in report["names"]}
        self.assertIn("legacy-invoice-export", names)
        self.assertIn("advancedReports", names)

    def test_snake_case_flag_calls_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.py"), "w") as fh:
                fh.write("if is_feature_enabled('beta_export'):\n    pass\n")
            report, _, _ = run_json("scan_signals.py", "--root", tmp,
                                    "--names", "flag")
            self.assertIn("beta_export", {n["name"] for n in report["names"]})

    def test_express_routes_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "s.js"), "w") as fh:
                fh.write("app.get('/api/thing', h);\nrouter.post('/api/x', h);\n")
            report, _, _ = run_json("scan_signals.py", "--root", tmp,
                                    "--names", "route")
            names = {n["name"] for n in report["names"]}
            self.assertEqual(names, {"/api/thing", "/api/x"})


class RepoCase(unittest.TestCase):
    """Builds a throwaway git repo from the fixture with controlled history."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="stripdown-test-")
        cls.repo = os.path.join(cls.tmp, "repo")
        shutil.copytree(FIXTURE, cls.repo)
        git(cls.repo, "init", "-q", "-b", "main")
        git(cls.repo, "add", "-A")
        git(cls.repo, "commit", "-q", "-m", "initial import",
            author="Ada", date="2026-05-01T10:00:00")

        # billing: touched often, by two people, with fixes
        for n, (author, subject) in enumerate([
            ("Ada", "fix billing rounding bug"),
            ("Ada", "fix invoice total regression"),
            ("Brun", "add proration to billing"),
            ("Brun", "hotfix billing webhook retry"),
        ]):
            path = os.path.join(cls.repo, "app", "billing", "page.tsx")
            with open(path, "a") as fh:
                fh.write("// change %d\n" % n)
            git(cls.repo, "add", "-A")
            git(cls.repo, "commit", "-q", "-m", subject, author=author,
                date="2026-0%d-02T10:00:00" % (6 + (n % 4)))

        # exports: created later, by one person only -> genuine bus factor of 1
        os.makedirs(os.path.join(cls.repo, "app", "exports"), exist_ok=True)
        with open(os.path.join(cls.repo, "app", "exports", "page.tsx"), "w") as fh:
            fh.write("export default function Exports() { return null; }\n")
        git(cls.repo, "add", "-A")
        git(cls.repo, "commit", "-q", "-m", "add CSV export screen", author="Dee",
            date="2026-07-11T10:00:00")

        # digest worker: one author, untouched since the import
        # reports: one small change
        with open(os.path.join(cls.repo, "app", "reports", "page.tsx"), "a") as fh:
            fh.write("// tweak\n")
        git(cls.repo, "add", "-A")
        git(cls.repo, "commit", "-q", "-m", "tidy reports copy", author="Cyd",
            date="2026-09-20T10:00:00")

        features = [
            {"id": "billing", "name": "Billing", "status": "active",
             "paths": ["app/billing/**", "prisma/schema.prisma"],
             "events": ["checkout_started", "invoice_downloaded"],
             "owner": "", "tags": [],
             "gates": {"contractual": "unknown", "regulated": "unknown",
                       "public_api": "unknown"}, "notes": ""},
            {"id": "reports", "name": "Reports", "status": "active",
             "paths": ["app/reports/**"], "events": ["report_viewed"],
             "owner": "", "tags": [], "migration": "point users at dashboard",
             "gates": {"contractual": "no", "regulated": "no",
                       "public_api": "no"}, "notes": ""},
            {"id": "weekly-digest", "name": "Weekly digest", "status": "active",
             "paths": ["workers/**"], "events": [],
             "owner": "", "tags": [],
             "gates": {"contractual": "no", "regulated": "no",
                       "public_api": "no"}, "notes": ""},
            {"id": "exports", "name": "CSV export", "status": "active",
             "paths": ["app/exports/**"], "events": ["export_downloaded"],
             "owner": "", "tags": [],
             "gates": {"contractual": "no", "regulated": "no",
                       "public_api": "no"}, "notes": ""},
            {"id": "notifications", "name": "Notification settings",
             "status": "active", "paths": ["app/settings/**"],
             "events": ["notification_pref_saved"],
             "owner": "", "tags": [],
             "gates": {"contractual": "no", "regulated": "no",
                       "public_api": "no"}, "notes": ""},
        ]
        os.makedirs(os.path.join(cls.repo, ".stripdown"), exist_ok=True)
        sdyaml.dump({"version": 1, "mode": "has-users", "features": features},
                    os.path.join(cls.repo, ".stripdown", "inventory.yml"))
        git(cls.repo, "add", "-A")
        git(cls.repo, "commit", "-q", "-m", "add strip-down inventory",
            author="Ada", date="2026-10-03T10:00:00")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def csv(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path


class CostTests(RepoCase):
    def test_attribution_and_ordering(self):
        report, _, err = run_json("cost_report.py", "--root", self.repo,
                                  "--all-history")
        self.assertEqual(err.strip(), "")
        rows = {r["id"]: r for r in report["features"]}
        self.assertEqual(report["features"][0]["id"], "billing",
                         "billing should rank highest on cost")
        self.assertEqual(rows["billing"]["commits"], 5)
        self.assertEqual(rows["billing"]["authors"], 2)
        self.assertEqual(rows["billing"]["fix_commits"], 3)
        self.assertEqual(rows["billing"]["fix_ratio"], 60.0)
        self.assertFalse(rows["billing"]["bus_factor_1"])

    def test_quiet_feature_is_marked_as_cheap_not_missing(self):
        report, _, _ = run_json("cost_report.py", "--root", self.repo,
                                "--months", "1")
        rows = {r["id"]: r for r in report["features"]}
        self.assertTrue(rows["weekly-digest"]["no_activity_in_window"])
        self.assertEqual(rows["weekly-digest"]["commits"], 0)
        self.assertGreater(rows["weekly-digest"]["loc"], 0,
                           "a quiet feature still has code and should show LOC")

    def test_single_author_feature_flags_bus_factor(self):
        report, _, _ = run_json("cost_report.py", "--root", self.repo,
                                "--all-history")
        rows = {r["id"]: r for r in report["features"]}
        self.assertTrue(rows["exports"]["bus_factor_1"])
        self.assertEqual(rows["exports"]["authors"], 1)
        self.assertEqual(rows["exports"]["top_author_share"], 100.0)

    def test_initial_import_counts_as_an_author_for_everything_it_touched(self):
        # Worth pinning: a squashed or imported first commit touches every
        # path, so features present at import never look single-author. This
        # is a property of git history, not a defect, and the report should
        # not pretend otherwise.
        report, _, _ = run_json("cost_report.py", "--root", self.repo,
                                "--all-history")
        rows = {r["id"]: r for r in report["features"]}
        self.assertGreaterEqual(rows["reports"]["authors"], 2)
        self.assertFalse(rows["reports"]["bus_factor_1"])

    def test_tests_are_counted_separately(self):
        path = os.path.join(self.repo, "app", "billing", "billing.test.tsx")
        with open(path, "w") as fh:
            fh.write("it('works', () => {});\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "add billing test", author="Ada",
            date="2026-10-02T10:00:00")
        try:
            report, _, _ = run_json("cost_report.py", "--root", self.repo,
                                    "--all-history")
            rows = {r["id"]: r for r in report["features"]}
            self.assertEqual(rows["billing"]["test_files"], 1)
            self.assertGreater(rows["billing"]["test_loc"], 0)
        finally:
            git(self.repo, "reset", "-q", "--hard", "HEAD~1")

    def test_unassigned_files_are_reported(self):
        report, _, _ = run_json("cost_report.py", "--root", self.repo,
                                "--all-history")
        self.assertGreater(report["unassigned_files"], 0)
        self.assertIsNotNone(report["coverage_pct"])
        self.assertTrue(any("server" in d["dir"]
                            for d in report["unassigned_top_dirs"]))

    def test_low_coverage_produces_a_leading_caveat(self):
        report, _, _ = run_json("cost_report.py", "--root", self.repo,
                                "--all-history")
        if report["coverage_pct"] < 60:
            self.assertIn("inventory is", report["caveats"][0])

    def test_refuses_without_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q", "-b", "main")
            code, _, err = run_script("cost_report.py", "--root", tmp)
            self.assertEqual(code, 2)
            self.assertIn("inventory", err)


class ValidatorTests(RepoCase):
    def test_valid_inventory_warns_about_blind_spot_only(self):
        report, code, _ = run_json("validate_inventory.py", "--root", self.repo)
        self.assertEqual(report["errors"], [])
        self.assertIn("weekly-digest", report["blind_spots"])
        self.assertEqual(code, 1, "blind spots should warn, not fail")

    def test_feature_matching_no_files_is_an_error(self):
        path = os.path.join(self.repo, ".stripdown", "inventory.yml")
        data = sdyaml.load(path)
        original = list(data["features"])
        data["features"].append({
            "id": "ghost", "name": "Ghost", "status": "active",
            "paths": ["app/ghost/**"], "events": ["ghost_seen"],
            "owner": "", "tags": [], "gates": {}, "notes": ""})
        sdyaml.dump(data, path)
        try:
            report, code, _ = run_json("validate_inventory.py",
                                       "--root", self.repo)
            self.assertEqual(code, 2)
            self.assertIn("ghost", report["features_matching_no_files"])
        finally:
            data["features"] = original
            sdyaml.dump(data, path)


class UsageTests(RepoCase):
    def test_aggregate_mode_computes_breadth_and_depth(self):
        path = self.csv("agg.csv", (
            "event,eligible_users,adopters,repeat_adopters\n"
            "checkout_started,1000,420,300\n"
            "invoice_downloaded,1000,80,60\n"
            "report_viewed,1000,40,34\n"
            "notification_pref_saved,1000,0,0\n"))
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["billing"]["adopters"], 420)
        self.assertEqual(rows["billing"]["breadth_pct"], 42.0)
        self.assertEqual(rows["billing"]["depth_pct"], 71.4)
        self.assertIn("multi_event_note", rows["billing"])
        self.assertEqual(rows["billing"]["signature"], "in-use")

    def test_blind_spot_is_not_a_removal_candidate(self):
        path = self.csv("agg2.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "checkout_started,1000,420,300\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["weekly-digest"]["signature"], "blind-spot")
        self.assertTrue(rows["weekly-digest"]["blind_spot"])
        self.assertIn("not a removal candidate",
                      rows["weekly-digest"]["signature_because"])

    def test_mapped_but_absent_events_are_no_data_not_dormant(self):
        path = self.csv("agg3.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "checkout_started,1000,420,300\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["reports"]["signature"], "no-data")
        self.assertIn("cannot tell which", rows["reports"]["signature_because"])

    def test_discoverability_signature(self):
        path = self.csv("agg4.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "report_viewed,1000,40,34\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["reports"]["signature"],
                         "discoverability-suspect")
        self.assertIn("awareness survey", rows["reports"]["signature_because"])

    def test_value_suspect_signature(self):
        path = self.csv("agg5.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "report_viewed,1000,600,60\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["reports"]["signature"], "value-suspect")

    def test_small_denominator_refuses_to_print_a_rate(self):
        path = self.csv("agg6.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "report_viewed,3,2,2\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["reports"]["signature"], "insufficient-data")

    def test_wilson_interval_is_wide_for_small_samples(self):
        path = self.csv("agg7.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "report_viewed,40,20,10\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        low, high = rows["reports"]["breadth_ci95"]
        self.assertLess(low, 50.0)
        self.assertGreater(high, 50.0)
        self.assertGreater(high - low, 15.0)

    def test_inconsistent_aggregate_is_rejected(self):
        path = self.csv("bad.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "report_viewed,10,20,2\n")
        code, _, err = run_script("usage_report.py", "--root", self.repo,
                                  "--aggregate", path)
        self.assertEqual(code, 2)
        self.assertIn("exceeds eligible_users", err)

    def test_events_in_data_not_in_inventory_are_surfaced(self):
        path = self.csv("agg8.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "checkout_started,1000,420,300\n"
                        "mystery_event,1000,900,800\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        self.assertIn("mystery_event", report["events_in_data_not_in_inventory"])

    def test_events_mode_computes_depth_retention_and_trend(self):
        lines = ["user_id,event,timestamp,account_id"]
        # u1..u10 use checkout twice (once early, once late) -> depth 100%
        for i in range(1, 11):
            lines.append("u%d,checkout_started,2026-01-05T10:00:00,acme" % i)
            lines.append("u%d,checkout_started,2026-03-05T10:00:00,acme" % i)
        # u11..u40 use it once, early only -> no repeat, not retained
        for i in range(11, 41):
            lines.append("u%d,checkout_started,2026-01-06T10:00:00,small%d"
                         % (i, i))
        path = self.csv("events.csv", "\n".join(lines) + "\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--events", path, "--eligible", "100")
        rows = {r["id"]: r for r in report["rows"]}
        billing = rows["billing"]
        self.assertEqual(billing["adopters"], 40)
        self.assertEqual(billing["breadth_pct"], 40.0)
        self.assertEqual(billing["depth_pct"], 25.0)
        self.assertEqual(billing["retained_adopters"], 10)

    def test_events_mode_without_eligible_warns_about_the_denominator(self):
        path = self.csv("events2.csv",
                        "user_id,event,timestamp\n"
                        "u1,checkout_started,2026-01-05T10:00:00\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--events", path)
        self.assertIn("not an eligible-user one", report["caveats"][0])

    def test_revenue_concentration(self):
        lines = ["user_id,event,timestamp,account_id"]
        for i in range(1, 6):
            lines.append("u%d,report_viewed,2026-02-01T10:00:00,whale" % i)
        lines.append("u99,report_viewed,2026-02-01T10:00:00,minnow")
        path = self.csv("events3.csv", "\n".join(lines) + "\n")
        rev = self.csv("rev.csv", "account_id,arr\nwhale,480000\nminnow,1200\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--events", path, "--revenue", rev,
                                "--eligible", "100")
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["reports"]["arr_touching"], 481200.0)
        self.assertGreater(rows["reports"]["top_account_arr_share_pct"], 99.0)

    def test_requires_an_input(self):
        code, _, err = run_script("usage_report.py", "--root", self.repo)
        self.assertEqual(code, 2)
        self.assertIn("--aggregate", err)

    def test_thresholds_are_reported_with_their_provenance(self):
        path = self.csv("agg9.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "checkout_started,1000,420,300\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        self.assertIn("not validated", report["thresholds"]["provenance"])


class DetectTests(unittest.TestCase):
    def test_detects_next_and_vendors(self):
        report, _, _ = run_json("detect_stack.py", "--root", FIXTURE)
        self.assertIn("next", report["frameworks"])
        self.assertIn("posthog", report["vendors"]["analytics"])
        self.assertIn("launchdarkly", report["vendors"]["flags"])
        self.assertIn("stripe", report["vendors"]["billing"])
        self.assertEqual(report["suggested_mode"], "has-users")

    def test_no_analytics_suggests_pre_users_and_says_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as fh:
                fh.write('{"name":"x","dependencies":{"react":"18.3.1"}}')
            report, _, _ = run_json("detect_stack.py", "--root", tmp)
            self.assertEqual(report["suggested_mode"], "pre-users")
            self.assertTrue(any("no analytics SDK" in n
                                for n in report["notes"]))




class DepsTests(unittest.TestCase):
    def test_normalise(self):
        cases = {
            "./lib/stripe": "lib/stripe",
            "@/app/billing/page.tsx": "app/billing/page",
            "app.billing.models": "app/billing/models",
            "../../workers/digest.py": "workers/digest",
            "@/components/ui/index.ts": "components/ui",
        }
        for raw, want in cases.items():
            self.assertEqual(deps.normalise(raw), want, "on %r" % raw)

    def test_tails_excludes_single_components(self):
        # Matching on "page" or "utils" alone would couple half a codebase.
        self.assertEqual(deps.tails("app/billing/page.tsx"),
                         ["app/billing/page", "billing/page"])
        self.assertNotIn("page", deps.tails("app/billing/page.tsx"))

    def test_inbound_detects_a_crossing_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "feat"))
            with open(os.path.join(tmp, "feat", "core.ts"), "w") as fh:
                fh.write("export const x = 1;\n")
            with open(os.path.join(tmp, "outside.ts"), "w") as fh:
                fh.write("import { x } from './feat/core';\n")
            index = deps.DepIndex(tmp, ["feat/core.ts", "outside.ts"],
                                  inv.read_text)
            hits, total = index.inbound(["feat/core.ts"])
            self.assertEqual(total, 1)
            self.assertEqual(hits[0]["from"], "outside.ts")

    def test_inbound_ignores_imports_within_the_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "feat"))
            with open(os.path.join(tmp, "feat", "core.ts"), "w") as fh:
                fh.write("export const x = 1;\n")
            with open(os.path.join(tmp, "feat", "ui.ts"), "w") as fh:
                fh.write("import { x } from './feat/core';\n")
            index = deps.DepIndex(tmp, ["feat/core.ts", "feat/ui.ts"],
                                  inv.read_text)
            _, total = index.inbound(["feat/core.ts", "feat/ui.ts"])
            self.assertEqual(total, 0)


class RegulatedClassifierTests(unittest.TestCase):
    def test_matches_obligation_shaped_names(self):
        for fid, name in [("audit-log", "Audit log"), ("invoices", "Invoices"),
                          ("exports", "CSV export of data"),
                          ("sso", "SSO / SAML login"),
                          ("account-deletion", "Delete my account"),
                          ("a11y", "Accessibility options")]:
            self.assertTrue(G.regulated_terms_matching({"id": fid, "name": name}),
                            "should have matched: %s" % fid)

    def test_does_not_match_ordinary_features(self):
        for fid, name in [("dashboard", "Dashboard"), ("reports", "Reports"),
                          ("weekly-digest", "Weekly digest email"),
                          ("themes", "Dark mode")]:
            self.assertEqual(G.regulated_terms_matching({"id": fid, "name": name}),
                             [], "should not have matched: %s" % fid)

    def test_plural_is_matched(self):
        self.assertIn("invoice",
                      G.regulated_terms_matching({"id": "invoices",
                                                  "name": "Invoices"}))


class GateUnitTests(unittest.TestCase):
    def ctx(self, **over):
        kwargs = {"window_days": 400, "has_revenue": True}
        kwargs.update(over)
        return G.Context(**kwargs)

    def test_dormancy_fails_on_a_short_window(self):
        gate = G.gate_dormancy({}, {"adopters": 0}, self.ctx(window_days=90))
        self.assertEqual(gate["state"], G.FAIL)
        self.assertIn("full 365-day", gate["because"])

    def test_dormancy_fails_when_the_feature_has_live_users(self):
        gate = G.gate_dormancy({}, {"adopters": 190, "breadth_pct": 4.0},
                               self.ctx())
        self.assertEqual(gate["state"], G.FAIL)
        self.assertIn("product decision", gate["because"])

    def test_dormancy_passes_on_zero_adopters_over_a_full_cycle(self):
        gate = G.gate_dormancy({}, {"adopters": 0}, self.ctx())
        self.assertEqual(gate["state"], G.PASS)

    def test_dormancy_unknown_without_a_window(self):
        gate = G.gate_dormancy({}, {"adopters": 0}, self.ctx(window_days=None))
        self.assertEqual(gate["state"], G.UNKNOWN)

    def test_instrumentation_fails_on_blind_spot_and_no_data(self):
        for sig in ("blind-spot", "no-data", "insufficient-data"):
            gate = G.gate_instrumentation({}, {"signature": sig}, self.ctx())
            self.assertEqual(gate["state"], G.FAIL, "on %s" % sig)

    def test_regulatory_blocks_an_obligation_name(self):
        feature = {"id": "exports", "name": "CSV export",
                   "gates": {"regulated": "unknown"}}
        self.assertEqual(G.gate_regulatory(feature, {}, self.ctx())["state"],
                         G.FAIL)

    def test_regulatory_needs_a_written_reason_to_be_overridden(self):
        feature = {"id": "exports", "name": "CSV export",
                   "gates": {"regulated": "no"}, "notes": ""}
        self.assertEqual(G.gate_regulatory(feature, {}, self.ctx())["state"],
                         G.UNKNOWN)
        feature["notes"] = "not a GDPR export; it exports chart images only"
        self.assertEqual(G.gate_regulatory(feature, {}, self.ctx())["state"],
                         G.PASS)

    def test_regulatory_honours_an_explicit_yes(self):
        feature = {"id": "x", "name": "Thing", "gates": {"regulated": "yes"}}
        self.assertEqual(G.gate_regulatory(feature, {}, self.ctx())["state"],
                         G.FAIL)

    def test_unanswered_gates_are_unknown_not_pass(self):
        feature = inv.blank_feature("x", "Thing")
        results = G.evaluate(feature, {"signature": "dormant", "adopters": 0},
                             self.ctx())
        self.assertEqual(results["contractual"]["state"], G.UNKNOWN)
        self.assertFalse(G.summarise(results)["all_clear"])

    def test_revenue_blocks_on_concentration_in_one_account(self):
        usage = {"arr_touching": 100000.0, "arr_share_pct": 1.0,
                 "top_account_arr_share_pct": 95.0}
        gate = G.gate_revenue({}, usage, self.ctx())
        self.assertEqual(gate["state"], G.FAIL)
        self.assertIn("single account", gate["because"])

    def test_revenue_blocks_above_the_arr_share_limit(self):
        usage = {"arr_touching": 100000.0, "arr_share_pct": 40.0,
                 "top_account_arr_share_pct": 10.0}
        self.assertEqual(G.gate_revenue({}, usage, self.ctx())["state"], G.FAIL)

    def test_revenue_unknown_without_revenue_data(self):
        gate = G.gate_revenue({}, {"adopters": 0}, self.ctx(has_revenue=False))
        self.assertEqual(gate["state"], G.UNKNOWN)

    def test_migration_passes_when_there_is_nobody_to_migrate(self):
        gate = G.gate_migration({}, {"adopters": 0}, self.ctx())
        self.assertEqual(gate["state"], G.PASS)

    def test_migration_unknown_when_users_exist_and_no_plan_recorded(self):
        gate = G.gate_migration({}, {"adopters": 50}, self.ctx())
        self.assertEqual(gate["state"], G.UNKNOWN)

    def test_migration_passes_with_a_recorded_plan(self):
        gate = G.gate_migration({"migration": "export then redirect"},
                                {"adopters": 50}, self.ctx())
        self.assertEqual(gate["state"], G.PASS)


class VerdictTests(RepoCase):
    AGG = ("event,eligible_users,adopters,repeat_adopters\n"
           "checkout_started,4820,1960,1310\n"
           "invoice_downloaded,4820,340,201\n"
           "report_viewed,4820,190,160\n"
           "notification_pref_saved,4820,0,0\n"
           "export_downloaded,4820,0,0\n")
    REV = "account_id,arr\nacme,120000\nsmall,4000\n"

    def verdict(self, *extra):
        agg = self.csv("v_agg.csv", self.AGG)
        rev = self.csv("v_rev.csv", self.REV)
        report, _, err = run_json(
            "verdict_report.py", "--root", self.repo, "--all-history",
            "--aggregate", agg, "--revenue", rev, "--window-days", "400",
            *extra)
        self.assertEqual(err.strip(), "")
        return {r["id"]: r for r in report["rows"]}, report

    def test_a_dormant_gate_clearing_feature_reaches_cut(self):
        rows, _ = self.verdict()
        self.assertEqual(rows["notifications"]["bucket"], "cut")
        self.assertEqual(rows["notifications"]["gates_failed"], [])
        self.assertEqual(rows["notifications"]["gates_unknown"], [])
        self.assertIn("red_team_brief", rows["notifications"])

    def test_cut_rows_carry_urgency_from_cost(self):
        rows, _ = self.verdict()
        self.assertIn(rows["notifications"]["urgency"],
                      ("low", "medium", "high"))

    def test_a_regulated_name_is_blocked_not_cut(self):
        rows, _ = self.verdict()
        self.assertEqual(rows["exports"]["bucket"], "blocked")
        self.assertIn("regulatory", rows["exports"]["gates_unknown"]
                      + rows["exports"]["gates_failed"])

    def test_discoverability_goes_to_reposition_and_suggests_a_survey(self):
        rows, _ = self.verdict()
        self.assertEqual(rows["reports"]["bucket"], "reposition")
        self.assertIn("survey", rows["reports"]["cheapest_next_step"])

    def test_a_feature_with_no_events_is_blind_spot(self):
        rows, _ = self.verdict()
        self.assertEqual(rows["weekly-digest"]["bucket"], "blind-spot")

    def test_a_busy_feature_is_kept(self):
        rows, _ = self.verdict()
        self.assertEqual(rows["billing"]["bucket"], "blocked")
        self.assertIn("dormancy", rows["billing"]["gates_failed"])

    def test_without_revenue_data_nothing_reaches_cut(self):
        agg = self.csv("v_agg2.csv", self.AGG)
        report, _, _ = run_json("verdict_report.py", "--root", self.repo,
                                "--all-history", "--aggregate", agg,
                                "--window-days", "400")
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["notifications"]["bucket"], "blocked")
        self.assertIn("revenue", rows["notifications"]["gates_unknown"])

    def test_a_short_window_blocks_everything_on_dormancy(self):
        agg = self.csv("v_agg3.csv", self.AGG)
        rev = self.csv("v_rev3.csv", self.REV)
        report, _, _ = run_json("verdict_report.py", "--root", self.repo,
                                "--all-history", "--aggregate", agg,
                                "--revenue", rev, "--window-days", "30")
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["notifications"]["bucket"], "blocked")
        self.assertIn("dormancy", rows["notifications"]["gates_failed"])

    def test_no_usage_data_means_everything_is_unassessable(self):
        report, _, _ = run_json("verdict_report.py", "--root", self.repo,
                                "--all-history")
        buckets = {b["bucket"]: b["features"] for b in report["buckets"]}
        self.assertEqual(buckets["cut"], 0)
        self.assertEqual(buckets["blind-spot"], report["features"])

    def test_every_row_names_its_missing_evidence_and_next_step(self):
        rows, _ = self.verdict()
        for fid, row in rows.items():
            self.assertIn("missing_evidence", row, fid)
            if row["bucket"] in ("blocked", "blind-spot", "reposition"):
                self.assertTrue(row["cheapest_next_step"],
                                "%s has no next step" % fid)

    def test_report_states_the_retention_caveat(self):
        _, report = self.verdict()
        self.assertTrue(any("no published evidence" in c
                            for c in report["caveats"]))


class SunsetTests(RepoCase):
    def plan(self, feature, *extra):
        agg = self.csv("s_agg.csv", VerdictTests.AGG)
        rev = self.csv("s_rev.csv", VerdictTests.REV)
        code, out, err = run_script(
            "sunset_plan.py", feature, "--root", self.repo, "--all-history",
            "--aggregate", agg, "--revenue", rev, "--window-days", "400",
            "--stdout", *extra)
        self.assertEqual(code, 0, err)
        return out

    def test_a_cleared_feature_gets_a_dated_schedule(self):
        body = self.plan("notifications")
        self.assertIn("## Schedule", body)
        self.assertIn("Flag off first, delete last", body)
        self.assertIn("## Abort triggers", body)
        self.assertNotIn("## Stop:", body)

    def test_a_blocked_feature_opens_with_the_blockers(self):
        body = self.plan("exports")
        self.assertIn("## Stop:", body)
        self.assertIn("Do not schedule a removal", body)
        self.assertLess(body.index("## Stop:"), body.index("## Evidence"))

    def test_the_plan_declares_itself_a_draft(self):
        body = self.plan("notifications")
        self.assertIn("DRAFT", body)
        self.assertIn("no code has been changed", body)

    def test_the_plan_states_the_churn_blind_spot(self):
        body = self.plan("notifications")
        self.assertIn("Churned users appear in no usage export", body)

    def test_unknown_feature_is_rejected_with_the_known_ids(self):
        code, _, err = run_script("sunset_plan.py", "nope", "--root", self.repo)
        self.assertEqual(code, 2)
        self.assertIn("billing", err)

    def test_writing_to_a_file_reports_the_path(self):
        agg = self.csv("s_agg2.csv", VerdictTests.AGG)
        report, _, _ = run_json(
            "sunset_plan.py", "notifications", "--root", self.repo,
            "--all-history", "--aggregate", agg, "--window-days", "400")
        self.assertEqual(report["wrote"], ".stripdown/sunset/notifications.md")
        self.assertIn("draft", report["status"])
        self.assertTrue(os.path.exists(
            os.path.join(self.repo, ".stripdown", "sunset",
                         "notifications.md")))


class ScopeDiffTests(RepoCase):
    def test_measures_off_path_share_of_activity(self):
        report, _, err = run_json("scope_diff.py", "--root", self.repo,
                                  "--path", "billing")
        self.assertEqual(err.strip(), "")
        self.assertTrue(report["critical_path_declared"])
        self.assertEqual(report["features_on_path"], 1)
        self.assertGreater(report["features_off_path"], 1)
        self.assertIsNotNone(report["off_path_shares"]["off_path_churn_pct"])
        self.assertIn("headline", report)

    def test_timeline_is_ordered_by_first_appearance(self):
        report, _, _ = run_json("scope_diff.py", "--root", self.repo,
                                "--path", "billing")
        dates = [t["first_seen"] for t in report["timeline"]]
        self.assertEqual(dates, sorted(dates))
        self.assertIn("exports", [t["id"] for t in report["timeline"]])

    def test_works_without_a_declared_path_and_says_so(self):
        report, _, _ = run_json("scope_diff.py", "--root", self.repo)
        self.assertFalse(report["critical_path_declared"])
        self.assertTrue(any("no critical path declared" in c
                            for c in report["caveats"]))
        self.assertTrue(report["timeline"])

    def test_rejects_an_unknown_feature_id(self):
        code, _, err = run_script("scope_diff.py", "--root", self.repo,
                                  "--path", "ghost")
        self.assertEqual(code, 2)
        self.assertIn("not in the inventory", err)

    def test_says_off_path_is_not_an_argument_for_removal(self):
        report, _, _ = run_json("scope_diff.py", "--root", self.repo,
                                "--path", "billing")
        self.assertTrue(any("not an argument for removal" in c
                            for c in report["caveats"]))


class ClaimsTests(unittest.TestCase):
    def write(self, tmp, body):
        os.makedirs(os.path.join(tmp, ".stripdown"), exist_ok=True)
        with open(os.path.join(tmp, ".stripdown", "demand.yml"), "w") as fh:
            fh.write(body)

    def check(self, body):
        tmp = tempfile.mkdtemp()
        try:
            self.write(tmp, body)
            code, out, err = run_script("validate_claims.py", "--root", tmp)
            return json.loads(out) if out.strip() else {}, code
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_well_cited_ledger_is_valid(self):
        report, code = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Competitor ships bulk export'\n"
            "    grade: B\n"
            "    source: 'https://example.com/pricing'\n"
            "    fetched: '2026-11-05'\n"
            "    kind: competitor\n"
            "    supports: []\n")
        self.assertEqual(report["errors"], [])
        self.assertEqual(code, 0)

    def test_grade_d_may_not_justify_a_feature(self):
        report, code = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Teams are desperate for AI dashboards'\n"
            "    grade: D\n"
            "    source: ''\n"
            "    kind: signal\n"
            "    supports: [dashboard]\n")
        self.assertEqual(code, 2)
        self.assertTrue(any("may not justify anything" in e
                            for e in report["errors"]))

    def test_grade_d_must_be_a_question(self):
        report, code = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'The market wants scheduled exports'\n"
            "    grade: D\n"
            "    source: ''\n"
            "    supports: []\n")
        self.assertEqual(code, 2)
        self.assertTrue(any("phrased as a question" in e
                            for e in report["errors"]))

    def test_grade_d_as_a_question_is_accepted(self):
        report, _ = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Would teams pay for scheduled exports?'\n"
            "    grade: D\n"
            "    source: ''\n"
            "    supports: []\n")
        self.assertEqual(report["errors"], [])

    def test_grade_b_needs_a_url_and_a_date(self):
        report, code = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Competitor ships export'\n"
            "    grade: B\n"
            "    source: 'their docs'\n"
            "    supports: []\n")
        self.assertEqual(code, 2)
        self.assertTrue(any("https URL" in e for e in report["errors"]))
        self.assertTrue(any("fetched:" in e for e in report["errors"]))

    def test_grade_a_cannot_be_an_external_url(self):
        report, code = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Our churn is concentrated off-path'\n"
            "    grade: A\n"
            "    source: 'https://example.com/thing'\n"
            "    supports: []\n")
        self.assertEqual(code, 2)
        self.assertTrue(any("cannot be grade A" in e
                            for e in report["errors"]))

    def test_discouraged_sources_are_warned_about(self):
        report, _ = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Reviewers complain about onboarding'\n"
            "    grade: C\n"
            "    source: 'https://www.g2.com/products/x/reviews'\n"
            "    fetched: '2026-11-05'\n"
            "    supports: []\n")
        self.assertTrue(any("prohibits scraping" in w
                            for w in report["warnings"]))

    def test_a_ledger_with_nothing_citable_warns(self):
        report, _ = self.check(
            "version: 1\n"
            "claims:\n"
            "  - id: c1\n"
            "    claim: 'Is there demand for this?'\n"
            "    grade: D\n"
            "    source: ''\n"
            "    supports: []\n")
        self.assertTrue(any("nothing citable" in w or "no claim is usable" in w
                            for w in report["warnings"]))


class DormancyRegressionTests(RepoCase):
    def test_zero_adopters_against_a_large_denominator_is_dormant(self):
        # Regression: zero adopters out of thousands of eligible users is a
        # STRONG result. It was previously reported as insufficient-data,
        # because the adopter floor meant for depth was swallowing it.
        path = self.csv("dormant.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "notification_pref_saved,4820,0,0\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["notifications"]["signature"], "dormant")
        self.assertIn("4820", rows["notifications"]["signature_because"])

    def test_a_tiny_denominator_is_still_insufficient_data(self):
        path = self.csv("tiny.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "notification_pref_saved,4,0,0\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertEqual(rows["notifications"]["signature"],
                         "insufficient-data")


class UsageWindowTests(RepoCase):
    def test_window_is_measured_from_event_timestamps(self):
        lines = ["user_id,event,timestamp"]
        for i in range(40):
            lines.append("u%d,report_viewed,2026-01-10T10:00:00" % i)
            lines.append("u%d,report_viewed,2026-06-10T10:00:00" % i)
        path = self.csv("win.csv", "\n".join(lines) + "\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--events", path, "--eligible", "1000")
        self.assertGreater(report["window_days"], 140)
        self.assertIn("measured from timestamps", report["window_days_basis"])
        self.assertTrue(any("under a full year" in c
                            for c in report["caveats"]))

    def test_unknown_window_is_flagged(self):
        path = self.csv("win2.csv",
                        "event,eligible_users,adopters,repeat_adopters\n"
                        "report_viewed,4820,190,160\n")
        report, _, _ = run_json("usage_report.py", "--root", self.repo,
                                "--aggregate", path)
        self.assertIsNone(report["window_days"])
        self.assertTrue(any("observation window is unknown" in c
                            for c in report["caveats"]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
