"""Precise RE spike + package-map writer for community G1/G2.

G1 (Dime ILB→OLB) and G2 (Ace TE→WR) package research.

Fixture identity (2K5 stock PLAY book used across clone proofs):
  asset_id: ``nfl2k5.resource.o0308.c0000.k504c4159``
  pack_offset (disc slice): ``106803200`` (see formation_play_writer tests)
  layout constants: :mod:`mod_editor.core.nfl2k5_playbook_inspector`

**2026-08-07 census (real o0308 ATL book):**

* **G1 assignment-only gate FAILED.** Shared Nickel/Dime play indices (18)
  are identical play records — zero assignment XOR. Only-Dime and only-Nickel
  plays have different names (no same-name twin). Link tables differ (16/26).
* **G1 real delta: formation package map** at body
  ``FORMATION_BASE + fi*FORMATION_SIZE + 0x0D`` (11 bytes, always a permutation
  of ``0..10`` on o0308). Nickel ``[4,5,0,2,3,1,7,8,9,6,10]`` vs Dime
  ``[5,0,2,3,1,7,8,9,4,6,10]`` — role id 4 moves from slot-index 0 → 8.
* **G2 package-map gate FAILED for Ace-vs-offense.** All offense formations
  including Ace share the same map ``[0,8,6,9,7,10,1,4,3,5,2]``. G2 remains
  play-link / assignment / save-surface research.

Offline writer shipped here: **formation package-map only** (11 bytes),
fail-closed (must be a permutation of 0..10), independent full-resource
byte-diff verifier. Runtime claim for G1 fix remains **unproved** — do not
label as a community one-click fix pack.

APF surface (parallel, not 2K5 o0308):
  MASTER PLAY outer inventory (586 plays × 11 slots) — assignment-route
  writer already offline-proved for exact descriptor copy; package-rule
  bits remain the gap for APF G1/G2 fix packs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable, Sequence

from .errors import ValidationError
from .nfl2k5_playbook_inspector import (
    ASSIGNMENT_COUNT,
    BODY_SIZE,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_CAPACITY,
    FORMATION_PLAY_LINKS,
    FORMATION_SIZE,
    NODE_BASE,
    NODE_SIZE,
    PLAY_BASE,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    PlaybookAssignment,
    PlaybookFormation,
    PlaybookPlay,
    Nfl2k5Playbook,
    parse_playbook_resource,
)

# Disc fixture used by clone offline proofs (no retail bytes embedded here).
O0308_ASSET_ID = "nfl2k5.resource.o0308.c0000.k504c4159"
O0308_PACK_OFFSET = 106_803_200

# 11-byte package role map inside each formation record (o0308 census).
PACKAGE_MAP_OFFSET_IN_FORMATION = 0x0D
PACKAGE_MAP_SIZE = 11

# Layout offsets relative to PLAY resource body (after 0x20 resource header).
# Verified against nfl2k5_playbook_inspector constants + PLAY_* product docs.
G1_G2_LAYOUT: dict[str, int | str] = {
    "resource_header_size": RESOURCE_HEADER_SIZE,
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
    "package_map_offset_in_formation": PACKAGE_MAP_OFFSET_IN_FORMATION,
    "package_map_size": PACKAGE_MAP_SIZE,
    "o0308_asset_id": O0308_ASSET_ID,
    "o0308_pack_offset": O0308_PACK_OFFSET,
    # Absolute body offset of play N assignment slot S:
    #   PLAY_BASE + N*PLAY_SIZE + 8 + S*8
    "assignment_offset_formula": "PLAY_BASE + play_index*PLAY_SIZE + 8 + slot*8",
    # Absolute body offset of formation package map:
    #   FORMATION_BASE + fi*FORMATION_SIZE + 0x0D
    "package_map_offset_formula": (
        "FORMATION_BASE + formation_index*FORMATION_SIZE + "
        f"{PACKAGE_MAP_OFFSET_IN_FORMATION:#x}"
    ),
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

    Reports assignment slot snapshots (historical focus) plus the package-map
    writer path discovered on o0308: formation ``+0x0D`` 11-byte role map.
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
        status="re_spike",  # runtime G1 fix unproved; package-map writer separate
        fixture_asset_id=O0308_ASSET_ID,
        fixture_pack_offset=O0308_PACK_OFFSET,
        layout=dict(G1_G2_LAYOUT),
        matching_formations=formation_names,
        matching_plays=tuple(p.name for p in plays[:12]),
        slot_snapshots=tuple(snapshots),
        hypothesis=(
            "Dime package remaps roster role membership via the formation "
            f"package map at body FORMATION_BASE+fi*{FORMATION_SIZE:#x}"
            f"+{PACKAGE_MAP_OFFSET_IN_FORMATION:#x} (11-byte permutation of 0..10). "
            "o0308 census: Nickel map [4,5,0,2,3,1,7,8,9,6,10] vs Dime "
            "[5,0,2,3,1,7,8,9,4,6,10] — role 4 moves slot-index 0→8. "
            "Assignment-only gate failed (shared plays byte-identical). "
            f"Also compare play-link aux at body+{FORMATION_AUX_BASE:#x}."
        ),
        next_offline_writer_gate=(
            "Package-map offline writer is shipped "
            "(build_formation_package_map_patch + verify). Runtime G1 fix still "
            "needs emulator proof that remapping Dime role 4 toward Nickel-like "
            "placement restores ILB field time. No community one-click fix pack "
            "until runtime-proved. Assignment 8-byte path is closed as not the "
            "primary delta."
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
            "WR chain. o0308 census: Ace shares the same formation package map "
            "as all other offense formations "
            f"([0,8,6,9,7,10,1,4,3,5,2] at +{PACKAGE_MAP_OFFSET_IN_FORMATION:#x}) "
            "— G2 is not package-map. Compare Ace formation play-link packed "
            f"values ({FORMATION_PLAY_LINKS} links) and skill-slot descriptors "
            f"at body+{PLAY_BASE:#x}+play*{PLAY_SIZE:#x}+8+slot*8 against "
            "non-Ace twins; also Save Assignments / director surfaces."
        ),
        next_offline_writer_gate=(
            "Package-map path does not differentiate Ace. Next: Ace vs Quads "
            "link-table + skill-slot assignment XOR on o0308; APF MASTER "
            "assignment census for TE-named plays. Until a pure offline delta "
            "is isolated: re_spike only — no one-click fix pack."
        ),
    )


def layout_pins() -> dict[str, int | str]:
    """Public pin table for docs and tests."""

    return dict(G1_G2_LAYOUT)


def formation_package_map_body_offset(formation_index: int) -> int:
    """Body-relative offset of the 11-byte package role map for one formation."""

    if not 0 <= formation_index < FORMATION_CAPACITY:
        raise ValidationError(
            f"formation_index must be 0..{FORMATION_CAPACITY - 1}; "
            f"got {formation_index}."
        )
    return (
        FORMATION_BASE
        + formation_index * FORMATION_SIZE
        + PACKAGE_MAP_OFFSET_IN_FORMATION
    )


def _validate_package_map(package_map: Sequence[int]) -> bytes:
    if len(package_map) != PACKAGE_MAP_SIZE:
        raise ValidationError(
            f"Package map must be {PACKAGE_MAP_SIZE} role ids; "
            f"got {len(package_map)}."
        )
    values = [int(v) for v in package_map]
    for v in values:
        if not 0 <= v <= 10:
            raise ValidationError(
                f"Package map role ids must be 0..10; got {v}."
            )
    if sorted(values) != list(range(PACKAGE_MAP_SIZE)):
        raise ValidationError(
            "Package map must be a permutation of 0..10 "
            f"(got {values})."
        )
    return bytes(values)


def read_formation_package_map(
    raw_resource: bytes, formation_index: int
) -> tuple[int, ...]:
    """Read the 11-byte package map from a full PLAY resource (header+body)."""

    _require_play_resource(raw_resource)
    body = raw_resource[RESOURCE_HEADER_SIZE:]
    off = formation_package_map_body_offset(formation_index)
    chunk = body[off : off + PACKAGE_MAP_SIZE]
    if len(chunk) != PACKAGE_MAP_SIZE:
        raise ValidationError("Package map lies outside the PLAY body.")
    return tuple(chunk)


def read_all_formation_package_maps(
    raw_resource: bytes, *, formation_count: int | None = None
) -> dict[int, tuple[int, ...]]:
    """Read package maps for formations 0..count-1 (default: parsed count)."""

    _require_play_resource(raw_resource)
    book = parse_playbook_resource(raw_resource)
    count = formation_count if formation_count is not None else len(book.formations)
    return {
        i: read_formation_package_map(raw_resource, i) for i in range(count)
    }


@dataclass(frozen=True, slots=True)
class G1DimeNickelCensus:
    """o0308-class census result for the G1 assignment-only gate."""

    dime_formation_index: int
    nickel_formation_index: int
    dime_package_map: tuple[int, ...]
    nickel_package_map: tuple[int, ...]
    package_map_differs: bool
    role_slot_deltas: tuple[tuple[int, int, int], ...]  # role, nickel_slot, dime_slot
    shared_play_indices: tuple[int, ...]
    only_dime_play_indices: tuple[int, ...]
    only_nickel_play_indices: tuple[int, ...]
    shared_plays_assignment_identical: bool
    link_table_diff_count: int
    assignment_only_gate: str  # "failed" | "passed"
    primary_offline_delta: str
    notes: str


def census_g1_dime_vs_nickel(raw_resource: bytes) -> G1DimeNickelCensus:
    """Compare Dime vs Nickel on a real PLAY resource (header+body).

    Proves whether the assignment-only offline gate holds and records the
    package-map delta that is the primary offline surface for G1.
    """

    _require_play_resource(raw_resource)
    body = raw_resource[RESOURCE_HEADER_SIZE:]
    book = parse_playbook_resource(raw_resource)

    dime_i = next(
        (f.index for f in book.formations if _DIME_RE.search(f.name or "")),
        None,
    )
    nickel_i = next(
        (f.index for f in book.formations if re.search(r"\bnickel\b", f.name or "", re.I)),
        None,
    )
    if dime_i is None or nickel_i is None:
        raise ValidationError(
            "Census requires both Dime and Nickel formations in the PLAY book."
        )

    dime_map = read_formation_package_map(raw_resource, dime_i)
    nickel_map = read_formation_package_map(raw_resource, nickel_i)

    role_deltas: list[tuple[int, int, int]] = []
    for role in range(PACKAGE_MAP_SIZE):
        ns = nickel_map.index(role)
        ds = dime_map.index(role)
        if ns != ds:
            role_deltas.append((role, ns, ds))

    n_links = book.formations[nickel_i].play_links
    d_links = book.formations[dime_i].play_links
    n_plays = {link.play_index for link in n_links}
    d_plays = {link.play_index for link in d_links}
    shared = tuple(sorted(n_plays & d_plays))
    only_d = tuple(sorted(d_plays - n_plays))
    only_n = tuple(sorted(n_plays - d_plays))

    # Shared play indices refer to the same PLAY records → byte-identical.
    # Cross-check: for each shared index, play record equals itself (tautology
    # that documents "no dual-copy of the same play under two indices").
    assign_identical = all(
        body[PLAY_BASE + pi * PLAY_SIZE : PLAY_BASE + (pi + 1) * PLAY_SIZE]
        == body[PLAY_BASE + pi * PLAY_SIZE : PLAY_BASE + (pi + 1) * PLAY_SIZE]
        for pi in shared
    )

    # Link-row diffs (pairwise up to min length)
    link_diffs = 0
    for a, b in zip(n_links, d_links):
        if (
            a.play_index != b.play_index
            or a.group != b.group
            or a.packed_value != b.packed_value
        ):
            link_diffs += 1
    link_diffs += abs(len(n_links) - len(d_links))

    if dime_map != nickel_map:
        gate = "failed"
        primary = (
            f"formation package map @ +{PACKAGE_MAP_OFFSET_IN_FORMATION:#x} "
            f"(Dime {list(dime_map)} vs Nickel {list(nickel_map)})"
        )
    else:
        gate = "unknown"
        primary = "unknown — package maps match; recheck link/assignment tables"

    return G1DimeNickelCensus(
        dime_formation_index=dime_i,
        nickel_formation_index=nickel_i,
        dime_package_map=dime_map,
        nickel_package_map=nickel_map,
        package_map_differs=dime_map != nickel_map,
        role_slot_deltas=tuple(role_deltas),
        shared_play_indices=shared,
        only_dime_play_indices=only_d,
        only_nickel_play_indices=only_n,
        shared_plays_assignment_identical=assign_identical,
        link_table_diff_count=link_diffs,
        assignment_only_gate=gate,
        primary_offline_delta=primary,
        notes=(
            "Shared play indices are the same PLAY records (byte-identical). "
            "G1 offline surface is the 11-byte formation package map, not "
            "per-play assignment 8-byte fields. Runtime effect unproved."
        ),
    )


@dataclass(frozen=True, slots=True)
class PackageMapPatchResult:
    """Result of an offline formation package-map patch."""

    raw_resource: bytes
    formation_index: int
    body_offset: int
    resource_offset: int  # body_offset + RESOURCE_HEADER_SIZE
    old_map: tuple[int, ...]
    new_map: tuple[int, ...]
    changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str  # offline_writer_proved for bytes only


def build_formation_package_map_patch(
    raw_resource: bytes,
    formation_index: int,
    new_map: Sequence[int],
) -> PackageMapPatchResult:
    """Patch one formation's 11-byte package map (fail-closed).

    Touches **only** those 11 bytes. Validates new_map is a permutation of
    0..10. Independent verifier: :func:`verify_formation_package_map_patch`.

    Capability: offline-writer-proved for the map bytes. **Not** runtime-proved
    as a G1 gameplay fix.
    """

    _require_play_resource(raw_resource)
    new_bytes = _validate_package_map(new_map)
    old = read_formation_package_map(raw_resource, formation_index)
    body_off = formation_package_map_body_offset(formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off

    out = bytearray(raw_resource)
    out[res_off : res_off + PACKAGE_MAP_SIZE] = new_bytes
    result = bytes(out)

    # Must still parse as a valid PLAY resource.
    parse_playbook_resource(result)

    changed = sum(
        1 for a, b in zip(raw_resource, result, strict=True) if a != b
    )
    if changed != sum(1 for a, b in zip(old, new_bytes) if a != b):
        # Defensive: only the map region may change.
        outside = [
            i
            for i in range(len(raw_resource))
            if raw_resource[i] != result[i]
            and not (res_off <= i < res_off + PACKAGE_MAP_SIZE)
        ]
        if outside:
            raise ValidationError(
                f"Package-map patch leaked outside map region at offsets {outside[:8]}."
            )

    return PackageMapPatchResult(
        raw_resource=result,
        formation_index=formation_index,
        body_offset=body_off,
        resource_offset=res_off,
        old_map=old,
        new_map=tuple(new_bytes),
        changed_byte_count=changed,
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(result).hexdigest(),
        status="offline_writer_proved",
    )


def verify_formation_package_map_patch(
    source: bytes,
    patched: bytes,
    formation_index: int,
    expected_new_map: Sequence[int],
) -> None:
    """Independent byte-diff verifier for a package-map patch.

    Raises :class:`ValidationError` on any failure.
    """

    _require_play_resource(source)
    _require_play_resource(patched)
    expected = _validate_package_map(expected_new_map)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched resource length {len(patched)} != source {len(source)}."
        )

    body_off = formation_package_map_body_offset(formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off
    actual = patched[res_off : res_off + PACKAGE_MAP_SIZE]
    if actual != expected:
        raise ValidationError(
            f"Patched map {list(actual)} != expected {list(expected)}."
        )

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if res_off <= i < res_off + PACKAGE_MAP_SIZE:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside package map "
                f"(source 0x{a:02x} → 0x{b:02x})."
            )

    # Reparse both
    parse_playbook_resource(source)
    parse_playbook_resource(patched)
    got = read_formation_package_map(patched, formation_index)
    if got != tuple(expected):
        raise ValidationError("Re-read package map does not match expected.")


def _require_play_resource(raw: bytes) -> None:
    if len(raw) != RESOURCE_HEADER_SIZE + BODY_SIZE:
        raise ValidationError(
            f"PLAY resource is {len(raw):,} bytes; "
            f"{RESOURCE_HEADER_SIZE + BODY_SIZE:,} were expected."
        )
    if raw[:4] != b"PLAY":
        raise ValidationError("Resource does not start with PLAY magic.")


def formation_link_table_body_offset(formation_index: int) -> int:
    """Body offset of the 0x50 formation play-link (aux) table."""

    if not 0 <= formation_index < FORMATION_CAPACITY:
        raise ValidationError(
            f"formation_index must be 0..{FORMATION_CAPACITY - 1}; "
            f"got {formation_index}."
        )
    return FORMATION_AUX_BASE + formation_index * FORMATION_AUX_SIZE


@dataclass(frozen=True, slots=True)
class LinkTablePatchResult:
    """Copy of one formation's play-link aux table onto another (G2 menu)."""

    raw_resource: bytes
    target_formation_index: int
    donor_formation_index: int
    body_offset: int
    resource_offset: int
    changed_byte_count: int
    target_link_count_before: int
    target_link_count_after: int
    donor_link_count: int
    source_sha256: str
    result_sha256: str
    status: str


def build_formation_link_table_copy_patch(
    raw_resource: bytes,
    target_formation_index: int,
    donor_formation_index: int,
) -> LinkTablePatchResult:
    """Copy donor formation play-link table (aux 0x50) onto target.

    Fail-closed offline writer for **menu composition** (G2 class). Does not
    change package maps or play assignment records. Independent verifier:
    :func:`verify_formation_link_table_copy_patch`.

    Capability: offline-writer-proved for the 80 aux bytes. **Not** a runtime
    TE→WR package-rule fix.
    """

    _require_play_resource(raw_resource)
    if target_formation_index == donor_formation_index:
        raise ValidationError("Donor and target formation indices must differ.")
    book = parse_playbook_resource(raw_resource)
    if not 0 <= target_formation_index < len(book.formations):
        raise ValidationError(
            f"Target formation {target_formation_index} is outside the book."
        )
    if not 0 <= donor_formation_index < len(book.formations):
        raise ValidationError(
            f"Donor formation {donor_formation_index} is outside the book."
        )

    body_off = formation_link_table_body_offset(target_formation_index)
    donor_off = formation_link_table_body_offset(donor_formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off
    donor_res = RESOURCE_HEADER_SIZE + donor_off
    donor_bytes = raw_resource[donor_res : donor_res + FORMATION_AUX_SIZE]
    if len(donor_bytes) != FORMATION_AUX_SIZE:
        raise ValidationError("Donor link table is truncated.")

    out = bytearray(raw_resource)
    out[res_off : res_off + FORMATION_AUX_SIZE] = donor_bytes
    result = bytes(out)
    patched_book = parse_playbook_resource(result)

    changed = sum(
        1 for a, b in zip(raw_resource, result, strict=True) if a != b
    )
    return LinkTablePatchResult(
        raw_resource=result,
        target_formation_index=target_formation_index,
        donor_formation_index=donor_formation_index,
        body_offset=body_off,
        resource_offset=res_off,
        changed_byte_count=changed,
        target_link_count_before=len(book.formations[target_formation_index].play_links),
        target_link_count_after=len(
            patched_book.formations[target_formation_index].play_links
        ),
        donor_link_count=len(book.formations[donor_formation_index].play_links),
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(result).hexdigest(),
        status="offline_writer_proved",
    )


def verify_formation_link_table_copy_patch(
    source: bytes,
    patched: bytes,
    target_formation_index: int,
    donor_formation_index: int,
) -> None:
    """Independent byte-diff verifier for a formation link-table copy."""

    _require_play_resource(source)
    _require_play_resource(patched)
    if len(source) != len(patched):
        raise ValidationError("Patched resource length differs from source.")

    body_off = formation_link_table_body_offset(target_formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off
    donor_off = formation_link_table_body_offset(donor_formation_index)
    donor_res = RESOURCE_HEADER_SIZE + donor_off
    expected = source[donor_res : donor_res + FORMATION_AUX_SIZE]
    actual = patched[res_off : res_off + FORMATION_AUX_SIZE]
    if actual != expected:
        raise ValidationError("Patched link table does not match donor table.")

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if res_off <= i < res_off + FORMATION_AUX_SIZE:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside formation link table."
            )

    parse_playbook_resource(source)
    parse_playbook_resource(patched)


_NICKEL_RE = re.compile(r"\bnickel\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class G1DimeFromNickelTarget:
    """One Dime-named formation that received the Nickel package map."""

    formation_index: int
    formation_name: str
    old_map: tuple[int, ...]
    new_map: tuple[int, ...]
    resource_offset: int
    changed_byte_count: int


@dataclass(frozen=True, slots=True)
class G1DimeFromNickelPackResult:
    """Multi-formation offline G1 package-map pack (bytes only; runtime unproved)."""

    raw_resource: bytes
    nickel_formation_index: int
    nickel_formation_name: str
    nickel_package_map: tuple[int, ...]
    targets: tuple[G1DimeFromNickelTarget, ...]
    total_changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str
    honesty: str
    manifest: dict[str, object]


def build_g1_dime_from_nickel_package_map_pack(
    raw_resource: bytes,
) -> G1DimeFromNickelPackResult:
    """Copy the first Nickel package map onto **every** Dime-named formation.

    Fail-closed offline writer for the G1 package-map surface across the whole
    PLAY book (not just one formation pair). Touches only 11-byte package-map
    regions. Independent verifier:
    :func:`verify_g1_dime_from_nickel_package_map_pack`.

    Capability: **offline_writer_proved** for map bytes. **Not** a runtime G1
    fix pack — do not ship as community one-click runtime proof.
    """

    _require_play_resource(raw_resource)
    book = parse_playbook_resource(raw_resource)

    nickel = next(
        (f for f in book.formations if _NICKEL_RE.search(f.name or "")),
        None,
    )
    if nickel is None:
        raise ValidationError(
            "G1 multi-Dime pack needs a formation whose name contains Nickel."
        )
    dime_forms = tuple(
        f for f in book.formations if _DIME_RE.search(f.name or "")
    )
    if not dime_forms:
        raise ValidationError(
            "G1 multi-Dime pack needs at least one formation whose name "
            "contains Dime."
        )

    nickel_map = read_formation_package_map(raw_resource, nickel.index)
    working = raw_resource
    targets: list[G1DimeFromNickelTarget] = []
    allowed_regions: list[tuple[int, int]] = []

    for form in dime_forms:
        old = read_formation_package_map(working, form.index)
        if old == nickel_map:
            # Still record identity (no-op) so the manifest lists every Dime.
            res_off = (
                RESOURCE_HEADER_SIZE
                + formation_package_map_body_offset(form.index)
            )
            targets.append(
                G1DimeFromNickelTarget(
                    formation_index=form.index,
                    formation_name=str(form.name or ""),
                    old_map=old,
                    new_map=nickel_map,
                    resource_offset=res_off,
                    changed_byte_count=0,
                )
            )
            continue
        patch = build_formation_package_map_patch(
            working, form.index, nickel_map
        )
        verify_formation_package_map_patch(
            working, patch.raw_resource, form.index, nickel_map
        )
        working = patch.raw_resource
        targets.append(
            G1DimeFromNickelTarget(
                formation_index=form.index,
                formation_name=str(form.name or ""),
                old_map=old,
                new_map=patch.new_map,
                resource_offset=patch.resource_offset,
                changed_byte_count=patch.changed_byte_count,
            )
        )
        allowed_regions.append(
            (patch.resource_offset, patch.resource_offset + PACKAGE_MAP_SIZE)
        )

    # Independent multi-region verify against original source.
    verify_g1_dime_from_nickel_package_map_pack(
        raw_resource,
        working,
        nickel_index=nickel.index,
        dime_indices=tuple(t.formation_index for t in targets),
        expected_map=nickel_map,
    )

    total_changed = sum(t.changed_byte_count for t in targets)
    honesty = (
        "offline_writer_proved for formation package-map bytes only. "
        "Runtime G1 (Dime ILB→OLB) is unproved. Not a project edit. "
        "Source ISO is never mutated. Private PLAY export only."
    )
    manifest: dict[str, object] = {
        "kind": "g1_dime_from_nickel_package_map_pack",
        "capability": "offline_writer_proved",
        "runtime_proved": False,
        "bug_id": "G1",
        "nickel_formation_index": nickel.index,
        "nickel_formation_name": str(nickel.name or ""),
        "nickel_package_map": list(nickel_map),
        "dime_targets": [
            {
                "formation_index": t.formation_index,
                "formation_name": t.formation_name,
                "old_map": list(t.old_map),
                "new_map": list(t.new_map),
                "resource_offset": t.resource_offset,
                "changed_byte_count": t.changed_byte_count,
            }
            for t in targets
        ],
        "total_changed_byte_count": total_changed,
        "source_sha256": hashlib.sha256(raw_resource).hexdigest(),
        "result_sha256": hashlib.sha256(working).hexdigest(),
        "honesty": honesty,
        "layout": {
            "package_map_offset_in_formation": PACKAGE_MAP_OFFSET_IN_FORMATION,
            "package_map_size": PACKAGE_MAP_SIZE,
            "package_map_offset_formula": G1_G2_LAYOUT[
                "package_map_offset_formula"
            ],
        },
    }
    return G1DimeFromNickelPackResult(
        raw_resource=working,
        nickel_formation_index=nickel.index,
        nickel_formation_name=str(nickel.name or ""),
        nickel_package_map=nickel_map,
        targets=tuple(targets),
        total_changed_byte_count=total_changed,
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(working).hexdigest(),
        status="offline_writer_proved",
        honesty=honesty,
        manifest=manifest,
    )


def verify_g1_dime_from_nickel_package_map_pack(
    source: bytes,
    patched: bytes,
    *,
    nickel_index: int,
    dime_indices: Sequence[int],
    expected_map: Sequence[int],
) -> None:
    """Independent multi-region byte-diff verifier for the G1 multi-Dime pack."""

    _require_play_resource(source)
    _require_play_resource(patched)
    expected = _validate_package_map(expected_map)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched resource length {len(patched)} != source {len(source)}."
        )

    allowed: set[int] = set()
    for fi in dime_indices:
        res_off = RESOURCE_HEADER_SIZE + formation_package_map_body_offset(
            int(fi)
        )
        for i in range(res_off, res_off + PACKAGE_MAP_SIZE):
            allowed.add(i)
        actual = patched[res_off : res_off + PACKAGE_MAP_SIZE]
        if actual != expected:
            raise ValidationError(
                f"Dime formation {fi} map {list(actual)} != expected "
                f"Nickel map {list(expected)}."
            )

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if i in allowed:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside Dime package-map regions "
                f"(source 0x{a:02x} → 0x{b:02x})."
            )

    # Nickel map itself must be unchanged (donor is read-only in the pack).
    nickel_read = read_formation_package_map(patched, nickel_index)
    if nickel_read != tuple(expected):
        raise ValidationError(
            "Nickel donor package map was mutated; pack must leave Nickel intact."
        )

    parse_playbook_resource(source)
    parse_playbook_resource(patched)


_QUADS_RE = re.compile(r"\bquads\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class G2AceFromQuadsTarget:
    """One Ace-named formation that received the Quads play-link table."""

    formation_index: int
    formation_name: str
    link_count_before: int
    link_count_after: int
    resource_offset: int
    changed_byte_count: int


@dataclass(frozen=True, slots=True)
class G2AceFromQuadsPackResult:
    """Multi-formation offline G2 link-table pack (menu bytes; runtime unproved)."""

    raw_resource: bytes
    quads_formation_index: int
    quads_formation_name: str
    quads_link_count: int
    targets: tuple[G2AceFromQuadsTarget, ...]
    total_changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str
    honesty: str
    manifest: dict[str, object]


def build_g2_ace_from_quads_link_table_pack(
    raw_resource: bytes,
) -> G2AceFromQuadsPackResult:
    """Copy the first Quads play-link table onto **every** Ace-named formation.

    Fail-closed offline writer for the G2 **menu composition** surface across
    the whole PLAY book. Touches only formation aux (0x50) play-link tables.
    Does **not** change package maps or play assignment records. Independent
    verifier: :func:`verify_g2_ace_from_quads_link_table_pack`.

    Capability: **offline_writer_proved** for menu link-table bytes. **Not** a
    runtime G2 (TE→WR) fix pack — do not ship as community one-click runtime
    proof.
    """

    _require_play_resource(raw_resource)
    book = parse_playbook_resource(raw_resource)

    quads = next(
        (f for f in book.formations if _QUADS_RE.search(f.name or "")),
        None,
    )
    if quads is None:
        raise ValidationError(
            "G2 multi-Ace pack needs a formation whose name contains Quads."
        )
    ace_forms = tuple(
        f for f in book.formations if _ACE_RE.search(f.name or "")
    )
    if not ace_forms:
        raise ValidationError(
            "G2 multi-Ace pack needs at least one formation whose name "
            "contains Ace."
        )
    if any(f.index == quads.index for f in ace_forms):
        raise ValidationError(
            "G2 multi-Ace pack refuses a formation named both Ace and Quads."
        )

    working = raw_resource
    targets: list[G2AceFromQuadsTarget] = []
    for form in ace_forms:
        before_count = len(form.play_links)
        patch = build_formation_link_table_copy_patch(
            working, form.index, quads.index
        )
        verify_formation_link_table_copy_patch(
            working, patch.raw_resource, form.index, quads.index
        )
        # Package map of Ace must stay identity with pre-pack map.
        old_map = read_formation_package_map(working, form.index)
        new_map = read_formation_package_map(patch.raw_resource, form.index)
        if old_map != new_map:
            raise ValidationError(
                f"G2 pack mutated package map on Ace formation {form.index}."
            )
        working = patch.raw_resource
        targets.append(
            G2AceFromQuadsTarget(
                formation_index=form.index,
                formation_name=str(form.name or ""),
                link_count_before=before_count,
                link_count_after=patch.target_link_count_after,
                resource_offset=patch.resource_offset,
                changed_byte_count=patch.changed_byte_count,
            )
        )

    verify_g2_ace_from_quads_link_table_pack(
        raw_resource,
        working,
        quads_index=quads.index,
        ace_indices=tuple(t.formation_index for t in targets),
    )

    total_changed = sum(t.changed_byte_count for t in targets)
    honesty = (
        "offline_writer_proved for formation play-link (menu) table bytes only. "
        "Runtime G2 (Ace TE→WR) is unproved. Package maps and play assignments "
        "are untouched. Not a project edit. Source ISO is never mutated. "
        "Private PLAY export only."
    )
    manifest: dict[str, object] = {
        "kind": "g2_ace_from_quads_link_table_pack",
        "capability": "offline_writer_proved",
        "runtime_proved": False,
        "bug_id": "G2",
        "quads_formation_index": quads.index,
        "quads_formation_name": str(quads.name or ""),
        "quads_link_count": len(quads.play_links),
        "ace_targets": [
            {
                "formation_index": t.formation_index,
                "formation_name": t.formation_name,
                "link_count_before": t.link_count_before,
                "link_count_after": t.link_count_after,
                "resource_offset": t.resource_offset,
                "changed_byte_count": t.changed_byte_count,
            }
            for t in targets
        ],
        "total_changed_byte_count": total_changed,
        "source_sha256": hashlib.sha256(raw_resource).hexdigest(),
        "result_sha256": hashlib.sha256(working).hexdigest(),
        "honesty": honesty,
        "layout": {
            "formation_aux_base": FORMATION_AUX_BASE,
            "formation_aux_size": FORMATION_AUX_SIZE,
            "surface": "play_link_menu_table",
        },
    }
    return G2AceFromQuadsPackResult(
        raw_resource=working,
        quads_formation_index=quads.index,
        quads_formation_name=str(quads.name or ""),
        quads_link_count=len(quads.play_links),
        targets=tuple(targets),
        total_changed_byte_count=total_changed,
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(working).hexdigest(),
        status="offline_writer_proved",
        honesty=honesty,
        manifest=manifest,
    )


def verify_g2_ace_from_quads_link_table_pack(
    source: bytes,
    patched: bytes,
    *,
    quads_index: int,
    ace_indices: Sequence[int],
) -> None:
    """Independent multi-region byte-diff verifier for the G2 multi-Ace pack."""

    _require_play_resource(source)
    _require_play_resource(patched)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched resource length {len(patched)} != source {len(source)}."
        )

    donor_res = RESOURCE_HEADER_SIZE + formation_link_table_body_offset(
        int(quads_index)
    )
    expected_table = source[donor_res : donor_res + FORMATION_AUX_SIZE]
    if len(expected_table) != FORMATION_AUX_SIZE:
        raise ValidationError("Quads donor link table is truncated.")

    allowed: set[int] = set()
    for fi in ace_indices:
        res_off = RESOURCE_HEADER_SIZE + formation_link_table_body_offset(
            int(fi)
        )
        for i in range(res_off, res_off + FORMATION_AUX_SIZE):
            allowed.add(i)
        actual = patched[res_off : res_off + FORMATION_AUX_SIZE]
        if actual != expected_table:
            raise ValidationError(
                f"Ace formation {fi} link table does not match Quads donor."
            )

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if i in allowed:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside Ace link-table regions."
            )

    # Quads donor table identity preserved.
    donor_after = patched[donor_res : donor_res + FORMATION_AUX_SIZE]
    if donor_after != expected_table:
        raise ValidationError(
            "Quads donor link table was mutated; pack must leave Quads intact."
        )

    parse_playbook_resource(source)
    parse_playbook_resource(patched)


__all__ = [
    "G1_G2_LAYOUT",
    "G1DimeFromNickelPackResult",
    "G1DimeFromNickelTarget",
    "G1DimeNickelCensus",
    "G2AceFromQuadsPackResult",
    "G2AceFromQuadsTarget",
    "LinkTablePatchResult",
    "O0308_ASSET_ID",
    "O0308_PACK_OFFSET",
    "PACKAGE_MAP_OFFSET_IN_FORMATION",
    "PACKAGE_MAP_SIZE",
    "PackageMapPatchResult",
    "PackageRuleSpikeResult",
    "SlotRoleSnapshot",
    "assignment_body_offset",
    "build_formation_link_table_copy_patch",
    "build_formation_package_map_patch",
    "build_g1_dime_from_nickel_package_map_pack",
    "build_g2_ace_from_quads_link_table_pack",
    "census_g1_dime_vs_nickel",
    "descriptor_body_offset",
    "formation_link_table_body_offset",
    "formation_package_map_body_offset",
    "layout_pins",
    "read_all_formation_package_maps",
    "read_formation_package_map",
    "spike_g1_dime_ilb",
    "spike_g2_ace_te",
    "verify_formation_link_table_copy_patch",
    "verify_formation_package_map_patch",
    "verify_g1_dime_from_nickel_package_map_pack",
    "verify_g2_ace_from_quads_link_table_pack",
]
