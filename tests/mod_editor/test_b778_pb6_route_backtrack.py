"""b778 pb6: no route runner of a shipped offense pack doubles back on itself, from any formation that lists the play.

int8 found two plays after pb5 filed plain play-action passes into gun and pistol sets (ARZ p102 "PA Slot Cross Dig",
TEN p089 "PA X Seam Shot"): the back's under-centre stem of 6 yd plus the native block endpoint (1 yd behind the line,
route kind 10) is fine from 7 yd deep and a 1.7 yd turn-round from a gun back's 5.3 yd.  The sc1 route test only
checked generated designs, never the shipped packs, so it stayed green.  (Failed on 54a30bc7b: 2 plays, 3 links.)
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from pb.v2 import repair_reversals as rv  # noqa: E402
from pb.v2 import sanity_b778 as sanity  # noqa: E402
from mod_editor.core import nfl2k5_route_reversal as rr  # noqa: E402

MANIFEST = ROOT / "pb" / "v2" / "manifest.json"


def packs():
    for row in json.loads(MANIFEST.read_text(encoding="utf-8"))["teams"]:
        yield row["team"], json.loads((ROOT / row["pack"]).read_text(encoding="utf-8"))


class ShippedRouteBacktrackTests(unittest.TestCase):
    def test_no_runner_reverses_from_any_listing_formation(self):
        """Every slot of every pass and play-action play, from every formation whose menu lists it (not only the
        target of a screen): route kinds 9 / 10 never send a player back toward his goal line by more than a yard."""
        bad = []
        for team, doc in packs():
            by_id = {f["id"]: f for f in doc["formations"]}
            for play in doc["plays"]:
                if play.get("play_type") not in ("pass", "pa_pass"):
                    continue
                chains = rv._chains(play)
                primary = rv._primary(play)
                for fid, ctx in rv.play_contexts(doc, play["id"]):
                    for q in ctx.players:
                        if q.slot != primary and chains[q.slot] and rr.reversals(q.z, chains[q.slot]):
                            bad.append((team, play["id"], play["custom_name"], by_id[fid]["custom_name"], q.slot))
        self.assertEqual(bad, [])

    def test_repair_audit_and_sanity_rule_agree_and_are_zero(self):
        for team, doc in packs():
            self.assertEqual(dict(rv.audit_doc(doc)), {}, team)
            self.assertEqual(sanity.fix_pa_reversal(json.loads(json.dumps(doc))), [], team)

    def test_refill_refuses_a_pairing_that_turns_the_back_round(self):
        """54a30bc7b's ARZ p102 ("PA Slot Cross Dig") in f05; b778 int2/ai7 regenerated the books,
        so the fixture finds the same shape on a current shipped pass play in a gun set."""
        doc = dict(packs())["ARZ"]
        by_id = {f["id"]: f for f in doc["formations"]}
        stem6 = [[0, 0, 548.64, 15], [10, 0, 91.44, 15]]
        found = None
        for play in doc["plays"]:
            if play.get("play_type") not in ("pass", "pa_pass") or not play["assignments"][10]:
                continue
            bad = json.loads(json.dumps(play))
            bad["assignments"][10] = [[1, [1, 3, 0, 0, 0, 0]], [23, [0, 0, 4]]] + [[18, v] for v in stem6]
            for fid, _ctx in rv.play_contexts(doc, play["id"]):
                gun = by_id[fid]
                if not gun["custom_name"].startswith("Gun"):
                    continue
                if sanity.reverses_in(gun, bad) and not sanity.reverses_in(gun, play):
                    found = (play, gun, bad)
                    break
            if found:
                break
        self.assertIsNotNone(found, "no shipped gun play reproduces the pa-back stem")
        play, gun, bad = found
        self.assertTrue(sanity.reverses_in(gun, bad))
        self.assertFalse(sanity.reverses_in(gun, play))


if __name__ == "__main__":
    unittest.main()
