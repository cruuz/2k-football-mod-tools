"""Hash-pinned, read-only camera-options inspection.

The research report carries executable addresses. This public-editor layer
projects only what a modder can act on -- the named settings, their stored type
and shipped range, the named presets and their geometry, and an honest statement
of why nothing here is writable. It never returns a raw address, never opens a
game binary, and never opens a save.

The one thing it deliberately does say out loud is the boundary: on both titles
the camera lives behind a signature, and the gameplay camera has no asset-side
representation at all, so no archive-only mod can reach it. That negative is
worth publishing, because it is the mod people keep trying to build.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAMERA_REPORT = ROOT / "reports/gameplay_tuning/camera_options_audit.json"
CAMERA_REPORT_SCHEMA = "vc_camera_options_audit/v1"

#: The shipped product snapshot. The raw audit lives under ``reports/`` and is
#: deliberately private -- the release gate refuses any ``reports/`` path -- so a
#: packaged build carries this sanitized projection instead. When both are
#: present the snapshot must agree with a fresh projection, which is what keeps
#: it from going stale.
DEFAULT_CAMERA_SNAPSHOT = ROOT / "mod_editor/data/camera_options_inspection.v1.json"
CAMERA_SNAPSHOT_SCHEMA = "mod_editor_camera_options_snapshot/v1"

GAME_NAMES = {"nfl2k5": "ESPN NFL 2K5", "apf2k8": "All-Pro Football 2K8"}
GAME_PLATFORMS = {"nfl2k5": "original Xbox", "apf2k8": "Xbox 360"}
_SECTIONS = {"nfl2k5": "nfl2k5", "apf2k8": "apf2k8"}


def _require_game(game: str) -> str:
    key = str(game).strip().lower()
    if key not in _SECTIONS:
        raise ValidationError(
            "Camera inspection game must be nfl2k5 or apf2k8."
        )
    return key


def _report(path: Path = DEFAULT_CAMERA_REPORT) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValidationError(f"Camera options report is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Camera options report is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != CAMERA_REPORT_SCHEMA:
        raise ValidationError("Camera options report schema mismatch")
    return value


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    """One setting, with every executable address removed."""

    public: dict[str, Any] = {
        "name": row.get("label"),
        "control": {5: "toggle", 7: "choice", 4: "slider"}.get(row.get("kind"), "unknown"),
        "stored_type": row.get("stored_type"),
        "stock_minimum": row.get("minimum"),
        "stock_maximum": row.get("maximum"),
    }
    if row.get("stored_type") == "float32":
        low, high = row.get("minimum"), row.get("maximum")
        # Height is world units and Distance is a bare multiplier; only Angle
        # and Pitch use the 0..1 convention. Saying so stops a panel from
        # drawing all three as one kind of bar.
        public["normalised_0_to_1"] = low == 0.0 and high == 1.0
    return public


def _snapshot(path: Path = DEFAULT_CAMERA_SNAPSHOT) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Camera snapshot is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != CAMERA_SNAPSHOT_SCHEMA:
        raise ValidationError("Camera snapshot schema mismatch")
    return value


def inspect_camera_options(
    game: str,
    path: Path = DEFAULT_CAMERA_REPORT,
    snapshot_path: Path = DEFAULT_CAMERA_SNAPSHOT,
) -> dict[str, Any]:
    """Return the sanitized, read-only camera surface for one game.

    Derives from the private audit when it is present -- a maintainer checkout --
    and falls back to the shipped snapshot in a packaged build, which has no
    ``reports/`` tree at all. When both exist the two must agree.
    """

    key = _require_game(game)
    if not path.is_file():
        shipped = _snapshot(snapshot_path)
        if shipped is None:
            raise ValidationError(
                f"Camera options data is missing: neither {path} nor {snapshot_path}"
            )
        value = shipped.get(key)
        if not isinstance(value, dict):
            raise ValidationError(f"Camera snapshot has no {key} section")
        return value
    report = _report(path)
    section = report.get(_SECTIONS[key])
    if not isinstance(section, dict):
        raise ValidationError(f"Camera options report has no {key} section")

    rows = [row for row in section.get("rows", []) if isinstance(row, dict)]
    presets = [p for p in section.get("presets", []) if isinstance(p, dict)]
    reachable = section.get("menu_reachable_preset_count", len(presets))

    public_presets = []
    for preset in presets:
        entry = {
            "name": preset.get("name"),
            "menu_reachable": int(preset.get("index", 0)) < int(reachable),
        }
        if "position" in preset:
            entry["position"] = preset["position"]
        if "slot0_eye" in preset:
            entry["eye"] = preset["slot0_eye"]
        if preset.get("authored") is not None:
            entry["fully_authored"] = bool(preset["authored"])
        public_presets.append(entry)

    hidden = [p["name"] for p in public_presets if not p["menu_reachable"]]

    return {
        "schema": "mod_editor_camera_options_inspection/v1",
        "game": GAME_NAMES[key],
        "platform": GAME_PLATFORMS[key],
        "read_only": True,
        "setting_count": len(rows),
        "settings": [_public_row(row) for row in rows],
        "preset_count": len(public_presets),
        "menu_reachable_preset_count": int(reachable),
        "presets": public_presets,
        "presets_present_but_not_selectable": hidden,
        "float_settings_apply_only_in_custom": bool(
            section.get("float_settings_apply_only_in_custom", True)
        ),
        "writer_available": False,
        "why_read_only": section.get("writer_boundary", ""),
        "archive_only_mod_possible": False,
        "archive_only_mod_note": (
            "The gameplay camera has no asset-side representation in either "
            "game. Every camera node in both archives belongs to an intro, "
            "cutscene, menu or model-preview scene, and no stadium scene "
            "contains one, so editing archive files cannot change a camera "
            "setting or preset."
        ),
        "runtime_behaviour_proved": False,
        "runtime_note": (
            "Every value here was read from the game's own executable. Nothing "
            "was observed running, and no claim is made about what any of it "
            "looks like on screen."
        ),
    }


def build_snapshot(path: Path = DEFAULT_CAMERA_REPORT) -> dict[str, Any]:
    """The shipped projection for every game, derived from the private audit."""

    return {
        "schema": CAMERA_SNAPSHOT_SCHEMA,
        **{game: inspect_camera_options(game, path) for game in sorted(_SECTIONS)},
    }


__all__ = [
    "CAMERA_REPORT_SCHEMA",
    "CAMERA_SNAPSHOT_SCHEMA",
    "DEFAULT_CAMERA_REPORT",
    "DEFAULT_CAMERA_SNAPSHOT",
    "build_snapshot",
    "inspect_camera_options",
]
