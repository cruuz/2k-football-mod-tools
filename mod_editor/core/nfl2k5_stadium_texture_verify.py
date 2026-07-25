"""Independent verifier for the bounded NFL 2K5 stadium-texture XISO.

This module intentionally imports neither the writer nor its delegate.  It
re-derives the XDVDFS layout, complete-disc difference boundary, VC-LZ fixed
span, preserved opaque tail, decoded P8 pixel/palette ownership, and all four
mip hashes from read-only descriptors.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

from .errors import ValidationError
from .json_stream import require_regular_file


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_txtr import (  # noqa: E402
    HEADER,
    TxtrError,
    decompress_vc_lz,
    minimum_vc_lz_overlap_scratch,
    unswizzle_2d,
)
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402


MANIFEST_SCHEMA = "2k5_mod_studio_stadium_texture_xiso/v1"
VERIFY_SCHEMA = "2k5_mod_studio_stadium_texture_xiso_verify/v1"
TARGET_TEXTURE_ID = "nfl2k5.stadium.o3280.c0005.scene2648.texture0002"
TARGET_SCENE_ID = "nfl2k5.stadium.o3280.c0005.scene2648"
PACK_PATH = "vc_53450030/9"
PACK_SECTOR = 35_531
PACK_SIZE = 634_941_440
INDEX_PATH = "vc_53450030/0"
INDEX_SECTOR = 796_479
INDEX_SIZE = 193_710_080
FILE_COUNT = 19
CHUNK_PACK_OFFSET = 0x07EA5A40
CHUNK_STORED_SIZE = 908_880
CHUNK_SPAN_SIZE = HEADER.size + CHUNK_STORED_SIZE
ABSOLUTE_SPAN = PACK_SECTOR * xiso.SECTOR_SIZE + CHUNK_PACK_OFFSET
SOURCE_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
SOURCE_DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
SYSTEM_BYTES = 577_792
VIDEO_BYTES = 947_072
DECODED_SIZE = SYSTEM_BYTES + VIDEO_BYTES
RETAIL_CONSUMED = 908_864
OPAQUE_TAIL_SIZE = 16
OPAQUE_TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"
PIXEL_OFFSET = 0x17300
PALETTE_OFFSET = 0x18840
MIP_DIMENSIONS = ((64, 64), (32, 32), (16, 16), (8, 8))
INDEX_CHAIN_BYTES = sum(width * height for width, height in MIP_DIMENSIONS)
PALETTE_BYTES = 1_024
MAX_SCRATCH = 3_120
MAX_MANIFEST = 128 * 1024
BLOCK = 16 * 1024 * 1024


class StadiumTextureVerifyError(ValidationError):
    """The copied XISO or its evidence violates the pinned texture contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StadiumTextureVerifyError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _regular(path: Path, label: str) -> Path:
    require_regular_file(path, label)
    return path.resolve(strict=True)


def _digest_fd(fd: int, offset: int = 0, length: int | None = None) -> str:
    digest = hashlib.sha256()
    position = offset
    remaining = length
    while remaining is None or remaining:
        request = BLOCK if remaining is None else min(BLOCK, remaining)
        payload = os.pread(fd, request, position)
        if not payload:
            break
        digest.update(payload)
        position += len(payload)
        if remaining is not None:
            remaining -= len(payload)
    if length is not None:
        _require(remaining == 0, "Short bounded hash read")
    return digest.hexdigest()


def _compare_discs(source_fd: int, output_fd: int, size: int) -> tuple[str, str, int]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    changed = 0
    position = 0
    end = ABSOLUTE_SPAN + CHUNK_SPAN_SIZE
    while position < size:
        request = min(BLOCK, size - position)
        left = os.pread(source_fd, request, position)
        right = os.pread(output_fd, request, position)
        _require(len(left) == len(right) == request, "Short full-disc comparison read")
        source_hash.update(left)
        output_hash.update(right)
        if left != right:
            for index, values in enumerate(zip(left, right)):
                if values[0] != values[1]:
                    absolute = position + index
                    _require(
                        ABSOLUTE_SPAN <= absolute < end,
                        f"Unauthorized XISO difference at 0x{absolute:x}",
                    )
                    changed += 1
        position += request
    return source_hash.hexdigest(), output_hash.hexdigest(), changed


def _ledger(before: bytes, after: bytes) -> dict[str, object]:
    _require(len(before) == len(after) == CHUNK_SPAN_SIZE, "SCNE ledger size changed")
    offsets = [index for index, values in enumerate(zip(before, after))
               if values[0] != values[1]]
    offset_hash = hashlib.sha256()
    before_hash = hashlib.sha256()
    after_hash = hashlib.sha256()
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        offset_hash.update(struct.pack("<I", offset))
        before_hash.update(before[offset:offset + 1])
        after_hash.update(after[offset:offset + 1])
        if not runs or runs[-1][1] != offset:
            runs.append((offset, offset + 1))
        else:
            runs[-1] = (runs[-1][0], offset + 1)
    return {
        "changed_byte_count": len(offsets),
        "changed_run_count": len(runs),
        "changed_offset_u32le_sha256": offset_hash.hexdigest(),
        "changed_before_bytes_sha256": before_hash.hexdigest(),
        "changed_after_bytes_sha256": after_hash.hexdigest(),
        "changed_run_pairs_u32le_sha256": _sha256(
            b"".join(struct.pack("<II", start, end) for start, end in runs)
        ),
    }


def _decode_mips(decoded: bytes) -> tuple[bytes, ...]:
    palette_start = SYSTEM_BYTES + PALETTE_OFFSET
    pixel_start = SYSTEM_BYTES + PIXEL_OFFSET
    palette_raw = decoded[palette_start:palette_start + PALETTE_BYTES]
    _require(len(palette_raw) == PALETTE_BYTES, "Output P8 palette is truncated")
    palette = [
        (palette_raw[index + 2], palette_raw[index + 1],
         palette_raw[index], palette_raw[index + 3])
        for index in range(0, PALETTE_BYTES, 4)
    ]
    result: list[bytes] = []
    cursor = pixel_start
    for width, height in MIP_DIMENSIONS:
        size = width * height
        swizzled = decoded[cursor:cursor + size]
        _require(len(swizzled) == size, "Output P8 mip is truncated")
        try:
            linear = unswizzle_2d(swizzled, width, height, 1)
        except TxtrError as exc:
            raise StadiumTextureVerifyError(f"Output P8 mip did not unswizzle ({exc})") from exc
        result.append(b"".join(bytes(palette[index]) for index in linear))
        cursor += size
    return tuple(result)


def verify_stadium_texture_xiso(
    source_xiso: Path, output_xiso: Path, manifest_path: Path
) -> dict[str, object]:
    """Independently verify one complete copied-XISO texture build."""

    source = _regular(source_xiso.expanduser(), "retail source XISO")
    output = _regular(output_xiso.expanduser(), "copied stadium-texture XISO")
    manifest_file = _regular(manifest_path.expanduser(), "stadium-texture build manifest")
    _require(len({source, output, manifest_file}) == 3,
             "Source, output, and manifest paths must be distinct")
    raw = manifest_file.read_bytes()
    _require(0 < len(raw) <= MAX_MANIFEST, "Build manifest size is invalid")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StadiumTextureVerifyError(f"Build manifest is invalid JSON ({exc})") from exc
    _require(raw == _canonical_json(manifest), "Build manifest is not canonical JSON")
    _require(
        isinstance(manifest, dict)
        and set(manifest) == {
            "schema", "target", "authored_replacement", "source", "resource",
            "xdvdfs", "output", "claims",
        }
        and manifest.get("schema") == MANIFEST_SCHEMA,
        "Build manifest root/schema is incompatible",
    )

    descriptors = [
        os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            # Both descriptors carry raw XISO *bytes* that are hashed here.  The
            # Windows CRT opens without ``O_BINARY`` in text mode, which collapses
            # CRLF and treats 0x1A as a soft EOF, so every digest below would be
            # computed over rewritten/short data.  ``O_BINARY`` is absent on POSIX
            # and resolves to 0, leaving the Linux/macOS flags unchanged.
            | getattr(os, "O_BINARY", 0),
        )
        for path in (source, output)
    ]
    source_fd, output_fd = descriptors
    try:
        source_info, output_info = map(os.fstat, descriptors)
        _require(
            stat.S_ISREG(source_info.st_mode)
            and stat.S_ISREG(output_info.st_mode)
            and source_info.st_size == output_info.st_size == xiso.EXPECTED_XISO_SIZE,
            "Source/output XISO size or file type changed",
        )
        identities = [xiso.fd_identity(fd) for fd in descriptors]
        _require(len(set(identities)) == 2, "Source and output XISOs alias an inode")
        _require(
            xiso.path_identity(source) == identities[0]
            and xiso.path_identity(output) == identities[1],
            "Source or output XISO pathname changed after open",
        )

        source_entries, source_directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
        output_entries, output_directory = xiso.parse_xdvdfs(output_fd, output_info.st_size)
        _require(
            source_entries == output_entries and source_directory == output_directory,
            "Output XDVDFS tree/extents differ from source",
        )
        files = [entry for entry in source_entries.values() if not (entry.attributes & 0x10)]
        pack = source_entries.get(PACK_PATH.casefold())
        index = source_entries.get(INDEX_PATH.casefold())
        xbe = source_entries.get("default.xbe")
        _require(len(files) == FILE_COUNT, "XDVDFS file count changed")
        _require(pack is not None and (pack.sector, pack.size) == (PACK_SECTOR, PACK_SIZE),
                 "XDVDFS volume 9 extent changed")
        _require(index is not None and (index.sector, index.size) == (INDEX_SECTOR, INDEX_SIZE),
                 "XDVDFS volume 0 extent changed")
        _require(xbe is not None and xbe.size == xiso.EXPECTED_XBE_SIZE,
                 "default.xbe extent changed")
        _require(pack.byte_offset + CHUNK_PACK_OFFSET == ABSOLUTE_SPAN,
                 "Authorized SCNE absolute offset changed")

        source_sha, output_sha, complete_changed = _compare_discs(
            source_fd, output_fd, source_info.st_size
        )
        _require(source_sha == xiso.EXPECTED_XISO_SHA256,
                 "Retail source XISO hash mismatch")
        retail_span = xiso.read_exact(source_fd, ABSOLUTE_SPAN, CHUNK_SPAN_SIZE)
        output_span = xiso.read_exact(output_fd, ABSOLUTE_SPAN, CHUNK_SPAN_SIZE)
        _require(_sha256(retail_span) == SOURCE_SPAN_SHA256,
                 "Retail source SCNE span hash mismatch")
        _require(output_span != retail_span, "Output stadium texture span is a no-op")
        derived_ledger = _ledger(retail_span, output_span)
        _require(complete_changed == derived_ledger["changed_byte_count"],
                 "Complete-disc change count differs from SCNE ledger")

        try:
            retail_decoded, retail_info = decompress_vc_lz(
                retail_span[HEADER.size:HEADER.size + RETAIL_CONSUMED], DECODED_SIZE
            )
            output_decoded, output_info_vc = decompress_vc_lz(
                output_span[HEADER.size:HEADER.size + RETAIL_CONSUMED], DECODED_SIZE
            )
        except TxtrError as exc:
            raise StadiumTextureVerifyError(f"SCNE VC-LZ verification failed ({exc})") from exc
        _require(retail_info.consumed_bytes == RETAIL_CONSUMED,
                 "Retail VC-LZ consumed length changed")
        _require(_sha256(retail_decoded) == SOURCE_DECODED_SHA256,
                 "Retail decoded SCNE hash changed")
        authored = manifest["authored_replacement"]
        _require(isinstance(authored, dict), "Authored replacement record is invalid")
        encoded_bytes = authored.get("encoded_bytes")
        scratch_after = authored.get("scratch_after")
        _require(isinstance(encoded_bytes, int) and not isinstance(encoded_bytes, bool),
                 "Manifest encoded byte count is invalid")
        _require(isinstance(scratch_after, int) and not isinstance(scratch_after, bool),
                 "Manifest scratch value is invalid")
        _require(output_info_vc.consumed_bytes == encoded_bytes,
                 "Output VC-LZ consumed length differs from manifest")
        _require(
            output_span[HEADER.size + encoded_bytes:HEADER.size + RETAIL_CONSUMED]
            == bytes(RETAIL_CONSUMED - encoded_bytes),
            "Output SCNE fixed gap is not zero-filled",
        )
        _require(
            _sha256(output_span[-OPAQUE_TAIL_SIZE:]) == OPAQUE_TAIL_SHA256
            and output_span[-OPAQUE_TAIL_SIZE:] == retail_span[-OPAQUE_TAIL_SIZE:],
            "Output SCNE opaque tail changed",
        )
        retail_header = HEADER.unpack_from(retail_span)
        output_header = HEADER.unpack_from(output_span)
        _require(
            retail_header == (b"SCNE", CHUNK_STORED_SIZE, SYSTEM_BYTES, VIDEO_BYTES,
                              0xFEEDBEEF, 16, 0, 0),
            "Retail SCNE wrapper changed",
        )
        _require(
            output_header[:5] == retail_header[:5]
            and output_header[5] == scratch_after
            and output_header[6:] == retail_header[6:],
            "Output SCNE wrapper changed outside overlap scratch",
        )
        alias = minimum_vc_lz_overlap_scratch(
            output_span[HEADER.size:HEADER.size + encoded_bytes],
            CHUNK_STORED_SIZE,
            DECODED_SIZE,
        )
        expected_scratch = (
            max(CHUNK_STORED_SIZE - encoded_bytes, alias) + 15
        ) & ~15
        _require(scratch_after == expected_scratch and scratch_after <= MAX_SCRATCH,
                 "Output SCNE scratch is not the bounded in-place value")

        pixel_start = SYSTEM_BYTES + PIXEL_OFFSET
        pixel_end = pixel_start + INDEX_CHAIN_BYTES
        palette_start = SYSTEM_BYTES + PALETTE_OFFSET
        palette_end = palette_start + PALETTE_BYTES
        decoded_changed = [
            index for index, values in enumerate(zip(retail_decoded, output_decoded))
            if values[0] != values[1]
        ]
        _require(
            decoded_changed
            and all(
                pixel_start <= index < pixel_end
                or palette_start <= index < palette_end
                for index in decoded_changed
            ),
            "Decoded output changed outside cement01 pixel/palette spans",
        )
        _require(len(decoded_changed) == authored.get("decoded_changed_byte_count"),
                 "Decoded changed-byte count differs from manifest")
        _require(_sha256(output_decoded) == authored.get("decoded_after_sha256"),
                 "Decoded output hash differs from manifest")
        output_mips = _decode_mips(output_decoded)
        mip_hashes = [_sha256(value) for value in output_mips]
        _require(mip_hashes == authored.get("mip_rgba_sha256"),
                 "Output P8 mip RGBA hashes differ from manifest")
        _require(mip_hashes[0] == authored.get("quantized_base_rgba_sha256"),
                 "Output base-level RGBA hash differs from manifest")
        _require(_sha256(output_span) == authored.get("rebuilt_span_sha256"),
                 "Output SCNE span hash differs from authored metadata")
        _require(
            _sha256(
                output_span[HEADER.size:HEADER.size + encoded_bytes]
            ) == authored.get("encoded_sha256"),
            "Output VC-LZ stream hash differs from authored metadata",
        )

        resource = manifest["resource"]
        _require(isinstance(resource, dict), "Manifest resource record is invalid")
        expected_resource_fixed = {
            "pack_path": PACK_PATH,
            "pack_sector": PACK_SECTOR,
            "pack_size": PACK_SIZE,
            "pack_span_offset": CHUNK_PACK_OFFSET,
            "absolute_xiso_span": ABSOLUTE_SPAN,
            "span_size": CHUNK_SPAN_SIZE,
            "source_span_sha256": SOURCE_SPAN_SHA256,
            "replacement_span_sha256": _sha256(output_span),
            "decoded_pixel_span": [pixel_start, pixel_end],
            "decoded_palette_span": [palette_start, palette_end],
            "fixed_opaque_tail_bytes": OPAQUE_TAIL_SIZE,
            "fixed_opaque_tail_sha256": OPAQUE_TAIL_SHA256,
            "retail_consumed_bytes": RETAIL_CONSUMED,
            "scratch_observed_retail_max": MAX_SCRATCH,
            **derived_ledger,
            "all_xiso_bytes_outside_span_bit_exact": True,
        }
        _require(resource == expected_resource_fixed, "Manifest resource ledger mismatch")

        target = manifest["target"]
        _require(
            isinstance(target, dict)
            and target.get("texture_id") == TARGET_TEXTURE_ID
            and target.get("scene_id") == TARGET_SCENE_ID
            and target.get("outer_index") == 3280
            and target.get("outer_id") == "0xe4d6b0bc"
            and target.get("chunk_index") == 5
            and target.get("scene_index") == 2648
            and target.get("texture_index") == 2
            and target.get("material_index") == 3
            and target.get("material_name") == "cement01"
            and target.get("dimensions") == [64, 64]
            and target.get("mip_dimensions") == [list(value) for value in MIP_DIMENSIONS]
            and target.get("format") == "P8",
            "Manifest target identity mismatch",
        )
        source_record = manifest["source"]
        _require(
            source_record == {
                "path": str(source),
                "size": source_info.st_size,
                "sha256": source_sha,
                "opened_read_only": True,
                "modified": False,
                "private_cache_png_sha256":
                    "f0db68aceb90f681a5d75b902b1686cf109cee13682c927a757f4291961fc28b",
            },
            "Manifest source record mismatch",
        )
        expected_xdvdfs = {
            **source_directory,
            "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
        }
        _require(manifest["xdvdfs"] == expected_xdvdfs, "Manifest XDVDFS record mismatch")
        output_pack_sha = _digest_fd(output_fd, pack.byte_offset, pack.size)
        output_record = manifest["output"]
        _require(
            isinstance(output_record, dict)
            and output_record == {
                "path": str(output),
                "size": output_info.st_size,
                "sha256": output_sha,
                "volume_9_sha256": output_pack_sha,
                "copy_method": output_record.get("copy_method"),
                "exclusively_created": True,
            }
            and output_record.get("copy_method") in {"copy_file_range", "pread_pwrite"},
            "Manifest output record mismatch",
        )
        _require(
            manifest["claims"] == {
                "bounded_existing_geometry_texture_write": True,
                "descriptor_palette_pixel_and_mips_verified": True,
                "layout_identical_copy_only_xiso": True,
                "private_cache_source_binding": True,
                "project_contains_retail_bytes": False,
                "xemu_boot_spot_check": False,
                "xemu_visible_texture_spot_check": False,
                "original_hardware_tested": False,
            },
            "Manifest claim boundary mismatch",
        )
        _require(
            xiso.path_identity(source) == identities[0]
            and xiso.path_identity(output) == identities[1],
            "Source or output artifact changed during verification",
        )
    finally:
        for descriptor in descriptors:
            os.close(descriptor)

    return {
        "schema": VERIFY_SCHEMA,
        "texture_id": TARGET_TEXTURE_ID,
        "output_xiso_sha256": output_sha,
        "output_volume_9_sha256": output_pack_sha,
        "changed_byte_count": derived_ledger["changed_byte_count"],
        "changed_run_count": derived_ledger["changed_run_count"],
        "decoded_changed_byte_count": len(decoded_changed),
        "mip_rgba_sha256": mip_hashes,
        "encoded_bytes": encoded_bytes,
        "scratch_after": scratch_after,
        "absolute_span_offset": ABSOLUTE_SPAN,
        "span_size": CHUNK_SPAN_SIZE,
        "xdvdfs_tree_exact": True,
        "outside_authorized_span_exact": True,
        "opaque_tail_exact": True,
        "all_four_mips_decoded": True,
        "source_unchanged": True,
        "xemu_runtime_spot_check": False,
    }


__all__ = [
    "StadiumTextureVerifyError",
    "VERIFY_SCHEMA",
    "verify_stadium_texture_xiso",
]
