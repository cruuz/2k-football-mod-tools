#!/usr/bin/env python3
"""b778 fa4: grow the main ROST arena so every dated free-agent candidate fits.

The released main ROST is a fixed native resource. The dated refresh can only add a new identity to a vacant
create record, and the two-team import floor plus a Create Player margin must survive. fa3 proved 19 of its 561
candidates fit at the safe margin; this tool reserves the 0xB0000-byte capacity arena (the same version-18
schema, a larger declared length and a block at the end) and then writes the refresh into the extra vacancies.

  python3 tools/b77/b778_fa4_capacity.py merge --edits IN.json --base ROSTER --out OUT.json

``--base`` is the refresh's pinned base: a disc image whose main roster precedes the refresh (the Oct 13 pack
disc) or a bare 0x90F60-byte body. Nothing is written except ``--out``. The output carries
``free_agent_capacity.records`` for the build's paired-arena step; the plan's new rows are addressed to the
grown body this tool proves, so the build must use that same base.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_college_check as college_check  # noqa: E402
from mod_editor.core import nfl2k5_roster_arena as arena  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_spare_capacity as capacity  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("b778_fa3", ROOT / "tools/b77/b778_fa3_free_agent_depth.py")
fa3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa3)

SCHEMA = "nfl2k5.free_agent_capacity.v1"
DEFAULT_ARENA = arena.CAPACITY_ARENA_SIZE


class CapacityError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CapacityError(message)


def grow(base_body, records, *, arena_size=DEFAULT_ARENA):
    require(arena_size == DEFAULT_ARENA, "only the 0xB0000 capacity arena is implemented")
    require(len(base_body) == capacity.BODY_SIZE, "the capacity base must be the 0x90F60-byte main ROST body")
    grown, receipt = arena.migrate(bytes(base_body), reserves_16=False, capacity_records=records)
    require(len(grown) == arena_size + 0x40, "capacity body has the wrong length")
    return grown, receipt


def floor_shortfall(base, plan, data, margin):
    """Records the retail base's import floor had to insert at fa3's fitted count."""
    count, body, floor = fa3.fit(base, plan, data, margin)
    return count, int(floor.get("added_records") or 0), floor


def merge(args):
    data = fa3.load(args.data)
    edits = json.loads(Path(args.edits).read_text(encoding="utf-8"))
    base = fa3.read_base(args.base)
    plan = edits["roster_refresh"]
    final = int(edits.get("fa3_free_agent_depth", {}).get("candidates") or len(data["players"]))
    fitted, floor_added, floor = floor_shortfall(base, plan, data, args.margin)
    require(fitted < final, f"this base already fits all {final} candidates")
    records = (final - fitted) + floor_added
    if getattr(args, "records", 0):
        require(args.records >= records, f"--records {args.records} is smaller than the {records} needed")
        records = args.records
    grown, grow_receipt = grow(base, records)
    extended = fa3.extend_plan(plan, data, final, grown)
    directive = {"schema": rr.EDITS_SCHEMA, "edits": [], "roster_refresh": extended, "restore_import_floor": True}
    body, receipt = rr.apply_body(grown, directive, scheme="one_pool")
    # b778 fa5 / fr1: apply_body is the test/plan writer; the disc writer (rr.apply) heals null colleges, and
    # the proof body must carry the same fix or the Contracts / Free Agents panel bugchecks on the first one.
    body, college_receipt = college_check.heal_null_references(body, source="capacity roster")
    doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
    vacancies = capacity.import_vacancies(body)
    require(len(doc.free_agents) == len(extended["free_agents"]), "free-agent count differs after the refresh")
    require(vacancies >= capacity.IMPORT_FLOOR + args.margin,
            f"only {vacancies} import vacancies remain; need {capacity.IMPORT_FLOOR + args.margin}")
    require(len(doc.by_pool("primary")) == grow_receipt["primary_after"],
            "the refresh changed the reserved primary count")
    out = copy.deepcopy(edits)
    out["roster_refresh"] = extended
    out["fa3_free_agent_depth"] = dict(edits.get("fa3_free_agent_depth") or {},
        added=final, candidates=final, margin=vacancies - capacity.IMPORT_FLOOR,
        import_vacancies_after_floor=vacancies, floor=capacity.IMPORT_FLOOR, capacity_arena=True)
    out["free_agent_capacity"] = {
        "schema": SCHEMA, "records": records, "arena_size": arena.CAPACITY_ARENA_SIZE,
        "block_offset": arena.CAPACITY_BLOCK_OFFSET, "base_primary": grow_receipt["primary_before"],
        "final_primary": grow_receipt["primary_after"], "candidates": final,
        "free_agents": len(doc.free_agents), "import_vacancies": vacancies,
        "floor": capacity.IMPORT_FLOOR, "margin": vacancies - capacity.IMPORT_FLOOR,
        "base_sha256": hashlib.sha256(base).hexdigest(),
        "grown_body_sha256": hashlib.sha256(grown).hexdigest(),
        "final_body_sha256": hashlib.sha256(body).hexdigest(),
        "college_null_repair": college_receipt["changed"]}
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["free_agent_capacity"], indent=1))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("merge", help="grow the arena and write every free-agent candidate")
    m.add_argument("--edits", required=True)
    m.add_argument("--base", required=True, help="the refresh's base roster: a disc image or a bare main ROST body")
    m.add_argument("--out", required=True)
    m.add_argument("--data", default=str(fa3.DATA))
    m.add_argument("--margin", type=int, default=fa3.DEFAULT_MARGIN)
    m.add_argument("--records", type=int, default=0,
                   help="reserve at least this many appended capacity records (default: the exact fit)")
    args = parser.parse_args(argv)
    try:
        return merge(args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"capacity growth refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
