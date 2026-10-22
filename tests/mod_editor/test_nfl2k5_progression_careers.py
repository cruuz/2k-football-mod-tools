"""b778 pg1: NFL career arcs in nfl2k5_progression (retirement base years, the in-place form routine 0x2BE0F0 and the
aging hook 0xE6488).

The real form routine, aging routine and Player Progress un-aging run in Unicorn on the retail and the patched
executables over a synthetic league (random ratings, years pro, form levels and last-season stats). No game boot.
The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_progression as p
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

WORLD, STACK, SENTINEL = 0x03000000, 0x03800000, 0x03F00000
STAT_AGO = 0x0014EF20
SAVED = ("EBX", "EBP", "ESI", "EDI")


class Emu:
    """The executable mapped in Unicorn, a league object at [0xB72918] and a mocked last-season stat reader."""

    def __init__(self, payload):
        self.m = m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({va for s in image.sections
                        for va in range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096)})
        start = prev = None
        for va in pages + [None]:
            if va is not None and prev is not None and va == prev + 4096:
                prev = va
                continue
            if start is not None:
                m.mem_map(start, prev + 4096 - start)
            start = prev = va
        for s in image.sections:
            if s.raw_size:
                m.mem_write(s.start, image.read(s.start, s.raw_size))
        m.mem_map(WORLD, 0x400000)
        m.mem_map(STACK, 0x100000)
        m.mem_map(SENTINEL, 0x1000)
        m.mem_write(SENTINEL, b"\xf4")
        self.stats = {}
        m.hook_add(uc.UC_HOOK_CODE, self._stat, begin=STAT_AGO, end=STAT_AGO)

    def _stat(self, m, _address, _size, _data):
        esp = m.reg_read(x86.UC_X86_REG_ESP)
        ret, ago = struct.unpack("<II", m.mem_read(esp, 8))
        key = (m.reg_read(x86.UC_X86_REG_ECX), m.reg_read(x86.UC_X86_REG_EDX))
        m.reg_write(x86.UC_X86_REG_EAX, (self.stats.get(key, 0) if ago == 1 else 0) & 0xFFFFFFFF)
        m.reg_write(x86.UC_X86_REG_ESP, esp + 8)
        m.reg_write(x86.UC_X86_REG_EIP, ret)

    def league(self, teams):
        """teams: lists of 0x54-byte records -> player VAs per team."""
        cursor, base, out = WORLD + 0x1000, WORLD + 0x200000, []
        for t, team in enumerate(teams):
            ptrs = []
            for rec in team:
                self.m.mem_write(cursor, bytes(rec))
                ptrs.append(cursor)
                cursor += 0x54
            self.m.mem_write(base + t * 0x1F4, struct.pack(f"<{len(ptrs)}I", *ptrs).ljust(0x1F4, b"\0"))
            self.m.mem_write(base + t * 0x1F4 + 0x11C, bytes([len(ptrs)]))
            out.append(ptrs)
        count = sum(map(len, out))
        self.m.mem_write(WORLD, struct.pack("<II", count, WORLD + 0x1000) + bytes(0x10) + struct.pack("<II", len(out), base))
        self.m.mem_write(0x00B72918, struct.pack("<I", WORLD))
        self.m.mem_write(0x00E576A0, struct.pack("<I", 0))          # league type 0: the roster object's teams
        return out

    def call(self, va, ecx=0, edx=0, args=()):
        m, esp = self.m, STACK + 0xFFF00
        for value in reversed((SENTINEL,) + tuple(args)):
            esp -= 4
            m.mem_write(esp, struct.pack("<I", value & 0xFFFFFFFF))
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        for i, name in enumerate(SAVED):
            m.reg_write(getattr(x86, f"UC_X86_REG_{name}"), 0x5A5A0000 + i)
        m.reg_write(x86.UC_X86_REG_ECX, ecx)
        m.reg_write(x86.UC_X86_REG_EDX, edx)
        m.emu_start(va, SENTINEL, count=20_000_000)
        assert [m.reg_read(getattr(x86, f"UC_X86_REG_{n}")) for n in SAVED] == [0x5A5A0000 + i for i in range(4)], \
            f"callee-saved registers clobbered by {va:#x}"
        assert m.reg_read(x86.UC_X86_REG_ESP) == STACK + 0xFFF00, f"stack imbalance after {va:#x}"
        return m.reg_read(x86.UC_X86_REG_EAX)

    def record(self, va):
        return bytes(self.m.mem_read(va, 0x54))


def synthetic_player(rng, position, profiles):
    rec = bytearray(0x54)
    rows = [k for k in range(p.WEIGHT_ROWS) if struct.unpack_from("<I", profiles, k * 16)[0] == position]
    row = rng.choice(rows)
    profile, sub = profiles[row * 16 + 4], profiles[row * 16 + 5]
    years = rng.randrange(1, 23)
    rec[0x08] = 0x04
    struct.pack_into("<I", rec, 0x24, (sub << 4) | (profile << 7) | (years << 8))
    struct.pack_into("<I", rec, 0x1C, rng.randrange(4) << 30)
    rec[0x35] = position
    for offset in range(0x36, 0x52):
        rec[offset] = rng.randrange(25, 99)
    return rec


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.applied, cls.receipt = p.apply(cls.retail)

    def test_states_and_upgrade_from_the_beta77_patch(self):
        self.assertEqual(p.status(self.retail), "retail")
        self.assertEqual(p.status(self.applied), "applied")
        # a beta-77 disc (curves and weights only) reads "legacy" and is upgraded in place to the same bytes
        legacy = bytearray(self.retail)
        for _label, va, _before, after in p._data_sites(self.retail):
            off = p._offset(self.retail, va)
            legacy[off:off + len(after)] = after
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for section in _sections(legacy):
            legacy[section.header_offset + 36:section.header_offset + 56] = section_digest(legacy, section)
        self.assertEqual(p.status(bytes(legacy)), "legacy")
        upgraded, receipt = p.apply(bytes(legacy))
        self.assertTrue(receipt["upgraded_from_legacy"])
        self.assertEqual(upgraded, self.applied)

    def test_everything_is_in_place(self):
        image = XbeImage(self.applied)
        code, labels, _dd = p.career_layout(self.applied)
        self.assertLessEqual(labels["used"], p.PERF_SIZE)
        self.assertEqual(image.read(p.PERF_VA, p.PERF_SIZE), code)
        self.assertEqual(code[labels["used"]:], b"\xcc" * (p.PERF_SIZE - labels["used"]))
        self.assertEqual(image.read(p.AGING_CALL_VA, 5)[:1], b"\xe8")
        self.assertEqual(p.AGING_CALL_VA + 5 + struct.unpack("<i", image.read(p.AGING_CALL_VA + 1, 4))[0], labels["aging_ext"])
        self.assertEqual(p.MINI_LOAD_VA + 5 + struct.unpack("<i", image.read(p.MINI_LOAD_VA + 1, 4))[0], labels["qb_mini"])
        self.assertEqual(struct.unpack("<17I", image.read(p.RETIRE_BASE_VA, 68)), p.NFL_RETIRE_BASE)
        changed = {e["label"]: e["bytes"] for e in self.receipt["edits"]}
        self.assertEqual(changed["form_routine_and_aging_tables"], 0x4C0)
        self.assertEqual(len(self.applied), len(self.retail))          # no growth, no allocator request
        text = (ROOT / "mod_editor/core/nfl2k5_progression.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", text)

    def test_nfl_shapes(self):
        _code, _labels, dd = p.career_layout(self.applied)
        run = lambda cls, group, upto: sum(dd[(cls, group)][:upto + 1])
        # running backs lose physical ratings from age 24 (years pro 4); the others hold until later
        self.assertLess(run("RB", "physical", 8), run("WR", "physical", 8))
        self.assertLess(run("RB", "physical", 8), run("OL", "physical", 8))
        # quarterbacks' skills: the installed curves' decline is cancelled into the late 30s
        self.assertGreaterEqual(run("QB", "skill", 15), 0)
        self.assertGreater(run("QB", "skill", 15), run("CB", "skill", 15))
        # retirement: backs and corners earliest, quarterbacks, kickers and punters last
        base = dict(zip(p.POSITIONS, p.NFL_RETIRE_BASE))
        self.assertEqual(min(base.values()), base["RB"])
        self.assertTrue(base["QB"] > base["WR"] > base["RB"] and base["K"] >= base["QB"])
        for dd_curve in dd.values():
            self.assertFalse(any(dd_curve[:p.DD_FIRST_YEAR]))


@unittest.skipIf(uc is None, "unicorn is not installed")
class RoutineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.applied, _ = p.apply(cls.retail)
        cls.profiles = p._profiles(cls.retail)
        # the beta-77 executable: curves and weights only (what the aging must equal before the class step)
        legacy = bytearray(cls.retail)
        for _label, va, _before, after in p._data_sites(cls.retail):
            off = p._offset(cls.retail, va)
            legacy[off:off + len(after)] = after
        cls.legacy = bytes(legacy)

    def league(self, seed, teams=34, size=40):
        rng = random.Random(seed)
        out = []
        for _ in range(teams):
            out.append([synthetic_player(rng, rng.randrange(17), self.profiles) for _ in range(size)])
        return rng, out

    def test_form_routine_equals_retail_for_every_position_but_quarterback(self):
        fields = (0, 2, 6, 8, 9, 10, 13, 0x12, 0x13, 0x22, 0x41, 0x43)
        values = (0, 1, 2, 3, 5, 6, 7, 10, 11, 14, 15, 20, 21, 25, 30, 49, 50, 69, 70, 75, 78, 79, 89, 99, 100, 200, 300,
                  450, 500, 600, 700, 800, 801, 1000, 2000, 2500, 2501, 4000)
        for seed in range(3):
            rng, teams = self.league(seed)
            runs = []
            for payload in (self.retail, self.applied):
                emu = Emu(payload)
                ptrs = emu.league(teams)
                flat = [va for team in ptrs for va in team]
                emu.stats = {}
                srng = random.Random(seed)
                for i, va in enumerate(flat):
                    for field in fields:
                        emu.stats[(va, field)] = srng.choice(values)
                    emu.stats[(va, 6)] = srng.choice((0, 100, 149, 150, 400))
                emu.call(0x002BE0F0, ecx=1)
                runs.append([emu.record(va) for va in flat])
            before = [bytes(r) for team in teams for r in team]
            changed = sum(a != b for a, b in zip(before, runs[0]))
            self.assertGreater(changed, len(before) // 2)
            for i, (a, b) in enumerate(zip(*runs)):
                if before[i][0x35] != 0:
                    self.assertEqual(a, b, f"seed {seed} player {i} position {before[i][0x35]}")

    def test_quarterback_rule(self):
        rng, teams = self.league(11, teams=34)
        emu = Emu(self.applied)
        ptrs = emu.league(teams)
        qbs = [(t, va, teams[t][k]) for t, team in enumerate(ptrs) for k, va in enumerate(team) if teams[t][k][0x35] == 0]
        line = {}
        n_sum = a_sum = 0
        for t, va, rec in qbs:
            att = rng.choice((0, 120, 150, 300, 550))
            yards, td, ints = rng.randrange(0, 5000), rng.randrange(0, 45), rng.randrange(0, 25)
            if t >= p.CLUB_TEAMS:            # not a club: a monster line that must not move the league average
                att, yards, td, ints = 600, 6000, 60, 0
            emu.stats.update({(va, 6): att, (va, 8): yards, (va, 9): td, (va, 10): ints})
            line[va] = (att, yards + 20 * td - 45 * ints)
            if att >= p.QB_MIN_ATTEMPTS and t < p.CLUB_TEAMS:
                n_sum, a_sum = n_sum + line[va][1], a_sum + att
        trunc = lambda a, b: int(a / b)
        league = trunc(10 * n_sum, a_sum)
        emu.call(0x002BE0F0, ecx=1)
        self.assertGreater(len(qbs), 20)
        for t, va, rec in qbs:
            after = emu.record(va)
            old = struct.unpack_from("<I", rec, 0x1C)[0] >> 30
            years = (struct.unpack_from("<I", rec, 0x24)[0] >> 8) & 31
            att, n = line[va]
            if att < p.QB_MIN_ATTEMPTS:
                level = old
            else:
                level = sum(trunc(10 * n, att) - league >= edge for edge in p.QB_LEVEL_EDGES)
                if years > p.QB_YOUNG_MAX_YEARS:
                    level = max(level, old)
            self.assertEqual(struct.unpack_from("<I", after, 0x1C)[0] >> 30, level)
            self.assertEqual((struct.unpack_from("<I", after, 0x18)[0] >> 29) & 3, old)
            self.assertEqual(after[0x36], rec[0x36])                        # speed: form never moves a QB's legs
            want = rec[0x42] + p.QB_MINI[1][level] - p.QB_MINI[1][old]       # accuracy: the QB skill mini-curve
            self.assertEqual(after[0x42], max(0, min(100, want)))
            if years > p.QB_YOUNG_MAX_YEARS:
                self.assertGreaterEqual(after[0x42], rec[0x42])            # a veteran never drops for a down year

    def test_aging_follows_the_position_tables_and_unages_exactly(self):
        _code, _labels, dd = p.career_layout(self.applied)
        rng, teams = self.league(5, teams=12)
        emus = [Emu(self.legacy), Emu(self.applied)]
        ptrs = [emu.league(teams) for emu in emus]
        flat = [[va for team in group for va in team] for group in ptrs]
        recs = [r for team in teams for r in team]
        for i, rec in enumerate(recs):
            if rec[0x35] == p.POS["RB"]:
                yards = rng.choice((0, 1199, 1200, 1599, 1600, 2000))
                for emu, vas in zip(emus, flat):
                    emu.stats[(vas[i], 2)], emu.stats[(vas[i], 13)] = yards - yards // 4, yards // 4
        checked = 0
        for i, rec in enumerate(recs):
            years = (struct.unpack_from("<I", rec, 0x24)[0] >> 8) & 31
            old, new = min(years - 1, 20), min(years, 20)
            for emu, vas in zip(emus, flat):
                emu.call(0x000E63F0, ecx=vas[i], edx=old, args=(new,))
            a, b = emus[0].record(flat[0][i]), emus[1].record(flat[1][i])
            cls = p.CLASS_OF[p.POSITIONS[rec[0x35]]]
            shift = 0
            if rec[0x35] == p.POS["RB"]:
                stats = emus[1].stats
                shift = sum(stats[(flat[1][i], 2)] + stats[(flat[1][i], 13)] >= y for y in p.RB_PRODUCTION_SHIFT)
            for rating, table, family in p.RATING_ENTRIES:
                group = p.GROUP_OF_FAMILY[family]
                if not table or rating == 0x51 or a[rating] in (0, 100) or b[rating] in (0, 100):
                    continue
                want = dd[(cls, p.GROUPS[group])][max(0, max(old, new) - shift)] if group < len(p.GROUPS) and old != new else 0
                self.assertEqual(b[rating] - a[rating], want, f"player {i} {cls} rating {rating:#x} years {years}")
                checked += 1
            # the Player Progress screen un-ages (y, y - 1) and re-ages: the record comes back exactly
            if not any(b[o] in (0, 100) for o in range(0x36, 0x52)):
                emus[1].call(0x000E63F0, ecx=flat[1][i], edx=new, args=(old,))
                emus[1].call(0x000E63F0, ecx=flat[1][i], edx=old, args=(new,))
                self.assertEqual(emus[1].record(flat[1][i]), b)
        self.assertGreater(checked, 3000)

    def test_generation_and_retail_aging_untouched_for_rookies(self):
        rng, teams = self.league(3, teams=2, size=30)
        emus = [Emu(self.legacy), Emu(self.applied)]
        flat = [[va for team in emu.league(teams) for va in team] for emu in emus]
        for i in range(len(flat[0])):
            for emu, vas in zip(emus, flat):
                emu.call(0x000E63F0, ecx=vas[i], edx=0xFF, args=(0,))      # the class generator's call
            self.assertEqual(emus[0].record(flat[0][i]), emus[1].record(flat[1][i]))


if __name__ == "__main__":
    unittest.main()
