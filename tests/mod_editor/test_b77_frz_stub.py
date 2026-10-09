"""Regression: a selector live team is not the roster record behind +0x1c."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_moment_gun_weight as gun
from mod_editor.core import nfl2k5_stock_books as stock

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
FIXTURES = Path(os.environ.get("FRZ_XBE_FIXTURES", "/nonexistent/frz-fixtures"))


@unittest.skipUnless(HAVE_UNICORN, "Unicorn required")
class LiveTeamContractTests(unittest.TestCase):
    """Portable test with disjoint real-address live/roster objects and poisoned RNG.

    First down avoids any environmental callee. No game files are required.
    The former layout would dereference 0x31e18c8e as a pointer on the first call.
    """

    def fixture(self, *, legacy=False):
        import unicorn as uc
        from unicorn import x86_const as r
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        m.mem_map(0x10000, 0xF00000)
        m.mem_map(0x14E3000, 0x2000)
        m.mem_map(0x3000000, 0x10000)
        va = 0x14E3BD0
        code = stock.code_for(va, legacy_team_pointer=legacy)
        m.mem_write(va, code)
        m.mem_write(gun.RETAIL_WEIGHT_VA, gun.RETAIL_WEIGHT_BYTES)
        m.mem_write(gun.STATE_POINTER, struct.pack("<I", 0x3003000))
        m.mem_write(0x3003004, struct.pack("<I", 1))
        for team in (0xE5FC20, 0xE5FC60):
            m.mem_write(team + 0x110, struct.pack("<I", 0x31E18C8E))
            m.mem_write(team + 0x128, struct.pack("<I", 0x3B106B0))
            m.mem_write(team + 0x1C, struct.pack("<I", 0xB30864))
        m.mem_write(0xB30864 + 0x110, struct.pack("<I", 0x3004000))
        m.mem_write(0x3004004, struct.pack("<I", 0x3004100))
        wrapper = b"\xe8" + struct.pack("<i", va + stock.STUB_OFFSET - (0x3000000 + 5))
        wrapper += b"\xd9\x1d" + struct.pack("<I", 0x3001000) + b"\xc3"
        m.mem_write(0x3000000, wrapper)
        for name, value in dict(ESP=0x3008000, FPCW=0x37F, FPTAG=0xFFFF, FPSW=0,
                                EBX=0x12345678, ESI=0x23456789, EDI=0x3456789A, EBP=0x456789AB).items():
            m.reg_write(getattr(r, "UC_X86_REG_" + name), value)
        return m, r

    def run_stub(self, m, r, *, key="BAL", team=0xE5FC20):
        m.mem_write(0x3004100, (key + "\0").encode("utf-16le"))
        # Simulated external call: only ESP/return address/argument supplied.
        # Never reset x87 state or nonvolatile registers between calls.
        m.reg_write(r.UC_X86_REG_ESP, 0x3008000)
        m.mem_write(0x3008000, struct.pack("<I", 0x3002000))
        m.mem_write(0x300801C, struct.pack("<I", team))
        m.emu_start(0x3000000, 0x3002000, count=2000)
        self.assertEqual(m.reg_read(r.UC_X86_REG_EIP), 0x3002000)
        self.assertEqual(m.reg_read(r.UC_X86_REG_ESP), 0x3008004)
        self.assertEqual(m.reg_read(r.UC_X86_REG_FPTAG), 0xFFFF)
        self.assertEqual(m.reg_read(r.UC_X86_REG_FPSW) & 0x387F, 0)
        for name, value in dict(EBX=0x12345678, ESI=0x23456789, EDI=0x3456789A, EBP=0x456789AB).items():
            self.assertEqual(m.reg_read(getattr(r, "UC_X86_REG_" + name)), value)
        return struct.unpack("<f", m.mem_read(0x3001000, 4))[0]

    def test_512_consecutive_calls_use_separate_roster_and_balance_fpu_stack_registers(self):
        m, r = self.fixture()
        rows = gun.team_bin_weights(keys=stock.key_order())
        for i in range(512):
            index = i % 32
            got = self.run_stub(m, r, key=stock.key_order()[index], team=(0xE5FC20, 0xE5FC60)[i % 2])
            self.assertAlmostEqual(got, rows[index][0], places=5)

    def test_shipped_stub_faults_with_identical_valid_live_team_layout(self):
        import unicorn
        m, r = self.fixture(legacy=True)
        with self.assertRaises(unicorn.UcError):
            self.run_stub(m, r)
        self.assertEqual(m.reg_read(r.UC_X86_REG_EIP), 0x14E3E66)

    def test_category_is_read_from_roster_and_unknown_key_falls_back(self):
        m, r = self.fixture()
        m.mem_write(0xB30864 + 0x128, struct.pack("<I", 4))
        self.assertAlmostEqual(self.run_stub(m, r), gun.RETAIL_WEIGHT)
        m.mem_write(0xB30864 + 0x128, bytes(4))
        self.assertAlmostEqual(self.run_stub(m, r, key="ZZZ"), gun.RETAIL_WEIGHT)

    def test_null_live_roster_and_key_fall_back_and_moment_bypasses_team(self):
        m, r = self.fixture()
        self.assertAlmostEqual(self.run_stub(m, r, team=0), gun.RETAIL_WEIGHT)
        m.mem_write(0xE5FC20 + 0x1C, bytes(4))
        self.assertAlmostEqual(self.run_stub(m, r), gun.RETAIL_WEIGHT)
        m.mem_write(0xE5FC20 + 0x1C, struct.pack("<I", 0xB30864))
        m.mem_write(0xB30864 + 0x110, bytes(4))
        self.assertAlmostEqual(self.run_stub(m, r), gun.RETAIL_WEIGHT)
        m.mem_write(gun.MODE_WORD, struct.pack("<I", 8))
        m.mem_write(gun.ROW_WORD, struct.pack("<I", 38))
        self.assertAlmostEqual(self.run_stub(m, r, team=0), gun.weights()[38])


@unittest.skipUnless((FIXTURES / "v06/default.xbe").is_file(), "set FRZ_XBE_FIXTURES to bounded disc extractions")
class ShippedUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.b77 import frz_stub_repair as repair
        cls.before = (FIXTURES / "v06/default.xbe").read_bytes()
        cls.after, cls.receipt = repair.build(cls.before, "X5")

    def test_exact_legacy_upgrade_idempotence_tables_and_scope(self):
        from tools.b77 import frz_xbe_bisect as b
        self.assertEqual(stock.status(self.before), "needs_fix")
        self.assertEqual(stock.status(self.after), "applied")
        self.assertEqual(stock.apply(self.after)[0], self.after)
        payload = [row for row in self.receipt["ranges"] if row["kind"] == "payload"]
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["size"], gun.STUB_SPACE)
        self.assertEqual(b.verify_scope(self.before, self.after, self.receipt["ranges"]), b.V06_HASH)
        alloc = stock.allocation(self.before)
        start, end = alloc["raw"] + stock.WEIGHT_OFFSET, alloc["raw"] + stock.CODE_SIZE
        self.assertEqual(self.before[start:end], self.after[start:end])
        self.assertTrue(b.digests_ok(self.after))

    def test_foreign_old_stub_is_refused_even_with_valid_allocator_seals(self):
        alloc = stock.allocation(self.before)
        body = bytearray(self.before[alloc["raw"]:alloc["raw"] + stock.CODE_SIZE])
        body[stock.STUB_OFFSET + 7] ^= 1
        foreign = stock._write_body(self.before, alloc, body)
        self.assertEqual(stock.status(foreign), "foreign")
        with self.assertRaises(ValueError):
            stock.apply(foreign)

    @unittest.skipUnless(HAVE_UNICORN, "Unicorn required")
    def test_full_native_selector_reproduces_old_fault_and_fixed_callers_balance(self):
        from tools.b77.frz_stub_audit import replay
        home = (FIXTURES / "v06/BAL.play").read_bytes()
        away = (FIXTURES / "v06/PHI.play").read_bytes()
        old = replay(self.before, home, away, plays=4)
        self.assertEqual(old["faults"][0]["native"]["pc"], "0x14e3e66")
        new = replay(self.after, home, away, plays=4)
        self.assertEqual(new["faults"], [])
        self.assertEqual(new["completed_plays"], 4)
        self.assertEqual(new["rule_balance_errors"], [])
        self.assertEqual(new["bad_weights"], [])
        self.assertGreater(new["rule_calls"]["0x208150"], 0)
        self.assertGreater(new["rule_calls"]["0x2083a9"], 0)


if __name__ == "__main__":
    unittest.main()
