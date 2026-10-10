#!/usr/bin/env python3
"""b77 / a2 prep: every quarterback, kicker and punter on the SOFTDRINK 2K28 disc, with the handedness the game holds.

Read-only. No real-world handedness is collected or invented here: the list states what the disc says today, where
that value lives (so a corrected value can be written exactly there), and where it most likely came from.

The value is the "Best Hand" bit of the 84-byte player record: byte +0x18, bit 1 (mask 0x02), 0 = Left, 1 = Right
(the row the game's own roster editor toggles). Twelve gameplay sites read it through the player's roster record
(entity +0x3C, see CONSUMERS) to choose handed animations, so it decides which way a quarterback throws and, as Noah saw
with Harrison Butker on the 2026 Chiefs, which foot a kicker uses.

  python3 tools/b77/a2_player_list.py --disc DISC.iso --retail RETAIL.iso --out a2_PLAYER_LIST.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_espn25_rosters as er  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

SCHEMA = "b77/a2_player_list/v1"
POSITIONS = ("QB", "K", "P")
HAND_FIELD = rr.FIELD_BY_NAME["hand"]
WRAPPER = 32                 # a ROST resource is a 32-byte wrapper, then the body the records' offsets count from
# Retail gameplay sites that test the roster record's Best Hand bit after loading the record from the player entity
# (+0x3C). They choose handed animation sets / mirror flags; which animation each one gates is NOT classified.
CONSUMERS = (0x1841F6, 0x18428D, 0x184324, 0x18AD70, 0x1B4E8C, 0x1BBB7F, 0x1E5E57, 0x1E775F, 0x2010AC, 0x2EF3F6,
             0x30B608, 0x311A26)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hand_name(value):
    return rr.HANDS[value]


def record_location(resource, outer, offset, extra=None):
    """Where the bit lives: byte `resource_offset` of the resource, mask 0x02 (0 = Left, 1 = Right)."""
    location = dict(resource=resource, outer_index=outer, record_offset=offset,
                    hand_byte_offset=WRAPPER + offset + HAND_FIELD.offset, mask=0x02)
    location.update(extra or {})
    return location


def main_roster_rows(main, retail_main, outer, positions=POSITIONS):
    doc, retail = rr.RosterDocument(main[WRAPPER:]), rr.RosterDocument(retail_main[WRAPPER:])
    retail_by_slot = {(p.pool, p.index): p for p in retail.players}
    retail_primary = max(p.index for p in retail.players if p.pool == "primary") + 1
    rows = []
    for player in doc.players:
        position = player.record.position_name
        values = player.record.values
        clubs = [doc.teams[i] for i in player.teams if doc.teams[i].kind == 0]
        others = [doc.teams[i].display for i in player.teams if doc.teams[i].kind != 0]
        # QB, K and P, and also any player on a club at another position whose record says Left: the game mirrors
        # animations for him too, and a Left there is almost certainly a reused slot's leftover
        listed_as = ("quarterback, kicker or punter" if position in POSITIONS else
                     "club player at another position whose record says Left" if clubs and not values["hand"] else
                     "listed by --all-positions" if position in positions else None)
        if listed_as is None:
            continue
        if clubs:
            team, group, abbreviation = clubs[0].display, "club", clubs[0].abbreviation
        else:
            team = abbreviation = None
            group = "free_agent_pool" if player.pool == "primary" else "secondary_pool"
        slot = retail_by_slot.get((player.pool, player.index))
        if slot is None:
            basis = ("record added by the roster capacity successor (index %d, past the retail %d); the bit is its "
                     "donor copy" % (player.index, retail_primary))
            inherited = None
        elif (slot.first, slot.last) == (player.first, player.last):
            basis = "the retail 2004 roster record of the same player (Visual Concepts data)"
            inherited = None
        else:
            inherited = dict(name=f"{slot.first} {slot.last}", position=slot.record.position_name,
                             hand=hand_name(slot.record.values["hand"]))
            basis = ("the record slot was reused for this player; the bit is the retail 2004 occupant's"
                     + (" (unchanged)" if slot.record.values["hand"] == values["hand"] else " (since changed)"))
        rows.append(dict(
            id=f"main:{player.pool}:{player.index}", scope="main_roster_2026", listed_as=listed_as, group=group, team=team,
            team_abbreviation=abbreviation, also_on=others, season=2026, name=f"{player.first} {player.last}",
            first=player.first, last=player.last, position=position, jersey=values["jersey"],
            years_pro=values["years_pro"], college=player.college, hand=hand_name(values["hand"]),
            hand_bit=values["hand"], basis=basis, retail_slot_occupant=inherited,
            record=record_location("main.ROST", outer, player.offset, dict(pool=player.pool, index=player.index))))
    return rows


def moment_team_files(disc_rows, data, descriptors, menu_rows=None):
    """{file name: {team, season, moments: [...]}} for every team file the 51 menu entries load, in physical order.
    A retail moment loads the retail historic file of its (franchise, season); a moment of rows 26 to 51 loads its own
    new file (nfl2k5_espn25_more_moments.table_entries)."""
    by_pair = {(d["selector"], d["year"]): d["filename"] for d in descriptors}
    authored = {key: filename for key, filename, _e, _s, _i in mm.table_entries(data)}
    used = {}
    for number, row in enumerate(disc_rows, 1):
        for side in ("away", "home"):
            selector, season = row[side]
            filename = authored[row[side + "_key"]] if number > mm.RETAIL_COUNT else by_pair[(selector, season)]
            used.setdefault(filename, []).append(dict(row=number, menu_row=(menu_rows or {}).get(number), title=row["title"],
                                                      date=row["date"], side=side))
    return used


def identity_birth_date(source):
    """ISO birth date from an exact-roster manifest player's source identity ('derek|kennard|19620909'), else None."""
    parts = str((source or {}).get("source_identity") or "").split("|")
    day = parts[-1] if len(parts) == 3 else ""
    return f"{day[:4]}-{day[4:6]}-{day[6:]}" if len(day) == 8 and day.isdigit() else None


def team_file_rows(raw, filename, outer, moments, provenance, positions=POSITIONS, born=None, retail_raw=None,
                   authored=False):
    doc = rr.RosterDocument(raw[WRAPPER:WRAPPER + struct.unpack_from("<I", raw, 4)[0]])
    team = doc.teams[0]
    retail_doc = rr.RosterDocument(retail_raw[WRAPPER:WRAPPER + struct.unpack_from("<I", retail_raw, 4)[0]]) \
        if retail_raw else None
    retail_slot = {p.index: p for p in retail_doc.players} if retail_doc else {}
    rows = []
    for player in sorted(doc.players, key=lambda p: p.index):
        position = player.record.position_name
        if position not in positions:
            continue
        values = player.record.values
        source = (provenance or {}).get(player.index) or {}
        if authored:
            basis = {"retail 2004 identity": "the retail 2004 roster record of the same player (Visual Concepts data)",
                     "left-handed list": "the quarterback list in tools/nfl2k5_espn25_more_moments_spec.json (Wikipedia, "
                                         "read 2026-09-23): not checked against a primary source",
                     "default right": "no source: the generator writes Right for everyone not found left-handed",
                     "sourced (b77 a2 handedness)": "sourced by b77 a2 (the manifest in this checkout postdates the v0.5 disc, "
                                                    "which holds the generator's earlier value)"}[
                source.get("hand_basis", "default right")]
        else:
            # one of the 35 retail historic files the ESPN25 exact-roster option rewrote (names, numbers, positions and
            # ratings of the real season roster); every other byte of the record, the hand bit included, stayed the
            # retail record's
            occupant = retail_slot.get(player.index)
            if source.get("retained_retail_identity"):
                basis = "the retail 2004 historic record was kept for this player (Visual Concepts data)"
            else:
                basis = ("the exact-roster option put this player into a retail placeholder's record and kept the "
                         "placeholder's hand bit" + (f" ({occupant.first} {occupant.last}, "
                                                    f"{hand_name(occupant.record.values['hand'])})" if occupant else ""))
        rows.append(dict(
            id=f"team:{filename[:-4]}:{player.index}", scope="moment_roster", group="moment", team=team.display,
            team_abbreviation=team.abbreviation, season=int(filename.split("-")[2]), name=f"{player.first} {player.last}",
            first=player.first, last=player.last, position=position, jersey=values["jersey"],
            years_pro=values["years_pro"], birth_date=(born or {}).get(player.index) or identity_birth_date(source),
            hand=hand_name(values["hand"]),
            hand_bit=values["hand"], gsis_id=source.get("gsis_id") or None, team_key=authored or None, basis=basis,
            moments=moments,
            record=record_location(filename, outer, player.offset, dict(pool="primary", index=player.index))))
    return rows


def authored_birth_dates(key):
    """{roster index: ISO birth date} from the team's data CSV (authored teams only)."""
    import csv
    with open(ROOT / "data/nfl2k5_espn25_more_teams" / f"{key}.csv", newline="", encoding="utf-8") as handle:
        return {int(row["index"]): row["birth_date"] or None for row in csv.DictReader(handle)}


def build(disc, retail_iso, positions=POSITIONS):
    data = mm.Data.load()
    exact = {r["filename"]: r for r in json.loads(
        (ROOT / "data/nfl2k5_espn25_moment_rosters/manifest.json").read_text())["resources"]}
    with rr._outer_image()(retail_iso) as retail_image:
        retail_main, retail_situ = retail_image.read_entry(5), retail_image.read_entry(22)
        return _build(disc, retail_image, retail_main, retail_situ, data, exact, positions)


def _build(disc, retail_image, retail_main, retail_situ, data, exact, positions):
    with rr._outer_image()(disc) as image:
        main = image.read_entry(5)
        context = er.describe_context(main, retail_situ, image.entries)
        by_id = {entry.name_id: entry for entry in image.entries}
        rows = main_roster_rows(main, retail_main, 5, positions)
        every_main = main_roster_rows(main, retail_main, 5, tuple(rr.POSITIONS))
        every_team = []
        # the 51 moments as menu rows see them: retail rows decoded from the retail situation.iff, the rest authored
        from tools.b77 import menu_facts
        expected = menu_facts.expected_rows(retail_situ, data)
        order = menu_facts.display_order_from(expected)
        used = moment_team_files(expected, data, context["descriptors"], {p: d + 1 for d, p in enumerate(order)})
        manifest = json.loads((ROOT / "data/nfl2k5_espn25_more_teams/manifest.json").read_text())["teams"]
        key_by_file = {filename: key for key, filename, _e, _s, _i in mm.table_entries(data)}
        files = []
        for filename, moments in used.items():
            entry = by_id[mm.name_id(filename)]
            raw = image.read_entry(entry.index)
            key = key_by_file.get(filename)
            if key:
                provenance, retail_raw = {p["index"]: p for p in manifest[key]["players"]}, None
            else:
                provenance = {p["slot"]: p for p in exact[filename]["players"]}
                retail_raw = retail_image.read_entry({e.name_id: e for e in retail_image.entries}[mm.name_id(filename)].index)
            born = authored_birth_dates(key) if key else None
            team_rows = team_file_rows(raw, filename, entry.index, moments, provenance, positions, born, retail_raw,
                                       key)
            rows.extend(team_rows)
            every_team.extend(team_file_rows(raw, filename, entry.index, moments, provenance, tuple(rr.POSITIONS), born,
                                             retail_raw, key))
            files.append(dict(file=filename, outer_index=entry.index, kind="authored" if key else "retail historic",
                              team_key=key, bytes=len(raw), sha256=sha(raw), moments=moments,
                              qb_k_p=len(team_rows)))
    counts, others = {}, {}
    for row in rows:
        counts.setdefault(row["scope"], {}).setdefault(row["position"], {"Left": 0, "Right": 0})[row["hand"]] += 1
    for row in every_main + every_team:
        if row["position"] not in positions:
            others.setdefault(row["scope"], {}).setdefault(row["position"], {"Left": 0, "Right": 0})[row["hand"]] += 1
    return dict(
        schema=SCHEMA, purpose=("What the game holds today for every quarterback, kicker and punter, and where. "
                                "Values are NOT facts about the real players: the swarm sources them, then "
                                "tools/b77/a2_handedness.py applies the answers."),
        disc=dict(path=str(disc), size=Path(disc).stat().st_size, sha256=file_sha256(disc)),
        field=dict(name="hand", editor_label="Best Hand", record_bytes=rr.PLAYER_SIZE, byte_in_record=HAND_FIELD.offset,
                   bit=1, mask=0x02, values={"0": "Left", "1": "Right"},
                   read_by_gameplay_sites=[hex(va) for va in CONSUMERS],
                   meaning=("Quarterbacks: throwing hand. Kickers and punters: the kicking foot (Noah saw the 2026 Chiefs' "
                            "Harrison Butker kick left-footed; his record holds Left). The same bit is read for every "
                            "position by twelve animation sites; which animations each gates is not classified.")),
        moment_rows_note=("In `moments`, `row` is the physical (authoring) row 1..51 and `menu_row` is where the 25th "
                          "Anniversary menu shows that moment (chronological)."),
        counts=counts, other_positions_not_listed=others,
        other_positions_note=("The same bit is read for every position. These are the counts of the positions this list "
                              "leaves out (run with --all-positions to list them); their real handedness is rarely "
                              "documented, so they keep the value the game holds unless a source says otherwise."),
        team_files=files, players=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disc", required=True, type=Path)
    parser.add_argument("--retail", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--all-positions", action="store_true", help="list every position, not only QB, K and P")
    args = parser.parse_args(argv)
    document = build(args.disc, args.retail, tuple(rr.POSITIONS) if args.all_positions else POSITIONS)
    args.out.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(args.out), "players": len(document["players"]), "counts": document["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
