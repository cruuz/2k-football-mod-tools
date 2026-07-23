#!/usr/bin/env python3
"""Generate the evidence-bounded APF menu-label/cold-route v3 report.

The tool consumes an unpatched APF PE memory image and read-only Ghidra
transcripts.  It does not execute the title, patch the executable, or modify a
Ghidra project.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


SCHEMA = "vc_apf_menu_label_renderer/v3"
APF_BASE = 0x82000000
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
BASE_REPORT_SHA256 = "1145accb0a91cc0137cbf3757a0bff9d6a85a00a55ed41efa891e2a267c7788a"
BASE_TRACE_SHA256 = "ecd93117a3a808a16697c23ae10e3225953bcb4dabda30afabdc5c02911974f1"


class ReportError(RuntimeError):
    pass


def hx(value: int) -> str:
    return f"0x{value:08X}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ReportError(f"{label}: expected {expected!r}, got {actual!r}")


class Image:
    def __init__(self, data: bytes):
        self.data = data

    def offset(self, address: int, size: int = 1) -> int:
        offset = address - APF_BASE
        if offset < 0 or offset + size > len(self.data):
            raise ReportError(f"APF address {hx(address)} (+{size}) is outside the PE image")
        return offset

    def read(self, address: int, size: int) -> bytes:
        offset = self.offset(address, size)
        return self.data[offset : offset + size]

    def u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def utf16(self, address: int, limit: int = 256) -> str:
        value = bytearray()
        for index in range(limit):
            unit = self.read(address + index * 2, 2)
            if unit == b"\0\0":
                return value.decode("utf-16-be")
            value.extend(unit)
        raise ReportError(f"unterminated UTF-16BE at {hx(address)}")

    def branch(self, address: int) -> tuple[int, bool]:
        word = self.u32(address)
        if word >> 26 != 18:
            raise ReportError(f"word at {hx(address)} is not an immediate PPC branch: {word:08X}")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = displacement if word & 2 else address + displacement
        return target & 0xFFFFFFFF, bool(word & 1)


def edge(image: Image, site: int, target: int, link: bool = True) -> dict[str, str]:
    actual_target, actual_link = image.branch(site)
    expect(actual_target, target, f"branch target at {hx(site)}")
    expect(actual_link, link, f"branch link bit at {hx(site)}")
    return {
        "site": hx(site),
        "target": hx(target),
        "kind": "call" if link else "jump",
    }


def direct_sites(image: Image, start: int, end: int, wanted: int) -> list[str]:
    sites: list[str] = []
    for address in range(start, end, 4):
        word = image.u32(address)
        if word >> 26 != 18 or not (word & 1):
            continue
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = (displacement if word & 2 else address + displacement) & 0xFFFFFFFF
        if target == wanted:
            sites.append(hx(address))
    return sites


def boundary(
    image: Image,
    name: str,
    address: int,
    end: int,
    pdata_slot: int,
    metadata: int,
    saved_body: str,
) -> dict[str, Any]:
    expect(image.u32(pdata_slot), address, f"PDATA address at {hx(pdata_slot)}")
    expect(image.u32(pdata_slot + 4), metadata, f"PDATA metadata at {hx(pdata_slot + 4)}")
    encoded_word_count = (metadata >> 8) & 0xFFFF
    expect(address + encoded_word_count * 4, end, f"PDATA extent for {name}")
    blob = image.read(address, end - address)
    return {
        "name": name,
        "address": hx(address),
        "end_exclusive": hx(end),
        "extent_size": len(blob),
        "extent_sha256": digest(blob),
        "pdata_slot": hx(pdata_slot),
        "pdata_metadata": hx(metadata),
        "pdata_encoded_word_count": encoded_word_count,
        "saved_ghidra_body": saved_body,
        "status": "exact PDATA-encoded extent; embedded jump tables remain data",
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


def r4_uses(instructions: dict[int, str], start: int, end: int) -> list[dict[str, str]]:
    return [
        {"address": hx(address), "instruction": instruction}
        for address, instruction in sorted(instructions.items())
        if start <= address < end and re.search(r"\br4\b", instruction)
    ]


def decode_rows(image: Image, start: int, count: int) -> list[dict[str, Any]]:
    result = []
    for index in range(count):
        address = start + index * 0x60
        label_pointer = image.u32(address + 4)
        result.append(
            {
                "index": index,
                "source_row": hx(address),
                "type": image.u32(address),
                "label_pointer": hx(label_pointer),
                "label": image.utf16(label_pointer),
                "target_descriptor": hx(image.u32(address + 8))
                if image.u32(address + 8)
                else None,
                "callback_34": hx(image.u32(address + 0x34))
                if image.u32(address + 0x34)
                else None,
                "callback_38": hx(image.u32(address + 0x38))
                if image.u32(address + 0x38)
                else None,
                "callback_44": hx(image.u32(address + 0x44))
                if image.u32(address + 0x44)
                else None,
                "preflight_48": hx(image.u32(address + 0x48))
                if image.u32(address + 0x48)
                else None,
                "runtime_tail": hx(address + 0x50),
                "runtime_label_field": hx(address + 0x58),
            }
        )
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    xex = args.apf_xex.read_bytes()
    pe_data = args.apf_pe.read_bytes()
    trace_data = args.trace.read_bytes()
    pseudo_data = args.pseudo.read_bytes()
    base_data = args.base_report.read_bytes()
    base_trace_data = args.base_trace.read_bytes()
    expect(digest(xex), APF_XEX_SHA256, "APF XEX SHA-256")
    expect(digest(pe_data), APF_PE_SHA256, "APF PE SHA-256")
    expect(digest(base_data), BASE_REPORT_SHA256, "v2 report SHA-256")
    expect(digest(base_trace_data), BASE_TRACE_SHA256, "v1 state trace SHA-256")
    base = json.loads(base_data)
    base_trace = json.loads(base_trace_data)
    expect(base["schema"], "vc_menu_state_trace_closure/v2", "v2 schema")
    expect(base_trace["schema"], "vc_menu_state_trace/v1", "v1 state trace schema")

    trace = trace_data.decode("utf-8")
    pseudo = pseudo_data.decode("utf-8")
    for marker in (
        "APF 2K8 menu-label renderer read-only v3 trace",
        "RANGE 0x846F2748..0x846F2977",
        "RANGE 0x846F2E00..0x846F308F",
        "RANGE 0x846F3568..0x846F3E3F",
        "RANGE 0x846F4988..0x846F4A6B",
        "RANGE 0x846F5198..0x846F52B3",
        "RANGE 0x846F9090..0x846F935F",
        "RANGE 0x84693478..0x84693537",
        "RANGE 0x84A352B0..0x84A35367",
        "RANGE 0x84B646C0..0x84B6477F",
        "RANGE 0x84B65B00..0x84B65B6F",
        "POST_DISASSEMBLY_REFERENCES",
    ):
        if marker not in trace:
            raise ReportError(f"Ghidra trace is missing marker {marker!r}")
    if "Saved-boundary APF menu-label pseudo-C" not in pseudo:
        raise ReportError("unexpected Ghidra pseudo-C provenance")

    image = Image(pe_data)
    boundaries = [
        boundary(image, "generic descriptor event callback", 0x846F2748, 0x846F2974, 0x844E0F90, 0x40008B05, "complete instruction body; jump table excluded from saved body"),
        boundary(image, "Main Menu descriptor event callback", 0x846F2E00, 0x846F308C, 0x844E0FA8, 0x4000A303, "0x846F2E00..0x846F2E07 only"),
        boundary(image, "shared event-side-effect helper", 0x846F3090, 0x846F3258, 0x844E0FB0, 0x40007203, "0x846F3090..0x846F3097 only"),
        boundary(image, "visible-ordinal to physical-row mapper", 0x846F35E8, 0x846F3668, 0x844E0FD8, 0x40002003, "0x846F35E8..0x846F35EF only"),
        boundary(image, "visible-ordinal runtime-row lookup", 0x846F3798, 0x846F37F0, 0x844E0FF0, 0x40001605, "no saved Ghidra function boundary; exact instruction extent"),
        boundary(image, "row callback pass", 0x846F4028, 0x846F40B4, 0x844E1050, 0x40002303, "0x846F4028..0x846F402F only"),
        boundary(image, "row materializer", 0x846F40B8, 0x846F4168, 0x844E1058, 0x40002C03, "0x846F40B8..0x846F40BF only"),
        boundary(image, "generic direct label-copy provider", 0x846F4988, 0x846F4A6C, 0x844E10A8, 0x40003903, "0x846F4988..0x846F498F only"),
        boundary(image, "template_quicknav option label provider", 0x846F5198, 0x846F52B4, 0x844E10D8, 0x40004703, "0x846F5198..0x846F519F only"),
        boundary(image, "generic row cache/widget constructor", 0x846F62E8, 0x846F64D4, 0x844E1168, 0x40007B04, "complete saved instruction body through 0x846F64D3"),
        boundary(image, "generic widget binding", 0x846F6618, 0x846F69D0, 0x844E1188, 0x4000EE06, "complete saved instruction body"),
        boundary(image, "generic widget render callback", 0x846F69D0, 0x846F6C34, 0x844E1190, 0x40009904, "complete saved instruction body through 0x846F6C33"),
        boundary(image, "framework event dispatcher", 0x846F9090, 0x846F9360, 0x844E1240, 0x4000B403, "0x846F9090..0x846F9097 only"),
        boundary(image, "normal run finalizer", 0x846933C0, 0x84693478, 0x844DE330, 0x40002E04, "complete saved instruction body"),
        boundary(image, "colored run finalizer", 0x84693478, 0x84693538, 0x844DE338, 0x40003003, "0x84693478..0x8469347F only"),
        boundary(image, "game-specific direct label-copy provider", 0x84A352B0, 0x84A35368, 0x844F35F8, 0x40002E03, "0x84A352B0..0x84A352B7 only"),
        boundary(image, "bounded UTF-16 formatting wrapper", 0x84B65B00, 0x84B65B70, 0x844FAC20, 0x40001C05, "complete saved instruction body"),
    ]

    main_words = [image.u32(0x820F4350 + index * 4) for index in range(18)]
    expect(main_words[0], 0x8460C04C, "Main title pointer")
    expect(main_words[3], 0x846F2E00, "Main default callback")
    expect(main_words[7], 0x84E57340, "Main row base")
    expect(main_words[15], 7, "Main row count")
    expect(image.utf16(main_words[0]), "Main Menu", "Main title")
    main_rows = decode_rows(image, main_words[7], main_words[15])
    expect([row["label"] for row in main_rows], [
        "Quick Game", "Teams", "Season", "Practice", "Options", "Features", "Xbox Live"
    ], "Main labels")
    expect([row["callback_38"] for row in main_rows], [None] * 7, "Main source +0x38 callbacks")

    traced_main = base_trace["apf2k8"]["state_descriptor"]
    expect(traced_main["address"], "0x820F4350", "v1 Main descriptor")
    expect(traced_main["loaded_layout_name"], "quicknav", "v1 Main loaded layout")
    child = base_trace["apf2k8"]["state_loaded_child_entry"]
    expect(child["platform"], "apf2k8", "v1 child platform")
    expect(child["archive_name"], "global.iff", "v1 child archive")
    expect(child["outer_index"], 1310, "v1 child outer index")
    expect(child["inner_index"], 223, "v1 child inner index")
    expect(child["layout_name"], "template_quicknav", "v1 child layout")
    expect(child["record_count"], 33, "v1 child record count")
    option_records = [
        record for record in child["records"]
        if record["type"] == 0 and
        (record["primary_name"] or "").startswith("quicknav_option")
    ]
    expected_option_ids = [
        0xC22FED9A, 0x5B26BC20, 0x2C218CB6, 0xB2451915,
        0xC5422983, 0x5C4B7839, 0x2B4C48AF, 0xBBF3553E,
    ]
    expect([record["index"] for record in option_records], list(range(5, 13)),
           "template_quicknav option record indexes")
    expect([int(record["id_or_hash"], 16) for record in option_records],
           expected_option_ids, "template_quicknav option IDs")

    timeline = base["apf2k8"]["template_quicknav_timeline"]
    config = timeline["template_config"]
    expect(config["address"], "0x84D30458", "v2 quicknav config address")
    expect(config["auxiliary_table"], "0x84D30400", "v2 quicknav auxiliary table")
    expect(config["template_name"], "template_quicknav", "v2 quicknav template name")
    expect([image.u32(0x84D30458 + index * 4) for index in range(5)],
           [8, 0x84521154, 0x84D30400, 0x846F4E38, 0x846F5058],
           "template_quicknav static config")
    expect(image.utf16(0x84521154), "template_quicknav", "quicknav config name")
    expect(image.u32(0x84D30400), 0x84D302C8, "quicknav auxiliary table base")

    option_bindings = []
    for slot, (record, record_id) in enumerate(zip(option_records, expected_option_ids)):
        address = 0x84D30328 + slot * 0x18
        words = [image.u32(address + index * 4) for index in range(6)]
        expect(words, [record_id, record_id, 0x846F5198, slot, 0, 0],
               f"quicknav option binding {slot}")
        option_bindings.append({
            "slot": slot,
            "layout_record_index": record["index"],
            "layout_record_id": hx(record_id),
            "layout_record_name": record["primary_name"],
            "binding_address": hx(address),
            "content_provider": "0x846F5198",
        })

    instructions = parse_trace_instructions(trace)
    normal_r4 = r4_uses(instructions, 0x846933C0, 0x84693478)
    colored_r4 = r4_uses(instructions, 0x84693478, 0x84693538)
    expect(normal_r4, [
        {"address": "0x846933E8", "instruction": "addi r4,r11,0x2ec0"},
        {"address": "0x846933F8", "instruction": "addi r4,r31,0xa8"},
        {"address": "0x84693438", "instruction": "addi r4,r11,0x2ec0"},
        {"address": "0x84693448", "instruction": "addi r4,r1,0x50"},
    ], "normal finalizer r4 audit")
    expect(colored_r4, [
        {"address": "0x846934A4", "instruction": "or r4,r30,r30"},
        {"address": "0x846934B4", "instruction": "or r4,r29,r29"},
        {"address": "0x846934C0", "instruction": "addi r4,r31,0xa8"},
        {"address": "0x846934F8", "instruction": "or r4,r30,r30"},
        {"address": "0x84693508", "instruction": "or r4,r29,r29"},
        {"address": "0x84693514", "instruction": "addi r4,r1,0x50"},
    ], "colored finalizer r4 audit")

    accessor_sites = direct_sites(image, 0x84600000, 0x84BE0000, 0x846F0708)
    expect(accessor_sites, [
        "0x846F35A4", "0x846F361C", "0x846F3698", "0x846F3764",
        "0x846F37D4", "0x846F3820", "0x846F3878", "0x846F3A88",
        "0x846F3D00", "0x846F3E24", "0x846F4078", "0x846F40F8",
        "0x846F6354", "0x846F66A8", "0x846F6718", "0x846F6800",
        "0x846F684C", "0x846F68C4",
    ], "direct runtime-row accessor calls in APF code")
    accessor_uses = [
        {"site": "0x846F35A4", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F361C", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F3698", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F3764", "immediate_use": "returned to caller"},
        {"site": "0x846F37D4", "immediate_use": "returned to caller"},
        {"site": "0x846F3820", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F3878", "immediate_use": "returned to caller"},
        {"site": "0x846F3A88", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F3D00", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F3E24", "immediate_use": "returned to caller"},
        {"site": "0x846F4078", "immediate_use": "passed to optional source +0x38 callback; all Main +0x38 fields are zero"},
        {"site": "0x846F40F8", "immediate_use": "16-byte runtime tail clear/materialization"},
        {"site": "0x846F6354", "immediate_use": "generic 16-byte runtime tail clear/materialization"},
        {"site": "0x846F66A8", "immediate_use": "passed to optional source +0x38 callback in generic widget path"},
        {"site": "0x846F6718", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F6800", "immediate_use": "runtime +0x0C flag"},
        {"site": "0x846F684C", "immediate_use": "stored as first widget +0x2C user data"},
        {"site": "0x846F68C4", "immediate_use": "stored as second widget +0x2C user data"},
    ]
    # Pin the instruction immediately after every call so the classification cannot
    # silently drift with a different executable or transcript.
    expected_after_accessor = {
        0x846F35A8: 0x8163000C, 0x846F3620: 0x8163000C,
        0x846F369C: 0x8163000C, 0x846F3768: 0x38210060,
        0x846F37D8: 0x38210070, 0x846F3824: 0x8163000C,
        0x846F387C: 0x38210080, 0x846F3A8C: 0x8163000C,
        0x846F3D04: 0x8163000C, 0x846F3E28: 0x38210070,
        0x846F407C: 0x7C641B78, 0x846F40FC: 0x39630010,
        0x846F6358: 0x90610058, 0x846F66AC: 0x7C7F1B78,
        0x846F671C: 0x8163000C, 0x846F6804: 0x8163000C,
        0x846F6850: 0x7C641B78, 0x846F68C8: 0x7C641B78,
    }
    for address, word in expected_after_accessor.items():
        expect(image.u32(address), word, f"post-accessor instruction at {hx(address)}")

    # Ghidra's saved project has no function boundary or pre-existing reference for
    # this two-instruction leaf.  Whole-image branch decoding plus transient
    # read-only disassembly recovers every direct caller.
    expect(image.u32(0x846F3888), 0x80630008, "runtime-label getter load")
    expect(image.u32(0x846F388C), 0x4E800020, "runtime-label getter return")
    getter_sites = direct_sites(image, 0x84600000, 0x84BE0000, 0x846F3888)
    expect(getter_sites,
           ["0x846F4A50", "0x846F524C", "0x846F5298", "0x84A3534C"],
           "runtime-label getter direct callers")
    getter_blob = image.read(0x846F3888, 8)

    # Exact quicknav provider instructions.  The selected row is formatted with
    # the literal "{0}|M_PRIMARY|"; all other rows use a bounded direct copy.
    expect(image.utf16(0x845210B8), "{0}|M_PRIMARY|", "selected-row format")
    for address, word in {
        0x846F51B0: 0x815F0004,
        0x846F51B8: 0x807F0018,
        0x846F51C8: 0x7FC4F378,
        0x846F51D4: 0x7F85E378,
        0x846F51DC: 0x7C7D1B78,
        0x846F5240: 0x7FA3EB78,
        0x846F5254: 0x90610050,
        0x846F5260: 0x38AB10B8,
        0x846F5264: 0x807F0010,
        0x846F526C: 0x38C10054,
        0x846F5270: 0x91410058,
        0x846F5274: 0x91610060,
        0x846F527C: 0x9161005C,
        0x846F5280: 0x91610054,
        0x846F5294: 0x83DF0014,
        0x846F529C: 0x7C641B78,
        0x846F52A0: 0x7FC5F378,
        0x846F52A4: 0x807F0010,
    }.items():
        expect(image.u32(address), word, f"quicknav label provider instruction at {hx(address)}")

    # Exact instruction anchors for the generic label-buffer path.
    for address, word in {
        0x846F6B50: 0x3D4062FD,
        0x846F6B54: 0x614AD7D8,
        0x846F6B64: 0x3D40966B,
        0x846F6B68: 0x614AC1A3,
        0x846F6B78: 0x3D40AFF8,
        0x846F6B7C: 0x614A5D42,
        0x846F6B8C: 0x38A00040,
        0x846F6B90: 0x81610460,
        0x846F6B94: 0x808B0008,
        0x846F6B98: 0x386103E0,
        0x846F6BA0: 0x81610460,
        0x846F6BA4: 0x816B000C,
        0x846F6BF0: 0x388103E0,
        0x846F6BF4: 0x38610320,
        0x846F6C00: 0x388103E0,
        0x846F6C04: 0x38610320,
    }.items():
        expect(image.u32(address), word, f"generic label instruction at {hx(address)}")

    expect(direct_sites(image, 0x846F2E00, 0x846F3090, 0x846F62E8), [], "Main callback -> generic constructor")
    expect(direct_sites(image, 0x846F2E00, 0x846F3090, 0x846F6618), [], "Main callback -> generic widget binder")
    expect(direct_sites(image, 0x846F2E00, 0x846F3090, 0x846F69D0), [], "Main callback -> generic render callback")
    expect(direct_sites(image, 0x846F2748, 0x846F2978, 0x846F62E8), ["0x846F2884"], "generic callback -> constructor")
    expect(direct_sites(image, 0x846F62E8, 0x846F64D8, 0x846F6618), ["0x846F64BC"], "constructor -> widget binder")

    expect(image.u32(0x846F92B0), 0x816B000C, "dispatcher callback load")
    expect(image.u32(0x846F92C8), 0x4E800421, "dispatcher callback bctrl")
    expect(image.u32(0x846F685C), 0x3D60846F, "generic callback pointer high")
    expect(image.u32(0x846F6860), 0x388B69D0, "generic callback pointer low")

    copy_edges = [
        edge(image, 0x846F6B9C, 0x84B43498),
        edge(image, 0x846F6BF8, 0x84693478),
        edge(image, 0x846F6C08, 0x846933C0),
    ]
    runtime_lookup_edges = [
        edge(image, 0x846F37B0, 0x846F35E8),
        edge(image, 0x846F37CC, 0x846F89C8),
        edge(image, 0x846F37D4, 0x846F0708),
    ]
    quicknav_provider_edges = [
        edge(image, 0x846F51A8, 0x846F4270),
        edge(image, 0x846F51D8, 0x846F3798),
        edge(image, 0x846F524C, 0x846F3888),
        edge(image, 0x846F5284, 0x84B65B00),
        edge(image, 0x846F5298, 0x846F3888),
        edge(image, 0x846F52A8, 0x84B43498),
    ]
    corroborating_provider_edges = {
        "generic_direct_copy": [
            edge(image, 0x846F4A04, 0x846F3798),
            edge(image, 0x846F4A50, 0x846F3888),
            edge(image, 0x846F4A60, 0x84B43498),
        ],
        "game_specific_direct_copy": [
            edge(image, 0x84A3530C, 0x846F3798),
            edge(image, 0x84A3534C, 0x846F3888),
            edge(image, 0x84A3535C, 0x84B43498),
        ],
    }
    main_event_edges = [
        edge(image, 0x846F2E28, 0x846F3090),
        edge(image, 0x846F2F20, 0x846F1778),
        edge(image, 0x846F2F28, 0x846F18A0),
        edge(image, 0x846F2F40, 0x846F55E8),
        edge(image, 0x846F5600, 0x846F89C8),
        edge(image, 0x846F5608, 0x846F4270),
        edge(image, 0x846F5618, 0x846F40B8),
        edge(image, 0x846F40E8, 0x846F06F0),
        edge(image, 0x846F40F8, 0x846F0708),
        edge(image, 0x846F415C, 0x846F4028),
    ]
    generic_edges = [
        edge(image, 0x846F2884, 0x846F62E8),
        edge(image, 0x846F64BC, 0x846F6618),
        edge(image, 0x846F684C, 0x846F0708),
        edge(image, 0x846F6858, 0x846FB3A0),
        edge(image, 0x846F6868, 0x846FB390),
        edge(image, 0x846F68C4, 0x846F0708),
        edge(image, 0x846F68D0, 0x846FB3A0),
    ]

    end_descriptor = [image.u32(0x820F4800 + index * 4) for index in range(18)]
    expect(image.utf16(end_descriptor[0]), "End Of Game", "End Of Game title")
    expect(image.utf16(end_descriptor[1]), "SlideOnNav_PauseMenu_EndOfGame", "End Of Game transition")
    expect(end_descriptor[3], 0x846F2E00, "End Of Game default callback")
    expect(end_descriptor[7], 0x84E588C0, "End Of Game row base")
    expect(end_descriptor[15], 6, "End Of Game row count")
    end_rows = decode_rows(image, end_descriptor[7], end_descriptor[15])
    quit_row = end_rows[5]
    expect(quit_row["label"], "Quit", "End Of Game final row label")
    expect(quit_row["type"], 10, "End Of Game final row type")
    expect(quit_row["preflight_48"], "0x84A58698", "End Of Game Quit preflight")
    expect(image.u32(0x84A586B0), 0x3D60820F, "return-to-Main descriptor high")
    expect(image.u32(0x84A586B8), 0x38AB4350, "return-to-Main descriptor low")
    boot_edges = [
        edge(image, 0x84A586AC, 0x84A56B00),
        edge(image, 0x84A586C0, 0x846F45E0),
    ]

    portme = [
        {
            "platform": "apf2k8",
            "address": "0x846F5198",
            "reason": "Ghidra's saved boundary stops at 0x846F519F; reconstruct a complete structured pseudo-C function from the exact 0x846F5198..0x846F52B3 PDATA extent even though its label-provider semantics are proved",
        },
        {
            "platform": "apf2k8",
            "address": "0x846EF1D0",
            "reason": "follow the template_quicknav option output buffer from the type-0 record draw path through final font selection, glyph layout, and GPU submission",
        },
        {
            "platform": "apf2k8",
            "address": "0x820F4350",
            "reason": "determine whether another locale/build replaces the seven source literals before materialization; the proved US content-provider chain itself performs no localization lookup",
        },
        {
            "platform": "apf2k8",
            "address": "0x84BE9D08",
            "reason": "trace a cold-boot path from the title entry/current-state initializer to 0x820F4350; 0x84A58698 is now rejected as the End Of Game Quit preflight callback",
        },
    ]

    report = {
        "schema": SCHEMA,
        "scope": {
            "analysis": "static unpatched APF binary plus read-only Ghidra evidence",
            "launches_original_menu": False,
            "writes_executable": False,
            "writes_ghidra_project": False,
            "main_label_content_provider_proved": True,
            "main_visible_label_renderer_proved": False,
            "final_glyph_renderer_proved": False,
            "main_provider_localization_bypass_proved": True,
            "localization_policy_proved": False,
            "cold_boot_predecessor_proved": False,
        },
        "provenance": {
            "apf_xex": {"path": "extracted/All-Pro Football 2K8 (USA)/default.xex", "sha256": digest(xex)},
            "apf_unpatched_pe": {"path": "derived by tools/xex_extract_pe.cpp", "sha256": digest(pe_data)},
            "v2_report": {"path": "reports/assets/menu_state_trace_closure_v2.json", "sha256": digest(base_data)},
            "v1_state_trace": {"path": "reports/assets/menu_state_trace.json", "sha256": digest(base_trace_data)},
            "ghidra_trace": {"path": "reports/assets/menu_label_renderer_v3_ghidra/apf_menu_label_renderer_v3_trace.txt", "sha256": digest(trace_data)},
            "ghidra_pseudo_c": {"path": "reports/assets/menu_label_renderer_v3_ghidra/apf_menu_label_renderer_v3_pseudo_c.c", "sha256": digest(pseudo_data)},
        },
        "recovered_boundaries": boundaries,
        "main_label_ownership": {
            "descriptor": {
                "address": "0x820F4350",
                "title": "Main Menu",
                "default_callback_field": "+0x0C",
                "default_callback": "0x846F2E00",
                "event_action_table_field": "+0x08",
                "event_action_table": None,
                "row_base": "0x84E57340",
                "row_count": 7,
            },
            "rows": main_rows,
            "event_dispatch": {
                "dispatcher": "0x846F9090",
                "callback_load": "0x846F92B0: lwz r11,0x0C(r11)",
                "callback_call": "0x846F92C8: bctrl",
                "event_3_edges": main_event_edges,
            },
            "row_callback_pass": {
                "function": "0x846F4028",
                "source_callback_field": "+0x38",
                "all_main_source_callback_fields_zero": True,
            },
            "runtime_row_accessor_audit": {
                "accessor": "0x846F0708",
                "direct_call_count_in_apf_code": len(accessor_sites),
                "direct_calls": accessor_uses,
                "result": "no direct call immediately loads runtime +0x08; the recovered provider instead calls wrapper 0x846F3798, then leaf 0x846F3888 reads +0x08",
            },
            "loaded_layout_join": {
                "descriptor_loaded_layout": traced_main["loaded_layout_name"],
                "loaded_child": {
                    "archive": child["archive_name"],
                    "outer_index": child["outer_index"],
                    "inner_index": child["inner_index"],
                    "layout_name": child["layout_name"],
                    "record_count": child["record_count"],
                },
                "static_template_config": {
                    "address": "0x84D30458",
                    "template_name_pointer": "0x84521154",
                    "template_name": "template_quicknav",
                    "auxiliary_table": "0x84D30400",
                    "auxiliary_entry_base": "0x84D302C8",
                },
                "option_bindings": option_bindings,
                "result": "all eight template_quicknav type-0 quicknav_option records are exactly bound to content provider 0x846F5198; Main loads quicknav and its template_quicknav child",
            },
            "runtime_label_provider": {
                "function": "0x846F5198",
                "pdata_extent": "0x846F5198..0x846F52B3",
                "runtime_lookup": {
                    "function": "0x846F3798",
                    "semantics": "maps a visible ordinal through 0x846F35E8, obtains the active descriptor through 0x846F89C8, and returns its runtime row through 0x846F0708",
                    "edges": runtime_lookup_edges,
                },
                "label_getter": {
                    "address": "0x846F3888",
                    "end_exclusive": "0x846F3890",
                    "sha256": digest(getter_blob),
                    "pdata_entry": False,
                    "saved_ghidra_function": False,
                    "semantics": "lwz r3,+0x08(r3); blr",
                    "all_direct_callers_in_apf_code": getter_sites,
                },
                "provider_edges": quicknav_provider_edges,
                "selected_row_output": {
                    "label_getter_call": "0x846F524C",
                    "format_pointer": "0x845210B8",
                    "format": "{0}|M_PRIMARY|",
                    "formatter_call": "0x846F5284 -> 0x84B65B00",
                    "argument_writer": "0x84B646C0",
                    "destination": "callback object +0x10",
                    "capacity": "callback object +0x14",
                },
                "ordinary_row_output": {
                    "label_getter_call": "0x846F5298",
                    "copy_call": "0x846F52A8 -> 0x84B43498",
                    "copy_semantics": "bounded UTF-16 copy with NUL termination",
                    "destination": "callback object +0x10",
                    "capacity": "callback object +0x14",
                },
                "corroborating_non_main_callers": corroborating_provider_edges,
                "result": "proved Main-loaded template option content provider: it obtains the active runtime row, reads runtime +0x08, and emits the literal label to the layout callback's bounded output buffer, adding M_PRIMARY markup only for the selected row",
            },
            "provider_localization_boundary": {
                "source": "seven direct UTF-16BE US literals in source-row +0x04",
                "materialization": "0x846F4144 copies source +0x04 directly to runtime +0x08",
                "provider_read": "0x846F3888 returns runtime +0x08 directly",
                "provider_output": "0x846F5198 either formats {0}|M_PRIMARY| or performs a bounded direct copy",
                "resolver_calls_in_proved_chain": [],
                "result": "localization bypass is proved at the US Main content-provider boundary; global policy and alternate-locale source replacement remain unproved",
            },
            "generic_widget_path_direct_calls_from_main_callback": {
                "0x846F62E8": [],
                "0x846F6618": [],
                "0x846F69D0": [],
            },
            "status": "Main copies seven direct literals to runtime +0x08 and its loaded template_quicknav option records bind 0x846F5198, which emits those labels into bounded layout output buffers; final glyph rendering remains unproved",
        },
        "generic_label_path_rejected_for_main": {
            "owner_callback": "0x846F2748",
            "owner_relation": "a different generic descriptor callback; Main descriptor +0x0C is 0x846F2E00",
            "edges": generic_edges,
            "widget_user_data": "0x846F6858 and 0x846F68D0 store the runtime row at widget +0x2C",
            "widget_render_callback": "0x846F6860 constructs 0x846F69D0; 0x846F6868 stores it",
            "runtime_label_read": "0x846F6B94 loads runtime row +0x08 into r4",
            "copy_helper": {
                "edge": copy_edges[0],
                "destination": "64-code-unit stack buffer at caller stack +0x3E0",
                "semantics": "bounded UTF-16 copy with NUL termination",
                "eligible_run_ids": ["0x62FDD7D8", "0x966BC1A3", "0xAFF85D42"],
            },
            "finalizer_edges": copy_edges[1:],
            "incoming_string_argument_audit": {
                "abi_register": "r4",
                "normal_0x846933C0_r4_mentions": normal_r4,
                "colored_0x84693478_r4_mentions": colored_r4,
                "result": "after each function's compiler prologue, incoming r4 is never read; every listed r4 instruction overwrites r4 from another register/stack address before a call",
            },
            "status": "this separate 0x846F2748-owned path also reads runtime +0x08, but its local copy buffer is ignored by both audited finalizers; it is not the Main template_quicknav provider",
        },
        "cold_boot_candidate_rejection": {
            "candidate": "0x84A58698",
            "static_owner_descriptor": {
                "address": "0x820F4800",
                "title": "End Of Game",
                "transition_name": "SlideOnNav_PauseMenu_EndOfGame",
                "row_base": "0x84E588C0",
                "row_count": 6,
            },
            "owner_rows": end_rows,
            "exact_owner": {
                "source_row": "0x84E58AA0",
                "row_index": 5,
                "row_type": 10,
                "label": "Quit",
                "field": "+0x48 preflight callback",
            },
            "edges": boot_edges,
            "target_descriptor": "0x820F4350",
            "result": "proved End Of Game/Quit return-to-Main route; definitively not a cold-boot predecessor",
        },
        "negative_findings": [
            "Main event 3 has no direct edge to the generic widget constructor, binder, or 0x846F69D0 callback",
            "all seven Main source +0x38 per-row callback fields are zero",
            "all 18 direct code calls to runtime-row accessor 0x846F0708 were audited; none immediately reads +0x08, because the proved provider obtains rows through wrapper 0x846F3798",
            "the generic runtime-label copy buffer is not read by either proved run finalizer body",
            "no final text layout, font selection, glyph generation, or GPU submission edge is proved below the template output buffer",
            "no localization resolver occurs inside the proved US Main source-to-provider chain; alternate-locale source replacement remains unproved",
            "0x84A58698 is owned by End Of Game row 5 ('Quit'), not cold boot",
            "no original retail menu was launched",
        ],
        "portme": portme,
    }
    return report


def write_tsv(report: dict[str, Any], path: Path) -> None:
    rows = [
        ("main", "proved", "0x846F40B8", "seven direct label pointers copied from source +0x04 to runtime +0x08"),
        ("main", "proved", "0x84D30328", "eight template_quicknav option IDs bind content provider 0x846F5198 with slot indexes 0..7"),
        ("main", "proved", "0x846F5198", "active runtime row -> orphan +0x08 getter -> bounded layout output; selected row uses {0}|M_PRIMARY|"),
        ("main", "proved", "0x846F3888", "orphan leaf is exactly lwz r3,+0x08(r3); blr; four direct callers recovered"),
        ("main", "partial", "0x846EF1D0", "final font/glyph/GPU consumer below the type-0 layout output remains unproved"),
        ("main", "proved", "0x820F4350", "US source-to-provider chain has no localization resolver; alternate-locale source policy unproved"),
        ("main", "negative", "0x846F2E00", "no direct call to 0x846F62E8/0x846F6618/0x846F69D0"),
        ("main", "negative", "0x84E57340", "all seven source +0x38 callbacks are zero"),
        ("generic", "proved", "0x846F2748", "event 3 alone reaches generic constructor 0x846F62E8 at 0x846F2884"),
        ("generic", "proved", "0x846F6618", "runtime rows stored as widget +0x2C and callback 0x846F69D0 bound"),
        ("generic", "partial", "0x846F6B94", "runtime +0x08 copied to stack; both downstream finalizers ignore incoming r4"),
        ("boot", "rejected", "0x84A58698", "End Of Game row 5 Quit +0x48 preflight; not cold boot"),
        ("scope", "unproved", "0x84BE9D08", "cold-boot predecessor to Main remains PORTME"),
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("category", "status", "address", "evidence"))
        writer.writerows(rows)


def write_portme(report: dict[str, Any], path: Path) -> None:
    lines = [
        "/* Generated APF menu-label/cold-route v3 blockers; not original game source. */",
        "#include <stdint.h>",
        "",
        "void vc_apf_menu_label_renderer_v3_unresolved(void) {",
    ]
    for item in report["portme"]:
        lines.append(
            f"    // PORTME: {item['platform']} function/data at {item['address']}: {item['reason']}."
        )
    lines.extend(["    (void)(uint32_t)0;", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--base-report", type=Path, required=True)
    parser.add_argument("--base-trace", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    parser.add_argument("--portme-c-out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        report = build_report(args)
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.tsv_out.parent.mkdir(parents=True, exist_ok=True)
        args.portme_c_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_tsv(report, args.tsv_out)
        write_portme(report, args.portme_c_out)
        print(
            "APF_MENU_LABEL_RENDERER_V3_REPORT_PASS "
            f"boundaries={len(report['recovered_boundaries'])} "
            f"main_rows={len(report['main_label_ownership']['rows'])} "
            f"portme={len(report['portme'])}"
        )
        return 0
    except (OSError, ValueError, KeyError, ReportError) as error:
        print(f"APF_MENU_LABEL_RENDERER_V3_REPORT_FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
