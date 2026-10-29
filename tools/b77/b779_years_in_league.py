#!/usr/bin/env python3
"""Job b779 fh1 (Noah 10/28): years pro = NFL seasons since the player entered the league, for every real player.

Noah: "For years pro, you should just do years in the league. So 16 for Kaepernick. That should apply to everybody."
The stored value counts the season in progress (rookie = 1) whether or not the player was in every one, which is also how
the game's rollover counts and how the Player Card labels its season rows (nfl2k5_roster_records.YEARS_PRO_CONVENTION).
The first year is nflverse's ``entry_year`` (data/nfl2k5_entry_years_2026.v1.json, built by b779_fh1_history_data.py).

  b779_years_in_league.py free-agents  mod_editor/data/nfl2k5_free_agents_2026.v1.json      [--write]
  b779_years_in_league.py depth        mod_editor/data/nfl2k5_free_agent_depth_2026.v1.json [--write]
  b779_years_in_league.py edits        league_roster_edits.json converted.json --base BASE_ROST_OR_PACK0

Data stamped ``game_years_in_league`` is refused (never converted twice); the older ``game_rookie_1`` stamp (nflverse
accrued seasons + 1) or no stamp converts.  The edits command also stamps the document and asks the build for the
created-player season history (``created_history``).  Each command prints the before/after counts.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_created_history as created  # noqa: E402

KEY = "years_pro_convention"
OLD = "game_rookie_1"
DEFAULT_ENTRY = ROOT / "mod_editor" / "data" / "nfl2k5_entry_years_2026.v1.json"
BASE_YEAR = 2026


class ConversionRefused(ValueError):
    pass


def load_entry_years(path: Path = DEFAULT_ENTRY) -> dict[str, int]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != "nfl2k5_entry_years/v1" or document.get(KEY) != rr.YEARS_PRO_CONVENTION:
        raise ConversionRefused("not an entry-year table of this convention")
    return {k: int(v) for k, v in document["entries"].items()}


def years_pro(entry_year: int) -> int:
    return rr.years_pro_for_season(BASE_YEAR, entry_year)


def _refuse_if_converted(document: dict, what: str) -> None:
    if document.get(KEY) == rr.YEARS_PRO_CONVENTION:
        raise ConversionRefused(f"{what} already counts years pro as seasons since entering the NFL; nothing converted")
    if KEY in document and document[KEY] != OLD:
        raise ConversionRefused(f"{what}: unknown {KEY} {document[KEY]!r}")


def _stamp(document: dict) -> None:
    document[KEY] = rr.YEARS_PRO_CONVENTION
    document[KEY + "_note"] = rr.YEARS_PRO_CONVENTION_NOTE


def _tally(pairs) -> dict:
    """pairs of (old, new) -> counts, including the 10-year veteran-cut threshold the retail rollover uses."""
    pairs = list(pairs)
    delta = collections.Counter(new - old for old, new in pairs)
    return {"players": len(pairs), "changed": sum(1 for o, n in pairs if o != n), "raised": sum(1 for o, n in pairs if n > o),
            "lowered": sum(1 for o, n in pairs if n < o), "at_least_10_before": sum(1 for o, _ in pairs if o >= 10),
            "at_least_10_after": sum(1 for _, n in pairs if n >= 10), "delta": dict(sorted(delta.items()))}


def convert_rows(document: dict, rows_key: str, entry: dict[str, int], what: str) -> tuple[dict, dict]:
    """Free-agent data: ``fields.years_pro`` of every row in ``document[rows_key]`` from the entry table."""
    _refuse_if_converted(document, what)
    out = json.loads(json.dumps(document))
    pairs, missing = [], []
    for row in out[rows_key]:
        fields = row.get("fields")
        if not fields or "years_pro" not in fields:
            continue
        year = entry.get(row.get("gsis_id"))
        if year is None:
            missing.append(row.get("name") or row.get("gsis_id"))
            continue
        new = years_pro(year)
        pairs.append((fields["years_pro"], new))
        fields["years_pro"] = new
    if missing:
        raise ConversionRefused(f"{what}: no entry year for {len(missing)} rows ({missing[:5]})")
    _stamp(out)
    return out, _tally(pairs)


def read_base_body(path: Path) -> bytes:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from f12_convert_data import read_base_body as read          # the pack-0 / bare body reader
    return read(path)


def convert_edits(document: dict, base_body: bytes, entry: dict[str, int]) -> tuple[dict, dict]:
    """Roster-edits document: years pro of every GSIS-identified player the document touches.

    Existing records (the league edits and the refresh's retained players) are corrected by an edit entry; edits are sparse,
    so the document is first applied to ``base_body`` and only a player whose result differs from the entry-year value
    gets a new or changed entry.  The refresh's NEW players are created from zero by the refresh, so their ``fields.years_pro``
    is rewritten in place.  The result is proved by applying it again and comparing every record."""
    _refuse_if_converted(document, "the roster-edits document")
    out = json.loads(json.dumps(document))
    generated = {"franchise_history", "modern_free_agents", "restore_historic_spare_capacity", "roster_refresh",
                 "free_agent_capacity", "fa3_free_agent_depth", "created_history"}
    # the old document is applied only to read the current values, so its own (refused) stamp is left off
    old_body, old_receipt = rr.apply_body(base_body, {k: v for k, v in document.items() if k not in generated and k != KEY})
    old_doc = rr.RosterDocument(old_body, scheme="one_pool", reference_year=2026)
    current = {(p.pool, p.index): p.record.values["years_pro"] for p in old_doc.players}
    vacant = {(p.pool, p.index) for p in old_doc.players if p.first.startswith("****")}
    identified: dict[tuple[str, int], tuple[str, str, str]] = {}
    for p in document.get("franchise_history", {}).get("players", ()):
        identified[(p["pool"], p["index"])] = (p["gsis_id"], p["first"], p["last"])
    refresh = document.get("roster_refresh", {}).get("players", ())
    for p in refresh:
        if not p.get("new"):
            identified.setdefault((p.get("pool", "primary"), p["index"]), (p["gsis_id"], p["first"], p["last"]))
    last_entry: dict[tuple[str, int], dict] = {}
    for item in out.get("edits", ()):
        if "years_pro" in (item.get("fields") or {}):
            last_entry[(str(item.get("pool", "primary")), int(item["index"]))] = item
    pairs, updated, appended, missing = [], 0, 0, []
    created_later = 0
    for key, (gsis, first, last) in sorted(identified.items()):
        if key in vacant:                  # a dated free agent: the free-agent data (converted by its own command) writes it
            created_later += 1
            continue
        year = entry.get(gsis)
        if year is None:
            missing.append(f"{first} {last}")
            continue
        new, old = years_pro(year), current.get(key)
        if old is None:
            raise ConversionRefused(f"{first} {last}: no base record at {key}")
        pairs.append((old, new))
        if old == new:
            continue
        item = last_entry.get(key)
        if item is not None:
            item["fields"]["years_pro"] = new
            updated += 1
        else:
            out["edits"].append({"pool": key[0], "index": key[1], "first": first, "last": last, "fields": {"years_pro": new}})
            appended += 1
    new_pairs = []
    for p in out.get("roster_refresh", {}).get("players", ()):
        if p.get("new"):
            year = entry.get(p["gsis_id"])
            if year is None:
                missing.append(f"{p['first']} {p['last']}")
                continue
            new = years_pro(year)
            new_pairs.append((p["fields"]["years_pro"], new))
            p["fields"]["years_pro"] = new
    if missing:
        raise ConversionRefused(f"no entry year for {len(missing)} players ({missing[:5]})")
    _stamp(out)
    out["created_history"] = created.DATA_VERSION
    new_body, new_receipt = rr.apply_body(base_body, {k: v for k, v in out.items() if k not in generated})
    if new_receipt["log"] != old_receipt["log"]:
        extra = [line for line in new_receipt["log"] if line not in set(old_receipt["log"])]
        raise ConversionRefused(f"the converted document logs differently ({len(extra)} new lines, e.g. {extra[:2]})")
    before = {(p.pool, p.index): p for p in old_doc.players}
    after = {(p.pool, p.index): p for p in rr.RosterDocument(new_body, scheme="one_pool", reference_year=2026).players}
    for key, player in before.items():
        a, b = dict(player.record.values), dict(after[key].record.values)
        if key in identified and key not in vacant and identified[key][0] in entry:
            if b["years_pro"] != years_pro(entry[identified[key][0]]):
                raise ConversionRefused(f"{player.display}: years pro {b['years_pro']} after conversion")
            a["years_pro"] = b["years_pro"]
        if a != b:
            raise ConversionRefused(f"{player.display}: another field changed in the conversion")
    report = {"existing_records": _tally(pairs), "new_refresh_players": _tally(new_pairs),
              "entries_updated": updated, "entries_appended": appended, "skipped_created_later": created_later}
    return out, report


def raw_ascii(text: str) -> bool:
    return all(ord(c) < 128 for c in text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("free-agents", "depth"):
        sp = sub.add_parser(name)
        sp.add_argument("path", type=Path)
        sp.add_argument("--entry", type=Path, default=DEFAULT_ENTRY)
        sp.add_argument("--write", action="store_true")
    ed = sub.add_parser("edits")
    ed.add_argument("source", type=Path)
    ed.add_argument("output", type=Path)
    ed.add_argument("--base", type=Path, required=True, help="the roster the document was built on: a ROST body or pack 0")
    ed.add_argument("--entry", type=Path, default=DEFAULT_ENTRY)
    args = parser.parse_args()
    try:
        entry = load_entry_years(args.entry)
        if args.command in ("free-agents", "depth"):
            document = json.loads(args.path.read_text(encoding="utf-8"))
            key = "added" if args.command == "free-agents" else "players"
            out, report = convert_rows(document, key, entry, f"the {args.command} data")
            if args.write:
                text = args.path.read_text(encoding="utf-8")
                indent = len(text.split("\n", 2)[1]) - len(text.split("\n", 2)[1].lstrip())    # keep the file's own layout
                args.path.write_text(json.dumps(out, indent=indent, ensure_ascii=raw_ascii(text)) + "\n", encoding="utf-8", newline="\n")
        else:
            if args.output.exists():
                parser.error("output exists; choose a fresh path")
            out, report = convert_edits(json.loads(args.source.read_text(encoding="utf-8")), read_base_body(args.base), entry)
            args.output.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    except ConversionRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
