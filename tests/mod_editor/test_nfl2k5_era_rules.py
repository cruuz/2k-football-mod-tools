"""PROVED OFFLINE: actual composed x86 rule paths, no graphics or game launch."""
import json
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_era_rules as era
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_anniversary_kickoff as gate
from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core import nfl2k5_kick_rules as kr
from mod_editor.core import nfl2k5_overtime as ot
from mod_editor.core import nfl2k5_defensive_try as dt
from mod_editor.core import nfl2k5_coin_defer as coin
from mod_editor.core import nfl2k5_decided_clock as clock
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

SOURCE = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")


def composition():
    if os.environ.get('NFL2K5_E2_BUILT_DISC'):
        from mod_editor.core.nfl2k5_espn25_rosters import read_xbe
        return read_xbe(Path(os.environ['NFL2K5_E2_BUILT_DISC']))
    payload = XBE.read_bytes()
    payload, _ = space.apply(payload, era.REQUESTS + gate.REQUESTS + dt.REQUESTS + coin.REQUESTS + clock.REQUESTS)
    for module in (kr, dk, ot, dt, coin, clock):
        payload, _ = module.apply(payload)
    payload, _ = gate.apply(payload, gate.disc_tables(SOURCE))
    return era.apply(payload)[0]


class Machine:
    STACK, STOP, SCRATCH = 0x2800000, 0x2801000, 0x2810000

    def __init__(self, payload):
        import unicorn as u
        from unicorn import x86_const as r
        self.r = r
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x2FF0000)
        image = XbeImage(payload)
        for section in image.sections:
            self.uc.mem_write(section.start, image.read(section.start, section.raw_size))
        self.uc.reg_write(r.UC_X86_REG_CR0, self.uc.reg_read(r.UC_X86_REG_CR0) & ~4)
        self.uc.reg_write(r.UC_X86_REG_CR4, self.uc.reg_read(r.UC_X86_REG_CR4) | 0x200)

    def w(self, at, value):
        self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def r32(self, at):
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def f(self, at):
        return struct.unpack("<f", self.uc.mem_read(at, 4))[0]

    def call(self, at, *, stop=None, flags=0x202, **regs):
        self.w(self.STACK, self.STOP)
        for name in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
            self.uc.reg_write(getattr(self.r, "UC_X86_REG_" + name.upper()), regs.get(name, 0))
        self.uc.reg_write(self.r.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(self.r.UC_X86_REG_EFLAGS, flags)
        self.uc.emu_start(at, stop or self.STOP, count=1_000_000)
        actual = self.uc.reg_read(self.r.UC_X86_REG_EIP)
        assert actual == (stop or self.STOP), hex(actual)
        return self.uc.reg_read(self.r.UC_X86_REG_EAX)

    def target(self, site):
        raw = bytes(self.uc.mem_read(site, 5))
        assert raw[0] in (0xE8, 0xE9)
        return site + 5 + struct.unpack_from("<i", raw, 1)[0]

    def multiply(self, site, sign=1):
        at = self.SCRATCH
        raw = b"\xd9\xe8" + (b"\xd9\xe0" if sign < 0 else b"")
        raw += b"\xe8" + struct.pack("<i", self.target(site) - at - len(raw) - 5)
        raw += b"\xd9\x1d" + struct.pack("<I", at + 256) + b"\xc3"
        self.uc.mem_write(at, raw)
        self.uc.ctl_remove_cache(at, at + 256)
        self.call(at)
        return self.f(at + 256)

    def row(self, i, mode=8):
        self.w(0xE5FF80, mode)
        self.w(0xBF1858, i)

    def scores(self, home, away, *, possession=0xE5FC20, phase=2, flags=0):
        self.w(0xE5FC28, self.SCRATCH + 0x400)
        self.w(0xE5FC68, self.SCRATCH + 0x500)
        self.w(self.SCRATCH + 0x400, home)
        self.w(self.SCRATCH + 0x500, away)
        self.w(0xE5FC20, 0xE5FC60)
        self.w(0xE5FC60, 0xE5FC20)
        self.w(0xE60280, possession)
        self.w(0xE60284, 0xE5FC60 if possession == 0xE5FC20 else 0xE5FC20)
        self.w(0xE602B4, phase)
        self.w(0xE602C4, 5)
        self.w(ot.STATE_FLAGS, flags)


@unittest.skipUnless(XBE.is_file() and SOURCE.is_file(), "private USA retail source required")
class NativeRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = composition()
        cls.rows = json.loads((era.ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]

    def setUp(self):
        self.m = Machine(self.payload)

    def test_all_owners_and_reversible_hooks(self):
        for module in (space, kr, dk, ot, dt, coin, clock, gate, era):
            self.assertEqual(module.status(self.payload), "applied", module.__name__)
        disabled, _ = era.apply(self.payload, enabled=False)
        self.assertEqual(era.status(disabled), "retail")
        self.assertEqual(era.apply(disabled)[0], self.payload)
        image = XbeImage(self.payload)
        bad = bytearray(self.payload)
        bad[image.offset(era.specs()[0][1], 1)] ^= 1
        self.assertEqual(era.status(era._seal(bad)), "foreign")

    def test_every_moment_kickoff_touchback_pat_and_sign(self):
        m = self.m
        for i, row in enumerate(self.rows):
            m.row(i)
            for _name, at, _const, kind in kr.KICKOFF_SITES:
                want = (50 - row["kickoff_yard"]) * 91.44 * (-1 if kind == "neg" else 1)
                for sign in (1, -1):
                    self.assertAlmostEqual(m.multiply(at, sign), sign * want, places=2)
            for phase, yard in ((2, row["free_kick_touchback_yard"]), (4, 20), (1, 20)):
                m.w(0xE602B4, phase)
                self.assertAlmostEqual(m.multiply(kr.TOUCHBACK_SITE_VA), (50 - yard) * 91.44, places=2)
            self.assertAlmostEqual(m.multiply(kr.TRY_RECORD_SITE_VA),
                                   (50 - row["pat_kick_snap_yard"]) * 91.44, places=2)

    def test_invalid_row_and_current_mode_keep_underlying_rules(self):
        m = self.m
        for ordinal, mode, yard in ((0, 4, 35), (49, 7, 35), (51, 8, 30), (0xFFFFFFFF, 8, 30)):
            m.row(ordinal, mode)
            self.assertAlmostEqual(m.multiply(kr.KICKOFF_SITES[0][1]), (50 - yard) * 91.44, places=2)

    def test_every_try_value_including_afl_and_reentry(self):
        m = self.m
        for i, row in enumerate(self.rows):
            m.row(i)
            score, actor = m.SCRATCH + 400, m.SCRATCH + 500
            m.w(score, 7)
            m.w(actor + 0x38, 0xE5FC20)
            m.call(0xB8487, eax=score, ecx=actor, stop=0xB848D)
            self.assertEqual(m.r32(score), 9 if row["two_point_try"] else 8, i + 1)
        m.row(0, 4)
        m.w(score, 7)
        m.call(0xB8487, eax=score, ecx=actor, stop=0xB848D)
        self.assertEqual(m.r32(score), 9)

    def test_every_overtime_format_first_scores_and_second_possession(self):
        m = self.m
        for i, row in enumerate(self.rows):
            if row["overtime"] == "none":
                continue
            m.row(i)
            for difference in (0, 3, 6):
                m.scores(20 + difference, 20)
                m.call(m.target(ot.PRED_SITE_VA))
                ended = bool(m.uc.reg_read(m.r.UC_X86_REG_EFLAGS) & 0x40)
                want = difference != 0 and (row["overtime"] == "sudden_death" or
                        (difference == 6 and row["overtime"] == "modified_sudden_death_first_TD_ends"))
                self.assertEqual(ended, want, (i + 1, difference))
            # Both sides have possessed; a leader in possession and a safety each end OT.
            for phase in (4, 1):
                m.scores(23, 20, phase=phase, flags=3)
                m.call(m.target(ot.PRED_SITE_VA))
                self.assertTrue(m.uc.reg_read(m.r.UC_X86_REG_EFLAGS) & 0x40)
            # Trailing team loses the ball to its leading opponent.
            m.scores(23, 20, phase=4, flags=2)
            m.call(m.target(ot.PRED_SITE_VA))
            self.assertTrue(m.uc.reg_read(m.r.UC_X86_REG_EFLAGS) & 0x40)

    def test_cpu_try_choice_uses_era_and_afl_exception(self):
        m = self.m
        for i, row in enumerate(self.rows):
            m.row(i)
            m.scores(20, 22)  # retail explicitly goes for two when down by two
            self.assertEqual(m.call(0x208470), int(row["two_point_try"]))
        m.row(0, 4)
        self.assertEqual(m.call(0x208470), 1)

    def test_completed_free_kick_fair_catch_spot_both_directions(self):
        m = self.m
        state = era.places(self.payload)["data"]["va"]
        player, position, direction, output = (m.SCRATCH + n for n in (0x100, 0x200, 0x300, 0x600))
        m.scores(0, 0)
        m.w(player + 0x38, 0xE5FC20)
        m.w(player + 0x18, position)
        m.w(m.SCRATCH + 0x400 + 12, direction)
        for row, mode, phase in ((49, 8, 2), (48, 8, 2), (49, 4, 2), (49, 8, 4)):
            m.row(row, mode)
            m.w(0xE602B4, phase)
            for sign in (1, -1):
                m.w(direction + 4, struct.unpack('<I', struct.pack('<f', sign))[0])
                for yard in (0, 1, 24, 25, 26, 40):
                    spot = (yard - 50) * 91.44 * sign
                    raw = struct.unpack('<I', struct.pack('<f', spot))[0]
                    m.w(position + 0x38, raw)
                    m.w(state + 8, 0)
                    m.call(0xB6989, eax=player, stop=0xB698E)
                    m.call(0xB6685, eax=output, ecx=raw, stop=0xB668F)
                    want = -2286 * sign if row == 49 and mode == 8 and phase == 2 and 0 < yard < 25 else spot
                    self.assertAlmostEqual(m.f(output + 8), want, places=2, msg=str((row, mode, phase, sign, yard)))
                    self.assertEqual(m.r32(state + 8), 0)
                    # The next ordinary dead ball must retain its own spot.
                    m.call(0xB6685, eax=output, ecx=raw, stop=0xB668F)
                    self.assertAlmostEqual(m.f(output + 8), spot, places=2)

    def test_no_overtime_and_postseason_period_continuation(self):
        m = self.m
        for i, row in enumerate(self.rows):
            m.row(i)
            m.scores(20, 20)
            m.call(0xB8AB0, stop=0xB8B04 if row['overtime'] == 'none' else 0xB8AB7)
            m.call(0xB8ADF, ecx=5, stop=0xB8AED if row['postseason'] else 0xB8B04)
            for home, away, possession, phase in ((20,20,0xE5FC20,4),(23,20,0xE5FC60,4),(23,20,0xE5FC20,4)):
                m.scores(home, away, possession=possession, phase=phase)
                m.call(m.target(ot.EXPIRY_SITE_VA))
                continued = bool(m.uc.reg_read(m.r.UC_X86_REG_EFLAGS) & 0x40)
                want = home == away or (row['postseason'] and row['overtime'] in
                        ('modified_sudden_death_first_TD_ends', 'both_possessions') and possession == 0xE5FC60)
                self.assertEqual(continued, want, (i+1,home,away,possession))

    def test_old_pat_paths_and_defensive_try_dead_ball(self):
        m = self.m
        for i, row in enumerate(self.rows):
            m.row(i)
            if row['season'] < 2015:
                for site, target in ((kr.PAT_STORE_SITE_VA,kr.STORE_TARGET_VA),
                                     (kr.PAT_PICK_SITE_VA,kr.PICK_TARGET_VA),
                                     (kr.PAT_AUDIBLE_SITE_VA,kr.AUDIBLE_TARGET_VA)):
                    m.call(m.target(site), stop=target)
                m.call(m.target(0x22EC11), stop=0x22E050)
            for site, size, live in ((0xB9B9A,12,0xB9BCD),(0xB9E37,12,0xB9E61)):
                for flags in (0x202,0x242):
                    target = site+size if row['season'] < 2015 and flags & 0x40 else live
                    m.call(site, flags=flags, stop=target)
                    self.assertEqual(m.r32(0xE602C0), 2)
            m.w(0xE602B4,3)
            m.call(0xB7B4B, edi=3, stop=0xB7B53 if row['season'] < 2015 else 0xB7B5D)

    def test_old_coin_toss_clears_modern_defer_state(self):
        m = self.m
        state = era.places(self.payload)["coin_state"]
        m.row(0)
        m.w(state, 0xE5FC20)
        m.call(0x25E7B5, eax=123, stop=0x25E7BC)
        self.assertEqual(m.r32(state), 0)
        self.assertEqual(m.uc.reg_read(m.r.UC_X86_REG_EBX), 123)

    def test_absolute_ot_minutes_and_later_period_keep_possessions(self):
        m = self.m
        state = era.places(self.payload)["data"]["va"]
        for i, row in enumerate(self.rows):
            if not row["overtime_minutes"]:
                continue
            m.row(i)
            m.scores(20, 20)
            m.w(state, 0)
            m.w(0xE6028C, m.SCRATCH + 600)
            m.call(m.target(ot.OT_KICKOFF_SITE_VA), stop=ot.FN_KICK_SETUP)
            self.assertEqual(m.f(0xE602B0), row["overtime_minutes"] * 60)
            self.assertEqual(m.f(m.SCRATCH + 616), row["overtime_minutes"] * 60)
            m.w(ot.STATE_FLAGS, 3)
            m.w(0xE602C4, 6)
            m.call(m.target(ot.OT_KICKOFF_SITE_VA), stop=ot.FN_KICK_SETUP)
            self.assertEqual(m.r32(ot.STATE_FLAGS) & 3, 3)

    def test_incidental_facemask_settings_and_current_restore(self):
        m = self.m
        m.w(0xE600A8, struct.unpack("<I", struct.pack("<f", 0.5))[0])
        for i, row in enumerate(self.rows):
            m.row(i)
            m.call(0xB1440)
            self.assertAlmostEqual(m.f(0xA8A480), 457.2 if row["season"] < 2008 else 1371.6, places=2)
            if row["season"] >= 2008:
                self.assertEqual(m.r32(0xA8A490), 0)
        m.row(0)
        m.call(0xB1440)
        m.row(0, 4)
        m.call(0xB1440)
        self.assertAlmostEqual(m.f(0xA8A480), 1371.6, places=2)


if __name__ == "__main__":
    unittest.main()
