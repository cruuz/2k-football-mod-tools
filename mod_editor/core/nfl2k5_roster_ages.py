"""Explicit, previewed DOB shifts. EXPERIMENTAL / UNWITNESSED.

This preserves each eligible player's age on September 1, not their historical
birth year. It does not advance the franchise calendar, years pro or contracts.
Only an explicit save-copy/export action persists a change. A reopened roster
cannot reveal which season its two-digit births were authored for; the caller
must choose the source season. No age is inferred from years pro.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any, Sequence

from . import nfl2k5_roster_records as rr

SCHEMA = "nfl2k5_roster_age_shift/v1"
MIN_AGE, MAX_AGE = 18, 55
DOB_FIELDS = ("birth_year_low", "birth_year_high", "birth_month", "birth_day")


def age_on_september_1(birth: dt.date, season: int) -> int:
    return season - birth.year - ((9, 1) < (birth.month, birth.day))


def preview(document: rr.RosterDocument, source_year: int, target_year: int,
            players: Sequence[rr.Player] | None = None) -> dict[str, Any]:
    """Plan all candidates without mutation; invalid/implausible DOBs are listed.

    Default scope is NFL-flagged primary records (active, free agent, reserve,
    and IR). Unflagged prospects, historical-only records and templates stay out.
    A selected list may narrow this scope but never widen it to templates.
    """
    for year in (source_year, target_year):
        rr.validate_reference_year(year)
        rr._require(year is not None, "choose both source and target season years")
    scope = list(document.players if players is None else players)
    identities = {(p.pool, p.index): p for p in document.players}
    keys = [(p.pool, p.index) for p in scope]
    rr._require(len(set(keys)) == len(keys), "age shift contains duplicate players")
    rr._require(all(identities.get(key) is p for key, p in zip(keys, scope)),
                "age shift contains a player from another document")
    rows, skipped = [], []
    shifted = {(row["pool"], row["index"])
               for prior in getattr(document, "_age_shift_history", [])
               if (prior["source_year"], prior["target_year"]) == (source_year, target_year)
               for row in prior["changes"]}
    for player in scope:
        record = player.record
        identity = {"pool": player.pool, "index": player.index, "name": player.display}
        reason = ""
        if (player.pool, player.index) in shifted:
            reason = "already shifted between these seasons in this session; undo to repeat"
        if player.pool != "primary" or not record.values["player_type"] & rr.FLAG_NFL_PLAYER:
            reason = "not a live NFL primary record (historical or template)"
        raw = record.values["birth_year_low"] | record.values["birth_year_high"] << 3
        try:
            birth = dt.date(rr.decode_birth_year(raw, source_year),
                            record.values["birth_month"], record.values["birth_day"])
        except ValueError:
            reason = reason or "invalid birth date in the source season"
            birth = None
        age = age_on_september_1(birth, source_year) if birth else None
        if age is not None and not MIN_AGE <= age <= MAX_AGE:
            reason = reason or f"age {age} is outside {MIN_AGE}..{MAX_AGE} in {source_year}"
        if reason:
            skipped.append({**identity, "reason": reason})
            continue
        assert birth is not None
        year = birth.year + target_year - source_year
        encoded = rr.encode_birth_year(year, target_year)
        note = ""
        try:
            after = birth.replace(year=year)
        except ValueError:
            # February 29 is the only legal source date invalid after a year shift.
            after = dt.date(year, 2, 28)
            note = "February 29 becomes February 28 in a non-leap target year"
        old = {name: record.values[name] for name in DOB_FIELDS}
        new = dict(old, birth_year_low=encoded & 7, birth_year_high=encoded >> 3,
                   birth_day=after.day)
        # A no-op must retain noncanonical legacy 100..127 encodings too.
        if source_year == target_year:
            new = old.copy()
        if new != old:
            candidate = record.copy()
            candidate.values.update(new)
            byte_changes = [{"offset": player.offset + i, "before": a, "after": b}
                            for i, (a, b) in enumerate(zip(record.encode(), candidate.encode())) if a != b]
            rows.append({**identity, "offset": player.offset, "before": old, "after": new,
                         "birth_before": birth.isoformat(), "birth_after": after.isoformat(),
                         "age_before": age, "age_after": age_on_september_1(after, target_year),
                         "byte_changes": byte_changes, "note": note})
    return {"schema": SCHEMA, "source_year": source_year, "target_year": target_year,
            "reference_year_before": document.reference_year,
            "before_sha256": hashlib.sha256(document.to_body()).hexdigest(),
            "scope": [list(key) for key in keys], "changes": rows, "skipped": skipped,
            "changed": len(rows), "experimental": True, "witnessed": False}


def apply(document: rr.RosterDocument, plan: dict[str, Any]) -> dict[str, Any]:
    """Recompute the entire preview before publishing any in-memory changes."""
    rr._require(plan.get("schema") == SCHEMA, "unknown age-shift preview")
    try:
        lookup = {(p.pool, p.index): p for p in document.players}
        scope = [lookup[tuple(key)] for key in plan["scope"]]
        expected = preview(document, plan["source_year"], plan["target_year"], scope)
    except (KeyError, TypeError) as exc:
        raise rr.RosterRecordError("invalid age-shift preview") from exc
    rr._require(expected == plan, "age-shift preview is stale or altered; preview again")
    for row in plan["changes"]:
        lookup[(row["pool"], row["index"])].record.values.update(row["after"])
    if plan["changed"]:
        document.set_reference_year(plan["target_year"])
        document._age_shift_history = [*getattr(document, "_age_shift_history", []), plan]
    return {**plan, "after_sha256": hashlib.sha256(document.to_body()).hexdigest(),
            "saved": False, "calendar_changed": False, "years_pro_changed": False,
            "summary": (f"Shifted {plan['changed']} players from season {plan['source_year']} "
                        f"to {plan['target_year']}; skipped {len(plan['skipped'])}. "
                        "Save a copy to keep these changes. Calendar and years pro are unchanged.")}
