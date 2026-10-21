"""fx1: build-path fixes from the b777 code reviews (ULTRA pr67/pr68/pr69, FINDINGS-LOCAL-*).

Each test names its finding. The real-XBE tests use the pinned USA retail default.xbe and skip without it.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402


def _retail():
    from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
    return retail_xbe()


class Preflights(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def xbe_source(self):
        source = self.root / "default.xbe"
        source.write_bytes(_retail())
        return source

    def plan(self, **options):
        return mod_build.BuildPlan(source=str(self.xbe_source()), target=str(self.root / "out.xbe"), **options)

    def test_team_ratings_preflight_reads_a_str_xbe_source(self):
        """pr67: _xbe_bytes(plan.source) got a str; a bare default.xbe raised AttributeError."""
        self.assertEqual(mod_build._xbe_bytes(str(self.xbe_source())), _retail())
        with self.assertRaisesRegex(ValueError, "Modern team ratings require modern position pools"):
            mod_build.preflight_plan(self.plan(team_ratings=True), lambda *a: None)

    def test_run_blocking_refuses_a_foreign_source_before_any_write(self):
        """pr68 nit: run blocking had no foreign-source preflight (qb_accuracy has one)."""
        from mod_editor.core import nfl2k5_run_blocking as rb
        mod_build.preflight_plan(self.plan(run_blocking=True), lambda *a: None)   # retail passes
        with patch.object(rb, "status", return_value="foreign"):
            with self.assertRaisesRegex(ValueError, "blocking code in this source is not retail"):
                mod_build.preflight_plan(self.plan(run_blocking=True), lambda *a: None)
        self.assertFalse((self.root / "out.xbe").exists())

    def test_dated_refresh_without_position_pools_refuses_in_preflight(self):
        """pr67 #3: 'Dated roster refresh requires modern position pools' was only checked after every writer."""
        import os
        image = os.environ.get("NFL2K5_RETAIL_IMAGE")
        if not image or not Path(image).is_file():
            self.skipTest("NFL2K5_RETAIL_IMAGE (the USA retail disc image) is not set")
        edits = self.root / "edits.json"
        edits.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": [], "roster_refresh": {}}), encoding="utf-8")
        plan = mod_build.BuildPlan(source=image, target=str(self.root / "out.iso"), roster_edits=str(edits))
        progress = []
        with self.assertRaisesRegex(ValueError, "Dated roster refresh requires modern position pools"):
            mod_build.preflight_plan(plan, lambda message, *a: progress.append(message))
        self.assertFalse((self.root / "out.iso").exists())


class RebuildRefusals(unittest.TestCase):
    """pr67 #4, pr68 #1-#3, #5: a disc an earlier Studio build made is refused before any write, not at the end."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.source = Path(self._tmp.name) / "default.xbe"

    def check(self, payload, **options):
        self.source.write_bytes(payload)
        plan = mod_build.BuildPlan(source=str(self.source), target=str(self.source) + ".out", **options)
        mod_build._rebuild_refusals(plan, self.source, False, lambda *a: None)

    def scaleout_with_qb_accuracy(self):
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_qb_accuracy as qa
        from mod_editor.core import nfl2k5_throw_tuning as tt
        payload, _ = space.apply(_retail(), tt._selected_space_requests(coach_ai=True), scaleout=True)
        return qa.apply(payload)[0]

    def test_a_retail_source_is_never_judged(self):
        self.check(_retail(), letter_grades=True, run_blocking=True, qb_accuracy=True, espn25_more_moments=True,
                   espn25_named_previews=True, play_art_routes=True)

    def test_an_earlier_late_owner_after_a_later_one_refuses_like_the_writer_would(self):
        from mod_editor.core import nfl2k5_run_blocking as rb
        payload = self.scaleout_with_qb_accuracy()
        with self.assertRaisesRegex(ValueError, "would move an existing allocation"):
            rb.apply(payload)                               # what the build hit after every step
        with self.assertRaisesRegex(ValueError, "without Run blocking.*nfl2k5_qb_accuracy.*retail dump"):
            self.check(payload, run_blocking=True)
        self.check(payload, qb_accuracy=True)               # already there: nothing to append

    def test_older_venue_names_and_the_era_ball_refuse(self):
        from mod_editor.core import nfl2k5_moment_venues as venues, nfl2k5_era_ball as ball
        payload = self.scaleout_with_qb_accuracy()
        with patch.object(venues, "status", return_value="previous"):
            with self.assertRaisesRegex(ValueError, "older Historical Anniversary venue names"):
                self.check(payload, espn25_more_moments=True, espn25_named_previews=True)
        with patch.object(venues, "status", return_value="retail"), patch.object(ball, "enabled", return_value=False), \
                patch.object(ball, "image_status", return_value="applied"):
            plan = mod_build.BuildPlan(source=str(self.source), target="y", espn25_more_moments=True,
                                       espn25_named_previews=True)
            self.source.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, "era ball"):
                mod_build._rebuild_refusals(plan, self.source, True, lambda *a: None)

    def test_lg2_letter_grades_refuse(self):
        import os
        b776 = os.environ.get("NFL2K5_B776_XBE")
        if not b776 or not Path(b776).is_file():
            self.skipTest("NFL2K5_B776_XBE (the extracted b776 test-disc default.xbe) is not set")
        with self.assertRaisesRegex(ValueError, "older Letter grades revision"):
            self.check(Path(b776).read_bytes(), letter_grades=True)
        self.check(Path(b776).read_bytes(), run_blocking=True)   # b776 + run blocking appends cleanly


class RefreshDefersTheLockCheck(unittest.TestCase):
    def test_main_pass_before_a_refresh_does_not_judge_pre_refresh_locks(self):
        """pr67 #2: the build drops roster_refresh from the main pass, which then ran check_depth_locks on the
        pre-refresh roster; the refresh validates the final club chains itself."""
        from tests.mod_editor.test_franchise_upgrade import disc_roster, fixture
        body = disc_roster(fixture()[0])      # a synthetic main-roster body that apply_body accepts
        doc = {"schema": rr.EDITS_SCHEMA, "edits": []}
        calls = []
        with patch.object(rr.RosterDocument, "check_depth_locks", lambda self: calls.append(1)):
            deferred, _ = rr.apply_body(body, doc, refresh_follows=True)
            self.assertEqual(calls, [])
            checked, _ = rr.apply_body(body, doc)
        self.assertEqual(calls, [1])
        self.assertEqual(deferred, checked)   # the check only reads


if __name__ == "__main__":
    unittest.main()
