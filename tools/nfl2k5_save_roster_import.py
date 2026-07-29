#!/usr/bin/env python3
"""Bring the names out of a PS2 save and into a 2K5 disc project.

Somebody with a season's worth of edited names on a memory card had no way to
get them onto a disc. Reading a save has worked for a while and writing disc
text has worked for a while; nothing joined them, so the only route was
retyping several hundred names by hand.

This reads the ROST arena out of a ``.psu`` or an extracted save directory and
emits a ``nfl2k5_visual_mod_project/v1`` project containing one text edit per
name, which Build Modded XISO already knows how to apply.

Two limits, both real and both stated rather than worked around:

* **Names only.** A save's ROST arena and the disc's ROST resource are the same
  format, but this lane carries the fixed-allocation name strings and nothing
  else. Ratings, jersey numbers and team assignments are separate proved lanes
  with their own writers, and pretending one importer covers them would produce
  a project that fails validation several steps later.
* **Fixed allocation.** Every name lives in a byte span the disc will not grow.
  A name that is longer than its slot is reported and skipped rather than
  truncated, because a silently shortened name is worse than an obvious refusal
  -- the modder can shorten it themselves and know what they chose.

    python3 tools/nfl2k5_save_roster_import.py \\
        --save BASLUS-209192K5Roster --project imported_names.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import nfl2k5_ps2_save as ps2  # noqa: E402


PROJECT_SCHEMA = "nfl2k5_visual_mod_project/v1"
IMPORT_SCHEMA = "nfl2k5_save_roster_import/v1"
# The disc-side text asset id shape the unified build validates.
FIELD_NAMES = ("first", "last")


class SaveImportError(ValueError):
    """Raised when a save cannot become a project the build would accept."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveImportError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_save_names(save_path: Path) -> list[dict[str, Any]]:
    """Every primary-player name slot in the save, with its capacity."""
    resolved = Path(save_path).expanduser()
    require(resolved.exists(), f"save is missing: {resolved}")
    try:
        save = ps2.load_save(resolved)
    except AttributeError:  # pragma: no cover - defensive, API is stable
        raise SaveImportError("the PS2 save reader changed shape") from None
    except Exception as exc:  # noqa: BLE001 - the reader raises broadly
        raise SaveImportError(f"could not read {resolved.name}: {exc}") from exc

    slots = list(ps2.player_name_slots(save))
    require(slots, "this save carries no primary player name slots")
    rows: list[dict[str, Any]] = []
    for slot in slots:
        field = str(slot["field"])
        if field not in FIELD_NAMES:
            continue
        rows.append({
            "player": int(slot["player"]),
            "field": field,
            "value": str(slot["value"]),
            "capacity_bytes": int(slot["capacity_bytes"]),
        })
    return rows


def build_project(
    rows: list[dict[str, Any]],
    text_asset_id: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Turn save names into project edits, and report what was skipped.

    ``text_asset_id`` maps ``(player_index, field)`` to a disc text asset id.
    Without one the project cannot name its targets, so the caller supplies it
    from a loaded source; this keeps the importer free of any assumption about
    how the disc numbers its own roster.
    """
    require(callable(text_asset_id),
            "a text_asset_id resolver is required; load the disc first so the "
            "importer can name the targets it is writing to")
    edits: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        value = row["value"].strip()
        if not value:
            continue
        asset_id = text_asset_id(row["player"], row["field"])
        if asset_id is None:
            skipped.append({**row, "reason": "no matching player on this disc"})
            continue
        encoded = len(value.encode("utf-16-le"))
        if encoded > row["capacity_bytes"]:
            # A truncated name is worse than a refusal: the modder never sees
            # what the game will actually show until it is on the disc.
            skipped.append({
                **row,
                "reason": (
                    f"{encoded} bytes will not fit the "
                    f"{row['capacity_bytes']}-byte slot"
                ),
            })
            continue
        edits.append({
            "kind": "universal_fixed_text",
            "selector": str(asset_id),
            "text": value,
        })
    require(edits, "no name from this save could be applied to this disc")
    project = {
        "edits": edits,
        "purpose": "Roster names imported from a PS2 memory-card save.",
        "schema": PROJECT_SCHEMA,
    }
    return project, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", required=True, type=Path,
                        help="a .psu file or an extracted BASLUS-20919* folder")
    parser.add_argument("--names", type=Path,
                        help="write the names as JSON instead of a project")
    args = parser.parse_args()
    try:
        rows = read_save_names(args.save)
    except SaveImportError as exc:
        print(f"nfl2k5_save_roster_import: {exc}", file=sys.stderr)
        return 2
    payload = (json.dumps({
        "schema": IMPORT_SCHEMA,
        "source": {"name": Path(args.save).name},
        "names": rows,
        "summary": {"slot_count": len(rows)},
    }, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.names:
        destination = args.names.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        print(json.dumps({"names": str(destination), "slots": len(rows),
                          "sha256": _digest(payload)}, sort_keys=True))
        return 0
    for row in rows:
        print(f"{row['player']:>5} {row['field']:<5} "
              f"cap={row['capacity_bytes']:<4} {row['value']!r}")
    print(f"{len(rows)} name slot(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
