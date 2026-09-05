"""Runner contracts; no Wine download, GUI, or product modifications required."""
from __future__ import annotations

import contextlib
from collections import Counter
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "local_windows_ci_tested", ROOT / "packaging/windows/local_windows_ci.py")
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="winci plan ")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.tests = self.repo / "tests/mod_editor"
        self.tests.mkdir(parents=True)
        for name, content in {"test_alpha.py": "import alpha\n", "test_beta.py": "# beta\n",
                              "test_gamma.py": "from alpha import x\n"}.items():
            (self.tests / name).write_text(content)

    def names(self, **kwargs):
        return [p.name for p in runner.plan(self.repo, kwargs.get("only", []), kwargs.get("changed"))]

    def test_default_and_repeatable_globs(self):
        args = runner.argument_parser().parse_args(["--only", "test_b*", "--only", "test_alpha.py", "-j", "2"])
        self.assertEqual(args.jobs, 2)
        self.assertEqual(self.names(only=args.only), ["test_alpha.py", "test_beta.py"])
        self.assertEqual(len(self.names()), 3)

    def test_only_multiple_names_and_deduplication(self):
        args = runner.argument_parser().parse_args(["--only", "test_alpha.py", "test_*", "--keep-going"])
        self.assertTrue(args.keep_going)
        self.assertEqual(len(self.names(only=args.only)), 3)

    def test_unmatched_only_is_an_error_even_with_other_matches(self):
        with self.assertRaisesRegex(ValueError, "matched no test"):
            self.names(only=["test_alpha.py", "missing.py"])

    def test_changed_direct_modules_deleted_modules_and_intersection(self):
        changed = {"tests/mod_editor/test_beta.py", "mod_editor/alpha.py"}
        self.assertEqual(len(self.names(changed=changed)), 3)
        self.assertEqual(self.names(only=["test_g*"], changed=changed), ["test_gamma.py"])
        self.assertEqual(self.names(changed={"mod_editor/alpha.py"}), ["test_alpha.py", "test_gamma.py"])
        self.assertEqual(self.names(changed={"README.md"}), [])

    def test_argument_limits(self):
        for argv in (["-j", "0"], ["--timeout", "-1"], ["--timeout", "nan"], ["--timeout", "inf"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                runner.argument_parser().parse_args(argv)

    def test_ci_skip_list_and_isolated_rule_stay_in_parity(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        case = workflow.split('case "$name" in', 1)[1].split('skipped=$((skipped + 1))', 1)[0]
        self.assertEqual(runner.LEAN_SKIPS, set(re.findall(r"test_[\w]+\.py", case)))
        self.assertIn(f'isolated="{runner.ISOLATED}"', workflow)
        self.assertIn(runner.EVIDENCE, workflow)
        self.assertEqual(runner.argument_parser().parse_args([]).timeout, 420)

    def test_evidence_controls_skips_even_when_explicitly_selected(self):
        name = next(iter(runner.LEAN_SKIPS))
        self.assertEqual(runner.skip_reason(not (self.repo / runner.EVIDENCE).is_file(), name), runner.LEAN_REASON)
        self.assertIsNone(runner.skip_reason(True, "test_modpack.py"))
        evidence = self.repo / runner.EVIDENCE
        evidence.parent.mkdir(parents=True)
        evidence.write_text("{}")
        self.assertIsNone(runner.skip_reason(not evidence.is_file(), name))

    @unittest.skipUnless(shutil.which("git"), "git is absent")
    def test_changed_paths_include_staged_unstaged_untracked_and_deleted(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.STDOUT)
        git("init")
        git("add", "tests/mod_editor/test_alpha.py", "tests/mod_editor/test_beta.py", "tests/mod_editor/test_gamma.py")
        git("-c", "user.name=Runner Test", "-c", "user.email=runner@example.invalid", "commit", "-m", "fixture")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.tests / "test_alpha.py").write_text("# unstaged\n")
        (self.tests / "test_beta.py").unlink()
        (self.repo / "new_module.py").write_text("# untracked\n")
        (self.tests / "test_gamma.py").write_text("# staged\n")
        git("add", "tests/mod_editor/test_gamma.py")
        self.assertEqual(runner.changed_paths(self.repo), {
            "tests/mod_editor/test_alpha.py", "tests/mod_editor/test_beta.py",
            "tests/mod_editor/test_gamma.py", "new_module.py"})


class OutputTests(unittest.TestCase):
    def test_last_unittest_count_like_ci(self):
        self.assertEqual(runner.test_count("Ran 90 tests\nchild\nRan 1 test in 0.1s\nOK"), 1)
        self.assertIsNone(runner.test_count("no unittest report"))
        self.assertEqual(runner.test_count("Ran 0 tests"), 0)

    def test_summary_counts_failed_tests_and_file_skips(self):
        results = [runner.Result("a", output="Ran 4 tests\nOK (skipped=1)"),
                   runner.Result("b", 1, "Ran 2 tests\nFAILED"),
                   runner.Result("c", skipped="lean"), runner.Result("d", 124, "TIMED OUT")]
        self.assertEqual(runner.summary(results), "SUMMARY: files=4 passed=1 failed=2 skipped=1 tests=6")

    def test_failure_tail_and_unknown_count(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            runner.report_result(runner.Result("bad.py", 1, "first line\n" + "tail\n" * 40))
            runner.report_result(runner.Result("good.py"))
        self.assertNotIn("first line", output.getvalue())
        self.assertIn("FAIL  bad.py  (rc=1)", output.getvalue())
        self.assertIn("PASS  good.py  (? tests)", output.getvalue())


class ClassificationTests(unittest.TestCase):
    # Short original log excerpts, with temp names changed to exercise portability.
    LINK_FAILURE = r'''......F
======================================================================
FAIL: test_recovery_refuses_aliases_and_invalid_hashes (__main__.WorkspaceStateStoreTests.test_recovery_refuses_aliases_and_invalid_hashes)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "Z:\repo\tests\mod_editor\test_workspace_recovery.py", line 91, in test_recovery_refuses_aliases_and_invalid_hashes
    with self.assertRaisesRegex(ValidationError, "not a regular private file"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValidationError not raised

----------------------------------------------------------------------
Ran 7 tests in 0.367s

FAILED (failures=1)
'''

    def test_classification_is_complete_and_report_table_agrees(self):
        rows = runner.CLASSIFICATIONS["files"]
        self.assertEqual(len(rows), 73)
        self.assertEqual(len({r["name"] for r in rows}), 73)
        self.assertEqual(Counter(r["category"] for r in rows), {
            "LEAN CHECKOUT": 27, "WINE GAP": 44, "RUNNER BUG": 1, "UNKNOWN": 1})
        report = (ROOT / "ASTRA_WIN_LOCAL_CI_REPORT.md").read_text()
        table = dict(re.findall(r"^\| `(test_\w+\.py)` \| ([A-Z ]+) \|", report, re.M))
        self.assertEqual(table, {r["name"]: r["category"] for r in rows})
        for row in rows:
            with self.subTest(name=row["name"]):
                self.assertTrue(row["evidence"])
                self.assertTrue(all(e["line"] > 0 and e["signature"] for e in row["evidence"]))
                if row["category"] == "WINE GAP":
                    self.assertTrue(row["wine_signatures"])
                for rule in row["wine_signatures"]:
                    self.assertIn(rule["gap"], runner.CLASSIFICATIONS["gap_reasons"])
                    self.assertNotIn("WinError 5", str(rule))
                    if "headers" in rule:
                        self.assertTrue(rule["statement"])
                        self.assertTrue(rule["terminal"])

    def test_only_observed_case_statement_and_exception_skip(self):
        name = "test_workspace_recovery.py"
        output = self.LINK_FAILURE
        reason = runner.wine_gap_reason(name, 1, output)
        self.assertTrue(reason.startswith("Wine gap: "))
        for other_name, rc, changed in (
            ("test_modpack.py", 1, output),
            (name, 0, output), (name, 124, output), (name, -11, output),
            (name, 1, output.replace("ValidationError not raised", "ValidationError: real regression")),
            (name, 1, output.replace("test_recovery_refuses_aliases_and_invalid_hashes", "test_new_regression")),
            (name, 1, output.replace('"not a regular private file"', '"new assertion"')),
            (name, 1, output.replace("failures=1", "failures=2")),
            (name, 1, output.replace("FAILED (failures=1)", "")),
            (name, 1, output + "TIMED OUT after 420s"),
        ):
            with self.subTest(name=other_name, rc=rc, changed=changed[-80:]):
                self.assertIsNone(runner.wine_gap_reason(other_name, rc, changed))
        result = runner.Result(name, 1, output, reason)
        self.assertEqual(runner.summary([result]), "SUMMARY: files=1 passed=0 failed=0 skipped=1 tests=0")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            runner.report_result(result)
        self.assertIn(f"SKIP {name} (Wine gap: ", printed.getvalue())

    def test_known_gap_never_hides_a_second_failure(self):
        extra = '''ERROR: test_new (__main__.WorkspaceStateStoreTests.test_new)
Traceback (most recent call last):
PermissionError: [WinError 5] Access denied: 'base.iso.part' -> 'base.iso'
'''
        output = self.LINK_FAILURE.replace("Ran 7 tests", extra + "Ran 8 tests")
        output = output.replace("FAILED (failures=1)", "FAILED (failures=1, errors=1)")
        self.assertIsNone(runner.wine_gap_reason("test_workspace_recovery.py", 1, output))
        output = output.replace("PermissionError: [WinError 5] Access denied: 'base.iso.part' -> 'base.iso'",
                                "FileNotFoundError: missing reports/assets/catalog.json")
        self.assertIsNone(runner.wine_gap_reason("test_workspace_recovery.py", 1, output))

    def test_temp_diagnostics_allow_new_profile_but_keep_artifact(self):
        old = r"FileNotFoundError: [WinError 2] File not found: 'C:\\users\\noah\\Temp\\tmpabcdefgh\\alias.iso'"
        new = r"FileNotFoundError: [WinError 2] File not found: 'C:\\users\\someone\\AppData\\Local\\Temp\\winci\\tmp01234567\\alias.iso'"
        self.assertEqual(runner.normalize_diagnostic(old), runner.normalize_diagnostic(new))
        self.assertNotEqual(runner.normalize_diagnostic(old), runner.normalize_diagnostic(new.replace("alias.iso", "source.iso")))
        self.assertEqual(runner.normalize_diagnostic(old), runner.normalize_diagnostic(new.replace("tmp01234567", "private-source-cache-01234567")))
        self.assertEqual(runner.normalize_diagnostic("Z:/tmp/winci-green/tests/fixtures/nfl2k5_player_star_thin_v1.json"),
                         runner.normalize_diagnostic("Z:/home/user/other checkout/tests/fixtures/nfl2k5_player_star_thin_v1.json"))

    def test_copyfile_crash_preserves_an_unreported_earlier_failure(self):
        def crash(name, case, progress):
            return (progress + 'wine: Call from 00006FFFFFC7D3B8 to unimplemented function KERNEL32.dll.CopyFile2, aborting\n'
                    'Windows fatal exception: code 0x80000100\n'
                    f'  File "Z:\\repo\\tests\\mod_editor\\{name}", line 96 in {case}\n')
        stage = crash("test_stage_release.py", "test_refuses_destination_below_symlinked_parent", "....")
        self.assertIn("CopyFile2", runner.wine_gap_reason("test_stage_release.py", 1, stage))
        self.assertIsNone(runner.wine_gap_reason("test_stage_release.py", 1, stage.replace("CopyFile2", "OtherFunction")))
        core = crash("test_core.py", "test_extracted_directory_copy_is_manifest_verified", "F..")
        self.assertIsNone(runner.wine_gap_reason("test_core.py", 1, core))

    def test_import_gap_is_specific_to_tkinter_and_its_importing_files(self):
        output = ('Traceback (most recent call last):\n'
                  '  File "Z:\\repo\\mod_editor\\gui\\tkinter_app.py", line 9, in <module>\n'
                  '    import tkinter as tk\nModuleNotFoundError: No module named \'tkinter\'\n')
        for name in ("test_gui.py", "test_nfl_audio.py"):
            self.assertIn("tkinter", runner.wine_gap_reason(name, 1, output))
            self.assertIsNone(runner.wine_gap_reason(name, 1, output.replace("tkinter", "mod_editor")))
        self.assertIsNone(runner.wine_gap_reason("test_core.py", 1, output))

    def followup_logs(self):
        fixture = json.loads((ROOT / "tests/fixtures/local_windows_ci_followup2.json").read_text())
        return {row["name"]: row for row in fixture["files"]}

    def test_followup_six_logs_match_only_the_three_reviewed_gaps(self):
        rows = self.followup_logs()
        decisions = runner.CLASSIFICATIONS["follow_up_2"]["remaining_six"]
        self.assertEqual(set(rows), {row["name"] for row in decisions})
        self.assertEqual({name: row["expected_status"] for name, row in rows.items()},
                         {row["name"]: row["expected_status"] for row in decisions})
        for name, row in rows.items():
            with self.subTest(name=name):
                reason = runner.wine_gap_reason(name, row["rc"], row["output"])
                self.assertEqual("SKIP" if reason else "FAIL", row["expected_status"])
                if reason:
                    self.assertIsNone(runner.wine_gap_reason(name, 124, row["output"]))
                    self.assertIsNone(runner.wine_gap_reason(name, 1, row["output"] + "TIMED OUT"))

    def test_followup_terminals_remain_specific_after_normalization(self):
        logs = self.followup_logs()
        variants = {
            "test_apf_audio_encoder_gui.py": [("[37 chars]ble", "[38 chars]ble"), ("[37 chars]ble", "[37 chars]exe")],
            "test_platform_compat.py": [("S-1-1-0", "S-1-5-99"), ("2k5-mod-studio", "another-cache")],
            "test_nfl2k5_audo_fixed_slots.py": [("inventory changed during publication", "inventory is missing")],
        }
        for name, replacements in variants.items():
            row = logs[name]
            for old, new in replacements:
                with self.subTest(name=name, replacement=new):
                    self.assertIn(old, row["output"])
                    self.assertIsNone(runner.wine_gap_reason(name, row["rc"], row["output"].replace(old, new)))
            # New profile names remain portable, including the non-temp ACL root.
            self.assertIsNotNone(runner.wine_gap_reason(name, row["rc"], row["output"].replace("noah", "someone-else")))

    def test_followup_gaps_never_hide_sharing_violations_or_extra_failures(self):
        logs = self.followup_logs()
        audio = logs["test_2k5_audio_operation_integration.py"]
        # The provided log is truncated; even a complete summary must keep the
        # new cleanup failure visible, while the four identity errors qualify.
        complete = audio["output"] + "000s\n\nFAILED (errors=5)\n"
        self.assertIsNone(runner.wine_gap_reason(audio["name"], 1, complete))
        self.assertIsNone(runner.wine_gap_reason(audio["name"], 1, complete.replace("WinError 32", "WinError 5")))
        known = audio["output"].split("ERROR: test_save_then_open_xiso", 1)[0]
        known += "Ran 17 tests in 71.000s\n\nFAILED (errors=4)\n"
        self.assertIn("identity or metadata", runner.wine_gap_reason(audio["name"], 1, known))
        for name in ("test_apf_audio_encoder_gui.py", "test_nfl2k5_audo_fixed_slots.py", "test_platform_compat.py"):
            row = logs[name]
            output = row["output"].split("\nFAILED (", 1)[0]
            count = len(re.findall(r"^(ERROR|FAIL):", output, re.M))
            output += ("\nERROR: test_regression (__main__.NewTests.test_regression)\n"
                       "PermissionError: [WinError 5] Access denied: 'base.iso.part' -> 'base.iso'\n"
                       f"FAILED (errors={count + 1})\n")
            self.assertIsNone(runner.wine_gap_reason(name, 1, output))

    def test_followup_projection_accounts_for_all_twelve_lean_files(self):
        data = runner.CLASSIFICATIONS["follow_up_2"]
        lean = data["lean_files"]
        self.assertEqual({row["name"] for row in lean}, runner.LEAN_SKIPS)
        self.assertEqual(Counter(row["observed_status"] for row in lean), {"PASS": 4, "FAIL": 8})
        existing, clean = data["replay_existing_tree"], data["replay_with_lean_policy"]
        baseline = data["baseline"]
        skipped = [row for row in self.followup_logs().values()
                   if runner.wine_gap_reason(row["name"], row["rc"], row["output"])]
        self.assertEqual(existing["passed"], baseline["passed"])
        self.assertEqual(existing["failed"], baseline["failed"] - len(skipped))
        self.assertEqual(existing["skipped"], baseline["skipped"] + len(skipped))
        self.assertEqual(existing["tests"], baseline["tests"] - sum(
            runner.test_count(row["output"]) for row in skipped))
        self.assertEqual(clean["passed"], existing["passed"] - 4)
        self.assertEqual(clean["failed"], existing["failed"] - 8)
        self.assertEqual(clean["skipped"], existing["skipped"] + 12)
        self.assertEqual(clean["tests"], existing["tests"] - sum(row["tests"] for row in lean))
        for totals in (baseline, existing, clean, data["conditional_clean"]):
            self.assertEqual(totals["files"], sum(totals[key] for key in ("passed", "failed", "skipped")))


class HydrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="winci hydration ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.source = self.root / "sibling"
        self.repo.mkdir()
        self.source.mkdir()

    def write(self, root, relative, content=b"evidence"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_sibling_merges_only_the_four_trees_and_preserves_existing_paths(self):
        expected = []
        for tree in runner.HYDRATION_TREES:
            relative = tree + "/nested/input.json"
            self.write(self.source, relative)
            expected.append(relative)
        self.write(self.source, "mod_editor/core/product.py")
        self.write(self.source, "reports/existing.json", b"replacement")
        self.write(self.repo, "reports/existing.json", b"user edit")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.hydrate_from(self.repo, self.source), expected)
            self.assertEqual(runner.hydrate_from(self.repo, self.source), [])
        self.assertEqual((self.repo / "reports/existing.json").read_bytes(), b"user edit")
        self.assertFalse((self.repo / "mod_editor/core/product.py").exists())
        self.assertIn("HYDRATED_LOCAL_INPUTS files=4", output.getvalue())
        self.assertIn("omitted existing=2", output.getvalue())
        for relative in expected:
            self.assertIn(f"HYDRATE + {relative}", output.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git is absent")
    def test_tracked_files_including_deleted_paths_cannot_be_hydrated(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.write(self.repo, "reports/kept.json", b"tracked edit")
        deleted = self.write(self.repo, "reports/deleted.json")
        self.write(self.repo, "reports/staged-deletion.json")
        subprocess.run(["git", "-C", str(self.repo), "add", "--", "reports/kept.json", "reports/deleted.json", "reports/staged-deletion.json"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Runner Test", "-c", "user.email=runner@example.invalid",
                        "commit", "-q", "-m", "fixture", "--", "reports/kept.json", "reports/deleted.json", "reports/staged-deletion.json"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "rm", "-q", "--", "reports/staged-deletion.json"], check=True)
        deleted.unlink()
        for relative in ("reports/kept.json", "reports/deleted.json", "reports/staged-deletion.json", "reports/added.json"):
            self.write(self.source, relative)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.hydrate_from(self.repo, self.source), ["reports/added.json"])
        self.assertFalse(deleted.exists())
        self.assertFalse((self.repo / "reports/staged-deletion.json").exists())
        self.assertEqual((self.repo / "reports/kept.json").read_bytes(), b"tracked edit")

    @unittest.skipUnless(os.name == "posix", "host symlink fixtures require POSIX")
    def test_neither_source_nor_destination_symlinks_are_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.write(outside, "private.json")
        self.write(self.source, "reports/normal.json")
        self.write(self.source, "reports/dangling.json")
        self.write(self.source, "tools/vendor/input.exe")
        (self.source / "reports/link.json").symlink_to(outside / "private.json")
        (self.source / "reports/linked-dir").symlink_to(outside, target_is_directory=True)
        (self.repo / "reports").mkdir()
        (self.repo / "reports/dangling.json").symlink_to(outside / "missing.json")
        (self.repo / "tools").symlink_to(outside, target_is_directory=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.hydrate_from(self.repo, self.source), ["reports/normal.json"])
        self.assertTrue((self.repo / "reports/dangling.json").is_symlink())
        self.assertFalse((outside / "missing.json").exists())
        self.assertFalse((outside / "vendor").exists())
        self.assertFalse((self.repo / "reports/link.json").exists())

    def test_same_or_nested_source_and_missing_source_are_rejected(self):
        for source in (self.repo, self.root, self.repo / "nested"):
            source.mkdir(exist_ok=True)
            with self.assertRaises(ValueError):
                runner.hydrate_from(self.repo, source)
        with self.assertRaises(FileNotFoundError):
            runner.hydrate_from(self.repo, self.root / "missing")

    def test_source_version_control_files_and_directories_are_omitted(self):
        for relative in ("reports/vendor/.git/config", "reports/vendor/.gitignore",
                         "tools/vendor/submodule/.git", "docs/research/.svn/entries",
                         "docs/research/.hg/store/data"):
            self.write(self.source, relative)
        self.write(self.source, "reports/vendor/reviewed.json")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.hydrate_from(self.repo, self.source), ["reports/vendor/reviewed.json"])

    @unittest.skipUnless(os.name == "posix", "host symlink fixtures require POSIX")
    def test_symlinked_source_tree_is_reported_and_real_source_copies_inventory(self):
        real = self.root / "real"
        self.write(real, runner.EVIDENCE)
        (self.source / "reports").mkdir()
        (self.source / "reports/assets").symlink_to(real / "reports/assets", target_is_directory=True)
        # os.walk refuses nested directory links too, as in beta-53's reports/assets.
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.hydrate_from(self.repo, self.source), [])
        self.assertIn("omitted source-symlink=1", output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.hydrate_from(self.repo, real), [runner.EVIDENCE])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.hydrate_from(self.repo, real), [])
        self.assertIn("omitted existing=1", output.getvalue())
        self.assertTrue((self.repo / runner.EVIDENCE).is_file())

    @unittest.skipUnless(os.name == "posix", "host symlink fixtures require POSIX")
    def test_hydration_reports_destination_refusal_reasons(self):
        self.write(self.repo, "reports/existing.json")
        self.write(self.repo, "reports/obstruction")
        (self.repo / "reports/linked").symlink_to(self.root / "absent")
        for name in ("existing.json", "obstruction/child.json", "linked/child.json", "deleted.json"):
            self.write(self.source, "reports/" + name)
        with patch.object(runner, "tracked_paths", return_value={"reports/deleted.json"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.hydrate_from(self.repo, self.source), [])
        self.assertIn("omitted destination-symlink=1, existing=1, obstructed-parent=1, tracked=1", output.getvalue())

    def archives(self, members=None):
        pins = {}
        for index, name in enumerate(runner.RELEASE_ARCHIVES):
            path = self.root / name
            entries = members if members is not None else [
                (f"release/reports/from-{index}.json", b"json", tarfile.REGTYPE),
                ("release/mod_editor/core/existing.py", b"release source", tarfile.REGTYPE)]
            with tarfile.open(path, "w:gz") as bundle:
                for relative, data, kind in entries:
                    info = tarfile.TarInfo(relative)
                    info.type = kind
                    info.mode = 0o755
                    info.size = len(data) if kind == tarfile.REGTYPE else 0
                    info.linkname = "outside" if kind == tarfile.SYMTYPE else ""
                    bundle.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
            pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return pins

    def test_release_pins_and_gh_command_match_ci(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        for name, pin in runner.RELEASE_ARCHIVES.items():
            self.assertIn(name, workflow)
            self.assertIn(pin, workflow)
        self.assertIn(f"gh release download {runner.RELEASE_TAG}", workflow)
        with patch.object(runner.subprocess, "run") as command, patch.object(runner, "hydrate_archives", return_value=[]) as hydrate:
            runner.hydrate_release(self.repo, self.root)
        argv = command.call_args.args[0]
        self.assertEqual(argv[:6], ["gh", "release", "download", "beta-50", "--repo", runner.RELEASE_REPO])
        self.assertEqual(argv[6:-2], [v for name in runner.RELEASE_ARCHIVES for v in ("--pattern", name)])
        self.assertEqual(hydrate.call_args.args[0], self.repo)

    def test_both_archive_hashes_are_verified_before_any_copy(self):
        pins = self.archives()
        pins[next(reversed(pins))] = "0" * 64
        with patch.object(runner, "RELEASE_ARCHIVES", pins), self.assertRaisesRegex(ValueError, "hash mismatch"):
            runner.hydrate_archives(self.repo, self.root)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_release_merges_absent_paths_preserving_source_and_modes(self):
        self.write(self.repo, "mod_editor/core/existing.py", b"local edit")
        pins = self.archives()
        with patch.object(runner, "RELEASE_ARCHIVES", pins), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.hydrate_archives(self.repo, self.root), ["reports/from-0.json", "reports/from-1.json"])
        self.assertEqual((self.repo / "mod_editor/core/existing.py").read_bytes(), b"local edit")
        if os.name == "posix":
            self.assertEqual((self.repo / "reports/from-0.json").stat().st_mode & 0o777, 0o755)

    def test_release_rejects_traversal_and_nonregular_members(self):
        for name, kind in (("/absolute/escape", tarfile.REGTYPE), ("release/../escape", tarfile.REGTYPE),
                           ("release/.git/config", tarfile.REGTYPE), ("release/C:/escape", tarfile.REGTYPE),
                           ("release/reports/link", tarfile.SYMTYPE), ("release/reports/fifo", tarfile.FIFOTYPE)):
            with self.subTest(name=name):
                pins = self.archives([(name, b"unsafe", kind)])
                with patch.object(runner, "RELEASE_ARCHIVES", pins), self.assertRaises(ValueError):
                    runner.hydrate_archives(self.repo, self.root)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_hydration_options_are_explicit_and_mutually_exclusive(self):
        self.assertEqual(runner.argument_parser().parse_args(["--hydrate-from", "sibling"]).hydrate_from, Path("sibling"))
        self.assertTrue(runner.argument_parser().parse_args(["--hydrate-release"]).hydrate_release)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            runner.argument_parser().parse_args(["--hydrate-from", "sibling", "--hydrate-release"])


class PathTests(unittest.TestCase):
    def test_temp_probe_creates_a_directory_under_local_app_data(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "profile with spaces"
            output = subprocess.check_output([sys.executable, "-c", runner.TEMP_PROBE],
                                             env=dict(os.environ, LOCALAPPDATA=str(profile)), text=True)
            self.assertEqual(Path(output.strip()), (profile / "Temp/winci").resolve())
            self.assertTrue(Path(output.strip()).is_dir())

    @unittest.skipUnless(sys.platform == "linux", "runner orchestration uses Linux locks")
    def test_main_supplies_profile_temp_and_hydrates_before_running_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tests/mod_editor").mkdir(parents=True)
            (root / "tests/mod_editor/test_fixture.py").write_text("")
            events = []
            def check(command, env, *args):
                if command[-1] == runner.TEMP_PROBE:
                    return r"C:\users\test\AppData\Local\Temp\winci"
                if command[-1] == runner.OS_PROBE:
                    self.assertEqual(env["TEMP"], env["TMP"])
                    self.assertEqual(env["TMPDIR"], env["TMP"])
                    self.assertIn(r"AppData\Local\Temp\winci", env["TMP"])
                return "probe OK"
            def hydrate(repo, source):
                events.append("hydrate")
            def run_file(test, repo, repo_windows, runtime, env, *args):
                events.append("test")
                self.assertEqual(env["TEMP"], r"C:\users\test\AppData\Local\Temp\winci")
                self.assertEqual(env["TMP"], env["TEMP"])
                self.assertEqual(env["TMPDIR"], env["TEMP"])
                return runner.Result(test.name, output="Ran 1 test\nOK\n")
            with patch.object(runner.shutil, "which", return_value="command"), \
                 patch.object(runner, "checked", side_effect=check), \
                 patch.object(runner, "hydrate_from", side_effect=hydrate), \
                 patch.object(runner, "ensure_runtime", return_value=root / "runtime"), \
                 patch.object(runner, "ensure_prefix"), patch.object(runner, "prove_imports"), \
                 patch.object(runner, "windows_path", return_value=r"Z:\fixture"), \
                 patch.object(runner, "run_file", side_effect=run_file), \
                 contextlib.redirect_stdout(io.StringIO()):
                rc = runner.main(["--repo", str(root), "--work", str(root / "work"),
                                  "--hydrate-from", str(root / "sibling"), "-j", "2"])
            self.assertEqual(rc, 0)
            self.assertEqual(events, ["hydrate", "test"])

    @unittest.skipUnless(sys.platform == "linux", "runner orchestration uses Linux locks")
    def test_main_freezes_lean_policy_after_hydration_on_the_selected_repo(self):
        for option in ("--hydrate-from", "--hydrate-release"):
            for present_after in (False, True):
                with self.subTest(option=option, present_after=present_after), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    repo = root / "selected"
                    tests = repo / "tests/mod_editor"
                    tests.mkdir(parents=True)
                    for name in ("test_000_mutates_inventory.py", "test_all_textures_workspace.py"):
                        (tests / name).write_text("")
                    inventory = repo / runner.EVIDENCE
                    inventory.parent.mkdir(parents=True)
                    def set_inventory(present):
                        if present:
                            inventory.write_text("{}")
                        else:
                            inventory.unlink(missing_ok=True)
                    set_inventory(not present_after)
                    def hydrate(*args):
                        set_inventory(present_after)
                    launched = []
                    def execute(command, env, cwd, log, timeout, pidfile):
                        self.assertEqual(cwd, repo)
                        launched.append(log.name)
                        set_inventory(not present_after)
                        log.write_text("Ran 1 test\nOK\n")
                        return 0
                    hydration_args = [option, str(root / "source")] if option == "--hydrate-from" else [option]
                    with patch.object(runner.shutil, "which", return_value="command"), \
                         patch.object(runner, "ROOT", root / "wrong-repo"), \
                         patch.object(runner, "checked", return_value="probe OK"), \
                         patch.object(runner, "hydrate_from", side_effect=hydrate), \
                         patch.object(runner, "hydrate_release", side_effect=hydrate), \
                         patch.object(runner, "ensure_runtime", return_value=root / "runtime"), \
                         patch.object(runner, "ensure_prefix"), patch.object(runner, "prove_imports"), \
                         patch.object(runner, "windows_path", return_value=r"Z:\selected"), \
                         patch.object(runner, "run_process", side_effect=execute), \
                         contextlib.redirect_stdout(io.StringIO()) as output:
                        rc = runner.main(["--repo", str(repo), "--work", str(root / "work"), "-j", "1", *hydration_args])
                    self.assertEqual(rc, 0)
                    self.assertEqual(len(launched), 2 if present_after else 1)
                    self.assertIn(f"lean_checkout={int(not present_after)}; inventory={inventory}", output.getvalue())
                    self.assertIn(f"inventory_before_hydration={'absent' if present_after else 'present'}", output.getvalue())
                    self.assertIn(str(inventory), (root / "work/logs/checkout.log").read_text())

    def test_environment_clears_display_and_isolated_pythonpath(self):
        with patch.dict(os.environ, {"DISPLAY": ":99", "WAYLAND_DISPLAY": "socket", "PYTHONPATH": "wrong", "PYTHONHOME": "wrong"}):
            isolated = runner.wine_environment(Path("/tmp/prefix"))
            normal = runner.wine_environment(Path("/tmp/prefix"), r"Z:\repo with spaces")
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH", "PYTHONHOME"):
            self.assertNotIn(key, isolated)
        self.assertEqual(normal["PYTHONPATH"], r"Z:\repo with spaces")
        self.assertEqual(isolated["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(isolated["MOD_STUDIO_NO_UPDATE_CHECK"], "1")
        self.assertEqual(isolated["PYTHONFAULTHANDLER"], "1")

    def test_private_pth_does_not_pin_a_checkout_or_installer_app(self):
        self.assertEqual(runner.pth_text().splitlines(), [
            "winci-bootstrap", "python312.zip", ".", "Lib\\site-packages", "import site"])

    def test_startup_resolves_repo_and_isolated_stage(self):
        with tempfile.TemporaryDirectory(prefix="winci import ") as temp:
            root = Path(temp)
            for name in ("repo", "stage"):
                package = root / name / "mod_editor"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("")
            # -I -S removes host startup/PYTHONPATH. Execute the exact private
            # startup source to check its path decisions using real imports.
            code = runner.STARTUP + "\nimport mod_editor; print(mod_editor.__file__)\n"
            env = dict(os.environ, PYTHONPATH=str(root / "repo"))
            normal = subprocess.check_output([sys.executable, "-I", "-S", "-c", code], cwd=root, env=env, text=True)
            self.assertEqual(Path(normal.strip()), root / "repo/mod_editor/__init__.py")
            env.pop("PYTHONPATH")
            isolated = subprocess.check_output([sys.executable, "-I", "-S", "-c", code], cwd=root / "stage", env=env, text=True)
            # macOS keeps temp dirs behind the /var -> /private/var symlink: compare resolved paths
        self.assertEqual(Path(isolated.strip()).resolve(), (root / "stage/mod_editor/__init__.py").resolve())

    def test_startup_restores_script_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sibling.py").write_text("value = 42\n")
            code = "import sys; sys.argv = [" + repr(str(root / "script.py")) + "]\n"
            code += runner.STARTUP + "\nimport sibling; print(sibling.value)\n"
            result = subprocess.check_output([sys.executable, "-I", "-S", "-c", code], text=True)
            self.assertEqual(result.strip(), "42")

    def test_run_file_selects_environment_and_records_windows_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seen = []
            def execute(command, env, cwd, log, timeout, pidfile):
                seen.append((command, env))
                log.write_text("Ran 2 tests\nOK\n")
                return 0
            env = runner.wine_environment(root / "prefix")
            with patch.object(runner, "run_process", side_effect=execute):
                for name in (runner.ISOLATED, "test_modpack.py"):
                    result = runner.run_file(root / name, root, r"Z:\repo space", root / "runtime", env, root, 420, r"Z:\logs", True)
                    self.assertEqual(result.rc, 0)
            self.assertNotIn("PYTHONPATH", seen[0][1])
            self.assertEqual(seen[1][1]["PYTHONPATH"], r"Z:\repo space")
            self.assertEqual(seen[1][0][-2], r"Z:\repo space\tests\mod_editor\test_modpack.py")
            self.assertEqual(seen[1][0][-1], r"Z:\logs\test_modpack.py.pid")
            self.assertNotIn("PYTHONPATH", env)


class CacheTests(unittest.TestCase):
    def test_build_once_private_copy_and_builder_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            builder_file = root / "builder.py"
            builder_file.write_text("version 1")
            calls = []
            class Builder:
                __file__ = str(builder_file)
                @staticmethod
                def build_runtime(work, downloads):
                    calls.append(work)
                    runtime = work / "runtime"
                    runtime.mkdir(exist_ok=True)
                    (runtime / "python.exe").write_bytes(b"pinned executable")
                    (runtime / "python312._pth").write_text("installer pth")
            with patch.object(runner, "installer_module", return_value=Builder), contextlib.redirect_stdout(io.StringIO()):
                private = runner.ensure_runtime(root)
                runner.ensure_runtime(root)
                self.assertEqual(len(calls), 1)
                self.assertEqual((root / "runtime/python312._pth").read_text(), "installer pth")
                self.assertEqual((private / "python312._pth").read_text(), runner.pth_text())
                self.assertEqual((private / "python.exe").read_bytes(), b"pinned executable")
                builder_file.write_text("version 2")
                runner.ensure_runtime(root)
                self.assertEqual(len(calls), 2)

    def test_existing_unowned_prefix_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "system.reg").write_text("unrelated prefix")
            with self.assertRaisesRegex(RuntimeError, "unowned Wine prefix"):
                runner.ensure_prefix(root, {}, root)


@unittest.skipUnless(sys.platform == "linux", "Unix process groups require Linux")
class ProcessTests(unittest.TestCase):
    def test_output_pump_flushes_a_partial_chunk_before_pipe_eof(self):
        read_fd, write_fd = os.pipe()
        output = io.StringIO()
        received = threading.Event()
        expected = "Ran 17 tests in 71.000s\n\nFAILED (errors=5)\n"

        class ObservedOutput:
            def write(self, text):
                output.write(text)
                if output.getvalue() == expected:
                    received.set()

            def flush(self):
                pass

        pump = threading.Thread(target=runner._pump, args=(
            os.fdopen(read_fd, "rb"), ObservedOutput(), threading.Lock()))
        pump.start()
        try:
            os.write(write_fd, expected.encode())
            flushed_before_eof = received.wait(timeout=1)
        finally:
            os.close(write_fd)
            pump.join(timeout=2)
        self.assertFalse(pump.is_alive())
        self.assertTrue(flushed_before_eof, "partial output was buffered until EOF")
        self.assertEqual(output.getvalue(), expected)

    def test_exited_launcher_with_inherited_stdout_still_times_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child = "import time; time.sleep(60)"
            parent = ("import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
                      + repr(child) + "]); print('final partial chunk', flush=True)")
            log = root / "test.log"
            started = time.monotonic()
            rc = runner.run_process([sys.executable, "-c", parent], dict(os.environ), root, log, 1)
            self.assertEqual(rc, 124)
            self.assertLess(time.monotonic() - started, 5)
            self.assertIn("final partial chunk\n", log.read_text())
            self.assertIn("TIMED OUT after 1s", log.read_text())

    def test_timeout_targets_only_the_recorded_windows_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pidfile = root / "test.pid"
            pidfile.write_text("77")
            parent, killer = Mock(), Mock()
            parent.stdout = io.BytesIO(b"child output\n")
            killer.wait.return_value = 0
            env = {"WINEPREFIX": str(root / "dedicated")}
            with patch.object(runner.subprocess, "Popen", side_effect=[parent, killer]) as popen, \
                 patch.object(runner, "kill_group") as kill, \
                 patch.object(runner.time, "monotonic", side_effect=[0, 1]):
                rc = runner.run_process(["wine", "python.exe"], env, root, root / "log", 0.5, pidfile)
            self.assertEqual(rc, 124)
            self.assertEqual(popen.call_args_list[1].args[0], ["wine", "taskkill", "/PID", "77", "/T", "/F"])
            self.assertEqual(popen.call_args_list[1].kwargs["env"], env)
            self.assertEqual([call.args[0] for call in kill.call_args_list], [killer, parent])

    def test_hung_taskkill_still_kills_the_launcher_group(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pidfile = root / "test.pid"
            pidfile.write_text("77")
            parent, killer = Mock(), Mock()
            parent.stdout = io.BytesIO(b"child output\n")
            killer.wait.side_effect = subprocess.TimeoutExpired("taskkill", 30)
            with patch.object(runner.subprocess, "Popen", side_effect=[parent, killer]), \
                 patch.object(runner, "kill_group") as kill, \
                 patch.object(runner.time, "monotonic", side_effect=[0, 1]):
                rc = runner.run_process(["wine", "python.exe"], {}, root, root / "log", 0.5, pidfile)
            self.assertEqual(rc, 124)
            self.assertEqual([call.args[0] for call in kill.call_args_list], [killer, parent])
            self.assertIn("taskkill timed out", (root / "log").read_text())

    def test_actual_pth_startup_and_child_import_isolation(self):
        # Native CPython also implements ._pth. Exercise the actual site hook
        # and a child interpreter without pretending these are Windows tests.
        with tempfile.TemporaryDirectory(prefix="winci pth ") as temp:
            root = Path(temp)
            python = root / "python"
            shutil.copy2(sys.executable, python)
            (root / "python._pth").write_text("\n".join([
                str(root), sysconfig.get_path("stdlib"), sysconfig.get_config_var("DESTSHARED"), "import site", ""]))
            (root / "sitecustomize.py").write_text(runner.STARTUP)
            for name in ("repo", "stage"):
                package = root / name / "mod_editor"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("")
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "sibling.py").write_text("value = 42\n")
            child_probe = "import mod_editor; print(mod_editor.__file__)"
            script = scripts / "check.py"
            script.write_text(
                "import os,subprocess,sys,sibling,mod_editor\n"
                "assert sibling.value == 42\nprint(mod_editor.__file__, flush=True)\n"
                "env=dict(os.environ); env.pop('PYTHONPATH',None)\n"
                "subprocess.run([sys.executable,'-c'," + repr(child_probe) + "], env=env, cwd="
                + repr(str(root / "stage")) + ", check=True)\n")
            env = dict(os.environ, PYTHONPATH=str(root / "repo"))
            result = subprocess.check_output([str(python), str(script)], cwd=root, env=env, text=True)
            self.assertEqual([Path(p) for p in result.splitlines()], [
                root / "repo/mod_editor/__init__.py", root / "stage/mod_editor/__init__.py"])

    def test_timeout_kills_child_and_grandchild_and_records_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pid = root / "descendant"
            child = "import os,time,pathlib; pathlib.Path(" + repr(str(pid)) + ").write_text(str(os.getpid())); time.sleep(60)"
            parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(60)"
            log = root / "test.log"
            started = time.monotonic()
            rc = runner.run_process([sys.executable, "-c", parent], dict(os.environ), root, log, 1)
            self.assertEqual(rc, 124)
            self.assertLess(time.monotonic() - started, 5)
            self.assertIn("TIMED OUT after 1s", log.read_text())
            descendant = int(pid.read_text())
            # A killed child can briefly remain a zombie until PID 1 reaps it.
            status = Path(f"/proc/{descendant}/stat")
            deadline = time.monotonic() + 2
            while status.exists():
                try:
                    state = status.read_text().split(") ", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == "Z":
                    break
                self.assertLess(time.monotonic(), deadline, "timed-out descendant is still running")
                time.sleep(0.01)

    def test_lock_refuses_a_second_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            with runner.exclusive(lock), self.assertRaisesRegex(RuntimeError, "another runner"):
                with runner.exclusive(lock):
                    self.fail("second lock acquired")


class WineAvailabilityTests(unittest.TestCase):
    def test_wine_can_start_without_a_display(self):
        if sys.platform != "linux" or not shutil.which("wine"):
            self.skipTest("Wine is absent; pure runner contracts were still tested")
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(["wine", "--version"], capture_output=True, text=True, timeout=15,
                                    env=runner.wine_environment(Path(temp) / "prefix"))
        if result.returncode in (-31, 159):
            self.skipTest("execution sandbox denies Wine startup (SIGSYS); Windows acceptance is unverified")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wine-", result.stdout)


if __name__ == "__main__":
    unittest.main()
