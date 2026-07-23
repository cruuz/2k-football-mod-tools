#!/usr/bin/env python3
"""Bounds-checked lister for the APF 2K8 outer 0A archive table.

This tool intentionally does not extract payloads.  It reads the small directory
in the first volume, validates every sibling volume, and emits either a compact
listing or a deterministic JSON manifest.  Logical entries may span more than
one physical volume; each manifest entry therefore contains an explicit segment
list.
"""

from __future__ import annotations

import argparse
import bisect
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys
from typing import BinaryIO, Iterable


MAGIC = 0xAA00B3BF
FIXED_HEADER_SIZE = 0x18
PACK_DESCRIPTOR_SIZE = 0x10
ENTRY_RECORD_SIZE = 0x0C
MAX_PACKS = 256
MAX_ENTRIES = 1_000_000
MAX_ALIGNMENT = 1 << 24


class FormatError(ValueError):
    """Raised when an archive field is inconsistent or out of bounds."""


@dataclass(frozen=True)
class Pack:
    ordinal: int
    name: str
    size_blocks: int
    declared_size: int
    actual_size: int
    virtual_start: int
    path: Path

    @property
    def virtual_end(self) -> int:
        return self.virtual_start + self.declared_size


@dataclass(frozen=True)
class Segment:
    pack_ordinal: int
    pack_name: str
    pack_offset: int
    size: int


@dataclass(frozen=True)
class Entry:
    table_index: int
    name_id: int
    offset_blocks: int
    size_blocks: int
    virtual_offset: int
    size: int
    head_hex: str
    segments: tuple[Segment, ...]

    @property
    def virtual_end(self) -> int:
        return self.virtual_offset + self.size


@dataclass(frozen=True)
class Archive:
    index_path: Path
    alignment: int
    reserved_0c: int
    reserved_14: int
    table_start: int
    table_end: int
    packs: tuple[Pack, ...]
    entries: tuple[Entry, ...]

    @property
    def virtual_size(self) -> int:
        return self.packs[-1].virtual_end


def _read_exact(stream: BinaryIO, count: int, what: str) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise FormatError(
            f"truncated {what}: wanted {count} bytes, received {len(data)}"
        )
    return data


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _decode_pack_name(raw: bytes, ordinal: int) -> str:
    try:
        decoded = raw.decode("utf-16-be")
    except UnicodeDecodeError as exc:
        raise FormatError(f"pack {ordinal}: invalid UTF-16BE name") from exc

    name, separator, tail = decoded.partition("\0")
    if separator and tail.strip("\0"):
        raise FormatError(f"pack {ordinal}: non-NUL data follows name terminator")
    if not name:
        raise FormatError(f"pack {ordinal}: empty name")
    if (
        name in {".", ".."}
        or Path(name).name != name
        or "/" in name
        or "\\" in name
    ):
        raise FormatError(f"pack {ordinal}: unsafe sibling name {name!r}")
    return name


def _segments_for_range(
    packs: tuple[Pack, ...], starts: list[int], offset: int, size: int
) -> tuple[Segment, ...]:
    if size == 0:
        return ()

    end = offset + size
    first_pack = bisect.bisect_right(starts, offset) - 1
    if first_pack < 0 or end > packs[-1].virtual_end:
        raise FormatError(
            f"entry range 0x{offset:x}..0x{end:x} is outside virtual archive"
        )

    segments: list[Segment] = []
    for pack in packs[first_pack:]:
        segment_start = max(offset, pack.virtual_start)
        segment_end = min(end, pack.virtual_end)
        if segment_start < segment_end:
            segments.append(
                Segment(
                    pack_ordinal=pack.ordinal,
                    pack_name=pack.name,
                    pack_offset=segment_start - pack.virtual_start,
                    size=segment_end - segment_start,
                )
            )
        if segment_end == end:
            break

    if sum(segment.size for segment in segments) != size:
        raise FormatError(
            f"entry range 0x{offset:x}..0x{end:x} could not be mapped completely"
        )
    return tuple(segments)


def _read_entry_head(packs: tuple[Pack, ...], segments: tuple[Segment, ...]) -> str:
    if not segments:
        return ""
    segment = segments[0]
    pack = packs[segment.pack_ordinal]
    count = min(4, segment.size)
    with pack.path.open("rb") as stream:
        stream.seek(segment.pack_offset)
        return _read_exact(stream, count, "entry head").hex()


def parse_archive(index_path: Path) -> Archive:
    index_path = index_path.expanduser()
    try:
        index_size = index_path.stat().st_size
    except OSError as exc:
        raise FormatError(f"cannot stat index {index_path}: {exc}") from exc
    if not index_path.is_file():
        raise FormatError(f"index is not a regular file: {index_path}")

    with index_path.open("rb") as stream:
        fixed = _read_exact(stream, FIXED_HEADER_SIZE, "fixed header")
        magic, alignment, pack_count, reserved_0c, entry_count, reserved_14 = (
            struct.unpack(">6I", fixed)
        )
        if magic != MAGIC:
            raise FormatError(
                f"bad magic 0x{magic:08x}; expected 0x{MAGIC:08x}"
            )
        if alignment == 0 or alignment > MAX_ALIGNMENT:
            raise FormatError(f"implausible alignment 0x{alignment:x}")
        if alignment & (alignment - 1):
            raise FormatError(f"alignment is not a power of two: 0x{alignment:x}")
        if not 1 <= pack_count <= MAX_PACKS:
            raise FormatError(f"implausible pack count {pack_count}")
        if not 1 <= entry_count <= MAX_ENTRIES:
            raise FormatError(f"implausible entry count {entry_count}")

        table_start = FIXED_HEADER_SIZE + pack_count * PACK_DESCRIPTOR_SIZE
        table_end = table_start + entry_count * ENTRY_RECORD_SIZE
        if table_end > index_size:
            raise FormatError(
                f"directory ends at 0x{table_end:x}, beyond index size 0x{index_size:x}"
            )

        raw_packs: list[tuple[str, int]] = []
        seen_names: set[str] = set()
        for ordinal in range(pack_count):
            raw = _read_exact(stream, PACK_DESCRIPTOR_SIZE, f"pack {ordinal}")
            size_blocks, reserved, raw_name = struct.unpack(">II8s", raw)
            if reserved != 0:
                raise FormatError(
                    f"pack {ordinal}: reserved field is 0x{reserved:08x}, not zero"
                )
            name = _decode_pack_name(raw_name, ordinal)
            if name in seen_names:
                raise FormatError(f"duplicate pack name {name!r}")
            seen_names.add(name)
            if size_blocks == 0:
                raise FormatError(f"pack {ordinal} {name!r}: zero declared size")
            raw_packs.append((name, size_blocks))

        raw_entries = [
            struct.unpack(">III", _read_exact(stream, ENTRY_RECORD_SIZE, f"entry {i}"))
            for i in range(entry_count)
        ]

    packs: list[Pack] = []
    virtual_start = 0
    for ordinal, (name, size_blocks) in enumerate(raw_packs):
        declared_size = size_blocks * alignment
        pack_path = index_path.parent / name
        try:
            actual_size = pack_path.stat().st_size
        except OSError as exc:
            raise FormatError(f"cannot stat declared pack {name!r}: {exc}") from exc
        if not pack_path.is_file():
            raise FormatError(f"declared pack is not a regular file: {pack_path}")
        if actual_size != declared_size:
            raise FormatError(
                f"pack {name!r}: declared 0x{declared_size:x} bytes, "
                f"actual 0x{actual_size:x}"
            )
        packs.append(
            Pack(
                ordinal=ordinal,
                name=name,
                size_blocks=size_blocks,
                declared_size=declared_size,
                actual_size=actual_size,
                virtual_start=virtual_start,
                path=pack_path,
            )
        )
        virtual_start += declared_size

    pack_tuple = tuple(packs)
    if index_path.name != pack_tuple[0].name:
        raise FormatError(
            f"index basename {index_path.name!r} does not match first descriptor "
            f"{pack_tuple[0].name!r}"
        )

    starts = [pack.virtual_start for pack in pack_tuple]
    entries: list[Entry] = []
    for table_index, (name_id, offset_blocks, size_blocks) in enumerate(raw_entries):
        virtual_offset = offset_blocks * alignment
        size = size_blocks * alignment
        if size == 0:
            raise FormatError(f"entry {table_index}: zero size")
        segments = _segments_for_range(pack_tuple, starts, virtual_offset, size)
        entries.append(
            Entry(
                table_index=table_index,
                name_id=name_id,
                offset_blocks=offset_blocks,
                size_blocks=size_blocks,
                virtual_offset=virtual_offset,
                size=size,
                head_hex=_read_entry_head(pack_tuple, segments),
                segments=segments,
            )
        )

    return Archive(
        index_path=index_path,
        alignment=alignment,
        reserved_0c=reserved_0c,
        reserved_14=reserved_14,
        table_start=table_start,
        table_end=table_end,
        packs=pack_tuple,
        entries=tuple(entries),
    )


def _validation(archive: Archive) -> dict[str, object]:
    ordered = sorted(archive.entries, key=lambda entry: entry.virtual_offset)
    overlap_count = 0
    gap_count = 0
    gap_bytes = 0
    previous_end = 0
    for entry in ordered:
        if entry.virtual_offset < previous_end:
            overlap_count += 1
        elif entry.virtual_offset > previous_end:
            gap_count += 1
            gap_bytes += entry.virtual_offset - previous_end
        previous_end = max(previous_end, entry.virtual_end)

    table_offset_decreases = sum(
        current.virtual_offset < previous.virtual_offset
        for previous, current in zip(archive.entries, archive.entries[1:])
    )
    duplicate_ids = sum(
        count - 1
        for count in Counter(entry.name_id for entry in archive.entries).values()
        if count > 1
    )
    first_payload = ordered[0].virtual_offset if ordered else None
    return {
        "all_pack_sizes_match": True,
        "all_entry_ranges_in_bounds": True,
        "duplicate_name_id_count": duplicate_ids,
        "entry_overlap_count": overlap_count,
        "gap_count_including_leading_gap": gap_count,
        "gap_bytes_including_leading_gap": gap_bytes,
        "first_payload_offset": first_payload,
        "aligned_table_end": _align_up(archive.table_end, archive.alignment),
        "coverage_end": previous_end,
        "coverage_reaches_virtual_end": previous_end == archive.virtual_size,
        "table_offset_decrease_count": table_offset_decreases,
        "cross_volume_entry_count": sum(
            len(entry.segments) > 1 for entry in archive.entries
        ),
    }


def manifest(archive: Archive) -> dict[str, object]:
    magic_counts = Counter(entry.head_hex for entry in archive.entries)
    return {
        "schema": "apf_outer_manifest/v1",
        "source_index": str(archive.index_path),
        "format": {
            "byte_order": "big",
            "magic": f"0x{MAGIC:08x}",
            "alignment": archive.alignment,
            "pack_count": len(archive.packs),
            "entry_count": len(archive.entries),
            "reserved_0c": archive.reserved_0c,
            "reserved_14": archive.reserved_14,
            "pack_descriptor_size": PACK_DESCRIPTOR_SIZE,
            "entry_record_size": ENTRY_RECORD_SIZE,
            "table_start": archive.table_start,
            "table_end": archive.table_end,
            "virtual_size": archive.virtual_size,
        },
        "validation": _validation(archive),
        "entry_head_hex_counts": dict(sorted(magic_counts.items())),
        "packs": [
            {
                "ordinal": pack.ordinal,
                "name": pack.name,
                "size_blocks": pack.size_blocks,
                "declared_size": pack.declared_size,
                "actual_size": pack.actual_size,
                "virtual_start": pack.virtual_start,
                "virtual_end": pack.virtual_end,
            }
            for pack in archive.packs
        ],
        "entries": [
            {
                "table_index": entry.table_index,
                "name_id": f"0x{entry.name_id:08x}",
                "offset_blocks": entry.offset_blocks,
                "size_blocks": entry.size_blocks,
                "virtual_offset": entry.virtual_offset,
                "virtual_end": entry.virtual_end,
                "size": entry.size,
                "head_hex": entry.head_hex,
                "segments": [
                    {
                        "pack_ordinal": segment.pack_ordinal,
                        "pack_name": segment.pack_name,
                        "pack_offset": segment.pack_offset,
                        "size": segment.size,
                    }
                    for segment in entry.segments
                ],
            }
            for entry in archive.entries
        ],
    }


def _format_segments(segments: Iterable[Segment]) -> str:
    return ",".join(
        f"{segment.pack_name}:0x{segment.pack_offset:x}+0x{segment.size:x}"
        for segment in segments
    )


def print_listing(archive: Archive, order: str) -> None:
    entries = archive.entries
    if order == "offset":
        entries = tuple(sorted(entries, key=lambda entry: entry.virtual_offset))
    print("table_index\tname_id\tvirtual_offset\tsize\thead_hex\tsegments")
    for entry in entries:
        print(
            f"{entry.table_index}\t0x{entry.name_id:08x}\t"
            f"0x{entry.virtual_offset:x}\t0x{entry.size:x}\t{entry.head_hex}\t"
            f"{_format_segments(entry.segments)}"
        )


def print_summary(archive: Archive) -> None:
    checks = _validation(archive)
    print(
        f"APF outer archive: {len(archive.entries)} entries, "
        f"{len(archive.packs)} packs, alignment 0x{archive.alignment:x}, "
        f"virtual size 0x{archive.virtual_size:x}"
    )
    print(
        f"table 0x{archive.table_start:x}..0x{archive.table_end:x}; "
        f"first payload 0x{checks['first_payload_offset']:x}; "
        f"cross-volume entries {checks['cross_volume_entry_count']}"
    )
    for pack in archive.packs:
        print(
            f"pack {pack.ordinal}: {pack.name} "
            f"virtual 0x{pack.virtual_start:x}..0x{pack.virtual_end:x} "
            f"({pack.declared_size} bytes)"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to the first APF volume (0A)")
    parser.add_argument(
        "--list", action="store_true", help="print one tab-separated row per entry"
    )
    parser.add_argument(
        "--order",
        choices=("offset", "table"),
        default="offset",
        help="listing order (default: offset)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        metavar="PATH",
        help="write deterministic JSON metadata; use - for standard output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list and args.manifest == Path("-"):
        print(
            "error: --list and --manifest - cannot share standard output",
            file=sys.stderr,
        )
        return 2
    try:
        archive = parse_archive(args.index)
        if args.list:
            print_listing(archive, args.order)
        elif args.manifest != Path("-"):
            print_summary(archive)
        if args.manifest is not None:
            document = json.dumps(manifest(archive), indent=2, sort_keys=False) + "\n"
            if args.manifest == Path("-"):
                sys.stdout.write(document)
            else:
                args.manifest.parent.mkdir(parents=True, exist_ok=True)
                args.manifest.write_text(document, encoding="utf-8")
    except BrokenPipeError:
        return 0
    except (FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
