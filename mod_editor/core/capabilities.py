"""Strict adapter for the research-owned capability registry.

The canonical registry lives in ``mod_editor/capabilities/registry.v1.json`` and
is maintained separately from this editor.  A tiny embedded sample keeps GUI
development and tests usable before that generated/reviewed registry exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any

from .errors import RegistryError
from .model import GameId


REGISTRY_SCHEMA = "vc_mod_capability_registry/v1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,127}$")


class Classification(str, Enum):
    RUNTIME_PROVED = "runtime-proved"
    OFFLINE_WRITER_PROVED = "offline-writer-proved"
    EXTRACT_ONLY = "extract-only"
    READ_ONLY_MAPPED = "read-only-mapped"
    UNKNOWN = "unknown"
    UNSAFE_DEFERRED = "unsafe/deferred"

    @property
    def badge(self) -> str:
        if self in {self.RUNTIME_PROVED, self.OFFLINE_WRITER_PROVED}:
            return "PROVED"
        if self in {self.EXTRACT_ONLY, self.READ_ONLY_MAPPED}:
            return "READ ONLY"
        return "PORTME"


@dataclass(frozen=True)
class Capability:
    capability_id: str
    game: GameId
    surface: str
    classification: Classification
    title: str
    category: str
    summary: str
    accepted_extensions: tuple[str, ...]
    raw: dict[str, Any]

    @property
    def badge(self) -> str:
        return self.classification.badge

    @property
    def can_queue_replacement(self) -> bool:
        backend = self.raw.get("backend", {})
        gui = self.raw.get("gui", {})
        return self.classification in {
            Classification.RUNTIME_PROVED,
            Classification.OFFLINE_WRITER_PROVED,
        } and (
            backend.get("operation") == "write"
            and isinstance(backend.get("module"), str)
            and isinstance(backend.get("command"), str)
            and gui.get("expose") is True
            and gui.get("mode") == "edit"
            and bool(self.accepted_extensions)
        )

    @property
    def is_experimental(self) -> bool:
        experimental_surface = self.surface in {
            "catching_drops",
            "cpu_ai_draft",
            "cross_title_model_conversion",
            "franchise_restoration_cross_title",
            "gameplay_tuning_sliders",
            "mode_state_routing",
            "scorebug_presentation",
        }
        # A reviewed data writer on an otherwise advanced surface belongs in
        # the normal browser. Its registry row still carries every remaining
        # behavior, geometry, and runtime limit.
        return experimental_surface and self.classification not in {
            Classification.RUNTIME_PROVED,
            Classification.OFFLINE_WRITER_PROVED,
        }


@dataclass(frozen=True)
class CapabilityRegistry:
    capabilities: tuple[Capability, ...]
    source_path: Path | None
    used_sample_fallback: bool
    warning: str = ""
    game_metadata: dict[GameId, dict[str, Any]] = field(default_factory=dict)

    def for_game(self, game: GameId) -> tuple[Capability, ...]:
        return tuple(item for item in self.capabilities if item.game == game)

    def get(self, capability_id: str) -> Capability:
        for item in self.capabilities:
            if item.capability_id == capability_id:
                return item
        raise RegistryError(f"Unknown capability id: {capability_id}")


_SAMPLE_REGISTRY: dict[str, Any] = {
    "schema": REGISTRY_SCHEMA,
    "games": [
        {"id": "nfl2k5_xbox", "title": "ESPN NFL 2K5"},
        {"id": "apf2k8_xbox360", "title": "All-Pro Football 2K8"},
        {"id": "nfl2k5_ps2", "title": "ESPN NFL 2K5 (PS2)"},
        {"id": "madden09_ps2", "title": "Madden NFL 09 (USA, PlayStation 2)"},
    ],
    "capabilities": [
        {
            "id": "sample.nfl2k5.uniform_png",
            "game": "nfl2k5_xbox",
            "surface": "uniform texture",
            "classification": "offline-writer-proved",
            "backend": {"operation": "none", "module": None, "command": None},
            "input_constraints": ["PNG input (sample row only)"],
            "source_container": {"format": "XISO", "hash_pins": [], "resource": "sample", "retail_file": "user-owned XISO"},
            "selectors": {"fields": [], "notes": "Named targets only"},
            "validation_command": None,
            "runtime": {"status": "not-tested", "scope": "Sample only", "evidence": []},
            "portme": ["Sample only; canonical registry not loaded."],
            "public_distribution": {"game_data": "never-bundle-retail-data", "mod_payload": "none-until-safe", "rule": "No retail data", "tooling": "source-and-schemas-only"},
            "evidence": [],
            "title": "Sample uniform PNG replacement",
            "summary": "Temporary UI sample; no patch backend is dispatched.",
            "gui": {"default_enabled": False, "expose": False, "mode": "deferred", "reason": "Canonical registry unavailable"},
        },
        {
            "id": "sample.apf2k8.models",
            "game": "apf2k8_xbox360",
            "surface": "3D models",
            "classification": "unknown",
            "backend": {"operation": "none", "module": None, "command": None},
            "input_constraints": ["No accepted replacement format"],
            "source_container": {"format": "Xbox 360 volume", "hash_pins": [], "resource": "sample", "retail_file": "user-owned disc/extracted volume"},
            "selectors": {"fields": [], "notes": "No selector available"},
            "validation_command": None,
            "runtime": {"status": "not-tested", "scope": "No runtime test", "evidence": []},
            "portme": ["Model replacement writer has not been established."],
            "public_distribution": {"game_data": "never-bundle-retail-data", "mod_payload": "none-until-safe", "rule": "No retail data", "tooling": "source-and-schemas-only"},
            "evidence": [],
            "title": "Model replacement",
            "summary": "Research boundary only.",
            "gui": {"default_enabled": False, "expose": False, "mode": "deferred", "reason": "No writer"},
        },
    ],
}


class CapabilityRegistryLoader:
    """Load the canonical v1 registry and reject ambiguous/malformed records."""

    def __init__(self, canonical_path: Path | None = None):
        package_root = Path(__file__).resolve().parents[1]
        self.canonical_path = canonical_path or package_root / "capabilities" / "registry.v1.json"

    def load(
        self,
        allow_sample_fallback: bool = True,
        *,
        check_files: bool = True,
    ) -> CapabilityRegistry:
        """Load the canonical registry.

        ``check_files=False`` is the product-runtime mode: the canonical
        classifications and UI metadata are still fully validated, while
        development-only evidence paths are not required in a retail-free
        application package.
        """
        if self.canonical_path.is_file():
            try:
                from mod_editor.capabilities.validate_registry import load_and_validate

                document = load_and_validate(
                    self.canonical_path, check_files=check_files
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise RegistryError(f"Cannot read capability registry: {exc}") from exc
            capabilities = self._parse_document(document, canonical=True)
            return CapabilityRegistry(
                capabilities,
                self.canonical_path,
                False,
                game_metadata=self._game_metadata(document["games"]),
            )
        if not allow_sample_fallback:
            raise RegistryError(f"Capability registry is missing: {self.canonical_path}")
        return CapabilityRegistry(
            self._parse_document(_SAMPLE_REGISTRY, canonical=False),
            None,
            True,
            "Canonical capability registry is unavailable; showing two non-release sample rows.",
            self._game_metadata(_SAMPLE_REGISTRY["games"]),
        )

    def _parse_document(self, document: Any, *, canonical: bool) -> tuple[Capability, ...]:
        if not isinstance(document, dict):
            raise RegistryError("Registry root must be an object")
        if document.get("schema") != REGISTRY_SCHEMA:
            raise RegistryError(f"Unsupported registry schema: {document.get('schema')!r}")
        expected_root = (
            {"$schema", "schema", "games", "capabilities", "classification_definitions", "surfaces"}
            if canonical
            else {"schema", "games", "capabilities"}
        )
        if set(document) != expected_root:
            raise RegistryError(
                f"Registry root fields differ from the {'canonical' if canonical else 'sample'} contract"
            )
        self._validate_games(document["games"])
        rows = document["capabilities"]
        if not isinstance(rows, list) or not rows:
            raise RegistryError("Registry capabilities must be a non-empty array")
        parsed = tuple(self._parse_capability(row, index) for index, row in enumerate(rows))
        ids = [row.capability_id for row in parsed]
        if len(ids) != len(set(ids)):
            raise RegistryError("Registry capability ids must be unique")
        return tuple(sorted(parsed, key=lambda row: (row.game.value, row.category, row.title)))

    @staticmethod
    def _validate_games(games: Any) -> None:
        if not isinstance(games, list) or not games:
            raise RegistryError("Registry games must be a non-empty array")
        seen: set[str] = set()
        for row in games:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise RegistryError("Each game record must be an object with a string id")
            try:
                CapabilityRegistryLoader._game_id(row["id"])
            except ValueError as exc:
                raise RegistryError(f"Unsupported registry game id: {row['id']!r}") from exc
            seen.add(row["id"])
        required = {"nfl2k5_xbox", "apf2k8_xbox360", "nfl2k5_ps2", "madden09_ps2"}
        if seen != required:
            raise RegistryError(f"Registry game ids must be exactly {sorted(required)}")

    @staticmethod
    def _parse_capability(row: Any, index: int) -> Capability:
        required = {
            "id",
            "game",
            "surface",
            "classification",
            "backend",
            "input_constraints",
            "source_container",
            "selectors",
            "validation_command",
            "runtime",
            "portme",
            "public_distribution",
            "evidence",
            "gui",
        }
        if not isinstance(row, dict):
            raise RegistryError(f"Capability {index} must be an object")
        missing = sorted(required - set(row))
        if missing:
            raise RegistryError(f"Capability {index} is missing fields: {missing}")
        capability_id = row["id"]
        if not isinstance(capability_id, str) or not _ID_RE.fullmatch(capability_id):
            raise RegistryError(f"Capability {index} has invalid id: {capability_id!r}")
        try:
            game = CapabilityRegistryLoader._game_id(row["game"])
            classification = Classification(row["classification"])
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"Capability {capability_id} has invalid enum value") from exc
        if not isinstance(row["surface"], str) or not row["surface"].strip():
            raise RegistryError(f"Capability {capability_id} needs a non-empty surface")
        for key in ("selectors", "runtime", "public_distribution", "gui", "source_container", "backend"):
            if not isinstance(row[key], dict):
                raise RegistryError(f"Capability {capability_id} field {key} must be an object")
        if not isinstance(row["evidence"], list):
            raise RegistryError(f"Capability {capability_id} evidence must be an array")
        if not isinstance(row["input_constraints"], list) or not all(
            isinstance(value, str) for value in row["input_constraints"]
        ):
            raise RegistryError(f"Capability {capability_id} input constraints must be strings")
        title = row.get("title", capability_id)
        category = row["surface"].replace("_", " ").title()
        summary = row.get("summary", "")
        if not all(isinstance(value, str) for value in (title, category, summary)):
            raise RegistryError(f"Capability {capability_id} GUI strings are invalid")
        extensions = CapabilityRegistryLoader._extract_extensions(row["input_constraints"])
        return Capability(
            capability_id=capability_id,
            game=game,
            surface=row["surface"],
            classification=classification,
            title=title,
            category=category,
            summary=summary,
            accepted_extensions=extensions,
            raw=row,
        )

    @staticmethod
    def _extract_extensions(constraints: list[str]) -> tuple[str, ...]:
        candidates: list[str] = []
        aliases = {
            "png": ".png",
            "gltf": ".gltf",
            "glb": ".glb",
            "obj": ".obj",
            "wav": ".wav",
            "xma": ".xma",
            "ogg": ".ogg",
            "json": ".json",
            "csv": ".csv",
        }
        for description in constraints:
            lowered = description.lower()
            for token, extension in aliases.items():
                if re.search(rf"(?<![a-z0-9])\.?{re.escape(token)}(?![a-z0-9])", lowered):
                    candidates.append(extension)
        result: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, str):
                raise RegistryError("Input extension constraints must be strings")
            normalized = aliases.get(candidate.lower(), candidate.lower())
            if not normalized.startswith(".") or not re.fullmatch(r"\.[a-z0-9]{1,10}", normalized):
                raise RegistryError(f"Invalid replacement extension: {candidate!r}")
            if normalized not in result:
                result.append(normalized)
        return tuple(result)

    @staticmethod
    def _game_id(registry_id: str) -> GameId:
        mapping = {
            "nfl2k5_xbox": GameId.NFL2K5,
            "apf2k8_xbox360": GameId.APF2K8,
            "nfl2k5_ps2": GameId.NFL2K5_PS2,
            "madden09_ps2": GameId.MADDEN09_PS2,
        }
        try:
            return mapping[registry_id]
        except (KeyError, TypeError) as exc:
            raise RegistryError(f"Unsupported registry game id: {registry_id!r}") from exc

    @staticmethod
    def _game_metadata(rows: list[dict[str, Any]]) -> dict[GameId, dict[str, Any]]:
        return {
            CapabilityRegistryLoader._game_id(row["id"]): dict(row)
            for row in rows
        }
