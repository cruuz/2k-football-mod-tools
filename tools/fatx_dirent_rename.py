#!/usr/bin/env python3
"""Locate or equal-length-rename one FATX directory entry in a raw Xbox HDD.

This intentionally supports only the fixed original-Xbox 8 GiB partition map
used by xemu HDD images.  It never edits FAT chains or file data.  A rename is
allowed only when the replacement is ASCII, the same byte length, and the
target path resolves uniquely in an already existing directory tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import struct


FATX_SIGNATURE = 0x58544146
FATX_PAGE_SIZE = 0x1000
FATX_SECTOR_SIZE = 0x200
FILE_ATTRIBUTE_DIRECTORY = 0x10
DIRENT_DELETED = 0xE5
DIRENT_END = {0x00, 0xFF}
DIRENT_SIZE = 0x40

PARTITIONS = {
    "X": (0x00080000, 0x2EE00000),
    "Y": (0x2EE80000, 0x2EE00000),
    "Z": (0x5DC80000, 0x2EE00000),
    "C": (0x8CA80000, 0x1F400000),
    "E": (0xABE80000, 0x1312D6000),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Dirent:
    name: str
    attributes: int
    first_cluster: int
    file_size: int
    offset: int
    raw: bytes

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & FILE_ATTRIBUTE_DIRECTORY)


class FatXVolume:
    def __init__(self, image, offset: int, length: int):
        self.image = image
        self.offset = offset
        self.length = length
        image.seek(offset)
        header = image.read(16)
        if len(header) != 16:
            raise ValueError("short FATX volume header")
        signature, self.serial, sectors_per_cluster, self.root_cluster = (
            struct.unpack("<LLLL", header)
        )
        if signature != FATX_SIGNATURE:
            raise ValueError(
                f"invalid FATX signature at 0x{offset:x}: 0x{signature:08x}"
            )
        self.bytes_per_cluster = sectors_per_cluster * FATX_SECTOR_SIZE
        if self.bytes_per_cluster <= 0:
            raise ValueError("invalid FATX cluster size")
        self.max_clusters = (length // self.bytes_per_cluster) + 1
        self.fat16 = self.max_clusters < 0xFFF0
        fat_entry_size = 2 if self.fat16 else 4
        fat_size = self.max_clusters * fat_entry_size
        fat_size = (fat_size + FATX_PAGE_SIZE - 1) & ~(FATX_PAGE_SIZE - 1)
        self.fat_offset = FATX_PAGE_SIZE
        self.file_area_offset = self.fat_offset + fat_size
        image.seek(offset + self.fat_offset)
        fat_bytes = image.read(self.max_clusters * fat_entry_size)
        if len(fat_bytes) != self.max_clusters * fat_entry_size:
            raise ValueError("short FATX allocation table")
        code = "H" if self.fat16 else "L"
        self.fat = struct.unpack(f"<{self.max_clusters}{code}", fat_bytes)

    def cluster_offset(self, cluster: int) -> int:
        if cluster < 1 or cluster >= self.max_clusters:
            raise ValueError(f"FATX cluster out of range: {cluster}")
        return (
            self.offset
            + self.file_area_offset
            + self.bytes_per_cluster * (cluster - 1)
        )

    def cluster_chain(self, first: int) -> list[int]:
        chain: list[int] = []
        current = first
        seen: set[int] = set()
        reserved = 0xFFF0 if self.fat16 else 0xFFFFFFF0
        while True:
            if current in seen:
                raise ValueError(f"FATX cluster loop at {current}")
            if current < 1 or current >= self.max_clusters:
                raise ValueError(f"FATX cluster out of range: {current}")
            seen.add(current)
            chain.append(current)
            nxt = self.fat[current]
            if nxt >= reserved:
                return chain
            if nxt == 0:
                raise ValueError(f"unexpected free FATX cluster after {current}")
            current = nxt

    def read_directory(self, first_cluster: int) -> list[Dirent]:
        entries: list[Dirent] = []
        ended = False
        for cluster in self.cluster_chain(first_cluster):
            base = self.cluster_offset(cluster)
            self.image.seek(base)
            data = self.image.read(self.bytes_per_cluster)
            if len(data) != self.bytes_per_cluster:
                raise ValueError(f"short FATX directory cluster {cluster}")
            for relative in range(0, self.bytes_per_cluster, DIRENT_SIZE):
                raw = data[relative : relative + DIRENT_SIZE]
                if len(raw) != DIRENT_SIZE:
                    raise ValueError("partial FATX directory entry")
                name_length, attributes, name_raw, first, size, *_ = struct.unpack(
                    "<BB42sLLLLL", raw
                )
                if name_length in DIRENT_END:
                    ended = True
                    break
                if name_length == DIRENT_DELETED:
                    continue
                if not 1 <= name_length <= 42:
                    raise ValueError(
                        f"invalid FATX name length {name_length} at 0x{base + relative:x}"
                    )
                encoded = name_raw[:name_length]
                try:
                    name = encoded.decode("ascii")
                except UnicodeDecodeError as error:
                    raise ValueError(
                        f"non-ASCII FATX name at 0x{base + relative:x}"
                    ) from error
                entries.append(
                    Dirent(
                        name=name,
                        attributes=attributes,
                        first_cluster=first,
                        file_size=size,
                        offset=base + relative,
                        raw=raw,
                    )
                )
            if ended:
                break
        return entries

    def resolve(self, components: list[str]) -> Dirent:
        entries = self.read_directory(self.root_cluster)
        current: Dirent | None = None
        walked: list[str] = []
        for index, component in enumerate(components):
            matches = [e for e in entries if e.name.casefold() == component.casefold()]
            if len(matches) != 1:
                where = "/" + "/".join(walked)
                raise ValueError(
                    f"expected one {component!r} under {where or '/'}, found {len(matches)}"
                )
            current = matches[0]
            walked.append(current.name)
            if index + 1 != len(components):
                if not current.is_directory:
                    raise ValueError(f"intermediate FATX entry is not a directory: {current.name}")
                entries = self.read_directory(current.first_cluster)
        if current is None:
            raise ValueError("empty FATX path")
        return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--partition", choices=sorted(PARTITIONS), default="E")
    parser.add_argument("--path", required=True, help="absolute FATX path")
    parser.add_argument("--rename-to")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.image.is_file() or args.image.is_symlink():
        raise SystemExit("image must be a regular non-symlink file")
    components = [part for part in args.path.split("/") if part]
    if not components:
        raise SystemExit("path must contain at least one component")
    mode = "r+b" if args.apply else "rb"
    partition_offset, partition_length = PARTITIONS[args.partition]
    with args.image.open(mode) as image:
        image.seek(0, os.SEEK_END)
        image_size = image.tell()
        if image_size != 8 * 1024**3:
            raise SystemExit(f"expected an 8 GiB raw image, got {image_size}")
        if partition_offset + partition_length > image_size:
            partition_length = image_size - partition_offset
        volume = FatXVolume(image, partition_offset, partition_length)
        target = volume.resolve(components)
        result = {
            "image": str(args.image),
            "partition": args.partition,
            "path": "/" + "/".join(components),
            "dirent_offset": target.offset,
            "dirent_offset_hex": f"0x{target.offset:x}",
            "name": target.name,
            "is_directory": target.is_directory,
            "first_cluster": target.first_cluster,
            "file_size": target.file_size,
            "dirent_sha256_before": sha256(target.raw),
            "applied": False,
        }
        if args.rename_to is not None:
            try:
                replacement = args.rename_to.encode("ascii")
            except UnicodeEncodeError as error:
                raise SystemExit("replacement name must be ASCII") from error
            original = target.name.encode("ascii")
            if len(replacement) != len(original):
                raise SystemExit("replacement must have the same byte length")
            if replacement == original:
                raise SystemExit("replacement must differ from original")
            if not args.apply:
                result["rename_to"] = args.rename_to
                result["changed_byte_count"] = sum(
                    left != right for left, right in zip(original, replacement)
                )
            else:
                image.seek(target.offset + 2)
                on_disk = image.read(len(original))
                if on_disk != original:
                    raise SystemExit("target name changed before write")
                image.seek(target.offset + 2)
                image.write(replacement)
                image.flush()
                os.fsync(image.fileno())
                image.seek(target.offset)
                after = image.read(DIRENT_SIZE)
                if after[2 : 2 + len(replacement)] != replacement:
                    raise SystemExit("FATX rename verification failed")
                expected = bytearray(target.raw)
                expected[2 : 2 + len(replacement)] = replacement
                if after != bytes(expected):
                    raise SystemExit("unexpected bytes changed inside FATX dirent")
                result.update(
                    {
                        "rename_to": args.rename_to,
                        "changed_byte_count": sum(
                            left != right for left, right in zip(original, replacement)
                        ),
                        "dirent_sha256_after": sha256(after),
                        "applied": True,
                    }
                )
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
