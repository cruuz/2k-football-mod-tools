"""b778 rt1: the QB Throw Power curve directive and the 2026 QB arm / career layer; synthetic data, no game bytes.

Noah (2026-10-22): Mahomes rated too low, "a lot of quarterbacks need higher throw power ratings ... I updated Cam
Ward's in my franchise, but I feel like it should be scaled across the league."  The tests pin the curve form of the
``qb_throw_power`` directive (monotone, capped, never lowers, slope 0..1, Noah's Ward calibration 82 -> 93, the rookie
templates move with it, the build applies it) and the tool's rules (a full season of tracking before the arm moves,
at most 8 points, the career anchor is a floor, only arm / read / consistency are written).
"""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import mod_build as build  # noqa: E402
from mod_editor.core import nfl2k5_qb_throw_power as qp  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
import test_b77_q1_qb_throw_power as q1  # noqa: E402
from tools.b778 import rt1_qb_ratings as rt1  # noqa: E402

CURVE = qp.normalise_directive(qp.B778_DIRECTIVE)


class CurveTests(unittest.TestCase):
    def test_the_shipped_curve_is_valid_and_calibrated(self) -> None:
        self.assertEqual(CURVE["curve"], [list(p) for p in qp.B778_CURVE])
        self.assertEqual((CURVE["cap"], CURVE["scope"]), (99, "all"))
        # Noah raised Cam Ward from 82 (his franchise predates the +4 directive) to 93
        self.assertEqual(qp.map_value(82, CURVE), 93)
        # the retail 2004 spread keeps its order: Vick 99, Favre/Manning/Culpepper 94, McNair/McNabb 90, middle starter 82
        self.assertEqual([qp.map_value(v, CURVE) for v in (99, 94, 90, 82)], [99, 98, 97, 93])
        self.assertEqual([qp.map_value(v, CURVE) for v in (0, 40, 50, 60, 70, 86, 88, 92, 96)], [20, 60, 70, 79, 86, 95, 96, 97, 98])

    def test_monotone_capped_never_lower_and_no_gap_widens(self) -> None:
        mapped = [qp.map_value(v, CURVE) for v in range(100)]
        self.assertTrue(all(0 <= b - a <= 1 for a, b in zip(mapped, mapped[1:])))
        self.assertTrue(all(m >= v for v, m in zip(range(100), mapped)))
        self.assertLessEqual(max(mapped), 99)
        for big in (100, 110, 127):                       # large attribute values are left alone
            self.assertEqual(qp.map_value(big, CURVE), big)
        self.assertEqual([qp.map_value(v, {**CURVE, "cap": 95}) for v in (80, 90, 99)], [92, 95, 99])

    def test_source_for_inverts_the_curve(self) -> None:
        for target in range(20, 100):
            source = qp.source_for(target, CURVE)
            self.assertEqual(qp.map_value(source, CURVE), target)
            self.assertTrue(source == 0 or qp.map_value(source - 1, CURVE) < target)
        self.assertIsNone(qp.source_for(5, CURVE))
        self.assertEqual(qp.source_for(98, {"add": 4, "cap": 99, "scope": "all"}), 94)

    def test_refusals(self) -> None:
        good = [list(p) for p in qp.B778_CURVE]
        bad_curves = (
            [[0, 20]],                                        # one point
            [[1, 20], [99, 99]],                              # does not start at 0
            [[0, 20], [98, 99]],                              # does not end at 99
            [[0, 20], [50, 70], [50, 71], [99, 99]],          # x does not rise
            [[0, 20], [10, 40], [99, 99]],                    # slope 2: a gap widens
            [[0, 50], [60, 49], [99, 99]],                    # falls, and lowers 60
            [[0, 0], [50, 40], [99, 99]],                     # lowers 50
            [[0, 20.5], [99, 99]],                            # not whole
            "0,20",
        )
        for curve in bad_curves:
            with self.assertRaises(qp.QbThrowPowerError, msg=repr(curve)):
                qp.normalise_directive({"curve": curve})
        with self.assertRaises(qp.QbThrowPowerError):
            qp.normalise_directive({"curve": good, "add": 4})
        with self.assertRaises(qp.QbThrowPowerError):
            qp.normalise_directive({"curve": good, "cap": 0})
        with self.assertRaises(qp.QbThrowPowerError):
            qp.normalise_directive({"curve": good, "scope": "some"})
        # the legacy add form is unchanged
        self.assertEqual(qp.normalise_directive({}), {"add": 4, "cap": 99, "scope": "all"})

    def test_the_roster_edits_reader_accepts_the_curve(self) -> None:
        document = {"schema": rr.EDITS_SCHEMA, "edits": [], "qb_throw_power": qp.B778_DIRECTIVE}
        self.assertEqual(qp.directive_of(rr.read_edits(document)), CURVE)
        with self.assertRaises(qp.QbThrowPowerError):
            rr.read_edits({**document, "qb_throw_power": {"curve": [[0, 0], [99, 98]]}})


class CurveResourceTests(unittest.TestCase):
    def test_only_qb_throw_power_bytes_and_the_rookie_templates_move(self) -> None:
        raw = q1.resource(q1.body_with(q1.ARMS))
        new, changes = qp.apply_resource(raw, CURVE)
        self.assertEqual([i for i in range(len(raw)) if raw[i] != new[i]], sorted(c["offset"] for c in changes))
        # primary QBs 97 and 75; templates 95/96/53/50 bracket a generated prospect
        self.assertEqual([(c["before"], c["after"]) for c in changes],
                         [(97, 98), (75, 89), (95, 98), (96, 98), (53, 73), (50, 70)])
        document = rr.RosterDocument(new[qp.WRAPPER:])
        self.assertEqual([p.record.values["pass_arm_strength"] for p in document.players if p.pool == "primary"][:7],
                         [98, 80, 70, 89, 90, 40, 99])            # non-QBs untouched

    def test_scope_all_on_an_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = q1.ImageTests().image(Path(tmp))
            receipt = qp.apply_image(fixture.path, qp.B778_DIRECTIVE)
            self.assertEqual((receipt["status"], receipt["files_changed"]), ("applied", 2))
            self.assertEqual(receipt["directive"], CURVE)
            self.assertEqual(q1.ImageTests().arms(fixture.path),
                             {5: [98, 89, 98, 98, 73, 70], 6: [79, 97, 86, 86, 60, 60]})

    def test_the_build_applies_the_curve_last(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            fixture = q1.ImageTests().image(root)
            stack.enter_context(patch.object(build, "inspect", return_value={"path": "unused", "container": "xiso"}))
            stack.enter_context(patch.object(build, "_xbe_bytes", side_effect=lambda path: b"XBE-retail"))
            stack.enter_context(patch.object(build, "_write_xbe_bytes", side_effect=lambda path, data: None))
            stack.enter_context(patch.object(build, "_check_playbook_scoring",
                                             return_value={"status": "applied", "books": 0, "faults": 0}))
            stack.enter_context(patch("mod_editor.core.nfl2k5_unc_bowl_uniforms.apply_to_image", return_value={"synthetic": True}))
            stack.enter_context(patch.object(rr, "apply", new=lambda path, *args, **kwargs: {"log": []}))
            edits = root / "edits.json"
            edits.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": [], "qb_throw_power": qp.B778_DIRECTIVE}),
                             encoding="utf-8")
            receipt = build.build(build.BuildPlan(str(fixture.path), str(root / "built.iso"), roster_edits=str(edits)))
            step = [s for s in receipt["steps"] if s["step"] == "qb_throw_power"]
            self.assertEqual(len(step), 1)
            self.assertEqual(step[0]["directive"], CURVE)
            self.assertEqual(q1.ImageTests().arms(root / "built.iso")[5], [98, 89, 98, 98, 73, 70])
            self.assertEqual(q1.ImageTests().arms(fixture.path)[5], [97, 75, 95, 96, 53, 50])


def ngs(gsis: str, distances, season: int = 2025) -> list[dict]:
    rows = [{"season": str(season), "week": str(i + 1), "max_air_distance": str(d), "player_gsis_id": gsis}
            for i, d in enumerate(distances)]
    rows.append({"season": str(season), "week": "0", "max_air_distance": "99", "player_gsis_id": gsis})   # season row
    return rows


class EvidenceTests(unittest.TestCase):
    def test_long_throws_top_three_weeks_and_season_window(self) -> None:
        rows = ngs("a", [50, 61, 58, 60, 40]) + ngs("a", [70], season=2019) + ngs("b", [55, 56])
        out = rt1.long_throws(rows)
        self.assertEqual(out["a"], {"top": round((61 + 60 + 58) / 3, 4), "weeks": 5, "longest": 61.0})
        self.assertEqual(out["b"]["weeks"], 2)

    def test_deep_passing_weights_and_skips_sacks(self) -> None:
        rows = [
            {"pass_attempt": "1", "sack": "0", "season_type": "REG", "air_yards": "25", "passer_player_id": "a", "complete_pass": "1"},
            {"pass_attempt": "1", "sack": "0", "season_type": "POST", "air_yards": "5", "passer_player_id": "a", "complete_pass": "1"},
            {"pass_attempt": "1", "sack": "1", "season_type": "REG", "air_yards": "", "passer_player_id": "a", "complete_pass": "0"},
            {"pass_attempt": "1", "sack": "0", "season_type": "PRE", "air_yards": "40", "passer_player_id": "a", "complete_pass": "1"},
        ]
        out = rt1.deep_passing(rows, 2024)
        self.assertEqual(out["a"], {"att": 1.6, "deep": 0.8, "deep_cmp": 0.8, "deep_cmp_air": 20.0})

    def test_career_epa_counts_early_dropbacks_before_2024_only(self) -> None:
        row = lambda epa: {"player_id": "a", "season_type": "REG", "attempts": "300", "sacks_suffered": "20", "passing_epa": str(epa)}
        out = rt1.career_epa({2022: [row(40)], 2025: [row(10)], 2017: [row(99)]})
        self.assertEqual(out["a"]["early_db"], 320.0)
        self.assertAlmostEqual(out["a"]["epa"], 0.45 * 40 + 10)
        self.assertEqual(sorted(out["a"]["seasons"]), [2022, 2025])


def league(n: int = 20) -> tuple[list[dict], dict, dict]:
    """n QBs: current arm 60 + 2i, long-throw evidence the reverse (the r1 order is wrong), 40 NGS weeks each."""
    qbs, long, deep = [], {}, {}
    for i in range(n):
        g = f"g{i}"
        qbs.append({"key": f"primary:{i}", "gsis": g, "arm": 60 + 2 * i, "current": {"pass_read_coverage": 70, "consistency": 70}})
        long[g] = {"top": 66.0 - 0.5 * i, "weeks": 40, "longest": 70.0}
        deep[g] = {"att": 500.0, "deep": 60.0, "deep_cmp": 25.0, "deep_cmp_air": 25.0 * 27}
    return qbs, long, deep


class PlanTests(unittest.TestCase):
    def test_the_arm_follows_the_evidence_within_eight_points(self) -> None:
        qbs, long, deep = league()
        out = rt1.arm_plan(qbs, long, deep)
        self.assertEqual(len(out), 20)
        for q in qbs:
            row = out[q["key"]]
            self.assertLessEqual(abs(row["arm"] - q["arm"]), rt1.MAX_MOVE)
            self.assertAlmostEqual(row["w"], 0.6 * 40 / 56, places=3)
        self.assertGreater(out["primary:0"]["arm"], qbs[0]["arm"])      # best evidence, lowest arm: up
        self.assertLess(out["primary:19"]["arm"], qbs[19]["arm"])       # worst evidence, highest arm: down
        self.assertEqual(out["primary:0"]["arm"], 68)                   # capped at +8

    def test_less_than_a_season_of_tracking_keeps_the_r1_arm(self) -> None:
        qbs, long, deep = league()
        long["g3"]["weeks"] = 16
        out = rt1.arm_plan(qbs, long, deep)
        self.assertNotIn("primary:3", out)
        qbs.append({"key": "primary:99", "gsis": "", "arm": 80, "current": {}})
        self.assertNotIn("primary:99", rt1.arm_plan(qbs, long, deep))

    def test_the_career_anchor_is_a_floor(self) -> None:
        qbs = [{"key": f"primary:{i}", "gsis": f"g{i}", "arm": 80,
                "current": {"pass_read_coverage": 60 + 3 * i, "consistency": 90 - 3 * i}} for i in range(10)]
        career = {f"g{i}": {"epa": 0.02 * i * 1000, "db": 1000.0, "early_db": 600.0, "seasons": [2022, 2025]} for i in range(10)}
        career["g5"]["early_db"] = 150.0                                 # no career before 2024: not anchored
        out = rt1.career_plan(qbs, career)
        self.assertNotIn("primary:5", out)
        for q in qbs:
            if q["key"] in out:
                for name in rt1.CAREER_FIELDS:
                    self.assertGreaterEqual(out[q["key"]][name], q["current"][name])
        self.assertLessEqual(out["primary:0"]["pass_read_coverage"], 61)   # worst career, lowest read: about unchanged
        self.assertGreater(out["primary:9"]["consistency"], qbs[9]["current"]["consistency"])   # best career lifted

    def test_edit_entries_write_only_arm_read_and_consistency(self) -> None:
        row = {"pool": "primary", "index": 7, "first": "Cam", "last": "Ward",
               "source": {"pass_arm_strength": 82, "pass_read_coverage": 73, "pass_accuracy": 75, "consistency": 45},
               "new": {"pass_arm_strength": 85, "pass_read_coverage": 73, "pass_accuracy": 75, "consistency": 50}}
        self.assertEqual(rt1.edit_entries([row]), [{"pool": "primary", "index": 7, "first": "Cam", "last": "Ward",
                                                    "fields": {"consistency": 50, "pass_arm_strength": 85}}])
        self.assertEqual(rt1.edit_entries([{**row, "new": dict(row["source"])}]), [])

    def test_the_merged_document_carries_the_curve_and_keeps_the_league(self) -> None:
        league_doc = {"schema": rr.EDITS_SCHEMA, "name": "league", "edits": [{"pool": "primary", "index": 1, "fields": {"hand": 0}}],
                      "qb_throw_power": {"add": 4, "cap": 99, "scope": "all"}}
        entry = {"pool": "primary", "index": 2, "first": "A", "last": "B", "fields": {"pass_arm_strength": 90}}
        merged = rt1.merged_document(league_doc, [entry], qp.B778_CURVE)
        self.assertEqual(merged["edits"], league_doc["edits"] + [entry])
        self.assertEqual(qp.directive_of(merged), CURVE)
        self.assertEqual(league_doc["qb_throw_power"], {"add": 4, "cap": 99, "scope": "all"})
        self.assertEqual(rr.read_edits(merged)["edits"][-1], entry)

    def test_match_gsis_prefers_birth_date_then_latest(self) -> None:
        players = [{"position": "QB", "display_name": "Josh Allen", "gsis_id": "old", "birth_date": "1980-01-01", "last_season": "2005"},
                   {"position": "QB", "display_name": "Josh Allen", "gsis_id": "new", "birth_date": "1996-05-21", "last_season": "2025"},
                   {"position": "LB", "display_name": "Josh Allen", "gsis_id": "lb", "birth_date": "1997-07-13", "last_season": "2025"}]
        self.assertEqual(rt1.match_gsis(players, "Josh", "Allen")[0], "new")
        self.assertEqual(rt1.match_gsis(players, "Josh", "Allen", "1980-01-01")[0], "old")
        self.assertEqual(rt1.match_gsis(players, "Michael", "Penix")[0], "")


if __name__ == "__main__":
    unittest.main()
