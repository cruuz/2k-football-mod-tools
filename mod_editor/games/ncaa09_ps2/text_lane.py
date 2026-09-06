"""The NCAA Football 09 disc's ``TEXT`` string banks, measured and never written.

A ``TEXT`` member is a run of NUL-terminated 8-bit strings.  The disc carries
**1,247 of them in four containers** -- ``EXAMS.DAT`` 1,238, ``JERSEY.DAT`` 7,
``OSDKSTRN.DAT`` 1 and ``GAMEDATA.DAT`` 1, 241,787 bytes in all [M].

This lane counts them and measures each one: how many slots, how many bytes,
how much room a slot has.  **The strings themselves are read from the user's own
image on demand and never stored here**, which is the whole reason this is a
measurement lane and not a dump: a string bank is game text.

There is no writer.  A same-size string replacement is the shape a writer would
take -- the slot's allocation is its room, so a shorter string fits and a longer
one does not -- and it needs the preload caches kept in step, which is why the
container inventory names them.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.text_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers

CAPABILITY_ID = "ncaa09ps2.menus.text_members"
LANE_ID = "menus.text_members"
SCHEMA = "ncaa09_ps2_text_members/v1"

#: EA stored these banks in 8-bit characters.  latin-1 and never utf-8: a utf-8
#: decoder either mangles an accented character or refuses the whole bank.
TEXT_ENCODING = "latin-1"

TERMINATOR = b"\x00"

#: How many member rows the page lists.  1,247 members is a table [M].
MAX_MEMBER_TARGETS = 2000


def split_strings(payload: bytes) -> Tuple[str, ...]:
    """The NUL-separated strings in a ``TEXT`` member, decoded latin-1."""

    pieces = [chunk.decode(TEXT_ENCODING) for chunk in payload.split(TERMINATOR)]
    while pieces and not pieces[-1]:
        pieces.pop()
    return tuple(pieces)


def slots_in(payload: bytes) -> Tuple[Tuple[int, int, int], ...]:
    """Every string slot, as ``(byte offset, length, allocation)``.

    A slot is one NUL-separated run of characters.  Its *length* is the string
    there now; its *allocation* is the room it has, which runs to the next
    slot's first byte less the terminator -- so a bank a previous edit shortened
    still shows the room its padding occupies, and an edit stays reversible.
    Empty runs are skipped: a slot with no bytes has no string to replace.
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
        allocation = (starts[position + 1][0] - offset - 1
                      if position + 1 < len(starts) else max(0, tail - offset))
        out.append((offset, length, max(length, allocation)))
    return tuple(out)


def measure(payload: bytes) -> Dict[str, Any]:
    """What a ``TEXT`` member is, as numbers: never the strings themselves."""

    slots = slots_in(payload)
    lengths = [length for _offset, length, _room in slots]
    return {
        "bytes": len(payload),
        "slots": len(slots),
        "shortest": min(lengths) if lengths else 0,
        "longest": max(lengths) if lengths else 0,
        "characters": sum(lengths),
        "padding_bytes": sum(room - length for _o, length, room in slots),
        "ends_with_terminator": payload.endswith(TERMINATOR),
    }


class TextLane:
    """The disc's ``TEXT`` banks, measured, read-only."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "menus"
    page = "menus"
    title = "Every TEXT string bank on the disc"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_text.sh",
        "tools/validate_ncaa09_ps2_text.bat",
    )
    fixed_allocation = True
    read_only = True

    REFUSAL = (
        "This lane measures the string banks on your disc and writes nothing. A writer "
        "would replace a string inside the room its slot already has and rewrite the "
        "preload caches that copy the container; neither is built for NCAA Football 09 "
        "yet, and no rebuilt container of this disc has been booted."
    )

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        image = containers.open_disc(Path(source))
        rows: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        targets: List[Target] = []
        members = slots = characters = payload_bytes = 0
        for name in containers.TEXT_CONTAINERS:
            try:
                container = containers.load_container(image, name)
            except containers.DiscError as exc:
                refusals.append({"reader": "containers.load_container",
                                 "where": name, "sentence": str(exc)})
                continue
            for index in range(len(container)):
                if progress is not None and index % 128 == 0:
                    progress(f"{name} member {index} of {len(container)}…")
                try:
                    payload = containers.member_uncached(container, index)
                except ea_terf.TerfError as exc:
                    refusals.append({"reader": "ea_terf.member",
                                     "where": f"{name}:{index}", "sentence": str(exc)})
                    continue
                if ea_terf.identify_member(payload) != ea_terf.FORMAT_TEXT:
                    continue
                row = measure(payload)
                row.update({"container": name, "member": index})
                members += 1
                slots += row["slots"]
                characters += row["characters"]
                payload_bytes += row["bytes"]
                rows.append(row)
                if len(targets) < MAX_MEMBER_TARGETS:
                    targets.append(self._member_target(row))
        document = {
            "schema": SCHEMA,
            "source": str(source),
            "containers": list(containers.TEXT_CONTAINERS),
            "text_members": members,
            "slots": slots,
            "characters": characters,
            "payload_bytes": payload_bytes,
            "member_rows_listed": len(targets),
            "member_rows_cap": MAX_MEMBER_TARGETS,
            "encoding": TEXT_ENCODING,
            "rows": rows,
            "refusals": refusals,
        }
        return Catalogue(schema=SCHEMA, lane_id=self.lane_id, source=str(source),
                         targets=tuple(targets), document=document)

    @staticmethod
    def _member_target(row: Mapping[str, Any]) -> Target:
        return Target(
            key=f"text:{row['container']}:{row['member']}",
            label=f"{row['container']} member {row['member']}",
            detail=" · ".join([
                f"{row['slots']} slot(s)",
                f"{row['characters']:,} character(s)",
                f"{row['bytes']:,} bytes",
                f"{row['padding_bytes']:,} byte(s) of padding",
            ]),
            budget="Read-only: this lane never writes to your disc.",
            searchable=f"{row['container']} {row['member']} text",
            raw=dict(row),
            fields=(
                Field("slots", "note", "Slots",
                      "How many NUL-separated strings this bank holds.", read_only=True),
                Field("longest", "note", "Longest string",
                      "The longest string's length in bytes.", read_only=True),
                Field("padding_bytes", "note", "Padding",
                      "Bytes of room past the strings that are there now.", read_only=True),
                Field("ends_with_terminator", "note", "Ends with a terminator",
                      "Whether the member's last byte is a NUL.", read_only=True),
            ),
        )

    def preview(self, source: Path, target: Target, *,
                limit: int = 40) -> Tuple[str, ...]:
        """The first *limit* strings of one bank, read off the user's image now.

        Nothing returned here is written to this repository; it exists so a page
        can show the user their own text without this module ever holding it.
        """

        raw = dict(target.raw or {})
        image = containers.open_disc(Path(source))
        container = containers.load_container(image, str(raw.get("container")))
        payload = containers.member_uncached(container, int(raw.get("member") or 0))
        return split_strings(payload)[:limit]

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-text-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.text_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.text_lane",
        description="Measure every TEXT string bank on an NCAA Football 09 (PS2) disc. "
                    "Read-only; counts and lengths, never the strings.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    lane = TextLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            catalogue = lane.build_catalogue(
                Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("TEXT members=%d slots=%d characters=%d bytes=%d"
          % (document["text_members"], document["slots"],
             document["characters"], document["payload_bytes"]))
    return 0


__all__ = ["CAPABILITY_ID", "LANE_ID", "MAX_MEMBER_TARGETS", "SCHEMA",
           "TERMINATOR", "TEXT_ENCODING", "TextLane", "measure", "slots_in",
           "split_strings"]


if __name__ == "__main__":
    raise SystemExit(_main())
