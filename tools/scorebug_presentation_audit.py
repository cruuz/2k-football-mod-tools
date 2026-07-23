#!/usr/bin/env python3
"""Build a bounded, reproducible NFL 2K5/APF 2K8 scorebug audit.

The report deliberately separates three things which are easy to conflate:

* a resource being present on disc;
* compiled code/data owning or registering that resource; and
* a replacement having been observed in a running title.

This tool is read-only.  It validates the retail archives and executables,
recovers the NFL material-to-texture table, inventories the APF scorebug scene
family, and records the exact fixed allocations a future public editor may use.

The v1 JSON is also a frozen authority for retained NFL copied-XISO builds.
Its APF ``digital_font`` capability labels describe the original static-audit
boundary and are intentionally not rewritten in place.  Current consumers
must compose it with the separately pinned digital-font layout and round-trip
reports, as ``mod_editor.core.presentation_inspection`` does.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

import apf_inner
import apf_outer
import nfl_outer
from nfl_txtr import Chunk, decode_chunk, parse_texture
from xbe_info import Xbe


SCHEMA = "vc_scorebug_presentation_audit/v1"
NFL_INDEX = Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
NFL_XBE = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe")
NFL_XISO = Path("ESPN NFL 2K5 (USA).xiso.iso")
APF_INDEX = Path("extracted/All-Pro Football 2K8 (USA)/0A")
APF_XEX = Path("extracted/All-Pro Football 2K8 (USA)/default.xex")
APF_PE = Path("/tmp/apf2k8_default.pe")
NFL_TEXTURES = Path("reports/assets/nfl2k5_all_txtr_inventory_v2.json")
NFL_SCENES = Path("reports/assets/nfl2k5_scne_scenes.tsv")
NFL_GLTF = Path("assets/intermediate/nfl2k5/models/manifest.json")
APF_INNER = Path("reports/manifests/apf_inner.json")
APF_SCENES = Path("reports/assets/apf_scene_inventory.json")
APF_GLTF = Path("assets/intermediate/apf2k8/models/manifest.json")

NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
NFL_INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
NFL_XISO_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"

NFL_TARGETS = {
    "digital_font": (3, 46, "shared global digit/font atlas"),
    "shield_espn": (346, 26, "ESPN strip bound by the field-scorebug table"),
    "score_buga": (346, 53, "field-scorebug frame/corner atlas"),
}

APF_SCOREBUG_NAMES = (
    "scorebug_bottombar",
    "scorebug_titlebar",
    "scorebug_team_logos",
    "scorebug_infobar",
    "scorebug_messages",
    "scorebug_blackbar",
    "scorebug_statbar",
)

APF_DESCRIPTOR_SITES = {
    "scorebug_infobar": 0x84EAD3F8,
    "scorebug_messages": 0x84EAD424,
    "scorebug_statbar": 0x84EAD450,
    "scorebug_titlebar": 0x84EAD47C,
    "scorebug_bottombar": 0x84EAD4A8,
    "scorebug_team_logos": 0x84EAD4D4,
    "scorebug_blackbar": 0x84EAD500,
}


class AuditError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    require(isinstance(value, dict), f"{path} is not a JSON object")
    return value


def xbe_u32(xbe: Xbe, address: int) -> int:
    return struct.unpack_from("<I", xbe.data, xbe.va_to_offset(address, 4))[0]


def xbe_wstring(xbe: Xbe, address: int) -> str:
    require(address != 0, "null XBE string pointer")
    offset = xbe.va_to_offset(address, 2)
    output: list[str] = []
    for index in range(256):
        value = struct.unpack_from("<H", xbe.data, offset + index * 2)[0]
        if value == 0:
            return "".join(output)
        output.append(chr(value))
    raise AuditError(f"unterminated XBE UTF-16LE string at 0x{address:08X}")


def load_nfl_texture_rows(path: Path) -> dict[tuple[int, int], dict[str, Any]]:
    report = read_json(path)
    require(report.get("schema") in {
        "nfl2k5_all_txtr_inventory/v1", "nfl2k5_all_txtr_inventory/v2"
    }, "unexpected NFL texture inventory schema")
    rows = report.get("textures")
    require(isinstance(rows, list), "NFL texture inventory has no texture rows")
    return {(int(row["outer_index"]), int(row["chunk_index"])): row for row in rows}


def load_nfl_scene(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    matches = [row for row in rows if row["outer_index"] == "346" and
               row["chunk_index"] == "78" and row["name"] == "score_bug"]
    require(len(matches) == 1, "NFL score_bug SCNE inventory identity changed")
    return matches[0]


def load_gltf_export(path: Path, outer: int, inner: int, name: str) -> dict[str, Any]:
    report = read_json(path)
    exports = report.get("exports")
    require(isinstance(exports, list), f"{path} has no exports")
    matches = [row for row in exports
               if int(row.get("outer_index", row.get("outer_table_index", -1))) == outer and
               int(row.get("chunk_index", row.get("inner_file_index", -1))) == inner and
               row.get("scene_name", row.get("root_name")) == name]
    require(len(matches) == 1 and matches[0].get("status") == "exported",
            f"glTF export identity changed for {outer}:{inner}:{name}")
    return matches[0]


def nfl_report(args: argparse.Namespace) -> dict[str, Any]:
    require(digest_file(args.nfl_xbe) == NFL_XBE_SHA256, "NFL XBE hash changed")
    require(digest_file(args.nfl_index) == NFL_INDEX_SHA256, "NFL index hash changed")
    require(digest_file(args.nfl_xiso) == NFL_XISO_SHA256, "NFL XISO hash changed")
    archive = nfl_outer.parse_archive(args.nfl_index)
    rows = load_nfl_texture_rows(args.nfl_textures)

    texture_targets: list[dict[str, Any]] = []
    for name, (outer_index, chunk_index, role) in NFL_TARGETS.items():
        row = dict(rows[(outer_index, chunk_index)])
        require(row["name"] == name and row["format_name"] == "P8" and
                int(row["mip_levels"]) == 1 and bool(row["compressed"]),
                f"NFL {name} target layout changed")
        entry = archive.entries[outer_index]
        span_size = 32 + int(row["stored_size"])
        span = nfl_outer.read_entry_range(
            archive, entry, int(row["chunk_offset"]), span_size)
        chunk = Chunk(0, 0, "TXTR", int(row["stored_size"]),
                      int(row["system_bytes"]), int(row["video_bytes"]),
                      0xFEEDBEEF, struct.unpack_from("<I", span, 20)[0], 0, 0)
        decoded, info = decode_chunk(span, chunk)
        texture = parse_texture(decoded, chunk)
        require(info is not None and texture.name == name and
                digest_bytes(decoded) == row["decoded_sha256"],
                f"NFL {name} decoded identity changed")
        segment = entry.segments[0]
        require(len(entry.segments) == 1 and segment.pack_name == "0",
                f"NFL {name} unexpectedly crosses pack volumes")
        # XDVDFS places vc_53450030/0 at sector 796479 in the pinned XISO.
        xiso_pack_offset = 796479 * 2048
        absolute = xiso_pack_offset + segment.pack_offset + int(row["chunk_offset"])
        texture_targets.append({
            **row,
            "role": role,
            "span_size": span_size,
            "span_sha256": digest_bytes(span),
            "pack_path": "vc_53450030/0",
            "pack_size": args.nfl_index.stat().st_size,
            "pack_sha256": NFL_INDEX_SHA256,
            "pack_offset": segment.pack_offset + int(row["chunk_offset"]),
            "xiso_pack_sector": 796479,
            "xiso_pack_byte_offset": xiso_pack_offset,
            "xiso_absolute_span_offset": absolute,
            "fixed_decoded_allocation": int(row["system_bytes"]) +
                                        int(row["video_bytes"]),
            "fixed_stored_allocation": int(row["stored_size"]),
            "lz_stream_tag": info.stream_tag,
            "lz_offset_bits": info.offset_bits,
            "lz_consumed_bytes": info.consumed_bytes,
            "safe_write_class": (
                "fixed_span_png_writeback_ready" if name != "digital_font" else
                "fixed_span_png_writeback_ready_global_side_effects"
            ),
        })

    xbe = Xbe(args.nfl_xbe)
    bindings: list[dict[str, Any]] = []
    for index, texture_pointer_site in enumerate(range(0x00A95C64, 0x00A95CBC, 8)):
        material_pointer = xbe_u32(xbe, texture_pointer_site - 4)
        texture_pointer = xbe_u32(xbe, texture_pointer_site)
        bindings.append({
            "index": index,
            "record_address": f"0x{texture_pointer_site - 4:08X}",
            "material_pointer": f"0x{material_pointer:08X}",
            "material": xbe_wstring(xbe, material_pointer),
            "texture_pointer": f"0x{texture_pointer:08X}",
            "texture": xbe_wstring(xbe, texture_pointer),
        })
    require(len(bindings) == 11 and
            [row["texture"] for row in bindings].count("score_buga") == 9 and
            [row["texture"] for row in bindings].count("shield_espn") == 2,
            "NFL material-to-texture binding table changed")

    scene = load_nfl_scene(args.nfl_scenes)
    gltf = load_gltf_export(args.nfl_gltf, 346, 78, "score_bug")
    entry = archive.entries[346]
    scene_span = nfl_outer.read_entry_range(
        archive, entry, int(scene["chunk_offset"]), 32 + int(scene["stored_size"]))
    require(digest_bytes(scene_span[32:]) != "", "unreachable digest guard")

    return {
        "source": {
            "xbe": {"path": str(args.nfl_xbe), "sha256": NFL_XBE_SHA256},
            "archive_index": {"path": str(args.nfl_index),
                              "size": args.nfl_index.stat().st_size,
                              "sha256": NFL_INDEX_SHA256},
            "xiso": {"path": str(args.nfl_xiso),
                     "size": args.nfl_xiso.stat().st_size,
                     "sha256": NFL_XISO_SHA256},
        },
        "field_scorebug_package": {
            "outer_index": 346, "outer_id": "0x00b6926c", "outer_head": "SMCD",
            "outer_size": entry.size, "pack_name": "0",
            "pack_offset": entry.segments[0].pack_offset,
            "named_layt_or_mrks_dependency_proved": False,
            "composition_boundary": (
                "The XBE owner and SCNE drive field-scorebug composition; no separate "
                "scorebug-named LAYT/MRKS resource is proved in the Xbox catalog."
            ),
            "score_bug_scne": {
                "chunk_index": 78, "chunk_offset": int(scene["chunk_offset"]),
                "stored_size": int(scene["stored_size"]),
                "system_bytes": int(scene["system_bytes"]),
                "video_bytes": int(scene["video_bytes"]),
                "span_size": len(scene_span), "span_sha256": digest_bytes(scene_span),
                "materials": int(scene["materials_count"]),
                "nodes": int(scene["nodes_count"]), "shapes": int(scene["shapes_count"]),
                "decoded_sha256": scene["decoded_sha256"],
                "gltf": gltf,
                "safe_write_class": "gltf_extract_only_no_scne_serializer",
            },
        },
        "texture_targets": texture_targets,
        "compiled_owner": {
            "material_texture_binding_function": "0x000FC1A0",
            "initialization_function": "0x000FCCD0",
            "initialization_caller": "0x00064710",
            "update_draw_function": "0x000FCE70",
            "update_draw_caller": "0x00064CD0",
            "binding_table_range": "0x00A95C60..0x00A95CB7",
            "bindings": bindings,
            "static_live_classification": "code_owned_field_scorebug",
            "runtime_replacement_visibility_proved": False,
        },
        "adjacent_presentation": {
            "same_smcd_texture_names": [
                "replayicons", "overlay_colors", "endQTR_textures", "z_ESPN_bug"
            ],
            "same_smcd_scene_names": ["replayOverlay", "replayOverlay2"],
            "code_owned_archive_names": ["overlay.iff"],
            "code_owned_audio_bank_names": ["overlayaudio"],
            "classification": (
                "replay/end-quarter presentation is adjacent but not part of the "
                "field scorebug texture binding table"
            ),
        },
    }


def find_apf_outer(report: dict[str, Any], table_index: int) -> dict[str, Any]:
    matches = [row for row in report["iff_entries"] if int(row["table_index"]) == table_index]
    require(len(matches) == 1, f"APF outer {table_index} missing")
    return matches[0]


def apf_file(outer: dict[str, Any], index: int, name: str) -> dict[str, Any]:
    matches = [row for row in outer["files"] if int(row["index"]) == index and
               row["name"] == name]
    require(len(matches) == 1, f"APF resource {outer['table_index']}:{index}:{name} missing")
    return matches[0]


def apf_report(args: argparse.Namespace) -> dict[str, Any]:
    require(digest_file(args.apf_xex) == APF_XEX_SHA256, "APF XEX hash changed")
    require(digest_file(args.apf_pe) == APF_PE_SHA256, "APF decoded PE hash changed")
    inner = read_json(args.apf_inner)
    global_outer = find_apf_outer(inner, 1310)
    season_outer = find_apf_outer(inner, 1215)
    gamedata_outer = find_apf_outer(inner, 659)
    halftime_outer = find_apf_outer(inner, 516)
    franchise_outer = find_apf_outer(inner, 810)
    halftime_stats_outer = find_apf_outer(inner, 929)
    overlay_audio_outer = find_apf_outer(inner, 1410)
    gltf_manifest = read_json(args.apf_gltf)
    gltf_exports = gltf_manifest["exports"]

    pe = args.apf_pe.read_bytes()
    scene_resources: list[dict[str, Any]] = []
    file_by_name = {row["name"]: row for row in global_outer["files"]}
    for name in APF_SCOREBUG_NAMES:
        file = file_by_name[name]
        export = load_gltf_export(args.apf_gltf, 1310, int(file["index"]), name)
        site = APF_DESCRIPTOR_SITES[name]
        offset = site - 0x82000000
        words = struct.unpack_from(">11I", pe, offset)
        require(words[0] == int(file["id"], 16) and words[1] == 0x18FD4C05,
                f"APF descriptor candidate changed for {name}")
        scene_resources.append({
            "name": name, "inner_index": int(file["index"]), "id": file["id"],
            "parts": file["parts"],
            "total_part_bytes": sum(int(part["length"]) for part in file["parts"]),
            "gltf": export,
            "compiled_descriptor_candidate": {
                "address": f"0x{site:08X}", "stride": 0x2C,
                "bytes_sha256": digest_bytes(pe[offset:offset + 0x2C]),
                "words_be": [f"0x{word:08X}" for word in words],
                "type_or_factory_id": "0x18FD4C05",
            },
            "safe_write_class": "gltf_extract_only_no_scne_serializer",
        })

    # Decode only global.iff DRAM to validate the 224-byte DXT5A metadata part.
    archive = apf_outer.parse_archive(args.apf_index)
    entry = archive.entries[1310]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        digital = record.files[246]
        require(digital.name == "digital_font" and digital.type_name == "TXTR",
                "APF digital_font identity changed")
        dram = apf_inner.decode_block(reader, record, 0, 256 * 1024 * 1024)
        part = digital.parts[0]
        header = dram[part.offset:part.offset + part.length]
        metadata = apf_inner.parse_txtr_metadata(header)
    require(metadata["format_name"] == "DXT5A" and metadata["width"] == 128 and
            metadata["height"] == 128 and metadata["tiled"] is True and
            metadata["endianness_name"] == "8in16",
            "APF digital_font layout changed")

    game_cast = apf_file(season_outer, 14, "game_cast_scorebug")
    game_cast_export = load_gltf_export(args.apf_gltf, 1215, 14, "game_cast_scorebug")
    game_cast_site = 0x84EAD638
    game_cast_offset = game_cast_site - 0x82000000
    require(struct.unpack_from(">I", pe, game_cast_offset)[0] == int(game_cast["id"], 16),
            "APF GameCast descriptor candidate changed")

    overlay_files = []
    for row in overlay_audio_outer["files"]:
        if row["type_name"] == "AUDO":
            overlay_files.append({
                "index": row["index"], "name": row["name"], "id": row["id"],
                "parts": row["parts"],
            })
    require(len(overlay_files) == 17, "APF sfx_overlay AUDO count changed")

    adjacent = []
    for outer, names in (
        (gamedata_outer, ("replayoverlay", "replayoverlay2", "replay_wipe_2k",
                          "overlayaudio", "replayicons", "instantreplay")),
        (halftime_outer, ("halftime_ticker", "halftime_show_wipe",
                          "halftime_team_comparison", "text_halftime_show")),
    ):
        rows = {row["name"]: row for row in outer["files"]}
        for name in names:
            row = rows[name]
            adjacent.append({
                "outer_index": outer["table_index"],
                "outer_names": [item["name"] for item in outer["outer_name_candidates"]],
                "inner_index": row["index"], "name": name,
                "type_name": row["type_name"], "id": row["id"], "parts": row["parts"],
            })
    for outer, index, name, use_class in (
        (franchise_outer, 101, "scorepanel",
         "franchise_menu_score_panel_not_field_hud"),
        (halftime_stats_outer, 9, "halftime_team_stats",
         "halftime_mrks_not_field_hud"),
    ):
        row = apf_file(outer, index, name)
        adjacent.append({
            "outer_index": outer["table_index"],
            "outer_names": [item["name"] for item in outer["outer_name_candidates"]],
            "inner_index": row["index"], "name": name,
            "type_name": row["type_name"], "id": row["id"],
            "parts": row["parts"], "use_class": use_class,
        })

    return {
        "source": {
            "xex": {"path": str(args.apf_xex), "sha256": APF_XEX_SHA256},
            "decoded_pe": {"path": args.apf_pe.name, "sha256": APF_PE_SHA256},
            "archive_index": {"path": str(args.apf_index),
                              "size": args.apf_index.stat().st_size,
                              "sha256": digest_file(args.apf_index)},
        },
        "field_scorebug_package": {
            "outer_index": 1310, "outer_id": global_outer["name_id"],
            "outer_names": [row["name"] for row in global_outer["outer_name_candidates"]],
            "outer_size": global_outer["outer_size"], "segments": global_outer["segments"],
            "blocks": global_outer["blocks"], "resources": scene_resources,
            "compiled_descriptor_candidate_range": "0x84EAD3F8..0x84EAD51B",
            "compiled_descriptor_stride": 0x2C,
            "same_name_layt_or_mrks_resources": [],
            "composition_boundary": (
                "The complete named global.iff catalog has no scorebug-named LAYT "
                "or MRKS peer; compiled behavior composes these SCNE components."
            ),
            "static_live_classification": "compiled_global_scorebug_scene_family",
            "runtime_replacement_visibility_proved": False,
        },
        "digital_font": {
            "outer_index": 1310, "inner_index": 246, "id": "0x899d899d",
            "parts": file_by_name["digital_font"]["parts"], "metadata": metadata,
            "safe_write_class": "metadata_only_dxt5a_codec_and_import_missing",
        },
        "season_gamecast_scorebug": {
            "outer_index": 1215, "outer_id": season_outer["name_id"],
            "outer_names": [row["name"] for row in season_outer["outer_name_candidates"]],
            "inner_index": 14, "id": game_cast["id"], "parts": game_cast["parts"],
            "gltf": game_cast_export,
            "compiled_descriptor_candidate": {
                "address": "0x84EAD638",
                "bytes_sha256": digest_bytes(pe[game_cast_offset:game_cast_offset + 0x2C]),
            },
            "use_class": "season_gamecast_menu_not_field_scorebug",
            "safe_write_class": "gltf_extract_only_no_scne_serializer",
        },
        "replay_halftime_presentation": {
            "adjacent_resources": adjacent,
            "sfx_overlay": {
                "outer_index": 1410, "outer_id": overlay_audio_outer["name_id"],
                "outer_names": [row["name"] for row in
                                overlay_audio_outer["outer_name_candidates"]],
                "outer_size": overlay_audio_outer["outer_size"],
                "audo_count": len(overlay_files), "audio": overlay_files,
                "codec": "XMA1 per existing APF audio inventory",
                "safe_write_class": "wav_extract_ready_xma_import_repack_not_closed",
            },
            "code_owners": {
                "overlay_iff_loader": "0x849D7A48",
                "sfx_overlay_iff_loader": "0x849DA728",
                "replay_wipe_controller": "0x847B7858",
                "overlay_event_name_table_function": "0x84A80AA8",
            },
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    nfl = nfl_report(args)
    apf = apf_report(args)
    return {
        "schema": SCHEMA,
        "scope": {
            "writes_originals": False, "launches_emulator": False,
            "runtime_capture_performed": False, "native_port_claimed": False,
            "nfl_field_scorebug_code_owner_proved": True,
            "apf_global_scorebug_descriptor_family_proved": True,
        },
        "nfl2k5": nfl,
        "apf2k8": apf,
        "cross_title_lineage": {
            "shared_exact_executable_strings": ["overlay.iff", "scoreboard"],
            "shared_concepts": [
                "field scorebug", "digital_font", "replay overlay", "halftime ticker",
                "team comparison", "replay wipe", "overlay audio bank",
            ],
            "structural_change": (
                "NFL 2K5 uses one monolithic score_bug SCNE plus P8 atlases; APF 2K8 "
                "splits the field HUD into seven registered SCNE components and keeps "
                "a separate season GameCast scorebug."
            ),
            "not_proved": (
                "No byte-identical SCNE body or automatic cross-title model conversion "
                "is claimed; the Xbox and Xenon scene formats differ."
            ),
        },
        "editor_capability": {
            "safe_now": [
                "NFL score_buga PNG extraction and fixed-span PNG write-back",
                "NFL shield_espn PNG extraction and fixed-span PNG write-back",
                "NFL digital_font fixed-span PNG write-back with global side-effect warning",
                "NFL/APF scorebug SCNE extraction to glTF for inspection",
                "APF overlay XMA extraction/standard-audio conversion through existing tools",
            ],
            "requires_new_binary_serializer": [
                "NFL glTF back to SCNE geometry/layout",
                "APF glTF back to SCNE plus whole-IFF H7A rebuild",
                "APF DXT5A digital_font PNG codec/import",
                "APF replacement XMA encode and exact archive repack validation",
            ],
            "requires_executable_behavior_patch": [
                "new scorebug fields or logic",
                "moving fields beyond recoverable SCNE transforms when code clamps/overwrites them",
                "new stat sources, timing, visibility rules, replay triggers, or presentation sequencing",
                "changing text formatting, score limits, clock logic, or dynamically selected team data",
            ],
        },
        "portme": [
            "PORTME(NFL SCNE 346:78): implement a byte-exact glTF-to-SCNE writer before exposing geometry write-back.",
            "PORTME(APF SCNE 1310:106/131/156/235/250/262/360): implement SCNE serialization and bounded H7A IFF rebuild.",
            "PORTME(APF TXTR 1310:246): implement Xenos DXT5A decode/encode, tiling, and 8-in-16 round-trip.",
            "PORTME(runtime): capture unmodified and modified scorebugs in xemu/Xenia before claiming on-screen replacement visibility.",
        ],
    }


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for row in report["nfl2k5"]["texture_targets"]:
        rows.append({
            "title": "nfl2k5", "outer": row["outer_index"],
            "inner": row["chunk_index"], "name": row["name"], "kind": "TXTR",
            "format": row["format_name"], "width": row["width"],
            "height": row["height"], "stored": row["stored_size"],
            "decoded": row["fixed_decoded_allocation"],
            "classification": row["safe_write_class"],
        })
    nfl_scene = report["nfl2k5"]["field_scorebug_package"]["score_bug_scne"]
    rows.append({"title": "nfl2k5", "outer": 346, "inner": 78,
                 "name": "score_bug", "kind": "SCNE", "format": "Xbox_SCNE",
                 "width": "", "height": "", "stored": nfl_scene["stored_size"],
                 "decoded": nfl_scene["system_bytes"],
                 "classification": nfl_scene["safe_write_class"]})
    for row in report["apf2k8"]["field_scorebug_package"]["resources"]:
        rows.append({"title": "apf2k8", "outer": 1310, "inner": row["inner_index"],
                     "name": row["name"], "kind": "SCNE", "format": "Xenon_SCNE",
                     "width": "", "height": "", "stored": "",
                     "decoded": row["total_part_bytes"],
                     "classification": row["safe_write_class"]})
    fieldnames = ["title", "outer", "inner", "name", "kind", "format", "width",
                  "height", "stored", "decoded", "classification"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nfl-index", type=Path, default=NFL_INDEX)
    parser.add_argument("--nfl-xbe", type=Path, default=NFL_XBE)
    parser.add_argument("--nfl-xiso", type=Path, default=NFL_XISO)
    parser.add_argument("--nfl-textures", type=Path, default=NFL_TEXTURES)
    parser.add_argument("--nfl-scenes", type=Path, default=NFL_SCENES)
    parser.add_argument("--nfl-gltf", type=Path, default=NFL_GLTF)
    parser.add_argument("--apf-index", type=Path, default=APF_INDEX)
    parser.add_argument("--apf-xex", type=Path, default=APF_XEX)
    parser.add_argument("--apf-pe", type=Path, default=APF_PE)
    parser.add_argument("--apf-inner", type=Path, default=APF_INNER)
    parser.add_argument("--apf-scenes", type=Path, default=APF_SCENES)
    parser.add_argument("--apf-gltf", type=Path, default=APF_GLTF)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build(args)
        args.json_out.write_bytes(canonical_json(report))
        write_tsv(args.tsv_out, report)
        print("SCOREBUG_PRESENTATION_AUDIT_OK "
              "nfl_bindings=11 apf_field_scenes=7 runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
