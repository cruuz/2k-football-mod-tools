#!/usr/bin/env python3
"""Build an emulator-only NFL 2K5 Fantasy Draft priority A/B XISO.

This experiment changes the proved seventeen-float CPU *Fantasy Draft* table
inside a copied retail XISO and refreshes the owning XBE section digest.  It
does not claim to affect the separate Franchise rookie draft.  The source XISO
is opened read-only and an output is published only after a full changed-byte
comparison succeeds.
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


SCHEMA = "2k5_mod_studio_fantasy_draft_experiment/v1"
SOURCE_XISO_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
SOURCE_XISO_SIZE = 6_300_499_968
SOURCE_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
SOURCE_XBE_SIZE = 11_948_032
TABLE_VA = 0x00589588
POSITIONS = (
    "QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB",
    "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE",
)
STOCK_WEIGHTS = (
    2.0, 0.1, 0.2, 1.4, 1.0, 1.1, 1.1, 1.7, 1.0,
    1.2, 1.2, 0.7, 0.5, 1.1, 1.3, 1.4, 1.3,
)
PRESETS = {
    "special-teams-control": (
        0.01, 100.0, 100.0, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
    ),
}


class DraftExperimentError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DraftExperimentError(message)


def _sha1_section(payload: bytes, raw: int, size: int) -> bytes:
    framed = struct.pack("<I", size) + payload[raw:raw + size]
    return hashlib.sha1(framed).digest()  # nosec B324 -- required XBE format


def _sections(payload: bytes) -> tuple[int, list[dict[str, object]]]:
    require(payload[:4] == b"XBEH", "default.xbe magic mismatch")
    image_base = struct.unpack_from("<I", payload, 0x104)[0]
    section_count, table_va = struct.unpack_from("<II", payload, 0x11C)
    require(image_base == 0x00010000 and section_count == 22,
            "default.xbe image/section boundary mismatch")
    table_offset = table_va - image_base
    rows: list[dict[str, object]] = []
    for index in range(section_count):
        header = table_offset + index * 56
        fields = struct.unpack_from("<9I20s", payload, header)
        name_offset = fields[5] - image_base
        end = payload.find(b"\0", name_offset, name_offset + 64)
        require(end >= 0, "XBE section name is not terminated")
        rows.append({
            "index": index,
            "header": header,
            "name": payload[name_offset:end].decode("ascii"),
            "va": fields[1],
            "raw": fields[3],
            "raw_size": fields[4],
            "stored_digest": fields[9],
        })
    return image_base, rows


def _patch_xbe(payload: bytes, preset_name: str) -> tuple[bytes, dict[str, object]]:
    require(preset_name in PRESETS, "unknown Fantasy Draft preset")
    require(len(payload) == SOURCE_XBE_SIZE and
            hashlib.sha256(payload).hexdigest() == SOURCE_XBE_SHA256,
            "default.xbe is not the supported NFL 2K5 USA executable")
    _image_base, sections = _sections(payload)
    rdata = next((row for row in sections if row["name"] == ".rdata"), None)
    require(rdata is not None, "default.xbe is missing .rdata")
    rdata_va = int(rdata["va"])
    rdata_raw = int(rdata["raw"])
    rdata_size = int(rdata["raw_size"])
    require(rdata_va <= TABLE_VA and TABLE_VA + 68 <= rdata_va + rdata_size,
            "Fantasy Draft table is outside the file-backed .rdata section")
    table_offset = rdata_raw + TABLE_VA - rdata_va
    stock_payload = struct.pack("<17f", *STOCK_WEIGHTS)
    require(payload[table_offset:table_offset + 68] == stock_payload,
            "retail Fantasy Draft table bytes changed")
    source_digest = _sha1_section(payload, rdata_raw, rdata_size)
    require(source_digest == bytes(rdata["stored_digest"]),
            "retail .rdata section digest does not match")

    weights = PRESETS[preset_name]
    replacement = struct.pack("<17f", *weights)
    patched = bytearray(payload)
    patched[table_offset:table_offset + len(replacement)] = replacement
    output_digest = _sha1_section(bytes(patched), rdata_raw, rdata_size)
    digest_offset = int(rdata["header"]) + 36
    patched[digest_offset:digest_offset + 20] = output_digest
    output = bytes(patched)
    changed = [
        index for index, (before, after) in enumerate(zip(payload, output))
        if before != after
    ]
    authorized = set(range(table_offset, table_offset + 68)) | set(
        range(digest_offset, digest_offset + 20)
    )
    require(changed and set(changed) <= authorized,
            "Fantasy Draft experiment changed bytes outside table and digest")
    require(output[table_offset:table_offset + 68] == replacement,
            "Fantasy Draft table readback mismatch")
    require(_sha1_section(output, rdata_raw, rdata_size) ==
            output[digest_offset:digest_offset + 20],
            "patched .rdata digest did not verify")
    require(payload[4:0x104] == output[4:0x104],
            "XBE RSA signature bytes changed")
    return output, {
        "preset": preset_name,
        "scope": "CPU Fantasy Draft position-priority table only",
        "table_virtual_address": f"0x{TABLE_VA:08x}",
        "table_file_offset": table_offset,
        "positions": list(POSITIONS),
        "weights": list(weights),
        "changed_xbe_offsets": changed,
        "semantic_table_bytes": 68,
        "section": {
            "name": ".rdata",
            "index": rdata["index"],
            "raw_offset": rdata_raw,
            "raw_size": rdata_size,
            "digest_header_offset": digest_offset,
            "source_digest": source_digest.hex(),
            "output_digest": output_digest.hex(),
        },
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
        require(opened.st_size == SOURCE_XISO_SIZE, "source XISO has the wrong size")
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
        source_xbe = xiso.read_exact(source_fd, xbe_entry.byte_offset, xbe_entry.size)
        patched_xbe, patch = _patch_xbe(source_xbe, preset_name)

        relative_differences = patch["changed_xbe_offsets"]
        require(isinstance(relative_differences, list),
                "internal changed-byte ledger error")
        expected_absolute = {
            xbe_entry.byte_offset + int(offset) for offset in relative_differences
        }
        output_owned = xiso.reserve_file(output)
        require(output_owned.identity != source_identity,
                "output XISO aliases the source inode")
        copy_method = xiso.copy_fd_exact(source_fd, output_owned.descriptor, opened.st_size)
        for offset in relative_differences:
            position = xbe_entry.byte_offset + int(offset)
            require(os.pwrite(
                output_owned.descriptor,
                patched_xbe[int(offset):int(offset) + 1],
                position,
            ) == 1, "short Fantasy Draft XISO write")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual_differences = xiso.compare_and_hash(
            source_fd, output_owned.descriptor, opened.st_size, expected_absolute
        )
        require(source_sha_after == source_sha_before,
                "source XISO changed during Fantasy Draft experiment")
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
                "fantasy_draft_table_patched": True,
                "fantasy_draft_runtime_effect_proved": False,
                "franchise_rookie_draft_effect_proved": False,
                "xemu_booted": False,
                "product_control_unlocked": False,
                "original_hardware_supported": False,
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
    parser.add_argument("--preset", choices=tuple(PRESETS),
                        default="special-teams-control")
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest, args.preset)
    except (DraftExperimentError, xiso.PatchError, OSError, struct.error,
            ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL2K5_FANTASY_DRAFT_EXPERIMENT_COMPLETE "
        f"preset={result['patch']['preset']} "
        f"changed={result['output']['changed_byte_count']} "
        f"sha256={result['output']['sha256']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
