#!/usr/bin/env python3
"""Independent refusal tests for the checked-in APF texture format spec."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_texture_format_spec as format_spec  # noqa: E402


class ApfUniformTextureFormatSpecTest(unittest.TestCase):
    def test_immutable_v1_validates_and_keeps_exact_hash(self) -> None:
        self.assertEqual(
            format_spec.validate(format_spec.V1_SPEC),
            {"version": 1, "families": 3, "slots": 72, "mips": 24},
        )
        self.assertEqual(format_spec.V1_SPEC.stat().st_size, format_spec.V1_SPEC_SIZE)
        self.assertEqual(
            hashlib.sha256(format_spec.V1_SPEC.read_bytes()).hexdigest(),
            format_spec.V1_SPEC_SHA256,
        )

    def test_canonical_v2_validates_four_closed_families(self) -> None:
        self.assertEqual(
            format_spec.validate(),
            {"version": 2, "families": 4, "slots": 96, "mips": 33},
        )

    def test_v2_is_additive_over_immutable_v1(self) -> None:
        v1 = json.loads(format_spec.V1_SPEC.read_bytes())
        v2 = json.loads(format_spec.V2_SPEC.read_bytes())
        for family in ("jersey_color", "pants_color", "helmet_color"):
            self.assertEqual(v2["families"][family], v1["families"][family])
        self.assertEqual(set(v2["families"]) - set(v1["families"]), {"shoulder_color"})

    def test_mutated_descriptor_is_rejected(self) -> None:
        original = json.loads(format_spec.DEFAULT_SPEC.read_bytes())
        mutated = copy.deepcopy(original)
        mutated["families"]["shoulder_color"]["txtr_descriptor"]["width"] = 512
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaisesRegex(format_spec.SpecError, "TXTR descriptor"):
                format_spec.validate(path)

    def test_mutated_per_slot_allocation_is_rejected(self) -> None:
        original = json.loads(format_spec.DEFAULT_SPEC.read_bytes())
        mutated = copy.deepcopy(original)
        mutated["families"]["shoulder_color"]["per_slot_fixed_allocations"][23][6] += 2048
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaisesRegex(format_spec.SpecError, "per-slot allocation table"):
                format_spec.validate(path)

    def test_mutated_source_pin_is_rejected_before_facts_are_trusted(self) -> None:
        original = json.loads(format_spec.DEFAULT_SPEC.read_bytes())
        mutated = copy.deepcopy(original)
        mutated["source_pins"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaisesRegex(format_spec.SpecError, "source_pins"):
                format_spec.validate(path)

    def test_mutated_shoulder_sibling_span_is_rejected(self) -> None:
        original = json.loads(format_spec.DEFAULT_SPEC.read_bytes())
        mutated = copy.deepcopy(original)
        mutated["families"]["shoulder_color"]["preserved_sibling_files"][2]["parts"][1][3] -= 16
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaisesRegex(format_spec.SpecError, "shoulder preserved sibling part map"):
                format_spec.validate(path)


if __name__ == "__main__":
    unittest.main()
