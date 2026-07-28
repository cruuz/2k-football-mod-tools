#!/usr/bin/env python3
"""Independent full-volume verifier for the APF 2K8 ``uniform_logocache`` writer.

This is the product of the cache writer: a standalone reader that proves, with
its OWN ``F0985030`` directory parse and canonical H7A decompression (it never
imports ``apf_logocache_patch``'s repack code), that a copied ``0A`` volume:

* differs from its retail source ONLY inside the two fixed cache extents — the
  directory ``uniform_logocache.iff`` (0A @ 0x032C5000, 0xA000 B) and the payload
  ``uniform_logocache.cdf`` (0A @ 0x3DF63000, 0x9E0800 B); every other byte of the
  1,140,850,688-byte volume is identical;
* decompresses (all 236 ``[DRAM 0xE0][VRAM 0xAC000]`` sub-block pairs) to content
  in which EXACTLY the intended catalog entries' VRAM base level(s) changed, while
  every DRAM part, every 0x2C000 packed mip tail, and every other catalog entry's
  base are byte-identical to the source;
* keeps a valid, strictly re-parseable directory (all 236 descriptors, aggregate
  slots, footer names and per-name CRC ids unchanged; only auxiliary
  ``[stream_a, len_a, stream_b, len_b]`` records move).

If any of those cannot be proved, verification fails and the volume does NOT
ship.  The emitted JSON manifest carries hashes, offsets and reasons only — never
retail texture bytes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402


VOLUME_SIZE = 1_140_850_688
DIR_TABLE_INDEX = 171
DIR_NAME_ID = 0x1C247977
DIR_SIZE = 0xA000
DIR_PACK_OFFSET = 53221376
PAYLOAD_TABLE_INDEX = 213
PAYLOAD_NAME_ID = 0x23859E23
PAYLOAD_SIZE = 0x9E0800
PAYLOAD_PACK_OFFSET = 1039226880
DIR_MAGIC = 0xF0985030
DIR_HEADER_SIZE = 0x2924
FILE_COUNT = 236
CATALOG_COUNT = 118
DRAM_STRIDE = 0xE0
VRAM_STRIDE = 0xAC000
BASE_LEN = 0x80000
MIP_LEN = 0x2C000
AUX_LEN_A = 0x71
TXTR_TYPE_HASH = 0x5C369069


class VerifyError(ValueError):
    """Raised when the copied volume cannot be proved a bounded cache edit."""


@dataclass(frozen=True)
class _Sub:
    index: int
    name: str
    catalog_index: int
    level: int
    stream_a: int
    len_a: int
    stream_b: int
    len_b: int


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Independent F0985030 directory parse (fresh field reads; not the writer's code).
# ---------------------------------------------------------------------------
def _parse_directory(raw: bytes) -> list[_Sub]:
    if len(raw) != DIR_SIZE:
        raise VerifyError(f"directory is 0x{len(raw):x}, expected 0x{DIR_SIZE:x}")
    (
        magic,
        header_size,
        file_length,
        zero,
        block_count,
        block_pointer,
        file_count,
        file_pointer,
        auxiliary_pointer,
        cache_name_pointer,
    ) = struct.unpack_from(">10I", raw, 0)
    if magic != DIR_MAGIC or header_size != file_length or header_size != DIR_HEADER_SIZE:
        raise VerifyError("directory header/magic/length invalid")
    if zero != 0 or block_count != 2 or file_count != FILE_COUNT:
        raise VerifyError("directory block/file counts invalid")
    file_pointer_table = 0x1C + file_pointer - 1
    auxiliary_pointer_table = 0x20 + auxiliary_pointer - 1
    cache_name_offset = 0x24 + cache_name_pointer - 1
    if file_pointer_table != 0x68 or auxiliary_pointer_table != 0x1688:
        raise VerifyError("directory pointer tables moved")
    if cache_name_offset != 0x28F8:
        raise VerifyError("directory internal-name pointer moved")

    # File descriptors (for the file-id CRC and aggregate-slot permutation check).
    descriptor_start = file_pointer_table + file_count * 4
    file_ids: list[int] = []
    slots: list[int] = []
    cursor = descriptor_start
    for index in range(file_count):
        pointer_field = file_pointer_table + index * 4
        descriptor = pointer_field + struct.unpack_from(">I", raw, pointer_field)[0] - 1
        if descriptor != cursor:
            raise VerifyError(f"file descriptor {index} is not packed")
        file_id, type_hash, offset_count, dram_offset, vram_offset = struct.unpack_from(
            ">5I", raw, descriptor
        )
        if type_hash != TXTR_TYPE_HASH or offset_count != 2:
            raise VerifyError(f"file descriptor {index} is not TXTR/2-part")
        if dram_offset % DRAM_STRIDE or vram_offset % VRAM_STRIDE:
            raise VerifyError(f"file descriptor {index} has unaligned aggregate offsets")
        if dram_offset // DRAM_STRIDE != vram_offset // VRAM_STRIDE:
            raise VerifyError(f"file descriptor {index} aggregate slots disagree")
        file_ids.append(file_id)
        slots.append(dram_offset // DRAM_STRIDE)
        cursor += 0x14
    if cursor != auxiliary_pointer_table:
        raise VerifyError("file descriptors do not end at the auxiliary table")
    if set(slots) != set(range(file_count)):
        raise VerifyError("aggregate slots are not a 0..235 permutation")

    # Footer names (reuse only the canonical shared name-footer reader).
    footer_magic = struct.unpack_from(">I", raw, file_length)[0]
    footer_size = struct.unpack_from("<I", raw, file_length + 4)[0]
    if footer_magic != apf_inner.NAME_FOOTER_MAGIC:
        raise VerifyError("directory name footer magic changed")
    footer_end = file_length + 8 + footer_size
    if footer_end > len(raw) or any(raw[footer_end:]):
        raise VerifyError("directory name footer/alignment tail invalid")
    names = apf_inner._parse_footer_names(  # type: ignore[attr-defined]
        raw[file_length + 8 : footer_end], file_count
    )

    # Auxiliary records.
    auxiliary_start = auxiliary_pointer_table + file_count * 4
    cursor = auxiliary_start
    previous_end = 0
    subs: list[_Sub] = []
    for index in range(file_count):
        pointer_field = auxiliary_pointer_table + index * 4
        descriptor = pointer_field + struct.unpack_from(">I", raw, pointer_field)[0] - 1
        if descriptor != cursor:
            raise VerifyError(f"auxiliary descriptor {index} is not packed")
        stream_a, length_a, stream_b, length_b = struct.unpack_from(">4I", raw, descriptor)
        if stream_a != previous_end or stream_b != stream_a + length_a:
            raise VerifyError(f"auxiliary stream {index} is not contiguous")
        if length_a != AUX_LEN_A:
            raise VerifyError(f"auxiliary DRAM length {index} is not 0x71")
        name, type_name = names[index]
        if file_ids[index] != zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF:
            raise VerifyError(f"file id {index} does not match name {name!r}")
        if type_name != "TXTR" or "_logo_l" not in name:
            raise VerifyError(f"entry {index} name/type invalid: {name!r}")
        index_text, level_text = name.split("_logo_l", 1)
        if not index_text.isdigit() or level_text not in ("0", "1"):
            raise VerifyError(f"entry {index} name syntax invalid: {name!r}")
        subs.append(
            _Sub(
                index=index,
                name=name,
                catalog_index=int(index_text),
                level=int(level_text),
                stream_a=stream_a,
                len_a=length_a,
                stream_b=stream_b,
                len_b=length_b,
            )
        )
        previous_end = stream_b + length_b
        cursor += 0x10
    if previous_end > PAYLOAD_SIZE:
        raise VerifyError("auxiliary stream exceeds the fixed payload allocation")
    return subs


def _decompress_vram(stored: bytes, what: str) -> bytes:
    if len(stored) < 0x14:
        raise VerifyError(f"{what} shorter than its H7A wrapper")
    magic, uncompressed, compressed, _unknown, shift = struct.unpack_from(">5I", stored, 0)
    if magic != apf_inner.H7A_MAGIC or compressed != len(stored):
        raise VerifyError(f"{what} H7A wrapper invalid")
    decoded = apf_inner.decompress_h7a(stored[0x14:], uncompressed, shift)
    if len(decoded) != VRAM_STRIDE:
        raise VerifyError(f"{what} decoded to 0x{len(decoded):x}, expected 0x{VRAM_STRIDE:x}")
    return decoded


# ---------------------------------------------------------------------------
# Volume access.
# ---------------------------------------------------------------------------
def _read_at(volume: Path, offset: int, size: int, what: str) -> bytes:
    with volume.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(size)
    if len(data) != size:
        raise VerifyError(f"short read of the {what} extent from {volume}")
    return data


def _locate_pair(volume: Path) -> tuple[bytes, bytes]:
    """Read the cache directory + payload directly from the ``0A`` file.

    The two entries are single-segment at fixed ``0A`` offsets, so this needs only
    the ``0A`` volume itself (no sibling packs).  Reading the wrong location is
    caught downstream by the strict ``F0985030`` magic/structure parse, so the
    pinned offsets are self-confirming.
    """

    return (
        _read_at(volume, DIR_PACK_OFFSET, DIR_SIZE, "directory"),
        _read_at(volume, PAYLOAD_PACK_OFFSET, PAYLOAD_SIZE, "payload"),
    )


def _diff_within_extents(
    source_volume: Path, output_volume: Path, extents: list[tuple[int, int]]
) -> dict[str, object]:
    """Stream both volumes; prove every differing byte lies inside an extent.

    Bytes covered by an extent are ignored (they are allowed to change and are
    reproved by content downstream); every remaining sub-range of each chunk must
    be byte-identical between source and output, checked with C-level slice
    comparisons rather than a per-byte Python loop.
    """

    extents = sorted(extents)
    source_size = source_volume.stat().st_size
    output_size = output_volume.stat().st_size
    if source_size != output_size:
        raise VerifyError("source and output volumes differ in size")
    if source_size != VOLUME_SIZE:
        raise VerifyError(f"volume size 0x{source_size:x} != 0x{VOLUME_SIZE:x}")
    outside_digest = hashlib.sha256()
    chunk = 8 * 1024 * 1024
    with source_volume.open("rb") as src, output_volume.open("rb") as out:
        position = 0
        while position < source_size:
            a = src.read(min(chunk, source_size - position))
            b = out.read(len(a))
            if len(a) != len(b):
                raise VerifyError("short read during full-volume diff")
            span_start = position
            span_end = position + len(a)
            # Walk the maximal sub-ranges of [span_start, span_end) NOT covered by
            # any extent; each must match byte-for-byte.
            cursor = span_start
            for lo, hi in extents:
                if hi <= cursor or lo >= span_end:
                    continue
                if lo > cursor:
                    s, e = cursor - span_start, min(lo, span_end) - span_start
                    if a[s:e] != b[s:e]:
                        raise VerifyError(
                            f"volume changed OUTSIDE the cache extents near 0x{span_start + s:x}"
                        )
                    outside_digest.update(a[s:e])
                cursor = max(cursor, min(hi, span_end))
            if cursor < span_end:
                s = cursor - span_start
                if a[s:] != b[s:]:
                    raise VerifyError(
                        f"volume changed OUTSIDE the cache extents near 0x{cursor:x}"
                    )
                outside_digest.update(a[s:])
            position += len(a)
    return {
        "volume_size": source_size,
        "all_changes_within_extents": True,
        "outside_extents_sha256": outside_digest.hexdigest(),
        "extents": [{"offset": lo, "length": hi - lo} for lo, hi in extents],
    }


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    changed_entries: list[str]
    manifest: dict[str, object]


def verify_cache_patch(
    source_volume: Path,
    output_volume: Path,
    expected_catalog_index: int | None = None,
    expect_l1: bool | None = None,
) -> VerifyResult:
    if source_volume.resolve() == output_volume.resolve():
        raise VerifyError("source and output volumes are the same path")

    extents = [
        (DIR_PACK_OFFSET, DIR_PACK_OFFSET + DIR_SIZE),
        (PAYLOAD_PACK_OFFSET, PAYLOAD_PACK_OFFSET + PAYLOAD_SIZE),
    ]
    volume_diff = _diff_within_extents(source_volume, output_volume, extents)

    src_dir, src_pay = _locate_pair(source_volume)
    out_dir, out_pay = _locate_pair(output_volume)

    src_subs = _parse_directory(src_dir)
    out_subs = _parse_directory(out_dir)
    if [s.name for s in src_subs] != [s.name for s in out_subs]:
        raise VerifyError("directory entry order/names changed")

    changed_entries: list[str] = []
    entry_reports: list[dict[str, object]] = []
    dram_preserved = True
    mip_preserved = True
    for src_sub, out_sub in zip(src_subs, out_subs):
        src_a = src_pay[src_sub.stream_a : src_sub.stream_a + src_sub.len_a]
        out_a = out_pay[out_sub.stream_a : out_sub.stream_a + out_sub.len_a]
        if src_a != out_a:
            dram_preserved = False
            raise VerifyError(f"{out_sub.name} DRAM part changed")
        src_vram = _decompress_vram(
            src_pay[src_sub.stream_b : src_sub.stream_b + src_sub.len_b], f"{src_sub.name} src"
        )
        out_vram = _decompress_vram(
            out_pay[out_sub.stream_b : out_sub.stream_b + out_sub.len_b], f"{out_sub.name} out"
        )
        if src_vram[BASE_LEN:] != out_vram[BASE_LEN:]:
            mip_preserved = False
            raise VerifyError(f"{out_sub.name} packed mip tail changed")
        if src_vram[:BASE_LEN] != out_vram[:BASE_LEN]:
            changed_entries.append(out_sub.name)
            entry_reports.append(
                {
                    "name": out_sub.name,
                    "catalog_index": out_sub.catalog_index,
                    "level": out_sub.level,
                    "base_sha256_before": _sha(src_vram[:BASE_LEN]),
                    "base_sha256_after": _sha(out_vram[:BASE_LEN]),
                    "mip_tail_preserved": True,
                }
            )

    # Directory: only auxiliary records may differ (descriptors/footer/header held).
    aux_lo = 0x1688 + FILE_COUNT * 4
    aux_hi = aux_lo + FILE_COUNT * 0x10
    for offset in range(len(src_dir)):
        if src_dir[offset] == out_dir[offset]:
            continue
        if not aux_lo <= offset < aux_hi:
            raise VerifyError(f"directory changed outside auxiliary records at 0x{offset:x}")

    # Expectation checks.
    if expected_catalog_index is not None:
        expected = {f"{expected_catalog_index:02d}_logo_l0"}
        if expect_l1:
            expected.add(f"{expected_catalog_index:02d}_logo_l1")
        if set(changed_entries) != expected:
            raise VerifyError(
                f"changed entries {sorted(changed_entries)} != expected {sorted(expected)}"
            )

    catalog_indices = sorted({s.split("_logo_l")[0] for s in changed_entries})
    manifest = {
        "schema": "apf_logocache_verify/v1",
        "source_volume": str(source_volume),
        "output_volume": str(output_volume),
        "volume_diff": volume_diff,
        "directory": {
            "size": DIR_SIZE,
            "sha256_before": _sha(src_dir),
            "sha256_after": _sha(out_dir),
            "only_auxiliary_records_changed": True,
        },
        "payload": {
            "size": PAYLOAD_SIZE,
            "sha256_before": _sha(src_pay),
            "sha256_after": _sha(out_pay),
            "sub_blocks_decompressed": FILE_COUNT * 2,
        },
        "proof": {
            "every_dram_part_preserved": dram_preserved,
            "every_mip_tail_preserved": mip_preserved,
            "changed_vram_base_levels": changed_entries,
            "changed_catalog_indices": catalog_indices,
            "changed_entry_details": entry_reports,
            "all_other_bases_preserved": True,
            "outside_cache_extents_bit_identical": True,
        },
        "conclusion": {
            "bounded_cache_edit_proved": True,
            "changed_entries_match_expectation": expected_catalog_index is not None,
            "contains_replacement_bytes": False,
        },
    }
    return VerifyResult(ok=True, changed_entries=changed_entries, manifest=manifest)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="retail 0A volume")
    parser.add_argument("--output", required=True, type=Path, help="patched copied 0A volume")
    parser.add_argument("--catalog-index", type=int, help="expected edited catalog index")
    parser.add_argument("--expect-l1", action="store_true", help="expect logo_l1 also edited")
    parser.add_argument("--manifest", type=Path, help="write the verification manifest JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_cache_patch(
            args.source.expanduser(),
            args.output.expanduser(),
            args.catalog_index,
            args.expect_l1,
        )
    except (VerifyError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        print(f"APF_LOGOCACHE_VERIFY_FAIL {exc}", file=sys.stderr)
        return 1
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result.manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        "APF_LOGOCACHE_VERIFY_PASS "
        f"changed={','.join(result.changed_entries)} "
        f"outside_extents_identical=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
