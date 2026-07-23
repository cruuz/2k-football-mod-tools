#!/usr/bin/env python3
"""Prove the AFC/NFC pregame-presentation remnants shipped in APF 2K8.

This read-only evidence generator compares APF outer 239 and NFL 2K5 outer
1193, both exactly ``pregameanims.iff`` under their platform filename hashes.
It decodes the four conference-figure textures from both titles, validates
their material/draw bindings, compares the migrated geometry, and records the
ESPN/team-matchup witnesses in the co-located MRKS resource.  It never writes
either game image.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import struct
import sys
import zlib

from PIL import Image

import apf_inner
import apf_outer
import nfl_outer
from apf_reference_nfl_remnants import (
    EvidenceError,
    EXPECTED_APF_INDEX_SHA256,
    EXPECTED_NFL_INDEX_SHA256,
    EXPECTED_NFL_XBE_SHA256,
    accessor_values,
    channel_metrics,
    directed_hausdorff,
    extract_text_runs,
    read_apf_file_parts,
    relative_target_be,
    sha256_bytes,
    sha256_file,
    source_pin,
    u32be,
    utf16be_z,
)
from nfl_scene_probe import (
    decode_resource,
    read_entry_range,
    record_from_header,
)
from nfl_scne_inventory import parse_scene, texture_info
from nfl_txtr import texture_to_rgba


SCHEMA = "vc_apf_pregame_conference_remnants/v1"
APF_OUTER_INDEX = 239
NFL_OUTER_INDEX = 1193
APF_OUTER_ID = 0x27B28292
NFL_OUTER_ID = 0x0205429D
MAX_DECOMPRESSED = 64 * 1024 * 1024
TEXTURE_RECORD_SIZE = 0xE0
MATERIAL_RECORD_SIZE = 0xF0

EXPECTED_APF_FILES = [
    ("bigfigureafc", "SCNE"),
    ("bigfigurenfc", "SCNE"),
    ("bighelmet", "SCNE"),
    ("big_team_matchup", "MRKS"),
]
EXPECTED_NFL_CHUNKS = [
    ("MRKS", "big_team_matchup"),
    ("SCNE", "bighelmet"),
    ("SCNE", "bigfigurenfc"),
    ("SCNE", "bigfigureafc"),
]
EXPECTED_CONFERENCE_MATERIALS = {
    "bigfigureafc": ["afc00", "afc01"],
    "bigfigurenfc": ["nfc00", "nfc01"],
}
MRKS_WITNESSES = [
    "big_team_matchup",
    "ESPNlogo",
    "ESPNpolygon",
    "ateam1helmet",
    "ateam2helmet",
    "ateam1logo",
    "ateam2logo",
    "ateam1primary",
    "ateam2primary",
    "team_awaylogo",
    "team_homelogo",
    "helmet_left",
    "helmet_right",
]


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fields,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def png_pin(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        size = list(image.size)
    return {
        "path": str(path.resolve()),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "dimensions": size,
    }


def decode_apf_scene(
    name: str,
    system: bytes,
    video: bytes,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    texture_count = u32be(system, 0x20, f"{name} texture count")
    texture_start = relative_target_be(system, 0x24, f"{name} texture table")
    material_count = u32be(system, 0x30, f"{name} material count")
    material_start = relative_target_be(system, 0x34, f"{name} material table")
    node_count = u32be(system, 0x44, f"{name} node count")
    node_start = relative_target_be(system, 0x48, f"{name} node table")
    if (texture_count, material_count, node_count) != (2, 2, 1):
        raise EvidenceError(f"{name}: unexpected texture/material/node counts")

    textures: list[dict[str, object]] = []
    texture_by_id: dict[int, dict[str, object]] = {}
    for index in range(texture_count):
        offset = texture_start + index * TEXTURE_RECORD_SIZE
        raw = system[offset : offset + TEXTURE_RECORD_SIZE]
        if len(raw) != TEXTURE_RECORD_SIZE:
            raise EvidenceError(f"{name}: truncated embedded texture {index}")
        texture_id = u32be(raw, 0, f"{name} texture {index} ID")
        metadata = apf_inner.parse_txtr_metadata(raw)
        video_word = u32be(raw, 0x6C, f"{name} texture {index} video offset")
        if video_word & 0xFFF != 1:
            raise EvidenceError(f"{name}: texture {index} video flags changed")
        video_offset = video_word & ~0xFFF
        byte_length = int(metadata["vc_base_data_length"])
        if video_offset + byte_length > len(video):
            raise EvidenceError(f"{name}: texture {index} exceeds VRAM")
        width, height, rgba = apf_inner.decode_txtr_base_rgba(
            metadata, video[video_offset : video_offset + byte_length]
        )
        if (metadata["format_name"], width, height) != ("DXT1", 256, 256):
            raise EvidenceError(f"{name}: conference texture format changed")
        png = output_dir / f"apf_{name}_{index}.png"
        apf_inner.write_rgba_png(png, width, height, rgba)
        row = {
            "index": index,
            "texture_id": f"0x{texture_id:08x}",
            "record_offset": f"0x{offset:x}",
            "video_offset": f"0x{video_offset:x}",
            "format": str(metadata["format_name"]),
            "dimensions": [width, height],
            "rgba_sha256": sha256_bytes(rgba),
            "png": png_pin(png),
            "_rgba": rgba,
        }
        textures.append(row)
        texture_by_id[texture_id] = row

    expected_materials = EXPECTED_CONFERENCE_MATERIALS[name]
    materials: list[dict[str, object]] = []
    for index in range(material_count):
        offset = material_start + index * MATERIAL_RECORD_SIZE
        name_target = relative_target_be(system, offset, f"{name} material name")
        material_name = utf16be_z(system, name_target, f"{name} material name")
        name_hash = u32be(system, offset + 4, f"{name} material hash")
        if name_hash != zlib.crc32(material_name.encode("ascii")) & 0xFFFFFFFF:
            raise EvidenceError(f"{name}: material-name hash mismatch")
        texture_id = u32be(system, offset + 0x50, f"{name} material texture")
        texture = texture_by_id.get(texture_id)
        if texture is None:
            raise EvidenceError(f"{name}: material references unknown texture")
        materials.append(
            {
                "index": index,
                "name": material_name,
                "texture_id": f"0x{texture_id:08x}",
                "texture_index": int(texture["index"]),
            }
        )
    if [row["name"] for row in materials] != expected_materials:
        raise EvidenceError(f"{name}: material order changed")

    node_name = utf16be_z(
        system,
        relative_target_be(system, node_start, f"{name} node name"),
        f"{name} node name",
    )
    draw_count = u32be(system, node_start + 0x7C, f"{name} draw count")
    draw_start = relative_target_be(system, node_start + 0x80, f"{name} draw table")
    draw_materials = [
        u32be(system, draw_start + index * 0x30 + 0x20, f"{name} draw material")
        for index in range(draw_count)
    ]
    if node_name != name or draw_count != 2 or draw_materials != [0, 1]:
        raise EvidenceError(f"{name}: node-to-material binding changed")

    scene = {
        "name": name,
        "system_size": len(system),
        "video_size": len(video),
        "texture_count": texture_count,
        "material_order": expected_materials,
        "node_name": node_name,
        "draw_material_indices": draw_materials,
        "textures": [{key: value for key, value in row.items() if key != "_rgba"}
                     for row in textures],
        "materials": materials,
    }
    return scene, textures


def parse_apf(
    index: Path,
    output_dir: Path,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]], bytes]:
    archive = apf_outer.parse_archive(index)
    entry = archive.entries[APF_OUTER_INDEX]
    if entry.name_id != APF_OUTER_ID:
        raise EvidenceError("APF pregameanims.iff outer ID changed")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        ]
    file_pairs = [(file.name, file.type_name) for file in record.files]
    if file_pairs != EXPECTED_APF_FILES:
        raise EvidenceError(f"APF pregame package composition changed: {file_pairs}")

    scenes: dict[str, object] = {}
    texture_sets: dict[str, list[dict[str, object]]] = {}
    for file in record.files[:2]:
        parts = read_apf_file_parts(record, blocks, file.index)
        if len(parts) != 2:
            raise EvidenceError(f"{file.name}: expected DRAM+VRAM parts")
        scene, textures = decode_apf_scene(file.name, parts[0], parts[1], output_dir)
        scenes[file.name] = scene
        texture_sets[file.name] = textures

    mrks_parts = read_apf_file_parts(record, blocks, record.files[3].index)
    if len(mrks_parts) != 1:
        raise EvidenceError("APF big_team_matchup expected one DRAM part")
    mrks = mrks_parts[0]
    mrks_strings = [row.text for row in extract_text_runs(mrks, "big")]
    if len(mrks_strings) != 259 or len(set(mrks_strings)) != 79:
        raise EvidenceError("APF big_team_matchup printable-string inventory changed")
    if not all(value in mrks_strings for value in MRKS_WITNESSES):
        raise EvidenceError("APF big_team_matchup lost a required ESPN/team witness")

    return {
        "outer_index": APF_OUTER_INDEX,
        "outer_id": f"0x{entry.name_id:08x}",
        "outer_size": entry.size,
        "filename": "pregameanims.iff",
        "filename_hash_rule": "CRC32 uppercase ASCII",
        "resources": [
            {"index": file.index, "name": file.name, "type": file.type_name}
            for file in record.files
        ],
        "conference_scenes": scenes,
        "big_team_matchup": {
            "size": len(mrks),
            "sha256": sha256_bytes(mrks),
            "printable_utf16be_occurrence_count": len(mrks_strings),
            "distinct_printable_utf16be_count": len(set(mrks_strings)),
            "selected_espn_team_witnesses": MRKS_WITNESSES,
        },
    }, texture_sets, mrks


def parse_nfl(
    index: Path,
    output_dir: Path,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]], bytes]:
    archive = nfl_outer.parse_archive(index)
    entry = archive.entries[NFL_OUTER_INDEX]
    if entry.name_id != NFL_OUTER_ID:
        raise EvidenceError("NFL pregameanims.iff outer ID changed")

    offsets: list[int] = []
    records = []
    cursor = 0
    for chunk_index in range(4):
        record = record_from_header(
            archive, NFL_OUTER_INDEX, chunk_index, cursor, "pregame_focus"
        )
        offsets.append(cursor)
        records.append(record)
        cursor = record.end_offset
    if cursor != entry.size:
        raise EvidenceError("NFL pregameanims chunks do not close outer entry")
    if [record.kind for record in records] != ["MRKS", "SCNE", "SCNE", "SCNE"]:
        raise EvidenceError("NFL pregameanims wrapper composition changed")

    mrks = read_entry_range(archive, entry, 0x20, records[0].stored_size)
    nfl_mrks_strings = [row.text for row in extract_text_runs(mrks, "little")]
    if not all(value in nfl_mrks_strings for value in MRKS_WITNESSES):
        raise EvidenceError("NFL big_team_matchup lost a required ESPN/team witness")

    scenes: dict[str, object] = {}
    texture_sets: dict[str, list[dict[str, object]]] = {}
    logical_chunks: list[tuple[str, str]] = [("MRKS", "big_team_matchup")]
    for scene_index, record in enumerate(records[1:], 1):
        span = read_entry_range(
            archive, entry, record.chunk_offset, 0x20 + record.stored_size
        )
        output, detail = decode_resource(span, record)
        scene, _names, material_rows, _sample = parse_scene(
            119300 + scene_index, record, output, {}
        )
        name = str(scene["name"])
        logical_chunks.append(("SCNE", name))
        if name not in EXPECTED_CONFERENCE_MATERIALS:
            continue
        expected_materials = EXPECTED_CONFERENCE_MATERIALS[name]
        materials = [row for row in material_rows]
        if [row["material_name"] for row in materials] != expected_materials:
            raise EvidenceError(f"NFL {name}: material order changed")
        embedded = list(scene["embedded_textures"])
        if len(embedded) != 2:
            raise EvidenceError(f"NFL {name}: embedded texture count changed")
        textures: list[dict[str, object]] = []
        for row in embedded:
            texture_index = int(row["index"])
            info = texture_info(output, int(row["descriptor_offset"]), name, texture_index)
            rgba = texture_to_rgba(output, record.as_chunk(), info)
            if (info.format_name, info.width, info.height) != ("P8", 256, 256):
                raise EvidenceError(f"NFL {name}: conference texture format changed")
            if sha256_bytes(rgba) != row["rgba_sha256"]:
                raise EvidenceError(f"NFL {name}: decoded texture hash mismatch")
            png = output_dir / f"nfl_{name}_{texture_index}.png"
            apf_inner.write_rgba_png(png, info.width, info.height, rgba)
            textures.append(
                {
                    "index": texture_index,
                    "format": info.format_name,
                    "dimensions": [info.width, info.height],
                    "rgba_sha256": sha256_bytes(rgba),
                    "png": png_pin(png),
                    "_rgba": rgba,
                }
            )
        scenes[name] = {
            "name": name,
            "chunk_index": record.chunk_index,
            "chunk_offset": f"0x{record.chunk_offset:x}",
            "stored_size": record.stored_size,
            "decoded_sha256": detail["decoded_sha256"],
            "material_order": expected_materials,
            "textures": [{key: value for key, value in row.items() if key != "_rgba"}
                         for row in textures],
        }
        texture_sets[name] = textures

    if logical_chunks != EXPECTED_NFL_CHUNKS:
        raise EvidenceError(f"NFL pregame logical chunk order changed: {logical_chunks}")

    return {
        "outer_index": NFL_OUTER_INDEX,
        "outer_id": f"0x{entry.name_id:08x}",
        "outer_size": entry.size,
        "filename": "pregameanims.iff",
        "filename_hash_rule": "CRC32 uppercase UTF-16LE",
        "chunks": [
            {
                "index": record.chunk_index,
                "offset": f"0x{record.chunk_offset:x}",
                "kind": record.kind,
                "logical_name": EXPECTED_NFL_CHUNKS[index][1],
                "stored_size": record.stored_size,
            }
            for index, record in enumerate(records)
        ],
        "conference_scenes": scenes,
        "big_team_matchup": {
            "size": len(mrks),
            "sha256": sha256_bytes(mrks),
            "selected_espn_team_witnesses": MRKS_WITNESSES,
        },
    }, texture_sets, mrks


def triangle_count(gltf: Path) -> int:
    document = json.loads(gltf.read_text())
    count = 0
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            values = accessor_values(gltf, int(primitive["indices"]))
            indices = [int(value) for value in values]
            mode = int(primitive["mode"])
            if mode == 4:
                if len(indices) % 3:
                    raise EvidenceError(f"{gltf}: triangle-list index count is not divisible by 3")
                count += sum(
                    len(set(indices[index : index + 3])) == 3
                    for index in range(0, len(indices), 3)
                )
            elif mode == 5:
                count += sum(
                    len({indices[index - 2], indices[index - 1], indices[index]}) == 3
                    for index in range(2, len(indices))
                )
            else:
                raise EvidenceError(f"{gltf}: unsupported primitive mode {mode}")
    return count


def compare_geometry(paths: dict[str, tuple[Path, Path]]) -> list[dict[str, object]]:
    expected = {
        "bigfigureafc": (919, 918, 1218, 1216),
        "bigfigurenfc": (919, 918, 1218, 1216),
        "bighelmet": (864, 864, 1077, 1076),
    }
    rows: list[dict[str, object]] = []
    for name, (apf_gltf, nfl_gltf) in paths.items():
        apf_vertices = accessor_values(apf_gltf, 0)
        nfl_vertices = accessor_values(nfl_gltf, 0)
        apf_triangles = triangle_count(apf_gltf)
        nfl_triangles = triangle_count(nfl_gltf)
        observed = (
            len(apf_vertices), len(nfl_vertices), apf_triangles, nfl_triangles
        )
        if observed != expected[name]:
            raise EvidenceError(f"{name}: geometry cardinalities changed {observed}")
        distance = max(
            directed_hausdorff(apf_vertices, nfl_vertices),
            directed_hausdorff(nfl_vertices, apf_vertices),
        )
        rows.append(
            {
                "name": name,
                "apf_vertex_count": len(apf_vertices),
                "nfl_vertex_count": len(nfl_vertices),
                "apf_triangle_count": apf_triangles,
                "nfl_triangle_count": nfl_triangles,
                "unordered_vertex_hausdorff_distance": distance,
            }
        )
    return rows


def make_contact_sheet(
    output: Path,
    apf_textures: dict[str, list[dict[str, object]]],
    nfl_textures: dict[str, list[dict[str, object]]],
) -> None:
    sheet = Image.new("RGBA", (1024, 512), (0, 0, 0, 255))
    for row_index, name in enumerate(("bigfigureafc", "bigfigurenfc")):
        ordered = [
            nfl_textures[name][0], apf_textures[name][0],
            nfl_textures[name][1], apf_textures[name][1],
        ]
        for column, texture in enumerate(ordered):
            with Image.open(texture["png"]["path"]) as image:
                sheet.paste(image.convert("RGBA"), (column * 256, row_index * 256))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", compress_level=9, optimize=False)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apf-index", type=Path,
        default=root / "extracted/All-Pro Football 2K8 (USA)/0A",
    )
    parser.add_argument(
        "--nfl-index", type=Path,
        default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
    )
    parser.add_argument(
        "--nfl-xbe", type=Path,
        default=root / "extracted/ESPN NFL 2K5 (USA)/default.xbe",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants",
    )
    parser.add_argument(
        "--json-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants.json",
    )
    parser.add_argument(
        "--texture-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/pregame_conference_texture_lineage.tsv",
    )
    parser.add_argument(
        "--claims-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/pregame_conference_video_claims.tsv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (args.apf_index, args.nfl_index, args.nfl_xbe):
        if not path.is_file():
            raise EvidenceError(f"required source is missing: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    apf, apf_textures, _apf_mrks = parse_apf(args.apf_index, args.output_dir)
    nfl, nfl_textures, _nfl_mrks = parse_nfl(args.nfl_index, args.output_dir)

    xbe = args.nfl_xbe.read_bytes()
    literal = "pregameanims.iff".encode("utf-16le")
    offsets = [match.start() for match in re.finditer(re.escape(literal), xbe)]
    if offsets != [0x00B027D4]:
        raise EvidenceError(f"NFL pregameanims.iff literal offsets changed: {offsets}")

    texture_rows: list[dict[str, object]] = []
    texture_lineage: list[dict[str, object]] = []
    for scene_name in ("bigfigureafc", "bigfigurenfc"):
        material_names = EXPECTED_CONFERENCE_MATERIALS[scene_name]
        for index in range(2):
            apf_row = apf_textures[scene_name][index]
            nfl_row = nfl_textures[scene_name][index]
            metrics = channel_metrics(apf_row["_rgba"], nfl_row["_rgba"])
            minimum_correlation = min(
                float(value["pearson_correlation"]) for value in metrics.values()
            )
            if minimum_correlation < 0.972:
                raise EvidenceError(f"{scene_name}/{index}: texture correlation changed")
            row = {
                "scene": scene_name,
                "material": material_names[index],
                "apf_format": apf_row["format"],
                "nfl_format": nfl_row["format"],
                "dimensions": [256, 256],
                "apf_rgba_sha256": apf_row["rgba_sha256"],
                "nfl_rgba_sha256": nfl_row["rgba_sha256"],
                "rgba_byte_identical": apf_row["_rgba"] == nfl_row["_rgba"],
                "channel_metrics": metrics,
                "minimum_channel_correlation": minimum_correlation,
                "apf_png": apf_row["png"],
                "nfl_png": nfl_row["png"],
            }
            texture_lineage.append(row)
            texture_rows.append(
                {
                    "scene": scene_name,
                    "material": material_names[index],
                    "apf_format": apf_row["format"],
                    "nfl_format": nfl_row["format"],
                    "width": 256,
                    "height": 256,
                    "minimum_channel_correlation": f"{minimum_correlation:.9f}",
                    "red_correlation": f"{metrics['R']['pearson_correlation']:.9f}",
                    "green_correlation": f"{metrics['G']['pearson_correlation']:.9f}",
                    "blue_correlation": f"{metrics['B']['pearson_correlation']:.9f}",
                    "apf_png": apf_row["png"]["path"],
                    "nfl_png": nfl_row["png"]["path"],
                }
            )

    contact_sheet = args.output_dir / "pregame_conference_textures_nfl_vs_apf.png"
    make_contact_sheet(contact_sheet, apf_textures, nfl_textures)

    root = Path(__file__).resolve().parents[1]
    gltf_paths = {
        "bigfigureafc": (
            root / "assets/intermediate/apf2k8/models/0239_0000_bigfigureafc.gltf",
            root / "assets/intermediate/nfl2k5/models/1193_0003_bigfigureafc.gltf",
        ),
        "bigfigurenfc": (
            root / "assets/intermediate/apf2k8/models/0239_0001_bigfigurenfc.gltf",
            root / "assets/intermediate/nfl2k5/models/1193_0002_bigfigurenfc.gltf",
        ),
        "bighelmet": (
            root / "assets/intermediate/apf2k8/models/0239_0002_bighelmet.gltf",
            root / "assets/intermediate/nfl2k5/models/1193_0001_bighelmet.gltf",
        ),
    }
    for pair in gltf_paths.values():
        for path in pair:
            if not path.is_file():
                raise EvidenceError(f"required glTF is missing: {path}")
    geometry = compare_geometry(gltf_paths)

    report = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_and_asset_analysis": True,
            "launches_game_or_emulator": False,
            "executes_translated_guest_code": False,
            "writes_game_images": False,
            "runtime_reachability_proved": False,
        },
        "sources": {
            "apf_index": source_pin(args.apf_index, EXPECTED_APF_INDEX_SHA256),
            "nfl_index": source_pin(args.nfl_index, EXPECTED_NFL_INDEX_SHA256),
            "nfl_xbe": source_pin(args.nfl_xbe, EXPECTED_NFL_XBE_SHA256),
            **{
                f"{name}_{platform}_gltf": source_pin(path)
                for name, pair in gltf_paths.items()
                for platform, path in zip(("apf", "nfl"), pair)
            },
        },
        "filename_identity": {
            "uppercase_name": "PREGAMEANIMS.IFF",
            "apf_crc32_uppercase_ascii": f"0x{zlib.crc32(b'PREGAMEANIMS.IFF') & 0xffffffff:08x}",
            "nfl_crc32_uppercase_utf16le": f"0x{zlib.crc32('PREGAMEANIMS.IFF'.encode('utf-16le')) & 0xffffffff:08x}",
            "matches_apf_outer_id": (zlib.crc32(b"PREGAMEANIMS.IFF") & 0xFFFFFFFF) == APF_OUTER_ID,
            "matches_nfl_outer_id": (zlib.crc32("PREGAMEANIMS.IFF".encode("utf-16le")) & 0xFFFFFFFF) == NFL_OUTER_ID,
            "nfl_xbe_utf16le_literal_offsets": [f"0x{value:08x}" for value in offsets],
        },
        "apf": apf,
        "nfl": nfl,
        "conference_texture_lineage": texture_lineage,
        "conference_geometry_lineage": geometry,
        "contact_sheet": {
            **png_pin(contact_sheet),
            "layout": "rows AFC,NFC; columns NFL material0, APF material0, NFL material1, APF material1",
        },
        "mrks_lineage": {
            "selected_exact_identifiers_present_in_both": MRKS_WITNESSES,
            "selected_exact_identifier_count": len(MRKS_WITNESSES),
            "interpretation": "the converted APF matchup graph retains ESPN presentation and dynamic team helmet/logo/color binding names",
        },
        "claims": {
            "safe": [
                "Retail APF 2K8 ships converted AFC and NFC inflatable-player scenes from NFL 2K5's exact pregameanims.iff package.",
                "All four AFC/NFC material textures remain directly bound and visibly retain the conference logos.",
                "The co-located APF big_team_matchup graph retains ESPNlogo/ESPNpolygon plus dynamic team helmet/logo/color identifiers.",
            ],
            "not_proved": [
                "The shipped APF frontend or presentation state reaches pregameanims.iff.",
                "The AFC/NFC figures are displayed during normal retail APF gameplay.",
                "The MRKS instruction/event semantics are sufficiently recovered to execute the presentation.",
            ],
        },
        "portme": [
            "// PORTME: trace APF ordinal/enumeration-based requests before classifying pregameanims.iff runtime use.",
            "// PORTME: recover big_team_matchup MRKS event and callback semantics before attempting playback.",
            "// PORTME: map the full SCNE shader/material contract before building a reversible model/texture importer.",
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    write_tsv(
        args.texture_tsv_out,
        texture_rows,
        [
            "scene", "material", "apf_format", "nfl_format", "width", "height",
            "minimum_channel_correlation", "red_correlation", "green_correlation",
            "blue_correlation", "apf_png", "nfl_png",
        ],
    )
    write_tsv(
        args.claims_tsv_out,
        [
            {
                "grade": "A_proven",
                "claim": "APF ships converted AFC and NFC pregame figures with the original conference-logo textures still bound.",
                "evidence": "exact pregameanims.iff package pair; exact resource/material names; four decoded 256x256 P8-to-DXT1 texture correlations above 0.972; near-identical geometry",
                "boundary": "retail APF presentation reachability is not proved",
            },
            {
                "grade": "A_proven",
                "claim": "APF's co-located matchup graph still carries ESPN and dynamic team-logo/helmet bindings.",
                "evidence": "big_team_matchup MRKS contains ESPNlogo, ESPNpolygon, ateam1/2 helmet/logo/primary, and home/away team-logo names",
                "boundary": "MRKS opcode/callback semantics remain unresolved",
            },
            {
                "grade": "boundary",
                "claim": "The files are converted licensed presentation content, not evidence of a reachable APF screen by themselves.",
                "evidence": "this generator performs archive, texture, material, and geometry analysis only",
                "boundary": "do not describe the derived PNGs as retail APF screenshots",
            },
        ],
        ["grade", "claim", "evidence", "boundary"],
    )
    print(
        "APF_PREGAME_CONFERENCE_REMNANTS_COMPLETE resources=4 textures=4 "
        f"corr_min={min(row['minimum_channel_correlation'] for row in texture_lineage):.6f} "
        "geometry=3 runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        EvidenceError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        nfl_outer.FormatError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
