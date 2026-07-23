#!/usr/bin/env python3
"""Inventory and cautiously reconstruct APF 2K8 Visual Concepts AUDO assets.

The APF IFF parser proves each AUDO file is split into a 44-byte DRAM record
and a packet-aligned SRAM payload.  This tool names only fields supported by
cross-record invariants, classifies packet headers as XMA1 versus XMA2, and can
wrap a selected payload in a minimal XMA1 RIFF header for independent FFmpeg
verification.  It never treats a successful container probe as decoded-audio
proof: ``--verify-wav`` must make FFmpeg decode the complete stream to PCM.

// PORTME: trace the remaining metadata words and loop fields through APF's
// XMACreateContext call site before implementing lossless loop round-tripping.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import Callable, Iterable
import zlib

import apf_inner
import apf_outer


AUDO_METADATA_SIZE = 44
XMA_PACKET_SIZE = 0x800
AUDO_TYPE = "AUDO"
AUSB_TYPE = "AUSB"
CHANNEL_LAYOUT_TO_COUNT = {2: 1, 5: 2}
PROCESS_POLL_SECONDS = 0.05
PROCESS_STOP_GRACE_SECONDS = 0.5
CancelRequested = Callable[[], bool]


class AudioError(ValueError):
    """Raised when an AUDO invariant is violated."""


class AudioCancelled(AudioError):
    """Raised when a caller cancels an in-flight audio decode or probe."""


def check_cancel_requested(cancel_requested: CancelRequested | None) -> None:
    """Raise a stable public cancellation error when a callback requests it."""

    if cancel_requested is None:
        return
    try:
        cancelled = cancel_requested()
    except Exception as exc:
        raise AudioError(
            f"Could not check whether audio decoding was cancelled: {exc}"
        ) from exc
    if cancelled:
        raise AudioCancelled("Audio decoding was cancelled; no PCM output was published")


def _stop_process_group(process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    """Terminate and drain the complete process group owned by one decoder."""

    process_group = process.pid

    def group_exists() -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def wait_for_group(timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while group_exists() and time.monotonic() < deadline:
            time.sleep(PROCESS_POLL_SECONDS)
        return not group_exists()

    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        pass
    # A launcher can exit while a detached helper in its process group keeps
    # running with closed stdio. Draining the direct child is therefore not
    # proof that the whole session-owned decoder group stopped.
    if wait_for_group(PROCESS_STOP_GRACE_SECONDS):
        return

    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        pass
    if not wait_for_group(PROCESS_STOP_GRACE_SECONDS):
        raise AudioError(
            "The audio decoder process group could not be stopped safely"
        )


def run_cancellable_subprocess(
    command: list[str],
    *,
    cancel_requested: CancelRequested,
    input_data: bytes | str | None = None,
    text: bool = False,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    """Run one decoder/probe without letting cancellation strand child processes.

    The executable is a new session leader.  Cancellation and timeout paths
    signal that complete process group, escalate from TERM to KILL, and drain
    its pipes before returning control to the caller.
    """

    check_cancel_requested(cancel_requested)
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise AudioError("Audio decoder timeout must be greater than zero")
    process: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None
    communication_complete = False
    started = time.monotonic()
    try:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=text,
                shell=False,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as exc:
            raise AudioError(f"Could not start the audio decoder: {exc}") from exc

        pending_input = input_data
        while True:
            check_cancel_requested(cancel_requested)
            poll_seconds = PROCESS_POLL_SECONDS
            if timeout_seconds is not None:
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout_seconds)
                poll_seconds = min(poll_seconds, remaining)
            try:
                stdout, stderr = process.communicate(
                    input=pending_input,
                    timeout=poll_seconds,
                )
                communication_complete = True
                check_cancel_requested(cancel_requested)
                return subprocess.CompletedProcess(
                    command,
                    process.returncode,
                    stdout,
                    stderr,
                )
            except subprocess.TimeoutExpired:
                # ``communicate`` retains any partially written stdin and may
                # safely be resumed without supplying the input a second time.
                pending_input = None
    except BaseException:
        if process is not None and not communication_complete:
            _stop_process_group(process)
        raise


def _publish_complete_file(source: Path, destination: Path) -> None:
    """Atomically replace one destination from a completely generated file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class SelectedAudio:
    table_index: int
    inner_index: int
    name: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def load_selection(
    manifest_path: Path, type_name: str = AUDO_TYPE
) -> tuple[list[SelectedAudio], str]:
    raw = manifest_path.read_bytes()
    document = json.loads(raw)
    selected: list[SelectedAudio] = []
    for entry in document.get("iff_entries", []):
        table_index = int(entry["table_index"])
        for item in entry.get("files", []):
            if item.get("type_name") == type_name:
                selected.append(
                    SelectedAudio(
                        table_index=table_index,
                        inner_index=int(item["index"]),
                        name=str(item.get("name") or f"file_{int(item['index']):04d}"),
                    )
                )
    selected.sort(key=lambda item: (item.table_index, item.inner_index))
    return selected, hashlib.sha256(raw).hexdigest()


def parse_metadata(data: bytes) -> dict[str, object]:
    if len(data) != AUDO_METADATA_SIZE:
        raise AudioError(
            f"AUDO DRAM metadata is {len(data)} bytes, expected {AUDO_METADATA_SIZE}"
        )
    words = struct.unpack(">11I", data)
    channel_count = CHANNEL_LAYOUT_TO_COUNT.get(words[2])
    return {
        "raw_be_words": [_hex(value) for value in words],
        "codec_or_version": words[0],
        "unknown_04": words[1],
        "channel_layout_code": words[2],
        "derived_channel_count": channel_count,
        "declared_sample_count": words[3],
        "sample_rate": words[4],
        "zero_14": words[5],
        "encoded_size": words[6],
        "zero_1c": words[7],
        "xma1_loop_start_bit_candidate": words[8],
        "xma1_loop_end_bit_candidate": words[9],
        "xma1_loop_subframe_candidate": words[10],
        "sha256": _sha256(data),
    }


def parse_packet_header(data: bytes) -> dict[str, object]:
    if len(data) < 4:
        raise AudioError("XMA packet probe is shorter than four bytes")
    word = struct.unpack_from(">I", data)[0]
    xma1 = {
        "sequence": (word >> 28) & 0xF,
        "metadata": (word >> 26) & 0x3,
        "first_frame_bit_offset": (word >> 11) & 0x7FFF,
        "packet_skip": word & 0x7FF,
    }
    xma2 = {
        "frame_count": (word >> 26) & 0x3F,
        "first_frame_bit_offset": (word >> 11) & 0x7FFF,
        "metadata": (word >> 8) & 0x7,
        "packet_skip": word & 0xFF,
    }
    # Microsoft's encoders use packet metadata value 2 for XMA1 and 1 for
    # XMA2.  Keep ambiguous cases explicit rather than forcing a version.
    if xma1["metadata"] == 2 and xma2["metadata"] != 1:
        classification = "xma1"
    elif xma2["metadata"] == 1 and xma1["metadata"] != 2:
        classification = "xma2"
    else:
        classification = "ambiguous"
    return {
        "word_be": _hex(word),
        "classification": classification,
        "xma1": xma1,
        "xma2": xma2,
    }


def summarize_packets(payload: bytes) -> dict[str, object]:
    if not payload or len(payload) % XMA_PACKET_SIZE:
        raise AudioError("AUDO SRAM payload is not a nonempty packet multiple")
    packets = [
        parse_packet_header(payload[offset : offset + 4])
        for offset in range(0, len(payload), XMA_PACKET_SIZE)
    ]
    return {
        "packet_count": len(packets),
        "classification_distribution": _counter(
            packet["classification"] for packet in packets
        ),
        "xma1_sequence_distribution": _counter(
            packet["xma1"]["sequence"] for packet in packets
        ),
        "xma1_metadata_distribution": _counter(
            packet["xma1"]["metadata"] for packet in packets
        ),
        "xma1_packet_skip_distribution": _counter(
            packet["xma1"]["packet_skip"] for packet in packets
        ),
        "first_frame_bit_offset_min": min(
            int(packet["xma1"]["first_frame_bit_offset"]) for packet in packets
        ),
        "first_frame_bit_offset_max": max(
            int(packet["xma1"]["first_frame_bit_offset"]) for packet in packets
        ),
        "all_packets_classify_xma1": all(
            packet["classification"] == "xma1" for packet in packets
        ),
        "all_xma1_metadata_is_2": all(
            int(packet["xma1"]["metadata"]) == 2 for packet in packets
        ),
        "all_xma1_packet_skips_are_zero": all(
            int(packet["xma1"]["packet_skip"]) == 0 for packet in packets
        ),
    }


def speaker_mask(channels: int) -> int:
    # Masks match the conventional WAVE speaker assignment used by XMA tools.
    masks = {
        1: 0x0004,
        2: 0x0003,
        3: 0x000B,
        4: 0x0033,
        5: 0x003B,
        6: 0x003F,
        7: 0x013F,
        8: 0x00FF,
    }
    return masks.get(channels, 0)


def make_xma1_riff(
    payload: bytes,
    channels: int,
    sample_rate: int,
    loop_start_bit: int = 0,
    loop_end_bit: int = 0,
    loop_subframe: int = 0,
) -> bytes:
    """Build vgmstream-compatible XMAWAVEFORMAT RIFF around raw packets."""
    if not 1 <= channels <= 8:
        raise AudioError(f"unsupported XMA1 channel count {channels}")
    if sample_rate <= 0:
        raise AudioError(f"invalid sample rate {sample_rate}")
    if not payload or len(payload) % XMA_PACKET_SIZE:
        raise AudioError("XMA1 payload is not a nonempty multiple of 2048 bytes")

    streams = (channels + 1) // 2
    fmt = bytearray()
    fmt += struct.pack("<HHHHHBB", 0x0165, 16, 0x10D6, 0, streams, 0, 2)
    remaining = channels
    stream_masks = (
        (0x0201, 0x0001),
        (0x0804, 0x0004),
        (0x8040, 0x0040),
        (0x2010, 0x0010),
    )
    for index in range(streams):
        stream_channels = 2 if remaining >= 2 else 1
        remaining -= stream_channels
        stereo_mask, mono_mask = stream_masks[index] if index < len(stream_masks) else (0, 0)
        fmt += struct.pack(
            "<IIIIBBH",
            sample_rate * stream_channels // 2,
            sample_rate,
            loop_start_bit,
            loop_end_bit,
            loop_subframe & 0xFF,
            stream_channels,
            stereo_mask if stream_channels == 2 else mono_mask,
        )
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + bytes(fmt)
    body += b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _read_part(
    reader: apf_inner.ArchiveReader,
    record: apf_inner.IFFRecord,
    part: apf_inner.FilePart,
    block_cache: dict[int, bytes],
    max_decompressed: int,
) -> bytes:
    block = record.blocks[part.block_index]
    if not block.is_compressed:
        return reader.read(
            record.entry,
            block.start_offset + part.offset,
            part.length,
        )
    if part.block_index not in block_cache:
        block_cache[part.block_index] = apf_inner.decode_block(
            reader, record, part.block_index, max_decompressed
        )
    data = block_cache[part.block_index]
    return data[part.offset : part.offset + part.length]


def _identify_parts(
    record: apf_inner.IFFRecord, item: apf_inner.DataFile
) -> tuple[apf_inner.FilePart, apf_inner.FilePart]:
    metadata_parts = [
        part
        for part in item.parts
        if record.blocks[part.block_index].type_hash
        == zlib.crc32(b"DRAM") & 0xFFFFFFFF
    ]
    payload_parts = [
        part
        for part in item.parts
        if record.blocks[part.block_index].type_hash
        == zlib.crc32(b"SRAM") & 0xFFFFFFFF
    ]
    if len(metadata_parts) != 1 or len(payload_parts) != 1:
        raise AudioError(
            f"entry {record.entry.table_index} file {item.index}: expected one "
            f"DRAM and one SRAM part, found {len(metadata_parts)}/{len(payload_parts)}"
        )
    return metadata_parts[0], payload_parts[0]


def _counter(values: Iterable[object]) -> dict[str, int]:
    counts = Counter(str(value) for value in values)
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def inventory(
    index_path: Path,
    manifest_path: Path,
    max_decompressed: int,
) -> dict[str, object]:
    selection, manifest_sha256 = load_selection(manifest_path)
    grouped: dict[int, list[SelectedAudio]] = defaultdict(list)
    for item in selection:
        grouped[item.table_index].append(item)

    archive = apf_outer.parse_archive(index_path)
    entry_by_index = {entry.table_index: entry for entry in archive.entries}
    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for table_index in sorted(grouped):
            entry = entry_by_index.get(table_index)
            if entry is None:
                raise AudioError(f"manifest references missing outer entry {table_index}")
            record = apf_inner.parse_iff(reader, entry)
            block_cache: dict[int, bytes] = {}
            for selected in grouped[table_index]:
                try:
                    item = record.files[selected.inner_index]
                    if item.type_name != AUDO_TYPE or item.name != selected.name:
                        raise AudioError("manifest/archive AUDO identity mismatch")
                    metadata_part, payload_part = _identify_parts(record, item)
                    metadata_data = _read_part(
                        reader, record, metadata_part, block_cache, max_decompressed
                    )
                    metadata = parse_metadata(metadata_data)
                    payload_data = _read_part(
                        reader, record, payload_part, block_cache, max_decompressed
                    )
                    payload_head = payload_data[:32]
                    packet = parse_packet_header(payload_head)
                    packet_summary = summarize_packets(payload_data)
                    row = {
                        "outer_table_index": table_index,
                        "inner_file_index": selected.inner_index,
                        "name": selected.name,
                        "metadata_part": {
                            "block_index": metadata_part.block_index,
                            "offset": metadata_part.offset,
                            "length": metadata_part.length,
                        },
                        "payload_part": {
                            "block_index": payload_part.block_index,
                            "offset": payload_part.offset,
                            "length": payload_part.length,
                        },
                        "metadata": metadata,
                        "first_packet": packet,
                        "packet_summary": packet_summary,
                        "payload_sha256": _sha256(payload_data),
                        "payload_head_sha256": _sha256(payload_head),
                        "invariants": {
                            "metadata_size_44": metadata_part.length == AUDO_METADATA_SIZE,
                            "encoded_size_matches_part": int(metadata["encoded_size"])
                            == payload_part.length,
                            "payload_packet_aligned": payload_part.length % XMA_PACKET_SIZE
                            == 0,
                            "known_channel_layout_code": metadata["derived_channel_count"]
                            is not None,
                            "loop_bit_range_bounded": 0
                            <= int(metadata["xma1_loop_start_bit_candidate"])
                            <= int(metadata["xma1_loop_end_bit_candidate"])
                            <= payload_part.length * 8,
                            "all_packets_classify_xma1": packet_summary[
                                "all_packets_classify_xma1"
                            ],
                            "all_xma1_metadata_is_2": packet_summary[
                                "all_xma1_metadata_is_2"
                            ],
                        },
                    }
                    rows.append(row)
                except (AudioError, apf_inner.FormatError, IndexError) as exc:
                    failures.append(
                        {
                            "outer_table_index": table_index,
                            "inner_file_index": selected.inner_index,
                            "name": selected.name,
                            "error": str(exc),
                            "portme": "inspect this AUDO variant manually",
                        }
                    )

    invariant_failures = sum(
        not all(bool(value) for value in row["invariants"].values()) for row in rows
    )
    summary = {
        "manifest_audo_count": len(selection),
        "parsed_audo_count": len(rows),
        "failure_count": len(failures),
        "invariant_failure_count": invariant_failures,
        "total_encoded_bytes": sum(
            int(row["payload_part"]["length"]) for row in rows
        ),
        "total_packet_count": sum(
            int(row["packet_summary"]["packet_count"]) for row in rows
        ),
        "metadata_size_distribution": _counter(
            row["metadata_part"]["length"] for row in rows
        ),
        "codec_or_version_distribution": _counter(
            row["metadata"]["codec_or_version"] for row in rows
        ),
        "unknown_04_distribution": _counter(
            row["metadata"]["unknown_04"] for row in rows
        ),
        "channel_layout_code_distribution": _counter(
            row["metadata"]["channel_layout_code"] for row in rows
        ),
        "derived_channel_count_distribution": _counter(
            row["metadata"]["derived_channel_count"] for row in rows
        ),
        "sample_rate_distribution": _counter(
            row["metadata"]["sample_rate"] for row in rows
        ),
        "packet_classification_distribution": _counter(
            row["first_packet"]["classification"] for row in rows
        ),
        "all_packet_sequences_zero_record_count": sum(
            row["packet_summary"]["xma1_sequence_distribution"]
            == {"0": int(row["packet_summary"]["packet_count"])}
            for row in rows
        ),
        "all_packet_skips_zero_record_count": sum(
            bool(row["packet_summary"]["all_xma1_packet_skips_are_zero"])
            for row in rows
        ),
        "remaining_word_distributions": {
            key: _counter(row["metadata"][key] for row in rows)
            for key in ("zero_14", "zero_1c", "xma1_loop_subframe_candidate")
        },
    }
    return {
        "schema": "apf_audo_inventory/v1",
        "source_index": str(index_path),
        "source_manifest": {
            "path": str(manifest_path),
            "sha256": manifest_sha256,
        },
        "constants": {
            "metadata_size": AUDO_METADATA_SIZE,
            "xma_packet_size": XMA_PACKET_SIZE,
            "integer_endianness": "big",
        },
        "summary": summary,
        "records": rows,
        "failures": failures,
        "portme": [
            "trace unknown_04 and the two zero words through the AUDO loader",
            "prove whether the XMA1 loop candidate triplet is playback looping or only valid-frame bounds",
            "prove speaker assignment before reversible import",
            "preserve original packets and metadata when exporting decoded PCM",
        ],
    }


def _decode_utf16be_z(data: bytes, offset: int = 0) -> tuple[str, int]:
    cursor = offset
    units = bytearray()
    while cursor + 2 <= len(data):
        unit = data[cursor : cursor + 2]
        cursor += 2
        if unit == b"\x00\x00":
            try:
                return units.decode("utf-16be"), cursor
            except UnicodeDecodeError as exc:
                raise AudioError("AUSB external filename is invalid UTF-16BE") from exc
        units.extend(unit)
    raise AudioError("AUSB external filename is not NUL-terminated")


def parse_ausb(data: bytes) -> dict[str, object]:
    if len(data) < 0x58:
        raise AudioError("AUSB record is shorter than its 0x58-byte prefix")
    external_filename, filename_end = _decode_utf16be_z(data)
    if not external_filename.lower().endswith(".bin"):
        raise AudioError(f"AUSB external filename is not .bin: {external_filename!r}")
    if filename_end > 0x40:
        raise AudioError("AUSB external filename overlaps fixed header at 0x40")
    padding = data[filename_end:0x40]
    padding_pattern = ("PADDING*" * 16).encode("utf-16le")
    if padding != padding_pattern[: len(padding)]:
        raise AudioError("AUSB filename padding does not match UTF-16LE PADDING* fill")

    values = struct.unpack_from(">6I", data, 0x40)
    entry_count, unknown_44, constant_48, sample_rate, unknown_50, layout_code = values
    table_end = 0x58 + entry_count * 8
    if table_end > len(data):
        raise AudioError("AUSB entry table extends beyond selected DRAM part")
    entries: list[dict[str, object]] = []
    for index in range(entry_count):
        value_bits, packet_offset = struct.unpack_from(">II", data, 0x58 + index * 8)
        value = struct.unpack(">f", struct.pack(">I", value_bits))[0]
        if not (-3.4028235e38 <= value <= 3.4028235e38):
            raise AudioError(f"AUSB entry {index} has non-finite float metadata")
        entries.append(
            {
                "index": index,
                "value_bits": _hex(value_bits),
                "value_float": value,
                "packet_offset": packet_offset,
            }
        )
    trailing = data[table_end:]
    if len(trailing) < 8:
        raise AudioError("AUSB trailing region lacks terminal boundary record")
    terminal_value_bits, terminal_packet_offset = struct.unpack_from(">II", trailing)
    terminal_value = struct.unpack(">f", struct.pack(">I", terminal_value_bits))[0]
    if not (-3.4028235e38 <= terminal_value <= 3.4028235e38):
        raise AudioError("AUSB terminal boundary has non-finite float metadata")
    return {
        "external_filename": external_filename,
        "external_filename_crc32_upper_ascii": _hex(
            zlib.crc32(external_filename.upper().encode("ascii")) & 0xFFFFFFFF
        ),
        "filename_end_offset": filename_end,
        "padding_length": len(padding),
        "entry_count": entry_count,
        "unknown_44": unknown_44,
        "constant_48": constant_48,
        "sample_rate": sample_rate,
        "unknown_50": unknown_50,
        "channel_layout_code": layout_code,
        "derived_channel_count": CHANNEL_LAYOUT_TO_COUNT.get(layout_code),
        "table_offset": 0x58,
        "table_end": table_end,
        "entries": entries,
        "terminal_boundary": {
            "value_bits": _hex(terminal_value_bits),
            "value_float": terminal_value,
            "packet_offset": terminal_packet_offset,
        },
        "trailing_length": len(trailing),
        "trailing_nonzero_byte_count": sum(byte != 0 for byte in trailing),
        "trailing_hex": trailing.hex(),
        "trailing_after_terminal_hex": trailing[8:].hex(),
        "sha256": _sha256(data),
    }


def inventory_ausb(
    index_path: Path,
    manifest_path: Path,
    max_decompressed: int,
) -> dict[str, object]:
    selection, manifest_sha256 = load_selection(manifest_path, AUSB_TYPE)
    grouped: dict[int, list[SelectedAudio]] = defaultdict(list)
    for item in selection:
        grouped[item.table_index].append(item)

    archive = apf_outer.parse_archive(index_path)
    entry_by_index = {entry.table_index: entry for entry in archive.entries}
    entries_by_id: dict[int, list[apf_outer.Entry]] = defaultdict(list)
    for entry in archive.entries:
        entries_by_id[entry.name_id].append(entry)

    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for table_index in sorted(grouped):
            record = apf_inner.parse_iff(reader, entry_by_index[table_index])
            cache: dict[int, bytes] = {}
            for selected in grouped[table_index]:
                try:
                    item = record.files[selected.inner_index]
                    if item.type_name != AUSB_TYPE or item.name != selected.name:
                        raise AudioError("manifest/archive AUSB identity mismatch")
                    if len(item.parts) != 1:
                        raise AudioError("AUSB does not have exactly one DRAM part")
                    part = item.parts[0]
                    if record.blocks[part.block_index].type_hash != (
                        zlib.crc32(b"DRAM") & 0xFFFFFFFF
                    ):
                        raise AudioError("AUSB selected part is not in DRAM")
                    data = _read_part(reader, record, part, cache, max_decompressed)
                    parsed = parse_ausb(data)
                    external_id = int(
                        str(parsed["external_filename_crc32_upper_ascii"]), 16
                    )
                    external_matches = entries_by_id.get(external_id, [])
                    if len(external_matches) != 1:
                        raise AudioError(
                            f"AUSB external filename resolves to {len(external_matches)} outer entries"
                        )
                    external = external_matches[0]
                    offsets = [int(value["packet_offset"]) for value in parsed["entries"]]
                    if offsets != sorted(offsets):
                        raise AudioError("AUSB external packet offsets are not sorted")
                    if offsets and offsets[0] != 0:
                        raise AudioError("AUSB first external packet offset is not zero")
                    ranges: list[dict[str, object]] = []
                    all_xma1 = True
                    for index, start in enumerate(offsets):
                        end = offsets[index + 1] if index + 1 < len(offsets) else external.size
                        if not 0 <= start < end <= external.size:
                            raise AudioError("AUSB external range is out of bounds")
                        if start % XMA_PACKET_SIZE or end % XMA_PACKET_SIZE:
                            raise AudioError("AUSB external range is not packet-aligned")
                        packet = parse_packet_header(reader.read(external, start, 4))
                        all_xma1 &= packet["classification"] == "xma1"
                        ranges.append(
                            {
                                "index": index,
                                "offset": start,
                                "length": end - start,
                                "packet_count": (end - start) // XMA_PACKET_SIZE,
                                "first_packet": packet,
                            }
                        )
                    terminal = parsed["terminal_boundary"]
                    terminal_offset_matches = int(terminal["packet_offset"]) == external.size
                    expanded_entries: list[dict[str, object]] = []
                    for index, value in enumerate(parsed["entries"]):
                        next_boundary = (
                            parsed["entries"][index + 1]
                            if index + 1 < len(parsed["entries"])
                            else terminal
                        )
                        duration = float(next_boundary["value_float"])
                        expanded_entries.append(
                            dict(
                                value,
                                external_range=ranges[index],
                                duration_seconds_candidate=duration,
                                declared_sample_count_candidate=round(
                                    duration * int(parsed["sample_rate"])
                                ),
                            )
                        )
                    first_duration_boundary = (
                        parsed["entries"][1]
                        if len(parsed["entries"]) > 1
                        else terminal
                    )
                    first_duration_is_duplicated = (
                        parsed["entries"][0]["value_bits"]
                        == first_duration_boundary["value_bits"]
                    )
                    parsed["entries"] = expanded_entries
                    row = {
                        "outer_table_index": table_index,
                        "inner_file_index": selected.inner_index,
                        "name": selected.name,
                        "part": {
                            "block_index": part.block_index,
                            "offset": part.offset,
                            "length": part.length,
                        },
                        "ausb": parsed,
                        "linked_external_outer_entry": {
                            "table_index": external.table_index,
                            "name_id": _hex(external.name_id),
                            "size": external.size,
                            "head_hex": external.head_hex,
                            "segments": [
                                {
                                    "pack_name": segment.pack_name,
                                    "pack_offset": segment.pack_offset,
                                    "size": segment.size,
                                }
                                for segment in external.segments
                            ],
                        },
                        "invariants": {
                            "part_size_covers_table": parsed["table_end"] <= part.length,
                            "constant_48_is_1": parsed["constant_48"] == 1,
                            "unknown_50_is_4096": parsed["unknown_50"] == 4096,
                            "known_channel_layout_code": parsed["derived_channel_count"]
                            is not None,
                            "external_head_is_xma_packet": external.head_hex == "08000000",
                            "all_external_ranges_classify_xma1": all_xma1,
                            "terminal_boundary_equals_external_size": terminal_offset_matches,
                            "first_duration_boundary_is_duplicated": first_duration_is_duplicated,
                        },
                    }
                    rows.append(row)
                except (AudioError, apf_inner.FormatError, IndexError, UnicodeError) as exc:
                    failures.append(
                        {
                            "outer_table_index": table_index,
                            "inner_file_index": selected.inner_index,
                            "name": selected.name,
                            "error": str(exc),
                            "portme": "inspect this AUSB/external-bank variant manually",
                        }
                    )

    unique_external = {
        int(row["linked_external_outer_entry"]["table_index"]): row[
            "linked_external_outer_entry"
        ]
        for row in rows
    }
    summary = {
        "manifest_ausb_count": len(selection),
        "parsed_ausb_count": len(rows),
        "failure_count": len(failures),
        "invariant_failure_count": sum(
            not all(bool(value) for value in row["invariants"].values()) for row in rows
        ),
        "unique_external_bin_count": len(unique_external),
        "total_substream_count": sum(int(row["ausb"]["entry_count"]) for row in rows),
        "total_duration_seconds_candidate": sum(
            sum(float(entry["duration_seconds_candidate"]) for entry in row["ausb"]["entries"])
            for row in rows
        ),
        "unique_external_encoded_bytes": sum(
            int(value["size"]) for value in unique_external.values()
        ),
        "sample_rate_distribution": _counter(row["ausb"]["sample_rate"] for row in rows),
        "channel_layout_code_distribution": _counter(
            row["ausb"]["channel_layout_code"] for row in rows
        ),
        "trailing_length_distribution": _counter(
            row["ausb"]["trailing_length"] for row in rows
        ),
        "unknown_44_distribution": _counter(row["ausb"]["unknown_44"] for row in rows),
    }
    return {
        "schema": "apf_ausb_external_bank_inventory/v1",
        "source_index": str(index_path),
        "source_manifest": {"path": str(manifest_path), "sha256": manifest_sha256},
        "summary": summary,
        "records": rows,
        "failures": failures,
        "portme": [
            "name the AUSB float metadata and remaining header/trailing fields from loader code",
            "recover exact per-substream sample counts and loops before bulk WAV export",
            "verify all external-bank substreams with a decoder and preserve bank ordering",
        ],
    }


def write_tsv(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = (
        "outer_table_index",
        "inner_file_index",
        "name",
        "unknown_04",
        "channel_layout_code",
        "derived_channel_count",
        "declared_sample_count",
        "sample_rate",
        "encoded_size",
        "packet_count",
        "packet_classification",
        "first_packet_word_be",
        "payload_sha256",
        "metadata_sha256",
    )
    with path.open("w", encoding="utf-8", newline="") as output:
        output.write("\t".join(columns) + "\n")
        for row in document["records"]:
            metadata = row["metadata"]
            packet = row["first_packet"]
            values = (
                row["outer_table_index"],
                row["inner_file_index"],
                row["name"],
                metadata["unknown_04"],
                metadata["channel_layout_code"],
                metadata["derived_channel_count"],
                metadata["declared_sample_count"],
                metadata["sample_rate"],
                metadata["encoded_size"],
                row["packet_summary"]["packet_count"],
                packet["classification"],
                packet["word_be"],
                row["payload_sha256"],
                metadata["sha256"],
            )
            output.write("\t".join(str(value).replace("\t", " ") for value in values) + "\n")


def parse_pcm_wav(path: Path) -> dict[str, int]:
    """Return exact PCM layout/sample count from a little-endian RIFF WAVE."""
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioError("decoded output is not a RIFF WAVE file")
    channels = sample_rate = bits_per_sample = data_length = None
    cursor = 12
    while cursor + 8 <= len(data):
        chunk_id = data[cursor : cursor + 4]
        chunk_size = struct.unpack_from("<I", data, cursor + 4)[0]
        payload = cursor + 8
        end = payload + chunk_size
        if end > len(data):
            raise AudioError("decoded WAV chunk extends beyond file")
        if chunk_id == b"fmt " and chunk_size >= 16:
            codec, channels, sample_rate, _, _, bits_per_sample = struct.unpack_from(
                "<HHIIHH", data, payload
            )
            if codec != 1:
                raise AudioError(f"decoded WAV codec is {codec}, expected PCM")
        elif chunk_id == b"data":
            data_length = chunk_size
        cursor = end + (chunk_size & 1)
    if None in (channels, sample_rate, bits_per_sample, data_length):
        raise AudioError("decoded WAV is missing fmt/data metadata")
    frame_size = int(channels) * int(bits_per_sample) // 8
    if frame_size <= 0 or int(data_length) % frame_size:
        raise AudioError("decoded WAV data size is not frame-aligned")
    return {
        "channels": int(channels),
        "sample_rate": int(sample_rate),
        "bits_per_sample": int(bits_per_sample),
        "data_length": int(data_length),
        "sample_count_per_channel": int(data_length) // frame_size,
    }


def _export_selected_impl(
    index_path: Path,
    table_index: int,
    inner_index: int,
    output_xma: Path,
    output_wav: Path | None,
    max_decompressed: int,
    *,
    cancel_requested: CancelRequested | None = None,
) -> dict[str, object]:
    check_cancel_requested(cancel_requested)
    archive = apf_outer.parse_archive(index_path)
    check_cancel_requested(cancel_requested)
    entries = [entry for entry in archive.entries if entry.table_index == table_index]
    if not entries:
        raise AudioError(f"no outer table index {table_index}")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entries[0])
        try:
            item = record.files[inner_index]
        except IndexError as exc:
            raise AudioError(f"entry {table_index} has no inner file {inner_index}") from exc
        if item.type_name != AUDO_TYPE:
            raise AudioError(f"selected file type is {item.type_name!r}, not AUDO")
        metadata_part, payload_part = _identify_parts(record, item)
        cache: dict[int, bytes] = {}
        metadata_data = _read_part(reader, record, metadata_part, cache, max_decompressed)
        payload = _read_part(reader, record, payload_part, cache, max_decompressed)
    check_cancel_requested(cancel_requested)
    metadata = parse_metadata(metadata_data)
    packet = parse_packet_header(payload[:32])
    if packet["classification"] != "xma1":
        raise AudioError(
            f"selected packet class is {packet['classification']}; refusing XMA1 wrapper"
        )
    if int(metadata["encoded_size"]) != len(payload):
        raise AudioError("metadata encoded size does not match selected SRAM payload")
    channels = metadata["derived_channel_count"]
    if channels is None:
        raise AudioError(
            f"unknown AUDO channel-layout code {metadata['channel_layout_code']}"
        )

    riff = make_xma1_riff(
        payload,
        int(channels),
        int(metadata["sample_rate"]),
        int(metadata["xma1_loop_start_bit_candidate"]),
        int(metadata["xma1_loop_end_bit_candidate"]),
        int(metadata["xma1_loop_subframe_candidate"]),
    )
    output_xma.parent.mkdir(parents=True, exist_ok=True)
    output_xma.write_bytes(riff)
    check_cancel_requested(cancel_requested)
    result: dict[str, object] = {
        "outer_table_index": table_index,
        "inner_file_index": inner_index,
        "name": item.name,
        "metadata": metadata,
        "first_packet": packet,
        "raw_payload_sha256": _sha256(payload),
        "xma": {
            "path": str(output_xma),
            "size": len(riff),
            "sha256": _sha256(riff),
            "status": "wrapped_unverified",
        },
        "wav": None,
    }
    if output_wav is not None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if ffmpeg is None or ffprobe is None:
            raise AudioError("--verify-wav requires ffmpeg and ffprobe")
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-y",
            "-i",
            str(output_xma),
            "-map_metadata",
            "-1",
            "-af",
            f"atrim=end_sample={int(metadata['declared_sample_count'])}",
            "-c:a",
            "pcm_s16le",
            str(output_wav),
        ]
        try:
            if cancel_requested is None:
                completed = subprocess.run(
                    command, capture_output=True, text=True, check=False
                )
            else:
                completed = run_cancellable_subprocess(
                    command,
                    cancel_requested=cancel_requested,
                    text=True,
                )
        except AudioError:
            output_wav.unlink(missing_ok=True)
            raise
        if completed.returncode != 0 or completed.stderr.strip() or not output_wav.is_file():
            result["xma"]["status"] = "decode_failed"
            result["wav"] = {
                "status": "failed",
                "ffmpeg_returncode": completed.returncode,
                "stderr": completed.stderr.strip(),
            }
            if output_wav.is_file():
                output_wav.unlink()
                result["wav"]["partial_output_removed"] = True
            return result
        wav_layout = parse_pcm_wav(output_wav)
        expected_samples = int(metadata["declared_sample_count"])
        layout_matches = (
            wav_layout["channels"] == int(channels)
            and wav_layout["sample_rate"] == int(metadata["sample_rate"])
            and wav_layout["bits_per_sample"] == 16
        )
        sample_delta = expected_samples - wav_layout["sample_count_per_channel"]
        # FFmpeg cleanly decodes some XMA1 streams to the preceding 128-sample
        # subframe boundary, while APF's declared count includes up to 127 tail
        # samples.  Accept the decoder-verified PCM but report the gap exactly;
        # do not synthesize or silently zero-pad samples that were not emitted.
        acceptable_tail_gap = 0 <= sample_delta < 128
        if not layout_matches or not acceptable_tail_gap:
            result["xma"]["status"] = "decode_incomplete"
            result["wav"] = {
                "status": "failed_sample_validation",
                "expected_sample_count_per_channel": expected_samples,
                "layout": wav_layout,
                "declared_minus_decoded_samples": sample_delta,
                "ffmpeg_stderr": completed.stderr.strip(),
            }
            output_wav.unlink()
            result["wav"]["partial_output_removed"] = True
            return result
        probe_command = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,channels,sample_rate,duration,nb_frames:format=duration,size",
            "-of",
            "json",
            str(output_wav),
        ]
        try:
            if cancel_requested is None:
                probe = subprocess.run(
                    probe_command,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                probe = run_cancellable_subprocess(
                    probe_command,
                    cancel_requested=cancel_requested,
                    text=True,
                )
        except AudioError:
            output_wav.unlink(missing_ok=True)
            raise
        if probe.returncode != 0:
            raise AudioError(f"ffprobe rejected decoded WAV: {probe.stderr.strip()}")
        status = (
            "decoder_verified_exact_declared_samples"
            if sample_delta == 0
            else "decoder_verified_with_declared_tail_gap"
        )
        result["xma"]["status"] = status
        result["wav"] = {
            "status": status,
            "path": str(output_wav),
            "size": output_wav.stat().st_size,
            "sha256": hashlib.sha256(output_wav.read_bytes()).hexdigest(),
            "probe": json.loads(probe.stdout),
            "layout": wav_layout,
            "expected_sample_count_per_channel": expected_samples,
            "declared_minus_decoded_samples": sample_delta,
            "ffmpeg_stderr": completed.stderr.strip(),
        }
        try:
            check_cancel_requested(cancel_requested)
        except AudioError:
            output_wav.unlink(missing_ok=True)
            raise
    return result


def export_selected(
    index_path: Path,
    table_index: int,
    inner_index: int,
    output_xma: Path,
    output_wav: Path | None,
    max_decompressed: int,
    *,
    cancel_requested: CancelRequested | None = None,
) -> dict[str, object]:
    """Export one AUDO sound, staging cancellable work before publication."""

    if cancel_requested is None:
        return _export_selected_impl(
            index_path,
            table_index,
            inner_index,
            output_xma,
            output_wav,
            max_decompressed,
        )

    check_cancel_requested(cancel_requested)
    with tempfile.TemporaryDirectory(prefix="apf-audo-cancellable-export-") as name:
        temporary = Path(name)
        staged_xma = temporary / "selected.xma"
        staged_wav = temporary / "selected.wav" if output_wav is not None else None
        result = _export_selected_impl(
            index_path,
            table_index,
            inner_index,
            staged_xma,
            staged_wav,
            max_decompressed,
            cancel_requested=cancel_requested,
        )
        check_cancel_requested(cancel_requested)
        _publish_complete_file(staged_xma, output_xma)
        result["xma"]["path"] = str(output_xma)
        if output_wav is not None:
            wav_report = result.get("wav")
            if isinstance(wav_report, dict) and staged_wav is not None:
                if staged_wav.is_file() and "path" in wav_report:
                    _publish_complete_file(staged_wav, output_wav)
                    wav_report["path"] = str(output_wav)
        return result


def _decode_unique_task(task: dict[str, object], ffmpeg: str) -> dict[str, object]:
    riff = task.pop("riff")
    channels = int(task["derived_channel_count"])
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-xerror",
                "-i",
                "pipe:0",
                "-map",
                "0:a:0",
                "-f",
                "s16le",
                "-c:a",
                "pcm_s16le",
                "pipe:1",
            ],
            input=riff,
            capture_output=True,
            check=False,
            timeout=120,
        )
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        stderr = re.sub(r" @ 0x[0-9A-Fa-f]+", " @ 0xADDR", stderr)
        frame_size = channels * 2
        aligned = len(completed.stdout) % frame_size == 0
        decoded_samples = len(completed.stdout) // frame_size if aligned else None
        declared = int(task["declared_sample_count"])
        decoder_clean = completed.returncode == 0 and not stderr
        if decoder_clean and aligned and decoded_samples and decoded_samples > 0:
            delta = declared - decoded_samples
            if delta == 0:
                status = "decoder_verified_exact_declared_samples"
            elif 0 < delta < 128:
                status = "decoder_verified_with_declared_tail_gap"
            elif -128 < delta < 0:
                status = "decoder_verified_with_padding_tail"
            else:
                status = "decoded_with_large_sample_delta"
        else:
            delta = None if decoded_samples is None else declared - decoded_samples
            status = "decode_failed"
        task.update(
            {
                "status": status,
                "ffmpeg_returncode": completed.returncode,
                "decoded_pcm_bytes": len(completed.stdout),
                "decoded_sample_count_per_channel": decoded_samples,
                "declared_minus_decoded_samples": delta,
                "stderr": stderr,
            }
        )
    except subprocess.TimeoutExpired:
        task.update(
            {
                "status": "decode_timeout",
                "ffmpeg_returncode": None,
                "decoded_pcm_bytes": 0,
                "decoded_sample_count_per_channel": None,
                "declared_minus_decoded_samples": None,
                "stderr": "FFmpeg decode exceeded 120 seconds",
            }
        )
    return task


def verify_unique_payloads(
    index_path: Path,
    inventory_document: dict[str, object],
    jobs: int,
    max_decompressed: int,
) -> dict[str, object]:
    if jobs <= 0:
        raise AudioError("--jobs must be positive")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioError("unique decode verification requires ffmpeg")

    records = inventory_document["records"]
    duplicates = Counter(str(row["payload_sha256"]) for row in records)
    representatives: dict[str, dict[str, object]] = {}
    for row in records:
        representatives.setdefault(str(row["payload_sha256"]), row)

    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in representatives.values():
        grouped[int(row["outer_table_index"])].append(row)

    archive = apf_outer.parse_archive(index_path)
    entry_by_index = {entry.table_index: entry for entry in archive.entries}
    tasks: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for table_index in sorted(grouped):
            record = apf_inner.parse_iff(reader, entry_by_index[table_index])
            cache: dict[int, bytes] = {}
            for row in sorted(grouped[table_index], key=lambda value: int(value["inner_file_index"])):
                item = record.files[int(row["inner_file_index"])]
                metadata_part, payload_part = _identify_parts(record, item)
                metadata = parse_metadata(
                    _read_part(reader, record, metadata_part, cache, max_decompressed)
                )
                payload = _read_part(reader, record, payload_part, cache, max_decompressed)
                payload_sha256 = _sha256(payload)
                if payload_sha256 != row["payload_sha256"]:
                    raise AudioError("unique verification payload hash disagrees with inventory")
                channels = metadata["derived_channel_count"]
                if channels is None:
                    raise AudioError("unique verification found unknown channel layout")
                riff = make_xma1_riff(
                    payload,
                    int(channels),
                    int(metadata["sample_rate"]),
                    int(metadata["xma1_loop_start_bit_candidate"]),
                    int(metadata["xma1_loop_end_bit_candidate"]),
                    int(metadata["xma1_loop_subframe_candidate"]),
                )
                tasks.append(
                    {
                        "outer_table_index": table_index,
                        "inner_file_index": item.index,
                        "name": item.name,
                        "payload_sha256": payload_sha256,
                        "duplicate_record_count": duplicates[payload_sha256],
                        "encoded_size": len(payload),
                        "xma_riff_sha256": _sha256(riff),
                        "channel_layout_code": metadata["channel_layout_code"],
                        "derived_channel_count": channels,
                        "sample_rate": metadata["sample_rate"],
                        "declared_sample_count": metadata["declared_sample_count"],
                        "riff": riff,
                    }
                )

    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(_decode_unique_task, task, ffmpeg) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: (int(row["outer_table_index"]), int(row["inner_file_index"])))

    status_distribution = _counter(row["status"] for row in results)
    failed = [row for row in results if not str(row["status"]).startswith("decoder_verified")]
    failed_record_count = sum(int(row["duplicate_record_count"]) for row in failed)
    version = subprocess.run(
        [ffmpeg, "-version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]
    return {
        "schema": "apf_audo_unique_decode_verification/v1",
        "source_index": str(index_path),
        "ffmpeg_version": version,
        "jobs": jobs,
        "summary": {
            "audo_record_count": len(records),
            "unique_payload_count": len(results),
            "duplicate_record_count": len(records) - len(results),
            "decoder_verified_unique_payload_count": len(results) - len(failed),
            "not_decoder_verified_unique_payload_count": len(failed),
            "decoder_verified_audo_record_count": len(records) - failed_record_count,
            "not_decoder_verified_audo_record_count": failed_record_count,
            "status_distribution": status_distribution,
            "failed_sample_rate_distribution": _counter(
                row["sample_rate"] for row in failed
            ),
        },
        "results": results,
        "portme": (
            "resolve every non-decoder-verified unique payload before claiming "
            "universal AUDO-to-WAV conversion"
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to APF first volume (0A)")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/manifests/apf_inner.json"),
        help="canonical APF inner manifest",
    )
    parser.add_argument("--inventory-json", type=Path)
    parser.add_argument("--inventory-tsv", type=Path)
    parser.add_argument(
        "--ausb-json",
        type=Path,
        help="inventory AUSB descriptors and resolve their external raw-XMA .bin entries",
    )
    parser.add_argument(
        "--verify-unique-json",
        type=Path,
        help="decode every unique payload with FFmpeg and write a deterministic report",
    )
    parser.add_argument(
        "--jobs", type=int, default=4, help="parallel FFmpeg jobs for --verify-unique-json"
    )
    parser.add_argument("--export-entry", type=int)
    parser.add_argument("--export-file", type=int)
    parser.add_argument("--output-xma", type=Path)
    parser.add_argument("--verify-wav", type=Path, metavar="PATH")
    parser.add_argument(
        "--export-report", type=Path, help="write selected export/verification JSON"
    )
    parser.add_argument(
        "--max-decompressed",
        type=int,
        default=apf_inner.DEFAULT_MAX_DECOMPRESSED,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    exporting = any(
        value is not None
        for value in (args.export_entry, args.export_file, args.output_xma, args.verify_wav)
    )
    if exporting and any(
        value is None for value in (args.export_entry, args.export_file, args.output_xma)
    ):
        print(
            "error: export requires --export-entry, --export-file, and --output-xma",
            file=sys.stderr,
        )
        return 2
    if (
        not exporting
        and args.inventory_json is None
        and args.inventory_tsv is None
        and args.ausb_json is None
        and args.verify_unique_json is None
    ):
        print("error: request an inventory or selected export", file=sys.stderr)
        return 2
    try:
        if exporting:
            result = export_selected(
                args.index,
                args.export_entry,
                args.export_file,
                args.output_xma,
                args.verify_wav,
                args.max_decompressed,
            )
            if args.export_report is not None:
                args.export_report.parent.mkdir(parents=True, exist_ok=True)
                args.export_report.write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf-8"
                )
            print(
                f"APF AUDO export: entry={args.export_entry} file={args.export_file} "
                f"xma={result['xma']['status']} wav="
                f"{None if result['wav'] is None else result['wav']['status']}"
            )
            if args.verify_wav is not None:
                return 0 if str(result["xma"]["status"]).startswith("decoder_verified") else 1
            return 0

        document = inventory(args.index, args.manifest, args.max_decompressed)
        ausb_document = None
        if args.inventory_json is not None:
            args.inventory_json.parent.mkdir(parents=True, exist_ok=True)
            args.inventory_json.write_text(
                json.dumps(document, indent=2) + "\n", encoding="utf-8"
            )
        if args.inventory_tsv is not None:
            write_tsv(args.inventory_tsv, document)
        if args.ausb_json is not None:
            ausb_document = inventory_ausb(
                args.index, args.manifest, args.max_decompressed
            )
            args.ausb_json.parent.mkdir(parents=True, exist_ok=True)
            args.ausb_json.write_text(
                json.dumps(ausb_document, indent=2) + "\n", encoding="utf-8"
            )
        unique_verification = None
        if args.verify_unique_json is not None:
            unique_verification = verify_unique_payloads(
                args.index, document, args.jobs, args.max_decompressed
            )
            args.verify_unique_json.parent.mkdir(parents=True, exist_ok=True)
            args.verify_unique_json.write_text(
                json.dumps(unique_verification, indent=2) + "\n", encoding="utf-8"
            )
        summary = document["summary"]
        print(
            f"APF AUDO inventory: {summary['parsed_audo_count']}/"
            f"{summary['manifest_audo_count']} parsed; failures={summary['failure_count']}; "
            f"invariant_failures={summary['invariant_failure_count']}"
        )
        if unique_verification is not None:
            unique_summary = unique_verification["summary"]
            print(
                f"APF AUDO unique decode: "
                f"{unique_summary['decoder_verified_unique_payload_count']}/"
                f"{unique_summary['unique_payload_count']} verified; "
                f"not_verified={unique_summary['not_decoder_verified_unique_payload_count']}"
            )
        if ausb_document is not None:
            ausb_summary = ausb_document["summary"]
            print(
                f"APF AUSB inventory: {ausb_summary['parsed_ausb_count']}/"
                f"{ausb_summary['manifest_ausb_count']} parsed; "
                f"external_bins={ausb_summary['unique_external_bin_count']}; "
                f"substreams={ausb_summary['total_substream_count']}"
            )
        return 0 if not summary["failure_count"] and not summary["invariant_failure_count"] else 1
    except (AudioError, apf_inner.FormatError, apf_outer.FormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
