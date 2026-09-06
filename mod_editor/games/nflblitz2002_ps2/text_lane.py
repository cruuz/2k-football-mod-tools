"""The text members of the ZIP, edited one line slot at a time.

72 members of the 2002 disc and 74 of the 2003 disc are plain text, in two
shapes [M]:

* **CRLF ASCII** -- the 31 (32) ``*_crowd.ini`` crowd tables, ``field.tab`` and,
  on the 2003 disc, ``credits.txt``.  Printable ASCII and whitespace on 32 of 32
  and 34 of 34 members, CRLF endings on every one.
* **Fixed 40-byte records** -- the 40 ``.trv`` trivia banks.  ``size % 40 == 0``
  on 40 of 40 members of each disc, every record printable ASCII padded with NUL.

A line owns its own bytes and nothing else.  A replacement must fit that span and
is padded to it -- with NUL in a ``.trv`` record and with spaces in a CRLF line --
so the member's length never changes, which is what lets it be written back into a
stored ZIP where it lies.  Its CRC-32 is then rewritten in all three places the
disc keeps it (see :mod:`.zip_lane`).

Three rows, one class, three pages: the crowd tables under *Text & Team
Identity*, ``field.tab`` under *Gameplay*, and the trivia banks under *Playbooks
& Plays*.  A row's members are the only thing that differs.
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

SCHEMA = "nflblitz2002_ps2_text_lines/v1"
GAME_ID = containers.GAME_ID
_PREFIX = GAME_ID.replace("_", "")


class TextLineLane:
    """One page's text members, each line a fixed-span slot."""

    recipe_schema = SCHEMA
    classification = "offline-writer-proved"
    fixed_allocation = True
    read_only = False

    def __init__(self, lane_id: str, surface: str, page: str, title: str, *,
                 suffix: str = "", exact: Sequence[str] = (), what: str = "",
                 validator: str = "") -> None:
        self.lane_id = lane_id
        self.capability_id = f"{_PREFIX}.{lane_id}"
        self.surface = surface
        self.page = page
        self.title = title
        self.suffix = suffix
        self.exact = tuple(exact)
        self.what = what
        self.validators = (f"tools/validate_{GAME_ID}_{validator}.sh",
                           f"tools/validate_{GAME_ID}_{validator}.bat")

    # -- catalogue ----------------------------------------------------------

    def members(self, disc: containers.Disc) -> Tuple[Any, ...]:
        return disc.members_named(suffix=self.suffix, exact=self.exact)

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        rows: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        total_slots = 0
        with containers.Disc(Path(source)) as disc:
            found = self.members(disc)
            for number, member in enumerate(found):
                if progress is not None:
                    progress(f"{member.name} ({number + 1} of {len(found)})…")
                try:
                    payload = disc.member_bytes(member.name)
                    slots = containers.read_line_slots(member.name, payload)
                except containers.DiscError as exc:
                    refusals.append({"where": member.name, "sentence": str(exc)})
                    continue
                total_slots += len(slots)
                rows.append({"member": member.name, "bytes": member.size,
                             "kind": containers.text_kind(member.name), "lines": len(slots),
                             "crc32": "%08x" % member.crc32,
                             "sha256": zip_lane.sha256(payload)})
                for slot in slots:
                    if len(targets) >= containers.MAX_TARGETS:
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
        document = {"schema": SCHEMA, "source": str(source), "lane": self.lane_id,
                    "what": self.what, "members": len(rows), "lines": total_slots,
                    "targets_listed": len(targets), "rows": rows, "refusals": refusals,
                    "not_booted": zip_lane.NOT_BOOTED}
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

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
        return {"schema": SCHEMA, "lane": self.lane_id,
                "edits": [{"target": edit.target_key, "text": str(edit.values.get("text", ""))}
                          for edit in edits]}

    def _resolve(self, disc: containers.Disc, recipe: Mapping[str, Any],
                 catalogue: Catalogue) -> Dict[str, bytes]:
        edits = list(recipe.get("edits") or ())
        if not edits:
            raise Refusal("This recipe carries no edits; stage a line change before building.")
        payloads: Dict[str, bytes] = {}
        for item in edits:
            target = catalogue.target(str(item.get("target", "")))
            member = str(target.raw["member"])
            if member not in payloads:
                payloads[member] = disc.member_bytes(member)
            slots = containers.read_line_slots(member, payloads[member])
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
            payloads[member] = containers.write_line_slot(payloads[member], slot,
                                                          str(item.get("text", "")))
        return payloads

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        with containers.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            ranges, rows = zip_lane.plan_ranges(disc, payloads)
        return Plan(self.lane_id, tuple(str(item.get("target")) for item in recipe.get("edits", ())),
                    ranges, {"schema": SCHEMA, "lane": self.lane_id, "members": rows})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        zip_lane.check_destination(Path(source), Path(destination))
        with containers.Disc(Path(source)) as disc:
            payloads = self._resolve(disc, recipe, catalogue)
            iso_report, ranges, rows = zip_lane.build_replacements(disc, Path(destination), payloads)
        document = {"schema": SCHEMA, "lane": self.lane_id, "members": rows,
                    "iso_report": iso_report, "not_booted": zip_lane.NOT_BOOTED}
        return Receipt(SCHEMA, self.lane_id, str(source), str(destination), ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        outcome = zip_lane.verify_replacements(Path(source), Path(destination), receipt.document)
        summary = ("%d member(s) replaced, %d checked, %d byte-identical; the index and the "
                   "archive agree" % (outcome["members_replaced"], outcome["members_checked"],
                                      outcome["members_byte_identical"]))
        if not outcome["passed"]:
            summary = "; ".join(outcome["failures"][:3])
        return Verdict(bool(outcome["passed"]), summary, outcome)

    # -- CI -----------------------------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if int(target.raw["span"]) >= 4:
                return (Edit(target.key, {"text": "FIX1"}),)
        raise Refusal("The synthetic source carries no line slot of four bytes or more.")


CROWD_LANE = TextLineLane(
    "identity.crowd_tables", "colors", "identity", "The per-team crowd tables",
    suffix=containers.CROWD_SUFFIX, validator="text",
    what="One CRLF ASCII table per NFL team; the 2003 disc adds the Houston Texans.")
FIELD_LANE = TextLineLane(
    "gameplay.field_table", "gameplay_tuning_sliders", "gameplay", "field.tab",
    exact=(containers.FIELD_TABLE,), validator="text",
    what="The one gameplay table on the disc, CRLF ASCII with a leading comment line.")
TRIVIA_LANE = TextLineLane(
    "playbooks.trivia_banks", "scripts_config", "playbooks", "The trivia banks",
    suffix=containers.TRIVIA_SUFFIX, exact=containers.LOOSE_TEXT, validator="text",
    what="40 banks of fixed 40-byte NUL-padded ASCII records, and the 2003 disc's credits.")

LANES = (CROWD_LANE, FIELD_LANE, TRIVIA_LANE)
_BY_NAME = {"crowd": CROWD_LANE, "field": FIELD_LANE, "trivia": TRIVIA_LANE}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{GAME_ID}.text_lane",
        description="Catalogue or edit the text members of an NFL Blitz 2002 (PS2) disc.")
    parser.add_argument("--lane", choices=sorted(_BY_NAME), default="crowd")
    parser.add_argument("--source")
    parser.add_argument("--destination")
    parser.add_argument("--recipe")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = _BY_NAME[arguments.lane]
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


__all__ = ["CROWD_LANE", "FIELD_LANE", "LANES", "SCHEMA", "TRIVIA_LANE", "TextLineLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
