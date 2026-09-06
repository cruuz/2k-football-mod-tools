"""The disc's EA TDB databases: catalogued table by table, and now edited.

Madden 09's team, roster and tuning data does not live in one file.  It lives
in **EA TDB databases packed as members of ``TERF`` containers** -- 235 of them
in ``DB_TEAMS.DAT``, 15 in ``TEMPLATE.DAT`` and 104 in ``GAMEDATA.DAT`` [M] --
plus one bare database on the disc, ``/DATA/STRMDATA.DB``, which carries no
container around it at all [M].

This lane is the shared
:class:`mod_editor.games._lanes.tdb_records.TdbRecordLane` -- the same one NCAA
Football 09's roster, identity and playbook rows stand on, because a record edit
inside a container member is one lane and a field map is what differs between
games.  It opens each database through
:mod:`mod_editor.games._formats.ea_tdb` and says what is inside: the tables,
how many records each holds against its capacity, the record stride, and every
field's name, type and bit width.  For the databases it can also **edit**, it
goes one step further and lists the rows themselves.

What it edits
-------------

Only ``/DATA/DB_TEAMS.DAT``, and inside it only two tables:

* ``PLAY`` -- one row per player: first and last name, jersey number, age and
  twenty numeric ratings.  The exact list is :data:`PLAYER_FIELDS`; it is a
  list and not "whatever is numeric" on purpose, so what this page offers is
  something a reader can check rather than a shape that drifts.
* ``TEAM`` -- the nickname, city, abbreviation and short name a team is drawn
  under (:data:`TEAM_FIELDS`).

Everything else on the disc stays read-only, and each has a reason:

* ``TEMPLATE.DAT`` and ``GAMEDATA.DAT`` are **named in the preload caches**
  ``/DATA/FE.QKL`` and ``/DATA/GAME.QKL``, and the first 256 bytes of each
  appear verbatim inside the cache that names them [M].  Editing one copy and
  not the other would leave the game reading whichever it reached first, so
  this lane refuses both rather than writing half a change.  ``DB_TEAMS.DAT``
  is named in neither [M], which is what makes it safe to write -- and the
  catalogue re-reads that list off the user's own image
  (:func:`containers.preload_names`) rather than trusting a table written down
  here.
* ``STRMDATA.DB`` is a 5 MB bare database of league and presentation tables
  with no ``PLAY`` table at all [M]; it is outside what this page is for.

Why a record edit is a bounded write
------------------------------------

A TDB field owns a fixed run of bits inside a fixed-stride record, so writing
one **cannot change a length**: the database comes back the same size, the
container member it sits in comes back the same size, and the ISO extent it
came from is rewritten in place.  A rewrite that would change any of those is
refused rather than allowed to move bytes this lane cannot account for.

The four checksums EA stores in a TDB header are recomputed on every write
(``ea_tdb.recompute_crcs``) and re-derived from the destination's own bytes by
the verifier (``ea_tdb.verify_crcs``).  The algorithm is proved against 4,806
checksum slots on the owner's retail disc; see :mod:`ea_tdb`.

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.  No emulator has booted
a rebuilt Madden 09 disc, and this module does not claim one has.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.team_data --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_tdb, ea_terf  # noqa: F401  (ea_terf: re-export)
from mod_editor.games._lanes.tdb_records import (
    FieldSpec,
    KEEP_NUMBER,
    TdbRecordLane,
    editor_fields,
    number_bound,
    row_values,
    text_budget,
)
from mod_editor.games.contract import Catalogue, Edit, Field, Refusal  # noqa: F401

from . import containers

import argparse
import json
import sys

CAPABILITY_ID = "madden09ps2.players.team_databases"
LANE_ID = "players_rosters.team_databases"
SCHEMA = "madden09_ps2_team_database_inventory/v1"
RECIPE_SCHEMA = "madden09_ps2_team_database_edit/v1"
RECEIPT_SCHEMA = "madden09_ps2_team_database_write/v1"

#: The containers whose members are EA TDB databases [M].  Named rather than
#: discovered so a 415 MB speech container is never opened looking for one.
TDB_CONTAINERS = (
    containers.TEAM_DATABASE_CONTAINER,
    containers.TEMPLATE_CONTAINER,
    containers.GAME_DATA_CONTAINER,
)

#: The one container this lane writes to.  See the module docstring: the other
#: two are duplicated inside ``FE.QKL`` and editing them would leave a stale
#: copy behind.
WRITABLE_CONTAINER = containers.TEAM_DATABASE_CONTAINER

#: Which preload cache names each container this lane will not write [M].
PRELOAD_COPIES: Mapping[str, Tuple[str, ...]] = {
    containers.TEMPLATE_CONTAINER: ("FE.QKL",),
    containers.GAME_DATA_CONTAINER: ("GAME.QKL", "FE.QKL"),
}

#: How many database targets are listed.  A retail disc has 355 TDB members
#: [M], so the cap is generous; the document's totals are complete regardless.
MAX_TARGETS = 2000

#: How many editable rows are listed.  ``DB_TEAMS.DAT`` holds 235 databases of
#: roughly 53 players and one team each -- about 12,700 rows [M].
MAX_ROW_TARGETS = 20000

#: The tables whose rows become editable, in the order a page shows them.
EDITABLE_TABLES = ("TEAM", "PLAY")

#: The scale Madden's numeric ratings are on [S].  The fields are seven bits
#: wide and would hold 127, but a rating above 99 is not a value the game's own
#: data ever carries, so the editor stops at 99 rather than at the bit width.
RATING_MAX = 99

#: The range an NFL jersey number covers [S].  ``PJEN`` is seven bits wide.
JERSEY_MAX = 99

#: How a row target's key is spelled: ``row:<iso path>#<member>:<table>:<record>``.
ROW_PREFIX = "row:"


def _rating(name: str, label: str) -> FieldSpec:
    return (name, label, f"{label} rating, 0 to {RATING_MAX}.", RATING_MAX)


#: The ``PLAY`` fields this lane offers, in the order a page draws them.  Each
#: is ``(field name, label, help, maximum)``; ``maximum`` of ``None`` means the
#: field's own bit width is the bound.  A field the table does not declare is
#: skipped, so a database with a different schema simply offers less.
PLAYER_FIELDS: Tuple[Tuple[str, str, str, Optional[int]], ...] = (
    ("PFNA", "First name", "The player's first name.", None),
    ("PLNA", "Last name", "The player's last name.", None),
    ("PJEN", "Jersey number", f"Squad number, 0 to {JERSEY_MAX}.", JERSEY_MAX),
    ("PAGE", "Age", "Age in years, as the six-bit field stores it.", None),
    ("PHGT", "Height (inches)",
     "Height in inches, as the seven-bit field stores it: every retail record holds "
     "60 to 84, and the executable reads it into the runtime height it compares with "
     "75.0 inches.", None),
    ("PWGT", "Weight less 160 (lb)",
     "Weight in pounds MINUS 160, the eight-bit field's own encoding: 0 means 160 lb "
     "and 206, the largest retail value, means 366. The same encoding is what the "
     "sibling Madden 08 roster compiler writes and has seen load in PCSX2, and the "
     "executable's runtime weight thresholds are 180, 222 and 310 lb.", None),
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
    _rating("PKPR", "Kick power"),
    _rating("PKAC", "Kick accuracy"),
    _rating("PMOR", "Morale"),
)

#: The ``TEAM`` fields this lane offers.  Which of the four holds which kind of
#: name was settled by reading all 32 of a retail disc's team records and
#: seeing what each column consistently was -- a nickname, a city, a two-to-
#: five character code, and a familiar short form -- so the labels are
#: measured, not guessed [M].  No value from that reading is stored here.
TEAM_FIELDS: Tuple[Tuple[str, str, str, Optional[int]], ...] = (
    ("TDNA", "Nickname", "The name the team is drawn under, e.g. its mascot.", None),
    ("TLNA", "City", "The city or region the team plays for.", None),
    ("TSNA", "Abbreviation", "The two-to-five letter short code.", None),
    ("TMNC", "Short name", "The familiar short form commentary uses.", None),
)

#: Both lists, keyed by the table they belong to.
EDITABLE_FIELDS: Mapping[str, Tuple[Tuple[str, str, str, Optional[int]], ...]] = {
    "PLAY": PLAYER_FIELDS,
    "TEAM": TEAM_FIELDS,
}

#: Both lists, keyed by the table they belong to.
EDITABLE_FIELDS: Mapping[str, Tuple[FieldSpec, ...]] = {
    "PLAY": PLAYER_FIELDS,
    "TEAM": TEAM_FIELDS,
}


class TeamDataError(Refusal):
    """This lane could not do what was asked; the sentence says why."""


def fields_for(table: ea_tdb.TdbTable) -> Tuple[Field, ...]:
    """The editor controls one row of *table* offers, in list order.

    The rule is the shared :func:`editor_fields`; this is the spelling callers
    in this package have always used, with this game's field map bound in.
    """

    return editor_fields(table, EDITABLE_FIELDS.get(table.name, ()))


def row_key(iso_path: str, member: int, table: str, record: int) -> str:
    """The target key for one record of one table of one container member."""

    return TeamDataLane().row_key(iso_path, member, table, record)


def parse_row_key(key: str) -> Tuple[str, int, str, int]:
    """``row:/DATA/DB_TEAMS.DAT#12:PLAY:34`` back into its four parts."""

    path, member, table, record = TeamDataLane().parse_row_key(key)
    if member is None:
        raise TeamDataError(
            f"{key!r} names no member; every database this lane writes is a member of "
            f"{WRITABLE_CONTAINER}."
        )
    return path, member, table, record


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> dict:
    """Re-derive, from the two images alone, that the build did what it claimed.

    The check itself is :meth:`TdbRecordLane.verify_build`, shared with NCAA
    Football 09's three record rows; this is the module-level spelling a caller
    in this package uses.
    """

    return TeamDataLane().verify_build(Path(source), Path(destination), receipt_document)


class TeamDataLane(TdbRecordLane):
    """Every EA TDB database on the disc, and the rows of the one it writes."""

    discs = containers

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Team and roster databases"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_team_data.sh",
        "tools/validate_madden09_ps2_team_data.bat",
    )

    tdb_containers = TDB_CONTAINERS
    writable_containers = (WRITABLE_CONTAINER,)
    bare_databases = (containers.STREAM_DATABASE_FILE,)
    editable_tables = EDITABLE_TABLES
    editable_fields = EDITABLE_FIELDS
    max_targets = MAX_TARGETS
    max_row_targets = MAX_ROW_TARGETS
    row_prefix = ROW_PREFIX
    #: This lane refuses a container a cache names rather than rewriting the
    #: copy, so the shrink allowance never applies.
    cached_member_may_shrink = False

    def read_only_reason(self, container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        caches = (cached or {}).get(container_name.upper()) or PRELOAD_COPIES.get(
            container_name.upper())
        if caches:
            named = " and ".join(f"/DATA/{item}" for item in caches)
            return (
                f"{container_name} is named in {named}, the preload cache, which carries a "
                f"copy of at least some of what it names and which this lane does not "
                f"rewrite; editing one copy and not the other would leave the game reading "
                f"whichever it reached first."
            )
        return (
            f"{container_name} is outside what this page edits: it writes the per-team "
            f"roster databases in {WRITABLE_CONTAINER}."
        )

    def build_catalogue(self, source: Path, *, progress=None) -> Catalogue:
        """The base's catalogue, after refusing an image that caches what it writes."""

        image = self.discs.open_disc(Path(source))
        cached = self.discs.preload_names(image)
        if WRITABLE_CONTAINER.upper() in {name.upper() for names in cached.values()
                                          for name in names}:
            raise TeamDataError(
                f"{WRITABLE_CONTAINER} is named in "
                + " and ".join(sorted(cache for cache, names in cached.items()
                                      if WRITABLE_CONTAINER.upper()
                                      in {name.upper() for name in names}))
                + " on this image, and a container a preload cache carries is not one this "
                  "lane rewrites; it edits nothing here."
            )
        return super().build_catalogue(source, progress=progress)

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        if table == "PLAY":
            name = " ".join(str(values.get(key, "")).strip()
                            for key in ("PFNA", "PLNA")).strip()
            return name or f"member {member} · player {index}"
        name = " ".join(str(values.get(key, "")).strip()
                        for key in ("TLNA", "TDNA")).strip()
        return name or f"member {member} · team {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        if table == "PLAY":
            parts = []
            if "PJEN" in values:
                parts.append(f"#{values['PJEN']}")
            if "POVR" in values:
                parts.append(f"OVR {values['POVR']}")
            if "PAGE" in values:
                parts.append(f"age {values['PAGE']}")
            return " · ".join(parts)
        return " · ".join(str(values[key]) for key in ("TSNA",) if key in values)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-teamdata-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(tdb_member=synthetic_database()))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """One name, one number and one rating, on the synthetic disc's own rows."""

        player = team = None
        for target in catalogue.targets:
            if not target.key.startswith(ROW_PREFIX):
                continue
            _path, _member, table, _record = self.parse_row_key(target.key)
            if table == "PLAY" and player is None:
                player = target
            elif table == "TEAM" and team is None:
                team = target
        if player is None or team is None:
            raise Refusal(
                "the synthetic database carries no PLAY and TEAM rows to edit; rebuild the "
                "fixture from synthetic_database()."
            )
        return (
            Edit(player.key, {"PFNA": "Kit", "PJEN": 7, "POVR": 88}, note="conformance"),
            Edit(team.key, {"TDNA": "Testers"}, note="conformance"),
        )


def synthetic_database() -> bytes:
    """A small EA TDB built from the format's own rules, for the synthetic disc.

    Two tables named as the real ones are, carrying the fields this lane edits
    so the conformance harness exercises a name, a number and a rating, and
    with bit widths that deliberately straddle byte boundaries so a writer that
    mis-orders the bit packing is visibly wrong.  Nothing here comes from a
    game: the names are invented and the numbers are a counting ramp.

    The four checksums are written from the result's own bytes, so this fixture
    is a database that passes :func:`ea_tdb.verify_crcs` -- which is what makes
    it a fair test of a writer that has to keep them passing.
    """

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        (
            "TEAM",
            (
                ("TGID", ea_tdb.FIELD_UINT, 11),
                ("TDNA", ea_tdb.FIELD_STRING, 17 * 8),
                ("TLNA", ea_tdb.FIELD_STRING, 18 * 8),
                ("TSNA", ea_tdb.FIELD_STRING, 7 * 8),
                ("TMNC", ea_tdb.FIELD_STRING, 17 * 8),
                ("TWIN", ea_tdb.FIELD_SINT, 5),
            ),
            (
                {"TGID": 1, "TDNA": "SYNTHETIC-A", "TLNA": "Nowhere",
                 "TSNA": "SYN", "TMNC": "Synths", "TWIN": 3},
                {"TGID": 900, "TDNA": "SYNTHETIC-B", "TLNA": "Elsewhere",
                 "TSNA": "SYB", "TMNC": "Others", "TWIN": -4},
            ),
        ),
        (
            "PLAY",
            (
                ("PGID", ea_tdb.FIELD_UINT, 15),
                ("PFNA", ea_tdb.FIELD_STRING, 11 * 8),
                ("PLNA", ea_tdb.FIELD_STRING, 13 * 8),
                ("PJEN", ea_tdb.FIELD_UINT, 7),
                ("PAGE", ea_tdb.FIELD_UINT, 6),
                ("POVR", ea_tdb.FIELD_UINT, 7),
                ("PSPD", ea_tdb.FIELD_UINT, 7),
                ("PAWR", ea_tdb.FIELD_UINT, 7),
                ("PWGT", ea_tdb.FIELD_UINT, 9),
            ),
            tuple({"PGID": 16384 + n, "PFNA": "Synth", "PLNA": f"Player{n}",
                   "PJEN": 10 + n, "PAGE": 22 + n, "POVR": 40 + n,
                   "PSPD": 50 + n, "PAWR": 60 + n, "PWGT": 180 + n}
                  for n in range(4)),
        ),
    )))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.team_data --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.team_data",
        description="List and edit the EA TDB databases on a Madden NFL 09 (PS2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of row edits, as compose_recipe writes")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the build receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = TeamDataLane()
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
        print("TEAM_DATA databases=%d tables=%d records=%d fields=%d editable_rows=%d"
              % (document["databases"], document["tables"], document["records"],
                 document["fields"], document["editable_rows_listed"]))
        if not arguments.recipe:
            if arguments.destination:
                parser.error("--destination needs --recipe: there is nothing to write without one")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        source = Path(arguments.source)
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("TEAM_DATA_PLAN targets=%d bytes=%d"
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
        print("TEAM_DATA_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "EDITABLE_FIELDS", "EDITABLE_TABLES", "JERSEY_MAX",
           "KEEP_NUMBER", "LANE_ID", "MAX_ROW_TARGETS", "MAX_TARGETS", "PLAYER_FIELDS",
           "PRELOAD_COPIES", "RATING_MAX", "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "ROW_PREFIX",
           "SCHEMA", "TDB_CONTAINERS", "TEAM_FIELDS", "TeamDataError", "TeamDataLane",
           "WRITABLE_CONTAINER", "fields_for", "number_bound", "parse_row_key", "row_key",
           "row_values", "synthetic_database", "text_budget", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
