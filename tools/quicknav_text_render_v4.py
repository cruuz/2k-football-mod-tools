#!/usr/bin/env python3
"""Generate the evidence-bounded APF quicknav text-render v4 report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any


SCHEMA = "vc_apf_quicknav_text_render/v4"
APF_BASE = 0x82000000
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
BASE_V3_SHA256 = "59f81323ba3edc5bbb0331c47998a1bfe15fc4246358863941fc54287e6f860b"
LOCALIZATION_TSV_SHA256 = "16693a0d7bbe6b16e40b8366c8400dc920332322a379840e6e9959168514e721"
PDATA_FIRST = 0x844DBE00
PDATA_AFTER_LAST = 0x84500000


class ReportError(RuntimeError):
    pass


def hx(value: int) -> str:
    return f"0x{value:08X}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ReportError(f"{label}: expected {expected!r}, got {actual!r}")


class Image:
    def __init__(self, data: bytes):
        self.data = data

    def offset(self, address: int, size: int = 1) -> int:
        offset = address - APF_BASE
        if offset < 0 or offset + size > len(self.data):
            raise ReportError(f"address {hx(address)} (+{size}) is outside APF PE image")
        return offset

    def read(self, address: int, size: int) -> bytes:
        offset = self.offset(address, size)
        return self.data[offset : offset + size]

    def u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def branch(self, address: int) -> tuple[int, bool]:
        word = self.u32(address)
        if word >> 26 != 18:
            raise ReportError(f"word at {hx(address)} is not an immediate PPC branch")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = displacement if word & 2 else address + displacement
        return target & 0xFFFFFFFF, bool(word & 1)


def edge(image: Image, site: int, target: int, link: bool = True) -> dict[str, str]:
    actual_target, actual_link = image.branch(site)
    expect(actual_target, target, f"branch target at {hx(site)}")
    expect(actual_link, link, f"branch link at {hx(site)}")
    return {"site": hx(site), "target": hx(target), "kind": "call" if link else "jump"}


def expect_word(image: Image, address: int, word: int, label: str) -> None:
    expect(image.u32(address), word, f"{label} at {hx(address)}")


def find_pdata_slot(image: Image, address: int, metadata: int) -> int:
    matches = []
    for slot in range(PDATA_FIRST, PDATA_AFTER_LAST, 8):
        if image.u32(slot) == address and image.u32(slot + 4) == metadata:
            matches.append(slot)
    expect(len(matches), 1, f"unique PDATA pair for {hx(address)}")
    return matches[0]


def boundary(
    image: Image, name: str, address: int, end: int, metadata: int, status: str
) -> dict[str, Any]:
    slot = find_pdata_slot(image, address, metadata)
    encoded_words = (metadata >> 8) & 0xFFFF
    expect(address + encoded_words * 4, end, f"PDATA extent for {name}")
    blob = image.read(address, end - address)
    return {
        "name": name,
        "address": hx(address),
        "end_exclusive": hx(end),
        "extent_size": len(blob),
        "extent_sha256": digest(blob),
        "pdata_slot": hx(slot),
        "pdata_metadata": hx(metadata),
        "status": status,
    }


def raw_extent(image: Image, name: str, address: int, end: int, status: str) -> dict[str, Any]:
    blob = image.read(address, end - address)
    return {
        "name": name,
        "address": hx(address),
        "end_exclusive": hx(end),
        "extent_size": len(blob),
        "extent_sha256": digest(blob),
        "status": status,
    }


def parse_trace_instructions(text: str) -> dict[int, str]:
    result: dict[int, str] = {}
    pattern = re.compile(
        r"^(0x[0-9A-F]{8}) (?:[0-9A-F]{2} ){3}[0-9A-F]{2} (.*?) owner=",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        result[int(match.group(1), 16)] = match.group(2)
    return result


def register_mentions(
    instructions: dict[int, str], register: str, start: int, end: int
) -> list[dict[str, str]]:
    return [
        {"address": hx(address), "instruction": instruction}
        for address, instruction in sorted(instructions.items())
        if start <= address < end and re.search(rf"\b{re.escape(register)}\b", instruction)
    ]


def byte_occurrences(data: bytes, value: int) -> list[str]:
    pattern = value.to_bytes(4, "big")
    result = []
    cursor = 0
    while True:
        cursor = data.find(pattern, cursor)
        if cursor < 0:
            return result
        result.append(hx(APF_BASE + cursor))
        cursor += 1


def constructed_address_hits(image: Image, target: int) -> list[dict[str, Any]]:
    high = ((target + 0x8000) >> 16) & 0xFFFF
    low = target & 0xFFFF
    result = []
    limit = len(image.data) - 24
    for offset in range(0, limit, 4):
        word = struct.unpack_from(">I", image.data, offset)[0]
        if word >> 26 != 15 or (word & 0xFFFF) != high or ((word >> 16) & 31) != 0:
            continue
        source_register = (word >> 21) & 31
        for delta in range(4, 24, 4):
            second = struct.unpack_from(">I", image.data, offset + delta)[0]
            if (
                second >> 26 == 14
                and ((second >> 16) & 31) == source_register
                and (second & 0xFFFF) == low
            ):
                result.append(
                    {
                        "lis": hx(APF_BASE + offset),
                        "addi": hx(APF_BASE + offset + delta),
                        "source_register": f"r{source_register}",
                        "destination_register": f"r{(second >> 21) & 31}",
                    }
                )
    return result


def localization_rows(path: Path) -> dict[str, dict[str, str]]:
    wanted = {"0x6e67dc9f", "0xd00114ff"}
    result: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            key = row["text_id"].lower()
            if key in wanted and row["outer_index"] == "1127" and row["table_name"] == "English":
                result[key] = row
    expect(set(result), wanted, "case-transform localization records")
    return result


BOUNDARIES = [
    ("active run-string width query", 0x84692B10, 0x84692BD0, 0x40003005),
    ("generic text/run renderer", 0x84692BE0, 0x84693194, 0x40016D05),
    ("proposed provider-output handoff", 0x84693198, 0x84693220, 0x40002204),
    ("render-run state copier", 0x84693288, 0x8469337C, 0x40003D03),
    ("render-run state finalizer", 0x84693380, 0x846933BC, 0x40000F04),
    ("markup/string callback dispatcher", 0x846E64C0, 0x846E66F0, 0x40008C04),
    ("normal string measurement wrapper", 0x846E6E58, 0x846E6EB8, 0x40001804),
    ("generic text-state submission wrapper", 0x846E6EB8, 0x846E6F0C, 0x40001504),
    ("text positioning dispatch", 0x846E90D8, 0x846E91B8, 0x40003805),
    ("active string positioning wrapper", 0x846E91B8, 0x846E91FC, 0x40001105),
    ("normal per-glyph vertex backend", 0x846E9510, 0x846EA134, 0x40030905),
    ("special per-glyph vertex backend", 0x846EA138, 0x846EAC74, 0x4002CF05),
    ("normal UTF-16 text walker", 0x846EAC78, 0x846EAEB0, 0x40008E05),
    ("normal text draw wrapper", 0x846EAEB0, 0x846EAF1C, 0x40001B07),
    ("special UTF-16 text walker", 0x846EB080, 0x846EB314, 0x4000A505),
    ("special text width wrapper", 0x846EB318, 0x846EB33C, 0x40000903),
    ("special text draw wrapper", 0x846EB3A8, 0x846EB41C, 0x40001D05),
    ("type-0 runtime callback dispatcher", 0x846EEFD0, 0x846EF1D0, 0x40008003),
    ("type-0 layout draw", 0x846EF1D0, 0x846EF634, 0x40011906),
    ("layout traversal/type dispatch", 0x846EF638, 0x846EF7A0, 0x40005A03),
    ("template_quicknav setup callback", 0x846F4E38, 0x846F5054, 0x40008703),
    ("template_quicknav event callback", 0x846F5058, 0x846F5194, 0x40004F03),
    ("template_quicknav label provider", 0x846F5198, 0x846F52B4, 0x40004703),
    ("reference-counted string UTF-16 adapter", 0x84762610, 0x8476284C, 0x40008F03),
    ("reference-counted string assignment", 0x847628E8, 0x847629A8, 0x40003005),
    ("dynamic vertex writer begin", 0x84B1B700, 0x84B1B794, 0x40002504),
    ("dynamic vertex writer finalizer", 0x84B1B848, 0x84B1B884, 0x40000F04),
    ("GPU command-buffer draw commit", 0x84B2D400, 0x84B2D4A4, 0x40002905),
    ("alternate render queue path", 0x84B32850, 0x84B32980, 0x40004C03),
    ("render queue submission path", 0x84B47838, 0x84B478F0, 0x40002E03),
    ("dynamic vertex writer final submit", 0x84B48520, 0x84B485E0, 0x40003005),
]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    xex = args.apf_xex.read_bytes()
    pe_data = args.apf_pe.read_bytes()
    base_data = args.base_v3.read_bytes()
    loc_data = args.localization_tsv.read_bytes()
    trace_data = args.trace.read_bytes()
    pseudo_data = args.pseudo.read_bytes()
    expect(digest(xex), APF_XEX_SHA256, "APF XEX SHA-256")
    expect(digest(pe_data), APF_PE_SHA256, "APF PE SHA-256")
    expect(digest(base_data), BASE_V3_SHA256, "menu-label v3 SHA-256")
    expect(digest(loc_data), LOCALIZATION_TSV_SHA256, "localization TSV SHA-256")

    base = json.loads(base_data)
    expect(base["schema"], "vc_apf_menu_label_renderer/v3", "base v3 schema")
    option_bindings = base["main_label_ownership"]["loaded_layout_join"]["option_bindings"]
    expect(len(option_bindings), 8, "v3 option binding count")
    expect({row["content_provider"] for row in option_bindings}, {"0x846F5198"}, "v3 providers")

    trace = trace_data.decode("utf-8")
    pseudo = pseudo_data.decode("utf-8")
    markers = [
        "APF 2K8 quicknav text-render read-only v4 trace",
        "RANGE 0x84692B10..0x84692BCF",
        "RANGE 0x84692BE0..0x84693193",
        "RANGE 0x846EEFD0..0x846EF1CF",
        "RANGE 0x846EF1D0..0x846EF633",
        "RANGE 0x846EF638..0x846EF79F",
        "RANGE 0x846E64C0..0x846E66EF",
        "RANGE 0x846E9368..0x846E950F",
        "RANGE 0x846E9510..0x846EA133",
        "RANGE 0x846EA138..0x846EAC73",
        "RANGE 0x846EAC78..0x846EAEAF",
        "RANGE 0x846EB080..0x846EB313",
        "RANGE 0x84B1B700..0x84B1B793",
        "RANGE 0x84B48520..0x84B485DF",
        "RANGE 0x846F5198..0x846F52B3",
        "POST_DISASSEMBLY_REFERENCES",
    ]
    for marker in markers:
        if marker not in trace:
            raise ReportError(f"Ghidra trace missing marker {marker!r}")
    if "Saved-boundary APF quicknav text pseudo-C" not in pseudo:
        raise ReportError("unexpected v4 Ghidra pseudo-C provenance")

    image = Image(pe_data)
    instructions = parse_trace_instructions(trace)
    r4_audit = register_mentions(instructions, "r4", 0x84693198, 0x84693220)
    expect(
        r4_audit,
        [
            {"address": "0x846931BC", "instruction": "addi r4,r31,0xa8"},
            {"address": "0x846931F0", "instruction": "addi r4,r1,0x50"},
        ],
        "0x84693198 incoming r4 audit",
    )

    expect_word(image, 0x846EF184, 0x4E800421, "indirect provider call")
    expect_word(image, 0x846EF058, 0x3D608501, "provider scratch high address")
    expect_word(image, 0x846EF060, 0x3B8BC060, "provider scratch low address")
    expect_word(image, 0x846EF05C, 0x3B200400, "provider capacity")
    expect_word(image, 0x846EF144, 0xB17C0000, "provider scratch clear")
    expect_word(image, 0x846EF17C, 0x817F0008, "provider callback load")
    expect_word(image, 0x846931AC, 0x817F0094, "run flags load")
    expect_word(image, 0x846931BC, 0x389F00A8, "run embedded string selection")
    expect_word(image, 0x846931F0, 0x38810050, "empty fallback string selection")
    expect_word(image, 0x84692960, 0x3D605361, "special material high hash")
    expect_word(image, 0x84692964, 0x616A92E7, "special material low hash")
    expect_word(image, 0x84692A4C, 0x3D60D001, "uppercase template high ID")
    expect_word(image, 0x84692A58, 0x616B14FF, "uppercase template low ID")
    expect_word(image, 0x84692AC8, 0x3D606E67, "lowercase template high ID")
    expect_word(image, 0x84692ACC, 0x616BDC9F, "lowercase template low ID")

    dispatch_edges = [
        edge(image, 0x846EF70C, 0x846EF1D0),
        edge(image, 0x846EF5D0, 0x846EEFD0),
        edge(image, 0x846EF190, 0x84693288),
        edge(image, 0x846EF19C, 0x84693198),
    ]
    text_edges = [
        edge(image, 0x846931C0, 0x846929F8),
        edge(image, 0x846931C8, 0x84692BE0),
        edge(image, 0x846931F8, 0x846929F8),
        edge(image, 0x84693200, 0x84692BE0),
        edge(image, 0x84692B4C, 0x846E6E58),
        edge(image, 0x84692B54, 0x846E9360),
        edge(image, 0x84692B8C, 0x846EB318),
        edge(image, 0x846930C8, 0x846E91B8),
        edge(image, 0x84693108, 0x846EB3A8),
        edge(image, 0x84693160, 0x846E91B8),
        edge(image, 0x84693174, 0x846EAEB0),
        edge(image, 0x846EAEE0, 0x846E64B0),
        edge(image, 0x846EAEF8, 0x846EAC78),
        edge(image, 0x846EAE78, 0x846E9510),
        edge(image, 0x846EB3E0, 0x846E64B0),
        edge(image, 0x846EB408, 0x846EB080),
        edge(image, 0x846EB1C8, 0x846EA138),
    ]
    vertex_edges = [
        edge(image, 0x846E998C, 0x84B1B700),
        edge(image, 0x846E9ABC, 0x84B1B848),
        edge(image, 0x846EA518, 0x84B1B700),
        edge(image, 0x846EA66C, 0x84B1B848),
        edge(image, 0x84B1B770, 0x84B48470),
        edge(image, 0x84B1B864, 0x84B48520),
        edge(image, 0x84B48560, 0x84B2D400),
        edge(image, 0x84B48574, 0x84B2AE80),
        edge(image, 0x84B485A0, 0x84B32850),
        edge(image, 0x84B485BC, 0x84B47838),
    ]

    scratch_hits = constructed_address_hits(image, 0x8500C060)
    expect(
        scratch_hits,
        [{"lis": "0x846EF058", "addi": "0x846EF060", "source_register": "r11", "destination_register": "r28"}],
        "provider scratch direct constructions",
    )
    active_string_hits = constructed_address_hits(image, 0x85008DA8)
    expect(len(active_string_hits), 8, "active string UTF-16 scratch constructions")
    static_binding_hits = constructed_address_hits(image, 0x84D30328)
    expect(static_binding_hits, [], "static binding base direct constructions")
    expect(byte_occurrences(pe_data, 0x8500C060), [], "provider scratch fullword occurrences")
    expect(byte_occurrences(pe_data, 0x84D30328), [], "binding base fullword occurrences")

    loc = localization_rows(args.localization_tsv)
    recovered = [
        boundary(
            image,
            name,
            start,
            end,
            metadata,
            "exact PDATA-encoded extent; raw trace is authoritative where saved Ghidra stops at the prologue or jump table",
        )
        for name, start, end, metadata in BOUNDARIES
    ]
    raw_extents = [
        raw_extent(image, "active string to UTF-16 adapter leaf", 0x846E64B0, 0x846E64C0, "saved leaf; no PDATA entry"),
        raw_extent(image, "special ASCII glyph-width walk", 0x846E9368, 0x846E9510, "saved orphan extent ending at next PDATA function"),
        raw_extent(image, "vertex position writer", 0x84B1B8E0, 0x84B1B928, "saved non-PDATA leaf"),
        raw_extent(image, "vertex UV writer", 0x84B1B928, 0x84B1B93C, "saved non-PDATA leaf"),
        raw_extent(image, "vertex color writer", 0x84B1B960, 0x84B1B970, "saved non-PDATA leaf"),
        raw_extent(image, "GPU command packet writer", 0x84B2AE80, 0x84B2AEC8, "saved non-PDATA leaf; emits 0x0A000000 packet class"),
        raw_extent(image, "dynamic vertex allocation/setup", 0x84B48470, 0x84B4851C, "saved non-PDATA function"),
    ]

    expect_word(image, 0x84B2AE94, 0x39000005, "GPU packet class source")
    expect_word(image, 0x84B2AEB4, 0x510AC80C, "GPU packet class insertion")
    expect_word(image, 0x84B2AEB8, 0x914B0000, "GPU packet header store")

    portme = [
        {
            "address": "0x84D30328",
            "text": "prove how the eight static six-word template_quicknav bindings are materialized into the runtime table read from layout/root +0x14; no direct fullword or lis/addi reference to the static base exists",
        },
        {
            "address": "0x84693198",
            "text": "recover the intended provider-string integration or prove the retail callback output dead: the exact type-0 caller passes 0x8500C060 in r4, but this function overwrites r4 with run +0xA8 or an empty local object before every use",
        },
        {
            "address": "0x846E9510",
            "text": "reconstruct complete structured control flow for the normal per-glyph backend and map its material identifier to a named FONT/KERN resource and atlas texture",
        },
        {
            "address": "0x846EA138",
            "text": "reconstruct complete structured control flow for the special per-glyph backend and identify the exact relationship between its hard-coded ASCII metrics and shipped geometry/font assets",
        },
        {
            "address": "0x84B48520",
            "text": "identify the final Xenos/XDK draw opcode or API boundary after dynamic vertex finalization; command-buffer packet emission and queue branches are proved, but a named GPU draw call is not",
        },
        {
            "address": "0x820F4350",
            "text": "establish alternate-locale source replacement policy; the US provider bypasses localization lookup for label content, while the disconnected generic renderer can still apply MAKE_UPPERCASE or MAKE_LOWERCASE templates",
        },
    ]

    return {
        "schema": SCHEMA,
        "provenance": {
            "apf_xex": {"path": "extracted/All-Pro Football 2K8 (USA)/default.xex", "sha256": digest(xex)},
            "apf_unpatched_pe": {"path": "transient xex_extract_pe output", "sha256": digest(pe_data)},
            "base_menu_label_v3": {"path": "reports/assets/menu_label_renderer_v3.json", "sha256": digest(base_data)},
            "localization_tsv": {"path": "reports/assets/apf_txt_localization.tsv", "sha256": digest(loc_data)},
            "ghidra_trace": {"path": "reports/assets/quicknav_text_render_v4_ghidra/apf_quicknav_text_render_v4_trace.txt", "sha256": digest(trace_data)},
            "ghidra_pseudo_c": {"path": "reports/assets/quicknav_text_render_v4_ghidra/apf_quicknav_text_render_v4_pseudo_c.c", "sha256": digest(pseudo_data)},
            "method": "static unpatched PE decoding plus clean -readOnly Ghidra trace; no retail code execution",
        },
        "scope": {
            "launches_original_menu": False,
            "writes_executable": False,
            "writes_ghidra_project": False,
            "provider_runtime_callback_invocation_proved": True,
            "provider_output_destination_proved": True,
            "provider_output_semantic_consumer_proved": False,
            "immediate_handoff_discards_provider_argument_proved": True,
            "static_to_runtime_binding_materialization_proved": False,
            "generic_text_backend_proved": True,
            "generic_utf16_glyph_walk_proved": True,
            "generic_vertex_generation_proved": True,
            "generic_gpu_command_buffer_path_proved": True,
            "named_font_resource_proved": False,
            "atlas_binding_proved": False,
            "named_final_gpu_draw_api_proved": False,
            "main_provider_localization_bypass_proved": True,
            "alternate_locale_policy_proved": False,
        },
        "runtime_provider_dispatch": {
            "static_bindings_from_v3": option_bindings,
            "static_binding_table": "0x84D30328..0x84D303E7",
            "runtime_table_load": {"site": "0x846EF0D8", "field": "layout/root +0x14"},
            "runtime_entry_stride": 24,
            "runtime_entry_schema": [
                {"offset": "+0x00", "use": "optional match against type-0 node +0x08"},
                {"offset": "+0x04", "use": "optional match against render run +0xA0"},
                {"offset": "+0x08", "use": "callback pointer; zero terminates table"},
                {"offset": "+0x0C", "use": "callback context +0x04 (quicknav slot)"},
                {"offset": "+0x10", "use": "callback context +0x08"},
                {"offset": "+0x14", "use": "callback context +0x0C"},
            ],
            "callback_context_at_stack_0x50": [
                {"offset": "+0x00", "value": "caller r4 / manager context"},
                {"offset": "+0x04", "value": "binding +0x0C / slot"},
                {"offset": "+0x08", "value": "binding +0x10"},
                {"offset": "+0x0C", "value": "binding +0x14"},
                {"offset": "+0x10", "value": "0x8500C060 UTF-16 destination"},
                {"offset": "+0x14", "value": "0x00000400 capacity"},
                {"offset": "+0x18", "value": "caller r6 / active manager used by provider"},
                {"offset": "+0x1C", "value": "0x84D22F00 render/style state"},
                {"offset": "+0x20", "value": "current render run"},
            ],
            "dispatch_edges": dispatch_edges,
            "result": "type-0 traversal, runtime match, callback invocation, destination, and capacity are exact; static table materialization remains unproved",
        },
        "provider_output_handoff": {
            "provider": "0x846F5198",
            "destination": "0x8500C060",
            "capacity_utf16_units": 1024,
            "selected_output": base["main_label_ownership"]["runtime_label_provider"]["selected_row_output"],
            "ordinary_output": base["main_label_ownership"]["runtime_label_provider"]["ordinary_row_output"],
            "only_direct_address_construction": scratch_hits,
            "fullword_pointer_occurrences": [],
            "handoff_call": {"site": "0x846EF19C", "function": "0x84693198", "r3": "render run", "r4": "0x8500C060"},
            "incoming_r4_mentions_in_0x84693198": r4_audit,
            "callee_source_selection": {
                "flag_test": "render run +0x94 bit 0x10",
                "set": "run +0xA8 reference-counted string object",
                "clear": "new empty local reference-counted string object",
                "provider_scratch_selected": False,
            },
            "selected_style_side_effect": "0x846F5210 stores a selected-state value through context +0x1C (0x84D22F00); this can affect render state even though the label characters are not handed off",
            "result": "the immediate type-0 handoff does not consume the provider buffer; no later Main-label semantic consumer is statically proved",
        },
        "generic_text_backend": {
            "ownership_warning": "statically reachable after the discarded provider argument, but its character source is run +0xA8 rather than 0x8500C060; it is not proof that Main provider labels render",
            "active_string_state": "0x84D22FAC (global render state 0x84D22EC0 +0xEC)",
            "source_and_case_transform": {
                "run_string": "0x846931BC selects run +0xA8 when run +0x94 bit 0x10 is set",
                "empty_fallback": "0x846931E0..0x846931F0 constructs/selects an empty local string otherwise",
                "uppercase": {"text_id": "0xD00114FF", "text": loc["0xd00114ff"]["text"]},
                "lowercase": {"text_id": "0x6E67DC9F", "text": loc["0x6e67dc9f"]["text"]},
                "plain_assignment": "0x84692AF8 -> 0x847628E8 assigns the supplied reference-counted string",
            },
            "utf16_adapter": {
                "function": "0x846E64B0 -> 0x84762610",
                "scratch": "0x85008DA8",
                "capacity": 2048,
                "direct_constructions": active_string_hits,
            },
            "material_selection": {
                "identifier": "render run +0x90",
                "normal": "0x84692974 resolves the identifier through 0x846E6228, then 0x84692984 stores the result into text render state",
                "special_identifier": "0x536192E7",
                "special_behavior": "bypasses the normal resolver and uses 0x846E9368 hard-coded ASCII widths plus 0x846EB080 -> 0x846EA138",
                "named_resource": None,
            },
            "normal_path": {
                "measure": "0x84692B4C -> 0x846E6E58 -> 0x846E64C0",
                "walk": "0x846EAEB0 -> 0x846E64B0 -> 0x846EAC78",
                "markup": "0x846EAC78 treats UTF-16 0x007C as an inline command delimiter",
                "glyph": "0x846EAE78 -> 0x846E9510",
            },
            "special_path": {
                "measure": "0x84692B54/0x84692B8C -> constant 0x78 and 0x846E9368 width walk",
                "metrics": "uppercase, lowercase, digits, colon, quote, space, minus, plus, and dollar are handled by fixed tables at 0x84D2BF50..0x84D2C130",
                "walk": "0x846EB3A8 -> 0x846E64B0 -> 0x846EB080",
                "glyph": "0x846EB080 -> 0x846EA138",
            },
            "text_edges": text_edges,
            "vertex_and_submission": {
                "begin": "0x84B1B700 -> 0x84B48470 allocates/prepares a dynamic vertex writer",
                "color": "0x84B1B960",
                "uv": "0x84B1B928",
                "position": "0x84B1B8E0",
                "finalize": "0x84B1B848 -> 0x84B48520",
                "command_packet": "0x84B2AE80 emits an Xbox GPU command-buffer packet with class bits 0x0A000000",
                "queue_branches": ["0x84B2D400", "0x84B32850", "0x84B47838"],
                "edges": vertex_edges,
                "named_final_draw_api": None,
            },
        },
        "localization_and_fallback": {
            "provider_label_source": "US descriptor UTF-16 literals; no resolver call in the v3-proved source-to-provider chain",
            "provider_selected_markup": "{0}|M_PRIMARY|",
            "generic_renderer_case_templates": [loc["0xd00114ff"]["text"], loc["0x6e67dc9f"]["text"]],
            "generic_renderer_empty_fallback": "when render run +0x94 bit 0x10 is clear, 0x84693198 supplies an empty string object, not the provider scratch",
            "global_policy": "unproved; provider-source bypass and downstream case-format support are separate facts",
        },
        "static_binding_materialization_negative": {
            "static_base": "0x84D30328",
            "static_base_fullword_occurrences": [],
            "static_base_lis_addi_constructions": static_binding_hits,
            "ghidra_saved_references": [],
            "result": "the runtime entry schema matches the six static words, but no instruction-level copy/registration edge has been recovered",
        },
        "recovered_boundaries": recovered,
        "raw_or_orphan_extents": raw_extents,
        "negative_findings": [
            "0x84693198 has no read of incoming r4 before replacing it on both branches",
            "0x8500C060 has one direct address construction (the dispatcher) and no fullword pointer occurrence in the PE image",
            "the actual UTF-16 backend converts a separate reference-counted string into 0x85008DA8",
            "no named FONT/KERN resource, atlas binding, or final XDK draw API is attributable to the Main provider output",
            "0x846F4E38 and 0x846F5058 contain template behavior but no direct reference to static binding base 0x84D30328",
        ],
        "phase_summary": {
            "worked": [
                "proved type-0 traversal, runtime binding match, provider callback invocation, buffer, and capacity",
                "proved the immediate provider-string handoff discards its incoming string argument",
                "recovered the separate active-string, UTF-16 walk, glyph metric, vertex generation, and command-buffer paths",
                "resolved downstream upper/lower case templates from the shipped English localization table",
            ],
            "failed_or_unproved": [
                "Main provider characters do not have a proved semantic consumer",
                "static binding table materialization into layout/root +0x14 is not instruction-proved",
                "font resource identity, atlas binding, and a named final GPU draw API are not proved",
                "alternate-locale policy is not proved",
            ],
            "blocking": "recover the missing provider-buffer-to-run-string edge, or prove at runtime that this retail path intentionally renders baked/run-owned text",
        },
        "portme": portme,
    }


def write_tsv(report: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["category", "address", "end_exclusive", "status", "evidence"])
        for item in report["recovered_boundaries"]:
            writer.writerow(["pdata_boundary", item["address"], item["end_exclusive"], "proved", item["name"]])
        for item in report["raw_or_orphan_extents"]:
            writer.writerow(["raw_extent", item["address"], item["end_exclusive"], "proved", item["name"]])
        writer.writerow(["provider_dispatch", "0x846EF184", "", "proved", "runtime entry +0x08 indirect callback"])
        writer.writerow(["provider_output", "0x8500C060", "", "proved", "1024-unit UTF-16 scratch"])
        writer.writerow(["handoff_negative", "0x84693198", "0x84693220", "proved", "incoming r4 replaced before use"])
        writer.writerow(["actual_string", "run+0xA8", "", "proved", "selected only when run+0x94 bit 0x10 is set"])
        writer.writerow(["active_utf16", "0x85008DA8", "", "proved", "separate 2048-unit backend scratch"])
        writer.writerow(["font_identity", "0x846E6228", "", "unproved", "material resolver reached but named FONT/atlas join missing"])
        writer.writerow(["gpu_submit", "0x84B48520", "0x84B485E0", "partial", "command path proved; named XDK draw API missing"])
        for item in report["portme"]:
            writer.writerow(["portme", item["address"], "", "blocked", item["text"]])


def write_portme(report: dict[str, Any], path: Path) -> None:
    lines = [
        "/* Generated APF quicknav text-render v4 blockers; not original game source. */",
        "#include <stdint.h>",
        "",
        "void vc_apf_quicknav_text_render_v4_unresolved(void) {",
    ]
    for item in report["portme"]:
        lines.append(f"    // PORTME: apf2k8 function/data at {item['address']}: {item['text']}.")
    lines.extend(["    (void)(uint32_t)0;", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--base-v3", type=Path, required=True)
    parser.add_argument("--localization-tsv", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    parser.add_argument("--portme-c-out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(report, args.tsv_out)
    write_portme(report, args.portme_c_out)
    print(
        "APF_QUICKNAV_TEXT_RENDER_V4_REPORT "
        f"boundaries={len(report['recovered_boundaries'])} "
        f"raw_extents={len(report['raw_or_orphan_extents'])} "
        f"portme={len(report['portme'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
