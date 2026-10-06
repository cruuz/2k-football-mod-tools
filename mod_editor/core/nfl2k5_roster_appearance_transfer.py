"""Carry selected native face, head-shape and portrait art with a roster.

The roster's +0x06 word selects disc resources as well as a portrait. Copying
the word alone into another project can select that project's previous face.
This optional bundle copies the existing native spans, including both SHAP
copies. It never edits the shared head mesh or reallocates an archive entry.
Xbox saves contain no art: callers must supply the disc those faces came from.
"""
from __future__ import annotations

import base64
import binascii
from functools import lru_cache
import hashlib
from pathlib import Path
import struct
from typing import Any

from . import nfl2k5_roster_records as rr

SCHEMA = "2k5_mod_studio_roster_appearance/v1"
MAX_BUNDLE_BYTES = 192 * 1024 * 1024
FACE_SHAPES_OUTER = 3108
FACE_SHAPE_SLOT = 512


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    # Existing packaged reports pin the resource layouts, not user artwork.
    rr._outer_image()  # Install the packaged tools import path, as roster IO does.
    from nfl_live_face_texture_targets import load_report as faces
    from nfl_player_portrait_targets import load_report as portraits
    _, face_report, _ = faces(rr.ROOT / "reports/assets/nfl2k5_live_face_texture_compatibility.json")
    _, _, portrait_report = portraits(rr.ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json")
    result = {}
    for row in face_report["resources"]:
        result[f"{row['face_id']}:{row['family']}"] = dict(row, kind="TXTR")
    for row in face_report["shapes"]:
        result[f"{row['face_id']}:s"] = dict(row, kind="SHAP")
        result[f"{row['face_id']}:s_global"] = dict(row, kind="SHAP", outer_index=FACE_SHAPES_OUTER)
    for row in portrait_report["targets"]:
        result[row["selector"]] = dict(row, kind="TXTR")
    return result


def _shape_offsets(archive) -> dict[str, int]:
    rr._require(len(archive.entries) > FACE_SHAPES_OUTER, "Disc has no FaceShapes table.")
    entry = archive.entries[FACE_SHAPES_OUTER]
    rr._require(entry.name_id == 0x52057D0A and entry.size == 624 * FACE_SHAPE_SLOT,
                "Disc FaceShapes identity or fixed capacity changed.")
    raw = archive.read(entry.virtual_offset, entry.size)
    result = {}
    for offset in range(0, len(raw), FACE_SHAPE_SLOT):
        rr._require(raw[offset:offset + 4] == b"SHAP", "Invalid FaceShapes slot.")
        name = raw[offset + 64:offset + 74].decode("utf-16-le")
        rr._require(name[0] == "s" and name[1:].isdigit() and name[1:] not in result,
                    "Invalid or duplicate FaceShapes selector.")
        result[name[1:]] = offset
    return result


def _entry_for(archive, row, shape_offsets):
    index = row["outer_index"]
    rr._require(index < len(archive.entries), "Appearance outer entry is absent.")
    entry = archive.entries[index]
    if index == FACE_SHAPES_OUTER:
        offset = shape_offsets[row["face_id"]]
    else:
        rr._require(entry.name_id == int(row["outer_id"], 0) and entry.size == row["outer_size"],
                    "Appearance entry identity or allocation changed.")
        offset = row["chunk_offset"]
    rr._require(0 <= offset and offset + row["span_size"] <= entry.size,
                "Appearance span exceeds its outer entry.")
    return entry.virtual_offset + offset


def _check_span(selector: str, raw: bytes, row) -> None:
    rr._require(len(raw) == row["span_size"] and raw[:4] == row["kind"].encode("ascii"),
                f"Invalid native appearance span: {selector}.")
    rr._require(struct.unpack_from("<I", raw, 4)[0] + 32 == len(raw),
                f"Appearance wrapper allocation changed: {selector}.")
    from nfl_txtr import HEADER, Chunk, decode_chunk, parse_texture, minimum_vc_lz_overlap_scratch
    chunk = Chunk(0, 0, row["kind"], *HEADER.unpack_from(raw)[1:])
    decoded, decode_info = decode_chunk(raw, chunk)
    if decode_info is not None:
        minimum = minimum_vc_lz_overlap_scratch(raw[32:32 + decode_info.consumed_bytes],
                                              chunk.stored_size, len(decoded))
        rr._require(chunk.overlap_scratch_bytes >= minimum,
                    f"Appearance compressed-load scratch is insufficient: {selector}.")
    if row["kind"] == "TXTR":
        texture = parse_texture(decoded, chunk)
        expected = (row.get("resource_name") or row["name"])
        rr._require(texture.name == expected, f"Appearance resource name differs: {selector}.")
        rr._require(chunk.system_bytes == row["system_bytes"] and chunk.video_bytes == row["video_bytes"]
                    and texture.packed_format == int(row["packed_format"], 0),
                    f"Appearance texture layout differs: {selector}.")
        rr._require(texture.width == row.get("width", texture.width)
                    and texture.height == row.get("height", texture.height),
                    f"Appearance texture dimensions differ: {selector}.")
    else:
        rr._require(not chunk.compressed and decoded[32:42].decode("utf-16-le") == row["resource_name"],
                    f"Appearance shape name or encoding differs: {selector}.")


def validate_bundle(bundle) -> dict[str, bytes]:
    """Validate every resource against the pinned, narrowly scoped layout."""
    rr._require(type(bundle) is dict and set(bundle) == {"schema", "resources"}
                and bundle["schema"] == SCHEMA and type(bundle["resources"]) is list,
                "Invalid roster appearance bundle.")
    catalog = _catalog()
    result = {}
    total = 0
    for row in bundle["resources"]:
        rr._require(type(row) is dict and set(row) == {"selector", "sha256", "data_base64"},
                    "Invalid appearance resource fields.")
        selector = row["selector"]
        rr._require(type(selector) is str and selector in catalog and selector not in result,
                    "Unknown or duplicate appearance resource selector.")
        encoded = row["data_base64"]
        maximum = 4 * ((catalog[selector]["span_size"] + 2) // 3)
        rr._require(type(encoded) is str and len(encoded) == maximum,
                    "Appearance resource encoded allocation differs.")
        total += catalog[selector]["span_size"]
        rr._require(total <= MAX_BUNDLE_BYTES, "Roster appearance bundle exceeds 192 MiB.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise rr.RosterRecordError("Invalid appearance resource base64.") from exc
        rr._require(hashlib.sha256(raw).hexdigest() == row["sha256"],
                    "Appearance resource SHA-256 differs.")
        _check_span(selector, raw, catalog[selector])
        result[selector] = raw
    # A partial face would mix two people's face/skull/shape art.
    ids = {s.split(":")[0] for s in result if not s.startswith("portrait:")}
    for face_id in ids:
        rr._require(all(f"{face_id}:{family}" in result for family in ("f", "h", "n", "s", "s_global")),
                    f"Incomplete face resources for {face_id}.")
    return result


def _selected(document) -> set[str]:
    catalog = _catalog()
    result = set()
    for player in document.players:
        photo = player.record.get("photo_id")
        face_id = f"{photo:04d}"
        if f"{face_id}:f" not in catalog:
            # Native fallback uses the encoded skin/face bits, not the full
            # editor skin enum. Reproduce the game's formula exactly.
            photo = 9001 + (player.record.skin & 7) * 100 + (player.record.get("face") & 7)
            face_id = f"{photo:04d}"
        rr._require(f"{face_id}:f" in catalog, f"No native generic face exists for {player.display}.")
        result.update(f"{face_id}:{family}" for family in ("f", "h", "n", "s", "s_global"))
        portrait = f"portrait:{player.record.get('photo_id'):04d}"
        if portrait in catalog:
            result.add(portrait)
    return result


def export_bundle(source: Path | str, document: rr.RosterDocument) -> dict[str, Any]:
    """Read art from a source disc/loose pack folder without mutating it."""
    catalog = _catalog()
    resources = []
    with rr._outer_image()(source) as archive:
        shapes = _shape_offsets(archive)
        for selector in sorted(_selected(document)):
            row = catalog[selector]
            raw = archive.read(_entry_for(archive, row, shapes), row["span_size"])
            _check_span(selector, raw, row)
            resources.append({"selector": selector, "sha256": hashlib.sha256(raw).hexdigest(),
                              "data_base64": base64.b64encode(raw).decode("ascii")})
    bundle = {"schema": SCHEMA, "resources": resources}
    validate_bundle(bundle)
    return bundle


def complete_document(source: Path | str, document: rr.RosterDocument, *, name="Roster with faces"):
    from . import nfl2k5_roster_snapshot as snapshot
    result = snapshot.document(document, name=name)
    result["appearance_assets"] = export_bundle(source, document)
    return result


def prepare_writes(archive, bundle, roster_body: bytes) -> list[tuple[int, bytes, str, str]]:
    """Preflight all resources before the caller writes even the roster."""
    resources = validate_bundle(bundle)
    required = _selected(rr.load_body(roster_body))
    rr._require(required <= set(resources), "Appearance bundle omits art selected by this roster.")
    shapes = _shape_offsets(archive)
    writes = []
    intervals = []
    for selector, raw in resources.items():
        row = _catalog()[selector]
        offset = _entry_for(archive, row, shapes)
        before = archive.read(offset, len(raw))
        _check_span(selector, before, row)
        intervals.append((offset, offset + len(raw)))
        if before != raw:
            writes.append((offset, raw, selector, hashlib.sha256(before).hexdigest()))
    intervals.sort()
    rr._require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])),
                "Appearance spans overlap.")
    return writes


def apply_writes(archive, writes) -> list[dict[str, Any]]:
    receipts = []
    for offset, raw, selector, before_hash in writes:
        rr._require(archive.write(offset, raw) == len(raw), "Short appearance resource write.")
        rr._require(archive.read(offset, len(raw)) == raw, "Appearance resource read-back differs.")
        receipts.append({"selector": selector, "virtual_offset": offset, "size": len(raw),
                         "before_sha256": before_hash, "after_sha256": hashlib.sha256(raw).hexdigest()})
    return receipts
