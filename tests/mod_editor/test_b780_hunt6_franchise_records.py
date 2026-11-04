"""b780 hunt6 (fix wave Q87, Q68): revision 2 of nfl2k5_coach_career_fix, two more in-place franchise record fixes.

* Q87 FUN_00135260, the per-game coach update: in the postseason the win and loss paths no longer add to the career W-L
  (+0x20/+0x22) or this season's W-L (+0x26/+0x28); streaks, playoff and Super Bowl counters are exactly retail's.
* Q68 the Owner Firing row's retail text callback 0x148A40: value 2 (All Teams, saved by a carousel build) reads On
  instead of the retail table's NULL third entry.
(Q66, the injured reserve bounds guard, moved to the modern IR owner, which rewrites that pass.)

Each routine runs in Unicorn on the retail and the patched executable (the only substitutions are the named leaves);
the bytes are checked against the annotated source docs/mod_editor/nfl2k5_coach_career_fix.S.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_coach_career_fix as fix
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_CPU = importlib.util.find_spec("unicorn") is not None
HAVE_DISASM = importlib.util.find_spec("capstone") is not None


def _env(name):
    value = os.environ.get(name, "")
    return Path(value) if value else None


V08_XBE = _env("NFL2K5_V08_XBE")
RC_XBE = _env("NFL2K5_B780_RC_XBE")
STOP, STACK, SCRATCH = 0x3100000, 0x3008000, 0x3010000


class Cpu:
    """The executable mapped at its addresses; code hooks substitute the named leaves only."""

    def __init__(self, payload, leaves=None):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn import x86_const as x
        self.x = x
        self.uc = u = Uc(UC_ARCH_X86, UC_MODE_32)
        u.mem_map(0x10000, 0xFF0000)
        image = XbeImage(payload)
        for s in image.sections:
            if s.raw_size:
                u.mem_write(s.start, image.read(s.start, min(s.size, s.raw_size)))
        u.mem_map(0x3000000, 0x20000)
        u.mem_map(STOP, 0x1000)
        self.leaves = dict(leaves or {})
        self.calls = []

        def hook(cpu, address, _size, _data):
            if address not in self.leaves:
                return
            value = self.leaves[address]
            sp = cpu.reg_read(x.UC_X86_REG_ESP)
            self.calls.append(address)
            ret = struct.unpack("<I", cpu.mem_read(sp, 4))[0]
            cpu.reg_write(x.UC_X86_REG_EAX, value() if callable(value) else value)
            cpu.reg_write(x.UC_X86_REG_ESP, sp + 4)     # the stubbed leaves take no stack arguments
            cpu.reg_write(x.UC_X86_REG_EIP, ret)
        u.hook_add(UC_HOOK_CODE, hook)

    def put(self, address, value, fmt="<I"):
        self.uc.mem_write(address, struct.pack(fmt, value))

    def read(self, address, size):
        return bytes(self.uc.mem_read(address, size))

    def run(self, address, **registers):
        x = self.x
        self.uc.mem_write(STACK, struct.pack("<I", STOP))
        self.uc.reg_write(x.UC_X86_REG_ESP, STACK)
        for name, value in registers.items():
            self.uc.reg_write(getattr(x, "UC_X86_REG_" + name.upper()), value)
        self.uc.emu_start(address, STOP, count=100000)
        assert self.uc.reg_read(x.UC_X86_REG_EIP) == STOP
        return self.uc.reg_read(x.UC_X86_REG_EAX)


class SiteTests(unittest.TestCase):
    def test_revision2_sites(self):
        self.assertEqual(fix.REVISION, 2)
        self.assertEqual([va for _l, va, _b, _a in fix.SITES], [0x247CD6, 0x135260, 0x148A40])
        for label, va, before, after in fix.SITES:
            self.assertEqual(len(before), len(after), label)
        self.assertLess(len(fix.BUILD_CAPTION), 61)
        self.assertNotIn("\u2014", fix.HELP_TEXT + fix.BUILD_CAPTION)

    @unittest.skipUnless(HAVE_DISASM, "capstone required")
    def test_the_new_routines_write_only_eax_and_the_coach_words(self):
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        md.detail = True
        rows = [(i.mnemonic, i.op_str) for i in md.disasm(fix.PATCHED_OWNER_TEXT, fix.OWNER_TEXT_VA)]
        self.assertEqual(rows[1:3], [("inc", "eax"), ("shr", "eax, 1")])
        written = set()
        for i in md.disasm(fix.PATCHED_RESULT, fix.RESULT_VA):
            if i.mnemonic in ("call", "ret", "nop", "cmp", "test") or i.mnemonic.startswith("j"):
                continue
            dest = i.op_str.split(",")[0]
            written.add("memory" if "ptr [esi" in dest else dest)
        self.assertEqual(written, {"memory", "ax"})

    def test_checked_in_assembly_reproduces_the_bytes(self):
        if os.name == "nt" or not all(shutil.which(t) for t in ("as", "ld", "objcopy")):
            self.skipTest("optional GNU assembler reproducibility check")
        specs = (("result", fix.RESULT_VA, fix.PATCHED_RESULT.rstrip(b"\x90")),
                 ("owner_text", fix.OWNER_TEXT_VA, fix.PATCHED_OWNER_TEXT))
        with tempfile.TemporaryDirectory() as tmp:
            obj, elf = Path(tmp) / "c.o", Path(tmp) / "c.elf"
            subprocess.run(["as", "--32", str(ROOT / "docs/mod_editor/nfl2k5_coach_career_fix.S"), "-o", str(obj)],
                           check=True, capture_output=True)
            subprocess.run(["ld", "-m", "elf_i386", *[f"--section-start=.{n}={va:#x}" for n, va, _ in specs],
                            "-e", "result", str(obj), "-o", str(elf)], check=True, capture_output=True)
            for name, _va, expected in specs:
                out = Path(tmp) / (name + ".bin")
                subprocess.run(["objcopy", "-O", "binary", "--only-section=." + name, str(elf), str(out)],
                               check=True, capture_output=True)
                self.assertEqual(out.read_bytes(), expected, name)


@unittest.skipUnless(XBE.is_file(), "retail extraction required")
class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()

    def _spans(self, payload):
        return {rdata.offset_of(payload, va): len(before) for _l, va, before, _a in fix.SITES}

    def test_retail_applies_all_three_sites_and_the_digest_only(self):
        self.assertEqual(fix.status(self.retail), "retail")
        patched, receipt = fix.apply(self.retail)
        self.assertEqual((fix.status(patched), receipt["revision"]), ("applied", 2))
        spans = self._spans(self.retail)
        changed = [i for i, (a, b) in enumerate(zip(self.retail, patched)) if a != b]
        outside = [i for i in changed if not any(a <= i < a + n for a, n in spans.items())]
        self.assertLessEqual(len(outside), 20)                       # the .text section digest
        self.assertEqual(fix.apply(patched)[0], patched)

    def test_a_revision1_install_reads_previous_and_upgrades_in_place(self):
        v1, _ = rdata.apply(self.retail, fix.SITES_V1, "revision 1")
        self.assertEqual(fix.status(v1), "previous")
        upgraded, receipt = fix.apply(v1)
        self.assertEqual((fix.status(upgraded), receipt["upgraded_from"]), ("applied", 1))
        self.assertEqual(upgraded, fix.apply(self.retail)[0])

    def test_a_foreign_byte_in_any_new_site_refuses(self):
        patched = fix.apply(self.retail)[0]
        for _label, va, before, _after in fix.SITES_V2:
            for delta in (0, len(before) - 1):
                broken = bytearray(patched)
                broken[rdata.offset_of(patched, va) + delta] ^= 0x41
                self.assertEqual(fix.status(bytes(broken)), "foreign", (hex(va), delta))

    @unittest.skipUnless(V08_XBE is not None and V08_XBE.is_file(), "NFL2K5_V08_XBE not set")
    def test_the_released_v08_takes_the_whole_fix(self):
        raw = V08_XBE.read_bytes()
        self.assertEqual(fix.status(raw), "retail")
        self.assertEqual(fix.status(fix.apply(raw)[0]), "applied")

    @unittest.skipUnless(RC_XBE is not None and RC_XBE.is_file(), "NFL2K5_B780_RC_XBE not set")
    def test_the_v09_rc_upgrades_in_place(self):
        raw = RC_XBE.read_bytes()
        self.assertEqual(fix.status(raw), "previous")
        out, receipt = fix.apply(raw)
        self.assertEqual((fix.status(out), receipt["upgraded_from"]), ("applied", 1))


@unittest.skipUnless(XBE.is_file() and HAVE_CPU, "retail extraction and Unicorn required")
class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched = fix.apply(cls.retail)[0]

    # ---- Q87: the per-game coach update -------------------------------------------------------------------------------
    def _result(self, payload, stage, ours, theirs, super_bowl, record):
        cpu = Cpu(payload, leaves={0x133A30: int(super_bowl)})
        cpu.put(0xE576A4, stage)
        cpu.uc.mem_write(SCRATCH, bytes(record))
        cpu.run(0x135260, esi=SCRATCH, edi=theirs, ebx=ours)       # edi < ebx is a win
        return cpu.read(SCRATCH, 0x40)

    def _record(self):
        raw = bytearray(0x40)
        for i, at in enumerate(range(0x1C, 0x3E, 2)):
            struct.pack_into("<H", raw, at, 10 + i)
        struct.pack_into("<H", raw, 0x2C, 1)                     # on a winning streak
        return raw

    def test_regular_season_and_preseason_games_count_as_retail(self):
        for stage in (7, 8):
            for ours, theirs in ((24, 17), (10, 31), (20, 20)):
                with self.subTest(stage=stage, ours=ours, theirs=theirs):
                    a = self._result(self.retail, stage, ours, theirs, False, self._record())
                    b = self._result(self.patched, stage, ours, theirs, False, self._record())
                    self.assertEqual(a, b)

    def test_playoff_games_stay_out_of_the_career_and_season_record(self):
        words = lambda raw, at: struct.unpack_from("<H", raw, at)[0]
        for ours, theirs in ((24, 17), (10, 31)):
            for super_bowl in (False, True):
                with self.subTest(win=ours > theirs, super_bowl=super_bowl):
                    before = self._record()
                    a = self._result(self.retail, 9, ours, theirs, super_bowl, before)
                    b = self._result(self.patched, 9, ours, theirs, super_bowl, before)
                    for at in (0x20, 0x22, 0x26, 0x28):
                        self.assertEqual(words(b, at), words(before, at), hex(at))
                    # retail moved exactly one career and one season word; everything else is identical
                    moved = {at for at in (0x20, 0x22, 0x26, 0x28) if words(a, at) != words(before, at)}
                    self.assertEqual(moved, {0x20, 0x26} if ours > theirs else {0x22, 0x28})
                    for at in range(0, 0x40, 2):
                        if at not in (0x20, 0x22, 0x26, 0x28):
                            self.assertEqual(words(a, at), words(b, at), hex(at))
                    counter = (0x38 if super_bowl else 0x34) if ours > theirs else (0x3A if super_bowl else 0x36)
                    self.assertEqual(words(b, counter), words(before, counter) + 1)

    def test_a_9_8_club_that_loses_its_first_playoff_game_keeps_its_winning_season(self):
        """The rollover compares this season's W (+0x26) with L (+0x28): 9-8 stays a winning season after a loss."""
        record = bytearray(0x40)
        struct.pack_into("<HH", record, 0x26, 9, 8)
        a = self._result(self.retail, 9, 10, 31, False, record)
        b = self._result(self.patched, 9, 10, 31, False, record)
        self.assertEqual(struct.unpack_from("<HH", a, 0x26), (9, 9))
        self.assertEqual(struct.unpack_from("<HH", b, 0x26), (9, 8))

    # ---- Q68: the Owner Firing text ------------------------------------------------------------------------------
    def test_owner_firing_text_reads_value_two_as_on(self):
        image = XbeImage(self.retail)
        off, on, third = struct.unpack("<3I", image.read(0x4ED994, 12))
        self.assertEqual(third, 0)
        for payload, expected in ((self.retail, (off, on, 0)), (self.patched, (off, on, on))):
            got = []
            for value in (0, 1, 2):
                cpu = Cpu(payload)
                cpu.put(0xE60144, value)
                got.append(cpu.run(fix.OWNER_TEXT_VA))
            self.assertEqual(tuple(got), expected)


if __name__ == "__main__":
    unittest.main()
