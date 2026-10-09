"""Load nfl4th pre-computed decisions (nflverse release 'nfl4th_infrastructure') joined to nflverse pbp.

Usage: venv/bin/python -I load_nfl4th.py <web/nflverse dir> <out parquet>
Untrusted-data note: the .rds and .parquet files are only parsed as data (pyreadr / pyarrow), never executed.
"""
import sys
from pathlib import Path
import pandas as pd
import pyreadr

src = Path(sys.argv[1]); out = Path(sys.argv[2])
res = pyreadr.read_r(str(src / "pre_computed_go_boost_release.rds"))
gb = next(iter(res.values()))
print("go_boost rows", len(gb), "cols", list(gb.columns))
print(gb.head())
cols = ["game_id", "play_id", "season", "season_type", "week", "qtr", "down", "ydstogo", "yardline_100", "score_differential",
        "game_seconds_remaining", "half_seconds_remaining", "quarter_seconds_remaining", "posteam", "defteam", "posteam_type",
        "posteam_timeouts_remaining", "defteam_timeouts_remaining", "spread_line", "wp", "play_type", "fourth_down_converted",
        "fourth_down_failed", "goal_to_go", "roof", "temp", "wind", "desc"]
frames = []
for y in range(2014, 2026):
    f = pd.read_parquet(src / f"pbp_{y}.parquet", columns=[c for c in cols])
    f = f[(f["down"] == 4)]
    frames.append(f)
pbp = pd.concat(frames, ignore_index=True)
print("4th-down pbp rows", len(pbp))
m = pbp.merge(gb, on=["game_id", "play_id"], how="inner")
print("joined rows", len(m))
m.to_parquet(out)
print(m[["go_boost", "go_wp", "punt_wp", "fg_wp"]].describe())
