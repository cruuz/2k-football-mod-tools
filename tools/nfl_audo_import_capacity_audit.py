#!/usr/bin/env python3
"""Audit fixed-allocation import capacity for all NFL 2K5 standalone AUDO.

This is a read-only corpus classifier.  It proves physical spans, hashes,
Xbox-IMA block geometry, and whether an exact-shape PCM fixture can be encoded
into each existing payload allocation.  It does not write game data, infer a
runtime selector from a sample name, or authorize a generic audio importer.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any, Iterable

import nfl_outer
import nfl_scene_probe
import nfl_uniform_color_xiso_direct_patch as xiso_common


SCHEMA = "nfl2k5_audo_import_capacity/v1"
SOURCE_XISO_SIZE = 6_300_499_968
SOURCE_XISO_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
AUDIO_REPORT_SHA256 = "08bc999ec2f2ca0af87933817e8e8fec912da2c2e43dbe1b3a4c70baee815b9f"
AUDIO_PROBE_SHA256 = "ce6fd48356f640becc7cab986a4a58e57cda1bf1f9a1f263f335ee77bfb9363f"
RESOURCE_INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
OUTER_MANIFEST_SHA256 = "be7129997b514377fed0ebffa629e47f13a6ef43cdd5b1752c2d20fa4a1f3f1c"
PACK_HASHES = {
    "0": "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
    "1": "40dedc28bb6f8fc8644534857e857ca944f0c3c1614323cc66f3b45554cdfb54",
    "2": "21e00e0f41b3e016e416c44f3e1f3a07f9d5d7fdb5b9fe586685fadceb335886",
    "3": "921a139a9fd1a9470cc77f78455a6282e426376d4c201635b97a512d1f947aa7",
    "4": "94e6f16dc53fe6e06a6357ecd23879244e6dd1854bd1b222e3a985f4611bf487",
    "5": "20d58c635bdccc9c66fae73defeb580fb5280e45a4c9bd4d6f70c4e389d3b811",
    "6": "6d8f0c24e9997938a48a7f47d6c1c179b013a4ed2d9d4121d76244a0762ec17a",
    "7": "e3bc7609dc173bfba9ddcbfc103ae44e140bf159d0d9fd7599cf9a7c2df209c7",
    "8": "265560a55bebc13e5c8bfbe7770dac2032624946b4767fad72191bb3266aca14",
    "9": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    "A": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    "B": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
    "C": "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090",
    "D": "dbf286add93d3b032822597bcbf5a1dfc58eaf3fe4d8ef63d1d77686c02f1ae2",
    "E": "ca858b2afa8ea0c0787379366c8fc88d65fb9ef6d55f809e1da2319558de2400",
    "F": "376f2d0ea4a5c01453408fbd9747bffbfb8715b56a7e3f41339158217b07da8d",
}

HEADER = struct.Struct("<4s7I")
DESCRIPTOR = struct.Struct("<8I")
CHANNEL_BLOCK_BYTES = 36
BLOCK_FRAMES = 64
PCM_SAMPLE_BYTES = 2
EXISTING_FIXED_SLOT = (3, 101)

CLASS_EXPORT_ONLY = "export-only"
CLASS_STRUCTURAL = "structurally-encodable-owner-runtime-unproved"
CLASS_CANDIDATE = "candidate-for-separately-authorized-fixed-slot-writer"

DEFAULT_INDEX = Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
DEFAULT_AUDIO_REPORT = Path("reports/assets/nfl2k5_audo_wav_all.json")
DEFAULT_AUDIO_PROBE = Path("reports/assets/nfl2k5_audo_probe.json")
DEFAULT_RESOURCE_INVENTORY = Path("reports/assets/nfl2k5_resource_chunks_v2.json")
DEFAULT_OUTER_MANIFEST = Path("reports/manifests/nfl_outer.json")
DEFAULT_XISO = Path("ESPN NFL 2K5 (USA).xiso.iso")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8)
IMA_STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)


class CapacityAuditError(ValueError):
    """An input or derived capacity claim failed closed."""


@dataclass(frozen=True)
class PinnedFile:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    size: int
    sha256: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CapacityAuditError(message)


def validate_source_constants() -> None:
    """Reject incomplete or malformed provenance pins before opening inputs."""

    require(set(PACK_HASHES) == set("0123456789ABCDEF"), "pack hash key set differs")
    pins = {
        "source XISO": SOURCE_XISO_SHA256,
        "full audio report": AUDIO_REPORT_SHA256,
        "audio prefix probe": AUDIO_PROBE_SHA256,
        "resource inventory": RESOURCE_INVENTORY_SHA256,
        "outer manifest": OUTER_MANIFEST_SHA256,
        **{f"pack {name}": value for name, value in PACK_HASHES.items()},
    }
    for label, value in pins.items():
        require(bool(SHA256_RE.fullmatch(value)), f"{label} SHA-256 pin is malformed")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def open_pinned(path: Path, expected_sha256: str, *, expected_size: int | None = None) -> PinnedFile:
    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise CapacityAuditError(f"required input is missing: {requested}") from exc
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"required input must be a non-symlink regular file: {requested}",
    )
    resolved = requested.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        require(
            stat.S_ISREG(opened.st_mode)
            and identity == (supplied.st_dev, supplied.st_ino)
            and opened.st_size == supplied.st_size,
            f"required input changed before open: {requested}",
        )
        if expected_size is not None:
            require(opened.st_size == expected_size, f"input size differs: {requested}")
        measured = hashlib.sha256()
        position = 0
        while position < opened.st_size:
            chunk = os.pread(descriptor, min(16 * 1024 * 1024, opened.st_size - position), position)
            require(bool(chunk), f"short read while hashing: {requested}")
            measured.update(chunk)
            position += len(chunk)
        require(measured.hexdigest() == expected_sha256, f"input SHA-256 differs: {requested}")
        current = resolved.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], opened.st_size),
            f"input pathname changed while hashing: {requested}",
        )
        return PinnedFile(resolved, descriptor, identity, opened.st_size, expected_sha256)
    except Exception:
        os.close(descriptor)
        raise


def close_pinned(item: PinnedFile) -> None:
    try:
        current = item.path.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (item.identity[0], item.identity[1], item.size),
            f"input pathname changed during audit: {item.path}",
        )
    finally:
        os.close(item.descriptor)


def read_json_pinned(path: Path, expected_sha256: str, maximum: int) -> tuple[PinnedFile, dict[str, Any]]:
    item = open_pinned(path, expected_sha256)
    try:
        require(0 < item.size <= maximum, f"JSON input size is outside limit: {path}")
        payload = os.pread(item.descriptor, item.size, 0)
        require(len(payload) == item.size, f"short JSON read: {path}")
        value = json.loads(payload)
        require(isinstance(value, dict), f"JSON root must be an object: {path}")
        return item, value
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        close_pinned(item)
        raise CapacityAuditError(f"invalid JSON input: {path}") from exc
    except Exception:
        close_pinned(item)
        raise


def expand_nibble(predictor: int, index: int, nibble: int) -> tuple[int, int]:
    step = IMA_STEP_TABLE[index]
    difference = step >> 3
    if nibble & 1:
        difference += step >> 2
    if nibble & 2:
        difference += step >> 1
    if nibble & 4:
        difference += step
    predictor = predictor - difference if nibble & 8 else predictor + difference
    predictor = max(-32_768, min(32_767, predictor))
    index = max(0, min(88, index + IMA_INDEX_TABLE[nibble & 7]))
    return predictor, index


def choose_nibble(target: int, predictor: int, index: int) -> tuple[int, int, int]:
    step = IMA_STEP_TABLE[index]
    delta = target - predictor
    nibble = 8 if delta < 0 else 0
    magnitude = abs(delta)
    if magnitude >= step:
        nibble |= 4
        magnitude -= step
    if magnitude >= step >> 1:
        nibble |= 2
        magnitude -= step >> 1
    if magnitude >= step >> 2:
        nibble |= 1
    decoded, new_index = expand_nibble(predictor, index, nibble)
    return nibble, decoded, new_index


def encode_channel_block(samples: tuple[int, ...]) -> bytes:
    """Encode one 64-frame mono sub-block using the proved Xbox framing."""

    require(len(samples) == BLOCK_FRAMES, "encoder block must contain 64 frames")
    initial_predictor = samples[0]
    best: tuple[int, int, list[int]] | None = None
    for initial_index in range(89):
        predictor = initial_predictor
        index = initial_index
        nibbles: list[int] = []
        squared_error = 0
        for target in samples[1:]:
            nibble, predictor, index = choose_nibble(target, predictor, index)
            nibbles.append(nibble)
            squared_error += (target - predictor) ** 2
        final_nibble, _, _ = choose_nibble(samples[-1], predictor, index)
        nibbles.append(final_nibble)
        candidate = (squared_error, initial_index, nibbles)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    encoded = bytearray(struct.pack("<hH", initial_predictor, best[1]))
    encoded.extend(
        best[2][offset] | (best[2][offset + 1] << 4)
        for offset in range(0, 64, 2)
    )
    require(len(encoded) == CHANNEL_BLOCK_BYTES, "encoder emitted wrong sub-block size")
    return bytes(encoded)


def encode_interleaved_block(samples: tuple[int, ...], channels: int) -> bytes:
    require(channels in (1, 2), "capacity encoder supports the observed mono/stereo corpus")
    require(len(samples) == BLOCK_FRAMES * channels, "interleaved block shape differs")
    return b"".join(
        encode_channel_block(tuple(samples[frame * channels + channel] for frame in range(BLOCK_FRAMES)))
        for channel in range(channels)
    )


def decode_xbox_ima(payload: bytes, channels: int) -> tuple[int, ...]:
    block_align = CHANNEL_BLOCK_BYTES * channels
    require(channels in (1, 2) and len(payload) % block_align == 0, "IMA payload shape differs")
    output: list[int] = []
    for block_start in range(0, len(payload), block_align):
        channel_samples: list[list[int]] = []
        for channel in range(channels):
            start = block_start + channel * CHANNEL_BLOCK_BYTES
            predictor, index = struct.unpack_from("<hH", payload, start)
            require(index <= 88, "IMA step index exceeds 88")
            decoded = [predictor]
            for value in payload[start + 4 : start + CHANNEL_BLOCK_BYTES]:
                for nibble in (value & 0x0F, value >> 4):
                    predictor, index = expand_nibble(predictor, index, nibble)
                    if len(decoded) < BLOCK_FRAMES:
                        decoded.append(predictor)
            require(len(decoded) == BLOCK_FRAMES, "IMA block frame count differs")
            channel_samples.append(decoded)
        for frame in range(BLOCK_FRAMES):
            for channel in range(channels):
                output.append(channel_samples[channel][frame])
    return tuple(output)


def probe_contract(channels: int) -> dict[str, Any]:
    samples = tuple(
        ((frame * 997 + channel * 7_919) % 24_001) - 12_000
        for frame in range(BLOCK_FRAMES)
        for channel in range(channels)
    )
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    encoded = encode_interleaved_block(samples, channels)
    decoded = decode_xbox_ima(encoded, channels)
    decoded_pcm = struct.pack(f"<{len(decoded)}h", *decoded)
    return {
        "block_predictor_samples_exact": all(
            samples[channel] == decoded[channel] for channel in range(channels)
        ),
        "channels": channels,
        "decoded_pcm_sha256": digest(decoded_pcm),
        "encoded_block_bytes": len(encoded),
        "encoded_block_sha256": digest(encoded),
        "frame_count": BLOCK_FRAMES,
        "pcm_block_sha256": digest(pcm),
        "stored_channel_subblocks_consecutively": True,
    }


def repeated_digest(payload: bytes, count: int) -> str:
    value = hashlib.sha256()
    for _ in range(count):
        value.update(payload)
    return value.hexdigest()


def group_id(prefix: str, value: str) -> str:
    return f"{prefix}:{digest(value.encode('utf-8'))[:16]}"


def classify_record(
    *,
    key: tuple[int, int],
    structurally_encodable: bool,
    name_group_size: int,
    content_group_size: int,
) -> tuple[str, list[str]]:
    """Apply the conservative public-boundary classifier."""

    if key == EXISTING_FIXED_SLOT and structurally_encodable:
        return CLASS_CANDIDATE, [
            "this exact physical slot already has a separately reviewed fixed-target writer",
            "runtime selector ownership and audible visibility remain unproved",
        ]
    reasons: list[str] = []
    if not structurally_encodable:
        reasons.append("the exact PCM shape could not be encoded into the existing allocation")
    if name_group_size > 1:
        reasons.append("the sample name is duplicated, so name-only routing is ambiguous")
    if content_group_size > 1:
        reasons.append("decoded content has equal-content siblings in distinct physical spans")
    if reasons:
        return CLASS_EXPORT_ONLY, reasons
    return CLASS_STRUCTURAL, [
        "an exact-shape PCM fixture encodes into the existing payload allocation",
        "no exact runtime selector or audible replacement witness is known",
    ]


def locate_single_pack_span(entry: nfl_outer.Entry, start: int, size: int) -> tuple[str, int]:
    end = start + size
    relative = 0
    matches: list[tuple[str, int, int]] = []
    for segment in entry.segments:
        segment_start = relative
        segment_end = relative + segment.size
        overlap_start = max(start, segment_start)
        overlap_end = min(end, segment_end)
        if overlap_start < overlap_end:
            matches.append(
                (
                    segment.pack_name,
                    segment.pack_offset + overlap_start - segment_start,
                    overlap_end - overlap_start,
                )
            )
        relative = segment_end
    require(len(matches) == 1 and matches[0][2] == size, "AUDO wrapper crosses a pack boundary")
    return matches[0][0], matches[0][1]


def _members(rows: Iterable[dict[str, Any]]) -> list[str]:
    return sorted(row["key"] for row in rows)


def build_audit(
    *,
    index: Path,
    audio_report_path: Path,
    audio_probe_path: Path,
    resource_inventory_path: Path,
    outer_manifest_path: Path,
    source_xiso_path: Path,
) -> tuple[dict[str, Any], str]:
    """Read and classify the exact retail corpus without writing any input."""

    validate_source_constants()
    with ExitStack() as pinned_inputs:
        audio_file, audio_report = read_json_pinned(
            audio_report_path, AUDIO_REPORT_SHA256, 4 * 1024 * 1024
        )
        pinned_inputs.callback(close_pinned, audio_file)
        probe_file, audio_probe = read_json_pinned(
            audio_probe_path, AUDIO_PROBE_SHA256, 4 * 1024 * 1024
        )
        pinned_inputs.callback(close_pinned, probe_file)
        outer_file, outer_manifest = read_json_pinned(
            outer_manifest_path, OUTER_MANIFEST_SHA256, 8 * 1024 * 1024
        )
        pinned_inputs.callback(close_pinned, outer_file)
        inventory_file, resource_inventory = read_json_pinned(
            resource_inventory_path, RESOURCE_INVENTORY_SHA256, 64 * 1024 * 1024
        )
        pinned_inputs.callback(close_pinned, inventory_file)

        require(audio_report.get("schema") == "nfl2k5_scene_probe/v1", "audio report schema differs")
        require(audio_probe.get("schema") == "nfl2k5_scene_probe/v1", "audio probe schema differs")
        require(outer_manifest.get("schema") == "nfl2k5_outer_manifest/v1", "outer manifest schema differs")
        require(
            resource_inventory.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "resource inventory schema differs",
        )
        records = audio_report.get("records")
        require(isinstance(records, list) and len(records) == 850, "audio report must contain 850 rows")
        require(audio_report.get("summary", {}).get("status_counts") == {"parsed": 850}, "audio report is not fully parsed")
        require(audio_probe.get("summary", {}).get("record_count") == 850, "audio prefix probe count differs")
        require(
            resource_inventory.get("summary", {}).get("resource_kind_counts", {}).get("AUDO") == 850,
            "resource inventory AUDO count differs",
        )
        inventory_chunks = resource_inventory.get("chunks")
        require(isinstance(inventory_chunks, list), "resource inventory chunks are missing")
        inventory_audo: dict[tuple[int, int], dict[str, Any]] = {}
        for inventory_row in inventory_chunks:
            require(isinstance(inventory_row, dict), "resource inventory row is not an object")
            if inventory_row.get("kind") != "AUDO":
                continue
            inventory_key = (inventory_row.get("outer_index"), inventory_row.get("chunk_index"))
            require(
                all(type(value) is int for value in inventory_key),
                "resource inventory AUDO key differs",
            )
            require(inventory_key not in inventory_audo, "resource inventory AUDO key is duplicated")
            inventory_audo[inventory_key] = inventory_row
        require(len(inventory_audo) == 850, "resource inventory AUDO key count differs")

        pack_files: dict[str, PinnedFile] = {}
        for pack_name, expected_hash in PACK_HASHES.items():
            pack_files[pack_name] = open_pinned(index.parent / pack_name, expected_hash)
            pinned_inputs.callback(close_pinned, pack_files[pack_name])
        archive = nfl_outer.parse_archive(index)
        require(len(archive.entries) == 4_323 and len(archive.packs) == 16, "outer archive shape differs")
        require(outer_manifest.get("format", {}).get("entry_count") == len(archive.entries), "outer manifest entry count differs")
        for pack in archive.packs:
            pinned = pack_files[pack.name]
            require(pack.size == pinned.size, f"outer pack size differs: {pack.name}")

        source_xiso = open_pinned(
            source_xiso_path, SOURCE_XISO_SHA256, expected_size=SOURCE_XISO_SIZE
        )
        pinned_inputs.callback(close_pinned, source_xiso)
        xiso_entries, xdvdfs = xiso_common.parse_xdvdfs(source_xiso.descriptor, source_xiso.size)
        for pack in archive.packs:
            xiso_path = f"vc_53450030/{pack.name}".casefold()
            require(xiso_path in xiso_entries, f"XISO pack is missing: {pack.name}")
            require(xiso_entries[xiso_path].size == pack.size, f"XISO pack size differs: {pack.name}")

        contracts = {channels: probe_contract(channels) for channels in (1, 2)}
        provisional: list[dict[str, Any]] = []
        seen_keys: set[tuple[int, int]] = set()
        used_packs: Counter[str] = Counter()

        for source_row in records:
            require(isinstance(source_row, dict), "audio row is not an object")
            outer_index = source_row.get("outer_index")
            chunk_index = source_row.get("chunk_index")
            require(type(outer_index) is int and type(chunk_index) is int, "audio key fields differ")
            key_tuple = (outer_index, chunk_index)
            require(key_tuple not in seen_keys, "duplicate outer/chunk key in audio report")
            seen_keys.add(key_tuple)
            require(0 <= outer_index < len(archive.entries), "audio outer index is out of range")
            entry = archive.entries[outer_index]
            inventory_row = inventory_audo.get(key_tuple)
            require(inventory_row is not None, "audio row is absent from the resource inventory")
            inventory_expectations = {
                "outer_id": source_row.get("outer_id"),
                "outer_size": source_row.get("outer_size"),
                "chunk_offset": source_row.get("chunk_offset"),
                "stored_size": source_row.get("stored_size"),
                "word_08": source_row.get("system_bytes"),
                "word_0c": source_row.get("video_bytes"),
                "word_10": source_row.get("compression_magic"),
                "word_14": source_row.get("overlap_scratch_bytes"),
            }
            for inventory_field, expected_value in inventory_expectations.items():
                require(
                    inventory_row.get(inventory_field) == expected_value,
                    f"resource inventory cross-reference differs: {inventory_field}",
                )
            chunk_offset = source_row.get("chunk_offset")
            stored_size = source_row.get("stored_size")
            require(type(chunk_offset) is int and type(stored_size) is int, "audio span fields differ")
            span_size = HEADER.size + stored_size
            require(0 <= chunk_offset and chunk_offset + span_size <= entry.size, "audio wrapper exceeds outer entry")
            pack_name, pack_offset = locate_single_pack_span(entry, chunk_offset, span_size)
            used_packs[pack_name] += 1
            wrapper = os.pread(pack_files[pack_name].descriptor, span_size, pack_offset)
            require(len(wrapper) == span_size, "short AUDO wrapper read")
            kind, raw_stored, system_bytes, video_bytes, magic, scratch, reserved0, reserved1 = HEADER.unpack_from(wrapper)
            require(
                kind == b"AUDO"
                and raw_stored == stored_size
                and system_bytes == source_row.get("system_bytes")
                and video_bytes == source_row.get("video_bytes")
                and magic == 0
                and scratch == 0
                and reserved0 == 0
                and reserved1 == 0,
                "AUDO wrapper header differs from the pinned report",
            )
            require(source_row.get("compressed") is False, "compressed AUDO is outside this audit")
            body = wrapper[HEADER.size:]
            require(digest(body) == source_row.get("decoded_sha256"), "AUDO decoded body hash differs")

            resource_record = nfl_scene_probe.ResourceRecord(
                outer_index=outer_index,
                outer_id=f"0x{entry.name_id:08x}",
                outer_size=entry.size,
                chunk_index=chunk_index,
                chunk_offset=chunk_offset,
                kind="AUDO",
                stored_size=stored_size,
                word_08=system_bytes,
                word_0c=video_bytes,
                word_10=magic,
                word_14=scratch,
            )
            parsed = nfl_scene_probe.probe_audo(body, resource_record, True)
            semantic = source_row.get("semantic")
            require(isinstance(semantic, dict), "AUDO semantic row is missing")
            for field in (
                "name", "descriptor_offset", "descriptor_words", "channels", "codec_word",
                "codec_flags", "data_size", "data_offset", "per_channel_data_size",
                "sample_rate", "wrapper_video_bytes", "wrapper_tail_bytes",
                "xbox_ima_block_align", "xbox_ima_block_count", "block_remainder",
            ):
                require(parsed.get(field) == semantic.get(field), f"AUDO semantic field differs: {field}")

            name = str(parsed["name"])
            channels = int(parsed["channels"])
            sample_rate = int(parsed["sample_rate"])
            data_size = int(parsed["data_size"])
            data_offset = int(parsed["data_offset"])
            block_align = int(parsed["xbox_ima_block_align"])
            block_count = int(parsed["xbox_ima_block_count"])
            frame_count = block_count * BLOCK_FRAMES
            require(channels in contracts, "AUDO channel count is outside the proved encoder")
            require(parsed["codec_word"] == "0x00000011", "AUDO codec is not Xbox IMA")
            require(data_offset == 0 and data_size == video_bytes, "AUDO payload extent differs")
            require(block_align == channels * CHANNEL_BLOCK_BYTES, "AUDO block alignment differs")
            require(block_count > 0 and block_count * block_align == data_size, "AUDO allocation is not whole blocks")
            payload_start = system_bytes + data_offset
            payload_end = payload_start + data_size
            require(payload_end <= len(body), "AUDO payload exceeds body")
            system = body[:system_bytes]
            payload = body[payload_start:payload_end]
            tail = body[system_bytes + video_bytes:]
            require(len(tail) == semantic["wrapper_tail_bytes"], "AUDO tail extent differs")

            all_step_indices: list[int] = []
            for block_start in range(0, len(payload), block_align):
                for channel in range(channels):
                    _, step_index = struct.unpack_from(
                        "<hH", payload, block_start + channel * CHANNEL_BLOCK_BYTES
                    )
                    all_step_indices.append(step_index)
            require(all(index_value <= 88 for index_value in all_step_indices), "AUDO block step index differs")
            decoded = decode_xbox_ima(payload, channels)
            require(len(decoded) == frame_count * channels, "AUDO decoded PCM frame count differs")
            decoded_pcm = struct.pack(f"<{len(decoded)}h", *decoded)

            descriptor_offset = int(parsed["descriptor_offset"])
            descriptor_bytes = body[descriptor_offset:descriptor_offset + DESCRIPTOR.size]
            require(len(descriptor_bytes) == DESCRIPTOR.size, "AUDO descriptor extent differs")
            descriptor_words = list(DESCRIPTOR.unpack(descriptor_bytes))
            require(
                [f"0x{value:08x}" for value in descriptor_words] == parsed["descriptor_words"],
                "AUDO descriptor bytes differ",
            )

            xiso_entry = xiso_entries[f"vc_53450030/{pack_name}".casefold()]
            xiso_start = xiso_entry.byte_offset + pack_offset
            xiso_wrapper = os.pread(source_xiso.descriptor, span_size, xiso_start)
            require(xiso_wrapper == wrapper, "extracted AUDO wrapper differs from pinned XISO")
            archive_start = entry.virtual_offset + chunk_offset

            contract = contracts[channels]
            probe_samples = tuple(
                ((frame * 997 + channel * 7_919) % 24_001) - 12_000
                for frame in range(BLOCK_FRAMES)
                for channel in range(channels)
            )
            probe_pcm_block = struct.pack(f"<{len(probe_samples)}h", *probe_samples)
            probe_encoded_block = encode_interleaved_block(probe_samples, channels)
            structurally_encodable = (
                len(probe_encoded_block) * block_count == data_size
                and contract["block_predictor_samples_exact"] is True
            )

            row_key = f"outer_{outer_index:04d}_chunk_{chunk_index:04d}"
            provisional.append(
                {
                    "absolute_span": {
                        "archive_virtual": {"end": archive_start + span_size, "start": archive_start},
                        "pack": {
                            "end": pack_offset + span_size,
                            "path": f"vc_53450030/{pack_name}",
                            "start": pack_offset,
                        },
                        "xiso": {
                            "end": xiso_start + span_size,
                            "file_extent_start": xiso_entry.byte_offset,
                            "file_sector": xiso_entry.sector,
                            "path": xiso_entry.path,
                            "start": xiso_start,
                        },
                    },
                    "chunk": {
                        "index": chunk_index,
                        "kind": "AUDO",
                        "offset_in_outer": chunk_offset,
                        "stored_body_bytes": stored_size,
                        "wrapper_span_bytes": span_size,
                    },
                    "descriptor": {
                        "offset_in_body": descriptor_offset,
                        "sha256": digest(descriptor_bytes),
                        "words_u32le": parsed["descriptor_words"],
                    },
                    "format": {
                        "block_count": block_count,
                        "block_frames": BLOCK_FRAMES,
                        "channel_block_bytes": CHANNEL_BLOCK_BYTES,
                        "channels": channels,
                        "codec_flags": parsed["codec_flags"],
                        "codec_word": parsed["codec_word"],
                        "data_offset": data_offset,
                        "frame_count": frame_count,
                        "payload_allocation_bytes": data_size,
                        "pcm16le_bytes": frame_count * channels * PCM_SAMPLE_BYTES,
                        "sample_rate": sample_rate,
                        "system_bytes": system_bytes,
                        "tail_bytes": len(tail),
                        "total_block_align": block_align,
                    },
                    "hashes": {
                        "decoded_pcm_sha256": digest(decoded_pcm),
                        "payload_sha256": digest(payload),
                        "resource_body_sha256": digest(body),
                        "resource_span_sha256": digest(wrapper),
                        "system_sha256": digest(system),
                        "tail_sha256": digest(tail),
                        "wrapper_header_sha256": digest(wrapper[:HEADER.size]),
                    },
                    "key": row_key,
                    "name": name,
                    "outer": {
                        "head_ascii": entry.head_ascii,
                        "id": f"0x{entry.name_id:08x}",
                        "index": outer_index,
                        "size": entry.size,
                        "virtual_start": entry.virtual_offset,
                    },
                    "ownership": {
                        "fixed_slot_authorization": (
                            "public-offline-writer-proved" if key_tuple == EXISTING_FIXED_SLOT else "none"
                        ),
                        "physical_resource_owner": "exact outer/chunk/span",
                        "physical_resource_evidence_id": "resource-inventory-v2",
                        "resource_type_registration_evidence_id": "audo-static-registration",
                        "runtime_selector_owner": "unproved",
                        "runtime_visibility": "not-tested",
                        "fixed_slot_evidence": (
                            [
                                "docs/research/audio_modding_compatibility.md",
                                "tools/nfl_audo_wav_xiso_workflow.py",
                                "tools/nfl_audo_wav_xiso_verify.py",
                            ]
                            if key_tuple == EXISTING_FIXED_SLOT
                            else []
                        ),
                    },
                    "structural_import": {
                        "all_retail_block_step_indices_valid": True,
                        "authoring_contract": {
                            "channels": channels,
                            "exact_frame_count": frame_count,
                            "format": "strict RIFF PCM16LE",
                            "metadata_chunks_allowed": False,
                            "sample_rate": sample_rate,
                        },
                        "encoder": "deterministic Xbox IMA, low nibble then high nibble",
                        "metadata_change_required": False,
                        "probe_encoded_payload_sha256": repeated_digest(probe_encoded_block, block_count),
                        "probe_pcm_sha256": repeated_digest(probe_pcm_block, block_count),
                        "same_allocation": structurally_encodable,
                        "quality_or_runtime_claim": False,
                    },
                }
            )

        require(len(provisional) == len(seen_keys) == 850, "AUDO row/key count differs")
        provisional.sort(key=lambda row: (row["outer"]["index"], row["chunk"]["index"]))

        name_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        payload_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        content_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        span_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in provisional:
            name_groups[row["name"]].append(row)
            payload_groups[row["hashes"]["payload_sha256"]].append(row)
            content_key = (
                f"{row['format']['channels']}:{row['format']['sample_rate']}:"
                f"{row['hashes']['decoded_pcm_sha256']}"
            )
            content_groups[content_key].append(row)
            span_groups[row["hashes"]["resource_span_sha256"]].append(row)

        duplicate_name_groups: list[dict[str, Any]] = []
        equal_payload_groups: list[dict[str, Any]] = []
        equal_content_groups: list[dict[str, Any]] = []
        equal_resource_groups: list[dict[str, Any]] = []
        for name, members in sorted(name_groups.items()):
            if len(members) > 1:
                duplicate_name_groups.append(
                    {"group_id": group_id("name", name), "member_count": len(members), "members": _members(members), "name": name}
                )
        for payload_hash, members in sorted(payload_groups.items()):
            if len(members) > 1:
                equal_payload_groups.append(
                    {"group_id": f"payload:{payload_hash[:16]}", "member_count": len(members), "members": _members(members), "payload_sha256": payload_hash}
                )
        for content_key, members in sorted(content_groups.items()):
            if len(members) > 1:
                channels_text, rate_text, pcm_hash = content_key.split(":", 2)
                equal_content_groups.append(
                    {
                        "channels": int(channels_text),
                        "decoded_pcm_sha256": pcm_hash,
                        "group_id": group_id("content", content_key),
                        "member_count": len(members),
                        "members": _members(members),
                        "sample_rate": int(rate_text),
                    }
                )
        for span_hash, members in sorted(span_groups.items()):
            if len(members) > 1:
                equal_resource_groups.append(
                    {"group_id": f"resource:{span_hash[:16]}", "member_count": len(members), "members": _members(members), "resource_span_sha256": span_hash}
                )

        classifications: Counter[str] = Counter()
        for row in provisional:
            name_members = name_groups[row["name"]]
            content_key = (
                f"{row['format']['channels']}:{row['format']['sample_rate']}:"
                f"{row['hashes']['decoded_pcm_sha256']}"
            )
            content_members = content_groups[content_key]
            payload_members = payload_groups[row["hashes"]["payload_sha256"]]
            span_members = span_groups[row["hashes"]["resource_span_sha256"]]
            row["groups"] = {
                "duplicate_name": (
                    {"group_id": group_id("name", row["name"]), "member_count": len(name_members)}
                    if len(name_members) > 1 else None
                ),
                "equal_decoded_content": (
                    {"group_id": group_id("content", content_key), "member_count": len(content_members)}
                    if len(content_members) > 1 else None
                ),
                "equal_payload": (
                    {"group_id": f"payload:{row['hashes']['payload_sha256'][:16]}", "member_count": len(payload_members)}
                    if len(payload_members) > 1 else None
                ),
                "equal_resource_span": (
                    {"group_id": f"resource:{row['hashes']['resource_span_sha256'][:16]}", "member_count": len(span_members)}
                    if len(span_members) > 1 else None
                ),
                "physical_span_shared": False,
            }
            row_key_tuple = (row["outer"]["index"], row["chunk"]["index"])
            classification, reasons = classify_record(
                key=row_key_tuple,
                structurally_encodable=row["structural_import"]["same_allocation"],
                name_group_size=len(name_members),
                content_group_size=len(content_members),
            )
            row["classification"] = classification
            row["classification_reasons"] = reasons
            classifications[classification] += 1

        xiso_spans = sorted(
            (row["absolute_span"]["xiso"]["start"], row["absolute_span"]["xiso"]["end"], row["key"])
            for row in provisional
        )
        overlaps = [
            (left[2], right[2])
            for left, right in zip(xiso_spans, xiso_spans[1:])
            if left[1] > right[0]
        ]
        require(not overlaps, "AUDO physical XISO spans overlap")

        existing_key = "outer_0003_chunk_0101"
        candidates = [row["key"] for row in provisional if row["classification"] == CLASS_CANDIDATE]
        require(candidates == [existing_key], "candidate set generalized beyond the existing fixed slot")
        menu_appear = next(row for row in provisional if row["key"] == "outer_0009_chunk_0033")
        require(menu_appear["name"] == "menu-appear_01", "next trace target identity differs")
        require(
            menu_appear["groups"]["duplicate_name"] is None
            and menu_appear["groups"]["equal_decoded_content"] is None
            and menu_appear["classification"] == CLASS_STRUCTURAL,
            "next trace target is not a unique structural row",
        )

        report: dict[str, Any] = {
            "candidate_review": {
                "additional_candidate_count": 0,
                "existing_fixed_slot": existing_key,
                "existing_fixed_slot_runtime_owner_proved": False,
                "new_candidates": [],
                "next_trace": {
                    "evidence_boundary": (
                        "AUDO marker registration is statically identified at FUN_00045740 with "
                        "callback label LAB_00045680, but trustworthy callback types and per-play "
                        "selector ownership are not recovered."
                    ),
                    "steps": [
                        "Recover the typed AUDO registration/callback arguments and the resource-key object passed into play requests.",
                        "Instrument one deterministic frontend action while logging outer index, chunk index, sample name, and game state.",
                        "Start with outer 9 / chunk 33 / menu-appear_01 because its current name and decoded-content groups are unique; uniqueness is prioritization, not ownership proof.",
                        "Capture matched control and fixed-payload replacement runs before authorizing a second slot.",
                    ],
                    "target": "outer_0009_chunk_0033",
                },
                "reason": (
                    "No additional row has exact runtime selector ownership or an audible changed-resource witness. "
                    "Structural capacity and a unique name/content group are insufficient authorization."
                ),
            },
            "claims": {
                "all_850_exported": True,
                "all_850_physical_spans_exact_and_nonoverlapping": True,
                "all_850_structurally_encodable_at_same_allocation": all(
                    row["structural_import"]["same_allocation"] for row in provisional
                ),
                "additional_fixed_slot_writer_authorized": False,
                "generic_audo_writer_authorized": False,
                "runtime_selector_ownership_proved_count": 0,
                "runtime_visibility_proved_count": 0,
                "source_modified": False,
            },
            "classification_definitions": {
                CLASS_CANDIDATE: (
                    "An exact physical slot has or could receive a separate fixed-target authorization; "
                    "this report contains only the already reviewed menu-back slot."
                ),
                CLASS_EXPORT_ONLY: (
                    "Extraction remains safe, but structural failure or duplicate-name/equal-content routing "
                    "ambiguity blocks even a candidate classification."
                ),
                CLASS_STRUCTURAL: (
                    "Exact-shape PCM can fit the physical allocation, but selector ownership and runtime "
                    "visibility are unproved; no writer is authorized."
                ),
            },
            "encoder_contracts": contracts,
            "groups": {
                "duplicate_name_groups": duplicate_name_groups,
                "equal_decoded_content_groups": equal_content_groups,
                "equal_payload_groups": equal_payload_groups,
                "equal_resource_span_groups": equal_resource_groups,
                "physical_overlap_count": 0,
            },
            "ownership_evidence": {
                "audo-static-registration": {
                    "callback_label": "LAB_00045680",
                    "evidence": [
                        "research/functions/nfl2k5/focused/asset_fourcc_trace.txt",
                        "research/functions/nfl2k5/focused/asset_fourcc_candidate_pseudo_c.c",
                        "docs/research/nfl_scene_audio_assets.md",
                    ],
                    "function": "FUN_00045740",
                    "scope": "AUDO resource-type registration only",
                    "selector_or_play_request_owner_proved": False,
                },
                "resource-inventory-v2": {
                    "audited_audo_key_count": len(inventory_audo),
                    "cross_checked_fields": sorted(inventory_expectations),
                    "path": str(resource_inventory_path),
                    "schema": resource_inventory["schema"],
                    "sha256": RESOURCE_INVENTORY_SHA256,
                },
            },
            "records": provisional,
            "schema": SCHEMA,
            "source": {
                "audio_full_report": {"path": str(audio_report_path), "sha256": AUDIO_REPORT_SHA256},
                "audio_prefix_probe": {"path": str(audio_probe_path), "sha256": AUDIO_PROBE_SHA256},
                "outer_manifest": {"path": str(outer_manifest_path), "sha256": OUTER_MANIFEST_SHA256},
                "packs": [
                    {
                        "name": pack.name,
                        "path": f"{index.parent}/{pack.name}",
                        "sha256": PACK_HASHES[pack.name],
                        "size": pack.size,
                        "xiso_file_offset": xiso_entries[f"vc_53450030/{pack.name}".casefold()].byte_offset,
                        "xiso_sector": xiso_entries[f"vc_53450030/{pack.name}".casefold()].sector,
                    }
                    for pack in archive.packs
                ],
                "resource_inventory": {"path": str(resource_inventory_path), "sha256": RESOURCE_INVENTORY_SHA256},
                "xiso": {"path": str(source_xiso_path), "sha256": SOURCE_XISO_SHA256, "size": SOURCE_XISO_SIZE},
                "xdvdfs": xdvdfs,
            },
            "summary": {
                "channel_counts": dict(sorted(Counter(str(row["format"]["channels"]) for row in provisional).items())),
                "classification_counts": dict(sorted(classifications.items())),
                "duplicate_name_group_count": len(duplicate_name_groups),
                "equal_decoded_content_group_count": len(equal_content_groups),
                "equal_payload_group_count": len(equal_payload_groups),
                "equal_resource_span_group_count": len(equal_resource_groups),
                "record_count": len(provisional),
                "sample_rate_counts": dict(sorted(Counter(str(row["format"]["sample_rate"]) for row in provisional).items())),
                "unique_name_count": len(name_groups),
                "used_pack_record_counts": dict(sorted(used_packs.items())),
            },
        }
        matrix = render_matrix(report)
        return report, matrix


MATRIX_FIELDS = (
    "key", "outer_index", "outer_id", "chunk_index", "name", "pack_path",
    "pack_offset", "xiso_absolute_start", "wrapper_span_bytes", "channels",
    "sample_rate", "codec_word", "codec_flags", "block_align", "block_count",
    "frame_count", "payload_allocation_bytes", "system_bytes", "tail_bytes",
    "name_group_size", "content_group_size", "classification",
    "runtime_selector_owner", "fixed_slot_authorization",
)


def render_matrix(report: dict[str, Any]) -> str:
    lines = ["\t".join(MATRIX_FIELDS)]
    for row in report["records"]:
        duplicate = row["groups"]["duplicate_name"]
        content = row["groups"]["equal_decoded_content"]
        values = {
            "key": row["key"],
            "outer_index": row["outer"]["index"],
            "outer_id": row["outer"]["id"],
            "chunk_index": row["chunk"]["index"],
            "name": row["name"],
            "pack_path": row["absolute_span"]["pack"]["path"],
            "pack_offset": row["absolute_span"]["pack"]["start"],
            "xiso_absolute_start": row["absolute_span"]["xiso"]["start"],
            "wrapper_span_bytes": row["chunk"]["wrapper_span_bytes"],
            "channels": row["format"]["channels"],
            "sample_rate": row["format"]["sample_rate"],
            "codec_word": row["format"]["codec_word"],
            "codec_flags": row["format"]["codec_flags"],
            "block_align": row["format"]["total_block_align"],
            "block_count": row["format"]["block_count"],
            "frame_count": row["format"]["frame_count"],
            "payload_allocation_bytes": row["format"]["payload_allocation_bytes"],
            "system_bytes": row["format"]["system_bytes"],
            "tail_bytes": row["format"]["tail_bytes"],
            "name_group_size": duplicate["member_count"] if duplicate else 1,
            "content_group_size": content["member_count"] if content else 1,
            "classification": row["classification"],
            "runtime_selector_owner": row["ownership"]["runtime_selector_owner"],
            "fixed_slot_authorization": row["ownership"]["fixed_slot_authorization"],
        }
        line: list[str] = []
        for field in MATRIX_FIELDS:
            value = str(values[field])
            require("\t" not in value and "\r" not in value and "\n" not in value, "TSV value contains control characters")
            line.append(value)
        lines.append("\t".join(line))
    require(len(lines) == 851, "capacity matrix row count differs")
    return "\n".join(lines) + "\n"


def _new_output(path: Path, suffix: str) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    require(requested.suffix.lower() == suffix, f"output must use {suffix}: {requested}")
    require(not os.path.lexists(requested), f"output already exists: {requested}")
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise CapacityAuditError(f"output parent is missing: {requested.parent}") from exc
    require(
        stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
        "output parent must be a non-symlink directory",
    )
    return requested.resolve(strict=False)


def write_outputs(output: Path, matrix: Path, report: dict[str, Any], tsv: str) -> None:
    json_path = _new_output(output, ".json")
    tsv_path = _new_output(matrix, ".tsv")
    require(json_path != tsv_path, "JSON and TSV outputs must be distinct")
    payloads = ((json_path, canonical_json(report)), (tsv_path, tsv.encode("utf-8")))
    owned: list[tuple[Path, tuple[int, int]]] = []
    descriptors: list[int] = []
    try:
        for path, payload in payloads:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                0o644,
            )
            descriptors.append(descriptor)
            opened = os.fstat(descriptor)
            require(stat.S_ISREG(opened.st_mode), "capacity output is not regular")
            identity = (opened.st_dev, opened.st_ino)
            owned.append((path, identity))
            cursor = 0
            while cursor < len(payload):
                written = os.write(descriptor, payload[cursor:])
                require(written > 0, "short capacity output write")
                cursor += written
            os.fsync(descriptor)
            current = path.lstat()
            require(
                stat.S_ISREG(current.st_mode)
                and not stat.S_ISLNK(current.st_mode)
                and (current.st_dev, current.st_ino, current.st_size)
                == (identity[0], identity[1], len(payload)),
                "capacity output pathname changed during write",
            )
    except Exception:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        descriptors.clear()
        for path, identity in reversed(owned):
            try:
                current = path.lstat()
                if stat.S_ISREG(current.st_mode) and not stat.S_ISLNK(current.st_mode) and (
                    current.st_dev, current.st_ino
                ) == identity:
                    path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--audio-report", type=Path, default=DEFAULT_AUDIO_REPORT)
    parser.add_argument("--audio-probe", type=Path, default=DEFAULT_AUDIO_PROBE)
    parser.add_argument("--resource-inventory", type=Path, default=DEFAULT_RESOURCE_INVENTORY)
    parser.add_argument("--outer-manifest", type=Path, default=DEFAULT_OUTER_MANIFEST)
    parser.add_argument("--source-xiso", type=Path, default=DEFAULT_XISO)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    args = parser.parse_args()
    try:
        report, matrix = build_audit(
            index=args.index,
            audio_report_path=args.audio_report,
            audio_probe_path=args.audio_probe,
            resource_inventory_path=args.resource_inventory,
            outer_manifest_path=args.outer_manifest,
            source_xiso_path=args.source_xiso,
        )
        write_outputs(args.output, args.matrix, report, matrix)
    except (OSError, CapacityAuditError, nfl_outer.FormatError, xiso_common.PatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL2K5_AUDO_IMPORT_CAPACITY_AUDIT_PASS "
        f"records={report['summary']['record_count']} "
        f"structural={report['claims']['all_850_structurally_encodable_at_same_allocation']} "
        f"new_candidates={report['candidate_review']['additional_candidate_count']} "
        "runtime=false generic_writer=false source_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
