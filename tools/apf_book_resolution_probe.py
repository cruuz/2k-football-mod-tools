#!/usr/bin/env python3
"""Reproduce the base-XEX book-resolution evidence without exporting game bodies.

Inputs are explicit user-owned paths. The report contains instruction words,
names, offsets, counts, and hashes only. No emulator or network is used.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError
import apf_inner
import apf_outer

PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
PE_LENGTH = 54001664
BASE = 0x82000000

# Small, selected instruction receipts. The whole-image pin makes these
# addresses unambiguous; the deliberately omitted control flow is in the report.
PIN_GROUPS = {
    "root_and_label_relocation": (
        0x84750F84, 0x8474F96C, 0x8474C438, 0x8474C450, 0x8474C454,
        0x8474C45C, 0x8474C478, 0x8474C484, 0x8473D4B0, 0x8473D4C8,
        0x8473D4CC, 0x8473D4D4, 0x8473D4D8, 0x8473D4EC, 0x8473D4F0,
        0x8473D554, 0x8473D564, 0x8473D568, 0x84747C84, 0x84747CBC,
        0x8474C210, 0x8474C21C, 0x84752F1C, 0x84752F34, 0x84752F38,
        0x84752F40, 0x84752F58, 0x84752F5C),
    "type_to_filename_and_request": (
        0x849D6224, 0x849D6238, 0x849D6248, 0x849D625C, 0x849D6268,
        0x849D6280, 0x849D6288, 0x849D6294, 0x849D6298, 0x849D629C,
        0x849D638C, 0x849D639C, 0x849D63A0, 0x849D6490, 0x849D6494,
        0x849D64B4, 0x849D64B8, 0x849D64C8, 0x849D64E4,
        0x849D820C, 0x849D8240, 0x849D8250, 0x849D8268,
        0x8468DB14, 0x8468D7FC, 0x8468D824, 0x8468D864,
        0x84B698DC, 0x84B69908, 0x84B69924, 0x84B68D50, 0x84B68D54,
        0x84B69504, 0x84B69534, 0x84B69548),
    "archive_dynamic_directory_and_hash_lookup": (
        0x84B91640, 0x84B91648, 0x84B91654, 0x84B9165C, 0x84B91660,
        0x84B91668, 0x84B9167C, 0x84B916AC, 0x84B916B4, 0x84B916BC,
        0x84B91700, 0x84B91708, 0x84B91750, 0x84B91764, 0x84B91768,
        0x84B91A50, 0x84B91380, 0x84B9138C, 0x84B91390, 0x84B91398,
        0x84B913A4, 0x84B913BC, 0x84B913C0, 0x84B913C4, 0x84B913C8,
        0x84B913CC, 0x84B913D4, 0x84B913DC, 0x84B21028, 0x84B2103C,
        0x84B21048, 0x84B2104C, 0x84B21054, 0x84B21078, 0x84B21090),
    "request_pool_and_loaded_match_books": (
        0x8468D614, 0x8468D618, 0x8468D62C, 0x8468D644, 0x8468D648,
        0x8468D66C, 0x849D4080, 0x849D4090, 0x849D40A0, 0x849D40CC,
        0x849D40E8, 0x849D4110, 0x849D4118, 0x849D4154, 0x849D4170,
        0x849D4198, 0x849D41B4, 0x849D41C8, 0x849D41F0, 0x849D420C,
        0x849D4210, 0x849FD6C8, 0x849FD6D0, 0x849FD6D8, 0x849FD6E0,
        0x849D8074, 0x849D8098, 0x849D80B0, 0x849D8124, 0x849D8148, 0x849D8160),
    "eight_saved_combined_user_books": (
        0x84AE8938, 0x84AE893C, 0x84AE8960, 0x84AE89A0, 0x84AE89DC,
        0x84AE89E8, 0x84AE8A00, 0x84AE8A28, 0x84AE8AA0, 0x84AE8AD0,
        0x84AE8B0C, 0x84AE8B14, 0x84AE8B18, 0x84AE8B20, 0x84AE8B58,
        0x84AE8B5C, 0x84AE8B60, 0x84AE8C1C, 0x84AE8C24, 0x84AE8C28,
        0x84AE8C68, 0x84AE8C70, 0x84AE8C74, 0x84750FD4, 0x84750FD8,
        0x84750FE8, 0x84750FFC, 0x84751000, 0x84751028, 0x8475102C,
        0x847510A0, 0x847510A4, 0x84AE8D24, 0x84AE8D2C, 0x84AE8F9C,
        0x84AE8FA0, 0x84AE8FAC, 0x84AE8FBC, 0x84AE8FC4),
    "two_UA_UB_working_buffers": (
        0x849FCF60, 0x849FCF64, 0x849FCF68, 0x849FCF6C,
        0x84A8F270, 0x84A8F290, 0x84A8F294, 0x84A8F2E8,
        0x84A8F2EC, 0x84A8F564, 0x84A8F584, 0x84A8F5BC, 0x84A8F5F8),
}
STRING_PINS = {
    0x845F1758: "UA", 0x845F177C: "UB", 0x845F1764: "{0}-spb.iff",
    0x845F1784: "PRACTICE-s-spb.iff", 0x845F20C4: "global-o-spb.iff",
    0x845F20E8: "global-d-spb.iff", 0x84626010: "user-o-spb.iff",
    0x846260A4: "user-d-spb.iff", 0x84618F30: "%s-spb.iff",
}


def executable_evidence(path: Path) -> dict:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != PE_LENGTH or digest != PE_SHA256:
        raise ValidationError("Expected the pinned flat base-XEX PE; TU/other images are not interchangeable")
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
    decoder = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    groups = {}
    for name, addresses in PIN_GROUPS.items():
        rows = []
        for address in addresses:
            word = data[address - BASE:address - BASE + 4]
            instructions = list(decoder.disasm(word, address))
            rows.append({"address": f"0x{address:08X}", "word": word.hex(),
                         "assembly": (instructions[0].mnemonic + " " + instructions[0].op_str)
                         if instructions else "Xenon instruction: undecoded by Capstone"})
        groups[name] = rows
    for address, expected in STRING_PINS.items():
        encoded = expected.encode("utf-16-be") + b"\0\0"
        if data[address - BASE:address - BASE + len(encoded)] != encoded:
            raise ValidationError("Executable string evidence changed")
    crc_table = []
    for value in range(256):
        for _bit in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        crc_table.append(value)
    actual = data[0x844C4DB8 - BASE:0x844C4DB8 - BASE + 1024]
    if struct.unpack(">256I", actual) != tuple(crc_table):
        raise ValidationError("Executable CRC table differs from the standard reflected CRC32 table")
    return {"sha256": digest, "bytes": len(data), "flat_base": hex(BASE), "instruction_groups": groups,
            "strings": {f"0x{x:08X}": y for x, y in STRING_PINS.items()},
            "crc_table": {"address": "0x844C4DB8", "entries": 256,
                          "polynomial": "0xEDB88320", "sha256": hashlib.sha256(actual).hexdigest()},
            "grade": "A_PROVEN static base image", "runtime_status": "UNWITNESSED"}


def archive_evidence(index_path: Path) -> tuple[dict, dict[str, bytes]]:
    archive = apf_outer.parse_archive(index_path)
    books, bodies = [], {}
    for outer, name in sorted(splb.STOCK_BOOKS.items()):
        _archive, entry, record, body, decoded, stored = identity.read_resource(
            index_path, identity.filename_id(name), "spb", "SPLB")
        book = splb.parse_book(body, entry.table_index)
        if book.name != name:
            raise ValidationError("SPLB header/filename identity mismatch")
        block = record.blocks[0]
        tokens, _used = apf_inner._parse_h7a_tokens(
            stored[block.start_offset + 20:block.start_offset + block.stored_length],
            len(decoded), block.wrapper.shift)
        bodies[name] = body
        books.append({"outer_index": entry.table_index, "stock_outer_index": outer,
                      "header_name": name, "name_id": f"0x{entry.name_id:08X}",
                      "filename": name + "-spb.iff", "decoded_bytes": len(body),
                      "populated_records": sum(x.populated for x in book.records),
                      "memberships": sum(len(x.entries) for x in book.records),
                      "file_length": record.file_length, "allocation_bytes": entry.size,
                      "h7a_overlaps": sum(x.distance is not None and x.length > x.distance for x in tokens),
                      "sha256": hashlib.sha256(body).hexdigest()})
    entries = sorted(archive.entries, key=lambda x: x.virtual_offset)
    holes = [(a.virtual_end, b.virtual_offset) for a, b in zip(entries, entries[1:])
             if a.virtual_end != b.virtual_offset]
    roster = identity.parse_roster_identity(identity.read_disc_roster(index_path))
    return {"alignment": archive.alignment, "entries": len(archive.entries),
            "table_start": archive.table_start, "table_end": archive.table_end,
            "first_payload": entries[0].virtual_offset, "virtual_size": archive.virtual_size,
            "unaccounted_payload_boundaries": holes, "tail_covered": entries[-1].virtual_end == archive.virtual_size,
            "sorted_unique_ids": [x.name_id for x in archive.entries] == sorted({x.name_id for x in archive.entries}),
            "packs": [{"name": x.name, "bytes": x.declared_size} for x in archive.packs],
            "books": books, "label_table": [asdict(x) for x in roster.labels],
            "book_identity": identity.book_identity_report(roster, {x["header_name"]: x["outer_index"] for x in books})}, bodies


def save_evidence(path: Path, templates: dict[str, bytes]) -> dict:
    data = path.read_bytes()
    extent = struct.unpack_from(">I", data)[0]
    bank_start = 4 + extent
    if bank_start + 8 * splb.RESOURCE_SIZE != len(data):
        raise ValidationError("Raw ROS does not contain exactly the traced eight-book tail")
    books = []
    for slot in range(8):
        at = bank_start + slot * splb.RESOURCE_SIZE
        body = data[at:at + splb.RESOURCE_SIZE]
        parsed = splb.parse_book(body, slot)
        books.append({"slot": slot, "offset": at, "name": parsed.name,
                      "populated_records": sum(x.populated for x in parsed.records),
                      "memberships": sum(len(x.entries) for x in parsed.records),
                      "sha256": hashlib.sha256(body).hexdigest(),
                      "matches_20_USER_o_records": body[0x70:0xE30] == templates["USER-o"][0x70:0xE30],
                      "matches_6_USER_d_records": body[0xE30:0x1250] == templates["USER-d"][0x70:0x490],
                      "mask_is_template_OR": struct.unpack_from(">I", body, 0x7E04)[0] ==
                      (struct.unpack_from(">I", templates["USER-o"], 0x7E04)[0] |
                       struct.unpack_from(">I", templates["USER-d"], 0x7E04)[0])})
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "roster_extent": extent,
            "bank_start": bank_start, "slots": books, "serialized_slots": 8,
            "grade": "A_PROVEN serialized capacity; runtime editing/selection UNWITNESSED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pe", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--save", type=Path, action="append", default=[])
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.receipt.exists():
            raise ValidationError("Receipt must be a new file")
        pe = executable_evidence(args.pe)
        archive, bodies = archive_evidence(args.source)
        report = {"schema": "apf2k8_book_resolution_evidence/v1", "pe": pe, "archive": archive,
                  "saves": [save_evidence(x, bodies) for x in args.save], "runtime_status": "UNWITNESSED"}
        with args.receipt.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(f"Pinned {sum(len(x) for x in pe['instruction_groups'].values())} instructions; "
              f"matched {len(archive['books'])} book filename hashes; inspected {len(args.save)} saves. "
              "Runtime UNWITNESSED.")
        return 0
    except (OSError, ValueError, RuntimeError, ValidationError) as exc:
        print(f"Evidence probe refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
