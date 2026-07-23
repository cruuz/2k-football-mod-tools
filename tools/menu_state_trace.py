#!/usr/bin/env python3
"""Deterministic, evidence-bounded main-menu state trace for NFL 2K5/APF 2K8.

The script does not decompile or execute either game.  It decodes the static
state records, validates manually recovered call-site anchors, and joins those
records to the already extracted LAYT inventories.  APF input is the unpatched
PE memory image produced by tools/xex_extract_pe.cpp; its file offset is
``virtual_address - 0x82000000``.
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


SCHEMA = "vc_menu_state_trace/v1"
APF_BASE = 0x82000000
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"


class TraceError(RuntimeError):
    pass


def hx(value: int | None) -> str | None:
    return None if value is None else f"0x{value:08X}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise TraceError(f"{label}: expected {expected!r}, got {actual!r}")


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
        raise TraceError(f"XBE VA {hx(va)} (+{size}) is not backed by a raw section")

    def read(self, va: int, size: int) -> bytes:
        off = self.offset(va, size)
        return self.data[off : off + size]

    def u8(self, va: int) -> int:
        return self.read(va, 1)[0]

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]

    def utf16(self, va: int, limit: int = 256) -> str:
        out = bytearray()
        for i in range(limit):
            unit = self.read(va + i * 2, 2)
            if unit == b"\x00\x00":
                return out.decode("utf-16le")
            out.extend(unit)
        raise TraceError(f"unterminated UTF-16LE string at {hx(va)}")


class ApfImage:
    def __init__(self, data: bytes):
        self.data = data

    def offset(self, va: int, size: int = 1) -> int:
        off = va - APF_BASE
        if off < 0 or off + size > len(self.data):
            raise TraceError(f"APF VA {hx(va)} (+{size}) is outside the PE memory image")
        return off

    def read(self, va: int, size: int) -> bytes:
        off = self.offset(va, size)
        return self.data[off : off + size]

    def u32(self, va: int) -> int:
        return struct.unpack(">I", self.read(va, 4))[0]

    def utf16(self, va: int, limit: int = 256) -> str:
        out = bytearray()
        for i in range(limit):
            unit = self.read(va + i * 2, 2)
            if unit == b"\x00\x00":
                return out.decode("utf-16be")
            out.extend(unit)
        raise TraceError(f"unterminated UTF-16BE string at {hx(va)}")

    def branch(self, va: int) -> tuple[int, bool]:
        word = self.u32(va)
        if word >> 26 != 18:
            raise TraceError(f"PPC word at {hx(va)} is not an immediate branch: {word:08X}")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = displacement if word & 2 else va + displacement
        return target & 0xFFFFFFFF, bool(word & 1)


def x86_rel_target(image: XbeImage, va: int, opcode: int) -> int:
    expect(image.u8(va), opcode, f"x86 opcode at {hx(va)}")
    rel = struct.unpack("<i", image.read(va + 1, 4))[0]
    return (va + 5 + rel) & 0xFFFFFFFF


def check_x86_edge(image: XbeImage, site: int, target: int, opcode: int = 0xE8) -> dict[str, str]:
    expect(x86_rel_target(image, site, opcode), target, f"x86 edge at {hx(site)}")
    return {"site": hx(site), "target": hx(target), "kind": "call" if opcode == 0xE8 else "jump"}


def check_ppc_edge(image: ApfImage, site: int, target: int, link: bool = True) -> dict[str, str]:
    actual_target, actual_link = image.branch(site)
    expect(actual_target, target, f"PPC edge target at {hx(site)}")
    expect(actual_link, link, f"PPC edge LK at {hx(site)}")
    return {"site": hx(site), "target": hx(target), "kind": "call" if link else "jump"}


def read_layout_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def select_layout(
    rows: list[dict[str, str]], platform: str, outer: int, inner: int, name: str
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row["platform"] == platform
        and int(row["outer_index"]) == outer
        and int(row["inner_index"]) == inner
        and row["layout_name"] == name
    ]
    if not selected:
        raise TraceError(f"missing layout {platform}:{outer}/{inner}:{name}")
    selected.sort(key=lambda row: int(row["record_index"]))
    return {
        "platform": platform,
        "outer_index": outer,
        "inner_index": inner,
        "layout_name": name,
        "name_crc32": hx(zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF),
        "record_count": len(selected),
        "record_type_counts": {
            str(kind): sum(int(row["record_type"]) == kind for row in selected)
            for kind in sorted({int(row["record_type"]) for row in selected})
        },
        "records": [
            {
                "index": int(row["record_index"]),
                "type": int(row["record_type"]),
                "id_or_hash": row["id_or_hash_08"],
                "primary_name": row["primary_name"] or None,
                "source_name": row["source_name"] or None,
                "instance_name": row["instance_name"] or None,
            }
            for row in selected
        ],
    }


def binary_anchor(name: str, image: Any, start: int, end: int) -> dict[str, Any]:
    blob = image.read(start, end - start)
    return {
        "name": name,
        "start": hx(start),
        "end_exclusive": hx(end),
        "size": len(blob),
        "sha256": sha256_bytes(blob),
    }


def decode_nfl(image: XbeImage, layouts: list[dict[str, str]]) -> dict[str, Any]:
    descriptor_va = 0x00515660
    words = [image.u32(descriptor_va + i * 4) for i in range(8)]
    expect(words, [0x00E8B1CC, 0x00515490, 0x000F3E90, 0, 0x005154C0, 0, 0x00E8B1E0, 0x00AC60D0], "NFL main descriptor")
    expect(image.utf16(words[0]), "Main Menu", "NFL state title")
    expect(image.utf16(words[6]), "main_menu_sub", "NFL state layout name")

    event_table: list[dict[str, Any]] = []
    event_cursor = words[1]
    for _ in range(6):
        event_id = image.u32(event_cursor)
        action = image.u32(event_cursor + 4)
        event_table.append({"event": event_id, "action_descriptor": hx(action)})
        event_cursor += 8
    expect([(row["event"], row["action_descriptor"]) for row in event_table], [
        (3, hx(0x00515300)), (4, hx(0x00515348)), (6, hx(0x00515390)),
        (7, hx(0x00515400)), (8, hx(0x00515448)), (0, hx(0)),
    ], "NFL event table")

    action_descriptors = [
        {"address": hx(0x00515300), "selector": image.u32(0x00515300), "callback": hx(image.u32(0x0051530C))},
        {"address": hx(0x00515348), "selector": image.u32(0x00515348), "callback": hx(image.u32(0x0051534C))},
        {"address": hx(0x00515390), "selector": image.u32(0x00515390), "callback": hx(image.u32(0x00515394)),
         "chained_selector": image.u32(0x005153B4), "chained_callback": hx(image.u32(0x005153B8))},
        {"address": hx(0x00515400), "selector": image.u32(0x00515400), "callback": hx(image.u32(0x0051540C))},
        {"address": hx(0x00515448), "selector": image.u32(0x00515448), "callback": hx(image.u32(0x00515454))},
    ]
    expect([row["selector"] for row in action_descriptors], [3, 1, 1, 3, 3], "NFL action selectors")
    expect([row["callback"] for row in action_descriptors], [hx(0x000F2F00), hx(0x00327A50), hx(0x00327A90), hx(0x000F2F00), hx(0x0024D490)], "NFL action callbacks")
    expect(action_descriptors[2]["chained_callback"], hx(0x00192090), "NFL chained callback")

    nav_rows: list[dict[str, Any]] = []
    nav_base = words[4]
    for index in range(7):
        va = nav_base + index * 0x34
        kind = image.u32(va)
        label_ptr = image.u32(va + 4)
        target = image.u32(va + 8)
        callback = image.u32(va + 0x28)
        target_title = None
        if target:
            target_title_ptr = image.u32(target)
            target_title = image.utf16(target_title_ptr) if target_title_ptr else None
        nav_rows.append({
            "index": index,
            "address": hx(va),
            "type": kind,
            "label_pointer": hx(label_ptr),
            "label": image.utf16(label_ptr),
            "target_descriptor": hx(target) if target else None,
            "target_title": target_title,
            "callback": hx(callback) if callback else None,
        })
    expect([row["label"] for row in nav_rows], ["Quick Game", "Game Modes", "The Crib|TM|", "Features", "Options", "Xbox Live", "Extras"], "NFL main labels")
    expect([row["type"] for row in nav_rows], [0, 0, 9, 0, 0, 0, 0], "NFL main row types")
    expect(image.u32(nav_base + 7 * 0x34), 3, "NFL nav sentinel")

    jump_map = list(image.read(0x000F3FA0, 28))
    expect(jump_map, [0, 9, 1, 9, 2, 3, 4, 5, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 6, 6, 6, 6, 9, 9, 9, 9, 7, 8], "NFL callback jump map")

    shared_names = [image.utf16(address) for address in (0x00E6BA90, 0x00E6BAB0, 0x00E6BACC, 0x00E6BAEC)]
    expect(shared_names, ["title_bar_short", "title_bar_sub", "title_bar_wide", "title_bar_short_sub"], "NFL shared LAYT names")
    nav_names = [image.utf16(image.u32(0x00AD0148 + i * 4)) for i in range(4)]
    expect(nav_names, ["nav_menu_a", "nav_bar_b", "nav_bar_c", "main_navi"], "NFL navigation LAYT names")

    edges = [
        check_x86_edge(image, 0x000F380C, 0x000449E0),
        check_x86_edge(image, 0x000F38C6, 0x000449E0),
        check_x86_edge(image, 0x000F38DA, 0x00143EA0),
        check_x86_edge(image, 0x000F39AE, 0x000F37E0),
        check_x86_edge(image, 0x000F39C4, 0x00143C30),
        check_x86_edge(image, 0x00150015, 0x002C8810, 0xE9),
        check_x86_edge(image, 0x002C884A, 0x000449E0),
        check_x86_edge(image, 0x002C885A, 0x00143EA0),
        check_x86_edge(image, 0x001501E4, 0x0006E390),
        check_x86_edge(image, 0x00150209, 0x0006E2E0),
        check_x86_edge(image, 0x000F2F85, 0x00143DE0, 0xE9),
        check_x86_edge(image, 0x0014FDFB, 0x0006E630),
        check_x86_edge(image, 0x0014FE2E, 0x00030AE0),
        check_x86_edge(image, 0x0014FEF5, 0x00030F50),
        check_x86_edge(image, 0x0014FF38, 0x000F1D50),
    ]

    visual_layout = select_layout(layouts, "nfl2k5", 8, 17, "main_menu")
    state_layout = select_layout(layouts, "nfl2k5", 8, 18, "main_menu_sub")
    navigation_layout = select_layout(layouts, "nfl2k5", 8, 19, "main_navi")
    return {
        "visual_layout_entry": visual_layout,
        "state_loaded_layout_entry": state_layout,
        "navigation_child_entry": navigation_layout,
        "state_descriptor": {
            "address": hx(descriptor_va),
            "size": 0x20,
            "title": image.utf16(words[0]),
            "event_table": hx(words[1]),
            "default_callback": hx(words[2]),
            "navigation_rows": hx(words[4]),
            "loaded_layout_name": image.utf16(words[6]),
            "layout_callback_context": hx(words[7]),
        },
        "event_table": event_table,
        "action_descriptors": action_descriptors,
        "default_event_callback": {
            "address": hx(0x000F3E90),
            "saved_function_boundary": False,
            "event_1_to_28_jump_classes": jump_map,
            "proved_paths": {
                "1": [hx(0x000F2920), hx(0x0014FF70)],
                "3": [hx(0x000F3CD0), hx(0x0014FF80), hx(0x000F3D60)],
                "5": [hx(0x0014FC20), hx(0x000F2D40)],
                "6": [hx(0x00150020), hx(0x000F3970)],
                "7": [hx(0x000F2810), hx(0x000F2F70), hx(0x00150260)],
                "8": [hx(0x000F26F0)],
                "19-22": [hx(0x0014FC60)],
                "27": [hx(0x000F3700), hx(0x0014FD70)],
                "28": [hx(0x000F3700)],
            },
        },
        "navigation_rows": nav_rows,
        "resource_lookup": {
            "loader": hx(0x000449E0),
            "type_fourcc_little_endian_register_value": hx(0x5459414C),
            "lifecycle_loader": hx(0x000F37E0),
            "active_descriptor_layout_field": "+0x18",
            "active_layout_runtime_slot": "+0x5A0",
            "initializer": hx(0x00143EA0),
            "shared_layout_names": shared_names,
            "navigation_layout_names": nav_names,
        },
        "state_and_navigation_chain": {
            "replace": hx(0x0006E2E0),
            "push": hx(0x0006E390),
            "pop": hx(0x0006E400),
            "event_dispatch": hx(0x0006E4E0),
            "row_constructor": hx(0x0014FF80),
            "row_stride": 0x2C,
            "source_row_stride": 0x34,
            "selection_update": hx(0x00150020),
            "type_0_action": "push target descriptor from source +0x08 via 0x0006E390",
            "type_9_action": "call source +0x28 callback; main Crib callback is 0x0024D440",
        },
        "event_3_construction": [
            hx(0x0006E4E0), hx(0x000F3E90), hx(0x000F3CD0), hx(0x000F37E0),
            hx(0x0014FF80), hx(0x0014FC60), hx(0x002C8810),
        ],
        "update_draw_visibility_timeline": {
            "update": [hx(0x000F3E90), "event 6", hx(0x00150020), hx(0x000F3970), hx(0x00143C30)],
            "draw": [hx(0x000F3E90), "event 7", hx(0x000F2F70), hx(0x00143DE0), hx(0x00143A00), hx(0x00143720)],
            "visibility": "0x00143EA0 initializes type-0 runtime +0x38; 0x00143720 tests it; 0x00143FE0 writes it by ID",
            "timeline": "0x00143C30 propagates per-layout update; 0x00143CE0 updates type-0 progress +0x54 and phase +0x58",
        },
        "localization": {
            "storage": "direct UTF-16LE literal pointers at source row +0x04",
            "render_chain": [hx(0x0014FF80), "runtime label +0x28", hx(0x0014FDA0), hx(0x00030AE0), hx(0x00030F50), hx(0x000F1D50)],
            "resolver_proved": False,
        },
        "validated_edges": edges,
        "binary_anchors": [
            binary_anchor("nfl_state_descriptor", image, 0x00515660, 0x00515680),
            binary_anchor("nfl_default_callback_fragment", image, 0x000F3E90, 0x000F3FC0),
            binary_anchor("nfl_state_dispatch", image, 0x0006E4E0, 0x0006E630),
            binary_anchor("nfl_nav_constructor", image, 0x0014FF80, 0x00150020),
            binary_anchor("nfl_nav_selection", image, 0x00150020, 0x0015023B),
        ],
    }


def decode_apf(image: ApfImage, layouts: list[dict[str, str]]) -> dict[str, Any]:
    descriptor_va = 0x820F4350
    words = [image.u32(descriptor_va + i * 4) for i in range(0x48 // 4)]
    expected = [
        0x8460C04C, 0x8460C060, 0, 0x846F2E00, 2, 0, 0, 0x84E57340,
        0, 0, 0, 0x8460C088, 0, 0, 0, 7, 0x005E018C, 0x88000000,
    ]
    expect(words, expected, "APF main descriptor")
    expect(image.utf16(words[0]), "Main Menu", "APF state title")
    expect(image.utf16(words[1]), "SlideOnNav_MainMenu", "APF transition name")
    expect(image.utf16(words[11]), "quicknav", "APF state layout name")
    quicknav_crc = zlib.crc32(b"quicknav") & 0xFFFFFFFF
    expect(quicknav_crc, 0x210FFA23, "APF quicknav CRC32")
    expect(image.u32(0x82016730), 0x86A1AC9E, "APF LAYT type hash")

    items: list[dict[str, Any]] = []
    item_base = words[7]
    for index in range(words[15]):
        va = item_base + index * 0x60
        kind = image.u32(va)
        label_ptr = image.u32(va + 4)
        target = image.u32(va + 8)
        preflight = image.u32(va + 0x48)
        callback = image.u32(va + 0x34)
        target_title = None
        if target:
            title_ptr = image.u32(target)
            target_title = image.utf16(title_ptr) if title_ptr else None
        items.append({
            "index": index,
            "address": hx(va),
            "type": kind,
            "label_pointer": hx(label_ptr),
            "label": image.utf16(label_ptr),
            "target_descriptor": hx(target) if target else None,
            "target_title": target_title,
            "callback_34": hx(callback) if callback else None,
            "preflight_callback_48": hx(preflight) if preflight else None,
        })
    expect([row["label"] for row in items], ["Quick Game", "Teams", "Season", "Practice", "Options", "Features", "Xbox Live"], "APF main labels")
    expect([row["type"] for row in items], [12, 11, 11, 12, 11, 11, 10], "APF main item types")
    expect(items[6]["callback_34"], hx(0x84A57F70), "APF Xbox Live callback")
    expect(items[6]["preflight_callback_48"], hx(0x846CAE10), "APF Xbox Live preflight callback")

    event_targets = [image.u32(0x846F2E50 + i * 4) for i in range(44)]
    expected_event_targets = [
        0x846F2F00, 0x846F2F88, 0x846F2F1C, 0x846F2F60, 0x846F2F70, 0x846F2F98,
        0x846F2FB0, 0x846F3084, 0x846F3084, 0x846F3034, 0x846F3014, 0x846F3014,
        *([0x846F3084] * 6), 0x846F304C, 0x846F305C, *([0x846F3084] * 6),
        0x846F306C, *([0x846F3084] * 9), 0x846F2FC8, 0x846F2FC8,
        *([0x846F3084] * 4), 0x846F2FDC, 0x846F2FF8,
    ]
    expect(event_targets, expected_event_targets, "APF main callback jump table")

    action_targets = [image.u32(0x846F5B0C + i * 4) for i in range(14)]
    expect(action_targets, [*([0x846F5BB0] * 10), 0x846F5B44, 0x846F5B60, 0x846F5B98, 0x846F5BB0], "APF item action jump table")

    route_ref_count = image.data.count(descriptor_va.to_bytes(4, "big"))
    expect(route_ref_count, 78, "APF main descriptor reference count")
    expect(image.u32(0x84A586B0), 0x3D60820F, "APF return callback lis")
    expect(image.u32(0x84A586B8), 0x38AB4350, "APF return callback addi")

    edges = [
        check_ppc_edge(image, 0x84A586AC, 0x84A56B00),
        check_ppc_edge(image, 0x84A586C0, 0x846F45E0),
        check_ppc_edge(image, 0x846EFDE0, 0x84B16398),
        check_ppc_edge(image, 0x846EFDF8, 0x846EE1A8),
        check_ppc_edge(image, 0x846EE39C, 0x846EDD30),
        check_ppc_edge(image, 0x846EE4A0, 0x846EE1A8),
        check_ppc_edge(image, 0x846F2F40, 0x846F55E8),
        check_ppc_edge(image, 0x846F18F8, 0x846EFF80),
        check_ppc_edge(image, 0x846EFFD8, 0x846EFD38),
        check_ppc_edge(image, 0x846F5618, 0x846F40B8),
        check_ppc_edge(image, 0x846F2FA4, 0x846F1DD0),
        check_ppc_edge(image, 0x846F1E20, 0x846EDAE8),
        check_ppc_edge(image, 0x846F2FB4, 0x846F0678),
        check_ppc_edge(image, 0x846F06D4, 0x846EF7A0),
        check_ppc_edge(image, 0x846EF70C, 0x846EF1D0),
        check_ppc_edge(image, 0x846F3028, 0x846F59A8),
        check_ppc_edge(image, 0x846F5B8C, 0x846F45E0),
        check_ppc_edge(image, 0x846F5BA0, 0x846F9020),
        check_ppc_edge(image, 0x846F9070, 0x846F8F00),
    ]

    expect(image.u32(0x846EF270), 0x81790034, "APF draw visibility load")
    expect(image.u32(0x846EF274), 0x556B0084, "APF draw visibility mask")

    quicknav_layout = select_layout(layouts, "apf2k8", 1310, 57, "quicknav")
    template_quicknav = select_layout(layouts, "apf2k8", 1310, 223, "template_quicknav")
    expect(quicknav_layout["record_type_counts"], {"2": 1}, "APF quicknav layout shape")
    expect(template_quicknav["record_type_counts"], {"0": 20, "3": 13}, "APF template_quicknav layout shape")

    visual_layout = select_layout(layouts, "apf2k8", 1493, 53, "layout_mainmenu")
    visual_layout["archive_name"] = "frontend_sync.iff"
    quicknav_layout["archive_name"] = "global.iff"
    template_quicknav["archive_name"] = "global.iff"
    return {
        "visual_layout_entry": visual_layout,
        "state_loaded_layout_entry": quicknav_layout,
        "state_loaded_child_entry": template_quicknav,
        "state_descriptor": {
            "address": hx(descriptor_va),
            "size": 0x48,
            "title": image.utf16(words[0]),
            "transition_name": image.utf16(words[1]),
            "default_callback": hx(words[3]),
            "navigation_rows": hx(words[7]),
            "loaded_layout_name": image.utf16(words[11]),
            "item_count": words[15],
            "raw_word_40": hx(words[16]),
            "raw_word_44": hx(words[17]),
            "big_endian_pointer_occurrences_in_image": route_ref_count,
        },
        "known_transition_to_main": {
            "callback": hx(0x84A58698),
            "descriptor_argument": hx(descriptor_va),
            "state_transition_routine": hx(0x846F45E0),
            "scope": "proved return/route transition; not a proved cold-boot constructor",
        },
        "default_event_callback": {
            "address": hx(0x846F2E00),
            "saved_function_boundary": False,
            "manual_contiguous_end_exclusive": hx(0x846F3090),
            "event_jump_targets": {str(i + 1): hx(target) for i, target in enumerate(event_targets)},
            "activation_events": [11, 12],
            "activation_path": [hx(0x846F3014), hx(0x846F5840), hx(0x846F59A8)],
        },
        "navigation_rows": items,
        "navigation_action_dispatch": {
            "address": hx(0x846F59A8),
            "saved_function_boundary": False,
            "manual_contiguous_end_exclusive": hx(0x846F5BB8),
            "type_10": "call source +0x34 callback; Xbox Live uses 0x84A57F70 after +0x48 preflight 0x846CAE10",
            "type_11": "optional source +0x44 callback, then 0x846F45E0(manager, runtime_row, source +0x08 target)",
            "type_12": "0x846F9020(manager, source +0x08 target), which reaches replace-like 0x846F8F00",
            "jump_targets_0_to_13": [hx(target) for target in action_targets],
        },
        "resource_lookup": {
            "lifecycle_loader": hx(0x846EFD38),
            "name_crc32_function": hx(0x84B20E48),
            "name": "quicknav",
            "logical_resource_id": hx(quicknav_crc),
            "dram_hash": hx(0xBB05A9C1),
            "type_hash": hx(0x86A1AC9E),
            "lookup": hx(0x84B16398),
            "runtime_layout_slot": "+0x410",
            "initializer": hx(0x846EE1A8),
        },
        "state_and_navigation_chain": {
            "state_transition": hx(0x846F45E0),
            "stack_push_like": hx(0x846F8A60),
            "replace_like": hx(0x846F8F00),
            "event_dispatch": hx(0x846F9090),
            "row_constructor": [hx(0x846F55E8), hx(0x846F40B8)],
            "source_row_stride": 0x60,
            "runtime_row_stride": 0x60,
            "runtime_source_pointer_offset": "+0x04",
            "runtime_label_pointer_offset": "+0x08",
            "selection_clamp": hx(0x846F3CB0),
        },
        "event_3_construction": [
            hx(0x846F2E00), hx(0x846F1778), hx(0x846F18A0), hx(0x846EFF80),
            hx(0x846EFD38), hx(0x84B20E48), hx(0x84B16398), hx(0x846EE1A8),
            hx(0x846F55E8), hx(0x846F40B8),
        ],
        "update_draw_visibility_timeline": {
            "update": [hx(0x846F2E00), "event 6", hx(0x846F5650), hx(0x846F1DD0), hx(0x846EDAE8)],
            "update_effect": "0x846EDAE8 stores delta at layout +0x34 and recursively follows type-2 child +0x28",
            "draw": [hx(0x846F2E00), "event 7", hx(0x846F0678), hx(0x846EF7A0), hx(0x846EF638), hx(0x846EF1D0)],
            "visibility": "0x846EF1D0 checks type-0 +0x34 bit 29 at 0x846EF270/0x846EF274; 0x846EEC98 is the ID-based writer",
            "timeline_initialization": [hx(0x846EFD38), hx(0x846EE1A8), hx(0x846EDD30)],
            "timeline_apply_gap": "template_quicknav contains 13 type-3 records, but no main-route-specific call to 0x846EDEA8 is proved",
        },
        "localization": {
            "storage": "direct UTF-16BE literal pointers at source row +0x04; 0x846F40B8 copies them to runtime row +0x08",
            "render_or_localization_resolver_proved": False,
        },
        "visual_layout_link_status": {
            "layout_mainmenu_id": hx(0x48C6D154),
            "state_loaded_quicknav_id": hx(quicknav_crc),
            "status": "no executable edge from this state descriptor to layout_mainmenu is proved",
            "unresolved_giant_function": hx(0x84C559C0),
        },
        "validated_edges": edges,
        "binary_anchors": [
            binary_anchor("apf_state_descriptor", image, 0x820F4350, 0x820F4398),
            binary_anchor("apf_main_items", image, 0x84E57340, 0x84E575E0),
            binary_anchor("apf_default_callback_fragment", image, 0x846F2E00, 0x846F3090),
            binary_anchor("apf_resource_loader_fragment", image, 0x846EFD38, 0x846EFE18),
            binary_anchor("apf_activation_fragment", image, 0x846F59A8, 0x846F5BB8),
            binary_anchor("apf_state_transition_fragment", image, 0x846F45E0, 0x846F4778),
        ],
    }


PORTME = [
    ("nfl2k5", "0x000F3E90", "recover and save the complete default-event function boundary; the x86 body is manually traced but absent from the function ledger"),
    ("nfl2k5", "0x002C8810", "recover and save the navigation LAYT-loader boundary reached by the tail jump at 0x00150015"),
    ("nfl2k5", "0x00327A50", "name and reimplement event-4 action callback semantics"),
    ("nfl2k5", "0x00327A90", "recover the missing function boundary and event-6 action callback semantics"),
    ("nfl2k5", "0x00192090", "recover the missing chained event-6 callback boundary and semantics"),
    ("nfl2k5", "0x0024D490", "name and reimplement event-8 action callback semantics"),
    ("nfl2k5", "0x0024D440", "name and reimplement the The Crib type-9 navigation callback"),
    ("nfl2k5", "0x000F1D50", "recover the text-render backend below the proved literal-copy/lowercase path"),
    ("nfl2k5", "0x00515660", "replace direct English row literals with a locale-aware host policy only after compatibility requirements are defined"),
    ("apf2k8", "0x846F2E00", "recover and save the complete PPC default-event boundary through 0x846F3088"),
    ("apf2k8", "0x846F45E0", "recover and save the state-transition boundary through 0x846F4774 and determine its exact push/replace contract"),
    ("apf2k8", "0x846F3CB0", "create the missing selection-clamp function boundary and preserve its per-stack selection behavior"),
    ("apf2k8", "0x846F59A8", "recover and save the complete item-activation boundary through 0x846F5BB4"),
    ("apf2k8", "0x846EFD38", "recover and save the quicknav resource-loader boundary through 0x846EFE10"),
    ("apf2k8", "0x846EE1A8", "recover the fragmented recursive LAYT initializer boundary through 0x846EE50C"),
    ("apf2k8", "0x846EF638", "recover the fragmented layout draw traversal boundary and all record-type cases"),
    ("apf2k8", "0x846EF1D0", "recover the fragmented type-0 draw function while preserving the +0x34 bit-29 gate"),
    ("apf2k8", "0x84A57F70", "name and reimplement the Xbox Live primary navigation callback"),
    ("apf2k8", "0x846CAE10", "name and reimplement the Xbox Live preflight callback at source row +0x48"),
    ("apf2k8", "0x820F4354", "prove how SlideOnNav_MainMenu selects a type-3 record and reaches 0x846EDEA8"),
    ("apf2k8", "0x84C559C0", "resolve the giant function or another reference that binds visual layout_mainmenu ID 0x48C6D154 to the native main route"),
    ("apf2k8", "0x846F40B8", "trace runtime label +0x08 through the final text renderer/localization policy"),
    ("apf2k8", "0x84A58698", "find the cold-boot predecessor; this callback only proves a transition back to main"),
]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    xbe_data = args.nfl_xbe.read_bytes()
    apf_data = args.apf_pe.read_bytes()
    header = json.loads(args.nfl_header.read_text(encoding="utf-8"))
    layout_semantics = json.loads(args.layout_semantics.read_text(encoding="utf-8"))
    layouts = read_layout_rows(args.layout_records)

    expect(sha256_bytes(xbe_data), NFL_XBE_SHA256, "NFL XBE SHA-256")
    expect(header["sha256"], NFL_XBE_SHA256, "NFL header-report SHA-256")
    expect(sha256_bytes(apf_data), APF_PE_SHA256, "APF PE SHA-256")
    expect(layout_semantics["schema"], "vc_cross_title_layout_semantics/v1", "layout-semantics schema")

    nfl = decode_nfl(XbeImage(xbe_data, header), layouts)
    apf = decode_apf(ApfImage(apf_data), layouts)
    expect(nfl["visual_layout_entry"]["record_count"], 3, "NFL visual main-menu record count")
    expect(apf["visual_layout_entry"]["record_count"], 7, "APF visual main-menu record count")

    return {
        "schema": SCHEMA,
        "scope": {
            "kind": "bounded static native main-menu state/callback trace",
            "executes_original_game": False,
            "launches_original_menu": False,
            "claims_source_equivalence": False,
        },
        "inputs": {
            "nfl2k5_xbe": {"sha256": NFL_XBE_SHA256, "md5": header["md5"]},
            "apf2k8_unpatched_pe_memory_image": {"sha256": APF_PE_SHA256, "size": len(apf_data), "va_mapping": "file_offset = VA - 0x82000000"},
            "layout_semantics_schema": layout_semantics["schema"],
        },
        "nfl2k5": nfl,
        "apf2k8": apf,
        "cross_title_correspondence": [
            {
                "concept": "state-selected LAYT",
                "nfl2k5": "descriptor +0x18 -> UTF-16LE main_menu_sub -> 0x000449E0",
                "apf2k8": "descriptor +0x2C -> UTF-16BE quicknav -> CRC32 -> 0x84B16398",
                "status": "conceptual homolog; no cross-ISA identical body claim",
            },
            {
                "concept": "navigation row materialization",
                "nfl2k5": "0x0014FF80 copies source +0x04 label into runtime +0x28",
                "apf2k8": "0x846F40B8 copies source +0x04 label into runtime +0x08",
                "status": "same data-driven pattern with different record layouts",
            },
            {
                "concept": "state stack and action dispatch",
                "nfl2k5": "0x0006E2E0/0x0006E390/0x0006E4E0",
                "apf2k8": "0x846F8F00/0x846F8A60/0x846F9090",
                "status": "semantic correspondence only",
            },
        ],
        "portme": [
            {"platform": platform, "address": address, "reason": reason}
            for platform, address, reason in PORTME
        ],
        "result": {
            "worked": [
                "decoded both exact main state descriptors and navigation arrays",
                "proved NFL main_menu_sub and APF quicknav runtime resource lookups",
                "proved navigation activation, update, draw, and runtime visibility chains at the listed addresses",
                "joined state-loaded resources to exact extracted LAYT entries",
            ],
            "failed_or_unproved": [
                "APF layout_mainmenu visual backdrop has no proved executable edge from the main state",
                "APF final label renderer/localization resolver is not proved",
                "neither title has a proved cold-boot-to-original-main-menu chain",
                "no original menu was executed or launched",
            ],
            "blocking": "address-specific PORTME entries must be resolved before a source-equivalent native main menu can be claimed",
        },
    }


def evidence_rows(report: dict[str, Any]) -> Iterable[tuple[str, str, str, str, str]]:
    yield ("nfl2k5", "layout", "0x00515678", "proved", "state descriptor names main_menu_sub, outer 8 / inner 18")
    yield ("nfl2k5", "resource_lookup", "0x000F38C6", "proved", "LAYT lookup of descriptor +0x18 via 0x000449E0")
    yield ("nfl2k5", "row_constructor", "0x0014FF80", "proved", "0x34-byte source rows become 0x2C-byte runtime rows")
    yield ("nfl2k5", "activation", "0x00150020", "proved", "type 0 pushes source +0x08; type 9 calls source +0x28")
    yield ("nfl2k5", "draw", "0x000F2F70", "proved", "active +0x5A0 layout tailcalls 0x00143DE0")
    yield ("nfl2k5", "localization", "0x0014FDA0", "partial", "direct UTF-16LE labels copied/lowercased; no locale resolver proved")
    yield ("apf2k8", "layout", "0x820F437C", "proved", "state descriptor names quicknav, global.iff outer 1310 / inner 57")
    yield ("apf2k8", "resource_lookup", "0x846EFDE0", "proved", "CRC32 quicknav ID 0x210FFA23 and LAYT hash 0x86A1AC9E reach 0x84B16398")
    yield ("apf2k8", "row_constructor", "0x846F40B8", "proved", "0x60-byte source rows become runtime rows with source +0x04 and label +0x08")
    yield ("apf2k8", "activation", "0x846F59A8", "proved", "types 10/11/12 dispatch callback/transition/replace paths")
    yield ("apf2k8", "draw", "0x846F06D4", "proved", "event-7 active +0x410 layout reaches recursive traversal")
    yield ("apf2k8", "visibility", "0x846EF270", "proved", "type-0 draw tests +0x34 bit 29")
    yield ("apf2k8", "timeline", "0x846EE39C", "partial", "initializer reaches 0x846EDD30; main binding to 0x846EDEA8 remains unproved")
    yield ("apf2k8", "visual_layout_link", "0x84C559C0", "blocked", "no proved edge to layout_mainmenu ID 0x48C6D154")


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["platform", "category", "address", "status", "evidence"])
        writer.writerows(evidence_rows(report))


def write_portme_c(path: Path) -> None:
    lines = [
        "/* Generated evidence ledger; it is not original game source. */",
        "#include <stdint.h>",
        "",
        "void vc_menu_state_trace_unresolved_boundaries(void) {",
    ]
    for platform, address, reason in PORTME:
        lines.append(f"    // PORTME: {platform} function/data at {address}: {reason}.")
    lines.extend(["    (void)(uint32_t)0;", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nfl-xbe", type=Path, required=True)
    parser.add_argument("--nfl-header", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--layout-semantics", type=Path, required=True)
    parser.add_argument("--layout-records", type=Path, required=True)
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
        write_portme_c(args.portme_c_out)
    except (OSError, ValueError, KeyError, TraceError) as exc:
        print(f"menu_state_trace: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
