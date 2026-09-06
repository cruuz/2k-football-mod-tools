#!/usr/bin/env python3
"""Catalogue the editable position lanes in ESPN NFL 2K5 PS2 stadium scenes.

This is the PlayStation 2 analogue of ``tools/nfl_stadium_static_target_catalog.py``
and it is **not** a port of it.  The two discs share a container, a compressor
and a pointer encoding; below the SCNE table level they share nothing.

WHAT THE XBOX CATALOGUE ASSUMES, AND WHY NONE OF IT HOLDS HERE
--------------------------------------------------------------
The Xbox shape record is 0x100 bytes and describes a GPU vertex buffer::

    +0x4C  u16 vertex_count
    +0x70  submesh table pointer (0x80-byte records, NV2A push buffer each)
    +0x84  16 x u32 vertex input descriptors (register 0 = position)
    +0xC4  8  x u16 stream strides
    +0xD4  8  x s32 stream pointers

Register 0 resolves to a flat contiguous ``vertex_count * 12`` FLOAT3 run, so
the Xbox writer is one ``bytes`` splice, and topology is a separate NV2A
command stream it preserves word for word.

The PS2 shape record is 0x70 bytes and has **no vertex count, no stream table,
no submesh table and no push buffer**.  Geometry is a PlayStation 2 DMA chain:
VIF codes that UNPACK quantised attribute lanes into VU1 memory, ending in an
MSCAL that runs the microprogram which emits the primitives.  Vertex count is
not stored as a field at all -- it is the ``NUM`` field of the UNPACK codes.

WHAT THIS TOOL ESTABLISHED ON THE RETAIL DISC (SLUS-20919)
----------------------------------------------------------
Read against ``/VC_20919`` entry 1556 chunk 2, scene ``stadium`` (101 shapes,
654 batches, 11,494 vertices), then generalised and re-checked per target::

    scene descriptor  +0x2C u32 shape count, +0x30 -> shape table, stride 0x70
    shape   +0x30  3 x f32 bounding-sphere centre (+0x3C is 1.0)
            +0x40  s32 -> UTF-16LE shape name
            +0x4C  f32 bounding-sphere radius
            +0x68  u32 batch count
            +0x6C  s32 -> batch table, stride 0x18
    batch   +0x00  s32 -> DMA/VIF chain
            +0x04  u32 byte size of the chain's FIRST DMA packet
    chain   qword-aligned DMA tags: 8-byte tag then two VIF codes; the tag's
            low u16 is QWC and bits 28..30 are the tag id; ids 0 (refe) and
            7 (end) terminate.  QWC qwords of VIF data follow each tag.
    VIF     cmd = byte 3; >= 0x60 is UNPACK, where vn = (cmd >> 2) & 3 and
            vl = cmd & 3 give the element shape, NUM (byte 2, 0 means 256) the
            element count and IMM the VU address.
    position lane = the single ``UNPACK V4_32`` with NUM > 1 in the batch:
            NUM elements of four little-endian binary32 (x, y, z, w).

The position claim is not a guess.  Every one of the 11,494 decoded vertices
lies inside its own shape's declared bounding sphere, with a maximum
distance/radius ratio of exactly 1.00000 -- the spheres are tight fits round
these exact points, which no unrelated lane would produce.

CONSEQUENCES FOR A WRITER
-------------------------
* The lane is **strided, not contiguous**: 12 editable bytes every 16.  The
  ``w`` component is preserved per vertex, so a PS2 writer cannot be one
  splice the way the Xbox writer is.
* "Same count" means every VIF ``NUM`` field is untouched, because that is
  where the count lives.
* "Same topology" means the whole chain outside the position payloads --
  every DMA tag, every VIF code, the index/header lane, colours, UVs, the
  MSCAL -- is preserved byte for byte.

RETAIL-FREE BY CONSTRUCTION
---------------------------
Only ``system_bytes`` of each SCNE is decoded, exactly as the disc inventory
does, so pixel and sample payload is never read.  Outputs carry names,
offsets, counts, strides and digests.  No coordinate ever reaches the JSON;
``--measure-fit`` additionally decodes the whole stream to measure how many
bytes the retail packer left spare, and still emits only counts and digests.

USAGE
-----
    python3 tools/nfl2k5_ps2_stadium_target_catalog.py --iso <SLUS-20919.iso> \\
        --json reports/gameplay_tuning/nfl2k5_ps2_stadium_target_catalog.v1.json \\
        [--entry N[:CHUNK] ...] [--scan] [--limit N] [--measure-fit]
    python3 tools/nfl2k5_ps2_stadium_target_catalog.py --selftest

Python 3.9 compatible, standard library only.  Imports its siblings
``ps2_iso9660`` and ``nfl2k5_ps2_disc_inventory`` with its own directory placed
on ``sys.path`` first, because the installed Windows runtime does not add it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps2_iso9660 as iso  # noqa: E402
import nfl2k5_ps2_disc_inventory as inv  # noqa: E402

__all__ = [
    "SCHEMA", "CatalogError", "VIF_UNPACK_ELEMENT_BYTES", "parse_chain",
    "shape_records", "batch_targets", "catalog", "selftest", "main",
]

SCHEMA = "nfl2k5_ps2_stadium_target_catalog/v1"

SHAPE_STRIDE = 0x70
BATCH_STRIDE = 0x18
SCENE_SHAPE_COUNT = 0x2C
SCENE_SHAPE_POINTER = 0x30

SHAPE_CENTRE = 0x30
SHAPE_NAME_POINTER = 0x40
SHAPE_RADIUS = 0x4C
SHAPE_BATCH_COUNT = 0x68
SHAPE_BATCH_POINTER = 0x6C

BATCH_CHAIN_POINTER = 0x00
BATCH_FIRST_PACKET_BYTES = 0x04

# VIF UNPACK element size, keyed by (vn, vl).  vn selects S/V2/V3/V4 and vl
# selects 32/16/8/5-bit components; (3, 3) is the packed 16-bit V4_5 colour.
VIF_UNPACK_ELEMENT_BYTES = {
    (0, 0): 4, (0, 1): 2, (0, 2): 1,
    (1, 0): 8, (1, 1): 4, (1, 2): 2,
    (2, 0): 12, (2, 1): 6, (2, 2): 3,
    (3, 0): 16, (3, 1): 8, (3, 2): 4, (3, 3): 2,
}
VIF_VN = {0: "S", 1: "V2", 2: "V3", 3: "V4"}
VIF_VL = {0: "32", 1: "16", 2: "8", 3: "5"}
# Non-UNPACK VIF commands and the extra immediate bytes each consumes.
VIF_COMMANDS = {
    0x00: ("NOP", 0), 0x01: ("STCYCL", 0), 0x02: ("OFFSET", 0),
    0x03: ("BASE", 0), 0x04: ("ITOP", 0), 0x05: ("STMOD", 0),
    0x06: ("MSKPATH3", 0), 0x07: ("MARK", 0), 0x10: ("FLUSHE", 0),
    0x11: ("FLUSH", 0), 0x13: ("FLUSHA", 0), 0x14: ("MSCAL", 0),
    0x15: ("MSCNT", 0), 0x17: ("MSCALF", 0), 0x20: ("STMASK", 4),
    0x30: ("STROW", 16), 0x31: ("STCOL", 16),
}
DMA_TAG_IDS = {0: "refe", 1: "cnt", 2: "next", 3: "ref", 4: "refs",
               5: "call", 6: "ret", 7: "end"}
DMA_TERMINATORS = (0, 7)
MAX_DMA_TAGS = 4096

POSITION_UNPACK = "V4_32"
POSITION_ELEMENT_BYTES = 16
POSITION_LANE_BYTES = 12          # x, y, z; w is preserved
BOUNDING_SPHERE_TOLERANCE = 1.0001

MAX_TARGETS = 200_000


class CatalogError(ValueError):
    """The disc, a scene, or a target's structure is not what this tool accepts."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise CatalogError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _span(data: bytes, offset: int, size: int, what: str) -> dict:
    _require(offset is not None and 0 <= offset and size >= 0
             and offset + size <= len(data), "%s span is outside the buffer" % what)
    return {"offset": offset, "end_offset": offset + size, "size": size,
            "sha256": _sha(data[offset:offset + size])}


# ---------------------------------------------------------------------------
# The PS2 geometry chain
# ---------------------------------------------------------------------------

def _parse_vif(system: bytes, start: int, size: int, unpacks: List[dict],
               commands: Dict[str, int]) -> Optional[str]:
    """Decode the VIF codes filling one transfer block.  None on success."""
    position = start
    end = start + size
    while position + 4 <= end:
        code = struct.unpack_from("<I", system, position)[0]
        command = (code >> 24) & 0xFF
        num = (code >> 16) & 0xFF
        immediate = code & 0xFFFF
        position += 4
        if command >= 0x60:
            vn = (command >> 2) & 3
            vl = command & 3
            element = VIF_UNPACK_ELEMENT_BYTES.get((vn, vl))
            if element is None:
                return "unsupported UNPACK command 0x%02X at 0x%x" % (command, position - 4)
            count = num if num else 256
            payload = count * element
            if position + payload > end:
                return "UNPACK payload at 0x%x runs past its transfer block" % (position - 4)
            unpacks.append({
                "code_offset": position - 4,
                "kind": "%s_%s" % (VIF_VN[vn], VIF_VL[vl]),
                "masked": bool((command >> 4) & 1),
                "num": count,
                "element_bytes": element,
                "vu_address": immediate & 0x3FF,
                "unsigned": bool((immediate >> 14) & 1),
                "data_offset": position,
                "data_bytes": payload,
            })
            commands["UNPACK"] = commands.get("UNPACK", 0) + 1
            position = (position + payload + 3) & ~3
            continue
        known = VIF_COMMANDS.get(command)
        if known is None:
            return "unknown VIF command 0x%02X at 0x%x" % (command, position - 4)
        name, extra = known
        commands[name] = commands.get(name, 0) + 1
        position += extra
    return None


def parse_chain(system: bytes, start: int) -> dict:
    """Walk one PS2 DMA/VIF geometry chain from *start* to its terminator.

    Returns a dict with ``unpacks``, ``tags``, ``commands``, ``end_offset`` and
    ``error``.  ``error`` is None only when the chain terminated cleanly with
    every VIF code understood and every payload inside ``system``.
    """
    unpacks: List[dict] = []
    commands: Dict[str, int] = {}
    tags: List[dict] = []
    position = start
    limit = len(system)
    if start is None or start < 0 or start + 16 > limit or start % 4:
        return {"unpacks": unpacks, "tags": tags, "commands": commands,
                "end_offset": start, "error": "chain pointer is not a bounded qword"}
    while position + 16 <= limit:
        low = struct.unpack_from("<I", system, position)[0]
        qwc = low & 0xFFFF
        identifier = (low >> 28) & 7
        tags.append({"offset": position, "id": identifier,
                     "id_name": DMA_TAG_IDS[identifier], "qwc": qwc})
        error = _parse_vif(system, position + 8, 8, unpacks, commands)
        if error is not None:
            return {"unpacks": unpacks, "tags": tags, "commands": commands,
                    "end_offset": position, "error": error}
        position += 16
        if qwc:
            if position + qwc * 16 > limit:
                return {"unpacks": unpacks, "tags": tags, "commands": commands,
                        "end_offset": position,
                        "error": "DMA tag QWC %d runs past the system buffer" % qwc}
            error = _parse_vif(system, position, qwc * 16, unpacks, commands)
            if error is not None:
                return {"unpacks": unpacks, "tags": tags, "commands": commands,
                        "end_offset": position, "error": error}
            position += qwc * 16
        if identifier in DMA_TERMINATORS:
            return {"unpacks": unpacks, "tags": tags, "commands": commands,
                    "end_offset": position, "error": None}
        if len(tags) > MAX_DMA_TAGS:
            return {"unpacks": unpacks, "tags": tags, "commands": commands,
                    "end_offset": position, "error": "chain exceeded %d DMA tags" % MAX_DMA_TAGS}
    return {"unpacks": unpacks, "tags": tags, "commands": commands,
            "end_offset": position, "error": "chain reached the system buffer end unterminated"}


def position_lanes(chain: dict) -> List[dict]:
    """Every multi-vertex V4_32 UNPACK in the chain, in transfer order.

    A batch's chain may carry several DMA packets, each unpacking its own mesh
    piece, so a batch owns zero or more independent position lanes rather than
    exactly one.  Each is a separate editable target with its own count.
    """
    return [u for u in chain["unpacks"]
            if u["kind"] == POSITION_UNPACK and u["num"] > 1]


def _bounds_check(system: bytes, lane: dict, centre: Sequence[float],
                  radius: float) -> Tuple[bool, float]:
    """Do every decoded xyz lie inside the shape's declared bounding sphere?"""
    if not (radius > 0.0):
        return False, float("inf")
    worst = 0.0
    for index in range(lane["num"]):
        base = lane["data_offset"] + index * POSITION_ELEMENT_BYTES
        x, y, z = struct.unpack_from("<3f", system, base)
        distance = ((x - centre[0]) ** 2 + (y - centre[1]) ** 2
                    + (z - centre[2]) ** 2) ** 0.5
        ratio = distance / radius
        if ratio > worst:
            worst = ratio
    return worst <= BOUNDING_SPHERE_TOLERANCE, worst


def shape_records(system: bytes) -> List[dict]:
    """Every shape in a decoded SCNE system buffer, structure only."""
    limit = len(system)
    _require(limit >= 0x18 and system[0x0C:0x10] == b"SCNE",
             "decoded buffer is not an SCNE object")
    descriptor = inv.relative_pointer(system, 0x14, limit)
    _require(descriptor is not None, "SCNE descriptor pointer is null")
    count = inv.u32(system, descriptor + SCENE_SHAPE_COUNT)
    table = inv.relative_pointer(system, descriptor + SCENE_SHAPE_POINTER, limit)
    if not count:
        return []
    _require(table is not None, "shape count %d with a null shape table" % count)
    _require(table + count * SHAPE_STRIDE <= limit,
             "shape table runs past the system buffer")
    shapes = []
    for index in range(count):
        record = table + index * SHAPE_STRIDE
        centre = struct.unpack_from("<3f", system, record + SHAPE_CENTRE)
        shapes.append({
            "index": index,
            "record_offset": record,
            "name": inv.pointer_name(system, record + SHAPE_NAME_POINTER, limit),
            "centre": list(centre),
            "radius": struct.unpack_from("<f", system, record + SHAPE_RADIUS)[0],
            "batch_count": inv.u32(system, record + SHAPE_BATCH_COUNT),
            "batch_table": inv.relative_pointer(
                system, record + SHAPE_BATCH_POINTER, limit),
        })
    return shapes


def batch_targets(system: bytes, shape: dict) -> List[dict]:
    """One entry per geometry batch of *shape*, eligible or not, in order."""
    limit = len(system)
    results = []
    count = shape["batch_count"]
    table = shape["batch_table"]
    if not count:
        return results
    if table is None or table + count * BATCH_STRIDE > limit:
        return [{"index": 0, "eligible": False,
                 "reason": "batch table is null or runs past the system buffer"}]
    for index in range(count):
        descriptor = table + index * BATCH_STRIDE
        chain_start = inv.relative_pointer(
            system, descriptor + BATCH_CHAIN_POINTER, limit)
        first_packet = inv.u32(system, descriptor + BATCH_FIRST_PACKET_BYTES)
        entry = {"index": index, "descriptor_offset": descriptor,
                 "chain_offset": chain_start, "first_packet_bytes": first_packet}
        if chain_start is None:
            entry.update(eligible=False, reason="batch chain pointer is null")
            results.append(entry)
            continue
        chain = parse_chain(system, chain_start)
        entry["dma_tag_count"] = len(chain["tags"])
        entry["unpack_count"] = len(chain["unpacks"])
        entry["vif_command_counts"] = dict(sorted(chain["commands"].items()))
        entry["chain_end_offset"] = chain["end_offset"]
        if chain["error"] is not None:
            entry.update(eligible=False, reason=chain["error"])
            results.append(entry)
            continue
        entry["chain_bytes"] = chain["end_offset"] - chain_start
        # +0x04 matches "16 + first tag QWC * 16" for some batches and not
        # others, so its meaning is recorded and never relied on.
        entry["first_packet_bytes_match_first_tag"] = bool(
            chain["tags"] and 16 + chain["tags"][0]["qwc"] * 16 == first_packet)
        lanes = []
        for ordinal, lane in enumerate(position_lanes(chain)):
            inside, worst = _bounds_check(
                system, lane, shape["centre"], shape["radius"])
            lanes.append({"ordinal": ordinal, "lane": lane,
                          "bounding_sphere_ratio_max": worst,
                          "eligible": inside,
                          "reason": "" if inside else
                          "a decoded position escapes the shape bounding sphere "
                          "(max ratio %.5f)" % worst})
        entry["lanes"] = lanes
        if not lanes:
            entry.update(eligible=False, reason="batch has no multi-vertex V4_32 UNPACK")
        else:
            entry["eligible"] = any(item["eligible"] for item in lanes)
            entry["reason"] = "" if entry["eligible"] else lanes[0]["reason"]
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Disc traversal
# ---------------------------------------------------------------------------

def _chunk_headers(archive, base: int, entry_size: int) -> List[dict]:
    """Every bounded resource chunk in one outer entry, headers only."""
    chunks = []
    offset = 0
    index = 0
    while entry_size - offset >= inv.CHUNK_HEADER_SIZE:
        header = archive.read(base + offset, inv.CHUNK_HEADER_SIZE)
        fourcc = header[:4]
        stored, system_bytes, video_bytes, magic = struct.unpack_from("<4I", header, 4)
        if not (inv.printable_fourcc(fourcc) and stored
                and offset + inv.CHUNK_HEADER_SIZE + stored <= entry_size):
            successor = inv.find_after_zero_padding(archive, base, entry_size, offset)
            if successor is None:
                break
            offset = successor
            continue
        chunks.append({"index": index, "fourcc": fourcc.decode("ascii"),
                       "offset": offset, "stored": stored,
                       "system_bytes": system_bytes, "video_bytes": video_bytes,
                       "compressed": magic == inv.COMPRESSED_SENTINEL,
                       "header": header})
        offset += inv.CHUNK_HEADER_SIZE + stored
        index += 1
    return chunks


def _read_system(archive, base: int, chunk: dict) -> bytes:
    """The decoded system buffer of one chunk, and never more than that."""
    want = chunk["system_bytes"]
    _require(0 < want <= inv.METADATA_CAP * 64,
             "chunk declares %d system bytes" % want)
    body_at = base + chunk["offset"] + inv.CHUNK_HEADER_SIZE
    if not chunk["compressed"]:
        return archive.read(body_at, min(want, chunk["stored"]))
    need = 10 + want + (want + 7) // 8 + 16
    body = archive.read(body_at, min(chunk["stored"], need))
    return inv.decompress_prefix(body, want)


def _scene_name(system: bytes) -> Optional[str]:
    if len(system) < 0x18 or system[0x0C:0x10] != b"SCNE":
        return None
    return inv.pointer_name(system, 0x10, len(system))


def _measure_fit(archive, base: int, chunk: dict) -> dict:
    """How many bytes the retail packer left spare inside the stored body.

    Needs the whole stream, so it is opt-in.  Emits counts and digests only.
    """
    body = archive.read(base + chunk["offset"] + inv.CHUNK_HEADER_SIZE, chunk["stored"])
    if not chunk["compressed"]:
        return {"compressed": False, "stored_size": chunk["stored"],
                "retail_consumed_bytes": chunk["stored"], "headroom_bytes": 0,
                "opaque_tail_bytes": 0, "opaque_tail_sha256": _sha(b"")}
    declared = struct.unpack_from("<I", body, 0)[0]
    decoded = inv.decompress_prefix(body, declared)
    _require(len(decoded) == chunk["system_bytes"] + chunk["video_bytes"],
             "decoded size disagrees with the chunk wrapper")
    # Re-run the decoder counting the bytes it actually consumes.
    consumed = _consumed_bytes(body, declared)
    tail = body[consumed:]
    return {"compressed": True, "stored_size": chunk["stored"],
            "stream_tag": struct.unpack_from("<I", body, 4)[0],
            "offset_bits": body[8],
            "retail_consumed_bytes": consumed,
            "headroom_bytes": chunk["stored"] - consumed,
            "opaque_tail_bytes": len(tail), "opaque_tail_sha256": _sha(tail),
            "decoded_size": len(decoded),
            "decoded_sha256": _sha(decoded)}


def _consumed_bytes(stream: bytes, output_size: int) -> int:
    """Compressed bytes the VC-LZ decoder reads to emit *output_size* bytes."""
    offset_bits = stream[8]
    _require(1 <= offset_bits <= 15, "invalid offset bit count %d" % offset_bits)
    length_bits = 16 - offset_bits
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << length_bits) - 1
    source = 9
    flags = stream[source]
    source += 1
    mask = 1
    produced = 0
    while produced < output_size:
        if flags & mask:
            code = struct.unpack_from("<H", stream, source)[0]
            source += 2
            produced += ((code >> offset_bits) & length_mask) + 3
        else:
            source += 1
            produced += 1
        mask = (mask << 1) & 0xFF
        if mask == 0 and produced < output_size:
            flags = stream[source]
            source += 1
            mask = 1
    return source


def _target_id(entry_index: int, chunk_index: int, shape_index: int,
               batch_index: int, lane_ordinal: int) -> str:
    return "nfl2k5ps2/stadium/e%d/c%d/s%d/b%d/l%d" % (
        entry_index, chunk_index, shape_index, batch_index, lane_ordinal)


def _scene_targets(system: bytes, entry_index: int, name_id: int,
                   chunk: dict, fit: Optional[dict],
                   scene_index: int = 0) -> Tuple[List[dict], dict]:
    """Every catalogued target of one scene, plus that scene's tallies."""
    scene_name = _scene_name(system)
    identity = {
        "entry_index": entry_index,
        "entry_name_id": "0x%08x" % name_id,
        "chunk_index": chunk["index"],
        "chunk_offset": chunk["offset"],
        "scene_name": scene_name,
        "system_bytes": chunk["system_bytes"],
        "video_bytes": chunk["video_bytes"],
        "system_sha256": _sha(system),
    }
    tally = {"shapes": 0, "batches": 0, "lanes": 0, "eligible": 0,
             "vertices": 0, "refusals": {}}
    targets: List[dict] = []
    for shape in shape_records(system):
        tally["shapes"] += 1
        for batch in batch_targets(system, shape):
            tally["batches"] += 1
            if not batch.get("lanes"):
                reason = batch.get("reason", "unclassified")
                tally["refusals"][reason] = tally["refusals"].get(reason, 0) + 1
                continue
            for item in batch["lanes"]:
                tally["lanes"] += 1
                if not item["eligible"]:
                    tally["refusals"][item["reason"]] = \
                        tally["refusals"].get(item["reason"], 0) + 1
                    continue
                lane = item["lane"]
                tally["eligible"] += 1
                tally["vertices"] += lane["num"]
                targets.append({
                    "target_id": _target_id(entry_index, chunk["index"],
                                            shape["index"], batch["index"],
                                            item["ordinal"]),
                    "scene_index": scene_index,
                    "shape": {
                        "index": shape["index"],
                        "name": shape["name"],
                        "record_offset": shape["record_offset"],
                        "batch_count": shape["batch_count"],
                        "bounding_radius": shape["radius"],
                    },
                    "batch": {
                        "index": batch["index"],
                        "descriptor_offset": batch["descriptor_offset"],
                        "chain": _span(system, batch["chain_offset"],
                                       batch["chain_bytes"], "geometry chain"),
                        "dma_tag_count": batch["dma_tag_count"],
                        "unpack_count": batch["unpack_count"],
                        "field_04": batch["first_packet_bytes"],
                        "field_04_matches_first_tag_packet_size":
                            batch["first_packet_bytes_match_first_tag"],
                        "position_lane_count": len(batch["lanes"]),
                    },
                    "position": {
                        "lane_ordinal_within_batch": item["ordinal"],
                        "vertex_count": lane["num"],
                        "unpack_code_offset": lane["code_offset"],
                        "vu_address": lane["vu_address"],
                        "payload": _span(system, lane["data_offset"],
                                         lane["data_bytes"], "position payload"),
                    },
                    "max_distance_over_radius":
                        item["bounding_sphere_ratio_max"],
                    "eligible": True,
                })
    return targets, tally


def catalog(iso_path: str, entries: Optional[Sequence[Tuple[int, Optional[int]]]] = None,
            scan: bool = False, limit: Optional[int] = None,
            measure_fit: bool = False, scene_name: str = "stadium") -> dict:
    """Build the catalogue from a user's own ISO, read-only."""
    image = iso.open_image(iso_path)
    identity = inv.image_identity(image, False)
    packs = inv.discover_packs(image)
    archive = inv.VirtualPacks(str(iso_path), packs)
    archive.open()
    try:
        outer, table = inv.read_outer_table(archive)
        wanted: List[Tuple[int, Optional[int]]] = list(entries or ())
        if scan or not wanted:
            wanted = [(index, None) for index in range(len(table))]
        targets: List[dict] = []
        scenes: List[dict] = []
        totals = {"shapes": 0, "batches": 0, "lanes": 0,
                  "eligible": 0, "vertices": 0}
        refusals: Dict[str, int] = {}
        for entry_index, want_chunk in wanted:
            if limit is not None and len(scenes) >= limit:
                break
            if not 0 <= entry_index < len(table):
                raise CatalogError("outer entry %d is outside the table" % entry_index)
            name_id, entry_size, offset_blocks = table[entry_index]
            base = offset_blocks * inv.ALIGNMENT
            for chunk in _chunk_headers(archive, base, entry_size):
                if chunk["fourcc"] != "SCNE" or not chunk["system_bytes"]:
                    continue
                if want_chunk is not None and chunk["index"] != want_chunk:
                    continue
                try:
                    system = _read_system(archive, base, chunk)
                except (inv.InventoryError, CatalogError, struct.error):
                    continue
                if _scene_name(system) != scene_name:
                    continue
                fit = _measure_fit(archive, base, chunk) if measure_fit else None
                found, tally = _scene_targets(system, entry_index, name_id,
                                              chunk, fit, len(scenes))
                targets.extend(found)
                for key in ("shapes", "batches", "lanes", "eligible", "vertices"):
                    totals[key] += tally[key]
                for reason, count in tally["refusals"].items():
                    refusals[reason] = refusals.get(reason, 0) + count
                scenes.append({
                    "scene_index": len(scenes),
                    "identity": {
                        "entry_index": entry_index,
                        "entry_name_id": "0x%08x" % name_id,
                        "chunk_index": chunk["index"],
                        "chunk_offset": chunk["offset"],
                        "scene_name": scene_name,
                        "system_bytes": chunk["system_bytes"],
                        "video_bytes": chunk["video_bytes"],
                        "system_sha256": _sha(system),
                    },
                    "stored_size": chunk["stored"],
                    "shapes": tally["shapes"],
                    "batches": tally["batches"],
                    "position_lanes": tally["lanes"],
                    "eligible_lanes": tally["eligible"],
                    "vertices": tally["vertices"],
                    "fixed_allocation": fit or {"measured": False},
                })
                if limit is not None and len(scenes) >= limit:
                    break
        _require(len(targets) <= MAX_TARGETS,
                 "%d targets is past the %d sanity cap" % (len(targets), MAX_TARGETS))
        # Several batch descriptors may point at the same DMA chain, so the
        # same position lane can be reachable under more than one target_id.
        # Editing two aliases of one lane at once is refused by the writer, so
        # the sharing is recorded here rather than discovered there.
        sharing: Dict[Tuple[int, int, int], int] = {}
        for row in targets:
            payload = row["position"]["payload"]
            key = (row["scene_index"], payload["offset"], payload["size"])
            sharing[key] = sharing.get(key, 0) + 1
        for row in targets:
            payload = row["position"]["payload"]
            key = (row["scene_index"], payload["offset"], payload["size"])
            row["payload_span_target_count"] = sharing[key]
        distinct_spans = len(sharing)
        aliased = sum(1 for row in targets if row["payload_span_target_count"] > 1)
    finally:
        archive.close()
    return {
        "schema": SCHEMA,
        "title": "ESPN NFL 2K5 (PS2) stadium position-lane targets",
        "scope": (
            "One target is one geometry batch of one stadium SCNE shape: the "
            "single multi-vertex VIF UNPACK V4_32 lane inside that batch's DMA "
            "chain. Vertex counts, every other UNPACK, every DMA tag and the "
            "VU1 microprogram invocation are outside the editable boundary."
        ),
        "source": {
            "serial": identity["serial"],
            "expected_serial": identity["expected_serial"],
            "serial_matches": identity["serial_matches"],
            "boot_sha256": identity["boot_sha256"],
            "retail_boot_elf": identity["retail_boot_elf"],
            "pack_directory": inv.PACK_DIRECTORY,
            "pack_count": len(packs),
            "outer_entry_count": outer["entry_count"],
        },
        "format": {
            "derived_from": "the retail disc, not from the Xbox catalogue",
            "shape_record_stride": SHAPE_STRIDE,
            "batch_record_stride": BATCH_STRIDE,
            "shape_fields": {
                "bounding_centre": "3*f32le at +0x30",
                "name_pointer": "s32le one-based self-relative at +0x40",
                "bounding_radius": "f32le at +0x4C",
                "batch_count": "u32le at +0x68",
                "batch_table_pointer": "s32le one-based self-relative at +0x6C",
            },
            "batch_fields": {
                "chain_pointer": "s32le one-based self-relative at +0x00",
                "first_packet_bytes": "u32le at +0x04",
            },
            "chain": {
                "unit": "128-bit DMA tag qword: 64-bit tag then two 32-bit VIF codes",
                "qwc": "the low u16 of the tag's low word",
                "tag_id": "bits 28..30 of the tag's low word",
                "terminators": [DMA_TAG_IDS[i] for i in DMA_TERMINATORS],
                "unpack_decode": "cmd>=0x60; vn=(cmd>>2)&3, vl=cmd&3, NUM=byte 2 "
                                 "(0 means 256), the low 10 bits of IMM are the VU address",
            },
            "differences_from_xbox": [
                "the Xbox shape record is 0x100 bytes and the PS2 record is 0x70",
                "PS2 has no vertex_count field; the count is the VIF UNPACK NUM",
                "PS2 has no vertex stream table, no stream strides and no stream pointers",
                "PS2 has no submesh table and no NV2A push buffer; primitives are "
                "assembled by a VU1 microprogram invoked with MSCAL",
                "the Xbox position lane is a contiguous FLOAT3 run of stride 12; "
                "the PS2 lane is strided FLOAT4, 12 editable bytes every 16",
                "PS2 carries colour (V4_5) and UV (V2_16) lanes inline in the same "
                "DMA chain rather than in separate vertex streams",
            ],
        },
        "target_common": {
            "position_encoding": "vif_unpack_v4_32",
            "component_storage": "4*f32le (x, y, z, w)",
            "element_stride": POSITION_ELEMENT_BYTES,
            "lane_offset_within_element": 0,
            "lane_size": POSITION_LANE_BYTES,
            "w_component_preserved": True,
            "payload_span_sharing": "several batch descriptors may point at the "
                                    "same DMA chain, so one lane can be reachable "
                                    "under more than one target_id; "
                                    "payload_span_target_count says how many, and "
                                    "the writer refuses a recipe that edits two "
                                    "aliases of one lane",
            "topology": {
                "count_lives_in": "VIF UNPACK NUM fields",
                "primitive_assembly": "VU1 microprogram invoked by MSCAL",
                "index_or_strip_data_decoded": False,
                "writer_policy": "preserve every chain byte outside the position "
                                 "payload, including all NUM fields",
            },
            "eligibility": {
                "mechanically_same_count_float_position": True,
                "reason": "the batch's DMA chain terminates cleanly with only "
                          "known VIF codes and every position the lane decodes "
                          "lies inside the shape's declared bounding sphere",
                "semantic_ownership_proved": False,
                "runtime_visibility_proved": False,
                "hardware_visibility_proved": False,
                "production_ready": False,
            },
        },
        "summary": {
            "scenes": len(scenes),
            "shapes": totals["shapes"],
            "batches": totals["batches"],
            "position_lanes": totals["lanes"],
            "eligible_lanes": totals["eligible"],
            "target_count": len(targets),
            "distinct_position_spans": distinct_spans,
            "targets_sharing_a_span_with_another": aliased,
            "vertex_total": totals["vertices"],
            "refusals": dict(sorted(refusals.items())),
        },
        "data_policy": {
            "contains_retail_geometry_or_pixel_bytes": False,
            "contains_position_values": False,
            "decoded_video_payload": bool(measure_fit),
            "emitted": "names, offsets, counts, strides and digests only",
        },
        "claim_flags": {
            "ps2_vertex_payload_layout_established_on_disc": True,
            "layout_ported_from_xbox": False,
            "same_count_position_writer_implemented": True,
            "changed_count_or_topology_write_back": False,
            "runtime_visibility_proved": False,
            "hardware_visibility_proved": False,
            "production_ready": False,
        },
        "scenes": scenes,
        "targets": targets,
    }


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Self-test: a synthetic scene, no game data
# ---------------------------------------------------------------------------

def _pointer(field: int, target: int) -> bytes:
    return struct.pack("<i", target - field + 1)


def build_synthetic_scene(vertex_counts: Sequence[int] = (3, 5),
                          broken_batch: bool = False,
                          duplicate_lane: bool = False) -> bytes:
    """A minimal SCNE system buffer with one shape and N geometry batches."""
    name = "stadium\0".encode("utf-16le")
    shape_name = "group01\0".encode("utf-16le")
    header = bytearray(0x18)
    header[0x0C:0x10] = b"SCNE"
    body = bytearray(header)

    def place(blob: bytes, align: int = 4) -> int:
        while len(body) % align:
            body.append(0)
        at = len(body)
        body.extend(blob)
        return at

    name_at = place(name, 2)
    shape_name_at = place(shape_name, 2)
    chains = []
    for count in vertex_counts:
        chain = bytearray()
        payload = bytearray()
        for index in range(count):
            payload.extend(struct.pack("<4f", 10.0 + index, 20.0, 30.0 - index, 0.0))
        vif = bytearray()
        vif.extend(struct.pack("<I", 0x01000103))                     # STCYCL
        vif.extend(struct.pack("<I", 0x6C000000 | (count << 16) | 0x4133))
        vif.extend(payload)
        if duplicate_lane:
            vif.extend(struct.pack("<I", 0x6C000000 | (count << 16) | 0x4155))
            vif.extend(payload)
        if broken_batch:
            vif.extend(struct.pack("<I", 0x3F000000))                 # unknown VIF
        else:
            vif.extend(struct.pack("<I", 0x14000000))                 # MSCAL
        while len(vif) % 16:
            vif.extend(struct.pack("<I", 0x00000000))                 # NOP padding
        qwc = len(vif) // 16
        chain.extend(struct.pack("<II", (1 << 28) | qwc, 0))          # cnt tag
        chain.extend(struct.pack("<II", 0, 0))                        # two NOP vifcodes
        chain.extend(vif)
        chain.extend(struct.pack("<II", 0, 0))                        # refe tag
        chain.extend(struct.pack("<II", 0, 0))
        chains.append((place(bytes(chain), 16), 16 + qwc * 16))

    batch_table = len(body)
    for _ in vertex_counts:
        body.extend(bytes(BATCH_STRIDE))
    for index, (chain_at, first_packet) in enumerate(chains):
        record = batch_table + index * BATCH_STRIDE
        body[record:record + 4] = _pointer(record, chain_at)
        struct.pack_into("<I", body, record + 4, first_packet)

    shape_at = place(bytes(SHAPE_STRIDE), 16)
    struct.pack_into("<3f", body, shape_at + SHAPE_CENTRE, 11.0, 20.0, 29.0)
    body[shape_at + SHAPE_NAME_POINTER:shape_at + SHAPE_NAME_POINTER + 4] = \
        _pointer(shape_at + SHAPE_NAME_POINTER, shape_name_at)
    struct.pack_into("<f", body, shape_at + SHAPE_RADIUS, 1000.0)
    struct.pack_into("<I", body, shape_at + SHAPE_BATCH_COUNT, len(vertex_counts))
    body[shape_at + SHAPE_BATCH_POINTER:shape_at + SHAPE_BATCH_POINTER + 4] = \
        _pointer(shape_at + SHAPE_BATCH_POINTER, batch_table)

    descriptor = place(bytes(0x54), 16)
    struct.pack_into("<I", body, descriptor + SCENE_SHAPE_COUNT, 1)
    body[descriptor + SCENE_SHAPE_POINTER:descriptor + SCENE_SHAPE_POINTER + 4] = \
        _pointer(descriptor + SCENE_SHAPE_POINTER, shape_at)

    body[0x10:0x14] = _pointer(0x10, name_at)
    body[0x14:0x18] = _pointer(0x14, descriptor)
    return bytes(body)


def selftest() -> int:
    failures = []

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    system = build_synthetic_scene((3, 5))
    check(_scene_name(system) == "stadium", "synthetic scene name")
    shapes = shape_records(system)
    check(len(shapes) == 1 and shapes[0]["name"] == "group01",
          "synthetic shape table %r" % [s["name"] for s in shapes])
    batches = batch_targets(system, shapes[0])
    check(len(batches) == 2, "synthetic batch count %d" % len(batches))
    check(all(b.get("eligible") for b in batches),
          "synthetic batches not eligible: %r" % [b.get("reason") for b in batches])
    check([b["lanes"][0]["lane"]["num"] for b in batches] == [3, 5],
          "synthetic vertex counts")
    check(all(item["lane"]["data_bytes"] == item["lane"]["num"] * 16
              for b in batches for item in b["lanes"]), "synthetic lane sizes")
    check(all(b["first_packet_bytes_match_first_tag"] for b in batches),
          "synthetic +0x04 does not match the first tag packet size")

    broken = build_synthetic_scene((4,), broken_batch=True)
    broken_batches = batch_targets(broken, shape_records(broken)[0])
    check(not broken_batches[0].get("eligible")
          and "unknown VIF command" in broken_batches[0]["reason"],
          "an unknown VIF code must refuse the batch: %r" % broken_batches[0].get("reason"))

    # A position moved outside the declared bounding sphere must be refused.
    moved = bytearray(build_synthetic_scene((3,)))
    lane = batch_targets(bytes(moved), shape_records(bytes(moved))[0])[0]["lanes"][0]["lane"]
    struct.pack_into("<f", moved, lane["data_offset"], 1.0e9)
    refused = batch_targets(bytes(moved), shape_records(bytes(moved))[0])[0]
    check(not refused.get("eligible") and "bounding sphere" in refused["reason"],
          "an escaped position must refuse the batch: %r" % refused.get("reason"))

    # Two V4_32 lanes in one batch are two independent targets, not an error.
    doubled = build_synthetic_scene((3,), duplicate_lane=True)
    pair = batch_targets(doubled, shape_records(doubled)[0])[0]
    check(len(pair["lanes"]) == 2 and all(i["eligible"] for i in pair["lanes"]),
          "a batch with two lanes must yield two targets: %r" % pair.get("reason"))

    # The VC-LZ consumed-byte counter must agree with the sibling decoder.
    payload = bytes(range(256)) * 40 + b"stadium" * 60
    stream = inv.compress(payload)
    check(inv.decompress_prefix(stream, len(payload)) == payload,
          "synthetic VC-LZ roundtrip")
    check(_consumed_bytes(stream, len(payload)) == len(stream),
          "consumed-byte counter %d vs stream %d"
          % (_consumed_bytes(stream, len(payload)), len(stream)))

    for failure in failures:
        sys.stderr.write("FAIL: %s\n" % failure)
    if failures:
        return 1
    print("NFL2K5_PS2_STADIUM_TARGET_CATALOG_SELFTEST_PASS batches=2 lanes=2 refusals=2")
    return 0


def _parse_entry(text: str) -> Tuple[int, Optional[int]]:
    if ":" in text:
        entry, chunk = text.split(":", 1)
        return int(entry, 0), int(chunk, 0)
    return int(text, 0), None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--iso")
    parser.add_argument("--entry", action="append", default=[],
                        help="outer entry index, optionally ENTRY:CHUNK; repeatable")
    parser.add_argument("--scan", action="store_true",
                        help="walk every outer entry looking for stadium scenes")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--measure-fit", action="store_true",
                        help="also decode each scene fully to measure its spare "
                             "stored bytes (counts and digests only)")
    parser.add_argument("--scene-name", default="stadium")
    parser.add_argument("--json")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.iso:
        parser.error("--iso is required unless --selftest is given")

    document = catalog(args.iso, [_parse_entry(text) for text in args.entry],
                       args.scan, args.limit, args.measure_fit, args.scene_name)
    payload = canonical_json(document)
    if args.json:
        with open(args.json, "wb") as handle:
            handle.write(payload)
    summary = document["summary"]
    print("NFL2K5_PS2_STADIUM_TARGET_CATALOG_PASS scenes=%d shapes=%d batches=%d "
          "lanes=%d targets=%d vertices=%d sha256=%s"
          % (summary["scenes"], summary["shapes"], summary["batches"],
             summary["position_lanes"], summary["target_count"],
             summary["vertex_total"],
             hashlib.sha256(payload).hexdigest()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, CatalogError, iso.Iso9660Error, inv.InventoryError,
            struct.error) as exc:
        raise SystemExit("error: %s" % exc) from exc
