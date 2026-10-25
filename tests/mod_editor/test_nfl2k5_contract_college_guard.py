"""b778-cr1: the Player Contracts panel must not dereference a null college word.

The retail panel case (0x6E0D8, case 3) does ``mov edx,[player+0] ; mov esi,[edx]`` with no null check: a player
whose college word is 0 (the released v0.6.1 main roster has 50) faults at EIP 0x6E11F. The guard hooks the load and
takes the panel's own missing-value fallback (0x6E14E, L"N/A"). The native tests run the real panel case under
Unicorn; they skip without the pinned retail XBE or Unicorn. Nothing here is an in-game result.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_contract_college_guard as guard  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", str(ROOT / "extracted"))) / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None


def _retail() -> bytes | None:
    if not XBE.is_file() or XBE.stat().st_size > 16 * 1024 ** 2:
        return None
    data = XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == RETAIL_SHA256 else None


class TemplateTests(unittest.TestCase):
    def test_site_and_cave(self):
        self.assertEqual(guard.REQUESTS, ((guard.OWNER, "code", 32, 16),))
        self.assertEqual(len(guard.code_for(0x14DA000)), 32)
        body = guard.code_for(0x14DA000)
        self.assertEqual(body[:4], bytes.fromhex("85d20f84"))
        self.assertEqual(body[8:10], bytes.fromhex("8b32"))
        self.assertEqual(body[10:15], bytes.fromhex("b940000000"))
        self.assertEqual(body[15], 0xE9)
        self.assertEqual(body[20:], b"\xcc" * 12)
        ((label, va, before, after),) = guard.sites(0x14DA000)
        self.assertEqual((label, va), ("contract_college", 0x6E11F))
        self.assertEqual((before, len(after)), (bytes.fromhex("8b32b94000"), 5))
        self.assertEqual(after, b"\xe9" + struct.pack("<i", 0x14DA000 - 0x6E11F - 5))

    def test_late_owner_is_last(self):
        # b778-int2: xs1's module loader stays last; the guard is immediately before it.
        self.assertEqual(space.LATE_OWNERS[-6:], ("nfl2k5_player_progress_screen", guard.OWNER, "nfl2k5_sim_cb_tackles", "nfl2k5_clock_led", "nfl2k5_module_loader", "nfl2k5_return_coverage"))
        self.assertEqual(space.LATE_OWNERS[-15], "nfl2k5_force_out")

    def test_relocations(self):
        a, b = guard.code_for(0x14DA000), guard.code_for(0x14DB000)
        self.assertEqual(a[:2], b[:2])
        self.assertNotEqual(a[2:10], b[2:10])
        self.assertNotEqual(a[17:22], b[17:22])


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.retail = retail
        cls.patched, _ = guard.apply(retail)

    def prepare(self, payload, college):
        from tests.mod_editor.test_nfl2k5_honors import Machine
        m = Machine(payload)
        player = m.HEAP + 0x1000
        m.uc.mem_write(player, bytes(0x54))
        if college is None:
            m.put(player, 0)
        else:
            record, string = m.HEAP + 0x2000, m.HEAP + 0x3000
            m.put(record, string)
            m.put(player, record)
            m.uc.mem_write(string, college.encode("utf-16-le") + b"\0\0")
        m.hook(guard.CASE_END, lambda _m: None)
        wrapper = m.HEAP + 0x70000
        m.uc.mem_write(wrapper, b"\xbf" + struct.pack("<I", player)
                       + b"\xe9" + struct.pack("<i", 0x6E11D - (wrapper + 10)))
        return m, wrapper

    def run_case(self, payload, college):
        m, wrapper = self.prepare(payload, college)
        m.call(wrapper, budget=1_000_000)
        return m.uc.mem_read(m.SP - 4 + 0xA0, 128).decode("utf-16-le").split("\0")[0]

    def test_retail_null_college_faults(self):
        m, wrapper = self.prepare(self.retail, None)
        with self.assertRaises(Exception):
            m.call(wrapper, budget=1_000_000)
        self.assertEqual(m.reg("EIP"), 0x6E11F)

    def test_guard_takes_the_panel_fallback(self):
        self.assertEqual(self.run_case(self.patched, None), "N/A")

    def test_guard_keeps_real_colleges(self):
        for college in ("Clemson", "Florida", "North Carolina"):
            with self.subTest(college=college):
                self.assertEqual(self.run_case(self.patched, college), college)

    def test_apply_is_idempotent(self):
        again, receipt = guard.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(guard.read_settings(self.patched),
                         {"status": "applied", "contract_college_guard": True})

    def test_foreign_site_refused(self):
        broken = bytearray(self.retail)
        off = guard.rdata.offset_of(self.retail, 0x6E11F)
        broken[off] ^= 0xFF
        with self.assertRaises(Exception):
            guard.apply(bytes(broken))


if __name__ == "__main__":
    unittest.main()
