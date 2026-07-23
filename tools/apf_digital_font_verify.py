#!/usr/bin/env python3
"""Independently verify an APF ``digital_font`` copied-volume patch.

The verifier does not import the font writer, transport, layout-audit, or
DXT5A module.  It independently derives the DXT5A bytes from the strict PNG,
parses both IFFs, compares all 751 inner parts, and hashes the copied volume
outside the one fixed ``global.iff`` allocation.
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


SCHEMA = "apf_digital_font_verify/v1"
RECIPE_SCHEMA = "apf2k8_digital_font_recipe/v1"
RECIPE_TARGET = "digital_font"
RECIPE_SCOPE = "shared-global-ui"
RECIPE_STORED_CHANNEL = "alpha"
PATCH_SCHEMA = "apf_digital_font_patch/v1"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_ENTRY_SHA256 = "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d"
EXPECTED_DRAM_SHA256 = "b4fb4a9ddaea8a65806c3a861597f3b1c828d41c9b9b7daa14d48af542039b2f"
EXPECTED_VRAM_SHA256 = "e9d70fda8bdb0950068f9da19c405d4e206a789387a6de396ef88cb028022ccd"
OUTER_INDEX = 1310
INNER_INDEX = 246
WIDTH = HEIGHT = 128
BLOCK_BYTES = 8
TEXTURE_BYTES = 8192
MAX_PNG_BYTES = 16 * 1024 * 1024
MAX_RECIPE_BYTES = 64 * 1024


class VerifyError(ValueError):
    """Raised when any independent font-patch invariant fails."""


def require(value: bool, message: str) -> None:
    if not value:
        raise VerifyError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def regular(path: Path, label: str) -> Path:
    info = path.expanduser().lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.expanduser().resolve(strict=True)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_png(path: Path) -> tuple[bytes, bytes, str]:
    png = regular(path, "digital_font PNG")
    payload = png.read_bytes()
    require(0 < len(payload) <= MAX_PNG_BYTES, "digital_font PNG size is outside its limit")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            require(
                image.format == "PNG" and image.size == (128, 128) and image.mode == "RGBA",
                "digital_font PNG must be exact 128x128 RGBA PNG",
            )
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise VerifyError(f"cannot decode digital_font PNG: {exc}") from exc
    require(
        all(rgba[offset : offset + 3] == b"\xff\xff\xff" for offset in range(0, len(rgba), 4)),
        "digital_font PNG RGB must be solid white",
    )
    return rgba, bytes(rgba[offset + 3] for offset in range(0, len(rgba), 4)), sha256(payload)


def load_recipe(path: Path) -> dict[str, object]:
    """Independently parse the canonical fixed-target alpha-only recipe."""

    recipe = regular(path, "APF digital_font recipe")
    size = recipe.stat().st_size
    require(0 < size <= MAX_RECIPE_BYTES, "APF digital_font recipe size is outside its limit")
    payload = recipe.read_bytes()
    require(len(payload) == size, "APF digital_font recipe changed while reading")
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"APF digital_font recipe is not valid UTF-8 JSON: {exc}") from exc
    canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    require(payload == canonical, "APF digital_font recipe must use canonical sorted JSON")
    fields = {
        "alpha_sha256", "png", "png_sha256", "png_size", "schema",
        "scope", "stored_channel", "target",
    }
    require(isinstance(value, dict) and set(value) == fields,
            "APF digital_font recipe fields differ from v1")
    require(value.get("schema") == RECIPE_SCHEMA, "APF digital_font recipe schema changed")
    require(value.get("target") == RECIPE_TARGET, "APF digital_font recipe target changed")
    require(value.get("scope") == RECIPE_SCOPE, "APF digital_font recipe global scope changed")
    require(value.get("stored_channel") == RECIPE_STORED_CHANNEL,
            "APF digital_font recipe stored channel changed")
    png_value = value.get("png")
    require(isinstance(png_value, str) and png_value and "\0" not in png_value,
            "APF digital_font recipe png must be a non-empty path string")
    png = Path(png_value).expanduser()
    if not png.is_absolute():
        png = recipe.parent / png
    png = regular(png, "APF digital_font PNG")
    require(png != recipe and png.suffix.lower() == ".png",
            "APF digital_font recipe must name a distinct .png file")
    rgba, alpha, png_sha = load_png(png)
    png_size = value.get("png_size")
    require(type(png_size) is int and png_size == png.stat().st_size,
            "APF digital_font recipe PNG size pin differs")
    require(value.get("png_sha256") == png_sha,
            "APF digital_font recipe PNG SHA-256 pin differs")
    require(value.get("alpha_sha256") == sha256(alpha),
            "APF digital_font recipe alpha SHA-256 pin differs")
    return {
        "schema": RECIPE_SCHEMA,
        "target": RECIPE_TARGET,
        "scope": RECIPE_SCOPE,
        "stored_channel": RECIPE_STORED_CHANNEL,
        "png": png,
        "png_size": png_size,
        "png_sha256": png_sha,
        "png_rgba_sha256": sha256(rgba),
        "alpha_sha256": sha256(alpha),
        "path": recipe,
        "sha256": sha256(payload),
    }


def _tile_offset(x: int, y: int) -> int:
    pitch_blocks = 32
    outer_blocks = ((y >> 5) * (pitch_blocks >> 5) + (x >> 5)) << 6
    inner_blocks = (((y >> 1) & 0b111) << 3) | (x & 0b111)
    outer_inner_bytes = (outer_blocks | inner_blocks) << 3
    bank = (y >> 4) & 1
    pipe = ((x >> 3) & 0b11) ^ (((y >> 3) & 1) << 1)
    return (
        ((y & 1) << 4)
        | (pipe << 6)
        | (bank << 11)
        | (outer_inner_bytes & 0xF)
        | (((outer_inner_bytes >> 4) & 1) << 5)
        | (((outer_inner_bytes >> 5) & 0b111) << 8)
        | ((outer_inner_bytes >> 8) << 12)
    )


def _endian_8in16(data: bytes) -> bytes:
    require(len(data) % 2 == 0, "DXT5A endian input is not 16-bit aligned")
    return b"".join(data[offset : offset + 2][::-1] for offset in range(0, len(data), 2))


def untile(tiled: bytes) -> bytes:
    require(len(tiled) == TEXTURE_BYTES, "DXT5A tiled allocation length changed")
    stored = bytearray(TEXTURE_BYTES)
    visited: set[int] = set()
    for y in range(32):
        for x in range(32):
            source = _tile_offset(x, y)
            require(source not in visited and source + 8 <= len(tiled), "DXT5A tile mapping invalid")
            visited.add(source)
            destination = (y * 32 + x) * 8
            stored[destination : destination + 8] = tiled[source : source + 8]
    require(len(visited) == 1024, "DXT5A tile mapping coverage changed")
    return _endian_8in16(bytes(stored))


def tile(linear: bytes) -> bytes:
    require(len(linear) == TEXTURE_BYTES, "DXT5A linear length changed")
    stored = _endian_8in16(linear)
    result = bytearray(TEXTURE_BYTES)
    visited: set[int] = set()
    for y in range(32):
        for x in range(32):
            destination = _tile_offset(x, y)
            require(destination not in visited and destination + 8 <= len(result),
                    "DXT5A tile mapping invalid")
            visited.add(destination)
            source = (y * 32 + x) * 8
            result[destination : destination + 8] = stored[source : source + 8]
    require(len(visited) == 1024, "DXT5A tile mapping coverage changed")
    return bytes(result)


def _palette(a0: int, a1: int) -> tuple[int, ...]:
    values = [a0, a1]
    if a0 > a1:
        values.extend((a0 * (7 - i) + a1 * i) // 7 for i in range(1, 7))
    else:
        values.extend((a0 * (5 - i) + a1 * i) // 5 for i in range(1, 5))
        values.extend((0, 255))
    return tuple(values)


def decode_block(block: bytes) -> tuple[int, ...]:
    require(len(block) == 8, "DXT5A block length changed")
    palette = _palette(block[0], block[1])
    selectors = int.from_bytes(block[2:8], "little")
    return tuple(palette[(selectors >> (pixel * 3)) & 7] for pixel in range(16))


def encode_block(alphas: tuple[int, ...]) -> bytes:
    require(len(alphas) == 16, "DXT5A encoder sample count changed")
    a0, a1 = max(alphas), min(alphas)
    palette = _palette(a0, a1)
    selectors = 0
    for pixel, alpha in enumerate(alphas):
        selector = min(range(8), key=lambda item: (abs(alpha - palette[item]), item))
        selectors |= selector << (pixel * 3)
    return bytes((a0, a1)) + selectors.to_bytes(6, "little")


def decode_alpha(linear: bytes) -> bytes:
    require(len(linear) == TEXTURE_BYTES, "DXT5A linear length changed")
    result = bytearray(WIDTH * HEIGHT)
    for block_y in range(32):
        for block_x in range(32):
            index = block_y * 32 + block_x
            values = decode_block(linear[index * 8 : index * 8 + 8])
            for local_y in range(4):
                for local_x in range(4):
                    result[(block_y * 4 + local_y) * WIDTH + block_x * 4 + local_x] = values[
                        local_y * 4 + local_x
                    ]
    return bytes(result)


def expected_linear(source_linear: bytes, wanted_alpha: bytes) -> tuple[bytes, list[int]]:
    source_alpha = decode_alpha(source_linear)
    result = bytearray(source_linear)
    changed: list[int] = []
    for block_y in range(32):
        for block_x in range(32):
            wanted = tuple(
                wanted_alpha[(block_y * 4 + ly) * WIDTH + block_x * 4 + lx]
                for ly in range(4) for lx in range(4)
            )
            original = tuple(
                source_alpha[(block_y * 4 + ly) * WIDTH + block_x * 4 + lx]
                for ly in range(4) for lx in range(4)
            )
            if wanted == original:
                continue
            index = block_y * 32 + block_x
            result[index * 8 : index * 8 + 8] = encode_block(wanted)
            changed.append(index)
    return bytes(result), changed


def metrics(wanted: bytes, decoded: bytes) -> dict[str, object]:
    require(len(wanted) == len(decoded), "alpha metric lengths differ")
    errors = [abs(a - b) for a, b in zip(wanted, decoded)]
    squared = sum(value * value for value in errors)
    rmse = math.sqrt(squared / len(errors)) if errors else 0.0
    return {
        "compared_pixels": len(errors),
        "different_pixels": sum(value != 0 for value in errors),
        "maximum_absolute_error": max(errors, default=0),
        "mean_absolute_error": sum(errors) / len(errors) if errors else 0.0,
        "rmse": rmse,
        "psnr_db": None if rmse == 0 else 20.0 * math.log10(255.0 / rmse),
    }


def strict_descriptor(metadata: dict[str, object]) -> None:
    required = {
        "vc_file_id": "0x899d899d", "vc_width": 128, "vc_height": 128,
        "vc_base_data_length": 8192, "vc_mip_data_length": 0,
        "fetch_dwords": ["0x810000fe", "0x0000007b", "0x000fe07f", "0x00a802da", "0x00000003", "0x00000200"],
        "pitch_pixels": 128, "tiled": True, "format": 59, "endianness": 1,
        "stacked": False, "width": 128, "height": 128,
        "swizzle_components": [5, 5, 5, 0], "mip_min_level": 0,
        "mip_max_level": 0, "dimension": 1, "packed_mips": False,
        "mip_address_pages": 0, "warnings": [],
    }
    require(all(metadata.get(key) == value for key, value in required.items()),
            "digital_font descriptor changed")


def entry_state(archive: apf_outer.Archive) -> dict[str, object]:
    entry = archive.entries[OUTER_INDEX]
    require(entry.name_id == 0xDB5E3E48 and len(entry.segments) == 1,
            "global.iff outer identity changed")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [apf_inner.decode_block(reader, record, i, 1 << 30) for i in range(record.block_count)]
        stored = [reader.read(entry, block.start_offset, block.stored_length) for block in record.blocks]
    require(record.block_count == 3 and record.file_count == 442 and not record.warnings,
            "global.iff structure changed")
    target = record.files[INNER_INDEX]
    require(
        target.file_id == 0x899D899D and target.name == "digital_font" and target.type_name == "TXTR"
        and [(p.block_index, p.offset, p.length) for p in target.parts]
        == [(0, 0x5C9F20, 0xE0), (1, 0x643000, 0x2000)],
        "digital_font identity or parts changed",
    )
    metadata = apf_inner.parse_txtr_metadata(blocks[0][0x5C9F20 : 0x5CA000])
    strict_descriptor(metadata)
    require(record.footer is not None, "global.iff footer missing")
    footer_total = 8 + record.footer.payload_size
    footer = entry_bytes[record.file_length : record.file_length + footer_total]
    require(not any(entry_bytes[record.file_length + footer_total :]),
            "global.iff allocation tail is nonzero")
    parts = {
        (item.index, part_index): sha256(
            blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for item in record.files
        for part_index, part in enumerate(item.parts)
    }
    require(len(parts) == 751, "global.iff file-part count changed")
    return {
        "entry": entry, "record": record, "entry_bytes": entry_bytes,
        "blocks": blocks, "stored": stored, "footer": footer, "parts": parts,
        "metadata": metadata, "texture": blocks[1][0x643000 : 0x645000],
    }


def outside_span_hash(source: Path, output: Path, offset: int, size: int) -> tuple[str, str]:
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
            end = cursor + len(a)
            for start, stop in ((cursor, min(end, offset)), (max(cursor, offset + size), end)):
                if start < stop:
                    local_start, local_stop = start - cursor, stop - cursor
                    before.update(a[local_start:local_stop])
                    after.update(b[local_start:local_stop])
            cursor = end
    require(before.digest() == after.digest(), "copied 0A differs outside global.iff")
    return before.hexdigest(), after.hexdigest()


def verify(source_path: Path, output_path: Path, manifest_path: Path, png_path: Path) -> dict[str, object]:
    source = regular(source_path, "source APF 0A")
    output = regular(output_path, "output APF 0A")
    manifest_file = regular(manifest_path, "font patch manifest")
    require(source != output, "source and output APF 0A paths must differ")
    source_before = sha256_file(source)
    require(source_before == EXPECTED_VOLUME_SHA256, "source is not pinned retail APF 0A")
    try:
        manifest = json.loads(manifest_file.read_bytes(), object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"font manifest is not valid UTF-8 JSON: {exc}") from exc
    require(manifest.get("schema") == PATCH_SCHEMA and manifest.get("mode") == "patched",
            "font manifest is not a patched v1 result")
    family = manifest.get("family_target", {})
    require(
        family.get("outer_index") == 1310 and family.get("inner_index") == 246
        and family.get("fixed_allocation") == 25028608
        and family.get("shared_global_ui_texture") is True
        and family.get("runtime_visibility_proved") is False,
        "font manifest target boundary changed",
    )
    rgba, wanted_alpha, png_file_sha = load_png(png_path)
    require(
        manifest["source"]["png_file_sha256"] == png_file_sha
        and manifest["source"]["png_rgba_sha256"] == sha256(rgba)
        and manifest["source"]["png_alpha_sha256"] == sha256(wanted_alpha),
        "font manifest PNG hashes differ",
    )

    source_archive = apf_outer.parse_archive(source)
    output_archive = apf_outer.parse_archive(output)
    source_state = entry_state(source_archive)
    output_state = entry_state(output_archive)
    source_entry = source_state["entry"]
    output_entry = output_state["entry"]
    require(source_entry.size == output_entry.size == 25028608,
            "global.iff fixed allocation changed")
    require(sha256(source_state["entry_bytes"]) == EXPECTED_ENTRY_SHA256,
            "source global.iff hash changed")
    require(sha256(source_state["blocks"][0][0x5C9F20 : 0x5CA000]) == EXPECTED_DRAM_SHA256,
            "source digital_font DRAM hash changed")
    require(sha256(source_state["texture"]) == EXPECTED_VRAM_SHA256,
            "source digital_font VRAM hash changed")
    require(
        sha256(output_state["entry_bytes"]) == manifest["binary_patch_manifest"]["replacement_sha256"],
        "output global.iff hash differs from manifest",
    )
    before_outside, after_outside = outside_span_hash(
        source, output, source_entry.segments[0].pack_offset, source_entry.size
    )
    require(source_state["record"].files == output_state["record"].files,
            "global.iff file descriptors changed")
    source_parts = source_state["parts"]
    output_parts = output_state["parts"]
    changed_parts = [key for key in source_parts if source_parts[key] != output_parts[key]]
    require(changed_parts == [(246, 1)], f"unexpected changed inner parts: {changed_parts}")
    require(source_state["stored"][0] == output_state["stored"][0], "DRAM stored block changed")
    require(source_state["stored"][2] == output_state["stored"][2], "SRAM stored block changed")
    require(source_state["footer"] == output_state["footer"], "global.iff footer changed")
    source_vram = source_state["blocks"][1]
    output_vram = output_state["blocks"][1]
    require(
        source_vram[:0x643000] == output_vram[:0x643000]
        and source_vram[0x645000:] == output_vram[0x645000:],
        "decoded global.iff VRAM changed outside digital_font",
    )

    source_linear = untile(source_state["texture"])
    output_linear = untile(output_state["texture"])
    independently_expected, changed_blocks = expected_linear(source_linear, wanted_alpha)
    require(output_linear == independently_expected,
            "output DXT5A bytes differ from independent PNG encoding")
    require(tile(output_linear) == output_state["texture"],
            "output DXT5A tile/endian round-trip failed")
    decoded_alpha = decode_alpha(output_linear)
    measured = metrics(wanted_alpha, decoded_alpha)
    require(measured == manifest["target"]["decode_back_metrics"],
            "independent DXT5A metrics differ from manifest")
    require(
        manifest["target"]["changed_dxt5a_blocks"]["count"] == len(changed_blocks)
        and manifest["target"]["linear_dxt5a_sha256_after"] == sha256(output_linear)
        and manifest["target"]["decoded_alpha_sha256_after"] == sha256(decoded_alpha),
        "font manifest DXT5A hashes/count differ",
    )
    source_after = sha256_file(source)
    require(source_after == source_before, "source APF 0A changed during verification")
    return {
        "schema": SCHEMA,
        "source": {
            "sha256_before": source_before,
            "sha256_after": source_after,
            "modified": False,
        },
        "output": {
            "sha256": sha256_file(output),
            "size": output.stat().st_size,
            "outside_global_iff_sha256_before": before_outside,
            "outside_global_iff_sha256_after": after_outside,
            "outside_global_iff_bit_exact": True,
        },
        "target": {
            "outer_index": 1310,
            "inner_index": 246,
            "entry_sha256": sha256(output_state["entry_bytes"]),
            "texture_sha256": sha256(output_state["texture"]),
            "linear_dxt5a_sha256": sha256(output_linear),
            "decoded_alpha_sha256": sha256(decoded_alpha),
            "changed_dxt5a_block_count": len(changed_blocks),
            "decode_back_metrics": measured,
        },
        "preservation": {
            "file_descriptor_count": 442,
            "file_part_count": 751,
            "changed_inner_parts": [{"file_index": 246, "part_index": 1}],
            "all_750_unrelated_inner_parts_preserved": True,
            "decoded_vram_outside_target_bit_exact": True,
            "dram_stored_block_bit_exact": True,
            "sram_stored_block_bit_exact": True,
            "footer_bit_exact": True,
            "fixed_outer_allocation": True,
        },
        "verification": {
            "writer_modules_imported": False,
            "png_reencoded_independently": True,
            "xenos_tile_endian_implemented_independently": True,
            "copied_archive_reparsed": True,
            "contains_game_or_replacement_bytes": False,
            "runtime_visibility_proved": False,
            "hardware_fidelity_proved": False,
        },
    }


def write_artifact_dir(path: Path, report: dict[str, object]) -> Path:
    """Exclusively create one canonical metadata-only verification receipt."""

    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise VerifyError(
            f"APF digital_font artifact parent is missing: {requested.parent}"
        ) from exc
    require(
        stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
        "APF digital_font artifact parent must be a non-symlink directory",
    )
    try:
        os.mkdir(requested, 0o755)
    except FileExistsError as exc:
        raise VerifyError(
            f"APF digital_font artifact directory already exists: {requested}"
        ) from exc
    report_path = requested / "verification.json"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            report_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            require(written > 0, "short APF digital_font artifact write")
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
                "alpha_sha256": recipe["alpha_sha256"],
                "field_scorebug_only_proved": False,
                "png_dimensions": [128, 128],
                "png_mode": "RGBA",
                "png_rgb_solid_white": True,
                "png_sha256": recipe["png_sha256"],
                "png_size": recipe["png_size"],
                "production_dxt5a_encoder_ready": False,
                "recipe_valid": True,
                "runtime_visibility_proved": False,
                "schema": RECIPE_SCHEMA,
                "scope": RECIPE_SCOPE,
                "stored_channel": RECIPE_STORED_CHANNEL,
                "target": RECIPE_TARGET,
            }, sort_keys=True))
            return 0
        if not legacy:
            recipe = load_recipe(args.recipe)
            report = verify(
                args.source_0a,
                args.output_0a,
                args.manifest,
                recipe["png"],  # type: ignore[arg-type]
            )
            report["recipe"] = {
                "schema": RECIPE_SCHEMA,
                "target": RECIPE_TARGET,
                "scope": RECIPE_SCOPE,
                "stored_channel": RECIPE_STORED_CHANNEL,
                "sha256": recipe["sha256"],
                "png_sha256": recipe["png_sha256"],
                "alpha_sha256": recipe["alpha_sha256"],
            }
            report["scope_boundary"] = {
                "shared_global_ui_texture": True,
                "field_scorebug_only_proved": False,
                "global_ui_consumers_mapped": False,
                "runtime_visibility_proved": False,
                "production_dxt5a_encoder_ready": False,
            }
            report_path = write_artifact_dir(args.artifact_dir, report)
            print(
                "APF_DIGITAL_FONT_VERIFY_PASS outer=1310 inner=246 parts=751 "
                f"blocks={report['target']['changed_dxt5a_block_count']} "
                f"global=true runtime=false report={report_path}"
            )
            return 0
        report = verify(args.source_volume, args.output_volume, args.manifest, args.png)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "APF_DIGITAL_FONT_VERIFY_PASS outer=1310 inner=246 parts=751 "
            f"blocks={report['target']['changed_dxt5a_block_count']} runtime=false"
        )
    except (
        VerifyError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
