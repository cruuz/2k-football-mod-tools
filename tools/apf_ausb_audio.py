#!/usr/bin/env python3
"""Export one APF AUSB external-bank substream as RIFF XMA1 and verified WAV.

// PORTME: AUSB's boundary float is decoder-correlated duration metadata, but
// exact loop ownership and the remaining header words still require loader
// tracing before reversible bank import is safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zlib

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_audio
import apf_inner
import apf_outer


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _export_substream_impl(
    index_path: Path,
    table_index: int,
    inner_index: int,
    substream_index: int,
    output_xma: Path,
    output_wav: Path | None,
    max_decompressed: int,
    *,
    cancel_requested: apf_audio.CancelRequested | None = None,
) -> dict[str, object]:
    apf_audio.check_cancel_requested(cancel_requested)
    archive = apf_outer.parse_archive(index_path)
    apf_audio.check_cancel_requested(cancel_requested)
    outer_entries = {entry.table_index: entry for entry in archive.entries}
    if table_index not in outer_entries:
        raise apf_audio.AudioError(f"no outer table index {table_index}")

    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, outer_entries[table_index])
        try:
            item = record.files[inner_index]
        except IndexError as exc:
            raise apf_audio.AudioError(
                f"entry {table_index} has no inner file {inner_index}"
            ) from exc
        if item.type_name != apf_audio.AUSB_TYPE or len(item.parts) != 1:
            raise apf_audio.AudioError("selected file is not a one-part AUSB descriptor")
        cache: dict[int, bytes] = {}
        ausb_data = apf_audio._read_part(
            reader, record, item.parts[0], cache, max_decompressed
        )
        ausb = apf_audio.parse_ausb(ausb_data)
        try:
            boundary = ausb["entries"][substream_index]
        except IndexError as exc:
            raise apf_audio.AudioError(
                f"AUSB has no substream {substream_index}"
            ) from exc
        next_boundary = (
            ausb["entries"][substream_index + 1]
            if substream_index + 1 < len(ausb["entries"])
            else ausb["terminal_boundary"]
        )
        start = int(boundary["packet_offset"])
        end = int(next_boundary["packet_offset"])
        if not 0 <= start < end or start % 2048 or end % 2048:
            raise apf_audio.AudioError("selected AUSB boundaries are invalid")

        external_id = zlib.crc32(
            str(ausb["external_filename"]).upper().encode("ascii")
        ) & 0xFFFFFFFF
        matches = [entry for entry in archive.entries if entry.name_id == external_id]
        if len(matches) != 1:
            raise apf_audio.AudioError(
                f"external filename resolves to {len(matches)} outer entries"
            )
        external = matches[0]
        if end > external.size:
            raise apf_audio.AudioError("selected AUSB range exceeds external .bin")
        payload = reader.read(external, start, end - start)
    apf_audio.check_cancel_requested(cancel_requested)

    channels = ausb["derived_channel_count"]
    if channels is None:
        raise apf_audio.AudioError(
            f"unknown AUSB layout code {ausb['channel_layout_code']}"
        )
    duration = float(next_boundary["value_float"])
    declared_samples = round(duration * int(ausb["sample_rate"]))
    riff = apf_audio.make_xma1_riff(
        payload, int(channels), int(ausb["sample_rate"])
    )
    output_xma.parent.mkdir(parents=True, exist_ok=True)
    output_xma.write_bytes(riff)
    apf_audio.check_cancel_requested(cancel_requested)

    result: dict[str, object] = {
        "schema": "apf_ausb_substream_export/v1",
        "outer_table_index": table_index,
        "inner_file_index": inner_index,
        "name": item.name,
        "substream_index": substream_index,
        "ausb": {
            "sha256": ausb["sha256"],
            "external_filename": ausb["external_filename"],
            "entry_count": ausb["entry_count"],
            "sample_rate": ausb["sample_rate"],
            "channel_layout_code": ausb["channel_layout_code"],
            "derived_channel_count": channels,
            "duration_seconds_candidate": duration,
            "declared_sample_count_candidate": declared_samples,
        },
        "external_outer_entry": {
            "table_index": external.table_index,
            "name_id": f"0x{external.name_id:08x}",
            "size": external.size,
            "range_offset": start,
            "range_length": len(payload),
            "packet_count": len(payload) // 2048,
            "payload_sha256": sha256(payload),
        },
        "first_packet": apf_audio.parse_packet_header(payload[:4]),
        "xma": {
            "path": str(output_xma),
            "size": len(riff),
            "sha256": sha256(riff),
            "status": "wrapped_unverified",
        },
        "wav": None,
        "portme": (
            "prove exact AUSB duration/loop semantics before reversible import; "
            "the WAV is a one-way modding export with source sidecar"
        ),
    }
    if output_wav is None:
        return result

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        raise apf_audio.AudioError("WAV verification requires ffmpeg and ffprobe")
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    decode_command = [
        ffmpeg,
        "-v",
        "error",
        "-xerror",
        "-y",
        "-i",
        str(output_xma),
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-af",
        f"atrim=end_sample={declared_samples}",
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    try:
        if cancel_requested is None:
            completed = subprocess.run(
                decode_command,
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            completed = apf_audio.run_cancellable_subprocess(
                decode_command,
                cancel_requested=cancel_requested,
                text=True,
            )
    except apf_audio.AudioError:
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

    layout = apf_audio.parse_pcm_wav(output_wav)
    delta = declared_samples - layout["sample_count_per_channel"]
    layout_ok = (
        layout["channels"] == channels
        and layout["sample_rate"] == ausb["sample_rate"]
        and layout["bits_per_sample"] == 16
        and 0 <= delta < 128
    )
    if not layout_ok:
        result["xma"]["status"] = "decode_incomplete"
        result["wav"] = {
            "status": "failed_sample_validation",
            "layout": layout,
            "declared_minus_decoded_samples": delta,
        }
        output_wav.unlink()
        result["wav"]["partial_output_removed"] = True
        return result

    status = (
        "decoder_verified_exact_candidate_samples"
        if delta == 0
        else "decoder_verified_with_candidate_tail_gap"
    )
    probe_command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,channels,sample_rate,duration:format=duration,size",
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
                check=True,
            )
        else:
            probe = apf_audio.run_cancellable_subprocess(
                probe_command,
                cancel_requested=cancel_requested,
                text=True,
            )
            if probe.returncode != 0:
                raise apf_audio.AudioError(
                    f"ffprobe rejected decoded WAV: {probe.stderr.strip()}"
                )
    except apf_audio.AudioError:
        output_wav.unlink(missing_ok=True)
        raise
    result["xma"]["status"] = status
    result["wav"] = {
        "status": status,
        "path": str(output_wav),
        "size": output_wav.stat().st_size,
        "sha256": hashlib.sha256(output_wav.read_bytes()).hexdigest(),
        "layout": layout,
        "declared_minus_decoded_samples": delta,
        "probe": json.loads(probe.stdout),
    }
    try:
        apf_audio.check_cancel_requested(cancel_requested)
    except apf_audio.AudioError:
        output_wav.unlink(missing_ok=True)
        raise
    return result


def export_substream(
    index_path: Path,
    table_index: int,
    inner_index: int,
    substream_index: int,
    output_xma: Path,
    output_wav: Path | None,
    max_decompressed: int,
    *,
    cancel_requested: apf_audio.CancelRequested | None = None,
) -> dict[str, object]:
    """Export one AUSB row, staging cancellable work before publication."""

    if cancel_requested is None:
        return _export_substream_impl(
            index_path,
            table_index,
            inner_index,
            substream_index,
            output_xma,
            output_wav,
            max_decompressed,
        )

    apf_audio.check_cancel_requested(cancel_requested)
    with tempfile.TemporaryDirectory(prefix="apf-ausb-cancellable-export-") as name:
        temporary = Path(name)
        staged_xma = temporary / "selected.xma"
        staged_wav = temporary / "selected.wav" if output_wav is not None else None
        result = _export_substream_impl(
            index_path,
            table_index,
            inner_index,
            substream_index,
            staged_xma,
            staged_wav,
            max_decompressed,
            cancel_requested=cancel_requested,
        )
        apf_audio.check_cancel_requested(cancel_requested)
        apf_audio._publish_complete_file(staged_xma, output_xma)
        result["xma"]["path"] = str(output_xma)
        if output_wav is not None:
            wav_report = result.get("wav")
            if isinstance(wav_report, dict) and staged_wav is not None:
                if staged_wav.is_file() and "path" in wav_report:
                    apf_audio._publish_complete_file(staged_wav, output_wav)
                    wav_report["path"] = str(output_wav)
        return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("index", type=Path, help="path to APF first volume (0A)")
    value.add_argument("--entry", type=int, required=True, help="outer IFF table index")
    value.add_argument("--file", type=int, required=True, help="inner AUSB file index")
    value.add_argument("--substream", type=int, required=True)
    value.add_argument("--output-xma", type=Path, required=True)
    value.add_argument("--verify-wav", type=Path)
    value.add_argument("--report", type=Path, required=True)
    value.add_argument(
        "--max-decompressed",
        type=int,
        default=apf_inner.DEFAULT_MAX_DECOMPRESSED,
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = export_substream(
            args.index,
            args.entry,
            args.file,
            args.substream,
            args.output_xma,
            args.verify_wav,
            args.max_decompressed,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(
            f"APF AUSB export: entry={args.entry} file={args.file} "
            f"substream={args.substream} xma={result['xma']['status']} "
            f"wav={None if result['wav'] is None else result['wav']['status']}"
        )
        if args.verify_wav is not None:
            return 0 if str(result["xma"]["status"]).startswith("decoder_verified") else 1
        return 0
    except (apf_audio.AudioError, apf_inner.FormatError, apf_outer.FormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
