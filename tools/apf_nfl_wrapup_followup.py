#!/usr/bin/env python3
"""Extend the APF/NFL archaeology with the previously unpaired awards cluster.

This is a read-only evidence generator.  It never writes either game's files,
never launches either game, and never executes translated guest code.  It
joins already recovered archive, audio, layout, director, and Ghidra evidence,
then independently reparses the source archives for the new claims.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave
import zlib

import apf_audio
import apf_inner
import apf_outer
from nfl_outer import parse_archive as parse_nfl_archive
from nfl_scene_probe import (
    decode_resource,
    named_inner,
    parse_inventory as parse_nfl_inventory,
    read_entry_range,
)


SCHEMA = "vc_apf_nfl_wrapup_followup/v1"
MAX_DECOMPRESSED = 256 * 1024 * 1024
COMPARABLE_KINDS = {"AMCR", "AUDO", "AUSB", "LAYT", "MRKS", "SCNE", "STRG", "TXTR"}

APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"

WRAPUP_CLUSTER = [
    ("awards", "AWARDS.IFF", 349, 17),
    ("show", "FRANCHISE_SHOW.IFF", 730, 18),
    ("director", "DIR_WRAPUP.IFF", 265, 19),
    ("intro", "FRANCHISE_SHOW_INTRO.IFF", 1221, 20),
    ("outro", "FRANCHISE_SHOW_OUTRO.IFF", 941, 21),
]


class FollowupError(ValueError):
    """Raised when a source-pinned follow-up invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FollowupError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)}


def source_labeled(path: Path, label: str) -> dict[str, object]:
    return {"path": label, "size": path.stat().st_size, "sha256": sha256_file(path)}


def crc_ascii_upper(filename: str) -> int:
    return zlib.crc32(filename.upper().encode("ascii")) & 0xFFFFFFFF


def crc_utf16le_upper(filename: str) -> int:
    return zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF


def read_apf_file(
    reader: apf_inner.ArchiveReader,
    record: apf_inner.IFFRecord,
    item: apf_inner.InnerFile,
    cache: dict[int, bytes],
) -> tuple[list[bytes], bytes]:
    parts: list[bytes] = []
    for part in item.parts:
        if part.block_index not in cache:
            cache[part.block_index] = apf_inner.decode_block(
                reader, record, part.block_index, MAX_DECOMPRESSED
            )
        decoded = cache[part.block_index]
        end = part.offset + part.length
        require(end <= len(decoded), "APF inner part exceeds decoded block")
        parts.append(decoded[part.offset:end])
    return parts, b"".join(parts)


def apf_resource_rows(
    archive: apf_outer.Archive,
    reader: apf_inner.ArchiveReader,
    outer_index: int,
) -> tuple[apf_inner.IFFRecord, list[dict[str, object]], dict[int, list[bytes]]]:
    record = apf_inner.parse_iff(reader, archive.entries[outer_index])
    cache: dict[int, bytes] = {}
    parts_by_index: dict[int, list[bytes]] = {}
    rows: list[dict[str, object]] = []
    for item in record.files:
        require(item.name is not None and item.type_name is not None, "unnamed APF inner file")
        parts, body = read_apf_file(reader, record, item, cache)
        parts_by_index[item.index] = parts
        rows.append(
            {
                "inner_index": item.index,
                "name": item.name,
                "kind": item.type_name,
                "part_sizes": [len(part) for part in parts],
                "decoded_body_size": len(body),
                "decoded_body_sha256": sha256_bytes(body),
            }
        )
    return record, rows, parts_by_index


def nfl_resource_rows(
    archive: object,
    inventory: list[object],
    outer_index: int,
    kinds: set[str],
) -> tuple[list[dict[str, object]], dict[tuple[str, str], bytes]]:
    entry = archive.entries[outer_index]
    rows: list[dict[str, object]] = []
    bodies: dict[tuple[str, str], bytes] = {}
    for record in inventory:
        if record.outer_index != outer_index or record.kind not in kinds:
            continue
        span = read_entry_range(archive, entry, record.chunk_offset, 0x20 + record.stored_size)
        data, _ = decode_resource(span, record)
        name, _, _ = named_inner(data, record.kind)
        require(data[0x0C:0x10] == record.kind.encode("ascii"), "NFL inner marker changed")
        body = data[0x20:]
        row = {
            "inner_index": record.chunk_index,
            "name": name,
            "kind": record.kind,
            "decoded_resource_size": len(data),
            "decoded_body_size_after_common_header": len(body),
            "decoded_resource_sha256": sha256_bytes(data),
            "decoded_body_sha256": sha256_bytes(body),
        }
        rows.append(row)
        bodies[(name.casefold(), record.kind)] = data
    rows.sort(key=lambda row: int(row["inner_index"]))
    return rows, bodies


def read_wav_pcm(path: Path) -> tuple[int, int, object]:
    import numpy as np

    with wave.open(str(path), "rb") as stream:
        require(stream.getsampwidth() == 2, "comparison WAV is not PCM16")
        channels = stream.getnchannels()
        rate = stream.getframerate()
        frames = stream.readframes(stream.getnframes())
    pcm = np.frombuffer(frames, dtype="<i2").reshape(-1, channels).astype(np.float64)
    return channels, rate, pcm


def decode_xma_pcm(riff: bytes, channels: int) -> object:
    import numpy as np

    ffmpeg = shutil.which("ffmpeg")
    require(ffmpeg is not None, "ffmpeg is required for audio-lineage verification")
    completed = subprocess.run(
        [
            ffmpeg,
            "-v", "error", "-xerror", "-i", "pipe:0", "-map", "0:a:0",
            "-f", "s16le", "-c:a", "pcm_s16le", "pipe:1",
        ],
        input=riff,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"FFmpeg rejected XMA: {completed.stderr.decode(errors='replace')}")
    require(not completed.stderr.strip(), "FFmpeg emitted XMA decoder diagnostics")
    require(len(completed.stdout) % (channels * 2) == 0, "decoded PCM is not frame-aligned")
    return np.frombuffer(completed.stdout, dtype="<i2").reshape(-1, channels).astype(np.float64)


def spectrum(samples: object, frame: int = 512, hop: int = 256) -> object:
    import numpy as np

    signal = samples.mean(axis=1)
    window = np.hanning(frame)
    result = np.zeros(frame // 2 + 1, dtype=np.float64)
    count = 0
    for offset in range(0, max(0, len(signal) - frame + 1), hop):
        result += np.abs(np.fft.rfft(signal[offset : offset + frame] * window))
        count += 1
    require(count > 0, "audio is too short for spectral comparison")
    return result


def cosine(first: object, second: object) -> float:
    import numpy as np

    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    require(denominator > 0.0, "zero-energy audio spectrum")
    return float(np.dot(first, second) / denominator)


def frontend_audio_lineage(
    root: Path,
    apf_rows: list[dict[str, object]],
    apf_parts: dict[int, list[bytes]],
) -> list[dict[str, object]]:
    import numpy as np

    inventory = json.loads((root / "reports/assets/apf_audio_inventory.json").read_text())
    apf_audio_rows = {
        (row["outer_table_index"], row["inner_file_index"]): row
        for row in inventory["records"]
    }
    nfl_report = json.loads((root / "reports/assets/nfl2k5_audo_wav_all.json").read_text())
    nfl_rows = {
        row["semantic"]["name"].casefold(): row
        for row in nfl_report["records"]
        if row["outer_index"] == 9
    }
    result: list[dict[str, object]] = []
    for resource in apf_rows:
        if resource["kind"] != "AUDO":
            continue
        name = str(resource["name"])
        inner_index = int(resource["inner_index"])
        require(name.casefold() in nfl_rows, f"frontend AUDO {name} lost NFL peer")
        metadata = apf_audio_rows[(988, inner_index)]["metadata"]
        parts = apf_parts[inner_index]
        require(len(parts) == 2, f"frontend AUDO {name} part count changed")
        channels = int(metadata["derived_channel_count"])
        rate = int(metadata["sample_rate"])
        riff = apf_audio.make_xma1_riff(
            parts[1], channels, rate,
            int(metadata["xma1_loop_start_bit_candidate"]),
            int(metadata["xma1_loop_end_bit_candidate"]),
            int(metadata["xma1_loop_subframe_candidate"]),
        )
        apf_pcm = decode_xma_pcm(riff, channels)
        nfl = nfl_rows[name.casefold()]
        nfl_channels, nfl_rate, nfl_pcm = read_wav_pcm(root / nfl["wav_output"])
        apf_rms = float(np.sqrt(np.mean(apf_pcm * apf_pcm)))
        nfl_rms = float(np.sqrt(np.mean(nfl_pcm * nfl_pcm)))
        row = {
            "name": name,
            "apf_inner_index": inner_index,
            "nfl_chunk_index": nfl["chunk_index"],
            "apf_codec": "XMA1",
            "nfl_codec": "Xbox IMA ADPCM",
            "apf_channels": channels,
            "nfl_channels": nfl_channels,
            "apf_sample_rate": rate,
            "nfl_sample_rate": nfl_rate,
            "apf_decoded_samples_per_channel": len(apf_pcm),
            "nfl_decoded_samples_per_channel": len(nfl_pcm),
            "sample_delta_apf_minus_nfl": len(apf_pcm) - len(nfl_pcm),
            "global_stft_magnitude_cosine": cosine(spectrum(apf_pcm), spectrum(nfl_pcm)),
            "apf_rms": apf_rms,
            "nfl_rms": nfl_rms,
            "rms_ratio": apf_rms / nfl_rms,
        }
        row["probable_common_source_transcode"] = bool(
            channels == nfl_channels
            and rate == nfl_rate
            and abs(int(row["sample_delta_apf_minus_nfl"])) <= 128
            and float(row["global_stft_magnitude_cosine"]) >= 0.95
            and 0.90 <= float(row["rms_ratio"]) <= 1.10
        )
        result.append(row)
    result.sort(key=lambda row: int(row["apf_inner_index"]))
    return result


def parse_nfl_drafta(
    archive: object,
    inventory: list[object],
) -> dict[str, object]:
    rows, bodies = nfl_resource_rows(archive, inventory, 3, {"AUSB"})
    match = [row for row in rows if row["name"].casefold() == "drafta"]
    require(len(match) == 1, "NFL global drafta AUSB identity changed")
    data = bodies[("drafta", "AUSB")]
    require(len(data) == 176, "NFL drafta AUSB size changed")
    require(data[0x20:0x2E] == "drafta\0".encode("utf-16le"), "NFL drafta name changed")
    require(data[0x40:0x56] == "drafta.bin\0".encode("utf-16le"), "NFL drafta.bin changed")
    count, unknown_84, channel_word, sample_rate, unit_word = struct.unpack_from("<5I", data, 0x80)
    require(count == 4, "NFL drafta track count changed")
    boundaries = list(struct.unpack_from(f"<{count + 1}I", data, 0x98))
    require(boundaries[0] == 0 and boundaries == sorted(boundaries), "NFL drafta boundaries changed")
    external_id = crc_utf16le_upper("DRAFTA.BIN")
    matches = [entry for entry in archive.entries if entry.name_id == external_id]
    require(len(matches) == 1, "NFL drafta.bin outer identity is ambiguous")
    external = matches[0]
    require(boundaries[-1] == external.size, "NFL drafta terminal boundary differs from bank size")
    return {
        "outer_index": 3,
        "chunk_index": int(match[0]["inner_index"]),
        "name": "drafta",
        "type": "AUSB",
        "descriptor_size": len(data),
        "external_filename": "drafta.bin",
        "entry_count": count,
        "unknown_84": unknown_84,
        "channel_word_88": channel_word,
        "sample_rate_word_8c": sample_rate,
        "unit_word_90": unit_word,
        "packet_boundaries": boundaries,
        "substream_lengths": [boundaries[index + 1] - boundaries[index] for index in range(count)],
        "external_outer_index": external.table_index,
        "external_outer_id": f"0x{external.name_id:08x}",
        "external_encoded_size": external.size,
        "decoded_resource_sha256": match[0]["decoded_resource_sha256"],
    }


def verify_apf_drafta_decode(
    archive: apf_outer.Archive,
    reader: apf_inner.ArchiveReader,
    record: dict[str, object],
) -> list[dict[str, object]]:
    ausb = record["ausb"]
    external = record["linked_external_outer_entry"]
    external_entry = archive.entries[int(external["table_index"])]
    channels = int(ausb["derived_channel_count"])
    rate = int(ausb["sample_rate"])
    entries = ausb["entries"]
    output: list[dict[str, object]] = []
    for index, boundary in enumerate(entries):
        start = int(boundary["packet_offset"])
        end = int(
            entries[index + 1]["packet_offset"]
            if index + 1 < len(entries)
            else ausb["terminal_boundary"]["packet_offset"]
        )
        payload = reader.read(external_entry, start, end - start)
        pcm = decode_xma_pcm(apf_audio.make_xma1_riff(payload, channels, rate), channels)
        declared = int(boundary["declared_sample_count_candidate"])
        shortfall = declared - len(pcm)
        require(abs(shortfall) < 128, f"APF drafta {index} decoded sample delta changed")
        output.append(
            {
                "index": index,
                "range_offset": start,
                "range_length": end - start,
                "packet_count": (end - start) // 2048,
                "duration_seconds_candidate": float(boundary["duration_seconds_candidate"]),
                "declared_sample_count_candidate": declared,
                "raw_decoded_samples_per_channel": len(pcm),
                "declared_minus_raw_decoded_samples": shortfall,
                "decoder_verified": True,
                "payload_sha256": sha256_bytes(payload),
            }
        )
    return output


def read_utf16be_at(pe: bytes, address: int) -> str:
    offset = address - 0x82000000
    require(0 <= offset < len(pe), "PE string address out of bounds")
    chars: list[str] = []
    while offset + 2 <= len(pe):
        value = struct.unpack_from(">H", pe, offset)[0]
        offset += 2
        if value == 0:
            return "".join(chars)
        chars.append(chr(value))
    raise FollowupError("unterminated UTF-16BE PE string")


def count_needle(data: bytes, needle: bytes) -> int:
    count = 0
    offset = 0
    while True:
        offset = data.find(needle, offset)
        if offset < 0:
            return count
        count += 1
        offset += 1


def find_all(data: bytes, needle: bytes) -> list[int]:
    result: list[int] = []
    offset = 0
    while True:
        offset = data.find(needle, offset)
        if offset < 0:
            return result
        result.append(offset)
        offset += 1


def build(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.resolve()
    apf_index = root / "extracted/All-Pro Football 2K8 (USA)/0A"
    apf_xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    nfl_index = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    nfl_xbe = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    pe_path = args.apf_pe.resolve()
    trace_path = args.ghidra_trace.resolve()
    require(sha256_file(apf_xex) == APF_XEX_SHA256, "APF XEX hash changed")
    require(sha256_file(pe_path) == APF_PE_SHA256, "reconstructed APF PE hash changed")
    require(sha256_file(nfl_xbe) == NFL_XBE_SHA256, "NFL XBE hash changed")

    apf_archive = apf_outer.parse_archive(apf_index)
    nfl_archive = parse_nfl_archive(nfl_index)
    _, nfl_inventory = parse_nfl_inventory(root / "reports/assets/nfl2k5_resource_chunks_v2.json")

    with apf_inner.ArchiveReader(apf_archive) as apf_reader:
        _, awards_apf, _ = apf_resource_rows(apf_archive, apf_reader, 349)
        _, frontend_apf, frontend_parts = apf_resource_rows(apf_archive, apf_reader, 988)

        awards_nfl, _ = nfl_resource_rows(nfl_archive, nfl_inventory, 17, {"MRKS"})
        require(
            [(row["name"], row["kind"]) for row in awards_apf]
            == [("primetimePlayers", "MRKS"), ("seasonAwards", "MRKS")],
            "APF awards resource order changed",
        )
        require(
            [(row["name"], row["kind"]) for row in awards_nfl]
            == [("primetimePlayers", "MRKS"), ("seasonAwards", "MRKS")],
            "NFL awards resource order changed",
        )

        frontend_nfl, _ = nfl_resource_rows(
            nfl_archive, nfl_inventory, 9, COMPARABLE_KINDS
        )
        apf_keys = {(str(row["name"]).casefold(), str(row["kind"])) for row in frontend_apf}
        nfl_keys = {(str(row["name"]).casefold(), str(row["kind"])) for row in frontend_nfl}
        shared_frontend = sorted(apf_keys & nfl_keys)
        require(len(frontend_apf) == 57 and len(frontend_nfl) == 57, "frontend comparable count changed")
        require(len(shared_frontend) == 52, "frontend shared resource count changed")
        audio_lineage = frontend_audio_lineage(root, frontend_apf, frontend_parts)
        require(len(audio_lineage) == 23, "frontend audio count changed")
        common_audio = [row for row in audio_lineage if row["probable_common_source_transcode"]]
        require(len(common_audio) == 17, "frontend common-source audio count changed")
        front_office = [row for row in audio_lineage if "front-office" in str(row["name"])]
        require(len(front_office) == 2, "front-office cue count changed")
        require(all(row["probable_common_source_transcode"] for row in front_office),
                "front-office common-source proof changed")

        ausb_inventory = json.loads((root / "reports/assets/apf_ausb_inventory.json").read_text())
        apf_drafta_rows = [
            row for row in ausb_inventory["records"]
            if row["outer_table_index"] == 1310 and row["inner_file_index"] == 51
        ]
        require(len(apf_drafta_rows) == 1, "APF drafta AUSB identity changed")
        apf_drafta = apf_drafta_rows[0]
        drafta_decode = verify_apf_drafta_decode(apf_archive, apf_reader, apf_drafta)

    nfl_drafta = parse_nfl_drafta(nfl_archive, nfl_inventory)
    require(apf_drafta["ausb"]["entry_count"] == nfl_drafta["entry_count"] == 4,
            "drafta track-count lineage changed")

    lineage = json.loads(
        (root / "reports/cut_content/apf_nfl_lineage/lineage.json").read_text()
    )
    show_marker_witnesses = sorted(
        row["name"] for row in lineage["resources"]
        if row["apf_outer_index"] == 730 and row["type"] == "MRKS"
        and row["name"] in {"show_primetime_players", "show_season_awards"}
    )
    require(
        show_marker_witnesses == ["show_primetime_players", "show_season_awards"],
        "franchise_show awards-marker witnesses changed",
    )
    archive_summaries = {row["apf_outer_index"]: row for row in lineage["archive_summaries"]}
    director = json.loads(
        (root / "reports/assets/cross_title_director_inventory.json").read_text()
    )
    wrapup_director = [row for row in director["cross_title_roles"] if row["role"] == "wrapup"]
    require(len(wrapup_director) == 1, "wrapup director lineage row changed")
    wrapup_director = wrapup_director[0]
    require(wrapup_director["instruction_record_count"] == {"apf": 96, "nfl": 96},
            "wrapup director instruction counts changed")
    require(wrapup_director["nonnull_fixed_record_count"] == {"apf": 20, "nfl": 20},
            "wrapup director fixed-record counts changed")
    require(wrapup_director["ordered_structural_signature_match_count"] == 19,
            "wrapup director structural match count changed")

    cluster_rows: list[dict[str, object]] = []
    for role, filename, apf_outer_index, nfl_outer_index in WRAPUP_CLUSTER:
        apf_entry = apf_archive.entries[apf_outer_index]
        nfl_entry = nfl_archive.entries[nfl_outer_index]
        expected_apf = crc_ascii_upper(filename)
        expected_nfl = crc_utf16le_upper(filename)
        require(apf_entry.name_id == expected_apf, f"APF {filename} outer ID changed")
        require(nfl_entry.name_id == expected_nfl, f"NFL {filename} outer ID changed")
        row: dict[str, object] = {
            "role": role,
            "filename": filename.lower(),
            "apf_outer_index": apf_outer_index,
            "apf_outer_id": f"0x{apf_entry.name_id:08x}",
            "apf_filename_hash_rule": "CRC32(uppercase ASCII filename)",
            "nfl_outer_index": nfl_outer_index,
            "nfl_outer_id": f"0x{nfl_entry.name_id:08x}",
            "nfl_filename_hash_rule": "CRC32(uppercase UTF-16LE filename)",
        }
        if role == "awards":
            row.update(
                {
                    "apf_resource_count": 2,
                    "nfl_resource_count": 2,
                    "direct_shared_name_type_count": 2,
                    "resource_order": ["primetimePlayers:MRKS", "seasonAwards:MRKS"],
                    "apf_decoded_body_sizes": [row_["decoded_body_size"] for row_ in awards_apf],
                    "nfl_decoded_body_sizes_after_common_header": [
                        row_["decoded_body_size_after_common_header"] for row_ in awards_nfl
                    ],
                }
            )
        elif role == "director":
            row.update(
                {
                    "apf_resource_count": 1,
                    "nfl_resource_count": 1,
                    "direct_shared_name_type_count": 1,
                    "resource_order": ["director:DRCT"],
                    "apf_instruction_record_count": 96,
                    "nfl_instruction_record_count": 96,
                    "apf_fixed_record_count": 20,
                    "nfl_fixed_record_count": 20,
                    "ordered_structural_signature_match_count": 19,
                }
            )
        else:
            summary = archive_summaries[apf_outer_index]
            row.update(
                {
                    "apf_resource_count": summary["apf_resource_count"],
                    "nfl_resource_count": summary["nfl_resource_count"],
                    "direct_shared_name_type_count": summary["direct_shared_name_type_count"],
                }
            )
        cluster_rows.append(row)
    require([row["nfl_outer_index"] for row in cluster_rows] == [17, 18, 19, 20, 21],
            "NFL wrapup cluster is no longer consecutive")

    pe = pe_path.read_bytes()
    nfl_xbe_bytes = nfl_xbe.read_bytes()
    nfl_awards_literal_count = count_needle(
        nfl_xbe_bytes, "awards.iff".encode("utf-16le")
    )
    require(nfl_awards_literal_count == 1, "NFL XBE awards.iff literal changed")
    nfl_fr_literal_offsets = find_all(nfl_xbe_bytes, "fr.iff".encode("utf-16le"))
    require(nfl_fr_literal_offsets == [0x00B0B6F8], "NFL XBE fr.iff literal changed")
    fr_context_witnesses = [
        "fr%s.iff", "FRANCHISE2", "coach_desk", "FRANCHISE1", "FRMINI", "mini.iff"
    ]
    fr_context = nfl_xbe_bytes[
        nfl_fr_literal_offsets[0] - 0x100 : nfl_fr_literal_offsets[0] + 0x100
    ]
    require(
        all(witness.encode("utf-16le") in fr_context for witness in fr_context_witnesses),
        "NFL fr.iff literal context changed",
    )
    require(
        nfl_archive.entries[23].name_id == crc_utf16le_upper("FR.IFF") == 0xC59D46A8,
        "NFL fr.iff outer identity changed",
    )
    require(
        apf_archive.entries[810].name_id == crc_ascii_upper("FRANCHISE.IFF") == 0x852E246F,
        "APF franchise.iff outer identity changed",
    )
    awards_literal_scan = {
        "awards_outer_id_be_count": count_needle(pe, struct.pack(">I", 0x38FC8DBF)),
        "awards_outer_id_le_count": count_needle(pe, struct.pack("<I", 0x38FC8DBF)),
        "awards_ascii_lower_count": count_needle(pe, b"awards.iff"),
        "awards_ascii_upper_count": count_needle(pe, b"AWARDS.IFF"),
        "awards_utf16be_lower_count": count_needle(pe, "awards.iff".encode("utf-16be")),
        "awards_utf16le_lower_count": count_needle(pe, "awards.iff".encode("utf-16le")),
    }
    require(not any(awards_literal_scan.values()), "APF PE gained a direct awards literal")

    layout_inventory = json.loads(
        (root / "reports/assets/cross_title_layout_inventory.json").read_text()
    )
    playoff_layout = [
        row for row in layout_inventory["layouts"]
        if row["platform"] == "apf2k8" and row["outer_index"] == 988
        and row["inner_index"] == 24 and row["layout_name"] == "playoff_setup"
    ]
    require(len(playoff_layout) == 1, "playoff_setup layout identity changed")
    playoff_records = [
        row for row in layout_inventory["records"]
        if row["platform"] == "apf2k8" and row["outer_index"] == 988
        and row["inner_index"] == 24
    ]
    playoff_names = Counter(row["primary_name"] for row in playoff_records)
    require(playoff_names == Counter({"tourney_game": 8, "tourney_selector_lg": 8,
                                      "tourney_selector_sm": 16}),
            "playoff_setup record-name distribution changed")

    table_words = list(struct.unpack_from(">12I", pe, 0x000FABB0))
    expected_table = [
        zlib.crc32(b"LAYT") & 0xFFFFFFFF,
        zlib.crc32(b"tourney_tree_64") & 0xFFFFFFFF,
        zlib.crc32(b"tourney_tree_32") & 0xFFFFFFFF,
        zlib.crc32(b"tourney_tree_16") & 0xFFFFFFFF,
        zlib.crc32(b"tourney_tree_8") & 0xFFFFFFFF,
        zlib.crc32(b"tourney_tree_4") & 0xFFFFFFFF,
        zlib.crc32(b"playoff_setup") & 0xFFFFFFFF,
        0x43, 0x1F, 0x0F, 0x07, 0x03,
    ]
    require(table_words == expected_table, "compiled tournament hash table changed")

    candidates_path = root / "reports/manifests/apf_inner_candidates.tsv"
    with candidates_path.open(newline="", encoding="utf-8") as stream:
        candidates = list(csv.DictReader(stream, delimiter="\t"))
    online_names = {
        (row["inner_name"], row["type_name"], int(row["inner_index"]))
        for row in candidates if int(row["outer_table_index"]) == 899
    }
    expected_online = {
        ("tourney_tree_64", "LAYT", 69), ("tourney_tree_32", "LAYT", 25),
        ("tourney_tree_16", "LAYT", 29), ("tourney_tree_8", "LAYT", 89),
        ("tourney_tree_4", "LAYT", 83), ("tourney_game", "SCNE", 76),
        ("tourney_selector_lg", "SCNE", 65), ("tourney_selector_sm", "SCNE", 49),
        ("live_draft", "LAYT", 12), ("live_draft", "SCNE", 13),
    }
    require(expected_online <= online_names, "online tournament resource set changed")

    trace = trace_path.read_text(encoding="utf-8")
    required_trace = [
        "APF_CUT_CONTENT_FOLLOWUP_TRACE_V1",
        "READ_ONLY true",
        "TARGET 0x820FABB0 section=.rdata owner=none refs=0x84A719B0(none,READ)",
        "materializations=0x84A7197C->0x84A71988(lis/addi,none)",
        "0x84A719A4 raw=0x7CC7402E instruction=lwzx r6,r7,r8",
        "0x84A719B0 raw=0x80EB0000 instruction=lwz r7,0x0(r11)",
        "0x84A719B8 raw=0x480A49E1 instruction=bl 0x84b16398",
        "TARGET 0x84614D6C section=.string_ owner=none refs=0x84A71A4C(none,PARAM)",
        "0x84A71A74 raw=0x4BC7C155 instruction=bl 0x846edbc8",
        "TARGET 0x8451618C section=.string_ owner=none refs= fullwords=0x8200FB40",
        "TARGET 0x845161A4 section=.string_ owner=none refs= fullwords=0x8200FB44",
        "TARGET 0x845161D0 section=.string_ owner=none refs= fullwords=0x8200FB6C",
    ]
    for marker in required_trace:
        require(marker in trace, f"Ghidra trace lacks {marker!r}")
    require(read_utf16be_at(pe, 0x8451618C) == "Live Draft", "Live Draft string changed")
    require(read_utf16be_at(pe, 0x845161A4) == "OnlineLiveDraft_Menu",
            "OnlineLiveDraft_Menu string changed")
    require(read_utf16be_at(pe, 0x845161D0) == "live_draft", "live_draft string changed")

    total_drafta_duration = sum(
        float(row["duration_seconds_candidate"]) for row in drafta_decode
    )
    document = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_and_asset_analysis": True,
            "launches_game_or_emulator": False,
            "executes_translated_guest_code": False,
            "writes_game_images": False,
            "playable_hidden_franchise_proved": False,
        },
        "sources": {
            "apf_xex": source(apf_xex),
            "apf_reconstructed_pe": source_labeled(pe_path, "apf2k8_default.pe"),
            "apf_index": source(apf_index),
            "nfl_xbe": source(nfl_xbe),
            "nfl_index": source(nfl_index),
            "ghidra_trace": source_labeled(
                trace_path,
                "reports/cut_content/apf_nfl_lineage/wrapup_followup_ghidra/trace.txt",
            ),
            "prior_lineage": source(root / "reports/cut_content/apf_nfl_lineage/lineage.json"),
            "director_inventory": source(root / "reports/assets/cross_title_director_inventory.json"),
            "layout_inventory": source(root / "reports/assets/cross_title_layout_inventory.json"),
        },
        "wrapup_cluster": {
            "nfl_outer_indices_are_consecutive_17_through_21": True,
            "all_five_have_exact_cross_platform_filename_hash_pairs": True,
            "packages": cluster_rows,
            "awards_package": {
                "new_filename_resolution": "awards.iff",
                "apf_outer_index": 349,
                "nfl_outer_index": 17,
                "resource_order_exact": True,
                "nfl_xbe_utf16le_filename_literal_count": nfl_awards_literal_count,
                "franchise_show_marker_name_witnesses": show_marker_witnesses,
                "marker_to_awards_action_semantics_proved": False,
                "resources": [
                    {
                        "name": apf_row["name"],
                        "type": apf_row["kind"],
                        "apf_inner_index": apf_row["inner_index"],
                        "nfl_chunk_index": nfl_row["inner_index"],
                        "apf_decoded_body_size": apf_row["decoded_body_size"],
                        "nfl_decoded_body_size_after_common_header":
                            nfl_row["decoded_body_size_after_common_header"],
                        "decoded_bodies_byte_identical":
                            apf_row["decoded_body_sha256"] == nfl_row["decoded_body_sha256"],
                    }
                    for apf_row, nfl_row in zip(awards_apf, awards_nfl)
                ],
                "apf_pe_direct_literal_scan": awards_literal_scan,
                "runtime_owner_proved": False,
            },
            "safe_conclusion": (
                "Every member of NFL 2K5's consecutive five-package SportsCenter wrapup "
                "cluster has an identifiable converted APF descendant, including the newly "
                "resolved awards.iff package. This is package/script lineage, not proof that "
                "retail APF reaches or completes the show."
            ),
        },
        "franchise_filename_resolution": {
            "previously_unresolved_nfl_outer_index": 23,
            "nfl_filename": "fr.iff",
            "nfl_outer_id": "0xc59d46a8",
            "nfl_filename_hash_rule": "CRC32(uppercase UTF-16LE filename)",
            "nfl_xbe_utf16le_literal_count": len(nfl_fr_literal_offsets),
            "nfl_xbe_literal_file_offset": f"0x{nfl_fr_literal_offsets[0]:08x}",
            "literal_context_witnesses": fr_context_witnesses,
            "apf_descendant_outer_index": 810,
            "apf_descendant_filename": "franchise.iff",
            "apf_descendant_outer_id": "0x852e246f",
            "apf_filename_hash_rule": "CRC32(uppercase ASCII filename)",
            "pair_basis": (
                "exact NFL filename literal/hash plus the previously proved co-located "
                "77-resource, 21-layout, and complete 1492-record string lineage"
            ),
            "safe_conclusion": (
                "NFL 2K5's previously unnamed main franchise package is fr.iff; APF's "
                "expanded descendant was renamed franchise.iff."
            ),
        },
        "frontend_lineage": {
            "filename": "frontend.iff",
            "apf_outer_index": 988,
            "apf_outer_id": f"0x{apf_archive.entries[988].name_id:08x}",
            "nfl_outer_index": 9,
            "nfl_outer_id": f"0x{nfl_archive.entries[9].name_id:08x}",
            "apf_comparable_resource_count": len(frontend_apf),
            "nfl_comparable_resource_count": len(frontend_nfl),
            "shared_exact_name_type_count": len(shared_frontend),
            "apf_only_name_type": [f"{name}:{kind}" for name, kind in sorted(apf_keys - nfl_keys)],
            "nfl_only_name_type": [f"{name}:{kind}" for name, kind in sorted(nfl_keys - apf_keys)],
            "audio_name_count": len(audio_lineage),
            "probable_common_source_transcoded_audio_count": len(common_audio),
            "audio_comparisons": audio_lineage,
            "front_office_cues": front_office,
            "safe_conclusion": (
                "APF's main frontend archive retains both NFL 2K5 Front Office transition cues "
                "as common-source XMA transcodes. Audio presence does not establish a reachable "
                "Front Office menu, whose scene/layout were removed from APF franchise.iff."
            ),
        },
        "drafta_bank_lineage": {
            "apf": {
                "outer_index": 1310,
                "outer_name": "global.iff",
                "inner_index": 51,
                "name": "drafta",
                "type": "AUSB",
                "external_filename": apf_drafta["ausb"]["external_filename"],
                "entry_count": apf_drafta["ausb"]["entry_count"],
                "sample_rate": apf_drafta["ausb"]["sample_rate"],
                "channels": apf_drafta["ausb"]["derived_channel_count"],
                "external_outer_index": apf_drafta["linked_external_outer_entry"]["table_index"],
                "external_encoded_size": apf_drafta["linked_external_outer_entry"]["size"],
                "total_duration_seconds_candidate": total_drafta_duration,
                "substreams": drafta_decode,
            },
            "nfl": nfl_drafta,
            "same_name_type_external_filename_and_four_track_shape": True,
            "decoded_common_source_audio_proved": False,
            "safe_conclusion": (
                "APF and NFL 2K5 each retain a global drafta AUSB descriptor pointing to "
                "drafta.bin with four substreams. APF's four XMA tracks decode; NFL's external "
                "bank codec has not been semantically compared, so shared source audio is unproved."
            ),
        },
        "tournament_false_friend": {
            "playoff_setup": {
                "apf_outer_index": 988,
                "inner_index": 24,
                "record_count": 32,
                "record_name_counts": dict(sorted(playoff_names.items())),
            },
            "compiled_hash_table": {
                "address": "0x820FABB0",
                "words": [f"0x{word:08x}" for word in table_words],
                "decoded_names": [
                    "LAYT", "tourney_tree_64", "tourney_tree_32", "tourney_tree_16",
                    "tourney_tree_8", "tourney_tree_4", "playoff_setup",
                ],
                "materialization": "0x84A7197C->0x84A71988",
                "selected_hash_load": "0x84A719A4",
                "type_hash_load": "0x84A719B0",
                "resource_call": "0x84A719B8 -> 0x84B16398",
                "tourney_game_format_lookup": "0x84A71A4C / 0x84A71A74",
            },
            "online_iff_outer_index": 899,
            "online_resource_witnesses": [
                f"{name}:{kind}:{index}" for name, kind, index in sorted(expected_online)
            ],
            "online_live_draft_static_strings": {
                "0x8451618C": "Live Draft",
                "0x845161A4": "OnlineLiveDraft_Menu",
                "0x845161D0": "live_draft",
            },
            "classification": (
                "compiled APF tournament/online bracket infrastructure; not evidence for an "
                "offline franchise playoff mode"
            ),
        },
        "video_claims": [
            {
                "grade": "A_PROVEN",
                "claim": "NFL 2K5 outer 23's previously unknown filename is fr.iff",
                "safe_wording": (
                    "The NFL XBE names the main package fr.iff beside FRANCHISE1 and "
                    "coach_desk; its exact filename hash is outer 23, whose expanded APF "
                    "descendant is renamed franchise.iff."
                ),
                "boundary": "filename and package lineage; it does not add APF retail reachability",
            },
            {
                "grade": "A_PROVEN",
                "claim": "APF preserves all five members of NFL 2K5's SportsCenter wrapup package cluster",
                "safe_wording": (
                    "All five consecutive NFL 2K5 wrapup packages—Awards, the main show, its "
                    "director graph, intro and outro—have identifiable converted descendants in "
                    "retail APF. The newly resolved Awards package contains Primetime Players and "
                    "Season Awards."
                ),
                "boundary": "five-package lineage closure, not a reachable or complete hidden show",
            },
            {
                "grade": "A_PROVEN",
                "claim": "APF ships NFL 2K5's two Front Office menu cues as common-source transcodes",
                "safe_wording": (
                    "The two Front Office transition sounds in APF's frontend match NFL 2K5 in "
                    "layout, rate, duration, RMS and spectral fingerprint after ADPCM-to-XMA conversion."
                ),
                "boundary": "sound-cue survival does not prove the removed Front Office scene/menu is reachable",
            },
            {
                "grade": "B_STRUCTURAL_LINEAGE",
                "claim": "APF retains a four-track drafta external audio bank",
                "safe_wording": (
                    "Both games carry a global four-entry drafta bank pointing to drafta.bin; "
                    "APF's four tracks decode to roughly 295 seconds total."
                ),
                "boundary": "NFL external-bank audio has not been decoded and common-source content is unproved",
            },
            {
                "grade": "BOUNDARY_PROVEN",
                "claim": "playoff_setup is tournament infrastructure, not hidden-franchise proof",
                "safe_wording": (
                    "Compiled APF code selects 4/8/16/32/64 tournament-tree layouts and formats "
                    "tourney_game rows; the tree assets and Live Draft live in online.iff."
                ),
                "boundary": "do not use playoff_setup or live_draft as evidence of an offline franchise mode",
            },
        ],
        "portme": [
            "PORTME: recover a live retail owner for awards.iff and the Wrapup route root before claiming runtime reachability.",
            "PORTME: decode the NFL 2K5 drafta.bin bank codec and compare all four tracks before claiming common-source audio.",
            "PORTME: recover DRCT instruction opcodes before mapping individual wrapup script actions to awards/show assets.",
            "PORTME: distinguish online Live Draft service behavior from reusable offline draft logic before porting a mode.",
        ],
    }
    return document


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--ghidra-trace", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--claims-tsv-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        document = build(args)
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        write_tsv(
            args.claims_tsv_out,
            document["video_claims"],
            ["grade", "claim", "safe_wording", "boundary"],
        )
        print(
            "APF_NFL_WRAPUP_FOLLOWUP_PASS "
            f"cluster={len(document['wrapup_cluster']['packages'])} "
            f"fr_name={document['franchise_filename_resolution']['nfl_filename']} "
            f"frontend_shared={document['frontend_lineage']['shared_exact_name_type_count']} "
            f"frontend_audio={document['frontend_lineage']['probable_common_source_transcoded_audio_count']} "
            f"drafta_tracks={document['drafta_bank_lineage']['apf']['entry_count']} "
            "hidden_franchise=false"
        )
        return 0
    except (
        FollowupError,
        apf_audio.AudioError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
