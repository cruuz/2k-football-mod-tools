"""Tests for positional, platform-aware APF roster export comparison."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "tools"))

import apf_roster_export_compare as subject  # noqa: E402


HEADER = [
    "First", "Last", "College", "DOB", "Number", "Photo", "PBP", "Age",
    "Team", "TeamJerseyBytes", "RunCoverage", "RunCoverage",
]


def jersey(seed: int, platform_variant: bool = False) -> str:
    data = bytearray((seed + index) % 256 for index in range(subject.JERSEY_BLOB_BYTES))
    if platform_variant:
        for block in range(subject.COLOUR_REGION_START, subject.COLOUR_REGION_END,
                           subject.COLOUR_BLOCK_SIZE):
            for offset in range(block, block + subject.COLOUR_BYTES_PER_BLOCK, 4):
                rgba = bytes(data[offset:offset + 4])
                data[offset:offset + 4] = rgba[3:4] + rgba[:3]
    return data.hex().upper()


def row(identity: list[str], team: str, jersey_bytes: str, run1: str, run2: str,
        unlabelled: str) -> list[str]:
    return identity + [team, jersey_bytes, run1, run2, unlabelled]


def write_export(path: Path, rows: list[list[str]]) -> None:
    lines = ["|".join(HEADER)] + ["|".join(values) for values in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ComparisonTests(unittest.TestCase):
    def make_pair(self, root: Path) -> tuple[dict, dict]:
        base_identity = ["A", "Player", "School", "1/1", "1", "10", "20", "30"]
        left_rows = [
            row(base_identity, "Stock", jersey(1), "50", "60", "tail"),
            row(base_identity, "Atoms", jersey(2), "51", "61", "tail"),
            row(base_identity, "Stock", jersey(3), "52", "62", "tail"),
            row(base_identity, "Stock", jersey(4), "53", "63", "tail"),
        ]
        identity_variant = ["B", "Replacement", "Other", "2/2", "2", "11", "21", "31"]
        right_rows = [
            row(identity_variant, "Stock", jersey(1, True), "50", "60", "tail"),
            row(base_identity, "Atoms", jersey(2, True), "99", "61", "changed"),
            row(base_identity, "Stock", jersey(3, True), "52", "62", "tail"),
            row(base_identity, "Stock", jersey(4, True), "53", "99", "tail"),
        ]
        left_path = root / "left.txt"
        right_path = root / "right.txt"
        write_export(left_path, left_rows)
        write_export(right_path, right_rows)
        return subject.parse_export(left_path), subject.parse_export(right_path)

    def test_schema_hazards_are_explicit_and_every_row_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            left, right = self.make_pair(Path(temporary))
            report = subject.compare_exports(
                left, right,
                left_platform="RPCS3",
                right_platform="Xenia",
                user_team_labels={"Atoms"},
            )
        schema = report["schema_audit"]
        self.assertEqual(schema["header_field_count"], 12)
        self.assertEqual(schema["data_field_count"], 13)
        self.assertEqual(schema["unlabelled_trailing_field_count"], 1)
        self.assertEqual(schema["duplicate_header_labels"], {"RunCoverage": 2})
        self.assertIn("RunCoverage#1", schema["positional_labels"])
        self.assertIn("RunCoverage#2", schema["positional_labels"])
        self.assertIn("Unlabelled12", schema["positional_labels"])
        self.assertEqual(report["classification_counts"], {
            "equivalent_after_platform_normalization": 1,
            "stock_identity_variant": 1,
            "unexplained": 1,
            "user_team_randomized_roster": 1,
        })
        self.assertEqual(report["platform_uniform_colour_order"]["equivalent_row_count"], 4)
        self.assertEqual(report["identity_variants"][0]["changes"]["First"], {
            "RPCS3": "A", "Xenia": "B",
        })
        self.assertEqual(report["user_team_variants"]["row_count"], 1)
        self.assertEqual(report["unexplained_rows"][0]["different_fields"],
                         ["RunCoverage#2"])

    def test_uniform_normalization_requires_the_exact_bounded_transform(self) -> None:
        left = jersey(7)
        right = bytearray.fromhex(jersey(7, True))
        self.assertTrue(subject.platform_jersey_bytes_equivalent(left, right.hex()))
        right[0] ^= 1
        self.assertFalse(subject.platform_jersey_bytes_equivalent(left, right.hex()))
        self.assertFalse(subject.platform_jersey_bytes_equivalent("00", "00"))

    def test_inconsistent_row_width_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.txt"
            path.write_text("A|B\n1|2\n3|4|5\n", encoding="utf-8")
            with self.assertRaisesRegex(subject.CompareError, "one exact width"):
                subject.parse_export(path)

    def test_report_writer_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(subject.CompareError, "refusing to overwrite"):
                subject._write_report(path, {"test": True})
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
