#!/usr/bin/env python3
"""b77 / a3 + a5: which uniform style each 25th Anniversary moment side selects (compiler).

Noah (10/8, playing the Unc Bowl): "should have proper uniforms, has 04 jerseys stock, we need newer scenarios to have
modern uniforms by default." A moment side selects a style of its franchise (the SITU record's kit index, +0x58 away and
+0x5C home). Style 0 is the 2026 kit once the 2026 program has written it, and the retail 2004 look sits on the franchise's
spare style; until now every authored "kit 0" meant "the 2004 look" and was moved to the spare, so a 2025 game showed
2004 stock jerseys, and a few moments borrowed a throwback style as "the closest" to a look style 0 could not give.

data/nfl2k5_moment_uniform_eras.json holds the sourced facts (design eras per franchise, the retail era sets, the seasons the
2004 retail look covers, what each side wore in its game) and this tool turns them into one decision per moment side, by
five rules in order:

  R0 a sourced per-side override (the `overrides` block: the kit that is closest to what the team wore in that game, with
     the worn colours and the sources that say so), when one exists;
  R1 style 0 (the 2026 kit) when the season is on or after the year the franchise's current primary design began;
  R2 a retail period set (the retail uniform table's era rows) when one covers the season;
  R3 the retail 2004 kit ("retail_current", kit 0 moved to the spare by the historic styles step) when the 2004 look was
     still worn that season by that kit (home or road). a5 (Noah 10/8: "Brady Super Bowl Patriots need old jerseys"): the
     Reebok/Nike template year no longer matters, the design does. The Nike cut (2012 on) is a difference of tailoring and
     marks, not of colours, and style 0 is a DIFFERENT design for every season before `design_2026_since`;
  R4 otherwise style 0: modern by default.

A kit in the moment data is an int style index (0 = the retail current look), {"era_year": Y}, or "modern" (style 0, the
2026 kit, exempt from the historic styles step). `compile` writes the decisions into the spec, the compiled moments file and
the Unc Bowl manifest, and the `decisions` block of the eras file; `check` verifies all of them agree.

  python3 tools/b77/a1_uniforms.py compile [--root DIR] [--v05-situ situation.iff]
  python3 tools/b77/a1_uniforms.py check   [--root DIR]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]

ERAS = "data/nfl2k5_moment_uniform_eras.json"
SPEC = "tools/nfl2k5_espn25_more_moments_spec.json"
MOMENTS = "data/nfl2k5_espn25_more_moments.json"
MODERN = "modern"
RETAIL_COUNT = 25                  # physical SITU rows 0..24 are the retail moments
SITU_ROW = 0x44, 0x6C              # first record, stride
KIT_AT = {"away": 0x58, "home": 0x5C}


class UniformError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise UniformError(message)


def load(root, name):
    return json.loads((Path(root) / name).read_text(encoding="utf-8"))


def franchise_of(team_key):
    selector, season = team_key.rsplit("_", 1)
    return selector, int(season)


def decide(eras, selector, season, role, moment=None):
    """(decision, rule, reason) for one team-season; decision is "modern", "retail_current" or an int style index.
    `moment` (the moment id) lets a sourced R0 override win."""
    for o in eras.get("overrides", []):
        if moment is not None and o["moment"] == moment and o["side"] == role:
            return o["kit"], "R0", o["reason"]
    f = eras["franchises"][selector]
    since = f["design_2026_since"]
    if since is not None and season >= since:
        return MODERN, "R1", f"the current primary design began in {since}"
    for index, first, last in f["retail_era_sets"]:
        if first <= season <= last:
            return index, "R2", f"retail period set {index} covers {first}-{last}"
    through = f["design_2004_through_home" if role == "home" else "design_2004_through_road"]
    first = f["design_2004_from"]
    if first is not None and first <= season <= through:
        template = ("Reebok template" if season <= eras["rule"]["retail_kit_template_through"]
                    else "Nike cut over the same design")
        return "retail_current", "R3", f"the 2004 look ({first}-{through}, {role} kit) was worn in {season} ({template})"
    return MODERN, "R4", f"no retail set covers {season} and the 2004 look does not (modern by default)"


def decisions(eras, moments):
    """[{moment, side, team_key, season, role, kit (the decision), rule, reason}] for every authored moment side."""
    out = []
    for m in moments:
        for side in ("away", "home"):
            selector, season = franchise_of(m[side])
            kit, rule, reason = decide(eras, selector, season, side, m["id"])
            out.append(dict(moment=m["id"], side=side, team_key=m[side], season=season, role=side, kit=kit, rule=rule,
                            reason=reason))
    return out


def kit_value(decision):
    """What the moment data stores: "modern", or the style int (0 = retail current)."""
    return 0 if decision == "retail_current" else decision


def situ_value(decision, selector, eras):
    """The kit index the SITU record holds once the historic styles step has run."""
    f = eras["franchises"][selector]
    if decision == MODERN:
        return 0
    if decision == "retail_current":
        return f["retail_spare_style_v05"]
    return decision


def read_situ_kits(situ):
    """{(row, side): kit} for every SITU row of a situation.iff file (32-byte wrapper, then the first chunk's body)."""
    body = situ[32:32 + struct.unpack_from("<I", situ, 4)[0]]
    count = struct.unpack_from("<I", body, 64)[0]
    return {(row, side): struct.unpack_from("<I", body, SITU_ROW[0] + row * SITU_ROW[1] + at)[0]
            for row in range(count) for side, at in KIT_AT.items()}


def json_text(doc):
    return json.dumps(doc, indent=2) + "\n"


def compile_all(root, v05_situ=None):
    """{path: new text}: the spec, the compiled moments, the eras file's decisions, then the manifests (data_sync)."""
    root = Path(root)
    eras = load(root, ERAS)
    spec = load(root, SPEC)
    compiled = load(root, MOMENTS)
    require([m["id"] for m in spec["moments"]] == [m["id"] for m in compiled["moments"]], "spec and moments differ in order")
    decided = decisions(eras, spec["moments"])
    by = {(d["moment"], d["side"]): d for d in decided}
    for doc in (spec, compiled):
        for m in doc["moments"]:
            m["kits"] = {side: kit_value(by[(m["id"], side)]["kit"]) for side in ("away", "home")}
    measured = read_situ_kits(Path(v05_situ).read_bytes()) if v05_situ else None
    old = {(d["moment"], d["side"]): d for d in eras.get("decisions", [])}
    for i, m in enumerate(spec["moments"]):
        for side in ("away", "home"):
            d = by[(m["id"], side)]
            selector, _season = franchise_of(d["team_key"])
            d["situ_row"] = RETAIL_COUNT + i
            d["v06_kit"] = situ_value(d["kit"], selector, eras)
            if measured is not None:
                d["v05_kit"] = measured[(RETAIL_COUNT + i, side)]
            elif (m["id"], side) in old:
                d["v05_kit"] = old[(m["id"], side)]["v05_kit"]
            else:
                raise UniformError("the first compile needs --v05-situ (the v0.5 situation.iff) to record the shipped kits")
            if (m["id"], side) in old:
                # the kit index a1x's repair wrote (state "a1x" of a stacked file); a5 keeps it so the repair can upgrade it
                d["a1x_kit"] = old[(m["id"], side)].get("a1x_kit", old[(m["id"], side)]["v06_kit"])
                d["a5_kit"] = old[(m["id"], side)].get("a5_kit", old[(m["id"], side)]["v06_kit"])
            else:
                d["a1x_kit"] = d["v05_kit"]
    eras["decisions"] = decided
    files = {root / SPEC: json_text(spec), root / ERAS: json_text(eras),
             root / MOMENTS: json.dumps(compiled, indent=2, ensure_ascii=True) + "\n"}
    return files


def check(root):
    """Problems (a list of strings) between the eras file and the data it compiles into; empty when consistent."""
    root = Path(root)
    eras = load(root, ERAS)
    spec = load(root, SPEC)
    compiled = load(root, MOMENTS)
    problems = []
    want = {(d["moment"], d["side"]): d for d in decisions(eras, spec["moments"])}
    stored = {(d["moment"], d["side"]): d for d in eras.get("decisions", [])}
    ids = {m["id"] for m in spec["moments"]}
    for o in eras.get("overrides", []):
        if o["moment"] not in ids or o["side"] not in ("away", "home"):
            problems.append(f"overrides: {o['moment']} {o['side']} is not a moment side")
        elif not (o.get("sources") and o.get("reason")) or not (o["kit"] in (MODERN, "retail_current") or isinstance(o["kit"], int)):
            problems.append(f"overrides: {o['moment']} {o['side']} needs a kit, a reason and sources")
    if set(stored) != set(want):
        problems.append("the eras file's decisions do not cover the moments")
    for doc, label in ((spec, "spec"), (compiled, "moments")):
        for m in doc["moments"]:
            for side in ("away", "home"):
                d = want.get((m["id"], side))
                if d is None or m["kits"][side] != kit_value(d["kit"]):
                    problems.append(f"{label}: {m['id']} {side} kit {m['kits'][side]!r} is not the decision {d and kit_value(d['kit'])!r}")
    for key, d in stored.items():
        if key in want and (d["kit"], d["rule"]) != (want[key]["kit"], want[key]["rule"]):
            problems.append(f"decisions: {key} is stale")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("--root", type=Path, default=ROOT)
    comp.add_argument("--v05-situ", type=Path)
    chk = sub.add_parser("check")
    chk.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.command == "check":
        problems = check(args.root)
        print("\n".join(problems) if problems else "consistent")
        return 1 if problems else 0
    files = compile_all(args.root, args.v05_situ)
    for path, text in sorted(files.items()):
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_bytes(text.encode("utf-8"))
            print("wrote", path)
    import data_sync
    for path, text in sorted(data_sync.sync(args.root).items()):
        path.write_bytes(text.encode("utf-8"))
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
