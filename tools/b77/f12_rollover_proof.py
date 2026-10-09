#!/usr/bin/env python3
"""Job f12 (beta 77): native proof of the experience years before and after the repair.

Runs the game's own x86 (Unicorn, the b765 Machine harness) on the real SOFTDRINK default.xbe and the real ROST bodies
-- the v0.5 body and the f12-repaired body -- and records what the game itself does:

  * the Player Card's YRS PRO text (0x145DA0) for named players, before any season and after one and two Postseason
    rollovers (0x247B40, with the draft-order and cap-cut services stubbed as in the b765 p2 proof);
  * the rollover aggregate: every allocated non-prospect adds exactly 1, prospects and vacant slots stay;
  * the Preseason aging (stage 7 -> 8 of 0x2480B0 in a second season) and the rating changes it applies;
  * the class generator (0x2BE6F0) for all 17 positions: every franchise-drafted rookie starts as 1 and prints R.

Synthetic RAM and stubbed external services are explicit fixtures; nothing here is a played game or a renderer.

  python3 tools/b77/f12_rollover_proof.py --xbe default.xbe --pack0-before PACK0_V05 --pack0-after PACK0_F12 --out proof.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from tools.b765.p1_timeline_proof import STUBS, Machine  # noqa: E402
from tools.b765.p2_lifecycle_proof import ROLLOVER_STUBS  # noqa: E402

SCHEMA = "nfl2k5_b77_f12_rollover_proof/v1"
RATING_ORDER = rr.RATING_BYTE_ORDER
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
# (first, last, birth date, label); drafts from nflverse draft_picks.csv, entry years from roster_2026.csv
SAMPLES = (("Cam", "Ward", "2002-05-25", "2025 draft, round 1 pick 1 (TEN)"),
           ("Travis", "Hunter", "2003-05-18", "2025 draft, round 1 pick 2 (JAX)"),
           ("Ashton", "Jeanty", "2003-12-02", "2025 draft, round 1 pick 6 (LV)"),
           ("Fernando", "Mendoza", "2003-10-01", "2026 draft, round 1 pick 1 (LV)"),
           ("Jeremiyah", "Love", "2005-05-31", "2026 draft, round 1 pick 3 (ARI)"),
           ("David", "Bailey", "2003-08-28", "2026 draft, round 1 pick 2 (NYJ)"),
           ("Patrick", "Mahomes", "1995-09-17", "2017 draft, entered 2017 (10th season in 2026)"),
           ("Travis", "Kelce", "1989-10-05", "2013 draft, entered 2013 (14th season in 2026)"),
           ("Aaron", "Rodgers", "1983-12-02", "2005 draft, entered 2005 (22nd season in 2026)"))
SHOWN_RATINGS = ("speed", "agility", "strength", "pass_accuracy", "catch", "tackle", "composure", "consistency")
ROST_OUTER_INDEX = 5


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def rost_body(pack: bytes) -> bytes:
    _name, size, blocks = struct.unpack_from("<3I", pack, 0x9C + ROST_OUTER_INDEX * 12)
    offset = blocks * 0x800
    resource = pack[offset:offset + size]
    if resource[:4] != b"ROST":
        raise ValueError("outer entry 5 is not a ROST resource")
    return resource[rr.RESOURCE_HEADER_SIZE:]


class Game:
    """One Machine over a ROST body, with the readers the proof needs."""

    def __init__(self, xbe: bytes, body: bytes):
        self.machine = Machine(xbe, body)
        self.count = self.machine.word(self.machine.root)

    def address(self, index: int) -> int:
        return self.machine.pool + 84 * index

    def years_pro(self, index: int) -> int:
        return (self.machine.word(self.address(index) + 0x24) >> 8) & 31

    def flags(self, index: int) -> int:
        return self.machine.byte(self.address(index) + 8)

    def card(self, index: int) -> str:
        """The YRS PRO text the Player Card builder prints (0x145DA0, called with the record in ecx)."""
        text = self.machine.call(0x145DA0, ecx=self.address(index))
        return bytes(self.machine.uc.mem_read(text, 64)).decode("utf-16-le", errors="ignore").split("\x00")[0]

    def card_of_record(self, record: bytes) -> str:
        """The same text for a record that is not in the main roster (an Anniversary team file's 84 bytes)."""
        at = self.machine.BASE + 0x100000
        self.machine.uc.mem_write(at, bytes(record))
        text = self.machine.call(0x145DA0, ecx=at)
        return bytes(self.machine.uc.mem_read(text, 64)).decode("utf-16-le", errors="ignore").split("\x00")[0]

    def career_rows(self, index: int, last_row: int = 40) -> list[tuple[str, int, int | None]]:
        """The Player Card's career table through the game's own code: for card row r the year label is 0x320460(r) and
        the season is history slot (years pro + 11 - r) (the arithmetic of 0x320471..0x32048E); read its games (field 0)
        and TEAM (field 87) with 0x14EE20."""
        m = self.machine
        player = self.address(index)
        m.put(0xC90248, player)
        m.put(0xBD7F98, 0)                                   # regular-season words
        years_pro = self.years_pro(index)
        rows = []
        for row in range(11, last_row):
            slot = years_pro + 11 - row
            if slot < 0:
                break
            games = m.call(0x14EE20, ecx=player, edx=0, args=(slot,))
            if not games:
                continue
            team = m.call(0x14EE20, ecx=player, edx=87, args=(slot,))
            label = bytes(m.uc.mem_read(m.call(0x320460, ecx=row), 40)).decode("utf-16-le", errors="ignore").split("\x00")[0]
            rows.append((label, m.word(games) & 0xFFFF, (m.word(team) & 0xFFFF) if team else None))
        return rows

    def ratings(self, index: int) -> dict[str, int]:
        raw = bytes(self.machine.uc.mem_read(self.address(index) + 0x36, 28))
        return dict(zip(RATING_ORDER, raw))

    def rollover(self) -> None:
        """Postseason -> next offseason: the retail 0x247B40 with its two external services stubbed."""
        m = self.machine
        m.put(0xE576A4, 9)
        m.put(0xE576AC, 34)
        for team in (32, 33):
            m.put(0xE5786C + team * 4, m.teams + team * 500)
        m.stubs = {address: m.ret for address in ROLLOVER_STUBS}
        m.call(0x247B40)
        assert m.word(0xE576A4) == 1, "the rollover did not reach the Retirement Period"

    def preseason_to_season(self) -> int:
        """The stage 7 -> 8 transition of 0x2480B0, which ages every allocated player when the season index is > 0."""
        m = self.machine
        m.put(0xE576A4, 7)
        m.put(0xE576B0, 4)
        m.put(0xE576B4, 4)
        m.stubs = {address: m.ret for address in STUBS}
        m.call(0x2480B0)
        return m.word(0xE576A4)

    def generate_rookies(self, first_slot: int = 1944, seed: int = 12345) -> list[dict]:
        m = self.machine
        m.call(0x48BE0, ecx=0xE5FCA0, edx=seed)
        rows = []
        for position, name in enumerate(POSITIONS):
            index = first_slot + position
            at = self.address(index)
            m.uc.mem_write(at, bytes(84))
            m.uc.mem_write(at + 0x35, bytes((position,)))
            m.call(0x2BE6F0, ecx=at, edx=position, budget=3000000)
            rows.append({"position": name, "years_pro": self.years_pro(index), "flags": hex(self.flags(index)),
                         "card": self.card(index), "birth_year_two_digit": (m.word(at + 0x18) >> 21) & 0x7F})
        return rows


def find(body: bytes, first: str, last: str, birth: str) -> int:
    document = rr.RosterDocument(body, base=0, scheme="one_pool", reference_year=2026)
    for player in document.players:
        if (player.pool == "primary" and (player.first, player.last) == (first, last)
                and player.record.birth_date and player.record.birth_date.isoformat() == birth):
            return player.index
    raise LookupError(f"{first} {last} {birth}")


def career_invariance(xbe: bytes, before: bytes, after: bytes) -> dict:
    """Every cohort player's career table (year label, games, TEAM) must read the same through the game before and after."""
    from mod_editor.core import nfl2k5_save_rost as sr
    old_game, new_game = Game(xbe, before), Game(xbe, after)
    decoded = sr.decode(before, preamble=0, reference_year=2026)
    players = rows = 0
    different = []
    for key, words in sorted(decoded.history_words.items()):
        if not words or key[0] != "primary":
            continue
        index = key[1]
        a, b = old_game.career_rows(index), new_game.career_rows(index)
        players += 1
        rows += len(a)
        if a != b or not a:
            different.append((index, a[:2], b[:2]))
    return {"players_compared": players, "career_rows_compared": rows, "players_whose_rows_differ": len(different),
            "differences": different[:5]}


def run_variant(xbe: bytes, body: bytes, indices: dict[str, int]) -> dict:
    game = Game(xbe, body)
    count = game.count
    # the game's own save (0xC0730) of the loaded roster, reloaded (0xC0500), must give back these exact bytes
    saved = game.machine.save_reload(len(body))
    before = [(game.years_pro(i), game.flags(i)) for i in range(count)]
    display = {name: {"start": game.card(i)} for name, i in indices.items()}
    stored = {name: [game.years_pro(i)] for name, i in indices.items()}
    game.rollover()
    after_one = [(game.years_pro(i), game.flags(i)) for i in range(count)]
    season_index = game.machine.word(0xE576B8)
    for name, i in indices.items():
        display[name]["after_rollover_1"] = game.card(i)
        stored[name].append(game.years_pro(i))
    classes: dict[str, int] = {}
    for (a, flag), (b, _flag) in zip(before, after_one):
        key = f"flag {flag:#04x}: " + ("+1" if b == (a + 1) & 31 else "unchanged" if a == b else "other")
        classes[key] = classes.get(key, 0) + 1
    aging_before = {name: game.ratings(i) for name, i in indices.items()}
    stage = game.preseason_to_season()
    aging = {}
    for name, i in indices.items():
        now = game.ratings(i)
        aging[name] = {"years_pro_at_aging": game.years_pro(i), "card": game.card(i),
                       "rating_changes": {k: now[k] - aging_before[name][k] for k in RATING_ORDER if now[k] != aging_before[name][k]},
                       "shown": {k: now[k] - aging_before[name][k] for k in SHOWN_RATINGS}}
    # a second Postseason rollover on a fresh machine state of the same body (the aging call above ran in season 2)
    second = Game(xbe, body)
    second.rollover()
    second.rollover()
    for name, i in indices.items():
        display[name]["after_rollover_2"] = second.card(i)
        stored[name].append(second.years_pro(i))
    return {"native_save_reload_sha256": saved, "body_sha256": sha(body), "display": display, "stored_years_pro": stored,
            "rollover": {"pool_records": count, "classes": dict(sorted(classes.items())),
                         "season_index_after_first_rollover": season_index},
            "preseason_stage_after": stage, "aging": aging,
            "generator": Game(xbe, body).generate_rookies()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--pack0-before", type=Path, required=True)
    parser.add_argument("--pack0-after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output exists; choose a fresh path")
    xbe = args.xbe.read_bytes()
    packs = {"v05": args.pack0_before.read_bytes(), "f12": args.pack0_after.read_bytes()}
    bodies = {key: rost_body(pack) for key, pack in packs.items()}
    indices = {f"{first} {last}": find(bodies["v05"], first, last, birth) for first, last, birth, _label in SAMPLES}
    result = {"schema": SCHEMA, "inputs": {"default_xbe_sha256": sha(xbe),
                                           **{f"pack0_{key}_sha256": sha(pack) for key, pack in packs.items()}},
              "samples": [{"name": f"{first} {last}", "index": indices[f"{first} {last}"], "note": label}
                          for first, last, _birth, label in SAMPLES],
              "limits": "x86 emulation of the shipped code on real data with synthetic RAM and stubbed external services; "
                        "not a played game, not a renderer, no Noah witness"}
    for key, body in bodies.items():
        result[key] = run_variant(xbe, body, indices)
    result["career_table_invariance"] = career_invariance(xbe, bodies["v05"], bodies["f12"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    for name in indices:
        print(f"{name:20} v0.5 {result['v05']['display'][name]}  repaired {result['f12']['display'][name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
