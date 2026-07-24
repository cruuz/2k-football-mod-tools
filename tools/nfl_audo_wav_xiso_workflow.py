#!/usr/bin/env python3
"""Import one strict PCM WAV into a copied NFL 2K5 XISO AUDO slot.

The only supported target is the pinned, uncompressed ``menu-back_01`` AUDO
at outer 3 / chunk 101.  Its wrapper, system metadata, descriptor, unknown
tail, XDVDFS layout, and every byte outside the encoded payload are preserved.
The source image is opened read-only and the output is exclusively created.

This is a transport/codec proof, not runtime visibility proof and not a
generic audio-bank importer.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_audo_wav_xiso_workflow/v1"
PACK_PATH = "vc_53450030/0"
PACK_SECTOR = 796_479
PACK_SIZE = 193_710_080
PACK_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"

OUTER_INDEX = 3
OUTER_PACK_OFFSET = 851_968
CHUNK_INDEX = 101
CHUNK_OFFSET = 768_656
WRAPPER_SIZE = 3_376
WRAPPER_SHA256 = "cb8d0c27b7687f13374176a50cc0ca32c817d98ab64342a8a6d2193c28274ac3"
HEADER_SIZE = 32
SYSTEM_SIZE = 128
PAYLOAD_SIZE = 3_204
TAIL_SIZE = 12
SYSTEM_SHA256 = "b3090973e21d57e5f433ff1c1b9a0288ff7295dc477b3537e80b772c2b36c875"
SOURCE_PAYLOAD_SHA256 = "50d8d4efc2b9f6d2405c005c27b544d8f9f8b57dc3e9449517f58d799985724b"
TAIL_SHA256 = "0206ad250f9b665e23746316a1391a776ec06398ddbcb3dd0aaa97d34012bb89"
ABSOLUTE_WRAPPER_OFFSET = 1_632_809_616
ABSOLUTE_PAYLOAD_OFFSET = 1_632_809_776

CHANNELS = 1
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
BLOCK_FRAMES = 64
CHANNEL_BLOCK_BYTES = 36
BLOCK_COUNT = 89
FRAME_COUNT = BLOCK_COUNT * BLOCK_FRAMES
PCM_BYTES = FRAME_COUNT * CHANNELS * SAMPLE_WIDTH
MAX_WAV_BYTES = 16 * 1024 * 1024

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


class AudioImportError(ValueError):
    pass


@dataclass(frozen=True)
class InputFile:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    size: int
    sha256: str
    payload: bytes


@dataclass(frozen=True)
class WavData:
    input: InputFile
    samples: tuple[int, ...]
    pcm_sha256: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioImportError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_small_regular(path: Path, maximum: int) -> InputFile:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "WAV input must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) |
        getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), "WAV descriptor is not regular")
        require((opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino),
                "WAV pathname changed while opening")
        require(44 <= opened.st_size <= maximum, "WAV input size is outside the bounded range")
        payload = common.read_exact(descriptor, 0, opened.st_size)
        require(not common.pread(descriptor, 1, opened.st_size),
                "WAV input grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "WAV input changed while reading")
        return InputFile(
            resolved,
            descriptor,
            (opened.st_dev, opened.st_ino),
            opened.st_size,
            digest(payload),
            payload,
        )
    except Exception:
        os.close(descriptor)
        raise


def parse_strict_wav(input_file: InputFile) -> WavData:
    data = input_file.payload
    require(data[:4] == b"RIFF" and data[8:12] == b"WAVE", "input is not RIFF/WAVE")
    require(struct.unpack_from("<I", data, 4)[0] + 8 == len(data),
            "RIFF size does not equal the complete input")
    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < len(data):
        require(offset + 8 <= len(data), "truncated WAV chunk header")
        kind = data[offset:offset + 4]
        length = struct.unpack_from("<I", data, offset + 4)[0]
        start = offset + 8
        end = start + length
        require(end <= len(data), "WAV chunk exceeds RIFF boundary")
        chunks.append((kind, data[start:end]))
        offset = end + (length & 1)
        require(offset <= len(data), "WAV pad byte exceeds RIFF boundary")
    require(offset == len(data), "WAV chunk traversal did not tile the input")
    require([kind for kind, _ in chunks] == [b"fmt ", b"data"],
            "strict WAV must contain exactly fmt then data; normalize metadata away")
    fmt = chunks[0][1]
    pcm = chunks[1][1]
    require(len(fmt) == 16, "strict WAV fmt chunk must be the 16-byte PCM form")
    format_tag, channels, rate, byte_rate, block_align, bits = struct.unpack("<HHIIHH", fmt)
    require(format_tag == 1, "WAV must use integer PCM format tag 1")
    require(channels == CHANNELS, f"WAV must have exactly {CHANNELS} channel")
    require(rate == SAMPLE_RATE, f"WAV must be exactly {SAMPLE_RATE} Hz")
    require(bits == 16 and block_align == 2 and byte_rate == SAMPLE_RATE * 2,
            "WAV must be little-endian PCM16 with canonical rate/alignment fields")
    require(len(pcm) == PCM_BYTES,
            f"WAV must contain exactly {FRAME_COUNT} frames ({PCM_BYTES} PCM bytes)")
    samples = struct.unpack(f"<{FRAME_COUNT}h", pcm)
    return WavData(input_file, samples, digest(pcm))


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
    magnitude = -delta if delta < 0 else delta
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


def encode_block(samples: tuple[int, ...]) -> bytes:
    require(len(samples) == BLOCK_FRAMES, "internal IMA block frame count differs")
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
        # Xbox IMA stores 64 nibbles but exposes 64 frames including the
        # predictor.  The final state-only nibble repeats the last target.
        final_nibble, _, _ = choose_nibble(samples[-1], predictor, index)
        nibbles.append(final_nibble)
        candidate = (squared_error, initial_index, nibbles)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    encoded = bytearray(struct.pack("<hH", initial_predictor, best[1]))
    nibbles = best[2]
    require(len(nibbles) == 64, "internal IMA nibble count differs")
    encoded.extend(nibbles[index] | (nibbles[index + 1] << 4)
                   for index in range(0, 64, 2))
    require(len(encoded) == CHANNEL_BLOCK_BYTES, "internal IMA block size differs")
    return bytes(encoded)


def encode_xbox_ima(samples: tuple[int, ...]) -> bytes:
    require(len(samples) == FRAME_COUNT, "internal WAV frame count differs")
    payload = b"".join(
        encode_block(samples[offset:offset + BLOCK_FRAMES])
        for offset in range(0, FRAME_COUNT, BLOCK_FRAMES)
    )
    require(len(payload) == PAYLOAD_SIZE, "encoded payload no longer fits fixed AUDO slot")
    return payload


def decode_xbox_ima(payload: bytes) -> tuple[int, ...]:
    require(len(payload) == PAYLOAD_SIZE, "IMA payload size differs")
    samples: list[int] = []
    for offset in range(0, len(payload), CHANNEL_BLOCK_BYTES):
        predictor, index = struct.unpack_from("<hH", payload, offset)
        require(index <= 88, "encoded IMA step index exceeds 88")
        samples.append(predictor)
        emitted = 1
        for value in payload[offset + 4:offset + CHANNEL_BLOCK_BYTES]:
            for nibble in (value & 0x0F, value >> 4):
                predictor, index = expand_nibble(predictor, index, nibble)
                if emitted < BLOCK_FRAMES:
                    samples.append(predictor)
                    emitted += 1
        require(emitted == BLOCK_FRAMES, "IMA block emitted frame count differs")
    require(len(samples) == FRAME_COUNT, "decoded IMA frame count differs")
    return tuple(samples)


def quality(input_samples: tuple[int, ...], decoded: tuple[int, ...]) -> dict[str, Any]:
    require(len(input_samples) == len(decoded) == FRAME_COUNT, "quality frame count differs")
    differences = [source - result for source, result in zip(input_samples, decoded, strict=True)]
    squared_error = sum(value * value for value in differences)
    signal_square = sum(value * value for value in input_samples)
    rmse = math.sqrt(squared_error / FRAME_COUNT)
    signal_rms = math.sqrt(signal_square / FRAME_COUNT)
    snr = None
    if squared_error and signal_square:
        snr = 10.0 * math.log10(signal_square / squared_error)
    return {
        "frame_count": FRAME_COUNT,
        "squared_error_sum": squared_error,
        "maximum_absolute_error": max(abs(value) for value in differences),
        "rmse": rmse,
        "signal_rms": signal_rms,
        "snr_db": snr,
        "lossless_pcm": squared_error == 0,
        "block_predictor_samples_exact": all(
            input_samples[index] == decoded[index]
            for index in range(0, FRAME_COUNT, BLOCK_FRAMES)
        ),
    }


def validate_retail_wrapper(span: bytes) -> None:
    require(len(span) == WRAPPER_SIZE and digest(span) == WRAPPER_SHA256,
            "retail menu-back AUDO wrapper identity differs")
    require(struct.unpack_from("<4s7I", span) ==
            (b"AUDO", 3344, SYSTEM_SIZE, PAYLOAD_SIZE, 0, 0, 0, 0),
            "retail AUDO wrapper fields differ")
    body = span[HEADER_SIZE:]
    system = body[:SYSTEM_SIZE]
    payload = body[SYSTEM_SIZE:SYSTEM_SIZE + PAYLOAD_SIZE]
    tail = body[SYSTEM_SIZE + PAYLOAD_SIZE:]
    require(digest(system) == SYSTEM_SHA256 and digest(payload) == SOURCE_PAYLOAD_SHA256 and
            len(tail) == TAIL_SIZE and digest(tail) == TAIL_SHA256,
            "retail AUDO system/payload/tail identity differs")
    name = "menu-back_01\0".encode("utf-16le")
    require(system[0x0C:0x10] == b"AUDO" and
            system[0x20:0x20 + len(name)] == name,
            "retail AUDO name identity differs")
    descriptor_offset = 0x13 + struct.unpack_from("<i", system, 0x14)[0]
    require(descriptor_offset == 64 and struct.unpack_from("<8I", system, descriptor_offset) ==
            (1, 1, 0x11, 0x35, PAYLOAD_SIZE, 0, PAYLOAD_SIZE, SAMPLE_RATE),
            "retail AUDO descriptor differs")


def offset_digest(values: list[int], fmt: str) -> str:
    return digest(b"".join(struct.pack(fmt, value) for value in values))


def difference_runs(values: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for value in values:
        if not result or value != result[-1][1] + 1:
            result.append((value, value))
        else:
            result[-1] = (result[-1][0], value)
    return result


def write_all(descriptor: int, offset: int, data: bytes) -> None:
    position = 0
    while position < len(data):
        written = common.pwrite(descriptor, data[position:], offset + position)
        require(written > 0, "short AUDO payload write")
        position += written


def run(source_path: Path, wav_path: Path, output_path: Path, manifest_path: Path) -> dict[str, Any]:
    source_lstat = source_path.lstat()
    require(stat.S_ISREG(source_lstat.st_mode) and not stat.S_ISLNK(source_lstat.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    wav_file = open_small_regular(wav_path, MAX_WAV_BYTES)
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    source_fd = -1
    success = False
    try:
        wav = parse_strict_wav(wav_file)
        encoded = encode_xbox_ima(wav.samples)
        decoded = decode_xbox_ima(encoded)
        metrics = quality(wav.samples, decoded)
        decoded_pcm = struct.pack(f"<{FRAME_COUNT}h", *decoded)

        output = common.canonical_new_path(output_path)
        manifest = common.canonical_new_path(manifest_path)
        require(not output.exists() and not manifest.exists(),
                "output XISO and manifest must not already exist")
        require(len({source, wav_file.path, output, manifest}) == 4,
                "source, WAV, output, and manifest paths must be distinct")

        source_fd = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) |
            getattr(os, "O_BINARY", 0),
        )
        source_info = os.fstat(source_fd)
        require(stat.S_ISREG(source_info.st_mode) and
                (source_info.st_dev, source_info.st_ino) ==
                (source_lstat.st_dev, source_lstat.st_ino),
                "source XISO pathname changed while opening")
        require(source_info.st_size == common.EXPECTED_XISO_SIZE,
                "retail XISO size differs")
        source_identity = common.fd_identity(source_fd)
        source_hash_before = common.sha256_fd(source_fd)
        require(source_hash_before == common.EXPECTED_XISO_SHA256,
                "retail XISO SHA-256 differs")
        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        require(len(files) == 19, "retail XDVDFS file count differs")
        pack = entries.get(PACK_PATH.casefold())
        require(pack is not None and pack.sector == PACK_SECTOR and pack.size == PACK_SIZE,
                "retail pack-0 extent differs")
        assert pack is not None
        require(common.sha256_fd(source_fd, pack.byte_offset, pack.size) == PACK_SHA256,
                "retail pack-0 SHA-256 differs")
        wrapper_absolute = pack.byte_offset + OUTER_PACK_OFFSET + CHUNK_OFFSET
        payload_absolute = wrapper_absolute + HEADER_SIZE + SYSTEM_SIZE
        require(wrapper_absolute == ABSOLUTE_WRAPPER_OFFSET and
                payload_absolute == ABSOLUTE_PAYLOAD_OFFSET,
                "AUDO absolute-offset arithmetic differs")
        retail_span = common.read_exact(source_fd, wrapper_absolute, WRAPPER_SIZE)
        validate_retail_wrapper(retail_span)
        retail_payload = retail_span[HEADER_SIZE + SYSTEM_SIZE:
                                     HEADER_SIZE + SYSTEM_SIZE + PAYLOAD_SIZE]
        relative_changes = [
            index for index, (before, after) in
            enumerate(zip(retail_payload, encoded, strict=True)) if before != after
        ]
        require(relative_changes, "encoded replacement is byte-identical to retail payload")
        absolute_changes = [payload_absolute + value for value in relative_changes]
        allowed = set(absolute_changes)

        xbe = entries.get("default.xbe")
        require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail default.xbe identity differs")

        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output XISO aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_info.st_size)
        write_all(output_owned.descriptor, payload_absolute, encoded)
        require(common.read_exact(output_owned.descriptor, wrapper_absolute, WRAPPER_SIZE) ==
                retail_span[:HEADER_SIZE + SYSTEM_SIZE] + encoded + retail_span[-TAIL_SIZE:],
                "patched AUDO wrapper readback differs")
        os.fsync(output_owned.descriptor)
        source_hash_after, output_hash, actual_changes = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed)
        require(source_hash_after == source_hash_before,
                "source XISO changed during workflow")
        require(common.path_identity(source) == source_identity and
                common.owned_path_matches(output_owned),
                "source or output pathname changed during workflow")
        require(common.path_identity(wav_file.path) == wav_file.identity and
                digest(common.read_exact(wav_file.descriptor, 0, wav_file.size)) ==
                wav_file.sha256,
                "WAV input changed during workflow")

        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size)
        require(output_entries == entries and output_directory == directory,
                "output XDVDFS tree/layout differs")
        require(common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "output default.xbe changed")
        patched_pack_hash = common.sha256_fd(
            output_owned.descriptor, pack.byte_offset, pack.size)
        relative_runs = difference_runs(relative_changes)
        absolute_runs = difference_runs(actual_changes)

        result: dict[str, Any] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source),
                "size": source_info.st_size,
                "sha256_before": source_hash_before,
                "sha256_after": source_hash_after,
                "opened_read_only": True,
                "modified": False,
                "device": source_identity[0],
                "inode": source_identity[1],
            },
            "input_wav": {
                "path": str(wav_file.path),
                "size": wav_file.size,
                "sha256": wav_file.sha256,
                "pcm_sha256": wav.pcm_sha256,
                "format": "strict RIFF PCM16LE",
                "channels": CHANNELS,
                "sample_rate": SAMPLE_RATE,
                "frame_count": FRAME_COUNT,
                "duration_seconds": FRAME_COUNT / SAMPLE_RATE,
                "extra_chunks_accepted": False,
                "loop_metadata_accepted": False,
                "device": wav_file.identity[0],
                "inode": wav_file.identity[1],
            },
            "output": {
                "path": str(output),
                "size": os.fstat(output_owned.descriptor).st_size,
                "sha256": output_hash,
                "copy_method": copy_method,
                "exclusively_created": True,
                "distinct_from_source_inode": True,
                "device": output_owned.identity[0],
                "inode": output_owned.identity[1],
            },
            "target": {
                "name": "menu-back_01",
                "resource_kind": "AUDO",
                "outer_index": OUTER_INDEX,
                "chunk_index": CHUNK_INDEX,
                "pack_path": PACK_PATH,
                "pack_sector": PACK_SECTOR,
                "pack_size": PACK_SIZE,
                "source_pack_sha256": PACK_SHA256,
                "patched_pack_sha256": patched_pack_hash,
                "outer_pack_offset": OUTER_PACK_OFFSET,
                "chunk_offset": CHUNK_OFFSET,
                "absolute_wrapper_offset": wrapper_absolute,
                "absolute_payload_offset": payload_absolute,
                "wrapper_size": WRAPPER_SIZE,
                "source_wrapper_sha256": WRAPPER_SHA256,
                "system_size": SYSTEM_SIZE,
                "system_sha256": SYSTEM_SHA256,
                "payload_size": PAYLOAD_SIZE,
                "source_payload_sha256": SOURCE_PAYLOAD_SHA256,
                "replacement_payload_sha256": digest(encoded),
                "tail_size": TAIL_SIZE,
                "tail_sha256": TAIL_SHA256,
            },
            "codec": {
                "name": "Xbox IMA ADPCM",
                "format_word": "0x00000011",
                "codec_flags_preserved": "0x00000035",
                "channel_block_bytes": CHANNEL_BLOCK_BYTES,
                "frames_per_block": BLOCK_FRAMES,
                "block_count": BLOCK_COUNT,
                "nibble_order": "low_then_high",
                "channel_order": "complete_36_byte_subblock_per_channel",
                "decoded_pcm_sha256": digest(decoded_pcm),
                "quality": metrics,
            },
            "xdvdfs": {
                **directory,
                "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
            },
            "patch": {
                "relative_changed_byte_count": len(relative_changes),
                "relative_changed_offsets_u32le_sha256":
                    offset_digest(relative_changes, "<I"),
                "relative_changed_run_count": len(relative_runs),
                "relative_changed_runs_u32le_sha256": digest(b"".join(
                    struct.pack("<II", start, end) for start, end in relative_runs)),
                "absolute_changed_byte_count": len(actual_changes),
                "absolute_changed_offsets_u64le_sha256":
                    offset_digest(actual_changes, "<Q"),
                "absolute_changed_run_count": len(absolute_runs),
                "all_changes_inside_fixed_payload": True,
                "wrapper_header_preserved": True,
                "system_metadata_preserved": True,
                "unknown_tail_preserved": True,
                "all_other_image_bytes_identical": True,
            },
            "claims": {
                "fixed_size_standalone_audo_wav_import_proved": True,
                "generic_nfl_audo_import_proved": False,
                "nfl_audobank_import_proved": False,
                "nfl_music_or_commentary_import_proved": False,
                "apf_xma_import_proved": False,
                "runtime_visibility_proved": False,
                "emulator_started": False,
                "title_executed": False,
                "retail_original_modified": False,
            },
            "portme": [
                "PORTME: prove which retail frontend route selects outer 3 chunk 101 at runtime.",
                "PORTME: recover NFL ABNK/WBNK directories, cues, loop points, gain, pan, and priority.",
                "PORTME: generalize only after each AUDO slot's exact allocation and metadata are validated.",
            ],
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        require(common.path_identity(source) == source_identity and
                common.path_identity(wav_file.path) == wav_file.identity and
                common.owned_path_matches(output_owned) and
                common.owned_path_matches(manifest_owned),
                "an owned pathname changed during manifest write")
        success = True
        return result
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        os.close(wav_file.descriptor)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            common.unlink_if_owned(manifest_owned)
            common.unlink_if_owned(output_owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--input-wav", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.input_wav, args.output_xiso, args.manifest)
    except (OSError, AudioImportError, common.PatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "output": result["output"]["path"],
        "sha256": result["output"]["sha256"],
        "changed_bytes": result["patch"]["absolute_changed_byte_count"],
        "runtime": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
