#!/usr/bin/env python3
"""Build an emulator-only NFL 2K5 catch-strength A/B candidate XISO.

The stock Human/CPU Catching values live in virtual ``.data`` and therefore
have no raw XBE bytes to replace.  Gameplay snapshots those values through two
file-backed getter functions.  This experiment redirects only those two getter
operands to an existing read-only float constant (1.25, 1.50, or 2.00), then
refreshes the owning ``.text`` section digest inside a new copied XISO.

This proves a bounded transport into the cached gameplay slider matrix.  It
does *not* prove final catch/drop polarity, effect size, downstream clamping,
or original-hardware signature acceptance.  Those require the controlled xemu
A/B described in the product findings.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import struct
import sys

import nfl_uniform_color_xiso_direct_patch as xiso
from xbe_info import XbeError


SCHEMA = "2k5_mod_studio_catch_strength_experiment/v1"
SOURCE_XISO_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
SOURCE_XISO_SIZE = 6_300_499_968
SOURCE_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
SOURCE_XBE_SIZE = 11_948_032
GETTERS = {
    "human": {"function_va": 0x0017B6D0, "stock_global_va": 0x00E600F4},
    "cpu": {"function_va": 0x0017B880, "stock_global_va": 0x00E60118},
}

# Each address is an already mapped little-endian float in the stock .rdata
# section.  No new constant and no stock payload are embedded in this tool.
PRESETS = {
    "125": {"label": "125% experimental", "value": 1.25,
            "constant_va": 0x004EF1CC},
    "150": {"label": "150% experimental", "value": 1.50,
            "constant_va": 0x004EDB34},
    "200": {"label": "200% experimental", "value": 2.00,
            "constant_va": 0x004EDB00},
}


class CatchExperimentError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CatchExperimentError(message)


def _section_digest(payload: bytes, raw: int, size: int) -> bytes:
    return hashlib.sha1(struct.pack("<I", size) + payload[raw:raw + size]).digest()  # nosec B324


def _patch_xbe(payload: bytes, preset_name: str) -> tuple[bytes, dict[str, object]]:
    require(preset_name in PRESETS, "unknown catch-strength preset")
    require(len(payload) == SOURCE_XBE_SIZE and payload[:4] == b"XBEH",
            "default.xbe size or magic mismatch")
    require(hashlib.sha256(payload).hexdigest() == SOURCE_XBE_SHA256,
            "default.xbe is not the supported retail executable")

    # Xbe is deliberately path-backed.  The source caller has already opened
    # and pinned the exact XISO extent; use its static parser on a private temp
    # file only when invoked standalone would add needless disk mutation.  The
    # compact section mapping below follows the XBE header directly instead.
    image_base = struct.unpack_from("<I", payload, 0x104)[0]
    section_count, section_table_va = struct.unpack_from("<II", payload, 0x11C)
    table_offset = section_table_va - image_base
    require(image_base == 0x00010000 and section_count == 22,
            "default.xbe image/section boundary mismatch")
    sections: list[dict[str, int | str | bytes]] = []
    for index in range(section_count):
        header = table_offset + index * 56
        fields = struct.unpack_from("<9I20s", payload, header)
        name_offset = fields[5] - image_base
        end = payload.find(b"\0", name_offset, name_offset + 64)
        require(end >= 0, "XBE section name is not terminated")
        name = payload[name_offset:end].decode("ascii")
        sections.append({
            "index": index,
            "header": header,
            "name": name,
            "va": fields[1],
            "vsize": fields[2],
            "raw": fields[3],
            "raw_size": fields[4],
            "stored_digest": fields[9],
        })
    text = next((row for row in sections if row["name"] == ".text"), None)
    rdata = next((row for row in sections if row["name"] == ".rdata"), None)
    require(text is not None and rdata is not None,
            "default.xbe is missing .text or .rdata")

    def va_to_offset(address: int, size: int) -> int:
        for row in sections:
            va = int(row["va"])
            raw_size = int(row["raw_size"])
            if va <= address and address + size <= va + raw_size:
                return int(row["raw"]) + address - va
        raise CatchExperimentError(
            f"XBE address 0x{address:08x} has no file-backed bytes"
        )

    text_raw = int(text["raw"])
    text_size = int(text["raw_size"])
    source_digest = _section_digest(payload, text_raw, text_size)
    require(source_digest == bytes(text["stored_digest"]),
            "retail .text section digest does not match")
    preset = PRESETS[preset_name]
    constant_va = int(preset["constant_va"])
    constant_offset = va_to_offset(constant_va, 4)
    require(struct.unpack_from("<f", payload, constant_offset)[0] == preset["value"],
            "preset float constant changed in default.xbe")

    patched = bytearray(payload)
    getter_rows: list[dict[str, object]] = []
    semantic_offsets: list[int] = []
    for owner, descriptor in GETTERS.items():
        function_va = descriptor["function_va"]
        function_offset = va_to_offset(function_va, 6)
        # Decode the two-byte x87 absolute-load form and its operand.  The
        # source hash is the authoritative preimage pin; this check prevents a
        # future address arithmetic error without carrying an instruction blob.
        require(payload[function_offset] == 0xD9 and payload[function_offset + 1] == 0x05,
                f"{owner} Catching getter is not an absolute float load")
        operand_offset = function_offset + 2
        stock_operand = struct.unpack_from("<I", payload, operand_offset)[0]
        require(stock_operand == descriptor["stock_global_va"],
                f"{owner} Catching getter no longer reads its stock global")
        struct.pack_into("<I", patched, operand_offset, constant_va)
        semantic_offsets.extend(range(operand_offset, operand_offset + 4))
        getter_rows.append({
            "owner": owner,
            "function_virtual_address": f"0x{function_va:08x}",
            "operand_file_offset": operand_offset,
            "stock_global_virtual_address": f"0x{stock_operand:08x}",
            "preset_constant_virtual_address": f"0x{constant_va:08x}",
        })

    output_digest = _section_digest(bytes(patched), text_raw, text_size)
    digest_offset = int(text["header"]) + 36
    patched[digest_offset:digest_offset + 20] = output_digest
    output = bytes(patched)
    changed = [
        index for index, (before, after) in enumerate(zip(payload, output))
        if before != after
    ]
    authorized = set(semantic_offsets) | set(range(digest_offset, digest_offset + 20))
    require(changed and set(changed) <= authorized,
            "catch experiment changed bytes outside its two operands and digest")
    # Both four-byte operands are semantically replaced, although common zero
    # bytes need not appear in the physical difference list.
    require(all(
        struct.unpack_from("<I", output, offset)[0] == constant_va
        for offset in (row["operand_file_offset"] for row in getter_rows)
    ), "a catch-strength operand did not receive the preset address")
    require(_section_digest(output, text_raw, text_size) ==
            output[digest_offset:digest_offset + 20],
            "patched .text digest did not verify")
    require(payload[4:0x104] == output[4:0x104],
            "XBE RSA signature bytes changed")
    return output, {
        "preset": preset_name,
        "label": preset["label"],
        "effective_value": preset["value"],
        "constant_virtual_address": f"0x{constant_va:08x}",
        "getters": getter_rows,
        "text_section": {
            "index": text["index"],
            "raw_offset": text_raw,
            "raw_size": text_size,
            "digest_header_offset": digest_offset,
            "source_digest": source_digest.hex(),
            "output_digest": output_digest.hex(),
        },
        "changed_xbe_offsets": changed,
        "semantic_operand_bytes": 8,
        "section_digest_recomputed": True,
        "rsa_signature_bytes_unchanged": True,
        "retail_signature_valid_after_patch": False,
    }


def run(
    source_path: Path,
    output_path: Path,
    manifest_path: Path,
    preset_name: str,
) -> dict[str, object]:
    source = source_path.expanduser().resolve(strict=True)
    output = xiso.canonical_new_path(output_path)
    manifest = xiso.canonical_new_path(manifest_path)
    require(output != source and manifest not in {source, output},
            "source, output, and manifest must be different paths")
    require(not output.exists() and not manifest.exists(),
            "output XISO and manifest must be new paths")
    source_info = source.lstat()
    require(stat.S_ISREG(source_info.st_mode) and not stat.S_ISLNK(source_info.st_mode),
            "source XISO must be a non-symlink regular file")

    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    output_owned: xiso.OwnedFile | None = None
    manifest_owned: xiso.OwnedFile | None = None
    success = False
    try:
        opened = os.fstat(source_fd)
        require(opened.st_size == SOURCE_XISO_SIZE,
                "source XISO has the wrong size")
        source_identity = xiso.fd_identity(source_fd)
        require(xiso.path_identity(source) == source_identity,
                "source pathname changed after read-only open")
        source_sha_before = xiso.sha256_fd(source_fd)
        require(source_sha_before == SOURCE_XISO_SHA256,
                "source is not the supported NFL 2K5 USA retail XISO")
        entries, directory = xiso.parse_xdvdfs(source_fd, opened.st_size)
        xbe_entry = entries.get("default.xbe")
        require(xbe_entry is not None and xbe_entry.size == SOURCE_XBE_SIZE,
                "default.xbe extent is missing or changed")
        source_xbe = xiso.read_exact(
            source_fd, xbe_entry.byte_offset, xbe_entry.size
        )
        patched_xbe, patch = _patch_xbe(source_xbe, preset_name)

        xbe_differences = patch["changed_xbe_offsets"]
        require(isinstance(xbe_differences, list), "internal difference ledger error")
        absolute_differences = {
            xbe_entry.byte_offset + int(offset) for offset in xbe_differences
        }
        output_owned = xiso.reserve_file(output)
        require(output_owned.identity != source_identity,
                "output XISO aliases the source inode")
        copy_method = xiso.copy_fd_exact(source_fd, output_owned.descriptor, opened.st_size)
        for offset in xbe_differences:
            absolute = xbe_entry.byte_offset + int(offset)
            amount = os.pwrite(
                output_owned.descriptor,
                patched_xbe[int(offset):int(offset) + 1],
                absolute,
            )
            require(amount == 1, "short catch-experiment XISO write")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual_differences = xiso.compare_and_hash(
            source_fd, output_owned.descriptor, opened.st_size, absolute_differences
        )
        require(source_sha_after == source_sha_before,
                "source XISO changed during catch experiment")
        require(xiso.read_exact(
            output_owned.descriptor, xbe_entry.byte_offset, xbe_entry.size
        ) == patched_xbe, "patched default.xbe readback mismatch")
        output_entries, output_directory = xiso.parse_xdvdfs(
            output_owned.descriptor, opened.st_size
        )
        require(output_entries == entries and output_directory == directory,
                "XDVDFS layout changed")

        document: dict[str, object] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source),
                "size": opened.st_size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "opened_read_only": True,
                "modified": False,
            },
            "xdvdfs": {
                **directory,
                "tree_and_extents_identical": True,
                "default_xbe_sector": xbe_entry.sector,
                "default_xbe_size": xbe_entry.size,
            },
            "patch": patch,
            "output": {
                "path": str(output),
                "size": opened.st_size,
                "sha256": output_sha,
                "copy_method": copy_method,
                "changed_byte_count": len(actual_differences),
                "exclusively_created": True,
            },
            "claims": {
                "emulator_only": True,
                "source_iso_modified": False,
                "cached_gameplay_slider_route_patched": True,
                "final_catch_drop_polarity_proved": False,
                "effect_size_measured": False,
                "downstream_clamping_excluded": False,
                "xemu_booted": False,
                "runtime_catch_sample_collected": False,
                "original_hardware_supported": False,
                "product_preset_unlocked": False,
            },
        }
        manifest_owned = xiso.reserve_file(manifest, 0o600)
        xiso.write_owned_json(manifest_owned, document)
        require(xiso.path_identity(source) == source_identity and
                xiso.owned_path_matches(output_owned) and
                xiso.owned_path_matches(manifest_owned),
                "an artifact pathname changed during publication")
        success = True
        return document
    finally:
        os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            xiso.unlink_if_owned(manifest_owned)
            xiso.unlink_if_owned(output_owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preset", required=True, choices=tuple(PRESETS))
    args = parser.parse_args()
    try:
        result = run(
            args.source_xiso, args.output_xiso, args.manifest, args.preset
        )
    except (CatchExperimentError, XbeError, xiso.PatchError, OSError,
            struct.error, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL2K5_CATCH_STRENGTH_EXPERIMENT_COMPLETE "
        f"preset={result['patch']['preset']} "
        f"changed={result['output']['changed_byte_count']} "
        f"sha256={result['output']['sha256']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
