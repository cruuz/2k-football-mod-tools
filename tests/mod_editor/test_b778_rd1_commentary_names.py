"""rd1 (b778): the announcer never says another player's first and last name.

10/21 stream: Berman called Jonathan Taylor "Chester Taylor" (and credited Alontae Taylor's interception to him). A retail
full-name cue records one retail player's first AND last name; 673 players of the 2026 league carried the cue of a retail
player who shares only the surname. The pinned table data/nfl2k5_retail_name_cues.json says whose name each cue is.
"""
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests" / "mod_editor", ROOT / "tools"):
    sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core.nfl2k5_prospect_names import RETAIL_AUDIO_BASE, RETAIL_LASTS  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body, SAMPLE  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
RELEASE = os.environ.get("NFL2K5_V061_DISC")
RELEASED = Path(RELEASE or "/nonexistent")


def is_name_cue(cue):
    return not (cue in rr.PBP_REPLACED or 9000 <= cue < 9100 or RETAIL_AUDIO_BASE <= cue < RETAIL_AUDIO_BASE + len(RETAIL_LASTS))


class Table(unittest.TestCase):
    def test_table_shape(self):
        table = rr.retail_name_cues()
        self.assertGreater(len(table), 1800)
        self.assertEqual(table[3722], ("Chester", "Taylor"))
        for cue, (first, last) in table.items():
            self.assertTrue(is_name_cue(cue), cue)
            self.assertTrue(first and last and "*" not in first + last, cue)

    def test_cue_decisions(self):
        taylor = rr.recorded_surname_ids()["taylor"]
        self.assertTrue(rr.is_wrong_name_cue(3722, "Jonathan", "Taylor"))
        self.assertFalse(rr.is_wrong_name_cue(3722, "Chester", "Taylor"))
        self.assertFalse(rr.is_wrong_name_cue(3722, "chester", "TAYLOR"))
        self.assertFalse(rr.is_wrong_name_cue(3722, "Chester", "Taylor Jr."))
        self.assertFalse(rr.is_wrong_name_cue(3722, "Anybody", "Else"), "another surname is a deliberate pick, kept")
        self.assertFalse(rr.is_wrong_name_cue(9309, "Jonathan", "Taylor"), "surname bank cues are never wrong")
        self.assertEqual(rr.commentary_id("Taylor", 28, 3722, first="Jonathan"), taylor)
        self.assertEqual(rr.commentary_id("Taylor", 28, 3722, first="Chester"), 3722)
        self.assertEqual(rr.commentary_id("Taylor", 28, 3722), 3722, "callers that do not pass a first name are unchanged")
        self.assertEqual(rr.commentary_id("Qwertyuiop", 28, 3722, first="Chester"), 3722)
        self.assertEqual(rr.commentary_id("Zzyzx", 28, rr.PBP_NUMBER_FALLBACK, first="A"), 9028)
        own = rr.exact_name_cue("Michael", "Pittman")
        self.assertIsNotNone(own)
        self.assertEqual(rr.retail_name_cues()[own], ("Michael", "Pittman"))

    def test_wrong_first_name_becomes_surname_then_number(self):
        taylor = rr.recorded_surname_ids()["taylor"]
        self.assertEqual(rr.commentary_id("Taylor", 28, 3722, first="Jonathan"), taylor)
        # a surname the bank does not record falls back to the number call, never to the old owner's first name
        table = rr.retail_name_cues()
        cue, (first, last) = next((c, n) for c, n in sorted(table.items())
                                  if rr.commentary_surname(n[1]) not in rr.recorded_surname_ids()
                                  and rr.exact_name_cue("Zed", n[1]) is None)
        self.assertEqual(rr.commentary_id(last, 44, cue, first="Zed"), 9044)


class Body(unittest.TestCase):
    """Player 0 of the synthetic roster is Peyton Manning; the table is patched so cue 7777 records "Zed Manning"."""

    def setUp(self):
        self._saved = rr._RETAIL_NAME_CUES
        rr._RETAIL_NAME_CUES = {7777: ("Zed", "Manning")}

    def tearDown(self):
        rr._RETAIL_NAME_CUES = self._saved

    def fixture(self, cue):
        doc = rr.load_body(synthetic_body())
        doc.players[0].record.set("pbp_id", cue, normalise_commentary=False)
        return doc

    def expected(self):
        player = rr.load_body(synthetic_body()).players[0]
        return rr.commentary_id(player.last, player.record.get("jersey"), rr.PBP_NUMBER_FALLBACK)

    def test_edited_record_with_the_wrong_first_name_is_repaired_on_write(self):
        out = rr.load_body(self.fixture(7777).to_body()).players[0].record.get("pbp_id")
        self.assertEqual(out, self.expected())
        self.assertNotEqual(out, 7777)

    def test_kept_when_the_cue_names_the_player_or_somebody_else_entirely(self):
        rr._RETAIL_NAME_CUES = {7777: ("Zed", "Manning"), 7778: ("Peyton", "Manning")}
        self.assertEqual(rr.load_body(self.fixture(7778).to_body()).players[0].record.get("pbp_id"), 7778)
        self.assertEqual(rr.load_body(self.fixture(7779).to_body()).players[0].record.get("pbp_id"), 7779)

    def test_final_pass_repairs_a_copy_only_in_pbp_id_and_is_idempotent(self):
        body = self.fixture(7777).to_body(normalise_commentary=False)
        self.assertEqual(rr.load_body(body).players[0].record.get("pbp_id"), 7777)
        fixed, receipt = rr.repair_commentary_body(body)
        self.assertEqual(rr.load_body(fixed).players[0].record.get("pbp_id"), self.expected())
        doc = rr.load_body(body)
        permitted = {p.offset + n for p in doc.players for n in (4, 5)}
        self.assertTrue(all(a == b or i in permitted for i, (a, b) in enumerate(zip(body, fixed))))
        self.assertEqual(rr.repair_commentary_body(fixed)[1]["players_changed"], 0)


@unittest.skipUnless(RETAIL.is_file(), "private retail disc is absent")
class AgainstRetail(unittest.TestCase):
    def test_table_is_exactly_the_retail_owners(self):
        retail = rr.load_image(RETAIL)
        owners = {}
        for p in retail.players:
            cue = p.record.values["pbp_id"]
            if p.pool == "primary" and p.first and p.last and "*" not in p.first + p.last and is_name_cue(cue):
                owners.setdefault(cue, set()).add((p.first, p.last))
        expected = {c: next(iter(n)) for c, n in owners.items() if len(n) == 1}
        self.assertEqual(rr.retail_name_cues(), expected)


@unittest.skipUnless(RELEASE and RELEASED.is_file() and RETAIL.is_file(), "set NFL2K5_V061_DISC (the v0.6.1 release disc, read only)")
class ReleasedDisc(unittest.TestCase):
    def test_no_player_of_the_final_pass_keeps_another_players_name(self):
        """v0.6.1 carried 673 wrong first names; the final pass leaves none and moves nothing else."""
        disc = rr.load_image(RELEASED)
        body = bytes(disc.body)
        wrong = [p for p in disc.players if (p.first or p.last)
                 and rr.is_wrong_name_cue(p.record.values["pbp_id"], p.first, p.last)]
        self.assertEqual(len(wrong), 673)
        fixed, receipt = rr.repair_commentary_body(body)
        after = rr.load_body(fixed)
        self.assertEqual(receipt["players_changed"], 673)
        self.assertEqual([p for p in after.players if (p.first or p.last)
                          and rr.is_wrong_name_cue(p.record.values["pbp_id"], p.first, p.last)], [])
        table = rr.retail_name_cues()
        for p in after.players:
            owner = table.get(p.record.values["pbp_id"])
            if owner is not None and (p.first or p.last) and rr.commentary_surname(owner[1]) == rr.commentary_surname(p.last):
                self.assertEqual(owner[0].casefold(), p.first.casefold(), p.display)
        permitted = {p.offset + n for p in disc.players for n in (4, 5)}
        self.assertTrue(all(a == b or i in permitted for i, (a, b) in enumerate(zip(body, fixed))))
        by_name = {(p.first, p.last): p.record.values["pbp_id"] for p in after.players if p.first}
        self.assertEqual(by_name[("Jonathan", "Taylor")], rr.recorded_surname_ids()["taylor"])
        self.assertEqual(by_name[("Alontae", "Taylor")], rr.recorded_surname_ids()["taylor"])


if __name__ == "__main__":
    unittest.main()
