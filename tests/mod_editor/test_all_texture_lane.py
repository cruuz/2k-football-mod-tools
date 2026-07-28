"""The general P8 texture lane: plan discipline, mip maths, and refusals.

Modders kept reporting the same shape of gap: the inventory can see all 57,208
textures, but only a curated handful could be edited.  Goalpost pads, the real
teams' end-zone art, ``divots``, the ``mark*`` overlays and shared equipment
like ``shoes_taped`` had no writer at all.  ``nfl_all_texture_xiso_workflow``
is that writer.

Everything here runs without retail data.  The parts that need a real disc --
resolving a target inside a real package and rebuilding its compressed span --
are exercised by the retail-gated test at the bottom, which skips when the
extracted index is absent, exactly like the rest of the suite.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_all_texture_xiso_workflow as lane  # noqa: E402

_INDEX = _REPO_ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"


def _plan(edits: list[dict[str, object]], schema: str = lane.PLAN_SCHEMA) -> Path:
    directory = tempfile.mkdtemp()
    path = Path(directory) / "plan.json"
    path.write_text(json.dumps({"schema": schema, "edits": edits}),
                    encoding="utf-8", newline="\n")
    return path


class PlanDisciplineTests(unittest.TestCase):
    def test_a_well_formed_plan_is_accepted(self) -> None:
        path = _plan([{"outer_index": 3136, "texture": "pad_north", "png": "a.png"}])
        _resolved, _payload, edits = lane.read_plan(path)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["texture"], "pad_north")

    def test_a_foreign_schema_is_refused(self) -> None:
        path = _plan([{"outer_index": 0, "texture": "t", "png": "a.png"}],
                     schema="something_else/v1")
        with self.assertRaises(lane.TextureWorkflowError):
            lane.read_plan(path)

    def test_an_edit_with_extra_or_missing_keys_is_refused(self) -> None:
        for edit in ({"outer_index": 0, "texture": "t"},
                     {"outer_index": 0, "texture": "t", "png": "a.png", "extra": 1}):
            with self.subTest(edit=edit):
                with self.assertRaises(lane.TextureWorkflowError):
                    lane.read_plan(_plan([edit]))

    def test_a_negative_or_non_integer_index_is_refused(self) -> None:
        for value in (-1, "3136", 3136.0, True):
            with self.subTest(value=value):
                with self.assertRaises(lane.TextureWorkflowError):
                    lane.read_plan(_plan(
                        [{"outer_index": value, "texture": "t", "png": "a.png"}]))

    def test_an_empty_plan_is_refused(self) -> None:
        with self.assertRaises(lane.TextureWorkflowError):
            lane.read_plan(_plan([]))


class MipChainTests(unittest.TestCase):
    """The retail chain length is what the palette offset has to equal."""

    def test_a_single_level_chain_is_the_base_image(self) -> None:
        rgba = bytes(4 * 4 * 4)
        levels = lane.generate_mips(rgba, 4, 4, 1)
        self.assertEqual([(item.width, item.height) for item in levels], [(4, 4)])

    def test_each_level_halves(self) -> None:
        levels = lane.generate_mips(bytes(128 * 128 * 4), 128, 128, 5)
        self.assertEqual([(i.width, i.height) for i in levels],
                         [(128, 128), (64, 64), (32, 32), (16, 16), (8, 8)])

    def test_the_chain_length_matches_the_retail_palette_offset(self) -> None:
        """pad_north is 128x128 with 5 levels and palette_offset 21824."""
        levels = lane.generate_mips(bytes(128 * 128 * 4), 128, 128, 5)
        self.assertEqual(sum(i.width * i.height for i in levels), 21824)

    def test_a_box_filter_averages_its_four_sources(self) -> None:
        base = bytearray(2 * 2 * 4)
        for index, value in enumerate((0, 100, 200, 255)):
            base[index * 4:index * 4 + 4] = bytes((value,) * 4)
        levels = lane.generate_mips(bytes(base), 2, 2, 2)
        self.assertEqual(levels[1].rgba, bytes((139,) * 4))  # (0+100+200+255+2)//4

    def test_an_odd_size_cannot_be_halved_and_is_refused(self) -> None:
        with self.assertRaises(lane.TextureWorkflowError):
            lane.generate_mips(bytes(3 * 3 * 4), 3, 3, 2)

    def test_a_wrong_sized_buffer_is_refused(self) -> None:
        with self.assertRaises(lane.TextureWorkflowError):
            lane.generate_mips(bytes(10), 4, 4, 1)


class ContractTests(unittest.TestCase):
    def test_only_p8_is_claimed(self) -> None:
        self.assertEqual(lane.SUPPORTED_FORMATS, ("P8",))

    def test_the_palette_is_a_fixed_1024_byte_block(self) -> None:
        self.assertEqual(lane.PALETTE_BYTES, 1024)

    def test_the_writer_does_not_gate_on_the_container(self) -> None:
        """The defect that refused legal dumps must not come back here."""
        source = Path(lane.__file__).read_text(encoding="utf-8")
        for pin in ("EXPECTED_XISO_SIZE", "EXPECTED_XISO_SHA256"):
            self.assertNotIn(
                pin, source,
                f"{pin} identifies how a disc was dumped, not which game it is; "
                "identity here is default.xbe plus each touched pack",
            )


@unittest.skipUnless(_INDEX.is_file(), "retail extracted index is not present")
class RetailTargetTests(unittest.TestCase):
    """Resolve real targets. Skipped anywhere the private index is absent."""

    @classmethod
    def setUpClass(cls) -> None:
        from nfl_outer import parse_archive
        cls.archive = parse_archive(_INDEX)

    def test_a_goalpost_pad_resolves_with_its_retail_layout(self) -> None:
        target = lane.resolve_target(self.archive, 3136, "pad_north")
        self.assertEqual((target.width, target.height), (128, 128))
        self.assertEqual(target.mip_levels, 5)
        self.assertEqual(target.palette_offset, 21824)
        self.assertEqual(target.pack_name, "8")

    def test_team_end_zone_art_resolves(self) -> None:
        target = lane.resolve_target(self.archive, 853, "endzone_north_left")
        self.assertEqual((target.width, target.height), (256, 128))
        self.assertEqual(target.pack_name, "1")

    def test_an_absent_texture_name_is_refused(self) -> None:
        with self.assertRaises(lane.TextureWorkflowError):
            lane.resolve_target(self.archive, 3136, "no_such_texture")

    def test_an_out_of_range_package_is_refused(self) -> None:
        with self.assertRaises(lane.TextureWorkflowError):
            lane.resolve_target(self.archive, 10 ** 9, "pad_north")

    def test_a_replacement_refits_the_exact_retail_span(self) -> None:
        """The core safety property: same bytes in, same span size out."""
        from nfl_txtr import decode_chunk, texture_to_rgba, parse_texture, write_png
        import dataclasses

        target = lane.resolve_target(self.archive, 3136, "pad_north")
        standalone = dataclasses.replace(target.chunk, offset=0)
        decoded, _ = decode_chunk(target.template_span, standalone)
        info = parse_texture(decoded, standalone)
        rgba = bytearray(texture_to_rgba(decoded, standalone, info))
        for index in range(0, len(rgba), 4):
            rgba[index] = 255 - rgba[index]
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "pad.png"
            write_png(png, target.width, target.height, bytes(rgba))
            replacement, report = lane.build_replacement(target, png)
        self.assertEqual(len(replacement), len(target.template_span))
        self.assertNotEqual(replacement, target.template_span)
        self.assertLessEqual(report["palette_entries"], 256)

    def test_a_png_of_the_wrong_size_is_refused(self) -> None:
        from nfl_txtr import write_png

        target = lane.resolve_target(self.archive, 3136, "pad_north")
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "wrong.png"
            write_png(png, 64, 64, bytes(64 * 64 * 4))
            with self.assertRaises(Exception):
                lane.build_replacement(target, png)


if __name__ == "__main__":
    unittest.main()
