"""Identity-preserving, dated league refresh after the pack's original imports.

This is an opt-in roster-edits directive, never a replacement for arbitrary
rosters or existing franchise saves. New players require unused create slots.
The primary index remains the identity of every existing player.

b778-eq1: a created player's gear comes from the same position's class-generator
templates (nfl2k5_equipment_fit), so a dated receiver does not stay in the zero
Face Mask 1 that retail kickers and punters wear.  Existing players' gear is
never read or written.

b778-ap1: a created player's skin, generic face, body and checked dreads bit
come from the measured headshot table (nfl2k5_created_appearance), so the 2026
players are not all the Lightest default.  A row that carries its own nonzero
skin/face/dreads is authored and wins; hair style and photo id are never touched.
"""
from __future__ import annotations

import datetime

SCHEMA = "nfl2k5.roster_refresh.v1"
EXISTING_FIELDS = frozenset(("jersey", "position", "depth_rank", "depth_side"))
CONTRACT_FIELDS = frozenset(("contract_value", "contract_length", "contract_remaining",
                             "contract_type", "contract_bonus"))

# b780 b4-economy (row D6; v0.8 known issue "69 real players are on no club and not on the free agent list ... so a
# franchise may never use them", e.g. Michael Pittman, Kelvin Banks, Montez Sweat, Jaycee Horn). The dated plan lists
# every player on a 2026 injured reserve list (nflverse status RES) with his record and club, and the disc cannot seed
# the franchise's own injured reserve list (that list is made in game), so the old writer checked their identity and
# then put them on no club and on no free-agent list. In the v0.8 plan that is 81 players with records (the other 12
# records on no club are the retail legends and celebrities of the alias squads, not franchise players). Now an
# injured player rejoins his club's active roster with the contract he already has, unlocked at the overflow depth
# row, so the game's own weekly depth sort seats him by rating. A club that would go past 53 releases, to the free
# agents, the lowest-rated player at a position above the modern 53-man minimum, as the economy's smart cut-down does
# at the regular-season gate (Noah 10/28: "prioritize the lowest overall at a position where they have more than they
# need"), taking players on small deals first so a first-round pick or a paid veteran is not cut for the 53rd spot
# (never a specialist, never a player who just rejoined); that player's contract is cleared like any unsigned free
# agent's. An injured player without a contract or a club joins the free agents.
INJURED_STATUSES = frozenset(("RES",))
# tools/franchise_economy/runtime.c cut_min (b779 rc1: 2024 53-man rosters, atlantafalcons.com 2024-08-28), by position
# code QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE; with no OLB in the league (the one-pool scheme) OLB 0 and LB 5.
CUT_MINIMUMS = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 3, 2, 2, 3, 3, 3, 4)
# A "small deal": at most 60 a year in the record's contract units ($10,000 game; $600,000 game, $2.4M real at the
# economy's 1:4 display). Late-round rookie deals and minimum contracts are below it; first-round deals are above it.
SMALL_DEAL_PER_YEAR = 60
OVERFLOW_DEPTH_ROW = 7
LOCK_ROLES = ("rank", "side", "kr1", "kr2", "pr")
# b780 rst2 (Q43, Noah 11/03: "release the lowest-ranked non-starters first"): the injured-reserve pass never releases a
# player the dated chart lists as a starter (rank 1 at his own slot) while another player can go, and among the rest it
# releases the deepest chart rank first (a player the chart does not list at all is the deepest).
STARTER_CHART_RANK = 1
UNLISTED_CHART_RANK = 99


def charted_ranks(rows):
    """{index: his chart rank at his own slot} from the refresh rows' dated depth chart (``depth_source``)."""
    ranks = {}
    for row in rows:
        source = row.get("depth_source") or {}
        if str(source.get("pos_rank", "")).isdigit():
            ranks[row["index"]] = int(source["pos_rank"])
    return ranks


# b780 rst2 (coordinator 11/03: Noah asked for a full modern injured reserve in beta-80 and IR1 builds it): how a club that
# is over the 53-man limit because its injured players rejoined makes room. "release" is this release's policy: the
# lowest-ranked non-starters go to the free agents (_make_room). "ir" is reserved for IR1's format: the injured players
# would go on the club's injured reserve list and nobody would be released, so only _rejoin_injured's placement block and
# the caller's release bookkeeping change; _make_room is the one function the release policy lives in.
ROOM_POLICY = "release"


def _make_room(club, active, keep, position, minimums, ranks, big_deal, overall, limit):
    """Remove players from ``active`` (a list, changed in place) until it holds ``limit``; returns who left, in order.

    The release-for-room policy (Q43, Noah 11/03: "release the lowest-ranked non-starters first"). A charted starter
    (rank 1 at his own slot) goes last, after every position floor has been tried without him; among the rest the
    deepest chart rank goes first (a player the chart does not list is the deepest), then the pre-rst2 order: a player
    on a small deal, then the lowest rated. A player in ``keep`` (the injured who rejoined and the specialists) stays."""
    from . import nfl2k5_roster_records as rr

    left = []
    while len(active) > limit:
        counts = {}
        for index in active:
            counts[position[index]] = counts.get(position[index], 0) + 1
        victim = None
        for protect, floor in ((True, False), (True, True), (False, False), (False, True)):
            pool = [i for i in active if i not in keep and position[i] < 17 and
                    counts[position[i]] > (1 if floor else minimums[position[i]]) and
                    not (protect and ranks.get(i, UNLISTED_CHART_RANK) == STARTER_CHART_RANK)]
            if pool:
                victim = min(pool, key=lambda i: (-ranks.get(i, UNLISTED_CHART_RANK), big_deal(i), overall(i), i))
                break
        rr._require(victim is not None, f"{club}: no player can make room for an injured player")
        active.remove(victim)
        left.append(victim)
    return left


def _rejoin_injured(by, rows, teams, assigned):
    """The membership after the injured players rejoin: (active list by club index, rejoined, released, to FA).
    Called after the rows and the contract initializers are written, so it reads the final records."""
    from . import nfl2k5_practice_squad as ps
    from . import nfl2k5_roster_records as rr
    from .nfl2k5_my_career_prospects import native_overall

    rr._require(ROOM_POLICY == "release", f"unknown room policy {ROOM_POLICY!r}: only 'release' is wired")
    position = {i: p.record.values["position"] for i, p in by.items()}
    for row in rows:
        if "position" in row["fields"]:
            position[row["index"]] = row["fields"]["position"]

    def overall(index):
        record = by[index].record.copy()
        record.set("position", position[index])
        return native_overall(record)

    def big_deal(index):
        record = by[index].record
        return record.get("contract_value") > SMALL_DEAL_PER_YEAR * max(1, record.get("contract_length"))

    ranks = charted_ranks(rows)
    placed, to_free = {}, []
    by_team = {t["team"]: t for t in teams}
    taken = set(assigned)
    for row in rows:
        if row.get("status") not in INJURED_STATUSES or row["index"] in taken:
            continue
        record = by[row["index"]].record
        team = by_team.get(row.get("team"))
        if team is None or record.get("contract_length") < 1 or record.get("contract_value") < 1:
            to_free.append(row["index"])
        else:
            placed.setdefault(team["index"], []).append(row["index"])
        taken.add(row["index"])
    has_olb = any(position[i] == 10 for t in teams for i in t["active"])
    minimums = list(CUT_MINIMUMS)
    if not has_olb:
        minimums[10], minimums[11] = 0, 5
    actives, released = {}, []
    for team in teams:
        active = list(team["active"]) + placed.get(team["index"], [])
        keep = set(placed.get(team["index"], ())) | {v for v in team["specialists"].values() if v is not None}
        released.extend(_make_room(team["team"], active, keep, position, minimums, ranks, big_deal, overall,
                                   ps.ACTIVE_LIMIT))
        actives[team["index"]] = active
    rejoined = {i for ids in placed.values() for i in ids}
    return actives, rejoined, released, to_free


# The dated refresh's native depth pairs (every club position on the v0.8 disc): the n-th player of a position's
# chart (0-based) holds rank row n and side row NATIVE_SIDE_ROWS[n] (n past the table: side row n). Rank row 0 is the
# left starter (LG, LT, LDT, LCB, MIKE ...), side row 0 the right one (RG, RT, RDT, RCB, WILL ...), side row 1 the
# third (SAM, the 3-4 right tackle); the depth-chart getter 0x242AE0 finds no one for a row nobody holds.
NATIVE_SIDE_ROWS = (2, 0, 1)


def native_depth_pair(order):
    """(rank row, side row) of the ``order``-th player (0-based) of a position's chart, as the refresh writes it."""
    if order >= OVERFLOW_DEPTH_ROW:
        return OVERFLOW_DEPTH_ROW, OVERFLOW_DEPTH_ROW
    return order, NATIVE_SIDE_ROWS[order] if order < len(NATIVE_SIDE_ROWS) else order


def depth_slots(rows):
    """{index: (slot, rank)} from the refresh rows' dated depth chart (``depth_source`` pos_abb and pos_rank)."""
    slots = {}
    for row in rows:
        source = row.get("depth_source") or {}
        if source.get("pos_abb") and str(source.get("pos_rank", "")).isdigit():
            slots[row["index"]] = (source["pos_abb"], int(source["pos_rank"]))
    return slots


def _reseat_chains(by, planned, active, rejoined, slots):
    """b780 roster1: close the depth charts a release for room left open. Returns the indices whose rows moved.

    The injured-reserve pass (b4-economy D6) releases the lowest-rated player at a position above its minimum, and
    that player can hold a locked row (v0.9 RC: 38 position charts on 24 clubs, among them the left guards of CAR and
    MIN, HOU's MIKE, GB's right guard and right defensive tackle, LAC's right defensive tackle and LV's right corner;
    the v0.8 disc had none). The disc then holds a row no player holds (the getter 0x242AE0 finds no one there): a
    lineup read from it falls back to the native list order, and the depth locks compactor closes it only at the first
    depth-chart visit or weekly pass, by moving everyone below up one (CAR's right guard Hunt to left guard).

    Each chart keeps the dated order (the rank rows the refresh wrote). The released player's place goes to the next
    player the dated chart lists at his own slot (Bullock, CAR LG1, makes room for Simpkins, LG2; Hunt stays the
    right guard); with none listed, the players below him move up one. Everyone then takes the native pairs for the
    new order, locked as before, so no row is empty and no player holds two starting rows. A chart that lost no one
    does not move, and the injured players who rejoined stay unlocked at the overflow row."""
    present = set(active)
    gone = {i for i in planned if i not in present and by[i].record.get("depth_rank") < OVERFLOW_DEPTH_ROW}
    moved = []
    for position in sorted({by[i].record.get("position") for i in gone}):
        chart = sorted((i for i in set(active) - rejoined | gone
                        if by[i].record.get("position") == position
                        and by[i].record.get("depth_rank") < OVERFLOW_DEPTH_ROW),
                       key=lambda i: (by[i].record.get("depth_rank"), by[i].record.get("depth_side"), i))
        at = 0
        while at < len(chart):
            index = chart[at]
            if index not in gone:
                at += 1
                continue
            chart.pop(at)
            slot = slots.get(index)
            same = [i for i in chart[at:] if slot and slots.get(i, ("", 0))[0] == slot[0] and slots[i][1] > slot[1]]
            if same:
                pick = min(same, key=lambda i: (slots[i][1], chart.index(i)))
                chart.remove(pick)
                chart.insert(at, pick)
        for order, index in enumerate(chart):
            record = by[index].record
            want = native_depth_pair(order)
            if (record.get("depth_rank"), record.get("depth_side")) != want:
                record.set("depth_rank", want[0])
                record.set("depth_side", want[1])
                moved.append(index)
    return moved


def _seat_lone_rejoined(by, active, rejoined):
    """b780 roster1: an injured player who rejoins as his club's only player at his position (NE's fullback Reggie
    Gilliam, LAC's Alec Ingold) takes that position's first rows, unlocked, instead of the overflow row, so the
    position's row 0 is not empty until the first weekly sort. Returns the indices seated."""
    positions = {}
    for index in active:
        record = by[index].record
        positions.setdefault(record.get("position"), []).append(index)
    seated = []
    for members in positions.values():
        if any(i not in rejoined for i in members):
            continue                                   # the club has a player of its own there: the sort decides
        lone = sorted(members)
        for order, index in enumerate(lone):
            rank, side = native_depth_pair(order)
            by[index].record.set("depth_rank", rank)
            by[index].record.set("depth_side", side)
            seated.append(index)
    return seated


def _repair_create_buffers(doc):
    """Keep each unused CAP name pair exclusive and adjacent for native creation.

    Imported packs can contain disjoint placeholder strings. The native creator
    takes the first vacant record and writes two 34-byte names, so merely having
    unused records is insufficient. Allocate only inside the known name pool.
    """
    from . import nfl2k5_roster_records as rr
    repaired = 0
    for player in doc.by_pool("primary"):
        flags = player.record.encode()[8]
        if not flags & 1 or flags & 4:
            continue
        rr._require(player.group == "pool" and player.first == player.last == "****************",
                    "Unexpected vacant create-player record")
        keys = ("first_name_pointer", "last_name_pointer")
        offsets = [doc._pointer_target(player.offset, k) for k in keys]
        if offsets[1] == offsets[0] + 34 and all(doc.name_refs[o] == 1 for o in offsets):
            continue
        rr._require(any(size >= 68 for size in doc.names.free.values()),
                    "No exclusive create-player name buffer available")
        start, capacity = doc.names._take_free(68)
        rr._require(capacity == 68, "Unexpected create-player buffer size")
        for i, (key, old) in enumerate(zip(keys, offsets)):
            target = start + i * 34
            doc.names._write(target, 34, "****************")
            field = player.offset + rr.FIELD_BY_NAME[key].offset
            doc.set_rel(field, target)
            player.record.values[key] = int.from_bytes(doc.body[field:field + 4], "little")
            doc.name_refs[target] = 1
            doc.name_refs[old] -= 1
            if not doc.name_refs[old]:
                del doc.name_refs[old]
                doc.names.release_if_unused(old)
        repaired += 1
    return repaired


def _without_suffix(last):
    """The surname without a separate generational suffix (Jr., Sr., II, III, IV, V); every other character exact.

    b778 sx1 keeps the suffix on real players' names ("Cedrick Wilson Jr.") and treats it as a display spelling of
    the same person (nfl2k5_free_agents compares surnames this way); a refresh dated before that change still names
    the same player without it."""
    import re
    return re.sub(r"\s+(?:jr|sr|ii|iii|iv|v)\.?$", "", last.strip(), flags=re.IGNORECASE)


def _same_person(player, first, last, birth, alternates=()):
    """``alternates``: other birth dates the plan accepts for this record (a sourced birth-date correction, below)."""
    return ((player.first, _without_suffix(player.last)) == (first, _without_suffix(last))
            and str(player.record.birth_date) in (birth, *alternates))


def apply_body(body, plan):
    from . import nfl2k5_roster_records as rr
    from . import nfl2k5_college_check as college_check
    from . import nfl2k5_created_appearance as created_appearance
    from . import nfl2k5_equipment_fit as equipment_fit
    from . import nfl2k5_practice_squad as ps

    appearance_data = created_appearance.load_data()
    appearance_created = []
    appearance_written = {}

    rr._require(plan.get("schema") == SCHEMA, "Unknown roster refresh schema")
    datetime.date.fromisoformat(plan["as_of"])
    doc = rr.RosterDocument(bytes(body), scheme="one_pool", reference_year=2026)
    rr._require(doc.version in (17, 18), "Roster refresh is for the disc, not a franchise save")
    from . import nfl2k5_spare_capacity as spare
    primary_count = len(doc.by_pool("primary"))
    # 2619: the pack's spare capacity; more on a replay after the import floor (b775) added blank records,
    # or after the b778 fa4 capacity growth (version 18), which validates its own moved tables.
    if doc.version == 18:
        spare.extended_layout(body)
        rr._require(primary_count >= spare.PRIMARY_AFTER, "Refresh needs the pack's 2619-player capacity")
    else:
        rr._require(spare.PRIMARY_AFTER <= primary_count <= spare.PRIMARY_AFTER + spare.MAX_FLOOR_RECORDS,
                    "Refresh needs the pack's 2619-player capacity")
    by = {p.index: p for p in doc.by_pool("primary")}
    # b780 rst2 (Q48, Logan Jones CHI C: the plan's guard had 2001-10-29, nflverse roster_2026 and players.csv of 10/28 and
    # 11/03 list 2001-10-19): a record may carry either date of a sourced correction; the correction writes the new one.
    corrections = {c["index"]: c for c in plan.get("birth_corrections", ())}
    rr._require(len(corrections) == len(plan.get("birth_corrections", ())), "Duplicate birth correction")
    for c in corrections.values():
        rr._require({"first", "last", "was", "birth_date"} <= set(c) and str(c.get("source", "")).startswith("https://"),
                    "A birth correction needs the name, both dates and its source")
        datetime.date.fromisoformat(c["was"])
        datetime.date.fromisoformat(c["birth_date"])

    def alternates(index):
        c = corrections.get(index)
        return (c["was"], c["birth_date"]) if c else ()

    guards = plan["identity_guards"]
    rr._require(len({g[0] for g in guards}) == len(guards), "Duplicate identity guard")
    for index, first, last, birth in guards:
        p = by.get(index)
        rr._require(p is not None and _same_person(p, first, last, birth, alternates(index)),
                    f"Pack identity guard failed at {index}")
    rows = plan["players"]
    rr._require(len({r["index"] for r in rows}) == len(rows), "Duplicate refresh identity")
    rr._require(len({r["gsis_id"] for r in rows}) == len(rows), "Duplicate source identity")
    for row in rows:
        p = by.get(row["index"])
        rr._require(p is not None and p.group != "draft_class", "Refresh touches absent/draft record")
        same = _same_person(p, row["first"], row["last"], row["birth_date"], alternates(row["index"]))
        vacant = (p.index >= 2464 and p.group == "pool" and
                  p.first == p.last == "****************" and p.record.get("player_type") == 1)
        rr._require(same or (row.get("new") is True and vacant),
                    f"Refresh identity mismatch at {p.index}: {p.display}")
        rr._require(row.get("source") and row.get("gsis_id"), "Refresh needs source evidence")
        fields = row["fields"]
        rr._require(all(k not in rr.POINTER_FIELDS for k in fields), "Refresh cannot import pointers")
        if not row.get("new"):
            rr._require(set(fields) <= EXISTING_FIELDS, "Refresh would replace an existing player's data")
        else:
            rr._require(set(rr.RATING_BYTE_ORDER) <= set(fields), "New player needs model ratings")
    teams = plan["teams"]
    rr._require([t["index"] for t in teams] == list(range(32)), "Refresh needs all 32 clubs")
    assigned = []
    for team, row in zip(doc.teams, teams):
        rr._require(team.abbreviation == row["team"], "Refresh team identity mismatch")
        active, reserves = row["active"], row["reserves"]
        rr._require(42 <= len(active) <= 53 and len(reserves) <= ps.RESERVE_LIMIT,
                    "Refresh exceeds supported active/reserve capacity")
        assigned.extend(active + reserves)
        rr._require(set(row["specialists"]) == set(rr.SPECIAL_TEAM_OFFSETS), "Missing specialist slots")
        rr._require(all(v is None or v in active for v in row["specialists"].values()),
                    "Specialist is not on this active roster")
    owned = set(assigned)
    assigned.extend(plan["free_agents"])
    rr._require(len(assigned) == len(set(assigned)) and all(i in by for i in assigned),
                "Refresh has duplicate or absent membership")
    rr._require(all(by[i].group != "draft_class" for i in assigned), "Draft player in refresh membership")
    rr._require(set(assigned) <= ({g[0] for g in guards} | {r["index"] for r in rows}),
                "Membership contains an unguarded player")
    rr._require(len(plan["free_agents"]) <= doc.free_agent_capacity, "Free-agent list is full")
    contracts = plan.get("contract_initializations", [])
    rr._require(len({r["index"] for r in contracts}) == len(contracts), "Duplicate contract initializer")
    for row in contracts:
        fields = row["fields"]
        rr._require(row["index"] in owned and set(fields) == CONTRACT_FIELDS,
                    "Contract initializer must describe an owned player and all five fields")
        rr._require(row.get("source", "").startswith("https://") and row.get("rule"),
                    "Modeled contract needs its source and rule")
        rr._require(all(type(v) is int for v in fields.values()) and
                    1 <= fields["contract_length"] <= 15 and
                    1 <= fields["contract_remaining"] <= fields["contract_length"] and
                    1 <= fields["contract_value"] <= 65535 and
                    0 <= fields["contract_type"] <= 7 and 0 <= fields["contract_bonus"] <= 7,
                    "Invalid native contract initializer")
    # All identity/capacity gates precede mutation of this private document (the injured-reserve placement below
    # reads the records as this refresh writes them, so its own gates run after the rows; a refusal there still
    # leaves the caller's body untouched).
    for index, c in corrections.items():
        year, month, day = (int(x) for x in c["birth_date"].split("-"))
        for key, value in (("birth_year", year), ("birth_month", month), ("birth_day", day)):
            by[index].record.set(key, value)
    added = 0
    for row in rows:
        p = by[row["index"]]
        if row.get("new") and p.first == "****************":
            names = {k: p.record.values[k] for k in ("first_name_pointer", "last_name_pointer")}
            p.record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
            p.record.values.update(names)
            for k, v in row["fields"].items():
                p.record.set(k, v)
            p.record.set("player_type", rr.FLAG_NFL_PLAYER)
            # b778-ap1: the row's identity/ratings arrive without an appearance; use the measured headshot
            # table (skin/face/BMI body/checked dreads).  A row with its own nonzero skin/face/dreads wins.
            written = created_appearance.apply(p, row["fields"], row["gsis_id"], appearance_data)
            if written:
                appearance_written[row["gsis_id"]] = written
            appearance_created.append(row["gsis_id"])
            # b778-eq1: a created record keeps the nflverse row's identity/ratings only; its gear comes
            # from the position's own class-generator templates (a WR is not left in Face Mask 1).
            equipment_fit.fill_created_player(doc, p, supplied=row["fields"])
            doc.set_name(p, "first", row["first"])
            doc.set_name(p, "last", row["last"])
            # b778 fr1: never leave the record without a college (the Contracts and Free Agents panel
            # reads it without a null check); unknown or blank names take the table's "None".
            doc.set_college(p, college_check.resolve_index(doc.colleges, row.get("college")))
            added += 1
        else:
            # A replay must preserve later ratings, appearance and history edits.
            for k, v in row["fields"].items():
                if k in EXISTING_FIELDS:
                    p.record.set(k, v)
    initialized_contracts = 0
    for row in contracts:
        rec = by[row["index"]].record
        if rec.get("contract_length") == 0:
            rr._require(rec.get("contract_value") == rec.get("contract_remaining") == 0,
                        "Malformed nonempty contract cannot be initialized")
            for key, value in row["fields"].items():
                rec.set(key, value)
            initialized_contracts += 1
    # b780 b4-economy (D6): the injured players rejoin their clubs (see INJURED_STATUSES), chosen on the records as
    # this refresh leaves them (new players created, positions and modeled contracts written), so a replay on the
    # output makes the same choices.
    actives, rejoined, released, injured_free = _rejoin_injured(by, rows, teams, assigned)
    free_agents = list(plan["free_agents"]) + released + injured_free
    rr._require(len(free_agents) == len(set(free_agents)), "Refresh has duplicate or absent membership")
    rr._require(len(free_agents) <= doc.free_agent_capacity, "Free-agent list is full")
    owned = (owned - set(released)) | rejoined
    rr._require(all(by[i].record.get("contract_length") >= 1 for i in owned),
                "Owned unsigned player needs a native contract initializer")
    reseated, seated, slots = [], [], depth_slots(rows)
    for team, row in zip(doc.teams, teams):
        active = actives[row["index"]]
        team.slots = [by[i].offset for i in active]
        team.repaired = True
        doc.reserves[team.index] = tuple(row["reserves"])
        for index in active:
            # These five low bits are depth preferences, separate from stars
            # and abilities. Pin current chains and replace stale return locks.
            rec = by[index].record
            if index in rejoined:
                # b780 b4-economy (D6): an injured player who rejoins is unlocked at the overflow row, so the
                # weekly depth sort (and on a user's club the user) seats him by rating.
                rec.set("depth_rank", OVERFLOW_DEPTH_ROW)
                rec.set("depth_side", OVERFLOW_DEPTH_ROW)
                for role in LOCK_ROLES:
                    rec.set_depth_lock(role, False)
                continue
            for role in ("rank", "side"):
                rec.set_depth_lock(role, True)
            for role in ("kr1", "kr2", "pr"):
                rec.set_depth_lock(role, row["specialists"][role] == index)
        # b780 roster1: a player released for room above held a locked row; close his chart (see _reseat_chains)
        reseated.extend(_reseat_chains(by, row["active"], active, rejoined, slots))
        seated.extend(_seat_lone_rejoined(by, active, rejoined))
        for key, identity in row["specialists"].items():
            doc.body[team.offset + rr.SPECIAL_TEAM_OFFSETS[key]] = (
                255 if identity is None else active.index(identity))
    for index in released:
        # b780 b4-economy (D6): released to make room, so an unsigned free agent like the others on the list.
        rec = by[index].record
        for key in CONTRACT_FIELDS:
            rec.set(key, 0)
        for role in LOCK_ROLES:
            rec.set_depth_lock(role, False)
    # b780 rst2 (Q44, the held b778 fd1 fix): the pack's policy is "unsigned contracts zero" (retail free agents carry a
    # zero contract block). The 10/14 plan's one-year placeholders landed on 11 players who were free agents again by
    # 11/03 (Andy Dalton, Harrison Mevis, Chris Moore, Blake Grupe ...), and a player the dated plan moves to the free
    # agents kept his old contract block. Every free agent on the final list has all five contract fields zero.
    cleared = []
    for index in free_agents:
        rec = by[index].record
        if any(rec.get(key) for key in CONTRACT_FIELDS):
            cleared.append(index)
            for key in CONTRACT_FIELDS:
                rec.set(key, 0)
    doc.free_agents = [by[i].offset for i in free_agents]
    doc._reindex_membership()
    # Celebrity/alumni squads alias the same records and cannot have independent
    # rank locks. Validate the 32 edited clubs, leaving alias pointers intact.
    rr._require(not any(doc.depth_lock_conflicts(t.index) for t in doc.teams[:32]),
                "Refresh creates conflicting club depth locks")
    create_buffers_repaired = _repair_create_buffers(doc)
    result = doc.to_body()
    checked = rr.RosterDocument(result, scheme="one_pool", reference_year=2026)
    errors = [r for r in rr.validate_membership(checked) if r["level"] == "error"]
    rr._require(not errors, f"Refreshed membership failed validation: {errors}")
    ps.validate_roster(result, strict_owners=True)
    return result, {"as_of": plan["as_of"], "added": added, "teams": 32,
                    "create_buffers_repaired": create_buffers_repaired,
                    "initialized_contracts": initialized_contracts,
                    "appearance": created_appearance.receipt(appearance_created, appearance_written,
                                                             appearance_data),
                    "active": sum(len(a) for a in actives.values()),
                    "reserves": sum(len(t["reserves"]) for t in teams),
                    "changed_bytes": sum(a != b for a, b in zip(body, result)),
                    "unrepresented": len(plan.get("unrepresented", [])),
                    # b780 rst2 (Q44): free agents whose stale contract block was zeroed
                    "birth_dates_corrected": sorted(f"{by[i].display} {c['was']} -> {c['birth_date']}"
                                                     for i, c in corrections.items()),
                    "free_agent_contracts_cleared": len(cleared),
                    "free_agent_contracts_cleared_players": sorted(by[i].display for i in cleared),
                    # b780 b4-economy (D6)
                    "injured_reserve": {"rejoined": len(rejoined), "released_for_room": len(released),
                                        "to_free_agents": len(injured_free),
                                        "rejoined_players": sorted(by[i].display for i in rejoined),
                                        "released_players": [by[i].display for i in released],
                                        "free_agent_players": [by[i].display for i in injured_free],
                                        # b780 roster1: rows moved up to close the chains the releases opened,
                                        # and injured players seated as their club's only player at a position
                                        "reseated_rows": len(reseated),
                                        "lone_rejoined_seated": sorted(by[i].display for i in seated)}}
