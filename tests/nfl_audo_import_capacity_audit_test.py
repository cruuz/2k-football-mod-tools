#!/usr/bin/env python3
"""Focused regression tests for the read-only NFL 2K5 AUDO capacity audit."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_audo_import_capacity_audit as audit  # noqa: E402


REPORT = ROOT / "reports/assets/nfl2k5_audo_import_capacity.json"
MATRIX = ROOT / "reports/assets/nfl2k5_audo_import_capacity.tsv"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NflAudoImportCapacityAuditTests(unittest.TestCase):
    def test_all_source_pins_are_complete_sha256_values(self) -> None:
        audit.validate_source_constants()
        self.assertEqual(set(audit.PACK_HASHES), set("0123456789ABCDEF"))
        self.assertTrue(all(SHA256_RE.fullmatch(value) for value in audit.PACK_HASHES.values()))
        self.assertEqual(
            audit.PACK_HASHES["A"],
            "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
        )
        self.assertEqual(
            audit.PACK_HASHES["F"],
            "376f2d0ea4a5c01453408fbd9747bffbfb8715b56a7e3f41339158217b07da8d",
        )

    def test_deterministic_encoder_contract_covers_mono_and_stereo(self) -> None:
        expected_hashes = {
            1: "cbd9998130c55373268beeb5f3b554200253eefb808bd52cb4cdb0df1da6117c",
            2: "be9ae8318c1b1abc483413dc0e098da20a02e81a416ac39b134e5b01bfe57c31",
        }
        for channels, expected_hash in expected_hashes.items():
            with self.subTest(channels=channels):
                contract = audit.probe_contract(channels)
                self.assertEqual(contract["channels"], channels)
                self.assertEqual(contract["frame_count"], 64)
                self.assertEqual(contract["encoded_block_bytes"], 36 * channels)
                self.assertEqual(contract["encoded_block_sha256"], expected_hash)
                self.assertTrue(contract["block_predictor_samples_exact"])
                self.assertTrue(contract["stored_channel_subblocks_consecutively"])

    def test_classifier_never_promotes_ambiguous_or_unencodable_rows(self) -> None:
        classification, _ = audit.classify_record(
            key=(3, 101), structurally_encodable=True, name_group_size=2, content_group_size=2
        )
        self.assertEqual(classification, audit.CLASS_CANDIDATE)

        classification, _ = audit.classify_record(
            key=(9, 33), structurally_encodable=True, name_group_size=1, content_group_size=1
        )
        self.assertEqual(classification, audit.CLASS_STRUCTURAL)

        for key, structurally_encodable, name_count, content_count in (
            ((9, 33), False, 1, 1),
            ((9, 33), True, 2, 1),
            ((9, 33), True, 1, 2),
            ((3, 101), False, 1, 1),
        ):
            with self.subTest(
                key=key,
                structurally_encodable=structurally_encodable,
                name_count=name_count,
                content_count=content_count,
            ):
                classification, reasons = audit.classify_record(
                    key=key,
                    structurally_encodable=structurally_encodable,
                    name_group_size=name_count,
                    content_group_size=content_count,
                )
                self.assertEqual(classification, audit.CLASS_EXPORT_ONLY)
                self.assertTrue(reasons)

    def test_committed_report_is_canonical_complete_and_fail_closed(self) -> None:
        payload = REPORT.read_bytes()
        report = json.loads(payload)
        self.assertEqual(payload, audit.canonical_json(report))
        self.assertEqual(report["schema"], audit.SCHEMA)
        self.assertEqual(
            {item["name"]: item["sha256"] for item in report["source"]["packs"]},
            audit.PACK_HASHES,
        )
        self.assertEqual(report["source"]["xiso"]["sha256"], audit.SOURCE_XISO_SHA256)
        self.assertEqual(
            report["summary"],
            {
                "channel_counts": {"1": 806, "2": 44},
                "classification_counts": {
                    audit.CLASS_CANDIDATE: 1,
                    audit.CLASS_EXPORT_ONLY: 697,
                    audit.CLASS_STRUCTURAL: 152,
                },
                "duplicate_name_group_count": 7,
                "equal_decoded_content_group_count": 53,
                "equal_payload_group_count": 53,
                "equal_resource_span_group_count": 91,
                "record_count": 850,
                "sample_rate_counts": {
                    "11025": 737,
                    "12000": 1,
                    "14000": 5,
                    "15000": 1,
                    "16000": 16,
                    "18000": 1,
                    "20000": 3,
                    "22050": 84,
                    "32000": 2,
                },
                "unique_name_count": 167,
                "used_pack_record_counts": {"0": 118, "1": 385, "2": 226, "C": 121},
            },
        )
        self.assertEqual(
            report["claims"],
            {
                "additional_fixed_slot_writer_authorized": False,
                "all_850_exported": True,
                "all_850_physical_spans_exact_and_nonoverlapping": True,
                "all_850_structurally_encodable_at_same_allocation": True,
                "generic_audo_writer_authorized": False,
                "runtime_selector_ownership_proved_count": 0,
                "runtime_visibility_proved_count": 0,
                "source_modified": False,
            },
        )

        rows = report["records"]
        self.assertEqual(len(rows), 850)
        self.assertEqual(len({row["key"] for row in rows}), 850)
        self.assertEqual(
            Counter(row["classification"] for row in rows),
            Counter(report["summary"]["classification_counts"]),
        )
        self.assertTrue(all(row["structural_import"]["same_allocation"] for row in rows))
        self.assertTrue(
            all(not row["structural_import"]["metadata_change_required"] for row in rows)
        )
        self.assertTrue(all(row["ownership"]["runtime_selector_owner"] == "unproved" for row in rows))
        self.assertTrue(all(row["ownership"]["runtime_visibility"] == "not-tested" for row in rows))

        spans: list[tuple[int, int]] = []
        for row in rows:
            wrapper_bytes = row["chunk"]["wrapper_span_bytes"]
            for space in ("archive_virtual", "pack", "xiso"):
                span = row["absolute_span"][space]
                self.assertEqual(span["end"] - span["start"], wrapper_bytes)
            spans.append(
                (row["absolute_span"]["xiso"]["start"], row["absolute_span"]["xiso"]["end"])
            )
            self.assertEqual(row["format"]["codec_word"], "0x00000011")
            self.assertEqual(
                row["format"]["total_block_align"], 36 * row["format"]["channels"]
            )
            self.assertEqual(
                row["format"]["frame_count"], 64 * row["format"]["block_count"]
            )
            self.assertEqual(
                row["format"]["payload_allocation_bytes"],
                row["format"]["total_block_align"] * row["format"]["block_count"],
            )
            for field in (
                "resource_span_sha256",
                "wrapper_header_sha256",
                "system_sha256",
                "tail_sha256",
                "payload_sha256",
            ):
                self.assertRegex(row["hashes"][field], SHA256_RE)
            self.assertEqual(row["ownership"]["physical_resource_evidence_id"], "resource-inventory-v2")
            self.assertEqual(
                row["ownership"]["resource_type_registration_evidence_id"],
                "audo-static-registration",
            )
        spans.sort()
        self.assertTrue(all(left[1] <= right[0] for left, right in zip(spans, spans[1:])))

        by_key = {row["key"]: row for row in rows}
        fixed = by_key["outer_0003_chunk_0101"]
        self.assertEqual(fixed["classification"], audit.CLASS_CANDIDATE)
        self.assertEqual(fixed["ownership"]["fixed_slot_authorization"], "public-offline-writer-proved")
        next_trace = by_key["outer_0009_chunk_0033"]
        self.assertEqual(next_trace["name"], "menu-appear_01")
        self.assertEqual(next_trace["classification"], audit.CLASS_STRUCTURAL)
        self.assertIsNone(next_trace["groups"]["duplicate_name"])
        self.assertIsNone(next_trace["groups"]["equal_decoded_content"])

        review = report["candidate_review"]
        self.assertEqual(review["additional_candidate_count"], 0)
        self.assertEqual(review["new_candidates"], [])
        self.assertFalse(review["existing_fixed_slot_runtime_owner_proved"])
        self.assertEqual(review["next_trace"]["target"], "outer_0009_chunk_0033")
        ownership = report["ownership_evidence"]
        self.assertEqual(ownership["resource-inventory-v2"]["audited_audo_key_count"], 850)
        self.assertEqual(ownership["audo-static-registration"]["function"], "FUN_00045740")
        self.assertEqual(ownership["audo-static-registration"]["callback_label"], "LAB_00045680")
        self.assertFalse(
            ownership["audo-static-registration"]["selector_or_play_request_owner_proved"]
        )

    def test_committed_tsv_has_one_exact_row_per_report_record(self) -> None:
        report = json.loads(REPORT.read_bytes())
        lines = MATRIX.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0].split("\t"), list(audit.MATRIX_FIELDS))
        self.assertEqual(len(lines), 851)
        cells = [line.split("\t") for line in lines[1:]]
        self.assertTrue(all(len(row) == len(audit.MATRIX_FIELDS) for row in cells))
        key_column = audit.MATRIX_FIELDS.index("key")
        self.assertEqual(
            [row[key_column] for row in cells],
            [row["key"] for row in report["records"]],
        )
        self.assertEqual(MATRIX.read_text(encoding="utf-8"), audit.render_matrix(report))

    def test_output_creation_is_exclusive_and_refuses_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "audit.json"
            matrix = root / "audit.tsv"
            audit.write_outputs(output, matrix, {"schema": "test/v1"}, "field\n")
            self.assertEqual(json.loads(output.read_bytes()), {"schema": "test/v1"})
            self.assertEqual(matrix.read_text(encoding="utf-8"), "field\n")
            with self.assertRaises(audit.CapacityAuditError):
                audit.write_outputs(output, root / "other.tsv", {}, "x\n")
            self.assertFalse(os.path.lexists(root / "other.tsv"))

            real_parent = root / "real"
            real_parent.mkdir()
            linked_parent = root / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaises(audit.CapacityAuditError):
                audit.write_outputs(
                    linked_parent / "linked.json", linked_parent / "linked.tsv", {}, "x\n"
                )
            self.assertEqual(list(real_parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
