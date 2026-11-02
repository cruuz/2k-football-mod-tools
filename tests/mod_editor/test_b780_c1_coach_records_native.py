"""b780 c1-coachdata: the coach record bytes, run through the game's own code in Unicorn.

* FUN_002818D0 (coach record -> the CPU's 216-byte decision statistics): where every tendency byte lands, and that the
  bytes the roster writer authors reach the statistics the CPU reads.
* 0x281D90 + 0x20B670 (the CPU's play pick) on a real retail playbook: the run and pass formation shares steer the
  formation class of the calls.
* The commentary handler at 0x5A390: a coach whose flags have bit 2 is announced with the generic cue 9299, any other
  coach with 9200 + his team's speech id (when that cue exists).

No game routine is replaced.  The hooks only answer lookups around the handler (team pointer, topic kind, cue exists)
and record the cue it queues.  Offline component proof, not a game witness.  Needs the private retail disc
(NFL2K5_RETAIL_XISO) and the unicorn package; each test skips without them."""
from __future__ import annotations

import collections
import os
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
_V08 = Path(os.environ.get("NFL2K5_V08_XISO", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.8 (2026-10-31).xiso.iso"))

try:
    import unicorn  # noqa: F401
except ImportError:                                        # pragma: no cover
    unicorn = None

SEED_MAP = (
    # (record offset, count, stats offset, step, stride of a pair, what the stats hold)
    (0x5A, 6, 0x04, 4, "pair"),            # run percent by score bin: {100, percent}
    (0x60, 1, 0x1C, 4, "pair"),            # red zone
    (0x61, 4, 0x20, 4, "pair"), (0x65, 4, 0x30, 4, "pair"),     # downs 1 and 2 by to-go bin
    (0x69, 4, 0x40, 4, "pair"), (0x6D, 4, 0x50, 4, "pair"),     # downs 3 and 4
    (0x71, 5, 0x62, 2, "words"),           # pass lateral zones
    (0x76, 4, 0x6C, 2, "words"),           # pass depth zones
    (0x7A, 4, 0x74, 2, "words"),           # receiver roles
    (0x7E, 5, 0x7C, 2, "words"),           # RUN LANES
    (0x83, 5, 0x88, 2, "words"),           # run formation classes 1..5
    (0x88, 5, 0x94, 2, "words"),           # pass formation classes 1..5
    (0x8D, 11, 0x9E, 2, "words"),          # run category weights
    (0x98, 11, 0xB4, 2, "words"),          # pass category weights
)


def _xbe(path: Path) -> bytes:
    from mod_editor.core.mod_build import _xbe_bytes
    return _xbe_bytes(path)


@unittest.skipUnless(_XISO.is_file() and unicorn is not None, "retail disc or unicorn absent")
class SeedRoutineTests(unittest.TestCase):
    """FUN_002818D0 on authored coach records."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_play_scoring as scoring
        cls.scoring = scoring
        cls.xbe = _xbe(_XISO)
        cls.base = rr.load_image(_XISO).to_body()
        cls.roster = rr.RosterDocument(cls.base)

    def seeded(self, record: bytes) -> bytes:
        world = self.scoring.NativeScorer(self.xbe)
        at = self.scoring.SOURCE + 0x1D000
        world.m.mem_write(at, bytes(record))
        stats = self.scoring.META + 0x800
        world.m.mem_write(stats, bytes(0xD8))
        world.call(0x2818D0, ecx=stats, edx=at)
        return bytes(world.m.mem_read(stats, 0xD8))

    def test_every_tendency_byte_lands_where_the_map_says(self) -> None:
        rng = random.Random(20261102)
        record = bytearray(rng.randrange(1, 100) for _ in range(rr.COACH_RECORD_SIZE))
        stats = self.seeded(record)
        words = lambda at, n=1: struct.unpack_from(f"<{n}H", stats, at)
        self.assertEqual(words(0, 2), (100 - record[0x59], record[0x59]), "pass and run weights")
        for at, count, dest, step, kind in SEED_MAP:
            for i in range(count):
                if kind == "pair":
                    self.assertEqual(words(dest + step * i, 2), (100, record[at + i]), f"+0x{at + i:X}")
                else:
                    self.assertEqual(words(dest + step * i)[0], record[at + i], f"+0x{at + i:X}")
        self.assertEqual(words(0x60)[0], 100)
        self.assertEqual(words(0xCA)[0], record[0xA3] * words(0)[0] // 100, "motion on passes, scaled by the pass weight")
        self.assertEqual(words(0xCC)[0], record[0xA4] * words(2)[0] // 100, "motion on runs, scaled by the run weight")
        self.assertEqual(words(0xCE, 3), (100, record[0xA5], 100), "no huddle roll")
        self.assertEqual(words(0xD4)[0], record[0xA6])
        self.assertEqual(words(0xD6)[0], record[0xA7])

    def test_the_authored_groups_reach_the_statistics(self) -> None:
        tendencies = {"run_share": 34, "run_by_score": [30, 31, 32, 33, 34, 35], "run_redzone": 41,
                      "run_by_down_distance": list(range(40, 56)), "run_lane": [20, 25, 30, 15, 10],
                      "formation_run": [5, 0, 10, 80, 5], "formation_pass": [82, 0, 3, 15, 0], "no_huddle": 3,
                      "personnel_run": [1, 14, 3, 32, 4, 3, 36, 1, 0, 5, 1], "personnel_pass": [1, 7, 1, 29, 1, 1, 35, 1, 0, 23, 1]}
        new, receipt = rr.apply_body(self.base, {"schema": rr.EDITS_SCHEMA, "edits": [],
                                                  "coaches": [{"team": "KC", "tendencies": tendencies}]})
        self.assertEqual(receipt["log"], [])
        kc = next(t for t in rr.RosterDocument(new).teams if t.abbreviation == "KC")
        stats = self.seeded(new[kc.coach_offset: kc.coach_offset + rr.COACH_RECORD_SIZE])
        words = lambda at, n=1: struct.unpack_from(f"<{n}H", stats, at)
        self.assertEqual(words(0, 2), (66, 34), "pass 66, run 34")
        self.assertEqual([words(4 + 4 * i, 2)[1] for i in range(6)], [30, 31, 32, 33, 34, 35])
        self.assertEqual(words(0x1C, 2), (100, 41))
        self.assertEqual([words(0x20 + 4 * i, 2)[1] for i in range(16)], list(range(40, 56)))
        self.assertEqual(words(0x7C, 5), (20, 25, 30, 15, 10))
        self.assertEqual(words(0x88, 5), (5, 0, 10, 80, 5), "run formation shares: gun, split, I, one back, empty")
        self.assertEqual(words(0x94, 5), (82, 0, 3, 15, 0), "pass formation shares")
        self.assertEqual(words(0xCE, 3), (100, 3, 100))
        self.assertEqual(words(0x9E, 11), tuple(tendencies["personnel_run"]), "personnel package weights of run calls")
        self.assertEqual(words(0xB4, 11), tuple(tendencies["personnel_pass"]), "personnel package weights of pass calls")
        # a coach record the plan does not mention keeps the bytes the old coach had
        old = self.base[kc.coach_offset + 0x71: kc.coach_offset + 0x7E]
        self.assertEqual(new[kc.coach_offset + 0x71: kc.coach_offset + 0x7E], old)


@unittest.skipUnless(_XISO.is_file() and unicorn is not None, "retail disc or unicorn absent")
class FormationSteerTests(unittest.TestCase):
    """0x281D90 (game plan) + 0x20B670 (CPU play pick) on the Chiefs' retail book: the formation shares steer the calls."""

    SAMPLES = 24
    POOLS = (3, 9, 14)          # 1st & 10 / 3rd & 1 / 3rd & 10 style situations (nfl2k5_vip's pool settings)

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_play_scoring as scoring, nfl2k5_playbook_inspector as inspector
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from pb.scoring_selectors import World
        from pb.verify_league import BOOK_ENTRIES, OuterImage
        cls.scoring, cls.inspector, cls.World = scoring, inspector, World
        cls.xbe = _xbe(_XISO)
        cls.classes = list(XbeImage(cls.xbe).read(0xAC9EE0, 256))
        with OuterImage(str(_XISO)) as archive:
            cls.book = archive.read_entry(BOOK_ENTRIES["KC"])

    @staticmethod
    def situation(index: int) -> dict:
        group, score = divmod(index, 3)
        distance, urgent = divmod(group, 2)
        down, yards = ((1, 10), (3, 1), (3, 10))[distance]
        return dict(down=down, distance=yards, yard=50, margin=(7, -7, 0)[score], quarter=4 if score == 0 else 2,
                    seconds=60 if urgent else 300)

    def calls(self, record: bytes) -> collections.Counter:
        s, ip = self.scoring, self.inspector
        world = self.World(self.xbe)
        world.load(self.book)
        at = s.SOURCE + 0x1D000
        world.m.mem_write(at, bytes(record))
        world.call(0x2818D0, ecx=s.META + 0x800, edx=at)
        counts: collections.Counter = collections.Counter()
        for pool in self.POOLS:
            rng = random.Random(20261102 + pool)
            world.put(0xE5FCA0, 54)
            world.put(0xE5FCA4, 23)
            for i in range(110):
                world.put(0xE5FCA8 + i * 4, rng.getrandbits(32))
            for _ in range(self.SAMPLES):
                world.configure(**self.situation(pool))
                world.fput(0xBF1484, rng.random())
                world.call(0x281D90)
                world.m.mem_write(0xBF16F8, bytes(world.m.mem_read(0xC5D4B0, 4)))
                out = s.SOURCE + 0x19100
                world.m.mem_write(out, bytes(16))
                world.call(0x20B670, ecx=s.TEAM, edx=out)
                _, formation, play, _ = struct.unpack("<4I", world.m.mem_read(out, 16))
                if not formation:
                    continue
                fi = (formation - s.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE
                pi = (play - s.BOOK - ip.PLAY_BASE) // ip.PLAY_SIZE
                flags = world.book.plays[pi].flags_or_id
                kind = "pass" if flags & 0x2000 and not flags & 0x8000 else "run" if flags & 0x8000 and not flags & 0x2000 else "other"
                formation_class = self.classes[world.get(formation + 0x18) & 0xFFFF]
                if kind != "other" and formation_class:
                    counts[kind, formation_class] += 1
        return counts

    def record(self, run: list[int], passes: list[int]) -> bytes:
        entry = {"team": "KC", "tendencies": {"run_share": 50, "formation_run": run, "formation_pass": passes}}
        new, _ = rr.apply_body(rr.load_image(_XISO).to_body(), {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": [entry]})
        kc = next(t for t in rr.RosterDocument(new).teams if t.abbreviation == "KC")
        return new[kc.coach_offset: kc.coach_offset + rr.COACH_RECORD_SIZE]

    def test_run_and_pass_formation_shares_steer_the_formation_class(self) -> None:
        gun_runs = self.calls(self.record([100, 0, 0, 0, 0], [0, 0, 0, 100, 0]))
        back_runs = self.calls(self.record([0, 0, 0, 100, 0], [100, 0, 0, 0, 0]))

        def share(counts, kind, formation_class):
            total = sum(n for (k, _c), n in counts.items() if k == kind)
            return counts[kind, formation_class] / total if total else 0.0

        self.assertGreater(sum(gun_runs.values()), 20)
        self.assertGreater(sum(back_runs.values()), 20)
        # The class weights choose among the classes the chosen playbook category offers, so a profile cannot force a
        # class the book's category lacks (a gun-only run profile still lands about half its runs from one back).
        # The calls are seeded and the game's code is deterministic, so these margins are stable: measured on the
        # Chiefs' retail book, gun-only run profile 11 of 23 runs from gun and 9 from one back, one-back-only profile
        # 0 from gun and 24 of 27 from one back; passes 28 of 44 from gun for the gun profile and 0 for the other.
        self.assertGreater(share(gun_runs, "run", 1), share(back_runs, "run", 1) + 0.3, (gun_runs, back_runs))
        self.assertGreater(share(back_runs, "run", 4), share(gun_runs, "run", 4) + 0.3, (gun_runs, back_runs))
        self.assertGreater(share(back_runs, "pass", 1), share(gun_runs, "pass", 1) + 0.4, (gun_runs, back_runs))
        self.assertGreater(share(gun_runs, "pass", 4), share(back_runs, "pass", 4) + 0.4, (gun_runs, back_runs))


@unittest.skipUnless(_XISO.is_file() and unicorn is not None, "retail disc or unicorn absent")
class AnnouncerTests(unittest.TestCase):
    """The commentary handler at 0x5A390 picks the coach-name cue."""

    GENERIC = 9299

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_commentary_final as final
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core import nfl2k5_playbook_pack as packs
        cls.xbe = _xbe(_XISO)
        cls.image = XbeImage(cls.xbe)
        with packs._outer_image().OuterImage(str(_XISO)) as archive:
            entry = archive.read_entry(3)
        at = final.find_table(entry)
        cls.cues = {i for i in final.ids(entry[at: at + final.SPCI_SIZE]) if 9100 <= i < 9500}

    def run_handler(self, speech: int, flags: int, existing: set[int]) -> dict:
        import unicorn as uc
        from unicorn import x86_const as r
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        m.mem_map(0x10000, 0xF00000)
        for section in self.image.sections:
            if section.raw_size:
                m.mem_write(section.start, self.image.read(section.start, section.raw_size))
        scratch, stack = 0x1100000, 0x1200000
        m.mem_map(scratch, 0x10000)
        m.mem_map(stack - 0x10000, 0x20000)
        team, coach, banks = scratch + 0x1000, scratch + 0x2000, scratch + 0x4000
        m.mem_write(team + 0x154, struct.pack("<H", speech))
        m.mem_write(team + 0x14C, struct.pack("<I", coach))
        m.mem_write(coach + 0x1A, bytes((flags,)))
        m.mem_write(0xB29AE8, struct.pack("<I", banks))
        m.mem_write(banks, struct.pack("<III", 0, banks + 0x100, banks + 0x200))
        seen = {"asked": [], "queued": []}

        def leave(mu, value, pop):
            sp = mu.reg_read(r.UC_X86_REG_ESP)
            mu.reg_write(r.UC_X86_REG_EAX, value)
            mu.reg_write(r.UC_X86_REG_EIP, struct.unpack("<I", mu.mem_read(sp, 4))[0])
            mu.reg_write(r.UC_X86_REG_ESP, sp + 4 + pop)

        def asked(mu, *_):
            cue = mu.reg_read(r.UC_X86_REG_EDX)
            seen["asked"].append(cue)
            leave(mu, int(cue in existing), 12)

        def queued(mu, *_):
            sp = mu.reg_read(r.UC_X86_REG_ESP)
            seen["queued"].append(struct.unpack("<I", mu.mem_read(sp + 4, 4))[0])
            leave(mu, 0, 12)

        for pc, hook in ((0x61C50, lambda mu, *_: leave(mu, team, 0)), (0xA9540, lambda mu, *_: leave(mu, 2, 0)),
                         (0xDB370, asked), (0xC31C0, queued), (0xC3060, queued)):
            m.hook_add(uc.UC_HOOK_CODE, hook, begin=pc, end=pc)
        frame = stack - 0x100
        m.mem_write(frame, struct.pack("<IIII", 0, 0xDEAD0000, 0x1234, 1))
        m.mem_write(frame - 12, bytes(12))
        for name, value in (("ESP", frame - 12), ("EBP", frame), ("EDI", team), ("ESI", 0), ("EBX", 0), ("EDX", 0),
                            ("ECX", 0), ("EAX", 0)):
            m.reg_write(getattr(r, "UC_X86_REG_" + name), value)
        m.emu_start(0x5A390, 0xDEAD0000, count=2000)
        return seen

    def test_the_retail_bank_has_the_coach_cues_the_research_listed(self) -> None:
        wanted = {9204, 9206, *range(9208, 9218), 9219, *range(9221, 9229), 9230, 9237, self.GENERIC}
        self.assertEqual(self.cues & wanted, wanted)

    def test_a_flagged_coach_is_announced_with_the_generic_line(self) -> None:
        for speech in (4, 6, 12, 16, 17, 30, 31):
            for flags in (0x02, 0x06):
                seen = self.run_handler(speech, flags, self.cues)
                self.assertEqual(seen["queued"], [self.GENERIC], (speech, flags, seen))
                self.assertEqual(seen["asked"][0], self.GENERIC, "the flag decides before any club cue is asked for")

    def test_an_unflagged_coach_keeps_his_club_cue_when_it_exists(self) -> None:
        for speech in (4, 6, 8, 12, 16, 17, 21, 28, 30):
            if 9200 + speech in self.cues:
                seen = self.run_handler(speech, 0x00, self.cues)
                self.assertEqual(seen["queued"], [9200 + speech], (speech, seen))
                self.assertEqual(self.run_handler(speech, 0x04, self.cues)["queued"], [9200 + speech], "other bits do not matter")
        for speech in (5, 7, 31):
            self.assertNotIn(9200 + speech, self.cues, "the 2004 offseason hires have no name cue")
            self.assertEqual(self.run_handler(speech, 0x00, self.cues)["queued"], [self.GENERIC])


@unittest.skipUnless(_XISO.is_file() and _V08.is_file(), "retail or v0.8 disc absent")
class ReleasedExecutableTests(unittest.TestCase):
    def test_the_released_executable_keeps_the_retail_bytes_these_proofs_ran_on(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        retail, released = XbeImage(_xbe(_XISO)), XbeImage(_xbe(_V08))
        for va, size, label in ((0x2818D0, 0x1B1, "FUN_002818D0 coach record seeding"),
                                (0x281D90, 0x200, "game plan 0x281D90 (first 512 bytes)"),
                                (0x280D10, 0x80, "score bin selector"), (0x280F30, 0x170, "formation class selector"),
                                (0x5A37D, 0xC8, "coach name cue handler"), (0xAC9EE0, 0x80, "formation class table")):
            self.assertEqual(released.read(va, size), retail.read(va, size), label)


if __name__ == "__main__":
    unittest.main()
