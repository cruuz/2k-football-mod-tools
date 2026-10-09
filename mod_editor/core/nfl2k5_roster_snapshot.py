"""Typed roster replacement, without transplanting save pointers or franchise state."""
from __future__ import annotations

from . import nfl2k5_roster_records as rr

SCHEMA = "2k5_mod_studio_roster_edits/v2"


def document(save, *, name):
    from .nfl2k5_roster_save_to_disc import CARRIED_FIELDS
    return {
        "schema": SCHEMA, "name": name, "scheme": save.scheme,
        "edits": [{"pool": p.pool, "index": p.index,
                   "first": p.first, "last": p.last, "college": p.college,
                   "fields": {k: p.record.get(k) for k in CARRIED_FIELDS}}
                  for p in save.players],
        "teams": [{"index": t.index, "asset_id": t.asset_id, "kind": t.kind,
                   "players": [[save.by_offset[o].pool, save.by_offset[o].index] for o in t.slots],
                   "reserves": list(save.reserves[t.index]),
                   "specialists": {k: save.body[t.offset + off]
                                   for k, off in rr.SPECIAL_TEAM_OFFSETS.items()}}
                  for t in save.teams],
        "free_agents": [[save.by_offset[o].pool, save.by_offset[o].index] for o in save.free_agents],
    }


def _names(roster, entries):
    """Repack the existing player string allocations together, after alias checks."""
    from . import nfl2k5_save_rost as codec, nfl2k5_roster_arena as arena
    pool = roster.names
    cursor = pool.start
    for offset, block in sorted(pool.blocks.items()):
        rr._require(offset == cursor, "Player names are not one contiguous pool; use the Xbox save instead.")
        cursor += block.capacity
    parsed = codec.decode(bytes(roster.body))
    fields = {p.offset + rr.FIELD_BY_NAME[k].offset for p in roster.players
              for k in ("first_name_pointer", "last_name_pointer")}
    for field in arena.pointer_fields(parsed):
        target = parsed.rel(field)
        rr._require(field in fields or target is None or not pool.start <= target < pool.end,
                    "Another roster table shares player name storage; use the Xbox save instead.")
    for table in parsed.tables.values():
        if table.count and table.offset is not None:
            rr._require(table.offset + table.count * table.stride <= pool.start or table.offset >= pool.end,
                        "A roster table overlaps player names.")
    strings = {}
    packed = bytearray()
    for entry in entries:
        for which in ("first", "last"):
            text = entry[which]
            rr._require(type(text) is str and (not text or text in pool._by_text
                        or rr.validate_name(text) == text),
                        "Save player names must fit without shortening or normalization.")
            if text and text not in strings:
                strings[text] = pool.start + len(packed)
                packed.extend(text.encode("utf-16-le") + b"\0\0")
    rr._require(len(packed) <= pool.capacity_bytes,
                f"The save's player names need {len(packed)} bytes; the disc has {pool.capacity_bytes}. "
                "Use the Xbox save instead; no players were skipped.")
    roster.body[pool.start:pool.end] = packed + bytes(pool.capacity_bytes - len(packed))
    for player, entry in zip(roster.players, entries):
        for which, key in (("first", "first_name_pointer"), ("last", "last_name_pointer")):
            text = entry[which]
            field = player.offset + rr.FIELD_BY_NAME[key].offset
            player.record.values[key] = ((strings[text] - field + 1) & 0xFFFFFFFF) if text else 0
            setattr(player, which, text)


def apply_body(body, doc, *, scheme=None):
    from .nfl2k5_roster_save_to_disc import CARRIED_FIELDS, _check_structure
    roster = rr.RosterDocument(body)
    roster.set_scheme(scheme or str(rr.detect_scheme_from_data(roster)["scheme"]))
    entries = doc["edits"]
    keys = [(p.pool, p.index) for p in roster.players]
    rr._require([(e.get("pool"), e.get("index")) for e in entries] == keys,
                "Save and disc player tables differ. Use a disc with matching roster capacity.")
    rr._require(type(doc.get("teams")) is list and len(doc["teams"]) == len(roster.teams),
                "Save and disc team tables differ. Use a disc with matching teams.")
    source_scheme = rr.normalise_scheme(doc.get("scheme"))
    rr._require(source_scheme != "one_pool" or roster.scheme == "one_pool",
                "A pooled save cannot replace a retail disc roster.")
    _check_structure(roster, "Disc")
    index = dict(zip(keys, roster.players))

    def offsets(values):
        rr._require(type(values) is list and all(type(k) is list and len(k) == 2
                    and type(k[0]) is str and type(k[1]) is int and tuple(k) in index for k in values),
                    "Invalid player in save roster membership.")
        result = [index[tuple(k)].offset for k in values]
        rr._require(len(set(result)) == len(result), "Duplicate save roster membership.")
        return result

    history_cleared = 0
    for player, entry in zip(roster.players, entries):
        fields = entry.get("fields")
        rr._require(type(fields) is dict and set(fields) == set(CARRIED_FIELDS),
                    "A replacement roster must carry every supported player field.")
        canonical_pbp = fields["pbp_id"]
        if (entry["first"] or entry["last"]) and "*" not in entry["first"] + entry["last"]:
            canonical_pbp = rr.commentary_id(entry["last"], fields["jersey"], canonical_pbp)
        # A new player must not inherit the previous occupant's career history.
        # The final commentary pass may have canonicalized this same snapshot's
        # ID on its first import. Accept that exact repair on replay as well.
        if ((player.first, player.last) != (entry["first"], entry["last"])
                or player.record.get("pbp_id") not in (fields["pbp_id"], canonical_pbp)
                or any(player.record.get(k) != fields[k] for k in
                       ("birth_month", "birth_day", "birth_year_low", "birth_year_high"))):
            history_cleared += bool(player.record.get("history_pointer"))
            player.record.values["history_pointer"] = 0
        for key, value in fields.items():
            rr._require(type(value) is int, f"{key} must be an integer.")
            if key == "position" and rr.is_retired_position(value, roster.scheme):
                value = rr.replacement_position_code(value, roster.scheme)
            player.record.set(key, value)
        college = entry.get("college")
        rr._require(type(college) is str and (not college or college in roster.colleges),
                    f"College {college!r} is absent from the disc. Use the Xbox save instead.")
        if college:
            roster.set_college(player, roster.colleges.index(college))
        else:
            player.record.values["college_pointer"] = 0
    _names(roster, entries)
    for team, row in zip(roster.teams, doc["teams"]):
        rr._require((row.get("index"), row.get("asset_id"), row.get("kind")) ==
                    (team.index, team.asset_id, team.kind), "Save and disc team identities differ.")
        team.slots = offsets(row.get("players"))
        # Repack through the ordinary writer, including the active/reserve boundary.
        team.repaired = True
        reserves = row.get("reserves")
        rr._require(type(reserves) is list and all(type(i) is int and ("primary", i) in index for i in reserves)
                    and len(set(reserves)) == len(reserves), "Invalid save reserve list.")
        roster.reserves[team.index] = tuple(reserves)
        specialists = row.get("specialists")
        rr._require(type(specialists) is dict and set(specialists) == set(rr.SPECIAL_TEAM_OFFSETS),
                    "Invalid save specialist slots.")
        for key, value in specialists.items():
            rr._require(type(value) is int and 0 <= value <= 255, "Invalid save specialist slot.")
            roster.body[team.offset + rr.SPECIAL_TEAM_OFFSETS[key]] = value
    roster.free_agents = offsets(doc.get("free_agents"))
    roster._reindex_membership()
    _check_structure(roster, "Save roster")
    roster.check_depth_locks()
    result = roster.to_body()
    # Parsing the complete serialized result checks reserve ownership as well.
    verified = rr.RosterDocument(result)
    _check_structure(verified, "Replacement roster")
    return result, {"edits": len(entries), "players_changed": len(entries) if result != body else 0,
                    "fields_written": len(entries) * len(CARRIED_FIELDS),
                    "players_moved": sum(p.teams != q.teams for p, q in
                                         zip(rr.RosterDocument(body).players, verified.players)),
                    "history_links_cleared": history_cleared, "log": []}
