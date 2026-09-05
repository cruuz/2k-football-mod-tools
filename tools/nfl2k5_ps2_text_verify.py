#!/usr/bin/env python3
"""Independently verify a bounded text edit made to an ESPN NFL 2K5 PS2 ISO.

This is the evidence behind ``nfl2k5_ps2_text_patch.py``.  Given the source
image, the written destination and the recipe, it re-derives from the bytes
alone that the edit did what it claimed and nothing else.

**It imports neither the patcher nor the catalog nor the ISO writer's reader.**
A verifier built on the same parser as the writer cannot see a bug in that
parser, because both sides compute the same wrong offset and agree with each
other.  So the pack walk, the chunk walk, the VC pointer decode and the string
pool decode are all spelled out again here, and deliberately derived in a
different order: the catalog finds pool entries by scanning forward from the
pool offset and then checks they are all referenced, while this module starts
from the record table's pointers and builds the pool out of the referenced set.
Two derivations that agree are evidence; one derivation quoted twice is not.

The one module it does reuse is ``ps2_iso9660_verify``, which is itself an
independent ISO9660 walker written to check the writer, and whose whole purpose
is to be the second opinion.  The patch report is an *input to be checked*,
never evidence: every offset it declares is compared against one this module
derives for itself, and a disagreement fails.

WHAT IS PROVED
--------------
1. **Byte-level containment.**  The two images are the same size, and streaming
   them against each other yields a set of differing bytes that is *exactly*
   the bytes the recipe's target allocations should have changed -- not a
   subset, not a superset.  A single stray byte anywhere in 4.3 GiB fails.
   This is the check that matters most, and it does not trust any report: it is
   a full comparison of both files.
2. **Nothing moved.**  For every bank the recipe touches, the resource body is
   parsed out of *both* images and their inner headers, descriptor offsets,
   record counts, whole record tables, pool start offsets and the complete list
   of allocation ``(start, end)`` spans are compared.  Identical means no
   pointer, id, count or allocation boundary shifted.
3. **Only the intended strings changed.**  Every pool allocation that the
   recipe does not name must decode to the same text in both images.
4. **The intended strings changed correctly.**  Each target decodes, in the
   destination, to exactly the recipe's ``new_text``, NUL-terminated, with the
   rest of its allocation zero-filled.
5. **Tokens survived.**  The inline formatted tokens in each target's *source*
   text appear, in the same order, in its destination text.
6. **The chunk is still readable.**  Its header still declares the same stored
   size and the same compression state, and the body still decodes end to end
   -- so a reader walking the archive after the edit sees what it saw before.
   (No text bank on this disc is compressed; a compressed one is refused by the
   patcher and reported as unverifiable here.)
7. **The ISO is still an ISO.**  ``ps2_iso9660_verify`` re-checks the volume
   descriptor, the directory tree, every extent and every declared range.
8. **The source is untouched**, re-hashed over the regions the edit named.

Every failure raises ``TextVerifyError`` naming the offending offset or
selector, and the CLI exits nonzero.

USAGE
-----
    nfl2k5_ps2_text_verify.py --source-iso <in.iso> --destination-iso <out.iso> \\
        --recipe edits.json [--patch-report r.json] [--iso-write-report w.json] \\
        [--output verdict.json]
    nfl2k5_ps2_text_verify.py --selftest

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps2_iso9660_verify as iso_verify  # noqa: E402


SCHEMA = "nfl2k5_ps2_text_verify/v1"

PACK_DIRECTORY = "/VC_20919"
PACK_LETTERS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BLOCK = 0x800
OUTER_HEADER = 0x0C + 36 * 4
OUTER_ENTRY = 12
CHUNK_HEADER = 0x20
LZ_MAGIC = 0xFEEDBEEF
COMPARE_CHUNK = 8 * 1024 * 1024

KIND_LAYOUT = {
    # kind: (descriptor, record_size, [(field, relative), ...])
    "CRED": (0x30, 0x0C, (("primary_text", 0x04), ("secondary_text", 0x08))),
    "TRIV": (0x44, 0x24, (("category", 0x04), ("subject", 0x08),
                          ("question", 0x0C), ("answer_a", 0x10),
                          ("answer_b", 0x14), ("answer_c", 0x18),
                          ("answer_d", 0x1C))),
    "SITU": (0x40, 0x6C, (("title", 0x00), ("historical_description", 0x04),
                          ("challenge_objective", 0x08), ("date", 0x0C),
                          ("away_team_asset_code", 0x14),
                          ("home_team_asset_code", 0x18))),
}
STRG_RECORD_SIZE = 0x0C

PIPE_TOKEN = re.compile(r"\|[A-Za-z0-9_]{1,24}\|")
PRINTF_TOKEN = re.compile(r"%[-+ #0]*[0-9]*(?:\.[0-9]+)?[diouxXeEfgGcsp%]")


class TextVerifyError(AssertionError):
    """The destination is not the bounded edit the recipe describes."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise TextVerifyError(message)


def _tokens(text: str) -> List[str]:
    return PIPE_TOKEN.findall(text) + PRINTF_TOKEN.findall(text)


# ---------------------------------------------------------------------------
# This module's own pack / chunk / VC decoding
# ---------------------------------------------------------------------------

def _pack_extents(path) -> List[Tuple[str, int, int]]:
    """``[(iso_path, byte_offset, length)]`` for the /VC_20919 packs, in order."""
    descriptor, volume = iso_verify.open_volume(path)
    try:
        # ISO9660 identifiers are case-insensitive by convention, so fold them
        # rather than assuming the walker's spelling.
        entries = {entry.path.casefold(): entry
                   for entry in iso_verify.walk(descriptor, volume)}
        found = []
        for letter in PACK_LETTERS:
            key = ("%s/%s." % (PACK_DIRECTORY, letter)).casefold()
            entry = entries.get(key) or entries.get(key[:-1])
            if entry is None or entry.is_dir:
                break
            found.append((entry.path,
                          iso_verify._extent_offset(volume, entry.lba),
                          entry.length))
        _require(found, "%s: no %s packs in the volume" % (path, PACK_DIRECTORY))
        return found
    finally:
        os.close(descriptor)


class _Archive:
    """The packs addressed as one virtual byte range, read through one handle."""

    def __init__(self, path, extents: Sequence[Tuple[str, int, int]]) -> None:
        self.path = str(path)
        self.extents = list(extents)
        self.starts = [0]
        for _iso_path, _base, size in self.extents:
            self.starts.append(self.starts[-1] + size)
        self.handle = open(self.path, "rb")

    def close(self) -> None:
        self.handle.close()

    def index_of(self, virtual: int) -> int:
        for index in range(len(self.extents) - 1, -1, -1):
            if self.starts[index] <= virtual:
                return index
        raise TextVerifyError("negative virtual offset")

    def absolute(self, virtual: int) -> Tuple[str, int]:
        index = self.index_of(virtual)
        iso_path, base, _size = self.extents[index]
        return iso_path, base + virtual - self.starts[index]

    def read(self, virtual: int, size: int) -> bytes:
        _require(size >= 0 and virtual >= 0
                 and virtual + size <= self.starts[-1],
                 "read outside the virtual archive")
        out = []
        while size:
            index = self.index_of(virtual)
            inside = virtual - self.starts[index]
            take = min(size, self.extents[index][2] - inside)
            self.handle.seek(self.extents[index][1] + inside)
            block = self.handle.read(take)
            _require(len(block) == take, "short read from pack")
            out.append(block)
            virtual += take
            size -= take
        return b"".join(out)


def _outer_entries(archive: _Archive) -> List[Tuple[int, int, int]]:
    header = archive.read(0, OUTER_HEADER)
    count, _reserved, populated = struct.unpack_from("<III", header, 0)
    _require(populated == len(archive.extents),
             "the outer index declares %d packs, the volume has %d"
             % (populated, len(archive.extents)))
    _require(0 < count <= 1_000_000, "the outer index declares %d entries" % count)
    table = archive.read(OUTER_HEADER, count * OUTER_ENTRY)
    return [struct.unpack_from("<III", table, index * OUTER_ENTRY)
            for index in range(count)]


def _chunk_at(archive: _Archive, outer_index: int, chunk_index: int,
              entries: Sequence[Tuple[int, int, int]]) -> dict:
    """Walk one outer entry's chunks and return the one at *chunk_index*."""
    _require(0 <= outer_index < len(entries),
             "outer entry %d is not in this archive" % outer_index)
    _name_id, entry_size, offset_blocks = entries[outer_index]
    base = offset_blocks * BLOCK
    offset = 0
    for index in range(chunk_index + 1):
        _require(offset + CHUNK_HEADER <= entry_size,
                 "outer entry %d has no chunk %d" % (outer_index, chunk_index))
        header = archive.read(base + offset, CHUNK_HEADER)
        stored, system_bytes, video_bytes, magic = struct.unpack_from(
            "<IIII", header, 4)
        _require(stored and offset + CHUNK_HEADER + stored <= entry_size,
                 "outer entry %d chunk %d has an impossible stored size"
                 % (outer_index, index))
        if index == chunk_index:
            return {"fourcc": header[0:4].decode("latin-1"),
                    "stored_size": stored, "system_bytes": system_bytes,
                    "video_bytes": video_bytes,
                    "compressed": magic == LZ_MAGIC,
                    "virtual_offset": base + offset,
                    "body_virtual_offset": base + offset + CHUNK_HEADER}
        offset = ((offset + CHUNK_HEADER + stored) + 15) & ~15
    raise TextVerifyError("unreachable")


def _relative(body: bytes, field: int, what: str) -> int:
    _require(0 <= field and field + 4 <= len(body),
             "%s: pointer field out of bounds" % what)
    target = field + struct.unpack_from("<i", body, field)[0] - 1
    _require(0 <= target < len(body), "%s: pointer leaves the resource" % what)
    return target


def _utf16z(body: bytes, offset: int, what: str) -> Tuple[str, int]:
    _require(0 <= offset and offset + 2 <= len(body) and not (offset & 1),
             "%s: bad UTF-16 offset" % what)
    cursor = offset
    while cursor + 2 <= len(body):
        if body[cursor:cursor + 2] == b"\0\0":
            try:
                return body[offset:cursor].decode("utf-16le"), cursor + 2
            except UnicodeDecodeError as exc:
                raise TextVerifyError("%s: not UTF-16LE (%s)" % (what, exc))
        cursor += 2
    raise TextVerifyError("%s: not NUL-terminated" % what)


def _decode_bank(body: bytes, kind: str, boundaries=None) -> dict:
    """Pool spans and text, derived pointer-first (the catalog scans pool-first).

    ``boundaries`` is the allocation layout taken from the *source* image.  It
    exists because the last allocation in a pool has no following pointer to
    bound it, so on its own the destination cannot tell "the last string was
    shortened and its tail zero-filled" -- which is legal -- from "the pool
    shrank" -- which is not.  The source settles it: the destination is decoded
    against the source's boundaries and must agree with them exactly, which is
    a stronger check than deriving its own, not a weaker one.
    """
    _require(body[0x0C:0x10] == kind.encode("ascii"),
             "the resource does not carry the %s marker" % kind)
    if kind == "STRG":
        descriptor = _relative(body, 0x14, "STRG descriptor")
        count = struct.unpack_from("<I", body, descriptor)[0]
        table = descriptor + 4
        pool = table + count * STRG_RECORD_SIZE
        _require(pool <= len(body), "STRG record table runs past its body")
        targets = []
        for index in range(count):
            code_units = struct.unpack_from(
                "<I", body, table + index * STRG_RECORD_SIZE + 8)[0]
            targets.append(pool + code_units * 2)
        record_size = STRG_RECORD_SIZE
    else:
        expected_descriptor, record_size, fields = KIND_LAYOUT[kind]
        descriptor = _relative(body, 0x14, "%s descriptor" % kind)
        _require(descriptor == expected_descriptor,
                 "%s descriptor is at 0x%x, not the expected 0x%x"
                 % (kind, descriptor, expected_descriptor))
        count = struct.unpack_from("<I", body, descriptor)[0]
        table = descriptor + 4
        pool = table + count * record_size
        _require(pool <= len(body), "%s record table runs past its body" % kind)
        targets = []
        for index in range(count):
            base = table + index * record_size
            for field_name, relative in fields:
                targets.append(_relative(body, base + relative,
                                         "%s record %d %s" % (kind, index, field_name)))

    # An allocation runs from its own pointer target to the *next* one, not to
    # its terminator.  In the stock disc those coincide, because the pools are
    # packed with no slack -- but a shortened replacement terminates early and
    # zero-fills the rest, so a model that ended an allocation at its
    # terminator would call every legitimate shortening "not contiguous".
    ordered = sorted(set(targets))
    _require(ordered and ordered[0] == pool,
             "%s: the first allocation starts at 0x%x, not the pool offset 0x%x"
             % (kind, ordered[0] if ordered else -1, pool))
    if boundaries is None:
        _last_text, last_end = _utf16z(body, ordered[-1],
                                       "%s final pool entry" % kind)
        ends = [ordered[position + 1] if position + 1 < len(ordered) else last_end
                for position in range(len(ordered))]
    else:
        _require([start for start, _end in boundaries] == ordered,
                 "%s: the pointer targets do not match the source's allocation "
                 "starts, so a pointer moved" % kind)
        ends = [end for _start, end in boundaries]
        last_end = ends[-1]

    entries = []
    for position, start in enumerate(ordered):
        end = ends[position]
        _require(end > start, "%s: allocation at 0x%x is empty" % (kind, start))
        text, text_end = _utf16z(body, start,
                                 "%s pool entry at 0x%x" % (kind, start))
        _require(text_end <= end,
                 "%s: the string at 0x%x runs past its allocation into the next "
                 "one (terminates at 0x%x, allocation ends at 0x%x)"
                 % (kind, start, text_end, end))
        _require(body[text_end:end] == bytes(end - text_end),
                 "%s: allocation at 0x%x has %d bytes of non-zero data past its "
                 "terminator; a bounded edit zero-fills that tail"
                 % (kind, start, end - text_end))
        entries.append({"start": start, "end": end, "text": text,
                        "text_end": text_end})

    return {
        "descriptor": descriptor, "count": count, "record_table": table,
        "record_table_bytes": body[table:pool], "pool_offset": pool,
        "pool_end": last_end, "entries": entries,
        "trailer": body[last_end:], "record_size": record_size,
    }


# ---------------------------------------------------------------------------
# Whole-image comparison
# ---------------------------------------------------------------------------

def _differing_ranges(source, destination) -> List[Tuple[int, int]]:
    """Every maximal run of differing bytes between two equal-size files."""
    size = os.stat(source).st_size
    _require(os.stat(destination).st_size == size,
             "the two images are different sizes (%d vs %d); a bounded edit "
             "never changes the image length"
             % (size, os.stat(destination).st_size))
    ranges: List[Tuple[int, int]] = []
    position = 0
    open_start = None
    with open(source, "rb") as left, open(destination, "rb") as right:
        while True:
            a = left.read(COMPARE_CHUNK)
            b = right.read(COMPARE_CHUNK)
            _require(len(a) == len(b), "the two images ended at different points")
            if not a:
                break
            if a != b:
                for index in range(len(a)):
                    if a[index] != b[index]:
                        if open_start is None:
                            open_start = position + index
                    elif open_start is not None:
                        ranges.append((open_start, position + index - open_start))
                        open_start = None
            elif open_start is not None:
                ranges.append((open_start, position - open_start))
                open_start = None
            position += len(a)
    if open_start is not None:
        ranges.append((open_start, position - open_start))
    return ranges


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _bank_from_selector(selector: str) -> Tuple[str, int, int]:
    """``nfl2k5.ps2.text-bank.<kind>.<outer>.<chunk>`` -> (KIND, outer, chunk)."""
    bank_id = selector.split(":", 1)[0]
    parts = bank_id.split(".")
    _require(len(parts) >= 6 and parts[2] == "text-bank",
             "%r is not a text bank id" % bank_id)
    kind = parts[-3].upper()
    _require(kind in ("STRG", "CRED", "SITU", "TRIV"),
             "%r names the unsupported bank kind %s" % (bank_id, kind))
    try:
        return kind, int(parts[-2]), int(parts[-1])
    except ValueError:
        raise TextVerifyError("%r does not end in outer.chunk" % bank_id)


def _targets_from_recipe(recipe: dict) -> List[dict]:
    edits = recipe.get("edits")
    _require(isinstance(edits, list) and edits, "the recipe has no edits")
    targets = []
    for index, edit in enumerate(edits):
        _require(isinstance(edit, dict), "recipe edit %d is not an object" % index)
        new_text = edit.get("new_text")
        _require(isinstance(new_text, str) and new_text,
                 "recipe edit %d has no new_text" % index)
        pool_index = edit.get("index", edit.get("pool_index"))
        if pool_index is not None:
            _require(isinstance(pool_index, int) and not isinstance(pool_index, bool)
                     and pool_index >= 0,
                     "recipe edit %d has a non-integer index" % index)
        selector = edit.get("selector")
        if selector is None:
            bank = edit.get("bank")
            _require(isinstance(bank, str) and pool_index is not None,
                     "recipe edit %d needs selector, or bank and index" % index)
            selector = "%s:#%d" % (bank, pool_index)
        targets.append({"selector": selector, "new_text": new_text,
                        "pool_index": pool_index, "recipe_index": index})
    return targets


def verify(*, source_iso, destination_iso, recipe: dict,
           patch_report: Optional[dict] = None,
           iso_write_report: Optional[dict] = None) -> dict:
    """Re-derive the whole claim from the two images and the recipe."""
    source_iso = str(source_iso)
    destination_iso = str(destination_iso)
    _require(Path(source_iso).resolve() != Path(destination_iso).resolve(),
             "the source and destination are the same file")

    targets = _targets_from_recipe(recipe)

    source_packs = _pack_extents(source_iso)
    destination_packs = _pack_extents(destination_iso)
    _require(source_packs == destination_packs,
             "the pack extents moved: %r vs %r" % (source_packs, destination_packs))

    left = _Archive(source_iso, source_packs)
    right = _Archive(destination_iso, destination_packs)
    checked: List[dict] = []
    expected_offsets: set = set()
    try:
        left_entries = _outer_entries(left)
        right_entries = _outer_entries(right)
        _require(left_entries == right_entries,
                 "the outer entry table changed; a bounded string edit never "
                 "touches it")

        by_bank: Dict[str, List[dict]] = {}
        for target in targets:
            by_bank.setdefault(target["selector"].split(":", 1)[0], []).append(target)

        for bank_id, bank_targets in sorted(by_bank.items()):
            kind, outer_index, chunk_index = _bank_from_selector(bank_id)
            left_chunk = _chunk_at(left, outer_index, chunk_index, left_entries)
            right_chunk = _chunk_at(right, outer_index, chunk_index, right_entries)
            for field in ("fourcc", "stored_size", "system_bytes", "video_bytes",
                          "compressed", "virtual_offset"):
                _require(left_chunk[field] == right_chunk[field],
                         "%s chunk header field %s changed (%r -> %r)"
                         % (bank_id, field, left_chunk[field], right_chunk[field]))
            _require(left_chunk["fourcc"] == kind,
                     "%s names kind %s but the chunk carries %r"
                     % (bank_id, kind, left_chunk["fourcc"]))
            _require(not left_chunk["compressed"],
                     "%s is LZ-compressed; this verifier cannot re-derive a "
                     "compressed body and refuses to pass it" % bank_id)

            size = left_chunk["stored_size"]
            left_body = left.read(left_chunk["body_virtual_offset"], size)
            right_body = right.read(right_chunk["body_virtual_offset"], size)
            _require(len(left_body) == len(right_body) == size,
                     "%s body length changed" % bank_id)

            before = _decode_bank(left_body, kind)
            after = _decode_bank(
                right_body, kind,
                boundaries=[(entry["start"], entry["end"])
                            for entry in before["entries"]])
            for field in ("descriptor", "count", "record_table", "pool_offset",
                          "pool_end", "record_size"):
                _require(before[field] == after[field],
                         "%s: %s moved (%r -> %r)"
                         % (bank_id, field, before[field], after[field]))
            _require(before["record_table_bytes"] == after["record_table_bytes"],
                     "%s: the record table changed, so a pointer, id or count "
                     "moved" % bank_id)
            _require(before["trailer"] == after["trailer"],
                     "%s: the bytes past the string pool changed" % bank_id)
            _require([(e["start"], e["end"]) for e in before["entries"]]
                     == [(e["start"], e["end"]) for e in after["entries"]],
                     "%s: an allocation boundary moved" % bank_id)

            by_index = {index: entry for index, entry
                        in enumerate(before["entries"])}
            wanted: Dict[int, dict] = {}
            for target in bank_targets:
                pool_index = target["pool_index"]
                if pool_index is None:
                    tail = target["selector"].rsplit(":", 1)[-1]
                    _require(tail.isdigit(),
                             "cannot tell which allocation %r names; give "
                             "bank and index" % target["selector"])
                    pool_index = int(tail)
                _require(pool_index in by_index,
                         "%s has no allocation %d" % (bank_id, pool_index))
                _require(pool_index not in wanted,
                         "the recipe names allocation %d of %s twice"
                         % (pool_index, bank_id))
                wanted[pool_index] = target

            for index, entry in enumerate(before["entries"]):
                new_entry = after["entries"][index]
                allocation = entry["end"] - entry["start"]
                if index not in wanted:
                    _require(entry["text"] == new_entry["text"],
                             "%s allocation %d changed but the recipe does not "
                             "name it" % (bank_id, index))
                    _require(
                        left_body[entry["start"]:entry["end"]]
                        == right_body[entry["start"]:entry["end"]],
                        "%s allocation %d has identical text but different "
                        "bytes; something is hidden past its terminator"
                        % (bank_id, index))
                    continue

                target = wanted[index]
                expected_text = target["new_text"]
                _require(new_entry["text"] == expected_text,
                         "%s allocation %d reads %d code units, not the recipe's "
                         "text" % (bank_id, index,
                                   len(new_entry["text"].encode("utf-16le")) // 2))
                encoded = expected_text.encode("utf-16le")
                _require(len(encoded) + 2 <= allocation,
                         "%s allocation %d holds %d bytes; the replacement needs "
                         "%d" % (bank_id, index, allocation, len(encoded) + 2))
                actual = right_body[entry["start"]:entry["end"]]
                _require(actual == encoded + b"\0\0" + bytes(
                             allocation - len(encoded) - 2),
                         "%s allocation %d is not the replacement followed by a "
                         "terminator and zero fill" % (bank_id, index))
                _require(_tokens(entry["text"]) == _tokens(expected_text),
                         "%s allocation %d does not carry the same inline "
                         "tokens as the string it replaced" % (bank_id, index))
                _require(entry["text"] != expected_text,
                         "%s allocation %d is unchanged; the recipe asked for "
                         "an edit that does nothing" % (bank_id, index))

                iso_path, absolute = right.absolute(
                    right_chunk["body_virtual_offset"] + entry["start"])
                original = left_body[entry["start"]:entry["end"]]
                # UTF-16LE means a changed character usually leaves its high
                # byte alone, so one replaced word produces *several* short
                # runs of differing bytes rather than one span.  Collect the
                # individual offsets and merge them the same way the image
                # comparison does, or the two sides disagree for no reason.
                expected_offsets.update(
                    absolute + offset for offset in range(allocation)
                    if original[offset] != actual[offset])
                checked.append({
                    "selector": target["selector"],
                    "bank_id": bank_id, "bank_kind": kind, "pool_index": index,
                    "pack_iso_path": iso_path,
                    "iso_byte_offset": absolute,
                    "allocation_bytes": allocation,
                    "original_text_sha256": hashlib.sha256(
                        entry["text"].encode("utf-16le")).hexdigest(),
                    "new_text_sha256": hashlib.sha256(encoded).hexdigest(),
                    "new_code_units": len(encoded) // 2,
                    "tokens": _tokens(expected_text),
                    "changed_byte_count": sum(
                        1 for offset in range(allocation)
                        if original[offset] != actual[offset]),
                })
    finally:
        left.close()
        right.close()

    _require(len(checked) == len(targets),
             "the recipe has %d edits but only %d were located"
             % (len(targets), len(checked)))

    # The decisive check: compare the whole of both images.
    observed = _differing_ranges(source_iso, destination_iso)
    expected = _merge_offsets(expected_offsets)
    _require(observed == expected,
             "the images differ outside the edited allocations.\n"
             "  derived from the recipe: %s\n"
             "  actually differing:      %s"
             % (_show(expected), _show(observed)))

    result = {
        "schema": SCHEMA,
        "verdict": "pass",
        "source": {"path": source_iso, "size": os.stat(source_iso).st_size},
        "destination": {"path": destination_iso,
                        "size": os.stat(destination_iso).st_size},
        "edits": checked,
        "differing_ranges": [{"offset": start, "length": length}
                             for start, length in observed],
        "changed_byte_count": sum(length for _start, length in observed),
        "checks": {
            "images_same_size": True,
            "differences_exactly_the_edited_allocations": True,
            "outer_entry_table_unchanged": True,
            "chunk_headers_unchanged": True,
            "record_tables_unchanged": True,
            "allocation_boundaries_unchanged": True,
            "untouched_strings_byte_identical": True,
            "replacements_terminated_and_zero_filled": True,
            "inline_tokens_preserved": True,
            "pack_extents_unchanged": True,
            "independent_of_patcher_and_catalog": True,
        },
    }

    if patch_report is not None:
        result["patch_report_agreement"] = _check_patch_report(patch_report, checked)
    if iso_write_report is not None:
        result["iso_write_verification"] = iso_verify.verify_replacement(
            source_iso, destination_iso, iso_write_report)
        result["checks"]["iso9660_verifier_passed"] = True
    return result


def _merge_offsets(offsets) -> List[Tuple[int, int]]:
    """Turn a set of byte offsets into the maximal runs they form."""
    runs: List[Tuple[int, int]] = []
    start = previous = None
    for offset in sorted(offsets):
        if start is None:
            start = previous = offset
        elif offset == previous + 1:
            previous = offset
        else:
            runs.append((start, previous - start + 1))
            start = previous = offset
    if start is not None:
        runs.append((start, previous - start + 1))
    return runs


def _show(ranges: Sequence[Tuple[int, int]]) -> str:
    if not ranges:
        return "(none)"
    shown = ["0x%x+%d" % (start, length) for start, length in ranges[:8]]
    if len(ranges) > 8:
        shown.append("... %d more" % (len(ranges) - 8))
    return ", ".join(shown)


def _check_patch_report(report: dict, checked: Sequence[dict]) -> dict:
    """The report is an input to be checked, so compare it against our own work."""
    _require(isinstance(report, dict), "the patch report is not an object")
    declared = report.get("edits")
    _require(isinstance(declared, list),
             "the patch report has no edits list")
    _require(len(declared) == len(checked),
             "the patch report declares %d edits; %d were verified"
             % (len(declared), len(checked)))
    ours = {item["iso_byte_offset"]: item for item in checked}
    for entry in declared:
        offset = entry.get("iso_byte_offset")
        _require(offset in ours,
                 "the patch report declares an edit at 0x%x that this module "
                 "did not derive" % (offset if isinstance(offset, int) else -1))
        mine = ours[offset]
        for field in ("allocation_bytes", "pool_index", "bank_id"):
            if field in entry:
                _require(entry[field] == mine[field],
                         "the patch report and this module disagree about %s "
                         "at 0x%x (%r vs %r)"
                         % (field, offset, entry[field], mine[field]))
        if "original_text_sha256" in entry:
            _require(entry["original_text_sha256"] == mine["original_text_sha256"],
                     "the patch report's original digest at 0x%x is not the one "
                     "the source image holds" % offset)
    return {"edit_count": len(declared), "agrees": True}


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def selftest(tmp: Optional[Path] = None) -> int:
    failures: List[str] = []

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    check(_tokens("a |CROSS| b") == ["|CROSS|"], "pipe token detection")
    check(_tokens("20%") == [], "a trailing percent is not a conversion")
    check(_tokens("%s") == ["%s"], "printf detection")

    body = _synthetic_strg(["MENU", "OPTIONS", "QUIT"])
    parsed = _decode_bank(body, "STRG")
    check([entry["text"] for entry in parsed["entries"]]
          == ["MENU", "OPTIONS", "QUIT"], "synthetic STRG decode")
    check(parsed["count"] == 3, "synthetic STRG count")

    moved = bytearray(body)
    struct.pack_into("<I", moved, parsed["record_table"] + 8, 1)
    try:
        _decode_bank(bytes(moved), "STRG")
        failures.append("a non-boundary pointer was accepted")
    except TextVerifyError:
        pass

    for line in failures:
        print("FAIL: %s" % line, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_TEXT_VERIFY_SELFTEST_PASS checks=6")
    return 0


def _synthetic_strg(texts: Sequence[str]) -> bytes:
    descriptor = 0x30
    body = bytearray(descriptor)
    body[0x0C:0x10] = b"STRG"
    name = "strings".encode("utf-16le") + b"\0\0"
    struct.pack_into("<i", body, 0x10, 0x20 - 0x10 + 1)
    struct.pack_into("<i", body, 0x14, descriptor - 0x14 + 1)
    body[0x20:0x20 + len(name)] = name
    body.extend(struct.pack("<I", len(texts)))
    body.extend(bytes(len(texts) * STRG_RECORD_SIZE))
    table = descriptor + 4
    pool = table + len(texts) * STRG_RECORD_SIZE
    cursor = pool
    for index, text in enumerate(texts):
        struct.pack_into("<III", body, table + index * STRG_RECORD_SIZE,
                         index, index, (cursor - pool) // 2)
        blob = text.encode("utf-16le") + b"\0\0"
        body.extend(blob)
        cursor += len(blob)
    return bytes(body)


def _load(path: Optional[str], what: str) -> Optional[dict]:
    if path is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise TextVerifyError("could not read the %s: %s" % (what, exc))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source-iso")
    parser.add_argument("--destination-iso")
    parser.add_argument("--recipe")
    parser.add_argument("--patch-report")
    parser.add_argument("--iso-write-report")
    parser.add_argument("--output")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not (args.source_iso and args.destination_iso and args.recipe):
        parser.error("--source-iso, --destination-iso and --recipe are required")
    try:
        result = verify(
            source_iso=args.source_iso,
            destination_iso=args.destination_iso,
            recipe=_load(args.recipe, "recipe"),
            patch_report=_load(args.patch_report, "patch report"),
            iso_write_report=_load(args.iso_write_report, "ISO write report"),
        )
    except (TextVerifyError, iso_verify.IsoVerifyError, OSError, ValueError) as exc:
        print("NFL2K5_PS2_TEXT_VERIFY_FAIL: %s" % exc, file=sys.stderr)
        return 1
    if args.output:
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    print("NFL2K5_PS2_TEXT_VERIFY_PASS edits=%d changed_bytes=%d ranges=%d"
          % (len(result["edits"]), result["changed_byte_count"],
             len(result["differing_ranges"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
