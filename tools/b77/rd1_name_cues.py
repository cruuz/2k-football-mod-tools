#!/usr/bin/env python3
"""b778 rd1: write data/nfl2k5_retail_name_cues.json from a retail ROST (collects no outside data).

    python3 tools/b77/rd1_name_cues.py RETAIL_DISC_OR_PACK_FOLDER [--out data/nfl2k5_retail_name_cues.json]

A retail full-name play-by-play cue is the recording of one retail player's first and last name. The table keeps every
such cue that exactly one named retail record carries (number calls 9000..9099, the surname bank, 0, 9100, 9101 and the
retail ids without a clip are not name cues).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core.nfl2k5_prospect_names import RETAIL_AUDIO_BASE, RETAIL_LASTS  # noqa: E402


def is_name_cue(cue: int) -> bool:
    return not (cue in rr.PBP_REPLACED or rr.PBP_NUMBER_BASE <= cue < rr.PBP_NUMBER_BASE + 100
                or RETAIL_AUDIO_BASE <= cue < RETAIL_AUDIO_BASE + len(RETAIL_LASTS))


def build(source: Path) -> dict:
    document = rr.load_image(source)
    owners: dict[int, set[tuple[str, str]]] = {}
    for player in document.players:
        if player.pool != "primary" or not (player.first and player.last) or "*" in player.first + player.last:
            continue
        cue = player.record.values["pbp_id"]
        if is_name_cue(cue):
            owners.setdefault(cue, set()).add((player.first, player.last))
    cues = {str(cue): list(next(iter(names))) for cue, names in sorted(owners.items()) if len(names) == 1}
    return {"schema": "nfl2k5_retail_name_cues/v1",
            "source": "the retail main roster (ESPN NFL 2K5 USA): pbp_id -> the one named player who carries it",
            "cues": cues}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "nfl2k5_retail_name_cues.json")
    args = parser.parse_args(argv)
    table = build(args.source)
    rows = ",\n".join(f"{json.dumps(cue)}: {json.dumps(name, ensure_ascii=False)}" for cue, name in table["cues"].items())
    text = (f'{{"schema": {json.dumps(table["schema"])},\n"source": {json.dumps(table["source"])},\n"cues": {{\n{rows}\n}}}}\n')
    json.loads(text)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(table['cues'])} cues -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
