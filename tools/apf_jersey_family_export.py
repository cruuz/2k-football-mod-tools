#!/usr/bin/env python3
"""Read-only APF jersey exporter selected only by proved asset index.

The tool accepts a pinned retail ``0A`` and an asset index in ``0..23``.  The
catalog resolves every archive detail; callers cannot supply an outer entry,
inner file, offset, allocation, codec, or layout.  A successful export creates
one new directory containing an editable base PNG, previews for mip levels
0..8, and canonical provenance JSON.  It never writes a game/archive file.
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
import sys
from typing import Any

from PIL import Image, UnidentifiedImageError

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_inner  # noqa: E402
import apf_jersey_family_verify as verifier  # noqa: E402
import apf_xenos_mip_layout as xenos_mips  # noqa: E402


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read; Windows has no os.pread, so seek/read/restore there."""
    preader = getattr(os, "pread", None)
    if preader is not None:
        return preader(fd, count, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def _pwrite(fd: int, data: bytes, offset: int) -> int:
    """Positional write; Windows has no os.pwrite, so seek/write/restore there."""
    pwriter = getattr(os, "pwrite", None)
    if pwriter is not None:
        return pwriter(fd, data, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.write(fd, data)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


SCHEMA = "apf2k8_jersey_family_export/v1"
PROVENANCE_NAME = "provenance.json"
TEAM_TABLE = WORKSPACE / "reports/assets/apf_uniform_team_assets.tsv"
EXPECTED_TEAM_TABLE_SHA256 = (
    "d112710582b223d32425a79eedf321a2d9f61a01152c1c9d03b74f250231d82b"
)
EXPECTED_TEAM_TABLE_SIZE = 178_182
TEAM_TABLE_HEADER = (
    "team_index",
    "team_name",
    "abbreviation",
    "slot_kind",
    "bank",
    "selector_slot",
    "semantic_status",
    "families",
    "asset_index_byte_0",
    "package_names",
    "package_outer_table_indices",
    "selector_record_index",
    "selector_record_offset",
    "raw_record_hex",
    "opaque_bytes_1_7_hex",
)


class ExportError(ValueError):
    """Raised when a source, target, decode, or output gate fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExportError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class OutputFile:
    name: str
    payload: bytes


@dataclass(frozen=True)
class PreviewLevel:
    level: int
    width: int
    height: int
    packed_tail: bool
    origin_block_x: int
    origin_block_y: int
    linear_bc3_sha256: str
    rgba_sha256: str
    png_name: str
    png_sha256: str
    png: bytes

    def provenance(self) -> dict[str, object]:
        return {
            "level": self.level,
            "width": self.width,
            "height": self.height,
            "packed_tail": self.packed_tail,
            "origin_block_x": self.origin_block_x,
            "origin_block_y": self.origin_block_y,
            "linear_bc3_sha256": self.linear_bc3_sha256,
            "decoded_rgba_sha256": self.rgba_sha256,
            "png": self.png_name,
            "png_size": len(self.png),
            "png_sha256": self.png_sha256,
        }


@dataclass(frozen=True)
class ExportPlan:
    document: dict[str, Any]
    files: tuple[OutputFile, ...]


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    provenance: Path
    asset_index: int
    file_count: int


def _png_bytes(width: int, height: int, rgba: bytes) -> bytes:
    require(len(rgba) == width * height * 4, "decoded mip RGBA length changed")
    image = Image.frombytes("RGBA", (width, height), rgba)
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    payload = output.getvalue()
    try:
        with Image.open(io.BytesIO(payload)) as check:
            check.load()
            require(
                check.format == "PNG"
                and check.mode == "RGBA"
                and check.size == (width, height)
                and check.tobytes() == rgba,
                "generated preview PNG failed strict decode-back",
            )
    except (UnidentifiedImageError, OSError) as exc:
        raise ExportError(f"generated preview PNG cannot be decoded: {exc}") from exc
    return payload


def _preview_levels(
    row: dict[str, Any], decoded: dict[str, Any]
) -> tuple[PreviewLevel, ...]:
    metadata = decoded["metadata"]
    texture = decoded["texture"]
    locations = decoded["locations"]
    require(metadata == row["txtr_descriptor"],
            "decoded jersey TXTR descriptor differs from the pinned catalog")
    require(sha256(texture) == row["inner_file"]["texture_sha256"],
            "decoded jersey texture differs from the pinned catalog")
    require(len(locations) == 9 and [item.level for item in locations] == list(range(9)),
            "decoded jersey does not have exactly mip levels 0..8")
    require(xenos_mips.transport_roundtrip(texture, locations) == texture,
            "decoded jersey Xenos transport is not bit-exact")
    expected_layout = row["nine_level_layout"]
    require(isinstance(expected_layout, list) and len(expected_layout) == 9,
            "pinned jersey catalog layout changed")

    previews: list[PreviewLevel] = []
    for location, expected in zip(locations, expected_layout):
        manifest = location.manifest()
        require(
            all(expected.get(key) == value for key, value in manifest.items()),
            f"mip {location.level} layout differs from the pinned catalog",
        )
        linear = xenos_mips.extract_linear_bc3(texture, location)
        linear_hash = sha256(linear)
        require(linear_hash == expected.get("linear_bc3_sha256"),
                f"mip {location.level} BC3 bytes differ from the pinned catalog")
        rgba = verifier.decode_linear_bc3(linear, location)
        png_name = f"mip_{location.level}_{location.width}x{location.height}.png"
        png = _png_bytes(location.width, location.height, rgba)
        previews.append(PreviewLevel(
            location.level,
            location.width,
            location.height,
            location.packed_tail,
            location.origin_block_x,
            location.origin_block_y,
            linear_hash,
            sha256(rgba),
            png_name,
            sha256(png),
            png,
        ))
    return tuple(previews)


def _affected_team_banks(
    asset_index: int, row: dict[str, Any]
) -> tuple[dict[str, object], ...]:
    identity = verifier.open_regular(
        TEAM_TABLE, "pinned APF uniform team selector inventory", 1024 * 1024
    )
    try:
        payload = verifier.read_all(identity, "pinned APF uniform team selector inventory")
    finally:
        identity.close()
    require(len(payload) == EXPECTED_TEAM_TABLE_SIZE and
            sha256(payload) == EXPECTED_TEAM_TABLE_SHA256,
            "APF uniform team selector inventory pin changed")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExportError("APF uniform team selector inventory is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    require(tuple(reader.fieldnames or ()) == TEAM_TABLE_HEADER,
            "APF uniform team selector inventory header changed")
    records = list(reader)
    require(len(records) == 1120, "APF uniform team selector inventory row count changed")
    selected: list[dict[str, object]] = []
    for record in records:
        if record["families"] != "jersey" or record["asset_index_byte_0"] != str(asset_index):
            continue
        require(record["selector_slot"] == "4" and record["bank"] in {"0", "1"} and
                record["package_names"] == row["outer_name"] and
                record["package_outer_table_indices"] == str(row["outer_table_index"]),
                "APF jersey team selector join differs from the pinned target")
        team_index = int(record["team_index"])
        bank = int(record["bank"])
        require(0 <= team_index < 40 and record["slot_kind"] in {
            "built_in_team", "user_slot", "online_slot"
        }, "APF jersey team selector row is outside the proved team/bank domain")
        selected.append({
            "team_index": team_index,
            "team_name": record["team_name"],
            "abbreviation": record["abbreviation"],
            "slot_kind": record["slot_kind"],
            "bank": bank,
            "bank_label": f"bank {bank}",
        })
    selected.sort(key=lambda item: (int(item["team_index"]), int(item["bank"])))
    require(len({(item["team_index"], item["bank"]) for item in selected}) == len(selected),
            "APF jersey team selector inventory has duplicate team/bank uses")
    return tuple(selected)


def _read_selected_source(
    source_0a: Path, asset_index: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str, Path, int]:
    require(type(asset_index) is int and 0 <= asset_index <= 23,
            "--asset-index must be an integer in 0..23")
    catalog = verifier.load_catalog()
    row = catalog["jerseys"][asset_index]
    require(row["asset_index"] == asset_index and
            row["physical"]["pack_name"] == "0A" and
            row["inner_file"]["index"] == 0 and
            row["inner_file"]["name"] == "jersey_color",
            "selected jersey catalog record changed")

    source = verifier.open_regular(source_0a, "source APF retail 0A")
    try:
        require(source.size == int(catalog["source"]["size"]),
                "source APF 0A size is not pinned retail")
        before = verifier.hash_fd(source.descriptor, source.size)
        require(before == verifier.EXPECTED_VOLUME_SHA256,
                "source APF 0A SHA-256 is not pinned retail")
        offset = int(row["physical"]["pack_offset"])
        size = int(row["outer_allocation"]["size"])
        require(0 <= offset <= source.size and size <= source.size - offset,
                "selected jersey allocation is outside source APF 0A")
        entry_bytes = _pread(source.descriptor, size, offset)
        require(len(entry_bytes) == size and
                sha256(entry_bytes) == row["outer_allocation"]["sha256"],
                "selected jersey allocation differs from the pinned catalog")
        source.recheck_path("source APF retail 0A")
        decoded = verifier.decode_entry_bytes(entry_bytes, row)
        after = verifier.hash_fd(source.descriptor, source.size)
        source.recheck_path("source APF retail 0A")
        require(after == before == verifier.EXPECTED_VOLUME_SHA256,
                "source APF 0A changed during read-only export")
        path = source.path
        source_size = source.size
    finally:
        source.close()
    return catalog, row, decoded, before, after, path, source_size


def build_export_plan(source_0a: Path, asset_index: int) -> ExportPlan:
    """Hash, read, and decode one pinned retail target without writing output."""

    catalog, row, decoded, before, after, source_path, source_size = (
        _read_selected_source(source_0a, asset_index)
    )
    previews = _preview_levels(row, decoded)
    team_banks = _affected_team_banks(asset_index, row)
    base = previews[0]
    base_name = "jersey_base.png"
    base_file = OutputFile(base_name, base.png)
    preview_files = tuple(OutputFile(item.png_name, item.png) for item in previews)
    files = (base_file, *preview_files)
    require(len({item.name for item in files}) == 10,
            "export output filenames are not unique")

    descriptor_hash = sha256(canonical_json(decoded["metadata"]))
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "scope": {
            "game": "All-Pro Football 2K8 (USA)",
            "operation": "read-only jersey PNG and mip preview export",
            "archive_opened_for_write": False,
            "archive_bytes_written": False,
            "emulator_launched": False,
        },
        "source": {
            "path": str(source_path),
            "volume": "0A",
            "size": source_size,
            "sha256_before": before,
            "sha256_after": after,
            "identity_rechecked": True,
            "opened_read_only": True,
        },
        "catalog": {
            "schema": catalog["schema"],
            "sha256": verifier.EXPECTED_CATALOG_SHA256,
            "target_count": 24,
        },
        "target": {
            "asset_index": asset_index,
            "outer_name": row["outer_name"],
            "outer_table_index": row["outer_table_index"],
            "fixed_allocation": row["outer_allocation"]["size"],
            "entry_sha256": row["outer_allocation"]["sha256"],
            "inner_name": "jersey_color",
            "texture_sha256": row["inner_file"]["texture_sha256"],
            "descriptor_sha256": descriptor_hash,
            "descriptor": decoded["metadata"],
        },
        "selector_inventory": {
            "path": str(TEAM_TABLE.relative_to(WORKSPACE)),
            "sha256": EXPECTED_TEAM_TABLE_SHA256,
            "affected_use_count": len(team_banks),
            "bank_labels": ["bank 0", "bank 1"],
            "home_away_orientation_proved": False,
            "affected_team_bank_uses": list(team_banks),
        },
        "base_png": {
            "png": base_name,
            "png_size": len(base.png),
            "png_sha256": base.png_sha256,
            "decoded_rgba_sha256": base.rgba_sha256,
            "width": base.width,
            "height": base.height,
            "same_pixels_as_mip_level": 0,
        },
        "mip_previews": [item.provenance() for item in previews],
        "output_contract": {
            "png_file_count": 10,
            "mip_level_count": 9,
            "provenance_created_last": True,
            "contains_raw_archive_entry": False,
            "contains_bc3_payload": False,
            "derived_retail_pixels_are_local_only": True,
        },
    }
    return ExportPlan(document, files)


def _absolute_new_directory(path: Path) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if os.path.lexists(requested):
        raise ExportError(f"output directory already exists: {requested}")
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise ExportError(f"output directory parent is missing: {requested.parent}") from exc
    require(stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
            "output directory parent must be a non-symlink directory")
    return requested.resolve(strict=False)


def _write_payload(descriptor: int, payload: bytes) -> None:
    cursor = 0
    while cursor < len(payload):
        written = os.write(descriptor, payload[cursor:])
        if written <= 0:
            raise OSError("short write while creating export file")
        cursor += written


def _unlink_owned(dir_fd: int, name: str, identity: tuple[int, int]) -> None:
    try:
        current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity:
        os.unlink(name, dir_fd=dir_fd)


def _create_file(dir_fd: int, name: str, payload: bytes) -> tuple[int, int]:
    require(Path(name).name == name and name not in {"", ".", ".."},
            "export filename is not a fixed basename")
    flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(name, flags, 0o644, dir_fd=dir_fd)
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), "exclusive export output is not regular")
        identity = (opened.st_dev, opened.st_ino)
        _write_payload(descriptor, payload)
        os.fsync(descriptor)
        require(_pread(descriptor, len(payload) + 1, 0) == payload,
                f"export output read-back differs: {name}")
        current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        require(stat.S_ISREG(current.st_mode) and
                (current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], len(payload)),
                f"export output pathname changed: {name}")
        return identity
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if identity is not None:
            _unlink_owned(dir_fd, name, identity)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_export_plan(output_dir: Path, plan: ExportPlan) -> ExportResult:
    """Exclusively commit a prepared export; provenance is always written last."""

    output = _absolute_new_directory(output_dir)
    try:
        os.mkdir(output, 0o755)
    except FileExistsError as exc:
        raise ExportError(f"output directory already exists: {output}") from exc
    directory_info = output.lstat()
    require(stat.S_ISDIR(directory_info.st_mode) and not stat.S_ISLNK(directory_info.st_mode),
            "created export output is not a regular directory")
    directory_identity = (directory_info.st_dev, directory_info.st_ino)
    dir_fd: int | None = None
    created: list[tuple[str, tuple[int, int]]] = []
    try:
        dir_fd = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        opened = os.fstat(dir_fd)
        require(stat.S_ISDIR(opened.st_mode) and
                (opened.st_dev, opened.st_ino) == directory_identity,
                "export output directory identity changed after creation")
        for file in plan.files:
            identity = _create_file(dir_fd, file.name, file.payload)
            created.append((file.name, identity))
        provenance_payload = canonical_json(plan.document)
        identity = _create_file(dir_fd, PROVENANCE_NAME, provenance_payload)
        created.append((PROVENANCE_NAME, identity))
        os.fsync(dir_fd)
        expected_names = {file.name for file in plan.files} | {PROVENANCE_NAME}
        require(set(os.listdir(dir_fd)) == expected_names,
                "export directory contains an unexpected file")
        current = output.lstat()
        require(stat.S_ISDIR(current.st_mode) and not stat.S_ISLNK(current.st_mode) and
                (current.st_dev, current.st_ino) == directory_identity,
                "export output directory pathname changed during commit")
    except Exception as exc:
        if dir_fd is not None:
            for name, identity in reversed(created):
                _unlink_owned(dir_fd, name, identity)
            os.close(dir_fd)
            dir_fd = None
        try:
            current = output.lstat()
            if stat.S_ISDIR(current.st_mode) and not stat.S_ISLNK(current.st_mode) and \
                    (current.st_dev, current.st_ino) == directory_identity:
                output.rmdir()
        except (FileNotFoundError, OSError):
            pass
        if isinstance(exc, ExportError):
            raise
        raise ExportError(f"could not create jersey export: {exc}") from exc
    finally:
        if dir_fd is not None:
            os.close(dir_fd)
    return ExportResult(
        output, output / PROVENANCE_NAME,
        int(plan.document["target"]["asset_index"]), len(plan.files) + 1,
    )


def export_jersey(source_0a: Path, asset_index: int, output_dir: Path) -> ExportResult:
    plan = build_export_plan(source_0a, asset_index)
    return write_export_plan(output_dir, plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-0a", required=True, type=Path,
                        help="user-owned pinned retail APF 0A opened read-only")
    parser.add_argument("--asset-index", required=True, type=int,
                        help="proved uniform_jersey asset index, exactly 0..23")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="new absent directory for PNG previews and provenance")
    args = parser.parse_args(argv)
    try:
        result = export_jersey(args.source_0a, args.asset_index, args.output_dir)
        print(
            "APF_JERSEY_FAMILY_EXPORT_PASS "
            f"asset={result.asset_index} mip_previews=9 pngs=10 "
            f"archive_written=false provenance={result.provenance}"
        )
        return 0
    except (
        ExportError,
        verifier.VerifyError,
        apf_inner.FormatError,
        xenos_mips.MipLayoutError,
        csv.Error,
        KeyError,
        TypeError,
        ValueError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
