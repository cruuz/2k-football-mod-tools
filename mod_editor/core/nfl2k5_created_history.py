"""Sourced season history for the real players Studio creates from zero (b779 fh1).

``nfl2k5_free_agents`` and the dated roster refresh write a new identity with an empty history stream
(``_create_new_player``: never borrow a real player's history), so the Player Card showed no season rows and no
TEAM for them.  This pass runs after every identity exists and writes their sourced regular seasons
(``data/nfl2k5_created_history_2026.v1.json``, nflverse-data, CC-BY-4.0) the way ``nfl2k5_franchise_history`` writes
the league players': slot ``years_pro - (base_year - year)``, sparse counters, one TEAM word (field 87, club index + 1)
per season with a games entry, unrelated streams byte for byte intact.

The card derives each row's year from the player's years pro (the record's slot count) and the stored slot, so a
history can only be placed when years pro is the number of seasons since the player entered the league.  The data
stamp ``years_pro_convention = game_years_in_league`` and the record's own years pro are both checked: a record
that still carries the old accrued-season count is refused, never half-labelled.

The pool holds 50,000 dwords.  When the sourced seasons do not fit the free space (less ``HISTORY_RESERVE``), the
least important players' oldest seasons are folded by the game's own fold (``nfl2k5_franchise_upgrade.fold_words``),
so their career totals stay whole; a folded row reads ``--`` for TEAM.  Importance is the spec's player order.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from . import nfl2k5_career_stats as cs
from . import nfl2k5_franchise_history as fh
from . import nfl2k5_save_rost as sr

SCHEMA = "nfl2k5_created_history/v1"
DATA_VERSION = "2026-10-28"
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "nfl2k5_created_history_2026.v1.json"
DATA_SHA256 = "17700012ed679a9011b9205b7a345104d14dda01ca0225baa582fb9ac7b121e7"
CONVENTION = "game_years_in_league"
HISTORY_RESERVE = 64
FOLD_DEPTHS = (12, 10, 8, 6, 4)
TEAM_FIELD = 87
HONOR_FIELD_FIRST = 96          # fields 96..105 are the honors owner's; a created player may already carry them


def load_data(path=DEFAULT_DATA):
    raw = Path(path).read_bytes()
    if Path(path) == DEFAULT_DATA:
        require(hashlib.sha256(raw).hexdigest() == DATA_SHA256, "the shipped created-history data differs from its pin")
    return json.loads(raw.decode("utf-8"))


# The game's own history fold, as nfl2k5_franchise_upgrade.fold_words has it (differentially tested against the retail
# code there). Kept here, not imported, so the build's import closure does not take the whole franchise-upgrade module;
# tests/mod_editor/test_b779_fh1_years_in_league.py proves the two give identical streams.
FOLD_MAX_FIELDS = frozenset((16, 17, 30, 36, 43, 44, 45, 46, 56, 73))
DEAD_WORD = 0x30000000
FOLD_BIT, END_BIT = 0x40000000, 0x80000000


def _signed16(raw: int) -> int:
    return (raw & 0xFFFF) - (0x10000 if raw & 0x8000 else 0)


def _with_end(words) -> list[int]:
    words = [w & ~END_BIT & 0xFFFFFFFF for w in words]
    if words:
        words[-1] |= END_BIT
    return words


def fold_words(words, years_pro: int, depth: int) -> tuple[int, ...]:
    """Merge every live regular-season word at least ``depth`` seasons old into the season ``depth - 1`` old (sum, or max
    for FOLD_MAX_FIELDS) and flag the receiving word folded; a stream whose sum would overflow a signed 16-bit cell is
    returned unfolded."""
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
        if not -0x8000 <= result <= 0x7FFF:
            return tuple(_with_end(words_in))
        if result & 0xFFFF == 0:
            if index is not None:
                del keep[index]
        elif index is None:
            keep.append((result & 0xFFFF) | (field << 16) | (target_slot << 23) | FOLD_BIT)
        else:
            keep[index] = (keep[index] & ~0xFFFF & 0xFFFFFFFF) | (result & 0xFFFF) | FOLD_BIT
    return tuple(_with_end(keep))


def require(ok, message):
    if not ok:
        raise cs.CareerStatsError(message)


def _surname(last: str) -> str:
    return re.sub(r"\s+(?:jr|sr|ii|iii|iv|v)\.?$", "", last.strip(), flags=re.IGNORECASE).casefold()


def season_words(identity: dict, years_pro: int, epoch: int) -> list[int]:
    """The player's words, sorted, without the end bit."""
    words, seen = [], set()
    for season in identity["seasons"]:
        year = season["year"]
        slot = years_pro - (epoch - year)
        require(type(year) is int and 1900 <= year < epoch and 1 <= slot < years_pro <= 31,
                f"unrepresentable completed season {year} for {identity['first']} {identity['last']} (years pro {years_pro})")
        require(year not in seen, "duplicate player season")
        seen.add(year)
        stats = season["stats"]
        require("games" in stats and stats["games"] > 0, "season needs positive sourced games")
        for name, value in stats.items():
            require(name in cs.BY_NAME, "unknown stat field")
            field = cs.BY_NAME[name]
            raw = cs._raw_value(field, Decimal(str(value)))
            if raw or name == "games":
                words.append((slot << 23) | (field.id << 16) | raw)
        if "team_index" in season:
            team = season["team_index"]
            require(type(team) is int and 0 <= team < 32, "invalid season team")
            words.append((slot << 23) | (TEAM_FIELD << 16) | (team + 1))
    words.sort(key=lambda w: (cs.Word(w).slot, cs.Word(w).field))
    return words


def apply_body(body: bytes, spec: dict):
    require(spec.get("schema") == SCHEMA, "unknown created-history schema")
    require(spec.get("years_pro_convention") == CONVENTION,
            "created-history data predates the years-in-league convention; regenerate it with tools/b77/b779_fh1_history_data.py")
    epoch = spec.get("base_year")
    require(type(epoch) is int and 1901 <= epoch <= 2100, "invalid history epoch")
    for name, pin in spec.get("sources", {}).items():
        require(re.fullmatch("[0-9a-f]{64}", pin.get("sha256", "")) and pin.get("url"), f"source {name} needs a hash and URL")
    doc = sr.decode(body, preamble=0, reference_year=epoch)
    require(doc.layout.version in (17, 18), "created history needs a version 17 or 18 roster")
    by_identity: dict[tuple, list] = {}
    for p in doc.players:
        if p.first.startswith("****"):
            continue
        try:
            birth = p.record.birth_date
        except Exception:
            continue
        by_identity.setdefault((birth, _surname(p.last), p.first.casefold()), []).append(p)
    streams, wanted, missing, wrong_years, already = {}, [], [], [], []
    for rank, identity in enumerate(spec["players"]):
        key = (dt.date.fromisoformat(identity["birth_date"]), _surname(identity["last"]), identity["first"].casefold())
        found = by_identity.get(key, [])
        if not found:
            missing.append(f"{identity['first']} {identity['last']}")
            continue
        require(len(found) == 1, f"{identity['first']} {identity['last']}: more than one record has this identity")
        player = found[0]
        count = player.record.values["years_pro"]
        if count != identity["years_pro"]:
            wrong_years.append(f"{player.first} {player.last} record {count} data {identity['years_pro']}")
            continue
        existing = [w & 0x7FFFFFFF for w in doc.history_words[player.key]]
        if any(cs.Word(w).field < HONOR_FIELD_FIRST for w in existing):
            already.append(player.key)           # another history owner wrote seasons for this record: never add a second set
            continue
        words = season_words(identity, count, epoch)
        if words:
            wanted.append((rank, player.key, count, words, existing))
    require(not wrong_years, "years pro differs from the created-history data (old accrued-season count?): "
            + "; ".join(wrong_years[:5]) + (f" and {len(wrong_years) - 5} more" if len(wrong_years) > 5 else ""))
    free = doc.pool_capacity - doc.pool_used - HISTORY_RESERVE
    total = sum(len(item[3]) for item in wanted)
    folded_players, depth_used, depth_used_for = 0, None, {}
    if total > free:
        wanted = [list(item) for item in wanted]
        for item in sorted(wanted, key=lambda it: -it[0]):                  # least important player first
            for depth in FOLD_DEPTHS:                                       # shallowest fold first, deeper only if still short
                if total <= free:
                    break
                folded = list(fold_words(item[3], item[2], depth))
                if len(folded) < len(item[3]):
                    total -= len(item[3]) - len(folded)
                    item[3] = folded
                    folded_players += 1 if depth_used_for.get(item[1]) is None else 0
                    depth_used_for[item[1]] = depth
            if total <= free:
                break
        depth_used = min(depth_used_for.values(), default=None)
        wanted = [tuple(item) for item in wanted]
    require(total <= free, f"created history needs {total} dwords, {free} are free")
    replacements = {}
    for _rank, key, _count, words, existing in wanted:
        merged = sorted([w & 0x7FFFFFFF for w in words] + existing, key=lambda w: (cs.Word(w).slot, cs.Word(w).field))
        merged[-1] |= 0x80000000
        replacements[key] = tuple(merged)
    result, receipt = fh.repack(body, doc, replacements)
    return result, {**receipt, "schema": SCHEMA, "base_year": epoch, "players_written": len(replacements),
                    "words_written": total, "players_not_in_roster": len(missing), "players_already_with_history": len(already),
                    "folded_players": folded_players, "fold_depth": depth_used, "history_reserve": HISTORY_RESERVE,
                    "source_body_sha256": hashlib.sha256(body).hexdigest(), "output_body_sha256": hashlib.sha256(result).hexdigest()}
