"""b77 co3: the automatic coach AI is decided before any write.

On a disc whose rosters (with the build's roster edits) do not carry the 32 2026 head coaches, the whole option is
skipped (executable kernel and profiles: the build runs as if it were off) and one plain line says so in the build
log, the receipt's user notes, the completion notice and the Build summary. A roster that carries them (the SOFTDRINK
2K28 pack's roster edits, or a SOFTDRINK disc) keeps the option unchanged.

The always-on tests use no disc. The retail checks read the user's own retail USA image and skip without it
(point NFL2K5_RETAIL_XISO at it); nothing is written to it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import build_feedback  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_coach_ai as ai  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
HAVE_RETAIL = RETAIL.is_file()
MESSAGE = ("2026 CPU coach profiles skipped: this disc's rosters do not have the 2026 head coaches. "
           "Install the SOFTDRINK 2K28 pack to use them.")


def _coaches_document(image, *, leave_out=()):
    """A minimal roster-edits document naming the 32 profile coaches, as the SOFTDRINK pack's roster edits do."""
    roster = rr.load_image(image)
    entries = []
    for row in ai.portrait_rows():
        if row["team"] in leave_out:
            continue
        coach = json.loads((ROOT / "data/vip/coaches" / f"{row['team']}.json").read_text(encoding="utf-8"))["coach"]
        first, last = coach.split(" ", 1)
        entries.append({"team": roster.teams[row["book_index"]].abbreviation, "first": first, "last": last})
    return {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": entries}


class Decision(unittest.TestCase):
    def test_the_message_is_one_plain_line(self):
        self.assertEqual(ai.SKIP_MESSAGE, MESSAGE)
        self.assertNotIn("\n", MESSAGE)
        self.assertNotIn("—", MESSAGE)

    def test_off_or_not_an_image_leaves_the_plan_alone(self):
        plan = mod_build.BuildPlan("missing.xbe", "out.xbe", coach_ai=False)
        self.assertEqual(mod_build._coach_ai_decision(plan), (plan, None))
        plan = mod_build.BuildPlan("missing.xbe", "out.xbe", coach_ai=True)
        self.assertEqual(mod_build._coach_ai_decision(plan), (plan, None))

    def test_not_ready_turns_the_option_off_with_one_note(self):
        said = []
        not_ready = dict(ready=False, checked=32, mismatches=["SF: roster coach 'Dennis Erickson' is not 'Kyle Shanahan'"])
        plan = mod_build.BuildPlan("retail.xiso.iso", "out.xiso.iso", coach_ai=True, cpu_money_downs="retail")
        with mock.patch.object(mod_build.tt, "is_disc_image", return_value=True), \
                mock.patch.object(mod_build.tt.coach_ai_patch, "roster_readiness", return_value=not_ready) as check:
            out, step = mod_build._coach_ai_decision(plan, lambda message, done, total: said.append(message))
        check.assert_called_once_with("retail.xiso.iso", roster_edits=None)
        self.assertIs(out.coach_ai, False)
        self.assertEqual(out.cpu_money_downs, "retail")          # coach AI's Modern 2 rides with it, not without it
        self.assertEqual(mod_build._validated_r62_plan_options(out)["cpu_money_downs"], "retail")
        self.assertEqual(said, [MESSAGE])
        self.assertEqual((step["step"], step["status"], step["applied"], step["decided"], step["user_notes"]),
                         ("coach_ai_resources", "skipped", False, "before any write", [MESSAGE]))
        title, message = build_feedback.completion({"outcome": {"status": "changed", "message": "Changed."},
                                                    "steps": [step]})
        self.assertEqual(message.splitlines()[-1], MESSAGE)

    def test_ready_keeps_the_option(self):
        plan = mod_build.BuildPlan("pack.xiso.iso", "out.xiso.iso", coach_ai=True, roster_edits="edits.json")
        with mock.patch.object(mod_build.tt, "is_disc_image", return_value=True), \
                mock.patch.object(mod_build.tt.coach_ai_patch, "roster_readiness",
                                  return_value=dict(ready=True, checked=32, mismatches=[])) as check:
            self.assertEqual(mod_build._coach_ai_decision(plan), (plan, None))
        check.assert_called_once_with("pack.xiso.iso", roster_edits="edits.json")

    def test_build_decides_before_any_copy_and_hands_the_reduced_plan_on(self):
        """build(): the decision runs right after the plan and path checks, before the board preflight, the money-downs
        options, the destination check and the private copy; the skipped plan is what the build then runs."""
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        body = source[source.index("def build(plan: BuildPlan"):source.index("def preflight_plan(")]
        at = body.index("plan, coach_ai_skip = _coach_ai_decision(plan, progress)")
        for later in ("preflight_board_source(plan, progress)", "r62 = _validated_r62_plan_options(plan)",
                      "check_image_destination(target", "tempfile.TemporaryDirectory(", "_project_builder(effective_source)",
                      "receipt = _build("):
            self.assertLess(at, body.index(later), later)
        self.assertIn('receipt["steps"].append(coach_ai_skip)', body)
        preflight = source[source.index("def preflight_plan("):source.index("def _coach_ai_decision(")]
        self.assertLess(preflight.index("_coach_ai_decision(plan, progress)"), preflight.index("_build(plan"))

    def test_a_skipped_build_runs_without_coach_ai_and_reports_it(self):
        seen = {}

        class Stop(Exception):
            pass

        def fake_build(plan, progress=None, **kwargs):
            seen["plan"], seen["r62"] = plan, kwargs.get("r62_options")
            raise Stop

        not_ready = dict(ready=False, checked=32, mismatches=["x"])
        with tempfile.TemporaryDirectory(prefix="coach-ai-gate-") as raw:
            folder = Path(raw)
            source = folder / "retail.xiso.iso"
            source.write_bytes(b"\0" * 4096)
            target = folder / "out.xiso.iso"
            plan = mod_build.BuildPlan(str(source), str(target), coach_ai=True)
            with mock.patch.object(mod_build.tt, "is_disc_image", return_value=True), \
                    mock.patch.object(mod_build, "validate_plan", return_value=[]), \
                    mock.patch.object(mod_build.tt.coach_ai_patch, "roster_readiness", return_value=not_ready), \
                    mock.patch.object(mod_build, "_build", side_effect=fake_build):
                with self.assertRaises(Stop):
                    mod_build.build(plan)
            self.assertIs(seen["plan"].coach_ai, False)
            self.assertEqual(seen["r62"]["cpu_money_downs"], plan.cpu_money_downs)
            self.assertFalse(target.exists())


class StudioGui(unittest.TestCase):
    def test_the_completion_dialog_and_the_build_summary_carry_the_line(self):
        """The Build page's completion notice (QMessageBox) and its Copy Build summary text both end with the line."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
        except ImportError:
            self.skipTest("PyQt5 not installed")
        from mod_editor.gui.build_panel_qt import BuildPanel
        app = QApplication.instance() or QApplication([])
        panel = BuildPanel(available={})
        try:
            step = {"step": "coach_ai_resources", "status": "skipped", "requested": True, "applied": False,
                    "decided": "before any write", "checked": 32, "mismatches": ["x"], "user_notes": [MESSAGE]}
            receipt = {"target": "output.xiso.iso", "steps": [step], "result": {"path": "output.xiso.iso"},
                       "outcome": {"status": "changed", "message": "The copy differs from your source."},
                       "coach_ai_skipped": MESSAGE}
            with mock.patch.object(QMessageBox, "information") as shown, mock.patch.object(panel, "apply_state"):
                panel._done(receipt)
            title, body = shown.call_args[0][1:3]
            self.assertEqual(title, "Disc ready")
            self.assertIn(MESSAGE, body.splitlines())
            self.assertIn(MESSAGE, panel._last_build_summary.splitlines())
            self.assertIn(MESSAGE, panel.status_label.text())
        finally:
            panel.deleteLater()
            app.processEvents()


@unittest.skipUnless(HAVE_RETAIL, "retail USA image not present (NFL2K5_RETAIL_XISO)")
class RetailRosters(unittest.TestCase):
    def test_a_retail_dump_does_not_carry_the_2026_coaches(self):
        result = ai.roster_readiness(RETAIL)
        self.assertFalse(result["ready"])
        self.assertEqual(result["checked"], 32)
        self.assertEqual(len(result["mismatches"]), 32)
        self.assertIn("SF: roster coach 'Dennis Erickson' is not 'Kyle Shanahan'", result["mismatches"])

    def test_roster_edits_with_the_2026_coaches_make_it_ready(self):
        """The pack path: the build's roster edits name every 2026 head coach, so the profiles apply."""
        document = _coaches_document(RETAIL)
        self.assertEqual(ai.roster_readiness(RETAIL, roster_edits=document),
                         dict(ready=True, checked=32, mismatches=[]))
        with tempfile.TemporaryDirectory(prefix="coach-ai-edits-") as raw:
            path = Path(raw) / "roster-edits.json"
            path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
            self.assertTrue(ai.roster_readiness(RETAIL, roster_edits=str(path))["ready"])
            plan = mod_build.BuildPlan(str(RETAIL), str(Path(raw) / "out.xiso.iso"), coach_ai=True,
                                       roster_edits=str(path))
            self.assertEqual(mod_build._coach_ai_decision(plan), (plan, None))

    def test_one_missing_coach_skips_the_whole_option(self):
        document = _coaches_document(RETAIL, leave_out=("NYG",))
        result = ai.roster_readiness(RETAIL, roster_edits=document)
        self.assertFalse(result["ready"])
        self.assertEqual(len(result["mismatches"]), 1)
        self.assertTrue(result["mismatches"][0].startswith("NYG: roster coach "))
        plan = mod_build.BuildPlan(str(RETAIL), "out.xiso.iso", coach_ai=True)
        out, step = mod_build._coach_ai_decision(plan)
        self.assertIs(out.coach_ai, False)
        self.assertEqual(step["user_notes"], [MESSAGE])

    def test_the_check_reads_only(self):
        before = RETAIL.stat()
        ai.roster_readiness(RETAIL, roster_edits=_coaches_document(RETAIL))
        after = RETAIL.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))


if __name__ == "__main__":
    unittest.main()
