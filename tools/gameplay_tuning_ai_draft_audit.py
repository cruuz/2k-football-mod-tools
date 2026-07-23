#!/usr/bin/env python3
"""Read-only audit of 2K5/APF gameplay sliders and fantasy-draft tuning.

The output deliberately separates proved data ownership from candidate patch
paths.  It never patches an XBE/XEX, save/profile, archive, or disc image.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from xbe_info import Xbe


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "vc_gameplay_tuning_ai_draft_audit/v1"

NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
APF_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"

DEFAULT_NFL_XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
DEFAULT_APF_XEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"
DEFAULT_APF_PE = ROOT / ".codex-tmp/apf-sixth/apf-decoded.pe"
DEFAULT_APF_HEADER = ROOT / "reports/headers/apf2k8_xex_report.json"
DEFAULT_NFL_LEDGER = ROOT / "research/functions/nfl2k5/functions.tsv"
DEFAULT_APF_LEDGER = ROOT / "research/functions/apf2k8/ledger"
DEFAULT_TRACE = ROOT / "reports/gameplay_tuning/apf_gameplay_tuning_trace.txt"
DEFAULT_JSON = ROOT / "reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json"
DEFAULT_TSV = ROOT / "reports/gameplay_tuning/gameplay_tuning_mod_candidates.tsv"
DEFAULT_PORTME = ROOT / "reports/gameplay_tuning/gameplay_tuning_ai_draft_portme.c"

NFL_SLIDER_TABLE = 0x00501F54
NFL_SLIDER_STRIDE = 0x34
APF_BASE = 0x82000000
APF_OFFLINE_TABLE = 0x84E4B088
APF_ONLINE_TABLE = 0x84E4C7C8
APF_SLIDER_STRIDE = 0x60

LABELS = (
    "Human Blocking", "Human Passing", "Human Running", "Human Catching",
    "Human Coverage", "Human Pursuit", "Human Tackling", "Human Kicking",
    "Human Fatigue", "CPU Blocking", "CPU Passing", "CPU Running",
    "CPU Catching", "CPU Coverage", "CPU Pursuit", "CPU Tackling",
    "CPU Kicking", "CPU Fatigue", "Injury", "Fumble", "Interception",
)
POSITIONS = (
    "QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB",
    "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE",
)
EXPECTED_DRAFT_WEIGHTS = (
    2.0, 0.1, 0.2, 1.4, 1.0, 1.1, 1.1, 1.7, 1.0,
    1.2, 1.2, 0.7, 0.5, 1.1, 1.3, 1.4, 1.3,
)


class AuditError(ValueError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise AuditError(message)


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def hx(value: int) -> str:
    return f"0x{value:08X}"


def sign16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def pe_bytes(pe: bytes, address: int, size: int) -> bytes:
    offset = address - APF_BASE
    require(0 <= offset <= len(pe) - size, f"APF address outside PE: {hx(address)}")
    return pe[offset:offset + size]


def pe_u32(pe: bytes, address: int) -> int:
    return struct.unpack(">I", pe_bytes(pe, address, 4))[0]


def pe_utf16be(pe: bytes, address: int) -> str:
    offset = address - APF_BASE
    require(0 <= offset < len(pe), f"APF string outside PE: {hx(address)}")
    end = offset
    while end + 1 < len(pe) and pe[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < len(pe), f"unterminated APF string at {hx(address)}")
    return pe[offset:end].decode("utf-16be")


def code_witness(data: bytes, start: int, end_inclusive: int) -> dict[str, Any]:
    blob = data[start:end_inclusive + 1]
    return {
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def xbe_witness(xbe: Xbe, start: int, end_inclusive: int) -> dict[str, Any]:
    size = end_inclusive - start + 1
    offset = xbe.va_to_offset(start, size)
    result = code_witness(xbe.data, offset, offset + size - 1)
    result.update({"range": f"{hx(start)}-{hx(end_inclusive)}", "file_offset": hx(offset)})
    return result


def apf_witness(pe: bytes, start: int, end_inclusive: int) -> dict[str, Any]:
    offset = start - APF_BASE
    result = code_witness(pe, offset, end_inclusive - APF_BASE)
    result.update({"range": f"{hx(start)}-{hx(end_inclusive)}", "flat_pe_offset": hx(offset)})
    return result


def nfl_sliders(xbe: Xbe) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, expected_label in enumerate(LABELS):
        address = NFL_SLIDER_TABLE + index * NFL_SLIDER_STRIDE
        offset = xbe.va_to_offset(address, NFL_SLIDER_STRIDE)
        kind, label_pointer = struct.unpack_from("<II", xbe.data, offset)
        callbacks = struct.unpack_from("<5I", xbe.data, offset + 0x0C)
        label = xbe.utf16z_va(label_pointer)
        require(kind == 4 and label == expected_label, f"NFL slider row {index} changed")
        maximum, minimum, current, increment, decrement = callbacks
        current_code = xbe.data[xbe.va_to_offset(current, 7):xbe.va_to_offset(current, 7) + 7]
        require(current_code[:2] == b"\xD9\x05" and current_code[6] == 0xC3,
                f"NFL current getter changed for {label}")
        global_address = struct.unpack_from("<I", current_code, 2)[0]
        require(xbe.data[xbe.va_to_offset(maximum, 7):xbe.va_to_offset(maximum, 7) + 7] ==
                b"\xD9\x05\x9C\x41\x4E\x00\xC3", f"NFL maximum getter changed for {label}")
        require(xbe.data[xbe.va_to_offset(minimum, 7):xbe.va_to_offset(minimum, 7) + 7] ==
                b"\xD9\x05\x80\x41\x4E\x00\xC3", f"NFL minimum getter changed for {label}")
        rows.append({
            "index": index,
            "label": label,
            "row_virtual_address": hx(address),
            "row_file_offset": hx(offset),
            "editable_global": hx(global_address),
            "callbacks": {
                "maximum": hx(maximum), "minimum": hx(minimum),
                "current": hx(current), "increment": hx(increment),
                "decrement": hx(decrement),
            },
        })
    return rows


def apf_getter_global(pe: bytes, address: int) -> int:
    words = struct.unpack(">4I", pe_bytes(pe, address, 16))
    require(words[0] >> 16 == 0x3D60, f"APF getter lis changed at {hx(address)}")
    require(words[1] >> 16 == 0x396B, f"APF getter addi changed at {hx(address)}")
    require(words[2] >> 16 == 0xC02B and words[3] == 0x4E800020,
            f"APF getter lfs/blr changed at {hx(address)}")
    return ((words[0] & 0xFFFF) << 16) + sign16(words[1] & 0xFFFF) + sign16(words[2] & 0xFFFF)


def apf_slider_table(pe: bytes, table: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    require(pe_u32(pe, table) == 7 and pe_utf16be(pe, pe_u32(pe, table + 4)) == "Difficulty",
            f"APF difficulty row changed at {hx(table)}")
    for index, expected_label in enumerate(LABELS):
        address = table + (index + 1) * APF_SLIDER_STRIDE
        kind = pe_u32(pe, address)
        label = pe_utf16be(pe, pe_u32(pe, address + 4))
        callbacks = [pe_u32(pe, address + delta) for delta in (0x0C, 0x10, 0x14, 0x18, 0x1C)]
        require(kind == 4 and label == expected_label, f"APF slider row {index} changed")
        maximum, minimum, current, increment, decrement = callbacks
        require(pe_bytes(pe, maximum, 12) == bytes.fromhex("3d608200c02b09a44e800020"),
                f"APF maximum getter changed for {label}")
        require(pe_bytes(pe, minimum, 12) == bytes.fromhex("3d608200c02b09a04e800020"),
                f"APF minimum getter changed for {label}")
        rows.append({
            "index": index,
            "label": label,
            "row_virtual_address": hx(address),
            "flat_pe_offset": hx(address - APF_BASE),
            "editable_global": hx(apf_getter_global(pe, current)),
            "callbacks": {
                "maximum": hx(maximum), "minimum": hx(minimum),
                "current": hx(current), "increment": hx(increment),
                "decrement": hx(decrement),
            },
        })
    return rows


def load_nfl_functions(path: Path, addresses: tuple[int, ...]) -> dict[str, Any]:
    wanted = {hx(address).lower(): address for address in addresses}
    found: dict[str, Any] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            address = row.get("address")
            if address and address.lower() in wanted:
                found[hx(int(address, 16))] = {
                    "ledger_range": f"{row['address']}-{row['end']}",
                    "caller_count": int(row["caller_count"]),
                    "callers": row["callers"].split(";") if row["callers"] else [],
                    "callee_count": int(row["callee_count"]),
                    "callees": row["callees"].split(";") if row["callees"] else [],
                    "pseudo_c": row["pseudo_c_file"],
                }
    require(set(found) == {hx(address) for address in addresses},
            "NFL function-ledger target set changed")
    return found


def load_apf_functions(directory: Path, addresses: tuple[int, ...]) -> dict[str, Any]:
    wanted = set(addresses)
    found: dict[str, Any] = {}
    for path in sorted(directory.glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                address = int(row["address"], 16)
                if address in wanted:
                    found[hx(address)] = {
                        "range": f"{row['range_start']}-{row['range_end_inclusive']}",
                        "caller_count": row["caller_count"],
                        "callers": row["callers"],
                        "callee_count": row["callee_count"],
                        "callees": row["callees"],
                        "direct_strings": [item["value"] for item in row["direct_string_references"]],
                        "pseudo_c": row["pseudo_c_shard"],
                    }
    require(set(found) == {hx(address) for address in wanted}, "APF function-ledger target set changed")
    return found


def parse_trace(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    require(lines[:2] == [
        "schema=vc_apf_gameplay_tuning_trace/v1",
        f"program_md5={APF_XEX_MD5}",
    ], "APF focused Ghidra trace header changed")
    targets: dict[str, Any] = {}
    for line in lines[2:]:
        require(line.startswith("target=") and " refs=" in line and " fullwords=" in line,
                "malformed APF trace row")
        address, tail = line[len("target="):].split(" refs=", 1)
        refs, fullwords = tail.split(" fullwords=", 1)
        targets[address] = {
            "references": refs.split(";") if refs else [],
            "aligned_fullword_occurrences": fullwords.split(";") if fullwords else [],
        }
    require("0x820F4B70" in targets and not targets["0x820F4B70"]["references"] and
            not targets["0x820F4B70"]["aligned_fullword_occurrences"],
            "APF draft table unexpectedly gained a direct trace owner")
    return {"schema": lines[0].split("=", 1)[1], "program_md5": APF_XEX_MD5, "targets": targets}


def ppc_materializations(pe: bytes, target: int) -> list[str]:
    """Find conventional lis+addi/ori materializations within eight words."""
    hi = (target >> 16) & 0xFFFF
    lo = target & 0xFFFF
    hits: list[str] = []
    for offset in range(0, len(pe) - 36, 4):
        first = struct.unpack_from(">I", pe, offset)[0]
        if first >> 26 != 15 or ((first >> 16) & 0x1F) != 0 or (first & 0xFFFF) != hi:
            continue
        register = (first >> 21) & 0x1F
        for delta in range(4, 36, 4):
            word = struct.unpack_from(">I", pe, offset + delta)[0]
            addi = (word >> 26 == 14 and (word >> 21) & 0x1F == register and
                    (word >> 16) & 0x1F == register and word & 0xFFFF == lo)
            ori = (word >> 26 == 24 and (word >> 21) & 0x1F == register and
                   (word >> 16) & 0x1F == register and word & 0xFFFF == lo)
            if addi or ori:
                hits.append(hx(APF_BASE + offset))
    return hits


def output_tsv(path: Path) -> None:
    rows = [
        ("NFL 2K5", "stock 21 gameplay sliders", "UI callbacks / profile state", "proved 0..1 UI", "yes for executable defaults", "no", "final per-play consumers unresolved"),
        ("NFL 2K5", "out-of-range sliders", "raw setter/import vector", "candidate only", "not necessarily if save payload is solved", "no", "no clamp on proved import path; downstream safety unknown"),
        ("NFL 2K5", "CPU fantasy-draft position priorities", "17-float .rdata table", "exact executable-patch candidate", "yes", "no", "table owner and pick path proved; runtime patch untested"),
        ("NFL 2K5", "catch/drop frequency", "Catching sliders plus final outcome logic", "partially mapped", "unknown", "no", "slider owner proved; final catch/drop branch and polarity not proved"),
        ("APF 2K8", "stock 21 gameplay sliders", "offline/online UI callbacks / 21-float profile state", "proved 0..1 UI", "yes for executable defaults", "no", "raw importer and runtime synchronization proved"),
        ("APF 2K8", "out-of-range sliders", "raw 21-float importer", "candidate only", "not necessarily if save payload is solved", "no", "importer does not clamp; final consumers and stability unknown"),
        ("APF 2K8", "CPU fantasy-draft priorities", "retained 17-float table / old UI cluster", "lineage only", "unknown", "no", "identical table exists but no direct/ref/materialized owner was found"),
        ("APF 2K8", "franchise mode", "state/UI/database/schedule/save executable systems", "not data-only", "yes", "no", "cannot be ported by assets or slider/profile edits"),
        ("cross-title", "2K5 franchise into APF", "code and schema integration", "requires executable reimplementation/patching", "yes", "no", "shared lineage lowers research cost but does not create a drop-in module"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("game", "feature", "mechanism", "status", "executable_mutation_required", "copy_only_iso_feasible", "notes"))
        writer.writerows(rows)


def output_portme(path: Path) -> None:
    text = """/* Auto-generated evidence placeholders; no original game code is included. */
#include <stddef.h>

typedef struct vc_portme_item {
    const char *game;
    const char *address;
    const char *work;
} vc_portme_item;

static const vc_portme_item vc_gameplay_portme[] = {
    /* PORTME: identify the final NFL catch-success/drop consumer and prove slider polarity. */
    {"NFL 2K5", "0x00E600F4/0x00E60118", "trace Human/CPU Catching from globals to final outcome branch"},
    /* PORTME: prove safety before exposing values outside the stock 0..1 interval. */
    {"NFL 2K5", "0x000E3B90", "trace every indexed slider consumer and validate finite ranges"},
    /* PORTME: map the Xbox save/profile container, integrity fields, and precedence. */
    {"NFL 2K5", "0x000E3DC0", "locate serialized slider payload without reusing disc offsets"},
    /* PORTME: runtime-test an emulator-compatible copied-XBE patch; never overwrite retail input. */
    {"NFL 2K5", "0x00589588", "validate CPU draft weight changes and section-digest/signature handling"},
    /* PORTME: identify the final APF catch-success/drop consumer and prove slider polarity. */
    {"APF 2K8", "0x84F3FC44/0x84F3FC20", "resolve indexed/computed reads after runtime synchronization"},
    /* PORTME: prove downstream safety for APF profile values outside 0..1. */
    {"APF 2K8", "0x8470A630", "trace all 21 imported floats through final gameplay consumers"},
    /* PORTME: map APF profile container/integrity and offline-versus-online precedence. */
    {"APF 2K8", "0x8471F2A0", "recover exact serialized owner of the 0x54-byte slider vector"},
    /* PORTME: resolve TOC/computed ownership or prove the retained draft table is dead data. */
    {"APF 2K8", "0x820F4B70", "find a CPU draft selector before offering any APF draft-AI control"},
    /* PORTME: franchise transfer needs subsystem integration, not an asset copy. */
    {"cross-title", "unresolved", "map mode state, season DB, schedule, contracts, UI, and saves"},
};

size_t vc_gameplay_portme_count(void) {
    return sizeof(vc_gameplay_portme) / sizeof(vc_gameplay_portme[0]);
}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    require(digest(args.nfl_xbe) == NFL_XBE_SHA256, "unexpected NFL XBE hash")
    require(digest(args.apf_xex) == APF_XEX_SHA256, "unexpected APF XEX hash")
    require(digest(args.apf_pe) == APF_PE_SHA256, "unexpected APF decoded PE hash")
    xbe = Xbe(args.nfl_xbe)
    pe = args.apf_pe.read_bytes()
    header = json.loads(args.apf_header.read_text(encoding="utf-8"))
    require(header["inputs"]["xex_sha256"] == APF_XEX_SHA256 and
            header["inputs"]["decompressed_pe_sha256"] == APF_PE_SHA256,
            "APF header report input identity changed")

    nfl_rows = nfl_sliders(xbe)
    apf_offline = apf_slider_table(pe, APF_OFFLINE_TABLE)
    apf_online = apf_slider_table(pe, APF_ONLINE_TABLE)
    require([(r["label"], r["editable_global"], r["callbacks"]) for r in apf_offline] ==
            [(r["label"], r["editable_global"], r["callbacks"]) for r in apf_online],
            "APF offline/online slider callbacks diverged")
    require([r["label"] for r in nfl_rows] == [r["label"] for r in apf_offline] == list(LABELS),
            "cross-title slider labels diverged")

    nfl_constants = {address: struct.unpack("<f", xbe.data[xbe.va_to_offset(address, 4):xbe.va_to_offset(address, 4) + 4])[0]
                     for address in (0x004E4180, 0x004E419C, 0x004F6B48, 0x00503C08)}
    require(all(abs(nfl_constants[address] - expected) < 1e-6 for address, expected in {
        0x004E4180: 0.0, 0x004E419C: 1.0, 0x004F6B48: 0.025, 0x00503C08: 0.975,
    }.items()), "NFL slider constants changed")
    apf_constants = {address: struct.unpack(">f", pe_bytes(pe, address, 4))[0]
                     for address in (0x820009A0, 0x820009A4, 0x820B4518, 0x820BACD0)}
    require(all(abs(apf_constants[address] - expected) < 1e-6 for address, expected in {
        0x820009A0: 0.0, 0x820009A4: 1.0, 0x820B4518: 0.025, 0x820BACD0: 0.975,
    }.items()), "APF slider constants changed")

    nfl_weight_address = 0x00589588
    nfl_weight_offset = xbe.va_to_offset(nfl_weight_address, 17 * 4)
    nfl_weights = struct.unpack_from("<17f", xbe.data, nfl_weight_offset)
    apf_weight_addresses = (0x820F4B70, 0x820053F0)
    apf_weights = [struct.unpack(">17f", pe_bytes(pe, address, 17 * 4)) for address in apf_weight_addresses]
    for values in (nfl_weights, *apf_weights):
        require(all(abs(a - b) < 1e-6 for a, b in zip(values, EXPECTED_DRAFT_WEIGHTS)),
                "fantasy-draft priority table changed")

    nfl_function_addresses = (0x0036EDD0, 0x0036EE70, 0x0036F0A0, 0x0036F830, 0x0010E050, 0x000E3B90, 0x000E3DC0)
    nfl_functions = load_nfl_functions(args.nfl_ledger, nfl_function_addresses)
    corrected = xbe_witness(xbe, 0x0036EE70, 0x0036F095)
    corrected["ledger_reported_range"] = nfl_functions[hx(0x0036EE70)]["ledger_range"]
    corrected["correction"] = "raw contiguous body reaches the restoring RET at 0x0036F095"
    body = xbe.data[xbe.va_to_offset(0x0036EE70, 0x226):xbe.va_to_offset(0x0036EE70, 0x226) + 0x226]
    corrected["table_pointer_occurrences"] = [hx(0x0036EE70 + i) for i in range(len(body))
                                               if body.startswith(struct.pack("<I", nfl_weight_address), i)]
    require(corrected["table_pointer_occurrences"] == ["0x0036EEFA", "0x0036EF22"],
            "NFL draft table use sites changed")

    apf_function_addresses = (
        0x8470A578, 0x8470A630, 0x8471F2A0, 0x847251A8, 0x849FE0D0,
        0x84680058, 0x846801B8, 0x84680C00, 0x84680C90, 0x84681030,
        0x84681258, 0x846813C8, 0x846819F8, 0x84681A48, 0x84681A88,
    )
    apf_functions = load_apf_functions(args.apf_ledger, apf_function_addresses)
    trace = parse_trace(args.trace)
    materializations = ppc_materializations(pe, 0x820F4B70)
    require(materializations == [], "APF draft table gained a conventional PPC materialization")

    nfl_sync_order = [
        next(row for row in nfl_rows if row["label"] == label)["editable_global"]
        for label in (*LABELS[9:18], *LABELS[0:9])
    ]
    apf_import_labels = ("Interception", *LABELS[:18], "Injury", "Fumble")
    apf_import_order = [{
        "parameter_index": index,
        "label": label,
        "editable_global": next(row for row in apf_offline if row["label"] == label)["editable_global"],
    } for index, label in enumerate(apf_import_labels)]

    draft_rows = [{"position_code": index, "position": position, "weight": round(nfl_weights[index], 3)}
                  for index, position in enumerate(POSITIONS)]
    return {
        "schema": SCHEMA,
        "inputs": {
            "nfl_xbe": {"path": str(args.nfl_xbe.resolve().relative_to(ROOT)), "sha256": NFL_XBE_SHA256},
            "apf_xex": {"path": str(args.apf_xex.resolve().relative_to(ROOT)), "sha256": APF_XEX_SHA256},
            "apf_decoded_pe": {"size": len(pe), "sha256": APF_PE_SHA256},
            "nfl_function_ledger_sha256": digest(args.nfl_ledger),
            "apf_function_manifest_sha256": digest(args.apf_ledger.parent / "manifest.json"),
            "ghidra_trace_sha256": digest(args.trace),
        },
        "scope": {
            "read_only": True,
            "emulator_or_game_launched": False,
            "save_or_profile_fixture_supplied": False,
            "originals_modified": False,
            "out_of_range_runtime_safety_claimed": False,
            "franchise_port_claimed": False,
        },
        "summary": {
            "shared_slider_count": 21,
            "stock_ui_minimum": 0.0,
            "stock_ui_maximum": 1.0,
            "stock_ui_step": 0.025,
            "nfl_cpu_draft_weight_count": 17,
            "nfl_cpu_draft_owner_proved": True,
            "apf_equivalent_draft_owner_proved": False,
            "copy_only_iso_gameplay_tuning_proved": False,
        },
        "shared_slider_schema": {"labels": list(LABELS), "labels_identical": True},
        "nfl2k5": {
            "sliders": {
                "table": {"virtual_address": hx(NFL_SLIDER_TABLE), "file_offset": hx(xbe.va_to_offset(NFL_SLIDER_TABLE, 21 * NFL_SLIDER_STRIDE)), "record_stride": NFL_SLIDER_STRIDE},
                "records": nfl_rows,
                "constants": {hx(address): value for address, value in nfl_constants.items()},
                "human_catching_direct_setter": {
                    "address": "0x000E23A0", "editable_global": "0x00E600F4",
                    "stores_raw_32_bit_argument_before_notification": True,
                    "range_clamp_observed": False,
                    "witness": xbe_witness(xbe, 0x000E23A0, 0x000E23AD),
                },
                "indexed_reload": {
                    "owner": "0x000E3B90", "observed_copy_range": "0x000E397E-0x000E3AFD",
                    "range_clamp_observed": False,
                    "witness": xbe_witness(xbe, 0x000E397E, 0x000E3AFD),
                },
                "synchronizer": {
                    "owner": "0x000E3DC0", "range": "0x000E3DC0-0x000E3F05",
                    "indexed_vector_base": "0x00E60218", "vector_order_cpu_then_human": nfl_sync_order,
                    "witness": xbe_witness(xbe, 0x000E3DC0, 0x000E3F05),
                },
                "aggregate_consumer": {
                    "address": "0x0010E050", "range": "0x0010E050-0x0010E0FA",
                    "uses_all_18_human_cpu_globals": True,
                    "is_final_catch_drop_outcome": False,
                    "witness": xbe_witness(xbe, 0x0010E050, 0x0010E0FA),
                },
            },
            "cpu_fantasy_draft": {
                "priority_table": {"virtual_address": hx(nfl_weight_address), "file_offset": hx(nfl_weight_offset), "section": ".rdata", "rows": draft_rows},
                "algorithm": "score each position using best available player evaluation times (base weight + 4.0 if empty, else target_count - current_count), sort positions, then rank-weight candidate selection",
                "functions": nfl_functions,
                "corrected_priority_builder_boundary": corrected,
                "pick_path": "0x0036F830-0x0036F938",
                "classification": "exact executable-patch candidate; runtime patch not performed",
            },
            "catch_drop_result": {
                "human_global": "0x00E600F4", "cpu_global": "0x00E60118",
                "slider_label_semantics_proved": True,
                "final_success_drop_branch_proved": False,
                "direction_or_polarity_claimed": False,
            },
        },
        "apf2k8": {
            "sliders": {
                "offline_descriptor": {"address": "0x820E8F38", "name": "OptionsMenu_AISlidersMenu", "table": hx(APF_OFFLINE_TABLE)},
                "online_descriptor": {"address": "0x820E94A8", "name": "OptionsMenu_OnlineAISlidersMenu", "table": hx(APF_ONLINE_TABLE)},
                "offline_records": apf_offline,
                "online_records_share_callbacks_and_globals": True,
                "constants": {hx(address): value for address, value in apf_constants.items()},
                "human_catching_increment": {"range": "0x84A42500-0x84A4258B", "witness": apf_witness(pe, 0x84A42500, 0x84A4258B)},
                "human_catching_decrement": {"range": "0x84A42590-0x84A42613", "witness": apf_witness(pe, 0x84A42590, 0x84A42613)},
                "exporter": {"range": "0x8470A578-0x8470A62B", "element_count": 21, "witness": apf_witness(pe, 0x8470A578, 0x8470A62B)},
                "importer": {"range": "0x8470A630-0x8470A757", "element_count": 21, "serialized_size": 0x54, "order": apf_import_order, "range_clamp_observed": False, "witness": apf_witness(pe, 0x8470A630, 0x8470A757)},
                "serialized_copy_owner": {"range": "0x8471F2A0-0x8471F2D3", "copies_exact_bytes": 0x54, "then_calls_importer": True},
                "runtime_sync": {"range": "0x849FE0D0-0x849FE183", "human_catching_source": "0x84F3F9C0", "human_catching_destination": "0x84F3FC44", "cpu_catching_source": "0x84F3F9E4", "cpu_catching_destination": "0x84F3FC20", "witness": apf_witness(pe, 0x849FE0D0, 0x849FE183)},
                "focused_ghidra_trace": trace,
            },
            "fantasy_draft_lineage": {
                "priority_tables": [{"virtual_address": hx(address), "flat_pe_offset": hx(address - APF_BASE), "rows": draft_rows} for address in apf_weight_addresses],
                "semantically_identical_to_nfl": True,
                "retained_function_cluster": {"range": "0x84680058-0x84681A8F", "functions": {key: apf_functions[key] for key in apf_functions if 0x84680058 <= int(key, 16) <= 0x84681A88}},
                "direct_ghidra_references_to_table": [],
                "aligned_fullword_pointers_to_table": [],
                "conventional_lis_addi_or_ori_materializations": materializations,
                "computed_or_toc_owner_exhaustively_excluded": False,
                "cpu_selector_proved": False,
                "classification": "retained lineage/orphan candidate, not a public draft-AI control",
            },
            "function_evidence": {key: apf_functions[key] for key in apf_functions if not 0x84680058 <= int(key, 16) <= 0x84681A88},
            "catch_drop_result": {
                "editable_globals": ["0x84F3F9C0", "0x84F3F9E4"],
                "runtime_copies": ["0x84F3FC44", "0x84F3FC20"],
                "direct_refs_to_runtime_copies_are_writes_only": True,
                "final_computed_or_indexed_consumer_proved": False,
                "direction_or_polarity_claimed": False,
            },
        },
        "executable_integrity_boundary": {
            "nfl_xbe": {"slider_and_draft_data_inside_signed_default_xbe": True, "section_sha1_digest_present": True, "copy_only_asset_archive_edit_reaches_values": False},
            "apf_xex": {"slider_code_and_state_inside_default_xex": True, "encryption": header["file_format"]["encryption_name"], "compression": header["file_format"]["compression_name"], "page_descriptor_count": header["security_info"]["page_descriptor_count"], "copy_only_asset_archive_edit_reaches_values": False},
            "save_profile_alternative": {"raw_slider_payload_candidate": True, "container_or_integrity_mapped": False, "load_precedence_mapped": False, "writer_safe_to_release": False},
        },
        "modding_conclusions": {
            "stock_slider_editor": "possible after save/profile container and integrity mapping, or via executable/emulator patching",
            "sliders_beyond_stock": "raw import paths accept them, but do not expose publicly until all final consumers and runtime stability are proved",
            "frequent_drops": "Catching controls are exact; final catch/drop branch and code-level polarity remain PORTME",
            "nfl_cpu_draft_logic": "17 position-priority weights are exact and patchable only through default.xbe/emulator patch work",
            "apf_cpu_draft_logic": "retained table/code lineage is real, but no selector ownership is proved",
            "franchise_2k5_to_apf": "not an asset/data-only mod; requires executable/state/UI/database/save integration",
        },
        "portme": [
            {"game": "NFL 2K5", "address": "0x00E600F4/0x00E60118", "task": "identify final catch/drop consumer and polarity"},
            {"game": "NFL 2K5", "address": "0x000E3B90", "task": "prove every out-of-range slider consumer safe"},
            {"game": "NFL 2K5", "address": "0x000E3DC0", "task": "map save/profile container, integrity, and precedence"},
            {"game": "NFL 2K5", "address": "0x00589588", "task": "runtime-test copied executable draft-weight patch and signature/digest handling"},
            {"game": "APF 2K8", "address": "0x84F3FC44/0x84F3FC20", "task": "resolve computed/indexed catch consumers"},
            {"game": "APF 2K8", "address": "0x8470A630", "task": "prove all out-of-range slider consumers safe"},
            {"game": "APF 2K8", "address": "0x8471F2A0", "task": "map exact profile container/integrity/precedence"},
            {"game": "APF 2K8", "address": "0x820F4B70", "task": "resolve a CPU selector or prove retained table dead"},
            {"game": "cross-title", "address": "unresolved", "task": "map and integrate franchise state, DB, schedule, contracts, UI, and saves"},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nfl-xbe", type=Path, default=DEFAULT_NFL_XBE)
    parser.add_argument("--apf-xex", type=Path, default=DEFAULT_APF_XEX)
    parser.add_argument("--apf-pe", type=Path, default=DEFAULT_APF_PE)
    parser.add_argument("--apf-header", type=Path, default=DEFAULT_APF_HEADER)
    parser.add_argument("--nfl-ledger", type=Path, default=DEFAULT_NFL_LEDGER)
    parser.add_argument("--apf-ledger", type=Path, default=DEFAULT_APF_LEDGER)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--tsv-out", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--portme-c-out", type=Path, default=DEFAULT_PORTME)
    args = parser.parse_args()
    report = build_report(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_tsv(args.tsv_out)
    output_portme(args.portme_c_out)
    print(f"GAMEPLAY_TUNING_AI_DRAFT_AUDIT_OK sliders=21 draft_weights=17 nfl_owner=true apf_owner=false json={args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
