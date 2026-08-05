"""The facemask colour is per uniform record, and the evidence has to say so.

The editor shipped a writer that changes one eight-byte pair and documentation
that called it a global setting. A modder said it should be per uniform set. He
was right: the packs hold hundreds of these records and they disagree with each
other, which a single global setting cannot do.

These tests pin the record layout on synthetic data so the reader cannot drift,
and assert the finding itself against the user's own packs when present.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "tools"))

import nfl_uniform_color_records as records  # noqa: E402

EXTRACTED = _REPO_ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


def _record(facemask: int, turtleneck: int, with_tset: bool = True) -> bytes:
    """One synthetic record in the layout the reader documents."""

    blob = bytearray(b"Unif")
    blob += struct.pack("<II", 0x11, 0x1D)
    blob += bytes(8)
    blob += "uniform".encode("utf-16-le") + b"\0\0"
    blob += bytes(records.COLOUR_OFFSET - len(blob))
    blob += struct.pack("<II", facemask, turtleneck)
    blob += struct.pack("<f", 1.0)
    if with_tset:
        blob += bytes(16) + b"TSET" + bytes(32)
    return bytes(blob)


class RecordLayoutTests(unittest.TestCase):
    def test_the_colour_is_read_from_the_documented_offset(self) -> None:
        blob = _record(0xFF000000, 0xFF385AAF)
        found = records.read_records(blob, "A")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["facemask_argb"], "FF000000")
        self.assertEqual(found[0]["turtleneck_argb"], "FF385AAF")
        self.assertEqual(found[0]["colour_offset"], records.COLOUR_OFFSET)

    def test_every_record_is_found_not_just_the_first(self) -> None:
        """The old writer knew one location; the point is that there are many."""

        blob = _record(0xFF111111, 0xFF222222) + _record(0xFF333333, 0xFF444444)
        found = records.read_records(blob, "A")
        self.assertEqual([row["facemask_argb"] for row in found],
                         ["FF111111", "FF333333"])

    def test_the_package_header_is_not_counted_as_a_record(self) -> None:
        """'UnifP' contains 'Unif' and would otherwise inflate every count."""

        blob = b"UnifP" + bytes(64) + _record(0xFF010203, 0xFF040506)
        found = records.read_records(blob, "A")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["facemask_argb"], "FF010203")

    def test_a_truncated_tail_is_skipped_rather_than_crashing(self) -> None:
        found = records.read_records(b"Unif" + bytes(4), "A")
        self.assertEqual(found, [])

    def test_disagreeing_records_are_reported_as_per_record(self) -> None:
        blob = _record(0xFF000000, 0xFF385AAF) + _record(0xFF9598A2, 0xFF202327)
        summary = records.summarise(records.read_records(blob, "A"))
        self.assertEqual(summary["distinct_colour_pairs"], 2)

    def test_identical_records_alone_would_not_prove_per_record(self) -> None:
        """The claim has to come from disagreement, not from record count."""

        blob = _record(0xFF000000, 0xFF385AAF) * 3
        summary = records.summarise(records.read_records(blob, "A"))
        self.assertEqual(summary["record_count"], 3)
        self.assertEqual(summary["distinct_colour_pairs"], 1)


class RealPackTests(unittest.TestCase):
    """The finding itself, against the user's own extracted packs."""

    @unittest.skipUnless((EXTRACTED / "vc_53450030" / "A").is_file(),
                         "extracted 2K5 packs not present")
    def test_the_packs_hold_many_disagreeing_colour_records(self) -> None:
        report = records.build_report(EXTRACTED, ("A", "B"))
        summary = report["summary"]
        self.assertGreater(summary["record_count"], 400)
        self.assertGreater(summary["distinct_colour_pairs"], 1)
        self.assertTrue(summary["colour_is_per_record_not_global"])

    @unittest.skipUnless((EXTRACTED / "vc_53450030" / "A").is_file(),
                         "extracted 2K5 packs not present")
    def test_the_span_the_old_writer_pinned_is_one_of_them(self) -> None:
        """0x055CA850 in pack A was described as global. It is record N of many."""

        report = records.build_report(EXTRACTED, ("A",))
        offsets = {row["colour_offset"] for row in report["records"]}
        self.assertIn(0x055CA850, offsets)
        self.assertGreater(len(offsets), 1)

    @unittest.skipUnless((EXTRACTED / "vc_53450030" / "A").is_file(),
                         "extracted 2K5 packs not present")
    def test_the_report_states_it_writes_nothing(self) -> None:
        report = records.build_report(EXTRACTED, ("A",))
        self.assertTrue(report["claims"]["read_only"])
        self.assertTrue(report["claims"]["writer_available"])
        self.assertTrue(report["claims"]["records_joined_to_uniform_selectors"])
        self.assertFalse(report["claims"]["runtime_visibility_proved"])
        json.dumps(report)  # the report has to survive serialisation


if __name__ == "__main__":
    unittest.main()
