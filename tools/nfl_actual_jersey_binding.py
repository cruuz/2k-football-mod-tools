#!/usr/bin/env python3
"""Revalidate and report NFL 2K5's actual player-jersey texture binding.

This is a read-only, retail-pinned analysis.  It joins a fresh decode of every
resource in Detroit current HOME ``09H0.IFF`` with the shared player SCNE
materials and an address-led XBE trace.  It intentionally treats the existing
negative xemu observation as unresolved runtime evidence rather than using it
to overwrite the executable's static dataflow.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from nfl_outer import parse_archive
from nfl_txtr import parse_texture, texture_to_rgba
from nfl_uniform_inventory import (
    LogicalName,
    parse_name,
    parse_tset,
    parse_unif,
    read_and_validate_span,
)


SCHEMA = "nfl2k5_actual_jersey_binding/v1"
TARGET_OUTER = 3685
TARGET_NAME = "09H0.IFF"
TARGET_ID = "0x9a4832d6"
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_PACK0_SHA256 = (
    "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
)


class BindingError(RuntimeError):
    """Raised when a pinned binding invariant is no longer true."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BindingError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    require(resolved.is_file(), f"not a regular file: {resolved}")
    return {
        "path": str(path),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames is not None, f"TSV has no header: {path}")
        return list(reader)


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, delimiter="\t", fieldnames=fields,
                                lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def texture_role(name: str) -> str:
    if name in {"jersey00", "jersey00_mud"}:
        return "diffuse_torso_clean_or_mud"
    if name in {"sleeve00", "sleeve00_mud"}:
        return "diffuse_sleeve_clean_or_mud"
    if name.isdigit() and 48 <= int(name) <= 57:
        return "front_back_jersey_digit_glyph"
    if name.startswith("hn") and name[2:].isdigit():
        return "helmet_digit_glyph"
    if name.startswith("an") and name[2:].isdigit():
        return "arm_shoulder_digit_glyph"
    if name in {"bump_jersey", "bump_sleeve", "bump_pants", "bump_sock"}:
        return "bump_or_normal_detail_not_diffuse"
    if name == "names":
        return "player_name_atlas"
    return "other_uniform_resource"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def digest_family(rows: list[dict[str, str]], prefix: str) -> str:
    selected = [
        row for row in rows
        if (prefix == "plain" and row["name"].isdigit())
        or (prefix != "plain" and row["name"].startswith(prefix))
    ]
    require(len(selected) == 10, f"digit family {prefix} has {len(selected)} rows")
    payload = "\n".join(
        f"{row['name']}:{row['rgba_sha256']}" for row in
        sorted(selected, key=lambda item: item["name"])
    ).encode("ascii")
    return sha256_bytes(payload)


def build(args: argparse.Namespace) -> tuple[
    dict[str, object], list[dict[str, object]], list[dict[str, object]],
    list[dict[str, object]], list[dict[str, object]],
]:
    source_paths = {
        "pack0": args.index,
        "xbe": args.xbe,
        "chunk_inventory": args.chunk_inventory,
        "uniform_inventory": args.uniform_inventory,
        "packages_tsv": args.packages,
        "tset_tsv": args.tsets,
        "standalone_tsv": args.standalone,
        "scne_scenes_tsv": args.scne_scenes,
        "scne_materials_tsv": args.scne_materials,
        "ghidra_trace": args.ghidra_trace,
        "ghidra_pseudo_c": args.ghidra_pseudo,
    }
    source_pins = {name: pin(path) for name, path in source_paths.items()}
    require(source_pins["xbe"]["sha256"] == EXPECTED_XBE_SHA256,
            "retail XBE hash changed")
    require(source_pins["pack0"]["sha256"] == EXPECTED_PACK0_SHA256,
            "canonical extracted pack 0 hash changed")

    chunk_inventory = load_json(args.chunk_inventory)
    require(chunk_inventory.get("schema") ==
            "nfl2k5_resource_chunk_inventory/v1", "wrong chunk inventory schema")
    uniform_inventory = load_json(args.uniform_inventory)
    require(uniform_inventory.get("schema") == "nfl2k5_uniform_inventory/v1",
            "wrong uniform inventory schema")
    packages = read_tsv(args.packages)
    tset_rows_all = read_tsv(args.tsets)
    standalone_rows_all = read_tsv(args.standalone)
    scne_scenes = read_tsv(args.scne_scenes)
    scne_materials = read_tsv(args.scne_materials)

    target_package = next(
        (row for row in packages if int(row["outer_index"]) == TARGET_OUTER), None
    )
    require(target_package is not None, "Detroit 09H0 package row is absent")
    assert target_package is not None
    require(target_package["logical_name"] == TARGET_NAME and
            target_package["outer_id"] == TARGET_ID and
            target_package["side_context"] == "HOME" and
            target_package["style_display"] == "Current Uniform",
            "Detroit 09H0 package identity changed")

    inventory_package = next(
        (row for row in uniform_inventory["packages"]
         if int(row["outer_index"]) == TARGET_OUTER), None
    )
    require(inventory_package is not None and
            inventory_package["logical_name"] == TARGET_NAME,
            "Detroit package is absent from uniform inventory")

    target_chunks = [
        row for row in chunk_inventory["chunks"]
        if int(row["outer_index"]) == TARGET_OUTER
    ]
    target_chunks.sort(key=lambda row: int(row["chunk_index"]))
    require(len(target_chunks) == 53, f"09H0 has {len(target_chunks)} chunks")
    expected_kinds = ["Unif"] + ["TSET"] * 10 + ["TXTR"] * 33 + \
        ["NAME"] + ["TXTR"] * 8
    require([row["kind"] for row in target_chunks] == expected_kinds,
            "09H0 chunk sequence changed")

    canonical_tsets = [
        row for row in tset_rows_all if int(row["outer_index"]) == TARGET_OUTER
    ]
    canonical_standalone = [
        row for row in standalone_rows_all
        if int(row["outer_index"]) == TARGET_OUTER
    ]
    require(len(canonical_tsets) == 51, "09H0 canonical TSET reference count changed")
    require(len(canonical_standalone) == 41,
            "09H0 canonical standalone TXTR count changed")
    canonical_tset_key = {
        (int(row["tset_chunk_index"]), int(row["reference_index"])): row
        for row in canonical_tsets
    }
    canonical_txtr_key = {
        int(row["chunk_index"]): row for row in canonical_standalone
    }

    archive = parse_archive(args.index)
    entry = archive.entries[TARGET_OUTER]
    require(entry.name_id == int(TARGET_ID, 16) and
            entry.size == int(target_package["outer_size"]),
            "fresh archive parse disagrees with 09H0 identity")
    logical = LogicalName(
        name=TARGET_NAME, name_id=int(TARGET_ID, 16), asset_code="09",
        side_code="H", side_context="HOME", variant_id=0, pair_key="09:0",
    )

    resource_rows: list[dict[str, object]] = []
    texture_rows: list[dict[str, object]] = []
    clean_tset_references: list[dict[str, object]] = []
    standalone_evidence: list[dict[str, object]] = []
    unif_evidence: dict[str, object] | None = None
    name_evidence: dict[str, object] | None = None
    for item in target_chunks:
        record, span, body, decode_info = read_and_validate_span(archive, item)
        row: dict[str, object] = {
            "outer_index": record.outer_index,
            "logical_name": TARGET_NAME,
            "chunk_index": record.chunk_index,
            "kind": record.kind,
            "chunk_offset": record.chunk_offset,
            "span_size": len(span),
            "stored_size": record.stored_size,
            "system_bytes": record.word_08,
            "video_bytes": record.word_0c,
            "span_sha256": sha256_bytes(span),
            "decoded_sha256": sha256_bytes(body),
            "resource_names": "",
            "resource_count": 1,
            "format_name": "",
            "width": "",
            "height": "",
            "role": "",
        }
        if record.kind == "Unif":
            unif_evidence = parse_unif(body, record)
            row["resource_names"] = "uniform"
            row["role"] = "uniform_scalar_configuration"
        elif record.kind == "NAME":
            name_evidence, metrics = parse_name(body, record)
            require(len(metrics) == 29, "NAME metric count changed")
            row["resource_names"] = "names"
            row["role"] = "player_name_metrics"
        elif record.kind == "TSET":
            summary, references, _ = parse_tset(body, record, logical, None)
            require(summary["decoded_sha256"] == row["decoded_sha256"],
                    f"TSET {record.chunk_index} decoded hash mismatch")
            row["resource_names"] = ";".join(
                str(reference["name"]) for reference in references
            )
            row["resource_count"] = len(references)
            row["role"] = "embedded_texture_set"
            for reference in references:
                key = (record.chunk_index, int(reference["reference_index"]))
                canonical = canonical_tset_key.get(key)
                require(canonical is not None, f"canonical TSET row absent: {key}")
                assert canonical is not None
                for field in (
                    "name", "format_name", "width", "height",
                    "base_pixel_sha256", "palette_bgra_sha256",
                ):
                    require(str(reference[field]) == canonical[field],
                            f"TSET {key} field {field} changed")
                texture = {
                    "storage_kind": "embedded_TSET",
                    "chunk_index": record.chunk_index,
                    "reference_index": reference["reference_index"],
                    "name": reference["name"],
                    "format_name": reference["format_name"],
                    "width": reference["width"],
                    "height": reference["height"],
                    "mip_levels": reference["mip_levels"],
                    "decoded_sha256": summary["decoded_sha256"],
                    "pixel_sha256": reference["base_pixel_sha256"],
                    "palette_sha256": reference["palette_bgra_sha256"],
                    "rgba_sha256": "",
                    "role": texture_role(str(reference["name"])),
                }
                texture_rows.append(texture)
                clean_tset_references.append(texture)
        elif record.kind == "TXTR":
            texture = parse_texture(body, record.as_chunk())
            rgba = texture_to_rgba(body, record.as_chunk(), texture)
            canonical = canonical_txtr_key.get(record.chunk_index)
            require(canonical is not None, f"canonical TXTR row absent: {record.chunk_index}")
            assert canonical is not None
            actual = {
                "storage_kind": "standalone_TXTR",
                "chunk_index": record.chunk_index,
                "reference_index": "",
                "name": texture.name,
                "format_name": texture.format_name,
                "width": texture.width,
                "height": texture.height,
                "mip_levels": texture.mip_levels,
                "decoded_sha256": sha256_bytes(body),
                "pixel_sha256": "",
                "palette_sha256": "",
                "rgba_sha256": sha256_bytes(rgba),
                "role": texture_role(texture.name),
            }
            for field in (
                "name", "format_name", "width", "height", "mip_levels",
                "decoded_sha256", "rgba_sha256",
            ):
                require(str(actual[field]) == canonical[field],
                        f"TXTR {record.chunk_index} field {field} changed")
            texture_rows.append(actual)
            standalone_evidence.append(actual)
            row.update({
                "resource_names": texture.name,
                "format_name": texture.format_name,
                "width": texture.width,
                "height": texture.height,
                "role": actual["role"],
            })
        else:
            raise BindingError(f"unexpected target kind {record.kind}")
        if decode_info is not None:
            row["lz_consumed_bytes"] = decode_info.consumed_bytes
        resource_rows.append(row)

    require(unif_evidence is not None and name_evidence is not None,
            "fresh Unif/NAME decode did not complete")
    require(len(texture_rows) == 92 and len(clean_tset_references) == 51 and
            len(standalone_evidence) == 41, "fresh texture inventory counts changed")
    require(not any(
        row["storage_kind"] == "standalone_TXTR" and
        row["width"] == 512 and row["height"] == 256 and
        row["role"] == "other_uniform_resource"
        for row in texture_rows
    ), "unexpected alternative standalone 512x256 diffuse candidate appeared")

    target_scenes = [
        row for row in scne_scenes if row["name"] in {"lo_body", "hi_body", "hi_head"}
    ]
    require({row["name"] for row in target_scenes} ==
            {"lo_body", "hi_body", "hi_head"}, "shared player scenes are incomplete")
    material_rows: list[dict[str, object]] = []
    for row in scne_materials:
        if row["scene_name"] not in {"lo_body", "hi_body", "hi_head"}:
            continue
        name = row["material_name"]
        if not ("UNIF_" in name or "NUMBER" in name or "PLAYERNAME" in name):
            continue
        require(row["mapping_status"] == "unmapped" and
                not row["texture_target"] and not row["texture_index"],
                f"{row['scene_name']} material {name} gained an on-disk texture target")
        material_rows.append({
            "scene_name": row["scene_name"],
            "scene_index": row["scene_index"],
            "chunk_index": row["chunk_index"],
            "material_index": row["material_index"],
            "material_name": name,
            "material_offset": row["material_offset"],
            "texture_pointer_field": row["texture_pointer_field"],
            "mapping_status": row["mapping_status"],
        })
    require(any(row["scene_name"] == "hi_body" and
                row["material_name"] == "UNIF_jersey" for row in material_rows),
            "hi_body UNIF_jersey material is absent")
    require(any(row["scene_name"] == "hi_body" and
                row["material_name"] == "UNIF_sleeve" for row in material_rows),
            "hi_body UNIF_sleeve material is absent")
    require(any(row["scene_name"] == "hi_body" and
                row["material_name"] == "NUMBER_L" for row in material_rows),
            "hi_body NUMBER_L material is absent")

    trace = args.ghidra_trace.read_text(encoding="utf-8")
    pseudo = args.ghidra_pseudo.read_text(encoding="utf-8")
    anchors = [
        "0x004EEACC pointer=0x00E63E90 text=HOME",
        "0x004EEAD0 pointer=0x00E63E9C text=AWAY",
        "index=07 slot=0x004EEB30 pointer=0x00E63FA4 local_first=0x00000001 text=jersey00",
        "index=08 slot=0x004EEB38 pointer=0x00E63FA4 local_first=0x00000001 text=jersey00",
        "index=09 slot=0x004EEB40 pointer=0x00E63FB8 local_first=0x00000001 text=sleeve00",
        "0x004EF3D8 value=0x00000018 possible_material_index=24 possible_material=UNIF_jersey",
        "0x004EF3DC value=0x00000019 possible_material_index=25 possible_material=UNIF_sleeve",
        "0x0008EC1F MOV ECX,dword ptr [EDX*0x4 + 0xb65428]",
        "0x0008EC2C CALL 0x0008e3f0",
        "0x0008EC4A MOV EAX,dword ptr [EDX + 0xb6544c]",
        "0x0008EC56 CALL 0x0008e3f0",
        "0x0008E422 MOV dword ptr [EAX + 0x30],ECX",
        "0x0008F576 MOV EDX,0xc",
        "0x0008F57B CALL 0x0008e910",
        "0x0008F058 MOV EDX,0xd",
        "0x0008F05D CALL 0x0008e910",
        "0x0008F5AF MOV EDX,0xe",
        "0x0008F5B4 CALL 0x0008e910",
        "0x00A86C00 value=0x00E6494C text=48",
        "0x00A86C78 value=0x00E6499C text=hn48",
        "0x00A86CF0 value=0x00E64A14 text=an48",
        "RANGE 0x00063261..0x0006329D (HOME/AWAY context load calls)",
    ]
    missing = [anchor for anchor in anchors if anchor not in trace]
    require(not missing, "Ghidra trace anchors absent: " + "; ".join(missing))
    require("(&DAT_00b65428)" in pseudo and "FUN_0008e910" in pseudo,
            "focused pseudo-C lost the body/digit binders")

    comparison_names = {
        row["logical_name"] for row in packages if row["asset_code"] == "09"
    } | {"01A0.IFF", "27H0.IFF"}
    package_by_outer = {
        int(row["outer_index"]): row for row in packages
        if row["logical_name"] in comparison_names
    }
    require(len(package_by_outer) == 22, "comparison package selection changed")
    tsets_by_outer: dict[int, list[dict[str, str]]] = {}
    txtr_by_outer: dict[int, list[dict[str, str]]] = {}
    for outer in package_by_outer:
        tsets_by_outer[outer] = [
            row for row in tset_rows_all if int(row["outer_index"]) == outer
        ]
        txtr_by_outer[outer] = [
            row for row in standalone_rows_all if int(row["outer_index"]) == outer
        ]
        require(len(tsets_by_outer[outer]) == 51 and len(txtr_by_outer[outer]) == 41,
                f"comparison outer {outer} inventory is incomplete")

    def tset_named(outer: int, name: str) -> dict[str, str]:
        matches = [row for row in tsets_by_outer[outer] if row["name"] == name]
        require(len(matches) == 1, f"outer {outer} does not have one {name}")
        return matches[0]

    baseline_jersey = tset_named(TARGET_OUTER, "jersey00")
    baseline_sleeve = tset_named(TARGET_OUTER, "sleeve00")
    comparison_rows: list[dict[str, object]] = []
    for outer, package in sorted(package_by_outer.items(),
                                 key=lambda item: item[1]["logical_name"]):
        jersey = tset_named(outer, "jersey00")
        jersey_mud = tset_named(outer, "jersey00_mud")
        sleeve = tset_named(outer, "sleeve00")
        sleeve_mud = tset_named(outer, "sleeve00_mud")
        digit_rows = txtr_by_outer[outer]
        comparison_rows.append({
            "outer_index": outer,
            "logical_name": package["logical_name"],
            "team": package["roster_current_names"],
            "side_context": package["side_context"],
            "variant_id": package["variant_id"],
            "style_display": package["style_display"],
            "jersey_pixel_sha256": jersey["base_pixel_sha256"],
            "jersey_palette_sha256": jersey["palette_bgra_sha256"],
            "jersey_mud_palette_sha256": jersey_mud["palette_bgra_sha256"],
            "sleeve_pixel_sha256": sleeve["base_pixel_sha256"],
            "sleeve_palette_sha256": sleeve["palette_bgra_sha256"],
            "sleeve_mud_palette_sha256": sleeve_mud["palette_bgra_sha256"],
            "jersey_digit_family_sha256": digest_family(digit_rows, "plain"),
            "helmet_digit_family_sha256": digest_family(digit_rows, "hn"),
            "arm_digit_family_sha256": digest_family(digit_rows, "an"),
            "same_jersey_pixels_as_09H0":
                jersey["base_pixel_sha256"] == baseline_jersey["base_pixel_sha256"],
            "same_jersey_palette_as_09H0":
                jersey["palette_bgra_sha256"] == baseline_jersey["palette_bgra_sha256"],
            "same_sleeve_pixels_as_09H0":
                sleeve["base_pixel_sha256"] == baseline_sleeve["base_pixel_sha256"],
            "same_sleeve_palette_as_09H0":
                sleeve["palette_bgra_sha256"] == baseline_sleeve["palette_bgra_sha256"],
        })

    report: dict[str, object] = {
        "schema": SCHEMA,
        "sources": source_pins,
        "target": {
            "outer_index": TARGET_OUTER,
            "outer_id": TARGET_ID,
            "logical_name": TARGET_NAME,
            "team": "Detroit Lions",
            "selector": "09H0",
            "side_context": "HOME",
            "variant": 0,
            "style": "Current Uniform",
        },
        "fresh_archive_revalidation": {
            "chunk_count": len(resource_rows),
            "kind_sequence": expected_kinds,
            "tset_count": 10,
            "embedded_tset_texture_count": len(clean_tset_references),
            "standalone_txtr_count": len(standalone_evidence),
            "unif": unif_evidence,
            "name": name_evidence,
            "all_wrappers_and_decoded_bodies_re_read_from_pack": True,
            "all_rows_match_canonical_inventories": True,
        },
        "shared_player_scenes": {
            "scope_note": "lo_body, hi_body, and hi_head are shared player SCNE resources in outer 3; they are not embedded in 09H0.IFF.",
            "scenes": target_scenes,
            "selected_material_occurrence_count": len(material_rows),
            "all_selected_texture_pointer_fields_unmapped_on_disk": True,
            "runtime_assignment_required": True,
        },
        "executable_binding": {
            "filename_selection": {
                "producer_function": "0x000615A0",
                "format": "%s%c%d.iff",
                "home_buffer": "0x00B30710",
                "away_buffer": "0x00B30730",
                "home_load_range": "0x00063270..0x0006327A",
                "away_load_range": "0x0006328E..0x00063298",
                "static_target_for_detroit_current_home": "09h0.iff into HOME",
            },
            "texture_cache_initialization": {
                "function": "0x0008E620",
                "cache_base": "0x00B65428",
                "quadrants": "clean/mud x HOME/AWAY; 96 binding-table entries per quadrant",
                "lookup_function": "0x0008E580",
                "lookup_policy": "HOME/AWAY context first for local_first=1, then global fallback only when absent",
            },
            "torso": {
                "body_binder": "0x0008EBB0",
                "material_route_table": "0x004EF3D8 -> index 24 -> UNIF_jersey",
                "texture_cache_slots": [7, 8],
                "binding_table_names": ["jersey00", "jersey00"],
                "binding_table_local_first": True,
                "cache_load_instruction": "0x0008EC1F",
                "material_write_call": "0x0008EC2C -> 0x0008E3F0",
                "material_texture_pointer_write": "material + 0x30 at 0x0008E422",
            },
            "sleeve": {
                "body_binder": "0x0008EBB0",
                "material_route_table": "0x004EF3DC -> index 25 -> UNIF_sleeve",
                "texture_cache_slot": 9,
                "binding_table_name": "sleeve00",
                "binding_table_local_first": True,
                "cache_load_instruction": "0x0008EC4A (0x00B6544C is cache slot 9 in the selected quadrant)",
                "material_write_call": "0x0008EC56 -> 0x0008E3F0",
            },
            "digits": {
                "initializer": "0x0008E620",
                "binder": "0x0008E910",
                "plain_jersey_names": [str(value) for value in range(48, 58)],
                "helmet_names": [f"hn{value}" for value in range(48, 58)],
                "arm_shoulder_names": [f"an{value}" for value in range(48, 58)],
                "plain_group_call": "0x0008F576..0x0008F57B with group 0x0C",
                "helmet_group_call": "0x0008F058..0x0008F05D with group 0x0D",
                "arm_group_call": "0x0008F5AF..0x0008F5B4 with group 0x0E",
                "material_write_function": "0x0008E8D0 (texture pointer at material +0x30; scale words 4.0 and 2.0)",
            },
            "trace_anchor_count": len(anchors),
        },
        "comparison": {
            "package_count": len(comparison_rows),
            "scope": "all 20 Detroit HOME/AWAY variants plus 01A0 and 27H0 cross-team controls",
            "distinct_jersey_pixel_hashes": len({
                row["jersey_pixel_sha256"] for row in comparison_rows
            }),
            "distinct_jersey_palette_hashes": len({
                row["jersey_palette_sha256"] for row in comparison_rows
            }),
            "distinct_sleeve_pixel_hashes": len({
                row["sleeve_pixel_sha256"] for row in comparison_rows
            }),
        },
        "conclusions": [
            {
                "confidence": "high",
                "claim": "Detroit current HOME torso diffuse is 09H0.IFF TSET chunk 1 jersey00 (jersey00_mud for the mud quadrant).",
                "basis": "fresh resource decode plus 0x8EBB0 slot-7/8 to UNIF_jersey dataflow",
            },
            {
                "confidence": "high",
                "claim": "Detroit current HOME sleeve diffuse is 09H0.IFF TSET chunk 3 sleeve00 (sleeve00_mud for the mud quadrant).",
                "basis": "fresh resource decode plus 0x8EBB0 slot-9 to UNIF_sleeve dataflow",
            },
            {
                "confidence": "high",
                "claim": "Front/back jersey digits use standalone 48..57 glyph TXTRs; helmet digits use hn48..hn57; arm/shoulder digits use an48..an57.",
                "basis": "0x8E620 name-table initialization, 0x8E910 group selection, and NUMBER_* player materials",
            },
            {
                "confidence": "high",
                "claim": "bump_jersey and bump_sleeve are detail maps, not an alternate large diffuse torso owner.",
                "basis": "resource names/formats, dimensions, and separate diffuse binder slots",
            },
            {
                "confidence": "high",
                "claim": "The 09H0 chunk-1 negative xemu capture does not prove that another retail resource owns the torso; it contradicts the pinned static bind and leaves runtime selection/loading unresolved.",
                "basis": "no alternate standalone diffuse candidate plus exact filename/context/cache/material dataflow",
            },
        ],
        "runtime_negative_result": {
            "observed": "The accepted exact-span 09H0 chunk-1 CODEX MOD replacement was not visible in Team Select, coin toss, or live play.",
            "static_result": "09H0 chunk 1 jersey00 is nevertheless the executable-selected HOME-first UNIF_jersey source.",
            "resolved": False,
            "do_not_claim": [
                "another retail texture has been proved to own the torso",
                "a persistent cache has been proved",
                "the emulator definitely loaded the intended HOME context",
            ],
        },
        "built_diagnostic_artifact": {
            "purpose": "AWAY-context discriminator; not a fix and not runtime proof",
            "target": "09A0.IFF chunk 1 jersey00/jersey00_mud",
            "target_outer_index": 4002,
            "target_outer_id": "0x07e10847",
            "xiso_path": "/media/noah/Storage/.codex-tmp/nfl2k5-actual-jersey-binding-away-probe-20260711/ESPN-NFL-2K5-Detroit-AWAY-CODEX-MOD-binding-probe.xiso.iso",
            "xiso_size": 6300499968,
            "xiso_sha256": "ac2a6556b9a6c77724a770c6665d5ea2d4b639e015fea468631a2faa8653b855",
            "manifest_path": "/media/noah/Storage/.codex-tmp/nfl2k5-actual-jersey-binding-away-probe-20260711/workflow_manifest.json",
            "manifest_sha256": "420977b306b14ec1eb1457dab71c0a9c7bc95414b84aeb86c1ce9df4141b3836",
            "replacement_span_sha256": "390c36805ed9ad7c9fbd0d330873bf93cf728cc270a73375fa3460d3967d2f5b",
            "changed_byte_count": 74703,
            "all_non_target_xiso_bytes_identical": True,
            "retail_source_sha256_before_after": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
            "retail_modified": False,
            "xemu_started": False,
            "runtime_visibility_proved": False,
        },
        "next_patch_targets": [
            {
                "priority": 1,
                "target": "09A0.IFF chunk 1 jersey00",
                "purpose": "single-context discriminator for an unexpected AWAY-context selection",
                "safe_with_existing_fixed_span_workflow": True,
                "offline_artifact_built": True,
                "runtime_started_by_this_analysis": False,
            },
            {
                "priority": 2,
                "target": "09H0.IFF chunk 3 sleeve00",
                "purpose": "independently test the adjacent, separately named UNIF_sleeve binding",
                "safe_with_existing_chunk1_only_workflow": False,
                "portme": "PORTME: generalize the fixed-span importer to the proved 128x128 two-reference sleeve TSET before patching.",
            },
            {
                "priority": 3,
                "target": "runtime values at 0x00B30710/0x00B30730 and 0x00B65428 quadrant entries",
                "purpose": "decisively record selected filenames, context objects, and resolved jersey00 pointers",
                "portme": "PORTME: capture these values with a debugger/instrumented emulator; static analysis cannot prove a particular run's live state.",
            },
        ],
        "portme": [
            "PORTME: reconcile the negative emulator capture with live HOME/AWAY, clean/mud, registry, and fallback values.",
            "PORTME: recover the complete TSET registration callback beginning at 0x00045280; its saved Ghidra function boundary remains absent.",
            "PORTME: do not interpret UI labels alone as proof of the live runtime context.",
        ],
    }
    return report, resource_rows, texture_rows, comparison_rows, material_rows


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    result.add_argument("--xbe", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    result.add_argument("--chunk-inventory", type=Path,
                        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"))
    result.add_argument("--uniform-inventory", type=Path,
                        default=Path("reports/assets/nfl2k5_uniform_inventory.json"))
    result.add_argument("--packages", type=Path,
                        default=Path("reports/assets/nfl2k5_uniform_packages.tsv"))
    result.add_argument("--tsets", type=Path,
                        default=Path("reports/assets/nfl2k5_uniform_tset_textures.tsv"))
    result.add_argument("--standalone", type=Path,
                        default=Path("reports/assets/nfl2k5_uniform_standalone_txtr.tsv"))
    result.add_argument("--scne-scenes", type=Path,
                        default=Path("reports/assets/nfl2k5_scne_scenes.tsv"))
    result.add_argument("--scne-materials", type=Path,
                        default=Path("reports/assets/nfl2k5_scne_texture_png_materials.tsv"))
    result.add_argument("--ghidra-trace", type=Path, default=Path(
        "reports/assets/nfl_actual_jersey_binding_ghidra/"
        "nfl_actual_jersey_binding_trace.txt"))
    result.add_argument("--ghidra-pseudo", type=Path, default=Path(
        "reports/assets/nfl_actual_jersey_binding_ghidra/"
        "nfl_actual_jersey_binding_pseudo_c.c"))
    result.add_argument("--output", type=Path,
                        default=Path("reports/assets/nfl2k5_actual_jersey_binding.json"))
    result.add_argument("--resources-tsv", type=Path, default=Path(
        "reports/assets/nfl2k5_actual_jersey_binding_resources.tsv"))
    result.add_argument("--textures-tsv", type=Path, default=Path(
        "reports/assets/nfl2k5_actual_jersey_binding_textures.tsv"))
    result.add_argument("--comparison-tsv", type=Path, default=Path(
        "reports/assets/nfl2k5_actual_jersey_binding_comparison.tsv"))
    result.add_argument("--materials-tsv", type=Path, default=Path(
        "reports/assets/nfl2k5_actual_jersey_binding_materials.tsv"))
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        report, resources, textures, comparison, materials = build(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_tsv(args.resources_tsv, resources, [
            "outer_index", "logical_name", "chunk_index", "kind", "chunk_offset",
            "span_size", "stored_size", "system_bytes", "video_bytes",
            "resource_count", "resource_names", "format_name", "width", "height",
            "role", "span_sha256", "decoded_sha256", "lz_consumed_bytes",
        ])
        write_tsv(args.textures_tsv, textures, [
            "storage_kind", "chunk_index", "reference_index", "name", "role",
            "format_name", "width", "height", "mip_levels", "decoded_sha256",
            "pixel_sha256", "palette_sha256", "rgba_sha256",
        ])
        write_tsv(args.comparison_tsv, comparison, [
            "outer_index", "logical_name", "team", "side_context", "variant_id",
            "style_display", "jersey_pixel_sha256", "jersey_palette_sha256",
            "jersey_mud_palette_sha256", "sleeve_pixel_sha256",
            "sleeve_palette_sha256", "sleeve_mud_palette_sha256",
            "jersey_digit_family_sha256", "helmet_digit_family_sha256",
            "arm_digit_family_sha256", "same_jersey_pixels_as_09H0",
            "same_jersey_palette_as_09H0", "same_sleeve_pixels_as_09H0",
            "same_sleeve_palette_as_09H0",
        ])
        write_tsv(args.materials_tsv, materials, [
            "scene_name", "scene_index", "chunk_index", "material_index",
            "material_name", "material_offset", "texture_pointer_field",
            "mapping_status",
        ])
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps({
        "schema": report["schema"],
        "target": report["target"],
        "resource_chunks": len(resources),
        "textures": len(textures),
        "comparison_packages": len(comparison),
        "selected_materials": len(materials),
        "runtime_negative_resolved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
