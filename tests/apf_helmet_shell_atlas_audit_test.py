"""Focused guards for the headless whole-shell APF crest-atlas audit."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for search_root in (ROOT, TOOLS):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import apf_helmet_shell_atlas_audit as audit  # noqa: E402


class ShellAtlasAuditTests(unittest.TestCase):
    def test_annulus_metrics_identify_two_simple_boundaries(self) -> None:
        # A four-cell ring around a square hole.
        faces = [
            (0, 1, 5), (0, 5, 4),
            (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6),
            (3, 0, 4), (3, 4, 7),
        ]
        result = audit._boundary_metrics(faces)
        self.assertTrue(result["is_annulus"])
        self.assertEqual(result["euler_characteristic"], 0)
        self.assertEqual(result["boundary_cycle_vertex_counts"], [4, 4])

    def test_uv_determinant_has_a_stable_sign(self) -> None:
        uv = {0: (0.0, 0.0), 1: (1.0, 0.0), 2: (1.0, 1.0)}
        self.assertGreater(audit._determinant((0, 1, 2), uv), 0.0)
        self.assertLess(audit._determinant((0, 2, 1), uv), 0.0)

    def test_audit_is_headless_path_agnostic_and_does_not_rewrite_uvs(self) -> None:
        source = (TOOLS / "apf_helmet_shell_atlas_audit.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--source-0a", required=True', source)
        self.assertIn('"source_uv_stream_reused_exactly": True', source)
        self.assertIn('"decoded_triangle_count_after": 0', source)
        self.assertNotIn("Xenia", source)
        self.assertNotIn("/media/", source)
        self.assertNotIn("write_bytes", source)


if __name__ == "__main__":
    unittest.main()
