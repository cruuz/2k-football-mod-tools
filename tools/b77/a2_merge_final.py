#!/usr/bin/env python3
"""b77 / a2 verify step: merge the Haiku handedness shards, apply the lead checks, write HANDEDNESS_FINAL.json,
a2_ANSWERS.json (input of tools/b77/a2_handedness.py) and the counts VERIFY.md quotes.

Inputs (reports/a2_swarm): shard_0..9.json (players), out_0..9.json (swarm results), ../a2_PLAYER_LIST.json.
Nothing is invented: each player gets a source tier.
  A  an explicit statement from a source (a left-handed / left-footed claim, or a Right with a quoted statement).
  B  a Right backed by a complete list read on 2026-10-08: quarterbacks absent from Wikipedia's "List of left-handed
     quarterbacks"; kickers who appeared in the NFL in 2019 or later (Wikipedia, Ben Sauls: he was the first
     left-footed kicker to appear in a regular-season game since Janikowski in 2018).
  E  an estimate only (Right is the large majority; no statement, no complete list). NOT applied.
  C  nothing to source (placeholder with no name, a player at another position). NOT applied.
Rows tier A and B are applied; E and C keep what the disc holds and are flagged.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
from pathlib import Path

LEFTY_QB_LIST_URL = "https://en.wikipedia.org/wiki/List_of_left-handed_quarterbacks"
# names on that page, fetched 2026-10-08 (all tables)
LEFTY_QBS = """Frankie Albert, Allie Sherman, John Karrs, Harry Agganis, Fred Wyant, Terry Baker, Bobby Douglass, Ken Stabler,
Jim Del Gaizo, Dennis Morrison, David Humm, Jim Zorn, Paul McDonald, Boomer Esiason, Steve Young, Erik Wilhelm, Jeff Carlson,
Scott Mitchell, Todd Marinovich, Will Furrer, Mark Brunell, Doug Nussmeier, Tony Graziani, Brock Huard, Cade McNown,
Michael Vick, Chris Simms, Jared Lorenzen, Tyler Palko, Matt Leinart, Pat White, Tim Tebow, Kellen Moore, Tua Tagovailoa,
Michael Penix, Dillon Gabriel, Hunter Dekkers, Cole Payton""".replace("\n", " ")
LEFTY_QBS = {n.strip() for n in LEFTY_QBS.split(",")}
SAULS_URL = "https://en.wikipedia.org/wiki/Ben_Sauls"
SI_2018 = "https://www.si.com/nfl/2018/01/11/lefty-left-footed-punters-bill-belichick-dustin-colquitt-zoltan-mesko-ryan-allen"
MONDAQ = "https://mondaq.com/unitedstates/sport/1394476/lefty-love"

# lead-verified in this step (WebFetch, 2026-10-08): where the lead re-read the source
LEAD_LEFT_QB = LEFTY_QBS
LEAD_SI = {"Ryan Allen", "Donnie Jones", "Dustin Colquitt", "Chris Jones", "Chris Hanson", "Kevin Huber", "David Akers"}

OVERRIDES = {
    ("Ken Walter", "P"): dict(hand="Left", confidence="medium", url="https://www.boston.com/sports/new-england-patriots/2007/08/30/leftfooted_punt/?amp=1",
        evidence="Boston.com 2007-08-30 (re-fetched by the lead): 'like Josh Miller and Ken Walter, he is a left-footed punter.' The swarm's two Ken Walter rows said Right (one 'None stated', one 'not individually searched') and disagreed with the first pass; the lead resolved them to Left.",
        note="swarm conflict resolved"),
    ("Ben Sauls", "K"): dict(hand="Left", confidence="high", url=SAULS_URL,
        evidence="Wikipedia (fetched by the lead): Sauls was 'the first left footed kicker in the league' to appear in a regular season game since Sebastian Janikowski (2018). Giants.com camp Q&A (via search result) calls him the lefty of the Giants' kicking battery. The swarm shard 9 recorded Right unresearched (search limit).",
        note="swarm missed a left-footed kicker", extra_urls=["https://www.giants.com/news/dominic-zvada-michigan-wolverines-kicker-ben-sauls-john-harbaugh-chris-horton"]),
    ("Tony Graziani", "QB"): dict(hand="Left", confidence="high", url=LEFTY_QB_LIST_URL,
        evidence="Wikipedia 'List of left-handed quarterbacks' (fetched by the lead) lists Tony Graziani (1997-2008; Falcons). The swarm's source was a 1996 college newspaper.", note=""),
    ("Harrison Butker", "K"): dict(hand="Right", confidence="medium", url="https://gazette.com/?p=98172",
        evidence="Gazette (Ken Sugiura column, search-result summary, page not opened) says Butker decides games 'with his right foot'; EA Sports Madden NFL 27 ratings page lists handedness Right (game database, weak); Noah states he is right-footed. No league or team bio statement found. Wikipedia has no statement (read to 100k of 140k chars).",
        note="needs a primary source if one can be found; this is the corrected value for the Butker bug"),
    ("Jim Breech", "K"): dict(hand="Right", confidence="medium", url="https://en.wikipedia.org/wiki/Jim_Breech",
        evidence="Wikipedia (the lead's search summary, consistent with the swarm quote): 'He wore a smaller size 5 cleat on his right kicking foot (his normal size was 7)'. The game holds Left for his 1988 row.",
        note="inferred from the cleat statement, not a bare 'right-footed'"),
}
CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def load(swarm):
    shards, results = [], []
    for i in range(10):
        shards += json.loads((swarm / f"shard_{i}.json").read_text())["players"]
        results += json.loads((swarm / f"out_{i}.json").read_text())["results"]
    return shards, results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", type=Path, default=Path("/home/noah/Desktop/2K5-8 Editors/b77_session/reports"))
    ap.add_argument("--today", default="2026-10-08")
    args = ap.parse_args(argv)
    swarm = args.reports / "a2_swarm"
    plist = json.loads((args.reports / "a2_PLAYER_LIST.json").read_text())
    rows = {r["id"]: r for r in plist["players"]}
    shards, results = load(swarm)

    # attach each result to its shard player by (name, position, row_ids order within the shard file)
    by_key = collections.defaultdict(list)       # (name, position) -> [(shard player, result)]
    for i in range(10):
        s_i = json.loads((swarm / f"shard_{i}.json").read_text())["players"]
        o_i = json.loads((swarm / f"out_{i}.json").read_text())["results"]
        pool = collections.defaultdict(list)
        for o in o_i:
            pool[(o["name"], o["position"])].append(o)
        for s in s_i:
            key = (s["name"], s["position"])
            by_key[key if s["name"] else (s["name"], s["position"], tuple(s["row_ids"]))].append((s, pool[key].pop(0) if pool[key] else None))

    players = []
    conflicts = []
    for key, items in sorted(by_key.items(), key=lambda kv: (kv[0][1], str(kv[0][0]))):
        name, position = key[0], key[1]
        row_ids = sorted({rid for s, _o in items for rid in s["row_ids"]})
        game_now = sorted({rows[r]["hand"] for r in row_ids})
        seasons = sorted({rows[r]["season"] for r in row_ids if rows[r].get("season")})
        years_pro = [rows[r].get("years_pro") for r in row_ids if rows[r]["scope"] == "main_roster_2026"]
        outs = [o for _s, o in items if o]
        best = max(outs, key=lambda o: CONF_RANK[o["confidence"]]) if outs else None
        distinct = {o["hand"] for o in outs}
        entry = dict(name=name, position=position, gsis_id=next((o["gsis_id"] for o in outs if o.get("gsis_id")), None),
                     row_ids=row_ids, seasons=seasons, game_value_now=game_now)
        if len(distinct) > 1:
            conflicts.append(dict(name=name, position=position, swarm=[(o["hand"], o["confidence"]) for o in outs]))
        ov = OVERRIDES.get((name, position))
        if ov:
            entry.update(hand=ov["hand"], confidence=ov["confidence"], tier="A", evidence=ov["evidence"],
                         url=ov["url"], urls=[ov["url"]] + ov.get("extra_urls", []), checked_by_sonnet=True,
                         verification="lead re-fetched / re-searched 2026-10-08", note=ov["note"])
        elif name == "Chris Berman":
            entry.update(hand=game_now[0], confidence="none", tier="C", evidence="Chris Berman is the ESPN host (an Easter-egg record in the 2026 pool), not an NFL quarterback: nothing to source",
                         url=None, urls=[], checked_by_sonnet=True, verification="not a real quarterback", note="not applied")
        elif not name.strip():
            entry.update(hand=game_now[0], confidence="none", tier="C", evidence="placeholder row: no player name, nothing to source",
                         url=None, urls=[], checked_by_sonnet=True, verification="placeholder", note="not applied")
        elif position not in ("QB", "K", "P"):
            entry.update(hand=best["hand"], confidence=best["confidence"], tier="C",
                         evidence=best["evidence"], url=best.get("url"), urls=[u for u in [best.get("url")] if u],
                         checked_by_sonnet=True, verification="not a QB/K/P: dominant hand is not used by those animations as far as we know; left as the disc holds it",
                         note="not applied")
        else:
            hand = best["hand"]
            if hand == "Left" or name in LEFTY_QBS:
                entry.update(hand=hand if name not in LEFTY_QBS else "Left")
            else:
                entry.update(hand=hand)
            entry.update(confidence=best["confidence"], evidence=best["evidence"], url=best.get("url"),
                         urls=[u for u in {o.get("url") for o in outs} if u])
            if entry["hand"] == "Left":
                lead = (position == "QB" and name in LEAD_LEFT_QB) or name in LEAD_SI
                if name == "Tress Way":
                    lead = True                                  # Mondaq 2023 names Way as left-footed; Wikipedia quote from the swarm
                    entry["urls"].append(MONDAQ)
                if position == "QB" and name in LEAD_LEFT_QB:
                    entry["urls"].append(LEFTY_QB_LIST_URL)
                if name in LEAD_SI:
                    entry["urls"].append(SI_2018)
                entry.update(tier="A", checked_by_sonnet=bool(lead),
                             verification=("lead re-read the source 2026-10-08" if lead else
                                           "swarm quote with URL; not re-fetched by the lead"), note="")
            elif entry["confidence"] in ("high", "medium"):
                entry.update(tier="A", checked_by_sonnet=False, verification="swarm quote with URL; not re-fetched", note="")
            elif position == "QB":
                entry.update(tier="B", checked_by_sonnet=True, confidence="medium",
                             verification="absent from Wikipedia's complete 'List of left-handed quarterbacks' (fetched 2026-10-08)",
                             evidence="Not on Wikipedia's List of left-handed quarterbacks (read in full 2026-10-08); the swarm found no left-handed statement either.",
                             url=LEFTY_QB_LIST_URL, urls=[LEFTY_QB_LIST_URL], note="negative evidence, not a bio statement")
            elif position == "K" and ((seasons and min(seasons) >= 2019 and max(seasons) <= 2025) or
                                      (seasons == [2026] and all(y and y >= 1 for y in years_pro))):
                entry.update(tier="B", checked_by_sonnet=True, confidence="medium",
                             verification="Wikipedia (Ben Sauls): first left-footed kicker to appear in a regular-season game since 2018; this kicker appeared in 2019 or later",
                             evidence="Every NFL placekicker who appeared from 2019 through 2025 was right-footed except Ben Sauls (Wikipedia, Ben Sauls); this player is not Sauls.",
                             url=SAULS_URL, urls=[SAULS_URL], note="negative evidence, not a bio statement")
            else:
                entry.update(tier="E", checked_by_sonnet=True, confidence="low",
                             verification="no complete list covers this player; Right is the large majority",
                             evidence="No statement and no complete list found; swarm: " + entry["evidence"], note="estimate only, not applied")
        entry["apply"] = entry["tier"] in ("A", "B")
        entry["game_differs"] = any(rows[r]["hand"] != entry["hand"] for r in row_ids)
        players.append(entry)

    final = dict(compiled=args.today, schema="b77/a2_handedness_final/v1",
                 rule="tiers A and B are applied; E (estimate) and C (nothing to source) keep what the disc holds",
                 lefty_qb_list_url=LEFTY_QB_LIST_URL, players=players, swarm_conflicts=conflicts)
    (swarm / "HANDEDNESS_FINAL.json").write_text(json.dumps(final, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    answers = []
    for p in players:
        if not p["apply"]:
            continue
        for rid in p["row_ids"]:
            answers.append(dict(id=rid, name=rows[rid]["name"], position=rows[rid]["position"], hand=p["hand"],
                                sources=p["urls"] or [p["url"]], note=f"tier {p['tier']} {p['confidence']}: {p['verification']}"))
    (swarm / "a2_ANSWERS.json").write_text(json.dumps(dict(schema="b77/a2_answers/v1", answers=answers), indent=1, ensure_ascii=False) + "\n",
                                           encoding="utf-8", newline="\n")
    cnt = collections.Counter((p["position"] if p["position"] in ("QB", "K", "P") else "other", p["tier"], p["hand"]) for p in players)
    print(json.dumps(dict(players=len(players), answers=len(answers), conflicts=len(conflicts),
                          counts={f"{a}|{b}|{c}": v for (a, b, c), v in sorted(cnt.items())}), indent=1))
    changed = [p for p in players if p["apply"] and p["game_differs"]]
    print("apply-and-differs:", len(changed), "rows:", sum(len(p["row_ids"]) for p in changed))
    print("unapplied game-Left:", [(p["name"], p["position"], p["tier"]) for p in players if not p["apply"] and "Left" in p["game_value_now"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
