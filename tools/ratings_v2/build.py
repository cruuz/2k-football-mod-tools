#!/usr/bin/env python3
"""NFL 2K5 ratings v2 (job r1, 2026-09-24): real 2024-2025 NFL data -> the game's own rating scale, layered as a
roster-edits fragment on a 2026 league roster, plus the superstar (player_tags) top 250. DESIGN / PROVED OFFLINE.

Steps (each writes under --work; run in order the first time):
  features   per-player, per-season measures from the public nflverse files (features.py)
  reference  retail 2004 tier scale + 2K's physical-rating fits + age slopes + drill imputation (reference.py)
  honors     AP All-Pro / Pro Bowl 2024-25 from Wikipedia (honors.py; --fetch downloads the four pages)
  predraft   Wikipedia pre-draft measurables for records missing combine drills (predraft.py; slow, gentle)
  stability  each component's 2024 -> 2025 stability, which sets its shrinkage constant (stability.py, v2.1)
  rate       the ratings, the abilities tiers (the studio's own auto-assign), the fragment, the tags, the receipt

  build.py STEP --retail EXTRACTED_DISC --base-edits BASE.json --team-receipt MERGE_RECEIPT.json
           --nflverse NFLVERSE_DIR --work WORK_DIR [--base-sha256 HEX] [--forty-sources F.json ...] [--out DIR]

Evidence labels in every output: PROVED OFFLINE (read from the disc or computed from cited public data), DESIGN
(a documented choice), INFERRED (a proxy with no direct measure). Nothing here was witnessed in game.
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import sys
import time
from pathlib import Path

import common
from common import CFG, ONE_POOL, base, rr

FOOTER = ("unknown_52", "unknown_53_high")


def rated_league(forty_sources=()):
    from model import Data, build_players, rate_all
    retail, body_u7, u7, rows = base()
    doc = rr.RosterDocument(body_u7)
    by = {(p.pool, p.index): p for p in doc.players}
    D = Data(forty_sources)
    players = build_players(D, rows, doc, by)
    draft = {}
    for r in common.read_csv(common.nfl("players.csv.gz")):
        try:
            draft[r["gsis_id"]] = int(float(r["draft_pick"]))
        except (TypeError, ValueError):
            draft[r["gsis_id"]] = None
    rate_all(D, players, draft)
    return D, players


def with_ratings(body, players):
    d = rr.RosterDocument(body)
    by = {(p.pool, p.index): p for p in d.players}
    for p in players:
        rec = by[(p["pool"], p["index"])].record
        for k, v in p["ratings"].items():
            rec.set(k, int(v))
    return d


def step_rate(args):
    from mod_editor.core import nfl2k5_abilities_editor as ab
    from model import MODEL_VERSION, RATINGS
    from rank import rank, RULE
    t0 = time.time()
    retail, body_u7, u7, rows = base()
    D, players = rated_league(args.forty_sources or ())
    d2 = with_ratings(body_u7, players)
    plan = ab.plan_auto_assign(d2, top_n=10)          # the studio's own tiers, as u1's merge ran them
    ab_receipt = ab.apply_plan(d2, plan)
    body_v2 = d2.to_body()
    frag = rr.edits_between(body_u7, body_v2, name=f"2026 ratings v2 ({MODEL_VERSION}, job r1)")
    frag["author"] = "SOFTDRINK"
    frag["notes"] = (f"Layer on {Path(CFG['base_edits']).name} (sha256 {common.sha256(CFG['base_edits'])}). Writes only "
                     "the 28 rating fields and the abilities footer (unknown_52, unknown_53_high) of NFL-club records; "
                     "the star bit travels through player_tags.")
    fields = collections.Counter(k for e in frag["edits"] for k in e["fields"])
    stray = sorted(set(fields) - set(RATINGS) - set(FOOTER))
    assert not stray, stray
    b1, r1 = rr.apply_body(body_u7, frag)
    assert not r1["log"] and b1 == body_v2
    merged = dict(u7, name=u7["name"] + " + ratings v2 (job r1)", edits=list(u7["edits"]) + list(frag["edits"]))
    b2, r2 = rr.apply_body(retail, merged)
    assert not r2["log"] and b2 == body_v2
    dv = rr.RosterDocument(body_v2)
    byv = {(p.pool, p.index): p for p in dv.players}
    ranked, tags = rank([(p["pool"], p["index"], byv[(p["pool"], p["index"])].record.values["position"],
                          byv[(p["pool"], p["index"])].record.encode(), f"{p['name']} ({p['team']})") for p in players])
    per_pos = collections.Counter(x["pos"] for x in ranked if x["star"])
    out = Path(args.out or common.work("deliver", "x").parent)
    out.mkdir(parents=True, exist_ok=True)
    docs = {"r1_ratings_v2_fragment.json": frag,
            "r1_player_tags_v2.json": {"schema": "r1.player_tags.v1", "model": MODEL_VERSION, "rule": RULE,
                                       "count": len(tags), "per_position": dict(sorted(per_pos.items())),
                                       "player_tags": [str(t) for t in tags],
                                       "stars": [{k: x[k] for k in ("league_rank", "index", "pos", "pos_rank", "ovr",
                                                                    "ovr_in_game", "label")} for x in ranked if x["star"]]}}
    shas = {}
    for name, doc in docs.items():
        (out / name).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        shas[name] = common.sha256(out / name)
    receipt = {"model": MODEL_VERSION, "players_rated": len(players), "fragment_entries": len(frag["edits"]),
               "fields_written": dict(sorted(fields.items())),
               "abilities": {"rows": len(plan["rows"]), "changed_players": ab_receipt["changed_players"]},
               "replay": {"fragment_on_base_log": len(r1["log"]), "base_plus_fragment_on_retail_log": len(r2["log"]),
                          "equal_bodies": True},
               "body_sha256": {"base": hashlib.sha256(body_u7).hexdigest(), "with_v2": hashlib.sha256(body_v2).hexdigest()},
               "files_sha256": shas, "stars": dict(sorted(per_pos.items())),
               "fits": {"pressure_vs_time_to_throw": D.pressure_fit, "fg_logistic": D.fg_fit, "separation": D.sep_fit[1:]},
               "seconds": round(time.time() - t0, 1)}
    (out / "r1_v2_receipt.json").write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    players_out = [{k: v for k, v in p.items() if k in ("gsis", "name", "pos", "team", "tier", "depth", "index", "pool",
                                                        "ratings", "current", "basis", "years", "age")} for p in players]
    (out / "v2_players.json").write_text(json.dumps(players_out) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: receipt[k] for k in ("fragment_entries", "abilities", "stars", "files_sha256", "seconds")},
                     indent=1))
    return 0


def step_predraft(args):
    import predraft
    from model import Data
    retail, body_u7, u7, rows = base()
    D = Data(args.forty_sources or ())
    targets = []
    for r in rows:
        c = D.combine.get(r["gsis_id"], {})
        missing = [k for k in ("forty", "shuttle", "vertical", "bench") if c.get(k) is None]
        if missing:
            targets.append(dict(gsis_id=r["gsis_id"], name=r["source_name"], team=common.team_of(r),
                                pos=r.get("written_position"), college=r.get("source_college", ""), missing=missing))
    predraft.run(targets, common.work("predraft", "predraft.json"), reuse_glob=args.reuse)
    reject_mismatched_births(rows)
    return 0


def reject_mismatched_births(rows):
    """An article whose '(born ... YYYY)' is more than a year off the roster's birth date is another person (a father
    with the same name, a namesake): its drills are not used. Writes <work>/predraft/rejected.json."""
    import re
    birth = {r["gsis_id"]: (r.get("source_birth_date") or "")[:4] for r in rows}
    rejected = []
    for path in glob.glob(str(common.work("predraft", "x").parent / "*.json")):
        if path.endswith("rejected.json"):
            continue
        for g, rec in json.loads(Path(path).read_text(encoding="utf-8")).items():
            if rec.get("status") != "ok" or not rec.get("evidence") or not birth.get(g):
                continue
            try:
                text = Path(rec["evidence"]).read_text(encoding="utf-8")
            except OSError:
                continue
            m = re.search(r"born[^)]{0,80}?(\d{4})", text[:6000])
            if m and abs(int(m.group(1)) - int(birth[g])) > 1:
                rejected.append(g)
    common.work("predraft", "rejected.json").write_text(json.dumps(sorted(rejected), indent=1) + "\n", encoding="utf-8")
    return rejected


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("features", "reference", "honors", "predraft", "stability", "rate"))
    for name in ("retail", "base-edits", "team-receipt", "nflverse", "work"):
        ap.add_argument(f"--{name}", required=True)
    ap.add_argument("--base-sha256", default="")
    ap.add_argument("--forty-sources", action="append", help="cited 40s (nfl2k5.forty_sources.v1), repeatable")
    ap.add_argument("--fetch", action="store_true", help="honors: download the four Wikipedia pages first")
    ap.add_argument("--reuse", default=None, help="predraft: glob of article files other jobs saved (<gsis>.wikitext)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    CFG.update(retail=args.retail, base_edits=args.base_edits, base_sha256=args.base_sha256,
               team_receipt=args.team_receipt, nflverse=args.nflverse, work=args.work)
    if args.step == "features":
        import features
        features.main()
    elif args.step == "reference":
        import reference
        reference.build()
    elif args.step == "honors":
        import honors
        if args.fetch:
            honors.fetch()
        honors.main()
    elif args.step == "predraft":
        return step_predraft(args)
    elif args.step == "stability":
        import stability
        stability.main()
    else:
        return step_rate(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
