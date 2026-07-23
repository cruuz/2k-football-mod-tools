"""Validated, retail-free APF 2K8 on-disc base-rating dictionary.

The dictionary names the exact independent rating bytes in each decoded player
record.  Public authoring is deliberately limited to 0..99 even though the
native getter accepts 100; an existing source value of 100 is displayed without
clipping and remains individually revertible.  Archive writing lives in the
token-preserving ROST tools, so this metadata module contains no game payload.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping


SCHEMA_ID = "apf2k8_player_ratings/v1"
DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "apf2k8_player_ratings.v1.json"
)
MAX_SCHEMA_BYTES = 64 * 1024


class PlayerRatingsError(ValueError):
    """Raised when the packaged dictionary or a player record is invalid."""


@dataclass(frozen=True)
class PlayerRatingField:
    field_id: str
    label: str
    relative_offset: int
    display_order: int
    formula_modifier_index: int
    label_status: str

    @property
    def relative_offset_hex(self) -> str:
        return f"0x{self.relative_offset:02X}"

    @property
    def named(self) -> bool:
        return self.label_status == "xex_ui_named"


@dataclass(frozen=True)
class ExcludedNeighborByte:
    relative_offset: int
    status: str

    @property
    def relative_offset_hex(self) -> str:
        return f"0x{self.relative_offset:02X}"


@dataclass(frozen=True)
class PlayerRatingSchema:
    fields: tuple[PlayerRatingField, ...]
    excluded_neighbor_bytes: tuple[ExcludedNeighborByte, ...]
    record_stride: int
    native_minimum: int
    native_maximum: int
    stock_observed_minimum: int
    stock_observed_maximum: int
    runtime_status: str
    runtime_reason: str
    display_policy: str

    def decode_record(self, record: bytes | bytearray | memoryview) -> dict[str, int]:
        """Return exact stored integers from one complete ``0x14C`` record."""

        view = memoryview(record)
        if len(view) != self.record_stride:
            raise PlayerRatingsError(
                f"APF player record is {len(view)} bytes; expected exactly "
                f"{self.record_stride} (0x{self.record_stride:X})"
            )
        values = {
            field.field_id: int(view[field.relative_offset])
            for field in self.fields
        }
        invalid = {
            field_id: value
            for field_id, value in values.items()
            if not self.native_minimum <= value <= self.native_maximum
        }
        if invalid:
            detail = ", ".join(
                f"{field_id}={value}" for field_id, value in invalid.items()
            )
            raise PlayerRatingsError(
                "APF base-rating bytes exceed the native 0..100 contract: "
                f"{detail}"
            )
        return values

    def field_rows(
        self, values: Mapping[str, object]
    ) -> tuple[dict[str, object], ...]:
        """Pair a decoded value mapping with immutable field metadata."""

        expected = {field.field_id for field in self.fields}
        actual = set(values)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise PlayerRatingsError(
                f"APF base-rating value keys changed; missing={missing}, extra={extra}"
            )
        rows: list[dict[str, object]] = []
        for field in self.fields:
            value = values[field.field_id]
            if isinstance(value, bool) or not isinstance(value, int):
                raise PlayerRatingsError(
                    f"APF base rating {field.field_id} must be an integer"
                )
            if not self.native_minimum <= value <= self.native_maximum:
                raise PlayerRatingsError(
                    f"APF base rating {field.field_id}={value} is outside 0..100"
                )
            rows.append(
                {
                    "id": field.field_id,
                    "label": field.label,
                    "value": value,
                    "relative_offset": field.relative_offset,
                    "relative_offset_hex": field.relative_offset_hex,
                    "label_status": field.label_status,
                }
            )
        return tuple(rows)


# The executable-backed contract is repeated here intentionally: the loader
# fails closed if packaged metadata is reordered, relabeled, or widened.  These
# are facts/coordinates only, never source bytes or player values.
_EXPECTED_FIELDS = (
    ("speed", "Speed", 0xBA, 0, 0, "xex_ui_named"),
    ("agility", "Agility", 0xBB, 1, 1, "xex_ui_named"),
    ("strength", "Strength", 0xC1, 2, 2, "xex_ui_named"),
    ("jumping", "Jumping", 0xC2, 3, 3, "xex_ui_named"),
    ("pass_arm_strength", "Pass Arm Strength", 0xBC, 4, 6, "xex_ui_named"),
    ("stamina", "Stamina", 0xBE, 5, 9, "xex_ui_named"),
    ("aggressiveness", "Aggressiveness", 0xD8, 6, 27, "xex_ui_named"),
    ("consistency", "Consistency", 0xD7, 7, 22, "xex_ui_named"),
    ("kick_power", "Kick Power", 0xBF, 8, 7, "xex_ui_named"),
    ("kicking_style", "Kicking Style", 0xD1, 9, 26, "xex_ui_named"),
    ("durability", "Durability", 0xC0, 10, 11, "xex_ui_named"),
    ("coverage", "Coverage", 0xC3, 11, 20, "xex_ui_named"),
    ("run_route", "Run Route", 0xC4, 12, 14, "xex_ui_named"),
    ("tackle", "Tackle", 0xC6, 13, 17, "xex_ui_named"),
    ("break_tackle", "Break Tackle", 0xC7, 14, 12, "xex_ui_named"),
    ("pass_accuracy", "Pass Accuracy", 0xC8, 15, 5, "xex_ui_named"),
    (
        "pass_read_coverage",
        "Pass Read Coverage",
        0xC9,
        16,
        13,
        "xex_ui_named",
    ),
    ("catch", "Catch", 0xCA, 17, 4, "xex_ui_named"),
    ("run_blocking", "Run Blocking", 0xCB, 18, 15, "xex_ui_named"),
    ("pass_blocking", "Pass Blocking", 0xCC, 19, 16, "xex_ui_named"),
    ("secure_ball", "Secure Ball", 0xCD, 20, 10, "xex_ui_named"),
    ("pass_rush", "Pass Rush", 0xCE, 21, 18, "xex_ui_named"),
    ("run_coverage", "Run Coverage", 0xCF, 22, 19, "xex_ui_named"),
    ("kick_accuracy", "Kick Accuracy", 0xD0, 23, 8, "xex_ui_named"),
    ("leadership", "Leadership", 0xD3, 24, 23, "xex_ui_named"),
    (
        "unknown_rating_24",
        "Unknown Rating 24",
        0xD4,
        25,
        24,
        "neutral_unresolved",
    ),
    ("composure", "Composure", 0xD5, 26, 21, "xex_ui_named"),
    ("scramble", "Scramble", 0xD6, 27, 25, "xex_ui_named"),
)
_EXPECTED_EXCLUDED = (
    (0xBD, "unknown_unassigned"),
    (0xC5, "unknown_unassigned"),
    (0xD2, "unknown_unassigned"),
    (0xD9, "height_in_inches_consumer_proved"),
)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PlayerRatingsError(f"{label} must be a JSON object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlayerRatingsError(f"{label} must be an integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlayerRatingsError(f"{label} must be nonempty text")
    return value


def load_player_rating_schema(path: Path | None = None) -> PlayerRatingSchema:
    """Load and fully validate the public metadata dictionary."""

    source = DEFAULT_SCHEMA_PATH if path is None else Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise PlayerRatingsError(
            f"Could not open APF player-rating dictionary: {source}"
        ) from exc
    if not 0 < size <= MAX_SCHEMA_BYTES:
        raise PlayerRatingsError(
            f"APF player-rating dictionary size {size} is outside 1..{MAX_SCHEMA_BYTES}"
        )
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlayerRatingsError(
            f"Could not decode APF player-rating dictionary: {source}"
        ) from exc
    root = _object(document, "APF player-rating dictionary")
    if root.get("schema") != SCHEMA_ID:
        raise PlayerRatingsError(
            f"APF player-rating schema is {root.get('schema')!r}; expected {SCHEMA_ID!r}"
        )
    if root.get("game") != "apf2k8_xbox360":
        raise PlayerRatingsError("APF player-rating dictionary targets the wrong game")
    if root.get("scope") != "on_disc_roster_base_ratings_editable":
        raise PlayerRatingsError("APF player-rating dictionary scope changed")

    source_contract = _object(root.get("source_contract"), "source_contract")
    record_stride = _integer(
        source_contract.get("player_record_stride"), "player_record_stride"
    )
    if record_stride != 0x14C:
        raise PlayerRatingsError("APF player record stride changed from 0x14C")
    if (
        _integer(source_contract.get("candidate_region_start"), "region start")
        != 0xBA
        or _integer(
            source_contract.get("candidate_region_end_inclusive"), "region end"
        )
        != 0xD9
    ):
        raise PlayerRatingsError("APF base-rating candidate region changed")

    scale = _object(root.get("scale"), "scale")
    scale_values = (
        _integer(scale.get("native_minimum"), "native_minimum"),
        _integer(scale.get("native_maximum"), "native_maximum"),
        _integer(scale.get("stock_observed_minimum"), "stock_observed_minimum"),
        _integer(scale.get("stock_observed_maximum"), "stock_observed_maximum"),
        _integer(scale.get("default_ui_minimum"), "default_ui_minimum"),
        _integer(scale.get("default_ui_maximum"), "default_ui_maximum"),
    )
    if scale_values != (0, 100, 0, 99, 0, 99):
        raise PlayerRatingsError(
            "APF player-rating native/stock/UI ranges changed from 0..100/0..99/0..99"
        )
    if scale.get("storage") != "unsigned_byte":
        raise PlayerRatingsError("APF base-rating storage is not unsigned_byte")

    raw_fields = root.get("fields")
    if not isinstance(raw_fields, list):
        raise PlayerRatingsError("fields must be a JSON array")
    parsed_fields: list[PlayerRatingField] = []
    for index, raw in enumerate(raw_fields):
        item = _object(raw, f"fields[{index}]")
        offset = _integer(item.get("relative_offset"), f"fields[{index}].offset")
        if item.get("relative_offset_hex") != f"0x{offset:02X}":
            raise PlayerRatingsError(f"fields[{index}] has a mismatched hex offset")
        parsed_fields.append(
            PlayerRatingField(
                _text(item.get("id"), f"fields[{index}].id"),
                _text(item.get("label"), f"fields[{index}].label"),
                offset,
                _integer(item.get("display_order"), f"fields[{index}].display_order"),
                _integer(
                    item.get("formula_modifier_index"),
                    f"fields[{index}].formula_modifier_index",
                ),
                _text(item.get("label_status"), f"fields[{index}].label_status"),
            )
        )
    observed_fields = tuple(
        (
            field.field_id,
            field.label,
            field.relative_offset,
            field.display_order,
            field.formula_modifier_index,
            field.label_status,
        )
        for field in parsed_fields
    )
    if observed_fields != _EXPECTED_FIELDS:
        raise PlayerRatingsError("APF player-rating field dictionary changed")
    if root.get("field_count") != 28 or root.get("named_field_count") != 27:
        raise PlayerRatingsError("APF player-rating field counts changed")
    if {field.formula_modifier_index for field in parsed_fields} != set(range(28)):
        raise PlayerRatingsError("APF formula modifier indices are not one exact 0..27 set")

    raw_excluded = root.get("excluded_neighbor_bytes")
    if not isinstance(raw_excluded, list):
        raise PlayerRatingsError("excluded_neighbor_bytes must be a JSON array")
    excluded: list[ExcludedNeighborByte] = []
    for index, raw in enumerate(raw_excluded):
        item = _object(raw, f"excluded_neighbor_bytes[{index}]")
        offset = _integer(
            item.get("relative_offset"), f"excluded_neighbor_bytes[{index}].offset"
        )
        if item.get("relative_offset_hex") != f"0x{offset:02X}":
            raise PlayerRatingsError(
                f"excluded_neighbor_bytes[{index}] has a mismatched hex offset"
            )
        excluded.append(
            ExcludedNeighborByte(
                offset,
                _text(item.get("status"), f"excluded_neighbor_bytes[{index}].status"),
            )
        )
    if tuple((item.relative_offset, item.status) for item in excluded) != _EXPECTED_EXCLUDED:
        raise PlayerRatingsError("APF excluded neighboring bytes changed")

    separation = _object(root.get("separation"), "separation")
    if set(separation) != {
        "overall",
        "abilities",
        "star_tier",
        "runtime_modifiers",
        "global_sliders",
    } or not all(isinstance(value, str) and value for value in separation.values()):
        raise PlayerRatingsError("APF rating-system separation notes are incomplete")
    runtime = _object(root.get("runtime"), "runtime")
    runtime_status = _text(runtime.get("status"), "runtime.status")
    if runtime_status != "token_preserving_runtime_loaded":
        raise PlayerRatingsError(
            "APF player-rating runtime status is not token-preserving loaded"
        )
    public = _object(root.get("public_distribution"), "public_distribution")
    if public.get("contains_retail_bytes") is not False or public.get(
        "contains_player_values"
    ) is not False:
        raise PlayerRatingsError("APF player-rating dictionary is not retail-free metadata")
    if public.get("metadata_contents") != (
        "field names, integer offsets, scale contracts, and findings only"
    ):
        raise PlayerRatingsError("APF player-rating public metadata boundary changed")

    return PlayerRatingSchema(
        tuple(parsed_fields),
        tuple(excluded),
        record_stride,
        scale_values[0],
        scale_values[1],
        scale_values[2],
        scale_values[3],
        runtime_status,
        _text(runtime.get("reason"), "runtime.reason"),
        _text(scale.get("display_policy"), "scale.display_policy"),
    )


__all__ = [
    "DEFAULT_SCHEMA_PATH",
    "ExcludedNeighborByte",
    "PlayerRatingField",
    "PlayerRatingSchema",
    "PlayerRatingsError",
    "SCHEMA_ID",
    "load_player_rating_schema",
]
