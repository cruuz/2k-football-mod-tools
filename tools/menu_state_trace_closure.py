#!/usr/bin/env python3
"""Build the evidence-bounded v2 closure report for retail menu traces.

This tool never executes either title and never patches a binary or Ghidra
project.  It validates exact XBE/XEX-derived bytes, recovered manual function
extents, jump tables, instruction edges, and the read-only Ghidra transcripts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "vc_menu_state_trace_closure/v2"
APF_BASE = 0x82000000
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
NFL_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
APF_MD5 = "217eea6084c3d03f0f1143802b1f5636"


class ClosureError(RuntimeError):
    pass


def hx(value: int) -> str:
    return f"0x{value:08X}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ClosureError(f"{label}: expected {expected!r}, got {actual!r}")


class XbeImage:
    def __init__(self, data: bytes, header: dict[str, Any]):
        self.data = data
        self.sections = header["sections"]

    def offset(self, va: int, size: int = 1) -> int:
        for section in self.sections:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise ClosureError(f"NFL XBE VA {hx(va)} (+{size}) is not raw-backed")

    def read(self, va: int, size: int) -> bytes:
        off = self.offset(va, size)
        return self.data[off : off + size]


class ApfImage:
    def __init__(self, data: bytes):
        self.data = data

    def offset(self, va: int, size: int = 1) -> int:
        off = va - APF_BASE
        if off < 0 or off + size > len(self.data):
            raise ClosureError(f"APF PE VA {hx(va)} (+{size}) is outside the image")
        return off

    def read(self, va: int, size: int) -> bytes:
        off = self.offset(va, size)
        return self.data[off : off + size]

    def u32(self, va: int) -> int:
        return struct.unpack(">I", self.read(va, 4))[0]

    def utf16(self, va: int, limit: int = 256) -> str:
        data = bytearray()
        for index in range(limit):
            unit = self.read(va + index * 2, 2)
            if unit == b"\0\0":
                return data.decode("utf-16-be")
            data.extend(unit)
        raise ClosureError(f"unterminated APF UTF-16BE at {hx(va)}")

    def branch(self, va: int) -> tuple[int, bool]:
        word = self.u32(va)
        if word >> 26 != 18:
            raise ClosureError(f"APF word at {hx(va)} is not an immediate branch: {word:08X}")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = displacement if word & 2 else va + displacement
        return target & 0xFFFFFFFF, bool(word & 1)


def x86_target(image: XbeImage, site: int, opcode: int) -> int:
    data = image.read(site, 5)
    expect(data[0], opcode, f"NFL opcode at {hx(site)}")
    return (site + 5 + struct.unpack("<i", data[1:])[0]) & 0xFFFFFFFF


def edge_x86(image: XbeImage, site: int, target: int, opcode: int = 0xE8) -> dict[str, str]:
    expect(x86_target(image, site, opcode), target, f"NFL edge at {hx(site)}")
    return {
        "site": hx(site),
        "target": hx(target),
        "kind": "call" if opcode == 0xE8 else "tail_jump",
    }


def edge_ppc(image: ApfImage, site: int, target: int, link: bool = True) -> dict[str, str]:
    actual, actual_link = image.branch(site)
    expect(actual, target, f"APF edge target at {hx(site)}")
    expect(actual_link, link, f"APF edge LK at {hx(site)}")
    return {"site": hx(site), "target": hx(target), "kind": "call" if link else "tail_jump"}


def boundary(
    image: Any,
    platform: str,
    start: int,
    end: int,
    saved_body: str,
    role: str,
    end_proof: str,
    embedded_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data = image.read(start, end - start)
    return {
        "platform": platform,
        "address": hx(start),
        "end_exclusive": hx(end),
        "size": end - start,
        "sha256": sha256(data),
        "ghidra_saved_body_before_trace": saved_body,
        "recovery_status": "instruction-bounded; not persisted to the read-only project",
        "role": role,
        "end_proof": end_proof,
        "embedded_data": embedded_data or [],
    }


def apf_words(image: ApfImage, address: int, count: int) -> list[str]:
    return [hx(image.u32(address + index * 4)) for index in range(count)]


def build_boundaries(nfl: XbeImage, apf: ApfImage) -> list[dict[str, Any]]:
    nfl_jump_targets = [struct.unpack("<I", nfl.read(0x000F3F78 + i * 4, 4))[0] for i in range(10)]
    expect(nfl_jump_targets, [
        0x000F3EB7, 0x000F3ECB, 0x000F3EE4, 0x000F3EFA, 0x000F3F10,
        0x000F3F2D, 0x000F3F3B, 0x000F3F4A, 0x000F3F65, 0x000F3F6E,
    ], "NFL default-event jump table")
    nfl_jump_classes = list(nfl.read(0x000F3FA0, 28))
    expect(nfl_jump_classes, [
        0, 9, 1, 9, 2, 3, 4, 5, 9, 9, 9, 9, 9, 9,
        9, 9, 9, 9, 6, 6, 6, 6, 9, 9, 9, 9, 7, 8,
    ], "NFL default-event class map")

    apf_event_targets = [apf.u32(0x846F2E50 + i * 4) for i in range(44)]
    expect(apf_event_targets, [
        0x846F2F00, 0x846F2F88, 0x846F2F1C, 0x846F2F60, 0x846F2F70, 0x846F2F98,
        0x846F2FB0, 0x846F3084, 0x846F3084, 0x846F3034, 0x846F3014, 0x846F3014,
        *([0x846F3084] * 6), 0x846F304C, 0x846F305C, *([0x846F3084] * 6),
        0x846F306C, *([0x846F3084] * 9), 0x846F2FC8, 0x846F2FC8,
        *([0x846F3084] * 4), 0x846F2FDC, 0x846F2FF8,
    ], "APF default-event jump table")
    apf_action_targets = [apf.u32(0x846F5B0C + i * 4) for i in range(14)]
    expect(apf_action_targets, [*([0x846F5BB0] * 10), 0x846F5B44, 0x846F5B60, 0x846F5B98, 0x846F5BB0], "APF action jump table")
    apf_draw_targets = [apf.u32(0x846EF6E4 + i * 4) for i in range(4)]
    expect(apf_draw_targets, [0x846EF6F4, 0x846EF714, 0x846EF734, 0x846EF770], "APF draw jump table")

    result = [
        boundary(nfl, "nfl2k5", 0x000F3E90, 0x000F3F78, "absent", "default event dispatcher for events 1..28", "all paths return by 0x000F3F75; 0x000F3F78 begins the referenced jump table"),
        boundary(nfl, "nfl2k5", 0x002C8810, 0x002C886C, "absent", "four-name navigation LAYT loader", "RET at 0x002C886B; alignment NOPs precede the next entry at 0x002C8870"),
        boundary(apf, "apf2k8", 0x846F2E00, 0x846F308C, "0x846F2E00..0x846F2E07 only", "default event dispatcher for events 1..44", "tail epilogue branch at 0x846F3088; next entry is 0x846F3090", [{"address": hx(0x846F2E50), "size": 176, "kind": "44-entry absolute jump table"}]),
        boundary(apf, "apf2k8", 0x846F3CB0, 0x846F3DBC, "absent", "selection clamp and per-stack selected-index persistence", "tail epilogue branch at 0x846F3DB8; aligned next entry is 0x846F3DC0"),
        boundary(apf, "apf2k8", 0x846F40B8, 0x846F4168, "0x846F40B8..0x846F40BF only", "navigation runtime-row materializer", "tail epilogue branch at 0x846F4164; next entry is 0x846F4168"),
        boundary(apf, "apf2k8", 0x846F45E0, 0x846F4778, "0x846F45E0..0x846F45E7 only", "state-stack transition/insertion routine", "tail epilogue branch at 0x846F4774; next entry is 0x846F4778"),
        boundary(apf, "apf2k8", 0x846F59A8, 0x846F5BB8, "0x846F59A8..0x846F59AF only", "selected-row activation and type 10/11/12 dispatch", "tail epilogue branch at 0x846F5BB4; next entry is 0x846F5BB8", [{"address": hx(0x846F5B0C), "size": 56, "kind": "14-entry absolute type jump table"}]),
        boundary(apf, "apf2k8", 0x846EFD38, 0x846EFE14, "absent", "state-selected quicknav lookup and initializer handoff", "BLR at 0x846EFE10; next entry is 0x846EFE18"),
        boundary(apf, "apf2k8", 0x846EE1A8, 0x846EE510, "0x846EE1A8..0x846EE1AF only", "recursive LAYT initializer", "tail epilogue branch at 0x846EE50C; next entry is 0x846EE510"),
        boundary(apf, "apf2k8", 0x846EF638, 0x846EF7A0, "0x846EF638..0x846EF63F only", "recursive layout draw traversal for record types 0..3", "tail epilogue branch at 0x846EF79C; next entry is 0x846EF7A0", [{"address": hx(0x846EF6E4), "size": 16, "kind": "four-entry record-type jump table"}]),
        boundary(apf, "apf2k8", 0x846F4E38, 0x846F5054, "0x846F4E38..0x846F4E3F only", "template_quicknav timeline selection/apply callback A", "tail epilogue branch at 0x846F5050; next entry is 0x846F5058"),
        boundary(apf, "apf2k8", 0x846F5058, 0x846F5194, "0x846F5058..0x846F505F only", "template_quicknav timeline selection/apply callback B", "tail epilogue branch at 0x846F5190; next entry is 0x846F5198", [{"address": hx(0x846F5088), "size": 32, "kind": "eight-entry mode jump table"}]),
    ]

    # Entry, return/epilogue, and high-value edges are separately asserted so a
    # matching range digest alone cannot hide an incorrect semantic boundary.
    expect(nfl.read(0x000F3E90, 4), bytes.fromhex("56578bfa"), "NFL default-event entry")
    expect(nfl.read(0x000F3F75, 3), bytes.fromhex("c38bff"), "NFL default-event end")
    expect(nfl.read(0x002C8810, 1), b"\x56", "NFL navigation-loader entry")
    expect(nfl.read(0x002C886A, 2), bytes.fromhex("5ec3"), "NFL navigation-loader return")
    expect(apf.u32(0x846F2E00), 0x7D8802A6, "APF default-event entry")
    expect(apf.u32(0x846F3088), 0x484E3DB4, "APF default-event epilogue")
    expect(apf.u32(0x846F4774), 0x484E26C4, "APF state-transition epilogue")
    expect(apf.u32(0x846F5BB4), 0x484E127C, "APF activation epilogue")
    expect(apf.u32(0x846EFE10), 0x4E800020, "APF lookup return")
    expect(apf.u32(0x846EE50C), 0x484E8910, "APF initializer epilogue")
    expect(apf.u32(0x846EF79C), 0x484E7694, "APF draw epilogue")
    return result


def build_edges(nfl: XbeImage, apf: ApfImage) -> list[dict[str, str]]:
    return [
        edge_x86(nfl, 0x00150015, 0x002C8810, 0xE9),
        edge_x86(nfl, 0x002C884A, 0x000449E0),
        edge_x86(nfl, 0x002C885A, 0x00143EA0),
        edge_ppc(apf, 0x846F2F40, 0x846F55E8),
        edge_ppc(apf, 0x846F3028, 0x846F59A8),
        edge_ppc(apf, 0x846F4760, 0x846F3CB0),
        edge_ppc(apf, 0x846F5618, 0x846F40B8),
        edge_ppc(apf, 0x846F5B8C, 0x846F45E0),
        edge_ppc(apf, 0x846EFDE0, 0x84B16398),
        edge_ppc(apf, 0x846EFDF8, 0x846EE1A8),
        edge_ppc(apf, 0x846EE4A0, 0x846EE1A8),
        edge_ppc(apf, 0x846EF70C, 0x846EF1D0),
        edge_ppc(apf, 0x846EF76C, 0x846EF638),
        edge_ppc(apf, 0x846F4EEC, 0x846EDFD0),
        edge_ppc(apf, 0x846F50C0, 0x846EDFD0),
    ]


def build_timeline(apf: ApfImage, base: dict[str, Any]) -> dict[str, Any]:
    expect(apf.utf16(0x84521154), "template_quicknav", "APF timeline config name")
    config = [apf.u32(0x84D30458 + index * 4) for index in range(5)]
    expect(config, [8, 0x84521154, 0x84D30400, 0x846F4E38, 0x846F5058], "APF template_quicknav callback config")
    records = base["apf2k8"]["state_loaded_child_entry"]["records"]
    record_by_id = {int(row["id_or_hash"], 16): row for row in records}
    for wanted in (0x0A7E11EF, 0x6EA8B3CC, 0x0F0D58DD):
        expect(record_by_id[wanted]["type"], 3, f"APF transition record {hx(wanted)}")
    for wanted in (0xE7189D9F, 0x7E11CC25, 0x0916FCB3, 0x97726910):
        expect(record_by_id[wanted]["type"], 0, f"APF title record {hx(wanted)}")

    transition_name = "SlideOnNav_MainMenu"
    transition_crc = zlib.crc32(transition_name.encode("ascii")) & 0xFFFFFFFF
    expect(transition_crc, 0xC5E34EE0, "APF main transition-name CRC32")
    transition_bytes_be = transition_crc.to_bytes(4, "big")
    transition_bytes_le = transition_crc.to_bytes(4, "little")
    expect(apf.data.count(transition_bytes_be), 0, "APF transition CRC BE occurrence count")
    expect(apf.data.count(transition_bytes_le), 0, "APF transition CRC LE occurrence count")
    expect(apf.data.count((0x8460C060).to_bytes(4, "big")), 1, "APF main transition pointer occurrence count")

    return {
        "template_config": {
            "address": hx(0x84D30458),
            "entry_count_or_mode_count": 8,
            "template_name_pointer": hx(0x84521154),
            "template_name": "template_quicknav",
            "auxiliary_table": hx(0x84D30400),
            "callback_a": hx(0x846F4E38),
            "callback_b": hx(0x846F5058),
        },
        "proved_apply_path": {
            "apply_wrapper": hx(0x846EDFD0),
            "type3_apply": hx(0x846EDEA8),
            "callback_a_call_site": hx(0x846F4EEC),
            "callback_a_type3_id": hx(0x0A7E11EF),
            "callback_a_type0_targets": [hx(value) for value in (0xE7189D9F, 0x7E11CC25, 0x0916FCB3, 0x97726910)],
            "callback_b_case5_type3_id": hx(0x6EA8B3CC),
            "callback_b_case6_type3_id": hx(0x0F0D58DD),
            "status": "exact template_quicknav type-3 selection/apply is proved",
        },
        "descriptor_name_gap": {
            "descriptor_field": hx(0x820F4354),
            "string_pointer": hx(0x8460C060),
            "string": transition_name,
            "ascii_crc32": hx(transition_crc),
            "crc_fullword_occurrences_in_unpatched_pe": 0,
            "status": "no executable/data edge maps this descriptor string to the proved type-3 IDs",
            "portme": "prove the descriptor +0x04 consumer and its exact mapping, or prove the string is non-runtime metadata",
        },
    }


def build_backdrop(apf: ApfImage, base: dict[str, Any]) -> dict[str, Any]:
    name = "layout_mainmenu"
    logical = zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF
    expect(logical, 0x48C6D154, "APF layout_mainmenu CRC32")
    expect(apf.data.count(name.encode("ascii")), 0, "APF backdrop ASCII count")
    expect(apf.data.count(name.encode("utf-16-be")), 0, "APF backdrop UTF-16BE count")
    expect(apf.data.count(logical.to_bytes(4, "big")), 0, "APF backdrop CRC BE count")
    expect(apf.data.count(logical.to_bytes(4, "little")), 0, "APF backdrop CRC LE count")
    expect(apf.utf16(0x8450232C), "frontend_sync.iff", "APF frontend archive string")
    expect(apf.data.count("frontend_sync.iff".encode("utf-16-be")), 1, "APF frontend archive string count")
    expect(apf.u32(0x84C77ED8), 0xB14B48C6, "APF false high-half collision")
    expect(apf.u32(0x84CCB66C), 0x618CD154, "APF false low-half collision")
    visual = base["apf2k8"]["visual_layout_entry"]
    expect(visual["layout_name"], name, "APF backdrop layout name")
    expect(visual["outer_index"], 1493, "APF backdrop outer")
    expect(visual["inner_index"], 53, "APF backdrop inner")
    return {
        "archive_entry": {
            "archive": "frontend_sync.iff",
            "outer_index": 1493,
            "inner_index": 53,
            "layout_name": name,
            "logical_crc32": hx(logical),
            "record_count": visual["record_count"],
        },
        "executable_search": {
            "layout_name_ascii_occurrences": 0,
            "layout_name_utf16be_occurrences": 0,
            "logical_crc32_big_endian_occurrences": 0,
            "logical_crc32_little_endian_occurrences": 0,
            "frontend_sync_utf16be_occurrences": 1,
            "frontend_sync_string_address": hx(0x8450232C),
        },
        "rejected_split_immediate_collision": {
            "high_site": hx(0x84C77ED8),
            "high_instruction": "sth r10,0x48c6(r11)",
            "high_context": "one zero-store in the consecutive +0x48c2/+0x48c4/+0x48c6/+0x48c8 halfword clear sequence",
            "low_site": hx(0x84CCB66C),
            "low_instruction": "ori r12,r12,0xd154",
            "low_context": "constructs indexed offset 0x0000d154 between 0xd152 and 0xd156 for another zero-store sequence",
            "status": "not a 0x48C6D154 construction",
        },
        "status": "archive ownership is exact; no executable edge to the main state is proved",
    }


def build_labels(apf: ApfImage) -> dict[str, Any]:
    labels = []
    for index in range(7):
        source = 0x84E57340 + index * 0x60
        pointer = apf.u32(source + 4)
        labels.append({
            "index": index,
            "source_row": hx(source),
            "source_label_pointer": hx(pointer),
            "label": apf.utf16(pointer),
            "runtime_tail": hx(source + 0x50),
            "runtime_label_field": hx(source + 0x58),
        })
    expect([row["label"] for row in labels], [
        "Quick Game", "Teams", "Season", "Practice", "Options", "Features", "Xbox Live",
    ], "APF main labels")
    return {
        "row_materializer": hx(0x846F40B8),
        "proved_writes": [
            "0x846F40E8 obtains source row = descriptor +0x1C + index*0x60",
            "0x846F40F8 obtains mutable runtime tail = source row +0x50",
            "0x846F412C clears the 16-byte runtime tail",
            "0x846F4138 writes source row to runtime +0x04",
            "0x846F4144 writes source +0x04 direct UTF-16BE label pointer to runtime +0x08",
        ],
        "labels": labels,
        "main_activation_reads": "0x846F59A8 consumes runtime +0x04 (source row), not runtime +0x08 (label)",
        "main_draw_reads": "0x846EF638 traverses the LAYT record list; no proved read of navigation runtime +0x08 occurs on this path",
        "localization_relation": "no STRG/TXT localization ID or resolver is proved between these direct literals and a final renderer",
        "final_renderer_proved": False,
    }


def build_main_routes(apf: ApfImage) -> dict[str, Any]:
    route_sites = [0x84A569B4, 0x84A56C18, 0x84A56C3C, 0x84A56C50, 0x84A56CD4, 0x84A56D4C, 0x84A56DD0]
    edges = []
    for site in route_sites:
        lis_sites = [candidate for candidate in (site - 8, site - 4) if apf.u32(candidate) == 0x3D60820F]
        expect(len(lis_sites), 1, f"APF main route lis count at {hx(site)}")
        expect(apf.u32(site), 0x388B4350, f"APF main route addi at {hx(site)}")
        edges.append({"lis_site": hx(lis_sites[0]), "descriptor_site": hx(site), "descriptor": hx(0x820F4350), "callee_site": hx(site + 4), "callee": hx(0x846F60E8)})
        expect(apf.branch(site + 4), (0x846F60E8, True), f"APF main route edge at {hx(site + 4)}")
    expect(apf.u32(0x84A586B0), 0x3D60820F, "APF known-route lis")
    expect(apf.u32(0x84A586B8), 0x38AB4350, "APF known-route addi")
    expect(apf.branch(0x84A586C0), (0x846F45E0, True), "APF known route to transition")
    return {
        "queue_wrapper": hx(0x846F60E8),
        "queue_wrapper_effect": "calls 0x846F5C90(manager, 0x8500EFD8, descriptor)",
        "queue_or_route_sites": edges,
        "direct_transition_site": {"site": hx(0x84A586C0), "caller": hx(0x84A58698), "descriptor": hx(0x820F4350), "callee": hx(0x846F45E0)},
        "status": "eight executable routes to the main descriptor are exact; none is proved to be cold boot",
    }


RESOLVED_PORTME = {
    ("nfl2k5", "0x000F3E90"), ("nfl2k5", "0x002C8810"),
    ("apf2k8", "0x846F2E00"), ("apf2k8", "0x846F3CB0"),
    ("apf2k8", "0x846F59A8"), ("apf2k8", "0x846EFD38"),
    ("apf2k8", "0x846EE1A8"), ("apf2k8", "0x846EF638"),
}


def remaining_portme(base: dict[str, Any]) -> list[dict[str, str]]:
    normalized = []
    for original in base["portme"]:
        if (original["platform"], original["address"]) in RESOLVED_PORTME:
            continue
        item = dict(original)
        if item["address"] == "0x846F45E0":
            item["reason"] = "boundary is recovered, but assign human push/replace/queued-transition names only after every mode/caller contract is proved"
        if item["address"] == "0x820F4354":
            item["reason"] = "map SlideOnNav_MainMenu to an exact runtime consumer/type-3 ID, or prove it is non-runtime metadata"
        normalized.append(item)
    return normalized


def validate_traces(nfl_trace: Path, nfl_pseudo: Path, apf_trace: Path, apf_pseudo: Path) -> dict[str, Any]:
    texts = {
        "nfl_trace": nfl_trace.read_text(encoding="utf-8"),
        "nfl_pseudo": nfl_pseudo.read_text(encoding="utf-8"),
        "apf_trace": apf_trace.read_text(encoding="utf-8"),
        "apf_pseudo": apf_pseudo.read_text(encoding="utf-8"),
    }
    for exact in (
        f"Program MD5: {NFL_MD5}",
        "0x000F3E90 56 PUSH ESI",
        "0x000F3F75 C3 RET",
        "0x002C8810 56 PUSH ESI",
        "0x002C8843 BA 4C 41 59 54 MOV EDX,0x5459414c",
        "0x002C886B C3 RET",
    ):
        if exact not in texts["nfl_trace"]:
            raise ClosureError(f"NFL read-only trace lacks exact anchor: {exact}")
    for exact in (
        f"Program MD5: {APF_MD5}",
        "0x846F2E00 7D 88 02 A6 mfspr r12,LR",
        "0x846F3088 48 4E 3D B4 b 0x84bd6e3c",
        "0x846F4774 48 4E 26 C4 b 0x84bd6e38",
        "0x846F5BB4 48 4E 12 7C b 0x84bd6e30",
        "0x846EFE10 4E 80 00 20 blr",
        "0x846EE50C 48 4E 89 10 b 0x84bd6e1c",
        "0x846EF79C 48 4E 76 94 b 0x84bd6e30",
        "0x846F4EEC 4B FF 90 E5 bl 0x846edfd0",
        "0x84C77ED8 B1 4B 48 C6 sth r10,0x48c6(r11)",
        "0x84CCB66C 61 8C D1 54 ori r12,r12,0xd154",
    ):
        if exact not in texts["apf_trace"]:
            raise ClosureError(f"APF read-only trace lacks exact anchor: {exact}")
    for exact in (
        "// PORTME: could not decompile function at 0x000F3E90",
        "// PORTME: could not decompile function at 0x002C8810",
    ):
        if exact not in texts["nfl_pseudo"]:
            raise ClosureError(f"NFL pseudo-C lacks boundary caveat: {exact}")
    if "// PORTME: could not decompile function at 0x84C559C0" not in texts["apf_pseudo"]:
        raise ClosureError("APF pseudo-C lacks giant-function PORTME")
    return {
        name: {"path": str(path), "sha256": sha256(path.read_bytes()), "size": path.stat().st_size}
        for name, path in (
            ("nfl_trace", nfl_trace), ("nfl_pseudo", nfl_pseudo),
            ("apf_trace", apf_trace), ("apf_pseudo", apf_pseudo),
        )
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    nfl_data = args.nfl_xbe.read_bytes()
    apf_data = args.apf_pe.read_bytes()
    xex_data = args.apf_xex.read_bytes()
    header = json.loads(args.nfl_header.read_text(encoding="utf-8"))
    base = json.loads(args.base_report.read_text(encoding="utf-8"))
    expect(sha256(nfl_data), NFL_XBE_SHA256, "NFL XBE SHA-256")
    expect(header["sha256"], NFL_XBE_SHA256, "NFL header SHA-256")
    expect(sha256(apf_data), APF_PE_SHA256, "APF PE SHA-256")
    expect(sha256(xex_data), APF_XEX_SHA256, "APF XEX SHA-256")
    expect(base["schema"], "vc_menu_state_trace/v1", "base menu trace schema")
    nfl = XbeImage(nfl_data, header)
    apf = ApfImage(apf_data)
    boundaries = build_boundaries(nfl, apf)
    traces = validate_traces(args.nfl_trace, args.nfl_pseudo, args.apf_trace, args.apf_pseudo)
    return {
        "schema": SCHEMA,
        "scope": {
            "kind": "read-only retail main-menu boundary closure",
            "executes_original_game": False,
            "launches_original_menu": False,
            "claims_source_equivalence": False,
            "writes_ghidra_project": False,
        },
        "inputs": {
            "nfl2k5_xbe": {"sha256": NFL_XBE_SHA256, "md5": header["md5"]},
            "apf2k8_xex": {"sha256": APF_XEX_SHA256},
            "apf2k8_unpatched_pe": {"sha256": APF_PE_SHA256, "size": len(apf_data), "mapping": "file_offset = VA - 0x82000000"},
            "base_report": {"schema": base["schema"], "sha256": sha256(args.base_report.read_bytes())},
            "ghidra_read_only_transcripts": traces,
        },
        "recovered_boundaries": boundaries,
        "validated_edges": build_edges(nfl, apf),
        "apf2k8": {
            "main_routes": build_main_routes(apf),
            "template_quicknav_timeline": build_timeline(apf, base),
            "layout_mainmenu_backdrop": build_backdrop(apf, base),
            "labels_and_localization": build_labels(apf),
        },
        "resolved_portme_from_v1": [
            {"platform": platform, "address": address, "resolution": "exact boundary and instruction semantics retained in this report"}
            for platform, address in sorted(RESOLVED_PORTME)
        ],
        "portme": remaining_portme(base),
        "result": {
            "worked": [
                "recovered two missing NFL and eight fragmented/missing APF function extents without persisting project changes",
                "proved the complete template_quicknav type-3 selection/apply callback chain and its exact record IDs",
                "proved eight executable APF routes to the main descriptor, none promoted to cold boot",
                "rejected both apparent layout_mainmenu CRC halfword hits with their exact zero-store contexts",
                "bounded the APF main-label chain through runtime +0x08 and retained the unproved final renderer",
            ],
            "failed_or_unproved": [
                "SlideOnNav_MainMenu has no proved mapping to any type-3 record ID",
                "layout_mainmenu remains archive-exact but has no executable main-state edge",
                "the final APF label renderer/localization policy remains unproved",
                "no route is proved to be cold boot and no original menu was launched",
            ],
            "blocking": "the remaining address-specific PORTME ledger still blocks a source-equivalent original-menu claim",
        },
    }


def evidence_rows(report: dict[str, Any]) -> Iterable[list[Any]]:
    for row in report["recovered_boundaries"]:
        yield [row["platform"], "boundary", row["address"], row["end_exclusive"], "proved", row["role"]]
    yield ["apf2k8", "timeline", "0x84D30458", "0x84D3046C", "proved", "template_quicknav config binds 0x846F4E38 and 0x846F5058"]
    yield ["apf2k8", "timeline", "0x846F4EEC", "0x846F4EF0", "proved", "type-3 0x0A7E11EF reaches apply wrapper 0x846EDFD0"]
    yield ["apf2k8", "transition_name", "0x820F4354", "0x820F4358", "blocked", "SlideOnNav_MainMenu has no proved mapping to the type-3 IDs"]
    yield ["apf2k8", "backdrop", "0x48C6D154", "0x48C6D154", "blocked", "archive identity exact; no fullword/name/executable state edge"]
    yield ["apf2k8", "label", "0x846F4144", "0x846F4148", "partial", "direct label copied to runtime +0x08; final renderer unresolved"]
    yield ["apf2k8", "main_route", "0x84A569B4", "0x84A56DD4", "partial", "seven queued and one direct main-descriptor routes; none is cold boot"]


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["platform", "category", "address", "end_exclusive", "status", "evidence"])
        writer.writerows(evidence_rows(report))


def write_portme(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "/* Generated unresolved menu-closure ledger; not original game source. */",
        "#include <stdint.h>",
        "",
        "void vc_menu_state_trace_closure_unresolved(void) {",
    ]
    for row in report["portme"]:
        lines.append(f"    // PORTME: {row['platform']} function/data at {row['address']}: {row['reason']}.")
    lines.extend(["    (void)(uint32_t)0;", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nfl-xbe", type=Path, required=True)
    parser.add_argument("--nfl-header", type=Path, required=True)
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--base-report", type=Path, required=True)
    parser.add_argument("--nfl-trace", type=Path, required=True)
    parser.add_argument("--nfl-pseudo", type=Path, required=True)
    parser.add_argument("--apf-trace", type=Path, required=True)
    parser.add_argument("--apf-pseudo", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    parser.add_argument("--portme-c-out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args)
        for path in (args.json_out, args.tsv_out, args.portme_c_out):
            path.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_tsv(args.tsv_out, report)
        write_portme(args.portme_c_out, report)
    except (OSError, ValueError, KeyError, ClosureError) as error:
        print(f"menu_state_trace_closure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
