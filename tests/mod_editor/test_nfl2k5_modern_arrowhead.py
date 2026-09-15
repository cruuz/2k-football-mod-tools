"""Modern Arrowhead (experimental): authored art, targets, fixed-span refit and pins."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_arrowhead as ma  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"


class ArtTests(unittest.TestCase):
    def test_every_target_has_exact_size_art_and_the_pins_name_it(self):
        pins = json.loads(ma.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(pins["schema"], ma.PINS_SCHEMA)
        self.assertEqual(pins["art"], ma.art_pins())
        self.assertEqual(set(ma.TARGETS.values()), set(pins["art"]))
        from PIL import Image
        for png in set(ma.TARGETS.values()):
            with Image.open(ma.ART_DIR / png) as image:
                self.assertEqual(image.mode in ("RGBA", "RGB"), True, png)
                width, height = image.size
                self.assertTrue(width & (width - 1) == 0 and height & (height - 1) == 0, png)
            self.assertEqual(len(ma.art_rgba(png, width, height)), width * height * 4)

    def test_variants_and_name_ids(self):
        self.assertEqual(len(ma.VARIANTS), 9)
        self.assertEqual(ma.name_id("s13nd.iff"), 0x03808CDC)
        self.assertEqual(ma.name_id("s13dd.iff"), 0xE9B764BD)

    def test_reviewed_catalog_carries_the_art(self):
        catalog = json.loads((ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json").read_text(encoding="utf-8"))
        for png in sorted(ma.ART_DIR.glob("*.png")):
            row = catalog["files"][f"data/nfl2k5_modern_arrowhead/{png.name}"]
            self.assertEqual(row["sha256"], hashlib.sha256(png.read_bytes()).hexdigest(), png.name)
            self.assertEqual(row["size"], png.stat().st_size)


class BundleStateTests(unittest.TestCase):
    def test_states_from_site_hashes(self):
        class Entry:
            name_id, size, virtual_offset = 1, 8, 0

        class Archive:
            entries = [Entry()]

            def __init__(self, blob):
                self.blob = blob

            def read(self, at, size):
                return self.blob[at:at + size]

        pin = dict(name="x", outer=0, name_id=1, size=8,
                   sites=[dict(offset=0, size=4, retail=ma.sha(b"aaaa"), applied=ma.sha(b"bbbb")),
                          dict(offset=4, size=4, retail=ma.sha(b"cccc"), applied=ma.sha(b"dddd"))])
        self.assertEqual(ma._bundle_state(Archive(b"aaaacccc"), pin), "retail")
        self.assertEqual(ma._bundle_state(Archive(b"bbbbdddd"), pin), "applied")
        self.assertEqual(ma._bundle_state(Archive(b"aaaadddd"), pin), "mixed")
        self.assertEqual(ma._bundle_state(Archive(b"aaaazzzz"), pin), "foreign")


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class RetailTests(unittest.TestCase):
    def test_night_bundle_refit_matches_the_pins_and_keeps_the_wrappers(self):
        pins = json.loads(ma.PINS_PATH.read_text(encoding="utf-8"))
        pin = next(b for b in pins["bundles"] if b["name"] == "s13nd.iff")
        with ma._outer_image()(PACKS) as archive:
            entry = archive.entries[pin["outer"]]
            self.assertEqual(entry.name_id, pin["name_id"])
            data = archive.read(entry.virtual_offset, entry.size)
        self.assertEqual(ma.sha(data), pin["retail_sha256"])
        after, edits = ma.modern_bundle(data)
        self.assertEqual(ma.sha(after), pin["applied_sha256"])
        self.assertEqual(len(after), len(data))
        self.assertEqual([e["kind"] for e in edits], ["field", "stadium"])
        for edit, site in zip(edits, pin["sites"]):
            self.assertEqual((edit["offset"], edit["size"], edit["before_sha256"], edit["after_sha256"]),
                             (site["offset"], site["size"], site["retail"], site["applied"]))
            # The retail wrapper (kind, sizes, magic) is kept; only the scratch word may move.
            self.assertEqual(after[edit["offset"]:edit["offset"] + 20], data[edit["offset"]:edit["offset"] + 20])
            self.assertLessEqual(edit["encoded_bytes"], edit["consumed_cap"])
        self.assertEqual({t["png"] for e in edits for t in e["textures"]}, set(ma.TARGETS.values()))
        # Bytes outside the two scene spans are untouched.
        spans = [(e["offset"], e["offset"] + e["size"]) for e in edits]
        for at in range(0, len(data), 4096):
            if not any(a <= at < b for a, b in spans):
                self.assertEqual(after[at:at + 64], data[at:at + 64], hex(at))

    def test_pins_cover_every_bundle_and_the_packs_read_as_retail(self):
        pins = json.loads(ma.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual([b["name"] for b in pins["bundles"]], list(ma.VARIANTS))
        with ma._outer_image()(PACKS) as archive:
            found = ma.arrowhead_entries(archive)
            self.assertEqual(set(found), set(ma.VARIANTS))
            for pin in pins["bundles"]:
                self.assertEqual(ma._bundle_state(archive, pin), "retail", pin["name"])
        self.assertEqual(ma.image_status(PACKS), "retail")


if __name__ == "__main__":
    unittest.main()
