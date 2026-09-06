"""A lane whose targets are string slots inside ``TEXT`` members of ``TERF`` containers.

``TEXT`` is what ``ea_terf.identify_member`` calls a member whose decompressed
bytes are printable NUL-separated strings.  Both Tiburon discs this package
serves carry thousands of them -- Madden NFL 09 14,748, NCAA Football 09 1,247
[M] -- and the rule for editing one is the same on both, which is why it is
written once here.

**A string slot is a fixed allocation.**  A slot's room runs to the next string
less the terminator, and that is what the budget quotes.  A shorter replacement
is padded to it with the format's own terminator, ``\x00``, so the string the
game reads ends where the replacement ends and every byte after it inside the
slot is a NUL.  A longer replacement is refused with the length it has to fit.
Nothing moves: the member keeps its exact byte count, so the container does, so
the ISO extent does, and the destination image is the source's exact size.
Because the allocation counts the padding a previous edit left behind,
shortening a string does not spend it: the next catalogue offers the same room
again.

**The catalogue carries no string.**  A catalogue is a file that can be
shipped, so the document is counts and digests; the strings themselves reach a
screen only through the *targets* built from the user's own image, or through
:meth:`TextBankLane.preview`, which re-reads them from the disc on demand.

**A container a preload cache names is refused.**  A ``QL01`` cache carries a
byte copy of at least some of what it names, and editing one copy and not the
other would leave the game reading whichever it reached first.  The list is
read off the user's own image by the game's ``preload_names``, and
:attr:`TextBankLane.preload_copies` is the measured floor for an image whose
caches cannot be walked.

What a game sets: its disc-access module, its ids and schemas, which containers
to walk, which of them a cache names, and how many targets to list.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import (
    Catalogue,
    DeclaredRange,
    Edit,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
)

from . import iso_tools


#: How many string slots are listed as targets.  The document's counts are
#: complete however many rows the table shows.
MAX_TARGETS = 4000

#: How many strings :meth:`TextBankLane.preview` returns by default.  A preview is
#: a look at the user's own disc, not a dump.
PREVIEW_STRINGS = 12

#: How long one previewed string may be before it is elided.
PREVIEW_WIDTH = 120

#: The containers holding ``TEXT`` members that the retail disc's preload
#: caches name [M].  The list a user's own image declares is read at catalogue
#: time by the game's ``preload_names`` and takes precedence; this is the
#: measured floor, so an image whose caches this module cannot read still
#: refuses the two it is known to have to.
#: The terminator a shorter replacement is padded with -- the same byte the
#: reader splits on.
TERMINATOR = b"\x00"

#: The encoding EA stored these banks in.  latin-1 and never utf-8: a decoder
#: that raises on an accented byte would refuse members that read perfectly.
TEXT_ENCODING = "latin-1"

#: How a slot's key is spelled: ``text:<container>:<member>:<byte offset>``.
SLOT_PREFIX = "text:"


class TextError(Refusal):
    """This lane could not do what was asked; the sentence says why."""


def split_strings(payload: bytes) -> Tuple[str, ...]:
    """The NUL-separated strings in a ``TEXT`` member, decoded latin-1.

    latin-1 and never utf-8: EA stores 8-bit characters, and a decoder that
    raises on a byte outside ASCII would refuse members that are perfectly
    readable.  Trailing empties are dropped -- the format pads with NULs.
    """

    pieces = [chunk.decode(TEXT_ENCODING) for chunk in payload.split(TERMINATOR)]
    while pieces and not pieces[-1].strip("\x00 \t\r\n"):
        pieces.pop()
    return tuple(pieces)


def slots_in(payload: bytes) -> Tuple[Tuple[int, int, int], ...]:
    """Every string slot in a member, as ``(byte offset, length, allocation)``.

    A slot is one NUL-separated run of characters.  Its *length* is the string
    that is there now; its *allocation* is the room it has, which is everything
    up to the next slot -- the NUL padding a previous edit left behind
    included, less the one byte that terminates it.  The last slot's allocation
    runs to the end of the member, less a terminator only if the member ends
    with one; the retail banks end without one [M], and a replacement that
    fills the allocation exactly reproduces that shape.

    Defining the allocation this way is what makes an edit reversible: a
    thirty-eight byte string cut to two leaves thirty-six NULs, and those NULs
    are still this slot's room the next time the catalogue is built, not a gap
    nothing can reach.  Empty runs are skipped -- a slot with no bytes has no
    string in it to replace.

    One byte is spent once: a member that shipped without a terminator gains
    one the first time its last slot is shortened, so that slot's allocation
    drops by exactly one and is stable from then on.
    """

    starts: List[Tuple[int, int]] = []
    cursor = 0
    for piece in payload.split(TERMINATOR):
        if piece:
            starts.append((cursor, len(piece)))
        cursor += len(piece) + 1
    tail = len(payload) - (1 if payload.endswith(TERMINATOR) else 0)
    out: List[Tuple[int, int, int]] = []
    for position, (offset, length) in enumerate(starts):
        if position + 1 < len(starts):
            allocation = starts[position + 1][0] - offset - 1
        else:
            allocation = max(0, tail - offset)
        out.append((offset, length, max(length, allocation)))
    return tuple(out)


def is_text_member(payload: bytes) -> bool:
    """Whether this member is a string bank, NUL padding and all.

    ``ea_terf.identify_member`` calls a member ``TEXT`` when its first
    thirty-two bytes are all printable.  That is right for a member as the disc
    ships it and wrong for one this lane has shortened: a bank whose first
    string was cut from thirty-eight characters to two now begins with two
    printable bytes and a run of NULs, and the shared classifier -- correctly,
    for its own purpose -- stops calling it text.  So the padding is discounted
    here: a bank is a bank when the head, with its terminators removed, is
    printable and not empty.

    **[M]** On the owner's retail disc this answers exactly what
    ``identify_member`` answers: 14,748 members either way, in the same eight
    containers, because no member the disc ships carries a NUL in its head.
    """

    if ea_terf.identify_member(payload) == ea_terf.FORMAT_TEXT:
        return True
    for magic, _name in ea_terf.MEMBER_FORMAT_MAGICS:
        if payload.startswith(magic):
            return False
    head = payload[:ea_terf.IDENTIFY_HEAD].replace(TERMINATOR, b"")
    return bool(head) and all(0x20 <= byte < 0x7F or byte in (9, 10, 13) for byte in head)


def measure(payload: bytes) -> Dict[str, Any]:
    """What a ``TEXT`` member is, as numbers: never the strings themselves."""

    pieces = split_strings(payload)
    lengths = [len(piece) for piece in pieces if piece]
    printable = sum(1 for byte in payload if 0x20 <= byte < 0x7F or byte in (0x00, 0x09, 0x0A, 0x0D))
    return {
        "bytes": len(payload),
        "strings": len(lengths),
        "longest_string": max(lengths) if lengths else 0,
        "mean_string": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
        "printable_ratio": round(printable / len(payload), 4) if payload else 0.0,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def slot_key(container: str, member: int, offset: int) -> str:
    """The target key for one string slot."""

    return f"{SLOT_PREFIX}{container}:{member}:{offset}"


def parse_slot_key(key: str) -> Tuple[str, int, int]:
    """``text:STRYTEXT.DAT:12:0`` back into container, member and byte offset."""

    if not key.startswith(SLOT_PREFIX):
        raise TextError(
            f"{key!r} is not a string slot; a slot's key is spelled "
            f"{SLOT_PREFIX}<container>:<member>:<byte offset>."
        )
    try:
        container, member, offset = key[len(SLOT_PREFIX):].rsplit(":", 2)
        return container, int(member), int(offset)
    except ValueError as exc:
        raise TextError(
            f"{key!r} is not a slot key this lane writes; it should read "
            f"{SLOT_PREFIX}<container>:<member>:<byte offset>."
        ) from exc


def encode_slot(text: str, allocation: int) -> bytes:
    """*text* as the bytes that fill a slot of *allocation* bytes exactly.

    Refuses a replacement that does not fit, naming the length it must fit; a
    shorter one is padded with the format's terminator so the string the game
    reads ends where the replacement ends.
    """

    if "\x00" in text:
        raise TextError(
            "the replacement may not contain a NUL character -- that is what ends a "
            "string in this format; remove it."
        )
    try:
        raw = text.encode(TEXT_ENCODING, "strict")
    except UnicodeEncodeError as exc:
        raise TextError(
            f"the replacement cannot be written as {TEXT_ENCODING}, which is the only "
            f"encoding these banks carry; use characters that encoding has."
        ) from exc
    if len(raw) > allocation:
        raise TextError(
            f"the replacement is {len(raw)} bytes and this string's own allocation is "
            f"{allocation}; shorten it to {allocation}."
        )
    return raw.ljust(allocation, TERMINATOR)


class TextBankLane:
    """Every ``TEXT`` member on the disc, measured; six containers' worth editable."""

    #: Every one of these is a game's to set.
    discs: Any = None
    lane_id = ""
    capability_id = ""
    #: The three schema strings this lane's documents carry.
    schema = ""
    recipe_schema = ""
    receipt_schema = ""
    #: The containers whose ``TEXT`` members this lane walks, and which of them
    #: a preload cache is known to name.  Both are the game's [M].
    text_containers: Tuple[str, ...] = ()
    preload_copies: Mapping[str, Tuple[str, ...]] = {}
    #: What a sentence calls this game.
    game_title = "this game"
    surface = "menus"
    page = "menus"
    title = "Text banks"
    classification = "offline-writer-proved"
    validators = (
        "tools/validate_madden09_ps2_text.sh",
        "tools/validate_madden09_ps2_text.bat",
    )
    #: A slot is rewritten inside its own bytes, so the image keeps its size.
    fixed_allocation = True
    read_only = False

    def read_only_reason(self, container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        """Why this container offers no edit, or ``""`` when it does.

        *cached* is what the user's own image's preload caches name, from
        the game's ``preload_names``; the measured constant is the floor.
        """

        caches = (cached or {}).get(container_name.upper()) or self.preload_copies.get(
            container_name.upper())
        if caches:
            named = " and ".join(f"/DATA/{item}" for item in caches)
            return (
                f"{container_name} is named in {named}, the preload cache, which carries a "
                f"copy of at least some of what it names and which this lane does not "
                f"rewrite; editing one copy and not the other would leave the game reading "
                f"whichever it reached first."
            )
        return ""

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = self.discs.open_disc(Path(source))
        files = self.discs.data_files(image)
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        cached = self.discs.preload_names(image)
        totals = {"members": 0, "strings": 0, "bytes": 0, "slots": 0}
        per_container: Dict[str, int] = {}
        for position, entry in enumerate(files):
            if progress is not None:
                progress(f"{entry.name} ({position + 1} of {len(files)})…")
            _report, container = self.discs.describe_container(image, entry, with_formats=False)
            if container is None:
                continue
            reason = self.read_only_reason(entry.name, cached)
            for index, payload in self._text_members(container):
                stats = measure(payload)
                slots = slots_in(payload)
                totals["members"] += 1
                totals["strings"] += stats["strings"]
                totals["bytes"] += stats["bytes"]
                totals["slots"] += len(slots)
                per_container[entry.name] = per_container.get(entry.name, 0) + 1
                rows.append({"container": entry.name, "index": index,
                             "slots": len(slots), "editable": not reason, **stats})
                if len(targets) >= MAX_TARGETS:
                    continue
                targets.extend(self._slot_targets(entry.name, index, payload, slots,
                                                  stats, reason,
                                                  MAX_TARGETS - len(targets)))
        document = {
            "schema": self.schema,
            "source": str(source),
            "text_members": totals["members"],
            "strings": totals["strings"],
            "bytes": totals["bytes"],
            "slots": totals["slots"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "rows_cap": MAX_TARGETS,
            "read_only_containers": {name: list(caches)
                                    for name, caches in sorted(cached.items())},
            "per_container": per_container,
            "rows": rows,
            "note": "Counts and digests only. The strings themselves are read from your own "
                    "disc when you ask for them and are never stored here.",
        }
        return Catalogue(self.schema, self.lane_id, str(source), tuple(targets), document)

    @staticmethod
    def _text_members(container: ea_terf.TerfContainer):
        """Every member of *container* this lane calls a string bank.

        Written here rather than through ``members_of_format`` so a
        bank this lane has already shortened -- whose first thirty-two bytes
        are no longer all printable -- is still found; see :func:`is_text_member`.
        """

        for index in range(len(container)):
            try:
                if not is_text_member(container.member(
                        index, max_output=ea_terf.IDENTIFY_HEAD)):
                    continue
                payload = container.member(index)
            except ea_terf.TerfError:
                # One member a codec cannot open must not empty a catalogue of
                # thousands, so it is skipped rather than raised.
                continue
            if not is_text_member(payload):
                continue
            yield index, payload

    def _slot_targets(self, container_name: str, index: int, payload: bytes,
                      slots: Sequence[Tuple[int, int]], stats: Mapping[str, Any],
                      reason: str, remaining: int) -> List[Target]:
        out: List[Target] = []
        for position, (offset, length, allocation) in enumerate(slots):
            if len(out) >= remaining:
                break
            text = payload[offset:offset + length].decode(TEXT_ENCODING)
            shown = text if len(text) <= PREVIEW_WIDTH else text[:PREVIEW_WIDTH - 1] + "…"
            detail = [f"{length:,} of {allocation:,} bytes",
                      f"slot {position + 1} of {len(slots)}"]
            if reason:
                detail.append("read-only")
            out.append(Target(
                key=slot_key(container_name, index, offset),
                label=(shown if shown.strip()
                       else f"{container_name} member {index} at byte {offset}"),
                detail=" · ".join(detail),
                budget=(f"Up to {allocation} characters -- this string's own allocation. "
                        "A shorter one is padded with NULs; nothing moves."),
                searchable=f"{container_name} {index} {offset} {text[:200]}",
                raw={
                    "container": container_name,
                    "iso_path": f"{self.discs.DATA_DIRECTORY}/{container_name}",
                    "index": index,
                    "member": index,
                    "offset": offset,
                    "length_bytes": length,
                    "allocation_bytes": allocation,
                    "member_bytes": int(stats["bytes"]),
                    "member_sha256": str(stats["sha256"]),
                    "editable": not reason,
                    "reason": reason,
                    "text": text,
                    "text_sha256": hashlib.sha256(
                        text.encode(TEXT_ENCODING, "replace")).hexdigest(),
                },
                fields=(Field(
                    "new_text", "text", "Replacement text",
                    (reason or
                     f"Up to {allocation} characters -- this string's own allocation, "
                     f"because the bank has no spare bytes. A shorter replacement is padded "
                     f"with NULs, so the string ends where you end it."),
                    maximum=allocation, read_only=bool(reason),
                ),),
            ))
        return out

    # -- reading the user's own strings, on demand ---------------------

    def preview(self, source: Path, target: Target, *,
                limit: int = PREVIEW_STRINGS) -> Tuple[str, ...]:
        """The first *limit* strings of one member, read from the user's disc now.

        Nothing is cached and nothing is written; this is one of two paths by
        which a string in this game reaches a screen, and it always comes
        straight off the image the user opened.
        """

        container_name = str(target.raw.get("container") or "")
        index = target.raw.get("index")
        if not container_name or not isinstance(index, int):
            raise Refusal(
                f"{target.key} does not name a container and member, so there is nothing to "
                f"preview; rebuild the catalogue from your disc."
            )
        image = self.discs.open_disc(Path(source))
        container = self.discs.load_container(image, container_name)
        try:
            payload = container.member(index)
        except ea_terf.TerfError as exc:
            raise Refusal(str(exc)) from exc
        pieces = [piece for piece in split_strings(payload) if piece.strip()]
        return tuple(
            piece if len(piece) <= PREVIEW_WIDTH else piece[:PREVIEW_WIDTH - 1] + "…"
            for piece in pieces[:max(0, limit)]
        )

    # -- editing -------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"new_text", "expect_sha256"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane writes; "
                    f"give new_text.")
        if not target.key.startswith(SLOT_PREFIX):
            return f"{target.key} is not a string slot; choose one of the catalogued strings."
        reason = str(target.raw.get("reason") or "")
        if reason:
            return reason
        text = values.get("new_text")
        if not isinstance(text, str) or text == "":
            return "Type the replacement text; an empty string cannot be written."
        allocation = int(target.raw.get("allocation_bytes") or 0)
        try:
            encode_slot(text, allocation)
        except TextError as exc:
            return str(exc)
        if text == target.raw.get("text"):
            return "That is the text already there; change it or leave the string alone."
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows: List[Dict[str, Any]] = []
        for edit in edits:
            row: Dict[str, Any] = {"target": edit.target_key,
                                   "new_text": edit.values.get("new_text")}
            if edit.values.get("expect_sha256"):
                row["expect_sha256"] = edit.values["expect_sha256"]
            rows.append(row)
        return {"schema": self.recipe_schema, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    def _recipe_edits(self, recipe: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        if str(recipe.get("schema")) != self.recipe_schema:
            raise TextError(
                f"this recipe says it is {recipe.get('schema')!r} and this lane writes "
                f"{self.recipe_schema}; hand it a recipe compose_recipe made."
            )
        rows = recipe.get("edits")
        if not isinstance(rows, list) or not rows:
            raise TextError(
                "this recipe changes nothing: its 'edits' list is empty, and a build with "
                "nothing to write would be a plain copy."
            )
        return [dict(row) for row in rows]

    def _resolve(self, source: Path, recipe: Mapping[str, Any]) -> Dict[str, Any]:
        """Work out every changed byte from the user's own image, writing nothing."""

        image = self.discs.open_disc(Path(source))
        files = {entry.name: entry for entry in self.discs.data_files(image)}
        cached = self.discs.preload_names(image)
        wanted: Dict[str, Dict[int, List[Tuple[int, str, Optional[str]]]]] = {}
        order: List[str] = []
        for row in self._recipe_edits(recipe):
            key = str(row.get("target", ""))
            container_name, member, offset = parse_slot_key(key)
            reason = self.read_only_reason(container_name, cached)
            if reason:
                raise TextError(reason)
            text = row.get("new_text")
            if not isinstance(text, str) or text == "":
                raise TextError(
                    f"{key} names no replacement text; an empty string cannot be written."
                )
            wanted.setdefault(container_name, {}).setdefault(member, []).append(
                (offset, text, row.get("expect_sha256")))
            order.append(key)

        rebuilt: Dict[str, bytes] = {}
        edits_report: List[Dict[str, Any]] = []
        members_report: List[Dict[str, Any]] = []
        for container_name, members in sorted(wanted.items()):
            entry = files.get(container_name)
            if entry is None:
                raise TextError(
                    f"this image holds no {self.discs.DATA_DIRECTORY}/{container_name}; it "
                    f"is not a {self.game_title} disc, or the container has been "
                    f"removed."
                )
            writable = self.discs.open_for_rewrite(image, entry)
            original = writable.data
            container = writable.parsed
            working = original
            for member, slots in sorted(members.items()):
                writable.require_member_inside(member)
                payload = container.member(member)
                known = {offset: (length, allocation)
                         for offset, length, allocation in slots_in(payload)}
                edited = bytearray(payload)
                for offset, text, expected in sorted(slots):
                    if offset not in known:
                        raise TextError(
                            f"member {member} of {container_name} has no string starting at "
                            f"byte {offset}; rebuild the catalogue from this image."
                        )
                    length, allocation = known[offset]
                    before = bytes(payload[offset:offset + length]).decode(TEXT_ENCODING)
                    if expected and hashlib.sha256(
                            before.encode(TEXT_ENCODING, "replace")).hexdigest() != expected:
                        raise TextError(
                            f"the string at byte {offset} of member {member} of "
                            f"{container_name} is not the one this edit was made against; "
                            f"rebuild the catalogue from this image and try again."
                        )
                    edited[offset:offset + allocation] = encode_slot(text, allocation)
                    edits_report.append({
                        "target": slot_key(container_name, member, offset),
                        "container": container_name,
                        "iso_path": entry.path,
                        "member": member,
                        "offset": offset,
                        "allocation_bytes": allocation,
                        "written_bytes": len(text.encode(TEXT_ENCODING, "replace")),
                        "after_sha256": hashlib.sha256(
                            text.encode(TEXT_ENCODING, "replace")).hexdigest(),
                    })
                new_payload = bytes(edited)
                if len(new_payload) != len(payload):
                    raise TextError(
                        f"editing member {member} of {container_name} changed its length "
                        f"from {len(payload):,} to {len(new_payload):,}; a slot rewrite "
                        f"cannot do that and the result is refused."
                    )
                working = ea_terf.rewrite_member(
                    working, member, new_payload,
                    allow_short_tail=writable.recorded_short)
                if len(working) != len(original):
                    raise TextError(
                        f"rewriting member {member} changed {entry.path} from "
                        f"{len(original):,} to {len(working):,} bytes; this lane writes only "
                        f"inside the space a file already owns."
                    )
                members_report.append({
                    "iso_path": entry.path,
                    "container": container_name,
                    "member": member,
                    "bytes": len(new_payload),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "destination_sha256": hashlib.sha256(new_payload).hexdigest(),
                })
            rebuilt[entry.path] = working
        return {"rebuilt": rebuilt, "edits": edits_report, "members": members_report,
                "target_keys": tuple(order)}

    @staticmethod
    def _ranges(iso_report: Mapping[str, Any]) -> Tuple[DeclaredRange, ...]:
        out: List[DeclaredRange] = []
        for item in iso_report.get("declared_ranges", ()):
            row = item if isinstance(item, Mapping) else item.as_dict()
            out.append(DeclaredRange(int(row["start"]), int(row["length"]),
                                     str(row.get("reason", ""))))
        return tuple(out)

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        writer = iso_tools.iso_writer()
        resolved = self._resolve(Path(source), recipe)
        try:
            report = writer.plan_report(Path(source), resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise TextError(str(exc)) from exc
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(resolved["target_keys"]),
            declared_ranges=self._ranges(report),
            document={
                "schema": self.receipt_schema,
                "edits": resolved["edits"],
                "members": resolved["members"],
                "files": sorted(resolved["rebuilt"]),
                "bytes_declared": int(report.get("bytes_declared", 0)),
            },
        )

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        if source.resolve() == destination.resolve():
            raise TextError(
                "the destination is the source; this lane writes a new image and leaves "
                "yours untouched, so give it another name."
            )
        if destination.exists():
            raise TextError(
                f"{destination} already exists and this lane never writes over an image; "
                f"choose a name that is not there yet."
            )
        writer = iso_tools.iso_writer()
        resolved = self._resolve(source, recipe)
        try:
            report = writer.replace_files(source, destination, resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise TextError(str(exc)) from exc
        return Receipt(
            schema=self.receipt_schema,
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=self._ranges(report),
            # The verifier re-derives the claim from the two images and the
            # recipe; the resolved report deliberately holds no replacement
            # text, so the recipe travels beside it.
            document={
                "schema": self.receipt_schema,
                "edits": resolved["edits"],
                "members": resolved["members"],
                "recipe": dict(recipe),
                "iso_write_report": writer.report_to_json(report),
            },
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = self.verify_build(Path(source), Path(destination), dict(receipt.document))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            True,
            f"text verifier: PASS · {report['slots_checked']} string(s) read back from the "
            f"destination · {report['members_checked']} bank(s) re-read at their exact "
            f"length · {report['undeclared_changed_bytes']} undeclared changed bytes.",
            report,
        )

    def verify_build(self, source: Path, destination: Path,
                         receipt_document: Mapping[str, Any]) -> Dict[str, Any]:
        """Re-derive, from the two images and the recipe, that the build did what it claimed.

        **This function imports none of the writer.**  The container-level claim is
        the repository's independent ISO verifier; the string-level claim is this
        module's own reader over the destination's bytes.  What the receipt says is
        an input to be checked, never evidence.

        Four things are proved:

        1. outside the declared byte ranges the destination is the source, the two
           images are the same size, and no untouched file's extent moved;
        2. each edited bank is byte-for-byte the same **length** in both images;
        3. every replacement **reads back** at its own byte offset in the
           destination, padded with the format's terminator to exactly its
           allocation;
        4. inside each edited bank, every byte that differs from the source lies
           inside one of the edited slots -- so a write that scribbled elsewhere is
           caught even though it is inside a declared ISO range.

        Raises :class:`Refusal` naming the first violation; returns counts on pass.
        """

        verifier = iso_tools.iso_verifier()
        iso_report = receipt_document.get("iso_write_report")
        if not isinstance(iso_report, Mapping):
            raise TextError(
                "this receipt carries no ISO write report, so there is nothing to verify "
                "against; rebuild with this lane's build()."
            )
        try:
            iso_verdict = verifier.verify_replacement(source, destination, dict(iso_report))
        except verifier.IsoVerifyError as exc:
            raise TextError(f"the destination image is not the source plus the declared edits: "
                            f"{exc}") from exc

        recipe = receipt_document.get("recipe")
        if not isinstance(recipe, Mapping):
            raise TextError(
                "this receipt carries no recipe, so the intended text is not here to check "
                "against; rebuild with this lane's build()."
            )
        wanted: Dict[str, str] = {}
        for row in recipe.get("edits", ()):
            item = dict(row)
            text = item.get("new_text")
            if not isinstance(text, str) or not text:
                raise TextError("the recipe carries an edit with no replacement text.")
            wanted[str(item.get("target"))] = text
        edits = [dict(item) for item in receipt_document.get("edits", ())]
        if not edits or set(wanted) != {str(item["target"]) for item in edits}:
            raise TextError(
                "the receipt's edits and the recipe's edits do not name the same strings, so "
                "the claim cannot be checked; rebuild with this lane's build()."
            )

        source_image = self.discs.open_disc(Path(source))
        destination_image = self.discs.open_disc(Path(destination))
        checked = 0
        members_checked = 0
        names = sorted({str(item["container"]) for item in edits})
        for container_name in names:
            source_container = self.discs.load_container(source_image, container_name)
            destination_container = self.discs.load_container(destination_image, container_name)
            members = sorted({int(item["member"]) for item in edits
                              if str(item["container"]) == container_name})
            for member in members:
                try:
                    before = source_container.member(member)
                    after = destination_container.member(member)
                except ea_terf.TerfError as exc:
                    raise TextError(
                        f"member {member} of {container_name} could not be read back out of the "
                        f"destination: {exc}"
                    ) from exc
                if len(before) != len(after):
                    raise TextError(
                        f"member {member} of {container_name} is {len(before):,} bytes in the "
                        f"source and {len(after):,} in the destination; a slot rewrite cannot "
                        f"change a length."
                    )
                members_checked += 1
                allowed: List[Tuple[int, int]] = []
                for item in edits:
                    if int(item["member"]) != member or str(item["container"]) != container_name:
                        continue
                    offset = int(item["offset"])
                    allocation = int(item["allocation_bytes"])
                    allowed.append((offset, allocation))
                    # Re-expressed rather than encode_slot()'d: a verifier that
                    # calls the encoder cannot see the encoder pad with the wrong
                    # byte, because both sides would be wrong together.
                    text = wanted[str(item["target"])].encode(TEXT_ENCODING, "strict")
                    if len(text) > allocation:
                        raise TextError(
                            f"the recipe asks for {len(text)} bytes at byte {offset} of member "
                            f"{member} of {container_name}, whose allocation is {allocation}."
                        )
                    expected = text + TERMINATOR * (allocation - len(text))
                    found = bytes(after[offset:offset + allocation])
                    if found != expected:
                        raise TextError(
                            f"the string at byte {offset} of member {member} of "
                            f"{container_name} does not hold the replacement: the destination "
                            f"has {found[:32]!r} and the recipe asked for {expected[:32]!r}."
                        )
                    checked += 1
                for offset in range(len(before)):
                    if before[offset] == after[offset]:
                        continue
                    if not any(start <= offset < start + length for start, length in allowed):
                        raise TextError(
                            f"byte {offset} of member {member} of {container_name} changed and "
                            f"no edited string covers it; the write reached outside what it "
                            f"declared."
                        )
        return {
            "schema": self.receipt_schema,
            "source": str(source),
            "destination": str(destination),
            "verdict": "PASS",
            "slots_checked": checked,
            "members_checked": members_checked,
            "undeclared_changed_bytes": 0,
            "iso": {key: iso_verdict[key] for key in sorted(iso_verdict)
                    if isinstance(iso_verdict.get(key), (int, str, bool))},
        }

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-text-synthetic.iso"
        path.write_bytes(self.discs.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if not target.raw.get("editable"):
                continue
            if int(target.raw.get("allocation_bytes") or 0) < 8:
                continue
            return (Edit(target.key,
                         {"new_text": "REPLACED BY CONFORMANCE",
                          "expect_sha256": target.raw["text_sha256"]},
                         note="conformance"),)
        raise Refusal(
            "the synthetic disc carries no editable string long enough to replace; rebuild "
            "the fixture from the game's build_synthetic_disc()."
        )


# --------------------------------------------------------------------------
# The independent verifier
# --------------------------------------------------------------------------


__all__ = [
    "MAX_TARGETS",
    "PREVIEW_STRINGS",
    "PREVIEW_WIDTH",
    "SLOT_PREFIX",
    "TERMINATOR",
    "TEXT_ENCODING",
    "TextBankLane",
    "parse_slot_key",
    "slot_key",
    "slots_in",
]
