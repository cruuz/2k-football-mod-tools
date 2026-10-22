#!/usr/bin/env python3
"""Playbook sanity fixes from Noah's 10/21 stream (b778, job pb5) on the shipped SOFTDRINK offense packs.

Four rules, each an audit (``--check``) and a repair (``--apply``). The generator (``pb/v2/generator.py``) applies the
same rules to new books; this script brings the shipped packs (generator + ``repair_reversals.py`` +
``menu_screen_cap.py``) in line without regenerating them. Play records, formation records and their counts never
change; only slot order, menu links and three kinds of node operand do.

1. ``page_one``     The play-call formation picker opens on the formation in book slot 0 (the native picker pages
                    through formations in book index order, 0xE1230 / 0xE12B0 over the offense category list
                    0x5102CC, and starts on page 0; only LT "Coach's Pick", 0xAA660, runs the situation lottery).
                    Every retail book has its base set in slot 0; every SOFTDRINK book had Goal Line Sneak, Goal Line
                    and Gun Wildcat in slots 0-2, so the menu opened on GOAL LINE SNEAK on every down. The repair
                    swaps the three best normal-down sets into those slots: with ``--image`` ranked by the native
                    CPU lottery's share on normal downs (``lottery_ranking``), else by the sets' own 1st & 10
                    ratings and menu size (``page_one_order``). Nothing else moves.
2. ``pa_backfield`` A play-action BOOT (QB fake, then an authored Special Move 0x04 mode 1 to the boot point instead
                    of the native dropback) is listed only in formations whose QB alignment (under centre / pistol /
                    gun) and faking backs (within 2 yd) match the formation it was designed in (its catalog
                    ``home``); retail authors every play-action rollout under centre only. A play named for its
                    alignment ("Pistol ...") is listed only in pistol sets. TEN "Pistol Boot" (home Pistol
                    Doubles) was also listed in Gun Tight Slots, Gun Bunch X Nasty, Gun Trey Y-Flex, Gun Doubles
                    Tight and Singleback Bunch. Plain play action (fake, then the native 0x06 drop, which retail
                    uses from every alignment) keeps its sharing. Menus are then trimmed back to whole pages.
3. ``direct_snap``  The direct snap QB decoy's Release Downfield (0x18) uses mode 1 (relative to the player), as
                    retail's "H Direct Snap" does (8 of 8); the generator wrote mode 0 (relative to the ball).
4. ``spot_out``     A route "straight, settle inside (kind 8), lateral out (kind 5)" crosses its own stem (native
                    route initializer 0x229AE0: up 5, back 0.9 yd inside, then out across the stem: the loop). The
                    settle becomes kind 7 (settle outside), so the route sits and slides out without crossing.

    python3 pb/v2/sanity_b778.py --check                 # counts per rule, exit 1 when anything would change
    python3 pb/v2/sanity_b778.py --apply [--rule NAME]   # repair the packs, catalogs and both manifests

PROVED OFFLINE on the packs' own data; gameplay effects are for the emulator / Noah to witness.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

RULES = ("page_one", "pa_backfield", "direct_snap", "spot_out")

# Native lottery curve A (0x207EF0): weight of a situation rating r at x = r - 2.
CURVE_A = {0: 0.5, 1: 2.0, 2: 1.0, 3: 0.5, 4: 0.1}
# Sets that never open the menu: goal line / short yardage and the wildcat gadget set.
SPECIAL_TAGS = ("goal", "short")
SPECIAL_NAMES = ("Gun Wildcat",)
PAGE = 3
QB, HB, FB = 0, 10, 11
FAKE_HANDOFF, RELEASE, ROUTE, SPECIAL_MOVE = 0x14, 0x18, 0x12, 0x04
BACK_DEPTH_CM = -228.6            # a back stands 2.5 yd or more behind the line
BACK_TOLERANCE_CM = 182.88        # 2 yd


def _tag(name: str) -> str:
    from mod_editor.core import nfl2k5_offense_concepts as oc
    spec = oc.FORMATIONS.get(name)
    return spec.tag if spec is not None else "base"


def is_special(name: str) -> bool:
    return name in SPECIAL_NAMES or _tag(name) in SPECIAL_TAGS


def first_down_weight(situation) -> float:
    """1st & 10 formation weight of the native lottery: downs 1-2 at 10 yards blend to the medium rating."""
    if not situation:
        return 0.0
    return CURVE_A.get(int(situation[1]), 0.1)


def page_one_order(names, situations, links) -> list[str]:
    """Fallback ranking (no compiled book): 1st & 10 weight of the formation's own ratings, then menu size."""
    return sorted((n for n in names if not is_special(n)),
                  key=lambda n: (-first_down_weight(situations.get(n)), -links.get(n, 0), names.index(n)))


# Normal downs the page-one ranking averages over (selection_model situations).
NORMAL_DOWNS = (dict(down=1, distance=10, yard=25), dict(down=1, distance=10, yard=60),
                dict(down=2, distance=8, yard=50), dict(down=2, distance=5, yard=35))


def lottery_ranking(book_raw: bytes) -> list[str]:
    """Offense formations of a compiled book ranked by the native CPU lottery's mean share on normal downs
    (``pb/v2/selection_model``: personnel group 0x2093F0, then formation 0x2081B0). The situation ratings it reads
    were fitted to each team's real 2025 formation shares, so the top set is the team's own base call."""
    from pb.v2 import selection_model as sm
    bk = sm.book_from(book_raw)
    acc: dict = {}
    for sit in NORMAL_DOWNS:
        _, pform, _ = bk.distribution(sit)
        for fi, p in pform.items():
            acc[fi] = acc.get(fi, 0.0) + p
    name = {f["index"]: f["name"] for f in bk.forms}
    return [name[fi] for fi, _p in sorted(acc.items(), key=lambda kv: (-kv[1], kv[0])) if not is_special(name[fi])]


# ---------------------------------------------------------------------------
# rule 1: page one
# ---------------------------------------------------------------------------

def _slot_key(f):
    return (f.get("replace_index") is None, f.get("replace_index") or 0)


def page_one_slots(names: list[str], ranked: list[str]) -> list[str]:
    """``names`` in slot order -> the same names in their new slot order: every special set in the first PAGE slots
    trades places with the best-ranked normal set outside them. Nothing else moves."""
    order = list(names)
    for i in range(min(PAGE, len(order))):
        if not is_special(order[i]):
            continue
        best = next((n for n in ranked if n in order and order.index(n) >= PAGE), None)
        if best is None:
            break
        j = order.index(best)
        order[i], order[j] = order[j], order[i]
    return order


def fix_page_one(doc: dict, ranking: list[str] | None = None) -> list:
    forms = sorted(doc["formations"], key=_slot_key)
    names = [f["custom_name"] for f in forms]
    situations = {f["custom_name"]: f.get("situation") for f in forms}
    links = {f["custom_name"]: len(doc["menus"].get(f["id"], [])) for f in forms}
    ranked = [n for n in (ranking or []) if n in names and not is_special(n)]
    ranked += [n for n in page_one_order(names, situations, links) if n not in ranked]
    order = page_one_slots(names, ranked)
    slots = [(f.get("replace_index"), f.get("replace_name", "")) for f in forms]
    by_name = {f["custom_name"]: f for f in forms}
    changes = []
    for k, name in enumerate(order):
        f = by_name[name]
        if (f.get("replace_index"), f.get("replace_name", "")) != slots[k]:
            changes.append(dict(slot=k if slots[k][0] is not None else None, now=name, was=names[k],
                                replace_index=slots[k][0]))
        f["replace_index"], f["replace_name"] = slots[k]
    # appended formations take indices in list order: keep the list in slot order so the file reads as the book does
    doc["formations"] = [by_name[n] for n in order]
    return changes


# ---------------------------------------------------------------------------
# rule 2: play-action backfield
# ---------------------------------------------------------------------------

def qb_alignment(form: dict) -> str:
    z = next(z for (x, z), code in zip(form["slot_positions"], form["position_codes"]) if code & 31 == QB)
    return "uc" if z > -274.32 else ("pistol" if z > -420.0 else "gun")


def backs(form: dict) -> list:
    return sorted((x, z) for (x, z), code in zip(form["slot_positions"], form["position_codes"])
                  if code & 31 in (HB, FB) and z <= BACK_DEPTH_CM)


def backfield_compatible(home: dict, form: dict) -> bool:
    if qb_alignment(home) != qb_alignment(form):
        return False
    a, b = backs(home), backs(form)
    return len(a) == len(b) and all(abs(x1 - x2) <= BACK_TOLERANCE_CM and abs(z1 - z2) <= BACK_TOLERANCE_CM
                                    for (x1, z1), (x2, z2) in zip(a, b))


def is_play_action(play: dict) -> bool:
    return play.get("play_type") == "pa_pass" and any(
        node[0] == FAKE_HANDOFF for chain in play["assignments"] if chain for node in chain)


def is_pa_boot(play: dict) -> bool:
    """Play action whose QB leaves the fake on an authored Special Move (0x04 mode 1, the boot / rollout point)
    instead of the native dropback: retail authors these per QB alignment (every retail PA rollout is under centre)."""
    qb = play["assignments"][0] or []
    return is_play_action(play) and any(n[0] == SPECIAL_MOVE and int(n[1][0]) == 1 for n in qb)


def alignment_named(name: str) -> str | None:
    """A play whose name starts with its QB alignment ("Pistol Boot") belongs only in sets with that alignment."""
    return "pistol" if name.split(" ", 1)[0] == "Pistol" else None


def fix_pa_backfield(doc: dict, catalog: dict) -> list:
    forms = {f["id"]: f for f in doc["formations"]}
    by_name = {f["custom_name"]: f for f in doc["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    home = {r["play"]: r["home"] for r in catalog["plays"]}
    uses = Counter(pid for menu in doc["menus"].values() for pid in menu)
    changes = []
    drops = {fid: [] for fid in doc["menus"]}
    for fid, menu in doc["menus"].items():
        for pid in menu:
            p = plays[pid]
            if pid not in home or home[pid] not in by_name:
                continue
            h = by_name[home[pid]]
            if h["id"] == fid:
                continue
            named = alignment_named(p["custom_name"])
            if named is not None:
                if qb_alignment(forms[fid]) == named:
                    continue
            elif not is_pa_boot(p) or backfield_compatible(h, forms[fid]):
                continue
            if pid not in doc["menus"].get(h["id"], []):
                continue                              # never remove the last place a record is listed
            drops[fid].append(pid)
    for fid, bad in drops.items():
        menu = doc["menus"][fid]
        if not bad:
            continue
        # keep back as few of the mismatched links as needed when the menu cannot otherwise end on a whole page
        for keep_back in range(len(bad) + 1):
            drop = bad[:len(bad) - keep_back]
            trial = Counter(uses)
            for pid in drop:
                trial[pid] -= 1
            kept = [pid for pid in menu if pid not in drop]
            # whole pages again: drop shared links from the end (never the first page, never a record's last link)
            extra = []
            for pid in reversed(kept[PAGE:]):
                if (len(kept) - len(extra)) % PAGE == 0:
                    break
                if trial[pid] > 1 and pid not in bad:
                    extra.append(pid)
                    trial[pid] -= 1
            kept = [pid for pid in kept if pid not in extra]
            if len(kept) >= PAGE and len(kept) % PAGE == 0:
                break
        else:
            raise SystemExit(f"{doc['book']['team']} {forms[fid]['custom_name']}: cannot keep whole pages")
        uses = trial
        if not drop and not extra:
            continue
        doc["menus"][fid] = kept
        changes.append(dict(formation=forms[fid]["custom_name"], dropped=[plays[p]["custom_name"] for p in drop],
                            kept_mismatched=[plays[p]["custom_name"] for p in bad if p not in drop],
                            trimmed=[plays[p]["custom_name"] for p in extra], links=len(kept)))
    return changes


# ---------------------------------------------------------------------------
# rule 3: direct snap decoy
# ---------------------------------------------------------------------------

def fix_direct_snap(doc: dict) -> list:
    changes = []
    for p in doc["plays"]:
        if p.get("play_type") != "direct_snap":
            continue
        chain = p["assignments"][0]
        for node in chain or []:
            if node[0] == RELEASE and int(node[1][0]) == 0:
                node[1][0] = 1
                changes.append(p["custom_name"])
    return changes


# ---------------------------------------------------------------------------
# rule 4: spot out loop
# ---------------------------------------------------------------------------

def spot_out_nodes(chain) -> list[int]:
    """Indices of 'settle inside' nodes (route kind 8) between a straight stem (kind 0) and a lateral out (kind 5)."""
    segs = [(i, int(n[1][0])) for i, n in enumerate(chain or []) if n[0] == ROUTE]
    return [segs[k][0] for k in range(1, len(segs) - 1)
            if segs[k][1] == 8 and segs[k - 1][1] == 0 and segs[k + 1][1] == 5]


def fix_spot_out(doc: dict) -> list:
    changes = []
    for p in doc["plays"]:
        for slot, chain in enumerate(p["assignments"]):
            for i in spot_out_nodes(chain):
                chain[i][1][0] = 7
                changes.append((p["custom_name"], slot))
    return changes


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def fix_doc(doc: dict, catalog: dict, rules=RULES, ranking=None) -> dict:
    out = {}
    if "page_one" in rules:
        out["page_one"] = fix_page_one(doc, ranking)
    if "pa_backfield" in rules:
        out["pa_backfield"] = fix_pa_backfield(doc, catalog)
    if "direct_snap" in rules:
        out["direct_snap"] = fix_direct_snap(doc)
    if "spot_out" in rules:
        out["spot_out"] = fix_spot_out(doc)
    return out


def _update_catalog(cat: dict, doc: dict) -> None:
    fname = {f["id"]: f["custom_name"] for f in doc["formations"]}
    names = {p["id"]: p["custom_name"] for p in doc["plays"]}
    rows = {f["formation"]: f for f in cat["formations"]}
    for f in doc["formations"]:
        if f["custom_name"] in rows:
            rows[f["custom_name"]]["index"] = f.get("replace_index")
    for fid, menu in doc["menus"].items():
        if fname.get(fid) in rows:
            rows[fname[fid]]["menu"] = [names[p] for p in menu]
    listed = {}
    for fid, menu in doc["menus"].items():
        for pid in menu:
            listed.setdefault(pid, []).append(fname[fid])
    for r in cat["plays"]:
        if r["play"] in listed:
            r["formations"] = listed[r["play"]]


def main(argv=None) -> int:
    from mod_editor.core import nfl2k5_playbook_pack as packs
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rule", action="append", choices=RULES)
    ap.add_argument("--json", type=Path, help="write the per-team change list here")
    ap.add_argument("--image", type=Path, help="retail XISO: rank page one by the CPU lottery of the compiled book")
    ap.add_argument("--xbe", type=Path, help="retail default.xbe (with --image)")
    ap.add_argument("--books", type=Path, help="directory of composed TEAM.play books of these packs (verify3 --books, "
                                               "or a disc's PLAY entries): rank page one by their CPU lottery")
    args = ap.parse_args(argv)
    if args.check == args.apply:
        ap.error("pass exactly one of --check / --apply")
    rules = tuple(args.rule or RULES)
    from pb.v2 import generator as gen
    manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text())
    totals, report = Counter(), {}
    image = None
    if args.image and "page_one" in rules:
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        image = OuterImage(args.image).__enter__()
        xbe = args.xbe.read_bytes() if args.xbe else None
    for row in manifest["teams"]:
        path = ROOT / row["pack"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        catp = ROOT / "pb/v2/catalogs" / f"{row['team']}.json"
        cat = json.loads(catp.read_text(encoding="utf-8"))
        ranking = None
        if args.books is not None and "page_one" in rules:
            ranking = lottery_ranking((args.books / f"{row['team']}.play").read_bytes())
        elif image is not None:
            compiled = packs.apply_pack_to_resource(image.read_entry(BOOK_ENTRIES[row["team"]]), packs.load_pack(path),
                                                    asset_id="book:" + row["team"], xbe=xbe)
            ranking = lottery_ranking(compiled.replacement)
        changes = fix_doc(doc, cat, rules, ranking)
        if ranking is not None:
            changes["page_one_ranking"] = ranking[:6]
        report[row["team"]] = changes
        for k, v in changes.items():
            if k in RULES:
                totals[k] += len(v)
            if k == "pa_backfield":
                totals["pa_links_dropped"] += sum(len(c["dropped"]) for c in v)
                totals["page_links_trimmed"] += sum(len(c["trimmed"]) for c in v)
        if args.check or not any(changes.get(r) for r in RULES):
            continue
        pack = packs.loads_pack(json.dumps(doc))
        packs.save_pack(pack, path)
        _update_catalog(cat, doc)
        catp.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8", newline="\n")
        row["links"] = sum(len(m) for _f, m in pack.menus)
        row["semantic_sha256"] = gen.semantic_digest(packs.loads_pack(pack.dumps()))
    if args.apply and any(totals.values()):
        (ROOT / "pb/v2/manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8",
                                                    newline="\n")
        league = json.loads((ROOT / "pb/league_manifest.json").read_text())
        by = {r["team"]: r for r in manifest["teams"]}
        for r in league["teams"]:
            if r["team"] in by:
                r["semantic_sha256"] = by[r["team"]]["semantic_sha256"]
        (ROOT / "pb/league_manifest.json").write_text(json.dumps(league, indent=2) + "\n", encoding="utf-8",
                                                      newline="\n")
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(dict(totals))
    return 1 if args.check and any(totals[r] for r in rules) else 0


if __name__ == "__main__":
    raise SystemExit(main())
