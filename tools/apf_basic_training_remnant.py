#!/usr/bin/env python3
"""Deterministic NFL 2K5 -> APF 2K8 Basic Training remnant audit.

The audit is static and read-only.  It proves retained state/code/data lineage
and a bounded absence of ordinary external routes; it does not execute either
title or claim that APF's tutorial is retail-reachable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from menu_state_trace import APF_BASE, APF_PE_SHA256, ApfImage, XbeImage


SCHEMA = "vc_apf_basic_training_remnant/v1"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
DIRECTOR_SHA256 = "77fdc2c8a2d404f0307cd54ab494ee6e38dc4797de8e068a4661b82af391cd31"

NFL_BASIC = 0x00509710
NFL_PAUSE = 0x00509844
NFL_CRIPPLED_PAUSE = 0x00509A04
APF_BASIC = 0x820E5AE0
APF_PAUSE = 0x820E5B28
APF_CRIPPLED_PAUSE = 0x820E5BD8
APF_MODE_GLOBAL = 0x84F3F8F8

CONTINUE = "Press|CROSS|To Continue"
TITLE = "Basic Training"
WELCOME = (
    "Welcome to ESPN NFL 2K5's \"Basic Training\" mode. Here you will be put "
    "through a series of drills that will help you gain a basic understanding "
    "of how to play this game."
)
COMPLETION = (
    "Congratulations! You are a true champion! Your football skills will save "
    "us all! You're the greatest! Okay, all that might be pushing it a bit. "
    "Nevertheless, you have completed ESPN NFL 2K5's \"Basic Training\" mode "
    "and you're likely a better person because of it."
)


class AuditError(RuntimeError):
    pass


def hx(value: int) -> str:
    return f"0x{value:08X}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AuditError(f"{label}: expected {expected!r}, got {actual!r}")


def anchor(image: Any, first: int, after_last: int, name: str) -> dict[str, Any]:
    body = image.read(first, after_last - first)
    return {
        "name": name,
        "first": hx(first),
        "after_last": hx(after_last),
        "size": len(body),
        "sha256": sha256_bytes(body),
    }


def xbe_offset_to_va(header: dict[str, Any], offset: int) -> int | None:
    for section in header["sections"]:
        raw = int(section["raw_address"])
        size = int(section["raw_size"])
        if raw <= offset < raw + size:
            return int(section["virtual_address"]) + offset - raw
    return None


def pointer_sites(
    data: bytes, value: int, byteorder: str, mapper: Any
) -> list[str]:
    needle = value.to_bytes(4, byteorder)
    result: list[str] = []
    cursor = 0
    while True:
        offset = data.find(needle, cursor)
        if offset < 0:
            return result
        mapped = mapper(offset)
        result.append(hx(mapped) if mapped is not None else f"file+0x{offset:X}")
        cursor = offset + 1


def x86_edge(image: XbeImage, site: int, target: int) -> dict[str, str]:
    expect(image.u8(site), 0xE8, f"NFL call opcode at {hx(site)}")
    relative = struct.unpack("<i", image.read(site + 1, 4))[0]
    actual = (site + 5 + relative) & 0xFFFFFFFF
    expect(actual, target, f"NFL call target at {hx(site)}")
    return {"site": hx(site), "target": hx(target), "bytes": image.read(site, 5).hex()}


def ppc_edge(image: ApfImage, site: int, target: int) -> dict[str, Any]:
    actual, link = image.branch(site)
    expect(actual, target, f"APF call target at {hx(site)}")
    expect(link, True, f"APF link bit at {hx(site)}")
    return {"site": hx(site), "target": hx(target), "word": f"{image.u32(site):08X}"}


def scan_ppc_branches(image: ApfImage, target: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for site in range(0x84630000, 0x84D0904C, 4):
        word = image.u32(site)
        if word >> 26 != 18:
            continue
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        actual = (displacement if word & 2 else site + displacement) & 0xFFFFFFFF
        if actual == target:
            result.append({"site": hx(site), "link": bool(word & 1)})
    return result


def scan_ppc_materializations(image: ApfImage, target: int) -> list[dict[str, str]]:
    high = ((target + 0x8000) >> 16) & 0xFFFF
    low = target & 0xFFFF
    result: list[dict[str, str]] = []
    for site in range(0x84630000, 0x84D0904C, 4):
        first = image.u32(site)
        if first >> 26 != 15 or ((first >> 16) & 31) != 0 or (first & 0xFFFF) != high:
            continue
        register = (first >> 21) & 31
        for distance in range(1, 9):
            second_site = site + distance * 4
            second = image.u32(second_site)
            opcode = second >> 26
            if opcode == 14 and ((second >> 16) & 31) == register and (second & 0xFFFF) == low:
                result.append({"lis": hx(site), "combine": hx(second_site), "kind": "addi"})
            if opcode == 24 and ((second >> 21) & 31) == register and (second & 0xFFFF) == low:
                result.append({"lis": hx(site), "combine": hx(second_site), "kind": "ori"})
    return result


def decode_nfl_descriptor(image: XbeImage, address: int, row_count: int) -> dict[str, Any]:
    words = [image.u32(address + index * 4) for index in range(8)]
    events: list[dict[str, Any]] = []
    for index in range(16):
        event = image.u32(words[1] + index * 8)
        action = image.u32(words[1] + index * 8 + 4)
        if event == 0:
            break
        action_type = image.u32(action)
        callback_offset = 0x0C if action_type == 3 else 4
        events.append({
            "event": event,
            "action": hx(action),
            "action_type": action_type,
            "callback": hx(image.u32(action + callback_offset)),
        })
    rows: list[dict[str, Any]] = []
    for index in range(row_count):
        row = words[4] + index * 0x34
        label_pointer = image.u32(row + 4)
        target = image.u32(row + 8)
        rows.append({
            "index": index,
            "address": hx(row),
            "type": image.u32(row),
            "label": image.utf16(label_pointer),
            "target": hx(target),
            "target_title": image.utf16(image.u32(target)) if target else None,
        })
    return {
        "address": hx(address),
        "title": image.utf16(words[0]),
        "event_table": hx(words[1]),
        "default_callback": hx(words[2]),
        "layout": image.utf16(words[6]),
        "rows": rows,
        "events": events,
    }


def decode_apf_descriptor(image: ApfImage, address: int) -> dict[str, Any]:
    words = [image.u32(address + index * 4) for index in range(18)]
    events: list[dict[str, Any]] = []
    for index in range(16):
        event = image.u32(words[2] + index * 8)
        action = image.u32(words[2] + index * 8 + 4)
        if event == 0:
            break
        events.append({
            "event": event,
            "action": hx(action),
            "action_type": image.u32(action),
            "callback": hx(image.u32(action + 4)),
        })
    rows: list[dict[str, Any]] = []
    for index in range(words[15]):
        row = words[7] + index * 0x60
        label_pointer = image.u32(row + 4)
        target = image.u32(row + 8)
        rows.append({
            "index": index,
            "address": hx(row),
            "type": image.u32(row),
            "label": image.utf16(label_pointer),
            "target": hx(target),
            "target_title": image.utf16(image.u32(target)) if target else None,
        })
    return {
        "address": hx(address),
        "title": image.utf16(words[0]),
        "transition": image.utf16(words[1]),
        "event_table": hx(words[2]),
        "default_callback": hx(words[3]),
        "row_base": hx(words[7]),
        "row_count": words[15],
        "layout": image.utf16(words[11]),
        "rows": rows,
        "events": events,
    }


def conventional_mode_stores(image: ApfImage) -> list[str]:
    """Find direct stw global,-1800(base) with a nearby lis base,0x84F4."""
    result: list[str] = []
    for site in range(0x84630000, 0x84D0904C, 4):
        word = image.u32(site)
        if word >> 26 != 36 or (word & 0xFFFF) != 0xF8F8:
            continue
        base_register = (word >> 16) & 31
        found = False
        for distance in range(1, 17):
            prior = image.u32(site - distance * 4)
            if (
                prior >> 26 == 15
                and ((prior >> 16) & 31) == 0
                and ((prior >> 21) & 31) == base_register
                and (prior & 0xFFFF) == 0x84F4
            ):
                found = True
                break
        if found:
            result.append(hx(site))
    return result


def mode_store_details(image: ApfImage) -> list[dict[str, Any]]:
    """Pin the interpretation boundary of every conventionally found store."""
    expected_words = {
        0x84669748: 0x3D6084F4, 0x8466974C: 0x906BF8F8,
        0x846699D4: 0x39600005, 0x846699D8: 0x3D4084F4, 0x846699DC: 0x916AF8F8,
        0x84681E50: 0x3D604E4E, 0x84681E54: 0x3D4084F4,
        0x84681E58: 0x616B4E4E, 0x84681E5C: 0x916AF8F8,
        0x8471224C: 0x3FE084F4, 0x84712250: 0x83DFF8F8, 0x84712260: 0x93DFF8F8,
        0x849D43A8: 0x3D6084F4, 0x849D43B8: 0x39400005, 0x849D43BC: 0x914BF8F8,
        0x849DD8E0: 0x39600006, 0x849DD8E8: 0x39600008,
        0x849DD8EC: 0x3D4084F4, 0x849DD8F4: 0x916AF8F8,
        0x849FB240: 0x3D4084F4, 0x849FB244: 0x39600005, 0x849FB248: 0x916AF8F8,
        0x84A20BD4: 0x3D4084F4, 0x84A20BD8: 0x39600001, 0x84A20BDC: 0x916AF8F8,
        0x84A36C34: 0x3D4084F4, 0x84A36C3C: 0x39600009, 0x84A36C40: 0x916AF8F8,
        0x84A67CB4: 0x3D4084F4, 0x84A67CB8: 0x39600005, 0x84A67CC4: 0x916AF8F8,
    }
    for address, word in expected_words.items():
        expect(image.u32(address), word, f"APF mode-store anchor at {hx(address)}")
    return [
        {"site": hx(0x8466974C), "classification": "arbitrary_r3_setter", "fixed_value": None},
        {"site": hx(0x846699DC), "classification": "fixed_immediate", "fixed_value": 5},
        {"site": hx(0x84681E5C), "classification": "initialization_sentinel", "fixed_value": hx(0x4E4E4E4E)},
        {"site": hx(0x84712260), "classification": "preserve_prior_value", "fixed_value": None},
        {"site": hx(0x849D43BC), "classification": "clamp_to_fixed_immediate", "fixed_value": 5},
        {"site": hx(0x849DD8F4), "classification": "computed_branch_values_include_6_7_8", "fixed_value": None},
        {"site": hx(0x849FB248), "classification": "fixed_immediate", "fixed_value": 5},
        {"site": hx(0x84A20BDC), "classification": "fixed_immediate", "fixed_value": 1},
        {"site": hx(0x84A36C40), "classification": "fixed_immediate", "fixed_value": 9},
        {"site": hx(0x84A67CC4), "classification": "fixed_immediate", "fixed_value": 5},
    ]


def decode_nfl(data: bytes, header: dict[str, Any]) -> dict[str, Any]:
    image = XbeImage(data, header)
    strings = {
        "continue": {"address": hx(0x00E73010), "text": image.utf16(0x00E73010, 64)},
        "completion": {"address": hx(0x00E73040), "text": image.utf16(0x00E73040, 512)},
        "title": {"address": hx(0x00E73250), "text": image.utf16(0x00E73250, 64)},
        "welcome": {"address": hx(0x00E73270), "text": image.utf16(0x00E73270, 512)},
    }
    expect([strings[key]["text"] for key in ("continue", "completion", "title", "welcome")],
           [CONTINUE, COMPLETION, TITLE, WELCOME], "NFL Basic Training strings")
    basic = decode_nfl_descriptor(image, NFL_BASIC, 0)
    pause = decode_nfl_descriptor(image, NFL_PAUSE, 4)
    crippled = decode_nfl_descriptor(image, NFL_CRIPPLED_PAUSE, 2)
    expect(basic["title"], TITLE, "NFL basic title")
    expect(basic["layout"], "spreadsheet", "NFL basic layout")
    expect([row["event"] for row in basic["events"]], [4, 6, 7, 11, 12, 1], "NFL basic events")
    expect([row["label"] for row in pause["rows"]], ["Resume", "Restart", "Tutorial Menu", "Quit"], "NFL pause rows")
    expect([row["label"] for row in crippled["rows"]], ["Tutorial Menu", "Quit"], "NFL crippled rows")
    expect(image.read(0x0011EB49, 7).hex(), "833d80ffe50003", "NFL mode-3 gate")
    expect(image.read(0x0011EE28, 3).hex(), "c20400", "NFL update final return")
    expect(image.read(0x0011EE2B, 5).hex(), "9090909090", "NFL update alignment padding")
    expect(image.read(0x0011EE30, 3).hex(), "83ec2c", "NFL next-function prologue")
    return {
        "architecture": "x86-32 little-endian",
        "strings": strings,
        "states": {"basic": basic, "pause": pause, "crippled_pause": crippled},
        "training_update": {
            **anchor(image, 0x0011EB40, 0x0011EE30, "function-plus-alignment span to next function"),
            "last_instruction_start": hx(0x0011EE28),
            "after_last_instruction": hx(0x0011EE2B),
            "alignment_padding": {
                "first": hx(0x0011EE2B),
                "after_last": hx(0x0011EE30),
                "bytes": "9090909090",
            },
            "next_function": hx(0x0011EE30),
        },
        "mode_gate": {"site": hx(0x0011EB49), "global": hx(0x00E5FF80), "required_value": 3},
        "direct_caller": x86_edge(image, 0x00064E4C, 0x0011EB40),
        "basic_descriptor_pointer_sites": pointer_sites(
            data, NFL_BASIC, "little", lambda offset: xbe_offset_to_va(header, offset)
        ),
    }


def decode_apf(data: bytes) -> dict[str, Any]:
    image = ApfImage(data)
    strings = {
        "continue": {"address": hx(0x8461F4CC), "text": image.utf16(0x8461F4CC, 64)},
        "completion": {"address": hx(0x8461F500), "text": image.utf16(0x8461F500, 512)},
        "title": {"address": hx(0x8461F710), "text": image.utf16(0x8461F710, 64)},
        "welcome": {"address": hx(0x8461F730), "text": image.utf16(0x8461F730, 512)},
    }
    expect([strings[key]["text"] for key in ("continue", "completion", "title", "welcome")],
           [CONTINUE, COMPLETION, TITLE, WELCOME], "APF Basic Training strings")

    basic = decode_apf_descriptor(image, APF_BASIC)
    pause = decode_apf_descriptor(image, APF_PAUSE)
    crippled = decode_apf_descriptor(image, APF_CRIPPLED_PAUSE)
    expect((basic["title"], basic["transition"], basic["layout"]),
           (TITLE, "TutorialSelectMenu", "spreadsheet"), "APF basic state identity")
    expect([row["event"] for row in basic["events"]], [1, 4, 6, 7, 11, 12], "APF basic events")
    expect([row["label"] for row in pause["rows"]], ["Resume", "Restart", "Tutorial Menu", "Quit"], "APF pause rows")
    expect([row["label"] for row in crippled["rows"]], ["Tutorial Menu", "Quit"], "APF crippled rows")
    expect([row["target"] for row in pause["rows"] if row["label"] == "Tutorial Menu"], [hx(APF_BASIC)], "APF pause loop")
    expect([row["target"] for row in crippled["rows"] if row["label"] == "Tutorial Menu"], [hx(APF_BASIC)], "APF crippled loop")

    expected_words = {
        0x84ADF7F0: 0x7D8802A6,
        0x84ADF804: 0x3D608462,
        0x84ADF80C: 0x3FA084F4,
        0x84ADF810: 0x3B8BF730,
        0x84ADF818: 0x397CFD9C,
        0x84ADF828: 0x817DF8F8,
        0x84ADF834: 0x2F0B0004,
        0x84ADF838: 0x409A02C4,
        0x84ADFA48: 0x395CFFE0,
        0x84ADFA58: 0x389CFDD0,
        0x84ADFAC4: 0x7F84E378,
        0x84ADFB08: 0x480F732C,
        0x84ADFB0C: 0x00000000,
        0x84ADFB10: 0x7D8802A6,
        0x849D8DA8: 0x7D8802A6,
        0x849D8DC0: 0x816BF8F8,
        0x849D8DC4: 0x2F0B0004,
        0x849D8DCC: 0x3D60845F,
        0x849D8DD4: 0x38CB2128,
        0x849D8E54: 0x4E800020,
        0x849D8E58: 0x7D8802A6,
    }
    for address, value in expected_words.items():
        expect(image.u32(address), value, f"APF Basic Training anchor at {hx(address)}")

    descriptor_pointers = pointer_sites(data, APF_BASIC, "big", lambda offset: APF_BASE + offset)
    descriptor_materializations = scan_ppc_materializations(image, APF_BASIC)
    expect(descriptor_pointers, [hx(0x84E48630), hx(0x84E486F0)], "APF descriptor pointer sites")
    expect(descriptor_materializations, [{"lis": hx(0x84ADFAE8), "combine": hx(0x84ADFAEC), "kind": "addi"}], "APF descriptor materialization")

    stores = conventional_mode_stores(image)
    store_details = mode_store_details(image)
    expected_store_sites = [
        0x8466974C, 0x846699DC, 0x84681E5C, 0x84712260, 0x849D43BC,
        0x849DD8F4, 0x849FB248, 0x84A20BDC, 0x84A36C40, 0x84A67CC4,
    ]
    expect(stores, [hx(value) for value in expected_store_sites], "APF conventional mode stores")
    expect([row["site"] for row in store_details], stores, "APF mode-store detail coverage")
    expect(any(row["fixed_value"] == 4 for row in store_details), False, "APF fixed mode-4 store")
    setter_branches = scan_ppc_branches(image, 0x84669748)
    setter_materializations = scan_ppc_materializations(image, 0x84669748)
    expect(setter_branches, [], "APF direct mode-setter branches")
    expect(setter_materializations, [], "APF mode-setter materializations")
    expect(data.count((0x84669748).to_bytes(4, "big")), 0, "APF mode-setter exact pointers")

    package_name = image.utf16(0x845F2128, 64)
    expect(package_name, "dir_tutorial.iff", "APF tutorial package name")
    loader_pointer_sites = pointer_sites(data, 0x849D8DA8, "big", lambda offset: APF_BASE + offset)
    expect(loader_pointer_sites, [hx(0x844F0F30)], "APF tutorial loader function-table pointer")
    update_tail_target, update_tail_link = image.branch(0x84ADFB08)
    expect((update_tail_target, update_tail_link), (0x84BD6E34, False), "APF update tail epilogue branch")
    return {
        "architecture": "PowerPC 32-bit big-endian code / Xenon ABI",
        "strings": strings,
        "states": {"basic": basic, "pause": pause, "crippled_pause": crippled},
        "training_update": {
            **anchor(image, 0x84ADF7F0, 0x84ADFB0C, "instruction span excluding one alignment word"),
            "last_instruction_start": hx(0x84ADFB08),
            "after_last_instruction": hx(0x84ADFB0C),
            "tail_epilogue_target": hx(update_tail_target),
            "alignment_padding": {
                "first": hx(0x84ADFB0C),
                "after_last": hx(0x84ADFB10),
                "word": "00000000",
            },
            "next_function": hx(0x84ADFB10),
            "direct_caller": ppc_edge(image, 0x849D2D74, 0x84ADF7F0),
            "caller_function": hx(0x849D2AD8),
            "caller_function_incoming_branches": scan_ppc_branches(image, 0x849D2AD8),
        },
        "mode_gate": {
            "site": hx(0x84ADF834),
            "global": hx(APF_MODE_GLOBAL),
            "required_value": 4,
            "conventional_nearby_lis_store_sites": stores,
            "conventional_store_classifications": store_details,
            "fixed_immediate_value_4_store_found": False,
            "arbitrary_setter": {
                "address": hx(0x84669748),
                "direct_branches": setter_branches,
                "exact_pointer_count": 0,
                "conventional_materializations": setter_materializations,
                "indirect_access_excluded": False,
            },
        },
        "ownership": {
            "basic_descriptor_exact_pointer_sites": descriptor_pointers,
            "basic_descriptor_conventional_materializations": descriptor_materializations,
            "all_proved_descriptor_routes_are_internal": True,
            "external_frontend_route_proved": False,
        },
        "tutorial_package_loader": {
            **anchor(image, 0x849D8DA8, 0x849D8E58, "function-table-owned conditional tutorial package loader"),
            "last_instruction_start": hx(0x849D8E54),
            "next_function": hx(0x849D8E58),
            "function_pointer_sites": loader_pointer_sites,
            "package_name_address": hx(0x845F2128),
            "package_name": package_name,
            "package_name_materializations": scan_ppc_materializations(image, 0x845F2128),
            "required_mode": 4,
        },
    }


def director_lineage(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    expect(report["schema"], "vc_cross_title_director_inventory/v1", "director schema")
    role = next(row for row in report["cross_title_roles"] if row["role"] == "tutorial")
    apf = next(row for row in report["resources"] if row["platform"] == "apf2k8" and row["role"] == "tutorial")
    nfl = next(row for row in report["resources"] if row["platform"] == "nfl2k5" and row["role"] == "tutorial")
    expect(role["primary_string_count"], {"apf": 101, "nfl": 101}, "tutorial string counts")
    expect(role["shared_exact_primary_string_count"], 101, "shared tutorial string count")
    expect(role["ordered_structural_signature_match_count"], 1, "tutorial structural match")
    return {
        "nfl2k5": {"outer_index": nfl["outer_index"], "byte_size": nfl["byte_size"], "sha256": nfl["sha256"]},
        "apf2k8": {"outer_index": apf["outer_index"], "outer_name": apf["outer_name"], "byte_size": apf["byte_size"], "sha256": apf["sha256"]},
        "primary_string_count": role["primary_string_count"],
        "shared_exact_primary_string_count": role["shared_exact_primary_string_count"],
        "instruction_record_count": role["instruction_record_count"],
        "nonnull_fixed_record_count": role["nonnull_fixed_record_count"],
        "ordered_structural_signature_match_count": role["ordered_structural_signature_match_count"],
        "lineage_statement": role["lineage_statement"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nfl-xbe", type=Path, required=True)
    parser.add_argument("--nfl-header", type=Path, required=True)
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--director-report", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()

    nfl_data = args.nfl_xbe.read_bytes()
    apf_data = args.apf_pe.read_bytes()
    header = json.loads(args.nfl_header.read_text(encoding="utf-8"))
    expect(sha256_bytes(nfl_data), NFL_XBE_SHA256, "NFL XBE SHA-256")
    expect(sha256_file(args.apf_xex), APF_XEX_SHA256, "APF XEX SHA-256")
    expect(sha256_bytes(apf_data), APF_PE_SHA256, "APF PE SHA-256")
    expect(sha256_file(args.director_report), DIRECTOR_SHA256, "director report SHA-256")

    nfl = decode_nfl(nfl_data, header)
    apf = decode_apf(apf_data)
    for key in ("continue", "completion", "title", "welcome"):
        expect(nfl["strings"][key]["text"], apf["strings"][key]["text"], f"shared {key} string")

    report = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_audit": True,
            "runtime_reachability_claimed": False,
            "playable_hidden_tutorial_claimed": False,
            "formal_nfl_2k6_identity_claimed": False,
        },
        "inputs": {
            "nfl2k5_xbe": {"path": args.nfl_xbe.as_posix(), "sha256": NFL_XBE_SHA256, "size": len(nfl_data)},
            "nfl2k5_header": {"path": args.nfl_header.as_posix(), "sha256": sha256_file(args.nfl_header)},
            "apf2k8_xex": {"path": args.apf_xex.as_posix(), "sha256": APF_XEX_SHA256, "size": args.apf_xex.stat().st_size},
            "apf2k8_pe": {"path": "generated temporary PE memory image", "sha256": APF_PE_SHA256, "size": len(apf_data)},
            "director_report": {"path": args.director_report.as_posix(), "sha256": DIRECTOR_SHA256},
        },
        "nfl2k5": nfl,
        "apf2k8": apf,
        "director_package_lineage": director_lineage(args.director_report),
        "cross_title_findings": {
            "four_exact_ui_strings_shared": True,
            "nfl_branding_retained_in_apf": True,
            "three_state_subsystem_retained": True,
            "six_basic_state_events_retained": True,
            "pause_navigation_shape_retained": True,
            "training_update_directly_called_in_both": True,
            "apf_tutorial_loader_function_pointer_retained": True,
            "all_101_director_strings_retained": True,
            "apf_external_frontend_route_proved": False,
            "safe_interpretation": (
                "APF ships a converted, code-connected, internally closed NFL 2K5 Basic Training subsystem. "
                "The ordinary descriptor/state-transition routes proved here remain within the subsystem, and no conventional fixed producer "
                "of its required APF mode value 4 was found. This is substantial cut-mode lineage, not a playable hidden-mode claim."
            ),
        },
        "portme": [
            "PORTME(0x820E5AE0): prove or falsify hashed/computed/external frontend entry into TutorialSelectMenu.",
            "PORTME(0x84F3F8F8): prove or falsify indirect producers of APF mode value 4.",
            "PORTME(0x84ADF7F0): recover complete field names and dialog/transition semantics for the retained update routine.",
            "PORTME(runtime): capture a safely reached APF Basic Training screen before calling the mode playable.",
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_BASIC_TRAINING_REMNANT_PASS states=3 events=6 director_strings=101 "
        "external_route=false mode4_fixed_store=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
