"""Measured appearance for real players the dated refresh creates (b778 ap1).

The dated roster refresh creates 2026 players from a zero record.  This module
gives each one the appearance b778 fa5 measured for the free-agent tail: a
nflverse headshot, a YuNet face box, cheek/forehead/nose ITA -> native tone 0..5,
body from height/weight BMI, a native generic face of that tone, and the dreads
bit only for a checked hanging-locs headshot.  The measurements and the review
flags live in ``data/nfl2k5_refresh_appearance_2026.v1.json`` per player.

Only a created record with no authored appearance is written.  A record that
already carries a nonzero skin, face or dreads value (a likeness scan, a coach,
a hand-set entry) is left alone, as are hair style and photo id: this module
never touches them.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "nfl2k5.created_appearance.v1"
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "nfl2k5_refresh_appearance_2026.v1.json"
APPEARANCE_FIELDS = ("skin", "face", "body", "dreads")
AUTHORED_FIELDS = ("skin", "face", "dreads")
PORTRAIT_BASE = 7100          # retail's no-photo range starts here; below it a real portrait exists


class AppearanceError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise AppearanceError(message)


def load_data(path=DEFAULT_DATA):
    """Load and validate the measured appearance table."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(data.get("schema") == SCHEMA, "Unknown created-appearance schema")
    players = data.get("players")
    _require(isinstance(players, dict) and players, "Created-appearance table is empty")
    review = {(r["gsis_id"], r["confidence"]) for r in data.get("review", ())}
    for gsis, entry in players.items():
        _require(isinstance(gsis, str) and gsis, "Appearance entry without a gsis id")
        _require(entry.get("name") and entry.get("method") and entry.get("measure"),
                 f"{gsis}: appearance needs name, method and measure")
        _require(entry.get("appearance_reviewed") is True, f"{gsis}: appearance was not reviewed")
        _require(0 <= entry["skin"] <= 5, f"{gsis}: skin outside the native range")
        _require(0 <= entry["face"] <= 6, f"{gsis}: face outside the native range")
        _require(0 <= entry["body"] <= 3, f"{gsis}: body outside the native range")
        _require(entry.get("dreads") in (0, 1), f"{gsis}: dreads must be 0 or 1")
        _require(entry.get("confidence") in ("measured", "reviewed", "low"),
                 f"{gsis}: unknown appearance confidence")
        if entry["confidence"] == "low":
            _require((gsis, "low") in review, f"{gsis}: low-confidence appearance is not listed for review")
    return data


def needs_appearance(values) -> bool:
    """True when a created row carries no authored skin, face, dreads or real portrait."""
    if any(int(values.get(name, 0) or 0) for name in AUTHORED_FIELDS):
        return False
    photo = int(values.get("photo_id", 0) or 0)
    return not 0 < photo < PORTRAIT_BASE


def measurement(gsis_id, data):
    """The validated measurement for this source identity, or None when it was not measured."""
    entry = (data.get("players") or {}).get(gsis_id)
    if entry is None:
        return None
    return {name: entry[name] for name in APPEARANCE_FIELDS}


def apply(player, values, gsis_id, data):
    """Write the measured appearance into a created record.

    ``values`` are the row fields the source supplied.  A nonzero skin, face or
    dreads value is an authored appearance and wins; otherwise the measured skin,
    face, BMI body and checked dreads bit are written.  Returns the written
    fields (empty when the record was left alone).
    """
    if not needs_appearance(values):
        return {}
    measured = measurement(gsis_id, data)
    if measured is None:
        return {}
    for name, value in measured.items():
        player.record.set(name, value)
    return measured


def receipt(created_ids, written, data):
    """A compact build receipt; the per-player method/measure/confidence stay in the data file."""
    players = data.get("players") or {}
    names = [players[g]["name"] for g in created_ids if g in players]
    filled = [g for g in created_ids if g in written]
    return {
        "table": Path(DEFAULT_DATA).name,
        "as_of": data.get("as_of"),
        "created": len(created_ids),
        "filled": len(filled),
        "measured": sum(1 for g in filled if players[g]["confidence"] == "measured"),
        "reviewed": [players[g]["name"] for g in filled if players[g]["confidence"] == "reviewed"],
        "low_confidence": [players[g]["name"] for g in filled if players[g]["confidence"] == "low"],
        "not_measured": [players[g]["name"] for g in created_ids if g not in written and g in players],
        "missing_from_table": [g for g in created_ids if g not in players],
        "dreads": [players[g]["name"] for g in filled if players[g]["dreads"]],
        "names": names,
    }
