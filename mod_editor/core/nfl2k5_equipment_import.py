"""Preflight the complete equipment TSET before one undoable Studio import.

Which package copy the game samples decides where an import has to go
(``nfl2k5_uniform_equipment_writer.consumer_targets``).  Team-coloured
variants are package-local.  Generic variants -- Style 1/2/4/5 shoes, gloves
1-4, elbow pads 1-4, long sleeves 1-2, wristbands 1-2 -- are one league-wide
texture at runtime: the executable binds the copy inside the most recently
loaded uniform package (the away team's package in a game, the viewed team's
``h0``/``a0`` package on the Edit Player screen).  Staging one package only
ever reached the Edit Player preview, so a generic variant is staged, as one
undoable transaction, into every package the game can sample it from.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile
from typing import Any

from .errors import ValidationError
from .nfl2k5_equipment_import_intent import (
    retail_source, same_visual_import, with_import_mode, with_retail_source,
)


CONSUMER_SCHEMA = "nfl2k5_equipment_consumer_fanout/v1"
GLOBAL_RULE = (
    "All teams share this style because the game reads its texture from the most recently loaded uniform package."
)
CONTEXT_FIRST_RULE = (
    "Native lookup checks the selected HOME/AWAY package, with separate clean and dirty artwork. "
    "A missing local texture falls back to the newest loaded package. In-game outcome UNWITNESSED.")
from .nfl2k5_equipment_import_intent import SHOE_ROUTE_HELP as PACKAGE_LOCAL_SHOE_HELP
ALL_TEAMS = "all-teams"
SELECTED_PACKAGE = "selected-package"


def equipment_import_scope(asset_id: str) -> tuple[tuple[tuple[str, str], ...], str]:
    """The dialog and non-GUI callers use the same reviewed scope contract."""
    from .nfl2k5_uniform_equipment_writer import in_game_lookup, load_targets

    target = load_targets()[0].get(asset_id)
    if target is None:
        raise ValidationError("Choose a reviewed equipment texture.")
    if in_game_lookup(target.name) == "global":
        return ((ALL_TEAMS, "All teams"),), GLOBAL_RULE
    return ((SELECTED_PACKAGE, "Selected uniform package"),), CONTEXT_FIRST_RULE


@dataclass(frozen=True)
class EquipmentImportResult:
    message: str
    receipt: dict[str, Any]
    changed_asset_ids: tuple[str, ...]
    modified: bool
    consumer_asset_ids: tuple[str, ...] = ()


def _package_counts(consumers: Any) -> dict[str, int]:
    away = sum(1 for item in consumers if item.set_selector[2:3] == "A")
    home_current = sum(1 for item in consumers if item.set_selector[2:] == "H0")
    return {"away": away, "home_current": home_current,
            "selected_only": len(consumers) - away - home_current}


def _consumer_receipt(target: Any, consumers: Any, staged: tuple[str, ...]) -> dict[str, Any]:
    from .nfl2k5_uniform_equipment_writer import BINDING_TABLE_ROWS, in_game_lookup

    lookup = in_game_lookup(target.name)
    base = target.name[:-4] if target.name.endswith("_mud") else target.name
    return {
        "schema": CONSUMER_SCHEMA,
        "selected_asset_id": target.asset_id,
        "name": target.name,
        "in_game_lookup": lookup,
        "rule": GLOBAL_RULE if lookup == "global" else CONTEXT_FIRST_RULE,
        "xbe_evidence": {
            "binding_table": "0x004EEAF8",
            "row": BINDING_TABLE_ROWS[base],
            "context_first": int(lookup == "context_first"),
            "lookup": ("FUN_0008E580 -> FUN_000449E0(0, 'TXTR', name): newest loaded context wins"
                       if lookup == "global" else
                       "FUN_0008E580 -> FUN_000449E0(HOME/AWAY, 'TXTR', name)"),
            "game_load_order": "FUN_00062BE0 creates HOME at 0x0006327A, then AWAY at 0x00063298",
            "front_end_preview": "FUN_00091940 loads <code>h0.iff or <code>a0.iff alone",
        },
        "package_counts": _package_counts(consumers),
        "consumer_asset_ids": [item.asset_id for item in consumers],
        "staged_asset_ids": list(staged),
    }


def _message(target: Any, consumers: Any, *, independent: bool,
             encoded: str, approximation: str, changed: bool) -> str:
    from .nfl2k5_uniform_equipment_writer import in_game_lookup

    count = len(consumers)
    if in_game_lookup(target.name) == "global":
        counts = _package_counts(consumers)
        where = (
            f"{count} uniform packages ({counts['away']} away, {counts['home_current']} home Current Uniform"
            + (f", {counts['selected_only']} selected only" if counts["selected_only"] else "") + ")"
        )
        scope = (f"In a game every player wearing this style uses the away team's package copy, "
                 f"so it was staged into all {where}.")
    else:
        scope = "This variant is read from each team's own package, so only this package changed."
    if not changed:
        return "Equipment artwork and its import choice already match the project."
    if independent:
        return (f"Equipment artwork is ready to build at {encoded}.{approximation} "
                f"Experimental / unwitnessed. {scope}")
    return f"Equipment recolour is ready to build.{approximation} {scope}"


def stage_equipment_import(session, asset, path, *, independent=None, scale=1, scope=None):
    from .equipment_staging import stage_equipment_import as stage
    return stage(session, asset, path, independent=independent, scale=scale, scope=scope)


def revert_equipment_import(session, asset):
    from .equipment_staging import revert_equipment_import as revert
    return revert(session, asset)
