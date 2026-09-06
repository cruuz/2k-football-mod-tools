#!/usr/bin/env python3
"""Strict stdlib validator for the public mod-editor capability registry."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = Path(__file__).with_name("registry.v1.json")
DEFAULT_SCHEMA = Path(__file__).with_name("registry.schema.json")

SCHEMA_ID = "vc_mod_capability_registry/v1"
SCHEMA_DOCUMENT_ID = "urn:vc-mod-capability-registry:v1"
GAMES = ("apf2k8_xbox360", "madden09_ps2", "mvp05_ps2", "ncaa09_ps2", "nfl2k5_ps2", "nfl2k5_xbox", "nflblitz2002_ps2")
# The two long-established games; nfl2k5_ps2 joins a surface's coverage rule
# only when that surface actually ships a PS2 capability row.
# The games every GAMES-wide surface rule was written for; a newer game
# covers only the surfaces its own rows declare below.
_ESTABLISHED_GAMES = ("apf2k8_xbox360", "nfl2k5_ps2", "nfl2k5_xbox")
_LEGACY_GAMES = ("apf2k8_xbox360", "nfl2k5_xbox")
SURFACES = (
    "audio",
    "catching_drops",
    "colors",
    "cpu_ai_draft",
    "crib_assets",
    "cross_title_model_conversion",
    "franchise_restoration_cross_title",
    "gameplay_tuning_sliders",
    "logos_cards",
    "menus",
    "mode_state_routing",
    "models_shap_scne",
    "players_rosters",
    "portraits_faces",
    "saves",
    "schedules_franchise",
    "scorebug_presentation",
    "scripts_config",
    "stadiums_fields",
    "textures",
    "uniforms",
)
SURFACE_GAMES = {surface: _LEGACY_GAMES for surface in SURFACES}
SURFACE_GAMES["crib_assets"] = ("nfl2k5_xbox",)
# The texture lane is NFL 2K5 only: APF 2K8 keeps its own field-art and
# uniform writers and has no equivalent corpus mapped. The PS2 release joins
# it with the read-only disc inventory (nfl2k5ps2.textures.disc_inventory).
SURFACE_GAMES["textures"] = ("nfl2k5_ps2", "nfl2k5_xbox") + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
# PS2 staged surfaces (each must carry at least one nfl2k5_ps2 row):
SURFACE_GAMES["saves"] = _ESTABLISHED_GAMES + ("ncaa09_ps2",)
# PS2 Phase 2 on-disc writers (each surface carries an nfl2k5ps2.* row):
SURFACE_GAMES["uniforms"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
# PS2 Phase 2 on-disc writers (each surface carries an nfl2k5ps2.* row):
SURFACE_GAMES["audio"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",)
SURFACE_GAMES["menus"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
SURFACE_GAMES["players_rosters"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
# nfl2k5_ps2 rows join these surfaces' coverage rule:
SURFACE_GAMES["gameplay_tuning_sliders"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("nflblitz2002_ps2",)
# madden09_ps2 covers these surfaces (one row each):
SURFACE_GAMES["colors"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
SURFACE_GAMES["scripts_config"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
SURFACE_GAMES["stadiums_fields"] = _ESTABLISHED_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",)
SURFACE_GAMES["scorebug_presentation"] = _LEGACY_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",) + ("nflblitz2002_ps2",)
SURFACE_GAMES["portraits_faces"] = _LEGACY_GAMES + ("madden09_ps2",) + ("ncaa09_ps2",) + ("mvp05_ps2",)
CLASSIFICATIONS = (
    "extract-only",
    "offline-writer-proved",
    "read-only-mapped",
    "runtime-proved",
    "unknown",
    "unsafe/deferred",
)
OPERATIONS = ("export", "inspect", "none", "write")
RUNTIME_STATUSES = (
    "negative",
    "not-applicable",
    "not-tested",
    "partial",
    "visible-proved",
)
GUI_MODES = ("deferred", "edit", "export", "view")
TOP_KEYS = {
    "$schema",
    "capabilities",
    "classification_definitions",
    "games",
    "schema",
    "surfaces",
}
CAPABILITY_KEYS = {
    "backend",
    "classification",
    "evidence",
    "game",
    "gui",
    "id",
    "input_constraints",
    "portme",
    "public_distribution",
    "runtime",
    "selectors",
    "source_container",
    "summary",
    "surface",
    "title",
    "validation_command",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]+$")


class RegistryError(ValueError):
    """A fail-closed registry contract violation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def _exact_keys(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{where}: expected object")
    actual = set(value)
    _require(actual == keys, f"{where}: keys differ: missing={sorted(keys - actual)} extra={sorted(actual - keys)}")
    return value


def _string_list(value: Any, where: str, *, allow_empty: bool = False) -> list[str]:
    _require(isinstance(value, list), f"{where}: expected array")
    if not allow_empty:
        _require(bool(value), f"{where}: must not be empty")
    _require(all(isinstance(item, str) and item for item in value), f"{where}: expected nonempty strings")
    return value


def _local_path(path_text: str, where: str) -> Path:
    _require(not Path(path_text).is_absolute(), f"{where}: local paths must be repository-relative")
    _require(".." not in Path(path_text).parts, f"{where}: parent traversal is forbidden")
    path = ROOT / path_text
    _require(path.is_file(), f"{where}: missing local file {path_text}")
    return path


def _command_module(command: str, where: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise RegistryError(f"{where}: invalid shell-style command: {exc}") from exc
    _require(bool(tokens), f"{where}: empty command")
    for token in tokens:
        if token.startswith("tools/") or token.startswith("mod_editor/"):
            return token
    # Product modules that use package-relative imports must be launched with
    # ``python -m package.module``.  Resolve that spelling to the same
    # repository-relative file identity used by backend.module instead of
    # forcing an unexecutable direct-path command into the registry.
    dotted_module = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"
    )
    for index, token in enumerate(tokens[:-1]):
        if token != "-m":
            continue
        module_name = tokens[index + 1]
        if dotted_module.fullmatch(module_name) is None:
            return None
        module_path = Path(*module_name.split("."))
        candidates = (
            module_path.with_suffix(".py"),
            module_path / "__main__.py",
        )
        for candidate in candidates:
            if (ROOT / candidate).is_file():
                return candidate.as_posix()
        return None
    return None


def validate_data(data: Any, *, check_files: bool = True) -> dict[str, Any]:
    root = _exact_keys(data, TOP_KEYS, "registry")
    _require(root["$schema"] == "registry.schema.json", "registry.$schema: wrong schema path")
    _require(root["schema"] == SCHEMA_ID, "registry.schema: wrong schema id")
    _require(root["surfaces"] == list(SURFACES), "registry.surfaces: must equal the canonical ordered surface list")

    definitions = root["classification_definitions"]
    _require(isinstance(definitions, dict), "classification_definitions: expected object")
    _require(tuple(sorted(definitions)) == tuple(sorted(CLASSIFICATIONS)), "classification_definitions: incomplete enum")
    _require(all(isinstance(value, str) and value for value in definitions.values()), "classification_definitions: empty definition")

    games = root["games"]
    _require(isinstance(games, list) and len(games) == 7, "games: expected exactly seven entries")
    _require([game.get("id") for game in games] == list(GAMES), "games: IDs/order must be canonical")
    for index, game in enumerate(games):
        where = f"games[{index}]"
        _exact_keys(game, {"id", "platform", "public_input", "retail_identity", "title"}, where)
        _require(all(isinstance(game[key], str) and game[key] for key in ("platform", "public_input", "title")), f"{where}: empty string")
        identity = _exact_keys(game["retail_identity"], {"content_sha256", "executable_sha256"}, f"{where}.retail_identity")
        for key, value in identity.items():
            _require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None, f"{where}.retail_identity.{key}: invalid SHA-256")

    capabilities = root["capabilities"]
    _require(isinstance(capabilities, list) and len(capabilities) >= 38, "capabilities: expected at least 38 entries")
    ids: list[str] = []
    coverage: set[tuple[str, str]] = set()
    game_ids = {game["id"] for game in games}

    for index, capability in enumerate(capabilities):
        where = f"capabilities[{index}]"
        _exact_keys(capability, CAPABILITY_KEYS, where)
        cap_id = capability["id"]
        _require(isinstance(cap_id, str) and ID_RE.fullmatch(cap_id) is not None, f"{where}.id: invalid")
        ids.append(cap_id)
        game = capability["game"]
        surface = capability["surface"]
        classification = capability["classification"]
        _require(game in game_ids, f"{where}.game: unknown game")
        _require(surface in SURFACES, f"{where}.surface: unknown surface")
        _require(classification in CLASSIFICATIONS, f"{where}.classification: unknown classification")
        coverage.add((game, surface))
        for key in ("title", "summary"):
            _require(isinstance(capability[key], str) and capability[key], f"{where}.{key}: empty string")
        _string_list(capability["input_constraints"], f"{where}.input_constraints")
        _string_list(capability["portme"], f"{where}.portme")
        evidence = _string_list(capability["evidence"], f"{where}.evidence")
        _require(len(evidence) == len(set(evidence)), f"{where}.evidence: duplicates")
        if check_files:
            for evidence_index, evidence_path in enumerate(evidence):
                _local_path(evidence_path, f"{where}.evidence[{evidence_index}]")

        backend = _exact_keys(capability["backend"], {"command", "module", "operation"}, f"{where}.backend")
        _require(backend["operation"] in OPERATIONS, f"{where}.backend.operation: invalid")
        _require(backend["module"] is None or isinstance(backend["module"], str), f"{where}.backend.module: invalid")
        _require(backend["command"] is None or isinstance(backend["command"], str), f"{where}.backend.command: invalid")
        if backend["operation"] == "none":
            _require(backend["module"] is None and backend["command"] is None, f"{where}.backend: none must have null module/command")
        else:
            _require(bool(backend["module"]) and bool(backend["command"]), f"{where}.backend: active operation needs module/command")
            if check_files:
                _local_path(backend["module"], f"{where}.backend.module")
                command_module = _command_module(backend["command"], f"{where}.backend.command")
                _require(command_module == backend["module"], f"{where}.backend.command: must invoke exact backend module")

        validation = capability["validation_command"]
        _require(validation is None or isinstance(validation, str), f"{where}.validation_command: invalid")
        if classification not in ("unknown", "unsafe/deferred"):
            _require(bool(validation), f"{where}.validation_command: proved/mapped capability needs a validator")
        if validation and check_files:
            module = _command_module(validation, f"{where}.validation_command")
            _require(module is not None, f"{where}.validation_command: no local module")
            _local_path(module, f"{where}.validation_command")

        source = _exact_keys(capability["source_container"], {"format", "hash_pins", "resource", "retail_file"}, f"{where}.source_container")
        for key in ("format", "resource", "retail_file"):
            _require(isinstance(source[key], str) and source[key], f"{where}.source_container.{key}: empty")
        _require(isinstance(source["hash_pins"], list), f"{where}.source_container.hash_pins: expected array")
        _require(all(isinstance(pin, str) and SHA256_RE.fullmatch(pin) for pin in source["hash_pins"]), f"{where}.source_container.hash_pins: invalid SHA-256")
        _require(len(source["hash_pins"]) == len(set(source["hash_pins"])), f"{where}.source_container.hash_pins: duplicate")

        selectors = _exact_keys(capability["selectors"], {"fields", "notes"}, f"{where}.selectors")
        _require(isinstance(selectors["notes"], str) and selectors["notes"], f"{where}.selectors.notes: empty")
        _require(isinstance(selectors["fields"], list), f"{where}.selectors.fields: expected array")
        for field_index, field in enumerate(selectors["fields"]):
            field_where = f"{where}.selectors.fields[{field_index}]"
            _exact_keys(field, {"allowed", "name", "required"}, field_where)
            _require(isinstance(field["allowed"], str) and field["allowed"], f"{field_where}.allowed: empty")
            _require(isinstance(field["name"], str) and field["name"], f"{field_where}.name: empty")
            _require(type(field["required"]) is bool, f"{field_where}.required: expected boolean")

        runtime = _exact_keys(capability["runtime"], {"evidence", "scope", "status"}, f"{where}.runtime")
        _require(runtime["status"] in RUNTIME_STATUSES, f"{where}.runtime.status: invalid")
        _require(isinstance(runtime["scope"], str) and runtime["scope"], f"{where}.runtime.scope: empty")
        runtime_evidence = _string_list(runtime["evidence"], f"{where}.runtime.evidence", allow_empty=True)
        if runtime["status"] == "visible-proved":
            _require(bool(runtime_evidence), f"{where}.runtime.evidence: visible proof needs evidence")
            if check_files:
                for runtime_index, runtime_path in enumerate(runtime_evidence):
                    _local_path(runtime_path, f"{where}.runtime.evidence[{runtime_index}]")

        gui = _exact_keys(capability["gui"], {"default_enabled", "expose", "mode", "reason"}, f"{where}.gui")
        _require(type(gui["default_enabled"]) is bool and type(gui["expose"]) is bool, f"{where}.gui: booleans required")
        _require(gui["mode"] in GUI_MODES, f"{where}.gui.mode: invalid")
        _require(isinstance(gui["reason"], str) and gui["reason"], f"{where}.gui.reason: empty")
        _require(not gui["default_enabled"] or gui["expose"], f"{where}.gui: hidden capability cannot default-enable")

        distribution = _exact_keys(capability["public_distribution"], {"game_data", "mod_payload", "rule", "tooling"}, f"{where}.public_distribution")
        _require(distribution["tooling"] == "source-and-schemas-only", f"{where}.public_distribution.tooling: invalid")
        _require(distribution["game_data"] == "never-bundle-retail-data", f"{where}.public_distribution.game_data: invalid")
        _require(distribution["mod_payload"] in ("metadata-only", "user-authored-inputs-and-recipes", "none-until-safe"), f"{where}.public_distribution.mod_payload: invalid")
        _require(isinstance(distribution["rule"], str) and distribution["rule"], f"{where}.public_distribution.rule: empty")

        expected = {
            "runtime-proved": ("write", "edit"),
            "offline-writer-proved": ("write", "edit"),
            "extract-only": ("export", "export"),
            "read-only-mapped": ("inspect", "view"),
            "unknown": ("none", "deferred"),
            "unsafe/deferred": ("none", "deferred"),
        }[classification]
        _require((backend["operation"], gui["mode"]) == expected, f"{where}: classification/backend/gui mismatch")
        if classification == "runtime-proved":
            _require(runtime["status"] == "visible-proved", f"{where}: runtime-proved needs visible-proved status")
        if classification in ("unknown", "unsafe/deferred"):
            _require(not gui["expose"] and not gui["default_enabled"], f"{where}: deferred capability must stay hidden")

    _require(ids == sorted(ids), "capabilities: IDs must be sorted for deterministic review")
    _require(len(ids) == len(set(ids)), "capabilities: duplicate ID")
    expected_coverage = {
        (game, surface)
        for surface in SURFACES
        for game in SURFACE_GAMES.get(surface, _ESTABLISHED_GAMES)
    }
    _require(coverage == expected_coverage, f"capabilities: incomplete game/surface coverage: missing={sorted(expected_coverage - coverage)}")
    return root


def load_and_validate(path: Path, *, check_files: bool = True, require_canonical: bool = True) -> dict[str, Any]:
    raw = path.read_bytes()
    _require(not path.is_symlink(), f"registry path is a symlink: {path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry JSON parse failed: {exc}") from exc
    validate_data(data, check_files=check_files)
    if require_canonical:
        canonical = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _require(raw == canonical, "registry JSON is not canonical sorted pretty JSON")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--skip-file-checks", action="store_true")
    args = parser.parse_args()
    _require(args.schema.resolve() == DEFAULT_SCHEMA.resolve(), "only the pinned v1 schema is accepted")
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    _require(schema.get("$id") == SCHEMA_DOCUMENT_ID, "schema file has wrong $id")
    data = load_and_validate(args.registry, check_files=not args.skip_file_checks)
    print(
        "MOD_CAPABILITY_REGISTRY_VALIDATION_PASS "
        f"schema={data['schema']} games={len(data['games'])} "
        f"surfaces={len(data['surfaces'])} capabilities={len(data['capabilities'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
