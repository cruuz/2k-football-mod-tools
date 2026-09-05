#!/usr/bin/env python3
"""Write fixed-allocation roster edits into a copy of a PS2 NFL 2K5 disc.

This is the disc half of NFL 2K5's roster surface on PS2.  The memory-card save
editor (``tools/nfl2k5_ps2_save.py``, shipped and PCSX2-verified) already edits
the ``ROST`` arena a *save* carries; the disc ships the same Visual Concepts
object as the seed the game boots into, so the same bounded edits apply to it.

What it writes, and the bound on each
-------------------------------------
* ``jersey_number`` -- ``record +0x20`` bits 3..9, 0..99.
* ``face_shield``   -- ``record +0x20`` bits 15..16, 0 None / 1 Clear / 2 Dark.
  The reserved value 3 is refused.  Both are masked writes into one word and
  every unrelated bit of that word is preserved -- checked, not assumed.
* ``first_name`` / ``last_name`` -- UTF-16LE, **fixed allocation**: a
  replacement must fit the bytes the original occupies, terminator included, so
  the arena's pointers never move.  A slot whose string is referenced from
  anywhere else in the arena, or which is a bare terminator (an empty
  placeholder), is refused.

Discipline
----------
* The source image is opened read-only; a new image comes out of
  ``ps2_iso9660_writer.replace_files``, which patches inside existing extents
  only and keeps the image's exact byte length.
* An LZ-compressed ``ROST`` body is refused: the edit would have to be
  recompressed back into its stored span.  No retail ``ROST`` chunk is
  compressed (0 of 76 measured).
* With ``--catalog``, the target roster's body digest and geometry must equal
  the pinned catalogue's, so a modded image is refused rather than written.
* Nothing is created until every check passes, so a refusal leaves no
  destination behind.
* A loaded roster or franchise save may override this disc seed -- the same
  caveat the Xbox row carries.

Usage::

    nfl2k5_ps2_disc_roster_patch.py --source <stock.iso> --destination <new.iso> \\
        --recipe <recipe.json> [--catalog <catalog.json>] [--receipt <receipt.json>]
    nfl2k5_ps2_disc_roster_patch.py --source <stock.iso> --recipe <r.json> --dry-run
    nfl2k5_ps2_disc_roster_patch.py --selftest

Recipe (``nfl2k5_ps2_disc_roster_recipe/v1``)::

    {"schema": "nfl2k5_ps2_disc_roster_recipe/v1",
     "roster": "boot",
     "edits": [{"pool": "primary_players", "player": 0,
                "first_name": "Duante", "jersey_number": 7}]}

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
from typing import Any, Dict, List, Optional, Sequence

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import nfl2k5_ps2_disc_roster_target_catalog as catalog_tool  # noqa: E402
import nfl2k5_ps2_unif_color_target_catalog as archive_tool  # noqa: E402
import ps2_iso9660 as iso  # noqa: E402
import ps2_iso9660_writer as iso_writer  # noqa: E402


SCHEMA = "nfl2k5_ps2_disc_roster_write/v1"
RECIPE_SCHEMA = "nfl2k5_ps2_disc_roster_recipe/v1"
SERIAL = catalog_tool.SERIAL
POOLS = catalog_tool.POOLS
NAME_FIELDS = ("first_name", "last_name")
PACKED_FIELDS = ("jersey_number", "face_shield")
JERSEY_MASK = catalog_tool.JERSEY_MASK
JERSEY_SHIFT = catalog_tool.JERSEY_SHIFT
JERSEY_MAX = catalog_tool.JERSEY_MAX
FACE_SHIELD_MASK = catalog_tool.FACE_SHIELD_MASK
FACE_SHIELD_SHIFT = catalog_tool.FACE_SHIELD_SHIFT
FACE_SHIELD_VALUES = catalog_tool.FACE_SHIELD_VALUES
TERMINATOR = catalog_tool.NAME_TERMINATOR_BYTES
COPY_CHUNK = 8 * 1024 * 1024
MAX_EDITS = 2547


class RosterPatchError(ValueError):
    """A roster edit would have broken one of this writer's guarantees."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise RosterPatchError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Recipe
# --------------------------------------------------------------------------

def load_recipe(path: Path) -> Dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RosterPatchError("recipe %s cannot be read: %s" % (path, exc))
    return parse_recipe(document)


def parse_recipe(document: Any) -> Dict[str, Any]:
    """Read and fully validate a recipe; return its normalised form."""
    _require(isinstance(document, dict), "a recipe must be a JSON object")
    _require(document.get("schema") == RECIPE_SCHEMA,
             "recipe schema is %r, expected %r"
             % (document.get("schema"), RECIPE_SCHEMA))
    roster = document.get("roster", "boot")
    _require(isinstance(roster, str) and roster.strip(),
             "the 'roster' selector must be 'boot' or 'outer:<index>'")
    roster = roster.strip().lower()
    _require(roster == "boot" or roster.startswith("outer:"),
             "the 'roster' selector must be 'boot' or 'outer:<index>', not %r"
             % roster)
    edits = document.get("edits")
    _require(isinstance(edits, list) and edits,
             "a recipe must carry a non-empty 'edits' list")
    _require(len(edits) <= MAX_EDITS,
             "%d edits is past the %d sanity cap" % (len(edits), MAX_EDITS))

    seen = set()
    parsed = []  # type: List[Dict[str, Any]]
    allowed = {"pool", "player", "note"} | set(NAME_FIELDS) | set(PACKED_FIELDS)
    for ordinal, raw in enumerate(edits):
        _require(isinstance(raw, dict), "edit %d is not an object" % ordinal)
        unknown = set(raw) - allowed
        _require(not unknown,
                 "edit %d carries unknown keys %s; this writer only edits the "
                 "proved fields %s"
                 % (ordinal, sorted(unknown), sorted(set(NAME_FIELDS) | set(PACKED_FIELDS))))
        pool = raw.get("pool", "primary_players")
        _require(pool in POOLS,
                 "edit %d names pool %r; expected one of %s"
                 % (ordinal, pool, list(POOLS)))
        player = raw.get("player")
        _require(isinstance(player, int) and not isinstance(player, bool)
                 and player >= 0,
                 "edit %d has no non-negative integer 'player' index" % ordinal)
        key = (pool, player)
        _require(key not in seen,
                 "%s %d appears twice; one record may be written once"
                 % (pool, player))
        seen.add(key)

        changes = {}  # type: Dict[str, Any]
        if raw.get("jersey_number") is not None:
            value = raw["jersey_number"]
            _require(isinstance(value, int) and not isinstance(value, bool)
                     and 0 <= value <= JERSEY_MAX,
                     "edit %d: jersey_number must be an integer 0..%d, not %r"
                     % (ordinal, JERSEY_MAX, value))
            changes["jersey_number"] = value
        if raw.get("face_shield") is not None:
            value = raw["face_shield"]
            _require(isinstance(value, int) and not isinstance(value, bool)
                     and value in FACE_SHIELD_VALUES,
                     "edit %d: face_shield must be 0 None, 1 Clear or 2 Dark; "
                     "the reserved value 3 is refused (%r given)"
                     % (ordinal, value))
            changes["face_shield"] = value
        for field in NAME_FIELDS:
            if raw.get(field) is None:
                continue
            value = raw[field]
            _require(isinstance(value, str),
                     "edit %d: %s must be a string" % (ordinal, field))
            try:
                value.encode("utf-16le")
            except UnicodeEncodeError as exc:
                raise RosterPatchError(
                    "edit %d: %s is not encodable as UTF-16LE: %s"
                    % (ordinal, field, exc))
            _require("\x00" not in value,
                     "edit %d: %s may not contain a NUL" % (ordinal, field))
            changes[field] = value
        _require(changes, "edit %d for %s %d changes nothing"
                 % (ordinal, pool, player))
        parsed.append({"pool": pool, "player": player, "changes": changes,
                       "note": raw.get("note")})
    return {"roster": roster, "edits": parsed}


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------

def _resolve_roster(catalog: Dict[str, Any], selector: str) -> Dict[str, Any]:
    if selector == "boot":
        return catalog_tool.boot_roster(catalog)
    try:
        index = int(selector.split(":", 1)[1], 0)
    except (IndexError, ValueError):
        raise RosterPatchError("%r is not an outer index" % selector)
    matches = [row for row in catalog["rosters"] if row["outer_index"] == index]
    if not matches:
        rejected = [row for row in catalog.get("rejected", [])
                    if row["outer_index"] == index]
        if rejected:
            raise RosterPatchError(
                "outer %d is an unsafe target: %s. Refusing rather than writing "
                "into a resource this capability cannot decode."
                % (index, rejected[0]["reason"]))
        raise RosterPatchError(
            "outer %d is not a catalogued ROST resource; an out-of-range roster "
            "selector is refused rather than guessed at" % index)
    return matches[0]


def _pack_bases(image) -> Dict[str, Dict[str, int]]:
    return {path: {"offset": base, "size": size, "pack": letter}
            for letter, base, size, path in archive_tool.discover_packs(image)}


def plan(source: Path, recipe: Dict[str, Any],
         pinned_catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve every edit against the operator's own image.  Writes nothing."""
    source = Path(source)
    _require(source.is_file(), "source image %s is not a file" % source)
    live = catalog_tool.build_catalog(str(source))
    roster = _resolve_roster(live, recipe["roster"])
    _require(not roster["compressed"],
             "outer %d: its ROST body is LZ-compressed, so a fixed-allocation "
             "edit would have to be recompressed back into the stored span. "
             "This lane refuses that: no retail ROST chunk is compressed."
             % roster["outer_index"])

    if pinned_catalog is not None:
        _require(pinned_catalog.get("schema") == catalog_tool.SCHEMA,
                 "catalogue schema is %r, expected %r"
                 % (pinned_catalog.get("schema"), catalog_tool.SCHEMA))
        pinned = [row for row in pinned_catalog.get("rosters", [])
                  if row["outer_index"] == roster["outer_index"]]
        _require(pinned, "outer %d is not in the pinned catalogue"
                 % roster["outer_index"])
        for field in ("body_sha256", "stored_size", "body_offset_in_pack",
                      "iso_path", "label", "version", "root"):
            _require(
                roster.get(field) == pinned[0].get(field),
                "outer %d: the image disagrees with the pinned catalogue on %s "
                "(%r vs %r). This is not the stock disc the catalogue was built "
                "from; refusing to write into an unverified target."
                % (roster["outer_index"], field, roster.get(field),
                   pinned[0].get(field)),
            )

    image = iso.open_image(str(source))
    packs = _pack_bases(image)
    pack = packs.get(roster["iso_path"])
    _require(pack is not None,
             "the image has no %s" % roster["iso_path"])
    body_base_in_pack = roster["body_offset_in_pack"]
    body_base_in_iso = roster["body_offset_in_iso"]
    stored = roster["stored_size"]

    # Player geometry is decoded from the *resolved* arena, never borrowed from
    # the catalogue's boot-roster listing: a historic roster has its own record
    # offsets, and reusing the boot roster's would aim every write at the wrong
    # bytes inside a structurally similar object.
    with open(str(source), "rb") as stream:
        stream.seek(body_base_in_iso)
        body = stream.read(stored)
    _require(len(body) == stored,
             "outer %d: short read of the %d-byte ROST arena"
             % (roster["outer_index"], stored))
    _require(_digest(body) == roster["body_sha256"],
             "outer %d: the ROST arena changed while it was planned"
             % roster["outer_index"])
    decoded = catalog_tool.decode_roster(body, "outer %d" % roster["outer_index"])
    arena_players = catalog_tool.decode_players(body, decoded["tables"])
    by_slot = {(row["pool"], row["index"]): row for row in arena_players}
    counts = {pool: sum(1 for row in arena_players if row["pool"] == pool)
              for pool in POOLS}

    planned = []  # type: List[Dict[str, Any]]
    with open(str(source), "rb") as stream:
        for edit in recipe["edits"]:
            player = by_slot.get((edit["pool"], edit["player"]))
            _require(
                player is not None,
                "outer %d has no %s record at index %d. It holds %d primary and "
                "%d secondary records; an out-of-range index is refused rather "
                "than guessed at."
                % (roster["outer_index"], edit["pool"], edit["player"],
                   counts["primary_players"], counts["secondary_players"]),
            )
            label = "%s %d" % (edit["pool"], edit["player"])

            packed = {name: edit["changes"][name] for name in PACKED_FIELDS
                      if name in edit["changes"]}
            if packed:
                offset = player["packed_word_offset"]
                _require(0 <= offset and offset + 4 <= stored,
                         "%s: its packed word at %d falls outside the %d-byte "
                         "arena" % (label, offset, stored))
                stream.seek(body_base_in_iso + offset)
                before = stream.read(4)
                _require(len(before) == 4, "%s: short read of the packed word" % label)
                _require(_digest(before) == player["packed_word_sha256"],
                         "%s: the packed word changed while it was planned" % label)
                word = struct.unpack("<I", before)[0]
                old_jersey = (word >> JERSEY_SHIFT) & 0x7F
                old_shield = (word >> FACE_SHIELD_SHIFT) & 0x3
                new_jersey = packed.get("jersey_number", old_jersey)
                new_shield = packed.get("face_shield", old_shield)
                new_word = (word & ~JERSEY_MASK) | (new_jersey << JERSEY_SHIFT)
                new_word = ((new_word & ~FACE_SHIELD_MASK)
                            | (new_shield << FACE_SHIELD_SHIFT))
                authored = ((JERSEY_MASK if "jersey_number" in packed else 0)
                            | (FACE_SHIELD_MASK if "face_shield" in packed else 0))
                _require((new_word & ~authored) == (word & ~authored),
                         "%s: the packed edit would change bits outside %s"
                         % (label, sorted(packed)))
                after = struct.pack("<I", new_word & 0xFFFFFFFF)
                _require(len(after) == 4,
                         "%s: a packed replacement must stay four bytes" % label)
                _require(after != before,
                         "%s already carries those packed values; refusing a "
                         "write that would declare a range and change nothing "
                         "in it" % label)
                planned.append({
                    "kind": "packed",
                    "pool": edit["pool"],
                    "player": edit["player"],
                    "fields": sorted(packed),
                    "offset_in_arena": offset,
                    "offset_in_pack": body_base_in_pack + offset,
                    "offset_in_iso": body_base_in_iso + offset,
                    "span_size": 4,
                    "before_sha256": _digest(before),
                    "after_sha256": _digest(after),
                    "replacement": after,
                    "note": edit.get("note"),
                })

            for field in NAME_FIELDS:
                if field not in edit["changes"]:
                    continue
                capacity = int(player[field + "_capacity"])
                offset = player[field + "_offset"]
                _require(offset is not None,
                         "%s: its %s pointer is null; there is no allocation to "
                         "write into" % (label, field))
                _require(capacity > TERMINATOR,
                         "%s: its %s allocation is a bare terminator (an empty "
                         "placeholder record); a zero-capacity slot is refused"
                         % (label, field))
                _require(int(player[field + "_references"]) == 1,
                         "%s: its %s string is referenced %d times in the arena, "
                         "so rewriting it would change another record too; "
                         "refusing an unsafe target"
                         % (label, field, player[field + "_references"]))
                encoded = edit["changes"][field].encode("utf-16le") + b"\x00\x00"
                _require(
                    len(encoded) <= capacity,
                    "%s: %s needs %d bytes but the slot holds %d. "
                    "Fixed-allocation edits may not grow the arena, because the "
                    "engine's pointers are byte offsets into it."
                    % (label, field, len(encoded), capacity),
                )
                _require(0 <= offset and offset + capacity <= stored,
                         "%s: its %s slot at %d+%d falls outside the %d-byte "
                         "arena" % (label, field, offset, capacity, stored))
                after = encoded.ljust(capacity, b"\x00")
                _require(len(after) == capacity,
                         "%s: a name replacement must fill exactly its slot" % label)
                stream.seek(body_base_in_iso + offset)
                before = stream.read(capacity)
                _require(len(before) == capacity,
                         "%s: short read of the %s slot" % (label, field))
                _require(after != before,
                         "%s already carries that %s; refusing a write that "
                         "would declare a range and change nothing in it"
                         % (label, field))
                planned.append({
                    "kind": "name",
                    "pool": edit["pool"],
                    "player": edit["player"],
                    "fields": [field],
                    "offset_in_arena": offset,
                    "offset_in_pack": body_base_in_pack + offset,
                    "offset_in_iso": body_base_in_iso + offset,
                    "span_size": capacity,
                    "before_sha256": _digest(before),
                    "after_sha256": _digest(after),
                    "replacement": after,
                    "note": edit.get("note"),
                })

    planned.sort(key=lambda row: row["offset_in_pack"])
    for left, right in zip(planned, planned[1:]):
        _require(
            left["offset_in_pack"] + left["span_size"] <= right["offset_in_pack"],
            "two edits overlap inside the arena at %d and %d"
            % (left["offset_in_pack"], right["offset_in_pack"]),
        )
    return {
        "source": str(source),
        "serial": SERIAL,
        "roster": {key: roster[key] for key in
                   ("outer_index", "outer_name_id", "label", "boot_roster",
                    "iso_path", "body_offset_in_pack", "body_offset_in_iso",
                    "stored_size", "body_sha256", "version", "root")},
        "edits": planned,
        "pack": pack,
        "catalog_summary": live["summary"],
    }


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _build_pack(source: Path, pack: Dict[str, int], items: Sequence[Dict[str, Any]],
                destination: Path) -> str:
    remaining = pack["size"]
    position = pack["offset"]
    with open(str(source), "rb") as reader, open(str(destination), "wb") as writer:
        while remaining:
            reader.seek(position)
            take = min(COPY_CHUNK, remaining)
            block = reader.read(take)
            _require(len(block) == take,
                     "short read while copying %d bytes of the pack extent" % take)
            writer.write(block)
            position += take
            remaining -= take
    written = destination.stat().st_size
    _require(written == pack["size"],
             "the staged pack is %d bytes but its extent holds %d; a fixed-"
             "allocation write may not change a file's size"
             % (written, pack["size"]))
    with open(str(destination), "r+b") as handle:
        for item in items:
            handle.seek(item["offset_in_pack"])
            handle.write(item["replacement"])
        handle.flush()
        os.fsync(handle.fileno())
    digest = hashlib.sha256()
    with open(str(destination), "rb") as handle:
        for block in iter(lambda: handle.read(COPY_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def apply(source, destination, recipe: Dict[str, Any], *,
          pinned_catalog: Optional[Dict[str, Any]] = None,
          work_dir=None) -> Dict[str, Any]:
    """Produce a new image carrying the recipe's roster edits."""
    import tempfile

    source = Path(source)
    destination = Path(destination)
    _require(not destination.exists(),
             "destination %s already exists; refusing to overwrite an image"
             % destination)
    prepared = plan(source, recipe, pinned_catalog)

    holder = tempfile.TemporaryDirectory(
        dir=str(work_dir) if work_dir else str(destination.parent))
    try:
        staging = Path(holder.name) / "pack.bin"
        staged_sha = _build_pack(source, prepared["pack"], prepared["edits"], staging)
        report = iso_writer.replace_files(
            source, destination, {prepared["roster"]["iso_path"]: staging})
    finally:
        holder.cleanup()

    return {
        "schema": SCHEMA,
        "serial": SERIAL,
        "source": str(source),
        "destination": str(destination),
        "files_replaced": [prepared["roster"]["iso_path"]],
        "roster": prepared["roster"],
        "edits": [{key: value for key, value in item.items() if key != "replacement"}
                  for item in prepared["edits"]],
        "declared_ranges": [
            {"start": item["offset_in_iso"], "length": item["span_size"],
             "reason": "roster_%s:%s:%d" % (item["kind"], item["pool"],
                                            item["player"])}
            for item in prepared["edits"]
        ],
        "staged_pack_sha256": {prepared["roster"]["iso_path"]: staged_sha},
        "iso_write_report": iso_writer.report_to_json(report),
        "catalog_summary": prepared["catalog_summary"],
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
    """Prove one edit lands and the bad ones are refused.  Needs no game data."""
    import tempfile

    failures = []  # type: List[str]

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    def refuses(name: str, call, needle: str) -> None:
        try:
            call()
        except RosterPatchError as exc:
            if needle.lower() not in str(exc).lower():
                failures.append("%s: refused with %r, expected %r"
                                % (name, str(exc), needle))
            return
        failures.append("%s was not refused" % name)

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work)
        source = room / "stock.iso"
        source.write_bytes(catalog_tool.build_synthetic_iso())
        pinned = catalog_tool.build_catalog(str(source))

        good = parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
            {"pool": "primary_players", "player": 0,
             "first_name": "Dwane", "jersey_number": 7},
            {"pool": "primary_players", "player": 1, "face_shield": 2},
        ]})
        destination = room / "edited.iso"
        receipt = apply(source, destination, good, pinned_catalog=pinned)
        check(receipt["schema"] == SCHEMA, "receipt must be stamped")
        check(len(receipt["edits"]) == 3,
              "a name edit and two packed edits must be declared, saw %d"
              % len(receipt["edits"]))
        check(receipt["roster"]["boot_roster"], "the boot roster must be the target")
        check(destination.stat().st_size == source.stat().st_size,
              "the image must keep its exact byte length")

        before = source.read_bytes()
        after = destination.read_bytes()
        player = catalog_tool.find_player(pinned, 0)
        boot = catalog_tool.boot_roster(pinned)
        word_at = boot["body_offset_in_iso"] + player["packed_word_offset"]
        word_before = struct.unpack_from("<I", before, word_at)[0]
        word_after = struct.unpack_from("<I", after, word_at)[0]
        check((word_after >> JERSEY_SHIFT) & 0x7F == 7, "the jersey must change")
        check((word_after & ~JERSEY_MASK) == (word_before & ~JERSEY_MASK),
              "no bit outside the jersey mask may move")
        name_at = boot["body_offset_in_iso"] + player["first_name_offset"]
        capacity = player["first_name_capacity"]
        check(after[name_at:name_at + capacity]
              == "Dwane".encode("utf-16le") + b"\x00" * (capacity - 10),
              "the name slot must hold the new name, zero filled")

        refuses("an existing destination",
                lambda: apply(source, destination, good, pinned_catalog=pinned),
                "already exists")
        refuses("an out-of-range player index",
                lambda: apply(source, room / "a.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"player": 99, "jersey_number": 1}]})),
                "out-of-range index")
        # A historic roster has its own record offsets and its own population.
        # Index 2 exists in the boot roster and not here, so borrowing the boot
        # roster's geometry would silently accept it and write to the wrong
        # bytes of a structurally similar object.
        refuses("an index that exists only in the boot roster",
                lambda: apply(source, room / "g.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA,
                                            "roster": "outer:1",
                                            "edits": [{"player": 2,
                                                       "jersey_number": 1}]})),
                "outer 1 has no primary_players record at index 2")
        check(not (room / "g.iso").exists(),
              "a refusal must not leave g.iso behind")
        historic = room / "historic.iso"
        receipt = apply(source, historic,
                        parse_recipe({"schema": RECIPE_SCHEMA,
                                      "roster": "outer:1",
                                      "edits": [{"player": 0,
                                                 "jersey_number": 21}]}))
        check(receipt["roster"]["outer_index"] == 1
              and receipt["roster"]["label"] == "historic",
              "a historic roster must be writable in its own right")
        check(receipt["edits"][0]["offset_in_iso"]
              >= receipt["roster"]["body_offset_in_iso"],
              "a historic edit must land inside the historic arena")
        refuses("an over-length name",
                lambda: apply(source, room / "b.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"player": 0,
                                   "first_name": "Bartholomewcubbins"}]})),
                "may not grow the arena")
        refuses("a zero-capacity placeholder slot",
                lambda: apply(source, room / "c.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"pool": "secondary_players", "player": 0,
                                   "first_name": "Al"}]})),
                "zero-capacity slot is refused")
        refuses("a compressed ROST that cannot be refit",
                lambda: apply(source, room / "d.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA,
                                            "roster": "outer:2",
                                            "edits": [{"player": 0,
                                                       "jersey_number": 1}]})),
                "recompressed back into the stored span")
        refuses("a no-op edit",
                lambda: apply(source, room / "e.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"player": 0, "jersey_number": 28}]})),
                "already carries those packed values")
        forged = json.loads(json.dumps(pinned))
        for row in forged["rosters"]:
            if row["boot_roster"]:
                row["body_sha256"] = "0" * 64
        refuses("a catalogue that disagrees with the image",
                lambda: apply(source, room / "f.iso",
                              parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                                  {"player": 0, "jersey_number": 3}]}),
                              pinned_catalog=forged),
                "not the stock disc")
        for name in "abcdef":
            check(not (room / ("%s.iso" % name)).exists(),
                  "a refusal must not leave %s.iso behind" % name)

        refuses("the reserved face-shield value",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"player": 0, "face_shield": 3}]}),
                "reserved value 3 is refused")
        refuses("an out-of-range jersey number",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"player": 0, "jersey_number": 100}]}),
                "must be an integer 0..99")
        refuses("a recipe with the wrong schema",
                lambda: parse_recipe({"schema": "nope", "edits": []}),
                "recipe schema")
        refuses("a duplicate player",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"player": 0, "jersey_number": 1},
                    {"player": 0, "face_shield": 1}]}),
                "appears twice")
        refuses("an unknown edit key",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"player": 0, "speed": 99}]}),
                "unknown keys")
        refuses("an unknown pool",
                lambda: parse_recipe({"schema": RECIPE_SCHEMA, "edits": [
                    {"pool": "coaches", "player": 0, "jersey_number": 1}]}),
                "names pool")

    for failure in failures:
        print("FAIL: %s" % failure, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_DISC_ROSTER_PATCH_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="stock SLUS-20919 ISO (read-only)")
    parser.add_argument("--destination", type=Path, help="new ISO to create")
    parser.add_argument("--recipe", type=Path, help="roster recipe JSON")
    parser.add_argument("--catalog", type=Path, help="pinned target catalogue JSON")
    parser.add_argument("--receipt", type=Path, help="write the receipt here")
    parser.add_argument("--work-dir", type=Path,
                        help="directory for the staged pack file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--tmp", help="directory for self-test scratch files")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.tmp)
    if not args.source or not args.recipe:
        parser.error("--source and --recipe are required unless --selftest is given")
    if not args.dry_run and not args.destination:
        parser.error("--destination is required unless --dry-run is given")

    try:
        recipe = load_recipe(args.recipe)
        pinned = None
        if args.catalog:
            pinned = json.loads(args.catalog.read_text(encoding="utf-8"))
        if args.dry_run:
            prepared = plan(args.source, recipe, pinned)
            document = {
                "schema": SCHEMA + "-dry-run",
                "source": prepared["source"],
                "roster": prepared["roster"],
                "files_replaced": [prepared["roster"]["iso_path"]],
                "edits": [{key: value for key, value in item.items()
                           if key != "replacement"}
                          for item in prepared["edits"]],
            }
        else:
            document = apply(args.source, args.destination, recipe,
                             pinned_catalog=pinned, work_dir=args.work_dir)
    except (RosterPatchError, catalog_tool.RosterCatalogError,
            archive_tool.CatalogError, iso_writer.IsoWriteError, iso.FormatError,
            OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.receipt:
        write_json(args.receipt, document)
    print("NFL2K5_PS2_DISC_ROSTER_PATCH_OK outer=%d edits=%d%s"
          % (document["roster"]["outer_index"], len(document["edits"]),
             " (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
