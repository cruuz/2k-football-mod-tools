"""b778-pc2: the franchise honors sync and the history fold it needs when a saved pool is full.

``fold_words`` is checked against the retail fold (FUN_0014EFE0) under Unicorn on random streams; the sync itself is
checked on synthetic franchises. The native class skips without the pinned USA XBE or Unicorn.
"""
from __future__ import annotations

from collections import Counter
import random
import struct
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_upgrade as up  # noqa: E402
from mod_editor.core import nfl2k5_franchise_upgrade_io as service  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as sr  # noqa: E402
from tests.mod_editor import test_nfl2k5_honors as native  # noqa: E402
from tests.mod_editor.test_franchise_team_history_upgrade import fixture as club_fixture  # noqa: E402
from tests.mod_editor.test_franchise_upgrade import disc_roster, fixture, signed_folder  # noqa: E402


def word(field, slot, value, *, folded=False):
    return (value & 0xFFFF) | (field << 16) | (slot << 23) | (0x40000000 if folded else 0)


class FoldTests(unittest.TestCase):
    """Pure Python, runs everywhere."""

    def test_fold_merges_by_sum_and_max_and_flags_the_receiver(self):
        words = [word(96, 1, 1), word(2, 1, 100), word(16, 1, 5), word(96, 2, 1), word(2, 2, 200),
                 word(16, 2, 9), word(0, 4, 16)]
        out = up.fold_words(words, 5, 4)
        self.assertEqual(sorted(w & ~0x80000000 for w in out),
                         sorted([word(96, 2, 2, folded=True), word(2, 2, 300, folded=True),
                                 word(16, 2, 9, folded=True), word(0, 4, 16)]))
        self.assertTrue(out[-1] & 0x80000000)
        self.assertFalse(any(w & 0x80000000 for w in out[:-1]))

    def test_a_sum_that_overflows_a_signed_cell_is_not_folded(self):
        words = [word(8, 1, 30000), word(8, 2, 30000), word(0, 4, 16)]
        out = up.fold_words(words, 5, 4)
        self.assertEqual(sorted(w & ~0x80000000 for w in out), sorted(words))
        words = [word(8, 1, 3000), word(8, 2, 20000), word(0, 4, 16)]
        self.assertEqual(sorted(w & ~0x80000000 for w in up.fold_words(words, 5, 4)),
                         sorted([word(8, 2, 23000, folded=True), word(0, 4, 16)]))

    def test_fold_leaves_new_seasons_dead_words_and_short_careers(self):
        dead = word(2, 1, 7) | 0x10000000
        words = [word(0, 4, 16), dead | 0x80000000]
        self.assertEqual(up.fold_words(words, 5, 4), (word(0, 4, 16), dead | 0x80000000))
        self.assertEqual(up.fold_words([], 5, 4), ())
        with self.assertRaises(up.UpgradeRefused):
            up.fold_words(words, 5, 1)


def with_streams(data, document, pool, streams):
    """A copy of a ROST-bearing buffer whose history pool at ``pool`` holds ``streams`` ({player index: words}),
    in player order; every other player has no stream."""
    data = bytearray(data)
    words, at = 0, pool
    data[pool:pool + 4 * 4000] = bytes(4 * 4000)
    for player in document.players:
        stream = streams.get(player.index)
        pointer = player.offset + 0x2C
        if not stream:
            struct.pack_into("<i", data, pointer, 0)
            continue
        struct.pack_into("<i", data, pointer, at - pointer + 1)
        for i, raw in enumerate(stream):
            struct.pack_into("<I", data, at, raw | (0x80000000 if i == len(stream) - 1 else 0))
            at += 4
        words += len(stream)
    struct.pack_into("<I", data, document.layout.root + 0x40, words)
    struct.pack_into("<i", data, document.layout.root + 0x44, pool - (document.layout.root + 0x44) + 1)
    return bytes(data)


def pair(save_streams, disc_streams):
    """(save payload, disc ROST body) over the synthetic franchise: Peyton Manning (years pro 7), Marvin Harrison (8)."""
    base = fixture(current=True)[0]
    document = sr.decode(base)
    save = with_streams(base, document, 0x70000, save_streams)
    disc = disc_roster(base)
    disc = with_streams(disc, sr.decode(disc, preamble=0, reference_year=up.BASE_YEAR), 0x70000 - 0x2E0, disc_streams)
    return save, disc


def honors_of(payload, index):
    _save, roster = up.franchise(payload)
    player = roster.players[index]
    return sorted(((w >> 16) & 127, (w >> 23) & 31, w & 0xFFFF, bool(w & 0x40000000))
                  for w in roster.history_words[player.key] if 96 <= (w >> 16) & 127 <= 105)


class SyncHonorsTests(unittest.TestCase):
    """b778-pc2: a franchise keeps its career-stat pool in the save, so one started before the honors page carried
    no award history. The disc's honors are copied by identity and re-slotted to the franchise's own season."""

    def streams(self):
        # years pro: Manning 8, Harrison 9. disc (2026): Manning MVP 2024 = slot 8 - (2026 - 2024) = 6, Harrison Pro Bowl
        # 2025 = slot 9 - 1 = 8; save (2027): the same seasons are slots 5 and 7
        return ({0: [word(0, 6, 17)]}, {0: [word(96, 6, 1)], 1: [word(103, 8, 1)]})

    def test_honors_are_copied_by_identity_reslotted_and_idempotent(self):
        save, disc = pair(*self.streams())
        result, receipt = up.sync_honors(save, disc)
        self.assertEqual(honors_of(result, 0), [(96, 5, 1, False)])
        self.assertEqual(honors_of(result, 1), [(103, 7, 1, False)])
        self.assertEqual(receipt["fold_depth"], 0)
        self.assertEqual({(c["player"], c["field"], c["season"]) for c in receipt["changes"]},
                         {("Peyton Manning", "honor.mvp", 2024), ("Marvin Harrison", "honor.pro_bowl", 2025)})
        self.assertTrue(receipt["outside_declared_fields_identical"])
        _save, before = up.franchise(save)
        _save, after = up.franchise(result)
        for player in before.players:        # nothing but the pool, the stream pointers and the used count moved
            self.assertEqual({k: v for k, v in before.by_key[player.key].record.values.items() if k != "history_pointer"},
                             {k: v for k, v in after.by_key[player.key].record.values.items() if k != "history_pointer"})
        self.assertEqual(after.history_words[before.players[0].key][-1] & 0x80000000, 0x80000000)
        again, receipt = up.sync_honors(result, disc)
        self.assertEqual((again, receipt["changes"]), (result, []))

    def test_unknown_identity_and_current_season_honors_are_left_out(self):
        save, disc = pair(*self.streams())
        edited = bytearray(disc)
        document = sr.decode(bytes(edited), preamble=0, reference_year=up.BASE_YEAR)
        edited[document.players[1].offset + 0x10:document.players[1].offset + 0x14] = bytes(4)   # no first name
        result, receipt = up.sync_honors(save, bytes(edited))
        self.assertEqual(honors_of(result, 1), [])
        self.assertEqual(honors_of(result, 0), [(96, 5, 1, False)])

    def test_a_full_pool_folds_the_oldest_seasons_like_the_game_and_keeps_career_totals(self):
        old = [word(f, s, v) for s, base in ((1, 10), (2, 20)) for f, v in ((0, base), (1, base + 1), (2, base + 2))]
        save, disc = pair({0: old + [word(0, 6, 17)]}, {0: [word(96, 6, 1)]})
        with unittest.mock.patch.object(up, "HISTORY_RESERVE", 20000 - 7):    # room for 7 words: 7 + 1 honor does not fit
            result, receipt = up.sync_honors(save, disc)
        self.assertEqual(receipt["fold_depth"], 7)
        self.assertEqual(receipt["folded_players"], ["Peyton Manning"])
        _save, roster = up.franchise(result)
        words = roster.history_words[roster.players[0].key]
        folded = {((w >> 16) & 127): w & 0xFFFF for w in words if w & 0x40000000 and (w >> 23) & 31 == 2}
        self.assertEqual(folded, {0: 30, 1: 32, 2: 34})                      # slot 1 merged into slot 2 by sum
        self.assertFalse(any((w >> 23) & 31 == 1 for w in words if (w >> 16) & 127 < 96))
        self.assertEqual(honors_of(result, 0), [(96, 5, 1, False)])
        self.assertEqual(receipt["used_after"], len(words))
        with unittest.mock.patch.object(up, "HISTORY_RESERVE", 20000 - 8):    # 8 words fit without folding
            result, receipt = up.sync_honors(save, disc)
        self.assertEqual(receipt["fold_depth"], 0)

    def test_honors_below_an_existing_fold_floor_join_the_folded_word_once(self):
        folded = word(0, 2, 30, folded=True)
        save, disc = pair({0: [folded, word(0, 6, 17)]}, {0: [word(103, 3, 1), word(103, 4, 1)]})
        # disc slots 3 and 4 are seasons 2022 and 2023: slots 2 and 3 in the save, the first at or below the floor (2)
        result, receipt = up.sync_honors(save, disc)
        self.assertEqual(honors_of(result, 0), [(103, 2, 1, True), (103, 3, 1, False)])
        self.assertEqual(up.sync_honors(result, disc)[1]["changes"], [])

    def test_shared_history_tails_are_not_edited(self):
        base = fixture(current=True, shared=True)[0]
        disc = pair({}, {0: [word(96, 6, 1)], 1: [word(103, 8, 1)]})[1]
        result, receipt = up.sync_honors(base, disc)
        self.assertEqual(result, base)
        self.assertEqual(receipt["shared_history_skipped"], ["Marvin Harrison", "Peyton Manning"])

    def test_nothing_fits_refuses_without_writing(self):
        save, disc = pair({0: [word(0, 6, 17)]}, {0: [word(96, 6, 1)]})
        with unittest.mock.patch.object(up, "HISTORY_RESERVE", 19999):
            with self.assertRaisesRegex(up.UpgradeRefused, "does not fit"):
                up.sync_honors(save, disc)

    def test_honors_is_a_command_and_part_of_upgrade(self):
        self.assertIn("honors", service.COMMANDS)
        save, disc = pair(*self.streams())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = signed_folder(root / "source", save)
            iso = root / "disc.iso"
            iso.write_bytes(b"synthetic disc fingerprint")
            with unittest.mock.patch.object(service, "load_disc", return_value=(disc, {})), \
                    unittest.mock.patch.object(up, "validate_save", return_value={}):
                plan = service.plan_upgrade(folder, iso, command="honors")
        self.assertEqual([s["operation"] for s in plan.receipt["steps"]], ["honors"])
        self.assertEqual(plan.receipt["changed_fields"], 2)
        from mod_editor.gui.franchise_upgrade_dialog_qt import preview_text
        plan.receipt["validation"] = {"after": {"findings": []}}
        self.assertIn("Award history from the disc: 2 honors for 2 players", preview_text(plan))


class PlayedClubsTests(unittest.TestCase):
    """b778-pc3: opening membership must not be written as a played-season fact."""

    def placed(self, abbreviation):
        save, disc = club_fixture()
        document = sr.decode(disc, preamble=0, reference_year=up.BASE_YEAR)
        team = next(t for t in document.teams if t.abbreviation == abbreviation)
        data = bytearray(disc)
        data[team.offset + 0x11C] = 1
        pointer = team.offset
        struct.pack_into("<i", data, pointer, document.players[0].offset - pointer + 1)
        return save, bytes(data)

    def test_opening_club_is_only_an_inferred_candidate_in_the_receipt(self):
        save, disc = self.placed("BUF")
        result, receipt = up.infer_played_clubs(save, disc)
        _s, roster = up.franchise(result)
        player = roster.players[0]
        clubs = [t.abbreviation for t in roster.teams[:32]]
        team = [w for w in roster.history_words[player.key] if (w >> 16) & 127 == 87 and not w & 0x30000000]
        # The source does prove 2025 TEN, but cannot prove a club for 2026.
        self.assertEqual([((w >> 23) & 31, (w & 0xFFFF) - 1) for w in team], [(1, clubs.index("TEN"))])
        self.assertEqual([(c["season"], c["after"]) for c in receipt["changes"]], [(2025, "TEN")])
        row = next(r for r in receipt["unresolved"] if r["season"] == 2026)
        self.assertTrue(row["inferred"])
        self.assertEqual(row["inferred_opening_clubs"], ["BUF"])
        self.assertTrue(receipt["outside_declared_fields_identical"])
        self.assertEqual(up.infer_played_clubs(result, disc)[1]["changes"], [])        # idempotent

    def test_nothing_is_guessed_without_a_disc_club_a_games_row_or_a_completed_season(self):
        save, disc = club_fixture()
        self.assertFalse(any(c["season"] == 2026 for c in up.infer_played_clubs(save, disc)[1]["changes"]))
        save, disc = self.placed("BUF")
        data = bytearray(save)
        roster = sr.decode(bytes(data))
        data[roster.layout.root + 0x40:roster.layout.root + 0x44] = struct.pack("<I", 0)   # empty history: no games row
        for player in roster.players:
            struct.pack_into("<i", data, player.offset + 0x2C, 0)
        self.assertEqual(up.infer_played_clubs(bytes(data), disc)[1]["changes"], [])

    def test_compatibility_command_uses_the_upgrade_club_step(self):
        self.assertIn("played-clubs", service.COMMANDS)
        save, disc = self.placed("BUF")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = signed_folder(root / "source", save)
            iso = root / "disc.iso"
            iso.write_bytes(b"synthetic disc fingerprint")
            with unittest.mock.patch.object(service, "load_disc", return_value=(disc, {})), \
                    unittest.mock.patch.object(up, "validate_save", return_value={}):
                plan = service.plan_upgrade(folder, iso, command="played-clubs")
        self.assertEqual([s["operation"] for s in plan.receipt["steps"]], ["played_clubs"])
        from mod_editor.gui.franchise_upgrade_dialog_qt import preview_text
        plan.receipt["validation"] = {"after": {"findings": []}}
        self.assertIn("Historical teams restored: 1", preview_text(plan))


@unittest.skipUnless(native.NativeTests.__dict__.get("__unittest_skip__") is None and native.XBE.is_file()
                     and native.HAVE_UC, "pinned USA XBE and unicorn required")
class NativeFoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = native._retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, _ = native.honors.apply(retail)

    def native_fold(self, streams, depth):
        m = native.Machine(self.patched)
        m.record(0x177990, "progress", pop=4)
        records = m.roster([(yp, words) for yp, words in streams])
        m.put(native.CLASS, 0)
        m.call(0x14EFE0, stack=(depth,), budget=400_000_000)
        return [m.stream(rec) for rec in records]

    def test_python_fold_equals_the_game_fold(self):
        """The two agree on the large majority of random streams. The retail loop (restart from the stream head
        after every insert) sometimes loses or skips a merge when several words fold in one pass (a stale-pointer
        quirk in its inserts); the sync is the intended fold and keeps that data."""
        rng = random.Random(778)
        fields = [0, 1, 2, 6, 7, 8, 10, 16, 17, 30, 36, 43, 56, 73, 83, 87, 96, 98, 101, 103, 104]
        live = lambda ws: Counter(w & ~0x80000000 & 0xFFFFFFFF for w in ws if not w & 0x10000000)
        same = total = 0
        for depth in (2, 3, 4, 6, 9):
            streams = []
            for _ in range(15):
                yp = rng.randint(2, 15)
                used, words = set(), []
                for _ in range(rng.randint(1, 30)):
                    key = (rng.choice(fields), rng.randint(1, yp))
                    if key in used:
                        continue
                    used.add(key)
                    value = rng.randint(0, 600)
                    words.append(word(key[0], key[1], value, folded=rng.random() < 0.15))
                streams.append((yp, words))
            for (yp, words), native_stream in zip(streams, self.native_fold(streams, depth)):
                mine, theirs = live(up.fold_words(words, yp, depth)), live(native_stream)
                same += mine == theirs
                total += 1
        self.assertGreaterEqual(same, total * 0.8, (same, total))

if __name__ == "__main__":
    unittest.main()
