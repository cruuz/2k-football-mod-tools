"""b780-m64a: the 64 MB / 128 MB memory model (nfl2k5_memory_budget) is pinned to what was measured.

Measured (exact): EMU1 H1R2 and H1V8B (2026-11-03, the v0.9 RC and v0.8 discs at 128 MiB, Texans at Ravens, M&T Bank
afternoon clear), K1 k1b (2026-09-23, retail with the K128 stub, the 64 MB layout), MEM1's Unicorn room for DIR_INTRO,
the RC executable's own allocator layout and the allocator's legacy-layout limit. Modelled: everything at 64 MB.
The tests are pure Python; the one that reads the RC executable skips without it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_memory_budget as mb   # noqa: E402

RC_XBE = Path(os.environ.get("NFL2K5_B780_RC_XBE",
                             "/home/noah/2k-worktrees/.b77-scratch/b780/emu1/heapb/v09_default.xbe"))
# the RC executable's allocator owners (nfl2k5_xbe_space.layout), Career Home's on-demand section left out
RC_OWNERS = frozenset("""
history_screen player_progress_screen my_career roster_arena_growth pass_rush_stats star_career defensive_try_stats
scorebug_runtime champions coach_ai xbe_space_directory practice_squad_screen anniversary_kickoff era_rules my_career_m3
music_playlist momentum qb_spy calendar espn25_more_moments honors defensive_try standings_records deep_zone moment_venues
franchise_autosave cpu_money_downs stock_books weekly_prep k128 cpu_qb_reads abilities_runtime historic_teams_quick_game
audible_legend camera cpu_clock2 accelerated_clock moment_coaches formation_art_spacing hback_spill sim_realism
team_ratings_spill hair_styles franchise_edit_player boot_logo coverage_trail screen_hooks sim_rb_injuries
team_number_scale draft_clock weekly_progression play_art_routes clock_led draft_picks_spill coin_defer
human_tap_burst_spill qb_accuracy letter_grades cpu_money_downs_late decided_clock pass_protection protection_calls
classic_teams module_loader cpu_passer_iq db_ball_play sim_cb_tackles period_goalposts cpu_third_down return_coverage
ball_carrier_ai scramble_tuning run_blocking cpu_scrambles widescreen_menus force_out roster_storage zone_drop
team_logo_swap star_retention practice_injuries contract_college_guard coverage_slider letter_grades_progress
preseason_warning moment_context cpu_money_downs_late_state""".split())
V08_ONLY_OFF = ("history_screen", "standings_records", "audible_legend", "cpu_clock2", "protection_calls", "cpu_passer_iq")


def off(plan, *fields):
    out = dict(plan)
    for field in fields:
        out[field] = mb.OFF_VALUES.get(field, False)
    return out


class EngineAndMeasurementTests(unittest.TestCase):

    def test_engine_constants(self):
        self.assertEqual(mb.DIR_INTRO_BYTES, (73_680 + 128 + 127) & ~127)        # DIR_INTRO's charge in heap B
        self.assertEqual(mb.EARLY_ARENA_GAIN, 15_622_144)
        self.assertEqual(mb.SCALEOUT_V3, 200_704)
        self.assertEqual((mb.ROSTER_RETAIL, mb.ROSTER_CAPACITY), (594_048, 827_520))
        self.assertEqual(mb.ROSTER_CAPACITY - mb.ROSTER_RETAIL, 233_472)        # the capacity arena at 64 MB

    def test_the_rc_anchor_reproduces_emu1_h1r2_exactly(self):
        rc = mb.rc_plan()
        self.assertEqual(mb.xbe_resident(rc, 128), 15_896_576)                 # the RC's boot-loaded pages
        room, game = mb.room(rc, 128, "anchor")
        self.assertEqual((room, game["delta"]), (1_495_936, 0))
        got = mb.heaps(room, 14_176, capped=True)
        self.assertEqual((got["block"], got["left"], got["heap_a"] - 128, got["heap_b"]),
                         (1_364_864, 1_349_952, 1_343_360, 6_400))
        self.assertFalse(got["dir_intro_fits"])                                 # the NULL at 0x166745: the loop

    def test_mem1s_room_for_dir_intro(self):
        # MEM1 (Unicorn, the RC's own code): 1,563,392 B of room loads DIR_INTRO, 1,563,264 B does not
        self.assertTrue(mb.heaps(1_563_392, 14_176)["dir_intro_fits"])
        self.assertFalse(mb.heaps(1_563_392 - 128, 14_176)["dir_intro_fits"])
        self.assertEqual(mb.needed_room(14_176, 0), 1_563_328)

    def test_v08_reproduces_emu1_h1v8b(self):
        v08 = off(mb.rc_plan(), *V08_ONLY_OFF)
        self.assertEqual(mb.xbe_resident(v08, 128), 15_835_136)                # 15 pages fewer, as measured
        room, _ = mb.room(v08, 128, "anchor")
        self.assertEqual(room - 1_555_456, 1_920)                               # MEM1's 1,920 B of other main-heap use
        got = mb.heaps(1_555_456, 13_856, capped=True)
        self.assertEqual((got["block"], got["heap_b"]), (1_424_384, 66_304))

    def test_retail_k1_lab_heaps(self):
        got = mb.heaps(mb.RETAIL["room"], mb.RETAIL["export"])
        self.assertEqual((got["block"], got["left"], got["heap_b"]), (2_115_456, 0x17C690, 214_656))

    def test_the_retail_gap_is_the_documented_unattributed_use(self):
        retail = {"roster_capacity": False}
        room, _ = mb.room(retail, 64, "anchor")                                 # retail's executable and resources
        room += mb.OUTER_TOP_GROWTH + mb.venue_charge(retail, "s02")            # retail's outer table, then s16
        for s16, gap in ((2_715_776, mb.UNATTRIBUTED_RC[0]), (2_731_008, mb.UNATTRIBUTED_RC[1])):
            self.assertEqual(room - s16 + gap, mb.RETAIL["room"])

    def test_the_rc_plan_installs_exactly_the_rc_owners(self):
        self.assertEqual(set(mb.owners(mb.rc_plan())), RC_OWNERS)

    @unittest.skipUnless(RC_XBE.is_file(), "needs the v0.9 RC default.xbe (NFL2K5_B780_RC_XBE)")
    def test_owner_bytes_are_the_rc_executables(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        payload = RC_XBE.read_bytes()
        pool = (0x150B000, 0x150B000 + 0x12000)
        got = {}
        for a in space.layout(payload)["allocations"]:
            owner = a["owner"][7:]
            if owner == "my_career_home":
                continue
            where = "pool" if pool[0] <= a["va"] < pool[1] else "v3"
            row = got.setdefault(owner, [0, 0, 0, 0, 0])
            row[{"code": 0, "read_only": 2, "data": 4}[a["kind"]] + (where == "pool" and a["kind"] != "data")] += a["size"]
        got["xbe_space_directory"][3] -= mb.POOL_DOC                            # the pool's directory page
        self.assertEqual({o: tuple(v) for o, v in got.items()}, {o: mb.OWNER_BYTES[o] for o in got})
        base, count, table = (struct.unpack_from("<I", payload, o)[0] for o in (0x104, 0x11C, 0x120))
        resident = 0
        for i in range(count):
            flags, va, vsize = struct.unpack_from("<3I", payload, table - base + i * 0x38)
            if flags & 2:
                resident += ((va + vsize + 0xFFF) & ~0xFFF) - (va & ~0xFFF)
        self.assertEqual(resident, mb.ANCHOR["resident"])


class AllocatorLayoutTests(unittest.TestCase):
    """The legacy layout (two pages) against nfl2k5_xbe_space.apply on the retail XBE (measured, 2026-11-03)."""

    def resident(self, owners):
        return mb._legacy_pages(owners)

    def test_seven_small_requests_fit_two_pages_and_the_eighth_takes_the_scale_out(self):
        seven = ["contract_college_guard", "qb_accuracy", "run_blocking", "pass_protection", "return_coverage",
                 "ball_carrier_ai", "practice_injuries"]
        self.assertEqual(self.resident(seven), 8_192)
        self.assertEqual(self.resident(seven + ["star_retention"]), 0)
        abilities = ["contract_college_guard", "abilities_runtime", "human_tap_burst_spill", "qb_accuracy",
                     "pass_protection", "run_blocking", "ball_carrier_ai"]
        self.assertEqual(self.resident(abilities), 8_192)
        self.assertEqual(self.resident(abilities + ["return_coverage"]), 0)
        self.assertEqual(self.resident(["my_career"]), 0)                      # a big owner needs the scale-out

    def test_the_third_page_compresses_the_directory_and_holds_more(self):
        # all measured with the allocator: a read-only request, a beta-62 owner mixed with newer ones, or a page
        # overflow from straddling takes the scale-out
        seven = ["contract_college_guard", "widescreen_menus", "preseason_warning", "qb_accuracy", "pass_protection",
                 "run_blocking", "ball_carrier_ai"]
        self.assertEqual(self.resident(seven), 8_192)
        self.assertEqual(self.resident(seven + ["calendar"]), 0)                # read-only
        self.assertEqual(self.resident(seven + ["zone_drop"]), 0)               # a beta-62 owner
        more = seven + ["abilities_runtime", "human_tap_burst_spill", "cpu_qb_reads"]
        self.assertEqual(self.resident(more), 12_288)
        self.assertEqual(self.resident(more + ["cpu_money_downs", "cpu_money_downs_late", "cpu_money_downs_late_state",
                                               "cpu_third_down"]), 0)        # the code no longer packs into two pages

    def test_the_profiles_owners(self):
        plan = mb.profile_64_plan()
        self.assertEqual(sorted(o for o in mb.owners(plan) if o not in mb.INFRASTRUCTURE),
                         ["abilities_runtime", "ball_carrier_ai", "contract_college_guard", "coverage_slider",
                          "cpu_passer_iq", "cpu_qb_reads", "db_ball_play", "draft_clock", "force_out",
                          "human_tap_burst_spill", "pass_protection", "practice_injuries", "preseason_warning",
                          "protection_calls", "qb_accuracy", "return_coverage", "run_blocking", "scramble_tuning",
                          "sim_cb_tackles", "star_retention", "weekly_progression", "widescreen_menus"])
        self.assertEqual(mb.xbe_resident(plan, 64) - mb.RETAIL_RESIDENT, 12_288)   # 25 requests, MEASURED
        self.assertEqual(mb.xbe_resident(dict(plan, all_stadiums=True), 64) - mb.RETAIL_RESIDENT, 212_992)
        self.assertEqual(mb.xbe_resident(dict(plan, screen_hooks=True), 64) - mb.RETAIL_RESIDENT, 212_992)

    def test_scale_out_fields_and_the_roster_edits_xbe_sections_take_the_scale_out(self):
        plan = mb.profile_64_plan()
        for extra in ({"camera": True}, {"roster_draft_pick_ownership": True}, {"roster_hback_roles": True},
                      {"team_ratings": True}):
            with self.subTest(extra=extra):
                self.assertEqual(mb.xbe_resident(dict(plan, **extra), 64) - mb.RETAIL_RESIDENT, 212_992)


class TargetTests(unittest.TestCase):

    def test_128_mb_with_the_early_form_reaches_the_cap(self):
        early = dict(mb.rc_plan(), k128_early=True)
        got = mb.predict(early, 128)
        self.assertTrue(got["fits"], got)
        self.assertEqual(got["block"], 0x180000)
        self.assertGreaterEqual(got["heap_b"], 213_888)                        # retail's 214,656 less the export margin
        shipped = mb.predict(mb.rc_plan(), 128)
        self.assertFalse(shipped["fits"])
        self.assertEqual(shipped["heap_b"], 0)                                  # the hardest game is worse than BAL's

    def test_64_mb_forces_off_the_128_mb_options_and_the_rc_does_not_fit(self):
        got = mb.predict(None, 64)
        self.assertEqual(got["forced_off"], ["k128_memory", "k128_roster_heap", "roster_capacity"])
        self.assertFalse(got["fits"])
        self.assertEqual((got["room"], got["over_bytes"]), (736_384, 892_992))
        self.assertEqual(got["hardest"], "NRG Stadium (s37)")
        self.assertEqual((got["matchup"]["home_kit"], got["matchup"]["away_kit"], got["matchup"]["delta"]),
                         ("37h0", "02a1", 177_792))
        self.assertEqual(set(mb.REQUIRES_128) >= {"k128_memory", "k128_roster_heap", "k128_early", "roster_capacity",
                                                  "reserves_16", "created_teams_extra", "guardian_overlay"}, True)
        with self.assertRaises(ValueError):
            mb.predict(None, 96)

    def test_the_recommended_64_mb_profile(self):
        profile = mb.recommended_64_profile()
        for field in ("k128_memory", "k128_roster_heap", "scorebug", "scorebug_runtime", "hair_styles", "my_career",
                      "history_screen", "depth_chart_rows", "camera"):
            self.assertIn(field, profile)
        self.assertFalse(set(profile) & mb.PSEUDO_FIELDS)
        self.assertFalse(set(profile) & set(mb.PROFILE_64_PATCHES))
        got = mb.predict(mb.profile_64_plan(), 64)
        self.assertEqual(got["forced_off"], [])
        # b780 m64kits: the profile turns ESPN Anniversary more moments off, so the build never composes the Ravens era kit
        # (its donor is a historic spare style): BAL style 1 keeps its retail size and every kit at every venue fits
        # (it was 1,572,096 / 82,048 / 8,192 and 57,280 B over with the composed kit counted).
        self.assertEqual((got["room"], got["heap_b"], got["margin"]), (1_661_056, 171_008, 97_152))
        self.assertTrue(got["fits"])
        self.assertEqual((got["over_bytes"], got["spare_bytes"]), (0, got["room"] - got["needed_room"]))
        self.assertGreaterEqual(got["margin"], mb.SAFETY_MARGIN)
        primary = got["primary_uniforms"]
        self.assertEqual((primary["heap_b"], primary["margin"]), (200_960, 127_104))
        self.assertGreaterEqual(primary["margin"], mb.SAFETY_MARGIN)        # every game in style 0 kits fits

    def test_the_profile_with_the_pack_roster_edits_takes_the_scale_out(self):
        plan = mb.profile_64_plan(roster_ready=False)       # the v0.9 pack: capacity and both XBE sections
        got = mb.predict(plan, 64)
        self.assertEqual(got["forced_off"], ["roster_capacity"])
        self.assertEqual(mb.xbe_resident(off(plan, "roster_capacity"), 64) - mb.RETAIL_RESIDENT, 212_992)


class ApiTests(unittest.TestCase):

    def test_predict_shape(self):
        got = mb.predict(mb.rc_plan(), 64)
        for key, kind in (("fits", bool), ("spare_bytes", int), ("over_bytes", int), ("hardest", str),
                          ("suggestions", list), ("forced_off", list), ("notes", list)):
            self.assertIsInstance(got[key], kind, key)
        self.assertTrue(all(isinstance(f, str) and isinstance(n, int) for f, n in got["suggestions"]))
        self.assertEqual(got["suggestions"][0], ("scorebug", 404_224))        # the sprite scorebug and its fonts
        self.assertIn(("scorebug_runtime", 0), got["suggestions"])           # rides with it

    def test_option_costs(self):
        costs = mb.option_costs()
        self.assertTrue(all(isinstance(k, str) and type(v) is int and v > 0 for k, v in costs.items()))
        self.assertEqual((costs["scorebug"], costs["hair_styles"], costs["depth_chart_rows"]),
                         (404_224, 84_736, 81_920))
        self.assertEqual(list(costs), sorted(costs, key=lambda k: -costs[k]))

    def test_plan_forms(self):
        from mod_editor.core import mod_build
        plan = mod_build.BuildPlan(Path("in.iso"), Path("out.iso"))
        self.assertEqual(mb.xbe_resident(mb.options(plan), 64), mb.RETAIL_RESIDENT)   # the default plan: retail
        recipe = {"preset": "softdrink_basic", "overrides": {"qb_accuracy": True}}
        self.assertTrue(mb.on(mb.options(recipe), "qb_accuracy"))
        self.assertTrue(mb.on(mb.options(recipe), "contract_college_guard"))          # from the Basic preset
        self.assertIsInstance(mb.predict(recipe, 64)["fits"], bool)

    def test_roster_edits_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edits.json"
            path.write_text(json.dumps({"free_agent_capacity": {"records": 612}, "draft_pick_ownership": {},
                                        "hback_roles": {}}))
            self.assertEqual(mb.roster_edits_summary(path),
                             {"capacity_records": 612, "draft_pick_ownership": True, "hback_roles": True})
            opts = mb.options({"roster_edits": str(path)})
            self.assertTrue(opts["roster_capacity"] and opts["roster_hback_roles"])
            self.assertEqual(mb.forced_off(opts, 64), ["roster_capacity"])
            path.write_text(json.dumps({"edits": []}))
            self.assertEqual(mb.roster_capacity_records(path), 0)
        self.assertEqual(mb.roster_capacity_records(None), 0)


if __name__ == "__main__":
    unittest.main()
