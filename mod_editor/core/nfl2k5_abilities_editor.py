"""Tier authoring and reversible rating assignment. EXPERIMENTAL / UNWITNESSED.

Only the existing record footer is edited. No rating, cosmetic star, depth
lock, Guardian flag, pointer, identity or membership is changed. Legacy tier0
flags are read without migration; explicit authoring enforces slot limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from . import nfl2k5_roster_records as rr
from . import nfl2k5_abilities_runtime as runtime

SCHEMA = "nfl2k5.abilities.assignment.v2"
TIERS = rr.ABILITY_TIERS
LIMITS = (0, 2, 4, 7)
TIER_MASK = 0xC000
OWNED_MASK = TIER_MASK | runtime.ABILITY_MASK
LABELS = {
    "speedster": "Speedster", "right_stick_moves": "Right-Stick Moves",
    "juke": "Juke / Agility", "spin": "Spin / Pass Rush",
    "truck": "Truck / Tackle Shed", "hurdle": "Hurdle / Jumping",
    "stiff_arm": "Stiff-Arm / Strength",
}
MASKS = {name: bit << (0 if field == "unknown_52" else 9)
         for name, (field, bit) in rr.ABILITY_BITS.items()}
RATINGS = {"speedster": "speed", "right_stick_moves": "agility", "juke": "agility",
           "spin": "pass_rush", "truck": "break_tackle", "hurdle": "jumping",
           "stiff_arm": "strength"}


class AssignmentError(ValueError):
    """Invalid capacity, identity, or stale assignment; no mutation occurs."""


def _require(ok, message):
    if not ok:
        raise AssignmentError(message)


def _tier(value):
    _require(type(value) is int and 0 <= value <= 3, "tier must be an integer 0..3")
    return value


def footer(record):
    return int.from_bytes(record.encode()[0x52:0x54], "little")


def _identity(player):
    v = player.record.values
    return dict(pool=player.pool, index=player.index, offset=player.offset,
                first=player.first, last=player.last,
                birth=[v[k] for k in ("birth_month", "birth_day", "birth_year_low", "birth_year_high")])


def _selection(tier, abilities):
    _tier(tier)
    _require(isinstance(abilities, (list, tuple, set, frozenset)), "abilities must be a collection of names")
    _require(all(isinstance(name, str) and name in MASKS for name in abilities), "unknown ability")
    _require(len(set(abilities)) == len(abilities), "duplicate ability")
    _require(len(abilities) <= LIMITS[tier], f"{TIERS[tier]} permits {LIMITS[tier]} abilities")
    return tier << 14 | sum(MASKS[name] for name in abilities)


def _row(player, tier, abilities):
    after = _selection(tier, abilities)
    before = footer(player.record) & OWNED_MASK
    mask = before ^ after
    if mask & TIER_MASK:
        mask |= TIER_MASK  # a tier is one two-bit field
    return dict(identity=_identity(player), before=before, after=after, mask=mask,
                tier=TIERS[tier], abilities=[n for n in MASKS if n in abilities])


def _plan(document, rows, *, kind, options=None):
    return dict(schema=SCHEMA, model_version=2, experimental=True, runtime_witnessed=False,
                kind=kind, options=options or {},
                source_sha256=hashlib.sha256(document.to_body()).hexdigest(),
                changed_players=sum(bool(row["mask"]) for row in rows), rows=rows)


def plan_player(document, player, *, tier, abilities):
    _require(any(p is player for p in document.players), "player is not in the current roster")
    return _plan(document, [_row(player, tier, abilities)], kind="player")


def fit_tier(record, tier):
    """Explicit tier changes retain flags in stable UI order up to capacity.

    Unranked clears flags; loading a legacy record never calls this helper.
    The caller shows all removals in the receipt, and undo restores them.
    """
    return [name for name, enabled in record.abilities.items() if enabled][:LIMITS[_tier(tier)]]


def _candidates(player):
    record = player.record
    position = record.position_name
    # Coverage and hands effects have no independent flag. Do not assign a
    # mislabeled substitute to a defensive back or receiver.
    if position in ("QB", "HB", "RB", "FB", "WR", "TE"):
        skills = ("juke", "truck", "hurdle", "stiff_arm")
    elif position in ("C", "G", "T", "LG", "RG", "LT", "RT"):
        skills = ("stiff_arm",)
    elif position in ("CB", "FS", "SS", "S"):
        skills = ("hurdle", "stiff_arm")
    elif position in ("K", "P"):
        skills = ()  # no proved kicking ability; tier alone is allowed
    else:
        skills = ("spin", "stiff_arm", "hurdle")
    if 100 <= record.get("speed") <= 127:
        skills += ("speedster",)
    return sorted(skills, key=lambda n: (-min(127, record.get(RATINGS[n])), list(MASKS).index(n)))


def plan_auto_assign(document, *, top_n=10):
    """Replace tiers/flags on active NFL club players, across the whole league.

    Rank within the document's position scheme by the mean of that position's
    key ratings (integer sum, stable pool index tie-break). Rank1 is X-Factor,
    ranks2..ceil(N/3) Superstar, the rest Star. Other eligible players clear.
    Free agents, templates, historic-only players and draft prospects stay.
    """
    _require(type(top_n) is int and 1 <= top_n <= 100, "top N must be an integer 1..100")
    groups = defaultdict(list)
    for player in document.players:
        if (player.pool == "primary" and player.record.get("player_type") & 4
                and any(0 <= team < 32 for team in player.teams)):
            groups[player.record.get("position")].append(player)
    rows = []
    for position, players in sorted(groups.items()):
        keys = rr.key_ratings(position)
        _require(bool(keys), f"no rating profile for position {position}")
        _require(all(0 <= p.record.get(k) <= 127 for p in players for k in set(keys) | set(RATINGS.values())),
                 f"position {position} has a rating outside the signed 0..127 range")
        ranked = sorted(players, key=lambda p: (-sum(min(127, p.record.get(k)) for k in keys), p.index))
        for rank, player in enumerate(ranked, 1):
            tier = 0 if rank > top_n else 3 if rank == 1 else 2 if rank <= (top_n + 2) // 3 else 1
            abilities = _candidates(player)[:LIMITS[tier]]
            # Stick gestures require both permissions when both locks are on.
            if "juke" in abilities and len(abilities) < LIMITS[tier]:
                abilities.append("right_stick_moves")
            row = _row(player, tier, abilities)
            row.update(position=player.record.position_name, rank=rank,
                       rating_sum=sum(min(127, player.record.get(k)) for k in keys), rating_fields=list(keys))
            rows.append(row)
    return _plan(document, rows, kind="auto", options=dict(top_n=top_n, scope="active NFL club players"))


def apply_plan(document, plan, *, reverse=False, require_fresh=False):
    """Validate every row first; exact masked replay/undo preserves other edits.

    Initial UI application requires the reviewed document hash. Later undo and
    redo compare identity and owned changed bits, allowing unrelated edits.
    A mixture of source/destination states refuses instead of partly applying.
    """
    _require(isinstance(plan, dict) and plan.get("schema") == SCHEMA, "unsupported abilities receipt")
    _require(type(reverse) is bool and type(require_fresh) is bool, "replay switches must be Boolean")
    if require_fresh:
        _require(hashlib.sha256(document.to_body()).hexdigest() == plan.get("source_sha256"),
                 "roster changed since preview; preview the assignment again")
    rows = plan.get("rows")
    _require(isinstance(rows, list) and len(rows) <= len(document.players), "invalid assignment rows")
    lookup = {(p.pool, p.index): p for p in document.players}
    prepared, states, seen = [], set(), set()
    for row in rows:
        _require(isinstance(row, dict) and isinstance(row.get("identity"), dict), "invalid player row")
        identity = row["identity"]
        key = identity.get("pool"), identity.get("index")
        _require(type(key[0]) is str and type(key[1]) is int, "invalid player key")
        player = lookup.get(key)
        _require(player is not None and key not in seen and _identity(player) == identity,
                 "missing, duplicate, or replaced player identity")
        seen.add(key)
        before, after, mask = (row.get(k) for k in ("before", "after", "mask"))
        _require(all(type(v) is int and v >= 0 and v & ~OWNED_MASK == 0 for v in (before, after, mask)),
                 "assignment contains foreign bits")
        expected_mask = before ^ after
        if expected_mask & TIER_MASK:
            expected_mask |= TIER_MASK
        _require(mask == expected_mask, "assignment mask does not match its edit")
        _require(_selection(after >> 14, row.get("abilities")) == after, "invalid destination abilities")
        source, target = (after, before) if reverse else (before, after)
        current = footer(player.record)
        if mask:
            if current & mask == source & mask:
                states.add("source")
            elif current & mask == target & mask:
                states.add("target")
            else:
                raise AssignmentError("ability fields changed since this receipt")
        word = current & ~mask | target & mask
        if mask and not reverse:
            _require((word & runtime.ABILITY_MASK).bit_count() <= LIMITS[word >> 14],
                     "current tier or abilities conflict with this receipt")
        prepared.append((player, word, mask))
    _require(len(states) <= 1, "mixed assignment state; no players were changed")
    before_body = document.to_body()
    if states == {"source"}:
        for player, word, mask in prepared:
            if mask:
                player.record.values["unknown_52"] = word & 255
                player.record.values["unknown_53_high"] = word >> 9
                # The unchanged star is in bit8; never assign star_tag here.
    after_body = document.to_body()
    return dict(schema=SCHEMA, status="applied" if before_body != after_body else "already_applied",
                reverse=reverse, changed_players=sum(bool(m) for _, _, m in prepared) if states == {"source"} else 0,
                changed_bytes=sum(a != b for a, b in zip(before_body, after_body)),
                source_sha256=hashlib.sha256(before_body).hexdigest(),
                result_sha256=hashlib.sha256(after_body).hexdigest(), plan=plan,
                experimental=True, runtime_witnessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--roster", type=Path, help="read-only disc image or loose extraction")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", type=Path, help="new JSON containing receipt and compatible roster edits")
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(dict(tiers=TIERS, limits=LIMITS, abilities=LABELS, effects=runtime.EFFECTS), indent=2))
        return
    if not args.roster or not args.output:
        parser.error("--roster and --output are required")
    document = rr.load_image(args.roster)
    plan = plan_auto_assign(document, top_n=args.top_n)
    receipt = apply_plan(document, plan, require_fresh=True)
    result = dict(receipt=receipt, roster_edits=rr.edits_document(document, name="Abilities rules v2"))
    with args.output.resolve().open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(f"EXPERIMENTAL / UNWITNESSED: assigned {receipt['changed_players']} players")


if __name__ == "__main__":
    main()
