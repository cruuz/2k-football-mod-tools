"""Conservative migration of an existing 2026 SOFTDRINK franchise.

Identity pins distinguish imported players from records reused by the game's
draft generator. All changes are planned in memory and carry field receipts.
No input file is ever modified by this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
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
    native_events = save.ledger()
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
                unresolved.append({**common, "reason": reason, "native_event_slots": event_slots})
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
