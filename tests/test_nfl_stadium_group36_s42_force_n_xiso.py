#!/usr/bin/env python3
"""Structural and refusal tests for the s42 global force-night diagnostic."""

from __future__ import annotations

import ast
import hashlib
import json
import struct
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_group36_s42_force_n_xiso_patch as writer  # noqa: E402
import nfl_stadium_group36_s42_force_n_xiso_verify as verifier  # noqa: E402


XBE_PATH = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"


class ForceNTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE_PATH.read_bytes()
        visibility = bytearray(cls.retail)
        visibility[writer.S42_UNLOCK_XBE_OFFSET:
                   writer.S42_UNLOCK_XBE_OFFSET + 4] = writer.S42_UNLOCK_VISIBLE_BYTES
        digest = bytes.fromhex(writer.xbe_sha1(
            bytes(visibility[writer.DATA_RAW:writer.DATA_RAW + writer.DATA_RAW_SIZE])
        ))
        assert digest == writer.DATA_VISIBILITY_DIGEST
        visibility[writer.DATA_SECTION_DIGEST:
                   writer.DATA_SECTION_DIGEST + 20] = digest
        cls.source = bytes(visibility)
        assert hashlib.sha256(cls.source).hexdigest() == writer.DEFAULT_XBE_SOURCE_SHA256

    def test_one_byte_control_flow_patch_is_unique(self) -> None:
        context = bytes.fromhex("85c07405bf6e000000668974240e66897c240c")
        self.assertEqual(self.source.count(context), 1)
        self.assertEqual(
            self.source[writer.TIME_BRANCH_XBE_OFFSET:
                        writer.TIME_BRANCH_XBE_OFFSET + 2],
            b"\x74\x05",
        )
        self.assertEqual(
            writer.TEXT_RAW + writer.TIME_BRANCH_VA - writer.TEXT_VA,
            writer.TIME_BRANCH_XBE_OFFSET,
        )
        self.assertEqual(writer.DISPLACEMENT_ABSOLUTE, 0x0029BC61)

    def test_writer_produces_exact_rehashed_xbe(self) -> None:
        output, record = writer.make_patched_xbe(self.source)
        self.assertEqual(hashlib.sha256(output).hexdigest(), writer.DEFAULT_XBE_OUTPUT_SHA256)
        self.assertEqual(len(record["changed_xbe_offsets"]), 21)
        self.assertEqual(
            record["changed_xbe_offsets"],
            [*range(0x394, 0x3A8), 0x52C61],
        )
        self.assertEqual(output[0x52C60:0x52C62], b"\x74\x00")
        self.assertEqual(output[0x394:0x3A8], writer.TEXT_OUTPUT_DIGEST)
        self.assertEqual(output[4:0x104], self.source[4:0x104])

    def test_independent_parser_agrees_without_writer_import(self) -> None:
        output, _ = writer.make_patched_xbe(self.source)
        source_record = verifier.parse_xbe(self.source, patched=False)
        output_record = verifier.parse_xbe(output, patched=True)
        self.assertEqual(source_record["section_digest"], writer.TEXT_SOURCE_DIGEST.hex())
        self.assertEqual(output_record["section_digest"], writer.TEXT_OUTPUT_DIGEST.hex())
        self.assertEqual(
            verifier.independent_xbe_difference(self.source, output),
            verifier.CHANGED_XBE_OFFSETS,
        )
        tree = ast.parse(
            (ROOT / "tools/nfl_stadium_group36_s42_force_n_xiso_verify.py")
            .read_text(encoding="utf-8")
        )
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertNotIn("nfl_stadium_group36_s42_force_n_xiso_patch", imports)

    def test_stale_text_digest_fails_closed(self) -> None:
        stale = bytearray(self.source)
        stale[writer.TIME_DISPLACEMENT_XBE_OFFSET] = 0
        with self.assertRaisesRegex(verifier.ForceNVerifyError, "digest mismatch"):
            verifier.parse_xbe(bytes(stale), patched=True)

    def test_wrong_instruction_context_fails_closed(self) -> None:
        wrong = bytearray(self.source)
        wrong[writer.TIME_BRANCH_XBE_OFFSET] = 0x75
        with self.assertRaisesRegex(writer.ForceNPatchError, "instruction context"):
            writer.make_patched_xbe(bytes(wrong))

    def test_digest_refresh_changes_signed_header_only_as_declared(self) -> None:
        output, _ = writer.make_patched_xbe(self.source)
        headers_size = struct.unpack_from("<I", self.source, 0x108)[0]
        self.assertEqual(headers_size, writer.XBE_HEADERS_SIZE)
        self.assertNotEqual(self.source[0x104:headers_size], output[0x104:headers_size])
        self.assertEqual(self.source[4:0x104], output[4:0x104])
        self.assertFalse(
            writer.XBE_SIGNED_HEADER_SOURCE_SHA1 == writer.XBE_SIGNED_HEADER_OUTPUT_SHA1
        )

    def test_weather_store_and_format_context_are_unchanged(self) -> None:
        output, _ = writer.make_patched_xbe(self.source)
        # ESI -> [ESP+0x0e], EDI -> [ESP+0x0c], then active stadium accessor.
        fixed = bytes.fromhex("668974240e66897c240ce8ea4701008b500c")
        offset = 0x52C67
        self.assertEqual(self.source[offset:offset + len(fixed)], fixed)
        self.assertEqual(output[offset:offset + len(fixed)], fixed)

    def test_machine_spec_is_canonical_and_bounded(self) -> None:
        path = ROOT / "reports/specs/nfl2k5_group36_s42_force_n_runtime_shim.v1.json"
        raw = path.read_bytes()
        value = json.loads(raw)
        self.assertEqual(
            raw,
            (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
        )
        self.assertEqual(value["schema"], "nfl2k5_group36_s42_force_n_runtime_shim/v1")
        self.assertEqual(
            value["xdvdfs_transport"]["allowed_changed_byte_offsets_decimal"],
            [*range(0x249394, 0x2493A8), 0x29BC61],
        )
        self.assertEqual(value["xdvdfs_transport"]["actual_changed_byte_count_per_visibility_source"], 21)
        self.assertTrue(value["claims"]["offline_force_n_dataflow_proved"])
        self.assertFalse(value["claims"]["retail_signed_executable_chain_preserved"])
        self.assertFalse(value["claims"]["xemu_target_outer_loaded_proved"])
        self.assertFalse(value["claims"]["xemu_geometry_visibility_proved"])


if __name__ == "__main__":
    unittest.main()
