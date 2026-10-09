#!/usr/bin/env python3
"""Job f12 (beta 77): move generated roster data from nflverse years_exp (rookie 0) to the game's years pro (rookie 1).

The game stores years pro with a rookie as 1 and prints R for that value (nfl2k5_roster_records.years_pro_from_years_exp
has the rule and the proof).  The 2026 league, free-agent and Anniversary builders wrote nflverse ``years_exp`` as it
came.  Their generators are fixed; this tool converts data files that were produced earlier, once, and stamps them
(``years_pro_convention`` = ``game_rookie_1``) so a second run refuses instead of adding another year.

  f12_convert_data.py free-agents  mod_editor/data/nfl2k5_free_agents_2026.v1.json            [--write]
  f12_convert_data.py edits        league_roster_edits.json  converted.json  --base BASE_ROST_OR_PACK0

Without ``--write`` the file command only reports what it would change.  The 50 Anniversary team-season CSVs are not
converted here: they are the output of ``tools/nfl2k5_espn25_more_moments_build.py`` (``--check`` regenerates them byte for
byte from the pinned nflverse files), and that builder carries the fix, including the entry-year fallback for the six team
seasons whose nflverse roster files have no ``years_exp``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

CONVENTION_KEY = "years_pro_convention"
CONVENTION = "game_rookie_1"
NOTE = "years pro counts the season in progress (rookie = 1, the card prints R): nflverse years_exp (rookie = 0) plus 1"


class ConversionRefused(ValueError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _refuse_if_converted(document: dict, what: str) -> None:
    if document.get(CONVENTION_KEY) == CONVENTION:
        raise ConversionRefused(f"{what} is already in the game's years pro convention ({CONVENTION}); nothing converted")
    if CONVENTION_KEY in document:
        raise ConversionRefused(f"{what}: unknown {CONVENTION_KEY} {document[CONVENTION_KEY]!r}")


def convert_free_agents(document: dict) -> tuple[dict, dict]:
    """+1 on every added free agent's ``fields.years_pro`` (existing rows only carry appearance and keep the roster's)."""
    _refuse_if_converted(document, "the free-agent data")
    out = json.loads(json.dumps(document))
    changed = 0
    for row in out.get("added", ()):
        fields = row.get("fields", {})
        if "years_pro" in fields:
            fields["years_pro"] = rr.years_pro_from_years_exp(fields["years_pro"])
            changed += 1
    out[CONVENTION_KEY] = CONVENTION
    out[CONVENTION_KEY + "_note"] = NOTE
    return out, {"added_rows_converted": changed}


def _identity(player) -> tuple:
    v = player.record.values
    return (player.first, player.last, v["birth_month"], v["birth_day"], v["birth_year_low"], v["birth_year_high"])


def authored_players(base_body: bytes, result_body: bytes) -> list:
    """The primary NFL players a document wrote (identity differs from the base record); vacant slots and the draft class
    are not players it authored."""
    base = rr.RosterDocument(base_body, scheme="one_pool", reference_year=2026)
    result = rr.RosterDocument(result_body, scheme="one_pool", reference_year=2026)
    base_by = {(p.pool, p.index): p for p in base.players}
    found = []
    for player in result.players:
        if player.pool != "primary" or player.group == "draft_class" or player.first.startswith("****"):
            continue
        if not player.record.values["player_type"] & rr.FLAG_NFL_PLAYER:
            continue
        if _identity(base_by[(player.pool, player.index)]) != _identity(player):
            found.append(player)
    return found


def convert_edits(document: dict, base_body: bytes) -> tuple[dict, dict]:
    """+1 on the years pro of every player a league roster-edits document authors (it was built from nflverse).

    Edits are sparse: a field equal to the base record is not written, so a 2025 draftee whose base slot already held
    1 has no ``years_pro`` entry at all.  The old document is therefore applied to ``base_body`` first; each authored
    player's years pro is read from that result and written back as result + 1 (into his last ``years_pro`` entry, or a
    new final entry when he has none).  The conversion is proved by applying the new document and comparing."""
    _refuse_if_converted(document, "the roster-edits document")
    out = json.loads(json.dumps(document))
    # These later generators already use rookie=1 in current Studio source.
    # Convert only the frozen league edits. Including the free-agent generator
    # would count its new identities as old authored players, double-convert
    # experience and append edits for names that do not exist until that pass.
    generated = {"franchise_history", "modern_free_agents", "restore_historic_spare_capacity"}
    old_body, old_receipt = rr.apply_body(base_body, {k: v for k, v in document.items() if k not in generated})
    players = authored_players(base_body, old_body)
    last_entry: dict[tuple[str, int], dict] = {}
    for entry in out.get("edits", ()):
        if "years_pro" in (entry.get("fields") or {}):
            last_entry[(str(entry.get("pool", "primary")), int(entry["index"]))] = entry
    updated = appended = 0
    for player in players:
        new = rr.years_pro_from_years_exp(player.record.values["years_pro"])
        entry = last_entry.get((player.pool, player.index))
        if entry is not None:
            entry["fields"]["years_pro"] = new
            updated += 1
        else:
            out["edits"].append({"pool": player.pool, "index": player.index, "first": player.first, "last": player.last,
                                 "fields": {"years_pro": new}})
            appended += 1
    out[CONVENTION_KEY] = CONVENTION
    out[CONVENTION_KEY + "_note"] = NOTE
    new_body, new_receipt = rr.apply_body(base_body, {k: v for k, v in out.items() if k not in generated})
    if new_receipt["log"] != old_receipt["log"]:
        raise ConversionRefused(f"the converted document logs differently ({new_receipt['log'][:1]})")
    before = {(p.pool, p.index): p for p in rr.RosterDocument(old_body, scheme="one_pool", reference_year=2026).players}
    after = {(p.pool, p.index): p for p in rr.RosterDocument(new_body, scheme="one_pool", reference_year=2026).players}
    authored = {(p.pool, p.index) for p in players}
    for key, player in before.items():
        a, b = dict(player.record.values), dict(after[key].record.values)
        if key in authored:
            if b["years_pro"] != min(rr.YEARS_PRO_MAX, a["years_pro"] + 1):
                raise ConversionRefused(f"{player.display}: converted years pro {b['years_pro']} from {a['years_pro']}")
            a["years_pro"] = b["years_pro"]
        if a != b:
            raise ConversionRefused(f"{player.display}: another field changed in the conversion")
    return out, {"authored_players": len(players), "entries_updated": updated, "entries_appended": appended}


def read_base_body(path: Path) -> bytes:
    """A bare ROST body, or the main roster of an extracted vc_53450030/0 (outer entry 5)."""
    import struct
    raw = Path(path).read_bytes()
    if len(raw) < 8_000_000 and raw[0x0C:0x10] == b"ROST":
        return raw
    _name, size, blocks = struct.unpack_from("<3I", raw, 0x9C + 5 * 12)
    resource = raw[blocks * 0x800:blocks * 0x800 + size]
    if resource[:4] != b"ROST":
        raise ConversionRefused("the base is neither a ROST body nor a pack 0 with the main roster at outer entry 5")
    return resource[rr.RESOURCE_HEADER_SIZE:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    fa = sub.add_parser("free-agents")
    fa.add_argument("path", type=Path)
    fa.add_argument("--write", action="store_true")
    ed = sub.add_parser("edits")
    ed.add_argument("source", type=Path)
    ed.add_argument("output", type=Path)
    ed.add_argument("--base", type=Path, required=True, help="the roster the document was built on: a ROST body or pack 0")
    args = parser.parse_args()
    try:
        if args.command == "free-agents":
            document = json.loads(args.path.read_text(encoding="utf-8"))
            out, report = convert_free_agents(document)
            if args.write:
                args.path.write_text(json.dumps(out, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
        else:
            if args.output.exists():
                parser.error("output exists; choose a fresh path")
            out, report = convert_edits(json.loads(args.source.read_text(encoding="utf-8")), read_base_body(args.base))
            args.output.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    except ConversionRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
