#!/usr/bin/env python3
"""Deterministic NFL 2K5 -> APF 2K8 Sound Test lineage/remnant audit.

This is a read-only static audit.  It does not patch an executable, launch an
emulator, or claim that APF's orphaned state is runtime reachable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from menu_state_trace import APF_BASE, APF_PE_SHA256, ApfImage, XbeImage


SCHEMA = "vc_audio_test_remnant/v1"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_INNER_SHA256 = "b57772a88e969db47aca6add24b1387ab2470b53cdb2f6f21bd4a3d8999fb6d1"
NFL_CHUNKS_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
LINEAGE_SHA256 = "12efe383009706725b76299e64c81a2145c69335aceba85347b6e6d272318e69"

NFL_OPTIONS_DESCRIPTOR = 0x00503288
NFL_SOUND_DESCRIPTOR = 0x0052BFA0
APF_OPTIONS_DESCRIPTOR = 0x820F4578
APF_SOUND_DESCRIPTOR = 0x82006870


class AuditError(RuntimeError):
    pass


def hx(value: int | None) -> str | None:
    return None if value is None else f"0x{value:08X}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AuditError(f"{label}: expected {expected!r}, got {actual!r}")


def pointer_count(data: bytes, value: int, byteorder: str) -> int:
    return data.count(value.to_bytes(4, byteorder))


def find_utf16(apf_data: bytes, text: str) -> list[int]:
    needle = (text + "\0").encode("utf-16be")
    result: list[int] = []
    cursor = 0
    while True:
        offset = apf_data.find(needle, cursor)
        if offset < 0:
            return result
        result.append(APF_BASE + offset)
        cursor = offset + 1


def scan_ppc_materializations(data: bytes, target: int) -> list[dict[str, Any]]:
    """Find conventional lis + nearby addi/ori absolute-address materializations."""
    start = 0x84630000
    after_last = 0x84D0904C
    high = ((target + 0x8000) >> 16) & 0xFFFF
    low = target & 0xFFFF
    result: list[dict[str, Any]] = []
    for address in range(start, after_last, 4):
        offset = address - APF_BASE
        word = struct.unpack_from(">I", data, offset)[0]
        if word >> 26 != 15 or ((word >> 16) & 31) != 0 or (word & 0xFFFF) != high:
            continue
        base_register = (word >> 21) & 31
        for distance in range(1, 9):
            second_address = address + distance * 4
            second = struct.unpack_from(">I", data, second_address - APF_BASE)[0]
            opcode = second >> 26
            if opcode == 14 and ((second >> 16) & 31) == base_register and (second & 0xFFFF) == low:
                result.append({
                    "lis": hx(address),
                    "combine": hx(second_address),
                    "kind": "addi",
                    "base_register": base_register,
                    "target_register": (second >> 21) & 31,
                })
            if opcode == 24 and ((second >> 21) & 31) == base_register and (second & 0xFFFF) == low:
                result.append({
                    "lis": hx(address),
                    "combine": hx(second_address),
                    "kind": "ori",
                    "base_register": base_register,
                    "target_register": (second >> 16) & 31,
                })
    return result


def decode_nfl_options(image: XbeImage) -> dict[str, Any]:
    words = [image.u32(NFL_OPTIONS_DESCRIPTOR + index * 4) for index in range(8)]
    expect(image.utf16(words[0]), "Options", "NFL Options title")
    expect(image.utf16(words[6]), "navigation", "NFL Options layout")
    rows: list[dict[str, Any]] = []
    sentinel = None
    for index in range(32):
        address = words[4] + index * 0x34
        kind = image.u32(address)
        if kind == 3:
            sentinel = address
            break
        label_pointer = image.u32(address + 4)
        target = image.u32(address + 8)
        rows.append({
            "index": index,
            "address": hx(address),
            "type": kind,
            "label_pointer": hx(label_pointer),
            "label": image.utf16(label_pointer),
            "target": hx(target),
            "target_title": image.utf16(image.u32(target)) if target else None,
        })
    if sentinel is None:
        raise AuditError("NFL Options row sentinel not found")
    expected_labels = [
        "Game Options", "Difficulty", "Presentation", "Weather", "Penalties",
        "Controller Setup", "Load / Save", "Online Options", "Audio Test",
    ]
    expect([row["label"] for row in rows], expected_labels, "NFL Options labels")
    expect(rows[-1]["target"], hx(NFL_SOUND_DESCRIPTOR), "NFL Audio Test target")
    expect(rows[-1]["target_title"], "Sound Test", "NFL Audio Test target title")
    return {
        "address": hx(NFL_OPTIONS_DESCRIPTOR),
        "title": "Options",
        "row_base": hx(words[4]),
        "row_stride": 0x34,
        "row_count": len(rows),
        "sentinel_address": hx(sentinel),
        "rows": rows,
    }


def decode_nfl_sound(image: XbeImage, xbe_data: bytes) -> dict[str, Any]:
    words = [image.u32(NFL_SOUND_DESCRIPTOR + index * 4) for index in range(8)]
    expect(image.utf16(words[0]), "Sound Test", "NFL Sound Test title")
    expect(image.utf16(words[6]), "gamesound", "NFL Sound Test layout")
    events: list[dict[str, Any]] = []
    cursor = words[1]
    for index in range(16):
        event = image.u32(cursor + index * 8)
        action = image.u32(cursor + index * 8 + 4)
        if event == 0:
            break
        action_type = image.u32(action)
        callback_offset = 0x0C if action_type == 3 else 4
        events.append({
            "event": event,
            "action": hx(action),
            "action_type": action_type,
            "callback": hx(image.u32(action + callback_offset)),
            "callback_field": f"+0x{callback_offset:02X}",
        })
    expect([row["event"] for row in events], [4, 6, 7, 1, 2], "NFL Sound Test events")
    expect(
        [row["callback"] for row in events],
        [hx(value) for value in (0x00356560, 0x00356860, 0x00356570, 0x003563E0, 0x00356530)],
        "NFL Sound Test callbacks",
    )
    code_ranges = []
    for first, after_last, name in (
        (0x003563E0, 0x00356530, "construct_and_load"),
        (0x00356530, 0x00356560, "teardown"),
        (0x00356570, 0x00356860, "draw"),
        (0x00356860, 0x00356A40, "update"),
    ):
        body = image.read(first, after_last - first)
        code_ranges.append({
            "name": name,
            "first": hx(first),
            "after_last": hx(after_last),
            "size": len(body),
            "sha256": sha256_bytes(body),
        })
    expect(image.read(0x00356419, 10).hex(), "ba0840eb00b9ec3feb00", "NFL package/title load anchor")
    return {
        "address": hx(NFL_SOUND_DESCRIPTOR),
        "title": "Sound Test",
        "event_table": hx(words[1]),
        "default_callback": hx(words[2]),
        "layout": "gamesound",
        "layout_context": hx(words[7]),
        "events": events,
        "absolute_pointer_count_in_xbe": pointer_count(xbe_data, NFL_SOUND_DESCRIPTOR, "little"),
        "code_ranges": code_ranges,
        "package_load_anchor": {
            "address": hx(0x00356419),
            "bytes": image.read(0x00356419, 10).hex(),
            "package_name": "audiotestmenu.iff",
            "state_name": "AUDIOTESTMENU",
        },
    }


def decode_apf_options(image: ApfImage) -> dict[str, Any]:
    words = [image.u32(APF_OPTIONS_DESCRIPTOR + index * 4) for index in range(18)]
    expect(image.utf16(words[0]), "Options", "APF Options title")
    expect(image.utf16(words[11]), "quicknav", "APF Options layout")
    rows: list[dict[str, Any]] = []
    for index in range(words[15]):
        address = words[7] + index * 0x60
        label_pointer = image.u32(address + 4)
        target = image.u32(address + 8)
        rows.append({
            "index": index,
            "address": hx(address),
            "type": image.u32(address),
            "label_pointer": hx(label_pointer),
            "label": image.utf16(label_pointer),
            "target": hx(target),
            "target_title": image.utf16(image.u32(target)) if target else None,
        })
    expect(
        [row["label"] for row in rows],
        ["Game Options", "Difficulty", "Presentation", "Ticker", "Penalties", "Controller Setup", "Load / Save"],
        "APF Options labels",
    )
    expect(any(row["target"] == hx(APF_SOUND_DESCRIPTOR) for row in rows), False, "APF Options Sound Test route")
    return {
        "address": hx(APF_OPTIONS_DESCRIPTOR),
        "title": "Options",
        "row_base": hx(words[7]),
        "row_stride": 0x60,
        "row_count": len(rows),
        "rows": rows,
    }


def decode_apf_sound(image: ApfImage, pe_data: bytes) -> dict[str, Any]:
    words = [image.u32(APF_SOUND_DESCRIPTOR + index * 4) for index in range(18)]
    expect(image.utf16(words[0]), "Sound Test", "APF Sound Test title")
    expect(image.utf16(words[1]), "AudioTestMenu", "APF Sound Test transition")
    expect(image.utf16(words[11]), "gamesound", "APF Sound Test layout")
    events: list[dict[str, Any]] = []
    event_table = words[2]
    for index in range(16):
        event = image.u32(event_table + index * 8)
        action = image.u32(event_table + index * 8 + 4)
        if event == 0:
            break
        events.append({
            "event": event,
            "action": hx(action),
            "action_type": image.u32(action),
            "callback": hx(image.u32(action + 4)),
        })
    expect([row["event"] for row in events], [4, 5, 6], "APF Sound Test events")
    expect(
        [row["callback"] for row in events],
        [hx(value) for value in (0x846A05C0, 0x846A0528, 0x846A0B48)],
        "APF Sound Test callbacks",
    )
    ranges = []
    for first, after_last, name in (
        (0x846A0528, 0x846A05C0, "teardown"),
        (0x846A05C0, 0x846A0810, "construct_and_load"),
        (0x846A0B48, 0x846A1028, "update_input_draw"),
    ):
        body = image.read(first, after_last - first)
        ranges.append({
            "name": name,
            "first": hx(first),
            "after_last": hx(after_last),
            "size": len(body),
            "sha256": sha256_bytes(body),
        })
    exact_count = pointer_count(pe_data, APF_SOUND_DESCRIPTOR, "big")
    materializations = scan_ppc_materializations(pe_data, APF_SOUND_DESCRIPTOR)
    expect(exact_count, 0, "APF Sound Test absolute pointer count")
    expect(materializations, [], "APF Sound Test conventional PPC address materializations")
    return {
        "address": hx(APF_SOUND_DESCRIPTOR),
        "title": "Sound Test",
        "transition": "AudioTestMenu",
        "event_table": hx(words[2]),
        "default_callback": hx(words[3]),
        "layout": "gamesound",
        "layout_context": hx(words[13]),
        "events": events,
        "absolute_pointer_count_in_pe": exact_count,
        "conventional_lis_addi_or_ori_materializations": materializations,
        "control_counts": {
            "main_menu_descriptor_absolute_pointers": pointer_count(pe_data, 0x820F4350, "big"),
            "options_descriptor_absolute_pointers": pointer_count(pe_data, APF_OPTIONS_DESCRIPTOR, "big"),
            "main_menu_descriptor_materializations": len(scan_ppc_materializations(pe_data, 0x820F4350)),
        },
        "code_ranges": ranges,
        "static_reachability": "no standard Options row, exact absolute pointer, or conventional lis+addi/ori materialization found",
        "reachability_boundary": "computed, indexed, hashed, TOC-relative, or runtime-created access is not excluded by this audit",
    }


def package_evidence(apf_inner_path: Path, nfl_chunks_path: Path, lineage_path: Path) -> dict[str, Any]:
    apf_manifest = json.loads(apf_inner_path.read_text(encoding="utf-8"))
    selected = [entry for entry in apf_manifest["iff_entries"] if entry["table_index"] == 137]
    expect(len(selected), 1, "APF audiotestmenu outer count")
    apf_entry = selected[0]
    expect(apf_entry["outer_name_candidates"][0]["name"], "audiotestmenu.iff", "APF audio package name")
    apf_files = [
        {
            "index": item["index"],
            "name": item["name"],
            "type": item["type_name"],
            "asset_class": item["asset_class"],
            "total_size": sum(part["length"] for part in item["parts"]),
        }
        for item in apf_entry["files"]
    ]
    expect(len(apf_files), 10, "APF audio package resource count")

    nfl_manifest = json.loads(nfl_chunks_path.read_text(encoding="utf-8"))
    nfl_chunks = [row for row in nfl_manifest["chunks"] if row["outer_index"] == 15]
    expect(len(nfl_chunks), 14, "NFL audio package resource count")
    expect([row["kind"] for row in nfl_chunks], [
        "MRKS", "SCNE", "SCNE", "SCNE", "SCNE", "SCNE", "SCNE", "SCNE", "SCNE",
        "LAYT", "ACRV", "AMCR", "ATUN", "AUSB",
    ], "NFL audio package chunk kinds")

    with lineage_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    shared = [
        {
            "apf_inner": int(row["apf_inner_index"]),
            "name": row["name"],
            "type": row["type"],
            "nfl_outer": int(row["direct_nfl_outer_index"]),
            "nfl_chunk": int(row["direct_nfl_chunk_index"]),
            "classification": row["classification"],
        }
        for row in rows
        if row["apf_outer_index"] == "137" and row["direct_nfl_outer_index"] == "15"
    ]
    expect(len(shared), 10, "direct shared audio resources")
    return {
        "nfl2k5": {
            "outer_index": 15,
            "outer_id": nfl_chunks[0]["outer_id"],
            "resource_count": len(nfl_chunks),
            "chunk_kinds": [row["kind"] for row in nfl_chunks],
            "xbox_only_relative_to_apf_pair": [
                {"chunk": row["chunk_index"], "type": row["kind"], "stored_size": row["stored_size"]}
                for row in nfl_chunks if row["chunk_index"] in (0, 9, 10, 12)
            ],
        },
        "apf2k8": {
            "outer_index": 137,
            "outer_id": apf_entry["name_id"],
            "outer_name": "audiotestmenu.iff",
            "resource_count": len(apf_files),
            "resources": apf_files,
        },
        "direct_shared_resources": shared,
    }


def rows_for_tsv(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for platform in ("nfl2k5", "apf2k8"):
        for row in report[platform]["options"]["rows"]:
            rows.append({
                "platform": platform,
                "table": "options_navigation",
                "index": row["index"],
                "type": row["type"],
                "label": row["label"],
                "target": row["target"],
                "target_title": row["target_title"] or "",
            })
        for row in report[platform]["sound_test"]["events"]:
            rows.append({
                "platform": platform,
                "table": "sound_test_events",
                "index": row["event"],
                "type": row["action_type"],
                "label": "",
                "target": row["action"],
                "target_title": row["callback"],
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nfl-xbe", type=Path, required=True)
    parser.add_argument("--nfl-header", type=Path, required=True)
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--apf-inner", type=Path, required=True)
    parser.add_argument("--nfl-chunks", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--ghidra-trace", type=Path, required=True)
    parser.add_argument("--ghidra-pseudo", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    args = parser.parse_args()

    nfl_data = args.nfl_xbe.read_bytes()
    apf_xex_data = args.apf_xex.read_bytes()
    apf_pe_data = args.apf_pe.read_bytes()
    expect(sha256_bytes(nfl_data), NFL_XBE_SHA256, "NFL XBE SHA-256")
    expect(sha256_bytes(apf_xex_data), APF_XEX_SHA256, "APF XEX SHA-256")
    expect(sha256_bytes(apf_pe_data), APF_PE_SHA256, "APF PE SHA-256")
    expect(sha256_file(args.apf_inner), APF_INNER_SHA256, "APF inner manifest SHA-256")
    expect(sha256_file(args.nfl_chunks), NFL_CHUNKS_SHA256, "NFL chunk manifest SHA-256")
    expect(sha256_file(args.lineage), LINEAGE_SHA256, "lineage TSV SHA-256")

    nfl_image = XbeImage(nfl_data, json.loads(args.nfl_header.read_text(encoding="utf-8")))
    apf_image = ApfImage(apf_pe_data)
    ghidra_trace = args.ghidra_trace.read_text(encoding="utf-8")
    ghidra_pseudo = args.ghidra_pseudo.read_text(encoding="utf-8")
    for marker in (
        "address=0x82006870 title=Sound Test transition=AudioTestMenu",
        "RANGE 0x846A05C0..0x846A080C",
        "RANGE 0x846A0B48..0x846A1024",
    ):
        if marker not in ghidra_trace:
            raise AuditError(f"missing Ghidra trace marker {marker!r}")
    if "// PORTME: no runtime route or rendered Sound Test screen is claimed." not in ghidra_pseudo:
        raise AuditError("missing Ghidra runtime-claim boundary")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_audit": True,
            "patched_executable": False,
            "launched_emulator": False,
            "runtime_reachability_claimed": False,
            "safe_claim": (
                "NFL 2K5 exposes a fully wired retail Audio Test navigation row. APF removes that row "
                "but retains a Sound Test state descriptor, three event callbacks, a gamesound layout "
                "binding, and ten structurally converted package resources. No direct APF route was found."
            ),
        },
        "inputs": {
            "nfl_xbe": {"path": str(args.nfl_xbe), "sha256": NFL_XBE_SHA256},
            "apf_xex": {"path": str(args.apf_xex), "sha256": APF_XEX_SHA256},
            "apf_pe": {
                "path": "generated unpatched APF PE memory image",
                "sha256": APF_PE_SHA256,
                "va_mapping": "file_offset = VA - 0x82000000",
            },
            "apf_inner": {"path": str(args.apf_inner), "sha256": APF_INNER_SHA256},
            "nfl_chunks": {"path": str(args.nfl_chunks), "sha256": NFL_CHUNKS_SHA256},
            "lineage": {"path": str(args.lineage), "sha256": LINEAGE_SHA256},
            "ghidra_trace": {"path": str(args.ghidra_trace), "sha256": sha256_file(args.ghidra_trace)},
            "ghidra_pseudo": {"path": str(args.ghidra_pseudo), "sha256": sha256_file(args.ghidra_pseudo)},
        },
        "nfl2k5": {
            "options": decode_nfl_options(nfl_image),
            "sound_test": decode_nfl_sound(nfl_image, nfl_data),
        },
        "apf2k8": {
            "options": decode_apf_options(apf_image),
            "sound_test": decode_apf_sound(apf_image, apf_pe_data),
            "source_identity_strings": {
                text: [hx(address) for address in find_utf16(apf_pe_data, text)]
                for text in ("audiotestmenu.game", "audiotestmenu.iff", "Sound Test", "AudioTestMenu", "gamesound")
            },
        },
        "package_lineage": package_evidence(args.apf_inner, args.nfl_chunks, args.lineage),
        "portme": [
            "PORTME(0x82006870): prove or falsify a computed/TOC-relative/runtime-created APF route to the Sound Test descriptor.",
            "PORTME(0x846A05C0): repair the saved Ghidra function boundary and recover source-level constructor semantics from the exact 0x250-byte range.",
            "PORTME(0x846A0B48): repair the saved Ghidra function boundary and recover the input/update/draw semantics from the exact 0x4E0-byte range.",
            "PORTME(runtime): only after a safe user-owned copy route exists, capture the APF screen before calling it playable cut content.",
        ],
    }

    expect(report["apf2k8"]["source_identity_strings"]["audiotestmenu.game"], [hx(0x845062BC)], "APF game source string")
    expect(report["apf2k8"]["source_identity_strings"]["audiotestmenu.iff"], [hx(0x84506348)], "APF archive source string")
    expect(report["apf2k8"]["source_identity_strings"]["Sound Test"], [hx(0x845064E8)], "APF Sound Test string")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.tsv_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = rows_for_tsv(report)
    with args.tsv_out.open("w", newline="", encoding="utf-8") as stream:
        fields = ["platform", "table", "index", "type", "label", "target", "target_title"]
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(
        "AUDIO_TEST_REMNANT_AUDIT_PASS "
        f"nfl_options={report['nfl2k5']['options']['row_count']} "
        f"apf_options={report['apf2k8']['options']['row_count']} "
        f"apf_descriptor_pointers={report['apf2k8']['sound_test']['absolute_pointer_count_in_pe']} "
        f"shared_resources={len(report['package_lineage']['direct_shared_resources'])} "
        "runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
