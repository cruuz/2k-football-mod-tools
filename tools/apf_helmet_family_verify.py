#!/usr/bin/env python3
"""Independently verify one APF helmet copied-volume patch.

This verifier does not import the helmet writer or transport.  It checks the
pinned family catalog, copied-volume identity outside one allocation, IFF/H7A
reparse, all seven DXN levels, PNG-derived mip hashes, fixed inactive bytes,
and bit-exact preservation of ``helmet_normal`` and both DRAM descriptors.
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
import apf_xenos_dxn_mip_layout as dxn_mips


SCHEMA = "apf_helmet_family_verify/v1"
RECIPE_SCHEMA = "apf2k8_helmet_color_recipe/v1"
PATCH_SCHEMA = "apf_helmet_family_patch/v1"
CATALOG_SCHEMA = "apf_helmet_family_layout/v1"
WORKSPACE = Path(__file__).resolve().parents[1]
CATALOG = WORKSPACE / "reports/assets/apf_helmet_family_layout.json"
EXPECTED_CATALOG_SHA256 = "72bf3efd4495e03fb856e0fb776313c842ebfafeb8d20d19f91318d7161aba03"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
MAX_RECIPE_BYTES = 64 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024


class VerifyError(ValueError):
    """Raised when a copied helmet patch violates an invariant."""


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
    """Load the canonical selector recipe without importing the writer."""

    recipe = regular(path, "APF helmet recipe")
    size = recipe.stat().st_size
    require(0 < size <= MAX_RECIPE_BYTES, "APF helmet recipe size is outside its limit")
    payload = recipe.read_bytes()
    require(len(payload) == size, "APF helmet recipe changed while reading")
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"APF helmet recipe is not valid UTF-8 JSON: {exc}") from exc
    canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    require(payload == canonical, "APF helmet recipe must use canonical sorted JSON")
    require(
        isinstance(value, dict)
        and set(value) == {"schema", "asset_index", "png"}
        and value.get("schema") == RECIPE_SCHEMA,
        "APF helmet recipe fields/schema differ from v1",
    )
    asset_index = value.get("asset_index")
    require(
        type(asset_index) is int and 0 <= asset_index <= 23,
        "APF helmet asset_index must be an integer in 0..23",
    )
    png_value = value.get("png")
    require(
        isinstance(png_value, str) and png_value and "\0" not in png_value,
        "APF helmet recipe png must be a non-empty path string",
    )
    png = Path(png_value).expanduser()
    if not png.is_absolute():
        png = recipe.parent / png
    png = regular(png, "APF helmet PNG")
    require(
        png != recipe and png.suffix.lower() == ".png",
        "APF helmet recipe must name a distinct .png file",
    )
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
    require(sha256(payload) == EXPECTED_CATALOG_SHA256,
            "helmet catalog hash changed")
    document = json.loads(payload)
    require(document.get("schema") == CATALOG_SCHEMA,
            "helmet catalog schema changed")
    require(document["source"]["sha256_before"] == EXPECTED_VOLUME_SHA256 and
            document["source"]["sha256_after"] == EXPECTED_VOLUME_SHA256,
            "helmet catalog source changed")
    rows = document["helmets"]
    require(len(rows) == 24 and [row["asset_index"] for row in rows] == list(range(24)),
            "helmet catalog roster changed")
    return rows[asset_index]


def load_png(path: Path) -> tuple[bytes, str]:
    path = regular(path, "helmet PNG")
    payload = path.read_bytes()
    require(0 < len(payload) <= MAX_PNG_BYTES, "helmet PNG size is outside its limit")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            require(image.format == "PNG" and image.size == (256, 1024) and
                    image.mode == "RGBA", "helmet PNG must be exact 256x1024 RGBA PNG")
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise VerifyError(f"cannot decode APF helmet PNG: {exc}") from exc
    require(all(rgba[index] == 0 for index in range(2, len(rgba), 4)),
            "helmet PNG B channel must be zero")
    require(all(rgba[index] == 255 for index in range(3, len(rgba), 4)),
            "helmet PNG A channel must be 255")
    return rgba, sha256(payload)


def _bc4_palette(a: int, b: int) -> tuple[int, ...]:
    if a > b:
        return (a, b, (6*a+b)//7, (5*a+2*b)//7, (4*a+3*b)//7,
                (3*a+4*b)//7, (2*a+5*b)//7, (a+6*b)//7)
    return (a, b, (4*a+b)//5, (3*a+2*b)//5, (2*a+3*b)//5,
            (a+4*b)//5, 0, 255)


def _decode_bc4(block: bytes) -> tuple[int, ...]:
    require(len(block) == 8, "BC4 block length changed")
    palette = _bc4_palette(block[0], block[1])
    selectors = int.from_bytes(block[2:], "little")
    return tuple(palette[(selectors >> (3*index)) & 7] for index in range(16))


def decode_level(linear: bytes, location: dxn_mips.MipLocation) -> bytes:
    require(len(linear) == location.logical_block_count * 16,
            "linear DXN level length changed")
    rgba = bytearray(location.width * location.height * 4)
    for by in range(location.height_blocks):
        for bx in range(location.width_blocks):
            index = by * location.width_blocks + bx
            block = linear[index*16:index*16+16]
            first, second = _decode_bc4(block[:8]), _decode_bc4(block[8:])
            for y in range(4):
                for x in range(4):
                    px, py = bx*4+x, by*4+y
                    if px < location.width and py < location.height:
                        offset = (py * location.width + px) * 4
                        sample = y*4+x
                        rgba[offset:offset+4] = bytes((first[sample], second[sample], 0, 255))
    return bytes(rgba)


def metrics(wanted: bytes, decoded: bytes) -> dict[str, object]:
    require(len(wanted) == len(decoded), "RGBA metric lengths differ")
    errors = [abs(a-b) for a, b in zip(wanted, decoded)]
    squared = sum(value*value for value in errors)
    rmse = math.sqrt(squared / len(errors)) if errors else 0.0
    return {
        "compared_components": len(errors),
        "different_components": sum(value != 0 for value in errors),
        "maximum_absolute_error": max(errors, default=0),
        "mean_absolute_error": sum(errors) / len(errors) if errors else 0.0,
        "rmse": rmse,
        "psnr_db": None if rmse == 0 else 20.0 * math.log10(255.0 / rmse),
    }


def _entry_state(archive: apf_outer.Archive, entry_index: int) -> dict[str, object]:
    entry = archive.entries[entry_index]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [apf_inner.decode_block(reader, record, index, 1 << 30)
                  for index in range(record.block_count)]
    require(record.block_count == 2 and record.file_count == 2 and not record.warnings,
            "helmet output IFF structure changed")
    require([item.name for item in record.files] == ["helmet_color", "helmet_normal"] and
            all(item.type_name == "TXTR" for item in record.files),
            "helmet output inner roster changed")
    expected = [
        [(0, 0x000, 0xE0), (1, 0x000000, 0x60000)],
        [(0, 0x0E0, 0xE0), (1, 0x060000, 0x160000)],
    ]
    require([[(part.block_index, part.offset, part.length) for part in item.parts]
             for item in record.files] == expected,
            "helmet output part layout changed")
    metadata = apf_inner.parse_txtr_metadata(blocks[0][:0xE0])
    required = {
        "vc_file_id": "0xcf7f3bdf", "width": 256, "height": 1024,
        "pitch_pixels": 256, "format": 49, "endianness": 1,
        "tiled": True, "stacked": False, "dimension": 1,
        "vc_base_data_length": 0x40000, "vc_mip_data_length": 0x20000,
        "mip_min_level": 0, "mip_max_level": 6, "packed_mips": True,
        "mip_address_pages": 64, "swizzle_components": [0, 1, 2, 3],
    }
    require(all(metadata.get(key) == value for key, value in required.items()),
            "helmet output descriptor changed")
    require(record.footer is not None, "helmet output footer missing")
    footer_size = 8 + record.footer.payload_size
    footer = entry_bytes[record.file_length:record.file_length + footer_size]
    require(not any(entry_bytes[record.file_length + footer_size:]),
            "helmet output allocation tail is nonzero")
    return {
        "entry": entry, "record": record, "entry_bytes": entry_bytes,
        "blocks": blocks, "metadata": metadata,
        "texture": blocks[1][:0x60000],
        "normal": blocks[1][0x60000:0x1C0000], "footer": footer,
    }


def _outside_span_equal(
    source: Path, output: Path, offset: int, size: int
) -> tuple[str, str]:
    require(source.stat().st_size == output.stat().st_size, "copied 0A size changed")
    before, after = hashlib.sha256(), hashlib.sha256()
    cursor = 0
    with source.open("rb") as left, output.open("rb") as right:
        while True:
            a, b = left.read(8*1024*1024), right.read(8*1024*1024)
            require(len(a) == len(b), "copied 0A shortened")
            if not a:
                break
            end = cursor + len(a)
            for start, stop in ((cursor, min(end, offset)),
                                (max(cursor, offset+size), end)):
                if start < stop:
                    lo, hi = start-cursor, stop-cursor
                    before.update(a[lo:hi]); after.update(b[lo:hi])
            cursor = end
    require(before.digest() == after.digest(), "copied 0A differs outside target span")
    return before.hexdigest(), after.hexdigest()


def verify(source_path: Path, output_path: Path, manifest_path: Path,
           png_path: Path, asset_index: int) -> dict[str, object]:
    row = load_catalog(asset_index)
    source = regular(source_path, "source APF 0A")
    output = regular(output_path, "output APF 0A")
    manifest_path = regular(manifest_path, "helmet patch manifest")
    require(source != output, "source and output APF 0A paths must differ")
    source_before = sha256_file(source)
    require(source_before == EXPECTED_VOLUME_SHA256, "source is not pinned retail APF 0A")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == PATCH_SCHEMA and manifest.get("mode") == "patched",
            "helmet manifest is not a patched v1 output")
    target = manifest.get("family_target", {})
    require(target.get("asset_index") == asset_index and
            target.get("outer_table_index") == row["outer_table_index"] and
            target.get("catalog_sha256") == EXPECTED_CATALOG_SHA256 and
            target.get("png_contract") == "R/G are DXN channels; B=0; A=255" and
            target.get("runtime_visibility_proved") is False,
            "helmet manifest target differs from catalog")
    png_rgba, png_sha = load_png(png_path)
    require(manifest["source"]["png_rgba_sha256"] == sha256(png_rgba),
            "manifest PNG RGBA hash differs")
    source_archive, output_archive = apf_outer.parse_archive(source), apf_outer.parse_archive(output)
    entry_index = int(row["outer_table_index"])
    source_state, output_state = _entry_state(source_archive, entry_index), _entry_state(output_archive, entry_index)
    source_entry, output_entry = source_state["entry"], output_state["entry"]
    require(source_entry.size == output_entry.size == row["outer_allocation"]["size"],
            "helmet fixed allocation changed")
    require(sha256(source_state["entry_bytes"]) == row["outer_allocation"]["sha256"],
            "source entry differs from catalog")
    require(sha256(output_state["entry_bytes"]) ==
            manifest["binary_patch_manifest"]["replacement_sha256"],
            "output entry differs from manifest")
    require(output_state["entry_bytes"] != source_state["entry_bytes"],
            "patched output entry is unchanged")
    require(source_state["blocks"][0] == output_state["blocks"][0],
            "helmet DRAM descriptors changed")
    require(source_state["normal"] == output_state["normal"],
            "helmet_normal changed")
    require(source_state["footer"] == output_state["footer"], "helmet footer changed")
    source_texture, output_texture = source_state["texture"], output_state["texture"]
    require(sha256(source_texture) == row["inner_file"]["texture_sha256"],
            "source texture differs from catalog")
    require(sha256(output_texture) == manifest["texture"]["sha256_after"],
            "output texture differs from manifest")
    locations = dxn_mips.derive_layout(output_state["metadata"])
    require(len(locations) == 7 and
            dxn_mips.transport_roundtrip(output_texture, locations) == output_texture,
            "output seven-level DXN transport failed")
    image = Image.frombytes("RGBA", (256, 1024), png_rgba)
    expected = [png_rgba] + [image.resize((item.width, item.height),
                                          Image.Resampling.BOX).tobytes()
                             for item in locations[1:]]
    level_reports = []
    for item, wanted, claimed in zip(locations, expected, manifest["levels"]):
        linear = dxn_mips.extract_linear_dxn(output_texture, item)
        decoded = decode_level(linear, item)
        actual_metrics = metrics(wanted, decoded)
        require(claimed["level"] == item.level and
                claimed["wanted_rgba_sha256"] == sha256(wanted) and
                claimed["linear_dxn_sha256_after"] == sha256(linear) and
                claimed["decoded_rgba_sha256_after"] == sha256(decoded) and
                claimed["decode_back_metrics"] == actual_metrics,
                f"manifest level {item.level} differs from independent decode")
        level_reports.append({
            "level": item.level, "linear_dxn_sha256": sha256(linear),
            "wanted_rgba_sha256": sha256(wanted),
            "decoded_rgba_sha256": sha256(decoded),
            "decode_back_metrics": actual_metrics,
        })
    active: set[int] = set()
    for item in locations:
        for y in range(item.height_blocks):
            for x in range(item.width_blocks):
                relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                    x + item.origin_block_x, y + item.origin_block_y,
                    item.pitch_blocks, 4,
                )
                active.update(range(item.data_offset+relative, item.data_offset+relative+16))
    require(all(source_texture[index] == output_texture[index]
                for index in range(len(source_texture)) if index not in active),
            "inactive DXN bytes changed")
    outside_before, outside_after = _outside_span_equal(
        source, output, source_entry.segments[0].pack_offset, source_entry.size
    )
    source_after = sha256_file(source)
    require(source_after == source_before, "source 0A changed during verification")
    return {
        "schema": SCHEMA,
        "asset_index": asset_index,
        "source": {"path": str(source), "sha256_before": source_before,
                   "sha256_after": source_after, "modified": False},
        "output": {"path": str(output), "sha256": sha256_file(output),
                   "entry_sha256": sha256(output_state["entry_bytes"]),
                   "texture_sha256": sha256(output_texture),
                   "outside_target_sha256_source": outside_before,
                   "outside_target_sha256_output": outside_after,
                   "outside_target_bit_exact": True},
        "png": {"path": str(png_path), "file_sha256": png_sha,
                "rgba_sha256": sha256(png_rgba),
                "contract": "R/G are DXN channels; B=0; A=255"},
        "levels": level_reports,
        "validation": {
            "catalog_target_exact": True,
            "copied_archive_reparsed": True,
            "all_seven_levels_independently_decoded": True,
            "inactive_mip_bytes_preserved": True,
            "both_dram_descriptors_preserved": True,
            "helmet_normal_preserved": True,
            "footer_preserved": True,
            "fixed_allocation_preserved": True,
            "source_opened_read_only": True,
            "helmet_color_channel_meanings_named": False,
            "runtime_visibility_proved": False,
        },
        "contains_game_or_replacement_bytes": False,
    }


def write_artifact_dir(path: Path, report: dict[str, object]) -> Path:
    """Exclusively create a hash/metrics-only provider artifact directory."""

    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    parent = requested.parent.lstat()
    require(
        stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
        "verification artifact parent must be a non-symlink directory",
    )
    try:
        os.mkdir(requested, 0o755)
    except FileExistsError as exc:
        raise VerifyError(
            f"verification artifact directory already exists: {requested}"
        ) from exc
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
            require(written > 0, "short write while creating helmet verification report")
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
                "png_dimensions": [256, 1024],
                "png_mode": "RGBA",
                "png_blue_zero": True,
                "png_alpha_255": True,
                "png_fully_opaque": True,
                "channel_semantics_named": False,
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
                "channel_semantics_named": False,
            }
            report_path = write_artifact_dir(args.artifact_dir, report)
            print(
                "APF_HELMET_FAMILY_VERIFY_PASS "
                f"asset={recipe['asset_index']} levels=7 normal=1 "
                "channels=raw-rg outside_target=exact runtime_visibility=false "
                f"report={report_path}"
            )
            return 0
        report = verify(args.source_volume, args.output_volume, args.manifest,
                        args.png, args.asset_index)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "APF_HELMET_FAMILY_VERIFY_PASS "
            f"asset={args.asset_index} levels=7 normal=1 "
            "outside_target=exact runtime_visibility=false"
        )
    except (VerifyError, apf_inner.FormatError, apf_outer.FormatError,
            dxn_mips.MipLayoutError, OSError, json.JSONDecodeError,
            KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
