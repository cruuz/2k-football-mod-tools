"""b780 c1-coachdata: the coach career counter fix (nfl2k5_coach_career_fix).

The patch is checked three ways: the bytes (4 changed, a valid 4-byte no-op, foreign refused), the section digest the
kernel checks, and the game's own rollover loop run in Unicorn on the retail and the patched executable.  Needs the
private retail disc (NFL2K5_RETAIL_XISO) and unicorn for the executable tests; the SOFTDRINK v0.8 executable is checked
when that disc is present."""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_coach_career_fix as fix  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402

_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
_V08 = Path(os.environ.get("NFL2K5_V08_XISO", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.8 (2026-10-31).xiso.iso"))
try:
    import unicorn
    from unicorn import x86_const as regs
except ImportError:                                         # pragma: no cover
    unicorn = None


def xbe_of(path: Path) -> bytes:
    from mod_editor.core.mod_build import _xbe_bytes
    return _xbe_bytes(path)


class SiteTests(unittest.TestCase):
    def test_the_patch_changes_exactly_the_one_increment(self) -> None:
        (label, va, before, after), = fix.SITES
        self.assertEqual((va, len(before), len(after)), (0x247CD6, 8, 8))
        self.assertEqual(before[:4], after[:4], "the winning-seasons increment at +0x30 stays")
        self.assertEqual(before[4:], bytes.fromhex("66ff4032"))
        self.assertEqual(after[4:], bytes.fromhex("0f1f4000"))
        try:
            import capstone
        except ImportError:
            return
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        self.assertEqual([(i.mnemonic, i.op_str) for i in md.disasm(before, va)],
                         [("inc", "word ptr [eax + 0x30]"), ("inc", "word ptr [eax + 0x32]")])
        self.assertEqual([(i.mnemonic, i.size) for i in md.disasm(after[4:], va + 4)], [("nop", 4)])

    def test_plain_words_for_the_option(self) -> None:
        self.assertNotIn("—", fix.HELP_TEXT + fix.BUILD_CAPTION)
        self.assertLess(len(fix.HELP_TEXT), 400)


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = xbe_of(_XISO)

    def test_retail_applies_once_and_only_four_code_bytes_and_the_digest_move(self) -> None:
        self.assertEqual(fix.status(self.retail), "retail")
        patched, receipt = fix.apply(self.retail)
        self.assertEqual(fix.status(patched), "applied")
        changed = [i for i, (a, b) in enumerate(zip(self.retail, patched)) if a != b]
        site = rdata.offset_of(self.retail, 0x247CDA)
        self.assertEqual(len(patched), len(self.retail))
        self.assertEqual(patched[site:site + 4], bytes.fromhex("0f1f4000"))
        self.assertEqual(self.retail[site:site + 4], bytes.fromhex("66ff4032"))
        outside = [i for i in changed if not site <= i < site + 4]
        self.assertLessEqual(len(outside), 20, "only the section digest (20 bytes) may move besides the instruction")
        self.assertEqual(receipt["sections_repinned"], [0])
        again, second = fix.apply(patched)
        self.assertEqual((again, second["changed_bytes"]), (patched, 0))

    def test_a_foreign_executable_is_refused(self) -> None:
        foreign = bytearray(self.retail)
        foreign[rdata.offset_of(self.retail, 0x247CDA)] ^= 0xFF
        self.assertEqual(fix.status(bytes(foreign)), "foreign")
        with self.assertRaises(rdata.RdataSiteError):
            fix.apply(bytes(foreign))

    @unittest.skipUnless(_V08.is_file(), "released v0.8 disc absent")
    def test_the_released_executable_is_still_retail_at_the_site(self) -> None:
        self.assertEqual(fix.status(xbe_of(_V08)), "retail")


@unittest.skipUnless(_XISO.is_file() and unicorn is not None, "retail disc or unicorn absent")
class RolloverReplayTests(unittest.TestCase):
    """The game's own loop at 0x247CA8..0x247CF4 over a fixture league, on both executables."""

    BASE, TEAMS, COACHES, STACK = 0x1100000, 0x1110000, 0x1120000, 0x1130000
    # (seasons with team, total seasons, season wins, season losses, ties, winning seasons, "super bowls", playoff W, L)
    FIXTURE = [
        dict(name="winning season", w=12, l=5, t=0, with_team=4, total=9, winning=6, trips=2),
        dict(name="losing season", w=5, l=12, t=0, with_team=1, total=3, winning=0, trips=0),
        dict(name="even season", w=8, l=8, t=1, with_team=2, total=2, winning=1, trips=0),
        dict(name="no coach record", w=None, l=None, t=None, with_team=0, total=0, winning=0, trips=0),
        dict(name="record shared by two clubs", w=11, l=6, t=0, with_team=7, total=20, winning=14, trips=3, share=0),
    ]

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = xbe_of(_XISO)
        cls.patched, _ = fix.apply(cls.retail)

    def replay(self, xbe: bytes) -> list[dict]:
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(xbe)
        m = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        m.mem_map(0x10000, 0xF00000)
        for section in image.sections:
            if section.raw_size:
                m.mem_write(section.start, image.read(section.start, section.raw_size))
        m.mem_map(self.BASE, 0x80000)
        coach_at = {}
        teams = []
        for index, row in enumerate(self.FIXTURE):
            owner = row.get("share", index)
            if row["w"] is not None:
                coach_at[index] = self.COACHES + owner * 0xA8
                if "share" not in row:
                    record = bytearray(0xA8)
                    struct.pack_into("<HHHHH", record, 0x1C, row["with_team"], row["total"], 0, 0, 0)
                    struct.pack_into("<HHH", record, 0x26, row["w"], row["l"], row["t"])
                    struct.pack_into("<HH", record, 0x30, row["winning"], row["trips"])
                    m.mem_write(coach_at[index], bytes(record))
            teams.append(self.TEAMS + index * 0x200)
        # a clone of the first record's club (row 4 shares record 0 with row 0)
        for index, team in enumerate(teams):
            pointer = coach_at.get(index, 0)
            if index == 4:
                pointer = coach_at[0]
            m.mem_write(team + 0x14C, struct.pack("<I", pointer))

        def leave(mu, value):
            sp = mu.reg_read(regs.UC_X86_REG_ESP)
            mu.reg_write(regs.UC_X86_REG_EAX, value)
            mu.reg_write(regs.UC_X86_REG_EIP, struct.unpack("<I", mu.mem_read(sp, 4))[0])
            mu.reg_write(regs.UC_X86_REG_ESP, sp + 4)

        m.hook_add(unicorn.UC_HOOK_CODE, lambda mu, *_: leave(mu, len(teams)), begin=0xC4BE0, end=0xC4BE0)
        m.hook_add(unicorn.UC_HOOK_CODE, lambda mu, *_: leave(mu, teams[mu.reg_read(regs.UC_X86_REG_ECX)]),
                   begin=0xC4C50, end=0xC4C50)
        m.mem_write(self.STACK - 0x100, bytes(0x100))
        for name, value in (("ESP", self.STACK - 0x80), ("EBP", 0), ("ESI", 0), ("EDI", 0), ("EBX", 0), ("EAX", 0), ("ECX", 0), ("EDX", 0)):
            m.reg_write(getattr(regs, "UC_X86_REG_" + name), value)
        m.emu_start(0x247CA8, 0x247CF4, count=100000)
        out = []
        for index, row in enumerate(self.FIXTURE):
            if "share" in row or row["w"] is None:
                continue
            record = bytes(m.mem_read(coach_at[index], 0xA8))
            out.append(dict(name=row["name"], with_team=struct.unpack_from("<H", record, 0x1C)[0],
                            total=struct.unpack_from("<H", record, 0x1E)[0], season=struct.unpack_from("<3H", record, 0x26),
                            winning=struct.unpack_from("<H", record, 0x30)[0], trips=struct.unpack_from("<H", record, 0x32)[0]))
        return out

    def test_every_counter_agrees_except_the_trips(self) -> None:
        before, after = self.replay(self.retail), self.replay(self.patched)
        self.assertEqual([r["name"] for r in before], ["winning season", "losing season", "even season"])
        for old, new in zip(before, after):
            for key in ("with_team", "total", "season", "winning"):
                self.assertEqual(old[key], new[key], (old["name"], key))
            self.assertEqual(old["season"], (0, 0, 0), "the season record resets")

    def test_retail_inflates_the_trips_and_the_fix_does_not(self) -> None:
        before, after = {r["name"]: r for r in self.replay(self.retail)}, {r["name"]: r for r in self.replay(self.patched)}
        # the winning coach's record is also the record of the last club (a record shared by two clubs is visited twice:
        # the seasons count twice, but the first visit resets the season record, so the winning season counts once)
        self.assertEqual((before["winning season"]["with_team"], before["winning season"]["total"]), (4 + 2, 9 + 2))
        self.assertEqual(before["winning season"]["winning"], 6 + 1)
        self.assertEqual(before["winning season"]["trips"], 2 + 1, "retail: a Super Bowl trip for the winning season")
        self.assertEqual(after["winning season"]["trips"], 2, "patched: the count stays what the roster wrote")
        self.assertEqual(after["winning season"]["winning"], 6 + 1, "the winning-seasons counter still counts")
        for name in ("losing season", "even season"):
            self.assertEqual(before[name]["trips"], after[name]["trips"], name)
            self.assertEqual(after[name]["winning"], before[name]["winning"], name)
        self.assertEqual((after["losing season"]["with_team"], after["losing season"]["total"]), (1 + 1, 3 + 1))
        self.assertEqual(after["even season"]["winning"], 1, "8-8-1 is not a winning season")


if __name__ == "__main__":
    unittest.main()
