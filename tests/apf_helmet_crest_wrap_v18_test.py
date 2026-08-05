"""Compatibility gates for the retired V18 crest module names.

V18 is no longer a production algorithm.  The two historical imports are
thin aliases to the dynamic v20 writer/verifier so an old local automation
script fails or succeeds under the same current safety contract.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as current_patch  # noqa: E402
import apf_helmet_crest_wrap_verify as current_verify  # noqa: E402
import apf_helmet_crest_wrap_v18_patch as legacy_patch  # noqa: E402
import apf_helmet_crest_wrap_v18_verify as legacy_verify  # noqa: E402


class V18CompatibilityAliasTest(unittest.TestCase):
    def test_legacy_names_resolve_to_the_current_v20_contract(self) -> None:
        self.assertEqual(legacy_patch.SCHEMA, current_patch.SCHEMA)
        self.assertEqual(legacy_verify.VERIFY_SCHEMA, current_verify.VERIFY_SCHEMA)
        self.assertIs(legacy_patch.build_patch, current_patch.build_patch)
        self.assertIs(legacy_verify.verify_outer, current_verify.verify_outer)
        self.assertEqual(
            legacy_patch.OPERATION,
            "route_shell_draw_to_crest_atlas_and_neutralize_overlay",
        )

    def test_wrong_source_still_fails_closed_through_legacy_name(self) -> None:
        rgba = bytearray(bytes((0, 0, 0, 136)) * (512 * 512))
        rgba[(256 * 512 + 256) * 4 : (256 * 512 + 256) * 4 + 4] = bytes(
            (255, 0, 0, 136)
        )
        with self.assertRaisesRegex(legacy_patch.PatchError, "outer.*allocation"):
            legacy_patch.build_patch(
                b"not retail outer 1310",
                design_rgba=bytes(rgba),
            )


if __name__ == "__main__":
    unittest.main()
