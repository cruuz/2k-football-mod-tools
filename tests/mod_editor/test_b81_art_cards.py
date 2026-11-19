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
SOURCES = Path(os.environ.get("B81_ART_SOURCES", "/media/noah/Storage/2K5-project/b81-art/src128-final"))
#: the alternates whose logo is rebuilt from the official mark (Bills blue, Broncos white, Jaguars teal), both shells
ALTERNATES = ("03_8", "08_5", "12_6")
#: Standard-shell kits whose side logos are rebuilt from the modern shell (tests/mod_editor/test_b81_art_helmet_cleanup.py)
STANDARD_REBUILT = ("00_0", "00_6", "00_7", "01_0", "02_0", "02_2", "02_3", "03_0", "03_3", "03_9", "04_0", "04_2",
                    "05_4", "08_0", "08_6", "09_0", "09_2", "09_9", "10_5", "12_0", "13_0", "14_0", "14_10", "16_9",
                    "18_7", "22_0", "22_5", "24_0", "24_9", "24_10", "25_7", "27_0", "28_7", "29_9", "37_2")
NEW_HELMETS = ({f"{shell}_{kit[:2]}{side}{kit[3:]}" for shell in ("helmet00", "helmet02") for kit in ALTERNATES for side in "HA"}
               | {f"helmet00_{kit[:2]}{side}{kit[3:]}" for kit in STANDARD_REBUILT for side in "HA"})


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
        # a mini follows its Standard-shell helmet where that side's texture changes by 500 texels or more (the logo
        # rebuilt from the modern shell, old-logo pieces gone) and the released mini is that texture's own render: both
        # sides for these clubs, the home side alone for the Cardinals
        self.assertEqual(sorted(doc["minis"]), sorted(
            [f"mini_{side}{code}_0" for code in ("01", "02", "03", "04", "09", "12", "13", "14", "24", "27") for side in "ha"]
            + ["mini_h00_0"]))
        for name, row in doc["minis"].items():
            self.assertNotEqual(row["source_rgba_sha256"], row["new_rgba_sha256"], name)
        # silver by default (the road kit's helmet), the black helmet with the 2012 panther on the blue alternate
        self.assertEqual(doc["helmet_reassign"], {"04H0": "04A0", "04H2": "04H0", "04A2": "04H0"})
        # new source art: the three rebuilt alternates on both shells and every rebuilt Standard-shell kit, both sides
        self.assertEqual(set(doc["helmets"]), NEW_HELMETS)
        self.assertEqual(len(doc["helmets"]), 82)
        for name, row in doc["helmets"].items():
            self.assertNotEqual(row["source_rgba_sha256"], row["new_rgba_sha256"], name)


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
        self.assertEqual(seen, 570 + 21)

    def test_the_rebuilt_helmets_are_the_pinned_source_art(self):
        doc = pins()
        seen = 0
        for edit in self.project["edits"]:
            if edit.get("kind") == "live_helmet":
                name = f"{edit['family']}_{edit['asset_code']}{edit['side']}{edit['variant']}"
                if name in doc["helmets"]:
                    self.assertEqual(rgba_sha(edit["png"]), doc["helmets"][name]["new_rgba_sha256"], name)
                    seen += 1
        self.assertEqual(seen, len(doc["helmets"]))
        self.assertEqual(seen, 82)

    def test_carolina_wears_the_assigned_helmets(self):
        helmets = {(f"{e['asset_code']}{e['side']}{e['variant']}", e["family"]): rgba_sha(e["png"])
                   for e in self.project["edits"] if e.get("kind") == "live_helmet"}
        doc = pins()
        # after the assignment the three slots hold: 04H0 = the road kit's silver helmet; 04H2 and 04A2 = one and the
        # same black helmet, which is no longer the art of 04H0 (by pixels: the rebuilt Standard-shell helmets are
        # new files per slot)
        for family in ("helmet00", "helmet02"):
            self.assertEqual(helmets[("04H0", family)], helmets[("04A0", family)])
            self.assertEqual(helmets[("04H2", family)], helmets[("04A2", family)])
            self.assertNotEqual(helmets[("04H2", family)], helmets[("04H0", family)])
        self.assertEqual(set(doc["helmet_reassign"]), {"04H0", "04H2", "04A2"})


if __name__ == "__main__":
    unittest.main()
