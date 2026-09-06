#!/usr/bin/env python3
"""Catalogue every ``Unif`` packed-colour target on the ESPN NFL 2K5 PS2 disc.

The Xbox lane proved that NFL 2K5's per-uniform colours are **not** global: each
physical uniform package owns an eight-byte pair inside its own ``Unif``
resource -- word 0 the facemask/faceshield tint, word 1 the ``HI_turtleneck``
tint (``mod_editor/core/nfl2k5_unif_color_writer.py``).  This module establishes
the same map for ``SLUS-20919`` by reading a user's own PS2 ISO and re-deriving
every offset from the container rather than assuming the Xbox constants hold.

What the PS2 disc actually carries, measured, not assumed
--------------------------------------------------------
Each uniform package is one outer archive entry whose **chunk 0** is the
``Unif`` resource, stored uncompressed at exactly 80 body bytes::

    +0x00  'Unif'                     chunk FourCC
    +0x04  u32  stored_size  = 80
    +0x08  u32  system_bytes = 0
    +0x0C  u32  video_bytes  = 0
    +0x10  u32  lz sentinel   = 0      (0xFEEDBEEF would mean compressed)
    +0x20  object base, 80 bytes
    +0x2C  'Unif'                      object FourCC   (object +0x0C)
    +0x30  rel ptr -> +0x40            object name     (object +0x10)
    +0x34  rel ptr -> +0x50            descriptor      (object +0x14)
    +0x40  UTF-16LE "uniform\\0"
    +0x50  u32 LE facemask   ARGB      descriptor +0x00
    +0x54  u32 LE turtleneck ARGB      descriptor +0x04

The colour offset is therefore **resolved through the object's own descriptor
pointer** and only then cross-checked against the Xbox writer's constant 0x50.
A target whose pointer disagrees is reported rather than written.

Retail-free by construction
---------------------------
The catalogue carries selectors, offsets, lengths and digests.  It does **not**
carry the retail colour words: those are read from the user's own image at edit
time, exactly as the Xbox writer keeps retail bytes out of a shareable project.
``--inspect`` prints them for the operator from their own disc and writes
nothing.

Usage::

    nfl2k5_ps2_unif_color_target_catalog.py --iso <SLUS-20919.iso> \\
        --output reports/gameplay_tuning/nfl2k5_ps2_unif_color_catalog.v1.json
    nfl2k5_ps2_unif_color_target_catalog.py --iso <iso> --inspect 18H0
    nfl2k5_ps2_unif_color_target_catalog.py --selftest

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# The shipped Windows runtime is an embeddable CPython whose ._pth defines
# sys.path outright and does not add a script's own directory; put it back.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import ps2_iso9660 as iso  # noqa: E402  (repo-local reader; never writes)


SCHEMA = "nfl2k5_ps2_unif_color_catalog/v1"
SERIAL = "SLUS-20919"
PACK_DIRECTORY = "/VC_20919"
PACK_NAMES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

ALIGNMENT = 0x800
PACK_SLOT_COUNT = 36
OUTER_HEADER_SIZE = 0x0C + PACK_SLOT_COUNT * 4          # 156
OUTER_ENTRY_SIZE = 12
MAX_OUTER_ENTRIES = 1 << 20

CHUNK_HEADER_SIZE = 0x20
COMPRESSED_SENTINEL = 0xFEEDBEEF

UNIF_TAG = b"Unif"
UNIF_OBJECT_NAME = "uniform"
#: Body bytes every retail ``Unif`` object occupies.  Fixed by the container.
UNIF_OBJECT_SIZE = 80
#: Object-relative offsets, from the VC object convention.
OBJECT_FOURCC = 0x0C
OBJECT_NAME_POINTER = 0x10
OBJECT_DESCRIPTOR_POINTER = 0x14
#: Chunk-relative constants the Xbox writer uses; re-derived, then compared.
XBOX_RECORD_TAG_OFFSET = 0x2C
XBOX_COLOUR_OFFSET = 0x50
XBOX_PROBE_BYTES = 0x70
COLOUR_SPAN_BYTES = 8
WORD_NAMES = ("facemask", "turtleneck")

#: Every retail uniform package is named ``<asset><side><variant>.IFF`` and the
#: archive keys it by CRC-32 of the uppercased UTF-16LE name (XBE 0x38650).
SELECTOR_ASSET_CODES = 100
SELECTOR_VARIANTS = 100


class CatalogError(ValueError):
    """A disc did not present the uniform-colour layout this tool requires."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise CatalogError(message)


# --------------------------------------------------------------------------
# Selector namespace (shared with the Xbox lane)
# --------------------------------------------------------------------------

def uniform_name_id(name: str) -> int:
    """CRC-32 of the uppercased UTF-16LE name, no terminator (XBE 0x38650)."""
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


_SELECTOR_BY_ID = None  # type: Optional[Dict[int, str]]


def selector_index() -> Dict[int, str]:
    """``{name_id: "18H0"}`` over the whole logical uniform namespace."""
    global _SELECTOR_BY_ID
    if _SELECTOR_BY_ID is None:
        index = {}  # type: Dict[int, str]
        for asset in range(SELECTOR_ASSET_CODES):
            for side in ("H", "A"):
                for variant in range(SELECTOR_VARIANTS):
                    selector = "%02d%s%d" % (asset, side, variant)
                    index.setdefault(uniform_name_id(selector + ".IFF"), selector)
        _SELECTOR_BY_ID = index
    return _SELECTOR_BY_ID


def parse_color(text: str) -> int:
    """Accept ``AARRGGBB`` or ``#RRGGBB`` and return a 32-bit ARGB integer."""
    value = str(text).strip().lstrip("#")
    _require(
        len(value) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in value),
        "%r is not a colour; use AARRGGBB or #RRGGBB" % (text,),
    )
    if len(value) == 6:
        value = "FF" + value
    return int(value, 16)


# --------------------------------------------------------------------------
# Archive geometry
# --------------------------------------------------------------------------

class PackedArchive:
    """``/VC_20919/0. .. N.`` addressed as one virtual byte range, read-only."""

    def __init__(self, iso_path: str, packs: Sequence[Tuple[str, int, int, str]]):
        self.iso_path = iso_path
        self.packs = list(packs)          # [(letter, iso_byte_base, size, iso_path)]
        self.starts = [0]
        for _letter, _base, size, _path in self.packs:
            self.starts.append(self.starts[-1] + size)
        self._handle = None

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    @property
    def size(self) -> int:
        return self.starts[-1]

    def pack_of(self, virtual_offset: int) -> int:
        _require(virtual_offset >= 0, "negative virtual offset")
        for index in range(len(self.packs) - 1, -1, -1):
            if self.starts[index] <= virtual_offset:
                return index
        raise CatalogError("negative virtual offset")

    def locate(self, virtual_offset: int, size: int) -> Tuple[int, str, int, int]:
        """``(pack_ordinal, iso_path, offset_in_pack, iso_byte_offset)``.

        Refuses a span that would straddle two packs: the writer replaces whole
        ISO files, and a straddling edit would need two of them kept in step.
        """
        index = self.pack_of(virtual_offset)
        inside = virtual_offset - self.starts[index]
        _require(
            inside + size <= self.packs[index][2],
            "span at virtual 0x%x straddles the %s/%s pack boundary; a bounded "
            "edit must live inside one ISO file"
            % (virtual_offset, PACK_DIRECTORY, self.packs[index][0]),
        )
        return index, self.packs[index][3], inside, self.packs[index][1] + inside

    def read(self, virtual_offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        _require(
            virtual_offset >= 0 and virtual_offset + size <= self.starts[-1],
            "read outside the virtual archive",
        )
        if self._handle is None:
            self._handle = open(self.iso_path, "rb")
        parts = []  # type: List[bytes]
        while size:
            index = self.pack_of(virtual_offset)
            inside = virtual_offset - self.starts[index]
            take = min(size, self.packs[index][2] - inside)
            self._handle.seek(self.packs[index][1] + inside)
            block = self._handle.read(take)
            _require(len(block) == take,
                     "short read from pack %s" % self.packs[index][0])
            parts.append(block)
            virtual_offset += take
            size -= take
        return b"".join(parts)


def discover_packs(image) -> List[Tuple[str, int, int, str]]:
    """``[(letter, iso_byte_offset, size, iso_path)]`` for the resource packs."""
    packs = []  # type: List[Tuple[str, int, int, str]]
    for letter in PACK_NAMES:
        for candidate in ("%s/%s." % (PACK_DIRECTORY, letter),
                          "%s/%s" % (PACK_DIRECTORY, letter)):
            found = iso.find(image, candidate)
            if found is not None and not found.is_dir:
                packs.append((letter, iso.extent_byte_offset(image, found.lba),
                              found.length, found.path))
                break
        else:
            break
    _require(packs, "no %s packs found; this is not a %s resource layout"
             % (PACK_DIRECTORY, SERIAL))
    return packs


def read_outer_table(archive: PackedArchive) -> Tuple[dict, List[Tuple[int, int, int]]]:
    """The outer index header and its ``(name_id, size, offset_blocks)`` rows."""
    header = archive.read(0, OUTER_HEADER_SIZE)
    entry_count, _reserved, populated = struct.unpack_from("<III", header, 0)
    block_counts = struct.unpack_from("<%dI" % PACK_SLOT_COUNT, header, 12)
    _require(populated == len(archive.packs),
             "outer index declares %d packs, the ISO has %d"
             % (populated, len(archive.packs)))
    for ordinal, (letter, _base, size, _path) in enumerate(archive.packs):
        _require(block_counts[ordinal] * ALIGNMENT == size,
                 "pack %s: index says %d bytes, ISO says %d"
                 % (letter, block_counts[ordinal] * ALIGNMENT, size))
    _require(0 < entry_count <= MAX_OUTER_ENTRIES,
             "outer index declares %d entries" % entry_count)
    table = archive.read(OUTER_HEADER_SIZE, entry_count * OUTER_ENTRY_SIZE)
    entries = [struct.unpack_from("<III", table, index * OUTER_ENTRY_SIZE)
               for index in range(entry_count)]
    return ({"entry_count": entry_count, "populated_pack_count": populated}, entries)


def _relative_pointer(data: bytes, field: int) -> Optional[int]:
    """Visual Concepts' field-local, minus-one-biased relative pointer."""
    value = struct.unpack_from("<i", data, field)[0]
    if value == 0:
        return None
    return field + value - 1


def _utf16z(data: bytes, offset: int, limit: int) -> Optional[str]:
    if offset is None or offset & 1 or offset + 2 > limit:
        return None
    end = offset
    while end + 2 <= limit and data[end:end + 2] != b"\x00\x00":
        end += 2
    if end + 2 > limit:
        return None
    try:
        return data[offset:end].decode("utf-16le")
    except UnicodeDecodeError:
        return None


# --------------------------------------------------------------------------
# Target discovery
# --------------------------------------------------------------------------

def describe_target(probe: bytes) -> Dict[str, Any]:
    """Decode one candidate chunk header + object; never raises on bad input."""
    result = {"ok": False, "reason": None}  # type: Dict[str, Any]
    if len(probe) < XBOX_PROBE_BYTES:
        result["reason"] = "short probe"
        return result
    if probe[:4] != UNIF_TAG:
        result["reason"] = "chunk FourCC is not Unif"
        return result
    stored, system_bytes, video_bytes, sentinel = struct.unpack_from("<4I", probe, 4)
    result["stored_size"] = stored
    result["system_bytes"] = system_bytes
    result["video_bytes"] = video_bytes
    result["compressed"] = sentinel == COMPRESSED_SENTINEL
    if result["compressed"]:
        result["reason"] = (
            "the Unif body is LZ-compressed; a same-size word poke would have to "
            "be recompressed back into the stored span, which this lane refuses "
            "(no retail Unif chunk is compressed)"
        )
        return result
    if stored != UNIF_OBJECT_SIZE:
        result["reason"] = ("Unif object is %d bytes, expected %d"
                            % (stored, UNIF_OBJECT_SIZE))
        return result
    body = probe[CHUNK_HEADER_SIZE:CHUNK_HEADER_SIZE + stored]
    if body[OBJECT_FOURCC:OBJECT_FOURCC + 4] != UNIF_TAG:
        result["reason"] = "object FourCC is not Unif"
        return result
    name_pointer = _relative_pointer(body, OBJECT_NAME_POINTER)
    descriptor = _relative_pointer(body, OBJECT_DESCRIPTOR_POINTER)
    if name_pointer is None or descriptor is None:
        result["reason"] = "object name or descriptor pointer is null"
        return result
    name = _utf16z(body, name_pointer, len(body))
    if name != UNIF_OBJECT_NAME:
        result["reason"] = "object name is %r, expected %r" % (name, UNIF_OBJECT_NAME)
        return result
    if descriptor + COLOUR_SPAN_BYTES > len(body):
        result["reason"] = "descriptor 0x%x leaves no room for the colour pair" % descriptor
        return result
    result["object_name"] = name
    result["name_pointer_chunk"] = CHUNK_HEADER_SIZE + name_pointer
    result["colour_offset_chunk"] = CHUNK_HEADER_SIZE + descriptor
    result["record_tag_offset_chunk"] = CHUNK_HEADER_SIZE + OBJECT_FOURCC
    result["matches_xbox_offsets"] = (
        result["colour_offset_chunk"] == XBOX_COLOUR_OFFSET
        and result["record_tag_offset_chunk"] == XBOX_RECORD_TAG_OFFSET
    )
    facemask, turtleneck = struct.unpack_from("<II", body, descriptor)
    result["words"] = (facemask, turtleneck)
    result["ok"] = True
    return result


def scan(iso_path: str, *, progress=None) -> Dict[str, Any]:
    """Walk the disc and return every uniform-colour target it carries."""
    image = iso.open_image(iso_path)
    packs = discover_packs(image)
    targets = []  # type: List[Dict[str, Any]]
    rejected = []  # type: List[Dict[str, Any]]
    selectors = selector_index()
    with PackedArchive(str(iso_path), packs) as archive:
        _header, entries = read_outer_table(archive)
        for index, (name_id, entry_size, offset_blocks) in enumerate(entries):
            if entry_size < CHUNK_HEADER_SIZE + UNIF_OBJECT_SIZE:
                continue
            virtual = offset_blocks * ALIGNMENT
            head = archive.read(virtual, 4)
            if head != UNIF_TAG:
                continue
            probe = archive.read(virtual, min(XBOX_PROBE_BYTES, entry_size))
            described = describe_target(probe)
            selector = selectors.get(name_id)
            if not described["ok"]:
                rejected.append({
                    "outer_index": index,
                    "outer_name_id": "0x%08x" % name_id,
                    "selector": selector,
                    "reason": described["reason"],
                })
                continue
            colour_virtual = virtual + described["colour_offset_chunk"]
            ordinal, pack_path, in_pack, iso_offset = archive.locate(
                colour_virtual, COLOUR_SPAN_BYTES)
            span = archive.read(colour_virtual, COLOUR_SPAN_BYTES)
            targets.append({
                "selector": selector,
                "outer_index": index,
                "outer_name_id": "0x%08x" % name_id,
                "pack": archive.packs[ordinal][0],
                "iso_path": pack_path,
                "chunk_virtual_offset": virtual,
                "chunk_offset_in_pack": virtual - archive.starts[ordinal],
                "colour_offset_in_chunk": described["colour_offset_chunk"],
                "colour_offset_in_pack": in_pack,
                "colour_offset_in_iso": iso_offset,
                "span_size": COLOUR_SPAN_BYTES,
                "stored_size": described["stored_size"],
                "compressed": described["compressed"],
                "matches_xbox_offsets": described["matches_xbox_offsets"],
                "probe_sha256": hashlib.sha256(probe[:XBOX_PROBE_BYTES]).hexdigest(),
                "retail_span_sha256": hashlib.sha256(span).hexdigest(),
            })
            if progress is not None and len(targets) % 128 == 0:
                progress(len(targets))
    targets.sort(key=lambda row: row["outer_index"])
    return {
        "packs": [{"pack": letter, "iso_path": path, "size": size}
                  for letter, _base, size, path in packs],
        "targets": targets,
        "rejected": rejected,
        "volume_id": image.volume_id,
        "volume_blocks": image.volume_blocks,
    }


def build_catalog(iso_path: str, *, progress=None) -> Dict[str, Any]:
    """The shippable catalogue: selectors, offsets, lengths, digests."""
    found = scan(iso_path, progress=progress)
    targets = found["targets"]
    _require(targets, "no Unif colour targets found on %s" % iso_path)
    named = [row for row in targets if row["selector"]]
    aligned = [row for row in targets if row["matches_xbox_offsets"]]
    duplicates = len(targets) - len({row["selector"] for row in named})
    return {
        "schema": SCHEMA,
        "serial": SERIAL,
        "source": {
            "volume_id": found["volume_id"],
            "volume_blocks": found["volume_blocks"],
            "size": Path(iso_path).stat().st_size,
            "packs": found["packs"],
        },
        "layout": {
            "chunk_header_size": CHUNK_HEADER_SIZE,
            "object_size": UNIF_OBJECT_SIZE,
            "object_fourcc_offset": OBJECT_FOURCC,
            "object_name_pointer_offset": OBJECT_NAME_POINTER,
            "object_descriptor_pointer_offset": OBJECT_DESCRIPTOR_POINTER,
            "span_size": COLOUR_SPAN_BYTES,
            "words": [{"index": index, "name": name, "encoding": "u32 little-endian ARGB"}
                      for index, name in enumerate(WORD_NAMES)],
            "xbox_record_tag_offset": XBOX_RECORD_TAG_OFFSET,
            "xbox_colour_offset": XBOX_COLOUR_OFFSET,
            "note": "Colour offsets are resolved through each object's own "
                    "descriptor pointer and then compared with the Xbox "
                    "writer's constants; they are never assumed.",
        },
        "summary": {
            "targets": len(targets),
            "with_selector": len(named),
            "matching_xbox_offsets": len(aligned),
            "compressed_targets": sum(1 for row in targets if row["compressed"]),
            "duplicate_selectors": duplicates,
            "rejected": len(found["rejected"]),
            "home_packages": sum(1 for row in named if row["selector"][2] == "H"),
            "away_packages": sum(1 for row in named if row["selector"][2] == "A"),
        },
        "retail_free": {
            "colour_words_included": False,
            "note": "Only digests of the retail eight-byte spans are recorded. "
                    "The words themselves are read from the operator's own image "
                    "at edit time.",
        },
        "targets": targets,
        "rejected": found["rejected"],
    }


def find_target(catalog: Dict[str, Any], selector: str) -> Dict[str, Any]:
    """Resolve one selector (``18H0``) or ``outer:<index>`` in a catalogue."""
    wanted = str(selector).strip().upper()
    if wanted.startswith("OUTER:"):
        try:
            index = int(wanted.split(":", 1)[1], 0)
        except ValueError:
            raise CatalogError("%r is not an outer index" % (selector,))
        matches = [row for row in catalog["targets"] if row["outer_index"] == index]
    else:
        matches = [row for row in catalog["targets"] if row["selector"] == wanted]
    _require(matches, "no uniform-colour target named %r" % (selector,))
    _require(len(matches) == 1, "%r resolves to %d targets" % (selector, len(matches)))
    return matches[0]


def write_json(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


# --------------------------------------------------------------------------
# Synthetic fixture (shared with the patcher's and the tests' self-checks)
# --------------------------------------------------------------------------

def _pointer(field: int, target: int) -> bytes:
    return struct.pack("<i", target - field + 1)


def unif_chunk(facemask: int, turtleneck: int, *, compressed: bool = False,
               object_size: int = UNIF_OBJECT_SIZE,
               object_name: str = UNIF_OBJECT_NAME) -> bytes:
    """One retail-shaped ``Unif`` chunk, for fixtures and tests."""
    body = bytearray(object_size)
    body[OBJECT_FOURCC:OBJECT_FOURCC + 4] = UNIF_TAG
    name_at = 0x20
    descriptor_at = 0x30
    body[OBJECT_NAME_POINTER:OBJECT_NAME_POINTER + 4] = _pointer(
        OBJECT_NAME_POINTER, name_at)
    body[OBJECT_DESCRIPTOR_POINTER:OBJECT_DESCRIPTOR_POINTER + 4] = _pointer(
        OBJECT_DESCRIPTOR_POINTER, descriptor_at)
    encoded = object_name.encode("utf-16le") + b"\x00\x00"
    body[name_at:name_at + len(encoded)] = encoded
    struct.pack_into("<II", body, descriptor_at, facemask, turtleneck)
    struct.pack_into("<f", body, descriptor_at + 0x10, 1.0)
    header = bytearray(CHUNK_HEADER_SIZE)
    header[0:4] = UNIF_TAG
    struct.pack_into("<4I", header, 4, len(body), 0, 0,
                     COMPRESSED_SENTINEL if compressed else 0)
    return bytes(header) + bytes(body)


def build_synthetic_iso(entries: Optional[Sequence[Tuple[str, bytes]]] = None) -> bytes:
    """A two-pack ``/VC_20919`` archive inside a PS2-shaped ISO9660 volume.

    ``entries`` are ``(logical_name, payload)`` pairs; the logical name is
    hashed exactly as the retail archive keys its entries, so a fixture target
    resolves through the same selector namespace the disc uses.
    """
    if entries is None:
        entries = [
            ("18H0.IFF", unif_chunk(0xFFA29895, 0xFF272320)),
            ("18A0.IFF", unif_chunk(0xFF000000, 0xFF665900)),
            ("07H1.IFF", unif_chunk(0xFF112233, 0xFF445566, compressed=True)),
            ("ZZZZ.BIN", b"RAWD" + bytes(12) + b"not a chunk stream" * 4),
        ]
    payloads = [payload for _name, payload in entries]
    table_size = OUTER_HEADER_SIZE + len(payloads) * OUTER_ENTRY_SIZE
    cursor = (table_size + ALIGNMENT - 1) // ALIGNMENT
    records = []
    for (name, payload) in entries:
        records.append((uniform_name_id(name), len(payload), cursor))
        cursor += (len(payload) + ALIGNMENT - 1) // ALIGNMENT
    virtual = bytearray(cursor * ALIGNMENT)
    for (_name_id, size, offset_blocks), payload in zip(records, payloads):
        virtual[offset_blocks * ALIGNMENT:offset_blocks * ALIGNMENT + size] = payload
    split = (records[-1][2] // 2 or 1) * ALIGNMENT
    split = min(max(split, ALIGNMENT), len(virtual) - ALIGNMENT)
    split -= split % ALIGNMENT
    pack0, pack1 = bytes(virtual[:split]), bytes(virtual[split:])
    header = bytearray(OUTER_HEADER_SIZE)
    struct.pack_into("<III", header, 0, len(records), 0, 2)
    struct.pack_into("<II", header, 12, len(pack0) // ALIGNMENT, len(pack1) // ALIGNMENT)
    table = b"".join(struct.pack("<III", *record) for record in records)
    pack0 = bytes(header) + table + pack0[len(header) + len(table):]
    _require(len(pack0) % ALIGNMENT == 0 and len(pack1) % ALIGNMENT == 0,
             "fixture packs must stay block aligned")
    return iso.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.01\r\n"
                              b"VMODE = NTSC\r\n"),
            (b"SLUS_209.19;1", b"\x7fELF" + bytes(2044)),
        ],
        sub_name=b"VC_20919",
        sub_files=[(b"0.;1", pack0), (b"1.;1", pack1)],
    )


def selftest(tmp: Optional[str] = None) -> int:
    """Prove the scan on a synthetic disc.  Needs no game data."""
    import tempfile

    failures = []  # type: List[str]

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    check(uniform_name_id("18H0.IFF") == uniform_name_id("18h0.iff"),
          "the name id must be case-insensitive")
    check(selector_index()[uniform_name_id("18H0.IFF")] == "18H0",
          "the selector index must round-trip 18H0")
    check(parse_color("#FF0000") == 0xFFFF0000, "#RRGGBB must imply alpha FF")
    check(parse_color("8012ab34") == 0x8012AB34, "AARRGGBB must be taken verbatim")
    for bad in ("", "12345", "ggggggg", "#12345"):
        try:
            parse_color(bad)
        except CatalogError:
            pass
        else:
            failures.append("parse_color accepted %r" % (bad,))

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        image = Path(work) / "synthetic.iso"
        image.write_bytes(build_synthetic_iso())
        catalog = build_catalog(str(image))
        check(catalog["schema"] == SCHEMA, "schema must be stamped")
        check(catalog["summary"]["targets"] == 2,
              "two uncompressed Unif targets expected, got %d"
              % catalog["summary"]["targets"])
        check(catalog["summary"]["rejected"] == 1,
              "the compressed Unif must be rejected, not catalogued")
        check(catalog["summary"]["matching_xbox_offsets"] == 2,
              "the fixture must land on the Xbox colour offset")
        check(catalog["summary"]["compressed_targets"] == 0,
              "no compressed target may reach the catalogue")
        check(all("facemask_argb" not in row and "words" not in row
                  for row in catalog["targets"]),
              "the catalogue must not carry retail colour words")
        target = find_target(catalog, "18H0")
        check(target["colour_offset_in_chunk"] == XBOX_COLOUR_OFFSET,
              "colour offset must resolve to 0x50")
        check(target["span_size"] == COLOUR_SPAN_BYTES, "span must be eight bytes")
        check(target["iso_path"].upper().startswith("/VC_20919/"),
              "targets must name their pack file")
        try:
            find_target(catalog, "99A9")
        except CatalogError:
            pass
        else:
            failures.append("find_target accepted an absent selector")

        rejected = catalog["rejected"][0]
        check(rejected["selector"] == "07H1", "the rejection must name its selector")
        check("compressed" in (rejected["reason"] or ""),
              "the rejection must say the body is compressed")

        output = Path(work) / "catalog.json"
        write_json(output, catalog)
        check(json.loads(output.read_text(encoding="utf-8"))["schema"] == SCHEMA,
              "the written catalogue must re-read")

    for failure in failures:
        print("FAIL: %s" % failure, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_UNIF_COLOR_CATALOG_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", help="the operator's own SLUS-20919 ISO")
    parser.add_argument("--output", type=Path, help="catalogue JSON to write")
    parser.add_argument("--inspect", metavar="SELECTOR",
                        help="print one target's current colours and exit")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--tmp", help="directory for self-test scratch files")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.tmp)
    if not args.iso:
        parser.error("--iso is required unless --selftest is given")

    try:
        catalog = build_catalog(args.iso)
    except (CatalogError, OSError, iso.FormatError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.inspect:
        try:
            target = find_target(catalog, args.inspect)
        except CatalogError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        with open(args.iso, "rb") as stream:
            stream.seek(target["colour_offset_in_iso"])
            span = stream.read(COLOUR_SPAN_BYTES)
        facemask, turtleneck = struct.unpack("<II", span)
        print("selector        %s" % target["selector"])
        print("outer index     %d (%s)" % (target["outer_index"], target["outer_name_id"]))
        print("iso path        %s" % target["iso_path"])
        print("colour offset   %d (0x%x) in pack, %d in the image"
              % (target["colour_offset_in_pack"], target["colour_offset_in_pack"],
                 target["colour_offset_in_iso"]))
        print("facemask        %08X" % facemask)
        print("turtleneck      %08X" % turtleneck)
        return 0

    if args.output:
        write_json(args.output, catalog)
    summary = catalog["summary"]
    print("NFL2K5_PS2_UNIF_COLOR_CATALOG_OK targets=%d selectors=%d "
          "xbox_offsets=%d rejected=%d home=%d away=%d"
          % (summary["targets"], summary["with_selector"],
             summary["matching_xbox_offsets"], summary["rejected"],
             summary["home_packages"], summary["away_packages"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
