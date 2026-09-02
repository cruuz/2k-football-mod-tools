#!/usr/bin/env python3
"""Read and verify one APF ``Roster.ROS`` payload from an STFS container.

This module is deliberately extraction-only.  It recognizes CON, LIVE, and
PIRS XContent packages, verifies the metadata hash, the active STFS hash-table
chain, and every extracted data block, then returns the one unambiguous
``Roster.ROS`` entry.  It never writes a container, rehashes one, or claims to
verify its RSA signature.

LIVE/PIRS packages require Microsoft's private signing keys after mutation.
CON packages require the owning console's private keyvault.  Neither key is
part of Mod Studio, so signed-container reinjection remains outside this
module's authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import struct


STFS_MAGICS = (b"CON ", b"LIVE", b"PIRS")
BLOCK_SIZE = 0x1000
HASHES_PER_TABLE = 0xAA
MAX_ALLOCATED_BLOCKS = HASHES_PER_TABLE * HASHES_PER_TABLE
MAX_CONTAINER_BYTES = 128 * 1024 * 1024
MAX_ROSTER_BYTES = 32 * 1024 * 1024
MAX_FILE_TABLE_BLOCKS = 1024
MAX_DIRECTORY_ENTRIES = MAX_FILE_TABLE_BLOCKS * 0x40
END_OF_CHAIN = 0xFFFFFF


class StfsRosterError(ValueError):
    """The package is unsupported, corrupt, ambiguous, or unsafe to extract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StfsRosterError(message)


@dataclass(frozen=True)
class StfsFileEntry:
    index: int
    path: str
    flags: int
    block_count: int
    starting_block: int
    parent_index: int
    file_size: int
    entry_offset: int

    @property
    def is_directory(self) -> bool:
        return bool(self.flags & 2)

    @property
    def consecutive(self) -> bool:
        return bool(self.flags & 1)


@dataclass(frozen=True)
class StfsRosterPayload:
    package_kind: str
    entry: StfsFileEntry
    payload: bytes
    metadata_hash_verified: bool
    hash_tree_verified: bool
    data_blocks_verified: int
    rsa_signature_verified: bool = False


@dataclass(frozen=True)
class _HashEntry:
    digest: bytes
    status: int
    next_block: int


def _slice(data: bytes, start: int, length: int, label: str) -> bytes:
    require(start >= 0 and length >= 0 and start <= len(data) - length,
            f"{label} exceeds the STFS package")
    return data[start : start + length]


def _u16le(data: bytes, offset: int, label: str) -> int:
    return struct.unpack("<H", _slice(data, offset, 2, label))[0]


def _u16be(data: bytes, offset: int, label: str) -> int:
    return struct.unpack(">H", _slice(data, offset, 2, label))[0]


def _u24le(data: bytes, offset: int, label: str) -> int:
    return int.from_bytes(_slice(data, offset, 3, label), "little")


def _u24be(data: bytes, offset: int, label: str) -> int:
    return int.from_bytes(_slice(data, offset, 3, label), "big")


def _u32be(data: bytes, offset: int, label: str) -> int:
    return struct.unpack(">I", _slice(data, offset, 4, label))[0]


class _StfsReader:
    def __init__(self, data: bytes):
        require(isinstance(data, bytes), "STFS input must be immutable bytes")
        require(0xA000 <= len(data) <= MAX_CONTAINER_BYTES,
                "STFS package size is outside the bounded save-container range")
        magic = data[:4]
        require(magic in STFS_MAGICS, "input is not a CON, LIVE, or PIRS package")
        self.data = data
        self.package_kind = magic.decode("ascii").strip()

        self.header_size = _u32be(data, 0x340, "XContent header size")
        require(0x971A <= self.header_size <= len(data),
                "XContent header size is invalid")
        self.first_table_address = (self.header_size + 0xFFF) & ~0xFFF
        require(self.first_table_address <= len(data) - BLOCK_SIZE,
                "STFS package has no complete first hash table")
        stored_metadata_hash = _slice(data, 0x32C, 0x14, "metadata hash")
        calculated_metadata_hash = hashlib.sha1(
            _slice(
                data,
                0x344,
                self.first_table_address - 0x344,
                "hashed XContent metadata",
            )
        ).digest()
        require(stored_metadata_hash == calculated_metadata_hash,
                "XContent metadata SHA-1 does not match")

        require(_u32be(data, 0x3A9, "filesystem type") == 0,
                "XContent package does not contain an STFS filesystem")
        require(data[0x379] == 0x24, "STFS volume descriptor size changed")
        self.block_separation = data[0x37B]
        self.file_table_block_count = _u16le(
            data, 0x37C, "file-table block count"
        )
        self.file_table_start = _u24le(data, 0x37E, "file-table start block")
        self.top_hash = _slice(data, 0x381, 0x14, "top hash-table hash")
        self.allocated_blocks = _u32be(data, 0x395, "allocated block count")
        require(1 <= self.allocated_blocks <= MAX_ALLOCATED_BLOCKS,
                "STFS allocated-block count exceeds the bounded extractor")
        require(1 <= self.file_table_block_count <= MAX_FILE_TABLE_BLOCKS,
                "STFS file-table block count is invalid")
        require(self.file_table_start < self.allocated_blocks,
                "STFS file-table start block is unallocated")

        # STFS calls the one-table layout "female" and the duplicated-table
        # layout "male".  Only the bit and the resulting block steps matter.
        self.sex = 0 if self.block_separation & 1 else 1
        self.block_step = (0xAB, 0x718F) if self.sex == 0 else (0xAC, 0x723A)
        self.top_level = 0 if self.allocated_blocks <= HASHES_PER_TABLE else 1
        top_true_block = 0 if self.top_level == 0 else self.block_step[0]
        self.top_table_address = (
            self.first_table_address
            + top_true_block * BLOCK_SIZE
            + ((self.block_separation & 2) << 11)
        )
        self.top_table = _slice(
            data, self.top_table_address, BLOCK_SIZE, "active top hash table"
        )
        require(hashlib.sha1(self.top_table).digest() == self.top_hash,
                "active top STFS hash table does not match the volume descriptor")
        self.top_entry_count = (
            self.allocated_blocks
            if self.top_level == 0
            else (self.allocated_blocks + HASHES_PER_TABLE - 1)
            // HASHES_PER_TABLE
        )
        require(self.top_entry_count <= HASHES_PER_TABLE,
                "top STFS hash table has too many entries")
        self.top_entries = tuple(
            self._parse_hash_entry(self.top_table, index * 0x18, "top hash entry")
            for index in range(self.top_entry_count)
        )
        self._level_zero_tables: dict[int, bytes] = {}
        self._verified_data_blocks: set[int] = set()

    @staticmethod
    def _parse_hash_entry(data: bytes, offset: int, label: str) -> _HashEntry:
        raw = _slice(data, offset, 0x18, label)
        return _HashEntry(raw[:0x14], raw[0x14], _u24be(raw, 0x15, label))

    def _first_level_backing_block(self, block: int) -> int:
        if block < HASHES_PER_TABLE:
            return 0
        value = (block // HASHES_PER_TABLE) * self.block_step[0]
        value += ((block // (HASHES_PER_TABLE**3)) + 1) << self.sex
        if block // (HASHES_PER_TABLE**3):
            value += 1 << self.sex
        return value

    def _data_backing_block(self, block: int) -> int:
        require(0 <= block < self.allocated_blocks,
                f"STFS data block {block} is unallocated")
        address = (
            ((block + HASHES_PER_TABLE) // HASHES_PER_TABLE) << self.sex
        ) + block
        if block < HASHES_PER_TABLE:
            return address
        if block < HASHES_PER_TABLE**2:
            return (
                address
                + (address + HASHES_PER_TABLE**2) // (HASHES_PER_TABLE**2)
            ) << self.sex
        raise StfsRosterError("STFS block requires an unsupported third-level hash tree")

    def block_address(self, block: int) -> int:
        address = self.first_table_address + self._data_backing_block(block) * BLOCK_SIZE
        _slice(self.data, address, BLOCK_SIZE, f"STFS data block {block}")
        return address

    def _level_zero_table(self, block: int) -> bytes:
        table_index = block // HASHES_PER_TABLE
        cached = self._level_zero_tables.get(table_index)
        if cached is not None:
            return cached
        if self.top_level == 0:
            table = self.top_table
        else:
            require(table_index < len(self.top_entries),
                    "STFS block has no parent hash entry")
            parent = self.top_entries[table_index]
            require(parent.status & 0x80,
                    "STFS level-zero hash table is not allocated")
            base = (
                self.first_table_address
                + self._first_level_backing_block(block) * BLOCK_SIZE
                + ((parent.status & 0x40) << 6)
            )
            table = _slice(
                self.data, base, BLOCK_SIZE,
                f"active level-zero hash table {table_index}",
            )
            require(hashlib.sha1(table).digest() == parent.digest,
                    f"STFS level-zero hash table {table_index} does not match its parent")
        self._level_zero_tables[table_index] = table
        return table

    def hash_entry(self, block: int) -> _HashEntry:
        require(0 <= block < self.allocated_blocks,
                f"STFS data block {block} is unallocated")
        table = self._level_zero_table(block)
        entry = self._parse_hash_entry(
            table, (block % HASHES_PER_TABLE) * 0x18,
            f"data-block hash entry {block}",
        )
        require(entry.status & 0x80, f"STFS data block {block} is not allocated")
        return entry

    def read_verified_block(self, block: int) -> bytes:
        entry = self.hash_entry(block)
        payload = _slice(
            self.data, self.block_address(block), BLOCK_SIZE,
            f"STFS data block {block}",
        )
        require(hashlib.sha1(payload).digest() == entry.digest,
                f"STFS data block {block} SHA-1 does not match")
        self._verified_data_blocks.add(block)
        return payload

    def directory_entries(self) -> tuple[StfsFileEntry, ...]:
        raw_rows: list[tuple[int, str, int, int, int, int, int, int]] = []
        block = self.file_table_start
        visited: set[int] = set()
        for block_index in range(self.file_table_block_count):
            require(block not in visited, "STFS file-table block chain contains a cycle")
            visited.add(block)
            block_data = self.read_verified_block(block)
            block_address = self.block_address(block)
            for row_index in range(0x40):
                offset = row_index * 0x40
                name_length_flags = block_data[offset + 0x28]
                name_length = name_length_flags & 0x3F
                if name_length == 0:
                    continue
                require(name_length <= 0x28, "STFS directory name exceeds 40 bytes")
                name_bytes = block_data[offset : offset + name_length]
                require(b"/" not in name_bytes and b"\\" not in name_bytes
                        and b"\0" not in name_bytes,
                        "STFS directory entry contains an unsafe path character")
                try:
                    name = name_bytes.decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise StfsRosterError("STFS directory name is not UTF-8") from exc
                require(name not in (".", ".."),
                        "STFS directory entry contains a traversal component")
                block_count = _u24le(block_data, offset + 0x29, "entry block count")
                duplicate_count = _u24le(
                    block_data, offset + 0x2C, "duplicate entry block count"
                )
                require(block_count == duplicate_count,
                        "STFS directory entry block counts disagree")
                starting_block = _u24le(
                    block_data, offset + 0x2F, "entry start block"
                )
                parent = _u16be(block_data, offset + 0x32, "entry parent index")
                file_size = _u32be(block_data, offset + 0x34, "entry file size")
                flags = name_length_flags >> 6
                index = block_index * 0x40 + row_index
                require(len(raw_rows) < MAX_DIRECTORY_ENTRIES,
                        "STFS package has too many directory entries")
                if flags & 2:
                    require(file_size == 0, "STFS directory entry has file data")
                else:
                    expected_blocks = (file_size + BLOCK_SIZE - 1) // BLOCK_SIZE
                    require(block_count == expected_blocks,
                            f"STFS file {name!r} has inconsistent block count")
                    require(file_size <= MAX_CONTAINER_BYTES,
                            f"STFS file {name!r} exceeds the extraction bound")
                    if block_count:
                        require(starting_block < self.allocated_blocks,
                                f"STFS file {name!r} starts in an unallocated block")
                raw_rows.append(
                    (
                        index, name, flags, block_count, starting_block,
                        parent, file_size, block_address + offset,
                    )
                )

            next_block = self.hash_entry(block).next_block
            if block_index + 1 == self.file_table_block_count:
                require(next_block == END_OF_CHAIN,
                        "STFS file-table chain continues past its declared length")
            else:
                require(next_block != END_OF_CHAIN,
                        "STFS file-table chain ended early")
                block = next_block

        by_index = {row[0]: row for row in raw_rows}
        require(len(by_index) == len(raw_rows), "STFS directory indices repeat")
        resolved: dict[int, str] = {}
        resolving: set[int] = set()

        def resolve(index: int) -> str:
            cached = resolved.get(index)
            if cached is not None:
                return cached
            require(index not in resolving, "STFS directory parent graph contains a cycle")
            resolving.add(index)
            row = by_index[index]
            parent = row[5]
            if parent == 0xFFFF:
                path = row[1]
            else:
                require(parent in by_index,
                        f"STFS directory entry {row[1]!r} has a missing parent")
                require(by_index[parent][2] & 2,
                        f"STFS directory entry {row[1]!r} parent is not a directory")
                path = f"{resolve(parent)}/{row[1]}"
            resolving.remove(index)
            resolved[index] = path
            return path

        entries = tuple(
            StfsFileEntry(
                index=row[0],
                path=resolve(row[0]),
                flags=row[2],
                block_count=row[3],
                starting_block=row[4],
                parent_index=row[5],
                file_size=row[6],
                entry_offset=row[7],
            )
            for row in raw_rows
        )
        paths = [entry.path.casefold() for entry in entries]
        require(len(paths) == len(set(paths)), "STFS directory paths are not unique")
        return entries

    def extract(self, entry: StfsFileEntry) -> bytes:
        require(not entry.is_directory, "cannot extract an STFS directory")
        require(entry.file_size <= MAX_ROSTER_BYTES,
                "Roster.ROS payload exceeds the bounded extraction size")
        if entry.file_size == 0:
            return b""
        blocks: list[int] = []
        if entry.consecutive:
            blocks = [entry.starting_block + index for index in range(entry.block_count)]
            require(blocks[-1] < self.allocated_blocks,
                    "consecutive STFS file exceeds allocated blocks")
        else:
            block = entry.starting_block
            seen: set[int] = set()
            for index in range(entry.block_count):
                require(block not in seen, "STFS file block chain contains a cycle")
                seen.add(block)
                blocks.append(block)
                following = self.hash_entry(block).next_block
                if index + 1 == entry.block_count:
                    require(following == END_OF_CHAIN,
                            "STFS file block chain continues past its declared length")
                else:
                    require(following != END_OF_CHAIN,
                            "STFS file block chain ended early")
                    block = following
        output = b"".join(self.read_verified_block(block) for block in blocks)
        return output[: entry.file_size]


def list_files(data: bytes) -> tuple[str, tuple[StfsFileEntry, ...]]:
    reader = _StfsReader(data)
    return reader.package_kind, reader.directory_entries()


def extract_roster_payload(data: bytes) -> StfsRosterPayload:
    reader = _StfsReader(data)
    files = tuple(
        entry
        for entry in reader.directory_entries()
        if not entry.is_directory
        and PurePosixPath(entry.path).name.casefold() == "roster.ros"
    )
    require(len(files) == 1,
            f"expected exactly one Roster.ROS payload in STFS package, found {len(files)}")
    entry = files[0]
    payload = reader.extract(entry)
    require(bool(payload), "Roster.ROS payload is empty")
    return StfsRosterPayload(
        package_kind=reader.package_kind,
        entry=entry,
        payload=payload,
        metadata_hash_verified=True,
        hash_tree_verified=True,
        data_blocks_verified=len(reader._verified_data_blocks),
    )


__all__ = [
    "MAX_CONTAINER_BYTES",
    "MAX_ROSTER_BYTES",
    "STFS_MAGICS",
    "StfsFileEntry",
    "StfsRosterError",
    "StfsRosterPayload",
    "extract_roster_payload",
    "list_files",
]
