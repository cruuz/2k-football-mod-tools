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
from pathlib import Path

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


# Sorted 96-bit, domain-specific identity checksums from the pinned retail body. This also
# recognizes surviving individuals on edited build inputs for which no clean disc is available.
STOCK_FINGERPRINTS = Path(__file__).resolve().parents[2] / "data/nfl2k5_stock_dob_fingerprints.txt"
FINGERPRINT_SIZE = 12
STOCK_DOB_SHA256 = "1c6408a01c177cb80b9e5e782c49a17ca7f1f97be87494873a3aa5b64c1fc2bc"


def _fingerprint(player) -> bytes:
    name = (player.first.casefold() + "\0" + player.last.casefold() + "\0").encode("utf8")
    birth = bytes(player.record.values[k] for k in DOB_FIELDS)
    return hashlib.blake2b(name + birth, digest_size=FINGERPRINT_SIZE, person=b"2k5-stock-dob").digest()


def _stock_fingerprints(stock_body: bytes | None) -> set[bytes]:
    if stock_body is not None:
        if hashlib.sha256(stock_body).hexdigest() != rr.RETAIL_BODY_SHA256:
            raise rr.RosterRecordError("Cannot generate stock birthday checksums from a modified roster")
        stock = rr.load_body(stock_body, reference_year=2004)
        return {_fingerprint(p) for p in stock.by_pool("primary")
                if p.first and p.last and p.record.values["player_type"] & rr.FLAG_NFL_PLAYER}
    try:
        data = bytes.fromhex(STOCK_FINGERPRINTS.read_text(encoding="ascii"))
    except (ValueError, OSError) as exc:
        raise rr.RosterRecordError("Cannot read the packaged stock birthday checksums") from exc
    if hashlib.sha256(data).hexdigest() != STOCK_DOB_SHA256:
        raise rr.RosterRecordError("The packaged stock birthday checksums are incomplete or damaged")
    return {data[i:i + FINGERPRINT_SIZE] for i in range(0, len(data), FINGERPRINT_SIZE)}


def preserve_stock_ages(body: bytes, *, stock_body: bytes | None = None, source_year: int = 2004,
                        target_year: int = 2026) -> tuple[bytes, dict[str, Any]]:
    """Rebase only surviving NFL identities with an exact birth date on the retail main roster.

    Matching names and original DOBs survives pool growth, reordering, position changes and trades.
    An already-shifted birthday does not match again.
    """
    if source_year != 2004:
        raise rr.RosterRecordError("The original stock roster is for the 2004 season")
    known = _stock_fingerprints(stock_body)
    document = rr.load_body(body, reference_year=source_year)
    retained = [p for p in document.by_pool("primary")
                if p.record.values["player_type"] & rr.FLAG_NFL_PLAYER and _fingerprint(p) in known]
    plan = preview(document, source_year, target_year, retained)
    # Write only the actual birthday bit fields. A build can already contain other owners' edits.
    changed = bytearray(body)
    for row in plan["changes"]:
        for edit in row["byte_changes"]:
            if changed[edit["offset"]] != edit["before"]:
                raise rr.RosterRecordError("Stock birthday does not match the final main roster")
            changed[edit["offset"]] = edit["after"]
    return bytes(changed), {"stock_age_policy": "preserve_age", "source_year": source_year,
                            "target_year": target_year, "matched": len(retained), "changed": plan["changed"],
                            "skipped_invalid": len(plan["skipped"]), "before_sha256": hashlib.sha256(body).hexdigest(),
                            "after_sha256": hashlib.sha256(changed).hexdigest()}


def apply_image(path, *, source_year: int = 2004, target_year: int = 2026) -> dict[str, Any]:
    """Preserve verified stock ages in the main ROST of a build copy, even for edited source discs."""
    archive_type = rr._outer_image()
    with archive_type(path, writable=True) as archive:
        entry = rr._entry(archive)
        original = archive.read(entry.virtual_offset, entry.size)
        if original[:4] != b"ROST":
            raise rr.RosterRecordError("Could not read the main roster resource")
        header = rr.RESOURCE_HEADER_SIZE
        changed, receipt = preserve_stock_ages(original[header:],
                                                source_year=source_year, target_year=target_year)
        if changed != original[header:]:
            raw = original[:header] + changed
            if (len(raw) != entry.size or archive.write(entry.virtual_offset, raw) != len(raw)
                    or archive.read(entry.virtual_offset, entry.size) != raw):
                raise rr.RosterRecordError("Could not verify the saved player birthdays")
    return receipt
