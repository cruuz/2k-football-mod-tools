"""The "Send to Madden" draft class: recognised, measured, and left alone.

NCAA Football writes one file the rest of this studio never sees.  At the end of
a dynasty season the game exports its graduating class to a **memory-card save**
that Madden NFL imports as its draft pool -- ``BASLUS-21769LClass08`` for the
NCAA 09 / Madden 09 pair -- and **no table on this disc holds one** [M].  It is
produced at run time; the disc carries the record *shape* and the position
tables the labels come from, and nothing else.

So this page's source is not the disc.  It is the save file itself, and this
lane says so in one sentence when it is handed an ISO.

What it recognises [M/S]
------------------------

============  =========================================================
bytes                138,240 -- exactly 270 x 512-byte sectors
header               4 bytes, ``46 00 40 06``
records              **1,600**, each **86 bytes**, at offset 4
trailer              636 zero bytes, padding to the sector boundary
============  =========================================================

Per record, the fields this lane reads and reports [S: the owner's own NCAA
draft-class research, `NCAA-Draft-Class-Editor`]:

============  ======  =============================================
offset          size  field
============  ======  =============================================
4                  1  ``TGID`` college id (1..254; 255 = not set)
6                 11  first name, ASCII, zero-padded
17                14  last name
31                 1  ``PYER`` college year
32                 1  ``PRSD`` redshirt flag
33                 1  ``POVR`` overall
34                 1  ``PJEN`` squad number
35                 1  ``PPOS`` position
36                 1  ``PWGT`` weight
37                 1  ``PHGT`` height in inches
38                21  the twenty-one rating bytes
============  ======  =============================================

**Why this is a reader and not a compiler.**  The same fields appear in this
disc's own ``PLAY`` table, 86 of them, and the two are the same record family
two years apart -- so the shape is corroborated by the disc rather than taken on
trust [M].  But a *compiler* for this file already exists outside this
repository, in the owner's own `NCAA-Draft-Class-Editor`, and building a second
one here would be two implementations of one format.  This lane recognises a
class, says what is in it, and refuses to write: **`read-only-mapped`**, and the
refusal names where the writer is.

The disc's half, catalogued by other pages [M]: the position labels a class is
drawn with are ``LEAGUE.DAT`` member 0's ``DRPS`` (17 rows), ``PLPS`` (21) and
``POSG`` (10); ``PPRO`` in ``TEMPLATE.DAT`` member 1 is the per-player
professional projection a dynasty accumulates, capacity 75 and **0 rows on the
disc**.

**No value from a user's save is written to this repository.**  The document is
counts, offsets, lengths and digests; a record's contents reach a screen only
through the targets built from the user's own file, exactly as the text lane's
strings do.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.saves_lane --source CLASS.bin
    python3 -m mod_editor.games.ncaa09_ps2.saves_lane --selftest

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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

CAPABILITY_ID = "ncaa09ps2.saves.draft_class"
LANE_ID = "saves.draft_class"
SCHEMA = "ncaa09_ps2_draft_class_inventory/v1"

#: The memory-card directory NCAA Football 09 writes the class into, for the
#: Madden NFL 09 pairing [S].
SAVE_DIRECTORY = "BASLUS-21769LClass08"

#: The file's exact length: 270 sectors of 512 bytes [S].  Pinned rather than
#: computed -- ``4 + 1600 * 86`` is 137,604, which rounds to 269 sectors, and
#: the real file is 270.
FILE_BYTES = 138_240
#: The four bytes it starts with [S].
MAGIC = bytes((0x46, 0x00, 0x40, 0x06))
#: Where the records start, how many there are and how long each is [S].
RECORD_OFFSET = 4
RECORD_COUNT = 1600
RECORD_BYTES = 86
#: What is left after the records: zero padding to the sector boundary.
TRAILER_BYTES = FILE_BYTES - RECORD_OFFSET - RECORD_COUNT * RECORD_BYTES

#: The byte a college id carries when no college is set [S].
COLLEGE_NOT_SET = 255

#: How many records are listed as targets.  All 1,600 fit comfortably.
MAX_TARGETS = 1600

#: ``(offset, length, key, label)`` per field this lane reads [S].  Names are
#: fixed-width ASCII runs; everything else is one byte.
NAME_FIELDS: Tuple[Tuple[int, int, str, str], ...] = (
    (6, 11, "first_name", "First name"),
    (17, 14, "last_name", "Last name"),
)
BYTE_FIELDS: Tuple[Tuple[int, str, str], ...] = (
    (4, "TGID", "College id"),
    (31, "PYER", "College year"),
    (32, "PRSD", "Redshirt"),
    (33, "POVR", "Overall"),
    (34, "PJEN", "Squad number"),
    (35, "PPOS", "Position"),
    (36, "PWGT", "Weight"),
    (37, "PHGT", "Height (inches)"),
)

#: Where the twenty-one rating bytes sit [S].  They are reported as a block
#: rather than named one by one: which byte is which rating is the owner's own
#: research and this lane does not restate it as if it had measured it.
RATING_OFFSET = 38
RATING_COUNT = 21

#: The one sentence this lane answers a write request with.
NO_WRITER = (
    "This lane recognises and reads a draft class; it does not write one. A compiler for "
    "this exact file already exists outside this repository, in the owner's own "
    "NCAA-Draft-Class-Editor, which builds a 138,240-byte class from canonical draft data "
    "and packs it into a memory-card container; a second implementation of one format is "
    "how two of them start to disagree. Use that to build a class, and this to check what "
    "one holds."
)

#: What a source that is not a draft class is told.
NOT_A_CLASS = (
    "this is not an NCAA Football draft-class save: a class is exactly {wanted:,} bytes "
    "and starts with {magic}, and this file is {found:,} bytes and starts with {head}. "
    "The Saves page reads the memory-card file NCAA Football writes for Madden "
    "({directory}), not a disc image -- point it at the exported save."
)


class DraftClassError(Refusal):
    """This is not a draft class this lane reads; the sentence says why."""


def is_draft_class(payload: bytes) -> bool:
    """Whether *payload* is the 138,240-byte class file, by length and magic."""

    return len(payload) == FILE_BYTES and payload[:len(MAGIC)] == MAGIC


def record_at(payload: bytes, index: int) -> bytes:
    """One 86-byte record, or a refusal naming the range."""

    if not 0 <= index < RECORD_COUNT:
        raise DraftClassError(
            f"record {index} is outside the class: a class holds {RECORD_COUNT} "
            f"(0..{RECORD_COUNT - 1})."
        )
    start = RECORD_OFFSET + index * RECORD_BYTES
    return payload[start:start + RECORD_BYTES]


def read_record(record: bytes) -> Dict[str, Any]:
    """What one record holds, for the fields this lane reads."""

    out: Dict[str, Any] = {}
    for offset, length, key, _label in NAME_FIELDS:
        raw = record[offset - RECORD_OFFSET:offset - RECORD_OFFSET + length]
        out[key] = raw.split(b"\x00", 1)[0].decode("latin-1")
    for offset, key, _label in BYTE_FIELDS:
        out[key] = record[offset - RECORD_OFFSET]
    out["ratings"] = list(record[RATING_OFFSET - RECORD_OFFSET:
                                 RATING_OFFSET - RECORD_OFFSET + RATING_COUNT])
    return out


def is_empty(record: bytes) -> bool:
    """Whether a record is all zero -- the state Madden 09 hangs on [S]."""

    return not any(record)


class DraftClassLane:
    """An NCAA Football draft class, recognised and read.  Never written."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "saves"
    page = "saves"
    title = "Send-to-Madden draft class"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_saves.sh",
        "tools/validate_ncaa09_ps2_saves.bat",
    )
    fixed_allocation = False
    read_only = True

    REFUSAL = NO_WRITER

    # -- catalogue ----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        path = Path(source)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise DraftClassError(f"{path} could not be read: {exc}") from exc
        if not is_draft_class(payload):
            raise DraftClassError(NOT_A_CLASS.format(
                wanted=FILE_BYTES, magic=MAGIC.hex(" "), found=len(payload),
                head=bytes(payload[:4]).hex(" ") or "nothing",
                directory=SAVE_DIRECTORY))
        targets: List[Target] = []
        empty = 0
        no_college = 0
        colleges: Dict[int, int] = {}
        positions: Dict[int, int] = {}
        overall_low, overall_high = 255, -1
        shape = self._fields()
        for index in range(RECORD_COUNT):
            if progress is not None and index and index % 400 == 0:
                progress(f"{index} of {RECORD_COUNT} records…")
            record = record_at(payload, index)
            if is_empty(record):
                empty += 1
                continue
            values = read_record(record)
            college = int(values["TGID"])
            if college == COLLEGE_NOT_SET:
                no_college += 1
            colleges[college] = colleges.get(college, 0) + 1
            positions[int(values["PPOS"])] = positions.get(int(values["PPOS"]), 0) + 1
            overall_low = min(overall_low, int(values["POVR"]))
            overall_high = max(overall_high, int(values["POVR"]))
            if len(targets) < MAX_TARGETS:
                targets.append(self._target(index, values))
        document = {
            "schema": SCHEMA,
            "source": str(path),
            "save_directory": SAVE_DIRECTORY,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "records": RECORD_COUNT,
            "record_bytes": RECORD_BYTES,
            "record_offset": RECORD_OFFSET,
            "trailer_bytes": TRAILER_BYTES,
            "empty_records": empty,
            "records_listed": len(targets),
            "distinct_colleges": len(colleges),
            "records_without_a_college": no_college,
            "distinct_positions": len(positions),
            "overall_range": [overall_low if overall_high >= 0 else 0,
                              max(overall_high, 0)],
            "writer": NO_WRITER,
            "note": "Counts, offsets, lengths and a digest of your own class file. No "
                    "record's contents are in this document; a name reaches a screen "
                    "only through the target list, read from your file when you ask.",
        }
        return Catalogue(SCHEMA, self.lane_id, str(path), tuple(targets), document)

    @staticmethod
    def _fields() -> Tuple[Field, ...]:
        out = [Field(key, "note", label, "Read from your own class file.", read_only=True)
               for _offset, _length, key, label in NAME_FIELDS]
        out += [Field(key, "note", label, "Read from your own class file.", read_only=True)
                for _offset, key, label in BYTE_FIELDS]
        out.append(Field("ratings", "note", "Ratings",
                         f"The {RATING_COUNT} rating bytes at offset {RATING_OFFSET}, as "
                         f"the record stores them.", read_only=True))
        return tuple(out)

    def _target(self, index: int, values: Mapping[str, Any]) -> Target:
        name = f"{values['first_name']} {values['last_name']}".strip()
        college = int(values["TGID"])
        detail = [f"OVR {values['POVR']}", f"pos {values['PPOS']}",
                  ("college not set" if college == COLLEGE_NOT_SET
                   else f"college {college}")]
        return Target(
            key=f"pick:{index}",
            label=name or f"record {index}",
            detail=" · ".join(detail),
            budget="Read-only: " + NO_WRITER,
            searchable=f"{index} {name} {values['PPOS']} {college}",
            raw={"record": index,
                 "offset": RECORD_OFFSET + index * RECORD_BYTES,
                 **dict(values)},
            fields=self._fields(),
        )

    # -- the write half, which refuses -------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return NO_WRITER

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        """A recipe this lane's own plan and build refuse, and say why.

        The conformance harness composes an empty recipe from a read-only lane
        and then proves ``plan`` and ``build`` refuse it, so this hands back a
        document rather than raising: the refusal belongs where the write is
        attempted, not where it is described.
        """

        return {"schema": SCHEMA, "edits": [], "note": NO_WRITER}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise DraftClassError(NO_WRITER)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise DraftClassError(NO_WRITER)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        return Verdict(False, f"Verification failed: {NO_WRITER}", {"error": NO_WRITER})

    # -- what CI proves it on -----------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        """A class file built from the format's own rules; no game data at all."""

        path = Path(work_dir) / "ncaa09-ps2-draft-class-synthetic.bin"
        path.write_bytes(synthetic_draft_class())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        return ()


def synthetic_draft_class(*, picks: int = 24) -> bytes:
    """A 138,240-byte class in the shape the format declares, computed not sampled.

    *picks* records carry a counting ramp of invented names and numbers; the
    rest carry a non-zero filler record, because **an all-zero slot is what
    Madden 09 hangs on** [S] and a fixture full of them would be a class the
    game refuses.  The trailer is the zero padding the real file has.
    """

    out = bytearray(MAGIC)
    for index in range(RECORD_COUNT):
        record = bytearray(RECORD_BYTES)
        real = index < picks
        record[4 - RECORD_OFFSET] = (index % 200) + 1 if real else 200
        first = (f"Synth{index}" if real else "Filler").encode("ascii")
        last = (f"Pick{index}" if real else f"Slot{index}").encode("ascii")
        record[6 - RECORD_OFFSET:6 - RECORD_OFFSET + len(first)] = first[:10]
        record[17 - RECORD_OFFSET:17 - RECORD_OFFSET + len(last)] = last[:13]
        record[31 - RECORD_OFFSET] = 3
        record[32 - RECORD_OFFSET] = 0
        record[33 - RECORD_OFFSET] = (90 - index) if real else 49
        record[34 - RECORD_OFFSET] = index % 100
        record[35 - RECORD_OFFSET] = index % 21
        record[36 - RECORD_OFFSET] = 40 + (index % 160)
        record[37 - RECORD_OFFSET] = 68 + (index % 12)
        for rating in range(RATING_COUNT):
            record[RATING_OFFSET - RECORD_OFFSET + rating] = (index + rating * 3) % 100
        out += record
    out += bytes(TRAILER_BYTES)
    assert len(out) == FILE_BYTES, len(out)
    return bytes(out)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.saves_lane --source CLASS.bin``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.saves_lane",
        description="Recognise and read an NCAA Football send-to-Madden draft class.",
    )
    parser.add_argument("--source", help="the user's own exported class file")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on a synthetic class; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = DraftClassLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            if not arguments.source:
                parser.error("give --source CLASS.bin, or --selftest")
            catalogue = lane.build_catalogue(
                Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        document = dict(catalogue.document)
        if arguments.out:
            Path(arguments.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        print("NCAA09_DRAFT_CLASS bytes=%d records=%d empty=%d listed=%d colleges=%d"
              % (document["bytes"], document["records"], document["empty_records"],
                 document["records_listed"], document["distinct_colleges"]))
        return 0
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["BYTE_FIELDS", "CAPABILITY_ID", "COLLEGE_NOT_SET", "DraftClassError",
           "DraftClassLane", "FILE_BYTES", "LANE_ID", "MAGIC", "MAX_TARGETS",
           "NAME_FIELDS", "NOT_A_CLASS", "NO_WRITER", "RATING_COUNT", "RATING_OFFSET",
           "RECORD_BYTES", "RECORD_COUNT", "RECORD_OFFSET", "SAVE_DIRECTORY", "SCHEMA",
           "TRAILER_BYTES", "is_draft_class", "is_empty", "read_record", "record_at",
           "synthetic_draft_class"]


if __name__ == "__main__":
    raise SystemExit(_main())
