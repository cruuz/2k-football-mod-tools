"""Retail-free APF 2K8 player-position dictionary and mirror contract."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


SCHEMA_ID = "apf2k8_player_positions/v1"
DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "apf2k8_player_positions.v1.json"
)
MAX_SCHEMA_BYTES = 32 * 1024


class PlayerPositionsError(ValueError):
    """The public position dictionary or one source record is invalid."""


@dataclass(frozen=True)
class PlayerPosition:
    code: int
    abbreviation: str
    name: str


@dataclass(frozen=True)
class PlayerPositionSchema:
    positions: tuple[PlayerPosition, ...]
    player_count: int
    record_stride: int
    semantic_relative_offset: int
    mirror_relative_offset: int
    runtime_status: str
    runtime_reason: str

    @property
    def code_minimum(self) -> int:
        return self.positions[0].code

    @property
    def code_maximum(self) -> int:
        return self.positions[-1].code

    def position_for(self, code: object) -> PlayerPosition:
        if type(code) is not int or not self.code_minimum <= code <= self.code_maximum:
            raise PlayerPositionsError("APF player position code must be an integer from 0 to 16")
        position = self.positions[code]
        if position.code != code:
            raise PlayerPositionsError("APF player-position dictionary order changed")
        return position

    def decode_record(self, record: bytes | bytearray | memoryview) -> PlayerPosition:
        view = memoryview(record)
        if len(view) != self.record_stride:
            raise PlayerPositionsError(
                f"APF player record is {len(view)} bytes; expected exactly "
                f"{self.record_stride} (0x{self.record_stride:X})"
            )
        semantic = int(view[self.semantic_relative_offset])
        mirror = int(view[self.mirror_relative_offset])
        position = self.position_for(semantic)
        if mirror != semantic:
            raise PlayerPositionsError(
                "APF player position source mirror +0x35 differs from semantic +0x34"
            )
        return position


_EXPECTED_POSITIONS = (
    (0, "QB", "Quarterback"),
    (1, "K", "Kicker"),
    (2, "P", "Punter"),
    (3, "WR", "Wide Receiver"),
    (4, "CB", "Cornerback"),
    (5, "FS", "Free Safety"),
    (6, "SS", "Strong Safety"),
    (7, "HB", "Halfback"),
    (8, "FB", "Fullback"),
    (9, "TE", "Tight End"),
    (10, "OLB", "Outside Linebacker"),
    (11, "ILB", "Inside Linebacker"),
    (12, "C", "Center"),
    (13, "G", "Guard"),
    (14, "T", "Tackle"),
    (15, "DT", "Defensive Tackle"),
    (16, "DE", "Defensive End"),
)


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise PlayerPositionsError(f"{label} must be an integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlayerPositionsError(f"{label} must be nonempty text")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PlayerPositionsError(f"{label} must be a JSON object")
    return value


def load_player_position_schema(path: Path | None = None) -> PlayerPositionSchema:
    """Load and fail closed over the complete public position contract."""

    source = DEFAULT_SCHEMA_PATH if path is None else Path(path)
    try:
        size = source.stat().st_size
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlayerPositionsError(
            f"Could not decode APF player-position dictionary: {source}"
        ) from exc
    if not 0 < size <= MAX_SCHEMA_BYTES:
        raise PlayerPositionsError("APF player-position dictionary size is invalid")
    root = _object(document, "APF player-position dictionary")
    if root.get("schema") != SCHEMA_ID:
        raise PlayerPositionsError("APF player-position schema changed")
    if root.get("game") != "apf2k8_xbox360":
        raise PlayerPositionsError("APF player-position dictionary targets the wrong game")
    if root.get("scope") != "on_disc_roster_player_position_editable":
        raise PlayerPositionsError("APF player-position dictionary scope changed")

    contract = _object(root.get("source_contract"), "source_contract")
    values = (
        _integer(contract.get("total_player_records"), "total_player_records"),
        _integer(contract.get("player_record_stride"), "player_record_stride"),
        _integer(contract.get("semantic_relative_offset"), "semantic_relative_offset"),
        _integer(contract.get("mirror_relative_offset"), "mirror_relative_offset"),
    )
    if values != (2_254, 0x14C, 0x34, 0x35):
        raise PlayerPositionsError("APF player-position record contract changed")
    if (
        contract.get("player_record_stride_hex") != "0x14C"
        or contract.get("semantic_relative_offset_hex") != "0x34"
        or contract.get("mirror_relative_offset_hex") != "0x35"
        or contract.get("source_mirror_required") is not True
    ):
        raise PlayerPositionsError("APF player-position mirror contract changed")
    if root.get("code_minimum") != 0 or root.get("code_maximum") != 16:
        raise PlayerPositionsError("APF player-position code range changed")

    raw_positions = root.get("positions")
    if not isinstance(raw_positions, list):
        raise PlayerPositionsError("positions must be a JSON array")
    positions = tuple(
        PlayerPosition(
            _integer(_object(item, f"positions[{index}]").get("code"), "position code"),
            _text(_object(item, f"positions[{index}]").get("abbreviation"), "position abbreviation"),
            _text(_object(item, f"positions[{index}]").get("name"), "position name"),
        )
        for index, item in enumerate(raw_positions)
    )
    if tuple((item.code, item.abbreviation, item.name) for item in positions) != _EXPECTED_POSITIONS:
        raise PlayerPositionsError("APF player-position dictionary changed")

    runtime = _object(root.get("runtime"), "runtime")
    runtime_status = _text(runtime.get("status"), "runtime.status")
    if runtime_status != "offline_writer_proved_runtime_spot_check_pending":
        raise PlayerPositionsError("APF player-position runtime status changed")
    public = _object(root.get("public_distribution"), "public_distribution")
    if (
        public.get("contains_retail_bytes") is not False
        or public.get("contains_player_values") is not False
        or public.get("metadata_contents")
        != "position codes, labels, record-relative offsets, and safety findings only"
    ):
        raise PlayerPositionsError("APF player-position metadata is not retail-free")
    return PlayerPositionSchema(
        positions,
        values[0],
        values[1],
        values[2],
        values[3],
        runtime_status,
        _text(runtime.get("reason"), "runtime.reason"),
    )


__all__ = [
    "DEFAULT_SCHEMA_PATH",
    "PlayerPosition",
    "PlayerPositionSchema",
    "PlayerPositionsError",
    "SCHEMA_ID",
    "load_player_position_schema",
]
