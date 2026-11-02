"""b780 b10-profile (bug row D9): Franchise > Upgrade seeds the champions history and no longer depends on the order of saves.

v0.8 listed two gaps for upgraded franchises: the champions history started empty (it only filled from the next Super Bowl),
and Upgrade had to run before the v0.8 game first saved the old franchise, because the game moves a v0.7 save to the bigger
roster file when it saves it and adds none of the 865 draft-class records ("it keeps its 3,231 records").  These tests cover
the merge of the disc's Super Bowl seasons into a save's 270-byte history block, the Upgrade step around it, and the in-place
fill of the draft-class records.  Fixtures are synthetic; real game-written saves and the released disc's roster are read only
when the environment names them (B780_B10_V07, B780_B10_RESAVED, B780_B10_DISC_ROST), and are never written.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions_history as history  # noqa: E402
from mod_editor.core import nfl2k5_franchise_upgrade as up  # noqa: E402
from mod_editor.core import nfl2k5_roster_arena as arena  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as sr  # noqa: E402
from tests.mod_editor.test_franchise_upgrade import capacity_fixture  # noqa: E402

REAL_V07 = Path(os.environ.get("B780_B10_V07", ""))
REAL_RESAVED = Path(os.environ.get("B780_B10_RESAVED", ""))
REAL_DISC_ROST = Path(os.environ.get("B780_B10_DISC_ROST", ""))
ZERO_FOOTER = 34_320


def seed_block() -> bytes:
    return history.seeded_block()                        # Super Bowls XXXIX to LX, the shipped sourced data


def disc_body(block: bytes | None, *, room: bool = True, size: int = arena.CAPACITY_ARENA_SIZE + 0x40) -> bytes:
    """A roster body ending like a disc's main roster: the reserve block, then the champions history."""
    body = bytearray(size)
    if room:
        at = size - history.FROM_END
        body[at:at + 8] = history.RESERVE_MAGIC
        if block is not None:
            body[at + history.RESERVE_BLOCK:at + history.RESERVE_BLOCK + history.USED] = block
    return bytes(body)


def recorded(number: int, champion=3, runner_up=5, points=(24, 17), mvp=("Test Player", "QB")) -> bytes:
    return history.entry_bytes(number, champion, runner_up, points[0], points[1], mvp)


class MergeTests(unittest.TestCase):
    def test_an_empty_save_takes_the_discs_block_as_it_is(self):
        seed = seed_block()
        for own in (None, bytes(history.USED)):
            merged, info = history.merge_blocks(own, seed, 60)
            self.assertEqual(merged, seed)
            self.assertEqual(info["added"], list(range(39, 61)))
            self.assertTrue(info["seeded"])
            self.assertEqual(info["kept"], [])
        rows = history.read_block(merged)
        self.assertEqual([r["super_bowl"] for r in rows], list(range(60, 38, -1)))
        self.assertEqual(rows[0]["season_mvp"]["last"], "STAFFORD")

    def test_super_bowls_the_franchise_could_not_have_seen_are_not_seeded(self):
        merged, info = history.merge_blocks(None, seed_block(), 50)
        self.assertEqual(info["added"], list(range(39, 51)))
        self.assertEqual([n for n, why in info["skipped"]], list(range(51, 61)))
        self.assertEqual({why for _n, why in info["skipped"]}, {"not played yet"})
        rows = history.read_block(merged)
        self.assertEqual(rows[0]["super_bowl"], 50)
        self.assertIsNone(rows[0]["season_mvp"])             # the disc's newest-season MVP belongs to Super Bowl 60
        with self.assertRaises(history.ChampionsHistoryError):
            history.merge_blocks(None, seed_block(), 38)    # nothing of the disc's history is old enough

    def test_seasons_the_game_recorded_are_kept_and_older_ones_fill_around_them(self):
        own = history.block_bytes({61: recorded(61)}, history.mvp_slot(61, ("Test Player", "QB"), 3))
        merged, info = history.merge_blocks(own, seed_block(), 61)
        self.assertEqual(info["kept"], [61])
        self.assertEqual(info["added"], list(range(40, 61)))           # Super Bowl 39 would share 61's ring slot (39 % 22)
        self.assertEqual(info["skipped"], [(39, "older than the ring keeps")])
        rows = history.read_block(merged)
        self.assertEqual([r["super_bowl"] for r in rows], list(range(61, 39, -1)))
        self.assertEqual(rows[0]["champion"], 3)                        # the game's own entry is untouched
        self.assertEqual(rows[0]["season_mvp"]["last"], "PLAYER")       # and so is the newest-season MVP field
        self.assertEqual(history.read_block(merged)[1]["super_bowl"], 60)
        self.assertTrue(history.block_ok(merged))

    def test_a_slot_the_game_filled_is_never_replaced(self):
        own = history.block_bytes({61: recorded(61), 59: recorded(59, champion=9, runner_up=2)})
        merged, info = history.merge_blocks(own, seed_block(), 61)
        self.assertEqual(info["kept"], [59, 61])
        self.assertNotIn(59, info["added"])
        row = {r["super_bowl"]: r for r in history.read_block(merged)}[59]
        self.assertEqual((row["champion"], row["runner_up"]), (9, 2))

    def test_the_result_is_a_block_the_games_reader_accepts(self):
        own = history.block_bytes({62: recorded(62)}, history.mvp_slot(62, ("A B", "HB"), 0))
        merged, _info = history.merge_blocks(own, seed_block(), 62)
        self.assertEqual(len(merged), history.USED)
        self.assertTrue(history.block_ok(merged))
        self.assertEqual(merged[:12], own[:12])                         # magic, version, ring size
        self.assertEqual(int.from_bytes(merged[12:16], "little"), history.checksum(merged))

    def test_a_foreign_or_damaged_spare_area_is_refused_not_overwritten(self):
        for own in (bytes(range(1, 256)) + bytes(15), history.block_bytes({61: recorded(61)})[:12] + b"\xff" * 4
                    + history.block_bytes({61: recorded(61)})[16:]):
            with self.subTest(len(own)), self.assertRaises(history.ChampionsHistoryError):
                history.merge_blocks(own, seed_block(), 61)
        with self.assertRaises(history.ChampionsHistoryError):
            history.merge_blocks(None, bytes(history.USED), 60)         # a disc without a history

    def test_the_merge_is_stable(self):
        once, _ = history.merge_blocks(None, seed_block(), 60)
        again, info = history.merge_blocks(once, seed_block(), 60)
        self.assertEqual(again, once)
        self.assertEqual(info["added"], [])


class ChampionsStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.save, _disc = capacity_fixture()             # a synthetic v0.7 franchise (0xB0000 arena), season 2027
        cls.seed = seed_block()
        cls.room = len(cls.save) - 0x400 - 0x2E0 + 0x2E0  # unused; the offsets come from the parsed save

    def locate(self, payload):
        save, _roster = up.franchise(payload)
        block = save.arena_end - history.FROM_END
        return block, block + history.RESERVE_BLOCK

    def test_the_fixture_has_the_reserve_block_and_no_history(self):
        block, gap = self.locate(self.save)
        self.assertEqual(self.save[block:block + 8], history.RESERVE_MAGIC)
        self.assertFalse(any(self.save[gap:gap + history.FREE]))

    def test_the_discs_seasons_are_written_and_nothing_else_moves(self):
        out, receipt = up.sync_champions(self.save, disc_body(self.seed))
        _block, gap = self.locate(self.save)
        self.assertEqual(receipt["operation"], "champions")
        self.assertTrue(receipt["seeded"])
        self.assertEqual(receipt["added"], list(range(39, 61)))
        self.assertEqual(receipt["newest_super_bowl"], 60)
        self.assertEqual(receipt["seasons_in_history"], 22)
        self.assertEqual(len(receipt["changes"]), 22)
        self.assertTrue(receipt["outside_declared_fields_identical"])
        self.assertEqual(out[gap:gap + history.USED], self.seed)
        changed = [i for i, (a, b) in enumerate(zip(self.save, out)) if a != b]
        self.assertTrue(changed and all(gap <= i < gap + history.USED for i in changed))
        self.assertEqual(receipt["changed_bytes"], len(changed))
        self.assertEqual(receipt["storage_spans"], [{"field": "champions_history", "offset": gap, "size": history.USED}])
        self.assertEqual(len(out), len(self.save))

    def test_a_second_run_changes_nothing(self):
        once, _ = up.sync_champions(self.save, disc_body(self.seed))
        again, receipt = up.sync_champions(once, disc_body(self.seed))
        self.assertEqual(again, once)
        self.assertEqual(receipt["changes"], [])
        self.assertIn("already holds", receipt["reason"])

    def test_seasons_the_game_recorded_in_this_franchise_stay(self):
        _block, gap = self.locate(self.save)
        data = bytearray(self.save)
        data[gap:gap + history.USED] = history.block_bytes({61: recorded(61)}, history.mvp_slot(61, ("Own Mvp", "QB"), 4))
        out, receipt = up.sync_champions(bytes(data), disc_body(self.seed))
        self.assertFalse(receipt["seeded"])
        self.assertEqual(receipt["kept"], [61])
        self.assertEqual(receipt["added"], list(range(40, 61)))
        rows = history.read_block(out[gap:gap + history.USED])
        self.assertEqual([r["super_bowl"] for r in rows], list(range(61, 39, -1)))
        self.assertEqual(rows[0]["champion"], 3)

    def test_every_reason_for_leaving_a_save_alone_is_said(self):
        save, body = self.save, disc_body(self.seed)
        block, gap = self.locate(save)
        cases = {}
        # the disc cannot give a history
        cases["no room on the disc"] = (save, disc_body(None, room=False), "no room for a champions history")
        cases["an empty disc history"] = (save, disc_body(None), "disc's champions history is empty")
        # the save cannot take one
        from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
        cases["no reserve block"] = (synthetic_franchise(), body, "no room for a champions history (no reserve block)")
        busy = bytearray(save)
        busy[gap + 5:gap + 9] = b"data"
        cases["something else lives there"] = (bytes(busy), body, "something other than a champions history")
        tail = bytearray(save)
        tail[gap + history.USED + 3] = 9
        cases["bytes behind the block"] = (bytes(tail), body, "behind the champions history hold something else")
        aux = bytearray(save)
        struct.pack_into("<I", aux, 0x2E8, 400)
        cases["a long auxiliary tail"] = (bytes(aux), body, "auxiliary tail is 400 bytes")
        for label, (payload, disc, why) in cases.items():
            with self.subTest(label):
                out, receipt = up.sync_champions(payload, disc)
                self.assertEqual(out, payload)
                self.assertEqual(receipt["changes"], [])
                self.assertIn(why, receipt["reason"])

    def test_the_command_and_the_step_are_part_of_upgrade(self):
        from mod_editor.core import nfl2k5_franchise_upgrade_io as service
        self.assertIn("champions", service.COMMANDS)
        import tools.nfl2k5_franchise_upgrade as cli
        self.assertEqual(cli.COMMANDS, service.COMMANDS)


# --- the draft-class records: Upgrade after the game has already saved the franchise -------------------------------
def with_class_template(payload: bytes) -> bytes:
    """The synthetic v0.7 fixture has no free draft-class record (flags 0, a college, no history): turn the last appended
    vacancy into one, as the v0.7 disc's first-class window records are."""
    document = sr.decode(payload)
    primary = document.tables["primary"]
    at = primary.offset + (primary.count - 1) * 84
    out = bytearray(payload)
    out[at + 8] = 0
    college = document.rel(primary.offset + 0x10)                  # any string inside the arena: the first player's name
    struct.pack_into("<i", out, at, college - at + 1)
    return bytes(out)


def game_moves_tail(payload: bytes) -> bytes:
    """What the v0.8 game's ``arena_load`` + save do to a v0.7 (0xB0000) franchise save (tools/roster_arena/lifecycle.h):
    the 0x410-byte tail (descriptor, reserve block, history bytes, auxiliary tail) moves to the end of the 0xCA000 arena,
    the old tail and the new gap are cleared, no record is added; everything after the arena is unchanged."""
    document = sr.decode(payload)
    layout = document.layout
    old, new, root = layout.arena_size, arena.CAPACITY_ARENA_SIZE, layout.root
    tail = payload[root + old - 0x410:root + old]
    body = bytearray(payload[root:root + old - 0x410]) + bytes(new - old) + tail
    out = bytearray(payload[:root]) + body + payload[layout.end:]
    struct.pack_into("<I", out, layout.wrapper + 4, root + new - layout.preamble)
    return bytes(out)


class InPlaceFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v07 = with_class_template(capacity_fixture()[0])
        cls.moved = game_moves_tail(cls.v07)

    def test_the_fixture_is_the_trap(self):
        document = sr.decode(self.moved)
        self.assertEqual(document.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(arena.capacity_descriptor(self.moved, document.layout), (612, arena.capacity_descriptor(self.v07, sr.decode(self.v07).layout)[1]))
        before = document.tables["primary"].count
        # the old code stopped here: the arena already has the disc's size, so nothing could be added
        out, receipt = arena._migrate_capacity(self.moved, 612, None, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual((out, receipt["already_applied"]), (self.moved, True))
        self.assertEqual(sr.decode(out).tables["primary"].count, before)

    def test_the_fill_equals_growing_the_original_save(self):
        grown, grown_receipt = arena.migrate(self.v07, reserves_16=False, capacity_records=612)
        filled, receipt = arena.fill_class_records(self.moved)
        self.assertGreater(receipt["class_records"], 100)
        self.assertEqual(receipt["class_records"], grown_receipt["class_records"])
        self.assertEqual(receipt["file_growth"], 0)
        self.assertTrue(receipt["in_place"])
        self.assertEqual(len(filled), len(grown))
        self.assertEqual(filled, grown)                                   # byte for byte the layout one growth would make
        document = sr.decode(filled)
        self.assertEqual(document.tables["primary"].count, 2 + 612 + receipt["class_records"])
        self.assertEqual(arena.capacity_descriptor(filled, document.layout)[0], 612 + receipt["class_records"])

    def test_an_explicit_count_is_honoured(self):
        grown, _ = arena.migrate(self.v07, reserves_16=False, capacity_records=612, class_records=25)
        filled, receipt = arena.fill_class_records(self.moved, class_records=25)
        self.assertEqual((receipt["class_records"], filled), (25, grown))

    def test_a_second_fill_is_a_no_op(self):
        filled, _ = arena.fill_class_records(self.moved)
        again, receipt = arena.fill_class_records(filled)
        self.assertEqual(again, filled)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["class_records"], 0)

    def test_everything_after_the_arena_is_untouched_and_the_size_is_the_same(self):
        zero_footer = self.moved + bytes(ZERO_FOOTER)
        filled, _ = arena.fill_class_records(zero_footer)
        self.assertEqual(len(filled), len(zero_footer))
        end = 0x320 + arena.CAPACITY_ARENA_SIZE
        self.assertEqual(filled[end:], zero_footer[end:])
        self.assertEqual(filled[:0x320], zero_footer[:0x320])

    def test_a_save_without_a_free_class_record_is_left_alone_with_the_reason(self):
        plain = game_moves_tail(capacity_fixture()[0])                     # no flags-0 record to copy
        out, receipt = arena.fill_class_records(plain)
        self.assertEqual(out, plain)
        self.assertTrue(receipt["already_applied"])
        self.assertIn("no free draft-class record", receipt["reason"])

    def test_a_save_without_the_capacity_descriptor_is_left_alone_with_the_reason(self):
        plain = bytearray(self.moved)
        at = 0x320 + arena.CAPACITY_ARENA_SIZE - 0x410
        plain[at:at + 8] = bytes(8)
        out, receipt = arena.fill_class_records(bytes(plain))
        self.assertEqual(out, bytes(plain))
        self.assertIn("no capacity descriptor", receipt["reason"])

    def test_name_strings_the_game_wrote_in_the_free_zone_move_with_their_records(self):
        # the v0.7 game keeps Create Player's blank-name buffers after the descriptor's names; the fill relocates
        # them the way the growth does, and every pointer into them follows
        document = sr.decode(self.v07)
        primary = document.tables["primary"]
        descriptor = arena.capacity_descriptor(self.v07, document.layout)
        names_end = ((descriptor[1] + descriptor[0] * 84 + 1) & ~1) + descriptor[0] * 68
        data = bytearray(self.v07)
        text = ("Zed" + "\0" * 2).encode("utf-16le")
        data[names_end:names_end + len(text)] = text
        at = primary.offset + 5 * 84
        struct.pack_into("<i", data, at + 0x10, names_end - (at + 0x10) + 1)
        v07 = bytes(data)
        moved = game_moves_tail(v07)
        filled, receipt = arena.fill_class_records(moved)
        self.assertGreater(receipt["class_records"], 0)
        grown, _ = arena.migrate(v07, reserves_16=False, capacity_records=612)
        self.assertEqual(filled, grown)
        doc = sr.decode(filled)
        self.assertEqual(doc.string(doc.tables["primary"].offset + 5 * 84 + 0x10), "Zed")


@unittest.skipUnless(REAL_V07.is_file() and REAL_RESAVED.is_file(),
                     "real game-written saves are not named in B780_B10_V07 and B780_B10_RESAVED")
class RealSaveTests(unittest.TestCase):
    """The released v0.7 game's 881,340-byte franchise, and the same franchise as a v0.8 game saved it (987,836 bytes)."""

    @classmethod
    def setUpClass(cls):
        cls.v07 = REAL_V07.read_bytes()
        cls.resaved = bytearray(REAL_RESAVED.read_bytes())
        # an early proof build of the v0.8 game left a copy of the old descriptor and reserve block at the old tail
        # position; the released arena_load clears them (tools/roster_arena/lifecycle.h), so clear them here too
        stale = 0x320 + arena.LEGACY_CAPACITY_ARENA_SIZE - 0x410
        if cls.resaved[stale:stale + 8] == arena.CAPACITY_MAGIC:
            cls.resaved[stale:stale + 368] = bytes(368)
        cls.resaved = bytes(cls.resaved)

    def test_the_resaved_franchise_still_has_its_3231_records_and_the_descriptor(self):
        document = sr.decode(self.resaved)
        self.assertEqual(document.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(document.tables["primary"].count, 3231)
        self.assertEqual(arena.capacity_descriptor(self.resaved, document.layout)[0], 612)

    def test_filling_the_resaved_franchise_equals_growing_the_original_but_for_the_games_own_byte(self):
        native = self.v07[:-ZERO_FOOTER]
        grown, grown_receipt = arena.migrate(native, reserves_16=False, capacity_records=612)
        filled, receipt = arena.fill_class_records(self.resaved)
        self.assertEqual((receipt["class_records"], receipt["primary_after"], receipt["file_growth"]), (865, 4096, 0))
        self.assertEqual(receipt["class_records"], grown_receipt["class_records"])
        differing = [i for i in range(len(grown)) if grown[i] != filled[i]]
        self.assertLessEqual(len(differing), 4, differing[:10])          # the game changed one byte of the season block
        self.assertTrue(all(i >= 0x320 + arena.CAPACITY_ARENA_SIZE for i in differing))
        self.assertEqual(filled[len(grown):], self.resaved[len(grown):])   # the stamped Player Progress footer is intact
        document = sr.decode(filled)
        self.assertEqual(arena.capacity_descriptor(filled, document.layout), (1477, 593792))


@unittest.skipUnless(REAL_V07.is_file() and REAL_DISC_ROST.is_file(),
                     "a real save and the released disc's roster are not named in B780_B10_V07 and B780_B10_DISC_ROST")
class RealChampionsTests(unittest.TestCase):
    def test_the_released_discs_history_is_seeded_into_a_real_grown_save(self):
        body = REAL_DISC_ROST.read_bytes()
        seed = body[history.gap_offset(body):history.gap_offset(body) + history.USED]
        grown, _ = arena.migrate(REAL_V07.read_bytes()[:-ZERO_FOOTER], reserves_16=False, capacity_records=612)
        out, receipt = up.sync_champions(grown, body)
        self.assertEqual((receipt["seeded"], len(receipt["added"]), receipt["newest_super_bowl"]), (True, 22, 60))
        at = up.franchise(out)[0].arena_end - history.FROM_END + history.RESERVE_BLOCK
        self.assertEqual(out[at:at + history.USED], seed)
        rows = history.read_block(out[at:at + history.USED])
        self.assertEqual((rows[0]["super_bowl"], rows[0]["champion_points"], rows[0]["runner_up_points"]), (60, 29, 13))
        self.assertEqual(rows[0]["super_bowl_mvp"]["last"], "WALKER")


if __name__ == "__main__":
    unittest.main()
