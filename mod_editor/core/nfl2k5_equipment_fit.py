"""Position gear for players the roster builders create from scratch (job b778-eq1).

holtbolt (`#2k5-bugs`, 10/24): "the colts kick returner Gould (rookie) has a kicker/punters facemask and
overall look."  A 2K5 player's gear is fifteen bit fields inside his 0x54 record and nothing derives it
from his position at run time.  The dated roster refresh and the free-agent pool create a record from
zero and wrote only the fields their source rows carry (identity, ratings, body, sometimes the measured
skin/face), so the gear stayed at zero.  Face Mask 1 (raw 0) is the classic two-bar mask and the mask
retail kickers and punters wear most (39 of 70 and 38 of 69 on the retail roster; 41 of 242 receivers
also wear it), so a new receiver who keeps it reads as a kicker.  Anthony Gould (primary 2528, WR,
Indianapolis' KR1 and PR on the released v0.6.1 disc) is one of the 90 dated-refresh players with every
gear field at zero.

The native draft-class generator (FUN_000E6780) does not have this gap: it copies the gear fields from
the 68 secondary records, four templates per position, and the shipped 2026 roster updates those
templates too.  A created player therefore takes the same position's template gear here: one of the four
templates (chosen by his stable primary index, so a class does not come out identical), for every gear
field his source row did not name.  Skin, face, body, hair, hand and portrait stay with the appearance
pipeline; a row that carries its own gear field keeps it; callers only pass records they have just
created, so no existing player's equipment changes.
"""
from __future__ import annotations

from typing import Iterable

from . import nfl2k5_roster_records as rr

OWNER = "nfl2k5_equipment_fit"
SCHEMA = "nfl2k5_equipment_fit/v1"

# The record fields that are gear rather than identity or body.  These are the fields the native class
# generator copies from the low/high template records (the face-mask, visor, mouthpiece, sleeve, glove,
# wrist and elbow blocks of its seventeen coin blocks), plus the helmet shell and shoes.
EQUIPMENT_FIELDS = (
    "helmet", "face_mask", "face_shield", "mouthpiece", "eye_black", "turtleneck", "sleeves",
    "neck_roll", "left_glove", "right_glove", "left_wrist", "right_wrist", "left_elbow", "right_elbow",
    "left_shoe", "right_shoe",
)

#: The record fields this owner deliberately leaves alone: the appearance pipeline sets these from the
#: headshot (or the row already names them) and the template must not overwrite a real player's look.
NOT_EQUIPMENT = ("skin", "face", "body", "dreads", "hair_style", "headless", "hand", "photo_id")


def templates_for_position(document: rr.RosterDocument, position: int) -> tuple[rr.Player, ...]:
    """The class generator's own templates for one position, in the secondary table's order."""

    return tuple(player for player in document.by_pool("secondary")
                 if player.record.get("position") == int(position))


def template_for_player(document: rr.RosterDocument, player: rr.Player) -> rr.Player | None:
    """The template whose gear a created player of this position and index takes."""

    templates = templates_for_position(document, player.record.get("position"))
    return templates[player.index % len(templates)] if templates else None


def fill_created_player(document: rr.RosterDocument, player: rr.Player,
                        supplied: Iterable[str] = ()) -> dict[str, int]:
    """Copy the position template's gear onto a just-created player; return what changed.

    Only fields absent from ``supplied`` are written, so a source row that names its own gear keeps
    it.  A roster whose secondary table is absent (a foreign or stand-in body) is left untouched
    rather than guessed at.
    """

    template = template_for_player(document, player)
    if template is None:
        return {}
    named = set(supplied)
    changed: dict[str, int] = {}
    for name in EQUIPMENT_FIELDS:
        if name in named:
            continue
        value = template.record.get(name)
        if player.record.get(name) != value:
            player.record.set(name, value)
            changed[name] = value
    return changed


def fill_created_players(document: rr.RosterDocument,
                         indices: Iterable[int]) -> dict[int, dict[str, int]]:
    """Fill named records a caller has already created from zero; never scans for a signature.

    This is the replay form for a body that is already built (the emulator fixture and tests).  The
    build calls ``fill_created_player`` at the two creation sites instead, so a real record whose
    equipment was deliberately emptied is never rewritten.
    """

    wanted = set(indices)
    filled: dict[int, dict[str, int]] = {}
    for player in document.by_pool("primary"):
        if player.index not in wanted:
            continue
        changed = fill_created_player(document, player)
        if changed:
            filled[player.index] = changed
    return filled
