"""A kit is the pack plus the right words -- and must stay both.

``tools/nfl2k5_ps2_replacement_pack_kit.py`` exists because one pack is loaded
by three emulators that need different settings, and carrying the other
emulator's instructions by hand is where the wrong setting gets copied. Two
things can therefore go wrong, and both are tested here against a real exported
pack rather than a hand-written one:

* the copy stops being the pack -- so every kit's pack is compared byte for
  byte with the original, **and** the independent verifier is run on the copy.
  A kit that no longer verifies would hand somebody a pack that cannot be
  checked, which is worse than no kit;
* the words stop matching the emulator -- so each kit is required to name its
  own target's settings and, for the two stock-PCSX2 targets, never to mention
  a Classic Texture Names setting those builds do not have.

The tool's own ``--selftest`` covers its refusals against synthetic fixtures;
these tests cover it against output the exporter actually wrote.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl2k5_ps2_replacement_pack_kit as kit  # noqa: E402
import nfl2k5_ps2_replacement_pack_verify as verify  # noqa: E402
from mod_editor.core import ps2_export_service as exporter  # noqa: E402

# The same shapes the verifier's own fixtures use: a canonical PCSX2 name is
# two hashes and a TEX0 word, and the exporter refuses a manifest whose names
# are not that.
WIDE = "%08x" % (0x29 | (9 << 6) | (8 << 10) | (1 << 14))
ONE = "p8:5:one"
FANOUT = "tset:7:4:2:socks01"
NAME_ONE = "1111-2222-" + WIDE + ".png"
NAME_FAN_A = "3333-4444-" + WIDE + ".png"
NAME_FAN_B = "3333-4444-" + WIDE + "-mip1.png"

PROVENANCE = {
    "counts": {"entries": 3},
    "disc": {"serial": "SLUS-20919", "boot_sha256": "0" * 64},
    "emulator": {
        "name": "PenguinScreen2",
        "commit": "0123456789abcdef",
        "hash_convention": "classic-tcc-bit14",
    },
    "generated": "2026-01-01T00:00:00Z",
    "method": "hop1/v5",
}


class KitTests(unittest.TestCase):
    """One honest exported pack, kitted for all three emulators."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ps2-kit-"))
        self.addCleanup(shutil.rmtree, self.work, True)

        document = dict(PROVENANCE)
        document["schema"] = verify.MAPPING_SCHEMA
        document["entries"] = [
            {"pcsx2_png": NAME_ONE, "xbox_asset_id": ONE},
            {"pcsx2_png": NAME_FAN_A, "xbox_asset_id": FANOUT},
            {"pcsx2_png": NAME_FAN_B, "xbox_asset_id": FANOUT},
        ]
        self.manifest = self.work / verify.MAPPING_MANIFEST
        self.manifest.write_bytes(
            json.dumps(document, indent=2, sort_keys=True).encode("utf-8"))

        payload = verify.synthetic_png(512, 256)
        rows = [(ONE, payload), (FANOUT, payload)]
        self.project = self._archive(rows)
        self.pack = self.work / "pack"
        exporter.export_replacement_pack(
            exporter.project_from_targets(rows), self.pack, self.manifest)

    def _archive(self, rows, name: str = "fixture.2k5mod") -> Path:
        path = self.work / name
        with zipfile.ZipFile(path, "w") as archive:
            edits = []
            for asset_id, payload in rows:
                member = "replacements/{key}.png".format(
                    key=hashlib.sha256(asset_id.encode("utf-8")).hexdigest())
                archive.writestr(member, payload)
                edits.append({
                    "asset_id": asset_id,
                    "file": member,
                    "png_sha256": hashlib.sha256(payload).hexdigest(),
                    "rgba_sha256": "0" * 64,
                })
            archive.writestr("manifest.json", json.dumps({
                "schema": "2k5_mod_studio_project/v1",
                "game": "espn_nfl_2k5_xbox",
                "payload_policy": "user-replacements-only",
                "edits": edits,
            }, indent=2, sort_keys=True))
        return path

    def _files(self, root: Path) -> dict:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()
        }

    # -- the copy ------------------------------------------------------

    def test_every_kit_holds_the_pack_byte_for_byte(self) -> None:
        kit.build_kit(self.pack, self.work / "kits")
        original = self._files(self.pack)
        # Not just the PNGs: the receipt and the shipped mapping manifest too,
        # because those are what let anyone check the pack later.
        self.assertIn(verify.RECEIPT_NAME, original)
        self.assertIn(verify.MAPPING_MANIFEST, original)
        for target in kit.EMULATOR_TARGETS:
            with self.subTest(target=target):
                copy = self._files(self.work / "kits" / target / "pack")
                self.assertEqual(copy, original)

    def test_the_pack_inside_a_kit_still_verifies(self) -> None:
        """The kit's extra files live outside the pack for exactly this reason."""

        kit.build_kit(self.pack, self.work / "kits")
        for target in kit.EMULATOR_TARGETS:
            with self.subTest(target=target):
                report = verify.verify(
                    self.work / "kits" / target / "pack", self.manifest,
                    self.project,
                )
                self.assertEqual(report["result"], verify.RESULT_PASS)

    def test_a_kit_can_be_asked_for_one_emulator(self) -> None:
        report = kit.build_kit(self.pack, self.work / "one",
                               (kit.TARGET_PCSX2_MODERN,))
        self.assertEqual(list(report["kits"]), [kit.TARGET_PCSX2_MODERN])
        self.assertFalse((self.work / "one" / kit.TARGET_PCSX2_LEGACY).exists())

    # -- the words -----------------------------------------------------

    def test_each_kit_names_its_own_emulators_settings(self) -> None:
        kit.build_kit(self.pack, self.work / "kits")
        for target in kit.EMULATOR_TARGETS:
            with self.subTest(target=target):
                root = self.work / "kits" / target
                how_to = (root / "HOW-TO.txt").read_text(encoding="utf-8")
                settings = (root / "settings.ini").read_text(encoding="utf-8")
                for row in kit.TARGET_SETTINGS[target]:
                    self.assertIn(row, how_to)
                    self.assertIn(row, settings)
                self.assertIn(kit.LOAD_REPLACEMENTS_SETTING, settings)
                if target != kit.TARGET_PENGUINSCREEN2_CLASSIC:
                    # There is no such setting in stock PCSX2; naming it sends
                    # the reader hunting through a menu that has no such row.
                    self.assertNotIn(kit.CLASSIC_NAMES_SETTING, how_to)
                    self.assertNotIn(kit.CLASSIC_NAMES_SETTING, settings)

    def test_a_kit_says_when_its_emulator_is_not_the_receipts(self) -> None:
        kit.build_kit(self.pack, self.work / "kits")
        crossed = (self.work / "kits" / kit.TARGET_PCSX2_LEGACY
                   / "HOW-TO.txt").read_text(encoding="utf-8")
        self.assertIn("was exported for", crossed)
        self.assertIn("same bytes", crossed)
        document = json.loads(
            (self.work / "kits" / kit.TARGET_PCSX2_LEGACY
             / kit.KIT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(document["kit_target"], kit.TARGET_PCSX2_LEGACY)
        self.assertEqual(document["receipt_emulator_target"],
                         exporter.DEFAULT_EMULATOR_TARGET)

    def test_the_kits_settings_table_matches_the_exporters(self) -> None:
        """Restated, not imported -- so a test has to hold them together."""

        self.assertEqual(kit.EMULATOR_TARGETS, exporter.EMULATOR_TARGETS)
        for target in exporter.EMULATOR_TARGETS:
            with self.subTest(target=target):
                self.assertEqual(kit.TARGET_SETTINGS[target],
                                 exporter.TARGET_SETTINGS[target])

    # -- refusals ------------------------------------------------------

    def test_a_pack_that_no_longer_matches_its_receipt_is_refused(self) -> None:
        victim = self.pack.joinpath(*verify.REPLACEMENTS_PARTS, NAME_ONE)
        victim.write_bytes(victim.read_bytes() + b"\x00")
        with self.assertRaises(kit.PackKitError) as caught:
            kit.build_kit(self.pack, self.work / "kits")
        self.assertIn(NAME_ONE, str(caught.exception))
        self.assertFalse((self.work / "kits" / kit.TARGET_PCSX2_MODERN).exists())

    def test_an_occupied_output_is_refused_rather_than_merged(self) -> None:
        kit.build_kit(self.pack, self.work / "kits")
        with self.assertRaises(kit.PackKitError):
            kit.build_kit(self.pack, self.work / "kits")

    def test_the_tools_own_selftest_passes(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(kit.selftest(), 0)
        self.assertIn("NFL2K5_PS2_REPLACEMENT_PACK_KIT_SELFTEST_PASS",
                      buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
