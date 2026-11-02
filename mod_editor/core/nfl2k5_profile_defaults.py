"""Take a build's new default game settings into a saved profile or franchise (b780 b10-profile, bug row D8).

Why this exists.  A fresh profile starts from the defaults inside ``default.xbe`` (b779 df1: 7-minute quarters, a 15-minute
Sim. Quarter Length when the pace fix is in the build, Chop Block on).  A Settings save and every franchise save carry the
whole 0x2E0-byte options block, and the game copies all of it over the live options when it loads one of them
(``FUN_000E2E20`` and its callers, df1 report section 1).  So a profile saved before the new defaults keeps 5 / 5 / off for
ever, and every franchise keeps its own copy.  The game cannot tell a saved 5 that nobody touched from a 5 somebody chose,
and its restore-defaults path only runs inside an online session, so no code in the game can move a saved profile safely
(df1 report section 5).  This module is the explicit, one-time, previewed alternative that runs in Studio on a COPY of a
save: it reads what the save holds, compares it with the defaults the chosen ``default.xbe`` installs
(``nfl2k5_option_defaults``), changes only the settings that still hold the old retail value, leaves everything the player
set himself alone unless he ticks it, and reports every byte it wrote.  Nothing outside the three option dwords changes.

Command line (the Studio's Gameplay > Saves & Sliders page and Franchise > Upgrade use the same code)::

    python3 -m mod_editor.core.nfl2k5_profile_defaults show  SAVEGAME.DAT --xbe default.xbe
    python3 -m mod_editor.core.nfl2k5_profile_defaults apply SAVEGAME.DAT --xbe default.xbe \\
        --out-dat NEW_SAVEGAME.DAT --out-extra NEW_EXTRA [--also quarter_minutes]

``show`` writes nothing.  ``apply`` writes a signed copy (the source is never written) and only the settings that still
hold the old value, plus any named with ``--also``.  Put both new files back into the save's folder together.

Where the three options live.  The block is an image of RAM 0xE5FF80..0xE6025F, so a Settings save (736 bytes) and the first
0x2E0 bytes of a franchise save hold the same dwords at ``va - 0xE5FF80``: Quarter Length 0xE6000C (+0x8C, 1..15), Sim.
Quarter Length 0xE60010 (+0x90, 3..15) and the Chop Block switch 0xE60064 (+0xE4, 0 or 1).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from . import nfl2k5_save_writer as writer

SCHEMA = "nfl2k5_profile_defaults/v1"
BLOCK_VA = writer.OPTION_BLOCK_VA
BLOCK_SIZE = writer.SETTINGS_BLOCK_SIZE
SETTINGS_SAVE_SIZE = writer.SETTINGS_SAVE_SIZE


class ProfileDefaultsError(writer.SaveWriterError):
    """A value is out of range, a save is not a Settings or franchise save, or an edit escaped its dword."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileDefaultsError(message)


@dataclass(frozen=True)
class Option:
    key: str            # the name nfl2k5_option_defaults.settings() uses
    label: str          # what the game's own menu calls it
    va: int
    retail: int         # what the retail game starts with (and what an untouched old save holds)
    low: int
    high: int
    unit: str           # "minutes" or "switch"
    where: str          # where the player finds it

    @property
    def offset(self) -> int:
        return self.va - BLOCK_VA

    def show(self, value: int) -> str:
        if self.unit == "switch":
            return "On" if value == 1 else "Off" if value == 0 else str(value)
        return f"{value} minute{'s' if value != 1 else ''}"


def _option(key: str, label: str, retail: int, unit: str, where: str) -> Option:
    va, low, high = writer.OPTION_FIELDS[key]          # the save writer owns the addresses and ranges
    return Option(key, label, va, retail, low, high, unit, where)


OPTIONS = (
    _option("quarter_minutes", "Quarter Length", 5, "minutes", "Options > Game Options"),
    _option("sim_minutes", "Sim. Quarter Length", 5, "minutes", "Franchise Settings"),
    _option("chop_block", "Chop Block penalty", 0, "switch", "Options > Penalties"),
)
BY_KEY = {option.key: option for option in OPTIONS}
assert set(BY_KEY) == set(writer.OPTION_FIELDS)


def kind(payload) -> str:
    """"settings" for the 736-byte Settings save, "franchise" for anything the save writer reads as a franchise."""
    found = writer.save_kind(bytes(payload))
    _require(found in ("settings", "franchise"),
             f"a save of {len(payload):,} bytes is neither a Settings save (736) nor a franchise save")
    return found


def read_options(payload) -> dict[str, int]:
    """{key: value} of the three options as the save stores them (unsigned 32-bit, not range checked)."""
    _require(len(payload) >= BLOCK_SIZE, "the save is smaller than the 0x2E0-byte options block")
    return writer.read_options(payload)


def build_targets(xbe: bytes) -> dict:
    """What a ``default.xbe`` installs as the defaults of a fresh profile.

    -> {"state": "applied" | "retail" | "foreign", "values": {key: int}}.  A retail executable gives the retail values,
    so nothing in a save looks "old" against it; a foreign one gives no values and nothing is planned."""
    from . import nfl2k5_option_defaults as defaults
    found = defaults.settings(bytes(xbe))
    state = found.get("state", "foreign")
    if state not in ("applied", "retail"):
        return {"state": "foreign", "values": {}}
    return {"state": state, "values": {"quarter_minutes": int(found["quarter_minutes"]),
                                       "sim_minutes": int(found["sim_minutes"]),
                                       "chop_block": int(bool(found["chop_block"]))}}


def explicit_targets(quarter_minutes: int | None = None, sim_minutes: int | None = None,
                     chop_block: bool | None = None) -> dict:
    """Targets typed in by hand (the command line's --quarter / --sim / --chop) in the shape build_targets returns."""
    values = {}
    for key, value in (("quarter_minutes", quarter_minutes), ("sim_minutes", sim_minutes), ("chop_block", chop_block)):
        if value is not None:
            values[key] = int(value)
    check_values(values)
    return {"state": "typed", "values": values}


def check_values(values: Mapping[str, int]) -> None:
    for key, value in values.items():
        _require(key in BY_KEY, f"unknown option {key!r}; expected one of {', '.join(BY_KEY)}")
        option = BY_KEY[key]
        _require(type(value) is int and option.low <= value <= option.high,
                 f"{option.label} must be a whole number from {option.low} to {option.high}"
                 if option.unit == "minutes" else f"{option.label} must be 0 (Off) or 1 (On)")


def plan(payload, targets: Mapping) -> dict:
    """Compare a save with a build's defaults, row by row, without changing anything.

    A row's ``action`` is ``change`` (the save still holds the old retail value and the build starts at another), ``same``
    (already what the build starts at) or ``kept`` (the player set another value, or the save holds a value the game would
    not offer; it stays unless the caller asks for it).  ``target`` is None when the build gives no value."""
    values = dict(targets.get("values") or {})
    check_values(values)
    current = read_options(payload)
    rows = []
    for option in OPTIONS:
        now, target = current[option.key], values.get(option.key)
        valid = option.low <= now <= option.high
        row = {"key": option.key, "label": option.label, "where": option.where, "offset": option.offset,
               "current": now, "retail": option.retail, "target": target, "valid": valid,
               "current_text": option.show(now), "target_text": None if target is None else option.show(target)}
        if target is None:
            row.update(action="kept", note="this build does not say what it starts at")
        elif now == target:
            row.update(action="same", note=f"already {option.show(now)}")
        elif valid and now == option.retail:
            row.update(action="change", note=f"{option.show(now)} is the old default; this build starts at "
                                             f"{option.show(target)}")
        elif not valid:
            row.update(action="kept", note=f"the save holds {now}, which the game's menu cannot set; left alone")
        else:
            row.update(action="kept", note=f"set to {option.show(now)} by the player; left alone")
        rows.append(row)
    changes = [row for row in rows if row["action"] == "change"]
    return {"schema": SCHEMA, "build_state": targets.get("state", "typed"), "block": kind(payload), "rows": rows,
            "changes": len(changes), "kept": [row["key"] for row in rows if row["action"] == "kept"]}


def apply_values(payload: bytearray, values: Mapping[str, int]) -> list[dict]:
    """Write the dwords into a mutable save, in place; -> one row per dword that really changed."""
    check_values(values)
    _require(len(payload) >= BLOCK_SIZE, "the save is smaller than the 0x2E0-byte options block")
    rows = writer.apply_option_edits(payload, dict(values))
    return [{"option": BY_KEY[row["key"]].label, **row} for row in rows]


def edit(payload: bytes, values: Mapping[str, int]) -> tuple[bytes, list[dict]]:
    """A copy of ``payload`` with the dwords written; proves that no other byte of the save moved."""
    out = bytearray(payload)
    rows = apply_values(out, values)
    allowed = {BY_KEY[row["key"]].offset + i for row in rows for i in range(4)}
    for at, (a, b) in enumerate(zip(payload, out)):
        _require(a == b or at in allowed, f"the edit changed byte 0x{at:x} outside its option")
    after = read_options(out)
    _require(all(after[row["key"]] == row["after"] for row in rows), "the options do not read back as written")
    return bytes(out), rows


def values_from_plan(report: Mapping, *, also: tuple[str, ...] = ()) -> dict[str, int]:
    """The values to write for a plan: every ``change`` row, plus the named ``kept`` rows the player ticked."""
    chosen = {}
    for row in report["rows"]:
        if row["target"] is not None and (row["action"] == "change" or row["key"] in also):
            chosen[row["key"]] = row["target"]
    return chosen


def lines(report: Mapping) -> list[str]:
    """Plain-words lines for a dialog, a log or the command line."""
    out = []
    for row in report["rows"]:
        if row["action"] == "change":
            out.append(f"{row['label']}: {row['current_text']} -> {row['target_text']}  ({row['where']})")
        elif row["action"] == "same":
            out.append(f"{row['label']}: {row['current_text']}, already the build's default")
        else:
            out.append(f"{row['label']}: {row['current_text']}, {row['note']}")
    return out


HELP_TEXT = ("A saved profile or franchise keeps the game settings it was saved with, so a new build's default game "
             "settings (7 minute quarters, a 15 minute Sim. Quarter Length with the pace fix, Chop Block on) only reach new "
             "profiles. This copies the defaults your default.xbe starts new profiles with into a copy of your save, for "
             "the settings that still hold the old 5 / 5 / Off. A setting you changed yourself is left alone unless you "
             "tick it. Each franchise keeps its own copy of these settings, so do it for your Settings save and for each "
             "franchise you want.")


def _signed_copy(source: Path, xbe: Path, out_dat: Path, out_extra: Path, values: Mapping[str, int],
                 overwrite: bool) -> dict:
    return writer.edit_save_file(source, out_dat, out_extra, xbe_path=xbe, options=dict(values), overwrite=overwrite)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="list what a save holds against what a default.xbe starts new profiles with")
    apply_ = commands.add_parser("apply", help="write a signed copy of a save with the build's defaults")
    for sub in (show, apply_):
        sub.add_argument("savegame", type=Path, help="a Settings1 or franchise SAVEGAME.DAT (never written)")
        sub.add_argument("--xbe", type=Path, required=True,
                         help="the default.xbe of the build whose defaults to take (also re-signs the copy)")
    apply_.add_argument("--out-dat", type=Path, required=True)
    apply_.add_argument("--out-extra", type=Path, required=True)
    apply_.add_argument("--also", action="append", default=[], choices=sorted(BY_KEY),
                        help="also replace this setting although the player changed it")
    apply_.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = args.savegame.read_bytes()
        targets = build_targets(args.xbe.read_bytes())
        report = plan(payload, targets)
        if args.command == "show":
            print(json.dumps({**report, "lines": lines(report)}, indent=2))
            return 0
        values = values_from_plan(report, also=tuple(args.also))
        if not values:
            print(json.dumps({**report, "lines": lines(report), "written": False,
                              "why": "nothing to change"}, indent=2))
            return 0
        result = _signed_copy(args.savegame, args.xbe, args.out_dat, args.out_extra, values, args.overwrite)
        print(json.dumps({**report, "lines": lines(report), "written": True, "result": result}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"REFUSED: {exc}")
        return 2


__all__ = ["BLOCK_SIZE", "BLOCK_VA", "BY_KEY", "HELP_TEXT", "OPTIONS", "Option", "ProfileDefaultsError", "SCHEMA",
           "apply_values", "build_targets", "check_values", "edit", "explicit_targets", "kind", "lines", "main",
           "plan", "read_options", "values_from_plan"]


if __name__ == "__main__":
    raise SystemExit(main())
