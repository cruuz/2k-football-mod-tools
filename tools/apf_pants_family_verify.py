#!/usr/bin/env python3
"""Independently verify an APF pants copied-volume patch.

The verifier does not import the pants writer or transport module.  It checks
the pinned catalog target, source/copy identity outside one allocation, IFF
and H7A reparse, all eight Xenos BC1 levels, the input PNG-derived mip hashes,
and preservation of the three normal maps.  It emits hashes and metrics only.
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
import sys
from typing import Any

from PIL import Image, UnidentifiedImageError

import apf_inner
import apf_outer
import apf_xenos_bc1_mip_layout as bc1_mips


SCHEMA = "apf_pants_family_verify/v1"
RECIPE_SCHEMA = "apf2k8_pants_color_recipe/v1"
PATCH_SCHEMA = "apf_pants_family_patch/v1"
CATALOG_SCHEMA = "apf_pants_family_layout/v1"
WORKSPACE = Path(__file__).resolve().parents[1]
CATALOG = WORKSPACE / "reports/assets/apf_pants_family_layout.json"
EXPECTED_CATALOG_SHA256 = "82241aefe6728a7426552663ee69ecffbdabca01f4359e8322edf75775adf293"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
MAX_RECIPE_BYTES = 64 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024


class VerifyError(ValueError):
    """Raised when a copied pants patch does not satisfy every invariant."""


def require(value: bool, message: str) -> None:
    if not value:
        raise VerifyError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in value, f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_recipe(path: Path) -> dict[str, object]:
    """Load the canonical named-selector recipe without importing the writer."""

    recipe = regular(path, "APF pants recipe")
    size = recipe.stat().st_size
    require(0 < size <= MAX_RECIPE_BYTES, "APF pants recipe size is outside its limit")
    payload = recipe.read_bytes()
    require(len(payload) == size, "APF pants recipe changed while reading")
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"APF pants recipe is not valid UTF-8 JSON: {exc}") from exc
    canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    require(payload == canonical, "APF pants recipe must use canonical sorted JSON")
    require(
        isinstance(value, dict)
        and set(value) == {"schema", "asset_index", "png"}
        and value.get("schema") == RECIPE_SCHEMA,
        "APF pants recipe fields/schema differ from v1",
    )
    asset_index = value.get("asset_index")
    require(
        type(asset_index) is int and 0 <= asset_index <= 23,
        "APF pants asset_index must be an integer in 0..23",
    )
    png_value = value.get("png")
    require(
        isinstance(png_value, str) and png_value and "\0" not in png_value,
        "APF pants recipe png must be a non-empty path string",
    )
    png = Path(png_value).expanduser()
    if not png.is_absolute():
        png = recipe.parent / png
    png = regular(png, "APF pants PNG")
    require(png != recipe and png.suffix.lower() == ".png",
            "APF pants recipe must name a distinct .png file")
    png_rgba, png_sha = load_png(png)
    return {
        "schema": RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": png,
        "png_file_sha256": png_sha,
        "png_rgba_sha256": sha256(png_rgba),
        "path": recipe,
        "sha256": sha256(payload),
    }


def load_catalog(asset_index: int) -> dict[str, object]:
    require(0 <= asset_index < 24, "asset index must be in 0..23")
    payload = CATALOG.read_bytes()
    require(sha256(payload) == EXPECTED_CATALOG_SHA256, "pants catalog hash changed")
    catalog = json.loads(payload)
    require(catalog.get("schema") == CATALOG_SCHEMA, "pants catalog schema changed")
    require(
        catalog["source"]["sha256_before"] == EXPECTED_VOLUME_SHA256
        and catalog["source"]["sha256_after"] == EXPECTED_VOLUME_SHA256,
        "pants catalog source changed",
    )
    rows = catalog["pants"]
    require(len(rows) == 24 and [row["asset_index"] for row in rows] == list(range(24)),
            "pants catalog roster changed")
    return rows[asset_index]


def load_png(path: Path) -> tuple[bytes, str]:
    path = regular(path, "pants PNG")
    payload = path.read_bytes()
    require(0 < len(payload) <= MAX_PNG_BYTES, "pants PNG size is outside its limit")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            require(image.format == "PNG" and image.size == (512, 512) and image.mode == "RGBA",
                    "pants PNG must be exact 512x512 RGBA PNG")
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise VerifyError(f"cannot decode APF pants PNG: {exc}") from exc
    require(all(rgba[index] == 255 for index in range(3, len(rgba), 4)),
            "pants PNG must be fully opaque")
    return rgba, sha256(payload)


def _entry_state(
    archive: apf_outer.Archive, entry_index: int
) -> dict[str, object]:
    entry = archive.entries[entry_index]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    require(record.block_count == 2 and record.file_count == 4 and not record.warnings,
            "pants output IFF structure changed")
    expected_names = [
        "pants_heavy_normal", "pants_medium_normal", "pants_color", "pants_light_normal"
    ]
    require([item.name for item in record.files] == expected_names and
            all(item.type_name == "TXTR" for item in record.files),
            "pants output inner roster changed")
    expected_parts = [
        [(0, 0x2A0, 0xE0), (1, 0xF0000, 0x60000)],
        [(0, 0x1C0, 0xE0), (1, 0x90000, 0x60000)],
        [(0, 0x000, 0xE0), (1, 0x00000, 0x30000)],
        [(0, 0x0E0, 0xE0), (1, 0x30000, 0x60000)],
    ]
    require(
        [[(part.block_index, part.offset, part.length) for part in item.parts]
         for item in record.files] == expected_parts,
        "pants output part layout changed",
    )
    metadata = apf_inner.parse_txtr_metadata(blocks[0][:0xE0])
    required = {
        "vc_file_id": "0x9717866d", "width": 512, "height": 512,
        "pitch_pixels": 512, "format": 18, "endianness": 1,
        "tiled": True, "stacked": False, "dimension": 1,
        "vc_base_data_length": 0x20000, "vc_mip_data_length": 0x10000,
        "mip_min_level": 0, "mip_max_level": 7, "packed_mips": True,
        "mip_address_pages": 32, "swizzle_components": [0, 1, 2, 3],
    }
    require(all(metadata.get(key) == value for key, value in required.items()),
            "pants output descriptor changed")
    require(record.footer is not None, "pants output footer missing")
    footer_size = 8 + record.footer.payload_size
    footer = entry_bytes[record.file_length : record.file_length + footer_size]
    require(not any(entry_bytes[record.file_length + footer_size :]),
            "pants output allocation tail is nonzero")
    return {
        "entry": entry,
        "record": record,
        "entry_bytes": entry_bytes,
        "blocks": blocks,
        "metadata": metadata,
        "texture": blocks[1][:0x30000],
        "footer": footer,
    }


def decode_level(linear: bytes, location: bc1_mips.MipLocation) -> bytes:
    require(len(linear) == location.logical_block_count * 8,
            "linear BC1 level length changed")
    rgba = bytearray(location.width * location.height * 4)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            block_index = block_y * location.width_blocks + block_x
            pixels = apf_inner._decode_bc1(linear[block_index * 8 : block_index * 8 + 8])  # type: ignore[attr-defined]
            for local_y in range(4):
                for local_x in range(4):
                    destination = (
                        (block_y * 4 + local_y) * location.width
                        + block_x * 4 + local_x
                    ) * 4
                    rgba[destination : destination + 4] = bytes(
                        pixels[local_y * 4 + local_x]
                    )
    return bytes(rgba)


def metrics(wanted: bytes, decoded: bytes) -> dict[str, object]:
    require(len(wanted) == len(decoded), "RGBA metric lengths differ")
    errors = [abs(first - second) for first, second in zip(wanted, decoded)]
    squared = sum(value * value for value in errors)
    rmse = math.sqrt(squared / len(errors)) if errors else 0.0
    return {
        "compared_components": len(errors),
        "different_components": sum(value != 0 for value in errors),
        "maximum_absolute_error": max(errors, default=0),
        "mean_absolute_error": sum(errors) / len(errors) if errors else 0.0,
        "rmse": rmse,
        "psnr_db": None if rmse == 0 else 20.0 * math.log10(255.0 / rmse),
    }


def _outside_span_equal(
    source: Path, output: Path, offset: int, size: int
) -> tuple[str, str]:
    require(source.stat().st_size == output.stat().st_size, "copied 0A size changed")
    before = hashlib.sha256()
    after = hashlib.sha256()
    cursor = 0
    with source.open("rb") as left, output.open("rb") as right:
        while True:
            a = left.read(8 * 1024 * 1024)
            b = right.read(8 * 1024 * 1024)
            require(len(a) == len(b), "copied 0A shortened")
            if not a:
                break
            chunk_end = cursor + len(a)
            for start, end in ((cursor, min(chunk_end, offset)),
                               (max(cursor, offset + size), chunk_end)):
                if start < end:
                    local_start, local_end = start - cursor, end - cursor
                    before.update(a[local_start:local_end])
                    after.update(b[local_start:local_end])
            cursor = chunk_end
    require(before.digest() == after.digest(), "copied 0A differs outside target span")
    return before.hexdigest(), after.hexdigest()


def verify(
    source_path: Path,
    output_path: Path,
    manifest_path: Path,
    png_path: Path,
    asset_index: int,
) -> dict[str, object]:
    row = load_catalog(asset_index)
    source = regular(source_path, "source APF 0A")
    output = regular(output_path, "output APF 0A")
    manifest_path = regular(manifest_path, "pants patch manifest")
    require(source != output, "source and output APF 0A paths must differ")
    source_before = sha256_file(source)
    require(source_before == EXPECTED_VOLUME_SHA256, "source is not pinned retail APF 0A")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == PATCH_SCHEMA and manifest.get("mode") == "patched",
            "pants manifest is not a patched v1 output")
    target = manifest.get("family_target", {})
    require(
        target.get("asset_index") == asset_index
        and target.get("outer_table_index") == row["outer_table_index"]
        and target.get("catalog_sha256") == EXPECTED_CATALOG_SHA256
        and target.get("runtime_visibility_proved") is False,
        "pants manifest target differs from catalog",
    )
    png_rgba, png_sha = load_png(png_path)
    require(manifest["source"]["png_rgba_sha256"] == sha256(png_rgba),
            "manifest PNG RGBA hash differs")

    source_archive = apf_outer.parse_archive(source)
    output_archive = apf_outer.parse_archive(output)
    entry_index = int(row["outer_table_index"])
    source_state = _entry_state(source_archive, entry_index)
    output_state = _entry_state(output_archive, entry_index)
    source_entry = source_state["entry"]
    output_entry = output_state["entry"]
    require(source_entry.size == output_entry.size == row["outer_allocation"]["size"],
            "pants fixed allocation changed")
    require(sha256(source_state["entry_bytes"]) == row["outer_allocation"]["sha256"],
            "source entry hash differs from catalog")
    require(sha256(output_state["entry_bytes"]) == manifest["binary_patch_manifest"]["replacement_sha256"],
            "output entry hash differs from manifest")
    require(output_state["entry_bytes"] != source_state["entry_bytes"],
            "patched output entry is unchanged")
    require(source_state["blocks"][0] == output_state["blocks"][0],
            "pants DRAM block changed")
    require(source_state["blocks"][1][0x30000:] == output_state["blocks"][1][0x30000:],
            "one or more pants normal maps changed")
    require(source_state["footer"] == output_state["footer"], "pants footer changed")

    source_texture = source_state["texture"]
    output_texture = output_state["texture"]
    require(sha256(source_texture) == row["inner_file"]["texture_sha256"],
            "source texture hash differs from catalog")
    require(sha256(output_texture) == manifest["texture"]["sha256_after"],
            "output texture hash differs from manifest")
    locations = bc1_mips.derive_layout(output_state["metadata"])
    require(len(locations) == 8 and bc1_mips.transport_roundtrip(output_texture, locations) == output_texture,
            "output eight-level transport failed")
    expected_rgba = [png_rgba] + [
        Image.frombytes("RGBA", (512, 512), png_rgba).resize(
            (item.width, item.height), Image.Resampling.BOX
        ).tobytes()
        for item in locations[1:]
    ]
    level_reports = []
    for location, wanted, claimed in zip(locations, expected_rgba, manifest["levels"]):
        linear = bc1_mips.extract_linear_bc1(output_texture, location)
        decoded = decode_level(linear, location)
        actual_metrics = metrics(wanted, decoded)
        require(claimed["level"] == location.level and
                claimed["wanted_rgba_sha256"] == sha256(wanted) and
                claimed["linear_bc1_sha256_after"] == sha256(linear) and
                claimed["decoded_rgba_sha256_after"] == sha256(decoded) and
                claimed["decode_back_metrics"] == actual_metrics,
                f"manifest level {location.level} differs from independent decode")
        level_reports.append({
            "level": location.level,
            "linear_bc1_sha256": sha256(linear),
            "wanted_rgba_sha256": sha256(wanted),
            "decoded_rgba_sha256": sha256(decoded),
            "decode_back_metrics": actual_metrics,
        })

    # Independently prove that bytes outside active BC1 blocks were preserved.
    active: set[int] = set()
    for location in locations:
        for block_y in range(location.height_blocks):
            for block_x in range(location.width_blocks):
                relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                    block_x + location.origin_block_x,
                    block_y + location.origin_block_y,
                    location.pitch_blocks,
                    3,
                )
                active.update(range(location.data_offset + relative,
                                    location.data_offset + relative + 8))
    require(all(source_texture[index] == output_texture[index]
                for index in range(len(source_texture)) if index not in active),
            "inactive BC1 bytes changed")
    outside_before, outside_after = _outside_span_equal(
        source, output, source_entry.segments[0].pack_offset, source_entry.size
    )
    source_after = sha256_file(source)
    require(source_after == source_before, "source 0A changed during verification")
    return {
        "schema": SCHEMA,
        "asset_index": asset_index,
        "source": {
            "path": str(source),
            "sha256_before": source_before,
            "sha256_after": source_after,
            "modified": False,
        },
        "output": {
            "path": str(output),
            "sha256": sha256_file(output),
            "entry_sha256": sha256(output_state["entry_bytes"]),
            "texture_sha256": sha256(output_texture),
            "outside_target_sha256_source": outside_before,
            "outside_target_sha256_output": outside_after,
            "outside_target_bit_exact": True,
        },
        "png": {"path": str(png_path), "file_sha256": png_sha, "rgba_sha256": sha256(png_rgba)},
        "levels": level_reports,
        "validation": {
            "catalog_target_exact": True,
            "copied_archive_reparsed": True,
            "all_eight_levels_independently_decoded": True,
            "inactive_mip_bytes_preserved": True,
            "dram_block_preserved": True,
            "three_normal_maps_preserved": True,
            "footer_preserved": True,
            "fixed_allocation_preserved": True,
            "source_opened_read_only": True,
            "runtime_visibility_proved": False,
        },
        "contains_game_or_replacement_bytes": False,
    }


def write_artifact_dir(path: Path, report: dict[str, object]) -> Path:
    """Exclusively create a hash/metrics-only typed-provider artifact directory."""

    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    parent = requested.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
            "verification artifact parent must be a non-symlink directory")
    try:
        os.mkdir(requested, 0o755)
    except FileExistsError as exc:
        raise VerifyError(f"verification artifact directory already exists: {requested}") from exc
    report_path = requested / "verification.json"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            report_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o644,
        )
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            require(written > 0, "short write while creating pants verification report")
            cursor += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        return report_path
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        try:
            report_path.unlink()
        except FileNotFoundError:
            pass
        try:
            requested.rmdir()
        except OSError:
            pass
        raise


def _legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-volume", required=True, type=Path)
    parser.add_argument("--output-volume", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--asset-index", required=True, type=int)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def _typed_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-recipe")
    validate.add_argument("--recipe", required=True, type=Path)
    typed_verify = commands.add_parser("verify")
    typed_verify.add_argument("--recipe", required=True, type=Path)
    typed_verify.add_argument("--source-0a", required=True, type=Path)
    typed_verify.add_argument("--output-0a", required=True, type=Path)
    typed_verify.add_argument("--manifest", required=True, type=Path)
    typed_verify.add_argument("--artifact-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    supplied = list(sys.argv[1:] if argv is None else argv)
    legacy = not supplied or supplied[0].startswith("-")
    args = (_legacy_parser() if legacy else _typed_parser()).parse_args(supplied)
    try:
        if not legacy and args.command == "validate-recipe":
            recipe = load_recipe(args.recipe)
            print(json.dumps({
                "schema": RECIPE_SCHEMA,
                "recipe_valid": True,
                "asset_index": recipe["asset_index"],
                "png_dimensions": [512, 512],
                "png_mode": "RGBA",
                "png_fully_opaque": True,
                "png_file_sha256": recipe["png_file_sha256"],
                "png_rgba_sha256": recipe["png_rgba_sha256"],
            }, sort_keys=True))
            return 0
        if not legacy:
            recipe = load_recipe(args.recipe)
            report = verify(
                args.source_0a,
                args.output_0a,
                args.manifest,
                recipe["png"],  # type: ignore[arg-type]
                recipe["asset_index"],  # type: ignore[arg-type]
            )
            report["recipe"] = {
                "schema": RECIPE_SCHEMA,
                "asset_index": recipe["asset_index"],
                "sha256": recipe["sha256"],
            }
            report_path = write_artifact_dir(args.artifact_dir, report)
            print(
                "APF_PANTS_FAMILY_VERIFY_PASS "
                f"asset={recipe['asset_index']} levels=8 normals=3 "
                "outside_target=exact runtime_visibility=false "
                f"report={report_path}"
            )
            return 0
        report = verify(
            args.source_volume, args.output_volume, args.manifest,
            args.png, args.asset_index,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "APF_PANTS_FAMILY_VERIFY_PASS "
            f"asset={args.asset_index} levels=8 normals=3 "
            "outside_target=exact runtime_visibility=false"
        )
    except (VerifyError, apf_inner.FormatError, apf_outer.FormatError,
            bc1_mips.MipLayoutError, OSError, json.JSONDecodeError,
            KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
