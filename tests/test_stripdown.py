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
             "owner": "", "tags": [],
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
