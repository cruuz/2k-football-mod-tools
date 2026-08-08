"""Bounded APF ``Roster.ROS`` packed-player and membership editor.

The Xbox 360 and PS3 APFe text exports supplied by a modder were paired with
their byte-identical-format raw roster payloads.  Together with the existing
XEX-backed on-disc player schema, they establish that a raw save keeps the
same 0x14C-byte player records behind a four-byte save prefix.  This module
exposes only fields whose complete storage mask is known.  It also supports a
membership *swap*: exchanging two existing counted roster pointers preserves
all team counts, the complete player-pointer multiset, and global uniqueness.

The selected source is never changed.  A CON/LIVE/PIRS source is verified and
extracted through :mod:`apf_stfs_roster_extract`; output is an independently
verified raw ``Roster.ROS`` handoff because Mod Studio does not possess the
owner's signing keyvault (or Microsoft's LIVE/PIRS signing keys).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
from typing import Iterable, Mapping

from mod_editor.core import platform_compat

from .backend import ensure_tools_importable
from .player_positions import load_player_position_schema
from .player_ratings import ENUMERATED_DOMAIN, load_player_rating_schema


ensure_tools_importable()
import apf_roster  # type: ignore  # noqa: E402
import apf_save_custom_team_appearance as save_layout  # type: ignore  # noqa: E402
import apf_stfs_roster_extract as stfs_reader  # type: ignore  # noqa: E402


SCHEMA = "apf2k8_save_packed_players/v1"
VERIFY_SCHEMA = "apf2k8_save_packed_players_verify/v1"
PLAYER_COUNT = 2_254
PLAYER_STRIDE = 0x14C
TEAM_COUNT = 40
TEAM_STRIDE = 0x180
TEAM_MEMBER_CAPACITY = 42
TEAM_MEMBER_COUNT_OFFSET = 0xC5
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_PLAYER_TEXT_UNITS = 2_048


class SaveRosterPlayerError(ValueError):
    """The source or requested edit left the proved raw-save contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveRosterPlayerError(message)


@dataclass(frozen=True)
class BitPart:
    """One contiguous portion of a logical value in one record byte."""

    byte_offset: int
    storage_shift: int
    width: int
    value_shift: int = 0

    @property
    def value_mask(self) -> int:
        return (1 << self.width) - 1

    @property
    def storage_mask(self) -> int:
        return self.value_mask << self.storage_shift


@dataclass(frozen=True)
class PackedField:
    field_id: str
    label: str
    category: str
    parts: tuple[BitPart, ...]
    minimum: int
    maximum: int
    choices: Mapping[int, str] | None = None
    authorable_values: frozenset[int] | None = None
    mirrored_parts: bool = False

    def decode(self, record: bytes | bytearray | memoryview) -> int:
        view = memoryview(record)
        _require(len(view) == PLAYER_STRIDE, "player record size changed")
        values: list[int] = []
        for part in self.parts:
            values.append((
                (int(view[part.byte_offset]) >> part.storage_shift)
                & part.value_mask
            ) << part.value_shift)
        if self.mirrored_parts:
            _require(
                bool(values) and len(set(values)) == 1,
                f"{self.label} source mirrors disagree",
            )
            return values[0]
        value = 0
        for item in values:
            value |= item
        return value

    def validate(self, value: object) -> int:
        _require(
            type(value) is int and self.minimum <= value <= self.maximum,
            f"{self.label} must be a whole number from {self.minimum} to {self.maximum}",
        )
        integer = int(value)
        if self.authorable_values is not None:
            _require(
                integer in self.authorable_values,
                f"{self.label} must be one of {sorted(self.authorable_values)}",
            )
        return integer

    def encode_into(self, record: bytearray, value: object) -> int:
        integer = self.validate(value)
        for part in self.parts:
            portion = (integer >> part.value_shift) & part.value_mask
            original = record[part.byte_offset]
            record[part.byte_offset] = (
                (original & ~part.storage_mask)
                | (portion << part.storage_shift)
            )
        _require(self.decode(record) == integer, f"{self.label} did not encode exactly")
        return integer


def _part(offset: int, shift: int, width: int, value_shift: int = 0) -> BitPart:
    return BitPart(offset, shift, width, value_shift)


def _field(
    field_id: str,
    label: str,
    category: str,
    offset: int,
    shift: int,
    width: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
    choices: Mapping[int, str] | None = None,
    authorable_values: Iterable[int] | None = None,
) -> PackedField:
    limit = (1 << width) - 1 if maximum is None else maximum
    proved_values = (
        tuple(choices)
        if choices is not None and authorable_values is None
        else authorable_values
    )
    return PackedField(
        field_id,
        label,
        category,
        (_part(offset, shift, width),),
        minimum,
        limit,
        choices,
        None if proved_values is None else frozenset(proved_values),
    )


_ABILITY_COORDINATES = (
    ("fourth_quarter_comeback", 40, 4),
    ("acrobatic_catches", 41, 5),
    ("ankle_breaker", 36, 3),
    ("arms_of_steel", 36, 2),
    ("ball_hawk", 27, 0),
    ("ball_strip", 37, 6),
    ("battering_ram", 36, 1),
    ("big_hit", 37, 5),
    ("branching_tackles", 37, 4),
    ("breakaway_burst", 36, 6),
    ("brick_wall", 38, 1),
    ("bull_rush", 43, 7),
    ("bulldozer", 38, 0),
    ("bullet_time", 35, 0),
    ("bump_buster", 41, 7),
    ("bump_master", 36, 4),
    ("cadence", 44, 4),
    ("closing_speed", 36, 5),
    ("club", 43, 6),
    ("clutch", 36, 7),
    ("coffin_corner", 31, 2),
    ("coverage_bonus", 39, 7),
    ("cutback_ability", 37, 3),
    ("cyclone", 36, 0),
    ("deception", 40, 7),
    ("deep_threat", 26, 7),
    ("durability_bonus", 39, 6),
    ("finesse", 44, 3),
    ("finesse_and_power", 44, 1),
    ("footsteps", 37, 2),
    ("goal_line_dive", 43, 1),
    ("high_helmet_tackle", 23, 1),
    ("hops", 39, 5),
    ("kick_accuracy_bonus", 39, 4),
    ("kick_power_bonus", 39, 3),
    ("laser_arm", 43, 3),
    ("leadership_bonus", 37, 1),
    ("loose_ball_magnet", 27, 1),
    ("magic_feet", 41, 3),
    ("mr_third_down", 41, 4),
    ("pass_rush_bonus", 39, 2),
    ("pass_threat", 40, 5),
    ("play_fake", 40, 6),
    ("pocket_presence", 44, 6),
    ("possession_receiver", 41, 2),
    ("power", 44, 2),
    ("qb_evade", 23, 0),
    ("quick_feet", 39, 1),
    ("quick_release", 44, 5),
    ("reach_tackle", 37, 0),
    ("return_specialist", 31, 1),
    ("rip", 43, 5),
    ("rocket_arm", 43, 2),
    ("route_god", 40, 0),
    ("run_coverage_bonus", 39, 0),
    ("run_reader", 38, 7),
    ("sack_master", 38, 6),
    ("scissor_kick", 43, 0),
    ("scrambler", 40, 1),
    ("secure_ball_bonus", 41, 1),
    ("signal_stealer", 44, 7),
    ("soft_hands", 42, 4),
    ("special_team_demon", 31, 0),
    ("speed_burner", 42, 3),
    ("spin", 43, 4),
    ("stamina_bonus", 42, 2),
    ("stonewall", 38, 5),
    ("stop_on_a_dime", 37, 7),
    ("strength_bonus", 42, 1),
    ("swim", 42, 0),
    ("tough_as_nails", 40, 3),
    ("tough_in_the_middle", 41, 6),
    ("two_way_player", 38, 4),
    ("work_horse", 38, 3),
    ("wrap_up_tackler", 38, 2),
)


_APPEARANCE_FIELDS = (
    _field("jersey_number", "Jersey number", "identity", 35, 1, 7, maximum=99),
    _field("depth_primary", "Primary depth", "depth_chart", 26, 4, 3),
    _field("depth_secondary", "Secondary depth", "depth_chart", 26, 1, 3),
    _field(
        "tier", "Star tier", "tier", 18, 0, 3,
        choices={0: "None", 2: "Gold", 4: "Silver", 6: "Bronze"},
        authorable_values=(0, 2, 4, 6),
    ),
    PackedField(
        "position",
        "Position",
        "identity",
        (_part(52, 0, 8), _part(53, 0, 8)),
        0,
        16,
        {
            row.code: f"{row.abbreviation} — {row.name}"
            for row in load_player_position_schema().positions
        },
        frozenset(range(17)),
        True,
    ),
    _field("player_type", "Player type", "identity", 54, 0, 8),
    _field("years_pro", "Years pro", "identity", 29, 3, 5),
    _field("height_inches", "Height (inches)", "appearance", 217, 0, 8),
    _field("handedness", "Handedness", "identity", 12, 4, 1, choices={0: "Right", 1: "Left"}),
    _field("body", "Body", "appearance", 16, 6, 2, choices={0: "Skinny", 1: "Normal", 2: "Large", 3: "Fat"}),
    _field("muscle", "Muscle", "appearance", 13, 4, 2, maximum=2, choices={0: "Normal", 1: "Ripped", 2: "Flabby"}),
    _field("face_mask", "Facemask", "equipment", 20, 3, 5),
    _field(
        "face_shield",
        "Face shield / visor",
        "equipment",
        20,
        1,
        2,
        choices={0: "None", 1: "Clear", 2: "Dark"},
    ),
    _field("eye_black", "Eye black", "equipment", 12, 3, 1),
    _field("nasal_strip", "Nasal strip", "equipment", 19, 3, 1),
    _field("left_glove", "Left glove", "equipment", 17, 6, 2, choices={0: "None", 1: "Whole", 2: "Palm", 3: "Tape"}),
    _field("right_glove", "Right glove", "equipment", 17, 4, 2, choices={0: "None", 1: "Whole", 2: "Palm", 3: "Tape"}),
    _field("left_wrist", "Left wrist", "equipment", 14, 4, 4),
    _field("right_wrist", "Right wrist", "equipment", 14, 0, 4),
    _field("left_elbow", "Left elbow", "equipment", 15, 4, 4),
    _field("right_elbow", "Right elbow", "equipment", 15, 0, 4),
    _field("sleeve", "Sleeve", "equipment", 13, 2, 2),
    _field("right_shoe", "Right shoe", "equipment", 18, 3, 3),
    _field("neck_roll", "Neck roll", "equipment", 13, 0, 2, choices={0: "None", 1: "Bulge", 2: "Ring", 3: "Board"}),
    _field("turtleneck", "Turtleneck", "equipment", 12, 1, 2, choices={0: "None", 1: "White", 2: "Black", 3: "Team"}),
    _field("left_glove_color", "Left glove colour", "equipment", 16, 3, 3),
    _field("right_glove_color", "Right glove colour", "equipment", 16, 0, 3),
    _field("left_shoe_tape", "Left shoe tape", "equipment", 17, 2, 1),
    _field("right_shoe_tape", "Right shoe tape", "equipment", 17, 1, 1),
)


_SPECIAL_SKILL_FIELDS = (
    _field("throw_motion", "Throw motion", "ability_style", 27, 4, 4),
    _field("qb_hold_ball_style", "QB hold-ball style", "ability_style", 21, 2, 4),
    _field("play_action_motion", "Play-action motion", "ability_style", 27, 2, 2),
    _field("qb_run_style", "QB run style", "ability_style", 19, 4, 1),
    _field("get_low", "Get Low", "ability", 44, 0, 1),
    _field("head_slap", "Head Slap", "ability", 42, 7, 1),
    _field("high_step", "High Step", "ability_style", 42, 4, 2),
)


_COMPOSITE_FIELDS = (
    PackedField("skin", "Skin", "appearance", (_part(12, 0, 1, 2), _part(13, 6, 2)), 0, 5),
    PackedField("face", "Face", "appearance", (_part(20, 0, 1, 2), _part(21, 6, 2)), 0, 7),
    PackedField("left_shoe", "Left shoe", "equipment", (_part(17, 0, 1, 2), _part(18, 6, 2)), 0, 7),
    PackedField("legpads", "Leg pads", "equipment", (_part(21, 0, 1, 1), _part(22, 7, 1)), 0, 2),
    # APFe presents ``(byte23 | (byte22 & 0x1F) << 8) / 16``.  The low
    # nibble of byte 23 is also consumed by packed abilities, so author only
    # whole pounds and preserve that shared nibble exactly.
    PackedField("weight_pounds", "Weight (whole pounds)", "appearance", (_part(23, 4, 4), _part(22, 0, 5, 4)), 0, 0x1FF),
    PackedField("pbp_id", "Play-by-play ID", "identity", (_part(9, 0, 8), _part(8, 0, 8, 8)), 0, 0xFFFF),
    PackedField("photo_id", "Photo ID", "appearance", (_part(11, 0, 8), _part(10, 0, 8, 8)), 0, 0xFFFF),
)


def _rating_fields() -> tuple[PackedField, ...]:
    schema = load_player_rating_schema()
    rows: list[PackedField] = []
    for value in schema.fields:
        authorable = (
            frozenset(value.observed_stock_values)
            if value.value_domain == ENUMERATED_DOMAIN
            else None
        )
        rows.append(
            PackedField(
                f"rating_{value.field_id}",
                f"Base rating: {value.label}",
                "base_rating",
                (_part(value.relative_offset, 0, 8),),
                0,
                99,
                None,
                authorable,
            )
        )
    return tuple(rows)


FIELDS = (
    _APPEARANCE_FIELDS
    + _COMPOSITE_FIELDS
    + _SPECIAL_SKILL_FIELDS
    + tuple(
        _field(
            f"ability_{name}",
            name.replace("_", " ").title(),
            "ability",
            offset,
            shift,
            1,
        )
        for name, offset, shift in _ABILITY_COORDINATES
    )
    + _rating_fields()
)
FIELDS_BY_ID = {field.field_id: field for field in FIELDS}
_require(len(FIELDS_BY_ID) == len(FIELDS), "packed-player field IDs repeat")

# These are the exact relative-pointer fields already consumed by the APF ROST
# parser.  Save authoring keeps every pointer fixed and may only replace text
# inside that field's existing UTF-16BE allocation.
PLAYER_TEXT_FIELDS_BY_ID = {
    field_id: relative_offset
    for relative_offset, field_id in apf_roster.PLAYER_STRING_FIELDS.items()
}
_require(
    len(PLAYER_TEXT_FIELDS_BY_ID) == len(apf_roster.PLAYER_STRING_FIELDS) == 15,
    "player text-field dictionary changed",
)


@dataclass(frozen=True)
class MembershipSlot:
    team_index: int
    roster_slot: int
    player_index: int
    pointer_field_offset: int


@dataclass(frozen=True)
class PlayerTextOwner:
    player_index: int
    field_id: str

    @property
    def owner_id(self) -> str:
        return f"player:{self.player_index}:{self.field_id}"


@dataclass(frozen=True)
class PlayerTextAllocation:
    allocation_id: str
    text: str
    allocation_bytes: int
    maximum_utf16_units: int
    owner_fingerprint: str
    owners: tuple[PlayerTextOwner, ...]
    target_offset: int


@dataclass(frozen=True)
class SaveRosterDocument:
    source: Path
    source_sha256: str
    raw_payload_sha256: str
    file_size: int
    signed_container: bool
    container_kind: str | None
    payload_path: str | None
    player_start: int
    team_start: int
    memberships: tuple[MembershipSlot, ...]
    text_allocations: tuple[PlayerTextAllocation, ...]
    text_owner_map: Mapping[tuple[int, str], int]
    raw_payload: bytes

    def player_record(self, player_index: int) -> bytes:
        _player_index(player_index)
        start = self.player_start + player_index * PLAYER_STRIDE
        return self.raw_payload[start : start + PLAYER_STRIDE]

    def player_values(self, player_index: int) -> Mapping[str, int]:
        record = self.player_record(player_index)
        return {field.field_id: field.decode(record) for field in FIELDS}

    def player_text_allocation(
        self, player_index: int, field_id: str
    ) -> PlayerTextAllocation:
        player = _player_index(player_index)
        _require(field_id in PLAYER_TEXT_FIELDS_BY_ID, f"unknown player text field: {field_id}")
        try:
            index = self.text_owner_map[(player, field_id)]
        except KeyError as exc:
            raise SaveRosterPlayerError(
                f"player {player} has no mapped {field_id} allocation"
            ) from exc
        return self.text_allocations[index]

    def player_text_values(self, player_index: int) -> Mapping[str, str]:
        player = _player_index(player_index)
        return {
            field_id: self.player_text_allocation(player, field_id).text
            for field_id in PLAYER_TEXT_FIELDS_BY_ID
        }


@dataclass(frozen=True)
class PlayerFieldEdit:
    player_index: int
    field_id: str
    value: int


@dataclass(frozen=True)
class MembershipSwap:
    first_team: int
    first_slot: int
    second_team: int
    second_slot: int


@dataclass(frozen=True)
class PlayerTextEdit:
    player_index: int
    field_id: str
    text: str


@dataclass(frozen=True)
class SaveRosterWriteReceipt:
    output: Path
    manifest: Path
    output_sha256: str
    changed_byte_count: int
    field_edit_count: int
    membership_swap_count: int
    text_edit_count: int
    verification_passed: bool
    source_was_signed_container: bool
    external_reinjection_required: bool
    output_is_raw_payload: bool = True
    runtime_in_game_proved: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _player_index(value: object) -> int:
    _require(type(value) is int and 0 <= value < PLAYER_COUNT, "player index must be 0..2253")
    return int(value)


def _raw_payload(source: bytes) -> tuple[bytes, bool, str | None, str | None]:
    _require(isinstance(source, bytes), "save source must be immutable bytes")
    _require(0 < len(source) <= MAX_SOURCE_BYTES, "save source size is outside the bounded range")
    if source[:4] in stfs_reader.STFS_MAGICS:
        try:
            extracted = stfs_reader.extract_roster_payload(source)
        except stfs_reader.StfsRosterError as exc:
            raise SaveRosterPlayerError(str(exc)) from exc
        return extracted.payload, True, extracted.package_kind, extracted.entry.path
    return source, False, None, None


def _relative_pointer(field: int, target: int) -> bytes:
    stored = target + 1 - field
    _require(-(1 << 31) <= stored < (1 << 31), "membership pointer is outside signed 32-bit range")
    return struct.pack(">i", stored)


def _layout(raw: bytes) -> tuple[int, int, tuple[MembershipSlot, ...]]:
    try:
        # This validates all 40 root counts and the independently recovered
        # team/palette/selector/config graph, not merely file length.
        save_layout._table_layout(raw)
        player_count = save_layout._root_count(raw, 0)
        player_start = save_layout._root_target(raw, 0)
        team_count = save_layout._root_count(raw, 4)
        team_start = save_layout._root_target(raw, 4)
    except save_layout.SaveAppearanceError as exc:
        raise SaveRosterPlayerError(str(exc)) from exc
    _require(player_count == PLAYER_COUNT, "save player count changed from 2254")
    _require(team_count == TEAM_COUNT, "save team count changed from 40")
    _require(player_start + PLAYER_COUNT * PLAYER_STRIDE <= team_start, "player and team tables overlap")
    _require(team_start + TEAM_COUNT * TEAM_STRIDE <= len(raw), "team table exceeds raw save")

    memberships: list[MembershipSlot] = []
    seen_players: set[int] = set()
    for team_index in range(TEAM_COUNT):
        team = team_start + team_index * TEAM_STRIDE
        count = raw[team + TEAM_MEMBER_COUNT_OFFSET]
        _require(count <= TEAM_MEMBER_CAPACITY, f"team {team_index} membership count exceeds 42")
        for roster_slot in range(count):
            field = team + roster_slot * 4
            try:
                target = save_layout._relative_target(
                    raw, field, f"team {team_index} roster slot {roster_slot}"
                )
                player_index = save_layout._record_index(
                    target,
                    player_start,
                    PLAYER_COUNT,
                    PLAYER_STRIDE,
                    f"team {team_index} roster slot {roster_slot}",
                )
            except save_layout.SaveAppearanceError as exc:
                raise SaveRosterPlayerError(str(exc)) from exc
            _require(
                player_index not in seen_players,
                f"player {player_index} occurs in more than one counted membership slot",
            )
            seen_players.add(player_index)
            memberships.append(MembershipSlot(team_index, roster_slot, player_index, field))
    return player_start, team_start, tuple(memberships)


def _decode_player_text(raw: bytes, target: int, label: str) -> tuple[str, int]:
    _require(target % 2 == 0, f"{label} is not UTF-16BE aligned")
    _require(0 <= target <= len(raw) - 2, f"{label} target exceeds the raw save")
    end = target
    for _unit in range(MAX_PLAYER_TEXT_UNITS + 1):
        _require(end <= len(raw) - 2, f"{label} has no in-file terminator")
        if raw[end : end + 2] == b"\0\0":
            try:
                return raw[target:end].decode("utf-16-be", errors="strict"), end + 2 - target
            except UnicodeDecodeError as exc:
                raise SaveRosterPlayerError(f"{label} is not valid UTF-16BE") from exc
        end += 2
    raise SaveRosterPlayerError(
        f"{label} exceeds the bounded {MAX_PLAYER_TEXT_UNITS}-character allocation"
    )


def _text_layout(
    raw: bytes, player_start: int
) -> tuple[tuple[PlayerTextAllocation, ...], Mapping[tuple[int, str], int]]:
    try:
        arrays_end_a = save_layout._relative_target(
            raw, save_layout.ROOT_OFFSET + 0x140, "save array-end pointer 0x140"
        )
        arrays_end_b = save_layout._relative_target(
            raw, save_layout.ROOT_OFFSET + 0x144, "save array-end pointer 0x144"
        )
        string_pool = save_layout._relative_target(
            raw, save_layout.ROOT_OFFSET + 0x148, "save string-pool pointer"
        )
    except save_layout.SaveAppearanceError as exc:
        raise SaveRosterPlayerError(str(exc)) from exc
    _require(arrays_end_a == arrays_end_b, "save array-end pointers disagree")
    _require(arrays_end_a <= string_pool <= len(raw), "save string-pool bounds changed")
    _require(
        not any(raw[arrays_end_a:string_pool]),
        "reserved save UTF-16 workspace contains nonzero bytes",
    )

    owners_by_target: dict[int, list[PlayerTextOwner]] = {}
    decoded_by_target: dict[int, tuple[str, int]] = {}
    for player_index in range(PLAYER_COUNT):
        record = player_start + player_index * PLAYER_STRIDE
        for field_id, relative in PLAYER_TEXT_FIELDS_BY_ID.items():
            field = record + relative
            try:
                target = save_layout._relative_target(
                    raw, field, f"player {player_index} {field_id} pointer"
                )
            except save_layout.SaveAppearanceError as exc:
                raise SaveRosterPlayerError(str(exc)) from exc
            _require(
                target >= string_pool,
                f"player {player_index} {field_id} does not target the save string pool",
            )
            owner = PlayerTextOwner(player_index, field_id)
            owners_by_target.setdefault(target, []).append(owner)
            if target not in decoded_by_target:
                decoded_by_target[target] = _decode_player_text(
                    raw, target, f"player {player_index} {field_id}"
                )

    allocations: list[PlayerTextAllocation] = []
    for target in sorted(owners_by_target):
        text, allocation_bytes = decoded_by_target[target]
        owners = tuple(
            sorted(owners_by_target[target], key=lambda row: row.owner_id)
        )
        fingerprint = _sha256(
            "\n".join(row.owner_id for row in owners).encode("utf-8")
        )
        allocations.append(
            PlayerTextAllocation(
                allocation_id=f"player-text:{fingerprint[:24]}",
                text=text,
                allocation_bytes=allocation_bytes,
                maximum_utf16_units=allocation_bytes // 2 - 1,
                owner_fingerprint=fingerprint,
                owners=owners,
                target_offset=target,
            )
        )
    for first, second in zip(allocations, allocations[1:]):
        _require(
            first.target_offset + first.allocation_bytes <= second.target_offset,
            "player text allocations overlap",
        )
    owner_map: dict[tuple[int, str], int] = {}
    for index, allocation in enumerate(allocations):
        for owner in allocation.owners:
            key = (owner.player_index, owner.field_id)
            _require(key not in owner_map, f"player text owner repeats: {owner.owner_id}")
            owner_map[key] = index
    _require(
        len(owner_map) == PLAYER_COUNT * len(PLAYER_TEXT_FIELDS_BY_ID),
        "complete player text-owner inventory changed",
    )
    return tuple(allocations), owner_map


def inspect_bytes(source: bytes, *, source_path: Path = Path("Roster.ROS")) -> SaveRosterDocument:
    raw, signed, kind, payload_path = _raw_payload(source)
    player_start, team_start, memberships = _layout(raw)
    text_allocations, text_owner_map = _text_layout(raw, player_start)
    return SaveRosterDocument(
        Path(source_path),
        _sha256(source),
        _sha256(raw),
        len(source),
        signed,
        kind,
        payload_path,
        player_start,
        team_start,
        memberships,
        text_allocations,
        text_owner_map,
        raw,
    )


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SaveRosterPlayerError(f"cannot open source read-only: {path}: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), f"source is not a regular file: {path}")
        _require(0 < info.st_size <= MAX_SOURCE_BYTES, "save source size is outside the bounded range")
        data = bytearray()
        while len(data) < info.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, info.st_size - len(data)))
            _require(bool(chunk), f"short read from source: {path}")
            data.extend(chunk)
        return bytes(data)
    finally:
        os.close(descriptor)


def inspect_save(path: Path) -> SaveRosterDocument:
    source = Path(path)
    return inspect_bytes(_read_regular(source), source_path=source)


def _membership_key(team: object, slot: object) -> tuple[int, int]:
    _require(type(team) is int and 0 <= team < TEAM_COUNT, "team index must be 0..39")
    _require(type(slot) is int and 0 <= slot < TEAM_MEMBER_CAPACITY, "roster slot must be 0..41")
    return int(team), int(slot)


def _replacement_text_bytes(
    allocation: PlayerTextAllocation, replacement: object
) -> tuple[str, bytes, int]:
    _require(isinstance(replacement, str), "player text replacement must be text")
    _require("\0" not in replacement, "player text replacement cannot contain NUL")
    try:
        encoded = replacement.encode("utf-16-be", errors="strict")
    except UnicodeEncodeError as exc:
        raise SaveRosterPlayerError(
            "player text replacement contains an unsupported Unicode value"
        ) from exc
    units = len(encoded) // 2
    _require(
        units <= allocation.maximum_utf16_units,
        f"{allocation.allocation_id} accepts at most "
        f"{allocation.maximum_utf16_units} UTF-16 characters; replacement needs {units}",
    )
    stored = encoded + b"\0\0"
    stored += b"\0" * (allocation.allocation_bytes - len(stored))
    return replacement, stored, units


def make_patch(
    document: SaveRosterDocument,
    field_edits: Iterable[PlayerFieldEdit] = (),
    membership_swaps: Iterable[MembershipSwap] = (),
    text_edits: Iterable[PlayerTextEdit] = (),
) -> tuple[bytes, dict[str, object]]:
    raw = document.raw_payload
    player_start, _team_start, memberships = _layout(raw)
    _require(_sha256(raw) == document.raw_payload_sha256, "inspected raw payload identity changed")
    output = bytearray(raw)
    authorized_masks: dict[int, int] = {}
    edit_rows: list[dict[str, object]] = []
    seen_fields: set[tuple[int, str]] = set()

    for edit in field_edits:
        player = _player_index(edit.player_index)
        field = FIELDS_BY_ID.get(edit.field_id)
        _require(field is not None, f"unknown packed-player field: {edit.field_id}")
        key = (player, field.field_id)
        _require(key not in seen_fields, f"player {player} field {field.field_id} is staged twice")
        seen_fields.add(key)
        start = player_start + player * PLAYER_STRIDE
        record = bytearray(output[start : start + PLAYER_STRIDE])
        before = field.decode(record)
        after = field.validate(edit.value)
        _require(before != after, f"player {player} {field.label} already equals {after}")
        for part in field.parts:
            absolute = start + part.byte_offset
            prior = authorized_masks.get(absolute, 0)
            _require(
                prior & part.storage_mask == 0,
                f"player {player} edits overlap packed bits at record byte 0x{part.byte_offset:X}",
            )
            authorized_masks[absolute] = prior | part.storage_mask
        field.encode_into(record, after)
        output[start : start + PLAYER_STRIDE] = record
        edit_rows.append(
            {
                "player_index": player,
                "field_id": field.field_id,
                "category": field.category,
                "before": before,
                "after": after,
            }
        )

    text_rows: list[dict[str, object]] = []
    seen_text_allocations: set[str] = set()
    for edit in text_edits:
        player = _player_index(edit.player_index)
        allocation = document.player_text_allocation(player, edit.field_id)
        _require(
            allocation.allocation_id not in seen_text_allocations,
            f"shared text allocation {allocation.allocation_id} is staged twice",
        )
        seen_text_allocations.add(allocation.allocation_id)
        replacement, stored, units = _replacement_text_bytes(allocation, edit.text)
        _require(
            replacement != allocation.text,
            f"player {player} {edit.field_id} already equals the requested text",
        )
        start = allocation.target_offset
        end = start + allocation.allocation_bytes
        _require(
            output[start:end]
            == allocation.text.encode("utf-16-be") + b"\0\0",
            f"{allocation.allocation_id} source allocation changed",
        )
        output[start:end] = stored
        for position in range(start, end):
            _require(position not in authorized_masks, "player text overlaps another staged edit")
            authorized_masks[position] = 0xFF
        text_rows.append(
            {
                "player_index": player,
                "field_id": edit.field_id,
                "allocation_id": allocation.allocation_id,
                "maximum_utf16_units": allocation.maximum_utf16_units,
                "replacement_utf16_units": units,
                "known_alias_count": len(allocation.owners),
                "owner_fingerprint": allocation.owner_fingerprint,
                "source_text_sha256": _sha256(allocation.text.encode("utf-8")),
                "replacement_text_sha256": _sha256(replacement.encode("utf-8")),
            }
        )

    by_key = {(row.team_index, row.roster_slot): row for row in memberships}
    swap_rows: list[dict[str, int]] = []
    used_membership_fields: set[int] = set()
    for swap in membership_swaps:
        first_key = _membership_key(swap.first_team, swap.first_slot)
        second_key = _membership_key(swap.second_team, swap.second_slot)
        _require(first_key != second_key, "membership swap must select two different slots")
        first = by_key.get(first_key)
        second = by_key.get(second_key)
        _require(first is not None and second is not None, "membership swap requires two populated counted slots")
        _require(
            first.pointer_field_offset not in used_membership_fields
            and second.pointer_field_offset not in used_membership_fields,
            "a membership slot is staged in more than one swap",
        )
        used_membership_fields.update((first.pointer_field_offset, second.pointer_field_offset))
        first_target = player_start + second.player_index * PLAYER_STRIDE
        second_target = player_start + first.player_index * PLAYER_STRIDE
        output[first.pointer_field_offset : first.pointer_field_offset + 4] = _relative_pointer(
            first.pointer_field_offset, first_target
        )
        output[second.pointer_field_offset : second.pointer_field_offset + 4] = _relative_pointer(
            second.pointer_field_offset, second_target
        )
        for position in range(first.pointer_field_offset, first.pointer_field_offset + 4):
            authorized_masks[position] = 0xFF
        for position in range(second.pointer_field_offset, second.pointer_field_offset + 4):
            authorized_masks[position] = 0xFF
        swap_rows.append(
            {
                "first_team": first.team_index,
                "first_slot": first.roster_slot,
                "first_player_before": first.player_index,
                "second_team": second.team_index,
                "second_slot": second.roster_slot,
                "second_player_before": second.player_index,
            }
        )

    _require(
        edit_rows or text_rows or swap_rows,
        "stage at least one packed-player, player-text, or membership edit",
    )
    frozen = bytes(output)
    reparsed = inspect_bytes(frozen)
    _require(len(reparsed.memberships) == len(memberships), "membership count changed after patch")
    changed = [index for index, pair in enumerate(zip(raw, frozen, strict=True)) if pair[0] != pair[1]]
    _require(bool(changed), "staged roster patch changed no bytes")
    for position in changed:
        mask = authorized_masks.get(position, 0)
        _require(mask != 0, "roster patch changed a byte outside selected targets")
        _require(((raw[position] ^ frozen[position]) & ~mask) == 0, "roster patch changed unowned packed bits")

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "source": {
            "source_sha256": document.source_sha256,
            "raw_payload_sha256": document.raw_payload_sha256,
            "source_was_signed_container": document.signed_container,
            "container_kind": document.container_kind,
            "payload_path": document.payload_path,
            "opened_read_only": True,
        },
        "output": {
            "layout": "raw_roster_payload",
            "sha256": _sha256(frozen),
            "size": len(frozen),
            "changed_byte_count": len(changed),
        },
        "field_edits": edit_rows,
        "text_edits": text_rows,
        "membership_swaps": swap_rows,
        "authorized_masks": [
            {"offset": position, "mask": mask}
            for position, mask in sorted(authorized_masks.items())
        ],
        "claims": {
            "all_nonselected_bits_preserved": True,
            "all_player_text_pointers_preserved": True,
            "all_text_replacements_fit_existing_allocations": True,
            "team_membership_counts_preserved": True,
            "membership_pointer_multiset_preserved": True,
            "output_is_raw_payload": True,
            "container_rehashed_or_resigned": False,
            "external_reinjection_required": document.signed_container,
            "runtime_in_game_proved": False,
            "overall_written": False,
            "active_roster_capacity_expanded": False,
        },
    }
    verify_patch(document, frozen, manifest)
    return frozen, manifest


def verify_patch(
    document: SaveRosterDocument,
    output: bytes,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    _require(manifest.get("schema") == SCHEMA, "packed-player manifest schema changed")
    source = manifest.get("source")
    result = manifest.get("output")
    _require(isinstance(source, Mapping) and isinstance(result, Mapping), "packed-player manifest is incomplete")
    _require(source.get("raw_payload_sha256") == document.raw_payload_sha256, "manifest source payload differs")
    _require(result.get("sha256") == _sha256(output), "output SHA-256 differs from manifest")
    _require(result.get("size") == len(output), "output size differs from manifest")
    reparsed = inspect_bytes(output)
    masks = manifest.get("authorized_masks")
    _require(isinstance(masks, list) and masks, "manifest has no authorized masks")
    allowed: dict[int, int] = {}
    for row in masks:
        _require(isinstance(row, Mapping), "authorized-mask row is malformed")
        position, mask = row.get("offset"), row.get("mask")
        _require(type(position) is int and type(mask) is int and 0 <= position < len(output) and 0 < mask <= 0xFF, "authorized mask is invalid")
        _require(position not in allowed, "authorized mask offset repeats")
        allowed[int(position)] = int(mask)

    expected_allowed: dict[int, int] = {}

    def expect_mask(position: int, mask: int) -> None:
        prior = expected_allowed.get(position, 0)
        _require(prior & mask == 0, "manifest edit targets overlap")
        expected_allowed[position] = prior | mask

    field_rows = manifest.get("field_edits")
    text_rows = manifest.get("text_edits")
    swap_rows = manifest.get("membership_swaps")
    _require(isinstance(field_rows, list), "manifest field edits are malformed")
    _require(isinstance(text_rows, list), "manifest text edits are malformed")
    _require(isinstance(swap_rows, list), "manifest membership swaps are malformed")
    seen_field_rows: set[tuple[int, str]] = set()
    for row in field_rows:
        _require(isinstance(row, Mapping), "field-edit receipt is malformed")
        player, field_id = row.get("player_index"), row.get("field_id")
        player = _player_index(player)
        _require(isinstance(field_id, str), "field-edit field ID is malformed")
        field = FIELDS_BY_ID.get(field_id)
        _require(field is not None, "field-edit receipt names an unknown field")
        key = (player, field_id)
        _require(key not in seen_field_rows, "field-edit receipt repeats a target")
        seen_field_rows.add(key)
        source_record = document.player_record(player)
        _require(row.get("before") == field.decode(source_record), "field-edit source value differs")
        after = field.validate(row.get("after"))
        _require(after != row.get("before"), "field-edit receipt is a no-op")
        _require(row.get("category") == field.category, "field-edit category differs")
        record = document.player_start + player * PLAYER_STRIDE
        for part in field.parts:
            expect_mask(record + part.byte_offset, part.storage_mask)

    seen_text_rows: set[str] = set()
    for row in text_rows:
        _require(isinstance(row, Mapping), "text-edit receipt is malformed")
        player, field_id = row.get("player_index"), row.get("field_id")
        player = _player_index(player)
        _require(isinstance(field_id, str), "text-edit field ID is malformed")
        allocation = document.player_text_allocation(player, field_id)
        _require(
            allocation.allocation_id == row.get("allocation_id")
            and allocation.owner_fingerprint == row.get("owner_fingerprint"),
            "text-edit source allocation ownership differs",
        )
        _require(
            allocation.allocation_id not in seen_text_rows,
            "text-edit receipt repeats a shared allocation",
        )
        seen_text_rows.add(allocation.allocation_id)
        _require(
            row.get("maximum_utf16_units") == allocation.maximum_utf16_units
            and row.get("known_alias_count") == len(allocation.owners),
            "text-edit allocation limits differ",
        )
        _require(
            row.get("source_text_sha256")
            == _sha256(allocation.text.encode("utf-8")),
            "text-edit source hash differs",
        )
        units = row.get("replacement_utf16_units")
        _require(
            type(units) is int and 0 <= units <= allocation.maximum_utf16_units,
            "text-edit replacement length is invalid",
        )
        for position in range(
            allocation.target_offset,
            allocation.target_offset + allocation.allocation_bytes,
        ):
            expect_mask(position, 0xFF)

    before_members = {
        (row.team_index, row.roster_slot): row.player_index
        for row in document.memberships
    }
    source_members = {
        (row.team_index, row.roster_slot): row for row in document.memberships
    }
    used_membership_fields: set[int] = set()
    for row in swap_rows:
        _require(isinstance(row, Mapping), "membership-swap receipt is malformed")
        first = (row.get("first_team"), row.get("first_slot"))
        second = (row.get("second_team"), row.get("second_slot"))
        first_source = source_members.get(first)
        second_source = source_members.get(second)
        _require(
            first_source is not None and second_source is not None and first != second,
            "membership-swap receipt does not name two populated source slots",
        )
        _require(
            row.get("first_player_before") == first_source.player_index
            and row.get("second_player_before") == second_source.player_index,
            "membership-swap source players differ",
        )
        for field_offset in (
            first_source.pointer_field_offset,
            second_source.pointer_field_offset,
        ):
            _require(
                field_offset not in used_membership_fields,
                "membership-swap receipt repeats a slot",
            )
            used_membership_fields.add(field_offset)
            for position in range(field_offset, field_offset + 4):
                expect_mask(position, 0xFF)
    _require(allowed == expected_allowed, "authorized masks differ from semantic edit targets")

    changed = 0
    for position, (before, after) in enumerate(zip(document.raw_payload, output, strict=True)):
        if before == after:
            continue
        changed += 1
        mask = allowed.get(position, 0)
        _require(mask and ((before ^ after) & ~mask) == 0, "output changed outside authorized packed bits")
    _require(changed == result.get("changed_byte_count"), "changed-byte count differs from manifest")

    for row in field_rows:
        _require(isinstance(row, Mapping), "field-edit receipt is malformed")
        player, field_id, after = row.get("player_index"), row.get("field_id"), row.get("after")
        _player_index(player)
        field = FIELDS_BY_ID.get(str(field_id))
        _require(field is not None, "field-edit receipt names an unknown field")
        _require(field.decode(reparsed.player_record(int(player))) == after, "field-edit output value differs")

    for row in text_rows:
        _require(isinstance(row, Mapping), "text-edit receipt is malformed")
        player, field_id = row.get("player_index"), row.get("field_id")
        _player_index(player)
        _require(isinstance(field_id, str), "text-edit field ID is malformed")
        allocation = reparsed.player_text_allocation(int(player), field_id)
        _require(
            allocation.allocation_id == row.get("allocation_id")
            and allocation.owner_fingerprint == row.get("owner_fingerprint"),
            "text-edit allocation ownership differs",
        )
        _require(
            _sha256(allocation.text.encode("utf-8"))
            == row.get("replacement_text_sha256"),
            "text-edit output value differs",
        )

    after_members = {(row.team_index, row.roster_slot): row.player_index for row in reparsed.memberships}
    _require(len(before_members) == len(after_members), "membership slot count changed")
    _require(sorted(before_members.values()) == sorted(after_members.values()), "membership player multiset changed")
    for row in swap_rows:
        _require(isinstance(row, Mapping), "membership-swap receipt is malformed")
        first = (row.get("first_team"), row.get("first_slot"))
        second = (row.get("second_team"), row.get("second_slot"))
        _require(after_members.get(first) == row.get("second_player_before"), "first membership swap result differs")
        _require(after_members.get(second) == row.get("first_player_before"), "second membership swap result differs")
    return {
        "schema": VERIFY_SCHEMA,
        "verified": True,
        "changed_byte_count": changed,
        "field_edit_count": len(field_rows),
        "text_edit_count": len(text_rows),
        "membership_swap_count": len(swap_rows),
    }


def _reserve(path: Path, mode: int) -> int:
    _require(path.parent.is_dir(), f"destination directory does not exist: {path.parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags, mode)
    except OSError as exc:
        raise SaveRosterPlayerError(f"refusing to overwrite destination: {path}: {exc}") from exc


def _write_all(descriptor: int, data: bytes) -> None:
    position = 0
    while position < len(data):
        count = os.write(descriptor, data[position:])
        _require(count > 0, "short write while creating roster output")
        position += count
    os.fsync(descriptor)


def write_new_save(
    document: SaveRosterDocument,
    output: Path,
    *,
    field_edits: Iterable[PlayerFieldEdit] = (),
    membership_swaps: Iterable[MembershipSwap] = (),
    text_edits: Iterable[PlayerTextEdit] = (),
    manifest: Path | None = None,
) -> SaveRosterWriteReceipt:
    current = _read_regular(document.source)
    _require(_sha256(current) == document.source_sha256, "source changed after inspection")
    payload, receipt = make_patch(document, field_edits, membership_swaps, text_edits)
    destination = Path(output)
    manifest_path = Path(manifest) if manifest is not None else destination.with_name(f"{destination.name}.players.json")
    _require(destination != manifest_path, "output and manifest paths must differ")
    manifest_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output_fd = manifest_fd = -1
    output_created = manifest_created = False
    try:
        output_fd = _reserve(destination, platform_compat.private_file_mode())
        output_created = True
        manifest_fd = _reserve(manifest_path, platform_compat.private_file_mode())
        manifest_created = True
        _write_all(output_fd, payload)
        _write_all(manifest_fd, manifest_bytes)
    except Exception:
        if output_fd >= 0:
            os.close(output_fd)
            output_fd = -1
        if manifest_fd >= 0:
            os.close(manifest_fd)
            manifest_fd = -1
        if output_created:
            destination.unlink(missing_ok=True)
        if manifest_created:
            manifest_path.unlink(missing_ok=True)
        raise
    finally:
        if output_fd >= 0:
            os.close(output_fd)
        if manifest_fd >= 0:
            os.close(manifest_fd)
    verification = verify_patch(document, payload, receipt)
    return SaveRosterWriteReceipt(
        destination,
        manifest_path,
        _sha256(payload),
        int(verification["changed_byte_count"]),
        int(verification["field_edit_count"]),
        int(verification["membership_swap_count"]),
        int(verification["text_edit_count"]),
        True,
        document.signed_container,
        document.signed_container,
    )


__all__ = [
    "FIELDS",
    "FIELDS_BY_ID",
    "MembershipSlot",
    "MembershipSwap",
    "PackedField",
    "PLAYER_TEXT_FIELDS_BY_ID",
    "PlayerFieldEdit",
    "PlayerTextAllocation",
    "PlayerTextEdit",
    "PlayerTextOwner",
    "SaveRosterDocument",
    "SaveRosterPlayerError",
    "SaveRosterWriteReceipt",
    "inspect_bytes",
    "inspect_save",
    "make_patch",
    "verify_patch",
    "write_new_save",
]
