#!/usr/bin/env python3
"""Independently verify one APF field-art copied-volume patch.

This verifier does not use the writer's encoders or its ``build`` path.  It
re-reads the source and output ``0A`` volumes, re-parses both, and re-derives
the expected footprint of the edit from the pinned contract and the supplied
PNG alone.  It proves, at two levels:

* Volume level -- a whole-volume byte diff: every differing byte lies inside the
  one target outer entry; the rest of the ~1.1 GB volume is byte-identical, and
  the retail source is never modified (hashed before and after).
* Entry level -- re-parsing the output entry: the descriptor pad, the packed mip
  tail, every sibling/other inner part, and the IFF name footer are byte-exact;
  the target texture's base level is the only decoded part that changed; and the
  changed 4x4 blocks (1x1 texels for 8_8_8_8) are a subset of exactly those
  blocks where the supplied PNG differs from the retail image -- so the output
  reflects the PNG edit and nothing else.

The base-mip decode uses the public ``apf_inner`` decoder; the pinned per-slot
facts come from ``apf_field_art_patch._CONTRACTS`` (data, not transport).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from PIL import Image, UnidentifiedImageError  # noqa: E402

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
from apf_field_art_patch import FieldArtContract, _CONTRACTS  # noqa: E402


SCHEMA = "apf_field_art_verify/v1"
PATCH_SCHEMA = "apf_field_art_patch/v1"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
MAX_PNG_BYTES = 64 * 1024 * 1024
_STREAM_CHUNK = 8 * 1024 * 1024


class VerifyError(ValueError):
    """Raised when a copied field-art patch violates an invariant."""


def require(value: bool, message: str) -> None:
    if not value:
        raise VerifyError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a non-symlink regular file",
    )
    return path.resolve(strict=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_STREAM_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def load_png(path: Path, width: int, height: int) -> tuple[bytes, str]:
    path = regular(path, "field-art PNG")
    payload = path.read_bytes()
    require(0 < len(payload) <= MAX_PNG_BYTES, "field-art PNG size is outside its limit")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            require(
                image.format == "PNG" and image.size == (width, height),
                f"field-art PNG must be an exact {width}x{height} PNG",
            )
            rgba = image.convert("RGBA").tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise VerifyError(f"cannot decode APF field-art PNG: {exc}") from exc
    return rgba, sha256(payload)


def _require_descriptor(contract: FieldArtContract, metadata: dict[str, object]) -> None:
    """Assert the output TXTR descriptor still describes the pinned texture."""

    checks = {
        "format": contract.format,
        "width": contract.width,
        "height": contract.height,
        "pitch_pixels": contract.pitch_pixels,
        "endianness": contract.endianness,
        "tiled": True,
        "stacked": False,
        "dimension": 1,
        "vc_base_data_length": contract.base_len,
        "vc_mip_data_length": contract.mip_len,
    }
    for key, value in checks.items():
        require(metadata.get(key) == value, f"output descriptor field {key} changed")
    require(
        tuple(metadata["swizzle_components"]) == contract.swizzle,  # type: ignore[arg-type]
        "output descriptor swizzle changed",
    )


def _entry_state(archive: apf_outer.Archive, contract: FieldArtContract) -> dict[str, Any]:
    """Re-parse one entry and slice out the target's descriptor/head/base/mip."""

    entry = archive.entries[contract.entry_index]
    require(
        len(entry.segments) == 1 and entry.segments[0].pack_name == "0A",
        "field-art entry is not in one 0A segment",
    )
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    require(
        contract.file_index < len(record.files),
        "output IFF has no target inner file",
    )
    target = record.files[contract.file_index]
    require(
        target.name == contract.name and target.type_name == contract.type_name,
        "output target inner file identity changed",
    )
    expected_parts = 2 if contract.part_layout == "dram_vram" else 1
    require(len(target.parts) == expected_parts, "output target part count changed")
    descriptor_part = target.parts[0]
    descriptor = blocks[descriptor_part.block_index][
        descriptor_part.offset : descriptor_part.offset + descriptor_part.length
    ]
    metadata = apf_inner.parse_txtr_metadata(descriptor)
    pixel_part = target.parts[contract.pixel_part_index]
    pixel = blocks[pixel_part.block_index][
        pixel_part.offset : pixel_part.offset + pixel_part.length
    ]
    head = len(pixel) - contract.base_len - contract.mip_len
    require(head == contract.head_len, "output head/base/mip split changed")
    require(record.footer is not None, "output IFF name footer missing")
    footer_total = 8 + record.footer.payload_size
    footer = entry_bytes[record.file_length : record.file_length + footer_total]
    require(
        not any(entry_bytes[record.file_length + footer_total :]),
        "output outer allocation tail is nonzero",
    )
    return {
        "entry": entry,
        "record": record,
        "entry_bytes": entry_bytes,
        "blocks": blocks,
        "metadata": metadata,
        "descriptor": descriptor,
        "head": pixel[:head],
        "base": pixel[head : head + contract.base_len],
        "mip": pixel[head + contract.base_len :],
        "footer": footer,
        "part_hashes": {
            (file.index, part_index): sha256(
                blocks[part.block_index][part.offset : part.offset + part.length]
            )
            for file in record.files
            for part_index, part in enumerate(file.parts)
        },
    }


def _changed_block_set(
    source_rgba: bytes,
    other_rgba: bytes,
    width: int,
    height: int,
    block_width: int,
    block_height: int,
) -> set[int]:
    """Indices of block-grid cells whose RGBA differs between the two images."""

    changed: set[int] = set()
    width_blocks = width // block_width
    for block_y in range(height // block_height):
        for block_x in range(width_blocks):
            for local_y in range(block_height):
                row = (block_y * block_height + local_y) * width + block_x * block_width
                if (
                    source_rgba[row * 4 : (row + block_width) * 4]
                    != other_rgba[row * 4 : (row + block_width) * 4]
                ):
                    changed.add(block_y * width_blocks + block_x)
                    break
    return changed


def _linear_blocks(metadata: dict[str, object], base: bytes, dims: tuple[int, int, int]) -> bytes:
    block_width, block_height, bytes_per_block = dims
    tiled = apf_inner._untile_2d(  # type: ignore[attr-defined]
        base,
        int(metadata["width"]),
        int(metadata["height"]),
        int(metadata["pitch_pixels"]),
        block_width,
        block_height,
        bytes_per_block,
    )
    return apf_inner._endian_swap(tiled, int(metadata["endianness"]))  # type: ignore[attr-defined]


def _whole_volume_diff(
    source: Path, output: Path, span_offset: int, span_size: int
) -> dict[str, object]:
    """Byte-diff the whole volume; assert every diff lies inside the span."""

    require(source.stat().st_size == output.stat().st_size, "copied 0A size changed")
    span_end = span_offset + span_size
    outside_source, outside_output = hashlib.sha256(), hashlib.sha256()
    changed_total = 0
    changed_in_span = 0
    first_changed: int | None = None
    last_changed: int | None = None
    cursor = 0
    with source.open("rb") as left, output.open("rb") as right:
        while True:
            a = left.read(_STREAM_CHUNK)
            b = right.read(_STREAM_CHUNK)
            require(len(a) == len(b), "copied 0A shortened")
            if not a:
                break
            end = cursor + len(a)
            for start, stop in (
                (cursor, min(end, span_offset)),
                (max(cursor, span_end), end),
            ):
                if start < stop:
                    lo, hi = start - cursor, stop - cursor
                    outside_source.update(a[lo:hi])
                    outside_output.update(b[lo:hi])
            if a != b:
                for offset in range(len(a)):
                    if a[offset] != b[offset]:
                        absolute = cursor + offset
                        changed_total += 1
                        if first_changed is None:
                            first_changed = absolute
                        last_changed = absolute
                        require(
                            span_offset <= absolute < span_end,
                            f"byte 0x{absolute:x} changed outside the target entry span",
                        )
                        changed_in_span += 1
            cursor = end
    require(
        outside_source.digest() == outside_output.digest(),
        "copied 0A differs outside the target entry span",
    )
    return {
        "changed_byte_count": changed_total,
        "changed_bytes_inside_target_entry": changed_in_span,
        "first_changed_offset": first_changed,
        "last_changed_offset": last_changed,
        "outside_target_sha256_source": outside_source.hexdigest(),
        "outside_target_sha256_output": outside_output.hexdigest(),
        "all_other_bytes_identical": True,
    }


def verify(
    source_path: Path,
    output_path: Path,
    png_path: Path,
    entry_index: int,
    file_index: int,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    contract = _CONTRACTS.get((entry_index, file_index))
    require(contract is not None, f"(entry {entry_index}, file {file_index}) is not a pinned slot")
    assert contract is not None
    source = regular(source_path, "source APF 0A")
    output = regular(output_path, "output APF 0A")
    require(source != output, "source and output APF 0A paths must differ")

    source_before = sha256_file(source)
    require(source_before == EXPECTED_VOLUME_SHA256, "source is not the pinned retail APF 0A")
    png_rgba, png_sha = load_png(png_path, contract.width, contract.height)

    source_archive = apf_outer.parse_archive(source)
    output_archive = apf_outer.parse_archive(output)
    source_state = _entry_state(source_archive, contract)
    output_state = _entry_state(output_archive, contract)
    source_entry = source_state["entry"]
    output_entry = output_state["entry"]

    require(source_entry.size == output_entry.size, "fixed outer allocation changed")
    require(
        sha256(source_state["entry_bytes"]) == contract.entry_sha256,
        "source entry is not the pinned retail package",
    )
    require(
        sha256(source_state["base"]) == contract.base_sha256,
        "source base is not the pinned retail texture",
    )

    # The output descriptor must still describe the pinned texture, and every
    # non-base region must be byte-exact.  For 2-part textures the descriptor is
    # a separate inner part (covered by the "only target part changed" hash
    # check below); for single-part textures it lives inside the preserved head.
    _require_descriptor(contract, output_state["metadata"])
    require(source_state["head"] == output_state["head"], "descriptor pad changed")
    require(source_state["mip"] == output_state["mip"], "packed mip tail changed")
    require(source_state["footer"] == output_state["footer"], "IFF name footer changed")
    if contract.part_layout == "dram_vram":
        require(
            source_state["descriptor"] == output_state["descriptor"],
            "separate DRAM descriptor part changed",
        )

    # Every inner part is decode-identical except the one target pixel part.
    target_key = (file_index, contract.pixel_part_index)
    changed_keys = [
        key
        for key in source_state["part_hashes"]
        if source_state["part_hashes"].get(key) != output_state["part_hashes"].get(key)
    ]
    require(
        set(source_state["part_hashes"]) == set(output_state["part_hashes"]),
        "inner part roster changed",
    )
    no_op = source_state["base"] == output_state["base"]
    if no_op:
        require(changed_keys == [], "no-op patch unexpectedly changed an inner part")
    else:
        require(changed_keys == [target_key], f"unexpected inner parts changed: {changed_keys}")
        require(
            output_state["base"] != source_state["base"],
            "patched output base is unchanged",
        )

    # Independent minimal-footprint proof from the PNG alone.
    dims = contract.block_dims
    _, _, source_rgba = apf_inner.decode_txtr_base_rgba(source_state["metadata"], source_state["base"])
    _, _, output_rgba = apf_inner.decode_txtr_base_rgba(output_state["metadata"], output_state["base"])
    png_changed = _changed_block_set(
        source_rgba, png_rgba, contract.width, contract.height, dims[0], dims[1]
    )
    source_linear = _linear_blocks(source_state["metadata"], source_state["base"], dims)
    output_linear = _linear_blocks(output_state["metadata"], output_state["base"], dims)
    block_bytes = dims[2]
    block_count = len(source_linear) // block_bytes
    output_changed_blocks = {
        index
        for index in range(block_count)
        if source_linear[index * block_bytes : (index + 1) * block_bytes]
        != output_linear[index * block_bytes : (index + 1) * block_bytes]
    }
    require(
        output_changed_blocks <= png_changed,
        "output changed base blocks the PNG did not touch",
    )
    for index in range(block_count):
        if index not in png_changed:
            lo, hi = index * block_bytes, (index + 1) * block_bytes
            require(
                source_linear[lo:hi] == output_linear[lo:hi],
                f"base block {index} changed although the PNG left it untouched",
            )

    # Whole-volume diff: only the target entry span may differ.
    volume = _whole_volume_diff(
        source, output, source_entry.segments[0].pack_offset, source_entry.size
    )
    source_after = sha256_file(source)
    require(source_after == source_before, "source 0A changed during verification")
    output_volume_sha = sha256_file(output)

    manifest_cross_check: dict[str, object] | None = None
    if manifest_path is not None:
        manifest = json.loads(regular(manifest_path, "patch manifest").read_text("utf-8"))
        require(manifest.get("schema") == PATCH_SCHEMA, "manifest is not an apf_field_art_patch/v1")
        manifest_mode = manifest.get("mode")
        require(
            manifest_mode == ("no_op" if no_op else "patched"),
            f"manifest mode {manifest_mode!r} disagrees with the observed output",
        )
        if no_op:
            require(
                output_state["entry_bytes"] == source_state["entry_bytes"],
                "no-op manifest but output entry differs from source",
            )
        else:
            replacement_sha = manifest.get("binary_patch_manifest", {}).get("replacement_sha256")
            require(
                replacement_sha == sha256(output_state["entry_bytes"]),
                "manifest replacement SHA differs from the output entry",
            )
        manifest_cross_check = {
            "schema_ok": True,
            "mode": manifest_mode,
            "output_entry_matches_manifest": True,
        }

    return {
        "schema": SCHEMA,
        "target": {
            "entry_index": entry_index,
            "file_index": file_index,
            "name": contract.name,
            "kind": contract.kind,
            "codec": contract.codec,
            "format": contract.format,
            "dimensions": [contract.width, contract.height],
            "base_len": contract.base_len,
            "mip_len": contract.mip_len,
            "part_layout": contract.part_layout,
        },
        "mode": "no_op" if no_op else "patched",
        "source": {
            "path": str(source),
            "sha256_before": source_before,
            "sha256_after": source_after,
            "modified": False,
            "entry_sha256": sha256(source_state["entry_bytes"]),
            "base_sha256": sha256(source_state["base"]),
        },
        "output": {
            "path": str(output),
            "sha256": output_volume_sha,
            "entry_sha256": sha256(output_state["entry_bytes"]),
            "base_sha256": sha256(output_state["base"]),
        },
        "png": {"path": str(png_path), "file_sha256": png_sha, "rgba_sha256": sha256(png_rgba)},
        "whole_volume_diff": volume,
        "base_footprint": {
            "block_dims": list(dims),
            "png_changed_block_count": len(png_changed),
            "output_changed_block_count": len(output_changed_blocks),
            "output_changed_is_subset_of_png_changed": True,
        },
        "validation": {
            "source_is_pinned_retail": True,
            "fixed_outer_allocation_preserved": True,
            "descriptor_preserved": True,
            "descriptor_pad_preserved": True,
            "packed_mip_tail_preserved": True,
            "name_footer_preserved": True,
            "only_target_base_part_changed": True,
            "output_edit_within_png_footprint": True,
            "all_other_volume_bytes_identical": True,
            "source_opened_read_only": True,
            "runtime_visibility_proved": False,
        },
        "manifest_cross_check": manifest_cross_check,
        "contains_game_or_replacement_bytes": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-volume", required=True, type=Path)
    parser.add_argument("--output-volume", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--entry-index", required=True, type=int)
    parser.add_argument("--file-index", required=True, type=int)
    parser.add_argument("--manifest", type=Path, help="optional patch manifest to cross-check")
    parser.add_argument("--report", type=Path, help="write the JSON verification report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = verify(
            args.source_volume,
            args.output_volume,
            args.png,
            args.entry_index,
            args.file_index,
            args.manifest,
        )
        if args.report is not None:
            report_path = args.report.expanduser()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        diff = report["whole_volume_diff"]
        print(
            "APF_FIELD_ART_VERIFY_PASS "
            f"entry={args.entry_index} file={args.file_index} mode={report['mode']} "
            f"changed_bytes={diff['changed_byte_count']} "
            f"all_other_identical={diff['all_other_bytes_identical']} "
            "source_read_only=true runtime_visibility=false"
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
