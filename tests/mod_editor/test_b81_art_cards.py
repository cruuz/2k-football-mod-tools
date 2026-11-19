"""b81-art: the Team Select cards and mini helmets of the SOFTDRINK league project after the helmet cleanup
(data/nfl2k5_b81_art_cards.json pins the pictures; the art lives in the pack, tools/b81_art made it).

The pin document's shape, and (with an extracted source folder that carries the new art, B81_ART_SOURCES) every card,
mini and Carolina helmet edit of the project compared with its pin by pixels."""
import hashlib
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "data/nfl2k5_b81_art_cards.json"
SOURCES = Path(os.environ.get("B81_ART_SOURCES", "/media/noah/Storage/2K5-project/b81-art/src128"))


def pins():
    return json.loads(PINS.read_text(encoding="utf-8"))


def rgba_sha(path):
    import numpy as np
    from PIL import Image
    with Image.open(path) as image:
        return hashlib.sha256(np.ascontiguousarray(np.asarray(image.convert("RGBA"), dtype=np.uint8)).tobytes()).hexdigest()


def card_name(edit):
    side = "h" if edit["side"] == "home" else "a"
    return f"{edit['family']}_{side}{edit['asset_code']}_{int(edit['style'])}_{int(edit['resolution'])}"


class Pins(unittest.TestCase):
    def test_every_card_of_the_95_kits_is_pinned(self):
        doc = pins()
        self.assertEqual(doc["schema"], "nfl2k5_b81_art_cards/v1")
        cards = doc["cards"]
        self.assertEqual(len(cards), 570)
        kits = {name.split("_")[1][1:] + "_" + name.split("_")[2] for name in cards}
        self.assertEqual(len(kits), 95)
        for kit in kits:
            code, style = kit.split("_")
            for side in "ha":
                for family, size in (("helm", 256), ("helm", 128), ("unif", 256)):
                    self.assertIn(f"{family}_{side}{code}_{style}_{size}", cards)
        for name, row in cards.items():
            self.assertEqual(len(row["source_rgba_sha256"]), 64, name)
            self.assertEqual(len(row["new_rgba_sha256"]), 64, name)
            self.assertEqual(row["changed_pixels"] > 0, row["source_rgba_sha256"] != row["new_rgba_sha256"], name)

    def test_minis_and_the_carolina_assignment(self):
        doc = pins()
        # both sides for the clubs whose Standard-shell helmet lost old-logo pieces; the home side alone for the clubs
        # whose left-side logo faced the back of the helmet
        self.assertEqual(sorted(doc["minis"]), sorted(
            [f"mini_{side}{code}_0" for code in ("00", "02", "09") for side in "ha"]
            + [f"mini_h{code}_0" for code in ("01", "03", "04", "12", "13", "14", "27")]))
        for name, row in doc["minis"].items():
            self.assertNotEqual(row["source_rgba_sha256"], row["new_rgba_sha256"], name)
        # silver by default (the road kit's helmet), the black helmet with the 2012 panther on the blue alternate
        self.assertEqual(doc["helmet_reassign"], {"04H0": "04A0", "04H2": "04H0", "04A2": "04H0"})


@unittest.skipUnless((SOURCES / "SOFTDRINK-league-project.json").is_file() and (SOURCES / "b81art-apply-receipt.json").is_file(),
                     "no extracted SOFTDRINK source folder with the b81-art pictures on this machine")
class SourceFolder(unittest.TestCase):
    """The league project of a source folder after tools/b81_art/apply_art.py, compared with the pins by pixels."""

    @classmethod
    def setUpClass(cls):
        cls.project = json.loads((SOURCES / "SOFTDRINK-league-project.json").read_text(encoding="utf-8"))

    def test_every_card_and_mini_is_the_pinned_picture(self):
        doc = pins()
        seen = 0
        for edit in self.project["edits"]:
            if edit.get("kind") == "team_select":
                self.assertEqual(rgba_sha(edit["png"]), doc["cards"][card_name(edit)]["new_rgba_sha256"], card_name(edit))
                seen += 1
            elif edit.get("kind") == "p8_texture" and edit["asset_id"].split(":")[-1] in doc["minis"]:
                name = edit["asset_id"].split(":")[-1]
                self.assertEqual(rgba_sha(edit["png"]), doc["minis"][name]["new_rgba_sha256"], name)
                seen += 1
        self.assertEqual(seen, 583)

    def test_carolina_wears_the_assigned_helmets(self):
        helmets = {(f"{e['asset_code']}{e['side']}{e['variant']}", e["family"]): e["png"]
                   for e in self.project["edits"] if e.get("kind") == "live_helmet"}
        doc = pins()
        # after the assignment the three slots hold: 04H0 = the road kit's silver helmet; 04H2 and 04A2 = one and the
        # same black helmet, which is no longer the art of 04H0
        for family in ("helmet00", "helmet02"):
            self.assertEqual(helmets[("04H0", family)], helmets[("04A0", family)])
            self.assertEqual(helmets[("04H2", family)], helmets[("04A2", family)])
            self.assertNotEqual(helmets[("04H2", family)], helmets[("04H0", family)])
        self.assertEqual(set(doc["helmet_reassign"]), {"04H0", "04H2", "04A2"})


if __name__ == "__main__":
    unittest.main()
