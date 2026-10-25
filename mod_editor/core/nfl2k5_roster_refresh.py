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
    guards = plan["identity_guards"]
    rr._require(len({g[0] for g in guards}) == len(guards), "Duplicate identity guard")
    for index, first, last, birth in guards:
        p = by.get(index)
        rr._require(p is not None and (p.first, p.last, str(p.record.birth_date)) ==
                    (first, last, birth), f"Pack identity guard failed at {index}")
    rows = plan["players"]
    rr._require(len({r["index"] for r in rows}) == len(rows), "Duplicate refresh identity")
    rr._require(len({r["gsis_id"] for r in rows}) == len(rows), "Duplicate source identity")
    for row in rows:
        p = by.get(row["index"])
        rr._require(p is not None and p.group != "draft_class", "Refresh touches absent/draft record")
        same = (p.first, p.last, str(p.record.birth_date)) == (
            row["first"], row["last"], row["birth_date"])
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
    # All identity/capacity gates precede mutation of this private document.
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
    rr._require(all(by[i].record.get("contract_length") >= 1 for i in owned),
                "Owned unsigned player needs a native contract initializer")
    for team, row in zip(doc.teams, teams):
        team.slots = [by[i].offset for i in row["active"]]
        team.repaired = True
        doc.reserves[team.index] = tuple(row["reserves"])
        for index in row["active"]:
            # These five low bits are depth preferences, separate from stars
            # and abilities. Pin current chains and replace stale return locks.
            rec = by[index].record
            for role in ("rank", "side"):
                rec.set_depth_lock(role, True)
            for role in ("kr1", "kr2", "pr"):
                rec.set_depth_lock(role, row["specialists"][role] == index)
        for key, identity in row["specialists"].items():
            doc.body[team.offset + rr.SPECIAL_TEAM_OFFSETS[key]] = (
                255 if identity is None else row["active"].index(identity))
    doc.free_agents = [by[i].offset for i in plan["free_agents"]]
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
                    "active": sum(len(t["active"]) for t in teams),
                    "reserves": sum(len(t["reserves"]) for t in teams),
                    "changed_bytes": sum(a != b for a, b in zip(body, result)),
                    "unrepresented": len(plan.get("unrepresented", []))}
