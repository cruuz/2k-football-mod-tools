#!/usr/bin/env python3
"""Independently verify a bounded NFL 2K5 WAV-to-AUDO XISO workflow.

This verifier does not import the writer.  It uses an independent XDVDFS
parser, independently decodes Xbox IMA ADPCM, scans both complete images, and
checks that only the fixed ``menu-back_01`` payload differs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
import wave

import nfl_team_identity_xiso_verify as base


SCHEMA = "nfl2k5_audo_wav_xiso_workflow/v1"
ARTIFACT_SCHEMA = "nfl2k5_menu_back_audio_verification/v1"
PACK_PATH = "vc_53450030/0"
PACK_SECTOR = 796_479
PACK_SIZE = 193_710_080
PACK_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
OUTER_PACK_OFFSET = 851_968
CHUNK_OFFSET = 768_656
HEADER_SIZE = 32
SYSTEM_SIZE = 128
PAYLOAD_SIZE = 3_204
TAIL_SIZE = 12
WRAPPER_SIZE = 3_376
ABSOLUTE_WRAPPER_OFFSET = 1_632_809_616
ABSOLUTE_PAYLOAD_OFFSET = 1_632_809_776
WRAPPER_SHA256 = "cb8d0c27b7687f13374176a50cc0ca32c817d98ab64342a8a6d2193c28274ac3"
SYSTEM_SHA256 = "b3090973e21d57e5f433ff1c1b9a0288ff7295dc477b3537e80b772c2b36c875"
SOURCE_PAYLOAD_SHA256 = "50d8d4efc2b9f6d2405c005c27b544d8f9f8b57dc3e9449517f58d799985724b"
TAIL_SHA256 = "0206ad250f9b665e23746316a1391a776ec06398ddbcb3dd0aaa97d34012bb89"
SAMPLE_RATE = 16_000
FRAME_COUNT = 5_696
BLOCK_BYTES = 36
BLOCK_FRAMES = 64
CHUNK = 16 * 1024 * 1024

INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8)
STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)


class AudioVerifyError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioVerifyError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_report(path: Path) -> tuple[Path, dict]:
    resolved, raw, _ = base.read_regular_bytes(path, "workflow manifest")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AudioVerifyError("workflow manifest is invalid JSON") from exc
    require(raw == (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
            "workflow manifest is not canonical JSON")
    require(value.get("schema") == SCHEMA, "workflow manifest schema differs")
    return resolved, value


def read_wav(path: Path) -> tuple[Path, bytes, tuple[int, ...]]:
    resolved, raw, _ = base.read_regular_bytes(path, "input WAV")
    require(digest(raw), "input WAV hash failed")
    try:
        with wave.open(io.BytesIO(raw), "rb") as stream:
            require(stream.getcomptype() == "NONE" and stream.getsampwidth() == 2,
                    "input WAV is not PCM16")
            require(stream.getnchannels() == 1 and stream.getframerate() == SAMPLE_RATE,
                    "input WAV channel/rate differs")
            require(stream.getnframes() == FRAME_COUNT, "input WAV frame count differs")
            pcm = stream.readframes(FRAME_COUNT)
            require(len(pcm) == FRAME_COUNT * 2 and not stream.readframes(1),
                    "input WAV PCM extent differs")
    except (EOFError, wave.Error) as exc:
        raise AudioVerifyError("input WAV cannot be decoded") from exc
    return resolved, raw, struct.unpack(f"<{FRAME_COUNT}h", pcm)


def decode_payload(payload: bytes) -> tuple[int, ...]:
    require(len(payload) == PAYLOAD_SIZE and len(payload) % BLOCK_BYTES == 0,
            "output AUDO payload framing differs")
    result: list[int] = []
    for block in range(0, len(payload), BLOCK_BYTES):
        predictor, step_index = struct.unpack_from("<hH", payload, block)
        require(step_index <= 88, "output AUDO step index exceeds 88")
        channel: list[int] = [predictor]
        for byte in payload[block + 4:block + BLOCK_BYTES]:
            for code in (byte & 0x0F, byte >> 4):
                step = STEP_TABLE[step_index]
                change = step // 8
                if code & 1:
                    change += step // 4
                if code & 2:
                    change += step // 2
                if code & 4:
                    change += step
                predictor = predictor - change if code & 8 else predictor + change
                predictor = min(32_767, max(-32_768, predictor))
                step_index += INDEX_TABLE[code & 7]
                step_index = min(88, max(0, step_index))
                if len(channel) < BLOCK_FRAMES:
                    channel.append(predictor)
        require(len(channel) == BLOCK_FRAMES, "output AUDO block frame count differs")
        result.extend(channel)
    require(len(result) == FRAME_COUNT, "output AUDO decoded frame count differs")
    return tuple(result)


def quality(source: tuple[int, ...], decoded: tuple[int, ...]) -> dict:
    errors = [left - right for left, right in zip(source, decoded, strict=True)]
    error_square = sum(value * value for value in errors)
    signal_square = sum(value * value for value in source)
    snr = None
    if error_square and signal_square:
        snr = 10.0 * math.log10(signal_square / error_square)
    return {
        "frame_count": FRAME_COUNT,
        "squared_error_sum": error_square,
        "maximum_absolute_error": max(abs(value) for value in errors),
        "rmse": math.sqrt(error_square / FRAME_COUNT),
        "signal_rms": math.sqrt(signal_square / FRAME_COUNT),
        "snr_db": snr,
        "lossless_pcm": error_square == 0,
        "block_predictor_samples_exact": all(
            source[index] == decoded[index]
            for index in range(0, FRAME_COUNT, BLOCK_FRAMES)
        ),
    }


def offset_digest(values: list[int], fmt: str) -> str:
    return digest(b"".join(struct.pack(fmt, value) for value in values))


def runs(values: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for value in values:
        if not result or value != result[-1][1] + 1:
            result.append((value, value))
        else:
            result[-1] = (result[-1][0], value)
    return result


def scan_images(source_fd: int, output_fd: int, allowed: set[int]) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    changed: list[int] = []
    position = 0
    while position < base.IMAGE_SIZE:
        size = min(CHUNK, base.IMAGE_SIZE - position)
        before = base.pread_exact(source_fd, position, size)
        after = base.pread_exact(output_fd, position, size)
        source_hash.update(before)
        output_hash.update(after)
        if before != after:
            changed.extend(
                position + index for index, (left, right) in
                enumerate(zip(before, after, strict=True)) if left != right
            )
            require(len(changed) <= PAYLOAD_SIZE,
                    "more than one fixed AUDO payload changed")
        position += size
    require(set(changed) == allowed, "full-image changed-byte set differs")
    return source_hash.hexdigest(), output_hash.hexdigest(), changed


def verify(source_path: Path, output_path: Path, wav_path: Path, manifest_path: Path) -> dict:
    source, source_fd = base.open_regular(source_path)
    output, output_fd = base.open_regular(output_path)
    try:
        require(os.fstat(source_fd).st_size == os.fstat(output_fd).st_size == base.IMAGE_SIZE,
                "source/output image size differs")
        require((os.fstat(source_fd).st_dev, os.fstat(source_fd).st_ino) !=
                (os.fstat(output_fd).st_dev, os.fstat(output_fd).st_ino),
                "source/output inode aliases")
        report_path, report = canonical_report(manifest_path)
        wav, wav_raw, wav_samples = read_wav(wav_path)
        require(len({source, output, report_path, wav}) == 4, "workflow paths alias")
        require(Path(report["source"]["path"]).resolve() == source and
                Path(report["output"]["path"]).resolve() == output and
                Path(report["input_wav"]["path"]).resolve() == wav,
                "manifest path identity differs")
        require(report["input_wav"]["sha256"] == digest(wav_raw) and
                report["input_wav"]["pcm_sha256"] ==
                digest(struct.pack(f"<{FRAME_COUNT}h", *wav_samples)),
                "manifest WAV identity differs")

        source_entries, source_tree = base.parse_xdvdfs(source_fd)
        output_entries, output_tree = base.parse_xdvdfs(output_fd)
        require(source_entries == output_entries and source_tree == output_tree,
                "output XDVDFS tree or extents differ")
        pack = source_entries.get(PACK_PATH)
        require(pack is not None and pack.sector == PACK_SECTOR and pack.size == PACK_SIZE,
                "pack-0 extent differs")
        assert pack is not None
        require(base.hash_extent(source_fd, pack.offset, pack.size) == PACK_SHA256,
                "retail pack-0 hash differs")
        wrapper = pack.offset + OUTER_PACK_OFFSET + CHUNK_OFFSET
        payload_offset = wrapper + HEADER_SIZE + SYSTEM_SIZE
        require(wrapper == ABSOLUTE_WRAPPER_OFFSET and payload_offset == ABSOLUTE_PAYLOAD_OFFSET,
                "AUDO absolute-offset arithmetic differs")
        source_span = base.pread_exact(source_fd, wrapper, WRAPPER_SIZE)
        output_span = base.pread_exact(output_fd, wrapper, WRAPPER_SIZE)
        require(digest(source_span) == WRAPPER_SHA256, "retail AUDO wrapper hash differs")
        require(struct.unpack_from("<4s7I", source_span) ==
                (b"AUDO", 3344, SYSTEM_SIZE, PAYLOAD_SIZE, 0, 0, 0, 0),
                "retail AUDO wrapper fields differ")
        source_system = source_span[HEADER_SIZE:HEADER_SIZE + SYSTEM_SIZE]
        output_system = output_span[HEADER_SIZE:HEADER_SIZE + SYSTEM_SIZE]
        source_payload = source_span[HEADER_SIZE + SYSTEM_SIZE:-TAIL_SIZE]
        output_payload = output_span[HEADER_SIZE + SYSTEM_SIZE:-TAIL_SIZE]
        require(source_span[:HEADER_SIZE] == output_span[:HEADER_SIZE] and
                source_system == output_system and
                source_span[-TAIL_SIZE:] == output_span[-TAIL_SIZE:],
                "AUDO wrapper/system/tail bytes changed")
        require(digest(source_system) == SYSTEM_SHA256 and
                digest(source_payload) == SOURCE_PAYLOAD_SHA256 and
                digest(source_span[-TAIL_SIZE:]) == TAIL_SHA256,
                "retail AUDO component identity differs")
        require(output_payload != source_payload, "output AUDO payload is unchanged")

        relative = [
            index for index, (left, right) in
            enumerate(zip(source_payload, output_payload, strict=True)) if left != right
        ]
        allowed = {payload_offset + value for value in relative}
        source_hash, output_hash, changed = scan_images(source_fd, output_fd, allowed)
        require(source_hash == base.SOURCE_SHA256 and
                report["source"]["sha256_before"] == source_hash and
                report["source"]["sha256_after"] == source_hash and
                report["source"]["modified"] is False,
                "source XISO identity/manifest differs")
        require(output_hash == report["output"]["sha256"],
                "output XISO hash/manifest differs")

        decoded = decode_payload(output_payload)
        decoded_pcm = struct.pack(f"<{FRAME_COUNT}h", *decoded)
        measured = quality(wav_samples, decoded)
        require(report["target"]["replacement_payload_sha256"] == digest(output_payload) and
                report["codec"]["decoded_pcm_sha256"] == digest(decoded_pcm) and
                report["codec"]["quality"] == measured,
                "codec payload/quality manifest differs")
        patch = report["patch"]
        relative_run_list = runs(relative)
        require(patch["relative_changed_byte_count"] == len(relative) and
                patch["relative_changed_offsets_u32le_sha256"] ==
                offset_digest(relative, "<I") and
                patch["relative_changed_run_count"] == len(relative_run_list) and
                patch["relative_changed_runs_u32le_sha256"] == digest(b"".join(
                    struct.pack("<II", start, end) for start, end in relative_run_list)) and
                patch["absolute_changed_byte_count"] == len(changed) and
                patch["absolute_changed_offsets_u64le_sha256"] ==
                offset_digest(changed, "<Q") and
                patch["all_other_image_bytes_identical"] is True,
                "changed-byte ledger differs")
        claims = report["claims"]
        require(claims == {
            "fixed_size_standalone_audo_wav_import_proved": True,
            "generic_nfl_audo_import_proved": False,
            "nfl_audobank_import_proved": False,
            "nfl_music_or_commentary_import_proved": False,
            "apf_xma_import_proved": False,
            "runtime_visibility_proved": False,
            "emulator_started": False,
            "title_executed": False,
            "retail_original_modified": False,
        }, "workflow claims differ")
        require(base.hash_extent(output_fd, output_entries["default.xbe"].offset,
                                 output_entries["default.xbe"].size) == base.XBE_SHA256,
                "output default.xbe changed")
        require(source.stat().st_ino == os.fstat(source_fd).st_ino and
                output.stat().st_ino == os.fstat(output_fd).st_ino,
                "source/output pathname changed during verification")
        return {
            "output_sha256": output_hash,
            "changed_bytes": len(changed),
            "replacement_payload_sha256": digest(output_payload),
            "decoded_pcm_sha256": digest(decoded_pcm),
            "rmse": measured["rmse"],
        }
    finally:
        os.close(output_fd)
        os.close(source_fd)


def write_artifact_dir(path: Path, result: dict) -> Path:
    """Exclusively create a metadata-only verification receipt directory."""

    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise AudioVerifyError("verification artifact parent does not exist") from exc
    require(
        stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
        "verification artifact parent must be a non-symlink directory",
    )
    require(
        not os.path.lexists(requested),
        "verification artifact directory must be absent",
    )
    directory_identity: tuple[int, int] | None = None
    report_identity: tuple[int, int] | None = None
    report_path = requested / "verification.json"
    descriptor: int | None = None
    try:
        os.mkdir(requested, 0o755)
        directory = requested.lstat()
        require(
            stat.S_ISDIR(directory.st_mode) and not stat.S_ISLNK(directory.st_mode),
            "verification artifact path is not a directory",
        )
        directory_identity = (directory.st_dev, directory.st_ino)
        # ``O_BINARY`` is what makes the byte-for-byte post-write check below
        # mean the same thing on every OS.  A descriptor opened without it is a
        # *text* descriptor on Windows, where the CRT rewrites each ``\n`` this
        # canonical JSON payload contains as ``\r\n`` on the way to disk while
        # still reporting the untranslated count back from ``os.write``.  The
        # receipt on disk would then be longer than the payload the verifier
        # serialized -- the exact "verification receipt changed during creation"
        # failure -- and a reader would get bytes we never produced.  The
        # constant does not exist on POSIX, so ``getattr`` contributes 0 there
        # and the flags are unchanged.
        descriptor = os.open(
            report_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0),
            0o644,
        )
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), "verification receipt is not regular")
        report_identity = (opened.st_dev, opened.st_ino)
        report = {
            "result": {
                **result,
                "all_other_image_bytes_identical": True,
                "independent_verifier": True,
                "runtime_visibility_proved": False,
                "source_unchanged": True,
            },
            "schema": ARTIFACT_SCHEMA,
            "target": {
                "chunk_index": 101,
                "name": "menu-back_01",
                "outer_index": 3,
            },
        }
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            require(written > 0, "short write while creating verification receipt")
            cursor += written
        os.fsync(descriptor)
        current_directory = requested.lstat()
        current_report = report_path.lstat()
        require(
            stat.S_ISDIR(current_directory.st_mode)
            and not stat.S_ISLNK(current_directory.st_mode)
            and (current_directory.st_dev, current_directory.st_ino) == directory_identity,
            "verification artifact directory changed during creation",
        )
        require(
            stat.S_ISREG(current_report.st_mode)
            and not stat.S_ISLNK(current_report.st_mode)
            and (current_report.st_dev, current_report.st_ino, current_report.st_size)
            == (report_identity[0], report_identity[1], len(payload)),
            "verification receipt changed during creation",
        )
        return report_path
    except FileExistsError as exc:
        raise AudioVerifyError("verification artifact directory already exists") from exc
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if report_identity is not None:
            try:
                current = report_path.lstat()
                if (
                    stat.S_ISREG(current.st_mode)
                    and not stat.S_ISLNK(current.st_mode)
                    and (current.st_dev, current.st_ino) == report_identity
                ):
                    report_path.unlink()
            except FileNotFoundError:
                pass
        if directory_identity is not None:
            try:
                current = requested.lstat()
                if (
                    stat.S_ISDIR(current.st_mode)
                    and not stat.S_ISLNK(current.st_mode)
                    and (current.st_dev, current.st_ino) == directory_identity
                ):
                    requested.rmdir()
            except (FileNotFoundError, OSError):
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--input-wav", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.source_xiso, args.output_xiso, args.input_wav, args.manifest)
    except (OSError, AudioVerifyError, base.VerifyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report_path = None
    if args.artifact_dir is not None:
        try:
            report_path = write_artifact_dir(args.artifact_dir, result)
        except (OSError, AudioVerifyError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    print(
        "NFL2K5_AUDO_WAV_XISO_VERIFY_PASS "
        f"changed_bytes={result['changed_bytes']} "
        f"payload_sha256={result['replacement_payload_sha256']} "
        f"runtime=false artifact={report_path if report_path is not None else 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
