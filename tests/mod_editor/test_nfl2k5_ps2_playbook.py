"""The PS2 playbook patcher and its independent verifier, with no game data.

Everything here is synthetic: a ``PLAY`` body built field by field so the
shipped codec accepts it, wrapped in a synthetic outer archive, wrapped in a
real ISO9660 image from the reader's own test builder.  No disc, no retail
bytes, no network.

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
import struct
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools", Path(__file__).resolve().parent):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from test_ps2_iso9660 import build_iso  # noqa: E402

import nfl2k5_ps2_playbook_patch as patcher  # noqa: E402
import nfl2k5_ps2_playbook_verify as verifier  # noqa: E402

from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_formation_play_writer as fpwriter  # noqa: E402


BOOK_ID = 0x49CD9F21
OTHER_BOOK_ID = 0x2C3DEF14

# Family 1 (defense), type code 4.  The retail validator's ball-handler and
# snapper requirements are unconditional for this family, so a two-node
# coverage chain in every slot is the smallest play it accepts.
PLAY_FLAGS = 4 | (1 << 6)
CHAIN_OPS = (0x1B, 0x0D)          # Defense Start -> Zone Coverage
CHAINS_PER_BOOK = codec.SLOT_COUNT
NODES_PER_CHAIN = len(CHAIN_OPS)


def _put_rel(body: bytearray, field: int, target: int) -> None:
    """Store the book's self-relative pointer form: ``target = field - 1 + v``."""
    struct.pack_into("<i", body, field, target - field + 1)


def synthetic_body(formations: int = 3, plays: int = 2, categories: int = 2) -> bytes:
    """A ``0x13390`` playbook body the shipped inspector and validator accept."""
    body = bytearray(insp.BODY_SIZE)
    body[0x0C:0x10] = b"PLAY"
    struct.pack_into("<I", body, 0x10, 0x11)
    struct.pack_into("<i", body, 0x14, -19)
    body[0x20:0x28] = b"p\0l\0b\0\0\0"

    # --- name pool, then the zero tail the custom-name path requires ---
    pool = bytearray()
    offset = {}
    for key, text in (("book", "TESTBOOK"), ("formation", "FORMATION"),
                      ("play", "PLAY"), ("category", "CATEGORY")):
        offset[key] = insp.STRING_BASE + len(pool)
        pool += text.encode("utf-16le") + b"\0\0"
    body[insp.STRING_BASE:insp.STRING_BASE + len(pool)] = pool
    pool_end = insp.STRING_BASE + len(pool)
    struct.pack_into("<I", body, fpwriter.POOL_COUNT_WORD,
                     (pool_end - insp.STRING_BASE) // 2)

    # --- one two-node chain per slot, shared by every play ---
    blob = bytearray()
    for _slot in range(CHAINS_PER_BOOK):
        nodes = [codec.Node(op, 0, codec.decode_operands(op, 0)) for op in CHAIN_OPS]
        codec.assign_node_flags(nodes)
        for node in nodes:
            blob += node.to_bytes()
    node_count = len(blob) // insp.NODE_SIZE
    body[insp.NODE_BASE:insp.NODE_BASE + len(blob)] = blob

    struct.pack_into("<I", body, 0x34, formations)
    struct.pack_into("<I", body, 0x38, plays)
    struct.pack_into("<I", body, 0x3C, categories)
    struct.pack_into("<I", body, 0x40, node_count)
    _put_rel(body, 0x30, offset["book"])
    _put_rel(body, 0x44, insp.FORMATION_BASE)
    _put_rel(body, 0x48, insp.FORMATION_AUX_BASE)
    _put_rel(body, 0x60, insp.PLAY_BASE)
    _put_rel(body, 0x64, insp.CATEGORY_BASE)
    _put_rel(body, 0x68, insp.NODE_BASE)

    chains = []
    for slot in range(CHAINS_PER_BOOK):
        start = insp.NODE_BASE + slot * NODES_PER_CHAIN * insp.NODE_SIZE
        chains.append([bytes(body[start + n * insp.NODE_SIZE:
                                  start + (n + 1) * insp.NODE_SIZE])
                       for n in range(NODES_PER_CHAIN)])
    staged = [(0, chains[slot]) for slot in range(CHAINS_PER_BOOK)]
    descriptors = [codec.build_descriptor(PLAY_FLAGS, staged, slot, 0xB0)
                   for slot in range(CHAINS_PER_BOOK)]

    for index in range(plays):
        base = insp.PLAY_BASE + index * insp.PLAY_SIZE
        _put_rel(body, base, offset["play"])
        struct.pack_into("<I", body, base + 4, PLAY_FLAGS)
        for slot in range(CHAINS_PER_BOOK):
            struct.pack_into("<I", body, base + 8 + slot * 8, descriptors[slot])
            _put_rel(body, base + 0x0C + slot * 8,
                     insp.NODE_BASE + slot * NODES_PER_CHAIN * insp.NODE_SIZE)

    for index in range(formations):
        base = insp.FORMATION_BASE + index * insp.FORMATION_SIZE
        _put_rel(body, base, offset["formation"])
        struct.pack_into("<I", body, base + 4,
                         codec.FORMATION_FLAG_UNDER_CENTER | (1 << 8))
        body[base + 0x0D:base + 0x18] = bytes(range(11))     # package map
        for slot in range(CHAINS_PER_BOOK):
            record = base + codec.FORMATION_SLOT_BASE + slot * codec.FORMATION_SLOT_STRIDE
            body[record + 1] = (codec.NO_MIRROR << 4) | 3
            lateral = (slot - 5) * 120
            struct.pack_into("<hhh", body, record + 2, lateral, lateral, lateral)
            struct.pack_into("<hhh", body, record + 8, 0, 0, 0)
        aux = insp.FORMATION_AUX_BASE + index * insp.FORMATION_AUX_SIZE
        for link in range(insp.FORMATION_PLAY_LINKS):
            struct.pack_into("<H", body, aux + link * 2, 0 if link == 0 else 0x01FF)

    for index in range(categories):
        base = insp.CATEGORY_BASE + index * insp.CATEGORY_SIZE
        _put_rel(body, base, offset["category"])
        body[base + 4] = index
        body[base + 5:base + 16] = bytes(range(11))

    return bytes(body)


def synthetic_resource(body: bytes) -> bytes:
    """A ``PLAY`` chunk: the 32-byte header plus the body, uncompressed."""
    head = bytearray(patcher.RESOURCE_HEADER_SIZE)
    head[0:4] = b"PLAY"
    struct.pack_into("<4I", head, 4, len(body), len(body), 0, 0)
    return bytes(head) + body


def synthetic_pack(resources) -> bytes:
    """A ``/VC_20919/0.`` outer archive holding one chunk per entry."""
    count = len(resources)
    table_end = patcher.OUTER_HEADER_SIZE + count * patcher.OUTER_ENTRY_SIZE
    block = -(-table_end // patcher.ALIGNMENT)
    placed = []
    for name_id, payload in resources:
        placed.append((name_id, len(payload), block, payload))
        block += -(-len(payload) // patcher.ALIGNMENT)
    buffer = bytearray(block * patcher.ALIGNMENT)
    struct.pack_into("<III", buffer, 0, count, 0, 1)
    struct.pack_into("<I", buffer, 0x0C, block)
    for index, (name_id, size, at, payload) in enumerate(placed):
        struct.pack_into("<III", buffer,
                         patcher.OUTER_HEADER_SIZE + index * patcher.OUTER_ENTRY_SIZE,
                         name_id, size, at)
        buffer[at * patcher.ALIGNMENT:at * patcher.ALIGNMENT + len(payload)] = payload
    return bytes(buffer)


def synthetic_iso(pack: bytes) -> bytes:
    return build_iso({
        "SYSTEM.CNF": b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.01\r\n"
                      b"VMODE = NTSC\r\n",
        "SLUS_209.19": b"ELF" + bytes(4093),
        "VC_20919": {"0.": pack},
    })


def default_books(plays: int = 2):
    return [
        (BOOK_ID, synthetic_resource(synthetic_body(plays=plays))),
        (OTHER_BOOK_ID, synthetic_resource(synthetic_body(plays=plays))),
    ]


RECIPE = {
    "schema": patcher.SCHEMA,
    "edits": [{
        "book_id": "0x%08x" % BOOK_ID,
        "formations": [{"donor_formation_index": 0, "custom_name": "GUN TRIPS RT",
                        "slot_positions": [[(s - 5) * 130, -90 if s == 0 else 0]
                                           for s in range(11)]}],
        "plays": [{"donor_play_index": 0, "custom_name": "SMASH"}],
    }],
}


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ps2playbook-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = self.tmp / "source.iso"
        self.output = self.tmp / "output.iso"

    def write_source(self, books=None) -> Path:
        self.source.write_bytes(synthetic_iso(synthetic_pack(books or default_books())))
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
