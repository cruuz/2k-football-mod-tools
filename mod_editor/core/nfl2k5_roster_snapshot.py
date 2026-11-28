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
    """Reuse existing strings or repack only storage actually occupied by player names."""
    pool = roster.names
    fields = ("first", "last")
    requested = {}
    for row in entries:
        for field in fields:
            text = row[field]
            rr._require(type(text) is str and (not text or text in pool._by_text or rr.validate_name(text) == text),
                        "Save player names must fit without shortening or normalization.")
            if text:
                requested[text] = None
    # A snapshot of this disc (including a staff or face edit) leaves its string storage intact.
    locations = {text: pool._by_text[text][0] for text in requested if text in pool._by_text}
    repacked = len(locations) < len(requested)
    if repacked:
        locations = _repack_names(roster, requested)

    for player, entry in zip(roster.players, entries):
        for which in fields:
            key = which + "_name_pointer"
            text = entry[which]
            if text and getattr(player, which) == text and pool.offsets_for(text):
                old = roster._pointer_target(player.offset, key)
                if not repacked:
                    continue
                encoded = text.encode("utf-16-le") + b"\0\0"
                if roster.body[old:old + len(encoded)] == encoded:
                    continue
            field = player.offset + rr.FIELD_BY_NAME[key].offset
            player.record.values[key] = ((locations[text] - field + 1) & 0xFFFFFFFF) if text else 0
            setattr(player, which, text)


def _repack_names(roster, requested):
    from bisect import bisect_left
    from . import nfl2k5_save_rost as codec, nfl2k5_roster_arena as arena

    parsed = codec.decode(bytes(roster.body))
    owned_fields = {p.offset + rr.FIELD_BY_NAME[k].offset for p in roster.players
                    for k in ("first_name_pointer", "last_name_pointer")}
    other_targets = sorted(target for field in arena.pointer_fields(parsed) if field not in owned_fields
                           and (target := parsed.rel(field)) is not None)
    tables = [(t.offset, t.offset + t.count * t.stride) for t in parsed.tables.values() if t.count and t.offset is not None]
    available = []
    locations = {}
    # An overlapping/suffix reference shares the underlying string. Group these before
    # checking aliases. Intervening gaps can contain coach, college or franchise data.
    groups = []
    for start, block in sorted(roster.names.blocks.items()):
        end = start + block.capacity
        if groups and start < groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], end)
            groups[-1][2].append(block)
        else:
            groups.append([start, end, [block]])
    for start, end, blocks in groups:
        at = bisect_left(other_targets, start)
        if ((at < len(other_targets) and other_targets[at] < end)
                or any(left < end and start < right for left, right in tables)):
            for block in blocks:
                locations[block.text] = block.offset
        elif available and start == available[-1][1]:
            available[-1][1] = end
        else:
            available.append([start, end])

    additions = [(text, text.encode("utf-16-le") + b"\0\0") for text in requested if text not in locations]
    # Best-fit, longest first, so a short name cannot consume the only span that holds a long one.
    for text, raw in sorted(additions, key=lambda item: -len(item[1])):
        span = min((s for s in available if s[1] - s[0] >= len(raw)), key=lambda s: s[1] - s[0], default=None)
        rr._require(span is not None, "Player names do not fit in the destination's verified name allocations. "
                    "Use the Xbox save instead; no players were skipped.")
        start = span[0]
        roster.body[start:start + len(raw)] = raw
        locations[text] = start
        span[0] += len(raw)
    return locations


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
    log = []
    coach = rr.apply_coach_edits(roster.body, roster.teams, doc, log, obj_base=roster.obj_base)
    result = roster.to_body()
    # Parsing the complete serialized result checks reserve ownership as well.
    verified = rr.RosterDocument(result)
    _check_structure(verified, "Replacement roster")
    return result, {"edits": len(entries), "players_changed": len(entries) if result != body else 0,
                    "fields_written": len(entries) * len(CARRIED_FIELDS),
                    "players_moved": sum(p.teams != q.teams for p, q in
                                         zip(rr.RosterDocument(body).players, verified.players)),
                    "history_links_cleared": history_cleared, **coach, "log": log}
