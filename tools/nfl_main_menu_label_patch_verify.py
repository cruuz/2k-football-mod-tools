#!/usr/bin/env python3
"""Independently verify an NFL 2K5 Main Menu literal XBE patch.

This verifier intentionally does not import the writer.  It reparses the XBE
section table, resolves each source-row pointer through virtual-to-file
mapping, checks every section SHA-1, reconstructs the expected changed-byte
allowlist from the edit document, and rejects any change outside the seven
literal slots plus the one ``.string_`` digest field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any


SCHEMA = "nfl2k5_main_menu_label_patch/v1"
EDITS_SCHEMA = "nfl2k5_main_menu_label_edits/v1"
SOURCE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
SOURCE_SIZE = 11_948_032
XBE_BASE = 0x00010000
SECTION_COUNT = 22
SECTION_TABLE_OFFSET = 0x370
SECTION_SIZE = 0x38
STRING_SECTION_INDEX = 14
STRING_SECTION_HEADER = 0x680
STRING_DIGEST_OFFSET = 0x6A4
RSA_OFFSET = 4
RSA_SIZE = 256

ROWS = (
    ("quick_game", 0, 0x005154C0, 0, 0x00E8B138, 24, "Quick Game"),
    ("game_modes", 1, 0x005154F4, 0, 0x00E8B150, 24, "Game Modes"),
    ("the_crib", 2, 0x00515528, 9, 0x00E8B168, 28, "The Crib|TM|"),
    ("features", 3, 0x0051555C, 0, 0x00E8B184, 20, "Features"),
    ("options", 4, 0x00515590, 0, 0x00E8B198, 16, "Options"),
    ("xbox_live", 5, 0x005155C4, 0, 0x00E8B1A8, 20, "Xbox Live"),
    ("extras", 6, 0x005155F8, 0, 0x00E8B1BC, 16, "Extras"),
)


class VerifyError(ValueError):
    """The independently observed patch differs from its narrow contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def xbe_sha1(value: bytes) -> bytes:
    return hashlib.sha1(struct.pack("<I", len(value)) + value).digest()


def runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "XBE sizes differ")
    result: list[list[int]] = []
    for offset, pair in enumerate(zip(before, after)):
        if pair[0] == pair[1]:
            continue
        if not result or offset != result[-1][1] + 1:
            result.append([offset, offset])
        else:
            result[-1][1] = offset
    return result


def sections(data: bytes) -> list[dict[str, int | bytes]]:
    require(data[:4] == b"XBEH", "not an XBE")
    require(struct.unpack_from("<I", data, 0x104)[0] == XBE_BASE,
            "XBE base changed")
    require(struct.unpack_from("<I", data, 0x11C)[0] == SECTION_COUNT,
            "section count changed")
    table = struct.unpack_from("<I", data, 0x120)[0] - XBE_BASE
    require(table == SECTION_TABLE_OFFSET, "section table moved")
    result: list[dict[str, int | bytes]] = []
    for index in range(SECTION_COUNT):
        header = table + index * SECTION_SIZE
        fields = struct.unpack_from("<9I", data, header)
        va, virtual_size, raw, raw_size = fields[1:5]
        require(raw + raw_size <= len(data), f"section {index} exceeds XBE")
        stored = data[header + 0x24:header + 0x38]
        computed = xbe_sha1(data[raw:raw + raw_size])
        require(stored == computed, f"section {index} SHA-1 mismatch")
        result.append({
            "index": index, "header": header, "va": va,
            "virtual_size": virtual_size, "raw": raw, "raw_size": raw_size,
            "digest_offset": header + 0x24, "digest": stored,
        })
    return result


def file_offset(parsed: list[dict[str, int | bytes]], va: int, size: int) -> int:
    matches = []
    for section in parsed:
        start = int(section["va"])
        raw_size = int(section["raw_size"])
        if start <= va and va + size <= start + raw_size:
            matches.append(int(section["raw"]) + va - start)
    require(len(matches) == 1, f"VA 0x{va:08x}+0x{size:x} is not uniquely file-backed")
    return matches[0]


def decode_slot(data: bytes, offset: int, size: int) -> tuple[str, bytes]:
    slot = data[offset:offset + size]
    require(len(slot) == size and size % 2 == 0, "invalid literal slot")
    end = None
    for cursor in range(0, size, 2):
        if slot[cursor:cursor + 2] == b"\0\0":
            end = cursor
            break
    require(end is not None, "literal slot is not NUL terminated")
    assert end is not None
    try:
        text = slot[:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise VerifyError("literal slot is invalid UTF-16LE") from exc
    require(not any(slot[end + 2:]), "literal slot has nonzero bytes after terminator")
    require(text and all(0x20 <= ord(char) <= 0x7E for char in text),
            "literal slot is not nonempty printable ASCII")
    return text, slot


def verify(source_path: Path, output_path: Path, edits_path: Path,
           manifest_path: Path) -> dict[str, Any]:
    source = source_path.read_bytes()
    output = output_path.read_bytes()
    require(len(source) == SOURCE_SIZE and digest(source) == SOURCE_SHA256,
            "source is not the pinned retail XBE")
    require(len(output) == len(source), "output XBE size changed")
    source_sections = sections(source)
    output_sections = sections(output)
    target_source = source_sections[STRING_SECTION_INDEX]
    target_output = output_sections[STRING_SECTION_INDEX]
    require(int(target_source["header"]) == STRING_SECTION_HEADER and
            int(target_source["digest_offset"]) == STRING_DIGEST_OFFSET,
            ".string_ section header moved")
    require(target_source["raw"] == target_output["raw"] and
            target_source["raw_size"] == target_output["raw_size"] and
            target_source["va"] == target_output["va"],
            ".string_ section allocation changed")
    for index, (before, after) in enumerate(zip(source_sections, output_sections)):
        if index != STRING_SECTION_INDEX:
            require(before == after, f"non-target section header {index} changed")

    edits_doc = json.loads(edits_path.read_text(encoding="utf-8"))
    require(isinstance(edits_doc, dict) and edits_doc.get("schema") == EDITS_SCHEMA,
            "edits schema mismatch")
    labels = edits_doc.get("labels")
    require(isinstance(labels, dict) and labels, "edits labels are invalid")
    known = {row[0] for row in ROWS}
    require(set(labels) <= known, "edits contain unknown selectors")

    allowed = bytearray(len(source))
    observed_rows: list[dict[str, Any]] = []
    for selector, index, row_va, row_type, label_va, slot_size, original in ROWS:
        row_offset = file_offset(source_sections, row_va, 0x34)
        out_row_offset = file_offset(output_sections, row_va, 0x34)
        require(row_offset == out_row_offset, f"{selector}: source row mapping changed")
        require(source[row_offset:row_offset + 0x34] ==
                output[row_offset:row_offset + 0x34],
                f"{selector}: source row/routing changed")
        require(struct.unpack_from("<I", source, row_offset)[0] == row_type,
                f"{selector}: source row type changed")
        source_pointer = struct.unpack_from("<I", source, row_offset + 4)[0]
        output_pointer = struct.unpack_from("<I", output, row_offset + 4)[0]
        require(source_pointer == output_pointer == label_va,
                f"{selector}: label pointer changed")
        require(source.count(struct.pack("<I", label_va)) == 1 and
                output.count(struct.pack("<I", label_va)) == 1,
                f"{selector}: label pointer is not unique")
        slot_offset = file_offset(source_sections, label_va, slot_size)
        require(slot_offset == file_offset(output_sections, label_va, slot_size),
                f"{selector}: literal mapping changed")
        source_text, _source_slot = decode_slot(source, slot_offset, slot_size)
        output_text, _output_slot = decode_slot(output, slot_offset, slot_size)
        require(source_text == original, f"{selector}: retail label changed")
        expected = labels.get(selector, original)
        require(isinstance(expected, str) and output_text == expected,
                f"{selector}: output label differs from edit document")
        if expected != original:
            allowed[slot_offset:slot_offset + slot_size] = b"\1" * slot_size
        observed_rows.append({
            "selector": selector,
            "index": index,
            "row_file_offset": row_offset,
            "label_file_offset": slot_offset,
            "source_text": source_text,
            "replacement_text": output_text,
            "changed": output_text != source_text,
        })

    sentinel_va = ROWS[-1][2] + 0x34
    sentinel = file_offset(source_sections, sentinel_va, 4)
    require(struct.unpack_from("<I", source, sentinel)[0] == 3 and
            output[sentinel:sentinel + 4] == source[sentinel:sentinel + 4],
            "seven-row sentinel changed")
    allowed[STRING_DIGEST_OFFSET:STRING_DIGEST_OFFSET + 20] = b"\1" * 20
    changed = [
        offset for offset, pair in enumerate(zip(source, output)) if pair[0] != pair[1]
    ]
    require(changed and all(allowed[offset] for offset in changed),
            "output changes escape literal slots/section digest")
    require(source[RSA_OFFSET:RSA_OFFSET + RSA_SIZE] ==
            output[RSA_OFFSET:RSA_OFFSET + RSA_SIZE],
            "retail RSA signature bytes changed")
    require(source[STRING_DIGEST_OFFSET:STRING_DIGEST_OFFSET + 20] !=
            output[STRING_DIGEST_OFFSET:STRING_DIGEST_OFFSET + 20],
            ".string_ digest did not change")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == SCHEMA, "manifest schema mismatch")
    require(manifest.get("source", {}).get("sha256") == digest(source) and
            manifest.get("source", {}).get("size") == len(source),
            "manifest source identity mismatch")
    require(manifest.get("output", {}).get("sha256") == digest(output) and
            manifest.get("output", {}).get("size") == len(output),
            "manifest output identity mismatch")
    require(manifest.get("output", {}).get("difference_runs") == runs(source, output) and
            manifest.get("output", {}).get("changed_byte_count") == len(changed),
            "manifest difference accounting mismatch")
    claims = manifest.get("claims", {})
    require(claims.get("same_xbe_size") is True and
            claims.get("fixed_literal_allocations_only") is True and
            claims.get("same_row_count_and_pointers") is True and
            claims.get("retail_rsa_signature_valid_after_patch") is False and
            claims.get("runtime_visible_pixels_proved") is False,
            "manifest claim boundary changed")
    route = manifest.get("menu_route", {})
    require(route.get("row_count") == 7 and
            route.get("strg_or_txt_lookup_consumed") is False and
            route.get("row_table_or_route_modified") is False,
            "manifest menu-route boundary changed")
    manifest_rows = manifest.get("rows", [])
    require(len(manifest_rows) == 7, "manifest row count changed")
    for observed, reported in zip(observed_rows, manifest_rows):
        require(reported.get("selector") == observed["selector"] and
                reported.get("index") == observed["index"] and
                reported.get("label_file_offset") == observed["label_file_offset"] and
                reported.get("source_text") == observed["source_text"] and
                reported.get("replacement_text") == observed["replacement_text"] and
                reported.get("changed") == observed["changed"],
                f"manifest row mismatch for {observed['selector']}")
    return {
        "output_sha256": digest(output),
        "changed_byte_count": len(changed),
        "changed_selectors": [row["selector"] for row in observed_rows if row["changed"]],
        "section_count": len(output_sections),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-xbe", required=True, type=Path)
    result.add_argument("--output-xbe", required=True, type=Path)
    result.add_argument("--edits", required=True, type=Path)
    result.add_argument("--manifest", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = verify(args.source_xbe, args.output_xbe,
                        args.edits, args.manifest)
    except (OSError, json.JSONDecodeError, VerifyError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_MAIN_MENU_LABEL_VERIFY_PASS "
        f"changed={','.join(result['changed_selectors'])} "
        f"bytes={result['changed_byte_count']} sections={result['section_count']} "
        "route_unchanged=true runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
