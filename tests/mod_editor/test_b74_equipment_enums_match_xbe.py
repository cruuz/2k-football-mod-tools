"""Beta 74: the Edit Player equipment lists are the game's own, in the game's order.

X_Ray (#2k5-ideas, 2026-09-20): "Add in the equipment options that are missing
in the edit player section like all of the high elbow pad options, turf elbow
pad options etc." The elbow list had thirteen entries for a four-bit field
and skipped White Turf, Black Turf and Taped, so "High White" wrote the value
the game shows as White Turf and the three real High pads were unreachable.

The retail executable keeps every equipment option list as one table of
UTF-16 string pointers (0x555BC4, file 0x54B0E4). When the private extraction
is present, every list in ``ENUMS`` that the game defines is compared against
that table in order; without it, the elbow list is pinned to the recovered
order so the fix cannot regress silently.
"""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from mod_editor.core import nfl2k5_roster_records as rr

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"

GAME_ORDER = (
    "None", "White", "Black", "White/Black Stripe", "Black/White Stripe", "Black/Team Stripe",
    "Team", "White/Team Stripe", "Elastic", "Neoprene", "White Turf", "Black Turf", "Taped",
    "High White", "High Black", "High Team",
)


def _xbe_option_lists(data):
    """Every option list in the executable's equipment table, keyed by its first labels."""
    base = struct.unpack_from("<I", data, 0x104)[0]
    count = struct.unpack_from("<I", data, 0x11C)[0]
    headers = struct.unpack_from("<I", data, 0x120)[0]
    sections = [struct.unpack_from("<IIIII", data, headers - base + i * 0x38) for i in range(count)]

    def read_label(va):
        for _flags, sva, _vsize, raw, rsize in sections:
            if sva <= va < sva + rsize:
                off = raw + (va - sva)
                end = data.find(b"\0\0", off)
                while end % 2:
                    end = data.find(b"\0\0", end + 1)
                return data[off:end].decode("utf-16le")
        return None

    table = []
    offset = 0x54B0E4
    while True:
        pointer = struct.unpack_from("<I", data, offset)[0]
        label = read_label(pointer) if pointer else None
        table.append(label)
        offset += 4
        if len(table) > 80 or (label is None and pointer):
            break
    # Split on the game's list starts: every equipment list but shoes begins
    # with "None"; the Yes/No pairs after the elbow list begin with "No".
    lists, current = [], []
    for label in table:
        if label in ("None", "Style 1", "No") and current:
            lists.append(tuple(current))
            current = []
        if label is None:
            if current:
                lists.append(tuple(current))
                current = []
            continue
        current.append(label)
    if current:
        lists.append(tuple(current))
    return lists


class EquipmentEnumTests(unittest.TestCase):
    def test_elbow_pads_are_the_game_order_and_fill_the_field(self):
        self.assertEqual(rr.ELBOWS, GAME_ORDER)
        self.assertEqual(len(rr.ELBOWS), 16)
        self.assertEqual(rr.ENUMS["left_elbow"], rr.ELBOWS)
        self.assertEqual(rr.ENUMS["right_elbow"], rr.ELBOWS)
        # The two-part left field and the right field are each four bits.
        widths = {f.name: f.width for f in rr.FIELDS if f.name in
                  ("left_elbow_low", "left_elbow_high", "right_elbow")}
        self.assertEqual(widths, {"left_elbow_low": 2, "left_elbow_high": 2, "right_elbow": 4})

    @unittest.skipUnless(XBE.is_file(), "private retail executable unavailable")
    def test_every_equipment_list_matches_the_executable_table(self):
        lists = _xbe_option_lists(XBE.read_bytes())
        expected = {
            "left_glove": rr.GLOVES, "left_shoe": rr.SHOES, "left_wrist": rr.WRISTS,
            "sleeves": rr.SLEEVES, "neck_roll": rr.NECK_ROLLS, "turtleneck": rr.TURTLENECKS,
            "left_elbow": rr.ELBOWS,
        }
        # Sleeves and turtlenecks share one list; membership, not inversion.
        missing = sorted(name for name, options in expected.items() if tuple(options) not in lists)
        self.assertEqual(missing, [], f"lists in the executable: {lists}")


if __name__ == "__main__":
    unittest.main()
