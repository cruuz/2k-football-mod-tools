"""The lane shapes both Midway Blitz discs use over a stored ZIP and its index.

NFL Blitz 2002 (``SLUS-20051``) and NFL Blitz 2003 (``SLUS-20474``) keep the
whole game in one ZIP whose every member is stored, with Midway's pre-built
``.ZIH`` index beside it.  The **formats** are
:mod:`mod_editor.games._formats.blitz_zip` (the pair, both index shapes and the
bounded three-place writer) and :mod:`mod_editor.games._formats.rw_txd` (the
RenderWare texture dictionaries inside it).  This module is the layer above:
how a member edit becomes a plan, a build and an independent verdict, and the
four lane classes the two games instantiate.

**Why it is here and not in the first module that needed it.**  The 2003 module
shipped as the 2002 module with a recorded substitution list applied, because a
game package may not import a sibling
(``mod_editor.games.contract.ALLOWED_CORE_IMPORTS``) and this shared layer did
not exist yet.  Two copies of a writer are two places for it to be wrong; both
games are now thin wirings over this file, exactly as Madden NFL 09 and NCAA
Football 09 are wirings over :mod:`._lanes.terf_art`.

Everything game-specific is data:

* a **disc-access module** -- the game's own ``containers``, which knows the
  serial, the archive and index paths, which member feeds which page, and how
  to build a synthetic disc CI can prove a lane on;
* the lane's **schema string**, which stays per game so a recipe written for
  one disc is refused by the other;
* a row's **member selection** -- a suffix, an exact name, or "every dictionary
  whose name is not a team's".

Five things live here:

============================  =====================================================
name                          what it is
============================  =====================================================
:func:`plan_ranges`,          the build half of the old per-game ``zip_lane``: the
:func:`build_replacements`    ranges a same-length member replacement declares, and
                              the new image the shared ISO9660 writer produces
:func:`verify_replacements`   the verify half, importing none of the patcher
:class:`TextLineLane`         three rows: crowd tables, ``field.tab``, trivia banks
:class:`RosterNameLane`       one row: either name field of a ``roster.rst`` record
:class:`TextureDictionaryLane` three rows: the inventory and two PNG export lanes
:class:`ContainerInventoryLane` one row: camera paths, ``WIFF`` heads, clumps
============================  =====================================================

**The three-place rule, and its two-place collapse, are decided by the file.**
A stored member's CRC-32 lives in the local file header, the central directory
and -- where the index carries a CRC column -- the ``.ZIH`` index.
``blitz_zip.plan_member_replacement`` returns every range or refuses; nothing
here writes one without the others, and nothing here asks which disc it is
looking at.  ``docs/product/MIDWAY_ZIP_FORMAT.md`` §6 is the measurement.

**Nothing here has been booted.**  Every claim is offline: the user's own image,
a new destination image, an independent verifier that re-reads it, and a
conformance harness that proves the whole path on a synthetic disc.

Standard library only; importable without Qt.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import zlib

from mod_editor.games._formats import blitz_zip, ea_shps, rw_txd
from mod_editor.games.contract import (
    Artifact, Catalogue, DeclaredRange, Edit, EncodedArt, Field, Plan, Receipt, Refusal,
    Target, Verdict, require,
)

__all__ = [
    "NOT_BOOTED", "NO_TEXTURE_WRITER", "INVENTORY_ONLY", "CONTAINER_INVENTORY_REFUSAL",
    "sha256", "check_destination", "plan_ranges", "build_replacements",
    "verify_replacements", "refuse_read_only",
    "TextLineLane", "RosterNameLane", "TextureDictionaryLane", "ContainerInventoryLane",
    "read_camera", "read_wiff", "walk_clump",
    "text_lane_main", "roster_lane_main", "texture_lane_main", "camera_lane_main",
]

#: The sentence every writer here carries, because it is true of every one.
NOT_BOOTED = ("No NFL Blitz image rebuilt by this module has been booted in an emulator or on "
              "hardware; the game's acceptance of a rewritten member is not claimed anywhere.")

#: Why an art row exports and never imports.  ``rw_txd._swizzle8`` is the exact
#: inverse of the decode, so a same-length texture writer is *within* these
#: readers -- and it is unproved, so it is not offered.
NO_TEXTURE_WRITER = ("This lane exports a raster and writes nothing: putting one back means "
                     "re-swizzling it into the GS memory image and rewriting the member at its "
                     "own length, which this module has not proved, so no import is offered.")

INVENTORY_ONLY = ("This lane counts every dictionary and raster on the disc and writes "
                  "nothing; export a raster on the page that owns its dictionary, Uniforms "
                  "& Equipment for a team logo and Menus & UI for everything else.")

CONTAINER_INVENTORY_REFUSAL = (
    "This lane lists every camera path, WIFF container and RenderWare clump on the disc "
    "and writes nothing: a path's 32-byte record is four-byte fields whose meanings are "
    "not measured, so there is nothing here it would be honest to offer an editor for.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _writer() -> Any:
    import ps2_iso9660_writer

    return ps2_iso9660_writer


def _verifier() -> Any:
    import ps2_iso9660_verify

    return ps2_iso9660_verify


def check_destination(source: Path, destination: Path) -> None:
    require(Path(destination).resolve() != Path(source).resolve(),
            f"{destination} is the source image; a build always writes a NEW image.")
    require(not os.path.lexists(destination),
            f"destination {destination} already exists; refusing to overwrite it.")


def refuse_read_only(sentence: str) -> None:
    raise Refusal(sentence)


# --------------------------------------------------------------------------
# The build half: whole members, same length, three CRC sites, one new image
# --------------------------------------------------------------------------

def _rewritten_pair(disc: Any, members: Mapping[str, bytes]
                    ) -> Tuple[bytes, bytes, List[Dict[str, Any]]]:
    """The two files as they will be written, and one row per member changed."""

    archive = disc.archive()
    index = disc.index()
    archive_blob = bytearray(disc.archive_bytes())
    index_blob = bytearray(disc.index_bytes())
    rows: List[Dict[str, Any]] = []
    for name in sorted(members):
        payload = members[name]
        plan = blitz_zip.plan_member_replacement(archive, index, name, payload)
        blitz_zip.apply_member_replacement(archive_blob, index_blob, plan)
        member = archive.member(name)
        rows.append({
            "member": name,
            "bytes": plan.size,
            "data_offset": member.data_offset,
            "crc32": "%08x" % plan.crc32,
            "previous_crc32": "%08x" % plan.previous_crc32,
            "sha256": sha256(payload),
            "archive_ranges": len(plan.zip_ranges),
            "index_ranges": len(plan.index_ranges),
        })
    return bytes(archive_blob), bytes(index_blob), rows


def plan_ranges(disc: Any, members: Mapping[str, bytes]
                ) -> Tuple[Tuple[DeclaredRange, ...], List[Dict[str, Any]]]:
    """What a build would declare, decided without writing anything."""

    archive_blob, index_blob, rows = _rewritten_pair(disc, members)
    replacements = {disc.archive_path: archive_blob}
    if any(row["index_ranges"] for row in rows):
        replacements[disc.index_path] = index_blob
    report = _writer().plan_report(disc.path, dict(replacements))
    ranges = tuple(DeclaredRange(item.start, item.length, item.reason)
                   for item in report["declared_ranges"])
    return ranges, rows


def build_replacements(disc: Any, destination: Path, members: Mapping[str, bytes]
                       ) -> Tuple[Dict[str, Any], Tuple[DeclaredRange, ...], List[Dict[str, Any]]]:
    """Write the new image; return the writer's JSON report, its ranges and the rows."""

    archive_blob, index_blob, rows = _rewritten_pair(disc, members)
    replacements: Dict[str, bytes] = {disc.archive_path: archive_blob}
    if any(row["index_ranges"] for row in rows):
        replacements[disc.index_path] = index_blob
    tool = _writer()
    report = tool.replace_files(disc.path, Path(destination), dict(replacements))
    json_report = tool.report_to_json(report)
    ranges = tuple(DeclaredRange(item["start"], item["length"], item["reason"])
                   for item in json_report["declared_ranges"])
    return json_report, ranges, rows


def _member_digest(disc: Any, member: Any, chunk: int = 1 << 22) -> str:
    """SHA-256 of one member's stored bytes, read in chunks so any size is comparable."""

    where = disc.pair()
    digest = hashlib.sha256()
    start, left = where.archive_offset + member.data_offset, member.size
    while left > 0:
        block = disc.read(start, min(chunk, left))
        if not block:
            break
        digest.update(block)
        start += len(block)
        left -= len(block)
    return digest.hexdigest()


def verify_replacements(discs: Any, source: Path, destination: Path,
                        document: Mapping[str, Any]) -> Dict[str, Any]:
    """The independent verdict.  Imports none of the code that wrote the image."""

    rows = list(document.get("members") or ())
    changed = {str(row["member"]): row for row in rows}
    failures: List[str] = []
    checked = identical = 0

    source_size = Path(source).stat().st_size
    destination_size = Path(destination).stat().st_size
    if source_size != destination_size:
        failures.append(f"the destination is {destination_size} bytes and the source is "
                        f"{source_size}; a fixed-allocation build never changes the length")

    with discs.Disc(Path(source)) as before, discs.Disc(Path(destination)) as after:
        old_archive, new_archive = before.archive(), after.archive()
        old_index, new_index = before.index(), after.index()
        old_names = [member.name for member in old_archive.members]
        new_names = [member.name for member in new_archive.members]
        if old_names != new_names:
            failures.append("the destination's member list is not the source's")
        cross = blitz_zip.cross_check(new_index, new_archive)
        for key in ("names_match_as_sets",):
            if not cross[key]:
                failures.append(f"in the destination, the index and the archive disagree: {key}")
        for key, wanted in (("sizes_agree", len(new_archive.members)),
                            ("data_offsets_agree", len(new_archive.members))):
            if cross[key] != wanted:
                failures.append(f"in the destination, {cross[key]} of {wanted} members "
                                f"{key.replace('_', ' ')}")
        if new_index.has_crc_column and cross["crc_column_agrees"] != len(new_archive.members):
            failures.append(f"in the destination, {cross['crc_column_agrees']} of "
                            f"{len(new_archive.members)} index CRC-32 values match the archive's")

        for member in new_archive.members:
            old = old_archive.by_name().get(member.name)
            if old is None:
                continue
            if member.data_offset != old.data_offset or member.size != old.size:
                failures.append(f"{member.name} moved or changed length")
                continue
            checked += 1
            row = changed.get(member.name)
            if row is None:
                # Every member the receipt did not name must be byte-identical, including the
                # 137 MB sound bank: it is compared by streaming digest rather than skipped,
                # because a member too large to hold in memory is exactly where an undeclared
                # change would hide.
                if _member_digest(after, member) == _member_digest(before, member):
                    identical += 1
                else:
                    failures.append(f"{member.name} was not named by the receipt and its bytes "
                                    f"changed")
                continue
            payload = after.archive().member_bytes(member.name)
            if sha256(payload) != row["sha256"]:
                failures.append(f"{member.name} does not carry the bytes the receipt names")
            recomputed = zlib.crc32(payload) & 0xFFFFFFFF
            if "%08x" % recomputed != row["crc32"]:
                failures.append(f"{member.name}'s bytes do not recompute to the CRC-32 the "
                                f"receipt names")
            if member.crc32 != recomputed:
                failures.append(f"{member.name}'s central-directory CRC-32 is not its bytes'")
            entry = new_index.by_name().get(member.name)
            if entry is not None and entry.crc32 is not None and entry.crc32 != recomputed:
                failures.append(f"{member.name}'s index CRC-32 is not its bytes'")

    image_report = document.get("iso_report")
    if not image_report:
        failures.append("the receipt carries no write report")
    else:
        tool = _verifier()
        try:
            tool.verify_replacement(Path(source), Path(destination), dict(image_report))
        except tool.IsoVerifyError as exc:
            failures.append(f"at the image level: {exc}")

    return {
        "passed": not failures,
        "members_checked": checked,
        "members_byte_identical": identical,
        "members_replaced": len(changed),
        "failures": failures,
        "not_booted": NOT_BOOTED,
    }


# --------------------------------------------------------------------------
# The text members, edited one line slot at a time
# --------------------------------------------------------------------------

class TextLineLane:
    """One page's text members, each line a fixed-span slot.

    A line owns its own bytes and nothing else.  A replacement must fit that
    span and is padded to it -- NUL in a ``.trv`` record, spaces in a CRLF line
    -- so the member's length never changes, which is what lets it go back into
    a stored ZIP where it lies.  Its CRC-32 is then rewritten in every place the
    disc keeps it (:func:`build_replacements`).
    """

    classification = "offline-writer-proved"
    fixed_allocation = True
    read_only = False

    def __init__(self, discs: Any, schema: str, lane_id: str, surface: str, page: str,
                 title: str, *, suffix: str = "", exact: Sequence[str] = (), what: str = "",
                 validator: str = "") -> None:
        self.discs = discs
        self.recipe_schema = schema
        self.lane_id = lane_id
        self.capability_id = f"{discs.GAME_ID.replace('_', '')}.{lane_id}"
        self.surface = surface
        self.page = page
        self.title = title
        self.suffix = suffix
        self.exact = tuple(exact)
        self.what = what
        self.validators = (f"tools/validate_{discs.GAME_ID}_{validator}.sh",
                           f"tools/validate_{discs.GAME_ID}_{validator}.bat")

    # -- catalogue ----------------------------------------------------------

    def members(self, disc: Any) -> Tuple[Any, ...]:
        return disc.members_named(suffix=self.suffix, exact=self.exact)

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        discs = self.discs
        schema = self.recipe_schema
        targets: List[Target] = []
        rows: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        total_slots = 0
        with discs.Disc(Path(source)) as disc:
            found = self.members(disc)
            for number, member in enumerate(found):
                if progress is not None:
                    progress(f"{member.name} ({number + 1} of {len(found)})…")
                try:
                    payload = disc.member_bytes(member.name)
                    slots = discs.read_line_slots(member.name, payload)
                except discs.DiscError as exc:
                    refusals.append({"where": member.name, "sentence": str(exc)})
                    continue
                total_slots += len(slots)
                rows.append({"member": member.name, "bytes": member.size,
                             "kind": discs.text_kind(member.name), "lines": len(slots),
                             "crc32": "%08x" % member.crc32,
                             "sha256": sha256(payload)})
                for slot in slots:
                    if len(targets) >= discs.MAX_TARGETS:
                        break
                    targets.append(Target(
                        key=f"{member.name}#{slot.number}",
                        label=f"{member.name} line {slot.number}",
                        detail=f"{slot.span} bytes at +{slot.offset} · {slot.kind}",
                        budget=slot.budget,
                        searchable=f"{member.name} {slot.number} {slot.text}",
                        raw={"member": member.name, "line": slot.number, "offset": slot.offset,
                             "span": slot.span, "kind": slot.kind},
                        fields=(Field("text", "text", "Line",
                                      f"Latin-1, at most {slot.span} characters; the rest of "
                                      f"the slot is padded."),)))
        document = {"schema": schema, "source": str(source), "lane": self.lane_id,
                    "what": self.what, "members": len(rows), "lines": total_slots,
                    "targets_listed": len(targets), "rows": rows, "refusals": refusals,
                    "not_booted": NOT_BOOTED}
        return Catalogue(schema, self.lane_id, str(source), tuple(targets), document)

    # -- editing ------------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        text = values.get("text")
        if text is None:
            return None
        if not isinstance(text, str):
            return "A line is text; give it a string."
        span = int(target.raw["span"])
        try:
            raw = text.encode("latin-1")
        except UnicodeEncodeError:
            return ("This disc stores its text as Latin-1 and that value carries a character "
                    "outside it; use plain letters, digits and punctuation.")
        if len(raw) > span:
            return (f"This line owns {span} bytes and that value needs {len(raw)}; shorten it "
                    f"to {span} characters or fewer.")
        if "\r" in text or "\n" in text or "\x00" in text:
            return ("A line cannot carry a line break or a NUL; the slot's own padding ends it.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema, "lane": self.lane_id,
                "edits": [{"target": edit.target_key, "text": str(edit.values.get("text", ""))}
                          for edit in edits]}

    def _resolve(self, disc: Any, recipe: Mapping[str, Any],
                 catalogue: Catalogue) -> Dict[str, bytes]:
        discs = self.discs
        edits = list(recipe.get("edits") or ())
        if not edits:
            raise Refusal("This recipe carries no edits; stage a line change before building.")
        payloads: Dict[str, bytes] = {}
        for item in edits:
            target = catalogue.target(str(item.get("target", "")))
            member = str(target.raw["member"])
            if member not in payloads:
                payloads[member] = disc.member_bytes(member)
            slots = discs.read_line_slots(member, payloads[member])
            number = int(target.raw["line"])
            if number >= len(slots):
                raise Refusal(f"{member} has {len(slots)} lines and the recipe names line "
                              f"{number}; rebuild the catalogue against this image.")
            slot = slots[number]
            if slot.offset != int(target.raw["offset"]) or slot.span != int(target.raw["span"]):
                raise Refusal(f"{member} line {number} is not where the catalogue put it; "
                              f"rebuild the catalogue against this image.")
            problem = self.check_edit(target, {"text": item.get("text", "")})
            if problem:
                raise Refusal(problem)
            payloads[member] = discs.write_line_slot(payloads[member], slot,
                                                     str(item.get("text", "")))
        return payloads

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        with self.discs.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            ranges, rows = plan_ranges(disc, payloads)
        return Plan(self.lane_id, tuple(str(item.get("target")) for item in recipe.get("edits", ())),
                    ranges, {"schema": self.recipe_schema, "lane": self.lane_id, "members": rows})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        check_destination(Path(source), Path(destination))
        with self.discs.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            iso_report, ranges, rows = build_replacements(disc, Path(destination), payloads)
        document = {"schema": self.recipe_schema, "lane": self.lane_id, "members": rows,
                    "iso_report": iso_report, "not_booted": NOT_BOOTED}
        return Receipt(self.recipe_schema, self.lane_id, str(source), str(destination), ranges,
                       document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        outcome = verify_replacements(self.discs, Path(source), Path(destination),
                                      receipt.document)
        summary = ("%d member(s) replaced, %d checked, %d byte-identical; the index and the "
                   "archive agree" % (outcome["members_replaced"], outcome["members_checked"],
                                      outcome["members_byte_identical"]))
        if not outcome["passed"]:
            summary = "; ".join(outcome["failures"][:3])
        return Verdict(bool(outcome["passed"]), summary, outcome)

    # -- CI -----------------------------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{self.discs.GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(self.discs.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if int(target.raw["span"]) >= 4:
                return (Edit(target.key, {"text": "FIX1"}),)
        raise Refusal("The synthetic source carries no line slot of four bytes or more.")


# --------------------------------------------------------------------------
# roster.rst: two name fields per record, and a census of the numbers
# --------------------------------------------------------------------------

class RosterNameLane:
    """The player names in ``roster.rst``, each a fixed 32-byte field.

    A name field is NUL-terminated ASCII padded with ``0xCD`` -- uninitialised
    MSVC heap fill, which is what tells you it is a fixed struct member and not
    a string table [M].  A replacement fits or is refused, so the member's
    length never changes.  The 36 numeric bytes are listed and never written.
    """

    surface = "players_rosters"
    page = "rosters"
    title = "Player names in roster.rst"
    classification = "offline-writer-proved"
    fixed_allocation = True
    read_only = False

    def __init__(self, discs: Any, schema: str, lane_id: str = "rosters.player_names") -> None:
        self.discs = discs
        self.recipe_schema = schema
        self.lane_id = lane_id
        self.capability_id = f"{discs.GAME_ID.replace('_', '')}.{lane_id}"
        self.validators = (f"tools/validate_{discs.GAME_ID}_roster.sh",
                           f"tools/validate_{discs.GAME_ID}_roster.bat")
        #: The numeric columns this lane publishes a census of and never writes.
        self.column_start = 64
        self.column_end = discs.ROSTER_RECORD_BYTES

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        discs = self.discs
        schema = self.recipe_schema
        targets: List[Target] = []
        with discs.Disc(Path(source)) as disc:
            if progress is not None:
                progress(f"{discs.ROSTER_MEMBER}…")
            member = disc.archive().member(discs.ROSTER_MEMBER)
            payload = disc.member_bytes(discs.ROSTER_MEMBER)
            players = discs.read_roster(payload, discs.ROSTER_MEMBER)
            columns: Dict[str, Dict[str, int]] = {}
            for column in range(self.column_start, self.column_end):
                values = {player.offset: payload[player.offset + column] for player in players}
                seen = sorted(set(values.values()))
                columns[str(column)] = {"distinct": len(seen), "minimum": seen[0],
                                        "maximum": seen[-1]}
            team_byte_agrees = sum(1 for player in players if player.team_byte == player.block)
            for player in players:
                if len(targets) >= discs.MAX_TARGETS:
                    break
                targets.append(Target(
                    key=f"{player.block}:{player.slot}",
                    label=f"{player.first} {player.last}",
                    detail=f"block {player.block} slot {player.slot} · +{player.offset}",
                    budget=f"two {discs.ROSTER_NAME_BYTES}-byte fields, each "
                           f"{discs.ROSTER_NAME_BYTES - 1} characters and a terminator",
                    searchable=f"{player.first} {player.last} block {player.block}",
                    raw={"block": player.block, "slot": player.slot, "offset": player.offset,
                         "first": player.first, "last": player.last,
                         "team_byte": player.team_byte},
                    fields=(Field("first", "text", "First name",
                                  f"Latin-1, at most {discs.ROSTER_NAME_BYTES - 1} "
                                  f"characters."),
                            Field("last", "text", "Last name",
                                  f"Latin-1, at most {discs.ROSTER_NAME_BYTES - 1} "
                                  f"characters."))))
            crowd = len(disc.members_named(suffix=discs.CROWD_SUFFIX))
            logos = len(disc.members_named(suffix=discs.TEAM_TEXTURE_SUFFIXES[0]))
        blocks = len(players) // discs.ROSTER_RECORDS_PER_BLOCK
        document = {
            "schema": schema, "source": str(source), "member": discs.ROSTER_MEMBER,
            "bytes": member.size, "crc32": "%08x" % member.crc32,
            "sha256": sha256(payload),
            "block_bytes": discs.ROSTER_BLOCK_BYTES, "blocks": blocks,
            "records_per_block": discs.ROSTER_RECORDS_PER_BLOCK,
            "records": len(players),
            "records_whose_team_byte_equals_their_block": team_byte_agrees,
            "team_crowd_tables": crowd, "team_logo_dictionaries": logos,
            "blocks_minus_team_tables": blocks - crowd,
            "numeric_column_census": columns, "targets_listed": len(targets),
            "not_booted": NOT_BOOTED,
        }
        return Catalogue(schema, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        discs = self.discs
        for key in ("first", "last"):
            text = values.get(key)
            if text is None:
                continue
            if not isinstance(text, str):
                return f"A {key} name is text; give it a string."
            if not text.strip():
                return f"A {key} name cannot be empty; the field is NUL-terminated."
            try:
                raw = text.encode("latin-1")
            except UnicodeEncodeError:
                return ("This disc stores its names as Latin-1 and that value carries a "
                        "character outside it; use plain letters, digits and punctuation.")
            if any(byte < 0x20 or byte > 0x7E for byte in raw):
                return f"A {key} name holds printable ASCII only; that value does not."
            if len(raw) + 1 > discs.ROSTER_NAME_BYTES:
                return (f"A name field holds {discs.ROSTER_NAME_BYTES} bytes including its "
                        f"terminator and that value needs {len(raw) + 1}; shorten it to "
                        f"{discs.ROSTER_NAME_BYTES - 1} characters or fewer.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"target": edit.target_key}
            for key in ("first", "last"):
                if key in edit.values:
                    row[key] = str(edit.values[key])
            rows.append(row)
        return {"schema": self.recipe_schema, "lane": self.lane_id, "edits": rows}

    def _resolve(self, disc: Any, recipe: Mapping[str, Any],
                 catalogue: Catalogue) -> Dict[str, bytes]:
        discs = self.discs
        edits = list(recipe.get("edits") or ())
        if not edits:
            raise Refusal("This recipe carries no edits; stage a name change before building.")
        payload = disc.member_bytes(discs.ROSTER_MEMBER)
        players = {f"{player.block}:{player.slot}": player
                   for player in discs.read_roster(payload, discs.ROSTER_MEMBER)}
        for item in edits:
            key = str(item.get("target", ""))
            target = catalogue.target(key)
            player = players.get(key)
            if player is None:
                raise Refusal(f"{key!r} is not a record in this image's roster; rebuild the "
                              f"catalogue against it.")
            if player.offset != int(target.raw["offset"]):
                raise Refusal(f"record {key} is not where the catalogue put it; rebuild the "
                              f"catalogue against this image.")
            problem = self.check_edit(target, item)
            if problem:
                raise Refusal(problem)
            for which in ("first", "last"):
                if which in item:
                    payload = discs.write_roster_name(payload, player, which, str(item[which]))
        return {discs.ROSTER_MEMBER: payload}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        with self.discs.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            ranges, rows = plan_ranges(disc, payloads)
        return Plan(self.lane_id,
                    tuple(str(item.get("target")) for item in recipe.get("edits", ())),
                    ranges, {"schema": self.recipe_schema, "lane": self.lane_id,
                             "members": rows})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        check_destination(Path(source), Path(destination))
        with self.discs.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            iso_report, ranges, rows = build_replacements(disc, Path(destination), payloads)
        document = {"schema": self.recipe_schema, "lane": self.lane_id, "members": rows,
                    "iso_report": iso_report, "not_booted": NOT_BOOTED}
        return Receipt(self.recipe_schema, self.lane_id, str(source), str(destination), ranges,
                       document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        discs = self.discs
        outcome = verify_replacements(discs, Path(source), Path(destination), receipt.document)
        failures = list(outcome["failures"])
        if outcome["passed"]:
            with discs.Disc(Path(destination)) as after:
                try:
                    players = discs.read_roster(after.member_bytes(discs.ROSTER_MEMBER),
                                                discs.ROSTER_MEMBER)
                except discs.DiscError as exc:
                    failures.append(f"the rewritten roster no longer parses: {exc}")
                else:
                    bad = [p for p in players if p.team_byte != p.block]
                    if bad:
                        failures.append(f"{len(bad)} rewritten record(s) no longer carry their "
                                        f"block's ordinal at byte +{discs.ROSTER_TEAM_BYTE}")
        outcome = dict(outcome)
        outcome["failures"] = failures
        outcome["passed"] = not failures
        summary = ("roster.rst replaced, %d member(s) checked, %d byte-identical; the roster "
                   "still parses and every record keeps its block ordinal"
                   % (outcome["members_checked"], outcome["members_byte_identical"]))
        if not outcome["passed"]:
            summary = "; ".join(failures[:3])
        return Verdict(bool(outcome["passed"]), summary, outcome)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{self.discs.GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(self.discs.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        if not catalogue.targets:
            raise Refusal("The synthetic source carries no roster records.")
        return (Edit(catalogue.targets[0].key, {"first": "Fixture", "last": "Namefield"}),)


# --------------------------------------------------------------------------
# The RenderWare texture dictionaries: one inventory and two export rows
# --------------------------------------------------------------------------

def _rows_for(discs: Any, disc: Any, members: Sequence[Any], *, decode: bool,
              progress: Optional[Callable[[str], None]] = None,
              targets: Optional[List[Target]] = None) -> Dict[str, Any]:
    """Walk a selection of dictionaries; count, and optionally build art targets."""

    totals = {"dictionaries": 0, "rasters": 0, "decodable": 0, "identities": 0,
              "listed_not_drawn": 0}
    depths: Dict[str, int] = {}
    dimensions: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    refusals: List[Dict[str, str]] = []
    for number, member in enumerate(members):
        if progress is not None:
            progress(f"{member.name} ({number + 1} of {len(members)})…")
        try:
            dictionary = disc.texture_dictionary(member.name)
        except discs.DiscError as exc:
            refusals.append({"where": member.name, "sentence": str(exc)})
            continue
        totals["dictionaries"] += 1
        row = {"member": member.name, "bytes": member.size, "crc32": "%08x" % member.crc32,
               "library_version": "0x%08x" % dictionary.library_version,
               "declared_textures": dictionary.declared_textures,
               "rasters": len(dictionary.rasters),
               "section_accounts_for_file": dictionary.section_accounts_for_file,
               "decodable": 0}
        for raster in dictionary.rasters:
            totals["rasters"] += 1
            key = str(raster.depth)
            depths[key] = depths.get(key, 0) + 1
            size = f"{raster.width}x{raster.height}"
            dimensions[size] = dimensions.get(size, 0) + 1
            reason = rw_txd.undecodable_reason(raster)
            if reason is None:
                totals["decodable"] += 1
                row["decodable"] += 1
            else:
                totals["listed_not_drawn"] += 1
            identity = None
            if decode and reason is None:
                identity = rw_txd.replacement_identity(dictionary, raster)
            if identity:
                totals["identities"] += 1
            if targets is not None and len(targets) < discs.MAX_TARGETS:
                targets.append(Target(
                    key=f"{member.name}#{raster.index}",
                    label=f"{member.name} · {raster.name or raster.index}",
                    detail=f"{size} · {raster.depth}-bit · "
                           + ("decodes" if reason is None else "listed, not drawn"),
                    budget=("Export only: a PNG import is not offered." if reason is None
                            else "Listed, not drawn."),
                    searchable=f"{member.name} {raster.name} {size}",
                    raw={"member": member.name, "raster": raster.index, "width": raster.width,
                         "height": raster.height, "depth": raster.depth,
                         "raster_format": "0x%08x" % raster.raster_format,
                         "psm": raster.psm, "texture_name": raster.name,
                         "texel_bytes": raster.texel_bytes,
                         "palette_bytes": raster.palette_bytes,
                         "replacement_identity": identity, "refusal": reason},
                    fields=(Field("size", "note", "Size", size, read_only=True),
                            Field("depth", "note", "Bits per texel", str(raster.depth),
                                  read_only=True),
                            Field("identity", "note", "PCSX2 name (derived)", identity or "-",
                                  read_only=True),
                            Field("refusal", "note", "Why not drawn", reason or "-",
                                  read_only=True))))
        rows.append(row)
    return {"totals": totals, "depths": depths, "dimensions": dimensions, "rows": rows,
            "refusals": refusals}


class TextureDictionaryLane:
    """The shared walker.  ``read_only`` lanes count; art lanes also export."""

    def __init__(self, discs: Any, schema: str, lane_id: str, surface: str, page: str,
                 title: str, classification: str, *, selection: str, refusal: str,
                 validator: str, read_only: bool) -> None:
        self.discs = discs
        self.recipe_schema = schema
        self.lane_id = lane_id
        self.capability_id = f"{discs.GAME_ID.replace('_', '')}.{lane_id}"
        self.surface = surface
        self.page = page
        self.title = title
        self.classification = classification
        self.selection = selection
        self.REFUSAL = refusal
        self.read_only = read_only
        #: An inventory changes nothing; an export writes PNG files beside the disc, not
        #: into it, so neither lane is a fixed-allocation image writer.
        self.fixed_allocation = False
        self.validators = (f"tools/validate_{discs.GAME_ID}_{validator}.sh",
                           f"tools/validate_{discs.GAME_ID}_{validator}.bat")

    def members(self, disc: Any) -> Tuple[Any, ...]:
        """Which dictionaries this row owns.

        A team's dictionaries are the ones named ``<a team prefix>_...``, and the
        prefixes come off the disc's own crowd tables (``Disc.team_prefixes``)
        rather than a list this module would have to keep in step: 594 of the 2002
        disc's 761 dictionaries and 610 of the 2003 disc's 840 carry one [M].
        """

        every = disc.members_named(suffix=self.discs.TEXTURE_SUFFIX)
        if self.selection == "all":
            return every
        prefixes = disc.team_prefixes()
        team = tuple(member for member in every
                     if disc.is_team_member(member.name, prefixes))
        if self.selection == "team":
            return team
        owned = {member.name for member in team}
        return tuple(member for member in every if member.name not in owned)

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        discs = self.discs
        schema = self.recipe_schema
        targets: List[Target] = []
        with discs.Disc(Path(source)) as disc:
            walk = _rows_for(discs, disc, self.members(disc), decode=not self.read_only,
                             progress=progress, targets=targets)
        document = {"schema": schema, "source": str(source), "lane": self.lane_id,
                    "selection": self.selection, "why": self.REFUSAL,
                    "not_drawn_reason": rw_txd.undecodable_reason(
                        rw_txd.Raster(0, "", "", 8, 8, 4, 0, 0, 0, 0, 0, 0, 0, 0)),
                    "targets_listed": len(targets), **walk}
        if self.read_only:
            targets = [Target(
                key=f"dictionary:{row['member']}", label=row["member"],
                detail=f"{row['rasters']} raster(s) · {row['decodable']} decode · "
                       f"{row['bytes']} bytes",
                budget="Read-only: this lane counts and writes nothing.",
                searchable=row["member"], raw=dict(row),
                fields=(Field("rasters", "note", "Rasters", str(row["rasters"]), read_only=True),
                        Field("decodable", "note", "Decodable", str(row["decodable"]),
                              read_only=True))) for row in walk["rows"][:discs.MAX_TARGETS]]
            document["targets_listed"] = len(targets)
        return Catalogue(schema, self.lane_id, str(source), tuple(targets), document)

    # -- exporting: an art lane writes PNG files, never the disc ------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """An export carries no values; any value proposed is refused by name."""

        if self.read_only or values:
            return self.REFUSAL
        if target.raw.get("refusal"):
            return str(target.raw["refusal"])
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        if self.read_only:
            return {"schema": self.recipe_schema, "lane": self.lane_id, "exports": []}
        return {"schema": self.recipe_schema, "lane": self.lane_id,
                "exports": [edit.target_key for edit in edits]}

    def _resolve(self, catalogue: Catalogue, recipe: Mapping[str, Any]) -> List[Target]:
        if self.read_only:
            raise Refusal(self.REFUSAL)
        keys = list(recipe.get("exports") or ())
        if not keys:
            raise Refusal("This recipe names no raster; choose one to export before building.")
        out = []
        for key in keys:
            target = catalogue.target(str(key))
            reason = target.raw.get("refusal")
            if reason:
                raise Refusal(str(reason))
            out.append(target)
        return out

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        targets = self._resolve(catalogue, recipe)
        return Plan(self.lane_id, tuple(target.key for target in targets), (),
                    {"schema": self.recipe_schema, "lane": self.lane_id,
                     "exports": len(targets),
                     "note": "An export writes PNG files beside the disc; it declares files, "
                             "not byte ranges, and never touches the source."})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        targets = self._resolve(catalogue, recipe)
        destination = Path(destination)
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite it.")
        artifacts: List[Artifact] = []
        rows: List[Dict[str, Any]] = []
        for number, target in enumerate(targets):
            png = self.decode_png(Path(source), target)
            where = destination if number == 0 else destination.with_name(
                f"{destination.stem}-{number}{destination.suffix or '.png'}")
            where.write_bytes(png)
            digest = hashlib.sha256(png).hexdigest()
            artifacts.append(Artifact(str(where), digest, kind="png"))
            rows.append({"target": target.key, "path": str(where), "bytes": len(png),
                         "sha256": digest, "width": int(target.raw["width"]),
                         "height": int(target.raw["height"]),
                         "replacement_identity": target.raw.get("replacement_identity")})
        document = {"schema": self.recipe_schema, "lane": self.lane_id, "exports": rows,
                    "no_writer": NO_TEXTURE_WRITER}
        return Receipt(self.recipe_schema, self.lane_id, str(source), str(destination), (),
                       document, tuple(artifacts))

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-decode every exported raster from the source and compare, importing no build state."""

        failures: List[str] = []
        rows = list(receipt.document.get("exports") or ())
        destination = Path(destination)
        for number, row in enumerate(rows):
            # The file to check is the destination this call names, laid out by the same
            # rule the build used, not the path the receipt happens to remember: a
            # verifier that read the receipt's path would never see a tampered copy.
            path = destination if number == 0 else destination.with_name(
                f"{destination.stem}-{number}{destination.suffix or '.png'}")
            if not path.is_file():
                failures.append(f"{path} was not written")
                continue
            written = path.read_bytes()
            if hashlib.sha256(written).hexdigest() != row["sha256"]:
                failures.append(f"{path} does not carry the bytes the receipt names")
            member, _, index = str(row["target"]).rpartition("#")
            with self.discs.Disc(Path(source)) as disc:
                dictionary = disc.texture_dictionary(member)
                raster = dictionary.raster(int(index))
                rgba = rw_txd.decode_rgba(dictionary, raster)
            again = ea_shps.encode_png(raster.width, raster.height, rgba)
            if again != written:
                failures.append(f"{path} is not what the source's own bytes decode to")
            if raster.width != int(row["width"]) or raster.height != int(row["height"]):
                failures.append(f"{path} does not carry the raster's measured size")
        if not rows:
            failures.append("the receipt names no export")
        summary = (f"{len(rows)} raster(s) exported and re-decoded from the source; every PNG "
                   f"matches its digest and the source's own bytes")
        if failures:
            summary = "; ".join(failures[:3])
        return Verdict(not failures, summary,
                       {"exports": len(rows), "failures": failures,
                        "no_writer": NO_TEXTURE_WRITER})

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        if self.read_only:
            raise Refusal(self.REFUSAL)
        for target in catalogue.targets:
            if not target.raw.get("refusal"):
                return (Edit(target.key, {}, note="conformance: export this raster"),)
        raise Refusal("This catalogue lists no raster this reader draws.")

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{self.discs.GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(self.discs.build_synthetic_disc())
        return path

    # -- ArtLane ------------------------------------------------------------

    def decode_png(self, source: Path, target: Target) -> bytes:
        with self.discs.Disc(Path(source)) as disc:
            dictionary = disc.texture_dictionary(str(target.raw["member"]))
            raster = dictionary.raster(int(target.raw["raster"]))
            rgba = rw_txd.decode_rgba(dictionary, raster)
        return ea_shps.encode_png(raster.width, raster.height, rgba)

    def encode(self, source: Path, target: Target, png: bytes) -> EncodedArt:
        raise Refusal(NO_TEXTURE_WRITER)

    def replacement_identity(self, target: Target) -> Optional[str]:
        value = target.raw.get("replacement_identity")
        return str(value) if value else None


# --------------------------------------------------------------------------
# CPTH camera paths, WIFF heads and RenderWare clumps: one read-only row
# --------------------------------------------------------------------------

def read_camera(discs: Any, payload: bytes, name: str) -> Dict[str, Any]:
    """The ``CPTH`` header, refusing anything whose own arithmetic does not hold."""

    if len(payload) < discs.CAMERA_HEADER_BYTES or payload[:4] != discs.CAMERA_MAGIC:
        raise discs.DiscError(
            f"{name} does not begin with {discs.CAMERA_MAGIC.decode('latin-1')}; it is not "
            f"a Blitz camera path.")
    word1, records, word3 = struct.unpack_from("<3I", payload, 4)
    expected = discs.CAMERA_HEADER_BYTES + records * discs.CAMERA_RECORD_BYTES
    if expected != len(payload):
        raise discs.DiscError(
            f"{name} declares {records} records, which is {expected} bytes with its header, and "
            f"the member is {len(payload)}; it is not a Blitz camera path.")
    return {"records": records, "word1": word1, "word3": word3,
            "record_bytes": discs.CAMERA_RECORD_BYTES}


def read_wiff(discs: Any, head: bytes, size: int, name: str) -> Dict[str, Any]:
    """The big-endian ``WIFF`` head, refusing anything whose declared size is not the member."""

    if len(head) < 12 or head[:4] != discs.WIFF_MAGIC:
        raise discs.DiscError(
            f"{name} does not begin with {discs.WIFF_MAGIC.decode('latin-1')}; it is not a "
            f"Blitz WIFF container.")
    declared = struct.unpack_from(">I", head, 4)[0]
    if declared + 8 != size:
        raise discs.DiscError(
            f"{name} declares {declared} big-endian body bytes in a {size}-byte member, and "
            f"{declared} + 8 is not {size}; it is not a Blitz WIFF container.")
    return {"declared_body_bytes": declared, "form": head[8:12].decode("latin-1")}


def walk_clump(payload: bytes, name: str) -> Dict[str, Any]:
    """A ``.dff``'s top-level RenderWare sections, and whether they consume the member."""

    sections = list(rw_txd.walk(payload, 0, len(payload)))
    consumed = bool(sections) and sections[-1].end == len(payload)
    return {"sections": len(sections), "consumed_whole_member": consumed,
            "ids": ["0x%x" % section.id for section in sections[:8]],
            "library_version": "0x%08x" % sections[0].version if sections else None}


class ContainerInventoryLane:
    """Camera paths, ``WIFF`` container heads and RenderWare clumps.  Read-only."""

    surface = "scorebug_presentation"
    page = "presentation"
    title = "Camera paths, WIFF containers and RenderWare clumps"
    classification = "read-only-mapped"
    fixed_allocation = True
    read_only = True
    REFUSAL = CONTAINER_INVENTORY_REFUSAL

    def __init__(self, discs: Any, schema: str,
                 lane_id: str = "presentation.camera_paths") -> None:
        self.discs = discs
        self.recipe_schema = schema
        self.lane_id = lane_id
        self.capability_id = f"{discs.GAME_ID.replace('_', '')}.{lane_id}"
        self.validators = (f"tools/validate_{discs.GAME_ID}_containers.sh",
                           f"tools/validate_{discs.GAME_ID}_containers.bat")

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        discs = self.discs
        schema = self.recipe_schema
        targets: List[Target] = []
        cameras: List[Dict[str, Any]] = []
        wiffs: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        camera_words: Dict[str, int] = {}
        wiff_forms: Dict[str, int] = {}
        clump_totals = {"members": 0, "consumed_whole_member": 0}
        clump_sequences: Dict[str, int] = {}
        versions: Dict[str, int] = {}
        with discs.Disc(Path(source)) as disc:
            for member in disc.members_named(suffix=discs.CAMERA_SUFFIX):
                if progress is not None:
                    progress(f"{member.name}…")
                try:
                    row = read_camera(discs, disc.member_bytes(member.name), member.name)
                except discs.DiscError as exc:
                    refusals.append({"where": member.name, "sentence": str(exc)})
                    continue
                row.update({"member": member.name, "bytes": member.size})
                cameras.append(row)
                camera_words[str(row["word1"])] = camera_words.get(str(row["word1"]), 0) + 1
                if len(targets) < discs.MAX_TARGETS:
                    targets.append(Target(
                        key=f"camera:{member.name}", label=member.name,
                        detail=f"{row['records']} record(s) x "
                               f"{discs.CAMERA_RECORD_BYTES} bytes · {member.size} bytes",
                        budget="Read-only: a record's fields are not measured.",
                        searchable=member.name, raw=dict(row),
                        fields=(Field("records", "note", "Records", str(row["records"]),
                                      read_only=True),
                                Field("word1", "note", "Header word 1 (unnamed)",
                                      str(row["word1"]), read_only=True))))
            for suffix in discs.WIFF_SUFFIXES:
                for member in disc.members_named(suffix=suffix):
                    try:
                        row = read_wiff(discs, disc.head(member.name, 12), member.size,
                                        member.name)
                    except discs.DiscError as exc:
                        refusals.append({"where": member.name, "sentence": str(exc)})
                        continue
                    row.update({"member": member.name, "bytes": member.size})
                    wiffs.append(row)
                    wiff_forms[row["form"]] = wiff_forms.get(row["form"], 0) + 1
                    if len(targets) < discs.MAX_TARGETS:
                        targets.append(Target(
                            key=f"wiff:{member.name}", label=member.name,
                            detail=f"WIFF form {row['form']!r} · {member.size} bytes",
                            budget="Read-only: no chunk inside a WIFF is read.",
                            searchable=member.name, raw=dict(row),
                            fields=(Field("form", "note", "Form type", row["form"],
                                          read_only=True),)))
            for member in disc.members_named(suffix=discs.MODEL_SUFFIX):
                try:
                    row = walk_clump(disc.member_bytes(member.name), member.name)
                except discs.DiscError as exc:
                    refusals.append({"where": member.name, "sentence": str(exc)})
                    continue
                clump_totals["members"] += 1
                clump_totals["consumed_whole_member"] += 1 if row["consumed_whole_member"] else 0
                key = " ".join(row["ids"])
                clump_sequences[key] = clump_sequences.get(key, 0) + 1
                if row["library_version"]:
                    versions[row["library_version"]] = versions.get(row["library_version"], 0) + 1
        document = {
            "schema": schema, "source": str(source), "lane": self.lane_id, "why": self.REFUSAL,
            "camera_paths": len(cameras), "camera_records": sum(r["records"] for r in cameras),
            "camera_header_word1_census": camera_words,
            "wiff_members": len(wiffs), "wiff_forms": wiff_forms,
            "clump_members": clump_totals["members"],
            "clumps_whose_walk_consumes_the_member": clump_totals["consumed_whole_member"],
            "clump_top_level_sequences": dict(sorted(clump_sequences.items(),
                                                     key=lambda item: -item[1])[:6]),
            "clump_library_versions": versions,
            "targets_listed": len(targets), "cameras": cameras, "wiffs": wiffs,
            "refusals": refusals,
        }
        return Catalogue(schema, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema, "lane": self.lane_id, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{self.discs.GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(self.discs.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


# --------------------------------------------------------------------------
# The four command-line entry points, which are the same on both discs
# --------------------------------------------------------------------------

def text_lane_main(discs: Any, by_name: Mapping[str, TextLineLane], short_title: str,
                   argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{discs.GAME_ID}.text_lane",
        description=f"Catalogue or edit the text members of an {short_title} disc.")
    parser.add_argument("--lane", choices=sorted(by_name), default="crowd")
    parser.add_argument("--source")
    parser.add_argument("--destination")
    parser.add_argument("--recipe")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = by_name[arguments.lane]
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                recipe = lane.compose_recipe(edits)
                plan = lane.plan(source, recipe, catalogue)
                destination = Path(room) / "out.iso"
                receipt = lane.build(source, destination, recipe, catalogue)
                verdict = lane.verify(source, destination, receipt)
                if not verdict.passed:
                    print(f"error: {verdict.summary}", file=sys.stderr)
                    return 1
                print("SELFTEST lane=%s targets=%d declared_ranges=%d declared_bytes=%d %s"
                      % (lane.lane_id, len(catalogue.targets), len(plan.declared_ranges),
                         plan.declared_bytes, verdict.summary))
                return 0
        if not arguments.source:
            parser.error("give --source a disc image, or --selftest")
        catalogue = lane.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
        document = dict(catalogue.document)
        if arguments.recipe and arguments.destination:
            recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
            receipt = lane.build(Path(arguments.source), Path(arguments.destination),
                                 recipe, catalogue)
            verdict = lane.verify(Path(arguments.source), Path(arguments.destination), receipt)
            document = {"receipt": dict(receipt.document), "verdict": verdict.summary,
                        "passed": verdict.passed}
            print("BUILD %s %s" % ("PASS" if verdict.passed else "FAIL", verdict.summary))
        else:
            print("CATALOGUE lane=%s members=%d lines=%d listed=%d"
                  % (lane.lane_id, document["members"], document["lines"],
                     document["targets_listed"]))
        if arguments.out:
            Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def roster_lane_main(discs: Any, lane: RosterNameLane, short_title: str,
                     argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{discs.GAME_ID}.roster_lane",
        description=f"Catalogue or edit the player names in an {short_title} roster.")
    parser.add_argument("--source")
    parser.add_argument("--destination")
    parser.add_argument("--recipe")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
                plan = lane.plan(source, recipe, catalogue)
                destination = Path(room) / "out.iso"
                receipt = lane.build(source, destination, recipe, catalogue)
                verdict = lane.verify(source, destination, receipt)
                if not verdict.passed:
                    print(f"error: {verdict.summary}", file=sys.stderr)
                    return 1
                print("SELFTEST lane=%s records=%d declared_ranges=%d declared_bytes=%d %s"
                      % (lane.lane_id, len(catalogue.targets), len(plan.declared_ranges),
                         plan.declared_bytes, verdict.summary))
                return 0
        if not arguments.source:
            parser.error("give --source a disc image, or --selftest")
        catalogue = lane.build_catalogue(Path(arguments.source))
        document = dict(catalogue.document)
        if arguments.recipe and arguments.destination:
            recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
            receipt = lane.build(Path(arguments.source), Path(arguments.destination), recipe,
                                 catalogue)
            verdict = lane.verify(Path(arguments.source), Path(arguments.destination), receipt)
            document = {"receipt": dict(receipt.document), "verdict": verdict.summary,
                        "passed": verdict.passed}
            print("BUILD %s %s" % ("PASS" if verdict.passed else "FAIL", verdict.summary))
        else:
            print("ROSTER blocks=%d records=%d team_byte_agrees=%d crowd_tables=%d logos=%d"
                  % (document["blocks"], document["records"],
                     document["records_whose_team_byte_equals_their_block"],
                     document["team_crowd_tables"], document["team_logo_dictionaries"]))
        if arguments.out:
            Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def texture_lane_main(discs: Any, by_name: Mapping[str, TextureDictionaryLane],
                      short_title: str, argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{discs.GAME_ID}.texture_lane",
        description=f"Walk the RenderWare texture dictionaries of an {short_title} disc.")
    parser.add_argument("--lane", choices=sorted(by_name), default="inventory")
    parser.add_argument("--source")
    parser.add_argument("--out")
    parser.add_argument("--export-png")
    parser.add_argument("--target")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = by_name[arguments.lane]
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                document = dict(catalogue.document)
                exported = 0
                if not lane.read_only:
                    for target in catalogue.targets:
                        if target.raw.get("refusal") is None:
                            png = lane.decode_png(source, target)
                            if not png.startswith(b"\x89PNG"):
                                print("error: the export is not a PNG", file=sys.stderr)
                                return 1
                            exported += 1
                    if exported == 0:
                        print("error: the synthetic source exported no raster", file=sys.stderr)
                        return 1
                totals = document["totals"]
                print("SELFTEST lane=%s dictionaries=%d rasters=%d decodable=%d identities=%d "
                      "exported=%d" % (lane.lane_id, totals["dictionaries"], totals["rasters"],
                                       totals["decodable"], totals["identities"], exported))
                return 0
        if not arguments.source:
            parser.error("give --source a disc image, or --selftest")
        catalogue = lane.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
        document = dict(catalogue.document)
        if arguments.export_png and arguments.target:
            png = lane.decode_png(Path(arguments.source), catalogue.target(arguments.target))
            Path(arguments.export_png).write_bytes(png)
            print("EXPORT %s %d bytes" % (arguments.export_png, len(png)))
        totals = document["totals"]
        print("TEXTURES lane=%s dictionaries=%d rasters=%d decodable=%d identities=%d "
              "not_drawn=%d refusals=%d"
              % (lane.lane_id, totals["dictionaries"], totals["rasters"], totals["decodable"],
                 totals["identities"], totals["listed_not_drawn"], len(document["refusals"])))
        if arguments.out:
            Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def camera_lane_main(discs: Any, lane: ContainerInventoryLane, short_title: str,
                     argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{discs.GAME_ID}.camera_lane",
        description=f"List the camera paths, WIFF containers and clumps of an {short_title} "
                    f"disc. Read-only.")
    parser.add_argument("--source")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            if not arguments.source:
                parser.error("give --source a disc image, or --selftest")
            catalogue = lane.build_catalogue(Path(arguments.source))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    print("CONTAINERS cameras=%d records=%d wiff=%d forms=%s clumps=%d consumed=%d refusals=%d"
          % (document["camera_paths"], document["camera_records"], document["wiff_members"],
             document["wiff_forms"], document["clump_members"],
             document["clumps_whose_walk_consumes_the_member"], len(document["refusals"])))
    return 0
