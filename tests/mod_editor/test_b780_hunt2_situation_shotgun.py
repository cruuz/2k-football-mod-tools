"""b780 hunt2: the plain Situation mode takes the 2026 club shotgun tables, not a stale 25th Anniversary moment weight.

The shotgun weight stub (``nfl2k5_moment_gun_weight``, placed by ``nfl2k5_stock_books``) answered "an Anniversary moment" for
game mode 8 alone. The plain Situation mode is game mode 8 too (Situation flag 0xE6014C = 1) and its moment row word holds 0
or the last moment played (b777-sm2), so every Situation game took that row's flat weight: 0.05 after boot (the retail
"almost no shotgun beyond the 10"), 1.7 after moment row 30, and never the club's down-and-distance table that Play Now uses.

The fix moves the stub's first test into a 15-byte gate in the allocation's free tail, ``(mode ^ 8) | flag`` (the test
``nfl2k5_moment_venues`` and the resolver in the same owner use), and leaves every byte of the stub after its first nine.

Always on (Unicorn): the stub of the current body and of the shipped body (beta-79 / v0.8 and the v0.9 RC, kind "b780_bins")
run on a small fake game: every non-Situation input (11 game modes, three flags, nine moment rows, six team arguments, six
downs, eight distances) gives the same float from both; the Situation mode gives the Play Now answer for every team, down
and distance, whatever the stale row. With ``NFL2K5_V08_XBE`` (the released v0.8 default.xbe): that executable reads
"needs_fix" and apply() changes only the stub's first nine bytes, the gate and the allocator's seals.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_moment_gun_weight as gw  # noqa: E402
from mod_editor.core import nfl2k5_stock_books as sb  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
VA = 0x014E3D30                       # where the v0.8 and v0.9 RC builds put the allocation (any VA does for the run)
YARD = 91.44
SITUATION_FLAG = 0x00E6014C
PAGE = 0x1000


class Machine:
    """The stub of one 1,536-byte body on a fake game: the globals it reads, two live teams and their roster records, the
    situation object (down), and a stand-in for the yards-to-go function 0x207950 (fld [distance] ; ret)."""

    DRIVER, OUT, STACK, HEAP, DIST = 0x02600000, 0x02600100, 0x02700000, 0x02800000, 0x02600200
    OFFENSE, DEFENSE, STRANGER = HEAP, HEAP + 0x100, HEAP + 0x200
    ROSTERS = (HEAP + 0x1000, HEAP + 0x1200, HEAP + 0x1400)

    def __init__(self, body: bytes):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_ESP
        self.esp_reg = UC_X86_REG_ESP
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        for base, size in ((VA & ~(PAGE - 1), 2 * PAGE), (0x00E5F000, PAGE), (0x00E60000, PAGE), (0x00BF1000, PAGE),
                           (0x004E6000, PAGE), (0x00207000, PAGE), (self.DRIVER, PAGE), (self.STACK, 4 * PAGE),
                           (self.HEAP, 4 * PAGE)):
            uc.mem_map(base, size)
        uc.mem_write(VA, body)
        uc.mem_write(gw.RETAIL_WEIGHT_VA, struct.pack("<f", 0.05))
        uc.mem_write(gw.TOGO_FUNCTION, bytes.fromhex("d905") + struct.pack("<I", self.DIST) + b"\xc3")
        stub = VA + sb.STUB_OFFSET                     # driver: call stub ; fstp [out] ; hlt
        uc.mem_write(self.DRIVER, b"\xe8" + struct.pack("<i", stub - (self.DRIVER + 5))
                     + b"\xd9\x1d" + struct.pack("<I", self.OUT) + b"\xf4")
        self.put(gw.OFFENSE_TEAM_POINTER, self.OFFENSE)
        self.put(gw.DEFENSE_TEAM_POINTER, self.DEFENSE)
        self.put(gw.STATE_POINTER, self.HEAP + 0x3000)

    def put(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def team(self, live: int, roster: int, key: str | None, category: int = 0) -> None:
        self.put(live + 0x1C, roster)
        self.put(roster + sb.gun.CATEGORY_OFFSET, category)
        if key is None:
            self.put(roster + sb.gun.KEY_OFFSET, 0)
            return
        name = roster + 0x180                          # past the roster fields the stub reads (+0x110, +0x128)
        self.put(roster + sb.gun.KEY_OFFSET, name)
        self.put(name + 4, name + 0x10)
        self.uc.mem_write(name + 0x10, (key + "\0").encode("utf-16le").ljust(8, b"\0"))

    def weight(self, *, mode: int, flag: int, row: int, team: int, down: int, yards: float) -> bytes:
        self.put(gw.MODE_WORD, mode)
        self.put(SITUATION_FLAG, flag)
        self.put(gw.ROW_WORD, row)
        self.put(self.HEAP + 0x3000 + 4, down)
        self.uc.mem_write(self.DIST, struct.pack("<f", yards * YARD))
        esp = self.STACK + 2 * PAGE
        self.uc.mem_write(esp, bytes(0x40))
        self.put(esp + 0x1C, team)                     # [esp+0x20] inside the stub = argument 1 of 0x207EF0
        self.uc.reg_write(self.esp_reg, esp)
        self.uc.emu_start(self.DRIVER, self.DRIVER + 11, count=4000)
        return bytes(self.uc.mem_read(self.OUT, 4))


def bodies():
    return sb.code_for(VA), sb.code_for(VA, gun_situation=False)


@unittest.skipUnless(HAVE_UNICORN, "Unicorn required")
class SituationShotgun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        new, old = bodies()
        cls.keys = sb.key_order()
        cls.bins = dict(zip(cls.keys, gw.team_bin_weights(keys=cls.keys)))
        cls.moments = gw.weights()
        # a club whose 2026 table is not flat (so the bins are visible), a second known club, and an unknown key
        modern = [k for k in cls.keys if len(set(cls.bins[k])) > 2]
        cls.club, cls.other = modern[0], modern[1]
        cls.machines = {}
        for label, body in (("new", new), ("old", old)):
            m = Machine(body)
            m.team(m.OFFENSE, m.ROSTERS[0], cls.club)
            m.team(m.DEFENSE, m.ROSTERS[1], cls.other)
            m.team(m.STRANGER, m.ROSTERS[2], cls.club)
            cls.machines[label] = m

    def teams(self, m):
        """(label, argument, roster setup) for the six team arguments the stub must handle."""
        return (("offense club", m.OFFENSE, (m.OFFENSE, m.ROSTERS[0], self.club, 0)),
                ("defense club", m.DEFENSE, (m.DEFENSE, m.ROSTERS[1], self.other, 0)),
                ("unknown key", m.OFFENSE, (m.OFFENSE, m.ROSTERS[0], "ZZZ", 0)),
                ("historic side", m.OFFENSE, (m.OFFENSE, m.ROSTERS[0], self.club, 4)),
                ("no key object", m.OFFENSE, (m.OFFENSE, m.ROSTERS[0], None, 0)),
                ("not a live team", m.STRANGER, (m.OFFENSE, m.ROSTERS[0], self.club, 0)))

    def both(self, setup, **state):
        out = []
        for label in ("new", "old"):
            m = self.machines[label]
            m.team(*setup)
            out.append(m.weight(**state))
        return out

    def test_every_other_input_gives_the_earlier_answer(self):
        modes = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0x108)
        rows = (0, 1, 22, 29, 30, 38, 50, 51, 0xFFFFFFFF)
        downs, yards = (0, 1, 2, 3, 4, 5), (1.0, 3.4, 3.5, 3.6, 6.5, 7.5, 8.0, 20.0)
        checked = 0
        for mode in modes:
            for flag in (0, 1, 0xFFFFFFFF):
                if mode == 8 and flag:
                    continue                                      # the one case the fix changes (next test)
                for row in (rows if mode == 8 else rows[:2]):
                    for label, team, setup in self.teams(self.machines["new"]):
                        for down in downs:
                            for distance in (yards if down in (2, 3, 4) else yards[:1]):
                                new, old = self.both(setup, mode=mode, flag=flag, row=row, team=team, down=down, yards=distance)
                                self.assertEqual(new, old, (mode, flag, row, label, down, distance))
                                checked += 1
        self.assertGreater(checked, 4000)

    def test_the_situation_mode_takes_the_play_now_answer(self):
        """Mode 8 with the Situation flag: exactly what mode 4 (Play Now) gives, for every team, down and distance, whatever
        the stale moment row; the shipped body gave the row's flat weight instead."""
        changed = 0
        for row in (0, 22, 29, 30, 50, 51, 0xFFFFFFFF):
            for flag in (1, 2, 0xFFFFFFFF):
                for label, team, setup in self.teams(self.machines["new"]):
                    for down in (1, 2, 3, 4):
                        for distance in ((1.0, 5.0, 9.0) if down > 1 else (10.0,)):
                            m = self.machines["new"]
                            m.team(*setup)
                            situation = m.weight(mode=8, flag=flag, row=row, team=team, down=down, yards=distance)
                            play_now = m.weight(mode=4, flag=0, row=row, team=team, down=down, yards=distance)
                            self.assertEqual(situation, play_now, (row, flag, label, down, distance))
                            old = self.machines["old"]
                            old.team(*setup)
                            shipped = old.weight(mode=8, flag=flag, row=row, team=team, down=down, yards=distance)
                            if row < 51:
                                self.assertAlmostEqual(struct.unpack("<f", shipped)[0], self.moments[row], places=5)
                            changed += shipped != situation
        self.assertGreater(changed, 100)

    def test_a_moment_still_reads_the_moment_table(self):
        for row in range(51):
            for label, team, setup in self.teams(self.machines["new"])[:2]:
                new, old = self.both(setup, mode=8, flag=0, row=row, team=team, down=1, yards=10.0)
                self.assertEqual(new, old, (row, label))
                self.assertAlmostEqual(struct.unpack("<f", new)[0], self.moments[row], places=5)

    def test_the_club_table_is_what_play_now_and_the_situation_mode_read(self):
        m = self.machines["new"]
        m.team(m.OFFENSE, m.ROSTERS[0], self.club, 0)
        first = struct.unpack("<f", m.weight(mode=8, flag=1, row=0, team=m.OFFENSE, down=1, yards=10.0))[0]
        self.assertAlmostEqual(first, self.bins[self.club][0], places=4)
        long_third = struct.unpack("<f", m.weight(mode=8, flag=1, row=0, team=m.OFFENSE, down=3, yards=9.0))[0]
        self.assertAlmostEqual(long_third, self.bins[self.club][6], places=4)


class Layout(unittest.TestCase):
    def test_only_the_stubs_first_nine_bytes_and_the_gate_differ(self):
        new, old = bodies()
        self.assertEqual(len(new), len(old), sb.CODE_SIZE)
        diff = [i for i in range(sb.CODE_SIZE) if new[i] != old[i]]
        self.assertTrue(all(sb.STUB_OFFSET <= i < sb.STUB_OFFSET + 9 or sb.GATE_OFFSET <= i < sb.GATE_OFFSET + 15
                            for i in diff), diff)
        self.assertEqual(new[sb.GATE_OFFSET:sb.GATE_OFFSET + 15], gw.SITUATION_GATE)
        self.assertEqual(old[sb.GATE_OFFSET:], b"\xcc" * (sb.CODE_SIZE - sb.GATE_OFFSET))
        self.assertEqual(new[sb.GATE_OFFSET + 15:], b"\xcc" * (sb.CODE_SIZE - sb.GATE_OFFSET - 15))
        self.assertEqual(sb.GATE_OFFSET, sb.BIN_TABLE_OFFSET + gw.BIN_TABLE_SIZE)
        # head: call gate ; jne team ; nop ; nop -- and the moment part still at +9 (mov eax,[row] ; cmp eax,51)
        stub = new[sb.STUB_OFFSET:sb.STUB_OFFSET + 17]
        self.assertEqual(stub[0], 0xE8)
        self.assertEqual(struct.unpack_from("<i", stub, 1)[0] + VA + sb.STUB_OFFSET + 5, VA + sb.GATE_OFFSET)
        self.assertEqual((stub[5], stub[7:9]), (0x75, b"\x90\x90"))
        self.assertEqual(stub[9:17], old[sb.STUB_OFFSET + 9:sb.STUB_OFFSET + 17])
        self.assertEqual(old[sb.STUB_OFFSET:sb.STUB_OFFSET + 7].hex(), "833d80ffe50008")
        self.assertEqual(gw.SITUATION_GATE.hex(), "a180ffe50083f0080b054c01e600c3")

    def test_the_shipped_body_reads_needs_fix_and_the_current_body_applied(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage

        class Image:
            def __init__(self, body):
                self.body = body

            def read(self, va, size):
                return self.body[va - VA:va - VA + size]

        new, old = bodies()
        self.assertEqual(sb._installed_kind(Image(old), VA)[0], "b780_bins")
        self.assertEqual(sb._installed_kind(Image(new), VA)[0], "current")
        self.assertIsNotNone(XbeImage)


@unittest.skipUnless(os.environ.get("NFL2K5_V08_XBE") and Path(os.environ.get("NFL2K5_V08_XBE", "")).is_file(),
                     "NFL2K5_V08_XBE (the default.xbe of the released v0.8 disc) is not set")
class ReleasedExecutable(unittest.TestCase):
    def test_v08_needs_fix_and_apply_changes_only_the_head_the_gate_and_the_seals(self):
        payload = Path(os.environ["NFL2K5_V08_XBE"]).read_bytes()
        owned = sb.allocation(payload)
        self.assertEqual(owned["va"], VA)
        self.assertEqual(sb.status(payload), "needs_fix")
        result, receipt = sb.apply(payload)
        self.assertEqual(sb.status(result), "applied")
        self.assertEqual(space.status(result), "applied")
        raw = owned["raw"]
        for i in (i for i in range(len(payload)) if payload[i] != result[i]):
            inside = raw + sb.STUB_OFFSET <= i < raw + sb.STUB_OFFSET + 9 or raw + sb.GATE_OFFSET <= i < raw + sb.GATE_OFFSET + 15
            seals = space.META_START <= i < space.LIB_COPY or space.SCALE_DIRECTORY <= i < space.SCALE_DIRECTORY + space.PAGE
            self.assertTrue(inside or seals, hex(i))
        self.assertEqual(sb.apply(result)[1]["status"], "already_applied")


if __name__ == "__main__":
    unittest.main()
