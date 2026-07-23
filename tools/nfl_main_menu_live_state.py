#!/usr/bin/env python3
"""Prove NFL 2K5 main-menu mode, initial selection, and draw ownership."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
EXPECTED_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
EXPECTED_HEADER_SHA256 = "0f480ad383cd4e6df647b4e50ee8a609365f3cd57e729f090048d0fc37958dad"

EXPECTED_RANGES = (
    ("state_replace_push_lifecycle", 0x0006E2E0, 0x0006E3F3,
     "975215249a854b7869f417b89ab4fbb0de1be3f40e065cbca3fffde3c86d4d9c"),
    ("state_event_dispatch", 0x0006E4E0, 0x0006E630,
     "3e109f7f4227757237edf45f505e63087b702cdd94ae43d98272d9f04c796208"),
    ("active_state_slot", 0x0006E630, 0x0006E63A,
     "34b5e087e0c7ba055fdeab5cce780e2292630a7101d917a91fda27311da0ea2a"),
    ("background_category_dispatch", 0x0006BEF0, 0x0006C09C,
     "4e1a6819bab578d9cfa96e3a5021283c112ff799e096076cf155ec2e677de9dd"),
    ("main_construct_mode", 0x000F3CD0, 0x000F3D57,
     "c6a26b2780164a3e75395d59ef13abaa13f1fc42a43b290ac27712748f7a2ec0"),
    ("main_default_event", 0x000F3E90, 0x000F3F78,
     "684b95ce9042a29a196ca37cdd457db0e32137026ee268989625480b211fb926"),
    ("initial_selection_wrapper", 0x0014FF70, 0x0014FF77,
     "94a94bf9d51dc06cfe964cba83834c1e8aaa721fae754ce0a9914488d0860c67"),
    ("row_rank_helpers", 0x0014FB10, 0x0014FB66,
     "77395029fd3f2a4995de0071368070358997256ceb0c3b1367b71c03b6ed649b"),
    ("selection_and_mode_writers", 0x0014FC50, 0x0014FCE0,
     "61bde167b32a0373cd769eb40039e3f801f78eea81d1c8b10d9630c8a23d0e6e"),
    ("direct_row_draw", 0x0014FDA0, 0x0014FF6A,
     "583c95f7688d987409f3f317cf81d6b2bdeb2d569ca8c01cf693f3e77cb77291"),
    ("row_materialize", 0x0014FF80, 0x00150020,
     "b9caaad84cde3c36bcce67af26a1a2e943756591e160f25abb916021a9f36a2e"),
    ("selection_input", 0x00150020, 0x0015023B,
     "2ffc619d8a4f45a941b94242dc727060220598eb15e64bd291e83fce2eaf570a"),
    ("mode_draw_gate", 0x00150260, 0x00150286,
     "411f26d64cdac7b2d23184f5ffd7dac7f7857af8986e3e00231508f7062e8355"),
    ("mode_zero_draw_stub", 0x002C8950, 0x002C8951,
     "ae3f4619b0413d70d3004b9131c3752153074e45725be13b9a148978895e359e"),
    ("mode_zero_selection_hook", 0x002C8960, 0x002C8961,
     "ae3f4619b0413d70d3004b9131c3752153074e45725be13b9a148978895e359e"),
    ("layout_draw_wrapper", 0x000F2F70, 0x000F2F8C,
     "6a71ca78fc79a6a23e008f8fb5c6613ff7e5d6e328e12d29df1c756db6591f2c"),
    ("layout_traverse_entry", 0x00143DE0, 0x00143DF0,
     "08caf325d466c484857077f3de39bd9d25183e32017a0018656462e7a446eefd"),
    ("layout_traverse", 0x00143A00, 0x00143AD3,
     "6ee6b3e3a011f3e96cff1d754b733c931466ba237d308da4b4b6c9ebd3ccafec"),
    ("text_context_init", 0x00046920, 0x000469B0,
     "eb1885e56619b0b7e653fa72af949e5ada2e8452bf19b1867dcc8591b267e7d7"),
    ("text_position_setter", 0x00046A70, 0x00046AB2,
     "40544648154b731a6b49f197c0a78da6d3f058d0011ed0ce5909c4118bd08dc2"),
    ("glyph_quad_add", 0x00046310, 0x0004641B,
     "97ed82850b22c8a67eb1344690fdd3bdde8b6875532aa96f464c44dd990d9933"),
    ("glyph_emit", 0x00046420, 0x0004656E,
     "08006e33d3ec7cc1c5b6f3dcbad6e0729fb68661eb08ea7922892ff5b59b0525"),
    ("vertex_command_emit", 0x0002CA70, 0x0002CB46,
     "316868d74fd90bdb7251b8080e30fd27f7a1500f2321a8dc20de8b5b91ccb330"),
    ("navigation_rows", 0x005154C0, 0x0051562C,
     "bf51c8ac0a800a670dd7c36899e1b49128e6a7a0d8141a0a6275dade4ded4dc7"),
    ("main_descriptor_plus_render_class", 0x00515660, 0x0051568C,
     "da3e32d94f29a863b2d90e0afcaac484c8df127f1a01da6b82d6867fe8b4ba1d"),
)

EXPECTED_MODES = (
    (0.0, 0.0, 10, 38.0),
    (0.0, 0.0, 10, 38.0),
    (144.0, 86.0, 11, 30.0),
)

PORTME = (
    "// PORTME(0x00515660): capture the retail cold-boot predecessor, descriptor install, and event-4 conditional-pop outcome before claiming original boot.",
    "// PORTME(0x0006BF02): trace the category-2 background branch with loaded retail resources and identify its first successful GPU primitive.",
    "// PORTME(0x001500DE): record the current raw selection after runtime callbacks and arbitrary controller frames; static analysis proves only the initialized value and transition rules.",
    "// PORTME(0x00150281): identify the mode-0 selected-row/highlight owner inside LAYT actions or timelines; the direct font-row path is skipped in this mode.",
    "// PORTME(0x0014372C): capture main_menu_sub/main_navi load, visibility, and traversal state to name the first successful menu-specific primitive.",
    "// PORTME(0x0002CA7D): recover the Xbox GPU shader, viewport, and display scaling before mapping CPU title-space coordinates to physical framebuffer pixels.",
    "// PORTME(0x000F3E90): could not decompile this serialized main callback as one function because the saved Ghidra project has no function boundary; exact instructions are retained.",
    "// PORTME(0x00192090): could not decompile this event-6 chained callback because the saved Ghidra project has no function boundary; exact instructions are retained.",
    "// PORTME(0x00327A90): could not decompile this event-6 action callback because the saved Ghidra project has no function boundary; exact instructions are retained.",
)


class LiveStateError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": file_sha256(path)}


class XbeView:
    def __init__(self, path: Path, header_path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        if hashlib.md5(self.data).hexdigest() != EXPECTED_XBE_MD5:
            raise LiveStateError("unexpected NFL 2K5 XBE MD5")
        if sha256(self.data) != EXPECTED_XBE_SHA256:
            raise LiveStateError("unexpected NFL 2K5 XBE SHA-256")

    def file_offset(self, va: int, size: int) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise LiveStateError(f"VA 0x{va:08x}+0x{size:x} is not file-backed")

    def at(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        result = self.data[offset:offset + size]
        if len(result) != size:
            raise LiveStateError(f"short read at VA 0x{va:08x}")
        return result


def require_phrases(text: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        if phrase not in text:
            raise LiveStateError(f"{label}: missing exact evidence {phrase!r}")


def load_json(path: Path, schema: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != schema:
        raise LiveStateError(f"{path}: expected schema {schema}")
    return value


def selection_table(labels: list[str]) -> list[dict[str, object]]:
    rows = []
    count = len(labels)
    for index, label in enumerate(labels):
        previous = (index - 1) % count
        following = (index + 1) % count
        rows.append({
            "raw_index": index,
            "label": label,
            "initial_selected": index == 0,
            "initial_drawable": True,
            "previous_raw_if_initial_set": previous,
            "previous_label_if_initial_set": labels[previous],
            "next_raw_if_initial_set": following,
            "next_label_if_initial_set": labels[following],
        })
    return rows


def build(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    if file_sha256(args.xbe_header) != EXPECTED_HEADER_SHA256:
        raise LiveStateError("unexpected XBE header report SHA-256")
    menu_state = load_json(args.menu_state_report, "vc_menu_state_trace/v1")
    row_layout = load_json(args.row_layout_report,
                           "nfl2k5_main_menu_row_layout/v1")
    font = load_json(args.font_report, "nfl2k5_main_menu_font/v1")

    nfl = menu_state.get("nfl2k5", {})
    navigation = nfl.get("navigation_rows", [])
    if len(navigation) != 7:
        raise LiveStateError("menu-state report does not contain seven NFL rows")
    labels = [row.get("label") for row in navigation]
    if labels != ["Quick Game", "Game Modes", "The Crib|TM|", "Features",
                  "Options", "Xbox Live", "Extras"]:
        raise LiveStateError("unexpected main-menu label order")
    if nfl.get("state_descriptor", {}).get("loaded_layout_name") != "main_menu_sub":
        raise LiveStateError("menu-state report does not prove main_menu_sub")
    child_layout = nfl.get("navigation_child_entry", {})
    if (child_layout.get("layout_name"), child_layout.get("record_count")) != (
            "main_navi", 7):
        raise LiveStateError("menu-state report does not prove main_navi records")

    modes = row_layout.get("modes", [])
    actual_modes = tuple((mode.get("base_x"), mode.get("base_y"),
                          mode.get("wrap_rows"), mode.get("row_step"))
                         for mode in modes)
    if actual_modes != EXPECTED_MODES:
        raise LiveStateError("row-layout report mode table differs")
    font_result = font.get("result", {})
    if (font_result.get("main_menu_font_slot"),
            font_result.get("main_menu_font_name")) != (6, "font7"):
        raise LiveStateError("font report does not prove slot 6 -> font7")

    xbe = XbeView(args.xbe, args.xbe_header)
    trace = args.trace.read_text(encoding="utf-8")
    pseudo = args.pseudo.read_text(encoding="utf-8")
    require_phrases(trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "0x0006E306 89 3C C6 MOV dword ptr [ESI + EAX*0x8],EDI",
        "0x0006E31F E8 BC 01 00 00 CALL 0x0006e4e0",
        "0x0006E328 6A 03 PUSH 0x3",
        "0x0006E3D2 E8 09 01 00 00 CALL 0x0006e4e0",
        "0x0006E3DB 6A 03 PUSH 0x3",
        "0x000F3EBE E8 AD C0 05 00 CALL 0x0014ff70",
        "0x0014FF70 33 D2 XOR EDX,EDX",
        "0x0014FF72 E9 D9 FC FF FF JMP 0x0014fc50",
        "0x0014FC58 89 70 04 MOV dword ptr [EAX + 0x4],ESI",
        "0x000F3ECB E8 00 FE FF FF CALL 0x000f3cd0",
        "0x000F3ED2 E8 A9 C0 05 00 CALL 0x0014ff80",
        "0x000F3CD9 33 D2 XOR EDX,EDX",
        "0x000F3CDF E8 EC BF 05 00 CALL 0x0014fcd0",
        "0x0014FCD8 89 B0 7C 0A 00 00 MOV dword ptr [EAX + 0xa7c],ESI",
        "0x002ACBCD 33 D2 XOR EDX,EDX",
        "0x002ACBD0 E9 FB 30 EA FF JMP 0x0014fcd0",
        "0x0014FFD8 33 C0 XOR EAX,EAX",
        "0x0014FFDA F3 AB STOSD.REP ES:EDI",
        "0x001500AA F7 44 24 18 00 00 00 01 TEST dword ptr [ESP + 0x18],0x1000000",
        "0x001500DE 89 45 04 MOV dword ptr [EBP + 0x4],EAX",
        "0x0015010A F7 44 24 18 00 00 00 02 TEST dword ptr [ESP + 0x18],0x2000000",
        "0x00150140 89 45 04 MOV dword ptr [EBP + 0x4],EAX",
        "0x00150268 8B 80 7C 0A 00 00 MOV EAX,dword ptr [EAX + 0xa7c]",
        "0x00150271 74 0B JZ 0x0015027e",
        "0x00150274 74 08 JZ 0x0015027e",
        "0x00150277 E8 24 FB FF FF CALL 0x0014fda0",
        "0x00150281 E9 CA 86 17 00 JMP 0x002c8950",
        "0x002C8950 C3 RET",
        "0x002C8960 C3 RET",
        "0x000F3F12 E8 F9 E8 FF FF CALL 0x000f2810",
        "0x000F3F19 E8 52 F0 FF FF CALL 0x000f2f70",
        "0x000F3F20 E8 3B C3 05 00 CALL 0x00150260",
        "0x0006C08D 8B 52 28 MOV EDX,dword ptr [EDX + 0x28]",
        "0x0006BFD3 FF 24 95 5C C0 06 00 JMP dword ptr [EDX*0x4 + 0x6c05c]",
        "0x0006BFDD E9 0E FF FF FF JMP 0x0006bef0",
        "0x000F2F78 8B 88 A0 05 00 00 MOV ECX,dword ptr [EAX + 0x5a0]",
        "0x000F2F85 E9 56 0E 05 00 JMP 0x00143de0",
        "0x00143DE3 68 50 F2 4F 00 PUSH 0x4ff250",
        "0x00143DEA E8 11 FC FF FF CALL 0x00143a00",
        "0x00143AAF E8 6C FC FF FF CALL 0x00143720",
        "0x00046994 89 50 64 MOV dword ptr [EAX + 0x64],EDX",
        "0x0004699B 66 C7 40 6E 80 02 MOV word ptr [EAX + 0x6e],0x280",
        "0x000469A5 66 C7 40 72 E0 01 MOV word ptr [EAX + 0x72],0x1e0",
        "0x00046A7F 89 46 10 MOV dword ptr [ESI + 0x10],EAX",
        "0x00046A82 89 4E 14 MOV dword ptr [ESI + 0x14],ECX",
        "0x00046A85 89 56 18 MOV dword ptr [ESI + 0x18],EDX",
        "0x00046359 E8 12 67 FE FF CALL 0x0002ca70",
        "0x0002CA7D 89 10 MOV dword ptr [EAX],EDX",
        "0x0002CA82 89 50 04 MOV dword ptr [EAX + 0x4],EDX",
        "0x0002CA88 89 48 08 MOV dword ptr [EAX + 0x8],ECX",
    ), "Ghidra trace")
    require_phrases(pseudo, (
        "/* 0x0006E2E0:FUN_0006e2e0",
        "iVar1 = FUN_0006e4e0(1);",
        "FUN_0006e4e0(3);",
        "return *(undefined4 *)(param_1 + 0x10c);",
        "*(undefined4 *)(iVar1 + 0xa7c) = param_2;",
        "*(undefined4 *)(iVar1 + 4) = param_2;",
        "FUN_00143a00(&DAT_004ff250,0,param_2);",
        "param_1[0x19] = 0;",
        "param_1[4] = param_2;",
        "FUN_0002ca70(*(float *)(unaff_ESI + 0x10) + *unaff_EDI,",
        "// PORTME: could not decompile function at 0x000F3E90;",
    ), "Ghidra pseudo-C")

    ranges = []
    for name, start, end, expected in EXPECTED_RANGES:
        body = xbe.at(start, end - start)
        actual = sha256(body)
        if actual != expected:
            raise LiveStateError(f"{name}: expected {expected}, got {actual}")
        ranges.append({
            "name": name,
            "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}",
            "size": end - start,
            "file_offset": xbe.file_offset(start, end - start),
            "sha256": actual,
        })

    descriptor = xbe.at(0x00515660, 0x2C)
    render_class, = struct.unpack_from("<I", descriptor, 0x28)
    if render_class != 2:
        raise LiveStateError("main descriptor +0x28 is not category 2")
    jump_targets = struct.unpack("<8I", xbe.at(0x0006C05C, 0x20))
    if jump_targets[2] != 0x0006BFDA:
        raise LiveStateError("background category 2 jump target differs")
    base_transform = struct.unpack("<4f", xbe.at(0x004FF250, 16))
    if base_transform != (0.0, 0.0, 0.0, 0.0):
        raise LiveStateError("LAYT base transform differs")

    row_bytes = xbe.at(0x005154C0, 7 * 0x34)
    row_types: list[int] = []
    source_callbacks: list[int] = []
    for index, upstream in enumerate(navigation):
        offset = index * 0x34
        row_type, label_pointer = struct.unpack_from("<II", row_bytes, offset)
        callback, = struct.unpack_from("<I", row_bytes, offset + 0x2C)
        expected_pointer = int(str(upstream["label_pointer"]), 16)
        if label_pointer != expected_pointer:
            raise LiveStateError(f"row {index}: label pointer differs")
        row_types.append(row_type)
        source_callbacks.append(callback)
    if row_types != [0, 0, 9, 0, 0, 0, 0]:
        raise LiveStateError(f"unexpected source row types {row_types!r}")
    if source_callbacks != [0] * 7:
        raise LiveStateError("a source +0x2C constructor callback is nonzero")
    sentinel_type, = struct.unpack("<I", xbe.at(0x0051562C, 4))
    if sentinel_type != 3:
        raise LiveStateError("navigation source list lacks type-3 sentinel")

    raw_modes = tuple(struct.unpack_from("<ffif", xbe.at(0x00509A30, 48),
                                         index * 16)
                      for index in range(3))
    if raw_modes != EXPECTED_MODES:
        raise LiveStateError("raw row mode table differs")

    transitions = selection_table(labels)
    report: dict[str, object] = {
        "schema": "nfl2k5_main_menu_live_state/v1",
        "result": {
            "construction_mode": 0,
            "initial_selected_raw_row": 0,
            "initial_selected_label": "Quick Game",
            "initial_selectable_rows": 7,
            "default_direct_font_row_draw": False,
            "default_background_render_category": 2,
            "default_layout_draw_call_if_loaded": True,
            "cpu_logical_canvas": [640, 480],
            "cpu_direct_text_vertex_coordinates_proved": True,
            "physical_framebuffer_mapping_proved": False,
            "first_successful_gpu_primitive_proved": False,
            "original_boot_proved": False,
        },
        "executable": {
            "path": str(args.xbe),
            "md5": EXPECTED_XBE_MD5,
            "sha256": EXPECTED_XBE_SHA256,
            "ranges": ranges,
        },
        "mode_ownership": {
            "manager_child": "0x0006e2d0 returns manager+0x10C",
            "field": "manager child +0xA7C",
            "writer": "0x0014fcd0 stores its EDX argument at +0xA7C",
            "known_direct_callers": [
                {"site": "0x000f3cdf", "value": 0,
                 "reason": "0x000f3cd9 XOR EDX,EDX"},
                {"site": "0x002acbd0", "value": 0,
                 "reason": "0x002acbcd XOR EDX,EDX before tail jump"},
            ],
            "menu_cluster_writer_count": 1,
            "global_offset_scan_scope": "other +0xA7C accesses around 0x00492xxx belong to unrelated objects; uniqueness is asserted only for the menu ownership cluster",
        },
        "initialization_and_selection": {
            "lifecycle": "replace 0x0006e2e0 and push 0x0006e390 install the descriptor, dispatch event 1, then dispatch event 3 when event 1 returns true",
            "event_1": "main callback 0x000f3e90 calls 0x0014ff70; XOR EDX,EDX then 0x0014fc50 stores raw selection 0 at active slot +4",
            "event_3": "main callback calls 0x000f3cd0 (mode 0), 0x0014ff80 (materialize rows), then 0x000f3d60",
            "event_3_tail": "0x000f3d60 dispatches event 4; action 0x00327a50 can pop the state via 0x0006e400 when 0x00192020 returns zero, so survival to event 7 is runtime-dependent even though this action does not rewrite the selected-row slot",
            "active_slot": "0x0006e630 returns manager + manager[+0x100]*8; slot +0 is descriptor and slot +4 is selected raw row",
            "initial_runtime_records": "0x0014ffda zeroes each 0x2C-byte runtime record before source pointers are attached; all seven runtime +0x18 suppression fields begin zero",
            "initial_source_callbacks_plus_0x2c": source_callbacks,
            "rank_helpers": "0x0014fb10 maps raw row to drawable rank; 0x0014fb40 maps drawable rank back to raw row by testing runtime +0x18",
            "input_masks": {"previous": "0x01000000", "next": "0x02000000"},
            "dynamic_limit": "the initialized current row is 0; callbacks and controller frames can change the current row later",
            "initial_transitions": transitions,
        },
        "draw_order": {
            "event_7_calls": ["0x000f2810", "0x000f2f70", "0x00150260"],
            "background_stage": {
                "descriptor_field": "+0x28 low signed nibble",
                "serialized_value": render_class,
                "dispatch": "0x0006c080 -> 0x0006bfd0 table index 2 -> 0x0006bfda -> 0x0006bef0",
                "status": "earliest statically selected render stage; successful resource/GPU output is runtime-dependent",
            },
            "menu_layout_stage": {
                "resource": "main_menu_sub",
                "runtime_slot": "manager child +0x5A0",
                "call_chain_if_loaded": ["0x000f2f70", "0x00143de0",
                                         "0x00143a00", "0x00143720"],
                "base_transform_xyzw": list(base_transform),
                "child_resource": "main_navi",
                "traversal": "type 0 calls 0x00143720, type 1 calls its callback, other records recurse when child +0x28 is nonzero",
            },
            "direct_row_stage": {
                "gate": "0x00150260",
                "mode_0_and_1_target": "0x002c8950 (RET)",
                "other_modes_target": "0x0014fda0 (font row renderer)",
                "default_mode_executes_font_renderer": False,
            },
            "first_successful_primitive": "not statically provable because background branches, resource load success, LAYT runtime +0x38 visibility, and GPU command consumption are dynamic",
        },
        "coordinate_chain": {
            "scope": "the direct 0x0014fda0 font path used only when mode is neither 0 nor 1",
            "logical_canvas": {"width": 640, "height": 480,
                               "context_fields": ["+0x6E", "+0x72"]},
            "origin": "0x00046a70 copies X/Y/Z to context +0x10/+0x14/+0x18 and W=0; +0x68 stays 0 here so its mode-2 Y adjustment is skipped",
            "glyph_vertices": "0x00046310 adds each glyph-local XYZW to the context origin and calls 0x0002ca70 four times",
            "command_copy": "0x0002ca70 copies the first three 32-bit coordinate words unchanged to the Xbox command buffer",
            "cpu_projection_after_origin": False,
            "gpu_projection_or_viewport_recovered": False,
            "physical_pixel_claim": False,
            "default_mode_uses_this_chain": False,
        },
        "decompiler_boundaries": {
            "exact_instruction_ranges_retained": True,
            "missing_saved_boundaries": ["0x000f3e90", "0x00192090",
                                         "0x00327a90"],
            "policy": "pseudo-C emits an address-specific PORTME instead of inventing a saved function boundary",
        },
        "upstream_joins": {
            "menu_state": {"path": str(args.menu_state_report),
                           "schema": menu_state["schema"],
                           "loaded_layout": "main_menu_sub",
                           "navigation_layout": "main_navi",
                           "labels": labels},
            "row_layout": {"path": str(args.row_layout_report),
                           "schema": row_layout["schema"],
                           "resolved_live_mode": 0,
                           "previous_report_left_live_mode_open": True,
                           "mode_0": {"base_x": 0.0, "base_y": 0.0,
                                      "wrap_rows": 10, "row_step": 38.0}},
            "font": {"path": str(args.font_report), "schema": font["schema"],
                     "slot": 6, "name": "font7",
                     "default_mode_reaches_font": False},
        },
        "source_pins": {
            "xbe": pin(args.xbe),
            "xbe_header": pin(args.xbe_header),
            "ghidra_trace": pin(args.trace),
            "ghidra_pseudo_c": pin(args.pseudo),
            "ghidra_script": pin(args.ghidra_script),
            "generator": pin(Path("tools/nfl_main_menu_live_state.py")),
            "menu_state_report": pin(args.menu_state_report),
            "row_layout_report": pin(args.row_layout_report),
            "font_report": pin(args.font_report),
        },
        "portme": list(PORTME),
    }
    return report, transitions


def portme_source() -> str:
    lines = [
        "/* Generated unresolved NFL 2K5 main-menu live-state work. */",
        "void vc_nfl2k5_main_menu_live_state_portme(void)",
        "{",
    ]
    lines.extend(f"    {entry}" for entry in PORTME)
    lines.extend(("}", ""))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--ghidra-script", type=Path, required=True)
    parser.add_argument("--menu-state-report", type=Path, required=True)
    parser.add_argument("--row-layout-report", type=Path, required=True)
    parser.add_argument("--font-report", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    parser.add_argument("--portme", type=Path, required=True)
    args = parser.parse_args()
    try:
        report, transitions = build(args)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(transitions[0]),
                                    dialect="excel-tab", lineterminator="\n")
            writer.writeheader()
            writer.writerows(transitions)
        args.portme.parent.mkdir(parents=True, exist_ok=True)
        args.portme.write_text(portme_source(), encoding="utf-8")
    except (LiveStateError, OSError, ValueError, KeyError, struct.error) as exc:
        parser.error(str(exc))
    print("NFL_MAIN_MENU_LIVE_STATE_COMPLETE mode=0 initial_row=0 rows=7 direct_font_default=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
