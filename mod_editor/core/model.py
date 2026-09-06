"""Serializable editor model with no GUI or binary-patching dependency."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
import re
from typing import Any
from uuid import uuid4

from .errors import ValidationError


PROJECT_SCHEMA = "vc_mod_project/v1"
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/ -]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GameId(str, Enum):
    NFL2K5 = "nfl2k5"
    APF2K8 = "apf2k8"
    NFL2K5_PS2 = "nfl2k5_ps2"
    MADDEN09_PS2 = "madden09_ps2"
    NCAA09_PS2 = "ncaa09_ps2"
    MVP05_PS2 = "mvp05_ps2"
    NFLBLITZ2002_PS2 = "nflblitz2002_ps2"
    NFLBLITZ2003_PS2 = "nflblitz2003_ps2"
    NFLSTREET1_PS2 = "nflstreet1_ps2"
    NFLSTREET3_PS2 = "nflstreet3_ps2"

    @property
    def display_name(self) -> str:
        return {
            GameId.NFL2K5: "ESPN NFL 2K5 (Original Xbox)",
            GameId.APF2K8: "All-Pro Football 2K8 (Xbox 360)",
            GameId.NFL2K5_PS2: "ESPN NFL 2K5 (PlayStation 2)",
            GameId.MADDEN09_PS2: "Madden NFL 09 (PS2)",
            GameId.NCAA09_PS2: "NCAA Football 09 (PS2)",
            GameId.MVP05_PS2: "MVP Baseball 2005 (PS2)",
            GameId.NFLBLITZ2002_PS2: "NFL Blitz 2002 (PS2)",
            GameId.NFLBLITZ2003_PS2: "NFL Blitz 2003 (PS2)",
            GameId.NFLSTREET1_PS2: "NFL Street (PS2)",
            GameId.NFLSTREET3_PS2: "NFL Street 3 (PS2)",
        }[self]


@dataclass(frozen=True)
class SourceRecord:
    selected_path: str
    inspected_path: str
    kind: str
    sha256: str
    size: int
    recognized: bool
    fingerprint_id: str | None = None
    detected_game: str | None = None
    note: str = ""


@dataclass(frozen=True)
class ReplacementItem:
    item_id: str
    capability_id: str
    replacement_path: str
    target_id: str

    @classmethod
    def create(
        cls, capability_id: str, replacement_path: str, target_id: str
    ) -> "ReplacementItem":
        cls.validate_target(target_id)
        target = target_id.strip()

        return cls(
            item_id=str(uuid4()),
            capability_id=capability_id,
            replacement_path=replacement_path,
            target_id=target,
        )

    @staticmethod
    def validate_target(target_id: str) -> None:
        if not isinstance(target_id, str):
            raise ValidationError("Target identifier must be a string")
        target = target_id.strip()
        if not _TARGET_RE.fullmatch(target):
            raise ValidationError(
                "Target identifiers may contain letters, numbers, spaces, '.', '_', '-', '/', or ':'; "
                "raw offsets and free-form binary edits are not supported."
            )
        lowered = target.lower()
        if lowered.startswith("0x") or "offset" in lowered:
            raise ValidationError(
                "Raw offsets are deliberately not accepted; select a named asset target."
            )


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    level: str
    message: str

    @classmethod
    def now(cls, level: str, message: str) -> "LogEntry":
        return cls(datetime.now(UTC).isoformat(timespec="seconds"), level, message)


@dataclass
class ModProject:
    name: str
    game: GameId
    project_id: str = field(default_factory=lambda: str(uuid4()))
    source: SourceRecord | None = None
    output_path: str = ""
    replacements: list[ReplacementItem] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)
    project_path: str | None = None
    dirty: bool = True

    def add_log(self, level: str, message: str) -> LogEntry:
        entry = LogEntry.now(level, message)
        self.log.append(entry)
        self.dirty = True
        return entry

    def to_document(self) -> dict[str, Any]:
        return {
            "schema": PROJECT_SCHEMA,
            "project_id": self.project_id,
            "name": self.name,
            "game": self.game.value,
            "source": asdict(self.source) if self.source else None,
            "output_path": self.output_path,
            "replacements": [asdict(item) for item in self.replacements],
            "log": [asdict(item) for item in self.log],
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "ModProject":
        expected = {
            "schema",
            "project_id",
            "name",
            "game",
            "source",
            "output_path",
            "replacements",
            "log",
        }
        if not isinstance(document, dict) or set(document) != expected:
            extra = sorted(set(document) - expected) if isinstance(document, dict) else []
            missing = sorted(expected - set(document)) if isinstance(document, dict) else sorted(expected)
            raise ValidationError(f"Invalid project fields; missing={missing}, extra={extra}")
        if document["schema"] != PROJECT_SCHEMA:
            raise ValidationError(f"Unsupported project schema: {document['schema']!r}")
        try:
            game = GameId(document["game"])
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Unsupported game id: {document['game']!r}") from exc
        if not isinstance(document["name"], str) or not document["name"].strip():
            raise ValidationError("Project name must be a non-empty string")
        if not isinstance(document["project_id"], str) or not document["project_id"]:
            raise ValidationError("Project id must be a non-empty string")
        if not isinstance(document["output_path"], str):
            raise ValidationError("Output path must be a string")

        source = None
        if document["source"] is not None:
            if not isinstance(document["source"], dict):
                raise ValidationError("Source record must be an object or null")
            try:
                source = SourceRecord(**document["source"])
            except TypeError as exc:
                raise ValidationError(f"Invalid source record: {exc}") from exc
            source_strings = (
                source.selected_path,
                source.inspected_path,
                source.kind,
                source.sha256,
                source.note,
            )
            if not all(isinstance(value, str) for value in source_strings):
                raise ValidationError("Source record string fields are invalid")
            if _SHA256_RE.fullmatch(source.sha256) is None:
                raise ValidationError("Source SHA-256 must be 64 lowercase hexadecimal characters")
            if type(source.size) is not int or source.size < 0 or type(source.recognized) is not bool:
                raise ValidationError("Source size/recognition fields are invalid")
            if source.detected_game is not None and source.detected_game not in {
                game.value for game in GameId
            }:
                raise ValidationError("Source detected game is invalid")

        replacements_raw = document["replacements"]
        logs_raw = document["log"]
        if not isinstance(replacements_raw, list) or not isinstance(logs_raw, list):
            raise ValidationError("Replacement queue and log must be arrays")
        try:
            replacements = [ReplacementItem(**item) for item in replacements_raw]
            logs = [LogEntry(**item) for item in logs_raw]
        except (TypeError, AttributeError) as exc:
            raise ValidationError(f"Invalid project list item: {exc}") from exc

        for item in replacements:
            ReplacementItem.validate_target(item.target_id)
            if not all(
                isinstance(value, str) and value
                for value in (item.item_id, item.capability_id, item.replacement_path)
            ):
                raise ValidationError("Replacement queue fields must be non-empty strings")
        for item in logs:
            if not all(
                isinstance(value, str) and value
                for value in (item.timestamp, item.level, item.message)
            ):
                raise ValidationError("Log fields must be non-empty strings")
        return cls(
            name=document["name"].strip(),
            game=game,
            project_id=document["project_id"],
            source=source,
            output_path=document["output_path"],
            replacements=replacements,
            log=logs,
            dirty=False,
        )
