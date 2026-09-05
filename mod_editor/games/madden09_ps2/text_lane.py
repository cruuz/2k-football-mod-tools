"""The disc's ``TEXT`` members: counted, measured, and read on demand.

``TEXT`` is what ``identify_member`` calls a member whose decompressed bytes are
printable NUL-separated strings, and Madden 09's retail disc carries 14,748 of
them -- most of the story generator's templates, plus menu and front-end
banks [M].  This lane lists them: which container, which member, how many
strings, how long, and the member's digest.

**The catalogue never carries a string.**  The contract's third rule is that a
catalogue holds names, offsets, lengths and digests and never payload, and a
catalogue is a file that can be shipped.  So the counts and the digest are
catalogued, and the strings themselves are read from the *user's own disc*
whenever they are asked for, through :meth:`TextLane.preview` -- which is also
what the command line's ``--preview`` prints.  Nothing decoded is written
anywhere by this lane.

It writes nothing to the disc either: ``plan``, ``build`` and ``verify`` refuse
by contract.  A ``TEXT`` **writer** would mean rebuilding a ``TERF`` container,
which cannot be shrunk back down without an ``LZH1`` encoder that exists
nowhere public, and would have to keep the ``GAME.QKL`` / ``FE.QKL`` preload
copies consistent [S]; neither is done, so nothing here claims it.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.text_lane --source DISC.iso

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
    Edit,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
)

from . import containers

CAPABILITY_ID = "madden09ps2.menus.text_members"
LANE_ID = "menus.text_members"
SCHEMA = "madden09_ps2_text_inventory/v1"

#: How many ``TEXT`` members are listed as targets.  The document's counts are
#: complete however many rows the table shows.
MAX_TARGETS = 4000

#: How many strings :meth:`TextLane.preview` returns by default.  A preview is
#: a look at the user's own disc, not a dump.
PREVIEW_STRINGS = 12

#: How long one previewed string may be before it is elided.
PREVIEW_WIDTH = 120


def split_strings(payload: bytes) -> Tuple[str, ...]:
    """The NUL-separated strings in a ``TEXT`` member, decoded latin-1.

    latin-1 and never utf-8: EA stores 8-bit characters, and a decoder that
    raises on a byte outside ASCII would refuse members that are perfectly
    readable.  Trailing empties are dropped -- the format pads with NULs.
    """

    pieces = [chunk.decode("latin-1") for chunk in payload.split(b"\x00")]
    while pieces and not pieces[-1].strip("\x00 \t\r\n"):
        pieces.pop()
    return tuple(pieces)


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


class TextLane:
    """Every ``TEXT`` member on the disc, measured; the strings stay on the disc."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "menus"
    page = "menus"
    title = "Text banks (read-only)"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_madden09_ps2_text.sh",
        "tools/validate_madden09_ps2_text.bat",
    )
    fixed_allocation = False
    read_only = True

    REFUSAL = (
        "The text lane reads your disc's string banks and never writes to them. Editing one "
        "would mean rebuilding its TERF container, which needs an LZH1 encoder that exists "
        "nowhere public, and keeping the GAME.QKL and FE.QKL preload copies consistent; "
        "neither is done, so this lane does not offer it."
    )

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        files = containers.data_files(image)
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        totals = {"members": 0, "strings": 0, "bytes": 0}
        per_container: Dict[str, int] = {}
        for position, entry in enumerate(files):
            if progress is not None:
                progress(f"{entry.name} ({position + 1} of {len(files)})…")
            _report, container = containers.describe_container(image, entry, with_formats=False)
            if container is None:
                continue
            for index, payload in containers.members_of_format(container, ea_terf.FORMAT_TEXT):
                stats = measure(payload)
                totals["members"] += 1
                totals["strings"] += stats["strings"]
                totals["bytes"] += stats["bytes"]
                per_container[entry.name] = per_container.get(entry.name, 0) + 1
                if len(targets) >= MAX_TARGETS:
                    continue
                row = {"container": entry.name, "index": index, **stats}
                rows.append(row)
                targets.append(Target(
                    key=f"{entry.name}:{index}",
                    label=f"{entry.name} member {index}",
                    detail=f"{stats['strings']:,} strings · {stats['bytes']:,} bytes · "
                           f"longest {stats['longest_string']}",
                    budget="Read-only: the strings stay on your disc; this lane counts them.",
                    searchable=f"{entry.name} {index} text",
                    raw=row,
                    fields=(
                        Field("container", "note", "Container",
                              "Which /DATA container holds this bank.", read_only=True),
                        Field("index", "note", "Member", "Its index in that container.",
                              read_only=True),
                        Field("strings", "note", "Strings",
                              "How many NUL-separated strings the member carries.",
                              read_only=True),
                        Field("bytes", "note", "Bytes",
                              "The member's decompressed length.", read_only=True),
                        Field("longest_string", "note", "Longest string",
                              "The longest string in the bank, in characters.", read_only=True),
                        Field("sha256", "note", "Digest",
                              "SHA-256 of the decompressed member.", read_only=True),
                    ),
                ))
        document = {
            "schema": SCHEMA,
            "source": str(source),
            "text_members": totals["members"],
            "strings": totals["strings"],
            "bytes": totals["bytes"],
            "rows_listed": len(targets),
            "rows_cap": MAX_TARGETS,
            "per_container": per_container,
            "rows": rows,
            "note": "Counts and digests only. The strings themselves are read from your own "
                    "disc when you ask for them and are never stored here.",
        }
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    # -- reading the user's own strings, on demand ---------------------

    def preview(self, source: Path, target: Target, *,
                limit: int = PREVIEW_STRINGS) -> Tuple[str, ...]:
        """The first *limit* strings of one member, read from the user's disc now.

        Nothing is cached and nothing is written; this is the only path by
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
        image = containers.open_disc(Path(source))
        container = containers.load_container(image, container_name)
        try:
            payload = container.member(index)
        except ea_terf.TerfError as exc:
            raise Refusal(str(exc)) from exc
        pieces = [piece for piece in split_strings(payload) if piece.strip()]
        return tuple(
            piece if len(piece) <= PREVIEW_WIDTH else piece[:PREVIEW_WIDTH - 1] + "…"
            for piece in pieces[:max(0, limit)]
        )

    # -- the three refusals --------------------------------------------

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

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-text-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.text_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.text_lane",
        description="Count the TEXT banks on a Madden NFL 09 (PS2) disc. Read-only.",
    )
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--preview", metavar="CONTAINER:INDEX",
                        help="print the first strings of one member, read from your own disc")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = TextLane()
    try:
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.preview:
            target = catalogue.target(arguments.preview)
            for line in lane.preview(Path(arguments.source), target):
                print(line)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("TEXT members=%d strings=%d bytes=%d listed=%d"
          % (document["text_members"], document["strings"], document["bytes"],
             document["rows_listed"]))
    return 0


__all__ = ["CAPABILITY_ID", "LANE_ID", "MAX_TARGETS", "PREVIEW_STRINGS", "PREVIEW_WIDTH",
           "SCHEMA", "TextLane", "measure", "split_strings"]


if __name__ == "__main__":
    raise SystemExit(_main())
