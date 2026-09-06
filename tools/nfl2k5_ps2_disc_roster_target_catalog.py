#!/usr/bin/env python3
"""Catalogue the on-disc ``ROST`` rosters of the ESPN NFL 2K5 PS2 disc.

``SLUS-20919`` ships 76 ``ROST`` resources.  Exactly one of them -- the object
labelled ``roster``, outer entry 5 -- is the roster the game boots into; the
other 75 are labelled ``historic`` and hold a 53-man all-time squad each.  This
tool reads a user's own ISO and reports where every one of them lives, whether
it decodes, and, for the boot roster, the **fixed-allocation budget of every
editable field**.

Parity with the two proved lanes
--------------------------------
The disc arena is the same Visual Concepts object the PS2 memory-card save
carries, so ``tools/nfl_roster.py`` parses it unchanged -- the same parser the
shipped save editor uses.  Measured on the retail disc: all 76 chunks decode at
version 17, root 0x40, and the boot roster holds 2,479 primary + 68 secondary =
**2,547 player records**, exactly the population the Xbox
``nfl2k5.players.disc_roster`` row names.

Editable fields, and why each is bounded
----------------------------------------
* ``jersey_number`` -- ``record +0x20`` bits 3..9, values 0..99.
* ``face_shield``   -- ``record +0x20`` bits 15..16, 0 None / 1 Clear / 2 Dark.
  Both are masked writes into one word: every unrelated bit is preserved.
* ``first_name`` / ``last_name`` -- UTF-16LE strings reached by the engine's
  ``target = field + int32le(field) - 1`` pointer.  A replacement must fit the
  bytes the original occupies, terminator included, so the arena's pointers
  never move.  A slot is writable only when **nothing else in the arena points
  at that string** and its capacity is greater than the bare terminator.

Retail-free by construction
---------------------------
The catalogue carries offsets, lengths, digests, player names and jersey
numbers -- public roster data.  It does **not** carry the packed equipment word
or any rating byte; those are digested instead and read from the operator's own
image at edit time.

Usage::

    nfl2k5_ps2_disc_roster_target_catalog.py --iso <SLUS-20919.iso> \\
        --output reports/gameplay_tuning/nfl2k5_ps2_disc_roster_catalog.v1.json
    nfl2k5_ps2_disc_roster_target_catalog.py --iso <iso> --inspect 12
    nfl2k5_ps2_disc_roster_target_catalog.py --selftest

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import nfl2k5_ps2_unif_color_target_catalog as archive_tool  # noqa: E402
import nfl_roster  # noqa: E402  (the shared ROST parser, used unchanged)
import ps2_iso9660 as iso  # noqa: E402


SCHEMA = "nfl2k5_ps2_disc_roster_catalog/v1"
SERIAL = archive_tool.SERIAL
CHUNK_HEADER_SIZE = archive_tool.CHUNK_HEADER_SIZE
COMPRESSED_SENTINEL = archive_tool.COMPRESSED_SENTINEL
ALIGNMENT = archive_tool.ALIGNMENT

ROST_TAG = b"ROST"
#: Object preamble, as ``nfl_roster.parse_resource`` requires it.
OBJECT_MAGIC_OFFSET = 0x0C
OBJECT_VERSION_OFFSET = 0x10
OBJECT_ROOT_POINTER = 0x14
OBJECT_LABEL_OFFSET = 0x20
DISC_VERSION = 17
DISC_ROOT = 0x40
BOOT_LABEL = "roster"
HISTORIC_LABEL = "historic"

PLAYER_STRIDE = nfl_roster.NFL_PLAYER_STRIDE          # 0x54
PLAYER_FIRST_NAME_FIELD = 0x10
PLAYER_LAST_NAME_FIELD = 0x14
#: The packed equipment word and its two proved fields (Xbox-proved, re-checked
#: here against the PS2 arena: every decoded jersey lands in 0..99 and no
#: face-shield selector uses the reserved value 3).
PACKED_WORD_FIELD = 0x20
JERSEY_MASK = 0x3F8
JERSEY_SHIFT = 3
JERSEY_MAX = 99
FACE_SHIELD_MASK = 0x18000
FACE_SHIELD_SHIFT = 15
FACE_SHIELD_VALUES = (0, 1, 2)
FACE_SHIELD_NAMES = {0: "none", 1: "clear", 2: "dark"}
NAME_TERMINATOR_BYTES = 2
POOLS = ("primary_players", "secondary_players")

#: Every table whose records carry string pointers, so a name's global
#: reference count can be counted rather than assumed.
_STRING_FIELDS = {
    "colleges": (0x08, (0x00,)),
    "stadiums": (0x80, (0x00, 0x08, 0x0C, 0x10, 0x14)),
    "coaches": (0xA8, (0x00, 0x04, 0x08, 0x0C, 0x10)),
    "team_labels": (0x08, (0x00, 0x04)),
    "generated_names": (0x08, (0x00, 0x04)),
    "historic_descriptors": (0x10, (0x0C,)),
    "teams": (nfl_roster.NFL_TEAM_STRIDE,
              (0x104, 0x108, 0x10C, 0x138, 0x13C)),
}


class RosterCatalogError(ValueError):
    """A disc did not present the roster layout this tool requires."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise RosterCatalogError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Arena decoding
# --------------------------------------------------------------------------

def string_capacity(body: bytes, pointer: int) -> int:
    """Bytes the stored UTF-16LE string occupies, terminator included."""
    end = pointer
    while end + 2 <= len(body) and body[end:end + 2] != b"\x00\x00":
        end += 2
    _require(end + 2 <= len(body),
             "a name string at 0x%x has no terminator inside the arena" % pointer)
    return end - pointer + NAME_TERMINATOR_BYTES


def string_reference_counts(body: bytes, tables: Dict[str, Any]) -> Dict[int, int]:
    """How many fields anywhere in the arena point at each string offset."""
    counts = {}  # type: Dict[int, int]

    def note(field: int) -> None:
        pointer = nfl_roster.relative_pointer(body, field, "string reference")
        if pointer is not None:
            counts[pointer] = counts.get(pointer, 0) + 1

    for pool in POOLS:
        table = tables[pool]
        for index in range(int(table["count"])):
            record = int(table["offset"]) + index * PLAYER_STRIDE
            note(record + PLAYER_FIRST_NAME_FIELD)
            note(record + PLAYER_LAST_NAME_FIELD)
    for name, (stride, fields) in _STRING_FIELDS.items():
        table = tables.get(name)
        if table is None:
            continue
        for index in range(int(table["count"])):
            record = int(table["offset"]) + index * stride
            for field in fields:
                note(record + field)
    return counts


def decode_players(body: bytes, tables: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every player record's editable-field geometry, budget included."""
    references = string_reference_counts(body, tables)
    players = []  # type: List[Dict[str, Any]]
    for pool in POOLS:
        table = tables[pool]
        for index in range(int(table["count"])):
            record = int(table["offset"]) + index * PLAYER_STRIDE
            word = struct.unpack_from("<I", body, record + PACKED_WORD_FIELD)[0]
            row = {
                "pool": pool,
                "index": index,
                "record_offset": record,
                "jersey_number": (word >> JERSEY_SHIFT) & 0x7F,
                "packed_word_sha256": _digest(
                    body[record + PACKED_WORD_FIELD:
                         record + PACKED_WORD_FIELD + 4]),
                "packed_word_offset": record + PACKED_WORD_FIELD,
            }
            for label, field in (("first_name", PLAYER_FIRST_NAME_FIELD),
                                 ("last_name", PLAYER_LAST_NAME_FIELD)):
                pointer = nfl_roster.relative_pointer(
                    body, record + field, "%s %d %s" % (pool, index, label))
                if pointer is None:
                    row[label] = None
                    row[label + "_offset"] = None
                    row[label + "_capacity"] = 0
                    row[label + "_references"] = 0
                    row[label + "_writable"] = False
                    continue
                capacity = string_capacity(body, pointer)
                value = body[pointer:pointer + capacity - NAME_TERMINATOR_BYTES]
                row[label] = value.decode("utf-16le", "replace")
                row[label + "_offset"] = pointer
                row[label + "_capacity"] = capacity
                row[label + "_references"] = references.get(pointer, 0)
                row[label + "_writable"] = (
                    capacity > NAME_TERMINATOR_BYTES
                    and references.get(pointer, 0) == 1
                )
            players.append(row)
    return players


def decode_roster(body: bytes, label_prefix: str) -> Dict[str, Any]:
    """Preamble, tables and label of one ``ROST`` object body."""
    _require(len(body) >= 0x40, "%s: the ROST preamble is short" % label_prefix)
    _require(body[OBJECT_MAGIC_OFFSET:OBJECT_MAGIC_OFFSET + 4] == ROST_TAG,
             "%s: the ROST object tag is missing" % label_prefix)
    version = struct.unpack_from("<I", body, OBJECT_VERSION_OFFSET)[0]
    root = nfl_roster.relative_pointer(body, OBJECT_ROOT_POINTER,
                                       "%s root" % label_prefix)
    _require(root is not None, "%s: the ROST root pointer is null" % label_prefix)
    label = nfl_roster.utf16z(body, OBJECT_LABEL_OFFSET, "%s label" % label_prefix)
    tables = nfl_roster.parse_tables(body, root, 0)
    return {"version": version, "root": root, "label": label, "tables": tables}


# --------------------------------------------------------------------------
# Disc scan
# --------------------------------------------------------------------------

def scan(iso_path: str) -> Dict[str, Any]:
    """Every ``ROST`` chunk on the image, decoded where it can be."""
    image = iso.open_image(iso_path)
    packs = archive_tool.discover_packs(image)
    rosters = []  # type: List[Dict[str, Any]]
    rejected = []  # type: List[Dict[str, Any]]
    boot_players = None  # type: Optional[List[Dict[str, Any]]]
    with archive_tool.PackedArchive(str(iso_path), packs) as archive:
        _header, entries = archive_tool.read_outer_table(archive)
        for index, (name_id, entry_size, offset_blocks) in enumerate(entries):
            if entry_size < CHUNK_HEADER_SIZE:
                continue
            virtual = offset_blocks * ALIGNMENT
            if archive.read(virtual, 4) != ROST_TAG:
                continue
            head = archive.read(virtual, CHUNK_HEADER_SIZE)
            stored, system_bytes, video_bytes, sentinel = struct.unpack_from(
                "<4I", head, 4)
            compressed = sentinel == COMPRESSED_SENTINEL
            label_prefix = "outer %d" % index
            if compressed:
                rejected.append({
                    "outer_index": index,
                    "outer_name_id": "0x%08x" % name_id,
                    "reason": "the ROST body is LZ-compressed; a fixed-allocation "
                              "edit would have to be recompressed back into the "
                              "stored span, which this lane refuses",
                })
                continue
            if not stored or CHUNK_HEADER_SIZE + stored > entry_size:
                rejected.append({
                    "outer_index": index,
                    "outer_name_id": "0x%08x" % name_id,
                    "reason": "the ROST body of %d bytes does not fit its %d-byte "
                              "entry" % (stored, entry_size),
                })
                continue
            body = archive.read(virtual + CHUNK_HEADER_SIZE, stored)
            try:
                decoded = decode_roster(body, label_prefix)
            except (RosterCatalogError, nfl_roster.RosterError) as exc:
                rejected.append({
                    "outer_index": index,
                    "outer_name_id": "0x%08x" % name_id,
                    "reason": str(exc),
                })
                continue
            ordinal, pack_path, in_pack, iso_offset = archive.locate(
                virtual, CHUNK_HEADER_SIZE + stored)
            row = {
                "outer_index": index,
                "outer_name_id": "0x%08x" % name_id,
                "label": decoded["label"],
                "boot_roster": decoded["label"] == BOOT_LABEL,
                "version": decoded["version"],
                "root": decoded["root"],
                "pack": archive.packs[ordinal][0],
                "iso_path": pack_path,
                "chunk_virtual_offset": virtual,
                "chunk_offset_in_pack": in_pack,
                "chunk_offset_in_iso": iso_offset,
                "body_offset_in_pack": in_pack + CHUNK_HEADER_SIZE,
                "body_offset_in_iso": iso_offset + CHUNK_HEADER_SIZE,
                "stored_size": stored,
                "system_bytes": system_bytes,
                "video_bytes": video_bytes,
                "compressed": compressed,
                "body_sha256": _digest(body),
                "tables": {name: int(table["count"])
                           for name, table in decoded["tables"].items()},
                "table_offsets": {name: int(table["offset"])
                                  for name, table in decoded["tables"].items()},
            }
            if row["boot_roster"]:
                _require(boot_players is None,
                         "two ROST objects claim the %r label; the boot roster "
                         "must be unique" % BOOT_LABEL)
                boot_players = decode_players(body, decoded["tables"])
                row["players"] = len(boot_players)
            rosters.append(row)
    rosters.sort(key=lambda row: row["outer_index"])
    return {"rosters": rosters, "rejected": rejected, "players": boot_players,
            "packs": [{"pack": letter, "iso_path": path, "size": size}
                      for letter, _base, size, path in packs],
            "volume_id": image.volume_id, "volume_blocks": image.volume_blocks}


def build_catalog(iso_path: str) -> Dict[str, Any]:
    """The shippable catalogue: geometry, budgets, digests and public names."""
    found = scan(iso_path)
    rosters = found["rosters"]
    _require(rosters, "no ROST resources found on %s" % iso_path)
    boot = [row for row in rosters if row["boot_roster"]]
    _require(len(boot) == 1,
             "%d ROST objects are labelled %r; exactly one boot roster is "
             "expected" % (len(boot), BOOT_LABEL))
    players = found["players"] or []
    jerseys = [row["jersey_number"] for row in players]
    _require(all(0 <= value <= JERSEY_MAX for value in jerseys),
             "a decoded jersey number falls outside 0..%d; the packed-word "
             "layout does not hold on this image" % JERSEY_MAX)
    writable_names = sum(1 for row in players
                         for label in ("first_name", "last_name")
                         if row[label + "_writable"])
    capacities = {}  # type: Dict[str, int]
    for row in players:
        for label in ("first_name", "last_name"):
            key = str(row[label + "_capacity"])
            capacities[key] = capacities.get(key, 0) + 1
    return {
        "schema": SCHEMA,
        "serial": SERIAL,
        "source": {
            "volume_id": found["volume_id"],
            "volume_blocks": found["volume_blocks"],
            "size": Path(iso_path).stat().st_size,
            "packs": found["packs"],
        },
        "layout": {
            "chunk_header_size": CHUNK_HEADER_SIZE,
            "object_magic_offset": OBJECT_MAGIC_OFFSET,
            "object_version": DISC_VERSION,
            "object_root": DISC_ROOT,
            "player_stride": PLAYER_STRIDE,
            "packed_word_field": PACKED_WORD_FIELD,
            "jersey": {"mask": "0x%x" % JERSEY_MASK, "shift": JERSEY_SHIFT,
                       "range": [0, JERSEY_MAX]},
            "face_shield": {"mask": "0x%x" % FACE_SHIELD_MASK,
                            "shift": FACE_SHIELD_SHIFT,
                            "values": list(FACE_SHIELD_VALUES),
                            "names": {str(k): v for k, v in FACE_SHIELD_NAMES.items()}},
            "name_fields": {"first_name": PLAYER_FIRST_NAME_FIELD,
                            "last_name": PLAYER_LAST_NAME_FIELD},
            "name_pointer_rule": "target = field + int32le(field) - 1",
            "note": "A name replacement must fit the bytes the original "
                    "occupies, terminator included; a slot is writable only when "
                    "nothing else in the arena points at that string.",
        },
        "summary": {
            "rost_chunks": len(rosters),
            "boot_rosters": len(boot),
            "historic_rosters": sum(1 for row in rosters
                                    if row["label"] == HISTORIC_LABEL),
            "compressed": sum(1 for row in rosters if row["compressed"]),
            "rejected": len(found["rejected"]),
            "boot_outer_index": boot[0]["outer_index"],
            "boot_players": len(players),
            "boot_primary_players": sum(1 for row in players
                                        if row["pool"] == "primary_players"),
            "boot_secondary_players": sum(1 for row in players
                                          if row["pool"] == "secondary_players"),
            "writable_name_slots": writable_names,
            "name_capacity_histogram": capacities,
        },
        "retail_free": {
            "packed_equipment_word_included": False,
            "ratings_included": False,
            "note": "Player names and jersey numbers are public roster data. "
                    "The packed equipment word (which also carries the "
                    "face-shield selector) is recorded only as a digest and is "
                    "read from the operator's own image at edit time.",
        },
        "rosters": rosters,
        "rejected": found["rejected"],
        "players": players,
    }


def find_player(catalog: Dict[str, Any], index: int,
                pool: str = "primary_players") -> Dict[str, Any]:
    matches = [row for row in catalog.get("players", [])
               if row["pool"] == pool and row["index"] == int(index)]
    _require(matches, "no %s record at index %s" % (pool, index))
    return matches[0]


def boot_roster(catalog: Dict[str, Any]) -> Dict[str, Any]:
    matches = [row for row in catalog["rosters"] if row["boot_roster"]]
    _require(len(matches) == 1, "the catalogue has no single boot roster")
    return matches[0]


def write_json(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


# --------------------------------------------------------------------------
# Synthetic fixture
# --------------------------------------------------------------------------

def _pointer(field: int, target: int) -> bytes:
    return struct.pack("<i", target - field + 1)


def _utf16(text: str) -> bytes:
    return text.encode("utf-16le") + b"\x00\x00"


def rost_chunk(label: str, players: Sequence[Tuple[str, str, int, int]], *,
               compressed: bool = False, version: int = DISC_VERSION,
               secondary: int = 0) -> bytes:
    """A retail-shaped ``ROST`` chunk with one team and ``players`` in it."""
    root = DISC_ROOT
    root_size = nfl_roster.NFL_ROOT_SIZE
    primary = len(players) - secondary
    table_at = root + root_size
    player_bytes = len(players) * PLAYER_STRIDE
    team_at = table_at + player_bytes
    strings_at = team_at + nfl_roster.NFL_TEAM_STRIDE
    strings = bytearray()
    offsets = []
    for first, last, _jersey, _shield in players:
        for text in (first, last):
            offsets.append(strings_at + len(strings))
            strings.extend(_utf16(text))
    body = bytearray(strings_at + len(strings))
    body[OBJECT_MAGIC_OFFSET:OBJECT_MAGIC_OFFSET + 4] = ROST_TAG
    struct.pack_into("<I", body, OBJECT_VERSION_OFFSET, version)
    body[OBJECT_ROOT_POINTER:OBJECT_ROOT_POINTER + 4] = _pointer(
        OBJECT_ROOT_POINTER, root)
    label_bytes = _utf16(label)
    body[OBJECT_LABEL_OFFSET:OBJECT_LABEL_OFFSET + len(label_bytes)] = label_bytes
    for spec in nfl_roster.TABLE_SPECS:
        count = 0
        pointer = table_at
        if spec.name == "primary_players":
            count = primary
        elif spec.name == "secondary_players":
            count = secondary
            pointer = table_at + primary * PLAYER_STRIDE
        elif spec.name == "teams":
            count, pointer = 1, team_at
        struct.pack_into("<I", body, root + spec.count_offset, count)
        body[root + spec.pointer_offset:root + spec.pointer_offset + 4] = _pointer(
            root + spec.pointer_offset, pointer)
    for ordinal, (_first, _last, jersey, shield) in enumerate(players):
        record = table_at + ordinal * PLAYER_STRIDE
        word = ((jersey & 0x7F) << JERSEY_SHIFT) | ((shield & 3) << FACE_SHIELD_SHIFT)
        struct.pack_into("<I", body, record + PACKED_WORD_FIELD, word)
        body[record + PLAYER_FIRST_NAME_FIELD:record + PLAYER_FIRST_NAME_FIELD + 4] = \
            _pointer(record + PLAYER_FIRST_NAME_FIELD, offsets[ordinal * 2])
        body[record + PLAYER_LAST_NAME_FIELD:record + PLAYER_LAST_NAME_FIELD + 4] = \
            _pointer(record + PLAYER_LAST_NAME_FIELD, offsets[ordinal * 2 + 1])
    body[strings_at:strings_at + len(strings)] = strings
    header = bytearray(CHUNK_HEADER_SIZE)
    header[0:4] = ROST_TAG
    struct.pack_into("<4I", header, 4, len(body), len(body), 0,
                     COMPRESSED_SENTINEL if compressed else 0)
    return bytes(header) + bytes(body)


def build_synthetic_iso() -> bytes:
    """A PS2-shaped image with a boot roster, a historic roster and a bad one."""
    boot = rost_chunk(BOOT_LABEL, [
        ("Duane", "Starks", 28, 0),
        ("Renaldo", "Hill", 21, 1),
        ("Coby", "Rhinehart", 23, 2),
        ("", "", 0, 0),               # a zero-capacity placeholder slot
    ], secondary=1)
    historic = rost_chunk(HISTORIC_LABEL, [("Bart", "Starr", 15, 0)])
    broken = rost_chunk(HISTORIC_LABEL, [("Otto", "Graham", 60, 0)],
                        compressed=True)
    return archive_tool.build_synthetic_iso(entries=[
        ("ROSTER.IFF", boot),
        ("HISTORIC1.IFF", historic),
        ("HISTORIC2.IFF", broken),
    ])


def selftest(tmp: Optional[str] = None) -> int:
    """Prove the scan on a synthetic disc.  Needs no game data."""
    import tempfile

    failures = []  # type: List[str]

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        image = Path(work) / "synthetic.iso"
        image.write_bytes(build_synthetic_iso())
        catalog = build_catalog(str(image))
        summary = catalog["summary"]
        check(catalog["schema"] == SCHEMA, "schema must be stamped")
        check(summary["rost_chunks"] == 2, "two decodable ROST chunks expected")
        check(summary["boot_rosters"] == 1, "exactly one boot roster expected")
        check(summary["historic_rosters"] == 1, "one historic roster expected")
        check(summary["rejected"] == 1, "the compressed ROST must be rejected")
        check(summary["boot_players"] == 4, "four boot players expected")
        check(summary["boot_primary_players"] == 3, "three primary players expected")
        check(summary["boot_secondary_players"] == 1, "one secondary player expected")
        check(summary["writable_name_slots"] == 6,
              "six writable name slots expected, got %d"
              % summary["writable_name_slots"])

        player = find_player(catalog, 0)
        check(player["first_name"] == "Duane", "the first name must decode")
        check(player["jersey_number"] == 28, "the jersey number must decode")
        check(player["first_name_capacity"] == len("Duane") * 2 + 2,
              "capacity must be the stored bytes plus a terminator")
        check(player["first_name_writable"], "a uniquely referenced name is writable")
        check("face_shield" not in player,
              "the catalogue must not carry the packed equipment field")

        placeholder = find_player(catalog, 0, "secondary_players")
        check(placeholder["first_name_capacity"] == 2,
              "the placeholder slot must be bare-terminator sized")
        check(not placeholder["first_name_writable"],
              "a zero-capacity slot must not be writable")

        boot = boot_roster(catalog)
        check(boot["version"] == DISC_VERSION, "the boot roster must be version 17")
        check(boot["root"] == DISC_ROOT, "the boot roster root must be 0x40")
        check(boot["iso_path"].upper().startswith("/VC_20919/"),
              "the boot roster must name its pack file")

        try:
            find_player(catalog, 99)
        except RosterCatalogError:
            pass
        else:
            failures.append("find_player accepted an absent index")

        output = Path(work) / "catalog.json"
        write_json(output, catalog)
        check(json.loads(output.read_text(encoding="utf-8"))["schema"] == SCHEMA,
              "the written catalogue must re-read")

    for failure in failures:
        print("FAIL: %s" % failure, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_DISC_ROSTER_CATALOG_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", help="the operator's own SLUS-20919 ISO")
    parser.add_argument("--output", type=Path, help="catalogue JSON to write")
    parser.add_argument("--inspect", type=int, metavar="INDEX",
                        help="print one boot-roster player and exit")
    parser.add_argument("--pool", default="primary_players", choices=POOLS)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--tmp", help="directory for self-test scratch files")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.tmp)
    if not args.iso:
        parser.error("--iso is required unless --selftest is given")

    try:
        catalog = build_catalog(args.iso)
    except (RosterCatalogError, nfl_roster.RosterError, archive_tool.CatalogError,
            OSError, iso.FormatError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.inspect is not None:
        try:
            player = find_player(catalog, args.inspect, args.pool)
        except RosterCatalogError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        boot = boot_roster(catalog)
        base = boot["body_offset_in_iso"]
        with open(args.iso, "rb") as stream:
            stream.seek(base + player["packed_word_offset"])
            word = struct.unpack("<I", stream.read(4))[0]
        print("pool            %s" % player["pool"])
        print("index           %d" % player["index"])
        print("name            %s %s" % (player["first_name"], player["last_name"]))
        print("jersey number   %d" % player["jersey_number"])
        print("face shield     %d (%s)"
              % ((word >> FACE_SHIELD_SHIFT) & 3,
                 FACE_SHIELD_NAMES.get((word >> FACE_SHIELD_SHIFT) & 3, "reserved")))
        for label in ("first_name", "last_name"):
            print("%-15s capacity %d bytes, %d reference(s), writable %s"
                  % (label, player[label + "_capacity"],
                     player[label + "_references"], player[label + "_writable"]))
        return 0

    if args.output:
        write_json(args.output, catalog)
    summary = catalog["summary"]
    print("NFL2K5_PS2_DISC_ROSTER_CATALOG_OK rost=%d boot_outer=%d players=%d "
          "primary=%d secondary=%d writable_names=%d historic=%d rejected=%d"
          % (summary["rost_chunks"], summary["boot_outer_index"],
             summary["boot_players"], summary["boot_primary_players"],
             summary["boot_secondary_players"], summary["writable_name_slots"],
             summary["historic_rosters"], summary["rejected"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
