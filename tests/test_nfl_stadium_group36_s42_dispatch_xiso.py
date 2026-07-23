from __future__ import annotations

import ast
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_group36_s42_dispatch_xiso_patch as writer  # noqa: E402
import nfl_stadium_group36_s42_dispatch_xiso_verify as verifier  # noqa: E402


RETAIL = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"


class NflGroup36S42DispatchXisoTest(unittest.TestCase):
    def test_two_byte_contract_is_pinned_in_both_modules(self) -> None:
        for module in (writer, verifier):
            self.assertEqual(module.ASSET_BEFORE, ("s18\0").encode("utf-16le"))
            self.assertEqual(module.ASSET_AFTER, ("s42\0").encode("utf-16le"))
            self.assertEqual(module.CHANGED_RELATIVE, [2, 4])
        self.assertEqual(writer.EXPECTED_CHANGED_ABSOLUTE, [0x617A8144, 0x617A8146])
        self.assertEqual(verifier.CHANGED_ABSOLUTE, [0x617A8144, 0x617A8146])

    def test_source_profiles_are_strict_and_identical(self) -> None:
        self.assertEqual(set(writer.SOURCE_PROFILES), {"retail_control", "expanded_wall"})
        self.assertEqual(writer.SOURCE_PROFILES, verifier.SOURCE_PROFILES)
        retail = writer.prepare_source_profile(
            "retail_control", RETAIL.resolve(), None, None, None, None, None
        )
        self.assertEqual(retail[0], writer.RETAIL_XISO_SHA256)
        self.assertEqual(retail[1], writer.RETAIL_VOLUME9_SHA256)
        with self.assertRaises(writer.DispatchPatchError):
            writer.prepare_source_profile(
                "retail_control", RETAIL.resolve(), ROOT / "unexpected.json",
                None, None, None, None,
            )

    def test_pinned_retail_roster_pointer_and_string(self) -> None:
        fd = os.open(RETAIL, os.O_RDONLY)
        try:
            for module in (writer, verifier):
                result = module.validate_roster(
                    fd, module.PACK0_SECTOR * 2048, module.ASSET_BEFORE
                )
                self.assertEqual(result["stadium_index"], 18)
                self.assertEqual(result["asset_pointer_field_offset"], 0x9BC)
                self.assertEqual(result["asset_string_body_offset"], 0x76122)
                self.assertEqual(result["asset_string_absolute_offset"], 0x617A8142)
                self.assertEqual(result["unique_aligned_relative_pointer_fields"], [0x9BC])
                self.assertEqual(result["asset_code"], "s18")
        finally:
            os.close(fd)

    def test_independent_verifier_does_not_import_writer(self) -> None:
        tree = ast.parse(
            (ROOT / "tools/nfl_stadium_group36_s42_dispatch_xiso_verify.py").read_text(
                encoding="utf-8"
            )
        )
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        self.assertNotIn("nfl_stadium_group36_s42_dispatch_xiso_patch", imports)


if __name__ == "__main__":
    unittest.main()
