"""The shared team-need header (tools/common/team_need.h) and its Python mirror (mod_editor/core/nfl2k5_team_need.py)
hold the same tables and constants, and the header compiles freestanding. Fails on c4406481b (neither file exists)."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "tools/common/team_need.h"


def _tables(text):
    out = {}
    for name, body in re.findall(r"static const unsigned char (TN_\w+)\[17\] = \{([^}]*)\};", text):
        out[name] = tuple(int(v) for v in body.split(","))
    return out


def _constants(text):
    return {name: int(value, 0) for name, value in re.findall(r"#define (TN_\w+) (\w+)u", text)}


class TeamNeedHeader(unittest.TestCase):
    def test_python_mirror_equals_the_header(self):
        from mod_editor.core import nfl2k5_team_need as tn
        text = HEADER.read_text(encoding="utf-8")
        self.assertEqual(_tables(text), {k: tuple(v) for k, v in tn.TABLES.items()})
        self.assertEqual(_constants(text), tn.CONSTANTS)

    def test_the_product_pools(self):
        from mod_editor.core import nfl2k5_team_need as tn
        self.assertEqual(tn.POOL[10], tn.LB)                    # OLB is an alias of LB in the product
        self.assertEqual(tn.SEATS[10], 0)
        self.assertEqual((tn.SEATS[3], tn.SEATS[4], tn.SEATS[11]), (3, 3, 4))
        self.assertTrue(all(n <= s for n, s in zip(tn.NEED_SEATS, tn.SEATS)))
        self.assertEqual((tn.NEED_SEATS[tn.FB], tn.NEED_SEATS[1], tn.NEED_SEATS[2]), (0, 0, 0))

    def test_present_and_healthy(self):
        import struct
        from mod_editor.core import nfl2k5_team_need as tn
        rec = bytearray(0x54)
        self.assertTrue(tn.present(bytes(rec)) and tn.healthy(bytes(rec)))
        struct.pack_into("<I", rec, 0x20, 0x80000000 | 2 << 22)          # out 2 weeks: present, not healthy
        self.assertTrue(tn.present(bytes(rec)))
        self.assertFalse(tn.healthy(bytes(rec)))
        struct.pack_into("<I", rec, 0x20, 0x80000000 | 3 << 22)          # out 3 weeks: not present
        self.assertFalse(tn.present(bytes(rec)))
        struct.pack_into("<I", rec, 0x20, 0)
        struct.pack_into("<I", rec, 0x24, 0x40000000)                    # a status bit
        self.assertFalse(tn.present(bytes(rec)))

    def test_the_header_compiles_freestanding(self):
        if not shutil.which("gcc"):
            raise unittest.SkipTest("gcc is needed")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "t.c"
            src.write_text('#include "team_need.h"\nunsigned f(const unsigned char *p, const unsigned char *s) '
                           '{ return tn_present(p) + tn_healthy(p) + tn_row(p) + tn_points(0x3F000000u) + '
                           'tn_percentile(s, 4, 80) + TN_SEATS[3] + TN_POOL[10] + TN_NEED_SEATS[4] + TN_PREMIUM[0] '
                           '+ TN_CUT_MIN[11]; }\n', encoding="utf-8")
            subprocess.run(["gcc", "-m32", "-Os", "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra", "-Werror",
                            "-I", str(HEADER.parent), "-c", str(src), "-o", str(Path(tmp) / "t.o")], check=True)

    def test_points_rounds_like_the_room(self):
        from mod_editor.core import nfl2k5_team_need as tn
        import struct
        for value in (0.0, 0.5, 0.75, 0.875, 1.0):
            bits = struct.unpack("<I", struct.pack("<f", value))[0]
            self.assertEqual(tn.points(bits), min(100, round(value * 100)) if value < 1 else 100)


if __name__ == "__main__":
    unittest.main()
