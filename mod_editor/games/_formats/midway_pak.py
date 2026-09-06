"""Midway ``PAK `` resource pack — NFL Blitz Pro (2003) and Blitz: The League (2005) on PS2.

The pack (``RESIMG1.DAT`` on both discs) is a read-only file-system image with
four parts, every one of them located by arithmetic that this module checks
rather than assumes [M]:

```
+0x000  " KAP"                 'PAK ' written as a little-endian u32
+0x004  u32  512               constant on both discs; not explained
+0x008  u32  body bytes        == file bytes - 2048 (checked)
+0x00C  u32  node-table bytes  the directory's node table, see the trailer
+0x010  u32  name-table bytes  the directory's name table
+0x014  u32  metadata offset   2048 on both discs; where 0x11111111 begins
        zero to 0x800

+0x800  metadata list          u32 0x11111111, u32 records, then one 2,048-byte
                               slot per record -- a verbatim copy of each
                               object's own header record (checked)

        objects                each one a 2,048-aligned ``<hex>.of`` file:
                                 2,048-byte object record (0x22222233)
                                 member directory (32- or 64-byte entries)
                                 members, each a 2,048-byte member record
                                 (0x11111111) followed by its bytes, padded

last 2,048 bytes               the directory: 16-byte nodes
                               (name offset, kind, offset, size-or-count)
                               rooted at 0 -- a directory "objects" whose
                               leaves are the object files, and a file
                               "resmeta.lf" that is the metadata list
```

The directory in the trailer is what turns a name into a byte range: its
leaves carry ``(offset, size)`` for every object, listed in the metadata or
not, and they tile the body from the first object to the trailer [M].  The
node table's length is header word 3 and the name table's is header word 4,
which is how the two "unexplained counts" of the first reading resolved.

Two generations of the same layout exist and are told apart by measurement,
never by title:

* **2005** (Blitz: The League): the object record keeps a 64-bit timestamp
  at +16 and its string-length triple at +40; the member directory entry is
  32 bytes ``(hash, 0, offset, size, hash2, u64 timestamp, 0)``; the member
  record keeps ``size`` at +44, ``hash2`` at +52, a type word at +56 and the
  member's real file name at +68.
* **2003** (NFL Blitz Pro): seven timestamp words at +16 and the triple at
  +60; a 64-byte directory entry ``(hash, 0, offset, size, char path[48])``
  whose path is ``modules\\<object hex>\\<member hex>.mf``; the member record
  keeps ``size`` at +64, ``hash2`` at +72, a type word at +76, the byte
  length of a module string at +80, and the file name at +88 followed by
  that module string.

Both keep the member's 32-bit name hash at +4 of its record and the member
count at +12 of the object record; ``member offset`` is relative to the
object's start and names the member's *data*, one record past its record.
``hash2`` is a second 32-bit value that is not the CRC-32 of the data [M];
the name hash is none of CRC-32, FNV-1/1a, djb2, sdbm, one-at-a-time, ELF or
SuperFastHash [M] and is carried, never recomputed.

Retail-free: :func:`build_pack` synthesises a pack of either generation for
the tests and the owner mapper's self-test.  Standard library only; no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import struct
from typing import BinaryIO, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from mod_editor.games.contract import Refusal

PAK_TAG = b" KAP"
HEADER_BYTES = 24
SECTOR = 2048
RECORD_BYTES = 2048
HEADER_WORD1 = 512
META_MAGIC = 0x11111111
OBJECT_RECORD_MAGIC = 0x22222233
OBJECT_RECORD_MASK = 0xFFFFFF00
OBJECT_RECORD_FAMILY = 0x22222200
MEMBER_RECORD_MAGIC = 0x11111111
DIRECTORY_BYTES = 2048
NODE_BYTES = 16
NODE_FILE = 0
NODE_DIRECTORY = 1
OBJECTS_DIRECTORY_NAME = "objects"
METADATA_LEAF_NAME = "resmeta.lf"
LAYOUT_2003 = "2003"
LAYOUT_2005 = "2005"
ENTRY_BYTES = {LAYOUT_2005: 32, LAYOUT_2003: 64}
_PATH_FIELD_BYTES = 48


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Refusal(message)


def _printable(raw: bytes) -> bool:
    return all(32 <= c < 127 for c in raw)


def _cstring(raw: bytes, start: int) -> Tuple[str, int]:
    """The NUL-terminated ASCII string at ``start``; returns (text, index past the NUL)."""
    end = raw.find(b"\x00", start)
    if end < 0:
        end = len(raw)
    return raw[start:end].decode("latin-1"), end + 1


def round_up(value: int, granule: int = SECTOR) -> int:
    return (value + granule - 1) // granule * granule


# ---------------------------------------------------------------------------
# Header


@dataclass(frozen=True)
class PakHeader:
    word1: int
    body_bytes: int
    node_table_bytes: int
    name_table_bytes: int
    metadata_offset: int

    @property
    def header_bytes(self) -> int:
        return HEADER_BYTES


def looks_like_pak(head: Union[bytes, memoryview]) -> bool:
    return bytes(head[:4]) == PAK_TAG


def parse_header(head: bytes, size: Optional[int] = None) -> PakHeader:
    _require(len(head) >= HEADER_BYTES and head[:4] == PAK_TAG,
             "not a Midway PAK: the file does not begin with 'PAK ' as a little-endian word")
    word1, body, nodes, names, meta = struct.unpack_from("<5I", head, 4)
    header = PakHeader(word1, body, nodes, names, meta)
    if size is not None:
        _require(body + meta == size,
                 "not a Midway PAK: body bytes %d plus metadata offset %d is not the file's %d bytes" % (body, meta, size))
        _require(meta + 8 <= size and size >= meta + DIRECTORY_BYTES,
                 "not a Midway PAK: %d bytes is too short for a metadata list and a directory" % size)
    return header


# ---------------------------------------------------------------------------
# Object and member records


@dataclass(frozen=True)
class ObjectRecord:
    """The 2,048-byte record at the head of an object (and copied into the metadata list)."""
    magic: int
    name_hash: int
    slot_bytes: int
    member_count: int
    layout: str
    category: str
    path: str
    timestamp_words: Tuple[int, ...]

    @property
    def file_name(self) -> str:
        return self.path.rsplit("\\", 1)[-1]

    @property
    def stem_matches_hash(self) -> bool:
        stem = self.file_name.rsplit(".", 1)[0]
        try:
            return int(stem, 16) == self.name_hash
        except ValueError:
            return False


def parse_object_record(raw: bytes, where: str = "the object record") -> ObjectRecord:
    _require(len(raw) >= RECORD_BYTES, "%s is %d bytes; a record is %d" % (where, len(raw), RECORD_BYTES))
    magic, name_hash, slot, count = struct.unpack_from("<4I", raw, 0)
    _require(magic & OBJECT_RECORD_MASK == OBJECT_RECORD_FAMILY,
             "%s does not begin with a 0x222222xx object record (found 0x%08x)" % (where, magic))
    _require(slot == RECORD_BYTES, "%s carries %d at +8 where every object record carries %d" % (where, slot, RECORD_BYTES))
    for triple_at, layout, stamp_words in ((40, LAYOUT_2005, 2), (60, LAYOUT_2003, 7)):
        l1, l2, l3 = struct.unpack_from("<3I", raw, triple_at)
        if not (0 < l1 < 64 and 0 < l2 < 240 and l3 == 0 and triple_at + 12 + l1 + l2 <= RECORD_BYTES):
            continue
        block = raw[triple_at + 12:triple_at + 12 + l1 + l2]
        if block[l1 - 1] or block[l1 + l2 - 1] or not _printable(block[:l1 - 1]) or not _printable(block[l1:l1 + l2 - 1]):
            continue
        category = block[:l1 - 1].decode("latin-1")
        path = block[l1:l1 + l2 - 1].decode("latin-1")
        stamps = struct.unpack_from("<%dI" % stamp_words, raw, 16)
        return ObjectRecord(magic, name_hash, slot, count, layout, category, path, tuple(stamps))
    raise Refusal("%s carries no category/path string pair at +40 (2005 layout) or +60 (2003 layout)" % where)


@dataclass(frozen=True)
class Member:
    """One file inside an object.  ``offset`` is object-relative and names the data; the record precedes it."""
    name_hash: int
    offset: int
    size: int
    name: str
    hash2: int
    type_word: int
    module: str = ""
    path: str = ""
    timestamp_words: Tuple[int, ...] = ()

    @property
    def record_offset(self) -> int:
        return self.offset - RECORD_BYTES

    @property
    def extension(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""


def parse_member_record(raw: bytes, layout: str, where: str = "the member record") -> Dict[str, object]:
    """Fields of a member record in the given layout; the caller checks them against the directory."""
    _require(len(raw) >= RECORD_BYTES, "%s is %d bytes; a record is %d" % (where, len(raw), RECORD_BYTES))
    magic, name_hash, slot = struct.unpack_from("<3I", raw, 0)
    _require(magic == MEMBER_RECORD_MAGIC, "%s does not begin with the 0x11111111 member record magic (found 0x%08x)" % (where, magic))
    _require(slot == RECORD_BYTES, "%s carries %d at +8 where every member record carries %d" % (where, slot, RECORD_BYTES))
    if layout == LAYOUT_2005:
        size, zero, hash2, type_word = struct.unpack_from("<4I", raw, 44)
        name, _ = _cstring(raw, 68)
        stamps = struct.unpack_from("<2I", raw, 12)
        module = ""
    else:
        size, zero, hash2, type_word, module_bytes = struct.unpack_from("<5I", raw, 64)
        name, after = _cstring(raw, 88)
        module, _ = _cstring(raw, after) if module_bytes else ("", after)
        stamps = struct.unpack_from("<7I", raw, 12)
    _require(0 < len(name) < 128 and _printable(name.encode("latin-1")),
             "%s carries no printable file name at +%d" % (where, 68 if layout == LAYOUT_2005 else 88))
    return {"name_hash": name_hash, "size": size, "hash2": hash2, "type_word": type_word, "name": name,
            "module": module, "timestamp_words": tuple(stamps)}


# ---------------------------------------------------------------------------
# The trailer directory


@dataclass(frozen=True)
class DirectoryNode:
    name: str
    kind: int
    offset: int
    size_or_count: int
    name_offset: int

    @property
    def is_directory(self) -> bool:
        return self.kind == NODE_DIRECTORY


@dataclass(frozen=True)
class Directory:
    root: DirectoryNode
    entries: Tuple[DirectoryNode, ...]          # the root's children
    objects: Tuple[DirectoryNode, ...]          # leaves of the "objects" directory, in file order
    metadata_leaf: Optional[DirectoryNode]
    node_table_bytes: int
    name_table_bytes: int


def parse_directory(raw: bytes, header: Optional[PakHeader] = None) -> Directory:
    _require(len(raw) == DIRECTORY_BYTES, "the directory block is %d bytes, not %d" % (len(raw), DIRECTORY_BYTES))
    name_base = header.node_table_bytes if header is not None else None

    def node(at: int) -> DirectoryNode:
        _require(at + NODE_BYTES <= DIRECTORY_BYTES, "directory node at %d runs past the block" % at)
        name_off, kind, offset, count = struct.unpack_from("<4I", raw, at)
        _require(kind in (NODE_FILE, NODE_DIRECTORY), "directory node at %d has kind %d; only 0 (file) and 1 (directory) exist" % (at, kind))
        _require(name_off < DIRECTORY_BYTES, "directory node at %d names a string at %d, outside the block" % (at, name_off))
        name, _ = _cstring(raw, name_off)
        return DirectoryNode(name, kind, offset, count, name_off)

    root = node(0)
    _require(root.is_directory and root.name == "", "the directory's root node is not an unnamed directory")
    entries = tuple(node(root.offset + NODE_BYTES * i) for i in range(root.size_or_count))
    objects: Tuple[DirectoryNode, ...] = ()
    meta: Optional[DirectoryNode] = None
    for entry in entries:
        if entry.is_directory and entry.name == OBJECTS_DIRECTORY_NAME:
            objects = tuple(node(entry.offset + NODE_BYTES * i) for i in range(entry.size_or_count))
        elif not entry.is_directory and entry.name == METADATA_LEAF_NAME:
            meta = entry
    _require(objects, "the directory has no '%s' directory" % OBJECTS_DIRECTORY_NAME)
    node_bytes = NODE_BYTES * (1 + len(entries) + len(objects))
    name_end = max(n.name_offset + len(n.name) + 1 for n in (root,) + entries + objects)
    if name_base is not None:
        _require(name_base == node_bytes,
                 "header word 3 says the node table is %d bytes; the directory holds %d" % (name_base, node_bytes))
    # the name table is padded to a 4-byte multiple on both discs (1,667 -> 1,668 and 463 -> 464) [M]
    return Directory(root, entries, objects, meta, node_bytes, round_up(name_end, 4) - node_bytes)


# ---------------------------------------------------------------------------
# The pack


@dataclass
class PakObject:
    """One ``<hex>.of`` file inside the pack, located by the directory and read on demand."""
    node: DirectoryNode
    record: ObjectRecord
    listed: bool
    layout: str
    members: List[Member] = field(default_factory=list)
    checks: Dict[str, object] = field(default_factory=dict)

    @property
    def offset(self) -> int:
        return self.node.offset

    @property
    def size(self) -> int:
        return self.node.size_or_count

    @property
    def end(self) -> int:
        return self.node.offset + self.node.size_or_count

    @property
    def name(self) -> str:
        return self.node.name

    @property
    def category(self) -> str:
        return self.record.category

    @property
    def name_hash(self) -> int:
        return self.record.name_hash

    @property
    def directory_bytes(self) -> int:
        return round_up(RECORD_BYTES + self.record.member_count * ENTRY_BYTES[self.layout])

    @property
    def trailing_bytes(self) -> int:
        """Bytes after the last member's padded end and before the object's end (0 on both discs)."""
        if not self.members:
            return self.size - self.directory_bytes
        last = self.members[-1]
        return self.size - round_up(last.offset + last.size)

    def member(self, name: str) -> Member:
        for m in self.members:
            if m.name == name:
                return m
        raise Refusal("object %s (%s) has no member named %s" % (self.name, self.category, name))


class MidwayPak:
    """A Midway ``PAK `` opened over a seekable stream; ``base``/``size`` bound it inside a larger file."""

    def __init__(self, stream: BinaryIO, *, base: int = 0, size: Optional[int] = None) -> None:
        self.stream = stream
        self.base = base
        if size is None:
            stream.seek(0, io.SEEK_END)
            size = stream.tell() - base
        self.size = size
        self.header = parse_header(self.read(0, HEADER_BYTES), size)
        self.directory = parse_directory(self.read(size - DIRECTORY_BYTES, DIRECTORY_BYTES), self.header)
        self.metadata_count, self.metadata_records = self._read_metadata()
        self.objects: List[PakObject] = self._locate_objects()

    # -- raw access ---------------------------------------------------------
    def read(self, offset: int, length: int) -> bytes:
        _require(0 <= offset and offset + length <= self.size,
                 "range %d+%d lies outside the %d-byte pack" % (offset, length, self.size))
        self.stream.seek(self.base + offset)
        data = self.stream.read(length)
        _require(len(data) == length, "the stream ended at %d of the %d bytes asked for at %d" % (len(data), length, offset))
        return data

    # -- the metadata list --------------------------------------------------
    def _read_metadata(self) -> Tuple[int, List[ObjectRecord]]:
        head = self.read(self.header.metadata_offset, 8)
        magic, count = struct.unpack_from("<2I", head, 0)
        _require(magic == META_MAGIC, "the metadata list at %d does not begin with 0x11111111" % self.header.metadata_offset)
        region = 8 + count * RECORD_BYTES
        _require(self.header.metadata_offset + region <= self.size - DIRECTORY_BYTES,
                 "the metadata list declares %d records, which run past the pack" % count)
        records = [parse_object_record(self.read(self.header.metadata_offset + 8 + i * RECORD_BYTES, RECORD_BYTES),
                                       "metadata slot %d" % i) for i in range(count)]
        return count, records

    @property
    def metadata_region_bytes(self) -> int:
        return 8 + self.metadata_count * RECORD_BYTES

    @property
    def body_end(self) -> int:
        """Where the objects stop: the directory trailer begins here."""
        return self.size - DIRECTORY_BYTES

    # -- objects ------------------------------------------------------------
    def _locate_objects(self) -> List[PakObject]:
        listed = {r.name_hash for r in self.metadata_records}
        objects: List[PakObject] = []
        for leaf in self.directory.objects:
            _require(not leaf.is_directory, "directory entry %s under objects is not a file" % leaf.name)
            _require(leaf.offset % SECTOR == 0, "object %s starts at %d, which is not sector-aligned" % (leaf.name, leaf.offset))
            _require(leaf.offset + leaf.size_or_count <= self.body_end,
                     "object %s (%d+%d) runs into the directory trailer at %d" % (leaf.name, leaf.offset, leaf.size_or_count, self.body_end))
            record = parse_object_record(self.read(leaf.offset, RECORD_BYTES), "object %s's record" % leaf.name)
            _require(record.file_name.lower() == leaf.name.lower(),
                     "object %s's record names itself %s" % (leaf.name, record.file_name))
            layout = self._detect_layout(leaf, record)
            objects.append(PakObject(leaf, record, record.name_hash in listed, layout))
        return objects

    def _detect_layout(self, leaf: DirectoryNode, record: ObjectRecord) -> str:
        if record.member_count == 0:
            return record.layout
        entry = self.read(leaf.offset + RECORD_BYTES, ENTRY_BYTES[LAYOUT_2003])
        text = entry[16:24]
        layout = LAYOUT_2003 if _printable(text) and text.strip(b"\x00") == text else LAYOUT_2005
        _require(layout == record.layout,
                 "object %s's directory is the %s layout but its record is the %s layout" % (leaf.name, layout, record.layout))
        return layout

    def load_members(self, obj: PakObject) -> List[Member]:
        """Read an object's member directory and every member record; checks each against the other."""
        if obj.members or obj.checks:
            return obj.members
        stride = ENTRY_BYTES[obj.layout]
        count = obj.record.member_count
        table = self.read(obj.offset + RECORD_BYTES, count * stride) if count else b""
        members: List[Member] = []
        checks = {"members": count, "records_agree": 0, "aligned": 0, "ascending": 0, "tiled": 0, "paths_match": 0}
        previous = 0
        for i in range(count):
            base = i * stride
            name_hash, zero, offset, size = struct.unpack_from("<4I", table, base)
            where = "object %s member %d's record" % (obj.name, i)
            _require(zero == 0, "%s directory entry carries %d where 0 is expected" % (where, zero))
            _require(RECORD_BYTES <= offset and offset + size <= obj.size,
                     "%s (%d+%d) lies outside the %d-byte object" % (where, offset, size, obj.size))
            record = parse_member_record(self.read(obj.offset + offset - RECORD_BYTES, RECORD_BYTES), obj.layout, where)
            path = ""
            entry_hash2 = 0
            stamps: Tuple[int, ...] = ()
            if obj.layout == LAYOUT_2005:
                entry_hash2, stamp_lo, stamp_hi, tail_zero = struct.unpack_from("<IIII", table, base + 16)
                stamps = (stamp_lo, stamp_hi)
            else:
                path, _ = _cstring(table[base + 16:base + 16 + _PATH_FIELD_BYTES], 0)
                stem = path.rsplit("\\", 1)[-1].rsplit(".", 1)[0]
                try:
                    checks["paths_match"] += int(stem, 16) == name_hash
                except ValueError:
                    pass
            agree = (record["name_hash"] == name_hash and record["size"] == size
                     and (obj.layout == LAYOUT_2003 or record["hash2"] == entry_hash2))
            _require(agree, "%s disagrees with its directory entry (hash 0x%08x/0x%08x, size %d/%d)"
                     % (where, record["name_hash"], name_hash, record["size"], size))
            checks["records_agree"] += 1
            checks["aligned"] += offset % SECTOR == 0
            checks["ascending"] += offset > previous
            previous = offset
            members.append(Member(name_hash, offset, size, str(record["name"]), int(record["hash2"]), int(record["type_word"]),
                                  str(record["module"]), path, tuple(record["timestamp_words"]) if obj.layout == LAYOUT_2003 else stamps))
        for i, m in enumerate(members):
            following = members[i + 1].record_offset if i + 1 < len(members) else obj.size
            checks["tiled"] += round_up(m.offset + m.size) == following
        checks["first_member_at_directory_end"] = (not members) or members[0].record_offset == obj.directory_bytes
        obj.members = members
        obj.checks = checks
        return members

    def load_all(self) -> None:
        for obj in self.objects:
            self.load_members(obj)

    def extract(self, obj: PakObject, member: Member) -> bytes:
        return self.read(obj.offset + member.offset, member.size)

    def member_head(self, obj: PakObject, member: Member, length: int = 16) -> bytes:
        return self.read(obj.offset + member.offset, min(length, member.size))

    def object_named(self, category: str) -> PakObject:
        for obj in self.objects:
            if obj.category.lower() == category.lower():
                return obj
        raise Refusal("the pack has no object whose category is %s" % category)

    # -- identities ---------------------------------------------------------
    def identities(self) -> Dict[str, object]:
        """The checks that make the layout *measured*: each is a count or a bool the page can quote."""
        objects = self.objects
        first = objects[0].offset if objects else self.body_end
        tiled = all(objects[i].end == objects[i + 1].offset for i in range(len(objects) - 1)) if objects else True
        slots = {r.name_hash: r for r in self.metadata_records}
        slot_copies = 0
        for obj in objects:
            rec = slots.get(obj.record.name_hash)
            if rec is not None and self.read(obj.offset, RECORD_BYTES) == self.read(
                    self.header.metadata_offset + 8 + self.metadata_records.index(rec) * RECORD_BYTES, RECORD_BYTES):
                slot_copies += 1
        meta_leaf = self.directory.metadata_leaf
        return {
            "objects": len(objects),
            "listed_in_metadata": sum(1 for o in objects if o.listed),
            "unlisted": [o.name for o in objects if not o.listed],
            "first_object_offset": first,
            "first_object_is_first_sector_after_metadata": first == round_up(self.header.metadata_offset + self.metadata_region_bytes),
            "objects_tile_body_to_directory": tiled and (not objects or objects[-1].end == self.body_end),
            "node_table_bytes_is_header_word3": self.directory.node_table_bytes == self.header.node_table_bytes,
            "name_table_bytes_is_header_word4": self.directory.name_table_bytes == self.header.name_table_bytes,
            "metadata_leaf_is_metadata_region": meta_leaf is not None and meta_leaf.offset == self.header.metadata_offset
                                                 and meta_leaf.size_or_count == self.metadata_region_bytes,
            "metadata_slots_copy_object_records": slot_copies,
            "record_stem_is_hash": sum(1 for o in objects if o.record.stem_matches_hash),
            "layouts": sorted({o.layout for o in objects}),
        }


def open_pack(path: str) -> MidwayPak:
    return MidwayPak(open(path, "rb"))


# ---------------------------------------------------------------------------
# Synthetic packs, for tests and the owner mapper's self-test


def _object_record(name_hash: int, count: int, category: str, layout: str, stamps: Sequence[int] = ()) -> bytes:
    slot = bytearray(RECORD_BYTES)
    struct.pack_into("<4I", slot, 0, OBJECT_RECORD_MAGIC, name_hash, RECORD_BYTES, count)
    path = "objects\\%x.of" % name_hash
    strings = category.encode("latin-1") + b"\x00" + path.encode("latin-1") + b"\x00"
    if layout == LAYOUT_2005:
        stamps = tuple(stamps) or (0x11223344, 0x08C70000)
        struct.pack_into("<2I", slot, 16, *stamps[:2])
        triple_at = 40
    else:
        stamps = tuple(stamps) or (2003, 9, 25, 18, 43, 53, 216)
        struct.pack_into("<7I", slot, 16, *stamps[:7])
        triple_at = 60
    struct.pack_into("<3I", slot, triple_at, len(category) + 1, len(path) + 1, 0)
    slot[triple_at + 12:triple_at + 12 + len(strings)] = strings
    return bytes(slot)


def _member_record(name_hash: int, size: int, name: str, layout: str, *, hash2: int = 0, type_word: int = 13,
                   module: str = "ResDefaultModule") -> bytes:
    rec = bytearray(RECORD_BYTES)
    struct.pack_into("<3I", rec, 0, MEMBER_RECORD_MAGIC, name_hash, RECORD_BYTES)
    if layout == LAYOUT_2005:
        struct.pack_into("<2I", rec, 12, 0x11223344, 0x08C70000)
        struct.pack_into("<4I", rec, 44, size, 0, hash2, type_word)
        rec[68:68 + len(name)] = name.encode("latin-1")
    else:
        struct.pack_into("<7I", rec, 12, 2003, 9, 10, 23, 40, 23, 192)
        struct.pack_into("<5I", rec, 64, size, 0, hash2, type_word, len(module) + 1 if module else 0)
        blob = name.encode("latin-1") + b"\x00" + (module.encode("latin-1") + b"\x00" if module else b"")
        rec[88:88 + len(blob)] = blob
    return bytes(rec)


def build_object(name_hash: int, category: str, members: Sequence[Tuple[int, str, bytes]], *, layout: str = LAYOUT_2005,
                 trailing: bytes = b"") -> bytes:
    """One ``<hex>.of`` file: record, directory, members (record + padded data), optional trailing bytes."""
    stride = ENTRY_BYTES[layout]
    directory_bytes = round_up(RECORD_BYTES + len(members) * stride)
    out = bytearray(_object_record(name_hash, len(members), category, layout))
    table = bytearray()
    body = bytearray()
    cursor = directory_bytes
    for member_hash, name, data in members:
        data_offset = cursor + RECORD_BYTES
        hash2 = (member_hash * 2654435761) & 0xFFFFFFFF
        if layout == LAYOUT_2005:
            table += struct.pack("<4I", member_hash, 0, data_offset, len(data)) + struct.pack("<IIII", hash2, 0x11223344, 0x08C70000, 0)
        else:
            path = ("modules\\%x\\%x.mf" % (name_hash, member_hash)).encode("latin-1")
            table += struct.pack("<4I", member_hash, 0, data_offset, len(data)) + path.ljust(_PATH_FIELD_BYTES, b"\x00")
        body += _member_record(member_hash, len(data), name, layout, hash2=hash2)
        body += data + bytes(round_up(len(data)) - len(data))
        cursor = data_offset + round_up(len(data))
    out += table
    out += bytes(directory_bytes - len(out))
    out += body
    out += trailing
    return bytes(out)


def build_pack(objects: Sequence[Tuple[int, str, Sequence[Tuple[int, str, bytes]]]], *, layout: str = LAYOUT_2005,
               unlisted: Iterable[int] = (), word1: int = HEADER_WORD1) -> bytes:
    """A whole pack of either generation.

    ``objects`` are ``(name_hash, category, members)`` with members ``(hash, file name, bytes)``; the
    objects are laid out in the order given, each sector-aligned.  Hashes in ``unlisted`` get an
    object but no metadata slot, as two of The League's do.
    """
    unlisted = set(unlisted)
    blobs = [(h, build_object(h, cat, members, layout=layout)) for h, cat, members in objects]
    listed = [b for h, b in blobs if h not in unlisted]
    metadata = struct.pack("<2I", META_MAGIC, len(listed)) + b"".join(b[:RECORD_BYTES] for b in listed)
    meta_offset = SECTOR
    first = round_up(meta_offset + len(metadata))
    body = bytearray()
    body += bytes(first - meta_offset - len(metadata))
    leaves: List[Tuple[str, int, int]] = []
    cursor = first
    for h, blob in blobs:
        leaves.append(("%x.of" % h, cursor, len(blob)))
        body += blob
        cursor += len(blob)
    # the directory trailer
    names = bytearray(b"\x00\x00\x00\x00")          # the root's empty name, padded to 4 as the discs pad it
    names_off: Dict[str, int] = {"": 0}
    def intern(name: str) -> int:
        if name not in names_off:
            names_off[name] = len(names)
            names.extend(name.encode("latin-1") + b"\x00")
        return names_off[name]
    node_count = 1 + 2 + len(leaves)
    node_bytes = node_count * NODE_BYTES
    nodes = bytearray()
    nodes += struct.pack("<4I", node_bytes + intern(""), NODE_DIRECTORY, NODE_BYTES, 2)
    nodes += struct.pack("<4I", node_bytes + intern(OBJECTS_DIRECTORY_NAME), NODE_DIRECTORY, NODE_BYTES * 3, len(leaves))
    nodes += struct.pack("<4I", node_bytes + intern(METADATA_LEAF_NAME), NODE_FILE, meta_offset, len(metadata))
    for name, offset, size in leaves:
        nodes += struct.pack("<4I", node_bytes + intern(name), NODE_FILE, offset, size)
    names += bytes(round_up(len(names), 4) - len(names))   # the discs pad the name table to a 4-byte multiple
    trailer = bytes(nodes) + bytes(names)
    _require(len(trailer) <= DIRECTORY_BYTES, "a synthetic pack of %d objects overflows the 2,048-byte directory" % len(leaves))
    trailer += bytes(DIRECTORY_BYTES - len(trailer))
    total = meta_offset + len(metadata) + len(body) + len(trailer)
    header = PAK_TAG + struct.pack("<5I", word1, total - meta_offset, node_bytes, len(names), meta_offset)
    return header + bytes(SECTOR - len(header)) + metadata + bytes(body) + trailer
