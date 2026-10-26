"""Team-coloured long sleeves: colour rule, retail binding-table proof, package palettes.

The executable half is pinned on the private retail ``default.xbe`` (skipped when
it is absent); the package half reads the private retail pack index read-only.
The pure colour rule needs neither.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_team_sleeves as sleeves


RETAIL_XBE = Path(os.environ.get(
    "NFL2K5_RETAIL_XBE",
    str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "default.xbe"),
))
RETAIL_INDEX = Path(os.environ.get(
    "NFL2K5_RETAIL_INDEX",
    str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"),
))
RELEASE_DISC = Path(os.environ.get("NFL2K5_RELEASE_DISC") or os.environ.get("NFL2K5_V061_DISC") or "/nonexistent")
COLOUR_CASES = (
    # team style is not black -> keep the game's Team colour
    (((10, 20, 50), (200, 10, 10), None, 0), ((10, 20, 50), "team-style")),
    # black Team style + a coloured jersey -> the jersey's own colour
    (((19, 20, 24), (210, 0, 54), None, 1), ((210, 0, 54), "jersey")),
    # black Team style + a white jersey of a current club -> that club's Team colour
    (((19, 20, 24), (248, 248, 248), None, 28), ((19, 20, 24), "current-team")),
    # black Team style + a white jersey of a historic club -> the helmet colour
    (((19, 20, 24), (248, 248, 248), [((230, 8, 24), 5000), ((248, 248, 248), 900)], 33),
     ((230, 8, 24), "helmet")),
    # a white/silver helmet falls back to a prominent chromatic mark
    (((19, 20, 24), (248, 248, 248), [((248, 248, 248), 5000), ((8, 24, 120), 900)], 50),
     ((8, 24, 120), "helmet")),
    # a white helmet with no team mark leaves the game's placeholder
    (((19, 20, 24), (248, 248, 248), [((248, 248, 248), 5000), ((8, 8, 8), 900)], 46),
     ((19, 20, 24), "default")),
)


class ColourRuleTests(unittest.TestCase):
    def test_choose_target(self):
        for arguments, expected in COLOUR_CASES:
            with self.subTest(arguments=arguments):
                self.assertEqual(sleeves.choose_target(*arguments), expected)

    def test_wet_93(self):
        self.assertEqual(sleeves._wet((100, 50, 1)), (93, 47, 1))


@unittest.skipUnless(RETAIL_XBE.is_file(), "Private retail default.xbe is absent")
class BindingTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not 0 < RETAIL_XBE.stat().st_size <= 16 * 1024 * 1024:
            raise unittest.SkipTest("Retail executable has an unexpected size")
        cls.retail = RETAIL_XBE.read_bytes()

    def test_style_table_maps_white_black_team_to_rows_35_36_37(self):
        self.assertEqual(sleeves.style_table(self.retail), (35, 36, 37))

    def test_retail_is_row36_global_and_apply_flips_only_it(self):
        self.assertEqual(sleeves.status(self.retail), "retail")
        patched, receipt = sleeves.apply(self.retail)
        self.assertEqual(sleeves.status(patched), "applied")
        self.assertEqual(receipt["row"], 36)
        self.assertEqual(receipt["name"], "longsleeve02")
        self.assertEqual(receipt["native_code_bytes"], 0)
        image = sleeves.XbeImage(self.retail)
        off = image.offset(sleeves.BLACK_FLAG_VA, 4)
        self.assertEqual(struct.unpack_from("<I", patched, off)[0], 1)
        # only the flag word and the .rdata digest move
        diff = [index for index, (a, b) in enumerate(zip(self.retail, patched)) if a != b]
        self.assertIn(off, diff)
        self.assertLessEqual(len(diff), 4 + 20)
        again, second = sleeves.apply(patched)
        self.assertTrue(second["already_applied"])
        self.assertEqual(again, patched)

    def test_foreign_table_is_refused(self):
        broken = bytearray(self.retail)
        image = sleeves.XbeImage(self.retail)
        off = image.offset(sleeves.BLACK_FLAG_VA, 4)
        struct.pack_into("<I", broken, off, 2)
        self.assertEqual(sleeves.status(bytes(broken)), "foreign")
        with self.assertRaises(sleeves.TeamSleevesError):
            sleeves.apply(bytes(broken))


@unittest.skipUnless(RETAIL_INDEX.is_file(), "Private retail pack index is absent")
class RetailPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl_outer import parse_archive
        from mod_editor.core.nfl2k5_uniform_equipment_writer import load_targets
        cls.archive = parse_archive(RETAIL_INDEX)
        cls.by_id, cls.groups = load_targets()
        cls.outer = {target.set_selector: target.outer_index
                     for target in cls.by_id.values()
                     if target.chunk_index == 7 and target.name.startswith("longsleeve")}

    def package(self, selector):
        from nfl_outer import read_entry_bytes
        return read_entry_bytes(self.archive, self.archive.entries[self.outer[selector]])

    @staticmethod
    def chunks(raw):
        from nfl_txtr import parse_chunks
        return {chunk.index: chunk for chunk in parse_chunks(raw, allow_trailing=True)
                if chunk.kind in ("TSET", "TXTR")}

    def palettes(self, raw):
        from nfl_txtr import decode_chunk
        from mod_editor.core import nfl2k5_kit_fixes_2026 as kit
        chunk = self.chunks(raw)[7]
        decoded, _ = decode_chunk(raw, chunk)
        textures = {item["name"]: item for item in kit._tset_textures(decoded)}
        return {name: kit.read_palette(decoded, chunk, texture)
                for name, texture in textures.items()}, chunk, decoded

    def test_kc_keeps_the_games_own_team_colour(self):
        raw = self.package("13H0")
        rows = self.groups[(self.outer["13H0"], 7)]
        span, receipt = sleeves.compile_package(raw, self.chunks(raw), rows)
        self.assertEqual(receipt["rule"], "team-style")
        self.assertGreater(receipt["changed_bytes"], 0)
        after, chunk, decoded = self.palettes_from_span(raw, span)
        before, _chunk, _decoded = self.palettes(raw)
        self.assertTrue((after["longsleeve02"] == before["longsleeve03"]).all())
        self.assertTrue((after["longsleeve02_mud"] == before["longsleeve03_mud"]).all())
        self.assertTrue((after["longsleeve01"] == before["longsleeve01"]).all())
        self.assertEqual(len(span), len(raw[self.chunks(raw)[7].offset:self.chunks(raw)[7].end_offset]))

    def test_historic_white_jersey_takes_the_helmet_colour(self):
        raw = self.package("33A0")
        rows = self.groups[(self.outer["33A0"], 7)]
        span, receipt = sleeves.compile_package(raw, self.chunks(raw), rows)
        self.assertEqual(receipt["rule"], "helmet")
        self.assertGreater(receipt["target"][0], receipt["target"][1] + 40)
        after, _chunk, _decoded = self.palettes_from_span(raw, span)
        self.assertTrue((after["longsleeve02"] == after["longsleeve03"]).all())
        self.assertEqual(int(after["longsleeve02"][0, 0]), receipt["target"][0])

    def test_a_second_pass_is_a_no_op(self):
        raw = self.package("33A0")
        rows = self.groups[(self.outer["33A0"], 7)]
        span, _receipt = sleeves.compile_package(raw, self.chunks(raw), rows)
        chunks = {7: __import__("nfl_txtr").parse_chunks(span, allow_trailing=True)[0]}
        again, receipt = sleeves.compile_package(span, chunks, rows)
        self.assertEqual(receipt["state"], "already")
        self.assertEqual(again, span)

    def palettes_from_span(self, raw, span):
        from nfl_txtr import parse_chunks
        chunk = parse_chunks(span)[0]
        from nfl_txtr import decode_chunk
        from mod_editor.core import nfl2k5_kit_fixes_2026 as kit
        decoded, _ = decode_chunk(span, chunk)
        textures = {item["name"]: item for item in kit._tset_textures(decoded)}
        return ({name: kit.read_palette(decoded, chunk, texture)
                 for name, texture in textures.items()}, chunk, decoded)


class BuildOptionTests(unittest.TestCase):
    def test_default_is_off_and_every_softdrink_preset_turns_it_on(self):
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").team_sleeves)
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertIs(mod_build.PRESETS[name]["team_sleeves"], True, name)
            self.assertTrue(mod_build.apply_preset(
                mod_build.BuildPlan(source="s", target="t"), name).team_sleeves, name)

    def test_recipe_round_trips_the_switch(self):
        plan = mod_build.BuildPlan(source="s", target="t", team_sleeves=True)
        self.assertIs(plan.to_recipe()["team_sleeves"], True)


@unittest.skipUnless(RELEASE_DISC.is_file(), "Private released disc is absent")
class ApplyToImageTests(unittest.TestCase):
    """The full Studio pass on the real disc: enumerate, compile, write and read back."""

    def test_selected_packages_are_compiled_and_written(self):
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_bump_texture_writer as bump

        class Recording:
            def __init__(self, path, writable):
                self.inner = bump._Image._open_xiso(path, writable=False)
                self.writes = {}
                self.closed = False

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.closed = True
                self.inner.close()
                return False

            def write_segments(self, segments, data):
                self.writes[tuple(segments)] = data

            def read_segments(self, segments):
                recorded = self.writes.get(tuple(segments))
                return recorded if recorded is not None else self.inner.read_segments(segments)

        opened = []

        def open_image(path, *, writable):
            proxy = Recording(path, writable)
            opened.append(proxy)
            return proxy

        original = sleeves._package_selectors
        keep = ("00H0", "13H0", "33A0", "21H9")

        def selected(by_id):
            full = original(by_id)
            return {name: full[name] for name in keep}

        with patch.object(bump._Image, "open", classmethod(lambda cls, path, *, writable: open_image(path, writable=writable))), \
                patch.object(sleeves, "_package_selectors", selected):
            receipt = sleeves.apply_to_image(RELEASE_DISC)
        self.assertEqual(receipt["state"], "applied")
        self.assertEqual(receipt["written_spans"], 4)
        self.assertEqual(sorted(item["selector"] for item in receipt["packages"]), sorted(keep))
        writes = {proxy for proxy in opened if proxy.writes}
        self.assertEqual(len(writes), 1)
        self.assertEqual(len(next(iter(writes)).writes), 4)
        self.assertTrue(all(item["state"] == "applied" for item in receipt["packages"]))
        self.assertFalse(receipt["runtime_witnessed"])

    def test_kept_packages_are_left_as_they_are(self):
        # b778 bd3: the historic team styles pin their spare kits to the retail style-0 art; the Eagles' spare is the
        # retail era-9 package 21H9/21A9, which the build now passes as kept.
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_bump_texture_writer as bump
        writes = []

        class Recording:
            def __init__(self, path):
                self.inner = bump._Image._open_xiso(path, writable=False)

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.inner.close()
                return False

            def write_segments(self, segments, data):
                writes.append(tuple(segments))
                self._last = (tuple(segments), data)

            def read_segments(self, segments):
                last = getattr(self, "_last", None)
                return last[1] if last and last[0] == tuple(segments) else self.inner.read_segments(segments)

        original = sleeves._package_selectors
        chosen = ("00H0", "21H9", "21A9")

        def selected(by_id):
            full = original(by_id)
            return {name: full[name] for name in chosen}

        with patch.object(bump._Image, "open", classmethod(lambda cls, path, *, writable: Recording(path))), \
                patch.object(sleeves, "_package_selectors", selected):
            receipt = sleeves.apply_to_image(RELEASE_DISC, keep=("21H9", "21A9"))
        self.assertEqual(sorted(receipt["kept"]), ["21A9", "21H9"])
        self.assertEqual([item["selector"] for item in receipt["packages"]], ["00H0"])
        self.assertEqual(receipt["written_spans"], 1)
        self.assertEqual(len(writes), 1)


if __name__ == "__main__":
    unittest.main()
