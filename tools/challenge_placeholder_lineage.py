#!/usr/bin/env python3
"""Audit shared challenge-camera and Hello World developer residue.

This is a read-only, evidence-bounded static audit of the retail NFL 2K5 XBE
and the decompressed retail APF 2K8 PE memory image.  It neither patches nor
executes either title.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from menu_state_trace import APF_BASE, APF_PE_SHA256, ApfImage, XbeImage


SCHEMA = "vc_challenge_placeholder_lineage/v1"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"

BOOTH_TEXT = "Booth Is Challenging Play\n"
PLACEHOLDER_TEXT = (
    "%s are Challenging Play.\n"
    " (This is a placeholder until we get all the pretty camera cuts)\n"
)
HELLO_TEXT = "Hello World"


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


def anchor(image: Any, start: int, after_last: int, name: str) -> dict[str, Any]:
    body = image.read(start, after_last - start)
    return {
        "name": name,
        "first": hx(start),
        "after_last": hx(after_last),
        "size": len(body),
        "sha256": sha256_bytes(body),
    }


def x86_edge(image: XbeImage, site: int, target: int, opcode: int) -> dict[str, str]:
    expect(image.u8(site), opcode, f"x86 opcode at {hx(site)}")
    relative = struct.unpack("<i", image.read(site + 1, 4))[0]
    actual = (site + 5 + relative) & 0xFFFFFFFF
    expect(actual, target, f"x86 edge at {hx(site)}")
    return {
        "site": hx(site),
        "target": hx(target),
        "kind": "call" if opcode == 0xE8 else "tail_jump",
        "bytes": image.read(site, 5).hex(),
    }


def ppc_edge(image: ApfImage, site: int, target: int) -> dict[str, str]:
    actual, link = image.branch(site)
    expect(actual, target, f"PPC edge target at {hx(site)}")
    expect(link, True, f"PPC edge link bit at {hx(site)}")
    return {
        "site": hx(site),
        "target": hx(target),
        "kind": "call",
        "word": f"{image.u32(site):08X}",
    }


def scan_x86_rel32_targets(
    data: bytes, header: dict[str, Any], target: int
) -> list[dict[str, str]]:
    """Conservative byte scan of game .text for direct E8/E9 targets."""
    section = next(row for row in header["sections"] if row["name"] == ".text")
    raw = int(section["raw_address"])
    size = int(section["raw_size"])
    base = int(section["virtual_address"])
    body = data[raw : raw + size]
    hits: list[dict[str, str]] = []
    for offset in range(len(body) - 4):
        opcode = body[offset]
        if opcode not in (0xE8, 0xE9):
            continue
        site = base + offset
        relative = struct.unpack_from("<i", body, offset + 1)[0]
        if ((site + 5 + relative) & 0xFFFFFFFF) == target:
            hits.append({
                "site": hx(site),
                "kind": "call" if opcode == 0xE8 else "jump",
            })
    return hits


def scan_ppc_branches(image: ApfImage, target: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for site in range(0x84630000, 0x84D0904C, 4):
        word = image.u32(site)
        if word >> 26 != 18:
            continue
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        actual = (displacement if word & 2 else site + displacement) & 0xFFFFFFFF
        if actual == target:
            hits.append({"site": hx(site), "link": bool(word & 1)})
    return hits


def scan_ppc_materializations(image: ApfImage, target: int) -> list[dict[str, Any]]:
    """Find conventional lis plus nearby addi/ori absolute materializations."""
    high = ((target + 0x8000) >> 16) & 0xFFFF
    low = target & 0xFFFF
    hits: list[dict[str, Any]] = []
    for site in range(0x84630000, 0x84D0904C, 4):
        first = image.u32(site)
        if first >> 26 != 15 or ((first >> 16) & 31) != 0 or (first & 0xFFFF) != high:
            continue
        register = (first >> 21) & 31
        for distance in range(1, 9):
            combine_site = site + distance * 4
            second = image.u32(combine_site)
            opcode = second >> 26
            if (
                opcode == 14
                and ((second >> 16) & 31) == register
                and (second & 0xFFFF) == low
            ):
                hits.append({
                    "lis": hx(site),
                    "combine": hx(combine_site),
                    "kind": "addi",
                })
            if (
                opcode == 24
                and ((second >> 21) & 31) == register
                and (second & 0xFFFF) == low
            ):
                hits.append({
                    "lis": hx(site),
                    "combine": hx(combine_site),
                    "kind": "ori",
                })
    return hits


def decode_nfl(data: bytes, header: dict[str, Any]) -> dict[str, Any]:
    image = XbeImage(data, header)
    strings = {
        "booth": {"address": hx(0x00E845E0), "text": image.utf16(0x00E845E0, 512)},
        "placeholder": {"address": hx(0x00E84618), "text": image.utf16(0x00E84618, 512)},
        "hello_world": {"address": hx(0x00E61848), "text": image.utf16(0x00E61848, 64)},
    }
    expect(strings["booth"]["text"], BOOTH_TEXT, "NFL booth string")
    expect(strings["placeholder"]["text"], PLACEHOLDER_TEXT, "NFL placeholder string")
    expect(strings["hello_world"]["text"], HELLO_TEXT, "NFL Hello World string")
    expect(data.count((BOOTH_TEXT + "\0").encode("utf-16le")), 1, "NFL booth occurrence count")
    expect(data.count((PLACEHOLDER_TEXT + "\0").encode("utf-16le")), 1, "NFL placeholder occurrence count")
    expect(data.count((HELLO_TEXT + "\0").encode("utf-16le")), 1, "NFL Hello World occurrence count")

    call_chain = [
        x86_edge(image, 0x0018C3E8, 0x000A1DB0, 0xE8),
        x86_edge(image, 0x000A1E1C, 0x001E8070, 0xE8),
        x86_edge(image, 0x001E80A9, 0x001B1420, 0xE9),
    ]
    expect(image.read(0x001B1432, 6).hex(), "85f68bf87508", "NFL null/booth branch anchor")
    expect(image.read(0x001B1439, 5).hex(), "bae045e800", "NFL booth immediate")
    expect(image.read(0x001B1452, 5).hex(), "ba1846e800", "NFL placeholder immediate")
    expect(image.read(0x00062140, 6).hex(), "b84818e600c3", "NFL Hello World getter")

    hello_calls = scan_x86_rel32_targets(data, header, 0x00062140)
    expect(hello_calls, [], "NFL direct callers of Hello World getter")
    expect(data.count((0x00062140).to_bytes(4, "little")), 0, "NFL absolute pointers to Hello World getter")
    return {
        "architecture": "x86-32 little-endian",
        "strings": strings,
        "challenge_formatter": anchor(image, 0x001B1420, 0x001B1500, "challenge presentation formatter"),
        "challenge_string_immediates": [
            {"site": hx(0x001B1439), "target": hx(0x00E845E0)},
            {"site": hx(0x001B1452), "target": hx(0x00E84618)},
        ],
        "bounded_call_chain": call_chain,
        "hello_world_getter": {
            **anchor(image, 0x00062140, 0x00062146, "Hello World pointer getter"),
            "return_string": hx(0x00E61848),
            "direct_rel32_call_or_jump_sites_in_text": hello_calls,
            "absolute_pointer_count_in_xbe": 0,
        },
    }


def decode_apf(data: bytes) -> dict[str, Any]:
    image = ApfImage(data)
    strings = {
        "booth": {"address": hx(0x845EBB40), "text": image.utf16(0x845EBB40, 512)},
        "placeholder": {"address": hx(0x845EBB78), "text": image.utf16(0x845EBB78, 512)},
        "hello_world": {"address": hx(0x845F15F4), "text": image.utf16(0x845F15F4, 64)},
    }
    expect(strings["booth"]["text"], BOOTH_TEXT, "APF booth string")
    expect(strings["placeholder"]["text"], PLACEHOLDER_TEXT, "APF placeholder string")
    expect(strings["hello_world"]["text"], HELLO_TEXT, "APF Hello World string")
    expect(data.count((BOOTH_TEXT + "\0").encode("utf-16be")), 1, "APF booth occurrence count")
    expect(data.count((PLACEHOLDER_TEXT + "\0").encode("utf-16be")), 1, "APF placeholder occurrence count")
    expect(data.count((HELLO_TEXT + "\0").encode("utf-16be")), 1, "APF Hello World occurrence count")

    expected_words = {
        0x8486FC90: 0x2B1F0000,
        0x8486FC94: 0x3D40845F,
        0x8486FCA4: 0x409A0014,
        0x8486FCA8: 0x388ABB40,
        0x8486FCBC: 0x394ABB40,
        0x8486FCC8: 0x388A0038,
        0x849D4B58: 0x3D60845F,
        0x849D4B5C: 0x386B15F4,
        0x849D4B60: 0x4E800020,
    }
    for address, word in expected_words.items():
        expect(image.u32(address), word, f"APF PPC anchor at {hx(address)}")

    call_chain = [
        ppc_edge(image, 0x848915F4, 0x8486EEB8),
        ppc_edge(image, 0x8486EEFC, 0x8486FC70),
    ]
    hello_branches = scan_ppc_branches(image, 0x849D4B58)
    hello_materializations = scan_ppc_materializations(image, 0x849D4B58)
    expect(hello_branches, [], "APF immediate branches to Hello World getter")
    expect(hello_materializations, [], "APF conventional materializations of Hello World getter")
    expect(data.count((0x849D4B58).to_bytes(4, "big")), 0, "APF absolute pointers to Hello World getter")
    return {
        "architecture": "PowerPC 32-bit big-endian code / Xenon ABI",
        "strings": strings,
        "challenge_formatter": anchor(image, 0x8486FC70, 0x8486FE30, "challenge presentation formatter"),
        "challenge_string_materialization": {
            "shared_lis": hx(0x8486FC94),
            "booth_addi": hx(0x8486FCA8),
            "named_base_addi": hx(0x8486FCBC),
            "named_plus_0x38_addi": hx(0x8486FCC8),
        },
        "bounded_call_chain": call_chain,
        "hello_world_getter": {
            **anchor(image, 0x849D4B58, 0x849D4B64, "Hello World pointer getter"),
            "return_string": hx(0x845F15F4),
            "immediate_branch_sites_in_text": hello_branches,
            "conventional_address_materializations_in_text": hello_materializations,
            "absolute_pointer_count_in_pe": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nfl-xbe", type=Path, required=True)
    parser.add_argument("--nfl-header", type=Path, required=True)
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()

    nfl_data = args.nfl_xbe.read_bytes()
    apf_data = args.apf_pe.read_bytes()
    header = json.loads(args.nfl_header.read_text(encoding="utf-8"))
    expect(sha256_bytes(nfl_data), NFL_XBE_SHA256, "NFL XBE SHA-256")
    expect(sha256_file(args.apf_xex), APF_XEX_SHA256, "APF XEX SHA-256")
    expect(sha256_bytes(apf_data), APF_PE_SHA256, "APF PE SHA-256")

    nfl = decode_nfl(nfl_data, header)
    apf = decode_apf(apf_data)
    expect(nfl["strings"]["booth"]["text"], apf["strings"]["booth"]["text"], "shared booth text")
    expect(
        nfl["strings"]["placeholder"]["text"],
        apf["strings"]["placeholder"]["text"],
        "shared placeholder text",
    )
    expect(nfl["strings"]["hello_world"]["text"], apf["strings"]["hello_world"]["text"], "shared Hello World text")

    report = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_audit": True,
            "runtime_visibility_claimed": False,
            "hidden_mode_claimed": False,
            "formal_nfl_2k6_proof_claimed": False,
        },
        "inputs": {
            "nfl2k5_xbe": {"path": args.nfl_xbe.as_posix(), "size": len(nfl_data), "sha256": NFL_XBE_SHA256},
            "nfl2k5_header": {"path": args.nfl_header.as_posix(), "sha256": sha256_file(args.nfl_header)},
            "apf2k8_xex": {"path": args.apf_xex.as_posix(), "size": args.apf_xex.stat().st_size, "sha256": APF_XEX_SHA256},
            "apf2k8_pe": {"path": "generated temporary PE memory image", "size": len(apf_data), "sha256": APF_PE_SHA256},
        },
        "nfl2k5": nfl,
        "apf2k8": apf,
        "cross_title_findings": {
            "exact_challenge_copy_shared": True,
            "challenge_copy_code_connected_in_both": True,
            "branch_shape_shared": "null/booth path versus named-team path",
            "developer_note": "The retail text explicitly calls the presentation a placeholder pending camera cuts.",
            "safe_interpretation": (
                "A shared, code-connected challenge-presentation placeholder survived the Xbox-to-Xenon engine conversion. "
                "It is source-lineage and unfinished-presentation evidence, not a hidden mode or standalone NFL 2K6 proof."
            ),
            "hello_world_shared_getters": True,
            "hello_world_direct_static_callers_found": False,
            "hello_world_limit": (
                "No direct rel32/PPC-immediate caller, exact function pointer, or conventional APF address materialization was found; "
                "indirect, table-relative, TOC-relative, computed, or runtime-created access is not excluded."
            ),
        },
        "portme": [
            "PORTME(0x001B1420/0x8486FC70): recover names/types for the complete shared challenge presentation routine.",
            "PORTME(runtime): capture the retail challenge path to determine which placeholder copy is visibly exercised.",
            "PORTME(0x00062140/0x849D4B58): prove or falsify indirect/relative callers of the Hello World getter pair.",
            "PORTME(lineage): do not assign these residues to a formally titled NFL 2K6 build without independent dated/build evidence.",
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "CHALLENGE_PLACEHOLDER_LINEAGE_PASS "
        "challenge_shared=yes code_connected=yes hello_direct_callers=0 "
        "runtime=false nfl2k6_claim=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
