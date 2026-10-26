"""b778 bd3: the blockers that stopped the full SOFTDRINK 2K28 release build (PB38, PB39, PB85).

Each class pins one fix; each fails on job/b778-int5 (f20cb274c) without it. The allocator tests run on the
pinned retail default.xbe and skip without it; the others need no game data.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

# The executable options of the SOFTDRINK release recipe (recipe_rc.json through mod_build, with every option the
# build derives from a disc image on): the request set that hit both allocator refusals.
RELEASE_SPACE_OPTIONS = dict(
    runtime=True, momentum=50, defensive_try=True, zone_drop_cap=True, all_stadiums=True, coverage_slider=True,
    scramble_tuning=True, music_shuffle=True, practice_squad_screen=True, abilities=True, qb_spy=True,
    calendar_engine=True, momentum_collisions=True, momentum_collision_level=50, my_career=True, screen_hooks=True,
    franchise_autosave=True, coverage_trail=True, franchise_edit_player=True, cpu_money_downs="modern2",
    accelerated_clock=True, weekly_prep=True, coach_ai=True, deep_zone_facing=True, deep_zone_bail=True,
    coin_defer=True, decided_clock=True, cpu_scrambles="modern", historic_teams_quick_game=True,
    espn25_more_moments=True, espn25_named_previews=True, historic_stock_books=True, espn25_era_rules=True,
    anniversary_kickoff=True, widescreen_menus=True, team_logo_swap=True, period_goalposts=True, k128_memory=True,
    k128_roster_heap=True, letter_grades=True, honors_page=True, my_career_home=True, roster_capacity=True,
    camera=True)
RELEASE_LATE_OWNERS = dict(
    hair_styles=True, cpu_qb_reads=True, db_ball_play=True, play_art_routes=True, team_number_scale=True,
    run_blocking=True, pass_protection=True, return_coverage=True, qb_accuracy=True, modern_force_out=True,
    practice_injuries=True, cpu_ball_carriers=True, star_retention=True, star_career=True,
    franchise_draft_clock=True, weekly_progression=True, player_progress=True, contract_college_guard=True,
    sim_cb_tackles=True, modern_clock_led=True, module_loader=True, classic_teams=True)


def _retail():
    from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
    return retail_xbe()


class DefensiveTryAdapterTests(unittest.TestCase):
    """bf1 blocker 1: "allocation requests differ; rebuild from base" in the late executable stage."""

    def test_late_stage_with_defensive_try_replays_the_early_late_owner_allocation(self):
        retail = _retail()
        late = dict(defensive_try=True, hair_styles=True, modern_clock_led=True, module_loader=True,
                    player_progress=True, roster_capacity=True, k128_memory=True, k128_roster_heap=True)
        early = tt._selected_space_requests(**late)
        self.assertTrue(any(r[0] == "nfl2k5_hair_styles" for r in early))
        installed, _ = space.apply(retail, early)
        patched, receipt = tt._apply_all(installed, None, catch_slider=False, arc_table=False, xbe_space=True, **late)
        self.assertEqual(space._read_scale_directory(patched), space._requests(early))
        self.assertEqual(space.status(patched), "applied")
        self.assertEqual(tt.defensive_try_patch.status(patched), "applied")


class DirectorySlotConversionTests(unittest.TestCase):
    """bf1 blockers 2 and 3: the release build appends the team-ratings spill (two named directory slots) to a
    103-owner v3 image whose sealed directory document reaches into the new slots."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_draft_picks as draft_picks, nfl2k5_hback as hback
        from mod_editor.core import nfl2k5_team_ratings as team_ratings
        retail = _retail()
        cls.early = tt._selected_space_requests(**RELEASE_SPACE_OPTIONS, **RELEASE_LATE_OWNERS)
        installed, _ = space.apply(retail, cls.early, scaleout=True)
        cls.v3 = installed
        payload, _ = space.extend_scaleout(installed, draft_picks.REQUESTS)
        payload, _ = space.extend_scaleout(payload, hback.REQUESTS)
        cls.before_ratings = payload
        cls.ratings = team_ratings.REQUESTS

    def test_the_old_document_reaches_into_the_new_slots(self):
        self.assertEqual(space.scale_version(self.before_ratings), 3)
        end = space.SCALE_DIRECTORY + space._directory_document_size(self.before_ratings)
        wanted = space._requests(list(space._read_scale_directory(self.before_ratings)) + list(self.ratings))
        slots = [r for r in space._directory_code_rows(wanted) if r["owner"] == "nfl2k5_team_ratings_spill"]
        self.assertTrue(any(r["raw"] < end for r in slots), "the fixture must reproduce the release overlap")
        self.assertFalse(space._v3_directory_fits(wanted))

    def test_appending_the_team_ratings_spill_converts_to_v4_and_moves_nothing(self):
        before = space._scale_allocations(space._read_scale_directory(self.before_ratings))
        grown, receipt = space.extend_scaleout(self.before_ratings, self.ratings)
        self.assertEqual(space.scale_version(grown), 4)
        self.assertEqual(space.status(grown), "applied")
        self.assertEqual(receipt["directory_tail_reassigned_bytes"], 912)
        after = space._scale_allocations(space._read_scale_directory(grown))
        for row in before:
            if row["owner"] != space.DIRECTORY_OWNER:
                self.assertIn(row, after)
        for row in after:
            if row["owner"] == "nfl2k5_team_ratings_spill":
                content = grown[row["raw"]:row["raw"] + row["size"]]
                self.assertEqual(content, (b"\xcc" if row["kind"] == "code" else b"\0") * row["size"])

    def test_the_moments_still_append_after_the_conversion(self):
        from mod_editor.core import nfl2k5_moment_coaches as coaches, nfl2k5_moment_context as context
        grown, _ = space.extend_scaleout(self.before_ratings, self.ratings)
        have = {(o, k) for o, k, _s, _a in space._requests(self.early)}
        for module in (coaches, context):
            rows = [r for r in module.REQUESTS if (r[0], r[1]) not in have]
            if rows:
                grown, _ = space.extend_scaleout(grown, rows)
        self.assertEqual(space.scale_version(grown), 4)
        self.assertEqual(space.status(grown), "applied")


class MomentKitsFillerTests(unittest.TestCase):
    """bf1 blocker 4: the classic teams' authored kits are a second moment-kits install; its zero filler took the
    first install's name and rewrite_plan refused it as existing."""

    def _appended(self, present):
        from mod_editor.core import nfl2k5_moment_kits as mk
        from mod_editor.core import nfl2k5_historic_styles as hs

        class Target:
            def has(self, name):
                return name in present

            def outer(self, name=None, *, identity=None):
                return 1

        inputs = dict(new_present={}, members={}, files={}, situ=b"situ", packages={})
        with mock.patch.object(mk, "expected", return_value=({"zz_new_kit.iff": b"k" * 100}, {}, {}, b"situ")), \
                mock.patch.object(hs, "AGGREGATES", ()), mock.patch.object(mk, "pins", side_effect=OSError):
            _edits, appended, _receipt = mk.compile_edits(Target(), dict(selections=[]), inputs)
        return [name for name, _data in appended]

    def test_first_install_keeps_the_original_filler_name(self):
        from mod_editor.core import nfl2k5_moment_kits as mk
        self.assertEqual(self._appended(set()), ["zz_new_kit.iff", mk.FILLER])

    def test_a_second_install_takes_the_next_free_filler_name(self):
        from mod_editor.core import nfl2k5_moment_kits as mk
        stem = mk.FILLER[:-len(".bin")]
        self.assertEqual(self._appended({mk.FILLER})[-1], f"{stem}_2.bin")
        self.assertEqual(self._appended({mk.FILLER, f"{stem}_2.bin"})[-1], f"{stem}_3.bin")


class ClassicTeamsRosterOuterTests(unittest.TestCase):
    """bf1 blocker 5: the classic teams keyed the main roster edit by its name id, not its outer index."""

    def test_the_roster_edit_is_keyed_by_the_roster_outer_index(self):
        from mod_editor.core import nfl2k5_classic_teams as ct
        from mod_editor.core import nfl2k5_historic_styles as hs
        entries = [types.SimpleNamespace(name_id=0x1000 + i, table_index=i) for i in range(9)]
        entries[5] = types.SimpleNamespace(name_id=hs.ROSTER_OUTER_ID, table_index=5)

        class Disc:
            def __init__(self, *_a, **_k):
                self.archive_entries = entries

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        captured = {}

        def rewrite(path, edits, appended, **_kw):
            captured.update(edits=dict(edits), appended=list(appended))
            return {}

        data = types.SimpleNamespace(teams={})
        with mock.patch.object(ct, "image_status", side_effect=["retail", "applied"]), \
                mock.patch("mod_editor.core.nfl2k5_espn25_rosters.read_xbe", return_value=b"xbe"), \
                mock.patch("mod_editor.core.nfl2k5_historic_teams_quick_game.status", return_value="applied"), \
                mock.patch("mod_editor.core.nfl2k5_historic_teams_quick_game.season_routing_status", return_value=False), \
                mock.patch.object(ct, "xbe_status", return_value="retail"), \
                mock.patch.object(ct, "install_authored_kits", return_value={}), \
                mock.patch("mod_editor.core.nfl2k5_classic_field.edits", return_value=({7: b"field"}, {})), \
                mock.patch.object(ct, "_inputs", return_value=(b"main", {}, {}, None, set())), \
                mock.patch.object(ct, "label_holder", return_value=b"holder"), \
                mock.patch.object(ct, "compile_files", return_value=([("h-x.iff", b"abc")], {})), \
                mock.patch("mod_editor.core.nfl2k5_position_pools.status", return_value="retail"), \
                mock.patch.object(ct, "rows_for", return_value=[]), \
                mock.patch.object(ct, "apply_xbe", return_value=(b"xbe2", {})), \
                mock.patch("mod_editor.core.nfl2k5_music_archive.Disc", Disc), \
                mock.patch.object(hs, "rewrite_archive", side_effect=rewrite), \
                mock.patch("mod_editor.core.nfl2k5_historic_rosters.write_xbe"), \
                mock.patch.object(ct.classic_face, "patch_image", return_value={}):
            result = ct.apply_to_image("unused.xiso.iso", "retail.xiso.iso", data)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(captured["edits"], {5: b"holder", 7: b"field"})
        self.assertTrue(all(0 <= index < len(entries) for index in captured["edits"]))


class WeatherCapacityRosterTests(unittest.TestCase):
    """bf1 blocker 6: the saved climate edits read the main ROST after the capacity arena grew it to version 18."""

    def test_the_grown_version_18_roster_reads_and_takes_the_climate_edits(self):
        from mod_editor.core import nfl2k5_weather as w
        from mod_editor.core import nfl2k5_roster_arena as arena
        retail = Path(__import__("os").environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) \
            / "ESPN NFL 2K5 (USA)" / "vc_53450030"
        if not (retail / "0").is_file():
            self.skipTest("USA retail vc_53450030 is absent; set NFL2K5_RETAIL_EXTRACTION")
        data = w.load_resource(retail)
        grown, receipt = arena.migrate(data, reserves_16=False, capacity_records=612)
        self.assertEqual(struct.unpack_from("<I", grown, 0x30)[0], arena.DISC_VERSION)
        self.assertNotEqual(len(grown), len(data))
        before = w.inspect_resource(data)["rows"]
        after = w.inspect_resource(grown)["rows"]
        strip = lambda rows: [{k: v for k, v in r.items() if k != "offset"} for r in rows]  # noqa: E731
        self.assertEqual(strip(after), strip(before))
        plan = w.less_rain_plan(data)
        self.assertTrue(plan["changes"])
        edited, _ = w.apply(grown, plan)
        w.verify(edited, plan, before=grown)
        self.assertEqual(len(edited), len(grown))
        self.assertEqual(struct.unpack_from("<I", edited, 0x30)[0], arena.DISC_VERSION)


class ColourExclusionTests(unittest.TestCase):
    """bf1 blockers 7 and 8: the classic field on s48 is authored before the colour grade."""

    @staticmethod
    def _pin(name, outer, data, applied):
        import hashlib
        sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
        return dict(name=name, outer=outer, name_id=100 + outer, size=len(data), retail_sha256=sha(data),
                    applied_sha256=sha(applied),
                    sites=[dict(kind="field", offset=0, size=len(data), retail=sha(data), applied=sha(applied))])

    def setUp(self):
        from mod_editor.core import nfl2k5_modern_color as mc
        self.mc = mc
        self.retail = {1: bytes(range(64)), 2: bytes(range(64, 128))}
        graded = bytes(b ^ 1 for b in self.retail[1])
        self.pins = dict(mc._pins(), bundles=[self._pin("s01dd.iff", 1, self.retail[1], graded),
                                  self._pin("s48dd.iff", 2, self.retail[2], bytes(b ^ 2 for b in self.retail[2]))])
        self.disc = dict(self.retail)
        self.disc[2] = bytes(b ^ 0x55 for b in self.retail[2])          # the classic field's own paint

        disc = self.disc

        class Entry:
            def __init__(self, outer):
                self.name_id, self.size, self.virtual_offset = 100 + outer, 64, outer * 1000

        class Archive:
            entries = {1: Entry(1), 2: Entry(2)}

            def read(self, at, size):
                return disc[at // 1000][:size]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        self.patches = [mock.patch.object(mc, "_pins", return_value=self.pins),
                        mock.patch.object(mc, "_outer_image", return_value=lambda _source: Archive())]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_without_the_scope_the_classic_field_is_not_recognized(self):
        self.assertEqual(self.mc.image_status("disc", receipt=None), "foreign")
        with self.assertRaisesRegex(self.mc.ModernColorError, "not recognized"):
            self.mc.check_image_request("disc", None, receipt=None)

    def test_the_excluded_bundle_is_left_out_of_the_retail_check(self):
        self.assertEqual(self.mc.image_status("disc", receipt=None, exclude=["s48dd.iff"]), "retail")
        self.assertEqual(self.mc.check_image_request("disc", None, receipt=None, exclude=["s48dd.iff"]), "retail")
        with self.assertRaisesRegex(self.mc.ModernColorError, "Unknown colour bundle exclusion"):
            self.mc.image_status("disc", receipt=None, exclude=["s99dd.iff"])

    def _receipt(self, scope):
        import hashlib
        from copy import deepcopy
        mc = self.mc
        settings = mc.normalize_settings(None)
        rows = {p["name"]: deepcopy(p) for p in self.pins["bundles"]}
        current = self.disc[2]
        rows["s48dd.iff"]["applied_sha256"] = hashlib.sha256(current).hexdigest()
        rows["s48dd.iff"]["sites"][0]["applied"] = hashlib.sha256(current).hexdigest()
        self.disc[1] = bytes(b ^ 1 for b in self.retail[1])               # the graded bundle
        return dict(schema=mc.RECEIPT_SCHEMA, settings=settings, settings_sha256=mc.settings_id(settings),
                    state="applied", bundle_pins=rows, excluded_bundles=list(scope))

    def test_a_scoped_receipt_pins_the_excluded_bundle_at_its_current_bytes(self):
        receipt = self._receipt(["s48dd.iff"])
        self.assertEqual(self.mc.image_status("disc", receipt=receipt), "applied")
        self.disc[2] = self.retail[2]                                    # the classic field lost
        self.assertEqual(self.mc.image_status("disc", receipt=receipt), "foreign")

    def test_a_caller_must_agree_with_the_receipt_scope(self):
        receipt = self._receipt(["s48dd.iff"])
        with self.assertRaisesRegex(self.mc.ModernColorError, "different bundle scope"):
            self.mc.image_status("disc", receipt=receipt, exclude=())
        self.assertEqual(self.mc.image_status("disc", receipt=receipt, exclude=["s48dd.iff"]), "applied")


class HistoricSpareKeepTests(unittest.TestCase):
    """The build's last read-back refused the historic team styles after the team-coloured sleeves rewrote the
    Eagles' spare (the retail era-9 package holding the retail style-0 art); the build now keeps it."""

    RELEASED = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 (2026-10-20).xiso.iso")
    RETAIL = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")

    def test_the_eagles_era_9_spare_is_named_for_the_sleeves_pass(self):
        if not (self.RELEASED.is_file() and self.RETAIL.is_file()):
            self.skipTest("private released and retail discs are absent")
        from mod_editor.core import nfl2k5_historic_styles as hs
        self.assertEqual(hs.image_status(self.RELEASED, self.RETAIL), "applied")
        kept = hs.retail_spare_selectors(self.RELEASED, self.RETAIL)
        self.assertIn("21H9", kept)
        self.assertIn("21A9", kept)
        self.assertEqual(hs.retail_spare_selectors(self.RETAIL, self.RETAIL), ())

    def test_the_build_passes_them_to_the_sleeves_pass(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = source.index("sleeves.apply_to_image(target, keep=keep)")
        self.assertIn("retail_spare_selectors(", source[at - 800:at])


class StarCareerWithMyCareerTests(unittest.TestCase):
    """The release build's tail: after the star-career owner was installed, MyCareer (and with it Career Home,
    Franchise Practice and Auto Save) read foreign, so the Player Progress screen refused its prerequisites. Its
    class-loop hooks sit in a MyCareer guard (0x2BE923..) and over the legacy "generation" jump at 0x2BE946."""

    def test_my_career_still_reads_applied_after_the_star_career_owner(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career as career
        from mod_editor.core import nfl2k5_star_career as star
        payload, _ = mode.apply(_retail())
        self.assertEqual(mode.status(payload), "applied")
        both, receipt = star.apply(payload)
        self.assertEqual(star.status(both), "applied")
        self.assertNotEqual(both, payload)
        self.assertEqual(mode.status(both), "applied")
        self.assertEqual(career.status(both), "applied")
        # only that owner's exact hook is accepted: a different jump there is still foreign
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        broken = repin_edit(both, 0x2BE946, b"\xcc")
        self.assertEqual(mode.status(broken), "foreign")
        self.assertEqual(XbeImage(both).read(0x2BE946, 5), b"\x90" * 5)


class PlayerProgressWithEconomyTests(unittest.TestCase):
    """The franchise economy (revision 3) hooks the stage getter call at 0x248628, inside the Player Progress
    owner's next-season guard; the screen refused it as a foreign prerequisite."""

    def test_player_progress_installs_beside_the_franchise_economy(self):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        from mod_editor.core import nfl2k5_player_progress_screen as screen
        with_economy, _ = economy.apply(_retail())
        self.assertEqual(economy.status(with_economy), "applied")
        self.assertEqual(screen.status(with_economy), "retail")
        applied, receipt = screen.apply(with_economy)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(screen.status(applied), "applied")
        self.assertEqual(economy.status(applied), "applied")

    def test_any_other_bytes_at_the_economy_site_are_still_foreign(self):
        from mod_editor.core import nfl2k5_player_progress_screen as screen
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        retail = _retail()
        self.assertEqual(screen.status(retail), "retail")
        # the economy's call bytes without the economy installed
        from mod_editor.core import nfl2k5_franchise_economy as economy
        site = next(s for s in economy.sites() if s.va == economy.AFTER_STAGE)
        self.assertEqual(screen.status(repin_edit(retail, site.va, site.patched)), "foreign")


class PlayerProgressBesideMyCareerTests(unittest.TestCase):
    """The release build's tail: the Player Progress screen chains its franchise footer hooks over MyCareer's
    inline ones (and hooks native routines MyCareer's guards hash), after which MyCareer, Career Home and Auto Save
    read foreign and the module loader refused ("the module loader needs Career Home")."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_franchise_autosave as autosave
        from mod_editor.core import nfl2k5_player_progress_screen as screen
        requests = tt._selected_space_requests(my_career=True, franchise_autosave=True, player_progress=True)
        payload, _ = space.apply(_retail(), requests, scaleout=True)
        payload, _ = mode.apply(payload)
        cls.before, _ = autosave.apply(payload)
        cls.after, cls.receipt = screen.apply(cls.before)

    def test_every_owner_reads_applied_after_the_screen(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career as career
        from mod_editor.core import nfl2k5_franchise_autosave as autosave
        from mod_editor.core import nfl2k5_player_progress_screen as screen
        self.assertEqual(self.receipt["status"], "applied")
        self.assertEqual(screen.status(self.after), "applied")
        self.assertEqual(mode.status(self.after), "applied")
        self.assertEqual(career.status(self.after), "applied")
        self.assertEqual(autosave.status(self.after), "applied")
        chained = screen.chained_footer_sites(self.after)
        self.assertEqual(len(chained), 4)
        self.assertEqual(sum(target is not None for _bytes, target in chained.values()), 3)

    def test_a_changed_footer_hook_is_still_foreign(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode
        from mod_editor.core import nfl2k5_player_progress_screen as screen
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        broken = repin_edit(self.after, screen.SITE_SAVE_FRONT_OFFICE[0], b"\x90" * 5)
        self.assertEqual(screen.chained_footer_sites(broken), {})
        self.assertEqual(mode.status(broken), "foreign")


if __name__ == "__main__":
    unittest.main()
