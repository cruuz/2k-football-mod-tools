"""Do not relabel create-team or franchise-office art as stock midfield art."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import unittest

_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY = _ROOT / "reports/assets/nfl2k5_txtr_inventory.json"
_XBE = _ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"


class TextureCorpusBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = json.loads(_INVENTORY.read_text(encoding="utf-8"))["textures"]

    def test_center_logo_is_exactly_the_create_team_outer_range(self) -> None:
        rows = [row for row in self.rows if row["name"] == "center_logo"]
        self.assertEqual(len(rows), 126)
        self.assertEqual([row["outer_index"] for row in rows], list(range(384, 510)))
        self.assertTrue(all(
            row["format_name"] == "P8"
            and (row["width"], row["height"]) == (256, 256)
            for row in rows
        ))

    def test_the_other_numbered_teamlogo_library_is_a_distinct_85_rows(self) -> None:
        rows = [
            row for row in self.rows
            if row["name"].endswith("_teamlogo_00_h0")
        ]
        self.assertEqual(len(rows), 85)
        self.assertEqual([row["outer_index"] for row in rows], list(range(24, 109)))
        self.assertTrue(all(row["name"] != "center_logo" for row in rows))


@unittest.skipUnless(_XBE.is_file(), "retail NFL 2K5 executable is absent")
class FranchiseOfficeStaticOwnerTests(unittest.TestCase):
    def test_numbered_teamlogo_format_is_loaded_into_the_franchise_scene(self) -> None:
        payload = _XBE.read_bytes()
        # .string_ raw 0x00AEF000 maps to VA 0x00E60320.
        for offset, text in (
            (0x00B0B650, "%s_teamlogo_00_h0\0"),
            (0x00B0B688, "FRANCHISE2\0"),
            (0x00B0B6A0, "coach_desk\0"),
            (0x00B0B6B8, "teamlogo\0"),
        ):
            encoded = text.encode("utf-16le")
            self.assertEqual(payload[offset:offset + len(encoded)], encoded)
        # Function VA 0x00142AF0 formats the current team name into that
        # pattern, asks the resource loader for TXTR, and its caller stores the
        # result on the named scene element. These exact immediates keep the
        # classification independently reproducible without shipping bytes.
        function_raw = 0x00132AF0
        body = payload[function_raw:function_raw + 0x3A]
        self.assertIn(b"\xBA" + struct.pack("<I", 0x00E7C970), body)
        self.assertIn(b"\xBA" + b"TXTR", body)
        caller_raw = 0x00132BB0
        caller = payload[caller_raw:caller_raw + 0x120]
        self.assertIn(struct.pack("<I", 0x00E7C9A8), caller)  # FRANCHISE2
        self.assertIn(struct.pack("<I", 0x00E7C9C0), caller)  # coach_desk
        self.assertIn(struct.pack("<I", 0x00E7C9D8), caller)  # teamlogo
        self.assertIn(b"\xE8\x5A\xFE\xFF\xFF", caller)    # call 0x142AF0


if __name__ == "__main__":
    unittest.main()
