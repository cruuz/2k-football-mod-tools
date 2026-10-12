"""Franchise event replay, not a played game or an awards-screen witness.

The actual game commit, week-complete predicate, award dispatcher, season winner
selectors, history writer/fold and Player Card draw run in Unicorn. Football,
weekly TV highlights, coaching and UI exit are explicit input boundaries.
No annual winner, honor word, award date or page result is supplied by a stub.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_honors as honors
from mod_editor.core import nfl2k5_season_length as season
from tests.mod_editor.test_nfl2k5_honors import (
    Machine, _retail, HAVE_UC, XBE, word, honors_in,
    CARD_PLAYER, SEASONS, LEAGUE_MODE, STAGE, WEEK, CELL, CLASS, AWARDS, LEAGUE_TEAMS, ROSTER,
)

V06 = Path(os.environ.get("B771_V1I_XBE", "/nonexistent/v06_default.xbe"))
V06_ROST = Path(os.environ.get("B771_V1I_ROST", "/nonexistent/v06_main.ROST"))


class SeasonMachine(Machine):
    """Existing F5 harness with address-specific callbacks for large native loops."""

    TEAMS = Machine.HEAP + 0x10000  # leave room for a full-pool roster

    def __init__(self, payload):
        super().__init__(payload)
        self.uc.hook_del(self._dispatch_handle)
        self._registered = set()
        self.reg("FPCW", 0x37F)
        self.events = []
        self.image = payload
        self.at = honors.labels(honors.allocations(payload)["code"]["va"])
        self.state = honors.allocations(payload)["data"]["va"]
        for name in ("honors_season_hook", "honors_sb_hook", "honors_fold_rule"):
            self.uc.hook_add(self.u.UC_HOOK_CODE,
                             lambda _u, _a, _s, _d, name=name: self.events.append((name, self.get(WEEK))),
                             begin=self.at[name], end=self.at[name])

    def hook(self, va, fn, pop=0):
        super().hook(va, fn, pop)
        if va not in self._registered:
            self._registered.add(va)
            self.uc.hook_add(self.u.UC_HOOK_CODE, self._dispatch, begin=va, end=va)

    def call(self, *args, **kwargs):
        kwargs.setdefault("budget", 100_000_000)
        return super().call(*args, **kwargs)

    def league(self, *, seeded=False, empty=False):
        positions = (0, 7, 3, 9, 12, 16, 11, 4, 1, 2, 8, 15)
        self.players = self.roster([
            (1 if i in (1, 5) else 5,
             [] if empty else [word(0, 0 if i in (1, 5) else 4, 17)] +
             ([word(103, 4, 1)] if seeded and i not in (1, 5) else []))
            for i in range(len(positions))])
        for i, (p, pos) in enumerate(zip(self.players, positions)):
            self.put8(p + 0x35, pos)
            # A signed player: 3-year contract with 2 years left. Retail's
            # rollover prices every rostered contract through 0xE6380, which
            # divides by the length nibble, so a zero contract faults there.
            self.put(p + 0x24, self.get(p + 0x24) | 0x03000002)
            self.put(self.TEAMS + i * 4, p)
        self.put8(self.TEAMS + 0x11C, len(positions))
        self.put(self.ROOT + 0x1C, self.TEAMS)
        self.put(LEAGUE_MODE, 2)
        self.put(0xE576AC, 32)
        self.put(CLASS, 0)
        for i in range(34):
            self.put(LEAGUE_TEAMS + i * 4, self.TEAMS + i * 0x1F4)
        # Every row has a real fixture and sixteen empty cells. Empty cells are
        # type 6; the native completion predicate must inspect the fixture.
        for row in range(22):
            for cell in range(17):
                self.uc.mem_write(0xE57C40 + (row * 17 + cell) * 8,
                                  bytes((1 if cell == 0 else 6, 0, 1, 9, 1, 26, 12, 0)))
        # In-game teams are input to the commit, distinct from league records.
        self.live_teams = (0xB30864, 0xB30A58)
        for i, live in enumerate(self.live_teams):
            self.put(live + 0x14C, self.HEAP + 0x78000 + i * 0x100)
        # These boundaries do not set season awards or history. Annual winner
        # selection, season-stat reads and every F5 path run without stubs.
        for va, pop in ((0x1151F0, 8), (0x1159E0, 0), (0x27DBC0, 0),
                        (0x27DF30, 0), (0x2AC520, 0), (0x134DD0, 8),
                        (0x134D40, 4), (0x73770, 0)):
            self.hook(va, lambda m: 0, pop)
        # The game's SB selection routine stores a translated live-player
        # pointer. Supply its game-performance winner, not the award slot.
        self.live_mvp = 0xB30C4C
        self.put(self.live_teams[0], self.live_mvp)
        self.put8(self.live_teams[0] + 0x11C, 1)
        self.put8(self.live_teams[1] + 0x11C, 0)
        self.hook(0x115170, lambda m: m.put(0xBA3D44, m.live_mvp))
        # Only team-score queries are external game inputs. Run a tiny x87
        # return thunk so the native quarter-score stores and sums execute.
        self.points = (27, 20)
        self.uc.mem_write(self.STOP + 0x100, b"\xd9\x05" + struct.pack("<I", self.STOP + 0x200) + b"\xc2\x04\x00")
        self.uc.hook_add(self.u.UC_HOOK_CODE, self._game_score, begin=0xCB2D0, end=0xCB2D0)

    def _game_score(self, _uc, _va, _size, _data):
        if self.reg("EDX") != 0x5B:
            raise AssertionError("unexpected non-score team statistic")
        team = self.live_teams.index(self.reg("ECX"))
        bank = self.get(self.reg("ESP") + 4)
        value = self.points[team] if bank in (0, 1) else 0
        self.uc.mem_write(self.STOP + 0x200, struct.pack("<f", value))
        self.reg("EIP", self.STOP + 0x100)

    def season_stats(self, week):
        for i, p in enumerate(self.players):
            self.put(CLASS, 0)
            for field, value in ((0, week + 1), (2, 100 * (week + 1) + i),
                                 (3, 2 * (week + 1)), (10, 50 * (week + 1) + i)):
                self.call(0x14F430, ecx=p, edx=field, stack=(value,))

    def weekly_results(self):
        # Explicit weekly-selection inputs. The real dispatcher archives them;
        # annual selectors and all career-history writers remain native.
        for category in range(3):
            for rank in range(3):
                self.put(AWARDS + 0x35F0 + category * 0x48 + rank * 0x18,
                         self.players[category * 3 + rank])
        for i in range(4):
            self.put(AWARDS + 0x35F0 + 0xD8 + i * 0x60, self.players[i])

    def check_weekly_archive(self, week):
        for category in range(3):
            for rank in range(3):
                actual = self.get(AWARDS + 0x3908 + category * 0x108 + week * 12 + rank * 4)
                if actual != self.players[category * 3 + rank]:
                    raise AssertionError("weekly ranking archive mismatch")
        row = AWARDS + 0x3C20 + week * 0x144
        if self.get(row) != 4:
            raise AssertionError("weekly highlight archive count mismatch")
        for i in range(4):
            if self.get(row + 4 + i * 0x50) != self.players[i]:
                raise AssertionError("weekly highlight player mismatch")
        if row + 0x144 > AWARDS + 0x57F8:
            raise AssertionError("weekly archive crossed annual awards")

    def game(self, week, *, stage=8, complete=True, budget=100_000_000):
        self.put(STAGE, stage)
        self.put(WEEK, week)
        self.put(CELL, 0)
        self.put8(0xE57C40 + week * 17 * 8 + 8, 6 if complete else 1)
        self.call(0x1356C0, ecx=0xE57C40 + week * 17 * 8, budget=budget)
        self.put8(0xE57C40 + week * 17 * 8, 3)

    def page(self, player):
        self.capture_text()
        # Supply the UI list and cursor; let the real selector fetch its player
        # pointer into C90248 before the real card draw reads player+0x2C.
        self.put(self.SCREEN + 0x40, self.SCREEN + 0x100)
        self.put(self.SCREEN + 0xA4, 1)
        self.put(self.SCREEN + 0x100, player)
        self.hook(0x6E2D0, lambda m: 0)
        self.hook(0xF31B0, lambda m: m.SCREEN)
        self.hook(0x170510, lambda m: 0)
        self.call(0x320DA0, eax=self.SCREEN)
        if self.get(CARD_PLAYER) != player:
            raise AssertionError("native card selection changed the player pointer")
        self.put(self.state, 1)
        self.text.clear()
        for va in (0x3208E0, 0x320640, 0x35B9C0):
            self.hook(va, lambda m: 0)
        self.call(0x320B70)
        return ({label[0]: value[0] for label, value in zip(self.text[:20:2], self.text[1:20:2])},
                [t[0] for t in self.text[20:]])


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA XBE and Unicorn required")
class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.source_payload = honors.apply(season.apply(retail)[0])[0]
        cls.payload = season.repair_awards_timing(V06.read_bytes())[0] if V06.is_file() else cls.source_payload
        cls.year = struct.unpack_from("<I", cls.payload, 0x3204AD - 0x10000)[0] - 11

    def machine(self, payload=None, **kwargs):
        m = SeasonMachine(self.payload if payload is None else payload)
        m.league(**kwargs)
        return m

    def test_full_regular_season_writers_and_page_two(self):
        for seeded, empty in ((True, False), (False, False), (False, True)):
            with self.subTest(seeded=seeded, empty=empty):
                m = self.machine(seeded=seeded, empty=empty)
                for week in range(18):
                    m.season_stats(week)
                    m.weekly_results()
                    m.game(week, complete=False)
                    self.assertFalse(any(e[0] == "honors_season_hook" for e in m.events))
                    m.game(week)
                    m.check_weekly_archive(week)
                    if week < 17:
                        self.assertFalse(any(e[0] == "honors_season_hook" for e in m.events))
                self.assertEqual([e for e in m.events if e[0] == "honors_season_hook"],
                                 [("honors_season_hook", 17)])
                self.assertFalse(any(e[0] == "honors_fold_rule" for e in m.events))
                for off, name in honors.SEASON_SLOTS:
                    p = m.get(AWARDS + off)
                    self.assertIn(p, m.players, name)
                    slot = (m.get(p + 0x24) >> 8) & 31
                    self.assertEqual(honors_in(m.stream(p))[(honors.FIELDS[name], slot)], (1, False))
                    counts, years = m.page(p)
                    self.assertGreaterEqual(int(counts[honors.LABELS_SHOWN[honors.HONORS.index(name)]]), 1)
                    self.assertIn(str(self.year), " ".join(years))
                # Duplicate presentation/commit cannot increment these honors.
                used = m.get(m.ROOT + 0x40)
                before = [honors_in(m.stream(p)) for p in m.players]
                m.game(17)
                self.assertEqual([honors_in(m.stream(p)) for p in m.players], before)
                self.assertEqual(m.get(m.ROOT + 0x40), used)

    def test_playoffs_and_actual_super_bowl_commit(self):
        m = self.machine()
        for week in range(18, 22):
            m.game(week, stage=9)
            for p in m.players:
                self.assertEqual(m.page(p)[0]["SUPER BOWLS"], "1" if week == 21 else "0")
        # 1167D0 performs the live-to-league mapping into +5888 itself.
        self.assertEqual(m.get(AWARDS + 0x5888), m.players[0])
        self.assertEqual(m.page(m.players[0])[0]["SB MVP"], "1")
        self.assertIn(str(self.year), m.page(m.players[0])[1])

    def test_final_week_statistics_can_change_the_mvp(self):
        m = self.machine()
        challenger = m.players[2]
        m.put8(challenger + 0x35, 0)  # second synthetic quarterback
        m.season_stats(16)
        for field, value in ((2, 1), (3, 0)):
            m.call(0x14F430, ecx=challenger, edx=field, stack=(value,))
        m.game(16)
        self.assertEqual(m.get(AWARDS + 0x5800), 0)
        for field, value in ((2, 30000), (3, 150)):
            m.call(0x14F430, ecx=challenger, edx=field, stack=(value,))
        m.game(17)
        self.assertEqual(m.get(AWARDS + 0x5800), challenger)
        self.assertEqual(m.page(challenger)[0]["MVP"], "1")

    def test_source_build_uses_the_same_final_week_and_accepts_shipped_upgrade(self):
        self.assertEqual(self.source_payload[season.AWARDS_WEEK_VA - 0x10000], 17)
        self.assertEqual(honors.status(self.source_payload), "applied")
        self.assertEqual(honors.status(self.payload), "applied")
        self.assertEqual(season.repair_awards_timing(self.payload)[0], self.payload)

    @unittest.skipUnless(V06_ROST.is_file(), "B771_V1I_ROST enables the real shipped roster")
    def test_real_shipped_roster_loads_seeded_honors_on_the_native_page(self):
        from mod_editor.core import nfl2k5_team_history as history
        resource = V06_ROST.read_bytes()
        self.assertEqual(hashlib.sha256(resource).hexdigest(),
                         "d50958ccd181e5c9b466e9cd75323105a20fa9909f90a541fd029e180c765e5e")
        body = resource[32:32 + history.BODY_SIZE]
        parsed = history.parse_body(body)
        self.assertEqual((parsed.player_count, parsed.used), (2619, 34462))
        m = SeasonMachine(self.payload)
        base = 0x3200000
        m.uc.mem_map(base, 0x100000)
        m.uc.mem_write(base, body)
        m.put(ROSTER, base + history.OBJ_OFF)
        for va in (0x10E9D0, 0x10E990):
            m.hook(va, lambda m: 0)  # post-load team/cache refresh
        m.call(0xC0500, ecx=base + history.OBJ_OFF)
        seen, total = set(), 0
        for player in parsed.players:
            fields = Counter()
            for (field, _slot), (value, _folded) in honors_in(player.entries).items():
                fields[field] += value
                total += value
            self.assertEqual(m.stream(base + player.offset), list(player.entries))
            if fields.keys() - seen:
                counts, _years = m.page(base + player.offset)
                for field in range(96, 106):
                    self.assertEqual(int(counts[honors.LABELS_SHOWN[field - 96]]), fields[field])
                seen.update(fields)
        self.assertEqual(seen, set(range(96, 106)))
        self.assertEqual(total, 1167)

    def test_second_season_capacity_fold_and_native_save_reload(self):
        m = self.machine(seeded=True)
        for week in range(18):
            m.season_stats(week)
            m.game(week)
        p = m.get(AWARDS + 0x5800)
        # Two old, synthetic MVP seasons exercise sum folding as well as the
        # two newly earned seasons. The native history setter writes all four.
        for slot in (1, 2):
            m.call(0x14F3B0, ecx=p, edx=96, stack=(slot, 1))
        for week in range(18, 22):
            m.game(week, stage=9)
        m.hook(0x31E210, lambda m: 0)  # draft order, as in f12_rollover_proof
        m.hook(0x2BFBE0, lambda m: 0)  # CPU cap cuts
        m.put(0xE576AC, 34)
        m.call(0x247B40)              # real years-pro increment and postseason wipe
        self.assertEqual((m.get(STAGE), m.get(SEASONS)), (1, 1))
        self.assertEqual(m.page(p)[0]["MVP"], "3")
        self.assertIn(str(self.year), " ".join(m.page(p)[1]))
        m.put(0xE576AC, 32)
        for week in range(18):
            m.season_stats(week)
            m.game(week)
        self.assertEqual(m.get(AWARDS + 0x5800), p)
        self.assertEqual(m.page(p)[0]["MVP"], "4")
        self.assertIn(str(self.year + 1), " ".join(m.page(p)[1]))
        # A valid full 50,000-word pool: unique stat/slot pairs on additional
        # allocated players, outside club rosters. The next SB honor must make
        # the real append routine call the fold, without a direct fold call.
        rows = [((m.get(q + 0x24) >> 8) & 31,
                 [w & 0x7FFFFFFF for w in m.stream(q)]) for q in m.players]
        rows.append((6, [word(field, slot, 1) for slot in (1, 2) for field in range(15)]))
        remaining = 50_000 - sum(len(ws) for _, ws in rows)
        # Current-season filler gives the native fold a few old words to merge,
        # instead of making its O(pool size) compactor run 50,000 times.
        filler = [word(field, 6, 1) for field in range(80)]
        while remaining:
            n = min(remaining, len(filler))
            rows.append((6, filler[:n]))
            remaining -= n
        m.roster(rows)
        m.hook(0x177990, lambda m: 0, 4)  # progress callback only
        m.hook(0x38F50, lambda m: 0)      # progress/UI yield only
        m.events.clear()
        m.put(CLASS, 1)
        m.game(21, stage=9, budget=500_000_000)
        self.assertTrue(any(e[0] == "honors_fold_rule" for e in m.events))
        self.assertLess(m.get(m.ROOT + 0x40), 50_000)
        self.assertEqual(m.get(CLASS), 1)
        counts, years = m.page(p)
        self.assertEqual((counts["MVP"], counts["SUPER BOWLS"]), ("4", "2"))
        folded = [w for w in m.stream(p) if ((w >> 16) & 127) == 96 and w & 0x40000000]
        self.assertEqual([w & 65535 for w in folded], [2])
        # Native roster serialization/relocation, fresh machine and base.
        m.call(0xC0730, ecx=m.ROOT)
        saved = bytes(m.uc.mem_read(m.ROOT, 0x80000))
        fresh = SeasonMachine(self.payload)
        base = 0x3200000
        fresh.uc.mem_map(base, 0x80000)
        fresh.uc.mem_write(base, saved)
        fresh.put(ROSTER, base)
        fresh.put(SEASONS, 1)
        for va in (0x10E9D0, 0x10E990):
            fresh.hook(va, lambda m: 0)  # team/cache refresh after relocation
        fresh.call(0xC0500, ecx=base)
        self.assertEqual(fresh.page(base + p - m.ROOT), (counts, years))

    def test_regular_postgame_merge_does_not_erase_honors(self):
        m = self.machine()
        m.season_stats(17)
        m.game(17)
        p = m.get(AWARDS + 0x5800)
        before = honors_in(m.stream(p))
        # Full native player merge. It expects a game stat context through
        # live+0x30; a zero game supplies no additional ordinary stats.
        live = 0xB30C4C
        m.uc.mem_write(live, bytes(m.uc.mem_read(p, 0x54)))
        m.put(live + 0x30, m.HEAP + 0x70000)
        m.put(m.HEAP + 0x70000, m.HEAP + 0x71000)
        m.call(0xCA7B0, stack=(0, 0))  # install the native game-stat context getter
        m.call(0x1334B0, eax=p, stack=(live, 0))
        self.assertEqual(honors_in(m.stream(p)), before)
        self.assertEqual(m.page(p)[0]["MVP"], "1")

    def test_no_supported_awards_are_backfilled_just_by_opening_old_save(self):
        m = self.machine()
        m.put(SEASONS, 8)
        before = m.get(m.ROOT + 0x40)
        for p in m.players:
            counts, years = m.page(p)
            self.assertEqual(set(counts.values()), {"0"})
            self.assertEqual(years, ["HONORS:", "NONE YET"])
        self.assertEqual(m.get(m.ROOT + 0x40), before)

    @unittest.skipUnless(V06.is_file(), "B771_V1I_XBE enables the shipped negative control")
    def test_shipped_negative_control_awards_are_a_week_early(self):
        m = self.machine(V06.read_bytes())
        for week in range(18):
            m.season_stats(week)
            m.game(week)
        self.assertEqual([e for e in m.events if e[0] == "honors_season_hook"],
                         [("honors_season_hook", 16)])


if __name__ == "__main__":
    unittest.main()
