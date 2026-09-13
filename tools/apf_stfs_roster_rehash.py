"""Fixed-size Roster.ROS replacement with an active STFS SHA-1 tree rebuild.

Xenia only; a real console will reject this package. No RSA signature is made
or validated. See docs/research/apf_stfs_rehash.md for the pinned Xenia reader
audit and the precise offline proof boundary. Emulator/game loading is
UNWITNESSED. This module never opens a file for writing.
"""
from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

import apf_stfs_roster_extract as stfs

SCHEMA = "apf2k8_stfs_roster_rehash/v1"
XENIA_ONLY = "Xenia only; a real console will reject this package"
RUNTIME = "UNWITNESSED: package discovery and in-game loading have not been tested"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inventory(source: bytes):
    reader = stfs._StfsReader(source)
    stfs.require(stfs._u32be(source, 0x344, "content type") == 1
                 and stfs._u32be(source, 0x360, "title ID") == 0x54540807,
                 "Package metadata is not an APF saved game; use raw Roster.ROS")
    stfs.require(stfs._u32be(source, 0x39D, "data file count") == 0,
                 "Multi-file STFS packages are unsupported; use an extracted Roster.ROS")
    # This pinned Xenia revision selects the next level at exact thresholds.
    stfs.require(reader.allocated_blocks not in (170, 28900),
                 "Xenia hash-level boundary is ambiguous for this allocation; use raw Roster.ROS")
    stfs.require(reader.sex or not reader.block_separation & 2,
                 "Single-copy STFS package selects a nonexistent secondary table")
    entries = reader.directory_entries()
    for index, entry in enumerate(entries):
        # Xenia stops at the first empty row and indexes parents in its packed
        # vector. Sparse rows or a child preceding its parent are not equivalent.
        stfs.require(entry.index == index and (
            entry.parent_index == 0xFFFF or entry.parent_index < index),
            "STFS directory order disagrees with Xenia traversal; use raw Roster.ROS")
    rosters = [e for e in entries if not e.is_directory
               and PurePosixPath(e.path).name.casefold() == "roster.ros"]
    stfs.require(len(rosters) == 1, "Choose a package containing exactly one Roster.ROS")
    roster = rosters[0]
    stfs.require(0 < roster.file_size <= stfs.MAX_ROSTER_BYTES, "Roster.ROS size is unsupported")
    # Account for ALL directory and file allocations. A malformed package must
    # not let a roster write silently change another file or its directory.
    owners: set[int] = set()
    block = reader.file_table_start
    for _ in range(reader.file_table_block_count):
        owners.add(block)
        block = reader.hash_entry(block).next_block
    for entry in entries:
        if entry.is_directory:
            continue
        blocks = reader.file_blocks(entry)
        stfs.require(not owners.intersection(blocks), "STFS files or directory share data blocks")
        owners.update(blocks)
        for index, block in enumerate(blocks):
            reader.read_verified_block(block)
            # Xenia ReadEntry follows next pointers even on contiguous files.
            expected = blocks[index + 1] if index + 1 < len(blocks) else stfs.END_OF_CHAIN
            stfs.require(reader.hash_entry(block).next_block == expected,
                         "STFS file chain disagrees with Xenia traversal; use raw Roster.ROS")
    # Verify every active leaf table and every allocated data entry, including
    # allocations not referenced by a directory entry. Preserve unused entries.
    for block in range(reader.allocated_blocks):
        table = reader._level_zero_table(block)
        entry = reader._parse_hash_entry(table, block % 170 * 24, "allocation")
        if entry.status & 0x80:
            reader.read_verified_block(block)
    return reader, roster


def _replace(source: bytes, payload: bytes) -> tuple[bytes, dict]:
    reader, roster = _inventory(source)
    stfs.require(len(payload) == roster.file_size,
                 "STFS replacement must retain Roster.ROS length; use a raw roster output")
    output = bytearray(source)
    changed_blocks = []
    changed_tables: set[int] = set()
    for index, block in enumerate(reader.file_blocks(roster)):
        start = index * stfs.BLOCK_SIZE
        chunk = payload[start:start + stfs.BLOCK_SIZE]
        address = reader.block_address(block)
        if source[address:address + len(chunk)] == chunk:
            continue
        output[address:address + len(chunk)] = chunk  # retain last-block padding
        leaf = reader.level_zero_address(block)
        entry = leaf + block % 170 * 24
        output[entry:entry + 20] = hashlib.sha1(output[address:address + 4096]).digest()
        changed_blocks.append(block)
        changed_tables.add(leaf)
    stfs.require(bool(changed_blocks), "Roster.ROS already matches; no rehashed package is needed")
    if reader.top_level == 1:
        for table_index in sorted({block // 170 for block in changed_blocks}):
            leaf = reader.level_zero_address(table_index * 170)
            entry = reader.top_table_address + table_index * 24
            output[entry:entry + 20] = hashlib.sha1(output[leaf:leaf + 4096]).digest()
        if changed_tables:
            changed_tables.add(reader.top_table_address)
    top = reader.top_table_address
    output[0x381:0x395] = hashlib.sha1(output[top:top + 4096]).digest()
    output[0x32C:0x340] = hashlib.sha1(output[0x344:reader.first_table_address]).digest()
    result = bytes(output)
    return result, {
        "schema": SCHEMA, "label": XENIA_ONLY,
        "source_sha256": _sha(source), "output_sha256": _sha(result),
        "payload_sha256": _sha(payload), "member": roster.path,
        "package_kind": reader.package_kind, "size": len(result),
        "data_blocks_rehashed": changed_blocks,
        "hash_table_addresses_rehashed": sorted(changed_tables),
        "header_hash_range": [0x344, reader.first_table_address],
        "signature_bytes_preserved": source[4:0x22C] == result[4:0x22C],
        "rsa_signature_verified": False, "console_resigned": False,
        "xenia_signature_check": "PROVED absent in the pinned local reader; see apf_stfs_rehash.md",
        "runtime": RUNTIME,
    }


def rehash_roster(source: bytes, payload: bytes) -> tuple[bytes, dict]:
    output, receipt = _replace(source, payload)
    receipt["verification"] = verify_rehash(source, output, receipt)
    return output, receipt


def verify_rehash(source: bytes, output: bytes, receipt: dict) -> dict:
    """Reparse the output, verify active hashes, and reject every extra mutation."""
    parsed = stfs.extract_roster_payload(output)
    expected, expected_receipt = _replace(source, parsed.payload)
    stfs.require(output == expected, "STFS output changed outside roster bytes and their hash chain")
    for key, value in expected_receipt.items():
        stfs.require(receipt.get(key) == value, f"STFS receipt {key} differs from reparse")
    reader, _ = _inventory(output)
    return {"verified": True, "metadata_hash_verified": True,
            "active_hash_tables_verified": len(reader._level_zero_tables),
            "data_blocks_verified": len(reader._verified_data_blocks),
            "signature_verified": False, "runtime_in_game_proved": False}


__all__ = ["SCHEMA", "XENIA_ONLY", "RUNTIME", "rehash_roster", "verify_rehash"]
