"""b780 b10-profile: the game's own code reads what Studio writes (Unicorn replays of the pinned USA retail executable).

* The options loader ``FUN_000E2E20`` (the one routine every Settings and franchise load goes through) copies a
  Studio-edited 0x2E0-byte block over the live options; the live Quarter Length, Sim. Quarter Length and Chop Block then read
  the new values, on the retail executable and on one carrying the new defaults.
* The champions page (the honors owner's third Player Card page, ``tools/nfl2k5_champions/runtime.c``) draws the seasons that
  Franchise > Upgrade merged into a save's history block, and the game's own Super Bowl recorder extends that block.
* The game's own arena load and save on a real v0.7 franchise, then Upgrade's in-place fill (the "Upgrade before the first
  save" trap), and the game's own MyCareer staging (``inline_stage``) on the block Upgrade writes after an arena change.

Boundaries: Unicorn runs the real routines on synthetic RAM (no boot, renderer or save device), so these are not in-game
results.  The tests skip without the private pinned retail ``default.xbe``.  Run them through the machine-wide test slot.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_champions_history as history  # noqa: E402
from mod_editor.core import nfl2k5_option_defaults as defaults  # noqa: E402
from mod_editor.core import nfl2k5_profile_defaults as profile  # noqa: E402
from tests.mod_editor import test_b779_hn1_champions as hn1  # noqa: E402
from tests.mod_editor.test_b780_b10_profile_defaults import NEW, settings_save  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC  # noqa: E402

BLOCK, BLOCK_SIZE = 0xE5FF80, 0x2E0
QUARTER, SIM, CHOP = 0xE6000C, 0xE60010, 0xE60064
REAL_SETTINGS = Path(os.environ.get("B780_B10_SETTINGS", ""))
REAL_FRANCHISE = Path(os.environ.get("B780_B10_V07", ""))


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail
    return _retail()


@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class OptionsLoaderTests(unittest.TestCase):
    """A saved profile wins over any default; Studio's edit is therefore what the game plays with."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched = defaults.apply(cls.retail)[0]

    def load(self, xbe, stored):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(xbe, trace_writes=False)
        m.call(0x77D20, budget=2_000_000, stop=0x77D45)               # the boot initializer: a fresh profile's defaults
        buffer = m.ARENA + 0x1000
        m.uc.mem_write(buffer, bytes(stored))
        m.call(0xE2E20, ecx=buffer)                                    # FUN_000E2E20: the options loader every save load uses
        return m, bytes(m.uc.mem_read(BLOCK, BLOCK_SIZE))

    def test_a_studio_edited_settings_save_loads_as_7_15_on(self):
        old = settings_save()                                          # 5 / 5 / Off, a profile saved before the new defaults
        new, rows = profile.edit(old, profile.values_from_plan(profile.plan(old, NEW)))
        self.assertEqual(len(rows), 3)
        for label, xbe in (("retail executable", self.retail), ("executable with the new defaults", self.patched)):
            with self.subTest(label):
                m, _live = self.load(xbe, old)
                self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (5, 5, 0))   # the old save still plays 5 / 5 / Off
                m, live = self.load(xbe, new)
                self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (7, 15, 1))
                self.assertEqual(live, new)                            # the loader copied all 0x2E0 bytes of the edited block

    def test_a_player_choice_survives_the_edit_and_the_loader(self):
        old = settings_save(10, 5, 0)
        new, _rows = profile.edit(old, profile.values_from_plan(profile.plan(old, NEW)))
        m, live = self.load(self.patched, new)
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (10, 15, 1))
        self.assertEqual(live, new)

    def test_only_the_three_dwords_differ_in_the_live_block(self):
        old = settings_save()
        new, _rows = profile.edit(old, {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        _m, before = self.load(self.retail, old)
        _m, after = self.load(self.retail, new)
        changed = {BLOCK + i for i in range(0, BLOCK_SIZE, 4) if before[i:i + 4] != after[i:i + 4]}
        self.assertEqual(changed, {QUARTER, SIM, CHOP})

    @unittest.skipUnless(REAL_SETTINGS.is_file(), "a real game-written Settings1 is not named in B780_B10_SETTINGS")
    def test_a_real_game_written_profile(self):
        old = REAL_SETTINGS.read_bytes()
        new, rows = profile.edit(old, profile.values_from_plan(profile.plan(old, NEW)))
        self.assertEqual(len(rows), 3)
        m, live = self.load(self.retail, new)
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (7, 15, 1))
        self.assertEqual(live, new)

    @unittest.skipUnless(REAL_FRANCHISE.is_file(), "a real game-written franchise is not named in B780_B10_V07")
    def test_a_franchise_prefix_loads_through_the_same_routine(self):
        # a franchise save starts with the same 0x2E0-byte block; its loaders call FUN_000E2E20 on that prefix
        franchise = REAL_FRANCHISE.read_bytes()
        new, rows = profile.edit(franchise, profile.values_from_plan(profile.plan(franchise, NEW)))
        self.assertEqual(len(rows), 3)
        m, live = self.load(self.retail, new[:BLOCK_SIZE])
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (7, 15, 1))
        self.assertEqual(live, new[:BLOCK_SIZE])


ABBREVIATIONS = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARI", "LAC", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG",
                 "JAX", "NYJ", "DET", "GB", "CAR", "NE", "LV", "LAR", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN")


@unittest.skipUnless(hn1.XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class ChampionsPageTests(unittest.TestCase):
    """The seasons Upgrade merges into a save are the seasons the game's Player Card page draws."""

    @classmethod
    def setUpClass(cls):
        hn1.NativeTests.setUpClass()
        cls.helper = hn1.NativeTests("test_a_block_written_by_the_studio_reads_back_and_is_extended")
        cls.seed = history.seeded_block()

    def machine(self):
        m = self.helper.machine()
        m.record(hn1.RETIRE, "retirement pass")
        self.clubs(m)
        return m

    @staticmethod
    def clubs(m, skip=()):
        """The 32 clubs in the arena's own order (the helper's season() builds its own pair; leave those alone)."""
        for index, abbr in enumerate(ABBREVIATIONS):
            if index not in skip:
                m.club(index, f"City{index}", f"Nick{index}", abbr)
        m.wire(None)

    @staticmethod
    def expected(rows):
        """The text the page shows for each season row, newest first (hn1 layout: year club pts-pts club  NAME, POS)."""
        lines = []
        for row in rows:
            text = (f"{row['super_bowl'] + 1965} {ABBREVIATIONS[row['champion']]} {row['champion_points']}-"
                    f"{row['runner_up_points']} {ABBREVIATIONS[row['runner_up']]}")
            mvp = row["super_bowl_mvp"]
            if mvp:
                text += f"  {mvp['last']}, {mvp['position']}"
            lines.append(text)
        return lines

    def test_the_seeded_seasons_are_drawn_newest_first(self):
        m = self.machine()
        merged, _info = history.merge_blocks(None, self.seed, 60)
        m.uc.mem_write(m.GAP, merged)
        rows = m.history()
        self.assertEqual([r["super_bowl"] for r in rows], list(range(60, 38, -1)))     # the game's reader accepts the block
        calls, text = self.helper.draw_card(m, 2)
        self.assertEqual(calls, ["header", "photo", "model"])
        drawn = [t[0] for t in text[:6]]
        self.assertEqual(drawn, self.expected(rows[:6]))
        self.assertEqual(drawn[0], "2025 SEA 29-13 NE  WALKER, HB")                    # Super Bowl LX
        self.assertIn("1-6 OF 22  UP/DOWN", [t[0] for t in text])                       # six at a time, 22 in all

    def test_a_season_the_game_recorded_is_extended_not_replaced(self):
        m = self.machine()
        self.helper.season(m, winner=27, loser=21, high=31, low=24, season_index=0)    # the 2026 season: Super Bowl 61
        self.clubs(m, skip=(27, 21))
        m.call(self.helper.champ["champions_advance"])
        own = bytes(m.uc.mem_read(m.GAP, history.USED))
        self.assertEqual([r["super_bowl"] for r in m.history()], [61])                 # the game wrote one season
        merged, info = history.merge_blocks(own, self.seed, 61)
        self.assertEqual((info["kept"], info["added"][0], info["added"][-1]), ([61], 40, 60))
        m.uc.mem_write(m.GAP, merged)
        rows = m.history()
        self.assertEqual([r["super_bowl"] for r in rows], list(range(61, 39, -1)))
        _calls, text = self.helper.draw_card(m, 2)
        drawn = [t[0] for t in text[:6]]
        self.assertEqual(drawn[1], "2025 SEA 29-13 NE  WALKER, HB")
        self.assertEqual(drawn[0].split()[0], "2026")
        self.assertEqual([r["season_mvp"] and r["season_mvp"]["last"] for r in rows[:2]], ["STAFFORD", None])
        # the next Super Bowl the game plays is written into the merged ring the way it extends its own
        self.helper.season(m, winner=3, loser=9, high=27, low=20, season_index=1)
        self.clubs(m, skip=(3, 9))
        m.call(self.helper.champ["champions_advance"])
        self.assertEqual([r["super_bowl"] for r in m.history()][:3], [62, 61, 60])
        self.assertEqual(len(m.history()), 22)

    def test_an_edited_ring_with_a_foreign_checksum_reads_as_empty_not_as_wrong_champions(self):
        m = self.machine()
        merged, _info = history.merge_blocks(None, self.seed, 60)
        broken = bytearray(merged)
        broken[40] ^= 0x01                                              # one season's byte changed after the checksum
        m.uc.mem_write(m.GAP, bytes(broken))
        self.assertEqual(m.history(), [])                              # the Python model and the game agree it is unreadable
        _calls, text = self.helper.draw_card(m, 2)
        self.assertFalse([t for t in text if t[0].startswith("20")])


RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "")) / "ESPN NFL 2K5 (USA)" / "default.xbe"


@unittest.skipUnless(HAVE_UC and REAL_FRANCHISE.is_file() and RETAIL_XBE.is_file(),
                     "the retail executable, the retail ROST pack and a real v0.7 franchise (B780_B10_V07) are required")
class GameResaveTests(unittest.TestCase):
    """The game's own load and save of a real v0.7 franchise, then Franchise > Upgrade's in-place fill.

    The arena runtime (``arena_load``, tools/roster_arena/lifecycle.h) runs unmodified under Unicorn: it moves the
    old 0x410-byte tail to the end of the 0xCA000 arena, clears the old tail and the gap, adds no record, and the native
    writer saves the arena again.  The fill must then give what Studio's growth of the original save gives."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_arena as arena
        from mod_editor.core import nfl2k5_roster_arena_growth as growth
        from mod_editor.core import nfl2k5_team_history as team_history
        from tests.mod_editor import test_nfl2k5_roster_arena_growth as growth_tests
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        if not (RETAIL_XBE.parent / "vc_53450030/0").is_file():
            raise unittest.SkipTest("the preserved ROST pack is absent")
        require_nfl_retail_packs(RETAIL_XBE.parent)
        cls.arena, cls.growth_tests = arena, growth_tests
        retail = RETAIL_XBE.read_bytes()
        cls.xbe, _ = growth.apply(retail, reserves_16=False, capacity=True)
        with team_history._outer_image()(RETAIL_XBE.parent) as archive:
            entry = team_history._entry(archive)
            retail_rost = archive.read(entry.virtual_offset, entry.size)
        cls.rost, _ = arena.migrate(retail_rost, reserves_16=False, capacity_records=612)
        cls.body = cls.rost[0x20:]

    def resave(self, source: bytes) -> bytes:
        """The v0.8 game loads ``source`` (a 0xB0000-arena franchise) and saves it again; -> the file as written."""
        import unicorn as uni
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
        from mod_editor.core import nfl2k5_franchise_save as fs
        arena = self.arena
        base = self.growth_tests.NativeTests("test_native_old_save_load_migrates_auxiliary_tail")
        base.patched, base.body = self.xbe, self.body
        base.setUp()
        base.put(0xB72808, arena.CAPACITY_ARENA_SIZE)
        base.put(0xB7280C, arena.CAPACITY_ARENA_SIZE)
        refresh = (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77B00, 0x77470)       # UI and cache refreshes outside the storage proof

        def service(uc, _address, _size, _data):
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, base.word(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
        hook = base.uc.hook_add(uni.UC_HOOK_CODE, service, begin=min(refresh), end=max(refresh))
        try:
            end = fs.ARENA_END + arena.LEGACY_CAPACITY_ARENA_SIZE - arena.RETAIL_SIZE
            base.uc.mem_write(base.OUT, source[fs.ARENA_WRAPPER:end])
            base.call(0xC2040, ecx=base.OUT, budget=12000000)                 # the native franchise load
            self.assertEqual(base.word(0xB72808), arena.CAPACITY_ARENA_SIZE)
            base.call(0xC1F90, ecx=base.OUT, budget=12000000)                 # the native franchise save
            resaved = bytes(base.uc.mem_read(base.OUT, 0x20 + 0x20 + arena.CAPACITY_ARENA_SIZE))
        finally:
            base.uc.hook_del(hook)
        return source[:fs.ARENA_WRAPPER] + resaved + source[end:]

    def test_the_fill_completes_what_the_games_own_resave_leaves(self):
        from mod_editor.core import nfl2k5_roster_arena as arena
        from mod_editor.core import nfl2k5_save_rost as sr
        original = REAL_FRANCHISE.read_bytes()
        native = original[:-34320] if not any(original[-34320:]) else original
        resaved = self.resave(native)
        document = sr.decode(resaved)
        self.assertEqual((document.layout.arena_size, document.tables["primary"].count), (arena.CAPACITY_ARENA_SIZE, 3231))
        self.assertEqual(arena.capacity_descriptor(resaved, document.layout)[0], 612)
        stale = 0x320 + arena.LEGACY_CAPACITY_ARENA_SIZE - 0x410
        self.assertEqual(resaved[stale:stale + 0x410], bytes(0x410))           # the released loader clears the old tail
        filled, receipt = arena.fill_class_records(resaved)
        self.assertEqual((receipt["class_records"], receipt["primary_after"], receipt["file_growth"]), (865, 4096, 0))
        grown, _ = arena.migrate(native, reserves_16=False, capacity_records=612)
        self.assertEqual(filled, grown)                                          # byte for byte, arena and everything after it

    @unittest.skipUnless(Path(os.environ.get("B780_B10_DISC_ROST", "")).is_file(),
                         "the released disc's roster is not named in B780_B10_DISC_ROST")
    def test_a_history_seeded_into_the_old_arena_survives_the_games_move(self):
        """`champions` on a save that is still in the v0.7 arena: the game's own load moves the whole tail, block included."""
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        original = REAL_FRANCHISE.read_bytes()
        native = original[:-34320] if not any(original[-34320:]) else original
        body = Path(os.environ["B780_B10_DISC_ROST"]).read_bytes()
        seed = body[history.gap_offset(body):history.gap_offset(body) + history.USED]
        seeded, receipt = up.sync_champions(native, body)
        self.assertEqual((receipt["seeded"], len(receipt["added"])), (True, 22))
        resaved = self.resave(seeded)
        at = up.franchise(resaved)[0].arena_end - history.FROM_END + history.RESERVE_BLOCK
        self.assertEqual(resaved[at:at + history.USED], seed)
        self.assertEqual([r["super_bowl"] for r in history.read_block(resaved[at:at + history.USED])], list(range(60, 38, -1)))


CAREER_OLD = Path(os.environ.get("B780_B10_CAREER_OLD", ""))
CAREER_NEW = Path(os.environ.get("B780_B10_CAREER_NEW", ""))


@unittest.skipUnless(HAVE_UC and RETAIL_XBE.is_file(), "the retail executable and unicorn are required")
class CareerStageTests(unittest.TestCase):
    """The game's own MyCareer staging accepts the block Upgrade writes and refuses the one it used to write.

    ``inline_stage`` (tools/mycareer_mode/runtime.c) runs unmodified on a whole save file: it follows the file's own
    pointers to the MyPlayer record and returns 0 when the career block's three string offsets differ from the record's."""

    @classmethod
    def setUpClass(cls):
        import hashlib
        from mod_editor.core import nfl2k5_my_career_mode as mode
        from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
        retail = RETAIL_XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail XBE pin differs")
        cls.payload, _ = mode.apply(retail)

    def stage(self, file: bytes, arena_size: int) -> int:
        from tests.nfl2k5_my_career_mode_fixture import Machine
        with Machine(self.payload) as m:
            m.uc.mem_write(m.SAVE, file)
            m.put(0xB72808, arena_size)
            return m.call("inline_stage", ecx=m.SAVE, edx=len(file), budget=4_000_000)

    def test_a_grown_career_save_stages_only_with_the_rebased_block(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        from mod_editor.core import nfl2k5_roster_arena as arena
        from tests.mod_editor.test_b780_b10_upgrade_gaps import capacity_fixture, with_career, with_class_template
        legacy = with_career(with_class_template(capacity_fixture()[0]))
        self.assertEqual(self.stage(legacy, arena.LEGACY_CAPACITY_ARENA_SIZE), 1)          # the v0.7-shaped career save loads
        grown, _ = arena.migrate(legacy, reserves_16=False, capacity_records=612)
        self.assertEqual(self.stage(grown, arena.CAPACITY_ARENA_SIZE), 0)                   # what Upgrade used to write
        fixed, receipt = up.rebase_career_block(legacy, grown)
        self.assertTrue(receipt["rebased"])
        self.assertEqual(self.stage(fixed, arena.CAPACITY_ARENA_SIZE), 1)                   # what it writes now

    def test_the_in_place_fill_of_a_game_resaved_career_stages_only_with_the_rebased_block(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        from mod_editor.core import nfl2k5_roster_arena as arena
        from tests.mod_editor.test_b780_b10_upgrade_gaps import capacity_fixture, game_moves_tail, with_career, with_class_template
        moved = game_moves_tail(with_career(with_class_template(capacity_fixture()[0])))
        self.assertEqual(self.stage(moved, arena.CAPACITY_ARENA_SIZE), 1)                   # the game's resave still stages
        filled, receipt = arena.fill_class_records(moved)
        self.assertGreater(receipt["class_records"], 0)
        self.assertEqual(self.stage(filled, arena.CAPACITY_ARENA_SIZE), 0)
        fixed, _ = up.rebase_career_block(moved, filled)
        self.assertEqual(self.stage(fixed, arena.CAPACITY_ARENA_SIZE), 1)

    @unittest.skipUnless(CAREER_OLD.is_file() and CAREER_NEW.is_file(),
                         "a real career save and its Upgrade output are not named in B780_B10_CAREER_OLD / B780_B10_CAREER_NEW")
    def test_a_real_career_save_before_and_after_upgrade(self):
        import struct
        from mod_editor.core import nfl2k5_my_career_save as career
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        from mod_editor.core import nfl2k5_roster_arena as arena
        old, new = CAREER_OLD.read_bytes(), CAREER_NEW.read_bytes()
        self.assertEqual(self.stage(old, 0x91000), 1)
        self.assertEqual(self.stage(new, arena.CAPACITY_ARENA_SIZE), 1)
        # the save as the old Upgrade wrote it: the same arena change, the career block still holding the old offsets
        at_old, at_new = up.career_block_at(old), up.career_block_at(new)
        stale = bytearray(new)
        for stored in (44, 48, 52):
            struct.pack_into("<I", stale, at_new + stored, career.word(old, at_old + stored))
        stale[at_new:at_new + 128] = career.seal(bytes(stale[at_new:at_new + 128]))
        self.assertNotEqual(bytes(stale), new)
        self.assertEqual(self.stage(bytes(stale), arena.CAPACITY_ARENA_SIZE), 0)


if __name__ == "__main__":
    unittest.main()
