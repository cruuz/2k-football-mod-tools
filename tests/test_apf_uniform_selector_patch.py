#!/usr/bin/env python3
"""Focused tests for APF's deterministic built-in all-family selector writer."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_selector_patch as writer  # noqa: E402
import apf_uniform_selector_verify as verifier  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
RECIPE = ROOT / "reports/asset_samples/apf_roster/uniform_all_families_built_in_capacity.v1.json"


class APFUniformSelectorPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.writer_source = writer.transport._validate_source(SOURCE)
        with mock.patch.object(
            writer.transport, "_validate_source", return_value=cls.writer_source
        ):
            cls.result = writer.build_patch(SOURCE, RECIPE)
        (
            _,
            _,
            _,
            cls.source_entry,
            _,
            cls.source_decoded,
            _,
        ) = cls.writer_source
        cls.output_iff = verifier.base.parse_iff(cls.result.entry)
        cls.output_decoded, _, _ = verifier.base.decode_h7a(cls.output_iff.payload)
        with verifier.base.BoundFile(
            verifier.ALLOCATION_REPORT, "allocation report"
        ) as bound:
            cls.allocation, _ = verifier.load_compact_authority(
                bound,
                verifier.ALLOCATION_REPORT_SIZE,
                verifier.ALLOCATION_REPORT_SHA256,
                "apf2k8_uniform_selector_allocation/v1",
                "allocation report",
            )
        with verifier.base.BoundFile(
            verifier.CAPACITY_REPORT, "capacity report"
        ) as bound:
            cls.capacity, _ = verifier.load_compact_authority(
                bound,
                verifier.CAPACITY_REPORT_SIZE,
                verifier.CAPACITY_REPORT_SHA256,
                "apf2k8_uniform_selector_capacity_probe/v1",
                "capacity report",
            )
        cls.source_iff = verifier.base.parse_iff(cls.source_entry)
        (
            cls.verifier_source_decoded,
            cls.source_tokens,
            cls.source_consumed,
        ) = verifier.base.decode_h7a(cls.source_iff.payload)
        cls.verifier_layout = verifier.derive_selector_layout(
            cls.verifier_source_decoded,
            cls.allocation,
            require_retail_vectors=True,
        )
        with verifier.base.BoundFile(RECIPE, "recipe") as bound:
            cls.recipe, cls.recipe_raw = verifier.base.load_canonical_json(
                bound, verifier.MAX_RECIPE_BYTES, "recipe"
            )

    def test_exact_combined_capacity_witness_is_reproduced(self) -> None:
        manifest = self.result.manifest
        self.assertEqual(manifest["recipe"]["family_count"], 11)
        self.assertEqual(manifest["recipe"]["assignment_count"], 264)
        self.assertEqual(
            manifest["recipe"]["changed_team_family_assignment_count"], 95
        )
        self.assertEqual(manifest["preservation"]["authorized_decoded_byte_count"], 528)
        self.assertEqual(manifest["preservation"]["decoded_changed_byte_count"], 190)
        self.assertEqual(
            manifest["preservation"]["changed_decoded_offsets_sha256"],
            "605468e121e70934e7e5b40664ebb45264e4946b851b8de6e898d16f87948ca0",
        )
        self.assertEqual(
            manifest["preservation"]["decoded_output_sha256"],
            "90bc181b311f0f637fe2ab994845ae10a5b3202652d633c990e6b9450a79387f",
        )
        self.assertEqual(manifest["compression"]["payload_size_after"], 435_528)
        self.assertEqual(manifest["compression"]["headroom_bytes_after"], 496)
        self.assertEqual(
            manifest["compression"]["payload_sha256_after"],
            "3ecaf03d32456650a721d515ca47f2b4373347e21a85678df2e9b52b1ba881c8",
        )
        self.assertEqual(
            manifest["result"]["outer_entry_sha256"],
            "5ecd30925837e8e847a00d1b81474955455bae5d94de0778998af26c1c59ec1d",
        )

    def test_all_families_reach_their_built_in_upper_bound(self) -> None:
        source_layout = writer.derive_selector_layout(
            self.source_decoded, self.allocation, require_retail_vectors=True
        )
        output_layout = writer.derive_selector_layout(
            self.output_decoded, self.allocation, require_retail_vectors=False
        )
        expected_changed = {
            "glove": 0,
            "helmet": 18,
            "jersey": 15,
            "logo": 0,
            "textlogo": 0,
            "font": 4,
            "number": 17,
            "pants": 13,
            "shoe": 0,
            "shoulder": 10,
            "sock": 18,
        }
        for family in self.result.manifest["families"]:
            name = family["family"]
            with self.subTest(family=name):
                self.assertEqual(family["changed_team_count"], expected_changed[name])
                self.assertEqual(
                    len(set(output_layout.families[name].assets[:24])),
                    family["catalog_capacity_upper_bound"],
                )
                self.assertEqual(
                    output_layout.families[name].offsets,
                    source_layout.families[name].offsets,
                )
                self.assertEqual(
                    output_layout.families[name].record_indices,
                    source_layout.families[name].record_indices,
                )

    def test_only_both_bank_byte_zero_values_change(self) -> None:
        differences = [
            offset
            for offset, pair in enumerate(zip(self.source_decoded, self.output_decoded))
            if pair[0] != pair[1]
        ]
        authorized: set[int] = set()
        for family in self.recipe["families"]:
            layout = self.verifier_layout.families[family["family"]]
            for assignment in family["assignments"]:
                if assignment["expected_retail_asset_index"] != assignment["replacement_asset_index"]:
                    authorized.update(layout.offsets[assignment["team_index"]])
        self.assertEqual(set(differences), authorized)
        self.assertEqual(len(differences), 190)
        for offset in authorized:
            self.assertEqual(
                self.source_decoded[offset + 1 : offset + 8],
                self.output_decoded[offset + 1 : offset + 8],
            )
        # Every online/user selector record, including unowned slots, remains exact.
        for team in range(24, 40):
            for family in self.verifier_layout.families.values():
                for offset in family.offsets[team]:
                    self.assertEqual(
                        self.source_decoded[offset : offset + 8],
                        self.output_decoded[offset : offset + 8],
                    )

    def _write_recipe(self, document: dict[str, object]) -> Path:
        temporary = tempfile.NamedTemporaryFile("wb", delete=False)
        temporary.write(writer.transport.canonical_json_bytes(document))
        temporary.close()
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_recipe_rejects_family_slot_expected_replacement_and_scope_tampering(self) -> None:
        cases: list[tuple[str, callable]] = [
            ("slot", lambda value: value["families"][0].__setitem__("selector_slot", 3)),
            ("expected", lambda value: value["families"][1]["assignments"][0].__setitem__("expected_retail_asset_index", 0)),
            ("replacement", lambda value: value["families"][2]["assignments"][8].__setitem__("replacement_asset_index", 22)),
            ("scope", lambda value: value["scope"]["team_indices"].__setitem__(23, 24)),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                changed = copy.deepcopy(self.recipe)
                mutate(changed)
                with self.assertRaisesRegex(writer.PatchError, "differs from"):
                    writer.load_recipe(self._write_recipe(changed))

    def test_independent_verifier_reconstructs_writer_entry_and_manifest(self) -> None:
        expected_entry, wanted, manifest, differences = verifier.build_expected(
            self.source_entry,
            self.source_iff,
            self.verifier_source_decoded,
            self.source_tokens,
            self.source_consumed,
            self.verifier_layout,
            self.recipe,
            self.recipe_raw,
            self.allocation,
            self.capacity,
            "fixture-0A",
            "f" * 64,
        )
        self.assertEqual(expected_entry, self.result.entry)
        self.assertEqual(wanted, self.output_decoded)
        self.assertEqual(len(differences), 190)
        for key in (
            "claim_flags",
            "compression",
            "families",
            "mode",
            "preservation",
            "recipe",
            "schema",
            "source",
        ):
            self.assertEqual(manifest[key], self.result.manifest[key])
        self.assertEqual(
            {key: value for key, value in manifest["result"].items() if key != "copied_volume"},
            self.result.manifest["result"],
        )

    def test_verifier_has_no_writer_or_allocation_import(self) -> None:
        tree = ast.parse(
            (ROOT / "tools/apf_uniform_selector_verify.py").read_text(encoding="utf-8")
        )
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("apf_uniform_selector_patch", imported)
        self.assertNotIn("apf_uniform_selector_allocation", imported)

    def _rebuild_decoded(self, decoded: bytes) -> bytes:
        payload, _ = verifier.base.encode_preserving_h7a(
            self.source_tokens,
            len(self.source_iff.payload) - self.source_consumed,
            decoded,
        )
        stored = struct.pack(
            ">5I",
            verifier.base.H7A_MAGIC,
            verifier.base.DECODED_SIZE,
            verifier.base.H7A_HEADER_SIZE + len(payload),
            verifier.base.H7A_UNKNOWN,
            verifier.base.H7A_SHIFT,
        ) + payload
        header = bytearray(self.source_entry[: verifier.base.IFF_HEADER_SIZE])
        struct.pack_into(
            ">8I",
            header,
            verifier.base.IFF_BLOCK_TABLE_OFFSET,
            verifier.base.IFF_BLOCK_HASH,
            verifier.base.IFF_BLOCK_HASH,
            0x20,
            verifier.base.DECODED_SIZE,
            verifier.base.H7A_UNKNOWN,
            verifier.base.IFF_HEADER_SIZE,
            len(stored),
            0,
        )
        file_length = verifier.base.IFF_HEADER_SIZE + len(stored)
        struct.pack_into(">I", header, 0x08, file_length)
        active = bytes(header) + stored + self.source_iff.footer
        return active + bytes(verifier.base.OUTER_SIZE - len(active))

    def test_one_bank_only_edit_is_rejected_before_output_admission(self) -> None:
        family = self.verifier_layout.families["helmet"]
        changed = bytearray(self.source_decoded)
        first_bank, _second_bank = family.offsets[1]
        changed[first_bank] = 2
        entry = self._rebuild_decoded(bytes(changed))
        parsed = verifier.base.parse_iff(entry)
        decoded, _, _ = verifier.base.decode_h7a(parsed.payload)
        with self.assertRaisesRegex(verifier.VerifyError, "bank values differ"):
            verifier.derive_selector_layout(
                decoded, self.allocation, require_retail_vectors=False
            )


if __name__ == "__main__":
    unittest.main()
