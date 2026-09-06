"""Every EA TDB database on the NCAA Football 09 disc — catalogued, and now edited.

NCAA 09 keeps its league in a shape Madden 09 does not: ``/DATA/LEAGUE.DAT`` is
a ``COMP`` container of 455 members whose 433 ``RLE1``-packed databases are one
league database plus **432 per-team roster databases**, each a ``PLAY`` and a
``DCHT`` table [M].  ``/DATA/GAMEDATA.DAT`` carries 137 more (one shared play
library and 136 playbooks), ``/DATA/TEMPLATE.DAT`` 11 fresh-dynasty templates,
and ``/DATA/STRMDATA.DB`` is a bare database with no container around it [M].

This lane catalogues all of them -- the tables, their record stride, how many
rows they hold and how many they can, and every field's name, type, bit width
and bit offset -- and **edits the 432 per-team rosters**.

What it edits, and what it deliberately does not
------------------------------------------------

``LEAGUE.DAT`` members 1..432, table ``PLAY``: the squad number, the college
class, the redshirt flag, height, weight, position, and the twenty attribute
fields.  :data:`PLAYER_FIELDS` is the list, and it is a list rather than
"whatever is numeric" so what this page offers is something a reader can check.

**There is no name to edit.**  Madden 09's ``PLAY`` carries ``PFNA`` and
``PLNA``; this one carries neither, because NCAA Football 09's players have no
names -- a licensing fact you can read straight off the field directory [M].
There is no ``PAGE`` either: a college player has a **class**, not an age, so
the disc stores ``PYER`` (3 bits) and ``PRSD`` (2 bits) instead, and those are
what this lane offers in its place.  ``PCON``, ``PYRP``, ``PMOR``, ``POID``,
``TGID`` and the whole ``PSA0..6`` contract block are absent as well; a
player's team here **is which of the 432 databases he is in**.

**The ratings are five bits, and the editor says five bits.**  Madden's
attribute fields are seven bits and its editor stops at 99.  These are five,
and reading them off the disc settles what that means: every value 0..31
appears, and 0..31 is what a five-bit field holds, with 16% of players sitting
on 31 -- the shape of a scale that saturates at its top [M].  So the spinner's
bound is **31**, the field's own, and no control here pretends the stored
number is a 0..99 rating.  ``docs/product/NCAA09_PS2_SCHEMA.md`` §2 is the
field-by-field census this comes from.

Everything else on the disc stays read-only, and each has a measured reason:
``LEAGUE.DAT`` member 0 is the *league* database and belongs to the Text & Team
Identity page's lane, which writes it; ``GAMEDATA.DAT``'s 137 databases are the
playbooks and belong to the Playbooks & Plays page's lane; ``TEMPLATE.DAT``
holds the fresh-dynasty templates, which are a save's starting state rather
than the league; and ``STRMDATA.DB`` is a bare 2 MB database of presentation
tables with no ``PLAY`` table at all [M].

Why a record edit is a bounded write here
-----------------------------------------

A TDB field owns a fixed run of bits in a fixed-stride record, so the
*decompressed* database comes back the same size.  ``LEAGUE.DAT``'s members are
``RLE1``-packed, so what can move is the **stored** size -- and it does not:
measured on the retail disc, a ``PLAY`` edit in each of members 1, 5, 100 and
432 re-packs to **exactly** the byte count EA shipped [M], so the container's
directory does not move and the two copies of it in ``PL.QKL`` stay valid.  The
lane does not rely on that: it prices the re-pack before writing, refuses a
member that would grow past the slot it owns, and rewrites every preload-cache
copy the edit disturbs (:mod:`mod_editor.games._lanes.preload_coherence`).

The four checksums EA stores in each database are recomputed on every write and
re-derived from the destination's own bytes by the verifier -- which is a check
with teeth before the writer existed, because all **8,564** checksum slots on
this disc already hold the value they recompute to [M].

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.database_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_tdb
from mod_editor.games._lanes.tdb_records import FieldSpec, KEEP_NUMBER, TdbRecordLane
from mod_editor.games.contract import Catalogue, Edit, Refusal

from . import containers

CAPABILITY_ID = "ncaa09ps2.players.league_databases"
LANE_ID = "players.league_databases"
SCHEMA = "ncaa09_ps2_league_databases/v1"
RECIPE_SCHEMA = "ncaa09_ps2_league_database_edit/v1"
RECEIPT_SCHEMA = "ncaa09_ps2_league_database_write/v1"

#: The containers this lane opens, in the order a report lists them [M].
DATABASE_CONTAINERS = (
    containers.LEAGUE_CONTAINER,
    containers.GAME_DATA_CONTAINER,
    containers.TEMPLATE_CONTAINER,
)

#: The one container this lane writes.
WRITABLE_CONTAINER = containers.LEAGUE_CONTAINER

#: ``LEAGUE.DAT`` member 0 is the league database -- ``TEAM``, ``CONF``,
#: ``DIVI``, ``STAD``, ``COCH``, ``PACL`` and the create-a-school tables -- and
#: is the Text & Team Identity page's subject, not this one's.  Its rows are
#: catalogued here and edited there, so one page owns one set of bytes.
LEAGUE_MEMBER = 0

#: How many database rows the page lists.  The disc holds 582 [M]; every one is
#: catalogued in the document, and the page's target list stops here so a table
#: stays a table.
MAX_DATABASE_TARGETS = 700

#: How many player rows are listed as editable targets.  The disc holds 24,717
#: across the 432 rosters [M] and the cap is above that, so a retail disc lists
#: every one.  The document says how many were listed either way.
MAX_ROW_TARGETS = 30000

#: The scale ``PLAY``'s attribute fields are on, measured rather than assumed.
#: They are **five bits** on this disc where Madden 09's are seven, and reading
#: 3,295 records off 62 of the 432 rosters finds every value 0..31 in use, with
#: 16% of players on 31 [M].  A five-bit field holds 0..31; that is the bound
#: the editor offers, and what the game draws from it is not established here.
RATING_MAX = 31

#: The range a college squad number covers [M]: ``PJEN`` is seven bits and the
#: disc's own records span 0..99.
JERSEY_MAX = 99


def _rating(name: str, label: str) -> FieldSpec:
    return (name, label,
            f"{label} rating, 0 to {RATING_MAX} -- the five-bit field's own scale.",
            RATING_MAX)


#: The ``PLAY`` fields this lane offers, in the order a page draws them.  Each
#: is ``(field name, label, help, maximum)``; a field the table does not declare
#: is skipped, so a database with a different schema simply offers less.
PLAYER_FIELDS: Tuple[FieldSpec, ...] = (
    ("PJEN", "Squad number", f"Squad number, 0 to {JERSEY_MAX}.", JERSEY_MAX),
    ("PPOS", "Position",
     "Position id, 0 to 20. The labels are the 21 rows of the league database's PLPS "
     "table; this field is the index into them and no name is stored on the player.",
     20),
    ("PYER", "College class",
     "Class as the three-bit field stores it: the disc's own records span 0 to 3, "
     "which is four class years. A college player has a class, not an age, and this "
     "disc carries no PAGE field at all.", None),
    ("PRSD", "Redshirt",
     "Redshirt state as the two-bit field stores it; the disc's records span 0 to 2.",
     None),
    ("PHGT", "Height (inches)",
     "Height in inches, as the seven-bit field stores it: every retail record on this "
     "disc holds 63 to 81.", None),
    ("PWGT", "Weight less 160 (lb)",
     "Weight in pounds MINUS 160, the eight-bit field's own encoding: 0 means 160 lb "
     "and 209, the largest value on this disc, means 369. The same encoding is what "
     "Madden 09's PLAY table uses, so it is one reading across both discs.", None),
    _rating("POVR", "Overall"),
    _rating("PSPD", "Speed"),
    _rating("PACC", "Acceleration"),
    _rating("PAGI", "Agility"),
    _rating("PSTR", "Strength"),
    _rating("PAWR", "Awareness"),
    _rating("PCTH", "Catching"),
    _rating("PCAR", "Carrying"),
    _rating("PTHP", "Throwing power"),
    _rating("PTHA", "Throwing accuracy"),
    _rating("PJMP", "Jumping"),
    _rating("PTAK", "Tackling"),
    _rating("PBTK", "Broken tackles"),
    _rating("PPBK", "Pass blocking"),
    _rating("PRBK", "Run blocking"),
    _rating("PSTA", "Stamina"),
    _rating("PINJ", "Injury"),
    _rating("PIMP", "Importance"),
    _rating("PKPR", "Kick power"),
    _rating("PKAC", "Kick accuracy"),
)

#: The ``DCHT`` fields this lane offers.  A depth-chart row is three fields on
#: this disc -- which player, at which position, how deep -- and the player id
#: is offered read-write because reordering a depth chart is exactly rewriting
#: it.  ``PGID`` values on this disc span 70..30,012 [M].
DEPTH_FIELDS: Tuple[FieldSpec, ...] = (
    ("PGID", "Player id",
     "Which player this depth-chart slot holds, by the PGID its PLAY row carries. "
     "0 empties the slot.", None),
    ("PPOS", "Position", "Position id this slot is for, 0 to 20.", 20),
    ("ddep", "Depth", "How deep in the position this slot is; 0 is the starter.", None),
)

EDITABLE_FIELDS: Mapping[str, Tuple[FieldSpec, ...]] = {
    "PLAY": PLAYER_FIELDS,
    "DCHT": DEPTH_FIELDS,
}


class DatabaseLane(TdbRecordLane):
    """The disc's EA TDB databases, and the rows of the 432 rosters it writes."""

    discs = containers

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Team rosters and every EA TDB database on the disc"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_databases.sh",
        "tools/validate_ncaa09_ps2_databases.bat",
    )

    tdb_containers = DATABASE_CONTAINERS
    writable_containers = (WRITABLE_CONTAINER,)
    bare_databases = (containers.STREAM_DATABASE_FILE,)
    editable_tables = ("PLAY", "DCHT")
    editable_fields = EDITABLE_FIELDS
    max_targets = MAX_DATABASE_TARGETS
    max_row_targets = MAX_ROW_TARGETS

    # -- what this page will not write --------------------------------

    def member_is_editable(self, container_name: str, member: Optional[int],
                           database: ea_tdb.TdbDatabase) -> bool:
        """Only the 432 per-team rosters.  Member 0 is another page's subject."""

        return member is not None and member != LEAGUE_MEMBER

    def read_only_reason(self, container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        name = container_name.upper()
        if name == containers.GAME_DATA_CONTAINER.upper():
            return (f"{container_name} holds the 137 playbook databases, and those are "
                    f"the Playbooks & Plays page's lane -- one page owns one set of "
                    f"bytes, so this one lists them and does not write them.")
        if name == containers.TEMPLATE_CONTAINER.upper():
            return (f"{container_name} holds the fresh-dynasty templates, which are a "
                    f"save's starting state rather than the league this page edits.")
        if name == containers.STREAM_DATABASE_FILE.upper():
            return (f"{container_name} is a bare database of presentation and league "
                    f"tables with no PLAY table at all; it is outside what this page "
                    f"is for.")
        return (f"{container_name} is outside what this page edits: it writes the 432 "
                f"per-team roster databases in {WRITABLE_CONTAINER}.")

    # -- how a row reads ----------------------------------------------

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        if table == "DCHT":
            return f"team {member} · depth slot {index}"
        return f"team {member} · player {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        parts = []
        if table == "PLAY":
            if "PJEN" in values:
                parts.append(f"#{values['PJEN']}")
            if "POVR" in values:
                parts.append(f"OVR {values['POVR']}/{RATING_MAX}")
            if "PPOS" in values:
                parts.append(f"pos {values['PPOS']}")
        else:
            if "PGID" in values:
                parts.append(f"PGID {values['PGID']}")
            if "PPOS" in values:
                parts.append(f"pos {values['PPOS']}")
            if "ddep" in values:
                parts.append(f"depth {values['ddep']}")
        return " · ".join(parts)

    def row_budget(self, container_name: str) -> str:
        return ("Every value is written where it already sits. The database keeps its "
                "exact size; the RLE1-packed member is re-packed and must fit the slot "
                "it already owns, and every preload-cache copy of this container is "
                "rewritten with it.")

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-rosters-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(
            tdb_members=[containers.synthetic_league_database(),
                         synthetic_roster_database(seed=0),
                         synthetic_roster_database(seed=1)]))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """One squad number, one rating and one depth-chart slot, on the fixture."""

        player = depth = None
        for target in catalogue.targets:
            if not target.key.startswith(self.row_prefix):
                continue
            _path, _member, table, _record = self.parse_row_key(target.key)
            if table == "PLAY" and player is None:
                player = target
            elif table == "DCHT" and depth is None:
                depth = target
        if player is None:
            raise Refusal(
                "the synthetic disc carries no editable PLAY row; rebuild the fixture "
                "from synthetic_roster_database()."
            )
        edits = [Edit(player.key, {"PJEN": 47, "POVR": 29, "PYER": 3}, note="conformance")]
        if depth is not None:
            edits.append(Edit(depth.key, {"ddep": 2}, note="conformance"))
        return tuple(edits)


def synthetic_roster_database(*, seed: int = 0, players: int = 6) -> bytes:
    """A per-team roster database in this disc's shape, built from the format's rules.

    Two tables named as the real ones are, carrying the fields this lane edits at
    the widths this disc declares -- five-bit ratings, a three-bit class, a
    two-bit redshirt flag -- so a writer that mis-orders the bit packing is
    visibly wrong.  Nothing here comes from a game: the numbers are a counting
    ramp.  The four checksums are written from the result's own bytes, so the
    fixture is a database that already passes ``ea_tdb.verify_crcs`` -- which is
    what makes it a fair test of a writer that has to keep them passing.
    """

    play_fields = [
        ("PGID", ea_tdb.FIELD_UINT, 16),
        ("PWGT", ea_tdb.FIELD_UINT, 8),
        ("PJEN", ea_tdb.FIELD_UINT, 7),
        ("PHGT", ea_tdb.FIELD_UINT, 7),
        ("PPOS", ea_tdb.FIELD_UINT, 5),
        ("PYER", ea_tdb.FIELD_UINT, 3),
        ("PRSD", ea_tdb.FIELD_UINT, 2),
        ("POVR", ea_tdb.FIELD_UINT, 5),
        ("PSPD", ea_tdb.FIELD_UINT, 5),
        ("PACC", ea_tdb.FIELD_UINT, 5),
        ("PAWR", ea_tdb.FIELD_UINT, 5),
        ("PSTR", ea_tdb.FIELD_UINT, 5),
    ]
    play_rows = tuple({
        "PGID": 1000 + seed * 100 + n, "PWGT": 40 + n, "PJEN": (10 + n) % 100,
        "PHGT": 68 + (n % 8), "PPOS": n % 21, "PYER": n % 4, "PRSD": n % 3,
        "POVR": (12 + n) % 32, "PSPD": (20 + n) % 32, "PACC": (18 + n) % 32,
        "PAWR": (9 + n) % 32, "PSTR": (25 + n) % 32,
    } for n in range(players))
    depth_fields = [
        ("PGID", ea_tdb.FIELD_UINT, 16),
        ("PPOS", ea_tdb.FIELD_UINT, 5),
        ("ddep", ea_tdb.FIELD_UINT, 4),
    ]
    depth_rows = tuple({"PGID": 1000 + seed * 100 + n, "PPOS": n % 21, "ddep": n % 4}
                       for n in range(players))
    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        ("PLAY", tuple(play_fields), play_rows),
        ("DCHT", tuple(depth_fields), depth_rows),
    )))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.database_lane --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.database_lane",
        description="List and edit the EA TDB databases on an NCAA Football 09 (PS2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of row edits, as compose_recipe writes")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the build receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = DatabaseLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            if not arguments.source:
                parser.error("give --source DISC.iso, or --selftest")
            catalogue = lane.build_catalogue(
                Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        document = dict(catalogue.document)
        if arguments.out:
            Path(arguments.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        print("NCAA09_DATABASES databases=%d tables=%d records=%d fields=%d editable_rows=%d"
              % (document["databases"], document["tables"], document["records"],
                 document["fields"], document["editable_rows_listed"]))
        if not arguments.recipe:
            if arguments.destination:
                parser.error("--destination needs --recipe: there is nothing to write "
                             "without one")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        source = Path(arguments.source)
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("NCAA09_DATABASES_PLAN targets=%d bytes=%d"
                  % (len(plan.target_keys), plan.declared_bytes))
            return 0
        receipt = lane.build(source, Path(arguments.destination), recipe, catalogue)
        verdict = lane.verify(source, Path(arguments.destination), receipt)
        print(verdict.summary)
        if arguments.report:
            Path(arguments.report).write_text(
                json.dumps({"receipt": dict(receipt.document),
                            "verdict": {"passed": verdict.passed,
                                        "summary": verdict.summary,
                                        "document": dict(verdict.document)}},
                           indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8", newline="\n")
        print("NCAA09_DATABASES_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "DATABASE_CONTAINERS", "DEPTH_FIELDS", "DatabaseLane",
           "EDITABLE_FIELDS", "JERSEY_MAX", "KEEP_NUMBER", "LANE_ID", "LEAGUE_MEMBER",
           "MAX_DATABASE_TARGETS", "MAX_ROW_TARGETS", "PLAYER_FIELDS", "RATING_MAX",
           "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA", "WRITABLE_CONTAINER",
           "synthetic_roster_database"]


if __name__ == "__main__":
    raise SystemExit(_main())
