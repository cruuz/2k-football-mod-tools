"""The roster scan must read the main ROST after the 16-reserves / extra-teams arena growth.

A beta-63 tester (jrolling2003, #2k5-bugs 2026-09-09) ticked the Gameplay page's experimental
set -- 16 reserves and Two extra created teams among them -- together with the merged position
pools, and Build died at the very end with

    ValueError: outer 5: ROST preamble. This image is: repacked disc (retail files, different
    layout ...). Build & Share works (it finds every file through the disc directory) ...

The identity sentence was a red herring: the failure has nothing to do with where the files sit.
``mod_build._build`` runs the Outside Linebackers scan (``tools.nfl2k5_roster_reclassify
.olb_filter_policy``) deliberately AFTER the last roster mutation, and the roster arena growth
(``mod_editor/core/nfl2k5_roster_arena.py``, ``DISC_VERSION = 18``) stamps the main roster's
preamble with version 18 and pads its arena to 0x92000 bytes.  The scan's parser accepted only the
retail version 17, so every build that combined the pools with the arena growth refused itself
after five minutes of copying, on a retail dump exactly as on a repack.

Everything in the first two classes is synthetic: a minimal ROST resource the reclassify parser
accepts, in its retail (17) and grown (18) shapes, and a small XDVDFS image whose only pack sits at
two different sectors.  The retail-gated class rebuilds the retail dump with the vendored
extract-xiso ``-r`` (through a symlink: rewrite mode renames its INPUT path to ``.old``), grows the
roster on that repack with the shipped arena writer and runs the same scan on the result.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl2k5_roster_reclassify as reclassify  # noqa: E402
import nfl_roster as nr  # noqa: E402
from nfl2k5_playbook_position_recode import OuterImage, RESOURCE_HEADER_SIZE  # noqa: E402
from nfl_outer import ALIGNMENT, ENTRY_SIZE, HEADER_SIZE, align_up  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402

RETAIL_VERSION = 17
GROWN_VERSION = 18
GROWN_ARENA_SIZE = 0x92000          # nfl2k5_roster_arena.ARENA_SIZE: the arena after the growth
ROOT_AT = 0x40
PREAMBLE_LABEL_AT = 0x20

RETAIL_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO",
                                  "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
EXTRACT_XISO = ROOT / "tools" / "vendor" / "extract-xiso" / "build" / "extract-xiso"
SCRATCH_ENV = "NFL2K5_REPACK_SCRATCH"
SCRATCH_NEEDED = 20 * 1024 ** 3      # the rebuild, the grown copy and its staging copy


def _rel(field: int, target: int) -> int:
    """Visual Concepts' field-local biased relative pointer: target = field + value - 1."""

    return target - field + 1


def synthetic_rost(version: int, *, label: str = "roster",
                   players: list[tuple[int, int, str, str]],
                   teams: list[tuple[str, str, int, int, list[int]]],
                   arena_size: int | None = None) -> bytes:
    """One uncompressed ROST outer entry (wrapper + body) the reclassify parser accepts.

    ``players`` rows are ``(position, order word, first, last)``; ``teams`` rows are
    ``(name, abbreviation, kind, scheme word, player indices)``.  The body carries the preamble,
    the 0x70-byte root, the primary player table, the team table, one label pair per team and the
    strings; every other table is empty.  ``arena_size`` pads the arena (body after the root) to
    the length the grown layout has.
    """

    n_players, n_teams = len(players), len(teams)
    players_at = ROOT_AT + nr.NFL_ROOT_SIZE
    teams_at = players_at + n_players * nr.NFL_PLAYER_STRIDE
    labels_at = teams_at + n_teams * nr.NFL_TEAM_STRIDE
    strings_at = labels_at + n_teams * 8
    body = bytearray(strings_at)
    strings = bytearray()

    def string(text: str) -> int:
        at = strings_at + len(strings)
        strings.extend(text.encode("utf-16le") + b"\0\0")
        return at

    body[0x0C:0x10] = b"ROST"
    struct.pack_into("<I", body, 0x10, version)
    struct.pack_into("<i", body, 0x14, _rel(0x14, ROOT_AT))
    encoded = label.encode("utf-16le") + b"\0\0"
    body[PREAMBLE_LABEL_AT:PREAMBLE_LABEL_AT + len(encoded)] = encoded
    # root: (count offset, pointer offset) per table, in nfl_roster.TABLE_SPECS order
    for spec in nr.TABLE_SPECS:
        count, at = {"primary_players": (n_players, players_at), "teams": (n_teams, teams_at),
                     "team_labels": (n_teams, labels_at)}.get(spec.name, (0, None))
        struct.pack_into("<I", body, ROOT_AT + spec.count_offset, count)
        if at is not None:
            struct.pack_into("<i", body, ROOT_AT + spec.pointer_offset, _rel(ROOT_AT + spec.pointer_offset, at))
    for index, (position, word, first, last) in enumerate(players):
        at = players_at + index * nr.NFL_PLAYER_STRIDE
        struct.pack_into("<i", body, at + 0x10, _rel(at + 0x10, string(first)))
        struct.pack_into("<i", body, at + 0x14, _rel(at + 0x14, string(last)))
        struct.pack_into("<H", body, at + reclassify.PLAYER_ORDER_WORD, word)
        body[at + reclassify.PLAYER_POSITION] = position
    for index, (name, abbreviation, kind, scheme, roster) in enumerate(teams):
        at = teams_at + index * nr.NFL_TEAM_STRIDE
        for slot, player in enumerate(roster):
            struct.pack_into("<i", body, at + slot * 4, _rel(at + slot * 4, players_at + player * nr.NFL_PLAYER_STRIDE))
        struct.pack_into("<i", body, at + 0x104, _rel(at + 0x104, string(name)))
        struct.pack_into("<i", body, at + 0x108, _rel(at + 0x108, string(abbreviation)))
        label_at = labels_at + index * 8
        struct.pack_into("<i", body, at + 0x110, _rel(at + 0x110, label_at))
        body[at + 0x11C] = len(roster)
        struct.pack_into("<I", body, at + 0x128, kind)
        struct.pack_into("<i", body, at + 0x138, _rel(at + 0x138, string(name.split()[0])))
        struct.pack_into("<I", body, at + reclassify.TEAM_SCHEME_WORD, scheme)
        struct.pack_into("<i", body, label_at + 4, _rel(label_at + 4, string(abbreviation)))
    body.extend(strings)
    body.extend(bytes(-len(body) % 16))
    if arena_size is not None:
        assert len(body) - ROOT_AT <= arena_size, "fixture larger than the requested arena"
        body.extend(bytes(arena_size - (len(body) - ROOT_AT)))
    stored = len(body)
    wrapper = struct.pack("<4s7I", b"ROST", stored, stored, 0, 0, 0, 0, 0)
    return wrapper + bytes(body)


PLAYERS = [
    (reclassify.ENUM_OLB, 0 << reclassify.RANK_SHIFT, "Mike", "Vrabel"),
    (reclassify.ENUM_ILB, 0 << reclassify.RANK_SHIFT, "Tedy", "Bruschi"),
    (reclassify.ENUM_DE, 0 << reclassify.RANK_SHIFT, "Richard", "Seymour"),
    (reclassify.ENUM_DT, 0 << reclassify.RANK_SHIFT, "Ted", "Washington"),
    (0, 0, "Tom", "Brady"),
]
TEAMS = [("New England Patriots", "NE", reclassify.TEAM_KIND_NFL, 1, [0, 1, 2, 3, 4]),
         ("Created 1", "USER1", 2, 0, [])]


def retail_shape() -> bytes:
    return synthetic_rost(RETAIL_VERSION, players=PLAYERS, teams=TEAMS)


def grown_shape() -> bytes:
    return synthetic_rost(GROWN_VERSION, players=PLAYERS, teams=TEAMS, arena_size=GROWN_ARENA_SIZE)


def historic_shape(index: int) -> bytes:
    return synthetic_rost(RETAIL_VERSION, label="historic",
                          players=[(reclassify.ENUM_ILB, 0, "Player", f"H{index}")],
                          teams=[(f"Historic {index}", f"H{index}", reclassify.TEAM_KIND_NFL, 0, [0])])


class SyntheticResourceTests(unittest.TestCase):
    """The parser, on the grown shape the arena writer produces."""

    def test_the_retail_shape_parses(self) -> None:
        raw = retail_shape()
        resource = reclassify.parse_resource(5, 0x392800, raw)
        self.assertEqual(resource.label, "roster")
        self.assertEqual(len(resource.players), len(PLAYERS))
        self.assertEqual([team.abbreviation for team in resource.teams], ["NE", "USER1"])
        self.assertEqual(sorted(p.position for p in resource.players.values()),
                         sorted(row[0] for row in PLAYERS))

    def test_the_grown_shape_parses_like_the_retail_one(self) -> None:
        """Version 18 with the 0x92000 arena is the same roster with more room, not a foreign file."""

        raw = grown_shape()
        self.assertEqual(struct.unpack_from("<I", raw, RESOURCE_HEADER_SIZE + 0x10)[0], GROWN_VERSION)
        self.assertEqual(len(raw) - RESOURCE_HEADER_SIZE - ROOT_AT, GROWN_ARENA_SIZE)
        grown = reclassify.parse_resource(5, 0x392800, raw)
        retail = reclassify.parse_resource(5, 0x392800, retail_shape())
        self.assertEqual({off: (p.position, p.word, p.name, p.teams) for off, p in grown.players.items()},
                         {off: (p.position, p.word, p.name, p.teams) for off, p in retail.players.items()})
        self.assertEqual([(t.abbreviation, t.kind, t.scheme_word, t.roster) for t in grown.teams],
                         [(t.abbreviation, t.kind, t.scheme_word, t.roster) for t in retail.teams])
        self.assertEqual(grown.tables["primary_players"]["count"], len(PLAYERS))

    def test_the_scan_counts_the_same_outside_linebackers_on_both_shapes(self) -> None:
        retail = reclassify.olb_filter_evidence([reclassify.parse_resource(5, 0, retail_shape())])
        grown = reclassify.olb_filter_evidence([reclassify.parse_resource(5, 0, grown_shape())])
        self.assertEqual(retail["olb_players"], 1)
        self.assertEqual(grown["olb_players"], retail["olb_players"])
        self.assertEqual(grown["resources"][0]["positions_sha256"], retail["resources"][0]["positions_sha256"])
        self.assertFalse(grown["complete"])         # one resource is never the whole disc

    def test_version_18_still_needs_the_grown_arena(self) -> None:
        """Only the arena writer's exact layout is accepted; a retail-length version 18 is foreign."""

        raw = synthetic_rost(GROWN_VERSION, players=PLAYERS, teams=TEAMS)
        with self.assertRaisesRegex(reclassify.ReclassifyError, "outer 5: ROST preamble"):
            reclassify.parse_resource(5, 0, raw)

    def test_other_versions_are_still_refused(self) -> None:
        for version in (0, 16, 19):
            raw = synthetic_rost(version, players=PLAYERS, teams=TEAMS, arena_size=GROWN_ARENA_SIZE)
            with self.subTest(version=version), self.assertRaisesRegex(reclassify.ReclassifyError, "ROST preamble"):
                reclassify.parse_resource(5, 0, raw)


class SyntheticImageTests(unittest.TestCase):
    """The scan the build runs last, on a disc whose main roster has grown, at two layouts."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="reclassify-grown-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _entries(self, main: bytes) -> list[tuple[int, bytes]]:
        entries: list[tuple[int, bytes]] = []
        last = max(reclassify.HISTORIC_ROST_ENTRIES)
        for index in range(last + 2):        # one trailing dummy takes the fixture's end padding
            if index == reclassify.MAIN_ROST_ENTRY:
                payload = main
            elif index in reclassify.HISTORIC_ROST_ENTRIES:
                payload = historic_shape(index)
            else:
                payload = b"DUMY" + bytes(12)
            entries.append((0x1000 + index, payload))
        return entries

    def _image(self, name: str, main: bytes, *, pack_sector: int) -> Path:
        entries = self._entries(main)
        needed = align_up(HEADER_SIZE + ENTRY_SIZE * len(entries)) + sum(align_up(len(p)) for _, p in entries)
        folder = self.tmp / name
        folder.mkdir()
        fixture = SyntheticXiso(folder, entries, pack_sizes=(align_up(needed) + ALIGNMENT,), pack_sectors=(pack_sector,))
        return fixture.path

    def test_the_scan_reads_a_grown_roster_wherever_the_pack_sits(self) -> None:
        """Retail-like and moved sectors give one answer: the reader goes through the directory."""

        results = []
        for name, sector in (("retail-layout", 64), ("moved-layout", 64 + 0x900)):
            image = self._image(name, grown_shape(), pack_sector=sector)
            with self.subTest(layout=name):
                scan = reclassify.olb_filter_policy(image)
                self.assertTrue(scan["complete"], scan)
                self.assertEqual(scan["olb_players"], 1)
                self.assertIs(scan["roster_has_olb"], True)
                self.assertEqual(scan["filter_rows"], "retained")
                self.assertEqual(scan["missing_resources"], [])
                results.append({k: v for k, v in scan.items()})
        self.assertEqual(results[0], results[1])

    def test_the_scan_reads_a_retail_roster_at_moved_sectors_too(self) -> None:
        image = self._image("moved-retail", retail_shape(), pack_sector=64 + 0x900)
        scan = reclassify.olb_filter_policy(image)
        self.assertTrue(scan["complete"])
        self.assertEqual(scan["olb_players"], 1)

    def test_a_grown_roster_without_outside_linebackers_certifies_absence(self) -> None:
        """The build removes the Outside Linebackers rows only on a complete scan that finds none."""

        moved = [(reclassify.ENUM_ILB if p == reclassify.ENUM_OLB else p, w, f, l) for p, w, f, l in PLAYERS]
        main = synthetic_rost(GROWN_VERSION, players=moved, teams=TEAMS, arena_size=GROWN_ARENA_SIZE)
        image = self._image("no-olb", main, pack_sector=64 + 0x900)
        scan = reclassify.olb_filter_policy(image)
        self.assertTrue(scan["complete"])
        self.assertIs(scan["roster_has_olb"], False)
        self.assertEqual(scan["filter_rows"], "removed")


def _scratch() -> Path | None:
    value = os.environ.get(SCRATCH_ENV)
    if not value:
        return None
    path = Path(value)
    if not path.is_dir() or shutil.disk_usage(path).free < SCRATCH_NEEDED:
        return None
    return path


@unittest.skipUnless(RETAIL_XISO.is_file(), f"retail xiso not present at {RETAIL_XISO}")
class RetailGrownRosterTests(unittest.TestCase):
    """The real main roster, grown in memory by the shipped arena migration."""

    def test_the_grown_retail_roster_parses_for_every_arena_option(self) -> None:
        from mod_editor.core import nfl2k5_roster_arena as arena

        with OuterImage(RETAIL_XISO) as archive:
            entry = archive.entries[reclassify.MAIN_ROST_ENTRY]
            raw = archive.read_entry(reclassify.MAIN_ROST_ENTRY)
        retail = reclassify.parse_resource(reclassify.MAIN_ROST_ENTRY, entry.virtual_offset, raw)
        self.assertEqual(retail.label, "roster")
        expected = reclassify.olb_filter_evidence([retail])["resources"][0]["positions_sha256"]
        for options in (dict(reserves_16=True, created_teams_extra=0),
                        dict(reserves_16=False, created_teams_extra=2),
                        dict(reserves_16=True, created_teams_extra=2)):
            with self.subTest(**options):
                grown, receipt = arena.migrate(raw, **options)
                self.assertFalse(receipt["already_applied"])
                self.assertEqual(struct.unpack_from("<I", grown, RESOURCE_HEADER_SIZE + 0x10)[0], GROWN_VERSION)
                resource = reclassify.parse_resource(reclassify.MAIN_ROST_ENTRY, entry.virtual_offset, grown)
                self.assertEqual(len(resource.teams), len(retail.teams) + options["created_teams_extra"])
                scan = reclassify.olb_filter_evidence([resource])
                self.assertEqual(scan["resources"][0]["positions_sha256"], expected)
                self.assertGreater(scan["olb_players"], 0)


@unittest.skipUnless(RETAIL_XISO.is_file(), f"retail xiso not present at {RETAIL_XISO}")
@unittest.skipUnless(EXTRACT_XISO.is_file(), f"vendored extract-xiso not built at {EXTRACT_XISO}")
@unittest.skipUnless(_scratch() is not None,
                     f"set {SCRATCH_ENV} to a folder with {SCRATCH_NEEDED // 1024 ** 3} GiB free to run the "
                     "extract-xiso -r rebuild (never the retail folder: rewrite mode renames its input)")
class RetailRepackTests(unittest.TestCase):
    """extract-xiso -r on the retail dump, then the shipped arena writer, then the scan."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="repack-", dir=_scratch()))
        link = cls.folder / "retail.iso"
        try:
            link.symlink_to(RETAIL_XISO)      # rewrite mode renames THIS path to .old, not the dump
        except OSError as exc:                # Windows without the symlink privilege
            shutil.rmtree(cls.folder, ignore_errors=True)
            raise unittest.SkipTest(f"cannot symlink the retail dump into the scratch folder: {exc}")
        subprocess.run([str(EXTRACT_XISO), "-r", "-d", str(cls.folder), str(link)],
                       check=True, capture_output=True, text=True)
        cls.rebuild = cls.folder / "retail.iso"
        assert cls.rebuild.is_file() and not cls.rebuild.is_symlink(), "extract-xiso wrote no rebuild"
        assert RETAIL_XISO.is_file(), "the retail dump must keep its name"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_the_rebuild_is_a_repack_the_scan_reads_through_the_directory(self) -> None:
        from mod_editor.core import nfl2k5_disc_identity as identity

        found = identity.identify(self.rebuild)
        self.assertEqual(found.kind, "repack", found.line())
        self.assertTrue(found.can_build)
        with OuterImage(RETAIL_XISO) as retail, OuterImage(self.rebuild) as rebuilt:
            for index in (reclassify.MAIN_ROST_ENTRY, *reclassify.HISTORIC_ROST_ENTRIES):
                self.assertEqual(hashlib.sha256(rebuilt.read_entry(index)).hexdigest(),
                                 hashlib.sha256(retail.read_entry(index)).hexdigest(), f"outer {index}")
        scan = reclassify.olb_filter_policy(self.rebuild)
        self.assertTrue(scan["complete"])
        self.assertIs(scan["roster_has_olb"], True)
        self.assertEqual(scan, reclassify.olb_filter_policy(RETAIL_XISO))

    def test_the_scan_reads_the_grown_roster_the_arena_writer_leaves_on_the_repack(self) -> None:
        """What the build does last, on the copy the 16-reserves / extra-teams writer produced."""

        from mod_editor.core import nfl2k5_roster_arena_image as arena_image

        grown = self.folder / "grown.iso"
        receipt = arena_image.build_image(self.rebuild, grown, reserves_16=True, created_teams_extra=2)
        self.addCleanup(lambda: grown.unlink(missing_ok=True))
        self.assertEqual(receipt["verification"]["status"], "verified")
        self.assertEqual(arena_image.image_status(grown), "applied")
        with OuterImage(grown) as archive:
            raw = archive.read_entry(reclassify.MAIN_ROST_ENTRY)
        self.assertEqual(struct.unpack_from("<I", raw, RESOURCE_HEADER_SIZE + 0x10)[0], GROWN_VERSION)
        scan = reclassify.olb_filter_policy(grown)
        self.assertTrue(scan["complete"], scan)
        self.assertIs(scan["roster_has_olb"], True)
        before = reclassify.olb_filter_policy(self.rebuild)
        self.assertEqual(scan["olb_players"], before["olb_players"])
        self.assertEqual([r["positions_sha256"] for r in scan["resources"]],
                         [r["positions_sha256"] for r in before["resources"]])


if __name__ == "__main__":
    unittest.main()
