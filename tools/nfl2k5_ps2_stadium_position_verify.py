#!/usr/bin/env python3
"""Independently verify a PS2 NFL 2K5 stadium position patch.

Given the stock ISO, the patched ISO, the catalogue and the recipe, this
re-derives from those four files alone that:

1. the two images are the same length, and **every byte that differs lies
   inside the owning SCNE chunk's fixed span** -- streamed, not sampled;
2. that span's 0x20 resource wrapper is byte-identical, so the in-place
   decode scratch word at +0x14 never moved;
3. the patched body still decompresses, to a buffer of exactly the wrapper's
   declared size;
4. the decoded buffers differ **only** inside the declared position lanes,
   and inside those only in the x/y/z of each 16-byte element -- the w
   component of every vertex is byte-identical;
5. the new coordinates are exactly the ones the recipe asked for;
6. every VIF ``UNPACK`` ``NUM`` field, every DMA tag, and every byte of every
   geometry chain outside the position payloads is unchanged -- that is what
   "same vertex count, same triangle set" means on this hardware, because the
   count lives in ``NUM`` and the primitives are assembled by the VU1
   microprogram the chain invokes;
7. the ISO9660 directory record for each touched pack still declares the same
   both-endian extent length, and the packs' extents did not move.

INDEPENDENCE
------------
This program imports **only the standard library**.  It shares no ISO9660
reader, no pack parser, no VC-LZ decoder and no SCNE walker with the writer;
each is reimplemented here from the format, so agreement between them is
evidence rather than a tautology.

USAGE
-----
    python3 tools/nfl2k5_ps2_stadium_position_verify.py \\
        --source-iso <stock.iso> --output-iso <patched.iso> \\
        --catalog <catalog.json> --recipe <recipe.json> [--report <out.json>]
    python3 tools/nfl2k5_ps2_stadium_position_verify.py --selftest

Python 3.9 compatible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from typing import Dict, List, Optional, Sequence, Tuple

SCHEMA = "nfl2k5_ps2_stadium_position_verify/v1"
CATALOG_SCHEMA = "nfl2k5_ps2_stadium_target_catalog/v1"
RECIPE_SCHEMA = "nfl2k5_ps2_stadium_position_recipe/v1"

SECTOR = 2048
PVD_BLOCK = 16
PACK_DIRECTORY = "VC_20919"
ALIGNMENT = 0x800
PACK_SLOTS = 36
OUTER_HEADER = 0x0C + PACK_SLOTS * 4
OUTER_ENTRY = 12
CHUNK_HEADER = 0x20
COMPRESSED = 0xFEEDBEEF
ELEMENT = 16
LANE = 12
READ_BLOCK = 1 << 22


class VerifyError(ValueError):
    """The pair of images, or the claim made about them, did not hold."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# A minimal ISO9660 reader, written here so it shares nothing with the writer
# ---------------------------------------------------------------------------

def _read_at(handle, offset: int, size: int, what: str) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    _require(len(data) == size, "short read of %s" % what)
    return data


def _both_u32(record: bytes, offset: int, what: str) -> int:
    little = struct.unpack_from("<I", record, offset)[0]
    big = struct.unpack_from(">I", record, offset + 4)[0]
    _require(little == big, "%s both-endian halves disagree (%d vs %d)"
             % (what, little, big))
    return little


def _walk_directory(handle, lba: int, length: int, prefix: str,
                    out: Dict[str, Tuple[int, int, int, int]], depth: int) -> None:
    _require(depth < 8, "directory nesting is deeper than this verifier walks")
    data = _read_at(handle, lba * SECTOR, length, "directory extent")
    offset = 0
    while offset < len(data):
        size = data[offset]
        if size == 0:
            offset = (offset // SECTOR + 1) * SECTOR
            continue
        record = data[offset:offset + size]
        _require(len(record) == size, "truncated directory record")
        name_length = record[32]
        name = record[33:33 + name_length]
        flags = record[25]
        child_lba = _both_u32(record, 2, "extent lba")
        child_length = _both_u32(record, 10, "data length")
        if name not in (b"\x00", b"\x01"):
            text = name.decode("latin-1").split(";")[0]
            path = prefix + "/" + text
            if flags & 0x02:
                _walk_directory(handle, child_lba, child_length, path, out, depth + 1)
            else:
                # (lba, length, record byte offset in the image, record size)
                out[path.upper()] = (child_lba, child_length,
                                     lba * SECTOR + offset, size)
        offset += size


def read_iso_packs(path: str) -> dict:
    """The VC pack files of one image, with each one's directory record."""
    size = os.stat(path).st_size
    with open(path, "rb") as handle:
        pvd = _read_at(handle, PVD_BLOCK * SECTOR, SECTOR, "primary volume descriptor")
        _require(pvd[0] == 1 and pvd[1:6] == b"CD001",
                 "block 16 is not a primary volume descriptor; a 2352-byte raw "
                 "image is out of scope, exactly as the writer refuses one")
        block_size = struct.unpack_from("<H", pvd, 128)[0]
        _require(block_size == SECTOR, "logical block size is %d" % block_size)
        volume_blocks = _both_u32(pvd, 80, "volume space size")
        root = pvd[156:156 + 34]
        root_lba = _both_u32(root, 2, "root extent")
        root_length = _both_u32(root, 10, "root length")
        entries: Dict[str, Tuple[int, int, int, int]] = {}
        _walk_directory(handle, root_lba, root_length, "", entries, 0)
    packs = []
    for letter in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        key = ("/%s/%s." % (PACK_DIRECTORY, letter)).upper()
        if key not in entries:
            key = ("/%s/%s" % (PACK_DIRECTORY, letter)).upper()
        if key not in entries:
            break
        lba, length, record_offset, record_size = entries[key]
        packs.append({"letter": letter, "iso_path": key, "lba": lba,
                      "length": length, "byte_offset": lba * SECTOR,
                      "record_offset": record_offset, "record_size": record_size})
    _require(packs, "no /%s packs in %s" % (PACK_DIRECTORY, path))
    return {"file_size": size, "volume_blocks": volume_blocks, "packs": packs}


def _virtual_read(handle, packs: Sequence[dict], offset: int, size: int) -> bytes:
    """Read across the packs addressed as one flat byte range."""
    starts = [0]
    for pack in packs:
        starts.append(starts[-1] + pack["length"])
    _require(0 <= offset and offset + size <= starts[-1],
             "read outside the virtual archive")
    parts = []
    remaining = size
    cursor = offset
    while remaining:
        index = max(i for i in range(len(packs)) if starts[i] <= cursor)
        inside = cursor - starts[index]
        take = min(remaining, packs[index]["length"] - inside)
        parts.append(_read_at(handle, packs[index]["byte_offset"] + inside, take,
                              "pack %s" % packs[index]["letter"]))
        cursor += take
        remaining -= take
    return b"".join(parts)


def read_outer_table(handle, packs: Sequence[dict]) -> List[Tuple[int, int, int]]:
    header = _virtual_read(handle, packs, 0, OUTER_HEADER)
    count, reserved, populated = struct.unpack_from("<III", header, 0)
    blocks = struct.unpack_from("<%dI" % PACK_SLOTS, header, 12)
    _require(reserved == 0, "outer header reserved word is %d" % reserved)
    _require(populated == len(packs),
             "outer index declares %d packs, the image has %d" % (populated, len(packs)))
    for index, pack in enumerate(packs):
        _require(blocks[index] * ALIGNMENT == pack["length"],
                 "pack %s: index says %d bytes, the image says %d"
                 % (pack["letter"], blocks[index] * ALIGNMENT, pack["length"]))
    _require(0 < count <= 1 << 20, "outer index declares %d entries" % count)
    table = _virtual_read(handle, packs, OUTER_HEADER, count * OUTER_ENTRY)
    return [struct.unpack_from("<III", table, index * OUTER_ENTRY)
            for index in range(count)]


# ---------------------------------------------------------------------------
# A VC-LZ decoder, written here for the same reason
# ---------------------------------------------------------------------------

def decompress(stream: bytes, expected: int) -> Tuple[bytes, int]:
    """Decode a VC-LZ body.  Returns (bytes, compressed bytes consumed)."""
    _require(len(stream) >= 10, "compressed stream is shorter than its prefix")
    declared = struct.unpack_from("<I", stream, 0)[0]
    _require(declared == expected,
             "stream declares %d output bytes, the wrapper says %d"
             % (declared, expected))
    offset_bits = stream[8]
    _require(1 <= offset_bits <= 15, "invalid offset bit count %d" % offset_bits)
    length_bits = 16 - offset_bits
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << length_bits) - 1
    out = bytearray(expected)
    source = 9
    flags = stream[source]
    source += 1
    mask = 1
    produced = 0
    while produced < expected:
        if flags & mask:
            _require(source + 2 <= len(stream), "truncated match token")
            code = struct.unpack_from("<H", stream, source)[0]
            source += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            _require(distance and distance <= produced, "invalid match distance")
            _require(produced + length <= expected, "match overruns the output")
            # The title copies a match from its high index down, so a match may
            # not overlap the bytes it is producing.
            for index in range(length - 1, -1, -1):
                out[produced + index] = out[produced + index - distance]
            produced += length
        else:
            _require(source < len(stream), "truncated literal")
            out[produced] = stream[source]
            source += 1
            produced += 1
        mask = (mask << 1) & 0xFF
        if mask == 0 and produced < expected:
            _require(source < len(stream), "missing flag byte")
            flags = stream[source]
            source += 1
            mask = 1
    return bytes(out), source


# ---------------------------------------------------------------------------
# A SCNE / DMA / VIF walker, written here for the same reason
# ---------------------------------------------------------------------------

UNPACK_ELEMENT = {(0, 0): 4, (0, 1): 2, (0, 2): 1,
                  (1, 0): 8, (1, 1): 4, (1, 2): 2,
                  (2, 0): 12, (2, 1): 6, (2, 2): 3,
                  (3, 0): 16, (3, 1): 8, (3, 2): 4, (3, 3): 2}
VIF_EXTRA = {0x20: 4, 0x30: 16, 0x31: 16}
VIF_KNOWN = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x10, 0x11,
             0x13, 0x14, 0x15, 0x17, 0x20, 0x30, 0x31}


def _resolve(system: bytes, field: int) -> Optional[int]:
    if field < 0 or field + 4 > len(system):
        return None
    value = struct.unpack_from("<i", system, field)[0]
    if value == 0:
        return None
    target = field + value - 1
    return target if 0 <= target < len(system) else None


def _vif_block(system: bytes, start: int, size: int, unpacks: List[dict]) -> None:
    position = start
    end = start + size
    while position + 4 <= end:
        code = struct.unpack_from("<I", system, position)[0]
        command = (code >> 24) & 0xFF
        num = (code >> 16) & 0xFF
        immediate = code & 0xFFFF
        position += 4
        if command >= 0x60:
            shape = ((command >> 2) & 3, command & 3)
            element = UNPACK_ELEMENT.get(shape)
            _require(element is not None,
                     "unsupported UNPACK 0x%02X at 0x%x" % (command, position - 4))
            count = num if num else 256
            payload = count * element
            _require(position + payload <= end, "UNPACK payload past its block")
            unpacks.append({"code_offset": position - 4, "vn": shape[0],
                            "vl": shape[1], "num": count, "element": element,
                            "data_offset": position, "data_bytes": payload,
                            "vu_address": immediate & 0x3FF})
            position = (position + payload + 3) & ~3
            continue
        _require(command in VIF_KNOWN,
                 "unknown VIF command 0x%02X at 0x%x" % (command, position - 4))
        position += VIF_EXTRA.get(command, 0)


def walk_chain(system: bytes, start: int) -> dict:
    """Walk one DMA/VIF chain to its terminator.  Raises on anything unclean."""
    _require(start is not None and 0 <= start and start % 4 == 0
             and start + 16 <= len(system), "chain pointer is not a bounded qword")
    unpacks: List[dict] = []
    tags: List[dict] = []
    position = start
    while position + 16 <= len(system):
        low = struct.unpack_from("<I", system, position)[0]
        qwc = low & 0xFFFF
        identifier = (low >> 28) & 7
        tags.append({"offset": position, "id": identifier, "qwc": qwc})
        _vif_block(system, position + 8, 8, unpacks)
        position += 16
        if qwc:
            _require(position + qwc * 16 <= len(system),
                     "DMA tag QWC %d past the system buffer" % qwc)
            _vif_block(system, position, qwc * 16, unpacks)
            position += qwc * 16
        if identifier in (0, 7):
            return {"tags": tags, "unpacks": unpacks, "end_offset": position}
        _require(len(tags) <= 4096, "chain exceeded 4096 DMA tags")
    raise VerifyError("chain reached the system buffer end unterminated")


def scene_lanes(system: bytes, shape_index: int, batch_index: int) -> List[dict]:
    """Every multi-vertex V4_32 UNPACK of one shape's one batch."""
    _require(system[0x0C:0x10] == b"SCNE", "decoded object is not an SCNE")
    descriptor = _resolve(system, 0x14)
    _require(descriptor is not None, "null SCNE descriptor pointer")
    shape_count = struct.unpack_from("<I", system, descriptor + 0x2C)[0]
    shape_table = _resolve(system, descriptor + 0x30)
    _require(shape_table is not None and shape_index < shape_count,
             "shape %d is outside the scene's %d shapes" % (shape_index, shape_count))
    record = shape_table + shape_index * 0x70
    _require(record + 0x70 <= len(system), "shape record past the system buffer")
    batch_count = struct.unpack_from("<I", system, record + 0x68)[0]
    batch_table = _resolve(system, record + 0x6C)
    _require(batch_table is not None and batch_index < batch_count,
             "batch %d is outside the shape's %d batches" % (batch_index, batch_count))
    chain_start = _resolve(system, batch_table + batch_index * 0x18)
    chain = walk_chain(system, chain_start)
    lanes = [u for u in chain["unpacks"] if u["vn"] == 3 and u["vl"] == 0 and u["num"] > 1]
    return [{"chain_start": chain_start, "chain_end": chain["end_offset"],
             "tags": len(chain["tags"]), "unpacks": len(chain["unpacks"]),
             "lane": lane, "ordinal": ordinal}
            for ordinal, lane in enumerate(lanes)]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _load_json(path: str, label: str) -> dict:
    _require(os.path.exists(path) and not os.path.islink(path),
             "%s must be an existing non-symlink file" % label)
    with open(path, "rb") as handle:
        payload = handle.read()

    def reject(pairs):
        seen = {}
        for key, value in pairs:
            _require(key not in seen, "duplicate JSON key in %s: %s" % (label, key))
            seen[key] = value
        return seen

    def constant(token):
        raise VerifyError("non-finite JSON constant in %s: %s" % (label, token))

    value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject,
                       parse_constant=constant)
    _require(isinstance(value, dict), "%s root must be an object" % label)
    return {"value": value, "sha256": _sha(payload)}


_TARGET_FIELDS = ("e", "c", "s", "b", "l")


def _parse_target_id(target_id: str) -> dict:
    parts = target_id.split("/")
    _require(len(parts) == 7 and parts[0] == "nfl2k5ps2" and parts[1] == "stadium",
             "target_id %r is not a PS2 stadium target" % target_id)
    numbers = {}
    for field, part in zip(_TARGET_FIELDS, parts[2:]):
        _require(part.startswith(field) and part[1:].isdigit(),
                 "target_id %r component %r is malformed" % (target_id, part))
        numbers[field] = int(part[1:])
    return numbers


def load_inputs(catalog_path: str, recipe_path: str) -> dict:
    catalog = _load_json(catalog_path, "catalog")
    _require(catalog["value"].get("schema") == CATALOG_SCHEMA,
             "catalog schema is not %s" % CATALOG_SCHEMA)
    scenes = catalog["value"].get("scenes") or []
    _require(scenes, "catalog carries no scenes")
    rows = {}
    for row in catalog["value"].get("targets") or []:
        _require(row["target_id"] not in rows,
                 "duplicate catalog target_id %s" % row["target_id"])
        index = row.get("scene_index")
        _require(isinstance(index, int) and 0 <= index < len(scenes),
                 "catalog target %s names no scene" % row["target_id"])
        row["source_identity"] = scenes[index]["identity"]
        rows[row["target_id"]] = row
    _require(rows, "catalog carries no targets")

    recipe = _load_json(recipe_path, "recipe")
    value = recipe["value"]
    _require(set(value) == {"schema", "catalog", "edits"}, "recipe fields differ")
    _require(value["schema"] == RECIPE_SCHEMA, "recipe schema differs")
    _require(value["catalog"] == {"schema": CATALOG_SCHEMA,
                                  "sha256": catalog["sha256"]},
             "the recipe pins a different catalog than the one supplied")
    edits = []
    identity = None
    for index, edit in enumerate(value["edits"]):
        _require(set(edit) == {"target_id", "positions"},
                 "edits[%d] fields differ" % index)
        row = rows.get(edit["target_id"])
        _require(row is not None,
                 "edits[%d] target_id is not in the catalog" % index)
        if identity is None:
            identity = row["source_identity"]
        _require(row["source_identity"] == identity,
                 "edits[%d] selects a different SCNE chunk" % index)
        count = row["position"]["vertex_count"]
        _require(len(edit["positions"]) == count,
                 "edits[%d] carries %d vertices, the catalog says %d"
                 % (index, len(edit["positions"]), count))
        triples = []
        for vertex, triple in enumerate(edit["positions"]):
            _require(isinstance(triple, list) and len(triple) == 3,
                     "edits[%d] positions[%d] is not XYZ" % (index, vertex))
            values = []
            for axis, component in enumerate(triple):
                _require(type(component) in (int, float)
                         and math.isfinite(float(component)),
                         "edits[%d] positions[%d][%d] is not a finite number"
                         % (index, vertex, axis))
                number = float(component)
                _require(number == struct.unpack("<f", struct.pack("<f", number))[0],
                         "edits[%d] positions[%d][%d] is not exactly binary32"
                         % (index, vertex, axis))
                values.append(number)
            triples.append(tuple(values))
        edits.append({"target_id": edit["target_id"], "row": row,
                      "positions": triples,
                      "address": _parse_target_id(edit["target_id"])})
    return {"catalog": catalog, "recipe": recipe, "edits": edits,
            "identity": identity, "rows": rows}


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _chunk_span(handle, packs, table, identity: dict) -> dict:
    entry_index = identity["entry_index"]
    _require(0 <= entry_index < len(table),
             "catalog entry index %d is outside the outer table" % entry_index)
    name_id, entry_size, offset_blocks = table[entry_index]
    _require("0x%08x" % name_id == identity["entry_name_id"],
             "outer entry %d carries a different name id" % entry_index)
    virtual = offset_blocks * ALIGNMENT + identity["chunk_offset"]
    header = _virtual_read(handle, packs, virtual, CHUNK_HEADER)
    _require(header[:4] == b"SCNE", "the catalogued chunk is not a SCNE")
    stored, system_bytes, video_bytes, magic, scratch, r0, r1 = \
        struct.unpack_from("<7I", header, 4)
    _require(magic == COMPRESSED, "the catalogued chunk is not VC-LZ compressed")
    _require(system_bytes == identity["system_bytes"]
             and video_bytes == identity["video_bytes"],
             "the chunk's decoded extents differ from the catalogued ones")
    _require(identity["chunk_offset"] + CHUNK_HEADER + stored <= entry_size,
             "the chunk runs past its outer entry")
    return {"virtual_offset": virtual, "stored": stored,
            "system_bytes": system_bytes, "video_bytes": video_bytes,
            "scratch": scratch, "reserved": (r0, r1),
            "span_size": CHUNK_HEADER + stored,
            "span": _virtual_read(handle, packs, virtual, CHUNK_HEADER + stored)}


def _physical_span(packs: Sequence[dict], virtual_offset: int, size: int) -> List[dict]:
    starts = [0]
    for pack in packs:
        starts.append(starts[-1] + pack["length"])
    out = []
    cursor = virtual_offset
    remaining = size
    while remaining:
        index = max(i for i in range(len(packs)) if starts[i] <= cursor)
        inside = cursor - starts[index]
        take = min(remaining, packs[index]["length"] - inside)
        out.append({"pack": packs[index]["letter"],
                    "image_offset": packs[index]["byte_offset"] + inside,
                    "size": take})
        cursor += take
        remaining -= take
    return out


def _image_diff(source: str, output: str, allowed: Sequence[dict]) -> dict:
    """Stream both images; every difference must fall in an allowed range."""
    windows = sorted((item["image_offset"], item["image_offset"] + item["size"])
                     for item in allowed)
    changed = 0
    first = None
    last = None
    outside = []
    with open(source, "rb") as left, open(output, "rb") as right:
        offset = 0
        while True:
            a = left.read(READ_BLOCK)
            b = right.read(READ_BLOCK)
            _require(len(a) == len(b),
                     "the two images stopped at different lengths")
            if not a:
                break
            if a != b:
                for index in range(len(a)):
                    if a[index] == b[index]:
                        continue
                    position = offset + index
                    changed += 1
                    if first is None:
                        first = position
                    last = position
                    if not any(low <= position < high for low, high in windows):
                        if len(outside) < 16:
                            outside.append(position)
            offset += len(a)
    _require(not outside,
             "%d byte(s) outside the declared chunk span changed, first at %d"
             % (len(outside), outside[0] if outside else -1))
    return {"changed_bytes": changed, "first_changed_offset": first,
            "last_changed_offset": last, "allowed_windows": len(windows)}


def verify(source_iso: str, output_iso: str, catalog_path: str,
           recipe_path: str) -> dict:
    inputs = load_inputs(catalog_path, recipe_path)
    identity = inputs["identity"]

    source_layout = read_iso_packs(source_iso)
    output_layout = read_iso_packs(output_iso)
    _require(source_layout["file_size"] == output_layout["file_size"],
             "the images are %d and %d bytes; a bounded write keeps the length"
             % (source_layout["file_size"], output_layout["file_size"]))
    _require(source_layout["volume_blocks"] == output_layout["volume_blocks"],
             "the volume space size changed")
    _require(len(source_layout["packs"]) == len(output_layout["packs"]),
             "the pack count changed")
    for before, after in zip(source_layout["packs"], output_layout["packs"]):
        _require(before["lba"] == after["lba"] and before["length"] == after["length"],
                 "pack %s moved or changed declared length" % before["letter"])
        _require(before["record_offset"] == after["record_offset"]
                 and before["record_size"] == after["record_size"],
                 "pack %s's directory record moved or resized" % before["letter"])

    with open(source_iso, "rb") as handle:
        table = read_outer_table(handle, source_layout["packs"])
        before = _chunk_span(handle, source_layout["packs"], table, identity)
    with open(output_iso, "rb") as handle:
        after_table = read_outer_table(handle, output_layout["packs"])
        after = _chunk_span(handle, output_layout["packs"], after_table, identity)
    _require(table == after_table, "the outer entry table changed")
    _require(before["span_size"] == after["span_size"],
             "the chunk's fixed span changed size")
    _require(before["span"][:CHUNK_HEADER] == after["span"][:CHUNK_HEADER],
             "the chunk's 0x20 wrapper changed; the in-place decode scratch "
             "word at +0x14 must stay at its retail value")

    expected = before["system_bytes"] + before["video_bytes"]
    source_decoded, source_consumed = decompress(before["span"][CHUNK_HEADER:], expected)
    output_decoded, output_consumed = decompress(after["span"][CHUNK_HEADER:], expected)
    _require(len(output_decoded) == expected,
             "the patched chunk decodes to %d bytes, not %d"
             % (len(output_decoded), expected))
    _require(output_consumed <= before["stored"],
             "the patched stream consumes %d of a %d-byte stored body"
             % (output_consumed, before["stored"]))
    _require(_sha(source_decoded[:before["system_bytes"]])
             == identity["system_sha256"],
             "the source scene differs from the catalogued one")

    # Rebuild the expected buffer from the source plus the recipe alone.
    rebuilt = bytearray(source_decoded)
    allowed_decoded: List[Tuple[int, int]] = []
    lane_reports = []
    for edit in inputs["edits"]:
        row = edit["row"]
        address = edit["address"]
        lanes = scene_lanes(source_decoded[:before["system_bytes"]],
                            address["s"], address["b"])
        _require(address["l"] < len(lanes),
                 "%s: the source scene has %d position lanes in that batch"
                 % (edit["target_id"], len(lanes)))
        found = lanes[address["l"]]
        lane = found["lane"]
        _require(lane["num"] == row["position"]["vertex_count"],
                 "%s: the source lane holds %d vertices, the catalog says %d"
                 % (edit["target_id"], lane["num"], row["position"]["vertex_count"]))
        _require(lane["data_offset"] == row["position"]["payload"]["offset"]
                 and lane["data_bytes"] == row["position"]["payload"]["size"],
                 "%s: the source lane is not where the catalog says" % edit["target_id"])
        # The same walk over the patched buffer must find the identical
        # structure: same chain, same tags, same UNPACK NUM fields.
        after_lanes = scene_lanes(output_decoded[:after["system_bytes"]],
                                  address["s"], address["b"])
        _require(len(after_lanes) == len(lanes)
                 and after_lanes[address["l"]]["lane"]["num"] == lane["num"]
                 and after_lanes[address["l"]]["lane"]["data_offset"] == lane["data_offset"]
                 and after_lanes[address["l"]]["chain_start"] == found["chain_start"]
                 and after_lanes[address["l"]]["chain_end"] == found["chain_end"]
                 and after_lanes[address["l"]]["tags"] == found["tags"]
                 and after_lanes[address["l"]]["unpacks"] == found["unpacks"],
                 "%s: the patched batch's chain structure or vertex count changed"
                 % edit["target_id"])
        for vertex, triple in enumerate(edit["positions"]):
            at = lane["data_offset"] + vertex * ELEMENT
            struct.pack_into("<3f", rebuilt, at, *triple)
            allowed_decoded.append((at, at + LANE))
        chain = row["batch"]["chain"]
        outside_lane = _chain_bytes_outside_lanes(
            source_decoded, chain["offset"], chain["end_offset"],
            [(l["lane"]["data_offset"], l["lane"]["data_offset"]
              + l["lane"]["data_bytes"]) for l in lanes])
        outside_after = _chain_bytes_outside_lanes(
            output_decoded, chain["offset"], chain["end_offset"],
            [(l["lane"]["data_offset"], l["lane"]["data_offset"]
              + l["lane"]["data_bytes"]) for l in lanes])
        _require(outside_lane == outside_after,
                 "%s: the geometry chain changed outside its position payloads"
                 % edit["target_id"])
        lane_reports.append({
            "target_id": edit["target_id"], "vertex_count": lane["num"],
            "payload_offset": lane["data_offset"],
            "payload_size": lane["data_bytes"],
            "chain_offset": found["chain_start"],
            "chain_end_offset": found["chain_end"],
            "dma_tags": found["tags"], "unpacks": found["unpacks"],
            "before_sha256": _sha(source_decoded[lane["data_offset"]:
                                                 lane["data_offset"] + lane["data_bytes"]]),
            "after_sha256": _sha(output_decoded[lane["data_offset"]:
                                                lane["data_offset"] + lane["data_bytes"]]),
        })

    _require(bytes(rebuilt) == output_decoded,
             "the patched scene is not the source scene with exactly the "
             "recipe's coordinates written into the declared lanes")

    # Independent containment: diff the two decoded buffers directly.
    changed = []
    index = 0
    while index < len(source_decoded):
        if source_decoded[index] == output_decoded[index]:
            index += 1
            continue
        start = index
        while index < len(source_decoded) and source_decoded[index] != output_decoded[index]:
            index += 1
        changed.append((start, index))
    for low, high in changed:
        _require(any(start <= low and high <= end for start, end in allowed_decoded),
                 "decoded bytes at [%d, %d) changed outside every declared "
                 "position lane" % (low, high))
    # The w component of every vertex must be untouched.
    for edit, report in zip(inputs["edits"], lane_reports):
        for vertex in range(report["vertex_count"]):
            at = report["payload_offset"] + vertex * ELEMENT + LANE
            _require(source_decoded[at:at + 4] == output_decoded[at:at + 4],
                     "%s: vertex %d's fourth component changed"
                     % (edit["target_id"], vertex))

    windows = _physical_span(source_layout["packs"], before["virtual_offset"],
                             before["span_size"])
    image = _image_diff(source_iso, output_iso, windows)

    mode = "no_op" if not changed else "patched"
    return {
        "schema": SCHEMA,
        "verdict": "pass",
        "mode": mode,
        "source_iso": os.path.abspath(source_iso),
        "output_iso": os.path.abspath(output_iso),
        "catalog_sha256": inputs["catalog"]["sha256"],
        "recipe_sha256": inputs["recipe"]["sha256"],
        "image": dict(image, file_size=source_layout["file_size"],
                      volume_blocks=source_layout["volume_blocks"],
                      pack_count=len(source_layout["packs"]),
                      pack_extents_unmoved=True,
                      directory_records_unchanged=True),
        "chunk": {
            "virtual_offset": before["virtual_offset"],
            "span_size": before["span_size"],
            "stored_size": before["stored"],
            "system_bytes": before["system_bytes"],
            "video_bytes": before["video_bytes"],
            "wrapper_identical": True,
            "wrapper_scratch_bytes": before["scratch"],
            "source_span_sha256": _sha(before["span"]),
            "output_span_sha256": _sha(after["span"]),
            "source_consumed_bytes": source_consumed,
            "output_consumed_bytes": output_consumed,
            "physical_windows": windows,
        },
        "decoded": {
            "size": expected,
            "source_sha256": _sha(source_decoded),
            "output_sha256": _sha(output_decoded),
            "changed_ranges": len(changed),
            "changed_bytes": sum(high - low for low, high in changed),
            "every_changed_byte_inside_a_declared_lane": True,
            "w_component_preserved": True,
            "matches_recipe_exactly": True,
        },
        "lanes": lane_reports,
        "topology": {
            "vertex_counts_unchanged": True,
            "dma_and_vif_structure_unchanged": True,
            "chain_bytes_outside_position_payloads_unchanged": True,
            "note": "on PS2 the vertex count is the VIF UNPACK NUM field and "
                    "primitives are assembled by the VU1 microprogram the chain "
                    "invokes, so preserving the chain outside the position "
                    "payloads is what preserves the triangle set",
        },
        "claims": {
            "same_count_position_write_back": True,
            "changed_count_or_topology_write_back": False,
            "runtime_visibility_proved": False,
            "hardware_visibility_proved": False,
            "production_ready": False,
        },
    }


def _chain_bytes_outside_lanes(decoded: bytes, start: int, end: int,
                               lanes: Sequence[Tuple[int, int]]) -> bytes:
    """The chain's bytes with every position payload cut out."""
    keep = []
    cursor = start
    for low, high in sorted(lanes):
        low = max(low, start)
        high = min(high, end)
        if low >= high:
            continue
        keep.append(decoded[cursor:low])
        cursor = high
    keep.append(decoded[cursor:end])
    return b"".join(keep)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def selftest() -> int:
    failures = []

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    payload = (bytes(range(256)) * 32) + b"stadium" * 50
    stream = _reference_compress(payload)
    decoded, consumed = decompress(stream, len(payload))
    check(decoded == payload and consumed == len(stream),
          "reference VC-LZ roundtrip (%d bytes, consumed %d of %d)"
          % (len(decoded), consumed, len(stream)))

    numbers = _parse_target_id("nfl2k5ps2/stadium/e1556/c2/s7/b1/l0")
    check(numbers == {"e": 1556, "c": 2, "s": 7, "b": 1, "l": 0},
          "target id parse %r" % (numbers,))
    for bad in ("nfl2k5/stadium/e1/c1/s1/b1/l1", "nfl2k5ps2/stadium/e1/c1/s1/b1",
                "nfl2k5ps2/stadium/eX/c1/s1/b1/l1"):
        try:
            _parse_target_id(bad)
        except VerifyError:
            pass
        else:
            failures.append("target id %r should have been refused" % bad)

    kept = _chain_bytes_outside_lanes(bytes(range(64)), 0, 64, [(16, 32)])
    check(kept == bytes(range(16)) + bytes(range(32, 64)), "chain cut-out")

    for failure in failures:
        sys.stderr.write("FAIL: %s\n" % failure)
    if failures:
        return 1
    print("NFL2K5_PS2_STADIUM_POSITION_VERIFY_SELFTEST_PASS checks=%d" % 6)
    return 0


def _reference_compress(data: bytes, offset_bits: int = 12) -> bytes:
    """A literal-only VC-LZ stream: enough to exercise the decoder's framing."""
    out = bytearray(struct.pack("<II", len(data), 1) + bytes([offset_bits]))
    for group in range(0, len(data), 8):
        out.append(0)
        out.extend(data[group:group + 8])
    return bytes(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source-iso")
    parser.add_argument("--output-iso")
    parser.add_argument("--catalog")
    parser.add_argument("--recipe")
    parser.add_argument("--report")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    for name in ("source_iso", "output_iso", "catalog", "recipe"):
        if not getattr(args, name):
            parser.error("--%s is required unless --selftest is given"
                         % name.replace("_", "-"))

    report = verify(args.source_iso, args.output_iso, args.catalog, args.recipe)
    if args.report:
        with open(args.report, "xb") as handle:
            handle.write((json.dumps(report, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n").encode("utf-8"))
    print("NFL2K5_PS2_STADIUM_POSITION_VERIFY_PASS mode=%s lanes=%d vertices=%d "
          "image_changed=%d decoded_changed=%d wrapper_identical=true runtime=false"
          % (report["mode"], len(report["lanes"]),
             sum(lane["vertex_count"] for lane in report["lanes"]),
             report["image"]["changed_bytes"],
             report["decoded"]["changed_bytes"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerifyError, struct.error) as exc:
        raise SystemExit("error: %s" % exc) from exc
