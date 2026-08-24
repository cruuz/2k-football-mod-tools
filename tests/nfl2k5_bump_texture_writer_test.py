"""The jersey bump-map writer must stay fixed-span, fail-closed, and retail-free.

Fixtures are synthetic: one ``Unif`` outer with a single compressed
``bump_sleeve``-shaped TXTR chunk (128x128 A8R8G8B8 swizzled, retail slot
dimensions) inside an extracted index/pack-B pair. No game file is touched.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_bump_texture_writer as writer  # noqa: E402
from nfl_all_texture_xiso_workflow import generate_mips  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402
from nfl_txtr import (  # noqa: E402
    COMPRESSED_SENTINEL,
    HEADER,
    compress_vc_lz,
    encode_rgba_png,
    swizzle_2d,
)


WIDTH = 128
HEIGHT = 128
MIPS = 4
SYSTEM_BYTES = 128
MIP_DIMS = [(WIDTH >> level, HEIGHT >> level) for level in range(MIPS)]
VIDEO_BYTES = sum(w * h * 4 for w, h in MIP_DIMS)
PACKED_FORMAT = (2 << 4) | (0x06 << 8) | (MIPS << 16) | (7 << 20) | (7 << 24)
LOGICAL_NAME = "09A0.IFF"
NAME_ID = zlib.crc32(LOGICAL_NAME.upper().encode("utf-16le")) & 0xFFFFFFFF


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _system_buffer() -> bytes:
    buffer = bytearray(SYSTEM_BYTES)
    buffer[0x0C:0x10] = b"TXTR"
    name_offset = 0x30
    descriptor_offset = 0x60
    struct.pack_into("<I", buffer, 0x10, name_offset - 0x0F)
    struct.pack_into("<I", buffer, 0x14, descriptor_offset - 0x13)
    encoded = "bump_sleeve".encode("utf-16le") + b"\0\0"
    buffer[name_offset : name_offset + len(encoded)] = encoded
    struct.pack_into(
        "<6I", buffer, descriptor_offset, 0, 0, 0, PACKED_FORMAT, 0, 0
    )
    return bytes(buffer)


def _pattern_rgba(step: int, phase: int) -> bytes:
    pixels = bytearray(WIDTH * HEIGHT * 4)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            value = 255 if ((y // step) + (x // step) + phase) % 2 else 0
            offset = (y * WIDTH + x) * 4
            pixels[offset : offset + 4] = bytes((value, value, value, 255))
    return bytes(pixels)


def _noise_rgba(seed: int) -> bytes:
    state = random.Random(seed)
    return bytes(state.randrange(256) for _ in range(WIDTH * HEIGHT * 4))


def _swizzled_chain(rgba: bytes) -> bytes:
    levels = generate_mips(rgba, WIDTH, HEIGHT, MIPS)
    return b"".join(
        swizzle_2d(level.rgba, level.width, level.height, 4) for level in levels
    )


def _build_fixture() -> tuple[bytes, bytes, bytes]:
    """Return (outer_bytes, fixture_top_rgba, decoded_body)."""

    retail_rgba = _pattern_rgba(8, 0)
    decoded = _system_buffer() + _swizzled_chain(retail_rgba)
    stream, _info = compress_vc_lz(decoded, offset_bits=13, verify_roundtrip=True)
    stored_size = len(stream) + 512
    span_body = stream + bytes(stored_size - len(stream))
    chunk0 = (
        HEADER.pack(b"Unif", 32, 0, 0, 0, 0, 0, 0) + bytes(range(32))
    )
    chunk1 = (
        HEADER.pack(
            b"TXTR", stored_size, SYSTEM_BYTES, VIDEO_BYTES,
            COMPRESSED_SENTINEL, 16, 0, 0,
        )
        + span_body
    )
    return chunk0 + chunk1, retail_rgba, decoded


def _index_pack(outer: bytes) -> bytes:
    blocks = (len(outer) + 0x7FF) // 0x800
    slots = [0] * 36
    slots[writer.PACK_B_ORDINAL] = blocks
    header = struct.pack("<III", 1, 0, 16)
    table = struct.pack("<36I", *slots)
    entry = struct.pack("<III", NAME_ID, len(outer), 0)
    return header + table + entry


def _write_fixture(directory: Path) -> tuple[bytes, Path]:
    outer, retail_rgba, _decoded = _build_fixture()
    blocks = (len(outer) + 0x7FF) // 0x800
    pack = outer + bytes(blocks * 0x800 - len(outer))
    (directory / writer.INDEX_VOLUME).write_bytes(_index_pack(outer))
    (directory / writer.PACK_B_NAME).write_bytes(pack)
    return retail_rgba, directory


CROSS_FIRST_PACK_BYTES = 0x1000
PACK_A_NAME = writer.PACK_NAMES[writer.PACK_NAMES.index("A")]


def _cross_index_pack(outer: bytes) -> bytes:
    first_blocks = CROSS_FIRST_PACK_BYTES // 0x800
    rest = len(outer) - CROSS_FIRST_PACK_BYTES
    rest_blocks = (rest + 0x7FF) // 0x800
    slots = [0] * 36
    slots[writer.PACK_NAMES.index("A")] = first_blocks
    slots[writer.PACK_B_ORDINAL] = rest_blocks
    header = struct.pack("<III", 1, 0, 16)
    table = struct.pack("<36I", *slots)
    entry = struct.pack("<III", NAME_ID, len(outer), 0)
    return header + table + entry


def _write_cross_fixture(directory: Path) -> tuple[bytes, Path]:
    outer, retail_rgba, _decoded = _build_fixture()
    assert len(outer) > CROSS_FIRST_PACK_BYTES, "fixture must cross the extent"
    first = outer[:CROSS_FIRST_PACK_BYTES]
    rest = outer[CROSS_FIRST_PACK_BYTES:]
    rest_blocks = (len(rest) + 0x7FF) // 0x800
    (directory / writer.INDEX_VOLUME).write_bytes(_cross_index_pack(outer))
    (directory / PACK_A_NAME).write_bytes(first)
    (directory / writer.PACK_B_NAME).write_bytes(
        rest + bytes(rest_blocks * 0x800 - len(rest))
    )
    return retail_rgba, directory


class LogicalNameTests(unittest.TestCase):
    def test_first_lookup_is_exact_and_misses_are_none(self) -> None:
        def name_id(name: str) -> int:
            return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF

        self.assertEqual(writer.logical_name_for(name_id("00H0.IFF")), "00H0.IFF")
        self.assertEqual(writer.logical_name_for(name_id("09A0.IFF")), "09A0.IFF")
        self.assertIsNone(writer.logical_name_for(0xDEADBEEF))


class BumpTextureWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source_dir = self.work / "src"
        self.source_dir.mkdir()
        self.retail_rgba, _path = _write_fixture(self.source_dir)

    def _write_png(self, rgba: bytes, name: str) -> Path:
        path = self.work / name
        path.write_bytes(encode_rgba_png(WIDTH, HEIGHT, rgba))
        return path

    def test_catalog_discovers_the_synthetic_bump_chunk(self) -> None:
        result = writer.catalog(self.source_dir)
        self.assertEqual(result["schema"], writer.CATALOG_SCHEMA)
        self.assertEqual(result["package_count"], 1)
        package = result["packages"][0]
        self.assertEqual(package["outer_index"], 0)
        self.assertEqual(package["logical_name"], LOGICAL_NAME)
        self.assertEqual(package["name_id"], NAME_ID)
        self.assertEqual(len(package["chunks"]), 1)
        chunk = package["chunks"][0]
        self.assertEqual(chunk["name"], "bump_sleeve")
        self.assertEqual((chunk["width"], chunk["height"]), (WIDTH, HEIGHT))
        self.assertEqual(chunk["mip_levels"], MIPS)
        self.assertEqual(chunk["format_code"], 0x06)
        self.assertEqual(chunk["video_bytes"], VIDEO_BYTES)
        self.assertEqual(chunk["chunk_index"], 1)
        self.assertEqual(chunk["span_size"], HEADER.size + chunk["stored_size"])

    def test_list_packages_reads_only_the_entry_table(self) -> None:
        rows = writer.list_packages(self.source_dir)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outer_index"], 0)
        self.assertEqual(rows[0]["logical_name"], LOGICAL_NAME)

    def test_export_round_trips_the_retail_top_mip(self) -> None:
        png, metadata = writer.export_bump(self.source_dir, 0, "bump_sleeve")
        width, height, rgba = decode_rgba_png(png, (WIDTH, HEIGHT))
        self.assertEqual((width, height), (WIDTH, HEIGHT))
        self.assertEqual(rgba, self.retail_rgba)
        self.assertEqual(metadata["rgba_sha256"], _digest(self.retail_rgba))
        self.assertEqual(metadata["chunk_index"], 1)

    def test_import_authored_pattern_verifies_and_touches_only_the_span(
        self,
    ) -> None:
        target_dir = self.work / "dst"
        target_dir.mkdir()
        _write_fixture(target_dir)
        authored = _pattern_rgba(4, 1)
        png = self._write_png(authored, "authored.png")

        evidence = writer.import_bump(
            self.source_dir, target_dir, 0, "bump_sleeve", png
        )
        self.assertEqual(evidence["schema"], writer.IMPORT_SCHEMA)
        self.assertNotEqual(
            evidence["retail_span_sha256"], evidence["replacement_span_sha256"]
        )
        self.assertGreater(evidence["changed_byte_count"], 0)
        self.assertTrue(evidence["wrapper_preserved_except_scratch"])
        self.assertTrue(evidence["post_write_readback_matches"])
        self.assertLessEqual(
            evidence["statistics"]["recompressed_bytes"],
            writer.package_bump_slots(self.source_dir, 0)["chunks"][0][
                "stored_size"
            ],
        )

        verification = writer.verify_write(target_dir, 0, "bump_sleeve", authored)
        self.assertTrue(verification["ok"], verification)
        self.assertTrue(all(verification["checks"].values()))

        source_pack = (self.source_dir / "B").read_bytes()
        target_pack = (target_dir / "B").read_bytes()
        changed = [
            index
            for index, (a, b) in enumerate(zip(source_pack, target_pack))
            if a != b
        ]
        self.assertTrue(changed)
        slots = writer.package_bump_slots(self.source_dir, 0)
        chunk_offset = slots["chunks"][0]["chunk_offset"]
        span_size = slots["chunks"][0]["span_size"]
        self.assertTrue(all(chunk_offset <= i < chunk_offset + span_size
                            for i in changed))
        original_header = HEADER.unpack_from(source_pack, chunk_offset)
        written_header = HEADER.unpack_from(target_pack, chunk_offset)
        self.assertEqual(original_header[:5], written_header[:5])
        self.assertEqual(original_header[6:], written_header[6:])
        self.assertGreaterEqual(written_header[5], original_header[5])

    def test_dimension_mismatch_is_refused(self) -> None:
        target_dir = self.work / "dst"
        target_dir.mkdir()
        _write_fixture(target_dir)
        wrong = self.work / "wrong.png"
        wrong.write_bytes(
            encode_rgba_png(64, 64, _pattern_rgba(4, 1)[: 64 * 64 * 4])
        )
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "exactly"):
            writer.import_bump(
                self.source_dir, target_dir, 0, "bump_sleeve", wrong
            )

    def test_identical_source_and_target_are_refused(self) -> None:
        authored = self._write_png(_pattern_rgba(4, 1), "authored.png")
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "copy"):
            writer.import_bump(
                self.source_dir, self.source_dir, 0, "bump_sleeve", authored
            )
        linked_dir = self.work / "linked"
        linked_dir.mkdir()
        (linked_dir / writer.INDEX_VOLUME).write_bytes(
            (self.source_dir / writer.INDEX_VOLUME).read_bytes()
        )
        (linked_dir / writer.PACK_B_NAME).hardlink_to(
            self.source_dir / writer.PACK_B_NAME
        )
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "copy"):
            writer.import_bump(
                self.source_dir, linked_dir, 0, "bump_sleeve", authored
            )

    def test_oversized_recompression_is_refused(self) -> None:
        target_dir = self.work / "dst"
        target_dir.mkdir()
        _write_fixture(target_dir)
        noise = self._write_png(_noise_rgba(45), "noise.png")
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "fit"):
            writer.import_bump(
                self.source_dir, target_dir, 0, "bump_sleeve", noise
            )
        self.assertEqual(
            (target_dir / "B").read_bytes(),
            (self.source_dir / "B").read_bytes(),
        )

    def test_absent_chunk_and_layout_drift_are_refused(self) -> None:
        target_dir = self.work / "dst"
        target_dir.mkdir()
        _write_fixture(target_dir)
        authored = self._write_png(_pattern_rgba(4, 1), "authored.png")
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "bump_jersey"):
            writer.import_bump(
                self.source_dir, target_dir, 0, "bump_jersey", authored
            )
        drifted = bytearray((target_dir / writer.INDEX_VOLUME).read_bytes())
        drifted[-1] ^= 0xFF
        (target_dir / writer.INDEX_VOLUME).write_bytes(bytes(drifted))
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "layout"):
            writer.import_bump(
                self.source_dir, target_dir, 0, "bump_sleeve", authored
            )

    def test_preview_reports_before_and_after(self) -> None:
        authored = _pattern_rgba(4, 1)
        png = self._write_png(authored, "authored.png")
        preview = writer.preview_import(
            self.source_dir, 0, "bump_sleeve", png
        )
        self.assertEqual(
            decode_rgba_png(preview["retail_png"], (WIDTH, HEIGHT))[2],
            self.retail_rgba,
        )
        self.assertEqual(
            decode_rgba_png(preview["authored_png"], (WIDTH, HEIGHT))[2],
            authored,
        )
        self.assertEqual(preview["authored_rgba"], authored)


class CrossExtentTests(unittest.TestCase):
    """Packages whose entry crosses a pack boundary stay fully editable."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source_dir = self.work / "src"
        self.source_dir.mkdir()
        self.retail_rgba, _path = _write_cross_fixture(self.source_dir)

    def _write_png(self, rgba: bytes, name: str) -> Path:
        path = self.work / name
        path.write_bytes(encode_rgba_png(WIDTH, HEIGHT, rgba))
        return path

    def test_catalog_flags_the_cross_extent_package(self) -> None:
        result = writer.catalog(self.source_dir)
        self.assertEqual(result["package_count"], 1)
        self.assertEqual(result["skipped_package_count"], 0)
        package = result["packages"][0]
        self.assertTrue(package["cross_extent"])
        self.assertEqual(len(package["chunks"]), 1)

    def test_export_reads_across_the_extent_boundary(self) -> None:
        png, metadata = writer.export_bump(self.source_dir, 0, "bump_sleeve")
        _width, _height, rgba = decode_rgba_png(png, (WIDTH, HEIGHT))
        self.assertEqual(rgba, self.retail_rgba)
        self.assertEqual(metadata["rgba_sha256"], _digest(self.retail_rgba))

    def test_import_writes_the_split_span_and_verifies(self) -> None:
        target_dir = self.work / "dst"
        target_dir.mkdir()
        _write_cross_fixture(target_dir)
        authored = _pattern_rgba(4, 1)
        png = self._write_png(authored, "authored.png")

        evidence = writer.import_bump(
            self.source_dir, target_dir, 0, "bump_sleeve", png
        )
        self.assertTrue(evidence["target"]["cross_extent"])
        extents = evidence["target"]["span_extents"]
        self.assertEqual(len(extents), 2)
        self.assertEqual(extents[0]["pack_name"], PACK_A_NAME)
        self.assertEqual(extents[1]["pack_name"], writer.PACK_B_NAME)
        self.assertEqual(
            sum(row["size"] for row in extents), evidence["target"]["span_size"]
        )

        verification = writer.verify_write(target_dir, 0, "bump_sleeve", authored)
        self.assertTrue(verification["ok"], verification)

        for pack_name in (PACK_A_NAME, writer.PACK_B_NAME):
            source_pack = (self.source_dir / pack_name).read_bytes()
            target_pack = (target_dir / pack_name).read_bytes()
            self.assertEqual(len(source_pack), len(target_pack))
        slots = writer.package_bump_slots(self.source_dir, 0)
        chunk_offset = slots["chunks"][0]["chunk_offset"]
        span_size = slots["chunks"][0]["span_size"]
        changed_virtual: list[int] = []
        first = (self.source_dir / PACK_A_NAME).read_bytes()
        second = (self.source_dir / writer.PACK_B_NAME).read_bytes()
        target_first = (target_dir / PACK_A_NAME).read_bytes()
        target_second = (target_dir / writer.PACK_B_NAME).read_bytes()
        changed_virtual.extend(
            i for i, (a, b) in enumerate(zip(first, target_first)) if a != b
        )
        changed_virtual.extend(
            CROSS_FIRST_PACK_BYTES + i
            for i, (a, b) in enumerate(zip(second, target_second))
            if a != b
        )
        self.assertTrue(changed_virtual)
        self.assertTrue(
            all(chunk_offset <= i < chunk_offset + span_size
                for i in changed_virtual)
        )


class AuthoringTemplateTests(unittest.TestCase):
    def test_jersey_template_marks_the_retail_zones(self) -> None:
        png, metadata = writer.authoring_template("bump_jersey")
        width, height, rgba = decode_rgba_png(png, None)
        self.assertEqual((width, height), (512, 256))
        self.assertEqual(metadata["schema"], writer.TEMPLATE_SCHEMA)
        self.assertEqual(len(metadata["zones"]), 3)
        corner = rgba[0:4]
        flat = bytes(writer.TEMPLATE_FLAT_NORMAL[:3])
        self.assertEqual(corner[:3], flat)

    def test_zone_free_slots_produce_a_clean_flat_template(self) -> None:
        png, metadata = writer.authoring_template("bump_sock")
        width, height, rgba = decode_rgba_png(png, None)
        self.assertEqual((width, height), (128, 128))
        self.assertEqual(metadata["zones"], [])
        flat = bytes(writer.TEMPLATE_FLAT_NORMAL)
        self.assertEqual(rgba, flat * (width * height))

    def test_unknown_slot_is_refused(self) -> None:
        with self.assertRaisesRegex(writer.BumpTextureWriterError, "not one of"):
            writer.authoring_template("bump_shoes1")


class _CountingIndexReader:
    """Wraps ``_read_index_table`` so tests can count index volume reads."""

    def __init__(self) -> None:
        self.calls = 0
        self._original = writer._read_index_table

    def __call__(self, image: object) -> bytes:
        self.calls += 1
        return self._original(image)

    def __enter__(self) -> "_CountingIndexReader":
        writer._read_index_table = self  # type: ignore[assignment]
        return self

    def __exit__(self, *_exc: object) -> None:
        writer._read_index_table = self._original  # type: ignore[assignment]


class IndexCacheTests(unittest.TestCase):
    """The parsed entry table is memoized per index-volume identity."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source_dir = self.work / "src"
        self.source_dir.mkdir()
        _write_fixture(self.source_dir)
        writer.clear_index_cache()
        self.addCleanup(writer.clear_index_cache)

    def test_repeated_calls_parse_the_index_once(self) -> None:
        with _CountingIndexReader() as counter:
            writer.list_packages(self.source_dir)
            writer.catalog(self.source_dir)
            writer.package_bump_slots(self.source_dir, 0)
            writer.export_bump(self.source_dir, 0, "bump_sleeve")
        self.assertEqual(counter.calls, 1)

    def test_rewriting_the_index_invalidates_the_cache(self) -> None:
        index_path = self.source_dir / writer.INDEX_VOLUME
        original = index_path.read_bytes()
        with _CountingIndexReader() as counter:
            writer.list_packages(self.source_dir)
            writer.list_packages(self.source_dir)
            self.assertEqual(counter.calls, 1)
            index_path.write_bytes(original)
            future = index_path.stat().st_mtime_ns + 10_000_000_000
            os.utime(index_path, ns=(future, future))
            writer.list_packages(self.source_dir)
            self.assertEqual(counter.calls, 2)

    def test_a_changed_entry_table_is_reparsed_and_refused_loudly(self) -> None:
        index_path = self.source_dir / writer.INDEX_VOLUME
        writer.list_packages(self.source_dir)
        drifted = bytearray(index_path.read_bytes())
        drifted[-2] ^= 0xFF
        # A trailing byte changes the volume size outright: some filesystems
        # stamp mtime coarsely, so the test must not depend on it moving.
        drifted += b"\x00"
        index_path.write_bytes(bytes(drifted))
        with self.assertRaises(writer.BumpTextureWriterError):
            writer.list_packages(self.source_dir)

    def test_clear_index_cache_forces_a_reread(self) -> None:
        with _CountingIndexReader() as counter:
            writer.list_packages(self.source_dir)
            writer.clear_index_cache()
            writer.list_packages(self.source_dir)
        self.assertEqual(counter.calls, 2)

    def test_distinct_images_hold_distinct_cache_entries(self) -> None:
        other_dir = self.work / "other"
        other_dir.mkdir()
        _write_fixture(other_dir)
        with _CountingIndexReader() as counter:
            writer.list_packages(self.source_dir)
            writer.list_packages(other_dir)
            writer.list_packages(self.source_dir)
            writer.list_packages(other_dir)
        self.assertEqual(counter.calls, 2)


SECTOR = 0x800
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"


def _xiso_node(
    name: bytes, sector: int, size: int, attributes: int, right: int
) -> bytes:
    record = struct.pack("<HHII", 0, right, sector, size) + bytes(
        [attributes, len(name)]
    ) + name
    while len(record) % 4:
        record += b"\x00"
    return record


def _write_xiso_fixture(directory: Path) -> Path:
    """A minimal XDVDFS image holding vc_53450030/0 and vc_53450030/B."""

    outer, _retail_rgba, _decoded = _build_fixture()
    blocks = (len(outer) + 0x7FF) // 0x800
    pack = outer + bytes(blocks * SECTOR - len(outer))
    index_volume = _index_pack(outer)

    header_sector = 0x20
    root_sector = 0x21
    group_sector = 0x22
    index_sector = 0x23
    pack_sector = index_sector + (len(index_volume) + SECTOR - 1) // SECTOR
    image_size = (pack_sector * SECTOR) + len(pack)

    group_dir = (
        _xiso_node(b"0", index_sector, len(index_volume), 0x20, 4)
        + _xiso_node(b"B", pack_sector, len(pack), 0x20, 0)
    )
    root_dir = _xiso_node(
        b"vc_53450030", group_sector, len(group_dir), 0x10, 0
    )
    header = bytearray(SECTOR)
    header[:20] = XDVDFS_MAGIC
    struct.pack_into("<II", header, 20, root_sector, SECTOR)
    header[-20:] = XDVDFS_MAGIC

    image = bytearray(image_size)
    image[header_sector * SECTOR : header_sector * SECTOR + SECTOR] = header
    image[root_sector * SECTOR : root_sector * SECTOR + len(root_dir)] = root_dir
    image[group_sector * SECTOR : group_sector * SECTOR + len(group_dir)] = (
        group_dir
    )
    image[index_sector * SECTOR : index_sector * SECTOR + len(index_volume)] = (
        index_volume
    )
    image[pack_sector * SECTOR : pack_sector * SECTOR + len(pack)] = pack
    path = directory / "fixture.xiso"
    path.write_bytes(bytes(image))
    return path


class XisoIndexCacheTests(unittest.TestCase):
    """The XISO cache key carries the image identity and the index extent."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.image_path = _write_xiso_fixture(self.work)
        writer.clear_index_cache()
        self.addCleanup(writer.clear_index_cache)

    def test_repeated_xiso_calls_parse_the_index_once(self) -> None:
        with _CountingIndexReader() as counter:
            writer.list_packages(self.image_path)
            writer.list_packages(self.image_path)
            writer.export_bump(self.image_path, 0, "bump_sleeve")
        self.assertEqual(counter.calls, 1)

    def test_touching_the_image_invalidates_the_cache(self) -> None:
        with _CountingIndexReader() as counter:
            writer.list_packages(self.image_path)
            future = self.image_path.stat().st_mtime_ns + 10_000_000_000
            os.utime(self.image_path, ns=(future, future))
            writer.list_packages(self.image_path)
        self.assertEqual(counter.calls, 2)

    def test_the_xiso_export_matches_the_extracted_export(self) -> None:
        extracted_dir = self.work / "extracted"
        extracted_dir.mkdir()
        retail_rgba, _ = _write_fixture(extracted_dir)
        png, metadata = writer.export_bump(self.image_path, 0, "bump_sleeve")
        _width, _height, rgba = decode_rgba_png(png, (WIDTH, HEIGHT))
        self.assertEqual(rgba, retail_rgba)
        self.assertEqual(metadata["rgba_sha256"], _digest(retail_rgba))


if __name__ == "__main__":
    unittest.main()
