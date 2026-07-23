#!/usr/bin/env python3
"""Generate deterministic APF frontend_sync/Main ownership evidence v6."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any, Iterable

import apf_inner
import apf_outer


BASE = 0x82000000
TEXT_FIRST = 0x84630000
TEXT_AFTER_LAST = 0x84D0904C
PDATA_FIRST = 0x844DBE00
PDATA_AFTER_LAST = 0x84500000

EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
EXPECTED_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
EXPECTED_INPUT_HASHES = {
    "outer_manifest": "3653a1e2f66df35e29e68d3cd92a9dd8dcc66a9c76f0fe97f06057cf2508b807",
    "inner_candidates": "26dd77660c91568773519f616e7120c6b8c23dc3613880e5a5831c18ee34a0d3",
    "base_menu": "ecd93117a3a808a16697c23ae10e3225953bcb4dabda30afabdc5c02911974f1",
    "base_closure": "1145accb0a91cc0137cbf3757a0bff9d6a85a00a55ed41efa891e2a267c7788a",
    "v5_report": "7124d3864bb7fbb30d9c8d42a454b115b3a6c07721ad1f3f2a75da0a21bcb911",
}
EXPECTED_PACK_HASHES = {
    "0A": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "0B": "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
    "1A": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
    "1B": "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
}


def hx(value: int) -> str:
    return f"0x{value:08X}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 << 20):
            hasher.update(block)
    return hasher.hexdigest()


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label}: expected {expected!r}, got {actual!r}")


class Image:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()

    def offset(self, address: int) -> int:
        offset = address - BASE
        if offset < 0 or offset >= len(self.data):
            raise ValueError(f"address outside reconstructed PE: {hx(address)}")
        return offset

    def u32(self, address: int) -> int:
        return struct.unpack_from(">I", self.data, self.offset(address))[0]

    def span(self, first: int, after_last: int) -> bytes:
        return self.data[self.offset(first) : self.offset(after_last - 1) + 1]

    def utf16(self, address: int, maximum_units: int = 256) -> str:
        output: list[str] = []
        offset = self.offset(address)
        for _ in range(maximum_units):
            code = struct.unpack_from(">H", self.data, offset)[0]
            offset += 2
            if code == 0:
                return "".join(output)
            output.append(chr(code))
        raise ValueError(f"unterminated UTF-16BE string at {hx(address)}")

    def branch(self, address: int) -> tuple[int, bool]:
        word = self.u32(address)
        if word >> 26 != 18:
            raise ValueError(f"not a PPC b/bl at {hx(address)}: {hx(word)}")
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

    def direct_branch_sites(self, target: int) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for address in range(TEXT_FIRST, TEXT_AFTER_LAST, 4):
            word = self.u32(address)
            if word >> 26 != 18:
                continue
            displacement = word & 0x03FFFFFC
            if displacement & 0x02000000:
                displacement -= 0x04000000
            actual = (displacement if word & 2 else address + displacement) & 0xFFFFFFFF
            if actual == target:
                result.append(
                    {
                        "site": hx(address),
                        "kind": "call" if word & 1 else "jump",
                    }
                )
        return result

    def direct_targets(self, first: int, after_last: int) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for address in range(first, after_last, 4):
            word = self.u32(address)
            if word >> 26 != 18:
                continue
            displacement = word & 0x03FFFFFC
            if displacement & 0x02000000:
                displacement -= 0x04000000
            target = (displacement if word & 2 else address + displacement) & 0xFFFFFFFF
            result.append(
                {
                    "site": hx(address),
                    "target": hx(target),
                    "kind": "call" if word & 1 else "jump",
                }
            )
        return result


BOUNDARIES = [
    ("frontend_sync plus online request", 0x8467CA70, 0x8467CA78, 0x8467CB20, 0x40002C03),
    ("frontend asynchronous request setup", 0x8467CB88, 0x8467CB90, 0x8467CC80, 0x40003E03),
    ("resource release wrapper", 0x8468CFC0, 0x8468CFC8, 0x8468D038, 0x40001E03),
    ("resource request default dispatch", 0x8468D7D0, 0x8468D7D8, 0x8468D870, 0x40002803),
    ("resource request override dispatch", 0x8468D870, 0x8468D878, 0x8468D910, 0x40002803),
    ("resource request front-end", 0x8468DA70, 0x8468DA78, 0x8468DB64, 0x40003D03),
    ("mode-specific descriptor close route", 0x846DE230, 0x846DE238, 0x846DE398, 0x40005A03),
    ("descriptor exit-policy dispatcher", 0x846F0058, 0x846F0060, 0x846F0190, 0x40004E03),
    ("queued-route policy A", 0x846F5F48, 0x846F5F50, 0x846F6050, 0x40004203),
    ("queued-route policy B", 0x846F6060, 0x846F6068, 0x846F60E8, 0x40002203),
    ("Team Select platform mode route", 0x84A59758, 0x84A59758, 0x84A59810, 0x40002E05),
    ("Team Select mode-2 route", 0x84A59A10, 0x84A59A10, 0x84A59A80, 0x40001C04),
    ("Team Select exit-policy callback", 0x84A59B10, 0x84A59B10, 0x84A59BA4, 0x40002505),
    ("generic close trigger", 0x846F5518, 0x846F5518, 0x846F5580, 0x40001A04),
    ("function immediately before orphan Main wrapper", 0x84A56900, 0x84A56900, 0x84A56950, 0x40001403),
]


def pdata_rows(image: Image) -> dict[int, tuple[int, int, int]]:
    rows: dict[int, tuple[int, int, int]] = {}
    for slot in range(PDATA_FIRST, PDATA_AFTER_LAST, 8):
        address = image.u32(slot)
        metadata = image.u32(slot + 4)
        words = (metadata >> 8) & 0xFFFF
        rows[address] = (slot, metadata, address + words * 4)
    return rows


def boundary_rows(image: Image) -> list[dict[str, Any]]:
    pdata = pdata_rows(image)
    output: list[dict[str, Any]] = []
    for role, address, body, end, metadata in BOUNDARIES:
        if address not in pdata:
            raise ValueError(f"missing PDATA entry for {hx(address)}")
        slot, actual_metadata, actual_end = pdata[address]
        expect(actual_metadata, metadata, f"PDATA metadata for {role}")
        expect(actual_end, end, f"PDATA end for {role}")
        output.append(
            {
                "role": role,
                "address": hx(address),
                "body_entry_after_shared_save": hx(body),
                "end_exclusive": hx(end),
                "size": end - address,
                "pdata_slot": hx(slot),
                "pdata_metadata": hx(metadata),
                "raw_sha256": digest(image.span(address, end)),
            }
        )
    return output


def read_candidates(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def find_all(data: bytes, needle: bytes) -> list[int]:
    result: list[int] = []
    cursor = 0
    while True:
        cursor = data.find(needle, cursor)
        if cursor < 0:
            return result
        result.append(cursor)
        cursor += 1


def scan_layout_payloads(
    archive: apf_outer.Archive,
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    by_outer: dict[int, list[tuple[int, str]]] = {}
    for row in candidates:
        if row["type_name"] == "LAYT":
            by_outer.setdefault(int(row["outer_table_index"]), []).append(
                (int(row["inner_index"]), row["inner_name"])
            )

    name_needle = "layout_mainmenu".encode("utf-16-be")
    hash_needle = (0x48C6D154).to_bytes(4, "big")
    name_hits: list[dict[str, Any]] = []
    hash_hits: list[dict[str, Any]] = []
    decoded_unique_bytes = 0
    layout_count = 0
    with apf_inner.ArchiveReader(archive) as reader:
        for outer_index, files in sorted(by_outer.items()):
            record = apf_inner.parse_iff(reader, archive.entries[outer_index])
            cache: dict[int, bytes] = {}
            for file_index, expected_name in files:
                item = record.files[file_index]
                expect(item.type_name, "LAYT", f"LAYT type outer {outer_index} inner {file_index}")
                expect(item.name, expected_name, f"LAYT name outer {outer_index} inner {file_index}")
                layout_count += 1
                for part in item.parts:
                    if part.block_index not in cache:
                        cache[part.block_index] = apf_inner.decode_block(
                            reader, record, part.block_index, 1 << 30
                        )
                        decoded_unique_bytes += len(cache[part.block_index])
                    payload = cache[part.block_index][
                        part.offset : part.offset + part.length
                    ]
                    for offset in find_all(payload, name_needle):
                        name_hits.append(
                            {
                                "outer_index": outer_index,
                                "inner_index": file_index,
                                "inner_name": item.name,
                                "block_index": part.block_index,
                                "block_offset": hx(part.offset + offset),
                                "part_offset": hx(offset),
                            }
                        )
                    for offset in find_all(payload, hash_needle):
                        hash_hits.append(
                            {
                                "outer_index": outer_index,
                                "inner_index": file_index,
                                "inner_name": item.name,
                                "block_index": part.block_index,
                                "block_offset": hx(part.offset + offset),
                                "part_offset": hx(offset),
                            }
                        )

    expect(len(by_outer), 13, "outer archives containing LAYT")
    expect(layout_count, 161, "LAYT payload count")
    expect(decoded_unique_bytes, 19_668_428, "decoded unique LAYT block bytes")
    expect(
        name_hits,
        [
            {
                "outer_index": 1493,
                "inner_index": 53,
                "inner_name": "layout_mainmenu",
                "block_index": 0,
                "block_offset": "0x001DF8B0",
                "part_offset": "0x00000190",
            }
        ],
        "layout_mainmenu self-name hits across LAYT payloads",
    )
    expect(hash_hits, [], "layout_mainmenu hash hits across LAYT payloads")
    return {
        "outer_archive_count": len(by_outer),
        "layout_file_count": layout_count,
        "decoded_unique_block_bytes": decoded_unique_bytes,
        "utf16be_name_hits": name_hits,
        "hash_big_endian_hits": hash_hits,
        "result": (
            "no other serialized LAYT names or hashes layout_mainmenu; the sole name "
            "hit is the target LAYT's own +0x190 self-name"
        ),
    }


def frontend_bundle_evidence(
    archive: apf_outer.Archive,
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    entry = archive.entries[1493]
    expect(entry.name_id, 0xF69D21E4, "frontend_sync outer name ID")
    rows = [
        row
        for row in candidates
        if int(row["outer_table_index"]) == 1493
    ]
    expect(len(rows), 157, "frontend_sync inner candidate count")
    target_rows = [row for row in rows if row["inner_name"] == "layout_mainmenu"]
    expect(len(target_rows), 1, "layout_mainmenu row count")
    expect(target_rows[0]["inner_index"], "53", "layout_mainmenu index")
    expect(target_rows[0]["type_name"], "LAYT", "layout_mainmenu type")

    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        target = record.files[53]
        expect(target.file_id, 0x48C6D154, "layout_mainmenu file ID")
        expect(target.name, "layout_mainmenu", "layout_mainmenu decoded name")
        expect(target.type_hash, 0x86A1AC9E, "layout_mainmenu type hash")
        expect(record.file_descriptor_offsets[53], 0x65C, "layout_mainmenu descriptor offset")
        expect(
            [(part.block_index, part.offset, part.length) for part in target.parts],
            [(0, 0x1DF720, 0x2C0)],
            "layout_mainmenu parts",
        )
        decoded_blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(len(record.blocks))
        ]

    name_needle = "layout_mainmenu".encode("utf-16-be")
    hash_needle = (0x48C6D154).to_bytes(4, "big")
    name_hits = [
        {"block_index": index, "offset": hx(offset)}
        for index, data in enumerate(decoded_blocks)
        for offset in find_all(data, name_needle)
    ]
    hash_hits = [
        {"block_index": index, "offset": hx(offset)}
        for index, data in enumerate(decoded_blocks)
        for offset in find_all(data, hash_needle)
    ]
    expect(name_hits, [{"block_index": 0, "offset": "0x001DF8B0"}], "frontend bundle name hits")
    expect(hash_hits, [], "frontend bundle decoded hash hits")
    return {
        "archive": "frontend_sync.iff",
        "outer_index": 1493,
        "outer_name_id": hx(entry.name_id),
        "outer_name_id_derivation": "CRC32 uppercase ASCII FRONTEND_SYNC.IFF",
        "inner_entry_count": len(record.files),
        "layout_entry_count": sum(file.type_name == "LAYT" for file in record.files),
        "inner_index": 53,
        "inner_name": target.name,
        "inner_file_id": hx(target.file_id),
        "inner_file_descriptor_offset": hx(record.file_descriptor_offsets[53]),
        "type_hash": hx(target.type_hash),
        "part": {"block_index": 0, "offset": hx(0x1DF720), "length": hx(0x2C0)},
        "decoded_block_sizes": [len(data) for data in decoded_blocks],
        "decoded_payload_name_hits": name_hits,
        "decoded_payload_hash_hits": hash_hits,
        "serialized_sibling_reference_status": (
            "none by exact UTF-16BE name or big-endian 32-bit ID; the sole decoded "
            "name is inner 53's self-name"
        ),
    }


def assert_word(image: Image, address: int, expected: int, label: str) -> None:
    expect(image.u32(address), expected, f"{label} at {hx(address)}")


def assert_branch(image: Image, site: int, target: int, link: bool = True) -> None:
    expect(image.branch(site), (target, link), f"branch at {hx(site)}")


def source_pin(path: Path, expected: str, label: str) -> dict[str, Any]:
    actual = file_digest(path)
    expect(actual, expected, f"{label} SHA-256")
    return {"path": path.as_posix(), "size": path.stat().st_size, "sha256": actual}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    xex_data = args.apf_xex.read_bytes()
    expect(digest(xex_data), EXPECTED_XEX_SHA256, "APF XEX SHA-256")
    expect(args.apf_pe.name, "apf2k8_default.pe", "reconstructed PE basename")
    image = Image(args.apf_pe)
    expect(digest(image.data), EXPECTED_PE_SHA256, "APF reconstructed PE SHA-256")

    inputs = {
        "outer_manifest": source_pin(args.outer_manifest, EXPECTED_INPUT_HASHES["outer_manifest"], "outer manifest"),
        "inner_candidates": source_pin(args.inner_candidates, EXPECTED_INPUT_HASHES["inner_candidates"], "inner candidates"),
        "base_menu": source_pin(args.base_menu, EXPECTED_INPUT_HASHES["base_menu"], "base menu report"),
        "base_closure": source_pin(args.base_closure, EXPECTED_INPUT_HASHES["base_closure"], "base closure report"),
        "v5_report": source_pin(args.v5_report, EXPECTED_INPUT_HASHES["v5_report"], "v5 report"),
    }
    base_menu = json.loads(args.base_menu.read_text())
    base_closure = json.loads(args.base_closure.read_text())
    v5 = json.loads(args.v5_report.read_text())
    expect(base_menu["schema"], "vc_menu_state_trace/v1", "base menu schema")
    expect(base_closure["schema"], "vc_menu_state_trace_closure/v2", "base closure schema")
    expect(v5["schema"], "vc_apf_frontend_boot_backdrop/v5", "v5 schema")

    archive = apf_outer.parse_archive(args.outer_index)
    expect(len(archive.entries), 1543, "APF outer entry count")
    pack_pins: list[dict[str, Any]] = []
    for pack in archive.packs:
        actual = file_digest(pack.path)
        expect(actual, EXPECTED_PACK_HASHES[pack.name], f"APF pack {pack.name} SHA-256")
        pack_pins.append(
            {
                "name": pack.name,
                "path": pack.path.as_posix(),
                "size": pack.path.stat().st_size,
                "sha256": actual,
            }
        )
    candidates = read_candidates(args.inner_candidates)
    bundle = frontend_bundle_evidence(archive, candidates)
    layout_scan = scan_layout_payloads(archive, candidates)

    trace = args.trace.read_text()
    pseudo = args.pseudo.read_text()
    required_trace = [
        "APF frontend_sync/Main ownership v6 read-only trace",
        "true_entry=0x8467CA70 body_entry=0x8467CA78 end_exclusive=0x8467CB20",
        "true_entry=0x8468DA70 body_entry=0x8468DA78 end_exclusive=0x8468DB64",
        "true_entry=0x846F0058 body_entry=0x846F0060 end_exclusive=0x846F0190",
        "UTF16 0x8450232C=frontend_sync.iff",
        "UTF16 0x8460C04C=Main Menu",
        "UTF16 0x8460C088=quicknav",
        "UTF16 0x84612064=Team Select",
        "0x84A56950 section=.text function_at=none owner=none refs=",
    ]
    for marker in required_trace:
        if marker not in trace:
            raise ValueError(f"missing v6 Ghidra trace marker: {marker}")
    required_pseudo = [
        "APF_FrontendSyncRequest_Body",
        "0xffffffff8450232c",
        "APF_ResourceRequestDispatch_Body",
        "APF_DescriptorDestroy_Body",
        "Function_84A59B10",
        "Function_84A59758",
        "APF_ModeSpecificDescriptorRoute_Body",
        "Function_846F5518",
        "case 0x1b:",
        "func_0x846f0058(param_1);",
        "// PORTME: Ghidra did not structurally recover all control flow for 0x84A59758",
    ]
    for marker in required_pseudo:
        if marker not in pseudo:
            raise ValueError(f"missing v6 pseudo-C marker: {marker}")

    # Boot-owned frontend_sync request.  The compiler retains a base string in
    # r31 and forms frontend_sync.iff cross-register at +0xCC; v5's same-register
    # literal scan therefore missed this exact use.
    assert_branch(image, 0x84691BB8, 0x8467CA70)
    expected_request_words = {
        0x8467CA7C: 0x3D608450,
        0x8467CA84: 0x3BEB2260,
        0x8467CAA4: 0x3CA04818,
        0x8467CAAC: 0x38DF00CC,
        0x8467CAB0: 0x60A51338,
    }
    for site, word in expected_request_words.items():
        assert_word(image, site, word, "frontend_sync request construction")
    assert_branch(image, 0x8467CACC, 0x8468DA70)
    expect(image.utf16(0x8450232C), "frontend_sync.iff", "frontend_sync string")
    expect(zlib.crc32(b"FRONTEND_SYNC") & 0xFFFFFFFF, 0x48181338, "frontend_sync stem CRC")
    expect(zlib.crc32(b"FRONTEND_SYNC.IFF") & 0xFFFFFFFF, 0xF69D21E4, "frontend_sync outer CRC")

    # The request front-end preserves input hash/name in nonvolatile r29/r28,
    # then passes them as r6/r7 to both lower request paths.
    request_forward_words = {
        0x8468DA84: 0x7CBD2B78,
        0x8468DA88: 0x7CDC3378,
        0x8468DAC4: 0x7F87E378,
        0x8468DAC8: 0x7FA6EB78,
        0x8468DB24: 0x7F04C378,
    }
    for site, word in request_forward_words.items():
        assert_word(image, site, word, "resource request argument forwarding")
    assert_branch(image, 0x8468DB14, 0x8468D7D0)
    assert_branch(image, 0x8468DB58, 0x8468D870)

    # Existing proved boot chain reaches Team Select.  Reassert its executable
    # endpoints and decode the descriptor-owned exit-policy record afresh.
    assert_branch(image, 0x846E0578, 0x846F8A60)
    assert_word(image, 0x846E0574, 0x388B4940, "Startup descriptor construction")
    assert_word(image, 0x84A5A4A0, 0x388B6D38, "Team Select descriptor construction")
    assert_branch(image, 0x84A5A4A8, 0x846F9018)
    expect(image.utf16(0x84612064), "Team Select", "Team Select name")
    expect(image.u32(0x820F6D70), 0x820F6D0C, "Team Select +0x38 exit policy")
    team_policy_words = [image.u32(0x820F6D0C + index * 4) for index in range(10)]
    expect(
        team_policy_words,
        [0x84A59B10, 0x820F4350, 1, 0x846AF620, 0, 1, 0x84A682C8, 0, 0, 0],
        "Team Select exit-policy words",
    )

    # Generic event 0x1B path obtains active descriptor +0x38 and invokes
    # policy[0](runtime, policy[1]).
    assert_branch(image, 0x846F2728, 0x846F0058)
    assert_word(image, 0x846F0088, 0x817E0038, "descriptor +0x38 load")
    assert_word(image, 0x846F015C, 0x808B0004, "exit-policy argument load")
    assert_word(image, 0x846F0160, 0x816B0000, "exit-policy callback load")
    assert_word(image, 0x846F0168, 0x4E800421, "exit-policy indirect call")

    # The Main-valued argument is not a construction edge in the proved callback
    # closure: every path ends at 0x846F5518, whose only r4 use is a null test.
    assert_branch(image, 0x84A59B50, 0x846F5518)
    assert_branch(image, 0x84A59B80, 0x84A59A10)
    assert_branch(image, 0x84A59B9C, 0x84A59758)
    assert_branch(image, 0x84A597BC, 0x846F5518)
    assert_branch(image, 0x84A597F4, 0x846DE230)
    assert_branch(image, 0x846DE38C, 0x846F5518)
    assert_word(image, 0x846F552C, 0x2B040000, "generic close r4 null test")
    close_targets = image.direct_targets(0x846F5518, 0x846F5580)
    forbidden_constructors = {hx(value) for value in (0x846F45E0, 0x846F60E8, 0x846F8A60, 0x846F8F00, 0x846F9018)}
    expect(
        [row for row in close_targets if row["target"] in forbidden_constructors],
        [],
        "descriptor constructors in generic close trigger",
    )

    # Main's direct descriptor-selected LAYT is quicknav, not layout_mainmenu.
    main_words = [image.u32(0x820F4350 + index * 4) for index in range(18)]
    expect(main_words[0], 0x8460C04C, "Main title pointer")
    expect(main_words[3], 0x846F2E00, "Main callback")
    expect(main_words[11], 0x8460C088, "Main LAYT name pointer")
    expect(image.utf16(0x8460C04C), "Main Menu", "Main title")
    expect(image.utf16(0x8460C088), "quicknav", "Main LAYT name")
    expect(zlib.crc32(b"quicknav") & 0xFFFFFFFF, 0x210FFA23, "quicknav CRC")
    assert_word(image, 0x846EFDA0, 0x807E002C, "descriptor +0x2C layout-name load")
    assert_branch(image, 0x846EFDAC, 0x84B20E48)
    assert_branch(image, 0x846EFDE0, 0x84B16398)
    assert_word(image, 0x82016730, 0x86A1AC9E, "LAYT type constant")
    assert_branch(image, 0x846EFDF8, 0x846EE1A8)
    quicknav_rows = [
        row
        for row in candidates
        if row["inner_name"] == "quicknav" and row["type_name"] == "LAYT"
    ]
    expect(len(quicknav_rows), 1, "quicknav LAYT candidate count")
    expect(
        (quicknav_rows[0]["outer_table_index"], quicknav_rows[0]["inner_index"], quicknav_rows[0]["outer_name_candidate"]),
        ("1310", "57", "global.iff"),
        "quicknav physical identity",
    )

    # The v5 orphan wrapper is exact code but has no PDATA entry, direct branch,
    # or fullword pointer in the reconstructed image.
    assert_word(image, 0x84A56950, 0x3D60820F, "orphan wrapper lis")
    assert_word(image, 0x84A56954, 0x388B4350, "orphan wrapper Main descriptor")
    assert_branch(image, 0x84A56958, 0x846F60E8, link=False)
    expect(image.u32(0x84A5695C), 0, "orphan wrapper trailing alignment")
    pdata = pdata_rows(image)
    expect(pdata[0x84A56900][2], 0x84A56950, "preceding PDATA end")
    expect(0x84A56950 in pdata, False, "orphan wrapper PDATA entry")
    expect(image.direct_branch_sites(0x84A56950), [], "orphan wrapper direct branches")
    expect(image.occurrences((0x84A56950).to_bytes(4, "big")), [], "orphan wrapper fullword pointers")

    portme = [
        {
            "address": "0x82015320/0x846E0528",
            "reason": "name TitlePage key 11 and prove its live input dispatch; the static TitlePage-to-StartupMenu callback edge remains exact",
        },
        {
            "address": "0x820F4350/0x820F6D0C/0x846F5518",
            "reason": "find a genuine cold-boot Main construction; Team Select owns Main as exit-policy callback argument, but the proved callback closure only tests that argument for non-null before generic close/back work",
        },
        {
            "address": "0x84A56950",
            "reason": "recover any indirect or computed runtime owner of the three-instruction Main tail wrapper; it has no PDATA entry, direct branch, fullword pointer, or Ghidra reference",
        },
        {
            "address": "0x48C6D154/0x846EFD38",
            "reason": "prove a runtime instantiation consumer for frontend_sync inner 53 layout_mainmenu; Main's direct descriptor path selects global.iff quicknav and no decoded LAYT payload serializes a name/hash edge to layout_mainmenu",
        },
    ]

    report: dict[str, Any] = {
        "schema": "vc_apf_frontend_main_ownership/v6",
        "source": {
            "xex": args.apf_xex.as_posix(),
            "xex_size": len(xex_data),
            "xex_sha256": digest(xex_data),
            "reconstructed_pe": args.apf_pe.name,
            "reconstructed_pe_size": len(image.data),
            "reconstructed_pe_sha256": digest(image.data),
            "ghidra_program_md5": "217eea6084c3d03f0f1143802b1f5636",
            "inputs": inputs,
            "packs": pack_pins,
        },
        "scope": {
            "launches_original_menu": False,
            "writes_executable": False,
            "writes_ghidra_project": False,
            "boot_frontend_sync_request_proved": True,
            "frontend_sync_outer_identity_proved": True,
            "boot_static_path_to_team_select_proved": True,
            "team_select_owns_main_policy_argument_proved": True,
            "team_select_policy_constructs_main_proved": False,
            "cold_boot_to_main_menu_proved": False,
            "main_direct_layout_is_quicknav_proved": True,
            "main_direct_layout_is_layout_mainmenu": False,
            "layout_mainmenu_runtime_instantiation_proved": False,
            "orphan_main_wrapper_owner_proved": False,
        },
        "recovered_boundaries": boundary_rows(image),
        "boot_frontend_sync_request": {
            "bootstrap_call": {"site": hx(0x84691BB8), "callee": hx(0x8467CA70)},
            "request_function": {"address": hx(0x8467CA70), "end_exclusive": hx(0x8467CB20)},
            "string_base": hx(0x84502260),
            "string_construction": {
                "base_lis_site": hx(0x8467CA7C),
                "base_addi_site": hx(0x8467CA84),
                "cross_register_addi_site": hx(0x8467CAAC),
                "result": hx(0x8450232C),
                "value": "frontend_sync.iff",
                "why_v5_missed_it": "v5 searched same-register classic absolute constructions; this compiler sequence adds +0xCC from a retained r31 base",
            },
            "request": {
                "site": hx(0x8467CACC),
                "callee": hx(0x8468DA70),
                "manager": hx(0x84F43800),
                "request_object": hx(0x84D21F68),
                "group_hash": hx(0x48181338),
                "group_hash_derivation": "CRC32 uppercase ASCII FRONTEND_SYNC",
                "archive_name": "frontend_sync.iff",
            },
            "request_dispatch": {
                "address": hx(0x8468DA70),
                "default_callee": hx(0x8468D7D0),
                "override_callee": hx(0x8468D870),
                "argument_flow": "input r5 hash -> r29 -> lower r6; input r6 archive-name pointer -> r28 -> lower r7",
            },
            "ordering": "after TitlePage descriptor registration at 0x84691B74 and before the frontend main loop begins",
        },
        "frontend_bundle": bundle,
        "boot_to_main_boundary": {
            "proved_static_prefix": [
                "XEX entry -> frontend bootstrap",
                "TitlePage_Menu registration",
                "TitlePage key-11 static callback -> StartupMenu",
                "StartupMenu recovered fallthrough -> Team Select",
            ],
            "title_key_11_live_dispatch_proved": False,
            "team_select_descriptor": {
                "address": hx(0x820F6D38),
                "name": "Team Select",
                "exit_policy_field": "+0x38",
                "exit_policy": hx(0x820F6D0C),
                "exit_policy_callback": hx(0x84A59B10),
                "exit_policy_argument": hx(0x820F4350),
                "exit_policy_argument_name": "Main Menu",
                "raw_words": [hx(value) for value in team_policy_words],
            },
            "runtime_policy_dispatch": {
                "generic_callback_event": "0x1B",
                "dispatcher": hx(0x846F0058),
                "descriptor_policy_load_site": hx(0x846F0088),
                "callback_load_site": hx(0x846F0160),
                "argument_load_site": hx(0x846F015C),
                "indirect_call_site": hx(0x846F0168),
            },
            "policy_argument_audit": {
                "selector": hx(0x84A59B10),
                "mode_2_route": hx(0x84A59A10),
                "mode_4_route": hx(0x84A59758),
                "mode_specific_route": hx(0x846DE230),
                "common_endpoint": hx(0x846F5518),
                "endpoint_r4_use": "only cmplwi r4,0 at 0x846F552C; the pointer value is not stored or passed to a state-construction helper in this extent",
                "known_constructor_targets_absent": sorted(forbidden_constructors),
                "result": "exact Main-valued callback argument, but not an exact Main descriptor construction edge",
            },
            "cold_boot_to_main_menu_proved": False,
        },
        "main_direct_layout": {
            "descriptor": hx(0x820F4350),
            "name": "Main Menu",
            "descriptor_layout_field": "+0x2C",
            "descriptor_layout_name": "quicknav",
            "descriptor_layout_crc32": hx(0x210FFA23),
            "lookup_function": hx(0x846EFD38),
            "name_load_site": hx(0x846EFDA0),
            "hash_call_site": hx(0x846EFDAC),
            "lookup_call_site": hx(0x846EFDE0),
            "initialize_call_site": hx(0x846EFDF8),
            "type": "LAYT",
            "type_hash": hx(0x86A1AC9E),
            "physical_resource": {"archive": "global.iff", "outer_index": 1310, "inner_index": 57},
            "layout_mainmenu_direct_owner_status": "disproved for this descriptor-selected LAYT path; the exact selected resource is quicknav",
        },
        "layout_mainmenu_cross_reference_audit": layout_scan,
        "orphan_main_wrapper": {
            "range": "0x84A56950..0x84A5695B",
            "descriptor": hx(0x820F4350),
            "tail_target": hx(0x846F60E8),
            "preceding_pdata_function_end_exclusive": hx(0x84A56950),
            "next_pdata_function": hx(0x84A56960),
            "pdata_entry": None,
            "direct_branch_sites": [],
            "fullword_pointer_sites": [],
            "ghidra_references": [],
            "owner_status": "unproved; exact code with no static incoming edge",
        },
        "ghidra": {
            "trace": args.trace.name,
            "trace_sha256": digest(args.trace.read_bytes()),
            "pseudo_c": args.pseudo.name,
            "pseudo_c_sha256": digest(args.pseudo.read_bytes()),
            "transient_rebuild_count": 10,
            "read_only": True,
            "pseudo_warning_count": pseudo.count("/* WARNING:"),
            "pseudo_portme_count": pseudo.count("// PORTME:"),
        },
        "portme": portme,
    }
    return report


def tsv_rows(report: dict[str, Any]) -> Iterable[list[str]]:
    yield ["frontend_archive", "proved", "0x84691BB8", "0x8467CA70", "boot calls frontend_sync request"]
    yield ["frontend_archive", "proved", "0x8467CAAC", "0x8450232C", "cross-register construction of frontend_sync.iff"]
    yield ["frontend_archive", "proved", "0x8467CACC", "0x8468DA70", "request forwards archive name and group hash"]
    yield ["frontend_archive", "proved", "0xF69D21E4", "outer 1493", "CRC32(FRONTEND_SYNC.IFF) physical identity"]
    yield ["boot_state", "proved_static", "0x84A5A4A8", "0x820F6D38", "StartupMenu fallthrough replaces with Team Select"]
    yield ["main_policy_argument", "proved", "0x820F6D0C", "0x820F4350", "Team Select +0x38 policy callback argument is Main Menu"]
    yield ["main_construction", "not_proved", "0x846F5518", "", "policy endpoint only tests argument for non-null"]
    yield ["main_direct_layout", "proved", "0x846EFD38", "0x210FFA23", "Main descriptor selects global.iff quicknav"]
    yield ["layout_mainmenu_direct_path", "disproved", "0x820F4350+0x2C", "0x48C6D154", "descriptor-selected path is quicknav, not layout_mainmenu"]
    yield ["layout_mainmenu_instantiation", "blocked", "0x48C6D154", "", "no runtime instantiation consumer proved"]
    yield ["layout_cross_reference", "negative", "161 LAYTs", "0 hits", "no serialized big-endian hash edge; sole name hit is self-name"]
    yield ["main_wrapper", "proved_unowned", "0x84A56950", "0x846F60E8", "no PDATA/direct-branch/fullword/Ghidra incoming edge"]


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["category", "status", "address", "target", "evidence"])
        writer.writerows(tsv_rows(report))


def write_portme(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "#include <stdint.h>",
        "",
        "void vc_apf_frontend_main_ownership_v6_portme(void)",
        "{",
    ]
    for item in report["portme"]:
        lines.append(
            f"    // PORTME: APF function/data at {item['address']}: {item['reason']}."
        )
    lines.extend(["    (void)(uint32_t)0;", "}", ""])
    path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--outer-index", type=Path, required=True)
    parser.add_argument("--outer-manifest", type=Path, required=True)
    parser.add_argument("--inner-candidates", type=Path, required=True)
    parser.add_argument("--base-menu", type=Path, required=True)
    parser.add_argument("--base-closure", type=Path, required=True)
    parser.add_argument("--v5-report", type=Path, required=True)
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
        "APF_FRONTEND_MAIN_OWNERSHIP_V6_REPORT_COMPLETE "
        f"boundaries={len(report['recovered_boundaries'])} "
        f"layouts={report['layout_mainmenu_cross_reference_audit']['layout_file_count']} "
        f"portme={len(report['portme'])}"
    )


if __name__ == "__main__":
    main()
