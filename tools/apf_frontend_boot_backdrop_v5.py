#!/usr/bin/env python3
"""Build a deterministic APF cold-boot/frontend-backdrop evidence report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any


BASE = 0x82000000
EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
EXPECTED_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"


def hx(value: int) -> str:
    return f"0x{value:08X}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label}: expected {expected!r}, got {actual!r}")


class Image:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()

    def offset(self, address: int) -> int:
        value = address - BASE
        if value < 0 or value >= len(self.data):
            raise ValueError(f"address outside reconstructed PE: {hx(address)}")
        return value

    def u32(self, address: int) -> int:
        return struct.unpack_from(">I", self.data, self.offset(address))[0]

    def span(self, first: int, after_last: int) -> bytes:
        return self.data[self.offset(first) : self.offset(after_last - 1) + 1]

    def utf16(self, address: int, maximum_units: int = 256) -> str:
        out: list[str] = []
        offset = self.offset(address)
        for _ in range(maximum_units):
            code = struct.unpack_from(">H", self.data, offset)[0]
            offset += 2
            if code == 0:
                return "".join(out)
            out.append(chr(code))
        raise ValueError(f"unterminated UTF-16BE string at {hx(address)}")

    def branch(self, address: int) -> tuple[int, bool]:
        word = self.u32(address)
        if word >> 26 != 18:
            raise ValueError(f"not a PPC b/bl instruction at {hx(address)}: {hx(word)}")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = displacement if word & 2 else address + displacement
        return target & 0xFFFFFFFF, bool(word & 1)

    def occurrences(self, needle: bytes) -> list[int]:
        result: list[int] = []
        cursor = 0
        while True:
            cursor = self.data.find(needle, cursor)
            if cursor < 0:
                return result
            result.append(BASE + cursor)
            cursor += 1

    def classic_absolute_constructions(self, target: int, window_instructions: int = 10) -> list[dict[str, str]]:
        """Find nearby same-register LIS+ADDI/ORI absolute constructions."""
        adjusted_high = ((target + 0x8000) >> 16) & 0xFFFF
        high = (target >> 16) & 0xFFFF
        low = target & 0xFFFF
        result: list[dict[str, str]] = []
        for offset in range(0, len(self.data) - window_instructions * 4, 4):
            first = struct.unpack_from(">I", self.data, offset)[0]
            if first >> 26 != 15 or ((first >> 16) & 31) != 0:
                continue
            register = (first >> 21) & 31
            immediate = first & 0xFFFF
            if immediate not in (adjusted_high, high):
                continue
            for delta in range(4, window_instructions * 4 + 1, 4):
                second = struct.unpack_from(">I", self.data, offset + delta)[0]
                opcode = second >> 26
                if (second >> 21) & 31 != register or (second >> 16) & 31 != register:
                    continue
                kind: str | None = None
                if opcode == 14 and immediate == adjusted_high and second & 0xFFFF == low:
                    kind = "lis+addi"
                elif opcode == 24 and immediate == high and second & 0xFFFF == low:
                    kind = "lis+ori"
                if kind:
                    result.append(
                        {
                            "lis_site": hx(BASE + offset),
                            "low_site": hx(BASE + offset + delta),
                            "kind": kind,
                        }
                    )
        return result


BOUNDARIES = [
    (0x84BE9D08, 0x84BE9D10, 0x84BE9EC8, 0xC0007004, "XEX title entry / CRT startup"),
    (0x846913E0, 0x846913E8, 0x8469154C, 0x40005B05, "per-frame main-loop iteration"),
    (0x84691650, 0x84691658, 0x84691C68, 0x40018603, "game/frontend bootstrap"),
    (0x846E0338, 0x846E0340, 0x846E0468, 0x40004C05, "TitlePage update callback"),
    (0x846F9360, 0x846F9368, 0x846F9480, 0x40004803, "state-runtime registration"),
    (0x84A59E68, 0x84A59E70, 0x84A5A4C4, 0x40019703, "StartupMenu callback"),
]


def boundary_rows(image: Image) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry, body, end, metadata, role in BOUNDARIES:
        rows.append(
            {
                "address": hx(entry),
                "body_entry_after_shared_save": hx(body),
                "end_exclusive": hx(end),
                "size": end - entry,
                "pdata_metadata": hx(metadata),
                "role": role,
                "raw_sha256": sha256(image.span(entry, end)),
                "boundary_proof": (
                    "PDATA encoded instruction count equals byte span; +8 skips only the "
                    "compiler out-of-line save-helper call"
                ),
            }
        )
    return rows


def static_words(image: Image, first: int, count: int) -> list[str]:
    return [hx(image.u32(first + index * 4)) for index in range(count)]


def parse_inner_rows(path: Path, outer_index: int) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return [
            row
            for row in csv.DictReader(stream, delimiter="\t")
            if int(row["outer_table_index"]) == outer_index
        ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    xex_data = args.apf_xex.read_bytes()
    expect(sha256(xex_data), EXPECTED_XEX_SHA256, "APF XEX SHA-256")
    image = Image(args.apf_pe)
    expect(sha256(image.data), EXPECTED_PE_SHA256, "APF reconstructed PE SHA-256")

    closure = json.loads(args.base_closure.read_text())
    menu = json.loads(args.base_menu.read_text())
    outer = json.loads(args.outer_manifest.read_text())
    trace = args.trace.read_text()
    pseudo = args.pseudo.read_text()
    expect(closure["schema"], "vc_menu_state_trace_closure/v2", "base closure schema")
    expect(menu["schema"], "vc_menu_state_trace/v1", "base menu schema")
    expect(outer["entries"][1493]["name_id"], "0xf69d21e4", "frontend outer name ID")

    required_trace = [
        "APF 2K8 cold-boot/frontend-backdrop read-only v5 trace",
        "true_entry=0x84BE9D08 body_entry=0x84BE9D10 end_exclusive=0x84BE9EC8",
        "true_entry=0x84691650 body_entry=0x84691658 end_exclusive=0x84691C68",
        "true_entry=0x846F9360 body_entry=0x846F9368 end_exclusive=0x846F9480",
        "UTF16 0x8451F2F0=TitlePage_Menu",
        "UTF16 0x8460D430=StartupMenu",
        "UTF16 0x8450232C=frontend_sync.iff",
        "0x8450232C section=.string_ function_at=none owner=none refs=",
    ]
    for marker in required_trace:
        if marker not in trace:
            raise ValueError(f"missing Ghidra trace marker: {marker}")
    required_pseudo = [
        "APF_XexEntry_Body",
        "APF_MainLoopIteration_Body",
        "APF_FrontendBootstrap_Body",
        "APF_TitlePageUpdate_Body",
        "APF_StateRuntimeRegister_Body",
        "APF_StartupMenuCallback_Body",
        "func_0x846f9360(0x1f1a625a,0xffffffff82015330)",
        "Function_846F8A60(param_1,0xffffffff820f4940)",
        "Function_846F8F00(uStack00000014,0xffffffff820f6d38)",
    ]
    for marker in required_pseudo:
        if marker not in pseudo:
            raise ValueError(f"missing Ghidra pseudo-C marker: {marker}")
    if "// PORTME:" in pseudo:
        raise ValueError("focused Ghidra pseudo-C unexpectedly contains a decompile PORTME")

    # Entry-to-main-loop edges.
    for site, target in [
        (0x84BE9D0C, 0x84BD6DE8),
        (0x84BE9E9C, 0x84B8B1D0),
        (0x84B8B1DC, 0x84B8AF98),
        (0x84B8B1E0, 0x84691C68),
        (0x84691CC0, 0x84691650),
        (0x84691CD0, 0x846913E0),
    ]:
        expect(image.branch(site), (target, True), f"boot branch at {hx(site)}")

    # Exact first state construction.
    expected_boot_words = {
        0x84691B64: 0x3D608201,
        0x84691B68: 0x3C601F1A,
        0x84691B6C: 0x388B5330,
        0x84691B70: 0x6063625A,
        0x84691B78: 0x907C000C,
        0x84691B7C: 0x48066BFD,
        0x84691B80: 0x38800001,
        0x84691B84: 0x907C0010,
        0x84691B88: 0x48066E31,
    }
    for site, word in expected_boot_words.items():
        expect(image.u32(site), word, f"frontend bootstrap word at {hx(site)}")
    expect(image.branch(0x84691B74), (0x846F9360, True), "state register call")
    expect(image.branch(0x84691B7C), (0x846F8778, True), "state runtime lookup")
    expect(image.branch(0x84691B88), (0x846F89B8, True), "state runtime enable")

    # Registration stores descriptor/id and dispatches lifecycle events 1 and 3.
    register_words = {
        0x846F9378: 0x7C651B78,
        0x846F937C: 0x7C9D2378,
        0x846F9434: 0x4BFFF345,
        0x846F9440: 0x93BF0008,
        0x846F9444: 0x90BF0004,
        0x846F9450: 0x38A00001,
        0x846F9454: 0x38800000,
        0x846F9464: 0x38A00003,
        0x846F9468: 0x38800000,
    }
    for site, word in register_words.items():
        expect(image.u32(site), word, f"state register word at {hx(site)}")
    expect(image.branch(0x846F9434), (0x846F8778, True), "register lookup call")
    expect(image.branch(0x846F9458), (0x846F9090, True), "register event 1 dispatch")
    expect(image.branch(0x846F9470), (0x846F9090, True), "register event 3 dispatch")

    title_descriptor = static_words(image, 0x82015330, 18)
    expect(title_descriptor[:4], [hx(0), hx(0x8451F2F0), hx(0x82015304), hx(0x846F2590)], "Title descriptor head")
    expect(image.utf16(0x8451F2F0), "TitlePage_Menu", "Title descriptor name")
    title_table = static_words(image, 0x82015304, 10)
    expect(
        title_table,
        [hx(3), hx(0x82015298), hx(6), hx(0x820152BC), hx(7), hx(0x820152D4), hx(11), hx(0x820152EC), hx(0), hx(0)],
        "Title action table",
    )
    expect(image.u32(0x820152D4), 3, "Title display record type")
    expect(image.u32(0x820152D8), 0x846E0468, "Title display callback")
    expect(image.u32(0x820152EC), 1, "Title action record type")
    expect(image.u32(0x820152F0), 0x846E0528, "Title action callback")
    expect(image.utf16(0x8451F2D8), "Press START", "Title prompt string")
    expect(image.utf16(0x8451F1FC), "Ambient: Title Start", "Title start ambience")

    # Static TitlePage action route to StartupMenu.
    expect(image.u32(0x846E056C), 0x3D60820F, "Startup route lis")
    expect(image.u32(0x846E0574), 0x388B4940, "Startup descriptor construction")
    expect(image.branch(0x846E0578), (0x846F8A60, True), "Startup route call")
    startup_descriptor = static_words(image, 0x820F4940, 18)
    expect(startup_descriptor[:4], [hx(0), hx(0x8460D430), hx(0x820F4910), hx(0x846F2590)], "Startup descriptor head")
    expect(image.utf16(0x8460D430), "StartupMenu", "Startup descriptor name")
    startup_table = static_words(image, 0x820F4910, 10)
    expect(
        startup_table,
        [hx(1), hx(0x820F4898), hx(2), hx(0x820F48B0), hx(6), hx(0x820F48C8), hx(9), hx(0x820F48E0), hx(10), hx(0x820F48F8)],
        "Startup action table",
    )
    expect(image.u32(0x820F48CC), 0x84A59E68, "Startup callback binding")

    # The recovered StartupMenu callback's fallthrough goes to Team Select, not Main.
    expect(image.u32(0x84A5A49C), 0x3D60820F, "Team Select route lis")
    expect(image.u32(0x84A5A4A0), 0x388B6D38, "Team Select descriptor construction")
    expect(image.branch(0x84A5A4A8), (0x846F9018, True), "Team Select replace thunk")
    expect(image.utf16(0x84612064), "Team Select", "Team Select title")
    expect(image.utf16(0x8461207C), "TeamSelectMenu_QuickGameMenu", "Team Select transition")

    # Existing exact main routes plus one previously omitted orphan tail wrapper.
    base_main_routes = closure["apf2k8"]["main_routes"]
    expect(len(base_main_routes["queue_or_route_sites"]), 7, "base queued Main routes")
    expect(image.u32(0x84A56950), 0x3D60820F, "orphan Main wrapper lis")
    expect(image.u32(0x84A56954), 0x388B4350, "orphan Main wrapper descriptor")
    expect(image.branch(0x84A56958), (0x846F60E8, False), "orphan Main tail route")
    boot_ranges = [(entry, end) for entry, _body, end, _metadata, _role in BOUNDARIES[:5]]
    main_descriptor_sequence_hits: list[str] = []
    for first, end in boot_ranges:
        for address in range(first, end - 8, 4):
            if image.u32(address) == 0x3D60820F and image.u32(address + 4) in (0x388B4350, 0x38AB4350):
                main_descriptor_sequence_hits.append(hx(address))
    expect(main_descriptor_sequence_hits, [], "Main descriptor construction in boot ranges")

    backdrop_base = closure["apf2k8"]["layout_mainmenu_backdrop"]
    visual = menu["apf2k8"]["visual_layout_entry"]
    expect(visual["name_crc32"], "0x48C6D154", "layout_mainmenu logical CRC")
    expect(zlib.crc32(b"layout_mainmenu") & 0xFFFFFFFF, 0x48C6D154, "layout_mainmenu CRC calculation")
    bundle_rows = parse_inner_rows(args.inner_candidates, 1493)
    layout_rows = [row for row in bundle_rows if row["inner_name"] == "layout_mainmenu"]
    expect(len(layout_rows), 1, "layout_mainmenu row count")
    expect(layout_rows[0]["inner_index"], "53", "layout_mainmenu inner index")
    expect(layout_rows[0]["type_name"], "LAYT", "layout_mainmenu type")
    expect(layout_rows[0]["type_hash"], "0x86a1ac9e", "layout_mainmenu type hash")

    frontend_name = "frontend_sync.iff".encode("utf-16-be")
    frontend_string_hits = image.occurrences(frontend_name)
    expect(frontend_string_hits, [0x8450232C], "frontend_sync UTF-16BE occurrence")
    layout_ascii_hits = image.occurrences(b"layout_mainmenu")
    layout_utf16_hits = image.occurrences("layout_mainmenu".encode("utf-16-be"))
    layout_crc_be_hits = image.occurrences((0x48C6D154).to_bytes(4, "big"))
    layout_crc_le_hits = image.occurrences((0x48C6D154).to_bytes(4, "little"))
    outer_id_be_hits = image.occurrences((0xF69D21E4).to_bytes(4, "big"))
    outer_id_le_hits = image.occurrences((0xF69D21E4).to_bytes(4, "little"))
    frontend_pointer_hits = image.occurrences((0x8450232C).to_bytes(4, "big"))
    expect(layout_ascii_hits, [], "layout_mainmenu ASCII occurrences")
    expect(layout_utf16_hits, [], "layout_mainmenu UTF-16 occurrences")
    expect(layout_crc_be_hits, [], "layout_mainmenu CRC BE occurrences")
    expect(layout_crc_le_hits, [], "layout_mainmenu CRC LE occurrences")
    expect(outer_id_be_hits, [], "frontend bundle ID BE occurrences")
    expect(outer_id_le_hits, [], "frontend bundle ID LE occurrences")
    expect(frontend_pointer_hits, [], "frontend string fullword pointer occurrences")
    frontend_string_constructions = image.classic_absolute_constructions(0x8450232C)
    outer_id_constructions = image.classic_absolute_constructions(0xF69D21E4)
    expect(frontend_string_constructions, [], "frontend string classic constructions")
    expect(outer_id_constructions, [], "frontend outer ID classic constructions")

    portme = [
        {
            "address": "0x82015320/0x820152EC/0x846E0528",
            "reason": "name action-table key 11 and prove the live input dispatch that invokes the statically bound TitlePage action; the callback's StartupMenu route is exact",
        },
        {
            "address": "0x84A56950",
            "reason": "recover the indirect owner/caller of the exact orphan tail wrapper to Main at 0x84A56950..0x84A5695B",
        },
        {
            "address": "0x820F4350",
            "reason": "connect TitlePage/StartupMenu or another proved boot successor to one exact Main route; no Main construction occurs in the recovered boot extents",
        },
        {
            "address": "0x8450232C/0xF69D21E4",
            "reason": "prove the executable or data-driven loader that owns frontend_sync.iff; the lone string, archive name ID, and classic absolute constructions have no edge",
        },
        {
            "address": "0x48C6D154",
            "reason": "prove which loaded frontend_sync resource lookup instantiates inner 53 layout_mainmenu for the native Main state",
        },
    ]

    report: dict[str, Any] = {
        "schema": "vc_apf_frontend_boot_backdrop/v5",
        "source": {
            "xex": str(args.apf_xex),
            "xex_size": len(xex_data),
            "xex_sha256": sha256(xex_data),
            "reconstructed_pe": args.apf_pe.name,
            "reconstructed_pe_size": len(image.data),
            "reconstructed_pe_sha256": sha256(image.data),
            "ghidra_program_md5": "217eea6084c3d03f0f1143802b1f5636",
        },
        "scope": {
            "launches_original_menu": False,
            "writes_executable": False,
            "writes_ghidra_project": False,
            "cold_boot_to_title_state_proved": True,
            "title_static_action_to_startup_menu_proved": True,
            "title_action_runtime_key_semantics_proved": False,
            "cold_boot_to_main_menu_proved": False,
            "frontend_sync_archive_identity_proved": True,
            "layout_mainmenu_archive_identity_proved": True,
            "layout_mainmenu_executable_owner_proved": False,
            "state_to_layout_mainmenu_edge_proved": False,
        },
        "recovered_boundaries": boundary_rows(image),
        "entry_to_main_loop": {
            "entry": hx(0x84BE9D08),
            "entry_body": hx(0x84BE9D10),
            "crt_main_call": {"site": hx(0x84BE9E9C), "target": hx(0x84B8B1D0)},
            "crt_main_setup_call": {"site": hx(0x84B8B1DC), "target": hx(0x84B8AF98)},
            "game_main_loop_call": {"site": hx(0x84B8B1E0), "target": hx(0x84691C68)},
            "bootstrap_call": {"site": hx(0x84691CC0), "target": hx(0x84691650)},
            "frame_loop_call": {"site": hx(0x84691CD0), "target": hx(0x846913E0)},
        },
        "cold_boot_title_state": {
            "registration": {
                "site": hx(0x84691B74),
                "callee": hx(0x846F9360),
                "state_id": hx(0x1F1A625A),
                "descriptor": hx(0x82015330),
                "result_store": hx(0x84FEF4FC),
                "runtime_lookup_site": hx(0x84691B7C),
                "runtime_store": hx(0x84FEF500),
                "runtime_enable_site": hx(0x84691B88),
            },
            "registration_contract": {
                "descriptor_store": {"site": hx(0x846F9440), "runtime_offset": "+0x08"},
                "state_id_store": {"site": hx(0x846F9444), "runtime_offset": "+0x04"},
                "event_1_dispatch": {"site": hx(0x846F9458), "callee": hx(0x846F9090)},
                "event_3_dispatch": {"site": hx(0x846F9470), "callee": hx(0x846F9090), "condition": "event 1 callback returned nonzero"},
            },
            "descriptor": {
                "address": hx(0x82015330),
                "name_address": hx(0x8451F2F0),
                "name": "TitlePage_Menu",
                "action_table": hx(0x82015304),
                "callback": hx(0x846F2590),
                "raw_words": title_descriptor,
            },
            "action_table": {
                "raw_words": title_table,
                "display_record": {"key": 7, "record": hx(0x820152D4), "record_type": 3, "callback": hx(0x846E0468), "literal": "Press START"},
                "startup_action_record": {"key": 11, "record": hx(0x820152EC), "record_type": 1, "callback": hx(0x846E0528), "literal": "Ambient: Title Start"},
                "runtime_key_11_name": None,
            },
        },
        "title_to_startup_menu": {
            "static_binding": "0x82015320 -> 0x820152EC -> callback 0x846E0528",
            "route": {"descriptor_site": hx(0x846E0574), "call_site": hx(0x846E0578), "callee": hx(0x846F8A60), "descriptor": hx(0x820F4940)},
            "descriptor": {
                "address": hx(0x820F4940),
                "name_address": hx(0x8460D430),
                "name": "StartupMenu",
                "action_table": hx(0x820F4910),
                "callback": hx(0x846F2590),
                "raw_words": startup_descriptor,
            },
            "action_table_raw_words": startup_table,
            "runtime_invocation_of_key_11_proved": False,
        },
        "startup_menu_fallthrough": {
            "callback": hx(0x84A59E68),
            "route_site": hx(0x84A5A4A8),
            "replace_thunk": hx(0x846F9018),
            "replace_target": hx(0x846F8F00),
            "descriptor": hx(0x820F6D38),
            "descriptor_title": "Team Select",
            "transition": "TeamSelectMenu_QuickGameMenu",
            "note": "this recovered fallthrough is not a route to Main Menu",
        },
        "main_menu_boundary": {
            "descriptor": hx(0x820F4350),
            "name": "Main Menu",
            "existing_queued_call_routes": base_main_routes["queue_or_route_sites"],
            "existing_direct_transition": base_main_routes["direct_transition_site"],
            "new_orphan_tail_wrapper": {
                "range": "0x84A56950..0x84A5695B",
                "descriptor_site": hx(0x84A56954),
                "tail_site": hx(0x84A56958),
                "callee": hx(0x846F60E8),
                "owner": None,
            },
            "main_descriptor_constructions_in_recovered_boot_extents": main_descriptor_sequence_hits,
            "cold_boot_predecessor_proved": False,
        },
        "layout_mainmenu_backdrop": {
            "archive": "frontend_sync.iff",
            "outer_index": 1493,
            "outer_name_id": hx(0xF69D21E4),
            "bundle_entry_count": len(bundle_rows),
            "bundle_layout_count": sum(row["type_name"] == "LAYT" for row in bundle_rows),
            "inner_index": 53,
            "layout_name": "layout_mainmenu",
            "logical_crc32": hx(0x48C6D154),
            "type_hash": hx(0x86A1AC9E),
            "parts": layout_rows[0]["parts"],
            "records": visual["records"],
            "rejected_split_immediate_collision": backdrop_base["rejected_split_immediate_collision"],
            "executable_negative": {
                "layout_name_ascii_occurrences": [hx(value) for value in layout_ascii_hits],
                "layout_name_utf16be_occurrences": [hx(value) for value in layout_utf16_hits],
                "logical_crc32_big_endian_occurrences": [hx(value) for value in layout_crc_be_hits],
                "logical_crc32_little_endian_occurrences": [hx(value) for value in layout_crc_le_hits],
                "frontend_sync_utf16be_occurrences": [hx(value) for value in frontend_string_hits],
                "frontend_sync_string_address": hx(0x8450232C),
                "frontend_sync_string_ghidra_references": [],
                "frontend_sync_string_fullword_pointer_occurrences": [hx(value) for value in frontend_pointer_hits],
                "frontend_sync_string_classic_absolute_constructions": frontend_string_constructions,
                "outer_name_id_big_endian_occurrences": [hx(value) for value in outer_id_be_hits],
                "outer_name_id_little_endian_occurrences": [hx(value) for value in outer_id_le_hits],
                "outer_name_id_classic_absolute_constructions": outer_id_constructions,
            },
            "owner_status": "blocked: bundle identity is exact, but no executable owner or state-to-inner-53 instantiation edge is proved",
        },
        "ghidra": {
            "trace": args.trace.name,
            "trace_sha256": sha256(args.trace.read_bytes()),
            "pseudo_c": args.pseudo.name,
            "pseudo_c_sha256": sha256(args.pseudo.read_bytes()),
            "transient_rebuild_count": len(BOUNDARIES),
            "focused_decompile_portme_count": pseudo.count("// PORTME:"),
            "read_only": True,
        },
        "portme": portme,
    }
    return report


def tsv_rows(report: dict[str, Any]):
    for row in report["recovered_boundaries"]:
        yield ["boundary", "proved", row["address"], row["end_exclusive"], row["role"]]
    for item in [
        ("entry", "proved", "0x84BE9D08", "0x84B8B1D0", "XEX entry reaches CRT main"),
        ("main_loop", "proved", "0x84B8B1E0", "0x84691C68", "CRT main enters game main loop"),
        ("bootstrap", "proved", "0x84691CC0", "0x84691650", "main loop calls frontend bootstrap"),
        ("initial_state", "proved", "0x84691B74", "0x82015330", "registers TitlePage_Menu as first frontend descriptor"),
        ("title_action", "proved_static", "0x82015320", "0x846E0528", "key 11 statically binds StartupMenu route callback"),
        ("startup_route", "proved", "0x846E0578", "0x820F4940", "queues StartupMenu via 0x846F8A60"),
        ("main_predecessor", "blocked", "0x820F4350", "", "no Main construction in recovered boot extents"),
        ("main_wrapper", "proved_unowned", "0x84A56950", "0x846F60E8", "orphan tail wrapper queues Main"),
        ("backdrop_archive", "proved", "0xF69D21E4", "0x48C6D154", "frontend_sync inner 53 is layout_mainmenu"),
        ("backdrop_owner", "blocked", "0x8450232C", "0x48C6D154", "no executable bundle owner or state instantiation edge"),
    ]:
        yield list(item)


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["category", "status", "address", "target", "evidence"])
        writer.writerows(tsv_rows(report))


def write_portme(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "#include <stdint.h>",
        "",
        "void vc_apf_frontend_boot_backdrop_v5_portme(void)",
        "{",
    ]
    for item in report["portme"]:
        lines.append(f"    // PORTME: APF function/data at {item['address']}: {item['reason']}.")
    lines.extend(["    (void)(uint32_t)0;", "}", ""])
    path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--base-closure", type=Path, required=True)
    parser.add_argument("--base-menu", type=Path, required=True)
    parser.add_argument("--outer-manifest", type=Path, required=True)
    parser.add_argument("--inner-candidates", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    parser.add_argument("--portme-c-out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_tsv(args.tsv_out, report)
    write_portme(args.portme_c_out, report)
    print(
        "APF_FRONTEND_BOOT_BACKDROP_V5_REPORT_COMPLETE "
        f"boundaries={len(report['recovered_boundaries'])} "
        f"portme={len(report['portme'])}"
    )


if __name__ == "__main__":
    main()
