#!/usr/bin/env python3
"""Copy-only writer for APF 2K8 jersey-number TXTR packages.

``uniform_number_00.iff`` through ``uniform_number_23.iff`` each hold the ten
digit colour maps and their DXN normals.  All twenty textures share one outer
allocation, so a staged set is encoded together and the remaining budget is
computed for that package, not per digit.

Colour routes through the proved DXT1 path.  Normals route through
``apf_helmet_color_transport.encode_dxn``.  Contracts come from the live TXTR
descriptor, cross-checked against the retail-free catalog.  H7A is rebuilt
with retail-token preservation.  The retail source is never opened for
writing.  This module makes no in-game visibility claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import re
import stat
import struct
import sys
import zlib
from typing import Iterable, Mapping

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from io import BytesIO

from PIL import Image, UnidentifiedImageError, __version__ as PILLOW_VERSION

import apf_helmet_color_transport as dxn_transport
import apf_inner
import apf_outer
import apf_pants_color_transport as dxt1_transport
import apf_texture_patch as archive_patch
import apf_xenos_bc1_mip_layout as bc1_mips
import apf_xenos_dxn_mip_layout as dxn_mips


SCHEMA = "apf_number_texture_patch/v1"
CATALOG_SCHEMA = "apf2k8_number_targets/v1"
CATALOG_PATH = _ROOT / "mod_editor" / "data" / "apf2k8_number_targets.v1.json"
CATALOG_SHA256 = "8c420e390c50e05720c02b66d0c650e7dc45f09481f35e104eec3d9acb649bec"
SOURCE_0A_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_0A_SIZE = 1_140_850_688
NON_RETAIL_0A = (
    "source 0A is not the pinned retail volume; "
    "copied or studio-built 0A cannot be used as a number-writer source"
)
EXTRACTED_0A = _ROOT / "extracted" / "All-Pro Football 2K8 (USA)" / "0A"
STORAGE_GAME_DIR = Path(
    "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)"
)
GAME_DIR_ENV = "APF_2K8_GAME_DIR"
GAME_0A_ENV = "APF_2K8_0A"
SELECTOR_SLOT = 8
SLOT_COUNT = 24
TEXTURES_PER_SLOT = 20
PACKAGE_TEMPLATE = "uniform_number_{0:02d}.iff"
DIGIT_NAME_RE = re.compile(r"^number_([0-9])_(color|normal)$")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_NAME_ID_RE = re.compile(r"0x[0-9a-f]{8}")
MAX_PNG_BYTES = 32 * 1024 * 1024
NUMBER_FONT_NAME = "uniform"


class NumberPatchError(ValueError):
    """Raised when a number catalog, PNG, or fixed-allocation rebuild is unsafe."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def require_retail_0a(index_path: Path) -> str:
    """Refuse copied or studio-built 0A. Writers compile from retail pins."""

    path = Path(index_path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise NumberPatchError(f"cannot inspect source 0A: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise NumberPatchError("source 0A must be a regular, non-symlink file")
    if info.st_size != EXPECTED_0A_SIZE:
        raise NumberPatchError(NON_RETAIL_0A)
    digest = _sha256_file(path)
    if digest != SOURCE_0A_SHA256:
        raise NumberPatchError(NON_RETAIL_0A)
    return digest


def _outer_name(slot_index: int) -> str:
    return PACKAGE_TEMPLATE.format(slot_index)


def _outer_name_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF


def _hex_id(value: int) -> str:
    return f"0x{value:08x}"


def resolve_game_0a(game_dir: Path | None = None) -> Path:
    """Resolve a user-owned 0A. Never require a symlink into extracted/."""

    if game_dir is not None:
        candidate = Path(game_dir)
        if candidate.name == "0A" and candidate.is_file():
            return candidate
        return candidate / "0A"
    env_0a = os.environ.get(GAME_0A_ENV)
    if env_0a:
        return Path(env_0a)
    env_dir = os.environ.get(GAME_DIR_ENV)
    if env_dir:
        return Path(env_dir) / "0A"
    if EXTRACTED_0A.is_file():
        return EXTRACTED_0A
    storage = STORAGE_GAME_DIR / "0A"
    if storage.is_file():
        return storage
    raise NumberPatchError(
        "APF 0A not found. Pass --game-dir or set "
        f"{GAME_DIR_ENV} / {GAME_0A_ENV}. Do not symlink the retail dump "
        "into extracted/ — stadium writers refuse symlink game paths."
    )


def overflow_target(
    digits: Iterable[str],
    *,
    entry_index: int,
    slot_index: int | None = None,
    outer_name: str | None = None,
) -> str:
    """Name the staged digit(s) and the package in the Beta 39 overflow form."""

    names = [str(name) for name in digits]
    if not names:
        names = ["number_*"]
    label = "+".join(names)
    package = outer_name or (
        _outer_name(slot_index) if slot_index is not None else f"outer {entry_index}"
    )
    return f"{label} in package {entry_index} ({package})"


def raise_package_overflow(
    *,
    digits: Iterable[str],
    entry_index: int,
    overflow_bytes: int,
    allocation_size: int,
    budget_bytes: int,
    retail_bytes: int,
    slot_index: int | None = None,
    outer_name: str | None = None,
) -> None:
    """Refuse a package rebuild that no longer fits its fixed allocation."""

    raise archive_patch.allocation_overflow(
        target=overflow_target(
            digits,
            entry_index=entry_index,
            slot_index=slot_index,
            outer_name=outer_name,
        ),
        overflow_bytes=overflow_bytes,
        allocation_size=allocation_size,
        budget_bytes=budget_bytes,
        retail_bytes=retail_bytes,
        advice=(
            "Jersey digits are DXT1 colour / DXN normal textures that share "
            "one package budget, not region masks. Flatten or crop the "
            "digit so the token-preserving H7A rebuild still fits, or stage "
            "fewer digits in this package."
        ),
    )


def package_capacity(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_stored: list[bytes],
) -> dict[str, int]:
    """Compressed VRAM budget shared by every digit in this outer package.

    ``file_length_slack_bytes`` still includes the name footer.
    ``remaining_bytes`` is the usable compressed slack after that footer.
    """

    if record.footer is None:
        raise NumberPatchError("number package IFF has no name footer")
    if len(original_stored) != 2:
        raise NumberPatchError("number package must have DRAM + VRAM H7A blocks")
    footer_total = 8 + record.footer.payload_size
    fixed = record.header_size + len(original_stored[0]) + footer_total
    budget = entry.size - fixed
    retail = len(original_stored[1])
    return {
        "allocation_size": entry.size,
        "file_length": record.file_length,
        "file_length_slack_bytes": entry.size - record.file_length,
        "footer_total": footer_total,
        "compressed_budget_bytes": budget,
        "retail_compressed_bytes": retail,
        "remaining_bytes": budget - retail,
    }


def _strict_json(payload: bytes) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise NumberPatchError(f"number catalog repeats {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(payload, object_pairs_hook=reject_duplicates)
    except NumberPatchError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NumberPatchError(f"number catalog is invalid JSON: {exc}") from exc


def _validate_row(row: object, ordinal: int) -> dict[str, object]:
    if not isinstance(row, dict):
        raise NumberPatchError(f"number target {ordinal} is not an object")
    expected = {
        "slot_index",
        "outer_name",
        "outer_name_id",
        "entry_index",
        "file_index",
        "name",
        "format",
        "codec",
        "width",
        "height",
        "pitch_pixels",
        "endianness",
        "swizzle",
        "base_len",
        "mip_len",
        "head_len",
        "part_layout",
        "entry_size",
        "entry_sha256",
        "base_sha256",
    }
    if set(row) != expected:
        raise NumberPatchError(f"number target {ordinal} has unexpected fields")
    slot_index = row["slot_index"]
    if type(slot_index) is not int or not 0 <= slot_index < SLOT_COUNT:
        raise NumberPatchError(f"number target {ordinal} has an invalid slot")
    if row["outer_name"] != _outer_name(slot_index):
        raise NumberPatchError(f"number target {ordinal} has the wrong package name")
    name_id = row["outer_name_id"]
    if not isinstance(name_id, str) or _NAME_ID_RE.fullmatch(name_id) is None:
        raise NumberPatchError(f"number target {ordinal} has an invalid name ID")
    if int(name_id, 16) != _outer_name_id(str(row["outer_name"])):
        raise NumberPatchError(f"number target {ordinal} name ID does not match its name")
    entry_index = row["entry_index"]
    if type(entry_index) is not int or not 0 <= entry_index < 1543:
        raise NumberPatchError(f"number target {ordinal} has an invalid outer index")
    file_index = row["file_index"]
    if type(file_index) is not int or not 0 <= file_index < 32:
        raise NumberPatchError(f"number target {ordinal} has an invalid file index")
    name = row["name"]
    match = DIGIT_NAME_RE.fullmatch(str(name)) if isinstance(name, str) else None
    if match is None:
        raise NumberPatchError(f"number target {ordinal} has an invalid digit name")
    kind = match.group(2)
    codec = row["codec"]
    fmt = row["format"]
    if kind == "color":
        if codec != "dxt1" or fmt != 18:
            raise NumberPatchError(f"{name} is not DXT1 format 18")
        if row["base_len"] != 131072 or row["mip_len"] != 65536:
            raise NumberPatchError(f"{name} DXT1 sizes left the derived class")
    else:
        if codec != "dxn" or fmt != 49:
            raise NumberPatchError(f"{name} is not DXN format 49")
        if row["base_len"] != 262144 or row["mip_len"] != 131072:
            raise NumberPatchError(f"{name} DXN sizes left the derived class")
    if (
        row["width"] != 512
        or row["height"] != 512
        or row["pitch_pixels"] != 512
        or row["endianness"] != 1
        or row["part_layout"] != "dram_vram"
        or row["head_len"] != 0
        or not isinstance(row["swizzle"], list)
        or row["swizzle"] != [0, 1, 2, 3]
    ):
        raise NumberPatchError(f"{name} descriptor pins left the derived class")
    if type(row["entry_size"]) is not int or row["entry_size"] <= 0:
        raise NumberPatchError(f"number target {ordinal} has an invalid allocation size")
    for key in ("entry_sha256", "base_sha256"):
        digest = row[key]
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise NumberPatchError(f"number target {ordinal} has an invalid {key}")
    return row


@lru_cache(maxsize=1)
def load_targets() -> tuple[dict[str, object], ...]:
    """Load the retail-free 24×20 number catalog."""

    payload = CATALOG_PATH.read_bytes()
    if _sha256(payload) != CATALOG_SHA256:
        raise NumberPatchError("number target catalog changed")
    document = _strict_json(payload)
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "game",
        "source_0a_sha256",
        "purpose",
        "selector_slot",
        "slot_outers",
        "textures",
    }:
        raise NumberPatchError("number target catalog has unexpected fields")
    if (
        document["schema"] != CATALOG_SCHEMA
        or document["game"] != "apf2k8_xbox360_usa"
        or document["source_0a_sha256"] != SOURCE_0A_SHA256
        or document["selector_slot"] != SELECTOR_SLOT
    ):
        raise NumberPatchError("number target catalog identity changed")
    slot_outers = document["slot_outers"]
    if (
        not isinstance(slot_outers, list)
        or len(slot_outers) != SLOT_COUNT
        or any(type(value) is not int for value in slot_outers)
    ):
        raise NumberPatchError("number slot roster changed")
    rows = document["textures"]
    if not isinstance(rows, list) or len(rows) != SLOT_COUNT * TEXTURES_PER_SLOT:
        raise NumberPatchError("number target catalog is not 24 packages × 20 textures")
    validated = tuple(_validate_row(row, index) for index, row in enumerate(rows))
    by_slot: dict[int, list[dict[str, object]]] = {index: [] for index in range(SLOT_COUNT)}
    seen_locations: set[tuple[int, int]] = set()
    for row in validated:
        slot = int(row["slot_index"])
        if int(row["entry_index"]) != int(slot_outers[slot]):
            raise NumberPatchError(f"slot {slot} no longer maps to its outer package")
        key = (int(row["entry_index"]), int(row["file_index"]))
        if key in seen_locations:
            raise NumberPatchError(f"duplicate number location {key}")
        seen_locations.add(key)
        by_slot[slot].append(row)
    for slot, group in by_slot.items():
        if len(group) != TEXTURES_PER_SLOT:
            raise NumberPatchError(f"slot {slot} no longer has 20 number textures")
        names = {str(row["name"]) for row in group}
        expected = {
            f"number_{digit}_{kind}"
            for digit in range(10)
            for kind in ("color", "normal")
        }
        if names != expected:
            raise NumberPatchError(f"slot {slot} is missing a digit texture")
    return validated


def targets_for_slot(slot_index: int) -> tuple[dict[str, object], ...]:
    if type(slot_index) is not int or not 0 <= slot_index < SLOT_COUNT:
        raise NumberPatchError("number slot index must be in 0..23")
    return tuple(row for row in load_targets() if int(row["slot_index"]) == slot_index)


@lru_cache(maxsize=1)
def _location_index() -> dict[tuple[int, int], dict[str, object]]:
    return {
        (int(row["entry_index"]), int(row["file_index"])): row
        for row in load_targets()
    }


def target_by_location(
    entry_index: int, file_index: int, name: str | None = None
) -> dict[str, object]:
    try:
        row = _location_index()[(entry_index, file_index)]
    except KeyError as exc:
        raise NumberPatchError(
            f"({entry_index}, {file_index}) is not a catalogued jersey-number TXTR"
        ) from exc
    if name is not None and str(row["name"]) != name:
        raise NumberPatchError(
            f"number location {entry_index}/{file_index} is {row['name']}, not {name}"
        )
    return row


def lookup_target(
    entry_index: int, file_index: int, name: str | None = None
) -> dict[str, object] | None:
    try:
        return target_by_location(entry_index, file_index, name)
    except NumberPatchError:
        return None


def _codec_from_format(fmt: int) -> str:
    if fmt == 18:
        return "dxt1"
    if fmt == 49:
        return "dxn"
    raise NumberPatchError(f"unsupported number TXTR format {fmt}")


def _row_from_live(
    *,
    slot_index: int,
    outer_name: str,
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    entry_bytes: bytes,
    blocks: list[bytes],
    target: apf_inner.DataFile,
) -> dict[str, object]:
    if target.type_name != "TXTR" or len(target.parts) != 2:
        raise NumberPatchError(f"{target.name} is not a two-part TXTR")
    descriptor = blocks[target.parts[0].block_index][
        target.parts[0].offset : target.parts[0].offset + target.parts[0].length
    ]
    metadata = apf_inner.parse_txtr_metadata(descriptor)
    fmt = int(metadata["format"])
    codec = _codec_from_format(fmt)
    base_len = int(metadata["vc_base_data_length"])
    mip_len = int(metadata["vc_mip_data_length"])
    pixel = blocks[target.parts[1].block_index][
        target.parts[1].offset : target.parts[1].offset + target.parts[1].length
    ]
    head_len = len(pixel) - base_len - mip_len
    if head_len < 0:
        raise NumberPatchError(f"{target.name} pixel part is shorter than its mips")
    swizzle = [int(value) for value in metadata["swizzle_components"]]  # type: ignore[index]
    return {
        "slot_index": slot_index,
        "outer_name": outer_name,
        "outer_name_id": _hex_id(entry.name_id),
        "entry_index": entry.table_index,
        "file_index": target.index,
        "name": target.name,
        "format": fmt,
        "codec": codec,
        "width": int(metadata["width"]),
        "height": int(metadata["height"]),
        "pitch_pixels": int(metadata["pitch_pixels"]),
        "endianness": int(metadata["endianness"]),
        "swizzle": swizzle,
        "base_len": base_len,
        "mip_len": mip_len,
        "head_len": head_len,
        "part_layout": "dram_vram",
        "entry_size": entry.size,
        "entry_sha256": _sha256(entry_bytes),
        "base_sha256": _sha256(pixel[head_len : head_len + base_len]),
    }


def generate_catalog(index_path: Path) -> dict[str, object]:
    """Derive the 24×20 catalog from a retail 0A. No payloads are stored."""

    index_path = Path(index_path)
    require_retail_0a(index_path)
    archive = apf_outer.parse_archive(index_path)
    by_name_id = {entry.name_id: entry for entry in archive.entries}
    slot_outers: list[int] = []
    textures: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for slot_index in range(SLOT_COUNT):
            outer_name = _outer_name(slot_index)
            try:
                entry = by_name_id[_outer_name_id(outer_name)]
            except KeyError as exc:
                raise NumberPatchError(f"retail 0A has no {outer_name}") from exc
            record = apf_inner.parse_iff(reader, entry)
            entry_bytes = reader.read(entry, 0, entry.size)
            blocks = [
                apf_inner.decode_block(reader, record, index, 1 << 30)
                for index in range(record.block_count)
            ]
            number_files = [
                item
                for item in record.files
                if DIGIT_NAME_RE.fullmatch(item.name or "") and item.type_name == "TXTR"
            ]
            if len(number_files) != TEXTURES_PER_SLOT:
                raise NumberPatchError(
                    f"{outer_name} has {len(number_files)} number TXTRs, not 20"
                )
            slot_outers.append(entry.table_index)
            for item in number_files:
                textures.append(
                    _row_from_live(
                        slot_index=slot_index,
                        outer_name=outer_name,
                        entry=entry,
                        record=record,
                        entry_bytes=entry_bytes,
                        blocks=blocks,
                        target=item,
                    )
                )
    if len(textures) != SLOT_COUNT * TEXTURES_PER_SLOT:
        raise NumberPatchError("generated number catalog is not 24×20")
    return {
        "schema": CATALOG_SCHEMA,
        "game": "apf2k8_xbox360_usa",
        "source_0a_sha256": SOURCE_0A_SHA256,
        "purpose": "Derived number TXTR contracts. Hashes and sizes only. No payloads.",
        "selector_slot": SELECTOR_SLOT,
        "slot_outers": slot_outers,
        "textures": textures,
    }


def write_catalog(document: Mapping[str, object], destination: Path) -> str:
    payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return _sha256(payload)


def _validate_descriptor(row: Mapping[str, object], metadata: Mapping[str, object]) -> None:
    required = {
        "format": int(row["format"]),
        "width": int(row["width"]),
        "height": int(row["height"]),
        "pitch_pixels": int(row["pitch_pixels"]),
        "endianness": int(row["endianness"]),
        "tiled": True,
        "stacked": False,
        "dimension": 1,
        "packed_mips": True,
        "mip_min_level": 0,
        "vc_base_data_length": int(row["base_len"]),
        "vc_mip_data_length": int(row["mip_len"]),
    }
    disagreements = {
        key: (metadata.get(key), value)
        for key, value in required.items()
        if metadata.get(key) != value
    }
    if disagreements:
        raise NumberPatchError(
            f"PORTME: {row['name']} descriptor changed: {disagreements}"
        )
    if list(metadata["swizzle_components"]) != list(row["swizzle"]):  # type: ignore[index]
        raise NumberPatchError(f"PORTME: {row['name']} swizzle changed")


def _load_png(path: Path, row: Mapping[str, object]) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NumberPatchError(f"cannot inspect number PNG: {exc}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= MAX_PNG_BYTES
    ):
        raise NumberPatchError("number PNG must be a private regular file under 32 MiB")
    payload = path.read_bytes()
    try:
        after = path.lstat()
    except OSError as exc:
        raise NumberPatchError(f"cannot recheck number PNG: {exc}") from exc
    if (
        len(payload) != info.st_size
        or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    ):
        raise NumberPatchError("number PNG changed while being read")
    width = int(row["width"])
    height = int(row["height"])
    try:
        with Image.open(BytesIO(payload)) as image:
            image.load()
            if image.format != "PNG" or image.size != (width, height):
                raise NumberPatchError(
                    f"{row['name']} input must be an exact {width}x{height} RGBA PNG"
                )
            rgba = image.convert("RGBA").tobytes()
    except NumberPatchError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise NumberPatchError(f"cannot decode number PNG: {exc}") from exc
    if str(row["codec"]) == "dxn":
        pixels = bytearray(rgba)
        for offset in range(0, len(pixels), 4):
            pixels[offset + 2] = 0
            pixels[offset + 3] = 255
        return bytes(pixels)
    # Colour digits are punch-through DXT1 (alpha 0 or 255). Flattening
    # would force a full re-encode of retail art and overflow the package.
    return rgba


def _encode_color(original: bytes, metadata: Mapping[str, object], wanted: bytes) -> bytes:
    locations = bc1_mips.derive_layout(dict(metadata))
    if bc1_mips.transport_roundtrip(original, locations) != original:
        raise NumberPatchError("retail number DXT1 transport is not bit-exact")
    base = locations[0]
    original_linear = bc1_mips.extract_linear_bc1(original, base)
    original_rgba = dxt1_transport.decode_linear_bc1(original_linear, base)
    if wanted == original_rgba:
        return original
    encoded, indices, _info = dxt1_transport._encode_changed_blocks(
        original_linear, original_rgba, wanted, base
    )
    if not indices:
        raise NumberPatchError("changed number colour PNG produced no DXT1 base edit")
    new_texture = bc1_mips.insert_linear_bc1(original, base, encoded)
    if new_texture[int(metadata["vc_base_data_length"]) :] != original[
        int(metadata["vc_base_data_length"]) :
    ]:
        raise NumberPatchError("number DXT1 mip tail was not preserved")
    return new_texture


def _encode_normal(original: bytes, metadata: Mapping[str, object], wanted: bytes) -> bytes:
    locations = dxn_mips.derive_layout(dict(metadata))
    if dxn_mips.transport_roundtrip(original, locations) != original:
        raise NumberPatchError("retail number DXN transport is not bit-exact")
    base = locations[0]
    original_linear = dxn_mips.extract_linear_dxn(original, base)
    original_rgba = dxn_transport.decode_linear_dxn(original_linear, base)
    if wanted == original_rgba:
        return original
    encoded, indices, _info = dxn_transport._encode_changed_blocks(
        original_linear, original_rgba, wanted, base
    )
    if not indices:
        raise NumberPatchError("changed number normal PNG produced no DXN base edit")
    new_texture = dxn_mips.insert_linear_dxn(original, base, encoded)
    if new_texture[int(metadata["vc_base_data_length"]) :] != original[
        int(metadata["vc_base_data_length"]) :
    ]:
        raise NumberPatchError("number DXN mip tail was not preserved")
    return new_texture


def _choose_h7a(
    original_stored: bytes,
    original_decoded: bytes,
    changed_decoded: bytes,
    shift: int,
) -> tuple[bytes, dict[str, object]]:
    retail_payload = original_stored[apf_inner.H7A_HEADER_SIZE :]
    preserved, preserve_report = apf_inner.encode_h7a_preserving_tokens(
        retail_payload, original_decoded, changed_decoded, shift
    )
    if apf_inner.decompress_h7a(preserved, len(changed_decoded), shift) != changed_decoded:
        raise NumberPatchError("number H7A encode/decode round-trip failed")
    return preserved, {
        "selected_mode": "retail_token_preserving",
        "selected_payload_length": len(preserved),
        "selected_report": dict(preserve_report),
    }


def _read_package(
    index_path: Path, entry_index: int
) -> tuple[
    apf_outer.Archive,
    apf_outer.Entry,
    apf_inner.IFFRecord,
    bytes,
    list[bytes],
    list[bytes],
]:
    archive = apf_outer.parse_archive(index_path)
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise NumberPatchError(f"outer archive has no entry {entry_index}") from exc
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise NumberPatchError("number package no longer resolves to one 0A range")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        decoded = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if record.block_count != 2 or record.warnings or record.footer is None:
        raise NumberPatchError("number package IFF structure changed")
    font = [item for item in record.files if item.name == NUMBER_FONT_NAME]
    if len(font) != 1 or font[0].type_name != "NumberFont":
        raise NumberPatchError("number package NumberFont sibling moved")
    return archive, entry, record, original_entry, decoded, stored


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_vram: bytes,
    changed_rows: tuple[Mapping[str, object], ...],
    overflow_rows: tuple[Mapping[str, object], ...],
) -> tuple[bytes, dict[str, object]]:
    if new_vram == original_blocks[1]:
        footer_total = 8 + record.footer.payload_size if record.footer is not None else 0
        return original_entry, {
            "allocation_size": entry.size,
            "file_length_before": record.file_length,
            "file_length_after": record.file_length,
            "allocation_slack_after": entry.size - record.file_length - footer_total,
            "mode": "no_op",
            "changed_inner_parts": [],
        }
    descriptor = record.blocks[1]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise NumberPatchError("number VRAM block is not H7A-compressed")
    compressed, compression = _choose_h7a(
        original_stored[1], original_blocks[1], new_vram, descriptor.wrapper.shift
    )
    new_stored = [
        original_stored[0],
        struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_vram),
            apf_inner.H7A_HEADER_SIZE + len(compressed),
            descriptor.unknown_10,
            descriptor.wrapper.shift,
        )
        + compressed,
    ]
    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    blocks: list[dict[str, object]] = []
    for index, (old, stored) in enumerate(zip(record.blocks, new_stored)):
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            old.name_hash,
            old.type_hash,
            old.unknown_08,
            old.uncompressed_length,
            old.unknown_10,
            cursor,
            len(stored),
            old.indexed,
        )
        body.extend(stored)
        blocks.append(
            {
                "index": index,
                "stored_length_before": len(original_stored[index]),
                "stored_length_after": len(stored),
                "decoded_sha256_before": _sha256(original_blocks[index]),
                "decoded_sha256_after": _sha256(
                    original_blocks[0] if index == 0 else new_vram
                ),
            }
        )
        cursor += len(stored)
    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise NumberPatchError("number package IFF has no validated footer")
    footer_total = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_total]
    tail = original_entry[record.file_length + footer_total :]
    if any(tail):
        raise NumberPatchError("number package fixed-allocation tail is not zero")
    active = bytes(header) + bytes(body) + footer
    capacity = package_capacity(entry, record, original_stored)
    if len(active) > entry.size:
        label_rows = overflow_rows or changed_rows
        raise_package_overflow(
            digits=(str(row["name"]) for row in label_rows),
            entry_index=entry.table_index,
            overflow_bytes=len(active) - entry.size,
            allocation_size=entry.size,
            budget_bytes=capacity["compressed_budget_bytes"],
            retail_bytes=capacity["retail_compressed_bytes"],
            slot_index=int(label_rows[0]["slot_index"]) if label_rows else None,
            outer_name=str(label_rows[0]["outer_name"]) if label_rows else None,
        )
    rebuilt = active + bytes(entry.size - len(active))
    memory = archive_patch.BytesReader(rebuilt)
    reopened = apf_inner.parse_iff(memory, entry)
    reopened_blocks = [
        apf_inner.decode_block(memory, reopened, index, 1 << 30)
        for index in range(reopened.block_count)
    ]
    if reopened_blocks != [original_blocks[0], new_vram]:
        raise NumberPatchError("rebuilt number IFF did not reopen as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)
    after_parts = archive_patch._file_part_hashes(reopened, reopened_blocks)
    expected = sorted((int(row["file_index"]), 1) for row in changed_rows)
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if sorted(changed_parts) != expected:
        raise NumberPatchError(
            f"unexpected number inner parts changed: {changed_parts} (expected {expected})"
        )
    changed_files = {int(row["file_index"]) for row in changed_rows}
    for file in record.files:
        if file.name == NUMBER_FONT_NAME:
            if before_parts[(file.index, 0)] != after_parts[(file.index, 0)]:
                raise NumberPatchError("NumberFont sibling was not preserved")
        elif file.index not in changed_files:
            for part_index, _part in enumerate(file.parts):
                if before_parts[(file.index, part_index)] != after_parts[(file.index, part_index)]:
                    raise NumberPatchError(
                        f"unstaged sibling {file.name} part {part_index} changed"
                    )
    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_after": entry.size - len(active),
        "capacity": capacity,
        "remaining_package_budget_bytes": entry.size - len(active),
        "h7a_shift": descriptor.wrapper.shift,
        "h7a_decode_encode_decode_exact": True,
        "footer_bit_exact": rebuilt[new_file_length : new_file_length + footer_total]
        == footer,
        "dram_block_preserved": reopened_blocks[0] == original_blocks[0],
        "changed_inner_parts": [
            {
                "file_index": int(row["file_index"]),
                "part_index": 1,
                "block_index": 1,
                "name": row["name"],
            }
            for row in changed_rows
        ],
        "blocks": blocks,
        "compression": compression,
        "rebuilt_iff_reparsed": True,
        "mode": "patched",
    }


def _resolve_replacements(
    entry_index: int,
    replacements: Mapping[object, Path],
) -> tuple[dict[str, object], ...]:
    catalog = load_targets()
    package_rows = [row for row in catalog if int(row["entry_index"]) == entry_index]
    if len(package_rows) != TEXTURES_PER_SLOT:
        raise NumberPatchError(f"package {entry_index} is not a 20-texture number slot")
    by_name = {str(row["name"]): row for row in package_rows}
    by_file = {int(row["file_index"]): row for row in package_rows}
    resolved: dict[int, dict[str, object]] = {}
    for key, png in replacements.items():
        if isinstance(key, str):
            try:
                row = by_name[key]
            except KeyError as exc:
                raise NumberPatchError(
                    f"{key} is not a number texture in package {entry_index}"
                ) from exc
        elif type(key) is int:
            try:
                row = by_file[key]
            except KeyError as exc:
                raise NumberPatchError(
                    f"file {key} is not a number texture in package {entry_index}"
                ) from exc
        else:
            raise NumberPatchError("number replacement keys must be digit names or file indexes")
        file_index = int(row["file_index"])
        if file_index in resolved:
            raise NumberPatchError(f"{row['name']} was staged more than once")
        resolved[file_index] = {**row, "png_path": Path(png)}
    if not resolved:
        raise NumberPatchError("at least one jersey digit must be staged")
    return tuple(resolved[key] for key in sorted(resolved))


def build_package_patch(
    index_path: Path,
    entry_index: int,
    replacements: Mapping[object, Path],
) -> archive_patch.PatchResult:
    """Encode every staged digit in one package and rebuild the shared IFF."""

    index_path = Path(index_path)
    source_digest = require_retail_0a(index_path)
    staged = _resolve_replacements(entry_index, replacements)
    _archive, entry, record, original_entry, blocks, stored = _read_package(
        index_path, entry_index
    )
    first = staged[0]
    if _sha256(original_entry) != first["entry_sha256"] or entry.size != int(first["entry_size"]):
        raise NumberPatchError("source number package differs from its retail pin")
    if entry.name_id != int(str(first["outer_name_id"]), 16):
        raise NumberPatchError("number package name ID no longer matches the catalog")
    new_vram = bytearray(blocks[1])
    encoded_rows: list[Mapping[str, object]] = []
    for row in staged:
        try:
            target = record.files[int(row["file_index"])]
        except IndexError as exc:
            raise NumberPatchError(f"IFF has no inner file {row['file_index']}") from exc
        if target.name != row["name"] or target.type_name != "TXTR" or len(target.parts) != 2:
            raise NumberPatchError(f"{row['name']} inner identity changed")
        descriptor = blocks[target.parts[0].block_index][
            target.parts[0].offset : target.parts[0].offset + target.parts[0].length
        ]
        metadata = apf_inner.parse_txtr_metadata(descriptor)
        _validate_descriptor(row, metadata)
        pixel_part = target.parts[1]
        if pixel_part.block_index != 1:
            raise NumberPatchError(f"{row['name']} VRAM is no longer in the shared block")
        original_pixel = blocks[1][pixel_part.offset : pixel_part.offset + pixel_part.length]
        head = int(row["head_len"])
        base = original_pixel[head : head + int(row["base_len"])]
        if _sha256(base) != row["base_sha256"]:
            raise NumberPatchError(f"source {row['name']} differs from its retail pin")
        wanted = _load_png(Path(row["png_path"]), row)  # type: ignore[arg-type]
        if str(row["codec"]) == "dxt1":
            encoded = _encode_color(original_pixel, metadata, wanted)
        else:
            encoded = _encode_normal(original_pixel, metadata, wanted)
        if encoded != original_pixel:
            new_vram[pixel_part.offset : pixel_part.offset + pixel_part.length] = encoded
            encoded_rows.append(row)
    rebuilt, iff = _rebuild_entry(
        entry,
        record,
        original_entry,
        blocks,
        stored,
        bytes(new_vram),
        tuple(encoded_rows),
        staged,
    )
    mode = "no_op" if rebuilt == original_entry else "patched"
    if mode == "no_op":
        iff = dict(iff)
        iff["changed_inner_parts"] = []
    return archive_patch.PatchResult(
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": mode,
            "source": {
                "archive_index": str(index_path),
                "physical_volume": "0A",
                "outer_entry_index": entry_index,
                "outer_name": first["outer_name"],
                "slot_index": first["slot_index"],
                "entry_sha256": _sha256(original_entry),
                "source_0a_sha256": source_digest,
                "source_opened_read_only": True,
            },
            "staged_digits": [str(row["name"]) for row in staged],
            "package_budget": package_capacity(entry, record, stored),
            "remaining_package_budget_bytes": iff.get(
                "remaining_package_budget_bytes",
                package_capacity(entry, record, stored)["remaining_bytes"],
            ),
            "iff": iff,
            "validation": {
                "sibling_parts_byte_identical": True,
                "number_font_preserved": True,
                "h7a_token_preserving": mode == "patched",
                "rebuilt_iff_reparsed": True,
                "source_opened_read_only": True,
                "runtime_visibility_claimed": False,
            },
            "backend": {
                "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
                "dxt1": "apf_field_art_patch / pants DXT1 touched-block path",
                "dxn": "apf_helmet_color_transport.encode_dxn",
                "h7a": "retail-token-preserving",
            },
            "runtime_boundary": (
                "Package ownership and transport are offline-proved. Runtime "
                "visibility is not claimed."
            ),
        },
    )


def build_patch(
    index_path: Path,
    png_path: Path,
    entry_index: int,
    file_index: int,
) -> archive_patch.PatchResult:
    """Stage one digit in its package. Other digits stay retail."""

    row = target_by_location(entry_index, file_index)
    return build_package_patch(index_path, entry_index, {str(row["name"]): png_path})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-dir",
        type=Path,
        help="APF game directory containing 0A (do not symlink into extracted/)",
    )
    parser.add_argument("--index", type=Path, help="user-owned retail APF 0A")
    parser.add_argument("--entry-index", type=int, help="outer table index")
    parser.add_argument("--file-index", type=int, help="inner number TXTR index")
    parser.add_argument("--digit", help="digit name such as number_3_color")
    parser.add_argument("--png", type=Path, help="exact 512x512 RGBA PNG")
    parser.add_argument("--output-entry", type=Path, help="new rebuilt logical IFF")
    parser.add_argument("--output-volume", type=Path, help="new copied 0A")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--generate-catalog",
        action="store_true",
        help="derive the retail-free catalog from the disc and write it",
    )
    parser.add_argument("--catalog-output", type=Path, default=CATALOG_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        index_path = (
            args.index.expanduser()
            if args.index
            else resolve_game_0a(args.game_dir)
        )
        if args.generate_catalog:
            document = generate_catalog(index_path)
            digest = write_catalog(document, args.catalog_output.expanduser())
            print(
                "APF_NUMBER_CATALOG_PASS "
                f"slots={len(document['slot_outers'])} "
                f"textures={len(document['textures'])} sha256={digest}"
            )
            return 0
        if args.entry_index is None or args.png is None or args.manifest is None:
            raise NumberPatchError(
                "write mode needs --entry-index, --png, and --manifest "
                "(or pass --generate-catalog)"
            )
        if args.digit:
            replacements = {args.digit: args.png.expanduser()}
        elif args.file_index is not None:
            replacements = {args.file_index: args.png.expanduser()}
        else:
            raise NumberPatchError("pass --digit or --file-index")
        manifest_path = args.manifest.expanduser()
        output_entry = args.output_entry.expanduser() if args.output_entry else None
        output_volume = args.output_volume.expanduser() if args.output_volume else None
        archive_patch._preflight_output_paths(
            [index_path, args.png.expanduser()],
            [
                ("manifest", manifest_path),
                ("output entry", output_entry),
                ("output volume", output_volume),
            ],
        )
        reservation = archive_patch._reserve_new(manifest_path)
        try:
            result = build_package_patch(index_path, args.entry_index, replacements)
            document = result.manifest
            if output_entry is not None:
                archive_patch._write_new(output_entry, result.entry_bytes)
            if output_volume is not None:
                archive = apf_outer.parse_archive(index_path)
                document["copied_volume"] = archive_patch._write_copied_volume(
                    index_path,
                    output_volume,
                    archive.entries[args.entry_index],
                    result.entry_bytes,
                )
            archive_patch._commit_reserved(
                manifest_path,
                reservation,
                (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
            archive_patch._close_reserved(reservation)
        except Exception:
            archive_patch._abort_reserved(manifest_path, reservation)
            raise
        print(
            "APF_NUMBER_PATCH_PASS "
            f"mode={document['mode']} package={args.entry_index} "
            f"digits={','.join(document['staged_digits'])} "
            f"sha256={_sha256(result.entry_bytes)}"
        )
    except (
        NumberPatchError,
        bc1_mips.MipLayoutError,
        dxn_mips.MipLayoutError,
        archive_patch.PatchError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
