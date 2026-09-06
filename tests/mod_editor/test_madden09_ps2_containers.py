"""The Madden 09 (PS2) container reader, on synthetic images only.

Every byte here is built by :mod:`containers`' own synthetic-disc builders out
of the formats' rules; nothing reads a disc, so this suite runs for a
contributor who owns none of these games.

One shape is pinned that a real image has and a naive fixture does not: a
container whose ISO9660 directory record understates it, which the
community's *Deluxe* image does to six of its own.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games._formats import ea_terf  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import containers  # noqa: E402


class _Disc(unittest.TestCase):
    """A synthetic image on disk, cleaned up after."""

    kwargs: dict = {}

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-containers-")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.source = self.work / "synthetic.iso"
        self.source.write_bytes(containers.build_synthetic_disc(**self.kwargs))
        self.image = containers.open_disc(self.source)
        self.files = {entry.name: entry
                      for entry in containers.data_files(self.image)}


class RecordedShortReadTests(_Disc):
    kwargs = {"recorded_short": True}

    def setUp(self) -> None:
        super().setUp()
        self.entry = self.files[containers.TEAM_DATABASE_CONTAINER]

    def test_the_reader_still_recovers_to_the_declared_length(self) -> None:
        """A reader wants every member; only a writer wants the record."""
        recovered = containers.read_file(self.image, self.entry)
        self.assertGreater(len(recovered), self.entry.recorded_length)
        self.assertEqual(len(recovered),
                         ea_terf.declared_length(recovered[:containers.PROBE_BYTES]))

    def test_open_for_rewrite_stops_at_the_record(self) -> None:
        writable = containers.open_for_rewrite(self.image, self.entry)
        self.assertEqual(len(writable.data), self.entry.recorded_length)
        self.assertTrue(writable.recorded_short)
        self.assertGreater(writable.declared_length, len(writable.data))
        self.assertTrue(writable.parsed.short_tail_is_empty)

    def test_only_empty_members_lie_past_the_record(self) -> None:
        writable = containers.open_for_rewrite(self.image, self.entry)
        beyond = [member for member in writable.parsed.members
                  if writable.member_end(member.index) > len(writable.data)]
        self.assertTrue(beyond)
        for member in beyond:
            self.assertTrue(member.empty)

    def test_a_member_inside_the_record_is_allowed(self) -> None:
        writable = containers.open_for_rewrite(self.image, self.entry)
        self.assertIsNone(writable.require_member_inside(0))

    def test_a_member_past_the_record_is_refused_with_both_sizes(self) -> None:
        writable = containers.open_for_rewrite(self.image, self.entry)
        beyond = next(member.index for member in writable.parsed.members
                      if writable.member_end(member.index) > len(writable.data))
        with self.assertRaises(Refusal) as caught:
            writable.require_member_inside(beyond)
        message = str(caught.exception)
        self.assertIn(f"{len(writable.data):,}", message)
        self.assertIn(f"{writable.declared_length:,}", message)
        self.assertIn("would have to grow the file", message)

    def test_a_member_that_is_not_there_at_all_says_so(self) -> None:
        writable = containers.open_for_rewrite(self.image, self.entry)
        with self.assertRaises(Refusal) as caught:
            writable.require_member_inside(writable.parsed.member_count)
        self.assertIn("has no member", str(caught.exception))


class OrdinaryContainerTests(_Disc):
    def test_a_container_that_is_not_short_says_so(self) -> None:
        entry = self.files[containers.TEAM_DATABASE_CONTAINER]
        writable = containers.open_for_rewrite(self.image, entry)
        self.assertFalse(writable.recorded_short)
        self.assertEqual(len(writable.data), entry.recorded_length)
        self.assertEqual(writable.declared_length, entry.recorded_length)
        self.assertEqual(writable.parsed.short_tail, 0)


if __name__ == "__main__":
    unittest.main()
