#!/usr/bin/env python3
"""Build a reproducible APF 2K8 -> NFL 2K5 archive-lineage evidence set.

This is deliberately an evidence classifier, not a runtime-reachability test.
It reads the original archive volumes without modifying them, decodes only the
seven selected APF IFFs, and compares their named resources against the
complete named NFL catalogs for every resource kind present in those IFFs.

The strongest classifications use independently recovered semantic reports:
whole-LAYT record sequences, the franchise STRG text pool, decoded RGBA
textures, and decoded audio spectra.  A shared name alone is always labelled
as such.  Likewise, absence means only absence from the complete *named NFL
catalog* covered here; it is not a claim that no anonymous byte sequence could
contain related data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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


SCHEMA = "vc_apf_nfl_cut_content_lineage/v1"
MAX_DECOMPRESSED = 256 * 1024 * 1024

APF_TARGETS = {
    108: "trophyroom.iff",
    137: "audiotestmenu.iff",
    730: "franchise_show.iff",
    810: "franchise.iff",
    941: "franchise_show_outro.iff",
    1215: "season.iff",
    1221: "franchise_show_intro.iff",
}

# Four pairs reproduce their exact NFL outer ID from the XBE's proven
# CRC32(uppercase UTF-16LE filename) domain.  NFL outer 23 has no recovered
# logical filename, so that pair is justified by the co-located resource and
# semantic evidence recorded in the report, not by inventing one.
DIRECT_PAIRS = {
    137: (15, "AUDIOTESTMENU.IFF", "exact_filename_id_and_resource_set"),
    730: (18, "FRANCHISE_SHOW.IFF", "exact_filename_id_and_resource_set"),
    810: (23, None, "resource_layout_and_string_pool_closure"),
    941: (21, "FRANCHISE_SHOW_OUTRO.IFF", "exact_filename_id_and_resource_set"),
    1221: (20, "FRANCHISE_SHOW_INTRO.IFF", "exact_filename_id_and_resource_set"),
}

TARGET_KINDS = {"AMCR", "AUDO", "AUSB", "LAYT", "MRKS", "SCNE", "STRG", "TXTR"}
GENERIC_NFL_KINDS = {"AMCR", "AUSB", "MRKS", "STRG"}
SELECTED_TEXTURES = {
    "conferencechampionships",
    "divisionplayoffs",
    "draft_logo",
    "email2",
    "mailpieces",
    "probowl",
    "superbowl",
    "wildcardplayoffs",
}
TEXTURE_COMPARE_NAMES = {"draft_logo", "email2", "mailpieces"}
LOCALIZATION_TEXTS = {
    "NFL",
    "PRESENTED BY ESPN",
    "Franchise/",
    "Playoff Picture",
    "Draft",
    "SEASON AWARDS",
    "Next week on SportsCenter",
    "OFF-SEASON",
}


class LineageError(ValueError):
    """Raised when a pinned evidence invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LineageError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def source(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)}


def safe(value: str) -> str:
    return "".join(character if character.isalnum() or character in "._-" else "_" for character in value)


def read_apf_part(
    reader: apf_inner.ArchiveReader,
    record: apf_inner.IFFRecord,
    part: apf_inner.FilePart,
    cache: dict[int, bytes],
) -> bytes:
    if part.block_index not in cache:
        cache[part.block_index] = apf_inner.decode_block(
            reader, record, part.block_index, MAX_DECOMPRESSED
        )
    data = cache[part.block_index]
    end = part.offset + part.length
    require(end <= len(data), "APF inner part exceeds decoded block")
    return data[part.offset:end]


def rgba_metrics(first: bytes, second: bytes) -> dict[str, object]:
    require(len(first) == len(second) and len(first) % 4 == 0, "RGBA sizes differ")
    count = len(first)
    absolute = [abs(a - b) for a, b in zip(first, second)]
    pixel_count = count // 4
    exact_pixels = sum(
        first[offset : offset + 4] == second[offset : offset + 4]
        for offset in range(0, count, 4)
    )
    mean_a = sum(first) / count
    mean_b = sum(second) / count
    covariance = sum((a - mean_a) * (b - mean_b) for a, b in zip(first, second))
    variance_a = sum((a - mean_a) ** 2 for a in first)
    variance_b = sum((b - mean_b) ** 2 for b in second)
    correlation = covariance / math.sqrt(variance_a * variance_b)
    return {
        "mean_absolute_error_rgba": sum(absolute) / count,
        "mean_absolute_error_rgb": sum(
            absolute[offset + channel]
            for offset in range(0, count, 4)
            for channel in range(3)
        )
        / (pixel_count * 3),
        "mean_absolute_error_alpha": sum(absolute[3::4]) / pixel_count,
        "exact_pixel_ratio": exact_pixels / pixel_count,
        "pearson_correlation_rgba": correlation,
    }


def png_rgba(path: Path) -> tuple[int, int, bytes]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise LineageError("Pillow is required for decoded texture comparison") from exc
    with Image.open(path) as image:
        converted = image.convert("RGBA")
        return converted.width, converted.height, converted.tobytes()


def stft_spectrum(samples: object, frame: int = 512, hop: int = 256) -> object:
    try:
        import numpy as np
    except ImportError as exc:
        raise LineageError("NumPy is required for the bounded audio comparison") from exc
    signal = samples.mean(axis=1)
    window = np.hanning(frame)
    spectrum = np.zeros(frame // 2 + 1, dtype=np.float64)
    count = 0
    for offset in range(0, max(0, len(signal) - frame + 1), hop):
        spectrum += np.abs(np.fft.rfft(signal[offset : offset + frame] * window))
        count += 1
    require(count > 0, "audio is too short for spectral comparison")
    return spectrum


def cosine(first: object, second: object) -> float:
    import numpy as np
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    require(denominator > 0.0, "zero-energy audio spectrum")
    return float(np.dot(first, second) / denominator)


def decode_xma_pcm(riff: bytes, channels: int) -> object:
    import numpy as np
    ffmpeg = shutil.which("ffmpeg")
    require(ffmpeg is not None, "ffmpeg is required for XMA evidence decoding")
    completed = subprocess.run(
        [
            ffmpeg,
            "-v", "error", "-xerror", "-i", "pipe:0", "-map", "0:a:0",
            "-f", "s16le", "-c:a", "pcm_s16le", "pipe:1",
        ],
        input=riff,
        capture_output=True,
        check=False,
        timeout=120,
    )
    require(completed.returncode == 0, f"ffmpeg XMA decode failed: {completed.stderr!r}")
    require(len(completed.stdout) % (channels * 2) == 0, "XMA PCM output is unaligned")
    return np.frombuffer(completed.stdout, dtype="<i2").reshape(-1, channels).astype(np.float64)


def read_wav_pcm(path: Path) -> tuple[int, int, object]:
    import numpy as np
    with wave.open(str(path), "rb") as stream:
        require(stream.getsampwidth() == 2, "NFL comparison WAV is not PCM16")
        channels = stream.getnchannels()
        rate = stream.getframerate()
        frames = stream.readframes(stream.getnframes())
    pcm = np.frombuffer(frames, dtype="<i2").reshape(-1, channels).astype(np.float64)
    return channels, rate, pcm


def load_nfl_catalog(
    root: Path,
    archive: object,
    inventory_rows: list[object],
) -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []

    texture_report = load_json(root / "reports/assets/nfl2k5_all_txtr_inventory_v2.json")
    require(texture_report["summary"]["decoded_texture_count"] == 57208, "NFL TXTR corpus changed")
    for row in texture_report["textures"]:
        catalog.append(
            {
                "name": row["name"], "name_casefolded": row["name"].casefold(),
                "kind": "TXTR", "outer_index": row["outer_index"],
                "chunk_index": row["chunk_index"], "decoded_sha256": row["decoded_sha256"],
                "rgba_sha256": row["rgba_sha256"], "png_path": row["png_path"],
                "width": row["width"], "height": row["height"], "format": row["format_name"],
            }
        )

    scene_report = load_json(root / "reports/assets/nfl2k5_scne_inventory.json")
    require(scene_report["summary"]["scene_count"] == 4616, "NFL SCNE corpus changed")
    for row in scene_report["scenes"]:
        catalog.append(
            {
                "name": row["name"], "name_casefolded": row["name"].casefold(),
                "kind": "SCNE", "outer_index": row["outer_index"],
                "chunk_index": row["chunk_index"], "decoded_sha256": row["decoded_sha256"],
            }
        )

    layout_report = load_json(root / "reports/assets/cross_title_layout_inventory.json")
    nfl_layouts = [row for row in layout_report["layouts"] if row["platform"] == "nfl2k5"]
    require(len(nfl_layouts) == 86, "NFL LAYT corpus changed")
    for row in nfl_layouts:
        catalog.append(
            {
                "name": row["layout_name"], "name_casefolded": row["layout_name"].casefold(),
                "kind": "LAYT", "outer_index": row["outer_index"],
                "chunk_index": row["inner_index"], "decoded_sha256": row["sha256"],
            }
        )

    audio_report = load_json(root / "reports/assets/nfl2k5_audo_wav_all.json")
    require(audio_report["summary"]["record_count"] == 850, "NFL AUDO corpus changed")
    for row in audio_report["records"]:
        semantic = row["semantic"]
        catalog.append(
            {
                "name": semantic["name"], "name_casefolded": semantic["name"].casefold(),
                "kind": "AUDO", "outer_index": row["outer_index"],
                "chunk_index": row["chunk_index"], "decoded_sha256": row["decoded_sha256"],
                "channels": semantic["channels"], "sample_rate": semantic["sample_rate"],
                "wav_path": row["wav_output"],
            }
        )

    for record in inventory_rows:
        if record.kind not in GENERIC_NFL_KINDS:
            continue
        entry = archive.entries[record.outer_index]
        span = read_entry_range(
            archive, entry, record.chunk_offset, 0x20 + record.stored_size
        )
        data, _ = decode_resource(span, record)
        name, _, _ = named_inner(data, record.kind)
        catalog.append(
            {
                "name": name, "name_casefolded": name.casefold(), "kind": record.kind,
                "outer_index": record.outer_index, "chunk_index": record.chunk_index,
                "decoded_sha256": sha256_bytes(data),
            }
        )

    counts = Counter(row["kind"] for row in catalog)
    require(
        counts == {
            "AMCR": 10, "AUDO": 850, "AUSB": 17, "LAYT": 86,
            "MRKS": 170, "SCNE": 4616, "STRG": 2, "TXTR": 57208,
        },
        f"named NFL catalog coverage changed: {dict(counts)}",
    )
    return catalog


def direct_nfl_entries(
    archive: object,
    inventory_rows: list[object],
    direct_indices: set[int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in inventory_rows:
        if record.outer_index not in direct_indices:
            continue
        entry = archive.entries[record.outer_index]
        span = read_entry_range(archive, entry, record.chunk_offset, 0x20 + record.stored_size)
        data, _ = decode_resource(span, record)
        name, _, _ = named_inner(data, record.kind)
        rows.append(
            {
                "outer_index": record.outer_index,
                "outer_id": f"0x{entry.name_id:08x}",
                "chunk_index": record.chunk_index,
                "name": name,
                "name_casefolded": name.casefold(),
                "kind": record.kind,
                "decoded_size": len(data),
                "decoded_sha256": sha256_bytes(data),
            }
        )
    return rows


def write_tsv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})


def scene_vertex_lineage(root: Path) -> list[dict[str, object]]:
    """Compare authored node names and declared vertices, not rendered pixels.

    APF counts come from the bounded SCNE parser's mesh declarations.  NFL
    counts come from the complete SCNE shape ledger; the NFL glTF supplies the
    corresponding recovered node order/name list.  The host screenshots are
    useful derived views, but these source declarations are the proof.
    """
    specifications = (
        {
            "name": "sc_logo",
            "apf_report": "reports/cut_content/apf_nfl_lineage/sc_logo/report.json",
            "nfl_outer_index": 18,
            "nfl_chunk_index": 10,
            "nfl_gltf": "assets/intermediate/nfl2k5/models/0018_0010_sc_logo.gltf",
            "derived_apf_view": "reports/cut_content/apf_nfl_lineage/sc_logo/render_full.png",
            "derived_nfl_view": "reports/cut_content/apf_nfl_lineage/sc_logo/nfl2k5_render_full.png",
        },
        {
            "name": "bermanintro",
            "apf_report": "reports/cut_content/apf_nfl_lineage/bermanintro/report.json",
            "nfl_outer_index": 21,
            "nfl_chunk_index": 0,
            "nfl_gltf": "assets/intermediate/nfl2k5/models/0021_0000_bermanintro.gltf",
            "derived_apf_view": "reports/cut_content/apf_nfl_lineage/bermanintro/berman_model_only.png",
            "derived_nfl_view": "reports/cut_content/apf_nfl_lineage/bermanintro/nfl2k5_berman_model_only.png",
        },
        {
            "name": "draft_menu",
            "apf_report": "reports/cut_content/apf_nfl_lineage/draft_menu/report.json",
            "nfl_outer_index": 23,
            "nfl_chunk_index": 5,
            "nfl_gltf": "assets/intermediate/nfl2k5/models/0023_0005_draft_menu.gltf",
            "derived_apf_view": "reports/cut_content/apf_nfl_lineage/draft_menu/draft_people_only.png",
            "derived_nfl_view": "reports/cut_content/apf_nfl_lineage/draft_menu/nfl2k5_draft_people_only.png",
        },
    )
    with (root / "reports/assets/nfl2k5_scne_shapes.tsv").open(encoding="utf-8") as stream:
        shape_rows = list(csv.DictReader(stream, delimiter="\t"))
    results: list[dict[str, object]] = []
    for specification in specifications:
        report_path = root / specification["apf_report"]
        nfl_gltf_path = root / specification["nfl_gltf"]
        report = load_json(report_path)
        require(report["summary"]["scne_parsed"] == 1, "APF scene proof did not parse")
        scene = report["scenes"][0]
        apf_nodes = [
            {
                "name": node["name"],
                "vertices": sum(int(mesh["vertex_count"]) for mesh in node["meshes"]),
            }
            for node in scene["nodes"]
        ]
        nfl_shapes = sorted(
            [
                row for row in shape_rows
                if int(row["outer_index"]) == specification["nfl_outer_index"]
                and int(row["chunk_index"]) == specification["nfl_chunk_index"]
            ],
            key=lambda row: int(row["index"]),
        )
        nfl_names = [node["name"] for node in load_json(nfl_gltf_path)["nodes"]]
        require(len(nfl_shapes) == len(nfl_names), "NFL SCNE name/shape counts differ")
        nfl_nodes = [
            {"name": name, "vertices": int(shape["vertex_count"])}
            for name, shape in zip(nfl_names, nfl_shapes)
        ]
        require(
            [row["name"] for row in apf_nodes] == [row["name"] for row in nfl_nodes],
            f"{specification['name']}: exact node-name/order lineage changed",
        )
        deltas = [
            {
                "name": apf["name"],
                "apf_vertices": apf["vertices"],
                "nfl_vertices": nfl["vertices"],
                "delta_apf_minus_nfl": apf["vertices"] - nfl["vertices"],
            }
            for apf, nfl in zip(apf_nodes, nfl_nodes)
            if apf["vertices"] != nfl["vertices"]
        ]
        for key in ("derived_apf_view", "derived_nfl_view"):
            require((root / specification[key]).is_file(), f"missing derived view {specification[key]}")
        results.append(
            {
                "name": specification["name"],
                "node_count": len(apf_nodes),
                "exact_node_name_and_order_match": True,
                "apf_declared_vertex_total": sum(row["vertices"] for row in apf_nodes),
                "nfl_declared_vertex_total": sum(row["vertices"] for row in nfl_nodes),
                "changed_node_count": len(deltas),
                "changed_nodes": deltas,
                "apf_source": source(report_path),
                "nfl_shape_source": {
                    "path": "reports/assets/nfl2k5_scne_shapes.tsv",
                    "outer_index": specification["nfl_outer_index"],
                    "chunk_index": specification["nfl_chunk_index"],
                },
                "nfl_name_source": source(nfl_gltf_path),
                "derived_views": {
                    "apf": specification["derived_apf_view"],
                    "nfl": specification["derived_nfl_view"],
                    "label": "derived neutral-material host projections; source declarations above are authoritative",
                },
            }
        )
    expected = {
        "sc_logo": (3, 1958, 1858, 2),
        "bermanintro": (20, 4270, 4328, 3),
        "draft_menu": (41, 8671, 8624, 7),
    }
    for row in results:
        require(
            (
                row["node_count"], row["apf_declared_vertex_total"],
                row["nfl_declared_vertex_total"], row["changed_node_count"],
            ) == expected[row["name"]],
            f"{row['name']}: pinned scene lineage counts changed",
        )
    return results


def build(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.resolve()
    apf_index = root / "extracted/All-Pro Football 2K8 (USA)/0A"
    nfl_index = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    report_dir = args.output.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    apf_manifest_path = root / "reports/manifests/apf_inner.json"
    nfl_inventory_path = root / "reports/assets/nfl2k5_resource_chunks_v2.json"
    apf_manifest = load_json(apf_manifest_path)
    require(apf_manifest["summary"]["total_inner_file_count"] == 10394, "APF manifest changed")
    manifest_entries = {row["table_index"]: row for row in apf_manifest["iff_entries"]}

    apf_archive = apf_outer.parse_archive(apf_index)
    nfl_archive = parse_nfl_archive(nfl_index)
    _, nfl_inventory = parse_nfl_inventory(nfl_inventory_path)
    nfl_catalog = load_nfl_catalog(root, nfl_archive, nfl_inventory)
    catalog_by_key: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in nfl_catalog:
        catalog_by_key[(row["name_casefolded"], row["kind"])].append(row)

    nfl_direct = direct_nfl_entries(
        nfl_archive, nfl_inventory, {value[0] for value in DIRECT_PAIRS.values()}
    )
    direct_by_outer: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in nfl_direct:
        direct_by_outer[row["outer_index"]].append(row)

    layout_semantics_path = root / "reports/assets/cross_title_layout_semantics.json"
    layout_semantics = load_json(layout_semantics_path)
    exact_layouts = {
        row["layout_name_casefolded"] for row in layout_semantics["exact_whole_layout_sequences"]
    }
    require(len(exact_layouts) == 27, "whole-layout semantic set changed")

    string_report_path = root / "reports/assets/cross_title_string_tables.json"
    string_report = load_json(string_report_path)
    string_summary = string_report["summary"]
    require(string_summary["primary_record_count"] == 1492, "franchise STRG count changed")
    require(string_summary["primary_ordered_texts_identical"], "franchise STRG order diverged")
    require(string_summary["primary_pools_identical"], "franchise STRG pool diverged")

    apf_audio_rows = {
        (row["outer_table_index"], row["inner_file_index"]): row
        for row in load_json(root / "reports/assets/apf_audio_inventory.json")["records"]
    }
    nfl_audio_rows = {
        (row["outer_index"], row["chunk_index"]): row
        for row in load_json(root / "reports/assets/nfl2k5_audo_wav_all.json")["records"]
    }

    texture_dir = report_dir / "visuals/apf_textures"
    nfl_texture_dir = report_dir / "visuals/nfl_textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    nfl_texture_dir.mkdir(parents=True, exist_ok=True)

    resources: list[dict[str, object]] = []
    audio_comparisons: list[dict[str, object]] = []
    texture_comparisons: list[dict[str, object]] = []
    archive_summaries: list[dict[str, object]] = []

    with apf_inner.ArchiveReader(apf_archive) as reader:
        for outer_index, outer_name in APF_TARGETS.items():
            entry = apf_archive.entries[outer_index]
            manifest = manifest_entries[outer_index]
            candidates = [row["name"] for row in manifest["outer_name_candidates"]]
            require(outer_name in candidates, f"APF outer {outer_index} lost {outer_name}")
            record = apf_inner.parse_iff(reader, entry)
            cache: dict[int, bytes] = {}

            direct = DIRECT_PAIRS.get(outer_index)
            direct_rows = [] if direct is None else direct_by_outer[direct[0]]
            direct_by_key = {
                (row["name_casefolded"], row["kind"]): row for row in direct_rows
            }
            apf_keys: set[tuple[str, str]] = set()
            direct_shared = 0
            direct_byte_exact = 0

            for item in record.files:
                require(item.name is not None and item.type_name is not None, "target APF file is unnamed")
                parts = [read_apf_part(reader, record, part, cache) for part in item.parts]
                body = b"".join(parts)
                key = (item.name.casefold(), item.type_name)
                apf_keys.add(key)
                global_matches = catalog_by_key.get(key, [])
                direct_match = direct_by_key.get(key)
                body_hash = sha256_bytes(body)
                global_byte_matches = [
                    match for match in global_matches if match["decoded_sha256"] == body_hash
                ]
                direct_exact = bool(
                    direct_match and direct_match["decoded_sha256"] == body_hash
                )
                if direct_match:
                    direct_shared += 1
                if direct_exact:
                    direct_byte_exact += 1

                classification = "apf_only_in_complete_named_nfl_catalog"
                proof = "catalog_absence_only"
                if global_matches:
                    classification = "name_and_type_match_only"
                    proof = "exact_resource_name_and_type"
                if direct_match:
                    classification = "structurally_converted_same_named_resource"
                    proof = "same_named_resource_in_direct_package_pair"
                if item.type_name == "LAYT" and item.name.casefold() in exact_layouts:
                    classification = "structurally_converted_exact_layout_sequence"
                    proof = "whole_record_type_and_exposed_name_sequence_exact"
                if outer_index == 810 and item.type_name == "STRG" and item.name == "strings":
                    classification = "structurally_converted_exact_1492_text_sequence"
                    proof = "ordered_texts_and_string_pool_exact"
                if direct_exact or global_byte_matches:
                    classification = "byte_identical_decoded_resource"
                    proof = "sha256_exact"

                texture = None
                if item.type_name == "TXTR":
                    try:
                        metadata = apf_inner.parse_txtr_metadata(parts[0])
                        base = parts[1] if len(parts) >= 2 else parts[0][4096:]
                        width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
                        texture = {
                            "status": "decoded", "width": width, "height": height,
                            "format": metadata["format_name"], "rgba_sha256": sha256_bytes(rgba),
                        }
                        if item.name.casefold() in SELECTED_TEXTURES:
                            output = texture_dir / f"{safe(item.name)}.png"
                            apf_inner.write_rgba_png(output, width, height, rgba)
                            texture["png_path"] = str(output.relative_to(root))
                            texture["png_sha256"] = sha256_file(output)
                        candidates_with_png = [match for match in global_matches if match.get("png_path")]
                        if candidates_with_png:
                            nfl = candidates_with_png[0]
                            nfl_path = root / nfl["png_path"]
                            nfl_width, nfl_height, nfl_rgba = png_rgba(nfl_path)
                            comparison = {
                                "apf_outer_index": outer_index,
                                "apf_inner_index": item.index,
                                "name": item.name,
                                "nfl_outer_index": nfl["outer_index"],
                                "nfl_chunk_index": nfl["chunk_index"],
                                "apf_dimensions": f"{width}x{height}",
                                "nfl_dimensions": f"{nfl_width}x{nfl_height}",
                                "same_dimensions": width == nfl_width and height == nfl_height,
                                "apf_format": metadata["format_name"],
                                "nfl_format": nfl["format"],
                                "rgba_exact": rgba == nfl_rgba,
                            }
                            if comparison["same_dimensions"]:
                                comparison.update(rgba_metrics(rgba, nfl_rgba))
                            texture_comparisons.append(comparison)
                            texture["nfl_comparison"] = comparison
                            if (
                                comparison["same_dimensions"]
                                and comparison["pearson_correlation_rgba"] >= 0.90
                            ):
                                classification = "visually_equivalent_transcoded_texture"
                                proof = "same_dimensions_and_decoded_rgba_correlation_ge_0.90"
                            if item.name.casefold() in TEXTURE_COMPARE_NAMES:
                                copied = nfl_texture_dir / f"{safe(item.name)}.png"
                                copied.write_bytes(nfl_path.read_bytes())
                                comparison["nfl_png_copy"] = str(copied.relative_to(root))
                    except apf_inner.FormatError as exc:
                        texture = {"status": "PORTME", "error": str(exc)}

                audio = None
                if item.type_name == "AUDO" and direct_match is not None:
                    apf_audio_row = apf_audio_rows[(outer_index, item.index)]
                    nfl_audio_row = nfl_audio_rows[
                        (direct_match["outer_index"], direct_match["chunk_index"])
                    ]
                    metadata = apf_audio_row["metadata"]
                    channels = int(metadata["derived_channel_count"])
                    rate = int(metadata["sample_rate"])
                    payload = parts[1]
                    riff = apf_audio.make_xma1_riff(
                        payload,
                        channels,
                        rate,
                        int(metadata["xma1_loop_start_bit_candidate"]),
                        int(metadata["xma1_loop_end_bit_candidate"]),
                        int(metadata["xma1_loop_subframe_candidate"]),
                    )
                    apf_pcm = decode_xma_pcm(riff, channels)
                    nfl_wav = root / nfl_audio_row["wav_output"]
                    nfl_channels, nfl_rate, nfl_pcm = read_wav_pcm(nfl_wav)
                    sample_delta = len(apf_pcm) - len(nfl_pcm)
                    spectrum_cosine = cosine(stft_spectrum(apf_pcm), stft_spectrum(nfl_pcm))
                    import numpy as np
                    apf_rms = float(np.sqrt(np.mean(apf_pcm * apf_pcm)))
                    nfl_rms = float(np.sqrt(np.mean(nfl_pcm * nfl_pcm)))
                    audio = {
                        "apf_codec": "XMA1", "nfl_codec": "Xbox IMA ADPCM",
                        "apf_channels": channels, "nfl_channels": nfl_channels,
                        "apf_sample_rate": rate, "nfl_sample_rate": nfl_rate,
                        "apf_decoded_samples_per_channel": len(apf_pcm),
                        "nfl_decoded_samples_per_channel": len(nfl_pcm),
                        "sample_count_delta_apf_minus_nfl": sample_delta,
                        "global_stft_magnitude_cosine": spectrum_cosine,
                        "apf_rms": apf_rms, "nfl_rms": nfl_rms,
                        "rms_ratio": apf_rms / nfl_rms,
                        "interpretation": "strong common-source evidence, not PCM identity",
                    }
                    audio_comparisons.append({"name": item.name, **audio})
                    if (
                        channels == nfl_channels and rate == nfl_rate
                        and abs(sample_delta) <= 128 and spectrum_cosine >= 0.95
                        and 0.90 <= audio["rms_ratio"] <= 1.10
                    ):
                        classification = "probable_common_source_transcoded_audio"
                        proof = "matching_layout_duration_rms_and_spectral_fingerprint"

                resources.append(
                    {
                        "apf_outer_index": outer_index,
                        "apf_outer_id": f"0x{entry.name_id:08x}",
                        "apf_outer_name": outer_name,
                        "apf_inner_index": item.index,
                        "name": item.name,
                        "type": item.type_name,
                        "decoded_part_count": len(parts),
                        "decoded_size": len(body),
                        "decoded_sha256": body_hash,
                        "global_nfl_name_type_match_count": len(global_matches),
                        "global_nfl_match_locations": [
                            f"{match['outer_index']}:{match['chunk_index']}" for match in global_matches
                        ],
                        "global_nfl_byte_match_count": len(global_byte_matches),
                        "direct_nfl_outer_index": None if direct_match is None else direct_match["outer_index"],
                        "direct_nfl_chunk_index": None if direct_match is None else direct_match["chunk_index"],
                        "direct_decoded_byte_identical": direct_exact,
                        "classification": classification,
                        "proof_basis": proof,
                        "texture": texture,
                        "audio": audio,
                    }
                )

            nfl_keys = {(row["name_casefolded"], row["kind"]) for row in direct_rows}
            archive_summaries.append(
                {
                    "apf_outer_index": outer_index,
                    "apf_outer_id": f"0x{entry.name_id:08x}",
                    "apf_outer_name": outer_name,
                    "apf_outer_size": entry.size,
                    "apf_resource_count": len(record.files),
                    "apf_type_counts": dict(sorted(Counter(item.type_name for item in record.files).items())),
                    "comparison_scope": "direct_package" if direct else "complete_named_nfl_catalog",
                    "nfl_outer_index": None if direct is None else direct[0],
                    "nfl_outer_id": None if direct is None else f"0x{nfl_archive.entries[direct[0]].name_id:08x}",
                    "nfl_filename": None if direct is None else direct[1],
                    "pair_basis": None if direct is None else direct[2],
                    "nfl_resource_count": None if direct is None else len(direct_rows),
                    "direct_shared_name_type_count": direct_shared,
                    "direct_apf_only_name_type_count": None if direct is None else len(apf_keys - nfl_keys),
                    "direct_nfl_only_name_type_count": None if direct is None else len(nfl_keys - apf_keys),
                    "direct_byte_identical_decoded_resource_count": direct_byte_exact,
                    "global_nfl_name_type_match_count": sum(
                        bool(catalog_by_key.get((item.name.casefold(), item.type_name)))
                        for item in record.files
                    ),
                    "apf_only_in_complete_named_nfl_catalog_count": sum(
                        not bool(catalog_by_key.get((item.name.casefold(), item.type_name)))
                        for item in record.files
                    ),
                }
            )

    require(len(resources) == 228, "selected APF resource count changed")
    require(sum(row["global_nfl_name_type_match_count"] > 0 for row in resources) == 107,
            "global NFL name/type match count changed")
    require(sum(row["global_nfl_name_type_match_count"] == 0 for row in resources) == 121,
            "APF catalog-only count changed")
    require(sum(row["direct_decoded_byte_identical"] for row in resources) == 0,
            "a direct decoded resource unexpectedly became byte-identical")

    direct_nfl_only: list[dict[str, object]] = []
    for apf_outer_index, (nfl_outer_index, _, _) in DIRECT_PAIRS.items():
        apf_keys = {
            (row["name"].casefold(), row["type"])
            for row in resources if row["apf_outer_index"] == apf_outer_index
        }
        for row in direct_by_outer[nfl_outer_index]:
            if (row["name_casefolded"], row["kind"]) not in apf_keys:
                direct_nfl_only.append(
                    {
                        "apf_outer_index": apf_outer_index,
                        "apf_outer_name": APF_TARGETS[apf_outer_index],
                        "nfl_outer_index": nfl_outer_index,
                        "nfl_chunk_index": row["chunk_index"],
                        "name": row["name"],
                        "type": row["kind"],
                        "classification": "nfl_only_in_direct_2k5_package",
                    }
                )

    localization_path = root / "reports/assets/apf_txt_localization.tsv"
    localization: list[dict[str, object]] = []
    with localization_path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["text"] in LOCALIZATION_TEXTS:
                localization.append(row)
    require(LOCALIZATION_TEXTS <= {row["text"] for row in localization},
            "one or more pinned APF NFL/ESPN localization strings disappeared")

    translations_path = root / "reports/assets/cross_title_string_tables_id_translation.tsv"
    string_witness_indices = {49, 52, 73, 76, 82, 98, 201}
    string_witnesses: list[dict[str, object]] = []
    with translations_path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if int(row["record_index"]) in string_witness_indices:
                string_witnesses.append(row)
    require({int(row["record_index"]) for row in string_witnesses} == string_witness_indices,
            "franchise string witness set changed")

    xex_report_path = root / "reports/headers/apf2k8_xex_report.json"
    toolchain_path = root / "reports/headers/apf2k8_toolchain_strings.tsv"
    xex_report = load_json(xex_report_path)
    build_identity = xex_report["build_identity"]
    codeview = xex_report["pe"]["debug"]["codeview"]
    require(build_identity["original_pe_name"] == "nfl_clean_opt_submission_ready.xex",
            "APF original PE name changed")
    require(build_identity["xex_timestamp_utc"] == "2007-06-12T22:11:24Z",
            "APF XEX timestamp changed")
    require("XENON\\NFL\\CLEAN_OPT\\default.xex.pdb" in codeview["pdb_path"],
            "APF PDB identity changed")
    with toolchain_path.open(encoding="utf-8") as stream:
        toolchain_rows = list(csv.DictReader(stream, delimiter="\t"))
    nfl_source_paths = [
        row for row in toolchain_rows
        if "/vcsports/nfl/code/" in row["value"].replace("\\", "/").casefold()
    ]
    require(len(nfl_source_paths) == 24, "APF embedded NFL source-path count changed")
    executable_identity = {
        "original_pe_name": build_identity["original_pe_name"],
        "build_timestamp_utc": build_identity["xex_timestamp_utc"],
        "pdb_path": codeview["pdb_path"],
        "embedded_vcsports_nfl_code_path_count": len(nfl_source_paths),
        "embedded_vcsports_nfl_code_paths": nfl_source_paths,
        "proof": "exact strings and XEX/PE debug metadata in the retail APF executable",
        "boundary": "NFL project naming proves branch ancestry; it does not name the branch NFL 2K6.",
    }

    visual_paths = [
        report_dir / "apf_franchise_texture_contact_sheet.png",
        report_dir / "draft_logo_2k5_vs_apf.png",
        report_dir / "sc_logo_2k5_vs_apf.png",
        report_dir / "berman_2k5_vs_apf.png",
        report_dir / "apf_xex_identity_card.png",
        report_dir / "apf_2k6_animation_identity_card.png",
    ]
    visual_evidence = []
    for path in visual_paths:
        require(path.is_file(), f"video-ready visual is missing: {path}")
        width, height, rgba = png_rgba(path)
        require(width >= 512 and height >= 512 and len(set(rgba)) > 16,
                f"video-ready visual is implausible: {path}")
        visual_evidence.append(
            {
                "path": str(path.relative_to(root)), "width": width, "height": height,
                "sha256": sha256_file(path),
            }
        )

    scene_comparisons = scene_vertex_lineage(root)

    summary = {
        "selected_apf_archive_count": len(APF_TARGETS),
        "selected_apf_resource_count": len(resources),
        "direct_archive_pair_count": len(DIRECT_PAIRS),
        "direct_shared_name_type_count": sum(row["direct_shared_name_type_count"] for row in archive_summaries),
        "direct_byte_identical_decoded_resource_count": 0,
        "global_nfl_name_type_match_count": 107,
        "apf_only_in_complete_named_nfl_catalog_count": 121,
        "franchise_apf_resource_count": 118,
        "franchise_nfl_resource_count": 91,
        "franchise_direct_shared_name_type_count": 77,
        "franchise_apf_addition_count": 41,
        "franchise_nfl_only_count": 14,
        "franchise_shared_layout_count": 22,
        "franchise_exact_whole_layout_sequence_count": 21,
        "franchise_exact_ordered_string_record_count": 1492,
        "franchise_exact_string_pool_entry_count": string_summary["primary_pool_entry_count"],
        "texture_visual_comparison_count": len(texture_comparisons),
        "probable_common_source_audio_count": sum(
            row["classification"] == "probable_common_source_transcoded_audio"
            for row in resources
        ),
        "scene_exact_node_name_lineage_count": len(scene_comparisons),
        "runtime_reachability_proved": False,
        "nfl_2k6_identity_proved": False,
    }
    require(summary["direct_shared_name_type_count"] == 105, "direct shared total changed")
    require(summary["franchise_exact_string_pool_entry_count"] == 1106, "string pool count changed")
    require(summary["probable_common_source_audio_count"] == 4, "audio lineage count changed")

    document = {
        "schema": SCHEMA,
        "sources": {
            "apf_index": {"path": str(apf_index), "size": apf_index.stat().st_size},
            "nfl_index": {"path": str(nfl_index), "size": nfl_index.stat().st_size},
            "apf_inner_manifest": source(apf_manifest_path),
            "nfl_resource_inventory": source(nfl_inventory_path),
            "layout_semantics": source(layout_semantics_path),
            "string_tables": source(string_report_path),
            "localization": source(localization_path),
            "apf_xex_report": source(xex_report_path),
            "apf_toolchain_strings": source(toolchain_path),
        },
        "catalog_coverage": {
            "scope": "all named NFL resources for every type present in the selected APF archives",
            "counts": dict(sorted(Counter(row["kind"] for row in nfl_catalog).items())),
            "absence_caveat": "APF-only means no exact case-insensitive name+type in this complete named catalog; it is not byte-search proof against anonymous data.",
        },
        "summary": summary,
        "archive_summaries": archive_summaries,
        "resources": resources,
        "direct_nfl_only_resources": direct_nfl_only,
        "texture_comparisons": texture_comparisons,
        "audio_comparisons": audio_comparisons,
        "scene_vertex_lineage": scene_comparisons,
        "apf_executable_identity": executable_identity,
        "franchise_string_evidence": {
            "apf": "outer 810 / inner 87 strings (UTF-16BE)",
            "nfl": "outer 23 / chunk 65 strings (UTF-16LE)",
            "record_count": 1492,
            "ordered_texts_identical": True,
            "pool_entry_count": 1106,
            "pools_identical": True,
            "numeric_id_domains_shared": False,
            "witnesses": string_witnesses,
        },
        "apf_nfl_espn_localization_witnesses": localization,
        "video_ready_visuals": visual_evidence,
        "interpretation_boundary": {
            "proved": [
                "Retail APF archives contain converted NFL 2K5 franchise and SportsCenter resources.",
                "APF franchise.iff preserves the complete 1492-record NFL franchise text sequence and 1106-entry text pool.",
                "Twenty-one co-located franchise LAYTs preserve complete record type/exposed-name sequences.",
                "APF contains a decoded NFL DRAFT texture and an SC-logo scene whose geometry renders as the SportsCenter mark.",
                "The APF/NFL sc_logo, bermanintro, and draft_menu scenes preserve all 3/20/41 node names in exact order while changing declared vertex counts, proving scene evolution rather than name-only residue.",
                "The compared decoded resource bodies are converted rather than byte-copied: zero of 105 direct same-name/type resources are byte-identical.",
            ],
            "not_proved": [
                "Archive presence alone does not prove any package is reachable in the shipped APF frontend.",
                "No recovered build label, date, or ownership edge identifies these assets specifically as NFL 2K6.",
                "No complete or half-complete executable franchise state machine is established by this archive audit.",
            ],
            "careful_inference": "The converted and expanded package is consistent with an intervening next-generation NFL development branch, but calling it an NFL 2K6 build remains a hypothesis.",
        },
        "portme": [
            "PORTME: trace every selected outer filename and resource through APF XEX ownership to distinguish reachable, orphaned, and development-only data.",
            "PORTME: recover APF MRKS event semantics and callbacks before claiming the franchise presentation can execute.",
            "PORTME: recover STRG numeric-ID consumers and the franchise gameplay/save data model; exact text preservation is not executable-mode preservation.",
            "PORTME: add DXT5A and linear Xenos TXTR decode/import for background2, gradient2, playcall, skew, and email1.",
            "PORTME: locate dated build metadata or an explicit NFL 2K6 identifier before assigning that product name.",
        ],
    }
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output", type=Path,
        default=Path("reports/cut_content/apf_nfl_lineage"),
        help="report directory (relative paths are resolved below --root)",
    )
    args = parser.parse_args()
    if not args.output.is_absolute():
        args.output = args.root / args.output
    document = build(args)
    output = args.output
    json_path = output / "lineage.json"
    json_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    write_tsv(
        output / "archive_summary.tsv",
        document["archive_summaries"],
        [
            "apf_outer_index", "apf_outer_id", "apf_outer_name", "apf_outer_size",
            "apf_resource_count", "comparison_scope", "nfl_outer_index", "nfl_outer_id",
            "nfl_filename", "pair_basis", "nfl_resource_count",
            "direct_shared_name_type_count", "direct_apf_only_name_type_count",
            "direct_nfl_only_name_type_count", "direct_byte_identical_decoded_resource_count",
            "global_nfl_name_type_match_count", "apf_only_in_complete_named_nfl_catalog_count",
        ],
    )
    write_tsv(
        output / "resource_lineage.tsv",
        document["resources"],
        [
            "apf_outer_index", "apf_outer_id", "apf_outer_name", "apf_inner_index",
            "name", "type", "decoded_size", "decoded_sha256",
            "global_nfl_name_type_match_count", "global_nfl_match_locations",
            "global_nfl_byte_match_count", "direct_nfl_outer_index",
            "direct_nfl_chunk_index", "direct_decoded_byte_identical",
            "classification", "proof_basis",
        ],
    )
    write_tsv(
        output / "scene_vertex_lineage.tsv",
        [
            {
                **row,
                "changed_nodes": ";".join(
                    f"{node['name']}:{node['nfl_vertices']}->{node['apf_vertices']}"
                    for node in row["changed_nodes"]
                ),
            }
            for row in document["scene_vertex_lineage"]
        ],
        [
            "name", "node_count", "exact_node_name_and_order_match",
            "nfl_declared_vertex_total", "apf_declared_vertex_total",
            "changed_node_count", "changed_nodes",
        ],
    )
    write_tsv(
        output / "video_evidence.tsv",
        [
            {
                "claim": "APF retail contains NFL DRAFT and postseason label textures",
                "proof": "decoded RGBA from franchise.iff TXTR resources",
                "artifact": "reports/cut_content/apf_nfl_lineage/apf_franchise_texture_contact_sheet.png",
                "boundary": "proves retail asset presence, not runtime use or NFL 2K6 identity",
            },
            {
                "claim": "APF retail contains SportsCenter logo geometry",
                "proof": "franchise_show.iff outer 730 inner 11 SCNE sc_logo; all 3 node names match NFL and declared vertices evolve 1858->1958",
                "artifact": "reports/cut_content/apf_nfl_lineage/sc_logo_2k5_vs_apf.png",
                "boundary": "derived neutral-material comparison; source declarations prove 1858->1958 vertices and exact node names",
            },
            {
                "claim": "APF Berman intro is a converted NFL 2K5 asset",
                "proof": "all 20 node names/order match; declared vertices evolved 4328->4270, including s_bermanhead 1348->1261",
                "artifact": "reports/cut_content/apf_nfl_lineage/berman_2k5_vs_apf.png",
                "boundary": "derived four-node neutral-material comparison; decoded bodies are not byte-identical",
            },
            {
                "claim": "APF draft stage is evolved NFL 2K5 scene data",
                "proof": "all 41 node names/order match; declared vertices evolved 8624->8671 across seven nodes",
                "artifact": "reports/cut_content/apf_nfl_lineage/draft_menu/draft_people_only.png",
                "boundary": "derived neutral-material view; exact source declaration deltas are in scene_vertex_lineage.tsv",
            },
            {
                "claim": "APF preserves the complete NFL franchise text payload",
                "proof": "1492 ordered records and 1106 pool entries are exact across endian-converted STRG bodies",
                "artifact": "reports/cut_content/apf_nfl_lineage/lineage.json",
                "boundary": "does not prove a working APF franchise state machine",
            },
            {
                "claim": "APF franchise layouts are evolved, not name-only remnants",
                "proof": "21 co-located LAYTs have exact whole type/exposed-name record sequences",
                "artifact": "reports/assets/cross_title_layout_semantics.json",
                "boundary": "callbacks and runtime ownership remain PORTME",
            },
            {
                "claim": "Retail APF executable is an NFL-named Xenon branch build",
                "proof": "original PE nfl_clean_opt_submission_ready.xex, XENON/NFL/CLEAN_OPT PDB, 24 vcsports/nfl/code paths",
                "artifact": "reports/cut_content/apf_nfl_lineage/apf_xex_identity_card.png",
                "boundary": "exact NFL branch ancestry; no exact NFL 2K6 product identifier",
            },
            {
                "claim": "Retail APF executable preserves a 2K6-era annual animation generation",
                "proof": "519 unique 2K6-tagged animation IDs and 597 aligned PPC pointer references",
                "artifact": "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_identity_card.png",
                "boundary": "direct annual gameplay lineage, not a formal complete product/build ID",
            },
        ],
        ["claim", "proof", "artifact", "boundary"],
    )
    print(
        "APF_NFL_CUT_CONTENT_LINEAGE_PASS "
        f"archives={document['summary']['selected_apf_archive_count']} "
        f"resources={document['summary']['selected_apf_resource_count']} "
        f"direct_shared={document['summary']['direct_shared_name_type_count']} "
        f"byte_identical={document['summary']['direct_byte_identical_decoded_resource_count']} "
        f"franchise_strings={document['summary']['franchise_exact_ordered_string_record_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LineageError, apf_inner.FormatError, apf_outer.FormatError, OSError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
