"""vb3 D4: a star list the game itself would agree with.

Noah's video 2 [6:13-6:17]: "I love that star players now have that star under them. You set that
in the editor. Obviously, Michael Vick should have that as well."

The video disc's ``player_tags`` are the 17 X-Factors (rank 1 per position) of the abilities tier
file, and that file ranks players by the plain sum of their position's key ratings
(``nfl2k5_abilities_editor.plan_auto_assign``).  Measured against the game's own overall (the
number its roster screens print, ``nfl2k5_my_career_prospects.native_overall``, FUN_00246D90):

* only one player per position can carry the star, so Randy Moss, Terrell Owens and Torry Holt
  (100 each), Brian Urlacher, LaDainian Tomlinson and Michael Vick never do;
* Vick is 6th of the QBs in the key-rating sum and 7th in the game's overall (90);
* the HB X-Factor is T.J. Duckett (overall 80), not Tomlinson (97), and the OLB one is Rosevelt
  Colvin (88), not Derrick Brooks (96).

The proposal: star every active NFL club player the game rates 90 or better.  On the retail roster
that is 120 players (about 3.8 a club) and includes Vick at exactly 90. Linemen use
the1wam's September 23 five-band rating, adopted in aef937d2; the older two-band
report contained 119 players. The plain retail rating still selects 118.

    python3 reports/vb3_d4/stars.py [--roster <disc or pack folder>] [--min-overall 90]
                                    [--write reports/vb3_d4/player_tags_ovr90.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_player_tags as pt  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

RETAIL = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
OUT = ROOT / "reports" / "vb3_d4" / "player_tags_ovr90.json"


def rows(document, *, min_overall: int = 90, lineman: bool = True) -> list[dict]:
    """The core rule (``nfl2k5_player_tags.star_rule_rows``) with club names; linemen as the video disc rates them."""

    out = []
    for row in pt.star_rule_rows(document, min_overall=min_overall, lineman=lineman):
        team = document.teams[row.pop("club")]
        out.append({**row, "team": f"{team.city} {team.nickname}"})
    return out


def document_for(roster: Path | str):
    return rr.load_image(roster)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roster", default=str(RETAIL))
    parser.add_argument("--min-overall", type=int, default=90)
    parser.add_argument("--write", nargs="?", const=str(OUT))
    args = parser.parse_args(argv)
    document = document_for(args.roster)
    found = rows(document, min_overall=args.min_overall)
    by_position = defaultdict(int)
    for row in found:
        by_position[row["position"]] += 1
    report = {
        "schema": "vb3-d4-star-tags/1",
        "rule": f"nfl2k5_player_tags.star_rule_tags: every active NFL club player whose in-game overall (FUN_00246D90, "
                f"linemen with the1wam's rating) is {args.min_overall} or better",
        "roster": "retail USA ROST" if Path(args.roster) == RETAIL else str(args.roster),
        "count": len(found), "by_position": dict(sorted(by_position.items())),
        "player_tags": sorted((row["tag"] for row in found), key=int),
        "players": found,
    }
    text = json.dumps(report, indent=1, ensure_ascii=False) + "\n"
    if args.write:
        Path(args.write).write_text(text, encoding="utf-8")
        print(f"wrote {args.write}: {len(found)} players")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
