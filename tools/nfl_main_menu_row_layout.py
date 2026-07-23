#!/usr/bin/env python3
"""Prove and export NFL 2K5 main-menu row/title-space coordinates."""

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
    ("manager_child_getter", 0x0006E2D0, 0x0006E2DE, "27666d018a56ca16d5916b3ebd4716c7be5caf80ce7c7f9fe8084bdea0f6c181"),
    ("row_origin_builder", 0x0014FB70, 0x0014FC16, "5329819038dff391ed1d9c293a89925bec50e4efdf1364b633c43e856ff84921"),
    ("main_menu_row_draw", 0x0014FDA0, 0x0014FF6A, "583c95f7688d987409f3f317cf81d6b2bdeb2d569ca8c01cf693f3e77cb77291"),
    ("row_mode_table", 0x00509A30, 0x00509A60, "278750b845a0c865eb17a7842594aaa61a6d93011909609ac7b53c6f51a5cc28"),
    ("text_x_offset", 0x004E6C50, 0x004E6C54, "03e3c2420f5066a5fa6e36735ed8cc4f6a251046263e1a6024f009deeee3b952"),
    ("wrap_x_offset", 0x004E6C6C, 0x004E6C70, "531ad685bf4dd31ed89c6b99e76c2b9451d6a6d04d82de7d4b1a73217f55e551"),
    ("text_y_offset", 0x004E6D40, 0x004E6D44, "4f4b9b7d8b86633e2824e2f439819357b0cd010ab410ea1a691b12c5f94e91e0"),
)

EXPECTED_MODES = (
    (0.0, 0.0, 10, 38.0),
    (0.0, 0.0, 10, 38.0),
    (144.0, 86.0, 11, 30.0),
)


class LayoutError(ValueError):
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
            raise LayoutError("unexpected NFL 2K5 XBE MD5")
        if sha256(self.data) != EXPECTED_XBE_SHA256:
            raise LayoutError("unexpected NFL 2K5 XBE SHA-256")

    def file_offset(self, va: int, size: int) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise LayoutError(f"VA 0x{va:08x}+0x{size:x} is not file-backed")

    def at(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        result = self.data[offset:offset + size]
        if len(result) != size:
            raise LayoutError(f"short read at VA 0x{va:08x}")
        return result


def require_phrases(text: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        if phrase not in text:
            raise LayoutError(f"{label}: missing exact evidence {phrase!r}")


def row_layout(mode: tuple[float, float, int, float], row: int) -> dict[str, object]:
    base_x, base_y, wrap_rows, step = mode
    x = base_x
    y = base_y + float(row) * step
    remaining = row
    columns = 0
    while remaining >= wrap_rows:
        x += 200.0
        y -= float(wrap_rows) * step
        remaining -= wrap_rows
        columns += 1
    return {
        "row": row,
        "x": x,
        "y": y,
        "z": 20.0,
        "w": 0.0,
        "text_x": x + 8.0,
        "text_y": y - 4.0,
        "wrapped_columns": columns,
    }


def build(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    if file_sha256(args.xbe_header) != EXPECTED_HEADER_SHA256:
        raise LayoutError("unexpected XBE header report SHA-256")
    menu_state = json.loads(args.menu_state_report.read_text(encoding="utf-8"))
    if menu_state.get("schema") != "vc_menu_state_trace/v1":
        raise LayoutError("unexpected menu-state report schema")
    navigation_rows = menu_state.get("nfl2k5", {}).get("navigation_rows", [])
    if len(navigation_rows) != 7 or [row.get("index") for row in navigation_rows] != list(range(7)):
        raise LayoutError("menu-state report does not prove seven ordered NFL rows")
    font_report = json.loads(args.font_report.read_text(encoding="utf-8"))
    if font_report.get("schema") != "nfl2k5_main_menu_font/v1":
        raise LayoutError("unexpected main-menu FONT report schema")
    font_result = font_report.get("result", {})
    if (font_result.get("main_menu_font_slot"),
            font_result.get("main_menu_font_name")) != (6, "font7"):
        raise LayoutError("FONT report does not prove slot 6 -> font7")
    xbe = XbeView(args.xbe, args.xbe_header)
    trace = args.trace.read_text(encoding="utf-8")
    pseudo = args.pseudo.read_text(encoding="utf-8")
    require_phrases(trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "0x0014FB75 CALL 0x0006e2d0",
        "0x0014FB7A MOV ECX,dword ptr [EAX + 0xa7c]",
        "0x0014FB80 SHL ECX,0x4",
        "0x0014FB83 FLD float ptr [ECX + 0x509a3c]",
        "0x0014FB95 FADD float ptr [ECX + 0x509a34]",
        "0x0014FB9F FLD float ptr [ECX + 0x509a30]",
        "0x0014FBAE MOV dword ptr [ESI + 0x8],0x41a00000",
        "0x0014FBD2 FADD float ptr [0x004e6c6c]",
        "0x0014FE4A CALL 0x0014fb70",
        "0x0014FEFE FSUB float ptr [0x004e6d40]",
        "0x0014FF18 FADD float ptr [0x004e6c50]",
        "0x0014FF21 CALL 0x00046a70",
        "0x0014FF38 CALL 0x000f1d50",
    ), "Ghidra trace")
    require_phrases(pseudo, (
        "/* 0x0014FB70:FUN_0014fb70 */",
        "unaff_ESI[1] = fVar1 * (float)param_1 + fVar2;",
        "unaff_ESI[2] = 20.0;",
        "*unaff_ESI = *unaff_ESI + _DAT_004e6c6c;",
        "FUN_00046a70(local_160 + _DAT_004e6c50,local_15c - _DAT_004e6d40,local_158);",
    ), "Ghidra pseudo-C")

    ranges = []
    for name, start, end, expected in EXPECTED_RANGES:
        body = xbe.at(start, end - start)
        actual = sha256(body)
        if actual != expected:
            raise LayoutError(f"{name}: expected {expected}, got {actual}")
        ranges.append({
            "name": name, "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}", "size": end - start,
            "file_offset": xbe.file_offset(start, end - start),
            "sha256": actual,
        })

    table = xbe.at(0x00509A30, 48)
    modes = tuple(struct.unpack_from("<ffif", table, index * 16)
                  for index in range(3))
    if modes != EXPECTED_MODES:
        raise LayoutError(f"row layout table differs: {modes!r}")
    text_x, = struct.unpack("<f", xbe.at(0x004E6C50, 4))
    wrap_x, = struct.unpack("<f", xbe.at(0x004E6C6C, 4))
    text_y_subtract, = struct.unpack("<f", xbe.at(0x004E6D40, 4))
    if (text_x, wrap_x, text_y_subtract) != (8.0, 200.0, 4.0):
        raise LayoutError("row-layout scalar constants differ")

    rows: list[dict[str, object]] = []
    mode_records: list[dict[str, object]] = []
    for mode_index, mode in enumerate(modes):
        mode_rows = []
        for row in range(7):
            layout = {"mode": mode_index, **row_layout(mode, row)}
            rows.append(layout)
            mode_rows.append(layout)
        mode_records.append({
            "mode": mode_index,
            "base_x": mode[0], "base_y": mode[1],
            "wrap_rows": mode[2], "row_step": mode[3],
            "first_seven_rows": mode_rows,
            "first_wrap": row_layout(mode, mode[2]),
        })

    report: dict[str, object] = {
        "schema": "nfl2k5_main_menu_row_layout/v1",
        "result": {
            "serialized_modes": 3,
            "recovered_main_menu_rows": 7,
            "emitted_mode_row_pairs": len(rows),
            "all_first_seven_rows_before_wrap": True,
            "portable_native_implementation": "src/recovered/nfl2k5/main_menu_row_layout.c",
            "concrete_live_mode_proved": False,
            "framebuffer_pixel_mapping_proved": False,
        },
        "executable": {
            "path": str(args.xbe), "md5": EXPECTED_XBE_MD5,
            "sha256": EXPECTED_XBE_SHA256, "ranges": ranges,
        },
        "ownership": {
            "manager_child": "0x0006e2d0 returns state+0x10c; 0x0014fb7a reads child+0xa7c",
            "mode_index": "child+0xa7c selects one 0x10-byte row at 0x00509a30",
            "row_index": "0x0014fda0 increments only for drawable records and calls 0x0014fb70 at 0x0014fe4a",
            "text_position": "0x0014ff18 adds 8 to row x; 0x0014fefe subtracts 4 from row y; 0x0014ff21 writes the text origin",
            "font_join": "0x0014ff38 draws the label after slot 6; the pinned nfl2k5_main_menu_font/v1 report proves slot 6 -> font7",
        },
        "upstream_joins": {
            "navigation_rows": {
                "report": str(args.menu_state_report),
                "schema": menu_state["schema"],
                "count": len(navigation_rows),
                "indices": [row["index"] for row in navigation_rows],
                "labels": [row["label"] for row in navigation_rows],
            },
            "font": {
                "report": str(args.font_report),
                "schema": font_report["schema"],
                "slot": font_result["main_menu_font_slot"],
                "name": font_result["main_menu_font_name"],
            },
        },
        "contract": {
            "row_origin": "x=base_x, y=base_y+row*row_step, z=20, w=0",
            "wrap": "while row>=wrap_rows: x+=200, y-=wrap_rows*row_step, row-=wrap_rows",
            "text_origin": "text_x=x+8; text_y=y-4",
            "coordinate_space": "exact title-space values before the still-unrecovered viewport/projection transform",
        },
        "modes": mode_records,
        "source_pins": {
            "xbe": pin(args.xbe), "xbe_header": pin(args.xbe_header),
            "ghidra_trace": pin(args.trace), "ghidra_pseudo_c": pin(args.pseudo),
            "ghidra_script": pin(args.ghidra_script),
            "generator": pin(Path("tools/nfl_main_menu_row_layout.py")),
            "menu_state_report": pin(args.menu_state_report),
            "main_menu_font_report": pin(args.font_report),
            "native_header": pin(args.native_header),
            "native_source": pin(args.native_source),
            "native_test": pin(args.native_test),
        },
        "portme": [
            "// PORTME(0x0014FB7A): identify the human-facing meaning and concrete live main-menu value of manager child field +0xA7C; all three exact table modes are retained.",
            "// PORTME(0x0014FF21): recover the downstream viewport/projection transform before treating title-space coordinates as Linux framebuffer pixels.",
            "// PORTME(0x0014FB83): preserve original x87 intermediate and exception behavior if arbitrary int32 row values, rather than the bounded menu rows, must be bit-exact.",
        ],
    }
    return report, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--ghidra-script", type=Path, required=True)
    parser.add_argument("--menu-state-report", type=Path, required=True)
    parser.add_argument("--font-report", type=Path, required=True)
    parser.add_argument("--native-header", type=Path, required=True)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--native-test", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()
    try:
        report, rows = build(args)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]),
                                    dialect="excel-tab", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    except (LayoutError, OSError, ValueError, struct.error) as exc:
        parser.error(str(exc))
    print("NFL_MAIN_MENU_ROW_LAYOUT_COMPLETE modes=3 rows=7 pairs=21")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
