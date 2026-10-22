"""b778-bd1: the standing "recompile equals pins" check for every module that pins its applied bytes.

beta-77.1 shipped Modern MetLife pins that no longer matched the code (the Giants field refit gained the midfield
re-centre after the pins were recorded), and nothing noticed because the release build ran with Modern colour, which
re-pins in memory. Each test here recompiles a module's pins from the retail data with the module's own author-time
recorder and demands byte equality with the committed pin file. That is the configuration a user gets WITHOUT Modern
colour (each option compiles alone against its pins). The last class composes the options WITH Modern colour on a few
bundles (the colour grade, then the combined refit) and checks the combined receipt against the same pins.

Every test skips, naming the missing input, when the retail disc, the extracted game folder or the official art pack
is absent, so hosted CI stays green.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACK0 = GAME / "vc_53450030" / "0"
MARKS = Path(os.environ.get("NFL2K5_MARKS_PACK", "/home/noah/.local/share/2k5-mod-studio/official-marks/"
                            "logos-7d37460c5f364263b81642d322f553f1"))


def need(test, *, iso=False, game=False, marks=False):
    if iso and not RETAIL.is_file():
        test.skipTest(f"needs the retail disc image ({RETAIL})")
    if game and not PACK0.is_file():
        test.skipTest(f"needs the extracted retail game folder with vc_53450030/0 ({GAME})")
    if marks:
        if not MARKS.is_dir():
            test.skipTest(f"needs the official art pack ({MARKS})")
        os.environ["NFL2K5_MARKS_PACK"] = str(MARKS)


def canonical(document):
    return json.loads(json.dumps(document, sort_keys=True))


def committed(path):
    return canonical(json.loads(Path(path).read_text(encoding="utf-8")))


def differing(old, new):
    """The top-level keys that differ, and up to twenty per-bundle/scene/texture rows."""
    keys = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    rows = []
    for key in keys:
        if isinstance(old.get(key), list) and isinstance(new.get(key), list):
            fresh = {json.dumps(r, sort_keys=True) for r in new[key]}
            rows += [str(r.get("name") or r.get("scene") or r.get("texture")) for r in old[key]
                     if isinstance(r, dict) and json.dumps(r, sort_keys=True) not in fresh]
    return keys, rows[:20]


class RecordedPinsEqualCommittedPins(unittest.TestCase):
    """Each module alone (no Modern colour): the author-time recorder reproduces the committed pin file."""

    def check(self, old_path, new_document):
        old, new = committed(old_path), canonical(new_document)
        self.assertTrue(old == new, f"{Path(old_path).name} is stale: differs at {differing(old, new)}")

    def test_modern_metlife(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_modern_metlife as m
        with tempfile.TemporaryDirectory() as folder:
            self.check(m.PINS_PATH, m.record_pins(str(RETAIL), Path(folder) / "p.json"))

    def test_modern_arrowhead(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_modern_arrowhead as m
        with tempfile.TemporaryDirectory() as folder:
            self.check(m.PINS_PATH, m.record_pins(str(RETAIL), Path(folder) / "p.json"))

    def test_modern_goalposts(self):
        need(self, game=True)
        from mod_editor.core import nfl2k5_modern_goalposts as m
        self.check(m.PINS_PATH, m.record_pins(PACK0, None))

    def test_espn_marks(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_espn_marks as m
        self.check(m.PINS_PATH, m.record_pins(str(RETAIL), None))

    def test_kick_meter_2026(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_kick_meter_2026 as m
        self.check(m.PINS_PATH, m.record_pins(str(RETAIL), None))

    def test_espn_wipes_boards(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_espn_wipes_boards as m
        self.check(m.PINS_PATH, m.record_pins(str(RETAIL), None))

    def test_modern_surfaces(self):
        need(self, iso=True)
        from mod_editor.core import nfl2k5_modern_surfaces as m
        self.check(m.PINS_PATH, m.build_pins(str(RETAIL)))

    def test_modern_colour(self):
        need(self, game=True)
        from mod_editor.core import nfl2k5_modern_color as m
        self.check(m.PINS_PATH, m.build_pins(GAME, workers=8))


class CombinedWithModernColour(unittest.TestCase):
    """Modern colour ON: the colour grade, then the stadium's combined refit, against the same pins."""

    def combined(self, module, name, *, dry=False):
        from mod_editor.core import nfl2k5_modern_color as colour
        pins = {p["name"]: p for p in module._pins()["bundles"]}
        pin = pins[name]
        with module._outer_image()(str(RETAIL)) as archive:
            def read(row):
                entry = archive.entries[row["outer"]]
                return archive.read(entry.virtual_offset, entry.size)
            retail = read(pin)
            dry_retail = read(pins[module.dry_name(name)]) if dry else None
        self.assertEqual(module.sha(retail), pin["retail_sha256"])
        graded, _ = colour.modern_bundle(retail, outer_index=pin["outer"])
        if dry:
            after, edits = module.combined_bundle(retail, graded, name, dry_retail, outer_index=pin["outer"])
        else:
            after, edits = module.combined_bundle(retail, graded, outer_index=pin["outer"])
        self.assertEqual(len(after), len(retail))
        by_kind = {e["kind"]: e for e in edits}
        for site in pin["sites"]:
            row = by_kind.get(site["kind"])
            self.assertIsNotNone(row, f"{name}: combined refit skipped the pinned {site['kind']} site")
            self.assertEqual((row["offset"], row["size"], row["retail"]),
                             (site["offset"], site["size"], site["retail"]), f"{name}: {site['kind']} site moved")
            span = after[site["offset"]:site["offset"] + site["size"]]
            self.assertEqual(module.sha(span), row["applied"])
        return after

    def test_modern_arrowhead_with_colour(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_modern_arrowhead as m
        self.combined(m, "s13dd.iff")

    def test_modern_metlife_with_colour_giants_snow_and_jets_day(self):
        need(self, iso=True, marks=True)
        from mod_editor.core import nfl2k5_modern_metlife as m
        for name in ("s18ds.iff", "s19dd.iff"):
            with self.subTest(name):
                self.combined(m, name, dry=True)


if __name__ == "__main__":
    unittest.main()
