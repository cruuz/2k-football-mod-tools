#!/usr/bin/env python3
"""Beta 77 u3s: uniform style slots for the 2026 alternates (census, native cycle proof, the slot plan).

  census  --disc DISC --retail RETAIL --out census.json
          per franchise: the main roster's style table and labels, kits, aggregate members, every owner of a style
          (historic team files, the Anniversary moments' files and SITU kits, m1's spare) and the free slots by class
  cycle   --xbe default.xbe --disc DISC [--plan PLAN] --out cycle.json
          runs the game's own Team Select code under Unicorn for every team record: 0xE2FB0 (home next) from style
          0 until it stops, 0xE2F70 (home prev) back to 0, the label through 0xE3700 -> 0xE3530 and the real
          formatter, and 0xE2F20 (the kit loader's clamp) for slots 0..14; with --plan, on the planned tables
  plan    --census census.json --decisions data/nfl2k5_uniform_slots_2026.json [--cycle cycle.json]
          --out u3s_SLOT_PLAN.json --table table.md
          merges the decisions with the census, refuses any slot history owns, and writes the plan and a readable
          table (every team: free slots, assignments slot -> sourced 2026 set, what is not assigned and why)

Read only: nothing here writes a disc. Game-derived outputs belong in private scratch.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_uniform_slots as us  # noqa: E402

PLAN_SCHEMA = "b77/u3s/uniform-slot-plan/v1"
DECISIONS_SCHEMA = "nfl2k5_uniform_slots_2026/v1"
HOME_TEAM_PTR, HOME_SLOT = 0xE5FE68, 0xE60210
FN_HOME_NEXT, FN_HOME_PREV, FN_HOME_LABEL, FN_CLAMP = 0xE2FB0, 0xE2F70, 0xE3700, 0xE2F20
SCRATCH = 0x02000000


# ----------------------------------------------------------------------------------------------- census

def census_doc(disc: Path, retail: Path) -> dict:
    franchises = us.census(disc, retail)
    out = {"schema": "b77/u3s/uniform-slot-census/v1", "disc": str(disc), "retail": str(retail), "franchises": {}}
    for code, f in sorted(franchises.items()):
        out["franchises"][f.abbreviation] = {
            "code": code, "team_index": f.team_index,
            "offered": us.offered_labels(f.pairs),
            "pairs": [list(p) for p in f.pairs],
            "kits": {str(s): list(v) for s, v in sorted(f.kits.items())},
            "retail_kits": sorted(f.retail_kits),
            "members": {str(s): v for s, v in sorted(f.members.items())},
            "owners": {str(s): v for s, v in sorted(f.owners.items())},
            "free": us.free_slots(f),
        }
    return out


def franchises_from_doc(doc: dict) -> dict[str, us.Franchise]:
    out = {}
    for abbr, d in doc["franchises"].items():
        f = us.Franchise(d["code"], abbr, d["team_index"], [tuple(p) for p in d["pairs"]])
        f.kits = {int(s): tuple(v) for s, v in d["kits"].items()}
        f.retail_kits = set(d["retail_kits"])
        f.members = {int(s): v for s, v in d["members"].items()}
        f.owners = {int(s): v for s, v in d["owners"].items()}
        out[d["code"]] = f
    return out


# ----------------------------------------------------------------------------------------------- native cycle

class Machine:
    """The executable mapped at its virtual addresses with a scratch page; calls return to a nop sentinel."""

    def __init__(self, xbe: bytes):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(xbe)
        self.m = Uc(UC_ARCH_X86, UC_MODE_32)
        lo = image.base & ~0xFFF
        hi = (image.base + image.image_size + 0xFFF) & ~0xFFF
        self.m.mem_map(lo, hi - lo)
        self.m.mem_write(image.base, xbe[:image.headers_size])
        for s in image.sections:
            if s.raw_size:
                self.m.mem_write(s.start, xbe[s.raw:s.raw + min(s.raw_size, s.size)])
        self.m.mem_map(SCRATCH, 0x100000)
        self.m.mem_write(SCRATCH, b"\x90" * 16)
        self.team = SCRATCH + 0x10000

    def call(self, va: int, **regs) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP
        names = {"eax": UC_X86_REG_EAX, "ecx": UC_X86_REG_ECX, "edx": UC_X86_REG_EDX}
        sp = SCRATCH + 0x80000 - 0x100
        self.m.mem_write(sp, struct.pack("<I", SCRATCH))
        self.m.reg_write(UC_X86_REG_ESP, sp)
        for name, value in regs.items():
            self.m.reg_write(names[name], value)
        self.m.emu_start(va, SCRATCH, count=200_000)
        return self.m.reg_read(UC_X86_REG_EAX)

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.m.mem_read(va, 4))[0]

    def w32(self, va: int, value: int) -> None:
        self.m.mem_write(va, struct.pack("<I", value))

    def wstr(self, va: int) -> str:
        raw = bytes(self.m.mem_read(va, 256))
        out = []
        for i in range(0, len(raw), 2):
            c = raw[i] | raw[i + 1] << 8
            if not c:
                break
            out.append(chr(c))
        return "".join(out)

    def cycle(self, record: bytes) -> dict:
        """The styles Team Select offers this team record, in order, with the game's labels."""
        self.m.mem_write(self.team, bytes(record))
        self.w32(HOME_TEAM_PTR, self.team)
        self.w32(HOME_SLOT, 0)
        order = [(0, self.wstr(self.call(FN_HOME_LABEL)))]
        for _ in range(16):
            before = self.u32(HOME_SLOT)
            self.call(FN_HOME_NEXT)
            slot = self.u32(HOME_SLOT)
            if slot == before:
                break
            order.append((slot, self.wstr(self.call(FN_HOME_LABEL))))
        back = [self.u32(HOME_SLOT)]
        for _ in range(16):
            before = self.u32(HOME_SLOT)
            self.call(FN_HOME_PREV)
            slot = self.u32(HOME_SLOT)
            if slot == before:
                break
            back.append(slot)
        clamp = [self.call(FN_CLAMP, ecx=self.team, edx=k) for k in range(us.MAX_STYLE + 1)]
        return {"order": order, "reverse": back, "clamp": clamp}


def main_records(disc: Path) -> list[tuple[str, bytes]]:
    from mod_editor.core import nfl2k5_historic_styles as hs
    with hs.Source(disc) as src:
        main = src.get(identity=hs.ROSTER_OUTER_ID)
    body = main[32:]
    return [(code, body[at:at + us.TEAM_SIZE]) for at, code in hs.team_records(main)[:32]]


def cycle_doc(xbe: Path, disc: Path, plan: dict | None = None) -> dict:
    import hashlib
    data = xbe.read_bytes()
    machine = Machine(data)
    out = {"schema": "b77/u3s/uniform-cycle/v1", "xbe_sha256": hashlib.sha256(data).hexdigest(),
           "planned": plan is not None, "teams": {}}
    for code, record in main_records(disc):
        abbr = us.FRANCHISES[code]
        record = bytearray(record)
        if plan is not None:
            for a in plan["teams"][abbr].get("assignments") or []:
                if a.get("pair") is not None:
                    struct.pack_into("<HH", record, us.TABLE + 4 * (a["style"] - 1), *a["pair"])
        result = machine.cycle(bytes(record))
        pairs = us.team_pairs(bytes(record))
        model = {"order": [[s, us.style_label(s, *(pairs[s - 1] if s else (0, 0)))] for s in us.offered_styles(pairs)],
                 "clamp": [us.loaded_style(pairs, k) for k in range(us.MAX_STYLE + 1)]}
        result["model_agrees"] = ([list(x) for x in result["order"]] == model["order"]
                                  and result["clamp"] == model["clamp"]
                                  and result["reverse"] == [s for s, _ in reversed(result["order"])])
        out["teams"][abbr] = result
    out["all_agree"] = all(t["model_agrees"] for t in out["teams"].values())
    return out


# ----------------------------------------------------------------------------------------------- the plan

def build_plan(census: dict, decisions: dict, cycle: dict | None = None) -> dict:
    if decisions.get("schema") != DECISIONS_SCHEMA:
        raise SystemExit("unexpected decisions schema")
    franchises = franchises_from_doc(census)
    teams = {}
    for code, f in sorted(franchises.items(), key=lambda kv: kv[1].abbreviation):
        d = decisions["teams"].get(f.abbreviation, {})
        free = us.free_slots(f)
        assignments = []
        # "2026  Alternate n": the shipped ones keep their number; new ones count on in the order the game cycles
        n = max([p[1] for p in f.pairs if p[0] == us.ALTERNATE_YEAR and p[1] < 1900] or [0])
        for a in sorted(d.get("assignments", []), key=lambda x: x["style"]):
            a = dict(a)
            style = a["style"]
            before = (us.style_label(style, *f.pairs[style - 1]) if us.style_exists(f.pairs, style)
                      else "(not offered)")
            if a["method"] == "authored":
                a["pair"] = list(f.pairs[style - 1])
            elif a.get("pair") is None:
                n += 1
                a["pair"] = [us.ALTERNATE_YEAR, n]
            a["label_before"] = before
            a["label_after"] = us.style_label(style, *a["pair"])
            a["kit_files"] = [f"{f.code}h{style}.iff", f"{f.code}a{style}.iff"]
            if a["method"] in ("repurpose", "enable_orphan", "authored"):
                a["fit"] = fit_risk(f.code, style)
            a["cards"] = [f"unif_h{f.code}_{style}", f"unif_a{f.code}_{style}", f"helm_h{f.code}_{style}",
                          f"helm_a{f.code}_{style}"]
            assignments.append(a)
        entry = {"code": code, "team_index": f.team_index,
                 "offered_now": us.offered_labels(f.pairs),
                 "owned": {str(s): v for s, v in sorted(f.owners.items())},
                 "free": free, "assignments": assignments,
                 "already_in_game": d.get("already_in_game", []),
                 "not_assigned": d.get("not_assigned", []),
                 "kept_free": d.get("kept_free", []),
                 "notes": d.get("notes", "")}
        teams[f.abbreviation] = entry
    plan = {"schema": PLAN_SCHEMA, "decisions_schema": DECISIONS_SCHEMA, "teams": teams,
            "rules": decisions.get("rules", {}), "sources": decisions.get("sources", {})}
    problems = us.validate_plan(plan, franchises)
    plan["validation"] = {"problems": problems, "ok": not problems}
    for abbr, entry in teams.items():
        f = next(x for x in franchises.values() if x.abbreviation == abbr)
        pairs = us.plan_pairs(f, entry, methods=("repurpose", "enable_orphan", "append", "authored"))
        entry["offered_after_plan"] = us.offered_labels(pairs)
        entry["offered_after_phase1"] = us.offered_labels(us.plan_pairs(f, entry, methods=("repurpose", "enable_orphan", "authored")))
    plan["roster_teams_edits"] = us.roster_team_entries(plan, franchises)
    plan["totals"] = totals(plan)
    if cycle is not None:
        plan["native_cycle"] = {"xbe_sha256": cycle["xbe_sha256"], "planned": cycle["planned"],
                                "all_agree": cycle["all_agree"]}
    return plan


def budgets(code: str, style: int) -> dict:
    """The slot's fixed texture budgets (compressed bytes each importer may use), from the Studio's target reports:
    jersey numbers (min and total of the ten), torso and pants, per kit. A 2026 kit is authored against style 0's
    budgets; a slot whose budgets are much smaller may not fit the same art (job u3s: CIN 4's road numbers)."""
    import nfl_jersey_tset_targets as jt
    import nfl_pants_tset_targets as pt
    import nfl_live_numbers_nameplate_targets as dt
    out = {}
    for side in "HA":
        digits = [dt.select_target("jersey_digit", code, side, style, d, dt.DEFAULT_REPORT)[2].stored_size
                  for d in range(10)]
        out[side] = {"digits_min": min(digits), "digits_total": sum(digits),
                     "torso": jt.select_target(code, side, style, jt.DEFAULT_REPORT)[3].stored_size,
                     "pants": pt.select_target(code, side, style, pt.DEFAULT_REPORT)[3].stored_size}
    return out


def fit_risk(code: str, style: int) -> dict:
    """The slot's budgets against style 0's (the 2026 primary art): the smallest ratio and a flag below 0.6."""
    slot, base = budgets(code, style), budgets(code, 0)
    ratios = {f"{side}_{k}": round(slot[side][k] / max(1, min(base["H"][k], base["A"][k])), 2)
              for side in "HA" for k in ("digits_total", "torso", "pants")}
    worst = min(ratios.values())
    return {"budgets": slot, "style0": base, "ratios": ratios, "worst_ratio": worst, "risk": worst < 0.6}


def totals(plan: dict) -> dict:
    count = {m: 0 for m in us.METHODS}
    built = 0
    for entry in plan["teams"].values():
        for a in entry["assignments"]:
            count[a["method"]] += 1
            built += a.get("status") in ("built", "shipped")
    risky = [f"{abbr} {a['style']}" for abbr, entry in plan["teams"].items() for a in entry["assignments"]
             if (a.get("fit") or {}).get("risk")]
    return {"assignments": sum(count.values()), "by_method": count, "built_or_shipped": built, "fit_risk": risky,
            "already_in_game": sum(len(e["already_in_game"]) for e in plan["teams"].values()),
            "not_assigned": sum(len(e["not_assigned"]) for e in plan["teams"].values())}


def table_md(plan: dict) -> str:
    lines = ["| team | free now (alt / orphan / era / append) | slot -> 2026 set (method) | already in game | not assigned |",
             "|---|---|---|---|---|"]
    for abbr, e in sorted(plan["teams"].items(), key=lambda kv: kv[1]["code"]):
        fr = e["free"]
        free = (f"{fr['retail_alternates'] or '-'} / {fr['orphans'] or '-'} / {fr['eras'] or '-'} / "
                f"{(fr['append'][:3] + ['...']) if len(fr['append']) > 3 else (fr['append'] or '-')}")
        slots = "<br>".join(f"{a['style']}: {a['set']} ({a['method']}; was {a['label_before']}; reads "
                            f"{a['label_after']}){' [' + a['status'] + ']' if a.get('status') else ''}"
                            for a in e["assignments"]) or "-"
        ing = "<br>".join(f"{x['set']} = style {x['style']}" for x in e["already_in_game"]) or "-"
        na = "<br>".join(f"{x['set']}: {x['why']}" for x in e["not_assigned"]) or "-"
        lines.append(f"| {abbr} ({e['code']}) | {free} | {slots} | {ing} | {na} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("census")
    s.add_argument("--disc", type=Path, required=True)
    s.add_argument("--retail", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("cycle")
    s.add_argument("--xbe", type=Path, required=True)
    s.add_argument("--disc", type=Path, required=True)
    s.add_argument("--plan", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("plan")
    s.add_argument("--census", type=Path, required=True)
    s.add_argument("--decisions", type=Path, required=True)
    s.add_argument("--cycle", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--table", type=Path)
    args = p.parse_args(argv)
    if args.command == "census":
        doc = census_doc(args.disc, args.retail)
        args.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({k: v["free"] for k, v in doc["franchises"].items()})[:400])
    elif args.command == "cycle":
        plan = json.loads(args.plan.read_text()) if args.plan else None
        doc = cycle_doc(args.xbe, args.disc, plan)
        args.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"all_agree": doc["all_agree"], "planned": doc["planned"]}))
        return 0 if doc["all_agree"] else 1
    elif args.command == "plan":
        census = json.loads(args.census.read_text())
        decisions = json.loads(args.decisions.read_text())
        cycle = json.loads(args.cycle.read_text()) if args.cycle else None
        plan = build_plan(census, decisions, cycle)
        args.out.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8", newline="\n")
        if args.table:
            args.table.write_text(table_md(plan), encoding="utf-8", newline="\n")
        print(json.dumps({"ok": plan["validation"]["ok"], "problems": plan["validation"]["problems"][:10],
                          "totals": plan["totals"]}))
        return 0 if plan["validation"]["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
