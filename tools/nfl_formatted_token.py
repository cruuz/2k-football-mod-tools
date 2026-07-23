#!/usr/bin/env python3
"""Recover NFL 2K5's 57 pipe-delimited inline-text token records."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
from typing import Any


XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
HEADER_SHA256 = "0f480ad383cd4e6df647b4e50ee8a609365f3cd57e729f090048d0fc37958dad"
TABLE_VA = 0x00A91100
TOKEN_COUNT = 57
TOKEN_STRIDE = 0x24

TOKEN_NAMES = (
    "CROSS", "TRIANGLE", "SQUARE", "CIRCLE", "START", "SELECT",
    "ANALOG", "WARNING", "L1", "R1", "L2", "R2", "DPAD", "L3",
    "R3", "RANALOG", "LANALOGUP", "LANALOGDOWN", "LANALOGLEFT",
    "LANALOGRIGHT", "RANALOGUP", "RANALOGDOWN", "RANALOGLEFT",
    "RANALOGRIGHT", "RANALOGUPLEFT", "RANALOGUPRIGHT",
    "RANALOGDOWNLEFT", "RANALOGDOWNRIGHT", "DPADUP", "DPADDOWN",
    "DPADLEFT", "DPADRIGHT", "COMBRED", "COMBGREEN", "COMBYELLOW",
    "DRAFTUP", "DRAFTRIGHT", "DRAFTLEFT", "DRAFTDOWN", "REG", "TM",
    "BULLET", "BOX", "M_HELP", "M_BACK", "M_PRIMARY", "M_SECONDARY",
    "M_LINK", "M_ADVANCE", "M_NEXTPAGE", "M_PREVPAGE",
    "M_NEXTSUBPAGE", "M_PREVSUBPAGE", "M_LEFTANALOG", "M_RIGHTANALOG",
    "M_LEFTSTICK", "M_RIGHTSTICK",
)

RESOURCE_NAMES = (
    "buttonicons", "buttonicons2", "combred", "combgreen", "combyellow",
    "draftup", "draftright", "draftleft", "draftdown", "tm", "bullet",
    "registered", "box",
)
RESOURCE_NAME_VAS = (
    0x00E6B4B4, 0x00E6B4CC, 0x00E6B4E8, 0x00E6B4F8, 0x00E6B50C,
    0x00E6B524, 0x00E6B534, 0x00E6B54C, 0x00E6B560, 0x00E6B574,
    0x00E6B57C, 0x00E6B58C, 0x00E6B5A4,
)
RESOURCE_CALLS = (
    0x000EF5B7, 0x000EF5CD, 0x000EF5E3, 0x000EF5F9, 0x000EF60F,
    0x000EF625, 0x000EF63B, 0x000EF651, 0x000EF667, 0x000EF67D,
    0x000EF693, 0x000EF6A9, 0x000EF6BF,
)
RESOURCE_STORES = tuple(0x00A90804 + index * 4 for index in range(13))

RANGES = (
    ("utf16_length", 0x00030A60, 0x00030A7E),
    ("utf16_ascii_casefold_compare", 0x00030BE0, 0x00030C3C),
    ("float_to_i32_truncate", 0x000EE8F0, 0x000EE8F9),
    ("inline_quad_emit", 0x000EEDB0, 0x000EEF2B),
    ("token_width", 0x000EEF30, 0x000EEF57),
    ("token_height", 0x000EEF60, 0x000EEF7F),
    ("token_match", 0x000EEF80, 0x000EF03E),
    ("font_and_inline_resource_loader", 0x000EF5A0, 0x000EF832),
    ("token_position_and_draw", 0x000EFC40, 0x000EFD5B),
    ("formatted_string_loop", 0x000F1D50, 0x000F1F1E),
    ("token_table", TABLE_VA, TABLE_VA + TOKEN_COUNT * TOKEN_STRIDE),
)


class TokenError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": file_digest(path)}


class Xbe:
    def __init__(self, path: Path, header_path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        if hashlib.md5(self.data).hexdigest() != XBE_MD5:
            raise TokenError("unexpected NFL 2K5 XBE MD5")
        if digest(self.data) != XBE_SHA256:
            raise TokenError("unexpected NFL 2K5 XBE SHA-256")

    def offset(self, va: int, size: int) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise TokenError(f"VA 0x{va:08x}+0x{size:x} is not raw-backed")

    def read(self, va: int, size: int) -> bytes:
        offset = self.offset(va, size)
        value = self.data[offset:offset + size]
        if len(value) != size:
            raise TokenError(f"short read at 0x{va:08x}")
        return value

    def utf16(self, va: int, limit: int = 128) -> str:
        value = bytearray()
        for index in range(limit):
            unit = self.read(va + index * 2, 2)
            if unit == b"\0\0":
                return value.decode("utf-16le")
            value.extend(unit)
        raise TokenError(f"unterminated UTF-16 string at 0x{va:08x}")


def require(text: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        if phrase not in text:
            raise TokenError(f"{label} lacks {phrase!r}")


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        raise TokenError(f"not a bounded PNG: {path}")
    return struct.unpack_from(">II", data, 16)


def token_records(xbe: Xbe) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(TOKEN_COUNT):
        va = TABLE_VA + index * TOKEN_STRIDE
        raw = xbe.read(va, TOKEN_STRIDE)
        name_pointer, texture_slot = struct.unpack_from("<II", raw)
        words = struct.unpack_from("<7I", raw, 8)
        values = struct.unpack_from("<6f", raw, 8)
        name = xbe.utf16(name_pointer)
        if name != TOKEN_NAMES[index]:
            raise TokenError(f"token {index} is {name!r}, expected {TOKEN_NAMES[index]!r}")
        u0, v0, u1, v1, height_scale, width_over_height = values
        if not (0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0 and
                height_scale > 0.0 and width_over_height > 0.0 and
                words[6] in (0, 1)):
            raise TokenError(f"token {index} has invalid serialized metrics")
        rows.append({
            "index": index, "record_va": f"0x{va:08x}",
            "name_pointer": f"0x{name_pointer:08x}", "name": name,
            "texture_slot": texture_slot,
            "u0": u0, "v0": v0, "u1": u1, "v1": v1,
            "height_scale": height_scale,
            "width_over_height": width_over_height,
            "flags": words[6],
            "u0_bits": f"0x{words[0]:08x}",
            "v0_bits": f"0x{words[1]:08x}",
            "u1_bits": f"0x{words[2]:08x}",
            "v1_bits": f"0x{words[3]:08x}",
            "height_scale_bits": f"0x{words[4]:08x}",
            "width_over_height_bits": f"0x{words[5]:08x}",
        })
    return rows


def resource_records(xbe: Xbe, inventory_path: Path) -> list[dict[str, object]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "nfl2k5_all_txtr_inventory/v1":
        raise TokenError("unexpected texture inventory schema")
    textures = inventory.get("textures", [])
    rows: list[dict[str, object]] = []
    for slot, expected_name in enumerate(RESOURCE_NAMES):
        name = xbe.utf16(RESOURCE_NAME_VAS[slot])
        if name != expected_name:
            raise TokenError(f"loader slot {slot} is {name!r}")
        matches = [row for row in textures
                   if row.get("outer_index") == 3 and
                   row.get("outer_head") == "FONT" and
                   row.get("name") == name]
        if len(matches) != 1:
            raise TokenError(f"texture inventory has {len(matches)} {name!r} rows")
        source = matches[0]
        if source.get("conversion_status") != "base_level_supported":
            raise TokenError(f"{name}: PNG conversion is not proved")
        png = Path(str(source["png_path"]))
        if not png.is_file():
            raise TokenError(f"{name}: missing converted PNG {png}")
        width, height = png_dimensions(png)
        if (width, height) != (source["width"], source["height"]):
            raise TokenError(f"{name}: PNG dimensions differ from inventory")
        rows.append({
            "texture_slot": slot, "resource_name": name,
            "name_pointer": f"0x{RESOURCE_NAME_VAS[slot]:08x}",
            "loader_call": f"0x{RESOURCE_CALLS[slot]:08x}",
            "runtime_store": f"0x{RESOURCE_STORES[slot]:08x}",
            "fourcc": "TXTR", "outer_index": source["outer_index"],
            "outer_id": source["outer_id"], "chunk_index": source["chunk_index"],
            "chunk_offset": source["chunk_offset"], "format": source["format_name"],
            "width": width, "height": height,
            "decoded_sha256": source["decoded_sha256"],
            "rgba_sha256": source["rgba_sha256"],
            "png_path": str(png), "png_sha256": file_digest(png),
        })
    return rows


def build(args: argparse.Namespace) -> tuple[dict[str, object],
                                              list[dict[str, object]],
                                              list[dict[str, object]]]:
    if file_digest(args.xbe_header) != HEADER_SHA256:
        raise TokenError("unexpected XBE-header report hash")
    xbe = Xbe(args.xbe, args.xbe_header)
    trace = args.trace.read_text(encoding="utf-8")
    pseudo = args.pseudo.read_text(encoding="utf-8")
    require(trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "0x000EEDCA MOV ESI,dword ptr [EDI + 0xa91104]",
        "0x000EEF30 CMP EAX,-0x1",
        "0x000EEF45 FMUL float ptr [ECX + 0x24]",
        "0x000EEF60 CMP EAX,-0x1",
        "0x000EEFB0 MOV EDI,0xa91100",
        "0x000EEFC5 CALL 0x00030be0",
        "0x000EEFCE CMP word ptr [ESI + EBP*0x2],0x7c",
        "0x000EEFDD CMP EDI,0xa91904",
        "0x000EF5AB PUSH 0xe6b4b4",
        "0x000EF66C PUSH 0xe6b574",
        "0x000EF67D CALL 0x000449e0",
        "0x000EFCD4 CALL 0x000eef60",
        "0x000EFD43 CALL 0x000eedb0",
        "0x000F1E53 CMP DX,0x7c",
        "0x000F1E5E CALL 0x000eef80",
        "0x000F1E76 CALL 0x000efc40",
        "0x000F1E8D LEA EBX,[EBX + EAX*0x2]",
    ), "Ghidra trace")
    require(pseudo, (
        "/* 0x000EEF80:FUN_000eef80 */",
        "ppuVar5 = &PTR_u_CROSS_00a91100;",
        "if ((iVar3 == 0) && (psVar4[iVar2] == 0x7c))",
        "/* 0x000EFC40:FUN_000efc40 */",
        "FUN_000eedb0(&local_30,unaff_ESI[8],unaff_ESI[0x18]);",
        "/* 0x000F1D50:FUN_000f1d50 */",
    ), "Ghidra pseudo-C")

    tokens = token_records(xbe)
    resources = resource_records(xbe, args.texture_inventory)
    tm = tokens[40]
    tm_resource = resources[9]
    if tm["name"] != "TM" or tm["texture_slot"] != 9 or \
            (tm["u0"], tm["v0"], tm["u1"], tm["v1"],
             tm["height_scale"], tm["width_over_height"], tm["flags"]) != \
            (0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1):
        raise TokenError("serialized TM token contract differs")
    if (tm_resource["resource_name"], tm_resource["width"],
            tm_resource["height"]) != ("tm", 32, 32):
        raise TokenError("TM texture ownership differs")

    menu = json.loads(args.menu_state_report.read_text(encoding="utf-8"))
    rows = menu.get("nfl2k5", {}).get("navigation_rows", [])
    crib = [row for row in rows if row.get("index") == 2]
    if len(crib) != 1 or crib[0].get("label") != "The Crib|TM|":
        raise TokenError("menu-state report does not prove The Crib|TM|")

    renderer_path = Path("src/render/bitmap_font.c")
    main_path = Path("src/main.c")
    cmake_path = Path("CMakeLists.txt")
    schema_path = Path("assets/mod/common/ui/nfl2k5_tm_override.schema.txt")
    screenshot_test_path = Path("tests/nfl_formatted_token_screenshot_test.py")
    require(renderer_path.read_text(encoding="utf-8"), (
        "token_index == 40", "vc_nfl_formatted_token_width",
        "tm_icon->id", "PORTME(0x000EEDB0)",
    ), "native bitmap renderer")
    require(main_path.read_text(encoding="utf-8"), (
        "--nfl-tm-icon", "VC_NFL2K5_TM_ICON", "ui/nfl2k5_tm.png",
        "0047_tm.png", "HOT RELOADED NFL2K5 TM INLINE ICON PNG",
    ), "native main")
    require(cmake_path.read_text(encoding="utf-8"), (
        "recovered_nfl_formatted_token_semantics",
        "host_gl_smoke_recovered_nfl_font7_literal_tm",
        "host_gl_recovered_nfl_tm_screenshot_semantics",
    ), "CMake integration")
    require(schema_path.read_text(encoding="utf-8"), (
        "nfl2k5_tm.png", "No extracted retail pixels",
    ), "loose override schema")

    ranges = []
    for name, start, end in RANGES:
        raw = xbe.read(start, end - start)
        ranges.append({
            "name": name, "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}", "size": end - start,
            "file_offset": xbe.offset(start, end - start),
            "sha256": digest(raw),
        })

    report: dict[str, object] = {
        "schema": "nfl2k5_formatted_token/v1",
        "result": {
            "serialized_token_count": len(tokens),
            "loaded_texture_resource_count": len(resources),
            "ascii_case_insensitive_matching_proved": True,
            "recognized_token_consumes_both_pipes": True,
            "tm_index": 40, "tm_texture_slot": 9,
            "tm_resource_name": "tm", "tm_png_proved": True,
            "main_menu_row_2_label": crib[0]["label"],
            "main_menu_tm_inline_object_proved": True,
            "native_tm_loose_override_wired": True,
            "original_default_main_menu_draw_claimed": False,
        },
        "executable": {"path": str(args.xbe), "md5": XBE_MD5,
                       "sha256": XBE_SHA256, "ranges": ranges},
        "parser_contract": {
            "entry": "0x000eef80",
            "delimiter": "UTF-16 code unit 0x007c",
            "comparison": "table-name length plus ASCII a-z case fold at 0x00030be0",
            "success": "return table index and consume name_length+2 UTF-16 units",
            "failure": "return -1; malformed-token traversal remains title-owned",
        },
        "extent_contract": {
            "height": "CVTTSS2SI(binary32(height_scale * font_height))",
            "width": "CVTTSS2SI(binary32(height_scale * font_height * width_over_height))",
            "tm": "height=font_height; width=font_height",
            "position": "0x000efc40 vertically centers the icon in the current font line and advances x by width",
        },
        "tokens": tokens, "texture_resources": resources,
        "main_menu_join": {
            "report": str(args.menu_state_report), "row": crib[0],
            "formatted_loop": "0x000f1d50",
            "boundary": "the label/token join is exact; the live default menu draw path is not claimed here",
        },
        "native": {
            "header": str(args.native_header), "source": str(args.native_source),
            "test": str(args.native_test),
            "scope": "57-record table, ASCII case-fold match, bounded extents, and loose TM PNG host rendering",
        },
        "source_pins": {
            "xbe": pin(args.xbe), "xbe_header": pin(args.xbe_header),
            "texture_inventory": pin(args.texture_inventory),
            "menu_state_report": pin(args.menu_state_report),
            "ghidra_trace": pin(args.trace), "ghidra_pseudo_c": pin(args.pseudo),
            "ghidra_script": pin(args.ghidra_script),
            "generator": pin(Path("tools/nfl_formatted_token.py")),
            "native_header": pin(args.native_header),
            "native_source": pin(args.native_source),
            "native_test": pin(args.native_test),
            "native_renderer": pin(renderer_path),
            "native_main": pin(main_path),
            "cmake": pin(cmake_path),
            "tm_override_schema": pin(schema_path),
            "screenshot_test": pin(screenshot_test_path),
            "tm_png": pin(Path(str(tm_resource["png_path"]))),
        },
        "portme": [
            "// PORTME(0x000EEDB0): reproduce the original NV2A render-state/quad command stream only after the guest renderer state is fully typed; the Linux seam uses a standard RGBA PNG.",
            "// PORTME(0x000F1EA3): preserve malformed/unknown pipe-token traversal only if title-authored invalid strings are found; the native host retains unknown source text visibly.",
            "// PORTME(0x0014FDA0): the exact The Crib|TM| data join does not prove that this row drawer is the cold-boot/default main-menu visual path.",
        ],
    }
    return report, tokens, resources


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]),
                                dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--texture-inventory", type=Path, required=True)
    parser.add_argument("--menu-state-report", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--ghidra-script", type=Path, required=True)
    parser.add_argument("--native-header", type=Path, required=True)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--native-test", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tokens-tsv", type=Path, required=True)
    parser.add_argument("--resources-tsv", type=Path, required=True)
    args = parser.parse_args()
    report, tokens, resources = build(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    write_tsv(args.tokens_tsv, tokens)
    write_tsv(args.resources_tsv, resources)
    print("NFL_FORMATTED_TOKEN_COMPLETE tokens=57 resources=13 "
          "tm_index=40 tm_slot=9 tm_png=32x32")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
