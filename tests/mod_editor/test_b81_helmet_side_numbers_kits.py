"""b81 helmet-sides: the Chargers' home and road kits take helmet-number route 5; no other kit changes route.

The disc checks run on a pair of private images named by the environment: NFL2K5_B81_BASE_DISC (a standard build
before this change) and NFL2K5_B81_HELMET_SIDES_DISC (the same disc after ``nfl2k5_modpack.py edit-helmet-sides``).
"""
from __future__ import annotations

import os
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from mod_editor.core import nfl2k5_helmet_side_numbers as sides  # noqa: E402

BASE = os.environ.get("NFL2K5_B81_BASE_DISC", "")
STAGED = os.environ.get("NFL2K5_B81_HELMET_SIDES_DISC", "")
KIT_NAME = re.compile(r"^([0-9]{2})([HA])([0-9]{1,2})\.IFF$", re.I)


def all_routes(path: str) -> dict[str, int]:
    """Every kit package's helmet-number route (Unif body +0x3C)."""
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    out = {}
    with bump._Image.open(Path(path), writable=False) as image:
        index = bump._parsed_index(image)
        for entry in index.entries:
            name = bump.logical_name_for(entry.name_id) or ""
            m = KIT_NAME.match(name)
            if not m:
                continue
            head = image.read_segments(index.sub_extents(entry, 0, 0x70))
            assert head[:4] == b"Unif" and struct.unpack_from("<I", head, 4)[0] == 80, name
            out[m.group(1) + m.group(2).upper() + str(int(m.group(3)))] = struct.unpack_from("<I", head, 0x5C)[0]
    return out


class ConstantsTests(unittest.TestCase):
    def test_only_the_chargers_primaries_move_from_route_2_to_route_5(self):
        self.assertEqual(sides.KITS, ("24H0", "24A0"))
        self.assertEqual((sides.ROUTE_BEFORE, sides.ROUTE), (2, 5))
        self.assertEqual(sides.UNIF_CHUNK_HEADER + sides.UNIF_ROUTE_OFFSET, 0x5C)   # payload +0x0C (accessor 0x8E830)

    def test_a_missing_or_foreign_image_reads_foreign(self):
        self.assertEqual(sides.image_status(ROOT / "no-such-disc.iso"), "foreign")
        self.assertEqual(sides.kit_status(ROOT / "no-such-disc.iso"), "foreign")


@unittest.skipUnless(BASE and STAGED and Path(BASE).is_file() and Path(STAGED).is_file(),
                     "NFL2K5_B81_BASE_DISC and NFL2K5_B81_HELMET_SIDES_DISC (private images) required")
class DiscTests(unittest.TestCase):
    def test_every_other_kit_keeps_its_route(self):
        before, after = all_routes(BASE), all_routes(STAGED)
        self.assertEqual(set(before), set(after))
        changed = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        self.assertEqual(changed, {"24H0": (2, 5), "24A0": (2, 5)})
        self.assertNotIn(5, {v for k, v in after.items() if k not in sides.KITS})

    def test_states(self):
        self.assertEqual(sides.image_status(BASE), "retail")
        self.assertEqual(sides.image_status(STAGED), "applied")
        self.assertEqual(sides.kit_routes(STAGED), {"24H0": 5, "24A0": 5})


if __name__ == "__main__":
    unittest.main()
