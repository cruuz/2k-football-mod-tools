"""Retail-free checks for the read-only home-field audit's evidence handling."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("s2_audit", ROOT / "tools" / "b765" / "s2_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class FieldAuditTests(unittest.TestCase):
    def test_home_scope_has_32_unique_venues_and_no_anniversary_bundles(self):
        self.assertEqual(len(audit.TEAM_PREFIXES), 32)
        self.assertEqual(len(set(audit.TEAM_PREFIXES.values())), 32)
        self.assertEqual(audit.TEAM_PREFIXES["ATL"], "s01")
        self.assertEqual(audit.TEAM_PREFIXES["HOU"], "s37")
        self.assertFalse(set(audit.TEAM_PREFIXES.values()) & {"s31", "s39", "s40", "s41", "s42", "s43", "s44", "s45"})
        self.assertEqual(len(audit.CODES), 9)

    def test_teams_reject_unknown_and_duplicate_names(self):
        for value in ("ATL,ATL", "NOT_A_TEAM"):
            with self.assertRaises(ValueError):
                audit.selected_teams(value)

    def test_strip_and_fan_draws_are_not_silently_dropped(self):
        # Native fields store almost all paint quads as triangle strips.
        self.assertEqual(audit.triangle_indices(5, [0, 1, 2, 3]), [0, 1, 2, 2, 1, 3])
        self.assertEqual(audit.triangle_indices(6, [0, 1, 2, 3]), [0, 1, 2, 0, 2, 3])
        self.assertEqual(audit.triangle_indices(5, [0, 1, 2, 2, 3, 4]), [0, 1, 2, 3, 2, 4])
        self.assertEqual(audit.triangle_indices(1, [0, 1]), [])

    def test_p8_reads_stored_mips_instead_of_regenerating(self):
        import numpy as np
        from mod_editor.core import nfl2k5_modern_metlife as mm
        tx, _inv, _rr, _header, _stw = mm._tools()
        base = tx.swizzle_2d(bytes([1] * 16), 4, 4, 1)
        mip = tx.swizzle_2d(bytes([2] * 4), 2, 2, 1)
        palette = np.zeros((256, 4), dtype=np.uint8)
        palette[1] = (0, 0, 255, 255)  # stored BGRA -> red
        palette[2] = (255, 0, 0, 255)  # stored BGRA -> blue
        data = base + mip + palette.tobytes()
        row = dict(width=4, height=4, mip_levels=2, pixel_offset=0, palette_offset=20)
        levels, used, raw = audit.read_mips(data, 0, row)
        self.assertEqual(tuple(levels[0][0, 0]), (255, 0, 0, 255))
        self.assertEqual(tuple(levels[1][0, 0]), (0, 0, 255, 255))
        self.assertEqual(used, [1, 1])
        self.assertEqual(raw, palette.tobytes())

    def test_p8_refuses_broken_native_mip_allocation(self):
        row = dict(width=4, height=4, mip_levels=2, pixel_offset=0, palette_offset=19)
        with self.assertRaisesRegex(ValueError, "allocation mismatch"):
            audit.read_mips(bytes(1044), 0, row)

    def test_native_projection_keeps_top_side_handedness(self):
        import numpy as np
        # Tiny asymmetric native quad: U grows along +z, V along +x.
        # +x projects upward. Reversing that sign mirrors the lettering.
        positions = np.array([[-2000, 0, -5000], [2000, 0, -5000],
                              [-2000, 0, 5000], [2000, 0, 5000]], dtype=float)
        uvs = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=float)
        texture = np.array([[[255, 0, 0, 255], [0, 255, 0, 255]],
                            [[0, 0, 255, 255], [255, 255, 255, 255]]], dtype=np.uint8)
        draw = dict(material="center_logo", positions=positions, uvs=uvs,
                    indices=np.array([0, 1, 2, 2, 1, 3]))
        image = np.asarray(audit.field_preview([draw], {"center_logo": texture}, size=(100, 100)))
        self.assertGreater(image[20, 20, 2], image[20, 20, 0])  # top-left is blue
        self.assertGreater(image[80, 20, 0], image[80, 20, 2])  # bottom-left is red


if __name__ == "__main__":
    unittest.main()
