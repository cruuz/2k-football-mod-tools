"""Precise RE spike for APF community G1 (Dime ILB→OLB) and G2 (Ace TE→WR).

This module does **not** write package-rule bytes. It pins the offline layout
constants and fixture identities that the next package-rule writer must use,
and it analyses a parsed PLAY book through the shipped inspector types so
tests drive real entry points.

Fixture identity (2K5 stock PLAY book used across clone proofs):
  asset_id: ``nfl2k5.resource.o0308.c0000.k504c4159``
  pack_offset (disc slice): ``106803200`` (see formation_play_writer tests)
  layout constants: :mod:`mod_editor.core.nfl2k5_playbook_inspector`

G1 hypothesis (Dime ILB benched / treated as OLB):
  Defense slots 4–10 first-opcode ``0x1b`` band (~72–78%) is the LB/DB band
  (``PLAY_PLAYER_ROLE_HYPOTHESIS``). Dime package membership likely remaps
  ILB field time into OLB/DB slots via formation aux ``0x50`` membership
  and/or per-play assignment descriptors at ``PLAY_BASE + play*0x60 + 8 + slot*8``.

G2 hypothesis (Ace TE→WR on long downs):
  Offense assignment descriptors + Ace formation play-link packed values
  (``FORMATION_AUX`` / formation play links) promote TE membership to a WR
  slot under long-down package rules. Compare Ace vs non-Ace formation
  link tables and slot 0–10 descriptors for TE-named plays.

APF surface (parallel, not 2K5 o0308):
  MASTER PLAY outer inventory (586 plays × 11 slots) — assignment-route
  writer already offline-proved for exact descriptor copy; package-rule
  bits remain the gap for G1/G2 fix packs.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .nfl2k5_playbook_inspector import (
    ASSIGNMENT_COUNT,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_PLAY_LINKS,
    FORMATION_SIZE,
    NODE_BASE,
    NODE_SIZE,
    PLAY_BASE,
    PLAY_SIZE,
    PlaybookAssignment,
    PlaybookFormation,
    PlaybookPlay,
    Nfl2k5Playbook,
)

# Disc fixture used by clone offline proofs (no retail bytes embedded here).
O0308_ASSET_ID = "nfl2k5.resource.o0308.c0000.k504c4159"
O0308_PACK_OFFSET = 106_803_200

# Layout offsets relative to PLAY resource body (after 0x20 resource header).
# Verified against nfl2k5_playbook_inspector constants + PLAY_* product docs.
G1_G2_LAYOUT: dict[str, int | str] = {
    "resource_header_size": 0x20,
    "formation_base": FORMATION_BASE,
    "formation_size": FORMATION_SIZE,
    "formation_aux_base": FORMATION_AUX_BASE,
    "formation_aux_size": FORMATION_AUX_SIZE,
    "formation_play_links": FORMATION_PLAY_LINKS,
    "play_base": PLAY_BASE,
    "play_size": PLAY_SIZE,
    "assignment_count": ASSIGNMENT_COUNT,
    "assignment_record_size": 8,  # descriptor u32 + chain_start u32
    "node_base": NODE_BASE,
    "node_size": NODE_SIZE,
    "o0308_asset_id": O0308_ASSET_ID,
    "o0308_pack_offset": O0308_PACK_OFFSET,
    # Absolute body offset of play N assignment slot S:
    #   PLAY_BASE + N*PLAY_SIZE + 8 + S*8
    "assignment_offset_formula": "PLAY_BASE + play_index*PLAY_SIZE + 8 + slot*8",
    # Descriptor word (family/package hints live here — bit map incomplete):
    "descriptor_offset_in_play": 0x04,
}


def assignment_body_offset(play_index: int, slot: int) -> int:
    """Body-relative offset of one assignment (descriptor+chain) in a PLAY."""

    if not 0 <= slot < ASSIGNMENT_COUNT:
        raise ValueError(f"slot must be 0..{ASSIGNMENT_COUNT - 1}")
    if play_index < 0:
        raise ValueError("play_index must be non-negative")
    return PLAY_BASE + play_index * PLAY_SIZE + 8 + slot * 8


def descriptor_body_offset(play_index: int) -> int:
    """Body-relative offset of the play-level descriptor word (+0x04)."""

    if play_index < 0:
        raise ValueError("play_index must be non-negative")
    return PLAY_BASE + play_index * PLAY_SIZE + 4


@dataclass(frozen=True, slots=True)
class SlotRoleSnapshot:
    """One assignment slot from a real or synthetic play."""

    play_index: int
    slot: int
    descriptor: int
    chain_start: int
    body_offset: int
    first_opcode: int | None
    chain_length: int


@dataclass(frozen=True, slots=True)
class PackageRuleSpikeResult:
    """Offline RE spike result for one community bug id."""

    bug_id: str
    status: str  # "re_spike" | "offline_writer_proved"
    fixture_asset_id: str
    fixture_pack_offset: int
    layout: dict[str, int | str]
    matching_formations: tuple[str, ...]
    matching_plays: tuple[str, ...]
    slot_snapshots: tuple[SlotRoleSnapshot, ...]
    hypothesis: str
    next_offline_writer_gate: str


_DIME_RE = re.compile(r"\bdime\b", re.IGNORECASE)
_ACE_RE = re.compile(r"\bace\b", re.IGNORECASE)


def _first_opcode(book: Nfl2k5Playbook, assignment: PlaybookAssignment) -> tuple[int | None, int]:
    try:
        chain = book.chain(assignment.chain_start_index)
    except Exception:  # noqa: BLE001 - synthetic books may omit chains
        return None, 0
    if not chain.nodes:
        return None, 0
    return chain.nodes[0].opcode, len(chain.nodes)


def _snapshots_for_play(
    book: Nfl2k5Playbook, play: PlaybookPlay
) -> tuple[SlotRoleSnapshot, ...]:
    rows: list[SlotRoleSnapshot] = []
    for assignment in play.assignments:
        opcode, length = _first_opcode(book, assignment)
        rows.append(
            SlotRoleSnapshot(
                play_index=play.index,
                slot=assignment.slot_index,
                descriptor=assignment.descriptor_word,
                chain_start=assignment.chain_start_index,
                body_offset=assignment_body_offset(play.index, assignment.slot_index),
                first_opcode=opcode,
                chain_length=length,
            )
        )
    return tuple(rows)


def _named(
    formations: Iterable[PlaybookFormation],
    plays: Iterable[PlaybookPlay],
    pattern: re.Pattern[str],
) -> tuple[tuple[str, ...], tuple[PlaybookPlay, ...]]:
    formation_names = tuple(
        f.name for f in formations if pattern.search(f.name or "")
    )
    matched_plays = tuple(p for p in plays if pattern.search(p.name or ""))
    # Also include plays linked from matching formations when names differ.
    return formation_names, matched_plays


def spike_g1_dime_ilb(book: Nfl2k5Playbook) -> PackageRuleSpikeResult:
    """Analyse a book for Dime package / ILB slot evidence (G1).

    Focus slots 4–5 (start of defense LB band per role hypothesis). Reports
    exact body offsets for each assignment so a future writer can pin only
    those eight-byte fields with an independent byte-diff verifier.
    """

    formation_names, plays = _named(book.formations, book.plays, _DIME_RE)
    # If no Dime-named plays, still snapshot first defensive play for layout.
    if not plays:
        plays = tuple(p for p in book.plays if p.family_id == 1)[:3]
    snapshots: list[SlotRoleSnapshot] = []
    for play in plays[:8]:
        for snap in _snapshots_for_play(book, play):
            if snap.slot in (4, 5, 6):  # ILB/OLB candidate band
                snapshots.append(snap)
    return PackageRuleSpikeResult(
        bug_id="G1",
        status="re_spike",
        fixture_asset_id=O0308_ASSET_ID,
        fixture_pack_offset=O0308_PACK_OFFSET,
        layout=dict(G1_G2_LAYOUT),
        matching_formations=formation_names,
        matching_plays=tuple(p.name for p in plays[:12]),
        slot_snapshots=tuple(snapshots),
        hypothesis=(
            "Dime package remaps ILB field membership into OLB/DB slots. "
            "Defense first-opcode 0x1b dominates slots 4–10; compare Dime vs "
            "Nickel assignment descriptors at "
            f"body+{PLAY_BASE:#x}+play*{PLAY_SIZE:#x}+8+slot*8 and formation "
            f"aux membership at body+{FORMATION_AUX_BASE:#x}."
        ),
        next_offline_writer_gate=(
            "Census Dime vs Nickel on o0308-class fixture: if only assignment "
            "descriptor/chain_start differ in slots 4–5, ship a copy-only "
            "package-rule writer that patches those 8-byte fields with "
            "independent full-resource reparse + volume byte-diff verifier. "
            "Do not invent opcodes. Status remains re_spike until that gate."
        ),
    )


def spike_g2_ace_te(book: Nfl2k5Playbook) -> PackageRuleSpikeResult:
    """Analyse a book for Ace package / TE→WR evidence (G2)."""

    formation_names, plays = _named(book.formations, book.plays, _ACE_RE)
    if not plays:
        plays = tuple(p for p in book.plays if p.family_id == 0)[:3]
    snapshots: list[SlotRoleSnapshot] = []
    for play in plays[:8]:
        for snap in _snapshots_for_play(book, play):
            # TE/WR candidate slots: mid/skill (3,6,7,8) per role variance docs
            if snap.slot in (3, 6, 7, 8, 9):
                snapshots.append(snap)
    return PackageRuleSpikeResult(
        bug_id="G2",
        status="re_spike",
        fixture_asset_id=O0308_ASSET_ID,
        fixture_pack_offset=O0308_PACK_OFFSET,
        layout=dict(G1_G2_LAYOUT),
        matching_formations=formation_names,
        matching_plays=tuple(p.name for p in plays[:12]),
        slot_snapshots=tuple(snapshots),
        hypothesis=(
            "Ace package long-down rules convert TE assignment membership to a "
            "WR chain. Compare Ace formation play-link packed values "
            f"({FORMATION_PLAY_LINKS} links/formation) and skill-slot descriptors "
            f"at body+{PLAY_BASE:#x}+play*{PLAY_SIZE:#x}+8+slot*8 against "
            "non-Ace twins of the same play family."
        ),
        next_offline_writer_gate=(
            "On o0308-class fixture, dump Ace vs I-Form (or Shotgun) skill-slot "
            "descriptors for TE-named plays. If only assignment 8-byte fields "
            "or formation-link packed values differ, offline-prove a copy of "
            "the non-broken package rule into the Ace play with independent "
            "verifier. Until then: re_spike only — no one-click fix pack."
        ),
    )


def layout_pins() -> dict[str, int | str]:
    """Public pin table for docs and tests."""

    return dict(G1_G2_LAYOUT)


__all__ = [
    "G1_G2_LAYOUT",
    "O0308_ASSET_ID",
    "O0308_PACK_OFFSET",
    "PackageRuleSpikeResult",
    "SlotRoleSnapshot",
    "assignment_body_offset",
    "descriptor_body_offset",
    "layout_pins",
    "spike_g1_dime_ilb",
    "spike_g2_ace_te",
]
