#!/usr/bin/env python3
"""Move catalogued stadium vertex positions inside a copy of a PS2 NFL 2K5 ISO.

Same-count, same-topology geometry editing for ESPN NFL 2K5 (PS2, SLUS-20919).
The source ISO is opened read-only and never written; a **new** image is
produced through ``ps2_iso9660_writer.replace_files``.

WHAT MAY CHANGE, AND NOTHING ELSE
---------------------------------
For each target the recipe names, the writer replaces the ``x``, ``y`` and
``z`` binary32 of every vertex in one catalogued VIF ``UNPACK V4_32`` lane.
The lane is **strided**: 12 editable bytes at the start of each 16-byte
element, and the fourth component is carried over from the source vertex.

Refused before anything is created:

* a vertex count that differs from the catalogue's -- the count is the VIF
  ``NUM`` field, so changing it *is* a topology change;
* any coordinate that is not a finite, exactly representable binary32;
* a decoded edit that touched a byte outside the declared lanes -- checked,
  not assumed;
* a recompressed stream that does not fit the chunk's fixed stored body;
* a rebuilt span whose 0x20 wrapper is not byte-identical to the source's.

THREE NESTED FIXED ALLOCATIONS
------------------------------
1. **ISO.**  ``ps2_iso9660_writer`` replaces a file inside the extent it
   already owns; nothing is relocated and the image keeps its exact length.
2. **Pack.**  A resource chunk's successors start at ``0x20 + stored_size``
   past it, so the rebuilt span must be exactly the size of the old one.
3. **Stream.**  The VC-LZ body must fit ``stored_size``, and the wrapper's
   ``+0x14`` in-place-decode scratch word must stay at its retail value.

Point 3 is the hard one.  The retail packer left these scenes 0-16 spare
bytes out of ~1.3 MB, so the retail-identical greedy encoder has no room for
an edit.  ``nfl_vc_lz_fill.rebuild_fixed_span_filled`` is used exactly as
written: greedy first (which reproduces the retail stream byte for byte, so a
no-op is provably free), then the optimal-parse encoder, whose ~1% tighter
packing is what buys the room; it then expands trailing matches back into
literals so the body still fills ``stored_size`` and the scratch word never
has to move.  Raising that word is what hung the Xbox attract demo on
2026-09-03, so this writer never does.

RETAIL-FREE
-----------
The recipe carries the user's own coordinates.  The report carries names,
offsets, counts and digests.  No disc byte is ever emitted.

USAGE
-----
    python3 tools/nfl2k5_ps2_stadium_position_patch.py \\
        --iso <stock SLUS-20919.iso> \\
        --catalog reports/gameplay_tuning/nfl2k5_ps2_stadium_target_catalog.v1.json \\
        --recipe <positions.json> --output <new.iso> [--report <report.json>]
    python3 tools/nfl2k5_ps2_stadium_position_patch.py --selftest

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps2_iso9660 as iso  # noqa: E402
import ps2_iso9660_writer as iso_writer  # noqa: E402
import nfl2k5_ps2_disc_inventory as inv  # noqa: E402
import nfl2k5_ps2_stadium_target_catalog as cat  # noqa: E402
import nfl_txtr as txtr  # noqa: E402
import nfl_vc_lz_fill as vclz  # noqa: E402

__all__ = [
    "SCHEMA", "RECIPE_SCHEMA", "PatchError", "load_catalog", "load_recipe",
    "apply_positions", "rebuild_span", "patch", "selftest", "main",
]

SCHEMA = "nfl2k5_ps2_stadium_position_patch/v1"
RECIPE_SCHEMA = "nfl2k5_ps2_stadium_position_recipe/v1"

MAX_RECIPE_BYTES = 8 * 1024 * 1024
MAX_CATALOG_BYTES = 256 * 1024 * 1024
MAX_EDITS = 4096
ELEMENT = cat.POSITION_ELEMENT_BYTES        # 16
LANE = cat.POSITION_LANE_BYTES              # 12


class PatchError(ValueError):
    """The disc, the catalogue, the recipe, or the rebuilt span is not acceptable."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise PatchError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Strict JSON
# ---------------------------------------------------------------------------

def _reject_duplicate_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise PatchError("duplicate JSON key: %s" % key)
        seen[key] = value
    return seen


def _reject_constant(token):
    raise PatchError("non-finite JSON constant %s is forbidden" % token)


def _load_json(path: str, label: str, maximum: int) -> dict:
    _require(os.path.exists(path), "%s does not exist: %s" % (label, path))
    _require(not os.path.islink(path),
             "%s must be a non-symlink regular file" % label)
    size = os.stat(path).st_size
    _require(0 < size <= maximum, "%s size is outside its limit" % label)
    with open(path, "rb") as handle:
        payload = handle.read()
    _require(len(payload) == size, "%s changed while reading" % label)
    try:
        value = json.loads(payload.decode("utf-8"),
                           object_pairs_hook=_reject_duplicate_pairs,
                           parse_constant=_reject_constant)
    except UnicodeDecodeError as exc:
        raise PatchError("%s is not UTF-8 JSON: %s" % (label, exc)) from exc
    except json.JSONDecodeError as exc:
        raise PatchError("%s is not valid JSON: %s" % (label, exc)) from exc
    _require(isinstance(value, dict), "%s root must be an object" % label)
    return {"value": value, "sha256": _sha(payload), "size": size}


def load_catalog(path: str) -> dict:
    document = _load_json(path, "catalog", MAX_CATALOG_BYTES)
    value = document["value"]
    _require(value.get("schema") == cat.SCHEMA,
             "catalog schema is not %s" % cat.SCHEMA)
    targets = value.get("targets")
    _require(isinstance(targets, list) and targets,
             "catalog carries no targets")
    scenes = value.get("scenes")
    _require(isinstance(scenes, list) and scenes, "catalog carries no scenes")
    rows = {}
    for row in targets:
        _require(isinstance(row, dict) and isinstance(row.get("target_id"), str),
                 "catalog target row is invalid")
        _require(row["target_id"] not in rows,
                 "duplicate catalog target_id: %s" % row["target_id"])
        index = row.get("scene_index")
        _require(isinstance(index, int) and 0 <= index < len(scenes),
                 "catalog target %s names no scene" % row["target_id"])
        row["source_identity"] = scenes[index]["identity"]
        rows[row["target_id"]] = row
    document["rows"] = rows
    document["scenes"] = scenes
    return document


def _binary32(value, label: str) -> float:
    _require(type(value) in (int, float), "%s must be a JSON number" % label)
    number = float(value)
    _require(math.isfinite(number), "%s must be finite" % label)
    try:
        decoded = struct.unpack("<f", struct.pack("<f", number))[0]
    except (OverflowError, struct.error) as exc:
        raise PatchError("%s is outside binary32" % label) from exc
    _require(number == decoded,
             "%s must be exactly representable as binary32" % label)
    return decoded


def load_recipe(path: str, catalog: dict) -> dict:
    document = _load_json(path, "recipe", MAX_RECIPE_BYTES)
    value = document["value"]
    _require(set(value) == {"schema", "catalog", "edits"},
             "recipe fields differ from %s" % RECIPE_SCHEMA)
    _require(value["schema"] == RECIPE_SCHEMA,
             "recipe schema is not %s" % RECIPE_SCHEMA)
    pin = value["catalog"]
    _require(isinstance(pin, dict) and set(pin) == {"schema", "sha256"},
             "recipe catalog pin fields differ")
    _require(pin["schema"] == cat.SCHEMA and pin["sha256"] == catalog["sha256"],
             "recipe pins a different catalog than the one supplied")
    edits = value["edits"]
    _require(isinstance(edits, list) and 0 < len(edits) <= MAX_EDITS,
             "recipe must carry 1..%d edits" % MAX_EDITS)
    resolved = []
    seen = set()
    identity = None
    for index, edit in enumerate(edits):
        label = "edits[%d]" % index
        _require(isinstance(edit, dict) and set(edit) == {"target_id", "positions"},
                 "%s fields differ from the recipe schema" % label)
        target_id = edit["target_id"]
        _require(isinstance(target_id, str), "%s target_id must be a string" % label)
        _require(target_id not in seen, "%s repeats target_id %s" % (label, target_id))
        seen.add(target_id)
        row = catalog["rows"].get(target_id)
        _require(row is not None,
                 "%s target_id is not authorised by the catalog: %s" % (label, target_id))
        if identity is None:
            identity = row["source_identity"]
        _require(row["source_identity"] == identity,
                 "%s selects a different SCNE chunk; one patch rebuilds one chunk"
                 % label)
        count = row["position"]["vertex_count"]
        positions = edit["positions"]
        _require(isinstance(positions, list) and len(positions) == count,
                 "%s must contain exactly %d vertices, not %d"
                 % (label, count, len(positions) if isinstance(positions, list) else -1))
        packed = []
        for vertex, triple in enumerate(positions):
            _require(isinstance(triple, list) and len(triple) == 3,
                     "%s positions[%d] must contain exactly XYZ" % (label, vertex))
            packed.append(tuple(
                _binary32(component, "%s positions[%d][%d]" % (label, vertex, axis))
                for axis, component in enumerate(triple)))
        resolved.append({"target_id": target_id, "row": row, "positions": packed})
    document["edits"] = resolved
    document["identity"] = identity
    return document


# ---------------------------------------------------------------------------
# The edit
# ---------------------------------------------------------------------------

def apply_positions(decoded: bytes, edits: Sequence[dict]) -> Tuple[bytes, List[dict]]:
    """Write each edit's XYZ into its lane, preserving every other byte.

    Returns the edited buffer and, per edit, the exact byte ranges written.
    The ``w`` component of every vertex is copied from the source, so the
    written ranges are ``vertex_count`` runs of 12 bytes, not one run of 16.
    """
    buffer = bytearray(decoded)
    written: List[dict] = []
    spans: List[Tuple[int, int]] = []
    for edit in edits:
        payload = edit["row"]["position"]["payload"]
        count = edit["row"]["position"]["vertex_count"]
        start = payload["offset"]
        _require(payload["size"] == count * ELEMENT,
                 "%s catalog payload size disagrees with its vertex count"
                 % edit["target_id"])
        _require(0 <= start and start + payload["size"] <= len(buffer),
                 "%s payload span is outside the decoded buffer" % edit["target_id"])
        # One lane can be reachable under several target_ids, so two edits may
        # name the same bytes.  Check payload spans, not the 12-byte runs: it
        # is the same test in O(n log n) rather than O(n^2) over every vertex.
        spans.append((start, start + payload["size"]))
        ranges = []
        for vertex, triple in enumerate(edit["positions"]):
            at = start + vertex * ELEMENT
            struct.pack_into("<3f", buffer, at, *triple)
            ranges.append((at, at + LANE))
        written.append({"target_id": edit["target_id"], "ranges": ranges,
                        "vertex_count": count,
                        "payload_offset": start, "payload_size": payload["size"]})
    ordered = sorted(spans)
    for index in range(1, len(ordered)):
        _require(ordered[index][0] >= ordered[index - 1][1],
                 "recipe edits overlap inside the decoded buffer; one position "
                 "lane can be reachable under several target_ids, so edit it "
                 "once")
    edited = bytes(buffer)

    # Prove containment rather than trusting the loop above.
    allowed = sorted(item for entry in written for item in entry["ranges"])
    changed = _changed_ranges(decoded, edited)
    for low, high in changed:
        _require(any(start <= low and high <= end for start, end in allowed),
                 "the decoded edit changed bytes at [%d, %d) outside every "
                 "declared position lane" % (low, high))
    return edited, written


def _changed_ranges(left: bytes, right: bytes) -> List[Tuple[int, int]]:
    """Maximal half-open ranges where two equal-length buffers differ."""
    _require(len(left) == len(right), "edited buffer changed length")
    ranges = []
    index = 0
    size = len(left)
    while index < size:
        if left[index] == right[index]:
            index += 1
            continue
        start = index
        while index < size and left[index] != right[index]:
            index += 1
        ranges.append((start, index))
    return ranges


def rebuild_span(span: bytes, edited: bytes) -> Tuple[bytes, dict]:
    """Recompress *edited* back into the chunk's fixed span, or refuse."""
    fields = txtr.HEADER.unpack_from(span)
    stored = fields[1]
    _require(len(span) == txtr.HEADER.size + stored,
             "source span is not 0x20 + stored_size bytes")
    _require(fields[4] == txtr.COMPRESSED_SENTINEL,
             "this writer only rebuilds VC-LZ chunks")
    source_decoded, source_info = txtr.decode_chunk(
        span, txtr.parse_chunks(span, allow_trailing=True)[0])
    if edited == source_decoded:
        # Identity is a byte-preservation path, never a recompression bet.
        return span, {"mode": "no_op", "stored_size": stored,
                      "retail_consumed_bytes": source_info.consumed_bytes,
                      "rebuilt_consumed_bytes": source_info.consumed_bytes,
                      "encoder": "none", "wrapper_identical": True,
                      "span_identical": True,
                      "scratch_bytes": fields[5], "matches_expanded": 0}
    try:
        rebuilt, info = vclz.rebuild_fixed_span_filled(span, edited, encoder="auto")
    except txtr.TxtrError as exc:
        raise PatchError(
            "the edited scene does not fit the chunk's fixed %d-byte stored body "
            "with the retail scratch word (%s). Nothing was written; move fewer "
            "vertices or choose a scene with more spare bytes." % (stored, exc)
        ) from exc
    _require(len(rebuilt) == len(span), "rebuilt span changed allocation")
    _require(rebuilt[:txtr.HEADER.size] == span[:txtr.HEADER.size],
             "rebuilt span changed the 0x20 wrapper")
    _require(info.wrapper_identical, "rebuilt span moved the scratch word")
    back, back_info = txtr.decode_chunk(
        rebuilt, txtr.parse_chunks(rebuilt, allow_trailing=True)[0])
    _require(back == edited, "writer-side independent decode differs from the edit")
    _require(back_info.consumed_bytes == info.filled_bytes,
             "rebuilt stream consumes a different number of bytes than it fills")
    return rebuilt, {
        "mode": "patched", "stored_size": stored,
        "retail_consumed_bytes": source_info.consumed_bytes,
        "rebuilt_consumed_bytes": info.filled_bytes,
        "compressed_bytes_before_fill": info.compressed_bytes,
        "encoder": "greedy" if info.compressed_bytes <= stored else "optimal",
        "padding_bytes": info.padding_bytes,
        "matches_expanded": info.matches_expanded,
        "scratch_bytes": info.scratch_bytes,
        "exact_minimum_scratch": info.exact_minimum_scratch,
        "wrapper_identical": info.wrapper_identical,
        "span_identical": rebuilt == span,
    }


# ---------------------------------------------------------------------------
# Disc plumbing
# ---------------------------------------------------------------------------

def _pack_paths(image) -> List[Tuple[str, int, int, str]]:
    """``[(iso_path, iso_byte_offset, size, letter)]`` for the VC packs."""
    packs = []
    for letter in inv.PACK_NAMES:
        entry = iso.find(image, "%s/%s." % (inv.PACK_DIRECTORY, letter))
        if entry is None:
            entry = iso.find(image, "%s/%s" % (inv.PACK_DIRECTORY, letter))
        if entry is None or entry.is_dir:
            break
        packs.append((entry.path, iso.extent_byte_offset(image, entry.lba),
                      entry.length, letter))
    _require(packs, "no %s packs found; this is not a SLUS-20919 layout"
             % inv.PACK_DIRECTORY)
    return packs


def _locate_chunk(archive, table, identity: dict) -> dict:
    entry_index = identity["entry_index"]
    _require(0 <= entry_index < len(table),
             "catalog entry index %d is outside the outer table" % entry_index)
    name_id, entry_size, offset_blocks = table[entry_index]
    _require("0x%08x" % name_id == identity["entry_name_id"],
             "outer entry %d carries a different name id" % entry_index)
    base = offset_blocks * inv.ALIGNMENT
    offset = identity["chunk_offset"]
    _require(0 <= offset and offset + inv.CHUNK_HEADER_SIZE <= entry_size,
             "catalog chunk offset is outside its outer entry")
    header = archive.read(base + offset, inv.CHUNK_HEADER_SIZE)
    _require(header[:4] == b"SCNE", "the catalogued chunk is not a SCNE")
    stored, system_bytes, video_bytes, magic = struct.unpack_from("<4I", header, 4)
    _require(system_bytes == identity["system_bytes"]
             and video_bytes == identity["video_bytes"],
             "the catalogued chunk's decoded extents changed")
    _require(magic == inv.COMPRESSED_SENTINEL, "the catalogued chunk is not compressed")
    _require(offset + inv.CHUNK_HEADER_SIZE + stored <= entry_size,
             "the catalogued chunk runs past its outer entry")
    return {"entry_index": entry_index, "base": base, "offset": offset,
            "stored": stored, "system_bytes": system_bytes,
            "video_bytes": video_bytes,
            "virtual_offset": base + offset,
            "span_size": inv.CHUNK_HEADER_SIZE + stored}


def _span_segments(packs, virtual_offset: int, size: int) -> List[dict]:
    """Split the chunk span across the pack files it physically occupies."""
    starts = [0]
    for _path, _base, length, _letter in packs:
        starts.append(starts[-1] + length)
    segments = []
    remaining = size
    cursor = virtual_offset
    while remaining:
        index = None
        for candidate in range(len(packs) - 1, -1, -1):
            if starts[candidate] <= cursor:
                index = candidate
                break
        _require(index is not None and cursor < starts[index + 1],
                 "the chunk span is outside the virtual archive")
        inside = cursor - starts[index]
        take = min(remaining, packs[index][2] - inside)
        segments.append({"pack_index": index, "iso_path": packs[index][0],
                         "pack_offset": inside, "size": take,
                         "span_offset": size - remaining})
        cursor += take
        remaining -= take
    return segments


def patch(iso_path: str, catalog_path: str, recipe_path: str, output_path: str,
          report_path: Optional[str] = None) -> dict:
    catalog = load_catalog(catalog_path)
    recipe = load_recipe(recipe_path, catalog)
    identity = recipe["identity"]

    _require(not os.path.exists(output_path),
             "refusing to overwrite an existing output image: %s" % output_path)
    _require(os.path.abspath(output_path) != os.path.abspath(iso_path),
             "the output image must not be the source image")

    image = iso.open_image(iso_path)
    disc = inv.image_identity(image, False)
    _require(disc["serial_matches"],
             "the image boots %s, not %s" % (disc["serial"], inv.SERIAL))
    packs = _pack_paths(image)
    archive = inv.VirtualPacks(str(iso_path),
                               [(letter, base, size)
                                for _path, base, size, letter in packs])
    archive.open()
    try:
        _outer, table = inv.read_outer_table(archive)
        chunk = _locate_chunk(archive, table, identity)
        span = archive.read(chunk["virtual_offset"], chunk["span_size"])
        source_span_sha = _sha(span)
        decoded, _info = txtr.decode_chunk(
            span, txtr.parse_chunks(span, allow_trailing=True)[0])
        _require(len(decoded) == chunk["system_bytes"] + chunk["video_bytes"],
                 "decoded size disagrees with the chunk wrapper")
        system = decoded[:chunk["system_bytes"]]
        _require(_sha(system) == identity["system_sha256"],
                 "the scene's system buffer differs from the catalogued one")
        for edit in recipe["edits"]:
            payload = edit["row"]["position"]["payload"]
            _require(_sha(decoded[payload["offset"]:payload["end_offset"]])
                     == payload["sha256"],
                     "%s position payload differs from the catalogued one"
                     % edit["target_id"])
            chain = edit["row"]["batch"]["chain"]
            _require(_sha(decoded[chain["offset"]:chain["end_offset"]])
                     == chain["sha256"],
                     "%s geometry chain differs from the catalogued one"
                     % edit["target_id"])
        edited, written = apply_positions(decoded, recipe["edits"])
        rebuilt, build = rebuild_span(span, edited)
        segments = _span_segments(packs, chunk["virtual_offset"], chunk["span_size"])
    finally:
        archive.close()

    # Build one replacement file per pack the span touches, then hand them all
    # to the ISO writer in a single bounded call.
    staging = tempfile.mkdtemp(prefix=".ps2-stadium-")
    replacements = {}
    staged = []
    try:
        for segment in segments:
            entry = iso.find(image, segment["iso_path"])
            _require(entry is not None, "pack %s vanished" % segment["iso_path"])
            target = os.path.join(staging, "pack%d.bin" % segment["pack_index"])
            with open(iso_path, "rb") as source, open(target, "xb") as destination:
                source.seek(iso.extent_byte_offset(image, entry.lba))
                remaining = entry.length
                while remaining:
                    block = source.read(min(1 << 22, remaining))
                    _require(block, "short read while copying %s" % segment["iso_path"])
                    destination.write(block)
                    remaining -= len(block)
            with open(target, "r+b") as handle:
                handle.seek(segment["pack_offset"])
                handle.write(rebuilt[segment["span_offset"]:
                                     segment["span_offset"] + segment["size"]])
                handle.flush()
                os.fsync(handle.fileno())
            _require(os.stat(target).st_size == entry.length,
                     "staged pack %s changed size" % segment["iso_path"])
            replacements[segment["iso_path"]] = _PathLike(target)
            staged.append({"iso_path": segment["iso_path"], "size": entry.length,
                           "pack_offset": segment["pack_offset"],
                           "bytes_spliced": segment["size"],
                           "sha256": _sha_file(target)})
        write_report = iso_writer.replace_files(iso_path, output_path, replacements)
    except BaseException:
        if os.path.exists(output_path):
            os.unlink(output_path)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    report = {
        "schema": SCHEMA,
        "source_iso": os.path.abspath(iso_path),
        "output_iso": os.path.abspath(output_path),
        "disc": {"serial": disc["serial"], "boot_sha256": disc["boot_sha256"],
                 "retail_boot_elf": disc["retail_boot_elf"]},
        "catalog": {"schema": cat.SCHEMA, "sha256": catalog["sha256"],
                    "target_count": len(catalog["rows"])},
        "recipe": {"schema": RECIPE_SCHEMA, "sha256": recipe["sha256"],
                   "edit_count": len(recipe["edits"]),
                   "contains_only_target_ids_and_positions": True},
        "scene": {
            "entry_index": chunk["entry_index"],
            "chunk_offset": chunk["offset"],
            "virtual_offset": chunk["virtual_offset"],
            "span_size": chunk["span_size"],
            "stored_size": chunk["stored"],
            "system_bytes": chunk["system_bytes"],
            "video_bytes": chunk["video_bytes"],
            "source_span_sha256": source_span_sha,
            "output_span_sha256": _sha(rebuilt),
            "source_decoded_sha256": _sha(decoded),
            "edited_decoded_sha256": _sha(edited),
        },
        "edits": [
            {"target_id": entry["target_id"], "vertex_count": entry["vertex_count"],
             "payload_offset": entry["payload_offset"],
             "payload_size": entry["payload_size"],
             "written_ranges": len(entry["ranges"]),
             "written_bytes": sum(high - low for low, high in entry["ranges"]),
             "before_sha256": _sha(decoded[entry["payload_offset"]:
                                           entry["payload_offset"] + entry["payload_size"]]),
             "after_sha256": _sha(edited[entry["payload_offset"]:
                                         entry["payload_offset"] + entry["payload_size"]])}
            for entry in written
        ],
        "decoded_diff": {
            "changed_ranges": len(_changed_ranges(decoded, edited)),
            "changed_bytes": sum(high - low
                                 for low, high in _changed_ranges(decoded, edited)),
            "every_changed_byte_inside_a_declared_lane": True,
        },
        "compression": dict(build, codec="VC-LZ",
                            scratch_policy="wrapper preserved byte-identical"),
        "packs": staged,
        "iso_write": iso_writer.report_to_json(write_report),
        "claims": {
            "same_count_position_write_back": True,
            "changed_count_or_topology_write_back": False,
            "runtime_visibility_proved": False,
            "hardware_visibility_proved": False,
            "production_ready": False,
        },
    }
    if report_path:
        with open(report_path, "xb") as handle:
            handle.write(cat.canonical_json(report))
    return report


class _PathLike(os.PathLike):
    """The ISO writer accepts bytes or os.PathLike; a str would be ambiguous."""

    def __init__(self, path: str) -> None:
        self._path = path

    def __fspath__(self) -> str:
        return self._path


# ---------------------------------------------------------------------------
# Self-test: a synthetic ISO carrying a synthetic pack, no game data
# ---------------------------------------------------------------------------

SYNTHETIC_SERIAL = "SLUS_209.19"


def build_synthetic_disc(vertex_counts: Sequence[int] = (4, 6),
                         slack_bytes: int = 96,
                         scratch: int = 96,
                         uniform_positions: bool = False) -> bytes:
    """A tiny SLUS-20919-shaped ISO with one VC pack holding one SCNE.

    ``slack_bytes`` is how many bytes of the chunk's stored body the retail
    stream leaves spare, which is what decides whether an edit can fit.
    ``uniform_positions`` makes every vertex identical so the payload packs
    into one long match -- the fixture the overflow test needs.
    """
    system = bytearray(cat.build_synthetic_scene(vertex_counts))
    if uniform_positions:
        shape = cat.shape_records(bytes(system))[0]
        for batch in cat.batch_targets(bytes(system), shape):
            for item in batch.get("lanes", ()):
                lane = item["lane"]
                for vertex in range(lane["num"]):
                    struct.pack_into("<4f", system,
                                     lane["data_offset"] + vertex * ELEMENT,
                                     10.0, 20.0, 30.0, 0.0)
    system = bytes(system)
    video = bytes(0x400)
    decoded = system + video
    stream, _metrics = txtr.compress_vc_lz(decoded, stream_tag=1, offset_bits=12,
                                           verify_roundtrip=True)
    stored = len(stream) + slack_bytes
    body = stream + bytes(slack_bytes)
    chunk = txtr.HEADER.pack(b"SCNE", stored, len(system), len(video),
                             txtr.COMPRESSED_SENTINEL, scratch, 0, 0) + body

    entry_offset_blocks = 1                      # one 0x800 block of index
    pack = bytearray()
    pack.extend(struct.pack("<III", 1, 0, 1))
    pack.extend(struct.pack("<%dI" % inv.PACK_SLOT_COUNT,
                            *([0] * inv.PACK_SLOT_COUNT)))
    pack.extend(struct.pack("<III", 0x5CAFF01D, len(chunk), entry_offset_blocks))
    pack.extend(bytes(entry_offset_blocks * inv.ALIGNMENT - len(pack)))
    pack.extend(chunk)
    while len(pack) % inv.ALIGNMENT:
        pack.append(0)
    struct.pack_into("<I", pack, 12, len(pack) // inv.ALIGNMENT)

    boot = ("BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
            % SYNTHETIC_SERIAL).encode("ascii")
    return iso.build_synthetic_iso(
        files=[(b"SYSTEM.CNF;1", boot),
               (SYNTHETIC_SERIAL.encode("ascii") + b";1", b"ELF" + bytes(2045))],
        sub_name=b"VC_20919",
        sub_files=[(b"0.;1", bytes(pack))])


def write_recipe(path: str, catalog_sha: str, edits: Sequence[Tuple[str, Sequence]]) -> None:
    document = {"schema": RECIPE_SCHEMA,
                "catalog": {"schema": cat.SCHEMA, "sha256": catalog_sha},
                "edits": [{"target_id": target_id,
                           "positions": [list(triple) for triple in positions]}
                          for target_id, positions in edits]}
    with open(path, "wb") as handle:
        handle.write(cat.canonical_json(document))


def selftest(tmp: Optional[str] = None) -> int:
    import nfl2k5_ps2_stadium_position_verify as verifier

    failures = []

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    root = tmp or tempfile.mkdtemp(prefix="ps2-stadium-selftest-")
    source = os.path.join(root, "source.iso")
    with open(source, "wb") as handle:
        handle.write(build_synthetic_disc())

    catalog_path = os.path.join(root, "catalog.json")
    document = cat.catalog(source, [(0, None)], False, None, True)
    with open(catalog_path, "wb") as handle:
        handle.write(cat.canonical_json(document))
    check(document["summary"]["target_count"] == 2,
          "synthetic catalog holds %d targets" % document["summary"]["target_count"])

    loaded = load_catalog(catalog_path)
    target = document["targets"][0]
    count = target["position"]["vertex_count"]
    moved = [(11.0 + index, 21.0, 29.0) for index in range(count)]
    recipe_path = os.path.join(root, "recipe.json")
    write_recipe(recipe_path, loaded["sha256"], [(target["target_id"], moved)])

    output = os.path.join(root, "patched.iso")
    report = patch(source, catalog_path, recipe_path, output)
    check(report["compression"]["mode"] == "patched", "self-test edit was a no-op")
    check(report["compression"]["wrapper_identical"], "wrapper moved")
    check(os.stat(output).st_size == os.stat(source).st_size,
          "the patched image changed length")

    result = verifier.verify(source, output, catalog_path, recipe_path)
    check(result["verdict"] == "pass", "verifier verdict %r" % result["verdict"])
    check(result["decoded"]["changed_bytes"] > 0, "verifier saw no change")

    for failure in failures:
        sys.stderr.write("FAIL: %s\n" % failure)
    if failures:
        return 1
    print("NFL2K5_PS2_STADIUM_POSITION_PATCH_SELFTEST_PASS targets=%d vertices=%d "
          "image_changed=%d wrapper_identical=true"
          % (document["summary"]["target_count"], count,
             result["image"]["changed_bytes"]))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--iso")
    parser.add_argument("--catalog")
    parser.add_argument("--recipe")
    parser.add_argument("--output")
    parser.add_argument("--report")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    for name in ("iso", "catalog", "recipe", "output"):
        if not getattr(args, name):
            parser.error("--%s is required unless --selftest is given" % name)

    report = patch(args.iso, args.catalog, args.recipe, args.output, args.report)
    print("NFL2K5_PS2_STADIUM_POSITION_PATCH_COMPLETE mode=%s edits=%d "
          "vertices=%d consumed=%d/%d span=%s runtime=false"
          % (report["compression"]["mode"], len(report["edits"]),
             sum(edit["vertex_count"] for edit in report["edits"]),
             report["compression"]["rebuilt_consumed_bytes"],
             report["compression"]["stored_size"],
             report["scene"]["output_span_sha256"][:16]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, PatchError, cat.CatalogError, iso.Iso9660Error,
            iso_writer.IsoWriteError, inv.InventoryError, txtr.TxtrError,
            struct.error) as exc:
        raise SystemExit("error: %s" % exc) from exc
