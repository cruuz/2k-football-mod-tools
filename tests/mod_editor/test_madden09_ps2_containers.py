"""The Madden 09 (PS2) container reader, on synthetic images only.

Every byte here is built by :mod:`containers`' own synthetic-disc builders out
of the formats' rules; nothing reads a disc, so this suite runs for a
contributor who owns none of these games.

Two shapes are pinned that a real image has and a naive fixture does not:

* a container whose ISO9660 directory record understates it, which the
  community's *Deluxe* image does to six of its own;
* a preload-cache row at a container boundary that names a member the
  container it names does not have.
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


class PreloadBoundaryTests(_Disc):
    """A ``DTLS`` row that names a member its container does not have.

    Measured twice on the retail Madden 09 disc (``FE.QKL`` naming
    ``UIS_FONT.DAT`` member 10 of a ten-member container) and twelve times on
    Madden 06 (``GAME.QKL`` naming ``SOUNDDAT.DAT`` members 470-481 of a
    447-member container).  In every case the row's own file index is read
    correctly -- its neighbours with that index resolve and match -- and the
    bytes at its offset are another copy the same cache already carries, so
    the off-by-one is in EA's member number and the bytes are the tie-breaker.
    """

    # A real member 0 as well as the boundary rows: the default fixture leaves
    # member 0 empty, and "a copy of member 0" is exactly the case a truthiness
    # test on the member number gets wrong.
    kwargs = {"boundary_copies": True,
              "tdb_member": containers.synthetic_text_member(
                  containers.SYNTHETIC_TEXT_LINES)}

    def _copies(self):
        rows = containers.preload_copies(self.image)
        return [copy for row in rows.values()
                for copy in list(row.header)
                + [item for items in row.members.values() for item in items]]

    def test_without_the_boundary_rows_nothing_is_re_attributed(self) -> None:
        plain = self.work / "plain.iso"
        plain.write_bytes(containers.build_synthetic_disc())
        rows = containers.preload_copies(containers.open_disc(plain))
        for row in rows.values():
            for copy in list(row.header) + [item for items in row.members.values()
                                            for item in items]:
                self.assertFalse(copy.reattributed)
                self.assertEqual(copy.as_dict().get("declared_container"), None)

    def test_every_copy_resolves_and_none_is_refused(self) -> None:
        for copy in self._copies():
            entry = self.files[copy.container]
            parsed = ea_terf.parse_terf(
                containers.read_file(self.image, entry, limit=None),
                allow_size_mismatch=True)
            self.assertGreater(copy.length_in(parsed), 0)

    def test_a_row_aliased_onto_another_member_of_its_own_container(self) -> None:
        """Madden 06's shape: an out-of-range number on a real member's offset."""
        moved = [copy for copy in self._copies()
                 if copy.reattributed and copy.cache == "GAME.QKL"]
        self.assertEqual(len(moved), 1)
        copy = moved[0]
        self.assertEqual(copy.container, containers.TEAM_DATABASE_CONTAINER)
        self.assertEqual(copy.declared_container, containers.TEAM_DATABASE_CONTAINER)
        self.assertFalse(copy.is_header)
        self.assertEqual(copy.member, 1)
        self.assertGreater(copy.declared_member, copy.member)
        twin = next(other for other in self._copies()
                    if other.offset == copy.offset and not other.reattributed)
        self.assertEqual((twin.container, twin.member), (copy.container, copy.member))

    def test_a_row_aliased_onto_the_next_containers_header(self) -> None:
        """Madden 09's shape: the bytes are the next file's container header."""
        moved = [copy for copy in self._copies()
                 if copy.reattributed and copy.cache == "FE.QKL"]
        self.assertEqual(len(moved), 1)
        copy = moved[0]
        self.assertEqual(copy.container, containers.UNIFORM_CONTAINER)
        self.assertTrue(copy.is_header)
        self.assertEqual(copy.declared_container, containers.TEAM_DATABASE_CONTAINER)
        self.assertEqual(copy.declared_kind, containers.PRELOAD_KIND_MEMBER)
        self.assertIsNone(copy.member)

    def test_the_bytes_the_re_attributed_copy_names_are_the_bytes_there(self) -> None:
        blob = containers.read_file(self.image, self.files["FE.QKL"], limit=None)
        copy = next(item for item in self._copies()
                    if item.reattributed and item.cache == "FE.QKL")
        parsed = ea_terf.parse_terf(
            containers.read_file(self.image, self.files[copy.container], limit=None),
            allow_size_mismatch=True)
        length = copy.length_in(parsed)
        source = containers.read_file(
            self.image, self.files[copy.container], limit=None)[:length]
        self.assertEqual(blob[copy.offset:copy.offset + length], source)

    def test_member_zero_is_not_mistaken_for_an_unresolved_row(self) -> None:
        """`copy.member or -1` would call member 0 unresolved; caches are full of it."""
        zero = [copy for copy in self._copies()
                if not copy.is_header and copy.member == 0]
        self.assertTrue(zero, "the fixture must carry a copy of member 0")
        for copy in zero:
            self.assertFalse(copy.reattributed)
            self.assertIsNone(copy.declared_member)

    def test_a_re_attributed_copy_keeps_what_its_row_said(self) -> None:
        copy = next(item for item in self._copies() if item.reattributed)
        row = copy.as_dict()
        self.assertEqual(row["declared_container"], containers.TEAM_DATABASE_CONTAINER)
        self.assertEqual(row["declared_kind"], "member")
        self.assertIsNotNone(row["declared_member"])


class MakeRecordedShortTests(unittest.TestCase):
    """The fixture builder, against the shapes the *Deluxe* image actually has."""

    def test_a_container_of_nothing_but_empty_members_keeps_its_data_chunk(self) -> None:
        """`MOVIEDAT.DAT` on that image is recorded as 200 bytes against 832 [M]."""
        short = containers.make_recorded_short(ea_terf.build_terf([b""] * 10))
        parsed = ea_terf.parse_terf(short, allow_size_mismatch=True)
        self.assertEqual(len(short), 200)
        self.assertEqual(parsed.declared_length, 832)
        self.assertEqual(parsed.member_count, 10)
        self.assertTrue(parsed.short_tail_is_empty)
        self.assertEqual(parsed.layout_violations(allow_short_tail=True), [])

    def test_a_container_with_no_empty_tail_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            containers.make_recorded_short(ea_terf.build_terf([b"alpha", b"bravo"]))
        self.assertIn("nothing about it is recorded short", str(caught.exception))

    def test_the_members_with_bytes_all_survive_the_cut(self) -> None:
        members = [b"alpha member", b"bravo member", b"charlie member"]
        short = containers.make_recorded_short(
            ea_terf.build_terf(members + [b""] * containers.SYNTHETIC_EMPTY_TAIL))
        parsed = ea_terf.parse_terf(short, allow_size_mismatch=True)
        for index, payload in enumerate(members):
            self.assertEqual(parsed.member(index), payload)


class PreloadUnresolvableTests(unittest.TestCase):
    """A row whose bytes match nothing is still refused, and says where."""

    def test_the_refusal_names_the_offset_and_the_member_count(self) -> None:
        members = [b"alpha member", b"bravo member"]
        container = ea_terf.build_terf(members)
        cache = containers.build_synthetic_preload_cache([
            (containers.TEAM_DATABASE_CONTAINER, containers.PRELOAD_KIND_MEMBER,
             9, b"bytes that copy nothing on this disc"),
        ])
        copies = containers.parse_preload_cache(cache, "GAME.QKL")
        self.assertEqual(len(copies), 1)
        with self.assertRaises(Refusal) as caught:
            copies[0].length_in(ea_terf.parse_terf(container))
        message = str(caught.exception)
        self.assertIn("member 9", message)
        self.assertIn(str(copies[0].offset), message)
        self.assertIn("has 2 member(s) (0..1)", message)
        self.assertIn("matches the bytes there", message)


if __name__ == "__main__":
    unittest.main()
