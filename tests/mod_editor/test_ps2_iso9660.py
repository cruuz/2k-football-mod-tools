"""Conformance suite for the PS2 ISO9660 reader, writer and verifier.

The whole point of this file is that it needs **no game data**. Every image it
asserts against is built here, from scratch, into a temp directory: a real
primary volume descriptor, a real path table, real directory records, real
extents. A bare CI runner with an empty disk runs the entire suite green, which
is exactly why it can be trusted to keep running -- the checks that matter most
here are the ones nobody would ever be able to run if they were gated on a
1.6 GB retail disc.

That is the same lesson as ``tests/mod_editor/test_xiso_layout_tolerance.py``,
which exists because a reader pinned one rip of one Xbox disc and turned away
users holding legitimate copies. The PS2 side has the identical hazard in a
different costume, and it is already measured:

* ``Madden NFL 09 (USA).iso`` -- retail, **empty** volume id, **0** slack.
* ``Madden NFL 12 Deluxe 2026 (USA).iso`` -- a community rebuild of the same
  filesystem shape carrying volume id ``MADDEN_12_MOD`` and **18,432 bytes**
  of trailing padding past the declared volume.

Neither of those differences is corruption, so the builder below takes
``volume_id`` and ``slack`` as ordinary parameters and the suite asserts that
both extremes read identically and survive a write untouched. The container may
vary; the contents may not.

What is deliberately NOT relaxed, and is asserted hard:

* a replacement lives inside its existing extent or it is refused -- no
  relocation, no growth, no rebuild;
* the on-disc declared length is rewritten in place, and the little-endian and
  big-endian halves of that both-endian field must agree, because a disagreement
  is precisely the shape of a half-finished write;
* ``parent_lba`` / ``record_offset`` on a returned entry are re-read from the
  image and decoded again here, independently, because the writer aims at those
  two numbers and an off-by-one in them silently corrupts a neighbouring
  record on a real disc;
* the verifier is proven able to **fail**. Two tests mutate a single byte of a
  known-good output -- one outside every declared range, one inside a declared
  range -- and require a raise. A verifier that cannot fail is not a verifier,
  it is a rubber stamp, and those two tests are the most valuable in this file.

Out of scope for v1, and therefore deliberately untested: growing a file,
rebuilding an image, path-table rewriting, Joliet / Rock Ridge, UDF,
multi-extent files, and adding or deleting entries.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import ps2_iso9660 as iso  # noqa: E402
import ps2_iso9660_verify as isoverify  # noqa: E402
import ps2_iso9660_writer as isowriter  # noqa: E402


# ---------------------------------------------------------------------------
# The synthetic ISO9660 builder.
#
# This is the load-bearing piece of the file: everything below tests against
# images it produced. It emits ECMA-119 structures by hand rather than shelling
# out to mkisofs, so the suite has no tooling dependency and can put the image
# into shapes a mastering tool would not (odd slack, empty volume id, missing
# ";1" version suffixes, raw 2352-byte CD sectors).
# ---------------------------------------------------------------------------

SECTOR = 2048                  # ISO9660 logical block, and PS2 DVD sector size
RAW_SECTOR = 2352              # raw CD sector (Mode 2 Form 1)
RAW_DATA_OFFSET = 24           # sync(12) + header(4) + subheader(8)

_PVD_LBA = 16                  # the system area occupies sectors 0..15
_TERMINATOR_LBA = 17
_PATH_TABLE_L_LBA = 18
_PATH_TABLE_M_LBA = 19
_FIRST_EXTENT_LBA = 20

_DIRECTORY_FLAG = 0x02
_MAX_IDENT = 32                # long enough to pad every identifier we emit

# 1 January 2000, UTC. Fixed so two builds of the same tree are byte-identical.
_RECORDING_TIME = bytes((100, 1, 1, 0, 0, 0, 0))


def _both_endian_32(value: int) -> bytes:
    return struct.pack("<I", value) + struct.pack(">I", value)


def _both_endian_16(value: int) -> bytes:
    return struct.pack("<H", value) + struct.pack(">H", value)


def _read_both_endian_32(blob: bytes, offset: int) -> "tuple[int, int]":
    """Return the (little, big) halves separately so a test can compare them."""
    little = struct.unpack_from("<I", blob, offset)[0]
    big = struct.unpack_from(">I", blob, offset + 4)[0]
    return little, big


def _record_length(identifier: bytes) -> int:
    length = 33 + len(identifier)
    return length + (length % 2)          # records are padded to even length


def _directory_record(identifier: bytes, lba: int, length: int, is_dir: bool) -> bytes:
    """One ECMA-119 9.1 directory record.

    Byte 10 is where the both-endian data length lives; that is the field the
    writer rewrites in place, and the offset is asserted directly in
    :class:`DirectoryRecordAddressingTests`.
    """
    total = _record_length(identifier)
    record = bytearray(total)
    record[0] = total
    record[1] = 0                                       # extended attr length
    record[2:10] = _both_endian_32(lba)
    record[10:18] = _both_endian_32(length)
    record[18:25] = _RECORDING_TIME
    record[25] = _DIRECTORY_FLAG if is_dir else 0x00
    record[26] = 0                                      # file unit size
    record[27] = 0                                      # interleave gap
    record[28:32] = _both_endian_16(1)                  # volume sequence number
    record[32] = len(identifier)
    record[33:33 + len(identifier)] = identifier
    return bytes(record)


def _pack_directory_extent(records: "list[bytes]") -> bytes:
    """Lay records out, honouring the rule that none may cross a block edge."""
    out = bytearray()
    for record in records:
        used = len(out) % SECTOR
        if used + len(record) > SECTOR:
            out += bytes(SECTOR - used)
        out += record
    if len(out) % SECTOR:
        out += bytes(SECTOR - len(out) % SECTOR)
    return bytes(out)


class _Node:
    """A planned directory or file: identifier, payload, extent placement."""

    def __init__(self, identifier: bytes, path: str, is_dir: bool) -> None:
        self.identifier = identifier
        self.path = path
        self.is_dir = is_dir
        self.data = b""
        self.children: "list[_Node]" = []
        self.parent: "_Node | None" = None
        self.lba = 0
        self.length = 0

    def __repr__(self) -> str:                                # pragma: no cover
        return "<_Node {} lba={} len={}>".format(self.path, self.lba, self.length)


def _stored_identifier(name: str, is_dir: bool, version_suffix: bool) -> bytes:
    """Name as ISO9660 stores it: upper case, and ``;1`` on files.

    A caller can spell the version explicitly (``"FOO.BIN;3"``) or turn the
    suffix off wholesale -- some rebuild tools omit it, and ``find`` has to cope
    with either, so the fixture has to be able to produce either.
    """
    name = name.upper()
    if is_dir:
        return name.encode("ascii")
    if ";" in name or not version_suffix:
        return name.encode("ascii")
    return (name + ";1").encode("ascii")


def _visible_path(parent_path: str, identifier: bytes) -> str:
    name = identifier.decode("ascii").split(";")[0]
    if parent_path == "/":
        return "/" + name
    return parent_path + "/" + name


def _build_tree(tree: "dict", version_suffix: bool) -> _Node:
    root = _Node(b"\x00", "/", True)

    def populate(node: _Node, mapping: "dict") -> None:
        children = []
        for name, value in mapping.items():
            is_dir = isinstance(value, dict)
            identifier = _stored_identifier(name, is_dir, version_suffix)
            child = _Node(identifier, _visible_path(node.path, identifier), is_dir)
            child.parent = node
            if is_dir:
                populate(child, value)
            else:
                child.data = bytes(value)
            children.append(child)
        # ECMA-119 9.3: identifiers sort as if padded with 0x20 to equal length.
        node.children = sorted(children, key=lambda c: c.identifier.ljust(_MAX_IDENT, b" "))

    populate(root, tree)
    return root


def _plan_layout(root: _Node) -> "tuple[list[_Node], list[_Node], int]":
    """Assign every extent an LBA and a declared length.

    Directories first (breadth first, so the root is lowest), then files. A
    directory's size depends only on its children's *names*, never on their
    addresses, so sizing can run before placement and there is no fixpoint to
    iterate.
    """
    directories = [root]
    index = 0
    while index < len(directories):
        for child in directories[index].children:
            if child.is_dir:
                directories.append(child)
        index += 1

    for directory in directories:
        records = [
            _directory_record(b"\x00", 0, 0, True),
            _directory_record(b"\x01", 0, 0, True),
        ]
        records += [
            _directory_record(child.identifier, 0, 0, child.is_dir)
            for child in directory.children
        ]
        directory.length = len(_pack_directory_extent(records))

    cursor = _FIRST_EXTENT_LBA
    for directory in directories:
        directory.lba = cursor
        cursor += directory.length // SECTOR

    files: "list[_Node]" = []
    for directory in directories:
        for child in directory.children:
            if not child.is_dir:
                files.append(child)
    for node in files:
        node.lba = cursor
        node.length = len(node.data)
        # A zero-length file still gets a block so its LBA is a real address.
        cursor += max(1, (len(node.data) + SECTOR - 1) // SECTOR)

    return directories, files, cursor


def _primary_volume_descriptor(
    volume_id: str, volume_blocks: int, root: _Node, path_table_size: int
) -> bytes:
    pvd = bytearray(SECTOR)
    pvd[0] = 1                                          # primary volume descriptor
    pvd[1:6] = b"CD001"
    pvd[6] = 1                                          # descriptor version
    pvd[8:40] = b"PLAYSTATION".ljust(32, b" ")          # system identifier
    pvd[40:72] = volume_id.upper().encode("ascii").ljust(32, b" ")
    pvd[80:88] = _both_endian_32(volume_blocks)
    pvd[120:124] = _both_endian_16(1)                   # volume set size
    pvd[124:128] = _both_endian_16(1)                   # volume sequence number
    pvd[128:132] = _both_endian_16(SECTOR)              # logical block size
    pvd[132:140] = _both_endian_32(path_table_size)
    pvd[140:144] = struct.pack("<I", _PATH_TABLE_L_LBA)
    pvd[144:148] = struct.pack("<I", 0)                 # optional L path table
    pvd[148:152] = struct.pack(">I", _PATH_TABLE_M_LBA)
    pvd[152:156] = struct.pack(">I", 0)                 # optional M path table
    pvd[156:190] = _directory_record(b"\x00", root.lba, root.length, True)
    pvd[190:318] = b" " * 128                           # volume set identifier
    pvd[318:446] = b" " * 128                           # publisher
    pvd[446:574] = b" " * 128                           # data preparer
    pvd[574:702] = b" " * 128                           # application
    pvd[702:739] = b" " * 37                            # copyright file
    pvd[739:776] = b" " * 37                            # abstract file
    pvd[776:813] = b" " * 37                            # bibliographic file
    stamp = b"2000010100000000" + bytes((0,))
    for base in (813, 830, 847, 864):
        pvd[base:base + 17] = stamp
    pvd[881] = 1                                        # file structure version
    return bytes(pvd)


def _path_table(directories: "list[_Node]", little: bool) -> bytes:
    numbers = {id(node): index + 1 for index, node in enumerate(directories)}
    out = bytearray()
    for node in directories:
        identifier = b"\x00" if node.parent is None else node.identifier
        parent = 1 if node.parent is None else numbers[id(node.parent)]
        out.append(len(identifier))
        out.append(0)                                   # extended attr length
        out += struct.pack("<I" if little else ">I", node.lba)
        out += struct.pack("<H" if little else ">H", parent)
        out += identifier
        if len(identifier) % 2:
            out.append(0)
    return bytes(out)


def _bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def _raw_cd_sector(lba: int, user: bytes) -> bytes:
    """Wrap one 2048-byte block as a raw Mode 2 Form 1 CD sector."""
    minutes, rest = divmod(lba + 150, 60 * 75)
    seconds, frames = divmod(rest, 75)
    sector = bytearray(RAW_SECTOR)
    sector[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    sector[12] = _bcd(minutes)
    sector[13] = _bcd(seconds)
    sector[14] = _bcd(frames)
    sector[15] = 2                                      # Mode 2
    sector[16:24] = bytes((0, 0, 0x08, 0, 0, 0, 0x08, 0))   # Form 1 subheader x2
    sector[RAW_DATA_OFFSET:RAW_DATA_OFFSET + SECTOR] = user
    return bytes(sector)


def build_iso(
    tree: "dict",
    volume_id: str = "SYNTHETIC",
    slack: int = 0,
    version_suffix: bool = True,
    raw_cd: bool = False,
) -> bytes:
    """A real, minimal, bootable-shaped ISO9660 image as bytes.

    ``tree`` maps names to ``bytes`` (a file) or to a nested dict (a directory),
    to any depth::

        build_iso({"SYSTEM.CNF": b"...", "DATA": {"SUB": {"DEEP.BIN": b"..."}}})

    ``slack`` appends bytes past the declared volume, reproducing the Deluxe
    rebuild. ``version_suffix=False`` stores file identifiers without ``;1``.
    ``raw_cd=True`` re-wraps every block as a 2352-byte Mode 2 Form 1 sector,
    which is what a PS2 CD title (``.bin``/``.cue``) actually looks like.
    """
    root = _build_tree(tree, version_suffix)
    directories, files, volume_blocks = _plan_layout(root)

    table_l = _path_table(directories, little=True)
    table_m = _path_table(directories, little=False)

    image = bytearray(volume_blocks * SECTOR)
    image[_PVD_LBA * SECTOR:_PVD_LBA * SECTOR + SECTOR] = _primary_volume_descriptor(
        volume_id, volume_blocks, root, len(table_l)
    )
    terminator = bytearray(SECTOR)
    terminator[0] = 0xFF
    terminator[1:6] = b"CD001"
    terminator[6] = 1
    image[_TERMINATOR_LBA * SECTOR:_TERMINATOR_LBA * SECTOR + SECTOR] = terminator
    image[_PATH_TABLE_L_LBA * SECTOR:_PATH_TABLE_L_LBA * SECTOR + len(table_l)] = table_l
    image[_PATH_TABLE_M_LBA * SECTOR:_PATH_TABLE_M_LBA * SECTOR + len(table_m)] = table_m

    for directory in directories:
        parent = directory.parent or directory
        records = [
            _directory_record(b"\x00", directory.lba, directory.length, True),
            _directory_record(b"\x01", parent.lba, parent.length, True),
        ]
        records += [
            _directory_record(child.identifier, child.lba, child.length, child.is_dir)
            for child in directory.children
        ]
        extent = _pack_directory_extent(records)
        assert len(extent) == directory.length, "directory sizing pass disagreed"
        start = directory.lba * SECTOR
        image[start:start + len(extent)] = extent

    for node in files:
        start = node.lba * SECTOR
        image[start:start + len(node.data)] = node.data

    if raw_cd:
        wrapped = bytearray()
        for lba in range(volume_blocks):
            wrapped += _raw_cd_sector(lba, bytes(image[lba * SECTOR:(lba + 1) * SECTOR]))
        image = wrapped

    return bytes(image) + bytes(slack)


def expected_paths(tree: "dict", version_suffix: bool = True) -> "set[str]":
    """The ``IsoEntry.path`` set ``build_iso(tree)`` should produce."""
    return set(expected_files(tree, version_suffix)) | expected_directories(
        tree, version_suffix
    )


def expected_files(tree: "dict", version_suffix: bool = True) -> "dict":
    """``{path: contents}`` for every file in *tree*, at its visible path."""
    found = {}

    def walk(mapping: "dict", prefix: str) -> None:
        for name, value in mapping.items():
            is_dir = isinstance(value, dict)
            identifier = _stored_identifier(name, is_dir, version_suffix)
            path = _visible_path(prefix, identifier)
            if is_dir:
                walk(value, path)
            else:
                found[path] = bytes(value)

    walk(tree, "/")
    return found


def expected_directories(tree: "dict", version_suffix: bool = True) -> "set[str]":
    found = set()

    def walk(mapping: "dict", prefix: str) -> None:
        for name, value in mapping.items():
            if not isinstance(value, dict):
                continue
            path = _visible_path(prefix, _stored_identifier(name, True, version_suffix))
            found.add(path)
            walk(value, path)

    walk(tree, "/")
    return found


# ---------------------------------------------------------------------------
# Independent decoding helpers, used to check the modules rather than trust
# them. These re-derive addresses from raw bytes exactly as the verifier is
# required to.
# ---------------------------------------------------------------------------

def decode_records(blob: bytes, lba: int, length: int) -> "list[dict]":
    """Decode one directory extent straight out of an image blob."""
    out = []
    base = lba * SECTOR
    offset = 0
    while offset < length:
        record_length = blob[base + offset]
        if record_length == 0:
            offset += SECTOR - (offset % SECTOR)        # skip block-edge padding
            continue
        record = blob[base + offset:base + offset + record_length]
        identifier_length = record[32]
        out.append({
            "offset": offset,
            "length": record_length,
            "identifier": record[33:33 + identifier_length],
            "extent": _read_both_endian_32(record, 2),
            "data_length": _read_both_endian_32(record, 10),
            "is_dir": bool(record[25] & _DIRECTORY_FLAG),
        })
        offset += record_length
    return out


def pvd_fields(blob: bytes) -> "dict":
    base = _PVD_LBA * SECTOR
    return {
        "magic": bytes(blob[base + 1:base + 6]),
        "type": blob[base],
        "version": blob[base + 6],
        "volume_id": blob[base + 40:base + 72].decode("ascii").rstrip(" "),
        "volume_blocks": _read_both_endian_32(blob, base + 80),
        "block_size": (
            struct.unpack_from("<H", blob, base + 128)[0],
            struct.unpack_from(">H", blob, base + 130)[0],
        ),
        "root_extent": _read_both_endian_32(blob, base + 156 + 2),
        "root_length": _read_both_endian_32(blob, base + 156 + 10),
    }


def _module_errors(module) -> "tuple":
    """Exception classes a module declares for itself.

    The frozen interface pins that the writer and verifier *raise* on a
    violation but never names the class, so it is discovered rather than
    guessed. ``ValueError`` and ``OSError`` are always accepted alongside;
    ``AttributeError`` / ``TypeError`` / ``struct.error`` deliberately are not,
    so a crash cannot masquerade as a refusal.
    """
    declared = tuple(
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, BaseException)
        and getattr(value, "__module__", "") == module.__name__
    )
    return declared + (ValueError, OSError)


REFUSALS = _module_errors(isowriter)
VIOLATIONS = _module_errors(isoverify) + (AssertionError,)


def declared_ranges(report: "dict") -> "list[tuple[int, int, str]]":
    """Normalise ``report["declared_ranges"]`` whether it holds objects or dicts.

    The report survives a JSON round trip in real use, so a test that only
    understood one of the two shapes would be brittle for no benefit.
    """
    out = []
    for item in report["declared_ranges"]:
        if isinstance(item, dict):
            out.append((int(item["start"]), int(item["length"]), str(item.get("reason", ""))))
        else:
            out.append((int(item.start), int(item.length), str(item.reason)))
    return out


def changed_spans(before: bytes, after: bytes) -> "list[tuple[int, int]]":
    """Coalesce differing positions into (offset, length) spans."""
    assert len(before) == len(after), "size changed; spans are meaningless"
    spans = []
    start = None
    for index in range(len(before)):
        if before[index] != after[index]:
            if start is None:
                start = index
        elif start is not None:
            spans.append((start, index - start))
            start = None
    if start is not None:
        spans.append((start, len(before) - start))
    return spans


# ---------------------------------------------------------------------------
# Shared fixture content.
# ---------------------------------------------------------------------------

BOOT_ELF = b"\x7fELF\x01\x01\x01\x00" + bytes(range(256)) * 3
SYSTEM_CNF = (
    b"BOOT2 = cdrom0:\\SLUS_217.70;1\r\n"
    b"VER = 1.00\r\n"
    b"VMODE = NTSC\r\n"
)

TREE = {
    "SYSTEM.CNF": SYSTEM_CNF,
    "SLUS_217.70": BOOT_ELF,
    "DATA": {
        "FOO.BIN": bytes(range(256)) * 12,          # 3072 bytes: spans two blocks
        "BAR.BIN": b"bar" * 100,
        "SUB": {
            "DEEP.BIN": b"deep payload" * 40,
        },
    },
}


class _IsoTestCase(unittest.TestCase):
    """Base class giving every test a private temp directory."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ps2iso-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def written(self, blob: bytes, name: str = "image.iso") -> Path:
        path = self.work / name
        path.write_bytes(blob)
        return path

    def image(self, tree: "dict" = None, name: str = "image.iso", **kwargs) -> Path:
        return self.written(build_iso(TREE if tree is None else tree, **kwargs), name)


# ---------------------------------------------------------------------------
# The fixture has to be a valid fixture before anything built on it means
# something. These checks use nothing but ``struct``.
# ---------------------------------------------------------------------------

class SyntheticImageIsWellFormedTests(_IsoTestCase):
    def test_the_primary_volume_descriptor_is_conforming(self) -> None:
        blob = build_iso(TREE, volume_id="TEST_VOL")
        fields = pvd_fields(blob)
        self.assertEqual(fields["magic"], b"CD001")
        self.assertEqual(fields["type"], 1)
        self.assertEqual(fields["version"], 1)
        self.assertEqual(fields["volume_id"], "TEST_VOL")
        self.assertEqual(fields["block_size"], (SECTOR, SECTOR))
        self.assertEqual(blob[_TERMINATOR_LBA * SECTOR], 0xFF)
        self.assertEqual(
            blob[_TERMINATOR_LBA * SECTOR + 1:_TERMINATOR_LBA * SECTOR + 6], b"CD001"
        )

    def test_every_both_endian_field_agrees_with_itself(self) -> None:
        """A both-endian field whose halves differ is the shape of a bad write.

        The suite later requires the *writer* to keep this property; asserting
        it of the fixture first means a failure there can only be the writer.
        """
        blob = build_iso(TREE)
        fields = pvd_fields(blob)
        for name in ("volume_blocks", "root_extent", "root_length"):
            little, big = fields[name]
            self.assertEqual(little, big, "PVD {} halves disagree".format(name))

        pending = [(fields["root_extent"][0], fields["root_length"][0])]
        seen = set()
        while pending:
            lba, length = pending.pop()
            if lba in seen:
                continue
            seen.add(lba)
            for record in decode_records(blob, lba, length):
                self.assertEqual(record["extent"][0], record["extent"][1])
                self.assertEqual(record["data_length"][0], record["data_length"][1])
                if record["is_dir"] and record["identifier"] not in (b"\x00", b"\x01"):
                    pending.append((record["extent"][0], record["data_length"][0]))
        self.assertGreater(len(seen), 1, "the walk never reached a subdirectory")

    def test_declared_extents_hold_the_bytes_that_were_requested(self) -> None:
        blob = build_iso(TREE)
        fields = pvd_fields(blob)
        found = {}

        def walk(lba: int, length: int, prefix: str) -> None:
            for record in decode_records(blob, lba, length):
                if record["identifier"] in (b"\x00", b"\x01"):
                    continue
                path = _visible_path(prefix, record["identifier"])
                if record["is_dir"]:
                    walk(record["extent"][0], record["data_length"][0], path)
                else:
                    start = record["extent"][0] * SECTOR
                    found[path] = blob[start:start + record["data_length"][0]]

        walk(fields["root_extent"][0], fields["root_length"][0], "/")
        self.assertEqual(found, expected_files(TREE))

    def test_slack_lands_past_the_declared_volume_and_is_measurable(self) -> None:
        """The Deluxe rebuild's 18,432 trailing bytes, in miniature."""
        for slack in (0, 512, 18432):
            with self.subTest(slack=slack):
                blob = build_iso(TREE, slack=slack)
                volume_blocks = pvd_fields(blob)["volume_blocks"][0]
                self.assertEqual(len(blob) - volume_blocks * SECTOR, slack)

    def test_raw_cd_wrapping_keeps_user_data_at_offset_24(self) -> None:
        plain = build_iso(TREE)
        raw = build_iso(TREE, raw_cd=True)
        self.assertEqual(len(raw) % RAW_SECTOR, 0)
        self.assertEqual(len(raw) // RAW_SECTOR, len(plain) // SECTOR)
        for lba in (0, _PVD_LBA, _FIRST_EXTENT_LBA):
            base = lba * RAW_SECTOR
            self.assertEqual(raw[base:base + 12], b"\x00" + b"\xff" * 10 + b"\x00")
            self.assertEqual(
                raw[base + RAW_DATA_OFFSET:base + RAW_DATA_OFFSET + SECTOR],
                plain[lba * SECTOR:(lba + 1) * SECTOR],
            )

    def test_the_builder_is_deterministic(self) -> None:
        """Two builds of one tree must be byte-identical, or diffs mean nothing."""
        self.assertEqual(build_iso(TREE), build_iso(TREE))


# ---------------------------------------------------------------------------
# Reader.
# ---------------------------------------------------------------------------

class ReaderRoundTripTests(_IsoTestCase):
    def test_build_open_iterate_find_read_returns_exactly_what_went_in(self) -> None:
        path = self.image(volume_id="ROUND_TRIP", slack=4096)
        image = iso.open_image(path)

        self.assertEqual(image.sector_size, SECTOR)
        self.assertEqual(image.data_offset, 0)
        self.assertEqual(image.block_size, SECTOR)
        self.assertEqual(image.volume_id, "ROUND_TRIP")
        self.assertEqual(image.file_size, path.stat().st_size)
        self.assertEqual(image.slack_bytes, 4096)
        self.assertEqual(
            image.file_size - image.volume_blocks * image.sector_size, image.slack_bytes
        )

        entries = list(iso.iter_entries(image))
        paths = {entry.path for entry in entries}
        self.assertEqual(paths - {"/"}, expected_paths(TREE))
        self.assertNotIn("/.", paths)
        self.assertFalse([p for p in paths if p.endswith("/..") or p.endswith("/.")])

        by_path = {entry.path: entry for entry in entries}
        self.assertTrue(by_path["/DATA"].is_dir)
        self.assertTrue(by_path["/DATA/SUB"].is_dir)
        self.assertFalse(by_path["/DATA/FOO.BIN"].is_dir)

        for path_text, expected in (
            ("/SYSTEM.CNF", SYSTEM_CNF),
            ("/SLUS_217.70", BOOT_ELF),
            ("/DATA/FOO.BIN", TREE["DATA"]["FOO.BIN"]),
            ("/DATA/BAR.BIN", TREE["DATA"]["BAR.BIN"]),
            ("/DATA/SUB/DEEP.BIN", TREE["DATA"]["SUB"]["DEEP.BIN"]),
        ):
            entry = iso.find(image, path_text)
            self.assertIsNotNone(entry, "{} was not found".format(path_text))
            self.assertEqual(entry.length, len(expected))
            self.assertEqual(iso.read_file(image, entry), expected)
            self.assertEqual(
                iso.sha256_of(image, entry), hashlib.sha256(expected).hexdigest()
            )

    def test_nested_directories_resolve_to_their_own_extents(self) -> None:
        """A deep tree, so a reader that only walks the root fails loudly."""
        tree = {"A": {"B": {"C": {"D": {"LEAF.BIN": b"leaf" * 64}}}}}
        image = iso.open_image(self.image(tree))
        entry = iso.find(image, "/A/B/C/D/LEAF.BIN")
        self.assertIsNotNone(entry)
        self.assertEqual(iso.read_file(image, entry), b"leaf" * 64)
        self.assertEqual(
            {e.path for e in iso.iter_entries(image)} - {"/"}, expected_paths(tree)
        )

    def test_find_is_case_insensitive_and_the_version_suffix_is_optional(self) -> None:
        image = iso.open_image(self.image())
        canonical = iso.find(image, "/DATA/FOO.BIN")
        self.assertIsNotNone(canonical)
        for spelling in (
            "/DATA/FOO.BIN",
            "/data/foo.bin",
            "/DaTa/FoO.BiN",
            "/DATA/FOO.BIN;1",
            "/data/foo.bin;1",
        ):
            with self.subTest(spelling=spelling):
                entry = iso.find(image, spelling)
                self.assertIsNotNone(entry, "{} did not resolve".format(spelling))
                self.assertEqual(entry.path, canonical.path)
                self.assertEqual(entry.lba, canonical.lba)
                self.assertEqual(entry.length, canonical.length)

    def test_an_image_stored_without_version_suffixes_still_resolves(self) -> None:
        """Rebuild tools drop ``;1``; a query carrying one must still match.

        This is the mirror of the previous test and the reason ``;1`` handling
        has to be a normalisation on both sides rather than a suffix strip on
        one of them.
        """
        image = iso.open_image(self.image(version_suffix=False))
        for spelling in ("/DATA/FOO.BIN", "/DATA/FOO.BIN;1", "/data/foo.bin;1"):
            with self.subTest(spelling=spelling):
                entry = iso.find(image, spelling)
                self.assertIsNotNone(entry, "{} did not resolve".format(spelling))
                self.assertEqual(iso.read_file(image, entry), TREE["DATA"]["FOO.BIN"])
        self.assertEqual(iso.find(image, "/DATA/FOO.BIN").raw_name, "FOO.BIN")

    def test_raw_name_is_what_the_disc_actually_stores(self) -> None:
        image = iso.open_image(self.image())
        entry = iso.find(image, "/DATA/FOO.BIN")
        self.assertEqual(entry.raw_name, "FOO.BIN;1")
        self.assertEqual(entry.path, "/DATA/FOO.BIN")

    def test_absent_paths_return_none_rather_than_raising(self) -> None:
        image = iso.open_image(self.image())
        for missing in ("/NOPE.BIN", "/DATA/NOPE.BIN", "/DATA/SUB/SUB/NOPE.BIN", "/DAT"):
            with self.subTest(path=missing):
                self.assertIsNone(iso.find(image, missing))

    def test_iteration_is_deterministic(self) -> None:
        image = iso.open_image(self.image())
        first = [(e.path, e.lba, e.length, e.is_dir) for e in iso.iter_entries(image)]
        second = [(e.path, e.lba, e.length, e.is_dir) for e in iso.iter_entries(image)]
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(p for p, _l, _n, _d in first)))

    def test_an_empty_volume_id_is_accepted(self) -> None:
        """Retail Madden 09 ships a blank volume id; it means nothing."""
        image = iso.open_image(self.image(volume_id=""))
        self.assertEqual(image.volume_id, "")
        self.assertEqual(iso.read_file(image, iso.find(image, "/SYSTEM.CNF")), SYSTEM_CNF)

    def test_a_file_that_is_not_a_disc_image_is_refused(self) -> None:
        """Tolerating volume ids and slack must not become tolerating anything."""
        for label, blob in (
            ("empty", b""),
            ("short", b"not an iso"),
            ("right size, no CD001", bytes(24 * SECTOR)),
        ):
            with self.subTest(image=label):
                path = self.written(blob, label.replace(" ", "_") + ".iso")
                with self.assertRaises(iso.Iso9660Error):
                    iso.open_image(path)


class DirectoryRecordAddressingTests(_IsoTestCase):
    """``parent_lba`` / ``record_offset`` are the writer's aiming point.

    The writer rewrites eight bytes at ``parent_lba * sector_size +
    data_offset + record_offset + 10``. If either number is off by one the edit
    lands in a neighbouring record's flags or identifier and the disc is
    quietly corrupt -- a class of damage that only shows up on hardware. So the
    contract is checked by going back to the image and decoding the record at
    the advertised address again, from raw bytes, without the reader's help.
    """

    def test_every_entry_points_at_its_own_directory_record(self) -> None:
        blob = build_iso(TREE)
        path = self.written(blob)
        image = iso.open_image(path)
        checked = 0
        for entry in iso.iter_entries(image):
            if entry.path == "/":
                continue
            with self.subTest(entry=entry.path):
                base = entry.parent_lba * image.sector_size + image.data_offset
                record_length = blob[base + entry.record_offset]
                self.assertGreaterEqual(record_length, 34, "record length is impossible")
                record = blob[
                    base + entry.record_offset:base + entry.record_offset + record_length
                ]
                identifier = record[33:33 + record[32]]
                self.assertEqual(identifier.decode("ascii"), entry.raw_name)
                self.assertEqual(_read_both_endian_32(record, 2), (entry.lba, entry.lba))
                self.assertEqual(
                    _read_both_endian_32(record, 10), (entry.length, entry.length)
                )
                self.assertEqual(bool(record[25] & _DIRECTORY_FLAG), entry.is_dir)
                checked += 1
        self.assertEqual(checked, len(expected_paths(TREE)))

    def test_record_offset_lands_inside_the_parent_extent(self) -> None:
        image = iso.open_image(self.image())
        by_path = {entry.path: entry for entry in iso.iter_entries(image)}
        for entry in by_path.values():
            if entry.path == "/":
                continue
            parent_path = entry.path.rsplit("/", 1)[0] or "/"
            parent_length = (
                image.root_length if parent_path == "/" else by_path[parent_path].length
            )
            parent_lba = image.root_lba if parent_path == "/" else by_path[parent_path].lba
            with self.subTest(entry=entry.path):
                self.assertEqual(entry.parent_lba, parent_lba)
                self.assertGreaterEqual(entry.record_offset, 0)
                self.assertLess(entry.record_offset, parent_length)

    def test_root_children_are_parented_to_the_root_lba(self) -> None:
        image = iso.open_image(self.image())
        for name in ("/SYSTEM.CNF", "/SLUS_217.70", "/DATA"):
            self.assertEqual(iso.find(image, name).parent_lba, image.root_lba)

    def test_the_first_two_records_of_an_extent_are_dot_and_dotdot(self) -> None:
        """No entry may be handed back pointing at ``.`` or ``..``.

        Those two records exist in every extent and are the easiest thing for a
        naive walker to hand back as a real file; the writer would then rewrite
        a directory's own self-record length.
        """
        image = iso.open_image(self.image())
        offsets = {
            entry.record_offset
            for entry in iso.iter_entries(image)
            if entry.parent_lba == image.root_lba
        }
        self.assertNotIn(0, offsets, "an entry pointed at the '.' record")
        self.assertNotIn(34, offsets, "an entry pointed at the '..' record")


class SectorGeometryTests(_IsoTestCase):
    def test_2048_byte_sectors_are_detected(self) -> None:
        image = iso.open_image(self.image())
        self.assertEqual(image.sector_size, SECTOR)
        self.assertEqual(image.data_offset, 0)
        self.assertEqual(image.block_size, SECTOR)

    def test_a_raw_2352_byte_cd_image_is_read_at_data_offset_24(self) -> None:
        """PS2 CD titles are 2352-byte raw sectors; silence is the only failure.

        The contract allowed either answer -- support raw CD with
        ``data_offset = 24``, or refuse it explicitly -- but forbade the third
        option, silently misparsing it: the PVD magic sits 24 bytes into a raw
        sector, so a reader that assumed 2048 would decode a garbage volume
        descriptor and carry on with nonsense addresses.

        The reader **supports** it, so that is what is pinned here. If a later
        change reduces this to a refusal, that is a deliberate scope decision
        and this test is the place it has to be argued.
        """
        image = iso.open_image(self.image(raw_cd=True, name="rawcd.iso"))
        self.assertEqual(image.sector_size, RAW_SECTOR)
        self.assertEqual(image.data_offset, RAW_DATA_OFFSET)
        self.assertEqual(image.block_size, SECTOR, "the logical block stays 2048")
        self.assertEqual(
            {e.path for e in iso.iter_entries(image)} - {"/"}, expected_paths(TREE)
        )
        for path_text, payload in expected_files(TREE).items():
            with self.subTest(path=path_text):
                self.assertEqual(
                    iso.read_file(image, iso.find(image, path_text)), payload
                )

    def test_raw_and_2048_images_of_one_tree_read_identically(self) -> None:
        """The container may vary; the contents may not.

        Same filesystem, two sector geometries, and everything the reader
        reports about the *contents* has to match -- paths, LBAs, lengths and
        bytes. Only ``sector_size`` / ``data_offset`` / ``file_size`` differ.
        """
        plain = iso.open_image(self.image(name="plain.iso"))
        raw = iso.open_image(self.image(raw_cd=True, name="raw.iso"))
        self.assertEqual(plain.volume_blocks, raw.volume_blocks)
        self.assertEqual(plain.root_lba, raw.root_lba)
        self.assertEqual(plain.slack_bytes, raw.slack_bytes)
        def shape(image):
            return [
                (e.path, e.raw_name, e.lba, e.length, e.is_dir,
                 e.parent_lba, e.record_offset)
                for e in iso.iter_entries(image)
            ]

        self.assertEqual(shape(plain), shape(raw))


# ---------------------------------------------------------------------------
# Writer.
# ---------------------------------------------------------------------------

class WriterFixedAllocationTests(_IsoTestCase):
    def _replace(self, replacements, source_kwargs=None, name="out.iso"):
        source = self.image(name="src.iso", **(source_kwargs or {}))
        destination = self.work / name
        report = isowriter.replace_files(source, destination, replacements)
        return source, destination, report

    def test_a_same_size_replacement_changes_only_the_payload_and_keeps_slack(self) -> None:
        """The Deluxe image's 18,432 trailing bytes must come out untouched."""
        original = TREE["DATA"]["FOO.BIN"]
        new = bytes(255 - byte for byte in original)
        self.assertEqual(len(new), len(original))

        source, destination, report = self._replace(
            {"/DATA/FOO.BIN": new}, {"slack": 18432}
        )
        before = source.read_bytes()
        after = destination.read_bytes()
        self.assertEqual(len(after), len(before), "file size must not change")
        self.assertEqual(after[len(before) - 18432:], before[len(before) - 18432:])

        image = iso.open_image(destination)
        self.assertEqual(image.slack_bytes, 18432)
        self.assertEqual(image.volume_blocks, iso.open_image(source).volume_blocks)
        entry = iso.find(image, "/DATA/FOO.BIN")
        self.assertEqual(entry.length, len(new))
        self.assertEqual(iso.read_file(image, entry), new)

        # Everything else on the disc is byte-identical.
        for other, expected in (
            ("/SYSTEM.CNF", SYSTEM_CNF),
            ("/SLUS_217.70", BOOT_ELF),
            ("/DATA/BAR.BIN", TREE["DATA"]["BAR.BIN"]),
            ("/DATA/SUB/DEEP.BIN", TREE["DATA"]["SUB"]["DEEP.BIN"]),
        ):
            self.assertEqual(iso.read_file(image, iso.find(image, other)), expected)

        self.assertEqual(isoverify.verify_replacement(source, destination, report).get(
            "result", "PASS"), "PASS")

    def test_a_shrinking_replacement_zero_fills_the_tail_and_rewrites_both_lengths(self) -> None:
        """A stale tail is a real bug: the engine reads the declared length.

        The declared length shrinks, so the bytes between the new end and the
        old end are no longer reachable through the filesystem -- but they are
        still on the disc, and anything that scans extents raw would find the
        previous game's data there. They must be zeroed, and *both* halves of
        the both-endian length field must be rewritten: an engine reading the
        big-endian copy would otherwise still see the old size.
        """
        original = TREE["DATA"]["FOO.BIN"]
        new = b"shrunk" * 10
        self.assertLess(len(new), len(original))

        source = self.image(name="src.iso")
        before_image = iso.open_image(source)
        entry = iso.find(before_image, "/DATA/FOO.BIN")
        extent_start = entry.lba * before_image.sector_size + before_image.data_offset
        record_start = (
            entry.parent_lba * before_image.sector_size
            + before_image.data_offset
            + entry.record_offset
        )

        destination = self.work / "shrunk.iso"
        report = isowriter.replace_files(source, destination, {"/DATA/FOO.BIN": new})
        after = destination.read_bytes()

        self.assertEqual(after[extent_start:extent_start + len(new)], new)
        self.assertEqual(
            after[extent_start + len(new):extent_start + entry.length],
            bytes(entry.length - len(new)),
            "the tail of the old extent was left stale",
        )

        little, big = _read_both_endian_32(after, record_start + 10)
        self.assertEqual(little, len(new), "little-endian declared length not updated")
        self.assertEqual(big, len(new), "big-endian declared length not updated")
        self.assertEqual(little, big, "both-endian halves disagree")

        reopened = iso.open_image(destination)
        self.assertEqual(iso.find(reopened, "/DATA/FOO.BIN").length, len(new))
        self.assertEqual(iso.read_file(reopened, iso.find(reopened, "/DATA/FOO.BIN")), new)
        isoverify.verify_replacement(source, destination, report)

    def test_declared_ranges_bound_every_byte_that_actually_changed(self) -> None:
        """The report is the contract; an undeclared byte is an unprovable edit."""
        source = self.image(name="src.iso")
        image = iso.open_image(source)
        entry = iso.find(image, "/DATA/FOO.BIN")
        destination = self.work / "declared.iso"
        report = isowriter.replace_files(
            source, destination, {"/DATA/FOO.BIN": b"z" * 100}
        )

        ranges = declared_ranges(report)
        self.assertTrue(ranges, "the writer declared nothing")
        reasons = {reason for _s, _l, reason in ranges}
        self.assertIn("extent:/DATA/FOO.BIN", reasons)
        self.assertIn("dirrec_length:/DATA/FOO.BIN", reasons)

        expected_record = (
            entry.parent_lba * image.sector_size + image.data_offset + entry.record_offset + 10
        )
        for start, length, reason in ranges:
            if reason.startswith("dirrec_length:"):
                self.assertEqual((start, length), (expected_record, 8))
            if reason.startswith("extent:"):
                self.assertEqual(
                    start, entry.lba * image.sector_size + image.data_offset
                )
                self.assertLessEqual(length, entry.length)

        before = source.read_bytes()
        after = destination.read_bytes()
        for start, length in changed_spans(before, after):
            covered = any(
                start >= r_start and start + length <= r_start + r_length
                for r_start, r_length, _reason in ranges
            )
            self.assertTrue(
                covered, "changed 0x{:x}+{} is covered by no declared range".format(
                    start, length
                )
            )
        # A writer cannot buy coverage by declaring the whole disc.
        self.assertLessEqual(
            sum(length for _s, length, _r in ranges), entry.length + 8
        )

    def test_several_files_replaced_in_one_pass(self) -> None:
        source = self.image(name="src.iso")
        destination = self.work / "multi.iso"
        wanted = {
            "/DATA/FOO.BIN": b"F" * 500,
            "/DATA/BAR.BIN": b"B" * 12,
            "/DATA/SUB/DEEP.BIN": b"D" * 3,
        }
        report = isowriter.replace_files(source, destination, wanted)
        image = iso.open_image(destination)
        for path_text, payload in wanted.items():
            entry = iso.find(image, path_text)
            self.assertEqual(entry.length, len(payload))
            self.assertEqual(iso.read_file(image, entry), payload)
        self.assertEqual(iso.read_file(image, iso.find(image, "/SYSTEM.CNF")), SYSTEM_CNF)
        isoverify.verify_replacement(source, destination, report)

    def test_a_replacement_supplied_as_a_path_is_read_from_disk(self) -> None:
        payload = b"from a file on disk" * 7
        blob = self.work / "payload.bin"
        blob.write_bytes(payload)
        source = self.image(name="src.iso")
        destination = self.work / "frompath.iso"
        isowriter.replace_files(source, destination, {"/DATA/FOO.BIN": blob})
        image = iso.open_image(destination)
        self.assertEqual(
            iso.read_file(image, iso.find(image, "/DATA/FOO.BIN")), payload
        )

    def test_the_source_image_is_never_modified(self) -> None:
        source = self.image(name="src.iso")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        destination = self.work / "copy.iso"
        isowriter.replace_files(source, destination, {"/DATA/FOO.BIN": b"x" * 64})
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_a_report_that_has_been_through_json_still_verifies(self) -> None:
        """The report crosses a process boundary in real use.

        The writer runs, its report is written to disk as JSON, and the
        verifier is invoked separately against the two images and that file --
        which is the whole point of the verifier being independent. So the
        declared ranges arrive as plain dicts rather than ``ByteRange``
        objects, and verification must be identical either way.
        """
        source = self.image(name="src.iso")
        destination = self.work / "json.iso"
        report = isowriter.replace_files(
            source, destination, {"/DATA/FOO.BIN": b"json round trip" * 8}
        )
        flattened = json.loads(json.dumps(report, default=lambda item: {
            "start": item.start, "length": item.length, "reason": item.reason,
        }))
        self.assertTrue(
            all(isinstance(rng, dict) for rng in flattened["declared_ranges"])
        )
        isoverify.verify_replacement(source, destination, flattened)
        self.assertEqual(
            declared_ranges(flattened), declared_ranges(report),
            "the JSON form must describe the same ranges",
        )


class WriterGrowthTests(_IsoTestCase):
    """``allow_growth`` relocates a grown file, and changes nothing else.

    The default is the bounded writer these tests do not touch: the first case
    below is the one that says so, by writing the same replacement with and
    without the flag and comparing the two images byte for byte.
    """

    def grow(self, replacements, *, slack=18432, name="grown.iso", allow_growth=True):
        source = self.image(name="src.iso", slack=slack)
        destination = self.work / name
        report = isowriter.replace_files(source, destination, replacements,
                                         allow_growth=allow_growth)
        return source, destination, report

    def test_the_flag_changes_nothing_when_the_replacement_fits(self) -> None:
        source = self.image(name="src.iso", slack=18432)
        small = b"fits"
        bounded = isowriter.replace_files(source, self.work / "a.iso",
                                          {"/DATA/FOO.BIN": small})
        flagged = isowriter.replace_files(source, self.work / "b.iso",
                                          {"/DATA/FOO.BIN": small}, allow_growth=True)
        self.assertEqual((self.work / "a.iso").read_bytes(),
                         (self.work / "b.iso").read_bytes())
        self.assertNotIn("growth", flagged)
        self.assertEqual({k: v for k, v in bounded.items() if k != "destination"},
                         {k: v for k, v in flagged.items() if k != "destination"})

    def test_a_grown_file_is_appended_and_its_record_repointed(self) -> None:
        content = b"G" * 7000
        source, destination, report = self.grow({"/DATA/BAR.BIN": content})
        growth = report["growth"]
        sectors = -(-len(content) // 2048)
        self.assertEqual(growth["appended_sectors"], sectors)
        self.assertEqual(destination.stat().st_size,
                         source.stat().st_size + sectors * 2048)
        self.assertEqual(growth["slack_bytes"], 0)
        self.assertEqual(growth["previous_slack_bytes"], 18432)

        image = iso.open_image(destination)
        entry = iso.find(image, "/DATA/BAR.BIN")
        self.assertEqual(entry.length, len(content))
        self.assertEqual(entry.lba, growth["append_lba"])
        blob = destination.read_bytes()
        start = entry.lba * 2048
        self.assertEqual(blob[start:start + len(content)], content)
        self.assertEqual(blob[start + len(content):start + sectors * 2048],
                         bytes(sectors * 2048 - len(content)))

    def test_the_extent_it_left_is_zeroed_and_the_source_untouched(self) -> None:
        before = None
        content = b"G" * 7000
        source, destination, report = self.grow({"/DATA/BAR.BIN": content})
        before = source.read_bytes()
        moved = report["replacements"][0]
        after = destination.read_bytes()
        self.assertTrue(moved["relocated"])
        self.assertEqual(
            after[moved["extent_offset"]:
                  moved["extent_offset"] + moved["previous_length"]],
            bytes(moved["previous_length"]))
        self.assertEqual(before, self.image(name="again.iso", slack=18432).read_bytes())

    def test_no_other_file_moves_and_the_slack_bytes_survive(self) -> None:
        source, destination, _report = self.grow({"/DATA/BAR.BIN": b"G" * 7000})
        before, after = iso.open_image(source), iso.open_image(destination)
        by_path = {entry.path: entry for entry in iso.iter_entries(after)}
        for entry in iso.iter_entries(before):
            if entry.path == "/DATA/BAR.BIN":
                continue
            self.assertEqual(by_path[entry.path].lba, entry.lba, entry.path)
            self.assertEqual(by_path[entry.path].length, entry.length, entry.path)
        original = source.read_bytes()
        grown = destination.read_bytes()
        self.assertEqual(grown[len(original) - 18432:len(original)],
                         original[len(original) - 18432:])

    def test_the_independent_verifier_passes_a_grown_image(self) -> None:
        content = b"G" * 9000
        source, destination, report = self.grow({"/DATA/BAR.BIN": content})
        as_json = json.loads(json.dumps(isowriter.report_to_json(report)))
        verdict = isoverify.verify_replacement(source, destination, as_json,
                                               expected={"/DATA/BAR.BIN": content})
        self.assertEqual(verdict["result"], "PASS")
        self.assertTrue(verdict["grew"])
        self.assertEqual(verdict["destination_file_size"], destination.stat().st_size)

    def test_two_files_can_grow_at_once_without_overlapping(self) -> None:
        first, second = b"1" * 5000, b"2" * 3000
        source, destination, report = self.grow(
            {"/DATA/BAR.BIN": first, "/DATA/SUB/DEEP.BIN": second})
        growth = report["growth"]
        self.assertEqual(sorted(growth["relocated"]),
                         ["/DATA/BAR.BIN", "/DATA/SUB/DEEP.BIN"])
        image = iso.open_image(destination)
        blob = destination.read_bytes()
        for path, content in (("/DATA/BAR.BIN", first), ("/DATA/SUB/DEEP.BIN", second)):
            entry = iso.find(image, path)
            start = entry.lba * 2048
            self.assertEqual(blob[start:start + len(content)], content, path)
        as_json = json.loads(json.dumps(isowriter.report_to_json(report)))
        self.assertEqual(
            isoverify.verify_replacement(source, destination, as_json)["result"], "PASS")

    def test_growing_without_the_flag_is_refused_naming_the_flag(self) -> None:
        source = self.image(name="src.iso")
        with self.assertRaises(isowriter.IsoWriteError) as caught:
            isowriter.replace_files(source, self.work / "no.iso",
                                    {"/DATA/BAR.BIN": b"x" * 9000})
        self.assertIn("allow_growth", str(caught.exception))
        self.assertFalse((self.work / "no.iso").exists())

    def test_growing_a_directory_is_refused(self) -> None:
        source = self.image(name="src.iso")
        with self.assertRaises(isowriter.IsoWriteError):
            isowriter.replace_files(source, self.work / "no.iso",
                                    {"/DATA": b"x" * 9000}, allow_growth=True)
        self.assertFalse((self.work / "no.iso").exists())

    def test_a_dry_run_prices_the_growth_and_writes_nothing(self) -> None:
        source = self.image(name="src.iso")
        plan = isowriter.plan_report(source, {"/DATA/BAR.BIN": b"x" * 7000},
                                     allow_growth=True)
        self.assertEqual(plan["growth"]["appended_sectors"], 4)
        self.assertEqual(sorted(rng.reason for rng in plan["declared_ranges"]),
                         ["dirrec_extent:/DATA/BAR.BIN", "dirrec_length:/DATA/BAR.BIN",
                          "extent:/DATA/BAR.BIN", "newextent:/DATA/BAR.BIN",
                          "pvd_volume_space"])
        self.assertEqual(sorted(path.name for path in self.work.iterdir()), ["src.iso"])

    def test_a_verifier_fed_a_grown_image_as_bounded_fails(self) -> None:
        content = b"G" * 7000
        source, destination, report = self.grow({"/DATA/BAR.BIN": content})
        as_json = json.loads(json.dumps(isowriter.report_to_json(report)))
        stripped = {key: value for key, value in as_json.items() if key != "growth"}
        with self.assertRaises(isoverify.IsoVerifyError):
            isoverify.verify_replacement(source, destination, stripped)


class WriterRefusalTests(_IsoTestCase):
    """Every refusal also has to leave no half-written destination behind."""

    def _refused(self, source, destination, replacements, must_not_exist=True):
        with self.assertRaises(REFUSALS) as caught:
            isowriter.replace_files(source, destination, replacements)
        self.assertTrue(str(caught.exception).strip(), "a refusal must say why")
        if must_not_exist:
            self.assertFalse(
                Path(destination).exists(),
                "a refused write left a destination behind",
            )
        return caught.exception

    def test_an_oversize_replacement_is_refused_and_writes_nothing(self) -> None:
        """v1 does fixed allocation only. Growth means rebuilding, which is out.

        The refusal has to happen before any bytes are copied, otherwise a
        user is left holding a truncated image that looks like a real one.
        """
        source = self.image(name="src.iso")
        entry = iso.find(iso.open_image(source), "/DATA/FOO.BIN")
        destination = self.work / "oversize.iso"
        self._refused(
            source, destination, {"/DATA/FOO.BIN": b"x" * (entry.length + 1)}
        )

    def test_an_existing_destination_is_refused(self) -> None:
        source = self.image(name="src.iso")
        destination = self.work / "already.iso"
        destination.write_bytes(b"do not clobber me")
        with self.assertRaises(REFUSALS):
            isowriter.replace_files(source, destination, {"/DATA/FOO.BIN": b"x"})
        self.assertEqual(destination.read_bytes(), b"do not clobber me")

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlinks")
    def test_a_symlinked_source_is_refused(self) -> None:
        real = self.image(name="real.iso")
        link = self.work / "link.iso"
        link.symlink_to(real)
        self._refused(link, self.work / "out.iso", {"/DATA/FOO.BIN": b"x"})

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlinks")
    def test_a_symlinked_destination_is_refused(self) -> None:
        """A symlinked destination writes through to whatever it points at."""
        source = self.image(name="src.iso")
        victim = self.work / "victim.bin"
        victim.write_bytes(b"innocent bystander")
        link = self.work / "dest.iso"
        link.symlink_to(victim)
        with self.assertRaises(REFUSALS):
            isowriter.replace_files(source, link, {"/DATA/FOO.BIN": b"x"})
        self.assertEqual(victim.read_bytes(), b"innocent bystander")

    def test_replacing_a_directory_is_refused(self) -> None:
        source = self.image(name="src.iso")
        self._refused(source, self.work / "dir.iso", {"/DATA": b"x"})

    def test_replacing_a_path_that_does_not_exist_is_refused(self) -> None:
        source = self.image(name="src.iso")
        self._refused(source, self.work / "missing.iso", {"/DATA/NOPE.BIN": b"x"})

    def test_an_extent_outside_the_declared_volume_is_refused(self) -> None:
        """A record can claim an LBA past the end of the disc; writing there
        would either extend the file or land in the slack.

        The bogus LBA is poked in through the entry's own ``parent_lba`` /
        ``record_offset``, so this doubles as proof those two numbers address a
        real record: if they were wrong, the poke would not change the entry.
        """
        blob = bytearray(build_iso(TREE))
        probe = self.written(bytes(blob), "probe.iso")
        image = iso.open_image(probe)
        entry = iso.find(image, "/DATA/FOO.BIN")
        record = entry.parent_lba * image.sector_size + image.data_offset + entry.record_offset
        blob[record + 2:record + 10] = _both_endian_32(image.volume_blocks + 4096)
        source = self.written(bytes(blob), "outofbounds.iso")

        reread = iso.find(iso.open_image(source), "/DATA/FOO.BIN")
        self.assertEqual(
            reread.lba, image.volume_blocks + 4096, "the poke did not take effect"
        )
        self._refused(source, self.work / "oob.iso", {"/DATA/FOO.BIN": b"x" * 8})

    def test_a_zero_length_entry_is_refused(self) -> None:
        """Nothing fits in nothing; writing would run past the record's claim."""
        source = self.image({"EMPTY.BIN": b"", "KEEP.BIN": b"keep"}, name="src.iso")
        self.assertEqual(iso.find(iso.open_image(source), "/EMPTY.BIN").length, 0)
        self._refused(source, self.work / "empty.iso", {"/EMPTY.BIN": b"x"})

    def test_a_raw_cd_source_is_refused_even_though_it_reads_fine(self) -> None:
        """Reading raw CD is supported; writing it is not, and the split is on purpose.

        A raw 2352-byte sector interleaves the 2048 user bytes with EDC/ECC
        that this writer does not recompute, so a patched sector would carry a
        correct payload behind a stale checksum -- readable by an emulator,
        rejected by real hardware. Refusing is the honest answer, and pinning it
        here stops anyone "fixing" the asymmetry by writing at the payload
        offset and leaving the EDC alone.
        """
        source = self.image(raw_cd=True, name="rawsrc.iso")
        self.assertEqual(iso.open_image(source).sector_size, RAW_SECTOR)
        exception = self._refused(
            source, self.work / "rawout.iso", {"/DATA/FOO.BIN": b"x" * 16}
        )
        self.assertIn("2352", str(exception))


# ---------------------------------------------------------------------------
# Verifier. The two mutation tests here are the most valuable in the file.
# ---------------------------------------------------------------------------

class VerifierCatchesCorruptionTests(_IsoTestCase):
    """A verifier that cannot fail is a rubber stamp, not a verifier.

    Everything else in this suite rests on ``verify_replacement`` being able to
    say no. So it is handed known-good output with exactly one byte changed --
    once outside every declared range, once inside one -- and required to raise
    both times. The control test in between proves the honest output still
    passes, so a verifier that simply always raised would fail too.
    """

    def setUp(self) -> None:
        super().setUp()
        self.source = self.image(name="src.iso", slack=2048)
        self.destination = self.work / "good.iso"
        self.new_payload = b"replacement payload" * 20
        self.report = isowriter.replace_files(
            self.source, self.destination, {"/DATA/FOO.BIN": self.new_payload}
        )
        self.ranges = declared_ranges(self.report)

    def _tampered(self, offset: int, name: str = "bad.iso") -> Path:
        blob = bytearray(self.destination.read_bytes())
        blob[offset] ^= 0xFF
        path = self.work / name
        path.write_bytes(bytes(blob))
        return path

    def test_the_honest_output_passes(self) -> None:
        """The control. Without it the two failures below prove nothing."""
        result = isoverify.verify_replacement(self.source, self.destination, self.report)
        self.assertIsInstance(result, dict)

    def test_a_byte_changed_outside_every_declared_range_is_caught(self) -> None:
        """The core promise: only the declared ranges may differ.

        The mutated byte sits inside a *different* file's extent, so it is a
        real content change on a real disc and unambiguously outside anything
        the writer declared.
        """
        image = iso.open_image(self.destination)
        victim = iso.find(image, "/DATA/SUB/DEEP.BIN")
        offset = victim.lba * image.sector_size + image.data_offset + 4
        for start, length, _reason in self.ranges:
            self.assertFalse(
                start <= offset < start + length,
                "the chosen byte is inside a declared range; the test is void",
            )
        tampered = self._tampered(offset, "undeclared.iso")
        with self.assertRaises(VIOLATIONS):
            isoverify.verify_replacement(self.source, tampered, self.report)

    def test_a_byte_changed_inside_a_declared_extent_is_caught(self) -> None:
        """Declaring a range is permission to change it, not to change it wrongly.

        A verifier that only diffed source against destination and checked the
        diff was covered would pass this, because the byte is inside a declared
        range. It must also re-read the replaced file and compare it to the
        content that was actually asked for.
        """
        extent = [r for r in self.ranges if r[2].startswith("extent:")]
        self.assertTrue(extent, "the writer declared no extent range")
        start, length, _reason = extent[0]
        offset = start + min(7, length - 1)
        tampered = self._tampered(offset, "inside.iso")
        self.assertNotEqual(
            tampered.read_bytes()[start:start + len(self.new_payload)],
            self.new_payload,
            "the mutation did not actually alter the replaced content",
        )
        with self.assertRaises(VIOLATIONS):
            isoverify.verify_replacement(self.source, tampered, self.report)

    def test_a_corrupted_declared_length_field_is_caught(self) -> None:
        """Half of a both-endian field is the classic partial-write signature."""
        record = [r for r in self.ranges if r[2].startswith("dirrec_length:")]
        self.assertTrue(record, "the writer declared no dirrec_length range")
        start, length, _reason = record[0]
        self.assertEqual(length, 8)
        tampered = self._tampered(start + 4, "endian.iso")     # big-endian half only
        blob = tampered.read_bytes()
        self.assertNotEqual(*_read_both_endian_32(blob, start))
        with self.assertRaises(VIOLATIONS):
            isoverify.verify_replacement(self.source, tampered, self.report)

    def test_a_destination_of_the_wrong_size_is_caught(self) -> None:
        """Losing the slack is the failure mode the Deluxe image exists to warn about."""
        for label, blob in (
            ("truncated", self.destination.read_bytes()[:-2048]),
            ("extended", self.destination.read_bytes() + bytes(512)),
        ):
            with self.subTest(shape=label):
                path = self.work / (label + ".iso")
                path.write_bytes(blob)
                with self.assertRaises(VIOLATIONS):
                    isoverify.verify_replacement(self.source, path, self.report)

    def test_a_changed_pvd_is_caught(self) -> None:
        """The volume geometry is not the writer's to touch."""
        offset = _PVD_LBA * SECTOR + 80          # volume space size, LE half
        tampered = self._tampered(offset, "pvd.iso")
        with self.assertRaises(VIOLATIONS):
            isoverify.verify_replacement(self.source, tampered, self.report)

    def test_an_unrelated_image_is_not_accepted_as_the_destination(self) -> None:
        other = self.image({"OTHER.BIN": b"a different disc"}, name="other.iso")
        with self.assertRaises(VIOLATIONS + REFUSALS):
            isoverify.verify_replacement(self.source, other, self.report)


# ---------------------------------------------------------------------------
# Boot identity.
# ---------------------------------------------------------------------------

class BootIdentityTests(_IsoTestCase):
    """``SYSTEM.CNF`` is the PS2 analogue of ``default.xbe``.

    It is the only thing on the disc that identifies the title independently of
    the container, which is why recognition has to follow it rather than the
    file size or the whole-image hash.
    """

    def _image_with_cnf(self, cnf: bytes, boot_name: str = "SLUS_217.70") -> Path:
        return self.image({"SYSTEM.CNF": cnf, boot_name: BOOT_ELF}, name="boot.iso")

    def test_a_plain_system_cnf_yields_boot_file_and_serial(self) -> None:
        image = iso.open_image(self._image_with_cnf(SYSTEM_CNF))
        identity = iso.boot_identity(image)
        self.assertEqual(identity["boot2"], "cdrom0:\\SLUS_217.70;1")
        self.assertEqual(identity["boot_file"], "SLUS_217.70")
        self.assertEqual(identity["serial"], "SLUS-21770")
        self.assertEqual(identity["boot_size"], len(BOOT_ELF))
        self.assertEqual(identity["boot_sha256"], hashlib.sha256(BOOT_ELF).hexdigest())
        self.assertIn("BOOT2", identity["system_cnf"])

    def test_crlf_lf_and_odd_spacing_are_all_tolerated(self) -> None:
        """Real SYSTEM.CNF files are hand-written and inconsistent.

        Retail discs, community rebuilds and homebrew all disagree about line
        endings, spaces around ``=``, key case, and trailing whitespace. None of
        that changes the title, so none of it may change the parse.
        """
        variants = {
            "crlf": b"BOOT2 = cdrom0:\\SLUS_217.70;1\r\nVER = 1.00\r\n",
            "lf": b"BOOT2 = cdrom0:\\SLUS_217.70;1\nVER = 1.00\n",
            "no spaces": b"BOOT2=cdrom0:\\SLUS_217.70;1\r\nVER=1.00\r\n",
            "wide spaces": b"BOOT2   =    cdrom0:\\SLUS_217.70;1   \r\n",
            "leading blank line": b"\r\n\r\nBOOT2 = cdrom0:\\SLUS_217.70;1\r\n",
            "tabs": b"BOOT2\t=\tcdrom0:\\SLUS_217.70;1\r\n",
            "no trailing newline": b"BOOT2 = cdrom0:\\SLUS_217.70;1",
            "boot2 last": b"VER = 1.00\r\nVMODE = NTSC\r\nBOOT2 = cdrom0:\\SLUS_217.70;1\r\n",
        }
        for label, cnf in variants.items():
            with self.subTest(system_cnf=label):
                identity = iso.boot_identity(iso.open_image(self._image_with_cnf(cnf)))
                self.assertEqual(identity["boot_file"], "SLUS_217.70")
                self.assertEqual(identity["serial"], "SLUS-21770")

    def test_the_serial_derivation_is_the_catalogue_form(self) -> None:
        """``SLUS_209.19`` on the disc is ``SLUS-20919`` everywhere else.

        PCSX2, redump, every cover-art database and this repository's own
        capability registry spell the serial with a hyphen and no dot; the disc
        spells it ``SLUS_209.19`` because an ISO9660 level-1 name forbids the
        hyphen and caps the name at 8.3. An earlier reader kept the dot
        (``SLUS-209.19``), which joined against nothing.
        """
        for stored, serial in (
            ("SLUS_209.19", "SLUS-20919"),
            ("SLUS_217.70", "SLUS-21770"),
            ("SLUS_219.46", "SLUS-21946"),
            ("SLES_502.10", "SLES-50210"),
            ("SCUS_971.11", "SCUS-97111"),
        ):
            with self.subTest(boot_file=stored):
                cnf = ("BOOT2 = cdrom0:\\" + stored + ";1\r\n").encode("ascii")
                identity = iso.boot_identity(
                    iso.open_image(self._image_with_cnf(cnf, stored))
                )
                self.assertEqual(identity["boot_file"], stored)
                self.assertEqual(identity["serial"], serial)

    def test_a_boot2_without_a_version_suffix_still_resolves(self) -> None:
        cnf = b"BOOT2 = cdrom0:\\SLUS_217.70\r\n"
        identity = iso.boot_identity(iso.open_image(self._image_with_cnf(cnf)))
        self.assertEqual(identity["boot_file"], "SLUS_217.70")
        self.assertEqual(identity["serial"], "SLUS-21770")
        self.assertEqual(identity["boot_size"], len(BOOT_ELF))

    def test_a_disc_without_system_cnf_is_refused_explicitly(self) -> None:
        image = iso.open_image(self.image({"README.TXT": b"no boot config here"}))
        with self.assertRaises(iso.Iso9660Error) as caught:
            iso.boot_identity(image)
        self.assertTrue(str(caught.exception).strip(), "a refusal must say why")


# ---------------------------------------------------------------------------
# Ground truth. Never required; read-only; never writes to the user's library.
#
# The reader was measured against four real discs while it was built (retail
# Madden NFL 09 -- blank volume id, zero slack -- and the Madden NFL 12 Deluxe
# rebuild -- volume id MADDEN_12_MOD, 18,432 bytes of slack -- among them; the
# synthetic builder above reproduces both shapes, so those facts are asserted
# without a disc). The one disc this repository ships a lane for is ESPN NFL
# 2K5, so the gated check kept here is the identity that lane keys on: the
# serial that the capability registry, the replacement-pack audit and the disc
# inventory all spell ``SLUS-20919``, and the boot ELF digest the registry
# pins. Point ``NFL2K5_PS2_ISO`` at a legally dumped image to run it; CI has
# no disc and skips.
# ---------------------------------------------------------------------------

_NFL2K5_PS2_ISO = (
    Path(os.environ["NFL2K5_PS2_ISO"]) if os.environ.get("NFL2K5_PS2_ISO") else None
)


def _registry_ps2_identity() -> dict:
    registry = json.loads(
        (_REPO_ROOT / "mod_editor" / "capabilities" / "registry.v1.json")
        .read_text(encoding="utf-8")
    )
    (game,) = [entry for entry in registry["games"] if entry["id"] == "nfl2k5_ps2"]
    return game["retail_identity"]


@unittest.skipUnless(
    _NFL2K5_PS2_ISO is not None and _NFL2K5_PS2_ISO.is_file(),
    "set NFL2K5_PS2_ISO to a legally dumped SLUS-20919 image to run the disc-gated test",
)
class RetailNfl2k5Ps2IdentityTests(unittest.TestCase):
    """Read-only against somebody's game library.

    The size and mtime are re-checked afterwards so a regression that started
    writing fails here rather than eating a 4.6 GB file.
    """

    def setUp(self) -> None:
        stat = _NFL2K5_PS2_ISO.stat()
        self.addCleanup(self._assert_untouched, stat.st_size, stat.st_mtime_ns)
        self.image = iso.open_image(_NFL2K5_PS2_ISO)

    def _assert_untouched(self, size: int, mtime_ns: int) -> None:
        stat = _NFL2K5_PS2_ISO.stat()
        self.assertEqual(stat.st_size, size, "the disc image was written to")
        self.assertEqual(stat.st_mtime_ns, mtime_ns, "the disc image was written to")

    def test_the_boot_identity_is_the_registry_serial(self) -> None:
        identity = iso.boot_identity(self.image)
        self.assertEqual(identity["boot2"], "cdrom0:\\SLUS_209.19;1")
        self.assertEqual(identity["boot_file"], "SLUS_209.19")
        self.assertEqual(identity["serial"], "SLUS-20919")
        self.assertGreater(identity["boot_size"], 0)

    def test_the_boot_elf_digest_matches_the_registry_pin(self) -> None:
        identity = iso.boot_identity(self.image)
        self.assertEqual(
            identity["boot_sha256"], _registry_ps2_identity()["executable_sha256"]
        )

    def test_the_serial_joins_the_replacement_pack_audit(self) -> None:
        import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402

        self.assertEqual(iso.boot_identity(self.image)["serial"], audit.SERIAL)

    def test_the_resource_pack_directory_is_where_the_inventory_expects_it(self) -> None:
        entry = iso.find(self.image, "/VC_20919")
        self.assertIsNotNone(entry, "the SLUS-20919 resource pack directory is missing")
        self.assertTrue(entry.is_dir)


if __name__ == "__main__":
    unittest.main()
