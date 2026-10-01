"""Shared paths, readers and the base roster for the ratings v2 tools (job r1, 2026-09-24).

Every path comes from the command line (build.py sets ``CFG``); nothing here names a machine path. The base roster
is the retail ROST of the user's own disc (a loose extraction) with a roster-edits document replayed on it (the 2026
league: u1's merge, u7's labels, main's name fix), and the per-team ``roster_rows.csv`` files beside the team
documents a merge receipt lists give each record its nflverse gsis id.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

# set by build.py (and the tests); every key is required by the step that uses it
CFG: dict[str, str] = {
    "retail": "",        # loose extraction folder of the user's retail disc (read-only)
    "base_edits": "",    # 2k5_mod_studio_roster_edits/v1 document the ratings are layered on
    "base_sha256": "",   # optional pin of that document
    "team_receipt": "",  # merge receipt listing the per-team documents (their roster_rows.csv give gsis ids)
    "nflverse": "",      # folder of the public nflverse files (see features.FILES)
    "work": "",          # folder for derived files (features, reference, scraped measurables)
}
ONE_POOL = {0: "QB", 1: "K", 2: "P", 3: "WR", 4: "CB", 5: "FS", 6: "SS", 7: "HB", 8: "FB", 9: "TE", 10: "OLB",
            11: "LB", 12: "C", 13: "G", 14: "T", 15: "DT", 16: "EDGE"}


def work(*parts: str) -> Path:
    p = Path(CFG["work"]).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def nfl(name: str) -> Path:
    return Path(CFG["nflverse"]) / name


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path) -> list[dict]:
    path = str(path)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


_BASE = None


def base():
    """(retail_body, base_body, base_document, rows): the retail ROST body, the body with the base document
    replayed (clean log required), the document, and one row per NFL-club record written by the team documents."""
    global _BASE
    if _BASE is None:
        if CFG.get("base_sha256"):
            assert sha256(CFG["base_edits"]) == CFG["base_sha256"], "the base roster edits changed"
        doc0 = rr.load_image(CFG["retail"])
        retail_body = doc0.to_body()
        edits = json.loads(Path(CFG["base_edits"]).read_text(encoding="utf-8"))
        body, receipt = rr.apply_body(retail_body, edits)
        assert not receipt["log"], receipt["log"][:5]
        rec = json.loads(Path(CFG["team_receipt"]).read_text(encoding="utf-8"))
        rows = []
        for team in rec["teams"]:
            doc_path = team.get("team_document")
            if not doc_path:
                continue
            for row in read_csv(os.path.join(os.path.dirname(doc_path), "roster_rows.csv")):
                row["team_document"] = doc_path
                rows.append(row)
        _BASE = (retail_body, bytes(body), edits, rows)
    return _BASE


def team_of(row, doc=None, player=None) -> str:
    if doc is not None and player is not None and player.teams:
        return doc.teams[player.teams[0]].abbreviation
    m = re.search(r"/teams/([A-Z]+)/", row["team_document"])
    return m.group(1) if m else "NYG"
