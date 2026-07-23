#!/usr/bin/env python3
"""Build a conservative NFL 2K5/APF 2K8 retail-audio modding matrix.

The report consumes SHA-pinned inventories and reads only the 17 small NFL
AUSB descriptors needed to classify streaming-bank boundaries.  It does not
decode or emit retail audio.  Its three report outputs are exclusively created
after rejecting source aliases, existing paths, symlinks, and unsafe parents.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
from typing import Any
import zlib

import nfl_scene_probe
import nfl_outer


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "vc_audio_modding_compatibility/v1"
MATRIX_SCHEMA = "vc_audio_modding_matrix/v1"
BANK_SCHEMA = "vc_audio_bank_inventory/v1"

SOURCES = {
    "nfl_audo": Path("reports/assets/nfl2k5_audo_wav_all.json"),
    "nfl_resources": Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    "nfl_pack0": Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
    "apf_audo": Path("reports/assets/apf_audio_inventory.json"),
    "apf_decode": Path("reports/assets/apf_audio_unique_decode.json"),
    "apf_ausb": Path("reports/assets/apf_ausb_inventory.json"),
    "presentation": Path("reports/assets/scorebug_presentation_audit.json"),
    "lineage": Path("reports/cut_content/apf_nfl_lineage/wrapup_followup.json"),
}

EXPECTED_SHA256 = {
    "reports/assets/nfl2k5_audo_wav_all.json":
        "08bc999ec2f2ca0af87933817e8e8fec912da2c2e43dbe1b3a4c70baee815b9f",
    "reports/assets/nfl2k5_resource_chunks_v2.json":
        "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac",
    "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0":
        "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
    "reports/assets/apf_audio_inventory.json":
        "510b110389a5415d3f91bfab41ec671633af30ca190ae03e653e8bdc4cd76c34",
    "reports/assets/apf_audio_unique_decode.json":
        "317ffad98d6748d95ee0e3a44fea12cc28b61678784464cf16b793e7d2b14573",
    "reports/assets/apf_ausb_inventory.json":
        "f4a893cb396d8a2bc075d1fc90d382209028670ca35231f78445db660562d64c",
    "reports/assets/scorebug_presentation_audit.json":
        "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1",
    "reports/cut_content/apf_nfl_lineage/wrapup_followup.json":
        "fa05d0ce2048d17512e65b6c13844576ae18813a9056f2a4f122acfd086e34ed",
}

APF_BANK_CLASSES = {
    "cwdloop": "diagnostic_or_ambient",
    "cwdsurr": "diagnostic_or_ambient",
    "halftimeaudio": "overlay_and_presentation",
    "overlayaudio": "overlay_and_presentation",
    "animationaudio": "overlay_and_presentation",
    "wrapupm": "music_or_show_presentation",
    "jukeboxmusic": "music",
    "jukebox22": "music",
    "femusic": "music",
    "loadm": "music",
    "drafta": "draft_presentation",
    "players": "commentary_or_speech",
    "lines": "commentary_or_speech",
    "teams": "commentary_or_speech",
    "pageneric": "stadium_pa",
    "pascore": "stadium_pa",
    "pachant": "stadium_pa",
    "coacha": "stadium_pa_or_coach",
    "pasfx": "stadium_pa_sfx",
}

NFL_BANK_CLASSES = {
    "lines": "commentary_or_speech",
    "players": "commentary_or_speech",
    "teams": "commentary_or_speech",
    "femusic": "music",
    "loadm": "music",
    "drafta": "draft_presentation",
    "coacha": "stadium_pa_or_coach",
    "cutsceneaudio": "cutscene_or_presentation",
    "cribmusic": "music",
    "crib22": "music_or_crib_audio",
    "cwdloop": "diagnostic_or_ambient",
    "wrapupm": "music_or_show_presentation",
    "cwdsurr": "diagnostic_or_ambient",
    "overlayaudio": "overlay_and_presentation",
    "halftimeaudio": "overlay_and_presentation",
    "animationaudio": "overlay_and_presentation",
}


class CompatibilityError(ValueError):
    pass


@dataclass(frozen=True)
class OutputTarget:
    requested: Path
    canonical: Path
    parent: Path
    parent_identity: tuple[int, int]


@dataclass(frozen=True)
class OwnedOutput:
    target: OutputTarget
    descriptor: int
    identity: tuple[int, int]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    full = ROOT / path
    before = full.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"source is not a non-symlink regular file: {path}")
    digest = sha256_file(full)
    require(EXPECTED_SHA256.get(path.as_posix()) == digest, f"source hash differs: {path}")
    after = full.stat(follow_symlinks=False)
    require((before.st_dev, before.st_ino, before.st_size) ==
            (after.st_dev, after.st_ino, after.st_size),
            f"source changed while hashing: {path}")
    return {"path": path.as_posix(), "size": before.st_size, "sha256": digest}


def load_json(key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = SOURCES[key]
    identity = pin(path)
    try:
        value = json.loads((ROOT / path).read_bytes())
    except json.JSONDecodeError as exc:
        raise CompatibilityError(f"invalid source JSON: {path}") from exc
    require(isinstance(value, dict), f"source JSON root differs: {path}")
    return value, identity


def plan_output(path: Path, suffix: str, label: str) -> OutputTarget:
    require(path.suffix == suffix, f"{label} output must use {suffix} suffix")
    try:
        supplied = path.lstat()
    except FileNotFoundError:
        supplied = None
    require(supplied is None, f"{label} output path must be absent and not a symlink")
    parent = path.parent
    try:
        parent_before = parent.lstat()
    except FileNotFoundError as exc:
        raise CompatibilityError(f"{label} output parent must already exist") from exc
    require(stat.S_ISDIR(parent_before.st_mode) and not stat.S_ISLNK(parent_before.st_mode),
            f"{label} output parent must be a non-symlink directory")
    canonical_parent = parent.resolve(strict=True)
    parent_after = parent.stat(follow_symlinks=False)
    require((parent_before.st_dev, parent_before.st_ino) ==
            (parent_after.st_dev, parent_after.st_ino),
            f"{label} output parent changed during preflight")
    return OutputTarget(
        requested=path,
        canonical=canonical_parent / path.name,
        parent=canonical_parent,
        parent_identity=(parent_after.st_dev, parent_after.st_ino),
    )


def plan_outputs(output: Path, matrix: Path, banks: Path) -> list[OutputTarget]:
    source_paths = {(ROOT / source).resolve(strict=True) for source in SOURCES.values()}
    requested_paths = [output.resolve(strict=False), matrix.resolve(strict=False),
                       banks.resolve(strict=False)]
    require(not any(path in source_paths for path in requested_paths),
            "an output aliases pinned input")
    targets = [
        plan_output(output, ".json", "JSON"),
        plan_output(matrix, ".tsv", "matrix"),
        plan_output(banks, ".tsv", "banks"),
    ]
    require(len({target.canonical for target in targets}) == len(targets),
            "output paths must be distinct")
    require(not any(target.canonical in source_paths for target in targets),
            "an output aliases pinned input")
    return targets


def reserve_outputs(targets: list[OutputTarget]) -> list[OwnedOutput]:
    owned: list[OwnedOutput] = []
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        for target in targets:
            parent = target.parent.stat(follow_symlinks=False)
            require(stat.S_ISDIR(parent.st_mode) and
                    (parent.st_dev, parent.st_ino) == target.parent_identity,
                    "output parent changed after preflight")
            descriptor = os.open(target.canonical, flags, 0o644)
            opened = os.fstat(descriptor)
            reserved = OwnedOutput(
                target=target,
                descriptor=descriptor,
                identity=(opened.st_dev, opened.st_ino),
            )
            owned.append(reserved)
            require(stat.S_ISREG(opened.st_mode), "reserved output is not regular")
        return owned
    except Exception:
        discard_outputs(owned)
        raise


def write_owned(output: OwnedOutput, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        written = os.write(output.descriptor, payload[position:])
        require(written > 0, "short report output write")
        position += written
    os.fsync(output.descriptor)
    opened = os.fstat(output.descriptor)
    current = output.target.canonical.stat(follow_symlinks=False)
    require((opened.st_dev, opened.st_ino) == output.identity ==
            (current.st_dev, current.st_ino) and current.st_size == len(payload),
            "owned output identity or size changed while writing")
    require(output.target.requested.resolve(strict=True) == output.target.canonical,
            "requested output path changed while writing")


def discard_outputs(outputs: list[OwnedOutput]) -> None:
    for output in reversed(outputs):
        try:
            os.close(output.descriptor)
        except OSError:
            pass
        try:
            current = output.target.canonical.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        if (current.st_dev, current.st_ino) == output.identity:
            output.target.canonical.unlink()


def close_outputs(outputs: list[OwnedOutput]) -> None:
    for output in outputs:
        os.close(output.descriptor)


def nfl_audo_summary(report: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary = report.get("summary", {})
    records = report.get("records", [])
    require(summary.get("record_count") == len(records) == 850, "NFL AUDO count differs")
    require(summary.get("status_counts") == {"parsed": 850}, "NFL AUDO parse status differs")
    require(summary.get("audo_channel_counts") == {"1": 806, "2": 44},
            "NFL AUDO channel counts differ")
    require(summary.get("audo_codec_word_counts") == {"0x00000011": 850},
            "NFL AUDO codec domain differs")
    require(all(record.get("compressed") is False for record in records),
            "NFL standalone AUDO compression status differs")
    require(all(record["semantic"]["codec_inference"] ==
                "Xbox IMA ADPCM (high confidence)" for record in records),
            "NFL AUDO codec confidence differs")
    groups = {
        "frontend_franchise_ui": {3, 9, 23},
        "field_ambient_player_state": {346, 347},
        "repeated_team_clap_cues": set(range(513, 1193)),
        "crib_minigame_trivia": {4248, 4249, 4250, 4264, 4266, 4271},
    }
    counts = {
        name: sum(record["outer_index"] in indices for record in records)
        for name, indices in groups.items()
    }
    require(counts == {
        "frontend_franchise_ui": 36,
        "field_ambient_player_state": 13,
        "repeated_team_clap_cues": 680,
        "crib_minigame_trivia": 121,
    }, "NFL AUDO package grouping differs")
    target = [record for record in records
              if record["outer_index"] == 3 and record["chunk_index"] == 101]
    require(len(target) == 1 and target[0]["semantic"]["name"] == "menu-back_01",
            "NFL bounded writer target differs")
    target_semantic = target[0]["semantic"]
    require(
        target[0]["stored_size"] == 3344 and target[0]["system_bytes"] == 128 and
        target[0]["video_bytes"] == 3204 and target_semantic["channels"] == 1 and
        target_semantic["sample_rate"] == 16000 and
        target_semantic["xbox_ima_block_count"] == 89,
        "NFL bounded writer target contract differs",
    )
    result = {
        "record_count": 850,
        "unique_name_count": summary["unique_name_count"],
        "codec": "Xbox IMA ADPCM",
        "uncompressed_wrapper_count": 850,
        "channel_distribution": summary["audo_channel_counts"],
        "sample_rate_distribution": summary["audo_sample_rate_counts"],
        "decoded_pcm_bytes": 34_922_624,
        "summed_duration_seconds": 957.13,
        "name_and_package_grouping": counts,
        "loop_gain_pan_priority_recovered": False,
        "generic_import_available": False,
    }
    bank_rows = [
        {
            "schema": BANK_SCHEMA,
            "title": "nfl2k5",
            "container": "AUDO standalone",
            "name": name,
            "external_filename": "",
            "role_class": name,
            "entry_count": count,
            "sample_rate": "mixed",
            "channel_field": "1/2 channels proved",
            "extract_status": "850/850 PCM16 WAV",
            "import_status": "only outer3/chunk101 bounded",
            "ownership_boundary": "package/name grouping; per-cue runtime owner not fully proved",
        }
        for name, count in counts.items()
    ]
    return result, bank_rows


def nfl_ausb_rows(resource_report: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inventory_pin = pin(SOURCES["nfl_pack0"])
    archive = nfl_outer.parse_archive(ROOT / SOURCES["nfl_pack0"])
    _, records = nfl_scene_probe.parse_inventory(ROOT / SOURCES["nfl_resources"])
    selected = [record for record in records if record.kind == "AUSB"]
    require(len(selected) == 17, "NFL AUSB descriptor count differs")
    rows: list[dict[str, Any]] = []
    external_seen: set[int] = set()
    for record in selected:
        entry = archive.entries[record.outer_index]
        span = nfl_scene_probe.read_entry_range(
            archive, entry, record.chunk_offset, 32 + record.stored_size)
        body, detail = nfl_scene_probe.decode_resource(span, record)
        name = nfl_scene_probe.named_inner(body, "AUSB")[0]
        external_filename = nfl_scene_probe.utf16z(body, 0x40, 0x80)[0]
        require(external_filename.casefold() == f"{name}.bin".casefold(),
                f"NFL AUSB filename/name differs: {name}")
        count, unknown, channel_word, rate, unit_word = struct.unpack_from("<5I", body, 0x80)
        require(count > 0 and rate == 22_050 and unit_word == 0x12000 and
                channel_word in {1, 2}, f"NFL AUSB fixed header differs: {name}")
        table_end = 0x98 + (count + 1) * 4
        require(table_end <= len(body), f"NFL AUSB boundary table exceeds body: {name}")
        boundaries = list(struct.unpack_from(f"<{count + 1}I", body, 0x98))
        require(boundaries[0] == 0 and boundaries == sorted(boundaries),
                f"NFL AUSB boundaries differ: {name}")
        external_id = zlib.crc32(external_filename.upper().encode("utf-16le")) & 0xFFFFFFFF
        matches = [candidate for candidate in archive.entries if candidate.name_id == external_id]
        require(len(matches) == 1 and boundaries[-1] == matches[0].size,
                f"NFL AUSB external bank identity differs: {name}")
        external_seen.add(matches[0].table_index)
        rows.append({
            "schema": BANK_SCHEMA,
            "title": "nfl2k5",
            "container": "AUSB -> external bank",
            "name": name,
            "external_filename": external_filename,
            "role_class": NFL_BANK_CLASSES[name],
            "entry_count": count,
            "sample_rate": rate,
            "channel_field": f"opaque_word={channel_word}",
            "extract_status": "descriptor/boundaries only; bank codec/directory unresolved",
            "import_status": "blocked",
            "ownership_boundary": "role class is filename-backed; exact cue routing remains unproved",
            "source": {
                "outer_index": record.outer_index,
                "chunk_index": record.chunk_index,
                "decoded_sha256": detail["decoded_sha256"],
                "external_outer_index": matches[0].table_index,
                "external_size": matches[0].size,
                "unknown_84": unknown,
                "unit_word_90": unit_word,
            },
        })
    rows.sort(key=lambda row: (row["name"], row["source"]["outer_index"]))
    require(set(NFL_BANK_CLASSES) == {row["name"] for row in rows},
            "NFL AUSB role-class domain differs")
    return {
        "descriptor_count": len(rows),
        "unique_external_entry_count": len(external_seen),
        "substream_count": sum(int(row["entry_count"]) for row in rows),
        "sample_rate_distribution": {"22050": len(rows)},
        "channel_word_distribution": {
            str(value): sum(row["channel_field"] == f"opaque_word={value}" for row in rows)
            for value in (1, 2)
        },
        "bank_codec_and_cue_directory_recovered": False,
        "source_pack": inventory_pin,
    }, rows


def apf_summaries(
    audo: dict[str, Any], decode: dict[str, Any], ausb: dict[str, Any],
    presentation: dict[str, Any], lineage: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    audo_summary = audo.get("summary", {})
    decode_summary = decode.get("summary", {})
    ausb_summary = ausb.get("summary", {})
    require(audo_summary.get("parsed_audo_count") == 2261 and
            audo_summary.get("failure_count") == 0 and
            audo_summary.get("total_packet_count") == 30_524,
            "APF AUDO inventory counts differ")
    require(audo_summary.get("packet_classification_distribution") == {"xma1": 2261},
            "APF AUDO packet classification differs")
    require(decode_summary.get("unique_payload_count") == 1268 and
            decode_summary.get("decoder_verified_unique_payload_count") == 1261 and
            decode_summary.get("decoder_verified_audo_record_count") == 2229 and
            decode_summary.get("not_decoder_verified_audo_record_count") == 32,
            "APF AUDO decoder result differs")
    require(ausb_summary.get("parsed_ausb_count") == 20 and
            ausb_summary.get("total_substream_count") == 45_514 and
            ausb_summary.get("unique_external_bin_count") == 19,
            "APF AUSB inventory counts differ")
    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for record in ausb.get("records", []):
        bank = record["ausb"]
        name = str(record["name"])
        require(name in APF_BANK_CLASSES, f"unclassified APF AUSB name: {name}")
        seen_names.add(name)
        rows.append({
            "schema": BANK_SCHEMA,
            "title": "apf2k8",
            "container": "AUSB -> external XMA1 bank",
            "name": name,
            "external_filename": bank["external_filename"],
            "role_class": APF_BANK_CLASSES[name],
            "entry_count": bank["entry_count"],
            "sample_rate": bank["sample_rate"],
            "channel_field": f"{bank['derived_channel_count']} channels (layout {bank['channel_layout_code']})",
            "extract_status": "packet boundaries proved; five halftime substreams decoder-verified",
            "import_status": "blocked: no XMA1 encoder/loop-duration repack proof",
            "ownership_boundary": "role class is filename-backed; exact cue routing remains incomplete",
            "source": {
                "outer_table_index": record["outer_table_index"],
                "inner_file_index": record["inner_file_index"],
                "linked_external_outer_index": record["linked_external_outer_entry"]["table_index"],
                "external_size": record["linked_external_outer_entry"]["size"],
            },
        })
    require(seen_names == set(APF_BANK_CLASSES), "APF AUSB role-class domain differs")
    rows.sort(key=lambda row: (row["name"], row["source"]["outer_table_index"]))

    overlay = presentation["apf2k8"]["replay_halftime_presentation"]["sfx_overlay"]
    require(len(overlay["audio"]) == 17 and
            overlay["outer_index"] == 1410,
            "APF owned overlay AUDO set differs")
    frontend = lineage["frontend_lineage"]
    require(frontend["audio_name_count"] == 23 and
            frontend["probable_common_source_transcoded_audio_count"] == 17,
            "cross-title frontend audio lineage differs")
    return ({
        "record_count": 2261,
        "codec": "XMA1",
        "packet_count": 30_524,
        "encoded_bytes": 62_513_152,
        "channel_distribution": audo_summary["derived_channel_count_distribution"],
        "sample_rate_distribution": audo_summary["sample_rate_distribution"],
        "unique_payload_count": 1268,
        "decoder_verified_unique_payload_count": 1261,
        "decoder_verified_record_count": 2229,
        "decoder_blocked_record_count": 32,
        "owned_overlay_sfx_count": 17,
        "owned_overlay_outer_index": 1410,
        "frontend_same_name_count": 23,
        "probable_common_source_frontend_transcodes": 17,
        "encoder_available": False,
        "archive_writeback_available": False,
    }, {
        "descriptor_count": 20,
        "unique_external_bank_count": 19,
        "substream_count": 45_514,
        "unique_external_encoded_bytes": 1_144_270_848,
        "sample_rate_distribution": ausb_summary["sample_rate_distribution"],
        "channel_layout_distribution": ausb_summary["channel_layout_code_distribution"],
        "duration_float_semantics": "decoder-correlated candidate, not complete loop/cue ownership",
        "encoder_available": False,
        "bank_repack_available": False,
    }, rows)


def matrix_rows() -> list[dict[str, str]]:
    values = [
        ("nfl_standalone_audo_extract", "NFL 2K5", "proved", "850/850 Xbox IMA AUDO resources decode to PCM16 WAV."),
        ("nfl_menu_back_fixed_slot_import", "NFL 2K5", "copy-only writer", "Strict mono 16 kHz PCM16 WAV with exactly 5,696 frames fits outer 3/chunk 101; runtime selection is unproved."),
        ("nfl_other_standalone_audo_import", "NFL 2K5", "blocked pending per-slot review", "All are uncompressed, but each allocation, metadata, duration, owner, and duplicate-name route must be pinned before exposure."),
        ("nfl_abnk_wbnk", "NFL 2K5", "blocked", "Bank directory, codec/sample references, cues, loops, DSP, gain, pan, and priority remain unresolved."),
        ("nfl_ausb_external_banks", "NFL 2K5", "descriptor-only", "17 descriptors and their external boundaries resolve; the external bank codec/directory is not a reversible import surface."),
        ("apf_standalone_audo_extract", "APF 2K8", "partial extract", "2,229/2,261 occurrences are decoder-verified; 32 occurrences across seven unique XMA1 payloads remain blocked."),
        ("apf_standalone_audo_import", "APF 2K8", "blocked", "No installed/open XMA1 encoder is validated and loop/valid-bit metadata plus IFF/H7A allocation must be rebuilt."),
        ("apf_ausb_external_banks", "APF 2K8", "indexed extract only", "45,514 packet-bounded substreams resolve; only five halftime samples have bounded decoder verification."),
        ("apf_ausb_import", "APF 2K8", "blocked", "Requires XMA1 encoding, packet sizing, duration/loop regeneration, boundary-table updates, and external-bank/archive repacking."),
        ("music_replacement", "both", "blocked", "Music lives primarily in streaming banks; neither title has a complete reversible bank writer."),
        ("commentary_speech_replacement", "both", "blocked", "Large lines/players/teams banks have unresolved cue identity/routing; APF additionally requires XMA1 encoding."),
        ("overlay_sfx_replacement", "APF 2K8", "extract-only", "Seventeen sfx_overlay AUDO cues and code owners are proved, but XMA1 import/repack is not."),
        ("loop_metadata", "both", "blocked", "Do not infer seamless loops from filenames; higher-level cue and loop ownership is incomplete."),
        ("flac_input", "both", "preprocess only", "FLAC is suitable as a lossless authoring archive but the bounded writer accepts canonical PCM16 WAV only."),
        ("runtime_visibility", "both", "not tested", "No emulator/game execution occurred in this audit; codec-valid writeback is not an audible-runtime claim."),
        ("public_distribution", "both", "user-media only", "Tools/reports may ship; extracted or converted retail audio must not."),
    ]
    return [
        {"schema": MATRIX_SCHEMA, "surface": surface, "title": title,
         "status": status, "boundary": boundary}
        for surface, title, status, boundary in values
    ]


def generate() -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
    nfl_audo, nfl_audo_pin = load_json("nfl_audo")
    nfl_resources, nfl_resources_pin = load_json("nfl_resources")
    apf_audo, apf_audo_pin = load_json("apf_audo")
    apf_decode, apf_decode_pin = load_json("apf_decode")
    apf_ausb, apf_ausb_pin = load_json("apf_ausb")
    presentation, presentation_pin = load_json("presentation")
    lineage, lineage_pin = load_json("lineage")
    nfl_standalone, nfl_standalone_rows = nfl_audo_summary(nfl_audo)
    nfl_banks, nfl_bank_rows = nfl_ausb_rows(nfl_resources)
    apf_standalone, apf_banks, apf_bank_rows = apf_summaries(
        apf_audo, apf_decode, apf_ausb, presentation, lineage)
    matrix = matrix_rows()
    bank_rows = nfl_standalone_rows + nfl_bank_rows + apf_bank_rows
    report = {
        "schema": SCHEMA,
        "scope": "read-only audio compatibility audit plus one separately validated copied-XISO writer; no runtime execution",
        "sources": {
            "nfl_audo": nfl_audo_pin,
            "nfl_resources": nfl_resources_pin,
            "apf_audo": apf_audo_pin,
            "apf_decode": apf_decode_pin,
            "apf_ausb": apf_ausb_pin,
            "presentation": presentation_pin,
            "lineage": lineage_pin,
            "nfl_pack0": nfl_banks.pop("source_pack"),
        },
        "nfl2k5": {
            "standalone_audo": nfl_standalone,
            "streaming_banks": nfl_banks,
            "bounded_writer": {
                "available": True,
                "target": "outer 3 / chunk 101 / menu-back_01",
                "input": "strict RIFF PCM16LE mono 16000 Hz, exactly 5696 frames",
                "output": "exclusively created layout-identical copied XISO",
                "codec": "deterministic Xbox IMA ADPCM, 89 x 36-byte blocks",
                "metadata": "wrapper, 128-byte system region, descriptor, and 12-byte unknown tail preserved",
                "runtime_visibility_proved": False,
                "generic": False,
            },
        },
        "apf2k8": {
            "standalone_audo": apf_standalone,
            "streaming_banks": apf_banks,
            "bounded_writer": {
                "available": False,
                "reason": "no validated XMA1 encoder; loop/valid-bit metadata and IFF/H7A/external-bank allocation/repack incomplete",
            },
        },
        "compatibility_matrix": matrix,
        "claims": {
            "nfl_standalone_audo_wav_extract_available": True,
            "nfl_one_fixed_slot_wav_import_available": True,
            "nfl_generic_audo_import_available": False,
            "nfl_music_commentary_bank_import_available": False,
            "apf_audo_wav_extract_partially_available": True,
            "apf_xma1_encoder_available": False,
            "apf_audio_writeback_available": False,
            "direct_flac_import_available": False,
            "runtime_visibility_tested": False,
            "emulator_started": False,
            "retail_original_modified": False,
            "retail_audio_in_report": False,
        },
        "portme": [
            "PORTME: prove the exact runtime owner selecting NFL outer 3 chunk 101 and capture audible replacement before labeling it runtime-tested.",
            "PORTME: validate and authorize other NFL AUDO slots individually; duplicate names do not imply shared ownership.",
            "PORTME: recover NFL ABNK/WBNK and AUSB external-bank directories, sample codecs, cues, loops, gain, pan, priority, and allocation.",
            "PORTME: obtain or implement a legally usable, bitstream-validated XMA1 encoder before any APF WAV/FLAC import claim.",
            "PORTME: prove APF AUDO loop/valid-bit semantics and rebuild DRAM/SRAM plus IFF/H7A allocation without altering unrelated files.",
            "PORTME: rebuild APF AUSB duration/boundary tables and external banks only after all cue identities and packet constraints are proved.",
        ],
    }
    return report, matrix, bank_rows


def encode_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def encode_tsv(rows: list[dict[str, Any]], fields: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports/assets/audio_modding_compatibility.json")
    parser.add_argument("--matrix", type=Path,
                        default=ROOT / "reports/assets/audio_modding_compatibility.tsv")
    parser.add_argument("--banks", type=Path,
                        default=ROOT / "reports/assets/audio_modding_banks.tsv")
    args = parser.parse_args()
    targets = plan_outputs(args.output, args.matrix, args.banks)
    report, matrix, banks = generate()
    payloads = [
        encode_json(report),
        encode_tsv(matrix, ["schema", "surface", "title", "status", "boundary"]),
        encode_tsv(banks, [
            "schema", "title", "container", "name", "external_filename", "role_class",
            "entry_count", "sample_rate", "channel_field", "extract_status", "import_status",
            "ownership_boundary",
        ]),
    ]
    outputs = reserve_outputs(targets)
    success = False
    try:
        for output, payload in zip(outputs, payloads, strict=True):
            write_owned(output, payload)
        success = True
    finally:
        if success:
            close_outputs(outputs)
        else:
            discard_outputs(outputs)
    print(
        "AUDIO_MODDING_COMPATIBILITY_PASS "
        f"matrix={len(matrix)} banks={len(banks)} nfl_writer=true apf_writer=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, CompatibilityError, nfl_outer.FormatError,
            nfl_scene_probe.ProbeError) as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
