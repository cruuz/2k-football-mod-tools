#!/usr/bin/env python3
"""Independently verify a PS2 NFL 2K5 disc-roster write.

This is the evidence behind ``nfl2k5_ps2_disc_roster_patch.py``.  Given the
stock image, the written image and the writer's receipt, it re-derives from the
bytes alone that

  1. the bounded ISO9660 replacement holds (delegated to ``ps2_iso9660_verify``,
     itself an independent decoder);
  2. **across the replaced pack extent the two images differ only inside the
     declared ranges** -- compared against the *source*, not against the
     writer's own staged content;
  3. every declared range holds exactly what the receipt claims it holds, and
     held exactly what the receipt claims it held;
  4. a packed edit moved no bit outside the masks it claimed, and a name edit
     left a NUL-terminated UTF-16LE string inside its original allocation;
  5. **the arena did not move**: the written ``ROST`` object still decodes at
     the same version and root, and every one of its ten tables keeps the same
     record count *and* the same byte offset as the stock image's;
  6. the image still carries the same set of ``ROST`` resources.

**It imports neither the patcher nor the ISO writer's parser, nor the shared
``nfl_roster`` parser the writer uses.**  A verifier that reuses the writer's
decoder cannot see a bug in that decoder: both sides would read the same wrong
offset and agree with each other.  The archive layout, the resource wrapper,
the pointer rule and the ten root tables are therefore restated below, and the
receipt is an input to be checked, never evidence.

The self-test uses the patcher only to *manufacture* a fixture -- the shipped
discipline of ``ps2_iso9660_verify`` and ``nfl2k5_ps2_save_verify`` -- while
every assertion still runs through this module's own decode.

Usage::

    nfl2k5_ps2_disc_roster_verify.py --source <stock.iso> --destination <new.iso> \\
        --receipt <receipt.json> [--report <verdict.json>]
    nfl2k5_ps2_disc_roster_verify.py --selftest

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import ps2_iso9660_verify as iso_verify  # noqa: E402  (independent ISO decoder)


SCHEMA = "nfl2k5_ps2_disc_roster_verify/v1"
WRITE_SCHEMA = "nfl2k5_ps2_disc_roster_write/v1"
SERIAL = "SLUS-20919"

# Container and arena constants, restated rather than imported.
_PACK_DIRECTORY = "/VC_20919"
_PACK_NAMES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ALIGNMENT = 0x800
_PACK_SLOTS = 36
_OUTER_HEADER = 0x0C + _PACK_SLOTS * 4
_OUTER_ENTRY = 12
_CHUNK_HEADER = 0x20
_LZ_SENTINEL = 0xFEEDBEEF
_ROST = b"ROST"
_MAGIC_AT = 0x0C
_VERSION_AT = 0x10
_ROOT_PTR_AT = 0x14
_LABEL_AT = 0x20
_ROOT_SIZE = 0x70
_MAX_ENTRIES = 1 << 20
_COMPARE_CHUNK = 8 * 1024 * 1024

#: ``(name, count_offset, pointer_offset, stride)`` for the ten root tables.
_TABLES = (
    ("primary_players", 0x00, 0x04, 0x54),
    ("secondary_players", 0x08, 0x0C, 0x54),
    ("stadiums", 0x10, 0x14, 0x80),
    ("teams", 0x18, 0x1C, 0x1F4),
    ("colleges", 0x20, 0x24, 0x08),
    ("coaches", 0x30, 0x34, 0xA8),
    ("player_pointer_vector", 0x38, 0x3C, 0x04),
    ("team_labels", 0x48, 0x4C, 0x08),
    ("generated_names", 0x50, 0x54, 0x08),
    ("historic_descriptors", 0x58, 0x5C, 0x10),
)

_JERSEY_MASK = 0x3F8
_JERSEY_SHIFT = 3
_FACE_SHIELD_MASK = 0x18000
_FACE_SHIELD_SHIFT = 15
_FIELD_MASKS = {"jersey_number": _JERSEY_MASK, "face_shield": _FACE_SHIELD_MASK}


class RosterVerifyError(AssertionError):
    """A written image did not hold what the receipt claimed about it."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise RosterVerifyError(message)


def _read(handle, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    _require(len(data) == size, "short read of %d bytes at %d" % (size, offset))
    return data


def _pointer(data: bytes, field: int) -> Optional[int]:
    value = struct.unpack_from("<i", data, field)[0]
    return None if value == 0 else field + value - 1


# --------------------------------------------------------------------------
# Independent decode
# --------------------------------------------------------------------------

def _pack_ordinal(iso_path: str) -> Optional[int]:
    """The archive ordinal of ``/VC_20919/<letter>[.]``, or None if not a pack.

    ``/VC_20919`` also holds a ``DATA/`` subtree of IOP modules and network
    assets; only the single-character resource packs make up the virtual
    archive, and their order is the order of ``_PACK_NAMES``, not disc order.
    """
    upper = iso_path.upper()
    if not upper.startswith(_PACK_DIRECTORY + "/"):
        return None
    leaf = upper[len(_PACK_DIRECTORY) + 1:]
    if leaf.endswith("."):
        leaf = leaf[:-1]
    if len(leaf) != 1 or leaf not in _PACK_NAMES:
        return None
    return _PACK_NAMES.index(leaf)


def pack_extents(path: Path) -> List[Tuple[str, int, int]]:
    """``[(iso_path, byte_offset, length)]`` for the resource packs, in order."""
    descriptor, volume = iso_verify.open_volume(path)
    try:
        entries = iso_verify.walk(descriptor, volume)
    finally:
        os.close(descriptor)
    found = []
    for entry in entries:
        if entry.is_dir:
            continue
        normalized = iso_verify.normalize_path(entry.path)
        ordinal = _pack_ordinal(normalized)
        if ordinal is None:
            continue
        found.append((ordinal, normalized,
                      entry.lba * volume.sector_size + volume.data_offset,
                      entry.length))
    _require(found, "%s carries no %s resource packs" % (path, _PACK_DIRECTORY))
    found.sort()
    _require([row[0] for row in found] == list(range(len(found))),
             "the %s resource packs are not a contiguous run from 0"
             % _PACK_DIRECTORY)
    return [(name, base, length) for _ordinal, name, base, length in found]


def rost_resources(path: Path) -> List[Dict[str, Any]]:
    """Every ``ROST`` resource in an image, decoded by this module's own walk."""
    packs = pack_extents(path)
    starts = [0]
    for _name, _base, length in packs:
        starts.append(starts[-1] + length)

    def virtual_to_iso(offset: int, size: int) -> Optional[int]:
        for ordinal, (_name, base, length) in enumerate(packs):
            inside = offset - starts[ordinal]
            if 0 <= inside and inside + size <= length:
                return base + inside
        return None

    def read_virtual(handle, offset: int, size: int) -> bytes:
        parts = []
        while size:
            index = max(i for i in range(len(packs)) if starts[i] <= offset)
            inside = offset - starts[index]
            take = min(size, packs[index][2] - inside)
            _require(take > 0, "virtual read fell off the archive at %d" % offset)
            parts.append(_read(handle, packs[index][1] + inside, take))
            offset += take
            size -= take
        return b"".join(parts)

    found = []  # type: List[Dict[str, Any]]
    with open(str(path), "rb") as handle:
        header = read_virtual(handle, 0, _OUTER_HEADER)
        entry_count, _reserved, populated = struct.unpack_from("<III", header, 0)
        _require(populated == len(packs),
                 "the outer index declares %d packs, the image has %d"
                 % (populated, len(packs)))
        _require(0 < entry_count <= _MAX_ENTRIES,
                 "the outer index declares %d entries" % entry_count)
        table = read_virtual(handle, _OUTER_HEADER, entry_count * _OUTER_ENTRY)
        for index in range(entry_count):
            name_id, size, blocks = struct.unpack_from(
                "<III", table, index * _OUTER_ENTRY)
            if size < _CHUNK_HEADER:
                continue
            virtual = blocks * _ALIGNMENT
            if virtual + _CHUNK_HEADER > starts[-1]:
                continue
            head = read_virtual(handle, virtual, _CHUNK_HEADER)
            if head[:4] != _ROST:
                continue
            stored, _system, _video, sentinel = struct.unpack_from("<4I", head, 4)
            row = {
                "outer_index": index,
                "outer_name_id": "0x%08x" % name_id,
                "stored_size": stored,
                "compressed": sentinel == _LZ_SENTINEL,
                "body_offset_in_iso": virtual_to_iso(virtual + _CHUNK_HEADER, stored),
            }
            if row["compressed"] or not stored or _CHUNK_HEADER + stored > size:
                row["decoded"] = False
                found.append(row)
                continue
            body = read_virtual(handle, virtual + _CHUNK_HEADER, stored)
            _require(body[_MAGIC_AT:_MAGIC_AT + 4] == _ROST,
                     "outer %d: the ROST object tag is gone" % index)
            root = _pointer(body, _ROOT_PTR_AT)
            _require(root is not None and 0 <= root
                     and root + _ROOT_SIZE <= len(body),
                     "outer %d: the ROST root pointer does not land in the arena"
                     % index)
            end = _LABEL_AT
            while end + 2 <= len(body) and body[end:end + 2] != b"\x00\x00":
                end += 2
            row["decoded"] = True
            row["version"] = struct.unpack_from("<I", body, _VERSION_AT)[0]
            row["root"] = root
            row["label"] = body[_LABEL_AT:end].decode("utf-16le", "replace")
            tables = {}
            for name, count_at, pointer_at, stride in _TABLES:
                count = struct.unpack_from("<I", body, root + count_at)[0]
                where = _pointer(body, root + pointer_at)
                _require(where is not None or count == 0,
                         "outer %d: %s has count %d and a null pointer"
                         % (index, name, count))
                if where is None:
                    where = root + _ROOT_SIZE
                _require(0 <= where and where + count * stride <= len(body),
                         "outer %d: %s runs past the arena" % (index, name))
                tables[name] = {"count": count, "offset": where, "stride": stride}
            row["tables"] = tables
            row["body_sha256"] = hashlib.sha256(body).hexdigest()
            found.append(row)
    found.sort(key=lambda row: row["outer_index"])
    return found


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

def _compare_extent(source, destination, base: int, length: int,
                    allowed: Sequence[Tuple[int, int]]) -> int:
    cuts = [0]
    for start, size in allowed:
        cuts.append(start - base)
        cuts.append(start - base + size)
    cuts.append(length)
    compared = 0
    for index in range(0, len(cuts) - 1, 2):
        begin, end = cuts[index], cuts[index + 1]
        _require(0 <= begin <= end <= length,
                 "a declared range is not inside the extent it claims")
        position = begin
        while position < end:
            take = min(_COMPARE_CHUNK, end - position)
            left = _read(source, base + position, take)
            right = _read(destination, base + position, take)
            if left != right:
                bad = next(i for i, pair in enumerate(zip(left, right))
                           if pair[0] != pair[1])
                raise RosterVerifyError(
                    "byte 0x%x changed outside every declared range; the write "
                    "did not stay in its lane" % (base + position + bad))
            compared += take
            position += take
    return compared


def verify(source, destination, receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Check one written image against its receipt.  Raises on any violation."""
    source = Path(source)
    destination = Path(destination)
    _require(receipt.get("schema") == WRITE_SCHEMA,
             "receipt schema is %r, expected %r"
             % (receipt.get("schema"), WRITE_SCHEMA))
    edits = receipt.get("edits") or []
    _require(edits, "the receipt declares no edits")
    claimed = receipt.get("roster") or {}
    _require("outer_index" in claimed,
             "the receipt does not say which ROST resource it wrote")

    iso_report = receipt.get("iso_write_report")
    _require(isinstance(iso_report, dict),
             "the receipt carries no ISO write report to check")

    packs = pack_extents(destination)
    _require(packs == pack_extents(source),
             "the pack extents moved between the two images")
    replaced = {item.upper() for item in (receipt.get("files_replaced") or [])}
    _require(replaced, "the receipt names no replaced file")

    grouped = {}  # type: Dict[str, List[Tuple[int, int]]]
    for row in receipt.get("declared_ranges", []):
        start, length = int(row["start"]), int(row["length"])
        _require(length > 0, "a declared range is empty")
        owner = None
        for name, base, extent in packs:
            if base <= start and start + length <= base + extent:
                owner = name
                break
        _require(owner is not None,
                 "the declared range at %d lies outside every %s pack"
                 % (start, _PACK_DIRECTORY))
        _require(owner.upper() in replaced,
                 "%s carries declared ranges but is not a replaced file" % owner)
        grouped.setdefault(owner, []).append((start, length))
    for ranges in grouped.values():
        ranges.sort()
        for left, right in zip(ranges, ranges[1:]):
            _require(left[0] + left[1] <= right[0],
                     "two declared ranges overlap at %d" % right[0])

    declared_by_offset = {(int(row["start"]), int(row["length"]))
                          for row in receipt.get("declared_ranges", [])}
    for edit in edits:
        _require((int(edit["offset_in_iso"]), int(edit["span_size"]))
                 in declared_by_offset,
                 "the edit at %s is not among the declared ranges"
                 % edit.get("offset_in_iso"))

    compared = 0
    names_checked = 0
    packed_checked = 0
    with open(str(source), "rb") as left, open(str(destination), "rb") as right:
        for name, base, length in packs:
            if name.upper() not in replaced:
                continue
            compared += _compare_extent(left, right, base, length,
                                        grouped.get(name, []))
        for edit in edits:
            offset = int(edit["offset_in_iso"])
            size = int(edit["span_size"])
            before = _read(left, offset, size)
            after = _read(right, offset, size)
            _require(hashlib.sha256(before).hexdigest() == edit["before_sha256"],
                     "the stock image does not hold the bytes the receipt "
                     "recorded at %d" % offset)
            _require(hashlib.sha256(after).hexdigest() == edit["after_sha256"],
                     "the written image does not hold the bytes the receipt "
                     "recorded at %d" % offset)
            _require(before != after,
                     "the declared range at %d did not change" % offset)
            if edit.get("kind") == "packed":
                _require(size == 4, "a packed edit must be four bytes, not %d" % size)
                old = struct.unpack("<I", before)[0]
                new = struct.unpack("<I", after)[0]
                authored = 0
                for field in edit.get("fields") or []:
                    _require(field in _FIELD_MASKS,
                             "the receipt claims an unknown packed field %r" % field)
                    authored |= _FIELD_MASKS[field]
                _require((old & ~authored) == (new & ~authored),
                         "the packed edit at %d moved a bit outside %s"
                         % (offset, edit.get("fields")))
                if "jersey_number" in (edit.get("fields") or []):
                    _require(0 <= ((new >> _JERSEY_SHIFT) & 0x7F) <= 99,
                             "the written jersey number is outside 0..99")
                if "face_shield" in (edit.get("fields") or []):
                    _require(((new >> _FACE_SHIELD_SHIFT) & 0x3) in (0, 1, 2),
                             "the written face shield uses the reserved value 3")
                packed_checked += 1
            elif edit.get("kind") == "name":
                _require(size % 2 == 0,
                         "a name allocation must be an even number of bytes")
                # The terminator must be found on a code-unit boundary: a naive
                # byte search finds the NUL pair straddling the last character's
                # high byte and the terminator's low byte.
                terminator = -1
                for position in range(0, size, 2):
                    if after[position:position + 2] == b"\x00\x00":
                        terminator = position
                        break
                _require(terminator >= 0,
                         "the written name at %d has no aligned terminator inside "
                         "its allocation" % offset)
                _require(after[terminator:] == b"\x00" * (size - terminator),
                         "the tail of the name allocation at %d is not zero filled"
                         % offset)
                after[:terminator].decode("utf-16le")
                names_checked += 1
            else:
                raise RosterVerifyError(
                    "the receipt declares an unknown edit kind %r" % edit.get("kind"))

    written = rost_resources(destination)
    stock = rost_resources(source)
    _require(len(written) == len(stock),
             "the written image carries %d ROST resources, the stock image %d"
             % (len(written), len(stock)))
    stock_by_index = {row["outer_index"]: row for row in stock}
    target = None
    for row in written:
        original = stock_by_index.get(row["outer_index"])
        _require(original is not None,
                 "outer %d appeared in the written image" % row["outer_index"])
        _require(row["decoded"] == original["decoded"]
                 and row["compressed"] == original["compressed"]
                 and row["stored_size"] == original["stored_size"],
                 "outer %d changed shape" % row["outer_index"])
        if not row["decoded"]:
            continue
        _require(row["version"] == original["version"]
                 and row["root"] == original["root"]
                 and row["label"] == original["label"],
                 "outer %d: the ROST preamble changed" % row["outer_index"])
        _require(row["tables"] == original["tables"],
                 "outer %d: a table count or offset moved; the edit did not stay "
                 "inside its fixed allocation" % row["outer_index"])
        if row["outer_index"] == int(claimed["outer_index"]):
            target = row
    _require(target is not None,
             "the receipt's target roster (outer %s) is not in the written image"
             % claimed.get("outer_index"))
    _require(target["label"] == claimed.get("label"),
             "outer %s is labelled %r, the receipt claims %r"
             % (claimed.get("outer_index"), target["label"], claimed.get("label")))
    _require(target["body_offset_in_iso"] == int(claimed["body_offset_in_iso"]),
             "the target arena is at %s, the receipt claims %s"
             % (target["body_offset_in_iso"], claimed.get("body_offset_in_iso")))
    for edit in edits:
        offset = int(edit["offset_in_iso"])
        _require(target["body_offset_in_iso"] <= offset
                 and offset + int(edit["span_size"])
                 <= target["body_offset_in_iso"] + target["stored_size"],
                 "the declared range at %d is not inside the target arena" % offset)

    # The bounded-replacement check runs last so that this module's own,
    # narrower findings name the offending byte first; its failures are
    # re-raised in this module's type so a caller has one surface to catch.
    try:
        iso_result = iso_verify.verify_replacement(source, destination, iso_report)
    except iso_verify.IsoVerifyError as exc:
        raise RosterVerifyError("the bounded ISO replacement did not verify: %s"
                                % exc)
    _require(iso_result.get("result") == "PASS",
             "the bounded ISO replacement did not verify: %r" % (iso_result,))

    return {
        "schema": SCHEMA,
        "result": "PASS",
        "serial": SERIAL,
        "source": str(source),
        "destination": str(destination),
        "edits_checked": len(edits),
        "name_edits_checked": names_checked,
        "packed_edits_checked": packed_checked,
        "rost_resources_decoded": sum(1 for row in written if row["decoded"]),
        "target_outer_index": target["outer_index"],
        "target_label": target["label"],
        "target_tables": {name: table["count"]
                          for name, table in sorted(target["tables"].items())},
        "files_replaced": sorted(receipt.get("files_replaced") or []),
        "unchanged_bytes_compared": compared,
        "iso_verify": {key: iso_result[key] for key in sorted(iso_result)
                       if key in ("result", "unchanged_bytes_compared",
                                  "declared_bytes", "entry_count")},
    }


def write_json(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

def selftest(tmp: Optional[str] = None) -> int:
    """Accept a correct write; reject the ways it can rot.  Needs no game data."""
    import tempfile

    import nfl2k5_ps2_disc_roster_patch as writer            # fixture generator only
    import nfl2k5_ps2_disc_roster_target_catalog as fixture  # fixture generator only

    failures = []  # type: List[str]

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work)
        source = room / "stock.iso"
        source.write_bytes(fixture.build_synthetic_iso())
        recipe = writer.parse_recipe({"schema": writer.RECIPE_SCHEMA, "edits": [
            {"pool": "primary_players", "player": 0,
             "first_name": "Dwane", "jersey_number": 7},
            {"pool": "primary_players", "player": 1, "face_shield": 2},
        ]})
        good = room / "edited.iso"
        receipt = writer.apply(source, good, recipe)

        report = verify(source, good, receipt)
        check(report["result"] == "PASS", "a correct write must verify")
        check(report["edits_checked"] == 3, "three declared edits must be checked")
        check(report["name_edits_checked"] == 1, "one name edit must be checked")
        check(report["packed_edits_checked"] == 2, "two packed edits must be checked")
        check(report["target_label"] == "roster", "the boot roster must be the target")
        check(report["rost_resources_decoded"] == 2,
              "both decodable ROST resources must survive")
        check(report["unchanged_bytes_compared"] > 0,
              "the out-of-lane comparison must read something")

        verify(source, good, json.loads(json.dumps(receipt)))

        def poke(path: Path, offset: int, value: bytes) -> None:
            with open(str(path), "r+b") as handle:
                handle.seek(offset)
                handle.write(value)

        def rejected(name: str, mutate, why: str, override=None) -> None:
            candidate = room / name
            candidate.write_bytes(good.read_bytes())
            mutate(candidate)
            try:
                verify(source, candidate, override or receipt)
            except (RosterVerifyError, iso_verify.IsoVerifyError):
                return
            failures.append("%s must fail verification" % why)

        catalog = fixture.build_catalog(str(source))
        boot = fixture.boot_roster(catalog)
        player = fixture.find_player(catalog, 2)
        stray = boot["body_offset_in_iso"] + player["packed_word_offset"]
        rejected("stray.iso", lambda path: poke(path, stray, b"\x00\x00\x00\x00"),
                 "a byte changed outside every declared range")
        target = fixture.find_player(catalog, 0)
        rejected("forged.iso",
                 lambda path: poke(path, boot["body_offset_in_iso"]
                                   + target["first_name_offset"],
                                   "Zed\x00".encode("utf-16le")),
                 "a declared span that disagrees with the receipt")
        rejected("moved.iso",
                 lambda path: poke(path, boot["body_offset_in_iso"]
                                   + boot["root"] + 0x04, b"\x99\x99\x00\x00"),
                 "a table pointer that moved")

        forged = json.loads(json.dumps(receipt))
        forged["edits"][0]["before_sha256"] = "0" * 64
        try:
            verify(source, good, forged)
        except RosterVerifyError:
            pass
        else:
            failures.append("a receipt lying about the stock bytes must fail")

        forged = json.loads(json.dumps(receipt))
        for row in forged["edits"]:
            if row["kind"] == "packed":
                row["fields"] = []
        try:
            verify(source, good, forged)
        except RosterVerifyError:
            pass
        else:
            failures.append("a packed edit claiming no fields must fail")

        forged = json.loads(json.dumps(receipt))
        forged["declared_ranges"] = forged["declared_ranges"][:1]
        try:
            verify(source, good, forged)
        except RosterVerifyError:
            pass
        else:
            failures.append("dropping a declared range must fail")

        forged = json.loads(json.dumps(receipt))
        forged["schema"] = "nope"
        try:
            verify(source, good, forged)
        except RosterVerifyError:
            pass
        else:
            failures.append("a receipt with the wrong schema must fail")

    for failure in failures:
        print("FAIL: %s" % failure, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_DISC_ROSTER_VERIFY_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--report", type=Path, help="write the verdict here")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--tmp", help="directory for self-test scratch files")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.tmp)
    if not (args.source and args.destination and args.receipt):
        parser.error("--source, --destination and --receipt are required")

    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        report = verify(args.source, args.destination, receipt)
    except (RosterVerifyError, iso_verify.IsoVerifyError, OSError, ValueError,
            UnicodeDecodeError) as exc:
        print("NFL2K5_PS2_DISC_ROSTER_VERIFY_FAIL %s" % exc, file=sys.stderr)
        return 1

    if args.report:
        write_json(args.report, report)
    print("NFL2K5_PS2_DISC_ROSTER_VERIFY_PASS edits=%d names=%d packed=%d "
          "rost=%d outer=%d unchanged_bytes=%d"
          % (report["edits_checked"], report["name_edits_checked"],
             report["packed_edits_checked"], report["rost_resources_decoded"],
             report["target_outer_index"], report["unchanged_bytes_compared"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
