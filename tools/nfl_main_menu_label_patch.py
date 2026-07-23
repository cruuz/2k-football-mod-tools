#!/usr/bin/env python3
"""Patch NFL 2K5's seven proved Main Menu literals in a new XBE copy.

The pinned US Xbox executable does not obtain these labels from STRG or any
other localization archive.  Each 0x34-byte source row owns one unique pointer
to a fixed UTF-16LE literal slot in ``.string_``.  This writer preserves the
row table, pointers, routing, section sizes, and XBE size; it only replaces
ASCII text inside those seven slots and refreshes the section SHA-1 digest.

The source is opened read-only.  Both output files must be new, non-symlink
paths and are created with O_EXCL.  The retail RSA signature cannot be
regenerated and is therefore deliberately preserved but invalidated by the
signed-header mutation; use requires an environment that accepts modified
XBEs.  Runtime-visible pixels remain a separate validation boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import stat
import struct
import sys
from typing import Any


SCHEMA = "nfl2k5_main_menu_label_patch/v1"
EDITS_SCHEMA = "nfl2k5_main_menu_label_edits/v1"
SOURCE_SIZE = 11_948_032
SOURCE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
SOURCE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
XBE_MAGIC = b"XBEH"
XBE_BASE = 0x00010000
SECTION_COUNT = 22
SECTION_TABLE_OFFSET = 0x370
SECTION_HEADER_SIZE = 0x38
STRING_SECTION_INDEX = 14
STRING_SECTION_NAME = ".string_"
STRING_SECTION_HEADER_OFFSET = 0x680
STRING_SECTION_VA = 0x00E60320
STRING_SECTION_RAW_OFFSET = 0x00AEF000
STRING_SECTION_RAW_SIZE = 0x0005D3A0
STRING_SECTION_DIGEST_OFFSET = STRING_SECTION_HEADER_OFFSET + 0x24
RSA_SIGNATURE_OFFSET = 4
RSA_SIGNATURE_SIZE = 256


class LabelPatchError(ValueError):
    """A source, edit, or exclusive-output contract failed closed."""


@dataclass(frozen=True)
class LabelSlot:
    selector: str
    index: int
    source_row_va: int
    pointer_field_file_offset: int
    label_va: int
    file_offset: int
    size: int
    original: str

    @property
    def max_ascii_characters(self) -> int:
        return self.size // 2 - 1


SLOTS = (
    LabelSlot("quick_game", 0, 0x005154C0, 0x0050A9E4,
              0x00E8B138, 0x00B19E18, 24, "Quick Game"),
    LabelSlot("game_modes", 1, 0x005154F4, 0x0050AA18,
              0x00E8B150, 0x00B19E30, 24, "Game Modes"),
    LabelSlot("the_crib", 2, 0x00515528, 0x0050AA4C,
              0x00E8B168, 0x00B19E48, 28, "The Crib|TM|"),
    LabelSlot("features", 3, 0x0051555C, 0x0050AA80,
              0x00E8B184, 0x00B19E64, 20, "Features"),
    LabelSlot("options", 4, 0x00515590, 0x0050AAB4,
              0x00E8B198, 0x00B19E78, 16, "Options"),
    LabelSlot("xbox_live", 5, 0x005155C4, 0x0050AAE8,
              0x00E8B1A8, 0x00B19E88, 20, "Xbox Live"),
    LabelSlot("extras", 6, 0x005155F8, 0x0050AB1C,
              0x00E8B1BC, 0x00B19E9C, 16, "Extras"),
)
SLOT_BY_SELECTOR = {slot.selector: slot for slot in SLOTS}


@dataclass(frozen=True)
class Section:
    index: int
    header_offset: int
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    name_address: int
    digest_offset: int
    stored_digest: bytes


@dataclass(frozen=True)
class OwnedOutput:
    path: Path
    descriptor: int
    identity: tuple[int, int]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LabelPatchError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def xbe_sha1(data: bytes) -> bytes:
    """Return the XBE section digest over LE length followed by raw bytes."""
    return hashlib.sha1(struct.pack("<I", len(data)) + data).digest()


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "output XBE size changed")
    result: list[list[int]] = []
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not result or index != result[-1][1] + 1:
            result.append([index, index])
        else:
            result[-1][1] = index
    return result


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LabelPatchError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_edits(path: Path) -> dict[str, str]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except UnicodeDecodeError as exc:
        raise LabelPatchError("edits JSON is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise LabelPatchError(f"invalid edits JSON: {exc}") from exc
    require(isinstance(value, dict), "edits JSON root must be an object")
    require(set(value) == {"schema", "labels"},
            "edits JSON must contain exactly schema and labels")
    require(value["schema"] == EDITS_SCHEMA, "edits schema mismatch")
    labels = value["labels"]
    require(isinstance(labels, dict) and labels, "labels must be a nonempty object")
    unknown = sorted(set(labels) - set(SLOT_BY_SELECTOR))
    require(not unknown, f"unknown label selectors: {unknown}")
    result: dict[str, str] = {}
    for selector, replacement in labels.items():
        require(isinstance(replacement, str), f"{selector}: replacement must be a string")
        require(replacement != "", f"{selector}: replacement may not be empty")
        try:
            encoded_ascii = replacement.encode("ascii")
        except UnicodeEncodeError as exc:
            raise LabelPatchError(
                f"{selector}: only printable ASCII is proved for this writer"
            ) from exc
        require(all(0x20 <= byte <= 0x7E for byte in encoded_ascii),
                f"{selector}: ASCII controls are not allowed")
        slot = SLOT_BY_SELECTOR[selector]
        encoded = replacement.encode("utf-16le") + b"\0\0"
        require(len(encoded) <= slot.size,
                f"{selector}: {len(replacement)} characters exceed slot capacity "
                f"{slot.max_ascii_characters}")
        result[selector] = replacement
    require(any(SLOT_BY_SELECTOR[key].original != text for key, text in result.items()),
            "edits do not change any label")
    return result


def parse_sections(data: bytes) -> list[Section]:
    require(data[:4] == XBE_MAGIC, "source is not an XBE")
    base = struct.unpack_from("<I", data, 0x104)[0]
    count = struct.unpack_from("<I", data, 0x11C)[0]
    table_address = struct.unpack_from("<I", data, 0x120)[0]
    require(base == XBE_BASE, "XBE base address changed")
    require(count == SECTION_COUNT, "XBE section count changed")
    table_offset = table_address - base
    require(table_offset == SECTION_TABLE_OFFSET, "XBE section table moved")
    result: list[Section] = []
    for index in range(count):
        offset = table_offset + index * SECTION_HEADER_SIZE
        require(offset + SECTION_HEADER_SIZE <= len(data), "section header is out of bounds")
        (_flags, va, virtual_size, raw_offset, raw_size, name_address,
         _references, _head, _tail) = struct.unpack_from("<9I", data, offset)
        require(raw_offset + raw_size <= len(data), f"section {index} raw range is out of bounds")
        digest_offset = offset + 0x24
        result.append(Section(
            index=index,
            header_offset=offset,
            virtual_address=va,
            virtual_size=virtual_size,
            raw_offset=raw_offset,
            raw_size=raw_size,
            name_address=name_address,
            digest_offset=digest_offset,
            stored_digest=data[digest_offset:digest_offset + 20],
        ))
    return result


def validate_source(data: bytes) -> list[Section]:
    require(len(data) == SOURCE_SIZE, f"source size is not {SOURCE_SIZE}")
    require(sha256(data) == SOURCE_SHA256, "source XBE SHA-256 mismatch")
    require(hashlib.md5(data).hexdigest() == SOURCE_MD5, "source XBE MD5 mismatch")
    sections = parse_sections(data)
    target = sections[STRING_SECTION_INDEX]
    require(target.header_offset == STRING_SECTION_HEADER_OFFSET and
            target.virtual_address == STRING_SECTION_VA and
            target.raw_offset == STRING_SECTION_RAW_OFFSET and
            target.raw_size == STRING_SECTION_RAW_SIZE,
            ".string_ section contract changed")
    for section in sections:
        computed = xbe_sha1(
            data[section.raw_offset:section.raw_offset + section.raw_size]
        )
        require(computed == section.stored_digest,
                f"section {section.index} SHA-1 is not internally consistent")
    for slot in SLOTS:
        pointer = struct.unpack_from("<I", data, slot.pointer_field_file_offset)[0]
        require(pointer == slot.label_va, f"{slot.selector}: source-row pointer changed")
        encoded = slot.original.encode("utf-16le") + b"\0\0"
        actual = data[slot.file_offset:slot.file_offset + slot.size]
        require(actual[:len(encoded)] == encoded and not any(actual[len(encoded):]),
                f"{slot.selector}: literal slot bytes changed")
        require(data.count(struct.pack("<I", slot.label_va)) == 1,
                f"{slot.selector}: label pointer is not unique in the XBE")
    return sections


def build_patch(source: bytes, edits: dict[str, str]) -> tuple[bytes, dict[str, Any]]:
    sections = validate_source(source)
    output = bytearray(source)
    rows: list[dict[str, Any]] = []
    for slot in SLOTS:
        replacement = edits.get(slot.selector, slot.original)
        encoded = replacement.encode("utf-16le") + b"\0\0"
        padded = encoded + bytes(slot.size - len(encoded))
        output[slot.file_offset:slot.file_offset + slot.size] = padded
        rows.append({
            "selector": slot.selector,
            "index": slot.index,
            "source_row_virtual_address": f"0x{slot.source_row_va:08x}",
            "pointer_field_file_offset": slot.pointer_field_file_offset,
            "label_virtual_address": f"0x{slot.label_va:08x}",
            "label_file_offset": slot.file_offset,
            "slot_size": slot.size,
            "max_ascii_characters": slot.max_ascii_characters,
            "source_text": slot.original,
            "replacement_text": replacement,
            "changed": replacement != slot.original,
            "little_endian_pointer_occurrences": 1,
        })

    string_section = sections[STRING_SECTION_INDEX]
    old_digest = bytes(output[
        string_section.digest_offset:string_section.digest_offset + 20
    ])
    new_digest = xbe_sha1(bytes(output[
        string_section.raw_offset:string_section.raw_offset + string_section.raw_size
    ]))
    output[string_section.digest_offset:string_section.digest_offset + 20] = new_digest
    patched = bytes(output)
    require(len(patched) == len(source), "patched XBE size changed")
    require(patched[RSA_SIGNATURE_OFFSET:RSA_SIGNATURE_OFFSET + RSA_SIGNATURE_SIZE] ==
            source[RSA_SIGNATURE_OFFSET:RSA_SIGNATURE_OFFSET + RSA_SIGNATURE_SIZE],
            "retail RSA signature bytes changed")

    allowed = bytearray(len(source))
    for slot in SLOTS:
        if slot.selector in edits and edits[slot.selector] != slot.original:
            allowed[slot.file_offset:slot.file_offset + slot.size] = b"\1" * slot.size
    allowed[STRING_SECTION_DIGEST_OFFSET:STRING_SECTION_DIGEST_OFFSET + 20] = b"\1" * 20
    changed_offsets = [
        index for index, pair in enumerate(zip(source, patched)) if pair[0] != pair[1]
    ]
    require(changed_offsets and all(allowed[index] for index in changed_offsets),
            "patch changed bytes outside label slots/section digest")

    after_sections = parse_sections(patched)
    for section in after_sections:
        computed = xbe_sha1(
            patched[section.raw_offset:section.raw_offset + section.raw_size]
        )
        require(computed == section.stored_digest,
                f"patched section {section.index} SHA-1 mismatch")
    require(after_sections[STRING_SECTION_INDEX].stored_digest == new_digest,
            "patched .string_ digest was not stored")
    require(old_digest != new_digest, ".string_ digest unexpectedly did not change")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {
            "size": len(source),
            "sha256": sha256(source),
            "md5": hashlib.md5(source).hexdigest(),
            "opened_read_only": True,
        },
        "output": {
            "size": len(patched),
            "sha256": sha256(patched),
            "difference_runs": difference_runs(source, patched),
            "changed_byte_count": len(changed_offsets),
        },
        "menu_route": {
            "row_count": len(SLOTS),
            "row_stride": 0x34,
            "label_field": "+0x04 direct UTF-16LE pointer",
            "storage_class": "pinned default.xbe .string_ literal slots",
            "strg_or_txt_lookup_consumed": False,
            "row_table_or_route_modified": False,
        },
        "string_section": {
            "section_index": STRING_SECTION_INDEX,
            "name": STRING_SECTION_NAME,
            "header_file_offset": STRING_SECTION_HEADER_OFFSET,
            "virtual_address": f"0x{STRING_SECTION_VA:08x}",
            "raw_file_offset": STRING_SECTION_RAW_OFFSET,
            "raw_size": STRING_SECTION_RAW_SIZE,
            "digest_file_offset": STRING_SECTION_DIGEST_OFFSET,
            "sha1_before": old_digest.hex(),
            "sha1_after": new_digest.hex(),
            "stored_digest_matches_raw_section": True,
            "all_other_section_digests_still_match": True,
        },
        "rows": rows,
        "claims": {
            "same_xbe_size": True,
            "fixed_literal_allocations_only": True,
            "same_row_count_and_pointers": True,
            "all_text_printable_ascii_utf16le": True,
            "source_modified": False,
            "output_created_exclusively": True,
            "retail_rsa_signature_bytes_preserved": True,
            "retail_rsa_signature_valid_after_patch": False,
            "reason_signature_invalid": (
                "the .string_ section digest is in the signed XBE header; the retail "
                "private key is unavailable"
            ),
            "requires_modified_xbe_acceptance": True,
            "runtime_visible_pixels_proved": False,
            "visual_width_or_font_coverage_proved": False,
        },
    }
    return patched, report


def _canonical_new(path: Path) -> Path:
    require(path.name not in {"", ".", ".."}, "invalid output path")
    parent = path.parent.resolve(strict=True)
    require(parent.is_dir(), f"output parent is not a directory: {parent}")
    return parent / path.name


def _reserve(path: Path) -> OwnedOutput:
    canonical = _canonical_new(path)
    try:
        descriptor = os.open(
            canonical,
            os.O_CREAT | os.O_EXCL | os.O_RDWR |
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o644,
        )
    except FileExistsError as exc:
        raise LabelPatchError(f"output already exists: {canonical}") from exc
    info = os.fstat(descriptor)
    return OwnedOutput(canonical, descriptor, (info.st_dev, info.st_ino))


def _path_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino


def _write_owned(owned: OwnedOutput, payload: bytes) -> None:
    require(_path_identity(owned.path) == owned.identity,
            f"output pathname identity changed: {owned.path}")
    position = 0
    while position < len(payload):
        written = os.pwrite(owned.descriptor, payload[position:], position)
        require(written > 0, f"short output write at 0x{position:x}")
        position += written
    os.fsync(owned.descriptor)
    require(os.fstat(owned.descriptor).st_size == len(payload), "output size mismatch")
    require(_path_identity(owned.path) == owned.identity,
            f"output pathname identity changed: {owned.path}")


def _unlink_owned(owned: OwnedOutput | None) -> None:
    if owned is None:
        return
    try:
        os.close(owned.descriptor)
    finally:
        if _path_identity(owned.path) == owned.identity:
            owned.path.unlink()


def _close_owned(owned: OwnedOutput) -> None:
    os.close(owned.descriptor)


def run(source_path: Path, edits_path: Path, output_path: Path,
        manifest_path: Path) -> dict[str, Any]:
    source_canonical = source_path.resolve(strict=True)
    edits_canonical = edits_path.resolve(strict=True)
    require(source_canonical.is_file() and not source_path.is_symlink(),
            "source XBE must be a non-symlink regular file")
    require(edits_canonical.is_file() and not edits_path.is_symlink(),
            "edits JSON must be a non-symlink regular file")
    output_canonical = _canonical_new(output_path)
    manifest_canonical = _canonical_new(manifest_path)
    require(output_canonical != manifest_canonical, "output XBE and manifest alias")
    require(output_canonical != source_canonical and
            manifest_canonical != source_canonical,
            "outputs may not alias the source XBE")
    require(not output_canonical.exists() and not manifest_canonical.exists(),
            "output XBE/manifest already exists")

    source_descriptor = os.open(
        source_canonical,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        info = os.fstat(source_descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size == SOURCE_SIZE,
                "source XBE is not the pinned regular file")
        source = bytearray()
        position = 0
        while position < info.st_size:
            block = os.pread(source_descriptor, min(8 * 1024 * 1024,
                                                     info.st_size - position), position)
            require(block, "short source XBE read")
            source.extend(block)
            position += len(block)
        source_bytes = bytes(source)
        source_identity = (info.st_dev, info.st_ino)
        edits = load_edits(edits_canonical)
        patched, report = build_patch(source_bytes, edits)
        report["source"]["path"] = str(source_canonical)
        report["edits"] = {
            "path": str(edits_canonical),
            "sha256": sha256(edits_canonical.read_bytes()),
            "selectors": sorted(edits),
        }
        report["output"]["path"] = str(output_canonical)
        report["manifest_path"] = str(manifest_canonical)

        output_owned: OwnedOutput | None = None
        manifest_owned: OwnedOutput | None = None
        success = False
        try:
            output_owned = _reserve(output_canonical)
            manifest_owned = _reserve(manifest_canonical)
            _write_owned(output_owned, patched)
            manifest_payload = (
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _write_owned(manifest_owned, manifest_payload)
            require(sha256(os.pread(output_owned.descriptor, len(patched), 0)) ==
                    report["output"]["sha256"], "output XBE readback hash mismatch")
            require(json.loads(os.pread(manifest_owned.descriptor,
                                        len(manifest_payload), 0)) == report,
                    "manifest readback mismatch")
            current = os.fstat(source_descriptor)
            require((current.st_dev, current.st_ino) == source_identity and
                    sha256(source_canonical.read_bytes()) == SOURCE_SHA256,
                    "source XBE changed during copy-only patch")
            success = True
        finally:
            if success:
                assert output_owned is not None and manifest_owned is not None
                _close_owned(manifest_owned)
                _close_owned(output_owned)
            else:
                _unlink_owned(manifest_owned)
                _unlink_owned(output_owned)
        return report
    finally:
        os.close(source_descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-xbe", type=Path, required=True,
                        help="pinned retail US default.xbe (read only)")
    result.add_argument("--edits", type=Path, required=True,
                        help="strict JSON mapping existing selectors to new labels")
    result.add_argument("--output-xbe", type=Path, required=True,
                        help="new patched XBE path; must not exist")
    result.add_argument("--manifest", type=Path, required=True,
                        help="new provenance JSON path; must not exist")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = run(args.source_xbe, args.edits, args.output_xbe, args.manifest)
    except (OSError, LabelPatchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    changed = [row["selector"] for row in report["rows"] if row["changed"]]
    print(
        "NFL_MAIN_MENU_LABEL_PATCH_PASS "
        f"changed={','.join(changed)} xbe_size={report['output']['size']} "
        "section_sha1=updated rsa_signature=invalid runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
