"""Run the retail catch decision (FUN_001C78D0) in Unicorn and measure drops with the catch_slider cave.

The real routine runs from 0x1C7F2B (the Catching skill lookup) to the roll at 0x1C8317: table select,
curve interpolation (FUN_001B0AE0, hands curve 0x50AC84), the pressure / diving / failed-attempt penalties,
the 0.1 floor, the veto.  Only the leaf queries that need a live game world are stubbed, and each is a scenario
parameter: the attribute accessor (Catching skill), FUN_001C6640 (defender pressure), FUN_001E6250 (diving
state) and FUN_001E6360 (animation gate).  The installed cave then turns the roll into the catch decision
(real instructions, real RNG stub), so the numbers include the patch.  Skipped when unicorn or the private
retail XBE is absent.  Run standalone with PYTHONPATH=<repo>.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_catch_slider as cs
from tests.nfl2k5_catch_cave_emulation_test import (
    PLAYER, RAND_FLOAT, RETAIL_XBE, SCRATCH, STACK_TOP, TEAM_A, TEAM_B, Uc, _load,
)

if Uc is not None:
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_FETCH_UNMAPPED, UC_HOOK_MEM_READ_UNMAPPED, UC_HOOK_MEM_WRITE_UNMAPPED, UcError
    from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESP

SKILL, PRESS, FLAGS = SCRATCH + 0x1000, SCRATCH + 0x1004, SCRATCH + 0x1008
OBJ = SCRATCH + 0x30000
ENTRY, CATCH_BRANCH, DEFLECT_BRANCH = 0x001C7F2B, 0x001C832F, 0x001C834C
HANDS = 0x420000          # contact mask bits the hands curve is chosen for
HUMAN_CELL, CPU_CELL = cs.HUMAN_CATCHING_CELL, cs.CPU_CATCHING_CELL


def _w(uc, address, data):
    try:
        uc.mem_write(address, data)
    except Exception:
        uc.mem_map(address & ~0xFFF, 0x2000)
        uc.mem_write(address, data)


def _f32(uc, address, value):
    _w(uc, address, struct.pack("<f", value))


def _u32(uc, address, value):
    _w(uc, address, struct.pack("<I", value & 0xFFFFFFFF))


class Routine:
    """One loaded image; ``run`` replays the decision for a scenario and returns (P, veto, outcome)."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def run(self, skill, *, pressure=0.0, failed=0, diving=0, rand=None, human=0.5, cpu=0.5, mask=HANDS,
            offense_human=True):
        uc = _load(self.payload)

        def unmapped(u, _access, address, _size, _value, _data):
            try:
                u.mem_map(address & ~0xFFF, 0x1000)
            except Exception:
                return False
            return True

        uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED, unmapped)
        # leaf queries: parameters of the scenario
        _w(uc, 0x17B010, b"\xd9\x05" + struct.pack("<I", SKILL) + b"\xc2\x04\x00")      # Catching skill
        _w(uc, 0x1C6640, b"\xd9\x05" + struct.pack("<I", PRESS) + b"\xc2\x04\x00")      # defender pressure
        _w(uc, 0x1E6250, b"\xa1" + struct.pack("<I", FLAGS) + b"\xc3")                   # diving state
        _w(uc, 0x1E6290, b"\xa1" + struct.pack("<I", FLAGS + 4) + b"\xc3")
        _w(uc, 0x1E6360, b"\xa1" + struct.pack("<I", FLAGS + 8) + b"\xc3")              # animation gate (nonzero = ok)
        _w(uc, 0x1C65D0, b"\xa1" + struct.pack("<I", FLAGS + 12) + b"\xc3")
        _w(uc, 0x1C65B0, b"\x33\xc0\xc3")
        _w(uc, 0x190930, b"\xb8\x01\x00\x00\x00\xc3")
        _f32(uc, SKILL, skill)
        _f32(uc, PRESS, pressure)
        for offset, value in ((0, diving), (4, 0), (8, 1), (12, 0)):
            _u32(uc, FLAGS + offset, value)
        # the world the routine reads
        _u32(uc, 0xE60280, TEAM_A)
        _u32(uc, 0xE60284, TEAM_B)
        _u32(uc, 0xE602C0, 4)                       # forward pass
        _u32(uc, 0xE3C020, failed)                  # failed attempts on this ball
        _u32(uc, 0xBE5B44, 0)
        _u32(uc, 0xE602EC, OBJ + 0x400)
        _u32(uc, 0xE6029C, OBJ + 0x500)
        _u32(uc, PLAYER + 0x38, TEAM_A)             # the catcher is on the team with the ball
        _u32(uc, TEAM_A + 0x30, 0x00F30000 if offense_human else 0)
        _u32(uc, PLAYER + 0x10, OBJ + 0x100)
        _u32(uc, OBJ + 0x104, OBJ + 0x200)
        _w(uc, OBJ + 0x204, b"\x00\x00\x00\x08")    # position type: not a back/TE special case
        _w(uc, OBJ + 0x180, b"\0\0\0\0")            # roll path
        _u32(uc, PLAYER + 0x3C, OBJ + 0x600)
        _w(uc, PLAYER + 0x2C, b"\x08")
        _f32(uc, HUMAN_CELL, human)
        _f32(uc, CPU_CELL, cpu)
        _f32(uc, cs.INT_SLIDER_GLOBAL, 0.5)
        if rand is not None:
            _w(uc, cs.RAND_FN, b"\xd9\x05" + struct.pack("<I", RAND_FLOAT) + b"\xc3")
            _f32(uc, RAND_FLOAT, rand)
        sp = (STACK_TOP - 0x400) & ~0xF
        for i in range(0, 0x100, 4):
            _u32(uc, sp + i, 0)
        for offset, value in ((0x24, OBJ + 0x700), (0x2C, OBJ + 0x720), (0x38, OBJ + 0x740), (0x3C, 1)):
            _u32(uc, sp + offset, value)
        ebp = STACK_TOP - 0x40
        _f32(uc, ebp + 8, 1 / 60)
        uc.reg_write(UC_X86_REG_EBP, ebp)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EBX, PLAYER)
        uc.reg_write(UC_X86_REG_EDI, mask)
        seen = {}

        def at_roll(u, address, _size, _data):
            if address == cs.HOOK_VA and "P" not in seen:
                esp = u.reg_read(UC_X86_REG_ESP)
                seen["P"] = struct.unpack("<f", u.mem_read(esp + 0x14, 4))[0]
                seen["veto"] = struct.unpack("<I", u.mem_read(esp + 0x30, 4))[0]
                if rand is None:
                    u.emu_stop()
            elif address in (CATCH_BRANCH, DEFLECT_BRANCH):
                seen["outcome"] = address == CATCH_BRANCH
                u.emu_stop()

        uc.hook_add(UC_HOOK_CODE, at_roll)
        try:
            uc.emu_start(ENTRY, 0x1C8400, timeout=3_000_000, count=4000)
        except UcError as error:  # pragma: no cover - surfaced by the assertion below
            seen["error"] = str(error)
        return seen


# Catching skill of a target by position group (NFL target shares 2022-25, nflverse): WR 62 %, TE 21 %, RB 17 %.
POSITION_GROUPS = ((0.62, 78, 8), (0.21, 68, 10), (0.17, 58, 10))     # share, mean rating, sd
# Defender pressure at the catch (FUN_001C6640, 0 .. 0.5): share of rolls with none / light / tight coverage.
PRESSURE_MIX = ((0.55, 0.0, 0.0), (0.30, 0.05, 0.25), (0.15, 0.25, 0.5))   # share, low, high
HARSH_MIX = ((0.25, 0.0, 0.0), (0.35, 0.05, 0.25), (0.40, 0.25, 0.5))       # tight coverage on 40 % of the targets
# NFL 2022-25 regular season (nflverse play-by-play + FTN charting, 71,653 targets): drops per catchable target.
NFL_DROP_PER_CATCHABLE = 0.0516


@unittest.skipUnless(Uc is not None and RETAIL_XBE.is_file(), "unicorn or the private retail XBE is absent")
class CatchDropDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        retail = RETAIL_XBE.read_bytes()
        cls.retail = Routine(retail)
        cls.patched = Routine(cs.apply(retail)[0])

    def test_the_scale_constant_is_a_retail_float(self) -> None:
        offset = cs._offset(self.retail.payload, cs.ODDS_SCALE_VA)
        self.assertEqual(struct.unpack("<f", self.retail.payload[offset: offset + 4])[0], cs.ODDS_SCALE)

    def test_hands_contact_probability_matches_the_curve_and_penalties(self) -> None:
        curve = ((0.0, 0.1), (0.3, 0.4), (0.5, 0.8), (0.65, 1.0), (0.8, 1.1), (0.9, 1.25), (1.0, 1.5))

        def hands(x):
            for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
                if x <= x1:
                    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)
            return curve[-1][1]

        for skill in (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            clean = self.retail.run(skill)
            self.assertAlmostEqual(clean["P"], hands(skill), places=5, msg=skill)
            self.assertEqual(clean["veto"], 0)
            tight = self.retail.run(skill, pressure=0.3)
            self.assertAlmostEqual(tight["P"], max(0.1, hands(skill) - 0.3), places=5, msg=skill)
            second = self.retail.run(skill, failed=2)
            self.assertAlmostEqual(second["P"], max(0.1, hands(skill) - 0.25 * (1 - skill) * 2), places=5, msg=skill)

    def test_cave_decides_with_min_1_of_m_times_p_and_human_equals_cpu(self) -> None:
        for skill in (0.4, 0.6, 0.75):
            for pressure in (0.0, 0.2):
                native = self.retail.run(skill, pressure=pressure)["P"]
                for human, cpu in ((0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (1.0, 0.0), (1.0, 1.0)):
                    m = cs.odds_multiplier(human, cpu)
                    for offense_human in (True, False):
                        caught = sum(
                            self.patched.run(skill, pressure=pressure, rand=r, human=human, cpu=cpu,
                                             offense_human=offense_human)["outcome"]
                            for r in (0.02, 0.2, 0.4, 0.6, 0.8, 0.98))
                        expected = sum(1 for r in (0.02, 0.2, 0.4, 0.6, 0.8, 0.98) if r < native * m)
                        self.assertEqual(caught, expected, (skill, pressure, human, cpu, offense_human))

    def drop_rate(self, m, *, bands=None, mix=PRESSURE_MIX, **scenario):
        """Expected drops per roll over the target mix; ``m`` = catch-odds multiplier."""
        total = weight = 0.0
        per_band = {}
        grid = [(share_g, mean, sd, share_p, low, high)
                for share_g, mean, sd in POSITION_GROUPS for share_p, low, high in mix]
        for share_g, mean, sd, share_p, low, high in grid:
            for z in (-1.5, -0.5, 0.5, 1.5):            # 4-point normal quadrature (equal weights)
                rating = max(30.0, min(99.0, mean + z * sd))
                for pressure in {low, (low + high) / 2, high}:
                    native = self.retail.run(rating / 100, pressure=pressure, **scenario)["P"]
                    w = share_g * share_p / (4 * len({low, (low + high) / 2, high}))
                    drop = max(0.0, 1.0 - min(1.0, native * m))
                    total += w * drop
                    weight += w
                    band = int(rating // 10) * 10
                    entry = per_band.setdefault(band, [0.0, 0.0])
                    entry[0] += w
                    entry[1] += w * drop
        if bands is not None:
            bands.update({b: v[1] / v[0] for b, v in sorted(per_band.items())})
        return total / weight

    def test_drop_rates_by_rating_band_before_and_after(self) -> None:
        rows = {}
        for label, m in (("retail CPU", 1.0), ("beta-78 human (Pro 0.75)", 1.5), ("new, both sides", cs.odds_multiplier(0.75, 0.25))):
            bands = {}
            rows[label] = (self.drop_rate(m, bands=bands), bands)
            print(label, "drops per roll %.4f" % rows[label][0], {b: round(v, 3) for b, v in bands.items()}, flush=True)
        retail, _ = rows["retail CPU"]
        new, new_bands = rows["new, both sides"]
        self.assertLess(new, retail)
        ordered = [new_bands[b] for b in sorted(new_bands)]
        self.assertEqual(ordered, sorted(ordered, reverse=True), "low-catch players must drop more than high-catch players")

    def test_new_drop_rate_is_near_the_nfl_rate_with_elite_hands_kept_sure(self) -> None:
        # b780 b5-sim: at m = 2 (b779 gp1) only P < 0.5 could drop, so receivers rated 70+ never dropped a ball in their
        # hands (0.1 to 0.3 drops a team-game in v0.8 against the NFL's 1.2). m = 1.25 puts the roll near the NFL's
        # 5.2 % of catchable targets while keeping elite hands (Catching 90+) almost sure.
        m = cs.odds_multiplier(0.75, 0.25)
        self.assertAlmostEqual(m, 1.25, places=6)
        for label, mix, scenario in (("assumed coverage", PRESSURE_MIX, {}), ("harsh coverage", HARSH_MIX, {}),
                                     ("harsh coverage, diving catches", HARSH_MIX, {"diving": 1})):
            bands = {}
            retail = self.drop_rate(1.0, mix=mix, **scenario)
            gp1 = self.drop_rate(2.0, mix=mix, **scenario)
            new = self.drop_rate(m, mix=mix, bands=bands, **scenario)
            print(f"{label}: drops per roll retail {retail:.4f}, beta-79 (m=2) {gp1:.4f}, new {new:.4f} "
                  f"(NFL {NFL_DROP_PER_CATCHABLE:.4f}) bands {({b: round(v, 4) for b, v in bands.items()})}", flush=True)
            self.assertLess(new, retail)
            self.assertGreater(new, 1.5 * gp1, "average hands must drop more than in beta-79")
            self.assertLess(bands.get(90, 0.0), 0.01, "elite hands stay almost sure")
            if not scenario:
                self.assertGreater(new, 0.015)
                self.assertLess(new, 1.4 * NFL_DROP_PER_CATCHABLE)


if __name__ == "__main__":
    unittest.main()
