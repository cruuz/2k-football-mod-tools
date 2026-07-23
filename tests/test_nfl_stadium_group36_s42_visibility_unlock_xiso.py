from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_group36_s42_visibility_unlock_xiso_patch as writer  # noqa: E402
import nfl_stadium_group36_s42_visibility_unlock_xiso_verify as verifier  # noqa: E402


XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
BUILD = ROOT / "build/nfl2k5-stadium-group36-geometry-xiso-20260713"


class NflGroup36S42VisibilityUnlockXisoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_xbe = XBE.read_bytes()

    def test_exact_table_mapping_and_complete_difference_contract(self) -> None:
        for module in (writer, verifier):
            table_offset = getattr(module, "AVAILABILITY_TABLE_XBE_OFFSET",
                                   getattr(module, "TABLE_OFFSET", None))
            row = getattr(module, "S42_ROW_INDEX", getattr(module, "S42_ROW", None))
            row_size = getattr(module, "AVAILABILITY_ROW_SIZE",
                               getattr(module, "ROW_SIZE", None))
            unlock_offset = getattr(module, "S42_UNLOCK_XBE_OFFSET",
                                    getattr(module, "S42_UNLOCK_OFFSET", None))
            self.assertEqual(table_offset, 0xA8C898)
            self.assertEqual(row, 4)
            self.assertEqual(row_size, 8)
            self.assertEqual(unlock_offset, table_offset + row * row_size + 4)
            self.assertEqual(unlock_offset, 0xA8C8BC)
        self.assertEqual(writer.S42_UNLOCK_BEFORE, b"\x4b\x01\0\0")
        self.assertEqual(writer.S42_UNLOCK_AFTER, b"\0\0\0\0")
        self.assertEqual(writer.EXPECTED_CHANGED_ABSOLUTE,
                         verifier.CHANGED_ABSOLUTE)
        self.assertEqual(len(writer.EXPECTED_CHANGED_ABSOLUTE), 22)
        self.assertEqual(writer.EXPECTED_CHANGED_ABSOLUTE[:20],
                         list(range(0x24966C, 0x249680)))
        self.assertEqual(writer.EXPECTED_CHANGED_ABSOLUTE[-2:],
                         [0xCD58BC, 0xCD58BD])

    def test_writer_transform_is_accepted_by_independent_xbe_parser(self) -> None:
        output, proof = writer.make_patched_xbe(self.source_xbe)
        self.assertEqual(len(output), len(self.source_xbe))
        self.assertEqual(len(proof["changed_xbe_offsets"]), 22)
        independent_source = verifier.validate_xbe(self.source_xbe, patched=False)
        independent_output = verifier.validate_xbe(output, patched=True)
        self.assertEqual(independent_source["s42_unlock_id"], 0x14B)
        self.assertEqual(independent_output["s42_unlock_id"], 0)
        self.assertEqual(independent_output["section_digest"],
                         "8011736208bf6320358ee1b1cdaf29d421f80c24")
        self.assertEqual(hashlib.sha256(output).hexdigest(),
                         writer.DEFAULT_XBE_OUTPUT_SHA256)

    def test_fail_closed_xbe_validation_rejects_stale_digest(self) -> None:
        stale = bytearray(self.source_xbe)
        stale[writer.S42_UNLOCK_XBE_OFFSET:
              writer.S42_UNLOCK_XBE_OFFSET + 4] = writer.S42_UNLOCK_AFTER
        with self.assertRaises(writer.VisibilityPatchError):
            writer.validate_xbe(bytes(stale), patched=True)
        with self.assertRaises(verifier.VisibilityVerifyError):
            verifier.validate_xbe(bytes(stale), patched=True)

    def test_paired_manifests_pin_false_runtime_boundary(self) -> None:
        expected = {
            "s42-visible-control-workflow.json": (
                "s42_control",
                "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
                "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
            ),
            "expanded-wall-s42-visible-workflow.json": (
                "s42_expanded_wall",
                "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
                "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
            ),
        }
        false_claims = {
            "retail_signed_executable_chain_preserved",
            "xemu_boot_acceptance_proved",
            "xemu_stadium_selectability_proved",
            "xemu_target_outer_loaded_proved",
            "xemu_geometry_visibility_proved",
            "original_xbox_hardware_proved",
            "production_ready",
            "distribution_ready",
            "public_editor_exposed",
        }
        for name, (profile, output_sha, pack9_sha) in expected.items():
            with self.subTest(name=name):
                raw = (BUILD / name).read_bytes()
                value = json.loads(raw)
                self.assertEqual(raw, writer.canonical_json(value))
                self.assertEqual(value["schema"], writer.SCHEMA)
                self.assertEqual(value["source_profile"], profile)
                self.assertEqual(value["output"]["sha256"], output_sha)
                self.assertEqual(value["xdvdfs"]["pack0_sha256"],
                                 writer.S42_PACK0_SHA256)
                self.assertEqual(value["xdvdfs"]["pack9_sha256"], pack9_sha)
                self.assertEqual(value["patch"]["actual_changed_byte_count"], 22)
                for claim in false_claims:
                    self.assertIs(value["claims"][claim], False)

    def test_independent_verifier_does_not_import_writer(self) -> None:
        path = ROOT / "tools/nfl_stadium_group36_s42_visibility_unlock_xiso_verify.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertNotIn("nfl_stadium_group36_s42_visibility_unlock_xiso_patch",
                         imports)


if __name__ == "__main__":
    unittest.main()
