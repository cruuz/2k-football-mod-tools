"""Conservative migration of an existing 2026 SOFTDRINK franchise.

Identity pins distinguish imported players from records reused by the game's
draft generator. All changes are planned in memory and carry field receipts.
No input file is ever modified by this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib
from typing import Mapping

from . import nfl2k5_career_stats as cs
from . import nfl2k5_franchise_save as fs
from . import nfl2k5_save_rost as sr

SCHEMA = "nfl2k5_franchise_upgrade/v1"
BASE_YEAR = 2026
SLOT_MASK = 0x1F << 23


class UpgradeRefused(ValueError):
    """Input cannot be migrated safely without further evidence."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise UpgradeRefused(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


TEAM_EVIDENCE_SCHEMA = "nfl2k5_franchise_team_evidence/v1"


def season_stats_sha256(words, slot: int) -> str:
    """Pin regular-season counters independently of the stream's location/terminator.

    Slot bits are excluded so the experience migration does not invalidate a
    season's evidence. Duplicate counters remain part of the fingerprint.
    """
    counters = sorted(raw & 0x7FFFFF for raw in words
                      if not raw & 0x70000000 and cs.Word(raw).slot == slot
                      and cs.Word(raw).field != 87)
    return sha(b"".join(struct.pack("<I", raw) for raw in counters))


def upgrade_team_history(payload: bytes, disc_body: bytes, evidence: Mapping | None = None) -> tuple[bytes, dict]:
    """Restore missing TEAM entries without guessing from current membership.

    Pre-franchise seasons may use the current disc's identity-matched history.
    Seasons played inside this franchise require explicit, counter-pinned
    evidence. Existing teams and every stat word are preserved. Replacement
    entries use native-style insertion in the bounded pool; shared streams
    are cloned so other owners retain their exact history. Insufficient capacity refuses the entire operation.
    """
    save, roster = franchise(payload)
    disc = sr.decode(disc_body, preamble=0, reference_year=BASE_YEAR)
    by_identity = defaultdict(list)
    disc_identity = defaultdict(list)
    for player in roster.players:
        if player.pool == "primary":
            by_identity[identity(player)].append(player)
    for player in disc.players:
        if player.pool == "primary":
            disc_identity[identity(player)].append(player)
    clubs = {team.abbreviation: team.index for team in roster.teams[:32]}
    require(len(clubs) == 32 and all(clubs), "requires unique NFL club abbreviations")
    # These events can identify a club at an event, but cannot prove the
    # absence of intervening moves. The native writer wraps at 600 entries,
    # clears kinds independently, and stores event arguments rather than a
    # season/date. A draft or signing plus today's membership is insufficient.
    native_events = save.ledger_in_write_order()
    events_by_player = defaultdict(list)
    for event in native_events:
        events_by_player[event["player_index"]].append(event["index"])
    native_evidence = {
        "ledger_write_cursor": save.u32(save.front_office_block + fs.F_LEDGER_CURSOR),
        "ledger_boundary_cursors": list(struct.unpack_from(
            "<II", payload, save.front_office_block + fs.F_LEDGER_BOUNDARIES)),
        "ledger_capacity": fs.F_LEDGER_CAPACITY,
        "retained_events": len(native_events),
        "retained_event_kinds": dict(sorted(Counter(e["kind"] for e in native_events).items())),
        "retained_slots_full": len(native_events) == fs.F_LEDGER_CAPACITY,
        "ordered_events": native_events,
        "event_dates_available": False,
        "news_log_entries": len(save.transactions()),
        "full_season_coverage_proved": False,
        "limitation": "Native event slots can wrap or be cleared and carry no season coverage marker. "
                      "Current membership, contracts, draft events and partial highlights do not prove a whole season.",
    }

    def entries(words, field, slot):
        return [raw for raw in words if not raw & 0x70000000
                and cs.Word(raw).field == field and cs.Word(raw).slot == slot]

    explicit = {}
    if evidence is not None:
        require(isinstance(evidence, Mapping), "TEAM evidence must be an object")
        require(evidence.get("schema") == TEAM_EVIDENCE_SCHEMA, "unknown TEAM evidence schema")
        sources = evidence.get("sources", {})
        rows = evidence.get("rows")
        require(isinstance(sources, Mapping) and isinstance(rows, list), "TEAM evidence needs sources and rows")
        for row in rows:
            require(isinstance(row, Mapping) and all(isinstance(row.get(key), str) for key in
                    ("first", "last", "birth_date", "team", "source", "stats_sha256")),
                    "TEAM evidence row has missing or invalid identity/source fields")
            require(bool(row["birth_date"]), "TEAM evidence needs a birth date")
            key = row["first"], row["last"], row["birth_date"]
            matches = by_identity[key]
            require(len(matches) == 1, "TEAM evidence identity missing or ambiguous")
            player = matches[0]
            year = row.get("season")
            require(type(year) is int and BASE_YEAR <= year < roster.reference_year,
                    "TEAM evidence must describe a completed franchise season")
            slot = player.record.values["years_pro"] - (roster.reference_year - year)
            require(1 <= slot <= 31, "TEAM evidence season outside player career")
            words = roster.history_words[player.key]
            games = entries(words, 0, slot)
            require(len(games) == 1 and games[0] & 65535, "TEAM evidence needs a positive games row")
            require(row.get("stats_sha256") == season_stats_sha256(words, slot),
                    "TEAM evidence counters changed")
            require(row["team"] in clubs, "TEAM evidence club is not in this franchise")
            source = sources.get(row.get("source"), {})
            require(isinstance(source, Mapping)
                    and isinstance(source.get("description"), str) and bool(source["description"].strip())
                    and isinstance(source.get("sha256"), str)
                    and re.fullmatch("[0-9a-f]{64}", source["sha256"]) is not None,
                    "TEAM evidence needs a described, hashed source")
            target = player.key, slot
            require(target not in explicit, "duplicate TEAM evidence season")
            existing = entries(words, 87, slot)
            value = clubs[row["team"]] + 1
            require(not existing or (len(existing) == 1 and existing[0] & 65535 == value),
                    "TEAM evidence conflicts with recorded history")
            explicit[target] = value, {"kind": "supplied_evidence", "source": row["source"],
                                       "description": source["description"], "sha256": source["sha256"]}

    # Opening membership is useful as a labelled candidate for a missing
    # 2026 row, never as a played-season fact. Retained native events are
    # undated and cannot assign a trade/signing to a season or a week.
    opening_clubs = defaultdict(set)
    disc_by_offset = {p.offset: p for p in disc.players}
    for team in disc.teams[:32]:
        for offset in team.player_offsets:
            source_player = disc_by_offset.get(offset)
            if source_player is not None:
                opening_clubs[identity(source_player)].add(team.abbreviation)
    additions = defaultdict(list)
    changes, unresolved = [], []
    for player in roster.players:
        words = roster.history_words[player.key]
        slots = sorted({cs.Word(raw).slot for raw in words if not raw & 0x70000000
                        and cs.Word(raw).field == 0 and raw & 65535})
        for slot in slots:
            if entries(words, 87, slot):
                continue
            year = roster.reference_year - player.record.values["years_pro"] + slot
            # Current rows use runtime membership. Never bake today's club into
            # an unknown old season or manufacture a folded "pre" season.
            if year >= roster.reference_year or slot < 1:
                continue
            found = explicit.get((player.key, slot))
            if found is None and year < BASE_YEAR and player.pool == "primary":
                key = identity(player)
                candidates = disc_identity[key]
                if key[2] and len(by_identity[key]) == 1 and len(candidates) == 1:
                    source_player = candidates[0]
                    source_slot = source_player.record.values["years_pro"] - (BASE_YEAR - year)
                    source_words = disc.history_words[source_player.key]
                    teams = entries(source_words, 87, source_slot)
                    games = entries(source_words, 0, source_slot)
                    if (1 <= source_slot <= 31 and len(teams) == 1 and len(games) == 1 and games[0] & 65535
                            and season_stats_sha256(source_words, source_slot) == season_stats_sha256(words, slot)):
                        index = (teams[0] & 65535) - 1
                        if 0 <= index < min(32, len(disc.teams)) and disc.teams[index].abbreviation in clubs:
                            found = (clubs[disc.teams[index].abbreviation] + 1,
                                     {"kind": "disc_history", "disc_body_sha256": sha(disc_body),
                                      "source_player_index": source_player.index, "source_slot": source_slot})
            common = {"pool": player.pool, "index": player.index, "player": f"{player.first} {player.last}",
                      "birth_date": identity(player)[2], "season": year, "slot": slot}
            if found is None:
                event_slots = events_by_player[player.index] if player.pool == "primary" else []
                reason = ("pre_franchise_source_missing_or_mismatched" if year < BASE_YEAR else
                          "retained_events_without_season_coverage" if event_slots else
                          "no_retained_player_event_or_season_coverage")
                row = {**common, "reason": reason, "native_event_slots": event_slots}
                if year >= BASE_YEAR:
                    row["inferred"] = True
                    row["week_by_week_coverage"] = False
                    row["undated_event_clubs"] = sorted({e["team_name"] for e in native_events
                        if player.pool == "primary" and e["player_index"] == player.index and e["team_name"]})
                    key = identity(player)
                    if (year == BASE_YEAR and key[2] and len(by_identity[key]) == 1
                            and len(disc_identity[key]) == 1):
                        row["inferred_opening_clubs"] = sorted(opening_clubs[key])
                    row["note"] = "Candidates are not a dated season history; no TEAM word was written."
                unresolved.append(row)
                continue
            value, basis = found
            additions[player.key].append((slot << 23) | (87 << 16) | value)
            changes.append({**common, "field": "team_history", "before": None,
                            "after": roster.teams[value - 1].abbreviation, "basis": basis})

    out = bytearray(payload)
    masks = {}
    spans = []
    used = roster.pool_used
    pool = roster.pool
    require(pool is not None, "missing history pool")
    # Native FUN_0014e8b0 inserts a word into the used pool with memmove,
    # adjusts later player pointers, and increments +0x40. Unused native slots
    # can contain stale words after compaction; zero bytes are not required.
    # Only accept the known native arena pool, not an arbitrary relocated span.
    require(not additions or pool == roster.layout.root + 0x41A34,
            "unsupported history pool location")
    intervals = {key: (start, start + 4 * len(roster.history_words[key]))
                 for key, start in roster.history_offsets.items() if start is not None}
    insertions, clones = {}, {}
    for key, new in additions.items():
        start, stop = intervals[key]
        shared = any(other != key and left < stop and right > start
                     for other, (left, right) in intervals.items())
        if shared:
            clones[key] = tuple(new) + roster.history_words[key]
        else:
            insertions[start] = (key, tuple(new))
    needed = sum(len(new) for _, new in insertions.values()) + sum(map(len, clones.values()))
    require(used + needed <= roster.pool_capacity, "insufficient history capacity for TEAM repair")
    end = pool + (used + needed) * 4
    require(end <= roster.layout.end, "TEAM repair exceeds roster arena")
    for table in roster.tables.values():
        if table.offset is not None and table.count and needed:
            require(end <= table.offset or pool >= table.offset + table.count * table.stride,
                    "TEAM repair would overlap a roster table")
    block = bytearray()
    cursor = pool
    targets = {}
    for start, (key, new) in sorted(insertions.items()):
        block.extend(payload[cursor:start])
        targets[key] = pool + len(block)
        block.extend(b"".join(struct.pack("<I", word) for word in new))
        cursor = start
    block.extend(payload[cursor:pool + used * 4])
    for key, words in sorted(clones.items()):
        targets[key] = pool + len(block)
        block.extend(b"".join(struct.pack("<I", word) for word in words))
    require(len(block) == (used + needed) * 4, "TEAM pool size mismatch")
    if needed:
        out[pool:end] = block
        spans.append({"field": "history_pool", "offset": pool, "size": end - pool})
        masks.update({offset: 255 for offset in range(pool, end)})
        for key, (start, _stop) in intervals.items():
            target = targets.get(key, start + sum(len(new) * 4 for at, (_, new) in insertions.items() if at <= start))
            if target != start:
                pointer = roster.by_key[key].offset + 0x2C
                struct.pack_into("<i", out, pointer, target - pointer + 1)
                masks.update({pointer + i: 255 for i in range(4)})
                spans.append({"field": "history_pointer", "pool": key[0], "index": key[1],
                              "offset": pointer, "size": 4})
        pointer = roster.layout.root + 0x40
        struct.pack_into("<I", out, pointer, used + needed)
        masks.update({pointer + i: 255 for i in range(4)})
        spans.append({"field": "history_used_count", "offset": pointer, "size": 4})
    result = bytes(out)
    proof = prove_scope(payload, result, masks)
    checked = sr.decode(result, base_year=BASE_YEAR)
    for player in roster.players:
        require(identity(checked.by_key[player.key]) == identity(player), "TEAM repair changed a player identity")
        require(checked.history_words[player.key] == tuple(additions.get(player.key, ()))
                + roster.history_words[player.key], "TEAM history read-back differs")
    require([t.abbreviation for t in checked.teams] == [t.abbreviation for t in roster.teams],
            "TEAM repair changed a club label")
    return result, {"operation": "team_history", "changes": changes, "unresolved": unresolved,
                    "unresolved_by_reason": dict(sorted(Counter(r["reason"] for r in unresolved).items())),
                    "native_evidence": native_evidence,
                    "unresolved_rows": len(unresolved), "used_before": used, "used_after": used + needed,
                    "capacity": roster.pool_capacity, "source_savegame_sha256": sha(payload),
                    "output_savegame_sha256": sha(result), "existing_history_words_preserved": True,
                    "storage_spans": spans,
                    **proof}


def identity(player: sr.Player) -> tuple[str, str, str]:
    return player.first, player.last, str(player.record.birth_date or "")


def franchise(payload: bytes) -> tuple[fs.FranchiseSave, sr.SaveRost]:
    try:
        save = fs.FranchiseSave(payload, base_year=BASE_YEAR)
        roster = sr.decode(payload, base_year=BASE_YEAR)
    except ValueError as exc:
        raise UpgradeRefused(str(exc)) from exc
    require(save.header.mode == 2 and save.header.substate != 3,
            "requires a populated native franchise, not a roster/settings/empty save")
    require(save.header.team_count == 32, "requires the 32-team NFL franchise")
    require(0 <= save.header.year_field <= 29, "unsupported franchise season index")
    return save, roster


def prove_scope(before: bytes, after: bytes, masks: Mapping[int, int]) -> dict:
    require(len(before) == len(after), "save size changed")
    changed = 0
    for offset, (a, b) in enumerate(zip(before, after)):
        if a != b:
            require((a ^ b) & ~masks.get(offset, 0) == 0,
                    f"write escaped declared field bits at {offset:#x}")
            changed += 1
    return {"outside_declared_fields_identical": True, "changed_bytes": changed}


def validate_save(payload: bytes) -> dict:
    """Apply Studio's structural, ownership and depth checks without rewriting.

    Cosmetic/rating warnings remain visible. Retired position codes on inactive
    secondary templates are preserved; active NFL and reserve players must use
    the current one-pool positions. Unknown depth values are never normalized.
    """
    from . import nfl2k5_practice_squad as ps
    from . import nfl2k5_roster_records as rr
    save, roster = franchise(payload)
    document = rr.RosterDocument(payload, base=roster.layout.preamble,
                                 scheme="one_pool", base_year=BASE_YEAR)
    findings = rr.validate(document)
    errors = [row for row in findings if row["level"] == "error"]
    require(not errors, f"Studio structural validation failed: {errors[:3]}")
    document.check_depth_locks()
    reserves = ps.validate_save(payload)
    positions = Counter()
    for player in document.players:
        position = player.record.values["position"]
        require(0 <= position <= 16, f"{player.display}: position outside native range")
        positions[position] += 1
        active = any(team < 32 for team in player.teams)
        reserved = (player.pool, player.index) in document.reserve_owner
        if active or reserved:
            require(not rr.is_retired_position(position, document.scheme),
                    f"{player.display}: active/reserve player uses retired LB code")
    coaches = roster.tables["coaches"]
    labels = roster.tables["team_labels"]
    special_roles = []
    for team in roster.teams:
        for relative, table, field in ((0x14C, coaches, "coach"), (0x110, labels, "playbook")):
            pointer = roster.rel(team.offset + relative, size=table.stride, label=field)
            if pointer is None:
                require(team.index >= 32, f"{team.abbreviation}: null {field} reference")
                continue
            require(table.offset is not None and pointer >= table.offset
                    and (pointer - table.offset) % table.stride == 0
                    and (pointer - table.offset) // table.stride < table.count,
                    f"{team.abbreviation}: {field} reference is not a table record")
        if team.index < 32:
            roles = {name: payload[team.offset + offset]
                     for name, offset in rr.SPECIAL_TEAM_OFFSETS.items()}
            require(all(slot == 255 or slot < len(team.player_offsets) for slot in roles.values()),
                    f"{team.abbreviation}: special-teams role outside active roster")
            special_roles.append({"team": team.abbreviation, "active": len(team.player_offsets),
                                  "roles": roles})
    games = save.games()
    for game in games:
        require(0 <= game.home < fs.LEAGUE_SLOTS and 0 <= game.away < fs.LEAGUE_SLOTS,
                f"schedule ({game.row}, {game.slot}): team outside native range")
    ir = save.injured_reserve()
    require(all(0 <= entry.player_index < roster.tables["primary"].count for entry in ir),
            "injured reserve player outside primary table")
    require(document.to_body() == payload, "read-only Studio round trip changed the save")
    return {"operation": "validation", "savegame_sha256": sha(payload),
            "players": len(roster.players), "teams": len(roster.teams),
            "schedule_games": len(games), "injured_reserve_entries": len(ir),
            "position_counts": dict(sorted(positions.items())),
            "reserve_counts": {str(team): len(rows) for team, rows in reserves.items()},
            "special_roles": special_roles,
            "checks": {name: "pass" for name in (
                "arena tables and relative pointers", "player history bounds and termination",
                "team and free agent membership", "practice squad and IR ownership",
                "position range and active LB/EDGE pools", "depth lock consistency",
                "holder, returner, kicker and snapper slot bounds",
                "team coach and book record references", "schedule team references",
                "byte-identical Studio round trip")},
            "findings": findings, "changes": []}


def upgrade_years(payload: bytes, cohort: Mapping) -> tuple[bytes, dict]:
    """Repair surviving f12 identities and all their existing history slot bits.

    The cohort records the old 2026 count, before the native annual rollover.
    Require a uniform old or corrected cohort; mixed/customized experience is
    deliberately refused. A generated record at a recycled index never matches
    on index alone. Existing current-season, deleted, postseason and folded
    words keep every non-slot bit, including their terminators.
    """
    save, roster = franchise(payload)
    require(cohort.get("schema") == "nfl2k5_b77_f12_cohort/v1", "unknown experience cohort")
    require(cohort.get("columns") ==
            ["index", "first", "last", "birth_date", "old_years_pro", "basis"],
            "unknown cohort columns")
    pins = {}
    for index, first, last, birth, old, basis in cohort["records"]:
        key = first, last, birth
        require(key not in pins and type(old) is int and 0 <= old <= 30,
                "duplicate/invalid imported identity pin")
        require(basis in cohort["basis_codes"], "unknown identity source basis")
        pins[key] = (index, old, basis)
    require(len(pins) == cohort["counts"]["records"], "incomplete cohort")
    found = defaultdict(list)
    for player in roster.players:
        if player.pool == "primary" and identity(player) in pins:
            found[identity(player)].append(player)
    require(bool(found), "no pinned modern imported players: unsupported franchise")
    require(all(len(players) == 1 for players in found.values()),
            "duplicate imported identity in save")
    matches = []
    states = set()
    for key, players in found.items():
        player = players[0]
        _index, old_start, basis = pins[key]
        old = old_start + save.header.year_field
        new = old + 1
        require(new <= 31, f"{player.first} {player.last}: experience exceeds supported range")
        actual = player.record.values["years_pro"]
        require(actual in (old, new),
                f"{player.first} {player.last}: years pro {actual}, expected {old} or {new}; "
                "customized/unsupported experience is not overwritten")
        states.add("old" if actual == old else "current")
        matches.append((player, old, new, basis))
    require(len(states) == 1, "mixed old/current experience: review before migrating")
    state = next(iter(states))
    match_keys = {p.key for p, *_ in matches}
    streams = sorted((start, start + len(roster.history_words[key]) * 4, key)
                     for key, start in roster.history_offsets.items() if start is not None)
    # The native game may retain shared tails after saving. No ownership proof
    # is needed for a current cohort because no history bytes will be written.
    # Keep the strict boundary for any migration that actually shifts slots.
    if state == "old":
        for left, right in zip(streams, streams[1:]):
            require(left[1] <= right[0], "shared/overlapping history ownership is unsupported")
    out = bytearray(payload)
    masks: dict[int, int] = {}
    changes = []
    word_count = honor_count = 0
    for player, old, new, basis in sorted(matches, key=lambda row: row[0].index):
        common = {"pool": player.pool, "index": player.index,
                  "player": f"{player.first} {player.last}", "birth_date": identity(player)[2]}
        words = roster.history_words[player.key]
        for word in words:
            slot = cs.Word(word).slot
            require(slot < 31 if state == "old" else slot >= 1,
                    f"{common['player']}: history slot inconsistent with experience state")
        if state == "current":
            continue
        at = player.offset + 0x25
        out[at] = (out[at] & 0xE0) | new
        masks[at] = 0x1F
        changes.append({**common, "field": "years_pro", "offset": at,
                        "mask": "0x1f", "before": old, "after": new, "basis": basis})
        start = roster.history_offsets[player.key]
        for ordinal, word in enumerate(words):
            decoded = cs.Word(word)
            after_word = word + (1 << 23)
            at = start + 4 * ordinal
            struct.pack_into("<I", out, at, after_word)
            masks[at + 2] = 0x80
            masks[at + 3] = 0x0F
            honor_count += 96 <= decoded.field <= 105
            word_count += 1
            changes.append({**common, "field": f"history[{ordinal}].slot", "offset": at,
                            "mask": "0x0f800000", "before": decoded.slot,
                            "after": decoded.slot + 1, "history_field": decoded.field,
                            "before_word": f"0x{word:08x}", "after_word": f"0x{after_word:08x}"})
    if state == "old":
        # fx1 (review r2-franchise MAJOR 1): "old" is read from years_pro against the cohort plus the header year,
        # and the Franchise page can edit that year. An old-convention save always carries slot-0 history words
        # (last season); an upgraded or new-build save has none. Without them the experience already moved, so
        # refuse (nothing is written: `out` is a private copy) rather than bump it a second time.
        require(any(cs.Word(word).slot == 0 for player, *_ in matches for word in roster.history_words[player.key]),
                "experience looks one year behind but no player has an old-convention (slot 0) history season: "
                "the franchise year was probably edited after an upgrade; nothing was changed")
    result = bytes(out)
    scope = prove_scope(payload, result, masks)
    checked = sr.decode(result, base_year=BASE_YEAR)
    for player in roster.players:
        after_player = checked.by_key[player.key]
        expected = dict(player.record.values)
        if state == "old" and player.key in match_keys:
            expected["years_pro"] += 1
            expected_words = tuple(w + (1 << 23) for w in roster.history_words[player.key])
        else:
            expected_words = roster.history_words[player.key]
        require(after_player.record.values == expected, "unexpected player-field write")
        require(checked.history_words[player.key] == expected_words, "history read-back differs")
    return result, {"schema": SCHEMA, "operation": "years", "state": state,
                    "season": save.header.display_year, "matched_players": len(matches),
                    "excluded_records": len(roster.players) - len(matches),
                    "changed_players": len(matches) if state == "old" else 0,
                    "shifted_history_words": word_count, "shifted_honors_words": honor_count,
                    "before_sha256": sha(payload), "after_sha256": sha(result),
                    **scope, "changes": changes}


def sync_playbooks(payload: bytes, disc_body: bytes,
                   resources: Mapping[int, bytes]) -> tuple[bytes, dict]:
    """Set each NFL team's combined book reference and defensive scheme.

    A native franchise stores team+110 -> an eight-byte label row; row+4 is
    the engine key for ``%s-pb.iff``. The combined resource supplies offense,
    defense and personnel packages. Per-game split-book choices are transient
    native/patch state, not fields in this franchise container. Keep the label
    row ordinal aligned with the disc as coach_ai also checks that ordinal.
    """
    from . import nfl2k5_playbook_inspector as inspector
    _save, roster = franchise(payload)
    target = sr.decode(disc_body, preamble=0, reference_year=BASE_YEAR)
    require(target.layout.version in (17, 18), "current source must be a disc ROST")
    require(len(roster.teams) >= 32 and len(target.teams) >= 32, "missing NFL teams")
    by_asset = {team.asset_id: team for team in target.teams[:32]}
    require(len(by_asset) == 32 and set(by_asset) == {t.asset_id for t in roster.teams[:32]},
            "save and current disc do not contain the same 32 NFL identities")
    saved_labels = roster.tables["team_labels"]
    source_labels = target.tables["team_labels"]
    out = bytearray(payload)
    masks: dict[int, int] = {}
    changes, teams = [], []
    for team in roster.teams[:32]:
        current = by_asset[team.asset_id]
        require(roster.u32(team.offset + 0x128) == target.u32(current.offset + 0x128) == 0,
                "custom/historic team in NFL franchise is unsupported")
        source_label = target.rel(current.offset + 0x110, size=8, label="disc playbook")
        require(source_label is not None and source_labels.offset is not None,
                "null current playbook reference")
        ordinal, remainder = divmod(source_label - source_labels.offset, 8)
        require(remainder == 0 and 0 <= ordinal < source_labels.count,
                "disc book reference is not a label record")
        require(saved_labels.offset is not None and ordinal < saved_labels.count,
                "save is missing the current playbook label")
        saved_label = saved_labels.offset + ordinal * 8
        key = target.string(source_label + 4)
        require(key and roster.string(saved_label + 4) == key,
                f"{team.abbreviation}: unknown/custom label table; cannot rewrite strings safely")
        filename = f"{key}-pb.iff"
        name_id = zlib.crc32(filename.upper().encode("utf-16-le")) & 0xFFFFFFFF
        require(name_id in resources, f"{team.abbreviation}: current disc is missing {filename}")
        raw = resources[name_id]
        book = inspector.parse_playbook_resource(raw, asset_id=filename)
        require(book.book_name == key, f"{filename}: compiled book identity differs")
        old_label = roster.rel(team.offset + 0x110, size=8, label="save playbook")
        old_key = roster.string(old_label + 4) if old_label is not None else None
        field = team.offset + 0x110
        pointer = saved_label - field + 1
        if old_label != saved_label:
            struct.pack_into("<i", out, field, pointer)
            masks.update({field + i: 0xFF for i in range(4)})
            changes.append({"team": team.abbreviation, "field": "combined_playbook_label",
                            "offset": field, "before": old_key, "after": key,
                            "before_word": roster.u32(field), "after_word": pointer & 0xFFFFFFFF})
        old_scheme = roster.u32(team.offset + 0x150)
        scheme = target.u32(current.offset + 0x150)
        require(scheme in (0, 1, 2), "current disc has an invalid defensive scheme")
        if old_scheme != scheme:
            field = team.offset + 0x150
            struct.pack_into("<I", out, field, scheme)
            masks.update({field + i: 0xFF for i in range(4)})
            changes.append({"team": team.abbreviation, "field": "defensive_scheme",
                            "offset": field, "before": old_scheme, "after": scheme})
        teams.append({"team": team.abbreviation, "asset_id": team.asset_id,
                      "book_label_index": ordinal, "offense": key, "defense": key,
                      "resource": filename, "resource_name_id": name_id,
                      "resource_sha256": sha(raw), "formations": len(book.formations),
                      "plays": len(book.plays), "scheme": scheme})
    result = bytes(out)
    scope = prove_scope(payload, result, masks)
    sr.decode(result, base_year=BASE_YEAR)
    return result, {"operation": "playbooks", "before_sha256": sha(payload),
                    "after_sha256": sha(result), "disc_roster_sha256": sha(disc_body),
                    "teams": teams, "changes": changes, **scope,
                    "storage": "combined book label and scheme; PLAY/packages come from disc",
                    "split_book_choices": "per game only; no persistent franchise field"}


def sync_coaches(payload: bytes, disc_body: bytes) -> tuple[bytes, dict]:
    """Copy exactly coach+18 u32 body and coach+40 u16 portrait by full name.

    Team assignment and coach-table order are deliberately not identity keys:
    an ongoing franchise may move coaches or add its own. Unmatched coaches
    are retained and reported; duplicate named identities fail closed.
    """
    _save, roster = franchise(payload)
    target = sr.decode(disc_body, preamble=0, reference_year=BASE_YEAR)
    require(target.layout.version in (17, 18), "coach source must be a disc ROST")

    def coaches(document):
        table = document.tables["coaches"]
        rows = {}
        unnamed = []
        for index in range(table.count):
            at = table.offset + index * table.stride
            key = document.string(at), document.string(at + 4)
            if not all(key) or key in (("xxxxxxxxxx", "xxxxxxxxxx"),
                                      ("************************", "************************")):
                unnamed.append(index)
                continue
            require(key not in rows, f"duplicate coach identity {' '.join(key)}")
            rows[key] = (index, at)
        return rows, unnamed

    saved, unnamed = coaches(roster)
    current, _ = coaches(target)
    out = bytearray(payload)
    masks: dict[int, int] = {}
    changes, matched, unmatched = [], [], []
    for key, (index, at) in saved.items():
        if key not in current:
            unmatched.append({"index": index, "coach": " ".join(key)})
            continue
        source_index, source_at = current[key]
        matched.append({"index": index, "source_index": source_index, "coach": " ".join(key)})
        for field, relative, fmt in (("body_id", 0x18, "<I"), ("portrait_id", 0x40, "<H")):
            before = struct.unpack_from(fmt, payload, at + relative)[0]
            after = struct.unpack_from(fmt, disc_body, source_at + relative)[0]
            if before == after:
                continue
            struct.pack_into(fmt, out, at + relative, after)
            masks.update({at + relative + i: 0xFF for i in range(struct.calcsize(fmt))})
            changes.append({"coach": " ".join(key), "index": index, "source_index": source_index,
                            "field": field, "offset": at + relative, "before": before, "after": after})
    require(bool(matched), "no matching coach identities")
    result = bytes(out)
    scope = prove_scope(payload, result, masks)
    sr.decode(result, base_year=BASE_YEAR)
    return result, {"operation": "coach_sync", "before_sha256": sha(payload),
                    "after_sha256": sha(result), "disc_roster_sha256": sha(disc_body),
                    "matched": matched, "unmatched_preserved": unmatched,
                    "unnamed_preserved": unnamed, "changes": changes, **scope}


#: b778-hr3: the hair style is the low nibble of player record +0x0D (nfl2k5_hair_styles; Studio field hair_style)
HAIR_STYLE_OFFSET, HAIR_STYLE_MASK = 0x0D, 0x0F


def sync_hair_styles(payload: bytes, disc_body: bytes) -> tuple[bytes, dict]:
    """Copy the disc roster's hair style (record +0x0D bits 0-3) into the franchise's own players by identity.

    b778-hr3: a franchise keeps its whole roster in the save, so a franchise started before a disc had hair styles
    (every record +0x0D zero) shows stock hair on every later disc. Only players whose (first, last, birth date) is
    unique in both rosters are touched, only when the save still has style 0 and the disc has one; a style the user
    set in the franchise is kept. Bits 4-7 and every other byte stay as they are.
    """
    _save, roster = franchise(payload)
    target = sr.decode(disc_body, preamble=0, reference_year=BASE_YEAR)
    require(target.layout.version in (17, 18), "hair style source must be a disc ROST")

    def by_identity(document):
        rows: dict[tuple[str, str, str], list[sr.Player]] = defaultdict(list)
        for player in document.players:
            if player.first or player.last:
                rows[identity(player)].append(player)
        return rows

    saved, current = by_identity(roster), by_identity(target)
    out = bytearray(payload)
    masks: dict[int, int] = {}
    changes, kept, ambiguous = [], [], []
    for key, sources in current.items():
        styles = {disc_body[p.offset + HAIR_STYLE_OFFSET] & HAIR_STYLE_MASK for p in sources}
        if styles == {0} or key not in saved:
            continue
        players = saved[key]
        if len(sources) != 1 or len(players) != 1:
            ambiguous.append(" ".join(key[:2]))
            continue
        style = styles.pop()
        player = players[0]
        at = player.offset + HAIR_STYLE_OFFSET
        before = payload[at] & HAIR_STYLE_MASK
        if before == style:
            continue
        if before:
            kept.append({"player": f"{player.first} {player.last}", "kept": before, "disc": style})
            continue
        out[at] = (payload[at] & ~HAIR_STYLE_MASK & 0xFF) | style
        masks[at] = HAIR_STYLE_MASK
        changes.append({"player": f"{player.first} {player.last}", "pool": player.pool, "index": player.index,
                        "field": "hair_style", "offset": at, "before": before, "after": style})
    result = bytes(out)
    scope = prove_scope(payload, result, masks)
    sr.decode(result, base_year=BASE_YEAR)
    return result, {"operation": "hair_styles", "before_sha256": sha(payload), "after_sha256": sha(result),
                    "disc_roster_sha256": sha(disc_body), "disc_players_with_style": sum(
                        1 for p in target.players if disc_body[p.offset + HAIR_STYLE_OFFSET] & HAIR_STYLE_MASK),
                    "kept_user_styles": kept, "ambiguous_identities_skipped": sorted(set(ambiguous)),
                    "changes": changes, **scope}


# --- b778-pc2: award history for a franchise created before the honors page -------------------------------------
#: fields the retail history fold (FUN_0014EFE0, rule table 0xAA26C0) merges by MAX; every other field sums. Past
#: field 86 the retail lookup reads unrelated variables: TEAM (87) is a nonzero read (sums, and the folded row shows
#: "--" anyway) and the honors owner pins fields 96..105 to sum.
FOLD_MAX_FIELDS = frozenset((16, 17, 30, 36, 43, 44, 45, 46, 56, 73))
HONOR_FIELD_FIRST, HONOR_FIELD_LAST = 96, 105
DEAD_WORD = 0x30000000                     # deleted (bit 28) or postseason (bit 29): never live regular-season data
FOLD_BIT, END_BIT = 0x40000000, 0x80000000
TEAM_FIELD = 87
HISTORY_RESERVE = 64                       # dwords kept free after the sync (the game folds again by itself when full)
SYNC_FOLD_DEPTHS = range(15, 1, -1)        # the card shows 15 season rows, so fold the oldest seasons first


def _signed16(raw: int) -> int:
    return (raw & 0xFFFF) - (0x10000 if raw & 0x8000 else 0)


def _with_end(words) -> list[int]:
    words = [w & ~END_BIT & 0xFFFFFFFF for w in words]
    if words:
        words[-1] |= END_BIT
    return words


def fold_words(words, years_pro: int, depth: int) -> tuple[int, ...]:
    """The game's own history fold for one stream: every live regular-season word at least ``depth`` seasons old is
    merged into the season ``depth - 1`` old (sum, or max for FOLD_MAX_FIELDS, 16-bit signed as the game stores it)
    and the receiving word is flagged folded (bit 30). Deleted and postseason words, and words newer than ``depth``,
    stay as they are; the end bit stays on the last word. A stream whose merged sum would overflow a signed 16-bit
    cell is returned unfolded (the game would wrap it into a negative career total). Differentially tested against the retail code under
    Unicorn (tests/mod_editor/test_nfl2k5_franchise_honors.py)."""
    require(depth >= 2, "fold depth must be at least 2")
    words_in = list(words)
    target_slot = years_pro - depth + 1
    keep, merged = [], {}
    for raw in words:
        raw &= ~END_BIT & 0xFFFFFFFF
        word = cs.Word(raw)
        if not raw & DEAD_WORD and years_pro - word.slot >= depth and target_slot >= 0:
            merged.setdefault(word.field, []).append(raw)
        else:
            keep.append(raw)
    for field, olds in sorted(merged.items()):
        index = next((i for i, raw in enumerate(keep)
                      if not raw & DEAD_WORD and (raw >> 16) & 127 == field and (raw >> 23) & 31 == target_slot), None)
        current = _signed16(keep[index]) if index is not None else None
        values = [_signed16(raw) for raw in olds]
        if field in FOLD_MAX_FIELDS:
            result = max([0 if current is None else current] + values)
        else:
            result = sum(values) + (0 if current is None else current)
        if not -0x8000 <= result <= 0x7FFF:        # a 16-bit signed cell cannot hold the sum: leave this stream alone
            return tuple(_with_end(words_in))
        if result & 0xFFFF == 0:                  # the game's writer treats 0 as "no entry"
            if index is not None:
                del keep[index]
        elif index is None:
            keep.append((result & 0xFFFF) | (field << 16) | (target_slot << 23) | FOLD_BIT)
        else:
            keep[index] = (keep[index] & ~0xFFFF & 0xFFFFFFFF) | (result & 0xFFFF) | FOLD_BIT
    return tuple(_with_end(keep))


def _live_regular(raw: int) -> bool:
    return not raw & DEAD_WORD


def _add_honors(words, years_pro: int, season_now: int, honors) -> tuple[tuple[int, ...], list, list]:
    """-> (stream with the honors added, added [(honor, season, slot, clamped)], skipped [(honor, season, reason)]).

    ``honors`` is [(honor, season)]. A season's slot is ``years_pro - (season_now - season)``. A word already
    present for that field and slot is kept (idempotent). When the stream has a fold floor (a folded word: older
    seasons are merged into that slot) an honor at or below it is counted in the floor slot's folded word instead
    (raised to the disc's count, never summed again, so a second run changes nothing)."""
    from . import nfl2k5_honors_history as hh
    words = [w & ~END_BIT & 0xFFFFFFFF for w in words]
    folded_slots = [(w >> 23) & 31 for w in words if _live_regular(w) and w & FOLD_BIT]
    floor = max(folded_slots) if folded_slots else None
    live = {((w >> 16) & 127, (w >> 23) & 31): i for i, w in enumerate(words) if _live_regular(w)}
    new, added, skipped, below = [], [], [], {}
    for honor, season in sorted(honors, key=lambda h: (h[1], h[0])):
        field = hh.FIELDS[honor]
        slot = years_pro - (season_now - season)
        if not 1 <= slot < years_pro:
            skipped.append((honor, season, f"no completed season slot (years pro {years_pro})"))
            continue
        if floor is not None and slot <= floor:
            below[field] = below.get(field, 0) + 1
            continue
        if (field, slot) in live:
            continue
        live[(field, slot)] = None
        new.append(hh.word(field, slot))
        added.append((honor, season, slot, False))
    for field, count in sorted(below.items()):
        index = live.get((field, floor))
        if index is None:
            new.append(hh.word(field, floor, count) | FOLD_BIT)
            added.append((hh.HONORS[field - hh.FIELD0], None, floor, True))
        elif (words[index] & 0xFFFF) < count:
            words[index] = (words[index] & ~0xFFFF & 0xFFFFFFFF) | count | FOLD_BIT
            added.append((hh.HONORS[field - hh.FIELD0], None, floor, True))
    new.sort(key=lambda w: ((w >> 23) & 31, (w >> 16) & 127))
    return tuple(_with_end(new + words)), added, skipped


def _history_streams(roster) -> tuple[list, set]:
    """-> (streams [(start, stop, key)] in pool order, the keys whose words another player shares).

    The game can leave one player's stream as the tail of another's. Those words belong to both players, so
    neither is edited; every other stream is rebuilt around them."""
    streams = sorted((start, start + len(roster.history_words[key]) * 4, key)
                     for key, start in roster.history_offsets.items() if start is not None)
    shared, cluster, cluster_end = set(), [], -1
    for start, stop, key in streams:
        if cluster and start < cluster_end:
            cluster.append(key)
            cluster_end = max(cluster_end, stop)
        else:
            if len(cluster) > 1:
                shared.update(cluster)
            cluster, cluster_end = [key], stop
    if len(cluster) > 1:
        shared.update(cluster)
    return streams, shared


def _rewrite_history(payload: bytes, roster, streams, shared, new_streams, used_after: int) -> tuple[bytes, dict]:
    """Write ``new_streams`` ({player key: words}) into the saved pool, keeping unowned words and shared tails as
    they are, fixing every +0x2C pointer and the used count, and proving that nothing else changed."""
    used, pool = roster.pool_used, roster.pool
    require(pool is not None, "history pool pointer is missing")
    require(not any(payload[pool + used * 4:pool + max(used_after, used) * 4]), "nonzero history slack")
    end = pool + max(used_after, used) * 4
    require(end <= roster.layout.end, "history rewrite exceeds the roster arena")
    for table in roster.tables.values():
        if table.offset is not None and table.count and used_after > used:
            require(end <= table.offset or pool >= table.offset + table.count * table.stride,
                    "history rewrite would overlap a roster table")
    out = bytearray(payload)
    masks: dict[int, int] = {}
    out[pool:end] = bytes(end - pool)
    masks.update({offset: 255 for offset in range(pool, end)})
    cursor, old_end, new_start, anchor = pool, pool, {}, None
    for start, stop, key in streams:
        require(start >= pool and stop <= pool + used * 4, "history stream outside the pool")
        if start < old_end:                      # a shared tail: unedited, placed relative to its owner
            require(key in shared and anchor is not None and stop <= old_end, "unexpected history overlap")
            new_start[key] = anchor[1] + (start - anchor[0])
            continue
        if start > old_end:                      # words no player points at (left by the game): carried over as they are
            out[cursor:cursor + start - old_end] = payload[old_end:start]
            cursor += start - old_end
        words = new_streams[key]
        new_start[key] = cursor
        anchor = (start, cursor)
        for word in words:
            struct.pack_into("<I", out, cursor, word)
            cursor += 4
        old_end = stop
    if old_end < pool + used * 4:
        out[cursor:cursor + pool + used * 4 - old_end] = payload[old_end:pool + used * 4]
        cursor += pool + used * 4 - old_end
    for player in sorted(roster.players, key=lambda p: p.key):     # players with no stream yet get one at the end
        words = new_streams[player.key]
        if roster.history_offsets[player.key] is None and words:
            new_start[player.key] = cursor
            for word in words:
                struct.pack_into("<I", out, cursor, word)
                cursor += 4
    for player in roster.players:
        pointer = player.offset + 0x2C
        before = payload[pointer:pointer + 4]
        if player.key in new_start:
            struct.pack_into("<i", out, pointer, new_start[player.key] - pointer + 1)
        if bytes(out[pointer:pointer + 4]) != before:
            masks.update({pointer + i: 255 for i in range(4)})
    require(cursor == pool + used_after * 4, f"history pool size mismatch {(cursor - pool) // 4} vs {used_after}")
    struct.pack_into("<I", out, roster.layout.root + 0x40, used_after)
    masks.update({roster.layout.root + 0x40 + i: 255 for i in range(4)})
    result = bytes(out)
    scope = prove_scope(payload, result, masks)
    checked = sr.decode(result, base_year=BASE_YEAR)
    for player in roster.players:
        require(identity(checked.by_key[player.key]) == identity(player), "history rewrite changed a player identity")
        require(checked.history_words[player.key] == new_streams[player.key], "history read-back differs")
    require(checked.pool_used == used_after, "history used count differs")
    return result, scope


def sync_honors(payload: bytes, disc_body: bytes) -> tuple[bytes, dict]:
    """Copy the disc roster's award history (Player Card honors page) into the franchise's own players by identity.

    b778-pc2: a franchise keeps its whole roster, career-stat pool included, in the save, so a franchise started
    before a disc carried the honors page shows "HONORS: NONE YET" for every player. The disc's honor words
    (history fields 96..105, one per honor and season) are re-slotted for the franchise's current season and added
    to the players whose (first, last, birth date) is unique in both rosters. A word the save already has is kept.
    The saved pool is usually full (the game folds old seasons whenever it runs out), so when the honors do not
    fit the oldest seasons are folded the way the game does it (``fold_words``), 15 seasons back first, only as
    deep as needed; the card's career totals do not change, and the receipt lists every folded player.
    """
    from . import nfl2k5_honors_history as hh
    save, roster = franchise(payload)
    season_now = save.header.display_year
    try:
        target = sr.decode(disc_body, preamble=0, reference_year=BASE_YEAR)
    except sr.SaveRostError as exc:
        raise UpgradeRefused(f"honors source must be a disc ROST: {exc}") from exc
    require(target.layout.version in (17, 18), "honors source must be a disc ROST")
    honor_names = {field: name for name, field in hh.FIELDS.items()}
    rows = []                      # the disc's live regular-season honor words, as (player, honor, season)
    for source in target.players:
        for raw in target.history_words[source.key]:
            field = (raw >> 16) & 127
            if field in honor_names and _live_regular(raw) and not raw & FOLD_BIT and raw & 0xFFFF:
                season = BASE_YEAR - source.record.values["years_pro"] + ((raw >> 23) & 31)
                rows.append({"first": source.first, "last": source.last,
                             "birth_date": str(source.record.birth_date or ""),
                             "honor": honor_names[field], "season": season, "value": raw & 0xFFFF, "folded": False})
    streams, shared = _history_streams(roster)
    disc_ids = Counter(identity(p) for p in target.players if p.first or p.last)
    saved = defaultdict(list)
    for player in roster.players:
        if player.first or player.last:
            saved[identity(player)].append(player)
    wanted = defaultdict(list)                # save player key -> [(honor, season)]
    ambiguous, unmatched, shared_skipped = set(), set(), set()
    for row in rows:
        if row["folded"] or not row["value"]:
            continue
        key = (row["first"], row["last"], row["birth_date"])
        players = saved.get(key, [])
        if disc_ids[key] != 1 or len(players) != 1:
            (ambiguous if players or disc_ids[key] > 1 else unmatched).add(" ".join(key[:2]))
            continue
        if players[0].key in shared:
            shared_skipped.add(f"{players[0].first} {players[0].last}")
            continue
        wanted[players[0].key].append((row["honor"], row["season"]))
    by_key = roster.by_key

    def years_pro(player):
        return player.record.values["years_pro"]

    def build(depth):
        out, folded = {}, []
        for key, words in roster.history_words.items():
            player = by_key[key]
            if depth and words and key not in shared:
                after = fold_words(words, years_pro(player), depth)
                if after != words:
                    folded.append(key)
                words = after
            out[key] = tuple(words)
        added, skipped = {}, []
        for key, honors in wanted.items():
            player = by_key[key]
            out[key], got, skip = _add_honors(out[key], years_pro(player), season_now, honors)
            added[key] = got
            skipped += [(key, *item) for item in skip]
        return out, folded, added, skipped, roster.pool_used + sum(
            len(words) - len(roster.history_words[key]) for key, words in out.items())

    capacity = roster.pool_capacity
    chosen = None
    for depth in (0, *SYNC_FOLD_DEPTHS):
        built = build(depth)
        if built[4] <= capacity - HISTORY_RESERVE:
            chosen = (depth, built)
            break
    require(chosen is not None, "the award history does not fit the history pool even after folding old seasons")
    depth, (new_streams, folded, added, skipped, used_after) = chosen
    pool, used = roster.pool, roster.pool_used
    if not any(added.values()) and not folded:
        return payload, {"operation": "honors", "before_sha256": sha(payload), "after_sha256": sha(payload),
                         "disc_roster_sha256": sha(disc_body), "disc_honor_rows": len(rows), "matched_players": len(wanted),
                         "ambiguous_identities_skipped": sorted(ambiguous), "unmatched_identities": len(unmatched),
                         "shared_history_skipped": sorted(shared_skipped),
                         "skipped": [], "fold_depth": 0, "folded_players": [], "changes": [],
                         "used_before": used, "used_after": used, "capacity": capacity,
                         "outside_declared_fields_identical": True, "changed_bytes": 0}
    result, scope = _rewrite_history(payload, roster, streams, shared, new_streams, used_after)
    changes = []
    for key, rows_added in sorted(added.items()):
        player = by_key[key]
        for honor, season, slot, clamped in rows_added:
            changes.append({"pool": player.pool, "index": player.index, "player": f"{player.first} {player.last}",
                            "field": f"honor.{honor}", "history_field": hh.FIELDS[honor], "season": season,
                            "slot": slot, "folded_floor": clamped})
    return result, {"operation": "honors", "before_sha256": sha(payload), "after_sha256": sha(result),
                    "disc_roster_sha256": sha(disc_body), "disc_honor_rows": len(rows),
                    "matched_players": len(wanted), "ambiguous_identities_skipped": sorted(ambiguous),
                    "unmatched_identities": len(unmatched), "shared_history_skipped": sorted(shared_skipped),
                    "skipped": [{"player": f"{by_key[k].first} {by_key[k].last}", "honor": h, "season": s, "reason": r}
                                for k, h, s, r in skipped],
                    "fold_depth": depth,
                    "folded_players": [f"{by_key[k].first} {by_key[k].last}" for k in folded],
                    "used_before": used, "used_after": used_after, "capacity": capacity, "changes": changes, **scope}


def infer_played_clubs(payload: bytes, disc_body: bytes, evidence: Mapping | None = None) -> tuple[bytes, dict]:
    """Compatibility command for the verified club step used by Upgrade.

    Older releases guessed 2026 from opening membership and wrote that guess
    as a fact into field 87. Native transactions cannot date those guesses:
    their bounded ring can wrap or be cleared and contains no season/week.
    Keep candidates in the receipt, restore only counter-pinned evidence,
    and leave missing clubs blank. Existing TEAM words are preserved.
    """
    result, receipt = upgrade_team_history(payload, disc_body, evidence)
    return result, {**receipt, "operation": "played_clubs", "season": BASE_YEAR,
                    "before_sha256": sha(payload), "after_sha256": sha(result),
                    "disc_roster_sha256": sha(disc_body), "fold_depth": 0,
                    "folded_players": [], "shared_history_skipped": []}
# b778-fa3: the 2026-10-22 free-agent depth (Kaepernick and the other verified unsigned, unretired veterans the dated
# refresh adds to the disc's free agents). A franchise keeps its own roster, so an existing franchise only gains them
# here. Nothing grows: each one fills a vacant create-player record of the save, inside the save's own arena.
FREE_AGENT_DEPTH = Path(__file__).resolve().parents[1] / "data" / "nfl2k5_free_agent_depth_2026.v1.json"
SAVE_KEEP_VACANCIES = 4          # vacant records left for Create Player / MyCareer in the franchise
DRAFT_WINDOW_END = 2324          # the native class generator's records end at 2323; never fill one
BLANK_NAME = "****************"


def free_agent_cohort(path=FREE_AGENT_DEPTH) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    require(data.get("schema") == "nfl2k5.free_agent_depth.v1", "unknown free-agent depth data")
    return [{"name": p["name"], "identity": (p["first"], p["last"], p["birth_date"])} for p in data["players"]]


def _save_vacancies(document, payload) -> list:
    """Vacant create records the native importer/creator would take (flags & 5 == 1, unowned, unlisted), outside the
    draft generator's window, with their own two blank name buffers."""
    listed = set(document.free_agents)
    rows = []
    for player in document.by_pool("primary"):
        if (payload[player.offset + 8] & 5 != 1 or player.group != "pool" or player.teams
                or player.offset in listed or (player.pool, player.index) in document.reserve_owner
                or player.index < DRAFT_WINDOW_END or not player.first == player.last == BLANK_NAME):
            continue
        targets = [document._pointer_target(player.offset, key) for key in ("first_name_pointer", "last_name_pointer")]
        if all(document.name_refs.get(t) == 1 for t in targets) and targets[0] != targets[1]:
            rows.append(player)
    return rows


def sync_free_agents(payload: bytes, disc_body: bytes, *, keep: int = SAVE_KEEP_VACANCIES,
                     cohort: list | None = None, strict: bool = False) -> tuple[bytes, dict]:
    """Add the disc's free-agent depth players that this franchise lacks to its free agents.

    Each player's record is the disc's own record for him (ratings, physicals, appearance, commentary), his
    names and college placed through the save's pools, no history, an unsigned contract, and years pro advanced by
    the franchise's completed seasons. Only players on the disc's free-agent list whose (first, last, birth date) is
    nowhere in the save are added, in the data's priority order, and only while ``keep`` vacant records remain.
    ``strict`` (the free-agents command) refuses when none can be added for lack of room.
    """
    from . import nfl2k5_college_check as college_check
    from . import nfl2k5_roster_records as rr
    save, roster = franchise(payload)
    require(type(keep) is int and keep >= 0, "keep must be a non-negative record count")
    cohort = free_agent_cohort() if cohort is None else cohort
    document = rr.RosterDocument(payload, base=roster.layout.preamble, scheme="one_pool", base_year=BASE_YEAR)
    disc = rr.RosterDocument(disc_body, scheme="one_pool", reference_year=BASE_YEAR)
    require(document.free_agent_list is not None, "the franchise has no free-agent list")

    def key(player):
        return player.first, player.last, str(player.record.birth_date)
    in_save = {key(p) for p in document.players if p.first != BLANK_NAME}
    disc_free = defaultdict(list)
    for offset in disc.free_agents:
        disc_free[key(disc.by_offset[offset])].append(disc.by_offset[offset])
    wanted, already, absent = [], [], []
    for row in cohort:
        identity = tuple(row["identity"])
        if identity in in_save:
            already.append(row["name"])
        elif len(disc_free.get(identity, ())) != 1:
            absent.append(row["name"])
        else:
            wanted.append((row["name"], disc_free[identity][0]))
    vacant = _save_vacancies(document, payload)
    room = max(0, len(vacant) - keep)
    room = min(room, document.free_agent_capacity - len(document.free_agents))
    chosen, left = wanted[:room], [name for name, _ in wanted[room:]]
    require(not (strict and wanted and not chosen),
            f"this franchise has {len(vacant)} vacant player records and keeps {keep} for Create Player; "
            f"no room for the {len(wanted)} new free agents")
    year = save.header.year_field
    pointer_bytes = {rr.FIELD_BY_NAME[name].offset for name in rr.POINTER_FIELDS}
    changes, spans = [], []
    for (name, source), target in zip(chosen, sorted(vacant, key=lambda p: -p.index)):
        raw = bytearray(disc_body[source.offset:source.offset + rr.PLAYER_SIZE])
        for at in pointer_bytes:
            raw[at:at + 4] = bytes(4)
        record = rr.PlayerRecord.decode(bytes(raw), scheme="one_pool", reference_year=BASE_YEAR)
        require(all(record.values[f] == 0 for f in ("contract_value", "contract_length", "contract_remaining")),
                f"{name}: the disc record is not an unsigned free agent")
        for field in ("first_name_pointer", "last_name_pointer"):
            record.values[field] = target.record.values[field]
        before_years = record.values["years_pro"]
        record.set("years_pro", min(31, before_years + year))
        target.record = record
        document.set_name(target, "first", source.first)
        document.set_name(target, "last", source.last)
        document.set_college(target, college_check.resolve_index(document.colleges, source.college))
        document.free_agents.append(target.offset)
        spans.append((target.offset, target.offset + rr.PLAYER_SIZE))
        changes.append({"player": name, "pool": target.pool, "index": target.index, "field": "new_free_agent",
                        "disc_index": source.index, "years_pro": [before_years, record.values["years_pro"]],
                        "college": document.colleges[target.college_index] if target.college_index is not None else ""})
    document._reindex_membership()
    result = document.to_body(normalise_commentary=False) if chosen else bytes(payload)
    require(len(result) == len(payload), "save size changed")
    # Scope: the filled records, the player-name pool, the free-agent pointers and their count; nothing else.
    lo, hi = document.names.start, document.names.end
    fa_start = document.free_agent_list
    fa_end = fa_start + 4 * document.free_agent_capacity
    count_at = document.obj_base + rr.FREE_AGENT_COUNT_FIELD
    for offset, (a, b) in enumerate(zip(payload, result)):
        if a != b:
            require(lo <= offset < hi or fa_start <= offset < fa_end or count_at <= offset < count_at + 4
                    or any(s <= offset < e for s, e in spans), f"free-agent write escaped its scope at {offset:#x}")
    check = rr.RosterDocument(result, base=roster.layout.preamble, scheme="one_pool", base_year=BASE_YEAR)
    listed = {key(check.by_offset[o]) for o in check.free_agents}
    require(all(key(source) in listed for _name, source in chosen), "a new free agent is missing after read-back")
    sr.decode(result, base_year=BASE_YEAR)
    after_vacant = len(_save_vacancies(check, result)) if chosen else len(vacant)
    return result, {"operation": "free_agents", "before_sha256": sha(payload), "after_sha256": sha(result),
                    "disc_roster_sha256": sha(disc_body), "franchise_year_field": year,
                    "vacant_records_before": len(vacant), "vacant_records_after": after_vacant, "kept_for_create": keep,
                    "free_agents_before": len(document.original_free_agents), "free_agents_after": len(check.free_agents),
                    "already_in_franchise": already, "not_on_disc": absent, "no_room": left,
                    "changes": changes, "outside_declared_fields_identical": True,
                    "changed_bytes": sum(a != b for a, b in zip(payload, result))}
