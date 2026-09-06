"""The PS2 playbook patcher and its independent verifier, with no game data.

Everything here is synthetic: a ``PLAY`` body built field by field so the
shipped codec accepts it, wrapped in a synthetic outer archive, wrapped in a
real ISO9660 image -- all three from the tool's own builders, which is where
they have to live so ``--selftest`` can prove the lane in a shipped tree.  No
disc, no retail bytes, no network.

What the cases pin, in order: a formation and a play can be added and the
independent verifier passes; a byte flipped anywhere outside the declared
playbook span makes verification fail; a book already at the 270-play capacity
is refused; and a compile that returns the wrong body length is refused
*before* the output image is created, so a fixed-allocation violation can never
reach the disk.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools", Path(__file__).resolve().parent):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import nfl2k5_ps2_playbook_patch as patcher  # noqa: E402
import nfl2k5_ps2_playbook_verify as verifier  # noqa: E402

from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_formation_play_writer as fpwriter  # noqa: E402


BOOK_ID = patcher.SELFTEST_BOOK_ID
OTHER_BOOK_ID = patcher.SELFTEST_OTHER_BOOK_ID

# The fixture builders live in the tool, not here: the lane's validator has to
# prove itself in a shipped tree, where ``tests/`` does not exist, so the
# synthetic book and the claims it supports are reachable as
# ``nfl2k5_ps2_playbook_patch.py --selftest``.  These tests exercise the same
# builders so the two can never drift apart.
synthetic_body = patcher.build_synthetic_body
synthetic_resource = patcher.build_synthetic_resource


def default_books(plays: int = 2):
    return [
        (BOOK_ID, synthetic_resource(synthetic_body(plays=plays))),
        (OTHER_BOOK_ID, synthetic_resource(synthetic_body(plays=plays))),
    ]


RECIPE = patcher.selftest_recipe()

CHAINS_PER_BOOK = codec.SLOT_COUNT
NODES_PER_CHAIN = len(patcher.SELFTEST_CHAIN_OPS)


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ps2playbook-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = self.tmp / "source.iso"
        self.output = self.tmp / "output.iso"

    def write_source(self, books=None) -> Path:
        self.source.write_bytes(
            patcher.build_synthetic_disc(books=books or default_books()))
        return self.source

    def write_recipe(self, recipe=None) -> Path:
        path = self.tmp / "recipe.json"
        path.write_text(json.dumps(recipe or RECIPE), encoding="utf-8")
        return path


class SyntheticFixtureTests(_Case):
    """The fixture has to be a real book, or nothing below proves anything."""

    def test_the_synthetic_body_parses_and_every_play_validates(self) -> None:
        book = insp._parse_body(synthetic_body(), asset_id="synthetic", outer_index=0)
        self.assertEqual(len(book.formations), 3)
        self.assertEqual(len(book.plays), 2)
        self.assertEqual(book.node_count, CHAINS_PER_BOOK * NODES_PER_CHAIN)
        self.assertEqual(len(book.chains), CHAINS_PER_BOOK)
        for play in book.plays:
            assignments = [
                (a.descriptor_word,
                 [bytes.fromhex(n.raw_hex)
                  for n in book.chain(a.chain_start_index).nodes])
                for a in play.assignments
            ]
            self.assertIsNone(codec.validate_play(play.flags_or_id, assignments))

    def test_targets_are_found_with_their_offsets(self) -> None:
        targets = patcher.find_targets(self.write_source())
        self.assertEqual([t.book_id for t in targets], [BOOK_ID, OTHER_BOOK_ID])
        for target in targets:
            self.assertEqual(target.pack_iso_path if hasattr(target, "pack_iso_path")
                             else target.pack.iso_path, "/VC_20919/0.")
            raw = patcher.read_resource(self.source, target)
            self.assertEqual(len(raw), patcher.PLAY_RESOURCE_SIZE)


class PatchAndVerifyTests(_Case):
    def test_adds_a_formation_and_a_play_and_verifies(self) -> None:
        source = self.write_source()
        report = patcher.patch(source, patcher.load_recipe(self.write_recipe()),
                               self.output, workdir=self.tmp)

        self.assertEqual(len(report["play_edits"]), 1)
        edit = report["play_edits"][0]
        self.assertEqual(edit["before"], {"formations": 3, "plays": 2,
                                          "categories": 2, "nodes": 22})
        self.assertEqual(edit["after"], {"formations": 4, "plays": 3,
                                         "categories": 2, "nodes": 22})
        self.assertEqual(edit["resource_size"], patcher.PLAY_RESOURCE_SIZE)
        self.assertEqual(source.stat().st_size, self.output.stat().st_size)

        result = verifier.verify(source, self.output, report)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["declared_edits"], 1)
        self.assertEqual(result["play_resources_found"], 2)
        self.assertEqual(result["books"][0]["counts"]["plays"], 3)
        self.assertEqual(result["books"][0]["plays_validated"], 3)
        self.assertTrue(result["changed_byte_total"] > 0)

    def test_the_untouched_book_keeps_every_byte(self) -> None:
        source = self.write_source()
        report = patcher.patch(source, patcher.load_recipe(self.write_recipe()),
                               self.output, workdir=self.tmp)
        edited = report["play_edits"][0]["absolute_offset"]
        for book_id, offset in verifier._play_resources(self.output):
            before = verifier._read_at(source, offset, patcher.PLAY_RESOURCE_SIZE)
            after = verifier._read_at(self.output, offset, patcher.PLAY_RESOURCE_SIZE)
            if offset == edited:
                self.assertNotEqual(before, after)
            else:
                self.assertEqual(before, after, "book %s changed" % book_id)


class RefusalTests(_Case):
    def test_a_byte_flipped_outside_the_declared_span_fails_verification(self) -> None:
        source = self.write_source()
        report = patcher.patch(source, patcher.load_recipe(self.write_recipe()),
                               self.output, workdir=self.tmp)
        self.assertEqual(verifier.verify(source, self.output, report)["verdict"], "PASS")

        # The other book's resource is a real, addressable, out-of-lane target.
        stray = None
        for _book_id, offset in verifier._play_resources(self.output):
            if offset != report["play_edits"][0]["absolute_offset"]:
                stray = offset
                break
        self.assertIsNotNone(stray)
        with open(self.output, "r+b") as handle:
            handle.seek(stray + patcher.RESOURCE_HEADER_SIZE + 0x40)
            original = handle.read(1)
            handle.seek(stray + patcher.RESOURCE_HEADER_SIZE + 0x40)
            handle.write(bytes([original[0] ^ 0xFF]))

        with self.assertRaises(Exception) as caught:
            verifier.verify(source, self.output, report)
        self.assertNotIsInstance(caught.exception, unittest.SkipTest)

    def test_a_book_at_the_play_capacity_is_refused(self) -> None:
        full = [(BOOK_ID, synthetic_resource(
            synthetic_body(plays=insp.PLAY_CAPACITY)))]
        source = self.write_source(full)
        with self.assertRaises(patcher.PlaybookPatchError) as caught:
            patcher.patch(source, patcher.load_recipe(self.write_recipe()),
                          self.output, workdir=self.tmp)
        self.assertIn("270", str(caught.exception))
        self.assertFalse(self.output.exists(),
                         "a refused patch must not create an output image")

    def test_a_wrong_length_compile_is_refused_before_the_output_exists(self) -> None:
        source = self.write_source()
        real = fpwriter.compile_formation_play_creations

        def truncating(raw, *args, **kwargs):
            result = real(raw, *args, **kwargs)
            object.__setattr__(result, "replacement", result.replacement[:-16])
            return result

        with mock.patch.object(fpwriter, "compile_formation_play_creations",
                               side_effect=truncating):
            with self.assertRaises(patcher.PlaybookPatchError) as caught:
                patcher.patch(source, patcher.load_recipe(self.write_recipe()),
                              self.output, workdir=self.tmp)
        self.assertIn("fixed allocation", str(caught.exception))
        self.assertFalse(self.output.exists(),
                         "a fixed-allocation refusal must not create an output image")

    def test_an_unknown_book_id_is_refused(self) -> None:
        source = self.write_source()
        recipe = json.loads(json.dumps(RECIPE))
        recipe["edits"][0]["book_id"] = "0xdeadbeef"
        with self.assertRaises(patcher.PlaybookPatchError):
            patcher.patch(source, patcher.load_recipe(self.write_recipe(recipe)),
                          self.output, workdir=self.tmp)
        self.assertFalse(self.output.exists())

    def test_a_bad_recipe_schema_is_refused(self) -> None:
        path = self.tmp / "bad.json"
        path.write_text(json.dumps({"schema": "nope", "edits": []}), encoding="utf-8")
        with self.assertRaises(patcher.PlaybookPatchError):
            patcher.load_recipe(path)


class ShippedSelftestTests(unittest.TestCase):
    """The lane validator runs these, and a shipped tree has no tests/."""

    def test_each_tool_has_a_passing_selftest(self) -> None:
        for tool in ("nfl2k5_ps2_playbook_patch.py",
                     "nfl2k5_ps2_playbook_target_catalog.py"):
            with self.subTest(tool=tool):
                result = subprocess.run(
                    [sys.executable, str(_REPO_ROOT / "tools" / tool), "--selftest"],
                    cwd=str(_REPO_ROOT), capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("SELFTEST_PASS", result.stdout)


class CatalogTests(_Case):
    def test_the_catalog_reports_counts_and_headroom(self) -> None:
        import nfl2k5_ps2_playbook_target_catalog as catalog

        source = self.write_source()
        built = catalog.build(source)
        self.assertEqual(built["totals"]["books"], 2)
        self.assertEqual(built["totals"]["plays"], 4)
        self.assertEqual(built["totals"]["books_at_play_capacity"], 0)
        for row in built["books"]:
            self.assertEqual(row["play_headroom"], insp.PLAY_CAPACITY - 2)
            self.assertFalse(row["compressed"])
            self.assertNotIn("raw", row)


if __name__ == "__main__":
    unittest.main()
