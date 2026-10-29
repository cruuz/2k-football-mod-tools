"""b779 hn1: the champions history block and a franchise save's auxiliary tail never overlap.

A save's auxiliary tail (up to 366 bytes) is the last bytes of the roster arena; the champions block sits right after the
352-byte reserve block, in the free bytes before it. Proven on real preserved saves grown to both capacity arenas
(0xB0000 and 0xCA000), and on the arithmetic for any tail the arena accepts. Private fixtures are skipped when absent.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_champions_history as history
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_save_rost as codec

HUB = Path(os.environ.get("NFL2K5_SAVE_FIXTURES", "/home/noah/Desktop/2K5-8 Editors/save_fixtures"))
SAVES = {"f0 (aux 366 declared)": HUB / "f0/UDATA/53450030/0B8506889D40/SAVEGAME.DAT",
         "f1 (aux 366 declared)": HUB / "f1/UDATA/53450030/0B8506889D40/SAVEGAME.DAT",
         "Franchise1 (aux 366 undeclared)": HUB / "256B40374FD6-Franchise1/UDATA/53450030/256B40374FD6/SAVEGAME.DAT"}
ARENAS = (arena.LEGACY_CAPACITY_ARENA_SIZE, arena.CAPACITY_ARENA_SIZE)
MOST_AUX = 366


class ArithmeticTests(unittest.TestCase):
    def test_the_block_ends_before_the_auxiliary_tail_begins_in_every_arena(self):
        for size in (arena.ARENA_SIZE,) + ARENAS:
            end = size
            block = range(end - history.FROM_END + history.RESERVE_BLOCK, end - history.FROM_END + history.RESERVE_BLOCK + history.USED)
            aux = range(end - MOST_AUX, end)
            self.assertFalse(set(block) & set(aux), hex(size))
            self.assertEqual(block.stop, end - 0x192)
            self.assertGreaterEqual(aux.start - block.stop, 36)
        self.assertEqual(history.FREE, 306)
        self.assertLessEqual(history.USED, history.FREE)
        self.assertEqual(history.USED, 270)

    def test_the_largest_tail_the_arena_accepts_still_leaves_room_only_for_the_reserve_block(self):
        # the arena admits an auxiliary tail up to 0x400 - 352; the history is only guaranteed clear of the 366 bytes
        # real saves hold, so a larger declared tail makes the Studio refuse to write the history (see test below)
        self.assertEqual(arena.CAPACITY_TAIL - arena.BLOCK_SIZE, 672)
        self.assertGreater(672, MOST_AUX)


class RealSaveTests(unittest.TestCase):
    def grown(self, path, size):
        original = path.read_bytes()
        try:
            payload, _receipt = arena._migrate_capacity(original, 612, class_records=0, arena_size=size)
        except arena.ArenaError as exc:               # a save with no blank create record cannot be grown at all
            raise unittest.SkipTest(f"{path.name}: {exc}")
        document = codec.decode(payload)
        return payload, document

    def test_a_real_saves_auxiliary_tail_and_the_champions_block_never_overlap(self):
        seen = 0
        for label, path in SAVES.items():
            if not path.is_file():
                continue
            for size in ARENAS:
                with self.subTest(save=label, arena=hex(size)):
                    try:
                        payload, document = self.grown(path, size)
                    except unittest.SkipTest:
                        continue
                    end = document.layout.end
                    self.assertEqual(end - document.layout.root, size)
                    declared = struct.unpack_from("<I", payload, document.layout.wrapper + 8)[0]
                    aux = declared or MOST_AUX
                    self.assertEqual(declared, MOST_AUX)                    # declared by the growth, even when the save left it 0
                    body = payload[:end]
                    reserve = end - history.FROM_END
                    self.assertEqual(payload[reserve:reserve + 8], arena.MAGIC)
                    # the free bytes the block may use are zero and end before the tail
                    free_from = reserve + history.RESERVE_BLOCK
                    self.assertFalse(any(payload[free_from:end - aux]), "the bytes before the tail are free")
                    self.assertGreaterEqual(end - aux - free_from, history.USED)
                    out, receipt = history.apply_body(body)
                    changed = [i for i in range(len(body)) if body[i] != out[i]]
                    self.assertTrue(changed)
                    self.assertTrue(all(free_from <= i < free_from + history.USED for i in changed))
                    self.assertLess(free_from + history.USED, end - aux)
                    self.assertEqual(out[end - aux:end], body[end - aux:end], "the auxiliary tail is byte for byte intact")
                    self.assertEqual(out[reserve:free_from], body[reserve:free_from])          # and the reserve block
                    rows = history.read_body(out)
                    self.assertEqual(len(rows), 22)
                    self.assertEqual(rows[0]["super_bowl"], 60)
                    again, receipt = history.apply_body(out)                                # idempotent on a real save
                    self.assertEqual(again, out)
                    seen += 1
        if not seen:
            self.skipTest("no preserved franchise save is present")

    def test_a_save_grown_from_the_older_arena_carries_the_block_with_its_tail(self):
        path = SAVES["f0 (aux 366 declared)"]
        if not path.is_file():
            self.skipTest("preserved save absent")
        legacy, legacy_doc = self.grown(path, arena.LEGACY_CAPACITY_ARENA_SIZE)
        body = legacy[:legacy_doc.layout.end]
        out, _ = history.apply_body(body)
        payload = bytearray(legacy)
        payload[:legacy_doc.layout.end] = out
        grown, receipt = arena.migrate(bytes(payload), reserves_16=False, capacity_records=612)
        document = codec.decode(grown)
        end = document.layout.end
        self.assertEqual(end - document.layout.root, arena.CAPACITY_ARENA_SIZE)
        rows = history.read_body(grown[:end])
        self.assertEqual([r["super_bowl"] for r in rows], list(range(60, 38, -1)))
        aux = struct.unpack_from("<I", grown, document.layout.wrapper + 8)[0]
        self.assertEqual(aux, MOST_AUX)
        self.assertEqual(grown[end - aux:end], legacy[legacy_doc.layout.end - aux:legacy_doc.layout.end])


if __name__ == "__main__":
    unittest.main()
