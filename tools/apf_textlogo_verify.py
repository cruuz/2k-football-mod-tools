#!/usr/bin/env python3
"""Independent whole-volume verifier for one APF ``uniform_textlogo`` edit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Mapping

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import apf_inner
import apf_outer
import apf_pants_color_transport as bc1_transport
import apf_textlogo_patch as contract
import apf_xenos_bc1_mip_layout as bc1_mips
from mod_editor.core import platform_compat


SCHEMA = "apf2k8_textlogo_whole_volume_verify/v1"


class TextLogoVerifyError(ValueError):
    """Raised when a copied volume is not exactly one bounded wordmark edit."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_range(path: Path, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if offset < 0 or length < 0 or offset + length > metadata.st_size:
            raise TextLogoVerifyError("verification byte range is outside the volume")
        cursor = offset
        remaining = length
        while remaining:
            block = platform_compat.pread(
                descriptor, min(8 * 1024 * 1024, remaining), cursor
            )
            if not block:
                raise TextLogoVerifyError("volume ended during verification")
            digest.update(block)
            cursor += len(block)
            remaining -= len(block)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _regular_identity(path: Path) -> tuple[int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise TextLogoVerifyError(f"volume is not a regular non-symlink file: {path}")
    return info.st_dev, info.st_ino, info.st_size


def _read_entry(
    archive: apf_outer.Archive, entry: apf_outer.Entry
) -> tuple[bytes, apf_inner.IFFRecord, list[bytes], dict[str, object], bytes]:
    with apf_inner.ArchiveReader(archive) as reader:
        raw = reader.read(entry, 0, entry.size)
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    if (
        record.block_count != 2
        or record.file_count != 1
        or record.warnings
        or record.files[0].name != contract.INNER_NAME
        or record.files[0].type_name != "TXTR"
        or [(p.block_index, p.offset, p.length) for p in record.files[0].parts]
        != [(0, 0, contract.DRAM_LENGTH), (1, 0, contract.TEXTURE_LENGTH)]
    ):
        raise TextLogoVerifyError("copied wordmark package left its proved IFF class")
    metadata = apf_inner.parse_txtr_metadata(blocks[0][: contract.DRAM_LENGTH])
    try:
        contract._strict_descriptor(metadata)
    except contract.TextLogoPatchError as exc:
        raise TextLogoVerifyError(str(exc)) from exc
    texture = blocks[1][: contract.TEXTURE_LENGTH]
    locations = bc1_mips.derive_layout(metadata)
    if len(locations) != 6 or bc1_mips.transport_roundtrip(texture, locations) != texture:
        raise TextLogoVerifyError("copied wordmark packed-mip transport is invalid")
    return raw, record, blocks, metadata, texture


def verify_copied_volume(
    source: Path,
    output: Path,
    asset_index: int,
    *,
    patch_manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Prove the output differs only inside the selected fixed package range."""

    source = Path(source).expanduser().resolve(strict=True)
    output = Path(output).expanduser().resolve(strict=True)
    source_identity = _regular_identity(source)
    output_identity = _regular_identity(output)
    if source_identity[:2] == output_identity[:2]:
        raise TextLogoVerifyError("output volume aliases the read-only source")
    if source_identity[2] != output_identity[2]:
        raise TextLogoVerifyError("copied volume length changed")
    row = contract.target_record(asset_index)
    source_archive = apf_outer.parse_archive(source)
    output_archive = apf_outer.parse_archive(output)
    outer_index = int(row["outer_table_index"])
    source_entry = source_archive.entries[outer_index]
    output_entry = output_archive.entries[outer_index]
    if (
        source_entry.name_id != output_entry.name_id
        or source_entry.size != output_entry.size
        or source_entry.segments != output_entry.segments
        or source_entry.size != int(row["outer_allocation"]["size"])  # type: ignore[index]
    ):
        raise TextLogoVerifyError("selected outer entry location/allocation changed")
    offset = source_entry.segments[0].pack_offset
    prefix_source = _hash_range(source, 0, offset)
    prefix_output = _hash_range(output, 0, offset)
    suffix_offset = offset + source_entry.size
    suffix_length = source_identity[2] - suffix_offset
    suffix_source = _hash_range(source, suffix_offset, suffix_length)
    suffix_output = _hash_range(output, suffix_offset, suffix_length)
    if prefix_source != prefix_output or suffix_source != suffix_output:
        raise TextLogoVerifyError("bytes outside the selected wordmark package changed")
    source_raw, source_record, source_blocks, metadata, source_texture = _read_entry(
        source_archive, source_entry
    )
    output_raw, output_record, output_blocks, output_metadata, output_texture = _read_entry(
        output_archive, output_entry
    )
    if _sha256(source_raw) != row["outer_allocation"]["sha256"]:  # type: ignore[index]
        raise TextLogoVerifyError("source package no longer matches its retail pin")
    if output_metadata != metadata:
        raise TextLogoVerifyError("wordmark TXTR descriptor changed")
    source_parts = {
        (file_index, part_index): _sha256(
            source_blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for file_index, item in enumerate(source_record.files)
        for part_index, part in enumerate(item.parts)
    }
    output_parts = {
        (file_index, part_index): _sha256(
            output_blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for file_index, item in enumerate(output_record.files)
        for part_index, part in enumerate(item.parts)
    }
    changed_parts = [key for key in source_parts if source_parts[key] != output_parts[key]]
    if changed_parts not in ([], [(0, 1)]):
        raise TextLogoVerifyError(f"unexpected wordmark inner parts changed: {changed_parts}")
    source_footer = source_raw[
        source_record.file_length : source_record.file_length
        + 8
        + source_record.footer.payload_size  # type: ignore[union-attr]
    ]
    output_footer = output_raw[
        output_record.file_length : output_record.file_length
        + 8
        + output_record.footer.payload_size  # type: ignore[union-attr]
    ]
    if source_footer != output_footer:
        raise TextLogoVerifyError("wordmark IFF footer changed")
    locations = bc1_mips.derive_layout(metadata)
    source_mask = bc1_transport.active_byte_mask(len(source_texture), locations)
    if (
        bc1_transport.hash_inactive(source_texture, source_mask)
        != bc1_transport.hash_inactive(output_texture, source_mask)
    ):
        raise TextLogoVerifyError("inactive packed-tail bytes changed")
    level_rows: list[dict[str, object]] = []
    for location in locations:
        linear = bc1_mips.extract_linear_bc1(output_texture, location)
        rgba = bc1_transport.decode_linear_bc1(linear, location)
        level_rows.append(
            {
                "level": location.level,
                "width": location.width,
                "height": location.height,
                "linear_bc1_sha256": _sha256(linear),
                "decoded_rgba_sha256": _sha256(rgba),
            }
        )
    if patch_manifest is not None:
        if (
            patch_manifest.get("schema") != contract.SCHEMA
            or patch_manifest.get("family_target", {}).get("asset_index")  # type: ignore[union-attr]
            != asset_index
            or patch_manifest.get("family_target", {}).get("outer_table_index")  # type: ignore[union-attr]
            != outer_index
        ):
            raise TextLogoVerifyError("patch manifest identifies another wordmark target")
        expected_output = patch_manifest.get("binary_patch_manifest", {}).get(  # type: ignore[union-attr]
            "replacement_sha256"
        )
        mode = patch_manifest.get("mode")
        if mode == "no_op":
            expected_output = row["outer_allocation"]["sha256"]  # type: ignore[index]
        if expected_output != _sha256(output_raw):
            raise TextLogoVerifyError("output package does not match the patch manifest")
        manifest_levels = patch_manifest.get("levels")
        if mode == "patched":
            if not isinstance(manifest_levels, list) or len(manifest_levels) != 6:
                raise TextLogoVerifyError("patch manifest mip inventory is incomplete")
            for actual, declared in zip(level_rows, manifest_levels):
                if (
                    not isinstance(declared, dict)
                    or declared.get("level") != actual["level"]
                    or declared.get("linear_bc1_sha256_after")
                    != actual["linear_bc1_sha256"]
                    or declared.get("decoded_rgba_sha256_after")
                    != actual["decoded_rgba_sha256"]
                ):
                    raise TextLogoVerifyError("output mip does not match the patch manifest")
    if _regular_identity(source) != source_identity:
        raise TextLogoVerifyError("source volume changed during verification")
    return {
        "schema": SCHEMA,
        "asset_index": asset_index,
        "outer_table_index": outer_index,
        "outer_name": row["outer_name"],
        "source_opened_read_only": True,
        "source_entry_sha256": _sha256(source_raw),
        "output_entry_sha256": _sha256(output_raw),
        "fixed_allocation_size": source_entry.size,
        "changed_inner_parts": [list(key) for key in changed_parts],
        "descriptor_part_bit_exact": source_parts[(0, 0)] == output_parts[(0, 0)],
        "footer_bit_exact": source_footer == output_footer,
        "inactive_mip_padding_bit_exact": True,
        "all_six_mips_reopened": True,
        "levels": level_rows,
        "outside_target": {
            "prefix_length": offset,
            "prefix_sha256": prefix_source,
            "suffix_offset": suffix_offset,
            "suffix_length": suffix_length,
            "suffix_sha256": suffix_source,
            "source_and_output_match": True,
        },
        "whole_volume_size_preserved": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--asset-index", required=True, type=int)
    parser.add_argument("--patch-manifest", type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.receipt.exists() or args.receipt.is_symlink():
            raise TextLogoVerifyError("verification receipt already exists")
        manifest = (
            json.loads(args.patch_manifest.read_text(encoding="utf-8"))
            if args.patch_manifest is not None
            else None
        )
        report = verify_copied_volume(
            args.source,
            args.output,
            args.asset_index,
            patch_manifest=manifest,
        )
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            args.receipt,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o644,
        )
        try:
            payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short verification receipt write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        print(
            "APF_TEXTLOGO_VERIFY_PASS "
            f"asset={args.asset_index} outer={report['outer_table_index']} "
            f"entry={report['output_entry_sha256']}"
        )
    except (
        TextLogoVerifyError,
        contract.TextLogoPatchError,
        bc1_mips.MipLayoutError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
