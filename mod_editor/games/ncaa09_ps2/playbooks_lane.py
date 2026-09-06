"""The 136 playbooks and the shared play library: their play names, renamed.

``/DATA/GAMEDATA.DAT`` holds **137 EA TDB databases at members 4 to 140** [M]:
one shared play library and 136 playbooks, all one schema shape.  **Their
nineteen tables are name-for-name identical to Madden NFL 09's nineteen** --
``ARTL PLCM FORM PBAU PBFM PBPL PBST PLRD PLYS PSAL SETL SETG SPKF PLYL PBAI
PLPD SGF\\x00 SPKG SETP``, zero only here, zero only there.  It is the closest
the two discs come anywhere.

**One field is why the Madden writer does not port.**  Madden's ``PBPL`` carries
a play ``name`` and this one's does not: ``PBPL`` here is 5 fields and 8 bytes
against Madden's 6 and 28.  So the play names live in ``PLYL`` (a 192-bit
string) instead, and five widths shift [M].  That is a **new field map, not new
code**, which is exactly what the shared
:class:`mod_editor.games._lanes.tdb_records.TdbRecordLane` is for.

Where the names are, measured across the 137 databases [M]:

=============  ======  =====================================
table           rows   ``name`` width on this disc
=============  ======  =====================================
``PLYL``        4,322  192 bits (24 bytes)
``PBST``        3,266  128 bits (16)
``PBFM``        2,356  264 bits (33)
``SGF\\x00``     2,086  32 bits (4)
``SPKF``        1,510  112 bits (14)
``SETL``          236  144 bits (18)
``FORM``           41  160 bits (20)
=============  ======  =====================================

**13,817 name-bearing rows**, and **2,301 of the 2,603 tables are packed exactly
full** -- so a rename is possible and an insertion is not.  This lane renames;
it never adds or removes a row, and the refusal for an attempt says which.

Why the write is bounded, and why the caches are cheap here
-----------------------------------------------------------

A TDB field owns a fixed run of bits in a fixed-stride record, so the
decompressed database comes back its exact size.  And **every one of
``GAMEDATA.DAT``'s 150 members is stored, codec 0** [M] -- there is no
compression to re-pack -- so a record edit cannot change a member's stored size
either.  The container's directory therefore never moves, which matters because
``GAMEDATA.DAT`` **is** named by two of the three preload caches: its directory
is copied twice and fifteen of its members once each [M].  Those fifteen include
members 4, 33, 94 and 133 -- real playbooks -- and an edit to one of them
rewrites its cache copy at the same length rather than being refused.  The lane
does not rely on the argument: it prices the re-pack before writing and rewrites
every copy the edit disturbs.

The four checksums EA stores in each database are recomputed on every write and
re-derived from the destination's own bytes by the verifier.

**Nothing here has been seen in a running game.**

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.playbooks_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_tdb
from mod_editor.games._lanes.tdb_records import FieldSpec, TdbRecordLane
from mod_editor.games.contract import Catalogue, Edit, Refusal

from . import containers

CAPABILITY_ID = "ncaa09ps2.playbooks.databases"
LANE_ID = "playbooks.databases"
SCHEMA = "ncaa09_ps2_playbook_inventory/v1"
RECIPE_SCHEMA = "ncaa09_ps2_playbook_edit/v1"
RECEIPT_SCHEMA = "ncaa09_ps2_playbook_write/v1"

#: The one container this lane reads and writes.
WRITABLE_CONTAINER = containers.GAME_DATA_CONTAINER

#: The nineteen table names a playbook database declares [M].  A member that
#: does not carry them is not a playbook and offers no row.
PLAYBOOK_TABLES: Tuple[str, ...] = (
    "ARTL", "PLCM", "FORM", "PBAU", "PBFM", "PBPL", "PBST", "PLRD", "PLYS",
    "PSAL", "SETL", "SETG", "SPKF", "PLYL", "PBAI", "PLPD", "SGF\x00", "SPKG", "SETP",
)

#: How many tables a member must share with :data:`PLAYBOOK_TABLES` to count as
#: a playbook.  All nineteen on this disc; the threshold is below that so a
#: re-cut that dropped an empty table still opens.
PLAYBOOK_TABLE_FLOOR = 15

#: The tables that carry a name, in the order a page shows them [M].
NAMED_TABLES: Tuple[str, ...] = ("PLYL", "PBST", "PBFM", "SGF\x00", "SPKF", "SETL", "FORM")

#: How many rows are listed as editable targets.  The disc carries 13,817
#: name-bearing rows [M]; the cap is above that so a retail disc lists them all.
MAX_ROW_TARGETS = 20000


def _name(label: str, what: str) -> FieldSpec:
    return ("name", label, what, None)


#: The field map.  One field per table -- the name -- because a rename is what
#: this page is, and every other column of a play is a number whose meaning is
#: not established here.
EDITABLE_FIELDS: Mapping[str, Tuple[FieldSpec, ...]] = {
    "PLYL": (_name("Play name",
                   "The play's name, as the play list carries it. On Madden 09 this "
                   "field is in PBPL; on this disc PBPL has no name at all, which is "
                   "the one thing that stops that writer porting."),),
    "PBST": (_name("Set name", "The name of a set of plays inside a formation."),),
    "PBFM": (_name("Formation name", "The formation's name."),),
    "SGF\x00": (_name("Sub-formation name", "The four-character sub-formation tag."),),
    "SPKF": (_name("Package name", "The personnel package's name."),),
    "SETL": (_name("Set list name", "The name of a list of sets."),),
    "FORM": (_name("Formation group name", "The formation group's name."),),
}

#: What the page says about the ceiling every book on this disc already sits at.
PACKED_FULL_NOTE = (
    "2,301 of the 2,603 tables across the 137 databases are packed exactly full, so a "
    "rename is possible on this disc and an insertion is not: there is no spare row to "
    "add a play into. This lane renames a row that exists and never adds or removes one."
)


class PlaybooksLane(TdbRecordLane):
    """Every playbook database on the disc, and the names inside the ones it writes."""

    discs = containers

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "scripts_config"
    page = "playbooks"
    title = "Playbooks and play names"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_playbooks.sh",
        "tools/validate_ncaa09_ps2_playbooks.bat",
    )

    tdb_containers = (WRITABLE_CONTAINER,)
    writable_containers = (WRITABLE_CONTAINER,)
    editable_tables = NAMED_TABLES
    editable_fields = EDITABLE_FIELDS
    max_targets = 200
    max_row_targets = MAX_ROW_TARGETS
    #: Every member of this container is stored, so a record edit cannot change
    #: a stored size and a cached copy is always rewritten at its own length.
    cached_member_may_shrink = False

    def member_is_editable(self, container_name: str, member: Optional[int],
                           database: ea_tdb.TdbDatabase) -> bool:
        """Whether this member is a playbook, read off its own table names."""

        return len(set(database.table_names) & set(PLAYBOOK_TABLES)) >= PLAYBOOK_TABLE_FLOOR

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        name = str(values.get("name") or "").strip()
        shown = table.replace("\x00", "")
        return name or f"book {member} · {shown} {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        return table.replace("\x00", "")

    def row_budget(self, container_name: str) -> str:
        return ("The name is written into the field it already occupies and padded out "
                "with the terminator. Every member of this container is stored, so the "
                "database, the member, the container and the image all keep their exact "
                "size. No row is added or removed: every table here is packed full.")

    def build_catalogue(self, source: Path, *, progress=None) -> Catalogue:
        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["named_tables"] = [table.replace("\x00", "") for table in NAMED_TABLES]
        document["packed_full"] = PACKED_FULL_NOTE
        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-playbooks-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(
            playbook_members=[synthetic_playbook(seed=0), synthetic_playbook(seed=1)]))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """One play rename, on the fixture's own first named row."""

        for target in catalogue.targets:
            if target.key.startswith(self.row_prefix):
                return (Edit(target.key, {"name": "Renamed"}, note="conformance"),)
        raise Refusal(
            "the synthetic playbook carries no named row to rename; rebuild the fixture "
            "from synthetic_playbook()."
        )


def synthetic_playbook(*, seed: int = 0, plays: int = 4) -> bytes:
    """A playbook database in this disc's shape, built from the format's own rules.

    The seven name-bearing tables at the widths this disc declares, so a writer
    that mis-orders the bit packing or overruns a name field is visibly wrong.
    The four-character table name ``SGF\\x00`` is here too, because it is a real
    table name on both discs and a fixture without it would not exercise the
    shared reader's ``decode_name``.  Nothing here comes from a game.
    """

    def table(name: str, width_bits: int, rows: int, prefix: str):
        return (name,
                (("name", ea_tdb.FIELD_STRING, width_bits),
                 ("plid", ea_tdb.FIELD_UINT, 12)),
                tuple({"name": f"{prefix}{index}", "plid": seed * 100 + index}
                      for index in range(rows)))

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        table("PLYL", 192, plays, "Play"),
        table("PBST", 128, 2, "Set"),
        table("PBFM", 264, 2, "Form"),
        table("SGF\x00", 32, 2, "S"),
        table("SPKF", 112, 2, "Pkg"),
        table("SETL", 144, 1, "List"),
        table("FORM", 160, 1, "Group"),
        # Twelve more tables so the member passes the playbook floor the same
        # way a real one does: nineteen table names, of which seven carry a name.
        ("ARTL", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 1},)),
        ("PLCM", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 2},)),
        ("PBAU", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 3},)),
        ("PBPL", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 4},)),
        ("PLRD", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 5},)),
        ("PLYS", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 6},)),
        ("PSAL", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 7},)),
        ("SETG", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 8},)),
        ("PBAI", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 9},)),
        ("PLPD", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 10},)),
        ("SPKG", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 11},)),
        ("SETP", (("plid", ea_tdb.FIELD_UINT, 12),), ({"id": 12},)),
    )))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.playbooks_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.playbooks_lane",
        description="List and rename the plays in an NCAA Football 09 (PS2) disc's "
                    "137 playbook databases.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of rename edits")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = PlaybooksLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                destination = Path(room) / "written.iso"
                receipt = lane.build(source, destination, lane.compose_recipe(edits),
                                     catalogue)
                verdict = lane.verify(source, destination, receipt)
                print("NCAA09_PLAYBOOKS_SELFTEST %s"
                      % ("PASS" if verdict.passed else "FAIL"))
                if not verdict.passed:
                    print(verdict.summary, file=sys.stderr)
                    return 1
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
        print("NCAA09_PLAYBOOKS books=%d tables=%d records=%d fields=%d named_rows=%d"
              % (document["databases"], document["tables"], document["records"],
                 document["fields"], document["editable_rows_listed"]))
        if arguments.selftest or not arguments.recipe:
            if arguments.destination and not arguments.selftest:
                parser.error("--destination needs --recipe")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        source = Path(arguments.source)
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("NCAA09_PLAYBOOKS_PLAN targets=%d bytes=%d"
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
        print("NCAA09_PLAYBOOKS_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "EDITABLE_FIELDS", "LANE_ID", "MAX_ROW_TARGETS",
           "NAMED_TABLES", "PACKED_FULL_NOTE", "PLAYBOOK_TABLES", "PLAYBOOK_TABLE_FLOOR",
           "PlaybooksLane", "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA",
           "WRITABLE_CONTAINER", "synthetic_playbook"]


if __name__ == "__main__":
    raise SystemExit(_main())
