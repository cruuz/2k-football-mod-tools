"""rd1 (b778): a transfer's school is the latest one nflverse lists (c1-12: Golden shown Houston, he finished at Texas)."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tools" / "b77"):
    sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
import nfl2k5_team_2026_roster as generator  # noqa: E402
import rd1_college_layer as layer  # noqa: E402

LAYER = json.loads(layer.LAYER.read_text(encoding="utf-8"))
RELEASE = os.environ.get("NFL2K5_V061_DISC")


class Generator(unittest.TestCase):
    def test_latest_school_is_the_first_one_listed(self):
        self.assertEqual(generator.latest_schools_first("Texas; Houston"), ["Texas", "Houston"])
        self.assertEqual(generator.latest_schools_first("Miami; Washington State; Incarnate Word")[0], "Miami")
        self.assertEqual(generator.latest_schools_first(""), [])
        self.assertEqual(generator.latest_schools_first(None), [])


class Layer(unittest.TestCase):
    def test_shape(self):
        rows = LAYER["updates"]
        self.assertEqual(LAYER["schema"], layer.SCHEMA)
        self.assertGreater(len(rows), 200)
        self.assertEqual(len({(r["pool"], r["index"]) for r in rows}), len(rows))
        by = {(r["first"], r["last"]): r for r in rows}
        self.assertEqual((by[("Matthew", "Golden")]["was"], by[("Matthew", "Golden")]["college"]), ("Houston", "Texas"))
        self.assertEqual(by[("Bo", "Nix")]["college"], "Oregon")
        for r in rows:
            self.assertTrue(r["college"] and r["college"] != r["was"], r)
            self.assertEqual(r["source"].split(";")[0].strip() != "", True)

    def test_merge_adds_and_replaces_without_touching_anything_else(self):
        rows = LAYER["updates"][:2]
        mini = {"schema": rr.EDITS_SCHEMA, "edits": [],
                "college_updates": [{"college": "Somewhere", "first": rows[0]["first"], "index": rows[0]["index"],
                                     "last": rows[0]["last"], "pool": "primary"},
                                    {"college": "Other", "first": "Zed", "index": 99999, "last": "Zed", "pool": "primary"}]}
        merged, receipt = layer.merge(mini, {"schema": layer.SCHEMA, "updates": rows})
        self.assertEqual(receipt, {"added": 1, "replaced": 1})
        by = {u["index"]: u for u in merged["college_updates"]}
        self.assertEqual(by[rows[0]["index"]]["college"], rows[0]["college"])
        self.assertEqual(by[rows[1]["index"]]["college"], rows[1]["college"])
        self.assertEqual(by[99999]["college"], "Other")
        self.assertEqual(mini["college_updates"][0]["college"], "Somewhere", "the input document is not modified")
        with self.assertRaises(ValueError):
            layer.merge(mini, {"schema": "x", "updates": rows})
        clash = {"schema": rr.EDITS_SCHEMA, "edits": [], "college_updates": [
            {"college": "Somewhere", "first": "Not", "index": rows[0]["index"], "last": "Him", "pool": "primary"}]}
        with self.assertRaises(ValueError):
            layer.merge(clash, {"schema": layer.SCHEMA, "updates": rows})


@unittest.skipUnless(RELEASE and Path(RELEASE).is_file(), "set NFL2K5_V061_DISC (the v0.6.1 release disc, read only)")
class ReleasedDisc(unittest.TestCase):
    def test_layer_moves_exactly_its_players_to_a_school_the_table_holds(self):
        disc = rr.load_image(RELEASE)
        body = bytes(disc.body)
        before = {(p.pool, p.index): p.college for p in disc.players}
        merged, _ = layer.merge({"schema": rr.EDITS_SCHEMA, "edits": []}, LAYER)
        out, receipt = rr.apply_body(body, merged, refresh_follows=True)
        self.assertEqual(receipt["log"], [])
        after = rr.load_body(out)
        changed = {(p.pool, p.index): p.college for p in after.players if before[(p.pool, p.index)] != p.college}
        expected = {(r["pool"], r["index"]): r["college"] for r in LAYER["updates"]}
        self.assertEqual(changed, expected)
        for r in LAYER["updates"]:
            self.assertEqual(before[(r["pool"], r["index"])], r["was"])
        self.assertEqual(sorted(after.colleges), sorted(disc.colleges), "the college table is not grown or renamed")
        names = {(p.first, p.last): p.college for p in after.players if p.pool == "primary" and p.teams}
        self.assertEqual(names[("Matthew", "Golden")], "Texas")


if __name__ == "__main__":
    unittest.main()
