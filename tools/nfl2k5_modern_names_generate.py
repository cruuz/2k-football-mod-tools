#!/usr/bin/env python3
"""Generate ``data/nfl2k5_modern_names.csv``: the modern generated-player name pool for ESPN NFL 2K5
(tier B of the 2026-09-04 draft-prospect-names study) from nflverse-data's ``players.parquet``
(https://github.com/nflverse/nflverse-data, CC-BY-4.0).

The retail pool (``nfl2k5_prospect_names.RETAIL_FIRSTS`` / ``RETAIL_LASTS``) is 485 first names and
485 surnames drawn independently by the rookie / free-agent generator; the commentary bank is
indexed by surname position, so a surname that stays at its index keeps its call-out.  This tool:

* counts first names and surnames over every nflverse player with a season in
  ``--first-season..--last-season`` (2015-2025: 8,258 players), ASCII-folded (NFKD, accents dropped);
* keeps every retail surname that is neither Hispanic-origin (the 1990 Census list the study flagged:
  49 entries) nor a developer name (Horsley, Hamre, Zdyrko) at its retail index -> 433 retained
  call-outs; the other 52 slots take the most frequent modern surnames the recorded bank does not
  know, in frequency order;
* replaces every first name with the 485 most frequent modern first names (ASCII letters plus
  ``' - .``, at most 12 characters);
* fits the pool's 13,238-byte in-place budget from the bottom of the ranking: the least frequent
  picks are swapped, one by one, for the best-ranked spare name that is shorter, until the UTF-16
  total fits (the top of the ranking is never touched).

Rows are ``index,first,last,audio`` (``audio`` = ``retail`` when the surname keeps its recorded
call-out, ``number`` when the announcer will use the jersey number).  Deterministic for a given
parquet: ties in frequency are broken alphabetically.  Needs pyarrow (``uv run --with pyarrow``).

usage: nfl2k5_modern_names_generate.py [--players players.parquet] [--out CSV] [--first-season 2015] [--last-season 2025]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import os
import sys
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_prospect_names as pn  # noqa: E402

PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet"
DEFAULT_CACHE = Path(os.environ.get("NFL2K5_NFLVERSE_CACHE", Path.home() / ".cache" / "nfl2k5-team-history"))
DEFAULT_OUT = pn.SHIPPED_CSV

# 1990 Census surname-list entries of Hispanic origin in the retail pool (the study's list, 49) and the
# three developer names spliced into the Census rank order: these slots take modern surnames.
HISPANIC_RETAIL_SURNAMES = frozenset({
    "Garcia", "Martinez", "Rodriguez", "Lopez", "Sanchez", "Rivera", "Torres", "Ramirez", "Flores", "Cruz", "Ortiz",
    "Gomez", "Morales", "Ramos", "Reyes", "Ruiz", "Chavez", "Alvarez", "Romero", "Mendoza", "Moreno", "Medina", "Silva",
    "Vargas", "Herrera", "Soto", "Jimenez", "Castro", "Pena", "Mendez", "Santiago", "Guzman", "Munoz", "Valdez", "Salazar",
    "Santos", "Delgado", "Aguilar", "Vega", "Ortega", "Guerrero", "Estrada", "Sandoval", "Colon", "Alvarado", "Padilla",
    "Nunez", "Figueroa", "Navarro",
})
DEVELOPER_SURNAMES = frozenset({"Horsley", "Hamre", "Zdyrko"})
REPLACED_RETAIL_SURNAMES = HISPANIC_RETAIL_SURNAMES | DEVELOPER_SURNAMES


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().strip()


def usable(name: str) -> bool:
    try:
        pn.validate_name(name, "name")
    except pn.ProspectNamesError:
        return False
    return True


def ranked(counter: collections.Counter) -> list[str]:
    """Most frequent first, ties alphabetical, unusable spellings dropped."""

    return [name for name, _n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])) if usable(name)]


def load_counts(players: Path, first_season: int, last_season: int) -> tuple[collections.Counter, collections.Counter, int]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment
        raise SystemExit("pyarrow is needed to read players.parquet (uv run --with pyarrow ...)") from exc
    table = pq.read_table(players, columns=["first_name", "last_name", "rookie_season", "last_season"])
    firsts: collections.Counter = collections.Counter()
    lasts: collections.Counter = collections.Counter()
    selected = 0
    for row in table.to_pylist():
        first, last = ascii_fold(row.get("first_name") or ""), ascii_fold(row.get("last_name") or "")
        rookie, final = row.get("rookie_season"), row.get("last_season")
        if not first or not last or (rookie is None and final is None):
            continue
        rookie = rookie if rookie is not None else final
        final = final if final is not None else rookie
        if final < first_season or rookie > last_season:
            continue
        selected += 1
        firsts[first] += 1
        lasts[last] += 1
    return firsts, lasts, selected


def build_rows(firsts: collections.Counter, lasts: collections.Counter) -> tuple[list[pn.NameRow], dict[str, int]]:
    retail_lasts = set(pn.RETAIL_LASTS)
    replacements = iter(name for name in ranked(lasts) if name not in retail_lasts)
    surnames: list[str] = []
    for i, retail in enumerate(pn.RETAIL_LASTS):
        surnames.append(next(replacements) if retail in REPLACED_RETAIL_SURNAMES else retail)
    modern_firsts = ranked(firsts)
    picks = modern_firsts[: pn.POOL_COUNT]
    if len(picks) < pn.POOL_COUNT:
        raise SystemExit(f"only {len(picks)} usable modern first names")
    spare = modern_firsts[pn.POOL_COUNT:]
    total = sum(pn.encoded_size(n) for n in picks) + sum(pn.encoded_size(n) for n in surnames)
    swaps = 0
    k = pn.POOL_COUNT - 1
    while total > pn.BUDGET:
        if k < 0:
            raise SystemExit("cannot fit the pool budget: ran out of shorter first names")
        # the least frequent pick still standing takes the best-ranked spare name that is shorter than it
        idx = next((j for j, name in enumerate(spare) if len(name) < len(picks[k])), None)
        if idx is not None:
            candidate = spare.pop(idx)
            total += pn.encoded_size(candidate) - pn.encoded_size(picks[k])
            picks[k] = candidate
            swaps += 1
        k -= 1
    rows = [pn.NameRow(index=i, first=picks[i], last=surnames[i]) for i in range(pn.POOL_COUNT)]
    return rows, {"bytes": total, "swaps": swaps, "retained": sum(1 for r in rows if r.retained),
                  "replaced": sum(1 for r in rows if not r.retained)}


def write_csv(path: Path, rows: list[pn.NameRow], stats: dict[str, int], *, players: Path, selected: int,
              first_season: int, last_season: int) -> None:
    layout = pn.plan_layout(rows)
    lines = [
        "# ESPN NFL 2K5 generated-player name pool: modern first names and surnames (tier B).",
        f"# Source: {pn.ATTRIBUTION} - players.parquet, every player with a season in {first_season}-{last_season}"
        f" ({selected} players).",
        f"# Generated by tools/nfl2k5_modern_names_generate.py on {dt.date.today().isoformat()} from {players.name}"
        f" (sha256 {hashlib.sha256(players.read_bytes()).hexdigest()[:16]}...).",
        f"# {stats['retained']} surnames keep their retail index and recorded call-out (audio = retail); {stats['replaced']}"
        " take modern surnames and are announced by number (audio = number); every first name is modern.",
        f"# Pool bytes: {layout.bytes_used} of {pn.BUDGET} (UTF-16LE with terminators); boundary body offset 0x{layout.boundary:x}.",
        "index,first,last,audio",
    ]
    lines += [f"{r.index},{r.first},{r.last},{'retail' if r.retained else 'number'}" for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--players", type=Path, default=None, help="nflverse players.parquet (default: the cache, downloaded when absent)")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--first-season", type=int, default=2015)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument("--offline", action="store_true", help="never download; fail when the parquet is absent")
    args = parser.parse_args(argv)
    players = args.players or (args.cache / "players.parquet")
    if not players.is_file():
        if args.offline or args.players is not None:
            raise SystemExit(f"players.parquet not found: {players}")
        players.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {PLAYERS_URL} -> {players}")
        urllib.request.urlretrieve(PLAYERS_URL, players)  # noqa: S310 - fixed https URL
    firsts, lasts, selected = load_counts(players, args.first_season, args.last_season)
    rows, stats = build_rows(firsts, lasts)
    write_csv(args.out, rows, stats, players=players, selected=selected, first_season=args.first_season, last_season=args.last_season)
    layout = pn.plan_layout(pn.read_csv(args.out.read_text(encoding="utf-8")))
    print(f"players {selected}; retained {stats['retained']}, replaced {stats['replaced']}, first-name swaps to fit {stats['swaps']}; "
          f"pool {layout.bytes_used}/{pn.BUDGET} bytes (spare {layout.spare}); boundary 0x{layout.boundary:x}")
    print(f"wrote {args.out} sha256 {hashlib.sha256(args.out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
