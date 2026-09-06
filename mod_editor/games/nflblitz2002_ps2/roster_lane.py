"""``roster.rst``: the one member on the disc whose name says roster, and its player names.

The file is a run of fixed blocks and nothing else [M]::

    block   u32 18, then 18 x 100-byte records          1,804 bytes
    record  char[32] first name, char[32] last name,    two NUL-terminated
            36 bytes of numbers                          ASCII fields, 0xCD-padded

Every identity below is exhaustive over the retail discs [M]:

===========================================================  ==========  ==========
identity                                                     2002        2003
===========================================================  ==========  ==========
member bytes                                                 73,964      75,768
``bytes % 1,804``                                            0           0
blocks (``bytes / 1,804``)                                   41          42
blocks whose header word is 18                               41 of 41    42 of 42
records whose two name fields are NUL-terminated ASCII       738 of 738  756 of 756
records whose byte +68 equals their block's ordinal          738 of 738  756 of 756
===========================================================  ==========  ==========

**The cross-check the block count earns.**  The disc carries one
``<two letters>_crowd.ini`` per NFL team and one ``<two letters>_glogo.rtd`` per
NFL team: 31 of each on the 2002 disc and 32 of each on the 2003 disc, and the
prefix the 2003 disc adds to both lists is ``ht`` -- the Houston Texans, the team
the NFL added for the 2002 season [M].  The roster's block count moves with them,
41 to 42.  So a block is a team's squad plus a fixed ten blocks the team lists do
not name, and the two counts agree on the one thing that changed between the
discs.  That is what a page may say; **which** block is which team is not
measured and is not claimed.

**What this lane writes, and what it does not.**  A name field is 32 bytes of
NUL-terminated ASCII padded with ``0xCD`` -- uninitialised MSVC heap fill, which
is what tells you the field is a fixed struct member and not a string table [M].
A replacement fits that field or is refused, so the member's length never
changes and it goes back into the stored ZIP where it lies.

The 36 numeric bytes are **listed and not written**.  Two of their columns have
exact identities -- byte +68 is the block ordinal, and byte +72 takes exactly 18
distinct values 0..17 -- and fourteen more sit in a 0..100 range that looks like
ratings [M].  Looking like ratings is not being ratings, so this lane names the
two it measured, publishes a column census for the rest, and offers no editor for
any of them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers, zip_lane

SCHEMA = "nflblitz2002_ps2_roster_names/v1"
GAME_ID = containers.GAME_ID
LANE_ID = "rosters.player_names"
CAPABILITY_ID = f"{GAME_ID.replace('_', '')}.{LANE_ID}"

#: The numeric columns this lane publishes a census of and never writes.
COLUMN_START = 64
COLUMN_END = containers.ROSTER_RECORD_BYTES


class RosterNameLane:
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Player names in roster.rst"
    classification = "offline-writer-proved"
    recipe_schema = SCHEMA
    validators = (f"tools/validate_{GAME_ID}_roster.sh", f"tools/validate_{GAME_ID}_roster.bat")
    fixed_allocation = True
    read_only = False

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        with containers.Disc(Path(source)) as disc:
            if progress is not None:
                progress(f"{containers.ROSTER_MEMBER}…")
            member = disc.archive().member(containers.ROSTER_MEMBER)
            payload = disc.member_bytes(containers.ROSTER_MEMBER)
            players = containers.read_roster(payload, containers.ROSTER_MEMBER)
            columns: Dict[str, Dict[str, int]] = {}
            for column in range(COLUMN_START, COLUMN_END):
                values = {player.offset: payload[player.offset + column] for player in players}
                seen = sorted(set(values.values()))
                columns[str(column)] = {"distinct": len(seen), "minimum": seen[0],
                                        "maximum": seen[-1]}
            team_byte_agrees = sum(1 for player in players if player.team_byte == player.block)
            for player in players:
                if len(targets) >= containers.MAX_TARGETS:
                    break
                targets.append(Target(
                    key=f"{player.block}:{player.slot}",
                    label=f"{player.first} {player.last}",
                    detail=f"block {player.block} slot {player.slot} · +{player.offset}",
                    budget=f"two {containers.ROSTER_NAME_BYTES}-byte fields, each "
                           f"{containers.ROSTER_NAME_BYTES - 1} characters and a terminator",
                    searchable=f"{player.first} {player.last} block {player.block}",
                    raw={"block": player.block, "slot": player.slot, "offset": player.offset,
                         "first": player.first, "last": player.last,
                         "team_byte": player.team_byte},
                    fields=(Field("first", "text", "First name",
                                  f"Latin-1, at most {containers.ROSTER_NAME_BYTES - 1} "
                                  f"characters."),
                            Field("last", "text", "Last name",
                                  f"Latin-1, at most {containers.ROSTER_NAME_BYTES - 1} "
                                  f"characters."))))
            crowd = len(disc.members_named(suffix=containers.CROWD_SUFFIX))
            logos = len(disc.members_named(suffix=containers.TEAM_TEXTURE_SUFFIXES[0]))
        blocks = len(players) // containers.ROSTER_RECORDS_PER_BLOCK
        document = {
            "schema": SCHEMA, "source": str(source), "member": containers.ROSTER_MEMBER,
            "bytes": member.size, "crc32": "%08x" % member.crc32,
            "sha256": zip_lane.sha256(payload),
            "block_bytes": containers.ROSTER_BLOCK_BYTES, "blocks": blocks,
            "records_per_block": containers.ROSTER_RECORDS_PER_BLOCK,
            "records": len(players),
            "records_whose_team_byte_equals_their_block": team_byte_agrees,
            "team_crowd_tables": crowd, "team_logo_dictionaries": logos,
            "blocks_minus_team_tables": blocks - crowd,
            "numeric_column_census": columns, "targets_listed": len(targets),
            "not_booted": zip_lane.NOT_BOOTED,
        }
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
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
            if len(raw) + 1 > containers.ROSTER_NAME_BYTES:
                return (f"A name field holds {containers.ROSTER_NAME_BYTES} bytes including its "
                        f"terminator and that value needs {len(raw) + 1}; shorten it to "
                        f"{containers.ROSTER_NAME_BYTES - 1} characters or fewer.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"target": edit.target_key}
            for key in ("first", "last"):
                if key in edit.values:
                    row[key] = str(edit.values[key])
            rows.append(row)
        return {"schema": SCHEMA, "lane": self.lane_id, "edits": rows}

    def _resolve(self, disc: containers.Disc, recipe: Mapping[str, Any],
                 catalogue: Catalogue) -> Dict[str, bytes]:
        edits = list(recipe.get("edits") or ())
        if not edits:
            raise Refusal("This recipe carries no edits; stage a name change before building.")
        payload = disc.member_bytes(containers.ROSTER_MEMBER)
        players = {f"{player.block}:{player.slot}": player
                   for player in containers.read_roster(payload, containers.ROSTER_MEMBER)}
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
                    payload = containers.write_roster_name(payload, player, which,
                                                           str(item[which]))
        return {containers.ROSTER_MEMBER: payload}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        with containers.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            ranges, rows = zip_lane.plan_ranges(disc, payloads)
        return Plan(self.lane_id,
                    tuple(str(item.get("target")) for item in recipe.get("edits", ())),
                    ranges, {"schema": SCHEMA, "lane": self.lane_id, "members": rows})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        zip_lane.check_destination(Path(source), Path(destination))
        with containers.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            iso_report, ranges, rows = zip_lane.build_replacements(disc, Path(destination),
                                                                   payloads)
        document = {"schema": SCHEMA, "lane": self.lane_id, "members": rows,
                    "iso_report": iso_report, "not_booted": zip_lane.NOT_BOOTED}
        return Receipt(SCHEMA, self.lane_id, str(source), str(destination), ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        outcome = zip_lane.verify_replacements(Path(source), Path(destination), receipt.document)
        failures = list(outcome["failures"])
        if outcome["passed"]:
            with containers.Disc(Path(destination)) as after:
                try:
                    players = containers.read_roster(after.member_bytes(containers.ROSTER_MEMBER),
                                                     containers.ROSTER_MEMBER)
                except containers.DiscError as exc:
                    failures.append(f"the rewritten roster no longer parses: {exc}")
                else:
                    bad = [p for p in players if p.team_byte != p.block]
                    if bad:
                        failures.append(f"{len(bad)} rewritten record(s) no longer carry their "
                                        f"block's ordinal at byte "
                                        f"+{containers.ROSTER_TEAM_BYTE}")
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
        path = Path(work_dir) / f"{GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        if not catalogue.targets:
            raise Refusal("The synthetic source carries no roster records.")
        return (Edit(catalogue.targets[0].key, {"first": "Fixture", "last": "Namefield"}),)


LANE = RosterNameLane()


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{GAME_ID}.roster_lane",
        description="Catalogue or edit the player names in an NFL Blitz 2002 (PS2) roster.")
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
                source = LANE.synthetic_source(Path(room))
                catalogue = LANE.build_catalogue(source)
                recipe = LANE.compose_recipe(LANE.conformance_edits(catalogue))
                plan = LANE.plan(source, recipe, catalogue)
                destination = Path(room) / "out.iso"
                receipt = LANE.build(source, destination, recipe, catalogue)
                verdict = LANE.verify(source, destination, receipt)
                if not verdict.passed:
                    print(f"error: {verdict.summary}", file=sys.stderr)
                    return 1
                print("SELFTEST lane=%s records=%d declared_ranges=%d declared_bytes=%d %s"
                      % (LANE.lane_id, len(catalogue.targets), len(plan.declared_ranges),
                         plan.declared_bytes, verdict.summary))
                return 0
        if not arguments.source:
            parser.error("give --source a disc image, or --selftest")
        catalogue = LANE.build_catalogue(Path(arguments.source))
        document = dict(catalogue.document)
        if arguments.recipe and arguments.destination:
            recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
            receipt = LANE.build(Path(arguments.source), Path(arguments.destination), recipe,
                                 catalogue)
            verdict = LANE.verify(Path(arguments.source), Path(arguments.destination), receipt)
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


__all__ = ["CAPABILITY_ID", "LANE", "LANE_ID", "RosterNameLane", "SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())
