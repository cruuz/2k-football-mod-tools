"""Job S7: the SportsCenter playoff screens, run natively (Unicorn) on the real executable, before and after.

Each test runs the game's own routines on a synthetic seven-seed league through tools/b77/s7_sportscenter_probe.py
and compares the executable as the v0.5 disc shipped it (the six S7 ranges at their v0.5 values) with the Studio
build.  Only the league data layer and scene service calls are replaced; no gameplay or pixels are claimed.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_playoff_picture as picture  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402

RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) \
    / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "b77" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load("s7_sportscenter_probe")
repair = _load("s7_repair")

FIRST_OUT_CELL = 0x133D3780      # Clinched cell of the eighth row
OLD_STICKER = 0x7362B270         # retail "On The Bubble" widget in the seventh row's numeral column


def cell(result, conf, key):
    return next(c for c in result["conferences"][conf]["overlay_cells"] if c["key"] == f"{key:#010x}")


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN, "private retail default.xbe and unicorn needed")
class SportsCenterNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = RETAIL_XBE.read_bytes()
        built, _ = season.apply(retail)
        cls.after, _ = picture.apply(built)
        raw = bytearray(cls.after)
        sections = strength._sections(cls.after)
        for _label, va, before, _after in repair.OWNED:
            at = season._offset(cls.after, va, sections)
            raw[at:at + len(before)] = before
        out = bytearray(raw)
        for section in sections:
            at = section.header_offset + 36
            out[at:at + 20] = strength.section_digest(bytes(out), section)
        cls.before = bytes(out)                     # the v0.5 shape of every byte S7 owns
        seventeen, _ = season.apply(retail, groups=("playoffs_14",))
        cls.seventeen, _ = picture.apply(seventeen)

    # -- the Playoff Picture -----------------------------------------------------------------------------------
    def test_field_builder_selector_and_narration_are_unchanged_by_the_repair(self):
        for xbe in (self.before, self.after):
            result = probe.probe_picture(xbe, 18, None)
            for conf in (0, 1):
                entry = result["conferences"][conf]
                self.assertTrue(entry["builder_matches_model"])                # seven seeds then the first team out
                self.assertEqual(entry["selector_rank_pool"], [0, 1, 2, 3, 4, 5, 6])
                cases = [row["narration_case"] for row in entry["ranks"]]
                self.assertEqual(cases, [0, 3, 3, 3, 4, 4, 4, 7])               # #1, division x3, berth x3, outside
                self.assertEqual([row["spot"] for row in entry["ranks"]], list(range(1, 9)))

    def test_final_picture_seventh_seed_is_no_longer_the_bubble_team(self):
        before = probe.probe_picture(self.before, 18, None)
        after = probe.probe_picture(self.after, 18, None)
        for conf in (0, 1):
            # v0.5: the seventh SEED's row carries the retail sticker, the real first team out carries nothing
            self.assertEqual(cell(before, conf, OLD_STICKER)["text"], "On The Bubble")
            self.assertEqual(cell(before, conf, FIRST_OUT_CELL)["text"], "")
            # after S7: nothing on the seventh row, "Better Luck Next Year" on the eighth (all 18 weeks played)
            self.assertEqual(cell(after, conf, OLD_STICKER)["text"], "")
            self.assertEqual(cell(after, conf, FIRST_OUT_CELL)["text"], "Better Luck Next Year")
            # the seven statuses are the 9/5 ones in both
            for rank, text in enumerate(["#1 Seed / Bye", "Division Title", "Division Title", "Division Title",
                                         "Playoff Berth", "Playoff Berth", "Playoff Berth"]):
                for result in (before, after):
                    status = next(c for c in result["conferences"][conf]["overlay_cells"]
                                  if c["kind"] == "status" and c["rank"] == rank)
                    self.assertEqual(status["text"], text)

    def test_mid_season_label_is_on_the_first_team_out(self):
        before = probe.probe_picture(self.before, 18, None, played=14)
        after = probe.probe_picture(self.after, 18, None, played=14)
        for conf in (0, 1):
            self.assertEqual(cell(before, conf, OLD_STICKER)["text"], "On The Bubble")
            self.assertEqual(cell(after, conf, OLD_STICKER)["text"], "")
            self.assertEqual(cell(after, conf, FIRST_OUT_CELL)["text"], "On The Bubble")
            # nobody has clinched yet: every real status cell stays blank
            for result in (before, after):
                for c in result["conferences"][conf]["overlay_cells"]:
                    if c["kind"] == "status" and c["rank"] < 7:
                        self.assertEqual(c["text"], "", (conf, c["rank"]))

    def test_label_switches_exactly_at_the_last_regular_week_of_each_season_length(self):
        for xbe, weeks in ((self.after, 18), (self.seventeen, 17)):
            for played in (weeks - 2, weeks - 1, weeks):
                result = probe.probe_picture(xbe, weeks, None, played=played)
                expected = "Better Luck Next Year" if played == weeks else "On The Bubble"
                self.assertEqual(cell(result, 0, FIRST_OUT_CELL)["text"], expected, (weeks, played))
                self.assertEqual(cell(result, 0, OLD_STICKER)["text"], "", (weeks, played))

    def test_descriptor_table_shape_before_and_after(self):
        """41 widgets: name/wins/losses/ties for ranks 0-7, status for 0-6, and exactly one label widget."""
        import struct
        def table(xbe):
            sections = strength._sections(xbe)
            at = season._offset(xbe, 0x50F8E0, sections)
            return [struct.unpack_from("<III", xbe, at + 12 * i) for i in range(41)]
        names = {0: "name", 1: "wins", 2: "losses", 3: "ties", 4: "status", 5: "label"}
        for xbe, label_key, blank_key in ((self.before, OLD_STICKER, FIRST_OUT_CELL),
                                          (self.after, FIRST_OUT_CELL, OLD_STICKER)):
            rows = table(xbe)
            self.assertEqual(len({key for key, _kind, _rank in rows}), 41)
            labels = [(key, rank) for key, kind, rank in rows if kind == 5]
            self.assertEqual([key for key, _rank in labels], [label_key])
            for kind in (0, 1, 2, 3):
                self.assertEqual(sorted(rank for _k, kd, rank in rows if kd == kind), list(range(8)), names[kind])
            status = sorted(rank for _k, kd, rank in rows if kd == 4)
            # eight status entries both times: v0.5 has ranks 0-7; S7 swaps which widget is the rank-7 status
            self.assertEqual(status, list(range(8)) if xbe is self.before else list(range(7)) + [7])
        after = table(self.after)
        self.assertEqual([row for row in after if row[0] == FIRST_OUT_CELL], [(FIRST_OUT_CELL, 5, 7)])
        self.assertEqual([row for row in after if row[0] == OLD_STICKER], [(OLD_STICKER, 4, 7)])
        before = table(self.before)
        self.assertEqual([row for row in before if row[0] == FIRST_OUT_CELL], [(FIRST_OUT_CELL, 4, 7)])
        self.assertEqual([row for row in before if row[0] == OLD_STICKER], [(OLD_STICKER, 5, 0)])
        # only these two entries differ
        self.assertEqual([i for i, (a, b) in enumerate(zip(before, after)) if a != b], [39, 40])

    # -- the show banner -----------------------------------------------------------------------------------------
    def test_banner_names_every_postseason_round_one_round_early_before_and_correctly_after(self):
        def names(xbe, weeks):
            return {row["weeks_played"]: (row["line_1"] + " " + row["line_2"]).strip() or row["single_line"]
                    for row in probe.probe_title(xbe, weeks)}
        old, new = names(self.before, 18), names(self.after, 18)
        # v0.5 (18-week league): the 18th week is already called Wildcard Week and the Super Bowl comes a round early
        self.assertEqual(old[18], "Wildcard Week")
        self.assertEqual(old[19], "Division Championships")
        self.assertEqual(old[21], "Super Bowl")
        self.assertEqual(old[22], "Pro Bowl")
        self.assertNotIn("Week 18", old.values())
        # repaired: Week 18, then the rounds as they are played, Super Bowl after the Super Bowl row (21)
        self.assertEqual({k: new[k] for k in range(16, 23)},
                         {16: "Week 16", 17: "Week 17", 18: "Week 18", 19: "Wildcard Week",
                          20: "Division Championships", 21: "Conference Championships", 22: "Super Bowl"})
        # a 17-week build keeps the retail table
        retail_like = names(self.seventeen, 17)
        self.assertEqual({k: retail_like[k] for k in range(16, 22)},
                         {16: "Week 16", 17: "Week 17", 18: "Wildcard Week", 19: "Division Championships",
                          20: "Conference Championships", 21: "Super Bowl"})

    # -- the primetime card's NEXT WEEK line -----------------------------------------------------------------------
    def test_primetime_next_week_says_playoffs_only_when_the_playoffs_are_next(self):
        def says_playoffs(xbe, weeks):
            return {row["last_played_index"]: row["next_week_text"] == "Playoffs"
                    for row in probe.probe_primetime_override(xbe, weeks) if row["stage"] == 8}
        old, new = says_playoffs(self.before, 18), says_playoffs(self.after, 18)
        self.assertEqual([k for k, v in old.items() if v], [16])           # one regular week still to play
        self.assertEqual([k for k, v in new.items() if v], [17])           # the last regular week was just played
        keep = says_playoffs(self.seventeen, 17)
        self.assertEqual([k for k, v in keep.items() if v], [16])          # 17-week league unchanged
        stage7 = [row for row in probe.probe_primetime_override(self.after, 18) if row["stage"] == 7]
        self.assertEqual(stage7[0]["next_week_text"], "Season Begins")

    # -- week-label audit (second pass) ----------------------------------------------------------------------------
    def test_menu_teaser_runs_one_line_per_picture_show_with_the_final_line_before_the_last_week(self):
        def lines(xbe, weeks):
            return {row["weeks_played"]: row["lines"] for row in probe.probe_teaser(xbe, weeks)}
        final = "Get a Look at the Final Playoff Picture."
        old, new = lines(self.before, 18), lines(self.after, 18)
        # v0.5: the final-picture line is offered after week 16, one week early; nothing after week 16
        self.assertIn(final, old[16])
        self.assertEqual(old[17], [])
        # repaired: the Picture airs after weeks 13..18, so teasers run after weeks 12..17; final line after week 17
        self.assertEqual([k for k, v in new.items() if v], [12, 13, 14, 15, 16, 17])
        self.assertIn(final, new[17])
        self.assertNotIn(final, " ".join(new[16]))
        for week in (14, 15, 16):
            self.assertIn(f"Who will clinch a playoff spot in Week {week + 1}?", new[week])
        for week in (12, 13, 14, 15):
            self.assertEqual(new[week], old[week])                  # the earlier teasers are byte for byte the same
        # a 17-week league keeps the retail teasers (final line after week 16)
        keep = lines(self.seventeen, 17)
        self.assertEqual([k for k, v in keep.items() if v], [12, 13, 14, 15, 16])
        self.assertIn(final, keep[16])

    def test_menu_teaser_dispatch_stays_inside_the_function_and_out_of_range_returns_cleanly(self):
        for weeks_played in (0, 5, 11, 18, 22, 40):
            emu = probe.Emu(self.after)
            probe.install_printf(emu)
            emu.hooks[probe.FN["last_played"]] = lambda lp=weeks_played - 1: emu.ret(lp)
            emu.hooks[probe.FN["rng"]] = lambda: emu.ret(1)
            emu.hooks[0x002CEB60] = lambda: emu.ret(1, pops=8)
            esp_before = probe.STACK_VA + 0x80000
            emu.call(0x002CF4B0, budget=100_000)
            self.assertEqual(emu.reg("esp"), esp_before + 4)       # balanced stack: back at the sentinel

    def test_idle_team_label_and_week_browser_header_name_the_right_round(self):
        def idle(xbe):
            return {row["row"]: row["label"] for row in probe.probe_idle_label(xbe, 18) if row["stage"] == 9}
        def header(xbe):
            return {row["row"]: row["header"] for row in probe.probe_week_header(xbe, 18)}
        want_idle = {17: "Bye Week", 18: "Wild Card Round", 19: "Division Championship Playoffs",
                     20: "Conference Championship Playoffs", 21: "Super Bowl"}
        want_header = {17: "Week N", 18: "Wildcard", 19: "Division Championship", 20: "Conference Championship",
                       21: "Super Bowl"}
        self.assertEqual({k: idle(self.after)[k] for k in want_idle}, want_idle)
        self.assertEqual({k: header(self.after)[k] for k in want_header}, want_header)
        # v0.5: Week 18 is a Wild Card round and the Super Bowl row reads Pro Bowl
        self.assertEqual(idle(self.before)[17], "Wild Card Round")
        self.assertEqual(idle(self.before)[21], "Pro Bowl")
        self.assertEqual(header(self.before)[17], "Wildcard")
        self.assertEqual(header(self.before)[21], "Pro Bowl")
        # 17-week league: retail tables
        self.assertEqual(idle(self.seventeen)[17], "Wild Card Round")
        self.assertEqual(header(self.seventeen)[20], "Super Bowl")


class ProbeToolTests(unittest.TestCase):
    def test_probe_decodes_mrks_widget_records_and_static_text(self):
        # one 0x90-byte text widget record: key, relative text pointer, class words, x/y at +0x50, then its text
        import struct
        record = bytearray(0x90)
        struct.pack_into("<I", record, 0, 0x11223344)
        struct.pack_into("<i", record, 4, 0x90 - 3)                  # target = off + 3 + rel = off + 0x90
        struct.pack_into("<II", record, 8, 0x005E13E0, 0x00683110)
        struct.pack_into("<2f", record, 0x50, 12.5, -3.0)
        raw = bytes(record) + "7.".encode("utf-16le") + b"\0\0" + bytes(0x90)
        widgets = probe.decode_mrks_widgets(raw)
        self.assertEqual(widgets[0]["key"], 0x11223344)
        self.assertEqual((widgets[0]["x"], widgets[0]["y"], widgets[0]["static"]), (12.5, -3.0, "7."))


if __name__ == "__main__":
    unittest.main()
